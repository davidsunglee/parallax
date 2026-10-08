"""What a caller-addressed range does with the starting rows its Locking
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
from parallax.core.base import INFINITY
from parallax.core.entity._construction_input import ABSENT
from parallax.core.execution._planning import build_write_planner
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import RetainedObservation, WritePlanningRequest
from parallax.core.unit_work import ranges as ranges_module
from parallax.core.unit_work.acquisition import CompletionRequest, CoverageReadRequest
from parallax.core.unit_work.materialized import BufferItem, TargetKeyedWrite, chained
from parallax.core.unit_work.ranges import DeferredTemporalRange
from parallax.core.unit_work.retain import RetainedTargetState
from parallax.core.unit_work.uow import bind_deferred_range
from parallax.core.unit_work.write_planner import compose_writes
from parallax.core.write_plan import PlannedClose, PlannedInsert, PredecessorRow
from parallax.core.write_plan.keys import ObservedStateKey, TemporalStateKey
from parallax.core.write_plan.plan import NO_TEMPORAL_WRITE_OWNERSHIP, BoundRange, ExecutionUnit
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._positional_row_support import positional_row
from tests.unit.core.unit_work._acquired_rows_support import HeldRows
from tests.unit.core.unit_work._temporal_targets_support import (
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


def _state(predecessor: PredecessorRow) -> TemporalStateKey:
    state = retained(predecessor).key
    assert isinstance(state, TemporalStateKey)
    return state


def _holding(item: TargetKeyedWrite, state: RetainedTargetState) -> TargetKeyedWrite:
    return dataclasses.replace(item, retained=state)


def _unit(
    *writes: BufferItem, concurrency: str = "locking", follows: bool = False
) -> ExecutionUnit:
    buffered = compose_writes(POSITION, list(writes))
    if follows:
        (composed,) = buffered
        assert not isinstance(composed, RetainedObservation)
        buffered = [chained(composed, "id", follows=True)]  # type: ignore[arg-type]
    plan = build_write_planner(POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=_INSTANT,
            concurrency=concurrency,  # type: ignore[arg-type]
            buffered_writes=tuple(buffered),
        )
    )
    (unit,) = plan.units
    assert isinstance(unit.deferred, DeferredTemporalRange)
    return unit


def _always(state: ObservedStateKey, read_at: int) -> bool:
    del state, read_at
    return True


def _bind(
    unit: ExecutionUnit,
    stored: Sequence[PredecessorRow],
    *,
    current: Callable[[ObservedStateKey, int], bool] = _always,
) -> tuple[BoundRange, HeldRows]:
    deferred = unit.deferred
    assert isinstance(deferred, DeferredTemporalRange)
    held = HeldRows(POSITION, stored, overlapping=True)
    bound = bind_deferred_range(
        deferred,
        acquire_rows=held,
        planner=build_write_planner(POSITION),
        ownership=NO_TEMPORAL_WRITE_OWNERSHIP,
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=_INSTANT,
        current=current,
    )
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
        request.valid_time_windows
        for request in held.requests
        if isinstance(request, CoverageReadRequest)
    ]


_START = rectangle(JAN, JUN, "100.00")
_LATER = rectangle(JUN, INFINITY, "200.00")


def test_a_current_retained_row_covering_the_window_is_reused_without_a_read() -> None:
    state = _held(_START)
    unit = _unit(_holding(addressed_write(until=MAY, value="150.00"), state))
    bound, held = _bind(unit, [_START])
    (completion,) = held.requests
    assert isinstance(completion, CompletionRequest)
    assert len([step for step in bound.steps if isinstance(step, PlannedClose)]) == 1
    assert [window[:2] for window in _windows(bound)] == [(JAN, MAR), (MAR, MAY), (MAY, JUN)]
    # The row is handed over once: its state holds nothing of it afterwards.
    assert state.take() is None


def test_only_the_coverage_a_retained_row_leaves_is_read() -> None:
    unit = _unit(_holding(addressed_write(value="150.00"), _held(_START)))
    bound, held = _bind(unit, [_START, _LATER])
    assert isinstance(held.requests[0], CompletionRequest)
    assert _coverage_windows(held) == [(TimeInterval(JUN, SEP),)]
    assert [window[:2] for window in _windows(bound)] == [
        (JAN, MAR),
        (MAR, JUN),
        (JUN, SEP),
        (SEP, INFINITY),
    ]


def test_a_row_two_reads_both_return_is_bound_once() -> None:
    # The in-memory acquisition answers the reused row to the coverage read too;
    # the same physical state is one original, not cardinality corruption.
    unit = _unit(_holding(addressed_write(value="150.00"), _held(_START)))
    held_rows = HeldRows(POSITION, [_START, _LATER])
    deferred = unit.deferred
    assert isinstance(deferred, DeferredTemporalRange)
    bound = bind_deferred_range(
        deferred,
        acquire_rows=held_rows,
        planner=build_write_planner(POSITION),
        ownership=NO_TEMPORAL_WRITE_OWNERSHIP,
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=_INSTANT,
        current=_always,
    )
    closes = [step for step in bound.steps if isinstance(step, PlannedClose)]
    assert len(closes) == 2


@pytest.mark.parametrize("replaces", [False, True], ids=["amendment", "replacement"])
def test_a_part_a_read_finds_empty_is_a_gap_and_is_read_once(replaces: bool) -> None:
    unit = _unit(
        _holding(addressed_write(replaces=replaces, value="150.00", acctNum="Z"), _held(_START))
    )
    bound, held = _bind(unit, [_START])
    assert len(_coverage_windows(held)) == 1
    windows = [window[:2] for window in _windows(bound)]
    assert windows == [(JAN, MAR), (MAR, JUN), *([(JUN, SEP)] if replaces else [])]


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
    monkeypatch.setattr(ranges_module, "_COVERAGE_TERMS", terms)
    unit = _unit(*_two_starts())
    bound, held = _bind(unit, [_EARLY, _MIDDLE, _CENTRE, _LATE])
    parts = (TimeInterval(MAR, MAY), TimeInterval(JUL, AUG))
    assert _coverage_windows(held) == ([parts] if terms > 1 else [(part,) for part in parts])
    # The rectangle between the two windows is read, and left as it stands.
    closed = [step for step in bound.steps if isinstance(step, PlannedClose)]
    assert len(closed) == 3


def test_a_stale_retained_row_is_discarded_unjudged_and_its_coverage_read() -> None:
    stale = _held(_START, read_at=1)
    unit = _unit(_holding(addressed_write(value="150.00"), stale))
    judged: list[int] = []

    def current(state: ObservedStateKey, read_at: int) -> bool:
        judged.append(read_at)
        return False

    _bound, held = _bind(unit, [_START, _LATER], current=current)
    assert judged == [1]
    assert not any(isinstance(request, CompletionRequest) for request in held.requests)
    assert _coverage_windows(held) == [(TimeInterval(MAR, SEP),)]
    assert stale.take() is None


def test_an_optimistic_range_reuses_no_retained_row() -> None:
    state = _held(_START)
    unit = _unit(_holding(addressed_write(value="150.00"), state), concurrency="optimistic")
    _bound, held = _bind(unit, [_START, _LATER])
    assert not any(isinstance(request, CompletionRequest) for request in held.requests)
    assert _coverage_windows(held) == [(TimeInterval(MAR, SEP),)]
    assert state.take() is None


def test_a_range_after_a_barrier_reuses_a_current_row_and_reads_the_rest() -> None:
    unit = _unit(_holding(addressed_write(value="150.00"), _held(_START)), follows=True)
    bound, held = _bind(unit, [_START, _LATER])
    assert isinstance(held.requests[0], CompletionRequest)
    assert _coverage_windows(held) == [(TimeInterval(JUN, SEP),)]
    assert _windows(bound)[0][:2] == (JAN, MAR)


def test_a_retained_row_is_released_by_a_range_that_binds_twice() -> None:
    state = _held(_START)
    unit = _unit(_holding(addressed_write(value="150.00"), state))
    _bind(unit, [_START, _LATER])
    # A second binding of the same description finds nothing retained, so it
    # reads its whole window rather than reusing what the first one consumed.
    _bound, held = _bind(unit, [_START, _LATER])
    assert _coverage_windows(held) == [(TimeInterval(MAR, SEP),)]


def test_a_retained_row_is_completed_as_one_original_beside_an_observed_one() -> None:
    # A retained row whose state an observed original already is joins nothing.
    observed = retained(_START)
    state = RetainedTargetState(
        _state(_START), 0, positional_row(_SHAPE, _START.members, absent=ABSENT), None
    )
    unit = _unit(
        _holding(addressed_write(valid_from=APR, value="150.00"), state),
        observed_write("amendUntil", observed, valid_from=APR, until=SEP, value="150.00"),
    )
    _bound, held = _bind(unit, [_START, _LATER])
    assert not any(isinstance(request, CompletionRequest) for request in held.requests)
    assert state.take() is None


def test_without_a_freshness_judge_every_retained_row_is_discarded() -> None:
    state = _held(_START)
    unit = _unit(_holding(addressed_write(value="150.00"), state))
    deferred = unit.deferred
    assert isinstance(deferred, DeferredTemporalRange)
    held = HeldRows(POSITION, [_START, _LATER], overlapping=True)
    bind_deferred_range(
        deferred,
        acquire_rows=held,
        planner=build_write_planner(POSITION),
        ownership=NO_TEMPORAL_WRITE_OWNERSHIP,
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=_INSTANT,
    )
    assert _coverage_windows(held) == [(TimeInterval(MAR, SEP),)]
    assert state.take() is None
