from parallax.core.temporal_read import Edge
from parallax.snapshot._handle._database import Database, ScopedDatabase, connect
from parallax.snapshot._handle._errors import (
    SnapshotConnectionError,
    SnapshotMaterializationError,
)
from parallax.snapshot._handle._read import (
    CheckedSnapshot,
    NoResultFound,
    Snapshot,
    TooManyResultsFound,
)
from parallax.snapshot._handle._stream import SnapshotStream
from parallax.snapshot._handle._transaction import ReadOnlyTxnContext, TxnContext
from parallax.snapshot._handle._wire import (
    WireDatabaseView,
    WireQuery,
    WireTransactionView,
)
from parallax.snapshot._handle._wire_writes import WireChanges, WirePredicateTarget
from parallax.snapshot._inspection import (
    SnapshotInspectionError,
    is_view_loaded,
    pin_of,
    view,
)
from parallax.snapshot._inspection import edge_of as _typed_edge_of
from parallax.snapshot._publication._root import SnapshotConsistencyError
from parallax.snapshot._publication._wire import WireEntity, WireValue, wire_edge_of

__all__ = [
    "CheckedSnapshot",
    "Database",
    "NoResultFound",
    "ReadOnlyTxnContext",
    "ScopedDatabase",
    "Snapshot",
    "SnapshotConnectionError",
    "SnapshotConsistencyError",
    "SnapshotInspectionError",
    "SnapshotMaterializationError",
    "SnapshotStream",
    "TooManyResultsFound",
    "TxnContext",
    "WireChanges",
    "WireDatabaseView",
    "WireEntity",
    "WirePredicateTarget",
    "WireQuery",
    "WireTransactionView",
    "WireValue",
    "connect",
    "edge_of",
    "is_view_loaded",
    "pin_of",
    "view",
]


def edge_of(node: object) -> Edge:
    """``node``'s own milestone :class:`~parallax.core.temporal_read.Edge` — the
    finite from-instant on every axis its family declares.

    A Typed node a Snapshot read materialized, or any edit of it, shares one
    Edge derived on first inspection. A Wire node a read published, a
    diagnostic node of an invalid root included, answers equal Edges on
    repeated calls, not necessarily one object. Inspection grants no write
    authority; a caller may state the Edge's ``tx_time`` as a target write's
    ``tx_start`` condition.
    """
    # Every Wire node is a frozen ``dict`` at runtime. Dispatching on that
    # concrete base keeps a Typed node off the abstract ``WireEntity`` instance
    # check, which alone would nearly double a cached Typed inspection.
    if isinstance(node, dict):
        return wire_edge_of(node)  # pyright: ignore[reportUnknownArgumentType] - the Wire reader authenticates its own carrier
    return _typed_edge_of(node)
