from __future__ import annotations

import bisect
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from parallax.core.unit_work.planned import PlannedWrite

__all__ = ["PlannedSteps", "StepSegment", "WritePlan", "eager_segment"]


class StepSegment(Protocol):
    """One homogeneous, positive-length run of a Write Plan's Planned Steps.

    A segment exposes only its length and a materialize-on-demand accessor;
    nothing about how it is backed is part of the contract.
    """

    def __len__(self) -> int: ...
    def step(self, index: int) -> PlannedWrite: ...


@dataclass(frozen=True, slots=True)
class _EagerSegment:
    """A segment over already-settled steps, held as one immutable tuple."""

    steps: tuple[PlannedWrite, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("a Step Segment carries at least one step")

    def __len__(self) -> int:
        return len(self.steps)

    def step(self, index: int) -> PlannedWrite:
        return self.steps[index]


def eager_segment(steps: Sequence[PlannedWrite]) -> StepSegment:
    """A Step Segment wrapping already-settled steps, in order."""
    return _EagerSegment(tuple(steps))


@dataclass(frozen=True, slots=True)
class PlannedSteps:
    """The immutable ordered logical sequence of Planned Writes a Write Plan exposes.

    Backed by segments rather than one flat tuple: a large materialized run
    packs its steps as compact columns and rebuilds one Planned Write at a
    time, so no consumer of a Write Plan forces the whole run into memory as
    independently allocated objects merely by holding the plan.
    """

    segments: tuple[StepSegment, ...] = ()
    _offsets: tuple[int, ...] = field(init=False, repr=False, compare=False)
    _length: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        offsets: list[int] = []
        total = 0
        for segment in self.segments:
            offsets.append(total)
            total += len(segment)
        object.__setattr__(self, "_offsets", tuple(offsets))
        object.__setattr__(self, "_length", total)

    def __len__(self) -> int:
        return self._length

    def __iter__(self) -> Iterator[PlannedWrite]:
        for segment in self.segments:
            for index in range(len(segment)):
                yield segment.step(index)

    def __getitem__(self, position: int) -> PlannedWrite:
        length = self._length
        resolved = position if position >= 0 else position + length
        if not 0 <= resolved < length:
            raise IndexError(position)
        segment_index = bisect.bisect_right(self._offsets, resolved) - 1
        return self.segments[segment_index].step(resolved - self._offsets[segment_index])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PlannedSteps):
            return NotImplemented
        return len(self) == len(other) and all(a == b for a, b in zip(self, other, strict=True))

    # Equality reads the logical sequence, not the segmentation, so two
    # Planned Steps values packed differently can compare equal — the same
    # reason no meaningful `__hash__` exists (Planned Steps is a value never
    # used as a mapping/set key).
    __hash__ = None  # pyright: ignore[reportAssignmentType] - deliberately unhashable


@dataclass(frozen=True, slots=True)
class WritePlan:
    """One flush's finalized, execution-ordered steps.

    An empty :class:`PlannedSteps` is the one canonical result for complete
    cancellation or known no-op elimination; there is no empty-plan sentinel and
    no second result variant.
    """

    steps: PlannedSteps = PlannedSteps()
