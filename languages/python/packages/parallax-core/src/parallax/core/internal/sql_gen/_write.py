from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from parallax.core.internal import inheritance, storage_layout
from parallax.core.internal.base import (
    INFINITY,
    INFINITY_LITERAL,
    DocumentValue,
    InternalError,
    NeutralType,
    StructuredDocument,
)
from parallax.core.internal.database_binding import ResolvedBinding
from parallax.core.internal.dialect import ArrayBind, Dialect
from parallax.core.internal.document_codec import assigned_members
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    CompiledEntity,
    EntityIdentity,
    Metamodel,
)
from parallax.core.internal.navigate import NoRootSelections, resolve_temporal_visibility
from parallax.core.internal.sql_gen._compile import compile_write_predicate
from parallax.core.internal.sql_gen._context import (
    SQL_GENERATION_FAILED,
    LoweredStatement,
    StatementBuilder,
)
from parallax.core.internal.storage_layout import EntityLayoutView
from parallax.core.internal.write_plan.payload import (
    AssignmentPayload,
    DocumentPatches,
    EffectSlots,
    InsertPayload,
    RowSlots,
)
from parallax.core.internal.write_plan.steps import (
    Finite,
    Infinity,
    KeyTarget,
    MaxPlusOne,
    MilestoneTarget,
    NonTemporalConcurrency,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedStep,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    ResolvedMutationSelection,
    SelfIncrement,
    TemporalConcurrency,
    TemporalGate,
    Versioned,
    VersionGate,
    WriteTarget,
)

__all__ = [
    "GroupedEffectBuilder",
    "InsertStatementBuilder",
    "StepPayload",
    "compile_write_step",
    "non_insert_parameter_ceiling",
]

type StepPayload = InsertPayload | AssignmentPayload | None
"""The prepared values one step's statement stores: an insert's entries' cells,
in entry order, under their Row Slots, the Assignment Payload a revising step
writes, or nothing for a step that stores no represented value."""


# One rendered cell: the physical Column it occupies and the value that lands
# there — a bind, the prepared patches a Structured Column merges, or the
# generated-value expression the statement folds in.
type _Cell = tuple[str, object, NeutralType | None]


def _ctx(resolved: ResolvedBinding, dialect: Dialect) -> StatementBuilder:
    meta = resolved.meta
    return StatementBuilder(
        resolved,
        inheritance.inheritance_facet_of(meta),
        storage_layout.storage_layout_facet_of(meta),
        dialect,
    )


def _bind(ctx: StatementBuilder, value: object, neutral_type: NeutralType | None = None) -> None:
    if value is INFINITY:
        ctx.bind_framework(value)
    elif neutral_type is not None and value is not None:
        ctx.bind_managed(value, neutral_type)
    elif isinstance(value, StructuredDocument):
        ctx.bind_document(value)
    else:
        ctx.bind_structural(value)


def _attribute(meta: Metamodel, identity: AttributeIdentity) -> AttributeMetadata:
    entity = meta.entity(identity.entity)
    attribute = None if entity is None else entity.attribute(identity.name)
    if attribute is None:  # pragma: no cover - planned identities come from accepted metadata
        raise InternalError(
            SQL_GENERATION_FAILED,
            f"{identity.entity.canonical}.{identity.name}: planned Attribute is not "
            "accepted metadata",
        )
    return attribute


def entity_layout(meta: Metamodel, entity: CompiledEntity) -> EntityLayoutView | None:
    return storage_layout.storage_layout_facet_of(meta).entity(entity.identity)


def compile_write_step(
    step: PlannedStep, payload: StepPayload, resolved: ResolvedBinding, dialect: Dialect
) -> LoweredStatement:
    """Lower one finalized step to its single DML statement, storing exactly the
    values ``payload`` prepared for it.

    Lowering places, renders, and binds; it never assembles a payload itself. A
    payload prepared from other inputs than the step's own, or a missing one, is
    a broken caller contract rather than a request to prepare one here.
    """
    match step:
        case PlannedInsert():
            return _lower_insert(step, _insert_payload(step, payload), resolved, dialect)
        case PlannedUpdate():
            return _lower_update(step, _assignment_payload(step, payload), resolved, dialect)
        case PlannedClose() | PlannedTemporalRevision():
            return _lower_milestone_update(
                step, _assignment_payload(step, payload), resolved, dialect
            )
        case PlannedDelete():
            _require_no_payload(step, payload)
            return _lower_delete(step, resolved, dialect)
        case PlannedTemporalRemoval():
            _require_no_payload(step, payload)
            return _lower_milestone_removal(step, resolved, dialect)
        case PlannedTemporalGuard():
            _require_no_payload(step, payload)
            return _lower_milestone_guard(step, resolved, dialect)


def non_insert_parameter_ceiling(
    step: PlannedClose
    | PlannedTemporalRevision
    | PlannedTemporalRemoval
    | PlannedTemporalGuard
    | PlannedUpdate
    | PlannedDelete,
) -> int:
    """A conservative upper bound on the SQL parameters ``step``'s statement
    carries, computed before its payload is prepared.

    The address binds each key value and at most one table-per-hierarchy tag,
    and a milestone address each axis end too; a temporal or version gate binds
    once more. Each member a revising step assigns, a version advance or
    registry increment included, binds at most once: in a Column of its own,
    or, with every other member the shared Structured Column holds, as the one
    object its mutation expression merges (`m-dialect`). A predicate-selected
    step's binds follow its predicate rather than its shape, so it has no such
    bound.
    """
    target = step.target
    if isinstance(target, ResolvedMutationSelection):
        raise InternalError(
            SQL_GENERATION_FAILED,
            f"{step.entity.canonical}: a predicate-selected step's binds are not bounded by its "
            "shape",
        )
    if isinstance(target, MilestoneTarget):
        ceiling = len(target.key_values) + 1 + len(target.end_values)
    else:
        ceiling = sum(len(values) for values in target.key_values) + 1
    if _gated(step.concurrency):
        ceiling += 1
    if isinstance(step, PlannedClose | PlannedTemporalRevision | PlannedUpdate):
        assignments = step.assignments
        ceiling += len(assignments.attributes) + len(assignments.value_objects)
    return ceiling


def _gated(concurrency: TemporalConcurrency | NonTemporalConcurrency) -> bool:
    return isinstance(concurrency, TemporalGate) or (
        isinstance(concurrency, Versioned) and isinstance(concurrency.gate, VersionGate)
    )


def _insert_payload(step: PlannedInsert, payload: StepPayload) -> InsertPayload:
    if (
        not isinstance(payload, InsertPayload)
        or len(payload.rows) != len(step.entries)
        or payload.slots.entity != step.entity
        or payload.slots.presence != step.entries[0].row.presence
    ):
        raise InternalError(
            SQL_GENERATION_FAILED,
            f"{step.entity.canonical}: an insert stores one prepared row per entry, under the "
            "Row Slots its entries state",
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
        raise InternalError(
            SQL_GENERATION_FAILED,
            f"{step.entity.canonical}: a revising step stores the Assignment Payload prepared "
            "from its own assignments",
        )
    return payload


def _require_no_payload(step: PlannedStep, payload: StepPayload) -> None:
    if payload is not None:
        raise InternalError(
            SQL_GENERATION_FAILED, f"{step.entity.canonical}: this step stores no prepared payload"
        )


class InsertStatementBuilder:
    """One non-generated insert of every entry appended, in entry order, into
    `<table>(<participating columns in Table Layout order>)`.

    ``slots`` fix the Table and the column list; an entry omitting a nullable
    member produces a narrower `INSERT`, never an explicit `NULL` bind. Each
    entry's ``cells`` are the ones ``slots`` gathered from its row, which
    admission already judged, so they bind as they are. A refused entry is not
    held, so :meth:`finish` still renders exactly the entries appended before
    it. A generated-value expression folds into its own statement and never
    reaches this builder.

    One entry renders `values (?, …)` with one bind per cell
    (:meth:`StatementBuilder.bind_managed_row`). Several render the dialect's
    column-array form, `select * from unnest(cast(? as <type>[]), …)`, with
    one array bind per cell slot whatever the number of entries, so its text
    and bind count follow the slots alone (`m-sql` *Batched insert / update*).
    A dialect without array binds has no multi-row form here.

    One builder compiles either a logical multi-entry insert, every entry of
    which it holds before finishing, or a run of single-entry inserts execution
    groups into one physical statement.
    """

    __slots__ = ("_dialect", "_resolved", "_rows", "_slots")

    def __init__(
        self,
        slots: RowSlots,
        cells: tuple[object, ...],
        resolved: ResolvedBinding,
        dialect: Dialect,
    ) -> None:
        self._slots = slots
        self._resolved = resolved
        self._dialect = dialect
        self._rows = [_placed(slots, cells)]

    def append(self, cells: tuple[object, ...]) -> None:
        self._rows.append(_placed(self._slots, cells))

    def finish(self) -> LoweredStatement:
        slots = self._slots
        dialect = self._dialect
        rows = self._rows
        statement = _ctx(self._resolved, dialect)
        column_sql = ", ".join([dialect.quote(column) for column in slots.columns])
        if len(rows) == 1:
            statement.bind_managed_row(
                _bound(rows[0], slots.documents),
                tuple(
                    [
                        None if neutral_type is None else (neutral_type, "MANAGED")
                        for neutral_type in slots.types
                    ]
                ),
            )
            holes = ", ".join(["?"] * len(slots.columns))
            return statement.finish(f"insert into {slots.table}({column_sql}) values ({holes})")
        if not dialect.binds_arrays:
            raise InternalError(
                SQL_GENERATION_FAILED,
                f"{slots.entity.canonical}: the {dialect.name!r} dialect binds no arrays, and "
                "a multi-row insert has no other form here",
            )
        element_types = slots.element_types
        for element_type, column in zip(element_types, slots.column_cells(rows), strict=True):
            statement.bind_array(ArrayBind(element_type, column))
        arrays = ", ".join(
            [dialect.array_parameter(element_type) for element_type in element_types]
        )
        return statement.finish(
            f"insert into {slots.table}({column_sql}) select * from unnest({arrays})"
        )


def _placed(slots: RowSlots, cells: tuple[object, ...]) -> tuple[object, ...]:
    """``cells`` as one row ``slots`` place: one cell per slot."""
    if len(cells) != len(slots.columns):
        raise InternalError(
            SQL_GENERATION_FAILED, "a repeated bind pattern has inconsistent row widths"
        )
    return cells


def _lower_insert(
    step: PlannedInsert, payload: InsertPayload, resolved: ResolvedBinding, dialect: Dialect
) -> LoweredStatement:
    """One logical insert's statement: every entry through one
    :class:`InsertStatementBuilder`, or the pk-gen `max` INSERT…SELECT form when
    a cell carries a generated-value expression, ending `returning <column>`
    where that allocation is returned. Several entries need the dialect's
    column-array form, so a dialect without array binds refuses them."""
    slots = payload.slots
    first, *rest = payload.rows
    if not any(isinstance(value, MaxPlusOne) for value in first):
        builder = InsertStatementBuilder(slots, first, resolved, dialect)
        for cells in rest:
            builder.append(cells)
        return builder.finish()
    if rest:
        raise InternalError(
            SQL_GENERATION_FAILED,
            f"multi-entry insert on {step.entity.name!r}: a generated-value expression "
            "folds into the statement itself, so it renders one row at a time (m-pk-gen)",
        )
    column_sql = ", ".join(dialect.quote(column) for column in slots.columns)
    table = slots.table
    ctx = _ctx(resolved, dialect)
    select_parts: list[str] = []
    returned: list[str] = []
    for column, value, neutral_type in zip(
        slots.columns, _bound(_placed(slots, first), slots.documents), slots.types, strict=True
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


_SOURCE = "v"
"""The alias of a grouped effect's source; its columns are ``c1`` onward and
its ordinal ``ord``, and the target Table is aliased ``t``, so no name either
side declares can capture a reference to the other."""


def _source_column(index: int) -> str:
    return f"{_SOURCE}.c{index + 1}"


type _Effect = (
    PlannedUpdate
    | PlannedDelete
    | PlannedClose
    | PlannedTemporalRevision
    | PlannedTemporalRemoval
    | PlannedTemporalGuard
)


class GroupedEffectBuilder:
    """One statement applying every effect appended, in append order, each
    effect's per-row values drawn from one row of its source and the
    statement returning the source ordinal of every target row it changed or
    removed (`m-sql` *Grouped effects*).

    ``slots`` fix the step kind and the source columns: each binds one array,
    whatever the number of effects, through the dialect's array-parameter
    cast, and the source is `unnest(…) with ordinality`. An update, close,
    revision, or guard is an `update … from` the source and a delete or
    removal a `delete … using` it. Each renders its assignments, address, and
    gate in the clause grammar the lone step's statement does, each per-row
    value taken from its source column rather than a bind: a key, a bounded
    axis end, a version advance, an assigned cell, and a version or
    Transaction-Time start gate alike. Only the table-per-hierarchy tag and
    the open Transaction-Time end bind once. Each effect's cells join the
    source columns as it is appended, so no effect's payload is held past its
    own append but the first's, whose placement renders the statement. A
    refused effect gathers nothing, so :meth:`finish` still renders exactly the
    effects appended before it. A dialect without array binds has no grouped
    effect.
    """

    __slots__ = ("_columns", "_dialect", "_first", "_resolved", "_slots")

    def __init__(self, slots: EffectSlots, resolved: ResolvedBinding, dialect: Dialect) -> None:
        if not dialect.binds_arrays:
            raise InternalError(
                SQL_GENERATION_FAILED,
                f"{slots.entity.canonical}: the {dialect.name!r} dialect binds no arrays, and "
                "a grouped effect has no other form",
            )
        self._slots = slots
        self._resolved = resolved
        self._dialect = dialect
        self._columns: tuple[list[object], ...] = tuple([[] for _ in slots.element_types])
        self._first: tuple[_Effect, AssignmentPayload | None] | None = None

    def append(self, step: PlannedStep, payload: StepPayload) -> None:
        """Gather ``step``'s cells, taking its assigned ones from the payload
        prepared from its assignments, refusing a step of another shape than the
        slots place."""
        slots = self._slots
        if (
            isinstance(step, PlannedInsert)
            or type(step) is not slots.kind
            or step.entity != slots.entity
        ):
            raise InternalError(
                SQL_GENERATION_FAILED,
                f"{slots.entity.canonical}: a grouped effect holds effects of its shape's kind "
                "and Entity",
            )
        if _gated(step.concurrency) != (slots.gate_source is not None) or not _shaped_address(
            step, slots
        ):
            raise InternalError(
                SQL_GENERATION_FAILED,
                f"{slots.entity.canonical}: a grouped effect's step addresses or gates its row "
                "otherwise than its shape",
            )
        assigned: AssignmentPayload | None = None
        if isinstance(step, PlannedUpdate | PlannedClose | PlannedTemporalRevision):
            assigned = _assignment_payload(step, payload)
            if len(assigned.values) != len(slots.assignment_sources):
                raise InternalError(
                    SQL_GENERATION_FAILED,
                    f"{slots.entity.canonical}: a grouped effect's step assigns a cell its shape "
                    "does not place",
                )
        else:
            _require_no_payload(step, payload)
        slots.gather(self._columns, step, assigned)
        if self._first is None:
            self._first = (step, assigned)

    def finish(self) -> LoweredStatement:
        slots, resolved, dialect = self._slots, self._resolved, self._dialect
        meta = resolved.meta
        if self._first is None:
            raise InternalError(
                SQL_GENERATION_FAILED, f"{slots.entity.canonical}: a grouped effect holds an effect"
            )
        first, payload = self._first
        entity = _entity(meta, first.entity)
        view = _layout(meta, entity)
        ctx = _ctx(resolved, dialect)
        terms = _sourced_set_terms(first, payload, slots, view, entity, dialect)
        element_types = slots.element_types
        for element_type, cells in zip(element_types, self._columns, strict=True):
            ctx.bind_array(ArrayBind(element_type, cells))
        arrays = ", ".join(
            [dialect.array_parameter(element_type) for element_type in element_types]
        )
        names = ", ".join([f"c{index + 1}" for index in range(len(element_types))])
        source = f"unnest({arrays}) with ordinality {_SOURCE}({names}, ord)"
        where = " and ".join(_sourced_address(ctx, first, slots, view, entity, dialect))
        table = ctx.table_sql(view.layout)
        if isinstance(first, PlannedDelete | PlannedTemporalRemoval):
            return ctx.finish(
                f"delete from {table} t using {source} where {where} returning {_SOURCE}.ord"
            )
        return ctx.finish(
            f"update {table} t set {', '.join(terms)} from {source} "
            f"where {where} returning {_SOURCE}.ord"
        )


def _shaped_address(step: _Effect, slots: EffectSlots) -> bool:
    """Whether ``step`` addresses one row as ``slots`` bind it: one key, and
    for a milestone the open Transaction-Time end wherever its effects share
    it."""
    target = step.target
    if isinstance(target, MilestoneTarget):
        sources = slots.end_sources
        return len(target.end_values) == len(sources) and all(
            source is not None or isinstance(bound, Infinity)
            for bound, source in zip(target.end_values, sources, strict=True)
        )
    return isinstance(target, KeyTarget) and len(target.key_values) == 1 and not slots.end_sources


def _sourced_set_terms(
    first: _Effect,
    payload: AssignmentPayload | None,
    slots: EffectSlots,
    view: EntityLayoutView,
    entity: CompiledEntity,
    dialect: Dialect,
) -> list[str]:
    """Each `set` term of a grouped effect in the order a lone statement of
    ``first``'s kind renders them, every value drawn from the source; none for
    a deletion."""
    if isinstance(first, PlannedTemporalGuard):
        column = dialect.quote(_column(view, first.concurrency.start_attribute, entity))
        return [f"{column} = t.{column}"]
    if payload is None:
        return []
    concurrency = first.concurrency
    version_column = (
        _column(view, concurrency.attribute, entity) if isinstance(concurrency, Versioned) else None
    )
    terms: list[str] = []
    advance: str | None = None
    for column, value, source in zip(
        payload.placement.columns, payload.values, slots.assignment_sources, strict=True
    ):
        quoted = dialect.quote(column)
        if isinstance(value, DocumentPatches):
            expression = dialect.sourced_document_mutation(f"t.{quoted}", _source_column(source))
        else:
            expression = _source_column(source)
        term = f"{quoted} = {expression}"
        if column == version_column:
            advance = term
        else:
            terms.append(term)
    if advance is not None:
        terms.append(advance)
    return terms


def _sourced_address(
    ctx: StatementBuilder,
    first: _Effect,
    slots: EffectSlots,
    view: EntityLayoutView,
    entity: CompiledEntity,
    dialect: Dialect,
) -> list[str]:
    """A grouped effect's `where` conditions in the order a lone statement of
    ``first``'s kind renders them — key, tag guard, each As-Of Axis end, then
    the gate — binding the tag and every shared open end as it goes."""
    target = first.target
    key_attributes = cast("KeyTarget | MilestoneTarget", target).key_attributes
    where = [
        f"t.{dialect.quote(_column(view, attribute, entity))} = {_source_column(source)}"
        for attribute, source in zip(key_attributes, slots.key_sources, strict=True)
    ]
    discriminator = view.discriminator
    if discriminator is not None:
        ctx.bind_framework(discriminator.value)
        where.append(f"t.{dialect.quote(discriminator.slot.column.name)} = ?")
    if isinstance(target, MilestoneTarget):
        for attribute, source in zip(target.end_attributes, slots.end_sources, strict=True):
            column = f"t.{dialect.quote(_column(view, attribute, entity))}"
            if source is None:
                ctx.bind_framework(INFINITY_LITERAL, wire_value=INFINITY_LITERAL)
                where.append(f"{column} = ?")
            else:
                where.append(f"{column} = {_source_column(source)}")
    gate = slots.gate_source
    if gate is not None:
        concurrency = first.concurrency
        attribute = (
            concurrency.attribute
            if isinstance(concurrency, Versioned)
            else cast("TemporalGate", concurrency).start_attribute
        )
        where.append(
            f"t.{dialect.quote(_column(view, attribute, entity))} = {_source_column(gate)}"
        )
    return where


def _lower_update(
    step: PlannedUpdate, payload: AssignmentPayload, resolved: ResolvedBinding, dialect: Dialect
) -> LoweredStatement:
    """`update <table> set <assigned columns> = ?, …[ where <target>[ and <gate>]]`.

    The assigned columns follow the Table Layout's slot order, with one
    exception: the optimistic-lock version renders LAST, after every other
    column, because a value-object document occupies the Document tier — after
    every scalar tier, the version's own slot included (`m-value-object` "One
    column") — so threading the advance through slot order would wrongly render
    it before the document. That position is a rendering fact, not a layout one,
    mirroring the version gate's own "binds last" rule one clause family over.
    """
    meta = resolved.meta
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    ctx = _ctx(resolved, dialect)
    version = step.concurrency.attribute if isinstance(step.concurrency, Versioned) else None
    assignment_sql = _set_clause(ctx, view, payload, version, entity, dialect)
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _gate(ctx, view, step.concurrency, meta, dialect)
    return ctx.finish(
        f"update {ctx.table_sql(view.layout)} set {assignment_sql}{_where(where_sql, gate_sql)}"
    )


def _lower_milestone_update(
    step: PlannedClose | PlannedTemporalRevision,
    payload: AssignmentPayload,
    resolved: ResolvedBinding,
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
    meta = resolved.meta
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    ctx = _ctx(resolved, dialect)
    assignment_sql = _set_clause(ctx, view, payload, None, entity, dialect)
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _temporal_gate(ctx, view, step.concurrency, entity, meta, dialect)
    return ctx.finish(
        f"update {ctx.table_sql(view.layout)} set {assignment_sql}{_where(where_sql, gate_sql)}"
    )


def _lower_milestone_removal(
    step: PlannedTemporalRemoval, resolved: ResolvedBinding, dialect: Dialect
) -> LoweredStatement:
    """`delete from <table> where <milestone target>[ and <gate>]`."""
    meta = resolved.meta
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    ctx = _ctx(resolved, dialect)
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _temporal_gate(ctx, view, step.concurrency, entity, meta, dialect)
    return ctx.finish(f"delete from {ctx.table_sql(view.layout)}{_where(where_sql, gate_sql)}")


def _lower_milestone_guard(
    step: PlannedTemporalGuard, resolved: ResolvedBinding, dialect: Dialect
) -> LoweredStatement:
    """`update <table> set <axis start> = <axis start> where <milestone target> and <gate>`.

    The gated Transaction-Time start is assigned to itself, so the statement
    matches and locks exactly the row a close would and changes no value of it.
    """
    meta = resolved.meta
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    ctx = _ctx(resolved, dialect)
    column = dialect.quote(_column(view, step.concurrency.start_attribute, entity))
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _temporal_gate(ctx, view, step.concurrency, entity, meta, dialect)
    return ctx.finish(
        f"update {ctx.table_sql(view.layout)} set {column} = {column}{_where(where_sql, gate_sql)}"
    )


def _lower_delete(
    step: PlannedDelete, resolved: ResolvedBinding, dialect: Dialect
) -> LoweredStatement:
    """`delete from <table>[ where <target>[ and <gate>]]`."""
    meta = resolved.meta
    entity = _entity(meta, step.entity)
    view = _layout(meta, entity)
    ctx = _ctx(resolved, dialect)
    where_sql = _target_predicate(ctx, view, step.target, entity, meta, dialect)
    gate_sql = _gate(ctx, view, step.concurrency, meta, dialect)
    return ctx.finish(f"delete from {ctx.table_sql(view.layout)}{_where(where_sql, gate_sql)}")


def _where(*conditions: str) -> str:
    """One `` where`` clause over the conditions that render, or nothing when
    none does: a readless target selecting every row renders no condition
    (`m-predicate` `true`), so its statement carries no `where` at all."""
    rendered = [condition for condition in conditions if condition]
    return f" where {' and '.join(rendered)}" if rendered else ""


def _set_clause(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    payload: AssignmentPayload,
    version: AttributeIdentity | None,
    entity: CompiledEntity,
    dialect: Dialect,
) -> str:
    version_column = None if version is None else _column(view, version, entity)
    placement = payload.placement
    columns, types, documents = placement.columns, placement.types, placement.documents
    parts: list[str] = []
    advance: tuple[str, object, NeutralType | None] | None = None
    for column, value, neutral_type, document in zip(
        columns, payload.values, types, documents, strict=True
    ):
        if document and value is not None and not isinstance(value, DocumentPatches):
            value = StructuredDocument(cast("DocumentValue", value))
        if column == version_column:
            advance = (column, value, neutral_type)
        else:
            parts.append(_set_term(ctx, column, value, neutral_type, dialect))
    if advance is not None:
        parts.append(_set_term(ctx, *advance, dialect))
    return ", ".join(parts)


def _set_term(
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
    members this step assigns, and every other Column takes one bind.
    """
    quoted = dialect.quote(column)
    if isinstance(value, SelfIncrement):
        ctx.bind_framework(value.amount)
        return f"{quoted} = {quoted} + ?"
    if isinstance(value, DocumentPatches):
        expression, binds = dialect.document_mutation(quoted, assigned_members(value.patches))
        for bind in binds:
            _bind(ctx, bind)
        return f"{quoted} = {expression}"
    _bind(ctx, value, neutral_type)
    return f"{quoted} = ?"


def _target_predicate(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    target: WriteTarget,
    entity: CompiledEntity,
    meta: Metamodel,
    dialect: Dialect,
) -> str:
    """The row selection ``target`` names, rendered against this Table Layout.

    A singleton Key Target keys by equality and a multi-key one by a membership
    of the key — two renderings of one selection, chosen by cardinality alone.
    Either way the table-per-hierarchy tag guard follows the key, because every
    addressed row of one step is the same concrete subtype. A Milestone Target
    adds its axis upper bounds after that guard, so the whole address renders
    before any gate. A
    Resolved Mutation Selection renders its predicate in place, or tests the
    membership of the Table's physical key in the key selection its compiled
    predicate is, inside this one statement. A readless target pins no temporal
    coordinate, so every temporal Entity its predicate reaches is visible at
    Latest on each of its axes (`m-navigate`).
    """
    match target:
        case ResolvedMutationSelection(predicate=predicate):
            temporal = resolve_temporal_visibility(
                predicate, target=entity, model=meta, resolution=NoRootSelections()
            )
            compiled = compile_write_predicate(temporal, ctx.resolved, dialect, entity)
            if compiled.lowered is None:  # pragma: no cover - compiler always retains proof
                raise InternalError(
                    SQL_GENERATION_FAILED, "compiled predicate carries no lowered statement"
                )
            ctx.append_fragment(compiled.lowered)
            if compiled.selection:
                return f"{_physical_key(view, dialect)} in ({compiled.sql})"
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


def _physical_key(view: EntityLayoutView, dialect: Dialect) -> str:
    """The Table's physical primary-key Columns in key order, as one membership
    operand: the Column itself, or the row of them."""
    columns = [dialect.quote(slot.column.name) for slot in view.layout.physical_primary_key]
    return columns[0] if len(columns) == 1 else f"({', '.join(columns)})"


def _axis_ends(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    target: MilestoneTarget,
    entity: CompiledEntity,
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
    entity: CompiledEntity,
    meta: Metamodel,
    dialect: Dialect,
) -> str:
    """The Key Target's rows: each key Column equal to its value for one key,
    and for several a membership of the key, through one array per key Column
    where the dialect binds arrays and one placeholder per value otherwise."""
    columns = [_column(view, attribute, entity) for attribute in target.key_attributes]
    types = tuple(_attribute(meta, attribute).type for attribute in target.key_attributes)
    if len(target.key_values) == 1:
        predicate = " and ".join(f"{dialect.quote(column)} = ?" for column in columns)
        for value, neutral_type in zip(target.key_values[0], types, strict=True):
            _bind(ctx, value, neutral_type)
        return predicate
    if dialect.binds_arrays:
        arrays: list[str] = []
        for index, neutral_type in enumerate(types):
            ctx.bind_array(ArrayBind(neutral_type, [values[index] for values in target.key_values]))
            arrays.append(dialect.array_parameter(neutral_type))
        if len(columns) == 1:
            return f"{dialect.quote(columns[0])} = any({arrays[0]})"
        keys_sql = ", ".join(dialect.quote(column) for column in columns)
        return f"({keys_sql}) in (select * from unnest({', '.join(arrays)}))"
    if len(columns) == 1:
        holes = ", ".join("?" for _ in target.key_values)
        for values in target.key_values:
            _bind(ctx, values[0], types[0])
        return f"{dialect.quote(columns[0])} in ({holes})"
    keys_sql = f"({', '.join(dialect.quote(column) for column in columns)})"
    row_hole = f"({', '.join('?' for _ in columns)})"
    holes = ", ".join(row_hole for _ in target.key_values)
    ctx.bind_managed_rows(
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
    """``<version> = ?`` for a gated step, else nothing.

    The gate binds LAST, no exception (`m-sql` "the version gate binds
    last"). Whether one exists at all was decided during planning, so nothing
    here consults a mode.
    """
    if not isinstance(concurrency, Versioned) or not isinstance(concurrency.gate, VersionGate):
        return ""
    slot = view.layout.contribution(concurrency.attribute)
    if slot is None:  # pragma: no cover - a gate names the target's own version Attribute
        raise InternalError(
            SQL_GENERATION_FAILED,
            f"{view.entity.canonical}: the version gate's Attribute occupies no Column",
        )
    _bind(ctx, concurrency.gate.observed_version, _attribute(meta, concurrency.attribute).type)
    return f"{dialect.quote(slot.column.name)} = ?"


def _temporal_gate(
    ctx: StatementBuilder,
    view: EntityLayoutView,
    concurrency: TemporalConcurrency,
    entity: CompiledEntity,
    meta: Metamodel,
    dialect: Dialect,
) -> str:
    """``<axis start> = ?`` for a gated close, else nothing.

    The gate binds LAST, after the whole address — the same absolute rule a
    version gate follows, with no inheritance exception for the tag guard the
    address already rendered.
    """
    if not isinstance(concurrency, TemporalGate):
        return ""
    column = _column(view, concurrency.start_attribute, entity)
    _bind(ctx, concurrency.observed_start, _attribute(meta, concurrency.start_attribute).type)
    return f"{dialect.quote(column)} = ?"


def _bound(values: tuple[object, ...], documents: Sequence[bool]) -> Sequence[object]:
    """One row's bind values: each stored document wrapped as a
    :class:`StructuredDocument`, every other value as it is, ``None``
    included, so a null Value Object binds SQL NULL."""
    if not any(documents):
        return values
    return [
        StructuredDocument(cast("DocumentValue", value))
        if document and value is not None
        else value
        for value, document in zip(values, documents, strict=True)
    ]


def _column(view: EntityLayoutView, attribute: AttributeIdentity, entity: CompiledEntity) -> str:
    slot = view.layout.contribution(attribute)
    if slot is None:  # pragma: no cover - a planned Attribute always occupies a Column
        raise InternalError(
            SQL_GENERATION_FAILED,
            f"{entity.identity.name!r}: {attribute.name!r} occupies no Column of the target's "
            "Table Layout",
        )
    return slot.column.name


def _entity(meta: Metamodel, identity: EntityIdentity) -> CompiledEntity:
    entity = meta.entity(identity)
    if entity is None:  # pragma: no cover - a planned step always names an accepted Entity
        raise InternalError(
            SQL_GENERATION_FAILED, f"{identity.canonical!r}: step target is not an accepted Entity"
        )
    return entity


def _layout(meta: Metamodel, entity: CompiledEntity) -> EntityLayoutView:
    view = entity_layout(meta, entity)
    if view is None:  # pragma: no cover - write planning refuses a target with no effective table
        raise InternalError(
            SQL_GENERATION_FAILED, f"{entity.identity.name!r}: write target has no effective table"
        )
    return view
