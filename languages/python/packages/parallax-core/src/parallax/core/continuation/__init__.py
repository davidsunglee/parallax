from __future__ import annotations

from dataclasses import dataclass, replace

from parallax.core.inheritance import InheritanceEntityView
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
)
from parallax.core.object_query._resolved import (
    ContinuationCoordinate,
    ContinuationTerm,
    Paging,
    ResolvedObjectQuery,
    ResolvedOrderTerm,
    ResolvedSeek,
    derive_page,
    resolved_order_term,
)
from parallax.core.temporal_read import ranked_axes, scans_resolved_axis
from parallax.core.temporal_read import view as temporal_view

__all__ = ["ContinuationError", "ContinuationPlan", "ordered", "plan"]


class ContinuationError(ValueError):
    """A query no page node can be composed for."""


@dataclass(frozen=True, slots=True)
class _Term:
    """One Continuation Order term, in both spellings one page needs of it.

    ``resolved`` is the ordering clause the page node carries; ``portable`` is
    the same term as the seek reads it. Both are derived here from one
    resolution of the member, so the clause a page orders by and the branch tree
    m-sql expands cannot disagree about a term's direction or Null Placement.
    """

    member: AttributeMetadata
    resolved: ResolvedOrderTerm
    portable: ContinuationTerm

    @property
    def identity(self) -> AttributeIdentity:
        return self.member.identity


class ContinuationPlan:
    """One query's page nodes, in the Continuation Order it advances by.

    Holds none of a stream's state: it answers nodes off the query and terms
    :func:`plan` formed it from, while the cursor, the emitted count, and the
    exhaustion verdict all belong to the loop that consumes it. Nothing mutates
    it, so two pages of one plan are two values and the plan is the same
    afterwards.
    """

    __slots__ = ("_model", "_query", "_terms")

    def __init__(
        self, model: Metamodel, query: ResolvedObjectQuery, terms: tuple[_Term, ...]
    ) -> None:
        self._model = model
        self._query = query
        self._terms = terms

    def first(self, *, limit: int) -> ResolvedObjectQuery:
        """The first page: the caller's query, ordered and capped at ``limit``.

        It carries paging without a seek, which is what makes it capture the
        coordinates a later page will advance from while admitting every root
        the caller's own predicate does.
        """
        return self._page(Paging(), limit=limit)

    def after(self, coordinate: ContinuationCoordinate, *, limit: int) -> ResolvedObjectQuery:
        """The page following the root that stood at ``coordinate``.

        The coordinate is the whole Continuation Order's worth of carriers the
        database evaluated for that root, positionally — never a selection a
        caller assembled, and never anything materialization decoded. It is
        carried into the node opaquely: this plan states which terms the seek
        is measured against and in what precedence, and m-sql expands that into
        the comparisons a page actually admits roots through.
        """
        if len(coordinate.carriers) != len(self._terms):
            raise ContinuationError(
                f"the Continuation Order has {len(self._terms)} term(s) and the coordinate "
                f"carries {len(coordinate.carriers)}"
            )
        seek = ResolvedSeek(tuple(term.portable for term in self._terms), coordinate)
        return self._page(Paging(seek=seek), limit=limit)

    def ordered(self) -> ResolvedObjectQuery:
        """The query in Continuation Order without paging capture or a cap."""
        return replace(self._query, order_by=tuple(term.resolved for term in self._terms))

    def _page(self, paging: Paging, *, limit: int) -> ResolvedObjectQuery:
        return derive_page(
            self._query,
            paging=paging,
            order_by=tuple(term.resolved for term in self._terms),
            limit=limit,
        )


def plan(query: ResolvedObjectQuery, model: Metamodel) -> ContinuationPlan:
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
    key = _family_view(entity, model).primary_key.identity
    terms = [_term_from_resolved(term) for term in query.order_by]
    for identity in (key, *_milestone_edge(entity, model, query)):
        if all(term.identity != identity for term in terms):
            terms.append(
                _term_from_resolved(
                    resolved_order_term(_attribute(identity, model), direction="asc", nulls="last")
                )
            )
    return ContinuationPlan(model, query, tuple(terms))


def ordered(query: ResolvedObjectQuery, model: Metamodel) -> ResolvedObjectQuery:
    """``query`` ordered by its Continuation Order without making it a page.

    Eager milestone-set delivery needs the same deterministic root sequence as a
    stream while retaining one ordinary, uncaptured database result.
    """
    return plan(query, model).ordered()


def _milestone_edge(
    entity: EntityMetadata, model: Metamodel, query: ResolvedObjectQuery
) -> tuple[AttributeIdentity, ...]:
    """The Attributes a milestone-set read's roots stand at, in canonical axis rank.

    Empty for a read that scans no axis, whose roots are one per primary key and
    therefore already totally ordered by it. A scan puts every milestone of a key
    in the result at once, and each milestone's own coordinate is its As-Of Axis
    start (`m-temporal-read`'s edge) — the from-instant that lies inside its own
    half-open interval and so distinguishes it from every other milestone of the
    same key.
    """
    if not scans_resolved_axis(query.temporal):
        return ()
    shape = temporal_view(model).shape(entity.identity)
    if shape is None:  # pragma: no cover - the Temporal Facet covers every accepted Entity
        raise ContinuationError(f"{entity.identity.canonical}: the model declares no such Entity")
    return tuple(axis.start_attribute for axis in ranked_axes(shape))


def _term_from_resolved(term: ResolvedOrderTerm) -> _Term:
    member = term.member
    return _Term(
        member=member,
        resolved=term,
        portable=ContinuationTerm(
            identity=member.identity,
            direction=term.direction,
            nulls=term.nulls,
            nullable=member.nullable,
        ),
    )


def _attribute(identity: AttributeIdentity, model: Metamodel) -> AttributeMetadata:
    """The Attribute an appended term orders by, resolved at its declaring
    Entity's own position."""
    entity = model.entity(identity.entity)
    attribute = None if entity is None else _applicable(entity, identity.name, model)
    if attribute is None:  # pragma: no cover - the term's identity names an accepted member
        raise ContinuationError(f"{identity}: the model declares no such Attribute")
    return attribute


def _applicable(entity: EntityMetadata, name: str, model: Metamodel) -> AttributeMetadata | None:
    position = inheritance_view(model).entity(entity.identity)
    inherited = None if position is None else position.applicable_attribute(name)
    return inherited or entity.attribute(name)


def _family_view(entity: EntityMetadata, model: Metamodel) -> InheritanceEntityView:
    position = inheritance_view(model).entity(entity.identity)
    if position is None:  # pragma: no cover - the Inheritance Facet covers every accepted Entity
        raise ContinuationError(f"{entity.identity.canonical}: the model declares no such Entity")
    return position
