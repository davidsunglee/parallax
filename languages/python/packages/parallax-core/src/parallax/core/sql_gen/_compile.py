from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import chain
from typing import Literal, assert_never

from parallax.core.base import (
    Bytes,
    DocumentReadOrdinals,
    ManagedValue,
)
from parallax.core.deep_fetch import PlannedEntityQuery, ResolvedReadProjection
from parallax.core.dialect import Dialect, LockMode
from parallax.core.document_codec import is_text_compared
from parallax.core.inheritance import InheritanceFacet
from parallax.core.inheritance import view as _inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
)
from parallax.core.navigate import TemporallyResolvedPredicate
from parallax.core.object_query._resolved import (
    Paging,
    ResolvedSeek,
)
from parallax.core.predicate._resolved import disjunctive
from parallax.core.sql_gen._context import (
    LoweredStatement,
    SqlGenError,
    StatementBuilder,
)
from parallax.core.sql_gen._context import table_layout as _table_layout

# The family LANE of this compiler — distinct from `parallax.core.inheritance`
# above, which is the metamodel module. Each name is aliased down to the
# module-private spelling it had while this file owned it, so a use site below
# never confuses the two.
from parallax.core.sql_gen._inheritance import ReadResultContract as _ReadResultContract
from parallax.core.sql_gen._inheritance import SingleTableReadPlan as _SingleTableReadPlan
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import TpcsUnionReadPlan as _TpcsUnionReadPlan
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import plan_read_shape as _plan_read_shape
from parallax.core.sql_gen._inheritance import tag_column as _tag_column
from parallax.core.sql_gen._inheritance import tag_guard as _tph_tag_guard

# The planning lane: one immutable statement plan per read or write filter,
# decided before anything renders and shared by every arm of a read. Same
# aliasing-down convention as above.
from parallax.core.sql_gen._planning import EvaluationContext as _EvaluationContext
from parallax.core.sql_gen._planning import LexicalScopeId as _LexicalScopeId
from parallax.core.sql_gen._planning import StatementPlan as _StatementPlan
from parallax.core.sql_gen._planning import WriteFilterForm as _WriteFilterForm
from parallax.core.sql_gen._planning import plan_statement as _plan_statement

# The predicate lane: a planned lexical scope and an entity row in, one
# `where`-clause fragment out, with this statement's binds pushed on the shared
# context in order.
from parallax.core.sql_gen._predicate import EntityRowScope as _EntityRowScope
from parallax.core.sql_gen._predicate import MemberSubject as _MemberSubject
from parallax.core.sql_gen._predicate import render_predicate as _render_predicate
from parallax.core.sql_gen._predicate import render_shared_sources as _render_shared_sources

# The continuation lane: one resolver per read shape, feeding the order clause,
# the hidden capture cell, and the seek alike.
from parallax.core.sql_gen._seek import LoweredTerm as _LoweredTerm
from parallax.core.sql_gen._seek import TermSubject as _TermSubject
from parallax.core.sql_gen._seek import emits_null_tail as _emits_null_tail
from parallax.core.sql_gen._seek import lower_seek as _lower_seek
from parallax.core.sql_gen._seek import lowered_terms as _lowered_terms
from parallax.core.sql_gen._seek import order_clause as _order_clause

# The select-list lane: every read select list is emitted through one owner,
# which also yields what each of its cells carries.
from parallax.core.sql_gen._select_list import SelectListBuilder as _SelectListBuilder
from parallax.core.storage_layout import DirectColumn as _DirectColumn
from parallax.core.storage_layout import DocumentPath as _DocumentPath
from parallax.core.storage_layout import StorageLayoutFacet as _StorageLayoutFacet
from parallax.core.storage_layout import TableLayout as _TableLayout
from parallax.core.storage_layout import view as _storage_view

__all__ = [
    "CompiledRead",
    "CompiledTemplate",
    "compile_read",
    "compile_template",
    "compile_write_predicate",
]

# The read's consumption lane (m-sql *Result form*): a ``row``-form read (the
# values lane) publishes flat rows, an ``instance``-form read (the object lane —
# a find / snapshot / deep-fetch whose rows materialize into instances) publishes
# objects. What either projects is the planned query's own resolved demand; the
# lane decides only the returned shape.
# PRIVATE: `compile_read`'s ``result_form`` keyword and its semantics are part of
# the supported interface, but the alias naming them is not — a caller spells the
# two literals inline (`Literal["row", "instance"]`) rather than importing a name
# whose only job is to abbreviate them.
_ResultForm = Literal["row", "instance"]


@dataclass(frozen=True, slots=True)
class CompiledPredicate:
    """A compiled write predicate and its ordered binds.

    Unless it is a ``selection``, ``sql`` is an UNALIASED `where`-clause
    fragment (`balance < ?`, never `t0.balance < ?`). A ``selection`` is
    instead a `select` of the target's physical primary-key Columns, in key
    order, from the rows the predicate matches through the shared sources a
    read of it joins; the write tests its own key's membership in it.

    Deliberately NOT a :class:`LoweredStatement`: either form is part of a
    statement — the caller splices it into its own `update … where` /
    `delete from … where` template (`m-batch-write.md` "Predicate-selected
    readless forms").
    """

    sql: str
    binds: tuple[object, ...] = ()
    lowered: LoweredStatement | None = field(default=None, repr=False, compare=False)
    selection: bool = False


@dataclass(frozen=True, slots=True)
class CompiledRead:
    """One compiled read: its :class:`LoweredStatement`, the root narrow to materialize
    under, and the result contract that names and locates what its driver rows carry.

    Self-contained by design: everything a caller needs to turn driver rows into
    observed rows travels WITH the compiled statement. Every materializing
    consumer — the typed and wire snapshot lanes and the write lanes alike — uses
    raw ordinal access and deferred conversion through the Page its lane owns.
    None re-derives what the statement projected.

    ``narrow_to`` is the read's own query-wide narrowing or ``None`` for a bare read: a
    table-per-concrete-subtype position resolving to exactly one concrete emits
    no `familyVariant` column at all, so this is what still names the row's own
    concrete identity. A deep-fetch CHILD level's narrow is its own planned child
    query's.

    ``projection`` is the planned query's own resolved demand, which the
    statement selected; binding judges exactly its occurrences, so an
    unrequested occurrence is never judged merely because the position could
    have carried it.
    """

    statement: LoweredStatement
    narrow_to: tuple[EntityIdentity, ...] | None
    target: EntityIdentity
    resolved_position: tuple[EntityIdentity, ...]
    projection: ResolvedReadProjection
    document_reads: tuple[DocumentReadOrdinals, ...]
    result_contract: _ReadResultContract


@dataclass(frozen=True, slots=True)
class CompiledTemplate:
    """One compiled child read whose parent key set is supplied per execution."""

    compiled: CompiledRead
    postgres_array: bool
    _markers: tuple[int, ...]
    _sql_parts: tuple[str, ...] = ()

    def render(self, keys: list[ManagedValue]) -> CompiledRead:
        """Bind ``keys`` at every position of the deferred key set; the Postgres array
        bind is the list itself, so the caller hands it over and must not mutate it
        afterwards."""
        if not keys:
            raise SqlGenError("a child read template requires at least one gathered key")
        statement = self.compiled.statement
        if self.postgres_array:
            rendered = statement.with_keys(statement.sql, self._markers, (keys,))
        else:
            holes = ", ".join("?" for _ in keys)
            rendered = statement.with_keys(holes.join(self._sql_parts), self._markers, keys)
        return replace(self.compiled, statement=rendered)


def compile_template(
    query: PlannedEntityQuery,
    model: Metamodel,
    dialect: Dialect,
    *,
    result_form: _ResultForm = "row",
    lock: LockMode | None = None,
) -> CompiledTemplate:
    """Compile a child read once, deferring only its gathered parent keys."""
    compiled = compile_read(query, model, dialect, result_form=result_form, lock=lock)
    return _template(compiled, postgres_array=dialect.name == "postgres")


def _template(compiled: CompiledRead, *, postgres_array: bool) -> CompiledTemplate:
    statement = compiled.statement
    return CompiledTemplate(
        compiled,
        postgres_array,
        statement.deferred_key_markers(),
        () if postgres_array else tuple(statement.sql.split("__parallax_deferred_keys__")),
    )


def compile_read(
    query: PlannedEntityQuery,
    model: Metamodel,
    dialect: Dialect,
    *,
    result_form: _ResultForm = "row",
    lock: LockMode | None = None,
) -> CompiledRead:
    """Compile one planned Entity Query into a self-contained read.

    ``result_form`` chooses only the materialization contract. Projection membership is
    already present on ``query``; ``lock`` is the caller-derived effective read lock.
    """

    storage = _storage_view(model)
    facet = _inheritance_view(model)
    terms = _lowered_terms(query.order_by, _reserved_result_keys(model, storage))
    seek = None if query.paging is None else query.paging.seek
    two_arms = (
        seek is not None and query.limit is not None and _needs_null_tail(seek, storage, dialect)
    )
    outer_lock = two_arms and lock == "locking" and dialect.name == "postgres"
    arm_lock = None if outer_lock else lock
    read_shape = _plan_read_shape(query, facet, storage, result_form == "instance", arm_lock)
    statement_plan = _plan_statement(
        query.predicate,
        evaluation_context=_EvaluationContext.SHARING_ALLOWED,
        entity=query.entity,
        meta=model,
        facet=facet,
        storage=storage,
        read_shape=read_shape,
        order_terms=query.order_by,
    )
    position = tuple(read_shape.concrete_types)
    statement, select_list = _render_read_arm(
        query,
        read_shape,
        statement_plan,
        terms,
        model,
        facet,
        storage,
        dialect,
        lock=arm_lock,
        null_tail=False,
    )
    if two_arms:
        null_tail, tail_list = _render_read_arm(
            query,
            read_shape,
            statement_plan,
            terms,
            model,
            facet,
            storage,
            dialect,
            lock=arm_lock,
            null_tail=True,
        )
        select_list.require_agreement(tail_list)
        statement, select_list = _union_null_tail(
            statement,
            null_tail,
            select_list,
            query,
            terms,
            model,
            facet,
            storage,
            dialect,
            locking=outer_lock,
        )
    return CompiledRead(
        statement,
        query.narrow_to,
        query.entity.identity,
        position,
        query.projection,
        select_list.document_reads,
        select_list.result_contract(
            read_shape, facet, query.projection, terms if query.paging is not None else ()
        ),
    )


def _union_null_tail(
    ordinary: LoweredStatement,
    null_tail: LoweredStatement,
    select_list: _SelectListBuilder,
    query: PlannedEntityQuery,
    terms: tuple[_LoweredTerm, ...],
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    *,
    locking: bool,
) -> tuple[LoweredStatement, _SelectListBuilder]:
    """The ordered, capped `union all` of a continuing page's ordinary and
    NULL-tail arms, selected through the cells both arms emit; a ``locking``
    union joins back to the target's base Table and locks that row instead."""
    statement_ctx = StatementBuilder(model, facet, storage, dialect)
    statement_ctx.append_fragment(ordinary)
    statement_ctx.append_fragment(null_tail)
    outer_alias = "u"
    outer_list = select_list.select_through(outer_alias)
    ordering = ", ".join(
        dialect.null_order(
            dialect.qualified(outer_alias, term.alias), term.term.direction, term.term.nulls
        )
        if term.member.nullable
        else f"{dialect.qualified(outer_alias, term.alias)} {term.term.direction}"
        for term in terms
    )
    source = f"(({ordinary.sql}) union all ({null_tail.sql})) {outer_alias}"
    lock_suffix = ""
    if locking:
        base_join, lock_suffix = _locking_base_join(
            statement_ctx,
            select_list,
            _table_layout(storage, facet, query.entity.identity),
            dialect,
            outer_alias,
        )
        source += base_join
    statement_ctx.bind_structural(query.limit)
    statement = statement_ctx.finish(
        f"select {outer_list.sql} from {source} order by {ordering} "
        f"{dialect.limit_clause()}{lock_suffix}"
    )
    return _normalize(statement), outer_list


def _needs_null_tail(seek: ResolvedSeek, storage: _StorageLayoutFacet, dialect: Dialect) -> bool:
    """Whether a continuing page needs a NULL-tail arm, with the leading term
    counted as document-resident unless every Table placing it gives it a Column."""
    if not seek.terms:  # pragma: no cover - validated continuations always order by a term
        return False
    placements = tuple(
        placement
        for layout in storage.tables
        if (placement := layout.placement(seek.terms[0].identity)) is not None
    )
    leading_resident = not placements or not all(
        isinstance(placement, _DirectColumn) for placement in placements
    )
    return _emits_null_tail(seek, dialect, leading_resident=leading_resident)


def _locking_base_join(
    ctx: StatementBuilder,
    select_list: _SelectListBuilder,
    layout: _TableLayout,
    dialect: Dialect,
    outer_alias: str,
) -> tuple[str, str]:
    """The join from a wrapped union back to the target's base Table, matched on
    every physical key Column under the alias ``select_list`` emitted it as,
    and the lock suffix naming that Table; the key cells' binds are appended to
    ``ctx`` in join order."""
    base_alias = "t0"
    join_terms: list[str] = []
    for slot in layout.physical_primary_key:
        if not isinstance(slot.contributor, AttributeIdentity):  # pragma: no cover
            raise SqlGenError("a physical primary-key column must be Attribute-owned")
        alias, neutral_type = select_list.selected_scalar(slot.contributor)
        base = dialect.render_scalar(base_alias, slot.column.name, neutral_type)
        ctx.bind_structural_all(base.binds)
        join_terms.append(f"{dialect.qualified(outer_alias, alias)} = {base.expression_sql}")
    return (
        f" join {layout.table.name} {base_alias} on " + " and ".join(join_terms),
        f" {dialect.read_lock_suffix(base_alias)}",
    )


def compile_write_predicate(
    op: TemporallyResolvedPredicate, model: Metamodel, dialect: Dialect, target: EntityMetadata
) -> CompiledPredicate:
    """Render an already-validated write predicate in the form its plan selects:
    unaliased, every occurrence unshared, unless an occurrence reads through a
    shared source; then the selection of the target's physical key from the
    rows it matches, rendered as a read of the target's own Table selects them.
    """
    facet = _inheritance_view(model)
    storage = _storage_view(model)
    layout = _table_layout(storage, facet, target.identity)
    statement_plan = _plan_statement(
        op,
        evaluation_context=_EvaluationContext.WRITE_FILTER,
        entity=target,
        meta=model,
        facet=facet,
        storage=storage,
    )
    root = statement_plan.root_scopes[None]
    ctx: StatementBuilder[_EntityRowScope] = StatementBuilder(model, facet, storage, dialect)
    match statement_plan.write_filter_form:
        case _WriteFilterForm.DIRECT_PREDICATE:
            scope = _EntityRowScope(ctx, target, layout, unaliased=True)
            statement = ctx.finish(
                _render_predicate(
                    statement_plan=statement_plan, scope_id=root, path=(), scope=scope
                )
            )
            return CompiledPredicate(statement.sql, statement.binds, statement)
        case _WriteFilterForm.PRIMARY_KEY_SUBQUERY:
            scope = _EntityRowScope(ctx, target, layout)
            keys = ", ".join(
                scope.own_column(slot.column.name) for slot in layout.physical_primary_key
            )
            parts = [f"select {keys}", f"from {layout.table.name} {scope.alias}"]
            _append_where(parts, _render_selection(statement_plan, root, scope, parts))
            statement = _normalize(ctx.finish(" ".join(parts)))
            return CompiledPredicate(statement.sql, statement.binds, statement, selection=True)
        case None:  # pragma: no cover - a write filter plan always selects its form
            raise SqlGenError("a write filter was planned without a form")


def _render_selection(
    statement_plan: _StatementPlan,
    scope_id: _LexicalScopeId,
    scope: _EntityRowScope,
    parts: list[str],
) -> str:
    """Append the joins of lexical plan ``scope_id``'s shared sources to
    ``parts`` and render its predicate beside them, so every alias and bind
    follows the text.

    The read forms selecting from one physical Table or one of its partitions
    share this seam with a readless write's key selection.
    """
    joins = _render_shared_sources(statement_plan, scope_id, scope)
    if joins:
        parts.append(joins)
    return _render_predicate(statement_plan=statement_plan, scope_id=scope_id, path=(), scope=scope)


def _reserved_result_keys(model: Metamodel, storage: _StorageLayoutFacet) -> frozenset[str]:
    """Every result key a read of this model can carry under an authored name.

    The complete reservation set a capture alias is allocated outside of. Two
    authored spellings reach a row: a projected cell named by its own Column
    spelling, and — under Relational Document Layout — the member spelling the
    document fan-out writes each resident member under, which claims no Column
    at all and so is free to spell anything. A cell's `_hex` projection and an
    allocated internal alias are the other two forms, and neither can collide
    with the framework's own prefix.

    Taken over the whole model rather than over one read's projection or one
    member's placement, so a given model allocates the same aliases for every
    read of it; over-reserving costs only the index a capture alias starts from.
    """
    return frozenset(
        chain(
            (slot.column.name for layout in storage.tables for slot in layout.columns),
            (
                member.storage.name
                for entity in model.entities
                for member in (*entity.declared_attributes, *entity.declared_value_objects)
            ),
        )
    )


def _emit_coordinates(
    select_list: _SelectListBuilder,
    terms: tuple[_LoweredTerm, ...],
    subject: _TermSubject,
    paging: Paging | None,
) -> None:
    """Emit this read's hidden coordinate cells, none where it pages nowhere.

    Each captures the expression the ``order by`` clause compares, through the
    same ``subject``, so what a row carries back is what the database ordered
    it by.
    """
    if paging is None:
        return
    for term in terms:
        select_list.emit_coordinate(term, subject(term.member).compared)


def _render_seek(
    terms: tuple[_LoweredTerm, ...],
    scope: _EntityRowScope,
    subject: _TermSubject,
    paging: Paging | None,
    ctx: StatementBuilder[_EntityRowScope],
    *,
    null_tail: bool = False,
) -> str:
    """This read's seek fragment, or nothing where it starts at the beginning.

    ``scope`` answers the leading term's Member Placement, which decides whether
    the seek hoists its leading range; it is the scope ``subject`` resolves
    against, asked here rather than there because resolving would bind an
    extraction's path segments ahead of text that may not be emitted.
    """
    if paging is None or paging.seek is None:
        return ""
    if null_tail:
        if not terms:  # pragma: no cover - a NULL tail is selected from its leading term
            raise SqlGenError("a NULL-tail continuation requires an ordering term")
        return f"{subject(terms[0].member).extraction} is null"
    return _lower_seek(
        paging.seek,
        terms,
        subject,
        ctx,
        leading_resident=bool(terms) and scope.document_resident(terms[0].member),
    )


def _where_as_conjunct(
    temporal: TemporallyResolvedPredicate, where_sql: str, *, conjoined: bool
) -> str:
    """The selection's `where` fragment, ready to join with `and` to a seek or
    a tag guard.

    An `or` binds looser than the enclosing `and`, so a top-level disjunction
    conjoined with either would silently re-associate the caller's own
    predicate into the framework term's first branch.
    """
    if conjoined and where_sql and disjunctive(temporal.predicate):
        return f"({where_sql})"
    return where_sql


def _append_where(parts: list[str], *fragments: str) -> None:
    """Append one `where` clause over whichever fragments survived."""
    surviving = [fragment for fragment in fragments if fragment]
    if surviving:
        parts.append("where " + " and ".join(surviving))


def _append_read_tail(
    parts: list[str],
    scope: _EntityRowScope,
    terms: tuple[_LoweredTerm, ...],
    subject: _TermSubject,
    limit: int | None,
    lock: LockMode | None,
) -> None:
    """Append the ``order by`` / ``limit`` / read-lock tail (m-sql) to the select
    reading ``scope``'s rows: a single-table read, or the outer select over a
    partitioned or union read.

    An ordering key that omitted `direction` or `nulls` already carries the
    schema defaults `asc` and `last` by the time it reaches here.

    An ordering key over a document-resident member lowers through the same
    extraction and typed-cast seams a predicate over it does (`m-sql`), which is
    what keeps one ordering answer the same under either layout: the six
    text-compared spellings order as their values do, and everything else orders
    inside the engine's own type system through the cast.
    """
    ordering = _order_clause(terms, subject, scope.dialect)
    if ordering:
        parts.append(ordering)
    if limit is not None:
        parts.append(scope.dialect.limit_clause())
        scope.ctx.bind_structural(limit)
    if lock == "locking":
        # The shared-row-lock suffix is the last thing in the statement (after any
        # `where` / `order by` / `limit`).
        parts.append(scope.dialect.read_lock_suffix(scope.alias))


def _render_read_arm(
    query: PlannedEntityQuery,
    plan: _SingleTableReadPlan | _TpcsUnionReadPlan,
    statement_plan: _StatementPlan,
    terms: tuple[_LoweredTerm, ...],
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    *,
    lock: LockMode | None,
    null_tail: bool,
) -> tuple[LoweredStatement, _SelectListBuilder]:
    """Render one ordinary or NULL-tail arm of ``query`` from its one physical
    plan and one statement plan, through builders of this arm's own: its
    statement and its outermost select list.

    The physical plan decides whether a read is one Table or a union, and the
    statement plan whether a table-per-hierarchy read partitions by variant.
    """
    entity = query.entity
    paging = query.paging
    limit = query.limit
    match plan:
        case _TpcsUnionReadPlan():
            return _render_tpcs_union_read(
                plan,
                statement_plan,
                entity,
                terms,
                paging,
                limit,
                model,
                facet,
                storage,
                dialect,
                null_tail,
            )
        case _SingleTableReadPlan() if statement_plan.requires_tph_partition:
            return _render_tph_partitioned_read(
                plan,
                statement_plan,
                entity,
                terms,
                paging,
                limit,
                model,
                facet,
                storage,
                dialect,
                lock,
                null_tail,
            )
        case _SingleTableReadPlan():
            return _render_single_table_read(
                plan,
                statement_plan,
                entity,
                terms,
                paging,
                limit,
                model,
                facet,
                storage,
                dialect,
                lock,
                null_tail,
            )
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(plan)


def _agreed(first: _SelectListBuilder | None, branch: _SelectListBuilder) -> _SelectListBuilder:
    """The select list one union's branches share, once ``branch`` agrees with
    the ``first`` branch's."""
    if first is None:
        return branch
    first.require_agreement(branch)
    return first


def _select_list(
    plan: _SingleTableReadPlan, dialect: Dialect, alias: str, *, document_pairs: bool = True
) -> _SelectListBuilder:
    select_list = _SelectListBuilder(dialect, document_pairs=document_pairs)
    for column in plan.columns:
        select_list.emit(column, table_alias=alias)
    return select_list


def _render_single_table_read(
    plan: _SingleTableReadPlan,
    statement_plan: _StatementPlan,
    entity: EntityMetadata,
    terms: tuple[_LoweredTerm, ...],
    paging: Paging | None,
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    lock: LockMode | None,
    null_tail: bool,
) -> tuple[LoweredStatement, _SelectListBuilder]:
    """Render one SELECT over the plan's one Table (m-sql "Inheritance —
    table-per-hierarchy lowering" and "… — table-per-concrete-subtype
    lowering"): select list, user predicate, seek, the plan's framework tag
    guard where it has one, then the clause tail, each binding in that order.

    The resolution scope's Entity stays the queried ``entity`` even where the
    Table is one concrete's, so an abstract position narrowed to that concrete
    still resolves Attributes across its family.
    """
    ctx: StatementBuilder[_EntityRowScope] = StatementBuilder(model, facet, storage, dialect)
    scope = _EntityRowScope(ctx, entity, _table_layout(storage, facet, plan.concrete_types[0]))
    select_list = _select_list(plan, dialect, scope.alias)
    ctx.bind_structural_all(select_list.binds)
    _emit_coordinates(select_list, terms, scope.subject_for, paging)
    parts = [f"select {select_list.sql}", f"from {plan.table} {scope.alias}"]
    where_sql = _render_selection(statement_plan, statement_plan.root_scopes[None], scope, parts)
    seek_sql = _render_seek(terms, scope, scope.subject_for, paging, ctx, null_tail=null_tail)
    conjoined = bool(seek_sql) or plan.tag_guard is not None
    where_terms = [
        _where_as_conjunct(statement_plan.predicate, where_sql, conjoined=conjoined),
        seek_sql,
    ]
    if plan.tag_guard is not None:
        # Bound after the user predicate and the seek have pushed their own
        # binds (m-sql "Grouped branch predicates": branch predicate first,
        # then tag).
        tag_sql, tag_binds = _tph_tag_guard(scope, facet, plan.tag_guard)
        where_terms.append(tag_sql)
        ctx.bind_framework_all(tag_binds)
    _append_where(parts, *where_terms)
    _append_read_tail(parts, scope, terms, scope.subject_for, limit, lock)
    return _normalize(ctx.finish(" ".join(parts))), select_list


def _render_tph_partitioned_read(
    plan: _SingleTableReadPlan,
    statement_plan: _StatementPlan,
    entity: EntityMetadata,
    terms: tuple[_LoweredTerm, ...],
    paging: Paging | None,
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    lock: LockMode | None,
    null_tail: bool,
) -> tuple[LoweredStatement, _SelectListBuilder]:
    """Render one tag-disjoint branch per selected TPH document variant."""
    branch_sqls: list[str] = []
    branches: list[LoweredStatement] = []
    branch_list: _SelectListBuilder | None = None
    layout = _table_layout(storage, facet, entity.identity)
    key_columns = tuple(slot.column.name for slot in layout.physical_primary_key)
    for branch_index, concrete in enumerate(plan.concrete_types):
        branch_ctx: StatementBuilder[_EntityRowScope] = StatementBuilder(
            model, facet, storage, dialect
        )
        base_scope = _EntityRowScope(
            branch_ctx,
            entity,
            layout,
            alias=f"t{branch_index + 1}" if lock is not None else "t0",
        )
        tag = _TagPredicate(
            _tag_column(layout, _entity_view(facet, entity.identity).root),
            (concrete,),
        )
        tag_sql, tag_binds = _tph_tag_guard(base_scope, facet, tag)
        tagged_alias = f"p{branch_index + 1}"
        fence_sql, fence_binds = dialect.optimizer_fence()
        tagged = f"select * from {plan.table} {base_scope.alias} where {tag_sql} {fence_sql}"
        branch_scope = _EntityRowScope(branch_ctx, entity, layout, alias=tagged_alias)
        if lock is not None:
            projection = ", ".join(
                dialect.qualified(branch_scope.alias, column) for column in key_columns
            )
        else:
            selected = _select_list(
                plan, dialect, branch_scope.alias, document_pairs=not terms and limit is None
            )
            branch_list = _agreed(branch_list, selected)
            branch_ctx.bind_structural_all(selected.binds)
            projection = selected.sql
        branch_ctx.bind_framework_all(tag_binds)
        branch_ctx.bind_framework_all(fence_binds)
        parts = [f"select {projection}", f"from ({tagged}) {tagged_alias}"]
        inner = _render_selection(
            statement_plan, statement_plan.root_scopes[concrete], branch_scope, parts
        )
        if inner:
            parts.append(f"where {inner}")
        branch_sql = " ".join(parts)
        branch_sqls.append(branch_sql)
        branches.append(branch_ctx.finish(branch_sql))

    union = " union all ".join(branch_sqls)
    if lock is not None:
        statement_ctx: StatementBuilder[_EntityRowScope] = StatementBuilder(
            model, facet, storage, dialect
        )
        outer_scope = _EntityRowScope(statement_ctx, entity, layout)
        select_list = _select_list(plan, dialect, outer_scope.alias)
        statement_ctx.bind_structural_all(select_list.binds)
        _emit_coordinates(select_list, terms, outer_scope.subject_for, paging)
        join_terms = " and ".join(
            f"{dialect.qualified('u', column)} = {dialect.qualified(outer_scope.alias, column)}"
            for column in key_columns
        )
        parts = [
            f"select {select_list.sql}",
            f"from {plan.table} {outer_scope.alias}",
            f"join ({union}) u on {join_terms}",
        ]
        for branch in branches:
            statement_ctx.append_fragment(branch)
        _append_where(
            parts,
            _render_seek(
                terms,
                outer_scope,
                outer_scope.subject_for,
                paging,
                statement_ctx,
                null_tail=null_tail,
            ),
        )
        _append_read_tail(parts, outer_scope, terms, outer_scope.subject_for, limit, lock)
        return _normalize(statement_ctx.finish(" ".join(parts))), select_list

    if branch_list is None:  # pragma: no cover - a position names at least one concrete
        raise SqlGenError("a partitioned read selects no variant")
    if not terms and limit is None:
        statement_ctx = StatementBuilder(model, facet, storage, dialect)
        for branch in branches:
            statement_ctx.append_fragment(branch)
        return _normalize(statement_ctx.finish(union)), branch_list

    statement_ctx = StatementBuilder(model, facet, storage, dialect)
    outer_scope = _EntityRowScope(
        statement_ctx, entity, layout, alias="u", wrapped=branch_list.scalar_cells()
    )
    select_list = branch_list.select_through(outer_scope.alias)
    _emit_coordinates(select_list, terms, outer_scope.subject_for, paging)
    parts = [f"select {select_list.sql}", f"from ({union}) {outer_scope.alias}"]
    for branch in branches:
        statement_ctx.append_fragment(branch)
    _append_where(
        parts,
        _render_seek(
            terms,
            outer_scope,
            outer_scope.subject_for,
            paging,
            statement_ctx,
            null_tail=null_tail,
        ),
    )
    _append_read_tail(parts, outer_scope, terms, outer_scope.subject_for, limit, None)
    return _normalize(statement_ctx.finish(" ".join(parts))), select_list


def _render_tpcs_union_read(
    plan: _TpcsUnionReadPlan,
    statement_plan: _StatementPlan,
    entity: EntityMetadata,
    terms: tuple[_LoweredTerm, ...],
    paging: Paging | None,
    limit: int | None,
    model: Metamodel,
    facet: InheritanceFacet,
    storage: _StorageLayoutFacet,
    dialect: Dialect,
    null_tail: bool,
) -> tuple[LoweredStatement, _SelectListBuilder]:
    """Render a table-per-concrete-subtype `union all` read (m-sql "Inheritance —
    table-per-concrete-subtype lowering").

    Each branch gets a FRESH ``StatementBuilder``: that is the whole mechanism behind a branch
    restarting its own alias scheme at `t0`, and behind the per-branch binds being
    separable so they concatenate in the plan's canonical branch order.

    A `union all` has no clause tail of its own, so an ordered or limited read
    wraps it as the derived table ``u`` and applies the tail against the union's
    own result aliases — the shape a table-per-hierarchy partitioned read already
    uses. The caller's predicate still lowers INSIDE each branch, where the branch
    layout is what resolves a member's column; the result-shape tail, the hidden
    capture cells, and the seek all move outward together, because a coordinate
    is measured against the very expression the union is ORDERED by. An
    unordered, uncapped read emits the bare union, unchanged.
    """
    wrapped = bool(terms) or limit is not None
    branch_sqls: list[str] = []
    branch_statements: list[LoweredStatement] = []
    union_list: _SelectListBuilder | None = None
    for branch in plan.branches:
        branch_ctx: StatementBuilder[_EntityRowScope] = StatementBuilder(
            model, facet, storage, dialect
        )
        branch_scope = _EntityRowScope(
            branch_ctx, entity, _table_layout(storage, facet, branch.identity)
        )
        branch_list = _SelectListBuilder(dialect, document_pairs=not wrapped)
        for column in branch.columns:
            branch_list.emit_branch(column, table_alias=branch_scope.alias)
        branch_list.emit_variant(branch.variant)
        union_list = _agreed(union_list, branch_list)
        branch_ctx.bind_structural_all(branch_list.binds)
        parts = [f"select {branch_list.sql}", f"from {branch.table} {branch_scope.alias}"]
        where_sql = _render_selection(
            statement_plan, statement_plan.root_scopes[branch.identity], branch_scope, parts
        )
        if where_sql:
            parts.append(f"where {where_sql}")
        branch_sql = " ".join(parts)
        branch_sqls.append(branch_sql)
        branch_statements.append(branch_ctx.finish(branch_sql))
    if union_list is None:  # pragma: no cover - a union position has several concretes
        raise SqlGenError("a table-per-concrete-subtype union selects no branch")

    union = " union all ".join(branch_sqls)
    if not wrapped:
        statement_ctx = StatementBuilder(model, facet, storage, dialect)
        for branch in branch_statements:
            statement_ctx.append_fragment(branch)
        return _normalize(statement_ctx.finish(union)), union_list

    # The outer select brackets the union in the emitted text — its capture
    # cells precede every branch and its tail follows them all — so its binds
    # are accumulated as two fragments and spliced on either side of the
    # branches. One context for the whole outer select would push both halves
    # after the branches and send branch data to a capture-cell placeholder.
    outer_layout = _table_layout(storage, facet, plan.branches[0].identity)
    capture_ctx: StatementBuilder[_EntityRowScope] = StatementBuilder(
        model, facet, storage, dialect
    )
    capture_scope = _EntityRowScope(capture_ctx, entity, outer_layout, alias="u")
    tail_ctx: StatementBuilder[_EntityRowScope] = StatementBuilder(model, facet, storage, dialect)
    outer_scope = _EntityRowScope(tail_ctx, entity, outer_layout, alias="u")
    select_list = union_list.select_through(outer_scope.alias)
    tail_subject = _tpcs_subject(plan, outer_scope)
    _emit_coordinates(select_list, terms, _tpcs_subject(plan, capture_scope), paging)
    outer_parts = [f"select {select_list.sql}", f"from ({union}) {outer_scope.alias}"]
    _append_where(
        outer_parts,
        _render_seek(
            terms,
            outer_scope,
            tail_subject,
            paging,
            tail_ctx,
            null_tail=null_tail,
        ),
    )
    _append_read_tail(outer_parts, outer_scope, terms, tail_subject, limit, None)
    statement_ctx = StatementBuilder(model, facet, storage, dialect)
    statement_ctx.append_fragment(capture_ctx.finish(""))
    for branch in branch_statements:
        statement_ctx.append_fragment(branch)
    statement_ctx.append_fragment(tail_ctx.finish(""))
    statement = _normalize(statement_ctx.finish(" ".join(outer_parts)))
    return statement, select_list


def _tpcs_subject(plan: _TpcsUnionReadPlan, scope: _EntityRowScope) -> _TermSubject:
    """How a wrapped union resolves one Continuation Order term.

    One thing differs from the generic scope resolver: a member is named by the
    result alias every branch projects it under rather than by any one branch's
    physical spelling, because the union is the ordered relation and a colliding
    spelling reaches it only through its allocated alias. That alias also
    carries what the branch already rendered into it, so a `bytes` member is a
    hex-encoded TEXT expression under the union and compares — and rebinds — as
    the codec's own text rather than as octets.

    The positional rule (`m-object-query`) admits a Sort Key only over a member
    applicable to every concrete in the active position, so a legal key is owned
    by every branch and never meets that branch's typed `NULL` placeholder.
    """
    return lambda attribute: _tpcs_order_subject(plan, scope, attribute)


def _tpcs_order_subject(
    plan: _TpcsUnionReadPlan, scope: _EntityRowScope, attribute: AttributeMetadata
) -> _MemberSubject:
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
        return _MemberSubject(
            reference,
            reference,
            attribute.type,
            document_resident=False,
            text_compared=isinstance(attribute.type, Bytes),
        )
    extraction, path_binds = scope.dialect.nested_extract(reference, document.path)
    scope.ctx.bind_structural_all(path_binds)
    return _MemberSubject(
        extraction,
        scope.dialect.nested_cast(extraction, attribute.type),
        attribute.type,
        document_resident=True,
        text_compared=is_text_compared(attribute.type),
    )


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
