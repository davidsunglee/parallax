"""Reading an Object Query's canonical node, for suites that pin query shape.

An Object Query exposes no canonical inspection and no serialization: the one way
to see what it carries is the first-party
:func:`~parallax.core.object_query.object_query_node` seam. These two helpers are
that seam plus the canonical serde, so a suite asserting a query's shape reads it
the same way execution does.
"""

from __future__ import annotations

from typing import Any

from parallax.core.object_query import ObjectQueryNode, serialize
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.predicate import serialize as serialize_predicate

__all__ = ["canonical_document", "canonical_query", "predicate_document"]


def canonical_query(query: ObjectQuery[Any, Any]) -> ObjectQueryNode:
    """``query``'s canonical ``m-object-query`` node."""
    return object_query_node(query)


def canonical_document(query: ObjectQuery[Any, Any]) -> dict[str, object]:
    """``query``'s canonical Object Query document."""
    return serialize(canonical_query(query))


def predicate_document(query: ObjectQuery[Any, Any]) -> dict[str, object]:
    """``query``'s canonical predicate clause, for a suite pinning selection shape."""
    return serialize_predicate(canonical_query(query).predicate)
