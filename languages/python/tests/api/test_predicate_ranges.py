"""A Bitemporal ``amend_where`` against real Postgres: membership selected at
``valid_from``, later coverage amended when the flush reaches it.

Each case commits a starting history, amends it through the public predicate
verbs in a later transaction, and reads back every row — current and
historical, under both storage layouts. Where another session commits between
the call and its flush, the read the flush makes sees that commit for the
later coverage, while the selected starting row keeps the proof its selection
observed: a peer's change there is the attempt's conflict. Under Locking the
selection holds the starting row's lock from the call, and a later row is
locked only when the flush reads it.

Every `Database` connects with a
:class:`~parallax.conformance.scripted_clock.ScriptedClock`, so every
Transaction-Time instant is known in advance.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Literal

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import Attr, Bitemporal, Document, DomainModel, attr
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.unit_work import OptimisticLockConflictError
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root

_NAMESPACE = "predicate.ranges"


class ColumnsRange(Bitemporal, table="pr_columns_range", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str] = attr(max_length=16)


class DocumentRange(Bitemporal, table="pr_document_range", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str] = attr(max_length=16)


_MODEL = DomainModel(ColumnsRange, DocumentRange)
_TABLES: dict[type[Any], str] = {
    ColumnsRange: "pr_columns_range",
    DocumentRange: "pr_document_range",
}

type _Concurrency = Literal["optimistic", "locking"]
type _Representation = Literal["typed", "wire"]

_AXES = pytest.mark.parametrize(
    "entity", [ColumnsRange, DocumentRange], ids=["columns", "document"]
)
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])

_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T1 = dt.datetime(2023, 12, 15, tzinfo=dt.UTC)
_TP = dt.datetime(2024, 1, 5, tzinfo=dt.UTC)
_TA = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_TB = dt.datetime(2024, 1, 20, tzinfo=dt.UTC)
_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _JUL, _AUG, _SEP = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in range(1, 10)
)


def _db(profile_run: Any, *instants: dt.datetime) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock(list(instants)))
    ).using_database_login()


def _member(entity: type[Any], member: str) -> str:
    return f"(payload->>'{member}')" if entity is DocumentRange else member


def _rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        "select id, in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        f"case when thru_z = 'infinity' then null else thru_z end, "
        f"{_member(entity, 'amount')}::int, {_member(entity, 'label')} "
        f"from {_TABLES[entity]} order by id, in_z, out_z, from_z"
    )
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def _seed(profile_run: Any, entity: type[Any], *, start: int = 100) -> None:
    """Object 1 as [January, June) at ``start`` opened at T0 and [June,
    infinity) at 200 opened at T1; object 2 as [January, infinity) at 900."""
    profile_run.reset(model_of(_MODEL), {})
    seeder = _db(profile_run, _T0, _T1)

    def first(tx: Transaction) -> None:
        tx.insert(entity(id=1, amount=start, label="a"), valid_from=_JAN, until=_JUN)
        tx.insert(entity(id=2, amount=900, label="z"), valid_from=_JAN)

    seeder.transact(first)
    seeder.transact(lambda tx: tx.insert(entity(id=1, amount=200, label="b"), valid_from=_JUN))


def _amend(
    tx: Transaction,
    entity: type[Any],
    representation: _Representation = "typed",
    *,
    selects: int = 100,
    assigns: int = 150,
) -> None:
    if representation == "typed":
        tx.amend_where(
            entity.where(entity.amount == selects),
            entity.amount.set(assigns),
            valid_from=_MAR,
            until=_SEP,
        )
        return
    name = f"{_NAMESPACE}.{entity.__name__}"
    tx.wire.amend_where(
        {"entity": name, "predicate": {"eq": {"attr": f"{name}.amount", "value": selects}}},
        {"amount": assigns},
        valid_from=_MAR,
        until=_SEP,
    )


def _find(tx: Transaction, entity: type[Any], at: dt.datetime) -> Any:
    return tx.find(entity.where(entity.id == 1).as_of(valid_time=at)).result()


def _relabel(
    peer: ScopedDatabase, entity: type[Any], at: dt.datetime, until: dt.datetime, label: str
) -> None:
    """Have another session relabel object 1 from ``at`` until ``until`` and
    commit, on a thread of its own, while this one's transaction stays open."""
    failures: list[BaseException] = []

    def run() -> None:
        try:
            peer.transact(
                lambda other: other.amend(_find(other, entity, at).edit(label=label), until=until)
            )
        except BaseException as failure:
            failures.append(failure)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=30.0)
    assert not thread.is_alive() and failures == []


_UNTOUCHED = (2, _T0, None, _JAN, None, 900, "z")


@_AXES
@_STRATEGIES
@pytest.mark.parametrize("representation", ["typed", "wire"])
def test_membership_is_fixed_at_valid_from_and_later_coverage_is_amended(
    profile_run: Any,
    entity: type[Any],
    concurrency: _Concurrency,
    representation: _Representation,
) -> None:
    # In March object 1 holds 100, so it is selected; its June rectangle holds
    # 200, which the predicate does not match, and is amended all the same
    # through September. Object 2 holds 900 and is untouched.
    _seed(profile_run, entity)
    _db(profile_run, _TA).transact(
        lambda tx: _amend(tx, entity, representation), concurrency=concurrency
    )
    assert _rows(profile_run, entity) == [
        (1, _T0, _TA, _JAN, _JUN, 100, "a"),
        (1, _T1, _TA, _JUN, None, 200, "b"),
        (1, _TA, None, _JAN, _MAR, 100, "a"),
        (1, _TA, None, _MAR, _JUN, 150, "a"),
        (1, _TA, None, _JUN, _SEP, 150, "b"),
        (1, _TA, None, _SEP, None, 200, "b"),
        _UNTOUCHED,
    ]


@_AXES
@_STRATEGIES
def test_a_start_already_holding_the_value_still_amends_its_later_coverage(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    # March already holds 150: that rectangle is kept whole, and June's 200 is
    # amended through September.
    _seed(profile_run, entity, start=150)
    _db(profile_run, _TA).transact(
        lambda tx: _amend(tx, entity, selects=150), concurrency=concurrency
    )
    assert _rows(profile_run, entity) == [
        (1, _T0, None, _JAN, _JUN, 150, "a"),
        (1, _T1, _TA, _JUN, None, 200, "b"),
        (1, _TA, None, _JUN, _SEP, 150, "b"),
        (1, _TA, None, _SEP, None, 200, "b"),
        _UNTOUCHED,
    ]


@_AXES
def test_no_object_matching_at_valid_from_writes_nothing(
    profile_run: Any, entity: type[Any]
) -> None:
    # Only the June rectangle holds 200, after March: nothing is selected.
    _seed(profile_run, entity)
    _db(profile_run, _TA).transact(lambda tx: _amend(tx, entity, selects=200))
    assert _rows(profile_run, entity) == [
        (1, _T0, None, _JAN, _JUN, 100, "a"),
        (1, _T1, None, _JUN, None, 200, "b"),
        _UNTOUCHED,
    ]


@_AXES
@_STRATEGIES
def test_the_flush_reads_later_coverage_a_peer_committed_after_the_call(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    # The peer relabels July through September after the selection and before
    # the flush; the flush reads the coverage it left and amends it, keeping
    # each rectangle's own label.
    _seed(profile_run, entity)
    peer = _db(profile_run, _TP)

    def fn(tx: Transaction) -> None:
        _amend(tx, entity)
        _relabel(peer, entity, _JUL, _SEP, "p")

    _db(profile_run, _TA).transact(fn, concurrency=concurrency)
    assert _rows(profile_run, entity) == [
        (1, _T0, _TA, _JAN, _JUN, 100, "a"),
        (1, _T1, _TP, _JUN, None, 200, "b"),
        (1, _TP, _TA, _JUN, _JUL, 200, "b"),
        (1, _TP, _TA, _JUL, _SEP, 200, "p"),
        (1, _TP, None, _SEP, None, 200, "b"),
        (1, _TA, None, _JAN, _MAR, 100, "a"),
        (1, _TA, None, _MAR, _JUN, 150, "a"),
        (1, _TA, None, _JUN, _JUL, 150, "b"),
        (1, _TA, None, _JUL, _SEP, 150, "p"),
        _UNTOUCHED,
    ]


def _peer_changes_the_start(profile_run: Any, entity: type[Any], *, retry: bool) -> int:
    """Amend through an attempt whose first try sees a peer relabel the
    selected start before the flush, answering how many attempts ran."""
    peer = _db(profile_run, _TP)
    attempts = 0

    def fn(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        _amend(tx, entity)
        if attempts == 1:
            _relabel(peer, entity, _FEB, _APR, "p")

    _db(profile_run, _TA, _TB).transact(fn, retry_optimistic_conflicts=retry)
    return attempts


@_AXES
def test_a_peers_change_of_the_selected_start_is_the_attempts_conflict(
    profile_run: Any, entity: type[Any]
) -> None:
    # The selection observed March's rectangle at T0; a peer replaces it
    # before the flush, so the starting gate falls short as an ordinary
    # conflict, which an opted-in retry reselects past.
    _seed(profile_run, entity)
    with pytest.raises(ExecutionFailure) as failed:
        _peer_changes_the_start(profile_run, entity, retry=False)
    assert isinstance(failed.value.cause, OptimisticLockConflictError)

    _seed(profile_run, entity)
    assert _peer_changes_the_start(profile_run, entity, retry=True) == 2
    assert [row for row in _rows(profile_run, entity) if row[2] is None] == [
        (1, _TP, None, _JAN, _FEB, 100, "a"),
        (1, _TB, None, _FEB, _MAR, 100, "p"),
        (1, _TB, None, _MAR, _APR, 150, "p"),
        (1, _TB, None, _APR, _JUN, 150, "a"),
        (1, _TB, None, _JUN, _SEP, 150, "b"),
        (1, _TB, None, _SEP, None, 200, "b"),
        _UNTOUCHED,
    ]


def _waiting(control: Any) -> bool:
    ((count,),) = control.execute("select count(*) from pg_locks where not granted", [])
    return bool(count)


@_AXES
def test_a_locking_selection_locks_its_start_at_the_call_and_later_rows_at_the_flush(
    profile_run: Any, entity: type[Any]
) -> None:
    _seed(profile_run, entity)
    later_peer = _db(profile_run, _TP)
    start_peer = _db(profile_run, _TB)
    control = profile_run.control()
    failures: list[BaseException] = []

    def change_the_start() -> None:
        try:
            start_peer.transact(
                lambda other: other.amend(_find(other, entity, _FEB).edit(label="p"), until=_APR)
            )
        except BaseException as failure:
            failures.append(failure)

    blocked = threading.Thread(target=change_the_start)

    def fn(tx: Transaction) -> None:
        _amend(tx, entity)
        # The later rectangle is not locked yet: a peer relabels it and commits.
        _relabel(later_peer, entity, _JUL, _SEP, "q")
        # The selected start is: a peer revising it waits until the commit.
        blocked.start()
        deadline = time.monotonic() + 10.0
        while not _waiting(control):
            assert time.monotonic() < deadline, "the peer never waited on the selection's lock"
            time.sleep(0.05)

    try:
        _db(profile_run, _TA).transact(fn, concurrency="locking")
        blocked.join(timeout=10.0)
    finally:
        control.close()
    (failure,) = failures
    assert isinstance(failure, ExecutionFailure)
    assert isinstance(failure.cause, OptimisticLockConflictError)
    assert [row for row in _rows(profile_run, entity) if row[2] is None] == [
        (1, _TP, None, _SEP, None, 200, "b"),
        (1, _TA, None, _JAN, _MAR, 100, "a"),
        (1, _TA, None, _MAR, _JUN, 150, "a"),
        (1, _TA, None, _JUN, _JUL, 150, "b"),
        (1, _TA, None, _JUL, _SEP, 150, "q"),
        _UNTOUCHED,
    ]


@_AXES
def test_a_failed_flush_rolls_back_every_batch_it_executed(
    profile_run: Any, entity: type[Any]
) -> None:
    # The amendment's objects settle and execute; a caller-addressed write the
    # same flush runs afterwards states a start object 2 does not hold, so the
    # whole attempt rolls back, the amendment's statements included.
    _seed(profile_run, entity)

    def fn(tx: Transaction) -> None:
        _amend(tx, entity)
        tx.wire.amend_if(
            f"{_NAMESPACE}.{entity.__name__}",
            {"id": 2, "label": "y"},
            valid_from=_FEB,
            tx_start=_T1,
        )

    with pytest.raises(ExecutionFailure):
        _db(profile_run, _TA).transact(fn)
    assert _rows(profile_run, entity) == [
        (1, _T0, None, _JAN, _JUN, 100, "a"),
        (1, _T1, None, _JUN, None, 200, "b"),
        _UNTOUCHED,
    ]
