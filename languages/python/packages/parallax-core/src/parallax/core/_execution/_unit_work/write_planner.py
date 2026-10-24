from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from operator import itemgetter

from parallax.core import inheritance, relationship, temporal_read
from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core._execution._unit_work.instructions import (
    AMEND_MUTATIONS,
    ExpectedVersion,
    PreparedKeyedInstruction,
    PreparedPredicateInstruction,
    derive_keyed_instruction,
)
from parallax.core._execution._unit_work.retain import ReadEvidence
from parallax.core._execution._unit_work.strategy import (
    ActorIdentity,
    AuditDecoration,
    AuditStrategy,
    BatchingStrategy,
    Concurrency,
    ConcurrencyStrategy,
    UndecoratedAudit,
)
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    ComposedWrite,
    InsertBatch,
    KeyedInsert,
    MutationPhase,
    ObjectLockedBatch,
    ObjectLockedWrite,
    OrderedWrite,
    PostRemovalInsert,
    TargetWrite,
)
from parallax.core._execution._unit_work.write_settlement import WritePlanCompiler
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, EntityMetadata, Metamodel
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    TemporalWriteOwnership,
    WritePlan,
)
from parallax.core.write_plan.planned_rows import entity_view, planned_assignments
from parallax.core.write_plan.steps import ANY_COUNT, UNVERSIONED, PlannedDelete, PlannedUpdate

__all__ = [
    "WritePlanner",
    "WritePlanningRequest",
]

type ComposedWrites = Sequence[ComposedWrite]


@dataclass(frozen=True, slots=True, kw_only=True)
class WritePlanningRequest:
    """One flush's complete planning input.

    Keyword-only and Actor Identity first: planning occurs under already
    captured Execution Authority, and field order emphasizes that without
    making it a positional API.

    ``composed_writes`` is the buffer as
    :class:`~parallax.core._execution._unit_work.admission.WriteAdmission`
    composed it, in authored order: one item per admitted or merged write, one composed
    write per temporal object's observed writes, and no write a later one
    cancelled. ``ownership`` answers which current temporal rows the planning
    attempt already opened and what its completed writes left for the sources
    it may still continue; planning reads it and never changes it.
    ``counts_unchanged_rows`` says the database's write count includes rows an
    update matched and left unchanged, so a guard can prove a milestone a write
    leaves unchanged (`m-dialect`).
    """

    actor_identity: ActorIdentity
    transaction_instant: TransactionInstant
    concurrency: Concurrency
    composed_writes: ComposedWrites
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP
    counts_unchanged_rows: bool = False


class WritePlanner:
    """The model-scoped, stateless Write Planner (`m-unit-work`).

    Constructed once per accepted Metamodel with its strategy adapters already
    wired; :meth:`finalize` plans a flush, :meth:`audit_decoration` supplies
    the audit a deferred range of its plans binds under once that range's
    coverage is read, and :meth:`predicate_step` plans a predicate-selected
    write's one statement. No caller sequences coalescing, batching, ordering, temporal
    expansion, observation validation, instant acquisition, or audit by hand.

    The compiler it constructs here is its own, built over the same model and
    compiled facets and living exactly as long: a prepared Model Selection
    carries a mutually consistent model, codec, planner, and compiler, and
    publication replaces the whole selection rather than rebinding any of
    them. So does the write payload preparer it is wired with, which every plan
    it answers is lowered through (:attr:`payloads`).
    """

    __slots__ = (
        "_audit",
        "_batching",
        "_compiler",
        "_concurrency",
        "_families",
        "_model",
        "_payloads",
        "_relationships",
        "_settled",
        "_temporal_facet",
    )

    def __init__(
        self,
        model: Metamodel,
        *,
        batching: BatchingStrategy,
        concurrency: ConcurrencyStrategy,
        audit: AuditStrategy,
        payloads: WritePayloadPreparer,
    ) -> None:
        self._model = model
        self._families = inheritance.view(model)
        self._temporal_facet = temporal_read.view(model)
        self._relationships = relationship.view(model)
        self._batching = batching
        self._concurrency = concurrency
        self._audit = audit
        self._payloads = payloads
        self._settled = (
            frozenset[AttributeIdentity]()
            if isinstance(audit, UndecoratedAudit)
            else _settled_attributes(model, self._families, self._temporal_facet, concurrency)
        )
        self._compiler = WritePlanCompiler(
            model,
            self._families,
            self._temporal_facet,
            concurrency=concurrency,
            audit=audit,
            settled=self._settled,
            payloads=payloads,
        )

    @property
    def payloads(self) -> WritePayloadPreparer:
        """The model's write payload preparer, which lowers every plan this
        planner answers and every deferred range of those plans."""
        return self._payloads

    def finalize(self, request: WritePlanningRequest) -> WritePlan:
        """Plan one flush: eliminate no-ops, batch, order into mutation phases,
        and hand them all to the compiler — answering the plan, whose settled
        writes carry the source evidence their writes held. Admission already
        composed the buffer, so finalization indexes nothing again.

        Pure with respect to its inputs — no database I/O, no direct clock
        access, no SQL. ``request.actor_identity`` is accepted and never
        inspected. ``request.transaction_instant`` is threaded unevaluated
        until a surviving temporal mutation needs it.

        Batching reads an opening row's member set directly, because
        preparation already spelled every applicable member out: two rows that
        write the same row therefore reach one group key and satisfy the Planned
        Insert's own same-members rule without a canonicalizing pass here.

        The three stages here REWRITE the sequence — drop, batch, reorder.
        The Write Plan
        :meth:`~parallax.core._execution._unit_work.write_settlement.WritePlanCompiler.compile`
        answers is returned unchanged, because its Write Groups, provenance, and
        each settled write's completion are decided there and nothing is left
        for the planner to add.
        """
        survivors = [
            item
            for item in (
                _without_noop_rows(item, self._families) for item in request.composed_writes
            )
            if item is not None
        ]
        batched = self._form_batches(survivors)
        return self._compiler.compile(
            self._order(batched),
            concurrency=request.concurrency,
            actor_identity=request.actor_identity,
            transaction_instant=request.transaction_instant,
            ownership=request.ownership,
            counts_unchanged_rows=request.counts_unchanged_rows,
        )

    def audit_decoration(
        self, *, actor_identity: ActorIdentity, transaction_instant: TransactionInstant
    ) -> AuditDecoration:
        """The configured audit applied with ``actor_identity`` and
        ``transaction_instant``. Building it invokes no hook and resolves no
        instant, so one serves every range a flush binds."""
        return AuditDecoration(self._audit, actor_identity, transaction_instant, self._settled)

    def predicate_step(
        self,
        prepared: PreparedPredicateInstruction,
        /,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedUpdate | PlannedDelete:
        """The one readless statement ``prepared`` executes as over every row
        its selection matches, unversioned and expecting any count, an update
        decorated once by the configured audit with ``actor_identity`` and
        ``transaction_instant``.

        It is planned alone, outside every buffered Write Plan: no buffered
        write is ordered around it, and it publishes no completion."""
        return _predicate_step(
            prepared,
            entity_view(self._families, prepared.selection.target),
            self.audit_decoration(
                actor_identity=actor_identity, transaction_instant=transaction_instant
            ),
        )

    def version_attribute(self, entity: EntityIdentity) -> AttributeIdentity | None:
        """The Attribute carrying ``entity``'s optimistic version, or ``None``
        for an unversioned Entity."""
        return self._concurrency.version_attribute(self._model, entity)

    def inserted_version(self, entity: EntityIdentity, advanced_from: int | None) -> int | None:
        """The version a row of ``entity`` the planning attempt inserted holds,
        given the version its last completed update advanced from — ``None``
        where no update did — or ``None`` for an unversioned Entity.

        The attempt wrote every revision of such a row, so the arithmetic that
        stamped them answers its version without reading it.
        """
        if self.version_attribute(entity) is None:
            return None
        arithmetic = self._concurrency.version_arithmetic()
        return arithmetic.initial if advanced_from is None else arithmetic.advance(advanced_from)

    def _form_batches(
        self, buffer: Sequence[ComposedWrite]
    ) -> list[OrderedWrite | PostRemovalInsert]:
        result: list[OrderedWrite | PostRemovalInsert] = []
        candidates: list[KeyedInsert | ObjectLockedWrite] = []
        batch: object = None

        def batch_key(item: PreparedKeyedInstruction) -> object:
            return self._batching.batch_key(self._model, item.target, item.mutation, item.rows[0])

        def close_batch() -> None:
            if not candidates:
                return
            first = candidates[0].instruction
            rows = [row for w in candidates for row in w.instruction.rows]
            if len(candidates) == 1:
                result.extend(candidates)
            elif self._batching.collapses(self._model, first.target, first.mutation, rows):
                result.append(_merged_batch(candidates, rows))
            else:
                result.extend(candidates)
            candidates.clear()

        # Inserts and object-locked writes batch; an object-locked batch keeps
        # every source evidence its writes held. A write carrying an
        # observation is never merged into a multi-row batch: a merged
        # statement shares ONE address, ONE assignment shape, and ONE
        # affected-row total, while every fact an observation licenses is
        # per-row — the milestone a close addresses, the version it advances
        # from, the gate it binds under optimistic mode, and the single row each
        # of those expects to affect. The exclusion therefore holds in locking
        # mode too, where the settled write is Ungated and only the address, the
        # advance, and the attribution are at stake. Neither does a write an
        # insertion or a caller's condition licenses batch, and every write
        # that does not batch reaches the `else` branch below as its own
        # singleton. An admitted write is single-row by construction, so the
        # batch this skips is the only way its row could have joined a
        # multi-row statement. An insert that must follow a removal is a
        # barrier no batch spans.
        for item in buffer:
            if isinstance(item, PostRemovalInsert):
                close_batch()
                result.append(item)
            elif isinstance(item, KeyedInsert | ObjectLockedWrite):
                instruction = item.instruction
                item_batch = batch_key(instruction)
                if (
                    candidates
                    and item_batch == batch
                    and _shares_statement(candidates[-1].instruction, instruction)
                ):
                    candidates.append(item)
                    continue
                close_batch()
                candidates.append(item)
                batch = item_batch
            else:
                close_batch()
                result.append(item)
        close_batch()
        return result

    def _order(self, items: Sequence[OrderedWrite | PostRemovalInsert]) -> list[MutationPhase]:
        """``items`` as mutation phases in flush order: within each region the
        inserts in ascending referential rank, then the updates in authored
        order, then the deletes in descending rank are a phase each, an empty
        one omitted. Both sorts are stable. Inserts that depend on an earlier
        removal open a new region, so the removal precedes them while they
        still order with what follows them."""
        phases: list[MutationPhase] = []
        inserts: list[tuple[int, OrderedWrite]] = []
        updates: list[OrderedWrite] = []
        deletes: list[tuple[int, OrderedWrite]] = []

        for item in items:
            if isinstance(item, PostRemovalInsert):
                # Everything authored before the removal-dependent insert
                # executes first, the removal it depends on included; what is
                # authored after it orders with it as usual.
                _close_region(phases, inserts, updates, deletes)
                item = item.insert
            phase = item.phase
            if phase == "update":
                updates.append(item)
            elif phase == "insert":
                inserts.append((self._ranked(item.target), item))
            else:
                deletes.append((self._ranked(item.target), item))
        _close_region(phases, inserts, updates, deletes)
        return phases

    def _ranked(self, entity: EntityMetadata) -> int:
        rank = self._relationships.referential_rank(entity.identity)
        return 0 if rank is None else rank


_RANK = itemgetter(0)


def _predicate_step(
    instruction: PreparedPredicateInstruction, view: InheritanceEntityView, audit: AuditDecoration
) -> PlannedUpdate | PlannedDelete:
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


def _close_region(
    phases: list[MutationPhase],
    inserts: list[tuple[int, OrderedWrite]],
    updates: list[OrderedWrite],
    deletes: list[tuple[int, OrderedWrite]],
) -> None:
    if inserts:
        inserts.sort(key=_RANK)
        phases.append(tuple(item for _, item in inserts))
        inserts.clear()
    if updates:
        phases.append(tuple(updates))
        updates.clear()
    if deletes:
        deletes.sort(key=_RANK, reverse=True)
        phases.append(tuple(item for _, item in deletes))
        deletes.clear()


def _key_name(families: inheritance.InheritanceFacet, entity: EntityMetadata) -> str:
    position = families.entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    return position.primary_key.identity.name


def _shares_statement(last: PreparedKeyedInstruction, arriving: PreparedKeyedInstruction) -> bool:
    return (
        last.target == arriving.target
        and last.mutation == arriving.mutation
        and last.valid_time_window == arriving.valid_time_window
    )


def _merged_batch(
    run: Sequence[KeyedInsert | ObjectLockedWrite], rows: Sequence[Mapping[str, object]]
) -> InsertBatch | ObjectLockedBatch:
    """``run`` collapsed into one multi-row instruction over ``rows``, every
    row of its single-row instructions in run (buffer) order, with the same
    entity, mutation, and Valid-Time window its members already share: a run
    of inserts, or one of object-locked writes, each keeping the object every
    row names and, for object-locked writes, every distinct source evidence
    they retained. A run shares one mutation, so it never mixes the two."""
    inserts: list[KeyedInsert] = []
    locked: list[ObjectLockedWrite] = []
    retained: dict[int, ReadEvidence] = {}
    for item in run:
        if isinstance(item, KeyedInsert):
            inserts.append(item)
            continue
        locked.append(item)
        for held in item.source_evidence:
            retained.setdefault(id(held), held)
    merged = derive_keyed_instruction(
        run[0].instruction, tuple(rows), assigns=any(w.instruction.assigns for w in run)
    )
    if not locked:
        return InsertBatch(instruction=merged, object_keys=tuple(w.object_key for w in inserts))
    assert not inserts  # a run shares one mutation
    return ObjectLockedBatch(
        instruction=merged,
        object_keys=tuple(w.object_key for w in locked),
        source_evidence=tuple(retained.values()),
    )


def _without_noop_rows(
    item: ComposedWrite, families: inheritance.InheritanceFacet
) -> ComposedWrite | None:
    """``item``, or ``None`` where it is known no-op work.

    An update row naming only key members changes nothing: a key ADDRESSES the
    row rather than assigns to it, so such a row is known no-op work and stage 2
    removes it (`m-unit-work` "eliminate known cancellation and no-op work"),
    ahead of batching and of the Transaction Instant, where the normative stage
    order puts it. An admitted write is single-row by construction, so it is
    either eliminated whole or passed through untouched, and is never rebuilt
    around a narrower instruction.
    """
    if isinstance(item, ComposedTemporalWrite | ComposedBitemporalOpening | PostRemovalInsert):
        return item
    if isinstance(item, TargetWrite) and isinstance(item.expectation, ExpectedVersion):
        # A caller-conditioned write of a versioned row still advances its
        # version, which is the revision its caller asked for.
        return item
    instruction = item.instruction
    if instruction.mutation not in AMEND_MUTATIONS:
        return item
    key_name = _key_name(families, instruction.target)
    (row,) = instruction.rows
    return None if all(name == key_name for name in row) else item


def _settled_attributes(
    model: Metamodel,
    families: inheritance.InheritanceFacet,
    temporal_facet: temporal_read.TemporalFacet,
    concurrency: ConcurrencyStrategy,
) -> frozenset[AttributeIdentity]:
    """Every Attribute of ``model`` whose value settlement alone decides — each
    Entity's primary key, temporal bounds, and optimistic version — which no
    audit answer may state."""
    settled: set[AttributeIdentity] = set()
    for entity in model.entities:
        position = families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
        settled.add(position.primary_key.identity)
        version = concurrency.version_attribute(model, entity.identity)
        if version is not None:
            settled.add(version)
        shape = temporal_facet.shape(entity.identity)
        if isinstance(shape, temporal_read.Bitemporal):
            axes = (shape.valid_time, shape.transaction_time)
        elif isinstance(shape, temporal_read.TransactionTimeOnly):
            axes = (shape.transaction_time,)
        else:
            axes = ()
        for axis in axes:
            settled.update((axis.start_attribute, axis.end_attribute))
    return frozenset(settled)
