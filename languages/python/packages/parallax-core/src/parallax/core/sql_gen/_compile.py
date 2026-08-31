"""Lower resolved flat Entity Queries to canonical SQL (m-sql).

``compile_read`` consumes :class:`ValidatedEntityQuery`: target metadata, predicate
members and operands, temporal/navigation rewrites, ordering, narrowing, and the
resolved read projection are already retained. This package chooses physical layout,
renders dialect expressions, records role-classified binds, and assembles inheritance
branches; it performs no authored reference or relationship resolution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, assert_never, cast

from parallax.core.base import (
    DocumentReadOrdinals,
    NeutralType,
    admits_stored_scalar,
)
from parallax.core.deep_fetch import ValidatedEntityQuery
from parallax.core.dialect import Dialect, LockMode, projection_result_key
from parallax.core.document_codec import DocumentFinding
from parallax.core.inheritance import InheritanceFacet
from parallax.core.inheritance import view as _inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    ValueObjectMetadata,
)
from parallax.core.object_query._validated import ValidatedOrderTerm
from parallax.core.predicate import Narrow
from parallax.core.predicate._validated import ValidatedPredicate
from parallax.core.sql_gen._context import LoweredStatement, SqlGenError, StatementBuilder
from parallax.core.sql_gen._context import table_layout as _table_layout

# The family LANE of this compiler — distinct from `parallax.core.inheritance`
# above, which is the metamodel module. Each name is aliased down to the
# module-private spelling it had while this file owned it, so a use site below
# never confuses the two.
from parallax.core.sql_gen._inheritance import RowTransform as _RowTransform
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import TpcsSinglePlan as _TpcsSinglePlan
from parallax.core.sql_gen._inheritance import TpcsUnionPlan as _TpcsUnionPlan
from parallax.core.sql_gen._inheritance import TphPlan as _TphPlan
from parallax.core.sql_gen._inheritance import (
    direct_document_transform as _direct_document_transform,
)
from parallax.core.sql_gen._inheritance import document_projection as _document_projection
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import observed_document as _observed_document
from parallax.core.sql_gen._inheritance import plan_inheritance_read as _plan_inheritance_read
from parallax.core.sql_gen._inheritance import position_documents as _position_documents
from parallax.core.sql_gen._inheritance import render_projection as _render_projection
from parallax.core.sql_gen._inheritance import select_projection as _select_projection
from parallax.core.sql_gen._inheritance import tag_column as _tag_column
from parallax.core.sql_gen._inheritance import tag_guard as _tph_tag_guard
from parallax.core.sql_gen._inheritance import (
    transform_structured_column as _transform_structured_column,
)

# The predicate lane: an entity resolution scope in, one `where`-clause fragment
# out, with this statement's binds pushed on the shared context in order. Same
# aliasing-down convention as the family lane above.
from parallax.core.sql_gen._predicate import EntityScope as _EntityScope
from parallax.core.sql_gen._predicate import lower_predicate as _lower_predicate
from parallax.core.storage_layout import DirectColumn as _DirectColumn
from parallax.core.storage_layout import DocumentPath as _DocumentPath
from parallax.core.storage_layout import StorageLayoutFacet as _StorageLayoutFacet
from parallax.core.storage_layout import TableLayout as _TableLayout
from parallax.core.storage_layout import view as _storage_view
from parallax.core.wire import WireDecodingError, WireValue, decode_canonical_wire

__all__ = [
    "AttributeReadContract",
    "CompiledPredicate",
    "CompiledRead",
    "LoweredStatement",
    "MaterializedReadRow",
    "SqlGenError",
    "compile_read",
    "compile_write_predicate",
]

# The read's consumption lane (m-sql *Read projection*, *Result form*): a
# ``row``-form read (the values lane) projects scalars only by default, with an
# explicit materializing-write override for required documents; an ``instance``-form
# read (the object lane — a find / snapshot / deep-fetch whose rows materialize
# into instances) additionally projects the value-object document columns (slot 4).
# PRIVATE: `compile_read`'s ``result_form`` keyword and its semantics are part of
# the supported interface, but the alias naming them is not — a caller spells the
# two literals inline (`Literal["row", "instance"]`) rather than importing a name
# whose only job is to abbreviate them.
_ResultForm = Literal["row", "instance"]


@dataclass(frozen=True, slots=True)
class CompiledPredicate:
    """A compiled write predicate: an UNALIASED `where`-clause fragment
    (`balance < ?`, never `t0.balance < ?`) and its ordered binds.

    Deliberately NOT a :class:`LoweredStatement`: this is a predicate fragment,
    not a complete statement — the caller splices it into its own `update … where` /
    `delete from … where` template (`m-batch-write.md` "Predicate-selected
    readless forms").
    """

    sql: str
    binds: tuple[object, ...] = ()
    lowered: LoweredStatement | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class MaterializedReadRow:
    """One instance-form row with exact concrete identity and field provenance.

    ``values`` excludes the synthetic ``familyVariant`` key so a Value Object
    document column with that physical spelling remains intact. ``family_variant``
    is the optional wire/graph spelling and ``resolved_entity`` is always the exact
    accepted Entity Identity the row denotes.

    ``document`` is the raw Structured Column this row arrived with under
    Relational Document Layout, kept beside ``values`` for the same reason
    ``family_variant`` is: it is provenance rather than a field, and the fan-out
    drops it from the values a result form renders. Absent for every read that
    projected no Structured Column. ``findings`` and ``family_tag_unknown`` are
    classified provenance that a consumer must propagate to publication;
    ``classified_members`` names values already judged by the document codec so
    conversion translates them without judging their synthesized collapse again.
    """

    values: dict[str, object]
    resolved_entity: EntityIdentity
    family_variant: str | None
    document: object | None = None
    findings: tuple[DocumentFinding, ...] = ()
    family_tag_unknown: bool = False
    classified_members: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class AttributeReadContract:
    """One projected Attribute's logical, physical, and driver-result contract."""

    identity: AttributeIdentity
    column: str
    result_key: str
    type: NeutralType
    nullable: bool
    temporal_end: bool
    encoded: bool


@dataclass(frozen=True, slots=True)
class CompiledRead:
    """One compiled read: its :class:`LoweredStatement`, the root narrow to materialize
    under, and the row transform that materializes `familyVariant`.

    Self-contained by design: everything a caller needs to turn driver rows into
    observed rows travels WITH the compiled statement. The flat lane publishes a
    transformed row through :meth:`transform_row`; every materializing consumer —
    the typed and wire snapshot lanes and the write lanes alike — uses
    :meth:`materialize_row`, row conversion, and the staging graph its own lane
    classifies or refuses. Neither re-derives what the statement projected.

    ``narrow_to`` is the read's own query-wide narrowing or ``None`` for a bare read: a
    table-per-concrete-subtype position resolving to exactly one concrete emits
    no `familyVariant` column at all, so this is what lets
    :attr:`MaterializedReadRow.resolved_entity` still name the row's own concrete
    identity. A deep-fetch CHILD level takes its narrow from its own
    ``FetchLevel.narrow_to`` instead.

    ``documents`` is the top-level Value Object occurrences the resolved position
    can carry, in Position Layout order — the scalar/document provenance a
    materializing caller needs, carried here so no consumer re-projects a family
    superset of its own. It is a property of the POSITION, not of the result form
    or the layout: a default row-form read projects no document column, while the
    explicit materializing-write widening lane projects the documents it needs.
    An occurrence is just as much a member when the layout stores it inside a
    shared Structured Column rather than in one of its own. ``materialize_row`` is the metadata-
    preserving contract for graph and write consumers; ``transform_row`` is only
    for clean flat publication and refuses classified invalid state.
    ``projected_documents`` is the demand-specific subset the statement actually
    selected; conversion receives that subset so an unrequested occurrence is
    never judged merely because the position could have carried it.
    """

    statement: LoweredStatement
    narrow_to: tuple[EntityIdentity, ...] | None
    target: EntityIdentity
    resolved_position: tuple[EntityIdentity, ...]
    documents: tuple[ValueObjectMetadata, ...]
    projected_documents: tuple[ValueObjectMetadata, ...]
    document_reads: tuple[DocumentReadOrdinals, ...]
    _scalar_contracts: tuple[tuple[EntityIdentity, tuple[AttributeReadContract, ...]], ...] = field(
        repr=False
    )
    _transform: _RowTransform

    @property
    def structured_column(self) -> str | None:
        """The Structured Column this read projected, or absence when it projected
        none — under `Columns` layout, and for a `Document`-layout read whose
        members are all direct.

        The fan-out drops that column from a row's values, so a caller retaining
        the stored document (`m-unit-work`'s Predecessor Row) reads it by this name
        off the driver row rather than out of the transformed one.
        """
        return _transform_structured_column(self._transform)

    def transform_row(self, row: Mapping[str, object]) -> dict[str, object]:
        """Materialize one metadata-free row, refusing classified invalid state.

        Accepts any ``Mapping`` (a wire-rendered row or a raw driver row alike)
        and always returns a FRESH ``dict``, including when there is nothing to
        materialize.
        """
        materialized = self.materialize_row(row)
        if (
            materialized.findings
            or materialized.family_tag_unknown
            or self._has_invalid_direct_scalar(materialized)
        ):
            raise SqlGenError("a row carrying invalid stored data cannot be flattened")
        if materialized.family_variant is not None:
            if "familyVariant" in materialized.values:  # pragma: no cover - formation rejects it
                raise SqlGenError(
                    "a flat row cannot represent both a declared `familyVariant` field and "
                    "the polymorphic synthetic key; Model Formation should reject the collision"
                )
            materialized.values["familyVariant"] = materialized.family_variant
        return materialized.values

    def _has_invalid_direct_scalar(self, row: MaterializedReadRow) -> bool:
        contracts = dict(self._scalar_contracts).get(row.resolved_entity, ())
        for contract in contracts:
            if (
                contract.result_key not in row.values
                or contract.result_key in row.classified_members
            ):
                continue
            value = row.values[contract.result_key]
            if contract.encoded:
                try:
                    value = decode_canonical_wire(contract.type, cast("WireValue", value))
                except WireDecodingError:
                    return True
            if not admits_stored_scalar(
                value,
                contract.type,
                nullable=contract.nullable,
                temporal_end=contract.temporal_end,
            ):
                return True
        return False

    def attribute_reads(self, entity: EntityIdentity) -> tuple[AttributeReadContract, ...]:
        """The compiled Attribute contracts for one resolved concrete Entity."""
        return dict(self._scalar_contracts).get(entity, ())

    def materialize_row(self, row: Mapping[str, object]) -> MaterializedReadRow:
        """Resolve one driver row without flattening synthetic field provenance."""
        column = self.structured_column
        transformed = self._transform.materialize(row)
        values = transformed.values
        resolved = transformed.resolved_entity
        if resolved is None:
            resolved = (
                self.resolved_position[0] if len(self.resolved_position) == 1 else self.target
            )
        return MaterializedReadRow(
            values,
            resolved,
            transformed.family_variant,
            None if column is None else _observed_document(row.get(column)),
            transformed.findings,
            transformed.family_tag_unknown,
            transformed.classified_members,
        )


# --------------------------------------------------------------------------- #
# Projection.                                                                  #
# --------------------------------------------------------------------------- #
def _projection(
    entity: EntityMetadata,
    layout: _TableLayout,
    dialect: Dialect,
    alias: str,
    projected_vos: tuple[ValueObjectMetadata, ...],
    *,
    observation: bool,
) -> tuple[
    str,
    list[object],
    tuple[DocumentReadOrdinals, ...],
    _RowTransform,
]:
    """Render the resolved Value Object projection in canonical layout order.

    ``projected_vos`` is deep fetch's exact retained selection. ``observation`` requests
    the Structured Column needed for predecessor evidence even when no selected member
    occupies it. Neither choice is inferred from result form in this compiler.
    """

    columns = _select_projection(
        layout.columns,
        entity.declared_attributes,
        projected_vos,
        project_discriminator=False,
    )
    document, transform = _document_projection(
        layout, entity.declared_attributes, projected_vos, observation=observation
    )
    if document is not None:
        columns = (*columns, document)
    transform = _direct_document_transform(transform, ((entity.identity, layout, projected_vos),))
    sql, binds, document_reads = _render_projection(dialect, alias, columns)
    return sql, list(binds), document_reads, transform


def _scalar_read_contracts(
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    position: tuple[EntityIdentity, ...],
) -> tuple[tuple[EntityIdentity, tuple[AttributeReadContract, ...]], ...]:
    contracts: list[tuple[EntityIdentity, tuple[AttributeReadContract, ...]]] = []
    for identity in position:
        view = _entity_view(facet, identity)
        layout = _table_layout(storage, facet, identity)
        root = model.entity(view.root)
        temporal_ends: frozenset[AttributeIdentity] = (
            frozenset()
            if root is None
            else frozenset(axis.end_attribute for axis in root.declared_as_of_axes)
        )
        entity_contracts: list[AttributeReadContract] = []
        for attribute in view.applicable_attributes:
            direct = isinstance(layout.placement(attribute.identity), _DirectColumn)
            projected_key = projection_result_key(attribute.storage.name, attribute.type)
            entity_contracts.append(
                AttributeReadContract(
                    attribute.identity,
                    attribute.storage.name,
                    projected_key if direct else attribute.storage.name,
                    attribute.type,
                    attribute.nullable,
                    attribute.identity in temporal_ends,
                    direct and projected_key != attribute.storage.name,
                )
            )
        contracts.append(
            (
                identity,
                tuple(entity_contracts),
            )
        )
    return tuple(contracts)


# --------------------------------------------------------------------------- #
# compile_read = lower -> normalize.                                          #
# --------------------------------------------------------------------------- #
def compile_read(
    query: ValidatedEntityQuery,
    model: Metamodel,
    dialect: Dialect,
    *,
    result_form: _ResultForm = "row",
    lock: LockMode | None = None,
) -> CompiledRead:
    """Compile one resolved Entity Query into a self-contained read.

    ``result_form`` chooses only the materialization contract. Projection membership is
    already present on ``query``; ``lock`` is the caller-derived effective read lock.
    """

    target = query.entity
    facet = _inheritance_view(model)
    storage = _storage_view(model)
    predicate = query.validated_predicate
    order_keys = query.order_by
    limit = query.limit
    narrow_to = query.narrow_to
    if target.inheritance is not None:
        statement, plan_position, document_reads, transform = _compile_inheritance_read(
            target,
            predicate,
            narrow_to,
            order_keys,
            limit,
            model,
            facet,
            storage,
            dialect,
            result_form,
            lock,
        )
        position_documents = _position_documents(facet, storage, plan_position)
        return CompiledRead(
            statement,
            narrow_to,
            target.identity,
            plan_position,
            position_documents,
            position_documents if result_form == "instance" else (),
            document_reads,
            _scalar_read_contracts(model, facet, storage, dialect, plan_position),
            transform,
        )
    # One context per statement (the mutable accumulator), one resolution scope
    # over it (the immutable "what does a leaf resolve against" half).
    ctx = StatementBuilder(model, facet, storage, dialect)
    layout = _table_layout(storage, facet, target.identity)
    scope = _EntityScope(ctx, target, layout)

    proj_sql, proj_binds, document_reads, transform = _projection(
        target,
        layout,
        dialect,
        scope.alias,
        query.projection.value_objects,
        observation=query.projection.observe_structured_document,
    )
    ctx.bind_structural_all(proj_binds)
    select = f"select {proj_sql}"
    parts = [select, f"from {layout.table.name} {scope.alias}"]

    where_sql = _lower_predicate(predicate, scope)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, scope, order_keys, limit, lock)

    statement = _normalize(ctx.finish(" ".join(parts)))
    # A non-family read projects no tag and no variant literal, so the only
    # transform it can carry is the document fan-out its own projection decided.
    position = (target.identity,)
    position_documents = _position_documents(facet, storage, position)
    return CompiledRead(
        statement,
        narrow_to,
        target.identity,
        position,
        position_documents,
        query.projection.value_objects,
        document_reads,
        _scalar_read_contracts(model, facet, storage, dialect, position),
        transform,
    )


def compile_write_predicate(
    op: ValidatedPredicate, model: Metamodel, dialect: Dialect, target: EntityMetadata
) -> CompiledPredicate:
    """Render an unaliased, already-validated write predicate."""
    facet = _inheritance_view(model)
    storage = _storage_view(model)
    ctx = StatementBuilder(model, facet, storage, dialect)
    scope = _EntityScope(
        ctx, target, _table_layout(storage, facet, target.identity), unaliased=True
    )
    where_sql = _lower_predicate(op, scope)
    statement = ctx.finish(where_sql)
    return CompiledPredicate(
        statement.sql,
        statement.binds,
        statement,
    )


def _append_result_shape(
    parts: list[str],
    scope: _EntityScope,
    order_keys: tuple[ValidatedOrderTerm, ...],
    limit: int | None,
    lock: LockMode | None,
) -> None:
    """Append the shared ``order by`` / ``limit`` / read-lock tail (m-sql), used by
    every single-select read form (plain, table-per-hierarchy, and a
    table-per-concrete-subtype read resolving to one concrete).
    """
    if order_keys:
        # An authored key that omitted `direction` or `nulls` (serde `None`) lowers
        # to the schema defaults `asc` and `last`.
        terms = [_order_term(scope, key) for key in order_keys]
        parts.append("order by " + ", ".join(terms))
    if limit is not None:
        parts.append(scope.dialect.limit_clause())
        scope.ctx.bind_structural(limit)
    if lock == "locking":
        # The shared-row-lock suffix is the last thing in the statement (after any
        # `where` / `order by` / `limit`).
        parts.append(scope.dialect.read_lock_suffix(scope.alias))


def _order_term(scope: _EntityScope, key: ValidatedOrderTerm) -> str:
    """One ``order by`` term: the dialect's Null Placement term for a NULLABLE key,
    else the plain form (`m-sql` "``order by`` key terms").

    Placement is observationally irrelevant on a non-nullable key — there are no
    NULLs to place, so both placements denote the same order — and such a key
    therefore renders plain without consulting the dialect at all.

    An ordering key over a document-resident member lowers through the same
    extraction and typed-cast seams a predicate over it does (`m-sql`), which is
    what keeps one ordering answer the same under either layout: the six
    text-compared spellings order as their values do, and everything else orders
    inside the engine's own type system through the cast.
    """
    direction = key.direction
    column_sql = scope.subject_for(key.member).compared
    if key.member.nullable:
        return scope.dialect.null_order(column_sql, direction, key.nulls)
    return f"{column_sql} {direction}"


# --------------------------------------------------------------------------- #
# Inheritance-family reads                                                      #
# (m-sql "Metamodel-extension lowering — inheritance").                         #
#                                                                               #
# `_inheritance` resolves the read's queried POSITION and hands back an          #
# immutable plan; the three assemblers below are its only consumers. Each one   #
# constructs this statement's own `StatementBuilder` (a table-per-concrete-subtype union    #
# constructs one PER BRANCH, which is what restarts each branch at `t0`), splices #
# the plan's projection binds, lowers the plan's un-lowered `inner` predicate,   #
# and only THEN appends the tag guard's binds — the m-sql "Grouped branch        #
# predicates" order, stated explicitly at each site rather than left to an       #
# evaluation-order accident.                                                     #
# --------------------------------------------------------------------------- #
def _compile_inheritance_read(
    entity: EntityMetadata,
    predicate: ValidatedPredicate,
    narrow_to: tuple[EntityIdentity, ...] | None,
    order_keys: tuple[ValidatedOrderTerm, ...],
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    result_form: _ResultForm,
    lock: LockMode | None,
) -> tuple[
    LoweredStatement,
    tuple[EntityIdentity, ...],
    tuple[DocumentReadOrdinals, ...],
    _RowTransform,
]:
    """Assemble an inheritance-family read from its plan.

    Returns the statement AND its row transform together: whether a read carries
    `familyVariant` is decided by the very same resolved position that decides
    what it projects, so the two travel together on one plan.
    """
    plan = _plan_inheritance_read(
        entity,
        predicate.authored,
        narrow_to,
        model,
        facet,
        storage,
        result_form == "instance",
        lock,
    )
    match plan:
        case _TphPlan():
            statement, document_reads, transform = _compile_tph_read(
                plan,
                predicate,
                entity,
                order_keys,
                limit,
                model,
                facet,
                storage,
                dialect,
                lock,
            )
            return statement, plan.position, document_reads, transform
        case _TpcsSinglePlan():
            statement, document_reads, transform = _compile_tpcs_single(
                plan,
                predicate,
                entity,
                order_keys,
                limit,
                model,
                facet,
                storage,
                dialect,
                lock,
            )
            return statement, plan.position, document_reads, transform
        case _TpcsUnionPlan():
            statement, document_reads, transform = _compile_tpcs_read(
                plan, predicate, entity, order_keys, limit, model, facet, storage, dialect
            )
            return statement, plan.position, document_reads, transform
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(plan)


def _compile_tph_read(
    plan: _TphPlan,
    predicate: ValidatedPredicate,
    entity: EntityMetadata,
    order_keys: tuple[ValidatedOrderTerm, ...],
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    lock: LockMode | None,
) -> tuple[LoweredStatement, tuple[DocumentReadOrdinals, ...], _RowTransform]:
    """Assemble a table-per-hierarchy read: one shared correlated `EXISTS`-free
    single-table SELECT (m-sql "Inheritance — table-per-hierarchy lowering").

    Everything family-shaped — the resolved position, the tag-predicate kind, what
    is projected — is decided by :func:`_plan_inheritance_read`; this builds the
    statement's context and sequences the four bind phases.
    """
    ctx = StatementBuilder(model, facet, storage, dialect)
    scope = _EntityScope(
        ctx,
        entity,
        _table_layout(storage, facet, entity.identity),
        position=plan.position,
    )
    proj_sql, proj_binds, document_reads = plan.projection(dialect, scope.alias)
    ctx.bind_structural_all(proj_binds)

    select = f"select {proj_sql}"
    parts = [select, f"from {plan.table} {scope.alias}"]

    inner_sql = _lower_predicate(_planned_inner(predicate, plan.inner), scope)
    where_terms = [inner_sql] if inner_sql else []
    if plan.tag is not None:
        # Planned, then bound HERE — after the user predicate above has pushed its
        # own binds (m-sql "Grouped branch predicates": branch-predicate-first,
        # then tag).
        tag_sql, tag_binds = _tph_tag_guard(scope, facet, plan.tag)
        where_terms.append(tag_sql)
        ctx.bind_framework_all(tag_binds)
    if where_terms:
        parts.append("where " + " and ".join(where_terms))

    _append_result_shape(parts, scope, order_keys, limit, lock)
    if ctx.requires_variant_partition:
        return (
            *_compile_tph_partitioned(
                plan,
                predicate,
                entity,
                order_keys,
                limit,
                model,
                facet,
                storage,
                dialect,
                lock,
            ),
            plan.transform,
        )
    statement = _normalize(ctx.finish(" ".join(parts)))
    return statement, document_reads, plan.transform


def _compile_tph_partitioned(
    plan: _TphPlan,
    predicate: ValidatedPredicate,
    entity: EntityMetadata,
    order_keys: tuple[ValidatedOrderTerm, ...],
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    lock: LockMode | None,
) -> tuple[LoweredStatement, tuple[DocumentReadOrdinals, ...]]:
    """Assemble one tag-disjoint branch per selected TPH document variant."""
    branch_sqls: list[str] = []
    branches: list[LoweredStatement] = []
    layout = _table_layout(storage, facet, entity.identity)
    key_columns = tuple(slot.column.name for slot in layout.physical_primary_key)
    for branch_index, concrete in enumerate(plan.position):
        branch_ctx = StatementBuilder(model, facet, storage, dialect)
        base_scope = _EntityScope(
            branch_ctx,
            entity,
            layout,
            alias=f"t{branch_index + 1}" if lock is not None else "t0",
            position=plan.position,
            variant=concrete,
        )
        tag = _TagPredicate(
            _tag_column(layout, _entity_view(facet, entity.identity).root),
            (concrete,),
        )
        tag_sql, tag_binds = _tph_tag_guard(base_scope, facet, tag)
        tagged_alias = f"p{branch_index + 1}"
        fence_sql, fence_binds = dialect.optimizer_fence()
        tagged = f"select * from {plan.table} {base_scope.alias} where {tag_sql} {fence_sql}"
        branch_scope = _EntityScope(
            branch_ctx,
            entity,
            layout,
            alias=tagged_alias,
            position=plan.position,
            variant=concrete,
        )
        if lock is not None:
            projection = ", ".join(
                dialect.qualified(branch_scope.alias, column) for column in key_columns
            )
        else:
            projection, projection_binds, _branch_document_reads = plan.projection(
                dialect,
                branch_scope.alias,
                document_pairs=not order_keys and limit is None,
            )
            branch_ctx.bind_structural_all(projection_binds)
        branch_ctx.bind_framework_all(tag_binds)
        branch_ctx.bind_framework_all(fence_binds)
        inner = _lower_predicate(_planned_inner(predicate, plan.inner), branch_scope)
        parts = [f"select {projection}", f"from ({tagged}) {tagged_alias}"]
        if inner:
            parts.append(f"where {inner}")
        branch_sql = " ".join(parts)
        branch_sqls.append(branch_sql)
        branches.append(branch_ctx.finish(branch_sql))

    union = " union all ".join(branch_sqls)
    if lock is not None:
        statement_ctx = StatementBuilder(model, facet, storage, dialect)
        outer_scope = _EntityScope(
            statement_ctx,
            entity,
            layout,
            position=plan.position,
        )
        projection, projection_binds, document_reads = plan.projection(dialect, outer_scope.alias)
        statement_ctx.bind_structural_all(projection_binds)
        join_terms = " and ".join(
            f"{dialect.qualified('u', column)} = {dialect.qualified(outer_scope.alias, column)}"
            for column in key_columns
        )
        parts = [
            f"select {projection}",
            f"from {plan.table} {outer_scope.alias}",
            f"join ({union}) u on {join_terms}",
        ]
        for branch in branches:
            statement_ctx.append_fragment(branch)
        _append_result_shape(parts, outer_scope, order_keys, limit, lock)
        return _normalize(statement_ctx.finish(" ".join(parts))), document_reads

    if not order_keys and limit is None:
        _projection, _projection_binds, document_reads = plan.projection(dialect, "t0")
        statement_ctx = StatementBuilder(model, facet, storage, dialect)
        for branch in branches:
            statement_ctx.append_fragment(branch)
        return _normalize(statement_ctx.finish(union)), document_reads

    statement_ctx = StatementBuilder(model, facet, storage, dialect)
    outer_scope = _EntityScope(
        statement_ctx,
        entity,
        layout,
        alias="u",
        position=plan.position,
    )
    projection, projection_binds, document_reads = plan.projection(dialect, outer_scope.alias)
    statement_ctx.bind_structural_all(projection_binds)
    parts = [
        f"select {projection}",
        f"from ({union}) {outer_scope.alias}",
    ]
    for branch in branches:
        statement_ctx.append_fragment(branch)
    _append_result_shape(parts, outer_scope, order_keys, limit, None)
    return _normalize(statement_ctx.finish(" ".join(parts))), document_reads


def _compile_tpcs_read(
    plan: _TpcsUnionPlan,
    predicate: ValidatedPredicate,
    entity: EntityMetadata,
    order_keys: tuple[ValidatedOrderTerm, ...],
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
) -> tuple[LoweredStatement, tuple[DocumentReadOrdinals, ...], _RowTransform]:
    """Assemble a table-per-concrete-subtype `union all` read (m-sql "Inheritance —
    table-per-concrete-subtype lowering").

    Each branch gets a FRESH ``StatementBuilder``: that is the whole mechanism behind a branch
    restarting its own alias scheme at `t0`, and behind the per-branch binds being
    separable so they concatenate in the plan's canonical branch order.

    A `union all` has no clause tail of its own, so an ordered or limited read
    wraps it as the derived table ``u`` and applies the tail against the union's
    own result aliases — the shape a table-per-hierarchy partitioned read already
    uses. The caller's predicate still lowers INSIDE each branch, where the branch
    layout is what resolves a member's column; only the result-shape tail moves
    outward. An unordered, uncapped read emits the bare union, unchanged.
    """
    wrapped = bool(order_keys) or limit is not None
    branch_sqls: list[str] = []
    branch_statements: list[LoweredStatement] = []
    document_reads: tuple[DocumentReadOrdinals, ...] | None = None
    for branch in plan.branches:
        branch_ctx = StatementBuilder(model, facet, storage, dialect)
        branch_scope = _EntityScope(
            branch_ctx,
            entity,
            _table_layout(storage, facet, branch.identity),
            position=plan.position,
            variant=branch.identity,
        )
        proj_sql, proj_binds, branch_document_reads = branch.projection(
            dialect, branch_scope.alias, document_pairs=not wrapped
        )
        if document_reads is None:
            document_reads = branch_document_reads
        elif document_reads != branch_document_reads:  # pragma: no cover - aligned union invariant
            raise SqlGenError("table-per-concrete-subtype branches disagree on document ordinals")
        branch_ctx.bind_structural_all(proj_binds)
        parts = [f"select {proj_sql}", f"from {branch.table} {branch_scope.alias}"]
        where_sql = _lower_predicate(_planned_inner(predicate, plan.inner), branch_scope)
        if where_sql:
            parts.append(f"where {where_sql}")
        branch_sql = " ".join(parts)
        branch_sqls.append(branch_sql)
        branch_statements.append(branch_ctx.finish(branch_sql))

    union = " union all ".join(branch_sqls)
    if not wrapped:
        statement_ctx = StatementBuilder(model, facet, storage, dialect)
        for branch in branch_statements:
            statement_ctx.append_fragment(branch)
        statement = _normalize(statement_ctx.finish(union))
        return statement, document_reads or (), plan.transform

    outer_ctx = StatementBuilder(model, facet, storage, dialect)
    outer_scope = _EntityScope(
        outer_ctx,
        entity,
        _table_layout(storage, facet, plan.branches[0].identity),
        alias="u",
        position=plan.position,
    )
    projection, _projection_binds, outer_document_reads = plan.projection(
        dialect, outer_scope.alias
    )
    outer_parts = [f"select {projection}", f"from ({union}) {outer_scope.alias}"]
    if order_keys:
        terms = [_tpcs_order_term(plan, outer_scope, key) for key in order_keys]
        outer_parts.append("order by " + ", ".join(terms))
    if limit is not None:
        outer_parts.append(dialect.limit_clause())
        outer_ctx.bind_structural(limit)
    statement_ctx = StatementBuilder(model, facet, storage, dialect)
    for branch in branch_statements:
        statement_ctx.append_fragment(branch)
    statement_ctx.append_fragment(outer_ctx.finish(""))
    statement = _normalize(statement_ctx.finish(" ".join(outer_parts)))
    return statement, outer_document_reads, plan.transform


def _tpcs_order_term(plan: _TpcsUnionPlan, scope: _EntityScope, key: ValidatedOrderTerm) -> str:
    """One ``order by`` term measured against a wrapped union's result alias.

    One thing differs from :func:`_order_term`: a member is named by the result
    alias every branch projects it under rather than by any one branch's physical
    spelling, because the union is the ordered relation and a colliding spelling
    reaches it only through its allocated alias.

    Nullability is the ordinary declared one. The positional rule (`m-object-query`)
    admits a Sort Key only over a member applicable to every concrete in the active
    position, so a legal key is owned by every branch and never meets that branch's
    typed `NULL` placeholder.
    """
    attribute = key.member
    direction = key.direction
    term = _tpcs_order_subject(plan, scope, attribute)
    if attribute.nullable:
        return scope.dialect.null_order(term, direction, key.nulls)
    return f"{term} {direction}"


def _tpcs_order_subject(
    plan: _TpcsUnionPlan, scope: _EntityScope, attribute: AttributeMetadata
) -> str:
    """The expression a wrapped union's ordering key compares, against the union alias.

    Member Placement decides which contributor the union column belongs to, exactly
    as it does inside a branch: a `DirectColumn` member claims its own, while a
    `DocumentPath` member claims none and rides the slot the placement names. A
    Relational Document Layout is declared by the family root, so every branch
    places such a member at the same path inside the one Structured Column the union
    projects, and the extraction is built once here rather than per branch.
    """
    placement = scope.layout.placement(attribute.identity)
    document = placement if isinstance(placement, _DocumentPath) else None
    column = plan.column_of(attribute.identity if document is None else document.slot.contributor)
    reference = scope.dialect.qualified(scope.alias, column.result_alias)
    if document is None:
        return reference
    extraction, path_binds = scope.dialect.nested_extract(reference, document.path)
    scope.ctx.bind_structural_all(path_binds)
    return scope.dialect.nested_cast(extraction, attribute.type)


def _compile_tpcs_single(
    plan: _TpcsSinglePlan,
    predicate: ValidatedPredicate,
    entity: EntityMetadata,
    order_keys: tuple[ValidatedOrderTerm, ...],
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    lock: LockMode | None,
) -> tuple[LoweredStatement, tuple[DocumentReadOrdinals, ...], _RowTransform]:
    """Assemble a table-per-concrete-subtype read resolving to exactly one
    concrete: an ordinary single-table read of that subtype's own table, no tag,
    no union, no `familyVariant` — attribute resolution still widens across the
    family (the RESOLUTION SCOPE's entity stays the read's own queried `target`,
    e.g. an abstract position narrowed down to this one concrete, so
    :meth:`_EntityScope._searchable_attributes` searches the whole family rather
    than only that entity's own declared attributes), matching the
    table-per-hierarchy concrete-target form.

    Like :func:`_compile_tph_read` this builds the statement's context and
    sequences its bind phases explicitly — here projection, then user predicate,
    then limit; there is no framework tag guard on this lane.
    """
    ctx = StatementBuilder(model, facet, storage, dialect)
    scope = _EntityScope(ctx, entity, _table_layout(storage, facet, plan.position[0]))
    proj_sql, proj_binds, document_reads = plan.projection(dialect, scope.alias)
    ctx.bind_structural_all(proj_binds)
    select = f"select {proj_sql}"
    parts = [select, f"from {plan.table} {scope.alias}"]
    where_sql = _lower_predicate(_planned_inner(predicate, plan.inner), scope)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, scope, order_keys, limit, lock)
    statement = _normalize(ctx.finish(" ".join(parts)))
    return statement, document_reads, plan.transform


def _planned_inner(predicate: ValidatedPredicate, planned: object) -> ValidatedPredicate:
    """Map a plan's top-level narrow interception back to its occurrence product."""
    if planned is predicate.authored:
        return predicate
    if isinstance(predicate.authored, Narrow) and planned is predicate.authored.operand:
        return predicate.only_child()
    raise SqlGenError("an inheritance plan replaced rather than selected its validated predicate")


# --------------------------------------------------------------------------- #
# Normalization (fixed-point identity check).                                 #
# --------------------------------------------------------------------------- #
def _normalize(statement: LoweredStatement) -> LoweredStatement:
    """Assert the emitted SQL is already the m-sql canonical fixed point.

    The compiler emits canonical form directly (single-space separation,
    lowercase keywords, alias-qualified columns), so normalization is the
    idempotence check the m-sql contract fixes rather than a rewrite. A stray
    double space would mean a lowering bug, so it is collapsed and asserted.
    """
    collapsed = " ".join(statement.sql.split())
    if collapsed != statement.sql:  # pragma: no cover - defends against a lowering bug
        raise SqlGenError(f"emitted SQL is not canonical: {statement.sql!r}")
    return statement
