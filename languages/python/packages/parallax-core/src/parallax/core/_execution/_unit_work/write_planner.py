from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from operator import itemgetter
from typing import Final, Never, final

from parallax.core._execution._unit_work.acquisition_spans import form_spans
from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core._execution._unit_work.flush_facts import FlushFacts
from parallax.core._execution._unit_work.instructions import (
    AMEND_MUTATIONS,
    PreparedPredicateInstruction,
)
from parallax.core._execution._unit_work.non_temporal_settlement import NonTemporalSettlement
from parallax.core._execution._unit_work.ranges import DeferredRange
from parallax.core._execution._unit_work.strategy import (
    ActorIdentity,
    AuditDecoration,
    AuditStrategy,
    UndecoratedAudit,
)
from parallax.core._execution._unit_work.temporal_settlement import TemporalSettlement
from parallax.core._execution._unit_work.write_collapse import collapse_writes
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    ComposedTemporalWrite,
    ComposedWrite,
    InsertBatch,
    InsertionAuthorized,
    KeyedInsert,
    MutationPhase,
    NonTemporalOrderedWrite,
    OrderedWrite,
    PostRemovalInsert,
    StateObserved,
    TemporalOrderedWrite,
    TxStartConditioned,
    UnversionedLocked,
    UnversionedWriteBatch,
    VersionConditioned,
    is_licensed_by,
)
from parallax.core._execution._unit_work.write_plan import (
    PlanEntry,
    SettledWrite,
    WriteGroup,
    WritePlan,
)
from parallax.core.internal import concurrency, inheritance, relationship, temporal_read
from parallax.core.internal.concurrency import ConcurrencyFacet, ConcurrencyPreference
from parallax.core.internal.metamodel import AttributeIdentity, CompiledEntity, Metamodel
from parallax.core.internal.planned_step.payload import WritePayloadPreparer
from parallax.core.internal.planned_step.planned_rows import entity_view, planned_assignments
from parallax.core.internal.planned_step.steps import (
    ANY_COUNT,
    UNVERSIONED,
    PlannedDelete,
    PlannedUpdate,
)
from parallax.core.internal.planned_step.write_effects import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    EffectShapeOf,
    TemporalWriteOwnership,
)
from parallax.core.internal.temporal_read import Bitemporal, TransactionTimeOnly
from parallax.core.internal.temporal_write.coverage import CoverageTransform

__all__ = [
    "WritePlanner",
    "WritePlanningRequest",
]

type ComposedWrites = Sequence[ComposedWrite]

_WRITES_PER_GROUP: Final = 1024
"""The most settled writes one Write Group holds. In a group of updates or
deletes every insert waits behind every non-insert step of the group, so this
bounds how many settled writes' non-insert steps a failing insert wastes,
whatever the flush's size; a batch counts once however many rows it covers. It
is not the executor's per-call statement or row cap. Each effect shape of a
group is one statement, so a group this large applies a thousand like
amendments as one statement where a smaller one would cut them into several."""

type _FamilyKey = tuple[AttributeIdentity, object]
"""One object a settled write writes: its family's primary-key Attribute and the
value it holds, so two Entities of one Inheritance Family sharing a key value
name one object and two unrelated Entities never do."""


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
    expansion, observation validation, instant acquisition, settlement,
    grouping, or audit by hand.

    The settlement of each temporal profile it constructs here is its own,
    built over the same compiled facets and living exactly as long: a
    prepared Model Selection carries a mutually consistent model, preparation,
    planner, and settlement, and publication replaces the whole selection
    rather than rebinding any of them. So does the write payload preparer it
    is wired with, which every plan it answers is lowered through
    (:attr:`payloads`).
    """

    __slots__ = (
        "_audit",
        "_families",
        "_model",
        "_non_temporal",
        "_payloads",
        "_relationships",
        "_reserved",
        "_temporal",
        "_temporal_facet",
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
        versioning = concurrency.concurrency_facet_of(model)
        self._audit = audit
        self._payloads = payloads
        self._reserved = (
            frozenset[AttributeIdentity]()
            if isinstance(audit, UndecoratedAudit)
            else _reserved_attributes(model, self._families, self._temporal_facet, versioning)
        )
        self._temporal = TemporalSettlement(self._families, versioning, payloads)
        self._non_temporal = NonTemporalSettlement(self._families, versioning)

    @property
    def payloads(self) -> WritePayloadPreparer:
        """The model's write payload preparer, which lowers every plan this
        planner answers and every deferred range of those plans."""
        return self._payloads

    def finalize(self, request: WritePlanningRequest) -> WritePlan:
        """Plan one flush: eliminate no-ops, batch, order into mutation phases,
        settle each surviving write once, and group what settles — answering
        the plan, whose settled writes carry the source evidence their writes
        held. Admission already composed the buffer, so finalization indexes
        nothing again.

        Pure with respect to its inputs — no database I/O, no direct clock
        access, no SQL. ``request.actor_identity`` is passed to the audit port
        and never inspected. ``request.transaction_instant`` is threaded
        unevaluated until a surviving temporal write needs it.

        Batching reads an opening row's member set directly, because
        preparation already spelled every applicable member out: two rows that
        write the same row therefore reach one group key and satisfy the Planned
        Insert's own same-members rule without a canonicalizing pass here.

        An item retired before settlement — folded into a pending insert,
        cancelled against one, or eliminated as a known no-op — never settles,
        and therefore no settled write carries the evidence it was holding.
        Audit reaches every write as it settles: each row a write produces —
        an opening, or a successor carried or changed — is finalized once, and
        each update and close it emits is decorated once.

        Each ordered item settles into one settled write, which records what
        its success publishes: the states it changes, advances, or destroys,
        the rows it removes and opens, and what it leaves for the temporal
        sources it reaches. Consecutive settled writes of one mutation phase
        over distinct objects share a Write Group of at most
        :data:`_WRITES_PER_GROUP`, laid out as every write's effects, shape by
        shape where the model's payload preparer gives them shapes, and then
        every write's inserts, each write's own order kept. A write naming an
        object the open group already writes starts the next group. A deferred
        write is grouped only once execution binds it: each unbroken run of
        deferred writes within a mutation phase forms acquisition spans
        (:func:`~parallax.core._execution._unit_work.acquisition_spans.form_spans`),
        whose coverage is read together and whose leading writes with ready
        coverage execute as one group. ``request.ownership`` answers which
        current rows this attempt already opened, so a write against one of
        them revises or removes that row instead of closing it into history.

        A milestone a write leaves exactly as it was — whether its source
        observed it, an insertion authorized the write, or a caller's condition
        names it — is kept rather than closed and chained, where its unchanged
        state is proven without changing it: by the shared lock under Locking,
        by ownership for a row the attempt opened, and otherwise by a guard
        that matches the milestone at its observed or stated start — which only
        a database whose write count includes unchanged rows
        (``request.counts_unchanged_rows``) can report. Without that proof the
        milestone is closed and chained as any changed one. A pending
        insertion settles with the writes its insertion authorized as the one
        settled write of new lineages they leave of its window.
        """
        flush = FlushFacts(
            preference=request.preference,
            instant=request.transaction_instant,
            ownership=request.ownership,
            audit=self.audit_decoration(
                actor_identity=request.actor_identity,
                transaction_instant=request.transaction_instant,
            ),
            guards=request.counts_unchanged_rows,
        )
        plan = _WritePlanBuilder(effect_shape=self._payloads.effect_shape)
        families = self._families
        survivors = [
            item
            for item in (_without_noop_rows(item, families) for item in request.composed_writes)
            if item is not None
        ]
        for phase in self._mutation_phases(collapse_writes(self._model, survivors)):
            for item in phase:
                shape = self._temporal_facet.shape(item.target.identity)
                settled = (
                    self._temporal.settle(_temporal_write(item), shape, flush)
                    if isinstance(shape, TransactionTimeOnly | Bitemporal)
                    else self._non_temporal.settle(_non_temporal_write(item), flush)
                )
                if isinstance(settled, DeferredRange):
                    plan.add_deferred(settled)
                else:
                    plan.add_settled(settled, _family_keys(item, families))
            plan.close_phase()
        return plan.build()

    def audit_decoration(
        self, *, actor_identity: ActorIdentity, transaction_instant: TransactionInstant
    ) -> AuditDecoration:
        """The configured audit applied with ``actor_identity`` and
        ``transaction_instant``. Building it invokes no hook and resolves no
        instant, so one serves every write a flush settles or binds."""
        return AuditDecoration(self._audit, actor_identity, transaction_instant, self._reserved)

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

    def _mutation_phases(
        self, items: Sequence[OrderedWrite | PostRemovalInsert]
    ) -> list[MutationPhase]:
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


class _WritePlanBuilder:
    """One finalization's Write Plan as its writes settle, in flush order: the
    open Write Group's settled writes and the objects they write, the unbroken
    run of deferred writes, and every entry closed so far."""

    __slots__ = ("_deferred", "_effect_shape", "_entries", "_held", "_writes")

    def __init__(self, *, effect_shape: EffectShapeOf) -> None:
        self._effect_shape = effect_shape
        self._entries: list[PlanEntry] = []
        self._writes: list[SettledWrite] = []
        self._held: set[_FamilyKey] = set()
        self._deferred: list[DeferredRange] = []

    def add_settled(self, write: SettledWrite, keys: tuple[_FamilyKey, ...]) -> None:
        """``write``, of the objects ``keys`` names, joins the open group
        once the run of deferred writes before it closes; a full group, or one
        already writing one of those objects, closes first."""
        self._close_run()
        if len(self._writes) == _WRITES_PER_GROUP or not self._held.isdisjoint(keys):
            self._close_group()
        self._writes.append(write)
        self._held.update(keys)

    def add_deferred(self, deferred: DeferredRange) -> None:
        """``deferred`` closes the open group and extends the run of deferred
        writes."""
        self._close_group()
        self._deferred.append(deferred)

    def close_phase(self) -> None:
        """A mutation phase ends: no group or span crosses it."""
        self._close_run()
        self._close_group()

    def build(self) -> WritePlan:
        return WritePlan(tuple(self._entries))

    def _close_run(self) -> None:
        """End the unbroken run of deferred writes: its acquisition spans are
        the plan's next entries."""
        deferred = self._deferred
        if deferred:
            self._entries.extend(form_spans(deferred))
            deferred.clear()

    def _close_group(self) -> None:
        writes = self._writes
        if writes:
            self._entries.append(WriteGroup.from_writes(writes, effect_shape=self._effect_shape))
            writes.clear()
        self._held.clear()


def _family_keys(
    item: OrderedWrite, families: inheritance.InheritanceFacet
) -> tuple[_FamilyKey, ...]:
    """The objects ``item`` writes, by its family's key."""
    objects = (
        item.object_keys
        if isinstance(item, InsertBatch | UnversionedWriteBatch)
        else (item.object_key,)
    )
    attribute = entity_view(families, item.target).primary_key.identity
    keys: list[_FamilyKey] = []
    for key in objects:
        ((_, value),) = key.primary_key
        keys.append((attribute, value))
    return tuple(keys)


def _temporal_write(item: OrderedWrite) -> TemporalOrderedWrite:
    """``item``, a write of a temporal object, as temporal settlement reads it."""
    # Batching joins no temporal write, and only an observation, an insertion,
    # or a caller's stated start licenses one of existing coverage.
    assert (
        isinstance(item, ComposedTemporalWrite | ComposedBitemporalOpening | KeyedInsert)
        or is_licensed_by(item, StateObserved)
        or is_licensed_by(item, InsertionAuthorized)
        or is_licensed_by(item, TxStartConditioned)
    )
    return item


def _non_temporal_write(item: OrderedWrite) -> NonTemporalOrderedWrite:
    """``item``, a write of a Non-Temporal object, as Non-Temporal settlement
    reads it."""
    # Only a temporal object's writes compose or state a Transaction-Time start.
    assert (
        isinstance(item, KeyedInsert | InsertBatch | UnversionedWriteBatch)
        or is_licensed_by(item, StateObserved)
        or is_licensed_by(item, UnversionedLocked)
        or is_licensed_by(item, VersionConditioned)
        or is_licensed_by(item, InsertionAuthorized)
    )
    return item


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
    if is_licensed_by(item, VersionConditioned):
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


def _reserved_attributes(
    model: Metamodel,
    families: inheritance.InheritanceFacet,
    temporal_facet: temporal_read.TemporalFacet,
    versioning: ConcurrencyFacet,
) -> frozenset[AttributeIdentity]:
    """Every Attribute of ``model`` whose value settlement alone decides — each
    Entity's primary key, temporal bounds, and optimistic version — which no
    audit answer may state."""
    reserved: set[AttributeIdentity] = set()
    for entity in model.entities:
        position = families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
        reserved.add(position.primary_key.identity)
        version = versioning.version_attribute(entity.identity)
        if version is not None:
            reserved.add(version)
        shape = temporal_facet.shape(entity.identity)
        if isinstance(shape, temporal_read.Bitemporal):
            axes = (shape.valid_time, shape.transaction_time)
        elif isinstance(shape, temporal_read.TransactionTimeOnly):
            axes = (shape.transaction_time,)
        else:
            axes = ()
        for axis in axes:
            reserved.update((axis.start_attribute, axis.end_attribute))
    return frozenset(reserved)
