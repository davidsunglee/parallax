"""``parallax.core.continuation`` — the page node a streamed read advances by.

Pure, and shaped like its neighbour :mod:`parallax.core.deep_fetch`: an Entity,
a canonical Object Query, and a model in; a plan out; no I/O anywhere. It lives
beside deep fetch rather than inside a handle because the page statement is the
same cross-language contract the ``1 + L`` shape is — every target must lower
the same SQL for the same page — so the keyset algebra is stated once here
rather than re-derived per implementation.

The plan answers two nodes and nothing else. :meth:`ContinuationPlan.first` is
the first page: the caller's own query under the Continuation Order, capped at
the page size. :meth:`ContinuationPlan.after` is every later page: the same
node with the caller's predicate conjoined with the seek that skips everything
already delivered.

The Continuation Order itself is deliberately NOT readable off the plan. A
caller hands over the last root's whole member map and the plan selects its own
terms, so there is no way to assemble a cursor the plan would then disagree
with; where the order is observable is where it is graded, as the ``orderBy`` of
the node :meth:`ContinuationPlan.first` returns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityMetadata,
    Metamodel,
    PrimaryKey,
)
from parallax.core.object_query import ObjectQueryNode, OrderKey
from parallax.core.predicate import And, Comparison, Scalar
from parallax.core.temporal_read import conjunction_terms, scans_an_axis

__all__ = ["ContinuationError", "ContinuationPlan", "plan"]


class ContinuationError(ValueError):
    """A query no page node can be composed for."""


class ContinuationPlan:
    """One query's page nodes, in the Continuation Order it advances by.

    Holds none of a stream's state: it answers nodes off the query and key
    :func:`plan` formed it from, while the cursor, the emitted count, and the
    exhaustion verdict all belong to the loop that consumes it. Nothing mutates
    it, so two pages of one plan are two values and the plan is the same
    afterwards.
    """

    __slots__ = ("_key", "_order", "_query")

    def __init__(self, query: ObjectQueryNode, key: AttributeIdentity) -> None:
        self._query = query
        self._key = key
        self._order = (OrderKey(attr=_reference(key), direction="asc"),)

    def first(self, *, limit: int) -> ObjectQueryNode:
        """The first page: the caller's query, ordered and capped at ``limit``."""
        return replace(self._query, order_by=self._order, limit=limit)

    def after(
        self, last_root: Mapping[AttributeIdentity, object], *, limit: int
    ) -> ObjectQueryNode:
        """The page following the root whose members are ``last_root``.

        The mapping is the whole root, keyed by Attribute Identity; which of its
        members the cursor is made of is this plan's own answer, so no caller
        can assemble one this plan would disagree with.

        The seek is a top-level conjunct of the caller's own predicate and never
        a term nested inside it, because that is what a planner reaches an index
        range through: an ordinary AND-qual over the leading ordering column.
        The caller's terms bind first, so bind order stays caller-first exactly
        as an injected as-of term leaves it.
        """
        seek = Comparison(
            op="greaterThan",
            attr=self._order[0].attr,
            value=self._cursor_value(last_root),
        )
        terms = (*conjunction_terms(self._query.predicate), seek)
        return replace(
            self._query,
            predicate=terms[0] if len(terms) == 1 else And(operands=terms),
            order_by=self._order,
            limit=limit,
        )

    def _cursor_value(self, last_root: Mapping[AttributeIdentity, object]) -> Scalar:
        """The Continuation Order's own value off the last delivered root.

        A primary-key member is one of `m-predicate`'s neutral scalar types even
        though a projection's values are typed as plain ``object``; the cast
        reflects that runtime invariant rather than widening the comparison
        node's own typed-literal contract.
        """
        if self._key not in last_root:
            raise ContinuationError(
                f"{self._key.name}: the Continuation Order names a member the delivered root "
                "does not carry"
            )
        return cast("Scalar", last_root[self._key])


def plan(entity: EntityMetadata, query: ObjectQueryNode, model: Metamodel) -> ContinuationPlan:
    """``query``'s page plan against ``model``, ordered by ``entity``'s family key.

    The Continuation Order is the family-declared primary key, ascending. That
    key is total, immutable, and non-nullable, so every page seeks against an
    index range and no write can move a root across a page boundary.

    A milestone-set (``history`` / ``asOfRange``) read is refused: one primary
    key stands behind several result roots there, so paging on the key alone
    would skip or duplicate at a page boundary. An authored ``orderBy`` is
    refused for the converse reason — the order a caller asked for is not the
    order this plan advances by, and delivering roots in a different one would
    answer a query nobody wrote.
    """
    if scans_an_axis(query):
        raise ContinuationError(
            f"{query.target.canonical}: a milestone-set read has no streamed page order yet"
        )
    if query.order_by:
        raise ContinuationError(
            f"{query.target.canonical}: a streamed read advances by primary key; an authored "
            "orderBy has no streamed page order yet"
        )
    return ContinuationPlan(query, _family_key(entity, model))


def _reference(identity: AttributeIdentity) -> str:
    """``identity`` as the member reference a query clause names it by.

    A clause addresses a member by the reference spelling every validator and
    lowering site resolves — the addressed Entity's canonical name and the
    member's own — rather than by the Identity, which no serialized query
    carries.
    """
    return f"{identity.entity.canonical}.{identity.name}"


def _family_key(entity: EntityMetadata, model: Metamodel) -> AttributeIdentity:
    """``entity``'s family-declared primary-key Attribute.

    The physical primary key is family-wide and root-owned (`m-inheritance`), so
    a subtype position resolves it through its family root rather than through
    its own locally empty declaration. It is exactly one Attribute: `m-metamodel`
    refuses a composite key outright, which is what makes a page cursor one
    bindable value rather than a lexicographic tuple.
    """
    position = inheritance_view(model).entity(entity.identity)
    root = entity if position is None else model.entity(position.root)
    if root is None:  # pragma: no cover - a resolved position always names a declared root
        raise ContinuationError(f"{entity.identity.canonical}: the model declares no family root")
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
