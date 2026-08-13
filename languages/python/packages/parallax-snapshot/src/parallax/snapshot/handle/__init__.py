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
  alike, :class:`SnapshotConnectionError`, the refusal of a model that names
  no Entity Class to materialize into, :class:`SnapshotMaterializationError`,
  the one translation of a graph-construction or lifecycle failure at the
  materialization boundary, and :class:`UnobservedWriteError`, the refusal of an
  Observation Key naming nothing this unit of work recorded. All four are
  defined in a dependency-free leaf so every raiser can name them.
- :mod:`~parallax.snapshot.handle._features` — :class:`DeferredFeatureError`,
  beside the fixed inventory of Deferred Execution Features it reports and the
  recognizer that matches a canonical Object Query against them.
- :mod:`~parallax.snapshot.handle._preflight` — :func:`preflight`, the one read
  gate every entry point crosses before any I/O.
- :mod:`~parallax.snapshot.handle._read` — :func:`find` and :func:`find_history`,
  the one production find executor, plus the result surface they build
  (:class:`Snapshot`, :class:`CheckedSnapshot`, :class:`FindResult`,
  :class:`HistoryFindResult`,
  :class:`NoResultFound`, :class:`TooManyResultsFound`) and
  :class:`ObservationCollector`, the optional seam a participating read hands its
  materialized rows to. :class:`NeutralReadRequest` is what the model-neutral
  entry points take, and :class:`NeutralReadResult` what they answer.

The model-neutral read vocabulary — :class:`NeutralRows`, :class:`NeutralGraph`,
:class:`NeutralGraphs`, :class:`NeutralNode`, :class:`NeutralNodeView` — is
:mod:`parallax.snapshot.materialize`'s, built by the second materializer beside
the merge both materializers consume, and re-exported here beside the entry
points that answer it. The invalid-result vocabulary a classified root publishes
— :class:`InvalidData`, :class:`StoredDataIssue`, :class:`InvalidDataError`, and
:class:`~parallax.core.unit_work.ObjectKey`, the identity a record locates itself
by — is re-exported for the same reason: a ``Snapshot`` element's own type must
be nameable beside the accessor that answers it.
:class:`~parallax.core.unit_work.ObservationKey` is
re-exported for the same reason the execution-provenance subset is: a caller
cannot use :meth:`Transaction.write_neutral`'s documented contract, or read the
key a neutral node publishes, without naming the type.

Execution provenance is `m-execution-log`'s vocabulary, canonically defined in
:mod:`parallax.core.execution_log`; the developer-facing subset a `db.find` or
`db.transact` caller reads off a result — :class:`ReadTrace`,
:class:`DatabaseCall`, :class:`ExecutionLog`, :class:`TransactionAttempt`,
:class:`TransactionResult`, and the two refusals a joined result's execution view
raises — is re-exported here beside :class:`Database` and :class:`Transaction`
rather than sending a developer to a core module for the type their own result
already carries.
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
  engine's scenario grading share, plus :class:`KeyedWriteValueError` and
  :data:`KEYED_WRITE_VALUE_CODES`, the provenance refusal the value-taking keyed
  verbs run before deriving a row.

The modules behind no exported name (``_materializer``, ``_family``,
``_keyed_sql``, ``_predicate_writes``) are reached only through the modules
above; each documents its own place in the package's acyclic internal graph.
``_preflight`` exports :func:`preflight` alone: an adapter's compile lane must
refuse exactly what this implementation's executor refuses, so the one gate is
reachable without an executor, and the module's own §7 scope is what proves it
reaches no port.
"""

from __future__ import annotations

from parallax.core.execution_log import (
    DatabaseCall,
    ExecutionLog,
    ReadTrace,
    TransactionAttempt,
    TransactionInProgressError,
    TransactionNotCommittedError,
    TransactionResult,
)
from parallax.core.unit_work import ObjectKey, ObservationKey
from parallax.snapshot.handle._database import (
    Database,
    TransactionOptionConflictError,
    TransactionOwnershipError,
    connect,
)
from parallax.snapshot.handle._errors import (
    QueryTargetError,
    SnapshotConnectionError,
    SnapshotMaterializationError,
    UnobservedWriteError,
)
from parallax.snapshot.handle._features import DeferredFeatureError
from parallax.snapshot.handle._planning import build_write_planner, plan_temporal_close
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._read import (
    CheckedSnapshot,
    FindResult,
    HistoryFindResult,
    NeutralReadRequest,
    NeutralReadResult,
    NoResultFound,
    ObservationCollector,
    Snapshot,
    TooManyResultsFound,
    find,
    find_history,
)
from parallax.snapshot.handle._step_lowering import lower_step
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._write_inputs import (
    KEYED_WRITE_VALUE_CODES,
    KeyedWriteValueError,
    TransactionTimePinReadOnlyError,
    validate_source_pin,
)
from parallax.snapshot.handle._write_lowering import stream_lowered
from parallax.snapshot.handle._write_types import WriteLoweringError
from parallax.snapshot.materialize import (
    InvalidData,
    InvalidDataError,
    NeutralGraph,
    NeutralGraphs,
    NeutralNode,
    NeutralNodeView,
    NeutralReadOutput,
    NeutralRows,
    StoredDataIssue,
)

__all__ = [
    "KEYED_WRITE_VALUE_CODES",
    "CheckedSnapshot",
    "Database",
    "DatabaseCall",
    "DeferredFeatureError",
    "ExecutionLog",
    "FindResult",
    "HistoryFindResult",
    "InvalidData",
    "InvalidDataError",
    "KeyedWriteValueError",
    "NeutralGraph",
    "NeutralGraphs",
    "NeutralNode",
    "NeutralNodeView",
    "NeutralReadOutput",
    "NeutralReadRequest",
    "NeutralReadResult",
    "NeutralRows",
    "NoResultFound",
    "ObjectKey",
    "ObservationCollector",
    "ObservationKey",
    "QueryTargetError",
    "ReadTrace",
    "Snapshot",
    "SnapshotConnectionError",
    "SnapshotMaterializationError",
    "StoredDataIssue",
    "TooManyResultsFound",
    "Transaction",
    "TransactionAttempt",
    "TransactionInProgressError",
    "TransactionNotCommittedError",
    "TransactionOptionConflictError",
    "TransactionOwnershipError",
    "TransactionResult",
    "TransactionTimePinReadOnlyError",
    "UnobservedWriteError",
    "WriteLoweringError",
    "build_write_planner",
    "connect",
    "find",
    "find_history",
    "lower_step",
    "plan_temporal_close",
    "preflight",
    "stream_lowered",
    "validate_source_pin",
]
