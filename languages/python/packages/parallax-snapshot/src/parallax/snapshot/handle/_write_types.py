"""``parallax.snapshot.handle._write_types`` — the lowering vocabulary.

:class:`WriteLoweringError` is the loud refusal a caller wiring defect earns
rather than a wrong emission.

Kept in its own leaf rather than inside :mod:`parallax.snapshot.handle._keyed_sql`
or :mod:`parallax.snapshot.handle._write_lowering` because those import it and
homing it in either would force a back-edge. The name is re-exported through the
package's frozen ``__all__``, so its spelling is public API.
"""

from __future__ import annotations

__all__ = ["WriteLoweringError"]


class WriteLoweringError(ValueError):
    """A planned write cannot be lowered to DML by the write seam (a caller
    wiring defect this seam still refuses loudly rather than mis-emitting —
    e.g. a materializing predicate write that reached here un-decomposed)."""
