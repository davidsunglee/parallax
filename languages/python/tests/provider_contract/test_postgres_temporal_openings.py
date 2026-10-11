"""Grouped temporal openings against a real server (`m-execution` *Flush
execution*, `m-sql` *Requested ranges*).

Each proof runs the same public writes twice: once as execution realizes them,
grouping the openings, and once with the internal entry cap at one, so each
opening runs as the singleton statement it lowers to alone. What a scripted
port cannot establish is here: that PostgreSQL stores from one multi-row
statement exactly the history the singleton statements store, collections of
every shape included, and that a grouped statement fails as a whole with its
own native diagnostic — which can differ from the error the earliest failing
opening raises alone — while the attempt still rolls back, refuses further
work, and reports that diagnostic's own retry verdict.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import Attr, Bitemporal, Document, DomainModel, Entity, ValueObject, attr
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure, _write_lowering
from parallax.core.execution_lifecycle import (
    AttemptRolledBack,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallStarted,
    ExecutionEvent,
    TransactionAttemptFinished,
)
from parallax.core.unit_work import RollbackOnlyError
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root

_NAMESPACE = "temporal.openings"


class Leg(ValueObject):
    stops: Attr[tuple[str, ...]] = attr()


class ColumnsSpan(Bitemporal, table="opn_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    account: Attr[str] = attr(max_length=16)
    amount: Attr[int]
    tags: Attr[tuple[str, ...]] = attr()
    legs: Attr[tuple[Leg, ...]] = attr()


class DocumentSpan(Bitemporal, table="opn_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    account: Attr[str] = attr(max_length=16)
    amount: Attr[int]
    tags: Attr[tuple[str, ...]] = attr()
    legs: Attr[tuple[Leg, ...]] = attr()


class Account(Entity, table="opn_account", namespace=_NAMESPACE):
    code: Attr[str] = attr(primary_key=True, max_length=16)


_MODEL = DomainModel(ColumnsSpan, DocumentSpan, Account)
_TABLES: dict[type[Any], str] = {
    ColumnsSpan: "opn_columns_span",
    DocumentSpan: "opn_document_span",
}

type _Concurrency = Literal["optimistic", "locking"]
type _Row = tuple[object, ...]

_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_TA = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_JAN, _FEB, _AUG, _SEP = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 8, 9))

_TAGS = ("a", "a", *(f"t{index}" for index in range(300)))
_LEGS = (Leg(stops=()), Leg(stops=("x", "x")), *(Leg(stops=("s",) * 40) for _ in range(20)))


@dataclass(frozen=True, slots=True)
class _Realized:
    """One amendment's stored history and the DML its attempt ran."""

    rows: list[_Row]
    writes: list[str]


def _database(profile_run: Any, provider: RecordingLifecycleProvider) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(
        connect(
            profile_run.port,
            _MODEL,
            clock=ScriptedClock([_T0, _TA]),
            lifecycle_provider=provider,
        )
    ).using_database_login()


def _seed(db: ScopedDatabase, entity: type[Any], tags: tuple[str, ...]) -> None:
    def seed(tx: Transaction) -> None:
        tx.insert(entity(id=1, account="A-1", amount=100, tags=tags, legs=_LEGS), valid_from=_JAN)
        tx.insert(Account(code="B-2"))

    db.transact(seed)


def _find(tx: Transaction, entity: type[Any]) -> Any:
    return tx.find(entity.where(entity.id == 1).as_of(valid_time=_FEB)).result()


def _amend(tx: Transaction, entity: type[Any]) -> None:
    """Amend span 1 from February until September: one close, then a head, a
    changed middle, and a tail."""
    tx.amend(_find(tx, entity).edit(amount=150), until=_SEP)


def _rows(profile_run: Any, entity: type[Any]) -> list[_Row]:
    return [
        tuple(row)
        for row in profile_run.port.execute(
            f"select * from {_TABLES[entity]} order by in_z, out_z, from_z", []
        )
    ]


def _events(provider: RecordingLifecycleProvider) -> list[ExecutionEvent]:
    """The last Root Execution's events: the amendment's."""
    return list(provider.roots[-1].events)


def _writes(events: list[ExecutionEvent]) -> list[str]:
    return [
        event.statement.sql
        for event in events
        if isinstance(event, DatabaseCallStarted) and event.kind == "write"
    ]


def _singletons(patched: pytest.MonkeyPatch) -> None:
    """Cap each grouped opening at one entry, so every opening runs alone."""
    patched.setattr(_write_lowering, "_OPENING_ENTRY_CAP", 1)


def _realized(
    profile_run: Any,
    monkeypatch: pytest.MonkeyPatch,
    entity: type[Any],
    concurrency: _Concurrency,
    *,
    grouped: bool,
) -> _Realized:
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider)
    _seed(db, entity, _TAGS)
    with monkeypatch.context() as patched:
        if not grouped:
            _singletons(patched)
        db.transact(lambda tx: _amend(tx, entity), concurrency=concurrency)
    return _Realized(_rows(profile_run, entity), _writes(_events(provider)))


@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan], ids=["columns", "document"])
@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_one_grouped_statement_stores_the_history_each_opening_alone_stores(
    profile_run: Any,
    monkeypatch: pytest.MonkeyPatch,
    entity: type[Any],
    concurrency: _Concurrency,
) -> None:
    raw = _realized(profile_run, monkeypatch, entity, concurrency, grouped=False)
    grouped = _realized(profile_run, monkeypatch, entity, concurrency, grouped=True)
    assert grouped.rows == raw.rows
    assert len(raw.rows) == 4
    close, *openings = raw.writes
    assert len(openings) == 3
    assert all(opening == openings[0] for opening in openings)
    single = openings[0]
    values = single.split(" values ")[1]
    assert grouped.writes == [close, f"{single}, {values}, {values}"]


def _conflicting_amendment(
    profile_run: Any, entity: type[Any], then: Callable[[Transaction], None]
) -> Callable[[Transaction], None]:
    """Amend span 1 after another session committed a row holding the key the
    changed middle opens, once an account constraint no opening satisfies is in
    force: the head violates that constraint, which is checked as its
    statement ends, and the middle violates the key, which is checked as its
    row is inserted."""
    control = profile_run.control()
    try:
        control.execute_write(
            f"alter table {_TABLES[entity]} add constraint opn_span_account "
            "foreign key (account) references opn_account (code) not valid",
            [],
        )
    finally:
        control.close()

    def edit(tx: Transaction) -> None:
        source = _find(tx, entity)
        other = profile_run.control()
        try:
            other.execute_write(
                f"insert into {_TABLES[entity]} (id, account, amount, tags, legs, "
                "from_z, thru_z, in_z, out_z) values (1, 'B-2', 7, '[]', '[]', "
                f"'{_AUG.isoformat()}', '{_SEP.isoformat()}', '{_TA.isoformat()}', 'infinity')",
                [],
            )
        finally:
            other.close()
        tx.amend(source.edit(amount=150), until=_SEP)
        then(tx)

    return edit


@dataclass(frozen=True, slots=True)
class _Failed:
    """What one failed amendment raised, what its attempt reported, and what it
    left stored."""

    cause: BaseException
    attempts: list[TransactionAttemptFinished]
    failed: list[DatabaseCallFinished]
    writes: list[str]
    rows: list[_Row]


def _failed(
    profile_run: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    grouped: bool,
    then: Callable[[Transaction], None] = lambda tx: None,
) -> _Failed:
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider)
    _seed(db, ColumnsSpan, ())
    before = _rows(profile_run, ColumnsSpan)
    edit = _conflicting_amendment(profile_run, ColumnsSpan, then)
    with monkeypatch.context() as patched:
        if not grouped:
            _singletons(patched)
        with pytest.raises(ExecutionFailure) as escaped:
            db.transact(edit, max_retries=2)
    events = _events(provider)
    rows = _rows(profile_run, ColumnsSpan)
    assert len(rows) == len(before) + 1
    assert all(row in rows for row in before)
    return _Failed(
        escaped.value.cause,
        [event for event in events if isinstance(event, TransactionAttemptFinished)],
        [
            event
            for event in events
            if isinstance(event, DatabaseCallFinished)
            and isinstance(event.outcome, DatabaseCallFailed)
        ],
        _writes(events),
        rows,
    )


def _diagnostic(failed: _Failed) -> tuple[object, object]:
    (call,) = failed.failed
    assert isinstance(call.outcome, DatabaseCallFailed)
    return call.outcome.diagnostic.category, call.outcome.diagnostic.native_code


def test_a_grouped_statement_fails_whole_with_its_own_diagnostic_and_retry_verdict(
    profile_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _failed(profile_run, monkeypatch, grouped=False)
    grouped = _failed(profile_run, monkeypatch, grouped=True)

    # Alone, the head fails first, on the account constraint its statement
    # checks as it ends.
    assert isinstance(raw.cause, DatabaseError)
    assert (raw.cause.category, raw.cause.native_code) == (None, "23503")
    assert _diagnostic(raw) == (None, "23503")
    assert len(raw.writes) == 2
    # Grouped, the one statement fails as a whole on the middle's key, which is
    # checked as its row is inserted, before the head's constraint is checked.
    assert isinstance(grouped.cause, DatabaseError)
    assert (grouped.cause.category, grouped.cause.native_code) == ("uniqueViolation", "23505")
    assert grouped.cause.violated_index is not None
    assert _diagnostic(grouped) == ("uniqueViolation", "23505")
    assert len(grouped.writes) == 2
    assert grouped.writes[1].count("), (") == 2
    for failed in (raw, grouped):
        (finished,) = failed.attempts
        assert isinstance(finished.outcome, AttemptRolledBack)
        assert finished.outcome.failure.retry_eligible is False
    assert grouped.rows == raw.rows


def test_a_grouped_statements_failure_leaves_the_attempt_rollback_only(
    profile_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcomes: list[BaseException] = []

    def then(tx: Transaction) -> None:
        # The read forces the flush; its failure is swallowed, and the attempt
        # refuses every later operation because of it.
        for _ in range(2):
            try:
                _find(tx, ColumnsSpan)
            except Exception as failure:
                outcomes.append(failure)

    failed = _failed(profile_run, monkeypatch, grouped=True, then=then)
    flush_failure, refused = outcomes
    assert isinstance(flush_failure, DatabaseError)
    assert flush_failure.category == "uniqueViolation"
    assert isinstance(refused, RollbackOnlyError)
    assert refused.__cause__ is flush_failure
    assert isinstance(failed.cause, RollbackOnlyError)
    (finished,) = failed.attempts
    assert isinstance(finished.outcome, AttemptRolledBack)
