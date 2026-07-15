"""Parallax snapshot lifecycle extension (``parallax-snapshot``).

Snapshot graph materialization and the developer handle over the spine. The
package re-exports exactly the spec §8 surface: :func:`connect` (the
composition-root entry point — application code constructs a concrete adapter
and calls ``parallax.snapshot.connect(adapter, meta)``), :class:`Snapshot`
(``Snapshot[T]``), and :class:`Execution`. :class:`NoResultFound` /
:class:`TooManyResultsFound` are ``Snapshot.result()`` / ``.result_or_none()``'s
own arity errors. The handle classes (``Database``, ``Transaction``) and the
lowering seam stay importable from :mod:`parallax.snapshot.handle`.
"""

from parallax.snapshot.handle import (
    Execution,
    NoResultFound,
    Snapshot,
    TooManyResultsFound,
    connect,
)

__all__ = [
    "Execution",
    "NoResultFound",
    "Snapshot",
    "TooManyResultsFound",
    "connect",
]
