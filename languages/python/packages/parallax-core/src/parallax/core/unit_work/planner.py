"""The pure flush planner (m-unit-work).

Given a unit of work's buffered write instructions, the observations it recorded,
the Clock-supplied processing instant, and the metamodel, :func:`plan_flush`
produces a **neutral, execution-ordered intermediate plan** — the coalesced,
FK-ordered, elision-applied sequence of write instructions with each keyed
instruction's bound observation attached. It is a **pure** function of its inputs.

**It emits no SQL.** The module DAG pins ``m-unit-work -> m-op-algebra`` and
``m-unit-work -> m-db-port`` only — there is deliberately **no** edge to ``m-sql``
or ``m-dialect`` — so this planner cannot render final DML. The write-DML -> SQL
lowering (the deliberate ``m-sql`` edge) happens one layer up, at the composition
surface that legally sees both (the snapshot handle / conformance engine), which
lowers each :class:`PlannedWrite` against :class:`FlushPlan.tx_instant`. This is
the same seam ``m-temporal-read`` resolved: rewrite into neutral terms here,
compose SQL above.

The stages, in order (``m-unit-work`` "Same-transaction write coalescing"):

- **coalesce** — a same-transaction keyed insert-then-update of one object folds
  the update into the pending insert (a single final-value write, per temporal
  flavor at lowering); a keyed insert-then-delete of one object **cancels** (both
  annihilate, no DML). The batch **collapse** stage and call-time materialization
  of versioned/temporal predicate writes are Phase 8, not built here.
- **FK-order** — a topological order over the descriptor foreign-key graph:
  inserts parent-first, deletes child-first, updates between (the canonical
  INSERT -> UPDATE -> DELETE flush order).
- **elide** — a keyed update whose effective change set is empty (a row carrying
  only its primary key) emits no instruction; a net-zero coalescing chain
  (insert-then-delete) already emitted nothing in coalesce.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core import inheritance
from parallax.core.descriptor import Metamodel
from parallax.core.unit_work.instructions import KeyedWrite, WriteInstruction

__all__ = [
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

    The optimistic-lock version and/or observed processing-from a gated write binds,
    attached to a planned write at flush and **never** carried on the durable
    instruction. Neutral here: this milestone pairs it onto the plan; lowering the
    version gate / advance into SQL is the composition layer's job (M4 / Phase 8).

    ``business_from`` / ``business_to`` / ``payload`` extend the vocabulary for a
    TEMPORAL observation (COR-3 Phase 8 increment 4; `m-audit-write` /
    `m-bitemp-write`): ``business_from`` is the observed rectangle's own business-axis
    lower bound — the bitemporal optimistic gate's discriminator candidate AND (via
    :mod:`parallax.core.bitemp_write`'s planning) the business lower bound the head
    rectangle's upper bound derives from; ``business_to`` is the observed rectangle's
    own business-axis upper bound — the tail rectangle's own upper bound; ``payload``
    is the observed row's OTHER business columns (every scalar / value-object member
    besides the milestone interval bounds), the "prior rectangle" values a bitemporal
    split's head/tail carry forward (`m-bitemp-write` "Head/tail old values come from
    the observed prior rectangle"). All three are ``None`` for a non-temporal or
    audit-only observation (an audit-only chain uses the instruction's own authored
    full row, never an observed payload, `m-audit-write`). This is Python-internal
    vocabulary, NOT the serialized instruction (ADR 0013 stands): the reserved
    ``observedVersion`` / ``observedInZ`` control keys stay forbidden on a write row;
    an observation attaches per row at flush, never carried on the instruction.
    """

    version: int | None = None
    in_z: str | None = None
    business_from: str | None = None
    business_to: str | None = None
    payload: Mapping[str, object] | None = None


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
    observation — the M4-era corpus witnesses this plan-level expectation
    never touches, since they never populate an observation for that key).
    """

    instruction: WriteInstruction
    observation: Observation | None = None
    expected_affected: int | None = None


@dataclass(frozen=True, slots=True)
class FlushPlan:
    """The neutral, execution-ordered intermediate flush plan (m-unit-work).

    ``writes`` is the coalesced, FK-ordered, elision-applied sequence. ``tx_instant``
    is the Clock-supplied processing instant carried as flush **context** — never an
    instruction field — that the composition layer binds as ``in_z`` when it lowers
    a temporal write. The composition layer (M4) lowers this plan to DML SQL through
    ``m-sql`` / ``m-dialect``; this scope neither takes a dialect nor emits SQL.
    """

    writes: tuple[PlannedWrite, ...] = ()
    tx_instant: str | None = None


def plan_flush(
    buffer: Sequence[WriteInstruction],
    observations: Mapping[ObjectKey, Observation],
    tx_instant: str | None,
    meta: Metamodel,
) -> FlushPlan:
    """Plan a flush: coalesce -> FK-order -> elide, then attach observations.

    Pure. Returns the neutral :class:`FlushPlan` the composition layer lowers to
    DML; this function renders no SQL and takes no dialect (the ``m-unit-work``
    seam is DML-neutral by DAG design).
    """
    coalesced = _coalesce(buffer, meta)
    ordered = _fk_order(coalesced, meta)
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
def _coalesce(buffer: Sequence[WriteInstruction], meta: Metamodel) -> list[WriteInstruction]:
    """Fold each same-transaction insert-then-X of one object (m-unit-work).

    A keyed single-row insert opens a pending insert for its object; a subsequent
    keyed update of that same object folds its non-key fields into the pending
    insert's row (one final-value write, no intermediate milestone); a subsequent
    keyed delete of that same object cancels the pending insert (both annihilate).
    Every other instruction passes through in order. The pair scope is exactly the
    coalescing witnesses'; a general ordered buffer and predicate-selected buffered
    writes are deferred (D-3).
    """
    result: list[WriteInstruction | None] = []
    pending_insert: dict[ObjectKey, int] = {}
    for instruction in buffer:
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
    return [instruction for instruction in result if instruction is not None]


def _merge_update_into_insert(
    insert: KeyedWrite, update: KeyedWrite, meta: Metamodel
) -> KeyedWrite:
    """Overlay ``update``'s non-key row fields onto ``insert``'s row.

    The coalesced write keeps the insert's mutation verb and business bounds (so it
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
        business_from=insert.business_from,
        business_to=insert.business_to,
    )


# --------------------------------------------------------------------------- #
# FK-order (topological over the descriptor foreign-key graph).                #
# --------------------------------------------------------------------------- #
def _fk_order(instructions: Sequence[WriteInstruction], meta: Metamodel) -> list[WriteInstruction]:
    """Order writes so a parent row inserts before a child that references it and
    deletes after: inserts parent-first, deletes child-first, updates between."""
    ranks = _fk_ranks(meta)

    def rank(instruction: WriteInstruction) -> int:
        return ranks.get(_instruction_entity(instruction), 0)

    inserts = [i for i in instructions if i.mutation in _INSERT_VERBS]
    updates = [i for i in instructions if i.mutation in _UPDATE_VERBS]
    deletes = [i for i in instructions if i.mutation in _DELETE_VERBS]
    inserts.sort(key=rank)  # ascending rank: referenced entities (parents) first
    deletes.sort(key=lambda i: -rank(i))  # descending rank: referencing entities (children) first
    return [*inserts, *updates, *deletes]


def _fk_ranks(meta: Metamodel) -> dict[str, int]:
    """A topological rank per entity: a referenced entity ranks before its referencer.

    A ``many-to-one`` relationship means the source holds the foreign key (source
    after related); a ``one-to-many`` means the related entity holds it (related
    after source). ``one-to-one`` / ``many-to-many`` contribute no FK-order edge
    (ambiguous / join-table; no reachable write depends on them). Ties break by
    declaration order; a (defensive) cycle falls back to declaration order.
    """
    names = [entity.name for entity in meta.entities]
    prereqs: dict[str, set[str]] = {name: set() for name in names}
    for entity in meta.entities:
        for rel in entity.relationships:
            related = rel.related_entity
            if related not in prereqs:
                continue  # a relationship reaching outside this model has no local order
            if rel.cardinality == "many-to-one":
                prereqs[entity.name].add(related)
            elif rel.cardinality == "one-to-many":
                prereqs[related].add(entity.name)
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
    elimination is a materialization concern (Phase 8), not applied here.
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
    observation (a non-versioned entity's row, or an M4-era write whose row
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
