"""``parallax.snapshot.handle._transaction`` — the developer transaction surface (spec §5).

:class:`Transaction` is what a ``db.transact`` closure receives: a facade over
the active unit of work and the transaction's own connection. It owns the
keyed verbs (``insert`` / ``update`` / ``delete`` and the typed
temporal-window family) and the participating :meth:`Transaction.find`.

What a keyed verb here OWNS is one adapter and one call. The order every keyed
write runs — re-entry, source, pin, window, preparation, effective changes,
the buffered-insert exemption, evidence, claim, and buffer — belongs to
:mod:`parallax.snapshot.handle._keyed_writes`, and what this module supplies is
the Typed Keyed Write Source and Keyed Insert Source: what an Entity value, its
Change Record, and its lifecycle answer that order, and nothing about the order
itself. The Wire verbs supply their own and the two meet in one judgement and
one buffer.

It also carries the row-form read (:meth:`Transaction.read_rows`), which the
conformance harness reaches and no developer surface does. It is not a second
lifecycle: the read enters the same force-flush and lock derivation ``find``
does, and opens its own Read under this transaction's attempt exactly as every
participating read here does.

The read COMPOSITION is not owned here either. :meth:`Transaction.find`,
:meth:`Transaction.stream`, and :meth:`Transaction.read_rows` delegate to the one
participating :class:`~parallax.snapshot.handle._read_scope.ReadScope` this
transaction constructs, which runs the same ladder a ``Database``'s standalone
reads run, under a participating execution policy rather than a standalone one.
The ``tx.wire`` view retains that same scope rather than anything cut from this
class, and so does every stream this transaction opens — which is why each page
force-flushes and opens its Stream Batch through the same policy an eager read
here runs under.

The predicate-selected ``_where`` family is NOT owned here: those five public
verbs are thin delegates that thread ``(uow, meta, conn)`` into
:mod:`parallax.snapshot.handle._predicate_writes`, which buffers through
``uow.buffer`` and never reaches back into this class.

Depends on :mod:`parallax.snapshot.handle._read_scope` (the read composition the
eager read verbs here delegate to),
:mod:`parallax.snapshot.handle._read` (the publication factories and the result
surface), :mod:`parallax.snapshot.handle._keyed_writes` (the keyed write ingress,
whose per-call context this transaction builds once and hands to its own keyed
verbs, to ``tx.wire``'s, and to the conformance bridge alike),
:mod:`parallax.snapshot.handle._write_inputs` (the steps the Typed sources
themselves run — instance resolution, the source pin and identity row a value
states, and the object a written row addresses), and
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
from parallax.core.entity import (
    AttributeAssignment,
    EntityRowCodec,
    lifecycle_state_of,
)
from parallax.core.entity import Entity as EntityBase
from parallax.core.execution_lifecycle._activity import (
    InstalledLifecycle,
    TransactionAttemptActivity,
    refuse_reentry,
)
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery
from parallax.core.unit_work import (
    KeyedMutation,
    UnitOfWork,
    instructions,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTemporalBounds,
)

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle._keyed_writes import (
    KeyedWriteContext,
    PreparedSourceWrite,
    Provenance,
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
    keyed_insert,
    keyed_write,
)
from parallax.snapshot.handle._predicate_writes import (
    buffer_predicate,
    buffer_predicate_instruction,
)
from parallax.snapshot.handle._read import RowsResult, Snapshot
from parallax.snapshot.handle._read_scope import SelectedReadModel, participating_read_scope
from parallax.snapshot.handle._stream import SnapshotStream
from parallax.snapshot.handle._wire import WireTransactionView
from parallax.snapshot.handle._wire_writes import WireWriteLane, buffer_prepared_keyed_write
from parallax.snapshot.handle._write_inputs import (
    UPDATE_MUTATIONS,
    BufferedInserts,
    keyed_instruction,
    metadata_of_instance,
    source_hint_of,
    source_identity_row,
    source_pin,
    written_object_key,
)


def provenance_of(value: EntityBase) -> Provenance:
    """Which framework-managed source produced ``value``.

    Read through :func:`~parallax.snapshot._inspection.snapshot_state_of` and the
    un-narrowed :func:`~parallax.core.entity.lifecycle_state_of`, never through a
    value's private state: the narrowed answer says THIS Snapshot lifecycle
    produced the value, and the un-narrowed one is what distinguishes another
    framework-managed source's value from one no managed read produced at all.

    It lives beside the Typed verbs because only a Typed value carries a
    lifecycle to read: a Wire source answers the same fact from the Source Hint
    its read filed, and what the keyed write judges is the answer rather than
    either carrier.
    """
    if lifecycle_state_of(value) is None:
        return "none"
    if snapshot_state_of(value) is None:
        return "foreign"
    return "this"


def prepared_typed_write(
    meta: Metamodel,
    mutation: KeyedMutation,
    entity: EntityMetadata,
    row: Mapping[str, object],
    bounds: PreparedTemporalBounds,
) -> PreparedKeyedWrite:
    """One authored single-row keyed instruction, measured by Unit Work's sole
    typed judgment — member names, values, and assignment legality together.

    The bounds ride the instruction's dimension-explicit fields rather than the
    row (ADR 0010/0013): an As-Of Axis endpoint is framework-owned, so a
    Valid-Time bound is never a member a caller could author.
    """
    prepared = instructions.prepare_typed_write(
        keyed_instruction(
            mutation, entity.identity, row, valid_from=bounds.valid_from, until=bounds.until
        ),
        meta,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


class TypedKeyedWriteSource:
    """The Typed Keyed Write Source: what an Entity value and its Change Record
    answer the keyed write ingress.

    Inert when constructed and private to one verb call, so nothing it can refuse
    runs before the ingress refuses re-entry. :meth:`capture` judges nothing at
    all — a Typed value's shape is fixed by its class, and ``edit()`` has already
    judged every assignment its Change Record holds, which is why the authoring
    refusals the Wire lane raises at its own capture reach a Typed caller before a
    verb ever receives a value.

    The mutation and the accepted Metamodel arrive at the phases the protocol
    hands them to and are retained for :meth:`prepare`, which authors the
    instruction and is handed neither.
    """

    __slots__ = ("_codec", "_meta", "_mutation", "_value")

    def __init__(self, value: EntityBase, codec: EntityRowCodec) -> None:
        self._value = value
        self._codec = codec
        self._meta: Metamodel | None = None
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedWriteSource:
        """The facts this value states about the state the write revises."""
        self._meta = model
        self._mutation = mutation
        entity = metadata_of_instance(model, self._value)
        return ResolvedKeyedWriteSource(
            entity=entity,
            pin=source_pin(self._value),
            hint=source_hint_of(self._value),
            identity_row=source_identity_row(entity, model, self._value),
            provenance=provenance_of(self._value),
        )

    def prepare(
        self, resolved: ResolvedKeyedWriteSource, bounds: PreparedTemporalBounds, /
    ) -> PreparedSourceWrite:
        """The instruction this value authors, beside its own originals.

        Both sides run through the SAME producer: an update family verb measures
        the Change Record's two halves — every touched member at the value it now
        holds, and those same members at the value the chain first recorded — so
        the ingress weighs effectiveness over canonical values on both sides
        rather than over a serialized document on one. A destructive or close verb
        names no member at all and authors its identity row alone, and so does an
        update off a value whose chain touched nothing.

        The object a refusal reports comes from the source's own hint where there
        is one, and is derived from the authored row where there is not — the two
        agree by construction, because a read keys its hint by the same rule a
        written row is keyed by.
        """
        meta, mutation = self._retained()
        authored = self._codec.authored_row(self._value) if mutation in UPDATE_MUTATIONS else None
        if authored is None:
            instruction = prepared_typed_write(
                meta, mutation, resolved.entity, self._codec.identity_row(self._value), bounds
            )
            originals: Mapping[str, object] = {}
        else:
            touched = frozenset(authored.originals)
            identity = {name: value for name, value in authored.row.items() if name not in touched}
            instruction = prepared_typed_write(
                meta, mutation, resolved.entity, authored.row, bounds
            )
            restored = prepared_typed_write(
                meta, mutation, resolved.entity, {**identity, **authored.originals}, bounds
            )
            originals = {name: restored.rows[0][name] for name in touched}
        return PreparedSourceWrite(
            instruction=instruction,
            object_key=(
                resolved.hint.object_key
                if resolved.hint is not None
                else written_object_key(resolved.entity, meta, instruction.rows[0])
            ),
            originals=originals,
        )

    def _retained(self) -> tuple[Metamodel, KeyedMutation]:
        # The ingress calls the three phases in order and nothing else calls any
        # of them, so what `resolve` filed is always here by `prepare`.
        assert self._meta is not None
        assert self._mutation is not None
        return self._meta, self._mutation


class TypedKeyedInsertSource:
    """The Typed Keyed Insert Source: what a fresh Entity instance answers the
    ingress's insert door.

    Narrower than its peer by exactly what an opening row has no answer for: no
    hint, no identity row named ahead of the instruction, and no originals. What
    it authors is the Create Payload — every member the instance actually SET —
    rather than a change set, because there is no prior state for a change to be
    against.
    """

    __slots__ = ("_codec", "_instance", "_meta", "_mutation")

    def __init__(self, instance: EntityBase, codec: EntityRowCodec) -> None:
        self._instance = instance
        self._codec = codec
        self._meta: Metamodel | None = None
        self._mutation: KeyedMutation | None = None

    def capture(self, mutation: KeyedMutation, /) -> None:
        return None

    def resolve(self, model: Metamodel, mutation: KeyedMutation, /) -> ResolvedKeyedInsert:
        self._meta = model
        self._mutation = mutation
        return ResolvedKeyedInsert(
            entity=metadata_of_instance(model, self._instance),
            pin=source_pin(self._instance),
            provenance=provenance_of(self._instance),
        )

    def prepare(
        self, resolved: ResolvedKeyedInsert, bounds: PreparedTemporalBounds, /
    ) -> PreparedKeyedWrite:
        assert self._meta is not None  # the ingress resolves before it prepares
        assert self._mutation is not None
        return prepared_typed_write(
            self._meta,
            self._mutation,
            resolved.entity,
            self._codec.full_row(self._instance),
            bounds,
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
        "_attempt",
        "_codec",
        "_conn",
        "_keyed",
        "_lifecycle",
        "_model",
        "_reads",
        "_uow",
    )

    def __init__(
        self,
        uow: UnitOfWork,
        conn: DbPort,
        selected: SelectedReadModel,
        codec: EntityRowCodec,
        attempt: TransactionAttemptActivity,
        lifecycle: InstalledLifecycle | None,
    ) -> None:
        self._uow = uow
        self._conn = conn
        # The write verbs' own metadata, which is the read selection's cataloged
        # half: a write names Entities and derives rows, so it needs the catalog
        # without the materialization capability beside it.
        self._model = selected.model
        self._codec = codec
        # The physical attempt every activity this transaction opens hangs
        # under: a read, the dependency batch that precedes it, and the
        # resolving read a materializing predicate write runs are all its
        # children, so the tree an observer sees is the call tree that made it.
        self._attempt = attempt
        # The opening handle's own installed lifecycle, which is what makes
        # "the originating Handle or Transaction" one refusal rather than two: a
        # verb called from inside that handle's provider, handler, or reporter is
        # refused here on exactly the state the handle refuses on
        # (`m-execution-lifecycle`).
        self._lifecycle = lifecycle
        # The one Read Scope this transaction's eager reads run through — its
        # own Typed verbs and the Wire view it answers alike (spec §5 "Private
        # read composition").
        self._reads = participating_read_scope(
            lifecycle=lifecycle, selected=selected, uow=uow, conn=conn, attempt=attempt
        )
        # The transaction state every keyed write of this transaction reads,
        # built once because all four facts are fixed for its life and handed to
        # each keyed verb by value. Its ledger of what THIS transaction buffered
        # an insert of is what a same-transaction insert leaves for a subsequent
        # keyed write to build on, so both read-your-own-writes exemptions — the
        # value-provenance refusal and the write-evidence resolution — read one
        # ledger, and so does the Wire ingress, whose inserts and updates pair
        # with the Typed ones.
        self._keyed = KeyedWriteContext(
            model=self._model,
            uow=uow,
            inserts=BufferedInserts(),
            lifecycle=lifecycle,
        )

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
        (:func:`validate_window`, `python.md` §5 "all validated at build").
        The window bounds come from THESE verb arguments, never from instance
        fields: an As-Of Axis endpoint is framework-owned and the temporal write
        path derives every interval bound itself (`python.md` §2), which is why
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
        keyed_write(
            self._keyed,
            TypedKeyedWriteSource(copy, self._codec),
            "update",
            valid_from=valid_from,
        )

    def delete(self, node_or_instance: EntityBase) -> None:
        """Buffer a keyed ``delete``, keyed off ``node_or_instance``'s primary
        key (a frozen ``Snapshot`` node, a fresh instance, or an edited copy —
        all carry valid primary-key values, spec §5). A source view pinned at a
        finite Transaction-Time instant is read-only and raises
        :class:`~parallax.snapshot.handle.TransactionTimePinReadOnlyError`
        before any buffering, exactly as every other keyed verb does.

        ``delete`` physically removes the row and carries no temporal meaning, so
        a target that milestones its rows refuses it at this call and names
        :meth:`terminate`, which closes the row's history instead (`python.md`
        §5 "Write verbs and temporal spellings")."""
        keyed_write(self._keyed, TypedKeyedWriteSource(node_or_instance, self._codec), "delete")

    # --- typed keyed temporal-window verbs (python.md §5). Every mutation   #
    # kind below is already a valid                                          #
    # ``KeyedMutation`` and already fully lowered (``bitemp_write`` /        #
    # ``txtime_write`` / ``planner``) — only the DEVELOPER-facing verb was    #
    # missing: a typed ``Transaction`` method that builds the SAME           #
    # instruction through the SAME ingress `insert`/`update`/`delete`        #
    # already enter, so a hand-written program and the engine's corpus       #
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
        (:func:`validate_window`, `python.md` §5 "all validated at build") —
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
        call, before any buffering (:func:`validate_window`, `python.md`
        §5)."""
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
        return self._reads.find(query)

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

        Its read half is this transaction's one Read Scope, retained rather than
        wrapped, so a Wire read enters at that scope's own verb and refuses
        re-entry at the same first line ``tx.find`` crosses. Its write half is a
        lane of its own, because a write settles against evidence a read never
        derives.
        """
        return WireTransactionView(
            self._reads,
            WireWriteLane(self._keyed, self._conn, self._attempt),
        )

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
        refuse_reentry(self._lifecycle)
        buffer_predicate(
            self._uow,
            self._model,
            self._conn,
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
        refuse_reentry(self._lifecycle)
        buffer_predicate(
            self._uow,
            self._model,
            self._conn,
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
        refuse_reentry(self._lifecycle)
        buffer_predicate(
            self._uow,
            self._model,
            self._conn,
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
        refuse_reentry(self._lifecycle)
        buffer_predicate(
            self._uow,
            self._model,
            self._conn,
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
        refuse_reentry(self._lifecycle)
        buffer_predicate(
            self._uow,
            self._model,
            self._conn,
            "terminateUntil",
            query,
            (),
            valid_from=valid_from,
            until=until,
            attempt=self._attempt,
        )

    def _buffer_prepared_predicate_write(self, instruction: PreparedPredicateWrite) -> None:
        refuse_reentry(self._lifecycle)
        buffer_predicate_instruction(
            self._uow,
            self._model,
            self._conn,
            instruction,
            self._attempt,
        )

    def _buffer_prepared_wire_keyed_write(
        self,
        instruction: PreparedKeyedWrite,
        observed: object,
        assigned_members: frozenset[str],
    ) -> None:
        buffer_prepared_keyed_write(
            WireWriteLane(self._keyed, self._conn, self._attempt),
            observed,
            instruction,
            assigned_members,
        )


def buffer_prepared_predicate_write(
    transaction: Transaction, instruction: PreparedPredicateWrite
) -> None:
    """Buffer an already-prepared predicate instruction on ``transaction``.

    The conformance translation owns a case-format carrier adapter before this
    seam. Production still owns dispatch, materialization, lifecycle, and the
    unit-of-work buffer; accepting only ``PreparedPredicateWrite`` prevents this
    execution bridge from becoming another instruction producer.
    """
    transaction._buffer_prepared_predicate_write(  # pyright: ignore[reportPrivateUsage]
        instruction
    )


def buffer_prepared_wire_keyed_write(
    transaction: Transaction,
    instruction: PreparedKeyedWrite,
    observed: object,
    assigned_members: frozenset[str],
) -> None:
    """Buffer an already-prepared keyed instruction against a Wire source."""
    transaction._buffer_prepared_wire_keyed_write(  # pyright: ignore[reportPrivateUsage]
        instruction,
        observed,
        assigned_members,
    )
