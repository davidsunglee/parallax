"""``parallax.snapshot.handle._wire`` — the Wire interface (`m-snapshot-read`).

``db.wire`` and ``tx.wire`` are lightweight VIEWS over the same connected model
and adapter their Typed peers use, never separate connections or transaction
modes. A view holds the one entry point its owner already composed — read gate,
force-flush, locking, evidence retention, activity bracket, unit of work,
coalescing — so a Wire call and a Typed call differ in nothing but the
representation their values are stated in. That is why the interfaces are two
objects rather than one ``format=`` argument: capability is what a caller holds,
not a value it passes.

Both views accept the canonical Object Query mapping and, on a class-backed
model, the Typed authoring value directly. A descriptor-backed caller therefore
passes the mapping and never imports an Entity Class, an Entity Identity, or an
Object Query node type; a class-backed caller passes the query it already built
and needs no public serialization step. Both lower to the SAME canonical node
before the shared read gate runs, so neither spelling can reach a different
executor.

``tx.wire`` additionally carries the complete keyed and predicate WRITE families.
The verbs here are the developer surface — signatures, defaults, and the
temporal spellings; every judgement they run lives in
:mod:`parallax.snapshot.handle._wire_writes`, which shares the evidence resolver,
the claim algebra, the instruction IR, and the buffer with the Typed verbs. There
is no ``tx.write(instruction)``, no flat ``wire_*`` method, and no observation
address in any signature.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from typing import Any

from parallax.core.object_query import ObjectQueryNode, deserialize
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.snapshot.handle._read import Snapshot
from parallax.snapshot.handle._wire_writes import (
    WireChanges,
    WirePredicateTarget,
    WireWriteLane,
    wire_insert,
    wire_keyed_write,
    wire_predicate_write,
)
from parallax.snapshot.materialize import WireEntity

__all__ = [
    "WireChanges",
    "WireDatabaseView",
    "WirePredicateTarget",
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
    Preference, and no participation stamped on the values it publishes — whose
    own retained evidence an effective-Optimistic write may still settle against.
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
    """``tx.wire`` — the Wire read AND write interface inside a transaction.

    A view over the SAME unit of work, evidence retention, locking, and
    coalescing the Typed transaction interface uses. A Wire read
    participates in exactly the four ways ``tx.find`` does: it force-flushes
    pending writes first, renders the read-lock suffix each materialized level's
    own target Entity calls for, retains onto each published node what a later
    write settles against, and opens its own Read under the active attempt
    (`m-execution-lifecycle`). A Wire write buffers into the same unit of work
    through the same instruction IR, so a Typed write and a Wire write of one
    object merge, deduplicate, and conflict by the one claim algebra rather than
    by an interface-specific rule.

    Every keyed verb but the insert family takes a frozen Entity mapping a
    Parallax Wire read published, and infers the concrete Entity and the exact
    observed state from it privately. There is no explicit-Entity
    ordinary-mapping overload: a mapping a caller built carries no evidence, and
    a verb that accepted one would be issuing a write nothing proves anything
    about.
    """

    __slots__ = ("_writes",)

    def __init__(self, find: _WireFind, writes: WireWriteLane) -> None:
        super().__init__(find)
        self._writes = writes

    def insert(
        self,
        entity_name: str,
        data: Mapping[str, object],
        *,
        valid_from: dt.datetime | None = None,
    ) -> WireEntity:
        """Buffer a Wire ``insert`` of ``data`` as a fresh ``entity_name`` row,
        and return the frozen node it opened.

        ``entity_name`` names the Entity the row opens under — required because
        an opening row has no source to infer one from — and resolves by the rule
        every write target does: the canonical spelling, or a bare local name no
        second namespace of this model shares. ``data`` is the Create
        Payload in accepted wire spellings; framework-owned members are refused
        rather than stored, since the interval bounds come from the Clock
        Strategy at flush and the version is derived.

        The returned node is the Wire peer of the instance ``tx.insert`` leaves
        its caller holding: it publishes the payload's own members in canonical
        Wire spelling and is a keyed source, so a pure Wire caller can revise the
        row it just opened without re-reading it — which it could not do anyway,
        since a participating read force-flushes and an insert-then-delete pair
        is required to emit no DML at all. The pair coalesces through the same
        read-your-own-writes ledger a Typed insert records into.

        ``valid_from`` is the plain Bitemporal insert's own Valid-Time instant —
        the open rectangle ``[valid_from, infinity)`` — and mirrors ``tx.insert``
        exactly: a Transaction-Time-Only or non-temporal target takes none.
        """
        return wire_insert(
            self._writes, entity_name, data, mutation="insert", valid_from=valid_from
        )

    def insert_until(
        self,
        entity_name: str,
        data: Mapping[str, object],
        *,
        valid_from: dt.datetime,
        until: dt.datetime,
    ) -> WireEntity:
        """Buffer a Valid-Time-bounded Wire ``insertUntil``: one bitemporal
        rectangle bounded to ``[valid_from, until)`` with no prior row to close
        (`m-bitemp-write`), returning the frozen node it opened as
        :meth:`insert` does. A window that does not satisfy
        ``valid_from < until`` raises at THIS call, before any buffering."""
        return wire_insert(
            self._writes,
            entity_name,
            data,
            mutation="insertUntil",
            valid_from=valid_from,
            until=until,
        )

    def update(
        self,
        observed: WireEntity,
        changes: WireChanges,
        *,
        valid_from: dt.datetime | None = None,
    ) -> None:
        """Buffer a Wire ``update`` of the row ``observed`` came from.

        ``changes`` names declared members only; identity, optimistic-version,
        temporal-axis, computed, read-only, and relationship members are refused
        statically, before the target Entity's Effective Concurrency Strategy or
        its evidence is consulted. A member whose authored value already equals
        what ``observed`` published is a restoration rather than an assignment,
        so a change set that restores everything it names issues no DML at all —
        the same zero-round-trip no-op an empty Typed effective change set is.

        ``valid_from`` is the plain Bitemporal correction's own Valid-Time
        instant; a Transaction-Time-Only or non-temporal target takes none.
        """
        wire_keyed_write(self._writes, "update", observed, changes, valid_from=valid_from)

    def delete(self, observed: WireEntity) -> None:
        """Buffer a Wire ``delete`` of the row ``observed`` came from, keyed off
        its own object.

        A source pinned at a finite Transaction-Time instant is read-only and
        raises before any buffering, exactly as every other keyed verb's is.
        """
        wire_keyed_write(self._writes, "delete", observed)

    def terminate(self, observed: WireEntity, *, valid_from: dt.datetime | None = None) -> None:
        """Buffer a Wire ``terminate``: close the milestone ``observed`` came
        from (the temporal delete-equivalent). Transaction-Time-Only takes no
        ``valid_from``; Bitemporal requires it."""
        wire_keyed_write(self._writes, "terminate", observed, valid_from=valid_from)

    def update_until(
        self,
        observed: WireEntity,
        changes: WireChanges,
        *,
        valid_from: dt.datetime,
        until: dt.datetime,
    ) -> None:
        """Buffer a Valid-Time-bounded Wire ``updateUntil`` of the row
        ``observed`` came from, bounded to ``[valid_from, until)`` (`m-bitemp-write`
        "The rectangle split") — bitemporal-only. The window is validated at THIS
        call, before the restoration/no-op rule :meth:`update` states is
        weighed."""
        wire_keyed_write(
            self._writes, "updateUntil", observed, changes, valid_from=valid_from, until=until
        )

    def terminate_until(
        self, observed: WireEntity, *, valid_from: dt.datetime, until: dt.datetime
    ) -> None:
        """Buffer a Valid-Time-bounded Wire ``terminateUntil``: close the single
        Valid-Time window ``[valid_from, until)`` on the milestone ``observed``
        came from (`m-bitemp-write`) — bitemporal-only."""
        wire_keyed_write(
            self._writes, "terminateUntil", observed, valid_from=valid_from, until=until
        )

    def update_where(
        self,
        target: WirePredicateTarget,
        changes: WireChanges,
        *,
        valid_from: dt.datetime | None = None,
    ) -> None:
        """A predicate-selected Wire ``update`` over ``target`` — the canonical
        ``{entity, predicate}`` selection, never an Object Query. Readless (one
        statement) for an unversioned Non-Temporal target; a versioned or temporal
        target materializes to one observation-backed per-row write.

        ``changes`` names at least one member. It lowers to the same canonical
        assignment algebra ``tx.update_where``'s ``.set(...)`` spelling does, and
        that algebra's list is non-empty, so ``{}`` is refused here rather than
        being the no-op it is for a keyed update — which has one row's published
        values to be a no-op against, and a selection has none."""
        wire_predicate_write(self._writes, "update", target, changes, valid_from=valid_from)

    def delete_where(self, target: WirePredicateTarget) -> None:
        """A predicate-selected Wire ``delete`` over a NON-temporal ``target``.

        The sanctioned spelling for unconditional intent: it says outright that
        the caller means to remove whatever matches, rather than arriving there
        by building a value nothing was read into.
        """
        wire_predicate_write(self._writes, "delete", target)

    def terminate_where(
        self, target: WirePredicateTarget, *, valid_from: dt.datetime | None = None
    ) -> None:
        """A predicate-selected Wire ``terminate`` over a TEMPORAL ``target``:
        Transaction-Time-Only takes no ``valid_from``; Bitemporal requires it."""
        wire_predicate_write(self._writes, "terminate", target, valid_from=valid_from)

    def update_until_where(
        self,
        target: WirePredicateTarget,
        changes: WireChanges,
        *,
        valid_from: dt.datetime,
        until: dt.datetime,
    ) -> None:
        """A predicate-selected, Valid-Time-bounded Wire ``updateUntil`` over a
        Bitemporal ``target``: always materializes to a close plus
        head/middle/tail. ``changes`` names at least one member, for
        :meth:`update_where`'s reason."""
        wire_predicate_write(
            self._writes, "updateUntil", target, changes, valid_from=valid_from, until=until
        )

    def terminate_until_where(
        self, target: WirePredicateTarget, *, valid_from: dt.datetime, until: dt.datetime
    ) -> None:
        """A predicate-selected, Valid-Time-bounded Wire ``terminateUntil`` over a
        Bitemporal ``target``: always materializes to a close plus head/tail."""
        wire_predicate_write(
            self._writes, "terminateUntil", target, valid_from=valid_from, until=until
        )
