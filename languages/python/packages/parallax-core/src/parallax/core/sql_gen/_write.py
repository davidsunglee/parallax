from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Final, cast
from weakref import WeakKeyDictionary

from parallax.core import inheritance, storage_layout
from parallax.core.base import INFINITY, INFINITY_LITERAL, FrozenMap, NeutralType
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import (
    Dialect,
    DocumentAssignment,
    DocumentLeafAssignment,
    DocumentValueAssignment,
)
from parallax.core.document_codec import PreparedPatch
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
)
from parallax.core.sql_gen._compile import compile_write_predicate
from parallax.core.sql_gen._context import (
    LoweredStatement,
    SqlGenError,
    StatementBuilder,
)
from parallax.core.storage_layout import (
    ColumnContributor,
    EntityLayoutView,
    InheritanceDiscriminator,
    StorageLayoutFacet,
)
from parallax.core.wire import WireValue
from parallax.core.write_plan.payload import (
    AssignmentPayload,
    PatchedDocument,
    RowPayload,
)
from parallax.core.write_plan.steps import (
    Finite,
    KeyTarget,
    MaxPlusOne,
    MilestoneTarget,
    NonTemporalConcurrency,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    PlannedWrite,
    SelfIncrement,
    TemporalConcurrency,
    TemporalGate,
    ValidatedMutationSelection,
    Versioned,
    VersionGate,
    WriteTarget,
)

__all__ = ["StepPayload", "compile_write_step"]

type StepPayload = tuple[RowPayload, ...] | AssignmentPayload | None
"""The prepared values one step's statement stores: one Row Payload per insert
entry, in entry order, the Assignment Payload a revising step writes, or
nothing for a step that stores no represented value."""


@dataclass(frozen=True, slots=True)
class _DocumentAssignments:
    """The ordered path assignments for one revising statement's Structured Column.

    A revising statement never rewrites the Column whole (`m-storage-layout`): it
    assigns one complete encoded value per path the step names, and every other
    key of the document stands. The sequence is canonical logical placement order,
    which both dialects apply left to right (`m-dialect`).
    """

    assignments: tuple[DocumentAssignment, ...]
    leaf_types: tuple[NeutralType | None, ...]


# One rendered cell: the physical Column it occupies and the value that lands
# there — a bind, the ordered path assignments a Structured Column takes, or the
# generated-value expression the statement folds in.
type _Cell = tuple[str, object, NeutralType | None]


def _ctx(meta: Metamodel, dialect: Dialect) -> StatementBuilder:
    return StatementBuilder(meta, inheritance.view(meta), storage_layout.view(meta), dialect)


def _bind(ctx: StatementBuilder, value: object, neutral_type: NeutralType | None = None) -> None:
    if value is INFINITY:
        ctx.bind_framework(value)
    elif neutral_type is not None and value is not None:
        ctx.bind_managed(value, neutral_type)
    elif isinstance(value, JsonDocument):
        ctx.bind_document(value)
    else:
        ctx.bind_structural(value)


def _attribute(meta: Metamodel, identity: AttributeIdentity) -> AttributeMetadata:
    entity = meta.entity(identity.entity)
    attribute = None if entity is None else entity.attribute(identity.name)
    if attribute is None:  # pragma: no cover - planned identities come from accepted metadata
        raise SqlGenError(
            f"{identity.entity.canonical}.{identity.name}: planned Attribute is not "
            "accepted metadata"
        )
    return attribute


def entity_layout(meta: Metamodel, entity: EntityMetadata) -> EntityLayoutView | None:
    return storage_layout.view(meta).entity(entity.identity)


def compile_write_step(
    step: PlannedWrite, payload: StepPayload, meta: Metamodel, dialect: Dialect
) -> LoweredStatement:
    """Lower one finalized step to its single DML statement, storing exactly the
    values ``payload`` prepared for it.

    Lowering places, renders, and binds; it never assembles a payload itself. A
    payload prepared from other inputs than the step's own, or a missing one, is
    a broken caller contract rather than a request to prepare one here.
    """
    match step:
        case PlannedInsert():
            return _lower_insert(step, _row_payloads(step, payload), meta, dialect)
        case PlannedUpdate():
            return _lower_update(step, _assignment_payload(step, payload), meta, dialect)
        case PlannedClose() | PlannedTemporalRevision():
            return _lower_milestone_update(step, _assignment_payload(step, payload), meta, dialect)
        case PlannedDelete():
            _require_no_payload(step, payload)
            return _lower_delete(step, meta, dialect)
        case PlannedTemporalRemoval():
            _require_no_payload(step, payload)
            return _lower_milestone_removal(step, meta, dialect)
        case PlannedTemporalGuard():
            _require_no_payload(step, payload)
            return _lower_milestone_guard(step, meta, dialect)


def _row_payloads(step: PlannedInsert, payload: StepPayload) -> tuple[RowPayload, ...]:
    if not isinstance(payload, tuple) or len(payload) != len(step.entries):
        raise SqlGenError(
            f"{step.entity.canonical}: an insert stores one prepared Row Payload per entry"
        )
    for entry, prepared in zip(step.entries, payload, strict=True):
        if not prepared.prepared_from(entry) or prepared.entity != step.entity:
            raise SqlGenError(
                f"{step.entity.canonical}: a prepared Row Payload belongs to another entry"
            )
    return payload


def _assignment_payload(
    step: PlannedUpdate | PlannedClose | PlannedTemporalRevision, payload: StepPayload
) -> AssignmentPayload:
    if (
        not isinstance(payload, AssignmentPayload)
        or payload.assignments is not step.assignments
        or payload.entity != step.entity
    ):
        raise SqlGenError(
            f"{step.entity.canonical}: a revising step stores the Assignment Payload prepared "
            "from its own assignments"
        )
    return payload


def _require_no_payload(step: PlannedWrite, payload: StepPayload) -> None:
    if payload is not None:
        raise SqlGenError(f"{step.entity.canonical}: this step stores no prepared payload")


def _lower_insert(
    step: PlannedInsert, payloads: tuple[RowPayload, ...], meta: Metamodel, dialect: Dialect
) -> LoweredStatement:
    """`insert into <table>(<participating columns in Table Layout order>) values
    (?, …)[, (?, …)…]`, or the pk-gen `max` INSERT…SELECT form when a cell
    carries a generated-value expression, ending `returning <column>` where
    that allocation is returned.

    Only the columns the prepared rows name are emitted — an entry omitting a
    nullable member produces a narrower `INSERT`, never an explicit `NULL` bind
    — and every entry renders one value tuple against that one shared column
    list, in entry order. Every entry of one step names the same members, so
    every row's cells name the same columns.
    """
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    first = payloads[0]
    columns, types, documents = _placed(meta, view, entity, first.contributors, _ROW)
    for payload in payloads[1:]:
        if payload.contributors != first.contributors:
            raise SqlGenError(
                f"{entity.identity.name!r}: every entry of one insert stores the same cells"
            )
    column_sql = ", ".join(dialect.quote(column) for column in columns)
    table = view.layout.table.name
    ctx = _ctx(meta, dialect)
    if not any(isinstance(value, MaxPlusOne) for value in first.values):
        ctx.bind_typed_rows(
            [_bound(payload.values, documents) for payload in payloads],
            [None if neutral_type is None else (neutral_type, "MANAGED") for neutral_type in types],
        )
        tuples = ", ".join(f"({', '.join('?' for _ in columns)})" for _ in payloads)
        return ctx.finish(f"insert into {table}({column_sql}) values {tuples}")
    if len(payloads) > 1:
        raise SqlGenError(
            f"multi-entry insert on {entity.identity.name!r}: a generated-value expression "
            "folds into the statement itself, so it renders one row at a time (m-pk-gen)"
        )
    select_parts: list[str] = []
    returned: list[str] = []
    for column, value, neutral_type in zip(
        columns, _bound(first.values, documents), types, strict=True
    ):
        if isinstance(value, MaxPlusOne):
            select_parts.append(f"coalesce(max(t0.{dialect.quote(column)}), ?) + ?")
            ctx.bind_framework(0)
            ctx.bind_framework(1)
            if value.returned:
                returned.append(dialect.quote(column))
        else:
            select_parts.append("?")
            _bind(ctx, value, neutral_type)
    returning = f" returning {', '.join(returned)}" if returned else ""
    return ctx.finish(
        f"insert into {table}({column_sql}) select {', '.join(select_parts)} from {table} t0"
        f"{returning}"
    )


def _lower_update(
    step: PlannedUpdate, payload: AssignmentPayload, meta: Metamodel, dialect: Dialect
) -> LoweredStatement:
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
    ctx = _ctx(meta, dialect)
    version = step.concurrency.attribute if isinstance(step.concurrency, Versioned) else None
    assignment_sql = _assignment_clause(ctx, view, meta, payload, version, entity, dialect)
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _gate(ctx, view, step.concurrency, meta, dialect)
    return ctx.finish(
        f"update {view.layout.table.name} set {assignment_sql} where {where_sql}{gate_sql}"
    )


def _lower_milestone_update(
    step: PlannedClose | PlannedTemporalRevision,
    payload: AssignmentPayload,
    meta: Metamodel,
    dialect: Dialect,
) -> LoweredStatement:
    """`update <table> set <assignments> where <milestone target>[ and <gate>]`.

    Physically a close and an owned revision are updates whose target happens to
    be a milestone slot: the address renders the key, then the
    table-per-hierarchy tag guard, then one exclusive upper bound per As-Of Axis
    in canonical order, and only the gate follows — binding last, exactly as a
    version gate does one clause family over. A close assigns the
    Transaction-Time end alone; a revision assigns payload and, where it moves,
    the Valid-Time start.
    """
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    ctx = _ctx(meta, dialect)
    assignment_sql = _assignment_clause(ctx, view, meta, payload, None, entity, dialect)
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _temporal_gate(ctx, view, step.concurrency, entity, meta, dialect)
    return ctx.finish(
        f"update {view.layout.table.name} set {assignment_sql} where {where_sql}{gate_sql}"
    )


def _lower_milestone_removal(
    step: PlannedTemporalRemoval, meta: Metamodel, dialect: Dialect
) -> LoweredStatement:
    """`delete from <table> where <milestone target>[ and <gate>]`."""
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    ctx = _ctx(meta, dialect)
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _temporal_gate(ctx, view, step.concurrency, entity, meta, dialect)
    return ctx.finish(f"delete from {view.layout.table.name} where {where_sql}{gate_sql}")


def _lower_milestone_guard(
    step: PlannedTemporalGuard, meta: Metamodel, dialect: Dialect
) -> LoweredStatement:
    """`update <table> set <axis start> = <axis start> where <milestone target> and <gate>`.

    The gated Transaction-Time start is assigned to itself, so the statement
    matches and locks exactly the row a close would and changes no value of it.
    """
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    ctx = _ctx(meta, dialect)
    column = dialect.quote(_column(view, step.concurrency.start_attribute, entity))
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _temporal_gate(ctx, view, step.concurrency, entity, meta, dialect)
    return ctx.finish(
        f"update {view.layout.table.name} set {column} = {column} where {where_sql}{gate_sql}"
    )


def _lower_delete(step: PlannedDelete, meta: Metamodel, dialect: Dialect) -> LoweredStatement:
    """`delete from <table> where <target>[ and <gate>]`."""
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    ctx = _ctx(meta, dialect)
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _gate(ctx, view, step.concurrency, meta, dialect)
    return ctx.finish(f"delete from {view.layout.table.name} where {where_sql}{gate_sql}")


def _assignment_clause(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    meta: Metamodel,
    payload: AssignmentPayload,
    version: AttributeIdentity | None,
    entity: EntityMetadata,
    dialect: Dialect,
) -> str:
    version_column = None if version is None else _column(view, version, entity)
    columns, types, documents = _placed(meta, view, entity, payload.contributors, _ASSIGNMENT)
    parts: list[str] = []
    advance: tuple[str, object, NeutralType | None] | None = None
    for column, value, neutral_type, document in zip(
        columns, payload.values, types, documents, strict=True
    ):
        if isinstance(value, PatchedDocument):
            value = _document_assignments(value.patches, entity)
        elif document:
            value = JsonDocument(value)
        if column == version_column:
            advance = (column, value, neutral_type)
        else:
            parts.append(_assignment(ctx, column, value, neutral_type, dialect))
    if advance is not None:
        parts.append(_assignment(ctx, *advance, dialect))
    return ", ".join(parts)


def _assignment(
    ctx: StatementBuilder,
    column: str,
    value: object,
    neutral_type: NeutralType | None,
    dialect: Dialect,
) -> str:
    """One `set` term and the binds it contributes, in rendered order.

    Three forms, each decided by what the planner settled rather than by the
    value's shape: the registry advance self-references its own Column, a
    Structured Column takes the dialect's document mutation expression over the
    paths this step assigns, and every other Column takes one bind.
    """
    quoted = dialect.quote(column)
    if isinstance(value, SelfIncrement):
        ctx.bind_framework(value.amount)
        return f"{quoted} = {quoted} + ?"
    if isinstance(value, _DocumentAssignments):
        expression, mutation_binds = dialect.document_mutation(quoted, value.assignments)
        for index, bind in enumerate(_document_binds(mutation_binds)):
            assignment_index, offset = divmod(index, 2)
            assigned = value.assignments[assignment_index].value
            # A scalar leaf and JSON null both cross as JSON text, and each
            # projects as the value it encodes.
            if offset == 1 and (value.leaf_types[assignment_index] is not None or assigned is None):
                ctx.bind_framework(bind, wire_value=cast("WireValue", assigned))
            else:
                _bind(ctx, bind)
        return f"{quoted} = {expression}"
    _bind(ctx, value, neutral_type)
    return f"{quoted} = ?"


def _document_binds(binds: Sequence[object]) -> tuple[object, ...]:
    """The document mutation expression's binds as managed carriers.

    The dialect decides each assigned value's SQL-level form — the document
    itself for a composite, its JSON text for a scalar (`m-dialect`) — and names
    no Database Port, so wrapping a composite in the neutral `m-db-port` carrier
    the adapter hands to its driver's structured-document bind happens here,
    exactly as it does for a whole-document cell one clause family over.
    """
    return tuple(
        JsonDocument(bind) if type(bind) in (dict, list, FrozenMap, tuple) else bind
        for bind in binds
    )


def _target_predicate(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    target: WriteTarget,
    entity: EntityMetadata,
    meta: Metamodel,
    dialect: Dialect,
) -> str:
    """The row selection ``target`` names, rendered against this Table Layout.

    A singleton Key Target keys by equality and a multi-key one by an `IN` list —
    two renderings of one selection, chosen by cardinality alone. Either way the
    table-per-hierarchy tag guard follows the key, because every addressed row of
    one step is the same concrete subtype. A Milestone Target adds its axis upper
    bounds after that guard, so the whole address renders before any gate.
    """
    match target:
        case ValidatedMutationSelection(predicate=predicate):
            compiled = compile_write_predicate(predicate, meta, dialect, entity)
            if compiled.lowered is None:  # pragma: no cover - compiler always retains proof
                raise SqlGenError("compiled predicate carries no lowered statement")
            ctx.append_fragment(compiled.lowered)
            return compiled.sql
        case KeyTarget():
            key_sql = _key_predicate(ctx, view, target, entity, meta, dialect)
            tag_sql = _tag_guard(ctx, view, dialect)
            return f"{key_sql}{tag_sql}"
        case MilestoneTarget():
            columns = [_column(view, attribute, entity) for attribute in target.key_attributes]
            key_sql = " and ".join(f"{dialect.quote(column)} = ?" for column in columns)
            for attribute, value in zip(target.key_attributes, target.key_values, strict=True):
                _bind(ctx, value, _attribute(meta, attribute).type)
            tag_sql = _tag_guard(ctx, view, dialect)
            end_sql = _axis_ends(ctx, view, target, entity, meta, dialect)
            return f"{key_sql}{tag_sql}{end_sql}"


def _axis_ends(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    target: MilestoneTarget,
    entity: EntityMetadata,
    meta: Metamodel,
    dialect: Dialect,
) -> str:
    """`` and <axis end> = ?`` per As-Of Axis, in the order the target names them."""
    parts: list[str] = []
    for attribute, bound in zip(target.end_attributes, target.end_values, strict=True):
        parts.append(f" and {dialect.quote(_column(view, attribute, entity))} = ?")
        if isinstance(bound, Finite):
            _bind(ctx, bound.instant, _attribute(meta, attribute).type)
        else:
            ctx.bind_framework(INFINITY_LITERAL, wire_value=INFINITY_LITERAL)
    return "".join(parts)


def _key_predicate(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    target: KeyTarget,
    entity: EntityMetadata,
    meta: Metamodel,
    dialect: Dialect,
) -> str:
    columns = [_column(view, attribute, entity) for attribute in target.key_attributes]
    types = tuple(_attribute(meta, attribute).type for attribute in target.key_attributes)
    if len(target.key_values) == 1:
        predicate = " and ".join(f"{dialect.quote(column)} = ?" for column in columns)
        for value, neutral_type in zip(target.key_values[0], types, strict=True):
            _bind(ctx, value, neutral_type)
        return predicate
    if len(columns) == 1:
        holes = ", ".join("?" for _ in target.key_values)
        for values in target.key_values:
            _bind(ctx, values[0], types[0])
        return f"{dialect.quote(columns[0])} in ({holes})"
    keys_sql = f"({', '.join(dialect.quote(column) for column in columns)})"
    row_hole = f"({', '.join('?' for _ in columns)})"
    holes = ", ".join(row_hole for _ in target.key_values)
    ctx.bind_typed_rows(
        target.key_values,
        tuple((neutral_type, "MANAGED") for neutral_type in types),
    )
    return f"{keys_sql} in ({holes})"


def _tag_guard(ctx: StatementBuilder, view: EntityLayoutView, dialect: Dialect) -> str:
    """`` and <tag.column> = ?`` plus its bind for a table-per-hierarchy concrete,
    else nothing — the guard joins the identity predicates immediately after the
    key (`m-inheritance` / `m-sql`)."""
    discriminator = view.discriminator
    if discriminator is None:
        return ""
    ctx.bind_framework(discriminator.value)
    return f" and {dialect.quote(discriminator.slot.column.name)} = ?"


def _gate(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    concurrency: NonTemporalConcurrency,
    meta: Metamodel,
    dialect: Dialect,
) -> str:
    """`` and <version> = ?`` for a gated step, else nothing.

    The gate binds LAST, no exception (`m-opt-lock` "the version gate binds
    last"). Whether one exists at all was decided during planning, so nothing
    here consults a mode.
    """
    if not isinstance(concurrency, Versioned) or not isinstance(concurrency.gate, VersionGate):
        return ""
    slot = view.layout.contribution(concurrency.attribute)
    if slot is None:  # pragma: no cover - a gate names the target's own version Attribute
        raise SqlGenError(
            f"{view.entity.canonical}: the version gate's Attribute occupies no Column"
        )
    _bind(ctx, concurrency.gate.observed_version, _attribute(meta, concurrency.attribute).type)
    return f" and {dialect.quote(slot.column.name)} = ?"


def _temporal_gate(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    concurrency: TemporalConcurrency,
    entity: EntityMetadata,
    meta: Metamodel,
    dialect: Dialect,
) -> str:
    """`` and <axis start> = ?`` for a gated close, else nothing.

    The gate binds LAST, after the whole address — the same absolute rule a
    version gate follows, with no inheritance exception for the tag guard the
    address already rendered.
    """
    if not isinstance(concurrency, TemporalGate):
        return ""
    column = _column(view, concurrency.start_attribute, entity)
    _bind(ctx, concurrency.observed_start, _attribute(meta, concurrency.start_attribute).type)
    return f" and {dialect.quote(column)} = ?"


type _Placement = tuple[Sequence[str], Sequence[NeutralType | None], Sequence[bool]]
"""The physical Column of each prepared cell, its Attribute's Neutral Type where
it binds a scalar, and whether it binds a whole document."""

type _Placed = tuple[tuple[Hashable, ...], _Placement]
type _RecentByEntity = dict[EntityIdentity, list[_Placed | None]]

_ROW, _ASSIGNMENT = range(2)

_RECENT: Final[WeakKeyDictionary[StorageLayoutFacet, _RecentByEntity]] = WeakKeyDictionary()
"""Each model's most recently placed row and assignment contributors, by Entity.

A placement is a pure function of the immutable Storage Layout Facet, the
Entity, and its contributors, so a remembered one never goes stale, and keying
by the facet weakly ends it with its model. One row and one assignment shape
are kept per Entity because one write interleaves both. Prepared contributors
are the layout's own identity objects, so a repeated shape is recognized by
tuple equality that its identical members answer without hashing."""


def _placed(
    meta: Metamodel,
    view: EntityLayoutView,
    entity: EntityMetadata,
    contributors: tuple[Hashable, ...],
    kind: int,
) -> _Placement:
    facet = storage_layout.view(meta)
    entities = _RECENT.get(facet)
    if entities is None:
        entities = _RECENT[facet] = {}
    recent = entities.get(entity.identity)
    if recent is None:
        recent = entities[entity.identity] = [None, None]
    placed = recent[kind]
    if placed is None or placed[0] != contributors:
        placed = recent[kind] = (contributors, _placement(view, entity, contributors))
    return placed[1]


def _placement(
    view: EntityLayoutView,
    entity: EntityMetadata,
    contributors: Sequence[Hashable],
) -> _Placement:
    """Where each prepared cell lands: the physical Column its contributor's
    slot occupies.

    A document a cell stores — a Value Object occurrence with a Column of its
    own, or the Table's shared Structured Column — binds as one
    :class:`~parallax.core.db_port.JsonDocument`, never decomposed. A scalar
    binds at its Attribute's Neutral Type.
    """
    columns: list[str] = []
    types: list[NeutralType | None] = []
    documents: list[bool] = []
    selection = view.member_selection
    for contributor in contributors:
        if isinstance(contributor, InheritanceDiscriminator):
            discriminator = view.discriminator
            if discriminator is None or discriminator.slot.contributor != contributor:
                raise SqlGenError(
                    f"{entity.identity.name!r}: a prepared discriminator cell names no tag slot"
                )
            columns.append(discriminator.slot.column.name)
            types.append(None)
            documents.append(False)
            continue
        slot = view.layout.contribution(cast("ColumnContributor", contributor))
        if slot is None:
            raise SqlGenError(
                f"{entity.identity.name!r}: a prepared cell's contributor occupies no Column of "
                "the target's Table Layout"
            )
        columns.append(slot.column.name)
        if isinstance(contributor, AttributeIdentity):
            binding = selection.bindings[selection.position(contributor)]
            types.append(cast("AttributeMetadata", binding).type)
            documents.append(False)
        else:
            types.append(None)
            documents.append(True)
    return tuple(columns), tuple(types), tuple(documents)


def _bound(values: tuple[object, ...], documents: Sequence[bool]) -> Sequence[object]:
    """One row's bind values: each stored document wrapped as the port's
    structured-document carrier, every other value as it is."""
    if not any(documents):
        return values
    return [
        JsonDocument(value) if document else value
        for value, document in zip(values, documents, strict=True)
    ]


def _document_assignments(
    patches: Sequence[PreparedPatch], entity: EntityMetadata
) -> _DocumentAssignments:
    assignments: list[DocumentAssignment] = []
    for patch in patches:
        if patch.removes:
            raise SqlGenError(
                f"{entity.identity.name!r}: a revising statement assigns values and removes no "
                "document key"
            )
        assignments.append(
            DocumentValueAssignment(patch.path, patch.value)
            if patch.leaf is None
            else DocumentLeafAssignment(patch.path, patch.value)
        )
    return _DocumentAssignments(tuple(assignments), tuple(patch.leaf for patch in patches))


def _column(view: EntityLayoutView, attribute: AttributeIdentity, entity: EntityMetadata) -> str:
    slot = view.layout.contribution(attribute)
    if slot is None:  # pragma: no cover - a planned Attribute always occupies a Column
        raise SqlGenError(
            f"{entity.identity.name!r}: {attribute.name!r} occupies no Column of the target's "
            "Table Layout"
        )
    return slot.column.name


def _entity(meta: Metamodel, identity: EntityIdentity) -> EntityMetadata:
    entity = meta.entity(identity)
    if entity is None:  # pragma: no cover - a planned step always names an accepted Entity
        raise SqlGenError(f"{identity.canonical!r}: step target is not an accepted Entity")
    return entity


def _layout(meta: Metamodel, entity: EntityMetadata) -> EntityLayoutView:
    view = entity_layout(meta, entity)
    if view is None:
        raise SqlGenError(f"{entity.identity.name!r}: write target has no effective table")
    return view
