"""Simulated step execution, with and without a store.

Each span is taken once. Recording lowers it through the production dry
traversal, its statements kept only once the whole span lowered and its steps
kept not at all; a store's rows change as each step is taken, and only a
recording simulation lowers at all. A lowering failure outranks a store's
refusal, which stops the store's changes and is raised once the span lowered;
any other failure applying a step propagates as it is taken. An allocating
span answers the next scripted keys, unchecked, and a store is answered none.
"""

from __future__ import annotations

import datetime as dt
import gc
import traceback
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
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
from parallax.core.metamodel import AttributeIdentity, entity_by_name
from parallax.core.write_plan.plan import PlannedWrites, WriteStepView
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
    PlannedWrite,
    WriteRow,
)

_ACCOUNT_META: Final = models.load_models()["account"]
_ACCOUNT: Final = entity_by_name(_ACCOUNT_META, "Account")
assert _ACCOUNT is not None
_ID: Final = AttributeIdentity(_ACCOUNT.identity, "id")
_PAYLOADS: Final = build_write_planner(_ACCOUNT_META).payloads


def _delete(key: int) -> PlannedWrite:
    return PlannedDelete(
        entity=_ACCOUNT.identity,
        target=KeyTarget((_ID,), ((key,),)),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(1, MISSING_TARGET),
    )


@dataclass
class _Taken:
    """A segment building each step only when asked, recording each position
    asked, and raising ``failure`` instead of building the step at ``failing``."""

    keys: tuple[int, ...]
    failing: int | None = None
    failure: Exception | None = None
    asked: list[int] = field(default_factory=list[int])

    def __len__(self) -> int:
        return len(self.keys)

    def step(self, index: int) -> PlannedWrite:
        self.asked.append(index)
        if index == self.failing and self.failure is not None:
            raise self.failure
        return _delete(self.keys[index])


@dataclass
class _Built:
    """A segment building each of ``steps`` only when asked, recording each
    position asked, and raising ``failure`` instead of building the step at
    ``failing``."""

    steps: tuple[Callable[[], PlannedWrite], ...]
    failing: int | None = None
    failure: Exception | None = None
    asked: list[int] = field(default_factory=list[int])

    def __len__(self) -> int:
        return len(self.steps)

    def step(self, index: int) -> PlannedWrite:
        self.asked.append(index)
        if index == self.failing and self.failure is not None:
            raise self.failure
        return self.steps[index]()


def _span(segment: _Taken | _Built) -> WriteStepView:
    return PlannedWrites((segment,)).view(0, len(segment))


def _simulated(*allocated: tuple[object, ...]) -> SimulatedWriteSteps:
    return SimulatedWriteSteps(_PAYLOADS, _ACCOUNT_META, POSTGRES, allocated_results=allocated)


def test_a_span_is_taken_once_and_lowered_as_the_dry_traversal_lowers_it() -> None:
    simulated = _simulated()
    segment = _Taken((1, 2, 3))
    assert simulated(_span(segment), allocates=False) == ()
    assert segment.asked == [0, 1, 2]
    expected = tuple(
        stream_physical([_delete(key) for key in (1, 2, 3)], _PAYLOADS, _ACCOUNT_META, POSTGRES)
    )
    assert simulated.statements == expected
    # Reading what was recorded takes and lowers nothing again.
    assert simulated.statements == expected
    assert segment.asked == [0, 1, 2]


def test_statements_accumulate_across_spans_in_order() -> None:
    simulated = _simulated()
    simulated(_span(_Taken((1,))), allocates=False)
    simulated(_span(_Taken(())), allocates=False)
    simulated(_span(_Taken((2,))), allocates=False)
    assert [statement.binds for statement in simulated.statements] == [(1,), (2,)]


def test_a_span_that_fails_to_lower_keeps_none_of_its_statements_and_answers_no_keys() -> None:
    simulated = _simulated((42,))
    failure = ValueError("the second step cannot be built")
    with pytest.raises(ValueError, match="cannot be built") as raised:
        simulated(_span(_Taken((1, 2), failing=1, failure=failure)), allocates=True)
    assert raised.value is failure
    assert simulated.statements == ()
    # The scripted keys are still the next allocating span's.
    assert simulated(_span(_Taken((3,))), allocates=True) == (42,)


def test_a_span_kept_nothing_of_its_steps_once_it_returned() -> None:
    simulated = _simulated()
    segment = _Taken((1, 2))
    alive = weakref.ref(segment)
    simulated(_span(segment), allocates=False)
    del segment
    gc.collect()
    assert alive() is None
    assert len(simulated.statements) == 2


def test_each_allocating_span_answers_the_next_scripted_keys_unchecked() -> None:
    simulated = _simulated((42,), (), (7, 8))
    assert simulated(_span(_Taken((1,))), allocates=False) == ()
    assert simulated(_span(_Taken((2,))), allocates=True) == (42,)
    assert simulated(_span(_Taken((3,))), allocates=True) == ()
    assert simulated(_span(_Taken((4,))), allocates=True) == (7, 8)
    with pytest.raises(ValueError, match="no scripted result"):
        simulated(_span(_Taken((5,))), allocates=True)
    # A misconfigured span records nothing either.
    assert len(simulated.statements) == 4


def test_a_simulation_with_no_store_records_its_statements() -> None:
    with pytest.raises(ValueError, match="records the statements"):
        SimulatedWriteSteps(_PAYLOADS, _ACCOUNT_META, POSTGRES, record_statements=False)


# --------------------------------------------------------------------------- #
# A store's rows change as each step is taken.                                 #
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


def _close(key: int) -> PlannedWrite:
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


def _opening(key: int, value: str) -> PlannedWrite:
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


def _succession(key: int) -> tuple[Callable[[], PlannedWrite], ...]:
    """Position ``key``'s close and the opening succeeding it."""
    return (lambda: _close(key), lambda: _opening(key, "150.00"))


def test_a_recorded_span_is_taken_once_applying_and_lowering_each_step() -> None:
    store = _store(_members(1, _JAN, "100.00"))
    simulated = _backed(store, record=True)
    segment = _Built(_succession(1))
    assert simulated(_span(segment), allocates=False) == ()
    assert segment.asked == [0, 1]
    assert _value(store, 1) == Decimal("150.00")
    expected = tuple(
        stream_physical(
            [step() for step in _succession(1)], _POSITION_PAYLOADS, _POSITION_META, POSTGRES
        )
    )
    assert simulated.statements == expected
    assert segment.asked == [0, 1]


def test_a_tracked_span_changes_the_store_and_lowers_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(*_arguments: object) -> object:
        raise AssertionError("a tracked span lowers nothing")

    monkeypatch.setattr(_simulated_write_steps, "stream_physical", refused)
    store = _store(_members(1, _JAN, "100.00"))
    simulated = _backed(store, record=False)
    segment = _Built(_succession(1))
    assert simulated(_span(segment), allocates=False) == ()
    assert segment.asked == [0, 1]
    assert _value(store, 1) == Decimal("150.00")
    assert simulated.statements == ()


def _twins() -> SimulatedTemporalStore:
    """Two rows of Position 1 sharing one complete address, which a close of
    it refuses."""
    return _store(_members(1, _JAN, "100.00"), _members(1, _JUN, "200.00"))


def test_a_store_refusal_raises_once_the_span_lowered_and_stops_its_later_changes() -> None:
    store = _twins()
    simulated = _backed(store, record=True)
    segment = _Built((lambda: _close(1), lambda: _opening(2, "9.00")))
    with pytest.raises(AmbiguousObservationError, match="share both") as raised:
        simulated(_span(segment), allocates=False)
    assert segment.asked == [0, 1]
    assert _value(store, 2) is None
    assert simulated.statements == ()
    # The refusal raised carries no traceback into the step it refused.
    store_module = simulated_temporal_store.__file__
    assert all(
        frame.filename != store_module for frame in traceback.extract_tb(raised.value.__traceback__)
    )


def test_a_lowering_failure_outranks_a_store_refusal() -> None:
    failure = ValueError("the second step cannot be built")
    simulated = _backed(_twins(), record=True)
    segment = _Built((lambda: _close(1), lambda: _close(2)), failing=1, failure=failure)
    with pytest.raises(ValueError, match="cannot be built") as raised:
        simulated(_span(segment), allocates=False)
    assert raised.value is failure
    assert simulated.statements == ()


def test_a_tracked_span_raises_a_store_refusal_as_its_step_is_taken() -> None:
    store = _twins()
    simulated = _backed(store, record=False)
    segment = _Built((lambda: _close(1), lambda: _opening(2, "9.00")))
    with pytest.raises(AmbiguousObservationError):
        simulated(_span(segment), allocates=False)
    assert segment.asked == [0]
    assert _value(store, 2) is None


@pytest.mark.parametrize("record", [True, False], ids=["recorded", "tracked"])
@pytest.mark.parametrize("failure", [RuntimeError("a defect"), KeyboardInterrupt()], ids=type)
def test_any_other_failure_applying_a_step_propagates_as_it_is_taken(
    monkeypatch: pytest.MonkeyPatch, record: bool, failure: BaseException
) -> None:
    def failing(store: SimulatedTemporalStore, model: object, step: PlannedWrite) -> None:
        raise failure

    monkeypatch.setattr(SimulatedTemporalStore, "apply", failing)
    simulated = _backed(_store(), record=record)
    segment = _Built((lambda: _close(1), lambda: _close(2)))
    with pytest.raises(type(failure)) as raised:
        simulated(_span(segment), allocates=False)
    assert raised.value is failure
    assert segment.asked == [0]
    assert simulated.statements == ()


@pytest.mark.parametrize("record", [True, False], ids=["recorded", "tracked"])
def test_a_store_backed_span_kept_nothing_of_its_steps_once_it_returned(record: bool) -> None:
    store = _store(_members(1, _JAN, "100.00"))
    simulated = _backed(store, record=record)
    segment = _Built(_succession(1))
    alive = weakref.ref(segment)
    simulated(_span(segment), allocates=False)
    del segment
    gc.collect()
    assert alive() is None


def test_a_store_backed_simulation_is_answered_no_scripted_keys() -> None:
    with pytest.raises(ValueError, match="answers no scripted keys"):
        SimulatedWriteSteps(
            _POSITION_PAYLOADS, _POSITION_META, POSTGRES, store=_store(), allocated_results=[(1,)]
        )
    simulated = _backed(_store(), record=True)
    with pytest.raises(ValueError, match="no scripted result"):
        simulated(_span(_Built((lambda: _opening(1, "1.00"),))), allocates=True)
