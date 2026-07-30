"""The Write Plan a flush's finalization produces (m-unit-work).

A Write Plan is the immutable, execution-ordered result of one planning call.
It retains no Transaction Instant, raw Write Observation, concurrency mode,
Subject Identity, strategy object, barrier marker, or private group — every
derived value is materialized into the steps themselves.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from parallax.core.unit_work.planned import PlannedWrite

__all__ = ["PlannedSteps", "WritePlan"]


@dataclass(frozen=True, slots=True)
class PlannedSteps:
    """The immutable ordered logical sequence of Planned Writes a Write Plan exposes.

    Logical rather than concrete: the semantic elements are Planned Writes,
    while the representation is free to pack homogeneous runs and expose stable
    immutable views during iteration instead of allocating one container per
    step. Views therefore compare by value and carry no object-identity promise.
    """

    steps: tuple[PlannedWrite, ...] = ()

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self) -> Iterator[PlannedWrite]:
        return iter(self.steps)

    def __getitem__(self, position: int) -> PlannedWrite:
        return self.steps[position]


@dataclass(frozen=True, slots=True)
class WritePlan:
    """One flush's finalized, execution-ordered steps.

    An empty :class:`PlannedSteps` is the one canonical result for complete
    cancellation or known no-op elimination; there is no empty-plan sentinel and
    no second result variant.
    """

    steps: PlannedSteps = PlannedSteps()
