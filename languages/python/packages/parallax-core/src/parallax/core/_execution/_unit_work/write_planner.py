from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from operator import itemgetter
from typing import Never, final

from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core._execution._unit_work.instructions import (
    AMEND_MUTATIONS,
    ExpectedVersion,
    PreparedPredicateInstruction,
)
from parallax.core._execution._unit_work.strategy import (
    ActorIdentity,
    AuditDecoration,
    AuditStrategy,
    UndecoratedAudit,
)
from parallax.core._execution._unit_work.write_collapse import collapse_writes
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    ComposedWrite,
    MutationPhase,
    OrderedWrite,
    PostRemovalInsert,
    TargetWrite,
)
from parallax.core._execution._unit_work.write_settlement import WritePlanCompiler
from parallax.core.internal import concurrency, inheritance, relationship, temporal_read
from parallax.core.internal.concurrency import ConcurrencyFacet, ConcurrencyPreference
from parallax.core.internal.metamodel import AttributeIdentity, CompiledEntity, Metamodel
from parallax.core.internal.temporal_write.coverage import CoverageTransform
from parallax.core.internal.write_plan.payload import WritePayloadPreparer
from parallax.core.internal.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    TemporalWriteOwnership,
    WritePlan,
)
from parallax.core.internal.write_plan.planned_rows import planned_assignments
from parallax.core.internal.write_plan.steps import (
    ANY_COUNT,
    UNVERSIONED,
    PlannedDelete,
    PlannedUpdate,
)

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
    preference: ConcurrencyPreference
    composed_writes: ComposedWrites
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP
    counts_unchanged_rows: bool = False


@final
class WritePlanner:
    """The model-scoped, stateless Write Planner (`m-unit-work`).

    Obtained only from
    :func:`~parallax.core._execution._planning.build_write_planner`, once per
    accepted Metamodel with its audit strategy already wired, so
    every planner plans under production's audit policy;
    :meth:`finalize` plans a flush, :meth:`audit_decoration` supplies
    the audit a deferred range of its plans binds under once that range's
    coverage is read, and :meth:`predicate_step` plans a predicate-selected
    write's one statement. No caller sequences coalescing, batching, ordering, temporal
    expansion, observation validation, instant acquisition, or audit by hand.

    The compiler it constructs here is its own, built over the same model and
    compiled facets and living exactly as long: a prepared Model Selection
    carries a mutually consistent model, preparation, planner, and compiler, and
    publication replaces the whole selection rather than rebinding any of
    them. So does the write payload preparer it is wired with, which every plan
    it answers is lowered through (:attr:`payloads`).
    """

    __slots__ = (
        "_audit",
        "_compiler",
        "_families",
        "_model",
        "_payloads",
        "_relationships",
        "_settled",
        "_temporal_facet",
        "_versioning",
    )

    def __init__(self, _unconstructible: Never) -> None:
        raise TypeError("a WritePlanner is obtained only from build_write_planner")

    @classmethod
    def _wired(
        cls,
        model: Metamodel,
        *,
        audit: AuditStrategy,
        payloads: WritePayloadPreparer,
    ) -> WritePlanner:
        planner = cls.__new__(cls)
        planner._wire(model, audit=audit, payloads=payloads)
        return planner

    def _wire(
        self,
        model: Metamodel,
        *,
        audit: AuditStrategy,
        payloads: WritePayloadPreparer,
    ) -> None:
        self._model = model
        self._families = inheritance.inheritance_facet_of(model)
        self._temporal_facet = temporal_read.temporal_facet_of(model)
        self._relationships = relationship.relationship_facet_of(model)
        self._versioning = concurrency.concurrency_facet_of(model)
        self._audit = audit
        self._payloads = payloads
        self._settled = (
            frozenset[AttributeIdentity]()
            if isinstance(audit, UndecoratedAudit)
            else _settled_attributes(model, self._families, self._temporal_facet, self._versioning)
        )
        self._compiler = WritePlanCompiler(
            model,
            self._families,
            self._temporal_facet,
            self._versioning,
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
        batched = collapse_writes(self._model, survivors)
        return self._compiler.compile(
            self._order(batched),
            preference=request.preference,
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
            self.audit_decoration(
                actor_identity=actor_identity, transaction_instant=transaction_instant
            ),
        )

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

    def _ranked(self, entity: CompiledEntity) -> int:
        rank = self._relationships.referential_rank(entity.identity)
        return 0 if rank is None else rank


_RANK = itemgetter(0)


def _predicate_step(
    instruction: PreparedPredicateInstruction, audit: AuditDecoration
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
            assignments=planned_assignments(instruction.row),
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


def _key_attribute(
    families: inheritance.InheritanceFacet, entity: CompiledEntity
) -> AttributeIdentity:
    position = families.entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    return position.primary_key.identity


def _without_noop_rows(
    item: ComposedWrite, families: inheritance.InheritanceFacet
) -> ComposedWrite | None:
    """``item``, or ``None`` where it is known no-op work.

    An update row naming only key members changes nothing: a key ADDRESSES the
    row rather than assigns to it, so such a row is known no-op work, removed
    ahead of the Transaction Instant (`m-unit-work` *The planning pipeline*) and
    of batching, which would carry it as an update with no member to write. An
    admitted write is single-row by construction, so it is either eliminated
    whole or passed through untouched, and is never rebuilt around a narrower
    instruction. A temporal composition is eliminated where every write it
    composed was such an amendment.
    """
    if isinstance(item, ComposedTemporalWrite):
        return None if _amends_nothing(item.transform) else item
    if isinstance(item, ComposedBitemporalOpening | PostRemovalInsert):
        return item
    if isinstance(item, TargetWrite) and isinstance(item.expectation, ExpectedVersion):
        # A caller-conditioned write of a versioned row still advances its
        # version, which is the revision its caller asked for.
        return item
    instruction = item.instruction
    if instruction.mutation not in AMEND_MUTATIONS:
        return item
    key = _key_attribute(families, instruction.target)
    (row,) = instruction.rows
    return None if row.presence & ~(1 << row.selection.members.index[key]) == 0 else item


def _amends_nothing(transform: CoverageTransform) -> bool:
    return all(
        segment.assigned is not None and not segment.assigned.presence and not segment.replaces
        for segment in transform.segments
    )


def _settled_attributes(
    model: Metamodel,
    families: inheritance.InheritanceFacet,
    temporal_facet: temporal_read.TemporalFacet,
    versioning: ConcurrencyFacet,
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
        version = versioning.version_attribute(entity.identity)
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
