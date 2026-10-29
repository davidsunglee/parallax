from __future__ import annotations

from parallax.core._execution._family import entity_layout, family_view
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.write_plan.managed_row import ManagedRow

__all__ = [
    "collapse_group_key",
]


def collapse_group_key(
    meta: Metamodel, entity: EntityMetadata, mutation: str, row: ManagedRow
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
    here — two legal deletes always share one key-membership statement.

    Every member of one Entity has exactly one placement — a Column of its own,
    or a Document Path in the shared Structured Column — so the members a row
    states, its presence, select its placements exactly, and two rows of one
    Entity answer one shape precisely when they state the same members. An
    opening row states every `many` member, its empty collection included
    (`m-unit-work`'s own canonicalization), so a row that left its zero state
    implicit never answers a different shape from one that wrote `[]`.

    TOTAL: the planner asks this of every collapse candidate, long before any
    lowering decides the row is renderable at all. A target owning no table and
    a delete row omitting its key member answer ``None`` — one undifferentiated
    group, leaving the loud refusal to the builder that would have rendered
    them.
    """
    if entity_layout(meta, entity) is None:
        return None
    if mutation != "delete":
        return (mutation, row.presence)
    key = 1 << row.selection.members.index[family_view(meta, entity).primary_key.identity]
    return (mutation, key) if row.presence & key else None
