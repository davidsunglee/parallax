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
planning with the ``m-opt-lock`` gate policy this seam already owns; increment 5
added the predicate-selected (set-based) and multi-row batch-collapse forms — an
unversioned, non-temporal predicate write lowers READLESS (`m-batch-write`
"Predicate-selected readless forms"), while a versioned or temporal one
MATERIALIZES to per-row keyed writes at buffer time (:class:`Transaction`'s
``_where`` verb family, ADR 0014) before ever entering a flush plan. A form this
seam cannot lower still raises a loud :class:`WriteLoweringError` naming the
reason, never a wrong emission — mirroring the read compiler's forward-error
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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from parallax.core import batch_write, inheritance, opt_lock
from parallax.core.auto_retry import run_with_retry
from parallax.core.db_port import DbPort
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import Statement as EntityStatement
from parallax.core.unit_work import (
    Clock,
    Concurrency,
    FlushExecutor,
    FlushPlan,
    KeyedWrite,
    PlannedWrite,
    RollbackOnlyError,
    SystemClock,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    active_unit_of_work,
    object_key,
    run_unit_of_work,
)

# The private implementation modules. Some of what follows is a public name this
# package re-exports through `__all__` (every `_write_types` / `_write_lowering`
# name, ten of the `_read` ones, `Transaction`); the rest is an implementation seam
# the code still living here shares with them — the pin / result-conversion helpers
# `Database.find` shares with the read executor. None of those carry a leading
# underscore, precisely because they cross a module boundary: privacy is carried by
# the private MODULE names and by `__all__`, not by per-name underscores, which
# under pyright strict would make every intra-package import a reportPrivateUsage
# error.
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
from parallax.snapshot.handle._transaction import Transaction
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
