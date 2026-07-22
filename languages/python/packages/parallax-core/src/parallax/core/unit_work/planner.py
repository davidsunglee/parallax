"""The pure flush planner (m-unit-work).

Given a unit of work's buffered write instructions, the observations it recorded,
the Clock-supplied Transaction-Time instant, and the metamodel, :func:`plan_flush`
produces a **neutral, execution-ordered intermediate plan** — the coalesced,
collapsed, FK-ordered, elision-applied sequence of write instructions with each
keyed instruction's bound observation attached. It is a **pure** function of its
inputs (an injected ``collapse`` policy included — see below).

**It emits no SQL.** The module DAG pins ``m-unit-work -> m-op-algebra`` and
``m-unit-work -> m-db-port`` only — there is deliberately **no** edge to ``m-sql``
or ``m-dialect`` — so this planner cannot render final DML. The write-DML -> SQL
lowering (the deliberate ``m-sql`` edge) happens one layer up, at the composition
surface that legally sees both (the snapshot handle / conformance engine), which
lowers each :class:`PlannedWrite` against :class:`FlushPlan.tx_instant`. This is
the same seam ``m-temporal-read`` resolved: rewrite into neutral terms here,
compose SQL above.

The stages, in order (``m-unit-work`` "Same-transaction write coalescing" /
"Buffered, batched, ordered writes"):

- **coalesce** — a same-transaction keyed insert-then-update of one object folds
  the update into the pending insert (a single final-value write, per temporal
  flavor at lowering); a keyed insert-then-delete of one object **cancels** (both
  annihilate, no DML). An :class:`AtomicUnit` representing a materialized
  predicate write is opaque here — never a coalescing
  candidate, never folded with an unrelated instruction.
- **collapse** — same-entity, same-mutation, ADJACENT single-row keyed writes
  merge into one multi-row instruction when the injected ``collapse`` policy
  (``m-batch-write``'s vocabulary, supplied by the composition layer — this
  scope takes no edge to it) says the run collapses; declining or omitted
  (``collapse=None``) leaves every instruction exactly as coalesce produced it.
  Deterministic in buffer order: a run never regroups across an intervening,
  differently-keyed instruction or an :class:`AtomicUnit` boundary.
- **FK-order** — a topological order over the descriptor foreign-key graph:
  inserts parent-first, deletes child-first, updates between (the canonical
  INSERT -> UPDATE -> DELETE flush order). An :class:`AtomicUnit` moves as ONE
  block (ranked by its own target entity), its internal row order untouched.
- **elide** — a keyed update whose effective change set is empty (a row carrying
  only its primary key) emits no instruction; a net-zero coalescing chain
  (insert-then-delete) already emitted nothing in coalesce.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core import inheritance
from parallax.core.descriptor import Metamodel
from parallax.core.unit_work.instructions import KeyedWrite, WriteInstruction

__all__ = [
    "AtomicUnit",
    "BufferItem",
    "CollapsePolicy",
    "FlushPlan",
    "ObjectKey",
    "Observation",
    "PlannedWrite",
    "object_key",
    "plan_flush",
]

# One object's identity: (entity, ordered (pk-attribute-name, value) pairs). The
# coalescing scope and the observation binding are keyed by it.
ObjectKey = tuple[str, tuple[tuple[str, object], ...]]

_INSERT_VERBS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
_UPDATE_VERBS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})
_DELETE_VERBS: Final[frozenset[str]] = frozenset({"delete", "terminate", "terminateUntil"})


@dataclass(frozen=True, slots=True)
class Observation:
    """A framework-owned per-object transaction observation (m-opt-lock, ADR 0013).

    The optimistic-lock version and/or observed Transaction-Time start a gated write binds,
    attached to a planned write at flush and **never** carried on the durable
    instruction. Neutral here: this milestone pairs it onto the plan; lowering the
    version gate or advance into SQL is the composition layer's job.

    ``valid_start`` / ``valid_end`` / ``payload`` extend the vocabulary for a
    temporal observation (`m-txtime-write` / `m-bitemp-write`): ``valid_start``
    is the observed rectangle's own Valid-Time
    lower bound — the bitemporal optimistic gate's discriminator candidate AND (via
    :mod:`parallax.core.bitemp_write`'s planning) the Valid-Time lower bound the head
    rectangle's upper bound derives from; ``valid_end`` is the observed rectangle's
    own Valid-Time upper bound — the tail rectangle's own upper bound; ``payload``
    is the observed row's OTHER columns (every scalar / value-object member besides
    the milestone interval bounds) — the "prior rectangle" values a bitemporal split's
    head/tail carry forward (`m-bitemp-write` "Head/tail old values come from the
    observed prior rectangle"), and the values an audit-only chaining ``update``
    merges a sparse authored row onto
    (`~parallax.core.txtime_write.plan`'s own ``_merged_row``) so an unauthored field
    is never silently dropped. ``valid_start`` / ``valid_end`` stay ``None`` for
    a non-temporal or Transaction-Time-Only observation (neither declares Valid Time to
    bound); all three are ``None`` for a non-temporal observation. This is
    Python-internal vocabulary, NOT the serialized instruction (ADR 0013 stands): the
    reserved ``observedVersion`` / ``observedTxStart`` control keys stay forbidden on a
    write row; an observation attaches per row at flush, never carried on the
    instruction.

    ``latest_pinned`` (`m-opt-lock` "Locking mode additionally requires that the
    observation be of the current milestone") is the historical-observation
    LICENSING bit `~parallax.core.opt_lock.check_locking_license` consumes: a
    versioned non-temporal observation is trivially latest-pinned (its single
    row is always current) and every engine-supplied temporal observation is
    latest-pinned by construction (the conformance engine's case-local shadow
    tracker only ever tracks the CURRENT milestone) — both default it ``True``
    without ever setting it explicitly. A REAL `Transaction.find` observation
    of a TEMPORAL entity sets it from the read's own Transaction-Time pin
    (`LATEST` or an omitted axis ⇒ ``True``; an explicit as-of instant ⇒
    ``False``) — the one caller that can ever observe something other than the
    current milestone.
    """

    version: int | None = None
    tx_start: str | None = None
    valid_start: str | None = None
    valid_end: str | None = None
    payload: Mapping[str, object] | None = None
    latest_pinned: bool = True


@dataclass(frozen=True, slots=True)
class PlannedWrite:
    """One execution-ordered item of the neutral flush plan: a (coalesced) write
    instruction, its bound observation (``None`` when none was recorded), and
    its affected-rows expectation (m-opt-lock).

    ``expected_affected`` is ``1`` for every keyed ``update``/``delete`` whose
    bound observation carries a version (a versioned row this unit of work
    observed) — the composition layer's shell compares the port's own
    ``execute_write`` count against it, raising the optimistic-lock conflict on
    a mismatch and aborting the whole unit of work (`parallax.core.opt_lock`).
    ``None`` for every other write (an unversioned write, or one whose row
    carries its version as plain caller-authored data rather than a recorded
    observation; corpus cases without an observation never use this
    plan-level expectation.
    """

    instruction: WriteInstruction
    observation: Observation | None = None
    expected_affected: int | None = None


@dataclass(frozen=True, slots=True)
class AtomicUnit:
    """A materialized predicate write's ORDERED, INDIVISIBLE planned unit
    (`m-unit-work` "Materialized predicate writes are an atomic planned unit",
    ADR 0014): the per-row keyed writes a versioned or
    temporal predicate-selected write materializes to, in the resolving read's
    OWN resolved-row order.

    Buffered as ONE opaque item at the call position (never split, never
    reordered internally) — EXEMPT from same-object coalescing (its rows are
    never folded with an unrelated buffered instruction: a materializing
    resolve only ever matches EXISTING rows, which read-your-own-writes has
    already flushed past any pending same-key insert, so no coalescing
    candidate can structurally arise) and from cross-unit reordering (FK-order
    moves it as ONE block, ranked by its own target entity, never reordering
    its internal rows — `_fk_order`, below). Each member write's own observation
    still flows through the SAME ``uow.observe`` seam as any other keyed write
    (never carried on this wrapper), so :func:`_attach_observation` binds it
    exactly as it would a lone keyed write — the "atomic" property is CONFINED
    to coalesce/collapse/FK-order; a flattened :class:`FlushPlan.writes` never
    carries this type at all.
    """

    writes: tuple[KeyedWrite, ...]


# One buffer item: an ordinary write instruction, or a materialized predicate
# write's atomic planned unit.
BufferItem = WriteInstruction | AtomicUnit

# The injected `m-batch-write` collapse-eligibility policy (`meta, entity_name,
# mutation, rows) -> collapses`): this scope takes no edge to `m-batch-write`
# (the `m-unit-work ↮ m-batch-write` contract), so `plan_flush` accepts it as
# an OPTIONAL parameter the composition layer supplies (`parallax.snapshot.handle`
# for production, the conformance compile lane identically) — omitted (`None`)
# is a pure no-op collapse stage, never a behavior a caller must opt into just to
# keep per-instruction lowering.
CollapsePolicy = Callable[[Metamodel, str, str, Sequence[Mapping[str, object]]], bool]


@dataclass(frozen=True, slots=True)
class FlushPlan:
    """The neutral, execution-ordered intermediate flush plan (m-unit-work).

    ``writes`` is the coalesced, collapsed, FK-ordered, elision-applied
    sequence — always FLAT (an :class:`AtomicUnit` never survives past
    FK-ordering; its member writes are inlined, adjacent, in their own
    resolved-row order). ``tx_instant`` is the Clock-supplied Transaction-Time
    instant carried as flush **context** — never an instruction field — that
    the composition layer binds as ``in_z`` when it lowers a temporal write.
    The composition layer lowers this plan to DML SQL through ``m-sql`` /
    ``m-dialect``; this scope neither takes a dialect nor emits SQL.
    """

    writes: tuple[PlannedWrite, ...] = ()
    tx_instant: str | None = None


def plan_flush(
    buffer: Sequence[BufferItem],
    observations: Mapping[ObjectKey, Observation],
    tx_instant: str | None,
    meta: Metamodel,
    *,
    collapse: CollapsePolicy | None = None,
) -> FlushPlan:
    """Plan a flush: coalesce -> collapse -> FK-order -> elide, then attach
    observations.

    Pure. Returns the neutral :class:`FlushPlan` the composition layer lowers to
    DML; this function renders no SQL and takes no dialect (the ``m-unit-work``
    seam is DML-neutral by DAG design). ``collapse`` is the injected
    ``m-batch-write`` vocabulary (omitted: the collapse stage is a no-op).
    """
    coalesced = _coalesce(buffer, meta)
    collapsed = _collapse(coalesced, meta, collapse, observations)
    ordered = _fk_order(collapsed, meta)
    elided = _elide(ordered, meta)
    writes = tuple(_attach_observation(instr, observations, meta) for instr in elided)
    return FlushPlan(writes=writes, tx_instant=tx_instant)


# --------------------------------------------------------------------------- #
# Object identity.                                                             #
# --------------------------------------------------------------------------- #
def object_key(instruction: WriteInstruction, meta: Metamodel) -> ObjectKey | None:
    """The identity of the single object a keyed write targets, or ``None``.

    ``None`` when the instruction is not a single-row keyed write, when the row
    does not carry every primary-key attribute (a pk-generated insert whose key is
    entirely DB-computed), or when a carried primary-key VALUE is itself a
    DB-computed marker (`m-pk-gen`'s `{computed: ...}` / `{increment: ...}` — a
    marker-shaped pk value has no coalescing identity, exactly like an absent
    one) — an unidentifiable write is never coalesced nor observation-bound.

    Primary-key resolution is FAMILY-EFFECTIVE
    (`inheritance.family_primary_key`): an inheritance participant's key is
    declared on the root alone (m-inheritance "Inherited members"), so the
    bare per-entity ``Entity.primary_key`` view is wrongly empty for a
    concrete subtype — every corpus family's own keyed writes.
    """
    if not isinstance(instruction, KeyedWrite) or len(instruction.rows) != 1:
        return None
    entity = meta.entity(instruction.entity)
    pk_names = [attr.name for attr in inheritance.family_primary_key(meta, entity)]
    if not pk_names:
        return None
    row = instruction.rows[0]
    pairs: list[tuple[str, object]] = []
    for name in pk_names:
        if name not in row:
            return None
        value = row[name]
        if isinstance(value, Mapping):
            return None
        pairs.append((name, value))
    return (instruction.entity, tuple(pairs))


# --------------------------------------------------------------------------- #
# Coalesce (same-transaction insert-then-update / insert-then-delete).         #
# --------------------------------------------------------------------------- #
def _coalesce(buffer: Sequence[BufferItem], meta: Metamodel) -> list[BufferItem]:
    """Fold each same-transaction insert-then-X of one object (m-unit-work).

    A keyed single-row insert opens a pending insert for its object; a subsequent
    keyed update of that same object folds its non-key fields into the pending
    insert's row (one final-value write, no intermediate milestone); a subsequent
    keyed delete of that same object cancels the pending insert (both annihilate).
    Every other instruction — a predicate write, a multi-row instruction, or an
    :class:`AtomicUnit` (a materialized predicate write's planned unit, EXEMPT
    from coalescing by construction) — passes through in order. The pair scope
    is limited to the specified coalescing pairs rather than arbitrary ordered
    buffer rewrites.
    """
    result: list[BufferItem | None] = []
    pending_insert: dict[ObjectKey, int] = {}
    for item in buffer:
        if isinstance(item, AtomicUnit):
            result.append(item)
            continue
        instruction = item
        key = object_key(instruction, meta)
        if not isinstance(instruction, KeyedWrite) or key is None:
            # A predicate write or an unidentifiable keyed write never coalesces.
            result.append(instruction)
            continue
        verb = instruction.mutation
        if verb in _INSERT_VERBS:
            result.append(instruction)
            pending_insert[key] = len(result) - 1
        elif verb in _UPDATE_VERBS and key in pending_insert:
            index = pending_insert[key]
            base = result[index]
            assert isinstance(base, KeyedWrite)  # a pending-insert slot is always a KeyedWrite
            result[index] = _merge_update_into_insert(base, instruction, meta)
        elif verb in _DELETE_VERBS and key in pending_insert:
            # Insert-then-delete cancels: the pending insert annihilates, no DML.
            result[pending_insert.pop(key)] = None
        else:
            result.append(instruction)
    return [item for item in result if item is not None]


def _merge_update_into_insert(
    insert: KeyedWrite, update: KeyedWrite, meta: Metamodel
) -> KeyedWrite:
    """Overlay ``update``'s non-key row fields onto ``insert``'s row.

    The coalesced write keeps the insert's mutation verb and Valid-Time bounds (so it
    still opens a current milestone / fully-current rectangle at lowering per
    temporal flavor) but carries the FINAL values — no ``INSERT`` + ``UPDATE``.
    """
    pk_names = {attr.name for attr in meta.entity(insert.entity).primary_key}
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


# --------------------------------------------------------------------------- #
# Collapse (m-batch-write's injected vocabulary: same-entity, same-mutation,   #
# ADJACENT single-row keyed writes merge into one multi-row instruction).      #
# --------------------------------------------------------------------------- #
def _collapse(
    buffer: Sequence[BufferItem],
    meta: Metamodel,
    collapse: CollapsePolicy | None,
    observations: Mapping[ObjectKey, Observation],
) -> list[BufferItem]:
    """Merge each ADJACENT run of same-entity, same-mutation, single-row keyed
    writes into one multi-row instruction, per the injected ``collapse`` policy.

    Deterministic in BUFFER order: a run starts the moment a single-row keyed
    write's entity+mutation first appears (or changes from the prior run) and
    ends the moment a non-matching item interrupts it — a differently-keyed
    instruction, a :class:`PredicateWrite`, an already-multi-row instruction, or
    an :class:`AtomicUnit` — so a run NEVER regroups across one of these
    boundaries, and an :class:`AtomicUnit` is never a merge candidate itself
    (opaque, exactly as coalesce treats it). A row whose
    :func:`object_key` is already present in ``observations`` is likewise
    NEVER a merge candidate: a recorded per-row observation (an engine
    `observedVersion`/`observedTxStart` signal, or a real transaction-scoped
    ``uow.observe``) is an explicit "keep this row separately identifiable"
    signal a merged multi-row instruction has no way to carry forward — a
    multi-row `KeyedWrite` never attaches a per-row observation at all
    (`object_key` returns ``None`` for one, so :func:`_attach_observation`
    could never re-discover it after merging). ``collapse is None`` (no
    ``m-batch-write`` vocabulary injected) is a pure no-op: every instruction
    survives exactly as coalesce produced it.
    """
    if collapse is None:
        return list(buffer)
    result: list[BufferItem] = []
    run: list[KeyedWrite] = []

    def flush_run() -> None:
        if not run:
            return
        if len(run) == 1:
            result.append(run[0])
        elif collapse(meta, run[0].entity, run[0].mutation, [row for w in run for row in w.rows]):
            result.append(_merge_rows(run))
        else:
            result.extend(run)
        run.clear()

    def observed(item: KeyedWrite) -> bool:
        key = object_key(item, meta)
        return key is not None and key in observations

    for item in buffer:
        if (
            isinstance(item, KeyedWrite)
            and len(item.rows) == 1
            and not observed(item)
            and run
            and run[-1].entity == item.entity
            and run[-1].mutation == item.mutation
            and run[-1].valid_from == item.valid_from
            and run[-1].until == item.until
        ):
            run.append(item)
            continue
        flush_run()
        if isinstance(item, KeyedWrite) and len(item.rows) == 1 and not observed(item):
            run.append(item)
        else:
            result.append(item)
    flush_run()
    return result


def _merge_rows(run: Sequence[KeyedWrite]) -> KeyedWrite:
    """One multi-row :class:`KeyedWrite` carrying every row of ``run``'s single-row
    instructions, in run (buffer) order — the same entity/mutation/Valid-Time bounds
    every member of the run already shares (`_collapse`'s own adjacency test)."""
    first = run[0]
    return KeyedWrite(
        mutation=first.mutation,
        entity=first.entity,
        rows=tuple(row for w in run for row in w.rows),
        valid_from=first.valid_from,
        until=first.until,
    )


# --------------------------------------------------------------------------- #
# FK-order (topological over the descriptor foreign-key graph).                #
# --------------------------------------------------------------------------- #
def _fk_order(items: Sequence[BufferItem], meta: Metamodel) -> list[WriteInstruction]:
    """Order writes so a parent row inserts before a child that references it and
    deletes after: inserts parent-first, deletes child-first, updates between.

    An :class:`AtomicUnit` participates as ONE pseudo-instruction — ranked and
    bucketed by its own first member write (every member shares the SAME
    mutation and target entity, since a predicate write's materialization is
    single-verb/single-entity by construction) — then FLATTENED back into its
    member writes, in their own resolved-row order, once the bucket sort has
    fixed its position: this is how it "moves as one block."
    """
    ranks = _fk_ranks(meta)

    def representative(item: BufferItem) -> WriteInstruction:
        return item.writes[0] if isinstance(item, AtomicUnit) else item

    def rank(item: BufferItem) -> int:
        entity_name = _instruction_entity(representative(item))
        resolved = meta.by_name.get(entity_name)
        if resolved is not None:
            entity_name = resolved.canonical_name
        return ranks.get(entity_name, 0)

    def mutation(item: BufferItem) -> str:
        return representative(item).mutation

    inserts = [i for i in items if mutation(i) in _INSERT_VERBS]
    updates = [i for i in items if mutation(i) in _UPDATE_VERBS]
    deletes = [i for i in items if mutation(i) in _DELETE_VERBS]
    inserts.sort(key=rank)  # ascending rank: referenced entities (parents) first
    deletes.sort(key=lambda i: -rank(i))  # descending rank: referencing entities (children) first
    ordered: list[BufferItem] = [*inserts, *updates, *deletes]
    return [
        write
        for item in ordered
        for write in (item.writes if isinstance(item, AtomicUnit) else (item,))
    ]


def _fk_ranks(meta: Metamodel) -> dict[str, int]:
    """A topological rank per entity: a referenced entity ranks before its referencer.

    A ``many-to-one`` relationship means the source holds the foreign key (source
    after related); a ``one-to-many`` means the related entity holds it (related
    after source). ``one-to-one`` contributes no FK-order edge because its
    storage owner is ambiguous. Ties break by
    declaration order; a (defensive) cycle falls back to declaration order.
    """
    names = [entity.canonical_name for entity in meta.entities]
    prereqs: dict[str, set[str]] = {name: set() for name in names}
    for entity in meta.entities:
        for rel in meta.relationships_for(entity):
            related = rel.join.target.entity
            if related not in prereqs:
                continue  # a relationship reaching outside this model has no local order
            if rel.cardinality == "many-to-one":
                prereqs[entity.canonical_name].add(related)
            elif rel.cardinality == "one-to-many":
                prereqs[related].add(entity.canonical_name)
    remaining = set(names)
    order: list[str] = []
    while remaining:
        ready = [n for n in names if n in remaining and not (prereqs[n] & remaining)]
        if not ready:
            # Defensive: reachable models are acyclic; a cycle keeps declaration order.
            order.extend(n for n in names if n in remaining)  # pragma: no cover
            break  # pragma: no cover
        order.append(ready[0])
        remaining.discard(ready[0])
    return {name: rank for rank, name in enumerate(order)}


def _instruction_entity(instruction: WriteInstruction) -> str:
    if isinstance(instruction, KeyedWrite):
        return instruction.entity
    return instruction.target.entity


# --------------------------------------------------------------------------- #
# Elide (empty effective change set).                                          #
# --------------------------------------------------------------------------- #
def _elide(instructions: Sequence[WriteInstruction], meta: Metamodel) -> list[WriteInstruction]:
    """Drop a keyed update whose effective change set is empty.

    A keyed update carrying only its primary key names no changed field, so it emits
    no DML — the net-zero elision (uniform for non-temporal and temporal entities;
    a value-identical milestone is never fabricated). Predicate-write per-row no-op
    elimination belongs to the materialization boundary, not this planner.
    """
    return [i for i in instructions if not _is_empty_keyed_update(i, meta)]


def _is_empty_keyed_update(instruction: WriteInstruction, meta: Metamodel) -> bool:
    if not isinstance(instruction, KeyedWrite) or instruction.mutation not in _UPDATE_VERBS:
        return False
    pk_names = {attr.name for attr in meta.entity(instruction.entity).primary_key}
    return all(all(key in pk_names for key in row) for row in instruction.rows)


# --------------------------------------------------------------------------- #
# Observation binding.                                                         #
# --------------------------------------------------------------------------- #
def _attach_observation(
    instruction: WriteInstruction,
    observations: Mapping[ObjectKey, Observation],
    meta: Metamodel,
) -> PlannedWrite:
    key = object_key(instruction, meta)
    observation = observations.get(key) if key is not None else None
    return PlannedWrite(
        instruction=instruction,
        observation=observation,
        expected_affected=_expected_affected(instruction, observation),
    )


def _expected_affected(
    instruction: WriteInstruction, observation: Observation | None
) -> int | None:
    """The affected-rows expectation `m-opt-lock` attaches at flush.

    ``1`` for a keyed ``update``/``delete`` whose bound observation carries a
    version (a versioned row this unit of work observed) — in EITHER
    concurrency mode, so a vanished row is caught even under a locking-mode
    write the version gate never guards. Nothing else ever carries a version
    observation (a non-versioned entity's row, or a write whose row
    carries its version as plain caller-authored data rather than a recorded
    observation), so this reduces to the single check below without a
    metamodel lookup of its own.
    """
    if not isinstance(instruction, KeyedWrite) or instruction.mutation not in (
        *_UPDATE_VERBS,
        *_DELETE_VERBS,
    ):
        return None
    if observation is None or observation.version is None:
        return None
    return 1
