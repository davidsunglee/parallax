from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Literal, assert_never

from parallax.core.base import INFINITY, STRING, Bytes, ManagedValue, NeutralType
from parallax.core.dialect import Dialect, projection_result_key
from parallax.core.document_codec import comparison_text, is_text_compared
from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    OccurrenceMetadata,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.predicate import ComparisonOp, MembershipOp, StringOp
from parallax.core.predicate._perspective import (
    AtPerspective,
    LatestPerspective,
    TemporalPerspective,
)
from parallax.core.predicate._resolved import (
    CurrentObject,
    DeferredKeySet,
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
    disjunctive,
)
from parallax.core.sql_gen._context import SqlGenError, StatementBuilder
from parallax.core.sql_gen._context import table_layout as _table_layout

# The family LANE of the compiler — distinct from `parallax.core.inheritance`
# above, which is the metamodel module. Aliased down to the module-private
# spelling, so a use site below never confuses the two.
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import tag_guard as _tph_tag_guard

# The navigation LANE renders planned candidates; the planning lane decides
# every placement before anything renders. Same aliasing-down convention as
# the family lane.
from parallax.core.sql_gen._navigation import (
    RenderedRelationshipCandidate as _RenderedRelationshipCandidate,
)
from parallax.core.sql_gen._navigation import (
    render_relationship_candidate as _render_relationship_candidate,
)
from parallax.core.sql_gen._planning import BranchSelection as _BranchSelection
from parallax.core.sql_gen._planning import CandidateExistence as _CandidateExistence
from parallax.core.sql_gen._planning import CandidateOperand as _CandidateOperand
from parallax.core.sql_gen._planning import (
    ConfinedScalarEvaluation as _ConfinedScalarEvaluation,
)
from parallax.core.sql_gen._planning import Continuation as _Continuation
from parallax.core.sql_gen._planning import JoinedTargetMatch as _JoinedTargetMatch
from parallax.core.sql_gen._planning import LexicalScopeId as _LexicalScopeId
from parallax.core.sql_gen._planning import LexicalScopePlan as _LexicalScopePlan
from parallax.core.sql_gen._planning import NoCandidate as _NoCandidate
from parallax.core.sql_gen._planning import OwnerResultEvaluation as _OwnerResultEvaluation
from parallax.core.sql_gen._planning import OwnerResultsPlan as _OwnerResultsPlan
from parallax.core.sql_gen._planning import OwnerResultsRef as _OwnerResultsRef
from parallax.core.sql_gen._planning import PlannedHop as _PlannedHop
from parallax.core.sql_gen._planning import PredicatePath as _PredicatePath
from parallax.core.sql_gen._planning import PredicatePlacement as _PredicatePlacement
from parallax.core.sql_gen._planning import (
    RelationshipCandidateBranch as _RelationshipCandidateBranch,
)
from parallax.core.sql_gen._planning import SharedRowEvaluation as _SharedRowEvaluation
from parallax.core.sql_gen._planning import SharedSourcePlan as _SharedSourcePlan
from parallax.core.sql_gen._planning import SharedSourceRef as _SharedSourceRef
from parallax.core.sql_gen._planning import StatementPlan as _StatementPlan
from parallax.core.sql_gen._planning import SubtypeSelection as _SubtypeSelection
from parallax.core.sql_gen._planning import TargetSelection as _TargetSelection
from parallax.core.sql_gen._planning import Terminal as _Terminal
from parallax.core.sql_gen._planning import UnsharedEvaluation as _UnsharedEvaluation
from parallax.core.sql_gen._planning import temporal_visibility as _temporal_visibility
from parallax.core.storage_layout import (
    ColumnContributor,
    DirectColumn,
    DocumentPath,
    TableLayout,
)
from parallax.core.wire._codec import encoded_json_kind

_HOP_TOKENS: Final = itertools.count()
# Typed, because an untyped null a scalar subquery selects reads as text.
_UNKNOWN: Final = "cast(null as boolean)"

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
class EntityRowScope:
    """The ENTITY row a predicate renders against: the active target, its
    alias, and how this statement names that row's columns.

    ``unaliased`` is the write lane (`m-batch-write.md` "Predicate-selected
    readless forms"): a write's rendered predicate is UNALIASED (`where balance
    < ?`), contrasting a read's aliased `t0.balance < ?` form.
    ``False`` — the read compiler's default — for every ordinary read scope. It
    lives on the scope rather than on the context precisely so that
    `compile_write_predicate` reaches the very same vocabulary a read does, one
    flag apart.

    ``layout`` is the ONE physical Table this statement (or `union all` branch)
    reads, so every reference to a member's column is answered by a Storage
    Layout slot rather than by re-reading the member's own storage declaration.
    A branch of a table-per-concrete-subtype union carries its OWN branch layout
    even though its active entity stays the read's queried `target`.

    ``wrapped`` says :attr:`alias` is a derived table over a union of branches
    that already applied their own per-type projection, so a direct member is
    named by the RESULT key a branch projected it under rather than by the
    physical Column no such union yields — and a `bytes` member is then the
    hex-encoded text that key carries rather than octets.
    """

    ctx: StatementBuilder[EntityRowScope]
    entity: EntityMetadata
    layout: TableLayout
    alias: str = "t0"
    unaliased: bool = False
    wrapped: bool = False

    @property
    def meta(self) -> Metamodel:
        return self.ctx.meta

    @property
    def facet(self) -> InheritanceFacet:
        return self.ctx.facet

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

    def next_alias(self) -> str:
        return self.ctx.next_alias()

    def child(self, entity: EntityMetadata, alias: str) -> EntityRowScope:
        """A nested row for a correlated hop's interior: the SAME statement
        context (so a nested hop's binds and aliases continue this statement's
        single sequence), a different active entity and alias.

        ``unaliased`` deliberately does NOT travel: the subquery this scope
        describes declares `alias` itself, so its columns are alias-qualified
        even inside a write's otherwise-unaliased predicate (`t1.folder_id = id`
        — the child correlation qualified, the parent column bare). The child's
        own Table Layout does travel, because the hop selects from the child's
        own table.
        """
        return EntityRowScope(
            ctx=self.ctx,
            entity=entity,
            layout=_table_layout(self.ctx.storage, self.ctx.facet, entity.identity),
            alias=alias,
        )


@dataclass(frozen=True, slots=True)
class ValueObjectElementScope:
    """A predicate resolving against ONE UNNESTED value-object array element
    (m-value-object same-element semantics).

    Every leaf a quantifier's `where` reads is element-relative (`type`,
    `geo.country`) and resolves against :attr:`container`, the same array
    element they all share, extracted through the alias the unnest declared. There is no
    ``unaliased`` here and there cannot be one: that alias is this statement's
    own declaration, so it qualifies in a write's predicate exactly as it does
    in a read's.
    """

    ctx: StatementBuilder[EntityRowScope]
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
    declared — always alias-qualified, for the reason
    :class:`ValueObjectElementScope`'s is.
    """

    ctx: StatementBuilder[EntityRowScope]
    member: ResolvedPredicateMember
    alias: str

    @property
    def dialect(self) -> Dialect:
        return self.ctx.dialect

    def element_reference(self) -> str:
        return self.dialect.qualified(self.alias, "value")


type PredicateScope = EntityRowScope | ValueObjectElementScope | ScalarElementScope

type _Operation = (
    ResolvedComparison
    | ResolvedRange
    | ResolvedMembership
    | ResolvedStringMatch
    | ResolvedNullCheck
)
type _Value = Callable[[PredicateScope], str]
type _Emit = Callable[[PredicateScope, _Terminal], str]


def render_predicate(
    *,
    statement_plan: _StatementPlan,
    scope_id: _LexicalScopeId,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    """Render the occurrence at ``path`` of lexical plan ``scope_id`` against
    ``scope``, appending binds in order.

    A constant true renders as the empty fragment, which a caller omits from
    its `where`; composed inside another term it renders as an always-true one.
    """
    lexical = statement_plan.lexical_scopes[scope_id]
    return _render(_occurrence(lexical.predicate, path), statement_plan, lexical, path, scope)


def _occurrence(predicate: ResolvedPredicate, path: _PredicatePath) -> ResolvedPredicate:
    """The occurrence ``path`` addresses within one lexical plan's predicate: an
    operand index of `and`/`or`, else slot ``0`` of a unary operand, a narrowing
    of the row, or a document collection's element body."""
    for slot in path:
        match predicate:
            case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands) if (
                0 <= slot < len(operands)
            ):
                predicate = operands[slot]
            case (
                ResolvedNot(operand=child)
                | ResolvedGroup(operand=child)
                | ResolvedNarrow(target=CurrentObject(), operand=child)
                | ResolvedQuantifier(where=child)
            ) if slot == 0 and child is not None and not _relationship_body(predicate):
                predicate = child
            case _:
                raise SqlGenError(f"predicate path {path} addresses no occurrence")
    return predicate


def _relationship_body(predicate: ResolvedPredicate) -> bool:
    """Whether ``predicate``'s body is planned at related rows of its own."""
    return isinstance(predicate, ResolvedQuantifier) and isinstance(
        predicate.collection, ResolvedRelationship
    )


def _render(
    predicate: ResolvedPredicate,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    match predicate:
        case ResolvedConstant(truth=truth):
            return "" if truth else "1 = 0"
        case ResolvedAnd(operands=operands):
            return " and ".join(
                _term(operand, plan, lexical, (*path, index), scope)
                for index, operand in enumerate(operands)
            )
        case ResolvedOr(operands=operands):
            return " or ".join(
                _term(operand, plan, lexical, (*path, index), scope)
                for index, operand in enumerate(operands)
            )
        case ResolvedNot(operand=operand):
            return f"not {_whole(operand, plan, lexical, (*path, 0), scope)}"
        case ResolvedGroup(operand=operand):
            return f"({_term(operand, plan, lexical, (*path, 0), scope)})"
        case (
            ResolvedComparison()
            | ResolvedRange()
            | ResolvedMembership()
            | ResolvedStringMatch()
            | ResolvedNullCheck()
        ):
            return _render_operation(predicate, _placement(lexical, path), lexical, scope)
        case ResolvedQuantifier():
            return _render_quantifier(predicate, plan, lexical, path, scope)
        case ResolvedPresence():
            return _render_presence(predicate, plan, lexical, path, scope)
        case ResolvedNarrow():
            return _render_narrow(predicate, plan, lexical, path, scope)
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(predicate)


def _term(
    predicate: ResolvedPredicate,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    return _render(predicate, plan, lexical, path, scope) or "1 = 1"


def _whole(
    predicate: ResolvedPredicate,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    """``predicate`` rendered as one term, a conjunction or disjunction grouped
    so neither a `not` nor a neighbouring operator re-associates it."""
    sql = _term(predicate, plan, lexical, path, scope)
    return f"({sql})" if isinstance(predicate, ResolvedAnd | ResolvedOr) else sql


def _conjunct(
    predicate: ResolvedPredicate,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    """``predicate`` rendered to stand complete beside an `and`: a disjunction
    is grouped so a conjoined framework term cannot re-associate it."""
    sql = _render(predicate, plan, lexical, path, scope)
    return f"({sql})" if sql and disjunctive(predicate) else sql


def _operand_term(plan: _StatementPlan, scope_id: _LexicalScopeId, scope: EntityRowScope) -> str:
    """The root of operand plan ``scope_id`` rendered as one term at ``scope``."""
    lexical = plan.lexical_scopes[scope_id]
    return _term(lexical.predicate, plan, lexical, (), scope)


def _placement(lexical: _LexicalScopePlan, path: _PredicatePath) -> _PredicatePlacement:
    placement = lexical.placements.get(path)
    if placement is None:
        raise SqlGenError(
            f"predicate occurrence {path} of lexical plan {lexical.scope_id} has no placement"
        )
    return placement


def _render_operation(
    operation: _Operation,
    placement: _PredicatePlacement,
    lexical: _LexicalScopePlan,
    scope: PredicateScope,
) -> str:
    """One scalar operation over its member's subject expression.

    The subject resolves FIRST: a document-resident member's path segments, and
    every bind a related position's subqueries carry, bind ahead of the
    compared values, which is the order the emitted text puts their holes in.
    An occurrence placed on a shared source reads its member from that
    source's joined row, where a missing target supplies SQL null, or through
    the confined scalar subqueries past a shared prefix.
    """
    member = operation.member
    if not isinstance(placement, _UnsharedEvaluation):
        subject = _subject_reached_by(operation, placement, lexical, scope)
    elif not placement.continuation.reaches_target:
        return _absent_operation(operation, placement.continuation, scope)
    elif placement.continuation.hops:
        subject = _subject_reached_by(operation, placement, lexical, scope)
    else:
        subject = _subject_here(member, operation.position, scope)
    match operation:
        case ResolvedComparison(op=tag, value=value, framework=framework):
            _bind_operand(value, subject, scope, framework=framework)
            # A Value Object leaf's inequality keeps its negated-equality form.
            if tag == "notEq" and not isinstance(member, AttributeMetadata):
                return f"not {subject.compared} = ?"
            return f"{subject.compared} {_COMPARATORS[tag]} ?"
        case ResolvedRange(lower=lower, upper=upper):
            _bind_operand(lower, subject, scope)
            _bind_operand(upper, subject, scope)
            return f"{subject.compared} between ? and ?"
        case ResolvedMembership(op=tag, values=values):
            return _render_membership(tag, values, subject, scope)
        case ResolvedStringMatch(op=tag, pattern=pattern, case_insensitive=folded):
            return _render_like(tag, pattern, folded, subject.extraction, scope)
        case ResolvedNullCheck(op=tag):
            column = subject.extraction
            return f"{column} is null" if tag == "isNull" else f"not {column} is null"
        case _:  # pragma: no cover - exhaustiveness guard
            assert_never(operation)


def _subject_reached_by(
    operation: _Operation,
    placement: _PredicatePlacement,
    lexical: _LexicalScopePlan,
    scope: PredicateScope,
) -> MemberSubject:
    """The operation's member at the related row its placement reaches."""
    reads_text = isinstance(operation, ResolvedStringMatch | ResolvedNullCheck)
    member = operation.member
    match placement:
        case _SharedRowEvaluation(source=source):
            return _subject(member, _target(scope, source))
        case _ConfinedScalarEvaluation(prefix=prefix, continuation=continuation):
            return _subject_reached(
                member,
                lambda value: _confined(
                    lexical, prefix, continuation, scope, _valued(value), None, None
                ),
                reads_text=reads_text,
            )
        case _UnsharedEvaluation(continuation=continuation):
            return _subject_reached(
                member,
                lambda value: _continue(continuation, scope, _valued(value), None, None),
                reads_text=reads_text,
            )
        case _OwnerResultEvaluation():  # pragma: no cover - owner results hold quantifiers
            raise SqlGenError("a scalar operation reads no owner result")


def _valued(value: _Value) -> _Emit:
    return lambda reached, _terminal: value(reached)


def _absent_operation(
    operation: _Operation, continuation: _Continuation, scope: PredicateScope
) -> str:
    """An operation over a field no candidate can supply: a null check sees the
    missing value, and every other operation is unknown. The answer is read
    where the continuation stops, before the empty target, so every hop reaching
    it still asserts its cardinality."""
    if isinstance(operation, ResolvedNullCheck):
        answer = "1 = 1" if operation.op == "isNull" else "1 = 0"
        return _continue(continuation, scope, _valued(lambda _: answer), answer, answer)
    return _continue(continuation, scope, _valued(lambda _: _UNKNOWN), _UNKNOWN, None)


def _subject_here(
    member: ResolvedPredicateMember, position: object, scope: PredicateScope
) -> MemberSubject:
    """``member`` as read from ``scope``'s current object or bound element."""
    if isinstance(position, ScalarElement):
        if not isinstance(scope, ScalarElementScope):  # pragma: no cover - validated scopes
            raise SqlGenError(f"{member.identity} element is read outside its quantifier")
        return _element_subject(member, scope)
    return _subject(member, scope)


def _subject_reached(
    member: ResolvedPredicateMember, chain: Callable[[_Value], str], *, reads_text: bool
) -> MemberSubject:
    """``member`` read at the end of ``chain``, as the operation demands it —
    its extraction when it reads text, else its compared value — so absence at
    any hop reads as SQL null."""
    reached: list[MemberSubject] = []

    def value(inner: PredicateScope) -> str:
        subject = _subject(member, inner)
        reached.append(subject)
        return subject.extraction if reads_text else subject.compared

    expression = chain(value)
    first = reached[0]
    return MemberSubject(
        expression,
        expression,
        first.type,
        document_resident=first.document_resident,
        text_compared=first.text_compared,
    )


def _subject(member: ResolvedPredicateMember, scope: PredicateScope) -> MemberSubject:
    """``member`` as read from ``scope``'s current object.

    An Attribute is read through its Member Placement. A Value Object leaf is a
    document extraction: from the Entity's document through single occurrences,
    or from the element a quantifier binds, relative to its occurrence.
    """
    if isinstance(scope, ScalarElementScope):  # pragma: no cover - validated scopes
        raise SqlGenError(f"{member.identity} is not read from a scalar element")
    if isinstance(member, AttributeMetadata):
        if isinstance(scope, ValueObjectElementScope):
            raise SqlGenError(f"{member.identity} is not read from a Value Object element")
        return scope.subject_for(member)
    if isinstance(scope, EntityRowScope):
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


def _render_membership(
    tag: MembershipOp,
    values: tuple[ManagedValue, ...] | DeferredKeySet,
    subject: MemberSubject,
    scope: PredicateScope,
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
    value: object, subject: MemberSubject, scope: PredicateScope, *, framework: bool = False
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


def render_perspective(perspective: TemporalPerspective, scope: EntityRowScope) -> list[str]:
    """The comparisons restricting ``scope``'s current object to ``perspective``,
    in canonical axis rank, each pushing its binds as its text lands.

    Latest fixes the axis end to the open bound; an instant lies within the
    axis's half-open interval, its start compared before its end.
    """
    terms: list[str] = []
    for axis_perspective in perspective.ranked_perspectives():
        match axis_perspective:
            case LatestPerspective(axis=axis):
                terms.append(_endpoint(axis.end_attribute, "eq", INFINITY, scope, framework=True))
            case AtPerspective(axis=axis, instant=instant):
                terms.append(_endpoint(axis.start_attribute, "lessThanEquals", instant, scope))
                terms.append(_endpoint(axis.end_attribute, "greaterThan", instant, scope))
    return terms


def _endpoint(
    endpoint: AttributeIdentity,
    op: ComparisonOp,
    value: object,
    scope: EntityRowScope,
    *,
    framework: bool = False,
) -> str:
    attribute = _entity_view(scope.facet, endpoint.entity).applicable_attribute(endpoint.name)
    if attribute is None:  # pragma: no cover - an accepted axis names declared Attributes
        raise SqlGenError(f"{endpoint}: an As-Of Axis endpoint is undeclared")
    subject = scope.subject_for(attribute)
    _bind_operand(value, subject, scope, framework=framework)
    return f"{subject.compared} {_COMPARATORS[op]} ?"


def _render_like(
    kind: StringOp,
    value: str,
    case_insensitive: bool,
    subject_sql: str,
    scope: PredicateScope,
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
# pattern, and `_render_like` routes them away before any affix rendering — so the
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
# Planned navigation                                                           #
# --------------------------------------------------------------------------- #


def _continue(
    continuation: _Continuation,
    scope: PredicateScope,
    emit: _Emit,
    absent: str | None,
    default: str | None,
    *,
    reach: tuple[tuple[_SharedSourceRef, _SharedSourcePlan], ...] = (),
) -> str:
    """An occurrence evaluated through ``continuation`` from ``scope``.

    Past no hop it is evaluated at ``scope`` itself. Otherwise each to-one hop
    is one correlated scalar subquery over every planned candidate, so it
    asserts its own cardinality where it is evaluated: no candidate is SQL
    null — or ``default`` — and several fail. Hops nest rather than join, so an
    absent later target never hides an earlier hop's candidates, and a subquery
    a database runs once per row never plans a join of its own. Where the
    continuation stops before a target with no candidate, the occurrence
    answers ``absent`` there. ``reach`` confines the first hop's candidates to
    the shared sources the row joined (:func:`_confined`).
    """
    hops = continuation.hops
    if not hops:
        terminal = continuation.terminals[0]
        if isinstance(terminal, _NoCandidate):
            return _absence(absent)
        return emit(scope, terminal)
    return _hop_chain(
        hops, continuation.terminals, _entity_row(scope), emit, absent, default, reach
    )


def _absence(absent: str | None) -> str:
    if absent is None:  # pragma: no cover - an operation answers before the empty target
        raise SqlGenError("a field is read through a relationship with no candidate")
    return absent


def _hop_chain(
    hops: tuple[_PlannedHop, ...],
    terminals: tuple[_Terminal, ...],
    scope: EntityRowScope,
    emit: _Emit,
    absent: str | None,
    default: str | None,
    reach: tuple[tuple[_SharedSourceRef, _SharedSourcePlan], ...],
) -> str:
    first, rest = hops[0], hops[1:]
    if rest:
        return _scalar_hop(
            first,
            scope,
            lambda reached, _index: _hop_chain(rest, terminals, reached, emit, absent, default, ()),
            default,
            reach,
        )

    def terminal(reached: EntityRowScope, index: int) -> str:
        planned = terminals[index]
        if isinstance(planned, _NoCandidate):
            return _absence(absent)
        return emit(reached, planned)

    return _scalar_hop(first, scope, terminal, default, reach)


def _scalar_hop(
    hop: _PlannedHop,
    scope: EntityRowScope,
    inner: Callable[[EntityRowScope, int], str],
    default: str | None,
    reach: tuple[tuple[_SharedSourceRef, _SharedSourcePlan], ...],
) -> str:
    """One correlated scalar subquery selecting ``inner`` from each candidate
    ``hop`` plans; a table-per-concrete-subtype target contributes every
    declared branch with `union all`."""
    branches: list[str] = []
    for index, branch in enumerate(hop.candidates.branches):
        # The branch's value precedes its own table in the text, so every alias the
        # value declares is allocated first and this branch's alias after it,
        # keeping aliases in source order (m-sql rule 1); a placeholder stands in
        # for the alias until then.
        token = _hop_token()
        rendered, branch_scope = _rendered_candidate(branch, scope, alias=token)
        value = inner(branch_scope, index)
        alias = scope.next_alias()
        where = _candidate_where(hop.relationship, branch_scope, rendered, None, reach)
        selected = f"select {value} from {rendered.table} {token} where {where}"
        branches.append(selected.replace(token, alias))
    subquery = f"({' union all '.join(branches)})"
    return subquery if default is None else f"coalesce({subquery}, {default})"


def _hop_token() -> str:
    return f"__hop{next(_HOP_TOKENS)}__"


def _confined(
    lexical: _LexicalScopePlan,
    prefix: _SharedSourceRef,
    continuation: _Continuation,
    scope: PredicateScope,
    emit: _Emit,
    absent: str | None,
    default: str | None,
) -> str:
    """An occurrence evaluated past its shared ``prefix`` through its own hops,
    the first hop's candidates confined to the prefix the row joined."""
    return _continue(
        continuation,
        _target(scope, prefix),
        emit,
        absent,
        default,
        reach=_reach(lexical, prefix),
    )


def _reach(
    lexical: _LexicalScopePlan, prefix: _SharedSourceRef
) -> tuple[tuple[_SharedSourceRef, _SharedSourcePlan], ...]:
    """The shared sources ``prefix`` is reached through, in join order."""
    chain: list[tuple[_SharedSourceRef, _SharedSourcePlan]] = []
    ref: _SharedSourceRef | None = prefix
    while ref is not None:
        source = lexical.sources[ref.index]
        chain.append((ref, source))
        ref = source.parent
    chain.reverse()
    return tuple(chain)


def _rendered_candidate(
    branch: _RelationshipCandidateBranch,
    scope: EntityRowScope,
    *,
    alias: str | None = None,
) -> tuple[_RenderedRelationshipCandidate, EntityRowScope]:
    """``branch`` rendered against ``scope``, with the row its target resolves
    under."""
    rendered = _render_relationship_candidate(branch, scope, alias)
    return rendered, scope.child(rendered.entity, rendered.alias)


def _candidate_where(
    relationship: ResolvedRelationship,
    scope: EntityRowScope,
    rendered: _RenderedRelationshipCandidate,
    interior: str | None,
    reach: tuple[tuple[_SharedSourceRef, _SharedSourcePlan], ...] = (),
) -> str:
    """The correlated `where` of one candidate branch: correlation, then the
    interior (if any), then the hop's temporal visibility, then its family
    guard — the guard's binds pushed last because its text comes last — then
    the join terms of each ``reach`` source in join order."""
    terms = [rendered.correlation_sql]
    if interior:
        terms.append(interior)
    terms.extend(render_perspective(_temporal_visibility(relationship), scope))
    if rendered.family_guard_sql is not None:
        terms.append(rendered.family_guard_sql)
    scope.ctx.bind_framework_all(rendered.family_guard_binds)
    for ref, source in reach:
        binding = scope.ctx.source_binding(ref)
        target = binding.target
        rejoined = _render_relationship_candidate(source.candidate, binding.origin, target.alias)
        terms.append(_join_terms(source.relationship, target, rejoined))
    return " and ".join(terms)


def _join_terms(
    relationship: ResolvedRelationship,
    target: EntityRowScope,
    rendered: _RenderedRelationshipCandidate,
) -> str:
    """A joined target's `on`: its correlation, its temporal visibility, then
    its family guard, each pushing its binds as its text lands."""
    terms = [rendered.correlation_sql]
    terms.extend(render_perspective(_temporal_visibility(relationship), target))
    if rendered.family_guard_sql is not None:
        terms.append(rendered.family_guard_sql)
    target.ctx.bind_framework_all(rendered.family_guard_binds)
    return " and ".join(terms)


def _existential(fragments: Sequence[str], *, negate: bool) -> str:
    """Branch-local `exists` fragments as one family-wide answer: a candidate in
    any branch answers it, and its negation is the whole answer negated. With
    no candidate at all nothing exists."""
    if not fragments:
        return "1 = 1" if negate else "1 = 0"
    answer = fragments[0] if len(fragments) == 1 else f"({' or '.join(fragments)})"
    return f"not {answer}" if negate else answer


def _existence(
    plan: _StatementPlan,
    relationship: ResolvedRelationship,
    existence: _Terminal,
    scope: EntityRowScope,
    *,
    negate: bool,
    counterexample: bool = False,
) -> str:
    """One correlated `exists` per planned candidate of ``relationship``, each
    taking its alias as it opens, so a later branch's alias follows everything
    the preceding one allocated."""
    if not isinstance(existence, _CandidateExistence):  # pragma: no cover - planned evaluations
        raise SqlGenError("a relationship is evaluated without planned candidates")
    fragments = [
        _candidate_exists(plan, relationship, candidate, scope, counterexample=counterexample)
        for candidate in existence.candidates
    ]
    return _existential(fragments, negate=negate)


def _candidate_exists(
    plan: _StatementPlan,
    relationship: ResolvedRelationship,
    candidate: _CandidateOperand,
    scope: EntityRowScope,
    *,
    counterexample: bool,
) -> str:
    """One candidate branch's `exists`: its complete operand — or, for a
    universal, its counterexample — beside the candidate test, the operand's
    shared sources joined to the candidate as its own lexical row."""
    rendered, branch_scope = _rendered_candidate(candidate.branch, scope)
    source = f"{rendered.table} {rendered.alias}"
    interior: str | None = None
    operand_scope = candidate.operand_scope
    if operand_scope is not None:
        joins = render_shared_sources(plan, operand_scope, branch_scope)
        source = f"{source} {joins}" if joins else source
        operand = plan.lexical_scopes[operand_scope]
        interior = (
            _counterexample(operand.predicate, plan, operand, (), branch_scope)
            if counterexample
            else _conjunct(operand.predicate, plan, operand, (), branch_scope)
        )
    where_sql = _candidate_where(relationship, branch_scope, rendered, interior)
    return f"exists (select 1 from {source} where {where_sql})"


def _counterexample(
    where: ResolvedPredicate,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    """An element the complete predicate ``where`` does not make true."""
    return f"not ({_term(where, plan, lexical, path, scope)}) is true"


# --------------------------------------------------------------------------- #
# Quantifiers, presences, and narrowings                                       #
# --------------------------------------------------------------------------- #


def _render_quantifier(
    quantifier: ResolvedQuantifier,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    """A quantifier at its placement: read from its owner-result cell,
    evaluated at its shared owner's joined row, continued through the confined
    hops past a shared prefix, or evaluated through its own hops. A missing
    owner holds no element: owner results and hops default to the empty
    collection's answer, and a missing joined owner correlates no element."""
    default = "false" if quantifier.kind == "any" else "true"
    placement = _placement(lexical, path)
    if isinstance(placement, _OwnerResultEvaluation):
        binding = scope.ctx.owner_results_binding(placement.results)
        return f"coalesce({binding.alias}.{binding.columns[placement.cell]}, {default})"

    def at(reached: PredicateScope, terminal: _Terminal) -> str:
        return _quantify(quantifier, terminal, plan, lexical, path, reached)

    match placement:
        case _SharedRowEvaluation(source=source, terminal=terminal):
            return at(_target(scope, source), terminal)
        case _ConfinedScalarEvaluation(prefix=prefix, continuation=continuation):
            return _confined(lexical, prefix, continuation, scope, at, default, default)
        case _UnsharedEvaluation(continuation=continuation):
            return _continue(continuation, scope, at, default, default)


def _quantify(
    quantifier: ResolvedQuantifier,
    terminal: _Terminal,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    """A quantifier at the object of ``scope`` holding its collection.

    ``any`` is a true-matching existence, ``none`` its complement, and ``all``
    the absence of a counterexample — an element for which the COMPLETE
    ``where`` is not true, so a false or unknown element fails it. Each binds
    its own element alias, so separate quantifiers never share one.
    """
    collection = quantifier.collection
    if isinstance(collection, ResolvedRelationship):
        return _existence(
            plan,
            collection,
            terminal,
            _entity_row(scope),
            negate=quantifier.kind != "any",
            counterexample=quantifier.kind == "all",
        )
    if isinstance(collection, ScalarCollection):
        guard = _scalar_array_guard(collection.member, scope)
        element: PredicateScope = ScalarElementScope(
            ctx=scope.ctx, member=collection.member, alias=scope.ctx.next_alias()
        )
    else:
        guard = _occurrence_array_guard(collection, scope)
        element = ValueObjectElementScope(
            ctx=scope.ctx, container=collection, alias=scope.ctx.next_alias()
        )
    inner = f"select 1 from jsonb_array_elements({guard}) {element.alias}"
    where = quantifier.where
    body = (*path, 0)
    if quantifier.kind == "all":
        assert where is not None
        return f"not exists ({inner} where {_counterexample(where, plan, lexical, body, element)})"
    if where is not None:
        interior = _render(where, plan, lexical, body, element)
        if interior:
            inner = f"{inner} where {interior}"
    keyword = "not exists" if quantifier.kind == "none" else "exists"
    return f"{keyword} ({inner})"


def _scalar_array_guard(member: ResolvedPredicateMember, scope: PredicateScope) -> str:
    """The guarded array a scalar collection's elements are unnested from."""
    if isinstance(scope, ScalarElementScope):  # pragma: no cover - validated scopes
        raise SqlGenError("a scalar element holds no collection")
    if isinstance(member, AttributeMetadata):
        if not isinstance(scope, EntityRowScope):  # pragma: no cover - validated scopes
            raise SqlGenError(f"{member.identity} is not read from a Value Object element")
        placement = scope.layout.placement(member.identity)
        if isinstance(placement, DocumentPath):
            document, segments = scope.own_column(placement.slot.column.name), placement.path
        else:
            document, segments = scope.own_column(scope.slot_column(member.identity)), ()
    elif isinstance(scope, EntityRowScope):
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


def _occurrence_array_guard(occurrence: OccurrenceMetadata, scope: PredicateScope) -> str:
    """The guarded array a ``many`` Value Object's elements are unnested from."""
    document, segments = _occurrence_carrier(occurrence, scope)
    guard, binds = scope.dialect.array_guard(document, segments)
    scope.ctx.bind_framework_all(binds)
    return guard


def _occurrence_carrier(
    occurrence: OccurrenceMetadata, scope: PredicateScope
) -> tuple[str, tuple[str, ...]]:
    """The rendered document carrying ``occurrence`` and the path reaching it."""
    identity = occurrence.identity
    if isinstance(scope, EntityRowScope):
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


def _render_presence(
    presence: ResolvedPresence,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    """Whether a single object is present, two-valued: an absent target at any
    preceding hop reads as absent. A matching operand is evaluated whole in
    each candidate's own row, so only a candidate making it true matches; a
    presence whose target is itself shared reads that target's join."""

    def present(reached: PredicateScope, terminal: _Terminal) -> str:
        return _present(presence, terminal, plan, reached, negate=False)

    match _placement(lexical, path):
        case _SharedRowEvaluation(source=source, terminal=_JoinedTargetMatch() as joined):
            return _joined_presence(
                plan, joined.operand_scope, _target(scope, source), negated=presence.negated
            )
        case _SharedRowEvaluation(source=source, terminal=terminal):
            return _present(
                presence, terminal, plan, _target(scope, source), negate=presence.negated
            )
        case _ConfinedScalarEvaluation(prefix=prefix, continuation=continuation):
            sql = _confined(lexical, prefix, continuation, scope, present, "false", "false")
        case _UnsharedEvaluation(continuation=continuation):
            if not continuation.hops and continuation.reaches_target:
                return _present(
                    presence, continuation.terminals[0], plan, scope, negate=presence.negated
                )
            sql = _continue(continuation, scope, present, "false", "false")
        case _OwnerResultEvaluation():  # pragma: no cover - owner results hold quantifiers
            raise SqlGenError("a presence reads no owner result")
    return f"not {sql}" if presence.negated else sql


def _present(
    presence: ResolvedPresence,
    terminal: _Terminal,
    plan: _StatementPlan,
    reached: PredicateScope,
    *,
    negate: bool,
) -> str:
    """``presence``'s test at the object it reaches."""
    target = presence.target
    if isinstance(target, ResolvedRelationship):
        return _existence(plan, target, terminal, _entity_row(reached), negate=negate)
    sql = _object_presence(target, reached)
    return f"not {sql}" if negate else sql


def _joined_presence(
    plan: _StatementPlan,
    operand_scope: _LexicalScopeId | None,
    target: EntityRowScope,
    *,
    negated: bool,
) -> str:
    """Presence, or a match, read from a shared target's joined row.

    The target is present exactly where a physical primary-key Column, which no
    row holds null, is non-null. A match tests its complete operand for truth
    only beneath that presence, so an absent target is false rather than the
    operand's unknown.
    """
    absent = _absent(target)
    if operand_scope is None:
        return absent if negated else f"not {absent}"
    match = (
        f"case when {absent} then false else ({_operand_term(plan, operand_scope, target)}) "
        "is true end"
    )
    return f"not {match}" if negated else match


def _absent(target: EntityRowScope) -> str:
    """Whether a joined target is missing: its first physical primary-key
    Column, which no row holds null, reads null."""
    key = target.layout.physical_primary_key
    if not key:  # pragma: no cover - a joined target is a keyed table row
        raise SqlGenError(f"{target.layout.table.name!r} has no physical primary key")
    return f"{target.own_column(key[0].column.name)} is null"


def _object_presence(occurrence: OccurrenceMetadata, scope: PredicateScope) -> str:
    document, segments = _occurrence_carrier(occurrence, scope)
    sql, binds = scope.dialect.object_presence(document, segments)
    scope.ctx.bind_framework_all(binds)
    return sql


def _render_narrow(
    narrow: ResolvedNarrow,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: PredicateScope,
) -> str:
    """A narrowing of the current Entity, or of a reached target: at a shared
    target's joined row where one is planned, else as its own candidate's
    result in the target's correlated scalar subquery, which keeps every
    declared candidate under its cardinality assertion."""
    placement = _placement(lexical, path)
    if isinstance(narrow.target, CurrentObject):
        return _branch_narrow(narrow, placement, plan, lexical, path, _entity_row(scope))
    if isinstance(placement, _SharedRowEvaluation):
        return _joined_narrow(narrow, placement.terminal, plan, _target(scope, placement.source))

    def chain(emit: _Emit, default: str) -> str:
        match placement:
            case _ConfinedScalarEvaluation(prefix=prefix, continuation=continuation):
                return _confined(lexical, prefix, continuation, scope, emit, default, default)
            case _UnsharedEvaluation(continuation=continuation):
                return _continue(continuation, scope, emit, default, default)
            case _:  # pragma: no cover - a reached narrowing holds no owner result
                raise SqlGenError("a narrowing reads no owner result")

    if narrow.operand is None:
        return chain(
            lambda candidate, terminal: _selected(
                _target_selection(terminal).selection, _entity_row(candidate)
            ),
            "false",
        )
    dialect = scope.dialect
    envelope = chain(
        lambda candidate, terminal: dialect.boolean_envelope(
            _selected_operand(_target_selection(terminal), plan, _entity_row(candidate))
        ),
        dialect.absent_envelope(),
    )
    return dialect.envelope_value(envelope)


def _target_selection(terminal: _Terminal) -> _TargetSelection:
    if not isinstance(terminal, _TargetSelection):  # pragma: no cover - planned narrowings
        raise SqlGenError("a narrowed target is evaluated without a planned selection")
    return terminal


def _joined_narrow(
    narrow: ResolvedNarrow, terminal: _Terminal, plan: _StatementPlan, target: EntityRowScope
) -> str:
    """A narrowing over a shared target's joined row: false where the target is
    missing or outside the selection, else its operand's own truth, unknown
    included."""
    selection = _target_selection(terminal)
    guard = f"not {_absent(target)}"
    selected = _selected(selection.selection, target)
    if selected != "true":
        guard = f"{guard} and {selected}"
    if selection.operand_scope is None:
        return f"({guard})"
    return (
        f"case when {guard} then {_operand_term(plan, selection.operand_scope, target)} "
        "else false end"
    )


def _selected(selection: _SubtypeSelection, candidate: EntityRowScope) -> str:
    """Whether ``candidate`` belongs to the narrowing's selection: its tag
    guard in a hierarchy table, its branch's own answer in a concrete table."""
    if isinstance(selection, _TagPredicate):
        tag_sql, tag_binds = _tph_tag_guard(candidate, candidate.facet, selection)
        candidate.ctx.bind_framework_all(tag_binds)
        return tag_sql
    return "true" if selection else "false"


def _selected_operand(
    selection: _TargetSelection, plan: _StatementPlan, candidate: EntityRowScope
) -> str:
    """The narrowing's complete result at one candidate: the operand where the
    candidate is selected, false where it is not."""
    if selection.selection is False or selection.operand_scope is None:
        return "false"
    if selection.selection is True:
        return _operand_term(plan, selection.operand_scope, candidate)
    selected = _selected(selection.selection, candidate)
    operand = _operand_term(plan, selection.operand_scope, candidate)
    return f"case when {selected} then {operand} else false end"


def _branch_narrow(
    narrow: ResolvedNarrow,
    placement: _PredicatePlacement,
    plan: _StatementPlan,
    lexical: _LexicalScopePlan,
    path: _PredicatePath,
    scope: EntityRowScope,
) -> str:
    """A `narrow` of the current Entity — a **grouped branch predicate** (m-sql
    "Grouped branch predicates"): the branch's own operand composes with its
    own tag guard via `and`, and the composition is wrapped in parens whenever
    there is a branch predicate to disambiguate against a sibling branch joined
    by `or` (`m-inheritance-015`). In a concrete table's branch the operand
    stands in for the narrow as one term.
    """
    terminal = (
        placement.continuation.terminals[0] if isinstance(placement, _UnsharedEvaluation) else None
    )
    if not isinstance(terminal, _BranchSelection):  # pragma: no cover - planned narrowings
        raise SqlGenError("a narrowing of the row is rendered without a planned selection")
    selection = terminal.selection
    operand = narrow.operand
    body = (*path, 0)
    if selection is False:
        return "1 = 0"
    if selection is True:
        return "1 = 1" if operand is None else _whole(operand, plan, lexical, body, scope)
    # Branch predicate first, THEN the guard's binds — the same explicit ordering
    # the top-level read states, for the same reason.
    branch_sql = "" if operand is None else _conjunct(operand, plan, lexical, body, scope)
    tag_sql, tag_binds = _tph_tag_guard(scope, scope.facet, selection)
    scope.ctx.bind_framework_all(tag_binds)
    if not branch_sql:
        return tag_sql
    return f"({branch_sql} and {tag_sql})"


def _resolved_vo_path(
    leaf: ValueObjectAttributeMetadata, scope: EntityRowScope
) -> tuple[ValueObjectMetadata, tuple[str, ...]]:
    identity = leaf.identity.value_object
    vo = _entity_view(scope.facet, identity.entity).applicable_value_object(identity.path[0])
    if vo is None:
        raise SqlGenError(f"resolved Value Object {identity} is absent from the active position")
    return vo, (*identity.path[1:], leaf.identity.name)


def _entity_row(scope: PredicateScope) -> EntityRowScope:
    if not isinstance(scope, EntityRowScope):  # pragma: no cover - a hop starts at an Entity
        raise SqlGenError("a relationship is reached only from an Entity position")
    return scope


def _target(scope: PredicateScope, source: _SharedSourceRef) -> EntityRowScope:
    """The joined target row ``source`` rendered as."""
    return scope.ctx.source_binding(source).target


# --------------------------------------------------------------------------- #
# Shared relationship sources                                                  #
# --------------------------------------------------------------------------- #


def render_shared_sources(
    statement_plan: _StatementPlan, scope_id: _LexicalScopeId, scope: EntityRowScope
) -> str:
    """The joins of lexical plan ``scope_id``'s shared sources at ``scope``, in
    plan order, then its owner results.

    Each source takes the next alias and pushes its `on` binds as it renders,
    so a join's aliases and binds precede the predicate beside it: its
    correlation against the source reaching it, its temporal visibility, then
    its family guard. A left join keeps every row of the scope and supplies null
    where the target is missing.
    """
    lexical = statement_plan.lexical_scopes[scope_id]
    if not lexical.sources and not lexical.owner_results:
        return ""
    ctx = scope.ctx
    ctx.select_scope_plan(statement_plan, scope_id)
    joins: list[str] = []
    for index, source in enumerate(lexical.sources):
        parent = scope if source.parent is None else ctx.source_binding(source.parent).target
        rendered, target = _rendered_candidate(source.candidate, parent)
        ctx.record_source_binding(_SharedSourceRef(scope_id, index), target=target, origin=parent)
        terms = _join_terms(source.relationship, target, rendered)
        joins.append(f"left join {rendered.table} {rendered.alias} on {terms}")
    joins.extend(
        _owner_results(statement_plan, _OwnerResultsRef(scope_id, index), results, scope)
        for index, results in enumerate(lexical.owner_results)
    )
    return " ".join(joins)


def _owner_results(
    plan: _StatementPlan,
    ref: _OwnerResultsRef,
    results: _OwnerResultsPlan,
    scope: EntityRowScope,
) -> str:
    """One owner's results: a relation reading the owner's Table again, one
    row per physical row, projecting every physical primary-key Column and
    each quantifier cell evaluated over that row, left joined to the owner's
    join on the complete key. A missing owner then reads no result.

    Each cell is rendered from its own lexical plan at its own owner row, the
    relation's table alias taken after the aliases its select list declares
    (m-sql rule 1), and is evaluated once per row the relation reads; the owner
    join's own terms need not repeat, because a row's collection is that row's
    alone.
    """
    ctx = scope.ctx
    owner = ctx.source_binding(results.owner).target
    token = _hop_token()
    row = EntityRowScope(ctx=ctx, entity=owner.entity, layout=owner.layout, alias=token)
    keys = [slot.column.name for slot in owner.layout.physical_primary_key]
    names = _result_columns(keys, len(results.cells))
    cells = [row.own_column(key) for key in keys]
    for cell, name in zip(results.cells, names, strict=True):
        cell_plan = plan.lexical_scopes[cell.scope_id]
        cells.append(f"{_render(cell_plan.predicate, plan, cell_plan, (), row)} {name}")
    alias = owner.next_alias()
    relation = ctx.next_relation_alias()
    ctx.record_owner_results_binding(ref, alias=relation, columns=tuple(names))
    dialect = owner.dialect
    on = " and ".join(
        f"{dialect.qualified(relation, key)} = {owner.own_column(key)}" for key in keys
    )
    selected = f"select {', '.join(cells)} from {owner.layout.table.name} {token}"
    return f"left join ({selected}) {relation} on {on}".replace(token, alias)


def _result_columns(keys: Sequence[str], count: int) -> list[str]:
    """``count`` result Column names, `q0`, `q1`, …, skipping any a key
    Column of the same relation already spells."""
    taken = set(keys)
    names = (f"q{index}" for index in itertools.count())
    return list(itertools.islice((name for name in names if name not in taken), count))
