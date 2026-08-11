"""The three-stage read compiler (m-sql): canonicalize -> lower -> normalize.

``compile_read`` turns an ``m-op-algebra`` operation into one canonical
``LoweredStatement`` for a dialect. Lowering descends through `_predicate`'s one
dispatcher (no visitor framework — see the third paragraph); the dialect strategy
supplies every dialect-specific string. The emitted SQL is produced directly in
canonical normalized form (alias-qualified columns, lowercase, single-space
separated, canonical clause order), so ``normalize`` is a fixed-point identity
check rather than a rewrite — the language target never depends on the reference harness's
sqlglot normalizer (non-normative). Temporal reads are canonicalized upstream by
``m-temporal-read`` (``inject_as_of``) into ordinary predicate nodes before they
reach this compiler; deep fetch (`DeepFetch`) is planned by `m-deep-fetch` into
one read per relationship level and is never a predicate, so reaching this
compiler as one raises a clear :class:`SqlGenError` and a mis-routed case fails
loudly, never silently.

Inheritance-family reads (table-per-hierarchy tag predicates / abstract-read
superset projection, table-per-concrete-subtype union-all) are ASSEMBLED here
(`m-sql` "Metamodel-extension lowering") from plans
`_inheritance` resolves — which is where the `parallax.core.inheritance` edge
lives, a legal one since `modules.md` already reaches `m-inheritance`
transitively through `m-op-algebra`. `validate_operation` runs upstream (the
conformance engine / statement frontend), so a narrow reaching this compiler is
already known position-valid; nothing in this package re-validates it.

Predicate lowering itself is NOT here. `_predicate` owns every descent into an
operation — the scalar vocabulary, navigation, value-object traversal, and the
mid-predicate `narrow` — behind one entry point (`lower_predicate`) taking an
immutable resolution scope. This module builds each statement's scope, calls
that entry point for the read's own predicate (per `union all` branch, where
there is one), and assembles the clause tail around the fragment it returns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, assert_never

from parallax.core.dialect import Dialect, LockMode
from parallax.core.inheritance import InheritanceFacet
from parallax.core.inheritance import view as _inheritance_view
from parallax.core.metamodel import (
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    ValueObjectMetadata,
)
from parallax.core.op_algebra import (
    Limit,
    Narrow,
    Operation,
    OrderBy,
    OrderKey,
)
from parallax.core.sql_gen._context import Ctx as _Ctx
from parallax.core.sql_gen._context import SqlGenError
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
from parallax.core.sql_gen._inheritance import document_projection as _document_projection
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
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
from parallax.core.storage_layout import StorageLayoutFacet as _StorageLayoutFacet
from parallax.core.storage_layout import TableLayout as _TableLayout
from parallax.core.storage_layout import view as _storage_view

__all__ = [
    "CompiledPredicate",
    "CompiledRead",
    "LoweredStatement",
    "MaterializedReadRow",
    "SqlGenError",
    "compile_read",
    "compile_write_predicate",
]

# The read's consumption lane (m-sql *Read projection*, *Result form*): a
# ``row``-form read (the values lane) projects scalars only; an ``instance``-form
# read (the object lane — a find / snapshot / deep-fetch whose rows materialize
# into instances) additionally projects the value-object document columns (slot 4).
# PRIVATE: `compile_read`'s ``result_form`` keyword and its semantics are part of
# the supported interface, but the alias naming them is not — a caller spells the
# two literals inline (`Literal["row", "instance"]`) rather than importing a name
# whose only job is to abbreviate them.
_ResultForm = Literal["row", "instance"]


@dataclass(frozen=True, slots=True)
class LoweredStatement:
    """One compiled SQL statement in canonical form and its ordered binds."""

    sql: str
    binds: tuple[object, ...] = ()


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
    projected no Structured Column.
    """

    values: dict[str, object]
    resolved_entity: EntityIdentity
    family_variant: str | None
    document: object | None = None


@dataclass(frozen=True, slots=True)
class CompiledRead:
    """One compiled read: its :class:`LoweredStatement`, the root narrow to materialize
    under, and the row transform that materializes `familyVariant`.

    Self-contained by design: everything a caller needs to turn driver
    rows into observed rows travels WITH the compiled statement, so the two
    execution lanes (the conformance engine's flat wire rows and the production
    snapshot find executor's instance-form graph rows) each shrink to "compile,
    execute, transform" and can no longer drift from what was actually
    projected.

    ``narrow_to`` is the read's own TOP-LEVEL authored narrow (its ``Narrow.to``,
    result-shaping directives peeled) or ``None`` for a bare read: a
    table-per-concrete-subtype position resolving to exactly one concrete emits
    no `familyVariant` column at all, so this is what lets
    :attr:`MaterializedReadRow.resolved_entity` still name the row's own concrete
    identity. A deep-fetch CHILD level takes its narrow from its own
    ``FetchLevel.narrow_to`` instead.

    ``documents`` is the top-level Value Object occurrences the resolved position
    can carry, in Position Layout order — the scalar/document provenance a
    materializing caller needs, carried here so no consumer re-projects a family
    superset of its own. It is a property of the POSITION, not of the result form
    or the layout: a row-form read projects no document column, yet its rows
    still render every applicable document key as absent, and an occurrence is
    just as much a member when the layout stores it inside a shared Structured
    Column rather than in one of its own.
    """

    statement: LoweredStatement
    narrow_to: tuple[str, ...] | None
    target: EntityIdentity
    resolved_position: tuple[EntityIdentity, ...]
    documents: tuple[ValueObjectMetadata, ...]
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
        """Materialize `familyVariant` on one observed row.

        Accepts any ``Mapping`` (a wire-rendered row or a raw driver row alike)
        and always returns a FRESH ``dict``, including when there is nothing to
        materialize.
        """
        materialized = self.materialize_row(row)
        if materialized.family_variant is not None:
            if "familyVariant" in materialized.values:  # pragma: no cover - formation rejects it
                raise SqlGenError(
                    "a flat row cannot represent both a declared `familyVariant` field and "
                    "the polymorphic synthetic key; Model Formation should reject the collision"
                )
            materialized.values["familyVariant"] = materialized.family_variant
        return materialized.values

    def materialize_row(self, row: Mapping[str, object]) -> MaterializedReadRow:
        """Resolve one driver row without flattening synthetic field provenance."""
        column = self.structured_column
        values, resolved, family_variant = self._transform.materialize(row)
        if resolved is None:
            resolved = (
                self.resolved_position[0] if len(self.resolved_position) == 1 else self.target
            )
        return MaterializedReadRow(
            values, resolved, family_variant, None if column is None else row.get(column)
        )


# --------------------------------------------------------------------------- #
# Projection.                                                                  #
# --------------------------------------------------------------------------- #
def _projection(
    entity: EntityMetadata,
    layout: _TableLayout,
    dialect: Dialect,
    alias: str,
    result_form: _ResultForm,
    *,
    include_value_objects: bool | frozenset[str] = False,
) -> tuple[str, list[object], _RowTransform]:
    """The base read projection (m-sql *Read projection*), a function of the model.

    The Entity's own Table Layout fixes the whole order — `Identity`,
    `Domain`, `Temporal`, `Audit`, then `Document`, stable in declaration order
    inside each tier — and this selects from it. Every applicable scalar slot is
    projected, and the dialect maps each to its select-list expression (a `bytes`
    column projects `encode(col, ?)`; every other column its plain reference).
    The framework-owned inheritance discriminator and `familyVariant` are never
    reached here: an inheritance-family read is built by
    :func:`_compile_tph_read` / :func:`_compile_tpcs_read`.

    An **instance-form** read (the object lane) additionally projects the
    `Document` slots — a json document is always a plain alias-qualified
    reference — so a value-object-bearing entity's whole document rides the
    owner's single statement (the one-round-trip materialization contract,
    m-value-object). A row-form read omits them by default.

    ``include_value_objects`` opts a **row-form** read into the `Document` slots
    too, WITHOUT becoming instance-form (`m-case-format` *Predicate-selected
    write instruction*): a materializing predicate write's own internal
    resolving read stays row-form (it constructs no instance) but still needs
    the raw VO document(s) the observation it records, or its own no-op
    comparison, must read — the caller (the materializing predicate-write
    resolve in `parallax.snapshot.handle`) derives this from the write's own
    needs, never from `result_form`. ``True`` projects EVERY declared value
    object (a temporal target, whose Predecessor Row is complete and whose
    carried rows keep whichever documents the assignments do NOT themselves
    reassign); a ``frozenset`` of value-object NAMES projects ONLY those (a
    versioned target's comparison-only need — minimal-read discipline,
    `m-sql`) — in EITHER case the layout's `Document` slot order is preserved,
    never the caller's own set iteration order.

    The third result is the read's own row transform. Under Relational Document
    Layout the members selected above may live inside the Table's one shared
    Structured Column, which is then projected once, last, and fanned back out
    per row; under `Columns` layout none of them does, so the select list is
    unchanged and the transform is the identity.

    The two lanes that widen to every declared member — instance-form and
    ``include_value_objects is True`` — are also the OBSERVATION lane, and they
    project that Structured Column wherever the Table has one, even where no
    member lives inside it: what such a read observes includes the stored
    document a Predecessor Row retains (`m-sql` *Read projection*, rule 5).
    """
    declared_vos = entity.declared_value_objects
    observation = result_form == "instance" or include_value_objects is True
    if observation:
        projected_vos = tuple(declared_vos)
    elif isinstance(include_value_objects, frozenset):
        projected_vos = tuple(
            member for member in declared_vos if member.identity.path[-1] in include_value_objects
        )
    else:
        projected_vos = ()
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
    sql, binds = _render_projection(dialect, alias, columns)
    return sql, list(binds), transform


# --------------------------------------------------------------------------- #
# compile_read = canonicalize -> lower -> normalize.                          #
# --------------------------------------------------------------------------- #
def compile_read(
    op: Operation,
    model: Metamodel,
    dialect: Dialect,
    target: EntityMetadata,
    *,
    result_form: _ResultForm = "row",
    lock: LockMode | None = None,
    include_value_objects: bool | frozenset[str] = False,
) -> CompiledRead:
    """Compile a read operation to one self-contained :class:`CompiledRead`.

    ``target`` is the queried Entity's accepted Metadata, taken from ``model``:
    the caller already resolved which position it is reading, so this compiler
    never re-resolves a name against the model.

    The result carries everything the caller needs to consume the read's rows —
    the canonical ``LoweredStatement`` for ``dialect``, the root ``narrow_to`` to
    materialize under, and :meth:`CompiledRead.transform_row` — so no caller
    re-derives `familyVariant` or narrowing from the operation a second time.

    ``result_form`` selects the projection lane (m-sql *Read projection*): a
    **row-form** read (the values lane — the corpus predicate `read` cases and the
    internal materialized-write resolving read) projects scalars only; an
    **instance-form** read (the object lane — a find / snapshot / deep-fetch whose
    rows materialize into instances) additionally projects the value-object document
    columns. The conformance engine derives it from the case's asserted result
    member (`then.rows` = row-form; `then.graph` / `then.graphs` = instance-form).

    ``include_value_objects`` opts a **row-form** read into the value-object
    document columns too, independent of ``result_form`` (`m-case-format`
    *Predicate-selected write instruction* — a materializing predicate write's
    own resolving read projects need-sensitively, on EVERY target class):
    ``True`` projects every declared document (a temporal target, whose
    observation retains a complete Predecessor Row and whose carried rows keep
    whichever documents an assignment-bearing verb does NOT itself reassign);
    a ``frozenset`` of value-object NAMES projects ONLY those (a versioned
    target's own per-row no-op comparison need — minimal-read discipline,
    never every declared document). An inheritance-family target never reaches this flag (a
    predicate-selected write on a family is rejected before this compiler,
    `m-inheritance`), so it is not threaded into the inheritance lowering
    below.

    ``lock`` renders the transactional read-lock suffix (m-sql *Read-lock suffix*,
    applied through the m-dialect seam): an in-transaction **object find** in
    ``locking`` mode appends the dialect's shared-row-lock suffix (Postgres
    ``for share of t0``) after every other clause; ``optimistic`` mode and the
    default (``None`` — a non-transactional read) append nothing. Grouped / aggregate
    reads are not yet reachable. The conformance scenario runner derives ``lock``
    from the step's unit of work concurrency mode.
    """
    facet = _inheritance_view(model)
    storage = _storage_view(model)
    predicate, order_keys, limit = _peel_directives(op)
    # The read's own TOP-LEVEL authored narrow, taken from the SAME peel the
    # lowering below uses — so what the caller materializes under can never
    # disagree with what was compiled.
    narrow_to = predicate.to if isinstance(predicate, Narrow) else None
    if target.inheritance is not None:
        statement, plan_position, transform = _compile_inheritance_read(
            target,
            predicate,
            order_keys,
            limit,
            model,
            facet,
            storage,
            dialect,
            result_form,
            lock,
        )
        return CompiledRead(
            statement,
            narrow_to,
            target.identity,
            plan_position,
            _position_documents(facet, storage, plan_position),
            transform,
        )
    # One context per statement (the mutable accumulator), one resolution scope
    # over it (the immutable "what does a leaf resolve against" half).
    ctx = _Ctx(model, facet, storage, dialect)
    layout = _table_layout(storage, facet, target.identity)
    scope = _EntityScope(ctx, target, layout)

    proj_sql, proj_binds, transform = _projection(
        target,
        layout,
        dialect,
        scope.alias,
        result_form,
        include_value_objects=include_value_objects,
    )
    ctx.binds.extend(proj_binds)
    select = f"select {proj_sql}"
    parts = [select, f"from {layout.table.name} {scope.alias}"]

    where_sql = _lower_predicate(predicate, scope)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, scope, order_keys, limit, lock)

    statement = _normalize(LoweredStatement(" ".join(parts), tuple(ctx.binds)))
    # A non-family read projects no tag and no variant literal, so the only
    # transform it can carry is the document fan-out its own projection decided.
    return CompiledRead(
        statement,
        narrow_to,
        target.identity,
        (target.identity,),
        _position_documents(facet, storage, (target.identity,)),
        transform,
    )


def compile_write_predicate(
    op: Operation, model: Metamodel, dialect: Dialect, target: EntityMetadata
) -> CompiledPredicate:
    """Render a BARE write predicate (`m-batch-write.md` "Predicate-selected
    readless forms"): the UNALIASED where-clause SQL and its ordered binds —
    `balance < ?`, never the resolving read's aliased `t0.balance < ?`.

    Reuses the op-algebra predicate lowering (`_predicate.lower_predicate`) with
    an unaliased column formatter (:attr:`_EntityScope.unaliased`) rather than
    forking SQL text assembly — the same `And`/`Or`/`Group`/`Comparison`/...
    dispatch a read's `where` clause lowers through, so a write's rendered
    predicate can never drift from the read compiler's own operator vocabulary.
    ``op`` MUST be a bare predicate (no result-shaping directive survives here —
    a set-based write target is validated bare upstream, `m-unit-work`
    write-instruction vocabulary / `python.md` §5 bare-statement guard); a
    directive reaching this raises :class:`SqlGenError` exactly as it would
    inside an ordinary read's predicate.
    """
    facet = _inheritance_view(model)
    storage = _storage_view(model)
    ctx = _Ctx(model, facet, storage, dialect)
    scope = _EntityScope(
        ctx, target, _table_layout(storage, facet, target.identity), unaliased=True
    )
    where_sql = _lower_predicate(op, scope)
    return CompiledPredicate(where_sql, tuple(ctx.binds))


def _append_result_shape(
    parts: list[str],
    scope: _EntityScope,
    order_keys: tuple[OrderKey, ...],
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
        scope.ctx.bind(limit)
    if lock == "locking":
        # The shared-row-lock suffix is the last thing in the statement (after any
        # `where` / `order by` / `limit`).
        parts.append(scope.dialect.read_lock_suffix(scope.alias))


def _order_term(scope: _EntityScope, key: OrderKey) -> str:
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
    direction = key.direction or "asc"
    column_sql = scope.subject_of(key.attr).compared
    if scope.entity_attribute(key.attr).nullable:
        return scope.dialect.null_order(column_sql, direction, key.nulls or "last")
    return f"{column_sql} {direction}"


def _peel_directives(op: Operation) -> tuple[Operation, tuple[OrderKey, ...], int | None]:
    """Strip result-shaping directives (any nesting) into canonical clause data.

    A read carries at most one of each directive. A directive kind stacked twice
    (`limit(limit(…))`) has no defined composition in `m-op-algebra` — the spec
    fixes only that a directive wraps one inner operation — so a repeated kind is
    refused loudly here rather than silently overwriting the outer clause.
    """
    order_keys: tuple[OrderKey, ...] = ()
    limit: int | None = None
    seen: set[str] = set()
    current = op
    while True:
        match current:
            case Limit(operand=operand, count=count):
                _reject_stacked("limit", seen)
                limit = count
                current = operand
            case OrderBy(operand=operand, keys=keys):
                _reject_stacked("orderBy", seen)
                order_keys = keys
                current = operand
            case _:
                return current, order_keys, limit


def _reject_stacked(kind: str, seen: set[str]) -> None:
    if kind in seen:
        raise SqlGenError(
            f"stacked `{kind}` directives have no defined composition semantics "
            "(m-op-algebra directives wrap one inner operation); refusing rather than "
            "silently overwriting the outer clause"
        )
    seen.add(kind)


# --------------------------------------------------------------------------- #
# Inheritance-family reads                                                      #
# (m-sql "Metamodel-extension lowering — inheritance").                         #
#                                                                               #
# `_inheritance` resolves the read's queried POSITION and hands back an          #
# immutable plan; the three assemblers below are its only consumers. Each one   #
# constructs this statement's own `_Ctx` (a table-per-concrete-subtype union    #
# constructs one PER BRANCH, which is what restarts each branch at `t0`), splices #
# the plan's projection binds, lowers the plan's un-lowered `inner` predicate,   #
# and only THEN appends the tag guard's binds — the m-sql "Grouped branch        #
# predicates" order, stated explicitly at each site rather than left to an       #
# evaluation-order accident.                                                     #
# --------------------------------------------------------------------------- #
def _compile_inheritance_read(
    entity: EntityMetadata,
    predicate: Operation,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    result_form: _ResultForm,
    lock: LockMode | None,
) -> tuple[LoweredStatement, tuple[EntityIdentity, ...], _RowTransform]:
    """Assemble an inheritance-family read from its plan.

    Returns the statement AND its row transform together: whether a read carries
    `familyVariant` is decided by the very same resolved position that decides
    what it projects, so the two travel together on one plan.
    """
    plan = _plan_inheritance_read(
        entity,
        predicate,
        order_keys,
        limit,
        model,
        facet,
        storage,
        result_form == "instance",
        lock,
    )
    match plan:
        case _TphPlan():
            statement, transform = _compile_tph_read(
                plan,
                entity,
                order_keys,
                limit,
                model,
                facet,
                storage,
                dialect,
                lock,
            )
            return statement, plan.position, transform
        case _TpcsSinglePlan():
            statement, transform = _compile_tpcs_single(
                plan,
                entity,
                order_keys,
                limit,
                model,
                facet,
                storage,
                dialect,
                lock,
            )
            return statement, plan.position, transform
        case _TpcsUnionPlan():
            statement, transform = _compile_tpcs_read(plan, entity, model, facet, storage, dialect)
            return statement, plan.position, transform
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(plan)


def _compile_tph_read(
    plan: _TphPlan,
    entity: EntityMetadata,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    lock: LockMode | None,
) -> tuple[LoweredStatement, _RowTransform]:
    """Assemble a table-per-hierarchy read: one shared correlated `EXISTS`-free
    single-table SELECT (m-sql "Inheritance — table-per-hierarchy lowering").

    Everything family-shaped — the resolved position, the tag-predicate kind, what
    is projected — is decided by :func:`_plan_inheritance_read`; this builds the
    statement's context and sequences the four bind phases.
    """
    ctx = _Ctx(model, facet, storage, dialect)
    scope = _EntityScope(
        ctx,
        entity,
        _table_layout(storage, facet, entity.identity),
        position=plan.position,
    )
    proj_sql, proj_binds = plan.projection(dialect, scope.alias)
    ctx.binds.extend(proj_binds)

    select = f"select {proj_sql}"
    parts = [select, f"from {plan.table} {scope.alias}"]

    inner_sql = _lower_predicate(plan.inner, scope)
    where_terms = [inner_sql] if inner_sql else []
    if plan.tag is not None:
        # Planned, then bound HERE — after the user predicate above has pushed its
        # own binds (m-sql "Grouped branch predicates": branch-predicate-first,
        # then tag).
        tag_sql, tag_binds = _tph_tag_guard(scope, facet, plan.tag)
        where_terms.append(tag_sql)
        ctx.binds.extend(tag_binds)
    if where_terms:
        parts.append("where " + " and ".join(where_terms))

    _append_result_shape(parts, scope, order_keys, limit, lock)
    if ctx.requires_variant_partition:
        return (
            _compile_tph_partitioned(
                plan,
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
    statement = _normalize(LoweredStatement(" ".join(parts), tuple(ctx.binds)))
    return statement, plan.transform


def _compile_tph_partitioned(
    plan: _TphPlan,
    entity: EntityMetadata,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    lock: LockMode | None,
) -> LoweredStatement:
    """Assemble one tag-disjoint branch per selected TPH document variant."""
    branch_sqls: list[str] = []
    binds: list[object] = []
    layout = _table_layout(storage, facet, entity.identity)
    key_columns = tuple(slot.column.name for slot in layout.physical_primary_key)
    for branch_index, concrete in enumerate(plan.position):
        branch_ctx = _Ctx(model, facet, storage, dialect)
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
            projection, projection_binds = plan.projection(dialect, branch_scope.alias)
            branch_ctx.binds.extend(projection_binds)
        branch_ctx.binds.extend(tag_binds)
        branch_ctx.binds.extend(fence_binds)
        inner = _lower_predicate(plan.inner, branch_scope)
        parts = [f"select {projection}", f"from ({tagged}) {tagged_alias}"]
        if inner:
            parts.append(f"where {inner}")
        branch_sqls.append(" ".join(parts))
        binds.extend(branch_ctx.binds)

    union = " union all ".join(branch_sqls)
    if lock is not None:
        outer_ctx = _Ctx(model, facet, storage, dialect)
        outer_scope = _EntityScope(
            outer_ctx,
            entity,
            layout,
            position=plan.position,
        )
        projection, projection_binds = plan.projection(dialect, outer_scope.alias)
        outer_ctx.binds.extend(projection_binds)
        join_terms = " and ".join(
            f"{dialect.qualified('u', column)} = {dialect.qualified(outer_scope.alias, column)}"
            for column in key_columns
        )
        parts = [
            f"select {projection}",
            f"from {plan.table} {outer_scope.alias}",
            f"join ({union}) u on {join_terms}",
        ]
        _append_result_shape(parts, outer_scope, order_keys, limit, lock)
        tail_binds = outer_ctx.binds[len(projection_binds) :]
        ordered_binds = (*projection_binds, *binds, *tail_binds)
        return _normalize(LoweredStatement(" ".join(parts), ordered_binds))

    if not order_keys and limit is None:
        return _normalize(LoweredStatement(union, tuple(binds)))

    outer_ctx = _Ctx(model, facet, storage, dialect)
    outer_scope = _EntityScope(
        outer_ctx,
        entity,
        layout,
        alias="u",
        position=plan.position,
    )
    projection = ", ".join(
        dialect.qualified(outer_scope.alias, column.column) for column in plan.columns
    )
    parts = [
        f"select {projection}",
        f"from ({union}) {outer_scope.alias}",
    ]
    _append_result_shape(parts, outer_scope, order_keys, limit, None)
    binds.extend(outer_ctx.binds)
    return _normalize(LoweredStatement(" ".join(parts), tuple(binds)))


def _compile_tpcs_read(
    plan: _TpcsUnionPlan,
    entity: EntityMetadata,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
) -> tuple[LoweredStatement, _RowTransform]:
    """Assemble a table-per-concrete-subtype `union all` read (m-sql "Inheritance —
    table-per-concrete-subtype lowering").

    Each branch gets a FRESH ``_Ctx``: that is the whole mechanism behind a branch
    restarting its own alias scheme at `t0`, and behind the per-branch binds being
    separable so they concatenate in the plan's canonical branch order. The
    clause tail has no place to land in a union, which is why the plan refused an
    `orderBy` / `limit` / read-lock read before reaching here.
    """
    branch_sqls: list[str] = []
    all_binds: list[object] = []
    for branch in plan.branches:
        branch_ctx = _Ctx(model, facet, storage, dialect)
        branch_scope = _EntityScope(
            branch_ctx,
            entity,
            _table_layout(storage, facet, branch.identity),
            position=plan.position,
            variant=branch.identity,
        )
        proj_sql, proj_binds = branch.projection(dialect, branch_scope.alias)
        branch_ctx.binds.extend(proj_binds)
        parts = [f"select {proj_sql}", f"from {branch.table} {branch_scope.alias}"]
        where_sql = _lower_predicate(plan.inner, branch_scope)
        if where_sql:
            parts.append(f"where {where_sql}")
        branch_sqls.append(" ".join(parts))
        all_binds.extend(branch_ctx.binds)

    statement = _normalize(LoweredStatement(" union all ".join(branch_sqls), tuple(all_binds)))
    return statement, plan.transform


def _compile_tpcs_single(
    plan: _TpcsSinglePlan,
    entity: EntityMetadata,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    lock: LockMode | None,
) -> tuple[LoweredStatement, _RowTransform]:
    """Assemble a table-per-concrete-subtype read resolving to exactly one
    concrete: an ordinary single-table read of that subtype's own table, no tag,
    no union, no `familyVariant` — attribute resolution still widens across the
    family (the RESOLUTION SCOPE's entity stays the read's own `targetEntity`,
    e.g. an abstract position narrowed down to this one concrete, so
    :meth:`_EntityScope._searchable_attributes` searches the whole family rather
    than only that entity's own declared attributes), matching the
    table-per-hierarchy concrete-target form.

    Like :func:`_compile_tph_read` this builds the statement's context and
    sequences its bind phases explicitly — here projection, then user predicate,
    then limit; there is no framework tag guard on this lane.
    """
    ctx = _Ctx(model, facet, storage, dialect)
    scope = _EntityScope(ctx, entity, _table_layout(storage, facet, plan.position[0]))
    proj_sql, proj_binds = plan.projection(dialect, scope.alias)
    ctx.binds.extend(proj_binds)
    select = f"select {proj_sql}"
    parts = [select, f"from {plan.table} {scope.alias}"]
    where_sql = _lower_predicate(plan.inner, scope)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, scope, order_keys, limit, lock)
    statement = _normalize(LoweredStatement(" ".join(parts), tuple(ctx.binds)))
    return statement, plan.transform


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
