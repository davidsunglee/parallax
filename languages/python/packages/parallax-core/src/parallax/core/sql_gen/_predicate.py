"""The ONE recursive predicate owner (m-sql), over an immutable resolution scope.

Every descent into an `m-op-algebra` predicate happens here. `_navigation` and
`_inheritance` return immutable PLANS and never lower anything; `_compile`
assembles statements around the fragment this module returns. So this file holds
the package's only RECURSIVE dispatch over the operation union, and its only
recursion — which is what makes "where does this node get lowered?" a question
with one answer. (`_compile` carries the package's only two other `match`
statements, and neither descends: `_peel_directives` walks the outer
`limit`/`orderBy`/`distinct` chain, and `_compile_inheritance_read` selects a
plan type, which is not an operation node at all.)

**The resolution scope is the dispatch argument.** :data:`ResolutionScope` is
either an :class:`EntityScope` (an active entity, its alias, and whether this
statement aliases its own columns at all) or an :class:`ElementScope` (one
unnested value-object array element: its container and the alias the unnest
declared). One dispatcher serves both — the boolean combinators and the flat
`nested*` family are legal in either, and everything else is entity-scope
vocabulary that an element scope refuses. There is deliberately no second
element dispatcher: a scoped `nestedExists` `where` builds an element scope and
hands its own operation back to :func:`lower_predicate`.

**Both mutual-recursion cycles close here rather than through a sibling.**

* A `narrow` reached mid-predicate is handled in this module: it self-recurses on
  the branch operand and asks `_inheritance` only for the tag guard's inputs.
* A hop is handled the same way: `_navigation` resolves the plan, this module
  opens each branch, builds the child scope, recurses on the branch's un-lowered
  interior, and only THEN pushes the guard's bind values (m-sql "Grouped branch
  predicates": a user predicate binds before a framework-injected guard).

**Binding is always spelled through the context.** A scope resolves and renders;
`scope.ctx` accumulates. Every bind site in this file therefore reads
`scope.ctx.bind(...)` / `scope.ctx.binds`, so the bind ORDER this task exists to
protect is greppable rather than inferred. The plan-only modules below hold a
`ColumnScope` / `PlanScope` instead, neither of which can reach a `ctx` at all.

To-many value-object array traversal lives here too (m-sql "To-many — exists /
notExists and any-element predicates"): a correlated `EXISTS` over a guarded
`jsonb_array_elements` unnest, continuing the same alias sequence navigation
uses. A flat predicate crossing a `many` member is **any-element** and self-
guards independently per predicate (two ANDed flat predicates open two
independent `EXISTS` subqueries, `m-value-object-018`); a scoped `nestedExists`
/ `nestedNotExists` `where` is **same-element** — every element predicate lowers
against the SAME unnested alias, element-relative (no `Class.valueObject`
prefix). This claim is Postgres-only; MariaDB's `json_contains` / `json_length`
containment family is documented in `m-sql` but not goldened for this target and
is not implemented here.

Named without a leading underscore because the MODULE carries the privacy, the
package convention `_context` established: importers alias each name down.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import assert_never

from parallax.core import inheritance
from parallax.core.descriptor import (
    Attribute,
    Entity,
    Metamodel,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
    VoPathMiss,
    find_value_object,
    find_vo_member,
    resolve_vo_leaf,
)
from parallax.core.dialect import Dialect
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
    StringMatch,
)
from parallax.core.sql_gen._context import Ctx as _Ctx
from parallax.core.sql_gen._context import SqlGenError

# The family LANE of the compiler — distinct from `parallax.core.inheritance`
# above, which is the metamodel module. Aliased down to the module-private
# spelling, so `inheritance.` at any use site below unambiguously means the
# metamodel.
from parallax.core.sql_gen._inheritance import plan_branch_narrow as _plan_branch_narrow
from parallax.core.sql_gen._inheritance import tag_guard as _tph_tag_guard

# The navigation LANE: hop plans in, one correlated `EXISTS` (or a grouped `or`
# of them) out. Same aliasing-down convention as the family lane above.
from parallax.core.sql_gen._navigation import open_branch as _open_branch
from parallax.core.sql_gen._navigation import plan_hop as _plan_hop

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


# --------------------------------------------------------------------------- #
# The resolution scopes.                                                       #
#                                                                              #
# Both are immutable VALUES describing "what does a leaf reference resolve      #
# against, and how does it render". Both point at the statement's one `Ctx`,    #
# which is the mutable half — so a scope may be freely rebuilt while aliases    #
# and binds keep advancing on the single shared accumulator.                    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class EntityScope:
    """A predicate resolving against an ENTITY: the active target, its alias, and
    whether this statement qualifies its own columns at all.

    ``unaliased`` is the write lane (`m-batch-write.md` "Predicate-selected
    readless forms"): a write's rendered predicate is UNALIASED (`where balance
    < ?`), contrasting the resolving read's aliased `t0.balance < ?` form.
    ``False`` — the read compiler's default — for every ordinary read scope. It
    lives on the scope rather than on the context precisely so that
    `compile_write_predicate` reaches the very same vocabulary a read does, one
    flag apart.
    """

    ctx: _Ctx
    entity: Entity
    alias: str = "t0"
    unaliased: bool = False

    @property
    def meta(self) -> Metamodel:
        return self.ctx.meta

    @property
    def dialect(self) -> Dialect:
        return self.ctx.dialect

    def own_column(self, column: str) -> str:
        """Render one of THIS scope's own columns, honoring :attr:`unaliased`.

        The single consultant of :attr:`unaliased` — every reference to a column
        of the active target must route through here so a write's bare-column
        form can never be bypassed. :meth:`column_of` is the attribute-resolving
        front door; a value object's backing DOCUMENT column is not an
        ``Attribute`` and so has no `attr_ref` to resolve, but it is just as much
        this target's own column and takes the same rendering decision.

        Not every column reference is "this scope's own": an unnested array
        element's ``t1.value`` is always alias-qualified, because the subquery
        that produced it declares that alias itself regardless of whether the
        enclosing statement is a read or a write. Those callers reach for
        :meth:`Dialect.qualified` directly, and correctly so.
        """
        if self.unaliased:
            return self.dialect.quote(column)
        return self.dialect.qualified(self.alias, column)

    def column_of(self, attr_ref: str) -> str:
        return self.own_column(self.entity_attribute(attr_ref).column)

    def entity_attribute(self, attr_ref: str) -> Attribute:
        _, _, name = attr_ref.rpartition(".")
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

    def next_alias(self) -> str:
        return self.ctx.next_alias()

    def child(self, entity: Entity, alias: str) -> EntityScope:
        """A nested scope for a correlated hop's interior: the SAME statement
        context (so a nested hop's binds and aliases continue this statement's
        single sequence), a different active entity and alias.

        ``unaliased`` deliberately does NOT travel: the subquery this scope
        describes declares `alias` itself, so its columns are alias-qualified
        even inside a write's otherwise-unaliased predicate (`t1.folder_id = id`
        — the child correlation qualified, the parent column bare).
        """
        return EntityScope(ctx=self.ctx, entity=entity, alias=alias)


@dataclass(frozen=True, slots=True)
class ElementScope:
    """A predicate resolving against ONE UNNESTED value-object array element
    (m-value-object same-element semantics).

    Every leaf under a scoped `nestedExists` / `nestedNotExists` `where` is
    element-relative (`type`, `geo.country` — no leading `Class.valueObject`)
    and resolves against :attr:`container`, the same array element they all
    share, extracted through the alias the unnest declared. There is no
    ``unaliased`` here and there cannot be one: that alias is this statement's
    own declaration, so it qualifies in a write's predicate exactly as it does
    in a read's.
    """

    ctx: _Ctx
    container: ValueObject | NestedValueObject
    alias: str

    @property
    def dialect(self) -> Dialect:
        return self.ctx.dialect

    def element_reference(self) -> str:
        """This element's own `t<n>.value` document reference."""
        return self.dialect.qualified(self.alias, "value")


ResolutionScope = EntityScope | ElementScope


# --------------------------------------------------------------------------- #
# The dispatcher.                                                              #
# --------------------------------------------------------------------------- #
def lower_predicate(op: Operation, scope: ResolutionScope) -> str:
    """Lower one predicate node to a SQL fragment, appending binds in order.

    The arms are grouped by which SCOPES admit them, which is the only thing the
    two vocabularies differ by (the node patterns are disjoint, so the grouping
    changes no dispatch outcome):

    1. The shared sub-grammar — boolean combinators and the flat `nested*`
       family — is legal in either scope. Only the `nested*` RESOLUTION differs:
       an entity scope walks `Class.valueObject.attribute` from its own document
       column, an element scope walks an element-relative path from the unnested
       alias.
    2. Everything below the element-scope refusal is entity vocabulary. An
       element scope refuses all of it with one message, deliberately NOT the
       entity dispatcher's differentiated ones: `m-op-algebra`'s
       `elementPredicate` grammar is a single named production, so what an
       element `where` gets wrong is always the same thing.
    """
    match op:
        # -- the shared sub-grammar: legal in EITHER scope ---------------------
        case And(operands=operands):
            return " and ".join(lower_predicate(o, scope) for o in operands)
        case Or(operands=operands):
            return " or ".join(lower_predicate(o, scope) for o in operands)
        case Not(operand=operand):
            return f"not {lower_predicate(operand, scope)}"
        case Group(operand=operand):
            return f"({lower_predicate(operand, scope)})"
        case NestedComparison() | NestedMembership() | NestedNullCheck():
            if isinstance(scope, ElementScope):
                return _lower_element_nested(op, scope)
            return _lower_nested(op, scope)
        # -- everything below is ENTITY-scope vocabulary -----------------------
        case _ if isinstance(scope, ElementScope):
            raise SqlGenError(
                f"{op!r} is not a legal nestedExists/nestedNotExists element predicate "
                "(m-op-algebra elementPredicate)"
            )
        case All():
            return ""
        case NoneOp():
            return "1 = 0"
        case Comparison(op=tag, attr=attr, value=value):
            scope.ctx.bind(value)
            return f"{scope.column_of(attr)} {_COMPARATORS[tag]} ?"
        case Between(attr=attr, lower=lower, upper=upper):
            scope.ctx.bind(lower)
            scope.ctx.bind(upper)
            return f"{scope.column_of(attr)} between ? and ?"
        case NullCheck(op=tag, attr=attr):
            col = scope.column_of(attr)
            return f"{col} is null" if tag == "isNull" else f"not {col} is null"
        case StringMatch():
            return _lower_string(op, scope)
        case Membership(op=tag, attr=attr, values=values):
            holes = ", ".join("?" for _ in values)
            for value in values:
                scope.ctx.bind(value)
            fragment = f"{scope.column_of(attr)} in ({holes})"
            return fragment if tag == "in" else f"not {fragment}"
        case NestedExists() | NestedNotExists():
            return _lower_nested_exists(op, scope)
        case Narrow():
            return _lower_branch_narrow(op, scope)
        case Navigate() | Exists() | NotExists():
            return _lower_navigation(op, scope)
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


def _lower_string(op: StringMatch, scope: EntityScope) -> str:
    col = scope.column_of(op.attr)
    if op.op in ("like", "notLike"):
        scope.ctx.bind(op.value)
        col_expr = f"lower({col})" if op.case_insensitive else col
        rhs = "lower(?)" if op.case_insensitive else "?"
        fragment = f"{col_expr} like {rhs}"
        return fragment if op.op == "like" else fragment.replace(" like ", " not like ", 1)
    # The affix pattern is folded to lower case under case-insensitive matching,
    # so the pattern bind is already lowercased (the corpus's affix convention);
    # `like`/`notLike` keep the pattern verbatim and rely on `lower(?)` alone.
    literal = op.value.lower() if op.case_insensitive else op.value
    pattern, needs_escape = _affix_pattern(op.op, literal)
    scope.ctx.bind(pattern)
    col_expr = f"lower({col})" if op.case_insensitive else col
    rhs = "lower(?)" if op.case_insensitive else "?"
    fragment = f"{col_expr} like {rhs}"
    if needs_escape:
        scope.ctx.bind("\\")
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
# Inheritance — a `narrow` reached MID-predicate (m-sql "Grouped branch         #
# predicates"). Cycle A closes here: this self-recurses on the branch operand   #
# and asks `_inheritance` only for the guard's inputs.                          #
# --------------------------------------------------------------------------- #
def _lower_branch_narrow(narrow: Narrow, scope: EntityScope) -> str:
    """A `narrow` node reached MID-predicate (nested inside and/or/not/group) — a
    **grouped branch predicate** (m-sql "Grouped branch predicates"): the
    branch's own operand composes with its own tag guard via `and`, and the
    composition is wrapped in parens whenever there is a branch predicate to
    disambiguate against a sibling branch joined by `or` (`m-inheritance-015`).
    A single narrow with a branch predicate and nothing to combine against
    needs no grouping — but that is the **top-level** narrow shape, intercepted
    before this dispatcher ever runs (`_compile._compile_tph_read`); every narrow
    this function receives is nested, so it always groups when it has two terms.
    """
    plan = _plan_branch_narrow(scope.meta, scope.entity, narrow)
    # Branch predicate first, THEN the guard's binds — the same explicit ordering
    # the top-level read states, for the same reason.
    branch_sql = lower_predicate(plan.operand, scope)
    tag_sql, tag_binds = _tph_tag_guard(scope, scope.meta, plan.tag)
    scope.ctx.binds.extend(tag_binds)
    if not branch_sql:
        return tag_sql
    return f"({branch_sql} and {tag_sql})"


# --------------------------------------------------------------------------- #
# Navigation (m-sql "Joins by navigation"). Cycle B closes here: `_navigation`  #
# resolves the hop and hands back an immutable plan; this is its only consumer. #
# The loop below is the whole lowering: OPEN a branch (which takes its alias    #
# and renders its correlation and its DEFERRED tag guard), lower that branch's  #
# own interior against a child scope, and only THEN push the guard's binds —    #
# the m-sql "Grouped branch predicates" order, stated here rather than left to  #
# an evaluation-order accident.                                                 #
# --------------------------------------------------------------------------- #
def _lower_navigation(op: Navigate | Exists | NotExists, scope: EntityScope) -> str:
    plan = _plan_hop(op, scope)
    fragments: list[str] = []
    for branch in plan.branches:
        # Opened INSIDE the loop, not up front: a branch takes its alias
        # immediately before its own interior lowers, so a later branch's alias
        # follows everything the preceding branch's interior allocated. Hoisting
        # this would renumber a grouped table-per-concrete-subtype hop whose
        # interior itself navigates.
        opened = _open_branch(branch, scope)
        child_scope = scope.child(opened.entity, opened.alias)
        where = _hop_where(opened.inner, opened.correlation, child_scope, *opened.tag_fragment)
        # AFTER the interior: the plan carried the guard's bind VALUES precisely so
        # this push is the caller's own visible statement (`_navigation` holds no
        # capability to have pushed them itself).
        child_scope.ctx.binds.extend(opened.tag_binds)
        fragments.append(opened.render(where))
    return plan.combine(fragments)


def _hop_where(
    inner: Operation | None, correlation: str, child_scope: EntityScope, *extra: str
) -> str:
    """The correlated sub-select's `where` clause: correlation, then the (optional)
    interior predicate, then any trailing fragment (a TPH tag guard) — the shared
    term order every hop shape composes (m-sql "Grouped branch predicates":
    a user/interior predicate binds before a framework-injected guard)."""
    terms = [correlation]
    if inner is not None:
        inner_sql = lower_predicate(inner, child_scope)
        if inner_sql:
            terms.append(inner_sql)
    terms.extend(extra)
    return " and ".join(terms)


# --------------------------------------------------------------------------- #
# Value-object nested predicates (m-value-object; resolved inline — the DAG    #
# forbids m-op-algebra / m-sql from importing m-value-object).                 #
# --------------------------------------------------------------------------- #
def _lower_nested(
    op: NestedComparison | NestedMembership | NestedNullCheck, scope: EntityScope
) -> str:
    """Lower a flat `nested*` predicate (m-op-algebra "Nested value-object
    predicates"): a scalar extraction against the scope's own alias when the path
    stays within `one`-multiplicity members, or — when it crosses a `multiplicity:
    many` member — the any-element array-traversal form (m-sql "To-many — exists /
    notExists and any-element predicates"; `m-value-object-017/-018/-021`)."""
    vo, segments = _flat_vo_path(op.path, scope.entity)
    crossing = _split_at_many(vo, segments)
    if crossing is not None:
        return _lower_any_element(op, vo, crossing, scope)
    leaf = _resolve_leaf(vo, segments)
    # The document column is the TARGET's own, so it renders through `own_column`
    # and goes bare in a write's unaliased predicate (m-sql rule 1).
    extraction, path_binds = scope.dialect.nested_extract(
        scope.own_column(vo.storage_column), segments
    )
    scope.ctx.binds.extend(path_binds)
    return _lower_comparator(op, extraction, leaf.type, scope)


def _lower_element_nested(
    op: NestedComparison | NestedMembership | NestedNullCheck, scope: ElementScope
) -> str:
    """The same flat `nested*` family, resolved ELEMENT-relatively (m-op-algebra
    `elementPredicate`; m-value-object same-element semantics): the path carries
    no `Class.valueObject` prefix, resolves against the scope's container, and
    extracts from the unnested element every predicate in this `where` shares —
    never by re-descending through the owner's document column."""
    segments = tuple(op.path.split("."))
    leaf = _resolve_leaf(scope.container, segments)
    extraction, path_binds = scope.dialect.nested_extract(scope.element_reference(), segments)
    scope.ctx.binds.extend(path_binds)
    return _lower_comparator(op, extraction, leaf.type, scope)


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
    scope: ResolutionScope,
) -> str:
    """Render one resolved extraction's comparator fragment (m-sql "valueObject
    — structured-column read and filter" / "The flat `nested*` operator
    family"), binding extraction-then-comparator in that order. Shared by the
    plain scalar path, the flat any-element lowering, and the same-element
    scoped `where` lowering — only how `extraction` was resolved differs, which
    is why this takes either scope.
    """
    if isinstance(op, NestedComparison):
        casted = scope.dialect.nested_cast(extraction, leaf_type)
        scope.ctx.bind(op.value)
        # nestedNotEq lowers to `not <ext> = ?` (the corpus form), not `<ext> <> ?`.
        if op.op == "nestedNotEq":
            return f"not {casted} = ?"
        return f"{casted} {_NESTED_COMPARATORS[op.op]} ?"
    if isinstance(op, NestedMembership):
        casted = scope.dialect.nested_cast(extraction, leaf_type)
        holes = ", ".join("?" for _ in op.values)
        for value in op.values:
            scope.ctx.bind(value)
        return f"{casted} in ({holes})"
    if op.op == "nestedIsNull":
        return f"{extraction} is null"
    return f"not {extraction} is null"


def _split_at_many(
    vo: ValueObject, segments: Sequence[str]
) -> tuple[ValueObject | NestedValueObject, tuple[str, ...], tuple[str, ...]] | None:
    """Split a flat predicate's path at the first `multiplicity: many` hop
    crossed while walking from `vo` (m-op-algebra "Flat predicates through a
    `many` segment mean any element matches"). Returns ``(the many container,
    the segments reaching it from vo's own document column, the remaining
    segments addressing a field WITHIN the element)`` — or ``None`` when the
    walk never crosses a `many` member (the plain scalar-extraction case
    :func:`_lower_nested` handles directly).
    """
    if vo.multiplicity == "many":
        return vo, (), tuple(segments)
    container: ValueObject | NestedValueObject = vo
    for index, segment in enumerate(segments):
        member = find_vo_member(container, segment)
        if not isinstance(member, NestedValueObject):
            return None  # reached a scalar leaf (or an unresolved segment) uncrossed
        if member.multiplicity == "many":
            return member, tuple(segments[: index + 1]), tuple(segments[index + 1 :])
        container = member
    return None


def _lower_any_element(
    op: NestedComparison | NestedMembership | NestedNullCheck,
    vo: ValueObject,
    crossing: tuple[ValueObject | NestedValueObject, tuple[str, ...], tuple[str, ...]],
    scope: EntityScope,
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
    guard_sql, guard_binds = scope.dialect.array_guard(scope.own_column(vo.storage_column), pre)
    scope.ctx.binds.extend(guard_binds)
    element = ElementScope(ctx=scope.ctx, container=container, alias=scope.next_alias())
    extraction, path_binds = scope.dialect.nested_extract(element.element_reference(), post)
    scope.ctx.binds.extend(path_binds)
    comparator = _lower_comparator(op, extraction, leaf.type, scope)
    return (
        f"exists (select 1 from jsonb_array_elements({guard_sql}) "
        f"{element.alias} where {comparator})"
    )


# --------------------------------------------------------------------------- #
# `nestedExists` / `nestedNotExists` (m-sql "To-many — exists / notExists and  #
# any-element predicates").                                                    #
# --------------------------------------------------------------------------- #
def _lower_nested_exists(op: NestedExists | NestedNotExists, scope: EntityScope) -> str:
    """A bare form is a non-empty / empty-or-absent test over the guarded
    unnest; a scoped `where` composes its element predicate on the SAME
    unnested alias (same-element semantics, m-value-object — as opposed to the
    any-element flat form above, which never shares an alias across
    predicates). Postgres `EXISTS` is never NULL, so the negated forms need no
    `coalesce` wrap: `not exists (...)` over zero unnested elements is already
    true (m-sql, explicit). MariaDB's containment form DOES need one — but this
    claim is Postgres-only and that form is not implemented here.

    The scoped `where` is handed back to :func:`lower_predicate` under an
    :class:`ElementScope`; there is no second dispatcher for it.
    """
    vo, pre, container = _resolve_vo_terminus(op.path, scope.entity)
    if container.multiplicity != "many":
        raise SqlGenError(
            f"nestedExists/nestedNotExists over a `one`-multiplicity value object "
            f"({op.path!r}) has no goldened lowering yet"
        )
    guard_sql, guard_binds = scope.dialect.array_guard(scope.own_column(vo.storage_column), pre)
    scope.ctx.binds.extend(guard_binds)
    element = ElementScope(ctx=scope.ctx, container=container, alias=scope.next_alias())
    inner = f"select 1 from jsonb_array_elements({guard_sql}) {element.alias}"
    if op.where is not None:
        inner = f"{inner} where {lower_predicate(op.where, element)}"
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
