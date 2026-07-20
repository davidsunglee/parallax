"""``parallax.snapshot.handle._transaction`` — the developer transaction surface (spec §5).

:class:`Transaction` is what a ``db.transact`` closure receives: a facade over
the active unit of work and the transaction's own connection. It owns the
graduated D-16 keyed verbs (``insert`` / ``update`` / ``delete`` and the typed
temporal-window family), the participating :meth:`Transaction.find`, and the
neutral ``_buffer`` instruction seam every keyed verb shares.

The predicate-selected ``_where`` family is NOT owned here: those six methods —
the five public verbs plus the frozen ``_buffer_predicate_instruction`` seam the
conformance engine calls — are thin delegates that thread
``(uow, meta, conn, dialect)`` into
:mod:`parallax.snapshot.handle._predicate_writes`, which buffers through
``uow.buffer`` and never reaches back into this class.

Depends on :mod:`parallax.snapshot.handle._read` (the shared find executor plus
the pin / result-conversion helpers ``find`` needs),
:mod:`parallax.snapshot.handle._write_inputs` (verb-input validation, the
sparse-row build, and the observation machinery), and
:mod:`parallax.snapshot.handle._predicate_writes`. Demarcation — ``Database``,
``_Demarcation``, and ``TransactionOptionConflictError`` — lives in
:mod:`parallax.snapshot.handle._database`, which imports this module, never the
reverse.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from parallax.core import inheritance, opt_lock, read_lock
from parallax.core.db_port import DbPort
from parallax.core.descriptor import Entity, Metamodel
from parallax.core.dialect import Dialect
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import Statement as EntityStatement
from parallax.core.entity import full_row, primary_key_row
from parallax.core.entity.expressions import AttributeAssignment
from parallax.core.unit_work import (
    ObjectKey,
    PredicateWrite,
    UnitOfWork,
    instructions,
    validate_write,
)

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.snapshot.handle._predicate_writes import (
    buffer_predicate,
    buffer_predicate_instruction,
)
from parallax.snapshot.handle._read import (
    Snapshot,
    deep_fetch_statement_pin,
    find,
    find_history,
    is_milestone_set_op,
    snapshot_from_find_result,
    snapshot_from_history_result,
)
from parallax.snapshot.handle._write_inputs import (
    entity_record_of_instance,
    observation_key,
    prepare_sparse_row,
    record_observations,
    validate_business_from,
    validate_until,
)


class Transaction:
    """The developer transaction handed to a ``db.transact`` closure (spec §5).

    A facade over the active unit of work and the transaction's own connection.
    The graduated D-16 verbs take entity instances: :meth:`insert` a full
    instance (the Create Payload), :meth:`update` an edited copy (the sparse
    row: primary key + effective change set — an empty effective set is a
    no-op, zero round trips), :meth:`delete` a node or instance (keys off its
    primary key). :meth:`find` runs a participating read and returns
    ``Snapshot[T]`` (DQ6): force-flush + the transaction's own lock suffix,
    otherwise identical to :meth:`Database.find`. The predicate-selected
    ``_where`` verb family (COR-3 Phase 8 increment 5; `python.md` §5) —
    :meth:`update_where`, :meth:`delete_where`, :meth:`terminate_where`,
    :meth:`update_until_where`, :meth:`terminate_until_where` — mirrors the
    keyed surface over a bare predicate: readless for an unversioned,
    non-temporal target, materializing to per-row keyed writes otherwise
    (:mod:`parallax.snapshot.handle._predicate_writes`, ADR 0014, which those
    five verbs delegate to). A reference used after
    its owning scope ends raises
    :class:`~parallax.core.unit_work.EscapedTransactionError` (every verb
    delegates to the unit of work, which fences use-after-scope).
    """

    __slots__ = ("_conn", "_dialect", "_inserted_keys", "_meta", "_uow")

    def __init__(
        self,
        uow: UnitOfWork,
        conn: DbPort,
        meta: Metamodel,
        dialect: Dialect,
    ) -> None:
        self._uow = uow
        self._conn = conn
        self._meta = meta
        self._dialect = dialect
        # The object keys THIS transaction buffered an insert for — the
        # read-your-own-writes exemption from the §5 prior-observation license
        # (`_require_observed_milestone`): a same-transaction insert IS the
        # provenance a subsequent keyed temporal close builds on.
        self._inserted_keys: set[ObjectKey] = set()

    def insert(self, instance: EntityBase, *, business_from: dt.datetime | None = None) -> None:
        """Buffer a keyed ``insert`` of a full instance (the Create Payload,
        spec §5): every member the instance actually SET. Raises
        :class:`~parallax.core.entity.base.FrameworkOwnedAxisError` (D-31,
        COR-3 Phase 8 increment 7 completion round) when ``instance`` itself
        SET an axis-governed attribute (``in_z``/``out_z``, bitemporal
        ``from_z``/``thru_z``) — those columns are framework-stamped at flush
        (the Clock Strategy), never caller-authored (:func:`full_row`'s own
        construction-time rejection replaces the pre-D-31 silent discard).

        ``business_from`` is the PLAIN (unbounded) bitemporal insert's own
        business instant — the open rectangle's lower bound
        ``[business_from, infinity)`` (`m-bitemp-write` "insert /
        insertUntil — a single open rectangle, no close"); mirrors ``update``'s
        own bitemporal-only-required :func:`validate_business_from`: an
        audit-only or non-temporal target takes none (no business axis to
        bound)."""
        record, declaring, business_from_literal = self._prepare_keyed_write(
            instance, "insert", business_from
        )
        self._buffer("insert", record.name, full_row(instance), business_from=business_from_literal)
        self._inserted_keys.add(observation_key(record, declaring, instance))

    def insert_until(
        self, instance: EntityBase, *, business_from: dt.datetime, until: dt.datetime
    ) -> None:
        """Buffer a keyed, business-window-BOUNDED ``insertUntil`` (D-31, COR-3
        Phase 8 increment 7 completion round; ``m-bitemp-write-003`` — the
        *Until trio's third member): open a single bitemporal rectangle
        bounded to ``[business_from, until)`` at the fresh processing
        milestone, with no prior row to close — the bitemporal analogue of an
        audit-only ``insert``, business-bounded — bitemporal-only (mirrors
        ``update_until``'s own required, non-optional ``business_from`` /
        ``until``). A window that does not satisfy ``business_from < until``
        (equal or reversed bounds) raises at THIS call, before any buffering
        (:func:`validate_until`, `python.md` §5 "all validated at build").
        Raises :class:`~parallax.core.entity.base.FrameworkOwnedAxisError`
        when ``instance`` itself SET an axis-governed attribute — the window
        bounds come from THESE verb arguments, never from instance fields
        (the Reladomo verb-argument precedent, decision 2)."""
        record, declaring, business_from_literal = self._prepare_keyed_write(
            instance, "insertUntil", business_from
        )
        until_literal = validate_until(declaring, "insertUntil", business_from, until)
        self._buffer(
            "insertUntil",
            record.name,
            full_row(instance),
            business_from=business_from_literal,
            business_to=until_literal,
        )
        self._inserted_keys.add(observation_key(record, declaring, instance))

    def update(self, copy: EntityBase, *, business_from: dt.datetime | None = None) -> None:
        """Buffer a sparse keyed ``update``: primary key + the effective change
        set of an edited copy (touched fields whose current value differs from
        the recorded original, spec §3/§5). An EMPTY effective change set
        issues no DML at all (zero round trips, the net-zero-chain no-op rule
        — the no-op-first ordering `m-opt-lock` fixes: dropped before any
        observation or locking concern). Raises
        :class:`~parallax.core.entity.ProvenanceError` for a provenance-less
        instance (never produced via ``model_copy``). The version column, if
        any, is never authored here — it is framework-owned end to end
        (`m-opt-lock`; ADR 0013): the write seam derives its advance from this
        unit of work's own recorded observation at lowering
        (`parallax.snapshot.handle.lower_write`), never from the edited copy.

        ``business_from`` is the PLAIN (unbounded) bitemporal correction's own
        business instant (`m-bitemp-write-006` "plain-update-split" —
        inactivates the original on the processing axis, then chains head
        (the old value) + a new tail (the new value) running to infinity, the
        two-way degenerate of ``update_until``'s three-way rectangle split).
        Mirrors ``update_where``'s own bitemporal-only-required
        :func:`validate_business_from`: an audit-only or non-temporal target
        takes none (no business axis to bound)."""
        record, declaring, business_from_literal = self._prepare_keyed_write(
            copy, "update", business_from
        )
        row = prepare_sparse_row(copy)
        if row is None:
            return
        self._require_observed_milestone(record, declaring, copy)
        self._buffer("update", record.name, row, business_from=business_from_literal)

    def delete(self, node_or_instance: EntityBase) -> None:
        """Buffer a keyed ``delete``, keyed off ``node_or_instance``'s primary
        key (a frozen ``Snapshot`` node, a fresh instance, or an edited copy —
        all carry valid primary-key values, spec §5)."""
        record = entity_record_of_instance(node_or_instance)
        self._buffer("delete", record.name, primary_key_row(node_or_instance))

    # --- typed keyed temporal-window verbs (python.md §5; COR-3 Phase 8      #
    # increment 7; ``insertUntil`` landed by the increment 7 completion      #
    # round, D-31). Every mutation kind below is already a valid             #
    # ``KeyedMutation`` and already fully lowered (``bitemp_write`` /        #
    # ``audit_write`` / ``planner``) — only the DEVELOPER-facing verb was    #
    # missing: a typed ``Transaction`` method that builds the SAME           #
    # instruction through the SAME `_buffer` seam `insert`/`update`/`delete` #
    # already share, so a hand-written program and the engine's corpus      #
    # replay can never diverge in behavior.                                 #
    def terminate(
        self, node_or_instance: EntityBase, *, business_from: dt.datetime | None = None
    ) -> None:
        """Buffer a keyed ``terminate``: close ``node_or_instance``'s current
        milestone (the temporal delete-equivalent, `python.md` §5) — keyed off
        its primary key alone, no chained row (close-only, `m-audit-write` /
        `m-bitemp-write`). Audit-only takes no ``business_from`` (no business
        axis to bound); bitemporal REQUIRES it (the mutation's own business
        instant, mirrors ``terminate_where``'s own
        :func:`validate_business_from`)."""
        record, declaring, business_from_literal = self._prepare_keyed_write(
            node_or_instance, "terminate", business_from
        )
        self._require_observed_milestone(record, declaring, node_or_instance)
        self._buffer(
            "terminate",
            record.name,
            primary_key_row(node_or_instance),
            business_from=business_from_literal,
        )

    def update_until(
        self, copy: EntityBase, *, business_from: dt.datetime, until: dt.datetime
    ) -> None:
        """Buffer a sparse keyed, business-window-BOUNDED ``updateUntil``:
        primary key + the effective change set of an edited copy (mirrors
        keyed ``update``), bounded to ``[business_from, until)``
        (`m-bitemp-write` "The rectangle split") — bitemporal-only (mirrors
        ``update_until_where``'s own required, non-optional ``business_from``
        / ``until``). A window that does not satisfy ``business_from < until``
        (equal or reversed bounds) raises at THIS call, before any buffering
        (:func:`validate_until`, `python.md` §5 "all validated at build") —
        checked BEFORE the empty-effective-change-set no-op return below (R2,
        COR-3 Phase 7 increment 7 round-2: window validation runs first for
        every window verb, never after; equal bounds reject even when the
        edited copy's own Change Record nets to zero). An EMPTY effective
        change set (once the window is confirmed valid) issues no DML at all,
        exactly like keyed ``update``."""
        record, declaring, business_from_literal = self._prepare_keyed_write(
            copy, "updateUntil", business_from
        )
        until_literal = validate_until(declaring, "updateUntil", business_from, until)
        row = prepare_sparse_row(copy)
        if row is None:
            return
        self._require_observed_milestone(record, declaring, copy)
        self._buffer(
            "updateUntil",
            record.name,
            row,
            business_from=business_from_literal,
            business_to=until_literal,
        )

    def terminate_until(
        self, node_or_instance: EntityBase, *, business_from: dt.datetime, until: dt.datetime
    ) -> None:
        """Buffer a keyed, business-window-BOUNDED ``terminateUntil``: close a
        single business window ``[business_from, until)`` on
        ``node_or_instance``'s current milestone, keyed off its primary key
        alone (`m-bitemp-write`) — bitemporal-only (mirrors
        ``terminate_until_where``). A window that does not satisfy
        ``business_from < until`` (equal or reversed bounds) raises at THIS
        call, before any buffering (:func:`validate_until`, `python.md`
        §5)."""
        record, declaring, business_from_literal = self._prepare_keyed_write(
            node_or_instance, "terminateUntil", business_from
        )
        until_literal = validate_until(declaring, "terminateUntil", business_from, until)
        self._require_observed_milestone(record, declaring, node_or_instance)
        self._buffer(
            "terminateUntil",
            record.name,
            primary_key_row(node_or_instance),
            business_from=business_from_literal,
            business_to=until_literal,
        )

    def _prepare_keyed_write(
        self, node_or_instance: EntityBase, mutation: str, business_from: dt.datetime | None
    ) -> tuple[Entity, Entity, str | None]:
        """The keyed-verb prep every verb above (``delete`` excepted — it takes
        no business-window bound) opens with (N2, COR-3 Phase 8 increment 7
        remediation; ``insert``/``insert_until`` joined at D-31, increment 7
        completion round): resolve the written
        instance's own :class:`~parallax.core.descriptor.Entity` record and
        its family's DECLARING entity
        (:func:`~parallax.core.inheritance.declaring_entity` — the entity
        that actually carries the temporal/versioned shape), then validate +
        render ``business_from`` against that declaring entity's own
        temporality (:func:`validate_business_from`, spec §5). Returns the
        record (``_buffer``'s own entity-name argument), the declaring entity
        (a ``*Until`` verb's own :func:`validate_until` needs it too, for
        its error message), and the rendered instant literal (``None`` for a
        non-temporal/audit-only target)."""
        record = entity_record_of_instance(node_or_instance)
        declaring = inheritance.declaring_entity(self._meta, record)
        business_from_literal = validate_business_from(declaring, mutation, business_from)
        return record, declaring, business_from_literal

    def _require_observed_milestone(
        self, record: Entity, declaring: Entity, instance: EntityBase
    ) -> None:
        """The `python.md` §5 prior-observation license for a keyed TEMPORAL
        update/terminate (:func:`opt_lock.require_observed_milestone` — the
        temporal sibling of the versioned ``require_observed`` seam in
        ``_lower_update``): the close must target a milestone THIS unit of
        work observed via a transaction-scoped find. Enforced HERE at the
        developer verb, never in ``_lower_temporal_write`` — the shared
        lowering also serves the neutral engine lane, whose case documents
        author their observation control keys (or legitimately none) and are
        graded against their own goldens. An object this SAME transaction
        buffered an insert for is exempt (read-your-own-writes: the buffered
        insert IS the provenance; the planner coalesces or orders the pair,
        `m-unit-work`). Callers invoke this AFTER a sparse update's
        empty-change-set no-op return (the no-op-first ordering `m-opt-lock`
        fixes: a no-op is dropped before any observation concern) and AFTER
        window validation (R2: the window rejects first)."""
        if not declaring.is_temporal:
            return
        key = observation_key(record, declaring, instance)
        if key in self._inserted_keys:
            return
        opt_lock.require_observed_milestone(record.name, self._uow.observation_for(key))

    def find(self, statement: EntityStatement) -> Snapshot[Any]:
        """Run a participating read for ``statement`` and return ``Snapshot[T]``
        (DQ6): force-flushes pending writes first (read-your-own-writes), and
        the transaction's participation mode renders the read-lock suffix
        (``locking`` takes the dialect's shared row lock; ``optimistic`` takes
        none). Otherwise identical to :meth:`Database.find` — the SAME shared
        find executor, the SAME frozen-node wrapping. Returns ``Snapshot[Any]``:
        the concrete root type is resolved only at runtime (from the
        statement's own target), so callers annotate their own binding
        (``snapshot: Snapshot[Order] = tx.find(...)``) for static typing.

        Every materialized node of a VERSIONED entity — root and included
        (deep-fetch) alike — records its observed version on this unit of work
        (`m-opt-lock`; ADR 0013), in EITHER concurrency mode: a later keyed
        update/delete of that SAME object derives its version advance (and,
        under optimistic concurrency, its gate) from THIS observation, never
        from an implicit resolving read at write time. Every materialized node
        of a TEMPORAL entity likewise records its observed processing-from
        (`in_z`) plus PIN PROVENANCE (`Observation.latest_pinned`, derived from
        this statement's own processing-axis pin below): a later temporal
        write's close/chain, or a locking-mode write's historical-observation
        license (`~parallax.core.opt_lock.check_locking_license`), derives from
        THIS observation, never a shadow lookup or an implicit resolving read
        (a MILESTONE-SET read — `.history()` / `.as_of_range()` — records
        nothing here; its own dispatch branch returns before this point).
        """
        target = statement.target
        op = statement.operation()
        entity = inheritance.declaring_entity(self._meta, self._meta.entity(target))
        pin = deep_fetch_statement_pin(op, entity)
        lock = read_lock.mode_for(self._uow.settings.concurrency)
        if is_milestone_set_op(op):
            history_result = self._uow.read(
                lambda: find_history(op, self._meta, self._dialect, target, self._conn)
            )
            return snapshot_from_history_result(history_result, target, self._meta)
        find_result = self._uow.read(
            lambda: find(op, self._meta, self._dialect, target, self._conn, lock=lock)
        )
        record_observations(self._uow, self._meta, find_result, pin)
        return snapshot_from_find_result(find_result, target, self._meta, pin)

    def _buffer(
        self,
        mutation: str,
        entity: str,
        row: Mapping[str, object],
        *,
        business_from: str | None = None,
        business_to: str | None = None,
    ) -> None:
        # The document route buys the IR's structural validation (no `at` alias,
        # no observation keys) first (`deserialize`), then the model-aware
        # `validate_write` (the SAME validator the conformance engine's
        # rejected lane calls, COR-3 Phase 8 increment 2 — one validator, two
        # callers): its inheritance payload-shape checks
        # (`subtype-write-metadata-field` / `-sibling-attribute` /
        # `-set-based-unsupported`, m-inheritance) classify a framework-owned
        # metadata key or a cross-branch field MORE SPECIFICALLY than the
        # generic member-name-honesty gate below ever could, so it runs
        # first — member-name honesty (`validate_instruction`) still catches
        # any OTHERWISE-unknown member a validate_write pass left unexamined
        # (it walks only DECLARED members, never flags a stray key itself).
        #
        # `business_from` / `business_to` extend this neutral seam for a TEMPORAL
        # keyed write (COR-3 Phase 8 increment 4): a non-temporal or audit-only
        # target's caller never passes them (every pre-increment-7 call site is
        # unaffected). The typed temporal developer verbs (COR-3 Phase 8
        # increment 7 — ``update``'s own optional bitemporal ``business_from``,
        # ``terminate``, ``update_until``, ``terminate_until``; ``insert``'s own
        # optional bitemporal ``business_from`` and ``insert_until`` joined at
        # D-31, increment 7 completion round) and the conformance engine's own
        # temporal write translation both pass them the SAME way (`m-audit-write`
        # / `m-bitemp-write` — the axis-explicit `businessFrom` / `businessTo`
        # instruction fields, never smuggled onto `row`, ADR 0010/0013).
        doc: dict[str, object] = {"mutation": mutation, "entity": entity, "rows": [dict(row)]}
        if business_from is not None:
            doc["businessFrom"] = business_from
        if business_to is not None:
            doc["businessTo"] = business_to
        instruction = instructions.deserialize(doc)
        validate_write(self._meta.entity(entity), row, self._meta, mutation=mutation)
        instructions.validate_instruction(instruction, self._meta)
        self._uow.buffer(instruction)

    # --- set-based write verbs (python.md §5; COR-3 Phase 8 increment 5) -- #
    def update_where(
        self,
        statement: EntityStatement,
        *assignments: AttributeAssignment,
        business_from: dt.datetime | None = None,
    ) -> None:
        """A predicate-selected ``update`` (`python.md` §5): ``statement`` MUST
        be a bare statement (nothing but a predicate); ``assignments`` are
        ``Attr.set(value)`` calls, non-empty, no duplicate field. Readless
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
            statement,
            assignments,
            business_from=business_from,
        )

    def delete_where(self, statement: EntityStatement) -> None:
        """A predicate-selected ``delete`` over a NON-temporal target
        (`python.md` §5): readless for an unversioned target; a versioned one
        MATERIALIZES to one gated per-row delete per resolved row (no
        no-op elimination — a delete changes a row's existence, never a value,
        `m-opt-lock`)."""
        buffer_predicate(
            self._uow,
            self._meta,
            self._conn,
            self._dialect,
            "delete",
            statement,
            (),
            business_from=None,
        )

    def terminate_where(
        self, statement: EntityStatement, *, business_from: dt.datetime | None = None
    ) -> None:
        """A predicate-selected ``terminate`` over a TEMPORAL target
        (`python.md` §5): audit-only takes no ``business_from`` (no business
        axis to bound); bitemporal REQUIRES it (the plain terminate's own
        business instant ``B``). Always materializes — a temporal predicate
        write has no readless template."""
        buffer_predicate(
            self._uow,
            self._meta,
            self._conn,
            self._dialect,
            "terminate",
            statement,
            (),
            business_from=business_from,
        )

    def update_until_where(
        self,
        statement: EntityStatement,
        *assignments: AttributeAssignment,
        business_from: dt.datetime,
        until: dt.datetime,
    ) -> None:
        """A predicate-selected, business-window-BOUNDED ``updateUntil`` over a
        bitemporal target (`python.md` §5; `m-bitemp-write` "The rectangle
        split"): always materializes to a close plus head/middle/tail."""
        buffer_predicate(
            self._uow,
            self._meta,
            self._conn,
            self._dialect,
            "updateUntil",
            statement,
            assignments,
            business_from=business_from,
            until=until,
        )

    def terminate_until_where(
        self, statement: EntityStatement, *, business_from: dt.datetime, until: dt.datetime
    ) -> None:
        """A predicate-selected, business-window-BOUNDED ``terminateUntil`` over
        a bitemporal target (`python.md` §5): always materializes to a close
        plus head/tail (no middle — the window becomes a hole in business
        time)."""
        buffer_predicate(
            self._uow,
            self._meta,
            self._conn,
            self._dialect,
            "terminateUntil",
            statement,
            (),
            business_from=business_from,
            until=until,
        )

    def _buffer_predicate_instruction(self, instruction: PredicateWrite) -> None:
        """Buffer an ALREADY-BUILT, already-validated predicate write
        (:func:`~parallax.snapshot.handle._predicate_writes.buffer_predicate_instruction`).

        This method is a FROZEN external seam, not an ordinary private helper:
        the conformance engine's predicate-write translation calls it directly
        (`parallax.conformance.engine`), so its name and signature are fixed and
        it keeps its leading underscore despite crossing a module boundary
        (COR-3 Phase 8 increment 5; `m-case-format` "predicate-shaped case
        entries deserialize to PredicateWrite through the existing serde and
        buffer through Transaction's own seam"). The typed ``_where`` verbs
        above and the engine converge on the SAME free function below, so the
        two callers can never diverge in behavior.
        """
        buffer_predicate_instruction(self._uow, self._meta, self._conn, self._dialect, instruction)
