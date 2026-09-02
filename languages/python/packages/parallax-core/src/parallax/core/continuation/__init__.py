"""``parallax.core.continuation`` — the page node a streamed read advances by.

Pure, and shaped like its neighbour :mod:`parallax.core.deep_fetch`: an Entity,
a canonical Object Query, and a model in; a plan out; no I/O anywhere. It lives
beside deep fetch rather than inside a handle because the page statement is the
same cross-language contract the ``1 + L`` shape is — every target must lower
the same SQL for the same page — so the keyset algebra is stated once here
rather than re-derived per implementation.

The plan answers two nodes. :meth:`ContinuationPlan.first` is the first page:
the caller's own query under the Continuation Order, capped at the page size.
:meth:`ContinuationPlan.after` is every later page: the same node carrying the
seek that skips everything already delivered.

That seek is a VALUE rather than predicate nodes. Continuation owns which terms
are in the order and in what precedence; what "strictly after" expands into
cannot be settled here, because it depends on where the dialect placed a NULL in
the clause m-sql emitted. So this module hands over a
:class:`~parallax.core.object_query._validated.ValidatedSeek` — the order plus
one opaque coordinate — and m-sql lowers the branch tree.

The coordinate is the one the database itself evaluated for the last delivered
root, carried through here without being inspected. Nothing about a root's
decoded members reaches this module, which is what lets a delivery continue past
a root whose stored data contradicted the model.

The Continuation Order itself is deliberately NOT readable off the plan: where
it is observable is where it is graded, as the ``orderBy`` of the node
:meth:`ContinuationPlan.first` returns.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    ContinuationCoordinate,
    ContinuationTerm,
    Paging,
    ValidatedObjectQuery,
    ValidatedOrderTerm,
    ValidatedSeek,
    derive_page,
    resolved_order_term,
)
from parallax.core.temporal_read import scans_validated_axis

__all__ = ["ContinuationError", "ContinuationPlan", "plan"]


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
    resolved: ValidatedOrderTerm
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
        self, model: Metamodel, query: ValidatedObjectQuery, terms: tuple[_Term, ...]
    ) -> None:
        self._model = model
        self._query = query
        self._terms = terms

    def first(self, *, limit: int) -> ValidatedObjectQuery:
        """The first page: the caller's query, ordered and capped at ``limit``.

        It carries paging without a seek, which is what makes it capture the
        coordinates a later page will advance from while admitting every root
        the caller's own predicate does.
        """
        return self._page(Paging(), limit=limit)

    def after(self, coordinate: ContinuationCoordinate, *, limit: int) -> ValidatedObjectQuery:
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
        seek = ValidatedSeek(tuple(term.portable for term in self._terms), coordinate)
        return self._page(Paging(seek=seek), limit=limit)

    def _page(self, paging: Paging, *, limit: int) -> ValidatedObjectQuery:
        return derive_page(
            self._query,
            paging=paging,
            order_by=tuple(term.resolved for term in self._terms),
            limit=limit,
        )


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
    return ContinuationPlan(model, query, tuple(terms))


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


def _term(key: OrderKey, model: Metamodel) -> _Term:
    """One appended term from the generated Sort Key naming it.

    An appended key omits `direction` and `nulls` nowhere else, so the schema
    defaults are applied here rather than left for a reader to infer.
    """
    attribute = _attribute(key.attr, model)
    direction = key.direction or "asc"
    nulls = key.nulls or "last"
    return _term_from_resolved(resolved_order_term(attribute, direction=direction, nulls=nulls))


def _term_from_resolved(term: ValidatedOrderTerm) -> _Term:
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
