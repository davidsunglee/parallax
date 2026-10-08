"""Temporal writes that leave a milestone as it was, against real Postgres."""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Literal

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import Attr, Bitemporal, Document, DomainModel, TxTemporal, ValueObject, attr
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.unit_work import OptimisticLockConflictError, WriteEvidenceError
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root
from tests.api._coverage_interleaving import AfterCoverageRead

_NAMESPACE = "temporal.unchanged"


class Spec(ValueObject):
    title: Attr[str | None]


class Mark(ValueObject):
    code: Attr[str | None]


class ColumnsSpan(Bitemporal, table="umw_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]


class DocumentSpan(Bitemporal, table="umw_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]


class ColumnsLog(TxTemporal, table="umw_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    spec: Attr[Spec | None]


class DocumentLog(TxTemporal, table="umw_document_log", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    spec: Attr[Spec | None]


_MODEL = DomainModel(ColumnsSpan, DocumentSpan, ColumnsLog, DocumentLog)
_TABLES: dict[type[Any], str] = {
    ColumnsSpan: "umw_columns_span",
    DocumentSpan: "umw_document_span",
    ColumnsLog: "umw_columns_log",
    DocumentLog: "umw_document_log",
}
_DOCUMENTS = (DocumentSpan, DocumentLog)

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]
type _Row = tuple[object, ...]

_SPAN_AXES = pytest.mark.parametrize(
    "entity", [ColumnsSpan, DocumentSpan], ids=["columns", "document"]
)
_LOG_AXES = pytest.mark.parametrize(
    "entity", [ColumnsLog, DocumentLog], ids=["columns", "document"]
)
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])

_S1 = dt.datetime(2023, 11, 1, tzinfo=dt.UTC)
_S2 = dt.datetime(2023, 11, 15, tzinfo=dt.UTC)
_S3 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_TP = dt.datetime(2024, 1, 5, tzinfo=dt.UTC)
_TA = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_TB = dt.datetime(2024, 1, 20, tzinfo=dt.UTC)
_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _JUL, _AUG, _OCT, _DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 2, 3, 4, 5, 6, 7, 8, 10, 12)
)
_SPEC = {"title": "s"}


def _db(profile_run: Any, *instants: dt.datetime, **options: Any) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock(list(instants)), **options)
    ).using_database_login()


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _member(entity: type[Any], member: str) -> str:
    return f"payload->'{member}'" if entity in _DOCUMENTS else member


def _plain(row: _Row) -> _Row:
    return tuple(int(cell) if isinstance(cell, float) else cell for cell in row)


def _span_rows(profile_run: Any, entity: type[Any]) -> list[_Row]:
    members = ", ".join(_member(entity, name) for name in ("amount", "label", "spec", "marks"))
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        f"case when thru_z = 'infinity' then null else thru_z end, {members} "
        f"from {_TABLES[entity]} order by from_z, in_z"
    )
    return [_plain(row) for row in profile_run.port.execute(sql, [])]


def _log_rows(profile_run: Any, entity: type[Any]) -> list[_Row]:
    members = ", ".join(_member(entity, name) for name in ("amount", "spec"))
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{members} from {_TABLES[entity]} order by in_z"
    )
    return [_plain(row) for row in profile_run.port.execute(sql, [])]


def _log_find(tx: Transaction, entity: type[Any], representation: _Representation) -> Any:
    if representation == "typed":
        return tx.find(entity.where(entity.id == 1)).result()
    name = _name(entity)
    return tx.wire.find(
        {
            "target": name,
            "predicate": {"eq": {"attr": f"{name}.id", "value": 1}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        }
    ).result()


def _span_find(
    tx: Transaction, entity: type[Any], representation: _Representation, at: dt.datetime
) -> Any:
    if representation == "typed":
        return tx.find(entity.where(entity.id == 1).as_of(valid_time=at)).result()
    name = _name(entity)
    return tx.wire.find(
        {
            "target": name,
            "predicate": {"eq": {"attr": f"{name}.id", "value": 1}},
            "temporal": {
                "transaction-time": {"asOf": "latest"},
                "valid-time": {"asOf": f"{at:%Y-%m-%dT%H:%M:%S.%fZ}"},
            },
        }
    ).result()


def _typed(changes: dict[str, object]) -> dict[str, object]:
    """``changes`` as the values a Typed edit takes."""
    typed: dict[str, object] = {}
    for name, value in changes.items():
        if name == "spec":
            typed[name] = None if value is None else Spec(**value)  # type: ignore[arg-type]
        elif name == "marks":
            typed[name] = tuple(Mark(**mark) for mark in value)  # type: ignore[union-attr]
        else:
            typed[name] = value
    return typed


def _update(
    tx: Transaction,
    observed: Any,
    representation: _Representation,
    changes: dict[str, object],
    *,
    until: dt.datetime | None = None,
) -> None:
    bounded = {} if until is None else {"until": until}
    if representation == "typed":
        tx.amend(observed.edit(**_typed(changes)), **bounded)
    else:
        tx.wire.amend(observed, changes, **bounded)


def _seed_log(profile_run: Any, entity: type[Any]) -> None:
    profile_run.reset(model_of(_MODEL), {})
    _db(profile_run, _S1).transact(
        lambda tx: tx.insert(entity(id=1, amount=100, spec=Spec(title="s")))
    )


# --------------------------------------------------------------------------- #
# Transaction-Time-Only: one row, kept.                                        #
# --------------------------------------------------------------------------- #
@_STRATEGIES
@_REPRESENTATIONS
@_LOG_AXES
def test_an_update_restating_a_transaction_time_row_keeps_its_milestone(
    profile_run: Any, entity: type[Any], representation: _Representation, concurrency: _Concurrency
) -> None:
    _seed_log(profile_run, entity)

    def fn(tx: Transaction) -> None:
        source = _log_find(tx, entity, representation)
        _update(tx, source, representation, {"amount": 100, "spec": _SPEC})
        fresh = _log_find(tx, entity, representation)
        # Completion spent the source; a fresh read of the kept row writes again.
        with pytest.raises(WriteEvidenceError) as spent:
            _update(tx, source, representation, {"amount": 100})
        assert spent.value.code == "write-evidence-consumed"
        _update(tx, fresh, representation, {"amount": 100})

    _db(profile_run, _TA).transact(fn, concurrency=concurrency)
    assert _log_rows(profile_run, entity) == [(_S1, None, 100, _SPEC)]


@_LOG_AXES
def test_a_changed_transaction_time_row_is_still_closed_and_chained(
    profile_run: Any, entity: type[Any]
) -> None:
    _seed_log(profile_run, entity)
    _db(profile_run, _TA).transact(
        lambda tx: _update(tx, _log_find(tx, entity, "typed"), "typed", {"amount": 150})
    )
    assert _log_rows(profile_run, entity) == [(_S1, _TA, 100, _SPEC), (_TA, None, 150, _SPEC)]


# --------------------------------------------------------------------------- #
# A range over three rectangles with a gap: [Jan, Apr) | gap | [May, Aug) |    #
# [Aug, Dec), each its own label; amount 100 is assigned over [Mar, Oct).      #
# --------------------------------------------------------------------------- #
_AMOUNTS = {"mixed": (100, 180, 100), "all-equal": (100, 100, 100), "all-changed": (110, 180, 130)}


def _seed_spans(profile_run: Any, entity: type[Any], amounts: tuple[int, int, int]) -> None:
    profile_run.reset(model_of(_MODEL), {})
    windows = ((_JAN, _APR, "a"), (_MAY, _AUG, "b"), (_AUG, _DEC, "c"))
    for instant, amount, (start, end, label) in zip((_S1, _S2, _S3), amounts, windows, strict=True):
        _db(profile_run, instant).transact(
            lambda tx, amount=amount, start=start, end=end, label=label: tx.insert(
                entity(id=1, amount=amount, label=label, spec=None, marks=()),
                valid_from=start,
                until=end,
            )
        )


def _expected(variant: str) -> list[_Row]:
    a, b, c = _AMOUNTS[variant]

    def row(
        in_z: dt.datetime, out_z: object, start: object, end: object, amount: int, label: str
    ) -> _Row:
        return (in_z, out_z, start, end, amount, label, None, [])

    if variant == "all-equal":
        return [
            row(_S1, None, _JAN, _APR, a, "a"),
            row(_S2, None, _MAY, _AUG, b, "b"),
            row(_S3, None, _AUG, _DEC, c, "c"),
        ]
    if variant == "mixed":
        return [
            row(_S1, None, _JAN, _APR, a, "a"),
            row(_S2, _TA, _MAY, _AUG, b, "b"),
            row(_TA, None, _MAY, _AUG, 100, "b"),
            row(_S3, None, _AUG, _DEC, c, "c"),
        ]
    return [
        row(_S1, _TA, _JAN, _APR, a, "a"),
        row(_TA, None, _JAN, _MAR, a, "a"),
        row(_TA, None, _MAR, _APR, 100, "a"),
        row(_S2, _TA, _MAY, _AUG, b, "b"),
        row(_TA, None, _MAY, _AUG, 100, "b"),
        row(_S3, _TA, _AUG, _DEC, c, "c"),
        row(_TA, None, _AUG, _OCT, 100, "c"),
        row(_TA, None, _OCT, _DEC, c, "c"),
    ]


@_STRATEGIES
@_REPRESENTATIONS
@pytest.mark.parametrize("variant", list(_AMOUNTS))
@_SPAN_AXES
def test_a_range_keeps_each_rectangle_it_leaves_unchanged(
    profile_run: Any,
    entity: type[Any],
    variant: str,
    representation: _Representation,
    concurrency: _Concurrency,
) -> None:
    _seed_spans(profile_run, entity, _AMOUNTS[variant])

    def fn(tx: Transaction) -> None:
        source = _span_find(tx, entity, representation, _MAR)
        _update(tx, source, representation, {"amount": 100}, until=_OCT)

    _db(profile_run, _TA).transact(fn, concurrency=concurrency)
    assert _span_rows(profile_run, entity) == _expected(variant)


@_REPRESENTATIONS
@_SPAN_AXES
def test_a_composition_that_ends_where_it_started_keeps_its_milestone(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    _seed_spans(profile_run, entity, _AMOUNTS["all-equal"])

    def fn(tx: Transaction) -> None:
        source = _span_find(tx, entity, representation, _FEB)
        _update(tx, source, representation, {"amount": 150}, until=_MAR)
        _update(tx, source, representation, {"amount": 100}, until=_MAR)

    _db(profile_run, _TA).transact(fn)
    assert _span_rows(profile_run, entity) == _expected("all-equal")


_STRUCTURED: dict[str, tuple[dict[str, object], bool]] = {
    "equal-whole-occurrence": ({"spec": {"title": "s"}}, True),
    "equal-many": ({"marks": [{"code": "m"}]}, True),
    "null-over-a-stored-null": ({"label": None}, True),
    "another-nested-value": ({"spec": {"title": "t"}}, False),
    "null-over-an-occurrence": ({"spec": None}, False),
    "a-shorter-many": ({"marks": []}, False),
}


@pytest.mark.parametrize("case", list(_STRUCTURED))
@_REPRESENTATIONS
@_SPAN_AXES
def test_nullable_and_structured_assignments_compare_their_whole_values(
    profile_run: Any, entity: type[Any], representation: _Representation, case: str
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    _db(profile_run, _S1).transact(
        lambda tx: tx.insert(
            entity(id=1, amount=100, label=None, spec=Spec(title="s"), marks=(Mark(code="m"),)),
            valid_from=_JAN,
        )
    )
    changes, kept = _STRUCTURED[case]

    def fn(tx: Transaction) -> None:
        _update(
            tx, _span_find(tx, entity, representation, _MAR), representation, changes, until=_JUN
        )

    _db(profile_run, _TA).transact(fn)
    rows = _span_rows(profile_run, entity)
    seeded: _Row = (_S1, None, _JAN, None, 100, None, _SPEC, [{"code": "m"}])
    if kept:
        assert rows == [seeded]
    else:
        assert len(rows) == 4
        assert rows[0][:2] == (_S1, _TA)


# --------------------------------------------------------------------------- #
# Rows the attempt opened, and an insertion's own source.                      #
# --------------------------------------------------------------------------- #
@_REPRESENTATIONS
@_SPAN_AXES
def test_an_unchanged_rectangle_the_attempt_opened_is_neither_split_nor_revised(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    profile_run.reset(model_of(_MODEL), {})

    def fn(tx: Transaction) -> None:
        inserted = entity(id=1, amount=100, label="a", spec=None, marks=())
        tx.insert(inserted, valid_from=_JAN)
        _update(tx, _span_find(tx, entity, representation, _MAR), representation, {"amount": 100})
        tx.find(entity.where(entity.id == 1).as_of(valid_time=_MAR)).result()
        tx.amend(inserted.edit(amount=100), until=_JUN)

    _db(profile_run, _TA).transact(fn)
    assert _span_rows(profile_run, entity) == [(_TA, None, _JAN, None, 100, "a", None, [])]


# --------------------------------------------------------------------------- #
# Two sessions.                                                                #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("retried", [False, True], ids=["conflict", "retried"])
@_LOG_AXES
def test_a_peer_revision_to_equal_values_after_the_read_still_conflicts(
    profile_run: Any, entity: type[Any], retried: bool
) -> None:
    _seed_log(profile_run, entity)
    peer = _db(profile_run, _TP)
    attempts = 0

    def revise() -> None:
        # The peer changes the row and restores its value in one transaction, so
        # a new milestone holds values equal to the one this attempt read.
        def restore(peer_tx: Transaction) -> None:
            _update(peer_tx, _log_find(peer_tx, entity, "typed"), "typed", {"amount": 120})
            _update(peer_tx, _log_find(peer_tx, entity, "typed"), "typed", {"amount": 100})

        peer.transact(restore)

    def fn(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        source = _log_find(tx, entity, "typed")
        if attempts == 1:
            other = threading.Thread(target=revise)
            other.start()
            other.join(timeout=10.0)
        _update(tx, source, "typed", {"amount": 100})

    ours = _db(profile_run, _TA, _TB)
    peer_rows = [(_S1, _TP, 100, _SPEC), (_TP, None, 100, _SPEC)]
    if not retried:
        with pytest.raises(ExecutionFailure) as failed:
            ours.transact(fn)
        assert isinstance(failed.value.cause, OptimisticLockConflictError)
    else:
        ours.transact(fn, retry_optimistic_conflicts=True)
        assert attempts == 2
    # The retry's guard matched the peer's milestone and kept it.
    assert _log_rows(profile_run, entity) == peer_rows


@pytest.mark.parametrize(("amount", "kept"), [(100, True), (120, False)], ids=["kept", "rewritten"])
@_LOG_AXES
def test_a_guard_holds_its_lock_until_commit_and_leaves_a_peers_token_standing(
    profile_run: Any, entity: type[Any], amount: int, kept: bool
) -> None:
    _seed_log(profile_run, entity)
    peer = _db(profile_run, _TP)
    control = profile_run.control()
    peer_failures: list[BaseException] = []

    def peer_write() -> None:
        try:
            peer.transact(
                lambda peer_tx: _update(
                    peer_tx, _log_find(peer_tx, entity, "typed"), "typed", {"amount": 150}
                )
            )
        except BaseException as failure:
            peer_failures.append(failure)

    def waiting() -> bool:
        ((count,),) = control.execute("select count(*) from pg_locks where not granted", [])
        return bool(count)

    thread = threading.Thread(target=peer_write)

    def fn(tx: Transaction) -> None:
        _update(tx, _log_find(tx, entity, "typed"), "typed", {"amount": amount})
        # A dependent read runs the guard now; the callback goes on afterwards.
        _log_find(tx, entity, "typed")
        thread.start()
        deadline = time.monotonic() + 10.0
        while not waiting():
            assert time.monotonic() < deadline, "the peer never waited on the row"
            time.sleep(0.05)

    try:
        _db(profile_run, _TA).transact(fn)
        thread.join(timeout=10.0)
    finally:
        control.close()
    if kept:
        # The milestone the peer read is still current, so its gated close matches.
        assert peer_failures == []
        assert _log_rows(profile_run, entity) == [(_S1, _TP, 100, _SPEC), (_TP, None, 150, _SPEC)]
    else:
        (failure,) = peer_failures
        assert isinstance(failure, ExecutionFailure)
        assert isinstance(failure.cause, OptimisticLockConflictError)
        assert _log_rows(profile_run, entity) == [(_S1, _TA, 100, _SPEC), (_TA, None, 120, _SPEC)]


_LOST = {
    # The peer revises the first rectangle, which the range keeps.
    "a-kept-rectangle": (_FEB, _MAR, 100, _S1),
    # The peer revises the middle rectangle, which the range rewrites.
    "a-rewritten-rectangle": (_JUN, _JUL, 180, _S2),
}


@pytest.mark.parametrize("lost", list(_LOST))
@_SPAN_AXES
def test_losing_any_rectangle_after_the_flush_read_rolls_back_every_effect(
    profile_run: Any, entity: type[Any], lost: str
) -> None:
    _seed_spans(profile_run, entity, _AMOUNTS["mixed"])
    start, until, amount, tx_start = _LOST[lost]
    peer = _db(profile_run, _TP)

    def peer_patch() -> None:
        peer.transact(
            lambda tx: tx.wire.amend_if(
                _name(entity),
                {"id": 1, "amount": amount, "label": "peer"},
                valid_from=start,
                until=until,
                tx_start=tx_start,
            )
        )

    before = _span_rows(profile_run, entity)
    # The source's own find is the first read naming the table's Valid-Time end;
    # the flush's coverage read is the second.
    interleaving = AfterCoverageRead(_TABLES[entity], peer_patch, nth=2)
    ours = own_root(
        connect(
            profile_run.port, _MODEL, clock=ScriptedClock([_TA]), lifecycle_provider=interleaving
        )
    ).using_database_login()

    def fn(tx: Transaction) -> None:
        _update(tx, _span_find(tx, entity, "typed", _MAR), "typed", {"amount": 100}, until=_OCT)

    with pytest.raises(ExecutionFailure) as failed:
        ours.transact(fn)
    assert interleaving.failures == []
    assert isinstance(failed.value.cause, OptimisticLockConflictError)
    # Only the peer's revision stands: nothing this attempt wrote survives.
    rows = _span_rows(profile_run, entity)
    assert all(row[0] != _TA and row[1] != _TA for row in rows)
    assert len(rows) == len(before) + 3


@_LOG_AXES
def test_an_audit_trigger_sees_the_guard_and_changes_no_outcome(
    profile_run: Any, entity: type[Any]
) -> None:
    _seed_log(profile_run, entity)
    table = _TABLES[entity]
    control = profile_run.control()
    try:
        control.execute_write("create table umw_audit (kept boolean not null)", [])
        control.execute_write("grant select on umw_audit to public", [])
        control.execute_write(
            "create function umw_on_update() returns trigger language plpgsql security definer "
            "as $body$ begin insert into umw_audit (kept) values (old.in_z = new.in_z and "
            "old.out_z = new.out_z); return new; end $body$",
            [],
        )
        control.execute_write(
            f"create trigger umw_updated after update on {table} "
            "for each row execute function umw_on_update()",
            [],
        )
    finally:
        control.close()

    _db(profile_run, _TA).transact(
        lambda tx: _update(tx, _log_find(tx, entity, "typed"), "typed", {"amount": 100})
    )
    assert list(profile_run.port.execute("select kept from umw_audit", [])) == [(True,)]
    assert _log_rows(profile_run, entity) == [(_S1, None, 100, _SPEC)]
