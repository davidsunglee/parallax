from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from parallax.core.execution._attempt import Attempt
from parallax.core.execution._keyed_writes import target_condition, window_mutation
from parallax.core.execution._options import OMITTED, Omitted
from parallax.core.execution._scope import ExecutionScope
from parallax.core.object_query import ObjectQueryNode, deserialize
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.snapshot._handle._read import Snapshot, wire_publication_for
from parallax.snapshot._handle._stream import SnapshotStream
from parallax.snapshot._handle._wire_writes import (
    WireChanges,
    WirePredicateTarget,
    editable_wire_data,
    wire_insert,
    wire_keyed_write,
    wire_predicate_write,
    wire_target_write,
)
from parallax.snapshot._publication._wire import WireEntity

__all__ = [
    "WireDatabaseView",
    "WireQuery",
    "WireTransactionView",
    "wire_query_node",
]

type WireQuery = ObjectQuery[Any, Any] | ObjectQueryNode | Mapping[str, object]
"""What a Wire read accepts: the canonical Object Query mapping, the canonical
node itself, or — on a class-backed model — the Typed authoring value."""


def wire_query_node(query: WireQuery) -> ObjectQueryNode:
    """``query`` as the one canonical Object Query node every read lowers through.

    Accepting three spellings adds no query semantics: the mapping goes through
    `m-object-query`'s own deserializer, the Typed value through the same
    accessor ``db.find`` uses, and a node passes as itself. Nothing here
    validates the query — the shared read gate does, after this resolution and
    before any I/O — so all three spellings meet the same refusals.

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
    return object_query_node(query)


class WireDatabaseView:
    """``db.wire`` — the Wire read interface outside any transaction.

    Non-transactional exactly as ``db.find`` is: no read lock, no Concurrency
    Preference, and no participation stamped on the values it publishes — whose
    own retained evidence an effective-Optimistic write may still settle against.
    """

    __slots__ = ("_reads",)

    def __init__(self, reads: ExecutionScope | Attempt) -> None:
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
        re-entry, then the read begun, then the spelling it was handed lowered
        to the canonical node.
        """
        return self._reads.read(
            query, convert_query=wire_query_node, build_publication=wire_publication_for
        )

    def stream(self, query: WireQuery, *, batch_size: int = 1000) -> SnapshotStream[WireEntity]:
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
            convert_query=wire_query_node,
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
    no source. The caller-conditioned verbs :meth:`amend_if` and
    :meth:`replace_if` address an object by Entity spelling and key instead,
    under the one condition their caller states.
    """

    __slots__ = ("_attempt",)

    def __init__(self, attempt: Attempt) -> None:
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
        mutation, bound = window_mutation("insert", "insertUntil", until)
        return wire_insert(
            self._attempt,
            entity_name,
            data,
            mutation=mutation,
            valid_from=valid_from,
            until=bound,
        )

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
        mutation, bound = window_mutation("amend", "amendUntil", until)
        wire_keyed_write(self._attempt, mutation, source, changes, until=bound)

    def amend_if(
        self,
        entity_name: str,
        changes: WireChanges,
        /,
        *,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
        unversioned: bool | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer an amendment of the existing ``entity_name`` object
        ``changes``'s primary-key entries name, under the one condition its
        caller states, exactly as ``tx.amend_if`` does.

        Every entry but the key is assigned, a value equal to the stored one
        included; a change set naming nothing but the key is validated and then
        dropped, with no database work at all — no existence or revision check.
        A Bitemporal amendment assigns its members to each existing interval of
        its window, every interval keeping what it does not assign, and leaves
        gaps and coverage after a scheduled termination absent.
        """
        mutation, bound = window_mutation("amend", "amendUntil", until)
        condition = target_condition(version=version, tx_start=tx_start, unversioned=unversioned)
        wire_target_write(
            self._attempt,
            mutation,
            entity_name,
            changes,
            condition,
            valid_from=valid_from,
            until=bound,
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
        mutation, bound = window_mutation("replace", "replaceUntil", until)
        wire_keyed_write(self._attempt, mutation, source, data, until=bound)

    def replace_if(
        self,
        target: str | WireEntity,
        data: Mapping[str, object] | Omitted = OMITTED,
        /,
        *,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
        unversioned: bool | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a complete replacement of an existing object under the one
        condition its caller states, exactly as ``tx.replace_if`` does.

        Handed an Entity spelling, ``data`` is required and its primary-key
        entries name the object; it is completed as :meth:`replace` completes
        it. Handed a node Parallax published instead — current or historical —
        the node's own Entity, key, and published writable state are the
        replacement, and ``data`` is not taken. Nothing the node carries stands
        in for the condition, and its provenance licenses nothing.
        """
        mutation, bound = window_mutation("replace", "replaceUntil", until)
        condition = target_condition(version=version, tx_start=tx_start, unversioned=unversioned)
        wire_target_write(
            self._attempt,
            mutation,
            target,
            data,
            condition,
            valid_from=valid_from,
            until=bound,
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
        mutation, bound = window_mutation("terminate", "terminateUntil", until)
        wire_keyed_write(self._attempt, mutation, observed, until=bound)

    def amend_where(
        self,
        target: WirePredicateTarget,
        changes: WireChanges,
        *,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """A predicate-selected Wire amendment over ``target`` — the canonical
        ``{entity, predicate}`` selection, never an Object Query. Readless (one
        statement) for an unversioned Non-Temporal target; a versioned or temporal
        target materializes to one observation-backed per-row write. A Bitemporal
        target requires ``valid_from``, and both bounds follow :meth:`insert`'s
        rules.

        ``changes`` names at least one member. It lowers to the same canonical
        assignment algebra ``tx.amend_where``'s ``.set(...)`` spelling does, and
        that algebra's list is non-empty, so ``{}`` is refused here rather than
        being the no-op it is for a keyed amendment — which addresses one row a
        caller already holds, where a selection holds none."""
        mutation, bound = window_mutation("amend", "amendUntil", until)
        wire_predicate_write(
            self._attempt,
            mutation,
            target,
            changes,
            valid_from=valid_from,
            until=bound,
        )

    def delete_where(self, target: WirePredicateTarget) -> None:
        """A predicate-selected Wire ``delete`` over a NON-temporal ``target``.

        The sanctioned spelling for unconditional intent: it says outright that
        the caller means to remove whatever matches, rather than arriving there
        by building a value nothing was read into.
        """
        wire_predicate_write(self._attempt, "delete", target)

    def terminate_where(
        self,
        target: WirePredicateTarget,
        *,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """A predicate-selected Wire terminate over a TEMPORAL ``target``:
        Transaction-Time-Only takes no ``valid_from``; Bitemporal requires it, and
        both bounds follow :meth:`insert`'s rules."""
        mutation, bound = window_mutation("terminate", "terminateUntil", until)
        wire_predicate_write(
            self._attempt,
            mutation,
            target,
            valid_from=valid_from,
            until=bound,
        )
