"""Reading the canonical export of a Typed query or predicate, for suites that
pin query shape.

An Object Query and a Predicate expose no canonical inspection and no
serialization: the one way to see what they carry canonically is the first-party
export through :func:`~parallax.core.object_query.object_query_node` and
:func:`~parallax.core.entity._expressions.canonical_predicate`. These helpers are
that export plus the canonical serde; execution itself never consumes it.
"""

from __future__ import annotations

import functools
from typing import Any, Literal

from parallax.core.entity import AllPredicate, DomainModel, Predicate
from parallax.core.entity._expressions import canonical_predicate
from parallax.core.execution import prepare_model
from parallax.core.execution._preflight import preflight
from parallax.core.execution._publication import SelectedReadModel, read_projection
from parallax.core.execution._read_policy import interpreted
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, object_query_node, typed_read_query
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.object_query.serde import serialize
from parallax.core.predicate import PredicateNode
from parallax.core.predicate import serialize as serialize_predicate

__all__ = [
    "canonical_document",
    "canonical_query",
    "predicate_document",
    "predicate_node",
    "typed_resolved",
]


def predicate_node(predicate: Predicate[Any] | AllPredicate[Any]) -> PredicateNode:
    """``predicate``'s canonical export."""
    return canonical_predicate(predicate.authored)


def canonical_query(query: ObjectQuery[Any, Any]) -> ObjectQueryNode:
    """``query``'s canonical ``m-object-query`` node."""
    return object_query_node(query)


def canonical_document(query: ObjectQuery[Any, Any]) -> dict[str, object]:
    """``query``'s canonical Object Query document."""
    return serialize(canonical_query(query))


def predicate_document(query: ObjectQuery[Any, Any]) -> dict[str, object]:
    """``query``'s canonical predicate clause, for a suite pinning selection shape."""
    return serialize_predicate(canonical_query(query).predicate)


@functools.cache
def _selected(model: DomainModel) -> SelectedReadModel:
    return read_projection(prepare_model(model, edition="query-probe"))


def typed_resolved(
    query: ObjectQuery[Any, Any],
    model: DomainModel,
    *,
    form: Literal["rows", "graph"] = "graph",
) -> ResolvedObjectQuery:
    """``query`` resolved through the Typed adapter against ``model``, exactly as a
    read resolves it once it has adopted that model."""
    selected = _selected(model)
    return preflight(
        interpreted(selected, typed_read_query(query)), model=selected.model.meta, form=form
    )
