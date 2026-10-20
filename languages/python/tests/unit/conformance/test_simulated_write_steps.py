"""Simulated step execution, with and without a store.

Recording lowers the steps it is handed through the production dry traversal,
keeping their statements only once all of them lowered and the steps not at
all; a store's rows change as each step is applied after that, and only a
recording simulation lowers at all. A lowering failure therefore outranks a
store's refusal, which stops the store's changes and is raised once the steps
lowered; any other failure applying a step propagates as it is applied.
Allocating steps answer the next scripted keys, unchecked, and a store is
answered none.
"""

from __future__ import annotations

import datetime as dt
import traceback
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance import _simulated_write_steps, models, simulated_temporal_store
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.simulated_temporal_store import (
    AmbiguousObservationError,
    SimulatedTemporalStore,
)
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._write_lowering import stream_physical
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, entity_by_name
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan.payload import AssignmentPayload
from parallax.core.write_plan.steps import INFINITY as OPEN_END
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    NEW_LINEAGE,
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
    PlannedInsert,
    PlannedRow,
    PlannedStep,
    WriteRow,
)
from tests.unit._gc_reachability import reachable_objects

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


def _holds_any(holder: object, steps: tuple[PlannedStep, ...]) -> bool:
    held = {id(steps), *(id(step) for step in steps)}
    return any(id(value) in held for value in reachable_objects(holder))


def test_steps_are_lowered_as_the_dry_traversal_lowers_them() -> None:
    simulated = _simulated()
    steps = _deletes(1, 2, 3)
    assert simulated(steps, allocates=False) == ()
    expected = tuple(stream_physical(steps, _PAYLOADS, _ACCOUNT_META, POSTGRES))
    assert simulated.statements == expected
    # Reading what was recorded lowers nothing again.
    assert simulated.statements == expected


def test_statements_accumulate_across_executions_in_order() -> None:
    simulated = _simulated()
    simulated(_deletes(1), allocates=False)
    simulated((), allocates=False)
    simulated(_deletes(2), allocates=False)
    assert [statement.binds for statement in simulated.statements] == [(1,), (2,)]


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


def test_an_execution_keeps_nothing_of_its_steps_once_it_returned() -> None:
    simulated = _simulated()
    steps = _deletes(1, 2)
    simulated(steps, allocates=False)
    assert not _holds_any(simulated, steps)
    assert len(simulated.statements) == 2


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


def test_a_simulation_with_no_store_records_its_statements() -> None:
    with pytest.raises(ValueError, match="records the statements"):
        SimulatedWriteSteps(_PAYLOADS, _ACCOUNT_META, POSTGRES, record_statements=False)


# --------------------------------------------------------------------------- #
# A store's rows change as each step is applied.                              #
# --------------------------------------------------------------------------- #
_POSITION_META: Final = models.load_models()["position"]
_POSITION: Final = entity_by_name(_POSITION_META, "Position")
assert _POSITION is not None
_POSITION_PAYLOADS: Final = build_write_planner(_POSITION_META).payloads
_JAN, _JUN = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 6))
_NOW: Final = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


def _position(name: str) -> AttributeIdentity:
    return AttributeIdentity(_POSITION.identity, name)


def _members(
    key: int, start: dt.datetime, value: str, *, tx_start: dt.datetime = _JAN
) -> dict[str, object]:
    return {
        "id": key,
        "acctNum": "A",
        "value": Decimal(value),
        "validStart": start,
        "validEnd": INFINITY,
        "txStart": tx_start,
        "txEnd": INFINITY,
    }


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


def _opening(key: int, value: str) -> PlannedStep:
    members = _members(key, _JAN, value, tx_start=_NOW)
    row = PlannedRow(attributes={_position(name): member for name, member in members.items()})
    return PlannedInsert(entity=_POSITION.identity, entries=(WriteRow(row, NEW_LINEAGE),))


def _store(*rows: dict[str, object]) -> SimulatedTemporalStore:
    store = SimulatedTemporalStore()
    store.seed_fixtures(_POSITION_META, _POSITION, rows)
    return store


def _value(store: SimulatedTemporalStore, key: int) -> object:
    observation = store.predecessor_for(_POSITION_META, _POSITION, {"id": key})
    return None if observation is None else observation.predecessor.member("value")


def _backed(store: SimulatedTemporalStore, *, record: bool) -> SimulatedWriteSteps:
    return SimulatedWriteSteps(
        _POSITION_PAYLOADS, _POSITION_META, POSTGRES, store=store, record_statements=record
    )


def _succession(key: int) -> tuple[PlannedStep, ...]:
    """Position ``key``'s close and the opening succeeding it."""
    return (_close(key), _opening(key, "150.00"))


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


def test_recorded_steps_are_applied_and_lowered() -> None:
    store = _store(_members(1, _JAN, "100.00"))
    simulated = _backed(store, record=True)
    steps = _succession(1)
    assert simulated(steps, allocates=False) == ()
    assert _value(store, 1) == Decimal("150.00")
    expected = tuple(stream_physical(steps, _POSITION_PAYLOADS, _POSITION_META, POSTGRES))
    assert simulated.statements == expected


def test_tracked_steps_change_the_store_and_lower_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(*_arguments: object) -> object:
        raise AssertionError("tracked steps lower nothing")

    monkeypatch.setattr(_simulated_write_steps, "stream_physical", refused)
    store = _store(_members(1, _JAN, "100.00"))
    simulated = _backed(store, record=False)
    assert simulated(_succession(1), allocates=False) == ()
    assert _value(store, 1) == Decimal("150.00")
    assert simulated.statements == ()


def _twins() -> SimulatedTemporalStore:
    """Two rows of Position 1 sharing one complete address, which a close of
    it refuses."""
    return _store(_members(1, _JAN, "100.00"), _members(1, _JUN, "200.00"))


def test_a_store_refusal_raises_once_the_steps_lowered_and_stops_their_later_changes() -> None:
    store = _twins()
    simulated = _backed(store, record=True)
    with pytest.raises(AmbiguousObservationError, match="share both") as raised:
        simulated((_close(1), _opening(2, "9.00")), allocates=False)
    assert _value(store, 2) is None
    assert simulated.statements == ()
    # The refusal raised carries no traceback into the step it refused.
    store_module = simulated_temporal_store.__file__
    assert all(
        frame.filename != store_module for frame in traceback.extract_tb(raised.value.__traceback__)
    )


def test_a_lowering_failure_outranks_a_store_refusal_and_changes_no_row() -> None:
    steps = (_close(1), _close(2), _opening(2, "9.00"))
    failure = ValueError("the second close cannot be prepared")
    store = _twins()
    simulated = SimulatedWriteSteps(
        _FailingPreparer(steps[1], failure), _POSITION_META, POSTGRES, store=store
    )
    with pytest.raises(ValueError, match="cannot be prepared") as raised:
        simulated(steps, allocates=False)
    assert raised.value is failure
    assert simulated.statements == ()
    assert _value(store, 2) is None


def test_tracked_steps_raise_a_store_refusal_as_its_step_is_applied() -> None:
    store = _twins()
    simulated = _backed(store, record=False)
    with pytest.raises(AmbiguousObservationError):
        simulated((_close(1), _opening(2, "9.00")), allocates=False)
    assert _value(store, 2) is None


@pytest.mark.parametrize("record", [True, False], ids=["recorded", "tracked"])
@pytest.mark.parametrize("failure", [RuntimeError("a defect"), KeyboardInterrupt()], ids=type)
def test_any_other_failure_applying_a_step_propagates_as_it_is_applied(
    monkeypatch: pytest.MonkeyPatch, record: bool, failure: BaseException
) -> None:
    applied: list[PlannedStep] = []

    def failing(store: SimulatedTemporalStore, model: object, step: PlannedStep) -> None:
        applied.append(step)
        raise failure

    monkeypatch.setattr(SimulatedTemporalStore, "apply", failing)
    simulated = _backed(_store(), record=record)
    steps = (_close(1), _close(2))
    with pytest.raises(type(failure)) as raised:
        simulated(steps, allocates=False)
    assert raised.value is failure
    assert applied == [steps[0]]
    assert simulated.statements == ()


@pytest.mark.parametrize("record", [True, False], ids=["recorded", "tracked"])
def test_a_store_backed_execution_keeps_nothing_of_its_steps_once_it_returned(
    record: bool,
) -> None:
    store = _store(_members(1, _JAN, "100.00"))
    simulated = _backed(store, record=record)
    steps = _succession(1)
    simulated(steps, allocates=False)
    assert not _holds_any(simulated, steps)


def test_a_store_backed_simulation_is_answered_no_scripted_keys() -> None:
    with pytest.raises(ValueError, match="answers no scripted keys"):
        SimulatedWriteSteps(
            _POSITION_PAYLOADS, _POSITION_META, POSTGRES, store=_store(), allocated_results=[(1,)]
        )
    simulated = _backed(_store(), record=True)
    with pytest.raises(ValueError, match="no scripted result"):
        simulated((_opening(1, "1.00"),), allocates=True)
