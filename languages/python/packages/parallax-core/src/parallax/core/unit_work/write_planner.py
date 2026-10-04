from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass, replace
from operator import itemgetter
from typing import cast

from parallax.core import inheritance, relationship, temporal_read
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.unit_work.claims import (
    ClaimVerdict,
    WriteIntent,
    admits,
    admits_composed,
    keyed_intent,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.instructions import (
    DESTRUCTIVE_MUTATIONS,
    INSERT_MUTATIONS,
    UPDATE_MUTATIONS,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedWrite,
    derive_keyed_write,
)
from parallax.core.unit_work.materialized import (
    BufferItem,
    ClaimedKeyedWrite,
    ComposedTemporalWrite,
    MaterializedWriteGroup,
    ObjectClaimedWrite,
    ObservedKeyedWrite,
    buffered_instruction,
    composed_temporal_write,
)
from parallax.core.unit_work.plan import NO_OWNERSHIP, Completion, Ownership
from parallax.core.unit_work.planner import ObjectKey, ObservedStateKey, resolve_object_key
from parallax.core.unit_work.strategy import (
    ActorIdentity,
    AuditStrategy,
    BatchingStrategy,
    Concurrency,
    ConcurrencyStrategy,
    TemporalStrategy,
)
from parallax.core.unit_work.write_settlement import (
    OrderedWrite,
    WritePlanningResult,
    WriteSettlement,
)

__all__ = [
    "PendingWrites",
    "PlanningRequest",
    "WritePlanner",
    "compose_writes",
]

type BufferedWrites = Sequence[OrderedWrite]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanningRequest:
    """One flush's complete planning input.

    Keyword-only and Actor Identity first: planning occurs under already
    captured Execution Authority, and field order emphasizes that without
    making it a positional API.

    ``buffered_writes`` is the buffer as :class:`PendingWrites` composed it at
    admission, in authored order: one item per coalesced write, one composed
    write per temporal object's observed writes, and no write a later one
    cancelled. ``ownership`` answers which current temporal rows the planning
    attempt already opened; planning reads it and never changes it.
    """

    actor_identity: ActorIdentity
    transaction_instant: TransactionInstant
    concurrency: Concurrency
    buffered_writes: BufferedWrites
    ownership: Ownership = NO_OWNERSHIP


class WritePlanner:
    """The model-scoped, stateless Write Planner (`m-unit-work`).

    Constructed once per accepted Metamodel with its strategy adapters already
    wired; :meth:`finalize` is its entire caller-visible surface. A caller with
    no evidence to spend reads ``finalize(request).plan``. No caller sequences
    coalescing, batching, ordering, temporal expansion, observation validation,
    instant acquisition, or provenance decoration by hand.

    The settlement module it constructs here is its own, built over the same
    model and compiled facets and living exactly as long: a prepared Model
    Selection carries a mutually consistent model, codec, planner, and
    settlement module, and publication replaces the whole selection rather than
    rebinding any of them.
    """

    __slots__ = (
        "_batching",
        "_families",
        "_model",
        "_relationships",
        "_settlement",
        "_temporal_facet",
    )

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
        self._families = inheritance.view(model)
        self._temporal_facet = temporal_read.view(model)
        self._relationships = relationship.view(model)
        self._batching = batching
        self._settlement = WriteSettlement(
            model,
            self._families,
            self._temporal_facet,
            concurrency=concurrency,
            temporal=temporal,
            audit=audit,
        )

    def finalize(self, request: PlanningRequest) -> WritePlanningResult:
        """Plan one flush: eliminate no-ops, batch, order, and hand the whole
        ordered sequence to settlement — answering the plan, whose execution
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
        The Write Planning Result
        :meth:`~parallax.core.unit_work.write_settlement.WriteSettlement.settle`
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
        return self._settlement.settle(
            self._order(batched),
            concurrency=request.concurrency,
            actor_identity=request.actor_identity,
            transaction_instant=request.transaction_instant,
            ownership=request.ownership,
        )

    def _form_batches(self, buffer: Sequence[OrderedWrite]) -> list[OrderedWrite]:
        result: list[OrderedWrite] = []
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
                    and run[-1].bounds == item.bounds
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

    def _order(self, items: Sequence[OrderedWrite]) -> list[OrderedWrite]:
        """``items`` in flush order: each readless predicate write stays where it
        was authored, and within each region between them inserts go in
        ascending referential rank, then updates in authored order, then deletes
        in descending rank. Both sorts are stable."""
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
            if isinstance(item, PreparedPredicateWrite):
                close_region()
                ordered.append(item)
                continue
            if isinstance(item, ComposedTemporalWrite):
                if item.assigns:
                    updates.append(item)
                else:
                    deletes.append((self._ranked(item.target), item))
                continue
            instruction = buffered_instruction(item)
            if instruction.mutation in UPDATE_MUTATIONS:
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


def _merge_update_into_insert(
    insert: PreparedKeyedWrite,
    update: PreparedKeyedWrite,
    families: inheritance.InheritanceFacet,
) -> PreparedKeyedWrite:
    """Overlay ``update``'s non-key row fields onto ``insert``'s row.

    The coalesced write keeps the insert's mutation verb and Valid-Time bounds
    (so it still opens a current milestone / fully-current rectangle at
    settling per temporal flavor) but carries the FINAL values — no
    ``INSERT`` + ``UPDATE``.
    """
    key_name = _key_name(families, insert.target)
    merged = dict(insert.rows[0])
    for name, value in update.rows[0].items():
        if name != key_name:
            merged[name] = value
    return derive_keyed_write(insert, (merged,))


type PendingTemporal = ObservedKeyedWrite | ComposedTemporalWrite
"""What a temporal object's pending observed writes are: one write still
alone, or several composed."""


class PendingWrites:
    """A buffer's writes, composed by the planner's rules as each is admitted.

    The one composition owner: a unit of work adds each write it admits, so the
    buffer it hands finalization is already composed, and a caller holding an
    uncomposed sequence folds it through :func:`compose_writes`. Composition
    follows authored order:

    * an update of an object whose insert is still pending folds into that
      insert, and a destructive write of it cancels the pair;
    * writes claiming one non-temporal scope coalesce by the claim algebra
      (:func:`~parallax.core.unit_work.claims.admits`);
    * a temporal object's observed writes compose into one
      :class:`~parallax.core.unit_work.materialized.ComposedTemporalWrite`
      (:func:`~parallax.core.unit_work.claims.admits_composed`), whose
      transform keeps only surviving values while every write's condition stays.
      Two writes of one observed state over one window simply coalesce, as a
      non-temporal pair does.

    A pair the algebra calls incompatible is one no verb admitted — a caller
    reached the buffer another way — and both writes are left standing rather
    than combined by a rule neither states.
    """

    __slots__ = (
        "_claims",
        "_families",
        "_inserts",
        "_items",
        "_sources",
        "_temporal",
        "_temporal_facet",
    )

    def __init__(self, model: Metamodel) -> None:
        self._families = inheritance.view(model)
        self._temporal_facet = temporal_read.view(model)
        self._items: list[BufferItem | ComposedTemporalWrite | None] = []
        self._inserts: dict[ObjectKey, int] = {}
        # Where each still-open claim sits, by its scope: one per exact observed
        # state, or the object itself for an object claim. Two observed
        # generations of one versioned row hold two independent claims, and
        # writes of them interleave freely.
        self._claims: dict[Hashable, int] = {}
        self._temporal: dict[ObjectKey, int] = {}
        self._sources: list[Completion] = []

    def __bool__(self) -> bool:
        return bool(self._items)

    def temporal(self, key: ObjectKey) -> PendingTemporal | None:
        """The pending observed writes of temporal object ``key``, if any."""
        index = self._temporal.get(key)
        if index is None:
            return None
        held = self._items[index]
        assert isinstance(held, ObservedKeyedWrite | ComposedTemporalWrite)
        return held

    def verdict(self, item: ClaimedKeyedWrite, key: ObjectKey) -> ClaimVerdict:
        """What a non-temporal claimed write becomes against the write pending
        at its own scope (:func:`~parallax.core.unit_work.claims.admits`)."""
        intent = keyed_intent(item.instruction)
        assert intent is not None  # neither carrier wraps an insert
        return admits(self._held_intent(_claim_scope(item, key)), intent)

    def holds(self, state: ObservedStateKey) -> bool:
        """Whether a pending keyed write claims observed state ``state``."""
        if state in self._claims:
            return True
        index = self._temporal.get(state.object)
        held = None if index is None else self._items[index]
        return held is not None and any(
            scope == state for scope, _intent in composed_intents(cast("PendingTemporal", held))
        )

    def _held_intent(self, scope: Hashable) -> WriteIntent | None:
        index = self._claims.get(scope)
        held = None if index is None else self._items[index]
        assert held is None or isinstance(held, ObservedKeyedWrite | ObjectClaimedWrite)
        return None if held is None else keyed_intent(held.instruction)

    def is_temporal(self, item: BufferItem) -> bool:
        """Whether ``item`` is an observed write of a temporal object, the
        writes that compose by object rather than by claimed scope."""
        return isinstance(item, ObservedKeyedWrite) and _is_temporal(
            self._temporal_facet, item.instruction.target
        )

    def add(self, item: BufferItem, key: ObjectKey | None = None) -> None:
        """Compose ``item`` into the pending writes, in authored order.

        ``key`` is the object ``item`` addresses where the caller already
        derived it, so the index shares that key rather than deriving its own.
        """
        items = self._items
        if isinstance(item, ObjectClaimedWrite) and item.source is not None:
            self._sources.append(item.source)
        if isinstance(item, MaterializedWriteGroup):
            items.append(item)
            return
        instruction = buffered_instruction(item)
        if key is None:
            key = resolve_object_key(instruction, self._families)
        if not isinstance(instruction, PreparedKeyedWrite) or key is None:
            items.append(item)
            return
        verb = instruction.mutation
        if verb in INSERT_MUTATIONS:
            items.append(item)
            self._inserts[key] = len(items) - 1
        elif verb in UPDATE_MUTATIONS and key in self._inserts:
            index = self._inserts[key]
            base = items[index]
            # Neither carrier wraps an insert, so a pending-insert slot is
            # always a bare instruction — and folding an update into it
            # yields an insert, which is why the merged item stays bare.
            assert isinstance(base, PreparedKeyedWrite)
            items[index] = _merge_update_into_insert(base, instruction, self._families)
        elif verb in DESTRUCTIVE_MUTATIONS and key in self._inserts:
            items[self._inserts.pop(key)] = None
        elif isinstance(item, ObservedKeyedWrite) and self.is_temporal(item):
            # A retained claim already holds its object's key, so the index
            # shares it rather than keeping one of its own.
            self._add_temporal(item, key if item.claim is None else item.claim.key.object)
        elif isinstance(item, ObservedKeyedWrite | ObjectClaimedWrite):
            self._combine_claimed(item, key)
        else:
            items.append(item)

    def _combine_claimed(self, item: ClaimedKeyedWrite, key: ObjectKey) -> None:
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
        held write itself.
        """
        items = self._items
        scope = _claim_scope(item, key)
        index = self._claims.get(scope)
        verdict = self.verdict(item, key)
        if verdict == "coalesce":
            assert index is not None  # an unclaimed scope admits
            base = items[index]
            assert isinstance(base, ObservedKeyedWrite | ObjectClaimedWrite)
            items[index] = _merged_claimed(base, item)
            return
        if verdict == "deduplicate":
            return
        if index is not None and verdict == "supersede":
            items[index] = None
        items.append(item)
        self._claims[scope] = len(items) - 1

    def _add_temporal(self, item: ObservedKeyedWrite, key: ObjectKey) -> None:
        items = self._items
        index = self._temporal.get(key)
        held = None if index is None else items[index]
        if index is None or held is None:
            items.append(item)
            self._temporal[key] = len(items) - 1
            return
        assert isinstance(held, ObservedKeyedWrite | ComposedTemporalWrite)
        intent = keyed_intent(item.instruction)
        assert intent is not None  # an observed write is no insert
        if isinstance(held, ObservedKeyedWrite) and held.observation == item.observation:
            held_intent = keyed_intent(held.instruction)
            assert held_intent is not None
            if held_intent.region == intent.region:
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
        scope = None if item.claim is None else item.claim.key
        if admits_composed(composed_intents(held), scope, intent) == "incompatible":
            items.append(item)
            return
        items[index] = composed_temporal_write(
            held, item, _key_name(self._families, item.instruction.target)
        )

    def writes(self) -> tuple[OrderedWrite, ...]:
        """The composed writes, in authored order, with every cancelled write
        gone and every object claim unwrapped to its own instruction."""
        return tuple(
            item.instruction if isinstance(item, ObjectClaimedWrite) else item
            for item in self._items
            if item is not None
        )

    def sources(self) -> tuple[Completion, ...]:
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


def composed_intents(
    held: PendingTemporal,
) -> tuple[tuple[ObservedStateKey | None, WriteIntent], ...]:
    """Each write ``held`` composes, as the scope it claims and the intent it
    states over its window."""
    if isinstance(held, ObservedKeyedWrite):
        intent = keyed_intent(held.instruction)
        assert intent is not None  # an observed write is no insert
        return ((None if held.claim is None else held.claim.key, intent),)
    return tuple(
        (
            None if contribution.claim is None else contribution.claim.key,
            WriteIntent(
                kind=contribution.kind,
                valid_from=contribution.bounds.valid_from,
                until=contribution.bounds.until,
            ),
        )
        for contribution in held.contributions
    )


def compose_writes(model: Metamodel, writes: Sequence[BufferItem]) -> tuple[OrderedWrite, ...]:
    """``writes`` composed in authored order by :class:`PendingWrites`, for a
    caller holding a buffer no unit of work admitted."""
    pending = PendingWrites(model)
    for item in writes:
        pending.add(item)
    return pending.writes()


def _claim_scope(item: ClaimedKeyedWrite, key: ObjectKey) -> Hashable:
    """The scope ``item``'s claim is filed under: the retained claim's own
    Observed State Key, the object for an object claim, or — for a caller-held
    observation, which names no state key — the object beside that evidence,
    since equal evidence about one object is one state."""
    if isinstance(item, ObjectClaimedWrite):
        return key
    if item.claim is not None:
        return item.claim.key
    return (key, item.observation)


def _merged_claimed[C: ClaimedKeyedWrite](base: C, arriving: ClaimedKeyedWrite) -> C:
    """``base`` carrying ``arriving``'s assignments too, later value winning.

    The surviving carrier keeps ``base``'s position, mutation, bounds, and claim
    — the two claim one scope over one region, which is what let them coalesce —
    and gains the merged row.
    """
    merged = dict(base.instruction.rows[0])
    merged.update(arriving.instruction.rows[0])
    return replace(base, instruction=derive_keyed_write(base.instruction, (merged,)))


def _decomposed_updates(
    buffer: Sequence[OrderedWrite], temporal_facet: temporal_read.TemporalFacet
) -> list[OrderedWrite]:
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
    decomposed: list[OrderedWrite] = []
    for item in buffer:
        if not isinstance(item, PreparedKeyedWrite) or not _splits_into_rows(item, temporal_facet):
            decomposed.append(item)
            continue
        decomposed.extend(derive_keyed_write(item, (row,)) for row in item.rows)
    return decomposed


def _splits_into_rows(
    item: PreparedKeyedWrite, temporal_facet: temporal_read.TemporalFacet
) -> bool:
    if len(item.rows) < 2 or item.mutation not in UPDATE_MUTATIONS:
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
    entity/mutation/Valid-Time bounds every member of the run already shares."""
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
    item: OrderedWrite,
    families: inheritance.InheritanceFacet,
    temporal_facet: temporal_read.TemporalFacet,
) -> OrderedWrite | None:
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
    if isinstance(item, ComposedTemporalWrite):
        return item
    instruction = buffered_instruction(item)
    if (
        not isinstance(instruction, PreparedKeyedWrite)
        or instruction.mutation not in UPDATE_MUTATIONS
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
