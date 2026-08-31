"""``parallax.snapshot.handle._keyed_sql`` — physical-shape batch grouping.

Every write family now finalizes into a settled step before lowering
(:class:`~parallax.core.unit_work.WritePlanner`) and renders through
:func:`parallax.core.sql_gen._write.compile_write_step` from that already-decided step.
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

from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.storage_layout import DocumentPath, EntityLayoutView, MemberPlacement
from parallax.snapshot.handle._family import entity_layout, family_primary_key, placed_members

__all__ = [
    "collapse_group_key",
]

# Where one member's value lands in a rendered statement: the slot's ordinal in
# Table order, the physical Column, and the Document Path inside it — empty for a
# member holding a Column of its own.
type _MemberAddress = tuple[int, str, tuple[str, ...]]


def _member_addresses(
    meta: Metamodel, entity: EntityMetadata, layout: EntityLayoutView
) -> dict[str, _MemberAddress]:
    """Each member name this Entity writes, mapped to where its Table puts it.

    Answered from Member Placement rather than from the Table's slots, because a
    document-resident member claims no slot of its own: several members share one
    Structured Column and are told apart by their Document Paths, which is exactly
    the distinction a collapse decision needs — under this layout the column list
    alone no longer separates two rows that name different members.

    The framework-owned discriminator is no member and is absent: no write input
    ever names it, and every form that emits it derives it from the view's own
    assignment instead.
    """
    ordinals = {slot.column.name: ordinal for ordinal, slot in enumerate(layout.layout.columns)}
    placed = placed_members(meta, entity, layout)
    named: list[tuple[str, MemberPlacement]] = [
        (attribute.identity.name, placement) for attribute, placement in placed.attributes
    ]
    named.extend(
        (occurrence.identity.path[-1], placement) for occurrence, placement in placed.value_objects
    )
    addresses: dict[str, _MemberAddress] = {}
    for name, placement in named:
        column = placement.slot.column.name
        path = placement.path if isinstance(placement, DocumentPath) else ()
        addresses[name] = (ordinals[column], column, path)
    return addresses


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

    ``row`` is a CANONICAL write row, which for an opening mutation means one whose
    `many` Value Object occurrences are spelled out whether the caller named them or
    not — `m-unit-work`'s own canonicalization, since absence and the empty array are
    one logical zero state. So a row that left its zero state implicit never answers
    a different shape from an otherwise identical one that wrote `[]`, which is what
    `m-sql` means by grouping the caller-present and framework-derived cells alike
    ("Physical DML ordering").

    Under Relational Document Layout the selection is Column *and* Document Path,
    because several members share one Structured Column. Two rows naming different
    document members do emit the same column list — an `INSERT` binds the whole
    document at that one `NOT NULL` Column whatever the row names — so the paths
    are what still tells their shapes apart, and they must: every entry of one
    Planned Insert has the same canonical member set, and incompatible entries form
    separate steps (`m-unit-work`, "Membership *is* the batching decision"). Under
    `Columns` layout the column list already carries that distinction; here the
    Document Path is what carries it, and dropping it would hand the planner a run
    it refuses rather than a wider batch.

    TOTAL: the planner asks this of every collapse candidate, long before any
    lowering decides the row is renderable at all. A target owning no table, a
    row naming a member its view does not carry, and a delete row omitting a key
    member all answer ``None`` — one undifferentiated group, leaving the loud
    refusal to the builder that would have rendered them.
    """
    view = entity_layout(meta, entity)
    if view is None:
        return None
    addresses = _member_addresses(meta, entity, view)
    members: Sequence[str] = (
        [attribute.identity.name for attribute in family_primary_key(meta, entity)]
        if mutation == "delete"
        else list(row)
    )
    selection: list[_MemberAddress] = []
    for name in members:
        address = addresses.get(name)
        if address is None or name not in row:
            return None
        selection.append(address)
    selection.sort()
    return (mutation, tuple((column, path) for _ordinal, column, path in selection))
