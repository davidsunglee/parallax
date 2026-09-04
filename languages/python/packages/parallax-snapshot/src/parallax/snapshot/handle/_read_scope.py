"""``parallax.snapshot.handle._read_scope`` — the Read Scope both Handles share.

A ``Database`` and a ``Transaction`` run one read ladder: re-entry is refused,
the operation's selected read model is obtained, a classless connection is
refused, the query is lowered, the shared gate runs, the activity opens, the
executor runs, and the result is published. Only the bracket around execution
differs between a standalone read and one participating in a transaction, so the
ladder belongs here once and the difference belongs below it, behind a private
execution policy the two factories construct.

This module is an implementation boundary rather than an extension point:
nothing here is re-exported from ``parallax.snapshot.handle`` or
``parallax.snapshot``, and module privacy is what closes construction.

Its ``spec/python.md`` §7 scope states what a read ladder reaches. Batch writes,
Transaction-Time writes, and Bitemporal writes fall outside its closure although
the parent scope is granted all three; bounded automatic retry does not, because
``m-execution-lifecycle`` — which the re-entry gate and the read roots require —
declares an edge to it.

Every name here is spelled bare: privacy is carried by this MODULE's leading
underscore and by the package's frozen ``__all__``, not by per-name underscores.
"""
