"""The three-stage read compiler (m-sql): canonicalize -> lower -> normalize.

``compile_read`` turns an ``m-op-algebra`` operation into one canonical
``Statement`` for a dialect. Lowering descends through `_predicate`'s one
dispatcher (no visitor framework — see the third paragraph); the dialect strategy
supplies every dialect-specific string. The emitted SQL is produced directly in
canonical normalized form (alias-qualified columns, lowercase, single-space
separated, canonical clause order), so ``normalize`` is a fixed-point identity
check rather than a rewrite — the language target never depends on the reference harness's
sqlglot normalizer (non-normative). Temporal reads are canonicalized upstream by
``m-temporal-read`` (``inject_as_of``) into ordinary predicate nodes before they
reach this compiler; deep fetch (`DeepFetch`), the one node this phase does not
yet lower, raises a clear :class:`SqlGenError` so a mis-routed case fails
loudly, never silently.

Inheritance-family reads (table-per-hierarchy tag predicates / abstract-read
superset projection, table-per-concrete-subtype union-all) are ASSEMBLED here
(COR-3 Phase 7 increment 2, `m-sql` "Metamodel-extension lowering") from plans
`_inheritance` resolves — which is where the `parallax.core.inheritance` edge now
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

from parallax.core.descriptor import Entity, Metamodel, column_order
from parallax.core.dialect import Dialect, LockMode
from parallax.core.op_algebra import (
    Distinct,
    Limit,
    Narrow,
    Operation,
    OrderBy,
    OrderKey,
)
from parallax.core.sql_gen._context import Ctx as _Ctx
from parallax.core.sql_gen._context import SqlGenError

# The family LANE of this compiler — distinct from `parallax.core.inheritance`
# above, which is the metamodel module. Each name is aliased down to the
# module-private spelling it had while this file owned it, so `inheritance.` at
# any use site below still unambiguously means the metamodel.
from parallax.core.sql_gen._inheritance import IDENTITY_TRANSFORM as _IDENTITY_TRANSFORM
from parallax.core.sql_gen._inheritance import RowTransform as _RowTransform
from parallax.core.sql_gen._inheritance import TpcsSinglePlan as _TpcsSinglePlan
from parallax.core.sql_gen._inheritance import TpcsUnionPlan as _TpcsUnionPlan
from parallax.core.sql_gen._inheritance import TphPlan as _TphPlan
from parallax.core.sql_gen._inheritance import plan_inheritance_read as _plan_inheritance_read
from parallax.core.sql_gen._inheritance import tag_guard as _tph_tag_guard

# The predicate lane: an entity resolution scope in, one `where`-clause fragment
# out, with this statement's binds pushed on the shared context in order. Same
# aliasing-down convention as the family lane above.
from parallax.core.sql_gen._predicate import EntityScope as _EntityScope
from parallax.core.sql_gen._predicate import lower_predicate as _lower_predicate

__all__ = [
    "CompiledPredicate",
    "CompiledRead",
    "SqlGenError",
    "Statement",
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
class Statement:
    """One compiled SQL statement in canonical form and its ordered binds."""

    sql: str
    binds: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledPredicate:
    """A compiled write predicate: an UNALIASED `where`-clause fragment
    (`balance < ?`, never `t0.balance < ?`) and its ordered binds.

    Deliberately NOT a :class:`Statement`: this is a predicate fragment, not a
    complete statement — the caller splices it into its own `update … where` /
    `delete from … where` template (`m-batch-write.md` "Predicate-selected
    readless forms").
    """

    sql: str
    binds: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledRead:
    """One compiled read: its :class:`Statement`, the root narrow to materialize
    under, and the row transform that materializes `familyVariant`.

    Self-contained by design (COR-43): everything a caller needs to turn driver
    rows into observed rows travels WITH the compiled statement, so the two
    execution lanes (the conformance engine's flat wire rows and the production
    snapshot find executor's instance-form graph rows) each shrink to "compile,
    execute, transform" and can no longer drift from what was actually
    projected.

    ``narrow_to`` is the read's own TOP-LEVEL authored narrow (its ``Narrow.to``,
    result-shaping directives peeled) or ``None`` for a bare read: a
    table-per-concrete-subtype position resolving to exactly one concrete emits
    no `familyVariant` column at all, so this is what lets
    :meth:`~parallax.snapshot.materialize.Assembler.materialize_root` still
    recover the row's own concrete identity. A deep-fetch CHILD level takes its
    narrow from its own ``FetchLevel.narrow_to`` instead.
    """

    statement: Statement
    narrow_to: tuple[str, ...] | None
    _transform: _RowTransform

    def transform_row(self, row: Mapping[str, object]) -> dict[str, object]:
        """Materialize `familyVariant` on one observed row.

        Accepts any ``Mapping`` (a wire-rendered row or a raw driver row alike)
        and always returns a FRESH ``dict``, including when there is nothing to
        materialize.
        """
        return self._transform.apply(row)


# --------------------------------------------------------------------------- #
# Projection.                                                                  #
# --------------------------------------------------------------------------- #
def _projection(
    entity: Entity,
    dialect: Dialect,
    alias: str,
    result_form: _ResultForm,
    *,
    include_value_objects: bool | frozenset[str] = False,
) -> tuple[str, list[object]]:
    """The base read projection (m-sql *Read projection*), a function of the model.

    Slot 1 — every declared scalar attribute's column in ``column_order`` — is the
    whole list for a **row-form** read (the values lane). The dialect maps each
    scalar to its select-list expression (a `bytes` column projects `encode(col,
    ?)`; every other column its plain reference). The framework-owned inheritance
    tag / familyVariant (slots 2/3) are never reached here — an inheritance-family
    read's projection is a distinct function of its resolved concrete-subtype
    position, not this per-entity ``column_order`` view, and is built by
    :func:`_compile_tph_read` / :func:`_compile_tpcs_read`.

    An **instance-form** read (the object lane) additionally projects slot 4: each
    declared top-level value object's backing document column, **last among all
    columns**, in declared value-object order — a json document is always a plain
    alias-qualified reference — so a value-object-bearing entity's whole document
    rides the owner's single statement (the one-round-trip materialization
    contract, m-value-object). A row-form read omits them by default.

    ``include_value_objects`` opts a **row-form** read into slot 4 too, WITHOUT
    becoming instance-form (`m-case-format.md:727`): a materializing predicate
    write's own internal resolving read stays row-form (it constructs no
    instance, `m-value-object-047`) but an assignment-bearing verb still needs
    the raw VO document(s) its own no-op comparison or chained/carried-forward
    row must read (confirmation-pass residual A) — the caller (the
    materializing predicate-write resolve in `parallax.snapshot.handle`)
    derives this from the verb's own needs, never from `result_form`. ``True``
    projects EVERY declared value object (a chain-bearing need, which must
    carry forward whichever documents the assignments do NOT themselves
    reassign); a ``frozenset`` of value-object NAMES projects ONLY those (a
    comparison-only need on a target that never chains — minimal-read
    discipline, `m-sql`) — in EITHER case the declared value-object order is
    preserved, never the caller's own set iteration order.
    """
    by_column = {attr.column: attr for attr in entity.attributes}
    exprs: list[str] = []
    binds: list[object] = []
    scalar_columns = [attr.column for attr in entity.attributes]
    for column in column_order(entity):
        attribute = by_column.get(column)
        if attribute is None or column not in scalar_columns:
            continue
        expr, extra = dialect.project(alias, column, attribute.type)
        exprs.append(expr)
        binds.extend(extra)
    if result_form == "instance" or include_value_objects is True:
        projected_vos = entity.value_objects
    elif include_value_objects:
        projected_vos = tuple(vo for vo in entity.value_objects if vo.name in include_value_objects)
    else:
        projected_vos = ()
    exprs.extend(dialect.qualified(alias, vo.column) for vo in projected_vos)
    return ", ".join(exprs), binds


# --------------------------------------------------------------------------- #
# compile_read = canonicalize -> lower -> normalize.                          #
# --------------------------------------------------------------------------- #
def compile_read(
    op: Operation,
    meta: Metamodel,
    dialect: Dialect,
    target: str,
    *,
    result_form: _ResultForm = "row",
    lock: LockMode | None = None,
    relationship_order: bool = False,
    include_value_objects: bool | frozenset[str] = False,
) -> CompiledRead:
    """Compile a read operation to one self-contained :class:`CompiledRead`.

    The result carries everything the caller needs to consume the read's rows —
    the canonical ``Statement`` for ``dialect``, the root ``narrow_to`` to
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
    document columns too, independent of ``result_form`` (`m-case-format.md:727`
    — a materializing predicate write's own resolving read projects need-
    sensitively, on EVERY target class, confirmation-pass residual A): ``True``
    projects every declared document (a temporal target's own chain need,
    which must carry forward whichever documents an assignment-bearing verb
    does NOT itself reassign — terminate/delete on a target that never
    chains still passes plain ``False``); a ``frozenset`` of value-object
    NAMES projects ONLY those (a non-chaining target's own per-row no-op
    comparison need — minimal-read discipline, never every declared
    document). An inheritance-family target never reaches this flag (a
    predicate-selected write on a family is rejected before this compiler,
    `m-inheritance`), so it is not threaded into the inheritance lowering
    below.

    ``lock`` renders the transactional read-lock suffix (m-sql *Read-lock suffix*,
    applied through the m-dialect seam): an in-transaction **object find** in
    ``locking`` mode appends the dialect's shared-row-lock suffix (Postgres
    ``for share of t0``) after every other clause; ``optimistic`` mode and the
    default (``None`` — a non-transactional read) append nothing. A ``distinct``
    result suppresses the lock (it has no identifiable base row to lock — the
    read-lock is an object-find property); grouped / aggregate reads are not yet
    reachable. The conformance scenario runner derives ``lock`` from the step's unit
    of work concurrency mode.

    ``relationship_order`` marks the peeled ``orderBy`` (if any) as a **declared
    relationship ordering** (`m-deep-fetch` "Ordered to-many children", a deep-fetch
    child level's own descriptor-derived directive) rather than a user-authored
    directive: a NULLABLE key renders through the dialect's NULLS-last rule
    (`Dialect.null_order`) instead of the plain `col dir` rendering every ordinary
    `orderBy` operation node still gets — the canonical, dialect-independent
    NULLs-last-both-directions rule applies only to the declared form (a
    non-nullable key renders identically either way, matching every existing
    relationship-ordering golden byte-for-byte).
    """
    entity = meta.entity(target)
    predicate, distinct, order_keys, limit = _peel_directives(op)
    # The read's own TOP-LEVEL authored narrow, taken from the SAME peel the
    # lowering below uses — so what the caller materializes under can never
    # disagree with what was compiled.
    narrow_to = predicate.to if isinstance(predicate, Narrow) else None
    if entity.inheritance is not None:
        statement, transform = _compile_inheritance_read(
            entity,
            predicate,
            distinct,
            order_keys,
            limit,
            meta,
            dialect,
            target,
            result_form,
            lock,
            relationship_order,
        )
        return CompiledRead(statement, narrow_to, transform)
    # One context per statement (the mutable accumulator), one resolution scope
    # over it (the immutable "what does a leaf resolve against" half).
    ctx = _Ctx(meta, dialect)
    scope = _EntityScope(ctx, entity)

    proj_sql, proj_binds = _projection(
        entity, dialect, scope.alias, result_form, include_value_objects=include_value_objects
    )
    ctx.binds.extend(proj_binds)
    select = f"select {'distinct ' if distinct else ''}{proj_sql}"
    parts = [select, f"from {entity.table} {scope.alias}"]

    where_sql = _lower_predicate(predicate, scope)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, scope, distinct, order_keys, limit, lock, relationship_order)

    statement = _normalize(Statement(" ".join(parts), tuple(ctx.binds)))
    # A non-family read projects no tag and no variant literal, so there is
    # nothing to materialize.
    return CompiledRead(statement, narrow_to, _IDENTITY_TRANSFORM)


def compile_write_predicate(
    op: Operation, meta: Metamodel, dialect: Dialect, target: str
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
    entity = meta.entity(target)
    ctx = _Ctx(meta, dialect)
    scope = _EntityScope(ctx, entity, unaliased=True)
    where_sql = _lower_predicate(op, scope)
    return CompiledPredicate(where_sql, tuple(ctx.binds))


def _append_result_shape(
    parts: list[str],
    scope: _EntityScope,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    lock: LockMode | None,
    relationship_order: bool = False,
) -> None:
    """Append the shared ``order by`` / ``limit`` / read-lock tail (m-sql), used by
    every single-select read form (plain, table-per-hierarchy, and a
    table-per-concrete-subtype read resolving to one concrete).

    ``relationship_order`` (m-deep-fetch "Ordered to-many children") renders each
    NULLABLE key through the dialect's NULLs-last rule (``Dialect.null_order``);
    a non-nullable key, and every key under an ordinary (non-declared) `orderBy`,
    renders the plain ``col dir`` form — the two forms coincide for `asc` on
    Postgres and for any non-nullable key, so this changes no existing golden.
    """
    if order_keys:
        # An authored key that omitted `direction` (serde `None`) lowers to the
        # schema default `asc`.
        terms = [_order_term(scope, key, relationship_order) for key in order_keys]
        parts.append("order by " + ", ".join(terms))
    if limit is not None:
        parts.append(scope.dialect.limit_clause())
        scope.ctx.bind(limit)
    if lock == "locking" and not distinct:
        # The shared-row-lock suffix is the last thing in the statement (after any
        # `where` / `order by` / `limit`); a `distinct` object read suppresses it.
        parts.append(scope.dialect.read_lock_suffix(scope.alias))


def _order_term(scope: _EntityScope, key: OrderKey, relationship_order: bool) -> str:
    """One ``order by`` term: `m-deep-fetch`'s declared-relationship NULLs-last
    rule for a NULLABLE key under ``relationship_order``, else the plain form."""
    direction = key.direction or "asc"
    column_sql = scope.column_of(key.attr)
    if relationship_order and scope.entity_attribute(key.attr).nullable:
        return scope.dialect.null_order(column_sql, direction)
    return f"{column_sql} {direction}"


def _peel_directives(op: Operation) -> tuple[Operation, bool, tuple[OrderKey, ...], int | None]:
    """Strip result-shaping directives (any nesting) into canonical clause data.

    A read carries at most one of each directive. A directive kind stacked twice
    (`limit(limit(…))`) has no defined composition in `m-op-algebra` — the spec
    fixes only that a directive wraps one inner operation — so a repeated kind is
    refused loudly here rather than silently overwriting the outer clause.
    """
    distinct = False
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
            case Distinct(operand=operand):
                _reject_stacked("distinct", seen)
                distinct = True
                current = operand
            case _:
                return current, distinct, order_keys, limit


def _reject_stacked(kind: str, seen: set[str]) -> None:
    if kind in seen:
        raise SqlGenError(
            f"stacked `{kind}` directives have no defined composition semantics "
            "(m-op-algebra directives wrap one inner operation); refusing rather than "
            "silently overwriting the outer clause"
        )
    seen.add(kind)


# --------------------------------------------------------------------------- #
# Inheritance-family reads (m-sql "Metamodel-extension lowering — inheritance"; #
# COR-3 Phase 7 increment 2).                                                  #
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
    entity: Entity,
    predicate: Operation,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    meta: Metamodel,
    dialect: Dialect,
    target: str,
    result_form: _ResultForm,
    lock: LockMode | None,
    relationship_order: bool = False,
) -> tuple[Statement, _RowTransform]:
    """Assemble an inheritance-family read from its plan.

    Returns the statement AND its row transform together: whether a read carries
    `familyVariant` is decided by the very same resolved position that decides
    what it projects, so the two travel together on one plan.
    """
    plan = _plan_inheritance_read(
        entity,
        predicate,
        distinct,
        order_keys,
        limit,
        meta,
        target,
        result_form == "instance",
        lock,
    )
    match plan:
        case _TphPlan():
            return _compile_tph_read(
                plan, entity, distinct, order_keys, limit, meta, dialect, lock, relationship_order
            )
        case _TpcsSinglePlan():
            return _compile_tpcs_single(
                plan, entity, distinct, order_keys, limit, meta, dialect, lock, relationship_order
            )
        case _TpcsUnionPlan():
            return _compile_tpcs_read(plan, entity, meta, dialect)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(plan)


def _compile_tph_read(
    plan: _TphPlan,
    entity: Entity,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    meta: Metamodel,
    dialect: Dialect,
    lock: LockMode | None,
    relationship_order: bool = False,
) -> tuple[Statement, _RowTransform]:
    """Assemble a table-per-hierarchy read: one shared correlated `EXISTS`-free
    single-table SELECT (m-sql "Inheritance — table-per-hierarchy lowering").

    Everything family-shaped — the resolved position, the tag-predicate kind, what
    is projected — is decided by :func:`_plan_inheritance_read`; this builds the
    statement's context and sequences the four bind phases.
    """
    ctx = _Ctx(meta, dialect)
    scope = _EntityScope(ctx, entity)
    proj_sql, proj_binds = plan.projection(dialect, scope.alias)
    ctx.binds.extend(proj_binds)

    select = f"select {'distinct ' if distinct else ''}{proj_sql}"
    parts = [select, f"from {plan.table} {scope.alias}"]

    inner_sql = _lower_predicate(plan.inner, scope)
    where_terms = [inner_sql] if inner_sql else []
    if plan.tag is not None:
        # Planned, then bound HERE — after the user predicate above has pushed its
        # own binds (m-sql "Grouped branch predicates": branch-predicate-first,
        # then tag).
        tag_sql, tag_binds = _tph_tag_guard(scope, meta, plan.tag)
        where_terms.append(tag_sql)
        ctx.binds.extend(tag_binds)
    if where_terms:
        parts.append("where " + " and ".join(where_terms))

    _append_result_shape(parts, scope, distinct, order_keys, limit, lock, relationship_order)
    statement = _normalize(Statement(" ".join(parts), tuple(ctx.binds)))
    return statement, plan.transform


def _compile_tpcs_read(
    plan: _TpcsUnionPlan,
    entity: Entity,
    meta: Metamodel,
    dialect: Dialect,
) -> tuple[Statement, _RowTransform]:
    """Assemble a table-per-concrete-subtype `union all` read (m-sql "Inheritance —
    table-per-concrete-subtype lowering").

    Each branch gets a FRESH ``_Ctx``: that is the whole mechanism behind a branch
    restarting its own alias scheme at `t0`, and behind the per-branch binds being
    separable so they concatenate in the plan's alphabetical branch order. The
    clause tail has no place to land in a union, which is why the plan refused a
    `distinct` / `orderBy` / `limit` / read-lock read before reaching here.
    """
    branch_sqls: list[str] = []
    all_binds: list[object] = []
    for branch in plan.branches:
        branch_ctx = _Ctx(meta, dialect)
        branch_scope = _EntityScope(branch_ctx, entity)
        proj_sql, proj_binds = branch.projection(dialect, branch_scope.alias)
        branch_ctx.binds.extend(proj_binds)
        parts = [f"select {proj_sql}", f"from {branch.table} {branch_scope.alias}"]
        where_sql = _lower_predicate(plan.inner, branch_scope)
        if where_sql:
            parts.append(f"where {where_sql}")
        branch_sqls.append(" ".join(parts))
        all_binds.extend(branch_ctx.binds)

    statement = _normalize(Statement(" union all ".join(branch_sqls), tuple(all_binds)))
    return statement, plan.transform


def _compile_tpcs_single(
    plan: _TpcsSinglePlan,
    entity: Entity,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    meta: Metamodel,
    dialect: Dialect,
    lock: LockMode | None,
    relationship_order: bool = False,
) -> tuple[Statement, _RowTransform]:
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
    ctx = _Ctx(meta, dialect)
    scope = _EntityScope(ctx, entity)
    proj_sql, proj_binds = plan.projection(dialect, scope.alias)
    ctx.binds.extend(proj_binds)
    select = f"select {'distinct ' if distinct else ''}{proj_sql}"
    parts = [select, f"from {plan.table} {scope.alias}"]
    where_sql = _lower_predicate(plan.inner, scope)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, scope, distinct, order_keys, limit, lock, relationship_order)
    statement = _normalize(Statement(" ".join(parts), tuple(ctx.binds)))
    return statement, plan.transform


# --------------------------------------------------------------------------- #
# Normalization (fixed-point identity check).                                 #
# --------------------------------------------------------------------------- #
def _normalize(statement: Statement) -> Statement:
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
