"""``parallax.core.batch_write`` enforcement scope (m-batch-write).

The set-based / batched-write COLLAPSE VOCABULARY: pure functions over the
``m-unit-work`` write-instruction IR that decide whether a run of buffered,
same-entity, same-mutation single-row :class:`~parallax.core.unit_work.KeyedWrite`
instructions **collapses** into one multi-row instruction, or stays decomposed
(``m-batch-write.md`` "Set-based flush"). This module **renders no SQL** — the
module DAG pins it to ``base`` / ``db_port`` / ``metamodel`` / ``inheritance`` /
``op_algebra`` / ``unit_work`` only (``modules.md`` §7's sole declared edge is
``m-batch-write --> m-unit-work``); the composition layer
(:mod:`parallax.snapshot.handle`, the sole module cleared to import both this
scope and ``m-sql``/``m-dialect``) renders the collapsed instruction's DML, and
the same layer injects this module's decision functions into
:func:`~parallax.core.unit_work.planner.plan_flush`'s optional collapse-policy
parameter — the injection the ``m-unit-work ↛ m-batch-write`` contract demands
(``m-unit-work`` MUST NOT import this scope). The planner resolves the write
IR's own entity spelling once per flush, so every entry point below takes the
already-resolved Entity Metadata rather than a name.

What this module decides is **eligibility**, never **grouping**. Whether a run's
rows are shaped alike enough to share one statement is a physical question — it
compares filtered Table Layout slot selections (`m-sql` "Physical DML ordering")
— and this scope has no edge to ``m-storage-layout``; the composition layer
answers it separately (:func:`parallax.snapshot.handle.collapse_group_key`,
injected into the planner beside :func:`collapses`), so by the time a run reaches
a function here its rows already share one physical shape.

Three collapse rules (``m-batch-write.md`` L15-26):

- **insert** — same-entity inserts ALWAYS collapse into one multi-row
  ``INSERT``, UNLESS the entity's primary key is pk-gen **managed** (a
  ``sequence`` / ``max`` generation — each row's own key allocation is
  independent, so a shared statement cannot express it, ``m-pk-gen``). A
  versioned entity's insert collapses too: the initial version is a derived
  CONSTANT (``opt_lock.INITIAL_VERSION``), never an observation, so no per-row
  gate is needed.
- **update** — same-entity updates setting the SAME columns collapse into a
  batched ``UPDATE``: once per distinct key when the new values differ, or ONE
  statement with an ``IN`` predicate when the new value is UNIFORM across the
  keys. A **versioned** entity's update NEVER collapses (even when uniform) —
  every row's gate/advance binds its OWN observed version, which one shared
  statement cannot carry (``m-opt-lock``, ADR 0014); it always decomposes to
  per-row keyed updates.
- **delete** — same-entity, NON-VERSIONED deletes collapse into one ``DELETE``
  with an ``IN`` predicate; a VERSIONED entity's delete never collapses (each
  row's own observed version must gate its own statement).

Every one of those facts is family-wide — a version Attribute, an As-Of Axis,
and the primary key are all root-owned — so each is read off the family-effective
member chain the Inheritance Facet precomputes rather than off the position's own
declarations, which are empty for a concrete subtype.

A **temporal** entity's keyed writes never reach this module's collapse
decision at all (`m-txtime-write` / `m-bitemp-write` own that lowering) —
every function here defensively answers "does
not collapse" for one, so an accidental call never silently mis-batches a
milestone chain.

Prior art (Reladomo; semantics, not idioms): buffered same-entity combine
mirrors ``TxOperations``/``combineAll()``; the uniform-value ``IN``-list
collapse mirrors ``MultiUpdateOperation`` vs ``BatchUpdateOperation``
(``UpdateOperation.canBeBatched``/``canBeMultiUpdated``); per-row affected-row
gates mirror ``checkUpdateResult``/``checkOptimisticResults``; Reladomo
deliberately UN-batches under optimistic locking (a per-row version bind even
inside a JDBC batch). Readless SET-BASED statements exist in Reladomo only for
``DELETE`` (``deleteAll()``; a *dated* ``deleteAll()`` throws, and
``terminateAll()`` resolves per-object instead) — there is no
``updateUsingOperation``: a bulk update always resolves rows first. Parallax's
readless predicate UPDATE (the unversioned, non-temporal exception,
``m-opt-lock.md`` "The one exception") is therefore a genuine widening beyond
Reladomo's own readless surface, owned by this module's sibling concern (the
predicate-write vocabulary, `m-batch-write.md` "Predicate-selected readless
forms") — rendered by :mod:`parallax.snapshot.handle`, decided nowhere in this
module (a readless predicate write is not a *buffered* collapse at all: there
is nothing tracked to combine, only one instruction to render).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.core import inheritance
from parallax.core.metamodel import (
    ApplicationAssigned,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
)

__all__ = [
    "collapses",
    "delete_collapses",
    "insert_collapses",
    "update_collapses",
]

_INSERT_MUTATIONS: Final[frozenset[str]] = frozenset({"insert", "insertUntil"})
_UPDATE_MUTATIONS: Final[frozenset[str]] = frozenset({"update", "updateUntil"})

# The observation control keys a case-authored row may carry (`m-opt-lock`; ADR
# 0013) — never legitimate batch-collapse input: a row explicitly carrying its
# own observed version/`in_z` is an explicit per-row-observation signal, so a
# run containing one never collapses (mirrors the conformance engine's own
# pre-existing `_rows_carry_observation_keys` guard, restated here as this
# module's own single source of truth for the rule).
_OBSERVATION_CONTROL_KEYS: Final[frozenset[str]] = frozenset({"observedVersion", "observedTxStart"})


def _family_members(model: Metamodel, entity: EntityMetadata) -> Sequence[AttributeMetadata]:
    """``entity``'s family-effective Attributes: its own ancestry chain's."""
    position = inheritance.view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return entity.declared_attributes
    return position.applicable_attributes


def _is_versioned(model: Metamodel, entity: EntityMetadata) -> bool:
    return any(attribute.optimistic_locking for attribute in _family_members(model, entity))


def _is_temporal(model: Metamodel, entity: EntityMetadata) -> bool:
    """Whether ``entity``'s family declares an As-Of Axis.

    Temporality is family-wide and root-owned, so the question is asked of the
    family root's own declaration; a descendant declares none of its own.
    """
    position = inheritance.view(model).entity(entity.identity)
    root = entity if position is None else model.entity(position.root)
    return root is not None and bool(root.declared_as_of_axes)


def _is_pk_gen_managed(model: Metamodel, entity: EntityMetadata) -> bool:
    """Whether ``entity``'s (family-effective) primary key is framework-allocated
    (`m-pk-gen`) — each row's own key allocation is independent, so a shared
    multi-row statement cannot express it."""
    return any(
        isinstance(attribute.primary_key, PrimaryKey)
        and not isinstance(attribute.primary_key.generation, ApplicationAssigned)
        for attribute in _family_members(model, entity)
    )


def _rows_carry_observation_keys(rows: Sequence[Mapping[str, object]]) -> bool:
    return any(_OBSERVATION_CONTROL_KEYS & row.keys() for row in rows)


def insert_collapses(model: Metamodel, entity: EntityMetadata) -> bool:
    """Whether same-entity ``insert`` rows collapse into one multi-row ``INSERT``
    (`m-batch-write.md` L17-19). ``False`` for a temporal entity (its keyed
    writes are `m-txtime-write` / `m-bitemp-write` territory, never this
    module's decision) or a pk-gen-**managed** entity; ``True`` otherwise,
    versioned or not (the initial version is a derived constant, never an
    observation, `m-opt-lock.INITIAL_VERSION`)."""
    if _is_temporal(model, entity):
        return False
    return not _is_pk_gen_managed(model, entity)


def update_collapses(
    model: Metamodel, entity: EntityMetadata, rows: Sequence[Mapping[str, object]]
) -> bool:
    """Whether a run of same-entity ``update`` rows collapses into ONE
    ``UPDATE ... WHERE id IN (...)`` statement (`m-batch-write.md` L20-22): only
    when the target is UNVERSIONED, non-temporal, no row carries an explicit
    observation control key, and every row assigns the IDENTICAL non-key
    values (the uniform-value case; a non-uniform run stays decomposed to one
    keyed statement per distinct key, never this module's concern). A
    **versioned** entity's update NEVER collapses,
    uniform or not — the gate/advance binds a PER-ROW observed version no
    shared statement can carry (`m-opt-lock`, ADR 0014)."""
    if _is_temporal(model, entity):
        return False
    if _is_versioned(model, entity):
        return False
    if _rows_carry_observation_keys(rows):
        return False
    if len(rows) < 2:
        return False
    pk_names = frozenset(
        attribute.identity.name
        for attribute in _family_members(model, entity)
        if isinstance(attribute.primary_key, PrimaryKey)
    )
    excluded = pk_names | _OBSERVATION_CONTROL_KEYS
    assigned = [{k: v for k, v in row.items() if k not in excluded} for row in rows]
    first = assigned[0]
    return all(candidate == first for candidate in assigned[1:])


def delete_collapses(model: Metamodel, entity: EntityMetadata) -> bool:
    """Whether same-entity ``delete`` rows collapse into one
    ``DELETE ... WHERE id IN (...)`` statement (`m-batch-write.md` L23-26,
    "the delete analogue of the multi-row INSERT"). ``False`` for a temporal
    entity (`terminate`/`terminateUntil` are `m-txtime-write` / `m-bitemp-write`
    territory) or a VERSIONED one — a versioned entity's set-based delete
    NEVER collapses (`m-batch-write.md` L26): each row must be removed under
    its own observed version (`m-batch-write-004`)."""
    if _is_temporal(model, entity):
        return False
    return not _is_versioned(model, entity)


def collapses(
    model: Metamodel,
    entity: EntityMetadata,
    mutation: str,
    rows: Sequence[Mapping[str, object]],
) -> bool:
    """The single ``(model, entity, mutation, rows) -> bool`` entry point
    (`~parallax.core.unit_work.planner.CollapsePolicy`'s own shape) — the
    function :mod:`parallax.snapshot.handle` and the conformance engine inject
    into :func:`~parallax.core.unit_work.planner.plan_flush` IDENTICALLY,
    dispatching to :func:`insert_collapses` / :func:`update_collapses` /
    :func:`delete_collapses` by ``mutation``.

    Insert and delete eligibility is a property of the TARGET alone, so only the
    update branch consults ``rows``: whether the rows are shaped alike is the
    injected grouping key's question, already settled before this is called."""
    if mutation in _INSERT_MUTATIONS:
        return insert_collapses(model, entity)
    if mutation in _UPDATE_MUTATIONS:
        return update_collapses(model, entity, rows)
    return delete_collapses(model, entity)
