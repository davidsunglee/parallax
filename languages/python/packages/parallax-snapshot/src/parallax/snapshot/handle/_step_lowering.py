"""``parallax.snapshot.handle._step_lowering`` — one settled step, one statement.

:func:`lower_step` answers the single PHYSICAL question a finalized
:class:`~parallax.core.unit_work.PlannedWrite` leaves open: how one storage
layout and one dialect express it. It reads the target's Storage Layout Entity
view for column participation and order, derives the table-per-hierarchy tag at
its own slot, quotes through the dialect, and orders binds — and it reads no
concurrency mode, observation, Transaction Instant, or temporal topology,
because a step arrives with all of those already decided.

It sits beside :mod:`parallax.snapshot.handle._keyed_sql` rather than inside it:
that module renders an instruction whose semantics are still being decided as it
goes, while everything here renders a step that carries no undecided fact.
"""

from __future__ import annotations

from collections.abc import Sequence

from parallax.core.db_port import JsonDocument
from parallax.core.dialect import Dialect
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.sql_gen import Statement
from parallax.core.storage_layout import EntityLayoutView
from parallax.core.unit_work.planned import MaxPlusOne, PlannedInsert, PlannedRow, PlannedWrite
from parallax.snapshot.handle._family import entity_layout
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = ["lower_step"]

# One rendered cell: the physical Column it occupies and the value that lands
# there — a bind, or the generated-value expression the statement folds in.
type _Cell = tuple[str, object]


def lower_step(step: PlannedWrite, meta: Metamodel, dialect: Dialect) -> Statement:
    """Lower one finalized step to its single DML statement."""
    match step:
        case PlannedInsert():
            return _lower_insert(step, meta, dialect)


def _lower_insert(step: PlannedInsert, meta: Metamodel, dialect: Dialect) -> Statement:
    """`insert into <table>(<participating columns in Table Layout order>) values
    (?, …)[, (?, …)…]`, or the pk-gen `max` INSERT…SELECT form when a cell
    carries a generated-value expression.

    Only the columns the step's entries name are emitted — an entry omitting a
    nullable member produces a narrower `INSERT`, never an explicit `NULL` bind
    — and every entry renders one value tuple against that one shared column
    list, in entry order. The table-per-hierarchy tag is derived from the
    layout's own discriminator assignment at its own slot; no entry ever names
    it.
    """
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    rows = [_cells(view, entry.row, entity) for entry in step.entries]
    columns = ", ".join(dialect.quote(column) for column, _ in rows[0])
    table = view.layout.table.name
    if not any(isinstance(value, MaxPlusOne) for _, value in rows[0]):
        binds = tuple(value for row in rows for _, value in row)
        tuples = ", ".join(f"({', '.join('?' for _ in row)})" for row in rows)
        return Statement(f"insert into {table}({columns}) values {tuples}", binds)
    if len(rows) > 1:
        raise WriteLoweringError(
            f"multi-entry insert on {entity.identity.name!r}: a generated-value expression "
            "folds into the statement itself, so it renders one row at a time (m-pk-gen)"
        )
    select_parts: list[str] = []
    select_binds: list[object] = []
    for column, value in rows[0]:
        if isinstance(value, MaxPlusOne):
            select_parts.append(f"coalesce(max(t0.{dialect.quote(column)}), ?) + ?")
            select_binds.extend([0, 1])
        else:
            select_parts.append("?")
            select_binds.append(value)
    return Statement(
        f"insert into {table}({columns}) select {', '.join(select_parts)} from {table} t0",
        tuple(select_binds),
    )


def _cells(view: EntityLayoutView, row: PlannedRow, entity: EntityMetadata) -> Sequence[_Cell]:
    """``row``'s members as ``(column, value)`` pairs, in Table Layout slot order.

    The view supplies both the physical Column each member identity occupies and
    the one order every cell follows, so a row's own member order never reaches
    the statement. A Value Object occurrence binds as one
    :class:`~parallax.core.db_port.JsonDocument` at its Document-tier slot — the
    whole document, never decomposed.
    """
    discriminator = view.discriminator
    cells: list[_Cell] = []
    matched = 0
    for slot in view.columns:
        contributor = slot.contributor
        if discriminator is not None and slot == discriminator.slot:
            cells.append((slot.column.name, discriminator.value))
        elif isinstance(contributor, AttributeIdentity) and contributor in row.attributes:
            cells.append((slot.column.name, row.attributes[contributor]))
            matched += 1
        elif isinstance(contributor, ValueObjectIdentity) and contributor in row.value_objects:
            cells.append((slot.column.name, JsonDocument(row.value_objects[contributor])))
            matched += 1
    if matched != len(row.members):  # pragma: no cover - finalization resolves against this view
        raise WriteLoweringError(
            f"{entity.identity.name!r}: a planned member occupies no Column of the target's "
            "Table Layout"
        )
    return cells


def _entity(meta: Metamodel, identity: EntityIdentity) -> EntityMetadata:
    entity = meta.entity(identity)
    if entity is None:  # pragma: no cover - a planned step always names an accepted Entity
        raise WriteLoweringError(f"{identity.canonical!r}: step target is not an accepted Entity")
    return entity


def _layout(meta: Metamodel, entity: EntityMetadata) -> EntityLayoutView:
    view = entity_layout(meta, entity)
    if view is None:
        raise WriteLoweringError(f"{entity.identity.name!r}: write target has no effective table")
    return view
