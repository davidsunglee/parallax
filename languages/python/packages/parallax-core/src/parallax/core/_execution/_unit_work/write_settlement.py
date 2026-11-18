from __future__ import annotations

from collections.abc import Container, Sequence
from typing import Final

from parallax.core._execution._unit_work._errors import VERSION_UNOBSERVED
from parallax.core._execution._unit_work.acquisition_spans import AcquisitionSpan, form_spans
from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedInstruction,
)
from parallax.core._execution._unit_work.non_temporal_settlement import (
    DELETION,
    AddressedFacts,
    NonTemporalFacts,
    Revision,
    non_temporal_step,
)
from parallax.core._execution._unit_work.ranges import (
    DeferredRange,
    settle_opening,
    settle_range,
)
from parallax.core._execution._unit_work.row_acquisition import CoverageReadKey
from parallax.core._execution._unit_work.strategy import (
    ActorIdentity,
    AuditDecoration,
    AuditStrategy,
)
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    InsertBatch,
    InsertionAuthorized,
    KeyedInsert,
    LicensedWrite,
    MutationPhase,
    OrderedWrite,
    StateObserved,
    TemporalCoverageWrite,
    TxStartConditioned,
    UnversionedWriteBatch,
    VersionConditioned,
    WriteAuthority,
    is_licensed_by,
)
from parallax.core._execution._unit_work.write_plan import (
    SettledWrite,
    WriteGroup,
    WritePlan,
)
from parallax.core.internal.base import InternalError, UsageError
from parallax.core.internal.concurrency import (
    INITIAL_VERSION,
    ConcurrencyFacet,
    ConcurrencyPreference,
)
from parallax.core.internal.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    CompiledEntity,
    EntityIdentity,
    Metamodel,
)
from parallax.core.internal.planned_step.keys import (
    ObjectKey,
    VersionedObjectStateKey,
)
from parallax.core.internal.planned_step.managed_row import ManagedRow
from parallax.core.internal.planned_step.observe import (
    StateObservation,
    TemporalObservation,
    VersionObservation,
)
from parallax.core.internal.planned_step.payload import WritePayloadPreparer
from parallax.core.internal.planned_step.planned_rows import (
    WRITE_PLANNING_FAILED,
    entity_view,
    planned_assignments,
    planned_row,
)
from parallax.core.internal.planned_step.steps import (
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    ExactCount,
    PlannedAssignments,
    PlannedInsert,
    PlannedStep,
    PlannedUpdate,
    WriteRow,
    shortfall_classification,
)
from parallax.core.internal.planned_step.write_effects import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    EffectShapeOf,
    Openings,
    TemporalWriteOwnership,
)
from parallax.core.internal.temporal_read import (
    Bitemporal,
    TemporalFacet,
    TemporalShape,
    TransactionTimeOnly,
)
from parallax.core.internal.temporal_write.expansion import (
    TemporalFacts,
    opening,
    openings,
)

__all__ = ["WritePlanCompiler", "require_observed_version"]


_WRITES_PER_GROUP: Final = 1024
"""The most settled writes one Write Group holds. In a group of updates or
deletes every insert waits behind every non-insert step of the group, so this
bounds how many settled writes' non-insert steps a failing insert wastes,
whatever the flush's size; a batch counts once however many rows it covers. It
is not the executor's per-call statement or row cap. Each effect shape of a
group is one statement, so a group this large applies a thousand like
amendments as one statement where a smaller one would cut them into several."""

type _GroupKey = tuple[AttributeIdentity, object]
"""One object a settled write writes: its family's primary-key Attribute and the
value it holds, so two Entities of one Inheritance Family sharing a key value
name one object and two unrelated Entities never do."""

type _ReadKeys = dict[tuple[EntityIdentity, bool], CoverageReadKey]
"""The read key of each Entity and lock decision one compilation settled a
range of, so the ranges reading alike share one instance."""


class WritePlanCompiler:
    """The Write Planner's own compiler of mutation phases into a Write Plan
    (`m-unit-work`): it interprets each write's concurrency and its ordinary
    or temporal semantics and audit, and assembles its steps, Write Groups,
    claims, and proposed effects.

    Constructed once per accepted Metamodel by the planner that owns it, with
    that model, the Inheritance, Temporal, and Concurrency facets it read, the
    audit strategy the composition layer wired, and the
    model's write payload preparer, which judges whether produced temporal
    rows merge.
    :meth:`compile` is its entire surface: no caller settles one item, packs a
    segment, audits a row or step, or collects a claim by hand.
    """

    __slots__ = (
        "_audit",
        "_families",
        "_model",
        "_payloads",
        "_settled",
        "_temporal_facet",
        "_versioning",
    )

    def __init__(
        self,
        model: Metamodel,
        families: InheritanceFacet,
        temporal_facet: TemporalFacet,
        versioning: ConcurrencyFacet,
        *,
        audit: AuditStrategy,
        settled: Container[object],
        payloads: WritePayloadPreparer,
    ) -> None:
        self._model = model
        self._families = families
        self._temporal_facet = temporal_facet
        self._versioning = versioning
        self._audit = audit
        self._settled = settled
        self._payloads = payloads

    def compile(
        self,
        phases: Sequence[MutationPhase],
        *,
        preference: ConcurrencyPreference,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
        ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
        counts_unchanged_rows: bool = False,
    ) -> WritePlan:
        """Every mutation phase, in flush order, as one Write Plan.

        Each settled write carries the exact Read Evidence of every source it
        settled. An item retired before settlement — folded into a
        pending insert, cancelled against one, or eliminated as a known no-op —
        never reaches this loop, and therefore no settled write carries the
        evidence it was holding.

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
        most :data:`_WRITES_PER_GROUP`, laid out as every write's effects, shape by
        shape where the model's payload preparer gives them shapes, and then
        every write's inserts, each write's own order kept. A write naming an
        object the open group already writes starts the next group. A deferred
        write is grouped only once execution binds it: each unbroken run of
        deferred writes within a mutation phase forms acquisition spans
        (:func:`~parallax.core._execution._unit_work.acquisition_spans.form_spans`),
        whose coverage is read together and whose leading writes with ready
        coverage execute as one group. ``ownership`` answers which current rows
        this attempt already opened, so a write against one of them revises or
        removes that row instead of closing it into history.

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
        turns: list[WriteGroup | AcquisitionSpan] = []
        read_keys: _ReadKeys = {}
        audit = AuditDecoration(self._audit, actor_identity, transaction_instant, self._settled)
        families = self._families
        shape = self._payloads.effect_shape
        for phase in phases:
            members: list[tuple[SettledWrite, tuple[PlannedStep, ...]]] = []
            held: set[_GroupKey] = set()
            deferred: list[DeferredRange] = []
            for item in phase:
                settled = self._settled_write(
                    item,
                    preference,
                    transaction_instant,
                    ownership,
                    audit,
                    counts_unchanged_rows,
                    read_keys,
                )
                if isinstance(settled, DeferredRange):
                    _close_group(turns, members, held, shape)
                    deferred.append(settled)
                    continue
                _close_run(turns, deferred)
                write, steps = settled
                keys = _group_keys(item, families)
                if len(members) == _WRITES_PER_GROUP or not held.isdisjoint(keys):
                    _close_group(turns, members, held, shape)
                members.append((write, steps))
                held.update(keys)
            _close_run(turns, deferred)
            _close_group(turns, members, held, shape)
        return WritePlan(tuple(turns))

    def _settled_write(
        self,
        item: OrderedWrite,
        preference: ConcurrencyPreference,
        transaction_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        guards: bool,
        read_keys: _ReadKeys,
    ) -> tuple[SettledWrite, tuple[PlannedStep, ...]] | DeferredRange:
        shape = self._temporal_facet.shape(item.target.identity)
        if isinstance(item, ComposedBitemporalOpening):
            assert isinstance(shape, Bitemporal)  # only a Bitemporal opening is composed
            return self._opening(
                item,
                shape,
                preference,
                transaction_instant,
                ownership,
                audit,
                read_keys,
                guards=guards,
            )
        if (
            isinstance(item, ComposedTemporalWrite)
            or is_licensed_by(item, StateObserved)
            or is_licensed_by(item, InsertionAuthorized)
            or is_licensed_by(item, TxStartConditioned)
        ) and isinstance(shape, TransactionTimeOnly | Bitemporal):
            return self._range(
                item,
                shape,
                preference,
                transaction_instant,
                ownership,
                audit,
                read_keys,
                guards=guards,
            )
        assert not isinstance(item, ComposedTemporalWrite)  # only temporal objects compose
        settled = self._settle_keyed(item, preference, transaction_instant, shape, audit)
        write = SettledWrite(
            source_evidence=item.source_evidence,
            changed=settled.changed,
            advanced=settled.advanced,
            destroyed=settled.destroyed,
            removed=settled.removed,
            opened=settled.opened,
        )
        return write, settled.steps

    def _settle_keyed(
        self,
        item: KeyedInsert | LicensedWrite[WriteAuthority] | InsertBatch | UnversionedWriteBatch,
        preference: ConcurrencyPreference,
        tx_instant: TransactionInstant,
        shape: TemporalShape | None,
        audit: AuditDecoration,
    ) -> BoundRange:
        """One ordered keyed write's settled steps and completion: an insert
        opens a new lineage, and any other write revises or deletes existing
        Non-Temporal rows."""
        instruction = item.instruction
        entity = instruction.target
        if isinstance(item, KeyedInsert | InsertBatch):
            if isinstance(shape, TransactionTimeOnly | Bitemporal):
                return self._settle_temporal_insert(entity, shape, instruction, tx_instant, audit)
            facts = self._non_temporal_facts(entity)
            return BoundRange(steps=(self._settle_insert(facts, instruction, audit),))
        # Every temporal write of existing state settles as a range, and only
        # an unversioned Non-Temporal row is locked by its object.
        assert not isinstance(shape, TransactionTimeOnly | Bitemporal)
        if isinstance(item, UnversionedWriteBatch):
            return self._settle(instruction, item.object_keys, None, preference, audit)
        scope = item.claim_scope
        authority = item.authority
        return self._settle(
            instruction,
            (item.object_key,),
            authority.retained_observation.evidence
            if isinstance(authority, StateObserved)
            else None,
            preference,
            audit,
            own_version=scope.version if isinstance(scope, VersionedObjectStateKey) else None,
            conditioned=isinstance(authority, VersionConditioned),
        )

    def _settle(
        self,
        instruction: PreparedKeyedInstruction,
        objects: tuple[ObjectKey, ...],
        observation: StateObservation | None,
        preference: ConcurrencyPreference,
        audit: AuditDecoration,
        *,
        own_version: int | None = None,
        conditioned: bool = False,
    ) -> BoundRange:
        """One ordered Non-Temporal write of existing ``objects``, one per row:
        its steps and completion. ``own_version`` is the
        version a write advances from in place of the one its ``observation``
        names: the protected state its source's authority reaches, the version
        this attempt's own writes left a row it inserted at, or the version a
        caller's condition requires. ``conditioned`` says the gate binds that
        caller's condition, so a shortfall against it is a failed precondition.

        A versioned update advances the state it starts from and a deletion
        destroys every object it addresses; an unversioned write changes each
        object it addresses without advancing anything."""
        entity = instruction.target
        facts = self._non_temporal_facts(entity)
        addressed = self._addressed_facts(facts, preference, conditioned=conditioned)
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
                        facts.version_attribute,
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
        item: TemporalCoverageWrite,
        shape: TransactionTimeOnly | Bitemporal,
        preference: ConcurrencyPreference,
        tx_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        read_keys: _ReadKeys,
        *,
        guards: bool,
    ) -> tuple[SettledWrite, tuple[PlannedStep, ...]] | DeferredRange:
        """``item`` settled as a range over its temporal object's coverage: the
        settled write with the steps it binds now, or the deferred range
        execution binds.

        A range, one write alone or a composition, observed inside the
        predecessors it holds binds them at once, and one reaching beyond them
        reads the rest at execution. Every observation it holds must be the
        Temporal Observation every close addresses, gates on, and carries
        state forward from, which is refused before the attempt captures its
        instant.
        """
        entity = item.target
        intents = item.intents
        if any(
            is_licensed_by(intent, StateObserved)
            and not isinstance(intent.authority.retained_observation.evidence, TemporalObservation)
            for intent in intents
        ):
            raise _unobserved_close(entity)
        view = entity_view(self._families, entity)
        ranged = settle_range(
            item,
            intents,
            view=view,
            shape=shape,
            read_key=_read_key(read_keys, entity, view, gated=self._gates(entity, preference)),
            # Reaching a surviving temporal write is what makes the attempt
            # capture its instant.
            instant=tx_instant.value(),
            ownership=ownership,
            audit=audit,
            payloads=self._payloads,
            guards=guards,
        )
        if isinstance(ranged, DeferredRange):
            return ranged
        write = SettledWrite(
            source_evidence=item.source_evidence,
            changed=ranged.changed,
            removed=ranged.removed,
            opened=ranged.opened,
            derived=ranged.derived,
            current_outputs=ranged.current_outputs,
        )
        return write, ranged.steps

    def _settle_insert(
        self, facts: NonTemporalFacts, instruction: PreparedKeyedInstruction, audit: AuditDecoration
    ) -> PlannedInsert:
        """One keyed insert as its rows, each opening a new lineage.

        An insert observes nothing, gates on nothing, and addresses nothing, so
        the only fact it takes from the mutation beyond its target is the
        version a new lineage opens at — and an unversioned target opens at no
        version, so it asks the strategy for no arithmetic either.
        """
        version = (
            None if facts.version_attribute is None else (facts.version_attribute, INITIAL_VERSION)
        )
        entries = tuple(
            audit.finalize_row(WriteRow(row=planned_row(row, version), origin=NEW_LINEAGE))
            for row in instruction.rows
        )
        return PlannedInsert(entity=facts.entity.identity, entries=entries)

    def _non_temporal_facts(self, entity: CompiledEntity) -> NonTemporalFacts:
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
            version_attribute=self._versioning.version_attribute(entity.identity),
        )

    def _addressed_facts(
        self,
        facts: NonTemporalFacts,
        preference: ConcurrencyPreference,
        *,
        conditioned: bool = False,
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
        gated = self._gates(facts.entity, preference)
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

    def _settle_temporal_insert(
        self,
        entity: CompiledEntity,
        shape: TransactionTimeOnly | Bitemporal,
        instruction: PreparedKeyedInstruction,
        tx_instant: TransactionInstant,
        audit: AuditDecoration,
    ) -> BoundRange:
        """One temporal insert as the new lineage it opens over its prepared
        window, the row recorded under the key it states."""
        view = entity_view(self._families, entity)
        # Reaching a surviving temporal insert is what makes the attempt
        # capture its instant; the row's fresh start derives from that value.
        (row,) = instruction.rows
        facts = TemporalFacts(
            entity=entity,
            view=view,
            shape=shape,
            instant=tx_instant.value(),
            selection=row.selection,
        )
        inserts = (
            PlannedInsert(
                entity=entity.identity,
                entries=(audit.finalize_row(opening(facts, row, instruction.valid_time_window)),),
            ),
        )
        return BoundRange(
            steps=inserts,
            opened=Openings(continued=openings(facts, inserts)),
        )

    def _opening(
        self,
        opening: ComposedBitemporalOpening,
        shape: Bitemporal,
        preference: ConcurrencyPreference,
        tx_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        read_keys: _ReadKeys,
        *,
        guards: bool,
    ) -> tuple[SettledWrite, tuple[PlannedStep, ...]] | DeferredRange:
        """A pending Bitemporal insertion and the writes it authorized since,
        settled as the one settled write of new lineages they leave of its window,
        together with any stored coverage a replacement it authorized reaches
        past that window (:func:`~parallax.core._execution._unit_work.ranges.settle_opening`):
        bound now, or deferred until execution reads that coverage."""
        entity = opening.target
        view = entity_view(self._families, entity)
        ranged = settle_opening(
            opening,
            view=view,
            shape=shape,
            read_key=_read_key(
                read_keys,
                entity,
                view,
                # Only a replacement reaching past the opening reaches stored
                # rows, whose closes the strategy gates.
                gated=opening.beyond is not None and self._gates(entity, preference),
            ),
            # Reaching a surviving temporal insert is what makes the attempt
            # capture its instant; every part's fresh start derives from that value.
            instant=tx_instant.value(),
            ownership=ownership,
            audit=audit,
            payloads=self._payloads,
            guards=guards,
        )
        if isinstance(ranged, DeferredRange):
            return ranged
        write = SettledWrite(
            source_evidence=opening.source_evidence,
            changed=ranged.changed,
            removed=ranged.removed,
            opened=ranged.opened,
            derived=ranged.derived,
            current_outputs=ranged.current_outputs,
        )
        return write, ranged.steps

    def _gates(self, entity: CompiledEntity, preference: ConcurrencyPreference) -> bool:
        """Whether a write of ``entity`` against existing rows gates: exactly
        when its Effective Concurrency Strategy is Optimistic."""
        return self._versioning.effective_strategy(entity.identity, preference) == "optimistic"

    def _observed_version(
        self,
        entity: CompiledEntity,
        instruction: PreparedKeyedInstruction,
        version_attr: AttributeIdentity | None,
        observation: StateObservation | None,
    ) -> int | None:
        """The version an addressed write against a versioned row advances
        from, or ``None`` for an unversioned target.

        The observation is required under both strategies, because the
        framework never issues a resolving read on behalf of a keyed write.

        A returned version therefore came off an observed write, which
        wraps exactly one row — so the Key Target the caller builds from
        ``instruction.rows`` is a singleton whenever this returns a version to
        advance from or gate on (`m-unit-work`: a Version Gate requires a
        singleton Key Target). The alternative — one row's observed version
        licensing every key a merged statement addresses — is unconstructable
        rather than merely unreached.

        An unversioned target has no version to advance from AND is entitled to
        no observation at all, so an observation arriving for one is refused
        rather than dropped: this is the model-aware half of the rule
        :class:`~parallax.core._execution._unit_work.write_items.StateObserved`
        delegates here, and discarding the evidence instead would be the
        silently-unobserved mode `m-unit-work` forbids.
        """
        if version_attr is None:
            _require_unobserved(entity, instruction.mutation, observation)
            return None
        return require_observed_version(entity.identity, observation)


def _group_keys(item: OrderedWrite, families: InheritanceFacet) -> tuple[_GroupKey, ...]:
    """The objects ``item`` writes, by its family's key."""
    objects = (
        item.object_keys
        if isinstance(item, InsertBatch | UnversionedWriteBatch)
        else (item.object_key,)
    )
    attribute = entity_view(families, item.target).primary_key.identity
    keys: list[_GroupKey] = []
    for key in objects:
        ((_, value),) = key.primary_key
        keys.append((attribute, value))
    return tuple(keys)


def _read_key(
    read_keys: _ReadKeys, entity: CompiledEntity, view: InheritanceEntityView, *, gated: bool
) -> CoverageReadKey:
    """The read key of ``entity``'s ranges, whose writes gate where ``gated``
    and whose coverage reads otherwise take the shared row lock: the one
    ``read_keys`` holds, or a new one it then holds."""
    shared_lock = not gated
    held = read_keys.get((entity.identity, shared_lock))
    if held is None:
        held = read_keys[entity.identity, shared_lock] = CoverageReadKey(
            entity, view.primary_key.identity, shared_lock
        )
    return held


def _close_run(turns: list[WriteGroup | AcquisitionSpan], deferred: list[DeferredRange]) -> None:
    """End the unbroken run of ``deferred`` writes: its acquisition spans are
    the plan's next turns."""
    if deferred:
        turns.extend(form_spans(deferred))
        deferred.clear()


def _close_group(
    turns: list[WriteGroup | AcquisitionSpan],
    members: list[tuple[SettledWrite, tuple[PlannedStep, ...]]],
    held: set[_GroupKey],
    effect_shape: EffectShapeOf,
) -> None:
    if members:
        turns.append(WriteGroup.from_members(members, effect_shape=effect_shape))
    members.clear()
    held.clear()


def _unobserved_close(entity: CompiledEntity) -> InternalError:
    return InternalError(
        WRITE_PLANNING_FAILED,
        f"{entity.identity.name!r}: a temporal write of existing coverage closes the "
        "current milestone, and every close requires the Temporal Observation it "
        "addresses, gates on, and carries state forward from (m-unit-work)",
    )


def _addressed_assignments(
    facts: NonTemporalFacts, addressed: AddressedFacts, row: ManagedRow
) -> PlannedAssignments:
    """The replacement values an addressed update writes, before its version
    overlay.

    Key members address the write rather than change it, so they never appear
    among the assignments. A multi-row update reaching here is one the batching
    strategy collapsed, and it collapses only a run assigning identical values to
    every key (`m-batch-write` keeps incompatible writes in separate steps), so
    the first row settles the whole step's assignments. Every admitted write
    is single-row, so no multi-row update arrives here any other way.
    """
    index = row.selection.members.index
    keys = 0
    for attribute in addressed.key_attributes:
        keys |= 1 << index[attribute]
    return planned_assignments(row, without=keys)


def _decorated(audit: AuditDecoration, step: PlannedStep) -> PlannedStep:
    """An addressed Non-Temporal step as audit leaves it: an update decorated
    once, a delete as it is."""
    return audit.decorate_update(step) if isinstance(step, PlannedUpdate) else step


def require_observed_version(entity: EntityIdentity, observation: StateObservation | None) -> int:
    """The version a keyed update or delete of an explicitly versioned row of
    ``entity`` advances from; refused with :data:`VERSION_UNOBSERVED` where the
    write reached settlement observing none."""
    if not isinstance(observation, VersionObservation):
        raise UsageError(
            VERSION_UNOBSERVED,
            f"{entity.name}: a keyed update/delete of a versioned row requires the version its "
            "source observed (a prior find) — the framework never issues an implicit "
            "resolving read on behalf of a keyed write",
        )
    return observation.observed_version


def _require_unobserved(
    entity: CompiledEntity, mutation: str, observation: StateObservation | None
) -> None:
    """Refuse ``observation`` when the target it arrived for is entitled to none.

    Reached only once the caller has established that the target is neither
    temporal nor versioned, which is the one shape `m-unit-work` declares
    observationless ("unversioned Non-Temporal writes have no observation",
    absence structural). Whether a write may hold evidence at all needs the
    model, so the admitted write, a keyed
    :class:`~parallax.core._execution._unit_work.write_items.StateObserved`
    write, can only refuse the instruction-local half and
    delegate this half to the model-aware settlement. This is that delegation:
    every write that IS settled crosses it, whatever produced it, so a
    producer that resolves evidence a target cannot carry is told rather than
    quietly stripped.

    Settled is the whole reach of that guarantee. Coalescing and no-op
    elimination run first, and a write they retire — folded into a pending
    insert, cancelled against one, or eliminated as a key-only no-op — is never
    settled at all. Nothing is
    stripped there either: the write itself is gone, so its observation gates,
    advances, and attributes nothing.
    """
    if observation is None:
        return
    raise InternalError(
        WRITE_PLANNING_FAILED,
        f"{entity.identity.name!r}: an unversioned Non-Temporal {mutation!r} carries no Write "
        "Observation, yet one was resolved for it — absence is structural (m-unit-work "
        "'unversioned Non-Temporal writes have no observation'), and settling this write "
        "would discard the evidence rather than gate or advance anything with it",
    )
