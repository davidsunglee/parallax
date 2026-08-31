"""``parallax.core.continuation`` — the page node a streamed read advances by.

Pure, and shaped like its neighbour :mod:`parallax.core.deep_fetch`: an Entity,
a canonical Object Query, and a model in; a plan out; no I/O anywhere. It lives
beside deep fetch rather than inside a handle because the page statement is the
same cross-language contract the ``1 + L`` shape is — every target must lower
the same SQL for the same page — so the keyset algebra is stated once here
rather than re-derived per implementation.

The plan answers two nodes and one question about a root.
:meth:`ContinuationPlan.first` is the first page: the caller's own query under
the Continuation Order, capped at the page size. :meth:`ContinuationPlan.after`
is every later page: the same node with the caller's predicate conjoined with
the seek that skips everything already delivered. And
:meth:`ContinuationPlan.continues_from` is whether a root supplies the
coordinates that seek would bind — the question a delivery asks of every root it
publishes rather than only of the one a page happens to end on.

The Continuation Order itself is deliberately NOT readable off the plan. A
caller hands over the last root's whole member map and the plan selects its own
terms, so there is no way to assemble a cursor the plan would then disagree
with; where the order is observable is where it is graded, as the ``orderBy`` of
the node :meth:`ContinuationPlan.first` returns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from parallax.core.base import ManagedValue
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
    entity_by_name,
)
from parallax.core.object_query import OrderKey
from parallax.core.object_query._validated import (
    ValidatedObjectQuery,
    ValidatedOrderTerm,
    derive_page,
    resolved_order_term,
)
from parallax.core.predicate import (
    Group,
    NoneOp,
    Or,
)
from parallax.core.predicate._validated import (
    ValidatedPredicate,
)
from parallax.core.predicate._validated import (
    compose as _compose,
)
from parallax.core.predicate._validated import (
    conjunction as _validated_conjunction,
)
from parallax.core.predicate._validated import empty_predicate as _empty_predicate
from parallax.core.predicate._validated import (
    managed_comparison as _managed_comparison,
)
from parallax.core.predicate._validated import (
    null_check as _null_check,
)
from parallax.core.temporal_read import scans_validated_axis

__all__ = ["ContinuationError", "ContinuationPlan", "plan"]


class ContinuationError(ValueError):
    """A query no page node can be composed for."""


@dataclass(frozen=True, slots=True)
class _Term:
    """One Continuation Order term, resolved to everything a seek needs of it.

    ``key`` is the Sort Key exactly as the page node carries it — an authored one
    verbatim, absent direction and placement included, so a page orders by what
    the caller asked for and not by a respelling of it. The three resolved fields
    beside it are what the seek is composed from: the member the cursor
    coordinate is read under, the effective direction, and whether the ordering
    can put a null anywhere at all.
    """

    key: OrderKey
    identity: AttributeIdentity
    direction: Literal["asc", "desc"]
    nulls: Literal["first", "last"]
    nullable: bool
    member: AttributeMetadata
    resolved: ValidatedOrderTerm

    @property
    def attr(self) -> str:
        return self.key.attr


class ContinuationPlan:
    """One query's page nodes, in the Continuation Order it advances by.

    Holds none of a stream's state: it answers nodes off the query and terms
    :func:`plan` formed it from, while the cursor, the emitted count, and the
    exhaustion verdict all belong to the loop that consumes it. Nothing mutates
    it, so two pages of one plan are two values and the plan is the same
    afterwards.
    """

    __slots__ = ("_order", "_query", "_terms")

    def __init__(self, query: ValidatedObjectQuery, terms: tuple[_Term, ...]) -> None:
        self._query = query
        self._terms = terms
        self._order = tuple(term.key for term in terms)

    def first(self, *, limit: int) -> ValidatedObjectQuery:
        """The first page: the caller's query, ordered and capped at ``limit``."""
        return derive_page(
            self._query,
            seek=None,
            order_by=tuple(term.resolved for term in self._terms),
            limit=limit,
        )

    def after(
        self, last_root: Mapping[AttributeIdentity, object], *, limit: int
    ) -> ValidatedObjectQuery:
        """The page following the root whose members are ``last_root``.

        The mapping is the whole root, keyed by Attribute Identity; which of its
        members the cursor is made of is this plan's own answer, so no caller
        can assemble one this plan would disagree with.

        The seek is composed of top-level conjuncts of the caller's own
        predicate and never of terms nested inside it, because that is what a
        planner reaches an index range through: an ordinary AND-qual over the
        leading ordering column. The caller's terms bind first, so bind order
        stays caller-first exactly as an injected as-of term leaves it.
        """
        seek_terms = self._seek(last_root)
        seek = seek_terms[0] if len(seek_terms) == 1 else _validated_conjunction(*seek_terms)
        return derive_page(
            self._query,
            seek=seek,
            order_by=tuple(term.resolved for term in self._terms),
            limit=limit,
        )

    def continues_from(self, root: Mapping[AttributeIdentity, object]) -> bool:
        """Whether ``root`` carries a coordinate for every term the seek binds.

        Only decoded values are bindable, so a root missing one of the plan's own
        members can begin no later page. The question is asked of every published
        root rather than only of the one a page ends on, which is what keeps the
        page size from deciding whether a stored row is survivable.
        """
        return all(term.identity in root for term in self._terms)

    def _seek(
        self, last_root: Mapping[AttributeIdentity, object]
    ) -> tuple[ValidatedPredicate, ...]:
        """The conjuncts admitting exactly the roots after ``last_root``.

        One term needs one strict comparison, which is already the top-level
        AND-qual a hoist exists to supply. Several need the lexicographic
        remainder — one disjunct per tie depth — and, ahead of it, the redundant
        non-strict comparison on the leading term that gives a planner a leading
        range to seek: the remainder alone offers nothing to push down, so it
        plans as a scan from the head of the index or as a disjunction that
        discards index order under the page's own ``order by`` and ``limit``.
        """
        coordinates = tuple(self._coordinate(term, last_root) for term in self._terms)
        lead = self._terms[0]
        if len(self._terms) == 1:
            return (_strictly_after(lead, coordinates[0]),)
        remainder = _remainder(self._terms, coordinates)
        if lead.nullable:
            return (remainder,)
        return (_hoist(lead, coordinates[0]), remainder)

    def _coordinate(
        self, term: _Term, last_root: Mapping[AttributeIdentity, object]
    ) -> ManagedValue | None:
        """``term``'s managed coordinate from the last delivered root.

        Continuation predicate construction adopts the value the managed root
        already carries. Predicate lowering owns its eventual bind carrier and
        canonical Wire observation; this seam neither renders nor re-decodes it.

        A member the root does not carry — one whose stored value no conforming
        member could hold — leaves nothing bindable to continue from, so it is
        refused by name rather than paged past.
        """
        if term.identity not in last_root:
            raise ContinuationError(
                f"{term.identity.name}: the Continuation Order names a member the delivered "
                "root does not carry"
            )
        value = last_root[term.identity]
        return cast("ManagedValue | None", value)


def plan(query: ValidatedObjectQuery, model: Metamodel) -> ContinuationPlan:
    """``query``'s page plan against ``model``, in its Continuation Order.

    The Continuation Order is the query's authored Sort Keys in the precedence it
    declares, followed by ``entity``'s family-declared primary key ascending and
    then — for a milestone-set (``history`` / ``asOfRange``) read — the milestone
    edge ascending, each appended only where no Sort Key already named it.

    The primary key alone is total for a single-instant read, where one key
    stands behind one result root. A milestone-set read returns one root per
    milestone, so several roots share one key and the key is no longer total by
    itself; what separates them is the milestone each stands at, which is the
    family's own As-Of Axis starts in canonical axis rank — Valid Time before
    Transaction Time. Every one of those is an ordinary Attribute, so the edge
    lowers and seeks exactly as an authored Sort Key does.
    """
    entity = query.root
    root = _family_root(entity, model)
    terms = [_term_from_resolved(term) for term in query.order_by]
    for identity in (_family_key(root), *_milestone_edge(root, query)):
        if all(term.identity != identity for term in terms):
            terms.append(_term(OrderKey(attr=_reference(identity), direction="asc"), model))
    return ContinuationPlan(query, tuple(terms))


def _milestone_edge(
    root: EntityMetadata, query: ValidatedObjectQuery
) -> tuple[AttributeIdentity, ...]:
    """The Attributes a milestone-set read's roots stand at, in canonical axis rank.

    Empty for a read that scans no axis, whose roots are one per primary key and
    therefore already totally ordered by it. A scan puts every milestone of a key
    in the result at once, and each milestone's own coordinate is its As-Of Axis
    start (`m-temporal-read`'s edge) — the from-instant that lies inside its own
    half-open interval and so distinguishes it from every other milestone of the
    same key.
    """
    if not scans_validated_axis(query.temporal):
        return ()
    axes = sorted(root.declared_as_of_axes, key=lambda axis: axis.dimension.value)
    return tuple(axis.start_attribute for axis in axes)


def _remainder(
    terms: tuple[_Term, ...], coordinates: tuple[ManagedValue | None, ...]
) -> ValidatedPredicate:
    """The lexicographic disjunction: one branch per tie depth.

    A depth whose term admits nothing after its own coordinate — a null under
    Nulls Last, which every remaining null ties with and no row follows —
    contributes no branch, because a branch that matches no row is one a reader
    has to reason past to see what the seek does.

    A branch that ties with something is grouped, because an ``and`` inside an
    ``or`` reads as a branch of it, and its own "strictly after" is grouped in
    turn where that is a disjunction — a nullable term under Nulls Last is
    strictly after its coordinate OR null, and ungrouped beside its ties the
    ``or`` would escape them and admit every null of that term whatever the terms
    above it hold. The leading branch is grouped neither way: it ties with
    nothing, so whatever it is composed of is already a disjunct of the whole.
    Where a single branch survives beside another term, it is never the leading
    one alone — every order carries the primary key, a non-nullable term whose
    branch drops under no coordinate — so the remainder handed back as one node is
    never an ungrouped disjunction.
    """
    branches: list[ValidatedPredicate] = []
    for depth, term in enumerate(terms):
        after = _strictly_after(term, coordinates[depth])
        if isinstance(after.authored, NoneOp):
            continue
        ties = tuple(_ties_with(terms[at], coordinates[at]) for at in range(depth))
        if not ties:
            branches.append(after)
            continue
        within = _group(after) if isinstance(after.authored, Or) else after
        conjunction = _validated_conjunction(*ties, within)
        branches.append(_group(conjunction))
    if len(branches) == 1:
        return branches[0]
    disjunction = Or(operands=tuple(branch.authored for branch in branches))
    return _group(_compose(disjunction, *branches))


def _hoist(term: _Term, coordinate: ManagedValue | None) -> ValidatedPredicate:
    """``term`` non-strictly past ``coordinate`` — the redundant leading range.

    Emitted only for a NON-NULLABLE leading term. With nulls placed after a
    non-null coordinate, "after" is two disjoint ranges of the index and no
    single comparison covers both, so there is nothing to hoist.
    """
    if coordinate is None:  # pragma: no cover - hoisting is limited to a non-nullable lead
        raise ContinuationError(f"{term.attr}: a non-nullable continuation coordinate is null")
    return _managed_comparison(
        op="greaterThanEquals" if term.direction == "asc" else "lessThanEquals",
        attr=term.attr,
        member=term.member,
        value=coordinate,
    )


def _strictly_after(term: _Term, coordinate: ManagedValue | None) -> ValidatedPredicate:
    """Everything ``term`` orders strictly after ``coordinate``.

    Measured in the term's OWN ordering: a descending term reverses the
    comparison, and a nullable term's Null Placement decides which side of the
    non-nulls its nulls fall on. A null coordinate ties with every other null, so
    what follows it is the non-nulls under Nulls First and nothing at all under
    Nulls Last.
    """
    if coordinate is None:
        if term.nulls == "first":
            return _null_check(op="isNotNull", attr=term.attr, member=term.member)
        return _empty_predicate()
    strict = _managed_comparison(
        op="greaterThan" if term.direction == "asc" else "lessThan",
        attr=term.attr,
        member=term.member,
        value=coordinate,
    )
    if term.nullable and term.nulls == "last":
        is_null = _null_check(op="isNull", attr=term.attr, member=term.member)
        return _compose(Or(operands=(strict.authored, is_null.authored)), strict, is_null)
    return strict


def _ties_with(term: _Term, coordinate: ManagedValue | None) -> ValidatedPredicate:
    if coordinate is None:
        return _null_check(op="isNull", attr=term.attr, member=term.member)
    return _managed_comparison(op="eq", attr=term.attr, member=term.member, value=coordinate)


def _group(predicate: ValidatedPredicate) -> ValidatedPredicate:
    return _compose(Group(operand=predicate.authored), predicate)


def _term(key: OrderKey, model: Metamodel) -> _Term:
    attribute = _attribute(key.attr, model)
    direction = key.direction or "asc"
    nulls = key.nulls or "last"
    return _Term(
        key=key,
        identity=attribute.identity,
        direction=direction,
        nulls=nulls,
        nullable=attribute.nullable,
        member=attribute,
        resolved=resolved_order_term(attribute, direction=direction, nulls=nulls),
    )


def _term_from_resolved(term: ValidatedOrderTerm) -> _Term:
    member = term.member
    key = OrderKey(
        attr=f"{member.identity.entity.canonical}.{member.identity.name}",
        direction=term.direction,
        nulls=term.nulls,
    )
    return _Term(
        key=key,
        identity=member.identity,
        direction=term.direction,
        nulls=term.nulls,
        nullable=member.nullable,
        member=member,
        resolved=term,
    )


def _attribute(reference: str, model: Metamodel) -> AttributeMetadata:
    """The Attribute a Sort Key's ``Entity.member`` reference addresses.

    Resolved through the addressed Entity's own position, so a Sort Key naming a
    family member through a subtype spelling answers the family root's Attribute
    — the same identity the primary-key comparison below is made against.
    """
    class_name, _, name = reference.rpartition(".")
    entity = entity_by_name(model, class_name)
    attribute = None if entity is None else _applicable(entity, name, model)
    if attribute is None:
        raise ContinuationError(f"{reference}: the model declares no such Attribute")
    return attribute


def _applicable(entity: EntityMetadata, name: str, model: Metamodel) -> AttributeMetadata | None:
    position = inheritance_view(model).entity(entity.identity)
    inherited = None if position is None else position.applicable_attribute(name)
    return inherited or entity.attribute(name)


def _reference(identity: AttributeIdentity) -> str:
    """``identity`` as the member reference a query clause names it by.

    A clause addresses a member by the reference spelling every validator and
    lowering site resolves — the addressed Entity's canonical name and the
    member's own — rather than by the Identity, which no serialized query
    carries.
    """
    return f"{identity.entity.canonical}.{identity.name}"


def _family_root(entity: EntityMetadata, model: Metamodel) -> EntityMetadata:
    """The Entity whose declaration carries ``entity``'s family-wide facts.

    The primary key and the As-Of Axes are both family-wide and root-owned
    (`m-inheritance`), so a subtype position resolves either through its family
    root rather than through its own locally empty declaration.
    """
    position = inheritance_view(model).entity(entity.identity)
    root = entity if position is None else model.entity(position.root)
    if root is None:  # pragma: no cover - a resolved position always names a declared root
        raise ContinuationError(f"{entity.identity.canonical}: the model declares no family root")
    return root


def _family_key(root: EntityMetadata) -> AttributeIdentity:
    """``root``'s primary-key Attribute.

    It is exactly one Attribute: `m-metamodel` refuses a composite key outright,
    which is what makes each Continuation Order's key term one bindable value
    rather than a tuple.
    """
    key = [
        attribute.identity
        for attribute in root.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
    if len(key) != 1:  # pragma: no cover - formation accepts exactly one primary-key Attribute
        raise ContinuationError(
            f"{root.identity.canonical}: the Entity declares no single primary-key Attribute"
        )
    return key[0]
