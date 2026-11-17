"""Simulated step execution.

Steps that fail to lower leave none of their statements behind, and a counted
step answers the next scripted count.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

import pytest

from parallax.conformance import models
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.core._execution._planning import build_write_planner
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.metamodel import AttributeIdentity, EntityIdentity, entity_by_name
from parallax.core.internal.planned_step.payload import AssignmentPayload
from parallax.core.internal.planned_step.steps import INFINITY as OPEN_END
from parallax.core.internal.planned_step.steps import (
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
from parallax.core.internal.write_payload import LayoutPayloadPreparer
from tests._support.bindings import bound_model

_ACCOUNT_META: Final = models.load_models()["account"]
_ACCOUNT: Final = entity_by_name(_ACCOUNT_META, "Account")
assert _ACCOUNT is not None
_ID: Final = AttributeIdentity(_ACCOUNT.identity, "id")
_PAYLOADS: Final = build_write_planner(bound_model(_ACCOUNT_META)).payloads


def _delete(key: int) -> PlannedDelete:
    return PlannedDelete(
        entity=_ACCOUNT.identity,
        target=KeyTarget((_ID,), ((key,),)),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(1, MISSING_TARGET),
    )


def test_steps_that_fail_to_lower_keep_none_of_their_statements() -> None:
    steps = (_close(1), _close(2))
    failure = ValueError("the second close cannot be prepared")
    simulated = SimulatedWriteSteps(
        _FailingPreparer(steps[1], failure), bound_model(_POSITION_META), POSTGRES
    )
    with pytest.raises(ValueError, match="cannot be prepared") as raised:
        simulated(steps)
    assert raised.value is failure
    assert simulated.statements == ()
    simulated((_close(3),))
    assert len(simulated.statements) == 1


def test_each_counted_step_answers_the_next_scripted_count_then_zero() -> None:
    simulated = SimulatedWriteSteps(_PAYLOADS, bound_model(_ACCOUNT_META), POSTGRES, counts=(3, 0))
    assert [simulated.counted(_delete(key)) for key in (1, 2, 3)] == [3, 0, 0]
    assert len(simulated.statements) == 3


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
        super().__init__(bound_model(_POSITION_META))
        assert isinstance(failing, PlannedClose)
        self.failing = failing
        self.failure = failure

    def assignments(
        self, entity: EntityIdentity, assignments: PlannedAssignments
    ) -> AssignmentPayload:
        if assignments is self.failing.assignments:
            raise self.failure
        return super().assignments(entity, assignments)
