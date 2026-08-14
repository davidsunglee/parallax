"""``parallax.snapshot.handle._wire`` — the Wire read interface (`m-snapshot-read`).

``db.wire`` and ``tx.wire`` are lightweight VIEWS over the same connected model
and adapter their Typed peers use, never separate connections or transaction
modes. A view holds the one entry point its owner already composed — read gate,
force-flush, locking, evidence retention, trace bracket — so a Wire read and a
Typed read differ in nothing but which materializer runs once execution has
finished. That is why the interfaces are two objects rather than one ``format=``
argument: capability is what a caller holds, not a value it passes.

Both views accept the canonical Object Query mapping and, on a class-backed
model, the Typed authoring value directly. A descriptor-backed caller therefore
passes the mapping and never imports an Entity Class, an Entity Identity, or an
Object Query node type; a class-backed caller passes the query it already built
and needs no public serialization step. Both lower to the SAME canonical node
before the shared read gate runs, so neither spelling can reach a different
executor.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from parallax.core.object_query import ObjectQueryNode, deserialize
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.snapshot.handle._read import Snapshot
from parallax.snapshot.materialize import WireEntity

__all__ = [
    "WireDatabaseView",
    "WireQuery",
    "WireTransactionView",
    "wire_query_node",
]

type WireQuery = ObjectQuery[Any, Any] | ObjectQueryNode | Mapping[str, object]
"""What a Wire read accepts: the canonical Object Query mapping, the canonical
node itself, or — on a class-backed model — the Typed authoring value."""

type _WireFind = Callable[[ObjectQueryNode], Snapshot[WireEntity]]


def wire_query_node(query: WireQuery) -> ObjectQueryNode:
    """``query`` as the one canonical Object Query node every read lowers through.

    Accepting three spellings adds no query semantics: the mapping goes through
    `m-object-query`'s own deserializer, the Typed value through the same
    accessor ``db.find`` uses, and a node passes as itself. Nothing here
    validates the query — the shared read gate does, after this resolution and
    before any I/O — so all three spellings meet the same refusals.
    """
    if isinstance(query, ObjectQueryNode):
        return query
    if isinstance(query, Mapping):
        return deserialize(query)
    return object_query_node(query)


class WireDatabaseView:
    """``db.wire`` — the Wire read interface outside any transaction.

    Non-transactional exactly as ``db.find`` is: no read lock, no Concurrency
    Preference, and no observation record.
    """

    __slots__ = ("_find",)

    def __init__(self, find: _WireFind) -> None:
        self._find = find

    def find(self, query: WireQuery) -> Snapshot[WireEntity]:
        """Execute ``query`` exactly once and return its Wire Snapshot.

        Each root is a frozen :class:`~parallax.snapshot.materialize.WireEntity`
        keyed by declared member name, unwound finitely along the requested
        Include Paths, or the
        :class:`~parallax.snapshot.materialize.InvalidData` record a root whose
        stored state contradicted the model publishes in its place.
        """
        return self._find(wire_query_node(query))

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


class WireTransactionView(WireDatabaseView):
    """``tx.wire`` — the Wire read interface inside a transaction.

    A view over the SAME unit of work, evidence retention, locking, and Execution
    Log the Typed transaction interface uses, so a Wire read participates in
    exactly the four ways ``tx.find`` does: it force-flushes pending writes
    first, renders the read-lock suffix each materialized level's own target
    Entity calls for, retains onto each published node what a later write settles
    against, and appends its Read Trace to the active attempt.
    """

    __slots__ = ()
