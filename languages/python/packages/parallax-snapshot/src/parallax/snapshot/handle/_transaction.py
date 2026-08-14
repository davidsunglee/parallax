"""``parallax.snapshot.handle._transaction`` — the developer transaction surface (spec §5).

:class:`Transaction` is what a ``db.transact`` closure receives: a facade over
the active unit of work and the transaction's own connection. It owns the
keyed verbs (``insert`` / ``update`` / ``delete`` and the typed
temporal-window family), the participating :meth:`Transaction.find`, and the
neutral ``_buffer`` instruction seam every keyed verb shares — which ends at
``_admit_and_buffer``, where a write's claim at the scope it settles against is
taken and an intent the buffer's existing claim cannot absorb is refused.

It also owns the row-form read (:meth:`Transaction.read_rows`) and the two
FIRST-PARTY members of the conformance bridge —
:meth:`Transaction.observed_read` and :meth:`Transaction.write_neutral` — which
are not developer surface and end with the Wire write verbs. None of the three is
a second lifecycle: each read enters the same force-flush, lock derivation,
evidence retention, and Read Trace bracket ``find`` does, and the bridge write
enters the same ``buffered_write`` carrier decision, the same buffer, and the
same flush triggers the keyed verbs do — one step later, on an instruction
already built rather than on an instance to derive one from.

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
from dataclasses import dataclass
from typing import Any

from parallax.core import opt_lock
from parallax.core.db_port import DbPort
from parallax.core.dialect import Dialect
from parallax.core.entity import (
    AttributeAssignment,
    EntityGraphConstruction,
    EntityRowCodec,
)
from parallax.core.entity import Entity as EntityBase
from parallax.core.execution_log import AttemptRecorder, ExecutionLog
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel, entity_by_name
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.temporal_read import scans_an_axis
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    ObservedStateKey,
    PredicateWrite,
    RetainedObservation,
    SettledEvidence,
    TemporalStateKey,
    UnitOfWork,
    VersionedStateKey,
    WriteInstruction,
    WriteObservation,
    buffered_write,
    claim_scope,
    instructions,
    keyed_intent,
    object_key,
    validate_write,
)

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot.handle._errors import SnapshotConnectionError, UnobservedWriteError
from parallax.snapshot.handle._family import declaring as declaring_of
from parallax.snapshot.handle._predicate_writes import (
    buffer_predicate,
    buffer_predicate_instruction,
)
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._read import (
    ResultPublication,
    RowsResult,
    Snapshot,
    find,
    find_history,
    find_rows,
    published_claims,
    typed_publication,
    wire_publication,
)
from parallax.snapshot.handle._wire import WireTransactionView
from parallax.snapshot.handle._write_inputs import (
    WrittenObject,
    admit_write_claim,
    metadata_of_instance,
    resolve_write_evidence,
    source_hint_of,
    source_pin,
    validate_source_pin,
    validate_until,
    validate_valid_from,
    validate_write_value,
    written_object,
    written_object_key,
)


@dataclass(frozen=True, slots=True)
class ObservedRead:
    """A participating Wire read paired with the claims its published nodes carry.

    The conformance bridge's own read value, and nothing a developer holds: a
    Snapshot is the whole public result, and an observed-state address is
    implementation state. Both halves come from one read, so pairing them here is
    what keeps a bridge caller from re-deriving evidence that would then have to
    agree with production's by inspection. Holding the retained observations is
    also what keeps them alive for the bridge's later writes, exactly as holding
    the published values would.
    """

    snapshot: Snapshot[Any]
    observations: tuple[RetainedObservation, ...]


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

    :attr:`wire` is the Wire read interface over this same transaction — a view,
    not a second lifecycle, so a Wire read participates exactly as :meth:`find`
    does.

    :meth:`read_rows` is the values lane over this same transaction — a
    first-party row-form read, not a third public result format.
    :meth:`observed_read` and :meth:`write_neutral` are the first-party
    conformance bridge: a Wire read that additionally answers the evidence it
    retained, and the write ingress that takes an already-decoded instruction plus
    whatever observed state a caller holds for it. Neither is developer surface,
    and both end when the Wire write verbs land.
    """

    __slots__ = (
        "_attempt",
        "_codec",
        "_conn",
        "_construction",
        "_dialect",
        "_execution_log",
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
        execution_log: ExecutionLog,
        attempt: AttemptRecorder,
    ) -> None:
        self._uow = uow
        self._conn = conn
        self._meta = meta
        self._dialect = dialect
        self._construction = construction
        self._codec = codec
        # The invocation's own live log (`m-execution-log`) and the writer for the
        # attempt this Transaction belongs to. The log spans every attempt and is
        # the SAME object a joining call's result carries; the recorder is scoped
        # to this one attempt, and a retry receives a fresh Transaction with a
        # fresh recorder over the SAME log.
        self._execution_log = execution_log
        self._attempt = attempt
        # What THIS transaction buffered an insert of — a same-transaction insert
        # IS the provenance a subsequent keyed write builds on, so both
        # read-your-own-writes exemptions (the value-provenance refusal and the
        # write-evidence resolution) read this one slot. It holds the total
        # reading `written_object` answers for any value rather than a derived
        # row's, because the provenance refusal is decided before any row is
        # derived and therefore cannot ask the codec anything.
        self._inserted_objects: set[WrittenObject | None] = set()

    @property
    def execution_log(self) -> ExecutionLog:
        """This invocation's live Execution Log (`m-execution-log`).

        The SAME stable read-only object throughout: its current attempt is
        ``active`` while this body runs, completed traces appear on it as they
        close, and it seals when the outermost invocation terminates. It is how a
        caller that retained the Transaction inspects failed attempts after
        ``db.transact`` raised and no result exists.
        """
        return self._execution_log

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
        own Bitemporal-only-required :func:`validate_valid_from`: a
        Transaction-Time-Only or non-temporal target takes none (no Valid-Time dimension to
        bound)."""
        record, declaring, valid_from_literal = self._prepare_keyed_write(
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
        (:func:`validate_until`, `python.md` §5 "all validated at build").
        The window bounds come from THESE verb arguments, never from instance
        fields: an As-Of Axis endpoint is framework-owned and the temporal write
        path derives every interval bound itself (`python.md` §2), which is why
        the Entity constructor refuses an authored one outright."""
        record, declaring, valid_from_literal = self._prepare_keyed_write(
            instance, "insertUntil", valid_from
        )
        until_literal = validate_until(declaring, "insertUntil", valid_from, until)
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
        :func:`validate_valid_from`: a Transaction-Time-Only or non-temporal target
        takes none (no Valid-Time dimension to bound)."""
        record, declaring, valid_from_literal = self._prepare_keyed_write(
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
        :func:`validate_valid_from`)."""
        record, declaring, valid_from_literal = self._prepare_keyed_write(
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
        (:func:`validate_until`, `python.md` §5 "all validated at build") —
        checked BEFORE the empty-effective-change-set no-op return below:
        window validation runs first for every window verb, never after;
        equal bounds reject even when the
        edited copy's own Change Record nets to zero). An EMPTY effective
        change set (once the window is confirmed valid) issues no DML at all,
        exactly like keyed ``update``."""
        record, declaring, valid_from_literal = self._prepare_keyed_write(
            copy, "updateUntil", valid_from
        )
        until_literal = validate_until(declaring, "updateUntil", valid_from, until)
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
        call, before any buffering (:func:`validate_until`, `python.md`
        §5)."""
        record, declaring, valid_from_literal = self._prepare_keyed_write(
            node_or_instance, "terminateUntil", valid_from
        )
        until_literal = validate_until(declaring, "terminateUntil", valid_from, until)
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
    ) -> tuple[EntityMetadata, EntityMetadata, str | None]:
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
        validate +
        render ``valid_from`` against that declaring entity's own
        temporality (:func:`validate_valid_from`, spec §5). Returns the
        record (``_buffer``'s own entity-name argument), the declaring entity
        (a ``*Until`` verb's own :func:`validate_until` needs it too, for
        its error message), and the rendered instant literal (``None`` for a
        non-temporal/audit-only target)."""
        record = metadata_of_instance(self._meta, node_or_instance)
        declaring = declaring_of(self._meta, record)
        validate_source_pin(record.identity, source_pin(node_or_instance))
        validate_write_value(
            record.identity,
            node_or_instance,
            mutation,
            inserted_here=lambda: self._has_buffered_insert(record, declaring, node_or_instance),
        )
        valid_from_literal = validate_valid_from(declaring, mutation, valid_from)
        return record, declaring, valid_from_literal

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
        if not restorations or not self._cancels_a_pending_assignment(record, copy, mutation):
            return None
        return self._codec.identity_row(copy), restorations

    def _cancels_a_pending_assignment(
        self, record: EntityMetadata, copy: EntityBase, mutation: KeyedMutation
    ) -> bool:
        """Whether this transaction already buffered an ASSIGNMENT at the scope
        ``copy``'s own write would claim.

        Read off the value's own hint rather than off a derived row, and at
        whatever scope the target Entity's Optimistic Key names, so the question
        is asked exactly where the verb about to buffer would take its claim: a
        versioned write settling against a different generation of the same row
        is a different claim and taking it back is not something this value said,
        while an unversioned Non-Temporal row has one claim per object because
        that is the grain its shared row lock is held at.

        Asked before the write's evidence is resolved, which is what keeps the
        no-op-first ordering `m-opt-lock` fixes: a net-zero chain off a value the
        verb would refuse still buffers nothing rather than raising.

        A value carrying no hint came from no read and can cancel nothing. A hint
        that IS there always reaches a scope for an update verb: it names an
        Object Key unconditionally, and it retains an observation for exactly the
        state-keyed targets whose arm needs one
        (:class:`~parallax.core.unit_work.SourceHint`).
        """
        hint = source_hint_of(copy)
        if hint is None:
            return False
        scope = claim_scope(
            opt_lock.settled_evidence(
                opt_lock.optimistic_key(self._meta, record.identity),
                mutation,
                object_key=hint.object_key,
                observation=hint.observation,
            )
        )
        if scope is None:  # pragma: no cover - a hint reaches its target's own arm
            return False
        held = self._uow.claimed(scope)
        return held is not None and held.kind == "assignment"

    def _record_buffered_insert(
        self, record: EntityMetadata, declaring: EntityMetadata, instance: EntityBase
    ) -> None:
        """Record the object this transaction just buffered an insert of — the
        read-your-own-writes exemption's whole state.

        Read as the value itself names it (:func:`written_object`) rather than
        through a derived row, because the exemption is asked on a branch that
        must not derive one.
        """
        self._inserted_objects.add(written_object(record, declaring, instance))

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
        object_written = written_object(record, declaring, instance)
        return object_written is not None and object_written in self._inserted_objects

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
        """This transaction's Wire read interface (spec §3).

        A lightweight view over the SAME unit of work, evidence retention,
        locking, and Execution Log the Typed verbs use, so Typed and Wire calls
        mix within one transaction without any cross-interface bookkeeping — and
        a Wire node and a Typed node of one row carry the identical claim.
        """
        return WireTransactionView(self._wire_find)

    def _wire_find(self, node: ObjectQueryNode) -> Snapshot[Any]:
        """One participating Wire read, dropping what only the bridge asks for."""
        return self._observed_wire_find(node).snapshot

    def _observed_wire_find(self, node: ObjectQueryNode) -> ObservedRead:
        """One participating Wire read, paired with the claims its PUBLISHED
        nodes carry.

        The evidence is read off the published values rather than off the read's
        own retained sources, because a claim belongs to a published Entity node:
        a projection nothing published — every node under a non-hydrating root —
        is a value no caller holds, and holding its evidence here would keep
        write authority alive for a row this read published nothing for.
        """
        snapshot = self._read(node, wire_publication(self._meta))
        return ObservedRead(snapshot, published_claims(snapshot))

    def _read[R](self, node: ObjectQueryNode, publication: ResultPublication[R]) -> R:
        """One participating read of ``node``, published through ``publication`` —
        the whole composition both read interfaces run.

        The gate precedes the force-flush ``uow.read`` performs, so a refused
        read flushes nothing; each level derives its own lock from this unit of
        work's Concurrency Preference and that level's own Entity; and the
        Read Trace bracket opens BEFORE that flush, so a batch the flush produces
        is appended first and the trace this read closes lands immediately after
        it — the read-dependency causality the Execution Log states positionally
        (`m-execution-log`). A milestone-set read retains no evidence at all: its
        roots stand at coordinates no keyed write may address.
        """
        preflight(node, model=self._meta, form="graph")
        if scans_an_axis(node):
            with self._attempt.read_trace() as recorder:
                history_result = self._uow.read(
                    lambda: find_history(
                        node, self._meta, self._dialect, self._conn, recorder=recorder
                    )
                )
            return publication.from_history(history_result)
        with self._attempt.read_trace() as recorder:
            find_result = self._uow.read(
                lambda: find(
                    node,
                    self._meta,
                    self._dialect,
                    self._conn,
                    preference=self._uow.settings.concurrency,
                    ledger=self._uow,
                    recorder=recorder,
                )
            )
        return publication.from_find(find_result)

    def observed_read(self, query: ObjectQueryNode) -> ObservedRead:
        """A participating Wire read paired with the claims its published nodes
        carry — the FIRST-PARTY read half of the conformance bridge, not
        developer surface.

        ``tx.wire.find`` answers the Snapshot alone, which is everything a
        developer can act on: an observation address is implementation state no
        public surface exposes. The conformance engine settles its own writes
        against the exact evidence production retained rather than against a
        second derivation, so it needs the pair, and it holds first-party access
        to ask for it. Holding those claims is also what keeps them alive for its
        later writes, exactly as holding the published values would. Both halves
        come from ONE read — the same statements, the same lock, the same trace —
        so nothing here is a second execution path.
        """
        return self._observed_wire_find(query)

    def read_rows(self, query: ObjectQueryNode) -> RowsResult:
        """Run a PARTICIPATING row-form read and return its published rows.

        The values lane's peer of :meth:`find`, participating in three of the
        same four ways: it force-flushes pending writes first
        (read-your-own-writes), renders the read-lock suffix its target Entity's
        Effective Concurrency Strategy calls for, and appends its Read Trace to
        this attempt in the position that states the read-dependency causality.

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
        # The bracket opens BEFORE the force-flush, exactly as `find`'s does, so
        # a dependency batch lands immediately before the trace it enabled.
        with self._attempt.read_trace() as recorder:
            return self._uow.read(
                lambda: find_rows(
                    query,
                    self._meta,
                    self._dialect,
                    self._conn,
                    preference=self._uow.settings.concurrency,
                    recorder=recorder,
                )
            )

    def write_neutral(
        self,
        instruction: WriteInstruction,
        *,
        observation: ObservedStateKey | WriteObservation | None = None,
    ) -> None:
        """Buffer an already-decoded write instruction — the ONE neutral runtime
        write ingress.

        The neutral peer of the typed verbs, entered one step later: a typed verb
        derives an instruction from an instance and resolves that instance's own
        observation, and this takes both already built. Everything downstream is
        identical — the same carrier decision
        (:func:`~parallax.core.unit_work.buffered_write`), the same unit of work,
        the same planner, the same flush triggers. There is no neutral write on
        ``Database`` and no developer-controlled flush: a buffered write executes
        only when production semantics require a dependency batch or the outer
        boundary's finalization.

        ``observation`` states the evidence three ways, and only three.
        An :data:`~parallax.core.unit_work.ObservedStateKey` resolves IMMEDIATELY
        and exactly against this unit of work — a key naming no reachable
        observation raises
        :class:`~parallax.snapshot.handle._errors.UnobservedWriteError` here, at
        the call that supplied it, rather than settling to a bare write whose
        refusal would surface at flush naming the wrong cause. A
        :class:`~parallax.core.unit_work.WriteObservation` is evidence a caller
        holds directly and is used as given, and claims nothing; a target
        entitled to none refuses it where a resolved one is refused, rather than
        having it dropped in favour of a claim the call never stated. ``None`` is
        what an insert and an unversioned Non-Temporal write supply, which is not
        the same answer: what each of them settles against is derived from the
        target Entity's own Optimistic Key here, exactly as a typed verb derives
        it, so an unversioned existing-row write claims its object through this
        ingress too and an insert claims nothing through either.

        A predicate-selected instruction carries no observation of its own — it
        materializes to a Materialized Write Group with its own observation
        columns — so supplying one with a
        :class:`~parallax.core.unit_work.PredicateWrite` is refused rather than
        silently dropped. That refusal is about the CALL rather than about the
        model, so it precedes validation: an instruction and an evidence
        argument that cannot go together are answered before either is measured.

        Each shape then reaches the SAME judgments its typed peer does, which is
        what makes this ingress classify an instruction exactly as the typed
        verbs do rather than leave a class-less caller to pre-validate for
        itself. A predicate-selected instruction reaches
        :func:`~parallax.core.unit_work.instructions.validate_instruction`, the
        whole of what the ``_where`` verbs measure through
        :func:`~parallax.snapshot.handle._predicate_writes.buffer_predicate`'s
        own step 5. A KEYED instruction reaches ``_validate_keyed``, which is
        exactly what the typed verbs' own ``_buffer`` runs on the instruction it
        builds.
        """
        if isinstance(instruction, PredicateWrite):
            if observation is not None:
                raise TypeError(
                    "a predicate-selected write resolves its own per-row evidence and takes "
                    "no observation; buffer the keyed writes it materializes to instead"
                )
            instructions.validate_instruction(instruction, self._meta)
            buffer_predicate_instruction(
                self._uow, self._meta, self._conn, self._dialect, instruction, self._attempt
            )
            return
        self._validate_keyed(instruction)
        resolved = (
            self._resolved_claim(observation)
            if isinstance(observation, VersionedStateKey | TemporalStateKey)
            else observation
        )
        self._admit_and_buffer(instruction, self._settled_evidence(instruction, resolved))

    def _validate_keyed(self, instruction: KeyedWrite) -> None:
        """The whole judgment a keyed write instruction is measured by, in the one
        order both this transaction's ingresses run it in.

        The model-aware :func:`~parallax.core.unit_work.validate_write` per row
        FIRST: its inheritance payload-shape rules
        (``subtype-write-metadata-field`` / ``-sibling-attribute`` /
        ``-set-based-unsupported``, `m-inheritance`) classify a framework-owned
        metadata key or a cross-branch field MORE SPECIFICALLY than the generic
        member-name honesty gate ever could. Then
        :func:`~parallax.core.unit_work.instructions.validate_instruction`, which
        still catches any OTHERWISE-unknown member the row walk left unexamined
        (it walks only DECLARED members, never flags a stray key itself).

        Extracted rather than spelled at each ingress because the ORDER is the
        rule: a typed verb and a neutral keyed instruction that classified the
        same defect differently would make the ingress, not the model, decide what
        a write violated.

        A spelling naming no single declared Entity is left entirely to
        ``validate_instruction``, which owns that classification and refuses it one
        step later: a row judgment presupposes the target whose members it is
        measured against, so an unresolvable target has no row question to answer,
        and answering it here would report a member complaint about an Entity the
        model does not have.
        """
        entity = entity_by_name(self._meta, instruction.entity)
        if entity is not None:
            for row in instruction.rows:
                validate_write(entity, row, self._meta, mutation=instruction.mutation)
        instructions.validate_instruction(instruction, self._meta)

    def _settled_evidence(
        self, instruction: KeyedWrite, observation: RetainedObservation | WriteObservation | None
    ) -> SettledEvidence | None:
        """What ``instruction`` settles against, for a caller holding an
        instruction rather than the value it was derived from.

        Evidence the caller supplied is what the write settles against, used as
        given: it is the one licensed way a keyed write settles against a row no
        read of this unit of work materialized, so a target that can hold none
        REFUSES it — an insert at the carrier, an unversioned Non-Temporal row
        where the write is settled — rather than having it dropped for a claim
        the caller never stated.

        A caller who supplied none reaches the derivation the typed verbs read
        off a source value's hint (:meth:`_resolve_evidence`), taken here from
        the instruction's own target and mutation, which is everything it needs.
        A bridge caller therefore cannot buffer an unversioned Non-Temporal write
        that claims nothing where a developer's own verb would have claimed its
        object, and the coalescing a case witnesses is the coalescing a program
        gets.
        """
        if observation is not None:
            return observation
        return opt_lock.settled_evidence(
            opt_lock.optimistic_key(self._meta, _instruction_identity(self._meta, instruction)),
            instruction.mutation,
            object_key=object_key(instruction, self._meta),
            observation=None,
        )

    def _resolved_claim(self, key: ObservedStateKey) -> RetainedObservation:
        """The retained evidence a neutral write claims, resolving a KEY here.

        A key is a reference into this unit of work's own weak index, so it is
        dereferenced at the call rather than carried to planning: an unresolvable
        key is a caller error about what was read, and reporting it at flush would
        report it as a licensing failure about what is being written. The unit of
        work's own scope fence answers first, so a key used after its transaction
        ended raises as the escaped reference it is.

        A caller-held :class:`~parallax.core.unit_work.WriteObservation` never
        reaches here: it is a value rather than a reference into the ledger, so
        there is no retained evidence for a flush to spend.
        """
        resolved = self._uow.retained_for(key)
        if resolved is None:
            raise UnobservedWriteError(
                "no observation is reachable in this unit of work for "
                f"{key.object.entity.canonical} under the state this key "
                "names; a neutral write settles against evidence a read of THIS "
                "transaction retained"
            )
        return resolved

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
        # no observation keys) first (`deserialize`), and the instruction it
        # yields is then measured by `_validate_keyed`, the SAME judgment in the
        # SAME order `write_neutral` runs on a keyed instruction it was handed.
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
        doc: dict[str, object] = {
            "mutation": mutation,
            "entity": entity.canonical,
            "rows": [dict(row)],
        }
        if valid_from is not None:
            doc["validFrom"] = valid_from
        if until is not None:
            doc["until"] = until
        instruction = instructions.deserialize(doc)
        assert isinstance(instruction, KeyedWrite)  # `doc` carries `rows`
        self._validate_keyed(instruction)
        self._admit_and_buffer(instruction, claim, restorations=restorations)

    def _admit_and_buffer(
        self,
        instruction: KeyedWrite,
        evidence: SettledEvidence | None,
        *,
        restorations: frozenset[str] = frozenset(),
    ) -> None:
        """Take this write's claim at the scope it settles against, then buffer it.

        The claim is the last judgment a keyed write passes, so a refused intent
        leaves nothing behind: the instruction is already fully validated, and
        the buffer and the claim it could not join are both untouched.

        Scope and intent are read off what the write settles against and what its
        verb does, and the two are absent together: an insert opens a row rather
        than writing against one, so it has neither. A caller-HELD Write
        Observation carries an intent but no scope, for the reason it spends
        nothing at the flush — it is a value rather than a reference into this
        scope's ledger, so there is no retained evidence a second intent could be
        competing for. Finalization still combines two such writes when they
        address one object and carry equal evidence, because what it coalesces is
        the intent rather than the claim.
        """
        admit_write_claim(
            self._uow,
            _instruction_identity(self._meta, instruction),
            keyed_intent(instruction),
            scope=claim_scope(evidence),
        )
        self._uow.buffer(buffered_write(instruction, evidence, restorations=restorations))

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
            attempt=self._attempt,
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
            attempt=self._attempt,
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
            attempt=self._attempt,
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
            attempt=self._attempt,
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
            attempt=self._attempt,
        )


def _instruction_identity(meta: Metamodel, instruction: KeyedWrite) -> EntityIdentity:
    """The Entity Identity ``instruction``'s own spelling names.

    Read by a refusal message and by the claim-scope derivation, both of which
    run after validation has already resolved the spelling; the fallback keeps
    the message honest — and leaves the derivation on the arm an unrecognized
    Entity takes everywhere else — for a spelling this model somehow does not
    carry, rather than raising a second failure while reporting the first.
    """
    entity = entity_by_name(meta, instruction.entity)
    if entity is None:  # pragma: no cover - validation resolved the spelling already
        return EntityIdentity(namespace="", name=instruction.entity)
    return entity.identity


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
