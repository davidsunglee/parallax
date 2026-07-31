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

from parallax.core.metamodel import (
    AttributeIdentity,
    EntityMetadata,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.storage_layout import ColumnContributor, EntityLayoutView
from parallax.snapshot.handle._family import entity_layout, family_primary_key

__all__ = [
    "collapse_group_key",
]


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
