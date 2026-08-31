"""``parallax.snapshot.handle._preflight`` — the shared read-preflight seam.

Every modeled read passes through :func:`preflight` before any I/O:
:meth:`Database.find`, :meth:`Transaction.find`, both Wire views' ``find``, both
values-lane entry points, and the conformance compile lane call it rather than
reimplementing a step of it. The
seam resolves the query's own target in the connected model, validates the
canonical Object Query from that resolved root, and classifies it against
Snapshot's Deferred Execution Features, in that order.

There is one gate rather than two because there is one value: an Object Query
carries its target and its clauses, so a Typed caller, a Wire caller, and a
class-less one hand over the same thing. The refusals and their order therefore exist once, and no
entry point can become a second, laxer read door by drifting from a second copy.

``form`` is the one fact a query does not carry — an Object Query has no result
form, and graph versus rows is a property of the CALL — so the gate takes it and
adds the one refusal it decides: the values lane materializes no relationships,
and a request selecting it while naming Include Paths is refused here rather than
inside the lane it cannot serve. Each of the four refusals this gate states is
decided before any I/O, which is what the force-flush ordering below requires.

The order is the contract, not an implementation detail. Target resolution is
not redundant with query validation: a find-all query carries no attribute
reference anywhere, so validation would never observe an undeclared target.
Classification comes last because it presupposes both — a query the connected
model cannot answer is refused as such and exposes no deferral result, even
where its clauses would match one. Form comes after all three: it is a refusal
about the result the caller asked for rather than about the read, and a query
this implementation cannot answer at all is refused as such first. And on a
participating read, preflight runs BEFORE ``uow.read``, whose force-flush would
otherwise turn a refused read into a write.

Deferred-Feature classification belongs to modeled READ execution alone. A
predicate-selected write reaches its own boundary, which requires a
mutation-compatible Object Query first, so a read-shaped query is refused as
``query-not-mutation-compatible`` there and never classified here.

This is its own module precisely so that it can be proven to touch no port. Its
``spec/python.md`` §7 scope grants only the Metamodel Interface, Predicate, and
Object Query, so the generated import-linter contract forbids it — directly or
through any chain — from reaching SQL generation, a dialect, any Database Port,
deep-fetch planning, or materialization. A helper that needs any of those does
not belong here.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores
(an underscored name imported across a module boundary is a Pyright strict
``reportPrivateUsage`` error, and this seam exists only to be imported).
"""

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
