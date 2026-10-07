"""Separate operations over disjoint windows of one temporal object, and the
ordering barriers between them, against real Postgres.

Two writes of one bitemporal object whose requested windows share no instant —
adjacent ones included — stand together as separate operations, each keeping
its own condition: a caller's stated Transaction-Time start, or the rectangle an
observed source read. Both may start inside one stored rectangle, which a flush
then transforms once. A readless predicate write between them is an ordering
barrier: each operation executes on its own side, and the later one finds the
rows the earlier one derived from the original it states, which that earlier
unit's guarded effect proved. Every case reads back every row, current and
historical, under both storage layouts.

Standalone Docker-backed proofs, like `test_temporal_target_writes.py`; every
`Database` connects with a
:class:`~parallax.conformance.scripted_clock.ScriptedClock`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import (
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.unit_work import OptimisticLockConflictError, WritePreconditionError
from parallax.snapshot import (
    WriteEvidenceError,
    connect,
)
from parallax.snapshot.handle import ScopedDatabase, Transaction
from tests._support.root_ownership import own_root
from tests.api._coverage_interleaving import AfterCoverageRead

_NAMESPACE = "temporal.disjoint"


class Spec(ValueObject):
    title: Attr[str | None]


class Mark(ValueObject):
    code: Attr[str | None]


class ColumnsSpan(Bitemporal, table="dtw_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]


class DocumentSpan(Bitemporal, table="dtw_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    label: Attr[str | None] = attr(max_length=16)
    spec: Attr[Spec | None]
    marks: Attr[tuple[Mark, ...]]


class ColumnsLog(TxTemporal, table="dtw_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]


class DocumentLog(TxTemporal, table="dtw_document_log", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    spec: Attr[Spec | None]


class Tag(Entity, table="dtw_tag", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_MODEL = DomainModel(ColumnsSpan, DocumentSpan, ColumnsLog, DocumentLog, Tag)
_SPANS = (ColumnsSpan, DocumentSpan)
_TABLES: dict[type[Any], str] = {
    ColumnsSpan: "dtw_columns_span",
    DocumentSpan: "dtw_document_span",
    ColumnsLog: "dtw_columns_log",
    DocumentLog: "dtw_document_log",
}

type _Concurrency = Literal["optimistic", "locking"]

_SPAN_AXES = pytest.mark.parametrize("entity", _SPANS, ids=["columns", "document"])
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])

_T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_T1 = dt.datetime(2023, 12, 15, tzinfo=dt.UTC)
_TP = dt.datetime(2024, 1, 5, tzinfo=dt.UTC)
_TA = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_TB = dt.datetime(2024, 1, 20, tzinfo=dt.UTC)
_JAN, _FEB, _MAR, _APR, _MAY, _JUN, _JUL, _AUG, _SEP, _OCT = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in range(1, 11)
)

_S1 = {"title": "s1"}
_M = [{"code": "m"}]

type _Row = tuple[object, ...]
type _State = tuple[object, object, object, object]

_SEED: _State = (100, "a", _S1, _M)


def _db(profile_run: Any, *instants: dt.datetime, **options: Any) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock(list(instants)), **options)
    ).using_database_login()


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _member(entity: type[Any], member: str) -> str:
    return f"payload->'{member}'" if entity in (DocumentSpan, DocumentLog) else member


def _rows(profile_run: Any, entity: type[Any]) -> list[_Row]:
    members = ", ".join(_member(entity, name) for name in ("amount", "label", "spec", "marks"))
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        f"case when thru_z = 'infinity' then null else thru_z end, {members} "
        f"from {_TABLES[entity]} order by in_z, out_z, from_z"
    )
    return [
        tuple(int(cell) if isinstance(cell, float) else cell for cell in row)
        for row in profile_run.port.execute(sql, [])
    ]


def _start(row: _Row) -> dt.datetime:
    start = row[2]
    assert isinstance(start, dt.datetime)
    return start


def _tag_label(profile_run: Any) -> object:
    ((label,),) = profile_run.port.execute("select label from dtw_tag where id = 1", [])
    return label


def _seeded(profile_run: Any, entity: type[Any], *instants: dt.datetime) -> ScopedDatabase:
    """Span 1 as one rectangle [January, infinity) opened at T0, and tag 1."""
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, *instants)

    def seed(tx: Transaction) -> None:
        tx.insert(
            entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=(Mark(code="m"),)),
            valid_from=_JAN,
        )
        tx.insert(Tag(id=1, label="t"))

    db.transact(seed)
    return db


def _two_rectangles(profile_run: Any, entity: type[Any], *instants: dt.datetime) -> ScopedDatabase:
    """Span 1 as [January, June) opened at T0 and [June, infinity) at T1."""
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, _T1, *instants)
    db.transact(
        lambda tx: tx.insert(
            entity(id=1, amount=100, label="a", spec=Spec(title="s1"), marks=(Mark(code="m"),)),
            valid_from=_JAN,
            until=_JUN,
        )
    )
    db.transact(lambda tx: tx.insert(entity(id=1, amount=200, label="b"), valid_from=_JUN))
    return db


def _find(tx: Transaction, entity: type[Any], at: dt.datetime) -> Any:
    return tx.find(entity.where(entity.id == 1).as_of(valid_time=at)).result()


def _barrier(tx: Transaction) -> None:
    tx.update_where(Tag.where(Tag.id == 1), Tag.label.set("q"))


# --------------------------------------------------------------------------- #
# Every disjoint pair over one original, separated or adjacent, both orders.   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Operation:
    """One write over ``[start, until)`` and what it leaves of the seed there:
    a state, or ``None`` where it destroys the coverage."""

    kind: str
    start: dt.datetime
    until: dt.datetime
    order: int

    @property
    def leaves(self) -> _State | None:
        amount, label = (150, "p1") if self.order == 0 else (175, "p2")
        match self.kind:
            case "P":
                return (amount, *_SEED[1:])
            case "R":
                return (amount + 150, label, None, [])
            case "O":
                return (_SEED[0], label, *_SEED[2:])
            case _:
                return None

    def write(self, tx: Transaction, entity: type[Any], source: Any) -> None:
        amount, label = (150, "p1") if self.order == 0 else (175, "p2")
        bounds: dict[str, Any] = {"valid_from": self.start, "until": self.until, "if_tx_start": _T0}
        match self.kind:
            case "P":
                tx.wire.update(_name(entity), {"id": 1, "amount": amount}, **bounds)
            case "R":
                tx.replace(entity(id=1, amount=amount + 150, label=label), **bounds)
            case "O":
                tx.update(source.edit(label=label), until=self.until)
            case _:
                tx.terminate(source, until=self.until)


def _expected(operations: Sequence[_Operation]) -> list[_Row]:
    """The current rows the seed's [January, infinity) leaves once every
    operation took effect inside its own window, authored independently of
    the production transform: each window's own state, the seed elsewhere."""
    bounds = sorted({_JAN, *(op.start for op in operations), *(op.until for op in operations)})
    rows: list[_Row] = []
    for start, end in zip(bounds, [*bounds[1:], None], strict=True):
        inside = next(
            (
                op
                for op in operations
                if op.start <= start and (end is not None and end <= op.until)
            ),
            None,
        )
        state = _SEED if inside is None else inside.leaves
        if state is not None:
            rows.append((_TA, None, start, end, *state))
    return [(_T0, _TA, _JAN, None, *_SEED), *rows]


_PAIRS = ["P-P", "P-R", "R-P", "R-R", "P-O", "O-P", "R-O", "O-R", "P-D", "D-P", "R-D", "D-R"]
_WINDOWS: dict[str, tuple[tuple[dt.datetime, dt.datetime], tuple[dt.datetime, dt.datetime]]] = {
    "separated": ((_FEB, _APR), (_JUN, _AUG)),
    "adjacent": ((_FEB, _APR), (_APR, _JUN)),
    "separated-later-first": ((_JUN, _AUG), (_FEB, _APR)),
    "adjacent-later-first": ((_APR, _JUN), (_FEB, _APR)),
}


@_SPAN_AXES
@_STRATEGIES
@pytest.mark.parametrize("windows", list(_WINDOWS))
@pytest.mark.parametrize("pair", _PAIRS)
def test_disjoint_operations_over_one_original_each_keep_their_own_effect(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, pair: str, windows: str
) -> None:
    db = _seeded(profile_run, entity, _TA)
    operations = [
        _Operation(kind, start, until, order)
        for order, (kind, (start, until)) in enumerate(
            zip(pair.split("-"), _WINDOWS[windows], strict=True)
        )
    ]

    def fn(tx: Transaction) -> None:
        # Every observed source is read before any write, so both operations
        # are pending together: each reads the one rectangle at its own start.
        sources = [_find(tx, entity, op.start) if op.kind in "OD" else None for op in operations]
        for op, source in zip(operations, sources, strict=True):
            op.write(tx, entity, source)

    db.transact(fn, concurrency=concurrency)
    # The one original is closed once, at one instant; everything outside the
    # two windows keeps its own values, and each window its operation's.
    assert _rows(profile_run, entity) == _expected(operations)


@_SPAN_AXES
@_STRATEGIES
@pytest.mark.parametrize("order", ["earlier-first", "later-first"])
def test_disjoint_targets_over_distinct_originals_meet_their_own_starts(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, order: str
) -> None:
    db = _two_rectangles(profile_run, entity, _TA)
    writes: list[Callable[[Transaction], None]] = [
        lambda tx: tx.wire.update(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_APR, if_tx_start=_T0
        ),
        lambda tx: tx.replace(
            entity(id=1, amount=300, label="r"), valid_from=_SEP, until=_OCT, if_tx_start=_T1
        ),
    ]
    if order == "later-first":
        writes.reverse()

    def fn(tx: Transaction) -> None:
        for write in writes:
            write(tx)

    db.transact(fn, concurrency=concurrency)
    assert _rows(profile_run, entity) == [
        (_T0, _TA, _JAN, _JUN, *_SEED),
        (_T1, _TA, _JUN, None, 200, "b", None, []),
        (_TA, None, _JAN, _FEB, *_SEED),
        (_TA, None, _FEB, _APR, 150, "a", _S1, _M),
        (_TA, None, _APR, _JUN, *_SEED),
        (_TA, None, _JUN, _SEP, 200, "b", None, []),
        (_TA, None, _SEP, _OCT, 300, "r", None, []),
        (_TA, None, _OCT, None, 200, "b", None, []),
    ]


@_SPAN_AXES
@_STRATEGIES
def test_a_disjoint_target_stating_another_rectangles_start_changes_nothing(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _two_rectangles(profile_run, entity, _TA, _TB)
    before = _rows(profile_run, entity)
    attempts = 0

    def fn(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_APR, if_tx_start=_T0
        )
        # September lies in the rectangle opened at T1; T0 names the other one.
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 175}, valid_from=_SEP, until=_OCT, if_tx_start=_T0
        )

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(fn, concurrency=concurrency, retry_optimistic_conflicts=True)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert attempts == 1
    assert _rows(profile_run, entity) == before


def _overlapping_observed(tx: Transaction, entity: type[Any], source: Any) -> None:
    tx.update(source.edit(label="o"), until=_AUG)


def _overlapping_target(tx: Transaction, entity: type[Any], source: Any) -> None:
    del source
    tx.wire.update(
        _name(entity), {"id": 1, "amount": 1}, valid_from=_JUN, until=_AUG, if_tx_start=_T0
    )


@_SPAN_AXES
@pytest.mark.parametrize(
    "second",
    [
        pytest.param(_overlapping_observed, id="an-unequal-overlap"),
        pytest.param(_overlapping_target, id="an-overlapping-target"),
    ],
)
def test_a_window_overlapping_a_targets_unequally_is_refused_and_earlier_work_still_runs(
    profile_run: Any, entity: type[Any], second: Callable[[Transaction, type[Any], Any], None]
) -> None:
    db = _seeded(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        source = _find(tx, entity, _JUN)
        # An unbounded window reaches every later window, whatever its start.
        tx.wire.update(_name(entity), {"id": 1, "amount": 150}, valid_from=_MAR, if_tx_start=_T0)
        with pytest.raises(WriteEvidenceError, match="write-evidence-already-claimed"):
            second(tx, entity, source)

    db.transact(fn)
    assert _rows(profile_run, entity) == [
        (_T0, _TA, _JAN, None, *_SEED),
        (_TA, None, _JAN, _MAR, *_SEED),
        (_TA, None, _MAR, None, 150, "a", _S1, _M),
    ]


# --------------------------------------------------------------------------- #
# Ordering barriers: each operation on its own side, proven across it.         #
# --------------------------------------------------------------------------- #
def _install(profile_run: Any, entity: type[Any], body: str) -> None:
    """A trigger on the tag table, which the readless predicate write updates:
    ``body`` runs once per updated tag row, as the table's owner."""
    control = profile_run.control()
    try:
        control.execute_write(
            "create table dtw_audit (seen int not null, current_rows int not null)", []
        )
        control.execute_write("grant select on dtw_audit to public", [])
        control.execute_write(
            "create function dtw_on_tag() returns trigger language plpgsql security definer "
            f"as $body$ begin {body} return new; end $body$",
            [],
        )
        control.execute_write(
            "create trigger dtw_tag_updated after update on dtw_tag "
            "for each row execute function dtw_on_tag()",
            [],
        )
    finally:
        control.close()


def _audit_current_rows(entity: type[Any]) -> str:
    return (
        "insert into dtw_audit (seen, current_rows) select 1, count(*) "
        f"from {_TABLES[entity]} where id = 1 and out_z = 'infinity';"
    )


def _audited(profile_run: Any) -> list[tuple[object, ...]]:
    return list(profile_run.port.execute("select seen, current_rows from dtw_audit", []))


_ACROSS = {
    "target-then-target": ("P", "P"),
    "target-then-observed": ("P", "O"),
    "observed-then-target": ("O", "P"),
    "replacement-then-destruction": ("R", "D"),
}


@_SPAN_AXES
@_STRATEGIES
@pytest.mark.parametrize("sequence", list(_ACROSS))
def test_a_barrier_between_disjoint_operations_keeps_each_on_its_own_side(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, sequence: str
) -> None:
    db = _seeded(profile_run, entity, _TA)
    _install(profile_run, entity, _audit_current_rows(entity))
    first, second = (
        _Operation(kind, start, until, order)
        for order, (kind, (start, until)) in enumerate(
            zip(_ACROSS[sequence], ((_FEB, _APR), (_JUN, _AUG)), strict=True)
        )
    )

    def fn(tx: Transaction) -> None:
        sources = [
            _find(tx, entity, op.start) if op.kind in "OD" else None for op in (first, second)
        ]
        first.write(tx, entity, sources[0])
        _barrier(tx)
        second.write(tx, entity, sources[1])

    db.transact(fn, concurrency=concurrency)
    # When the barrier ran, the first operation had split the original into
    # three rows and the second had not yet written.
    assert _audited(profile_run) == [(1, 3)]
    assert _tag_label(profile_run) == "q"
    # Each operation's own effect stands at one instant, with no history of the
    # attempt's own: the second revised or removed the rows the first opened.
    assert _rows(profile_run, entity) == _expected((first, second))


@_SPAN_AXES
@_STRATEGIES
def test_a_write_of_the_same_window_after_a_barrier_carries_the_values_left_before_it(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run, entity, _TA)

    def fn(tx: Transaction) -> None:
        source = _find(tx, entity, _FEB)
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_APR, if_tx_start=_T0
        )
        _barrier(tx)
        tx.update(source.edit(label="o"), until=_APR)

    db.transact(fn, concurrency=concurrency)
    # The observed edit lands on the row the target left: the amount is the
    # target's, never the one the source observed.
    assert _rows(profile_run, entity) == [
        (_T0, _TA, _JAN, None, *_SEED),
        (_TA, None, _JAN, _FEB, *_SEED),
        (_TA, None, _FEB, _APR, 150, "o", _S1, _M),
        (_TA, None, _APR, None, *_SEED),
    ]


@_SPAN_AXES
@_STRATEGIES
def test_overlapping_observed_writes_on_either_side_of_a_barrier_apply_in_authored_order(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run, entity, _TA)
    _install(profile_run, entity, _audit_current_rows(entity))

    def fn(tx: Transaction) -> None:
        early, later = _find(tx, entity, _MAR), _find(tx, entity, _APR)
        tx.update(early.edit(label="e"), until=_JUN)
        _barrier(tx)
        tx.update(later.edit(amount=175), until=_AUG)

    db.transact(fn, concurrency=concurrency)
    assert _audited(profile_run) == [(1, 3)]
    assert _rows(profile_run, entity) == [
        (_T0, _TA, _JAN, None, *_SEED),
        (_TA, None, _JAN, _MAR, *_SEED),
        (_TA, None, _MAR, _APR, 100, "e", _S1, _M),
        (_TA, None, _APR, _JUN, 175, "e", _S1, _M),
        (_TA, None, _JUN, _AUG, 175, "a", _S1, _M),
        (_TA, None, _AUG, None, *_SEED),
    ]


_BREAKS = {
    "restamped": "update {table} set in_z = in_z + interval '1 second' "
    "where id = 1 and out_z = 'infinity' and from_z = timestamptz '2024-04-01 00:00:00+00';",
    "removed": "delete from {table} where id = 1 and out_z = 'infinity' "
    "and from_z = timestamptz '2024-04-01 00:00:00+00';",
}


@_SPAN_AXES
@_STRATEGIES
@pytest.mark.parametrize("broken", list(_BREAKS))
def test_a_side_effect_that_breaks_continuity_across_a_barrier_fails_the_later_operation(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency, broken: str
) -> None:
    db = _seeded(profile_run, entity, _TA)
    _install(profile_run, entity, _BREAKS[broken].format(table=_TABLES[entity]))
    before = _rows(profile_run, entity)

    def fn(tx: Transaction) -> None:
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_APR, if_tx_start=_T0
        )
        _barrier(tx)
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 175}, valid_from=_JUN, until=_AUG, if_tx_start=_T0
        )

    with pytest.raises(ExecutionFailure) as failed:
        db.transact(fn, concurrency=concurrency)
    # The row the barrier's side effect changed is no longer what the first
    # unit derived from the original the caller stated, so nothing proves it.
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert _rows(profile_run, entity) == before
    assert _tag_label(profile_run) == "t"


# --------------------------------------------------------------------------- #
# A dependent read between disjoint windows of one original.                   #
# --------------------------------------------------------------------------- #
@_SPAN_AXES
@_STRATEGIES
def test_after_a_read_flushes_one_window_a_later_window_restates_its_start(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    db = _seeded(profile_run, entity, _TA, _TB)

    def stale(tx: Transaction) -> None:
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_APR, if_tx_start=_T0
        )
        _find(tx, entity, _JAN)
        # The flush closed the original T0 named; its token is not rebased.
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 175}, valid_from=_JUN, until=_AUG, if_tx_start=_T0
        )

    before = _rows(profile_run, entity)
    with pytest.raises(ExecutionFailure) as failed:
        db.transact(stale, concurrency=concurrency)
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert _rows(profile_run, entity) == before

    def fresh(tx: Transaction) -> None:
        early = _find(tx, entity, _JUN)
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_APR, if_tx_start=_T0
        )
        current = _find(tx, entity, _JUN)
        with pytest.raises(WriteEvidenceError, match="write-evidence-consumed"):
            tx.update(early.edit(label="stale"), until=_AUG)
        tx.update(current.edit(label="fresh"), until=_AUG)
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 175}, valid_from=_SEP, until=_OCT, if_tx_start=_TB
        )

    db.transact(fresh, concurrency=concurrency)
    assert _rows(profile_run, entity) == [
        (_T0, _TB, _JAN, None, *_SEED),
        (_TB, None, _JAN, _FEB, *_SEED),
        (_TB, None, _FEB, _APR, 150, "a", _S1, _M),
        (_TB, None, _APR, _JUN, *_SEED),
        (_TB, None, _JUN, _AUG, 100, "fresh", _S1, _M),
        (_TB, None, _AUG, _SEP, *_SEED),
        (_TB, None, _SEP, _OCT, 175, "a", _S1, _M),
        (_TB, None, _OCT, None, *_SEED),
    ]


# --------------------------------------------------------------------------- #
# Another session changes an original after the flush read it.                 #
# --------------------------------------------------------------------------- #
def _interleaved(
    profile_run: Any,
    entity: type[Any],
    peer: Callable[[], None],
    *instants: dt.datetime,
    nth: int = 1,
) -> tuple[ScopedDatabase, AfterCoverageRead]:
    interleaving = AfterCoverageRead(_TABLES[entity], peer, nth=nth)
    return _db(profile_run, *instants, lifecycle_provider=interleaving), interleaving


@_SPAN_AXES
@pytest.mark.parametrize("barrier", [False, True], ids=["one-unit", "across-a-barrier"])
def test_a_shared_original_revised_after_the_flush_read_fails_at_its_one_guard(
    profile_run: Any, entity: type[Any], barrier: bool
) -> None:
    _seeded(profile_run, entity)
    peer_db = _db(profile_run, _TP)

    def peer() -> None:
        peer_db.transact(
            lambda tx: tx.update(_find(tx, entity, _MAY).edit(label="peer"), until=_JUN)
        )

    ours, interleaving = _interleaved(profile_run, entity, peer, _TA, _TB)
    attempts = 0

    def fn(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_APR, if_tx_start=_T0
        )
        if barrier:
            _barrier(tx)
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 175}, valid_from=_JUN, until=_AUG, if_tx_start=_T0
        )

    with pytest.raises(ExecutionFailure) as failed:
        ours.transact(fn, retry_optimistic_conflicts=True)
    # Both callers stated the original the peer replaced; the guard on it is
    # the first start's, so the failure is that caller's and is not retried.
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert (attempts, interleaving.failures) == (1, [])
    assert [row[:4] for row in _rows(profile_run, entity)] == [
        (_T0, _TP, _JAN, None),
        (_TP, None, _JAN, _MAY),
        (_TP, None, _MAY, _JUN),
        (_TP, None, _JUN, None),
    ]
    assert _tag_label(profile_run) == "t"


@_SPAN_AXES
def test_a_lost_second_start_is_its_callers_and_a_lost_observed_original_retries(
    profile_run: Any, entity: type[Any]
) -> None:
    _two_rectangles(profile_run, entity)
    peer_db = _db(profile_run, _TP, _TP)

    def peer() -> None:
        peer_db.transact(
            lambda tx: tx.update(_find(tx, entity, _JUL).edit(label="peer"), until=_AUG)
        )

    ours, interleaving = _interleaved(profile_run, entity, peer, _TA)
    with pytest.raises(ExecutionFailure) as failed:
        ours.transact(
            lambda tx: (
                tx.wire.update(
                    _name(entity),
                    {"id": 1, "amount": 150},
                    valid_from=_FEB,
                    until=_APR,
                    if_tx_start=_T0,
                ),
                tx.wire.update(
                    _name(entity),
                    {"id": 1, "amount": 175},
                    valid_from=_SEP,
                    until=_OCT,
                    if_tx_start=_T1,
                ),
            ),
            retry_optimistic_conflicts=True,
        )
    assert isinstance(failed.value.cause, WritePreconditionError)
    assert failed.value.cause.expected == _T1
    assert interleaving.failures == []

    # An observed write over a disjoint window keeps its own source's
    # condition: losing that original is an ordinary conflict, which retries
    # with the callback reading its source again.
    _two_rectangles(profile_run, entity)
    second_peer = _db(profile_run, _TP)

    def later_peer() -> None:
        second_peer.transact(
            lambda tx: tx.update(_find(tx, entity, _JUL).edit(label="peer"), until=_AUG)
        )

    retried, interleaving = _interleaved(profile_run, entity, later_peer, _TA, _TB)
    attempts = 0

    def fn(tx: Transaction) -> None:
        nonlocal attempts
        attempts += 1
        source = _find(tx, entity, _SEP)
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_APR, if_tx_start=_T0
        )
        tx.update(source.edit(label="o"), until=_OCT)

    retried.transact(fn, retry_optimistic_conflicts=True)
    assert (attempts, interleaving.failures) == (2, [])
    current = sorted((row for row in _rows(profile_run, entity) if row[1] is None), key=_start)
    assert [row[2:6] for row in current] == [
        (_JAN, _FEB, 100, "a"),
        (_FEB, _APR, 150, "a"),
        (_APR, _JUN, 100, "a"),
        (_JUN, _JUL, 200, "b"),
        (_JUL, _AUG, 200, "peer"),
        (_AUG, _SEP, 200, "b"),
        (_SEP, _OCT, 200, "o"),
        (_OCT, None, 200, "b"),
    ]


@_SPAN_AXES
def test_a_disjoint_observed_original_lost_without_retries_rolls_every_effect_back(
    profile_run: Any, entity: type[Any]
) -> None:
    _two_rectangles(profile_run, entity)
    peer_db = _db(profile_run, _TP)

    def peer() -> None:
        peer_db.transact(
            lambda tx: tx.update(_find(tx, entity, _JUL).edit(label="peer"), until=_AUG)
        )

    ours, _interleaving = _interleaved(profile_run, entity, peer, _TA)

    def fn(tx: Transaction) -> None:
        source = _find(tx, entity, _SEP)
        tx.wire.update(
            _name(entity), {"id": 1, "amount": 150}, valid_from=_FEB, until=_APR, if_tx_start=_T0
        )
        tx.update(source.edit(label="o"), until=_OCT)

    with pytest.raises(ExecutionFailure) as failed:
        ours.transact(fn)
    assert isinstance(failed.value.cause, OptimisticLockConflictError)
    assert [row[:2] for row in _rows(profile_run, entity)][:2] == [(_T0, None), (_T1, _TP)]


# --------------------------------------------------------------------------- #
# Across a barrier on a Transaction-Time-Only object, and through an          #
# insertion's own source.                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("entity", (ColumnsLog, DocumentLog), ids=["columns", "document"])
@_STRATEGIES
def test_a_transaction_time_write_after_a_barrier_revises_the_row_the_first_opened(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    db = _db(profile_run, _T0, _TA)

    def seed(tx: Transaction) -> None:
        tx.insert(entity(id=1, label="seed", spec=Spec(title="s1")))
        tx.insert(Tag(id=1, label="t"))

    db.transact(seed)

    def fn(tx: Transaction) -> None:
        tx.wire.update(_name(entity), {"id": 1, "label": "p"}, if_tx_start=_T0)
        _barrier(tx)
        # Both callers state the milestone the first one closes; the second's
        # stands at the row the first opened from it.
        tx.wire.update(_name(entity), {"id": 1, "spec": {"title": "s2"}}, if_tx_start=_T0)

    db.transact(fn, concurrency=concurrency)
    members = ", ".join(_member(entity, name) for name in ("label", "spec"))
    rows = profile_run.port.execute(
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{members} from {_TABLES[entity]} order by in_z",
        [],
    )
    assert [tuple(row) for row in rows] == [
        (_T0, _TA, "seed", _S1),
        (_TA, None, "p", {"title": "s2"}),
    ]


@_SPAN_AXES
@_STRATEGIES
def test_an_insertion_sources_edits_on_both_sides_of_a_barrier_keep_one_instant(
    profile_run: Any, entity: type[Any], concurrency: _Concurrency
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    # Inserting a Non-Temporal tag captures no Transaction Instant.
    db = _db(profile_run, _TA)
    db.transact(lambda tx: tx.insert(Tag(id=1, label="t")))

    def fn(tx: Transaction) -> None:
        inserted = tx.wire.insert(
            _name(entity), {"id": 1, "amount": 100, "label": "a"}, valid_from=_JAN
        )
        _find(tx, entity, _JAN)
        tx.wire.update(inserted, {"amount": 150}, until=_APR)
        _barrier(tx)
        tx.wire.update(inserted, {"label": "z"}, until=_JUN)

    db.transact(fn, concurrency=concurrency)
    assert _rows(profile_run, entity) == [
        (_TA, None, _JAN, _APR, 150, "z", None, []),
        (_TA, None, _APR, _JUN, 100, "z", None, []),
        (_TA, None, _JUN, None, 100, "a", None, []),
    ]
