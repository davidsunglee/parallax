"""``parallax.snapshot.handle._transaction`` — the developer transaction surface (spec §5).

:class:`Transaction` is what a ``db.transact`` closure receives: a facade over
the active unit of work and the transaction's own connection. It owns the
keyed verbs (``insert`` / ``update`` / ``delete`` and the typed
temporal-window family), the participating :meth:`Transaction.find`, and the
neutral ``_buffer`` instruction seam every keyed verb shares.

It also owns the MODEL-NEUTRAL pair, :meth:`Transaction.read_neutral` and
:meth:`Transaction.write_neutral`, which a caller holding no Entity Class uses in
place of the typed verbs. They are not a second lifecycle: the neutral read
enters the same force-flush, lock derivation, observation recording, and Read
Trace bracket ``find`` does, and the neutral write enters the same
``buffered_write`` carrier decision, the same buffer, and the same flush triggers
the keyed verbs do — one step later, on an instruction already built rather than
on an instance to derive one from.

The predicate-selected ``_where`` family is NOT owned here: those five public
verbs are thin delegates that thread ``(uow, meta, conn, dialect)`` into
:mod:`parallax.snapshot.handle._predicate_writes`, which buffers through
``uow.buffer`` and never reaches back into this class.

Depends on :mod:`parallax.snapshot.handle._preflight` (the shared read gate
``find`` passes before touching the unit of work),
:mod:`parallax.snapshot.handle._read` (the shared find executor plus
the pin / result-conversion helpers ``find`` needs),
:mod:`parallax.snapshot.handle._write_inputs` (verb-input validation and the
observation machinery), and
:mod:`parallax.snapshot.handle._predicate_writes`. Demarcation — ``Database``,
``_Demarcation``, and ``TransactionOptionConflictError`` — lives in
:mod:`parallax.snapshot.handle._database`, which imports this module, never the
reverse.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from parallax.core import opt_lock, read_lock
from parallax.core.db_port import DbPort
from parallax.core.dialect import Dialect
from parallax.core.entity import (
    AttributeAssignment,
    EntityGraphConstruction,
    EntityRowCodec,
    FindQuery,
)
from parallax.core.entity import Entity as EntityBase
from parallax.core.execution_log import AttemptRecorder, ExecutionLog
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel, entity_by_name
from parallax.core.temporal_read import scans_an_axis
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    ObservationKey,
    PredicateWrite,
    UnitOfWork,
    WriteInstruction,
    WriteObservation,
    buffered_write,
    instructions,
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
from parallax.snapshot.handle._preflight import preflight_find, preflight_neutral
from parallax.snapshot.handle._read import (
    NeutralReadRequest,
    NeutralReadResult,
    Snapshot,
    execute_neutral,
    find,
    find_history,
    snapshot_from_find_result,
    snapshot_from_history_result,
)
from parallax.snapshot.handle._write_inputs import (
    ReadObservations,
    WrittenObject,
    metadata_of_instance,
    observation_keying,
    record_observations,
    source_edge,
    source_pin,
    validate_source_pin,
    validate_until,
    validate_valid_from,
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
    ``Snapshot[T]``: force-flush + the transaction's own lock suffix,
    otherwise identical to :meth:`Database.find`. The predicate-selected
    ``_where`` verb family (`python.md` §5) —
    :meth:`update_where`, :meth:`delete_where`, :meth:`terminate_where`,
    :meth:`update_until_where`, :meth:`terminate_until_where` — mirrors the
    keyed surface over a mutation-compatible Find Query: readless for an
    unversioned,
    non-temporal target, materializing to per-row keyed writes otherwise
    (:mod:`parallax.snapshot.handle._predicate_writes`, ADR 0014, which those
    five verbs delegate to). A reference used after
    its owning scope ends raises
    :class:`~parallax.core.unit_work.EscapedTransactionError` (every verb
    delegates to the unit of work, which fences use-after-scope).

    :meth:`read_neutral` and :meth:`write_neutral` are the same two capabilities
    for a caller with no Entity Class: a read that participates exactly as
    :meth:`find` does and publishes each node's Observation Key, and the one
    neutral write ingress, which takes an already-decoded instruction plus the
    evidence it settles against.
    """

    __slots__ = (
        "_attempt",
        "_codec",
        "_conn",
        "_construction",
        "_dialect",
        "_execution_log",
        "_inserted_keys",
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
        # What THIS transaction buffered an insert of, recorded once per insert
        # (`_record_buffered_insert`) in the two readings the two
        # read-your-own-writes exemptions need — a same-transaction insert IS the
        # provenance a subsequent keyed write builds on.
        #
        # The observation slots serve the §5 prior-observation license
        # (`_resolve_observed_milestone`), which runs where a row has already been
        # derived. An inserted instance names no milestone yet, so the slot
        # carries no coordinate and a close derived from that instance resolves to
        # the same one. The written objects serve the keyed-write value provenance
        # refusal (`_has_buffered_insert`), which is decided before any row is
        # derived and therefore cannot ask the codec anything — which is why that
        # slot holds the total reading `written_object` answers for any value.
        self._inserted_keys: set[ObservationKey] = set()
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
        (`m-opt-lock`; ADR 0013): the write seam derives its advance from this
        unit of work's own recorded observation at lowering
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
        row = self._codec.edited_row(copy)
        if row is None:
            return
        self._buffer(
            "update",
            record.identity,
            row,
            valid_from=valid_from_literal,
            observation=self._resolve_observed_milestone(record, declaring, copy),
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
            observation=self._resolve_observation(
                record, declaring_of(self._meta, record), node_or_instance
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
            observation=self._resolve_observed_milestone(record, declaring, node_or_instance),
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
        row = self._codec.edited_row(copy)
        if row is None:
            return
        self._buffer(
            "updateUntil",
            record.identity,
            row,
            valid_from=valid_from_literal,
            until=until_literal,
            observation=self._resolve_observed_milestone(record, declaring, copy),
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
            observation=self._resolve_observed_milestone(record, declaring, node_or_instance),
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

    def _record_buffered_insert(
        self, record: EntityMetadata, declaring: EntityMetadata, instance: EntityBase
    ) -> None:
        """Record a buffered insert in both slots the read-your-own-writes
        exemptions read.

        One write site, so the observation slot a temporal close is exempted by
        and the written object a provenance refusal is exempted by can never
        describe different inserts. Reached only after the insert's own row is
        derived, which is why the codec-derived observation key is free here —
        and why an insert whose value names no object never arrives: deriving
        that row refused it first.
        """
        self._inserted_keys.add(self._observation_key(record, declaring, instance))
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

    def _observation_key(
        self, record: EntityMetadata, declaring: EntityMetadata, instance: EntityBase
    ) -> ObservationKey:
        """``instance``'s observation slot: the object it names AND the milestone
        it came from.

        The identity half is derived through the SAME codec every row this
        transaction buffers comes from — so the key a verb resolves an
        observation by and the row it writes can never read the primary key two
        different ways. The milestone half is the value's own Edge, which the
        read installed from the same axis-start state it recorded the
        observation's Predecessor Row from, so a write settles against the
        milestone the value it was handed actually came from rather than against
        whichever coordinate of that row was read most recently.
        """
        return ObservationKey(
            written_object_key(record, declaring, self._codec.identity_row(instance)),
            source_edge(instance),
        )

    def _resolve_observation(
        self, record: EntityMetadata, declaring: EntityMetadata, instance: EntityBase
    ) -> WriteObservation | None:
        """The Write Observation a keyed write against existing state settles
        against — resolved once, here, from the value the verb was handed, and
        carried to the planner on the buffered write itself.

        One resolution serves the address, the gate, and the version advance,
        which is what makes it impossible for them to disagree. Absence stays
        structural: a target needing no observation resolves to ``None`` and
        buffers bare.

        This resolution refuses nothing of its own. A versioned row has exactly
        one row per primary key, so identity alone addresses it and a value's
        provenance is irrelevant; an unobserved versioned write buffers bare and
        is refused while it is settled
        (:func:`opt_lock.require_observed`), which is what keeps
        same-transaction insert-then-update folding to one INSERT, since
        coalescing decides before any observation concern does. The keyed
        TEMPORAL verbs resolve through :meth:`_resolve_observed_milestone`
        instead, where a miss IS the refusal.
        """
        return self._uow.observation_for(self._observation_key(record, declaring, instance))

    def _resolve_observed_milestone(
        self, record: EntityMetadata, declaring: EntityMetadata, instance: EntityBase
    ) -> WriteObservation | None:
        """:meth:`_resolve_observation` for the four keyed temporal verbs, where a
        miss is a refusal rather than a bare buffer.

        The `python.md` §5 prior-observation license
        (:func:`opt_lock.require_observed_milestone` — the temporal sibling of
        the versioned ``require_observed`` seam the Write Planner's own settling
        consults) is this same resolution: the close must target a milestone THIS
        unit of work observed via a transaction-scoped find, so a miss is the
        refusal. Enforced HERE at
        the developer verb, never inside the planner's own temporal settling —
        the shared planner also serves the neutral engine lane, and demands
        only the observation a close structurally needs to address, gate, and
        carry state forward from, which that lane resolves from its own tracked
        milestone state rather than from a developer's find.

        A value naming NO milestone therefore has no observation to resolve and
        is refused: a fresh instance, an edit of a fresh instance, and a copy
        carried in from another transaction all carry no lifecycle state, so none of
        them can be closed on the strength of some other observation of the same
        primary key. Closing a milestone is spelled "find it, then close what you
        found".

        An object this SAME transaction
        buffered an insert for is exempt (read-your-own-writes: the buffered
        insert IS the provenance; the planner coalesces or orders the pair,
        `m-unit-work`), and the write that follows it settles bare exactly as the
        insert does. Callers invoke this AFTER a sparse update's
        empty-change-set no-op return (the no-op-first ordering `m-opt-lock`
        fixes: a no-op is dropped before any observation concern) and AFTER
        window validation (the window rejects first)."""
        if not declaring.declared_as_of_axes:
            return self._resolve_observation(record, declaring, instance)
        key = self._observation_key(record, declaring, instance)
        if key in self._inserted_keys:
            return None
        observation = self._uow.observation_for(key)
        opt_lock.require_observed_milestone(record.identity.name, observation)
        return observation

    def find[S](self, query: FindQuery[Any, S]) -> Snapshot[S]:
        """Run a participating read for ``query`` and return ``Snapshot[S]``:
        force-flushes pending writes first (read-your-own-writes), and
        the transaction's participation mode renders the read-lock suffix
        (``locking`` takes the dialect's shared row lock; ``optimistic`` takes
        none). Otherwise identical to :meth:`Database.find` — the SAME
        :func:`~parallax.snapshot.handle._preflight.preflight_find` gate, which
        runs BEFORE the force-flush so a refused read flushes nothing, the SAME
        shared find executor, the SAME frozen-node wrapping, and the SAME
        parameter answer: the Snapshot carries the query's RESULT Entity.

        Every materialized node of a VERSIONED entity — root and included
        (deep-fetch) alike — records its observed version on this unit of work
        (`m-opt-lock`; ADR 0013), in EITHER concurrency mode: a later keyed
        update/delete of that SAME object derives its version advance (and,
        under optimistic concurrency, its gate) from THIS observation, never
        from an implicit resolving read at write time. Every materialized node
        of a TEMPORAL entity likewise records its whole observed predecessor
        milestone, filed under the milestone it observed: a later temporal
        write's close/chain derives from THIS observation, never a shadow
        lookup or an implicit resolving read (a MILESTONE-SET read —
        `.history()` / `.as_of_range()` — records nothing here; its own
        dispatch branch returns before this point).
        """
        # Both refusals precede `uow.read` deliberately: that read force-flushes
        # pending buffered writes, so a refused read must be refused before it.
        construction = _materializing(self._construction)
        lowered = preflight_find(query, model=self._meta)
        target, op = lowered.target.canonical, lowered.operation
        lock = read_lock.mode_for(self._uow.settings.concurrency)
        # The Read Trace bracket opens BEFORE the force-flush, so a batch that
        # flush produces is appended first and the trace this read closes lands
        # immediately after it — the read-dependency causality the Execution Log
        # states positionally (`m-execution-log`).
        if scans_an_axis(op):
            with self._attempt.read_trace() as recorder:
                history_result = self._uow.read(
                    lambda: find_history(
                        op, self._meta, self._dialect, target, self._conn, recorder=recorder
                    )
                )
            return snapshot_from_history_result(history_result, self._meta, construction)
        observations = ReadObservations()
        with self._attempt.read_trace() as recorder:
            find_result = self._uow.read(
                lambda: find(
                    op,
                    self._meta,
                    self._dialect,
                    target,
                    self._conn,
                    lock=lock,
                    observations=observations,
                    recorder=recorder,
                )
            )
        record_observations(self._uow, self._meta, observations)
        return snapshot_from_find_result(find_result, self._meta, construction)

    def read_neutral(self, request: NeutralReadRequest) -> NeutralReadResult:
        """Run a PARTICIPATING neutral read and return its materialized output.

        The neutral peer of :meth:`find`, and participating in exactly the same
        four ways: it force-flushes pending writes first (read-your-own-writes),
        renders the transaction's own read-lock suffix from its participation
        mode, records what a later write settles against, and appends its Read
        Trace to this attempt in the position that states the read-dependency
        causality. A caller with no Entity Class therefore gets the same
        transaction semantics a typed reader gets, not a weaker read path beside
        them.

        Each materialized node additionally publishes the Observation Key its
        evidence was filed under, which is how a class-less caller settles a
        later :meth:`write_neutral` against the row this read actually saw
        rather than against a key it reconstructed. A row-form request and a
        milestone-set request each record no evidence and publish no key
        (`_read.execute_neutral`).
        """
        # The gate precedes `uow.read` deliberately, exactly as `find`'s does:
        # that read force-flushes pending buffered writes, so a refused read must
        # be refused before it or a refusal turns into a write.
        preflight_neutral(request.target, request.operation, model=self._meta, form=request.form)
        lock = read_lock.mode_for(self._uow.settings.concurrency)
        observations = ReadObservations()
        # The bracket opens BEFORE the force-flush, exactly as `find`'s does, so
        # a dependency batch lands immediately before the trace it enabled.
        with self._attempt.read_trace() as recorder:
            result = self._uow.read(
                lambda: execute_neutral(
                    request,
                    self._meta,
                    self._dialect,
                    self._conn,
                    lock=lock,
                    observations=observations,
                    recorder=recorder,
                    observed=observation_keying(self._meta),
                )
            )
        record_observations(self._uow, self._meta, observations)
        return result

    def write_neutral(
        self,
        instruction: WriteInstruction,
        *,
        observation: ObservationKey | WriteObservation | None = None,
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
        An :class:`~parallax.core.unit_work.ObservationKey` resolves IMMEDIATELY
        and exactly against this unit of work — a key naming no recorded
        observation raises
        :class:`~parallax.snapshot.handle._errors.UnobservedWriteError` here, at
        the call that supplied it, rather than settling to a bare write whose
        refusal would surface at flush naming the wrong cause. A
        :class:`~parallax.core.unit_work.WriteObservation` is evidence a caller
        holds directly and is used as given. ``None`` buffers bare, which is what
        an insert and an unobserved target need.

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
        self._uow.buffer(buffered_write(instruction, self._resolved_observation(observation)))

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

    def _resolved_observation(
        self, observation: ObservationKey | WriteObservation | None
    ) -> WriteObservation | None:
        """The evidence a neutral write settles against, resolving a KEY here.

        A key is a reference into this unit of work's own observation record, so
        it is dereferenced at the call rather than carried to planning: an
        unresolvable key is a caller error about what was read, and reporting it
        at flush would report it as a licensing failure about what is being
        written. The unit of work's own scope fence answers first, so a key used
        after its transaction ended raises as the escaped reference it is.
        """
        if not isinstance(observation, ObservationKey):
            return observation
        resolved = self._uow.observation_for(observation)
        if resolved is None:
            raise UnobservedWriteError(
                "no observation is recorded in this unit of work for "
                f"{observation.object_key.entity.canonical} under the milestone this key "
                "names; a neutral write settles against evidence a read of THIS "
                "transaction recorded"
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
        observation: WriteObservation | None = None,
    ) -> None:
        # `observation` is what the verb resolved for THIS write from the value
        # it was handed, and `buffered_write` turns it into the buffer variant it
        # implies: an `ObservedKeyedWrite` when there is one, the bare
        # instruction when there is not. The observation is never an
        # instruction field — a
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
        self._uow.buffer(buffered_write(instruction, observation))

    # --- set-based write verbs (python.md §5) ----------------------------- #
    def update_where(
        self,
        query: FindQuery[Any, Any],
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

    def delete_where(self, query: FindQuery[Any, Any]) -> None:
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
        self, query: FindQuery[Any, Any], *, valid_from: dt.datetime | None = None
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
        query: FindQuery[Any, Any],
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
        self, query: FindQuery[Any, Any], *, valid_from: dt.datetime, until: dt.datetime
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
