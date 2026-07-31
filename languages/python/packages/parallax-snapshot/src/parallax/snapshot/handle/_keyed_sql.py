"""``parallax.snapshot.handle._keyed_sql`` — physical-shape batch grouping.

Every write family now finalizes into a settled step before lowering
(:class:`~parallax.core.unit_work.WritePlanner`) and renders through
:mod:`parallax.snapshot.handle._step_lowering` from that already-decided step.
:func:`collapse_group_key` is this module's one live seam: the same physical
slot selection that fixes a statement's column list also fixes which buffered
rows may share one, so it answers a row's filtered, table-ordered selection for
the Write Planner's own ``BatchingStrategy`` port — a collapsed multi-row
instruction is same-shaped before any step is ever settled. Every physical
fact comes from the target's Storage Layout Entity view (`_family.entity_layout`)
— its Table, its Table-ordered applicable slots, and its derived discriminator
assignment. Semantic selections stay where they are decided: the
family-effective primary key (`_family.family_primary_key`) names Attribute
identities, which this module maps onto layout slots rather than reading
storage declarations of its own.

The name the composition root reads is spelled bare; the helpers this module
keeps to itself keep their leading underscore because every one of their call
sites is in THIS module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from parallax.core import opt_lock
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import Dialect
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.sql_gen import Statement
from parallax.core.storage_layout import ColumnContributor, EntityLayoutView
from parallax.core.unit_work import KeyedWrite
from parallax.snapshot.handle._family import (
    entity_layout,
    family_primary_key,
    slot_column,
)
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = [
    "collapse_group_key",
    "key_predicate",
    "lower_insert",
]


# A scalar cell's recognized DB-computed marker kinds (`m-pk-gen`;
# `write-instruction.schema.json#/$defs/writeComputedMarker`): `computed` (the
# `max` strategy's `coalesce(max(col), ?) + ?` INSERT fold) and `increment`
# (a self-referential `col = col + ?` SET advance, e.g. a sequence registry's
# `next_val`). Each is legal only at the mutation that can render it.
_MARKER_KEYS: Final[frozenset[str]] = frozenset({"computed", "increment"})


def _layout(meta: Metamodel, entity: EntityMetadata) -> EntityLayoutView:
    """``entity``'s canonical physical layout selection, or a loud refusal when
    it owns no rows (an abstract family position is never a write target)."""
    view = entity_layout(meta, entity)
    if view is None:
        raise WriteLoweringError(f"{entity.identity.name!r}: write target has no effective table")
    return view


def _table(meta: Metamodel, entity: EntityMetadata) -> str:
    return _layout(meta, entity).layout.table.name


def _tag(meta: Metamodel, entity: EntityMetadata) -> tuple[str, str] | None:
    """``(tag column, tag value)`` for an inheritance-family table-per-hierarchy
    concrete, else ``None`` — the discriminator assignment a keyed write derives
    from the layout's own slot (never authored in the neutral write input)."""
    discriminator = _layout(meta, entity).discriminator
    if discriminator is None:
        return None
    return discriminator.slot.column.name, discriminator.value


def _marker_kind(value: object) -> str | None:
    """A scalar cell's DB-computed marker kind (``computed`` / ``increment``),
    or ``None`` for an ordinary literal — classified by SHAPE (a one-key
    mapping naming a recognized marker key), never by the member's declared
    role: a value-object document is wrapped in :class:`JsonDocument` before
    this ever runs, so it is never mistaken for a marker (m-value-object
    "Writing" marker disambiguation)."""
    if isinstance(value, Mapping):
        marker = cast("Mapping[str, object]", value)
        if len(marker) == 1 and (key := next(iter(marker))) in _MARKER_KEYS:
            return key
    return None


def _refuse_unrecognized_marker(
    entity: EntityMetadata, column: str, value: object, context: str
) -> None:
    """Refuse a marker this ``context`` (``insert`` / ``update``) lowering does
    not render — e.g. an ``increment`` marker reaching an INSERT's value list,
    or a ``computed`` marker reaching an UPDATE's `set` clause. Never fires for
    an ordinary literal or a value-object document (already excluded by
    :func:`_marker_kind`'s shape classification)."""
    kind = _marker_kind(value)
    if kind is not None:
        raise WriteLoweringError(
            f"unsupported DB-computed marker on {entity.identity.name!r}.{column}: a {kind!r} "
            f"marker is not recognized for {context} lowering"
        )


def lower_insert(
    entity: EntityMetadata,
    instruction: KeyedWrite,
    dialect: Dialect,
    meta: Metamodel,
    version_attr: AttributeMetadata | None,
) -> Statement:
    """`insert into <table>(<present columns in Table Layout order>) values (?, …)`,
    or the pk-gen `max` INSERT…SELECT form when a scalar cell carries the
    `{computed: "maxPlusOne"}` marker (`m-pk-gen`) — the row form a temporal
    write's chained/opened milestone rows take, which is structurally an
    ordinary full-row insert.

    Only the columns the write input names are emitted — a row omitting a nullable
    column produces a narrower `INSERT` (never an explicit `NULL` bind), matching the
    corpus (`m-unit-work-003` inserts 4 of OrderItem's 5 columns). A versioned entity's
    row derives the INITIAL version (`m-opt-lock.INITIAL_VERSION`) at the version
    column's own slot position, ignoring any row-carried value; an
    inheritance-family (table-per-hierarchy) concrete additionally derives the tag
    column from its own `tagValue` at the layout's Discriminator-tier slot
    (`m-inheritance` / `m-sql` "Table-per-hierarchy DML") — neither is ever authored
    in the neutral write input.
    """
    row = dict(instruction.rows[0])
    if version_attr is not None:
        row[version_attr.identity.name] = opt_lock.INITIAL_VERSION
    cells = _ordered_cells(meta, entity, row, discriminator=True)
    columns = ", ".join(dialect.quote(column) for column, _ in cells)
    has_computed = any(_marker_kind(value) == "computed" for _, value in cells)
    if not has_computed:
        binds: list[object] = []
        for column, value in cells:
            _refuse_unrecognized_marker(entity, column, value, "insert")
            binds.append(value)
        holes = ", ".join("?" for _ in cells)
        return Statement(
            f"insert into {_table(meta, entity)}({columns}) values ({holes})", tuple(binds)
        )
    select_parts: list[str] = []
    binds = []
    for column, value in cells:
        if _marker_kind(value) == "computed":
            _require_max_plus_one(entity, column, value)
            select_parts.append(f"coalesce(max(t0.{dialect.quote(column)}), ?) + ?")
            binds.extend([0, 1])
        else:
            _refuse_unrecognized_marker(entity, column, value, "insert")
            select_parts.append("?")
            binds.append(value)
    select_list = ", ".join(select_parts)
    return Statement(
        f"insert into {_table(meta, entity)}({columns}) select {select_list} "
        f"from {_table(meta, entity)} t0",
        tuple(binds),
    )


def _require_max_plus_one(entity: EntityMetadata, column: str, value: object) -> None:
    marker = cast("Mapping[str, object]", value)
    if marker.get("computed") != "maxPlusOne":
        raise WriteLoweringError(
            f"unsupported DB-computed marker on {entity.identity.name!r}.{column}: "
            f"{marker.get('computed')!r} is not a recognized `computed` strategy (m-pk-gen)"
        )


def _member_contributor(contributor: ColumnContributor) -> str | None:
    """The declared member name behind ``contributor``, or ``None`` for the
    framework-owned discriminator (which no write input ever names)."""
    if isinstance(contributor, AttributeIdentity):
        return contributor.name
    if isinstance(contributor, ValueObjectIdentity):
        return contributor.path[-1]
    return None


def _member_ordinals(layout: EntityLayoutView) -> dict[str, tuple[int, str, bool]]:
    """Each member name the view carries, mapped to its
    ``(slot ordinal, physical column, is a document slot)``.

    The framework-owned discriminator has no member name and is absent: no write
    input ever names it, and every form that emits it derives it from the view's
    own assignment instead.
    """
    ordinals: dict[str, tuple[int, str, bool]] = {}
    for ordinal, slot in enumerate(layout.columns):
        member = _member_contributor(slot.contributor)
        if member is not None:
            is_document = isinstance(slot.contributor, ValueObjectIdentity)
            ordinals[member] = (ordinal, slot.column.name, is_document)
    return ordinals


def collapse_group_key(
    meta: Metamodel, entity: EntityMetadata, mutation: str, row: Mapping[str, object]
) -> object:
    """The physical shape a buffered row must share with its neighbours before
    they may collapse into one statement — this layer's half of the planner's
    batch grouping (`m-sql` "Physical DML ordering": grouping compares the
    FILTERED, table-ordered slot selections, never the payload mapping).

    The compared selection is the one the EMITTED statement makes, so a member
    the statement never renders never splits a group. An `INSERT`'s value list
    and an `UPDATE`'s `set` clause both render the row's own present members:
    two such rows carrying different members select different columns, and one
    shared statement could only bind the later row's values positionally against
    the first row's column list, so answering their shapes apart keeps them in
    separate runs. A `DELETE` renders its identity predicate alone, so its
    selection is the key columns and its non-key payload members are invisible
    here — two legal deletes always share one `IN`-list statement.

    TOTAL: the planner asks this of every collapse candidate, long before any
    lowering decides the row is renderable at all. A target owning no table, a
    row naming a member its view does not carry, and a delete row omitting a key
    member all answer ``None`` — one undifferentiated group, leaving the loud
    refusal to the builder that would have rendered them.
    """
    view = entity_layout(meta, entity)
    if view is None:
        return None
    ordinals = _member_ordinals(view)
    members: Sequence[str] = (
        [attribute.identity.name for attribute in family_primary_key(meta, entity)]
        if mutation == "delete"
        else list(row)
    )
    selection: list[tuple[int, str]] = []
    for name in members:
        slot = ordinals.get(name)
        if slot is None or name not in row:
            return None
        selection.append((slot[0], slot[1]))
    selection.sort()
    return (mutation, tuple(column for _, column in selection))


def _ordered_cells(
    meta: Metamodel,
    entity: EntityMetadata,
    row: Mapping[str, object],
    *,
    discriminator: bool = False,
) -> list[tuple[str, object]]:
    """The row's present members as `(column, bind)` pairs, in Table Layout order.

    The target's Storage Layout Entity view supplies both the physical column of
    each member and the one order every cell follows, so a row's data order never
    reaches the statement. Each row key names a declared scalar Attribute or a
    top-level Value Object of that view; a value-object member binds as one
    :class:`JsonDocument` at its Document-tier slot (the whole document — the
    write never decomposes it), a scalar binds its value (or its DB-computed
    marker document verbatim, classified by the caller). ``discriminator``
    additionally emits the layout's derived table-per-hierarchy tag value at its
    own Discriminator-tier slot — the one cell a full-row write derives rather
    than reads.
    """
    layout = _layout(meta, entity)
    assignment = layout.discriminator
    ordinals = _member_ordinals(layout)
    discriminator_cell: tuple[int, str, object] | None = None
    if discriminator and assignment is not None:
        for ordinal, slot in enumerate(layout.columns):
            if slot == assignment.slot:
                discriminator_cell = (ordinal, slot.column.name, assignment.value)
    cells: list[tuple[int, str, object]] = []
    for name, value in row.items():
        ordinal, column, is_value_object = ordinals[name]
        cells.append((ordinal, column, JsonDocument(value) if is_value_object else value))
    if discriminator_cell is not None:
        cells.append(discriminator_cell)
    cells.sort(key=lambda cell: cell[0])
    return [(column, bind) for _, column, bind in cells]


def _key_columns(
    layout: EntityLayoutView, meta: Metamodel, entity: EntityMetadata
) -> tuple[tuple[AttributeMetadata, str], ...]:
    """The family-effective primary-key Attributes paired with the physical
    Columns their slots occupy.

    Operation key selection stays semantic (`_family.family_primary_key`); only
    the mapping onto physical Columns comes from the layout, so an update or
    delete predicate keys on the model identity rather than on the Table's own
    physical key.
    """
    return tuple(
        (attribute, slot_column(layout, attribute.identity))
        for attribute in family_primary_key(meta, entity)
    )


def key_predicate(
    meta: Metamodel, entity: EntityMetadata, row: Mapping[str, object], dialect: Dialect
) -> tuple[str, tuple[object, ...]]:
    """The `<pk1> = ? [and <pk2> = ?] [and <tag.column> = ?]` identity predicate
    and its ordered binds — the family-effective primary key, then an
    inheritance-family table-per-hierarchy concrete's own tag guard, joining the
    identity predicates immediately after the pk (`m-inheritance` / `m-sql`) —
    never present for a table-per-concrete-subtype participant or a
    non-participant.
    """
    keys = _key_columns(_layout(meta, entity), meta, entity)
    predicate = " and ".join(f"{dialect.quote(column)} = ?" for _, column in keys)
    binds: tuple[object, ...] = tuple(row[attribute.identity.name] for attribute, _ in keys)
    tag = _tag(meta, entity)
    if tag is not None:
        predicate = f"{predicate} and {dialect.quote(tag[0])} = ?"
        binds = (*binds, tag[1])
    return predicate, binds
