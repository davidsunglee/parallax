from __future__ import annotations

import bisect
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from parallax.core.base import ManagedValue
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, EntityMetadata
from parallax.core.unit_work.planned import INFINITY, PlannedWrite, TemporalUpperBound
from parallax.core.unit_work.planner import ObservedStateKey

__all__ = [
    "NO_OWNERSHIP",
    "OPEN_BITEMPORAL_ENDS",
    "TRANSACTION_TIME_ENDS",
    "BoundRange",
    "Completion",
    "Completions",
    "DeferredRange",
    "ExecutionUnit",
    "OwnedEndpoint",
    "Ownership",
    "PlannedSteps",
    "RangeAcquisition",
    "StepSegment",
    "WritePlan",
    "eager_segment",
]


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
class OwnedEndpoint:
    """One temporal row's complete physical address: its Entity, its family
    primary-key values in key order, and one exclusive upper bound per As-Of
    Axis in canonical axis order.

    Axis starts and payload are not part of it, so a same-address revision
    leaves the endpoint unchanged.
    """

    entity: EntityIdentity
    key: tuple[object, ...]
    ends: tuple[TemporalUpperBound, ...]


TRANSACTION_TIME_ENDS: Final[tuple[TemporalUpperBound, ...]] = (INFINITY,)
"""The ends of every current Transaction-Time-Only row."""

OPEN_BITEMPORAL_ENDS: Final[tuple[TemporalUpperBound, ...]] = (INFINITY, INFINITY)
"""The ends of a current Bitemporal row whose Valid Time runs on without end."""


class Ownership(Protocol):
    """Read-only access to the rows the planning attempt opened successfully.

    Ownership is the attempt's own record of executed openings, never an
    inference from a row's Transaction-Time start equalling the attempt's
    instant.
    """

    def owns(self, endpoint: OwnedEndpoint, /) -> bool: ...

    def owns_any(self, entity: EntityIdentity, /) -> bool:
        """Whether any owned row is an object of ``entity``."""
        ...

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        """Whether the owned row ``endpoint`` is coverage an admitted insertion
        opened, so that its successors are too."""
        ...


@dataclass(frozen=True, slots=True)
class _NoOwnership:
    def owns(self, endpoint: OwnedEndpoint, /) -> bool:
        del endpoint
        return False

    def owns_any(self, entity: EntityIdentity, /) -> bool:
        del entity
        return False

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        del endpoint
        return False


NO_OWNERSHIP: Final[Ownership] = _NoOwnership()
"""The ownership of an attempt that has opened nothing."""


class Completion(Protocol):
    """Source authority a successful execution unit spends."""

    def consume(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Completions:
    """Several distinct source authorities one unit spends together."""

    members: tuple[Completion, ...]

    def consume(self) -> None:
        for member in self.members:
            member.consume()


@dataclass(frozen=True, slots=True)
class RangeAcquisition:
    """The current coverage a deferred range must read before it binds: one
    object's current rows overlapping ``[valid_from, until)`` — through the open
    bound when ``until`` is ``None`` — read under the shared row lock when
    ``locking``. A Transaction-Time-Only object has no Valid Time, so its
    bounds are both ``None`` and its one current row is the coverage."""

    entity: EntityMetadata
    key_attribute: AttributeIdentity
    key_value: ManagedValue
    valid_from: ManagedValue | None
    until: ManagedValue | None
    locking: bool


@dataclass(frozen=True, slots=True)
class BoundRange:
    """What a deferred range became once its acquired coverage was bound: the
    physical steps it executes, in order, and the facts its success publishes."""

    steps: tuple[PlannedWrite, ...]
    changed: tuple[ObservedStateKey, ...]
    removed: tuple[OwnedEndpoint, ...]
    opened: tuple[OwnedEndpoint, ...]
    continued: tuple[OwnedEndpoint, ...] = ()


class DeferredRange(Protocol):
    """A finalized range whose physical steps depend on coverage no planning
    input knew: the executor performs ``acquisition`` and hands back the rows it
    read, and :meth:`bind` answers the steps to execute."""

    @property
    def acquisition(self) -> RangeAcquisition: ...

    def bind(self, rows: object, /) -> BoundRange: ...


@dataclass(frozen=True, slots=True)
class ExecutionUnit:
    """One execution unit of a Write Plan and what its success publishes.

    A unit spans the plan's steps up to the exclusive offset ``end``, after the
    previous unit's. Its facts are applied only once every one of its steps has
    succeeded, and before any later unit executes: the source authority
    ``claim`` it spends, the observed states it changed — a single retained
    claim's own state among them whenever the unit has a step — and the owned
    rows it removed and opened. The rows it opened are split by what they
    derive from: ``continued`` holds an insert's row and every successor of a
    row an admitted insertion opened, and ``opened`` every other. Removals are
    retired before openings are registered, so a row removed and reopened at
    one address remains owned.

    A unit with a ``deferred`` range has no planned step of its own: its steps
    and the facts beyond its claim come from binding the coverage the executor
    acquires for it.
    """

    end: int
    claim: Completion | None = None
    changed: Iterable[ObservedStateKey] = ()
    removed: Iterable[OwnedEndpoint] = ()
    opened: Iterable[OwnedEndpoint] = ()
    continued: Iterable[OwnedEndpoint] = ()
    deferred: DeferredRange | None = None


@dataclass(frozen=True, slots=True)
class WritePlan:
    """One flush's finalized, execution-ordered steps.

    An empty :class:`PlannedSteps` is the one canonical result for complete
    cancellation or known no-op elimination; there is no empty-plan sentinel and
    no second result variant.

    ``units`` partitions ``steps`` into execution units, in order and ending
    where the steps end; a plan given none forms one unit of every step, which
    publishes nothing beyond its steps' own effects.
    """

    steps: PlannedSteps = PlannedSteps()
    units: tuple[ExecutionUnit, ...] = ()

    def __post_init__(self) -> None:
        length = len(self.steps)
        units = self.units
        if not units:
            if length:
                object.__setattr__(self, "units", (ExecutionUnit(end=length),))
            return
        previous = 0
        for unit in units:
            if unit.end < previous:
                raise ValueError("a Write Plan's execution units follow its steps in order")
            previous = unit.end
        if previous != length:
            raise ValueError(
                f"a Write Plan's execution units end where its {length} step(s) end, not at "
                f"{previous}"
            )
