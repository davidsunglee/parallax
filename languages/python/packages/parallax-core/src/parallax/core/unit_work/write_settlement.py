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
    TemporalConcurrency,
    TemporalGate,
    TemporalUpperBound,
    Versioned,
    VersionGate,
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
)
from parallax.core.unit_work.temporal import (
    ResolvedSuccessor,
    TemporalAxes,
    bind_successor,
    expand_milestone,
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
        _reject_milestone_verb(entity, instruction.mutation, "keyed")
        version_attr = self._concurrency.version_attribute(declaring_entity)
        view = self._families.view(entity)
        if instruction.mutation == "insert":
            return (self._settle_insert(entity, view, instruction, version_attr),)
        observed_version = self._observed_version(entity, instruction, version_attr, observation)
        settled = _non_temporal_concurrency(
            version_attr,
            observed_version,
            self._concurrency.gates(concurrency, declaring_entity),
        )
        key_attributes = tuple(a.identity for a in self._families.primary_key(entity))
        target = _key_target(entity, key_attributes, instruction.rows)
        affected_rows = ExactCount(
            expected=len(target.key_values), on_shortfall=shortfall_for(settled)
        )
        if instruction.mutation == "delete":
            return (
                PlannedDelete(
                    entity=entity.identity,
                    target=target,
                    concurrency=settled,
                    affected_rows=affected_rows,
                ),
            )
        return (
            PlannedUpdate(
                entity=entity.identity,
                target=target,
                assignments=self._update_assignments(
                    entity, view, instruction, key_attributes, version_attr, observed_version
                ),
                concurrency=settled,
                affected_rows=affected_rows,
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
        self,
        entity: EntityMetadata,
        view: InheritanceEntityView,
        instruction: PreparedKeyedWrite,
        version_attr: AttributeIdentity | None,
    ) -> PlannedInsert:
        version = (
            None if version_attr is None else (version_attr, self._concurrency.initial_version())
        )
        entries = tuple(
            InsertEntry(row=_planned_row(entity, view, row, version), origin=NEW_LINEAGE)
            for row in instruction.rows
        )
        return PlannedInsert(entity=entity.identity, entries=entries)

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
        _reject_temporal_delete(entity, instruction.mutation, "keyed")
        topology = self._temporal.topology(declaring_entity, instruction.mutation)
        observed = observation if isinstance(observation, TemporalObservation) else None
        if topology.closure is not None and observed is None:
            raise WritePlanningError(
                f"{entity.identity.name!r}: a temporal {instruction.mutation!r} closes the "
                "current milestone, and every close requires the Temporal Observation it "
                "addresses, gates on, and carries state forward from (m-unit-work; m-opt-lock)"
            )
        valid_axis = declaring_entity.as_of_axis(TemporalDimension.VALID_TIME)
        tx_axis = _tx_time_axis(declaring_entity)
        axes = TemporalAxes(
            transaction_start=tx_axis.start_attribute.name,
            transaction_end=tx_axis.end_attribute.name,
            valid_start=None if valid_axis is None else valid_axis.start_attribute.name,
            valid_end=None if valid_axis is None else valid_axis.end_attribute.name,
        )
        # Reaching a temporal mutation is what makes the attempt capture its
        # instant; the close's new Transaction-Time end and every successor's
        # fresh start derive from that one value.
        instant = tx_instant.value()
        view = self._families.view(entity)
        steps: list[PlannedStep] = []
        if topology.closure is not None:
            assert observed is not None  # refused above
            gate = _temporal_gate(
                _gate_axis(declaring_entity, topology.closure.gate_basis).start_attribute,
                observed.predecessor,
                self._concurrency.gates(concurrency, declaring_entity),
            )
            steps.append(
                _close(
                    entity,
                    declaring_entity,
                    key_attributes=tuple(a.identity for a in self._families.primary_key(entity)),
                    identity=instruction.rows[0],
                    observed_valid_end=(
                        None
                        if valid_axis is None
                        else observed.predecessor.member(valid_axis.end_attribute.name)
                    ),
                    cause=topology.closure.cause,
                    gate=gate,
                    instant=instant,
                )
            )
        steps.extend(
            PlannedInsert(
                entity=entity.identity,
                entries=(
                    InsertEntry(
                        row=_planned_row(entity, view, milestone.members, None),
                        origin=milestone.origin,
                    ),
                ),
            )
            for milestone in expand_milestone(
                topology,
                axes,
                transaction_instant=instant,
                authored=instruction.rows[0],
                valid_from=instruction.bounds.valid_from,
                until=instruction.bounds.until,
                predecessor=None if observed is None else observed.predecessor,
            )
        )
        return tuple(steps)

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

    def _update_assignments(
        self,
        entity: EntityMetadata,
        view: InheritanceEntityView,
        instruction: PreparedKeyedWrite,
        key_attributes: tuple[AttributeIdentity, ...],
        version_attr: AttributeIdentity | None,
        observed_version: int | None,
    ) -> PlannedAssignments:
        """The replacement values an addressed update writes.

        Key members address the write rather than change it, so they never
        appear among the assignments. A multi-row update reaching here is one
        the batching strategy collapsed, and it collapses only a run assigning
        identical values to every key (`m-batch-write` keeps incompatible
        writes in separate steps), so the first row settles the whole step's
        assignments. That holds for a PREFORMED multi-row instruction too:
        :func:`_decomposed_updates` splits one into its rows before the
        collapse decision, so no update arrives here having skipped it. A
        versioned target advances the version in BOTH modes, which is why the
        advance is an assignment rather than a gate member.
        """
        key_names = frozenset(attribute.name for attribute in key_attributes)
        row = instruction.rows[0]
        assigned = {name: value for name, value in row.items() if name not in key_names}
        assignments = _assignments(entity, view, assigned)
        if version_attr is None or observed_version is None:
            return assignments
        return PlannedAssignments(
            attributes={
                **assignments.attributes,
                version_attr: self._concurrency.advance(observed_version),
            },
            value_objects=assignments.value_objects,
        )

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
        return self._settle_versioned_group(group, entity, concurrency)

    def _settle_versioned_group(
        self,
        group: MaterializedWriteGroup,
        entity: EntityMetadata,
        concurrency: Concurrency,
    ) -> StepSegment:
        """A versioned (non-temporal) Materialized Write Group's segment.

        Every row shares the SAME gate/ungated decision and the SAME
        assignment overlay (`m-batch-write`'s set-based semantics extended to
        the materializing case); only the observed and advanced version
        differ per row, which is why those alone stay per-row columns rather
        than a per-row object. A group's observation columns are not optional,
        so an entity this group's own Concurrency Strategy does not recognize
        as versioned is refused here rather than settled Unversioned with its
        columns dropped — the same entitlement rule an ordinary keyed write
        meets in :meth:`_observed_version`.

        The verb is measured against the target for the same reason and by the
        same rule an addressed keyed write meets in :meth:`_settle`
        (:func:`_reject_milestone_verb`): reaching here means the resolve
        matched rows on a target with no As-Of Axis, so a milestone verb has
        nothing to close and every mutation but ``delete`` would otherwise
        settle as an ordinary versioned update — the caller's bounded window
        silently discarded while its version is consumed.
        """
        assert isinstance(group.observations, VersionColumns)
        _reject_milestone_verb(entity, group.mutation.mutation, "predicate")
        declaring_entity = self._families.declaring(entity)
        version_attr = self._concurrency.version_attribute(declaring_entity)
        if version_attr is None:
            _require_unobserved(entity, group.mutation.mutation, group.observations)
        key_attributes = tuple(a.identity for a in self._families.primary_key(entity))
        gated = self._concurrency.gates(concurrency, declaring_entity)
        versions = group.observations.versions
        mutation = group.mutation.mutation
        base_assignments: PlannedAssignments | None = None
        advanced_versions: tuple[int, ...] = ()
        if mutation != "delete":
            assignment_row = {
                _assignment_member(assignment.attr): assignment.value
                for assignment in group.mutation.managed_assignments
            }
            if version_attr is not None and version_attr.name in assignment_row:
                self._concurrency.reject_authored_version(entity.identity, version_attr)
            view = self._families.view(entity)
            base_assignments = _assignments(entity, view, assignment_row)
            if version_attr is not None:
                advanced_versions = tuple(self._concurrency.advance(value) for value in versions)
        shortfall = shortfall_for(_non_temporal_concurrency(version_attr, versions[0], gated))
        return _MaterializedNonTemporalSegment(
            entity=entity,
            key_attributes=key_attributes,
            key_attribute_names=group.key_attributes,
            key_columns=group.key_columns,
            mutation=mutation,
            version_attribute=version_attr,
            versions=versions,
            advanced_versions=advanced_versions,
            base_assignments=base_assignments,
            gated=gated,
            affected_rows=ExactCount(expected=1, on_shortfall=shortfall),
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

        The temporal topology, the gate decision, the successor expansion
        shape, and (because every temporal mutation needs one) the concrete
        Transaction Instant are all decided once, here — the only clock
        consultation this group's whole flush makes, however many rows it
        resolved. Only a row's own predecessor and key values remain for
        :meth:`_MaterializedTemporalSegment.step` to bind.
        """
        assert isinstance(group.observations, TemporalColumns)
        _reject_temporal_delete(entity, group.mutation.mutation, "predicate")
        topology = self._temporal.topology(declaring_entity, group.mutation.mutation)
        gated = self._concurrency.gates(concurrency, declaring_entity)
        steps_per_row = (1 if topology.closure is not None else 0) + len(topology.successors)
        # Reaching a temporal group is what makes the attempt capture its
        # instant; every row's close end and every successor's fresh start
        # derive from this one value.
        instant = tx_instant.value()
        valid_axis = declaring_entity.as_of_axis(TemporalDimension.VALID_TIME)
        tx_axis = _tx_time_axis(declaring_entity)
        axes = TemporalAxes(
            transaction_start=tx_axis.start_attribute.name,
            transaction_end=tx_axis.end_attribute.name,
            valid_start=None if valid_axis is None else valid_axis.start_attribute.name,
            valid_end=None if valid_axis is None else valid_axis.end_attribute.name,
        )
        assignment_row = {
            _assignment_member(assignment.attr): assignment.value
            for assignment in group.mutation.managed_assignments
        }
        close_cause: CloseCause | None = None
        gate_start_attribute: AttributeIdentity | None = None
        if topology.closure is not None:
            close_cause = topology.closure.cause
            gate_start_attribute = _gate_axis(
                declaring_entity, topology.closure.gate_basis
            ).start_attribute
        resolved_successors = resolve_successors(
            topology.successors,
            valid_from=group.mutation.bounds.valid_from,
            until=group.mutation.bounds.until,
        )
        return _MaterializedTemporalSegment(
            entity=entity,
            declaring_entity=declaring_entity,
            view=self._families.view(entity),
            key_attributes=tuple(a.identity for a in self._families.primary_key(entity)),
            key_attribute_names=group.key_attributes,
            key_columns=group.key_columns,
            predecessors=group.observations.predecessors,
            resolved_successors=resolved_successors,
            close_cause=close_cause,
            gate_start_attribute=gate_start_attribute,
            axes=axes,
            instant=instant,
            gated=gated,
            assignment_row=assignment_row,
            steps_per_row=steps_per_row,
        )


@dataclass(frozen=True, slots=True)
class _MaterializedNonTemporalSegment:
    """A versioned Materialized Write Group's rows: one Planned Update or
    Planned Delete per resolved row, assembled on demand from already-decided,
    group-wide facts and the group's own compact columns alone.

    No group, concurrency mode, Transaction Instant, or strategy object is
    reachable here — every value :meth:`step` reads is either a static field
    or an aligned column lookup by row index — and two calls for the same
    index return equal but distinct objects, never a shared mutable flyweight.
    """

    entity: EntityMetadata
    key_attributes: tuple[AttributeIdentity, ...]
    key_attribute_names: tuple[str, ...]
    key_columns: tuple[ColumnSlice[object], ...]
    mutation: str
    version_attribute: AttributeIdentity | None
    versions: ColumnSlice[int]
    advanced_versions: tuple[int, ...]
    base_assignments: PlannedAssignments | None
    gated: bool
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
        target = _key_target(self.entity, self.key_attributes, (key_row,))
        concurrency = _non_temporal_concurrency(
            self.version_attribute, self.versions[index], self.gated
        )
        if self.mutation == "delete":
            return PlannedDelete(
                entity=self.entity.identity,
                target=target,
                concurrency=concurrency,
                affected_rows=self.affected_rows,
            )
        assert self.base_assignments is not None  # every update's overlay is settled up front
        assignments = self.base_assignments
        if self.version_attribute is not None:
            assignments = PlannedAssignments(
                attributes={
                    **assignments.attributes,
                    self.version_attribute: self.advanced_versions[index],
                },
                value_objects=assignments.value_objects,
            )
        return PlannedUpdate(
            entity=self.entity.identity,
            target=target,
            assignments=assignments,
            concurrency=concurrency,
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
    (:meth:`WriteSettlement._settle_temporal_group`). ``step`` only binds one
    row's own predecessor and key values into that already-decided shape; it
    never re-derives a decision a strategy already made.

    ``steps_per_row`` is invariant across the group — every row shares the
    same authored mutation and therefore the same topology — so a flat step
    index maps to (row, sub-step) by simple division, and nothing here is
    cached between accesses.
    """

    entity: EntityMetadata
    declaring_entity: EntityMetadata
    view: InheritanceEntityView
    key_attributes: tuple[AttributeIdentity, ...]
    key_attribute_names: tuple[str, ...]
    key_columns: tuple[ColumnSlice[object], ...]
    predecessors: PredecessorColumns
    resolved_successors: tuple[ResolvedSuccessor, ...]
    close_cause: CloseCause | None
    gate_start_attribute: AttributeIdentity | None
    axes: TemporalAxes
    instant: dt.datetime
    gated: bool
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
        return self._settle_row(row)[sub_step]

    def _settle_row(self, row: int) -> tuple[PlannedStep, ...]:
        key_row = dict(
            zip(
                self.key_attribute_names,
                (column[row] for column in self.key_columns),
                strict=True,
            )
        )
        predecessor = self.predecessors.row(row)
        steps: list[PlannedStep] = []
        if self.close_cause is not None:
            assert self.gate_start_attribute is not None  # settled alongside close_cause
            gate = _temporal_gate(self.gate_start_attribute, predecessor, self.gated)
            observed_valid_end = (
                None if self.axes.valid_end is None else predecessor.member(self.axes.valid_end)
            )
            steps.append(
                _close(
                    self.entity,
                    self.declaring_entity,
                    key_attributes=self.key_attributes,
                    identity=key_row,
                    observed_valid_end=observed_valid_end,
                    cause=self.close_cause,
                    gate=gate,
                    instant=self.instant,
                )
            )
        authored = {**key_row, **self.assignment_row}
        steps.extend(
            PlannedInsert(
                entity=self.entity.identity,
                entries=(
                    InsertEntry(
                        row=_planned_row(self.entity, self.view, successor.members, None),
                        origin=successor.origin,
                    ),
                ),
            )
            for successor in (
                bind_successor(
                    resolved,
                    self.axes,
                    transaction_instant=self.instant,
                    authored=authored,
                    predecessor=predecessor,
                )
                for resolved in self.resolved_successors
            )
        )
        return tuple(steps)


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
