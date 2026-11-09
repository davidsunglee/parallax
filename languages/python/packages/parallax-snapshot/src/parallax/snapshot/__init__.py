from parallax.core.temporal_read import Edge, Pin
from parallax.core.wire import WireValue
from parallax.snapshot._handle._database import Database, ScopedDatabase, connect
from parallax.snapshot._handle._errors import SnapshotMaterializationError
from parallax.snapshot._handle._read import (
    CheckedSnapshot,
    SharingScope,
    Snapshot,
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
    required_pin,
    typed_edge_of,
    typed_pin_of,
    view,
)
from parallax.snapshot._publication._graph_view import SnapshotConsistencyError
from parallax.snapshot._publication._wire import (
    WireEntity,
    required_wire_provenance,
    wire_edge_of,
)

__all__ = [
    "CheckedSnapshot",
    "Database",
    "ReadOnlyTxnContext",
    "ScopedDatabase",
    "SharingScope",
    "Snapshot",
    "SnapshotConsistencyError",
    "SnapshotInspectionError",
    "SnapshotMaterializationError",
    "SnapshotStream",
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

    A Typed node a Snapshot read materialized and every edit of it answer equal
    Edges, however often they are inspected. A Wire node a read published, a
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
    return typed_edge_of(node)


def pin_of(node: object) -> Pin:
    """The :class:`~parallax.core.temporal_read.Pin` retained for the read that
    published ``node`` — where the read stood, not where ``node`` itself starts,
    which is :func:`edge_of`'s answer.

    A read-published Typed or Wire temporal node answers, a diagnostic node
    inside :class:`~parallax.core.read_delivery.InvalidData` included. An included
    node shares its root's Pin, and each milestone-set root holds its own
    milestone's instants, or the empty ``Pin()`` where a start did not decode.
    Inspection performs no I/O and grants no write authority.

    Raises :class:`SnapshotInspectionError`: ``snapshot-pin-unavailable`` for a
    non-temporal node, and ``snapshot-node-required`` for anything no read
    published, including an insert answer, a plain mapping or copy, a nested
    Value Object mapping, and the ``InvalidData`` wrapper itself.
    """
    # The same dispatch as ``edge_of``, for the same reason.
    if isinstance(node, dict):
        return required_pin(required_wire_provenance(node, "pin_of"))  # pyright: ignore[reportUnknownArgumentType] - the Wire reader authenticates its own carrier
    return typed_pin_of(node)
