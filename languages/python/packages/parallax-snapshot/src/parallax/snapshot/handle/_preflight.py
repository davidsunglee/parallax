"""``parallax.snapshot.handle._preflight`` — the shared read-preflight seam.

Every modeled read passes through :func:`preflight_find` before any I/O:
:meth:`Database.find` and :meth:`Transaction.find` call it rather than
reimplementing a step of it. The seam resolves the query's target in the
connected model and validates its canonical operation from that resolved root,
in that order, and returns the one :class:`LoweredRead` the caller keeps for the
rest of that execution.

The order is the contract, not an implementation detail. Target resolution is
not redundant with operation validation: a find-all query carries no attribute
reference anywhere, so operation validation would never observe an undeclared
target. And on a participating read, preflight runs BEFORE ``uow.read``, whose
force-flush would otherwise turn a refused read into a write.

This is its own module precisely so that it can be proven to touch no port. Its
``spec/python.md`` §7 scope grants only the Entity frontend's statement
submodule, the Metamodel Interface, and the operation algebra, so the generated
import-linter contract forbids it — directly or through any chain — from
reaching SQL generation, a dialect, any Database Port, deep-fetch planning, or
materialization. The grant stops at :mod:`parallax.core.entity.statement`
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

from dataclasses import dataclass

from parallax.core.entity.statement import Statement as EntityStatement
from parallax.core.metamodel import EntityMetadata, Metamodel, entity_by_name
from parallax.core.op_algebra import Operation, validate_operation
from parallax.snapshot.handle._errors import QueryTargetError

__all__ = ["LoweredRead", "preflight_find"]


@dataclass(frozen=True, slots=True)
class LoweredRead:
    """One execution's lowered read, produced by :func:`preflight_find`.

    ``target`` is the query's own target spelling (what the find executor and
    the result conversion name the queried position by), ``root`` the accepted
    Metadata it resolved to in the connected model, and ``operation`` the
    canonical ``m-op-algebra`` operation that was validated from that root.
    Carries no model, no class index, no feature tags, no SQL, and no Database.
    """

    target: str
    root: EntityMetadata
    operation: Operation


def preflight_find(query: EntityStatement, *, model: Metamodel) -> LoweredRead:
    """Resolve and validate ``query`` against ``model``, performing no I/O.

    Raises :class:`~parallax.snapshot.handle._errors.QueryTargetError` when
    ``model`` declares no Entity for the query's target, and
    :class:`~parallax.core.op_algebra.OperationRejectedError` when the operation
    is not applicable from that resolved root. Performs no SQL generation,
    Database Port or connection work, transaction demarcation, or
    materialization.
    """
    target = query.target
    root = entity_by_name(model, target)
    if root is None:
        raise QueryTargetError(
            "the connected model declares no Entity for this query's target "
            "(query-target-not-in-model)"
        )
    operation = query.operation()
    validate_operation(root, operation, model)
    return LoweredRead(target=target, root=root, operation=operation)
