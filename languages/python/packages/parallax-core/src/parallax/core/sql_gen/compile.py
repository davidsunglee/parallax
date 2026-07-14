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
reach this compiler; to-many value-object array traversal, inheritance-family, and
navigation nodes that this phase does not yet lower raise a clear
:class:`SqlGenError` so a mis-routed case fails loudly, never silently.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, assert_never

from parallax.core.descriptor import (
    Attribute,
    Entity,
    Metamodel,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
    column_order,
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

__all__ = ["ResultForm", "SqlGenError", "Statement", "compile_read"]

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


@dataclass(frozen=True, slots=True)
class _Ctx:
    """Lowering context: the resolved target entity, its dialect, and its alias."""

    meta: Metamodel
    dialect: Dialect
    entity: Entity
    alias: str = "t0"
    binds: list[object] = field(default_factory=_new_binds)

    def column_of(self, attr_ref: str) -> str:
        attribute = self.entity_attribute(attr_ref)
        return self.dialect.qualified(self.alias, attribute.column)

    def entity_attribute(self, attr_ref: str) -> Attribute:
        _, _, name = attr_ref.partition(".")
        for attribute in self.entity.attributes:
            if attribute.name == name:
                return attribute
        raise SqlGenError(f"{attr_ref!r} names no attribute on {self.entity.name}")

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
    tag / familyVariant (slots 2/3) are not reached here — inheritance-family reads
    are refused in this phase (:func:`compile_read`).

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
    """
    entity = meta.entity(target)
    if entity.inheritance is not None:
        raise SqlGenError(
            f"{target}: inheritance-family read lowering is deferred past the Phase-5 "
            "read path to the snapshot branch (COR-3 Phase 7; ledger D-12)"
        )
    predicate, distinct, order_keys, limit = _peel_directives(op)
    ctx = _Ctx(meta=meta, dialect=dialect, entity=entity)

    proj_sql, proj_binds = _projection(entity, dialect, ctx.alias, result_form)
    ctx.binds.extend(proj_binds)
    select = f"select {'distinct ' if distinct else ''}{proj_sql}"
    parts = [select, f"from {entity.table} {ctx.alias}"]

    where_sql = _lower_predicate(predicate, ctx)
    if where_sql:
        parts.append(f"where {where_sql}")
    if order_keys:
        # An authored key that omitted `direction` (serde `None`) lowers to the
        # schema default `asc`.
        terms = [f"{ctx.column_of(key.attr)} {key.direction or 'asc'}" for key in order_keys]
        parts.append("order by " + ", ".join(terms))
    if limit is not None:
        parts.append(dialect.limit_clause())
        ctx.bind(limit)
    if lock == "locking" and not distinct:
        # The shared-row-lock suffix is the last thing in the statement (after any
        # `where` / `order by` / `limit`); a `distinct` object read suppresses it.
        parts.append(dialect.read_lock_suffix(ctx.alias))

    return _normalize(Statement(" ".join(parts), tuple(ctx.binds)))


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
            raise SqlGenError(
                "to-many value-object array traversal (nestedExists/nestedNotExists) "
                "is deferred past the Phase-5 read path to the snapshot branch's "
                "value-object materialization (COR-3 Phase 7; ledger D-12)"
            )
        case Narrow() | Navigate() | Exists() | NotExists() | DeepFetch():
            raise SqlGenError(
                "navigation / narrow / deep-fetch lowering lands with the snapshot branch"
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
def _lower_nested(op: Operation, ctx: _Ctx) -> str:
    if isinstance(op, NestedComparison):
        extraction, leaf_type = _nested_extraction(op.path, ctx)
        casted = ctx.dialect.nested_cast(extraction, leaf_type)
        ctx.bind(op.value)
        # nestedNotEq lowers to `not <ext> = ?` (the corpus form), not `<ext> <> ?`.
        if op.op == "nestedNotEq":
            return f"not {casted} = ?"
        return f"{casted} {_NESTED_COMPARATORS[op.op]} ?"
    if isinstance(op, NestedMembership):
        extraction, leaf_type = _nested_extraction(op.path, ctx)
        casted = ctx.dialect.nested_cast(extraction, leaf_type)
        holes = ", ".join("?" for _ in op.values)
        for value in op.values:
            ctx.bind(value)
        return f"{casted} in ({holes})"
    assert isinstance(op, NestedNullCheck)
    extraction, _leaf_type = _nested_extraction(op.path, ctx)
    if op.op == "nestedIsNull":
        return f"{extraction} is null"
    return f"not {extraction} is null"


def _nested_extraction(path: str, ctx: _Ctx) -> tuple[str, str]:
    """Resolve a `Class.vo.seg...` path to its extraction expression and leaf type.

    A flat predicate whose path crosses a ``cardinality: many`` member takes
    core's any-element semantics and lowers to array traversal, which this phase
    does not yet emit; such a path is refused here so a mis-declared case fails
    loudly rather than emitting a wrong scalar extraction.
    """
    parts = path.split(".")
    if len(parts) < 3:
        raise SqlGenError(f"nested path {path!r} needs Class.valueObject.attribute")
    _entity_name, vo_name, *segments = parts
    vo = _value_object(ctx.entity, vo_name)
    if _crosses_many(vo, tuple(segments)):
        raise SqlGenError(
            f"nested path {path!r} crosses a `many` member (any-element array traversal "
            "is deferred past the Phase-5 read path to the snapshot branch — "
            "COR-3 Phase 7; ledger D-12)"
        )
    leaf = _resolve_leaf(vo, tuple(segments))
    extraction, path_binds = ctx.dialect.nested_extract(ctx.alias, vo.column, tuple(segments))
    ctx.binds.extend(path_binds)
    return extraction, leaf.type


def _crosses_many(vo: ValueObject, segments: Sequence[str]) -> bool:
    """Whether a flat path traverses any ``cardinality: many`` value-object member."""
    if vo.cardinality == "many":
        return True
    container: ValueObject | NestedValueObject = vo
    for segment in segments:
        nested = _find_nested(container, segment)
        if nested is None:
            return False  # reached a scalar leaf without crossing a many member
        if nested.cardinality == "many":
            return True
        container = nested
    return False


def _value_object(entity: Entity, name: str) -> ValueObject:
    for vo in entity.value_objects:
        if vo.name == name:
            return vo
    raise SqlGenError(f"{entity.name}: {name!r} is not a declared value object")


def _resolve_leaf(
    vo: ValueObject | NestedValueObject, segments: Sequence[str]
) -> ValueObjectAttribute:
    container: ValueObject | NestedValueObject = vo
    for index, segment in enumerate(segments):
        attribute = _find_attribute(container, segment)
        if attribute is not None:
            if index != len(segments) - 1:
                raise SqlGenError(f"value-object path continues past scalar {segment!r}")
            return attribute
        nested = _find_nested(container, segment)
        if nested is None:
            raise SqlGenError(f"value-object path segment {segment!r} is undeclared")
        container = nested
    raise SqlGenError("value-object path does not reach a scalar leaf")


def _find_attribute(
    container: ValueObject | NestedValueObject, name: str
) -> ValueObjectAttribute | None:
    for attribute in container.attributes:
        if attribute.name == name:
            return attribute
    return None


def _find_nested(container: ValueObject | NestedValueObject, name: str) -> NestedValueObject | None:
    for nested in container.value_objects:
        if nested.name == name:
            return nested
    return None


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
