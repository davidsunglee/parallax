from __future__ import annotations

import bisect
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan.keys import ObjectKey, ObservedStateKey
from parallax.core.write_plan.steps import INFINITY, PlannedWrite, TemporalUpperBound

__all__ = [
    "NO_OPENINGS",
    "NO_TEMPORAL_WRITE_OWNERSHIP",
    "OPEN_BITEMPORAL_ENDS",
    "TRANSACTION_TIME_ENDS",
    "AllocatedOpening",
    "BoundRange",
    "CombinedSourceAuthority",
    "DeferredRange",
    "Derivation",
    "Descent",
    "ExecutionUnit",
    "Openings",
    "OwnedEndpoint",
    "PlannedSteps",
    "SourceAuthority",
    "StepSegment",
    "TemporalWriteOwnership",
    "UnitEffects",
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


@dataclass(frozen=True, slots=True)
class Derivation:
    """One original an execution unit transformed under protection — a guarded
    effect that succeeded, or the shared lock the unit held — and the current
    rows it left in that original's place.

    ``original`` is the exact state the unit found, ``valid_time_coverage`` the
    Valid Time it covered (``None`` on a Transaction-Time-Only object), and
    ``owned`` its own address where the attempt had opened it. ``rows`` holds
    each nonempty row the unit derived from it, by address and the Valid Time
    it covers, a row revised in place among them.
    """

    original: ObservedStateKey
    valid_time_coverage: TimeInterval | None
    owned: OwnedEndpoint | None
    rows: tuple[tuple[OwnedEndpoint, TimeInterval | None], ...]


@dataclass(frozen=True, slots=True)
class Descent:
    """What one current row the attempt opened derives from within the running
    flush: the Valid Time it covers as opened (``None`` on a
    Transaction-Time-Only object), and the protected original that stood before
    the flush began, through however many of its units."""

    valid_time_coverage: TimeInterval | None
    original: ObservedStateKey


class TemporalWriteOwnership(Protocol):
    """Read-only access to the temporal rows the planning attempt opened
    successfully, and to what the running flush's earlier units proved.

    It reads the attempt's own record of executed openings, never an
    inference from a row's Transaction-Time start equalling the attempt's
    instant, and is neither a copy of that record nor source authority.
    """

    def owns(self, endpoint: OwnedEndpoint, /) -> bool: ...

    def owns_any(self, entity: EntityIdentity, /) -> bool:
        """Whether any owned row is an object of ``entity``."""
        ...

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        """Whether the owned row ``endpoint`` is coverage an admitted insertion
        opened, so that its successors are too."""
        ...

    def proven(self, original: ObservedStateKey, /) -> Derivation | None:
        """How an earlier execution unit of the running flush transformed
        ``original``, if one did."""
        ...

    def descendants(
        self, original: ObservedStateKey, valid_time_window: TimeInterval | None, /
    ) -> Iterable[tuple[OwnedEndpoint, Descent]]:
        """The current rows the running flush derived from ``original``, which
        it proved (:meth:`proven`), whose Valid Time overlaps
        ``valid_time_window`` — every one of them where it is ``None`` — in
        Valid-Time order. The traversal is consumed before ownership changes."""
        ...

    def descent(self, endpoint: OwnedEndpoint, /) -> Descent | None:
        """What the current row ``endpoint`` derives from within the running
        flush, if anything."""
        ...


@dataclass(frozen=True, slots=True)
class _NoTemporalWriteOwnership:
    def owns(self, endpoint: OwnedEndpoint, /) -> bool:
        del endpoint
        return False

    def owns_any(self, entity: EntityIdentity, /) -> bool:
        del entity
        return False

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        del endpoint
        return False

    def proven(self, original: ObservedStateKey, /) -> Derivation | None:
        del original
        return None

    def descendants(
        self, original: ObservedStateKey, valid_time_window: TimeInterval | None, /
    ) -> Iterable[tuple[OwnedEndpoint, Descent]]:
        del original, valid_time_window
        return ()

    def descent(self, endpoint: OwnedEndpoint, /) -> Descent | None:
        del endpoint
        return None


NO_TEMPORAL_WRITE_OWNERSHIP: Final[TemporalWriteOwnership] = _NoTemporalWriteOwnership()
"""The ownership of an attempt that has opened nothing."""


class SourceAuthority(Protocol):
    """Source authority admission already accepted, which a successful
    execution unit spends."""

    def consume(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CombinedSourceAuthority:
    """Several distinct source authorities one unit spends together."""

    members: tuple[SourceAuthority, ...]

    def consume(self) -> None:
        for member in self.members:
            member.consume()


@dataclass(frozen=True, slots=True)
class AllocatedOpening:
    """A row an execution unit opens whose key the database allocates: its
    address is complete once the insert that opens it answers the key."""

    entity: EntityIdentity
    ends: tuple[TemporalUpperBound, ...]


@dataclass(frozen=True, slots=True)
class Openings:
    """The owned rows an execution unit opens, by what each derives from:
    ``continued`` holds an insert's row and every successor of a row an
    admitted insertion opened, and ``fresh`` every other row. ``allocated``
    holds, in step order, each row whose key its insert answers."""

    fresh: Iterable[OwnedEndpoint] = ()
    continued: Iterable[OwnedEndpoint] = ()
    allocated: tuple[AllocatedOpening, ...] = ()


NO_OPENINGS: Final[Openings] = Openings()


@dataclass(frozen=True, slots=True, kw_only=True)
class UnitEffects:
    """What one execution unit's success publishes, complete.

    ``changed`` names every observed state the unit changes, its own source's
    included; executing a step changes nothing by itself, so a guard proving a
    milestone unchanged names none. ``removed`` and ``opened`` are the owned
    rows it retires and registers. ``derived`` records the originals the unit
    transformed and the rows it left of each, for a later unit of the same
    flush whose conditions those originals carry; a unit no later one depends
    on records none. ``concludes`` names the object of a range that follows
    ordering barriers and leads none: no later unit of the flush consumes what
    earlier units proved about that object.
    """

    changed: Iterable[ObservedStateKey] = ()
    removed: Iterable[OwnedEndpoint] = ()
    opened: Openings = NO_OPENINGS
    derived: tuple[Derivation, ...] = ()
    concludes: ObjectKey | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BoundRange(UnitEffects):
    """What a range became once bound to its coverage: the physical steps it
    executes, in order, beside the effects their success publishes."""

    steps: tuple[PlannedWrite, ...]


class DeferredRange:
    """A finalized range whose physical steps depend on coverage no planning
    input knew, which the unit of work that planned it binds at its unit's
    turn. Field-free here: what binding reads belongs to its unit-of-work
    subclass."""

    __slots__ = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionUnit(UnitEffects):
    """One execution unit of a Write Plan and what its success publishes.

    A unit spans the plan's steps up to the exclusive offset ``end``, after the
    previous unit's. Its effects are applied only once every one of its steps
    has succeeded, and before any later unit executes, after it spends the
    source authority ``claim``. Removals are retired before openings are
    registered, so a row removed and reopened at one address remains owned, and
    an insertion whose last row the unit removed still stands when a row the
    unit opened continues it.

    A unit with a ``deferred`` range has no planned step of its own: its steps
    and effects come from binding that range at the unit's turn.
    """

    end: int
    claim: SourceAuthority | None = None
    deferred: DeferredRange | None = None


@dataclass(frozen=True, slots=True)
class WritePlan:
    """One flush's finalized, execution-ordered steps.

    An empty :class:`PlannedSteps` is the one canonical result for complete
    cancellation or known no-op elimination; there is no empty-plan sentinel and
    no second result variant.

    ``units`` partitions ``steps`` into execution units, in order and ending
    where the steps end; a plan given none forms one unit of every step, which
    publishes nothing.
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
