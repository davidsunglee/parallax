from __future__ import annotations

import bisect
import datetime as dt
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan.keys import ObjectKey, ObjectStateKey
from parallax.core.write_plan.steps import INFINITY, PlannedStep, TemporalUpperBound

__all__ = [
    "NO_OPENINGS",
    "NO_TEMPORAL_WRITE_OWNERSHIP",
    "OPEN_BITEMPORAL_ENDS",
    "TRANSACTION_TIME_ENDS",
    "AllocatedOpening",
    "BoundRange",
    "CombinedSourceAuthority",
    "CompletionFacts",
    "DeferredRange",
    "Derivation",
    "DerivedRow",
    "Descent",
    "Openings",
    "OwnedEndpoint",
    "PlannedWrites",
    "SettledWrite",
    "SourceAuthority",
    "StepSegment",
    "TemporalWriteOwnership",
    "WritePlan",
    "WriteStepView",
    "eager_segment",
    "eager_writes",
]


class StepSegment(Protocol):
    """One homogeneous, positive-length run of a Write Plan's Planned Steps.

    A segment exposes only its length and a materialize-on-demand accessor;
    nothing about how it is backed is part of the contract.
    """

    def __len__(self) -> int: ...
    def step(self, index: int) -> PlannedStep: ...


@dataclass(frozen=True, slots=True)
class _EagerSegment:
    """A segment over already-settled steps, held as one immutable tuple."""

    steps: tuple[PlannedStep, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("a Step Segment carries at least one step")

    def __len__(self) -> int:
        return len(self.steps)

    def step(self, index: int) -> PlannedStep:
        return self.steps[index]


def eager_segment(steps: Sequence[PlannedStep]) -> StepSegment:
    """A Step Segment wrapping already-settled steps, in order."""
    return _EagerSegment(tuple(steps))


@dataclass(frozen=True, slots=True)
class PlannedWrites:
    """The immutable ordered logical sequence of Planned Steps a Write Plan exposes.

    Backed by segments (:class:`StepSegment`) rather than one flat tuple, each
    asked for one Planned Step at a time.
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

    def __iter__(self) -> Iterator[PlannedStep]:
        for segment in self.segments:
            for index in range(len(segment)):
                yield segment.step(index)

    def __getitem__(self, position: int) -> PlannedStep:
        length = self._length
        resolved = position if position >= 0 else position + length
        if not 0 <= resolved < length:
            raise IndexError(position)
        segment_index = bisect.bisect_right(self._offsets, resolved) - 1
        return self.segments[segment_index].step(resolved - self._offsets[segment_index])

    def view(self, first: int, stop: int) -> WriteStepView:
        """The steps from position ``first`` up to ``stop``, exclusive, borrowed
        from this sequence (:class:`WriteStepView`)."""
        return WriteStepView(self, first, stop)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PlannedWrites):
            return NotImplemented
        return len(self) == len(other) and all(a == b for a, b in zip(self, other, strict=True))

    # Equality reads the logical sequence, not the segmentation, so two
    # Planned Steps values packed differently can compare equal — the same
    # reason no meaningful `__hash__` exists (Planned Steps is a value never
    # used as a mapping/set key).
    __hash__ = None  # pyright: ignore[reportAssignmentType] - deliberately unhashable


@dataclass(frozen=True, slots=True)
class WriteStepView:
    """A contiguous span of one :class:`PlannedWrites` sequence, from position
    ``first`` up to ``stop``, exclusive, possibly empty.

    The view holds its owner and two positions and nothing else. Iterating it
    walks only the owner's segments the span intersects, in order, asking each
    for every spanned step once per pass, so a consumer that keeps the step it
    was handed never has a lazily backed segment rebuild it again.
    """

    owner: PlannedWrites
    first: int
    stop: int

    def __post_init__(self) -> None:
        if not 0 <= self.first <= self.stop <= len(self.owner):
            raise ValueError(
                f"a view spans positions within its {len(self.owner)} Planned Step(s) in "
                f"order, not {self.first} to {self.stop}"
            )

    def __len__(self) -> int:
        return self.stop - self.first

    def __iter__(self) -> Iterator[PlannedStep]:
        position = self.first
        stop = self.stop
        if position == stop:
            return
        owner = self.owner
        offsets = owner._offsets  # pyright: ignore[reportPrivateUsage] - the owner's own index
        segments = owner.segments
        segment_index = bisect.bisect_right(offsets, position) - 1
        while position < stop:
            segment = segments[segment_index]
            base = offsets[segment_index]
            end = min(base + len(segment), stop)
            for index in range(position - base, end - base):
                yield segment.step(index)
            position = end
            segment_index += 1


def eager_writes(steps: Sequence[PlannedStep]) -> PlannedWrites:
    """The Planned Steps sequence of already-settled ``steps``, in order: one
    eager segment, or none for no step."""
    return PlannedWrites((eager_segment(steps),)) if steps else PlannedWrites()


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
class DerivedRow:
    """One current row a settled write left of an original: its address, the Valid Time
    the row covers, and the part of it the original contributed — the whole
    row unless the row merged successors of several contributors. Both are
    ``None`` on a Transaction-Time-Only object."""

    endpoint: OwnedEndpoint
    valid_time_coverage: TimeInterval | None
    contributed: TimeInterval | None


@dataclass(frozen=True, slots=True)
class Derivation:
    """One original a settled write transformed under protection — a guarded
    effect that succeeded, or the shared lock the write held — and the current
    rows it left in that original's place.

    ``original`` is the exact state the write found, ``valid_time_coverage`` the
    Valid Time it covered (``None`` on a Transaction-Time-Only object), and
    ``owned`` its own address where the attempt had opened it. ``rows`` holds
    each nonempty row the write derived from it, a row revised in place among
    them, with the part of each the original contributed.
    """

    original: ObjectStateKey
    valid_time_coverage: TimeInterval | None
    owned: OwnedEndpoint | None
    rows: tuple[DerivedRow, ...]


@dataclass(frozen=True, slots=True)
class Descent:
    """What one current row the attempt opened derives from within the running
    flush: the Valid Time it covers as opened (``None`` on a
    Transaction-Time-Only object), and each protected original that stood
    before the flush began, through however many of its settled writes, beside the
    disjoint part of the row it contributed. A row merged from several
    originals' successors names each; any other names one, over the whole
    row."""

    valid_time_coverage: TimeInterval | None
    contributions: tuple[tuple[ObjectStateKey, TimeInterval | None], ...]

    def original_at(self, instant: dt.datetime | None) -> ObjectStateKey | None:
        """The original whose contribution holds ``instant`` — ``None`` on a
        Transaction-Time-Only object, whose row has one — or ``None`` where
        none does."""
        for original, contributed in self.contributions:
            if contributed is None or (instant is not None and contributed.contains(instant)):
                return original
        return None


class TemporalWriteOwnership(Protocol):
    """Read-only access to the temporal rows the planning attempt opened
    successfully, and to what the running flush's earlier settled writes proved.

    It reads the attempt's own record of executed openings, never an
    inference from a row's Transaction-Time start equalling the attempt's
    instant, and is neither a copy of that record nor source authority.
    """

    def owns(self, endpoint: OwnedEndpoint, /) -> bool: ...

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        """Whether an admitted insertion contributed any part of the owned row
        ``endpoint`` (:meth:`insertion_coverage`)."""
        ...

    def insertion_coverage(
        self, endpoint: OwnedEndpoint, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        """The parts of the owned row ``endpoint``, which covers
        ``valid_time_coverage``, that an admitted insertion standing when it
        opened contributed, in order — the whole row, or only some of a row
        that merged other coverage — so that the same parts of its successors
        continue it. Empty where no insertion contributed any."""
        ...

    def proven(self, original: ObjectStateKey, /) -> Derivation | None:
        """How an earlier settled write of the running flush transformed
        ``original``, if one did."""
        ...

    def descendants(
        self, original: ObjectStateKey, valid_time_window: TimeInterval | None, /
    ) -> Iterable[tuple[OwnedEndpoint, Descent]]:
        """The current rows the running flush derived from ``original``, which
        it proved (:meth:`proven`), whose part ``original`` contributed overlaps
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

    def continues_insertion(self, endpoint: OwnedEndpoint, /) -> bool:
        del endpoint
        return False

    def insertion_coverage(
        self, endpoint: OwnedEndpoint, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        del endpoint, valid_time_coverage
        return ()

    def proven(self, original: ObjectStateKey, /) -> Derivation | None:
        del original
        return None

    def descendants(
        self, original: ObjectStateKey, valid_time_window: TimeInterval | None, /
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
    settled write spends."""

    def consume(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CombinedSourceAuthority:
    """Several distinct source authorities one settled write spends together."""

    members: tuple[SourceAuthority, ...]

    def consume(self) -> None:
        for member in self.members:
            member.consume()


@dataclass(frozen=True, slots=True)
class AllocatedOpening:
    """A row a settled write opens whose key the database allocates: its
    address is complete once the insert that opens it answers the key."""

    entity: EntityIdentity
    ends: tuple[TemporalUpperBound, ...]


@dataclass(frozen=True, slots=True)
class Openings:
    """The owned rows a settled write opens, by what each derives from:
    ``continued`` holds an insert's row and every row an admitted insertion
    contributed whole, ``shared`` each row it contributed only some parts of,
    with those parts in order, and ``fresh`` every other row. A row the write
    revised in place into a merged extent, or whose insertion's parts it
    narrowed, is among them again under its own address. ``allocated`` holds,
    in step order, each row whose key its insert answers."""

    fresh: Iterable[OwnedEndpoint] = ()
    continued: Iterable[OwnedEndpoint] = ()
    allocated: tuple[AllocatedOpening, ...] = ()
    shared: Iterable[tuple[OwnedEndpoint, tuple[TimeInterval, ...]]] = ()


NO_OPENINGS: Final[Openings] = Openings()


@dataclass(frozen=True, slots=True, kw_only=True)
class CompletionFacts:
    """What completing one settled write applies, complete.

    ``changed`` names every observed state the write changes, its own source's
    included; executing a step changes nothing by itself, so a guard proving a
    milestone unchanged names none. ``removed`` and ``opened`` are the owned
    rows it retires and registers. ``derived`` records the originals the write
    transformed and the rows it left of each, for a later settled write of the
    same flush whose conditions those originals carry; a write no later one
    depends on records none. ``concludes`` names the object of a range that
    follows ordering barriers and leads none: no later settled write of the
    flush consumes what earlier ones proved about that object.
    """

    changed: Iterable[ObjectStateKey] = ()
    removed: Iterable[OwnedEndpoint] = ()
    opened: Openings = NO_OPENINGS
    derived: tuple[Derivation, ...] = ()
    concludes: ObjectKey | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BoundRange(CompletionFacts):
    """What a range became once bound to its coverage: the Planned Steps it
    executes, in order, beside the completion facts their success publishes."""

    steps: PlannedWrites


class DeferredRange:
    """A finalized range whose physical steps depend on coverage no planning
    input knew, which the unit of work that planned it binds at its settled
    write's turn. Field-free here: what binding reads belongs to its unit-of-work
    subclass."""

    __slots__ = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SettledWrite(CompletionFacts):
    """One caller write after settlement in a Write Plan, and the completion
    facts its success applies.

    It spans the plan's steps up to the exclusive offset ``end``, after the
    previous settled write's. Its facts are applied only once every one of its
    steps has succeeded, and before any later settled write executes, after it
    spends the source authority ``claim``. Removals are retired before openings
    are registered, so a row removed and reopened at one address remains owned,
    and an insertion whose last row the write removed still stands when a row
    the write opened continues it.

    A settled write with a ``deferred`` range has no planned step of its own:
    its steps and facts come from binding that range at its turn.
    """

    end: int
    claim: SourceAuthority | None = None
    deferred: DeferredRange | None = None


@dataclass(frozen=True, slots=True)
class WritePlan:
    """One flush's finalized, execution-ordered steps.

    An empty :class:`PlannedWrites` is the one canonical result for complete
    cancellation or known no-op elimination; there is no empty-plan sentinel and
    no second result variant.

    ``units`` partitions ``steps`` into settled writes, in order and ending
    where the steps end; a plan given none forms one settled write of every step,
    which publishes nothing.
    """

    steps: PlannedWrites = PlannedWrites()
    units: tuple[SettledWrite, ...] = ()

    def __post_init__(self) -> None:
        length = len(self.steps)
        units = self.units
        if not units:
            if length:
                object.__setattr__(self, "units", (SettledWrite(end=length),))
            return
        previous = 0
        for unit in units:
            if unit.end < previous:
                raise ValueError("a Write Plan's settled writes follow its steps in order")
            previous = unit.end
        if previous != length:
            raise ValueError(
                f"a Write Plan's settled writes end where its {length} step(s) end, not at "
                f"{previous}"
            )
