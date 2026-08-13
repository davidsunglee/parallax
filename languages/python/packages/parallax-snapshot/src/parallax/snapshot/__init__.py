"""Parallax snapshot lifecycle extension (``parallax-snapshot``).

Snapshot graph materialization and the developer handle over the spine. The
package re-exports exactly the spec §8 surface: :func:`connect` (the
composition-root entry point — application code constructs a concrete adapter
and calls ``parallax.snapshot.connect(adapter, model)``), :class:`Snapshot`
(``Snapshot[T]``) with :class:`CheckedSnapshot` (``CheckedSnapshot[T]``), its
checked view, the in-band invalid-result vocabulary a classified root publishes
— :class:`InvalidData`, :class:`StoredDataIssue`, :class:`ObjectKey` (the
identity a record locates itself by), and the :class:`InvalidDataError` a
default accessor raises — and the execution-provenance subset a result carries —
:class:`ReadTrace`, :class:`DatabaseCall`, :class:`ExecutionLog`,
:class:`TransactionAttempt`, and :class:`TransactionResult`, with
:class:`TransactionInProgressError` / :class:`TransactionNotCommittedError`
the two refusals a joined result's execution view raises.
:class:`NoResultFound` /
:class:`TooManyResultsFound` are ``Snapshot.result()`` / ``.result_or_none()``'s
own arity errors. The refusals are :class:`QueryTargetError`, of a query
whose target the connected model does not declare;
:class:`DeferredFeatureError`, of a valid query whose execution Features this
implementation has deferred; :class:`SnapshotConnectionError`, of a model that
cannot materialize rows; :class:`TransactionOwnershipError`, the demarcation's
own refusal of a nested ``transact`` through a handle that did not open it;
:class:`SnapshotDecodingError`, of classified stored data that prevents atomic
result publication; and
:class:`SnapshotMaterializationError`, the one translation of a failure to build
the Entity graph a successful read's rows describe; and
:class:`KeyedWriteValueError`, of a value whose provenance the keyed write verb
it was handed to does not accept, whose three codes are
:data:`KEYED_WRITE_VALUE_CODES`.

It also publishes the surface that inspects a node this lifecycle produced —
:func:`is_view_loaded`, :func:`view`, :func:`pin_of`, :func:`edge_of`, their
:class:`SnapshotInspectionError` refusal, and the
:class:`UnloadedRelationshipError` a closed-world access raises. These live here
rather than on ``parallax.core`` because each is a question about the lifecycle
that materialized the node; ``UnloadedRelationshipError`` is *defined* by
``parallax.core.entity`` and re-exported here by the package that can produce the
unloaded state, so a caller who never touches a Snapshot can never see it raised.

The handle classes (``Database``, ``Transaction``) and the lowering seam stay
importable from :mod:`parallax.snapshot.handle`.
"""

from parallax.core.entity import UnloadedRelationshipError
from parallax.snapshot._inspection import (
    SnapshotInspectionError,
    edge_of,
    is_view_loaded,
    pin_of,
    view,
)
from parallax.snapshot.handle import (
    KEYED_WRITE_VALUE_CODES,
    CheckedSnapshot,
    DatabaseCall,
    DeferredFeatureError,
    ExecutionLog,
    InvalidData,
    InvalidDataError,
    KeyedWriteValueError,
    NoResultFound,
    ObjectKey,
    QueryTargetError,
    ReadTrace,
    Snapshot,
    SnapshotConnectionError,
    SnapshotMaterializationError,
    StoredDataIssue,
    TooManyResultsFound,
    TransactionAttempt,
    TransactionInProgressError,
    TransactionNotCommittedError,
    TransactionOwnershipError,
    TransactionResult,
    connect,
)
from parallax.snapshot.materialize import SnapshotDecodingError

__all__ = [
    "KEYED_WRITE_VALUE_CODES",
    "CheckedSnapshot",
    "DatabaseCall",
    "DeferredFeatureError",
    "ExecutionLog",
    "InvalidData",
    "InvalidDataError",
    "KeyedWriteValueError",
    "NoResultFound",
    "ObjectKey",
    "QueryTargetError",
    "ReadTrace",
    "Snapshot",
    "SnapshotConnectionError",
    "SnapshotDecodingError",
    "SnapshotInspectionError",
    "SnapshotMaterializationError",
    "StoredDataIssue",
    "TooManyResultsFound",
    "TransactionAttempt",
    "TransactionInProgressError",
    "TransactionNotCommittedError",
    "TransactionOwnershipError",
    "TransactionResult",
    "UnloadedRelationshipError",
    "connect",
    "edge_of",
    "is_view_loaded",
    "pin_of",
    "view",
]
