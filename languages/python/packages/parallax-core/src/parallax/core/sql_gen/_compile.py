"""The three-stage read compiler (m-sql): canonicalize -> lower -> normalize.

``compile_read`` turns an ``m-op-algebra`` operation into one canonical
``Statement`` for a dialect. Lowering is per-concern ``match`` functions over the
node union (no visitor framework); the dialect strategy supplies every
dialect-specific string. The emitted SQL is produced directly in canonical
normalized form (alias-qualified columns, lowercase, single-space separated,
canonical clause order), so ``normalize`` is a fixed-point identity check rather
than a rewrite — the language target never depends on the reference harness's
sqlglot normalizer (non-normative). Temporal reads are canonicalized upstream by
``m-temporal-read`` (``inject_as_of``) into ordinary predicate nodes before they
reach this compiler; deep fetch (`DeepFetch`), the one node this phase does not
yet lower, raises a clear :class:`SqlGenError` so a mis-routed case fails
loudly, never silently.

Inheritance-family reads (table-per-hierarchy tag predicates / abstract-read
superset projection, table-per-concrete-subtype union-all) are lowered here too
(COR-3 Phase 7 increment 2, `m-sql` "Metamodel-extension lowering"): narrow
resolution imports `parallax.core.inheritance` directly — a legal edge, since
`modules.md` already reaches `m-inheritance` transitively through
`m-op-algebra`. `validate_operation` runs upstream (the conformance engine /
statement frontend), so a narrow reaching this compiler is already known
position-valid; this module only resolves and lowers, it never re-validates.

Navigation (`navigate` / `exists` / `notExists`) lowers here too (COR-3 Phase 7
increment 3, `m-sql` "Joins by navigation"): a hop's correlation columns are
derived mechanically from the relationship's declared `join` predicate, and a
polymorphic hop's effective concrete-subtype set is resolved the same way the
top-level inheritance reads above already do — this module never needs the
per-hop as-of predicate to be anything but an ordinary, pre-injected
`m-op-algebra` node (`parallax.core.navigate.canonicalize` runs upstream, the
composition-at-the-engine M2 precedent, since the DAG forbids `m-sql` from
importing `m-temporal-read`). The correlated-`EXISTS` alias sequence continues
the single `t0, t1, …` numbering across nested hops via `_Ctx.next_alias`,
sharing one mutable counter and one bind list with its parent context.

To-many value-object array traversal (`nestedExists` / `nestedNotExists`, and a
flat `nested*` predicate whose path crosses a `cardinality: many` member) lowers
here too (COR-3 Phase 7 increment 4, `m-sql` "To-many — exists / notExists and
any-element predicates"): a correlated `EXISTS` over a guarded `jsonb_array_
elements` unnest, continuing the same `_Ctx.next_alias` sequence navigation
already uses. The array-type guard (`Dialect.array_guard`, abbreviated `<arr>`
below) keeps the strict `jsonb_array_elements` from erroring on a non-array
value, folding it to zero elements exactly like a NULL column or a missing key
(m-op-algebra absence collapse). A flat predicate crossing a `many` member is
**any-element** and self-guards independently per predicate (two ANDed flat
predicates open two independent `EXISTS` subqueries, `m-value-object-018`); a
scoped `nestedExists`/`nestedNotExists` `where` is **same-element** — every
element predicate lowers against the SAME unnested alias, element-relative
(no `Class.valueObject` prefix). This claim is Postgres-only; MariaDB's
`json_contains`/`json_length` containment family is documented in `m-sql` but
not goldened for this target and is not implemented here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, assert_never

from parallax.core import inheritance
from parallax.core.descriptor import (
    Entity,
    Metamodel,
    NestedValueObject,
    Relationship,
    ValueObject,
    ValueObjectAttribute,
    VoPathMiss,
    column_order,
    find_value_object,
    find_vo_member,
    resolve_vo_leaf,
)
from parallax.core.dialect import Dialect, LockMode
from parallax.core.op_algebra import (
    All,
    And,
    AsOf,
    AsOfRange,
    Between,
    Comparison,
    DeepFetch,
    Distinct,
    Exists,
    Group,
    History,
    Limit,
    Membership,
    Narrow,
    Navigate,
    NestedComparison,
    NestedExists,
    NestedMembership,
    NestedNotExists,
    NestedNullCheck,
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    Operation,
    Or,
    OrderBy,
    OrderKey,
    StringMatch,
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
from parallax.core.sql_gen._inheritance import narrow_effective_set as _narrow_effective_set
from parallax.core.sql_gen._inheritance import plan_branch_narrow as _plan_branch_narrow
from parallax.core.sql_gen._inheritance import plan_inheritance_read as _plan_inheritance_read
from parallax.core.sql_gen._inheritance import tag_guard as _tph_tag_guard
from parallax.core.sql_gen._inheritance import tph_tag_column as _tph_tag_column

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

_COMPARATORS: dict[str, str] = {
    "eq": "=",
    "notEq": "<>",
    "greaterThan": ">",
    "greaterThanEquals": ">=",
    "lessThan": "<",
    "lessThanEquals": "<=",
}
_NESTED_COMPARATORS: dict[str, str] = {
    "nestedEq": "=",
    "nestedNotEq": "<>",
    "nestedGt": ">",
    "nestedGte": ">=",
    "nestedLt": "<",
    "nestedLte": "<=",
}


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
    ctx = _Ctx(meta=meta, dialect=dialect, entity=entity)

    proj_sql, proj_binds = _projection(
        entity, dialect, ctx.alias, result_form, include_value_objects=include_value_objects
    )
    ctx.binds.extend(proj_binds)
    select = f"select {'distinct ' if distinct else ''}{proj_sql}"
    parts = [select, f"from {entity.table} {ctx.alias}"]

    where_sql = _lower_predicate(predicate, ctx)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, ctx, distinct, order_keys, limit, lock, relationship_order)

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

    Reuses the op-algebra predicate lowering (:func:`_lower_predicate`) with an
    unaliased column formatter (:attr:`_Ctx.unaliased`) rather than forking SQL
    text assembly — the same `And`/`Or`/`Group`/`Comparison`/... dispatch a read's
    `where` clause lowers through, so a write's rendered predicate can never drift
    from the read compiler's own operator vocabulary. ``op`` MUST be a bare
    predicate (no result-shaping directive survives here — a set-based write
    target is validated bare upstream, `m-unit-work` write-instruction vocabulary
    / `python.md` §5 bare-statement guard); a directive reaching this raises
    :class:`SqlGenError` exactly as it would inside an ordinary read's predicate.
    """
    entity = meta.entity(target)
    ctx = _Ctx(meta=meta, dialect=dialect, entity=entity, unaliased=True)
    where_sql = _lower_predicate(op, ctx)
    return CompiledPredicate(where_sql, tuple(ctx.binds))


def _append_result_shape(
    parts: list[str],
    ctx: _Ctx,
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
        terms = [_order_term(ctx, key, relationship_order) for key in order_keys]
        parts.append("order by " + ", ".join(terms))
    if limit is not None:
        parts.append(ctx.dialect.limit_clause())
        ctx.bind(limit)
    if lock == "locking" and not distinct:
        # The shared-row-lock suffix is the last thing in the statement (after any
        # `where` / `order by` / `limit`); a `distinct` object read suppresses it.
        parts.append(ctx.dialect.read_lock_suffix(ctx.alias))


def _order_term(ctx: _Ctx, key: OrderKey, relationship_order: bool) -> str:
    """One ``order by`` term: `m-deep-fetch`'s declared-relationship NULLs-last
    rule for a NULLABLE key under ``relationship_order``, else the plain form."""
    direction = key.direction or "asc"
    column_sql = ctx.column_of(key.attr)
    if relationship_order and ctx.entity_attribute(key.attr).nullable:
        return ctx.dialect.null_order(column_sql, direction)
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
    ctx = _Ctx(meta=meta, dialect=dialect, entity=entity)
    proj_sql, proj_binds = plan.projection(dialect, ctx.alias)
    ctx.binds.extend(proj_binds)

    select = f"select {'distinct ' if distinct else ''}{proj_sql}"
    parts = [select, f"from {plan.table} {ctx.alias}"]

    inner_sql = _lower_predicate(plan.inner, ctx)
    where_terms = [inner_sql] if inner_sql else []
    if plan.tag_kind != "none":
        # Planned, then bound HERE — after the user predicate above has pushed its
        # own binds (m-sql "Grouped branch predicates": branch-predicate-first,
        # then tag).
        tag_sql, tag_binds = _tph_tag_guard(
            ctx, meta, plan.tag_column, plan.tag_kind, plan.position
        )
        where_terms.append(tag_sql)
        ctx.binds.extend(tag_binds)
    if where_terms:
        parts.append("where " + " and ".join(where_terms))

    _append_result_shape(parts, ctx, distinct, order_keys, limit, lock, relationship_order)
    statement = _normalize(Statement(" ".join(parts), tuple(ctx.binds)))
    return statement, plan.transform


def _lower_branch_narrow(narrow: Narrow, ctx: _Ctx) -> str:
    """A `narrow` node reached MID-predicate (nested inside and/or/not/group) — a
    **grouped branch predicate** (m-sql "Grouped branch predicates"): the
    branch's own operand composes with its own tag guard via `and`, and the
    composition is wrapped in parens whenever there is a branch predicate to
    disambiguate against a sibling branch joined by `or` (`m-inheritance-015`).
    A single narrow with a branch predicate and nothing to combine against
    needs no grouping — but that is the **top-level** narrow shape, intercepted
    before `_lower_predicate` ever runs (`_compile_tph_read`); every narrow this
    function receives is nested, so it always groups when it has two terms.
    """
    plan = _plan_branch_narrow(ctx.meta, ctx.entity, narrow)
    # Branch predicate first, THEN the guard's binds — the same explicit ordering
    # the top-level read above states, for the same reason.
    branch_sql = _lower_predicate(plan.operand, ctx)
    tag_sql, tag_binds = _tph_tag_guard(
        ctx, ctx.meta, plan.tag_column, plan.tag_kind, plan.position
    )
    ctx.binds.extend(tag_binds)
    if not branch_sql:
        return tag_sql
    return f"({branch_sql} and {tag_sql})"


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
        branch_ctx = _Ctx(meta=meta, dialect=dialect, entity=entity)
        proj_sql, proj_binds = branch.projection(dialect, branch_ctx.alias)
        branch_ctx.binds.extend(proj_binds)
        parts = [f"select {proj_sql}", f"from {branch.table} {branch_ctx.alias}"]
        where_sql = _lower_predicate(plan.inner, branch_ctx)
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
    family (``ctx.entity`` stays the read's own `targetEntity`, e.g. an abstract
    position narrowed down to this one concrete), matching the
    table-per-hierarchy concrete-target form.
    """
    ctx = _Ctx(meta=meta, dialect=dialect, entity=entity)
    proj_sql, proj_binds = plan.projection(dialect, ctx.alias)
    ctx.binds.extend(proj_binds)
    select = f"select {'distinct ' if distinct else ''}{proj_sql}"
    parts = [select, f"from {plan.table} {ctx.alias}"]
    where_sql = _lower_predicate(plan.inner, ctx)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, ctx, distinct, order_keys, limit, lock, relationship_order)
    statement = _normalize(Statement(" ".join(parts), tuple(ctx.binds)))
    return statement, plan.transform


# --------------------------------------------------------------------------- #
# Navigation (m-sql "Joins by navigation"; COR-3 Phase 7 increment 3).         #
#                                                                               #
# A `navigate` / `exists` / `notExists` node lowers to a correlated `EXISTS`   #
# (`notExists`: negated) semi-join: the correlation columns are derived        #
# MECHANICALLY from the relationship's declared `join` predicate (the user    #
# never writes a join), never authored or guessed. A polymorphic target       #
# resolves its effective concrete-subtype set exactly as a top-level          #
# inheritance read does (`_narrow_effective_set` / `effective_concrete_       #
# subtypes`, above); the per-hop as-of predicate (if any) already rides       #
# inside `op` as a plain predicate node — `parallax.core.navigate.            #
# canonicalize` injected it upstream — so nothing here is temporal-aware.     #
# --------------------------------------------------------------------------- #
def _resolve_relationship_ref(rel_ref: str, meta: Metamodel) -> Relationship:
    class_name, _, member_name = rel_ref.partition(".")
    entity = meta.entity(class_name)
    for relationship in entity.relationships:
        if relationship.name == member_name:
            return relationship
    raise SqlGenError(  # pragma: no cover - guards an unvalidated operation
        f"{rel_ref!r} names no declared relationship on {entity.name}"
    )


def _parse_join(join: str) -> tuple[str, str]:
    """Split a relationship's `this.<attr> = <Entity>.<attr>` join predicate into
    ``(owner attribute name, related attribute name)`` — the mechanical
    correlation-column derivation `m-navigate` requires."""
    lhs, _, rhs = join.partition(" = ")
    _, _, owner_attr = lhs.partition(".")
    _, _, related_attr = rhs.partition(".")
    return owner_attr, related_attr


def _lower_navigation(op: Navigate | Exists | NotExists, ctx: _Ctx) -> str:
    negate = isinstance(op, NotExists)
    relationship = _resolve_relationship_ref(op.rel, ctx.meta)
    target_entity = ctx.meta.entity(relationship.related_entity)
    owner_attr, related_attr = _parse_join(relationship.join)
    parent_col = ctx.column_of(f"{ctx.entity.name}.{owner_attr}")
    if target_entity.inheritance is not None:
        return _lower_polymorphic_hop(
            relationship, target_entity, op.op, parent_col, related_attr, ctx, negate=negate
        )
    return _lower_simple_hop(target_entity, op.op, parent_col, related_attr, ctx, negate=negate)


def _hop_where(inner: Operation | None, correlation: str, child_ctx: _Ctx, *extra: str) -> str:
    """The correlated sub-select's `where` clause: correlation, then the (optional)
    interior predicate, then any trailing fragment (a TPH tag guard) — the shared
    term order every hop shape below composes (m-sql "Grouped branch predicates":
    a user/interior predicate binds before a framework-injected guard)."""
    terms = [correlation]
    if inner is not None:
        inner_sql = _lower_predicate(inner, child_ctx)
        if inner_sql:
            terms.append(inner_sql)
    terms.extend(extra)
    return " and ".join(terms)


def _lower_simple_hop(
    target_entity: Entity,
    inner: Operation | None,
    parent_col: str,
    related_attr: str,
    ctx: _Ctx,
    *,
    negate: bool,
) -> str:
    """A monomorphic relationship target: one correlated `EXISTS` over its own
    table (m-sql "Joins by navigation")."""
    child_alias = ctx.next_alias()
    child_ctx = ctx.child(target_entity, child_alias)
    correlation = f"{child_ctx.column_of(f'{target_entity.name}.{related_attr}')} = {parent_col}"
    where = _hop_where(inner, correlation, child_ctx)
    keyword = "not exists" if negate else "exists"
    return f"{keyword} (select 1 from {target_entity.table} {child_alias} where {where})"


def _hop_position(
    meta: Metamodel, relatable_entity: str, inner: Operation | None
) -> tuple[tuple[str, ...], Operation | None, bool]:
    """The polymorphic hop's resolved effective position + remaining interior
    predicate, mirroring `_compile_tph_read`'s own top-level narrow interception:
    a top-level `narrow` in the hop's `op` (`m-navigate` "Polymorphic navigation")
    replaces the target's own effective set with its resolved `to` set; otherwise
    the target's own effective concrete-subtype set stands. The third element is
    whether the UNTOUCHED target itself is the family's abstract root (the TPH
    "no tag predicate at all" case, `m-inheritance`).
    """
    if isinstance(inner, Narrow):
        return _narrow_effective_set(meta, inner.to), inner.operand, False
    target = meta.entity(relatable_entity)
    is_bare_root = target.inheritance is not None and target.inheritance.role == "root"
    return (
        tuple(inheritance.effective_concrete_subtypes(meta, relatable_entity)),
        inner,
        is_bare_root,
    )


def _lower_polymorphic_hop(
    relationship: Relationship,
    target_entity: Entity,
    inner: Operation | None,
    parent_col: str,
    related_attr: str,
    ctx: _Ctx,
    *,
    negate: bool,
) -> str:
    """A polymorphic relationship target: table-per-hierarchy lowers to a single
    correlated `EXISTS` with the interior tag predicate (reusing increment 2's
    tag-fragment machinery); table-per-concrete-subtype lowers to a grouped `OR`
    of one correlated `EXISTS` per effective concrete, alphabetical, continuing
    the single alias sequence (m-sql "Polymorphic navigation lowering")."""
    root = inheritance.family_root(ctx.meta, target_entity)
    assert root.inheritance is not None
    position, remaining_inner, is_bare_root = _hop_position(
        ctx.meta, relationship.related_entity, inner
    )
    if root.inheritance.strategy == "table-per-hierarchy":
        tag_kind = "none" if is_bare_root else ("eq" if len(position) == 1 else "in")
        return _lower_tph_hop(
            root, position, remaining_inner, parent_col, related_attr, ctx, tag_kind, negate=negate
        )
    return _lower_tpcs_hop(position, remaining_inner, parent_col, related_attr, ctx, negate=negate)


def _lower_tph_hop(
    root: Entity,
    position: Sequence[str],
    remaining_inner: Operation | None,
    parent_col: str,
    related_attr: str,
    ctx: _Ctx,
    tag_kind: str,
    *,
    negate: bool,
) -> str:
    tag_col = _tph_tag_column(root)
    table = ctx.meta.entity(position[0]).table
    if table is None:  # pragma: no cover - a validated TPH concrete always declares one
        raise SqlGenError(f"{position[0]}: table-per-hierarchy concrete subtype declares no table")
    child_alias = ctx.next_alias()
    # The child context's active entity is the hop's TARGET (possibly abstract):
    # family-wide attribute resolution (`_searchable_attributes`) needs only that
    # `inheritance is not None`, exactly like a top-level inheritance read's ctx.
    child_ctx = ctx.child(ctx.meta.entity(root.name), child_alias)
    correlation = f"{child_ctx.column_of(f'{root.name}.{related_attr}')} = {parent_col}"
    # The guard is PLANNED here but BOUND below, after `_hop_where` has lowered the
    # interior predicate. Passing a bind-as-you-render fragment as an ARGUMENT to
    # `_hop_where` would push the tag bind during argument evaluation — ahead of
    # the interior's own binds — so the SQL text (guard last) and the bind order
    # (guard first) would disagree, which is the COR-43 defect this shape retires.
    tag_fragment: tuple[str, ...] = ()
    tag_binds: tuple[object, ...] = ()
    if tag_kind != "none":
        tag_sql, tag_binds = _tph_tag_guard(child_ctx, ctx.meta, tag_col, tag_kind, position)
        tag_fragment = (tag_sql,)
    where = _hop_where(remaining_inner, correlation, child_ctx, *tag_fragment)
    child_ctx.binds.extend(tag_binds)
    keyword = "not exists" if negate else "exists"
    return f"{keyword} (select 1 from {table} {child_alias} where {where})"


def _lower_tpcs_hop(
    position: Sequence[str],
    remaining_inner: Operation | None,
    parent_col: str,
    related_attr: str,
    ctx: _Ctx,
    *,
    negate: bool,
) -> str:
    if len(position) == 1:
        return _lower_tpcs_branch(
            ctx.meta.entity(position[0]),
            remaining_inner,
            parent_col,
            related_attr,
            ctx,
            negate=negate,
        )
    branch_sqls = [
        _lower_tpcs_branch(
            ctx.meta.entity(name), remaining_inner, parent_col, related_attr, ctx, negate=False
        )
        for name in position
    ]
    grouped = f"({' or '.join(branch_sqls)})"
    return f"not {grouped}" if negate else grouped


def _lower_tpcs_branch(
    concrete: Entity,
    remaining_inner: Operation | None,
    parent_col: str,
    related_attr: str,
    ctx: _Ctx,
    *,
    negate: bool,
) -> str:
    if concrete.table is None:  # pragma: no cover - a validated TPCS concrete always has one
        raise SqlGenError(f"{concrete.name}: table-per-concrete-subtype subtype declares no table")
    child_alias = ctx.next_alias()
    child_ctx = ctx.child(concrete, child_alias)
    correlation = f"{child_ctx.column_of(f'{concrete.name}.{related_attr}')} = {parent_col}"
    where = _hop_where(remaining_inner, correlation, child_ctx)
    keyword = "not exists" if negate else "exists"
    return f"{keyword} (select 1 from {concrete.table} {child_alias} where {where})"


# --------------------------------------------------------------------------- #
# Predicate lowering.                                                          #
# --------------------------------------------------------------------------- #
def _lower_predicate(op: Operation, ctx: _Ctx) -> str:
    """Lower one predicate node to a SQL fragment, appending binds in order."""
    match op:
        case All():
            return ""
        case NoneOp():
            return "1 = 0"
        case Comparison(op=tag, attr=attr, value=value):
            ctx.bind(value)
            return f"{ctx.column_of(attr)} {_COMPARATORS[tag]} ?"
        case Between(attr=attr, lower=lower, upper=upper):
            ctx.bind(lower)
            ctx.bind(upper)
            return f"{ctx.column_of(attr)} between ? and ?"
        case NullCheck(op=tag, attr=attr):
            col = ctx.column_of(attr)
            return f"{col} is null" if tag == "isNull" else f"not {col} is null"
        case StringMatch():
            return _lower_string(op, ctx)
        case Membership(op=tag, attr=attr, values=values):
            holes = ", ".join("?" for _ in values)
            for value in values:
                ctx.bind(value)
            fragment = f"{ctx.column_of(attr)} in ({holes})"
            return fragment if tag == "in" else f"not {fragment}"
        case And(operands=operands):
            return " and ".join(_lower_predicate(o, ctx) for o in operands)
        case Or(operands=operands):
            return " or ".join(_lower_predicate(o, ctx) for o in operands)
        case Not(operand=operand):
            return f"not {_lower_predicate(operand, ctx)}"
        case Group(operand=operand):
            return f"({_lower_predicate(operand, ctx)})"
        case NestedComparison() | NestedMembership() | NestedNullCheck():
            return _lower_nested(op, ctx)
        case NestedExists() | NestedNotExists():
            return _lower_nested_exists(op, ctx)
        case Narrow():
            return _lower_branch_narrow(op, ctx)
        case Navigate() | Exists() | NotExists():
            return _lower_navigation(op, ctx)
        case DeepFetch():
            raise SqlGenError(
                "deep fetch (eager graph materialization across relationship levels) lands "
                "with the snapshot branch's deep-fetch + materialization increment (COR-3 "
                "Phase 7 increment 5; ledger D-12) — relationship navigation itself lowers "
                "(increment 3)"
            )
        case AsOf() | AsOfRange() | History():
            # Temporal reads are lowered by `m-temporal-read` (auto-injected as-of
            # predicate + default-latest injection) into ordinary predicate nodes
            # BEFORE compile_read runs — the module DAG forbids m-sql from importing
            # m-temporal-read, so the composition happens in the caller (the
            # conformance engine's canonicalize step). Reaching this branch means a
            # temporal wrapper survived un-canonicalized, which is a wiring error, not
            # an unsupported node.
            raise SqlGenError(
                "temporal wrapper reached m-sql un-lowered; canonicalize the read with "
                "m-temporal-read.inject_as_of before compile_read (m-sql cannot import "
                "m-temporal-read per the module DAG)"
            )
        case OrderBy() | Limit() | Distinct():
            raise SqlGenError("result-shaping directive nested inside a predicate")
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


def _lower_string(op: StringMatch, ctx: _Ctx) -> str:
    col = ctx.column_of(op.attr)
    if op.op in ("like", "notLike"):
        ctx.bind(op.value)
        col_expr = f"lower({col})" if op.case_insensitive else col
        rhs = "lower(?)" if op.case_insensitive else "?"
        fragment = f"{col_expr} like {rhs}"
        return fragment if op.op == "like" else fragment.replace(" like ", " not like ", 1)
    # The affix pattern is folded to lower case under case-insensitive matching,
    # so the pattern bind is already lowercased (the corpus's affix convention);
    # `like`/`notLike` keep the pattern verbatim and rely on `lower(?)` alone.
    literal = op.value.lower() if op.case_insensitive else op.value
    pattern, needs_escape = _affix_pattern(op.op, literal)
    ctx.bind(pattern)
    col_expr = f"lower({col})" if op.case_insensitive else col
    rhs = "lower(?)" if op.case_insensitive else "?"
    fragment = f"{col_expr} like {rhs}"
    if needs_escape:
        ctx.bind("\\")
        fragment = f"{fragment} escape ?"
    return fragment


def _affix_pattern(kind: str, value: str) -> tuple[str, bool]:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    needs_escape = escaped != value
    if kind == "startsWith":
        return f"{escaped}%", needs_escape
    if kind == "endsWith":
        return f"%{escaped}", needs_escape
    return f"%{escaped}%", needs_escape


# --------------------------------------------------------------------------- #
# Value-object nested predicates (m-value-object; resolved inline — the DAG    #
# forbids m-op-algebra / m-sql from importing m-value-object).                 #
# --------------------------------------------------------------------------- #
def _lower_nested(op: NestedComparison | NestedMembership | NestedNullCheck, ctx: _Ctx) -> str:
    """Lower a flat `nested*` predicate (m-op-algebra "Nested value-object
    predicates"): a scalar extraction against `ctx.alias` when the path stays
    within `one`-cardinality members, or — when it crosses a `cardinality: many`
    member — the any-element array-traversal form (m-sql "To-many — exists /
    notExists and any-element predicates"; `m-value-object-017/-018/-021`)."""
    vo, segments = _flat_vo_path(op.path, ctx.entity)
    crossing = _split_at_many(vo, segments)
    if crossing is not None:
        return _lower_any_element(op, vo, crossing, ctx)
    leaf = _resolve_leaf(vo, segments)
    # The document column is the TARGET's own, so it renders through `own_column`
    # and goes bare in a write's unaliased predicate (m-sql rule 1).
    extraction, path_binds = ctx.dialect.nested_extract(ctx.own_column(vo.column), segments)
    ctx.binds.extend(path_binds)
    return _lower_comparator(op, extraction, leaf.type, ctx)


def _flat_vo_path(path: str, entity: Entity) -> tuple[ValueObject, tuple[str, ...]]:
    """Parse a flat `Class.valueObject(.valueObject)*.attribute` reference
    (m-op-algebra) into its top-level value object and the path segments after
    it (which may cross zero or more nested value objects before reaching a
    leaf, or a `many` member — `_split_at_many` tells the two apart)."""
    parts = path.split(".")
    if len(parts) < 3:
        raise SqlGenError(f"nested path {path!r} needs Class.valueObject.attribute")
    _entity_name, vo_name, *segments = parts
    return _value_object(entity, vo_name), tuple(segments)


def _lower_comparator(
    op: NestedComparison | NestedMembership | NestedNullCheck,
    extraction: str,
    leaf_type: str,
    ctx: _Ctx,
) -> str:
    """Render one resolved extraction's comparator fragment (m-sql "valueObject
    — structured-column read and filter" / "The flat `nested*` operator
    family"), binding extraction-then-comparator in that order. Shared by the
    plain scalar path, the flat any-element lowering, and the same-element
    scoped `where` lowering below — only how `extraction` was resolved differs.
    """
    if isinstance(op, NestedComparison):
        casted = ctx.dialect.nested_cast(extraction, leaf_type)
        ctx.bind(op.value)
        # nestedNotEq lowers to `not <ext> = ?` (the corpus form), not `<ext> <> ?`.
        if op.op == "nestedNotEq":
            return f"not {casted} = ?"
        return f"{casted} {_NESTED_COMPARATORS[op.op]} ?"
    if isinstance(op, NestedMembership):
        casted = ctx.dialect.nested_cast(extraction, leaf_type)
        holes = ", ".join("?" for _ in op.values)
        for value in op.values:
            ctx.bind(value)
        return f"{casted} in ({holes})"
    if op.op == "nestedIsNull":
        return f"{extraction} is null"
    return f"not {extraction} is null"


def _split_at_many(
    vo: ValueObject, segments: Sequence[str]
) -> tuple[ValueObject | NestedValueObject, tuple[str, ...], tuple[str, ...]] | None:
    """Split a flat predicate's path at the first `cardinality: many` hop
    crossed while walking from `vo` (m-op-algebra "Flat predicates through a
    `many` segment mean any element matches"). Returns ``(the many container,
    the segments reaching it from vo's own document column, the remaining
    segments addressing a field WITHIN the element)`` — or ``None`` when the
    walk never crosses a `many` member (the plain scalar-extraction case
    `_lower_nested` handles directly).
    """
    if vo.cardinality == "many":
        return vo, (), tuple(segments)
    container: ValueObject | NestedValueObject = vo
    for index, segment in enumerate(segments):
        member = find_vo_member(container, segment)
        if not isinstance(member, NestedValueObject):
            return None  # reached a scalar leaf (or an unresolved segment) uncrossed
        if member.cardinality == "many":
            return member, tuple(segments[: index + 1]), tuple(segments[index + 1 :])
        container = member
    return None


def _lower_any_element(
    op: NestedComparison | NestedMembership | NestedNullCheck,
    vo: ValueObject,
    crossing: tuple[ValueObject | NestedValueObject, tuple[str, ...], tuple[str, ...]],
    ctx: _Ctx,
) -> str:
    """Any-element lowering for a flat `nested*` predicate crossing a `many`
    member (m-sql "To-many — exists / notExists and any-element predicates"):
    an independent correlated `EXISTS` over the guarded unnest, the field
    resolved against the SAME unnested element alias (never against `t0`).
    Each such predicate self-guards and self-aliases — two ANDed flat
    predicates through the same array open TWO independent subqueries
    (`m-value-object-018`'s any-element-independence witness), never one
    shared alias (that would be the same-element `nestedExists`/`where` form
    below).
    """
    container, pre, post = crossing
    if not post:
        raise SqlGenError(
            f"nested path {op.path!r} ends on the `many` array itself, not a field "
            "within its elements"
        )
    leaf = _resolve_leaf(container, post)
    # The owning document column is the target's own (bare under `unaliased`); the
    # unnested ELEMENT is not, and stays alias-qualified either way — this very
    # subquery declares `array_alias`, so there is no alias here to leak.
    guard_sql, guard_binds = ctx.dialect.array_guard(ctx.own_column(vo.column), pre)
    ctx.binds.extend(guard_binds)
    array_alias = ctx.next_alias()
    extraction, path_binds = ctx.dialect.nested_extract(
        ctx.dialect.qualified(array_alias, "value"), post
    )
    ctx.binds.extend(path_binds)
    comparator = _lower_comparator(op, extraction, leaf.type, ctx)
    return (
        f"exists (select 1 from jsonb_array_elements({guard_sql}) {array_alias} where {comparator})"
    )


# --------------------------------------------------------------------------- #
# `nestedExists` / `nestedNotExists` (m-sql "To-many — exists / notExists and  #
# any-element predicates"; COR-3 Phase 7 increment 4).                        #
# --------------------------------------------------------------------------- #
def _lower_nested_exists(op: NestedExists | NestedNotExists, ctx: _Ctx) -> str:
    """A bare form is a non-empty / empty-or-absent test over the guarded
    unnest; a scoped `where` composes its element predicate on the SAME
    unnested alias (same-element semantics, m-value-object — as opposed to the
    any-element flat form above, which never shares an alias across
    predicates). Postgres `EXISTS` is never NULL, so the negated forms need no
    `coalesce` wrap: `not exists (...)` over zero unnested elements is already
    true (m-sql, explicit). MariaDB's containment form DOES need one — but this
    claim is Postgres-only and that form is not implemented here.
    """
    vo, pre, container = _resolve_vo_terminus(op.path, ctx.entity)
    if container.cardinality != "many":
        raise SqlGenError(
            f"nestedExists/nestedNotExists over a `one`-cardinality value object "
            f"({op.path!r}) has no goldened lowering yet"
        )
    guard_sql, guard_binds = ctx.dialect.array_guard(ctx.own_column(vo.column), pre)
    ctx.binds.extend(guard_binds)
    array_alias = ctx.next_alias()
    inner = f"select 1 from jsonb_array_elements({guard_sql}) {array_alias}"
    if op.where is not None:
        where_sql = _lower_element_predicate(op.where, container, array_alias, ctx)
        inner = f"{inner} where {where_sql}"
    keyword = "not exists" if isinstance(op, NestedNotExists) else "exists"
    return f"{keyword} ({inner})"


def _resolve_vo_terminus(
    path: str, entity: Entity
) -> tuple[ValueObject, tuple[str, ...], ValueObject | NestedValueObject]:
    """Resolve a `nestedExists`/`nestedNotExists` value-object-TERMINATED path
    (`Class.valueObject(.valueObject)*`, m-op-algebra) to its top-level value
    object, the full segment chain from that object's own document column to
    the terminal member, and the terminal container itself (`vo` unchanged
    when the path names the top-level object directly, no further segments).
    """
    parts = path.split(".")
    if len(parts) < 2:
        raise SqlGenError(f"nested path {path!r} needs at least Class.valueObject")
    _entity_name, vo_name, *segments = parts
    vo = _value_object(entity, vo_name)
    container: ValueObject | NestedValueObject = vo
    for segment in segments:
        member = find_vo_member(container, segment)
        if not isinstance(member, NestedValueObject):
            raise SqlGenError(
                f"nested path {path!r}: {segment!r} does not name a nested value object"
            )
        container = member
    return vo, tuple(segments), container


def _lower_element_predicate(
    op: Operation, container: ValueObject | NestedValueObject, alias: str, ctx: _Ctx
) -> str:
    """Lower a scoped `nestedExists`/`nestedNotExists` `where` compound
    (m-op-algebra `elementPredicate`; m-value-object same-element semantics):
    every leaf's path is element-relative (`type`, `geo.country` — no leading
    `Class.valueObject`) and resolves against `container`, the SAME array
    element every predicate here shares — extracted via the unnested element
    alias (`t1.value`), never re-descending through `Class.valueObject`. The
    serde's `elementPredicate` grammar admits only the nested* family plus the
    boolean combinators here, so this dispatch need not re-derive that
    restriction.
    """
    match op:
        case NestedComparison(path=path) | NestedMembership(path=path) | NestedNullCheck(path=path):
            segments = tuple(path.split("."))
            leaf = _resolve_leaf(container, segments)
            # `alias` names the unnest this statement itself declared, so the
            # element reference is alias-qualified in a write's predicate too.
            extraction, path_binds = ctx.dialect.nested_extract(
                ctx.dialect.qualified(alias, "value"), segments
            )
            ctx.binds.extend(path_binds)
            return _lower_comparator(op, extraction, leaf.type, ctx)
        case And(operands=operands):
            return " and ".join(
                _lower_element_predicate(o, container, alias, ctx) for o in operands
            )
        case Or(operands=operands):
            return " or ".join(_lower_element_predicate(o, container, alias, ctx) for o in operands)
        case Not(operand=operand):
            return f"not {_lower_element_predicate(operand, container, alias, ctx)}"
        case Group(operand=operand):
            return f"({_lower_element_predicate(operand, container, alias, ctx)})"
        case _:  # pragma: no cover - the elementPredicate schema admits nothing else here
            raise SqlGenError(
                f"{op!r} is not a legal nestedExists/nestedNotExists element predicate "
                "(m-op-algebra elementPredicate)"
            )


def _value_object(entity: Entity, name: str) -> ValueObject:
    vo = find_value_object(entity, name)
    if vo is None:
        raise SqlGenError(f"{entity.name}: {name!r} is not a declared value object")
    return vo


def _resolve_leaf(
    vo: ValueObject | NestedValueObject, segments: Sequence[str]
) -> ValueObjectAttribute:
    """Resolve dotted ``segments`` against ``vo`` via the shared, error-neutral
    `parallax.core.descriptor.vo_path` walk (S3: the same one `m-op-algebra`'s
    operation validator uses), classifying a miss into `SqlGenError` verbatim."""
    result = resolve_vo_leaf(vo, segments)
    if isinstance(result, VoPathMiss):
        if result.reason == "scalar-continues":
            raise SqlGenError(f"value-object path continues past scalar {result.segment!r}")
        if result.reason == "ends-on-nested":
            raise SqlGenError("value-object path does not reach a scalar leaf")
        raise SqlGenError(f"value-object path segment {result.segment!r} is undeclared")
    return result


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
