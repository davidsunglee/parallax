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

# The ONE reserved observation control key a flush-time authored row may carry
# (`m-opt-lock`; ADR 0013) — never legitimate batch-collapse input: a row
# explicitly carrying its own observed version is an explicit
# per-row-observation signal, so a run containing one never collapses. A
# Transaction-Time gate is authored beside the write rather than in a row, so no
# row key names one.
_OBSERVATION_CONTROL_KEYS: Final[frozenset[str]] = frozenset({"observedVersion"})


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
    (`m-batch-write.md` "Batching is a membership decision"). ``False`` for a
    temporal entity (its keyed
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
    ``UPDATE ... WHERE id IN (...)`` statement (`m-batch-write.md` "Batching is a
    membership decision"): only
    when the target is UNVERSIONED, non-temporal, no row carries an explicit
    observation control key, and every row assigns the IDENTICAL non-key
    values (the uniform-value case; a non-uniform run stays decomposed to one
    keyed statement per distinct key, never this module's concern). A
    **versioned** entity's update NEVER collapses,
    uniform or not — the gate/advance binds a PER-ROW observed version no
    shared statement can carry."""
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
    ``DELETE ... WHERE id IN (...)`` statement (`m-batch-write.md` "Batching is a
    membership decision" — the delete analogue of the multi-row INSERT). ``False``
    for a temporal entity (`terminate`/`terminateUntil` are `m-txtime-write` /
    `m-bitemp-write` territory) or a VERSIONED one — a versioned entity's set-based
    delete NEVER collapses: each row is removed under its own
    prior observation and its own exactly-one affected-row expectation, in
    either concurrency mode, and optimistic mode binds that row's version as its
    own gate on top (`m-batch-write-004` is the ungated locking form,
    `m-opt-lock-015` the gated one)."""
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
    (``BatchingStrategy.collapses``'s own shape) — the function
    :mod:`parallax.snapshot.handle` wires into the
    :class:`~parallax.core.unit_work.WritePlanner` and the conformance engine
    reaches through the SAME ``build_write_planner`` factory, dispatching to
    :func:`insert_collapses` / :func:`update_collapses` / :func:`delete_collapses`
    by ``mutation``.

    Insert and delete eligibility is a property of the TARGET alone, so only the
    update branch consults ``rows``: whether the rows are shaped alike is the
    injected grouping key's question, already settled before this is called."""
    if mutation in _INSERT_MUTATIONS:
        return insert_collapses(model, entity)
    if mutation in _UPDATE_MUTATIONS:
        return update_collapses(model, entity, rows)
    return delete_collapses(model, entity)
