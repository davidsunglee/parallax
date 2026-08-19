"""``parallax.snapshot.handle._transaction`` — the developer transaction surface (spec §5).

:class:`Transaction` is what a ``db.transact`` closure receives: a facade over
the active unit of work and the transaction's own connection. It owns the
keyed verbs (``insert`` / ``update`` / ``delete`` and the typed
temporal-window family), the participating :meth:`Transaction.find`, and the
``_buffer`` seam every keyed verb shares — which ends at
:func:`~parallax.snapshot.handle._write_inputs.admit_and_buffer`, where a write's
claim at the scope it settles against is taken and an intent the buffer's existing
claim cannot absorb is refused. That seam is `_write_inputs`' rather than this
class's, because the Wire verbs reach it too: one ingress per representation, one
judgement and one buffer for both.

It also owns the row-form read (:meth:`Transaction.read_rows`), which the
conformance harness reaches and no developer surface does. It is not a second
lifecycle: the read enters the same force-flush, lock derivation, evidence
retention, and Read activity bracket ``find`` does.

The predicate-selected ``_where`` family is NOT owned here: those five public
verbs are thin delegates that thread ``(uow, meta, conn, dialect)`` into
:mod:`parallax.snapshot.handle._predicate_writes`, which buffers through
``uow.buffer`` and never reaches back into this class.

Depends on :mod:`parallax.snapshot.handle._preflight` (the shared read gate
``find`` passes before touching the unit of work),
:mod:`parallax.snapshot.handle._read` (the shared find executor plus
the pin / result-conversion helpers ``find`` needs),
:mod:`parallax.snapshot.handle._write_inputs` (verb-input validation and the
evidence machinery), and
:mod:`parallax.snapshot.handle._predicate_writes`. Demarcation — ``Database``,
``_Demarcation``, and ``TransactionOptionConflictError`` — lives in
:mod:`parallax.snapshot.handle._database`, which imports this module, never the
reverse.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from parallax.core.db_port import DbPort
from parallax.core.dialect import Dialect
from parallax.core.entity import (
    AttributeAssignment,
    EntityGraphConstruction,
    EntityRowCodec,
)
from parallax.core.entity import Entity as EntityBase
from parallax.core.execution_lifecycle._activity import INERT
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.temporal_read import scans_an_axis
from parallax.core.unit_work import (
    KeyedMutation,
    SettledEvidence,
    UnitOfWork,
)

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot.handle._errors import SnapshotConnectionError
from parallax.snapshot.handle._family import declaring as declaring_of
from parallax.snapshot.handle._predicate_writes import (
    buffer_predicate,
)
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._read import (
    ResultPublication,
    RowsResult,
    Snapshot,
    find,
    find_history,
    find_rows,
    typed_publication,
    wire_publication,
)
from parallax.snapshot.handle._wire import WireTransactionView
from parallax.snapshot.handle._wire_writes import WireWriteLane
from parallax.snapshot.handle._write_inputs import (
    BufferedInserts,
    admit_and_buffer,
    cancels_a_pending_assignment,
    keyed_instruction,
    metadata_of_instance,
    resolve_write_evidence,
    source_hint_of,
    source_pin,
    validate_keyed_instruction,
    validate_source_pin,
    validate_window,
    validate_write_value,
    written_object,
    written_object_key,
)


class Transaction:
    """The developer transaction handed to a ``db.transact`` closure (spec §5).

    A facade over the active unit of work and the transaction's own connection.
    The keyed verbs take entity instances: :meth:`insert` a full
    instance (the Create Payload), :meth:`update` an edited copy (the sparse
    row: primary key + effective change set — an empty effective set is a
    no-op, zero round trips), :meth:`delete` a node or instance (keys off its
    primary key). :meth:`find` runs a participating read and returns
    ``Snapshot[T]``: force-flush + the lock suffix each materialized level's own
    target Entity calls for, otherwise identical to :meth:`Database.find`. The predicate-selected
    ``_where`` verb family (`python.md` §5) —
    :meth:`update_where`, :meth:`delete_where`, :meth:`terminate_where`,
    :meth:`update_until_where`, :meth:`terminate_until_where` — mirrors the
    keyed surface over a mutation-compatible Object Query: readless for an
    unversioned,
    non-temporal target, materializing to per-row keyed writes otherwise
    (:mod:`parallax.snapshot.handle._predicate_writes`, ADR 0014, which those
    five verbs delegate to). A reference used after
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
    addressed by a value a read published, a fresh row by the payload an insert
    opens it with, and a set by a selection plus its assignments.
    """

    __slots__ = (
        "_codec",
        "_conn",
        "_construction",
        "_dialect",
        "_inserted_objects",
        "_meta",
        "_uow",
    )

    def __init__(
        self,
        uow: UnitOfWork,
        conn: DbPort,
        meta: Metamodel,
        dialect: Dialect,
        construction: EntityGraphConstruction | None,
        codec: EntityRowCodec,
    ) -> None:
        self._uow = uow
        self._conn = conn
        self._meta = meta
        self._dialect = dialect
        self._construction = construction
        self._codec = codec
        # What THIS transaction buffered an insert of — a same-transaction insert
        # IS the provenance a subsequent keyed write builds on, so both
        # read-your-own-writes exemptions (the value-provenance refusal and the
        # write-evidence resolution) read this one ledger, and so does the Wire
        # ingress, whose inserts and updates pair with the Typed ones.
        self._inserted_objects = BufferedInserts()

    def insert(self, instance: EntityBase, *, valid_from: dt.datetime | None = None) -> None:
        """Buffer a keyed ``insert`` of a full instance (the Create Payload,
        spec §5): every member the instance actually SET. A framework-owned
        member is never among them: the interval bounds (``in_z``/``out_z``,
        bitemporal ``from_z``/``thru_z``) are stamped at flush from the Clock
        Strategy and the version is derived, so the Entity constructor refuses a
        caller-authored one and the row carries none.

        ``valid_from`` is the plain Bitemporal insert's Valid-Time instant — the
        open rectangle's lower bound ``[valid_from, infinity)`` (`m-bitemp-write` "insert /
        insertUntil — a single open rectangle, no close"); mirrors ``update``'s
        own Bitemporal-only-required :func:`validate_window`: a
        Transaction-Time-Only or non-temporal target takes none (no Valid-Time dimension to
        bound)."""
        record, declaring, valid_from_literal, _ = self._prepare_keyed_write(
            instance, "insert", valid_from
        )
        self._buffer(
            "insert",
            record.identity,
            self._codec.full_row(instance),
            valid_from=valid_from_literal,
        )
        self._record_buffered_insert(record, declaring, instance)

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
        (:func:`validate_window`, `python.md` §5 "all validated at build").
        The window bounds come from THESE verb arguments, never from instance
        fields: an As-Of Axis endpoint is framework-owned and the temporal write
        path derives every interval bound itself (`python.md` §2), which is why
        the Entity constructor refuses an authored one outright."""
        record, declaring, valid_from_literal, until_literal = self._prepare_keyed_write(
            instance, "insertUntil", valid_from, until
        )
        self._buffer(
            "insertUntil",
            record.identity,
            self._codec.full_row(instance),
            valid_from=valid_from_literal,
            until=until_literal,
        )
        self._record_buffered_insert(record, declaring, instance)

    def update(self, copy: EntityBase, *, valid_from: dt.datetime | None = None) -> None:
        """Buffer a sparse keyed ``update``: primary key + the effective change
        set of an edited copy (touched fields whose current value differs from
        the recorded original, spec §3/§5). An EMPTY effective change set
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
        Mirrors ``update_where``'s own bitemporal-only-required
        :func:`validate_window`: a Transaction-Time-Only or non-temporal target
        takes none (no Valid-Time dimension to bound)."""
        record, declaring, valid_from_literal, _ = self._prepare_keyed_write(
            copy, "update", valid_from
        )
        authored = self._authored_assignments(record, copy, "update")
        if authored is None:
            return
        row, restorations = authored
        self._buffer(
            "update",
            record.identity,
            row,
            valid_from=valid_from_literal,
            claim=self._resolve_evidence(record, declaring, copy, "update"),
            restorations=restorations,
        )

    def delete(self, node_or_instance: EntityBase) -> None:
        """Buffer a keyed ``delete``, keyed off ``node_or_instance``'s primary
        key (a frozen ``Snapshot`` node, a fresh instance, or an edited copy —
        all carry valid primary-key values, spec §5). A source view pinned at a
        finite Transaction-Time instant is read-only and raises
        :class:`~parallax.snapshot.handle.TransactionTimePinReadOnlyError`
        before any buffering, exactly as every other keyed verb does."""
        record = metadata_of_instance(self._meta, node_or_instance)
        validate_source_pin(record.identity, source_pin(node_or_instance))
        self._buffer(
            "delete",
            record.identity,
            self._codec.identity_row(node_or_instance),
            claim=self._resolve_evidence(
                record, declaring_of(self._meta, record), node_or_instance, "delete"
            ),
        )

    # --- typed keyed temporal-window verbs (python.md §5). Every mutation   #
    # kind below is already a valid                                          #
    # ``KeyedMutation`` and already fully lowered (``bitemp_write`` /        #
    # ``txtime_write`` / ``planner``) — only the DEVELOPER-facing verb was    #
    # missing: a typed ``Transaction`` method that builds the SAME           #
    # instruction through the SAME `_buffer` seam `insert`/`update`/`delete` #
    # already share, so a hand-written program and the engine's corpus      #
    # replay can never diverge in behavior.                                 #
    def terminate(
        self, node_or_instance: EntityBase, *, valid_from: dt.datetime | None = None
    ) -> None:
        """Buffer a keyed ``terminate``: close ``node_or_instance``'s current
        milestone (the temporal delete-equivalent, `python.md` §5) — keyed off
        its primary key alone, no chained row (close-only, `m-txtime-write` /
        `m-bitemp-write`). Transaction-Time-Only takes no ``valid_from``;
        Bitemporal requires it (the mutation's own Valid-Time
        instant, mirrors ``terminate_where``'s own
        :func:`validate_window`)."""
        record, declaring, valid_from_literal, _ = self._prepare_keyed_write(
            node_or_instance, "terminate", valid_from
        )
        self._buffer(
            "terminate",
            record.identity,
            self._codec.identity_row(node_or_instance),
            valid_from=valid_from_literal,
            claim=self._resolve_evidence(record, declaring, node_or_instance, "terminate"),
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
        (:func:`validate_window`, `python.md` §5 "all validated at build") —
        checked BEFORE the empty-effective-change-set no-op return below:
        window validation runs first for every window verb, never after;
        equal bounds reject even when the
        edited copy's own Change Record nets to zero). An EMPTY effective
        change set (once the window is confirmed valid) issues no DML at all,
        exactly like keyed ``update``."""
        record, declaring, valid_from_literal, until_literal = self._prepare_keyed_write(
            copy, "updateUntil", valid_from, until
        )
        authored = self._authored_assignments(record, copy, "updateUntil")
        if authored is None:
            return
        row, restorations = authored
        self._buffer(
            "updateUntil",
            record.identity,
            row,
            valid_from=valid_from_literal,
            until=until_literal,
            claim=self._resolve_evidence(record, declaring, copy, "updateUntil"),
            restorations=restorations,
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
        call, before any buffering (:func:`validate_window`, `python.md`
        §5)."""
        record, declaring, valid_from_literal, until_literal = self._prepare_keyed_write(
            node_or_instance, "terminateUntil", valid_from, until
        )
        self._buffer(
            "terminateUntil",
            record.identity,
            self._codec.identity_row(node_or_instance),
            valid_from=valid_from_literal,
            until=until_literal,
            claim=self._resolve_evidence(record, declaring, node_or_instance, "terminateUntil"),
        )

    def _prepare_keyed_write(
        self,
        node_or_instance: EntityBase,
        mutation: KeyedMutation,
        valid_from: dt.datetime | None,
        until: dt.datetime | None = None,
    ) -> tuple[EntityMetadata, EntityMetadata, str | None, str | None]:
        """The keyed-verb prep every verb above (``delete`` excepted — it takes
        no Valid-Time bound) opens with: resolve the written instance's own
        accepted Metadata and its family's DECLARING entity (the entity that
        actually carries the temporal/versioned shape), refuse a source view
        pinned at a finite Transaction-Time instant
        (:func:`validate_source_pin` — the Transaction-Time past is read-only,
        and an edited copy of such a view carries that view's own pin, so
        deriving one is no route past this refusal), refuse a value whose
        provenance this mutation's verb does not accept
        (:func:`validate_write_value`, before any row is derived — with the
        object this transaction already buffered an insert for exempted, so an
        insert-then-update pair coalesces rather than being refused), then
        validate + render the whole Valid-Time window against that declaring
        entity's own temporality (:func:`validate_window`, spec §5).

        The window is validated HERE for every verb, bounded and plain alike,
        rather than leaving a ``*Until`` verb to add its own ``until`` step
        afterwards: a bounded window is a PAIR, and asking half of it first is
        what let an absent half be reported as something other than the missing
        bound it is. Returns the record (``_buffer``'s own entity-name
        argument), the declaring entity (the evidence resolution below needs
        it), and the two rendered instant literals (``None`` where the target
        or the verb states no such bound)."""
        record = metadata_of_instance(self._meta, node_or_instance)
        declaring = declaring_of(self._meta, record)
        validate_source_pin(record.identity, source_pin(node_or_instance))
        validate_write_value(
            record.identity,
            node_or_instance,
            mutation,
            inserted_here=lambda: self._has_buffered_insert(record, declaring, node_or_instance),
        )
        valid_from_literal, until_literal = validate_window(declaring, mutation, valid_from, until)
        return record, declaring, valid_from_literal, until_literal

    def _authored_assignments(
        self, record: EntityMetadata, copy: EntityBase, mutation: KeyedMutation
    ) -> tuple[Mapping[str, object], frozenset[str]] | None:
        """What an update verb buffers for ``copy``: its row and the members its
        edit chain touched and put back — or ``None`` when it buffers nothing.

        A chain with an effective change buffers that change, and rides its
        restorations beside it so a later merge knows which members the author's
        last word left alone. A chain that nets to zero normally buffers nothing
        at all, which is the zero-round-trip no-op every net-zero edit has always
        been. The exception is the one thing such a chain CAN do: cancel an
        assignment this transaction has already buffered at the same claim
        scope. There it buffers its identity row alone, carrying the
        restorations that erase the pending assignment — and the merged write is
        then eliminated exactly as a single net-zero edit is, so the outcome is
        still no DML rather than a write of a value the caller took back.
        """
        row = self._codec.edited_row(copy)
        restorations = self._codec.restored_members(copy)
        if row is not None:
            return row, restorations
        if not restorations or not cancels_a_pending_assignment(
            self._uow, self._meta, record, source_hint_of(copy), mutation
        ):
            return None
        return self._codec.identity_row(copy), restorations

    def _record_buffered_insert(
        self, record: EntityMetadata, declaring: EntityMetadata, instance: EntityBase
    ) -> None:
        """Record the object this transaction just buffered an insert of — the
        read-your-own-writes exemption's whole state.

        Read as the value itself names it (:func:`written_object`) rather than
        through a derived row, because the exemption is asked on a branch that
        must not derive one.
        """
        self._inserted_objects.record(written_object(record, declaring, instance))

    def _has_buffered_insert(
        self, record: EntityMetadata, declaring: EntityMetadata, instance: EntityBase
    ) -> bool:
        """Whether THIS transaction already buffered an insert of the object
        ``instance`` names — the read-your-own-writes half of the provenance
        rule.

        Asked on the branch that would otherwise refuse, so it derives nothing
        from ``instance`` that could fail: a value whose class cannot even name
        an object (:func:`written_object`) is no object this transaction
        inserted, and answering ``False`` for it is what leaves the provenance
        refusal — rather than an ``EntityRowError`` from a row nothing asked for
        — as what the developer sees. A transaction that buffered no insert
        answers without reading ``instance`` at all.
        """
        if not self._inserted_objects:
            return False
        return self._inserted_objects.holds(written_object(record, declaring, instance))

    def _resolve_evidence(
        self,
        record: EntityMetadata,
        declaring: EntityMetadata,
        instance: EntityBase,
        mutation: KeyedMutation,
    ) -> SettledEvidence | None:
        """What a keyed write against existing state settles against — resolved
        once, here, off the value the verb was handed.

        One resolution serves the address, the gate, the version advance, the
        license, and the claim, which is what makes it impossible for them to
        disagree. The evidence comes from the VALUE rather than from a transaction-wide slot:
        the observation belongs to the source that observed it (`m-unit-work`
        "Observation lifetime"), so a standalone ``db.find`` value carries its
        own and a value that came from no read carries none. Which of those
        licenses this write is
        :func:`~parallax.snapshot.handle._write_inputs.resolve_write_evidence`'s
        answer, under the target Entity's own Effective Concurrency Strategy.

        The object a refusal reports comes from the source's own hint where there
        is one, and is derived through the codec only where there is not — the
        two agree by construction, because the read keys its hint by the same
        rule the codec keys a written row by, and deriving it eagerly would cost
        every accepted write an identity row it never uses.

        An object this SAME transaction buffered an insert for is exempt
        (read-your-own-writes: the buffered insert IS the provenance; the planner
        coalesces or orders the pair, `m-unit-work`), and the write that follows
        it settles bare and claims nothing, exactly as the insert does — the row
        it revises is the one that insert opens, so there is no prior row for a
        second intent to compete for and same-object coalescing is what combines
        the pair. Callers invoke this AFTER a
        sparse update's empty-change-set no-op return (the no-op-first ordering
        `m-opt-lock` fixes: a no-op is dropped before any observation concern)
        and AFTER window validation (the window rejects first).
        """
        if self._has_buffered_insert(record, declaring, instance):
            return None
        hint = source_hint_of(instance)
        return resolve_write_evidence(
            self._meta,
            record,
            hint,
            mutation=mutation,
            object_key=(
                hint.object_key
                if hint is not None
                else written_object_key(record, declaring, self._codec.identity_row(instance))
            ),
            preference=self._uow.settings.concurrency,
            participation=self._uow.participation,
        )

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        """Run a participating read for ``query`` and return ``Snapshot[S]``:
        force-flushes pending writes first (read-your-own-writes), and renders
        the read-lock suffix per materialized level from that level's OWN target
        Entity — its Effective Concurrency Strategy, derived from this
        transaction's one Concurrency Preference and the Entity's Optimistic
        Lock Facet, takes the dialect's shared row lock under Locking and none
        under Optimistic. One deep fetch may therefore lock some levels and not
        others. Otherwise identical to :meth:`Database.find` — the SAME
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
        # The classless-connection refusal precedes the read seam deliberately:
        # the gate and the force-flush it stands in front of both live below
        # here, so a Transaction that cannot materialize a Snapshot refuses
        # before either runs.
        construction = _materializing(self._construction)
        node = object_query_node(query)
        return self._read(node, typed_publication(self._meta, construction))

    @property
    def wire(self) -> WireTransactionView:
        """This transaction's Wire read and write interface (spec §3, §5).

        A lightweight view over the SAME unit of work, evidence retention,
        locking, and coalescing the Typed verbs use, so Typed and
        Wire calls mix within one transaction without any cross-interface
        bookkeeping — a Wire node and a Typed node of one row carry the identical
        claim, and a Wire write and a Typed write of one object meet in the one
        claim algebra. The write lane reads the same buffered-insert ledger the
        Typed verbs record into, so read-your-own-writes spans both
        representations.
        """
        return WireTransactionView(
            self._wire_find,
            WireWriteLane(
                self._meta,
                self._uow,
                self._conn,
                self._dialect,
                INERT,
                self._inserted_objects,
            ),
        )

    def _wire_find(self, node: ObjectQueryNode) -> Snapshot[Any]:
        """One participating Wire read, published as its Wire Snapshot.

        What a caller may later write off it rides on the published values
        themselves — each Entity node carries its own Source Hint — so the read
        answers the result and nothing beside it.
        """
        return self._read(node, wire_publication(self._meta))

    def _read[R](self, node: ObjectQueryNode, publication: ResultPublication[R]) -> R:
        """One participating read of ``node``, published through ``publication`` —
        the whole composition both read interfaces run.

        The gate precedes the force-flush ``uow.read`` performs, so a refused
        read flushes nothing, and each level derives its own lock from this unit
        of work's Concurrency Preference and that level's own Entity. A
        milestone-set read retains no evidence at all: its roots stand at
        coordinates no keyed write may address.

        A participating read's Read activity is a child of the current
        Transaction Attempt, opened AFTER the dependency Write Batch the
        force-flush produces so the two are ordered siblings
        (`m-execution-lifecycle`). No Transaction Attempt activity exists yet, so
        this runs against the shared inert activity and emits nothing.
        """
        preflight(node, model=self._meta, form="graph")
        if scans_an_axis(node):
            history_result = self._uow.read(
                lambda: find_history(node, self._meta, self._dialect, self._conn, read=INERT)
            )
            return publication.from_history(history_result)
        find_result = self._uow.read(
            lambda: find(
                node,
                self._meta,
                self._dialect,
                self._conn,
                preference=self._uow.settings.concurrency,
                ledger=self._uow,
                read=INERT,
            )
        )
        return publication.from_find(find_result)

    def read_rows(self, query: ObjectQueryNode) -> RowsResult:
        """Run a PARTICIPATING row-form read and return its published rows.

        The values lane's peer of :meth:`find`, participating in three of the
        same four ways: it force-flushes pending writes first
        (read-your-own-writes), renders the read-lock suffix its target Entity's
        Effective Concurrency Strategy calls for, and publishes its Read
        activity under this attempt exactly as the graph form does.

        It records NO observation. The values lane projects scalars only, so a
        Predecessor Row read off it would be incomplete under Relational Document
        Layout while `m-unit-work` requires a complete one. A caller that needs
        evidence reads the graph form, which is what :meth:`find` and
        ``tx.wire.find`` always run.
        """
        # The gate precedes `uow.read` deliberately, exactly as `find`'s does:
        # that read force-flushes pending buffered writes, so a refused read must
        # be refused before it or a refusal turns into a write.
        preflight(query, model=self._meta, form="rows")
        return self._uow.read(
            lambda: find_rows(
                query,
                self._meta,
                self._dialect,
                self._conn,
                preference=self._uow.settings.concurrency,
                read=INERT,
            )
        )

    def _buffer(
        self,
        mutation: KeyedMutation,
        entity: EntityIdentity,
        row: Mapping[str, object],
        *,
        valid_from: str | None = None,
        until: str | None = None,
        claim: SettledEvidence | None = None,
        restorations: frozenset[str] = frozenset(),
    ) -> None:
        # `claim` is what the verb resolved THIS write settles against, off the
        # value it was handed, and is what `buffered_write` turns into the
        # buffer variant it implies: an `ObservedKeyedWrite` carrying both the
        # observation and the claim where a state was observed, an
        # `ObjectClaimedWrite` where the object's own lock is the evidence, and
        # the bare instruction where the write settles against nothing. Riding
        # the buffered item is what keeps the evidence alive
        # while the write is buffered and what has a successful flush spend
        # exactly the claims its surviving writes carried. The observation is
        # never an instruction field — a
        # `WriteInstruction` is a durable, schema-validated document whose
        # `deserialize` refuses the reserved observation control keys outright —
        # so it rides beside the instruction rather than inside it, exactly as a
        # Materialized Write Group's own observation columns do.
        #
        # The document route buys the IR's structural validation (no `at` alias,
        # no observation keys) first (`keyed_instruction`), and the instruction
        # it yields is then measured by `validate_keyed_instruction`, the SAME
        # judgment in the SAME order every other ingress runs on a keyed
        # instruction it holds.
        #
        # `valid_from` / `until` extend this neutral seam for a TEMPORAL keyed
        # write: a non-temporal or Transaction-Time-Only
        # target's caller never passes them. The typed temporal developer verbs
        # (``update``'s own optional Bitemporal ``valid_from``,
        # ``terminate``, ``update_until``, ``terminate_until``; ``insert``'s own
        # optional Bitemporal ``valid_from`` and ``insert_until``) and the
        # conformance engine's own
        # temporal write translation both pass them the SAME way (`m-txtime-write`
        # / `m-bitemp-write` — the dimension-explicit `validFrom` / `until`
        # instruction fields, never smuggled onto `row`, ADR 0010/0013).
        instruction = keyed_instruction(mutation, entity, row, valid_from=valid_from, until=until)
        validate_keyed_instruction(self._meta, instruction)
        admit_and_buffer(self._uow, self._meta, instruction, claim, restorations=restorations)

    # --- set-based write verbs (python.md §5) ----------------------------- #
    def update_where(
        self,
        query: ObjectQuery[Any, Any],
        *assignments: AttributeAssignment[Any],
        valid_from: dt.datetime | None = None,
    ) -> None:
        """A predicate-selected ``update`` (`python.md` §5): ``query`` MUST be
        mutation-compatible (nothing but a target and a predicate);
        ``assignments`` are ``Attr.set(value)`` calls, non-empty, no duplicate
        field, each addressing the query's exact target. Readless
        (one statement) for an unversioned, non-temporal target; a versioned
        or temporal target MATERIALIZES (`m-opt-lock`, ADR 0014) — see
        :func:`~parallax.snapshot.handle._predicate_writes.buffer_predicate`,
        the neutral seam this and every other ``_where`` verb share."""
        buffer_predicate(
            self._uow,
            self._meta,
            self._conn,
            self._dialect,
            "update",
            query,
            assignments,
            valid_from=valid_from,
            read=INERT,
        )

    def delete_where(self, query: ObjectQuery[Any, Any]) -> None:
        """A predicate-selected ``delete`` over a NON-temporal target
        (`python.md` §5): readless for an unversioned target; a versioned one
        MATERIALIZES to one observation-backed per-row delete per resolved row
        — in both modes, since each row's write requires that row's own prior
        observation — with no no-op elimination, because a delete changes a
        row's existence, never a value (`m-opt-lock`)."""
        buffer_predicate(
            self._uow,
            self._meta,
            self._conn,
            self._dialect,
            "delete",
            query,
            (),
            valid_from=None,
            read=INERT,
        )

    def terminate_where(
        self, query: ObjectQuery[Any, Any], *, valid_from: dt.datetime | None = None
    ) -> None:
        """A predicate-selected ``terminate`` over a TEMPORAL target
        (`python.md` §5): Transaction-Time-Only takes no ``valid_from``;
        Bitemporal requires it. Always materializes — a temporal predicate
        write has no readless template."""
        buffer_predicate(
            self._uow,
            self._meta,
            self._conn,
            self._dialect,
            "terminate",
            query,
            (),
            valid_from=valid_from,
            read=INERT,
        )

    def update_until_where(
        self,
        query: ObjectQuery[Any, Any],
        *assignments: AttributeAssignment[Any],
        valid_from: dt.datetime,
        until: dt.datetime,
    ) -> None:
        """A predicate-selected, Valid-Time-bounded ``updateUntil`` over a
        Bitemporal target (`python.md` §5; `m-bitemp-write` "The rectangle
        split"): always materializes to a close plus head/middle/tail."""
        buffer_predicate(
            self._uow,
            self._meta,
            self._conn,
            self._dialect,
            "updateUntil",
            query,
            assignments,
            valid_from=valid_from,
            until=until,
            read=INERT,
        )

    def terminate_until_where(
        self, query: ObjectQuery[Any, Any], *, valid_from: dt.datetime, until: dt.datetime
    ) -> None:
        """A predicate-selected, Valid-Time-bounded ``terminateUntil`` over
        a Bitemporal target (`python.md` §5): always materializes to a close
        plus head/tail (no middle — the window becomes a hole in Valid
        time)."""
        buffer_predicate(
            self._uow,
            self._meta,
            self._conn,
            self._dialect,
            "terminateUntil",
            query,
            (),
            valid_from=valid_from,
            until=until,
            read=INERT,
        )


def _materializing(
    construction: EntityGraphConstruction | None,
) -> EntityGraphConstruction:
    """The graph construction a modeled read needs, or refuse before ``uow.read``.

    Absent only for the first-party construction that connects a Database to a
    bare accepted Metamodel for neutral write work; ``Database.connect`` admits
    no such model, so an application never reaches this.
    """
    if construction is None:
        raise SnapshotConnectionError(
            "this Transaction's Database was connected to a model that composed no Entity "
            "Class, so it cannot materialize a Snapshot (snapshot-class-backed-model-required)"
        )
    return construction
