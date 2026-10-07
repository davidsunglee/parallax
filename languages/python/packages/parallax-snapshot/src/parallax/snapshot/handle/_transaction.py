from __future__ import annotations

import datetime as dt
from typing import Any

from parallax.core.db_port import DatabaseConnection
from parallax.core.entity import AttributeAssignment, EntityRowCodec
from parallax.core.entity import Entity as EntityBase
from parallax.core.execution_lifecycle._activity import (
    InstalledLifecycle,
    TransactionAttemptActivity,
)
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.read_delivery import RowsResult
from parallax.core.read_delivery._read_plan import ReadPlanner
from parallax.core.unit_work import UnitOfWork

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot._inspection import bind_insertion
from parallax.snapshot.handle._keyed_writes import (
    KeyedWriteContext,
    keyed_insert,
    keyed_write,
    window_mutation,
)
from parallax.snapshot.handle._options import OMITTED, DatabaseOptions, Omitted
from parallax.snapshot.handle._predicate_writes import PredicateWriteContext
from parallax.snapshot.handle._publication import SelectedReadModel, SelectedWriteModel
from parallax.snapshot.handle._read import Snapshot, typed_publication_for
from parallax.snapshot.handle._read_scope import participating_read_scope
from parallax.snapshot.handle._stream import SnapshotStream
from parallax.snapshot.handle._typed_writes import (
    TypedKeyedInsertSource,
    TypedKeyedWriteSource,
    typed_predicate_write,
    typed_target_write,
)
from parallax.snapshot.handle._wire import WireTransactionView


class Transaction:
    """The developer transaction handed to a ``db.transact`` closure.

    A facade over the active unit of work and the transaction's own connection.
    The keyed verbs take entity instances: :meth:`insert` a full
    instance (the Create Payload), :meth:`update` an edited copy (the sparse
    row: primary key + effective change set — an empty effective set is a
    no-op, zero round trips), :meth:`delete` a node or instance (keys off its
    primary key). :meth:`find` runs a participating read and returns
    ``Snapshot[T]``: force-flush + the lock suffix each materialized level's own
    target Entity calls for, otherwise identical to
    :meth:`ScopedDatabase.find`. The predicate-selected
    ``_where`` verb family —
    :meth:`update_where`, :meth:`delete_where`, :meth:`terminate_where` — mirrors
    the keyed surface over a mutation-compatible Object Query: readless for an
    unversioned, non-temporal target, materializing to per-row keyed writes
    otherwise (:mod:`parallax.snapshot.handle._predicate_writes`, ADR 0014, which
    those verbs reach through the Typed predicate ingress). Every windowed verb
    selects its bounded form with keyword-only ``until``. A reference used after
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

    __slots__ = (
        "_codec",
        "_edition",
        "_keyed",
        "_options",
        "_predicates",
        "_reads",
        "_uow",
    )

    def __init__(
        self,
        uow: UnitOfWork,
        conn: DatabaseConnection,
        read: SelectedReadModel,
        write: SelectedWriteModel,
        attempt: TransactionAttemptActivity,
        lifecycle: InstalledLifecycle | None,
        planner: ReadPlanner,
        options: DatabaseOptions,
    ) -> None:
        self._uow = uow
        # The invocation's resolved record, shared by reference across every
        # attempt of the invocation: what a joining call is compared against,
        # and what a caller inspects, without ambient state on either path.
        self._options = options
        # The two projections of the one selection this attempt adopted: the
        # read projection serves every participating read, and the write
        # projection's cataloged model and codec serve every keyed verb — a
        # write names Entities and derives rows, so it needs the catalog without
        # the materialization capability beside it. Both carry the edition.
        self._edition = write.edition
        self._codec: EntityRowCodec = write.codec
        # The one Read Scope this transaction's eager reads run through — its
        # own Typed verbs and the Wire view it answers alike (the Python binding "Private
        # read composition"). The opening handle's own installed lifecycle rides
        # every read and write context, which is what makes "the originating
        # Handle or Transaction" one refusal rather than two: a verb called from
        # inside that handle's provider, handler, or reporter is refused on
        # exactly the state the handle refuses on (`m-execution-lifecycle`).
        self._reads = participating_read_scope(
            lifecycle=lifecycle,
            selected=read,
            uow=uow,
            conn=conn,
            attempt=attempt,
            planner=planner,
        )
        # The transaction state every keyed write of this transaction reads,
        # built once because all three facts are fixed for its life. The unit
        # of work's admitted insertions are what a same-transaction insert
        # leaves for a subsequent keyed write to build on, so both
        # read-your-own-writes exemptions — the value-provenance refusal and the
        # write-evidence resolution — and the repeated-insert refusal read one
        # record, through either representation.
        self._keyed = KeyedWriteContext(model=write.model, uow=uow, lifecycle=lifecycle)
        # The predicate-selected writes of both representations share the keyed
        # context plus what only a materializing write reads: this connection,
        # and the physical attempt its resolving read hangs under as a child.
        self._predicates = PredicateWriteContext(self._keyed, conn, attempt)

    @property
    def edition(self) -> str:
        """The Model Edition this attempt adopted before its boundary opened.

        Retained for the attempt's life: a publication landing while the
        callback runs changes nothing here, and a retried callback receives a
        new transaction that may report another edition.
        """
        return self._edition

    @property
    def options(self) -> DatabaseOptions:
        """The resolved options this transaction's invocation runs under: each
        explicit ``db.transact`` keyword, else the Database Root's default.

        One record for the whole invocation, so every retried attempt and every
        joining call reads the same values; a joining call's explicit keyword is
        compared against exactly this.
        """
        return self._options

    def insert(
        self,
        instance: EntityBase,
        *,
        valid_from: dt.datetime | None = None,
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
        the update and terminate verbs revise what the insert opened for the rest
        of the attempt, starting at ``valid_from``, before and after a flush. A
        value derived before the insert, or another instance of the same key,
        carries none. The authority is private to the instance — not a member,
        not serialized — and ends with the attempt.

        An object whose insertion still stands is not opened twice: a repeated
        insert of it — the same instance again, or another instance of the same
        primary key, through either interface — is refused at the verb
        (:class:`~parallax.snapshot.handle.KeyedWriteValueError`,
        ``write-value-already-stored``) rather than left for the database to
        refuse at commit. Once everything the insertion opened has been removed,
        or a pending write removes it, the object may be inserted again: the new
        insertion executes after that removal, and grants the instance it takes
        a fresh authority, which no earlier draft shares.

        ``valid_from`` is a Bitemporal insert's Valid-Time start; a
        Transaction-Time-Only or non-temporal target takes none. ``until`` bounds
        a Bitemporal insert to ``[valid_from, until)``; omitting it opens
        ``[valid_from, infinity)``. A stated ``until`` is a bound whatever its
        value — ``None`` is refused rather than read as omission — and a target
        with no Valid Time refuses one outright. The window is judged at THIS
        call, before any buffering. Both bounds come from these arguments, never
        from instance fields: an As-Of Axis endpoint is framework-owned."""
        mutation, bound = window_mutation("insert", "insertUntil", until)
        opened = keyed_insert(
            self._keyed,
            TypedKeyedInsertSource(instance, self._codec),
            mutation,
            valid_from=valid_from,
            until=bound,
        )
        bind_insertion(instance, opened.authority)

    def update(self, copy: EntityBase, *, until: dt.datetime | Omitted = OMITTED) -> None:
        """Buffer a sparse keyed update of an edited copy: its primary key plus
        every member its edit chain touched, at the value each now holds.

        The touched set is the literal assignment: a member set back to the value
        the source was read with is still written, and a copy whose chain touched
        nothing is the empty set, which buffers nothing and issues no statement. A
        value no read of this store produced is refused instead, before any row is
        derived (:class:`~parallax.snapshot.handle.KeyedWriteValueError`,
        ``write-value-not-stored``) — unless THIS transaction already admitted its
        insert, which is the row it stores (`m-unit-work` "Insert-then-update
        coalesces in place"). The version column, if any, is never authored here —
        it is framework-owned end to end (`m-opt-lock`; ADR 0013): the write seam
        derives its advance from the observation the source value itself retained.

        A Bitemporal update starts where its source was read — the source's
        finite Valid-Time pin, or the start an insert this transaction admitted
        was authored with — and applies to every interval of the object's current
        coverage from there: through infinity when ``until`` is omitted, or up to
        the exclusive ``until``. Each interval keeps its own unassigned members,
        and gaps stay gaps (`m-temporal-write`). A source read at Valid-Time
        ``LATEST`` names no start and is refused. ``until`` follows
        :meth:`insert`'s rules, and is judged at THIS call even when the set is
        empty."""
        mutation, bound = window_mutation("update", "updateUntil", until)
        keyed_write(self._keyed, TypedKeyedWriteSource(copy, self._codec), mutation, until=bound)

    def replace(
        self,
        instance: EntityBase,
        *,
        valid_from: dt.datetime | None = None,
        until: dt.datetime | Omitted = OMITTED,
        if_version: int | None = None,
        if_tx_start: dt.datetime | None = None,
    ) -> None:
        """Buffer a complete replacement of the existing object ``instance``'s
        primary key names, under the revision its caller states.

        ``instance`` states the object's whole writable state: every member it
        sets is written, an omitted nullable member is written empty and an
        omitted ``many`` the empty collection, and an omitted required member is
        refused — nothing is carried forward from the state it replaces.
        Framework-owned members are never written. Whatever produced
        ``instance`` is not consulted: a replacement is addressed by its key
        and conditioned by its arguments alone.

        The condition is the caller's: a versioned Entity requires
        ``if_version``, the version the caller last observed; a temporal one
        ``if_tx_start``, the Transaction-Time start of the milestone the caller
        last observed where the write starts, never this transaction's own
        instant; an unversioned one takes no revision argument. The write still
        advances the version, or chains a milestone, when every value equals
        what is stored. Under the Optimistic strategy the stated revision gates
        the write, and a row that no longer stands at it raises
        :class:`~parallax.core.unit_work.WritePreconditionError` at flush, which
        no retry repeats. Under Locking the stored row is read under the shared
        lock now — reading nothing it already holds, and executing no pending
        write — and a mismatch raises that error here. An object this
        transaction inserted is refused (``write-evidence-inserted``): until
        commit, write it through the instance the insert took or a read.

        ``valid_from`` and ``until`` follow :meth:`insert`'s rules, so a
        non-temporal target takes neither. A Bitemporal replacement requires
        current coverage at ``valid_from`` and establishes ``instance``'s state
        over its whole window, gaps and coverage after a scheduled termination
        included; the stated milestone describes that start alone, and the
        flush reads the later coverage the window reaches. Returns ``None``; a
        read reports the saved state."""
        mutation, bound = window_mutation("replace", "replaceUntil", until)
        typed_target_write(
            self._predicates,
            mutation,
            instance,
            self._codec,
            valid_from=valid_from,
            until=bound,
            if_version=if_version,
            if_tx_start=if_tx_start,
        )

    def delete(self, node_or_instance: EntityBase) -> None:
        """Buffer a keyed ``delete``, keyed off ``node_or_instance``'s primary
        key (a frozen ``Snapshot`` node, a fresh instance, or an edited copy —
        all carry valid primary-key values). A source view pinned at a
        finite Transaction-Time instant is read-only and raises
        :class:`~parallax.snapshot.handle.TransactionTimePinReadOnlyError`
        before any buffering, exactly as every other keyed verb does.

        ``delete`` physically removes the row and carries no temporal meaning, so
        a target that milestones its rows refuses it at this call and names
        :meth:`terminate`, which closes the row's history instead."""
        keyed_write(self._keyed, TypedKeyedWriteSource(node_or_instance, self._codec), "delete")

    def terminate(
        self, node_or_instance: EntityBase, *, until: dt.datetime | Omitted = OMITTED
    ) -> None:
        """Buffer a keyed terminate: end ``node_or_instance``'s current coverage,
        keyed off its primary key alone (the temporal delete-equivalent,
        `m-temporal-write`).

        A Transaction-Time-Only target closes its current milestone. A Bitemporal
        one starts where its source was read, as :meth:`update` does, and ends
        every interval of current coverage from there — through infinity when
        ``until`` is omitted, or up to the exclusive ``until``; history and
        coverage outside that window survive."""
        mutation, bound = window_mutation("terminate", "terminateUntil", until)
        keyed_write(
            self._keyed,
            TypedKeyedWriteSource(node_or_instance, self._codec),
            mutation,
            until=bound,
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
        :func:`~parallax.snapshot.handle._preflight.preflight` gate, which
        runs BEFORE the force-flush so a refused read flushes nothing, the SAME
        shared find executor, the SAME frozen-node wrapping, and the SAME
        parameter answer: the Snapshot carries the query's RESULT Entity.

        Every materialized node of a VERSIONED entity — root and included
        (deep-fetch) alike — CARRIES the observed version it was read at
        (`m-opt-lock`; ADR 0013), in EITHER concurrency mode: a later keyed
        update/delete of that SAME object derives its version advance (and,
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
        return self._reads.read(
            query, convert_query=object_query_node, build_publication=typed_publication_for
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

        Its read half is this transaction's one Read Scope, retained rather than
        wrapped, so a Wire read enters at that scope's own verb and refuses
        re-entry at the same first line ``tx.find`` crosses. Its write half is
        the same write context the Typed verbs here use, so a Wire write meets
        the insertions the Typed verbs admitted in one unit of work, and a
        repeated insert is refused across both representations.
        """
        return WireTransactionView(self._reads, self._predicates)

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
            self._reads,
            query,
            batch_size,
            convert_query=object_query_node,
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
        return self._reads.read_rows(query)

    def update_where(
        self,
        query: ObjectQuery[Any, Any],
        *assignments: AttributeAssignment[Any],
        valid_from: dt.datetime | None = None,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """A predicate-selected update: ``query`` MUST be mutation-compatible
        (nothing but a target and a predicate); ``assignments`` are
        ``Attr.set(value)`` calls, non-empty, no duplicate field, each addressing
        the query's exact target. Readless (one statement) for an unversioned,
        non-temporal target; a versioned or temporal target MATERIALIZES
        (`m-opt-lock`, ADR 0014) — see
        :func:`~parallax.snapshot.handle._typed_writes.typed_predicate_write`,
        the Typed predicate ingress every ``_where`` verb here delegates to.

        A Bitemporal target requires ``valid_from``; ``until`` bounds the
        correction to ``[valid_from, until)`` and follows :meth:`insert`'s
        rules."""
        mutation, bound = window_mutation("update", "updateUntil", until)
        typed_predicate_write(
            self._predicates, mutation, query, assignments, valid_from=valid_from, until=bound
        )

    def delete_where(self, query: ObjectQuery[Any, Any]) -> None:
        """A predicate-selected ``delete`` over a NON-temporal target
        : readless for an unversioned target; a versioned one
         MATERIALIZES to one observation-backed per-row delete per resolved row
         — in both modes, since each row's write requires that row's own prior
         observation — with no no-op elimination, because a delete changes a
         row's existence, never a value (`m-opt-lock`)."""
        typed_predicate_write(self._predicates, "delete", query, (), valid_from=None)

    def terminate_where(
        self,
        query: ObjectQuery[Any, Any],
        *,
        valid_from: dt.datetime | None = None,
        until: dt.datetime | Omitted = OMITTED,
    ) -> None:
        """A predicate-selected terminate over a TEMPORAL target, which always
        materializes — a temporal predicate write has no readless template.
        Transaction-Time-Only takes no ``valid_from``; Bitemporal requires it, and
        ``until`` bounds the window to ``[valid_from, until)`` under
        :meth:`insert`'s rules."""
        mutation, bound = window_mutation("terminate", "terminateUntil", until)
        typed_predicate_write(
            self._predicates, mutation, query, (), valid_from=valid_from, until=bound
        )
