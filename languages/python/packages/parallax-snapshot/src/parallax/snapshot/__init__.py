"""Parallax snapshot lifecycle extension (``parallax-snapshot``).

Snapshot graph materialization and the developer handle over the spine. The
package re-exports exactly the spec §8 surface: :func:`connect` (the
composition-root entry point — application code constructs a concrete adapter
and calls ``parallax.snapshot.connect(adapter, model)``), :class:`Snapshot`
(``Snapshot[T]``), and :class:`Execution`. :class:`NoResultFound` /
:class:`TooManyResultsFound` are ``Snapshot.result()`` / ``.result_or_none()``'s
own arity errors. The four refusals are :class:`QueryTargetError`, of a query
whose target the connected model does not declare;
:class:`DeferredFeatureError`, of a valid query whose execution Features this
implementation has deferred; :class:`SnapshotConnectionError`, of a model that
cannot materialize rows; and :class:`TransactionOwnershipError`, the
demarcation's own refusal of a nested ``transact`` through a handle that did not
open it. The handle classes (``Database``, ``Transaction``) and the lowering seam
stay importable from :mod:`parallax.snapshot.handle`.
"""

from parallax.snapshot.handle import (
    DeferredFeatureError,
    Execution,
    NoResultFound,
    QueryTargetError,
    Snapshot,
    SnapshotConnectionError,
    TooManyResultsFound,
    TransactionOwnershipError,
    connect,
)

__all__ = [
    "DeferredFeatureError",
    "Execution",
    "NoResultFound",
    "QueryTargetError",
    "Snapshot",
    "SnapshotConnectionError",
    "TooManyResultsFound",
    "TransactionOwnershipError",
    "connect",
]
