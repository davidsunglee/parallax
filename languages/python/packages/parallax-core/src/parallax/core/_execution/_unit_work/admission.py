from __future__ import annotations

import heapq
from collections.abc import Callable, Hashable, Iterator, Mapping, Sequence
from dataclasses import replace
from enum import Enum
from operator import attrgetter
from typing import Final, Literal, cast, final

from parallax.core import inheritance, temporal_read
from parallax.core._execution._unit_work._write_ownership import InsertionRecord, WriteOwnership
from parallax.core._execution._unit_work.claims import (
    ClaimScope,
    ClaimVerdict,
    WriteIntent,
    admits,
    admits_composed,
    claimed_object,
    keyed_intent,
)
from parallax.core._execution._unit_work.instructions import (
    ASSIGNMENT_MUTATIONS,
    DESTRUCTIVE_MUTATIONS,
    INSERT_MUTATIONS,
    REPLACE_MUTATIONS,
    PreparedKeyedWrite,
    derive_keyed_write,
)
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    RetainedObservation,
)
from parallax.core._execution._unit_work.write_items import (
    AfterRemoval,
    BufferedWrite,
    BufferItem,
    ChainedTemporalWrite,
    ClaimedKeyedWrite,
    ComposedTemporalWrite,
    FollowingKeyedWrite,
    InsertionKeyedWrite,
    ObjectClaimedWrite,
    ObservedKeyedWrite,
    PendingOpening,
    ReadlessPredicateWrite,
    TargetKeyedWrite,
    TemporalContribution,
    TemporalKeyedWrite,
    buffered_claim_scope,
    buffered_object_key,
    chained_temporal_write,
    composed_temporal_write,
    temporal_contribution,
)
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import TimeInterval, milestone_edge, valid_time_coverage
from parallax.core.temporal_write.coverage import NO_TRANSFORM
from parallax.core.write_plan.keys import ObjectKey, ObjectStateKey, VersionedObjectStateKey
from parallax.core.write_plan.observe import TemporalObservation
from parallax.core.write_plan.plan import (
    AllocatedOpening,
    Openings,
    OwnedEndpoint,
    SourceAuthority,
    TemporalWriteOwnership,
    UnitEffects,
)

__all__ = [
    "NO_INSERTION_AUTHORITY",
    "WRITE_EVIDENCE_CODES",
    "BufferOutcome",
    "NoInsertionAuthority",
    "UnitOfWorkError",
    "WriteAdmission",
    "WriteEvidenceError",
    "WriteEvidenceErrorCode",
]


class UnitOfWorkError(RuntimeError):
    """A unit of work was driven into an illegal state."""


type WriteEvidenceErrorCode = Literal[
    "write-evidence-unavailable",
    "write-evidence-consumed",
    "write-evidence-already-claimed",
    "write-evidence-inserted",
]
"""The write-evidence refusals a keyed verb raises.

The first three partition what can be wrong with a source's evidence at the
verb: there is none the target Entity's Effective Concurrency Strategy can use,
the evidence there is has been spent by a successful flush, or a write already
buffered in this unit of work claimed the scope this one settles against, for an
intent this one cannot join. The fourth refuses a caller's own condition on an
object this attempt inserted, which only that insertion's source or a read
addresses. A conflict the database discovers later is a different thing
entirely and keeps its own flush-time classification.
"""

WRITE_EVIDENCE_CODES: Final[frozenset[str]] = frozenset(
    {
        "write-evidence-unavailable",
        "write-evidence-consumed",
        "write-evidence-already-claimed",
        "write-evidence-inserted",
    }
)
"""The complete set of codes :class:`WriteEvidenceError` carries."""


class WriteEvidenceError(LookupError):
    """A keyed write verb was handed a source whose write evidence it cannot use.

    A ``LookupError`` because every code reports that the evidence this write
    needs is not there for it to use: never recorded for this source, recorded
    and already spent, or still live but claimed by an intent this unit of work
    already buffered at the scope this write settles against, which this one
    cannot join. ``object_key`` is the object the write addressed, always
    visible so a caller can say WHICH write was refused; the Read Evidence and the
    claim scope behind it stay implementation state.

    Raised synchronously at the verb, before any buffering and before any
    database access. A conflict the database discovers later is a different
    thing entirely and keeps its own flush-time classification.
    """

    def __init__(
        self, *, code: WriteEvidenceErrorCode, message: str, object_key: ObjectKey
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code: Final = code
        self.message: Final = message
        self.object_key: Final = object_key


class BufferOutcome(Enum):
    """What buffering one accepted item did to the buffer's pending inserts.

    Both values mean the item was buffered; a refused item raises instead.
    ``CANCELLED_PENDING_INSERT`` reports a destructive keyed write that left
    nothing of a still-unflushed insert of its object — the pair the flush
    emits nothing for — and nothing about SQL.
    """

    BUFFERED = "buffered"
    CANCELLED_PENDING_INSERT = "cancelled-pending-insert"


@final
class NoInsertionAuthority:
    """The answer :meth:`WriteAdmission.insertion_authority` gives where no
    admitted insertion's authority stands: distinct from the ``None`` window of
    a standing insertion without Valid Time."""

    __slots__ = ()


NO_INSERTION_AUTHORITY: Final = NoInsertionAuthority()

type _PendingItem = BufferItem | ComposedTemporalWrite | PendingOpening | None

type _PendingTemporal = TemporalKeyedWrite | ComposedTemporalWrite
"""What a temporal object's pending writes against its existing coverage are:
one write still alone, or several composed."""

type _Claimed = ClaimedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite

_CLAIMED: Final = (ObservedKeyedWrite, ObjectClaimedWrite, InsertionKeyedWrite, TargetKeyedWrite)

_TEMPORAL: Final = (
    ObservedKeyedWrite,
    InsertionKeyedWrite,
    TargetKeyedWrite,
    ComposedTemporalWrite,
)

_SEVERAL: Final = object()
"""What the object view records for an object claimed at more than one
scope."""


class WriteAdmission:
    """One unit of work's accepted writes: the pending batch composed as each
    write is admitted, every claim it holds, and the insertions the attempt
    admitted (`m-unit-work` "Observed-State Coalescing").

    :meth:`admit` accepts a write under the authority it carries or refuses
    it, with nothing pending changed. Composition follows authored order:

    * an amendment or replacement of an object whose insert is still pending
      folds into that insert, and a destructive write of it cancels the pair; a
      Bitemporal opening composes them over its coverage instead
      (:class:`~parallax.core._execution._unit_work.write_items.PendingOpening`);
    * writes claiming one non-temporal scope coalesce by the claim algebra
      (:func:`~parallax.core._execution._unit_work.claims.admits`), a write a
      caller addressed keeping its condition through every overwrite and
      destruction;
    * a temporal object's writes against its existing coverage — observed ones,
      those an admitted insertion authorized, and those a caller addressed
      alike — compose into one
      :class:`~parallax.core._execution._unit_work.write_items.ComposedTemporalWrite`,
      whose transform keeps only surviving values while every write's
      condition stays. Two writes of one observed state over one window simply
      coalesce, as a non-temporal pair does. Writes of the object over disjoint
      windows stay separate operations inside it, each with its own condition.

    A readless predicate write is an ordering barrier no write composes across:
    a write of an object whose insert stands before one is a write of the row
    that insert opens, a temporal object's writes on each side of one compose
    apart
    (:class:`~parallax.core._execution._unit_work.write_items.ChainedTemporalWrite`),
    and a Non-Temporal write of a scope whose earlier write stands before one
    follows it as a write of its own
    (:class:`~parallax.core._execution._unit_work.write_items.FollowingKeyedWrite`).
    Admission still judges each arriving write against every pending write of
    its object.

    Planning borrows :meth:`composed_writes` and :attr:`ownership` without
    changing either; only a successfully planned batch is drained
    (:meth:`drain_planned`). The insertions, and the temporal rows the
    attempt's successful units opened, outlive every batch.
    """

    __slots__ = (
        "_after_removal",
        "_claimed_objects",
        "_claims",
        "_conditioned",
        "_families",
        "_inserted_version",
        "_linked",
        "_ownership",
        "_regions",
        "_removals",
        "_sources",
        "_temporal",
        "_temporal_facet",
        "_writes",
    )

    def __init__(
        self,
        meta: Metamodel,
        *,
        inserted_version: Callable[[EntityIdentity, int | None], int | None],
    ) -> None:
        self._families = inheritance.view(meta)
        self._temporal_facet = temporal_read.view(meta)
        # The version a row this attempt inserted holds, given the version its
        # last completed update advanced from: the scope a write its insertion
        # authorized claims once the row is stored.
        self._inserted_version = inserted_version
        self._ownership = WriteOwnership()
        self._writes: list[_PendingItem] = []
        # Every claim the batch holds, by its scope: the position of the write
        # that holds it. A temporal object's writes against its coverage are
        # indexed by object instead (`_temporal`).
        self._claims: dict[ClaimScope, int] = {}
        self._temporal: dict[ObjectKey, int] = {}
        self._sources: list[SourceAuthority] = []
        # Objects a pending write removes whole, the positions of inserts that
        # must follow a removal of an earlier insertion, and the insertions the
        # batch linked — each allocated by the first write it records, since
        # most batches hold none.
        self._removals: set[ObjectKey] | None = None
        self._after_removal: set[int] | None = None
        self._linked: list[InsertionRecord] | None = None
        # The scope of each object's pending caller-conditioned write,
        # allocated by the first such write.
        self._conditioned: dict[ObjectKey, ClaimScope] | None = None
        # The scope each claimed object is claimed at, built by the first
        # question that needs it and kept current from then on.
        self._claimed_objects: dict[ObjectKey, Hashable] | None = None
        # Where the latest barrier stands and what the regions before it hold —
        # allocated by the first barrier, since most batches carry none.
        self._regions: _Regions | None = None

    def __bool__(self) -> bool:
        """Whether the pending batch has anything for a flush to process —
        composed writes, or writes composition left nothing of."""
        return bool(self._writes)

    @property
    def ownership(self) -> TemporalWriteOwnership:
        """The attempt's live ownership, which planning and deferred binding
        read as the flush's earlier units left it."""
        return self._ownership

    def admit(
        self,
        item: BufferItem,
        *,
        confirm_target: Callable[[TargetKeyedWrite], TargetKeyedWrite],
        insertion_advice: KeyedWriteRefusalAdvice | None = None,
    ) -> BufferOutcome:
        """Accept ``item`` into the pending batch under the authority it
        carries, composing it there — all of it, or nothing.

        A write a caller addressed is refused where this attempt inserted its
        object (``write-evidence-inserted``) or it cannot join the object's
        pending writes; only then, unless a pending write of the same state
        already proves its starting state, ``confirm_target`` answers it as
        its caller's revision is confirmed, or refuses it. A write an insertion
        authorized is admitted only while that authority stands. An arriving
        keyed intent a held claim cannot absorb is refused
        (``write-evidence-already-claimed``).

        An insert opens an insertion of its object, issuing its identity
        (:meth:`insertion_identity`) and keeping ``insertion_advice`` for a
        repeat of it (:meth:`insertion_advice`); where an earlier insertion of
        the object is stored and a pending write removes all of it, the insert
        executes after that removal. The outcome reports whether ``item``, a
        destructive write leaving nothing of its object's still-pending insert
        and reaching no stored coverage past it, cancelled that pair.
        """
        if isinstance(item, TargetKeyedWrite):
            self._admit_target(item, confirm_target)
        elif isinstance(item, ReadlessPredicateWrite):
            self._seal()
            self._writes.append(item)
        else:
            return self._admit_keyed(item, insertion_advice)
        return BufferOutcome.BUFFERED

    def _admit_keyed(
        self,
        item: PreparedKeyedWrite | ClaimedKeyedWrite | InsertionKeyedWrite,
        insertion_advice: KeyedWriteRefusalAdvice | None,
    ) -> BufferOutcome:
        record: InsertionRecord | None = None
        if isinstance(item, InsertionKeyedWrite):
            item, record = self._authorized(item)
        key = buffered_object_key(item, self._families)
        temporal = self._is_temporal(item)
        verdict: ClaimVerdict | None = None
        if temporal:
            assert key is not None  # such a write names one object
            self._check_temporal_claims(cast("ObservedKeyedWrite | InsertionKeyedWrite", item), key)
        else:
            verdict = self._check_keyed_claim(item, key)
        if isinstance(item, ObjectClaimedWrite):
            self._sources.append(item.source)
        instruction = item if isinstance(item, PreparedKeyedWrite) else item.instruction
        if key is None:
            self._writes.append(item)
            return BufferOutcome.BUFFERED
        if instruction.mutation in INSERT_MUTATIONS:
            return self._open_insertion(instruction, key, insertion_advice)
        if record is None:
            record = self._ownership.insertion_record(key)
        if record is not None and self._foldable(record):
            return self._fold_into_opening(instruction, record)
        self._add_existing(item, instruction, key, record, verdict=verdict, temporal=temporal)
        return BufferOutcome.BUFFERED

    def composed_writes(self) -> tuple[BufferedWrite, ...]:
        """The pending batch's composed writes, in authored order, with every
        cancelled write gone, every object claim unwrapped to its own
        instruction, every Bitemporal opening composed with the writes its
        insertion authorized, and every insert that must follow a removal
        marked as such."""
        written: list[BufferedWrite] = []
        after_removal = self._after_removal or ()
        follows = {} if self._regions is None else self._regions.follows
        for index, item in enumerate(self._writes):
            if item is None:
                continue
            if index in after_removal:
                # An insert is a bare instruction, or an opening composed over it.
                assert isinstance(item, PreparedKeyedWrite | PendingOpening)
                written.append(AfterRemoval(item))
                continue
            if isinstance(item, PendingOpening):
                written.append(item)
                continue
            advances = follows.get(index)
            if advances is not None and isinstance(
                item, ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite
            ):
                written.append(FollowingKeyedWrite(item, advances))
            else:
                written.append(item.instruction if isinstance(item, ObjectClaimedWrite) else item)
        return tuple(written)

    def drain_planned(self) -> Sequence[SourceAuthority]:
        """End the pending batch its flush planned, answering every
        observation-free source authority its writes were admitted through, in
        admission order, for the flush to spend once its plan succeeds.

        An insertion the batch buffered is stored from then on, unless a later
        write of the batch removes it, and a removal of everything an earlier
        insertion of an object opened retires that insertion's authority.
        """
        sources = self._sources
        self._sources = []
        if self._removals is not None:
            for target in self._removals:
                record = self._ownership.insertion_record(target)
                if record is None:
                    continue
                if record.valid_time_window is None:
                    record.stored_count = 0
                if record.pending_state != "opening":
                    record.identity = None
        if self._linked is not None:
            for record in self._linked:
                if record.pending_state == "opening":
                    window = record.valid_time_window
                    if window is None:
                        record.stored_count = 1
                    record.set_earliest_stored_anchor(None if window is None else window.start)
                record.unlink()
        self._clear_batch()
        return sources

    def record_version_advance(self, state: VersionedObjectStateKey) -> None:
        """Note that a completed unit advanced ``state``'s row past its
        version, which a write a standing insertion of it authorizes claims
        from then on."""
        record = self._ownership.insertion_record(state.object)
        if record is not None:
            record.advanced_from = state.version

    def complete_unit(self, effects: UnitEffects, allocated_keys: tuple[object, ...]) -> None:
        """Retire the owned rows a successful unit removed, then register the
        rows it opened — those whose keys the database allocated named by
        ``allocated_keys`` — and what it derived from its originals."""
        opened = effects.opened
        self._ownership.complete(
            effects.removed,
            _resolve_allocated_openings(opened, allocated_keys) if allocated_keys else opened,
            effects.derived,
            effects.concludes,
        )

    def release_continuity(self) -> None:
        """End what the flush's units proved for later ones."""
        self._ownership.release_continuity()

    def discard(self) -> None:
        """Drop the pending batch, its claims and source authorities unspent,
        and every insertion and owned row of the attempt."""
        self._sources.clear()
        self._clear_batch()
        self._ownership.clear()

    def insertion_identity(self, target: ObjectKey) -> InsertionIdentity | None:
        """The authority the standing admitted insertion of ``target`` grants,
        or ``None`` where none stands."""
        record = self._ownership.insertion_record(target)
        return None if record is None else record.identity

    def insertion_authority(
        self, identity: InsertionIdentity
    ) -> TimeInterval | NoInsertionAuthority | None:
        """The Valid-Time window the insertion ``identity`` names was admitted
        with while its authority stands, ``None`` for a standing insertion of
        an object without Valid Time, or :data:`NO_INSERTION_AUTHORITY` once it
        does not stand."""
        record = self._ownership.authorized_insertion(identity)
        return NO_INSERTION_AUTHORITY if record is None else record.valid_time_window

    def insertion_advice(self, target: ObjectKey) -> KeyedWriteRefusalAdvice | None:
        """The refusal advice of the admitted insertion of ``target`` that a
        further insertion of it would repeat, or ``None`` where an insertion of
        it is a first opening or its opener supplied none.

        An insertion still pending is repeated by another; so is one whose
        coverage is stored and survives what is pending. Once everything the
        object's admissions opened has been removed — or a pending write
        removes all of it — the object can be inserted again.
        """
        record = self._ownership.insertion_record(target)
        if record is None or self._removed_whole(target, record):
            return None
        if record.pending_state == "opening" or record.has_stored_coverage:
            return record.insertion_advice
        return None

    def _admit_target(
        self,
        item: TargetKeyedWrite,
        confirm_target: Callable[[TargetKeyedWrite], TargetKeyedWrite],
    ) -> None:
        instruction = item.instruction
        target = instruction.target
        scope = item.scope
        key = buffered_object_key(item, self._families)
        assert key is not None  # a caller's condition addresses one object
        if self._ownership.insertion_record(key) is not None:
            raise WriteEvidenceError(
                code="write-evidence-inserted",
                message=(
                    f"{target.identity.canonical}: this transaction inserted the object this write "
                    "addresses, so no caller's revision describes it; until the transaction "
                    "commits, write it through the value the insert took or a read of it"
                ),
                object_key=key,
            )
        verdict: ClaimVerdict | None = None
        temporal = self._is_temporal(item)
        if temporal:
            admitted = self._admits_temporal(item, key)
            proven = self._states_window(key, instruction.valid_time_window)
        else:
            intent = keyed_intent(instruction)
            assert intent is not None  # a caller-addressed write is no insert
            held = self._objects().get(key)
            verdict = admits(self._held_intent(scope), intent)
            admitted = (held is None or held == scope) and verdict != "incompatible"
            proven = scope in self._claims
        if not admitted:
            raise _already_claimed(target, key)
        if not proven:
            item = confirm_target(item)
        self._add_existing(item, instruction, key, None, verdict=verdict, temporal=temporal)

    def _authorized(self, item: InsertionKeyedWrite) -> tuple[InsertionKeyedWrite, InsertionRecord]:
        """``item`` checked against the authority it carries, and given the
        claim scope its stored Non-Temporal row takes, beside the insertion's
        record — or refused."""
        record = self._ownership.authorized_insertion(item.identity)
        instruction = item.instruction
        if record is None:
            raise UnitOfWorkError(
                f"{instruction.target.identity.canonical}: the insertion this write was authored "
                "through no longer stands in this unit of work"
            )
        if self._foldable(record):
            if not self._opening_admits(record, instruction):
                raise _already_claimed(instruction.target, item.identity.object_key)
            return item, record
        if self._is_temporal(item):
            return item, record
        key = item.identity.object_key
        version = self._inserted_version(instruction.target.identity, record.advanced_from)
        scope = key if version is None else VersionedObjectStateKey(key, version)
        scoped = InsertionKeyedWrite(instruction=instruction, identity=item.identity, scope=scope)
        return scoped, record

    def _check_keyed_claim(
        self,
        item: PreparedKeyedWrite | ClaimedKeyedWrite | InsertionKeyedWrite,
        key: ObjectKey | None,
    ) -> ClaimVerdict | None:
        """What a non-temporal write becomes against the claim held at its
        scope, or ``None`` where it claims nothing — refused where it cannot
        join that claim or its object's pending caller-conditioned write."""
        scope = buffered_claim_scope(item, key)
        if scope is None:
            return None
        assert not isinstance(item, PreparedKeyedWrite)  # a bare instruction claims nothing
        intent = keyed_intent(item.instruction)
        assert intent is not None  # no carrier wraps an insert
        claimed = claimed_object(scope)
        conditioned = None if self._conditioned is None else self._conditioned.get(claimed)
        verdict = admits(self._held_intent(scope), intent)
        if conditioned in (None, scope) and verdict != "incompatible":
            return verdict
        raise WriteEvidenceError(
            code="write-evidence-already-claimed",
            message=(
                f"{item.instruction.target.identity.canonical}: a write already buffered in this "
                "transaction claims what this one settles against, for an intent it cannot be "
                "combined with — a different Valid-Time region composes no interval, and an "
                "assignment after a destructive intent resurrects nothing; read the row through "
                "this transaction to flush the buffered intent and settle against fresh state"
            ),
            object_key=claimed,
        )

    def _check_temporal_claims(
        self, item: ObservedKeyedWrite | InsertionKeyedWrite, key: ObjectKey
    ) -> None:
        """Refuse a temporal object's write against existing coverage that
        cannot compose with the object's pending writes, judged over every one
        of them.

        A write an insertion authorized of an object whose insert is still
        pending composes with that opening instead, as already judged; its
        object's other compositions still bound it.
        """
        if not self._admits_temporal(item, key):
            raise _already_claimed(item.instruction.target, key)

    def _claim(self, scope: ClaimScope, position: int, key: ObjectKey) -> None:
        self._claims[scope] = position
        objects = self._claimed_objects
        if objects is not None:
            _note_scope(objects, key, scope)

    def _held_intent(self, scope: ClaimScope) -> WriteIntent | None:
        held = self._claims.get(scope)
        if held is None:
            return None
        write = self._writes[held]
        assert isinstance(write, _CLAIMED)
        return keyed_intent(write.instruction)

    def _objects(self) -> dict[ObjectKey, Hashable]:
        objects = self._claimed_objects
        if objects is None:
            objects = self._claimed_objects = {}
            for scope in self._claims:
                _note_scope(objects, claimed_object(scope), scope)
        return objects

    def _open_insertion(
        self,
        instruction: PreparedKeyedWrite,
        key: ObjectKey,
        insertion_advice: KeyedWriteRefusalAdvice | None,
    ) -> BufferOutcome:
        record = self._ownership.insertion_record(key)
        after_removal = record is not None and (
            record.pending_state == "ended_opening" or self._removed_whole(key, record)
        )
        linked = record is not None and record.pending_state is not None
        writes = self._writes
        writes.append(instruction)
        position = len(writes) - 1
        if after_removal:
            if self._after_removal is None:
                self._after_removal = set()
            self._after_removal.add(position)
        record = self._ownership.open_insert(
            key, insertion_advice, instruction.valid_time_window, position
        )
        if not linked:
            if self._linked is None:
                self._linked = []
            self._linked.append(record)
        return BufferOutcome.BUFFERED

    def _foldable(self, record: InsertionRecord) -> bool:
        """Whether a write of ``record``'s object composes with its
        still-pending insert: one is pending, and no barrier stands between
        them."""
        position = record.pending_position
        return (
            record.pending_state == "opening"
            and position is not None
            and not self._closed(position)
        )

    def _opening_admits(self, record: InsertionRecord, instruction: PreparedKeyedWrite) -> bool:
        """Whether ``instruction`` composes with the still-pending opening of
        ``record``'s object: an assignment never reaches coverage an earlier
        write of the opening destroyed, and a destruction overlapping an
        earlier write states exactly its window
        (:func:`~parallax.core._execution._unit_work.claims.admits_composed`)."""
        position = record.pending_position
        assert position is not None  # a foldable opening is pending
        held = self._writes[position]
        if not isinstance(held, PendingOpening):
            return True
        intent = keyed_intent(instruction)
        assert intent is not None  # an opening's own writes are no inserts
        return (
            admits_composed(((None, held_intent) for held_intent in held.intents), None, intent)
            != "incompatible"
        )

    def _fold_into_opening(
        self, instruction: PreparedKeyedWrite, record: InsertionRecord
    ) -> BufferOutcome:
        """Fold a write into its object's still-pending insert.

        A non-temporal or Transaction-Time-Only opening takes an amendment's
        values in place and is cancelled by any destruction, which removes all
        of it. A Bitemporal opening composes the write over the coverage it
        opens and ends once nothing its writes opened survives. It is then
        cancelled, unless a composed replacement reached stored coverage past
        it: the composed destruction still settles there, though the insert no
        longer stands, so a further insert of the object follows it.
        """
        writes = self._writes
        position = record.pending_position
        assert position is not None  # a foldable opening is pending
        base = writes[position]
        target = instruction.target
        if isinstance(self._temporal_facet.shape(target.identity), temporal_read.Bitemporal):
            opening = (
                base
                if isinstance(base, PendingOpening)
                else PendingOpening(
                    insert=cast("PreparedKeyedWrite", base), transform=NO_TRANSFORM, intents=()
                )
            ).then(instruction, self._key_name(target))
            if opening.survives or opening.transform.assigns:
                writes[position] = opening
                return BufferOutcome.BUFFERED
            if opening.beyond is not None:
                writes[position] = opening
                record.pending_state = "ended_opening"
                record.identity = None
                return BufferOutcome.BUFFERED
        elif instruction.mutation in ASSIGNMENT_MUTATIONS:
            # No carrier wraps an insert, so a pending-insert slot is always a
            # bare instruction — and folding an update into it yields an insert,
            # which is why the merged item stays bare.
            assert isinstance(base, PreparedKeyedWrite)
            writes[position] = _merge_assignment_into_insert(
                base, instruction, self._key_name(target)
            )
            return BufferOutcome.BUFFERED
        writes[position] = None
        record.unlink()
        record.identity = None
        if self._after_removal is not None:
            self._after_removal.discard(position)
        return BufferOutcome.CANCELLED_PENDING_INSERT

    def _add_existing(
        self,
        item: BufferItem,
        instruction: PreparedKeyedWrite,
        key: ObjectKey,
        record: InsertionRecord | None,
        *,
        verdict: ClaimVerdict | None,
        temporal: bool,
    ) -> None:
        """Compose an admitted write against existing state into the pending
        batch."""
        if instruction.mutation in DESTRUCTIVE_MUTATIONS and not isinstance(
            self._temporal_facet.shape(instruction.target.identity), temporal_read.Bitemporal
        ):
            if self._removals is None:
                self._removals = set()
            self._removals.add(key)
            if record is not None and record.pending_state == "opening":
                # A barrier kept this removal after the object's pending
                # insert, which therefore executes and opens the row this one
                # removes.
                record.pending_state = "before_removal"
                record.stored_count = 1
        if temporal:
            assert isinstance(item, ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite)
            self._add_temporal(item, key)
        elif isinstance(item, _CLAIMED):
            assert verdict is not None  # admission judged the claimed scope
            self._combine_claimed(item, key, verdict)
        else:
            self._writes.append(item)

    def _combine_claimed(self, item: _Claimed, key: ObjectKey, verdict: ClaimVerdict) -> None:
        """Combine ``item`` with the write pending at its own scope, or open
        that scope, as admission's ``verdict`` decided: assignments merge in
        authored order, a destruction supersedes the assignments buffered
        before it, and a repeated destruction of one scope and region adds
        nothing.

        Which write ``item`` meets is decided by what it settles against and
        never by its key alone, so writes of two states of one key may
        interleave without either displacing the other. A write an insertion
        authorized meets an observed write of the same state as its peer, and
        the survivor keeps the observed write's evidence, which it still
        spends.
        """
        writes = self._writes
        scope = buffered_claim_scope(item, key)
        assert scope is not None  # admission gave every claimed write its scope
        if isinstance(item, TargetKeyedWrite):
            if self._conditioned is None:
                self._conditioned = {}
            self._conditioned[key] = scope
        index = self._claims.get(scope)
        if index is not None and self._closed(index) and verdict in ("coalesce", "supersede"):
            # A barrier stands between the two: each keeps its own side, and
            # this one starts from the state the earlier one leaves.
            regions = self._regions
            assert regions is not None  # a closed region exists only behind a barrier
            writes.append(item)
            position = len(writes) - 1
            regions.follows[position] = regions.follows.get(index, 0) + 1
            self._claim(scope, position, key)
            return
        if verdict == "coalesce":
            assert index is not None  # an unclaimed scope admits
            base = writes[index]
            assert isinstance(base, _CLAIMED)
            writes[index] = _merged_claimed(base, item)
            return
        if verdict == "deduplicate":
            assert index is not None  # an unclaimed scope admits
            base = writes[index]
            assert isinstance(base, _CLAIMED)
            writes[index] = _with_composed_authority(base, item, base.instruction)
            return
        if index is not None and verdict == "supersede":
            base = writes[index]
            assert isinstance(base, _CLAIMED)
            writes[index] = None
            item = _with_composed_authority(item, base, item.instruction)
        writes.append(item)
        self._claim(scope, len(writes) - 1, key)

    def _add_temporal(self, item: TemporalKeyedWrite, key: ObjectKey) -> None:
        writes = self._writes
        index = self._temporal.get(key)
        held = None if index is None else writes[index]
        if index is None or held is None:
            sealed = None if self._regions is None else self._regions.temporal.get(key)
            if sealed is None:
                writes.append(item)
            else:
                # An earlier region writes the object: that composition hands
                # on what it derives, and this one starts from it.
                key_name = self._key_name(item.instruction.target)
                latest = sealed[-1]
                earlier = writes[latest]
                assert isinstance(earlier, _TEMPORAL)
                writes[latest] = chained_temporal_write(earlier, key_name, leads=True)
                writes.append(chained_temporal_write(item, key_name, follows=True))
            self._temporal[key] = len(writes) - 1
            return
        assert isinstance(held, _TEMPORAL)
        if (
            isinstance(held, ObservedKeyedWrite)
            and isinstance(item, ObservedKeyedWrite)
            and held.retained_observation is item.retained_observation
        ):
            held_intent = keyed_intent(held.instruction)
            intent = keyed_intent(item.instruction)
            assert held_intent is not None and intent is not None  # neither is an insert
            if held_intent.valid_time_window == intent.valid_time_window:
                verdict = admits(held_intent, intent)
                if verdict == "coalesce":
                    writes[index] = _merged_claimed(held, item)
                    return
                if verdict == "deduplicate":
                    return
                if verdict == "supersede":
                    writes[index] = None
                    writes.append(item)
                    self._temporal[key] = len(writes) - 1
                    return
        key_name = self._key_name(item.instruction.target)
        composed = composed_temporal_write(held, item, key_name)
        writes[index] = (
            chained_temporal_write(composed, key_name, leads=held.leads, follows=held.follows)
            if isinstance(held, ChainedTemporalWrite)
            else composed
        )

    def _admits_temporal(self, item: TemporalKeyedWrite, key: ObjectKey) -> bool:
        """Whether ``item``, a write of temporal object ``key`` against its
        existing coverage, composes with that object's pending writes — every
        one of them, in every barrier region, overwritten ones included.

        Observed writes and those an insertion authorized compose with each
        other by the window algebra
        (:func:`~parallax.core._execution._unit_work.claims.admits_composed`). A write a
        caller addressed meets each other write of the object on its own terms:

        * over exactly its window, the two start from one state — the caller's
          stated Transaction-Time start and the observed rectangle's agreeing —
          and no assignment follows a destruction;
        * over a disjoint window, adjacent ones included, the two are separate
          operations, unless an observed rectangle holds the caller's start at
          another Transaction-Time start, which no current coverage can satisfy;
        * over any other overlapping window, never.
        """
        compositions = self._compositions(key)
        if not compositions:
            return True
        intent = keyed_intent(item.instruction)
        assert intent is not None  # a write against existing coverage is no insert
        scope = item.retained_observation.key if isinstance(item, ObservedKeyedWrite) else None
        if not isinstance(item, TargetKeyedWrite) and not any(
            _targeted(held) for held in compositions
        ):
            return (
                admits_composed(
                    (pair for held in compositions for pair in _composed_intents(held)),
                    scope,
                    intent,
                )
                != "incompatible"
            )
        entity = item.instruction.target
        arriving = temporal_contribution(item)
        start = self._starting_revision(entity, arriving)
        untargeted: list[tuple[ObjectStateKey | None, WriteIntent]] = []
        for held in compositions:
            for contribution in _contributions(held):
                if arriving.condition is None and contribution.condition is None:
                    untargeted.append((_scope(contribution), _intent(contribution)))
                elif not self._separable(entity, contribution, arriving, start):
                    return False
        return admits_composed(untargeted, scope, intent) != "incompatible"

    def _separable(
        self,
        entity: EntityMetadata,
        held: TemporalContribution,
        arriving: TemporalContribution,
        start: object | None,
    ) -> bool:
        """Whether two writes of one temporal object, at least one a caller
        addressed, can stand together: as one exact-window operation, or as
        separate ones over disjoint windows (:meth:`_admits_temporal`)."""
        held_window = held.valid_time_window
        arriving_window = arriving.valid_time_window
        if held_window == arriving_window:
            return (
                not (held.kind == "destructive" and arriving.kind == "assignment")
                and start is not None
                and self._starting_revision(entity, held) == start
            )
        # Writes without Valid Time span the whole axis, so every two of an
        # object's are equal and only Valid-Time windows differ.
        assert held_window is not None and arriving_window is not None
        if held_window.overlaps(arriving_window):
            return False
        return self._rectangle_admits(entity, held, arriving) and self._rectangle_admits(
            entity, arriving, held
        )

    def _rectangle_admits(
        self,
        entity: EntityMetadata,
        addressed: TemporalContribution,
        observed: TemporalContribution,
    ) -> bool:
        """Whether ``observed``'s rectangle, where it holds ``addressed``'s
        start, stands at the Transaction-Time start that caller stated."""
        condition = addressed.condition
        observation = observed.observation
        if condition is None or not isinstance(observation, TemporalObservation):
            return True
        shape = self._temporal_facet.shape(entity.identity)
        assert isinstance(shape, temporal_read.Bitemporal)  # disjoint windows are Valid Time's
        window = addressed.valid_time_window
        predecessor = observation.predecessor
        coverage = valid_time_coverage(shape, predecessor, None)
        assert window is not None and coverage is not None  # both lie on Valid Time
        if not coverage.contains(window.start):
            return True
        return milestone_edge(shape, predecessor, None).tx_time == condition.instant

    def _starting_revision(
        self, entity: EntityMetadata, contribution: TemporalContribution
    ) -> object | None:
        """The Transaction-Time start ``contribution`` requires of the coverage
        at its window's start: its caller's, or the observed rectangle's own.
        An insertion's write states none."""
        if contribution.condition is not None:
            return contribution.condition.instant
        observation = contribution.observation
        if not isinstance(observation, TemporalObservation):
            return None
        shape = self._temporal_facet.shape(entity.identity)
        assert shape is not None  # the facet covers every accepted Entity
        return milestone_edge(shape, observation.predecessor, None).tx_time

    def _states_window(self, key: ObjectKey, window: TimeInterval | None) -> bool:
        """Whether a pending write of temporal object ``key`` states exactly
        ``window`` as its own."""
        return any(
            contribution.valid_time_window == window
            for held in self._compositions(key)
            for contribution in _contributions(held)
        )

    def _removed_whole(self, key: ObjectKey, record: InsertionRecord) -> bool:
        """Whether the pending writes of ``key`` remove everything its
        admissions opened, so a further insertion of it is a first opening.

        An insertion still pending is removed whole only from beyond a barrier,
        since a removal beside it cancels it instead. A Non-Temporal or
        Transaction-Time-Only removal there already counts the insertion as
        stored, so only a Bitemporal opening is judged here: the writes buffered
        after it must destroy all the coverage it opens.
        """
        if record.pending_state != "opening":
            return record.has_stored_coverage and self._removes_stored(key, record)
        window = record.valid_time_window
        position = record.pending_position
        if window is None or position is None or self._foldable(record):
            return False
        return window.first_uncovered(self._destroyed_coverage(key, after=position)) is None

    def _removes_stored(self, key: ObjectKey, record: InsertionRecord) -> bool:
        """Whether the pending writes of ``key`` remove everything its admitted
        insertions left stored.

        A Non-Temporal row is removed whole by a pending delete, and so is a
        Transaction-Time-Only object by a termination. A Bitemporal object's
        stored coverage lies between its earliest admitted anchor and the latest
        end among the rows those admissions opened, so the pending writes must
        destroy all of that window.
        """
        if record.valid_time_window is None:
            return self._removals is not None and key in self._removals
        window = self._ownership.removal_window(record)
        return window.first_uncovered(self._destroyed_coverage(key)) is None

    def _destroyed_coverage(self, key: ObjectKey, *, after: int = -1) -> Iterator[TimeInterval]:
        """The Valid-Time intervals the pending writes of Bitemporal object
        ``key`` buffered after position ``after`` destroy, ordered by start.

        Each barrier region's composition yields its own destroyed segments,
        already ordered, and a lone destructive write its prepared window.
        Regions stand in authored order rather than temporal order, so their
        streams are merged by start, holding one interval per region rather
        than copying any. Duplicate and overlapping intervals may remain. The
        view reads the batch as it stands, so it is consumed before the batch
        changes.
        """
        streams = [_destroyed(held) for held in self._compositions(key, after)]
        if len(streams) == 1:
            return streams[0]
        return heapq.merge(*streams, key=_START)

    def _compositions(self, key: ObjectKey, after: int = -1) -> tuple[_PendingTemporal, ...]:
        """Every pending composition of temporal object ``key`` buffered after
        position ``after``, in authored order, one per barrier region that
        writes it."""
        index = self._temporal.get(key)
        held = None if index is None else self._writes[index]
        assert held is None or isinstance(held, _TEMPORAL)
        # The current region follows every position a caller asks after.
        assert index is None or index > after
        sealed = None if self._regions is None else self._regions.temporal.get(key)
        if sealed is None:
            return () if held is None else (held,)
        writes = self._writes
        earlier = tuple(
            cast("_PendingTemporal", writes[position]) for position in sealed if position > after
        )
        return earlier if held is None else (*earlier, held)

    def _seal(self) -> None:
        """Close the current barrier region at the barrier about to be
        appended: no later write combines with a write before it."""
        regions = self._regions
        if regions is None:
            regions = self._regions = _Regions()
        regions.start = len(self._writes)
        temporal = self._temporal
        for key, index in temporal.items():
            regions.temporal.setdefault(key, []).append(index)
        temporal.clear()

    def _closed(self, index: int) -> bool:
        """Whether the pending write at ``index`` stands before the latest
        barrier."""
        regions = self._regions
        return regions is not None and index < regions.start

    def _is_temporal(self, item: BufferItem) -> bool:
        """Whether ``item`` is a write of a temporal object against its existing
        coverage, the writes that compose by object rather than by claimed
        scope."""
        return isinstance(
            item, ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite
        ) and isinstance(
            self._temporal_facet.shape(item.instruction.target.identity),
            temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
        )

    def _key_name(self, entity: EntityMetadata) -> str:
        position = self._families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
        return position.primary_key.identity.name

    def _clear_batch(self) -> None:
        self._writes.clear()
        self._claims.clear()
        self._temporal.clear()
        self._removals = None
        self._after_removal = None
        self._linked = None
        self._conditioned = None
        self._claimed_objects = None
        self._regions = None


class _Regions:
    """The barrier regions of a batch that holds a readless predicate write.

    ``start`` is the position of the latest barrier: every write before it
    stands in a closed region. ``temporal`` holds where each temporal object's
    compositions in closed regions stand, in order, and ``follows`` how many
    earlier writes of its scope each Non-Temporal write a barrier kept apart
    follows.
    """

    __slots__ = ("follows", "start", "temporal")

    def __init__(self) -> None:
        self.start = 0
        self.temporal: dict[ObjectKey, list[int]] = {}
        self.follows: dict[int, int] = {}


def _note_scope(objects: dict[ObjectKey, Hashable], key: ObjectKey, scope: ClaimScope) -> None:
    held = objects.get(key)
    if held is None:
        objects[key] = scope
    elif held != scope:
        objects[key] = _SEVERAL


def _composed_intents(
    held: _PendingTemporal,
) -> tuple[tuple[ObjectStateKey | None, WriteIntent], ...]:
    """Each write ``held`` composes, as the scope it claims and the intent it
    states over its window."""
    if not isinstance(held, ComposedTemporalWrite):
        intent = keyed_intent(held.instruction)
        assert intent is not None  # a write against existing coverage is no insert
        scope = held.retained_observation.key if isinstance(held, ObservedKeyedWrite) else None
        return ((scope, intent),)
    return tuple(
        (_scope(contribution), _intent(contribution)) for contribution in held.contributions
    )


def _scope(contribution: TemporalContribution) -> ObjectStateKey | None:
    retained = contribution.retained_observation
    return None if retained is None else retained.key


def _intent(contribution: TemporalContribution) -> WriteIntent:
    return WriteIntent(kind=contribution.kind, valid_time_window=contribution.valid_time_window)


def _destroyed(held: _PendingTemporal) -> Iterator[TimeInterval]:
    """The Valid-Time intervals ``held`` destroys, ordered by start."""
    if isinstance(held, ComposedTemporalWrite):
        for segment in held.transform.segments:
            if segment.assigned is None:
                window = segment.valid_time_window
                assert window is not None  # only a Bitemporal object's coverage is asked for
                yield window
        return
    instruction = held.instruction
    if instruction.mutation not in ASSIGNMENT_MUTATIONS:
        window = instruction.valid_time_window
        assert window is not None  # only a Bitemporal object's coverage is asked for
        yield window


_START: Final = attrgetter("start")


def _targeted(held: _PendingTemporal) -> bool:
    """Whether a caller-addressed write is among ``held``."""
    if isinstance(held, ComposedTemporalWrite):
        return any(contribution.condition is not None for contribution in held.contributions)
    return isinstance(held, TargetKeyedWrite)


def _contributions(held: _PendingTemporal) -> tuple[TemporalContribution, ...]:
    if isinstance(held, ComposedTemporalWrite):
        return held.contributions
    return (temporal_contribution(held),)


def _merge_assignment_into_insert(
    insert: PreparedKeyedWrite, assigned: PreparedKeyedWrite, key_name: str
) -> PreparedKeyedWrite:
    """Overlay ``assigned``'s non-key row fields onto ``insert``'s row.

    The coalesced write keeps the insert's mutation verb and Valid-Time window
    (so it still opens a current milestone / fully-current rectangle at
    settling per temporal flavor) but carries the FINAL values — no
    ``INSERT`` + ``UPDATE``.
    """
    merged = dict(insert.rows[0])
    for name, value in assigned.rows[0].items():
        if name != key_name:
            merged[name] = value
    return derive_keyed_write(insert, (merged,))


def _merged_claimed(base: _Claimed, arriving: _Claimed) -> _Claimed:
    """``base`` carrying ``arriving``'s assignments too, later value winning.

    The surviving carrier keeps ``base``'s position, window, and claim — the
    two claim one scope over one window, which is what let them coalesce — and
    gains the merged row under the verb they leave (:func:`_coalesced`).
    """
    merged = dict(base.instruction.rows[0])
    merged.update(arriving.instruction.rows[0])
    return _with_composed_authority(
        base, arriving, _coalesced(base.instruction, arriving.instruction, merged)
    )


def _with_composed_authority(
    first: _Claimed, second: _Claimed, instruction: PreparedKeyedWrite
) -> _Claimed:
    """``instruction`` in the carrier of whichever of two writes of one scope
    a caller conditioned, else whichever a read authorized — ``first`` where
    both or neither were.

    A caller's condition outranks a read's evidence because it must still be
    met whatever the survivor writes, and the survivor then spends every
    retained observation either write was admitted through. A read's evidence
    outranks an insertion's authority because the survivor still has to spend
    it, and the two settle against the same state. Where both were read, both
    were admitted through the one live observation their attempt holds for that
    state (`UnitOfWork.retain`), so the survivor's claim is the other's too.
    """
    target = (
        first
        if isinstance(first, TargetKeyedWrite)
        else second
        if isinstance(second, TargetKeyedWrite)
        else None
    )
    if target is not None:
        retained = target.retained_observations
        for write in (first, second):
            for observation in _retained_observations(write):
                if all(observation is not held for held in retained):
                    retained = (*retained, observation)
        return replace(target, instruction=instruction, retained_observations=retained)
    carrier = second if isinstance(first, InsertionKeyedWrite) else first
    return replace(carrier, instruction=instruction)


def _retained_observations(write: _Claimed) -> tuple[RetainedObservation, ...]:
    if isinstance(write, TargetKeyedWrite):
        return write.retained_observations
    # Only an observed write shares a caller's scope: an object-claimed write's
    # unversioned object has no version a caller could state, and a caller
    # addressing an object this attempt inserted is refused.
    assert isinstance(write, ObservedKeyedWrite)
    return (write.retained_observation,)


def _coalesced(
    base: PreparedKeyedWrite, arriving: PreparedKeyedWrite, merged: Mapping[str, object]
) -> PreparedKeyedWrite:
    """``base`` over the ``merged`` row, replacing where either write did: a
    replacement's complete state overlaid by an amendment, or overlaying one,
    is still the complete state a replacement establishes over its window."""
    if arriving.mutation not in REPLACE_MUTATIONS or base.mutation in REPLACE_MUTATIONS:
        return derive_keyed_write(base, (merged,))
    bounded = base.mutation.endswith("Until")
    return derive_keyed_write(base, (merged,), mutation="replaceUntil" if bounded else "replace")


def _resolve_allocated_openings(opened: Openings, allocated: tuple[object, ...]) -> Openings:
    named = tuple(
        _allocated_endpoint(opening, key)
        for opening, key in zip(opened.allocated, allocated, strict=True)
    )
    return Openings(fresh=(*opened.fresh, *named), continued=opened.continued, shared=opened.shared)


def _allocated_endpoint(opening: AllocatedOpening, key: object) -> OwnedEndpoint:
    return OwnedEndpoint(opening.entity, (key,), opening.ends)


def _already_claimed(target: EntityMetadata, key: ObjectKey) -> WriteEvidenceError:
    return WriteEvidenceError(
        code="write-evidence-already-claimed",
        message=(
            f"{target.identity.canonical}: a write already buffered in this transaction cannot "
            "be composed with this one — an assignment after a destructive intent over its "
            "window resurrects nothing, and a destructive intent composes only with writes of "
            "exactly its own window; read the row through this transaction to flush the "
            "buffered intent and settle against fresh state"
        ),
        object_key=key,
    )
