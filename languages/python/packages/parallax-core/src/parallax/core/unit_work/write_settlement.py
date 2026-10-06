from __future__ import annotations

import bisect
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Final, cast

from parallax.core.base import (
    TemporalBound,
    retain_document_value,
)
from parallax.core.document_codec import (
    PreparedEffectiveChange,
    prepare_effective_change,
)
from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    Document,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    OccurrenceMetadata,
    TemporalDimension,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import (
    NON_TEMPORAL,
    Bitemporal,
    TemporalFacet,
    TemporalShape,
    TimeInterval,
    TransactionTimeOnly,
    valid_time_coverage,
)
from parallax.core.temporal_write.expansion import (
    Expansion,
    TemporalFacts,
    bitemporal_ends,
    dispose,
    entry_ends,
    kept,
    opening,
    openings,
    planned_close,
    preserved,
    revision_assignments,
    successor_insert,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.instructions import (
    INSERT_MUTATIONS,
    UPDATE_MUTATIONS,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedWrite,
)
from parallax.core.unit_work.materialized import (
    ComposedTemporalWrite,
    FollowingKeyedWrite,
    GroupStates,
    InsertionKeyedWrite,
    MaterializedWriteGroup,
    ObservedKeyedWrite,
    TargetKeyedWrite,
    VersionedEvidence,
    composed_alone,
)
from parallax.core.unit_work.ranges import (
    Decoration,
    DeferredTemporalRange,
    range_claims,
    settle_range,
)
from parallax.core.unit_work.retain import RetainedObservation
from parallax.core.unit_work.strategy import (
    ActorIdentity,
    AuditStrategy,
    AuthoredState,
    CarriedState,
    ChangedState,
    Concurrency,
    ConcurrencyStrategy,
    TemporalStrategy,
    VersionArithmetic,
)
from parallax.core.unit_work.temporal import (
    ResolvedSuccessor,
    bound_cell,
    bound_value,
    resolve_successors,
)
from parallax.core.unit_work.write_validate import WriteRejectedError
from parallax.core.write_plan.columns import ColumnSlice
from parallax.core.write_plan.keys import (
    ObservedStateKey,
    VersionedStateKey,
)
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.observe import PredecessorRow, TemporalObservation, WriteObservation
from parallax.core.write_plan.plan import (
    NO_OWNERSHIP,
    TRANSACTION_TIME_ENDS,
    AllocatedOpening,
    Completion,
    Completions,
    ExecutionUnit,
    Openings,
    OwnedEndpoint,
    Ownership,
    PlannedSteps,
    StepSegment,
    UnitEffects,
    WritePlan,
    eager_segment,
)
from parallax.core.write_plan.planned_rows import (
    WritePlanningError,
    assigned_name,
    entity_view,
    key_target,
    key_tuple,
    planned_assignments,
    planned_row,
    prepared_assignments,
    resolve_row,
    resolved_assignments,
)
from parallax.core.write_plan.steps import (
    ANY_COUNT,
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    RETURNED_MAX_PLUS_ONE,
    UNGATED,
    UNVERSIONED,
    AffectedRows,
    CloseCause,
    ExactCount,
    InsertEntry,
    MaxPlusOne,
    NonTemporalConcurrency,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    PlannedValue,
    Shortfall,
    TemporalGate,
    Versioned,
    VersionGate,
    adopt_planned_assignments,
    shortfall_classification,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = [
    "OrderedWrite",
    "WritePlanningResult",
    "WriteSettlement",
    "reject_readless_document_many",
]

type OrderedWrite = (
    PreparedWrite
    | ObservedKeyedWrite
    | InsertionKeyedWrite
    | TargetKeyedWrite
    | FollowingKeyedWrite
    | ComposedTemporalWrite
    | MaterializedWriteGroup
)
"""One element of the sequence settlement reads: a buffer item once the
planner's rewriting stages have finished with it.

An object-claimed write is absent by construction rather than by convention:
coalescing is the only stage that reads one, and it hands the survivor on as the
ordinary instruction it always was, so batching, ordering, and settlement see an
unversioned write as the bare instruction they measure every other one by.
"""

# The predicate-selected verbs a readless template exists for. A `terminate`
# or `*Until` predicate write names a milestone, so its only legal targets
# materialize to keyed writes long before finalization.
_READLESS_VERBS: Final[frozenset[str]] = frozenset({"update", "delete"})


@dataclass(frozen=True, slots=True)
class WritePlanningResult:
    """One flush's finalized plan.

    Each of its execution units carries the claim its SURVIVING write settled
    against. Work the earlier stages retired (folded into a pending insert,
    cancelled against one, eliminated as a known no-op) reaches no unit, which
    is what keeps a batch's surviving write from spending a claim no statement
    of it will carry (`m-unit-work` "A successful execution unit consumes").
    """

    plan: WritePlan


@dataclass(frozen=True, slots=True, kw_only=True)
class _Settled(UnitEffects):
    """One settled write's steps beside the effects their success publishes."""

    steps: tuple[PlannedStep, ...]


@dataclass(frozen=True, slots=True)
class _SettledClose:
    """What closing a keyed write's or a group's current milestone takes, as its
    topology table describes it."""

    cause: CloseCause
    key_attributes: tuple[AttributeIdentity, ...]
    gate_start_attribute: AttributeIdentity
    gated: bool


@dataclass(frozen=True, slots=True)
class _TableFacts(TemporalFacts):
    """A temporal mutation's facts beside the close and successors its topology
    table describes."""

    close: _SettledClose | None
    resolved_successors: tuple[ResolvedSuccessor, ...]


@dataclass(frozen=True, slots=True)
class _NonTemporalFacts:
    """Every semantic fact one non-temporal mutation settles about its TARGET,
    whatever the verb does to it — decided once per keyed instruction and once
    per Materialized Write Group, by
    :meth:`WriteSettlement._non_temporal_facts` alone.

    Everything here is a value some producer emitted for THIS mutation: the
    facet's compiled view of the target and the Attribute the Optimistic Lock
    Facet names as its version source. No producer is among them, which is what
    lets a segment hold this by reference and still settle no decision at step
    access.

    What is deliberately absent is any row's own observed version: a keyed
    write's is one value it settles with, a group's is a column it keeps, and
    neither is a fact about the mutation.
    """

    entity: EntityMetadata
    view: InheritanceEntityView
    version_attribute: AttributeIdentity | None


@dataclass(frozen=True, slots=True)
class _AddressedFacts:
    """What addressing rows that already exist settles, once per non-temporal
    update or delete, by :meth:`WriteSettlement._addressed_facts` alone.

    An insert opens a new lineage and addresses nothing, so none of this is a
    fact about one: it has no key to address by, nothing observed to gate
    against, and no shortfall a missing row could produce.
    """

    key_attributes: tuple[AttributeIdentity, ...]
    gated: bool
    shortfall: Shortfall


@dataclass(frozen=True, slots=True)
class _VersionOverlay:
    """The version Attribute a settled update writes and the arithmetic it
    advances the observed value by.

    Carried by the emission rather than by the target's facts because only an
    update overlays a version: a delete advances nothing, and an unversioned
    update has nothing to advance, so neither obtains the arithmetic.
    """

    attribute: AttributeIdentity
    arithmetic: VersionArithmetic


@dataclass(frozen=True, slots=True)
class _Deletion:
    """What a settled non-temporal delete emits: nothing beyond its address.

    A delete assigns no value at all, so its emission carries none — the
    absence is the shape rather than a null field every reader re-checks.
    """


@dataclass(frozen=True, slots=True)
class _Revision:
    """What a settled non-temporal update emits: the replacement values every
    row of the mutation writes, and the version overlay an update against a
    versioned target lays over them."""

    base_assignments: PlannedAssignments
    version: _VersionOverlay | None


type _NonTemporalEmission = _Deletion | _Revision
"""Which non-temporal step one settled mutation emits, and what it assigns.

Decided once per mutation, from the authored verb, by whichever arm settled it
— which is what leaves the verb behind at settlement: no emitter re-reads it,
and a delete carrying assignments or an update missing them is unconstructable
rather than merely asserted against.
"""

_DELETION: Final[_Deletion] = _Deletion()


class WriteSettlement:
    """The Write Planner's own settlement module (`m-unit-work`).

    Constructed once per accepted Metamodel by the planner that owns it, with
    that model, the Inheritance and Temporal facets it compiled, and the
    concurrency, temporal, and audit strategies the composition layer wired.
    :meth:`settle` is its entire surface: no caller settles one item, packs a
    segment, decorates a step, or collects a claim by hand.
    """

    __slots__ = (
        "_audit",
        "_concurrency",
        "_families",
        "_model",
        "_temporal_facet",
        "_temporal_strategy",
    )

    def __init__(
        self,
        model: Metamodel,
        families: InheritanceFacet,
        temporal_facet: TemporalFacet,
        *,
        concurrency: ConcurrencyStrategy,
        temporal: TemporalStrategy,
        audit: AuditStrategy,
    ) -> None:
        self._model = model
        self._families = families
        self._temporal_facet = temporal_facet
        self._concurrency = concurrency
        self._temporal_strategy = temporal
        self._audit = audit

    def settle(
        self,
        ordered_writes: Sequence[OrderedWrite],
        *,
        concurrency: Concurrency,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
        ownership: Ownership = NO_OWNERSHIP,
        counts_unchanged_rows: bool = False,
    ) -> WritePlanningResult:
        """The whole ordered sequence as one Write Planning Result.

        An item the planner's earlier stages retired never reaches this loop,
        and therefore no execution unit carries the evidence it was holding.

        Packing is a property of adjacency, which is why the whole sequence
        crosses in one call: a run of eagerly settled steps stays one eager
        segment, and a Materialized Write Group always occupies its own. A
        group's every group-wide semantic fact — temporal topology, the
        gate/concurrency decision, the affected-row policy, the assignment
        shape, and the resolved instant if the group needs one — is decided
        into that segment before this returns; the segment, and the ``WritePlan``
        it becomes part of, retain no group, concurrency mode, Transaction
        Instant, or strategy object. Only the PER-ROW data stays as the group's
        own compact evidence, and a row's ``PlannedWrite`` is rebuilt from that
        evidence and the already-settled facts one at a time, on demand, so a
        large materialized run never forces a parallel ``PlannedWrite``-per-row
        object graph merely by being planned.

        Provenance decoration reaches the eagerly settled steps only, before
        they are packed and after each one's topology is settled; a Materialized
        Write Group's rows stay as its segment produced them.

        ``actor_identity`` is passed to the audit port and never inspected
        here; ``transaction_instant`` is threaded unevaluated until a surviving
        temporal write needs it.

        Each ordered item settles into one execution unit, which records what
        its success changes: the claim it spends, the observed state it
        revises, and the rows it removes and opens. ``ownership`` answers which
        current rows this attempt already opened, so a write against one of
        them revises or removes that row instead of closing it into history.

        A milestone an observed or insertion-authored write leaves exactly as
        it was is kept rather than closed and chained, where its unchanged
        state is proven without changing it: by the shared lock under Locking,
        by ownership for a row the attempt opened, and otherwise by a guard
        that matches the observed milestone — which only a database whose
        write count includes unchanged rows (``counts_unchanged_rows``) can
        report. Without that proof the milestone is closed and chained as any
        changed one.
        """
        segments: list[StepSegment] = []
        pending: list[PlannedStep] = []
        units: list[ExecutionUnit] = []
        count = 0

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
                segment = self._settle_group(item, concurrency, transaction_instant, ownership)
                segments.append(segment)
                count += len(segment)
                units.append(segment.unit(count))
                continue
            shape = (
                self._temporal_facet.shape(item.target.identity)
                if isinstance(item, ComposedTemporalWrite)
                else self._temporal_facet.shape(item.instruction.target.identity)
                if isinstance(item, ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite)
                else None
            )
            composed = self._composition(item, shape)
            if composed is not None:
                assert isinstance(shape, TransactionTimeOnly | Bitemporal)
                entity = composed.target
                view = entity_view(self._families, entity)
                gated = self._concurrency.gates(concurrency, self._model, entity.identity)
                ranged = settle_range(
                    composed,
                    view=view,
                    shape=shape,
                    gated=gated,
                    instant=transaction_instant.value(),
                    ownership=ownership,
                    decorate=Decoration(self._audit, actor_identity, transaction_instant),
                    guards=counts_unchanged_rows,
                )
                claim = range_claims(composed)
                if isinstance(ranged, DeferredTemporalRange):
                    units.append(ExecutionUnit(end=count, claim=claim, deferred=ranged))
                    continue
                pending.extend(ranged.steps)
                count += len(ranged.steps)
                units.append(
                    ExecutionUnit(
                        end=count,
                        claim=claim,
                        changed=ranged.changed,
                        removed=ranged.removed,
                        opened=ranged.opened,
                        derived=ranged.derived,
                        concludes=ranged.concludes,
                    )
                )
                continue
            assert not isinstance(item, ComposedTemporalWrite | MaterializedWriteGroup)
            settled, claim, own_state = self._settle_keyed(
                item,
                concurrency,
                transaction_instant,
                ownership,
                shape,
                advances,
                guards=counts_unchanged_rows,
            )
            for step in settled.steps:
                pending.append(
                    self._audit.decorate(
                        step,
                        actor_identity=actor_identity,
                        transaction_instant=transaction_instant,
                    )
                )
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
        return WritePlanningResult(
            WritePlan(steps=PlannedSteps(tuple(segments)), units=tuple(units))
        )

    def _settle_keyed(
        self,
        item: PreparedWrite | ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: Ownership,
        shape: TemporalShape | None,
        advances: int = 0,
        *,
        guards: bool = False,
    ) -> tuple[_Settled | Expansion, Completion | None, VersionedStateKey | None]:
        """One ordered keyed write's settled steps and effects, beside the
        claim its unit spends and the state its carrier itself names as
        changed. ``advances`` is how many versions earlier writes of its scope
        a barrier kept before it advance the row past the state that scope
        names.

        A write spending one retained observation, or several twinned
        observations of one state, changes that state wherever its steps
        change the row it observed."""
        own_state: VersionedStateKey | None = None
        observation: WriteObservation | None = None
        claim: Completion | None = None
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
            ownership,
            shape,
            source=source,
            own_version=None if own_state is None else own_state.version,
            conditioned=isinstance(item, TargetKeyedWrite),
            advances=advances,
            guards=guards,
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
        instruction: PreparedWrite,
        observation: WriteObservation | None,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: Ownership,
        shape: TemporalShape | None,
        *,
        source: ObservedStateKey | None = None,
        own_version: int | None = None,
        conditioned: bool = False,
        advances: int = 0,
        guards: bool = False,
    ) -> _Settled | Expansion:
        """One ordered write's steps and effects. ``source`` is the observed
        state the write's claim names, which it changes wherever it changes the
        row it observed. ``own_version`` is the version a write
        advances from in place of an observed one: the version this attempt's
        own writes left a row it inserted at, or the version a caller's
        condition requires. ``conditioned`` says the gate binds that caller's
        condition, so a shortfall against it is a failed precondition.
        ``advances`` moves an observed version past the writes of its state a
        barrier kept before this one."""
        if isinstance(instruction, PreparedPredicateWrite):
            return _Settled(steps=self._settle_predicate(instruction))
        entity = instruction.target
        if shape is None:
            shape = self._temporal_facet.shape(entity.identity)
        if isinstance(shape, TransactionTimeOnly | Bitemporal):
            return self._settle_temporal(
                entity,
                shape,
                instruction,
                observation,
                concurrency,
                tx_instant,
                ownership,
                source,
                guards=guards,
                preserves=not conditioned,
            )
        facts = self._non_temporal_facts(entity)
        changed = _changes(source)
        if instruction.mutation == "insert":
            return _Settled(steps=(self._settle_insert(facts, instruction),), changed=changed)
        addressed = self._addressed_facts(facts, concurrency, conditioned=conditioned)
        observed_version = (
            own_version
            if own_version is not None
            else self._observed_version(entity, instruction, facts.version_attribute, observation)
        )
        if advances and observed_version is not None:
            observed_version = self._advanced(observed_version, advances)
        return _Settled(
            steps=(
                _non_temporal_step(
                    facts,
                    addressed,
                    emission=(
                        _DELETION
                        if instruction.mutation == "delete"
                        else _Revision(
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
            changed=changed,
        )

    def _settle_predicate(self, instruction: PreparedPredicateWrite) -> tuple[PlannedStep, ...]:
        """One readless predicate-selected write as its single step.

        Admissibility is the prepared product's own: preparation already refused
        an inheritance-family target and a verb the target does not take. What
        is refused here is routing — a versioned or temporal target has no
        readless template at all and materializes to keyed writes at buffer
        time, so reaching this stage with one is a caller wiring defect.
        """
        entity = instruction.selection.target
        if (
            isinstance(
                self._temporal_facet.shape(entity.identity), TransactionTimeOnly | Bitemporal
            )
            or self._concurrency.version_attribute(self._model, entity.identity) is not None
        ):
            raise WritePlanningError(
                f"{instruction.selection.target.identity.canonical!r}: a predicate write on a "
                "versioned or temporal "
                "target has no readless template — it must materialize to keyed writes before "
                "reaching planning (m-opt-lock; ADR 0014); this is a caller wiring defect"
            )
        if instruction.mutation not in _READLESS_VERBS:
            raise WritePlanningError(
                f"{instruction.selection.target.identity.canonical!r}: a readless predicate "
                f"{instruction.mutation!r} "
                "names a milestone, and every legal milestone target materializes to keyed "
                "writes before planning (m-batch-write 'Predicate-selected readless forms')"
            )
        reject_readless_document_many(entity, instruction)
        target = instruction.selection
        if instruction.mutation == "delete":
            return (
                PlannedDelete(
                    entity=entity.identity,
                    target=target,
                    concurrency=UNVERSIONED,
                    affected_rows=ANY_COUNT,
                ),
            )
        return (
            PlannedUpdate(
                entity=entity.identity,
                target=target,
                assignments=prepared_assignments(entity, instruction.managed_assignments),
                concurrency=UNVERSIONED,
                affected_rows=ANY_COUNT,
            ),
        )

    def _settle_insert(
        self, facts: _NonTemporalFacts, instruction: PreparedKeyedWrite
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
            InsertEntry(row=planned_row(facts.entity, facts.view, row, version), origin=NEW_LINEAGE)
            for row in instruction.rows
        )
        return PlannedInsert(entity=facts.entity.identity, entries=entries)

    def _non_temporal_facts(self, entity: EntityMetadata) -> _NonTemporalFacts:
        """What one non-temporal mutation settles about its target, before a
        row is in hand and whatever the verb does to it.

        The sole site for each of these decisions, whichever representation the
        mutation arrived as: which members the family makes applicable, and
        which Attribute (if any) carries the optimistic version. An eagerly
        settled instruction and a Materialized Write Group therefore cannot
        answer any of them differently. What only a write against EXISTING rows
        settles belongs to :meth:`_addressed_facts` instead.
        """
        return _NonTemporalFacts(
            entity=entity,
            view=entity_view(self._families, entity),
            version_attribute=self._concurrency.version_attribute(self._model, entity.identity),
        )

    def _addressed_facts(
        self, facts: _NonTemporalFacts, concurrency: Concurrency, *, conditioned: bool = False
    ) -> _AddressedFacts:
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
        return _AddressedFacts(
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
    ) -> _VersionOverlay | None:
        """The version overlay a settled update carries, or absence for an
        unversioned target — which has no version to advance and therefore asks
        the strategy for no arithmetic."""
        if version_attribute is None:
            return None
        return _VersionOverlay(
            attribute=version_attribute, arithmetic=self._concurrency.version_arithmetic()
        )

    def _settle_temporal(
        self,
        entity: EntityMetadata,
        shape: TransactionTimeOnly | Bitemporal,
        instruction: PreparedKeyedWrite,
        observation: WriteObservation | None,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: Ownership,
        source: ObservedStateKey | None,
        *,
        guards: bool = False,
        preserves: bool = True,
    ) -> _Settled | Expansion:
        """One temporal mutation as the effects on its predecessor and its
        successors, in that order. ``source`` is the predecessor's observed
        state, as the write's claim names it.

        Preparation admits a temporal keyed instruction with exactly one row
        (`m-unit-work`), since each row of a milestone chain opens its own
        successors.

        An insert opens a new lineage over its prepared window
        (:func:`~parallax.core.temporal_write.expansion.opening`).

        A changed successor overlays every member the instruction's row
        assigns: an observed update's row is its literal assignment set.

        A predecessor that existed before this attempt is closed and every
        nonempty successor opened. One this attempt opened itself is never
        closed into history: it is revised in place when exactly one successor
        keeps its complete physical address, and removed otherwise
        (:func:`~parallax.core.temporal_write.expansion.dispose`).

        An update every assigned member of which the predecessor already holds
        leaves it as it was, and where that is proven
        (:func:`~parallax.core.temporal_write.expansion.preserved`) it is kept
        rather than closed. A caller's write that ``preserves`` nothing is
        always closed, since its caller asked for the revision.
        """
        if instruction.mutation in INSERT_MUTATIONS:
            return self._settle_temporal_insert(entity, shape, instruction, tx_instant, source)
        observed = observation if isinstance(observation, TemporalObservation) else None
        facts = self._temporal_facts(
            entity,
            shape,
            instruction.mutation,
            instruction.valid_time_window,
            observed=observed is not None,
            concurrency=concurrency,
            tx_instant=tx_instant,
        )
        close = facts.close
        # Every milestone verb closes what it observed, which the refusal in
        # `_temporal_facts` guarantees reached it.
        assert close is not None and observed is not None
        row = instruction.rows[0]
        authored_attributes, authored_value_objects = resolve_row(
            entity, facts.view, row, context="insert"
        )
        predecessor = observed.predecessor
        if (
            preserves
            and instruction.mutation in UPDATE_MUTATIONS
            and (guards or not close.gated or ownership.owns_any(entity.identity))
        ):
            key_names = {attribute.name for attribute in close.key_attributes}
            assigned = {name: value for name, value in row.items() if name not in key_names}
            if predecessor.holds(facts.view.member_selection, assigned):
                kept_as_is = preserved(
                    facts, _observed_close(facts, close, row, predecessor), ownership, guards=guards
                )
                if kept_as_is is not None:
                    return kept_as_is
        if facts.resolved_successors:
            predecessor = predecessor.with_bindable_document()
        successors = tuple(
            _successor_step(
                facts, resolved, authored_attributes, authored_value_objects, predecessor
            )
            for resolved in facts.resolved_successors
        )
        closing = _observed_close(facts, close, row, predecessor)
        return dispose(facts, closing, successors, predecessor, ownership, source)

    def _settle_temporal_insert(
        self,
        entity: EntityMetadata,
        shape: TransactionTimeOnly | Bitemporal,
        instruction: PreparedKeyedWrite,
        tx_instant: TransactionInstant,
        source: ObservedStateKey | None,
    ) -> _Settled:
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
                entries=(opening(facts, attributes, value_objects, instruction.valid_time_window),),
            ),
        )
        return _Settled(
            steps=inserts,
            changed=_changes(source),
            opened=Openings(
                continued=openings(facts, inserts),
                allocated=_allocated(facts, inserts) if allocates else (),
            ),
        )

    def _temporal_facts(
        self,
        entity: EntityMetadata,
        shape: TransactionTimeOnly | Bitemporal,
        mutation: str,
        valid_time_window: TimeInterval | None,
        *,
        observed: bool,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
    ) -> _TableFacts:
        """Everything one temporal mutation that closes its current milestone
        settles before a row is in hand, read off its topology table.

        The sole site for each of these decisions, whichever representation the
        mutation arrived as: which topology the Temporal Facet describes it
        with, what closing takes, which successors exist and what each one's
        bound expression and represented-state kind is, and the one instant the
        attempt stamps. An eagerly settled instruction and a Materialized Write
        Group therefore cannot answer any of them differently.

        ``shape`` is the family's Temporal Shape the caller already read to
        dispatch here, retained by reference so no later decision re-reads it.

        ``observed`` says whether a Temporal Observation reached this mutation;
        a topology that closes has nothing to address, gate on, or carry state
        forward from without one, so the refusal precedes every consultation
        after it — the clock included, which is what keeps a refused write from
        capturing the attempt's instant.
        """
        topology = self._temporal_strategy.topology(shape, mutation)
        if topology.closure is not None and not observed:
            raise WritePlanningError(
                f"{entity.identity.name!r}: a temporal {mutation!r} closes the "
                "current milestone, and every close requires the Temporal Observation it "
                "addresses, gates on, and carries state forward from (m-unit-work; m-opt-lock)"
            )
        view = entity_view(self._families, entity)
        close: _SettledClose | None = None
        if topology.closure is not None:
            close = _SettledClose(
                cause=topology.closure.cause,
                key_attributes=(view.primary_key.identity,),
                gate_start_attribute=_gate_axis(shape, topology.closure.gate_basis).start_attribute,
                gated=self._concurrency.gates(concurrency, self._model, entity.identity),
            )
        return _TableFacts(
            entity=entity,
            view=view,
            shape=shape,
            # Reaching a surviving temporal mutation is what makes the attempt
            # capture its instant; the close's new Transaction-Time end and
            # every successor's fresh start derive from that one value.
            instant=tx_instant.value(),
            close=close,
            resolved_successors=resolve_successors(
                topology.successors, valid_time_window=valid_time_window
            ),
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
        if instruction.mutation == "update" and version_attr.name in instruction.rows[0]:
            self._concurrency.reject_authored_version(entity.identity, version_attr)
        return self._concurrency.require_version(entity.identity, observation)

    def _settle_group(
        self,
        group: MaterializedWriteGroup,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: Ownership,
    ) -> _GroupSegment:
        """One Materialized Write Group as one already-settled segment.

        Every group-wide semantic fact — the temporal topology, the gate and
        concurrency decision, the affected-row policy, the assignment shape,
        and (only when the surviving group needs one) the concrete Transaction
        Instant literal — is decided HERE, once, before this method returns.
        The returned segment carries none of the group, the concurrency mode,
        the Transaction Instant, or a strategy object: its ``step`` rebuilds
        one row's Planned Write from these already-decided facts and the
        group's own compact evidence alone.
        """
        entity = group.mutation.selection.target
        shape = self._temporal_facet.shape(entity.identity)
        if isinstance(shape, TransactionTimeOnly | Bitemporal):
            return self._settle_temporal_group(
                group, entity, shape, concurrency, tx_instant, ownership
            )
        return self._settle_versioned_group(group, entity, concurrency)

    def _settle_versioned_group(
        self,
        group: MaterializedWriteGroup,
        entity: EntityMetadata,
        concurrency: Concurrency,
    ) -> _MaterializedNonTemporalSegment:
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
        emission: _NonTemporalEmission = _DELETION
        if mutation != "delete":
            if facts.version_attribute is not None and any(
                isinstance(assignment.member, AttributeMetadata)
                and assignment.member.identity == facts.version_attribute
                for assignment in group.mutation.managed_assignments
            ):
                self._concurrency.reject_authored_version(entity.identity, facts.version_attribute)
            emission = _Revision(
                prepared_assignments(entity, group.mutation.managed_assignments),
                self._version_overlay(facts.version_attribute),
            )
        return _MaterializedNonTemporalSegment(
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

    def _settle_temporal_group(
        self,
        group: MaterializedWriteGroup,
        entity: EntityMetadata,
        shape: TransactionTimeOnly | Bitemporal,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
        ownership: Ownership,
    ) -> _MaterializedTemporalSegment:
        """A temporal Materialized Write Group's segment.

        The group's facts are settled through the same
        :meth:`_temporal_facts` an eagerly settled temporal instruction crosses
        — the only clock consultation this group's whole flush makes, however
        many rows it resolved — and the segment holds them by reference. The
        authored assignments resolve here, once, in insert context, so a
        marker no opened row can express is refused while the plan is made
        rather than when a step is asked for. Only a row's own retained state
        remains for :meth:`_MaterializedTemporalSegment.step` to bind, through
        the same close and successor primitives :meth:`_settle_temporal`
        composes.

        With two or more assignments a surviving row may still restore some of
        them, so the codec's effective-change comparison is prepared once here
        and the changed step overlays only the members it answers as effective
        for that row (`m-unit-work` "Comparing an assigned member"). A single
        assignment was already judged effective when the row was selected.

        A selected row this attempt opened itself is revised or removed rather
        than closed, and an empty successor is not opened, exactly as for a
        keyed write's own predecessor
        (:func:`~parallax.core.temporal_write.expansion.dispose`). Only a group with such
        a row lays its rows out one by one; every other group keeps one uniform
        step count per row.
        """
        evidence = group.evidence
        assert isinstance(evidence, PredecessorRows)
        facts = self._temporal_facts(
            entity,
            shape,
            group.mutation.mutation,
            group.mutation.valid_time_window,
            observed=True,
            concurrency=concurrency,
            tx_instant=tx_instant,
        )
        close = facts.close
        # Every predicate milestone verb closes what it selected and opens no
        # new lineage, so each successor reads the row's own retained state.
        assert close is not None
        assert not any(
            isinstance(resolved.state, AuthoredState) for resolved in facts.resolved_successors
        )
        assignments = group.mutation.managed_assignments
        authored_attributes, authored_value_objects = resolved_assignments(
            entity, assignments, "insert"
        )
        selection = evidence.selection
        segment = _MaterializedTemporalSegment(
            facts=facts,
            close=close,
            evidence=evidence,
            authored_attributes=MappingProxyType(authored_attributes),
            authored_value_objects=MappingProxyType(authored_value_objects),
            change=(
                prepare_effective_change(
                    selection.shape,
                    {assigned_name(assignment): assignment.value for assignment in assignments},
                    absent=evidence.absent,
                )
                if len(assignments) >= 2
                else None
            ),
            gate_position=selection.position(close.gate_start_attribute) if close.gated else None,
            valid_end_position=(
                selection.position(shape.valid_time.end_attribute)
                if isinstance(shape, Bitemporal)
                else None
            ),
            steps_per_row=1 + len(facts.resolved_successors),
            changed=GroupStates(
                entity.identity, facts.view.primary_key.identity.name, evidence, shape
            ),
        )
        return segment.with_layout(ownership)

    def _composition(
        self, item: OrderedWrite, shape: TemporalShape | None
    ) -> ComposedTemporalWrite | None:
        """``item`` as the composition the range path settles, or ``None`` for
        an item settled by its own topology.

        A lone observed temporal write whose window lies inside the predecessor
        it observed binds that predecessor alone, which is exactly its topology's
        close and successors; every other observed temporal write is a range over
        coverage only binding can discover, and so is every temporal write an
        insertion authorized or a caller addressed, which observed nothing.
        """
        if isinstance(item, ComposedTemporalWrite):
            return item
        if isinstance(item, InsertionKeyedWrite | TargetKeyedWrite) and isinstance(
            shape, TransactionTimeOnly | Bitemporal
        ):
            view = entity_view(self._families, item.instruction.target)
            return composed_alone(item, view.primary_key.identity.name)
        if not isinstance(item, ObservedKeyedWrite) or not isinstance(shape, Bitemporal):
            return None
        instruction = item.instruction
        observation = item.observation
        if not isinstance(observation, TemporalObservation):
            return None
        window = instruction.valid_time_window
        coverage = valid_time_coverage(shape, observation.predecessor, None)
        assert window is not None and coverage is not None  # a Bitemporal write and its row
        if coverage.contains(window):
            return None
        view = entity_view(self._families, instruction.target)
        return composed_alone(item, view.primary_key.identity.name)


@dataclass(frozen=True, slots=True)
class _MaterializedNonTemporalSegment:
    """A versioned Materialized Write Group's rows: one Planned Update or
    Planned Delete per resolved row, assembled on demand from already-decided,
    group-wide facts and the group's own compact evidence alone.

    Every semantic decision the group's authored mutation settles — the
    applicable members and version source (``facts``), the family-effective
    primary key, the gate decision and how a shortfall classifies
    (``addressed``), and the assignments and version arithmetic an update lays
    over a row (``emission``) — is resolved once, when the segment is built, and
    reached here through those references. ``step`` only binds one row's own key
    value and observed version into that already-decided shape, through the
    same :func:`_non_temporal_step` an eagerly settled keyed write emits from.

    ``versions`` is the group's own evidence column, held by reference: the
    advance is an addition performed at step access, so a row's new version is
    never a second column sized by the resolved row count.

    No group, concurrency mode, Transaction Instant, or strategy object is
    reachable here — every value :meth:`step` reads is either a settled fact or
    an aligned column lookup by row index — and two calls for the same index
    return equal but distinct objects, never a shared mutable flyweight.
    """

    facts: _NonTemporalFacts
    addressed: _AddressedFacts
    key_name: str
    keys: ColumnSlice[object]
    versions: ColumnSlice[int]
    emission: _NonTemporalEmission
    affected_rows: AffectedRows
    changed: Iterable[ObservedStateKey]

    def __len__(self) -> int:
        return len(self.versions)

    def unit(self, end: int) -> ExecutionUnit:
        return ExecutionUnit(end=end, changed=self.changed)

    def step(self, index: int) -> PlannedStep:
        return _non_temporal_step(
            self.facts,
            self.addressed,
            emission=self.emission,
            key_rows=({self.key_name: self.keys[index]},),
            observed_version=self.versions[index],
            affected_rows=self.affected_rows,
        )


@dataclass(frozen=True, slots=True)
class _RowLayout:
    """How one selected row's steps are laid out when they differ from the
    uniform close and every successor.

    ``kept`` is the successor position an owned row is revised in place into,
    and ``revises`` whether that revision assigns anything; an owned row with no
    kept successor is removed; a row that existed before the attempt has
    neither and is closed. ``opened`` is the successor positions opened, in
    order — every nonempty one but ``kept`` — and ``continues`` whether the
    row is coverage an admitted insertion opened, which its successors then
    continue.
    """

    owned: bool
    kept: int | None
    revises: bool
    opened: tuple[int, ...]
    continues: bool = False

    @property
    def steps(self) -> int:
        return (0 if self.kept is not None and not self.revises else 1) + len(self.opened)


@dataclass(frozen=True, slots=True)
class _GroupLayout:
    """Where each selected row's steps start, for a group some of whose rows
    the attempt opened itself or open an empty successor.

    ``rows`` holds a :class:`_RowLayout` for such a row and ``None`` for a row
    that keeps the uniform close and every successor.
    """

    rows: tuple[_RowLayout | None, ...]
    offsets: tuple[int, ...]
    length: int


@dataclass(frozen=True, slots=True)
class _MaterializedTemporalSegment:
    """A temporal Materialized Write Group's rows: one close plus its
    successors per resolved row, assembled on demand from already-decided,
    group-wide facts and the group's own retained evidence alone.

    Every semantic decision the group's authored mutation settles — which
    successors exist, each one's represented-state kind, which Valid-Time
    bound expression applies, the close's cause and gate, the authored
    assignments, and the positions of the cells a close reads — is resolved
    once, when the segment is built, and reached here by reference. ``step``
    builds only the one close or successor its index names, through the same
    primitives an eagerly settled temporal instruction composes; a close reads
    its row's cells by position and resolves no Predecessor Row.

    ``steps_per_row`` is invariant across the group's rows that existed before
    the attempt — every row shares the same authored mutation and therefore the
    same topology — so without a ``layout`` a flat step index maps to (row,
    sub-step) by simple division. A ``layout`` exists only when the attempt
    owns some selected row, whose revision or removal takes its own step count.
    The one thing kept between accesses is a row's Predecessor Row while more
    of its successors follow, so the successors of a row, asked for in turn,
    share the one recursively immutable copy of its document they bind and
    patch.
    """

    facts: _TableFacts
    close: _SettledClose
    evidence: PredecessorRows
    authored_attributes: Mapping[AttributeIdentity, PlannedValue]
    authored_value_objects: Mapping[ValueObjectIdentity, object]
    change: PreparedEffectiveChange | None
    gate_position: int | None
    valid_end_position: int | None
    steps_per_row: int
    changed: Iterable[ObservedStateKey]
    layout: _GroupLayout | None = None
    _bound: tuple[int, PredecessorRow] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __len__(self) -> int:
        layout = self.layout
        return len(self.evidence) * self.steps_per_row if layout is None else layout.length

    def step(self, index: int) -> PlannedStep:
        layout = self.layout
        if layout is None:
            return self._row_step(*divmod(index, self.steps_per_row))
        row_index = bisect.bisect_right(layout.offsets, index) - 1
        sub_step = index - layout.offsets[row_index]
        row = layout.rows[row_index]
        if row is None:
            return self._row_step(row_index, sub_step)
        return self._laid_out_step(row_index, row, sub_step)

    def unit(self, end: int) -> ExecutionUnit:
        return ExecutionUnit(
            end=end,
            changed=self.changed,
            removed=_GroupRemovals(self),
            opened=Openings(
                fresh=_GroupOpenings(self, continued=False),
                continued=_GroupOpenings(self, continued=True),
            ),
        )

    def with_layout(self, ownership: Ownership) -> _MaterializedTemporalSegment:
        """This segment laid out row by row, when some selected row is one the
        attempt opened (``ownership``) or opens an empty successor; otherwise
        this segment itself, whose rows all take the uniform steps."""
        facts = self.facts
        owning = ownership.owns_any(facts.entity.identity)
        if not owning and not isinstance(facts.shape, Bitemporal):
            return self
        rows = range(len(self.evidence))
        if not any(self._row_layout(row, ownership, owning) is not None for row in rows):
            return self
        layouts = tuple(self._row_layout(row, ownership, owning) for row in rows)
        offsets: list[int] = []
        length = 0
        for layout in layouts:
            offsets.append(length)
            length += self.steps_per_row if layout is None else layout.steps
        return replace(
            self, layout=_GroupLayout(rows=layouts, offsets=tuple(offsets), length=length)
        )

    def _row_layout(self, row_index: int, ownership: Ownership, owning: bool) -> _RowLayout | None:
        positions = range(len(self.facts.resolved_successors))
        own = self.endpoint(row_index) if owning else None
        if own is None or not ownership.owns(own):
            if not any(self._opens_empty(row_index, position) for position in positions):
                return None
            return _RowLayout(
                owned=False,
                kept=None,
                revises=False,
                opened=tuple(
                    position for position in positions if not self._opens_empty(row_index, position)
                ),
            )
        nonempty = tuple(
            position for position in positions if not self._opens_empty(row_index, position)
        )
        predecessor = self._predecessor(row_index, keep=False)
        pieces = tuple(self._successor(row_index, position, predecessor) for position in nonempty)
        kept_at = kept(self.facts, own, pieces)
        return _RowLayout(
            owned=True,
            kept=None if kept_at is None else nonempty[kept_at],
            revises=kept_at is not None
            and revision_assignments(self.facts, pieces[kept_at].entries[0], predecessor)
            is not None,
            opened=tuple(
                position
                for index, position in enumerate(nonempty)
                if kept_at is None or index != kept_at
            ),
            continues=ownership.continues_insertion(own),
        )

    def opened_positions(self, row_index: int) -> tuple[int, ...]:
        layout = self.layout
        row = None if layout is None else layout.rows[row_index]
        if row is None:
            return tuple(range(len(self.facts.resolved_successors)))
        return row.opened

    def removes(self, row_index: int) -> bool:
        layout = self.layout
        row = None if layout is None else layout.rows[row_index]
        return row is not None and row.owned and row.kept is None

    def continues(self, row_index: int) -> bool:
        layout = self.layout
        row = None if layout is None else layout.rows[row_index]
        return row is not None and row.continues

    def endpoint(self, row_index: int) -> OwnedEndpoint:
        evidence = self.evidence
        valid_end_position = self.valid_end_position
        return OwnedEndpoint(
            self.facts.entity.identity,
            (evidence.key(row_index),),
            TRANSACTION_TIME_ENDS
            if valid_end_position is None
            else bitemporal_ends(evidence.rows[row_index][valid_end_position]),
        )

    def opened_endpoint(self, row_index: int, position: int) -> OwnedEndpoint:
        """The complete physical address the successor at ``position`` of row
        ``row_index`` opens, read from the bounds it binds rather than from a
        built row."""
        ends = TRANSACTION_TIME_ENDS
        if isinstance(self.facts.shape, Bitemporal):
            _start, end = self._bounds(row_index, position)
            ends = bitemporal_ends(end)
        return OwnedEndpoint(self.facts.entity.identity, (self.evidence.key(row_index),), ends)

    def _opens_empty(self, row_index: int, position: int) -> bool:
        if not isinstance(self.facts.shape, Bitemporal):
            return False
        start, end = self._bounds(row_index, position)
        return end is not TemporalBound.INFINITY and end == start

    def _bounds(self, row_index: int, position: int) -> tuple[object, object]:
        shape = self.facts.shape
        assert isinstance(shape, Bitemporal)  # only a Bitemporal successor binds a window
        evidence = self.evidence
        row = evidence.rows[row_index]
        start_position = evidence.selection.position(shape.valid_time.start_attribute)
        end_position = self.valid_end_position
        assert start_position is not None and end_position is not None
        window = self.facts.resolved_successors[position].window
        assert window is not None  # only a Bitemporal successor binds a window
        start, end = row[start_position], row[end_position]
        return bound_value(window.start, start, end), bound_value(window.end, start, end)

    def _closing(self, row_index: int) -> PlannedClose:
        evidence = self.evidence
        row = evidence.rows[row_index]
        gate_position = self.gate_position
        valid_end_position = self.valid_end_position
        return _close_step(
            self.facts,
            self.close,
            key_values=(row[evidence.key_position],),
            observed_valid_end=None if valid_end_position is None else row[valid_end_position],
            observed_gate_start=None if gate_position is None else row[gate_position],
        )

    def _row_step(self, row_index: int, sub_step: int) -> PlannedStep:
        if sub_step == 0:
            return self._closing(row_index)
        predecessor = self._predecessor(row_index, keep=sub_step < self.steps_per_row - 1)
        return self._successor(row_index, sub_step - 1, predecessor)

    def _laid_out_step(self, row_index: int, row: _RowLayout, sub_step: int) -> PlannedStep:
        predecessor = self._predecessor(row_index, keep=True)
        if not row.owned:
            if sub_step == 0:
                return self._closing(row_index)
            return self._successor(row_index, row.opened[sub_step - 1], predecessor)
        owned = row
        if owned.kept is None:
            if sub_step == 0:
                closing = self._closing(row_index)
                return PlannedTemporalRemoval(
                    entity=closing.entity,
                    target=closing.target,
                    concurrency=closing.concurrency,
                    affected_rows=closing.affected_rows,
                )
            return self._successor(row_index, owned.opened[sub_step - 1], predecessor)
        if owned.revises:
            if sub_step == 0:
                closing = self._closing(row_index)
                piece = self._successor(row_index, owned.kept, predecessor)
                assignments = revision_assignments(self.facts, piece.entries[0], predecessor)
                assert assignments is not None  # laid out as a revision that assigns
                return PlannedTemporalRevision(
                    entity=closing.entity,
                    target=closing.target,
                    assignments=assignments,
                    concurrency=closing.concurrency,
                    affected_rows=closing.affected_rows,
                )
            sub_step -= 1
        return self._successor(row_index, owned.opened[sub_step], predecessor)

    def _predecessor(self, row_index: int, *, keep: bool) -> PredecessorRow:
        bound = self._bound
        if bound is not None and bound[0] == row_index:
            return bound[1]
        evidence = self.evidence
        document = evidence.document(row_index)
        predecessor = PredecessorRow.over_row(
            evidence.selection,
            evidence.rows[row_index],
            None if document is None else retain_document_value(document),
            evidence.absent,
        )
        if keep:
            object.__setattr__(self, "_bound", (row_index, predecessor))
        return predecessor

    def _successor(
        self, row_index: int, position: int, predecessor: PredecessorRow
    ) -> PlannedInsert:
        resolved = self.facts.resolved_successors[position]
        change = self.change
        return _successor_step(
            self.facts,
            resolved,
            self.authored_attributes,
            self.authored_value_objects,
            predecessor,
            effective=(
                change.effective_positions(self.evidence.rows[row_index])
                if change is not None and isinstance(resolved.state, ChangedState)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class _GroupOpenings:
    """The rows a group opens from the selected rows an admitted insertion
    opened when ``continued``, and from every other selected row when not."""

    segment: _MaterializedTemporalSegment
    continued: bool

    def __iter__(self) -> Iterator[OwnedEndpoint]:
        segment = self.segment
        continued = self.continued
        if continued and segment.layout is None:
            return
        for row_index in range(len(segment.evidence)):
            if segment.continues(row_index) is not continued:
                continue
            for position in segment.opened_positions(row_index):
                yield segment.opened_endpoint(row_index, position)


@dataclass(frozen=True, slots=True)
class _GroupRemovals:
    segment: _MaterializedTemporalSegment

    def __iter__(self) -> Iterator[OwnedEndpoint]:
        segment = self.segment
        layout = segment.layout
        if layout is None:
            return
        for row_index in range(len(segment.evidence)):
            if segment.removes(row_index):
                yield segment.endpoint(row_index)


type _GroupSegment = _MaterializedNonTemporalSegment | _MaterializedTemporalSegment


def _observed_close(
    facts: TemporalFacts,
    close: _SettledClose,
    row: Mapping[str, object],
    predecessor: PredecessorRow,
) -> PlannedClose:
    return _close_step(
        facts,
        close,
        key_values=key_tuple(facts.entity, close.key_attributes, row),
        observed_valid_end=(
            predecessor.cell(facts.shape.valid_time.end_attribute)
            if isinstance(facts.shape, Bitemporal)
            else None
        ),
        observed_gate_start=predecessor.cell(close.gate_start_attribute) if close.gated else None,
    )


def _close_step(
    facts: TemporalFacts,
    close: _SettledClose,
    *,
    key_values: tuple[object, ...],
    observed_valid_end: object | None,
    observed_gate_start: object | None,
) -> PlannedClose:
    """One temporal row's close, from the few observed cells it reads.

    ``observed_gate_start`` is read only for a gated close, and
    ``observed_valid_end`` only for a Bitemporal one.
    """
    return planned_close(
        facts,
        key_attributes=close.key_attributes,
        key_values=key_values,
        observed_valid_end=observed_valid_end,
        cause=close.cause,
        gate=(
            TemporalGate(
                start_attribute=close.gate_start_attribute,
                observed_start=observed_gate_start,
            )
            if close.gated
            else UNGATED
        ),
    )


def _successor_step(
    facts: TemporalFacts,
    resolved: ResolvedSuccessor,
    authored_attributes: Mapping[AttributeIdentity, PlannedValue],
    authored_value_objects: Mapping[ValueObjectIdentity, object],
    predecessor: PredecessorRow,
    *,
    effective: Iterable[int] | None = None,
) -> PlannedInsert:
    """One resolved topology successor of ``predecessor``, its Valid-Time
    bounds read from the predecessor's own cells where its topology names
    them."""
    window = resolved.window
    valid_start: object = None
    valid_end: object = None
    if window is not None:
        shape = facts.shape
        assert isinstance(shape, Bitemporal)  # only a Bitemporal topology windows a successor
        valid_start = bound_cell(window.start, shape.valid_time, predecessor)
        valid_end = bound_cell(window.end, shape.valid_time, predecessor)
    match resolved.state:
        case CarriedState():
            return successor_insert(facts, predecessor, valid_start, valid_end)
        case ChangedState():
            return successor_insert(
                facts,
                predecessor,
                valid_start,
                valid_end,
                authored_attributes,
                authored_value_objects,
                effective=effective,
            )
        case AuthoredState():  # pragma: no cover - an insert opens through `opening`
            raise AssertionError("an opening topology settles no successor of a predecessor")


def _observed_claim(item: ObservedKeyedWrite) -> Completion | None:
    """What an observed keyed write's unit spends: its claim, together with
    every twinned observation of the same state."""
    if not item.twins:
        return item.claim
    assert item.claim is not None  # twins meet only at their claim's own scope
    return Completions((item.claim, *item.twins))


def _target_claim(item: TargetKeyedWrite) -> Completion | None:
    """What a caller-conditioned write's unit spends: the observations of the
    observed writes composed into it, if any."""
    claims = item.claims
    if not claims:
        return None
    return claims[0] if len(claims) == 1 else Completions(claims)


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


def _non_temporal_step(
    facts: _NonTemporalFacts,
    addressed: _AddressedFacts,
    *,
    emission: _NonTemporalEmission,
    key_rows: Sequence[Mapping[str, object]],
    observed_version: int | None,
    affected_rows: AffectedRows,
) -> PlannedStep:
    """The rows ``key_rows`` addresses as the step ``emission`` settled.

    Pure in its settled values: everything it reads was decided by the two
    facts methods :class:`WriteSettlement` settles a mutation through and by the
    arm that settled the authored verb, so this reaches no clock, strategy,
    model, or facet — and re-reads no verb — and can therefore run either
    eagerly, while the instruction settles, or lazily, when a Materialized Write
    Group's segment is asked for a row.

    Cardinality is the caller's, and it is the one thing the two representations
    do not share: an addressed write hands every key it addresses to one call
    and receives ONE aggregate step, while a group hands one row per call and
    receives one independently gated step per row.
    """
    target = key_target(facts.entity, addressed.key_attributes, key_rows)
    concurrency = _non_temporal_concurrency(
        facts.version_attribute, observed_version, addressed.gated
    )
    match emission:
        case _Deletion():
            return PlannedDelete(
                entity=facts.entity.identity,
                target=target,
                concurrency=concurrency,
                affected_rows=affected_rows,
            )
        case _Revision(base_assignments, version):
            return PlannedUpdate(
                entity=facts.entity.identity,
                target=target,
                assignments=_versioned_assignments(base_assignments, version, observed_version),
                concurrency=concurrency,
                affected_rows=affected_rows,
            )


def _versioned_assignments(
    base: PlannedAssignments, version: _VersionOverlay | None, observed_version: int | None
) -> PlannedAssignments:
    """``base`` with the advanced version at the target's own version Attribute.

    The one version overlay, whichever representation an update arrived as. A
    versioned target advances in BOTH concurrency modes, which is why the new
    version is an assignment rather than a gate member, and the advance happens
    HERE — while an addressed write settles, and when a group's row is asked for
    — so no advanced version is ever stored.
    """
    if version is None or observed_version is None:
        return base
    return adopt_planned_assignments(
        {
            **base.attributes,
            version.attribute: version.arithmetic.advance(observed_version),
        },
        base.value_objects,
    )


def _addressed_assignments(
    facts: _NonTemporalFacts, addressed: _AddressedFacts, row: Mapping[str, object]
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


def _non_temporal_concurrency(
    version_attr: AttributeIdentity | None, observed_version: int | None, gated: bool
) -> NonTemporalConcurrency:
    """The settled concurrency decision one addressed non-temporal write
    carries, given the already-decided ``gated`` fact — the version analogue
    of a close's own gate (:func:`_close_step`).

    An unversioned target has nothing to gate on. A versioned one binds its
    observation as a gate when gated and records an explicit `Ungated`
    decision otherwise, whose shared read lock is what makes the write correct
    instead.
    """
    if version_attr is None or observed_version is None:
        return UNVERSIONED
    gate = VersionGate(observed_version=observed_version) if gated else UNGATED
    return Versioned(attribute=version_attr, gate=gate)


def _gate_axis(
    shape: TransactionTimeOnly | Bitemporal, gate_basis: TemporalDimension
) -> AsOfAxisMetadata:
    """The As-Of Axis a close's optimistic gate binds, by the topology's declared basis."""
    if gate_basis is TemporalDimension.TRANSACTION_TIME:
        return shape.transaction_time
    if isinstance(shape, Bitemporal):
        return shape.valid_time
    raise WritePlanningError(  # pragma: no cover - only a Bitemporal topology gates on Valid Time
        "a Transaction-Time-Only close has no Valid-Time axis to gate on"
    )


def reject_readless_document_many(
    entity: EntityMetadata, instruction: PreparedPredicateWrite
) -> None:
    """Refuse the readless document-array assignment shape before planning."""
    if not isinstance(entity.declared_layout, Document):
        return
    occurrences = {
        occurrence.identity.path[-1]: occurrence for occurrence in entity.declared_value_objects
    }
    for assignment in instruction.managed_assignments:
        if isinstance(assignment.member, AttributeMetadata):
            continue
        member = assignment.member.identity.path[-1]
        occurrence = occurrences.get(member)
        if occurrence is None:
            continue
        nested_many = assigned_many_path(occurrence, assignment.value)
        if occurrence.multiplicity is Multiplicity.MANY or nested_many is not None:
            path = member if nested_many is None else ".".join((member, *nested_many))
            raise WriteRejectedError(
                "predicate-write-readless-document-many-unsupported",
                f"{entity.identity.canonical}.{path}: a readless predicate write cannot "
                "assign a document-resident `many` occurrence",
            )


def assigned_many_path(occurrence: OccurrenceMetadata, authored: object) -> tuple[str, ...] | None:
    """Return the first authored nested ``many`` path in declaration order."""
    if not isinstance(authored, Mapping):
        return None
    authored_members = cast("Mapping[object, object]", authored)
    for nested in occurrence.value_objects:
        name = nested.identity.path[-1]
        if name not in authored_members:
            continue
        if nested.multiplicity is Multiplicity.MANY:
            return (name,)
        path = assigned_many_path(nested, authored_members[name])
        if path is not None:
            return (name, *path)
    return None


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
