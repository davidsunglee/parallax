"""``parallax.snapshot.handle`` — the composition surface (connect / transact / plan / lowering).

This is the layer that legally sees **both** the neutral write-instruction IR /
Write Planner (``m-unit-work``) **and** SQL generation (``m-sql`` / ``m-dialect``):
the module DAG forbids ``m-unit-work`` from importing ``m-sql`` (why the planner
emits a neutral :class:`~parallax.core.unit_work.WritePlan`) and forbids ``m-sql``
from importing ``m-unit-work``, so the write-DML → SQL lowering — the deliberate
``m-sql`` edge M3 deferred — is composed **here**. It is also the sole module
cleared to import both ``m-batch-write`` and ``m-unit-work``, which is why the
Write Planner's strategy adapters are wired here (:func:`build_write_planner`)
rather than in either optional policy module. :func:`stream_lowered` is the
single lowering function; both the developer transaction path (the injected
``FlushExecutor``) and the conformance engine reuse it (the conformance family is
the import-side DAG exemption), so there is exactly one write-lowering seam.

This module defines nothing: every name below is defined in a private
sibling and re-exported here, and no runtime orchestration remains at this level.
The private modules are implementation rather than seams — nothing outside the
package imports one except the three sanctioned test seams — so a name's
``__module__`` now reports its private defining module, which no specification or
public-surface check promises. Where the exported names live:

- :mod:`~parallax.snapshot.handle._database` — :class:`Database`, :func:`connect`,
  :class:`TransactionOptionConflictError`, :class:`TransactionOwnershipError`:
  the composition root (which connects only to a class-backed Domain Model) and
  the spec §5 callback demarcation (sentinel-backed options, join through the
  exact originating ``Database`` with the option-conflict check, the
  ``m-auto-retry`` bounded retry loop, and the injected flush executor).
- :mod:`~parallax.snapshot.handle._planning` — :func:`build_write_planner`, the
  one factory that wires ``m-batch-write``, ``m-opt-lock``, ``m-txtime-write``,
  and ``m-bitemp-write`` into a :class:`~parallax.core.unit_work.WritePlanner`'s
  strategy ports, and :func:`plan_temporal_close`, the ``m-opt-lock`` conflict
  lane's standalone close probe wired with the same concurrency adapter.
- :mod:`~parallax.snapshot.handle._transaction` — :class:`Transaction`: the
  developer verbs a ``db.transact`` closure drives, and the participating
  :meth:`Transaction.find`.
- :mod:`~parallax.snapshot.handle._errors` — :class:`QueryTargetError`, the
  refusal of a query whose target the connected model does not declare, raised
  by the shared read-preflight seam and by the write side's target resolution
  alike, and :class:`SnapshotConnectionError`, the refusal of a model that names
  no Entity Class to materialize into. Both are defined in a dependency-free leaf
  so every raiser can name them.
- :mod:`~parallax.snapshot.handle._read` — :func:`find` and :func:`find_history`,
  the one production find executor, plus the result surface they build
  (:class:`Snapshot`, :class:`Execution`, :class:`ExecutedStatement`,
  :class:`FindResult`, :class:`HistoryFindResult`, :class:`MilestoneGraph`,
  :class:`NoResultFound`, :class:`TooManyResultsFound`).
- :mod:`~parallax.snapshot.handle._write_lowering` — :func:`stream_lowered`,
  which lowers an already-settled Write Plan's steps into the one seam DML
  becomes through.
- :mod:`~parallax.snapshot.handle._step_lowering` — :func:`lower_step`, the
  physical lowering of one settled step on its own, for the ``m-opt-lock``
  conflict lane's standalone close probe.
- :mod:`~parallax.snapshot.handle._write_types` — :class:`WriteLoweringError`.
- :mod:`~parallax.snapshot.handle._write_inputs` —
  :class:`TransactionTimePinReadOnlyError` and :func:`validate_source_pin`, the
  finite-Transaction-Time-pin refusal the keyed verbs and the conformance
  engine's scenario grading share.

The modules behind no exported name (``_wrap``, ``_family``, ``_keyed_sql``,
``_predicate_writes``, ``_preflight``) are reached only through the modules
above; each documents its own place in the package's acyclic internal graph.
``_preflight`` in particular stays unexported: the read gate is an intra-package
seam, and its own §7 scope is what proves it reaches no port.
"""

from __future__ import annotations

from parallax.snapshot.handle._database import (
    Database,
    TransactionOptionConflictError,
    TransactionOwnershipError,
    connect,
)
from parallax.snapshot.handle._errors import QueryTargetError, SnapshotConnectionError
from parallax.snapshot.handle._planning import build_write_planner, plan_temporal_close
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
from parallax.snapshot.handle._step_lowering import lower_step
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._write_inputs import (
    TransactionTimePinReadOnlyError,
    validate_source_pin,
)
from parallax.snapshot.handle._write_lowering import stream_lowered
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = [
    "Database",
    "ExecutedStatement",
    "Execution",
    "FindResult",
    "HistoryFindResult",
    "MilestoneGraph",
    "NoResultFound",
    "QueryTargetError",
    "Snapshot",
    "SnapshotConnectionError",
    "TooManyResultsFound",
    "Transaction",
    "TransactionOptionConflictError",
    "TransactionOwnershipError",
    "TransactionTimePinReadOnlyError",
    "WriteLoweringError",
    "build_write_planner",
    "connect",
    "find",
    "find_history",
    "lower_step",
    "plan_temporal_close",
    "stream_lowered",
    "validate_source_pin",
]
