"""``parallax.core.sql_gen`` enforcement scope (m-sql).

SQL generation: the three-stage read compiler (canonicalize -> lower ->
normalize) that turns an ``m-op-algebra`` operation into one canonical
``Statement`` per dialect. Lowering is a set of per-concern ``match`` functions
over the node union; dialect variation enters only through the injected
``Dialect`` strategy. ``m-sql`` depends on ``m-op-algebra`` and ``m-dialect``.
"""

from __future__ import annotations

from parallax.core.sql_gen.compile import ResultForm, SqlGenError, Statement, compile_read

__all__ = ["ResultForm", "SqlGenError", "Statement", "compile_read"]
