"""The ONE recursive predicate owner (m-sql), over an immutable resolution scope.

Every descent into an `m-predicate` predicate happens here. `_navigation` and
`_inheritance` return immutable PLANS and never lower anything; `_compile`
assembles statements around the fragment this module returns. So this file holds
the package's only RECURSIVE dispatch over the Predicate union, and its only
recursion — which is what makes "where does this node get lowered?" a question
with one answer. (`_compile_inheritance_read` carries the package's only other
`match`, selecting a plan type rather than a Predicate node.)

**The resolution scope is the dispatch argument.** :data:`ResolutionScope` is
either an :class:`EntityScope` (an active entity, its alias, and whether this
statement aliases its own columns at all) or an :class:`ElementScope` (one
unnested value-object array element: its container and the alias the unnest
declared). One dispatcher serves both — the boolean combinators and the flat
`nested*` family are legal in either, and everything else is entity-scope
vocabulary that an element scope refuses. There is deliberately no second
element dispatcher: a scoped `nestedExists` `where` builds an element scope and
hands its own predicate back to :func:`lower_predicate`.

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
from typing import Literal, assert_never, cast

from parallax.core.base import STRING, Bytes, NeutralType
from parallax.core.dialect import Dialect, projection_result_key
from parallax.core.document_codec import comparison_text, is_text_compared
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.predicate import (
    All,
    And,
    Between,
    Comparison,
    Exists,
    Group,
    Membership,
    Narrow,
    Navigate,
    NestedComparison,
    NestedExists,
    NestedMembership,
    NestedNotExists,
    NestedNullCheck,
    NestedRange,
    NestedStringMatch,
    NestedStringOp,
    NoneOp,
    Not,
    NotExists,
    NullCheck,
    Or,
    StringMatch,
    StringOp,
)
from parallax.core.predicate._validated import ValidatedPredicate
from parallax.core.sql_gen._context import SqlGenError, StatementBuilder
from parallax.core.sql_gen._context import table_layout as _table_layout

# The family LANE of the compiler — distinct from `parallax.core.inheritance`
# above, which is the metamodel module. Aliased down to the module-private
# spelling, so a use site below never confuses the two.
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import (
    plan_validated_branch_narrow as _plan_validated_branch_narrow,
)
from parallax.core.sql_gen._inheritance import tag_guard as _tph_tag_guard

# The navigation LANE: hop plans in, one correlated `EXISTS` (or a grouped `or`
# of them) out. Same aliasing-down convention as the family lane above.
from parallax.core.sql_gen._navigation import open_branch as _open_branch
from parallax.core.sql_gen._navigation import plan_validated_hop as _plan_validated_hop
from parallax.core.storage_layout import (
    ColumnContributor,
    DirectColumn,
    DocumentPath,
    StorageLayoutFacet,
    TableLayout,
)
from parallax.core.wire import WireValue

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
# Each nested string predicate's scalar twin. The pattern grammar, the escaping, and
# the case folding are the SAME rule at both levels (m-predicate), so the nested
# family is rendered by mapping onto the scalar kind rather than by a second table.
_NESTED_STRING_KINDS: dict[NestedStringOp, StringOp] = {
    "nestedLike": "like",
    "nestedNotLike": "notLike",
    "nestedStartsWith": "startsWith",
    "nestedEndsWith": "endsWith",
    "nestedContains": "contains",
}


@dataclass(frozen=True, slots=True)
class MemberSubject:
    """One resolved scalar member as a predicate or ordering term reads it.

    ``extraction`` is what the member's value is read out of — an
    alias-qualified Column under a `DirectColumn` placement, the dialect's
    document text extraction under a `DocumentPath` one. ``compared`` is that
    expression with the declared type's cast applied where the comparison casts
    at all (`m-dialect`), and is identical to ``extraction`` for a direct Column,
    which is already typed, and for a document-resident member of one of the six
    text-compared types.

    The two are not interchangeable: an equality, range, or membership test
    compares ``compared`` while a null check and a string pattern read
    ``extraction``, exactly as the conventional nested vocabulary already does.
    ``document_resident`` is what decides which literal form a compared value
    binds in. ``text_compared`` is the narrower fact a REBIND needs: whether
    ``compared`` yields the codec's comparison text rather than a value of the
    declared type. It is not derivable from the other three — a wrapped `union
    all` names a `bytes` member by the result key its branches already
    hex-encoded, so that expression compares as text while claiming no document
    residence at all.
    """

    extraction: str
    compared: str
    type: NeutralType
    document_resident: bool
    text_compared: bool = False


# --------------------------------------------------------------------------- #
# The resolution scopes.                                                       #
#                                                                              #
# Both are immutable VALUES describing "what does a leaf reference resolve      #
# against, and how does it render". Both point at the statement's one `StatementBuilder`,    #
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

    ``layout`` is the ONE physical Table this statement (or `union all` branch)
    reads, so every reference to a member's column is answered by a Storage
    Layout slot rather than by re-reading the member's own storage declaration.
    A branch of a table-per-concrete-subtype union carries its OWN branch layout
    even though its active entity stays the read's queried `target`, which is what
    makes "does this branch physically carry that member?" a question the scope
    can answer at all.

    ``wrapped`` says :attr:`alias` is a derived table over a union of branches
    that already applied their own per-type projection, so a direct member is
    named by the RESULT key a branch projected it under rather than by the
    physical Column no such union yields — and a `bytes` member is then the
    hex-encoded text that key carries rather than octets.
    """

    ctx: StatementBuilder
    entity: EntityMetadata
    layout: TableLayout
    alias: str = "t0"
    unaliased: bool = False
    position: tuple[EntityIdentity, ...] | None = None
    variant: EntityIdentity | None = None
    wrapped: bool = False

    @property
    def meta(self) -> Metamodel:
        return self.ctx.meta

    @property
    def facet(self) -> InheritanceFacet:
        return self.ctx.facet

    @property
    def storage(self) -> StorageLayoutFacet:
        return self.ctx.storage

    @property
    def dialect(self) -> Dialect:
        return self.ctx.dialect

    def own_column(self, column: str) -> str:
        """Render one of THIS scope's own columns, honoring :attr:`unaliased`.

        The single consultant of :attr:`unaliased` — every reference to a column
        of the active target must route through here so a write's bare-column
        form can never be bypassed. :meth:`column_of` and :meth:`subject_of` are
        the attribute-resolving front doors; a Structured Column is not an
        ``Attribute`` and so has no `attr_ref` to resolve, but it is just as much
        this target's own column and takes the same rendering decision, which is
        why :meth:`document_root` returns a rendered reference rather than a name.

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
        """Render one DIRECT Attribute Column of the active target.

        The join lane's front door. Member Placement is the sole authority here
        too (`m-storage-layout`), and what it must answer is `DirectColumn`:
        both endpoints of a Relationship Join hold a direct-column role under
        either layout, so a hop's correlation always has a Column to name and
        never extracts from a document.

        The reference resolves by name against the active target's family
        (:meth:`entity_attribute`), so an endpoint addressed at a descendant
        position reaches the ancestor declaration the placement is keyed by.
        """
        return self.column_for(self.entity_attribute(attr_ref))

    def column_for(self, attribute: AttributeMetadata) -> str:
        """Render a validated direct-column Attribute by identity."""
        placement = self.layout.placement(attribute.identity)
        if not isinstance(placement, DirectColumn):  # pragma: no cover
            raise SqlGenError(
                f"{attribute.identity!r} is not a direct Column of table "
                f"{self.layout.table.name!r}, so it cannot carry a join correlation"
            )
        return self.own_column(placement.slot.column.name)

    def subject_of(self, attr_ref: str) -> MemberSubject:
        """Resolve a framework-generated reference before entering identity lowering."""
        return self.subject_for(self.entity_attribute(attr_ref))

    def subject_for(self, attribute: AttributeMetadata) -> MemberSubject:
        """Render a validated Attribute without revisiting its authored spelling.

        Member Placement is the sole authority (`m-storage-layout`): a
        `DirectColumn` renders the Column, and a `DocumentPath` renders the
        dialect's extraction over the Structured Column the placement names,
        binding that path's segments here — so the path comes from the compiled
        placement rather than from splitting an authored string, and the segments
        are already on the context before the caller binds its compared value.
        """
        placement = self.layout.placement(attribute.identity)
        if not isinstance(placement, DocumentPath):
            spelling = self.slot_column(attribute.identity)
            encoded = self.wrapped and isinstance(attribute.type, Bytes)
            column = self.own_column(
                projection_result_key(spelling, attribute.type) if self.wrapped else spelling
            )
            return MemberSubject(
                column, column, attribute.type, document_resident=False, text_compared=encoded
            )
        self._record_document_applicability(attribute.identity.entity)
        document = self.own_column(placement.slot.column.name)
        extraction, path_binds = self.dialect.nested_extract(document, placement.path)
        self.ctx.bind_structural_all(path_binds)
        return MemberSubject(
            extraction,
            self.dialect.nested_cast(extraction, attribute.type),
            attribute.type,
            document_resident=True,
            text_compared=is_text_compared(attribute.type),
        )

    def document_resident(self, attribute: AttributeMetadata) -> bool:
        """Whether this scope reads ``attribute`` out of a document.

        The same Member Placement question :meth:`subject_for` renders from,
        asked without emitting anything: resolving a subject binds the
        extraction's path segments on the context, so a caller deciding whether
        to emit an occurrence at all cannot ask by resolving one.
        """
        return isinstance(self.layout.placement(attribute.identity), DocumentPath)

    def document_root(self, vo: ValueObjectMetadata) -> tuple[str, tuple[str, ...]]:
        """The rendered document reference carrying ``vo``, and the path reaching it.

        One occurrence sits in two places depending on the Entity's layout, and
        its placement says which: under `Columns` it owns a Structured Column of
        its own and the prefix is empty, while under `Document` it is a subtree of
        the Table's one shared Structured Column and the prefix is its own path
        from that document's root. Every path a nested predicate walks is
        prefixed with it, so one extraction site serves both layouts.
        """
        placement = self.layout.placement(vo.identity)
        if isinstance(placement, DocumentPath):
            self._record_document_applicability(vo.identity.entity)
            return self.own_column(placement.slot.column.name), placement.path
        return self.own_column(self.slot_column(vo.identity)), ()

    def slot_column(self, contributor: ColumnContributor) -> str:
        """``contributor``'s physical Column in the Table this scope reads.

        The one place a member reaches its column: `m-sql` resolves accepted
        member Identities through the Storage Layout slot index rather than
        re-reading each declaration's own storage location, so a predicate and
        the projection beside it can never disagree about the physical Table.
        """
        slot = self.layout.contribution(contributor)
        if slot is None:
            raise SqlGenError(f"{contributor} has no Column in table {self.layout.table.name!r}")
        return slot.column.name

    def entity_attribute(self, attr_ref: str) -> AttributeMetadata:
        owner_ref, _, name = attr_ref.rpartition(".")
        owner = entity_by_name(self.meta, owner_ref)
        if owner is not None:
            attribute = _entity_view(self.facet, owner.identity).applicable_attribute(name)
            root = _entity_view(self.facet, self.entity.identity).root
            searchable = {
                candidate.identity
                for candidate in _entity_view(self.facet, root).superset_attributes
            }
            if attribute is not None and attribute.identity in searchable:
                return attribute
        raise SqlGenError(f"{attr_ref!r} names no attribute on {self.entity.identity.name}")

    def _record_document_applicability(self, owner: EntityIdentity) -> None:
        if self.position is None:
            return
        owner_view = _entity_view(self.facet, owner)
        if self.variant is not None:
            exposed = (self.variant,)
        else:
            root = _entity_view(self.facet, self.entity.identity).root
            exposed = _entity_view(self.facet, root).concrete_subtypes
        if not set(exposed) <= set(owner_view.concrete_subtypes):
            self.ctx.requires_variant_partition = True

    def next_alias(self) -> str:
        return self.ctx.next_alias()

    def child(self, entity: EntityMetadata, alias: str) -> EntityScope:
        """A nested scope for a correlated hop's interior: the SAME statement
        context (so a nested hop's binds and aliases continue this statement's
        single sequence), a different active entity and alias.

        ``unaliased`` deliberately does NOT travel: the subquery this scope
        describes declares `alias` itself, so its columns are alias-qualified
        even inside a write's otherwise-unaliased predicate (`t1.folder_id = id`
        — the child correlation qualified, the parent column bare). The child's
        own Table Layout does travel, because the hop selects from the child's
        own table.
        """
        return EntityScope(
            ctx=self.ctx,
            entity=entity,
            layout=_table_layout(self.ctx.storage, self.ctx.facet, entity.identity),
            alias=alias,
        )


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

    ctx: StatementBuilder
    container: ValueObjectMetadata | NestedValueObjectMetadata
    alias: str

    @property
    def dialect(self) -> Dialect:
        return self.ctx.dialect

    def element_reference(self) -> str:
        """This element's own `t<n>.value` document reference."""
        return self.dialect.qualified(self.alias, "value")


ResolutionScope = EntityScope | ElementScope

# Either kind of Value Object occurrence a dotted path may be walked against.
# The two Metadata shapes differ only in what a TOP-LEVEL occurrence additionally
# owns (its Storage Location), and neither member lookup below cares, so the walk
# takes the union rather than branching on depth.
_VoContainer = ValueObjectMetadata | NestedValueObjectMetadata

# The flat `nested*` family — the sub-grammar legal in EITHER scope, resolved
# path-relatively against an entity's document column or element-relatively against
# an unnested element. One alias, because every function below takes the whole
# family and differs only in how it resolved the extraction.
_FlatNested = (
    NestedComparison | NestedRange | NestedMembership | NestedStringMatch | NestedNullCheck
)


# --------------------------------------------------------------------------- #
# The dispatcher.                                                              #
# --------------------------------------------------------------------------- #
def lower_predicate(product: ValidatedPredicate, scope: ResolutionScope) -> str:
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
       entity dispatcher's differentiated ones: `m-predicate`'s
       `elementPredicate` grammar is a single named production, so what an
       element `where` gets wrong is always the same thing.
    """
    op = product.authored
    match op:
        # -- the shared sub-grammar: legal in EITHER scope ---------------------
        case And(operands=operands):
            del operands
            return " and ".join(lower_predicate(child, scope) for child in product.children)
        case Or(operands=operands):
            del operands
            return " or ".join(lower_predicate(child, scope) for child in product.children)
        case Not(operand=operand):
            del operand
            return f"not {lower_predicate(product.only_child(), scope)}"
        case Group(operand=operand):
            del operand
            return f"({lower_predicate(product.only_child(), scope)})"
        case (
            NestedComparison()
            | NestedRange()
            | NestedMembership()
            | NestedStringMatch()
            | NestedNullCheck()
        ):
            if isinstance(scope, ElementScope):
                return _lower_element_nested(product, scope)
            return _lower_nested(product, scope)
        # -- everything below is ENTITY-scope vocabulary -----------------------
        case _ if isinstance(scope, ElementScope):
            raise SqlGenError(
                f"{op!r} is not a legal nestedExists/nestedNotExists element predicate "
                "(m-predicate elementPredicate)"
            )
        case All():
            return ""
        case NoneOp():
            return "1 = 0"
        case Comparison(op=tag, value=value):
            # The subject resolves FIRST: a document-resident member's path
            # segments bind ahead of the compared value, which is the order the
            # emitted text puts their holes in.
            subject = scope.subject_for(_attribute_member(product))
            del value
            _bind_member_literal(product, 0, subject, scope)
            return f"{subject.compared} {_COMPARATORS[tag]} ?"
        case Between(lower=lower, upper=upper):
            subject = scope.subject_for(_attribute_member(product))
            del lower, upper
            _bind_member_literal(product, 0, subject, scope)
            _bind_member_literal(product, 1, subject, scope)
            return f"{subject.compared} between ? and ?"
        case NullCheck(op=tag):
            col = scope.subject_for(_attribute_member(product)).extraction
            return f"{col} is null" if tag == "isNull" else f"not {col} is null"
        case StringMatch():
            return _lower_string(product, scope)
        case Membership(op=tag, values=values):
            subject = scope.subject_for(_attribute_member(product))
            holes = ", ".join("?" for _ in values)
            del values
            for index in range(len(_operands(product))):
                _bind_member_literal(product, index, subject, scope)
            fragment = f"{subject.compared} in ({holes})"
            return fragment if tag == "in" else f"not {fragment}"
        case NestedExists() | NestedNotExists():
            return _lower_nested_exists(product, scope)
        case Narrow():
            return _lower_branch_narrow(product, scope)
        case Navigate() | Exists() | NotExists():
            return _lower_navigation(product, scope)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(op)


def _lower_string(product: ValidatedPredicate, scope: EntityScope) -> str:
    # The subject resolves as an ARGUMENT, so a document-resident member's path
    # segments bind before `_lower_like` pushes the pattern — the same
    # extraction-then-comparator order every other arm keeps.
    op = product.authored
    if not isinstance(op, StringMatch):  # pragma: no cover
        raise AssertionError("validated string product has the wrong authored node")
    subject = scope.subject_for(_attribute_member(product))
    return _lower_like(
        op.op, str(_operand(product, 0)), op.case_insensitive, subject.extraction, scope
    )


def _attribute_member(product: ValidatedPredicate) -> AttributeMetadata:
    if not isinstance(product.member, AttributeMetadata):
        raise SqlGenError(f"{type(product.authored).__name__} carries no resolved Attribute")
    return product.member


def _operands(product: ValidatedPredicate) -> tuple[object, ...]:
    if product.operands is None:
        raise SqlGenError(f"{type(product.authored).__name__} carries no validated operands")
    return product.operands.values


def _operand(product: ValidatedPredicate, index: int) -> object:
    return _operands(product)[index]


def _bind_member_literal(
    product: ValidatedPredicate, index: int, subject: MemberSubject, scope: EntityScope
) -> None:
    """Bind one compared literal in the form ``subject``'s expression compares.

    A direct Column is compared in the engine's own column type, so its literal
    crosses the seam as its managed value with explicit neutral-type metadata. A
    document-resident member is compared through an
    extraction, so it takes the same split the conventional nested vocabulary
    does: the comparison text where the extraction compares as text, the managed
    value in its declared Neutral Type where the extraction casts.
    """
    operands = product.operands
    if operands is None:
        raise SqlGenError(f"{type(product.authored).__name__} carries no validated operands")
    value = operands.values[index]
    if not subject.document_resident:
        if operands.form == "framework":
            scope.ctx.bind_framework(value, wire_value=cast("WireValue", value))
        else:
            if operands.neutral_type is None:
                raise SqlGenError("a managed Predicate operand has no declared neutral type")
            scope.ctx.bind_managed(value, operands.neutral_type)
        return
    _bind_nested_operand(value, subject.type, scope)


def _lower_like(
    kind: StringOp,
    value: str,
    case_insensitive: bool | None,
    subject_sql: str,
    scope: ResolutionScope,
) -> str:
    """Render one string predicate over an ALREADY-RESOLVED subject expression.

    The whole rule lives here once (m-sql "Wildcard / escape rendering"), because a
    scalar column, a nested extraction, and an unnested element's extraction differ
    only in how the subject was resolved: `like`/`notLike` bind the pattern verbatim,
    the affix forms bind an escaped pattern and append `escape ?` plus its bind ONLY
    when escaping actually changed the literal, `notLike` negates INFIX (the
    normalizer's fixed point for this operator, unlike membership's leading `not`),
    and case-insensitive matching folds both sides.
    """
    if kind in ("like", "notLike"):
        scope.ctx.bind_comparison_text(value, STRING)
        needs_escape = False
    else:
        # The affix pattern is folded to lower case under case-insensitive matching,
        # so the pattern bind is already lowercased (the corpus's affix convention);
        # `like`/`notLike` keep the pattern verbatim and rely on `lower(?)` alone.
        literal = value.lower() if case_insensitive else value
        pattern, needs_escape = _affix_pattern(kind, literal)
        scope.ctx.bind_comparison_text(pattern, STRING)
    subject_expr = f"lower({subject_sql})" if case_insensitive else subject_sql
    rhs = "lower(?)" if case_insensitive else "?"
    operator = "not like" if kind == "notLike" else "like"
    fragment = f"{subject_expr} {operator} {rhs}"
    if needs_escape:
        scope.ctx.bind_structural("\\")
        fragment = f"{fragment} escape ?"
    return fragment


# The three AFFIX kinds, whose `value` is literal text this module wraps in
# wildcards. `like` / `notLike` are deliberately absent: their value is already a
# pattern, and `_lower_like` routes them away before any affix rendering — so the
# narrower domain makes that contract unrepresentable rather than merely documented.
_AffixOp = Literal["startsWith", "endsWith", "contains"]


def _affix_pattern(kind: _AffixOp, value: str) -> tuple[str, bool]:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    needs_escape = escaped != value
    if kind == "startsWith":
        return f"{escaped}%", needs_escape
    if kind == "endsWith":
        return f"%{escaped}", needs_escape
    if kind == "contains":
        return f"%{escaped}%", needs_escape
    assert_never(kind)  # pragma: no cover - exhaustiveness guard


# --------------------------------------------------------------------------- #
# Inheritance — a `narrow` reached MID-predicate (m-sql "Grouped branch         #
# predicates"). Cycle A closes here: this self-recurses on the branch operand   #
# and asks `_inheritance` only for the guard's inputs.                          #
# --------------------------------------------------------------------------- #
def _lower_branch_narrow(product: ValidatedPredicate, scope: EntityScope) -> str:
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
    narrow = product.authored
    if not isinstance(narrow, Narrow):  # pragma: no cover
        raise AssertionError("validated narrow product has the wrong authored node")
    if product.position is None:
        raise SqlGenError("validated narrow carries no resolved effective position")
    plan = _plan_validated_branch_narrow(scope.facet, scope.storage, scope.entity, product.position)
    operand = product.only_child()
    if scope.variant is not None:
        if scope.variant not in plan.position:
            return "1 = 0"
        return lower_predicate(operand, scope) or "1 = 1"
    if plan.tag is None:  # pragma: no cover - TPCS union branches always carry a variant
        raise SqlGenError("a TPCS branch narrow requires a concrete branch scope")
    # Branch predicate first, THEN the guard's binds — the same explicit ordering
    # the top-level read states, for the same reason.
    branch_sql = lower_predicate(operand, scope)
    tag_sql, tag_binds = _tph_tag_guard(scope, scope.facet, plan.tag)
    scope.ctx.bind_framework_all(tag_binds)
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
def _lower_navigation(product: ValidatedPredicate, scope: EntityScope) -> str:
    op = product.authored
    if not isinstance(op, (Navigate, Exists, NotExists)):  # pragma: no cover
        raise AssertionError("validated navigation product has the wrong authored node")
    if (
        product.relationship_target is None
        or product.relationship_source is None
        or product.relationship_member is None
    ):
        raise SqlGenError("validated navigation carries no resolved relationship join")
    inner_product = None if not product.children else product.only_child()
    position = (
        inner_product.position
        if inner_product is not None and isinstance(inner_product.authored, Narrow)
        else None
    )
    plan = _plan_validated_hop(
        product.relationship_target,
        product.relationship_source,
        product.relationship_member,
        position=position,
        scope=scope,
        negate=isinstance(op, NotExists),
    )
    fragments: list[str] = []
    for branch in plan.branches:
        # Opened INSIDE the loop, not up front: a branch takes its alias
        # immediately before its own interior lowers, so a later branch's alias
        # follows everything the preceding branch's interior allocated. Hoisting
        # this would renumber a grouped table-per-concrete-subtype hop whose
        # interior itself navigates.
        opened = _open_branch(branch, scope)
        child_scope = scope.child(opened.entity, opened.alias)
        inner = None if not product.children else product.only_child()
        if isinstance(op.op, Narrow) and inner is not None:
            inner = inner.only_child()
        where = _hop_where(inner, opened.correlation, child_scope, *opened.tag_fragment)
        # AFTER the interior: the plan carried the guard's bind VALUES precisely so
        # this push is the caller's own visible statement (`_navigation` holds no
        # capability to have pushed them itself).
        child_scope.ctx.bind_framework_all(opened.tag_binds)
        fragments.append(opened.render(where))
    return plan.combine(fragments)


def _hop_where(
    inner: ValidatedPredicate | None,
    correlation: str,
    child_scope: EntityScope,
    *extra: str,
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
# Value-object nested predicates (m-value-object). Every occurrence is         #
# self-identifying accepted Metadata with its own expected-O(1) member lookup, #
# so a dotted path resolves through the Metamodel Interface here rather than   #
# through m-value-object, which the DAG forbids m-sql from importing.          #
# --------------------------------------------------------------------------- #
def _lower_nested(product: ValidatedPredicate, scope: EntityScope) -> str:
    """Lower a flat `nested*` predicate (m-predicate "Nested value-object
    predicates"): a scalar extraction against the scope's own alias when the path
    stays within `one`-multiplicity members, or — when it crosses a `multiplicity:
    many` member — the any-element array-traversal form (m-sql "To-many — exists /
    notExists and any-element predicates"; `m-value-object-017/-018/-021`)."""
    op = product.authored
    if not isinstance(
        op,
        (NestedComparison, NestedRange, NestedMembership, NestedStringMatch, NestedNullCheck),
    ):
        raise AssertionError("validated nested product has the wrong authored node")
    leaf = _value_object_leaf(product)
    vo, segments = _resolved_vo_path(leaf, scope)
    crossing = _split_at_many(vo, segments)
    if crossing is not None:
        return _lower_any_element(product, vo, crossing, scope)
    # The document column is the TARGET's own, so it renders through `own_column`
    # and goes bare in a write's unaliased predicate (m-sql rule 1). Under
    # Relational Document Layout the occurrence is a subtree of the Table's
    # shared column, so its own placement prefixes every path walked below it.
    document, prefix = scope.document_root(vo)
    extraction, path_binds = scope.dialect.nested_extract(document, (*prefix, *segments))
    scope.ctx.bind_structural_all(path_binds)
    return _lower_comparator(product, extraction, leaf.type, scope)


def _lower_element_nested(product: ValidatedPredicate, scope: ElementScope) -> str:
    """The same flat `nested*` family, resolved ELEMENT-relatively (m-predicate
    `elementPredicate`; m-value-object same-element semantics): the path carries
    no `Class.valueObject` prefix, resolves against the scope's container, and
    extracts from the unnested element every predicate in this `where` shares —
    never by re-descending through the owner's document column."""
    op = product.authored
    if not isinstance(
        op,
        (NestedComparison, NestedRange, NestedMembership, NestedStringMatch, NestedNullCheck),
    ):
        raise AssertionError("validated nested product has the wrong authored node")
    leaf = _value_object_leaf(product)
    base = scope.container.identity.path
    leaf_path = leaf.identity.value_object.path
    if leaf_path[: len(base)] != base:
        raise SqlGenError("validated element leaf is outside its resolved container")
    segments = (*leaf_path[len(base) :], leaf.identity.name)
    extraction, path_binds = scope.dialect.nested_extract(scope.element_reference(), segments)
    scope.ctx.bind_structural_all(path_binds)
    return _lower_comparator(product, extraction, leaf.type, scope)


def _value_object_leaf(product: ValidatedPredicate) -> ValueObjectAttributeMetadata:
    member = product.member
    if member is None or not isinstance(member.identity, ValueObjectAttributeIdentity):
        raise SqlGenError(f"{type(product.authored).__name__} carries no resolved nested leaf")
    return cast("ValueObjectAttributeMetadata", member)


def _resolved_vo_path(
    leaf: ValueObjectAttributeMetadata, scope: EntityScope
) -> tuple[ValueObjectMetadata, tuple[str, ...]]:
    identity = leaf.identity.value_object
    vo = _entity_view(scope.facet, identity.entity).applicable_value_object(identity.path[0])
    if vo is None:
        raise SqlGenError(f"validated Value Object {identity} is absent from the active position")
    return vo, (*identity.path[1:], leaf.identity.name)


def _lower_comparator(
    product: ValidatedPredicate,
    extraction: str,
    leaf_type: NeutralType,
    scope: ResolutionScope,
) -> str:
    """Render one resolved extraction's comparator fragment (m-sql "valueObject
    — structured-column read and filter" / "The flat `nested*` operator
    family"), binding extraction-then-comparator in that order. Shared by the
    plain scalar path, the flat any-element lowering, and the same-element
    scoped `where` lowering — only how `extraction` was resolved differs, which
    is why this takes either scope.
    """
    op = product.authored
    if isinstance(op, NestedComparison):
        casted = scope.dialect.nested_cast(extraction, leaf_type)
        _bind_nested_operand(_operand(product, 0), leaf_type, scope)
        # nestedNotEq lowers to `not <ext> = ?` (the corpus form), not `<ext> <> ?`.
        if op.op == "nestedNotEq":
            return f"not {casted} = ?"
        return f"{casted} {_NESTED_COMPARATORS[op.op]} ?"
    if isinstance(op, NestedRange):
        casted = scope.dialect.nested_cast(extraction, leaf_type)
        _bind_nested_operand(_operand(product, 0), leaf_type, scope)
        _bind_nested_operand(_operand(product, 1), leaf_type, scope)
        # One `between`, never two comparisons: through a `many` member the flat
        # family is any-element, so a lowered pair could be satisfied by two
        # DIFFERENT elements (m-predicate).
        return f"{casted} between ? and ?"
    if isinstance(op, NestedMembership):
        casted = scope.dialect.nested_cast(extraction, leaf_type)
        holes = ", ".join("?" for _ in op.values)
        for operand in _operands(product):
            _bind_nested_operand(operand, leaf_type, scope)
        # nestedNotIn lowers to a LEADING `not` (the corpus form), adding no bind.
        fragment = f"{casted} in ({holes})"
        return fragment if op.op == "nestedIn" else f"not {fragment}"
    if isinstance(op, NestedStringMatch):
        # No cast: the leaf is a `String` member by the non-string-member rule
        # (m-predicate), so the text extraction IS what the pattern matches.
        return _lower_like(
            _NESTED_STRING_KINDS[op.op],
            str(_operand(product, 0)),
            op.case_insensitive,
            extraction,
            scope,
        )
    if isinstance(op, NestedNullCheck) and op.op == "nestedIsNull":
        return f"{extraction} is null"
    return f"not {extraction} is null"


def _bind_nested_operand(value: object, leaf_type: NeutralType, scope: ResolutionScope) -> None:
    """Bind one managed document operand in the form its extraction compares.

    Typed extraction binds the managed value directly; text extraction derives the
    codec-owned comparison text. Wire decoding already occurred in predicate validation.
    """

    if is_text_compared(leaf_type):
        scope.ctx.bind_comparison_text(comparison_text(leaf_type, value), leaf_type)
    else:
        scope.ctx.bind_managed(value, leaf_type)


def _split_at_many(
    vo: ValueObjectMetadata, segments: Sequence[str]
) -> tuple[_VoContainer, tuple[str, ...], tuple[str, ...]] | None:
    """Split a flat predicate's path at the first `multiplicity: many` hop
    crossed while walking from `vo` (m-predicate "Flat predicates through a
    `many` segment mean any element matches"). Returns ``(the many container,
    the segments reaching it from vo's own document column, the remaining
    segments addressing a field WITHIN the element)`` — or ``None`` when the
    walk never crosses a `many` member (the plain scalar-extraction case
    :func:`_lower_nested` handles directly).
    """
    if vo.multiplicity is Multiplicity.MANY:
        return vo, (), tuple(segments)
    container: _VoContainer = vo
    for index, segment in enumerate(segments):
        member = container.value_object(segment)
        if member is None:
            return None  # reached a scalar leaf (or an unresolved segment) uncrossed
        if member.multiplicity is Multiplicity.MANY:
            return member, tuple(segments[: index + 1]), tuple(segments[index + 1 :])
        container = member
    return None


def _lower_any_element(
    product: ValidatedPredicate,
    vo: ValueObjectMetadata,
    crossing: tuple[_VoContainer, tuple[str, ...], tuple[str, ...]],
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
        authored = product.authored
        path = (
            authored.path
            if isinstance(
                authored,
                (
                    NestedComparison,
                    NestedRange,
                    NestedMembership,
                    NestedStringMatch,
                    NestedNullCheck,
                ),
            )
            else "?"
        )
        raise SqlGenError(
            f"nested path {path!r} ends on the `many` array itself, not a field within its elements"
        )
    leaf = _value_object_leaf(product)
    # The owning document column is the target's own (bare under `unaliased`); the
    # unnested ELEMENT is not, and stays alias-qualified either way — this very
    # subquery declares `array_alias`, so there is no alias here to leak.
    document, prefix = scope.document_root(vo)
    guard_sql, guard_binds = scope.dialect.array_guard(document, (*prefix, *pre))
    scope.ctx.bind_framework_all(guard_binds)
    element = ElementScope(ctx=scope.ctx, container=container, alias=scope.next_alias())
    extraction, path_binds = scope.dialect.nested_extract(element.element_reference(), post)
    scope.ctx.bind_structural_all(path_binds)
    comparator = _lower_comparator(product, extraction, leaf.type, scope)
    return (
        f"exists (select 1 from jsonb_array_elements({guard_sql}) "
        f"{element.alias} where {comparator})"
    )


# --------------------------------------------------------------------------- #
# `nestedExists` / `nestedNotExists` (m-sql "To-many — exists / notExists and  #
# any-element predicates").                                                    #
# --------------------------------------------------------------------------- #
def _lower_nested_exists(product: ValidatedPredicate, scope: EntityScope) -> str:
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
    op = product.authored
    if not isinstance(op, (NestedExists, NestedNotExists)):  # pragma: no cover
        raise AssertionError("validated nested-exists product has the wrong authored node")
    container = product.container
    if container is None:
        raise SqlGenError("validated nested-exists carries no resolved container")
    identity = container.identity
    vo = _entity_view(scope.facet, identity.entity).applicable_value_object(identity.path[0])
    if vo is None:
        raise SqlGenError(f"validated Value Object {identity} is absent from the active position")
    pre = tuple(identity.path[1:])
    if container.multiplicity is not Multiplicity.MANY:
        raise SqlGenError(
            f"nestedExists/nestedNotExists over a `one`-multiplicity value object "
            f"({op.path!r}) has no goldened lowering yet"
        )
    document, prefix = scope.document_root(vo)
    guard_sql, guard_binds = scope.dialect.array_guard(document, (*prefix, *pre))
    scope.ctx.bind_framework_all(guard_binds)
    element = ElementScope(ctx=scope.ctx, container=container, alias=scope.next_alias())
    inner = f"select 1 from jsonb_array_elements({guard_sql}) {element.alias}"
    if op.where is not None:
        inner = f"{inner} where {lower_predicate(product.only_child(), element)}"
    keyword = "not exists" if isinstance(op, NestedNotExists) else "exists"
    return f"{keyword} ({inner})"
