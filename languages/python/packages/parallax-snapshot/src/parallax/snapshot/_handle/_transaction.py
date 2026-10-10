from __future__ import annotations

import datetime as dt
from typing import Any

from parallax.core.entity import AttributeAssignment, EntityRowCodec
from parallax.core.entity import Entity as EntityBase
from parallax.core.execution import DatabaseOptions
from parallax.core.execution._attempt import Attempt
from parallax.core.execution._keyed_writes import target_condition, window_mutation
from parallax.core.execution._options import OMITTED, Omitted
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, typed_read_query
from parallax.core.read_delivery import RowsResult
from parallax.snapshot._handle._read import Snapshot, typed_publication_for
from parallax.snapshot._handle._stream import SnapshotStream
from parallax.snapshot._handle._typed_writes import (
    TypedKeyedInsertSource,
    TypedKeyedWriteSource,
    typed_conditional_amend,
    typed_predicate_write,
    typed_target_write,
)
from parallax.snapshot._handle._wire import WireTransactionView

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot._inspection import bind_insertion

__all__ = ["Transaction", "transaction_for"]


class Transaction:
    """The developer transaction handed to a ``db.transact`` closure.

    A facade over one transaction attempt: its unit of work, its connection, and
    the selection it adopted.
    The method names the authority a write runs under. The source-authorized
    verbs take a value this store published or an insertion opened:
    :meth:`amend` its edits or explicit assignments, :meth:`replace` its
    complete writable state, :meth:`delete` and :meth:`terminate` its object.
    :meth:`insert` opens a full instance (the Create Payload). The
    caller-conditioned verbs :meth:`amend_if` and :meth:`replace_if` address an
    object themselves under the one condition their caller states, never
    falling back on a source's authority. :meth:`find` runs a participating
    read and returns ``Snapshot[T]``: force-flush + the lock suffix each
    materialized level's own target Entity calls for, otherwise identical to
    :meth:`ScopedDatabase.find`. The predicate-selected ``_where`` verb family
    — :meth:`amend_where`, :meth:`delete_where`, :meth:`terminate_where` —
    writes every row a mutation-compatible Object Query selects: readless for an
    unversioned, non-temporal target, materializing to per-row keyed writes
    otherwise (ADR 0014, which those verbs reach through the Typed predicate
    ingress). Every windowed verb selects its bounded form with keyword-only
    ``until``, and a stated ``valid_from`` or ``until`` of ``None`` is refused
    rather than read as omission. A reference used after
    its owning scope ends raises
    :class:`~parallax.core.unit_work.EscapedTransactionError` (every verb
    delegates to the unit of work, which fences use-after-scope).

    :attr:`wire` is the Wire read AND write interface over this same transaction
    — a view, not a second lifecycle, so a Wire read participates exactly as
    :meth:`find` does and a Wire write buffers exactly as the keyed verbs here
    do.

    :meth:`read_rows` is the values lane over this same transaction — a
    first-party row-form read, not a third public result format. There is no
    write peer of it: every write, first-party callers included, is stated
    through the keyed, predicate, and caller-addressed verbs, Typed or Wire — an
    existing row addressed by a value this store published, from a read or from
    the insert that opened the row, a fresh row by the payload an insert opens it
    with, a set by a selection plus its assignments, and an existing object by
    its key under the revision its caller states.
    """

    __slots__ = ("_attempt", "_codec")

    def __init__(self, attempt: Attempt, codec: EntityRowCodec) -> None:
        # The attempt is this transaction's every read and write: its reads
        # participate in its unit of work on its connection, its keyed,
        # predicate, and caller-addressed verbs admit into that unit of work,
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
    def options(self) -> DatabaseOptions:
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

    def amend(
        self,
        source: EntityBase,
        *assignments: AttributeAssignment[Any],
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
        unversioned: bool | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer an amendment of the existing object of concrete ``entity``
        that ``key`` names, under the one condition its caller states.

        ``key`` is the object's scalar primary-key value, whatever the key
        Attribute is called. ``assignments`` are ``Attr.set(...)`` calls naming
        members ``entity`` declares or inherits, each at most once and each
        assigned even when it equals the stored value; assigning nothing is
        validated and then dropped, with no database work at all. No instance,
        read, or source is consulted.

        Exactly one condition is required, and it must be the one ``entity``
        has: ``version``, the version of a versioned Entity its caller last
        observed; ``tx_start``, the Transaction-Time start of the milestone a
        temporal Entity's write starts from; or ``unversioned=True`` for an
        Entity with neither. A missing, extra, ``None``, or inapplicable
        condition is refused, never replaced by a source's authority. Under
        the Optimistic strategy the stated revision gates the write, and a row
        no longer standing at it raises
        :class:`~parallax.core.unit_work.WritePreconditionError` at flush, which
        no retry repeats. Under Locking the stored row is read under the shared
        lock now — reading nothing it already holds, and executing no pending
        write — and a mismatch raises that error here; ``unversioned=True``
        never disables that lock. An object this transaction inserted is
        refused (``write-evidence-inserted``).

        A Bitemporal amendment requires ``valid_from`` and current coverage
        there, and applies to every interval of its window, each keeping what
        it does not assign; gaps and coverage after a scheduled termination
        stay absent. ``valid_from`` and ``until`` follow :meth:`insert`'s
        rules."""
        mutation, bound = window_mutation("amend", "amendUntil", until)
        condition = target_condition(version=version, tx_start=tx_start, unversioned=unversioned)
        typed_conditional_amend(
            self._attempt,
            mutation,
            entity,
            assignments,
            key,
            condition,
            valid_from=valid_from,
            until=bound,
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
        unversioned: bool | Omitted = OMITTED,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """Buffer a complete replacement of the existing object ``payload``'s
        primary key names, under the one condition its caller states.

        ``payload`` states the object's whole writable state, completed as
        :meth:`replace` completes it. Whatever produced ``payload`` is not
        consulted: a historical observation can restore its state under a
        current condition and new bounds without being copied first, and no
        read's evidence or insertion's authority it carries stands in for the
        condition. The condition follows :meth:`amend_if`'s rules.

        A Bitemporal replacement requires ``valid_from`` and current coverage
        there, and establishes ``payload``'s state over its whole window, gaps
        and coverage after a scheduled termination included; the stated
        milestone describes that start alone, and the flush reads the later
        coverage the window reaches. ``valid_from`` and ``until`` follow
        :meth:`insert`'s rules. Returns ``None``; a read reports the saved
        state."""
        mutation, bound = window_mutation("replace", "replaceUntil", until)
        condition = target_condition(version=version, tx_start=tx_start, unversioned=unversioned)
        typed_target_write(
            self._attempt,
            mutation,
            payload,
            self._codec,
            condition,
            valid_from=valid_from,
            until=bound,
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

    def amend_where(
        self,
        query: ObjectQuery[Any, Any],
        *assignments: AttributeAssignment[Any],
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """A predicate-selected amendment: ``query`` MUST be mutation-compatible
        (nothing but a target and a predicate); ``assignments`` are
        ``Attr.set(value)`` calls, non-empty, no duplicate field, each addressing
        the query's exact target. Readless (one statement) for an unversioned,
        non-temporal target; a versioned or temporal target MATERIALIZES
        (`m-opt-lock`, ADR 0014) — see
        :func:`~parallax.snapshot._handle._typed_writes.typed_predicate_write`,
        the Typed predicate ingress every ``_where`` verb here delegates to.

        A Bitemporal target requires ``valid_from``; ``until`` bounds the
        correction to ``[valid_from, until)``, and both follow :meth:`insert`'s
        rules."""
        mutation, bound = window_mutation("amend", "amendUntil", until)
        typed_predicate_write(
            self._attempt,
            mutation,
            query,
            assignments,
            valid_from=valid_from,
            until=bound,
        )

    def delete_where(self, query: ObjectQuery[Any, Any]) -> None:
        """A predicate-selected ``delete`` over a NON-temporal target
        : readless for an unversioned target; a versioned one
         MATERIALIZES to one observation-backed per-row delete per resolved row
         — in both modes, since each row's write requires that row's own prior
         observation — with no no-op elimination, because a delete changes a
         row's existence, never a value (`m-opt-lock`)."""
        typed_predicate_write(self._attempt, "delete", query, ())

    def terminate_where(
        self,
        query: ObjectQuery[Any, Any],
        *,
        valid_from: dt.datetime | Omitted = OMITTED,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """A predicate-selected terminate over a TEMPORAL target, which always
        materializes — a temporal predicate write has no readless template.
        Transaction-Time-Only takes no ``valid_from``; Bitemporal requires it, and
        ``until`` bounds the window to ``[valid_from, until)``, both under
        :meth:`insert`'s rules."""
        mutation, bound = window_mutation("terminate", "terminateUntil", until)
        typed_predicate_write(
            self._attempt,
            mutation,
            query,
            (),
            valid_from=valid_from,
            until=bound,
        )


def transaction_for(attempt: Attempt) -> Transaction:
    """The Snapshot transaction one fully constructed attempt is handed to its
    callback as, deriving rows through the codec that attempt adopted."""
    return Transaction(attempt, attempt.codec)
