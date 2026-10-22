"""What a target range does with the starting rows its Locking
acquisitions retained (`m-unit-work` *Retained starting rows*), driven through
the unit of work's own binding over an in-memory acquisition: a current row is
completed and reused without a read, only the coverage nothing held is read, a
stale row is discarded unjudged, and each retained row is released however its
range treats it."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence

import pytest

from parallax.core import inheritance
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import ranges as ranges_module
from parallax.core._execution._unit_work.acquisition import (
    CompletionRequest,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
)
from parallax.core._execution._unit_work.ranges import DeferredTemporalRange, RangeBindings
from parallax.core._execution._unit_work.retain import RetainedTargetState
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    TargetKeyedWrite,
)
from parallax.core.base import INFINITY
from parallax.core.entity._construction_input import ABSENT
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import WritePlanningRequest
from parallax.core.write_plan import PlannedClose, PlannedInsert, PredecessorRow
from parallax.core.write_plan.keys import ObjectStateKey, TemporalObjectStateKey
from parallax.core.write_plan.plan import BoundRange, SettledWrite
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, admitted_writes, settled_writes
from tests.unit._positional_row_support import positional_row
from tests.unit.core._execution._reach_support import frames, reaches
from tests.unit.core._execution._unit_work._acquired_rows_support import (
    HeldRows,
    bind_deferred,
    range_bindings,
)
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    APR,
    AUG,
    FEB,
    JAN,
    JUL,
    JUN,
    MAR,
    MAY,
    POSITION,
    SEP,
    addressed_write,
    observed_write,
    rectangle,
    retained,
)

_INSTANT = instant_at("2024-10-01T00:00:00+00:00")
_VIEW = inheritance.view(POSITION).entity(addressed_write().instruction.target.identity)
assert _VIEW is not None
_SHAPE = _VIEW.member_selection.shape


def _held(predecessor: PredecessorRow, *, read_at: int = 0) -> RetainedTargetState:
    """``predecessor`` as a Locking acquisition retained it."""
    row = positional_row(_SHAPE, predecessor.members, absent=ABSENT)
    return RetainedTargetState(_state(predecessor), read_at, row, None)


def _state(predecessor: PredecessorRow) -> TemporalObjectStateKey:
    state = retained(predecessor).key
    assert isinstance(state, TemporalObjectStateKey)
    return state


def _holding(item: TargetKeyedWrite, state: RetainedTargetState) -> TargetKeyedWrite:
    return dataclasses.replace(item, retained=state)


def _planned(*writes: AdmittedWrite, concurrency: str = "locking") -> SettledWrite:
    buffered = admitted_writes(POSITION, list(writes))
    plan = build_write_planner(POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_INSTANT,
            concurrency=concurrency,  # type: ignore[arg-type]
            buffered_writes=tuple(buffered),
        )
    )
    (write,) = settled_writes(plan)
    return write


def _settled(*writes: AdmittedWrite, concurrency: str = "locking") -> SettledWrite:
    settled = _planned(*writes, concurrency=concurrency)
    assert isinstance(settled.deferred, DeferredTemporalRange)
    return settled


def _always(state: ObjectStateKey, read_at: int) -> bool:
    del state, read_at
    return True


def _bind(
    settled: SettledWrite,
    stored: Sequence[PredecessorRow],
    *,
    current: Callable[[ObjectStateKey, int], bool] = _always,
) -> tuple[BoundRange, HeldRows]:
    deferred = settled.deferred
    assert isinstance(deferred, DeferredTemporalRange)
    held = HeldRows(POSITION, stored, overlapping=True)
    bound = bind_deferred(POSITION, deferred, held, transaction_instant=_INSTANT, current=current)
    return bound, held


def _windows(bound: BoundRange) -> list[tuple[object, object, object]]:
    windows: list[tuple[object, object, object]] = []
    for step in bound.steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            windows.append((cells["validStart"], cells["validEnd"], cells["value"]))
    return windows


def _coverage_windows(held: HeldRows) -> list[tuple[TimeInterval, ...]]:
    return [
        request.terms[0].valid_time_windows
        for request in held.requests
        if isinstance(request, CoverageReadRequest)
    ]


_START = rectangle(JAN, JUN, "100.00")
_LATER = rectangle(JUN, INFINITY, "200.00")


def test_a_current_retained_row_covering_the_window_is_reused_without_a_read() -> None:
    state = _held(_START)
    settled = _settled(_holding(addressed_write(until=MAY, value="150.00"), state))
    bound, held = _bind(settled, [_START])
    (completion,) = held.requests
    assert isinstance(completion, CompletionRequest)
    assert len([step for step in bound.steps if isinstance(step, PlannedClose)]) == 1
    assert [window[:2] for window in _windows(bound)] == [(JAN, MAR), (MAR, MAY), (MAY, JUN)]
    # The row is handed over once: its state holds nothing of it afterwards.
    assert state.take() is None


def test_only_the_coverage_a_retained_row_leaves_is_read() -> None:
    settled = _settled(_holding(addressed_write(value="150.00"), _held(_START)))
    bound, held = _bind(settled, [_START, _LATER])
    assert isinstance(held.requests[0], CompletionRequest)
    assert _coverage_windows(held) == [(TimeInterval(JUN, SEP),)]
    # The equal changed parts of the reused row and the row read merge.
    assert [window[:2] for window in _windows(bound)] == [
        (JAN, MAR),
        (MAR, SEP),
        (SEP, INFINITY),
    ]


def test_a_row_two_reads_both_return_is_bound_once() -> None:
    # The in-memory acquisition answers the reused row to the coverage read too;
    # the same physical state is one original, not cardinality corruption.
    settled = _settled(_holding(addressed_write(value="150.00"), _held(_START)))
    held_rows = HeldRows(POSITION, [_START, _LATER])
    deferred = settled.deferred
    assert isinstance(deferred, DeferredTemporalRange)
    bound = bind_deferred(
        POSITION, deferred, held_rows, transaction_instant=_INSTANT, current=_always
    )
    closes = [step for step in bound.steps if isinstance(step, PlannedClose)]
    assert len(closes) == 2


def test_overlapping_rows_one_read_returns_beside_a_reused_row_are_each_bound() -> None:
    # Two current rows sharing a start on both axes are distinct physical rows.
    ending = rectangle(JUN, SEP, "200.00")
    unbounded = rectangle(JUN, INFINITY, "300.00")
    settled = _settled(_holding(addressed_write(value="150.00"), _held(_START)))
    bound, held = _bind(settled, [_START, ending, unbounded])
    assert _coverage_windows(held) == [(TimeInterval(JUN, SEP),)]
    closes = [step for step in bound.steps if isinstance(step, PlannedClose)]
    assert len(closes) == 3


@pytest.mark.parametrize("replaces", [False, True], ids=["amendment", "replacement"])
def test_a_part_a_read_finds_empty_is_a_gap_and_is_read_once(replaces: bool) -> None:
    settled = _settled(
        _holding(addressed_write(replaces=replaces, value="150.00", acctNum="Z"), _held(_START))
    )
    bound, held = _bind(settled, [_START])
    assert len(_coverage_windows(held)) == 1
    windows = [window[:2] for window in _windows(bound)]
    # A replacement's gap opens its complete state, which the changed part
    # before it already holds, so the two are one row.
    assert windows == [(JAN, MAR), (MAR, SEP if replaces else JUN)]


_EARLY = rectangle(JAN, MAR, "100.00")
_MIDDLE = rectangle(MAR, MAY, "200.00")
_CENTRE = rectangle(MAY, JUL, "300.00")
_LATE = rectangle(JUL, INFINITY, "400.00")


def _two_starts() -> tuple[TargetKeyedWrite, TargetKeyedWrite]:
    return (
        _holding(addressed_write(valid_from=FEB, until=MAR, value="150.00"), _held(_EARLY)),
        _holding(addressed_write(valid_from=JUN, until=AUG, value="175.00"), _held(_CENTRE)),
    )


@pytest.mark.parametrize("terms", [2, 1], ids=["one-read", "one-read-per-part"])
def test_the_parts_retained_rows_leave_are_read_in_reads_of_bounded_terms(
    monkeypatch: pytest.MonkeyPatch, terms: int
) -> None:
    monkeypatch.setattr(ranges_module, "_COVERAGE_WINDOWS", terms)
    settled = _settled(*_two_starts())
    bound, held = _bind(settled, [_EARLY, _MIDDLE, _CENTRE, _LATE])
    parts = (TimeInterval(MAR, MAY), TimeInterval(JUL, AUG))
    assert _coverage_windows(held) == ([parts] if terms > 1 else [(part,) for part in parts])
    # The rectangle between the two windows is read, and left as it stands.
    closed = [step for step in bound.steps if isinstance(step, PlannedClose)]
    assert len(closed) == 3


def test_a_stale_retained_row_is_discarded_unjudged_and_its_coverage_read() -> None:
    stale = _held(_START, read_at=1)
    settled = _settled(_holding(addressed_write(value="150.00"), stale))
    judged: list[int] = []

    def current(state: ObjectStateKey, read_at: int) -> bool:
        judged.append(read_at)
        return False

    _bound, held = _bind(settled, [_START, _LATER], current=current)
    assert judged == [1]
    assert not any(isinstance(request, CompletionRequest) for request in held.requests)
    assert _coverage_windows(held) == [(TimeInterval(MAR, SEP),)]
    assert stale.take() is None


def test_an_optimistic_range_reuses_no_retained_row() -> None:
    state = _held(_START)
    settled = _settled(_holding(addressed_write(value="150.00"), state), concurrency="optimistic")
    _bound, held = _bind(settled, [_START, _LATER])
    assert not any(isinstance(request, CompletionRequest) for request in held.requests)
    assert _coverage_windows(held) == [(TimeInterval(MAR, SEP),)]
    assert state.take() is None


def test_a_retained_row_is_released_by_a_range_that_binds_twice() -> None:
    state = _held(_START)
    settled = _settled(_holding(addressed_write(value="150.00"), state))
    _bind(settled, [_START, _LATER])
    # A second binding of the same description finds nothing retained, so it
    # reads its whole window rather than reusing what the first one consumed.
    _bound, held = _bind(settled, [_START, _LATER])
    assert _coverage_windows(held) == [(TimeInterval(MAR, SEP),)]


def test_a_retained_row_is_completed_as_one_original_beside_an_observed_one() -> None:
    # A retained row whose state an observed original already is joins nothing.
    observed = retained(_START)
    state = RetainedTargetState(
        _state(_START), 0, positional_row(_SHAPE, _START.members, absent=ABSENT), None
    )
    settled = _settled(
        _holding(addressed_write(valid_from=APR, value="150.00"), state),
        observed_write("amendUntil", observed, valid_from=APR, until=SEP, value="150.00"),
    )
    _bound, held = _bind(settled, [_START, _LATER])
    assert not any(isinstance(request, CompletionRequest) for request in held.requests)
    assert state.take() is None


def test_a_range_bound_at_planning_releases_the_row_it_retained() -> None:
    whole = rectangle(JAN, INFINITY, "100.00")
    state = _held(whole)
    settled = _planned(
        observed_write("amendUntil", retained(whole), valid_from=MAR, until=APR, value="150.00"),
        _holding(addressed_write(valid_from=APR, until=MAY, value="175.00"), state),
    )
    assert settled.deferred is None
    assert state.take() is None


class _Failed(Exception):
    pass


def test_a_failed_coverage_read_leaves_its_bindings_holding_no_reused_row() -> None:
    settled = _settled(_holding(addressed_write(value="150.00"), _held(_START)))
    deferred = settled.deferred
    assert isinstance(deferred, DeferredTemporalRange)
    held = HeldRows(POSITION, [_START, _LATER], overlapping=True)
    reused: list[object] = []
    failure = _Failed()

    def acquire[Request: RowRequest, Result](
        request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        if isinstance(request, CoverageReadRequest):
            raise failure
        answer = held(request, consumer)
        reused.append(answer)
        return answer

    bindings = range_bindings(
        POSITION, deferred, acquire, transaction_instant=_INSTANT, current=_always
    )
    with pytest.raises(_Failed) as raised, bindings:
        next(bindings)
    # The failure is the read's own, its traceback intact.
    assert raised.value is failure
    owned = [
        frame
        for frame in frames(raised.value.__traceback__, module=ranges_module.__file__)
        if frame.f_code.co_qualname.startswith(f"{RangeBindings.__name__}.")
    ]
    assert owned
    (rows,) = reused
    assert rows is not None
    assert not reaches([bindings, *owned], rows)
    assert next(bindings, None) is None
