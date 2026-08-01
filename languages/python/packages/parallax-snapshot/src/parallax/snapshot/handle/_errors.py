"""``parallax.snapshot.handle._errors`` — the dependency-free refusal leaf.

Holds the refusals more than one module in the package raises. It imports
nothing but the standard library, which is what lets the read-preflight seam
(:mod:`parallax.snapshot.handle._preflight`) and the write-lowering family leaf
(:mod:`parallax.snapshot.handle._family`) name the SAME failure: their
enforcement scopes grant disjoint dependencies, so either importing the other
would drag a scope the importer may not reach.

That emptiness is load-bearing rather than incidental, so ``spec/python.md`` §7
gives this module its own child scope with a grant row of ``(none)``. The
generated import-linter contract forbids every first-party scope outside
``parallax.snapshot.handle`` AND every sibling child scope inside it, which is
the whole of what makes the two consumers legal: each may name this module only
because reaching it reaches nothing they are not already granted. A ``forbidden``
row is package-scoped, so the one name the row cannot state is the shared parent
package itself. A sibling module §7 declares no child scope over is not stated
either; such a module always carries a first-party import of its own, because
``just python-check-scope-ownership`` fails on an import-free module written
beside this scope, so importing one breaks the gate on the chain through it.
Those two gates together are what keep this module's dependency-freedom
enforced rather than conventional.

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
