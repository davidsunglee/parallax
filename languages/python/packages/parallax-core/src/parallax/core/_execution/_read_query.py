from __future__ import annotations

from typing import Final

from parallax.core._execution._features import deferred_feature_refusal, deferred_features
from parallax.core.internal.base import UsageError
from parallax.core.internal.metamodel import Metamodel, entity_by_name
from parallax.core.internal.metamodel._states import ambiguous_entity_spellings
from parallax.core.internal.object_query import (
    InterpretedQuery,
    QueryInput,
    validate_object_query,
)
from parallax.core.internal.object_query._resolved import ResolvedObjectQuery
from parallax.core.internal.predicate import REFERENCE_AMBIGUOUS_ENTITY_NAME

__all__ = ["QUERY_TARGET_NOT_IN_MODEL", "resolve_read_query"]

QUERY_TARGET_NOT_IN_MODEL: Final = "query-target-not-in-model"
"""Code for a query whose target Entity the connected model does not declare.

The identical query succeeds against a model declaring the Entity, so the
refusal names the model rather than the query, and retains neither.
"""


def resolve_read_query(query: QueryInput, *, model: Metamodel) -> ResolvedObjectQuery:
    """Resolve and validate ``query`` against ``model``, and do no I/O.

    A canonical query's predicate is validated here; an interpreted query's
    adapter is invoked at the same stage, so both meet one gate order.

    Target resolution follows the reference-position rule every validator and
    lowering site resolves a spelling by, so "read-query resolution accepted this
    target" implies "planning resolves it". Raises a
    :class:`~parallax.core.internal.base.UsageError` coded ``query-target-not-in-model``
    when ``model`` declares no Entity for it, a ``UsageError`` with the rule's
    code when a clause is not applicable from that resolved root, and an
    :class:`~parallax.core.internal.base.UnsupportedError` coded
    ``execution-feature-deferred`` when the query is applicable but requires a
    Feature this implementation has not built yet. Performs no SQL generation,
    Database Port or connection work, transaction demarcation, or
    materialization.
    """
    clauses = query.clauses if isinstance(query, InterpretedQuery) else query
    root = entity_by_name(model, clauses.target.canonical)
    if root is None:
        shared = ambiguous_entity_spellings(model, clauses.target.canonical)
        if shared:
            raise UsageError(
                REFERENCE_AMBIGUOUS_ENTITY_NAME,
                f"{clauses.target.canonical!r}: the bare Entity spelling is shared by "
                f"{list(shared)}, so it names no single Entity in this model and the read "
                "resolves nowhere (m-predicate reference resolution)",
            )
        raise UsageError(
            QUERY_TARGET_NOT_IN_MODEL,
            "the connected model declares no Entity for this read's target",
        )
    resolved = validate_object_query(root, query, model)
    deferred = deferred_features(clauses)
    if deferred:
        raise deferred_feature_refusal(deferred)
    return resolved
