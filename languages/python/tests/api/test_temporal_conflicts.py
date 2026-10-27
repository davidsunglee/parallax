"""Closes the attempt's Transaction Instant cannot follow, against real Postgres.

A close ends a stored row at the attempt's instant, so the instant must be
strictly later than the row's stored Transaction-Time start (`m-unit-work`
*Closes the instant cannot follow*). A clock repeating an instant, a clock
behind another writer's, and an instant one attempt captured before another
transaction committed a later version all reach a refused close: a
``TemporalConflictError`` whose attempt rolls back, storing nothing, and whose
retry is a new attempt at a fresh instant.

Each proof drives the public Typed and Wire verbs under both storage layouts and
both concurrency strategies and reads back every stored row. Every ``Database``
connects with a scripted clock, so every instant is known in advance.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any, Final, Literal

import pytest

from parallax.conformance.scripted_clock import FixedClock, ScriptedClock
from parallax.core import Attr, Bitemporal, Document, DomainModel, TxTemporal, attr
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import RollbackOnlyError, TemporalConflictError
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.root_ownership import own_root
from tests.api._peer_commit import commit_as_a_peer

_NAMESPACE: Final = "temporal.conflict"


class ColumnsLog(TxTemporal, table="tc_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class DocumentLog(TxTemporal, table="tc_document_log", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class ColumnsSpan(Bitemporal, table="tc_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


class DocumentSpan(Bitemporal, table="tc_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


_MODEL: Final = DomainModel(ColumnsLog, DocumentLog, ColumnsSpan, DocumentSpan)
_TABLES: Final[dict[type[Any], str]] = {
    ColumnsLog: "tc_columns_log",
    DocumentLog: "tc_document_log",
    ColumnsSpan: "tc_columns_span",
    DocumentSpan: "tc_document_span",
}
_LOGS: Final = (ColumnsLog, DocumentLog)
_SPANS: Final = (ColumnsSpan, DocumentSpan)

_JAN, _MAR, _APR, _MAY, _JUN = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 4, 5, 6)
)
_SEEDED: Final = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]

_REPRESENTATIONS: tuple[_Representation, ...] = ("typed", "wire")
_CONCURRENCIES: tuple[_Concurrency, ...] = ("optimistic", "locking")


def _identity(entity: type[Any]) -> EntityIdentity:
    return EntityIdentity(_NAMESPACE, entity.__name__)


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _member(entity: type[Any], name: str) -> str:
    return f"payload->>'{name}'" if entity in (DocumentLog, DocumentSpan) else name


def _db(profile_run: Any, instants: Sequence[dt.datetime]) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock(list(instants)))
    ).using_database_login()


def _seeded_db(
    profile_run: Any, entity: type[Any], instants: Sequence[dt.datetime]
) -> ScopedDatabase:
    """A database whose first attempt stores object 1 of ``entity`` — a log
    labelled ``seeded``, or a span over ``[January, ∞)`` at 100 — at the
    clock's first instant; the later instants answer later attempts."""
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, instants)
    if entity in _LOGS:
        db.transact(lambda tx: tx.insert(entity(id=1, label="seeded")))
    else:
        db.transact(lambda tx: tx.insert(entity(id=1, amount=100), valid_from=_JAN))
    return db


def _log_rows(profile_run: Any, entity: type[Any], key: int = 1) -> list[tuple[object, ...]]:
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{_member(entity, 'label')} from {_TABLES[entity]} where id = %s order by in_z, out_z"
    )
    return [tuple(row) for row in profile_run.port.execute(sql, [key])]


def _span_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        "case when thru_z = 'infinity' then null else thru_z end, "
        f"({_member(entity, 'amount')})::int from {_TABLES[entity]} order by in_z, out_z, from_z"
    )
    return [tuple(row) for row in profile_run.port.execute(sql, [])]


def _find(tx: TxnContext, entity: type[Any], representation: _Representation) -> Any:
    if representation == "typed":
        query = entity.where(entity.id == 1)
        return tx.find(query if entity in _LOGS else query.as_of(valid_time=_MAR)).result()
    name = _name(entity)
    temporal: dict[str, object] = {"transaction-time": {"asOf": "latest"}}
    if entity in _SPANS:
        temporal["valid-time"] = {"asOf": f"{_MAR:%Y-%m-%dT%H:%M:%S.%fZ}"}
    return tx.wire.find(
        {
            "target": name,
            "predicate": {"eq": {"path": f"{name}.id", "value": 1}},
            "temporal": temporal,
        }
    ).result()


def _amend(tx: TxnContext, observed: Any, representation: _Representation, label: str) -> None:
    if representation == "typed":
        tx.amend(observed.edit(label=label))
    else:
        tx.wire.amend(observed, {"label": label})


def _terminate(tx: TxnContext, observed: Any, representation: _Representation) -> None:
    if representation == "typed":
        tx.terminate(observed)
    else:
        tx.wire.terminate(observed)


def _amend_until(tx: TxnContext, observed: Any, representation: _Representation) -> None:
    # A bounded window inside the stored rectangle: a head, a middle, and a tail.
    if representation == "typed":
        tx.amend(observed.edit(amount=150), until=_MAY)
    else:
        tx.wire.amend(observed, {"amount": 150}, until=_MAY)


def _refused(failure: pytest.ExceptionInfo[ExecutionFailure]) -> TemporalConflictError:
    cause = failure.value.cause
    assert isinstance(cause, TemporalConflictError)
    return cause


# --------------------------------------------------------------------------- #
# A clock at or behind a stored start refuses the close.                       #
# --------------------------------------------------------------------------- #
_AT_OR_BEHIND: Final = pytest.mark.parametrize(
    "instant", [_SEEDED, _SEEDED - dt.timedelta(days=1)], ids=["equal", "behind"]
)


@_AT_OR_BEHIND
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _LOGS)
@pytest.mark.parametrize("mutation", ["amend", "terminate"])
def test_a_transaction_time_close_at_or_before_its_stored_start_is_refused(
    profile_run: Any,
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
    mutation: str,
    instant: dt.datetime,
) -> None:
    db = _seeded_db(profile_run, entity, [_SEEDED, instant])

    def change(tx: TxnContext) -> None:
        observed = _find(tx, entity, representation)
        if mutation == "amend":
            _amend(tx, observed, representation, "first")
        else:
            _terminate(tx, observed, representation)

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(change, concurrency=concurrency, max_retries=0)
    refusal = _refused(failed)
    assert refusal.entity == _identity(entity)
    assert (refusal.instant, refusal.stored_bound) == (instant, _SEEDED)
    assert refusal.key == {"id": 1}
    assert _log_rows(profile_run, entity) == [(_SEEDED, None, "seeded")]


@_AT_OR_BEHIND
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _SPANS)
def test_a_bounded_bitemporal_amendment_behind_its_stored_start_opens_no_piece(
    profile_run: Any,
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
    instant: dt.datetime,
) -> None:
    db = _seeded_db(profile_run, entity, [_SEEDED, instant])

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(
            lambda tx: _amend_until(tx, _find(tx, entity, representation), representation),
            concurrency=concurrency,
            max_retries=0,
        )
    assert _refused(failed).stored_bound == _SEEDED
    assert _span_rows(profile_run, entity) == [(_SEEDED, None, _JAN, None, 100)]


# --------------------------------------------------------------------------- #
# Retry: a new attempt at a fresh instant.                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _SPANS)
def test_a_refused_close_is_retried_at_the_clocks_next_instant(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    db = _seeded_db(profile_run, entity, [_SEEDED, _SEEDED, _JUN])
    attempts: list[None] = []

    def change(tx: TxnContext) -> None:
        attempts.append(None)
        _amend_until(tx, _find(tx, entity, representation), representation)

    db.transact(change, concurrency=concurrency)

    assert len(attempts) == 2
    assert _span_rows(profile_run, entity) == [
        (_SEEDED, _JUN, _JAN, None, 100),
        (_JUN, None, _JAN, _MAR, 100),
        (_JUN, None, _MAR, _MAY, 150),
        (_JUN, None, _MAY, None, 100),
    ]


@pytest.mark.parametrize("entity", _LOGS)
def test_a_clock_that_stays_behind_exhausts_the_bound_with_the_conflict_as_cause(
    profile_run: Any, entity: type[Any]
) -> None:
    db = _seeded_db(profile_run, entity, [_SEEDED] * 4)
    attempts: list[None] = []

    def change(tx: TxnContext) -> None:
        attempts.append(None)
        _amend(tx, _find(tx, entity, "typed"), "typed", "first")

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(change, max_retries=2)
    assert len(attempts) == 3
    assert _refused(failed).__notes__ == ["bounded retry exhausted after 3 attempts (retries=2)"]
    assert _log_rows(profile_run, entity) == [(_SEEDED, None, "seeded")]


# --------------------------------------------------------------------------- #
# A caught refusal never lets the attempt commit.                              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("entity", _LOGS)
def test_a_caught_refusal_of_a_held_row_still_fails_the_attempt(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    # The refused write planned against the row its read holds stays buffered,
    # so the commit refuses it again rather than committing anything.
    db = _seeded_db(profile_run, entity, [_SEEDED, _SEEDED])
    caught: list[TemporalConflictError] = []

    def change(tx: TxnContext) -> str:
        _amend(tx, _find(tx, entity, "typed"), "typed", "first")
        tx.insert(entity(id=2, label="other"))
        try:
            _find(tx, entity, "typed")
        except TemporalConflictError as refusal:
            caught.append(refusal)
        return "withheld"

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(change, concurrency=concurrency, max_retries=0)
    assert len(caught) == 1
    assert _refused(failed).stored_bound == _SEEDED
    assert _log_rows(profile_run, entity) == [(_SEEDED, None, "seeded")]
    assert _log_rows(profile_run, entity, key=2) == []


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _LOGS)
def test_a_caught_refusal_bound_inside_the_flush_dooms_the_attempt_and_is_retried(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    # The target write's current row is read inside the flush a later read
    # forces, so its refusal is an execution failure: the attempt is doomed,
    # the next read refuses with it as the cause, and the retry succeeds.
    db = _seeded_db(profile_run, entity, [_SEEDED, _SEEDED, _JUN])
    observed: list[BaseException] = []

    def change(tx: TxnContext) -> None:
        if representation == "typed":
            tx.amend_if(entity, entity.label.set("first"), key=1, tx_start=_SEEDED)
        else:
            tx.wire.amend_if(_name(entity), {"id": 1, "label": "first"}, tx_start=_SEEDED)
        for _ in range(2):
            try:
                _find(tx, entity, representation)
            except (TemporalConflictError, RollbackOnlyError) as failure:
                observed.append(failure)

    db.transact(change, concurrency="optimistic")

    refusal, doomed, *retried = observed
    assert isinstance(refusal, TemporalConflictError)
    assert isinstance(doomed, RollbackOnlyError)
    assert doomed.__cause__ is refusal
    assert retried == []
    assert _log_rows(profile_run, entity) == [(_SEEDED, _JUN, "seeded"), (_JUN, None, "first")]


# --------------------------------------------------------------------------- #
# An instant captured before another transaction commits a later version.     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", _CONCURRENCIES)
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
@pytest.mark.parametrize("entity", _LOGS)
def test_an_instant_captured_before_a_peer_commits_a_later_version_is_retried(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    # A's first flush captures March. B then commits April's version, which
    # A's Read Committed read returns; closing it at March would invert it.
    profile_run.reset(model_of(_MODEL), {})
    _db(profile_run, [_JAN]).transact(lambda tx: tx.insert(entity(id=1, label="seeded")))
    peer = own_root(
        connect(profile_run.port, _MODEL, clock=FixedClock(_APR))
    ).using_database_login()
    attempts: list[None] = []

    def change(tx: TxnContext) -> None:
        attempts.append(None)
        tx.insert(entity(id=2, label="unrelated"))
        if len(attempts) == 1:
            tx.find(entity.where(entity.id == 2)).result()
            commit_as_a_peer(
                lambda: peer.transact(
                    lambda peer_tx: peer_tx.amend(
                        peer_tx.find(entity.where(entity.id == 1)).result().edit(label="peer")
                    )
                )
            )
        _amend(tx, _find(tx, entity, representation), representation, "ours")

    _db(profile_run, [_MAR, _JUN]).transact(
        change, concurrency=concurrency, isolation="read_committed"
    )

    assert len(attempts) == 2
    assert _log_rows(profile_run, entity) == [
        (_JAN, _APR, "seeded"),
        (_APR, _JUN, "peer"),
        (_JUN, None, "ours"),
    ]
    assert _log_rows(profile_run, entity, key=2) == [(_JUN, None, "unrelated")]
