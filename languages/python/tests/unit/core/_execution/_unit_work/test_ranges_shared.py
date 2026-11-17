"""The deferred ranges of one acquisition span bound through one scoped
binding (`m-unit-work` *Shared coverage acquisition*), over the in-memory
acquisition: their uncovered parts read in shared reads packed in range order —
a Bitemporal range's in Valid-Time order, a Transaction-Time-Only range's one
current row whole — each range ready once every read naming its parts
succeeded, and the leading ready ranges bound together as one Write Group only
when the flush advances to it."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from types import FrameType
from typing import Any, cast

import pytest

from parallax.core import Attr, Bitemporal, DomainModel, InternalError, TxTemporal, attr
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import ranges as ranges_module
from parallax.core._execution._unit_work import write_plan as plan_module
from parallax.core._execution._unit_work.acquisition_spans import AcquisitionSpan
from parallax.core._execution._unit_work.effects import (
    CARDINALITY_CORRUPTION,
    WRITE_PRECONDITION_FAILED,
    WritePreconditionError,
)
from parallax.core._execution._unit_work.instructions import (
    PreparedTargetInstruction,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.ranges import DeferredRange, RangeBindings
from parallax.core._execution._unit_work.row_acquisition import (
    AcquireRows,
    CompletionRequest,
    CoverageReadRequest,
    RetainedTargetState,
    RowConsumer,
    RowRequest,
)
from parallax.core._execution._unit_work.write_items import AdmittedWrite, TargetWrite, target_write
from parallax.core._execution._unit_work.write_plan import WriteGroup, WritePlan
from parallax.core.internal.base import INFINITY
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.entity._construction_input import ABSENT
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.inheritance import inheritance_facet_of
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.planned_step import ObjectKey, PredecessorRow, PredecessorRows
from parallax.core.internal.planned_step.keys import ObjectStateKey, TemporalObjectStateKey
from parallax.core.internal.planned_step.steps import (
    MilestoneTarget,
    PlannedClose,
    PlannedInsert,
    PlannedStep,
)
from parallax.core.internal.planned_step.write_effects import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    WriteEffects,
)
from parallax.core.internal.temporal_read import milestone_edge, temporal_facet_of
from parallax.core.internal.unit_work import (
    KeyedWriteInstruction,
    TargetWriteInstruction,
    WritePlanningRequest,
    admitted_write,
)
from tests._support.bindings import bound_model
from tests._support.clock_probes import instant_at
from tests._support.errors import raises_code
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, admitted_writes
from tests._support.write_preparation import write_preparation_of
from tests.unit._positional_row_support import positional_row
from tests.unit.core._execution._reach_support import frames, reaches
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows
from tests.unit.core._shared_coverage_support import (
    AT,
    MODEL,
    T0,
    ShareCols,
    covered_target,
    day,
    frag,
    frag_rows,
    observation,
    plan,
    rectangle,
)

_BIND_RANGE = ranges_module._bind_range  # pyright: ignore[reportPrivateUsage] - the binding every deferred range takes


def _always(state: ObjectStateKey, read_at: int) -> bool:
    del state, read_at
    return True


class _Traced:
    """``held``'s answers, each request recorded in ``trace`` as it is asked
    for: a completion by the keys it completes, a coverage read by each key it
    names and how many parts. ``answers`` keeps each object's rows a read
    answered, and ``fail`` raises in place of the read it names, counting
    coverage reads from 1. What it records stays out of reach of the
    acquisition it hands out, which is a function."""

    def __init__(self, held: AcquireRows) -> None:
        self.trace: list[tuple[str, tuple[Any, ...]]] = []
        self.answers: list[PredecessorRows] = []
        self.fail: dict[int, BaseException] = {}
        self.reads = 0
        self.acquire = self._acquisition(held)

    def _acquisition(self, held: AcquireRows) -> AcquireRows:
        def acquire[Request: RowRequest, Result](
            request: Request, consumer: RowConsumer[Request, Result], /
        ) -> Result:
            self._asked(request)
            answer = held(request, consumer)
            self._record(answer)
            return answer

        return acquire

    def _asked(self, request: RowRequest) -> None:
        if isinstance(request, CompletionRequest):
            self.trace.append(("complete", tuple(row[0] for row in request.rows)))
            return
        assert isinstance(request, CoverageReadRequest)
        self.reads += 1
        self.trace.append(
            (
                "read",
                tuple((term.key_value, term.part_count) for term in request.terms),
            )
        )
        failure = self.fail.get(self.reads)
        if failure is not None:
            raise failure

    def _record(self, answer: object) -> None:
        if isinstance(answer, PredecessorRows):
            self.answers.append(answer)
        elif isinstance(answer, dict):
            by_key = cast("dict[object, PredecessorRows]", answer)
            self.answers.extend(by_key.values())


def _bindings(written: WritePlan, acquire: AcquireRows, model: Metamodel = MODEL) -> RangeBindings:
    """The scoped binding of ``written``'s one turn, an acquisition span."""
    (span,) = written.turns
    assert isinstance(span, AcquisitionSpan)
    return _span_bindings(span, acquire, model)


def _span_bindings(
    span: AcquisitionSpan, acquire: AcquireRows, model: Metamodel = MODEL
) -> RangeBindings:
    planner = build_write_planner(bound_model(model))
    return RangeBindings(
        span,
        acquire_rows=acquire,
        current=_always,
        ownership=NO_TEMPORAL_WRITE_OWNERSHIP,
        audit=planner.audit_decoration(
            actor_identity=TEST_ACTOR_IDENTITY, transaction_instant=instant_at(AT.isoformat())
        ),
        payloads=planner.payloads,
    )


def _key(bound: WriteEffects) -> object:
    state = next(iter(bound.changed))
    assert isinstance(state, TemporalObjectStateKey)
    ((_name, value),) = state.object.primary_key
    return value


def _keys(group: WriteGroup) -> tuple[object, ...]:
    return tuple(_key(write) for write in group.writes)


def _members(groups: Sequence[WriteGroup]) -> list[BoundRange]:
    """Every bound range of ``groups``, in order."""
    members: list[BoundRange] = []
    for group in groups:
        for write in group.writes:
            assert isinstance(write, BoundRange)
            members.append(write)
    return members


def _drained(bindings: RangeBindings, trace: list[tuple[str, tuple[Any, ...]]]) -> list[WriteGroup]:
    """Each group ``bindings`` answer, its keys recorded in ``trace`` as it is
    answered."""
    groups: list[WriteGroup] = []
    with bindings:
        for each in bindings:
            trace.append(("bind", _keys(each)))
            groups.append(each)
    return groups


def _span(written: WritePlan) -> WritePlan:
    """``written``, whose every write is deferred into its one acquisition
    span."""
    (span,) = written.turns
    assert isinstance(span, AcquisitionSpan) and len(span.ranges) > 1
    return written


def _fragmented(
    entity: type[Bitemporal],
    parts: Sequence[int],
    *,
    concurrency: ConcurrencyPreference = "optimistic",
) -> tuple[WritePlan, list[PredecessorRow]]:
    """One span of ``frag(k, parts[k - 1])`` for each object ``k``, beside every
    row the objects store."""
    writes = [write for key, count in enumerate(parts, 1) for write in frag(entity, key, count)]
    stored = [row for key, count in enumerate(parts, 1) for row in frag_rows(entity, key, count)]
    return _span(plan(writes, concurrency=concurrency)), stored


@dataclass(slots=True)
class _Bound:
    """Each binding's evidence, recorded as the binding is asked for."""

    calls: list[tuple[object, PredecessorRows | None, tuple[PredecessorRows, ...]]] = field(
        default_factory=list[tuple[object, PredecessorRows | None, tuple[PredecessorRows, ...]]]
    )

    def __call__(
        self,
        deferred: DeferredRange,
        reused: PredecessorRows | None,
        acquired: Sequence[PredecessorRows],
        **keywords: Any,
    ) -> BoundRange:
        self.calls.append((deferred.key_value, reused, tuple(acquired)))
        return _BIND_RANGE(deferred, reused, acquired, **keywords)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> _Bound:
    bound = _Bound()
    monkeypatch.setattr(ranges_module, "_bind_range", bound)
    return bound


# --------------------------------------------------------------------------- #
# Readiness: the read finishing each range's parts, whatever it returned.     #
# --------------------------------------------------------------------------- #
def test_a_range_needing_nothing_binds_at_once_and_none_passes_an_earlier_unready_one() -> None:
    first, first_row = covered_target(ShareCols, 1)
    third, third_row = covered_target(ShareCols, 3)
    writes = [first, *frag(ShareCols, 2, 65), third, *frag(ShareCols, 4, 1)]
    stored = [first_row, *frag_rows(ShareCols, 2, 65), third_row, *frag_rows(ShareCols, 4, 1)]
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    written = _span(plan(writes, concurrency="locking"))
    bound = _drained(_bindings(written, traced.acquire), traced.trace)
    # Readiness [0, 2, 0, 2]: the first executes alone before any read, and
    # the third waits behind the second's two reads, then joins its group.
    assert traced.trace == [
        ("complete", (1,)),
        ("complete", (3,)),
        ("bind", (1,)),
        ("read", ((2, 64),)),
        ("read", ((2, 1), (4, 1))),
        ("bind", (2, 3, 4)),
    ]
    assert [_keys(each) for each in bound] == [(1,), (2, 3, 4)]


def test_a_read_can_finish_one_range_while_it_reads_part_of_the_next(recorded: _Bound) -> None:
    written, stored = _fragmented(ShareCols, (33, 33, 1))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    _drained(_bindings(written, traced.acquire), traced.trace)
    assert traced.trace == [
        ("read", ((1, 33), (2, 31))),
        ("bind", (1,)),
        ("read", ((2, 2), (3, 1))),
        ("bind", (2, 3)),
    ]
    # The second range binds every read's rows, each read's apart.
    assert [(key, reused, len(acquired)) for key, reused, acquired in recorded.calls] == [
        (1, None, 1),
        (2, None, 2),
        (3, None, 1),
    ]
    _key, _reused, (earlier, later) = recorded.calls[1]
    assert (len(earlier), len(later)) == (31, 2)


@pytest.mark.parametrize(
    ("parts", "reads"),
    [((63,), 1), ((64,), 1), ((65,), 2), ((63, 1), 1), ((64, 1), 2), ((32, 32), 1)],
)
def test_each_read_names_at_most_64_parts_of_the_span(parts: tuple[int, ...], reads: int) -> None:
    if len(parts) == 1:
        (count,) = parts
        written = plan(frag(ShareCols, 1, count))
        (alone,) = written.turns
        assert isinstance(alone, AcquisitionSpan) and len(alone.ranges) == 1
        stored = frag_rows(ShareCols, 1, count)
    else:
        written, stored = _fragmented(ShareCols, parts)
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    bound = _members(_drained(_bindings(written, traced.acquire), traced.trace))
    named = [entry for entry in traced.trace if entry[0] == "read"]
    assert len(named) == reads
    assert all(sum(windows for _key, windows in terms) <= 64 for _kind, terms in named)
    # Every range closes every rectangle it stores, whatever read found it.
    for each, count in zip(bound, parts, strict=True):
        assert sum(isinstance(step, PlannedClose) for step in each.steps) == 2 * count


@pytest.mark.parametrize("replaces", [False, True], ids=["amendment", "replacement"])
def test_a_range_whose_read_returned_nothing_binds_as_it_binds_alone(replaces: bool) -> None:
    # Object 2 stores only the rectangle it observed, so the read of the part
    # beyond it returns nothing for it: it is ready all the same.
    observed = rectangle(ShareCols, 2, 0, 2, 5)
    later = _reaching_past(observed, replaces=replaces)
    writes = [*frag(ShareCols, 1, 1), later]
    stored = [*frag_rows(ShareCols, 1, 1), observed]
    written = _span(plan(writes))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    shared = _members(_drained(_bindings(written, traced.acquire), traced.trace))
    assert traced.trace == [("read", ((1, 1), (2, 1))), ("bind", (1, 2))]
    alone = _members(
        _drained(_bindings(plan([later]), HeldRows(MODEL, stored, overlapping=True)), [])
    )
    assert shared[1].steps == alone[0].steps
    openings = [_window(step) for step in shared[1].steps if isinstance(step, PlannedInsert)]
    # A replacement opens its state over the part no row held; an amendment
    # opens nothing past the rows it found.
    assert any(end == day(4) for _start, end in openings) is replaces


def _reaching_past(observed: PredecessorRow, *, replaces: bool) -> AdmittedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "replaceUntil" if replaces else "amendUntil",
            ShareCols.identity.canonical,
            ({"id": 2, "amount": 9, "label": "k2"} if replaces else {"id": 2, "amount": 9},),
            day(0),
            day(4),
        ),
        write_preparation_of(MODEL),
    )
    held = observation(ShareCols, observed)
    return admitted_write(prepared, held, held.key.object)


def _window(step: PlannedStep) -> tuple[object, object]:
    assert isinstance(step, PlannedInsert)
    (entry,) = step.entries
    cells = {identity.name: value for identity, value in entry.row.attributes.items()}
    return cells["validStart"], cells["validEnd"]


def test_each_ranges_missing_term_is_derived_once_before_anything_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    derive = ranges_module._missing_term  # pyright: ignore[reportPrivateUsage] - the derivation each range takes once
    written, stored = _fragmented(ShareCols, (33, 33, 1))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    derived: list[int] = []

    def deriving(*arguments: Any) -> Any:
        derived.append(traced.reads)
        return derive(*arguments)

    monkeypatch.setattr(ranges_module, "_missing_term", deriving)
    _drained(_bindings(written, traced.acquire), traced.trace)
    assert derived == [0, 0, 0]


# --------------------------------------------------------------------------- #
# Each stored row reaches its own object's binding.                           #
# --------------------------------------------------------------------------- #


def test_a_row_one_read_returns_twice_reaches_its_binding_twice(recorded: _Bound) -> None:
    # An Optimistic target write's caller states the row at its window's start.
    written = _span(plan([*frag(ShareCols, 1, 1), covered_target(ShareCols, 2)[0]]))
    start = rectangle(ShareCols, 2, 0, None, 0)
    held = HeldRows(MODEL, [*frag_rows(ShareCols, 1, 1), start, start], overlapping=True)
    with _bindings(written, held) as bindings:
        # Both are ready after the one read, so the later range's binding
        # fails the group the earlier one bound into.
        with raises_code(InternalError, CARDINALITY_CORRUPTION) as corrupt:
            next(bindings)
        assert next(bindings, None) is None
    assert "affected 2 row(s), expected 1" in str(corrupt.value)
    assert [key for key, _reused, _acquired in recorded.calls] == [1, 2]


def test_a_row_two_reads_both_return_is_bound_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ranges_module, "_PARTS_PER_READ", 1)
    written, stored = _fragmented(ShareCols, (1, 2))
    traced = _Traced(_KeyedRows(stored))
    shared = _members(_drained(_bindings(written, traced.acquire), traced.trace))
    assert [entry for entry in traced.trace if entry[0] == "read"] == [
        ("read", ((1, 1),)),
        ("read", ((2, 1),)),
        ("read", ((2, 1),)),
    ]
    alone = _members(
        _drained(
            _bindings(
                plan(frag(ShareCols, 2, 2)),
                HeldRows(MODEL, frag_rows(ShareCols, 2, 2), overlapping=True),
            ),
            [],
        )
    )
    assert shared[1].steps == alone[0].steps


@dataclass(slots=True)
class _KeyedRows:
    """A read answering every stored row of each object it names, whatever
    windows it names."""

    rows: Sequence[PredecessorRow]

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        assert isinstance(request, CoverageReadRequest)
        named = [term.key_value for term in request.terms]
        held = [row for row in self.rows if row.members["id"] in named]
        return HeldRows(MODEL, held)(request, consumer)


# --------------------------------------------------------------------------- #
# The failure encountered first propagates.                                   #
# --------------------------------------------------------------------------- #
class _Refused(Exception):
    pass


def test_a_later_ranges_retained_completion_fails_before_any_read_or_binding(
    recorded: _Bound,
) -> None:
    first, first_row = covered_target(ShareCols, 1)
    second, second_row = covered_target(ShareCols, 2)
    refused = _Refused()
    held = HeldRows(MODEL, [first_row, second_row], overlapping=True)

    def acquire[Request: RowRequest, Result](
        request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        if isinstance(request, CompletionRequest) and request.rows[0][0] == 2:
            raise refused
        return held(request, consumer)

    written = _span(plan([first, *frag(ShareCols, 3, 1), second], concurrency="locking"))
    with pytest.raises(_Refused) as raised, _bindings(written, acquire) as bindings:
        next(bindings)
    assert raised.value is refused
    assert recorded.calls == []
    assert [type(request) for request in held.requests] == [CompletionRequest]


# --------------------------------------------------------------------------- #
# However the scope ends, it holds none of the rows it read.                  #
# --------------------------------------------------------------------------- #
def _binding_frames(failure: BaseException) -> list[FrameType]:
    return [
        frame
        for frame in frames(failure.__traceback__, module=ranges_module.__file__)
        if frame.f_code.co_qualname.startswith((f"{RangeBindings.__name__}.", "_transfer"))
    ]


def _three() -> tuple[WritePlan, list[PredecessorRow]]:
    """A span whose first read finishes the first range and reads part of the
    second, and whose second read finishes the second and the third."""
    return _fragmented(ShareCols, (1, 64, 1))


@pytest.mark.parametrize("leaves", ["exhaustion", "break", "raise"])
def test_a_scope_left_any_way_holds_none_of_the_rows_it_read(leaves: str) -> None:
    written, stored = _three()
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    bindings = _bindings(written, traced.acquire)
    bound: list[WriteGroup] = []
    with contextlib.suppress(_Refused), bindings:
        for each in bindings:
            bound.append(each)
            if leaves == "raise":
                raise _Refused
            if leaves == "break":
                break
    assert traced.answers
    assert not any(reaches([bindings], rows) for rows in traced.answers)
    assert next(bindings, None) is None
    # What the bound groups carry is the flush's, and stays usable.
    assert all(sum(isinstance(step, PlannedClose) for step in each.steps) for each in bound)


def test_a_failed_read_leaves_neither_the_scope_nor_its_frames_holding_an_earlier_reads_rows() -> (
    None
):
    written, stored = _three()
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    traced.fail[2] = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")
    bindings = _bindings(written, traced.acquire)
    with pytest.raises(DatabaseError) as raised, bindings:
        for _each in bindings:
            pass
    # The first read's rows of the second range waited for the second read.
    partial = [rows for rows in traced.answers if rows.key(0) == 2]
    assert partial
    owned = _binding_frames(raised.value)
    assert owned
    assert not any(reaches([bindings, *owned], rows) for rows in partial)


def test_a_failed_completion_leaves_neither_the_scope_nor_its_frames_holding_an_earlier_one() -> (
    None
):
    first, first_row = covered_target(ShareCols, 1)
    second, second_row = covered_target(ShareCols, 2)
    traced = _Traced(HeldRows(MODEL, [first_row, second_row], overlapping=True))
    refused = _Refused()

    def acquire[Request: RowRequest, Result](
        request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        if isinstance(request, CompletionRequest) and request.rows[0][0] == 2:
            raise refused
        return traced.acquire(request, consumer)

    bindings = _bindings(_span(plan([first, second], concurrency="locking")), acquire)
    with pytest.raises(_Refused) as raised, bindings:
        next(bindings)
    assert len(traced.answers) == 1
    owned = _binding_frames(raised.value)
    assert owned
    assert not reaches([bindings, *owned], traced.answers[0])


def test_a_failed_handoff_leaves_neither_the_scope_nor_its_frames_holding_the_reads_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collect = ranges_module._collect  # pyright: ignore[reportPrivateUsage] - the handoff of one object's rows
    handed: list[int] = []

    def collecting(pending: Any, rows: PredecessorRows | None) -> None:
        handed.append(1)
        if len(handed) == 2:
            raise _Refused
        collect(pending, rows)

    monkeypatch.setattr(ranges_module, "_collect", collecting)
    written, stored = _three()
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    bindings = _bindings(written, traced.acquire)
    with pytest.raises(_Refused) as raised, bindings:
        next(bindings)
    owned = _binding_frames(raised.value)
    assert owned
    assert not any(reaches([bindings, *owned], rows) for rows in traced.answers)


def test_a_failed_binding_leaves_neither_the_scope_nor_its_frames_holding_the_reads_rows() -> None:
    written = _span(plan([*frag(ShareCols, 1, 1), covered_target(ShareCols, 2)[0]]))
    start = rectangle(ShareCols, 2, 0, None, 0)
    traced = _Traced(HeldRows(MODEL, [*frag_rows(ShareCols, 1, 1), start, start], overlapping=True))
    bindings = _bindings(written, traced.acquire)
    with raises_code(InternalError, CARDINALITY_CORRUPTION) as raised, bindings:
        for _each in bindings:
            pass
    waiting = [rows for rows in traced.answers if rows.key(0) == 2]
    owned = _binding_frames(raised.value)
    assert waiting and owned
    assert not any(reaches([bindings, *owned], rows) for rows in waiting)


def test_a_later_writes_failed_binding_leaves_no_frame_holding_the_earlier_bound_write(
    recorded: _Bound,
) -> None:
    bound: list[BoundRange] = []

    def binding(*arguments: Any, **keywords: Any) -> BoundRange:
        bound.append(recorded(*arguments, **keywords))
        return bound[-1]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ranges_module, "_bind_range", binding)
        written = _span(plan([*frag(ShareCols, 1, 1), covered_target(ShareCols, 2)[0]]))
        start = rectangle(ShareCols, 2, 0, None, 0)
        held = HeldRows(MODEL, [*frag_rows(ShareCols, 1, 1), start, start], overlapping=True)
        bindings = _bindings(written, held)
        with raises_code(InternalError, CARDINALITY_CORRUPTION) as raised, bindings:
            next(bindings)
    (earlier,) = bound
    # The earlier write was bound and handed to the group being assembled;
    # neither the assembly, the producer, nor the scope keeps it.
    owned = [
        *_binding_frames(raised.value),
        *frames(raised.value.__traceback__, module=plan_module.__file__),
    ]
    assert any(frame.f_code.co_name == "from_members" for frame in owned)
    assert not reaches([bindings, *owned], earlier)


def test_a_deferred_write_a_planned_write_separates_binds_in_a_span_of_its_own() -> None:
    planned = plan([*frag(ShareCols, 1, 1), _inside_write(), *frag(ShareCols, 2, 1)])
    first, group, last = planned.turns
    assert isinstance(group, WriteGroup)
    for span in (first, last):
        assert isinstance(span, AcquisitionSpan) and len(span.ranges) == 1
    assert isinstance(last, AcquisitionSpan)
    held = HeldRows(MODEL, frag_rows(ShareCols, 2, 1), overlapping=True)
    with _span_bindings(last, held) as bindings:
        (bound,) = bindings
    assert _keys(bound) == (2,)
    assert len(held.requests) == 1


def _inside_write() -> AdmittedWrite:
    """A write of object 9 its observation covers, so it binds at planning."""
    observed = rectangle(ShareCols, 9, 0, None, 0)
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "amendUntil", ShareCols.identity.canonical, ({"id": 9, "amount": 9},), day(0), day(1)
        ),
        write_preparation_of(MODEL),
    )
    held = observation(ShareCols, observed)
    return admitted_write(prepared, held, held.key.object)


# --------------------------------------------------------------------------- #
# Transaction-Time-Only ranges: each one part, its current row.               #
# --------------------------------------------------------------------------- #
class ShareLog(TxTemporal, table="share_log", namespace="parallax.execution.shared"):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]


_LOG_MODEL = model_of(DomainModel(ShareLog))


def _log_row(key: int) -> PredecessorRow:
    """Object ``key``'s current row, known from ``T0``."""
    return PredecessorRow(members={"id": key, "amount": key, "txStart": T0, "txEnd": INFINITY})


def _log_target(key: int, *, covered: bool = False) -> TargetWrite:
    """A target write of object ``key`` stating ``T0``, beside, where
    ``covered``, the current row its Locking acquisition retained."""
    prepared = prepare_wire_write(
        TargetWriteInstruction(
            "amend", ShareLog.identity.canonical, {"id": key, "amount": 7}, if_tx_start=T0
        ),
        write_preparation_of(_LOG_MODEL),
    )
    assert isinstance(prepared, PreparedTargetInstruction)
    families = inheritance_facet_of(_LOG_MODEL)
    write = target_write(prepared, families)
    if not covered:
        return write
    view = families.entity(ShareLog.identity)
    shape = temporal_facet_of(_LOG_MODEL).shape(ShareLog.identity)
    assert view is not None and shape is not None
    stored = _log_row(key)
    state = TemporalObjectStateKey(
        ObjectKey(ShareLog.identity, (("id", key),)), milestone_edge(shape, stored, None)
    )
    row = positional_row(view.member_selection.shape, stored.members, absent=ABSENT)
    return replace(write, retained=RetainedTargetState(state, 0, row, None))


def _log_plan(
    writes: Sequence[AdmittedWrite], *, concurrency: ConcurrencyPreference = "optimistic"
) -> WritePlan:
    return build_write_planner(bound_model(_LOG_MODEL)).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at(AT.isoformat()),
            preference=concurrency,
            composed_writes=admitted_writes(_LOG_MODEL, list(writes)),
        )
    )


def _closed(bound: BoundRange) -> tuple[object, ...]:
    (close,) = (step for step in bound.steps if isinstance(step, PlannedClose))
    assert isinstance(close.target, MilestoneTarget)
    return close.target.key_values


def test_transaction_time_only_ranges_share_one_read_naming_each_current_row_once(
    recorded: _Bound,
) -> None:
    written = _span(_log_plan([_log_target(key) for key in (1, 2, 3)]))
    # The rows arrive in another order than the read names their objects.
    traced = _Traced(
        HeldRows(_LOG_MODEL, [_log_row(3), _log_row(1), _log_row(2)], overlapping=True)
    )
    shared = _members(_drained(_bindings(written, traced.acquire, _LOG_MODEL), traced.trace))
    assert traced.trace == [("read", ((1, 1), (2, 1), (3, 1))), ("bind", (1, 2, 3))]
    assert [_closed(bound) for bound in shared] == [(1,), (2,), (3,)]
    assert [(key, len(acquired)) for key, _reused, acquired in recorded.calls] == [
        (1, 1),
        (2, 1),
        (3, 1),
    ]
    alone = _members(
        _drained(
            _bindings(
                _log_plan([_log_target(2)]),
                HeldRows(_LOG_MODEL, [_log_row(2)], overlapping=True),
                _LOG_MODEL,
            ),
            [],
        )
    )
    assert shared[1].steps == alone[0].steps


def test_a_covered_range_needs_no_read_and_never_passes_an_uncovered_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ranges_module, "_PARTS_PER_READ", 1)
    writes = [
        _log_target(1, covered=True),
        _log_target(2),
        _log_target(3, covered=True),
        _log_target(4),
    ]
    written = _span(_log_plan(writes, concurrency="locking"))
    traced = _Traced(HeldRows(_LOG_MODEL, [_log_row(2), _log_row(4)], overlapping=True))
    _drained(_bindings(written, traced.acquire, _LOG_MODEL), traced.trace)
    # The covered first range runs before anything is read; the covered third
    # runs with the second once its read succeeded, before the fourth is read.
    assert traced.trace == [
        ("complete", (1,)),
        ("complete", (3,)),
        ("bind", (1,)),
        ("read", ((2, 1),)),
        ("bind", (2, 3)),
        ("read", ((4, 1),)),
        ("bind", (4,)),
    ]


@pytest.mark.parametrize(
    ("bound", "reads"),
    [(1, [(1,), (2,), (3,)]), (2, [(1, 2), (3,)]), (3, [(1, 2, 3)])],
    ids=["one-per-read", "two-per-read", "all-in-one-read"],
)
def test_each_current_row_takes_one_part_of_a_reads_bound(
    monkeypatch: pytest.MonkeyPatch, bound: int, reads: list[tuple[int, ...]]
) -> None:
    monkeypatch.setattr(ranges_module, "_PARTS_PER_READ", bound)
    written = _span(_log_plan([_log_target(key) for key in (1, 2, 3)]))
    traced = _Traced(HeldRows(_LOG_MODEL, [_log_row(key) for key in (1, 2, 3)], overlapping=True))
    shared = _members(_drained(_bindings(written, traced.acquire, _LOG_MODEL), traced.trace))
    named = [terms for kind, terms in traced.trace if kind == "read"]
    assert named == [tuple((key, 1) for key in keys) for keys in reads]
    assert [_closed(each) for each in shared] == [(1,), (2,), (3,)]


def test_a_range_its_read_found_nothing_for_is_ready_and_binds_to_no_row() -> None:
    written = _span(_log_plan([_log_target(1), _log_target(2)]))
    traced = _Traced(HeldRows(_LOG_MODEL, [_log_row(1)], overlapping=True))
    with (
        raises_code(WritePreconditionError, WRITE_PRECONDITION_FAILED) as failed,
        _bindings(written, traced.acquire, _LOG_MODEL) as bindings,
    ):
        next(bindings)
    # One read named both objects; the second, ready once it succeeded, bound
    # to the absence of its row and failed as its caller's precondition.
    assert traced.trace == [("read", ((1, 1), (2, 1)))]
    assert "key={'id': 2}" in str(failed.value)


def test_a_failed_read_binds_no_range_still_waiting_for_it(
    monkeypatch: pytest.MonkeyPatch, recorded: _Bound
) -> None:
    monkeypatch.setattr(ranges_module, "_PARTS_PER_READ", 1)
    written = _span(_log_plan([_log_target(1), _log_target(2)]))
    traced = _Traced(HeldRows(_LOG_MODEL, [_log_row(1), _log_row(2)], overlapping=True))
    traced.fail[2] = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")
    with pytest.raises(DatabaseError), _bindings(written, traced.acquire, _LOG_MODEL) as bindings:
        for each in bindings:
            traced.trace.append(("bind", _keys(each)))
    assert traced.trace == [("read", ((1, 1),)), ("bind", (1,)), ("read", ((2, 1),))]
    assert [key for key, _reused, _acquired in recorded.calls] == [1]
