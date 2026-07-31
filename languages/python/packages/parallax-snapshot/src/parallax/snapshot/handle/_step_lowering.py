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

from collections.abc import Mapping, Sequence

from parallax.core.base import INFINITY_LITERAL
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import Dialect
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.sql_gen import Statement, compile_write_predicate
from parallax.core.storage_layout import EntityLayoutView
from parallax.core.unit_work.planned import (
    Finite,
    KeyTarget,
    MaxPlusOne,
    MilestoneTarget,
    NonTemporalConcurrency,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedUpdate,
    PlannedWrite,
    PredicateTarget,
    SelfIncrement,
    TemporalConcurrency,
    TemporalGate,
    TemporalUpperBound,
    Versioned,
    VersionGate,
    WriteTarget,
)
from parallax.snapshot.handle._family import declaring, entity_layout, version_attribute
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = ["lower_step"]

# One rendered cell: the physical Column it occupies and the value that lands
# there — a bind, or the generated-value expression the statement folds in.
type _Cell = tuple[str, object]

# One rendered predicate: its SQL text and the binds it contributes, in order.
type _Predicate = tuple[str, tuple[object, ...]]


def lower_step(step: PlannedWrite, meta: Metamodel, dialect: Dialect) -> Statement:
    """Lower one finalized step to its single DML statement."""
    match step:
        case PlannedInsert():
            return _lower_insert(step, meta, dialect)
        case PlannedUpdate():
            return _lower_update(step, meta, dialect)
        case PlannedClose():
            return _lower_close(step, meta, dialect)
        case PlannedDelete():
            return _lower_delete(step, meta, dialect)


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
    rows = [
        _member_cells(view, entry.row.attributes, entry.row.value_objects, entity, stamp_tag=True)
        for entry in step.entries
    ]
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


def _lower_update(step: PlannedUpdate, meta: Metamodel, dialect: Dialect) -> Statement:
    """`update <table> set <assigned columns> = ?, … where <target>[ and <gate>]`.

    The assigned columns follow the Table Layout's slot order, with one
    exception: the optimistic-lock version renders LAST, after every other
    column, because a value-object document occupies the Document tier — after
    every scalar tier, the version's own slot included (`m-value-object` "One
    column") — so threading the advance through slot order would wrongly render
    it before the document. That position is a rendering fact, not a layout one,
    mirroring the version gate's own "binds last" rule one clause family over.
    """
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    assignment_sql, assignment_binds = _assignment_clause(
        view, step.assignments, meta, entity, dialect
    )
    where_sql, where_binds = _target_predicate(view, step.target, entity, meta, dialect)
    gate_sql, gate_binds = _gate(view, step.concurrency, dialect)
    return Statement(
        f"update {view.layout.table.name} set {assignment_sql} where {where_sql}{gate_sql}",
        (*assignment_binds, *where_binds, *gate_binds),
    )


def _lower_close(step: PlannedClose, meta: Metamodel, dialect: Dialect) -> Statement:
    """`update <table> set <axis end> = ? where <milestone target>[ and <gate>]`.

    Physically this is an update whose target happens to be a milestone slot:
    the address renders the key, then the table-per-hierarchy tag guard, then
    one exclusive upper bound per As-Of Axis in canonical order, and only the
    gate follows — binding last, exactly as a version gate does one clause
    family over.
    """
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    assignment_sql, assignment_binds = _assignment_clause(
        view, step.assignments, meta, entity, dialect
    )
    where_sql, where_binds = _target_predicate(view, step.target, entity, meta, dialect)
    gate_sql, gate_binds = _temporal_gate(view, step.concurrency, entity, dialect)
    return Statement(
        f"update {view.layout.table.name} set {assignment_sql} where {where_sql}{gate_sql}",
        (*assignment_binds, *where_binds, *gate_binds),
    )


def _lower_delete(step: PlannedDelete, meta: Metamodel, dialect: Dialect) -> Statement:
    """`delete from <table> where <target>[ and <gate>]`."""
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    where_sql, where_binds = _target_predicate(view, step.target, entity, meta, dialect)
    gate_sql, gate_binds = _gate(view, step.concurrency, dialect)
    return Statement(
        f"delete from {view.layout.table.name} where {where_sql}{gate_sql}",
        (*where_binds, *gate_binds),
    )


def _assignment_clause(
    view: EntityLayoutView,
    assignments: PlannedAssignments,
    meta: Metamodel,
    entity: EntityMetadata,
    dialect: Dialect,
) -> _Predicate:
    version = version_attribute(meta, declaring(meta, entity))
    version_column = None if version is None else _column(view, version.identity, entity)
    cells = _member_cells(
        view,
        assignments.attributes,
        assignments.value_objects,
        entity,
        stamp_tag=False,
    )
    ordered = [cell for cell in cells if cell[0] != version_column]
    ordered.extend(cell for cell in cells if cell[0] == version_column)
    parts = [_assignment(column, value, dialect) for column, value in ordered]
    binds = tuple(_assignment_bind(value) for _, value in ordered)
    return ", ".join(parts), binds


def _assignment(column: str, value: object, dialect: Dialect) -> str:
    quoted = dialect.quote(column)
    if isinstance(value, SelfIncrement):
        return f"{quoted} = {quoted} + ?"
    return f"{quoted} = ?"


def _assignment_bind(value: object) -> object:
    return value.amount if isinstance(value, SelfIncrement) else value


def _target_predicate(
    view: EntityLayoutView,
    target: WriteTarget,
    entity: EntityMetadata,
    meta: Metamodel,
    dialect: Dialect,
) -> _Predicate:
    """The row selection ``target`` names, rendered against this Table Layout.

    A singleton Key Target keys by equality and a multi-key one by an `IN` list —
    two renderings of one selection, chosen by cardinality alone. Either way the
    table-per-hierarchy tag guard follows the key, because every addressed row of
    one step is the same concrete subtype. A Milestone Target adds its axis upper
    bounds after that guard, so the whole address renders before any gate.
    """
    match target:
        case PredicateTarget(predicate):
            compiled = compile_write_predicate(predicate, meta, dialect, entity)
            return compiled.sql, compiled.binds
        case KeyTarget():
            key_sql, key_binds = _key_predicate(view, target, entity, dialect)
            tag_sql, tag_binds = _tag_guard(view, dialect)
            return f"{key_sql}{tag_sql}", (*key_binds, *tag_binds)
        case MilestoneTarget():
            columns = [_column(view, attribute, entity) for attribute in target.key_attributes]
            key_sql = " and ".join(f"{dialect.quote(column)} = ?" for column in columns)
            tag_sql, tag_binds = _tag_guard(view, dialect)
            end_sql, end_binds = _axis_ends(view, target, entity, dialect)
            return (
                f"{key_sql}{tag_sql}{end_sql}",
                (*target.key_values, *tag_binds, *end_binds),
            )


def _axis_ends(
    view: EntityLayoutView, target: MilestoneTarget, entity: EntityMetadata, dialect: Dialect
) -> _Predicate:
    """`` and <axis end> = ?`` per As-Of Axis, in the order the target names them."""
    parts: list[str] = []
    binds: list[object] = []
    for attribute, bound in zip(target.end_attributes, target.end_values, strict=True):
        parts.append(f" and {dialect.quote(_column(view, attribute, entity))} = ?")
        binds.append(_upper_bound_bind(bound))
    return "".join(parts), tuple(binds)


def _upper_bound_bind(bound: TemporalUpperBound) -> object:
    return bound.instant if isinstance(bound, Finite) else INFINITY_LITERAL


def _key_predicate(
    view: EntityLayoutView, target: KeyTarget, entity: EntityMetadata, dialect: Dialect
) -> _Predicate:
    columns = [_column(view, attribute, entity) for attribute in target.key_attributes]
    if len(target.key_values) == 1:
        predicate = " and ".join(f"{dialect.quote(column)} = ?" for column in columns)
        return predicate, target.key_values[0]
    if len(columns) == 1:
        holes = ", ".join("?" for _ in target.key_values)
        binds = tuple(values[0] for values in target.key_values)
        return f"{dialect.quote(columns[0])} in ({holes})", binds
    keys_sql = f"({', '.join(dialect.quote(column) for column in columns)})"
    row_hole = f"({', '.join('?' for _ in columns)})"
    holes = ", ".join(row_hole for _ in target.key_values)
    binds = tuple(value for values in target.key_values for value in values)
    return f"{keys_sql} in ({holes})", binds


def _tag_guard(view: EntityLayoutView, dialect: Dialect) -> _Predicate:
    """`` and <tag.column> = ?`` plus its bind for a table-per-hierarchy concrete,
    else nothing — the guard joins the identity predicates immediately after the
    key (`m-inheritance` / `m-sql`)."""
    discriminator = view.discriminator
    if discriminator is None:
        return "", ()
    return f" and {dialect.quote(discriminator.slot.column.name)} = ?", (discriminator.value,)


def _gate(
    view: EntityLayoutView, concurrency: NonTemporalConcurrency, dialect: Dialect
) -> _Predicate:
    """`` and <version> = ?`` for a gated step, else nothing.

    The gate binds LAST, no exception (`m-opt-lock` "the version gate binds
    last"). Whether one exists at all was decided during planning, so nothing
    here consults a mode.
    """
    if not isinstance(concurrency, Versioned) or not isinstance(concurrency.gate, VersionGate):
        return "", ()
    gate = concurrency.gate
    slot = view.layout.contribution(gate.attribute)
    if slot is None:  # pragma: no cover - a gate names the target's own version Attribute
        raise WriteLoweringError(
            f"{view.entity.canonical}: the version gate's Attribute occupies no Column"
        )
    return f" and {dialect.quote(slot.column.name)} = ?", (gate.observed_version,)


def _temporal_gate(
    view: EntityLayoutView,
    concurrency: TemporalConcurrency,
    entity: EntityMetadata,
    dialect: Dialect,
) -> _Predicate:
    """`` and <axis start> = ?`` for a gated close, else nothing.

    The gate binds LAST, after the whole address — the same absolute rule a
    version gate follows, with no inheritance exception for the tag guard the
    address already rendered.
    """
    if not isinstance(concurrency, TemporalGate):
        return "", ()
    column = _column(view, concurrency.start_attribute, entity)
    return f" and {dialect.quote(column)} = ?", (concurrency.observed_start,)


def _member_cells(
    view: EntityLayoutView,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
    entity: EntityMetadata,
    *,
    stamp_tag: bool,
) -> Sequence[_Cell]:
    """The named members as ``(column, value)`` pairs, in Table Layout slot order.

    The view supplies both the physical Column each member identity occupies and
    the one order every cell follows, so a caller's own member order never reaches
    the statement. A Value Object occurrence binds as one
    :class:`~parallax.core.db_port.JsonDocument` at its Document-tier slot — the
    whole document, never decomposed.

    ``stamp_tag`` additionally emits the table-per-hierarchy discriminator at its
    own slot. An opening row writes it because the row's concrete subtype is being
    established; a revising statement leaves it alone, since revising a row never
    changes what it is.
    """
    discriminator = view.discriminator if stamp_tag else None
    cells: list[_Cell] = []
    matched = 0
    for slot in view.columns:
        contributor = slot.contributor
        if discriminator is not None and slot == discriminator.slot:
            cells.append((slot.column.name, discriminator.value))
        elif isinstance(contributor, AttributeIdentity) and contributor in attributes:
            cells.append((slot.column.name, attributes[contributor]))
            matched += 1
        elif isinstance(contributor, ValueObjectIdentity) and contributor in value_objects:
            cells.append((slot.column.name, JsonDocument(value_objects[contributor])))
            matched += 1
    _require_placed(matched, len(attributes) + len(value_objects), entity)
    return cells


def _require_placed(matched: int, named: int, entity: EntityMetadata) -> None:
    if matched != named:  # pragma: no cover - finalization resolves against this view
        raise WriteLoweringError(
            f"{entity.identity.name!r}: a planned member occupies no Column of the target's "
            "Table Layout"
        )


def _column(view: EntityLayoutView, attribute: AttributeIdentity, entity: EntityMetadata) -> str:
    slot = view.layout.contribution(attribute)
    if slot is None:  # pragma: no cover - a planned Attribute always occupies a Column
        raise WriteLoweringError(
            f"{entity.identity.name!r}: {attribute.name!r} occupies no Column of the target's "
            "Table Layout"
        )
    return slot.column.name


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
