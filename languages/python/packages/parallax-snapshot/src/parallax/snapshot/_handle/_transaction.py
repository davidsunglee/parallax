from __future__ import annotations

import datetime as dt
from typing import Any

from parallax.core._execution._keyed_writes import window_mutation
from parallax.core._execution._options import OMITTED, Omitted, ReadOnlyTxnOptions, TxnOptions
from parallax.core._execution._transaction._attempt import ReadOnlyTxnAttempt, TxnAttempt
from parallax.core.entity import AttributeAssignment, EntityRowCodec
from parallax.core.entity import Entity as EntityBase
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, typed_read_query
from parallax.core.read_delivery import RowsResult
from parallax.snapshot._handle._read import Snapshot, typed_publication_for
from parallax.snapshot._handle._stream import SnapshotStream
from parallax.snapshot._handle._typed_writes import (
    TypedInstanceTargetWriteAdapter,
    TypedKeyedInsertSource,
    TypedKeyedWriteSource,
    TypedKeyTargetWriteAdapter,
    TypedPredicateWriteAdapter,
)
from parallax.snapshot._handle._wire import WireDatabaseView, WireTransactionView

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot._inspection import bind_insertion

__all__ = ["ReadOnlyTxnContext", "TxnContext", "read_only_context_for", "transaction_for"]


class TxnContext:
    """The writable transaction context handed to a ``db.transact`` callback.

    A facade over one transaction attempt: its unit of work, its connection, and
    the selection it adopted.
    The method names the authority a write runs under. The source-authorized
    verbs take a value this store published or an insertion opened:
    :meth:`amend` its edits or explicit assignments, :meth:`replace` its
    complete writable state, :meth:`delete` and :meth:`terminate` its object.
    :meth:`insert` opens a full instance (the Create Payload). The
    caller-conditioned verbs :meth:`amend_if`, :meth:`replace_if`,
    :meth:`delete_if`, and :meth:`terminate_if` address an object themselves
    under the one revision their caller states, never falling back on a
    source's authority. :meth:`find` runs a participating
    read and returns ``Snapshot[T]``: force-flush + the lock suffix each
    materialized level's own target Entity calls for, otherwise identical to
    :meth:`ScopedDatabase.find`. The predicate-selected ``_where`` verb family
    — :meth:`amend_where`, :meth:`replace_where`, and :meth:`delete_where` —
    writes every row a
    mutation-compatible Object Query selects in one readless statement over an
    unversioned, non-temporal target, executed at the call after everything
    buffered before it, and answers how many rows that statement affected; it
    takes no window, and preparation refuses every other target (ADR 0075).
    Every windowed verb selects its bounded form with keyword-only ``until``,
    and a stated ``valid_from`` or ``until`` of ``None`` is refused rather than
    read as omission. A reference used after its attempt ended raises
    ``EscapedTransactionError``: the attempt's lifetime fences every verb.

    :attr:`wire` is the Wire read AND write interface over this same transaction
    — a view, not a second lifecycle, so a Wire read participates exactly as
    :meth:`find` does and a Wire write buffers exactly as the keyed verbs here
    do.

    :meth:`read_rows` is the values lane over this same transaction — a
    first-party row-form read, not a third public result format. There is no
    write peer of it: every write, first-party callers included, is stated
    through the keyed, predicate, and target verbs, Typed or Wire — an
    existing row addressed by a value this store published, from a read or from
    the insert that opened the row, a fresh row by the payload an insert opens it
    with, a set by a selection plus its assignments, and an existing object by
    its key under the revision its caller states.
    """

    __slots__ = ("_attempt", "_codec")

    def __init__(self, attempt: TxnAttempt, codec: EntityRowCodec) -> None:
        # The attempt is this transaction's every read and write: its reads
        # participate in its unit of work on its connection, its keyed,
        # predicate, and target verbs admit into that unit of work,
        # and its own installed lifecycle is what makes "the originating Handle
        # or Transaction" one re-entry refusal rather than two. The codec is the
        # adopted selection's, which every Typed verb derives its rows through.
        self._attempt = attempt
        self._codec = codec

    @property
    def edition(self) -> str:
        """The Model Edition this attempt adopted before its boundary opened.

        Retained for the attempt's life: a publication landing while the
        callback runs changes nothing here, and a retried callback receives a
        new transaction that may report another edition.
        """
        return self._attempt.edition

    @property
    def options(self) -> TxnOptions:
        """The resolved options this transaction's invocation runs under: each
        explicit ``db.transact`` keyword, else the Database Root's default.

        One record for the whole invocation, so every retried attempt and every
        joining call reads the same values; a joining call's explicit keyword is
        compared against exactly this.
        """
        return self._attempt.options

    def insert(
        self,
        instance: EntityBase,
        *,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a keyed insert of a full instance (the Create Payload,
        the Python binding): every member the instance actually SET. A framework-owned
        member is never among them: the interval bounds (``in_z``/``out_z``,
        bitemporal ``from_z``/``thru_z``) are stamped at flush from the Clock
        Strategy and the version is derived, so the Entity constructor refuses a
        caller-authored one and the row carries none.

        The admitted instance carries the insertion's authority from then on, and
        so does every value derived from it afterwards by ``edit``: through them
        the amend, replace, and terminate verbs revise what the insert opened for the rest
        of the attempt, starting at ``valid_from``, before and after a flush. A
        value derived before the insert, or another instance of the same key,
        carries none. The authority is private to the instance — not a member,
        not serialized — and ends with the attempt.

        An object whose insertion still stands is not opened twice: a repeated
        insert of it — the same instance again, or another instance of the same
        primary key, through either interface — is refused at the verb
        (:class:`~parallax.core.execution.KeyedWriteValueError`,
        ``write-value-already-stored``) rather than left for the database to
        refuse at commit. Once everything the insertion opened has been removed,
        or a pending write removes it, the object may be inserted again: the new
        insertion executes after that removal, and grants the instance it takes
        a fresh authority, which no earlier draft shares.

        ``valid_from`` is a Bitemporal insert's Valid-Time start; a
        Transaction-Time-Only or non-temporal target takes none. ``until`` bounds
        a Bitemporal insert to ``[valid_from, until)``; omitting it opens
        ``[valid_from, infinity)``. A stated bound is a bound whatever its
        value — ``None`` is refused rather than read as omission — and a target
        with no Valid Time refuses one outright. The window is judged at THIS
        call, before any buffering. Both bounds come from these arguments, never
        from instance fields: an As-Of Axis endpoint is framework-owned."""
        mutation, bound = window_mutation("insert", "insertUntil", until)
        opened = self._attempt.keyed_insert(
            TypedKeyedInsertSource(instance, self._codec),
            mutation,
            valid_from=valid_from,
            until=bound,
        )
        bind_insertion(instance, opened.authority)

    def amend[E: EntityBase](
        self,
        source: E,
        *assignments: AttributeAssignment[E],
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer an amendment of the object ``source`` was read or inserted
        as: the members it assigns, every other member of each predecessor
        kept.

        Its members are either everything ``source``'s edit chain touched, at
        the value each now holds, or exactly the ``Attr.set(...)``
        ``assignments`` given beside an unedited ``source`` — never both, and
        never a diff inferred from either. Each is literal: a member set back
        to, or assigned, the value it already holds is still assigned. An
        amendment assigning nothing buffers nothing and issues no statement.
        An explicit assignment names a member ``source``'s Entity declares or
        inherits, once, and its reference and value are judged before
        anything is buffered.

        ``source`` supplies the write's authority, and the method takes no
        condition of its own: a value no read of this store produced is
        refused (:class:`~parallax.core.execution.KeyedWriteValueError`,
        ``write-value-not-stored``) unless THIS transaction admitted its insert.
        The version column, if any, is never authored here — it is
        framework-owned end to end (`m-opt-lock`; ADR 0013): the write seam
        derives its advance from the observation the source itself retained.

        A Bitemporal amendment starts where its source was read — the source's
        finite Valid-Time pin, or the start an insert this transaction admitted
        was authored with — and applies to every interval of the object's
        current coverage from there: through infinity when ``until`` is
        omitted, or up to the exclusive ``until``. Each interval keeps its own
        unassigned members, and gaps stay gaps (`m-temporal-write`). A source
        read at Valid-Time ``LATEST`` names no start and is refused. ``until``
        follows :meth:`insert`'s rules, and is judged at THIS call even when
        nothing is assigned."""
        mutation, bound = window_mutation("amend", "amendUntil", until)
        self._attempt.keyed_write(
            TypedKeyedWriteSource(source, self._codec, assignments), mutation, until=bound
        )

    def amend_if[E: EntityBase](
        self,
        entity: type[E],
        *assignments: AttributeAssignment[E],
        key: object,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer an amendment of the existing object of concrete ``entity``
        that ``key`` names, under the one revision its caller states.

        ``key`` is the object's scalar primary-key value, whatever the key
        Attribute is called. ``assignments`` are ``Attr.set(...)`` calls naming
        members ``entity`` declares or inherits, each at most once and each
        assigned even when it equals the stored value; assigning nothing is
        validated and then dropped, with no database work at all. No instance,
        read, or source is consulted.

        Exactly one revision is required, and it must be the one ``entity``
        has: ``version``, the version of a versioned Entity its caller last
        observed, or ``tx_start``, the Transaction-Time start of the milestone a
        temporal Entity's write starts from. A missing, extra, ``None``, or
        inapplicable revision is refused, never replaced by a source's
        authority, and an Entity with neither is refused outright: no write
        could detect a change to it since its caller's query, so it is written
        through a read of this transaction instead. A retried callback states
        the same revision again. Under the Optimistic strategy the stated
        revision gates the write, and a row no longer standing at it raises
        :class:`~parallax.core.unit_work.WritePreconditionError` at flush, which
        no retry repeats. Under Locking the stored row is read under the shared
        lock now — reading nothing it already holds, and executing no pending
        write — and a mismatch raises that error here. An object this
        transaction inserted is refused (``write-evidence-inserted``).

        A Bitemporal amendment requires ``valid_from`` and current coverage
        there, and applies to every interval of its window, each keeping what
        it does not assign; gaps and coverage after a scheduled termination
        stay absent. ``valid_from`` and ``until`` follow :meth:`insert`'s
        rules."""
        self._attempt.target_write(
            TypedKeyTargetWriteAdapter(entity, assignments, key),
            "amend",
            version=version,
            tx_start=tx_start,
            valid_from=valid_from,
            until=until,
        )

    def replace(self, source: EntityBase, *, until: dt.datetime | Omitted = OMITTED) -> None:
        """Buffer a complete replacement of the object ``source`` was read or
        inserted as, with ``source``'s whole writable state.

        Every writable member ``source`` holds is written — edited or not, a
        value equal to the stored one included — an omitted nullable member is
        written empty and an omitted ``many`` the empty collection, and an
        omitted required member is refused; nothing is carried forward from the
        state it replaces. Framework-owned, read-only non-key, and relationship
        members are never part of it.

        ``source`` supplies the write's authority exactly as for
        :meth:`amend`, which is also where a Bitemporal replacement starts; the
        method takes no condition or start of its own. A Bitemporal replacement
        establishes its state over its whole window, gaps and coverage after a
        scheduled termination included, reading the later coverage its window
        reaches at flush. Failed authority never licenses it to open coverage:
        a replacement is no upsert. ``until`` follows :meth:`insert`'s rules."""
        mutation, bound = window_mutation("replace", "replaceUntil", until)
        self._attempt.keyed_write(TypedKeyedWriteSource(source, self._codec), mutation, until=bound)

    def replace_if(
        self,
        payload: EntityBase,
        *,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a complete replacement of the existing object ``payload``'s
        primary key names, under the one revision its caller states.

        ``payload`` states the object's whole writable state, completed as
        :meth:`replace` completes it. Whatever produced ``payload`` is not
        consulted: a historical observation can restore its state under a
        current condition and new bounds without being copied first, and no
        read's evidence or insertion's authority it carries stands in for the
        revision. The revision follows :meth:`amend_if`'s rules.

        A Bitemporal replacement requires ``valid_from`` and current coverage
        there, and establishes ``payload``'s state over its whole window, gaps
        and coverage after a scheduled termination included; the stated
        milestone describes that start alone, and the flush reads the later
        coverage the window reaches. ``valid_from`` and ``until`` follow
        :meth:`insert`'s rules. Returns ``None``; a read reports the saved
        state."""
        self._attempt.target_write(
            TypedInstanceTargetWriteAdapter(payload),
            "replace",
            version=version,
            tx_start=tx_start,
            valid_from=valid_from,
            until=until,
        )

    def delete_if(
        self,
        entity: type[EntityBase],
        *,
        key: object,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a deletion of the existing object of concrete ``entity`` that
        ``key`` names, under the one revision its caller states.

        ``key`` and the revision follow :meth:`amend_if`'s rules, and no
        instance, read, or source is consulted. A deletion has no empty form:
        under the Optimistic strategy the stated version gates the ``delete``,
        and an object no longer standing at it — revised or already gone —
        raises :class:`~parallax.core.unit_work.WritePreconditionError` at
        flush rather than deleting nothing; under Locking the stored row is
        read under the shared lock now, and a mismatch or a missing row raises
        that error here. A temporal ``entity`` refuses the verb and names
        :meth:`terminate_if`, which closes its history instead."""
        self._attempt.target_write(
            TypedKeyTargetWriteAdapter(entity, (), key),
            "delete",
            version=version,
            tx_start=tx_start,
        )

    def terminate_if(
        self,
        entity: type[EntityBase],
        *,
        key: object,
        version: int | Omitted = OMITTED,
        tx_start: dt.datetime | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a termination of the existing temporal object of concrete
        ``entity`` that ``key`` names, under the one revision its caller
        states.

        ``key`` and the revision follow :meth:`amend_if`'s rules. A
        Transaction-Time-Only termination closes the current milestone, which
        must start at ``tx_start``. A Bitemporal one requires ``valid_from`` and
        a current rectangle there starting at ``tx_start``, and ends every
        interval of its window — through infinity when ``until`` is omitted,
        or up to the exclusive ``until`` — as :meth:`terminate` does. The
        stated milestone describes that start alone: a later rectangle the
        window reaches is ended under its own current revision, even one
        another writer changed after the caller's query. A missing or revised
        starting milestone raises
        :class:`~parallax.core.unit_work.WritePreconditionError`, never an
        empty termination. A non-temporal ``entity`` refuses the verb and names
        :meth:`delete_if`. ``valid_from`` and ``until`` follow :meth:`insert`'s
        rules."""
        self._attempt.target_write(
            TypedKeyTargetWriteAdapter(entity, (), key),
            "terminate",
            version=version,
            tx_start=tx_start,
            valid_from=valid_from,
            until=until,
        )

    def delete(self, node_or_instance: EntityBase) -> None:
        """Buffer a keyed ``delete``, keyed off ``node_or_instance``'s primary
        key (a frozen ``Snapshot`` node, a fresh instance, or an edited copy —
        all carry valid primary-key values). A source view pinned at a
        finite Transaction-Time instant is read-only and raises
        :class:`~parallax.core.execution.TransactionTimePinReadOnlyError`
        before any buffering, exactly as every other keyed verb does.

        ``delete`` physically removes the row and carries no temporal meaning, so
        a target that milestones its rows refuses it at this call and names
        :meth:`terminate`, which closes the row's history instead."""
        self._attempt.keyed_write(TypedKeyedWriteSource(node_or_instance, self._codec), "delete")

    def terminate(
        self, node_or_instance: EntityBase, *, until: dt.datetime | Omitted = OMITTED
    ) -> None:
        """Buffer a keyed terminate: end ``node_or_instance``'s current coverage,
        keyed off its primary key alone (the temporal delete-equivalent,
        `m-temporal-write`).

        A Transaction-Time-Only target closes its current milestone. A Bitemporal
        one starts where its source was read, as :meth:`amend` does, and ends
        every interval of current coverage from there — through infinity when
        ``until`` is omitted, or up to the exclusive ``until``; history and
        coverage outside that window survive."""
        mutation, bound = window_mutation("terminate", "terminateUntil", until)
        self._attempt.keyed_write(
            TypedKeyedWriteSource(node_or_instance, self._codec), mutation, until=bound
        )

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        """Run a participating read for ``query`` and return ``Snapshot[S]``:
        force-flushes pending writes first (read-your-own-writes), and renders
        the read-lock suffix per materialized level from that level's OWN target
        Entity — its Effective Concurrency Strategy, derived from this
        transaction's one Concurrency Preference and the Entity's Optimistic
        Lock Facet, takes the dialect's shared row lock under Locking and none
        under Optimistic. One deep fetch may therefore lock some levels and not
        others. Otherwise identical to :meth:`ScopedDatabase.find` — the SAME
        read gate, which
        runs BEFORE the force-flush so a refused read flushes nothing, the SAME
        shared find executor, the SAME frozen-node wrapping, and the SAME
        parameter answer: the Snapshot carries the query's RESULT Entity.

        Every materialized node of a VERSIONED entity — root and included
        (deep-fetch) alike — CARRIES the observed version it was read at
        (`m-opt-lock`; ADR 0013), in EITHER concurrency mode: a later keyed
        write of that SAME object derives its version advance (and,
        under optimistic concurrency, its gate) from THAT value's own retained
        observation, never from an implicit resolving read at write time. Every
        materialized node of a TEMPORAL entity likewise carries its whole
        observed predecessor milestone: a later temporal write's close/chain
        derives from it, never from a shadow lookup or an implicit resolving
        read. This transaction additionally stamps its participation on every
        node such a read publishes, which is the license an effective-Locking
        write needs. A MILESTONE-SET read — `.history()` / `.as_of_range()` —
        retains no evidence at all: its roots stand at coordinates no keyed
        write may address.
        """
        return self._attempt.read(
            query, convert_query=typed_read_query, build_publication=typed_publication_for
        )

    @property
    def wire(self) -> WireTransactionView:
        """This transaction's Wire read and write interface.

        A lightweight view over the SAME unit of work, evidence retention,
        locking, and coalescing the Typed verbs use, so Typed and
        Wire calls mix within one transaction without any cross-interface
        bookkeeping — a Wire node and a Typed node of one row carry the identical
        claim, and a Wire write and a Typed write of one object meet in the one
        claim algebra.

        Its read and write halves are this transaction's one attempt, retained
        rather than wrapped, so a Wire read enters at the attempt's own read and
        refuses re-entry at the same first line ``tx.find`` crosses, and a Wire
        write meets the insertions the Typed verbs admitted in one unit of work,
        so a repeated insert is refused across both representations.
        """
        return WireTransactionView(self._attempt)

    def stream[S](self, query: ObjectQuery[Any, S], *, batch_size: int = 1000) -> SnapshotStream[S]:
        """Deliver ``query``'s roots one at a time inside this transaction, as
        the scope-bound single-pass peer of :meth:`find`.

        Participation is per PAGE rather than per read: each page force-flushes
        pending writes before its own statements run, so a loop that writes as
        it reads still sees its own writes, and derives every level's read lock
        from that level's own target Entity. The buffer a writing loop
        accumulates is therefore bounded by one page rather than by the result —
        the same dial, pointed at the same thing.

        Delivery is attempt-local. A ``db.transact`` may re-execute its
        callback, and roots already consumed cannot be revoked, so a retried
        callback opens a fresh stream and may observe them again.
        """
        return SnapshotStream(
            self._attempt,
            query,
            batch_size,
            convert_query=typed_read_query,
            build_publication=typed_publication_for,
        )

    def read_rows(self, query: ObjectQueryNode) -> RowsResult:
        """Run a PARTICIPATING row-form read and return its published rows.

        The values lane's peer of :meth:`find`, participating exactly as the
        graph form does: it force-flushes pending writes first
        (read-your-own-writes) and renders the read-lock suffix its target
        Entity's Effective Concurrency Strategy calls for. Like every
        participating read it opens its Read activity inside that force-flush,
        under this transaction's attempt (`m-execution-lifecycle`).

        It records NO observation. The values lane projects scalars only, so a
        Predecessor Row read off it would be incomplete under Relational Document
        Layout while `m-unit-work` requires a complete one. A caller that needs
        evidence reads the graph form, which is what :meth:`find` and
        ``tx.wire.find`` always run.
        """
        return self._attempt.read_rows(query)

    def amend_where[E: EntityBase](
        self, query: ObjectQuery[E, Any], *assignments: AttributeAssignment[E]
    ) -> int:
        """Amend every row ``query`` selects now, in one readless statement —
        the members ``assignments`` names, every other member kept — and answer
        how many rows it matched, unchanged ones included.

        Every write buffered before it executes first, in the same flush, so the
        statement sees them, and its errors are raised here; nothing about the
        rows it reached is remembered. ``query`` carries nothing but its target
        and predicate (``query-not-mutation-compatible`` otherwise), and
        ``assignments`` are ``Attr.set(...)`` calls naming members of its exact
        target, each at most once. Naming none is the empty amendment, judged
        and then answered ``0``, so no statement runs and nothing buffered is
        flushed. A versioned or temporal target, which each object's write must
        observe, is refused before anything else is judged
        (``set-based-write-target-unsupported``)."""
        return self._attempt.predicate_write(
            TypedPredicateWriteAdapter(query, assignments), "amend"
        )

    def replace_where[E: EntityBase](self, query: ObjectQuery[E, Any], payload: E) -> int:
        """Replace every row ``query`` selects now, in one readless statement,
        with ``payload``'s whole writable state, under :meth:`amend_where`'s
        query, target, timing, and count rules.

        ``payload`` is an instance of the queried Entity, used only as data, as
        :meth:`replace_if` uses it: whatever produced it is not consulted. Its
        state is completed as :meth:`replace` completes it — an omitted
        nullable member is written empty, an omitted ``many`` the empty
        collection, and an omitted required member is refused — and its key
        addresses nothing, since ``query`` selects the rows, so it is never
        written."""
        return self._attempt.predicate_write(TypedPredicateWriteAdapter(query, payload), "replace")

    def delete_where(self, query: ObjectQuery[Any, Any]) -> int:
        """Delete every row ``query`` selects now, in one readless statement,
        under :meth:`amend_where`'s query, target, and timing rules, and answer
        how many rows it deleted."""
        return self._attempt.predicate_write(TypedPredicateWriteAdapter(query, ()), "delete")


def transaction_for(attempt: TxnAttempt) -> TxnContext:
    """The Snapshot transaction one fully constructed attempt is handed to its
    callback as, deriving rows through the codec that attempt adopted."""
    return TxnContext(attempt, attempt.codec)


class ReadOnlyTxnContext:
    """The read-only transaction context handed to a ``db.read_only`` callback.

    A facade over one read-only transaction attempt: its connection, the
    selection it adopted, and a native transaction opened read-only. It reads
    exactly as :class:`TxnContext` does — :meth:`find`, :meth:`stream`,
    :meth:`read_rows`, and :attr:`wire` — except that no read takes a
    participation lock, the unversioned fallback included, and it has no verb
    that writes. A reference used after its attempt ended raises
    ``EscapedTransactionError``, a live stream included.
    """

    __slots__ = ("_attempt",)

    def __init__(self, attempt: ReadOnlyTxnAttempt) -> None:
        self._attempt = attempt

    @property
    def edition(self) -> str:
        """The Model Edition this attempt adopted before its boundary opened,
        retained for the attempt's life as :attr:`TxnContext.edition` is."""
        return self._attempt.edition

    @property
    def options(self) -> ReadOnlyTxnOptions:
        """The resolved options this read-only invocation runs under: each
        explicit ``db.read_only`` keyword, else the Database Root's default.

        One record for the whole invocation, shared by every retried attempt
        and every joining call, which compares its explicit keywords against
        exactly this. It has no Concurrency Preference: a read-only transaction
        takes no participation lock.
        """
        return self._attempt.options

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        """Run ``query`` inside this transaction and return ``Snapshot[S]``,
        taking no participation lock and retaining no Read Evidence. Otherwise
        identical to :meth:`TxnContext.find`."""
        return self._attempt.read(
            query, convert_query=typed_read_query, build_publication=typed_publication_for
        )

    def stream[S](self, query: ObjectQuery[Any, S], *, batch_size: int = 1000) -> SnapshotStream[S]:
        """Deliver ``query``'s roots one at a time inside this transaction.

        Delivery is attempt-local: a retried callback opens a fresh stream and
        may observe roots already consumed, and a stream outliving its attempt
        reads no further page.
        """
        return SnapshotStream(
            self._attempt,
            query,
            batch_size,
            convert_query=typed_read_query,
            build_publication=typed_publication_for,
        )

    def read_rows(self, query: ObjectQueryNode) -> RowsResult:
        """Run a row-form read inside this transaction; it records no
        observation and takes no participation lock."""
        return self._attempt.read_rows(query)

    @property
    def wire(self) -> WireDatabaseView:
        """This transaction's Wire read interface: the same reads, Wire-spelled,
        over the same attempt."""
        return WireDatabaseView(self._attempt)


def read_only_context_for(attempt: ReadOnlyTxnAttempt) -> ReadOnlyTxnContext:
    """The context one fully constructed read-only attempt is handed to its
    callback as."""
    return ReadOnlyTxnContext(attempt)
