"""The deferred ranges of one acquisition span bound through one scoped
binding (`m-unit-work` *Shared coverage acquisition*), over the in-memory
acquisition: their coverage read in shared reads packed in range and
Valid-Time order, each range ready once every read naming its parts
succeeded, and each bound only when the flush advances to it."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from types import FrameType
from typing import Any, cast

import pytest

from parallax.core import Bitemporal
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import ranges as ranges_module
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    CompletionRequest,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
)
from parallax.core._execution._unit_work.instructions import prepare_wire_write
from parallax.core._execution._unit_work.ranges import DeferredTemporalRange, RangeBindings
from parallax.core._execution._unit_work.write_items import AdmittedWrite
from parallax.core.db_error import DatabaseError
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    Concurrency,
    KeyedWriteInstruction,
    buffered_write,
)
from parallax.core.write_plan import PredecessorRow, PredecessorRows
from parallax.core.write_plan.keys import ObjectStateKey, TemporalObjectStateKey
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    AcquisitionSpan,
    BoundRange,
    WritePlan,
)
from parallax.core.write_plan.steps import PlannedClose, PlannedInsert, PlannedStep
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit.core._execution._reach_support import frames, reaches
from tests.unit.core._execution._shared_coverage_support import (
    AT,
    MODEL,
    ShareCols,
    ShareDoc,
    covered_target,
    day,
    frag,
    frag_rows,
    observation,
    plan,
    ranges_of,
    rectangle,
)
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows

_BIND_RANGE = ranges_module._bind_range  # pyright: ignore[reportPrivateUsage] - the binding every deferred range takes


def _always(state: ObjectStateKey, read_at: int) -> bool:
    del state, read_at
    return True


def _never(state: ObjectStateKey, read_at: int) -> bool:
    del state, read_at
    return False


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
                tuple((term.key_value, len(term.valid_time_windows)) for term in request.terms),
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


def _bindings(
    ranges: tuple[DeferredTemporalRange, ...],
    acquire: AcquireRows,
    *,
    current: Callable[[ObjectStateKey, int], bool] = _always,
) -> RangeBindings:
    planner = build_write_planner(MODEL)
    return RangeBindings(
        ranges,
        acquire_rows=acquire,
        current=current,
        ownership=NO_TEMPORAL_WRITE_OWNERSHIP,
        audit=planner.audit_decoration(
            actor_identity=TEST_ACTOR_IDENTITY, transaction_instant=instant_at(AT.isoformat())
        ),
        payloads=planner.payloads,
    )


def _key(bound: BoundRange) -> object:
    state = next(iter(bound.changed))
    assert isinstance(state, TemporalObjectStateKey)
    ((_name, value),) = state.object.primary_key
    return value


def _drained(bindings: RangeBindings, trace: list[tuple[str, tuple[Any, ...]]]) -> list[BoundRange]:
    bound: list[BoundRange] = []
    with bindings:
        for each in bindings:
            trace.append(("bind", (_key(each),)))
            bound.append(each)
    return bound


def _span(written: WritePlan) -> tuple[DeferredTemporalRange, ...]:
    assert written.acquisition_spans == (AcquisitionSpan(0, len(written.groups)),)
    return ranges_of(written)


def _fragmented(
    entity: type[Bitemporal], parts: Sequence[int], *, concurrency: Concurrency = "optimistic"
) -> tuple[tuple[DeferredTemporalRange, ...], list[PredecessorRow]]:
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
        deferred: DeferredTemporalRange,
        reused: PredecessorRows | None,
        acquired: Sequence[PredecessorRows],
        **keywords: Any,
    ) -> BoundRange:
        self.calls.append((deferred.meaning.key_value, reused, tuple(acquired)))
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
    ranges = _span(plan(writes, concurrency="locking"))
    bound = _drained(_bindings(ranges, traced.acquire), traced.trace)
    # Readiness [0, 2, 0, 2]: the first binds before any read, and the third
    # waits behind the second's two reads.
    assert traced.trace == [
        ("complete", (1,)),
        ("complete", (3,)),
        ("bind", (1,)),
        ("read", ((2, 64),)),
        ("read", ((2, 1), (4, 1))),
        ("bind", (2,)),
        ("bind", (3,)),
        ("bind", (4,)),
    ]
    assert [_key(each) for each in bound] == [1, 2, 3, 4]


def test_a_read_can_finish_one_range_while_it_reads_part_of_the_next(recorded: _Bound) -> None:
    ranges, stored = _fragmented(ShareCols, (33, 33, 1))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    _drained(_bindings(ranges, traced.acquire), traced.trace)
    assert traced.trace == [
        ("read", ((1, 33), (2, 31))),
        ("bind", (1,)),
        ("read", ((2, 2), (3, 1))),
        ("bind", (2,)),
        ("bind", (3,)),
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
        assert written.acquisition_spans == ()
        ranges, stored = ranges_of(written), frag_rows(ShareCols, 1, count)
    else:
        ranges, stored = _fragmented(ShareCols, parts)
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    bound = _drained(_bindings(ranges, traced.acquire), traced.trace)
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
    ranges = _span(plan(writes))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    shared = _drained(_bindings(ranges, traced.acquire), traced.trace)
    assert traced.trace == [("read", ((1, 1), (2, 1))), ("bind", (1,)), ("bind", (2,))]
    alone = _drained(
        _bindings(ranges_of(plan([later])), HeldRows(MODEL, stored, overlapping=True)), []
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
        MODEL,
    )
    return buffered_write(prepared, observation(ShareCols, observed))


def _window(step: PlannedStep) -> tuple[object, object]:
    assert isinstance(step, PlannedInsert)
    (entry,) = step.entries
    cells = {identity.name: value for identity, value in entry.row.attributes.items()}
    return cells["validStart"], cells["validEnd"]


def test_a_span_its_retained_rows_cover_reads_nothing() -> None:
    targets = [covered_target(ShareCols, key) for key in (1, 2, 3)]
    traced = _Traced(HeldRows(MODEL, [row for _write, row in targets], overlapping=True))
    ranges = _span(plan([write for write, _row in targets], concurrency="locking"))
    _drained(_bindings(ranges, traced.acquire), traced.trace)
    assert traced.trace == [
        ("complete", (1,)),
        ("complete", (2,)),
        ("complete", (3,)),
        ("bind", (1,)),
        ("bind", (2,)),
        ("bind", (3,)),
    ]


def test_a_stale_retained_row_is_read_with_the_spans_other_parts() -> None:
    target, stored = covered_target(ShareCols, 1)
    traced = _Traced(HeldRows(MODEL, [stored, *frag_rows(ShareCols, 2, 1)], overlapping=True))
    ranges = _span(plan([target, *frag(ShareCols, 2, 1)], concurrency="locking"))
    _drained(_bindings(ranges, traced.acquire, current=_never), traced.trace)
    assert traced.trace == [("read", ((1, 1), (2, 1))), ("bind", (1,)), ("bind", (2,))]


def test_each_ranges_missing_coverage_is_derived_once_before_anything_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    derive = ranges_module._missing_coverage  # pyright: ignore[reportPrivateUsage] - the derivation each range takes once
    ranges, stored = _fragmented(ShareCols, (33, 33, 1))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    derived: list[int] = []

    def deriving(*arguments: Any) -> Any:
        derived.append(traced.reads)
        return derive(*arguments)

    monkeypatch.setattr(ranges_module, "_missing_coverage", deriving)
    _drained(_bindings(ranges, traced.acquire), traced.trace)
    assert derived == [0, 0, 0]


def test_a_range_is_bound_only_when_the_flush_advances_to_it(recorded: _Bound) -> None:
    ranges, stored = _fragmented(ShareCols, (1, 1, 1))
    held = HeldRows(MODEL, stored, overlapping=True)
    with _bindings(ranges, held) as bindings:
        assert (held.requests, recorded.calls) == ([], [])
        next(bindings)
        # One read serves all three; only the first is bound.
        assert len(held.requests) == 1
        assert [key for key, _reused, _acquired in recorded.calls] == [1]
        next(bindings)
        assert [key for key, _reused, _acquired in recorded.calls] == [1, 2]


# --------------------------------------------------------------------------- #
# Each stored row reaches its own object's binding.                           #
# --------------------------------------------------------------------------- #
def test_interleaved_rows_and_their_documents_reach_the_object_whose_key_each_holds(
    recorded: _Bound,
) -> None:
    first = frag_rows(ShareDoc, 1, 1)
    second = frag_rows(ShareDoc, 2, 2)
    stored = [second[1], first[1], second[3], first[0], second[0], second[2]]
    ranges = _span(plan([*frag(ShareDoc, 1, 1), *frag(ShareDoc, 2, 2)]))
    _drained(_bindings(ranges, HeldRows(MODEL, stored, overlapping=True)), [])
    by_key = {key: acquired for key, _reused, acquired in recorded.calls}
    assert set(by_key) == {1, 2}
    for key, (rows,) in by_key.items():
        documents = [rows.document(index) for index in range(len(rows))]
        assert {rows.key(index) for index in range(len(rows))} == {key}
        assert documents == [
            {"amount": amount, "label": f"k{key}"} for amount in ((1,) if key == 1 else (1, 3))
        ]


def test_a_row_one_read_returns_twice_reaches_its_binding_twice() -> None:
    # An Optimistic target write's caller states the row at its window's start.
    ranges = _span(plan([*frag(ShareCols, 1, 1), covered_target(ShareCols, 2)[0]]))
    start = rectangle(ShareCols, 2, 0, None, 0)
    held = HeldRows(MODEL, [*frag_rows(ShareCols, 1, 1), start, start], overlapping=True)
    with _bindings(ranges, held) as bindings:
        assert _key(next(bindings)) == 1
        with pytest.raises(CardinalityCorruptionError) as corrupt:
            next(bindings)
    assert (corrupt.value.expected, corrupt.value.actual) == (1, 2)


def test_a_row_two_reads_both_return_is_bound_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ranges_module, "_COVERAGE_WINDOWS", 1)
    ranges, stored = _fragmented(ShareCols, (1, 2))
    traced = _Traced(_KeyedRows(stored))
    shared = _drained(_bindings(ranges, traced.acquire), traced.trace)
    assert [entry for entry in traced.trace if entry[0] == "read"] == [
        ("read", ((1, 1),)),
        ("read", ((2, 1),)),
        ("read", ((2, 1),)),
    ]
    alone = _drained(
        _bindings(ranges[1:], HeldRows(MODEL, frag_rows(ShareCols, 2, 2), overlapping=True)), []
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

    ranges = _span(plan([first, *frag(ShareCols, 3, 1), second], concurrency="locking"))
    with pytest.raises(_Refused) as raised, _bindings(ranges, acquire) as bindings:
        next(bindings)
    assert raised.value is refused
    assert recorded.calls == []
    assert [type(request) for request in held.requests] == [CompletionRequest]


def test_a_ready_ranges_binding_precedes_the_read_its_successor_waits_for() -> None:
    ranges, stored = _fragmented(ShareCols, (1, 64))
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    traced.fail[2] = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")
    bound: list[object] = []
    with pytest.raises(DatabaseError), _bindings(ranges, traced.acquire) as bindings:
        for each in bindings:
            bound.append(_key(each))
    assert bound == [1]
    assert [entry[0] for entry in traced.trace] == ["read", "read"]


# --------------------------------------------------------------------------- #
# However the scope ends, it holds none of the rows it read.                  #
# --------------------------------------------------------------------------- #
def _binding_frames(failure: BaseException) -> list[FrameType]:
    return [
        frame
        for frame in frames(failure.__traceback__, module=ranges_module.__file__)
        if frame.f_code.co_qualname.startswith((f"{RangeBindings.__name__}.", "_transfer"))
    ]


def _three() -> tuple[tuple[DeferredTemporalRange, ...], list[PredecessorRow]]:
    """A span whose first read finishes the first range and reads part of the
    second, and whose second read finishes the second and the third."""
    return _fragmented(ShareCols, (1, 64, 1))


@pytest.mark.parametrize("leaves", ["exhaustion", "break", "raise"])
def test_a_scope_left_any_way_holds_none_of_the_rows_it_read(leaves: str) -> None:
    ranges, stored = _three()
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    bindings = _bindings(ranges, traced.acquire)
    bound: list[BoundRange] = []
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
    # What the bound ranges carry is the flush's, and stays usable.
    assert all(sum(isinstance(step, PlannedClose) for step in each.steps) for each in bound)


def test_a_failed_read_leaves_neither_the_scope_nor_its_frames_holding_an_earlier_reads_rows() -> (
    None
):
    ranges, stored = _three()
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    traced.fail[2] = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")
    bindings = _bindings(ranges, traced.acquire)
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
    ranges, stored = _three()
    traced = _Traced(HeldRows(MODEL, stored, overlapping=True))
    bindings = _bindings(ranges, traced.acquire)
    with pytest.raises(_Refused) as raised, bindings:
        next(bindings)
    owned = _binding_frames(raised.value)
    assert owned
    assert not any(reaches([bindings, *owned], rows) for rows in traced.answers)


def test_a_failed_binding_leaves_neither_the_scope_nor_its_frames_holding_the_reads_rows() -> None:
    ranges = _span(plan([*frag(ShareCols, 1, 1), covered_target(ShareCols, 2)[0]]))
    start = rectangle(ShareCols, 2, 0, None, 0)
    traced = _Traced(HeldRows(MODEL, [*frag_rows(ShareCols, 1, 1), start, start], overlapping=True))
    bindings = _bindings(ranges, traced.acquire)
    with pytest.raises(CardinalityCorruptionError) as raised, bindings:
        for _each in bindings:
            pass
    waiting = [rows for rows in traced.answers if rows.key(0) == 2]
    owned = _binding_frames(raised.value)
    assert waiting and owned
    assert not any(reaches([bindings, *owned], rows) for rows in waiting)
