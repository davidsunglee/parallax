"""The Write Planner: the single finalization authority (m-unit-work).

:class:`WritePlanner` turns one flush's boundary-captured Subject Identity,
lazy Transaction Instant, concurrency mode, and buffered writes into a
:class:`~parallax.core.unit_work.plan.WritePlan`. A write that settles against
existing state arrives carrying the observation its verb resolved for it, so the
planner resolves no evidence of its own. It is model-scoped,
constructed once per accepted Metamodel with its batching, concurrency,
temporal, and audit strategies already wired, and it exposes exactly one
planning operation, :meth:`WritePlanner.plan`.

**It emits no SQL.** The module DAG pins ``m-unit-work -> m-op-algebra`` and
``m-unit-work -> m-db-port`` only — there is deliberately **no** edge to
``m-sql``, ``m-dialect``, or any optional policy module (``m-batch-write``,
``m-opt-lock``, ``m-txtime-write``, ``m-bitemp-write``, ``m-read-lock``). This
module reaches those policies only through the strategy ports
:mod:`~parallax.core.unit_work.strategy` declares, injected once by the
composition layer that legally sees both (``parallax.snapshot.handle``).

Stage grouping. ``core/spec/m-unit-work.md`` describes the pipeline as nine
named stages; this is an ordering CONTRACT, not a mandate for nine methods.
Four orderings are normative and this implementation preserves each:
coalescing and known no-op elimination precede batching, ordering, and the
lazy instant resolution inside :meth:`_settle` — a known net-zero edit is
never merged into a batch, never dependency-ordered, and never the reason a
timestamp is captured; a required observation is validated before the gate
decision that consumes it, inside the same :meth:`_settle` call; a surviving
temporal mutation stays one indivisible unit through batching and ordering and
expands only after :meth:`_order` has fixed its position; and provenance
decoration (:meth:`plan`'s own trailing pass) runs after every step's topology
is settled and before the Write Plan freezes. :meth:`plan` therefore runs
coalesce, eliminate no-ops, form batches, order, settle, in that order —
eliminating a no-op ahead of batching is what lets two writes a no-op
separates in the buffer still merge into one batch.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast

from parallax.core import inheritance
from parallax.core.base import INFINITY_LITERAL
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    Cardinality,
    DefiningRelationshipDeclaration,
    Document,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    TemporalDimension,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.columns import (
    ColumnSlice,
    PredecessorColumns,
    freeze_retained_value,
)
from parallax.core.unit_work.instructions import (
    INSERT_MUTATIONS,
    KeyedWrite,
    PredicateWrite,
    WriteInstruction,
)
from parallax.core.unit_work.materialized import (
    MaterializedWriteGroup,
    ObservedKeyedWrite,
    TemporalColumns,
    VersionColumns,
)
from parallax.core.unit_work.observe import (
    LATEST_PINNED,
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
    PredicateTarget,
    SelfIncrement,
    TemporalConcurrency,
    TemporalGate,
    TemporalUpperBound,
    Versioned,
    VersionGate,
    shortfall_for,
)
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.core.unit_work.planner import (
    BufferItem,
    ObjectKey,
    Targets,
    buffered_instruction,
    resolve_object_key,
    targets,
)
from parallax.core.unit_work.strategy import (
    AuditStrategy,
    BatchingStrategy,
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

__all__ = ["PlanningRequest", "SubjectIdentity", "WritePlanner", "plan_temporal_close"]

type BufferedWrites = Sequence[BufferItem]

# The keyed mutation verbs finalized directly into a row write — the
# non-temporal write triad. The milestone verbs open, split, or close a
# milestone rather than write a row outright, and a temporal entity's own
# `insert` opens one too, so neither is this shape.
_FINALIZED_VERBS: Final[frozenset[str]] = frozenset({"insert", "update", "delete"})

# The predicate-selected verbs a readless template exists for. A `terminate`
# or `*Until` predicate write names a milestone, so its only legal targets
# materialize to keyed writes long before finalization.
_READLESS_VERBS: Final[frozenset[str]] = frozenset({"update", "delete"})

_UPDATE_VERBS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})
_DELETE_VERBS: Final[frozenset[str]] = frozenset({"delete", "terminate", "terminateUntil"})

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


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanningRequest:
    """One flush's complete planning input.

    Keyword-only and Subject Identity first: planning occurs inside an already
    established Principal boundary, and field order emphasizes that without
    making it a positional API.
    """

    subject_identity: SubjectIdentity
    transaction_instant: TransactionInstant
    concurrency: Concurrency
    buffered_writes: BufferedWrites


class WritePlanner:
    """The model-scoped, stateless Write Planner (`m-unit-work`).

    Constructed once per accepted Metamodel with its strategy adapters already
    wired; :meth:`plan` is its entire caller-visible surface. No caller
    sequences coalescing, batching, ordering, temporal expansion, observation
    validation, instant acquisition, or provenance decoration by hand.
    """

    __slots__ = ("_audit", "_batching", "_concurrency", "_model", "_temporal")

    def __init__(
        self,
        model: Metamodel,
        *,
        batching: BatchingStrategy,
        concurrency: ConcurrencyStrategy,
        temporal: TemporalStrategy,
        audit: AuditStrategy,
    ) -> None:
        self._model = model
        self._batching = batching
        self._concurrency = concurrency
        self._temporal = temporal
        self._audit = audit

    def plan(self, request: PlanningRequest) -> WritePlan:
        """Plan one flush: coalesce, eliminate no-ops, batch, order, settle
        every surviving item, decorate the eagerly settled steps, and freeze.

        Pure with respect to its inputs — no database I/O, no direct clock
        access, no SQL. ``request.subject_identity`` is accepted and never
        inspected. ``request.transaction_instant`` is threaded unevaluated
        until a surviving temporal mutation needs it.

        Every surviving opening row is canonicalized before batching and settling
        (:func:`_canonical_item`), so membership — which decides both — reads one
        answer rather than one per stage.

        A Materialized Write Group settles every group-wide semantic fact —
        temporal topology, the gate/concurrency decision, the affected-row
        policy, the assignment shape, and the resolved instant if the group
        needs one — into its own segment (:meth:`_settle_group`) before
        ``plan`` returns; the segment itself, and the ``WritePlan`` it becomes
        part of, retain no group, concurrency mode, Transaction Instant, or
        strategy object. Only the PER-ROW data stays as the group's own
        compact columns, and a row's ``PlannedWrite`` is rebuilt from those
        columns and the already-settled facts one at a time, on demand, so a
        large materialized run never forces a parallel `PlannedWrite`-per-row
        object graph merely by being planned. An ordinary (non-materialized)
        run settles eagerly, exactly as before, into one shared segment.
        """
        resolved = targets(self._model)
        coalesced = self._coalesce(request.buffered_writes, resolved)
        survivors = [
            item
            for item in (_without_noop_rows(item, resolved) for item in coalesced)
            if item is not None
        ]
        canonical = [_canonical_item(item, resolved) for item in survivors]
        batched = self._form_batches(canonical, resolved)
        ordered = self._order(batched, resolved)
        segments: list[StepSegment] = []
        pending: list[PlannedStep] = []

        def flush_pending() -> None:
            if pending:
                segments.append(eager_segment(tuple(pending)))
                pending.clear()

        for item in ordered:
            if isinstance(item, MaterializedWriteGroup):
                flush_pending()
                segments.append(
                    self._settle_group(
                        item, resolved, request.concurrency, request.transaction_instant
                    )
                )
                continue
            instruction, observation = (
                (item.instruction, item.observation)
                if isinstance(item, ObservedKeyedWrite)
                else (item, None)
            )
            for step in self._settle(
                instruction,
                resolved,
                observation,
                request.concurrency,
                request.transaction_instant,
            ):
                pending.append(
                    self._audit.decorate(
                        step,
                        subject_identity=request.subject_identity,
                        transaction_instant=request.transaction_instant,
                    )
                )
        flush_pending()
        return WritePlan(steps=PlannedSteps(tuple(segments)))

    # ----------------------------------------------------------------- #
    # Stage 1: resolve identities and coalesce buffered intent.          #
    # A same-transaction keyed insert-then-update of one object folds     #
    # into a single final-value write; insert-then-delete cancels.        #
    # ----------------------------------------------------------------- #
    def _coalesce(self, buffer: BufferedWrites, resolved: Targets) -> list[BufferItem]:
        result: list[BufferItem | None] = []
        pending_insert: dict[ObjectKey, int] = {}
        for item in buffer:
            if isinstance(item, MaterializedWriteGroup):
                result.append(item)
                continue
            instruction = buffered_instruction(item)
            key = resolve_object_key(instruction, resolved)
            if not isinstance(instruction, KeyedWrite) or key is None:
                result.append(item)
                continue
            verb = instruction.mutation
            if verb in INSERT_MUTATIONS:
                result.append(item)
                pending_insert[key] = len(result) - 1
            elif verb in _UPDATE_VERBS and key in pending_insert:
                index = pending_insert[key]
                base = result[index]
                # An `ObservedKeyedWrite` refuses to wrap an insert, so a
                # pending-insert slot is always a bare instruction — and folding
                # an update into it yields an insert, which is why the merged
                # item stays bare.
                assert isinstance(base, KeyedWrite)
                result[index] = _merge_update_into_insert(base, instruction, resolved)
            elif verb in _DELETE_VERBS and key in pending_insert:
                result[pending_insert.pop(key)] = None
            else:
                result.append(item)
        return [item for item in result if item is not None]

    # ----------------------------------------------------------------- #
    # Stage 4: form compatible batches. Same-entity, same-mutation,       #
    # ADJACENT single-row keyed writes merge when the injected batching   #
    # strategy says the run collapses. A preformed multi-row update is    #
    # split into its rows first (`_decomposed_updates`), so no addressed  #
    # update reaches settlement sharing a step the strategy never         #
    # admitted.                                                           #
    # ----------------------------------------------------------------- #
    def _form_batches(self, buffer: Sequence[BufferItem], resolved: Targets) -> list[BufferItem]:
        result: list[BufferItem] = []
        run: list[KeyedWrite] = []
        run_group: object = None

        def group_key(item: KeyedWrite) -> object:
            entity = resolved.entity(item.entity)
            if entity is None:
                return None
            return self._batching.group_key(self._model, entity, item.mutation, item.rows[0])

        def flush_run() -> None:
            if not run:
                return
            entity = resolved.entity(run[0].entity)
            rows = [row for w in run for row in w.rows]
            if len(run) == 1 or entity is None:
                result.extend(run)
            elif self._batching.collapses(self._model, entity, run[0].mutation, rows):
                result.append(_merge_rows(run))
            else:
                result.extend(run)
            run.clear()

        # A write carrying an observation is never merged into a multi-row run:
        # a merged statement shares ONE address, ONE assignment shape, and ONE
        # affected-row total, while every fact an observation licenses is
        # per-row — the milestone a close addresses, the version it advances
        # from, the gate it binds under optimistic mode, and the single row each
        # of those expects to affect. The exclusion therefore holds in locking
        # mode too, where the settled write is Ungated and only the address, the
        # advance, and the attribution are at stake. It reaches the `else`
        # branch below as its own singleton, because carrying an observation IS
        # being wrapped — no map and no key recomputation decides it, for
        # versioned and temporal alike. A carrier is single-row by
        # construction, so the run this skips is the only way its row could
        # have joined a multi-row statement.
        for item in _decomposed_updates(buffer, resolved):
            if isinstance(item, KeyedWrite) and len(item.rows) == 1:
                item_group = group_key(item)
                if (
                    run
                    and run[-1].entity == item.entity
                    and run[-1].mutation == item.mutation
                    and run[-1].valid_from == item.valid_from
                    and run[-1].until == item.until
                    and item_group == run_group
                ):
                    run.append(item)
                    continue
                flush_run()
                run.append(item)
                run_group = item_group
            else:
                flush_run()
                result.append(item)
        flush_run()
        return result

    # ----------------------------------------------------------------- #
    # Stage 5: dependency-order within barrier regions. A readless        #
    # predicate write is a hard ordering barrier partitioning the         #
    # sequence into independently reorderable regions.                    #
    # ----------------------------------------------------------------- #
    def _order(self, items: Sequence[BufferItem], resolved: Targets) -> list[BufferItem]:
        ranks = _fk_ranks(self._model)

        def rank(item: BufferItem) -> int:
            entity = resolved.entity(_instruction_entity(buffered_instruction(item)))
            return 0 if entity is None else ranks.get(entity.identity, 0)

        def mutation(item: BufferItem) -> str:
            return buffered_instruction(item).mutation

        def order_region(region: Sequence[BufferItem]) -> list[BufferItem]:
            inserts = [i for i in region if mutation(i) in INSERT_MUTATIONS]
            updates = [i for i in region if mutation(i) in _UPDATE_VERBS]
            deletes = [i for i in region if mutation(i) in _DELETE_VERBS]
            inserts.sort(key=rank)
            deletes.sort(key=lambda i: -rank(i))
            return [*inserts, *updates, *deletes]

        ordered: list[BufferItem] = []
        region: list[BufferItem] = []
        for item in items:
            if isinstance(item, PredicateWrite):
                ordered.extend(order_region(region))
                ordered.append(item)
                region = []
            else:
                region.append(item)
        ordered.extend(order_region(region))
        return ordered

    # ----------------------------------------------------------------- #
    # Stage 2 (known cancellation and no-op work) is filtered in         #
    # `plan`'s own comprehension via `_without_noop_rows`, BEFORE        #
    # batching and ordering, so neither a no-op instruction nor a no-op  #
    # ROW of one ever occupies a batch run or a dependency-ordered       #
    # position, and neither is ever settled.                             #
    #                                                                     #
    # Stages 3, 6, 7: validate the observation the item arrived carrying, #
    # resolve the Transaction Instant lazily, and expand temporal          #
    # topology in place.                                                   #
    # ----------------------------------------------------------------- #
    def _settle(
        self,
        instruction: WriteInstruction,
        resolved: Targets,
        observation: WriteObservation | None,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
    ) -> tuple[PlannedStep, ...]:
        if isinstance(instruction, PredicateWrite):
            return self._settle_predicate(instruction, resolved)
        entity = _require_entity(resolved, instruction.entity)
        declaring_entity = resolved.declaring(entity)
        if declaring_entity.declared_as_of_axes:
            return self._settle_temporal(
                entity,
                declaring_entity,
                instruction,
                resolved,
                observation,
                concurrency,
                tx_instant,
            )
        if instruction.mutation not in _FINALIZED_VERBS:
            raise WritePlanningError(
                f"{instruction.mutation!r} is a temporal milestone verb, and "
                f"{entity.identity.name!r} declares no temporal dimension — a milestone verb "
                "never applies to a non-temporal entity (m-txtime-write / m-bitemp-write)"
            )
        version_attr = self._concurrency.version_attribute(declaring_entity)
        members = resolved.applicable_members(entity)
        if instruction.mutation == "insert":
            return (self._settle_insert(entity, members, instruction, version_attr),)
        observed_version = self._observed_version(entity, instruction, version_attr, observation)
        settled = _non_temporal_concurrency(
            version_attr, observed_version, self._concurrency.gates(concurrency)
        )
        key_attributes = tuple(a.identity for a in resolved.family_primary_key(entity))
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
                    entity, members, instruction, key_attributes, version_attr, observed_version
                ),
                concurrency=settled,
                affected_rows=affected_rows,
            ),
        )

    def _settle_predicate(
        self, instruction: PredicateWrite, resolved: Targets
    ) -> tuple[PlannedStep, ...]:
        """One readless predicate-selected write as its single step.

        The refusals live here, on the semantic side, because they answer what
        a write MEANS rather than how it reads: an inheritance-family target
        has no per-object write to select (`m-inheritance`), and a versioned
        or temporal target has no readless template at all — it materializes
        to keyed writes at buffer time, so reaching this stage is a
        caller wiring defect. Both guards are total rather than upstream-only:
        this seam is reached straight from a deserialized instruction as well
        as from the developer verbs.
        """
        entity = _require_entity(resolved, instruction.target.entity)
        inheritance.reject_predicate_write(entity)
        declaring_entity = resolved.declaring(entity)
        if (
            declaring_entity.declared_as_of_axes
            or self._concurrency.version_attribute(declaring_entity) is not None
        ):
            raise WritePlanningError(
                f"{instruction.target.entity!r}: a predicate write on a versioned or temporal "
                "target has no readless template — it must materialize to keyed writes before "
                "reaching planning (m-opt-lock; ADR 0014); this is a caller wiring defect"
            )
        if instruction.mutation not in _READLESS_VERBS:
            raise WritePlanningError(
                f"{instruction.target.entity!r}: a readless predicate {instruction.mutation!r} "
                "names a milestone, and every legal milestone target materializes to keyed "
                "writes before planning (m-batch-write 'Predicate-selected readless forms')"
            )
        reject_readless_document_many(entity, instruction)
        target = PredicateTarget(predicate=instruction.target.predicate)
        if instruction.mutation == "delete":
            return (
                PlannedDelete(
                    entity=entity.identity,
                    target=target,
                    concurrency=UNVERSIONED,
                    affected_rows=ANY_COUNT,
                ),
            )
        members = resolved.applicable_members(entity)
        assignment_row = {
            _assignment_member(assignment.attr): assignment.value
            for assignment in instruction.assignments
        }
        return (
            PlannedUpdate(
                entity=entity.identity,
                target=target,
                assignments=_assignments(entity, members, assignment_row),
                concurrency=UNVERSIONED,
                affected_rows=ANY_COUNT,
            ),
        )

    def _settle_insert(
        self,
        entity: EntityMetadata,
        members: Mapping[str, AttributeIdentity | ValueObjectIdentity],
        instruction: KeyedWrite,
        version_attr: AttributeIdentity | None,
    ) -> PlannedInsert:
        version = (
            None if version_attr is None else (version_attr, self._concurrency.initial_version())
        )
        entries = tuple(
            InsertEntry(row=_planned_row(entity, members, row, version), origin=NEW_LINEAGE)
            for row in instruction.rows
        )
        return PlannedInsert(entity=entity.identity, entries=entries)

    def _settle_temporal(
        self,
        entity: EntityMetadata,
        declaring_entity: EntityMetadata,
        instruction: KeyedWrite,
        resolved: Targets,
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
        topology = self._temporal.topology(declaring_entity, instruction.mutation)
        observed = observation if isinstance(observation, TemporalObservation) else None
        if topology.closure is not None and observed is None:
            raise WritePlanningError(
                f"{entity.identity.name!r}: a temporal {instruction.mutation!r} closes the "
                "current milestone, and every close requires the Temporal Observation it "
                "addresses, gates on, and carries state forward from (m-unit-work; m-opt-lock)"
            )
        if observed is not None:
            # The REAL licensing check: an engine-supplied observation is
            # latest-pinned by construction, but a developer's own historical
            # or edge-pinned `Transaction.find` took its read lock on a row a
            # locking-mode close would never reach.
            self._concurrency.check_locking_license(concurrency, observed.transaction_time_basis)
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
        members = resolved.applicable_members(entity)
        steps: list[PlannedStep] = []
        if topology.closure is not None:
            assert observed is not None  # refused above
            gate = _temporal_gate(
                _gate_axis(declaring_entity, topology.closure.gate_basis).start_attribute,
                observed.predecessor,
                self._concurrency.gates(concurrency),
            )
            steps.append(
                _close(
                    entity,
                    declaring_entity,
                    key_attributes=tuple(a.identity for a in resolved.family_primary_key(entity)),
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
                        row=_planned_row(entity, members, milestone.members, None),
                        origin=milestone.origin,
                    ),
                ),
            )
            for milestone in expand_milestone(
                topology,
                axes,
                transaction_instant=instant,
                authored=instruction.rows[0],
                valid_from=instruction.valid_from,
                until=instruction.until,
                predecessor=None if observed is None else observed.predecessor,
            )
        )
        return tuple(steps)

    def _observed_version(
        self,
        entity: EntityMetadata,
        instruction: KeyedWrite,
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
        members: Mapping[str, AttributeIdentity | ValueObjectIdentity],
        instruction: KeyedWrite,
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
        assignments = _assignments(entity, members, assigned)
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
    # A Materialized Write Group's compact rows, settled ONCE HERE (in    #
    # `plan`), never re-derived at step access.                          #
    # ----------------------------------------------------------------- #
    def _settle_group(
        self,
        group: MaterializedWriteGroup,
        resolved: Targets,
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
        entity = _require_entity(resolved, group.mutation.target.entity)
        declaring_entity = resolved.declaring(entity)
        if declaring_entity.declared_as_of_axes:
            return self._settle_temporal_group(
                group, entity, declaring_entity, resolved, concurrency, tx_instant
            )
        return self._settle_versioned_group(group, entity, resolved, concurrency)

    def _settle_versioned_group(
        self,
        group: MaterializedWriteGroup,
        entity: EntityMetadata,
        resolved: Targets,
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
        """
        assert isinstance(group.observations, VersionColumns)
        declaring_entity = resolved.declaring(entity)
        version_attr = self._concurrency.version_attribute(declaring_entity)
        if version_attr is None:
            _require_unobserved(entity, group.mutation.mutation, group.observations)
        key_attributes = tuple(a.identity for a in resolved.family_primary_key(entity))
        gated = self._concurrency.gates(concurrency)
        versions = group.observations.versions
        mutation = group.mutation.mutation
        base_assignments: PlannedAssignments | None = None
        advanced_versions: tuple[int, ...] = ()
        if mutation != "delete":
            assignment_row = {
                _assignment_member(assignment.attr): assignment.value
                for assignment in group.mutation.assignments
            }
            if version_attr is not None and version_attr.name in assignment_row:
                self._concurrency.reject_authored_version(entity.identity, version_attr)
            members = resolved.applicable_members(entity)
            base_assignments = _assignments(entity, members, assignment_row)
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
        resolved: Targets,
        concurrency: Concurrency,
        tx_instant: TransactionInstant,
    ) -> StepSegment:
        """A temporal Materialized Write Group's segment.

        The temporal topology, the locking license, the gate decision, the
        successor expansion shape, and (because every temporal mutation needs
        one) the concrete Transaction Instant are all decided once, here —
        the only clock consultation this group's whole flush makes, however
        many rows it resolved. Only a row's own predecessor and key values
        remain for :meth:`_MaterializedTemporalSegment.step` to bind.
        """
        assert isinstance(group.observations, TemporalColumns)
        topology = self._temporal.topology(declaring_entity, group.mutation.mutation)
        self._concurrency.check_locking_license(
            concurrency, group.observations.transaction_time_basis
        )
        gated = self._concurrency.gates(concurrency)
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
            for assignment in group.mutation.assignments
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
            valid_from=group.mutation.valid_from,
            until=group.mutation.until,
        )
        return _MaterializedTemporalSegment(
            entity=entity,
            declaring_entity=declaring_entity,
            members=resolved.applicable_members(entity),
            key_attributes=tuple(a.identity for a in resolved.family_primary_key(entity)),
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
    (:meth:`WritePlanner._settle_temporal_group`). ``step`` only binds one
    row's own predecessor and key values into that already-decided shape; it
    never re-derives a decision a strategy already made.

    ``steps_per_row`` is invariant across the group — every row shares the
    same authored mutation and therefore the same topology — so a flat step
    index maps to (row, sub-step) by simple division, and nothing here is
    cached between accesses.
    """

    entity: EntityMetadata
    declaring_entity: EntityMetadata
    members: Mapping[str, AttributeIdentity | ValueObjectIdentity]
    key_attributes: tuple[AttributeIdentity, ...]
    key_attribute_names: tuple[str, ...]
    key_columns: tuple[ColumnSlice[object], ...]
    predecessors: PredecessorColumns
    resolved_successors: tuple[ResolvedSuccessor, ...]
    close_cause: CloseCause | None
    gate_start_attribute: AttributeIdentity | None
    axes: TemporalAxes
    instant: str
    gated: bool
    assignment_row: Mapping[str, object]
    steps_per_row: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "members", MappingProxyType(dict(self.members)))
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
                        row=_planned_row(self.entity, self.members, successor.members, None),
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
    members: Mapping[str, AttributeIdentity | ValueObjectIdentity],
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
    attributes, value_objects = _resolve(entity, members, row, context="insert")
    if version is not None:
        attribute, initial_value = version
        attributes[attribute] = initial_value
    return PlannedRow(attributes=attributes, value_objects=value_objects)


def _assignments(
    entity: EntityMetadata,
    members: Mapping[str, AttributeIdentity | ValueObjectIdentity],
    row: Mapping[str, object],
) -> PlannedAssignments:
    attributes, value_objects = _resolve(entity, members, row, context="update")
    return PlannedAssignments(attributes=attributes, value_objects=value_objects)


def _resolve(
    entity: EntityMetadata,
    members: Mapping[str, AttributeIdentity | ValueObjectIdentity],
    row: Mapping[str, object],
    *,
    context: str,
) -> tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]:
    """``row``'s cells under their resolved member identities."""
    attributes: dict[AttributeIdentity, PlannedValue] = {}
    value_objects: dict[ValueObjectIdentity, object] = {}
    for name, value in row.items():
        member = members.get(name)
        if member is None:
            raise WritePlanningError(
                f"{entity.identity.name!r}: write row names {name!r}, which is not a member "
                "of the Entity's family"
            )
        if isinstance(member, ValueObjectIdentity):
            value_objects[member] = value
        else:
            attributes[member] = _cell(entity, name, value, context)
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

    Every real close-bearing mutation chains at least one successor, and a
    conflict probe deliberately runs only the close, so it settles one here
    directly rather than through a full :class:`WritePlanner` pipeline.
    ``identity`` is the row the address keys on, ``observed_valid_end``
    completes that address on a Bitemporal target, and ``observed_tx_start``
    is the gate candidate; a probe names all three explicitly rather than
    reading them from a tracked milestone. The cause it records is
    supersession — what a real mutation's own close performs, and whose
    successors the probe deliberately does not run.

    Structurally separate from :meth:`WritePlanner.plan` (which stays the
    entire caller-visible *pipeline* surface): this is one atomic close
    settlement with no coalescing, batching, or ordering to do, callable
    without a full flush. ``concurrency_strategy`` is the SAME adapter a
    production ``WritePlanner`` was constructed with, so the two can never
    disagree about a gate decision.
    """
    resolved = targets(model)
    entity = _require_entity(resolved, entity_name)
    declaring_entity = resolved.declaring(entity)
    key_attributes = tuple(a.identity for a in resolved.family_primary_key(entity))
    _refuse_unaddressing_identity(entity, key_attributes, identity)
    gate: TemporalConcurrency = UNGATED
    if observed_tx_start is not None:
        concurrency_strategy.check_locking_license(concurrency, LATEST_PINNED)
        if concurrency_strategy.gates(concurrency):
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
    instant: str,
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
        elif observed_valid_end == INFINITY_LITERAL:
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


def reject_readless_document_many(entity: EntityMetadata, instruction: PredicateWrite) -> None:
    """Refuse the readless document-array assignment shape before planning."""
    if not isinstance(entity.declared_layout, Document):
        return
    occurrences = {
        occurrence.identity.path[-1]: occurrence for occurrence in entity.declared_value_objects
    }
    for assignment in instruction.assignments:
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


def _require_entity(resolved: Targets, spelling: str) -> EntityMetadata:
    entity = resolved.entity(spelling)
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


def _merge_update_into_insert(
    insert: KeyedWrite, update: KeyedWrite, resolved: Targets
) -> KeyedWrite:
    """Overlay ``update``'s non-key row fields onto ``insert``'s row.

    The coalesced write keeps the insert's mutation verb and Valid-Time bounds
    (so it still opens a current milestone / fully-current rectangle at
    settling per temporal flavor) but carries the FINAL values — no
    ``INSERT`` + ``UPDATE``.
    """
    entity = resolved.entity(insert.entity)
    pk_names: set[str] = (
        set() if entity is None else {a.identity.name for a in resolved.family_primary_key(entity)}
    )
    merged = dict(insert.rows[0])
    for name, value in update.rows[0].items():
        if name not in pk_names:
            merged[name] = value
    return KeyedWrite(
        mutation=insert.mutation,
        entity=insert.entity,
        rows=(merged,),
        valid_from=insert.valid_from,
        until=insert.until,
    )


def _decomposed_updates(buffer: Sequence[BufferItem], resolved: Targets) -> list[BufferItem]:
    """``buffer`` with every PREFORMED multi-row non-temporal keyed update split
    back into one single-row instruction per row.

    An addressed update's assignments are the shape one statement carries, and a
    step shared across several keys therefore requires them to be uniform
    (`m-batch-write`: incompatible writes remain separate logical steps). Only
    the collapse decision knows whether a given run is uniform, and it is asked
    of single-row runs alone — so an instruction that arrived already carrying
    several rows would otherwise skip it entirely and have its FIRST row's values
    applied to every key it addresses. Splitting it here submits those rows to
    the same decision a caller that buffered them one at a time gets: uniform
    rows re-merge through :func:`_merge_rows` into the identical instruction,
    and incompatible ones stay separate steps that each write their own values.

    Every child names at least one member to write, because stage 2's
    :func:`_without_noop_rows` already removed the key-only rows: splitting is a
    regrouping of surviving work, never the thing that mints an empty update.

    Inserts and deletes are left whole. A multi-row insert's entries are checked
    for a shared canonical member set downstream, and a delete's rows contribute
    keys rather than assignments, so neither projects one row onto the others.
    A TEMPORAL entry is left whole too, so :meth:`WritePlanner._settle_temporal`
    still refuses it as the multi-row milestone chain it is rather than silently
    settling it as several chains the caller never authored.
    """
    decomposed: list[BufferItem] = []
    for item in buffer:
        if not isinstance(item, KeyedWrite) or not _splits_into_rows(item, resolved):
            decomposed.append(item)
            continue
        decomposed.extend(
            KeyedWrite(
                mutation=item.mutation,
                entity=item.entity,
                rows=(row,),
                valid_from=item.valid_from,
                until=item.until,
            )
            for row in item.rows
        )
    return decomposed


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
    delegate this half to the model-aware settlement both of them reach. This is
    that delegation: every buffered item crosses it whatever produced it, so a
    producer that resolves evidence a target cannot carry is told rather than
    quietly stripped.
    """
    if observation is None:
        return
    raise WritePlanningError(
        f"{entity.identity.name!r}: an unversioned Non-Temporal {mutation!r} carries no Write "
        "Observation, yet one was resolved for it — absence is structural (m-unit-work "
        "'unversioned Non-Temporal writes have no observation'), and settling this write "
        "would discard the evidence rather than gate or advance anything with it"
    )


def _splits_into_rows(item: KeyedWrite, resolved: Targets) -> bool:
    if len(item.rows) < 2 or item.mutation not in _UPDATE_VERBS:
        return False
    entity = resolved.entity(item.entity)
    return entity is not None and not resolved.declaring(entity).declared_as_of_axes


def _merge_rows(run: Sequence[KeyedWrite]) -> KeyedWrite:
    """One multi-row :class:`KeyedWrite` carrying every row of ``run``'s
    single-row instructions, in run (buffer) order — the same
    entity/mutation/Valid-Time bounds every member of the run already shares."""
    first = run[0]
    return KeyedWrite(
        mutation=first.mutation,
        entity=first.entity,
        rows=tuple(row for w in run for row in w.rows),
        valid_from=first.valid_from,
        until=first.until,
    )


def _fk_ranks(model: Metamodel) -> dict[EntityIdentity, int]:
    """A topological rank per entity: a referenced entity ranks before its
    referencer.

    A ``many-to-one`` relationship means the source holds the foreign key
    (source after related); a ``one-to-many`` means the related entity holds
    it (related after source). ``one-to-one`` contributes no FK-order edge
    because its storage owner is ambiguous. Ties break by the accepted
    model's own canonical Entity order; a (defensive) cycle falls back to it
    too.

    Only DEFINING declarations contribute: a reverse declaration names a
    defining one rather than repeating it, and the inverted direction it
    denotes yields the very edge the defining side already contributed, so
    reading both would add nothing and would need the paired cardinality this
    scope cannot see. Every declared target is an accepted Entity of this
    model, so an edge always lands on a ranked position.
    """
    identities = [entity.identity for entity in model.entities]
    prereqs: dict[EntityIdentity, set[EntityIdentity]] = {
        identity: set() for identity in identities
    }
    for entity in model.entities:
        for declaration in entity.declared_relationships:
            if not isinstance(declaration, DefiningRelationshipDeclaration):
                continue
            related = declaration.join.target.entity
            if declaration.cardinality is Cardinality.MANY_TO_ONE:
                prereqs[entity.identity].add(related)
            elif declaration.cardinality is Cardinality.ONE_TO_MANY:
                prereqs[related].add(entity.identity)
    remaining = set(identities)
    order: list[EntityIdentity] = []
    while remaining:
        ready = [i for i in identities if i in remaining and not (prereqs[i] & remaining)]
        if not ready:
            # Defensive: reachable models are acyclic; a cycle keeps declaration order.
            order.extend(i for i in identities if i in remaining)  # pragma: no cover
            break  # pragma: no cover
        order.append(ready[0])
        remaining.discard(ready[0])
    return {identity: rank for rank, identity in enumerate(order)}


def _instruction_entity(instruction: WriteInstruction) -> str:
    if isinstance(instruction, KeyedWrite):
        return instruction.entity
    # A readless predicate write is always a barrier in `_order`, never a
    # region member `rank`/`mutation` resolves against — but a Materialized
    # Write Group's own `mutation` IS a `PredicateWrite`, and a group ranks
    # as an ordinary region member, so this arm is reached for one.
    return instruction.target.entity


def _without_noop_rows(item: BufferItem, resolved: Targets) -> BufferItem | None:
    """``item`` with its known no-op rows gone, or ``None`` when none survive.

    An update row naming only key members changes nothing: a key ADDRESSES the
    row rather than assigns to it, so such a row is known no-op work and stage 2
    removes it (`m-unit-work` "eliminate known cancellation and no-op work").

    Elimination is per ROW, not per instruction, because a preformed multi-row
    update mixing a key-only row with an assigning one is not empty as a whole
    and would therefore survive an instruction-level test — only to be split
    into its rows during batching and hand the key-only child to
    :meth:`WritePlanner._update_assignments`, which has no member to write.
    Removing the row HERE keeps that child from ever existing and keeps the
    elimination at stage 2, ahead of batching and of the Transaction Instant,
    where the normative stage order puts it.

    A temporal instruction is narrowed only to nothing, never to fewer rows:
    dropping one row of an authored multi-row temporal instruction would
    silently discard a milestone chain the author wrote, which is precisely the
    reduction :meth:`WritePlanner._settle_temporal` refuses outright
    (`m-unit-work` "A temporal keyed instruction carries exactly one row").
    An observation carrier is single-row by construction, so it is either
    eliminated whole or passed through untouched, and is never rebuilt around a
    narrower instruction.
    """
    instruction = buffered_instruction(item)
    if not isinstance(instruction, KeyedWrite) or instruction.mutation not in _UPDATE_VERBS:
        return item
    entity = resolved.entity(instruction.entity)
    if entity is None:
        return item
    pk_names = {a.identity.name for a in resolved.family_primary_key(entity)}
    kept = tuple(row for row in instruction.rows if not all(name in pk_names for name in row))
    if not kept:
        return None
    if len(kept) == len(instruction.rows) or resolved.declaring(entity).declared_as_of_axes:
        return item
    return KeyedWrite(
        mutation=instruction.mutation,
        entity=instruction.entity,
        rows=kept,
        valid_from=instruction.valid_from,
        until=instruction.until,
    )


def _canonical_item(item: BufferItem, resolved: Targets) -> BufferItem:
    """``item`` with every opening row's canonical member set spelled out.

    An opening row that does not name a `many` Value Object occurrence has said the
    occurrence holds no elements, so the empty collection is a member of that row as
    surely as any value it wrote (`m-value-object`). Membership *is* the batching
    decision and it is also what one step's entries must share, so the two rows
    ``{id, tags: []}`` and ``{id}`` have to reach both with one member set: left
    apart, they answer different group keys and then fail the Planned Insert's own
    same-members rule, though they write the same row.

    Only an OPENING row is canonicalized. A revising one is sparse — an unnamed
    member there is untouched rather than zero — so adding the occurrence would turn
    a member the caller left alone into one the statement assigns.

    Passing an observation carrier through untouched loses no opening row: an
    ``ObservedKeyedWrite`` refuses to wrap an insert, so every carrier is a
    revising write by construction.
    """
    if not isinstance(item, KeyedWrite) or item.mutation not in INSERT_MUTATIONS:
        return item
    entity = resolved.entity(item.entity)
    if entity is None:
        return item
    zero_state = resolved.zero_state_members(entity)
    if not zero_state:
        return item
    rows = tuple(_with_zero_states(row, zero_state) for row in item.rows)
    return KeyedWrite(
        mutation=item.mutation,
        entity=item.entity,
        rows=rows,
        valid_from=item.valid_from,
        until=item.until,
    )


def _with_zero_states(row: Mapping[str, object], zero_state: Sequence[str]) -> Mapping[str, object]:
    filled: dict[str, object] = dict(row)
    for name in zero_state:
        if name not in filled:
            filled[name] = []
    return filled
