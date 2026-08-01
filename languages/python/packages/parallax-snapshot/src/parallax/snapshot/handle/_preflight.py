"""``parallax.snapshot.handle._preflight`` — the shared read-preflight seam.

Every modeled read passes through :func:`preflight_find` before any I/O:
:meth:`Database.find` and :meth:`Transaction.find` call it rather than
reimplementing a step of it. The seam lowers the Find Query, resolves its target
in the connected model, validates the canonical operation from that resolved
root, and classifies it against Snapshot's Deferred Execution Features, in that
order, and returns the one
:class:`~parallax.core.entity.LoweredFindQuery` the caller keeps for the rest of
that execution.

The order is the contract, not an implementation detail. Target resolution is
not redundant with operation validation: a find-all query carries no attribute
reference anywhere, so operation validation would never observe an undeclared
target. Classification comes last because it presupposes both — a query the
connected model cannot answer is refused as such and exposes no deferral result,
even where its operation would match one. And on a participating read, preflight
runs BEFORE ``uow.read``, whose force-flush would otherwise turn a refused read
into a write.

Deferred-Feature classification belongs to modeled READ execution alone. A
predicate-selected write reaches its own boundary, which requires a
mutation-compatible Find Query first, so a read-shaped query is refused as
``query-not-mutation-compatible`` there and never classified here.

This is its own module precisely so that it can be proven to touch no port. Its
``spec/python.md`` §7 scope grants only the Entity frontend's query submodule,
the Metamodel Interface, and the operation algebra, so the generated
import-linter contract forbids it — directly or through any chain — from
reaching SQL generation, a dialect, any Database Port, deep-fetch planning, or
materialization. The grant stops at :mod:`parallax.core.entity._query`
rather than the frontend package because the package reaches a Database Port
through its model-construction edge (``_formation_profile -> m-opt-lock ->
m-unit-work -> m-db-port``), and a forbidden row is the complement of a closure:
granting the package would put the port inside this seam's own closure, where no
row could forbid it. A helper that needs any of those does not belong here.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores
(an underscored name imported across a module boundary is a Pyright strict
``reportPrivateUsage`` error, and this seam exists only to be imported).
"""

from __future__ import annotations

from typing import Any

from parallax.core.entity._query import FindQuery, LoweredFindQuery, lower_find_query
from parallax.core.metamodel import Metamodel
from parallax.core.op_algebra import validate_operation
from parallax.snapshot.handle._errors import QueryTargetError
from parallax.snapshot.handle._features import DeferredFeatureError, deferred_features

__all__ = ["preflight_find"]


def preflight_find(query: FindQuery[Any, Any], *, model: Metamodel) -> LoweredFindQuery:
    """Lower ``query``, resolve and validate it against ``model``, and do no I/O.

    Lowering runs once here and its result is what the caller keeps for the rest
    of that execution — nothing memoizes it, so a later execution of the same
    query lowers again.

    Target resolution is by Entity Identity rather than by spelling: a Find Query
    retains the structured identity its Entity Class declared, so the lookup is
    exact, namespace-aware, and immune to the bare-name ambiguity a
    two-namespace model creates. Raises
    :class:`~parallax.snapshot.handle._errors.QueryTargetError` when ``model``
    declares no Entity for it,
    :class:`~parallax.core.op_algebra.OperationRejectedError` when the operation
    is not applicable from that resolved root, and
    :class:`~parallax.snapshot.handle._features.DeferredFeatureError` when it is
    applicable but requires a Feature this implementation has not built yet.
    Performs no SQL generation, Database Port or connection work, transaction
    demarcation, or materialization.
    """
    lowered = lower_find_query(query)
    root = model.entity(lowered.target)
    if root is None:
        raise QueryTargetError(
            "the connected model declares no Entity for this query's target "
            "(query-target-not-in-model)"
        )
    validate_operation(root, lowered.operation, model)
    deferred = deferred_features(lowered.operation)
    if deferred:
        raise DeferredFeatureError(deferred)
    return lowered
