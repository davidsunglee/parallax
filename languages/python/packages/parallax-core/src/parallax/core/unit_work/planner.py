"""The pure flush planner (m-unit-work).

Given a unit of work's buffered write instructions, the observations it recorded,
the attempt's lazy Transaction Instant, and the metamodel, :func:`plan_flush`
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
  that share the injected ``collapse_group`` key merge into one multi-row
  instruction when the injected ``collapse`` policy (``m-batch-write``'s
  vocabulary, supplied by the composition layer — this scope takes no edge to
  it) says the run collapses; declining or omitted (``collapse=None``) leaves
  every instruction exactly as coalesce produced it. Deterministic in buffer
  order: a run never regroups across an intervening, differently-keyed
  instruction or an :class:`AtomicUnit` boundary.
- **FK-order** — a topological order over the declared foreign-key graph:
  inserts parent-first, deletes child-first, updates between (the canonical
  INSERT -> UPDATE -> DELETE flush order). A readless :class:`~parallax.core.
  unit_work.PredicateWrite` is a hard BARRIER: it keeps its authored position
  and partitions the sequence into regions ordered independently, so no write
  crosses it in either direction. An :class:`AtomicUnit` moves as ONE block
  within its region (ranked by its own target entity), its internal row order
  untouched.
- **elide** — a keyed update whose effective change set is empty (a row carrying
  only its primary key) emits no instruction; a net-zero coalescing chain
  (insert-then-delete) already emitted nothing in coalesce.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core import inheritance
from parallax.core.metamodel import (
    AttributeMetadata,
    Cardinality,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.instructions import KeyedWrite, PredicateWrite, WriteInstruction
from parallax.core.unit_work.observe import VersionObservation, WriteObservation

__all__ = [
    "AtomicUnit",
    "BufferItem",
    "CollapseGroupKey",
    "CollapsePolicy",
    "FlushPlan",
    "ObjectKey",
    "PlannedWrite",
    "object_key",
    "plan_flush",
]

# One object's identity: (entity, ordered (pk-attribute-name, value) pairs). The
# coalescing scope and the observation binding are keyed by it.
ObjectKey = tuple[str, tuple[tuple[str, object], ...]]


@dataclass(frozen=True, slots=True)
class _Targets:
    """The per-flush resolution of the write IR's own entity spellings.

    A write instruction names its entity by the spelling its canonical document
    carries (`write-instruction.schema.json`), which is a wire spelling rather
    than an Entity Identity. Resolving it needs the model, and every stage below
    then needs the same Entity's family-effective members, so one resolution is
    made per flush and threaded down rather than repeated per instruction.
    """

    model: Metamodel
    by_spelling: Mapping[str, EntityMetadata]
    families: inheritance.InheritanceFacet

    def entity(self, spelling: str) -> EntityMetadata | None:
        """The accepted Metadata ``spelling`` names, or absence.

        The canonical spelling always resolves; a bare declared name resolves
        only when the model declares it once, so an ambiguous bare name reaches
        no Entity rather than an arbitrary one.
        """
        return self.by_spelling.get(spelling)

    def members(self, entity: EntityMetadata) -> Sequence[AttributeMetadata]:
        """``entity``'s family-effective Attributes, root first.

        An inheritance participant declares only its own members while its
        writes name every inherited one, so the applicable chain — not the
        Entity's own declarations — is what a write-side member lookup reads.
        """
        position = self.families.entity(entity.identity)
        if position is None:  # pragma: no cover - the facet covers every accepted Entity
            return entity.declared_attributes
        return position.applicable_attributes


def _targets(model: Metamodel) -> _Targets:
    by_spelling = {entity.identity.canonical: entity for entity in model.entities}
    counts: dict[str, int] = {}
    for entity in model.entities:
        counts[entity.identity.name] = counts.get(entity.identity.name, 0) + 1
    for entity in model.entities:
        if counts[entity.identity.name] == 1:
            by_spelling.setdefault(entity.identity.name, entity)
    return _Targets(model=model, by_spelling=by_spelling, families=inheritance.view(model))


_INSERT_VERBS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
_UPDATE_VERBS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})
_DELETE_VERBS: Final[frozenset[str]] = frozenset({"delete", "terminate", "terminateUntil"})


@dataclass(frozen=True, slots=True)
class PlannedWrite:
    """One execution-ordered item of the neutral flush plan: a (coalesced) write
    instruction, its bound observation (``None`` when none was recorded), and
    its affected-rows expectation (m-opt-lock).

    ``expected_affected`` is ``1`` for every keyed ``update``/``delete`` whose
    bound observation carries a version (a versioned row this unit of work
    observed) — the composition layer's shell compares the port's own
    ``execute_write`` count against it and, on a mismatch, raises the outcome the
    statement's GATE implies (the retriable optimistic-lock conflict when it
    gated, the non-retriable stale write when it did not), aborting the whole
    unit of work (`parallax.core.opt_lock`).
    ``None`` for every other write (an unversioned write, or one whose row
    carries its version as plain caller-authored data rather than a recorded
    observation; corpus cases without an observation never use this
    plan-level expectation.
    """

    instruction: WriteInstruction
    observation: WriteObservation | None = None
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

# The injected `m-batch-write` collapse-eligibility policy (`model, entity,
# mutation, rows) -> collapses`): this scope takes no edge to `m-batch-write`
# (the `m-unit-work ↮ m-batch-write` contract), so `plan_flush` accepts it as
# an OPTIONAL parameter the composition layer supplies (`parallax.snapshot.handle`
# for production, the conformance compile lane identically) — omitted (`None`)
# is a pure no-op collapse stage, never a behavior a caller must opt into just to
# keep per-instruction lowering.
CollapsePolicy = Callable[[Metamodel, EntityMetadata, str, Sequence[Mapping[str, object]]], bool]

# The injected batch-GROUPING key (`model, entity, mutation, row) -> key`): the
# physical shape two adjacent rows must share to belong to one collapse run.
# Deciding it needs the target's physical slot selection, which this scope has no
# edge to (`m-storage-layout`), so it arrives the same way the collapse policy
# does — from the composition layer, which resolves each row against the concrete
# Entity's layout view (`m-sql` "Physical DML ordering": batch grouping compares
# the resulting ordered slot selections). Keys are compared with ``==`` only.
# Omitted (`None`) groups purely by entity, mutation, and Valid-Time bounds.
CollapseGroupKey = Callable[[Metamodel, EntityMetadata, str, Mapping[str, object]], object]


@dataclass(frozen=True, slots=True)
class FlushPlan:
    """The neutral, execution-ordered intermediate flush plan (m-unit-work).

    ``writes`` is the coalesced, collapsed, FK-ordered, elision-applied
    sequence — always FLAT (an :class:`AtomicUnit` never survives past
    FK-ordering; its member writes are inlined, adjacent, in their own
    resolved-row order). ``tx_instant`` is the attempt's lazy
    :class:`~parallax.core.unit_work.TransactionInstant`, carried as flush
    **context** — never an instruction field — which the composition layer binds
    as ``in_z`` when it lowers a temporal write. It is always present and never
    consulted here: a plan whose surviving writes need no Transaction-Time
    boundary leaves it uncaptured, so an empty or fully coalesced-away flush
    reads no clock (ADR 0010). The composition layer lowers this plan to DML SQL
    through ``m-sql`` / ``m-dialect``; this scope neither takes a dialect nor
    emits SQL.
    """

    writes: tuple[PlannedWrite, ...]
    tx_instant: TransactionInstant


def plan_flush(
    buffer: Sequence[BufferItem],
    observations: Mapping[ObjectKey, WriteObservation],
    tx_instant: TransactionInstant,
    model: Metamodel,
    *,
    collapse: CollapsePolicy | None = None,
    collapse_group: CollapseGroupKey | None = None,
) -> FlushPlan:
    """Plan a flush: coalesce -> collapse -> FK-order -> elide, then attach
    observations.

    Pure. Returns the neutral :class:`FlushPlan` the composition layer lowers to
    DML; this function renders no SQL and takes no dialect (the ``m-unit-work``
    seam is DML-neutral by DAG design). ``tx_instant`` is threaded onto the
    result untouched — planning never captures it, so cancellation and elision
    decide whether a clock is read at all. ``collapse`` is the injected
    ``m-batch-write`` vocabulary (omitted: the collapse stage is a no-op) and
    ``collapse_group`` the injected physical-shape grouping key a run's rows must
    share (omitted: rows group by entity, mutation, and Valid-Time bounds alone).
    """
    targets = _targets(model)
    coalesced = _coalesce(buffer, targets)
    collapsed = _collapse(coalesced, targets, collapse, collapse_group, observations)
    ordered = _fk_order(collapsed, targets)
    elided = _elide(ordered, targets)
    writes = tuple(_attach_observation(instr, observations, targets) for instr in elided)
    return FlushPlan(writes=writes, tx_instant=tx_instant)


# --------------------------------------------------------------------------- #
# Object identity.                                                             #
# --------------------------------------------------------------------------- #
def object_key(instruction: WriteInstruction, model: Metamodel) -> ObjectKey | None:
    """The identity of the single object a keyed write targets, or ``None``.

    ``None`` when the instruction is not a single-row keyed write, when its
    entity spelling names no Entity of ``model``, when the row does not carry
    every primary-key attribute (a pk-generated insert whose key is entirely
    DB-computed), or when a carried primary-key VALUE is itself a DB-computed
    marker (`m-pk-gen`'s `{computed: ...}` / `{increment: ...}` — a
    marker-shaped pk value has no coalescing identity, exactly like an absent
    one) — an unidentifiable write is never coalesced nor observation-bound.
    """
    return _object_key(instruction, _targets(model))


def _object_key(instruction: WriteInstruction, targets: _Targets) -> ObjectKey | None:
    """:func:`object_key` over an already-resolved flush context.

    Primary-key resolution is FAMILY-EFFECTIVE: an inheritance participant's key
    is declared on the root alone (m-inheritance "Inherited members"), so the
    Entity's own declared Attributes are wrongly empty for a concrete subtype —
    every corpus family's own keyed writes — and the applicable member chain the
    Inheritance Facet precomputes is what carries the inherited key.
    """
    if not isinstance(instruction, KeyedWrite) or len(instruction.rows) != 1:
        return None
    entity = targets.entity(instruction.entity)
    if entity is None:
        return None
    # An accepted Entity always carries a primary key, so the family-effective
    # chain is never empty and only the row itself can leave a write unkeyed.
    pk_names = _primary_key_names(targets, entity)
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


def _primary_key_names(targets: _Targets, entity: EntityMetadata) -> list[str]:
    """``entity``'s family-effective primary-key Attribute names, in chain order."""
    return [
        attribute.identity.name
        for attribute in targets.members(entity)
        if isinstance(attribute.primary_key, PrimaryKey)
    ]


# --------------------------------------------------------------------------- #
# Coalesce (same-transaction insert-then-update / insert-then-delete).         #
# --------------------------------------------------------------------------- #
def _coalesce(buffer: Sequence[BufferItem], targets: _Targets) -> list[BufferItem]:
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
        key = _object_key(instruction, targets)
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
            result[index] = _merge_update_into_insert(base, instruction, targets)
        elif verb in _DELETE_VERBS and key in pending_insert:
            # Insert-then-delete cancels: the pending insert annihilates, no DML.
            result[pending_insert.pop(key)] = None
        else:
            result.append(instruction)
    return [item for item in result if item is not None]


def _merge_update_into_insert(
    insert: KeyedWrite, update: KeyedWrite, targets: _Targets
) -> KeyedWrite:
    """Overlay ``update``'s non-key row fields onto ``insert``'s row.

    The coalesced write keeps the insert's mutation verb and Valid-Time bounds (so it
    still opens a current milestone / fully-current rectangle at lowering per
    temporal flavor) but carries the FINAL values — no ``INSERT`` + ``UPDATE``.
    """
    entity = targets.entity(insert.entity)
    # Both instructions already carry a resolved object key, so the Entity is
    # always known here; the guard keeps the walk total rather than asserting.
    pk_names: set[str] = set() if entity is None else set(_primary_key_names(targets, entity))
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
    targets: _Targets,
    collapse: CollapsePolicy | None,
    group: CollapseGroupKey | None,
    observations: Mapping[ObjectKey, WriteObservation],
) -> list[BufferItem]:
    """Merge each ADJACENT run of same-entity, same-mutation, single-row keyed
    writes into one multi-row instruction, per the injected ``collapse`` policy.

    Deterministic in BUFFER order: a run starts the moment a single-row keyed
    write's entity+mutation first appears (or changes from the prior run) and
    ends the moment a non-matching item interrupts it — a differently-keyed
    instruction, a :class:`PredicateWrite`, an already-multi-row instruction, or
    an :class:`AtomicUnit` — so a run NEVER regroups across one of these
    boundaries, and an :class:`AtomicUnit` is never a merge candidate itself
    (opaque, exactly as coalesce treats it). A change in the injected ``group``
    key ends a run too: rows whose physical shapes differ can never share one
    statement, so they must never share one run, and splitting HERE keeps every
    same-shaped neighbourhood collapsible instead of decomposing the lot. A row
    whose
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
    run_group: object = None

    def group_key(item: KeyedWrite) -> object:
        entity = targets.entity(item.entity)
        if group is None or entity is None:
            return None
        return group(targets.model, entity, item.mutation, item.rows[0])

    def flush_run() -> None:
        if not run:
            return
        entity = targets.entity(run[0].entity)
        rows = [row for w in run for row in w.rows]
        if len(run) == 1 or entity is None:
            result.extend(run)
        elif collapse(targets.model, entity, run[0].mutation, rows):
            result.append(_merge_rows(run))
        else:
            result.extend(run)
        run.clear()

    def observed(item: KeyedWrite) -> bool:
        key = _object_key(item, targets)
        return key is not None and key in observations

    for item in buffer:
        if isinstance(item, KeyedWrite) and len(item.rows) == 1 and not observed(item):
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
# FK-order (topological over the declared foreign-key graph).                  #
# --------------------------------------------------------------------------- #
def _fk_order(items: Sequence[BufferItem], targets: _Targets) -> list[WriteInstruction]:
    """Order writes so a parent row inserts before a child that references it and
    deletes after: inserts parent-first, deletes child-first, updates between.

    A READLESS :class:`~parallax.core.unit_work.PredicateWrite` is an ORDERING
    BARRIER: it stays at its authored position and partitions the pending
    sequence into independently reorderable REGIONS, with the bucket sort below
    applied WITHIN each region alone. Nothing crosses it in either direction.
    Unlike a keyed or materialized write, a readless predicate does not reveal
    which rows it touches, so moving another write across it could change which
    rows it matches — a reordering the planner cannot prove safe. The barrier is
    private planning structure: it produces no group, wrapper, or flag in the
    result, only a position nothing may pass.

    An :class:`AtomicUnit` participates as ONE pseudo-instruction — ranked and
    bucketed by its own first member write (every member shares the SAME
    mutation and target entity, since a predicate write's materialization is
    single-verb/single-entity by construction) — then FLATTENED back into its
    member writes, in their own resolved-row order, once the bucket sort has
    fixed its position: this is how it "moves as one block."
    """
    ranks = _fk_ranks(targets.model)

    def representative(item: BufferItem) -> WriteInstruction:
        return item.writes[0] if isinstance(item, AtomicUnit) else item

    def rank(item: BufferItem) -> int:
        entity = targets.entity(_instruction_entity(representative(item)))
        return 0 if entity is None else ranks.get(entity.identity, 0)

    def mutation(item: BufferItem) -> str:
        return representative(item).mutation

    def order_region(region: Sequence[BufferItem]) -> list[BufferItem]:
        inserts = [i for i in region if mutation(i) in _INSERT_VERBS]
        updates = [i for i in region if mutation(i) in _UPDATE_VERBS]
        deletes = [i for i in region if mutation(i) in _DELETE_VERBS]
        inserts.sort(key=rank)  # ascending rank: referenced entities (parents) first
        # descending rank: referencing entities (children) first
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
    return [
        write
        for item in ordered
        for write in (item.writes if isinstance(item, AtomicUnit) else (item,))
    ]


def _fk_ranks(model: Metamodel) -> dict[EntityIdentity, int]:
    """A topological rank per entity: a referenced entity ranks before its referencer.

    A ``many-to-one`` relationship means the source holds the foreign key (source
    after related); a ``one-to-many`` means the related entity holds it (related
    after source). ``one-to-one`` contributes no FK-order edge because its
    storage owner is ambiguous. Ties break by the accepted model's own canonical
    Entity order; a (defensive) cycle falls back to it too.

    Only DEFINING declarations contribute: a reverse declaration names a defining
    one rather than repeating it, and the inverted direction it denotes yields
    the very edge the defining side already contributed, so reading both would
    add nothing and would need the paired cardinality this scope cannot see.
    Every declared target is an accepted Entity of this model, so an edge always
    lands on a ranked position.
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
    return instruction.target.entity


# --------------------------------------------------------------------------- #
# Elide (empty effective change set).                                          #
# --------------------------------------------------------------------------- #
def _elide(instructions: Sequence[WriteInstruction], targets: _Targets) -> list[WriteInstruction]:
    """Drop a keyed update whose effective change set is empty.

    A keyed update carrying only its primary key names no changed field, so it emits
    no DML — the net-zero elision (uniform for non-temporal and temporal entities;
    a value-identical milestone is never fabricated). Predicate-write per-row no-op
    elimination belongs to the materialization boundary, not this planner.
    """
    return [i for i in instructions if not _is_empty_keyed_update(i, targets)]


def _is_empty_keyed_update(instruction: WriteInstruction, targets: _Targets) -> bool:
    if not isinstance(instruction, KeyedWrite) or instruction.mutation not in _UPDATE_VERBS:
        return False
    entity = targets.entity(instruction.entity)
    if entity is None:
        return False
    pk_names = set(_primary_key_names(targets, entity))
    return all(all(key in pk_names for key in row) for row in instruction.rows)


# --------------------------------------------------------------------------- #
# Observation binding.                                                         #
# --------------------------------------------------------------------------- #
def _attach_observation(
    instruction: WriteInstruction,
    observations: Mapping[ObjectKey, WriteObservation],
    targets: _Targets,
) -> PlannedWrite:
    key = _object_key(instruction, targets)
    observation = observations.get(key) if key is not None else None
    return PlannedWrite(
        instruction=instruction,
        observation=observation,
        expected_affected=_expected_affected(instruction, observation),
    )


def _expected_affected(
    instruction: WriteInstruction, observation: WriteObservation | None
) -> int | None:
    """The affected-rows expectation `m-opt-lock` attaches at flush.

    ``1`` for a keyed ``update``/``delete`` bound to a Version Observation (a
    versioned row this unit of work observed) — in EITHER concurrency mode, so a
    vanished row is caught even under a locking-mode write the version gate never
    guards. Nothing else ever carries one (a non-versioned entity's row, or a
    write whose row carries its version as plain caller-authored data rather than
    a recorded observation), so this reduces to the single check below without a
    metamodel lookup of its own.
    """
    if not isinstance(instruction, KeyedWrite) or instruction.mutation not in (
        *_UPDATE_VERBS,
        *_DELETE_VERBS,
    ):
        return None
    if not isinstance(observation, VersionObservation):
        return None
    return 1
