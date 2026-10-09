from __future__ import annotations

import heapq
from collections.abc import Hashable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from operator import attrgetter, itemgetter
from typing import Final, cast

from parallax.core import inheritance, relationship, temporal_read
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import TimeInterval, milestone_edge, valid_time_coverage
from parallax.core.temporal_write.coverage import NO_TRANSFORM
from parallax.core.unit_work.acquisition import AcquireRows
from parallax.core.unit_work.claims import (
    ClaimVerdict,
    WriteIntent,
    admits,
    admits_composed,
    keyed_intent,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.instructions import (
    AMEND_MUTATIONS,
    ASSIGNMENT_MUTATIONS,
    DESTRUCTIVE_MUTATIONS,
    INSERT_MUTATIONS,
    REPLACE_MUTATIONS,
    ExpectedVersion,
    PreparedKeyedWrite,
    PreparedWrite,
    derive_keyed_write,
)
from parallax.core.unit_work.keys import resolve_object_key
from parallax.core.unit_work.materialized import (
    AfterRemoval,
    BufferItem,
    ChainedTemporalWrite,
    ClaimedKeyedWrite,
    ComposedTemporalWrite,
    FollowingKeyedWrite,
    InsertionKeyedWrite,
    MaterializedWriteGroup,
    ObjectClaimedWrite,
    ObservedKeyedWrite,
    PendingOpening,
    ReadlessPredicateWrite,
    TargetKeyedWrite,
    TemporalContribution,
    TemporalKeyedWrite,
    buffered_instruction,
    chained,
    composed_temporal_write,
    temporal_contribution,
)
from parallax.core.unit_work.ranges import (
    DeferredGroupRange,
    DeferredTemporalRange,
    GroupContinuation,
    bind_deferred,
)
from parallax.core.unit_work.retain import RetainedObservation
from parallax.core.unit_work.strategy import (
    ActorIdentity,
    AuditDecoration,
    AuditStrategy,
    BatchingStrategy,
    Concurrency,
    ConcurrencyStrategy,
    UndecoratedAudit,
)
from parallax.core.unit_work.write_settlement import OrderedWrite, WritePlanCompiler
from parallax.core.write_plan.keys import ObjectKey, ObservedStateKey, VersionedStateKey
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.observe import TemporalObservation
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    SourceAuthority,
    TemporalWriteOwnership,
    WritePlan,
)

__all__ = [
    "BufferedWrite",
    "PendingWrites",
    "WritePlanner",
    "WritePlanningRequest",
    "compose_writes",
]

type BufferedWrite = OrderedWrite | AfterRemoval
"""One composed buffered write as finalization receives it: what settlement
reads, or inserts that must follow an earlier removal."""

type BufferedWrites = Sequence[BufferedWrite]


@dataclass(frozen=True, slots=True, kw_only=True)
class WritePlanningRequest:
    """One flush's complete planning input.

    Keyword-only and Actor Identity first: planning occurs under already
    captured Execution Authority, and field order emphasizes that without
    making it a positional API.

    ``buffered_writes`` is the buffer as :class:`PendingWrites` composed it at
    admission, in authored order: one item per coalesced write, one composed
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
    wired; :meth:`finalize` plans a flush, and :meth:`bind_deferred` binds a
    deferred range of a plan it finalized once that range's coverage is read.
    No caller sequences coalescing, batching, ordering, temporal expansion,
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
        composed the buffer (:class:`PendingWrites`), so finalization indexes
        nothing again.

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
        :meth:`~parallax.core.unit_work.write_settlement.WritePlanCompiler.compile`
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
        )

    def continue_group(
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


def _merge_assignment_into_insert(
    insert: PreparedKeyedWrite,
    assigned: PreparedKeyedWrite,
    families: inheritance.InheritanceFacet,
) -> PreparedKeyedWrite:
    """Overlay ``assigned``'s non-key row fields onto ``insert``'s row.

    The coalesced write keeps the insert's mutation verb and Valid-Time window
    (so it still opens a current milestone / fully-current rectangle at
    settling per temporal flavor) but carries the FINAL values — no
    ``INSERT`` + ``UPDATE``.
    """
    key_name = _key_name(families, insert.target)
    merged = dict(insert.rows[0])
    for name, value in assigned.rows[0].items():
        if name != key_name:
            merged[name] = value
    return derive_keyed_write(insert, (merged,))


type PendingTemporal = TemporalKeyedWrite | ComposedTemporalWrite
"""What a temporal object's pending writes against its existing coverage are:
one write still alone, or several composed."""


class PendingWrites:
    """A buffer's writes, composed by the planner's rules as each is admitted.

    The one composition owner: a unit of work adds each write it admits, so the
    buffer it hands finalization is already composed, and a caller holding an
    uncomposed sequence folds it through :func:`compose_writes`. Composition
    follows authored order:

    * an amendment or replacement of an object whose insert is still pending
      folds into that insert, and a destructive write of it cancels the pair; a
      Bitemporal opening composes them over its coverage instead
      (:class:`~parallax.core.unit_work.materialized.PendingOpening`);
    * writes claiming one non-temporal scope coalesce by the claim algebra
      (:func:`~parallax.core.unit_work.claims.admits`);
    * a write a caller addressed with its own starting condition
      (:class:`~parallax.core.unit_work.materialized.TargetKeyedWrite`) claims
      the scope that condition names and composes there like any claimed
      write, keeping the condition through every overwrite and destruction;
    * a temporal object's writes against its existing coverage — observed ones,
      those an admitted insertion authorized, and those a caller addressed
      alike — compose into one
      :class:`~parallax.core.unit_work.materialized.ComposedTemporalWrite`
      (:meth:`admits_temporal`), whose transform keeps only surviving values
      while every write's condition stays. Two writes of one observed state over
      one window simply coalesce, as a non-temporal pair does. Writes of the
      object over disjoint windows stay separate operations inside it, each with
      its own condition. A readless predicate write is an ordering barrier no
      write crosses, so the object's writes on each side of one compose apart
      (:class:`~parallax.core.unit_work.materialized.ChainedTemporalWrite`),
      though admission still judges each arriving write against all of them.

    No write composes across a readless predicate write, which is an ordering
    barrier: a write of an object whose insert stands before one is a write of
    the row that insert opens, and a Non-Temporal write of a scope whose
    earlier write stands before one follows it as a write of its own
    (:class:`~parallax.core.unit_work.materialized.FollowingKeyedWrite`).

    A pair the algebra calls incompatible is one no verb admitted — a caller
    reached the buffer another way — and both writes are left standing rather
    than combined by a rule neither states.
    """

    __slots__ = (
        "_after_removal",
        "_claims",
        "_ended",
        "_families",
        "_inserts",
        "_items",
        "_objects",
        "_regions",
        "_removals",
        "_sources",
        "_targets",
        "_temporal",
        "_temporal_facet",
    )

    def __init__(self, model: Metamodel) -> None:
        self._families = inheritance.view(model)
        self._temporal_facet = temporal_read.view(model)
        self._items: list[BufferItem | ComposedTemporalWrite | PendingOpening | None] = []
        self._inserts: dict[ObjectKey, int] = {}
        # Where each still-open claim sits, by its scope: one per exact observed
        # state, or the object itself for an object claim. Two observed
        # generations of one versioned row hold two independent claims, and
        # writes of them interleave freely.
        self._claims: dict[Hashable, int] = {}
        self._temporal: dict[ObjectKey, int] = {}
        self._sources: list[SourceAuthority] = []
        # Objects a pending write removes whole, and the positions of inserts
        # that must follow a removal of an earlier insertion — each allocated by
        # the first write it records, since most buffers hold neither.
        self._removals: set[ObjectKey] | None = None
        self._after_removal: set[int] | None = None
        # Objects whose ended Bitemporal opening still settles the stored
        # coverage its replacement reached, which a further insert follows.
        self._ended: set[ObjectKey] | None = None
        # The scope each object's claimed writes stand at, and the scope of each
        # object's pending caller-conditioned write — both allocated by the first
        # such write, since a buffer holding none needs neither.
        self._objects: dict[ObjectKey, Hashable] | None = None
        self._targets: dict[ObjectKey, Hashable] | None = None
        # Where the latest barrier stands and what the regions before it hold —
        # allocated by the first barrier, since most buffers carry none.
        self._regions: _Regions | None = None

    def __bool__(self) -> bool:
        return bool(self._items)

    def temporal(self, key: ObjectKey) -> PendingTemporal | None:
        """The pending writes of temporal object ``key`` against its existing
        coverage in the current barrier region, if any."""
        index = self._temporal.get(key)
        if index is None:
            return None
        held = self._items[index]
        assert isinstance(held, _TEMPORAL)
        return held

    def _compositions(self, key: ObjectKey, after: int = -1) -> tuple[PendingTemporal, ...]:
        """Every pending composition of temporal object ``key`` buffered after
        position ``after``, in authored order, one per barrier region that
        writes it."""
        held = self.temporal(key)
        # The current region follows every position a caller asks after.
        assert held is None or self._temporal[key] > after
        sealed = None if self._regions is None else self._regions.temporal.get(key)
        if sealed is None:
            return () if held is None else (held,)
        items = self._items
        earlier = tuple(cast("PendingTemporal", items[index]) for index in sealed if index > after)
        return earlier if held is None else (*earlier, held)

    def states_window(self, key: ObjectKey, window: TimeInterval | None) -> bool:
        """Whether a pending write of temporal object ``key`` states exactly
        ``window`` as its own."""
        return any(
            contribution.valid_time_window == window
            for held in self._compositions(key)
            for contribution in _contributions(held)
        )

    def verdict(
        self, item: ClaimedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite, key: ObjectKey
    ) -> ClaimVerdict:
        """What a non-temporal claimed write becomes against the write pending
        at its own scope (:func:`~parallax.core.unit_work.claims.admits`)."""
        intent = keyed_intent(item.instruction)
        assert intent is not None  # no carrier wraps an insert
        return admits(self._held_intent(_claim_scope(item, key)), intent)

    def admits_target(self, item: TargetKeyedWrite, key: ObjectKey) -> bool:
        """Whether a caller-conditioned write of ``key`` joins the writes of the
        object already pending: none may stand at another scope — a different
        stated revision, or a state some other source observed — since one
        object's writes cannot start from two states, and the write it meets at
        its own scope must admit it (:func:`~parallax.core.unit_work.claims.admits`)."""
        objects = self._objects
        if objects is None:
            objects = self._index_objects()
        held = objects.get(key)
        if held is not None and held != item.scope:
            return False
        return self.verdict(item, key) != "incompatible"

    def target_scope(self, key: ObjectKey) -> Hashable | None:
        """The scope of the caller-conditioned write of ``key`` still pending,
        if any — the one scope every other write of the object must share."""
        targets = self._targets
        return None if targets is None else targets.get(key)

    def holds_scope(self, scope: Hashable) -> bool:
        """Whether a pending keyed write claims ``scope``."""
        return scope in self._claims

    def _index_objects(self) -> dict[ObjectKey, Hashable]:
        objects: dict[ObjectKey, Hashable] = {}
        for scope in self._claims:
            _note_scope(objects, _scope_object(scope), scope)
        self._objects = objects
        return objects

    def opening_admits(self, key: ObjectKey, instruction: PreparedKeyedWrite) -> bool:
        """Whether ``instruction`` composes with the still-pending opening of
        ``key``: an assignment never reaches coverage an earlier write of the
        opening destroyed, and a destruction overlapping an earlier write
        states exactly its window (:func:`~parallax.core.unit_work.claims.admits_composed`)."""
        index = self._inserts.get(key)
        held = None if index is None else self._items[index]
        if not isinstance(held, PendingOpening):
            return True
        intent = keyed_intent(instruction)
        assert intent is not None  # an opening's own writes are no inserts
        return (
            admits_composed(((None, held_intent) for held_intent in held.intents), None, intent)
            != "incompatible"
        )

    def admits_temporal(self, item: TemporalKeyedWrite, key: ObjectKey) -> bool:
        """Whether ``item``, a write of temporal object ``key`` against its
        existing coverage, composes with that object's pending writes — every
        one of them, in every barrier region, overwritten ones included.

        Observed writes and those an insertion authorized compose with each
        other by the window algebra
        (:func:`~parallax.core.unit_work.claims.admits_composed`). A write a
        caller addressed meets each other write of the object on its own terms:

        * over exactly its window, the two start from one state — the caller's
          stated Transaction-Time start and the observed rectangle's agreeing —
          and no assignment follows a destruction;
        * over a disjoint window, adjacent ones included, the two are separate
          operations, unless an observed rectangle holds the caller's start at
          another Transaction-Time start, which no current coverage can satisfy;
        * over any other overlapping window, never.
        """
        compositions = self._compositions(key)
        if not compositions:
            return True
        intent = keyed_intent(item.instruction)
        assert intent is not None  # a write against existing coverage is no insert
        scope = (
            item.claim.key
            if isinstance(item, ObservedKeyedWrite) and item.claim is not None
            else None
        )
        if not isinstance(item, TargetKeyedWrite) and not any(
            _targeted(held) for held in compositions
        ):
            return (
                admits_composed(
                    (pair for held in compositions for pair in composed_intents(held)),
                    scope,
                    intent,
                )
                != "incompatible"
            )
        entity = item.instruction.target
        arriving = temporal_contribution(item)
        start = self._starting_revision(entity, arriving)
        untargeted: list[tuple[ObservedStateKey | None, WriteIntent]] = []
        for held in compositions:
            for contribution in _contributions(held):
                if arriving.condition is None and contribution.condition is None:
                    untargeted.append((_scope(contribution), _intent(contribution)))
                elif not self._separable(entity, contribution, arriving, start):
                    return False
        return admits_composed(untargeted, scope, intent) != "incompatible"

    def _separable(
        self,
        entity: EntityMetadata,
        held: TemporalContribution,
        arriving: TemporalContribution,
        start: object | None,
    ) -> bool:
        """Whether two writes of one temporal object, at least one a caller
        addressed, can stand together: as one exact-window operation, or as
        separate ones over disjoint windows (:meth:`admits_temporal`)."""
        held_window = held.valid_time_window
        arriving_window = arriving.valid_time_window
        if held_window == arriving_window:
            return (
                not (held.kind == "destructive" and arriving.kind == "assignment")
                and start is not None
                and self._starting_revision(entity, held) == start
            )
        # Writes without Valid Time span the whole axis, so every two of an
        # object's are equal and only Valid-Time windows differ.
        assert held_window is not None and arriving_window is not None
        if held_window.overlaps(arriving_window):
            return False
        return self._rectangle_admits(entity, held, arriving) and self._rectangle_admits(
            entity, arriving, held
        )

    def _rectangle_admits(
        self,
        entity: EntityMetadata,
        addressed: TemporalContribution,
        observed: TemporalContribution,
    ) -> bool:
        """Whether ``observed``'s rectangle, where it holds ``addressed``'s
        start, stands at the Transaction-Time start that caller stated."""
        condition = addressed.condition
        observation = observed.observation
        if condition is None or not isinstance(observation, TemporalObservation):
            return True
        shape = self._temporal_facet.shape(entity.identity)
        assert isinstance(shape, temporal_read.Bitemporal)  # disjoint windows are Valid Time's
        window = addressed.valid_time_window
        predecessor = observation.predecessor
        coverage = valid_time_coverage(shape, predecessor, None)
        assert window is not None and coverage is not None  # both lie on Valid Time
        if not coverage.contains(window.start):
            return True
        return milestone_edge(shape, predecessor, None).tx_time == condition.instant

    def _starting_revision(
        self, entity: EntityMetadata, contribution: TemporalContribution
    ) -> object | None:
        """The Transaction-Time start ``contribution`` requires of the coverage
        at its window's start: its caller's, or the observed rectangle's own.
        An insertion's write states none."""
        if contribution.condition is not None:
            return contribution.condition.instant
        observation = contribution.observation
        if not isinstance(observation, TemporalObservation):
            return None
        shape = self._temporal_facet.shape(entity.identity)
        assert shape is not None  # the facet covers every accepted Entity
        return milestone_edge(shape, observation.predecessor, None).tx_time

    def holds(self, state: ObservedStateKey) -> bool:
        """Whether a pending keyed write claims observed state ``state``."""
        if state in self._claims:
            return True
        return any(
            scope == state
            for held in self._compositions(state.object)
            for scope, _intent in composed_intents(held)
        )

    def removes(self, key: ObjectKey) -> bool:
        """Whether a pending write removes object ``key`` whole: a deletion of a
        Non-Temporal object, or a termination of a Transaction-Time-Only one."""
        removals = self._removals
        return removals is not None and key in removals

    def removals(self) -> tuple[ObjectKey, ...]:
        """Every object a pending write removes whole (:meth:`removes`)."""
        removals = self._removals
        return () if removals is None else tuple(removals)

    def destroyed_coverage(
        self, key: ObjectKey, *, after_opening: bool = False
    ) -> Iterator[TimeInterval]:
        """The Valid-Time intervals the pending writes of Bitemporal object
        ``key`` destroy, ordered by start — with ``after_opening``, only those
        buffered after its pending insert.

        Each barrier region's composition yields its own destroyed segments,
        already ordered, and a lone destructive write its prepared window.
        Regions stand in authored order rather than temporal order, so their
        streams are merged by start, holding one interval per region rather
        than copying any. Duplicate and overlapping intervals may remain. The
        view reads the buffer as it stands, so it is consumed before the buffer
        changes.
        """
        streams = [
            _destroyed(held)
            for held in self._compositions(key, self._inserts[key] if after_opening else -1)
        ]
        if len(streams) == 1:
            return streams[0]
        return heapq.merge(*streams, key=_START)

    def _held_intent(self, scope: Hashable) -> WriteIntent | None:
        index = self._claims.get(scope)
        held = None if index is None else self._items[index]
        assert held is None or isinstance(
            held, ObservedKeyedWrite | ObjectClaimedWrite | InsertionKeyedWrite | TargetKeyedWrite
        )
        return None if held is None else keyed_intent(held.instruction)

    def is_bitemporal_target(self, instruction: PreparedKeyedWrite) -> bool:
        """Whether ``instruction``'s target is a Bitemporal Entity."""
        return isinstance(
            self._temporal_facet.shape(instruction.target.identity), temporal_read.Bitemporal
        )

    def is_temporal(self, item: BufferItem) -> bool:
        """Whether ``item`` is a write of a temporal object against its existing
        coverage, the writes that compose by object rather than by claimed
        scope."""
        return isinstance(
            item, ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite
        ) and _is_temporal(self._temporal_facet, item.instruction.target)

    def add(
        self, item: BufferItem, key: ObjectKey | None = None, *, after_removal: bool = False
    ) -> bool:
        """Compose ``item`` into the pending writes, in authored order, and
        answer whether it cancelled the pending insert of its object.

        ``key`` is the object ``item`` addresses where the caller already
        derived it, so the index shares that key rather than deriving its own.
        ``after_removal`` marks an insert that must execute after every write
        authored before it, because one of those removes an earlier insertion
        of its object.
        """
        items = self._items
        if isinstance(item, ObjectClaimedWrite) and item.source is not None:
            self._sources.append(item.source)
        if isinstance(item, MaterializedWriteGroup):
            items.append(item)
            return False
        instruction = buffered_instruction(item)
        if key is None:
            key = resolve_object_key(instruction, self._families)
        if not isinstance(instruction, PreparedKeyedWrite) or key is None:
            if isinstance(item, ReadlessPredicateWrite):
                self._seal()
            items.append(item)
            return False
        if instruction.mutation in INSERT_MUTATIONS:
            items.append(item)
            index = len(items) - 1
            self._inserts[key] = index
            if after_removal or (self._ended is not None and key in self._ended):
                if self._after_removal is None:
                    self._after_removal = set()
                self._after_removal.add(index)
            return False
        if self.folds_into_opening(key):
            return self._fold_into_opening(instruction, key)
        self._add_existing(item, instruction, key)
        return False

    def _add_existing(
        self, item: BufferItem, instruction: PreparedKeyedWrite, key: ObjectKey
    ) -> None:
        """Compose a write against existing state into the pending writes."""
        if instruction.mutation in DESTRUCTIVE_MUTATIONS and not self.is_bitemporal_target(
            instruction
        ):
            if self._removals is None:
                self._removals = set()
            self._removals.add(key)
        if self.is_temporal(item):
            assert isinstance(item, ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite)
            # A retained claim already holds its object's key, so the index
            # shares it rather than keeping one of its own.
            claim = item.claim if isinstance(item, ObservedKeyedWrite) else None
            self._add_temporal(item, key if claim is None else claim.key.object)
            return
        if isinstance(
            item, ObservedKeyedWrite | ObjectClaimedWrite | InsertionKeyedWrite | TargetKeyedWrite
        ):
            self._combine_claimed(item, key)
        else:
            self._items.append(item)

    def _fold_into_opening(self, instruction: PreparedKeyedWrite, key: ObjectKey) -> bool:
        """Fold a write of ``key`` into its still-pending insert, answering
        whether that cancelled the insert.

        A non-temporal or Transaction-Time-Only opening takes an amendment's
        values in place and is cancelled by any destruction, which removes all
        of it. A Bitemporal opening composes the write over the coverage it
        opens and ends once nothing its writes opened survives. It is then
        cancelled, unless a composed replacement reached stored coverage past
        it: the composed destruction still settles there, though the insert no
        longer stands, so a further insert of the object follows it.
        """
        items = self._items
        index = self._inserts[key]
        base = items[index]
        target = instruction.target
        if isinstance(self._temporal_facet.shape(target.identity), temporal_read.Bitemporal):
            opening = (
                base
                if isinstance(base, PendingOpening)
                else PendingOpening(
                    insert=cast("PreparedKeyedWrite", base), transform=NO_TRANSFORM, intents=()
                )
            ).then(instruction, _key_name(self._families, target))
            if opening.survives or opening.transform.assigns:
                items[index] = opening
                return False
            if opening.beyond is not None:
                items[index] = opening
                del self._inserts[key]
                if self._ended is None:
                    self._ended = set()
                self._ended.add(key)
                return False
        elif instruction.mutation in ASSIGNMENT_MUTATIONS:
            # No carrier wraps an insert, so a pending-insert slot is always a
            # bare instruction — and folding an update into it yields an insert,
            # which is why the merged item stays bare.
            assert isinstance(base, PreparedKeyedWrite)
            items[index] = _merge_assignment_into_insert(base, instruction, self._families)
            return False
        items[index] = None
        del self._inserts[key]
        if self._after_removal is not None:
            self._after_removal.discard(index)
        return True

    def _combine_claimed(
        self, item: ClaimedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite, key: ObjectKey
    ) -> None:
        """Combine ``item`` with the write pending at its OWN scope, or open
        that scope.

        The verdict is the one algebra the arriving verb already ran
        (:func:`~parallax.core.unit_work.claims.admits`), unclaimed row
        included: assignments merge in authored order, a destruction supersedes
        the assignments buffered before it, and a repeated destruction of one
        scope and region adds nothing. An ``incompatible`` pair leaves both
        writes standing.

        Which write ``item`` meets is decided by what it settles against and
        never by its key alone (:func:`_claim_scope`), so writes of two states
        of one key may interleave without either displacing the other. Only
        each scope's position is indexed: the held intent is read back off the
        held write itself. A write an insertion authorized meets an observed
        write of the same state as its peer, and the survivor keeps the
        observed write's evidence, which it still spends.
        """
        items = self._items
        scope = _claim_scope(item, key)
        if isinstance(item, TargetKeyedWrite):
            if self._targets is None:
                self._targets = {}
            self._targets[key] = scope
            if self._objects is None:
                self._index_objects()
        index = self._claims.get(scope)
        verdict = self.verdict(item, key)
        if index is not None and self._closed(index) and verdict in ("coalesce", "supersede"):
            # A barrier stands between the two: each keeps its own side, and
            # this one starts from the state the earlier one leaves.
            regions = self._regions
            assert regions is not None  # a closed region exists only behind a barrier
            items.append(item)
            position = len(items) - 1
            regions.follows[position] = regions.follows.get(index, 0) + 1
            self._claims[scope] = position
            if self._objects is not None:
                _note_scope(self._objects, key, scope)
            return
        if verdict == "coalesce":
            assert index is not None  # an unclaimed scope admits
            base = items[index]
            assert isinstance(base, _CLAIMED)
            items[index] = _merged_claimed(base, item)
            return
        if verdict == "deduplicate":
            assert index is not None  # an unclaimed scope admits
            base = items[index]
            assert isinstance(base, _CLAIMED)
            items[index] = _evidenced(base, item, base.instruction)
            return
        if index is not None and verdict == "supersede":
            base = items[index]
            assert isinstance(base, _CLAIMED)
            items[index] = None
            item = _evidenced(item, base, item.instruction)
        items.append(item)
        self._claims[scope] = len(items) - 1
        if self._objects is not None:
            _note_scope(self._objects, key, scope)

    def _seal(self) -> None:
        """Close the current barrier region at the barrier about to be
        appended: no later write combines with a write before it."""
        regions = self._regions
        if regions is None:
            regions = self._regions = _Regions()
        regions.start = len(self._items)
        temporal = self._temporal
        for key, index in temporal.items():
            regions.temporal.setdefault(key, []).append(index)
        temporal.clear()

    def _closed(self, index: int) -> bool:
        """Whether the pending write at ``index`` stands before the latest
        barrier."""
        regions = self._regions
        return regions is not None and index < regions.start

    def folds_into_opening(self, key: ObjectKey) -> bool:
        """Whether a write of ``key`` composes with the object's still-pending
        insert: one is pending, and no barrier stands between them."""
        index = self._inserts.get(key)
        return index is not None and not self._closed(index)

    def _add_temporal(self, item: TemporalKeyedWrite, key: ObjectKey) -> None:
        items = self._items
        index = self._temporal.get(key)
        held = None if index is None else items[index]
        if index is None or held is None:
            sealed = None if self._regions is None else self._regions.temporal.get(key)
            if sealed is None:
                items.append(item)
            else:
                # An earlier region writes the object: that composition hands
                # on what it derives, and this one starts from it.
                key_name = _key_name(self._families, item.instruction.target)
                latest = sealed[-1]
                earlier = items[latest]
                assert isinstance(earlier, _TEMPORAL)
                items[latest] = chained(earlier, key_name, leads=True)
                items.append(chained(item, key_name, follows=True))
            self._temporal[key] = len(items) - 1
            return
        assert isinstance(held, _TEMPORAL)
        intent = keyed_intent(item.instruction)
        assert intent is not None  # a write against existing coverage is no insert
        if (
            isinstance(held, ObservedKeyedWrite)
            and isinstance(item, ObservedKeyedWrite)
            and held.claim is item.claim
            and held.observation == item.observation
        ):
            held_intent = keyed_intent(held.instruction)
            assert held_intent is not None
            if held_intent.valid_time_window == intent.valid_time_window:
                verdict = admits(held_intent, intent)
                if verdict == "coalesce":
                    items[index] = _merged_claimed(held, item)
                    return
                if verdict == "deduplicate":
                    return
                if verdict == "supersede":
                    items[index] = None
                    items.append(item)
                    self._temporal[key] = len(items) - 1
                    return
        if not self.admits_temporal(item, key):
            items.append(item)
            return
        key_name = _key_name(self._families, item.instruction.target)
        composed = composed_temporal_write(held, item, key_name)
        items[index] = (
            chained(composed, key_name, leads=held.leads, follows=held.follows)
            if isinstance(held, ChainedTemporalWrite)
            else composed
        )

    def writes(self) -> tuple[BufferedWrite, ...]:
        """The composed writes, in authored order, with every cancelled write
        gone, every object claim unwrapped to its own instruction, every
        Bitemporal opening composed with the writes its insertion authorized,
        and every insert that must follow a removal marked as such."""
        written: list[BufferedWrite] = []
        after_removal = self._after_removal or ()
        follows = {} if self._regions is None else self._regions.follows
        for index, item in enumerate(self._items):
            if item is None:
                continue
            if index in after_removal:
                # An insert is a bare instruction, or an opening composed over it.
                assert isinstance(item, PreparedKeyedWrite | PendingOpening)
                written.append(AfterRemoval(item))
                continue
            if isinstance(item, PendingOpening):
                written.append(item)
                continue
            advances = follows.get(index)
            if advances is not None and isinstance(
                item, ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite
            ):
                written.append(FollowingKeyedWrite(item, advances))
            else:
                written.append(item.instruction if isinstance(item, ObjectClaimedWrite) else item)
        return tuple(written)

    def sources(self) -> tuple[SourceAuthority, ...]:
        """Every observation-free source authority a pending write was admitted
        through, which the flush spends on success however the writes composed.

        Observation-bearing authority needs no such list: it is a claim the
        composed writes themselves carry to their execution units.
        """
        return tuple(self._sources)

    def clear(self) -> None:
        """Drop every pending write — the buffer that held them is gone."""
        self._items.clear()
        self._sources.clear()
        self._inserts.clear()
        self._claims.clear()
        self._temporal.clear()
        self._removals = None
        self._after_removal = None
        self._ended = None
        self._objects = None
        self._targets = None
        self._regions = None


class _Regions:
    """The barrier regions of a buffer that holds a readless predicate write.

    ``start`` is the position of the latest barrier: every write before it
    stands in a closed region. ``temporal`` holds where each temporal object's
    compositions in closed regions stand, in order, and ``follows`` how many
    earlier writes of its scope each Non-Temporal write a barrier kept apart
    follows.
    """

    __slots__ = ("follows", "start", "temporal")

    def __init__(self) -> None:
        self.start = 0
        self.temporal: dict[ObjectKey, list[int]] = {}
        self.follows: dict[int, int] = {}


_CLAIMED = (ObservedKeyedWrite, ObjectClaimedWrite, InsertionKeyedWrite, TargetKeyedWrite)

_TEMPORAL = (ObservedKeyedWrite, InsertionKeyedWrite, TargetKeyedWrite, ComposedTemporalWrite)

_SEVERAL: Final = object()
"""What the object index records for an object whose claimed writes stand at
more than one scope."""


def _note_scope(objects: dict[ObjectKey, Hashable], key: ObjectKey, scope: Hashable) -> None:
    held = objects.get(key)
    if held is None:
        objects[key] = scope
    elif held != scope:
        objects[key] = _SEVERAL


def _scope_object(scope: Hashable) -> ObjectKey:
    """The object a claimed scope addresses: itself, a state's object, or the
    object beside a caller-held observation."""
    if isinstance(scope, ObjectKey):
        return scope
    if isinstance(scope, VersionedStateKey):
        return scope.object
    key, _evidence = cast("tuple[ObjectKey, object]", scope)
    return key


def composed_intents(
    held: PendingTemporal,
) -> tuple[tuple[ObservedStateKey | None, WriteIntent], ...]:
    """Each write ``held`` composes, as the scope it claims and the intent it
    states over its window."""
    if not isinstance(held, ComposedTemporalWrite):
        intent = keyed_intent(held.instruction)
        assert intent is not None  # a write against existing coverage is no insert
        claim = held.claim if isinstance(held, ObservedKeyedWrite) else None
        return ((None if claim is None else claim.key, intent),)
    return tuple(
        (_scope(contribution), _intent(contribution)) for contribution in held.contributions
    )


def _scope(contribution: TemporalContribution) -> ObservedStateKey | None:
    return None if contribution.claim is None else contribution.claim.key


def _intent(contribution: TemporalContribution) -> WriteIntent:
    return WriteIntent(kind=contribution.kind, valid_time_window=contribution.valid_time_window)


def _destroyed(held: PendingTemporal) -> Iterator[TimeInterval]:
    """The Valid-Time intervals ``held`` destroys, ordered by start."""
    if isinstance(held, ComposedTemporalWrite):
        for segment in held.transform.segments:
            if segment.assigned is None:
                window = segment.valid_time_window
                assert window is not None  # only a Bitemporal object's coverage is asked for
                yield window
        return
    instruction = held.instruction
    if instruction.mutation not in ASSIGNMENT_MUTATIONS:
        window = instruction.valid_time_window
        assert window is not None  # only a Bitemporal object's coverage is asked for
        yield window


_START: Final = attrgetter("start")


def _targeted(held: PendingTemporal) -> bool:
    """Whether a caller-addressed write is among ``held``."""
    if isinstance(held, ComposedTemporalWrite):
        return any(contribution.condition is not None for contribution in held.contributions)
    return isinstance(held, TargetKeyedWrite)


def _contributions(held: PendingTemporal) -> tuple[TemporalContribution, ...]:
    if isinstance(held, ComposedTemporalWrite):
        return held.contributions
    return (temporal_contribution(held),)


def compose_writes(model: Metamodel, writes: Sequence[BufferItem]) -> tuple[BufferedWrite, ...]:
    """``writes`` composed in authored order by :class:`PendingWrites`, for a
    caller holding a buffer no unit of work admitted."""
    pending = PendingWrites(model)
    for item in writes:
        pending.add(item)
    return pending.writes()


def _claim_scope(
    item: ClaimedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite, key: ObjectKey
) -> Hashable:
    """The scope ``item``'s claim is filed under: the retained claim's own
    Observed State Key, the object for an object claim, the scope an
    insertion-authorized write was admitted at, the state a caller's condition
    names, or — for a caller-held observation, which names no state key — the
    object beside that evidence, since equal evidence about one object is one
    state."""
    if isinstance(item, ObjectClaimedWrite):
        return key
    if isinstance(item, TargetKeyedWrite):
        return item.scope
    if isinstance(item, InsertionKeyedWrite):
        return key if item.scope is None else item.scope
    if item.claim is not None:
        return item.claim.key
    return (key, item.observation)


type _Claimed = ClaimedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite


def _merged_claimed(base: _Claimed, arriving: _Claimed) -> _Claimed:
    """``base`` carrying ``arriving``'s assignments too, later value winning.

    The surviving carrier keeps ``base``'s position, window, and claim — the
    two claim one scope over one window, which is what let them coalesce — and
    gains the merged row under the verb they leave (:func:`_coalesced`).
    """
    merged = dict(base.instruction.rows[0])
    merged.update(arriving.instruction.rows[0])
    return _evidenced(base, arriving, _coalesced(base.instruction, arriving.instruction, merged))


def _evidenced(first: _Claimed, second: _Claimed, instruction: PreparedKeyedWrite) -> _Claimed:
    """``instruction`` in the carrier of whichever of two writes of one scope
    a caller conditioned, else whichever a read authorized — ``first`` where
    both or neither were.

    A caller's condition outranks a read's evidence because it must still be
    met whatever the survivor writes, and the survivor then spends every
    retained observation either write was admitted through. A read's evidence
    outranks an insertion's authority because the survivor still has to spend
    it, and the two settle against the same state. Where both were read, the
    survivor also spends every distinct retained observation the other was
    admitted through.
    """
    target = (
        first
        if isinstance(first, TargetKeyedWrite)
        else second
        if isinstance(second, TargetKeyedWrite)
        else None
    )
    if target is not None:
        claims = target.claims
        for write in (first, second):
            for claim in _retained_claims(write):
                if all(claim is not held for held in claims):
                    claims = (*claims, claim)
        return replace(target, instruction=instruction, claims=claims)
    carrier, other = (second, first) if isinstance(first, InsertionKeyedWrite) else (first, second)
    if not isinstance(carrier, ObservedKeyedWrite) or not isinstance(other, ObservedKeyedWrite):
        return replace(carrier, instruction=instruction)
    twins = carrier.twins
    for claim in (other.claim, *other.twins):
        if claim is not None and claim is not carrier.claim and all(claim is not t for t in twins):
            twins = (*twins, claim)
    return replace(carrier, instruction=instruction, twins=twins)


def _retained_claims(write: _Claimed) -> tuple[RetainedObservation, ...]:
    if isinstance(write, TargetKeyedWrite):
        return write.claims
    if isinstance(write, ObservedKeyedWrite) and write.claim is not None:
        return (write.claim, *write.twins)
    return ()


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


def _coalesced(
    base: PreparedKeyedWrite, arriving: PreparedKeyedWrite, merged: Mapping[str, object]
) -> PreparedKeyedWrite:
    """``base`` over the ``merged`` row, replacing where either write did: a
    replacement's complete state overlaid by an amendment, or overlaying one,
    is still the complete state a replacement establishes over its window."""
    if arriving.mutation not in REPLACE_MUTATIONS or base.mutation in REPLACE_MUTATIONS:
        return derive_keyed_write(base, (merged,))
    bounded = base.mutation.endswith("Until")
    return derive_keyed_write(base, (merged,), mutation="replaceUntil" if bounded else "replace")
