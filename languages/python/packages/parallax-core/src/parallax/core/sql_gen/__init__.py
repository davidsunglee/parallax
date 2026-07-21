"""``parallax.core.sql_gen`` enforcement scope (m-sql).

SQL generation: the three-stage read compiler (canonicalize -> lower ->
normalize) that turns an ``m-op-algebra`` operation into one canonical
``Statement`` per dialect. Lowering is a set of per-concern ``match`` functions
over the node union; dialect variation enters only through the injected
``Dialect`` strategy. ``m-sql`` depends on ``m-op-algebra`` and ``m-dialect``.

The six names below are the whole supported seam; everything else in this
package is private implementation. ``compile_read`` returns a self-contained
:class:`CompiledRead` — statement, root narrow, and row transform together — so
a caller executes and transforms without re-deriving anything from the
operation it just compiled.
"""

from __future__ import annotations

from parallax.core.sql_gen._compile import (
    CompiledPredicate,
    CompiledRead,
    SqlGenError,
    Statement,
    compile_read,
    compile_write_predicate,
)

__all__ = [
    "CompiledPredicate",
    "CompiledRead",
    "SqlGenError",
    "Statement",
    "compile_read",
    "compile_write_predicate",
]
