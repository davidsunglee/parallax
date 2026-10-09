from __future__ import annotations

from collections.abc import Container, Mapping, Sequence

from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import AttributeIdentity, AttributeMetadata, EntityMetadata, Metamodel
from parallax.core.temporal_read import (
    NON_TEMPORAL,
    Bitemporal,
    TemporalFacet,
    TemporalShape,
    TransactionTimeOnly,
)
from parallax.core.temporal_write.coverage import NO_TRANSFORM
from parallax.core.temporal_write.expansion import (
    PredecessorExpander,
    TemporalFacts,
    entry_ends,
    opening,
    openings,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.group_segments import (
    DELETION,
    AddressedFacts,
    NonTemporalEmission,
    NonTemporalFacts,
    NonTemporalGroupSegment,
    Revision,
    TemporalGroupSegment,
    VersionOverlay,
    non_temporal_step,
)
from parallax.core.unit_work.instructions import (
    AMEND_MUTATIONS,
    ASSIGNMENT_MUTATIONS,
    INSERT_MUTATIONS,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
)
from parallax.core.unit_work.materialized import (
    ComposedTemporalWrite,
    FollowingKeyedWrite,
    GroupStates,
    InsertionKeyedWrite,
    MaterializedWriteGroup,
    ObservedKeyedWrite,
    PendingOpening,
    ReadlessPredicateWrite,
    TargetKeyedWrite,
    VersionedEvidence,
)
from parallax.core.unit_work.ranges import (
    DeferredGroupRange,
    DeferredTemporalRange,
    defer_group,
    range_claims,
    settle_opening,
    settle_range,
)
from parallax.core.unit_work.retain import RetainedObservation
from parallax.core.unit_work.strategy import (
    ActorIdentity,
    AuditDecoration,
    AuditStrategy,
    Concurrency,
    ConcurrencyStrategy,
)
from parallax.core.write_plan.keys import (
    ObservedStateKey,
    VersionedStateKey,
)
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.observe import TemporalObservation, WriteObservation
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    AllocatedOpening,
    BoundRange,
    CombinedSourceAuthority,
    ExecutionUnit,
    Openings,
    PlannedWrites,
    SourceAuthority,
    StepSegment,
    TemporalWriteOwnership,
    WritePlan,
    eager_segment,
)
from parallax.core.write_plan.planned_rows import (
    WritePlanningError,
    assigned_name,
    entity_view,
    planned_assignments,
    planned_row,
    prepared_assignments,
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
    PlannedUpdate,
    PlannedValue,
    WriteRow,
    shortfall_classification,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = [
    "OrderedWrite",
    "WritePlanCompiler",
]

type OrderedWrite = (
    PreparedKeyedWrite
    | ReadlessPredicateWrite
    | ObservedKeyedWrite
    | InsertionKeyedWrite
    | TargetKeyedWrite
    | FollowingKeyedWrite
    | ComposedTemporalWrite
    | PendingOpening
    | MaterializedWriteGroup
)
"""One element of the sequence settlement reads: a buffer item once the
planner's rewriting stages have finished with it.

An object-claimed write is absent by construction rather than by convention:
coalescing is the only stage that reads one, and it hands the survivor on as the
ordinary instruction it always was, so batching, ordering, and settlement see an
unversioned write as the bare instruction they measure every other one by.
"""


class WritePlanCompiler:
    """The Write Planner's own compiler of ordered writes into a Write Plan
    (`m-unit-work`): it interprets each write's concurrency and its ordinary,
    grouped, or temporal semantics and audit, and assembles step segments,
    unit boundaries, claims, and proposed effects.

    Constructed once per accepted Metamodel by the planner that owns it, with
    that model, the Inheritance and Temporal facets it compiled, and the
    concurrency and audit strategies the composition layer wired.
    :meth:`compile` is its entire surface: no caller settles one item, packs a
    segment, audits a row or step, or collects a claim by hand.
    """

    __slots__ = (
        "_audit",
        "_concurrency",
        "_families",
        "_model",
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
    ) -> None:
        self._model = model
        self._families = families
        self._temporal_facet = temporal_facet
        self._concurrency = concurrency
        self._audit = audit
        self._settled = settled

    def compile(
        self,
        ordered_writes: Sequence[OrderedWrite],
        *,
        concurrency: Concurrency,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
        ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
        counts_unchanged_rows: bool = False,
    ) -> WritePlan:
        """The whole ordered sequence as one Write Plan.

        Each execution unit carries the claim its surviving write settled
        against. An item the planner's earlier stages retired — folded into a
        pending insert, cancelled against one, or eliminated as a known no-op —
        never reaches this loop, and therefore no execution unit carries the
        evidence it was holding (`m-unit-work` "A successful execution unit
        consumes").

        Packing is a property of adjacency, which is why the whole sequence
        crosses in one call: a run of eagerly settled steps stays one eager
        segment, and a Materialized Write Group always occupies its own. A
        group's every group-wide semantic fact — temporal expansion, the
        gate/concurrency decision, the affected-row policy, the assignment
        shape, and the resolved instant if the group needs one — is decided
        into that segment before this returns; the segment, and the ``WritePlan``
        it becomes part of, retain no group, concurrency mode, Transaction
        Instant, or strategy object. Only the PER-ROW data stays as the group's
        own compact evidence, and a row's ``PlannedWrite`` is rebuilt from that
        evidence and the already-settled facts one at a time, on demand, so a
        large materialized run never forces a parallel ``PlannedWrite``-per-row
        object graph merely by being planned.

        Audit reaches every write as it settles, before anything is packed: each
        row a write produces — an opening, or a successor carried or changed —
        is finalized once, and each update and close it emits is decorated
        once. A Materialized Write Group's segment keeps only what its audit
        added, so enumerating its steps audits nothing again.

        ``actor_identity`` is passed to the audit port and never inspected
        here; ``transaction_instant`` is threaded unevaluated until a surviving
        temporal write needs it.

        Each ordered item settles into one execution unit, which records what
        its success changes: the claim it spends, the observed state it
        revises, and the rows it removes and opens. ``ownership`` answers which
        current rows this attempt already opened, so a write against one of
        them revises or removes that row instead of closing it into history.

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
        unit of new lineages they leave of its window.
        """
        segments: list[StepSegment] = []
        pending: list[PlannedStep] = []
        units: list[ExecutionUnit] = []
        count = 0
        audit = AuditDecoration(self._audit, actor_identity, transaction_instant, self._settled)

        def flush_pending() -> None:
            if pending:
                segments.append(eager_segment(tuple(pending)))
                pending.clear()

        for item in ordered_writes:
            advances = 0
            if isinstance(item, FollowingKeyedWrite):
                advances = item.advances
                item = item.write
            if isinstance(item, MaterializedWriteGroup):
                flush_pending()
                segment = self._settle_group(
                    item,
                    concurrency,
                    transaction_instant,
                    ownership,
                    audit,
                    guards=counts_unchanged_rows,
                )
                if isinstance(segment, DeferredGroupRange):
                    units.append(ExecutionUnit(end=count, deferred=segment))
                    continue
                if len(segment):
                    segments.append(segment)
                    count += len(segment)
                units.append(segment.unit(count))
                continue
            shape = self._carrier_shape(item)
            if isinstance(item, PendingOpening):
                assert isinstance(shape, Bitemporal)  # only a Bitemporal opening is composed
                steps, unit = self._opening(
                    item,
                    shape,
                    concurrency,
                    transaction_instant,
                    ownership,
                    audit,
                    start=count,
                    guards=counts_unchanged_rows,
                )
                pending.extend(steps)
                count = unit.end
                units.append(unit)
                continue
            if isinstance(shape, TransactionTimeOnly | Bitemporal):
                assert not isinstance(item, PreparedKeyedWrite | ReadlessPredicateWrite)
                steps, unit = self._range(
                    item,
                    shape,
                    concurrency,
                    transaction_instant,
                    ownership,
                    audit,
                    start=count,
                    guards=counts_unchanged_rows,
                )
                pending.extend(steps)
                count = unit.end
                units.append(unit)
                continue
            assert not isinstance(item, ComposedTemporalWrite | MaterializedWriteGroup)
            settled, claim, own_state = self._settle_keyed(
                item, concurrency, transaction_instant, shape, audit, advances
            )
            pending.extend(settled.steps)
            count += len(settled.steps)
            units.append(
                ExecutionUnit(
                    end=count,
                    claim=claim,
                    changed=(
                        settled.changed if own_state is None else (*settled.changed, own_state)
                    ),
                    removed=settled.removed,
                    opened=settled.opened,
                )
            )
        flush_pending()
        return WritePlan(steps=PlannedWrites(tuple(segments)), units=tuple(units))

    def _carrier_shape(self, item: OrderedWrite) -> TemporalShape | None:
        """The Temporal Shape of a buffered carrier's target, read once at
        dispatch; ``None`` for a bare instruction, whose settlement reads it."""
        if isinstance(item, ComposedTemporalWrite):
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
            | ReadlessPredicateWrite
            | ObservedKeyedWrite
            | InsertionKeyedWrite
            | TargetKeyedWrite
        ),
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        shape: TemporalShape | None,
        audit: AuditDecoration,
        advances: int = 0,
    ) -> tuple[BoundRange, SourceAuthority | None, VersionedStateKey | None]:
        """One ordered keyed write's settled steps and effects, beside the
        claim its unit spends and the state its carrier itself names as
        changed. ``advances`` is how many versions earlier writes of its scope
        a barrier kept before it advance the row past the state that scope
        names.

        A write spending one retained observation, or several twinned
        observations of one state, changes that state wherever its steps
        change the row it observed."""
        if isinstance(item, ReadlessPredicateWrite):
            return BoundRange(steps=(_readless_step(item.instruction, audit),)), None, None
        own_state: VersionedStateKey | None = None
        observation: WriteObservation | None = None
        claim: SourceAuthority | None = None
        source: ObservedStateKey | None = None
        if isinstance(item, ObservedKeyedWrite):
            instruction, observation = item.instruction, item.observation
            claim = _observed_claim(item)
            source = None if item.claim is None else item.claim.key
        elif isinstance(item, TargetKeyedWrite | InsertionKeyedWrite):
            instruction = item.instruction
            scope = item.scope
            if isinstance(scope, VersionedStateKey):
                own_state = (
                    VersionedStateKey(scope.object, self._advanced(scope.version, advances))
                    if advances
                    else scope
                )
                advances = 0
            if isinstance(item, TargetKeyedWrite):
                claim = _target_claim(item)
                if isinstance(claim, RetainedObservation):
                    source = claim.key
        else:
            instruction = item
        settled = self._settle(
            instruction,
            observation,
            concurrency,
            tx_instant,
            shape,
            audit,
            source=source,
            own_version=None if own_state is None else own_state.version,
            conditioned=isinstance(item, TargetKeyedWrite),
            advances=advances,
        )
        return settled, claim, own_state

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
        source: ObservedStateKey | None = None,
        own_version: int | None = None,
        conditioned: bool = False,
        advances: int = 0,
    ) -> BoundRange:
        """One ordered write's steps and effects. ``source`` is the observed
        state the write's claim names, which it changes wherever it changes the
        row it observed. ``own_version`` is the version a write
        advances from in place of an observed one: the version this attempt's
        own writes left a row it inserted at, or the version a caller's
        condition requires. ``conditioned`` says the gate binds that caller's
        condition, so a shortfall against it is a failed precondition.
        ``advances`` moves an observed version past the writes of its state a
        barrier kept before this one.

        A temporal write reaching here travels with no carrier the range path
        takes: an insert opens a new lineage, and any other closes a milestone
        it holds no observation of, which is refused."""
        entity = instruction.target
        if shape is None:
            shape = self._temporal_facet.shape(entity.identity)
        if isinstance(shape, TransactionTimeOnly | Bitemporal):
            if instruction.mutation not in INSERT_MUTATIONS:
                raise _unobserved_close(entity, instruction.mutation)
            return self._settle_temporal_insert(
                entity, shape, instruction, tx_instant, source, audit
            )
        facts = self._non_temporal_facts(entity)
        changed = _changes(source)
        if instruction.mutation == "insert":
            return BoundRange(
                steps=(self._settle_insert(facts, instruction, audit),), changed=changed
            )
        addressed = self._addressed_facts(facts, concurrency, conditioned=conditioned)
        observed_version = (
            own_version
            if own_version is not None
            else self._observed_version(entity, instruction, facts.version_attribute, observation)
        )
        if advances and observed_version is not None:
            observed_version = self._advanced(observed_version, advances)
        return BoundRange(
            steps=(
                _decorated(
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
                ),
            ),
            changed=changed,
        )

    def _range(
        self,
        item: ComposedTemporalWrite | ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite,
        shape: TransactionTimeOnly | Bitemporal,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        *,
        start: int,
        guards: bool,
    ) -> tuple[tuple[PlannedStep, ...], ExecutionUnit]:
        """``item`` settled as a range over its temporal object's coverage: the
        steps it binds now and the unit they form from ``start``, or no step
        and the unit carrying the deferred range execution binds.

        A lone observed write enters as the carrier it was buffered in, so one
        that lies inside the predecessor it observed binds that predecessor at
        once and one reaching beyond it reads the rest at execution. Its
        observation must be the Temporal Observation every close addresses,
        gates on, and carries state forward from, which is refused before the
        attempt captures its instant.
        """
        entity = item.target if isinstance(item, ComposedTemporalWrite) else item.instruction.target
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
            guards=guards,
        )
        claim = range_claims(item)
        if isinstance(ranged, DeferredTemporalRange):
            return (), ExecutionUnit(end=start, claim=claim, deferred=ranged)
        steps = ranged.steps
        return steps, ExecutionUnit(
            end=start + len(steps),
            claim=claim,
            changed=ranged.changed,
            removed=ranged.removed,
            opened=ranged.opened,
            derived=ranged.derived,
            concludes=ranged.concludes,
        )

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
        which Attribute (if any) carries the optimistic version. An eagerly
        settled instruction and a Materialized Write Group therefore cannot
        answer any of them differently. What only a write against EXISTING rows
        settles belongs to :meth:`_addressed_facts` instead.
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
        source: ObservedStateKey | None,
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
            changed=_changes(source),
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
        start: int,
        guards: bool,
    ) -> tuple[tuple[PlannedStep, ...], ExecutionUnit]:
        """A pending Bitemporal insertion and the writes it authorized since,
        settled as the one unit of new lineages they leave of its window,
        together with any stored coverage a replacement it authorized reaches
        past that window (:func:`~parallax.core.unit_work.ranges.settle_opening`):
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
            guards=guards,
        )
        if isinstance(ranged, DeferredTemporalRange):
            return (), ExecutionUnit(end=start, deferred=ranged)
        steps = ranged.steps
        return steps, ExecutionUnit(
            end=start + len(steps),
            changed=ranged.changed,
            removed=ranged.removed,
            opened=ranged.opened,
            derived=ranged.derived,
        )

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
        :class:`~parallax.core.unit_work.materialized.ObservedKeyedWrite`
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

    def _settle_group(
        self,
        group: MaterializedWriteGroup,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        *,
        guards: bool,
    ) -> NonTemporalGroupSegment | TemporalGroupSegment | DeferredGroupRange:
        """One Materialized Write Group as one already-settled segment, or as
        the deferred range a Bitemporal amendment settles at execution.

        Every group-wide semantic fact — the temporal expansion, the gate and
        concurrency decision, the affected-row policy, the assignment shape,
        and (only when the surviving group needs one) the concrete Transaction
        Instant literal — is decided HERE, once, before this method returns.
        The returned segment carries none of the group, the concurrency mode,
        the Transaction Instant, or a strategy object: its ``step`` rebuilds
        one row's Planned Write from these already-decided facts and the
        group's own compact evidence alone.

        A Bitemporal amendment selected each object by the row current at its
        ``valid_from`` and reaches the object's later coverage too, which no
        planning input holds: each object settles at execution as a range from
        that row (:func:`~parallax.core.unit_work.ranges.defer_group`), whose
        unchanged milestones ``guards`` lets an Optimistic guard prove.
        """
        entity = group.mutation.selection.target
        shape = self._temporal_facet.shape(entity.identity)
        if isinstance(shape, Bitemporal) and group.mutation.mutation in AMEND_MUTATIONS:
            return defer_group(
                group,
                view=entity_view(self._families, entity),
                shape=shape,
                gated=self._concurrency.gates(concurrency, self._model, entity.identity),
                # Reaching a surviving temporal group is what makes the attempt
                # capture its instant, once for every object it selected.
                instant=tx_instant.value(),
                guards=guards,
            )
        if isinstance(shape, TransactionTimeOnly | Bitemporal):
            return self._settle_temporal_group(
                group, entity, shape, concurrency, tx_instant, ownership, audit
            )
        return self._settle_versioned_group(group, entity, concurrency, audit)

    def _settle_versioned_group(
        self,
        group: MaterializedWriteGroup,
        entity: EntityMetadata,
        concurrency: Concurrency,
        audit: AuditDecoration,
    ) -> NonTemporalGroupSegment:
        """A versioned (non-temporal) Materialized Write Group's segment.

        The group's facts are settled through the same
        :meth:`_non_temporal_facts` and :meth:`_addressed_facts` an eagerly
        settled keyed write crosses, and the segment holds them by reference.
        Every row shares the SAME gate/ungated decision and the SAME assignment
        overlay (`m-batch-write`'s set-based semantics extended to the
        materializing case); only the observed version differs per row, which is
        why it alone stays a per-row column — and it stays the group's OWN
        column, advanced at step access through the arithmetic the update's
        emission carries rather than copied into a second one.

        A group's evidence is not optional, so an entity this
        group's own Concurrency Strategy does not recognize as versioned is
        refused here rather than settled Unversioned with its evidence dropped —
        the same entitlement rule an ordinary keyed write meets in
        :meth:`_observed_version`.
        """
        evidence = group.evidence
        assert isinstance(evidence, VersionedEvidence)
        facts = self._non_temporal_facts(entity)
        addressed = self._addressed_facts(facts, concurrency)
        mutation = group.mutation.mutation
        if facts.version_attribute is None:
            _require_unobserved(entity, mutation, evidence)
        emission: NonTemporalEmission = DELETION
        if mutation != "delete":
            if facts.version_attribute is not None and any(
                isinstance(assignment.member, AttributeMetadata)
                and assignment.member.identity == facts.version_attribute
                for assignment in group.mutation.managed_assignments
            ):
                self._concurrency.reject_authored_version(entity.identity, facts.version_attribute)
            emission = Revision(
                prepared_assignments(entity, group.mutation.managed_assignments),
                self._version_overlay(facts.version_attribute),
            )
        segment = NonTemporalGroupSegment(
            facts=facts,
            addressed=addressed,
            key_name=addressed.key_attributes[0].name,
            keys=evidence.keys,
            versions=evidence.versions,
            emission=emission,
            # One resolved row is one independently gated step, so every row of
            # the group shares this one expectation rather than building its own.
            affected_rows=ExactCount(expected=1, on_shortfall=addressed.shortfall),
            changed=GroupStates(
                entity.identity, facts.view.primary_key.identity.name, evidence, NON_TEMPORAL
            ),
        )
        if audit.neutral or not isinstance(emission, Revision):
            return segment
        return segment.audited_by(audit)

    def _settle_temporal_group(
        self,
        group: MaterializedWriteGroup,
        entity: EntityMetadata,
        shape: TransactionTimeOnly | Bitemporal,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
    ) -> TemporalGroupSegment:
        """A temporal Materialized Write Group's segment.

        The group's one mutation is one transform over every selected row,
        settled through the same :class:`PredecessorExpander` a range expands
        its originals through — the only clock consultation this group's whole
        flush makes, however many rows it resolved — which decides each row's
        disposition before the segment exists
        (:meth:`~parallax.core.temporal_write.expansion.PredecessorExpander.settle_group`).
        The segment then builds each step from the settled backing and the
        group's own evidence alone, and neither consults the attempt's
        ownership again.
        """
        evidence = group.evidence
        assert isinstance(evidence, PredecessorRows)
        mutation = group.mutation
        view = entity_view(self._families, entity)
        transform = NO_TRANSFORM.followed_by(
            mutation.valid_time_window,
            (
                {
                    assigned_name(assignment): assignment.value
                    for assignment in mutation.managed_assignments
                }
                if mutation.mutation in AMEND_MUTATIONS
                else None
            ),
            replaces=False,
        )
        expansion = PredecessorExpander(
            # Reaching a surviving temporal group is what makes the attempt
            # capture its instant, once for every row it resolved.
            TemporalFacts(entity=entity, view=view, shape=shape, instant=tx_instant.value()),
            transform,
            key_attribute=view.primary_key.identity,
            gated=self._concurrency.gates(concurrency, self._model, entity.identity),
            ownership=ownership,
            audit=audit,
        )
        return TemporalGroupSegment(
            expansion.settle_group(evidence, mutation.managed_assignments), evidence
        )


def _unobserved_close(entity: EntityMetadata, mutation: str) -> WritePlanningError:
    return WritePlanningError(
        f"{entity.identity.name!r}: a temporal {mutation!r} closes the "
        "current milestone, and every close requires the Temporal Observation it "
        "addresses, gates on, and carries state forward from (m-unit-work; m-opt-lock)"
    )


def _observed_claim(item: ObservedKeyedWrite) -> SourceAuthority | None:
    """What an observed keyed write's unit spends: its claim, together with
    every twinned observation of the same state."""
    if not item.twins:
        return item.claim
    assert item.claim is not None  # twins meet only at their claim's own scope
    return CombinedSourceAuthority((item.claim, *item.twins))


def _target_claim(item: TargetKeyedWrite) -> SourceAuthority | None:
    """What a caller-conditioned write's unit spends: the observations of the
    observed writes composed into it, if any."""
    claims = item.claims
    if not claims:
        return None
    return claims[0] if len(claims) == 1 else CombinedSourceAuthority(claims)


def _changes(source: ObservedStateKey | None) -> tuple[ObservedStateKey, ...]:
    return () if source is None else (source,)


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

    A Materialized Write Group has no counterpart to this: its assignments are
    the authored predicate write's own, uniform across every resolved row and
    carrying no key members to project out.
    """
    key_names = frozenset(attribute.name for attribute in addressed.key_attributes)
    return planned_assignments(
        facts.entity,
        facts.view,
        {name: value for name, value in row.items() if name not in key_names},
    )


def _readless_step(instruction: PreparedPredicateWrite, audit: AuditDecoration) -> PlannedStep:
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
            assignments=prepared_assignments(entity, instruction.managed_assignments),
            concurrency=UNVERSIONED,
            affected_rows=ANY_COUNT,
        )
    )


def _decorated(audit: AuditDecoration, step: PlannedStep) -> PlannedStep:
    """An addressed Non-Temporal step as audit leaves it: an update decorated
    once, a delete as it is."""
    return audit.decorate_update(step) if isinstance(step, PlannedUpdate) else step


def _require_unobserved(entity: EntityMetadata, mutation: str, observation: object | None) -> None:
    """Refuse ``observation`` when the target it arrived for is entitled to none.

    Reached only once the caller has established that the target is neither
    temporal nor versioned, which is the one shape `m-unit-work` declares
    observationless ("unversioned Non-Temporal writes have no observation",
    absence structural). Whether a write may hold evidence at all needs the
    model, so the buffered carriers — a keyed
    :class:`~parallax.core.unit_work.materialized.ObservedKeyedWrite` and a
    :class:`~parallax.core.unit_work.materialized.MaterializedWriteGroup`'s
    evidence — can only refuse the instruction-local half and
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
