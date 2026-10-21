from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Protocol

from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan.keys import ObjectKey, ObjectStateKey, VersionedObjectStateKey
from parallax.core.write_plan.steps import INFINITY, PlannedStep, TemporalUpperBound

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
    "DerivedRow",
    "Descent",
    "Openings",
    "OwnedEndpoint",
    "SettledWrite",
    "SourceAuthority",
    "TemporalWriteOwnership",
    "WriteCompletion",
    "WriteGroup",
    "WritePlan",
]


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
    """Temporal source authority admission already accepted, which a
    successful settled write spends."""

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
class WriteCompletion:
    """What one settled write's success publishes, complete.

    ``changed`` names every state the write changes, its own source's
    included — an Observed State Key for a versioned or temporal object and an
    Object Key for each unversioned Non-Temporal one — for the freshness of
    reads that acquired rows before it; executing a step changes nothing by
    itself, so a guard proving a milestone unchanged names none. ``advanced``
    names the protected state each surviving versioned Non-Temporal update
    advanced from, and ``destroyed`` every Non-Temporal object a keyed deletion
    removed. ``removed`` and ``opened`` are the owned rows it retires and
    registers. ``derived`` records the originals the write transformed and the
    rows it left of each, for a later settled write of the same flush whose
    conditions those originals carry; a write no later one depends on records
    none. ``concludes`` names the object of a range that follows ordering
    barriers and leads none: no later settled write of the flush consumes what
    earlier ones proved about that object.
    """

    changed: Iterable[ObjectKey | ObjectStateKey] = ()
    advanced: tuple[VersionedObjectStateKey, ...] = ()
    destroyed: tuple[ObjectKey, ...] = ()
    removed: Iterable[OwnedEndpoint] = ()
    opened: Openings = NO_OPENINGS
    derived: tuple[Derivation, ...] = ()
    concludes: ObjectKey | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BoundRange(WriteCompletion):
    """What a range became once bound to its coverage: the Planned Steps it
    executes, in order, beside the completion their success publishes."""

    steps: tuple[PlannedStep, ...]


class DeferredRange:
    """A finalized range whose physical steps depend on coverage no planning
    input knew, which the unit of work that planned it binds at its settled
    write's turn. Field-free here: what binding reads belongs to its unit-of-work
    subclass."""

    __slots__ = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SettledWrite(WriteCompletion):
    """One caller write after settlement in a Write Plan, and the completion
    its success publishes.

    Its completion is published only once every step of its Write Group has
    succeeded, and before any later group executes, after it spends the
    temporal source authority ``claim``. Removals are retired before openings
    are registered, so a row removed and reopened at one address remains owned,
    and an insertion whose last row the write removed still stands when a row
    the write opened continues it.

    A settled write with a ``deferred`` range has no planned step of its own:
    its steps and completion come from binding that range at its turn.
    """

    claim: SourceAuthority | None = None
    deferred: DeferredRange | None = None


@dataclass(frozen=True, slots=True)
class WriteGroup:
    """Settled writes that execute and complete together.

    ``steps`` holds their planned steps in execution order. Each of ``writes``
    completes, in order, only once every one of ``steps`` has succeeded, and
    before any step of a later group executes, so no write of a group may
    depend on another's completion. A deferred write's range binds and executes
    at its turn, after the group's steps.
    """

    writes: tuple[SettledWrite, ...]
    steps: tuple[PlannedStep, ...]

    def __post_init__(self) -> None:
        if not self.writes:
            raise ValueError("a Write Group holds at least one settled write")


@dataclass(frozen=True, slots=True)
class WritePlan:
    """One flush's finalized Write Groups, in execution order.

    A plan of no group is the one canonical result for complete cancellation or
    known no-op elimination; there is no empty-plan sentinel and no second
    result variant.
    """

    groups: tuple[WriteGroup, ...] = ()
