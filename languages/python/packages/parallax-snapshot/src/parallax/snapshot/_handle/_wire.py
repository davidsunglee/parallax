from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from parallax.core._execution._options import OMITTED, Omitted
from parallax.core._execution._read_policy import ReadQuery
from parallax.core._execution._scope import ExecutionScope
from parallax.core._execution._transaction._attempt import ReadOnlyTxnAttempt, TxnAttempt
from parallax.core.object_query import ObjectQueryNode, deserialize
from parallax.core.object_query._fluent import ObjectQuery, typed_read_query
from parallax.snapshot._handle._read import Snapshot, wire_publication_for
from parallax.snapshot._handle._stream import DEFAULT_BATCH_SIZE, SnapshotStream
from parallax.snapshot._handle._wire_writes import (
    WireChanges,
    WirePredicateTarget,
    WirePredicateWriteAdapter,
    WireTargetWriteAdapter,
    editable_wire_data,
    wire_insert,
    wire_keyed_write,
)
from parallax.snapshot._publication._wire import WireEntity

__all__ = [
    "WireDatabaseView",
    "WireQuery",
    "WireTransactionView",
    "wire_read_query",
]

type WireQuery = ObjectQuery[Any, Any] | ObjectQueryNode | Mapping[str, object]
"""What a Wire read accepts: the canonical Object Query mapping, the canonical
node itself, or — on a class-backed model — the Typed authoring value."""


def wire_read_query(query: WireQuery) -> ReadQuery:
    """``query`` as the unresolved input the shared read gate resolves.

    Accepting three spellings adds no query semantics: the mapping goes through
    `m-object-query`'s own deserializer and a node passes as itself, while the
    Typed value stays authored exactly as ``db.find`` hands it over, so it keeps
    the Typed operand policy rather than being encoded and decoded again.
    Nothing here validates the query — the shared read gate does, after the read
    adopts its selection and before any I/O — so all three spellings meet the
    same refusals.

    It is a stable converter a read is handed rather than a step the read
    performs first: a Wire read refuses re-entry before it looks at what it was
    handed, so a mapping no deserializer could accept is refused as re-entry
    when it arrives from inside a lifecycle context, exactly as an unusable Typed
    query is.
    """
    if isinstance(query, ObjectQueryNode):
        return query
    if isinstance(query, Mapping):
        return deserialize(query)
    return typed_read_query(query)


class WireDatabaseView:
    """The Wire read interface: ``db.wire`` outside any transaction, and
    ``rtx.wire`` inside a read-only one.

    It reads exactly as the Typed reads beside it do. Standalone, as ``db.find``
    is: no transaction, read lock, or Concurrency Preference. Inside a read-only
    transaction, as ``rtx.find`` is: on that transaction's attempt and
    connection, taking no participation lock. Either way it retains no Read
    Evidence on the values it publishes, which stay stored values a
    target write can state a revision from.
    """

    __slots__ = ("_reads",)

    def __init__(self, reads: ExecutionScope | ReadOnlyTxnAttempt | TxnAttempt) -> None:
        self._reads = reads

    def find(self, query: WireQuery) -> Snapshot[WireEntity]:
        """Execute ``query`` exactly once and return its Wire Snapshot.

        Each root is a frozen :class:`~parallax.snapshot.WireEntity`
        keyed by declared member name, unwound finitely along the requested
        Include Paths, or the
        :class:`~parallax.core.read_delivery.InvalidData` record a root whose
        stored state contradicted the model publishes in its place.

        The refusal order is the Typed read's without its classless rung — no
        Wire node is an Entity Class instance, so none needs a materializer:
        re-entry, then the read begun, then the spelling it was handed captured
        and resolved under the read's selection.
        """
        return self._reads.read(
            query, convert_query=wire_read_query, build_publication=wire_publication_for
        )

    def stream(
        self, query: WireQuery, *, batch_size: int = DEFAULT_BATCH_SIZE
    ) -> SnapshotStream[WireEntity]:
        """Deliver ``query``'s roots one at a time, in the Continuation Order,
        as the scope-bound single-pass peer of :meth:`find`.

        Delivery is the verb and representation stays the namespace: every root
        this publishes arrives as the frozen
        :class:`~parallax.snapshot.WireEntity` node ``find``
        publishes for that root, one at a time instead of all of them, with no
        format argument anywhere. WHICH roots arrive is the separate claim: over
        storage the model describes they are ``find``'s roots exactly, and
        ``batch_size`` counts root positions and is a performance dial alone
        there, exactly as in the Typed namespace. :class:`SnapshotStream` states
        the one stored value outside that, for both namespaces.
        """
        return SnapshotStream(
            self._reads,
            query,
            batch_size,
            convert_query=wire_read_query,
            build_publication=wire_publication_for,
        )

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

    The method names the authority a write runs under. Every source-authorized
    verb — :meth:`amend`, :meth:`replace`, :meth:`delete`, :meth:`terminate` —
    takes a frozen Entity mapping this store published — a Wire read's result,
    or the node an insert answered for the row it opened — and infers the
    concrete Entity and the object the write addresses from it privately,
    together with the exact state a read published node observed and the
    Valid-Time instant it was read at, where a Bitemporal write starts. The node
    an insert answered observed nothing, and the write off it resolves no
    evidence at all: the buffered insert licenses it, and it starts where that
    insert was authored to. A mapping a caller built carries neither, so it is
    no source. The caller-conditioned verbs :meth:`amend_if`,
    :meth:`replace_if`, :meth:`delete_if`, and :meth:`terminate_if` address an
    object by Entity spelling and key instead, under the one revision their
    caller states.
    """

    __slots__ = ("_attempt",)

    def __init__(self, attempt: TxnAttempt) -> None:
        super().__init__(attempt)
        self._attempt = attempt

    def insert(
        self,
        entity_name: str,
        data: Mapping[str, object],
        *,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> WireEntity:
        """Buffer a Wire insert of ``data`` as a fresh ``entity_name`` row, and
        return the frozen node it opened.

        ``entity_name`` names the Entity the row opens under — required because
        an opening row has no source to infer one from — and resolves by the rule
        every write target does: the canonical spelling, or a bare local name no
        second namespace of this model shares. ``data`` is the Create
        Payload in accepted wire spellings; framework-owned members are refused
        rather than stored, since the interval bounds come from the Clock
        Strategy at flush and the version is derived.

        The returned node is the Wire peer of the instance ``tx.insert`` leaves
        its caller holding: it publishes the payload's own members in canonical
        Wire spelling and carries the insertion's authority, so a pure Wire
        caller revises the row it opened through it for the rest of the attempt,
        before and after a flush, without re-reading it. Only this node carries
        that authority: a plain copy of it, or another document of the same key,
        is no keyed source. A repeated insert of the object is refused while
        anything the insertion opened stands, whether the payload is stated again
        or the returned node is handed back, since revising the row is the amend
        and replace verbs' job; once all of it has been removed, a fresh
        insertion is admitted.

        ``valid_from`` and ``until`` bound a Bitemporal insert exactly as
        ``tx.insert`` does: omitting ``until`` opens ``[valid_from, infinity)``,
        a stated bound is a bound whatever its value — ``None`` is refused — and
        a target with no Valid Time takes neither.
        """
        return wire_insert(self._attempt, entity_name, data, valid_from=valid_from, until=until)

    def amend(
        self,
        source: WireEntity,
        changes: WireChanges,
        /,
        *,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer an amendment of the object ``source`` was read or inserted
        as: the members ``changes`` names, every other member of each
        predecessor kept.

        ``changes`` names declared members; version, temporal-axis, computed,
        read-only, and relationship members are refused statically, before the
        target Entity's Effective Concurrency Strategy or its evidence is
        consulted. Every member it names is assigned, including one whose value
        equals what the node published; ``{}`` names none and issues no DML at
        all. A primary-key entry is optional addressing data: it must name
        ``source``'s own object and is never assigned, so a key-only document
        assigns nothing. ``source`` supplies the write's authority and start
        exactly as ``tx.amend``'s does, so the method takes no condition or
        ``valid_from``; ``until`` follows :meth:`insert`'s rules.
        """
        wire_keyed_write(self._attempt, "amend", source, changes, until=until)

    def amend_if(
        self,
        entity_name: str,
        changes: WireChanges,
        /,
        *,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer an amendment of the existing ``entity_name`` object
        ``changes``'s primary-key entries name, under the one revision its
        caller states, exactly as ``tx.amend_if`` does.

        Every entry but the key is assigned, a value equal to the stored one
        included; a change set naming nothing but the key is validated and then
        dropped, with no database work at all — no existence or revision check.
        A Bitemporal amendment assigns its members to each existing interval of
        its window, every interval keeping what it does not assign, and leaves
        gaps and coverage after a scheduled termination absent.
        """
        self._attempt.target_write(
            WireTargetWriteAdapter(entity_name, changes),
            "amend",
            version=version,
            tx_start=tx_start,
            valid_from=valid_from,
            until=until,
        )

    def replace(
        self,
        source: WireEntity,
        data: Mapping[str, object] | Omitted = OMITTED,
        /,
        *,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a complete replacement of the object ``source`` was read or
        inserted as, exactly as ``tx.replace`` does.

        ``data`` is the object's whole writable state in accepted wire
        spellings and stands alone: an omitted nullable member is written
        empty, an omitted ``many`` the empty collection, an omitted required
        member is refused, a framework-owned member is refused rather than
        stored, and nothing is filled from ``source`` — ``{}`` included. A
        primary-key entry is optional addressing data naming ``source``'s own
        object. Omitting ``data`` replaces with the writable state ``source``
        published. ``source`` supplies the write's authority and start, so the
        method takes no condition or ``valid_from``; ``until`` follows
        :meth:`insert`'s rules.
        """
        wire_keyed_write(self._attempt, "replace", source, data, until=until)

    def replace_if(
        self,
        target: str | WireEntity,
        data: Mapping[str, object] | Omitted = OMITTED,
        /,
        *,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a complete replacement of an existing object under the one
        revision its caller states, exactly as ``tx.replace_if`` does.

        Handed an Entity spelling, ``data`` is required and its primary-key
        entries name the object; it is completed as :meth:`replace` completes
        it. Handed a node Parallax published instead — current or historical —
        the node's own Entity, key, and published writable state are the
        replacement, and ``data`` is not taken. Nothing the node carries stands
        in for the revision, and its provenance licenses nothing.
        """
        self._attempt.target_write(
            WireTargetWriteAdapter(target, data),
            "replace",
            version=version,
            tx_start=tx_start,
            valid_from=valid_from,
            until=until,
        )

    def delete_if(
        self,
        entity_name: str,
        key: Mapping[str, object],
        /,
        *,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a deletion of the existing ``entity_name`` object ``key``'s
        primary-key entries name, under the one revision its caller states,
        exactly as ``tx.delete_if`` does. ``key`` states the primary key alone;
        any other member is refused."""
        self._attempt.target_write(
            WireTargetWriteAdapter(entity_name, key), "delete", version=version, tx_start=tx_start
        )

    def terminate_if(
        self,
        entity_name: str,
        key: Mapping[str, object],
        /,
        *,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a termination of the existing temporal ``entity_name`` object
        ``key``'s primary-key entries name, under the one revision its caller
        states, exactly as ``tx.terminate_if`` does. ``key`` states the primary
        key alone; any other member is refused."""
        self._attempt.target_write(
            WireTargetWriteAdapter(entity_name, key),
            "terminate",
            version=version,
            tx_start=tx_start,
            valid_from=valid_from,
            until=until,
        )

    def editable_data(self, source: WireEntity) -> dict[str, object]:
        """Independently mutable authoring data copied from ``source``, a node
        Parallax published: its primary key and every writable member it
        published, in their Wire spellings, in fresh mappings and lists.

        Relationships, framework-owned revision and temporal members, derived
        variant metadata, and read-only members other than the key are left
        out. The result is ordinary data for any verb — edited and passed to
        :meth:`replace` or :meth:`replace_if`, or given a new or removed key
        and passed to :meth:`insert` — and carries no authority: ``source``
        stays the keyed carrier, unconsumed and unrenewed. It records no edit
        history, so passing all of it to :meth:`amend` assigns every member it
        holds. Nothing is queried, completed, generated, or recovered beyond
        what ``source`` published.
        """
        return editable_wire_data(self._attempt, source)

    def delete(self, observed: WireEntity) -> None:
        """Buffer a Wire ``delete`` of the row ``observed`` came from, keyed off
        its own object.

        A source pinned at a finite Transaction-Time instant is read-only and
        raises before any buffering, exactly as every other keyed verb's is.

        ``delete`` physically removes the row and carries no temporal meaning, so
        a target that milestones its rows refuses it at this call and names
        :meth:`terminate`, which closes the row's history instead."""
        wire_keyed_write(self._attempt, "delete", observed)

    def terminate(self, observed: WireEntity, *, until: dt.datetime | Omitted = OMITTED) -> None:
        """Buffer a Wire terminate of the coverage ``observed`` came from, exactly
        as ``tx.terminate`` does: a Transaction-Time-Only milestone closes, and a
        Bitemporal target's current coverage ends from where ``observed`` was
        read, through infinity or up to the exclusive ``until``."""
        wire_keyed_write(self._attempt, "terminate", observed, until=until)

    def amend_where(self, target: WirePredicateTarget, changes: WireChanges, /) -> int:
        """Amend every row ``target`` selects now, in one readless statement,
        exactly as ``tx.amend_where`` does: the members ``changes`` names,
        every other member kept, answering how many rows it matched.

        ``target`` is a Typed Object Query, held to ``tx.amend_where``'s rules
        and kept as authored, or the canonical ``{entity, predicate}``
        selection document. ``changes`` lowers to the same canonical assignment
        algebra ``tx.amend_where``'s ``.set(...)`` spelling does; ``{}`` is the
        empty amendment, judged and then answered ``0``, so no statement
        runs."""
        return self._attempt.predicate_write(WirePredicateWriteAdapter(target, changes), "amend")

    def replace_where(
        self, target: WirePredicateTarget, data: Mapping[str, object] | WireEntity, /
    ) -> int:
        """Replace every row ``target`` selects now, in one readless
        statement, exactly as ``tx.replace_where`` does, under
        :meth:`amend_where`'s target and count rules.

        ``data`` is the selected objects' whole writable state in accepted wire
        spellings, completed as :meth:`replace` completes it, a read-only
        member or a name the Entity does not declare refused rather than
        stored. Handed a node Parallax
        published instead, the node's writable state is the replacement, and
        the node must be one of the selected Entity. A primary-key entry
        addresses nothing, since ``target`` selects the rows, so it is accepted
        and never written."""
        return self._attempt.predicate_write(WirePredicateWriteAdapter(target, data), "replace")

    def delete_where(self, target: WirePredicateTarget, /) -> int:
        """Delete every row ``target`` selects now, in one readless statement,
        under :meth:`amend_where`'s target rules, answering how many rows it
        deleted.

        The sanctioned spelling for unconditional intent: it says outright that
        the caller means to remove whatever matches, rather than arriving there
        by building a value nothing was read into.
        """
        return self._attempt.predicate_write(WirePredicateWriteAdapter(target), "delete")
