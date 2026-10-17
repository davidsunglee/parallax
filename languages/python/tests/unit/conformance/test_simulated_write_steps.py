"""Simulated step execution without a store.

Each span is taken once and lowered through the production dry traversal, its
statements kept only once the whole span lowered and its steps kept not at
all; an allocating span answers the next scripted keys, unchecked.
"""

from __future__ import annotations

import gc
import weakref
from dataclasses import dataclass, field
from typing import Final

import pytest

from parallax.conformance import models
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._write_lowering import stream_physical
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import AttributeIdentity, entity_by_name
from parallax.core.write_plan.plan import PlannedWrites, WriteStepView
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedDelete,
    PlannedWrite,
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


def _span(segment: _Taken) -> WriteStepView:
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
