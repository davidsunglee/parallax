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
from parallax.core.object_query._fluent import ObjectQuery
from parallax.core.unit_work import UnitOfWork

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot.handle._keyed_writes import (
    InsertedObjects,
    KeyedWriteContext,
    keyed_insert,
    keyed_write,
)
from parallax.snapshot.handle._options import DatabaseOptions
from parallax.snapshot.handle._predicate_writes import PredicateWriteContext
from parallax.snapshot.handle._publication import SelectedReadModel, SelectedWriteModel
from parallax.snapshot.handle._read import RowsResult, Snapshot
from parallax.snapshot.handle._read_plan import ReadPlanner
from parallax.snapshot.handle._read_scope import participating_read_scope
from parallax.snapshot.handle._stream import SnapshotStream
from parallax.snapshot.handle._typed_writes import (
    TypedKeyedInsertSource,
    TypedKeyedWriteSource,
    typed_predicate_write,
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
    :meth:`update_where`, :meth:`delete_where`, :meth:`terminate_where`,
    :meth:`update_until_where`, :meth:`terminate_until_where` — mirrors the
    keyed surface over a mutation-compatible Object Query: readless for an
    unversioned,
    non-temporal target, materializing to per-row keyed writes otherwise
    (:mod:`parallax.snapshot.handle._predicate_writes`, ADR 0014, which those
    five verbs reach through the Typed predicate ingress). A reference used after
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
    through the keyed and predicate verbs, Typed or Wire — an existing row
    addressed by a value this store published, from a read or from the insert
    that opened the row, a fresh row by the payload an insert opens it with, and
    a set by a selection plus its assignments.
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
        # built once because all four facts are fixed for its life. Its
        # opened-object ledger is what a same-transaction insert leaves for a
        # subsequent keyed write to build on, so both read-your-own-writes
        # exemptions — the value-provenance refusal and the write-evidence
        # resolution — and the repeated-insert refusal read one ledger, through
        # either representation.
        self._keyed = KeyedWriteContext(
            model=write.model,
            uow=uow,
            inserts=InsertedObjects(),
            lifecycle=lifecycle,
        )
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

    def insert(self, instance: EntityBase, *, valid_from: dt.datetime | None = None) -> None:
        """Buffer a keyed ``insert`` of a full instance (the Create Payload,
        the Python binding): every member the instance actually SET. A framework-owned
        member is never among them: the interval bounds (``in_z``/``out_z``,
        bitemporal ``from_z``/``thru_z``) are stamped at flush from the Clock
        Strategy and the version is derived, so the Entity constructor refuses a
        caller-authored one and the row carries none.

        An object this transaction already buffered an insert of is not opened
        twice: a repeated insert of it — the same instance again, or another
        instance of the same primary key, through either interface — is refused
        at the verb (:class:`~parallax.snapshot.handle.KeyedWriteValueError`,
        ``write-value-already-stored``) rather than left for the database to
        refuse at commit, and the update verbs are what revise the row it opens.

        ``valid_from`` is the plain Bitemporal insert's Valid-Time instant — the
        open rectangle's lower bound ``[valid_from, infinity)`` (`m-bitemp-write` "insert /
        insertUntil — a single open rectangle, no close"); mirrors ``update``'s
        own Bitemporal-only requirement: a
        Transaction-Time-Only or non-temporal target takes none (no Valid-Time dimension to
        bound)."""
        keyed_insert(
            self._keyed,
            TypedKeyedInsertSource(instance, self._codec),
            "insert",
            valid_from=valid_from,
        )

    def insert_until(
        self, instance: EntityBase, *, valid_from: dt.datetime, until: dt.datetime
    ) -> None:
        """Buffer a keyed, Valid-Time-bounded ``insertUntil``
        (``m-bitemp-write-003``): open a single bitemporal rectangle
        bounded to ``[valid_from, until)`` at the fresh Transaction-Time
        milestone, with no prior row to close — the bitemporal analogue of an
        audit-only ``insert``, Valid-Time-bounded — bitemporal-only (mirrors
        ``update_until``'s own required ``valid_from`` / ``until``). A window
        that does not satisfy ``valid_from < until``
        (equal or reversed bounds) raises at THIS call, before any buffering
        (all validated at build), and
        so does a repeated insert of an object this transaction already buffered
        an insert of, exactly as :meth:`insert` refuses one.
        The window bounds come from THESE verb arguments, never from instance
        fields: an As-Of Axis endpoint is framework-owned and the temporal write
        path derives every interval bound itself, which is why
        the Entity constructor refuses an authored one outright."""
        keyed_insert(
            self._keyed,
            TypedKeyedInsertSource(instance, self._codec),
            "insertUntil",
            valid_from=valid_from,
            until=until,
        )

    def update(self, copy: EntityBase, *, valid_from: dt.datetime | None = None) -> None:
        """Buffer a sparse keyed ``update``: primary key + the effective change
        set of an edited copy (touched fields whose current value differs from
        the recorded original). An EMPTY effective change set
        issues no DML at all (zero round trips, the net-zero-chain no-op rule
        — the no-op-first ordering `m-opt-lock` fixes: dropped before any
        observation or locking concern), and a node this transaction's own read
        returned that no edit touched carries exactly that empty change set:
        writing every value a find returned and editing only some of them is
        correct code. A value no read of this store produced is refused instead,
        before any row is derived
        (:class:`~parallax.snapshot.handle.KeyedWriteValueError`,
        ``write-value-not-stored``) — unless THIS transaction already buffered
        its insert, which is the row it stores and the pair the flush coalesces
        into one final-value write (`m-unit-work` "Insert-then-update coalesces
        in place"). The version column, if
        any, is never authored here — it is framework-owned end to end
        (`m-opt-lock`; ADR 0013): the write seam derives its advance from the
        observation the source value itself retained
        (`parallax.snapshot.handle`'s write finalization), never from the edited copy.

        ``valid_from`` is the plain Bitemporal correction's Valid-Time instant
        (`m-bitemp-write-006` "plain-update-split" — inactivates the original on
        Transaction Time, then chains head
        (the old value) + a new tail (the new value) running to infinity, the
        two-way degenerate of ``update_until``'s three-way rectangle split).
        Mirrors ``update_where``'s own Bitemporal-only requirement: a
        Transaction-Time-Only or non-temporal target takes none (no Valid-Time
        dimension to bound)."""
        keyed_write(
            self._keyed,
            TypedKeyedWriteSource(copy, self._codec),
            "update",
            valid_from=valid_from,
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
        self, node_or_instance: EntityBase, *, valid_from: dt.datetime | None = None
    ) -> None:
        """Buffer a keyed ``terminate``: close ``node_or_instance``'s current
        milestone (the temporal delete-equivalent) — keyed off
        its primary key alone, no chained row (close-only, `m-txtime-write` /
        `m-bitemp-write`). Transaction-Time-Only takes no ``valid_from``;
        Bitemporal requires it (the mutation's own Valid-Time
        instant, mirroring ``terminate_where``)."""
        keyed_write(
            self._keyed,
            TypedKeyedWriteSource(node_or_instance, self._codec),
            "terminate",
            valid_from=valid_from,
        )

    def update_until(
        self, copy: EntityBase, *, valid_from: dt.datetime, until: dt.datetime
    ) -> None:
        """Buffer a sparse keyed, Valid-Time-bounded ``updateUntil``:
        primary key + the effective change set of an edited copy (mirrors
        keyed ``update``), bounded to ``[valid_from, until)``
        (`m-bitemp-write` "The rectangle split") — bitemporal-only (mirrors
        ``update_until_where``'s own required ``valid_from`` / ``until``). A
        window that does not satisfy ``valid_from < until``
        (equal or reversed bounds) raises at THIS call, before any buffering
        (all validated at build) —
        checked BEFORE the empty-effective-change-set no-op return below:
        window validation runs first for every window verb, never after;
        equal bounds reject even when the
        edited copy's own Change Record nets to zero). An EMPTY effective
        change set (once the window is confirmed valid) issues no DML at all,
        exactly like keyed ``update``."""
        keyed_write(
            self._keyed,
            TypedKeyedWriteSource(copy, self._codec),
            "updateUntil",
            valid_from=valid_from,
            until=until,
        )

    def terminate_until(
        self, node_or_instance: EntityBase, *, valid_from: dt.datetime, until: dt.datetime
    ) -> None:
        """Buffer a keyed, Valid-Time-bounded ``terminateUntil``: close a
        single Valid-Time window ``[valid_from, until)`` on
        ``node_or_instance``'s current milestone, keyed off its primary key
        alone (`m-bitemp-write`) — bitemporal-only (mirrors
        ``terminate_until_where``). A window that does not satisfy
        ``valid_from < until`` (equal or reversed bounds) raises at THIS
        call, before any buffering."""
        keyed_write(
            self._keyed,
            TypedKeyedWriteSource(node_or_instance, self._codec),
            "terminateUntil",
            valid_from=valid_from,
            until=until,
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
        return self._reads.find(query)

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
        the same write context the Typed verbs here use, so a Wire write reads
        the opened-object ledger the Typed verbs record into and
        read-your-own-writes spans both representations.
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
        return self._reads.stream(query, batch_size)

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
    ) -> None:
        """A predicate-selected ``update``: ``query`` MUST be
        mutation-compatible (nothing but a target and a predicate);
        ``assignments`` are ``Attr.set(value)`` calls, non-empty, no duplicate
        field, each addressing the query's exact target. Readless
        (one statement) for an unversioned, non-temporal target; a versioned
        or temporal target MATERIALIZES (`m-opt-lock`, ADR 0014) — see
        :func:`~parallax.snapshot.handle._typed_writes.typed_predicate_write`,
        the Typed predicate ingress every ``_where`` verb here delegates to."""
        typed_predicate_write(self._predicates, "update", query, assignments, valid_from=valid_from)

    def delete_where(self, query: ObjectQuery[Any, Any]) -> None:
        """A predicate-selected ``delete`` over a NON-temporal target
        : readless for an unversioned target; a versioned one
         MATERIALIZES to one observation-backed per-row delete per resolved row
         — in both modes, since each row's write requires that row's own prior
         observation — with no no-op elimination, because a delete changes a
         row's existence, never a value (`m-opt-lock`)."""
        typed_predicate_write(self._predicates, "delete", query, (), valid_from=None)

    def terminate_where(
        self, query: ObjectQuery[Any, Any], *, valid_from: dt.datetime | None = None
    ) -> None:
        """A predicate-selected ``terminate`` over a TEMPORAL target
        : Transaction-Time-Only takes no ``valid_from``;
         Bitemporal requires it. Always materializes — a temporal predicate
         write has no readless template."""
        typed_predicate_write(self._predicates, "terminate", query, (), valid_from=valid_from)

    def update_until_where(
        self,
        query: ObjectQuery[Any, Any],
        *assignments: AttributeAssignment[Any],
        valid_from: dt.datetime,
        until: dt.datetime,
    ) -> None:
        """A predicate-selected, Valid-Time-bounded ``updateUntil`` over a
        Bitemporal target (the Python binding; `m-bitemp-write` "The rectangle
        split"): always materializes to a close plus head/middle/tail."""
        typed_predicate_write(
            self._predicates,
            "updateUntil",
            query,
            assignments,
            valid_from=valid_from,
            until=until,
        )

    def terminate_until_where(
        self, query: ObjectQuery[Any, Any], *, valid_from: dt.datetime, until: dt.datetime
    ) -> None:
        """A predicate-selected, Valid-Time-bounded ``terminateUntil`` over
        a Bitemporal target: always materializes to a close
        plus head/tail (no middle — the window becomes a hole in Valid
        time)."""
        typed_predicate_write(
            self._predicates,
            "terminateUntil",
            query,
            (),
            valid_from=valid_from,
            until=until,
        )
