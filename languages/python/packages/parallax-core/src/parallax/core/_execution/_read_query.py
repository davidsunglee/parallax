from __future__ import annotations

from typing import Final

from parallax.core._execution._features import DeferredFeatureError, deferred_features
from parallax.core.base import UsageError
from parallax.core.metamodel import Metamodel, entity_by_name
from parallax.core.metamodel._states import ambiguous_entity_spellings
from parallax.core.object_query import (
    InterpretedQuery,
    QueryInput,
    validate_object_query,
)
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.predicate import REFERENCE_AMBIGUOUS_ENTITY_NAME

__all__ = ["QueryTargetError", "resolve_read_query"]


class QueryTargetError(RuntimeError):
    """The connected model declares no Entity for a query's target.

    Raised before any SQL, connection acquisition, or adapter activity, and
    before a participating read force-flushes the unit of work, so a query the
    connected model cannot answer never becomes a side effect.

    The refusal reports that the CONNECTED MODEL, not the call's arguments, is
    what makes the query unanswerable — the identical query succeeds against a
    model declaring the Entity — which is why this is a ``RuntimeError``. It
    retains and exposes neither the query, the model, nor the Database:
    :data:`code` and the message are its whole public state.
    """

    code: Final[str] = "query-target-not-in-model"


def resolve_read_query(query: QueryInput, *, model: Metamodel) -> ResolvedObjectQuery:
    """Resolve and validate ``query`` against ``model``, and do no I/O.

    A canonical query's predicate is validated here; an interpreted query's
    adapter is invoked at the same stage, so both meet one gate order.

    Target resolution follows the reference-position rule every validator and
    lowering site resolves a spelling by, so "read-query resolution accepted this
    target" implies "planning resolves it". Raises
    the :class:`QueryTargetError` when ``model``
    declares no Entity for it,
    a :class:`~parallax.core.base.UsageError` with the rule's code when a clause
    is not applicable from that resolved root, and
    :class:`~parallax.core._execution._features.DeferredFeatureError` when the
    query is applicable but requires a Feature this implementation has not built
    yet. Performs no SQL generation, Database Port or connection work,
    transaction demarcation, or materialization.
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
        raise QueryTargetError(
            "the connected model declares no Entity for this read's target "
            "(query-target-not-in-model)"
        )
    resolved = validate_object_query(root, query, model)
    deferred = deferred_features(clauses)
    if deferred:
        raise DeferredFeatureError(deferred)
    return resolved
