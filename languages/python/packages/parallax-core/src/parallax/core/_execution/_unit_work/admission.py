from __future__ import annotations

import datetime as dt
from collections.abc import Collection, Hashable, Iterator
from dataclasses import replace
from enum import Enum
from typing import Final, Protocol

from parallax.core._execution._unit_work._errors import (
    WRITE_EVIDENCE_ALREADY_CLAIMED,
    WRITE_EVIDENCE_INSERTED,
    write_evidence_refusal,
)
from parallax.core._execution._unit_work._write_ownership import (
    InsertionComposition,
    KeyedWriteRefusalAdvice,
)
from parallax.core._execution._unit_work.claims import (
    ClaimScope,
    ClaimVerdict,
    WriteIntent,
    admits,
    admits_composed,
    claimed_object,
    keyed_intent,
)
from parallax.core._execution._unit_work.evidence import InsertionIdentity, RetainedObservation
from parallax.core._execution._unit_work.instructions import (
    DESTRUCTIVE_MUTATIONS,
    REPLACE_MUTATIONS,
    PreparedKeyedInstruction,
    derive_keyed_instruction,
)
from parallax.core._execution._unit_work.source_registry import SourceRegistry
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    CallerConditioned,
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    ComposedWrite,
    InsertionAuthorized,
    KeyedInsert,
    LicensedWrite,
    PostRemovalInsert,
    SourceBacked,
    StateObserved,
    TemporalCoverageAuthority,
    TemporalCoverageWrite,
    TemporalIntent,
    TxStartConditioned,
    UnversionedLocked,
    VersionConditioned,
    WriteAuthority,
    compact_observed_run,
    compose_temporal_write,
    distinct_evidence,
    is_licensed_by,
)
from parallax.core.internal import inheritance, temporal_read
from parallax.core.internal.base import UsageError
from parallax.core.internal.metamodel import CompiledEntity, Metamodel
from parallax.core.internal.planned_step.keys import ObjectKey, ObjectStateKey
from parallax.core.internal.planned_step.managed_row import ManagedRow
from parallax.core.internal.planned_step.observe import PredecessorRow, TemporalObservation
from parallax.core.internal.temporal_read import TimeInterval, milestone_edge, valid_time_coverage
from parallax.core.internal.temporal_write.coverage import NO_TRANSFORM

__all__ = [
    "BufferOutcome",
    "HoldStatedRevision",
    "WriteAdmission",
]


class BufferOutcome(Enum):
    """What buffering one accepted item did to the buffer's pending inserts.

    Both values mean the item was buffered; a refused item raises instead.
    ``CANCELLED_PENDING_INSERT`` reports a destructive keyed write that left
    nothing of a still-unflushed insert of its object — the pair the flush
    emits nothing for — and nothing about SQL.
    """

    BUFFERED = "buffered"
    CANCELLED_PENDING_INSERT = "cancelled-pending-insert"


type _PendingItem = AdmittedWrite | ComposedTemporalWrite | ComposedBitemporalOpening | None

type _Claimed = LicensedWrite[WriteAuthority]

_SEVERAL: Final = object()
"""What the object view records for an object claimed at more than one
scope."""


class HoldStatedRevision(Protocol):
    """Hold the revision a target write's caller stated, answering the write
    as holding it left it — with any row it read that the write keeps — or
    refuse the write with its condition's refusal."""

    def __call__[A: CallerConditioned](self, item: LicensedWrite[A], /) -> LicensedWrite[A]: ...


class WriteAdmission:
    """One unit of work's accepted writes: the buffer composed as each
    write is admitted, every claim it holds, and where each still-pending
    insert stands in it (`m-unit-work` "Observed-State Coalescing").

    :meth:`admit` accepts a write a source licensed, :meth:`admit_target` a
    write a caller conditioned, and :meth:`admit_insert` an insert, or each
    refuses it, with nothing pending changed. The lifecycle of each
    insertion — whether it still stands, what it left stored, and when it
    retires — is ``registry``'s, which this asks through its named
    transitions. Composition follows authored order:

    * an amendment or replacement of an object whose insert is still pending
      folds into that insert, and a destructive write of it cancels the pair; a
      Bitemporal opening instead composes over its coverage only the writes its
      own insertion authorized
      (:class:`~parallax.core._execution._unit_work.write_items.ComposedBitemporalOpening`),
      and a write a read authorized changes the coverage that read observed;
    * writes claiming one non-temporal scope coalesce by the claim algebra
      (:func:`~parallax.core._execution._unit_work.claims.admits`), a
      target write keeping its condition through every overwrite and
      destruction;
    * a temporal object's writes against its existing coverage — observed ones,
      those an admitted insertion authorized, and target writes
      alike — compose, once a second arrives, into one
      :class:`~parallax.core._execution._unit_work.write_items.ComposedTemporalWrite`,
      whose transform keeps only surviving values while every write's
      condition stays. An initial run of writes of one observed state over one
      window keeps one intent, as a non-temporal pair coalesces, and a
      destruction superseding that run moves the composition to the buffer's
      tail. Writes of the object over disjoint windows stay separate
      operations inside it, each with its own condition.

    Planning borrows :meth:`composed_writes` without changing it; only a
    successfully planned buffer is drained (:meth:`drain_planned`).
    """

    __slots__ = (
        "_after_removal",
        "_claimed_objects",
        "_claims",
        "_families",
        "_first_insert_key",
        "_first_insert_position",
        "_pending_insert_positions",
        "_registry",
        "_removals",
        "_temporal",
        "_temporal_facet",
        "_version_conditioned",
        "_writes",
    )

    def __init__(self, meta: Metamodel, *, registry: SourceRegistry) -> None:
        self._families = inheritance.inheritance_facet_of(meta)
        self._temporal_facet = temporal_read.temporal_facet_of(meta)
        self._registry = registry
        self._writes: list[_PendingItem] = []
        # Every claim the buffer holds, by its scope: the position of the write
        # that holds it. A temporal object's writes against its coverage are
        # indexed by object instead (`_temporal`).
        self._claims: dict[ClaimScope, int] = {}
        self._temporal: dict[ObjectKey, int] = {}
        # Objects a pending write removes whole, and the positions of inserts
        # that must follow a removal of an earlier insertion — each allocated by
        # the first write it records, since most buffers hold none.
        self._removals: set[ObjectKey] | None = None
        self._after_removal: set[int] | None = None
        # The position of each object's latest pending insert, a composition
        # its insertion ended included. A lone object's stays in the two
        # first-insert fields until a second object's moves both into a map:
        # most buffers holding an insert hold one, and a map retains far more
        # than two fields.
        self._first_insert_key: ObjectKey | None = None
        self._first_insert_position = 0
        self._pending_insert_positions: dict[ObjectKey, int] | None = None
        # The scope of each object's pending version-conditioned write,
        # allocated by the first such write.
        self._version_conditioned: dict[ObjectKey, ClaimScope] | None = None
        # The scope each claimed object is claimed at, built by the first
        # question that needs it and kept current from then on.
        self._claimed_objects: dict[ObjectKey, Hashable] | None = None

    def __bool__(self) -> bool:
        """Whether the buffer has anything for a flush to process —
        composed writes, or writes composition left nothing of."""
        return bool(self._writes)

    def admit(self, item: LicensedWrite[SourceBacked]) -> BufferOutcome:
        """Accept ``item``, a write of existing state a source licensed, into
        the buffer, composing it there — all of it, or nothing.

        A write an insertion authorized is admitted only while that authority
        stands. An arriving keyed intent a held claim cannot absorb is refused
        (``write-evidence-already-claimed``). The outcome reports whether
        ``item``, a destructive write leaving nothing of its object's
        still-pending insert and reaching no stored coverage past it,
        cancelled that pair.
        """
        if is_licensed_by(item, InsertionAuthorized):
            item = self._resolve_insertion(item)
        if (
            is_licensed_by(item, StateObserved) or is_licensed_by(item, InsertionAuthorized)
        ) and self._is_temporal(item.target):
            return self._admit_temporal(item)
        verdict = self._check_keyed_claim(item)
        folded = self._folded(item)
        if folded is not None:
            return folded
        # Only a write folding into its object's pending insert claims nothing.
        assert verdict is not None
        key = item.object_key
        self._note_removal(item.instruction, key)
        self._combine_claimed(item, key, verdict)
        return BufferOutcome.BUFFERED

    def admit_target(
        self,
        item: LicensedWrite[CallerConditioned],
        *,
        hold_stated_revision: HoldStatedRevision | None,
    ) -> None:
        """Accept ``item``, a write a caller conditioned, into the buffer,
        composing it there — all of it, or nothing.

        It is refused where this attempt inserted its object
        (``write-evidence-inserted``) or it cannot join the object's pending
        writes (``write-evidence-already-claimed``). Only then, unless a
        pending write of the same state already proves the state it starts
        from, ``hold_stated_revision`` holds the caller's revision, or refuses
        it; with none, nothing is read and the condition stays the write's.
        """
        if is_licensed_by(item, TxStartConditioned):
            self._admit_temporal_target(item, hold_stated_revision)
            return
        assert is_licensed_by(item, VersionConditioned)  # a caller states one of the two
        self._admit_versioned_target(item, hold_stated_revision)

    def admit_insert(
        self, insert: KeyedInsert, *, insertion_advice: KeyedWriteRefusalAdvice | None
    ) -> InsertionIdentity:
        """Accept ``insert`` into the buffer, answering the identity of the
        insertion it opens — or refuse a repeat of an insertion still standing,
        with nothing pending changed
        (:meth:`~parallax.core._execution._unit_work.source_registry.SourceRegistry.open_insertion`).

        ``insertion_advice`` is kept for a repeat of this insertion. Where an
        earlier insertion of the object is stored and a pending write removes
        all of it, the insert executes after that removal.
        """
        writes = self._writes
        key = insert.object_key
        held = self._composition(key)
        identity, follows_removal = self._registry.open_insertion(
            insert,
            pending_removal=None if held is None else held.transform,
            removes_object=self._removals is not None and key in self._removals,
            insertion_advice=insertion_advice,
        )
        position = len(writes)
        writes.append(insert)
        if follows_removal:
            if self._after_removal is None:
                self._after_removal = set()
            self._after_removal.add(position)
        self._index_pending_insert(key, position)
        return identity

    def _pending_insert_position(self, key: ObjectKey) -> int | None:
        positions = self._pending_insert_positions
        if positions is not None:
            return positions.get(key)
        return self._first_insert_position if key == self._first_insert_key else None

    def _index_pending_insert(self, key: ObjectKey, position: int) -> None:
        positions = self._pending_insert_positions
        first = self._first_insert_key
        if positions is not None:
            positions[key] = position
        elif first is None or first == key:
            self._first_insert_key = key
            self._first_insert_position = position
        else:
            self._pending_insert_positions = {first: self._first_insert_position, key: position}
            self._first_insert_key = None

    def _unindex_pending_insert(self, key: ObjectKey) -> None:
        positions = self._pending_insert_positions
        if positions is not None:
            del positions[key]
        else:
            assert key == self._first_insert_key  # a cancelled insert was pending
            self._first_insert_key = None

    def _pending_insert_keys(self) -> Collection[ObjectKey]:
        positions = self._pending_insert_positions
        if positions is not None:
            return positions
        first = self._first_insert_key
        return () if first is None else (first,)

    def _admit_temporal(
        self, item: LicensedWrite[StateObserved | InsertionAuthorized]
    ) -> BufferOutcome:
        """Admit a keyed write of a temporal object, refused where it cannot
        compose with that object's pending writes, judged over every one of
        them. A write folding into its object's still-pending insert is judged
        against the object's other compositions too."""
        key = item.object_key
        instruction = item.instruction
        write_intent = keyed_intent(instruction)
        assert write_intent is not None  # a write against existing coverage is no insert
        arriving = TemporalIntent(write_intent, item.authority)
        if not self._admits_temporal(item.target, key, arriving):
            raise _already_claimed(key)
        folded = self._folded(item)
        if folded is not None:
            return folded
        self._note_removal(instruction, key)
        self._add_temporal(item, arriving, key)
        return BufferOutcome.BUFFERED

    def _folded(self, item: LicensedWrite[SourceBacked]) -> BufferOutcome | None:
        """What folding ``item`` into its object's still-pending insert did, or
        ``None`` where it writes existing state instead: a Bitemporal opening
        takes only a write its own insertion authorized.

        An object's indexed insert is still pending unless composition ended
        it as a Bitemporal opening, and only a write that opening's insertion
        authorized could fold there: that authority ended with it, so such a
        write was already refused.
        """
        key = item.object_key
        position = self._pending_insert_position(key)
        if position is None:
            return None
        if not self._is_bitemporal(item.target):
            return self._fold_non_bitemporal_opening(item, key, position)
        if is_licensed_by(item, InsertionAuthorized):
            return self._fold_bitemporal_opening(item, key, position)
        return None

    def composed_writes(self) -> tuple[ComposedWrite, ...]:
        """The buffer's composed writes, in authored order, with every
        cancelled write gone, every Bitemporal opening composed with the writes
        its insertion authorized, and every insert that must follow a removal
        marked as such."""
        written: list[ComposedWrite] = []
        after_removal = self._after_removal or ()
        for index, item in enumerate(self._writes):
            if item is None:
                continue
            if index in after_removal:
                # Only an insert, or an opening composed over one, follows a removal.
                assert isinstance(item, KeyedInsert | ComposedBitemporalOpening)
                written.append(PostRemovalInsert(item))
            else:
                written.append(item)
        return tuple(written)

    def drain_planned(self) -> None:
        """End the buffer its flush planned.

        An insertion the buffer held is stored from then on, unless a later
        write of the buffer removes it, and a removal of everything an earlier
        insertion of an object opened retires that insertion's authority.
        """
        removals = self._removals
        pending_keys = self._pending_insert_keys()
        if removals is not None or pending_keys:
            self._registry.finish_insertion_planning(
                pending_keys=pending_keys,
                removed_objects=() if removals is None else removals,
            )
        self._clear_buffer()

    def discard(self) -> None:
        """Drop the buffer and its claims."""
        self._clear_buffer()

    def _admit_temporal_target(
        self,
        item: LicensedWrite[TxStartConditioned],
        hold_stated_revision: HoldStatedRevision | None,
    ) -> None:
        instruction = item.instruction
        key = item.object_key
        arriving = TemporalIntent(self._target_intent(item), item.authority)
        if not self._admits_temporal(item.target, key, arriving):
            raise _already_claimed(key)
        if hold_stated_revision is not None and not self._states_window(
            key, instruction.valid_time_window
        ):
            held = hold_stated_revision(item)
            if held.authority is not item.authority:
                arriving = TemporalIntent(arriving.write_intent, held.authority)
            item = held
        self._note_removal(instruction, key)
        self._add_temporal(item, arriving, key)

    def _admit_versioned_target(
        self,
        item: LicensedWrite[VersionConditioned],
        hold_stated_revision: HoldStatedRevision | None,
    ) -> None:
        intent = self._target_intent(item)
        scope = item.claim_scope
        assert scope is not None  # a caller's stated version names the state it claims
        key = item.object_key
        held = self._objects().get(key)
        verdict = admits(self._held_intent(scope), intent)
        if (held is not None and held != scope) or verdict == "incompatible":
            raise _already_claimed(key)
        if hold_stated_revision is not None and scope not in self._claims:
            hold_stated_revision(item)
        self._note_removal(item.instruction, key)
        self._combine_claimed(item, key, verdict)

    def _target_intent(self, item: LicensedWrite[CallerConditioned]) -> WriteIntent:
        """What ``item``, a write a caller conditioned, intends — refused where
        this attempt inserted its object."""
        key = item.object_key
        if self._registry.has_admitted_insertion(key):
            raise write_evidence_refusal(
                WRITE_EVIDENCE_INSERTED,
                key,
                "this transaction inserted the object this write addresses, so no caller's "
                "revision describes it; until the transaction commits, write it through the "
                "value the insert took or a read of it",
            )
        intent = keyed_intent(item.instruction)
        assert intent is not None  # a target write is no insert
        return intent

    def _resolve_insertion(
        self, item: LicensedWrite[InsertionAuthorized]
    ) -> LicensedWrite[InsertionAuthorized]:
        """``item`` checked against the authority it carries, given the claim
        scope its stored Non-Temporal row takes, and checked against the
        still-pending opening it folds into — or refused.

        The registry is asked again here, after preparation, because
        preparation runs caller-owned code that can retire or supersede the
        insertion.
        """
        item = self._registry.resolve_insertion_authorized_write(item)
        position = self._pending_insert_position(item.object_key)
        if position is not None and not self._opening_admits(position, item.instruction):
            raise _already_claimed(item.object_key)
        return item

    def _check_keyed_claim(self, item: LicensedWrite[SourceBacked]) -> ClaimVerdict | None:
        """What a non-temporal write becomes against the claim held at its
        scope, or ``None`` where it claims nothing — refused where it cannot
        join that claim or its object's pending caller-conditioned write."""
        scope = item.claim_scope
        if scope is None:
            return None
        intent = keyed_intent(item.instruction)
        assert intent is not None  # a claimed write is no insert
        claimed = claimed_object(scope)
        conditioned = (
            None if self._version_conditioned is None else self._version_conditioned.get(claimed)
        )
        verdict = admits(self._held_intent(scope), intent)
        if conditioned in (None, scope) and verdict != "incompatible":
            return verdict
        raise write_evidence_refusal(
            WRITE_EVIDENCE_ALREADY_CLAIMED,
            claimed,
            "a write already buffered in this transaction claims what this one settles "
            "against, for an intent it cannot be combined with — a different Valid-Time region "
            "composes no interval, and an assignment after a destructive intent resurrects "
            "nothing; read the row through this transaction to flush the buffered intent and "
            "settle against fresh state",
        )

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
        assert isinstance(write, LicensedWrite)
        return keyed_intent(write.instruction)

    def _objects(self) -> dict[ObjectKey, Hashable]:
        objects = self._claimed_objects
        if objects is None:
            objects = self._claimed_objects = {}
            for scope in self._claims:
                _note_scope(objects, claimed_object(scope), scope)
        return objects

    def _opening_admits(self, position: int, instruction: PreparedKeyedInstruction) -> bool:
        """Whether ``instruction`` composes with the still-pending opening at
        ``position``: an assignment never reaches coverage an earlier write of
        the opening destroyed, and a destruction overlapping an earlier write
        states exactly its window
        (:func:`~parallax.core._execution._unit_work.claims.admits_composed`)."""
        held = self._writes[position]
        if not isinstance(held, ComposedBitemporalOpening):
            return True
        intent = keyed_intent(instruction)
        assert intent is not None  # an opening's own writes are no inserts
        return (
            admits_composed(((None, held_intent) for held_intent in held.intents), None, intent)
            != "incompatible"
        )

    def _fold_bitemporal_opening(
        self, write: LicensedWrite[InsertionAuthorized], key: ObjectKey, position: int
    ) -> BufferOutcome:
        """Compose a write its insertion authorized over the coverage that
        insertion's still-pending Bitemporal opening at ``position`` opens.

        The opening ends once nothing its writes opened survives. It is then
        cancelled, unless a composed replacement reached stored coverage past
        it: the composed destruction still settles there, though the insert no
        longer stands, so a further insert of the object follows it.
        """
        writes = self._writes
        base = writes[position]
        if not isinstance(base, ComposedBitemporalOpening):
            assert isinstance(base, KeyedInsert)  # a pending insertion holds its insert
            base = ComposedBitemporalOpening(insert=base, transform=NO_TRANSFORM, intents=())
        instruction = write.instruction
        opening = base.followed_by(instruction, self._key_name(instruction.target))
        composition = self._registry.apply_insertion_composition(
            key, arriving=write, proposed_opening=opening
        )
        if composition is InsertionComposition.CANCELLED:
            return self._cancel_opening(key, position)
        writes[position] = opening
        return BufferOutcome.BUFFERED

    def _fold_non_bitemporal_opening(
        self, item: LicensedWrite[SourceBacked], key: ObjectKey, position: int
    ) -> BufferOutcome:
        """Fold a write into its object's still-pending Non-Temporal or
        Transaction-Time-Only insert at ``position``, which takes an
        amendment's values in place and is cancelled by any destruction, which
        removes all of it."""
        composition = self._registry.apply_insertion_composition(
            key, arriving=item, proposed_opening=None
        )
        if composition is InsertionComposition.CANCELLED:
            return self._cancel_opening(key, position)
        writes = self._writes
        base = writes[position]
        # Only a Bitemporal opening composes, so this slot holds the insert
        # itself, which the amendment leaves an insert.
        assert isinstance(base, KeyedInsert)
        instruction = item.instruction
        writes[position] = replace(
            base,
            instruction=_merge_assignment_into_insert(
                base.instruction, instruction, self._key_name(instruction.target)
            ),
        )
        return BufferOutcome.BUFFERED

    def _cancel_opening(self, key: ObjectKey, position: int) -> BufferOutcome:
        """Drop the pending insert at ``position`` that composition left
        nothing of, with its object's pending insert position."""
        self._writes[position] = None
        self._unindex_pending_insert(key)
        if self._after_removal is not None:
            self._after_removal.discard(position)
        return BufferOutcome.CANCELLED_PENDING_INSERT

    def _note_removal(self, instruction: PreparedKeyedInstruction, key: ObjectKey) -> None:
        """Record that a destruction of a Non-Temporal or Transaction-Time-Only
        object removes it whole."""
        if instruction.mutation in DESTRUCTIVE_MUTATIONS and not self._is_bitemporal(
            instruction.target
        ):
            if self._removals is None:
                self._removals = set()
            self._removals.add(key)

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
        the survivor keeps the observed write's evidence.
        """
        writes = self._writes
        scope = item.claim_scope
        assert scope is not None  # admission gave every claimed write its scope
        if isinstance(item.authority, VersionConditioned):
            if self._version_conditioned is None:
                self._version_conditioned = {}
            self._version_conditioned[key] = scope
        index = self._claims.get(scope)
        if verdict == "coalesce":
            assert index is not None  # an unclaimed scope admits
            base = writes[index]
            assert isinstance(base, LicensedWrite)
            writes[index] = _merged_claimed(base, item)
            return
        if verdict == "deduplicate":
            assert index is not None  # an unclaimed scope admits
            base = writes[index]
            assert isinstance(base, LicensedWrite)
            writes[index] = _merged_survivor(base, item, base.instruction)
            return
        if index is not None and verdict == "supersede":
            base = writes[index]
            assert isinstance(base, LicensedWrite)
            writes[index] = None
            item = _merged_survivor(item, base, item.instruction)
        writes.append(item)
        self._claim(scope, len(writes) - 1, key)

    def _add_temporal(
        self,
        item: LicensedWrite[TemporalCoverageAuthority],
        arriving: TemporalIntent[TemporalCoverageAuthority],
        key: ObjectKey,
    ) -> None:
        """Compose ``item``, which keeps ``arriving``, with its object's
        pending writes, or buffer it alone as the object's first.

        A first write stays the admitted write it is until a second arrives,
        which composes the two. While the pending writes keep one observed
        intent, an arriving write of the identical observation over the same
        window takes the claim algebra's verdict instead of another intent: a
        destruction superseding the run's assignments moves the composition to
        the buffer's tail, after everything authored before it, and the run
        otherwise keeps its position.
        """
        writes = self._writes
        index = self._temporal.get(key)
        held = self._composition(key)
        if index is None or held is None:
            writes.append(item)
            self._temporal[key] = len(writes) - 1
            return
        key_name = self._key_name(item.target)
        if is_licensed_by(arriving, StateObserved):
            verdict = _observed_run_verdict(held, arriving)
            if verdict == "supersede":
                writes[index] = None
                writes.append(compact_observed_run(held, item, arriving, key_name))
                self._temporal[key] = len(writes) - 1
                return
            if verdict is not None:
                writes[index] = compact_observed_run(held, item, arriving, key_name)
                return
        writes[index] = compose_temporal_write(held, item, arriving, key_name)

    def _admits_temporal(
        self,
        entity: CompiledEntity,
        key: ObjectKey,
        arriving: TemporalIntent[TemporalCoverageAuthority],
    ) -> bool:
        """Whether a write of temporal object ``key`` against its existing
        coverage, keeping ``arriving``, composes with that object's pending
        writes — every one of them, overwritten ones included.

        Observed writes and those an insertion authorized compose with each
        other by the window algebra
        (:func:`~parallax.core._execution._unit_work.claims.admits_composed`). A
        target write meets each other write of the object on its own terms:

        * over exactly its window, the two start from one state — the caller's
          stated Transaction-Time start and the observed rectangle's agreeing —
          and no assignment follows a destruction;
        * over a disjoint window, adjacent ones included, the two are separate
          operations, unless an observed rectangle holds the caller's start at
          another Transaction-Time start, which no current coverage can satisfy;
        * over any other overlapping window, never.

        An observed write whose source continues through what this attempt's
        completed writes left is judged by the current row the attempt holds
        there, not by the rectangle its source observed.
        """
        held = self._composition(key)
        if held is None:
            return True
        intents = held.intents
        targeted = isinstance(arriving.authority, TxStartConditioned)
        scope = _observed_scope(arriving)
        write_intent = arriving.write_intent
        if not targeted and not any(
            isinstance(prior.authority, TxStartConditioned) for prior in intents
        ):
            return admits_composed(_scoped(intents), scope, write_intent) != "incompatible"
        start = self._starting_revision(entity, key, arriving)
        untargeted: list[tuple[ObjectStateKey | None, WriteIntent]] = []
        for prior in intents:
            if not targeted and not isinstance(prior.authority, TxStartConditioned):
                untargeted.append((_observed_scope(prior), prior.write_intent))
            elif not self._separable(entity, key, prior, arriving, start):
                return False
        return admits_composed(untargeted, scope, write_intent) != "incompatible"

    def _separable(
        self,
        entity: CompiledEntity,
        key: ObjectKey,
        prior: TemporalIntent[TemporalCoverageAuthority],
        arriving: TemporalIntent[TemporalCoverageAuthority],
        start: object | None,
    ) -> bool:
        """Whether the write keeping ``arriving``, from Transaction-Time
        ``start``, can stand beside the pending write that keeps ``prior`` —
        two writes of one temporal object, at least one a caller addressed —
        as one exact-window operation, or as separate ones over disjoint
        windows (:meth:`_admits_temporal`)."""
        prior_window = prior.write_intent.valid_time_window
        window = arriving.write_intent.valid_time_window
        if prior_window == window:
            return (
                not (
                    prior.write_intent.kind == "destructive"
                    and arriving.write_intent.kind == "assignment"
                )
                and start is not None
                and self._starting_revision(entity, key, prior) == start
            )
        # Writes without Valid Time span the whole axis, so every two of an
        # object's are equal and only Valid-Time windows differ.
        assert prior_window is not None and window is not None
        if prior_window.overlaps(window):
            return False
        return self._rectangle_admits(entity, key, prior, prior_window, arriving) and (
            self._rectangle_admits(entity, key, arriving, window, prior)
        )

    def _rectangle_admits(
        self,
        entity: CompiledEntity,
        key: ObjectKey,
        conditioned: TemporalIntent[TemporalCoverageAuthority],
        window: TimeInterval,
        other: TemporalIntent[TemporalCoverageAuthority],
    ) -> bool:
        """Whether ``other``'s observed rectangle — or, where its source
        continues, the current row the attempt holds — where it holds
        ``window``'s start, stands at the Transaction-Time start a caller
        stated for ``conditioned``. A write no caller conditioned states no
        start to disagree with, and one that observed nothing holds no
        rectangle to disagree."""
        authority = conditioned.authority
        observed = _retained_observation(other)
        if not isinstance(authority, TxStartConditioned) or observed is None:
            return True
        observation = observed.evidence
        if not isinstance(observation, TemporalObservation):
            return True
        shape = self._temporal_facet.shape(entity.identity)
        assert isinstance(shape, temporal_read.Bitemporal)  # disjoint windows are Valid Time's
        if observed.invalidated:
            held = self._held_at(key, shape, window.start)
            return held is None or authority.holds(milestone_edge(shape, held, None).tx_time)
        predecessor = observation.predecessor
        coverage = valid_time_coverage(shape, predecessor, None)
        assert coverage is not None  # a Bitemporal observation lies on Valid Time
        if not coverage.contains(window.start):
            return True
        return authority.holds(milestone_edge(shape, predecessor, None).tx_time)

    def _starting_revision(
        self,
        entity: CompiledEntity,
        key: ObjectKey,
        intent: TemporalIntent[TemporalCoverageAuthority],
    ) -> object | None:
        """The Transaction-Time start the pending or arriving write of
        temporal object ``key`` keeping ``intent`` requires of the coverage at
        its window's start: its caller's, the observed rectangle's own, or,
        where its source continues through what the attempt's completed
        writes left, that of the current row the attempt holds there. An
        insertion's write states none, and neither does a continuing one whose
        row there the attempt does not hold."""
        match intent.authority:
            case TxStartConditioned(revision=revision):
                return revision
            case InsertionAuthorized():
                return None
            case StateObserved(retained_observation=observed):
                observation = observed.evidence
                if not isinstance(observation, TemporalObservation):
                    return None
                shape = self._temporal_facet.shape(entity.identity)
                assert isinstance(
                    shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal
                )
                if observed.invalidated:
                    window = intent.write_intent.valid_time_window
                    held = self._held_at(key, shape, None if window is None else window.start)
                    return None if held is None else milestone_edge(shape, held, None).tx_time
                return milestone_edge(shape, observation.predecessor, None).tx_time

    def _held_at(
        self,
        key: ObjectKey,
        shape: temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
        instant: dt.datetime | None,
    ) -> PredecessorRow | None:
        """The current row of ``key`` holding Valid-Time ``instant`` — its one
        current row without Valid Time — among those the attempt's completed
        writes produced and hold, if any."""
        for row in self._registry.planning_ownership(concluding=False).current_rows(key, None):
            coverage = valid_time_coverage(shape, row, None)
            if instant is None or coverage is None or coverage.contains(instant):
                return row
        return None

    def _states_window(self, key: ObjectKey, window: TimeInterval | None) -> bool:
        """Whether a pending write of temporal object ``key`` states exactly
        ``window`` as its own."""
        held = self._composition(key)
        return held is not None and any(
            prior.write_intent.valid_time_window == window for prior in held.intents
        )

    def _composition(self, key: ObjectKey) -> TemporalCoverageWrite | None:
        """The pending writes of temporal object ``key`` against its existing
        coverage — one alone, or their composition — if any."""
        index = self._temporal.get(key)
        held = None if index is None else self._writes[index]
        assert (
            held is None
            or isinstance(held, ComposedTemporalWrite)
            or is_licensed_by(held, StateObserved)
            or is_licensed_by(held, InsertionAuthorized)
            or is_licensed_by(held, TxStartConditioned)
        )  # an object's temporal slot holds its writes against its coverage
        return held

    def _is_temporal(self, entity: CompiledEntity) -> bool:
        """Whether ``entity`` is temporal, so a write of its existing coverage
        composes by object rather than by claimed scope."""
        return isinstance(
            self._temporal_facet.shape(entity.identity),
            temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
        )

    def _is_bitemporal(self, entity: CompiledEntity) -> bool:
        return isinstance(self._temporal_facet.shape(entity.identity), temporal_read.Bitemporal)

    def _key_name(self, entity: CompiledEntity) -> str:
        position = self._families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
        return position.primary_key.identity.name

    def _clear_buffer(self) -> None:
        self._writes.clear()
        self._claims.clear()
        self._temporal.clear()
        self._removals = None
        self._after_removal = None
        self._first_insert_key = None
        self._pending_insert_positions = None
        self._version_conditioned = None
        self._claimed_objects = None


def _note_scope(objects: dict[ObjectKey, Hashable], key: ObjectKey, scope: ClaimScope) -> None:
    held = objects.get(key)
    if held is None:
        objects[key] = scope
    elif held != scope:
        objects[key] = _SEVERAL


def _scoped(
    intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...],
) -> Iterator[tuple[ObjectStateKey | None, WriteIntent]]:
    """Each of ``intents`` as the scope it claims and the intent it states
    over its window."""
    return ((_observed_scope(prior), prior.write_intent) for prior in intents)


def _observed_run_verdict(
    held: TemporalCoverageWrite, arriving: TemporalIntent[StateObserved]
) -> ClaimVerdict | None:
    """What the claim algebra makes of ``arriving`` against ``held``'s initial
    observed run — ``held`` keeping one observed intent of the identical
    observation over the same window — or ``None`` where ``held`` is no such
    run."""
    intents = held.intents
    if len(intents) != 1:
        return None
    (only,) = intents
    if (
        _retained_observation(only) is not arriving.authority.retained_observation
        or only.write_intent.valid_time_window != arriving.write_intent.valid_time_window
    ):
        return None
    verdict = admits(only.write_intent, arriving.write_intent)
    # Admission refused an assignment after the run's destruction before it
    # composed anything.
    assert verdict != "incompatible"
    return verdict


def _observed_scope(intent: TemporalIntent[TemporalCoverageAuthority]) -> ObjectStateKey | None:
    observed = _retained_observation(intent)
    return None if observed is None else observed.key


def _retained_observation(
    intent: TemporalIntent[TemporalCoverageAuthority],
) -> RetainedObservation | None:
    match intent.authority:
        case StateObserved(retained_observation=observed):
            return observed
        case InsertionAuthorized() | TxStartConditioned():
            return None


def _merge_assignment_into_insert(
    insert: PreparedKeyedInstruction, assigned: PreparedKeyedInstruction, key_name: str
) -> PreparedKeyedInstruction:
    """Overlay ``assigned``'s non-key row fields onto ``insert``'s row.

    The coalesced write keeps the insert's mutation verb and Valid-Time window
    (so it still opens a current milestone / fully-current rectangle at
    settling per temporal flavor) but carries the FINAL values — no
    ``INSERT`` + ``UPDATE``.
    """
    (row,) = insert.rows
    (overlay,) = assigned.rows
    key = overlay.selection.members.shape.position(key_name)
    if key is not None:
        overlay = overlay.without(1 << key)
    return derive_keyed_instruction(
        insert, (row.with_members_of(overlay),), assigns=insert.assigns or assigned.assigns
    )


def _merged_claimed(base: _Claimed, arriving: _Claimed) -> _Claimed:
    """``base`` carrying ``arriving``'s assignments too, later value winning.

    The surviving write keeps ``base``'s position, window, and claim — the
    two claim one scope over one window, which is what let them coalesce — and
    gains the merged row under the verb they leave (:func:`_coalesced`).
    """
    (row,) = base.instruction.rows
    (overlay,) = arriving.instruction.rows
    return _merged_survivor(
        base,
        arriving,
        _coalesced(base.instruction, arriving.instruction, row.with_members_of(overlay)),
    )


def _merged_survivor(
    first: _Claimed, second: _Claimed, instruction: PreparedKeyedInstruction
) -> _Claimed:
    """``instruction`` in the write of whichever of two writes of one scope
    a caller conditioned, else whichever a read authorized — ``first`` where
    both or neither were — retaining the exact source evidence of both.

    A caller's condition outranks a read's evidence because it must still be
    met whatever the survivor writes. A read's evidence outranks an insertion's
    authority, since the two settle against the same state. Sources resolving
    to one scope may have observed different states, or published equal but
    distinct evidence, so the survivor keeps every source's evidence by
    identity rather than the one its own write held.
    """
    match first.authority, second.authority:
        case (VersionConditioned() | TxStartConditioned(), _):
            survivor, other = first, second
        case (_, VersionConditioned() | TxStartConditioned()) | (InsertionAuthorized(), _):
            survivor, other = second, first
        case _:
            survivor, other = first, second
    match survivor.authority:
        case StateObserved() | UnversionedLocked() | VersionConditioned() as authority:
            evidence = distinct_evidence((authority.source_evidence, other.source_evidence))
            if evidence is not authority.source_evidence:
                authority = replace(authority, source_evidence=evidence)
            return replace(survivor, instruction=instruction, authority=authority)
        case InsertionAuthorized() | TxStartConditioned():
            # Only a pair of insertion-authorized writes leaves one of them
            # surviving, and insertion authority holds no Read Evidence.
            return replace(survivor, instruction=instruction)


def _coalesced(
    base: PreparedKeyedInstruction, arriving: PreparedKeyedInstruction, merged: ManagedRow
) -> PreparedKeyedInstruction:
    """``base`` over the ``merged`` row, replacing where either write did: a
    replacement's complete state overlaid by an amendment, or overlaying one,
    is still the complete state a replacement establishes over its window."""
    assigns = base.assigns or arriving.assigns
    if arriving.mutation not in REPLACE_MUTATIONS or base.mutation in REPLACE_MUTATIONS:
        return derive_keyed_instruction(base, (merged,), assigns=assigns)
    bounded = base.mutation.endswith("Until")
    return derive_keyed_instruction(
        base, (merged,), mutation="replaceUntil" if bounded else "replace", assigns=assigns
    )


def _already_claimed(key: ObjectKey) -> UsageError:
    return write_evidence_refusal(
        WRITE_EVIDENCE_ALREADY_CLAIMED,
        key,
        "a write already buffered in this transaction cannot be composed with this one — an "
        "assignment after a destructive intent over its window resurrects nothing, and a "
        "destructive intent composes only with writes of exactly its own window; read the row "
        "through this transaction to flush the buffered intent and settle against fresh state",
    )
