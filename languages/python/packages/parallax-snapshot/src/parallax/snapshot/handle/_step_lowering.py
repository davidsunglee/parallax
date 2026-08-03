"""``parallax.snapshot.handle._step_lowering`` — one settled step, one statement.

:func:`lower_step` answers the single PHYSICAL question a finalized
:class:`~parallax.core.unit_work.PlannedWrite` leaves open: how one storage
layout and one dialect express it. It reads the target's Storage Layout Entity
view for column participation and order, derives the table-per-hierarchy tag at
its own slot, quotes through the dialect, and orders binds — and it consults no
concurrency mode, no unit of work, no Transaction Instant, and no temporal
topology, because a step arrives with all of those already decided.

The one thing a step carries that lowering still has to READ is what an insert
entry's Insert Origin retains: the milestone that entry succeeds, whose own raw
Structured Column document a successor is patched from (`m-unit-work`). That is
state the plan settled rather than a decision left open — the origin says which
milestone, and this module only spells what the row now holds.

It sits beside :mod:`parallax.snapshot.handle._keyed_sql` rather than inside it:
that module renders an instruction whose semantics are still being decided as it
goes, while everything here renders a step that carries no undecided fact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core.base import INFINITY_LITERAL, NeutralType, decode_neutral_literal
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import (
    Dialect,
    DocumentAssignment,
    DocumentLeafAssignment,
    DocumentManyAssignment,
    DocumentOneAssignment,
)
from parallax.core.document_codec import (
    NULL,
    DocumentPatch,
    DocumentShape,
    Leaf,
    Presence,
    Present,
    SetLeaf,
    SetMany,
    SetOccurrence,
    apply_patches,
    encode_document,
    encode_leaf,
    encode_many,
    entity_shape,
    occurrence_shape,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.sql_gen import Statement, compile_write_predicate
from parallax.core.storage_layout import DocumentPath, EntityLayoutView, RelationalDocument
from parallax.core.unit_work import PredecessorRow
from parallax.core.unit_work.planned import (
    Finite,
    InsertOrigin,
    KeyTarget,
    MaxPlusOne,
    MilestoneTarget,
    NewLineage,
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
from parallax.snapshot.handle._family import (
    PlacedMembers,
    declaring,
    entity_layout,
    placed_members,
    version_attribute,
)
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = ["lower_step"]


@dataclass(frozen=True, slots=True)
class _DocumentAssignments:
    """The ordered mutation trees for one revising statement's Structured Column.

    A revising statement PATCHES rather than replaces (`m-storage-layout`): leaf
    and ``many`` entries assign encoded values, while ``one`` entries recursively
    guard and patch nested occurrences. The sequence is canonical logical
    placement order, which both dialects apply left to right (`m-dialect`).
    """

    assignments: tuple[DocumentAssignment, ...]


# One rendered cell: the physical Column it occupies and the value that lands
# there — a bind, the ordered path assignments a Structured Column takes, or the
# generated-value expression the statement folds in.
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

    Under Relational Document Layout every document-resident member the entry
    names collapses into the one shared Structured Column cell, which each entry
    binds whether or not it names any: the Column is `NOT NULL` and every governed
    row carries a document, the empty object included (`m-storage-layout`).

    An entry whose Insert Origin carries a predecessor — a temporal successor —
    composes that cell from the predecessor's own retained document instead
    (:func:`_successor_document`), so the entries of one step may bind different
    documents while naming the same members.
    """
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    placed = placed_members(meta, entity, view)
    rows = [
        _member_cells(
            view,
            placed,
            entry.row.attributes,
            entry.row.value_objects,
            entity,
            stamp_tag=True,
            opening=True,
            predecessor=_origin_predecessor(entry.origin),
        )
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
        placed_members(meta, entity, view),
        assignments.attributes,
        assignments.value_objects,
        entity,
        stamp_tag=False,
        opening=False,
    )
    ordered = [cell for cell in cells if cell[0] != version_column]
    ordered.extend(cell for cell in cells if cell[0] == version_column)
    parts: list[str] = []
    binds: list[object] = []
    for column, value in ordered:
        part, cell_binds = _assignment(column, value, dialect)
        parts.append(part)
        binds.extend(cell_binds)
    return ", ".join(parts), tuple(binds)


def _assignment(column: str, value: object, dialect: Dialect) -> tuple[str, Sequence[object]]:
    """One `set` term and the binds it contributes, in rendered order.

    Three forms, each decided by what the planner settled rather than by the
    value's shape: the registry advance self-references its own Column, a
    Structured Column takes the dialect's document mutation expression over the
    paths this step assigns, and every other Column takes one bind.
    """
    quoted = dialect.quote(column)
    if isinstance(value, SelfIncrement):
        return f"{quoted} = {quoted} + ?", (value.amount,)
    if isinstance(value, _DocumentAssignments):
        expression, mutation_binds = dialect.document_mutation(quoted, value.assignments)
        return f"{quoted} = {expression}", _document_binds(mutation_binds)
    return f"{quoted} = ?", (value,)


def _document_binds(binds: Sequence[object]) -> tuple[object, ...]:
    """The document mutation expression's binds as managed carriers.

    The dialect decides each assigned value's SQL-level form — the document
    itself for a composite, its JSON text for a scalar (`m-dialect`) — and names
    no Database Port, so wrapping a composite in the neutral `m-db-port` carrier
    the adapter hands to its driver's structured-document bind happens here,
    exactly as it does for a whole-document cell one clause family over.
    """
    return tuple(
        JsonDocument(cast("object", bind)) if isinstance(bind, (dict, list)) else bind
        for bind in binds
    )


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
    placed: PlacedMembers,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
    entity: EntityMetadata,
    *,
    stamp_tag: bool,
    opening: bool,
    predecessor: PredecessorRow | None = None,
) -> Sequence[_Cell]:
    """The named members as ``(column, value)`` pairs, in Table Layout slot order.

    The view supplies both the physical Column each member occupies and the one
    order every cell follows, so a caller's own member order never reaches the
    statement. A Value Object occurrence with a Column of its own binds as one
    :class:`~parallax.core.db_port.JsonDocument` there — the whole document,
    never decomposed — and every document-resident member instead collapses into
    the Table's one shared Structured Column, whose cell an ``opening`` statement
    fills with the row's complete document and a revising one with the ordered
    path assignments it patches.

    An ``opening`` statement binds a `many` occurrence's Column whether or not
    the row names it: absence and the empty array are one logical zero state, so
    an unnamed `many` stores ``[]`` (`m-value-object`), which is the same answer
    the codec composes for one inside a document. A revising statement leaves an
    unnamed occurrence alone, because patching touches only what it assigns.

    ``stamp_tag`` additionally emits the table-per-hierarchy discriminator at its
    own slot. An opening row writes it because the row's concrete subtype is being
    established; a revising statement leaves it alone, since revising a row never
    changes what it is.

    ``predecessor`` is the milestone an opening row succeeds, which decides how its
    Structured Column is composed: from the retained document it observed, or from
    the row's own members alone (:func:`_successor_document`).
    """
    discriminator = view.discriminator if stamp_tag else None
    cells: list[_Cell] = []
    matched = 0
    for slot in view.columns:
        contributor = slot.contributor
        if discriminator is not None and slot == discriminator.slot:
            cells.append((slot.column.name, discriminator.value))
        elif isinstance(contributor, RelationalDocument):
            resident = _resident_members(placed, slot.column.name)
            if opening:
                cells.append(
                    (
                        slot.column.name,
                        JsonDocument(
                            _successor_document(resident, attributes, value_objects, predecessor)
                        ),
                    )
                )
            else:
                patches = _patches(resident, attributes, value_objects)
                if patches:
                    cells.append((slot.column.name, _DocumentAssignments(patches)))
            matched += _resident_count(resident, attributes, value_objects)
        elif isinstance(contributor, AttributeIdentity) and contributor in attributes:
            cells.append((slot.column.name, attributes[contributor]))
            matched += 1
        elif isinstance(contributor, ValueObjectIdentity):
            occurrence = _occurrence_of(placed, contributor)
            if contributor in value_objects:
                value = value_objects[contributor]
                document = None if value is None else _occurrence_document(occurrence, value)
                cells.append((slot.column.name, JsonDocument(document)))
                matched += 1
            elif opening and occurrence.multiplicity is Multiplicity.MANY:
                cells.append((slot.column.name, JsonDocument(_occurrence_document(occurrence, ()))))
    _require_placed(matched, len(attributes) + len(value_objects), entity)
    return cells


@dataclass(frozen=True, slots=True)
class _ResidentMembers:
    """The members one Structured Column's document carries, canonical order."""

    attributes: tuple[tuple[AttributeMetadata, tuple[str, ...]], ...]
    value_objects: tuple[tuple[ValueObjectMetadata, tuple[str, ...]], ...]


def _resident_members(placed: PlacedMembers, column: str) -> _ResidentMembers:
    return _ResidentMembers(
        tuple(
            (attribute, placement.path)
            for attribute, placement in placed.attributes
            if isinstance(placement, DocumentPath) and placement.slot.column.name == column
        ),
        tuple(
            (occurrence, placement.path)
            for occurrence, placement in placed.value_objects
            if isinstance(placement, DocumentPath) and placement.slot.column.name == column
        ),
    )


def _resident_count(
    resident: _ResidentMembers,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> int:
    """How many of this step's named members the Structured Column accounts for."""
    return sum(attribute.identity in attributes for attribute, _path in resident.attributes) + sum(
        occurrence.identity in value_objects for occurrence, _path in resident.value_objects
    )


def _row_document(
    resident: _ResidentMembers,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> object:
    """One opening row's complete Structured Column document.

    Composed through the codec against the shape of every APPLICABLE
    document-resident member rather than only the named ones, so presence
    classification stays the codec's: a member the row omits is absent, one the
    row sets to ``None`` is JSON null, and a `many` occurrence always contributes
    its array even where the row never mentions it (`m-document-codec`).
    """
    shape = entity_shape(
        tuple(attribute for attribute, _path in resident.attributes),
        tuple(occurrence for occurrence, _path in resident.value_objects),
    )
    values: dict[str, Presence] = {}
    for attribute, _path in resident.attributes:
        if attribute.identity in attributes:
            raw = attributes[attribute.identity]
            values[attribute.identity.name] = (
                NULL if raw is None else Present(decode_neutral_literal(raw, attribute.type))
            )
    for occurrence, _path in resident.value_objects:
        if occurrence.identity in value_objects:
            raw = value_objects[occurrence.identity]
            values[occurrence.identity.path[-1]] = (
                NULL if raw is None else Present(_occurrence_document(occurrence, raw))
            )
    return encode_document(shape, values)


def _origin_predecessor(origin: InsertOrigin) -> PredecessorRow | None:
    """The milestone one insert entry succeeds, or absence for a new lineage."""
    return None if isinstance(origin, NewLineage) else origin.predecessor


def _successor_document(
    resident: _ResidentMembers,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
    predecessor: PredecessorRow | None,
) -> object:
    """One opening row's Structured Column, given the milestone it succeeds.

    A row that succeeds a milestone whose observation retained the predecessor's
    raw document is composed by PATCHING that document, so every key it carries
    survives the close-and-insert — a key a newer application version wrote
    included (`m-document-codec`, `m-unit-work`). Only the members whose value the
    mutation actually changed are patched: a member the successor carries forward
    is already spelled in the retained document, and re-encoding it from its
    decoded value would rebuild the subtree an occurrence holds and drop the
    unknown keys inside it.

    Without a retained document there is nothing to preserve — a new lineage opens
    no predecessor, and an observation that read no row knows no key this model
    does not declare — so the row's own complete member set composes the document
    (:func:`_row_document`).
    """
    if predecessor is None or predecessor.document is None:
        return _row_document(resident, attributes, value_objects)
    patches = _successor_patches(resident, attributes, value_objects, predecessor)
    if not patches:
        return predecessor.document
    shape = entity_shape(
        tuple(attribute for attribute, _path in resident.attributes),
        tuple(occurrence for occurrence, _path in resident.value_objects),
    )
    return apply_patches(shape, predecessor.document, patches)


def _successor_patches(
    resident: _ResidentMembers,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
    predecessor: PredecessorRow,
) -> tuple[DocumentPatch, ...]:
    """The in-memory patches carrying one successor's changes onto its predecessor.

    A successor's row restates every member, changed or not (`m-unit-work`), and
    its carried half is copied straight out of the observation's own member map —
    so comparing each member against that same map is what tells a carried member
    from a changed one. The comparison is deliberately against the observation
    rather than against the retained document: the map is the row's own
    provenance, while the document is a value the observation's two paths spell
    differently (a materialized occurrence carries the declared members decoded by
    type, the stored subtree carries every key as written), and a carried
    occurrence misread as changed would be rebuilt from declared members and drop
    every key no member names.

    Order is canonical logical placement order, which both the in-memory patch and
    the equivalent path-patched `UPDATE` apply left to right (`m-storage-layout`).
    """
    patches: list[DocumentPatch] = []
    for attribute, path in resident.attributes:
        name = attribute.identity.name
        if attribute.identity not in attributes or attributes[attribute.identity] == (
            predecessor.members.get(name)
        ):
            continue
        raw = attributes[attribute.identity]
        patches.append(
            SetLeaf(
                path, NULL if raw is None else Present(decode_neutral_literal(raw, attribute.type))
            )
        )
    for occurrence, path in resident.value_objects:
        name = occurrence.identity.path[-1]
        if occurrence.identity not in value_objects or value_objects[occurrence.identity] == (
            predecessor.members.get(name)
        ):
            continue
        raw = value_objects[occurrence.identity]
        if occurrence.multiplicity is Multiplicity.MANY:
            patches.append(SetMany(path, _occurrence_document(occurrence, raw)))
        else:
            patches.append(
                SetOccurrence(path, None if raw is None else _occurrence_document(occurrence, raw))
            )
    return tuple(patches)


def _patches(
    resident: _ResidentMembers,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object],
) -> tuple[DocumentAssignment, ...]:
    """The ordered path assignments a revising statement applies.

    A revising statement patches only the paths it assigns, so every key it does
    not name survives — a model member the step left alone and a key a newer
    application version wrote alike (`m-storage-layout`). An assigned ``None``
    writes JSON null rather than removing the key, which is the one not-present
    state a NULL Column also has. A ``one`` recursively patches only named declared
    members, while a ``many`` replaces its ordered array whole.
    """
    patches: list[DocumentAssignment] = []
    for attribute, path in resident.attributes:
        if attribute.identity in attributes:
            raw = attributes[attribute.identity]
            patches.append(
                DocumentLeafAssignment(path, None if raw is None else _leaf(attribute.type, raw))
            )
    for occurrence, path in resident.value_objects:
        if occurrence.identity in value_objects:
            raw = value_objects[occurrence.identity]
            patches.append(_occurrence_assignment(occurrence, path, raw))
    return tuple(patches)


def _occurrence_assignment(
    occurrence: ValueObjectMetadata, path: tuple[str, ...], raw: object
) -> DocumentAssignment:
    if occurrence.multiplicity is Multiplicity.MANY:
        return DocumentManyAssignment(path, _occurrence_document(occurrence, raw))
    if raw is None:
        return DocumentOneAssignment(path, None)
    shape = occurrence_shape(occurrence)
    return DocumentOneAssignment(path, _element_assignments(shape, raw))


def _element_assignments(shape: DocumentShape, value: object) -> tuple[DocumentAssignment, ...]:
    raw: Mapping[str, object] = (
        cast("Mapping[str, object]", value)
        if isinstance(value, Mapping)
        else cast("Mapping[str, object]", {})
    )
    assignments: list[DocumentAssignment] = []
    for member in shape.members:
        if member.name not in raw:
            continue
        nested = raw[member.name]
        path = (member.name,)
        if isinstance(member, Leaf):
            assignments.append(
                DocumentLeafAssignment(path, None if nested is None else _leaf(member.type, nested))
            )
        elif member.multiplicity is Multiplicity.MANY:
            elements = cast("Sequence[object]", nested)
            assignments.append(
                DocumentManyAssignment(
                    path,
                    encode_many(
                        member.shape,
                        [_element_presences(member.shape, element) for element in elements],
                    ),
                )
            )
        else:
            assignments.append(
                DocumentOneAssignment(
                    path, None if nested is None else _element_assignments(member.shape, nested)
                )
            )
    return tuple(assignments)


def _occurrence_of(placed: PlacedMembers, identity: ValueObjectIdentity) -> ValueObjectMetadata:
    for occurrence, _placement in placed.value_objects:
        if occurrence.identity == identity:
            return occurrence
    raise WriteLoweringError(  # pragma: no cover - a slot's contributor is always placed
        f"{identity.path[-1]!r}: the occurrence occupying a Column is not an applicable member"
    )


def _occurrence_document(occurrence: ValueObjectMetadata, value: object) -> object:
    """One Value Object occurrence's document, spelled by the codec.

    The write input carries each leaf in whatever portable spelling it was
    authored or built in; the codec owns the ONE spelling stored, so the value
    the statement binds is composed here rather than handed to a serializer as it
    arrived. That is what gives a ``decimal``, ``bytes``, ``date``, ``time``,
    ``timestamp``, or ``uuid`` leaf inside an occurrence its storage form on the
    write lane, and it is idempotent over an already-encoded document because
    every decode leg is the encode leg's inverse (`m-document-codec`).
    """
    shape = occurrence_shape(occurrence)
    if occurrence.multiplicity is Multiplicity.MANY:
        elements = cast("Sequence[object]", value)
        return encode_many(shape, [_element_presences(shape, element) for element in elements])
    return encode_document(shape, _element_presences(shape, value))


def _element_presences(shape: DocumentShape, value: object) -> dict[str, Presence]:
    """One document's members as presences, keyed by canonical name.

    A key the input omits contributes no entry, so the codec classifies it
    ``Missing``; an authored ``None`` is an explicit null. A nested occurrence
    composes through the codec in turn, so nothing here assembles a JSON object
    or array of its own.
    """
    raw: Mapping[str, object] = (
        cast("Mapping[str, object]", value) if isinstance(value, Mapping) else {}
    )
    presences: dict[str, Presence] = {}
    for member in shape.members:
        if member.name not in raw:
            continue
        nested = raw[member.name]
        if nested is None:
            presences[member.name] = NULL
        elif isinstance(member, Leaf):
            presences[member.name] = Present(decode_neutral_literal(nested, member.type))
        elif member.multiplicity is Multiplicity.MANY:
            elements = cast("Sequence[object]", nested)
            presences[member.name] = Present(
                encode_many(
                    member.shape,
                    [_element_presences(member.shape, element) for element in elements],
                )
            )
        else:
            presences[member.name] = Present(
                encode_document(member.shape, _element_presences(member.shape, nested))
            )
    return presences


def _leaf(neutral_type: NeutralType, value: object) -> object:
    """One leaf's document spelling, from whatever carrier it arrived in."""
    return encode_leaf(neutral_type, decode_neutral_literal(value, neutral_type))


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
