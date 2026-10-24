from __future__ import annotations

from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core._execution._unit_work.instructions import (
    ASSIGNMENT_MUTATIONS,
    PreparedKeyedInstruction,
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
    settle_opening,
    settle_range,
)
from parallax.core._execution._unit_work.strategy import (
    ActorIdentity,
    AuditDecoration,
    AuditStrategy,
    Concurrency,
    ConcurrencyStrategy,
)
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    InsertBatch,
    InsertionAuthorizedWrite,
    KeyedInsert,
    MutationPhase,
    ObjectLockedBatch,
    ObjectLockedWrite,
    OrderedWrite,
    StateObservedIntent,
    StateObservedWrite,
    TargetWrite,
    TemporalCoverageWrite,
)
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, EntityMetadata, Metamodel
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
    VersionedObjectStateKey,
)
from parallax.core.write_plan.observe import StateObservation, TemporalObservation
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    AcquisitionSpan,
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
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    RETURNED_MAX_PLUS_ONE,
    ExactCount,
    MaxPlusOne,
    PlannedAssignments,
    PlannedInsert,
    PlannedStep,
    PlannedUpdate,
    PlannedValue,
    WriteRow,
    shortfall_classification,
)

__all__ = ["WritePlanCompiler"]


_GROUP_WRITES: Final = 64
"""The most settled writes one Write Group holds. In a group of updates or
deletes every insert waits behind every non-insert step of the group, so this
bounds how many settled writes' non-insert steps a failing insert wastes,
whatever the flush's size; a batch counts once however many rows it covers. It
is not the executor's per-call statement or row cap."""

type _GroupKey = tuple[AttributeIdentity, object]
"""One object a settled write writes: its family's primary-key Attribute and the
value it holds, so two Entities of one Inheritance Family sharing a key value
name one object and two unrelated Entities never do."""

_ACQUISITION_RANGES: Final = 32
"""The most deferred settled writes one acquisition span holds (`m-unit-work`
*Shared coverage acquisition*): how many objects' coverage can be read ahead of
their writes' turns. It bounds objects, not the parts or rows their reads
return. The ready writes of a span execute as one Write Group, so it is never
more than :data:`_GROUP_WRITES`."""


@dataclass(frozen=True, slots=True)
class _AcquisitionCandidate:
    """What a deferred settled write of a Bitemporal object shares a coverage
    read by: the concrete Entity and key Attribute it reads, whether the read
    takes the shared lock, and the object it writes."""

    entity: EntityIdentity
    key_attribute: AttributeIdentity
    locking: bool
    key: _GroupKey


@dataclass(slots=True)
class _AcquisitionRun:
    """The acquisition span settlement is extending: its plan entries
    ``[start, stop)``, the read its first write shares, and every object its writes
    write."""

    start: int
    stop: int
    first: _AcquisitionCandidate
    keys: set[_GroupKey]


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
        settled. An item the planner's earlier stages retired — folded into a
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
        most :data:`_GROUP_WRITES`, laid out as every write's non-insert steps
        and then every write's inserts, each write's own order kept. A write
        whose insert the database allocates a key for and a write naming no
        complete object key form a group of their own, and a write naming an
        object the open group already writes starts the next group. A deferred
        write is a plan entry of its own, grouped only once execution binds it.
        Consecutive deferred writes of one mutation phase sharing a coverage
        read and writing distinct objects, at most :data:`_ACQUISITION_RANGES`
        of them, are recorded as one acquisition span: their coverage is read
        together, and the leading ones whose coverage is ready execute as one
        group. ``ownership`` answers which current rows
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
        entries: list[WriteGroup | SettledWrite] = []
        spans: list[AcquisitionSpan] = []
        audit = AuditDecoration(self._audit, actor_identity, transaction_instant, self._settled)
        families = self._families
        for phase in phases:
            members: list[tuple[SettledWrite, tuple[PlannedStep, ...]]] = []
            held: set[_GroupKey] = set()
            run: _AcquisitionRun | None = None
            for item in phase:
                write, steps = self._settled_write(
                    item, concurrency, transaction_instant, ownership, audit, counts_unchanged_rows
                )
                if write.deferred is not None:
                    _close_group(entries, members, held)
                    run = _extend_run(
                        spans, run, len(entries), _acquisition_candidate(write, item, families)
                    )
                    entries.append(write)
                    continue
                keys = None if write.opened.allocated else _group_keys(item, families)
                if keys is None:
                    _close_group(entries, members, held)
                    entries.append(WriteGroup((write,), steps))
                    continue
                if len(members) == _GROUP_WRITES or not held.isdisjoint(keys):
                    _close_group(entries, members, held)
                members.append((write, steps))
                held.update(keys)
            _close_group(entries, members, held)
            _close_run(spans, run)
        return WritePlan(tuple(entries), tuple(spans))

    def _settled_write(
        self,
        item: OrderedWrite,
        concurrency: Concurrency,
        transaction_instant: TransactionInstant,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        guards: bool,
    ) -> tuple[SettledWrite, tuple[PlannedStep, ...]]:
        shape = self._temporal_facet.shape(item.target.identity)
        if isinstance(item, ComposedBitemporalOpening):
            assert isinstance(shape, Bitemporal)  # only a Bitemporal opening is composed
            return self._opening(
                item, shape, concurrency, transaction_instant, ownership, audit, guards=guards
            )
        if isinstance(
            item,
            ComposedTemporalWrite | StateObservedWrite | InsertionAuthorizedWrite | TargetWrite,
        ) and isinstance(shape, TransactionTimeOnly | Bitemporal):
            return self._range(
                item, shape, concurrency, transaction_instant, ownership, audit, guards=guards
            )
        assert not isinstance(item, ComposedTemporalWrite)  # only temporal objects compose
        settled = self._settle_keyed(item, concurrency, transaction_instant, shape, audit)
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
        item: (
            KeyedInsert
            | InsertBatch
            | StateObservedWrite
            | ObjectLockedWrite
            | ObjectLockedBatch
            | InsertionAuthorizedWrite
            | TargetWrite
        ),
        concurrency: Concurrency,
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
        if isinstance(item, ObjectLockedBatch):
            return self._settle(instruction, item.object_keys, None, concurrency, audit)
        scope = item.claim_scope
        return self._settle(
            instruction,
            (item.object_key,),
            item.observation if isinstance(item, StateObservedWrite) else None,
            concurrency,
            audit,
            own_version=scope.version if isinstance(scope, VersionedObjectStateKey) else None,
            conditioned=isinstance(item, TargetWrite),
        )

    # Stages 5, 6, 7: validate the observation the item arrived carrying, #

    def _settle(
        self,
        instruction: PreparedKeyedInstruction,
        objects: tuple[ObjectKey, ...],
        observation: StateObservation | None,
        concurrency: Concurrency,
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
            isinstance(intent, StateObservedIntent)
            and not isinstance(intent.retained_observation.evidence, TemporalObservation)
            for intent in intents
        ):
            raise _unobserved_close(entity)
        ranged = settle_range(
            item,
            intents,
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
        evidence = item.source_evidence
        if isinstance(ranged, DeferredTemporalRange):
            return SettledWrite(source_evidence=evidence, deferred=ranged), ()
        write = SettledWrite(
            source_evidence=evidence,
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
        instruction: PreparedKeyedInstruction,
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
        opening: ComposedBitemporalOpening,
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
        entity = opening.target
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
        evidence = opening.source_evidence
        if isinstance(ranged, DeferredTemporalRange):
            return SettledWrite(source_evidence=evidence, deferred=ranged), ()
        write = SettledWrite(
            source_evidence=evidence,
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
        instruction: PreparedKeyedInstruction,
        version_attr: AttributeIdentity | None,
        observation: StateObservation | None,
    ) -> int | None:
        """The version an addressed write against a versioned row advances
        from, or ``None`` for an unversioned target.

        A row-carried version value is refused BEFORE the observation is even
        required: the version is framework-owned end to end, so it is never an
        alternative source, observed or not. The observation itself is
        required in both concurrency modes, because the framework never
        issues a resolving read on behalf of a keyed write.

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
        :class:`~parallax.core._execution._unit_work.write_items.StateObservedWrite`
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


def _group_keys(item: OrderedWrite, families: InheritanceFacet) -> tuple[_GroupKey, ...] | None:
    """The objects ``item`` writes, by its family's key, or ``None`` where one
    names no complete key: an insert whose key is absent or the database
    computes."""
    objects = (
        item.object_keys
        if isinstance(item, InsertBatch | ObjectLockedBatch)
        else (item.object_key,)
    )
    attribute = entity_view(families, item.target).primary_key.identity
    keys: list[_GroupKey] = []
    for key in objects:
        if key is None:
            return None
        ((_, value),) = key.primary_key
        if value is None:
            return None
        keys.append((attribute, value))
    return tuple(keys)


def _acquisition_candidate(
    write: SettledWrite, item: OrderedWrite, families: InheritanceFacet
) -> _AcquisitionCandidate | None:
    """What ``write``'s deferred range shares a coverage read by, or ``None``
    where it reads alone: a Transaction-Time-Only range, or one naming no
    complete key the database does not allocate."""
    deferred = write.deferred
    if not isinstance(deferred, DeferredTemporalRange):
        return None
    meaning = deferred.meaning
    if not isinstance(meaning.facts.shape, Bitemporal):
        return None
    keys = _group_keys(item, families)
    if keys is None:
        return None
    (key,) = keys
    return _AcquisitionCandidate(
        meaning.facts.entity.identity, meaning.key_attribute, not meaning.gated, key
    )


def _acquisition_compatible(first: _AcquisitionCandidate, later: _AcquisitionCandidate) -> bool:
    return (
        first.entity == later.entity
        and first.key_attribute == later.key_attribute
        and first.locking == later.locking
    )


def _extend_run(
    spans: list[AcquisitionSpan],
    run: _AcquisitionRun | None,
    position: int,
    candidate: _AcquisitionCandidate | None,
) -> _AcquisitionRun | None:
    """The acquisition span open once the deferred write at plan entry
    ``position`` joins it, or starts another where it cannot join ``run``: an
    entry lies between them, the run is full, the write reads differently, or it writes an
    object the run already does. A write that reads alone ends the run."""
    if run is not None and (
        candidate is None
        or position != run.stop
        or run.stop - run.start == _ACQUISITION_RANGES
        or not _acquisition_compatible(run.first, candidate)
        or candidate.key in run.keys
    ):
        _close_run(spans, run)
        run = None
    if candidate is None:
        return None
    if run is None:
        return _AcquisitionRun(position, position + 1, candidate, {candidate.key})
    run.stop = position + 1
    run.keys.add(candidate.key)
    return run


def _close_run(spans: list[AcquisitionSpan], run: _AcquisitionRun | None) -> None:
    if run is not None and run.stop - run.start > 1:
        spans.append(AcquisitionSpan(run.start, run.stop))


def _close_group(
    entries: list[WriteGroup | SettledWrite],
    members: list[tuple[SettledWrite, tuple[PlannedStep, ...]]],
    held: set[_GroupKey],
) -> None:
    if members:
        entries.append(WriteGroup.from_members(members))
    members.clear()
    held.clear()


def _unobserved_close(entity: EntityMetadata) -> WritePlanningError:
    return WritePlanningError(
        f"{entity.identity.name!r}: a temporal write of existing coverage closes the "
        "current milestone, and every close requires the Temporal Observation it "
        "addresses, gates on, and carries state forward from (m-unit-work; m-opt-lock)"
    )


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
    the first row settles the whole step's assignments. Every admitted write
    is single-row, so no multi-row update arrives here any other way.
    """
    key_names = frozenset(attribute.name for attribute in addressed.key_attributes)
    return planned_assignments(
        facts.entity,
        facts.view,
        {name: value for name, value in row.items() if name not in key_names},
    )


def _decorated(audit: AuditDecoration, step: PlannedStep) -> PlannedStep:
    """An addressed Non-Temporal step as audit leaves it: an update decorated
    once, a delete as it is."""
    return audit.decorate_update(step) if isinstance(step, PlannedUpdate) else step


def _require_unobserved(
    entity: EntityMetadata, mutation: str, observation: StateObservation | None
) -> None:
    """Refuse ``observation`` when the target it arrived for is entitled to none.

    Reached only once the caller has established that the target is neither
    temporal nor versioned, which is the one shape `m-unit-work` declares
    observationless ("unversioned Non-Temporal writes have no observation",
    absence structural). Whether a write may hold evidence at all needs the
    model, so the admitted write, a keyed
    :class:`~parallax.core._execution._unit_work.write_items.StateObservedWrite`,
    can only refuse the instruction-local half and
    delegate this half to the model-aware settlement. This is that delegation:
    every write that IS settled crosses it, whatever produced it, so a
    producer that resolves evidence a target cannot carry is told rather than
    quietly stripped.

    Settled is the whole reach of that guarantee. Coalescing and no-op
    elimination run first, in the stage order `m-unit-work` fixes, and a write
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
