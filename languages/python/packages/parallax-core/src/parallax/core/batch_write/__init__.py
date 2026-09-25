from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.core import inheritance, opt_lock, temporal_read
from parallax.core.metamodel import (
    ApplicationAssigned,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
)

__all__ = [
    "collapses",
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


def _primary_key(model: Metamodel, entity: EntityMetadata) -> AttributeMetadata:
    position = inheritance.view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise RuntimeError(f"{entity.identity.canonical}: no compiled inheritance position")
    return position.primary_key


def _is_versioned(model: Metamodel, entity: EntityMetadata) -> bool:
    return isinstance(
        opt_lock.view(model).key(entity.identity),
        opt_lock.ExplicitVersion | opt_lock.TransactionTimeDerived,
    )


def _is_temporal(model: Metamodel, entity: EntityMetadata) -> bool:
    return isinstance(
        temporal_read.view(model).shape(entity.identity),
        temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
    )


def _is_pk_gen_managed(model: Metamodel, entity: EntityMetadata) -> bool:
    """Whether ``entity``'s family primary key is framework-allocated
    (`m-pk-gen`) — each row's own key allocation is independent, so a shared
    multi-row statement cannot express it."""
    primary_key = _primary_key(model, entity).primary_key
    return isinstance(primary_key, PrimaryKey) and not isinstance(
        primary_key.generation, ApplicationAssigned
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
    key_name = _primary_key(model, entity).identity.name
    assigned = [
        {k: v for k, v in row.items() if k != key_name and k not in _OBSERVATION_CONTROL_KEYS}
        for row in rows
    ]
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
