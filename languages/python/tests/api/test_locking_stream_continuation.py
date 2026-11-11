from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import closing
from typing import Any

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    attr,
)
from parallax.core.execution_lifecycle import DatabaseCallFailed, DatabaseCallFinished
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import TablePerConcreteSubtype
from parallax.snapshot import ScopedDatabase, TxnContext, WireEntity, connect
from tests._support.retry import fast_retry
from tests._support.root_ownership import own_root

_NAMESPACE = "locking.stream"


class Counter(Entity, table="ls_counter", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    position: Attr[int | None]
    seats: Attr[int]


class VersionedCounter(Entity, table="ls_versioned", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    position: Attr[int | None]
    seats: Attr[int]
    version: Attr[int] = attr(optimistic_locking=True)


class DocumentCounter(Entity, table="ls_document", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    position: Attr[int | None]
    seats: Attr[int]
    version: Attr[int] = attr(optimistic_locking=True)


class Vehicle(Entity, namespace=_NAMESPACE, inheritance=AbstractRoot(TablePerConcreteSubtype())):
    id: Attr[int] = attr(primary_key=True)
    position: Attr[int | None]


class Car(Vehicle, table="ls_car", namespace=_NAMESPACE, inheritance=ConcreteSubtype()):
    seats: Attr[int]


class Bike(Vehicle, table="ls_bike", namespace=_NAMESPACE, inheritance=ConcreteSubtype()):
    gears: Attr[int]


_MODEL = DomainModel(Counter, VersionedCounter, DocumentCounter, Vehicle, Car, Bike)
_TABLES: dict[type[Any], str] = {
    Counter: "ls_counter",
    VersionedCounter: "ls_versioned",
    DocumentCounter: "ls_document",
    Car: "ls_car",
}
_VERSIONED: tuple[type[Any], ...] = (VersionedCounter, DocumentCounter)
_SHAPES = (
    (Counter, "id"),
    (Counter, "position"),
    (VersionedCounter, "id"),
    (VersionedCounter, "position"),
    (DocumentCounter, "id"),
    (Car, "id"),
    (Car, "position"),
)


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _seeded(profile_run: Any, provider: RecordingLifecycleProvider | None = None) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    db = own_root(
        connect(profile_run.port, _MODEL, lifecycle_provider=provider)
    ).using_database_login()

    def seed(tx: TxnContext) -> None:
        for entity in _TABLES:
            for key, position in ((1, 10), (2, 20), (3, 30), (4, 40), (5, 50), (6, None)):
                tx.wire.insert(_name(entity), {"id": key, "position": position, "seats": 4})
        tx.insert(Bike(id=2, position=20, gears=6))

    db.transact(seed)
    # The race needs the small-table plan to return the contended row instead
    # of dropping it during Read Committed's concurrent-update recheck.
    with closing(profile_run.control()) as control:
        for table in _TABLES.values():
            control.execute_write(f"analyze {table}", [])
    return db


def _stream(tx: TxnContext, entity: type[Any], order: str, wire: bool) -> Any:
    target = Vehicle if entity is Car else entity
    query = target.where(target.all)
    if entity is Car:
        query = query.narrow(Car)
    query = query.order_by(getattr(target, order).asc())
    return (tx.wire if wire else tx).stream(query, batch_size=2)


def _value(source: Any, member: str) -> Any:
    return source[member] if isinstance(source, WireEntity) else getattr(source, member)


def _increment(tx: TxnContext, source: Any) -> None:
    value = _value(source, "seats") + 1
    if isinstance(source, WireEntity):
        tx.wire.amend(source, {"seats": value})
    else:
        tx.amend(source.edit(seats=value))


def _peer_update(entity: type[Any], *, move: bool = False) -> str:
    assignments = (
        "payload = jsonb_set(payload, '{seats}', '8')" if entity is DocumentCounter else "seats = 8"
    )
    if entity in _VERSIONED:
        assignments += ", version = version + 1"
    if move:
        assignments += ", position = 45"
    return f"update {_TABLES[entity]} set {assignments} where id = 4"


def _behind_updater(
    profile_run: Any, update: str, operation: Callable[[], None]
) -> BaseException | None:
    outcomes: list[BaseException | None] = []

    def run() -> None:
        try:
            operation()
        except BaseException as error:
            outcomes.append(error)
        else:
            outcomes.append(None)

    with (
        closing(profile_run.control(autocommit=False)) as peer,
        closing(profile_run.control()) as observer,
    ):
        ((pid,),) = peer.execute("select pg_backend_pid()", [])
        peer.execute_write(update, [])
        thread = threading.Thread(target=run)
        thread.start()
        try:
            waited = False
            poll = threading.Event()
            for _ in range(500):
                ((blocked,),) = observer.execute(
                    "select count(*) from pg_stat_activity "
                    "where datname = current_database() and ? = any(pg_blocking_pids(pid)) "
                    "and position('union all' in query) > 0",
                    [pid],
                )
                if blocked:
                    waited = True
                    break
                if not thread.is_alive():
                    break
                poll.wait(0.02)
            assert waited, f"continuation did not wait behind the updater: {outcomes!r}"
            peer.execute("commit", [])
        finally:
            peer.execute("rollback", [])
            thread.join(timeout=30)
        assert not thread.is_alive()
    (outcome,) = outcomes
    return outcome


@pytest.mark.parametrize("wire", [False, True], ids=["typed", "wire"])
@pytest.mark.parametrize(("entity", "order"), _SHAPES)
def test_locking_continuation_publishes_the_row_its_lock_protects(
    profile_run: Any, entity: type[Any], order: str, wire: bool
) -> None:
    db = _seeded(profile_run)
    observed: list[tuple[int, int, int | None]] = []
    options: dict[str, Any] = {"concurrency": "locking"} if entity in _VERSIONED else {}

    def increment(tx: TxnContext) -> None:
        with _stream(tx, entity, order, wire) as stream:
            for source in stream:
                key = _value(source, "id")
                version = _value(source, "version") if entity in _VERSIONED else None
                observed.append((key, _value(source, "seats"), version))
                if key == 4:
                    _increment(tx, source)

    # The first two-root page also locks lookahead row 3; row 4 belongs to
    # the next page's delivered prefix.
    outcome = _behind_updater(
        profile_run,
        _peer_update(entity, move=order == "position"),
        lambda: db.transact(increment, **options),
    )
    if outcome is not None:
        raise outcome
    versioned = entity in _VERSIONED
    stored = db.find(entity.where(entity.id == 4)).result()
    assert stored.seats == 9
    assert observed == [
        (1, 4, 1 if versioned else None),
        (2, 4, 1 if versioned else None),
        (3, 4, 1 if versioned else None),
        (4, 8, 2 if versioned else None),
        (5, 4, 1 if versioned else None),
        (6, 4, 1 if versioned else None),
    ]
    if versioned:
        assert stored.version == 3
    if order == "position":
        assert stored.position == 45
    if entity is Car:
        assert db.find(Bike.where(Bike.id == 2)).result().gears == 6


@pytest.mark.parametrize("wire", [False, True], ids=["typed", "wire"])
@pytest.mark.parametrize("retries", [0, 1], ids=["disabled", "retry"])
def test_repeatable_read_restarts_the_whole_attempt_or_reports_serialization_failure(
    profile_run: Any, wire: bool, retries: int
) -> None:
    provider = RecordingLifecycleProvider()
    db = _seeded(profile_run, provider)
    attempts: list[list[tuple[int, int]]] = []

    def increment(tx: TxnContext) -> None:
        seen: list[tuple[int, int]] = []
        attempts.append(seen)
        with _stream(tx, Counter, "id", wire) as stream:
            for source in stream:
                key = _value(source, "id")
                seen.append((key, _value(source, "seats")))
                _increment(tx, source)

    outcome = _behind_updater(
        profile_run,
        _peer_update(Counter),
        lambda: db.transact(increment, isolation="repeatable_read", retry=fast_retry(retries)),
    )
    failures = [
        (event.outcome.diagnostic.category, event.outcome.diagnostic.native_code)
        for root in provider.roots
        for event in root.events
        if isinstance(event, DatabaseCallFinished) and isinstance(event.outcome, DatabaseCallFailed)
    ]
    assert failures == [("deadlock", "40001")]
    assert attempts[0] == [(1, 4), (2, 4)]
    if retries:
        if outcome is not None:
            raise outcome
        assert attempts == [
            [(1, 4), (2, 4)],
            [(1, 4), (2, 4), (3, 4), (4, 8), (5, 4), (6, 4)],
        ]
        expected = [(1, 5), (2, 5), (3, 5), (4, 9), (5, 5), (6, 5)]
    else:
        assert isinstance(outcome, DatabaseError)
        assert (outcome.category, outcome.native_code) == ("deadlock", "40001")
        assert len(attempts) == 1
        expected = [(1, 4), (2, 4), (3, 4), (4, 8), (5, 4), (6, 4)]
    assert [
        (row.id, row.seats)
        for row in db.find(Counter.where(Counter.all).order_by(Counter.id.asc())).results()
    ] == expected
