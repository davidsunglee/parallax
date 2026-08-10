"""``parallax.snapshot.handle._preflight`` — the shared read-preflight seam.

Every modeled read passes through :func:`preflight_find` before any I/O:
:meth:`Database.find` and :meth:`Transaction.find` call it rather than
reimplementing a step of it. The seam lowers the Find Query, resolves its target
in the connected model, validates the canonical operation from that resolved
root, and classifies it against Snapshot's Deferred Execution Features, in that
order, and returns the one
:class:`~parallax.core.entity.LoweredFindQuery` the caller keeps for the rest of
that execution.

:func:`preflight_neutral` IS that gate, and :func:`preflight_find` is it with a
lowering step in front: a model-neutral read states the two facts lowering would
have produced, so a neutral caller supplies them directly. The three refusals and
their order therefore exist once, and the neutral entry points cannot become a
second, laxer read door by drifting from a second copy.

A neutral read states one fact more than lowering produces — the RESULT FORM it
wants — so the gate takes it and adds the one refusal it decides: the values lane
materializes no relationships, and a request selecting it while naming
deep-fetch paths is refused here rather than inside the lane it cannot serve.
Every refusal a neutral read can meet is therefore decided before any I/O, which
is what the force-flush ordering below requires.

The order is the contract, not an implementation detail. Target resolution is
not redundant with operation validation: a find-all query carries no attribute
reference anywhere, so operation validation would never observe an undeclared
target. Classification comes last because it presupposes both — a query the
connected model cannot answer is refused as such and exposes no deferral result,
even where its operation would match one. Form comes after all three: it is a
refusal about the result the caller asked for rather than about the read, and a
query this implementation cannot answer at all is refused as such first. And on a
participating read, preflight runs BEFORE ``uow.read``, whose force-flush would
otherwise turn a refused read into a write.

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

from typing import Any, Literal

from parallax.core.entity._query import FindQuery, LoweredFindQuery, lower_find_query
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.op_algebra import (
    AsOf,
    AsOfRange,
    DeepFetch,
    Distinct,
    History,
    Limit,
    Narrow,
    Operation,
    OrderBy,
    validate_operation,
)
from parallax.snapshot.handle._errors import QueryTargetError
from parallax.snapshot.handle._features import DeferredFeatureError, deferred_features

__all__ = ["preflight_find", "preflight_neutral"]


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
    preflight_neutral(lowered.target, lowered.operation, model=model, form="graph")
    return lowered


def preflight_neutral(
    target: EntityIdentity,
    operation: Operation,
    *,
    model: Metamodel,
    form: Literal["rows", "graph"],
) -> None:
    """Resolve and validate an already-lowered read against ``model``, and do no I/O.

    The gate itself, entered directly by a caller that has no Find Query to
    lower: a model-neutral read supplies the resolved target and the canonical
    operation, which is exactly what lowering produces. Every entry point runs
    the same three steps in the same ORDER — target resolution, then operation
    validation from that resolved root, then Deferred Execution Feature
    classification — so a neutral read is refused for the same reason, with the
    same class, at the same point relative to a participating read's
    force-flush.

    ``form`` is the fourth step and the one a typed find always answers
    ``"graph"``: the values lane projects scalars and materializes no
    relationships, so a ``"rows"`` request whose operation names deep-fetch paths
    is refused here — before the lane compiles anything and, on a participating
    read, before the force-flush that would otherwise make the refusal write.
    """
    root = model.entity(target)
    if root is None:
        raise QueryTargetError(
            "the connected model declares no Entity for this read's target "
            "(query-target-not-in-model)"
        )
    validate_operation(root, operation, model)
    deferred = deferred_features(operation)
    if deferred:
        raise DeferredFeatureError(deferred)
    if form == "rows" and fetches_relationships(operation):
        raise ValueError(
            "a row-form read materializes no relationships, so it carries no deep-fetch "
            "levels; request the graph form to materialize a related level"
        )


def fetches_relationships(operation: Operation) -> bool:
    """Whether ``operation`` names a relationship level to fetch, at any depth a
    result wrapper can carry one.

    A deep fetch is not confined to the outermost node: ``m-op-algebra`` composes
    it freely with the other nodes that return their operand's OWN rows —
    ``orderBy``, ``limit``, ``distinct``, ``narrow``, and the temporal ``asOf``,
    ``asOfRange``, and ``history`` — so ``limit(deepFetch(all, path), 1)`` is as
    legal a request as the bare ``deepFetch``, and the levels it names are just as
    unserviceable by the values lane. The walk descends that closed set of
    wrappers and no other node, which is the same spine the algebra's own ordered-
    position rule resolves through; a level named anywhere along it refuses.

    Reaching a ``DeepFetch`` ends the walk either way: a directive with no path,
    or a path with no segment, names no level and is not a refusal. Deciding all
    of this structurally is what keeps this seam free of deep-fetch planning,
    which its enforcement scope forbids it to reach — and the seam cannot borrow
    the planner's own reading of the operation, which sees the outer node alone.
    """
    node = operation
    while True:
        match node:
            case DeepFetch(paths=paths):
                return any(path.segments for path in paths)
            case (
                OrderBy(operand=operand)
                | Limit(operand=operand)
                | Distinct(operand=operand)
                | Narrow(operand=operand)
                | AsOf(operand=operand)
                | AsOfRange(operand=operand)
                | History(operand=operand)
            ):
                node = operand
            case _:
                return False
