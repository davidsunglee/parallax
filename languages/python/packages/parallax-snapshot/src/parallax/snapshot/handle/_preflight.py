from __future__ import annotations

from typing import Literal

from parallax.core.metamodel import Metamodel, entity_by_name
from parallax.core.metamodel._states import ambiguous_entity_spellings
from parallax.core.object_query import ObjectQueryNode, validate_object_query
from parallax.core.object_query._validated import ValidatedObjectQuery
from parallax.core.predicate import ModelRejectedError
from parallax.snapshot.handle._errors import QueryTargetError
from parallax.snapshot.handle._features import DeferredFeatureError, deferred_features

__all__ = ["fetches_relationships", "preflight"]


def preflight(
    query: ObjectQueryNode, *, model: Metamodel, form: Literal["rows", "graph"]
) -> ValidatedObjectQuery:
    """Resolve and validate ``query`` against ``model``, and do no I/O.

    Target resolution follows the reference-position rule every validator and
    lowering site resolves a spelling by, so "preflight accepted this target"
    implies "planning resolves it". Raises
    :class:`~parallax.snapshot.handle._errors.QueryTargetError` when ``model``
    declares no Entity for it,
    :class:`~parallax.core.predicate.ModelRejectedError` when a clause is not
    applicable from that resolved root, and
    :class:`~parallax.snapshot.handle._features.DeferredFeatureError` when the
    query is applicable but requires a Feature this implementation has not built
    yet. Performs no SQL generation, Database Port or connection work,
    transaction demarcation, or materialization.
    """
    root = entity_by_name(model, query.target.canonical)
    if root is None:
        shared = ambiguous_entity_spellings(model, query.target.canonical)
        if shared:
            raise ModelRejectedError(
                "reference-ambiguous-entity-name",
                f"{query.target.canonical!r}: the bare Entity spelling is shared by "
                f"{list(shared)}, so it names no single Entity in this model and the read "
                "resolves nowhere (m-predicate reference resolution)",
            )
        raise QueryTargetError(
            "the connected model declares no Entity for this read's target "
            "(query-target-not-in-model)"
        )
    validated = validate_object_query(root, query, model)
    deferred = deferred_features(query)
    if deferred:
        raise DeferredFeatureError(deferred)
    if form == "rows" and fetches_relationships(query):
        raise ValueError(
            "a row-form read materializes no relationships, so it carries no deep-fetch "
            "levels; request the graph form to materialize a related level"
        )
    return validated


def fetches_relationships(query: ObjectQueryNode) -> bool:
    """Whether ``query`` names a relationship level to fetch.

    Includes is one clause of one flat query, so this is a field read: a named
    level is a path segment, and a path is non-empty by construction. Deciding it
    structurally is what keeps this seam free of deep-fetch planning, which its
    enforcement scope forbids it to reach.
    """
    return any(path.segments for path in query.includes)
