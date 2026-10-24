from __future__ import annotations

import datetime as dt
import weakref
from collections.abc import Callable, Hashable, Iterable, Sequence
from enum import Enum
from typing import cast, final
from weakref import WeakValueDictionary

from parallax.core._execution._unit_work._errors import WriteEvidenceError
from parallax.core._execution._unit_work._write_ownership import (
    InsertionComposition,
    WriteOwnership,
)
from parallax.core._execution._unit_work.claims import SettledEvidence
from parallax.core._execution._unit_work.instructions import KeyedMutation
from parallax.core._execution._unit_work.lifetime import AttemptLifetime
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    NoInsertionAuthority,
    ParticipationToken,
    ReadEvidence,
    RetainedObservation,
)
from parallax.core._execution._unit_work.strategy import Concurrency, EvidencePolicyLookup
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    InsertionAuthorizedWrite,
    KeyedInsert,
    ReadAuthorizedWrite,
)
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
    AllocatedOpening,
    CurrentRowOutput,
    Openings,
    TemporalRowCoordinates,
    TemporalWriteOwnership,
    WriteEffects,
)

__all__ = ["SourceAuthority"]


class _SourceRefusal(Enum):
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


class _ReleaseRegistration:
    """The one callback every read registration of an authority shares,
    holding its owner weakly, so neither a registration nor its evidence keeps
    the authority alive."""

    __slots__ = ("_owner",)

    def __init__(self, owner: SourceAuthority) -> None:
        self._owner = weakref.ref(owner)

    def __call__(self, registration: _ReadRegistration) -> None:
        owner = self._owner()
        if owner is not None:
            owner._release_read_evidence(registration)  # pyright: ignore[reportPrivateUsage] - the registration's own owner


class SourceAuthority:
    """Whether a source this attempt read, or an insertion it admitted, still
    authorizes a write, judged from this attempt's own completed writes
    (`m-unit-work` "Observation lifetime", "Insertion authority").

    It is the evidence context a writable attempt's observing reads file
    into: the participation they stamp, the freshness their rows were acquired
    at, the weak index of the observed states they retain, and the
    registration of each evidence they publish. A keyed write's source is
    resolved here once, at its verb, and an insertion's lifecycle — opened,
    composed, planned, stored, and retired — moves only through its named
    transitions. Planning reads what completed writes left through
    :meth:`planning_ownership`, and each successful settled write publishes
    everything it did through one :meth:`complete_write`.

    Only facts and weak references are held: no source value, pending write,
    or the unit of work that executes them. ``version_after`` answers the
    version a row of an Entity holds once a completed update advanced it from
    a version, or, from none, the version an insert stores.
    """

    __slots__ = (
        "__weakref__",
        "_changed",
        "_concluding",
        "_concurrency",
        "_current_versions",
        "_destroyed",
        "_evidence_policy_for",
        "_freshness",
        "_lifetime",
        "_observations",
        "_ownership",
        "_participation",
        "_read_registrations",
        "_release",
        "_version_after",
    )

    def __init__(
        self,
        meta: Metamodel,
        *,
        lifetime: AttemptLifetime,
        concurrency: Concurrency,
        evidence_policy_for: EvidencePolicyLookup,
        version_after: Callable[[EntityIdentity, int | None], int | None],
    ) -> None:
        self._lifetime = lifetime
        self._concurrency: Concurrency = concurrency
        # The connected model's write-evidence policy, bound once per accepted
        # model by model preparation, which alone may reach `m-opt-lock`.
        self._evidence_policy_for = evidence_policy_for
        self._version_after = version_after
        # This scope's participation identity: what a read of THIS attempt
        # stamps on the values it produces, and what a keyed write tests its
        # source against.
        self._participation = ParticipationToken()
        # This index is not an owner: a retained observation lives as long as
        # some source value or buffered or planned write reaches it, and this
        # entry disappears with the last of them (`m-unit-work` "Observation
        # lifetime"). It recognizes a state this transaction has already seen,
        # so a reread of one state answers the evidence the earlier read's
        # values already carry rather than a second copy of it, and tells
        # ownership which observed states a completed write's changes may still
        # serve a source of.
        self._observations: WeakValueDictionary[ObjectStateKey, RetainedObservation] = (
            WeakValueDictionary()
        )
        # How many settled writes have changed a state so far, and the count at
        # which each changed state — an observed state, or an unversioned
        # object — last changed. A read captures the count when it runs, so
        # evidence it builds later, from rows it already holds, is known to
        # predate any change completed in between. The counts outlive every
        # source's demand: a page acquired before a change stays older than it.
        self._freshness = 0
        self._changed: dict[ObjectKey | ObjectStateKey, int] = {}
        # Every registered Non-Temporal source by its evidence's identity; each
        # versioned object's protected versions, from the one its first
        # completed update advanced from to the one its latest produced; and
        # the change count at which a completed deletion last removed each
        # object.
        self._read_registrations: dict[int, _ReadRegistration] = {}
        self._current_versions: dict[ObjectKey, tuple[int, int]] = {}
        self._destroyed: dict[ObjectKey, int] = {}
        self._release = _ReleaseRegistration(self)
        self._ownership = WriteOwnership(
            meta, version_after=version_after, observations=self._observations
        )
        self._concluding: _ConcludingOwnership | None = None

    @property
    def participation(self) -> ParticipationToken:
        """This attempt's participation identity — what its own reads stamp on
        the values they produce, and what a keyed write proves its source
        against."""
        self._lifetime.ensure_open()
        return self._participation

    @property
    def freshness(self) -> int:
        """What a read captures when it runs, so that evidence it builds later
        from the rows it holds is judged against the state those rows had
        (:meth:`retain`)."""
        self._lifetime.ensure_open()
        return self._freshness

    def retain(
        self, observation: RetainedObservation, /, *, read_at: int | None = None
    ) -> RetainedObservation:
        """Index ``observation`` under the state it observed, answering the
        evidence this attempt already holds for that state where it holds any.

        A reread that resolves to a state some live value already observed
        answers THAT value's evidence, so one observed state has one claim
        within a transaction however many reads reach it — the same rule
        graph aliases already follow. A state an own change replaced is not
        reused: a fresh read of the state the row is in now is fresh evidence.

        ``read_at`` is the :attr:`freshness` the producing read captured, by
        default now. Evidence built from a read that ran before a later
        successful change of the same state is answered invalidated and never
        indexed: its rows describe a state this attempt has since replaced.
        """
        self._lifetime.ensure_open()
        key = observation.key
        if not self.is_unchanged_since(key, self._freshness if read_at is None else read_at):
            observation.invalidate()
            return observation
        held = self._observations.get(key)
        if held is not None and not held.invalidated:
            return held
        self._observations[key] = observation
        return observation

    def register_read_evidence(self, evidence: ReadEvidence, /, *, read_at: int) -> None:
        """Register the exact ``evidence`` a read of this attempt published,
        judging once whether its read, which captured :attr:`freshness`
        ``read_at``, predates a completed change of what it observed.

        Before any change completed, every read precedes every later change
        and nothing is judged. After one, a Non-Temporal source published
        fresh, of an object no completed deletion removed, was read before any
        deletion that completes later, which is what unregistered evidence
        answers, so only the rest are registered. A temporal source registers
        nothing: its shared observation, which :meth:`retain` indexes or
        refuses as stale, is what any later judgment of it reads.
        """
        if not self._freshness:
            return
        observation = evidence.observation
        state: VersionedObjectStateKey | ObjectKey
        if observation is None:
            target = state = evidence.object_key
        elif isinstance(observation.key, VersionedObjectStateKey):
            state = observation.key
            target = state.object
        else:
            return
        fresh = self.is_unchanged_since(state, read_at)
        if fresh and target not in self._destroyed:
            return
        self._read_registrations[id(evidence)] = _ReadRegistration(
            evidence, self._release, read_at if fresh else None
        )

    def resolve_read_evidence(
        self,
        target: EntityMetadata,
        read_evidence: ReadEvidence | None,
        *,
        mutation: KeyedMutation,
        object_key: ObjectKey,
    ) -> SettledEvidence | None:
        """What a keyed write of ``target`` against existing state settles
        against, read off its source's ``read_evidence``, or
        :class:`~parallax.core._execution._unit_work._errors.WriteEvidenceError`
        where this attempt cannot use it.

        One resolution serves the address, the gate, the version advance, and
        the claim, so they cannot disagree. Under either Effective Concurrency
        Strategy (`m-opt-lock`) the source must have been read in THIS attempt:
        a standalone read, a read-only transaction's read, and an earlier
        attempt's read participated in nothing this attempt can stand on,
        whatever key or revision they share with it. The strategy then decides
        what that participating read proves:

        * **Locking** — the license is the shared row lock the read holds. That
          holds for unversioned Non-Temporal targets too: the lock is the whole
          of their evidence, and unconditional intent has its own
          predicate-selected spelling.
        * **Optimistic** — the license is the database gate, so the read must
          also have retained the observation the gate binds.

        A source's authority continues through this attempt's own completed
        writes while its observation stays what it read: a versioned
        Non-Temporal source settles against the version they produced, an
        unversioned one against its object, and a temporal one against what
        they left of the state it observed. Under BOTH strategies a source
        published from rows a read acquired before a completed write changed
        them is refused, and so is one those writes ended — of an object a
        completed keyed deletion removed, or a temporal source whose observed
        state they left nothing of at its Valid-Time pin: a held lock does not
        restore a state the attempt itself replaced.
        """
        self._lifetime.ensure_open()
        identity = target.identity.canonical
        if read_evidence is None or read_evidence.participation is not self._participation:
            raise WriteEvidenceError(
                code="write-evidence-unavailable",
                message=(
                    f"{identity}: a keyed write is licensed only by a read of THIS transaction "
                    "attempt, and the value handed to the verb came from no such read — a "
                    "standalone read, a read-only transaction, and an earlier attempt license "
                    "nothing here; read the row through this transaction and write what that "
                    "read returned, or state the revision you observed through the `*_if` verb"
                ),
                object_key=object_key,
            )
        policy = self._evidence_policy_for(target.identity)
        observation = read_evidence.observation
        settled = policy.settled_evidence(mutation, object_key=object_key, observation=observation)
        if policy.effective_strategy(self._concurrency) == "optimistic" and (observation is None):
            raise WriteEvidenceError(
                code="write-evidence-unavailable",
                message=(
                    f"{identity}: the Optimistic strategy gates this write on the state its "
                    "source observed, and the value handed to the verb carries no retained "
                    "observation; read the row through a `find` and write what it returned"
                ),
                object_key=object_key,
            )
        if settled is None:
            return None
        resolved = self._resolve_source(read_evidence)
        if resolved is _SourceRefusal.STALE:
            raise WriteEvidenceError(
                code="write-evidence-consumed",
                message=(
                    f"{identity}: this transaction has since changed the state this value "
                    "observed, so its evidence no longer describes the stored row; read the row "
                    "again and write what that read returns"
                ),
                object_key=object_key,
            )
        if resolved is _SourceRefusal.ENDED:
            raise WriteEvidenceError(
                code="write-evidence-consumed",
                message=(
                    f"{identity}: a write this transaction completed left nothing of what this "
                    "value's source read — a deletion of its object, or the coverage at the "
                    "Valid-Time instant it was read at — so the source authorizes no further "
                    "write, whatever was inserted there since; read the row again and write "
                    "what that read returns"
                ),
                object_key=object_key,
            )
        return resolved

    def _resolve_source(self, evidence: ReadEvidence) -> SettledEvidence | _SourceRefusal:
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
            reach = self._ownership.continues(observation, _finite_valid_time(evidence))
            if reach is None:
                return _SourceRefusal.STALE
            return observation if reach else _SourceRefusal.ENDED
        registration = self._read_registrations.get(id(evidence))
        read_at = 0
        if registration is not None and registration() is evidence:
            if not registration.fresh_at_publication:
                return _SourceRefusal.STALE
            read_at = cast("int", registration.read_at)
        target = evidence.object_key
        destroyed = self._destroyed.get(target) if self._destroyed else None
        if destroyed is not None and destroyed > read_at:
            return _SourceRefusal.ENDED
        if observation is None:
            return target
        observed = observation.key
        assert isinstance(observed, VersionedObjectStateKey)  # a Non-Temporal observation
        versions = self._current_versions.get(target)
        if versions is None or not versions[0] <= observed.version < versions[1]:
            return observed
        return VersionedObjectStateKey(target, versions[1])

    def _release_read_evidence(self, registration: _ReadRegistration) -> None:
        """Forget a registration whose evidence is gone."""
        key = registration.key
        if self._read_registrations.get(key) is registration:
            del self._read_registrations[key]

    def has_live_observation(self, state: ObjectStateKey, /) -> bool:
        """Whether a live read of exactly ``state`` this attempt holds — under
        its shared lock, and still describing the stored state — already
        proves it."""
        held = self._observations.get(state)
        return (
            held is not None and held.participation is self._participation and not held.invalidated
        )

    def is_unchanged_since(self, state: ObjectKey | ObjectStateKey, read_at: int, /) -> bool:
        """Whether no settled write that completed after a read capturing
        :attr:`freshness` ``read_at`` changed ``state``: what that read found
        of ``state`` is still what the attempt stores, whatever else changed.
        An unchanged milestone a guard proved is no change."""
        log = self._changed
        changed = log.get(state) if log else None
        return changed is None or changed <= read_at

    def insertion_authority(
        self, identity: InsertionIdentity
    ) -> TimeInterval | NoInsertionAuthority | None:
        """The Valid-Time window the insertion ``identity`` names was admitted
        with — whose start is where a write it authorizes starts — while its
        authority stands in this attempt, ``None`` for a standing insertion of
        an object without Valid Time, or
        :data:`~parallax.core._execution._unit_work.retain.NO_INSERTION_AUTHORITY`
        once it does not stand: never issued here, retired by the complete
        removal of what it opened, or superseded by a later insertion of the
        same object."""
        self._lifetime.ensure_open()
        return self._ownership.insertion_authority(identity)

    def resolve_insertion_authorized_write(
        self, write: InsertionAuthorizedWrite
    ) -> InsertionAuthorizedWrite:
        """``write`` while the insertion authority it carries stands, with the
        claim scope its stored row takes
        (:meth:`~parallax.core._execution._unit_work._write_ownership.WriteOwnership.resolve_insertion_authorized_write`)."""
        return self._ownership.resolve_insertion_authorized_write(write)

    def has_admitted_insertion(self, target: ObjectKey) -> bool:
        """Whether this attempt admitted an insertion of ``target`` at all,
        whether or not any insertion of it still stands."""
        return self._ownership.has_admitted_insertion(target)

    def open_insertion(
        self,
        insert: KeyedInsert,
        *,
        pending_removal: CoverageTransform | None,
        removes_object: bool,
        insertion_advice: KeyedWriteRefusalAdvice | None,
    ) -> tuple[InsertionIdentity, bool]:
        """Open an insertion of the object ``insert`` names, answering the
        identity it issues and whether the insert must follow a pending
        removal, or refuse a repeat with nothing changed
        (:meth:`~parallax.core._execution._unit_work._write_ownership.WriteOwnership.open_insertion`)."""
        return self._ownership.open_insertion(
            insert,
            pending_removal=pending_removal,
            removes_object=removes_object,
            insertion_advice=insertion_advice,
        )

    def apply_insertion_composition(
        self,
        target: ObjectKey,
        *,
        arriving: ReadAuthorizedWrite | InsertionAuthorizedWrite,
        proposed_opening: ComposedBitemporalOpening | None,
    ) -> InsertionComposition:
        """What composing ``arriving`` into the still-pending insertion of
        ``target`` does to that insertion
        (:meth:`~parallax.core._execution._unit_work._write_ownership.WriteOwnership.apply_insertion_composition`)."""
        return self._ownership.apply_insertion_composition(
            target, arriving=arriving, proposed_opening=proposed_opening
        )

    def finish_insertion_planning(
        self, *, pending_keys: Iterable[ObjectKey], removed_objects: Iterable[ObjectKey]
    ) -> None:
        """End the pending lifecycle of the insertions a planned buffer held
        (:meth:`~parallax.core._execution._unit_work._write_ownership.WriteOwnership.finish_insertion_planning`)."""
        self._ownership.finish_insertion_planning(
            pending_keys=pending_keys, removed_objects=removed_objects
        )

    def planning_ownership(self, *, concluding: bool) -> TemporalWriteOwnership:
        """The live ownership one flush plans and binds its deferred writes
        under, as its earlier Write Groups' completion left it.

        The ``concluding`` pre-commit flush borrows the same live ownership,
        but demands nothing its writes leave: no later submission follows it,
        and no write of it continues from what another of its writes leaves.
        """
        if not concluding:
            return self._ownership
        view = self._concluding
        if view is None:
            view = self._concluding = _ConcludingOwnership(self._ownership)
        return view

    def complete_write(
        self,
        effects: WriteEffects,
        allocated_keys: tuple[object, ...],
        *,
        captured: tuple[tuple[CurrentRowOutput, object | None], ...] = (),
    ) -> None:
        """Publish one successful write's ``effects``: a settled write's own,
        or those of the range its deferred coverage bound.

        Live evidence of every observed state it changed is invalidated and
        every change recorded, so a read that ran before it cannot later
        publish eligible evidence of that state or object; the Non-Temporal
        sources whose state it advanced continue from the version it produced,
        which a write a standing insertion of it authorizes claims from then
        on, and those of every object it deleted end; the owned rows it removed
        are retired before the rows it opened, completed by the keys the
        database ``allocated_keys``, are registered; and what it left of each
        observed temporal state a live source shares is recorded, with the rows
        its execution ``captured`` for them.
        """
        stamp = self._freshness + 1
        changed_any = False
        for key in effects.changed:
            changed_any = True
            if not isinstance(key, ObjectKey):
                held = self._observations.get(key)
                if held is not None:
                    held.invalidate()
            self._changed[key] = stamp
        if changed_any:
            self._freshness = stamp
        self._continue_sources(effects.advanced, effects.destroyed)
        opened = effects.opened
        self._ownership.complete(
            effects.removed,
            _resolve_allocated_openings(opened, allocated_keys) if allocated_keys else opened,
            effects.derived,
            captured,
        )

    def _continue_sources(
        self, advanced: Iterable[VersionedObjectStateKey], destroyed: Iterable[ObjectKey]
    ) -> None:
        """Each versioned state a completed write ``advanced`` from now stands
        at the version it produced, and each object it ``destroyed`` ends every
        source read before it, so no later state of the object, a reinserted
        one's included, revives them."""
        versions = self._current_versions
        for state in advanced:
            target = state.object
            produced = self._version_after(target.entity, state.version)
            assert produced is not None  # only a versioned row advances
            held = versions.get(target)
            first = held[0] if held is not None and held[1] == state.version else state.version
            versions[target] = (first, produced)
            self._ownership.advance_insertion_version(target, produced)
        for target in destroyed:
            self._destroyed[target] = self._freshness
            versions.pop(target, None)

    def clear(self) -> None:
        """Forget every observation, change, registration, insertion, owned
        row, and continuation of an attempt that will not commit, keeping its
        participation and its change count."""
        self._observations.clear()
        self._changed.clear()
        self._read_registrations.clear()
        self._current_versions.clear()
        self._destroyed.clear()
        self._ownership.clear()


@final
class _ConcludingOwnership:
    """``ownership`` answering every question as it does, except that no
    predecessor is demanded."""

    __slots__ = ("_ownership",)

    def __init__(self, ownership: TemporalWriteOwnership) -> None:
        self._ownership = ownership

    def owns(self, coordinates: TemporalRowCoordinates, /) -> bool:
        return self._ownership.owns(coordinates)

    def continues_insertion(self, coordinates: TemporalRowCoordinates, /) -> bool:
        return self._ownership.continues_insertion(coordinates)

    def insertion_coverage(
        self, coordinates: TemporalRowCoordinates, valid_time_coverage: TimeInterval | None, /
    ) -> tuple[TimeInterval | None, ...]:
        return self._ownership.insertion_coverage(coordinates, valid_time_coverage)

    def demanded(
        self, predecessor: ObjectStateKey, coordinates: TemporalRowCoordinates | None, /
    ) -> bool:
        del predecessor, coordinates
        return False

    def continues(self, observation: Hashable, pin: dt.datetime | None, /) -> bool | None:
        return self._ownership.continues(observation, pin)

    def current_rows(
        self, target: ObjectKey, valid_time_window: TimeInterval | None, /
    ) -> Sequence[PredecessorRow]:
        return self._ownership.current_rows(target, valid_time_window)


def _resolve_allocated_openings(opened: Openings, allocated: tuple[object, ...]) -> Openings:
    named = tuple(
        _allocated_coordinates(opening, key)
        for opening, key in zip(opened.allocated, allocated, strict=True)
    )
    return Openings(fresh=(*opened.fresh, *named), continued=opened.continued, shared=opened.shared)


def _allocated_coordinates(opening: AllocatedOpening, key: object) -> TemporalRowCoordinates:
    return TemporalRowCoordinates(opening.entity, (key,), opening.ends)


def _finite_valid_time(evidence: ReadEvidence) -> dt.datetime | None:
    """The finite Valid-Time instant ``evidence``'s read was pinned at, or
    ``None`` where it named none."""
    pin = evidence.pin
    valid_time = None if pin is None else pin.valid_time
    return valid_time if isinstance(valid_time, dt.datetime) else None
