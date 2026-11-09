"""Simulated step execution.

Steps that fail to lower leave none of their statements behind, and allocating
steps answer the next scripted keys, unchecked.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

import pytest

from parallax.conformance import models
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.core._execution._planning import build_write_planner
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, entity_by_name
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan.payload import AssignmentPayload
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    STALE_WRITE,
    SUPERSEDED,
    UNGATED,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedStep,
)

_ACCOUNT_META: Final = models.load_models()["account"]
_ACCOUNT: Final = entity_by_name(_ACCOUNT_META, "Account")
assert _ACCOUNT is not None
_ID: Final = AttributeIdentity(_ACCOUNT.identity, "id")
_PAYLOADS: Final = build_write_planner(_ACCOUNT_META).payloads


def _delete(key: int) -> PlannedStep:
    return PlannedDelete(
        entity=_ACCOUNT.identity,
        target=KeyTarget((_ID,), ((key,),)),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(1, MISSING_TARGET),
    )


def _simulated(*allocated: tuple[object, ...]) -> SimulatedWriteSteps:
    return SimulatedWriteSteps(_PAYLOADS, _ACCOUNT_META, POSTGRES, allocated_results=allocated)


def _deletes(*keys: int) -> tuple[PlannedStep, ...]:
    return tuple(_delete(key) for key in keys)


def test_steps_that_fail_to_lower_keep_none_of_their_statements_and_answer_no_keys() -> None:
    steps = (_close(1), _close(2))
    failure = ValueError("the second close cannot be prepared")
    simulated = SimulatedWriteSteps(
        _FailingPreparer(steps[1], failure),
        _POSITION_META,
        POSTGRES,
        allocated_results=[(42,)],
    )
    with pytest.raises(ValueError, match="cannot be prepared") as raised:
        simulated(steps, allocates=True)
    assert raised.value is failure
    assert simulated.statements == ()
    # The scripted keys are still the next allocating execution's.
    assert simulated((_close(3),), allocates=True) == (42,)


def test_each_allocating_execution_answers_the_next_scripted_keys_unchecked() -> None:
    simulated = _simulated((42,), (), (7, 8))
    assert simulated(_deletes(1), allocates=False) == ()
    assert simulated(_deletes(2), allocates=True) == (42,)
    assert simulated(_deletes(3), allocates=True) == ()
    assert simulated(_deletes(4), allocates=True) == (7, 8)
    with pytest.raises(ValueError, match="no scripted result"):
        simulated(_deletes(5), allocates=True)
    # A misconfigured execution records nothing either.
    assert len(simulated.statements) == 4


_POSITION_META: Final = models.load_models()["position"]
_POSITION: Final = entity_by_name(_POSITION_META, "Position")
assert _POSITION is not None
_NOW: Final = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


def _position(name: str) -> AttributeIdentity:
    return AttributeIdentity(_POSITION.identity, name)


def _close(key: int) -> PlannedStep:
    return PlannedClose(
        entity=_POSITION.identity,
        target=MilestoneTarget(
            key_attributes=(_position("id"),),
            key_values=(key,),
            end_attributes=(_position("validEnd"), _position("txEnd")),
            end_values=(OPEN_END, OPEN_END),
        ),
        assignments=PlannedAssignments(attributes={_position("txEnd"): _NOW}),
        cause=SUPERSEDED,
        concurrency=UNGATED,
        affected_rows=ExactCount(1, STALE_WRITE),
    )


class _FailingPreparer(LayoutPayloadPreparer):
    __slots__ = ("failing", "failure")

    def __init__(self, failing: PlannedStep, failure: Exception) -> None:
        super().__init__(_POSITION_META)
        assert isinstance(failing, PlannedClose)
        self.failing = failing
        self.failure = failure

    def assignments(
        self, entity: EntityIdentity, assignments: PlannedAssignments
    ) -> AssignmentPayload:
        if assignments is self.failing.assignments:
            raise self.failure
        return super().assignments(entity, assignments)
