"""``parallax.snapshot.handle._errors`` — the dependency-free refusal leaf.

Holds the refusals more than one module in the package raises. It imports
nothing but the standard library, which is what lets the read-preflight seam
(:mod:`parallax.snapshot.handle._preflight`) and the write-lowering family leaf
(:mod:`parallax.snapshot.handle._family`) name the SAME failure: their
enforcement scopes grant disjoint dependencies, so either importing the other
would drag a scope the importer may not reach.

That emptiness is load-bearing rather than incidental, so it is enforced rather
than described: ``spec/python.md`` §7 gives this module its own child scope with
a grant row of ``(none)``, and the generated import-linter contract therefore
forbids every first-party scope outside this package. Any first-party import
added here fails ``just python-check-imports``.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores.
"""

from __future__ import annotations

from typing import Final

__all__ = ["QueryTargetError"]


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
