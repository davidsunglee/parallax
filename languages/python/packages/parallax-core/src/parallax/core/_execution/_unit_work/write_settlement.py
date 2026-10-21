from __future__ import annotations

from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core._execution._unit_work.instructions import (
    ASSIGNMENT_MUTATIONS,
    INSERT_MUTATIONS,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
)
from parallax.core._execution._unit_work.non_temporal_settlement import (
    DELETION,
    AddressedFacts,
    NonTemporalFacts,
    Revision,
    VersionOverlay,
    non_temporal_step,
)
from parallax.core._execution._unit_work.ranges import (
    DeferredTemporalRange,
    range_source_evidence,
    settle_opening,
    settle_range,
)
from parallax.core._execution._unit_work.retain import ReadEvidence
from parallax.core._execution._unit_work.strategy import (
    ActorIdentity,
    AuditDecoration,
    AuditStrategy,
    Concurrency,
    ConcurrencyStrategy,
)
from parallax.core._execution._unit_work.write_items import (
    CoalescedTemporalWrite,
    FollowingKeyedWrite,
    InsertionKeyedWrite,
    MutationPhase,
    ObjectClaimedBatch,
    ObjectClaimedWrite,
    ObservedKeyedWrite,
    OrderedWrite,
    PendingOpening,
    TargetKeyedWrite,
)
from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.metamodel import AttributeIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import (
    Bitemporal,
    TemporalFacet,
    TemporalShape,
    TransactionTimeOnly,
)
from parallax.core.temporal_write.expansion import (
    TemporalFacts,
    entry_ends,
    opening,
    openings,
)
from parallax.core.write_plan.keys import (
    ObjectKey,
    ObjectStateKey,
    VersionedObjectStateKey,
)
from parallax.core.write_plan.observe import TemporalObservation, WriteObservation
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    AllocatedOpening,
    BoundRange,
    Openings,
    SettledWrite,
    TemporalWriteOwnership,
    WriteGroup,
    WritePlan,
)
from parallax.core.write_plan.planned_rows import (
    WritePlanningError,
    entity_view,
    planned_assignments,
    planned_row,
    resolve_row,
)
from parallax.core.write_plan.steps import (
    ANY_COUNT,
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    RETURNED_MAX_PLUS_ONE,
    UNVERSIONED,
    ExactCount,
    MaxPlusOne,
    PlannedAssignments,
    PlannedDelete,
    PlannedInsert,
    PlannedStep,
    PlannedUpdate,
    PlannedValue,
    WriteRow,
    shortfall_classification,
)

__all__ = ["SettledWriteWithSource", "WritePlanCompiler"]


@dataclass(frozen=True, slots=True, kw_only=True)
class SettledWriteWithSource(SettledWrite):
    """A settled write that keeps alive the exact Read Evidence of every
    source whose write it settled, by identity.

    ``source_evidence`` is an inert lifetime edge: while the plan holding the
    write stays reachable its sources stay registered and their observations
    live, and nothing reads it — completion publishes from the write's own
    completion.
    """

    source_evidence: tuple[ReadEvidence, ...]


_GROUP_WRITES: Final = 64
"""The most settled writes one Write Group holds. In a group of updates or
deletes every insert waits behind every effect of the group, so this bounds how
many settled writes' effects a failing insert wastes, whatever the flush's size;
a batch counts once however many rows it covers. It is not the executor's
per-call statement or row cap."""

type _GroupKey = tuple[AttributeIdentity, object]
"""One object a settled write writes: its family's primary-key Attribute and the
value it holds, so two Entities of one Inheritance Family sharing a key value
name one object and two unrelated Entities never do."""


class WritePlanCompiler:
    """The Write Planner's own compiler of mutation phases into a Write Plan
    (`m-unit-work`): it interprets each write's concurrency and its ordinary
    or temporal semantics and audit, and assembles its steps, Write Groups,
    claims, and proposed effects.

    Constructed once per accepted Metamodel by the planner that owns it, with
    that model, the Inheritance and Temporal facets it compiled, the
    concurrency and audit strategies the composition layer wired, and the
    model's write payload preparer, which judges whether produced temporal
    rows merge.
    :meth:`compile` is its entire surface: no caller settles one item, packs a
    segment, audits a row or step, or collects a claim by hand.
    """

    __slots__ = (
        "_audit",
        "_concurrency",
        "_families",
        "_model",
        "_payloads",
        "_settled",
        "_temporal_facet",
    )

    def __init__(
        self,
        model: Metamodel,
        families: InheritanceFacet,
        temporal_facet: TemporalFacet,
        *,
        concurrency: ConcurrencyStrategy,
        audit: AuditStrategy,
        settled: Container[object],
        payloads: WritePayloadPreparer,
    ) -> None:
        self._model = model
        self._families = families
        self._temporal_facet = temporal_facet
        self._concurrency = concurrency
        self._audit = audit
        self._settled = settled
        self._payloads = payloads

    def compile(
        self,
        phases: Sequence[MutationPhase],
        *,
        concurrency: Concurrency,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
        ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
        counts_unchanged_rows: bool = False,
    ) -> WritePlan:
        """Every mutation phase, in flush order, as one Write Plan.

        Each settled write carries the exact Read Evidence of every source it
        settled (:class:`SettledWriteWithSource`). An item the planner's
        earlier stages retired — folded into a pending insert, cancelled against
        one, or eliminated as a known no-op — never reaches this loop, and
        therefore no settled write carries the evidence it was holding.

        Audit reaches every write as it settles: each row a write produces —
        an opening, or a successor carried or changed — is finalized once, and
        each update and close it emits is decorated once.

        ``actor_identity`` is passed to the audit port and never inspected
        here; ``transaction_instant`` is threaded unevaluated until a surviving
        temporal write needs it.

        Each ordered item settles into one settled write, which records what
        its success publishes: the states it changes, advances, or destroys,
        the rows it removes and opens, and what it leaves for the temporal
        sources it reaches. Consecutive settled writes
        of one mutation phase over distinct objects share a Write Group of at
        most :data:`_GROUP_WRITES`, laid out as every write's effects and then
        every write's inserts, each write's own order kept. A deferred write, a
        write whose insert the database allocates a key for, and a write naming
        no complete object key form a group of their own, and a write naming an
        object the open group already writes starts the next group.
        ``ownership`` answers which current rows this attempt already opened,
        so a write against one of them revises or removes that row instead of
        closing it into history.

        A milestone a write leaves exactly as it was — whether its source
        observed it, an insertion authorized the write, or a caller's condition
        names it — is kept rather than closed and chained, where its unchanged
        state is proven without changing it: by the shared lock under Locking,
        by ownership for a row the attempt opened, and otherwise by a guard
        that matches the milestone at its observed or stated start — which only
        a database whose write count includes unchanged rows
        (``counts_unchanged_rows``) can report. Without that proof the
        milestone is closed and chained as any changed one. A pending
        insertion settles with the writes its insertion authorized as the one
        settled write of new lineages they leave of its window.
        """
        groups: list[WriteGroup] = []
        audit = AuditDecoration(self._audit, actor_identity, transaction_instant, self._settled)
        families = self._families
        for phase in phases:
            members: list[tuple[SettledWrite, tuple[PlannedStep, ...]]] = []
            held: set[_GroupKey] = set()
            for item in phase:
                write, steps = self._settled_write(
                    item, concurrency, transaction_instant, ownership, audit, counts_unchanged_rows
                )
                keys = (
                    None
                    if write.deferred is not None or write.opened.allocated
                    else _object_keys(item, families)
                )
                if keys is None:
                    _close_group(groups, members, held)
                    groups.append(WriteGroup((write,), steps))
                    continue
                if len(members) == _GROUP_WRITES or not held.isdisjoint(keys):
                    _close_group(groups, members, held)
                members.append((write, steps))
                held.update(keys)
            _close_group(groups, members, held)
        return WritePlan(tuple(groups))

    def _settled_write(
        self,
        item: OrderedWrite,
        concurrency: Concurrency,
        transaction_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        guards: bool,
    ) -> tuple[SettledWrite, tuple[PlannedStep, ...]]:
        advances = 0
        if isinstance(item, FollowingKeyedWrite):
            advances = item.advances
            item = item.write
        shape = self._carrier_shape(item)
        if isinstance(item, PendingOpening):
            assert isinstance(shape, Bitemporal)  # only a Bitemporal opening is composed
            return self._opening(
                item, shape, concurrency, transaction_instant, ownership, audit, guards=guards
            )
        if isinstance(shape, TransactionTimeOnly | Bitemporal):
            assert not isinstance(
                item,
                PreparedKeyedWrite
                | PreparedPredicateWrite
                | ObjectClaimedWrite
                | ObjectClaimedBatch,
            )
            return self._range(
                item, shape, concurrency, transaction_instant, ownership, audit, guards=guards
            )
        assert not isinstance(item, CoalescedTemporalWrite)
        settled = self._settle_keyed(item, concurrency, transaction_instant, shape, audit, advances)
        evidence = _source_evidence(item)
        if not evidence:
            write = SettledWrite(
                changed=settled.changed,
                advanced=settled.advanced,
                destroyed=settled.destroyed,
                removed=settled.removed,
                opened=settled.opened,
            )
        else:
            write = SettledWriteWithSource(
                source_evidence=evidence,
                changed=settled.changed,
                advanced=settled.advanced,
                destroyed=settled.destroyed,
                removed=settled.removed,
                opened=settled.opened,
            )
        return write, settled.steps

    def _carrier_shape(self, item: OrderedWrite) -> TemporalShape | None:
        """The Temporal Shape of a buffered carrier's target, read once at
        dispatch; ``None`` for a bare instruction, whose settlement reads it."""
        if isinstance(item, CoalescedTemporalWrite):
            return self._temporal_facet.shape(item.target.identity)
        if isinstance(item, PendingOpening):
            return self._temporal_facet.shape(item.insert.target.identity)
        if isinstance(item, ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite):
            return self._temporal_facet.shape(item.instruction.target.identity)
        return None

    def _settle_keyed(
        self,
        item: (
            PreparedKeyedWrite
            | PreparedPredicateWrite
            | ObservedKeyedWrite
            | ObjectClaimedWrite
            | ObjectClaimedBatch
            | InsertionKeyedWrite
            | TargetKeyedWrite
        ),
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        shape: TemporalShape | None,
        audit: AuditDecoration,
        advances: int = 0,
    ) -> BoundRange:
        """One ordered keyed write's settled steps and completion.
        ``advances`` is how many versions earlier writes of its scope a barrier
        kept before it advance the row past the state that scope names."""
        if isinstance(item, PreparedPredicateWrite):
            view = entity_view(self._families, item.selection.target)
            return BoundRange(steps=(_readless_step(item, view, audit),))
        observation: WriteObservation | None = None
        scope: ObjectStateKey | ObjectKey | None = None
        if isinstance(item, PreparedKeyedWrite):
            instruction = item
        else:
            instruction = item.instruction
            if isinstance(item, ObservedKeyedWrite):
                observation = item.observation
                scope = item.scope
            elif not isinstance(item, ObjectClaimedWrite | ObjectClaimedBatch):
                scope = item.scope
        own_version: int | None = None
        if isinstance(scope, VersionedObjectStateKey):
            own_version = self._advanced(scope.version, advances)
        return self._settle(
            instruction,
            observation,
            concurrency,
            tx_instant,
            shape,
            audit,
            own_version=own_version,
            conditioned=isinstance(item, TargetKeyedWrite),
        )

    def _advanced(self, version: int, advances: int) -> int:
        arithmetic = self._concurrency.version_arithmetic()
        for _ in range(advances):
            version = arithmetic.advance(version)
        return version

    # Stages 5, 6, 7: validate the observation the item arrived carrying, #

    def _settle(
        self,
        instruction: PreparedKeyedWrite,
        observation: WriteObservation | None,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        shape: TemporalShape | None,
        audit: AuditDecoration,
        *,
        own_version: int | None = None,
        conditioned: bool = False,
    ) -> BoundRange:
        """One ordered write's steps and completion. ``own_version`` is the
        version a write advances from in place of the one its ``observation``
        names: the protected state its source's authority reaches, the version
        this attempt's own writes left a row it inserted at, or the version a
        caller's condition requires. ``conditioned`` says the gate binds that
        caller's condition, so a shortfall against it is a failed precondition.

        A versioned update advances the state it starts from and a deletion
        destroys every object it addresses; an unversioned write changes each
        object it addresses without advancing anything.

        A temporal write reaching here travels with no carrier the range path
        takes: an insert opens a new lineage, and any other closes a milestone
        it holds no observation of, which is refused."""
        entity = instruction.target
        if shape is None:
            shape = self._temporal_facet.shape(entity.identity)
        if isinstance(shape, TransactionTimeOnly | Bitemporal):
            if instruction.mutation not in INSERT_MUTATIONS:
                raise _unobserved_close(entity, instruction.mutation)
            return self._settle_temporal_insert(entity, shape, instruction, tx_instant, audit)
        facts = self._non_temporal_facts(entity)
        if instruction.mutation == "insert":
            return BoundRange(steps=(self._settle_insert(facts, instruction, audit),))
        addressed = self._addressed_facts(facts, concurrency, conditioned=conditioned)
        observed_version = (
            self._observed_version(entity, instruction, facts.version_attribute, observation)
            if observation is not None or own_version is None
            else None
        )
        if own_version is not None:
            observed_version = own_version
        step = _decorated(
            audit,
            non_temporal_step(
                facts,
                addressed,
                emission=(
                    DELETION
                    if instruction.mutation == "delete"
                    else Revision(
                        _addressed_assignments(facts, addressed, instruction.rows[0]),
                        self._version_overlay(facts.version_attribute),
                    )
                ),
                key_rows=instruction.rows,
                observed_version=observed_version,
                # One addressed instruction is ONE step however many keys it
                # addresses, so its expectation is the whole batch's (ADR 0044)
                # rather than a per-row one.
                affected_rows=ExactCount(
                    expected=len(instruction.rows), on_shortfall=addressed.shortfall
                ),
            ),
        )
        objects = _addressed_objects(facts, instruction)
        destroyed = objects if instruction.mutation == "delete" else ()
        if observed_version is None:
            return BoundRange(steps=(step,), changed=objects, destroyed=destroyed)
        (target,) = objects  # an observed version addresses exactly one row
        state = VersionedObjectStateKey(target, observed_version)
        return BoundRange(
            steps=(step,),
            changed=(state,),
            advanced=() if destroyed else (state,),
            destroyed=destroyed,
        )

    def _range(
        self,
        item: CoalescedTemporalWrite | ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite,
        shape: TransactionTimeOnly | Bitemporal,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        *,
        guards: bool,
    ) -> tuple[SettledWrite, tuple[PlannedStep, ...]]:
        """``item`` settled as a range over its temporal object's coverage: the
        settled write with the steps it binds now, or the settled write
        carrying the deferred range execution binds, with no step.

        A lone observed write enters as the carrier it was buffered in, so one
        that lies inside the predecessor it observed binds that predecessor at
        once and one reaching beyond it reads the rest at execution. Its
        observation must be the Temporal Observation every close addresses,
        gates on, and carries state forward from, which is refused before the
        attempt captures its instant.
        """
        entity = (
            item.target if isinstance(item, CoalescedTemporalWrite) else item.instruction.target
        )
        if isinstance(item, ObservedKeyedWrite) and not isinstance(
            item.observation, TemporalObservation
        ):
            raise _unobserved_close(entity, item.instruction.mutation)
        ranged = settle_range(
            item,
            view=entity_view(self._families, entity),
            shape=shape,
            gated=self._concurrency.gates(concurrency, self._model, entity.identity),
            # Reaching a surviving temporal write is what makes the attempt
            # capture its instant.
            instant=tx_instant.value(),
            ownership=ownership,
            audit=audit,
            payloads=self._payloads,
            guards=guards,
        )
        evidence = range_source_evidence(item)
        if isinstance(ranged, DeferredTemporalRange):
            if not evidence:
                return SettledWrite(deferred=ranged), ()
            return SettledWriteWithSource(source_evidence=evidence, deferred=ranged), ()
        if not evidence:
            write = SettledWrite(
                changed=ranged.changed,
                removed=ranged.removed,
                opened=ranged.opened,
                derived=ranged.derived,
                current_outputs=ranged.current_outputs,
            )
        else:
            write = SettledWriteWithSource(
                source_evidence=evidence,
                changed=ranged.changed,
                removed=ranged.removed,
                opened=ranged.opened,
                derived=ranged.derived,
                current_outputs=ranged.current_outputs,
            )
        return write, ranged.steps

    def _settle_insert(
        self, facts: NonTemporalFacts, instruction: PreparedKeyedWrite, audit: AuditDecoration
    ) -> PlannedInsert:
        """One keyed insert as its rows, each opening a new lineage.

        An insert observes nothing, gates on nothing, and addresses nothing, so
        the only fact it takes from the mutation beyond its target is the
        version a new lineage opens at — and an unversioned target opens at no
        version, so it asks the strategy for no arithmetic either.
        """
        version = (
            None
            if facts.version_attribute is None
            else (facts.version_attribute, self._concurrency.version_arithmetic().initial)
        )
        entries = tuple(
            audit.finalize_row(
                WriteRow(
                    row=planned_row(facts.entity, facts.view, row, version), origin=NEW_LINEAGE
                )
            )
            for row in instruction.rows
        )
        return PlannedInsert(entity=facts.entity.identity, entries=entries)

    def _non_temporal_facts(self, entity: EntityMetadata) -> NonTemporalFacts:
        """What one non-temporal mutation settles about its target, before a
        row is in hand and whatever the verb does to it.

        The sole site for each of these decisions, whichever representation the
        mutation arrived as: which members the family makes applicable, and
        which Attribute (if any) carries the optimistic version. What only a
        write against EXISTING rows settles belongs to :meth:`_addressed_facts`
        instead.
        """
        return NonTemporalFacts(
            entity=entity,
            view=entity_view(self._families, entity),
            version_attribute=self._concurrency.version_attribute(self._model, entity.identity),
        )

    def _addressed_facts(
        self, facts: NonTemporalFacts, concurrency: Concurrency, *, conditioned: bool = False
    ) -> AddressedFacts:
        """What one non-temporal mutation against EXISTING rows settles before
        a row is in hand.

        The sole site for each of these decisions, whichever representation the
        mutation arrived as: what the target's effective primary key is,
        whether the write gates, and how a shortfall against it classifies. An
        insert never reaches here, so it settles no address it does not use.
        A gate binding a caller's ``conditioned`` revision classifies its
        shortfall as that condition failing.
        """
        gated = self._concurrency.gates(concurrency, self._model, facts.entity.identity)
        return AddressedFacts(
            key_attributes=(facts.view.primary_key.identity,),
            gated=gated,
            shortfall=(
                FAILED_PRECONDITION
                if conditioned and gated
                else shortfall_classification(
                    observing=facts.version_attribute is not None, gated=gated
                )
            ),
        )

    def _version_overlay(
        self, version_attribute: AttributeIdentity | None
    ) -> VersionOverlay | None:
        """The version overlay a settled update carries, or absence for an
        unversioned target — which has no version to advance and therefore asks
        the strategy for no arithmetic."""
        if version_attribute is None:
            return None
        return VersionOverlay(
            attribute=version_attribute, arithmetic=self._concurrency.version_arithmetic()
        )

    def _settle_temporal_insert(
        self,
        entity: EntityMetadata,
        shape: TransactionTimeOnly | Bitemporal,
        instruction: PreparedKeyedWrite,
        tx_instant: TransactionInstant,
        audit: AuditDecoration,
    ) -> BoundRange:
        """One temporal insert as the new lineage it opens over its prepared
        window, the row recorded under the key it states or, where the
        database allocates the key, under the key its insert answers."""
        view = entity_view(self._families, entity)
        # Reaching a surviving temporal insert is what makes the attempt
        # capture its instant; the row's fresh start derives from that value.
        facts = TemporalFacts(entity=entity, view=view, shape=shape, instant=tx_instant.value())
        attributes, value_objects = resolve_row(entity, view, instruction.rows[0], context="insert")
        allocates = _returns_allocated_key(facts, attributes)
        inserts = (
            PlannedInsert(
                entity=entity.identity,
                entries=(
                    audit.finalize_row(
                        opening(facts, attributes, value_objects, instruction.valid_time_window)
                    ),
                ),
            ),
        )
        return BoundRange(
            steps=inserts,
            opened=Openings(
                continued=openings(facts, inserts),
                allocated=_allocated(facts, inserts) if allocates else (),
            ),
        )

    def _opening(
        self,
        opening: PendingOpening,
        shape: Bitemporal,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        *,
        guards: bool,
    ) -> tuple[SettledWrite, tuple[PlannedStep, ...]]:
        """A pending Bitemporal insertion and the writes it authorized since,
        settled as the one settled write of new lineages they leave of its window,
        together with any stored coverage a replacement it authorized reaches
        past that window (:func:`~parallax.core._execution._unit_work.ranges.settle_opening`):
        bound now, or deferred until execution reads that coverage."""
        entity = opening.insert.target
        ranged = settle_opening(
            opening,
            view=entity_view(self._families, entity),
            shape=shape,
            # Only a replacement reaching past the opening reaches stored rows,
            # whose closes the strategy gates.
            gated=opening.beyond is not None
            and self._concurrency.gates(concurrency, self._model, entity.identity),
            # Reaching a surviving temporal insert is what makes the attempt
            # capture its instant; every part's fresh start derives from that value.
            instant=tx_instant.value(),
            ownership=ownership,
            audit=audit,
            payloads=self._payloads,
            guards=guards,
        )
        if isinstance(ranged, DeferredTemporalRange):
            return SettledWrite(deferred=ranged), ()
        write = SettledWrite(
            changed=ranged.changed,
            removed=ranged.removed,
            opened=ranged.opened,
            derived=ranged.derived,
            current_outputs=ranged.current_outputs,
        )
        return write, ranged.steps

    def _observed_version(
        self,
        entity: EntityMetadata,
        instruction: PreparedKeyedWrite,
        version_attr: AttributeIdentity | None,
        observation: WriteObservation | None,
    ) -> int | None:
        """The version an addressed write against a versioned row advances
        from, or ``None`` for an unversioned target.

        A row-carried version value is refused BEFORE the observation is even
        required: the version is framework-owned end to end, so it is never an
        alternative source, observed or not. The observation itself is
        required in both concurrency modes, because the framework never
        issues a resolving read on behalf of a keyed write.

        A returned version therefore came off an observation carrier, which
        wraps exactly one row — so the Key Target the caller builds from
        ``instruction.rows`` is a singleton whenever this returns a version to
        advance from or gate on (`m-unit-work`: a Version Gate requires a
        singleton Key Target). The alternative — one row's observed version
        licensing every key a merged statement addresses — is unconstructable
        rather than merely unreached.

        An unversioned target has no version to advance from AND is entitled to
        no observation at all, so an observation arriving for one is refused
        rather than dropped: this is the model-aware half of the rule
        :class:`~parallax.core._execution._unit_work.write_items.ObservedKeyedWrite`
        delegates here, and discarding the evidence instead would be the
        silently-unobserved mode `m-unit-work` forbids.
        """
        if version_attr is None:
            _require_unobserved(entity, instruction.mutation, observation)
            return None
        if (
            instruction.mutation in ASSIGNMENT_MUTATIONS
            and version_attr.name in instruction.rows[0]
        ):
            self._concurrency.reject_authored_version(entity.identity, version_attr)
        return self._concurrency.require_version(entity.identity, observation)


def _object_keys(item: OrderedWrite, families: InheritanceFacet) -> tuple[_GroupKey, ...] | None:
    """``None`` where a row names no complete key: a readless predicate write,
    or an insert whose key is absent or the database computes."""
    if isinstance(item, FollowingKeyedWrite):
        item = item.write
    if isinstance(item, PreparedPredicateWrite):
        return None
    if isinstance(item, CoalescedTemporalWrite):
        target, rows = item.target, (item.key,)
    elif isinstance(item, PendingOpening):
        target, rows = item.insert.target, item.insert.rows
    else:
        instruction = item if isinstance(item, PreparedKeyedWrite) else item.instruction
        target, rows = instruction.target, instruction.rows
    key = entity_view(families, target).primary_key.identity
    keys: list[_GroupKey] = []
    for row in rows:
        value = row.get(key.name)
        if value is None or isinstance(value, Mapping):
            return None
        keys.append((key, value))
    return tuple(keys)


def _close_group(
    groups: list[WriteGroup],
    members: list[tuple[SettledWrite, tuple[PlannedStep, ...]]],
    held: set[_GroupKey],
) -> None:
    if len(members) == 1:
        ((write, steps),) = members
        groups.append(WriteGroup((write,), steps))
    elif members:
        effects = [step for _, steps in members for step in steps if not _inserts(step)]
        inserts = [step for _, steps in members for step in steps if _inserts(step)]
        groups.append(WriteGroup(tuple(write for write, _ in members), (*effects, *inserts)))
    members.clear()
    held.clear()


def _inserts(step: PlannedStep) -> bool:
    return isinstance(step, PlannedInsert)


def _unobserved_close(entity: EntityMetadata, mutation: str) -> WritePlanningError:
    return WritePlanningError(
        f"{entity.identity.name!r}: a temporal {mutation!r} closes the "
        "current milestone, and every close requires the Temporal Observation it "
        "addresses, gates on, and carries state forward from (m-unit-work; m-opt-lock)"
    )


def _source_evidence(item: OrderedWrite) -> tuple[ReadEvidence, ...]:
    """The exact Read Evidence a Non-Temporal carrier retains, if any."""
    if isinstance(item, ObservedKeyedWrite | ObjectClaimedWrite | ObjectClaimedBatch):
        return item.source_evidence
    if isinstance(item, TargetKeyedWrite):
        return item.source_evidence
    return ()


def _addressed_objects(
    facts: NonTemporalFacts, instruction: PreparedKeyedWrite
) -> tuple[ObjectKey, ...]:
    """Every object an addressed Non-Temporal write names, one per row, keyed
    as admission and reads key them: its concrete Entity and its family's
    primary key."""
    entity = facts.entity.identity
    name = facts.view.primary_key.identity.name
    return tuple(ObjectKey(entity, ((name, row[name]),)) for row in instruction.rows)


def _returns_allocated_key(
    facts: TemporalFacts, attributes: dict[AttributeIdentity, PlannedValue]
) -> bool:
    """Ask the insert that opens a row whose key the database allocates to
    answer that key, so the row is recorded by its complete address."""
    key = facts.view.primary_key.identity
    if not isinstance(attributes.get(key), MaxPlusOne):
        return False
    attributes[key] = RETURNED_MAX_PLUS_ONE
    return True


def _allocated(
    facts: TemporalFacts, inserts: Sequence[PlannedInsert]
) -> tuple[AllocatedOpening, ...]:
    key = facts.view.primary_key.identity
    return tuple(
        AllocatedOpening(facts.entity.identity, entry_ends(facts, entry.row.attributes))
        for insert in inserts
        for entry in insert.entries
        if entry.row.attributes.get(key) == RETURNED_MAX_PLUS_ONE
    )


def _addressed_assignments(
    facts: NonTemporalFacts, addressed: AddressedFacts, row: Mapping[str, object]
) -> PlannedAssignments:
    """The replacement values an addressed update writes, before its version
    overlay.

    Key members address the write rather than change it, so they never appear
    among the assignments. A multi-row update reaching here is one the batching
    strategy collapsed, and it collapses only a run assigning identical values to
    every key (`m-batch-write` keeps incompatible writes in separate steps), so
    the first row settles the whole step's assignments. That holds for a
    PREFORMED multi-row instruction too: the planner's batch decomposition splits
    one into its rows before the collapse decision, so no update arrives here
    having skipped it.
    """
    key_names = frozenset(attribute.name for attribute in addressed.key_attributes)
    return planned_assignments(
        facts.entity,
        facts.view,
        {name: value for name, value in row.items() if name not in key_names},
    )


def _readless_step(
    instruction: PreparedPredicateWrite, view: InheritanceEntityView, audit: AuditDecoration
) -> PlannedStep:
    """A readless predicate-selected write's one unversioned statement over
    every row its selection matches, an update decorated once."""
    entity = instruction.selection.target
    target = instruction.selection
    if instruction.mutation == "delete":
        return PlannedDelete(
            entity=entity.identity, target=target, concurrency=UNVERSIONED, affected_rows=ANY_COUNT
        )
    return audit.decorate_update(
        PlannedUpdate(
            entity=entity.identity,
            target=target,
            assignments=planned_assignments(entity, view, instruction.row),
            concurrency=UNVERSIONED,
            affected_rows=ANY_COUNT,
        )
    )


def _decorated(audit: AuditDecoration, step: PlannedStep) -> PlannedStep:
    """An addressed Non-Temporal step as audit leaves it: an update decorated
    once, a delete as it is."""
    return audit.decorate_update(step) if isinstance(step, PlannedUpdate) else step


def _require_unobserved(
    entity: EntityMetadata, mutation: str, observation: WriteObservation | None
) -> None:
    """Refuse ``observation`` when the target it arrived for is entitled to none.

    Reached only once the caller has established that the target is neither
    temporal nor versioned, which is the one shape `m-unit-work` declares
    observationless ("unversioned Non-Temporal writes have no observation",
    absence structural). Whether a write may hold evidence at all needs the
    model, so the buffered carrier, a keyed
    :class:`~parallax.core._execution._unit_work.write_items.ObservedKeyedWrite`,
    can only refuse the instruction-local half and
    delegate this half to the model-aware settlement. This is that delegation:
    every carrier that IS settled crosses it, whatever produced it, so a
    producer that resolves evidence a target cannot carry is told rather than
    quietly stripped.

    Settled is the whole reach of that guarantee. Coalescing and no-op
    elimination run first, in the stage order `m-unit-work` fixes, and a carrier
    they retire — folded into a pending insert, cancelled against one, or
    eliminated as a key-only no-op — is never settled at all. Nothing is
    stripped there either: the write itself is gone, so its observation gates,
    advances, and attributes nothing.
    """
    if observation is None:
        return
    raise WritePlanningError(
        f"{entity.identity.name!r}: an unversioned Non-Temporal {mutation!r} carries no Write "
        "Observation, yet one was resolved for it — absence is structural (m-unit-work "
        "'unversioned Non-Temporal writes have no observation'), and settling this write "
        "would discard the evidence rather than gate or advance anything with it"
    )
