"""``parallax.snapshot.handle`` — the composition surface (connect / transact / lowering).

This is the layer that legally sees **both** the neutral write-instruction IR /
flush planner (``m-unit-work``) **and** SQL generation (``m-sql`` / ``m-dialect``):
the module DAG forbids ``m-unit-work`` from importing ``m-sql`` (why the planner
emits a neutral :class:`~parallax.core.unit_work.FlushPlan`) and forbids ``m-sql``
from importing ``m-unit-work``, so the write-DML → SQL lowering — the deliberate
``m-sql`` edge M3 deferred — is composed **here**. :func:`lower_write` is the single
lowering function; both the developer transaction path (the injected
``FlushExecutor``) and the conformance engine reuse it (the conformance family is
the import-side DAG exemption), so there is exactly one write-lowering seam.

M4 lowers the **non-temporal keyed** write forms (`insert` / `update` / `delete` on
a non-temporal, non-inheritance entity, version carried as plain column data). The
temporal milestone forms (close-and-chain, rectangle splits), the optimistic-lock
version gate/advance, predicate-selected (set-based) writes, and inheritance-family
DML land with the write path (COR-3 Phase 8); reaching one raises a loud
:class:`WriteLoweringError` naming the deferral, never a wrong emission — mirroring
the read compiler's forward-error posture.
"""

from __future__ import annotations

from collections.abc import Mapping

from parallax.core.db_port import JsonDocument
from parallax.core.descriptor import Entity, Metamodel, column_order
from parallax.core.dialect import Dialect
from parallax.core.sql_gen import Statement
from parallax.core.unit_work import KeyedWrite, PlannedWrite, PredicateWrite

__all__ = ["WriteLoweringError", "lower_write"]

# The keyed mutation verbs M4 lowers (the non-temporal write triad). The temporal
# `*Until` / `terminate` verbs open / split / close milestones and land with the
# write path (Phase 8).
_NON_TEMPORAL_VERBS: frozenset[str] = frozenset({"insert", "update", "delete"})


class WriteLoweringError(ValueError):
    """A planned write cannot be lowered to DML by the M4 (non-temporal keyed) path."""


def lower_write(planned: PlannedWrite, meta: Metamodel, dialect: Dialect) -> list[Statement]:
    """Lower one planned write to its ordered DML statements (m-sql write DML).

    ``planned`` is one execution-ordered item of a :class:`FlushPlan`: a (coalesced,
    FK-ordered, elided) write instruction plus its bound transaction observation.
    Returns the ordered statements the write emits — one for a keyed non-temporal
    write, more once the temporal / rectangle-split forms land (Phase 8). The
    temporal forms will additionally consume the flush's Clock-supplied processing
    instant (``FlushPlan.tx_instant``, bound as ``in_z`` / the close instant); the
    non-temporal forms M4 lowers do not, so it is threaded in with those forms.
    """
    instruction = planned.instruction
    if isinstance(instruction, PredicateWrite):
        raise WriteLoweringError(
            f"predicate-selected (set-based) write on {instruction.target.entity!r}: "
            "materialize-then-lower lands with the write path (COR-3 Phase 8; m-batch-write / "
            "m-opt-lock)"
        )
    observation = planned.observation
    if observation is not None and (
        observation.version is not None or observation.in_z is not None
    ):
        raise WriteLoweringError(
            f"optimistic-lock gated write on {instruction.entity!r}: the version gate / advance "
            "lands with the write path (COR-3 Phase 8; m-opt-lock)"
        )
    entity = meta.entity(instruction.entity)
    if entity.is_temporal:
        raise WriteLoweringError(
            f"temporal write on {entity.name!r} ({entity.temporal}): milestone lowering "
            "(close-and-chain / rectangle split) lands with the write path (COR-3 Phase 8; "
            "m-audit-write / m-bitemp-write)"
        )
    if entity.inheritance is not None:
        raise WriteLoweringError(
            f"inheritance-family write on {entity.name!r}: tag / concrete-subtype DML lands with "
            "the write path (COR-3 Phase 8; m-inheritance)"
        )
    if instruction.business_from is not None or instruction.business_to is not None:
        raise WriteLoweringError(
            f"{instruction.mutation!r} on the non-temporal entity {entity.name!r} carries a "
            "business bound; bounded writes are temporal (COR-3 Phase 8)"
        )
    if instruction.mutation not in _NON_TEMPORAL_VERBS:
        raise WriteLoweringError(
            f"{instruction.mutation!r} is a temporal milestone verb; its lowering lands with the "
            "write path (COR-3 Phase 8)"
        )
    if instruction.mutation == "insert":
        return [_lower_insert(entity, instruction, dialect)]
    if instruction.mutation == "update":
        return [_lower_update(entity, instruction, dialect)]
    return [_lower_delete(entity, instruction, dialect)]


def _lower_insert(entity: Entity, instruction: KeyedWrite, dialect: Dialect) -> Statement:
    """`insert into <table>(<present columns in columnOrder>) values (?, …)`.

    Only the columns the write input names are emitted — a row omitting a nullable
    column produces a narrower `INSERT` (never an explicit `NULL` bind), matching the
    corpus (`m-unit-work-003` inserts 4 of OrderItem's 5 columns).
    """
    cells = _ordered_cells(entity, instruction.rows[0])
    columns = ", ".join(dialect.quote(column) for _, column, _ in cells)
    holes = ", ".join("?" for _ in cells)
    binds = tuple(bind for _, _, bind in cells)
    return Statement(f"insert into {entity.table}({columns}) values ({holes})", binds)


def _lower_update(entity: Entity, instruction: KeyedWrite, dialect: Dialect) -> Statement:
    """`update <table> set <non-pk columns in columnOrder> = ? where <pk> = ?`.

    The `SET` columns follow descriptor `columnOrder` (not the row's data order); the
    `WHERE` keys on the primary key. Binds are the set values then the key values.
    """
    pk_columns = {attr.column for attr in entity.primary_key}
    set_cells = [
        cell for cell in _ordered_cells(entity, instruction.rows[0]) if cell[1] not in pk_columns
    ]
    assignments = ", ".join(f"{dialect.quote(column)} = ?" for _, column, _ in set_cells)
    where_sql, key_binds = _key_predicate(entity, instruction.rows[0], dialect)
    binds = (*(bind for _, _, bind in set_cells), *key_binds)
    return Statement(f"update {entity.table} set {assignments} where {where_sql}", binds)


def _lower_delete(entity: Entity, instruction: KeyedWrite, dialect: Dialect) -> Statement:
    """`delete from <table> where <pk> = ?` — keyed by the primary key."""
    where_sql, key_binds = _key_predicate(entity, instruction.rows[0], dialect)
    return Statement(f"delete from {entity.table} where {where_sql}", key_binds)


def _ordered_cells(entity: Entity, row: Mapping[str, object]) -> list[tuple[int, str, object]]:
    """The row's present members as `(columnOrder index, column, bind)`, ordered.

    Each row key names a declared scalar attribute or a value object; a value-object
    member binds as one :class:`JsonDocument` in its `columnOrder` position (the
    whole document — the write never decomposes it), a scalar binds its value.
    """
    members = _members(entity)
    order = {column: index for index, column in enumerate(column_order(entity))}
    cells: list[tuple[int, str, object]] = []
    for name, value in row.items():
        column, is_value_object = members[name]
        bind = JsonDocument(value) if is_value_object else value
        cells.append((order[column], column, bind))
    cells.sort(key=lambda cell: cell[0])
    return cells


def _key_predicate(
    entity: Entity, row: Mapping[str, object], dialect: Dialect
) -> tuple[str, tuple[object, ...]]:
    """The `<pk1> = ? [and <pk2> = ?]` predicate and its ordered key binds."""
    keys = entity.primary_key
    predicate = " and ".join(f"{dialect.quote(attr.column)} = ?" for attr in keys)
    binds = tuple(row[attr.name] for attr in keys)
    return predicate, binds


def _members(entity: Entity) -> dict[str, tuple[str, bool]]:
    """Map each writable member name to `(column, is_value_object)`."""
    members: dict[str, tuple[str, bool]] = {
        attr.name: (attr.column, False) for attr in entity.attributes
    }
    for value_object in entity.value_objects:
        members[value_object.name] = (value_object.column, True)
    return members
