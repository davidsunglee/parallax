from __future__ import annotations

import bisect
import datetime as dt
import weakref
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
from dataclasses import replace
from enum import Enum
from typing import Final, Literal, cast, final

from parallax.core import temporal_read
from parallax.core._execution._unit_work._errors import KeyedWriteValueError, UnitOfWorkError
from parallax.core._execution._unit_work.instructions import ASSIGNMENT_MUTATIONS
from parallax.core._execution._unit_work.retain import (
    NO_INSERTION_AUTHORITY,
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    NoInsertionAuthority,
    ReadEvidence,
    RetainedObservation,
)
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    InsertionAuthorizedWrite,
    KeyedInsert,
    ReadAuthorizedWrite,
)
from parallax.core.base import INFINITY, TemporalBound, retain_document_value
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import TimeInterval
from parallax.core.temporal_write.coverage import CoverageTransform
from parallax.core.write_plan.keys import (
    ObjectKey,
    ObjectStateKey,
    TemporalObjectStateKey,
    VersionedObjectStateKey,
)
from parallax.core.write_plan.observe import PredecessorRow
from parallax.core.write_plan.plan import (
    CurrentRowOutput,
    Derivation,
    Openings,
    TemporalRowCoordinates,
)
from parallax.core.write_plan.steps import Finite, MaxPlusOne, SelfIncrement

__all__ = [
    "InsertionComposition",
    "SourceRefusal",
    "SourceScope",
    "WriteOwnership",
]

type _PendingInsertionState = Literal["opening", "ended_opening"]
"""How an insertion of the buffer stands, while the buffer holds it.

``opening`` is the object's current insertion, still to execute, which a later
write of the object folds into — for a Bitemporal object, only a write that
insertion authorized. ``ended_opening`` is a Bitemporal opening whose
writes left nothing of it while a composed replacement still reaches the
object's older stored coverage, so it folds nothing and its object is opened
again only after that replacement.
"""


class InsertionComposition(Enum):
    """What composing a write into its object's still-pending insertion did to
    that insertion.

    ``SURVIVES``: the insertion still opens something and stands. ``ENDED``: a
    Bitemporal opening its writes left nothing of, whose composed replacement
    still reaches older stored coverage; its work stays where it is and its
    authority ends. ``CANCELLED``: nothing of the pair remains, and the
    insertion's authority ends with it.
    """

    SURVIVES = "survives"
    ENDED = "ended"
    CANCELLED = "cancelled"


class InsertionRecord:
    """What one attempt holds about one object it inserted.

    ``insertion_advice`` is the refusal advice the latest insertion's opener
    supplied, kept for a repeat's diagnostics, and ``valid_time_window`` is the
    window it was admitted with, ``None`` for an object without Valid Time — its
    start is the anchor every write it authorizes starts at. ``identity`` is the
    authority that insertion grants while it stands, and ``None`` once its
    complete removal, or a composition leaving nothing of it, retired it.
    ``pending_state`` is how the insertion stands in the buffer that buffered
    it, until the buffer drains or composition cancels it.

    What survives of the object's admitted insertions is counted where it is
    stored: ``stored_count`` — the owned current rows an admission of the
    object opened, by their tags — for a Bitemporal object, whose coverage a
    write can remove in part, and zero or one for any other, which a removal
    takes whole. ``earliest_stored_anchor`` is the earliest anchor of any
    admission whose coverage may still be stored — once a flush executes an
    insertion, its own anchor, since what an earlier admission opened was
    removed before it — and ``produced_version`` the version the last completed
    update of a versioned row produced since the latest insertion opened.
    ``cached_removal_window`` keeps the stored removal window once it is asked
    for (:meth:`WriteOwnership._removal_window`), until what it derives from
    changes. A record lasts until the attempt ends, whatever became of the
    insertion: it is also the fact that this attempt admitted one.
    """

    __slots__ = (
        "cached_removal_window",
        "earliest_stored_anchor",
        "identity",
        "insertion_advice",
        "pending_state",
        "produced_version",
        "stored_count",
        "valid_time_window",
    )

    def __init__(
        self,
        insertion_advice: KeyedWriteRefusalAdvice | None,
        valid_time_window: TimeInterval | None,
        identity: InsertionIdentity,
    ) -> None:
        self.insertion_advice = insertion_advice
        self.valid_time_window = valid_time_window
        self.identity: InsertionIdentity | None = identity
        self.pending_state: _PendingInsertionState | None = "opening"
        self.stored_count = 0
        self.earliest_stored_anchor = _window_start(valid_time_window)
        self.produced_version: int | None = None
        self.cached_removal_window: TimeInterval | _Uncomputed = _UNCOMPUTED

    def set_earliest_stored_anchor(self, anchor: dt.datetime | None) -> None:
        if anchor != self.earliest_stored_anchor:
            self.earliest_stored_anchor = anchor
            self.cached_removal_window = _UNCOMPUTED

    @property
    def has_stored_coverage(self) -> bool:
        """Whether anything an admitted insertion of the object opened may
        still be stored."""
        return self.stored_count > 0

    def unlink(self) -> None:
        self.pending_state = None


@final
class _Uncomputed:
    """The removal window a record has not derived since what it derives from
    last changed — distinct from every window, and from a missing Valid-Time
    axis."""

    __slots__ = ()


_UNCOMPUTED: Final = _Uncomputed()


def _window_start(window: TimeInterval | None) -> dt.datetime | None:
    return None if window is None else window.start


type _ObjectAddress = tuple[EntityIdentity, tuple[object, ...]]

type _InsertionTag = tuple[InsertionIdentity, tuple[TimeInterval, ...] | None]
"""The admission an owned row continues, and the parts of the row it
contributed in order, ``None`` where it contributed the whole row."""

type SourceScope = RetainedObservation | VersionedObjectStateKey | ObjectKey
"""The protected state a source's authority reaches: the shared observation of
a temporal source, whose writes settle against what this attempt's completed
writes left of it; a versioned Non-Temporal row's exact state; or an
unversioned Non-Temporal row's object, whose shared lock covers every state it
is in."""


class SourceRefusal(Enum):
    """Why a source's evidence reaches no protected state.

    ``STALE`` evidence was published from rows a read acquired before a
    completed write of this attempt changed them. ``ENDED`` evidence's object a
    completed keyed deletion of this attempt removed after its read, or, for a
    temporal source, its completed writes left nothing of the state it observed
    at its Valid-Time pin.
    """

    STALE = "stale"
    ENDED = "ended"


class _ReadRegistration(weakref.ref[ReadEvidence]):
    """The exact weak reference one Non-Temporal Read Evidence published
    after a completed change of this attempt is registered by.

    ``key`` is the evidence's identity, which the registration is indexed by
    and still names once the evidence is gone. ``read_at`` is the change count
    its read captured, which places the read before or after each later
    destruction of its object, and ``None`` for evidence its publication judged
    stale.
    """

    __slots__ = ("key", "read_at")

    key: int
    read_at: int | None

    def __new__(
        cls,
        evidence: ReadEvidence,
        callback: Callable[[_ReadRegistration], object],
        read_at: int | None,
    ) -> _ReadRegistration:
        registration = super().__new__(cls, evidence, callback)
        registration.key = id(evidence)
        registration.read_at = read_at
        return registration

    def __init__(
        self,
        evidence: ReadEvidence,
        callback: Callable[[_ReadRegistration], object],
        read_at: int | None,
    ) -> None:
        # The reference is made whole by __new__.
        del evidence, callback, read_at

    @property
    def fresh_at_publication(self) -> bool:
        """The judgment made once, when the evidence was published: whether no
        completed write of the attempt had changed what its read acquired."""
        return self.read_at is not None


class _Contribution:
    """The part of one current row, at ``coordinates``, that one origin's
    observed state contributed: ``coverage``, or the whole row of a
    Transaction-Time-Only object where it is ``None``."""

    __slots__ = ("coordinates", "coverage", "origin")

    def __init__(
        self, origin: _Origin, coordinates: TemporalRowCoordinates, coverage: TimeInterval | None
    ) -> None:
        self.origin = origin
        self.coordinates = coordinates
        self.coverage = coverage


class _OriginLineage:
    """The surviving parts of current rows one origin's observed state
    contributed, in Valid-Time order.

    They are pieces of one observed row's coverage and so never overlap, which
    is what lets :meth:`at` find the one holding a pin by its start alone. An
    origin without Valid Time contributes to at most one current row, keyed at
    the earliest instant.
    """

    __slots__ = ("contributions", "starts")

    def __init__(self) -> None:
        self.contributions: list[_Contribution] = []
        self.starts: list[dt.datetime] = []

    def add(self, contribution: _Contribution) -> None:
        start = _start_key(contribution.coverage)
        position = bisect.bisect_right(self.starts, start)
        self.starts.insert(position, start)
        self.contributions.insert(position, contribution)

    def discard(self, contribution: _Contribution) -> None:
        position = bisect.bisect_left(self.starts, _start_key(contribution.coverage))
        assert self.contributions[position] is contribution  # one origin's parts never overlap
        del self.contributions[position]
        del self.starts[position]

    def at(self, pin: dt.datetime | None) -> bool:
        """Whether some surviving part holds Valid-Time ``pin`` — whether any
        part survives at all where it is ``None``."""
        contributions = self.contributions
        if pin is None or not contributions:
            return bool(contributions)
        position = bisect.bisect_right(self.starts, pin) - 1
        if position < 0:
            return False
        coverage = contributions[position].coverage
        return coverage is None or coverage.contains(pin)


class _Origin(weakref.ref[RetainedObservation]):
    """One observed state a completed write of the attempt changed, by a weak
    reference to the observation every source of it shares, and what survives
    of it.

    ``key`` is the observation's identity, which the origin is indexed by and
    still names once the observation is gone. ``lineage`` holds its surviving
    contributions, empty where nothing of it survives; existing at all is what
    tells a changed state from one no completed write reached.
    """

    __slots__ = ("key", "lineage")

    key: int
    lineage: _OriginLineage

    def __new__(
        cls, observation: RetainedObservation, callback: Callable[[_Origin], object]
    ) -> _Origin:
        origin = super().__new__(cls, observation, callback)
        origin.key = id(observation)
        origin.lineage = _OriginLineage()
        return origin

    def __init__(
        self, observation: RetainedObservation, callback: Callable[[_Origin], object]
    ) -> None:
        # The reference is made whole by __new__.
        del observation, callback


class _HeldCurrentRows:
    """The current rows of one object the attempt's completed writes produced
    and still hold for some source's continuation, in Valid-Time order: each
    at its coordinates, over its Valid Time, with its complete state.
    ``starts`` and ``held`` are derived from ``rows``, for lookup by start and
    by coordinates."""

    __slots__ = ("held", "rows", "starts")

    def __init__(self) -> None:
        self.rows: list[tuple[TemporalRowCoordinates, TimeInterval | None, PredecessorRow]] = []
        self.starts: list[dt.datetime] = []
        self.held: dict[TemporalRowCoordinates, dt.datetime] = {}

    def put(
        self,
        coordinates: TemporalRowCoordinates,
        coverage: TimeInterval | None,
        row: PredecessorRow,
    ) -> None:
        self.drop(coordinates)
        start = _start_key(coverage)
        position = bisect.bisect_right(self.starts, start)
        self.starts.insert(position, start)
        self.rows.insert(position, (coordinates, coverage, row))
        self.held[coordinates] = start

    def drop(self, coordinates: TemporalRowCoordinates) -> None:
        start = self.held.pop(coordinates, None)
        if start is None:
            return
        position = bisect.bisect_left(self.starts, start)
        assert self.rows[position][0] == coordinates  # one object's current rows never overlap
        del self.rows[position]
        del self.starts[position]

    def overlapping(self, window: TimeInterval | None) -> list[PredecessorRow]:
        """Every row overlapping ``window``, every row where it is ``None``:
        those starting before its end, from the last one starting at or before
        its start."""
        rows = self.rows
        if window is None:
            return [row for _coordinates, _coverage, row in rows]
        starts = self.starts
        first = max(bisect.bisect_right(starts, window.start) - 1, 0)
        end = window.end
        last = len(starts) if end is INFINITY else bisect.bisect_left(starts, end)
        return [
            row
            for _coordinates, coverage, row in rows[first:last]
            if coverage is None or coverage.overlaps(window)
        ]


class _Release:
    """The one callback every weak reference of an ownership shares, holding
    its owner weakly, so neither a reference nor what it refers to keeps the
    attempt's ownership alive."""

    __slots__ = ("_owner",)

    def __init__(self, owner: WriteOwnership) -> None:
        self._owner = weakref.ref(owner)

    def __call__(self, reference: _ReadRegistration | _Origin) -> None:
        owner = self._owner()
        if owner is None:
            return
        if isinstance(reference, _Origin):
            owner._prune_origin(reference)  # pyright: ignore[reportPrivateUsage] - the reference's own owner
        else:
            owner._release_read_evidence(reference)  # pyright: ignore[reportPrivateUsage] - the reference's own owner


class WriteOwnership:
    """The attempt's write-owned facts about the objects it writes.

    Each target's admitted insertion, which only this owner's named
    transitions open, compose, plan, store, and retire, and every current
    temporal row the attempt successfully opened, by its coordinates. A row of
    a Bitemporal object that continues an admission standing when it opens — the
    admission's own insert, or a successor of the part of a row an admission
    contributed — is tagged with that admission's identity, and with the parts
    of it the admission contributed where that is not the whole row; a
    successor of coverage no admission opened is not. Reads add no row to it,
    so its rows follow what the attempt wrote rather than what it read.

    It also answers what this attempt's completed writes did to the states its
    sources reach, deriving every judgment from those writes rather than from
    the reads that published the sources:

    * Each versioned Non-Temporal object a completed update advanced keeps the
      version its first such update advanced from and the version the latest
      produced, and each object a completed keyed deletion removed keeps when
      that happened. Non-Temporal evidence a read published after a completed
      change is registered by a weak identity reference with what its
      publication judged, and its registration goes with the last value or
      pending or planned write reaching it.
    * A temporal source's demand is the observation it shares with every other
      source of the same state, which the unit of work indexes as
      ``observations`` while some value or pending or planned write keeps it
      alive. Only a completed write changing an observed state a live
      observation describes, or a row descending from one, records what
      survives of that state — the parts of current rows it contributed — and
      the complete state of those rows its execution captured. Both are
      released when that observation is collected, however its sources were
      judged.

    A source holds nothing of its ownership. ``version_after`` answers the
    version a row of an Entity holds once a completed update advanced it from a
    version, or, from none, the version an insert stores.
    """

    __slots__ = (
        "__weakref__",
        "_addresses",
        "_contributions",
        "_current_rows",
        "_current_versions",
        "_destroyed",
        "_observations",
        "_origins",
        "_owned",
        "_pending_prunes",
        "_read_registrations",
        "_records",
        "_release",
        "_tags",
        "_temporal_facet",
        "_updating",
        "_version_after",
    )

    def __init__(
        self,
        meta: Metamodel,
        *,
        version_after: Callable[[EntityIdentity, int | None], int | None],
        observations: Mapping[ObjectStateKey, RetainedObservation],
    ) -> None:
        self._temporal_facet = temporal_read.view(meta)
        self._version_after = version_after
        self._observations = observations
        # Every registered Non-Temporal source by its evidence's identity; each
        # versioned object's protected versions, from the one its first
        # completed update advanced from to the one its latest produced; and
        # the change count at which a completed deletion last removed each
        # object.
        self._read_registrations: dict[int, _ReadRegistration] = {}
        self._current_versions: dict[ObjectKey, tuple[int, int]] = {}
        self._destroyed: dict[ObjectKey, int] = {}
        # Every changed observed state by its observation's identity; each
        # current row's contributions, the reverse view of the same facts; and
        # each object's captured current rows. An origin collected while a
        # completion is changing them is pruned once that completion is done.
        self._origins: dict[int, _Origin] = {}
        self._contributions: dict[TemporalRowCoordinates, list[_Contribution]] = {}
        self._current_rows: dict[_ObjectAddress, _HeldCurrentRows] = {}
        self._updating = False
        self._pending_prunes: list[_Origin] = []
        self._release = _Release(self)
        self._records: dict[ObjectKey, InsertionRecord] = {}
        # The Bitemporal records again, by the address an owned row names its
        # object with, so tagging a row needs no key of its own.
        self._addresses: dict[_ObjectAddress, InsertionRecord] = {}
        self._owned: set[TemporalRowCoordinates] = set()
        self._tags: dict[TemporalRowCoordinates, _InsertionTag] = {}

    def owns(self, coordinates: TemporalRowCoordinates, /) -> bool:
        return coordinates in self._owned

    def continues_insertion(self, coordinates: TemporalRowCoordinates, /) -> bool:
        return coordinates in self._tags

    def insertion_coverage(
        self, coordinates: TemporalRowCoordinates, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        tag = self._tags.get(coordinates) if self._tags else None
        if tag is None:
            return ()
        parts = tag[1]
        if parts is None or valid_time_coverage is None:
            return (valid_time_coverage,)
        return tuple(
            part
            for part in (part.intersection(valid_time_coverage) for part in parts)
            if part is not None
        )

    def demanded(
        self, predecessor: ObjectStateKey, coordinates: TemporalRowCoordinates | None, /
    ) -> bool:
        if coordinates is not None and coordinates in self._contributions:
            return True
        observation = self._observations.get(predecessor)
        return observation is not None and self._origin(observation) is None

    def continues(self, observation: Hashable, pin: dt.datetime | None, /) -> bool | None:
        origin = self._origin(observation)
        return None if origin is None else origin.lineage.at(pin)

    def current_rows(
        self, target: ObjectKey, valid_time_window: TimeInterval | None, /
    ) -> Sequence[PredecessorRow]:
        rows = self._current_rows.get(_address(target)) if self._current_rows else None
        return () if rows is None else rows.overlapping(valid_time_window)

    def register_read_evidence(
        self,
        evidence: ReadEvidence,
        *,
        read_at: int,
        current: Callable[[ObjectKey | ObjectStateKey, int], bool],
    ) -> None:
        """Register ``evidence`` a read capturing change count ``read_at``
        published, judged by whether what it observed is still ``current``.

        A Non-Temporal source published fresh, of an object no completed
        deletion removed, was read before any deletion that completes later,
        which is what unregistered evidence answers, so only the rest are
        registered. A temporal source registers nothing: its shared
        observation, which the unit of work indexes or refuses as stale, is
        what any later judgment of it reads."""
        observation = evidence.observation
        state: VersionedObjectStateKey | ObjectKey
        if observation is None:
            target = state = evidence.object_key
        elif isinstance(observation.key, VersionedObjectStateKey):
            state = observation.key
            target = state.object
        else:
            return
        fresh = current(state, read_at)
        if fresh and target not in self._destroyed:
            return
        self._read_registrations[id(evidence)] = _ReadRegistration(
            evidence, self._release, read_at if fresh else None
        )

    def resolve_source(self, evidence: ReadEvidence) -> SourceScope | SourceRefusal:
        """The protected state ``evidence``'s authority reaches, or why it
        reaches none.

        A temporal source reaches the state it observed while no completed
        write changed it, and what those writes left of it while some part
        holds its Valid-Time pin. A Non-Temporal source reaches the state it
        observed, or the version this attempt's completed updates produced from
        it; unregistered Non-Temporal evidence was published fresh, before any
        completed deletion of its object, so it was read before every one of
        them.
        """
        observation = evidence.observation
        if observation is not None and isinstance(observation.key, TemporalObjectStateKey):
            if not observation.invalidated:
                return observation
            reach = self.continues(observation, _finite_valid_time(evidence))
            if reach is None:
                return SourceRefusal.STALE
            return observation if reach else SourceRefusal.ENDED
        registration = self._read_registrations.get(id(evidence))
        read_at = 0
        if registration is not None and registration() is evidence:
            if not registration.fresh_at_publication:
                return SourceRefusal.STALE
            read_at = cast("int", registration.read_at)
        target = evidence.object_key
        destroyed = self._destroyed.get(target) if self._destroyed else None
        if destroyed is not None and destroyed > read_at:
            return SourceRefusal.ENDED
        if observation is None:
            return target
        observed = observation.key
        assert isinstance(observed, VersionedObjectStateKey)  # a Non-Temporal observation
        versions = self._current_versions.get(target)
        if versions is None or not versions[0] <= observed.version < versions[1]:
            return observed
        return VersionedObjectStateKey(target, versions[1])

    def continue_sources(
        self,
        advanced: Iterable[VersionedObjectStateKey],
        destroyed: Iterable[ObjectKey],
        *,
        at: int,
    ) -> None:
        """Publish what one successful settled write, completing at change
        count ``at``, did to the protected states Non-Temporal sources reach:
        each versioned state it ``advanced`` from now stands at the version it
        produced, and each object it ``destroyed`` ends every source read before
        it, so no later state of the object, a reinserted one's included,
        revives them. A versioned row this attempt inserted stands at the
        version produced, which a write its insertion authorizes claims from
        then on."""
        versions = self._current_versions
        records = self._records
        for state in advanced:
            target = state.object
            produced = self._version_after(target.entity, state.version)
            assert produced is not None  # only a versioned row advances
            held = versions.get(target)
            first = held[0] if held is not None and held[1] == state.version else state.version
            versions[target] = (first, produced)
            record = records.get(target) if records else None
            if record is not None:
                record.produced_version = produced
        for target in destroyed:
            self._destroyed[target] = at
            versions.pop(target, None)

    def _release_read_evidence(self, registration: _ReadRegistration) -> None:
        """Forget a registration whose evidence is gone."""
        key = registration.key
        if self._read_registrations.get(key) is registration:
            del self._read_registrations[key]

    def has_admitted_insertion(self, target: ObjectKey) -> bool:
        """Whether this attempt admitted an insertion of ``target`` at all,
        whether or not any insertion of it still stands."""
        return target in self._records

    def insertion_authority(
        self, identity: InsertionIdentity
    ) -> TimeInterval | NoInsertionAuthority | None:
        """The Valid-Time window the insertion ``identity`` names was admitted
        with while its authority stands, ``None`` for a standing insertion of
        an object without Valid Time, or :data:`NO_INSERTION_AUTHORITY` once it
        does not stand: never issued here, retired, or superseded by a later
        insertion of the same object."""
        record = self._standing(identity)
        return NO_INSERTION_AUTHORITY if record is None else record.valid_time_window

    def open_insertion(
        self,
        insert: KeyedInsert,
        *,
        pending_removal: CoverageTransform | None,
        removes_object: bool,
        insertion_advice: KeyedWriteRefusalAdvice | None,
    ) -> tuple[InsertionIdentity, bool]:
        """Open an insertion of the object ``insert`` names, superseding the
        authority of any earlier one, and answer the identity it issues beside
        whether the insert must follow a pending removal — or refuse a repeat,
        with nothing changed.

        A repeat is an insert of an object whose admitted insertion still
        stands: one still pending, or one whose stored coverage survives what
        is pending. It is refused with the advice the standing insertion's
        opener supplied, and admitted where that opener supplied none.
        ``removes_object`` is whether a pending write removes a Non-Temporal or
        Transaction-Time-Only object whole, and ``pending_removal`` what the
        pending writes of a Bitemporal object do to its existing coverage. Once
        they remove everything the object's admissions left stored, or once
        composition ended its pending opening, the insert is a first opening
        again, which executes after that removal. ``insertion_advice`` is kept
        for a repeat of this insertion.
        """
        target = insert.object_key
        assert target is not None  # a key the database allocates opens no insertion
        window = insert.instruction.valid_time_window
        record = self._records.get(target)
        if record is None:
            identity = InsertionIdentity(target)
            record = InsertionRecord(insertion_advice, window, identity)
            self._records[target] = record
            if window is not None:
                self._addresses[_address(target)] = record
            return identity, False
        removed = self._removed_whole(record, pending_removal, removes_object)
        if not removed and (record.pending_state == "opening" or record.has_stored_coverage):
            advice = record.insertion_advice
            if advice is not None:
                raise _repeated_insert(insert, advice)
        follows_removal = removed or record.pending_state == "ended_opening"
        identity = InsertionIdentity(target)
        if not record.has_stored_coverage:
            record.set_earliest_stored_anchor(_window_start(window))
        record.insertion_advice = insertion_advice
        record.valid_time_window = window
        record.identity = identity
        record.pending_state = "opening"
        record.produced_version = None
        return identity, follows_removal

    def apply_insertion_composition(
        self,
        target: ObjectKey,
        *,
        arriving: ReadAuthorizedWrite | InsertionAuthorizedWrite,
        proposed_opening: ComposedBitemporalOpening | None,
    ) -> InsertionComposition:
        """What composing ``arriving`` into the still-pending insertion of
        ``target`` does to that insertion, ending its authority where nothing
        of it survives.

        A Bitemporal opening is judged by ``proposed_opening``, the opening
        with ``arriving`` composed over its coverage: it survives while some of
        the opened coverage survives or an assignment remains, and otherwise
        ends where a composed replacement reaches stored coverage past it, or
        is cancelled. Any other insert takes an amendment's values in place
        and is cancelled by any destruction, which removes all of it.
        """
        record = self._records[target]
        if proposed_opening is None:
            if arriving.instruction.mutation in ASSIGNMENT_MUTATIONS:
                return InsertionComposition.SURVIVES
        elif proposed_opening.survives or proposed_opening.transform.assigns:
            return InsertionComposition.SURVIVES
        elif proposed_opening.beyond is not None:
            record.pending_state = "ended_opening"
            record.identity = None
            return InsertionComposition.ENDED
        record.unlink()
        record.identity = None
        return InsertionComposition.CANCELLED

    def finish_insertion_planning(
        self, *, pending_keys: Iterable[ObjectKey], removed_objects: Iterable[ObjectKey]
    ) -> None:
        """End the pending lifecycle of the insertions a planned buffer held.

        A pending removal of a whole Non-Temporal or Transaction-Time-Only
        object ``removed_objects`` names leaves nothing of what its admissions
        stored, which retires an insertion of it no longer pending. Each
        insertion of an object ``pending_keys`` names that is still pending is
        stored from then on, anchored at its own window's start since what an
        earlier admission opened was removed before it; an ended opening is no
        longer pending either.
        """
        records = self._records
        for target in removed_objects:
            record = records.get(target)
            if record is None:
                continue
            if record.valid_time_window is None:
                record.stored_count = 0
            if record.pending_state != "opening":
                record.identity = None
        for target in pending_keys:
            record = records[target]
            if record.pending_state == "opening":
                window = record.valid_time_window
                if window is None:
                    record.stored_count = 1
                record.set_earliest_stored_anchor(None if window is None else window.start)
            record.unlink()

    def resolve_insertion_authorized_write(
        self, write: InsertionAuthorizedWrite
    ) -> InsertionAuthorizedWrite:
        """``write`` while the insertion authority it carries stands, given
        the claim scope a stored Non-Temporal row takes — the version this
        attempt's completed updates left it at, the version an insert stores
        where none completed, or the object itself where it is unversioned.
        A write of a temporal object, or of one whose insertion is still
        pending, takes none.

        Raises :class:`UnitOfWorkError` once that authority no longer stands.
        """
        record = self._standing(write.identity)
        instruction = write.instruction
        target = instruction.target
        if record is None:
            raise UnitOfWorkError(
                f"{target.identity.canonical}: the insertion this write was authored "
                "through no longer stands in this unit of work"
            )
        if record.pending_state == "opening" or self._is_temporal(target):
            return write
        version = record.produced_version
        if version is None:
            version = self._version_after(target.identity, None)
        key = write.object_key
        scope = key if version is None else VersionedObjectStateKey(key, version)
        return replace(write, claim_scope=scope)

    def _standing(self, identity: InsertionIdentity) -> InsertionRecord | None:
        """The record whose standing authority ``identity`` is, if any."""
        record = self._records.get(identity.object_key)
        return record if record is not None and record.identity is identity else None

    def _is_temporal(self, entity: EntityMetadata) -> bool:
        return isinstance(
            self._temporal_facet.shape(entity.identity),
            temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
        )

    def _removed_whole(
        self,
        record: InsertionRecord,
        pending_removal: CoverageTransform | None,
        removes_object: bool,
    ) -> bool:
        """Whether the pending writes of ``record``'s object remove everything
        its admissions left stored, so a further insertion of it is a first
        opening.

        An insertion still pending is never removed whole: a removal it
        composes with folds into it, and a Bitemporal removal a read authorized
        changes only the coverage that read observed, leaving the opening
        standing. A Non-Temporal row is removed whole by a pending delete, and
        so is a Transaction-Time-Only object by a termination. A Bitemporal
        object's stored coverage lies within its removal window, which the
        pending writes must destroy all of.
        """
        if record.pending_state == "opening" or not record.has_stored_coverage:
            return False
        if record.valid_time_window is None:
            return removes_object
        if pending_removal is None:
            return False
        return self._removal_window(record).first_uncovered(_destroyed(pending_removal)) is None

    def _removal_window(self, record: InsertionRecord) -> TimeInterval:
        """The Valid Time a removal of everything a Bitemporal ``record``'s
        admissions left stored must destroy: from its earliest stored anchor to
        the latest end among the owned rows they opened, the open bound
        included.

        It encloses that coverage rather than tracing it, and is derived when
        first asked, then kept on the record until a row it derives from is
        tagged or retired or the anchor moves.
        """
        removal = record.cached_removal_window
        if isinstance(removal, TimeInterval):
            return removal
        anchor = record.earliest_stored_anchor
        assert anchor is not None  # a Bitemporal opening states its start
        removal = record.cached_removal_window = TimeInterval(anchor, self._latest_end(record))
        return removal

    def _latest_end(self, record: InsertionRecord) -> dt.datetime | Literal[TemporalBound.INFINITY]:
        """The latest Valid-Time end among the coverage ``record``'s admissions
        contributed to owned rows — a whole row's physical end read from its
        coordinates, a contributed part's own end — the open bound where one
        runs on, or where none is tagged."""
        latest: dt.datetime | None = None
        for coordinates, (_identity, parts) in self._tags.items():
            if self._addresses.get((coordinates.entity, coordinates.key)) is not record:
                continue
            if parts is None:
                end = coordinates.ends[0]
                if not isinstance(end, Finite):
                    return INFINITY
                instant = end.instant
            else:
                instant = parts[-1].end
                if instant is INFINITY:
                    return INFINITY
            assert isinstance(instant, dt.datetime)  # a finite Valid-Time end is an instant
            if latest is None or instant > latest:
                latest = instant
        return INFINITY if latest is None else latest

    def complete(
        self,
        removed: Iterable[TemporalRowCoordinates],
        opened: Openings,
        derived: tuple[Derivation, ...] = (),
        captured: Iterable[tuple[CurrentRowOutput, object | None]] = (),
    ) -> None:
        """Retire the owned rows one settled write removed, then register the
        rows it opened, each tagged with the parts an admission contributed to
        it, or no longer tagged where it names a row again that none did. An
        admission whose last tagged row the write removed or untagged is retired
        only if no row the write opened continues it.

        Every predecessor the write ``derived`` rows from passes on what a
        continuable source has in it: the observed state a live observation
        describes, over its whole coverage, and each part an earlier changed
        state contributed to it, each over what of its part every derived row
        took. Rows the write ``captured`` that some such part reaches are held
        with the persisted document their execution stored; every other row a
        changed predecessor's coordinates or a derived row's held before is
        released."""
        self._updating = True
        try:
            sources = self._sources(derived) if derived else ()
            drained = self._retire(removed)
            self._open(opened, drained)
            for record, tag in drained:
                if (
                    not record.stored_count
                    and record.identity is tag
                    and record.pending_state != "opening"
                ):
                    # Nothing this admission contributed is left: it was removed
                    # completely, and its authority ends with it.
                    record.identity = None
            if derived:
                self._derive(derived, sources)
            self._adopt_captured_rows(captured)
        finally:
            self._updating = False
            self._drain_prunes()

    def _sources(
        self, derived: tuple[Derivation, ...]
    ) -> list[list[tuple[_Origin, TimeInterval | None]]]:
        """For each of ``derived``, every origin its predecessor carries and the
        part of the predecessor each reaches: the parts earlier changed states
        contributed to it, read before this write retires them, and, where a
        live observation describes its unchanged state, that state itself over
        the predecessor's whole coverage."""
        contributions = self._contributions
        sources: list[list[tuple[_Origin, TimeInterval | None]]] = []
        created: dict[int, _Origin] = {}
        for derivation in derived:
            parts: list[tuple[_Origin, TimeInterval | None]] = []
            coordinates = derivation.input_coordinates
            if coordinates is not None:
                parts.extend(
                    (contribution.origin, contribution.coverage)
                    for contribution in contributions.get(coordinates, ())
                )
            observation = self._observations.get(derivation.predecessor)
            if observation is not None:
                origin = created.get(id(observation))
                if origin is None and self._origin(observation) is None:
                    origin = created[id(observation)] = _Origin(observation, self._release)
                    self._origins[origin.key] = origin
                if origin is not None:
                    parts.append((origin, derivation.valid_time_coverage))
            sources.append(parts)
        return sources

    def _derive(
        self,
        derived: tuple[Derivation, ...],
        sources: Sequence[list[tuple[_Origin, TimeInterval | None]]],
    ) -> None:
        """Replace what every changed predecessor's coordinates and every
        derived row's coordinates held with what each derived row now takes of
        its predecessor's origins, each origin's adjacent parts of one row
        joined."""
        for derivation in derived:
            coordinates = derivation.input_coordinates
            if coordinates is not None:
                self._forget(coordinates)
            for row in derivation.rows:
                self._forget(row.coordinates)
        contributions = self._contributions
        for coordinates, parts in _gathered(derived, sources).items():
            held = contributions.setdefault(coordinates, [])
            for origin, coverage in _joined(parts):
                contribution = _Contribution(origin, coordinates, coverage)
                held.append(contribution)
                origin.lineage.add(contribution)

    def _adopt_captured_rows(
        self, captured: Iterable[tuple[CurrentRowOutput, object | None]]
    ) -> None:
        """Hold each captured row some origin's part still reaches, at its
        coordinates, as the complete state its execution persisted."""
        contributions = self._contributions
        for output, document in captured:
            coordinates = output.coordinates
            if coordinates not in contributions:
                continue
            row = output.row.row
            attributes = row.attributes
            if any(isinstance(value, MaxPlusOne | SelfIncrement) for value in attributes.values()):
                continue
            address = (coordinates.entity, coordinates.key)
            rows = self._current_rows.get(address)
            if rows is None:
                rows = self._current_rows[address] = _HeldCurrentRows()
            rows.put(
                coordinates,
                output.valid_time_coverage,
                PredecessorRow.adopt_written(
                    attributes, row.value_objects, retain_document_value(document)
                ),
            )

    def _forget(self, coordinates: TemporalRowCoordinates) -> None:
        """Release every part any origin contributed to the row at
        ``coordinates``, and the state held for it."""
        held = self._contributions.pop(coordinates, None)
        if held is None:
            return
        for contribution in held:
            contribution.origin.lineage.discard(contribution)
        self._drop_current(coordinates)

    def _drop_current(self, coordinates: TemporalRowCoordinates) -> None:
        address = (coordinates.entity, coordinates.key)
        rows = self._current_rows.get(address)
        if rows is not None:
            rows.drop(coordinates)
            if not rows.rows:
                del self._current_rows[address]

    def _origin(self, observation: Hashable) -> _Origin | None:
        origins = self._origins
        origin = origins.get(id(observation)) if origins else None
        return origin if origin is not None and origin() is observation else None

    def _prune_origin(self, origin: _Origin) -> None:
        """Forget an origin whose observation is gone — at once, or once the
        completion changing what it holds is done."""
        if self._updating:
            self._pending_prunes.append(origin)
            return
        self._forget_origin(origin)

    def _drain_prunes(self) -> None:
        pending = self._pending_prunes
        while pending:
            self._forget_origin(pending.pop())

    def _forget_origin(self, origin: _Origin) -> None:
        if self._origins.get(origin.key) is not origin:
            return
        del self._origins[origin.key]
        contributions = self._contributions
        for contribution in origin.lineage.contributions:
            coordinates = contribution.coordinates
            held = contributions[coordinates]
            held.remove(contribution)
            if not held:
                del contributions[coordinates]
                self._drop_current(coordinates)

    def _open(
        self, opened: Openings, drained: list[tuple[InsertionRecord, InsertionIdentity]]
    ) -> None:
        """Register each row ``opened`` names, tagged with what an admission
        contributed to it and with nothing where it names none."""
        for coordinates in opened.fresh:
            self._owned.add(coordinates)
            if self._tags:
                self._untag(coordinates, drained)
        for coordinates in opened.continued:
            self._owned.add(coordinates)
            self._tag(coordinates, None, drained)
        for coordinates, parts in opened.shared:
            self._owned.add(coordinates)
            self._tag(coordinates, parts, drained)

    def _retire(
        self, removed: Iterable[TemporalRowCoordinates]
    ) -> list[tuple[InsertionRecord, InsertionIdentity]]:
        """Retire each removed row, answering every admission whose last tagged
        row went with them."""
        drained: list[tuple[InsertionRecord, InsertionIdentity]] = []
        for coordinates in removed:
            self._owned.remove(coordinates)  # planning removes only a row this attempt owns
            if self._contributions:
                self._forget(coordinates)
            if self._tags:
                self._untag(coordinates, drained)
        return drained

    def _tag(
        self,
        coordinates: TemporalRowCoordinates,
        parts: tuple[TimeInterval, ...] | None,
        drained: list[tuple[InsertionRecord, InsertionIdentity]],
    ) -> None:
        """Tag the row at ``coordinates`` with the standing admission of its
        object over ``parts`` of it, the whole row where ``None``, replacing
        any tag it held."""
        record = self._addresses.get((coordinates.entity, coordinates.key))
        if record is None or record.identity is None:
            if self._tags:
                self._untag(coordinates, drained)
            return
        if coordinates not in self._tags:
            record.stored_count += 1
        self._tags[coordinates] = (record.identity, parts)
        record.cached_removal_window = _UNCOMPUTED

    def _untag(
        self,
        coordinates: TemporalRowCoordinates,
        drained: list[tuple[InsertionRecord, InsertionIdentity]],
    ) -> None:
        tag = self._tags.pop(coordinates, None)
        if tag is not None:
            self._drain(coordinates, tag[0], drained)

    def _drain(
        self,
        coordinates: TemporalRowCoordinates,
        identity: InsertionIdentity,
        drained: list[tuple[InsertionRecord, InsertionIdentity]],
    ) -> None:
        record = self._addresses[(coordinates.entity, coordinates.key)]
        record.stored_count -= 1
        record.cached_removal_window = _UNCOMPUTED
        if not record.stored_count:
            drained.append((record, identity))

    def clear(self) -> None:
        self._records.clear()
        self._addresses.clear()
        self._owned.clear()
        self._tags.clear()
        self._read_registrations.clear()
        self._current_versions.clear()
        self._destroyed.clear()
        self._origins.clear()
        self._contributions.clear()
        self._current_rows.clear()
        self._pending_prunes.clear()


def _gathered(
    derived: tuple[Derivation, ...],
    sources: Sequence[list[tuple[_Origin, TimeInterval | None]]],
) -> dict[TemporalRowCoordinates, list[tuple[_Origin, TimeInterval | None]]]:
    """Each derived row's coordinates with every origin its predecessor carried
    over the part of the row that origin's part of the predecessor became —
    the whole row without Valid Time — and no origin whose part it missed."""
    gathered: dict[TemporalRowCoordinates, list[tuple[_Origin, TimeInterval | None]]] = {}
    for derivation, parts in zip(derived, sources, strict=True):
        if not parts:
            continue
        for row in derivation.rows:
            contributed = row.contributed
            for origin, part in parts:
                if contributed is None or part is None:
                    shared = None
                else:
                    shared = contributed.intersection(part)
                    if shared is None:
                        continue
                gathered.setdefault(row.coordinates, []).append((origin, shared))
    return gathered


def _destroyed(transform: CoverageTransform) -> Iterator[TimeInterval]:
    """The Valid-Time intervals ``transform`` destroys, ordered by start."""
    for segment in transform.segments:
        if segment.assigned is None:
            window = segment.valid_time_window
            assert window is not None  # only a Bitemporal object's coverage is asked for
            yield window


def _repeated_insert(insert: KeyedInsert, advice: KeyedWriteRefusalAdvice) -> KeyedWriteValueError:
    """The refusal of ``insert``, a repeat of an insertion still standing,
    naming the way out its opener's interface offers.

    The advice is the OPENING insert's, never the refusing call's: two values
    of one primary key open one row, so revising the refused value would
    author a change against a value nothing buffered, and only the opening
    interface produced a carrier the repair can name.
    """
    entity = insert.target.identity
    return KeyedWriteValueError(
        code="write-value-already-stored",
        message=(
            f"{entity.canonical}: {insert.instruction.mutation!r} was handed a value naming an "
            "object this transaction already buffered an insert of, so there is no row to open; "
            f"{advice.repeated_insert}"
        ),
        identity=entity,
    )


def _finite_valid_time(evidence: ReadEvidence) -> dt.datetime | None:
    """The finite Valid-Time instant ``evidence``'s read was pinned at, or
    ``None`` where it named none."""
    pin = evidence.pin
    valid_time = None if pin is None else pin.valid_time
    return valid_time if isinstance(valid_time, dt.datetime) else None


def _joined(
    parts: list[tuple[_Origin, TimeInterval | None]],
) -> list[tuple[_Origin, TimeInterval | None]]:
    """``parts`` of one row with each origin's duplicate and adjacent parts
    joined, each origin's in Valid-Time order.

    A row without Valid Time takes each origin's part once already, since its
    one predecessor carries each origin at most once."""
    if len(parts) < 2 or parts[0][1] is None:
        return parts
    parts.sort(key=_by_origin_then_start)
    joined: list[tuple[_Origin, TimeInterval | None]] = []
    for origin, coverage in parts:
        assert coverage is not None  # one object's parts all lie on Valid Time
        if joined:
            previous, earlier = joined[-1]
            assert earlier is not None
            if previous is origin and (earlier.meets(coverage) or earlier == coverage):
                joined[-1] = (origin, TimeInterval(earlier.start, coverage.end))
                continue
        joined.append((origin, coverage))
    return joined


def _by_origin_then_start(part: tuple[_Origin, TimeInterval | None]) -> tuple[int, dt.datetime]:
    return part[0].key, _start_key(part[1])


_AXISLESS: Final = dt.datetime.min.replace(tzinfo=dt.UTC)


def _start_key(coverage: TimeInterval | None) -> dt.datetime:
    return _AXISLESS if coverage is None else coverage.start


def _address(target: ObjectKey) -> _ObjectAddress:
    return (target.entity, tuple(value for _name, value in target.primary_key))
