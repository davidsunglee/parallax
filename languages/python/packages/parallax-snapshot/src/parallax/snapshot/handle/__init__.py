"""``parallax.snapshot.handle`` — the composition surface (connect / transact / lowering).

This is the layer that legally sees **both** the neutral write-instruction IR /
flush planner (``m-unit-work``) **and** SQL generation (``m-sql`` / ``m-dialect``):
the module DAG forbids ``m-unit-work`` from importing ``m-sql`` (why the planner
emits a neutral :class:`~parallax.core.unit_work.FlushPlan`) and forbids ``m-sql``
from importing ``m-unit-work``, so the write-DML → SQL lowering — the deliberate
``m-sql`` edge M3 deferred — is composed **here**. :func:`lower_write` is the single
lowering function; both the developer transaction path (the injected
``FlushExecutor``) and the conformance engine reuse it (the conformance family is
the import-side DAG exemption), so there is exactly one write-lowering seam.

M4 lowered the non-temporal keyed write forms; COR-3 Phase 8 increment 3 added the
``m-opt-lock`` version gate/advance and inheritance-family DML; increment 4 adds the
**temporal** milestone forms — audit-only close-and-chain and full-bitemporal
rectangle splits (``insert`` / ``update`` / ``terminate`` and the bounded ``*Until``
trio), composing `parallax.core.audit_write` / `.bitemp_write`'s neutral milestone
planning with the ``m-opt-lock`` gate policy this seam already owns. Predicate-
selected (set-based) writes and multi-row batch collapse still land with a later
write increment; reaching one raises a loud :class:`WriteLoweringError` naming the
deferral, never a wrong emission — mirroring the read compiler's forward-error
posture.

The **developer transaction surface** (spec §5) also composes here:
:meth:`Database.connect` wires a concrete ``m-db-port`` adapter to a metamodel,
and :meth:`Database.transact` is the callback demarcation — sentinel-backed
options, join with the option-conflict check, the ``m-auto-retry`` bounded retry
loop, and the injected flush executor that lowers each planned write and runs it
on the transaction's own connection. Per ledger D-16 (COR-3 Phase 7 increment
6a, full graduation) the :class:`Transaction` verbs take entity instances:
``insert(instance)`` (the Create Payload), ``update(edited_copy)`` (the sparse
row: primary key + effective change set), ``delete(node_or_instance)`` (keys
off it); :meth:`Database.find` / :meth:`Transaction.find` both wrap the SAME
production find executor below in ``Snapshot[T]`` (DQ6).

:meth:`Transaction.find` participates in the transaction (force-flush +
read-your-own-writes, the transaction's own lock suffix) by running the shared
:func:`find` / :func:`find_history` executor through
:meth:`~parallax.core.unit_work.UnitOfWork.read` — root canonicalization
(``m-temporal-read`` + ``m-navigate``) happens inside the shared executor via
``parallax.core.deep_fetch.plan``, never re-derived here.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from parallax.core import (
    batch_write,
    deep_fetch,
    inheritance,
    op_algebra,
    opt_lock,
    read_lock,
)
from parallax.core.auto_retry import run_with_retry
from parallax.core.db_port import DbPort, Row
from parallax.core.descriptor import Attribute, Entity, Metamodel
from parallax.core.dialect import POSTGRES, Dialect, LockMode
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import Statement as EntityStatement
from parallax.core.entity import full_row, primary_key_row
from parallax.core.entity.expressions import AttributeAssignment
from parallax.core.sql_gen import Statement, compile_read
from parallax.core.unit_work import (
    AtomicUnit,
    Clock,
    Concurrency,
    FlushExecutor,
    FlushPlan,
    KeyedWrite,
    ObjectKey,
    Observation,
    PlannedWrite,
    PredicateWrite,
    RollbackOnlyError,
    SystemClock,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    active_unit_of_work,
    instructions,
    object_key,
    run_unit_of_work,
    validate_write,
)

# The private implementation modules. Some of what follows is a public name this
# package re-exports through `__all__` (every `_write_types` / `_write_lowering`
# name, ten of the `_read` ones); the rest is an implementation seam the code still
# living here shares with them — the family-descriptor lookups, and the pin /
# result-conversion helpers `Transaction.find` shares with the read executor. None of
# those carry a leading underscore, precisely because they cross a module boundary:
# privacy is carried by the private MODULE names and by `__all__`, not by per-name
# underscores, which under pyright strict would make every intra-package import a
# reportPrivateUsage error.
from parallax.snapshot.handle._family import assignment_member, members, version_attribute
from parallax.snapshot.handle._read import (
    ExecutedStatement,
    Execution,
    FindResult,
    HistoryFindResult,
    MilestoneGraph,
    NoResultFound,
    Snapshot,
    TooManyResultsFound,
    deep_fetch_statement_pin,
    find,
    find_history,
    is_milestone_set_op,
    snapshot_from_find_result,
    snapshot_from_history_result,
)
from parallax.snapshot.handle._write_inputs import (
    entity_record_of_instance,
    materialize_row,
    observation_key,
    prepare_sparse_row,
    record_observations,
    validate_business_from,
    validate_until,
)
from parallax.snapshot.handle._write_lowering import lower_temporal_close, lower_write
from parallax.snapshot.handle._write_types import LoweredStatement, WriteLoweringError

__all__ = [
    "Database",
    "ExecutedStatement",
    "Execution",
    "FindResult",
    "HistoryFindResult",
    "LoweredStatement",
    "MilestoneGraph",
    "NoResultFound",
    "Snapshot",
    "TooManyResultsFound",
    "Transaction",
    "TransactionOptionConflictError",
    "WriteLoweringError",
    "connect",
    "find",
    "find_history",
    "lower_temporal_close",
    "lower_write",
]


# --------------------------------------------------------------------------- #
# The developer transaction surface (spec §5) — connect / transact.           #
# --------------------------------------------------------------------------- #


class TransactionOptionConflictError(ValueError):
    """A joining ``db.transact`` call tried to re-negotiate the boundary.

    A joining call may not change the active transaction's settings: an explicit
    (non-``None``) option whose value conflicts with the outermost boundary's
    resolved setting raises; an explicit equal value and an omitted option are
    accepted (spec §5).
    """


@dataclass(frozen=True, slots=True)
class _ResolvedOptions:
    """The outermost boundary's resolved ``db.transact`` options.

    ``concurrency`` also lives on the core :class:`TransactionSettings`;
    ``retries`` and ``retry_optimistic_conflicts`` are demarcation-level only
    (the core unit of work never sees them). ``retry_optimistic_conflicts``
    is stored for the join/conflict contract AND gates
    :func:`_optimistic_conflict_retriable` — the opt-in-only classification
    branch :meth:`Database.transact` injects into
    :func:`~parallax.core.auto_retry.run_with_retry` (COR-3 Phase 8
    increment 6; `m-opt-lock` "Retry contract").
    """

    retries: int
    concurrency: Concurrency
    retry_optimistic_conflicts: bool


@dataclass(frozen=True, slots=True)
class _Demarcation:
    """What the outermost boundary publishes on the unit of work's ``companion``.

    A joining ``db.transact`` call needs the same :class:`Transaction` to hand
    its closure and the boundary's resolved options for the conflict check;
    both ride core's single per-thread active binding, so their visibility ends
    exactly when it does (no handle-owned thread-local, nothing to clean up).
    """

    tx: Transaction
    options: _ResolvedOptions


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
    (:meth:`_materialize_predicate_write`, ADR 0014). A reference used after
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
        :meth:`_buffer_predicate`, the neutral seam this and every other
        ``_where`` verb share."""
        self._buffer_predicate("update", statement, assignments, business_from=business_from)

    def delete_where(self, statement: EntityStatement) -> None:
        """A predicate-selected ``delete`` over a NON-temporal target
        (`python.md` §5): readless for an unversioned target; a versioned one
        MATERIALIZES to one gated per-row delete per resolved row (no
        no-op elimination — a delete changes a row's existence, never a value,
        `m-opt-lock`)."""
        self._buffer_predicate("delete", statement, (), business_from=None)

    def terminate_where(
        self, statement: EntityStatement, *, business_from: dt.datetime | None = None
    ) -> None:
        """A predicate-selected ``terminate`` over a TEMPORAL target
        (`python.md` §5): audit-only takes no ``business_from`` (no business
        axis to bound); bitemporal REQUIRES it (the plain terminate's own
        business instant ``B``). Always materializes — a temporal predicate
        write has no readless template."""
        self._buffer_predicate("terminate", statement, (), business_from=business_from)

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
        self._buffer_predicate(
            "updateUntil", statement, assignments, business_from=business_from, until=until
        )

    def terminate_until_where(
        self, statement: EntityStatement, *, business_from: dt.datetime, until: dt.datetime
    ) -> None:
        """A predicate-selected, business-window-BOUNDED ``terminateUntil`` over
        a bitemporal target (`python.md` §5): always materializes to a close
        plus head/tail (no middle — the window becomes a hole in business
        time)."""
        self._buffer_predicate(
            "terminateUntil", statement, (), business_from=business_from, until=until
        )

    def _buffer_predicate(
        self,
        mutation: str,
        statement: EntityStatement,
        assignments: Sequence[AttributeAssignment],
        *,
        business_from: dt.datetime | None,
        until: dt.datetime | None = None,
    ) -> None:
        """The neutral seam every ``_where`` verb shares — the SAME seam the
        conformance engine's predicate-write translation drives (COR-3 Phase 8
        increment 5), so the developer-facing verbs and the corpus-driven
        engine path can never diverge in behavior.

        1. **Bare-statement guard** (`python.md` §5 "A statement becomes a
           write target only as a bare statement") — one carrying nothing but
           a predicate; every other clause is rejected (`EntityStatement.
           is_bare`, subsuming ``.distinct()``).
        2. **Inheritance rejection** (`m-inheritance` "Per-object writes are
           keyed; set-based inheritance writes are out of scope") — BEFORE any
           SQL, the SAME ``subtype-write-set-based-unsupported`` classification
           a keyless keyed write raises.
        3. **Business-bound validation** — a bitemporal target REQUIRES
           ``business_from`` (its own business instant); an audit-only or
           non-temporal target takes none (no business axis to bound); the
           ``*Until`` forms additionally require ``until``, with
           ``business_from < until`` — an equal or reversed window rejects
           HERE, at build, before any buffering (:func:`validate_until`, S4
           COR-3 Phase 8 increment 7 remediation).
        4. **Build + validate the canonical instruction** (the SAME
           deserialize/`validate_instruction` round trip a keyed write buys in
           :meth:`_buffer` — non-empty/no-duplicate assignments are the schema's
           own check).
        5. **Dispatch**: an unversioned, non-temporal target buffers READLESS
           (one statement, `m-batch-write`); a versioned or temporal one
           MATERIALIZES (:meth:`_materialize_predicate_write`, ADR 0014).
        """
        if not statement.is_bare():
            raise ValueError(
                f"{statement.target}: a set-based write target must be a bare statement "
                "(nothing but a predicate) — order_by / limit / distinct / as_of / history / "
                "as_of_range / narrow / include are all rejected on a write target (python.md §5)"
            )
        entity = self._meta.entity(statement.target)
        inheritance.reject_predicate_write(entity)
        declaring = inheritance.declaring_entity(self._meta, entity)
        business_from_literal = validate_business_from(declaring, mutation, business_from)
        until_literal: str | None = None
        if until is not None:
            assert business_from is not None  # `*_until_where` verbs require both together
            until_literal = validate_until(declaring, mutation, business_from, until)

        doc: dict[str, object] = {
            "mutation": mutation,
            "target": {
                "entity": statement.target,
                "predicate": op_algebra.serialize(statement.predicate),
            },
        }
        if assignments:
            doc["assignments"] = [{"attr": str(a.attr), "value": a.value} for a in assignments]
        if business_from_literal is not None:
            doc["businessFrom"] = business_from_literal
        if until_literal is not None:
            doc["businessTo"] = until_literal
        instruction = instructions.deserialize(doc)
        assert isinstance(
            instruction, PredicateWrite
        )  # this seam always builds the predicate shape
        instructions.validate_instruction(instruction, self._meta)
        self._buffer_predicate_instruction(instruction)

    def _buffer_predicate_instruction(self, instruction: PredicateWrite) -> None:
        """The neutral seam UNDERLYING every ``_where`` verb and the
        conformance engine's own predicate-write translation (COR-3 Phase 8
        increment 5; `m-case-format` "predicate-shaped case entries deserialize
        to PredicateWrite through the existing serde and buffer through
        Transaction's own seam"): given an ALREADY-BUILT, already-validated
        :class:`~parallax.core.unit_work.PredicateWrite` instruction, reject an
        inheritance-family target (`m-inheritance`), then dispatch READLESS
        (`m-batch-write`) or MATERIALIZE (`m-opt-lock`, ADR 0014). The typed
        ``_where`` verbs (:meth:`_buffer_predicate`) build ``instruction`` from
        a bare :class:`~parallax.core.entity.Statement` plus typed
        ``Attr.set(...)`` assignments first; the engine builds it directly
        from the case's own canonical write-instruction document — both
        converge HERE, so the two callers can never diverge in behavior.
        """
        entity = self._meta.entity(instruction.target.entity)
        inheritance.reject_predicate_write(entity)
        declaring = inheritance.declaring_entity(self._meta, entity)
        version_attr = version_attribute(declaring)
        if not declaring.is_temporal and version_attr is None:
            # Readless (`m-batch-write.md` "Predicate-selected readless forms"):
            # one statement, no materialization, no equality-elimination pass.
            self._uow.buffer(instruction)
            return
        self._materialize_predicate_write(instruction, entity, declaring, version_attr)

    def _materialize_predicate_write(
        self,
        instruction: PredicateWrite,
        entity: Entity,
        declaring: Entity,
        version_attr: Attribute | None,
    ) -> None:
        """Materialize a predicate write on a VERSIONED or TEMPORAL target
        (`m-opt-lock` "Predicate-selected writes materialize when observations
        are needed"; ADR 0014): resolve the predicate through a MINIMAL
        row-form read on THIS transaction's own connection (never instance-form
        — the resolve constructs no object, `m-value-object-047`), record each
        matched row's observation through ``uow.observe`` (the SAME
        transaction-scoped seam a real :meth:`find` uses — never an engine-side
        map), then buffer one keyed per-row write per row the verb WRITES (the
        per-row no-op elimination below) as an ORDERED ATOMIC PLANNED UNIT
        (`m-unit-work`, :class:`AtomicUnit`) at the call position. Zero
        resolved rows -> zero keyed writes, success (no unit buffered at all).
        The lock suffix on the resolve derives from the transaction's own
        concurrency mode (``locking`` ⇒ the shared read lock, ``optimistic`` ⇒
        none) — the SAME rule a real ``Transaction.find`` applies.

        A TEMPORAL target's raw predicate carries no as-of wrapper (a bare
        statement forbids ``.as_of()``/``.history()``, python.md §5) — exactly
        like an ordinary find's omitted axis, it must still default every
        declared axis to its CURRENT milestone (`m-temporal-read` "default-
        latest"), so the resolve routes through the SAME
        :func:`~parallax.core.deep_fetch.plan` root-canonicalization every
        other read uses (:func:`find`, above) rather than compiling the raw
        predicate directly — otherwise a temporal target's resolve would match
        every historical milestone too, not just the open one(s).
        """
        lock: LockMode | None = read_lock.mode_for(self._uow.settings.concurrency)
        plan_ = deep_fetch.plan(instruction.target.entity, instruction.target.predicate, self._meta)
        assignments = {
            assignment_member(assignment.attr): assignment.value
            for assignment in instruction.assignments
        }
        # Need-sensitive projection (`m-case-format.md:727`): the resolving
        # read projects the resolved row's own value-object document(s) for
        # TWO independent needs, on EVERY target class — never gated on
        # temporality alone (confirmation-pass residual A, completing P2).
        #
        # CHAIN need: the verb's OWN milestone plan writes a CHAINED row
        # from the resolved one. A BITEMPORAL target's rectangle split
        # (`bitemp_write.plan`) chains on EVERY close-bearing mutation —
        # update, updateUntil, terminate, AND terminateUntil alike, since
        # head (and tail, for the `*Until` forms) always carry the OLD
        # payload forward, not just an assignment-bearing one
        # (`m-bitemp-write` "head/tail old values come from the observed
        # prior rectangle"). An AUDIT-ONLY target's plan (`audit_write.
        # plan`) chains ONLY an ASSIGNMENT-BEARING `update`
        # (`materialize_row`'s own `assignment_bearing` set) — its
        # `terminate` is close-only, no chained row, so it stays
        # document-free (`m-value-object-047`'s own row-form-omits-slot-4
        # witness stays byte-identical); audit-only never reaches the
        # `*Until` forms (bitemporal-only, `validate_business_from`). The
        # chain need projects EVERY declared document, never just the
        # assigned ones — a chained row must carry forward whichever
        # documents the assignments do NOT themselves reassign. Either way,
        # an AUDIT-ONLY target's own `full_row` merge (`materialize_row`)
        # reads this read's row directly, while a BITEMPORAL target's split
        # reads it indirectly, through `_temporal_observation`'s payload,
        # which keeps a value-object document whenever THIS read actually
        # projected it (`m-value-object` "the document rides every
        # chained/split row whole").
        #
        # COMPARISON need: an assignment-bearing verb's per-row no-op
        # elimination (below, `materialize_row` -> `_apply_assignments`)
        # compares each assigned member's new value against the resolved
        # row's own — a value-object member's comparison can only ever see
        # the STORED document when this read actually projected its column
        # (`m-opt-lock.md:92-95` "when all assignments already equal that
        # row's values, it issues no DML, advances no version"). A TEMPORAL
        # target's chain need above already projects every document
        # whenever it is assignment-bearing, so this need is a strict no-op
        # there; a VERSIONED NON-TEMPORAL target never chains (no milestone
        # to carry a payload across — `m-opt-lock`/`m-descriptor`: versioned
        # and temporal are mutually exclusive), so it reaches this need
        # ALONE. Minimal-read discipline (`m-sql`) then projects the
        # ASSIGNED value-object document(s) only — never every declared
        # one, matching an ordinary read's own need-driven projection.
        assignment_bearing = instruction.mutation in ("update", "updateUntil")
        chain_need = (
            version_attr is None
            and declaring.is_temporal
            and (declaring.temporal == "bitemporal" or instruction.mutation == "update")
        )
        needs_documents: bool | frozenset[str]
        if chain_need:
            needs_documents = True
        elif assignment_bearing:
            member_columns = members(self._meta, entity)
            needs_documents = frozenset(
                member for member in assignments if member_columns[member][1]
            )
        else:
            needs_documents = False
        statement = compile_read(
            plan_.root_operation,
            self._meta,
            self._dialect,
            instruction.target.entity,
            result_form="row",
            lock=lock,
            include_value_objects=needs_documents,
        )
        rows = self._uow.read(lambda: self._resolve_rows(statement))
        writes: list[KeyedWrite] = []
        pending: list[tuple[ObjectKey, Observation | None]] = []
        for row in rows:
            key, observation, new_row = materialize_row(
                self._meta, entity, declaring, version_attr, instruction.mutation, assignments, row
            )
            if new_row is None:
                continue  # per-row no-op elimination (assignment-bearing verbs only)
            writes.append(
                KeyedWrite(
                    mutation=cast("Any", instruction.mutation),
                    entity=instruction.target.entity,
                    rows=(new_row,),
                    business_from=instruction.business_from,
                    business_to=instruction.business_to,
                )
            )
            pending.append((key, observation))
        if not writes:
            return
        for key, observation in pending:
            if observation is not None:
                self._uow.observe(key, observation)
        self._uow.buffer(AtomicUnit(writes=tuple(writes)))

    def _resolve_rows(self, statement: Statement) -> list[Row]:
        return self._conn.execute(self._dialect.to_driver_sql(statement.sql), list(statement.binds))


class Database:
    """A connected Parallax database handle: one adapter, one metamodel (spec §5)."""

    __slots__ = ("_clock", "_dialect", "_meta", "_port")

    def __init__(
        self,
        port: DbPort,
        meta: Metamodel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
    ) -> None:
        self._port = port
        self._meta = meta
        self._dialect = dialect
        self._clock: Clock = clock if clock is not None else SystemClock()

    @classmethod
    def connect(
        cls,
        adapter: DbPort,
        meta: Metamodel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
    ) -> Database:
        """Wire a concrete ``m-db-port`` adapter to the metamodel it will serve.

        The composition-root entry point (spec §8): only the root names a
        concrete adapter; everything above works against the port. ``dialect``
        defaults to the sole adapter's; ``clock`` defaults to the system clock
        (inject a fixed clock in tests).
        """
        return cls(adapter, meta, dialect=dialect, clock=clock)

    def find(self, statement: EntityStatement) -> Snapshot[Any]:
        """Execute ``statement`` exactly once, materializing fully, and return
        ``Snapshot[T]`` (spec §3). Non-transactional: no read lock, no
        participation mode. ``.history()`` / ``.as_of_range()`` return one root
        per milestone, each edge-pinned at its own milestone's from-instant.
        Returns ``Snapshot[Any]``: the concrete root type is resolved only at
        runtime (from the statement's own target), so callers annotate their
        own binding (``snapshot: Snapshot[Order] = db.find(...)``) for static
        typing.
        """
        target = statement.target
        op = statement.operation()
        entity = inheritance.declaring_entity(self._meta, self._meta.entity(target))
        pin = deep_fetch_statement_pin(op, entity)
        if is_milestone_set_op(op):
            history_result = find_history(op, self._meta, self._dialect, target, self._port)
            return snapshot_from_history_result(history_result, target, self._meta)
        find_result = find(op, self._meta, self._dialect, target, self._port)
        return snapshot_from_find_result(find_result, target, self._meta, pin)

    def transact[T](
        self,
        fn: Callable[[Transaction], T],
        *,
        retries: int | None = None,
        concurrency: Concurrency | None = None,
        retry_optimistic_conflicts: bool | None = None,
    ) -> T:
        """Run ``fn(tx)`` in a transaction, returning its value only after commit.

        Every option is sentinel-backed (spec §5): ``None`` means *apply the
        outermost defaults when this call opens the transaction* (``retries=10``,
        ``concurrency="locking"``, ``retry_optimistic_conflicts=False``) *and
        inherit the active transaction's settings when it joins one*. A call
        while a transaction is active on the current thread joins it — the
        closure receives the **same** :class:`Transaction`, its value returns
        immediately, and an explicit option that conflicts with the boundary
        raises :class:`TransactionOptionConflictError`. The outermost boundary
        owns commit, abort, and the ``m-auto-retry`` bounded retry loop; abort
        withholds the callback value, and an inner failure dooms the whole
        transaction (rollback-only) even if caught.
        """
        active = active_unit_of_work()
        if active is not None:
            demarcation = active.companion
            if not isinstance(demarcation, _Demarcation):
                raise UnitOfWorkError(
                    "a bare unit of work is active on this thread; db.transact can "
                    "only join a transaction it opened"
                )
            _check_join_options(
                demarcation.options,
                retries=retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
            )
            # The join path returns immediately and ignores these arguments in
            # favor of the active transaction's own (m-unit-work); rollback-only
            # foreclosure happens before the closure runs.
            return run_unit_of_work(
                lambda _: fn(demarcation.tx),
                settings=active.settings,
                clock=active.clock,
                meta=active.meta,
                flush_executor=active.flush_executor,
            )
        options = _ResolvedOptions(
            retries=retries if retries is not None else 10,
            concurrency=concurrency if concurrency is not None else "locking",
            retry_optimistic_conflicts=(
                retry_optimistic_conflicts if retry_optimistic_conflicts is not None else False
            ),
        )

        def attempt() -> T:
            def in_txn(conn: DbPort) -> T:
                def body(uow: UnitOfWork) -> T:
                    tx = Transaction(uow, conn, self._meta, self._dialect)
                    # Published for joining calls; visible only while core's
                    # active-transaction binding is, so it needs no cleanup.
                    uow.companion = _Demarcation(tx=tx, options=options)
                    return fn(tx)

                return run_unit_of_work(
                    body,
                    settings=TransactionSettings(concurrency=options.concurrency),
                    clock=self._clock,
                    meta=self._meta,
                    flush_executor=_flush_executor(
                        conn, self._meta, self._dialect, options.concurrency
                    ),
                    # The injected `m-batch-write` collapse vocabulary (COR-3
                    # Phase 8 increment 5) — `parallax.snapshot.handle` is the
                    # sole module cleared to import both `batch_write` and
                    # `m-unit-work`, so it supplies the SAME policy the
                    # conformance compile lane injects into its own direct
                    # `plan_flush` calls (`parallax.conformance.engine`).
                    collapse_policy=batch_write.collapses,
                )

            return self._port.transaction(in_txn)

        return run_with_retry(
            attempt,
            retries=options.retries,
            extra_retriable_types=(opt_lock.OptimisticLockConflictError,),
            extra_retriable=(
                _optimistic_conflict_retriable if options.retry_optimistic_conflicts else None
            ),
        )


def _optimistic_conflict_retriable(exc: BaseException) -> bool:
    """The ``retry_optimistic_conflicts`` opt-in's own retriability verdict
    (`m-opt-lock` "Retry contract"; `m-auto-retry.md` "Which failures are
    retriable"; ADR 0008 / `python.md` §5 L622-624) — injected into
    :func:`~parallax.core.auto_retry.run_with_retry` as its
    ``extra_retriable`` extension ONLY when the resolved option is set
    (:meth:`Database.transact`, above).

    ``parallax.core.auto_retry`` may not import ``parallax.core.opt_lock``
    (the import-linter contract fixes the `m-auto-retry` DAG edges at
    ``m-unit-work`` / ``m-db-error`` only), so this composed, opt-in-gated
    branch lives HERE, the one seam that legally sees both — the SAME two
    raise shapes :func:`~parallax.core.auto_retry._retriable_failure`
    already distinguishes for a transient database failure: the conflict
    itself (a direct :class:`~parallax.core.opt_lock.OptimisticLockConflictError`),
    or the rollback-only refusal whose ``__cause__`` preserves it (the JOIN
    case — an inner joined scope's own conflict marks the root
    rollback-only, and the outermost retry loop still applies per the
    original failure's category, spec §5). :class:`~parallax.core.opt_lock.
    StaleWriteError` (the distinct, NON-retriable locking-mode sibling,
    `m-opt-lock` "Conflict classification") is never named here — it stays
    outside the retriable set unconditionally, opt-in or not.
    """
    if isinstance(exc, opt_lock.OptimisticLockConflictError):
        return True
    if isinstance(exc, RollbackOnlyError):
        return isinstance(exc.__cause__, opt_lock.OptimisticLockConflictError)
    return False


# The spec §8 module-level spelling of the composition-root entry point.
connect = Database.connect


def _check_join_options(
    active: _ResolvedOptions,
    *,
    retries: int | None,
    concurrency: Concurrency | None,
    retry_optimistic_conflicts: bool | None,
) -> None:
    """Refuse a joining call's explicit option that conflicts with the boundary."""
    _refuse_conflict("retries", retries, active.retries)
    _refuse_conflict("concurrency", concurrency, active.concurrency)
    _refuse_conflict(
        "retry_optimistic_conflicts", retry_optimistic_conflicts, active.retry_optimistic_conflicts
    )


def _refuse_conflict(name: str, explicit: object | None, active_value: object) -> None:
    if explicit is not None and explicit != active_value:
        raise TransactionOptionConflictError(
            f"cannot join the active transaction with {name}={explicit!r}: the boundary "
            f"was opened with {name}={active_value!r} (a joining call may not "
            "re-negotiate; omit the option to inherit)"
        )


def _flush_executor(
    conn: DbPort, meta: Metamodel, dialect: Dialect, concurrency: Concurrency
) -> FlushExecutor:
    """The unit of work's injected flush sink: lower each planned write, execute
    every lowered statement in order, and enforce each STATEMENT's own
    affected-rows expectation (`m-opt-lock`; `m-audit-write`; `m-bitemp-write`).

    The single write-lowering seam (:func:`lower_write`) run on the transaction's
    own connection, inside the still-open ``port.transaction`` scope — so an
    abort rolls back force-flushed writes with everything else. Checking is
    PER-STATEMENT, not per-planned-write: a non-temporal keyed write lowers to
    exactly one statement (its own expectation, unchanged from increment 3), while
    a temporal write lowers to a close then zero-to-three chained opens — only the
    close carries an expectation (always ``1``), so a mismatch there raises and
    ABORTS BEFORE the chained rows ever execute (`m-audit-write` "MUST NOT silently
    succeed and proceed to chain"). ``LoweredStatement.stale_error`` picks the raised
    class: the retriable :class:`~parallax.core.opt_lock.OptimisticLockConflictError`
    for a gated mismatch (every non-temporal expectation, and a gated temporal
    close), the non-retriable :class:`~parallax.core.opt_lock.StaleWriteError` for an
    ungated (locking-mode) temporal close's mismatch.
    """

    def execute(plan: FlushPlan) -> None:
        for planned in plan.writes:
            for lowered in lower_write(planned, meta, dialect, concurrency, plan.tx_instant):
                affected = conn.execute_write(
                    dialect.to_driver_sql(lowered.statement.sql), list(lowered.statement.binds)
                )
                if lowered.expected_affected is not None and affected != lowered.expected_affected:
                    raise _conflict_error(planned, meta, affected, lowered)

    return execute


def _conflict_error(
    planned: PlannedWrite, meta: Metamodel, actual: int | None, lowered: LoweredStatement
) -> opt_lock.OptimisticLockConflictError | opt_lock.StaleWriteError:
    """The affected-row-mismatch error for one lowered statement — the retriable
    gated conflict, or (``lowered.stale_error``) the non-retriable ungated
    temporal-close outcome (`m-audit-write` / `m-bitemp-write`). Resolves this
    seam's own identifying context (the instruction's object key) and defers
    the actual classification to :func:`~parallax.core.opt_lock.classify_mismatch`
    — the one place that decision is made, shared with the conformance
    engine's standalone conflict-close probe."""
    instruction = planned.instruction
    assert isinstance(instruction, KeyedWrite)  # only a keyed write ever carries an expectation
    key = object_key(instruction, meta)
    assert key is not None  # an expectation is attached only alongside a resolved object key
    assert lowered.expected_affected is not None  # the caller's own guard
    return opt_lock.classify_mismatch(
        instruction.entity,
        key[1],
        lowered.expected_affected,
        actual,
        stale_error=lowered.stale_error,
    )
