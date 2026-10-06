"""The Write Plan's own contract (m-write-plan values, `m-unit-work` *Write Plan
and Planned Steps*).

An empty Planned Steps is the one canonical result for a flush that survives
nothing, and Planned Steps is a logical sequence whose views compare by value
rather than by object identity. A plan's execution units partition its steps in
order, and an attempt that opened nothing owns, proved, and derived nothing.
"""

from __future__ import annotations

import pytest

from parallax.core.metamodel import AttributeIdentity
from parallax.core.write_plan import PlannedInsert, WritePlan
from parallax.core.write_plan.keys import ObjectKey, VersionedStateKey
from parallax.core.write_plan.plan import (
    NO_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    ExecutionUnit,
    OwnedEndpoint,
    PlannedSteps,
    eager_segment,
)
from parallax.core.write_plan.steps import NEW_LINEAGE, InsertEntry, PlannedRow
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of

_ACCOUNT = entity_of(corpus_model("account"), "Account").identity
_ID = AttributeIdentity(_ACCOUNT, "id")


def _insert(key: int) -> PlannedInsert:
    return PlannedInsert(
        entity=_ACCOUNT,
        entries=(InsertEntry(row=PlannedRow(attributes={_ID: key}), origin=NEW_LINEAGE),),
    )


def test_an_empty_write_plan_is_the_canonical_cancelled_result() -> None:
    plan = WritePlan()
    assert len(plan.steps) == 0
    assert list(plan.steps) == []
    assert plan == WritePlan(steps=PlannedSteps())


def test_planned_steps_expose_their_writes_in_execution_order() -> None:
    first = _insert(1)
    second = _insert(2)
    plan = WritePlan(steps=PlannedSteps(segments=(eager_segment((first, second)),)))
    assert len(plan.steps) == 2
    assert plan.steps[0] == first
    assert list(plan.steps) == [first, second]


def test_an_eager_segment_refuses_zero_steps() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        eager_segment(())


def test_planned_steps_indexing_out_of_range_raises() -> None:
    step = _insert(1)
    steps = PlannedSteps(segments=(eager_segment((step,)),))
    with pytest.raises(IndexError):
        steps[5]


def test_planned_steps_compares_unequal_to_a_non_planned_steps_value() -> None:
    step = _insert(1)
    steps = PlannedSteps(segments=(eager_segment((step,)),))
    assert steps != "not a Planned Steps value"


def test_an_attempt_that_opened_nothing_owns_nothing_an_insertion_opened() -> None:
    endpoint = OwnedEndpoint(_ACCOUNT, (1,), OPEN_BITEMPORAL_ENDS)
    assert not NO_OWNERSHIP.owns(endpoint)
    assert not NO_OWNERSHIP.continues_insertion(endpoint)


def test_an_attempt_that_opened_nothing_has_proved_and_derived_nothing() -> None:
    endpoint = OwnedEndpoint(_ACCOUNT, (1,), OPEN_BITEMPORAL_ENDS)
    state = VersionedStateKey(ObjectKey(_ACCOUNT, (("id", 1),)), 1)
    assert NO_OWNERSHIP.proven(state) is None
    assert tuple(NO_OWNERSHIP.descendants(state, None)) == ()
    assert NO_OWNERSHIP.descent(endpoint) is None


def test_a_plan_without_units_forms_one_unit_of_every_step() -> None:
    steps = PlannedSteps((eager_segment((_insert(1), _insert(2))),))
    assert WritePlan(steps=steps).units == (ExecutionUnit(end=2),)
    assert WritePlan().units == ()


def test_a_plans_units_follow_its_steps_in_order_and_end_with_them() -> None:
    steps = PlannedSteps((eager_segment((_insert(1), _insert(2))),))
    with pytest.raises(ValueError, match="follow its steps in order"):
        WritePlan(steps=steps, units=(ExecutionUnit(end=2), ExecutionUnit(end=1)))
    with pytest.raises(ValueError, match="end where its 2 step"):
        WritePlan(steps=steps, units=(ExecutionUnit(end=1),))
