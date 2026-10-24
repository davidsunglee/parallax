from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Hashable, Iterator, Mapping
from dataclasses import replace
from enum import Enum
from typing import Final

from parallax.core import inheritance, temporal_read
from parallax.core._execution._unit_work._errors import WriteEvidenceError
from parallax.core._execution._unit_work._write_ownership import InsertionComposition
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
    DESTRUCTIVE_MUTATIONS,
    REPLACE_MUTATIONS,
    ExpectedTxStart,
    PreparedKeyedInstruction,
    derive_keyed_instruction,
)
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    RetainedObservation,
)
from parallax.core._execution._unit_work.source_authority import SourceAuthority
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    ComposedWrite,
    InsertionAuthorizedIntent,
    InsertionAuthorizedWrite,
    KeyedInsert,
    ObjectLockedWrite,
    PostRemovalInsert,
    ReadAuthorizedWrite,
    StateObservedIntent,
    StateObservedWrite,
    TargetIntent,
    TargetWrite,
    TemporalCoverageWrite,
    TemporalIntent,
    compact_observed_run,
    compose_temporal_write,
    temporal_intent,
)
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.temporal_read import TimeInterval, milestone_edge, valid_time_coverage
from parallax.core.temporal_write.coverage import NO_TRANSFORM
from parallax.core.write_plan.keys import ObjectKey, ObjectStateKey
from parallax.core.write_plan.observe import PredecessorRow, TemporalObservation

__all__ = [
    "BufferOutcome",
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

type _Claimed = ReadAuthorizedWrite | InsertionAuthorizedWrite | TargetWrite

type _TemporalArrival = StateObservedWrite | InsertionAuthorizedWrite | TargetWrite
"""A write of a temporal object against its existing coverage, which composes
by object rather than by claimed scope."""

_CLAIMED: Final = (StateObservedWrite, ObjectLockedWrite, InsertionAuthorizedWrite, TargetWrite)

_TEMPORAL: Final = (
    StateObservedWrite,
    InsertionAuthorizedWrite,
    TargetWrite,
    ComposedTemporalWrite,
)

_SEVERAL: Final = object()
"""What the object view records for an object claimed at more than one
scope."""


class WriteAdmission:
    """One unit of work's accepted writes: the buffer composed as each
    write is admitted, every claim it holds, and where each still-pending
    insert stands in it (`m-unit-work` "Observed-State Coalescing").

    :meth:`admit` accepts a write under the authority it carries, and
    :meth:`admit_insert` an insert, or either refuses it, with nothing pending
    changed. The lifecycle of each insertion — whether it still stands, what
    it left stored, and when it retires — is ``authority``'s, which this asks
    through its named transitions. Composition follows authored order:

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
        "_authority",
        "_claimed_objects",
        "_claims",
        "_conditioned",
        "_families",
        "_pending_insert_positions",
        "_removals",
        "_temporal",
        "_temporal_facet",
        "_writes",
    )

    def __init__(self, meta: Metamodel, *, authority: SourceAuthority) -> None:
        self._families = inheritance.view(meta)
        self._temporal_facet = temporal_read.view(meta)
        self._authority = authority
        self._writes: list[_PendingItem] = []
        # Every claim the buffer holds, by its scope: the position of the write
        # that holds it. A temporal object's writes against its coverage are
        # indexed by object instead (`_temporal`).
        self._claims: dict[ClaimScope, int] = {}
        self._temporal: dict[ObjectKey, int] = {}
        # Objects a pending write removes whole, the positions of inserts that
        # must follow a removal of an earlier insertion, and the position of
        # each object's latest pending insert, a composition its insertion
        # ended included — each allocated by the first write it records, since
        # most buffers hold none.
        self._removals: set[ObjectKey] | None = None
        self._after_removal: set[int] | None = None
        self._pending_insert_positions: dict[ObjectKey, int] | None = None
        # The scope of each object's pending caller-conditioned write,
        # allocated by the first such write.
        self._conditioned: dict[ObjectKey, ClaimScope] | None = None
        # The scope each claimed object is claimed at, built by the first
        # question that needs it and kept current from then on.
        self._claimed_objects: dict[ObjectKey, Hashable] | None = None

    def __bool__(self) -> bool:
        """Whether the buffer has anything for a flush to process —
        composed writes, or writes composition left nothing of."""
        return bool(self._writes)

    def admit(
        self,
        item: ReadAuthorizedWrite | InsertionAuthorizedWrite | TargetWrite,
        *,
        confirm_target: Callable[[TargetWrite], TargetWrite],
    ) -> BufferOutcome:
        """Accept ``item``, a write of existing state, into the buffer under
        the authority it carries, composing it there — all of it, or nothing.

        A target write is refused where this attempt inserted its
        object (``write-evidence-inserted``) or it cannot join the object's
        pending writes; only then, unless a pending write of the same state
        already proves its starting state, ``confirm_target`` answers it as
        its caller's revision is confirmed, or refuses it. A write an insertion
        authorized is admitted only while that authority stands. An arriving
        keyed intent a held claim cannot absorb is refused
        (``write-evidence-already-claimed``). The outcome reports whether
        ``item``, a destructive write leaving nothing of its object's
        still-pending insert and reaching no stored coverage past it, cancelled
        that pair.
        """
        if isinstance(item, TargetWrite):
            self._admit_target(item, confirm_target)
            return BufferOutcome.BUFFERED
        return self._admit_keyed(item)

    def admit_insert(
        self, insert: KeyedInsert, *, insertion_advice: KeyedWriteRefusalAdvice | None
    ) -> InsertionIdentity | None:
        """Accept ``insert`` into the buffer, answering the identity of the
        insertion it opens — or refuse a repeat of an insertion still standing,
        with nothing pending changed
        (:meth:`~parallax.core._execution._unit_work.source_authority.SourceAuthority.open_insertion`).

        ``insertion_advice`` is kept for a repeat of this insertion. Where an
        earlier insertion of the object is stored and a pending write removes
        all of it, the insert executes after that removal. An insert whose key
        the database allocates opens no insertion and answers ``None``.
        """
        writes = self._writes
        key = insert.object_key
        if key is None:
            writes.append(insert)
            return None
        held = self._composition(key)
        identity, follows_removal = self._authority.open_insertion(
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
        positions = self._pending_insert_positions
        if positions is None:
            positions = self._pending_insert_positions = {}
        positions[key] = position
        return identity

    def _admit_keyed(self, item: ReadAuthorizedWrite | InsertionAuthorizedWrite) -> BufferOutcome:
        if isinstance(item, InsertionAuthorizedWrite):
            item = self._authorized(item)
        if isinstance(item, StateObservedWrite | InsertionAuthorizedWrite) and self._is_temporal(
            item.target
        ):
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

    def _admit_temporal(self, item: StateObservedWrite | InsertionAuthorizedWrite) -> BufferOutcome:
        """Admit a keyed write of a temporal object, refused where it cannot
        compose with that object's pending writes, judged over every one of
        them. A write folding into its object's still-pending insert is judged
        against the object's other compositions too."""
        key = item.object_key
        instruction = item.instruction
        intent = keyed_intent(instruction)
        assert intent is not None  # a write against existing coverage is no insert
        if not self._admits_temporal(item, key, intent):
            raise _already_claimed(instruction.target, key)
        folded = self._folded(item)
        if folded is not None:
            return folded
        self._note_removal(instruction, key)
        self._add_temporal(item, intent, key)
        return BufferOutcome.BUFFERED

    def _folded(self, item: ReadAuthorizedWrite | InsertionAuthorizedWrite) -> BufferOutcome | None:
        """What folding ``item`` into its object's still-pending insert did, or
        ``None`` where it writes existing state instead: a Bitemporal opening
        takes only a write its own insertion authorized.

        An object's indexed insert is still pending unless composition ended
        it as a Bitemporal opening, and only a write that opening's insertion
        authorized could fold there: that authority ended with it, so such a
        write was already refused.
        """
        key = item.object_key
        positions = self._pending_insert_positions
        position = None if positions is None else positions.get(key)
        if position is None:
            return None
        if not self._is_bitemporal(item.target):
            return self._fold_non_bitemporal_opening(item, key, position)
        if isinstance(item, InsertionAuthorizedWrite):
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
        positions = self._pending_insert_positions
        if removals is not None or positions is not None:
            self._authority.finish_insertion_planning(
                pending_keys=() if positions is None else positions,
                removed_objects=() if removals is None else removals,
            )
        self._clear_buffer()

    def discard(self) -> None:
        """Drop the buffer and its claims."""
        self._clear_buffer()

    def _admit_target(
        self,
        item: TargetWrite,
        confirm_target: Callable[[TargetWrite], TargetWrite],
    ) -> None:
        instruction = item.instruction
        target = instruction.target
        scope = item.claim_scope
        key = item.object_key
        if self._authority.has_admitted_insertion(key):
            raise WriteEvidenceError(
                code="write-evidence-inserted",
                message=(
                    f"{target.identity.canonical}: this transaction inserted the object this write "
                    "addresses, so no caller's revision describes it; until the transaction "
                    "commits, write it through the value the insert took or a read of it"
                ),
                object_key=key,
            )
        intent = keyed_intent(instruction)
        assert intent is not None  # a target write is no insert
        if self._is_temporal(target):
            if not self._admits_temporal(item, key, intent):
                raise _already_claimed(target, key)
            if not self._states_window(key, instruction.valid_time_window):
                item = confirm_target(item)
            self._note_removal(instruction, key)
            self._add_temporal(item, intent, key)
            return
        held = self._objects().get(key)
        verdict = admits(self._held_intent(scope), intent)
        if (held is not None and held != scope) or verdict == "incompatible":
            raise _already_claimed(target, key)
        if scope not in self._claims:
            item = confirm_target(item)
        self._note_removal(instruction, key)
        self._combine_claimed(item, key, verdict)

    def _authorized(self, item: InsertionAuthorizedWrite) -> InsertionAuthorizedWrite:
        """``item`` checked against the authority it carries, given the claim
        scope its stored Non-Temporal row takes, and checked against the
        still-pending opening it folds into — or refused.

        The authority is asked again here, after preparation, because
        preparation runs caller-owned code that can retire or supersede it.
        """
        item = self._authority.resolve_insertion_authorized_write(item)
        positions = self._pending_insert_positions
        position = None if positions is None else positions.get(item.object_key)
        if position is not None and not self._opening_admits(position, item.instruction):
            raise _already_claimed(item.instruction.target, item.object_key)
        return item

    def _check_keyed_claim(
        self, item: ReadAuthorizedWrite | InsertionAuthorizedWrite
    ) -> ClaimVerdict | None:
        """What a non-temporal write becomes against the claim held at its
        scope, or ``None`` where it claims nothing — refused where it cannot
        join that claim or its object's pending caller-conditioned write."""
        scope = item.claim_scope
        if scope is None:
            return None
        intent = keyed_intent(item.instruction)
        assert intent is not None  # a claimed write is no insert
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
        self, write: InsertionAuthorizedWrite, key: ObjectKey, position: int
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
        composition = self._authority.apply_insertion_composition(
            key, arriving=write, proposed_opening=opening
        )
        if composition is InsertionComposition.CANCELLED:
            return self._cancel_opening(key, position)
        writes[position] = opening
        return BufferOutcome.BUFFERED

    def _fold_non_bitemporal_opening(
        self, item: ReadAuthorizedWrite | InsertionAuthorizedWrite, key: ObjectKey, position: int
    ) -> BufferOutcome:
        """Fold a write into its object's still-pending Non-Temporal or
        Transaction-Time-Only insert at ``position``, which takes an
        amendment's values in place and is cancelled by any destruction, which
        removes all of it."""
        composition = self._authority.apply_insertion_composition(
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
        positions = self._pending_insert_positions
        assert positions is not None  # a cancelled insert was pending
        del positions[key]
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
        if isinstance(item, TargetWrite):
            if self._conditioned is None:
                self._conditioned = {}
            self._conditioned[key] = scope
        index = self._claims.get(scope)
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

    def _add_temporal(self, item: _TemporalArrival, intent: WriteIntent, key: ObjectKey) -> None:
        """Compose ``item``, stating ``intent``, with its object's pending
        writes, or buffer it alone as the object's first.

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
        held = None if index is None else writes[index]
        if index is None or held is None:
            writes.append(item)
            self._temporal[key] = len(writes) - 1
            return
        assert isinstance(held, _TEMPORAL)  # an object's temporal slot holds its writes
        key_name = self._key_name(item.target)
        arriving = temporal_intent(item, intent)
        if isinstance(item, StateObservedWrite) and isinstance(arriving, StateObservedIntent):
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

    def _admits_temporal(self, item: _TemporalArrival, key: ObjectKey, intent: WriteIntent) -> bool:
        """Whether ``item``, a write of temporal object ``key`` against its
        existing coverage stating ``intent``, composes with that object's
        pending writes — every one of them, overwritten ones included.

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
        targeted = isinstance(item, TargetWrite)
        scope = item.retained_observation.key if isinstance(item, StateObservedWrite) else None
        if not targeted and not any(isinstance(prior, TargetIntent) for prior in intents):
            return admits_composed(_scoped(intents), scope, intent) != "incompatible"
        start = self._starting_revision(item.target, key, item, intent.valid_time_window)
        untargeted: list[tuple[ObjectStateKey | None, WriteIntent]] = []
        for prior in intents:
            if not targeted and not isinstance(prior, TargetIntent):
                untargeted.append((_scope(prior), prior.intent))
            elif not self._separable(key, prior, item, intent, start):
                return False
        return admits_composed(untargeted, scope, intent) != "incompatible"

    def _separable(
        self,
        key: ObjectKey,
        prior: TemporalIntent,
        item: _TemporalArrival,
        intent: WriteIntent,
        start: object | None,
    ) -> bool:
        """Whether ``item``, stating ``intent`` from Transaction-Time
        ``start``, can stand beside the pending write that keeps ``prior`` —
        two writes of one temporal object, at least one a caller addressed —
        as one exact-window operation, or as separate ones over disjoint
        windows (:meth:`_admits_temporal`)."""
        entity = item.target
        prior_window = prior.intent.valid_time_window
        window = intent.valid_time_window
        if prior_window == window:
            return (
                not (prior.intent.kind == "destructive" and intent.kind == "assignment")
                and start is not None
                and self._starting_revision(entity, key, prior, prior_window) == start
            )
        # Writes without Valid Time span the whole axis, so every two of an
        # object's are equal and only Valid-Time windows differ.
        assert prior_window is not None and window is not None
        if prior_window.overlaps(window):
            return False
        if isinstance(prior, TargetIntent) and not self._rectangle_admits(
            entity, key, prior.expected, prior_window, _arriving_observation(item)
        ):
            return False
        return not isinstance(item, TargetWrite) or self._rectangle_admits(
            entity, key, _stated_start(item), window, _observation(prior)
        )

    def _rectangle_admits(
        self,
        entity: EntityMetadata,
        key: ObjectKey,
        expected: ExpectedTxStart,
        window: TimeInterval,
        observed: RetainedObservation | None,
    ) -> bool:
        """Whether ``observed``'s rectangle — or, where its source continues,
        the current row the attempt holds — where it holds ``window``'s start,
        stands at the Transaction-Time start ``expected`` a caller stated. A
        write that observed nothing holds no rectangle to disagree."""
        if observed is None:
            return True
        observation = observed.evidence
        if not isinstance(observation, TemporalObservation):
            return True
        shape = self._temporal_facet.shape(entity.identity)
        assert isinstance(shape, temporal_read.Bitemporal)  # disjoint windows are Valid Time's
        if observed.invalidated:
            held = self._held_at(key, shape, window.start)
            return held is None or milestone_edge(shape, held, None).tx_time == expected.instant
        predecessor = observation.predecessor
        coverage = valid_time_coverage(shape, predecessor, None)
        assert coverage is not None  # a Bitemporal observation lies on Valid Time
        if not coverage.contains(window.start):
            return True
        return milestone_edge(shape, predecessor, None).tx_time == expected.instant

    def _starting_revision(
        self,
        entity: EntityMetadata,
        key: ObjectKey,
        write: TemporalIntent | _TemporalArrival,
        window: TimeInterval | None,
    ) -> object | None:
        """The Transaction-Time start ``write``, a pending or arriving write of
        temporal object ``key`` over ``window``, requires of the coverage at
        the window's start: its caller's, the observed rectangle's own, or,
        where its source continues through what the attempt's completed
        writes left, that of the current row the attempt holds there. An
        insertion's write states none, and neither does a continuing one whose
        row there the attempt does not hold."""
        if isinstance(write, TargetIntent):
            return write.expected.instant
        if isinstance(write, TargetWrite):
            return _stated_start(write).instant
        if isinstance(write, InsertionAuthorizedIntent | InsertionAuthorizedWrite):
            return None
        observed = write.retained_observation
        observation = observed.evidence
        if not isinstance(observation, TemporalObservation):
            return None
        shape = self._temporal_facet.shape(entity.identity)
        assert isinstance(shape, temporal_read.TransactionTimeOnly | temporal_read.Bitemporal)
        if observed.invalidated:
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
        for row in self._authority.planning_ownership(concluding=False).current_rows(key, None):
            coverage = valid_time_coverage(shape, row, None)
            if instant is None or coverage is None or coverage.contains(instant):
                return row
        return None

    def _states_window(self, key: ObjectKey, window: TimeInterval | None) -> bool:
        """Whether a pending write of temporal object ``key`` states exactly
        ``window`` as its own."""
        held = self._composition(key)
        return held is not None and any(
            prior.intent.valid_time_window == window for prior in held.intents
        )

    def _composition(self, key: ObjectKey) -> TemporalCoverageWrite | None:
        """The pending writes of temporal object ``key`` against its existing
        coverage — one alone, or their composition — if any."""
        index = self._temporal.get(key)
        held = None if index is None else self._writes[index]
        assert held is None or isinstance(held, _TEMPORAL)
        return held

    def _is_temporal(self, entity: EntityMetadata) -> bool:
        """Whether ``entity`` is temporal, so a write of its existing coverage
        composes by object rather than by claimed scope."""
        return isinstance(
            self._temporal_facet.shape(entity.identity),
            temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
        )

    def _is_bitemporal(self, entity: EntityMetadata) -> bool:
        return isinstance(self._temporal_facet.shape(entity.identity), temporal_read.Bitemporal)

    def _key_name(self, entity: EntityMetadata) -> str:
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
        self._pending_insert_positions = None
        self._conditioned = None
        self._claimed_objects = None


def _note_scope(objects: dict[ObjectKey, Hashable], key: ObjectKey, scope: ClaimScope) -> None:
    held = objects.get(key)
    if held is None:
        objects[key] = scope
    elif held != scope:
        objects[key] = _SEVERAL


def _scoped(
    intents: tuple[TemporalIntent, ...],
) -> Iterator[tuple[ObjectStateKey | None, WriteIntent]]:
    """Each of ``intents`` as the scope it claims and the intent it states
    over its window."""
    return ((_scope(prior), prior.intent) for prior in intents)


def _observed_run_verdict(
    held: TemporalCoverageWrite, arriving: StateObservedIntent
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
        not isinstance(only, StateObservedIntent)
        or only.retained_observation is not arriving.retained_observation
        or only.intent.valid_time_window != arriving.intent.valid_time_window
    ):
        return None
    verdict = admits(only.intent, arriving.intent)
    # Admission refused an assignment after the run's destruction before it
    # composed anything.
    assert verdict != "incompatible"
    return verdict


def _scope(prior: TemporalIntent) -> ObjectStateKey | None:
    return prior.retained_observation.key if isinstance(prior, StateObservedIntent) else None


def _observation(prior: TemporalIntent) -> RetainedObservation | None:
    return prior.retained_observation if isinstance(prior, StateObservedIntent) else None


def _arriving_observation(item: _TemporalArrival) -> RetainedObservation | None:
    return item.retained_observation if isinstance(item, StateObservedWrite) else None


def _stated_start(item: TargetWrite) -> ExpectedTxStart:
    """The Transaction-Time start a temporal target write's caller states."""
    expectation = item.expectation
    assert isinstance(expectation, ExpectedTxStart)  # preparation states a temporal target's start
    return expectation


def _merge_assignment_into_insert(
    insert: PreparedKeyedInstruction, assigned: PreparedKeyedInstruction, key_name: str
) -> PreparedKeyedInstruction:
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
    return derive_keyed_instruction(insert, (merged,), assigns=insert.assigns or assigned.assigns)


def _merged_claimed(base: _Claimed, arriving: _Claimed) -> _Claimed:
    """``base`` carrying ``arriving``'s assignments too, later value winning.

    The surviving write keeps ``base``'s position, window, and claim — the
    two claim one scope over one window, which is what let them coalesce — and
    gains the merged row under the verb they leave (:func:`_coalesced`).
    """
    merged = dict(base.instruction.rows[0])
    merged.update(arriving.instruction.rows[0])
    return _with_composed_authority(
        base, arriving, _coalesced(base.instruction, arriving.instruction, merged)
    )


def _with_composed_authority(
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
    target = (
        first
        if isinstance(first, TargetWrite)
        else second
        if isinstance(second, TargetWrite)
        else None
    )
    survivor = (
        target
        if target is not None
        else second
        if isinstance(first, InsertionAuthorizedWrite)
        else first
    )
    retained = survivor.source_evidence
    for write in (first, second):
        if write is survivor:
            continue
        for evidence in write.source_evidence:
            if all(evidence is not held for held in retained):
                retained = (*retained, evidence)
    if not retained:
        return replace(survivor, instruction=instruction)
    # Only a pair of insertion-authorized writes leaves one of them surviving,
    # and insertion authority holds no Read Evidence.
    assert not isinstance(survivor, InsertionAuthorizedWrite)
    return replace(survivor, instruction=instruction, source_evidence=retained)


def _coalesced(
    base: PreparedKeyedInstruction, arriving: PreparedKeyedInstruction, merged: Mapping[str, object]
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
