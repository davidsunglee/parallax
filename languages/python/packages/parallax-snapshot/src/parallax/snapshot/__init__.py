"""Parallax snapshot lifecycle extension (``parallax-snapshot``).

Snapshot graph materialization and the developer handle over the spine. The
package re-exports exactly the spec §8 surface: :func:`connect` (the
composition-root entry point — application code constructs a concrete adapter
and calls ``parallax.snapshot.connect(adapter, meta)``); ``Snapshot[T]`` and
``Execution`` land with the Phase-7 materialization. The handle classes
(``Database``, ``Transaction``) and the lowering seam stay importable from
:mod:`parallax.snapshot.handle`.
"""

from parallax.snapshot.handle import connect

__all__ = ["connect"]
