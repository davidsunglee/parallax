"""Reading the canonical export of a Typed query, for suites that pin query shape.

An Object Query and a Predicate expose no canonical inspection and no
serialization: the one way to see what they carry canonically is the first-party
export through :func:`~parallax.core.object_query.object_query_node`, which
judges and spells the query under a serving model exactly as a read of it would.
These helpers are that export plus the canonical serde; execution itself never
consumes it.
"""

from __future__ import annotations

import functools
from typing import Any, Literal

from parallax.core.entity import DomainModel
from parallax.core.entity._authored_resolver import object_query_node
from parallax.core.execution import prepare_model
from parallax.core.execution._preflight import preflight
from parallax.core.execution._publication import SelectedReadModel, read_projection
from parallax.core.execution._read_policy import interpreted
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, typed_read_query
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


def canonical_query(query: ObjectQuery[Any, Any], model: DomainModel) -> ObjectQueryNode:
    """``query``'s canonical ``m-object-query`` node under ``model``."""
    return object_query_node(query, model)


def predicate_node(query: ObjectQuery[Any, Any], model: DomainModel) -> PredicateNode:
    """``query``'s canonical predicate under ``model``."""
    return canonical_query(query, model).predicate


def canonical_document(query: ObjectQuery[Any, Any], model: DomainModel) -> dict[str, object]:
    """``query``'s canonical Object Query document under ``model``."""
    return serialize(canonical_query(query, model))


def predicate_document(query: ObjectQuery[Any, Any], model: DomainModel) -> dict[str, object]:
    """``query``'s canonical predicate clause under ``model``, for a suite pinning
    selection shape."""
    return serialize_predicate(predicate_node(query, model))


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
