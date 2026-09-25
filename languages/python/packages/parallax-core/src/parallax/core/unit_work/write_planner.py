from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from operator import itemgetter

from parallax.core import inheritance, relationship, temporal_read
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.unit_work.claims import WriteIntent, admits, keyed_intent
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
    MaterializedWriteGroup,
    ObjectClaimedWrite,
    ObservedKeyedWrite,
    buffered_instruction,
)
from parallax.core.unit_work.observe import WriteObservation
from parallax.core.unit_work.planner import ObjectKey, resolve_object_key
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
    "PlanningRequest",
    "WritePlanner",
]

type BufferedWrites = Sequence[BufferItem]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanningRequest:
    """One flush's complete planning input.

    Keyword-only and Actor Identity first: planning occurs under already
    captured Execution Authority, and field order emphasizes that without
    making it a positional API.
    """

    actor_identity: ActorIdentity
    transaction_instant: TransactionInstant
    concurrency: Concurrency
    buffered_writes: BufferedWrites


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
        """Plan one flush: coalesce, eliminate no-ops, batch, order, and hand
        the whole ordered sequence to settlement — answering the plan and the
        claims the settled writes carried.

        Pure with respect to its inputs — no database I/O, no direct clock
        access, no SQL. ``request.actor_identity`` is accepted and never
        inspected. ``request.transaction_instant`` is threaded unevaluated
        until a surviving temporal mutation needs it.

        Batching reads an opening row's member set directly, because
        preparation already spelled every applicable member out: two rows that
        write the same row therefore reach one group key and satisfy the Planned
        Insert's own same-members rule without a canonicalizing pass here.

        The four stages here REWRITE the sequence — merge, drop, split, reorder.
        The Write Planning Result
        :meth:`~parallax.core.unit_work.write_settlement.WriteSettlement.settle`
        answers is returned unchanged, because packing, provenance, and claim
        collection are decided there and nothing is left for the planner to add.
        """
        coalesced = self._coalesce(request.buffered_writes)
        survivors = [
            item
            for item in (
                _without_noop_rows(item, self._families, self._temporal_facet) for item in coalesced
            )
            if item is not None
        ]
        batched = self._form_batches(survivors)
        return self._settlement.settle(
            self._order(batched),
            concurrency=request.concurrency,
            actor_identity=request.actor_identity,
            transaction_instant=request.transaction_instant,
        )

    def _coalesce(self, buffer: BufferedWrites) -> list[OrderedWrite]:
        result: list[BufferItem | None] = []
        pending_insert: dict[ObjectKey, int] = {}
        # Where each object's still-open claims sit, so a second write claiming
        # one of them reaches the carrier it must combine with. An object's
        # entries are one per exact observed state, plus at most one the object
        # itself is the scope of: a key whose reads resolved to two states — two
        # current rectangles of one Bitemporal key, or two observed generations of
        # one versioned row — holds two independent claims, and writes of them
        # interleave freely. Indexing by object alone would let the second state
        # evict the first, and a later write of the first would then be emitted
        # beside the write it was admitted to merge into. An unversioned
        # Non-Temporal object's writes can never be in that position, which is why
        # one entry serves all of them.
        pending: dict[ObjectKey, list[_PendingClaim]] = {}
        for item in buffer:
            if isinstance(item, MaterializedWriteGroup):
                result.append(item)
                continue
            instruction = buffered_instruction(item)
            key = resolve_object_key(instruction, self._families)
            if not isinstance(instruction, PreparedKeyedWrite) or key is None:
                result.append(item)
                continue
            verb = instruction.mutation
            if verb in INSERT_MUTATIONS:
                result.append(item)
                pending_insert[key] = len(result) - 1
            elif verb in UPDATE_MUTATIONS and key in pending_insert:
                index = pending_insert[key]
                base = result[index]
                # Neither carrier wraps an insert, so a pending-insert slot is
                # always a bare instruction — and folding an update into it
                # yields an insert, which is why the merged item stays bare.
                assert isinstance(base, PreparedKeyedWrite)
                result[index] = _merge_update_into_insert(base, instruction, self._families)
            elif verb in DESTRUCTIVE_MUTATIONS and key in pending_insert:
                result[pending_insert.pop(key)] = None
            elif isinstance(item, ObservedKeyedWrite | ObjectClaimedWrite):
                _combine_claimed(item, key, result, pending)
            else:
                result.append(item)
        return [
            surviving
            for surviving in (_coalesced_item(item) for item in result)
            if surviving is not None
        ]

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
        rank = self._relationships.referential_rank(_instruction_target(instruction).identity)
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


@dataclass(slots=True)
class _PendingClaim:
    """One still-open claim during coalescing: where its surviving carrier sits,
    the observed state it settles against — absent where the OBJECT is what it
    claims — and what it intends.

    The observed state is carried as the observation itself rather than as an
    Observed State Key, because the two writes only have to agree — and equal
    evidence about one object IS one state, while deriving the key would make
    coalescing depend on temporal coordinates a caller-held observation need not
    be able to produce. An unversioned Non-Temporal object's claim carries none
    for the reason its scope is the object: there is no state to agree about, and
    the entry's own position under its Object Key is the whole of its address.
    """

    index: int
    observation: WriteObservation | None
    intent: WriteIntent


def _combine_claimed(
    item: ClaimedKeyedWrite,
    key: ObjectKey,
    result: list[BufferItem | None],
    pending: dict[ObjectKey, list[_PendingClaim]],
) -> None:
    """Combine ``item`` with the claim already open at its OWN scope, or open a
    new one, extending ``result`` and ``pending`` in place.

    The verdict is the one algebra the arriving verb already ran
    (:func:`~parallax.core.unit_work.claims.admits`), unclaimed row included, so
    what happens here is what that verb admitted rather than a second reading of
    the same buffer: assignments merge in authored order, a destruction
    supersedes the assignments buffered before it, and a repeated destruction of
    one scope and region adds nothing. An ``incompatible`` pair is one no verb of
    this transaction admitted — the caller reached the buffer another way — and
    both writes are left standing rather than combined by a rule neither states.

    Which claim ``item`` meets is decided by what it settles against and never by
    its key alone, exactly as the verb-time table's own scope decides it: an
    observation-bearing write meets the claim on its own observed state, and an
    object-claimed one meets the object's. An object's other open claims are left
    where they are, so writes of two states of one key may interleave without
    either displacing the other.
    """
    intent = keyed_intent(item.instruction)
    assert intent is not None  # neither carrier wraps an insert
    observed = item.observation if isinstance(item, ObservedKeyedWrite) else None
    claims = pending.setdefault(key, [])
    held = next((claim for claim in claims if claim.observation == observed), None)
    verdict = admits(None if held is None else held.intent, intent)
    if verdict == "coalesce":
        assert held is not None  # an unclaimed scope admits
        base = result[held.index]
        assert isinstance(base, ObservedKeyedWrite | ObjectClaimedWrite)
        result[held.index] = _merged_claimed(base, item)
        return
    if verdict == "deduplicate":
        return
    if held is not None:
        if verdict == "supersede":
            result[held.index] = None
        claims.remove(held)
    result.append(item)
    claims.append(_PendingClaim(index=len(result) - 1, observation=observed, intent=intent))


def _merged_claimed(base: ClaimedKeyedWrite, arriving: ClaimedKeyedWrite) -> ClaimedKeyedWrite:
    """``base`` carrying ``arriving``'s assignments too, later value winning.

    The surviving carrier keeps ``base``'s position, mutation, bounds, and claim
    — the two claim one scope over one region, which is what let them coalesce —
    and gains the merged row. Restoration follows the same later-wins rule as the
    value: a member ``arriving`` assigns stops being restored, and one it put back
    becomes restored however the earlier write left it.
    """
    merged = dict(base.instruction.rows[0])
    merged.update(arriving.instruction.rows[0])
    return _rewritten(
        base,
        merged,
        (base.restorations - set(arriving.instruction.rows[0])) | arriving.restorations,
    )


def _rewritten(
    item: ClaimedKeyedWrite, row: Mapping[str, object], restorations: frozenset[str]
) -> ClaimedKeyedWrite:
    """``item`` carrying ``row`` and ``restorations``, at its own claim scope.

    The one place a carrier is rebuilt, so merging and restoration-dropping state
    what changes rather than each restating which fields a carrier keeps.
    """
    instruction = derive_keyed_write(item.instruction, (row,))
    if isinstance(item, ObservedKeyedWrite):
        return ObservedKeyedWrite(
            instruction=instruction,
            observation=item.observation,
            claim=item.claim,
            restorations=restorations,
        )
    return ObjectClaimedWrite(instruction=instruction, restorations=restorations)


def _coalesced_item(item: BufferItem | None) -> OrderedWrite | None:
    """``item`` as it leaves stage 1: every member its author touched and put back
    dropped from its row, and an object claim it no longer needs unwrapped.

    Applied once coalescing has settled which write survives, so a restoration
    cancels every assignment merged into that survivor rather than only the one
    its own verb saw. What is left is measured by stage 2 exactly as an ordinary
    sparse row is, which is how a chain that nets to zero across several verbs
    reaches the same no-DML outcome a single net-zero edit does.

    An object-claimed write leaves stage 1 as the bare instruction it always was.
    Everything its carrier said — which grain to combine on, and which members the
    last word restored — has been read by the time this runs, and it licenses
    nothing per-row that would keep it out of a multi-row batch, so no later stage
    needs to know the type existed.
    """
    if not isinstance(item, ObservedKeyedWrite | ObjectClaimedWrite):
        return item
    if not item.restorations:
        return _without_object_claim(item)
    row = {
        name: value
        for name, value in item.instruction.rows[0].items()
        if name not in item.restorations
    }
    return _without_object_claim(_rewritten(item, row, frozenset()))


def _without_object_claim(item: ClaimedKeyedWrite) -> OrderedWrite:
    """``item`` as the buffer item planning's later stages consume: an object
    claim as its own instruction, and an observation carrier whole — claim
    included, because what a later stage settles and spends rides there."""
    return item.instruction if isinstance(item, ObjectClaimedWrite) else item


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
