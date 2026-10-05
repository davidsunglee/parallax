from __future__ import annotations

from parallax.core.unit_work import (
    WRITE_EVIDENCE_CODES,
    ObjectKey,
    WriteEvidenceError,
    WriteEvidenceErrorCode,
    WriteInstructionError,
)
from parallax.snapshot.handle._adoption import ExecutionFailure
from parallax.snapshot.handle._database import Database, ScopedDatabase, connect, prepare_model
from parallax.snapshot.handle._errors import (
    QueryTargetError,
    SnapshotConnectionError,
    SnapshotMaterializationError,
)
from parallax.snapshot.handle._execution_authority import InvalidPrincipalError, Principal
from parallax.snapshot.handle._features import DeferredFeatureError
from parallax.snapshot.handle._keyed_writes import (
    KEYED_WRITE_VALUE_CODES,
    KeyedWriteValueError,
    TransactionTimePinReadOnlyError,
    validate_source_pin,
)
from parallax.snapshot.handle._options import DatabaseOptions
from parallax.snapshot.handle._planning import build_write_planner
from parallax.snapshot.handle._publication import (
    ModelSelection,
    PublicationConflictError,
    ServingModel,
)
from parallax.snapshot.handle._read import (
    CheckedSnapshot,
    NoResultFound,
    PublishedRow,
    Snapshot,
    TooManyResultsFound,
    find,
)
from parallax.snapshot.handle._stream import (
    SnapshotStream,
    SnapshotStreamContinuationError,
    SnapshotStreamStateError,
)
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._transaction_runner import (
    TransactionAuthorityError,
    TransactionOptionConflictError,
    TransactionOwnershipError,
    TransactionRollbackError,
)
from parallax.snapshot.handle._write_lowering import stream_lowered
from parallax.snapshot.materialize import (
    InvalidData,
    InvalidDataError,
    SnapshotConsistencyError,
    StoredDataIssue,
    WireEntity,
    WireValue,
)

__all__ = [
    "KEYED_WRITE_VALUE_CODES",
    "WRITE_EVIDENCE_CODES",
    "CheckedSnapshot",
    "Database",
    "DatabaseOptions",
    "DeferredFeatureError",
    "ExecutionFailure",
    "InvalidData",
    "InvalidDataError",
    "InvalidPrincipalError",
    "KeyedWriteValueError",
    "ModelSelection",
    "NoResultFound",
    "ObjectKey",
    "Principal",
    "PublicationConflictError",
    "PublishedRow",
    "QueryTargetError",
    "ScopedDatabase",
    "ServingModel",
    "Snapshot",
    "SnapshotConnectionError",
    "SnapshotConsistencyError",
    "SnapshotMaterializationError",
    "SnapshotStream",
    "SnapshotStreamContinuationError",
    "SnapshotStreamStateError",
    "StoredDataIssue",
    "TooManyResultsFound",
    "Transaction",
    "TransactionAuthorityError",
    "TransactionOptionConflictError",
    "TransactionOwnershipError",
    "TransactionRollbackError",
    "TransactionTimePinReadOnlyError",
    "WireEntity",
    "WireValue",
    "WriteEvidenceError",
    "WriteEvidenceErrorCode",
    "WriteInstructionError",
    "build_write_planner",
    "connect",
    "find",
    "prepare_model",
    "stream_lowered",
    "validate_source_pin",
]
