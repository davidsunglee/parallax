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
from dataclasses import dataclass, field
from typing import Literal, assert_never, cast

from parallax.core import inheritance
from parallax.core.descriptor import (
    Attribute,
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

__all__ = [
    "FamilyVariantPlan",
    "ResultForm",
    "SqlGenError",
    "Statement",
    "apply_family_variant",
    "compile_read",
    "family_variant_plan",
]

# The read's consumption lane (m-sql *Read projection*, *Result form*): a
# ``row``-form read (the values lane) projects scalars only; an ``instance``-form
# read (the object lane — a find / snapshot / deep-fetch whose rows materialize
# into instances) additionally projects the value-object document columns (slot 4).
ResultForm = Literal["row", "instance"]

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


def _new_binds() -> list[object]:
    return []


class SqlGenError(ValueError):
    """An operation cannot be lowered to SQL (unsupported node or unbound reference)."""


@dataclass(frozen=True, slots=True)
class Statement:
    """One compiled SQL statement in canonical form and its ordered binds."""

    sql: str
    binds: tuple[object, ...] = ()


def _new_alias_seq() -> list[int]:
    # The next alias INDEX after this context's own `t0` — a one-element mutable
    # cell so every `_Ctx` created via `.child()` (a correlated-EXISTS interior,
    # nested however deep) shares and advances the SAME counter, continuing the
    # single `t0, t1, …` sequence (m-sql rule 1). A fresh top-level statement
    # (a plain read, a TPH read, or each TPCS `union all` branch — which restarts
    # its own alias scheme at `t0`) gets its own counter via this default factory.
    return [1]


@dataclass(frozen=True, slots=True)
class _Ctx:
    """Lowering context: the resolved target entity, its dialect, and its alias."""

    meta: Metamodel
    dialect: Dialect
    entity: Entity
    alias: str = "t0"
    binds: list[object] = field(default_factory=_new_binds)
    alias_seq: list[int] = field(default_factory=_new_alias_seq)

    def column_of(self, attr_ref: str) -> str:
        attribute = self.entity_attribute(attr_ref)
        return self.dialect.qualified(self.alias, attribute.column)

    def next_alias(self) -> str:
        """The next alias in this statement's single continuing sequence."""
        index = self.alias_seq[0]
        self.alias_seq[0] = index + 1
        return f"t{index}"

    def child(self, entity: Entity, alias: str) -> _Ctx:
        """A nested context for a correlated hop's interior: the SAME bind list
        and alias counter (so a nested hop's binds/aliases continue this
        statement's single sequence), a different active entity/alias."""
        return _Ctx(
            meta=self.meta,
            dialect=self.dialect,
            entity=entity,
            alias=alias,
            binds=self.binds,
            alias_seq=self.alias_seq,
        )

    def entity_attribute(self, attr_ref: str) -> Attribute:
        _, _, name = attr_ref.partition(".")
        for attribute in self._searchable_attributes():
            if attribute.name == name:
                return attribute
        raise SqlGenError(f"{attr_ref!r} names no attribute on {self.entity.name}")

    def _searchable_attributes(self) -> tuple[Attribute, ...]:
        """The attributes an `attr_ref`'s class-name-qualified name may resolve to.

        A plain entity resolves only against its own declared attributes
        (unchanged). An inheritance participant resolves against its **whole
        family** (`parallax.core.inheritance.family_attributes`): the read's own
        predicate may reference a root-inherited attribute through a concrete
        target's own class name, and a `narrow` branch predicate references that
        branch's own attribute by its own class name — narrow-position validity
        for the reference is enforced upstream (`m-op-algebra`'s model-aware
        validator), so this need only widen the search, never re-validate scope.
        """
        if self.entity.inheritance is None:
            return self.entity.attributes
        return inheritance.family_attributes(self.meta, self.entity)

    def bind(self, value: object) -> None:
        self.binds.append(value)


# --------------------------------------------------------------------------- #
# Projection.                                                                  #
# --------------------------------------------------------------------------- #
def _projection(
    entity: Entity, dialect: Dialect, alias: str, result_form: ResultForm
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
    contract, m-value-object). A row-form read omits them.
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
    if result_form == "instance":
        exprs.extend(dialect.qualified(alias, vo.column) for vo in entity.value_objects)
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
    result_form: ResultForm = "row",
    lock: LockMode | None = None,
    relationship_order: bool = False,
) -> Statement:
    """Compile a read operation to one canonical ``Statement`` for ``dialect``.

    ``result_form`` selects the projection lane (m-sql *Read projection*): a
    **row-form** read (the values lane — the corpus predicate `read` cases and the
    internal materialized-write resolving read) projects scalars only; an
    **instance-form** read (the object lane — a find / snapshot / deep-fetch whose
    rows materialize into instances) additionally projects the value-object document
    columns. The conformance engine derives it from the case's asserted result
    member (`then.rows` = row-form; `then.graph` / `then.graphs` = instance-form).

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
    if entity.inheritance is not None:
        return _compile_inheritance_read(
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
    ctx = _Ctx(meta=meta, dialect=dialect, entity=entity)

    proj_sql, proj_binds = _projection(entity, dialect, ctx.alias, result_form)
    ctx.binds.extend(proj_binds)
    select = f"select {'distinct ' if distinct else ''}{proj_sql}"
    parts = [select, f"from {entity.table} {ctx.alias}"]

    where_sql = _lower_predicate(predicate, ctx)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, ctx, distinct, order_keys, limit, lock, relationship_order)

    return _normalize(Statement(" ".join(parts), tuple(ctx.binds)))


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
# The read's queried **position** is the resolved effective concrete-subtype   #
# set the whole read targets: a top-level `narrow` (the read's ENTIRE predicate #
# after peeling result-shaping directives) replaces `targetEntity`'s own        #
# position with its resolved `to` set; a `narrow` reached anywhere else (nested #
# inside and/or/not/group) is a local BRANCH guard and never changes the read's #
# own position (`m-inheritance-015`'s `or` of two narrowed branches is the      #
# corpus witness — the projection and the whole-family "no tag" rule stay keyed #
# to `targetEntity`, only each branch's own tag guard is injected).             #
# --------------------------------------------------------------------------- #
def _narrow_effective_set(meta: Metamodel, to: Sequence[str]) -> tuple[str, ...]:
    """A narrow's resolved, canonically alphabetical effective concrete set.

    `validate_operation` runs upstream and guarantees the resolved set is
    non-empty and a subset of the active position (`m-op-algebra` "the four-step
    validation rule") before this compiler ever sees the operation, so this need
    only resolve and canonicalize — never re-validate.
    """
    resolved: set[str] = set()
    for name in to:
        resolved.update(inheritance.effective_concrete_subtypes(meta, name))
    return tuple(sorted(resolved))


def _superset_columns(meta: Metamodel, position: Sequence[str]) -> list[tuple[Attribute, str]]:
    """The stable superset column list for a read over ``position`` (m-sql
    *Abstract-read projection* / *union-all lowering*): each ancestor's own
    attributes in ancestry order, then each position concrete's own attributes in
    canonical alphabetical order — paired with the declaring entity's name so a
    table-per-concrete-subtype branch can tell which columns it physically owns.
    """
    columns: list[tuple[Attribute, str]] = []
    for ancestor in inheritance.ancestor_chain(meta, position):
        columns.extend((attribute, ancestor.name) for attribute in ancestor.attributes)
    for name in sorted(position):
        entity = meta.entity(name)
        columns.extend((attribute, entity.name) for attribute in entity.attributes)
    return columns


def _superset_value_objects(meta: Metamodel, position: Sequence[str]) -> list[ValueObject]:
    """The value objects reachable from ``position``, same ordering rule as
    :func:`_superset_columns` (ancestry prefix, then alphabetical own blocks) —
    the shared `inheritance.superset_value_objects` resolution (also used by
    `m-snapshot-read`'s row-decoding superset)."""
    return inheritance.superset_value_objects(meta, position)


def _compile_inheritance_read(
    entity: Entity,
    predicate: Operation,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    meta: Metamodel,
    dialect: Dialect,
    target: str,
    result_form: ResultForm,
    lock: LockMode | None,
    relationship_order: bool = False,
) -> Statement:
    """Dispatch an inheritance-family read to its strategy's lowering (m-inheritance
    admits exactly two strategies; a third is rejected long before SQL, by the
    model-aware descriptor validator)."""
    root = inheritance.family_root(meta, entity)
    assert root.inheritance is not None  # a family root always carries its own block
    strategy = root.inheritance.strategy
    if strategy == "table-per-hierarchy":
        return _compile_tph_read(
            entity,
            root,
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
    if strategy == "table-per-concrete-subtype":
        return _compile_tpcs_read(
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
    # m-inheritance admits only the two strategies above; a descriptor failing to
    # declare one is refused by the model-aware validator long before a read
    # reaches this compiler.
    raise SqlGenError(
        f"{root.name}: unrecognized inheritance strategy {strategy!r}"
    )  # pragma: no cover


def _compile_tph_read(
    entity: Entity,
    root: Entity,
    predicate: Operation,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    meta: Metamodel,
    dialect: Dialect,
    target: str,
    result_form: ResultForm,
    lock: LockMode | None,
    relationship_order: bool = False,
) -> Statement:
    """Table-per-hierarchy: one shared correlated `EXISTS`-free single-table SELECT
    (m-sql "Inheritance — table-per-hierarchy lowering").

    The tag PREDICATE (none / `=` / `in`) is keyed purely to the resolved
    position's SIZE — one concrete lowers to `=` whether reached by a direct
    concrete `targetEntity` or a narrow, several lower to `in`, and only an
    untouched abstract-**root** `targetEntity` (no top-level narrow at all) gets
    no tag predicate at all. The raw tag column PROJECTION (slot 2) is instead
    keyed to whether `targetEntity` itself is abstract — independent of the
    narrow's resolved cardinality (`m-inheritance-012`: `Animal` narrowed to the
    single concrete `Dog` still projects `t0.kind` and still carries
    `familyVariant`, because the caller queried the polymorphic `Animal`
    position). These are deliberately two different conditions.
    """
    assert root.inheritance is not None
    tag_col = root.inheritance.tag_column
    if tag_col is None:  # pragma: no cover - a validated TPH root always declares one
        raise SqlGenError(f"{root.name}: table-per-hierarchy root declares no tag column")
    abstract_target = entity.inheritance is not None and entity.inheritance.role in (
        "root",
        "abstract-subtype",
    )

    if isinstance(predicate, Narrow):
        position = _narrow_effective_set(meta, predicate.to)
        inner = predicate.operand
        tag_kind = "eq" if len(position) == 1 else "in"
    else:
        position = tuple(inheritance.effective_concrete_subtypes(meta, target))
        inner = predicate
        is_bare_root = entity.inheritance is not None and entity.inheritance.role == "root"
        tag_kind = "none" if is_bare_root else ("eq" if len(position) == 1 else "in")

    table = meta.entity(position[0]).table
    if table is None:  # pragma: no cover - a validated TPH concrete always declares one
        raise SqlGenError(f"{position[0]}: table-per-hierarchy concrete subtype declares no table")

    ctx = _Ctx(meta=meta, dialect=dialect, entity=entity)
    proj_exprs: list[str] = []
    for attribute, _owner in _superset_columns(meta, position):
        expr, extra = dialect.project(ctx.alias, attribute.column, attribute.type)
        proj_exprs.append(expr)
        ctx.binds.extend(extra)
    if abstract_target:
        # Slot 2 (m-sql resolved Q6): the raw tag column, projected iff the read's
        # OWN targetEntity is abstract — never derived from the resolved position.
        proj_exprs.append(dialect.qualified(ctx.alias, tag_col))
    if result_form == "instance":
        proj_exprs.extend(
            dialect.qualified(ctx.alias, vo.column)
            for vo in _superset_value_objects(meta, position)
        )

    select = f"select {'distinct ' if distinct else ''}{', '.join(proj_exprs)}"
    parts = [select, f"from {table} {ctx.alias}"]

    inner_sql = _lower_predicate(inner, ctx)
    where_terms = [inner_sql] if inner_sql else []
    if tag_kind != "none":
        where_terms.append(_tph_tag_fragment(ctx, meta, tag_col, tag_kind, position))
    if where_terms:
        parts.append("where " + " and ".join(where_terms))

    _append_result_shape(parts, ctx, distinct, order_keys, limit, lock, relationship_order)
    return _normalize(Statement(" ".join(parts), tuple(ctx.binds)))


def _tph_tag_fragment(
    ctx: _Ctx, meta: Metamodel, tag_col: str, tag_kind: str, position: Sequence[str]
) -> str:
    """The tag-predicate fragment for ``position`` (m-sql *Tag-predicate
    selection*): `t0.<tag> = ?` for one concrete, `t0.<tag> in (?, …)` for several
    — the `in` list in ``position``'s already-canonical alphabetical order, so its
    tag values follow suit. Binds append to ``ctx`` in that same order.
    """
    col = ctx.dialect.qualified(ctx.alias, tag_col)
    tag_values = [_tag_value(meta, name) for name in position]
    if tag_kind == "eq":
        ctx.bind(tag_values[0])
        return f"{col} = ?"
    holes = ", ".join("?" for _ in tag_values)
    for value in tag_values:
        ctx.bind(value)
    return f"{col} in ({holes})"


def _tag_value(meta: Metamodel, concrete_name: str) -> str:
    concrete = meta.entity(concrete_name)
    if concrete.inheritance is None or concrete.inheritance.tag_value is None:
        raise SqlGenError(  # pragma: no cover - a validated TPH concrete always declares one
            f"{concrete_name}: table-per-hierarchy concrete subtype declares no tagValue"
        )
    return concrete.inheritance.tag_value


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
    root = inheritance.family_root(ctx.meta, ctx.entity)
    if root.inheritance is None or root.inheritance.strategy != "table-per-hierarchy":
        raise SqlGenError(
            "a narrow nested inside and/or/not/group over a table-per-concrete-subtype "
            "family has no goldened lowering yet"
        )
    tag_col = root.inheritance.tag_column
    if tag_col is None:  # pragma: no cover - a validated TPH root always declares one
        raise SqlGenError(f"{root.name}: table-per-hierarchy root declares no tag column")
    position = _narrow_effective_set(ctx.meta, narrow.to)
    tag_kind = "eq" if len(position) == 1 else "in"
    branch_sql = _lower_predicate(narrow.operand, ctx)
    tag_sql = _tph_tag_fragment(ctx, ctx.meta, tag_col, tag_kind, position)
    if not branch_sql:
        return tag_sql
    return f"({branch_sql} and {tag_sql})"


def _compile_tpcs_read(
    entity: Entity,
    predicate: Operation,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    meta: Metamodel,
    dialect: Dialect,
    target: str,
    result_form: ResultForm,
    lock: LockMode | None,
    relationship_order: bool = False,
) -> Statement:
    """Table-per-concrete-subtype (m-sql "Inheritance — table-per-concrete-subtype
    lowering"): a position resolving to ONE concrete is an ordinary single-table
    read (no union, no `familyVariant`) regardless of how that single concrete was
    reached; a position resolving to two or more concretes lowers to canonical
    `union all`, one branch per concrete in alphabetical order, every branch
    restarting its own alias at `t0` and projecting the same stable superset with
    `cast(null as <type>)` placeholders for columns it does not own, plus its own
    `familyVariant` subtype-name literal. Unlike table-per-hierarchy, this
    single-vs-several split is the ONLY thing that decides `familyVariant` here —
    there is no table-per-concrete-subtype analogue of the abstract-`targetEntity`
    slot-2 rule, because a resolved single concrete has no shared table to
    discriminate and no sibling branch to distinguish it from (m-sql, explicit).
    """
    if isinstance(predicate, Narrow):
        position = _narrow_effective_set(meta, predicate.to)
        inner = predicate.operand
    else:
        position = tuple(inheritance.effective_concrete_subtypes(meta, target))
        inner = predicate

    if len(position) == 1:
        return _compile_tpcs_single(
            meta.entity(position[0]),
            inner,
            distinct,
            order_keys,
            limit,
            meta,
            dialect,
            entity,
            result_form,
            lock,
            position,
            relationship_order,
        )

    if distinct or order_keys or limit is not None or lock is not None:
        raise SqlGenError(
            "distinct / orderBy / limit / a read-lock suffix over a table-per-concrete-"
            "subtype union-all read (2+ effective concretes) has no goldened lowering yet"
        )
    if result_form == "instance":
        raise SqlGenError(
            "instance-form (value-object document) projection over a table-per-concrete-"
            "subtype union-all read has no goldened lowering yet"
        )

    columns = _superset_columns(meta, position)
    branch_sqls: list[str] = []
    all_binds: list[object] = []
    for name in position:
        concrete = meta.entity(name)
        if concrete.table is None:  # pragma: no cover - a validated TPCS concrete always has one
            raise SqlGenError(f"{name}: table-per-concrete-subtype subtype declares no table")
        owned = {ancestor.name for ancestor in inheritance.ancestor_chain(meta, (name,))} | {name}
        branch_ctx = _Ctx(meta=meta, dialect=dialect, entity=entity)
        proj_exprs: list[str] = []
        for attribute, owner in columns:
            if owner in owned:
                expr, extra = dialect.project(branch_ctx.alias, attribute.column, attribute.type)
                proj_exprs.append(expr)
                branch_ctx.binds.extend(extra)
            else:
                cast_type = dialect.null_cast(attribute.type, attribute.max_length)
                proj_exprs.append(f"cast(null as {cast_type}) {attribute.column}")
        # Slot 3 (the settled TPH/TPCS asymmetry): TPCS projects the variant NAME
        # literal per branch directly — there is no tag column to derive it from.
        proj_exprs.append(f"'{name}' family_variant")
        select = f"select {', '.join(proj_exprs)}"
        parts = [select, f"from {concrete.table} {branch_ctx.alias}"]
        where_sql = _lower_predicate(inner, branch_ctx)
        if where_sql:
            parts.append(f"where {where_sql}")
        branch_sqls.append(" ".join(parts))
        all_binds.extend(branch_ctx.binds)

    return _normalize(Statement(" union all ".join(branch_sqls), tuple(all_binds)))


def _compile_tpcs_single(
    concrete: Entity,
    inner: Operation,
    distinct: bool,
    order_keys: tuple[OrderKey, ...],
    limit: int | None,
    meta: Metamodel,
    dialect: Dialect,
    entity: Entity,
    result_form: ResultForm,
    lock: LockMode | None,
    position: Sequence[str],
    relationship_order: bool = False,
) -> Statement:
    """A table-per-concrete-subtype read resolving to exactly one concrete: an
    ordinary single-table read of that subtype's own table, no tag, no union, no
    `familyVariant` — attribute resolution still widens across the family (`ctx.entity`
    stays the read's own `targetEntity`, e.g. an abstract position narrowed down to
    this one concrete), matching the table-per-hierarchy concrete-target form.
    """
    if concrete.table is None:  # pragma: no cover - a validated TPCS concrete always has one
        raise SqlGenError(f"{concrete.name}: table-per-concrete-subtype subtype declares no table")
    ctx = _Ctx(meta=meta, dialect=dialect, entity=entity)
    proj_exprs: list[str] = []
    for attribute, _owner in _superset_columns(meta, position):
        expr, extra = dialect.project(ctx.alias, attribute.column, attribute.type)
        proj_exprs.append(expr)
        ctx.binds.extend(extra)
    if result_form == "instance":
        proj_exprs.extend(
            dialect.qualified(ctx.alias, vo.column)
            for vo in _superset_value_objects(meta, position)
        )
    select = f"select {'distinct ' if distinct else ''}{', '.join(proj_exprs)}"
    parts = [select, f"from {concrete.table} {ctx.alias}"]
    where_sql = _lower_predicate(inner, ctx)
    if where_sql:
        parts.append(f"where {where_sql}")
    _append_result_shape(parts, ctx, distinct, order_keys, limit, lock, relationship_order)
    return _normalize(Statement(" ".join(parts), tuple(ctx.binds)))


# --------------------------------------------------------------------------- #
# familyVariant materialization plan (engine-facing; m-case-format /            #
# m-conformance-adapter): TPH derives it from the projected raw tag column at   #
# row construction, TPCS reads it straight from the projected literal column.   #
# A concrete-target read (TPH) or a single-resolved-position read (TPCS)        #
# carries neither, and `family_variant_plan` returns `None`.                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class FamilyVariantPlan:
    """How the conformance engine derives ``familyVariant`` for one read's wire
    rows, or graph leaves (m-case-format). Never used for a concrete-target read.
    """

    kind: Literal["tag", "literal"]
    column: str
    tag_map: Mapping[str, str] | None = None


def family_variant_plan(meta: Metamodel, target: str, op: Operation) -> FamilyVariantPlan | None:
    """The read's ``familyVariant`` materialization plan, or ``None`` when the
    read carries none.

    Mirrors `compile_read`'s own top-level-narrow / position resolution so the
    engine's row post-processing can never drift from what was actually
    projected: a table-per-hierarchy read materializes it whenever `target`
    itself is abstract (regardless of a narrow's resolved cardinality,
    `m-inheritance-012`); a table-per-concrete-subtype read carries it only when
    the resolved position spans two or more concretes (the union-all form).
    """
    entity = meta.entity(target)
    if entity.inheritance is None:
        return None
    predicate, *_directives = _peel_directives(op)
    root = inheritance.family_root(meta, entity)
    assert root.inheritance is not None
    if isinstance(predicate, Narrow):
        position = _narrow_effective_set(meta, predicate.to)
    else:
        position = tuple(inheritance.effective_concrete_subtypes(meta, target))

    if root.inheritance.strategy == "table-per-hierarchy":
        if entity.inheritance.role not in ("root", "abstract-subtype"):
            return None
        tag_col = root.inheritance.tag_column
        assert tag_col is not None
        family_concretes = inheritance.effective_concrete_subtypes(meta, root.name)
        tag_map = {_tag_value(meta, name): name for name in family_concretes}
        return FamilyVariantPlan(kind="tag", column=tag_col, tag_map=tag_map)
    # table-per-concrete-subtype
    if len(position) <= 1:
        return None
    return FamilyVariantPlan(kind="literal", column="family_variant")


def apply_family_variant(
    row: Mapping[str, object], plan: FamilyVariantPlan | None
) -> dict[str, object]:
    """Materialize ``familyVariant`` on one observed row from its ``plan`` (or
    return ``row`` unchanged when ``plan`` is ``None``).

    The single application of a :class:`FamilyVariantPlan` every consumer shares —
    the conformance engine's flat wire rows and the production snapshot find
    executor's instance-form graph rows alike (COR-3 Phase 7 increment 5) — so
    the `tag` (pop the raw tag column, look it up in ``plan.tag_map``) / `literal`
    (rename the projected literal column) derivation lives once, in `m-sql`.
    """
    if plan is None:
        return dict(row)
    materialized = dict(row)
    raw = materialized.pop(plan.column)
    if plan.kind == "tag":
        assert plan.tag_map is not None
        materialized["familyVariant"] = plan.tag_map[cast("str", raw)]
    else:
        materialized["familyVariant"] = raw
    return materialized


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
    assert root.inheritance is not None
    tag_col = root.inheritance.tag_column
    if tag_col is None:  # pragma: no cover - a validated TPH root always declares one
        raise SqlGenError(f"{root.name}: table-per-hierarchy root declares no tag column")
    table = ctx.meta.entity(position[0]).table
    if table is None:  # pragma: no cover - a validated TPH concrete always declares one
        raise SqlGenError(f"{position[0]}: table-per-hierarchy concrete subtype declares no table")
    child_alias = ctx.next_alias()
    # The child context's active entity is the hop's TARGET (possibly abstract):
    # family-wide attribute resolution (`_searchable_attributes`) needs only that
    # `inheritance is not None`, exactly like a top-level inheritance read's ctx.
    child_ctx = ctx.child(ctx.meta.entity(root.name), child_alias)
    correlation = f"{child_ctx.column_of(f'{root.name}.{related_attr}')} = {parent_col}"
    tag_fragment = (
        ()
        if tag_kind == "none"
        else (_tph_tag_fragment(child_ctx, ctx.meta, tag_col, tag_kind, position),)
    )
    where = _hop_where(remaining_inner, correlation, child_ctx, *tag_fragment)
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
    extraction, path_binds = ctx.dialect.nested_extract(ctx.alias, vo.column, segments)
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
    guard_sql, guard_binds = ctx.dialect.array_guard(ctx.alias, vo.column, pre)
    ctx.binds.extend(guard_binds)
    array_alias = ctx.next_alias()
    extraction, path_binds = ctx.dialect.nested_extract(array_alias, "value", post)
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
    guard_sql, guard_binds = ctx.dialect.array_guard(ctx.alias, vo.column, pre)
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
            extraction, path_binds = ctx.dialect.nested_extract(alias, "value", segments)
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
