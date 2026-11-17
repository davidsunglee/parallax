from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from parallax.core.internal.metamodel import EntityIdentity
from parallax.core.internal.planned_step.keys import (
    ObjectKey,
    ObjectStateKey,
    VersionedObjectStateKey,
)
from parallax.core.internal.planned_step.observe import PredecessorRow
from parallax.core.internal.planned_step.steps import (
    INFINITY,
    PlannedStep,
    PlannedTemporalRevision,
    TemporalUpperBound,
    WriteRow,
)
from parallax.core.internal.temporal_read import TimeInterval

__all__ = [
    "NO_OPENINGS",
    "NO_TEMPORAL_WRITE_OWNERSHIP",
    "OPEN_BITEMPORAL_ENDS",
    "TRANSACTION_TIME_ENDS",
    "BoundRange",
    "CurrentRowOutput",
    "Derivation",
    "DerivedRow",
    "EffectShapeOf",
    "EffectSpan",
    "Openings",
    "TemporalRowCoordinates",
    "TemporalWriteOwnership",
    "WriteEffects",
]


@dataclass(frozen=True, slots=True)
class TemporalRowCoordinates:
    """The coordinates identifying one physical temporal row: its Entity, its
    family primary-key values in key order, and one **exclusive upper bound**
    per As-Of Axis in canonical axis order.

    Axis starts and payload are not part of them, so a same-address revision
    keeps its row's coordinates. They identify a row and prove nothing: neither
    that this attempt owns it nor that any source may write it.
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
    """One current row a settled write left of a predecessor: its coordinates,
    the Valid Time the row covers, and the part of it the predecessor
    contributed — the whole row unless the row merged successors of several
    predecessors. Both are ``None`` on a Transaction-Time-Only object."""

    coordinates: TemporalRowCoordinates
    valid_time_coverage: TimeInterval | None
    contributed: TimeInterval | None


@dataclass(frozen=True, slots=True)
class Derivation:
    """One predecessor a settled write changed under protection — a guarded
    effect that succeeded, or the shared lock the write held — and the current
    rows it left in that predecessor's place.

    ``predecessor`` is the exact state the write found, ``valid_time_coverage``
    the Valid Time it covered (``None`` on a Transaction-Time-Only object), and
    ``input_coordinates`` its coordinates where the attempt had opened it,
    ``None`` for any other predecessor. ``rows`` holds each nonempty row the
    write derived from it, a row revised in place among them, with the part of
    each the predecessor contributed. It describes one execution's geometry and
    is never retained as history.
    """

    predecessor: ObjectStateKey
    valid_time_coverage: TimeInterval | None
    input_coordinates: TemporalRowCoordinates | None
    rows: tuple[DerivedRow, ...]


@dataclass(frozen=True, slots=True)
class CurrentRowOutput:
    """A current row a settled write produces that a source of the attempt may
    continue from, described before execution: its ``coordinates``, the Valid
    Time it covers (``None`` on a Transaction-Time-Only object), its complete
    logical ``row``, and the ``emitter`` that persists it — the insert entry,
    which is ``row`` itself, or the in-place revision of a row whose raw
    document was ``predecessor_document``.

    It is a description, not a captured value: execution pairs it with the
    persisted document the emitter's payload actually stores.
    """

    coordinates: TemporalRowCoordinates
    valid_time_coverage: TimeInterval | None
    row: WriteRow
    emitter: WriteRow | PlannedTemporalRevision
    predecessor_document: object | None = None


class TemporalWriteOwnership(Protocol):
    """Read-only access to the temporal rows the planning attempt opened
    successfully, and to what its completed writes left for the sources it
    may still continue.

    It reads the attempt's own record of executed openings, never an
    inference from a row's Transaction-Time start equalling the attempt's
    instant, and is neither a copy of that record nor source authority.
    """

    def owns(self, coordinates: TemporalRowCoordinates, /) -> bool: ...

    def continues_insertion(self, coordinates: TemporalRowCoordinates, /) -> bool:
        """Whether an admitted insertion contributed any part of the owned row
        at ``coordinates`` (:meth:`insertion_coverage`)."""
        ...

    def insertion_coverage(
        self, coordinates: TemporalRowCoordinates, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        """The parts of the owned row at ``coordinates``, which covers
        ``valid_time_coverage``, that an admitted insertion standing when it
        opened contributed, in order — the whole row, or only some of a row
        that merged other coverage — so that the same parts of its successors
        continue it. Empty where no insertion contributed any."""
        ...

    def demanded(
        self, predecessor: ObjectStateKey, coordinates: TemporalRowCoordinates | None, /
    ) -> bool:
        """Whether a source the attempt may still continue reaches the current
        row in state ``predecessor`` — at ``coordinates``, where the attempt
        opened it — so changing it must say what it leaves in its place."""
        ...

    def continues(self, observation: Hashable, pin: dt.datetime | None, /) -> bool | None:
        """Whether a source sharing ``observation`` continues at Valid-Time
        ``pin`` — at any surviving part where ``pin`` is ``None`` — through
        what the attempt's completed writes left of the state it observed;
        ``None`` where no completed write changed that state."""
        ...

    def current_rows(
        self, target: ObjectKey, valid_time_window: TimeInterval | None, /
    ) -> Sequence[PredecessorRow]:
        """The complete state of every current row of ``target`` overlapping
        ``valid_time_window`` — every one where it is ``None`` — that the
        attempt's completed writes produced and still hold, in Valid-Time
        order, whichever source's continuation they are held for."""
        ...


@dataclass(frozen=True, slots=True)
class _NoTemporalWriteOwnership:
    def owns(self, coordinates: TemporalRowCoordinates, /) -> bool:
        del coordinates
        return False

    def continues_insertion(self, coordinates: TemporalRowCoordinates, /) -> bool:
        del coordinates
        return False

    def insertion_coverage(
        self, coordinates: TemporalRowCoordinates, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        del coordinates, valid_time_coverage
        return ()

    def demanded(
        self, predecessor: ObjectStateKey, coordinates: TemporalRowCoordinates | None, /
    ) -> bool:
        del predecessor, coordinates
        return False

    def continues(self, observation: Hashable, pin: dt.datetime | None, /) -> bool | None:
        del observation, pin
        return None

    def current_rows(
        self, target: ObjectKey, valid_time_window: TimeInterval | None, /
    ) -> Sequence[PredecessorRow]:
        del target, valid_time_window
        return ()


NO_TEMPORAL_WRITE_OWNERSHIP: Final[TemporalWriteOwnership] = _NoTemporalWriteOwnership()
"""The ownership of an attempt that has opened nothing."""


@dataclass(frozen=True, slots=True)
class Openings:
    """The owned rows a settled write opens, by what each derives from:
    ``continued`` holds an insert's row and every row an admitted insertion
    contributed whole, ``shared`` each row it contributed only some parts of,
    with those parts in order, and ``fresh`` every other row. A row the write
    revised in place into a merged extent, or whose insertion's parts it
    narrowed, is among them again at its own coordinates."""

    fresh: Iterable[TemporalRowCoordinates] = ()
    continued: Iterable[TemporalRowCoordinates] = ()
    shared: Iterable[tuple[TemporalRowCoordinates, tuple[TimeInterval, ...]]] = ()


NO_OPENINGS: Final[Openings] = Openings()


@dataclass(frozen=True, slots=True, kw_only=True)
class WriteEffects:
    """What one write's success publishes, complete: the changes to the
    attempt's state completion applies once every step of the write's Write
    Group has succeeded. It is prepared before any step executes and records
    no execution result.

    ``changed`` names every state the write changes, its own source's
    included — an Observed State Key for a versioned or temporal object and an
    Object Key for each unversioned Non-Temporal one — for the freshness of
    reads that acquired rows before it; executing a step changes nothing by
    itself, so a guard proving a milestone unchanged names none. ``advanced``
    names the protected state each surviving versioned Non-Temporal update
    advanced from, and ``destroyed`` every Non-Temporal object a keyed deletion
    removed. ``removed`` and ``opened`` are the owned rows it retires and
    registers. ``derived`` describes what the write left of each temporal
    predecessor a source of the attempt may still continue from, and
    ``current_outputs`` the rows among them that execution captures as it
    persists them; a write no such source reaches describes neither.
    """

    changed: Iterable[ObjectKey | ObjectStateKey] = ()
    advanced: tuple[VersionedObjectStateKey, ...] = ()
    destroyed: tuple[ObjectKey, ...] = ()
    removed: Iterable[TemporalRowCoordinates] = ()
    opened: Openings = NO_OPENINGS
    derived: tuple[Derivation, ...] = ()
    current_outputs: tuple[CurrentRowOutput, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class BoundRange(WriteEffects):
    """What a range became once bound to its coverage: the Planned Steps it
    executes, in order, beside the effects their success publishes."""

    steps: tuple[PlannedStep, ...]


type EffectShapeOf = Callable[[PlannedStep], Hashable | None]
"""The shape of one effect — a non-insert step — that execution may present
with every other effect of an equal shape as one statement, compared by
equality; ``None`` where the effect runs alone."""


@dataclass(frozen=True, slots=True)
class EffectSpan:
    """The steps ``[start, stop)`` of a Write Group, at least two, each an
    effect of ``shape``, which execution may present as one grouped effect."""

    start: int
    stop: int
    shape: Hashable
