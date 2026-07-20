"""``parallax.snapshot.handle`` — the composition surface (connect / transact / lowering).

This is the layer that legally sees **both** the neutral write-instruction IR /
flush planner (``m-unit-work``) **and** SQL generation (``m-sql`` / ``m-dialect``):
the module DAG forbids ``m-unit-work`` from importing ``m-sql`` (why the planner
emits a neutral :class:`~parallax.core.unit_work.FlushPlan`) and forbids ``m-sql``
from importing ``m-unit-work``, so the write-DML → SQL lowering — the deliberate
``m-sql`` edge M3 deferred — is composed **here**. :func:`lower_write` is the single
lowering function; both the developer transaction path (the injected
``FlushExecutor``) and the conformance engine reuse it (the conformance family is
the import-side DAG exemption), so there is exactly one write-lowering seam.

Since COR-42 this module defines nothing: every name below is defined in a private
sibling and re-exported here, and no runtime orchestration remains at this level.
The private modules are implementation rather than seams — nothing outside the
package imports one except the three sanctioned test seams — so a name's
``__module__`` now reports its private defining module, which no specification or
public-surface check promises. Where the exported names live:

- :mod:`~parallax.snapshot.handle._database` — :class:`Database`, :func:`connect`,
  :class:`TransactionOptionConflictError`: the composition root and the spec §5
  callback demarcation (sentinel-backed options, join with the option-conflict
  check, the ``m-auto-retry`` bounded retry loop, and the injected flush executor).
- :mod:`~parallax.snapshot.handle._transaction` — :class:`Transaction`: the
  developer verbs a ``db.transact`` closure drives, and the participating
  :meth:`Transaction.find`.
- :mod:`~parallax.snapshot.handle._read` — :func:`find` and :func:`find_history`,
  the one production find executor, plus the result surface they build
  (:class:`Snapshot`, :class:`Execution`, :class:`ExecutedStatement`,
  :class:`FindResult`, :class:`HistoryFindResult`, :class:`MilestoneGraph`,
  :class:`NoResultFound`, :class:`TooManyResultsFound`).
- :mod:`~parallax.snapshot.handle._write_lowering` — :func:`lower_write` and the
  ``m-opt-lock`` conflict lane's :func:`lower_temporal_close`.
- :mod:`~parallax.snapshot.handle._write_types` — :class:`WriteLoweringError` and
  :class:`LoweredStatement`.

The five modules behind no exported name (``_wrap``, ``_family``, ``_keyed_sql``,
``_write_inputs``, ``_predicate_writes``) are reached only through the modules
above; each documents its own place in the package's acyclic internal graph.
"""

from __future__ import annotations

from parallax.snapshot.handle._database import (
    Database,
    TransactionOptionConflictError,
    connect,
)
from parallax.snapshot.handle._read import (
    ExecutedStatement,
    Execution,
    FindResult,
    HistoryFindResult,
    MilestoneGraph,
    NoResultFound,
    Snapshot,
    TooManyResultsFound,
    find,
    find_history,
)
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._write_lowering import lower_temporal_close, lower_write
from parallax.snapshot.handle._write_types import LoweredStatement, WriteLoweringError

__all__ = [
    "Database",
    "ExecutedStatement",
    "Execution",
    "FindResult",
    "HistoryFindResult",
    "LoweredStatement",
    "MilestoneGraph",
    "NoResultFound",
    "Snapshot",
    "TooManyResultsFound",
    "Transaction",
    "TransactionOptionConflictError",
    "WriteLoweringError",
    "connect",
    "find",
    "find_history",
    "lower_temporal_close",
    "lower_write",
]
