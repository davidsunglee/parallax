from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Final, Literal, assert_never

from parallax.core.base import STRING, Bytes, ManagedValue, NeutralType
from parallax.core.dialect import Dialect, projection_result_key
from parallax.core.document_codec import comparison_text, is_text_compared
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    OccurrenceMetadata,
    TablePerHierarchy,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.predicate import MembershipOp, StringOp
from parallax.core.predicate._resolved import (
    CurrentObject,
    DeferredKeySet,
    ObjectPosition,
    RelatedObject,
    ResolvedAnd,
    ResolvedComparison,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedMembership,
    ResolvedNarrow,
    ResolvedNot,
    ResolvedNullCheck,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedPredicateMember,
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedRelationship,
    ResolvedStringMatch,
    ScalarCollection,
    ScalarElement,
    SubjectPosition,
    disjunctive,
)
from parallax.core.sql_gen._context import SqlGenError, StatementBuilder
from parallax.core.sql_gen._context import table_layout as _table_layout

# The family LANE of the compiler — distinct from `parallax.core.inheritance`
# above, which is the metamodel module. Aliased down to the module-private
# spelling, so a use site below never confuses the two.
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import (
    plan_resolved_branch_narrow as _plan_resolved_branch_narrow,
)
from parallax.core.sql_gen._inheritance import tag_column as _tag_column
from parallax.core.sql_gen._inheritance import tag_guard as _tph_tag_guard

# The navigation LANE: hop plans in, correlated subqueries out. Same
# aliasing-down convention as the family lane above.
from parallax.core.sql_gen._navigation import HopPlan as _HopPlan
from parallax.core.sql_gen._navigation import OpenBranch as _OpenBranch
from parallax.core.sql_gen._navigation import open_branch as _open_branch
from parallax.core.sql_gen._navigation import plan_resolved_hop as _plan_resolved_hop
from parallax.core.storage_layout import (
    ColumnContributor,
    DirectColumn,
    DocumentPath,
    StorageLayoutFacet,
    TableLayout,
)
from parallax.core.wire._codec import encoded_json_kind

_HOP_TOKENS: Final = itertools.count()

_COMPARATORS: dict[str, str] = {
    "eq": "=",
    "notEq": "<>",
    "greaterThan": ">",
    "greaterThanEquals": ">=",
    "lessThan": "<",
    "lessThanEquals": "<=",
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
    position: Sequence[EntityIdentity] | None = None
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
        form can never be bypassed. :meth:`column_of` and :meth:`subject_for` are
        the attribute-resolving front doors; a Structured Column is not an
        ``Attribute`` and so has no Attribute to resolve, but it is just as much
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
        self.record_document_applicability(attribute.identity.entity)
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
            self.record_document_applicability(vo.identity.entity)
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

    def record_document_applicability(self, owner: EntityIdentity) -> None:
        """Note that this statement reads a document member ``owner`` declares,
        which partitions an abstract read whose variants do not all carry it."""
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

    def child(
        self, entity: EntityMetadata, alias: str, variant: EntityIdentity | None = None
    ) -> EntityScope:
        """A nested scope for a correlated hop's interior: the SAME statement
        context (so a nested hop's binds and aliases continue this statement's
        single sequence), a different active entity and alias, and — for one
        concrete table of a table-per-concrete-subtype target — that ``variant``.

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
            variant=variant,
        )


@dataclass(frozen=True, slots=True)
class ElementScope:
    """A predicate resolving against ONE UNNESTED value-object array element
    (m-value-object same-element semantics).

    Every leaf a quantifier's `where` reads is element-relative (`type`,
    `geo.country`) and resolves against :attr:`container`, the same array
    element they all share, extracted through the alias the unnest declared. There is no
    ``unaliased`` here and there cannot be one: that alias is this statement's
    own declaration, so it qualifies in a write's predicate exactly as it does
    in a read's.
    """

    ctx: StatementBuilder
    container: OccurrenceMetadata
    alias: str

    @property
    def dialect(self) -> Dialect:
        return self.ctx.dialect

    def element_reference(self) -> str:
        """This element's own `t<n>.value` document reference."""
        return self.dialect.qualified(self.alias, "value")


@dataclass(frozen=True, slots=True)
class ScalarElementScope:
    """A predicate resolving against ONE UNNESTED scalar-collection element.

    Every operation a scalar quantifier's `where` holds reads this element, a
    scalar of :attr:`member`'s declared type, through the alias the unnest
    declared — always alias-qualified, for the reason :class:`ElementScope`'s
    is.
    """

    ctx: StatementBuilder
    member: ResolvedPredicateMember
    alias: str

    @property
    def dialect(self) -> Dialect:
        return self.ctx.dialect

    def element_reference(self) -> str:
        return self.dialect.qualified(self.alias, "value")


ResolutionScope = EntityScope | ElementScope | ScalarElementScope

type _Operation = (
    ResolvedComparison
    | ResolvedRange
    | ResolvedMembership
    | ResolvedStringMatch
    | ResolvedNullCheck
)
type _Demand = Callable[[ResolutionScope], str]


def lower_predicate(predicate: ResolvedPredicate, scope: ResolutionScope) -> str:
    """Lower one resolved predicate to a SQL fragment, appending binds in order.

    A constant true lowers to the empty fragment, which a caller omits from its
    `where`; composed inside another term it renders as an always-true one.
    """
    match predicate:
        case ResolvedConstant(truth=truth):
            return "" if truth else "1 = 0"
        case ResolvedAnd(operands=operands):
            return " and ".join(_term(operand, scope) for operand in operands)
        case ResolvedOr(operands=operands):
            return " or ".join(_term(operand, scope) for operand in operands)
        case ResolvedNot(operand=operand):
            return _negated(operand, scope)
        case ResolvedGroup(operand=operand):
            return f"({_term(operand, scope)})"
        case (
            ResolvedComparison()
            | ResolvedRange()
            | ResolvedMembership()
            | ResolvedStringMatch()
            | ResolvedNullCheck()
        ):
            return _lower_operation(predicate, scope)
        case ResolvedQuantifier():
            return _at(
                predicate.position,
                scope,
                lambda reached: _lower_quantifier(predicate, reached),
                "false" if predicate.kind == "any" else "true",
            )
        case ResolvedPresence():
            return _lower_presence(predicate, scope)
        case ResolvedNarrow():
            return _lower_narrow(predicate, scope)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(predicate)


def _term(predicate: ResolvedPredicate, scope: ResolutionScope) -> str:
    return lower_predicate(predicate, scope) or "1 = 1"


def _negated(operand: ResolvedPredicate, scope: ResolutionScope) -> str:
    """``operand`` negated whole: `not` binds tighter than `and` and `or`."""
    sql = _term(operand, scope)
    return f"not ({sql})" if isinstance(operand, ResolvedAnd | ResolvedOr) else f"not {sql}"


def _conjunct(predicate: ResolvedPredicate, scope: ResolutionScope) -> str:
    """``predicate`` lowered to stand complete beside an `and`: a disjunction is
    grouped so a conjoined framework term cannot re-associate it."""
    sql = lower_predicate(predicate, scope)
    return f"({sql})" if sql and disjunctive(predicate) else sql


def _lower_operation(operation: _Operation, scope: ResolutionScope) -> str:
    """One scalar operation over its member's subject expression.

    The subject resolves FIRST: a document-resident member's path segments, and
    every bind a related position's subqueries carry, bind ahead of the
    compared values, which is the order the emitted text puts their holes in.
    """
    if _unreachable(operation.position, scope):
        return _absent_operation(operation)
    reads_text = isinstance(operation, ResolvedStringMatch | ResolvedNullCheck)
    subject = _subject_at(operation.member, operation.position, scope, reads_text=reads_text)
    match operation:
        case ResolvedComparison(op=tag, value=value, framework=framework):
            _bind_operand(value, subject, scope, framework=framework)
            # A Value Object leaf's inequality keeps its negated-equality form.
            if tag == "notEq" and not isinstance(operation.member, AttributeMetadata):
                return f"not {subject.compared} = ?"
            return f"{subject.compared} {_COMPARATORS[tag]} ?"
        case ResolvedRange(lower=lower, upper=upper):
            _bind_operand(lower, subject, scope)
            _bind_operand(upper, subject, scope)
            return f"{subject.compared} between ? and ?"
        case ResolvedMembership(op=tag, values=values):
            return _lower_membership(tag, values, subject, scope)
        case ResolvedStringMatch(op=tag, pattern=pattern, case_insensitive=folded):
            return _lower_like(tag, pattern, folded, subject.extraction, scope)
        case ResolvedNullCheck(op=tag):
            column = subject.extraction
            return f"{column} is null" if tag == "isNull" else f"not {column} is null"
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(operation)


def _absent_operation(operation: _Operation) -> str:
    """An operation over a field no candidate can supply: a null check sees the
    missing value, and every other operation is unknown."""
    if isinstance(operation, ResolvedNullCheck):
        return "1 = 1" if operation.op == "isNull" else "1 = 0"
    return "null"


def _subject_at(
    member: ResolvedPredicateMember,
    position: SubjectPosition,
    scope: ResolutionScope,
    *,
    reads_text: bool,
) -> MemberSubject:
    """``member`` as read at ``position`` from ``scope``.

    A related position is reached through one scalar subquery per to-one hop,
    each selecting what the operation demands — its extraction when it reads
    text, else its compared value — so absence at any hop reads as SQL null.
    """
    if isinstance(position, ScalarElement):
        if not isinstance(scope, ScalarElementScope):  # pragma: no cover - validated scopes
            raise SqlGenError(f"{member.identity} element is read outside its quantifier")
        return _element_subject(member, scope)
    if isinstance(position, CurrentObject):
        return _subject(member, scope)
    reached: list[MemberSubject] = []

    def demand(inner: ResolutionScope) -> str:
        subject = _subject(member, inner)
        reached.append(subject)
        return subject.extraction if reads_text else subject.compared

    expression = _at(position, scope, demand, None)
    first = reached[0]
    return MemberSubject(
        expression,
        expression,
        first.type,
        document_resident=first.document_resident,
        text_compared=first.text_compared,
    )


def _subject(member: ResolvedPredicateMember, scope: ResolutionScope) -> MemberSubject:
    """``member`` as read from ``scope``'s current object.

    An Attribute is read through its Member Placement. A Value Object leaf is a
    document extraction: from the Entity's document through single occurrences,
    or from the element a quantifier binds, relative to its occurrence.
    """
    if isinstance(scope, ScalarElementScope):  # pragma: no cover - validated scopes
        raise SqlGenError(f"{member.identity} is not read from a scalar element")
    if isinstance(member, AttributeMetadata):
        if isinstance(scope, ElementScope):
            raise SqlGenError(f"{member.identity} is not read from a Value Object element")
        return scope.subject_for(member)
    if isinstance(scope, EntityScope):
        vo, segments = _resolved_vo_path(member, scope)
        document, prefix = scope.document_root(vo)
        reference, path = document, (*prefix, *segments)
    else:
        reference, path = (
            scope.element_reference(),
            (
                *_relative_path(member.identity.value_object.path, scope.container),
                member.identity.name,
            ),
        )
    extraction, path_binds = scope.dialect.nested_extract(reference, path)
    scope.ctx.bind_structural_all(path_binds)
    return MemberSubject(
        extraction,
        scope.dialect.nested_cast(extraction, member.type),
        member.type,
        document_resident=True,
        text_compared=is_text_compared(member.type),
    )


def _element_subject(member: ResolvedPredicateMember, scope: ScalarElementScope) -> MemberSubject:
    """The bound element as a scalar of ``member``'s declared type, projected
    only where its JSON kind is the one that type's canonical encoding takes."""
    kind = encoded_json_kind(member.type)
    if kind is None:  # pragma: no cover - only Json lacks one kind, and no collection holds it
        raise SqlGenError(f"{member.type!r} elements carry no single JSON kind")
    extraction, compared, binds = scope.dialect.scalar_element(
        scope.element_reference(), kind, member.type
    )
    scope.ctx.bind_structural_all(binds)
    return MemberSubject(
        extraction,
        compared,
        member.type,
        document_resident=True,
        text_compared=is_text_compared(member.type),
    )


def _relative_path(path: tuple[str, ...], container: OccurrenceMetadata) -> tuple[str, ...]:
    base = container.identity.path
    if path[: len(base)] != base:
        raise SqlGenError("resolved element member is outside its resolved container")
    return path[len(base) :]


def _lower_membership(
    tag: MembershipOp,
    values: tuple[ManagedValue, ...] | DeferredKeySet,
    subject: MemberSubject,
    scope: ResolutionScope,
) -> str:
    if isinstance(values, DeferredKeySet):
        if tag != "in":  # pragma: no cover - generated child reads are positive
            raise SqlGenError("a deferred key set supports only positive membership")
        if scope.dialect.name == "postgres":
            scope.ctx.bind_managed_array(values, values.neutral_type)
            return f"{subject.compared} = any(?)"
        scope.ctx.bind_managed(values, values.neutral_type)
        return f"{subject.compared} in (__parallax_deferred_keys__)"
    holes = ", ".join("?" for _ in values)
    for value in values:
        _bind_operand(value, subject, scope)
    fragment = f"{subject.compared} in ({holes})"
    return fragment if tag == "in" else f"not {fragment}"


def _bind_operand(
    value: object, subject: MemberSubject, scope: ResolutionScope, *, framework: bool = False
) -> None:
    """Bind one compared operand in the form ``subject``'s expression compares.

    A direct Column is compared in the engine's own column type, so its operand
    crosses the seam as its managed value with explicit neutral-type metadata,
    or as itself when it is a framework sentinel. A document-resident member is
    compared through an extraction: the codec-owned comparison text where the
    extraction compares as text, the managed value in its declared Neutral Type
    where the extraction casts. Wire decoding already occurred in predicate
    validation.
    """
    if not subject.document_resident:
        if framework:
            scope.ctx.bind_framework(value)
        else:
            scope.ctx.bind_managed(value, subject.type)
    elif subject.text_compared:
        scope.ctx.bind_comparison_text(comparison_text(subject.type, value), subject.type)
    else:
        scope.ctx.bind_managed(value, subject.type)


def _lower_like(
    kind: StringOp,
    value: str,
    case_insensitive: bool,
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


def _at(
    position: ObjectPosition, scope: ResolutionScope, demand: _Demand, default: str | None
) -> str:
    """``demand`` evaluated at ``position`` from ``scope``.

    Each to-one hop is one correlated scalar subquery over every candidate the
    relationship declares, so it asserts its own cardinality where it is
    evaluated: no candidate is SQL null — or ``default`` — and several fail.
    Hops nest rather than join, so an absent later target never hides an
    earlier hop's candidates.
    """
    if isinstance(position, CurrentObject):
        return demand(scope)
    hops: list[ResolvedRelationship] = []
    current: ObjectPosition = position
    while isinstance(current, RelatedObject):
        hops.append(current.relationship)
        current = current.source
    hops.reverse()
    if not isinstance(scope, EntityScope):  # pragma: no cover - validated scopes
        raise SqlGenError("a relationship is reached only from an Entity position")
    if any(_reaches_nothing(hop, scope) for hop in hops):
        if default is None:  # pragma: no cover - an operation answers before demanding
            raise SqlGenError("a field is read through a relationship with no candidate")
        return default
    return _hop_chain(hops, scope, demand, default)


def _unreachable(position: SubjectPosition, scope: ResolutionScope) -> bool:
    """Whether some hop toward ``position`` reaches a target with no concrete
    subtype, so no candidate can exist there."""
    current = position
    while isinstance(current, RelatedObject):
        if _reaches_nothing(current.relationship, _entity_scope(scope)):
            return True
        current = current.source
    return False


def _reaches_nothing(relationship: ResolvedRelationship, scope: EntityScope) -> bool:
    target = relationship.target
    if target.inheritance is None:
        return False
    return not _entity_view(scope.facet, target.identity).concrete_subtypes


def _hop_chain(
    hops: Sequence[ResolvedRelationship], scope: EntityScope, demand: _Demand, default: str | None
) -> str:
    first, rest = hops[0], hops[1:]
    if not rest:
        return _scalar_hop(first, scope, demand, default)
    return _scalar_hop(
        first,
        scope,
        lambda reached: _hop_chain(rest, _entity_scope(reached), demand, default),
        default,
    )


def _entity_scope(scope: ResolutionScope) -> EntityScope:
    if not isinstance(scope, EntityScope):  # pragma: no cover - a hop's candidate is an Entity
        raise SqlGenError("a relationship is reached only from an Entity position")
    return scope


def _scalar_hop(
    relationship: ResolvedRelationship, scope: EntityScope, inner: _Demand, default: str | None
) -> str:
    """One correlated scalar subquery selecting ``inner`` from each candidate
    ``relationship`` reaches; a table-per-concrete-subtype target contributes
    every declared branch with `union all`."""
    plan = _hop_plan(relationship, scope, position=None, negate=False)
    tpcs = _is_tpcs(relationship.target, scope)
    branches: list[str] = []
    for branch in plan.branches:
        # The branch's value precedes its own table in the text, so every alias the
        # value declares is allocated first and this branch's alias after it,
        # keeping aliases in source order (m-sql rule 1); a placeholder stands in
        # for the alias until then.
        token = f"__hop{next(_HOP_TOKENS)}__"
        opened = _open_branch(branch, scope, alias=token)
        branch_scope = scope.child(opened.entity, token, opened.entity.identity if tpcs else None)
        value = inner(branch_scope)
        alias = scope.next_alias()
        where = _candidate_where(relationship, branch_scope, opened, None)
        selected = f"select {value} from {opened.table} {token} where {where}"
        branches.append(selected.replace(token, alias))
    subquery = f"({' union all '.join(branches)})"
    return subquery if default is None else f"coalesce({subquery}, {default})"


def _hop_plan(
    relationship: ResolvedRelationship,
    scope: EntityScope,
    *,
    position: tuple[EntityIdentity, ...] | None,
    negate: bool,
) -> _HopPlan:
    return _plan_resolved_hop(
        relationship.target,
        relationship.source,
        relationship.related,
        position=position,
        scope=scope,
        negate=negate,
    )


def _opened_branches(
    plan: _HopPlan, relationship: ResolvedRelationship, scope: EntityScope
) -> Iterator[tuple[_OpenBranch, EntityScope]]:
    """Each planned branch with its alias and scope, opened lazily: a branch
    takes its alias immediately before its own interior lowers, so a later
    branch's alias follows everything the preceding one allocated."""
    tpcs = _is_tpcs(relationship.target, scope)
    for branch in plan.branches:
        opened = _open_branch(branch, scope)
        yield (
            opened,
            scope.child(opened.entity, opened.alias, opened.entity.identity if tpcs else None),
        )


def _is_tpcs(target: EntityMetadata, scope: EntityScope) -> bool:
    if target.inheritance is None:
        return False
    return not isinstance(_entity_view(scope.facet, target.identity).strategy, TablePerHierarchy)


def _candidate_where(
    relationship: ResolvedRelationship,
    scope: EntityScope,
    opened: _OpenBranch,
    interior: str | None,
) -> str:
    """The correlated `where` of one candidate branch: correlation, then the
    interior (if any), then the hop's visibility terms, then its tag guard —
    the guard's binds pushed last because its text comes last."""
    terms = [opened.correlation]
    if interior:
        terms.append(interior)
    terms.extend(_term(term, scope) for term in relationship.visibility)
    terms.extend(opened.tag_fragment)
    scope.ctx.bind_framework_all(opened.tag_binds)
    return " and ".join(terms)


def _lower_quantifier(quantifier: ResolvedQuantifier, scope: ResolutionScope) -> str:
    """A quantifier at the current object of ``scope``.

    ``any`` is a true-matching existence, ``none`` its complement, and ``all``
    the absence of a counterexample — an element for which the COMPLETE
    ``where`` is not true, so a false or unknown element fails it. Each binds
    its own element alias, so separate quantifiers never share one.
    """
    collection = quantifier.collection
    if isinstance(collection, ResolvedRelationship):
        if not isinstance(scope, EntityScope):  # pragma: no cover - validated scopes
            raise SqlGenError("a relationship is quantified only from an Entity position")
        return _lower_relationship_quantifier(quantifier, collection, scope)
    if isinstance(collection, ScalarCollection):
        guard = _scalar_array_guard(collection.member, scope)
        element: ResolutionScope = ScalarElementScope(
            ctx=scope.ctx, member=collection.member, alias=scope.ctx.next_alias()
        )
    else:
        guard = _occurrence_array_guard(collection, scope)
        element = ElementScope(ctx=scope.ctx, container=collection, alias=scope.ctx.next_alias())
    inner = f"select 1 from jsonb_array_elements({guard}) {element.alias}"
    where = quantifier.where
    if quantifier.kind == "all":
        assert where is not None
        return f"not exists ({inner} where {_counterexample(where, element)})"
    if where is not None:
        interior = lower_predicate(where, element)
        if interior:
            inner = f"{inner} where {interior}"
    keyword = "not exists" if quantifier.kind == "none" else "exists"
    return f"{keyword} ({inner})"


def _counterexample(where: ResolvedPredicate, scope: ResolutionScope) -> str:
    """An element the complete predicate ``where`` does not make true."""
    return f"not ({_term(where, scope)}) is true"


def _scalar_array_guard(member: ResolvedPredicateMember, scope: ResolutionScope) -> str:
    """The guarded array a scalar collection's elements are unnested from."""
    if isinstance(scope, ScalarElementScope):  # pragma: no cover - validated scopes
        raise SqlGenError("a scalar element holds no collection")
    if isinstance(member, AttributeMetadata):
        if not isinstance(scope, EntityScope):  # pragma: no cover - validated scopes
            raise SqlGenError(f"{member.identity} is not read from a Value Object element")
        placement = scope.layout.placement(member.identity)
        if isinstance(placement, DocumentPath):
            scope.record_document_applicability(member.identity.entity)
            document, segments = scope.own_column(placement.slot.column.name), placement.path
        else:
            document, segments = scope.own_column(scope.slot_column(member.identity)), ()
    elif isinstance(scope, EntityScope):
        vo, path = _resolved_vo_path(member, scope)
        document, prefix = scope.document_root(vo)
        segments = (*prefix, *path)
    else:
        document = scope.element_reference()
        segments = (
            *_relative_path(member.identity.value_object.path, scope.container),
            member.identity.name,
        )
    guard, binds = scope.dialect.array_guard(document, segments)
    scope.ctx.bind_framework_all(binds)
    return guard


def _occurrence_array_guard(occurrence: OccurrenceMetadata, scope: ResolutionScope) -> str:
    """The guarded array a ``many`` Value Object's elements are unnested from."""
    document, segments = _occurrence_carrier(occurrence, scope)
    guard, binds = scope.dialect.array_guard(document, segments)
    scope.ctx.bind_framework_all(binds)
    return guard


def _occurrence_carrier(
    occurrence: OccurrenceMetadata, scope: ResolutionScope
) -> tuple[str, tuple[str, ...]]:
    """The rendered document carrying ``occurrence`` and the path reaching it."""
    identity = occurrence.identity
    if isinstance(scope, EntityScope):
        vo = _entity_view(scope.facet, identity.entity).applicable_value_object(identity.path[0])
        if vo is None:
            raise SqlGenError(
                f"resolved Value Object {identity} is absent from the active position"
            )
        document, prefix = scope.document_root(vo)
        return document, (*prefix, *identity.path[1:])
    if isinstance(scope, ScalarElementScope):  # pragma: no cover - validated scopes
        raise SqlGenError("a scalar element holds no Value Object")
    return scope.element_reference(), _relative_path(identity.path, scope.container)


def _lower_relationship_quantifier(
    quantifier: ResolvedQuantifier, relationship: ResolvedRelationship, scope: EntityScope
) -> str:
    """One correlated `exists` per planned branch of the related Entity.

    An ``any`` or ``none`` whose ``where`` is itself a narrowing of the bound
    element selects the branches the hop plans rather than lowering a guard in
    each: an element outside the selection makes that narrowing false, so it
    can neither match ``any`` nor spoil ``none``. A universal keeps every
    branch, because such an element is its counterexample.
    """
    if _reaches_nothing(relationship, scope):
        return "1 = 0" if quantifier.kind == "any" else "1 = 1"
    where = quantifier.where
    narrowed = (
        where
        if quantifier.kind != "all"
        and isinstance(where, ResolvedNarrow)
        and isinstance(where.target, CurrentObject)
        else None
    )
    inner = where if narrowed is None else narrowed.operand
    negate = quantifier.kind != "any"
    plan = _hop_plan(
        relationship,
        scope,
        position=None if narrowed is None else narrowed.selection,
        negate=negate,
    )
    fragments: list[str] = []
    for opened, branch_scope in _opened_branches(plan, relationship, scope):
        if quantifier.kind == "all":
            assert inner is not None
            interior: str | None = _counterexample(inner, branch_scope)
        else:
            interior = None if inner is None else _conjunct(inner, branch_scope)
        where_sql = _candidate_where(relationship, branch_scope, opened, interior)
        fragments.append(
            f"{opened.keyword} (select 1 from {opened.table} {opened.alias} where {where_sql})"
        )
    return plan.combine(fragments)


def _lower_presence(presence: ResolvedPresence, scope: ResolutionScope) -> str:
    """Whether a single object is present, two-valued: an absent target at any
    preceding hop reads as absent."""
    target = presence.target
    if isinstance(presence.position, CurrentObject):
        if isinstance(target, ResolvedRelationship):
            if not isinstance(scope, EntityScope):  # pragma: no cover - validated scopes
                raise SqlGenError("a relationship is reached only from an Entity position")
            return _relationship_presence(target, scope, negate=presence.negated)
        sql = _object_presence(target, scope)
        return f"not {sql}" if presence.negated else sql

    def present(reached: ResolutionScope) -> str:
        if isinstance(target, ResolvedRelationship):
            return _relationship_presence(target, _entity_scope(reached), negate=False)
        return _object_presence(target, reached)

    sql = _at(presence.position, scope, present, "false")
    return f"not {sql}" if presence.negated else sql


def _relationship_presence(
    relationship: ResolvedRelationship, scope: EntityScope, *, negate: bool
) -> str:
    if _reaches_nothing(relationship, scope):
        return "1 = 1" if negate else "1 = 0"
    plan = _hop_plan(relationship, scope, position=None, negate=negate)
    fragments = [
        f"{opened.keyword} (select 1 from {opened.table} {opened.alias} where "
        f"{_candidate_where(relationship, branch_scope, opened, None)})"
        for opened, branch_scope in _opened_branches(plan, relationship, scope)
    ]
    return plan.combine(fragments)


def _object_presence(occurrence: OccurrenceMetadata, scope: ResolutionScope) -> str:
    document, segments = _occurrence_carrier(occurrence, scope)
    sql, binds = scope.dialect.object_presence(document, segments)
    scope.ctx.bind_framework_all(binds)
    return sql


def _lower_narrow(narrow: ResolvedNarrow, scope: ResolutionScope) -> str:
    target = narrow.target
    if isinstance(target, CurrentObject):
        if not isinstance(scope, EntityScope):  # pragma: no cover - validated scopes
            raise SqlGenError("a narrow addresses an Entity position, not a bound element")
        return _lower_branch_narrow(narrow, scope)
    relationship = target.relationship
    if narrow.operand is None:
        return _at(
            target.source,
            scope,
            lambda reached: _scalar_hop(
                relationship,
                _entity_scope(reached),
                lambda candidate: _selected(narrow, relationship, _entity_scope(candidate)),
                "false",
            ),
            "false",
        )
    dialect = scope.dialect
    default = dialect.absent_envelope()
    operand = narrow.operand
    envelope = _at(
        target.source,
        scope,
        lambda reached: _scalar_hop(
            relationship,
            _entity_scope(reached),
            lambda candidate: dialect.boolean_envelope(
                _selected_operand(narrow, relationship, _entity_scope(candidate), operand)
            ),
            default,
        ),
        default,
    )
    return dialect.envelope_value(envelope)


def _selected(
    narrow: ResolvedNarrow, relationship: ResolvedRelationship, candidate: EntityScope
) -> str:
    """Whether ``candidate`` belongs to the narrowing's selection: its tag
    guard in a hierarchy table, its branch's own answer in a concrete table."""
    target = relationship.target
    if target.inheritance is None:
        return "true"
    if candidate.variant is not None:
        return "true" if candidate.variant in narrow.selection else "false"
    root = _entity_view(candidate.facet, target.identity).root
    layout = _table_layout(candidate.storage, candidate.facet, root)
    tag_sql, tag_binds = _tph_tag_guard(
        candidate, candidate.facet, _TagPredicate(_tag_column(layout, root), narrow.selection)
    )
    candidate.ctx.bind_framework_all(tag_binds)
    return tag_sql


def _selected_operand(
    narrow: ResolvedNarrow,
    relationship: ResolvedRelationship,
    candidate: EntityScope,
    operand: ResolvedPredicate,
) -> str:
    """The narrowing's complete result at one candidate: the operand where the
    candidate is selected, false where it is not."""
    if candidate.variant is not None:
        if candidate.variant not in narrow.selection:
            return "false"
        return _term(operand, candidate)
    selected = _selected(narrow, relationship, candidate)
    if selected == "true":
        return _term(operand, candidate)
    return f"case when {selected} then {_term(operand, candidate)} else false end"


def _lower_branch_narrow(narrow: ResolvedNarrow, scope: EntityScope) -> str:
    """A `narrow` of the current Entity — a **grouped branch predicate** (m-sql
    "Grouped branch predicates"): the branch's own operand composes with its
    own tag guard via `and`, and the composition is wrapped in parens whenever
    there is a branch predicate to disambiguate against a sibling branch joined
    by `or` (`m-inheritance-015`).
    """
    plan = _plan_resolved_branch_narrow(scope.facet, scope.storage, scope.entity, narrow.selection)
    operand = narrow.operand
    if scope.variant is not None:
        if scope.variant not in plan.position:
            return "1 = 0"
        return ("" if operand is None else _conjunct(operand, scope)) or "1 = 1"
    if plan.tag is None:  # pragma: no cover - TPCS union branches always carry a variant
        raise SqlGenError("a TPCS branch narrow requires a concrete branch scope")
    # Branch predicate first, THEN the guard's binds — the same explicit ordering
    # the top-level read states, for the same reason.
    branch_sql = "" if operand is None else _conjunct(operand, scope)
    tag_sql, tag_binds = _tph_tag_guard(scope, scope.facet, plan.tag)
    scope.ctx.bind_framework_all(tag_binds)
    if not branch_sql:
        return tag_sql
    return f"({branch_sql} and {tag_sql})"


def _resolved_vo_path(
    leaf: ValueObjectAttributeMetadata, scope: EntityScope
) -> tuple[ValueObjectMetadata, tuple[str, ...]]:
    identity = leaf.identity.value_object
    vo = _entity_view(scope.facet, identity.entity).applicable_value_object(identity.path[0])
    if vo is None:
        raise SqlGenError(f"resolved Value Object {identity} is absent from the active position")
    return vo, (*identity.path[1:], leaf.identity.name)
