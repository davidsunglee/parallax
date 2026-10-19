from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from operator import itemgetter

from parallax.core import inheritance, relationship, temporal_read
from parallax.core._execution._unit_work.acquisition import AcquireRows
from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core._execution._unit_work.instructions import (
    AMEND_MUTATIONS,
    ASSIGNMENT_MUTATIONS,
    DESTRUCTIVE_MUTATIONS,
    INSERT_MUTATIONS,
    ExpectedVersion,
    PreparedKeyedWrite,
    PreparedWrite,
    derive_keyed_write,
)
from parallax.core._execution._unit_work.ranges import (
    DeferredGroupRange,
    DeferredTemporalRange,
    GroupContinuation,
    bind_deferred,
)
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
    AfterRemoval,
    BufferedWrite,
    ComposedTemporalWrite,
    FollowingKeyedWrite,
    InsertionKeyedWrite,
    MaterializedWriteGroup,
    ObservedKeyedWrite,
    OrderedWrite,
    PendingOpening,
    ReadlessPredicateWrite,
    TargetKeyedWrite,
    buffered_instruction,
)
from parallax.core._execution._unit_work.write_settlement import WritePlanCompiler
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, EntityMetadata, Metamodel
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    TemporalWriteOwnership,
    WritePlan,
)

__all__ = [
    "WritePlanner",
    "WritePlanningRequest",
]

type BufferedWrites = Sequence[BufferedWrite]


@dataclass(frozen=True, slots=True, kw_only=True)
class WritePlanningRequest:
    """One flush's complete planning input.

    Keyword-only and Actor Identity first: planning occurs under already
    captured Execution Authority, and field order emphasizes that without
    making it a positional API.

    ``buffered_writes`` is the pending batch as
    :class:`~parallax.core._execution._unit_work.admission.WriteAdmission`
    composed it, in authored order: one item per coalesced write, one composed
    write per temporal object's observed writes, and no write a later one
    cancelled. ``ownership`` answers which current temporal rows the planning
    attempt already opened; planning reads it and never changes it.
    ``counts_unchanged_rows`` says the database's write count includes rows an
    update matched and left unchanged, so a guard can prove a milestone a write
    leaves unchanged (`m-dialect`).
    """

    actor_identity: ActorIdentity
    transaction_instant: TransactionInstant
    concurrency: Concurrency
    buffered_writes: BufferedWrites
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP
    counts_unchanged_rows: bool = False


class WritePlanner:
    """The model-scoped, stateless Write Planner (`m-unit-work`).

    Constructed once per accepted Metamodel with its strategy adapters already
    wired; :meth:`finalize` plans a flush, :meth:`bind_deferred` binds a
    deferred range of a plan it finalized once that range's coverage is read,
    and :meth:`prepare_group` answers the continuation a deferred group of such
    a plan settles through. No caller sequences coalescing, batching, ordering, temporal expansion,
    observation validation, instant acquisition, or audit by hand.

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
        planner answers and every range it binds."""
        return self._payloads

    def finalize(self, request: WritePlanningRequest) -> WritePlan:
        """Plan one flush: eliminate no-ops, batch, order, and hand the whole
        ordered sequence to the compiler — answering the plan, whose execution
        units carry the claims the settled writes held. Admission already
        composed the batch, so finalization indexes nothing again.

        Pure with respect to its inputs — no database I/O, no direct clock
        access, no SQL. ``request.actor_identity`` is accepted and never
        inspected. ``request.transaction_instant`` is threaded unevaluated
        until a surviving temporal mutation needs it.

        Batching reads an opening row's member set directly, because
        preparation already spelled every applicable member out: two rows that
        write the same row therefore reach one group key and satisfy the Planned
        Insert's own same-members rule without a canonicalizing pass here.

        The three stages here REWRITE the sequence — drop, split, reorder.
        The Write Plan
        :meth:`~parallax.core._execution._unit_work.write_settlement.WritePlanCompiler.compile`
        answers is returned unchanged, because packing, provenance, and each
        unit's claim are decided there and nothing is left for the planner to add.
        """
        survivors = [
            item
            for item in (
                _without_noop_rows(item, self._families, self._temporal_facet)
                for item in request.buffered_writes
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

    def bind_deferred(
        self,
        description: DeferredTemporalRange,
        reused: PredecessorRows | None,
        acquired: Sequence[PredecessorRows],
        /,
        *,
        ownership: TemporalWriteOwnership,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> BoundRange:
        """Bind a deferred range this planner finalized to the starting rows it
        ``reused`` and the coverage ``acquired`` for it, each ``None`` or empty
        where there was none.

        Its temporal meaning, concurrency, and gates were fixed when the plan
        was made; binding reads ``ownership`` as the running flush's earlier
        units left it and never recaptures the instant. The configured audit
        finalizes each row the binding produces once, and decorates each close
        it emits, with ``actor_identity`` and ``transaction_instant``, changing no
        topology and classifying no gate.
        """
        return bind_deferred(
            description,
            reused,
            acquired,
            ownership=ownership,
            audit=AuditDecoration(self._audit, actor_identity, transaction_instant, self._settled),
            payloads=self._payloads,
        )

    def prepare_group(
        self,
        description: DeferredGroupRange,
        /,
        *,
        acquire_rows: AcquireRows,
        ownership: TemporalWriteOwnership,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> GroupContinuation:
        """The continuation that settles a deferred group this planner
        finalized, batch by batch, reading each batch's coverage through
        ``acquire_rows`` under ``ownership`` as the running flush's earlier
        units left it; the configured audit finalizes each row it produces once
        and decorates each close it emits, with ``actor_identity`` and
        ``transaction_instant``."""
        return GroupContinuation(
            description,
            acquire_rows=acquire_rows,
            ownership=ownership,
            audit=AuditDecoration(self._audit, actor_identity, transaction_instant, self._settled),
            payloads=self._payloads,
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

    def _form_batches(self, buffer: Sequence[BufferedWrite]) -> list[BufferedWrite]:
        result: list[BufferedWrite] = []
        run: list[PreparedKeyedWrite] = []
        run_group: object = None

        def group_key(item: PreparedKeyedWrite) -> object:
            return self._batching.group_key(self._model, item.target, item.mutation, item.rows[0])

        def flush_run() -> None:
            if not run:
                return
            entity = run[0].target
            rows = [row for w in run for row in w.rows]
            if len(run) == 1:
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
        for item in _decomposed_updates(buffer, self._temporal_facet):
            if isinstance(item, PreparedKeyedWrite) and len(item.rows) == 1:
                item_group = group_key(item)
                if (
                    run
                    and run[-1].target == item.target
                    and run[-1].mutation == item.mutation
                    and run[-1].valid_time_window == item.valid_time_window
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

    def _order(self, items: Sequence[BufferedWrite]) -> list[OrderedWrite]:
        """``items`` in flush order: each readless predicate write stays where it
        was authored, and within each region between them inserts go in
        ascending referential rank, then updates in authored order, then deletes
        in descending rank. Both sorts are stable. Inserts that depend on an
        earlier removal open a new region, as a barrier does, so the removal
        precedes them while they still order with what follows them."""
        ordered: list[OrderedWrite] = []
        inserts: list[tuple[int, OrderedWrite]] = []
        updates: list[OrderedWrite] = []
        deletes: list[tuple[int, OrderedWrite]] = []

        def close_region() -> None:
            inserts.sort(key=_RANK)
            deletes.sort(key=_RANK, reverse=True)
            ordered.extend(item for _, item in inserts)
            ordered.extend(updates)
            ordered.extend(item for _, item in deletes)
            inserts.clear()
            updates.clear()
            deletes.clear()

        for item in items:
            if isinstance(item, ReadlessPredicateWrite):
                close_region()
                ordered.append(item)
                continue
            if isinstance(item, AfterRemoval):
                # Everything authored before the removal-dependent insert
                # executes first, the removal it depends on included; what is
                # authored after it orders with it as usual.
                close_region()
                item = item.insert
            if isinstance(item, ComposedTemporalWrite):
                if item.assigns:
                    updates.append(item)
                else:
                    deletes.append((self._ranked(item.target), item))
                continue
            instruction = _ordered_instruction(item)
            if instruction.mutation in ASSIGNMENT_MUTATIONS:
                updates.append(item)
            elif instruction.mutation in INSERT_MUTATIONS:
                inserts.append((self._rank(instruction), item))
            elif instruction.mutation in DESTRUCTIVE_MUTATIONS:
                deletes.append((self._rank(instruction), item))
        close_region()
        return ordered

    def _rank(self, instruction: PreparedWrite) -> int:
        return self._ranked(_instruction_target(instruction))

    def _ranked(self, entity: EntityMetadata) -> int:
        rank = self._relationships.referential_rank(entity.identity)
        return 0 if rank is None else rank


_RANK = itemgetter(0)


def _decomposed_updates(
    buffer: Sequence[BufferedWrite], temporal_facet: temporal_read.TemporalFacet
) -> list[BufferedWrite]:
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
    A TEMPORAL entry is left whole too, so settlement still refuses it as the
    multi-row milestone chain it is rather than silently settling it as several
    chains the caller never authored.
    """
    decomposed: list[BufferedWrite] = []
    for item in buffer:
        if not isinstance(item, PreparedKeyedWrite) or not _splits_into_rows(item, temporal_facet):
            decomposed.append(item)
            continue
        decomposed.extend(derive_keyed_write(item, (row,)) for row in item.rows)
    return decomposed


def _splits_into_rows(
    item: PreparedKeyedWrite, temporal_facet: temporal_read.TemporalFacet
) -> bool:
    if len(item.rows) < 2 or item.mutation not in ASSIGNMENT_MUTATIONS:
        return False
    return not _is_temporal(temporal_facet, item.target)


def _is_temporal(temporal_facet: temporal_read.TemporalFacet, entity: EntityMetadata) -> bool:
    return isinstance(
        temporal_facet.shape(entity.identity),
        temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
    )


def _key_name(families: inheritance.InheritanceFacet, entity: EntityMetadata) -> str:
    position = families.entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    return position.primary_key.identity.name


def _merge_rows(run: Sequence[PreparedKeyedWrite]) -> PreparedKeyedWrite:
    """One multi-row :class:`PreparedKeyedWrite` carrying every row of ``run``'s
    single-row instructions, in run (buffer) order — the same
    entity/mutation/Valid-Time window every member of the run already shares."""
    first = run[0]
    return derive_keyed_write(first, tuple(row for w in run for row in w.rows))


def _instruction_target(instruction: PreparedWrite) -> EntityMetadata:
    if isinstance(instruction, PreparedKeyedWrite):
        return instruction.target
    # A readless predicate write is always a barrier in `_order`, never a
    # region member `_rank` resolves against — but a Materialized Write
    # Group's own `mutation` IS a `PredicateWrite`, and a group ranks as an
    # ordinary region member, so this arm is reached for one.
    return instruction.selection.target


def _without_noop_rows(
    item: BufferedWrite,
    families: inheritance.InheritanceFacet,
    temporal_facet: temporal_read.TemporalFacet,
) -> BufferedWrite | None:
    """``item`` with its known no-op rows gone, or ``None`` when none survive.

    An update row naming only key members changes nothing: a key ADDRESSES the
    row rather than assigns to it, so such a row is known no-op work and stage 2
    removes it (`m-unit-work` "eliminate known cancellation and no-op work").

    Elimination is per ROW, not per instruction, because a preformed multi-row
    update mixing a key-only row with an assigning one is not empty as a whole
    and would therefore survive an instruction-level test — only to be split
    into its rows during batching and hand the key-only child to the update
    settlement, which has no member to write.
    Removing the row HERE keeps that child from ever existing and keeps the
    elimination at stage 2, ahead of batching and of the Transaction Instant,
    where the normative stage order puts it.

    A PLURAL temporal instruction is passed through whole and unexamined, so
    that settlement refuses it as the shape it is
    (`m-unit-work` "A temporal keyed instruction carries exactly one row").
    That singleton contract admits no exception, which rules out BOTH reductions
    stage 2 could otherwise reach for: narrowing it to its assigning rows would
    silently discard a milestone chain the author wrote, and eliminating it
    whole — the shape every one of its rows is key-only — would silently
    discard all of them and return a plan that says nothing was wrong. Only a
    SINGLE-row temporal instruction is measured, and then only for the
    all-or-nothing outcome a single row can have.
    An observation carrier is single-row by construction, so it is either
    eliminated whole or passed through untouched, and is never rebuilt around a
    narrower instruction.
    """
    if isinstance(
        item, ComposedTemporalWrite | PendingOpening | AfterRemoval | FollowingKeyedWrite
    ):
        return item
    if isinstance(item, TargetKeyedWrite) and isinstance(item.expectation, ExpectedVersion):
        # A caller-conditioned write of a versioned row still advances its
        # version, which is the revision its caller asked for.
        return item
    instruction = buffered_instruction(item)
    if (
        not isinstance(instruction, PreparedKeyedWrite)
        or instruction.mutation not in AMEND_MUTATIONS
    ):
        return item
    entity = instruction.target
    if len(instruction.rows) > 1 and _is_temporal(temporal_facet, entity):
        return item
    key_name = _key_name(families, entity)
    kept = tuple(row for row in instruction.rows if not all(name == key_name for name in row))
    if not kept:
        return None
    if len(kept) == len(instruction.rows):
        return item
    return derive_keyed_write(instruction, kept)


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


def _ordered_instruction(
    item: PreparedKeyedWrite
    | ReadlessPredicateWrite
    | ObservedKeyedWrite
    | InsertionKeyedWrite
    | TargetKeyedWrite
    | FollowingKeyedWrite
    | PendingOpening
    | MaterializedWriteGroup,
) -> PreparedWrite:
    """The instruction ordering ranks ``item`` by: a pending opening's own
    insert, and the write a barrier keeps after earlier ones."""
    if isinstance(item, FollowingKeyedWrite):
        return item.write.instruction
    if isinstance(item, PendingOpening):
        return item.insert
    return buffered_instruction(item)
