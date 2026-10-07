from __future__ import annotations

from parallax.core.unit_work import (
    WRITE_EVIDENCE_CODES,
    WriteEvidenceError,
    WriteEvidenceErrorCode,
    WriteInstructionError,
)
from parallax.core.write_plan import ObjectKey
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
    Snapshot,
    TooManyResultsFound,
)
from parallax.snapshot.handle._stream import SnapshotStream
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._transaction_runner import (
    TransactionAuthorityError,
    TransactionOptionConflictError,
    TransactionOwnershipError,
    TransactionRollbackError,
)
from parallax.snapshot.handle._write_lowering import stream_lowered
from parallax.snapshot.materialize import (
    SnapshotConsistencyError,
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
    "InvalidPrincipalError",
    "KeyedWriteValueError",
    "ModelSelection",
    "NoResultFound",
    "ObjectKey",
    "Principal",
    "PublicationConflictError",
    "QueryTargetError",
    "ScopedDatabase",
    "ServingModel",
    "Snapshot",
    "SnapshotConnectionError",
    "SnapshotConsistencyError",
    "SnapshotMaterializationError",
    "SnapshotStream",
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
    "prepare_model",
    "stream_lowered",
    "validate_source_pin",
]
