"""Write Settlement: dependency-ordered intent as Planned Writes (m-unit-work).

:class:`WriteSettlement` owns everything after the Write Planner's four
rewriting stages. :meth:`WriteSettlement.settle` reads the complete ordered
sequence once and answers the Write Planning Result: it decides each surviving
write's target, topology, concurrency, and expected effects, decorates the
eagerly settled steps with provenance, packs adjacent eager runs into one
segment while a Materialized Write Group keeps its own compact one, and
collects the claims those surviving writes settled against.

It is model-scoped and owned by the planner prepared for one exact accepted
Metamodel: it reads that model's family facts through the
:class:`~parallax.core.unit_work.planner.FamilyFacts` reader the planner hands
it, holds the concurrency, temporal, and audit strategies the composition layer
wired, and observes publication not at all. Settlement accepts only PREPARED
input — every write it settles carries exact target Metadata — so it owns no
entity-spelling index; :func:`plan_temporal_close`, the `m-opt-lock` conflict
lane's standalone probe, is the one function here reached with a spelling, and
it resolves through the accepted model's own reference-position rule.

Imports run one way, ``write_planner`` to here, so nothing settlement decides is
reachable from a stage that runs before it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast

from parallax.core import inheritance
from parallax.core.base import INFINITY_LITERAL, TemporalBound
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    Document,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    TemporalDimension,
    ValueObjectIdentity,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.columns import (
    ColumnSlice,
    PredecessorColumns,
    freeze_retained_value,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTemporalBounds,
    PreparedWrite,
    WriteSurface,
    non_temporal_milestone_refusal,
    temporal_delete_refusal,
)
from parallax.core.unit_work.materialized import (
    MaterializedWriteGroup,
    ObservedKeyedWrite,
    TemporalColumns,
    VersionColumns,
)
from parallax.core.unit_work.observe import (
    PredecessorRow,
    TemporalObservation,
    WriteObservation,
)
from parallax.core.unit_work.plan import PlannedSteps, StepSegment, WritePlan, eager_segment
from parallax.core.unit_work.planned import (
    ANY_COUNT,
    INFINITY,
    MAX_PLUS_ONE,
    NEW_LINEAGE,
    SUPERSEDED,
    UNGATED,
    UNVERSIONED,
    AffectedRows,
    CloseCause,
    ExactCount,
    Finite,
    InsertEntry,
    KeyTarget,
    MilestoneTarget,
    NonTemporalConcurrency,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedUpdate,
    PlannedValue,
    SelfIncrement,
    Shortfall,
    TemporalConcurrency,
    TemporalGate,
    TemporalUpperBound,
    Versioned,
    VersionGate,
    shortfall_classification,
    shortfall_for,
)
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.core.unit_work.planner import FamilyFacts, family_facts
from parallax.core.unit_work.retain import RetainedObservation
from parallax.core.unit_work.strategy import (
    AuditStrategy,
    Concurrency,
    ConcurrencyStrategy,
    SubjectIdentity,
    TemporalStrategy,
    VersionArithmetic,
)
from parallax.core.unit_work.temporal import (
    ResolvedSuccessor,
    TemporalAxes,
    bind_successor,
    resolve_successors,
)
from parallax.core.unit_work.write_validate import WriteRejectedError

__all__ = [
    "OrderedWrite",
    "WritePlanningError",
    "WritePlanningResult",
    "WriteSettlement",
    "assigned_many_path",
    "plan_temporal_close",
    "reject_readless_document_many",
]

type OrderedWrite = PreparedWrite | ObservedKeyedWrite | MaterializedWriteGroup
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

# A scalar cell's recognized DB-computed marker kinds
# (`write-instruction.schema.json#/$defs/writeComputedMarker`), classified by
# SHAPE — a one-key mapping naming one of them. A Value Object occurrence never
# reaches this classification: its member resolves to a ValueObjectIdentity, so
# a marker-shaped document stays a document (m-value-object "Writing" marker
# disambiguation).
_MARKER_KEYS: Final[frozenset[str]] = frozenset({"computed", "increment"})


class WritePlanningError(ValueError):
    """A buffered write cannot be settled into a Planned Write — a caller
    wiring defect the planner refuses loudly rather than settling wrongly
    (e.g. a materializing predicate write that reached planning un-decomposed,
    or a row naming a member outside its Entity's family)."""


@dataclass(frozen=True, slots=True)
class WritePlanningResult:
    """One flush's finalized plan, and the claims its SURVIVING writes settled
    against.

    The two travel together because only settlement knows both: the plan says
    what will execute, and ``claims`` says which retained evidence that execution
    uses — the claims carried by the buffered writes that reached settlement, in
    settlement order. Work the earlier stages retired (folded into a pending
    insert, cancelled against one, eliminated as a known no-op) contributes none,
    which is what keeps a batch's surviving write from spending a claim no
    statement of it will carry (`m-unit-work` "A successful flush consumes").

    Each claim appears ONCE, by identity, at the position its first surviving
    carrier settled. Several writes of one flush may settle against one observed
    state — two edits of one source value are two writes holding one claim — and
    what consumption records is a fact about that observed state, not about a
    statement, so a repeated entry would spend one piece of evidence twice.

    Spending them is the caller's, and only after the executor returns: a plan
    that never ran spends nothing.
    """

    plan: WritePlan
    claims: tuple[RetainedObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class _SettledClose:
    """What closing the current milestone takes, settled once per temporal
    mutation whose topology closes one.

    One value rather than four independently optional fields on the facts: a
    topology either closes or does not, and each of these is settled exactly
    when it does — so a cause reaching emission without its gate basis is
    unconstructable rather than asserted against, and a mutation that opens a
    milestone without closing one settles no address and asks for no gate
    decision at all.
    """

    cause: CloseCause
    key_attributes: tuple[AttributeIdentity, ...]
    gate_start_attribute: AttributeIdentity
    gated: bool


@dataclass(frozen=True, slots=True)
class _TemporalFacts:
    """Every semantic fact one temporal mutation settles before any row of it
    is bound — decided once per keyed instruction and once per Materialized
    Write Group, by :meth:`WriteSettlement._temporal_facts` alone.

    Everything here is a value some producer emitted for THIS mutation: the
    facet's compiled view of the target, the axis names the family bounds its
    intervals with, the instant the clock resolved, what closing takes if the
    topology closes anything, and the successors the Temporal Strategy's
    topology described. No producer is among them, which is what lets a segment
    hold this by reference and still settle no decision at step access.
    """

    entity: EntityMetadata
    declaring_entity: EntityMetadata
    view: InheritanceEntityView
    axes: TemporalAxes
    instant: dt.datetime
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
    the family-fact reader that planner holds and the concurrency, temporal, and
    audit strategies the composition layer wired. :meth:`settle` is its entire
    surface: no caller settles one item, packs a segment, decorates a step, or
    collects a claim by hand.
    """

    __slots__ = ("_audit", "_concurrency", "_families", "_temporal")

    def __init__(
        self,
        families: FamilyFacts,
        *,
        concurrency: ConcurrencyStrategy,
        temporal: TemporalStrategy,
        audit: AuditStrategy,
    ) -> None:
        self._families = families
        self._concurrency = concurrency
        self._temporal = temporal
        self._audit = audit

    def settle(
        self,
        ordered_writes: Sequence[OrderedWrite],
        *,
        concurrency: Concurrency,
        subject_identity: SubjectIdentity,
        transaction_instant: TransactionInstant,
    ) -> WritePlanningResult:
        """The whole ordered sequence as one Write Planning Result.

        One traversal answers both halves, so they cannot disagree about which
        writes survived: an item the planner's earlier stages retired never
        reaches this loop, and therefore never contributes the evidence it was
        holding. Claim collection is identity-keyed, so two surviving carriers
        holding one claim answer it once.

        Packing is a property of adjacency, which is why the whole sequence
        crosses in one call: a run of eagerly settled steps stays one eager
        segment, and a Materialized Write Group always occupies its own. A
        group's every group-wide semantic fact — temporal topology, the
        gate/concurrency decision, the affected-row policy, the assignment
        shape, and the resolved instant if the group needs one — is decided
        into that segment before this returns; the segment, and the ``WritePlan``
        it becomes part of, retain no group, concurrency mode, Transaction
        Instant, or strategy object. Only the PER-ROW data stays as the group's
        own compact columns, and a row's ``PlannedWrite`` is rebuilt from those
        columns and the already-settled facts one at a time, on demand, so a
        large materialized run never forces a parallel ``PlannedWrite``-per-row
        object graph merely by being planned.

        Provenance decoration reaches the eagerly settled steps only, before
        they are packed and after each one's topology is settled; a Materialized
        Write Group's rows stay as its segment produced them.

        ``subject_identity`` is passed to the audit port and never inspected
        here; ``transaction_instant`` is threaded unevaluated until a surviving
        temporal write needs it.
        """
        segments: list[StepSegment] = []
        pending: list[PlannedStep] = []
        claims: dict[RetainedObservation, None] = {}

        def flush_pending() -> None:
            if pending:
                segments.append(eager_segment(tuple(pending)))
                pending.clear()

        for item in ordered_writes:
            if isinstance(item, MaterializedWriteGroup):
                flush_pending()
                segments.append(self._settle_group(item, concurrency, transaction_instant))
                continue
            instruction, observation = (
                (item.instruction, item.observation)
                if isinstance(item, ObservedKeyedWrite)
                else (item, None)
            )
            for step in self._settle(instruction, observation, concurrency, transaction_instant):
                pending.append(
                    self._audit.decorate(
                        step,
                        subject_identity=subject_identity,
                        transaction_instant=transaction_instant,
                    )
                )
            if isinstance(item, ObservedKeyedWrite) and item.claim is not None:
                claims.setdefault(item.claim, None)
        flush_pending()
        return WritePlanningResult(WritePlan(steps=PlannedSteps(tuple(segments))), tuple(claims))

    # ----------------------------------------------------------------- #
    # Stages 5, 6, 7: validate the observation the item arrived carrying, #
    # resolve the Transaction Instant lazily, and expand temporal          #
    # topology in place. Stage 2 ran before settlement was reached, so a   #
    # known no-op instruction and a no-op ROW of one are both already      #
    # gone and neither is ever settled.                                    #
    # ----------------------------------------------------------------- #
    def _settle(
        self,
        instruction: PreparedWrite,
        observation: WriteObservation | None,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
    ) -> tuple[PlannedStep, ...]:
        if isinstance(instruction, PreparedPredicateWrite):
            return self._settle_predicate(instruction)
        entity = instruction.target
        declaring_entity = self._families.declaring(entity)
        if declaring_entity.declared_as_of_axes:
            return self._settle_temporal(
                entity,
                declaring_entity,
                instruction,
                observation,
                concurrency,
                tx_instant,
            )
        facts = self._non_temporal_facts(
            entity, declaring_entity, instruction.mutation, surface="keyed"
        )
        if instruction.mutation == "insert":
            return (self._settle_insert(facts, instruction),)
        addressed = self._addressed_facts(facts, declaring_entity, concurrency)
        observed_version = self._observed_version(
            entity, instruction, facts.version_attribute, observation
        )
        return (
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
        )

    def _settle_predicate(self, instruction: PreparedPredicateWrite) -> tuple[PlannedStep, ...]:
        """One readless predicate-selected write as its single step.

        The refusals live here, on the semantic side, because they answer what
        a write MEANS rather than how it reads: an inheritance-family target
        has no per-object write to select (`m-inheritance`), and a versioned
        or temporal target has no readless template at all — it materializes
        to keyed writes at buffer time, so reaching this stage is a
        caller wiring defect. Both guards are total rather than upstream-only:
        settlement judges the prepared carrier it is handed and never which door
        prepared it, so a shape buffering would have refused or materialized is
        refused here rather than settled.
        """
        entity = instruction.selection.target
        inheritance.reject_predicate_write(entity)
        declaring_entity = self._families.declaring(entity)
        if (
            declaring_entity.declared_as_of_axes
            or self._concurrency.version_attribute(declaring_entity) is not None
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
        view = self._families.view(entity)
        assignment_row = {
            _assignment_member(assignment.attr): assignment.value
            for assignment in instruction.managed_assignments
        }
        return (
            PlannedUpdate(
                entity=entity.identity,
                target=target,
                assignments=_assignments(entity, view, assignment_row),
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
            InsertEntry(
                row=_planned_row(facts.entity, facts.view, row, version), origin=NEW_LINEAGE
            )
            for row in instruction.rows
        )
        return PlannedInsert(entity=facts.entity.identity, entries=entries)

    def _non_temporal_facts(
        self,
        entity: EntityMetadata,
        declaring_entity: EntityMetadata,
        mutation: str,
        *,
        surface: WriteSurface,
    ) -> _NonTemporalFacts:
        """What one non-temporal mutation settles about its target, before a
        row is in hand and whatever the verb does to it.

        The sole site for each of these decisions, whichever representation the
        mutation arrived as: whether the verb has a milestone to act on at all,
        which members the family makes applicable, and which Attribute (if any)
        carries the optimistic version. An eagerly settled instruction and a
        Materialized Write Group therefore cannot answer any of them
        differently. What only a write against EXISTING rows settles belongs to
        :meth:`_addressed_facts` instead.

        ``surface`` is what the milestone-verb refusal words itself with, and it
        is the one input that genuinely differs between an addressed write and a
        resolved predicate.
        """
        _reject_milestone_verb(entity, mutation, surface)
        return _NonTemporalFacts(
            entity=entity,
            view=self._families.view(entity),
            version_attribute=self._concurrency.version_attribute(declaring_entity),
        )

    def _addressed_facts(
        self,
        facts: _NonTemporalFacts,
        declaring_entity: EntityMetadata,
        concurrency: Concurrency,
    ) -> _AddressedFacts:
        """What one non-temporal mutation against EXISTING rows settles before
        a row is in hand.

        The sole site for each of these decisions, whichever representation the
        mutation arrived as: what the target's effective primary key is,
        whether the write gates, and how a shortfall against it classifies. An
        insert never reaches here, so it settles no address it does not use.
        """
        gated = self._concurrency.gates(concurrency, declaring_entity)
        return _AddressedFacts(
            key_attributes=tuple(a.identity for a in self._families.primary_key(facts.entity)),
            gated=gated,
            shortfall=shortfall_classification(
                observing=facts.version_attribute is not None, gated=gated
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
        declaring_entity: EntityMetadata,
        instruction: PreparedKeyedWrite,
        observation: WriteObservation | None,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
    ) -> tuple[PlannedStep, ...]:
        """One temporal mutation as its close and its successors, in that order.

        Each row of a milestone chain opens its own successors, so a temporal
        keyed instruction carries exactly one row (`m-unit-work`) and reaching
        here with several is a caller wiring defect.
        """
        if len(instruction.rows) != 1:
            raise WritePlanningError(
                f"multi-row temporal {instruction.mutation!r} on {entity.identity.name!r} "
                f"({len(instruction.rows)} rows): a temporal keyed instruction carries exactly "
                "one row (m-unit-work) — each row closes its own milestone and chains its own "
                "successors, and the set-based batch collapse never applies to a temporal "
                "entity (m-batch-write)"
            )
        observed = observation if isinstance(observation, TemporalObservation) else None
        facts = self._temporal_facts(
            entity,
            declaring_entity,
            instruction.mutation,
            instruction.bounds,
            surface="keyed",
            observed=observed is not None,
            concurrency=concurrency,
            tx_instant=tx_instant,
        )
        row = instruction.rows[0]
        return _temporal_steps(
            facts,
            key_row=row,
            authored=row,
            predecessor=None if observed is None else observed.predecessor,
        )

    def _temporal_facts(
        self,
        entity: EntityMetadata,
        declaring_entity: EntityMetadata,
        mutation: str,
        bounds: PreparedTemporalBounds,
        *,
        surface: WriteSurface,
        observed: bool,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
    ) -> _TemporalFacts:
        """Everything one temporal mutation settles before a row is in hand.

        The sole site for each of these decisions, whichever representation the
        mutation arrived as: what the family's As-Of Axes are named, whether
        the verb has a milestone to act on at all, which topology the Temporal
        Facet describes it with, what closing takes if that topology closes
        anything, which successors exist and what each one's bound expression
        and represented-state kind is, and the one instant the attempt stamps.
        An eagerly settled instruction and a Materialized Write Group therefore
        cannot answer any of them differently.

        A topology that closes nothing settles no close: it addresses no
        existing row and gates against none, so neither the target's primary
        key nor the Concurrency Strategy's gate decision is a fact about it.

        ``observed`` says whether a Temporal Observation reached this mutation;
        a topology that closes has nothing to address, gate on, or carry state
        forward from without one, so the refusal precedes every consultation
        after it — the clock included, which is what keeps a refused write from
        capturing the attempt's instant.
        """
        _reject_temporal_delete(entity, mutation, surface)
        topology = self._temporal.topology(declaring_entity, mutation)
        if topology.closure is not None and not observed:
            raise WritePlanningError(
                f"{entity.identity.name!r}: a temporal {mutation!r} closes the "
                "current milestone, and every close requires the Temporal Observation it "
                "addresses, gates on, and carries state forward from (m-unit-work; m-opt-lock)"
            )
        valid_axis = declaring_entity.as_of_axis(TemporalDimension.VALID_TIME)
        tx_axis = _tx_time_axis(declaring_entity)
        close: _SettledClose | None = None
        if topology.closure is not None:
            close = _SettledClose(
                cause=topology.closure.cause,
                key_attributes=tuple(a.identity for a in self._families.primary_key(entity)),
                gate_start_attribute=_gate_axis(
                    declaring_entity, topology.closure.gate_basis
                ).start_attribute,
                gated=self._concurrency.gates(concurrency, declaring_entity),
            )
        return _TemporalFacts(
            entity=entity,
            declaring_entity=declaring_entity,
            view=self._families.view(entity),
            axes=TemporalAxes(
                transaction_start=tx_axis.start_attribute.name,
                transaction_end=tx_axis.end_attribute.name,
                valid_start=None if valid_axis is None else valid_axis.start_attribute.name,
                valid_end=None if valid_axis is None else valid_axis.end_attribute.name,
            ),
            # Reaching a surviving temporal mutation is what makes the attempt
            # capture its instant; the close's new Transaction-Time end and
            # every successor's fresh start derive from that one value.
            instant=tx_instant.value(),
            close=close,
            resolved_successors=resolve_successors(
                topology.successors, valid_from=bounds.valid_from, until=bounds.until
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

    # ----------------------------------------------------------------- #
    # A Materialized Write Group's compact rows, settled ONCE HERE,       #
    # never re-derived at step access.                                    #
    # ----------------------------------------------------------------- #
    def _settle_group(
        self,
        group: MaterializedWriteGroup,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
    ) -> StepSegment:
        """One Materialized Write Group as one already-settled segment.

        Every group-wide semantic fact — the temporal topology, the gate and
        concurrency decision, the affected-row policy, the assignment shape,
        and (only when the surviving group needs one) the concrete Transaction
        Instant literal — is decided HERE, once, before this method returns.
        The returned segment carries none of the group, the concurrency mode,
        the Transaction Instant, or a strategy object: its ``step`` rebuilds
        one row's Planned Write from these already-decided facts and the
        group's own compact columns alone.
        """
        entity = group.mutation.selection.target
        declaring_entity = self._families.declaring(entity)
        if declaring_entity.declared_as_of_axes:
            return self._settle_temporal_group(
                group, entity, declaring_entity, concurrency, tx_instant
            )
        return self._settle_versioned_group(group, entity, declaring_entity, concurrency)

    def _settle_versioned_group(
        self,
        group: MaterializedWriteGroup,
        entity: EntityMetadata,
        declaring_entity: EntityMetadata,
        concurrency: Concurrency,
    ) -> StepSegment:
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

        A group's observation columns are not optional, so an entity this
        group's own Concurrency Strategy does not recognize as versioned is
        refused here rather than settled Unversioned with its columns dropped —
        the same entitlement rule an ordinary keyed write meets in
        :meth:`_observed_version`.
        """
        assert isinstance(group.observations, VersionColumns)
        facts = self._non_temporal_facts(
            entity, declaring_entity, group.mutation.mutation, surface="predicate"
        )
        addressed = self._addressed_facts(facts, declaring_entity, concurrency)
        mutation = group.mutation.mutation
        if facts.version_attribute is None:
            _require_unobserved(entity, mutation, group.observations)
        emission: _NonTemporalEmission = _DELETION
        if mutation != "delete":
            assignment_row = {
                _assignment_member(assignment.attr): assignment.value
                for assignment in group.mutation.managed_assignments
            }
            if (
                facts.version_attribute is not None
                and facts.version_attribute.name in assignment_row
            ):
                self._concurrency.reject_authored_version(entity.identity, facts.version_attribute)
            emission = _Revision(
                _assignments(entity, facts.view, assignment_row),
                self._version_overlay(facts.version_attribute),
            )
        return _MaterializedNonTemporalSegment(
            facts=facts,
            addressed=addressed,
            key_attribute_names=group.key_attributes,
            key_columns=group.key_columns,
            versions=group.observations.versions,
            emission=emission,
            # One resolved row is one independently gated step, so every row of
            # the group shares this one expectation rather than building its own.
            affected_rows=ExactCount(expected=1, on_shortfall=addressed.shortfall),
        )

    def _settle_temporal_group(
        self,
        group: MaterializedWriteGroup,
        entity: EntityMetadata,
        declaring_entity: EntityMetadata,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
    ) -> StepSegment:
        """A temporal Materialized Write Group's segment.

        The group's facts are settled through the same
        :meth:`_temporal_facts` an eagerly settled temporal instruction crosses
        — the only clock consultation this group's whole flush makes, however
        many rows it resolved — and the segment holds them by reference. Only a
        row's own predecessor and key values remain for
        :meth:`_MaterializedTemporalSegment.step` to bind, through the same
        emission :meth:`_settle_temporal` returns from.
        """
        assert isinstance(group.observations, TemporalColumns)
        facts = self._temporal_facts(
            entity,
            declaring_entity,
            group.mutation.mutation,
            group.mutation.bounds,
            surface="predicate",
            observed=True,
            concurrency=concurrency,
            tx_instant=tx_instant,
        )
        closes = 0 if facts.close is None else 1
        return _MaterializedTemporalSegment(
            facts=facts,
            key_attribute_names=group.key_attributes,
            key_columns=group.key_columns,
            predecessors=group.observations.predecessors,
            assignment_row={
                _assignment_member(assignment.attr): assignment.value
                for assignment in group.mutation.managed_assignments
            },
            steps_per_row=closes + len(facts.resolved_successors),
        )


@dataclass(frozen=True, slots=True)
class _MaterializedNonTemporalSegment:
    """A versioned Materialized Write Group's rows: one Planned Update or
    Planned Delete per resolved row, assembled on demand from already-decided,
    group-wide facts and the group's own compact columns alone.

    Every semantic decision the group's authored mutation settles — the
    applicable members and version source (``facts``), the family-effective
    primary key, the gate decision and how a shortfall classifies
    (``addressed``), and the assignments and version arithmetic an update lays
    over a row (``emission``) — is resolved once, when the segment is built, and
    reached here through those references. ``step`` only binds one row's own key
    values and observed version into that already-decided shape, through the
    same :func:`_non_temporal_step` an eagerly settled keyed write emits from.

    ``versions`` is the group's own observation column, held by reference: the
    advance is an addition performed at step access, so a row's new version is
    never a second column sized by the resolved row count.

    No group, concurrency mode, Transaction Instant, or strategy object is
    reachable here — every value :meth:`step` reads is either a settled fact or
    an aligned column lookup by row index — and two calls for the same index
    return equal but distinct objects, never a shared mutable flyweight.
    """

    facts: _NonTemporalFacts
    addressed: _AddressedFacts
    key_attribute_names: tuple[str, ...]
    key_columns: tuple[ColumnSlice[object], ...]
    versions: ColumnSlice[int]
    emission: _NonTemporalEmission
    affected_rows: AffectedRows

    def __len__(self) -> int:
        return len(self.versions)

    def step(self, index: int) -> PlannedStep:
        key_row = dict(
            zip(
                self.key_attribute_names,
                (column[index] for column in self.key_columns),
                strict=True,
            )
        )
        return _non_temporal_step(
            self.facts,
            self.addressed,
            emission=self.emission,
            key_rows=(key_row,),
            observed_version=self.versions[index],
            affected_rows=self.affected_rows,
        )


@dataclass(frozen=True, slots=True)
class _MaterializedTemporalSegment:
    """A temporal Materialized Write Group's rows: one close plus its
    successors per resolved row, assembled on demand from already-decided,
    group-wide facts and the group's own compact columns alone.

    Every semantic decision the group's authored mutation settles — which
    successors exist, each one's represented-state kind, which Valid-Time
    bound expression applies, the close's cause, and its gate basis's
    Attribute — is resolved once, when the segment is built
    (:meth:`WriteSettlement._temporal_facts`), and reached here through the one
    ``facts`` reference. ``step`` only binds one row's own predecessor and key
    values into that already-decided shape, through the same
    :func:`_temporal_steps` an eagerly settled temporal instruction emits from;
    it never re-derives a decision a strategy already made.

    ``steps_per_row`` is invariant across the group — every row shares the
    same authored mutation and therefore the same topology — so a flat step
    index maps to (row, sub-step) by simple division, and nothing here is
    cached between accesses.
    """

    facts: _TemporalFacts
    key_attribute_names: tuple[str, ...]
    key_columns: tuple[ColumnSlice[object], ...]
    predecessors: PredecessorColumns
    assignment_row: Mapping[str, object]
    steps_per_row: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assignment_row",
            MappingProxyType(
                {name: freeze_retained_value(value) for name, value in self.assignment_row.items()}
            ),
        )

    def __len__(self) -> int:
        return len(self.key_columns[0]) * self.steps_per_row

    def step(self, index: int) -> PlannedStep:
        row, sub_step = divmod(index, self.steps_per_row)
        key_row = dict(
            zip(
                self.key_attribute_names,
                (column[row] for column in self.key_columns),
                strict=True,
            )
        )
        return _temporal_steps(
            self.facts,
            key_row=key_row,
            authored={**key_row, **self.assignment_row},
            predecessor=self.predecessors.row(row),
        )[sub_step]


def _temporal_steps(
    facts: _TemporalFacts,
    *,
    key_row: Mapping[str, object],
    authored: Mapping[str, object],
    predecessor: PredecessorRow | None,
) -> tuple[PlannedStep, ...]:
    """One temporal row's close and its successors, in that order.

    Pure in ``facts``: everything it reads was decided by
    :meth:`WriteSettlement._temporal_facts`, so this reaches no clock,
    strategy, model, or facet and can therefore run either eagerly, while the
    instruction settles, or lazily, when a Materialized Write Group's segment
    is asked for a row. It is also the sole composition of the two temporal
    primitives, :func:`~parallax.core.unit_work.temporal.resolve_successors`
    (already run, into ``facts``) and
    :func:`~parallax.core.unit_work.temporal.bind_successor`.

    ``key_row`` addresses the close; ``authored`` is the represented state a
    changed or authored successor overlays. The eager arm passes the
    instruction's one row as both — the address is projected out of it — while
    a group passes its own key columns and the group-wide assignment overlay
    on top of them.
    """
    steps: list[PlannedStep] = []
    close = facts.close
    if close is not None:
        assert predecessor is not None  # a closing topology refuses an unobserved mutation
        steps.append(
            _close(
                facts.entity,
                facts.declaring_entity,
                key_attributes=close.key_attributes,
                identity=key_row,
                observed_valid_end=(
                    None
                    if facts.axes.valid_end is None
                    else predecessor.member(facts.axes.valid_end)
                ),
                cause=close.cause,
                gate=_temporal_gate(close.gate_start_attribute, predecessor, close.gated),
                instant=facts.instant,
            )
        )
    steps.extend(
        PlannedInsert(
            entity=facts.entity.identity,
            entries=(
                InsertEntry(
                    row=_planned_row(facts.entity, facts.view, successor.members, None),
                    origin=successor.origin,
                ),
            ),
        )
        for successor in (
            bind_successor(
                resolved,
                facts.axes,
                transaction_instant=facts.instant,
                authored=authored,
                predecessor=predecessor,
            )
            for resolved in facts.resolved_successors
        )
    )
    return tuple(steps)


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
    target = _key_target(facts.entity, addressed.key_attributes, key_rows)
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
    return PlannedAssignments(
        attributes={
            **base.attributes,
            version.attribute: version.arithmetic.advance(observed_version),
        },
        value_objects=base.value_objects,
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
    return _assignments(
        facts.entity,
        facts.view,
        {name: value for name, value in row.items() if name not in key_names},
    )


def _non_temporal_concurrency(
    version_attr: AttributeIdentity | None, observed_version: int | None, gated: bool
) -> NonTemporalConcurrency:
    """The settled concurrency decision one addressed non-temporal write
    carries, given the already-decided ``gated`` fact — the version analogue
    of :func:`_temporal_gate`.

    An unversioned target has nothing to gate on. A versioned one binds its
    observation as a gate when gated and records an explicit `Ungated`
    decision otherwise, whose shared read lock is what makes the write correct
    instead.
    """
    if version_attr is None or observed_version is None:
        return UNVERSIONED
    if not gated:
        return Versioned(gate=UNGATED)
    return Versioned(gate=VersionGate(attribute=version_attr, observed_version=observed_version))


def _temporal_gate(
    start_attribute: AttributeIdentity,
    predecessor: PredecessorRow,
    gated: bool,
) -> TemporalConcurrency:
    """The settled gate decision one close carries, given the already-decided
    ``gated`` fact and the gate basis's already-resolved Attribute.

    Optimistic mode binds the observed start of the axis the facet names as
    its gate basis — the version analogue for an entity carrying no version
    column. Locking mode records the explicit ungated decision, whose shared
    read lock is what makes the close correct instead.
    """
    if not gated:
        return UNGATED
    return TemporalGate(
        start_attribute=start_attribute,
        observed_start=predecessor.member(start_attribute.name),
    )


def _planned_row(
    entity: EntityMetadata,
    view: InheritanceEntityView,
    row: Mapping[str, object],
    version: tuple[AttributeIdentity, int] | None,
) -> PlannedRow:
    """One write row as its finalized semantic contents.

    A versioned Entity's row derives the INITIAL version at its own Attribute
    (`m-opt-lock`), ignoring any value the row carries — the version is
    framework-owned end to end, and the initial value the caller
    already resolved is a constant rather than an observation. ``version`` is
    absent for a temporal successor row, which carries no version column.
    """
    attributes, value_objects = _resolve(entity, view, row, context="insert")
    if version is not None:
        attribute, initial_value = version
        attributes[attribute] = initial_value
    return PlannedRow(attributes=attributes, value_objects=value_objects)


def _assignments(
    entity: EntityMetadata,
    view: InheritanceEntityView,
    row: Mapping[str, object],
) -> PlannedAssignments:
    attributes, value_objects = _resolve(entity, view, row, context="update")
    return PlannedAssignments(attributes=attributes, value_objects=value_objects)


def _resolve(
    entity: EntityMetadata,
    view: InheritanceEntityView,
    row: Mapping[str, object],
    *,
    context: str,
) -> tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]:
    """``row``'s cells under their resolved member identities, read off the
    family-effective indexes the Inheritance Facet compiled once.

    A Value Object occurrence is consulted FIRST, so an occurrence sharing a
    name with an applicable Attribute still claims the cell.
    """
    attributes: dict[AttributeIdentity, PlannedValue] = {}
    value_objects: dict[ValueObjectIdentity, object] = {}
    for name, value in row.items():
        occurrence = view.applicable_value_object(name)
        if occurrence is not None:
            value_objects[occurrence.identity] = value
            continue
        attribute = view.applicable_attribute(name)
        if attribute is None:
            raise WritePlanningError(
                f"{entity.identity.name!r}: write row names {name!r}, which is not a member "
                "of the Entity's family"
            )
        attributes[attribute.identity] = _cell(entity, name, value, context)
    return attributes, value_objects


def plan_temporal_close(
    identity: Mapping[str, object],
    entity_name: str,
    model: Metamodel,
    concurrency: Concurrency,
    concurrency_strategy: ConcurrencyStrategy,
    tx_instant: TransactionInstant,
    observed_tx_start: object | None,
    observed_valid_end: object | None = None,
) -> PlannedClose:
    """A STANDALONE temporal milestone close — the `m-opt-lock` conflict lane's
    own probe.

    A conflict probe runs only the close, under an address and a gate its
    caller names outright rather than reads off an observation, so it settles
    one here directly rather than through a full planning pipeline. The
    pipeline reaches this shape only for a Transaction-Time-Only
    ``terminate``, whose topology chains nothing; every Bitemporal closure
    chains at least the head rectangle.
    ``identity`` is the row the address keys on, ``observed_valid_end``
    completes that address on a Bitemporal target, and ``observed_tx_start``
    is the gate candidate; a probe names all three explicitly rather than
    reading them from a tracked milestone. The cause it records is
    supersession — what a real mutation's own close performs, and whose
    successors the probe deliberately does not run.

    Structurally separate from :meth:`WriteSettlement.settle`, which stays the
    only way an ordered flush becomes Planned Writes: this is one atomic close
    settlement with no coalescing, batching, or ordering to do, callable
    without a full flush. ``concurrency_strategy`` is the SAME adapter a
    production Write Planner was constructed with, so the two can never
    disagree about a gate decision.
    """
    families = family_facts(model)
    entity = _require_entity(model, entity_name)
    declaring_entity = families.declaring(entity)
    key_attributes = tuple(a.identity for a in families.primary_key(entity))
    _refuse_unaddressing_identity(entity, key_attributes, identity)
    gate: TemporalConcurrency = UNGATED
    if observed_tx_start is not None and concurrency_strategy.gates(concurrency, declaring_entity):
        gate = TemporalGate(
            start_attribute=_tx_time_axis(declaring_entity).start_attribute,
            observed_start=observed_tx_start,
        )
    return _close(
        entity,
        declaring_entity,
        key_attributes=key_attributes,
        identity=identity,
        observed_valid_end=observed_valid_end,
        cause=SUPERSEDED,
        gate=gate,
        instant=tx_instant.value(),
    )


def _refuse_unaddressing_identity(
    entity: EntityMetadata,
    key_attributes: tuple[AttributeIdentity, ...],
    identity: Mapping[str, object],
) -> None:
    """Refuse a standalone close's ``identity`` cell that addresses nothing.

    Here ``identity`` IS the address, unlike the pipeline's own close, whose
    ``identity`` is the full durable row the surrounding mutation revises and out
    of which the address is projected. A close ends a milestone's currency and
    revises no represented value, so a cell naming anything but a primary-key
    member is a value its caller believes this close binds and it does not.
    Projecting the key and dropping the rest silently would let a caller's own
    mistranslation reach the database as a well-formed statement.
    """
    addressing = {attribute.name for attribute in key_attributes}
    unaddressing = sorted(name for name in identity if name not in addressing)
    if unaddressing:
        named = ", ".join(repr(name) for name in unaddressing)
        raise WritePlanningError(
            f"{entity.identity.name!r}: a standalone temporal close is addressed by its "
            f"primary key alone, and this one's identity row also names {named} — a close "
            "revises no represented value, so nothing else the row carries would be bound"
        )


def _close(
    entity: EntityMetadata,
    declaring_entity: EntityMetadata,
    *,
    key_attributes: tuple[AttributeIdentity, ...],
    identity: Mapping[str, object],
    observed_valid_end: object | None,
    cause: CloseCause,
    gate: TemporalConcurrency,
    instant: dt.datetime,
) -> PlannedClose:
    """One settled close of the current milestone ``identity`` addresses.

    Its assignments carry the Transaction-Time end alone — a close ends a
    milestone's currency and revises no represented value — and it expects
    exactly one row in every mode: a close reaching none would otherwise chain
    a duplicate or an orphaned current row, so the shortfall is an outcome
    rather than a silent success.
    """
    return PlannedClose(
        entity=entity.identity,
        target=MilestoneTarget(
            key_attributes=key_attributes,
            key_values=_key_tuple(entity, key_attributes, identity),
            end_attributes=tuple(axis.end_attribute for axis in _as_of_axes(declaring_entity)),
            end_values=_end_values(entity, declaring_entity, observed_valid_end),
        ),
        assignments=PlannedAssignments(
            attributes={_tx_time_axis(declaring_entity).end_attribute: instant}
        ),
        cause=cause,
        concurrency=gate,
        affected_rows=ExactCount(expected=1, on_shortfall=shortfall_for(gate)),
    )


def _end_values(
    entity: EntityMetadata, declaring_entity: EntityMetadata, observed_valid_end: object | None
) -> tuple[TemporalUpperBound, ...]:
    """One exclusive upper bound per As-Of Axis, in canonical order.

    Transaction Time is invariantly `Infinity`, which is what keeps an
    operational close on a row still current. Valid Time is whatever the
    observed predecessor carries — `Infinity` for a rectangle running to the
    open bound, and a finite instant for a bounded one a prior split left
    behind, so binding a constant on both axes would silently miss every
    bounded sibling.
    """
    values: list[TemporalUpperBound] = []
    for axis in _as_of_axes(declaring_entity):
        if axis.dimension is TemporalDimension.TRANSACTION_TIME:
            values.append(INFINITY)
        elif observed_valid_end is None:
            raise WritePlanningError(
                f"bitemporal close on {entity.identity.name!r}: no observed Valid-Time end "
                "supplied — a Bitemporal milestone address needs one exclusive upper bound "
                "per As-Of Axis (m-bitemp-write 'Address and gate are separate')"
            )
        elif observed_valid_end == INFINITY_LITERAL or observed_valid_end is TemporalBound.INFINITY:
            values.append(INFINITY)
        else:
            values.append(Finite(instant=observed_valid_end))
    return tuple(values)


def _as_of_axes(declaring_entity: EntityMetadata) -> tuple[AsOfAxisMetadata, ...]:
    """``declaring_entity``'s declared As-Of Axes in canonical order."""
    valid_axis = declaring_entity.as_of_axis(TemporalDimension.VALID_TIME)
    tx_axis = _tx_time_axis(declaring_entity)
    return (tx_axis,) if valid_axis is None else (valid_axis, tx_axis)


def _gate_axis(declaring_entity: EntityMetadata, gate_basis: TemporalDimension) -> AsOfAxisMetadata:
    """The As-Of Axis a close's optimistic gate binds, by the topology's declared basis."""
    return next(axis for axis in _as_of_axes(declaring_entity) if axis.dimension is gate_basis)


def _tx_time_axis(declaring_entity: EntityMetadata) -> AsOfAxisMetadata:
    axis = declaring_entity.as_of_axis(TemporalDimension.TRANSACTION_TIME)
    if axis is None:  # pragma: no cover - callers guard on a temporal declaring Entity
        raise WritePlanningError(f"{declaring_entity.identity.canonical}: no Transaction-Time axis")
    return axis


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
        member = _assignment_member(assignment.attr)
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


def assigned_many_path(occurrence: ValueObjectMetadata, authored: object) -> tuple[str, ...] | None:
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
        path = assigned_many_path(cast("ValueObjectMetadata", nested), authored_members[name])
        if path is not None:
            return (name, *path)
    return None


def _require_entity(model: Metamodel, spelling: str) -> EntityMetadata:
    entity = entity_by_name(model, spelling)
    if entity is None:
        raise WritePlanningError(f"{spelling!r}: not a declared Entity of the accepted Metamodel")
    return entity


def _key_target(
    entity: EntityMetadata,
    key_attributes: tuple[AttributeIdentity, ...],
    rows: Sequence[Mapping[str, object]],
) -> KeyTarget:
    """The rows an addressed keyed write selects, one aligned value tuple each."""
    return KeyTarget(
        key_attributes=key_attributes,
        key_values=tuple(_key_tuple(entity, key_attributes, row) for row in rows),
    )


def _key_tuple(
    entity: EntityMetadata,
    key_attributes: tuple[AttributeIdentity, ...],
    row: Mapping[str, object],
) -> tuple[object, ...]:
    """One addressed row's aligned primary-key values.

    A row that omits a key member addresses nothing, so it is refused here
    rather than settled into a target with a missing value.
    """
    values: list[object] = []
    for attribute in key_attributes:
        if attribute.name not in row:
            raise WritePlanningError(
                f"{entity.identity.name!r}: an addressed write row omits the primary-key "
                f"member {attribute.name!r}, so it selects no row"
            )
        values.append(row[attribute.name])
    return tuple(values)


def _cell(entity: EntityMetadata, name: str, value: object, context: str) -> PlannedValue:
    """``value`` as a planned cell: an ordinary literal, or the closed
    generated-value expression its DB-computed marker names.

    Each `m-pk-gen` allocation is legal only where the statement that renders
    it can express it: `max` folds into the row an insert opens, and the
    registry advance reads the very row an update revises. Reaching the other
    position names no allocation this target supports, and is refused here
    rather than settled wrongly.
    """
    marker = _marker(value)
    if marker is None:
        return value
    kind, payload = marker
    if kind == "computed" and context == "insert":
        if payload != "maxPlusOne":
            raise WritePlanningError(
                f"unsupported DB-computed marker on {entity.identity.name!r}.{name}: "
                f"{payload!r} is not a recognized `computed` strategy (m-pk-gen)"
            )
        return MAX_PLUS_ONE
    if kind == "increment" and context == "update":
        return SelfIncrement(amount=cast("int", payload))
    raise WritePlanningError(
        f"unsupported DB-computed marker on {entity.identity.name!r}.{name}: a {kind!r} "
        f"marker is not recognized for {context} planning"
    )


def _marker(value: object) -> tuple[str, object] | None:
    """``value``'s ``(marker key, payload)`` when it is shaped as a DB-computed
    marker, else ``None``. A differently shaped mapping is an ordinary literal."""
    if not isinstance(value, Mapping):
        return None
    marker = cast("Mapping[str, object]", value)
    if len(marker) != 1:
        return None
    key = next(iter(marker))
    return (key, marker[key]) if key in _MARKER_KEYS else None


def _assignment_member(attr: str) -> str:
    """The declared member name of an assignment's ``Class.member`` reference."""
    _, _, member = attr.rpartition(".")
    return member


def _reject_temporal_delete(entity: EntityMetadata, mutation: str, surface: WriteSurface) -> None:
    """Refuse ``mutation`` when ``entity``'s family milestones the rows it would
    physically remove.

    Reached only once the caller has established that the target DOES derive an
    As-Of Axis — the converse of :func:`_reject_milestone_verb`'s quadrant, and
    the last structural refusal before the temporal facet is asked for a
    topology it owns none for. Refusing here rather than there is what lets the
    caller hear which verb their target does take: a facet answers a mutation
    token alone and carries neither the target's name nor the surface the call
    arrived on.
    """
    refusal = temporal_delete_refusal(entity.identity.name, mutation, surface=surface)
    if refusal is not None:
        raise WritePlanningError(refusal)


def _reject_milestone_verb(entity: EntityMetadata, mutation: str, surface: WriteSurface) -> None:
    """Refuse ``mutation`` when ``entity``'s family has no milestone for it to
    open, split, or close.

    Reached only once the caller has established that the target derives no
    As-Of Axis, which is where the two settlement paths a milestone verb can
    arrive through meet: an addressed keyed write, and a Materialized Write
    Group whose predicate resolved against a versioned (non-temporal) target.
    Both must refuse rather than settle, because settling keeps the verb's row
    effect and drops its temporal meaning — a bounded `updateUntil` consuming
    the row's version as an ordinary overwrite of the window it named.

    The wording comes from
    :func:`~parallax.core.unit_work.instructions.non_temporal_milestone_refusal`,
    which the build-time validator and the buffering seam raise their own errors
    from, so an instruction refused before SQL and one refused at flush describe
    the same mismatch.
    """
    refusal = non_temporal_milestone_refusal(entity.identity.name, mutation, surface=surface)
    if refusal is not None:
        raise WritePlanningError(refusal)


def _require_unobserved(entity: EntityMetadata, mutation: str, observation: object | None) -> None:
    """Refuse ``observation`` when the target it arrived for is entitled to none.

    Reached only once the caller has established that the target is neither
    temporal nor versioned, which is the one shape `m-unit-work` declares
    observationless ("unversioned Non-Temporal writes have no observation",
    absence structural). Whether a write may hold evidence at all needs the
    model, so the buffered carriers — a keyed
    :class:`~parallax.core.unit_work.materialized.ObservedKeyedWrite` and a
    :class:`~parallax.core.unit_work.materialized.MaterializedWriteGroup`'s
    observation columns — can only refuse the instruction-local half and
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
