"""The Write Plan's own contract (m-write-plan values, `m-unit-work` *Write Plan
and Planned Writes*).

An empty Planned Writes is the one canonical result for a flush that survives
nothing, and Planned Writes is a logical sequence whose views compare by value
rather than by object identity. A borrowed span of it reads only the steps it
spans, once each per pass. A plan's execution units partition its steps in
order, and an attempt that opened nothing owns, proved, and derived nothing.
"""

from __future__ import annotations

import dataclasses

import pytest

from parallax.core.metamodel import AttributeIdentity
from parallax.core.write_plan import PlannedInsert, WritePlan
from parallax.core.write_plan.keys import ObjectKey, VersionedStateKey
from parallax.core.write_plan.plan import (
    NO_OPENINGS,
    NO_TEMPORAL_WRITE_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    DeferredRange,
    ExecutionUnit,
    OwnedEndpoint,
    PlannedWrites,
    UnitEffects,
    WriteStepView,
    eager_segment,
    eager_writes,
)
from parallax.core.write_plan.steps import NEW_LINEAGE, PlannedRow, PlannedWrite, WriteRow
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of

_ACCOUNT = entity_of(corpus_model("account"), "Account").identity
_ID = AttributeIdentity(_ACCOUNT, "id")


def _insert(key: int) -> PlannedInsert:
    return PlannedInsert(
        entity=_ACCOUNT,
        entries=(WriteRow(row=PlannedRow(attributes={_ID: key}), origin=NEW_LINEAGE),),
    )


def test_an_empty_write_plan_is_the_canonical_cancelled_result() -> None:
    plan = WritePlan()
    assert len(plan.steps) == 0
    assert list(plan.steps) == []
    assert plan == WritePlan(steps=PlannedWrites())


def test_planned_steps_expose_their_writes_in_execution_order() -> None:
    first = _insert(1)
    second = _insert(2)
    plan = WritePlan(steps=PlannedWrites(segments=(eager_segment((first, second)),)))
    assert len(plan.steps) == 2
    assert plan.steps[0] == first
    assert list(plan.steps) == [first, second]


def test_an_eager_segment_refuses_zero_steps() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        eager_segment(())


def test_planned_steps_indexing_out_of_range_raises() -> None:
    step = _insert(1)
    steps = PlannedWrites(segments=(eager_segment((step,)),))
    with pytest.raises(IndexError):
        steps[5]


def test_planned_steps_compares_unequal_to_a_non_planned_steps_value() -> None:
    step = _insert(1)
    steps = PlannedWrites(segments=(eager_segment((step,)),))
    assert steps != "not a Planned Writes value"


class _CountingSegment:
    """A segment that rebuilds each step it is asked for, as a lazily backed
    segment does, and records every position it was asked for."""

    def __init__(self, keys: range) -> None:
        self._keys = keys
        self.asked: list[int] = []

    def __len__(self) -> int:
        return len(self._keys)

    def step(self, index: int) -> PlannedWrite:
        self.asked.append(index)
        return _insert(self._keys[index])


def _keys(steps: object) -> list[object]:
    assert isinstance(steps, WriteStepView | PlannedWrites)
    return [
        next(iter(step.entries[0].row.attributes.values()))
        for step in steps
        if isinstance(step, PlannedInsert)
    ]


def test_a_view_walks_only_the_segments_its_span_crosses_once_each() -> None:
    segments = (_CountingSegment(range(0, 3)), _CountingSegment(range(3, 5)))
    segments += (_CountingSegment(range(5, 9)),)
    steps = PlannedWrites(segments)
    view = steps.view(2, 6)
    assert len(view) == 4
    assert _keys(view) == [2, 3, 4, 5]
    assert [segment.asked for segment in segments] == [[2], [0, 1], [0]]


def test_an_empty_view_reads_no_segment_wherever_it_stands() -> None:
    segment = _CountingSegment(range(3))
    steps = PlannedWrites((segment,))
    for position in range(4):
        view = steps.view(position, position)
        assert len(view) == 0
        assert list(view) == []
    assert list(PlannedWrites().view(0, 0)) == []
    assert segment.asked == []


def test_a_whole_view_reads_its_owner_in_order() -> None:
    steps = PlannedWrites((eager_segment((_insert(1), _insert(2))), eager_segment((_insert(3),))))
    assert list(steps.view(0, len(steps))) == list(steps)
    assert _keys(steps.view(1, 3)) == [2, 3]


def test_a_view_holds_its_owner_and_two_positions_only() -> None:
    steps = eager_writes((_insert(1),))
    view = steps.view(0, 1)
    assert view.owner is steps
    assert (view.first, view.stop) == (0, 1)
    assert not hasattr(view, "__dict__")


@pytest.mark.parametrize(("first", "stop"), [(-1, 1), (2, 1), (0, 4), (4, 4)])
def test_a_view_spans_positions_within_its_owner_in_order(first: int, stop: int) -> None:
    steps = PlannedWrites((eager_segment((_insert(1), _insert(2), _insert(3))),))
    with pytest.raises(ValueError, match="within its 3 Planned Write"):
        steps.view(first, stop)
    with pytest.raises(ValueError, match="within its 3 Planned Write"):
        WriteStepView(steps, first, stop)


def test_eager_writes_hold_settled_steps_as_at_most_one_segment() -> None:
    first, second = _insert(1), _insert(2)
    steps = eager_writes((first, second))
    assert len(steps.segments) == 1
    assert list(steps) == [first, second]
    assert eager_writes(()).segments == ()


def test_an_attempt_that_opened_nothing_owns_nothing_an_insertion_opened() -> None:
    endpoint = OwnedEndpoint(_ACCOUNT, (1,), OPEN_BITEMPORAL_ENDS)
    assert not NO_TEMPORAL_WRITE_OWNERSHIP.owns(endpoint)
    assert not NO_TEMPORAL_WRITE_OWNERSHIP.continues_insertion(endpoint)
    assert NO_TEMPORAL_WRITE_OWNERSHIP.insertion_coverage(endpoint, None) == ()


def test_an_attempt_that_opened_nothing_has_proved_and_derived_nothing() -> None:
    endpoint = OwnedEndpoint(_ACCOUNT, (1,), OPEN_BITEMPORAL_ENDS)
    state = VersionedStateKey(ObjectKey(_ACCOUNT, (("id", 1),)), 1)
    assert NO_TEMPORAL_WRITE_OWNERSHIP.proven(state) is None
    assert tuple(NO_TEMPORAL_WRITE_OWNERSHIP.descendants(state, None)) == ()
    assert NO_TEMPORAL_WRITE_OWNERSHIP.descent(endpoint) is None


def test_a_plan_without_units_forms_one_unit_of_every_step() -> None:
    steps = PlannedWrites((eager_segment((_insert(1), _insert(2))),))
    assert WritePlan(steps=steps).units == (ExecutionUnit(end=2),)
    assert WritePlan().units == ()


def test_a_plans_units_follow_its_steps_in_order_and_end_with_them() -> None:
    steps = PlannedWrites((eager_segment((_insert(1), _insert(2))),))
    with pytest.raises(ValueError, match="follow its steps in order"):
        WritePlan(steps=steps, units=(ExecutionUnit(end=2), ExecutionUnit(end=1)))
    with pytest.raises(ValueError, match="end where its 2 step"):
        WritePlan(steps=steps, units=(ExecutionUnit(end=1),))


_EFFECTS = ("changed", "removed", "opened", "derived", "concludes")


@pytest.mark.parametrize("result", [ExecutionUnit, BoundRange])
def test_every_result_extends_the_one_flat_effects_vocabulary(result: type[UnitEffects]) -> None:
    assert issubclass(result, UnitEffects)
    names = [field.name for field in dataclasses.fields(result)]
    assert names[: len(_EFFECTS)] == list(_EFFECTS)
    assert all(field.kw_only for field in dataclasses.fields(result))
    with pytest.raises(TypeError):
        result(0)  # type: ignore[call-arg]


def test_effects_are_held_in_slots_on_the_unit_and_bound_range_themselves() -> None:
    for value in (ExecutionUnit(end=0), BoundRange(steps=PlannedWrites())):
        assert not hasattr(value, "__dict__")


def test_a_unit_publishes_nothing_it_does_not_name() -> None:
    unit = ExecutionUnit(end=0)
    assert [getattr(unit, name) for name in _EFFECTS] == [(), (), NO_OPENINGS, (), None]
    assert not any(
        isinstance(getattr(unit, field.name), UnitEffects) for field in dataclasses.fields(unit)
    )
    assert (unit.claim, unit.deferred) == (None, None)


class _Deferred(DeferredRange):
    __slots__ = ()


def test_a_deferred_unit_spans_no_step_between_the_units_around_it() -> None:
    steps = PlannedWrites((eager_segment((_insert(1), _insert(2))),))
    deferred = _Deferred()
    units = (
        ExecutionUnit(end=1),
        ExecutionUnit(end=1, deferred=deferred),
        ExecutionUnit(end=1, deferred=deferred),
        ExecutionUnit(end=2),
    )
    assert WritePlan(steps=steps, units=units).units == units
    leading = (ExecutionUnit(end=0, deferred=deferred), ExecutionUnit(end=2))
    assert WritePlan(steps=steps, units=leading).units == leading
