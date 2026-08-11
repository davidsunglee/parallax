"""Reading a Find Query's canonical lowering, for suites that pin query shape.

A Find Query exposes no canonical-operation inspection and no serialization: the
one way to see what it lowers to is the first-party
:func:`~parallax.core.entity._query.lower_find_query` seam. These two helpers are
that seam plus the canonical serde, so a suite asserting a query's shape reads it
the same way execution does.
"""

from __future__ import annotations

from typing import Any

from parallax.core.entity._query import FindQuery, lower_find_query
from parallax.core.predicate import PredicateNode, serialize

__all__ = ["lowered_document", "lowered_operation"]


def lowered_operation(query: FindQuery[Any, Any]) -> PredicateNode:
    """``query``'s canonical ``m-predicate`` operation."""
    return lower_find_query(query).operation


def lowered_document(query: FindQuery[Any, Any]) -> dict[str, object]:
    """``query``'s canonical operation document."""
    return serialize(lowered_operation(query))
