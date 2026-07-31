"""``parallax.snapshot.handle._database`` — demarcation and the flush edge (spec §5).

The composition root's own module: :meth:`Database.connect` wires a concrete
``m-db-port`` adapter to a metamodel, :meth:`Database.find` runs the shared read
executor once outside any transaction, and :meth:`Database.transact` is the
callback demarcation — sentinel-backed options, join with the option-conflict
check, the ``m-auto-retry`` bounded retry loop, and the flush executor it injects
into the unit of work.

That injected executor is where the package's two halves meet: it lowers the
Write Plan the injected :class:`~parallax.core.unit_work.WritePlanner` produces
through :func:`~parallax.snapshot.handle._write_lowering.stream_lowered` and runs
each statement on the transaction's own connection, so an abort rolls back
force-flushed writes with everything else. ``parallax.core.auto_retry`` may not
import ``parallax.core.opt_lock``, so the ``retry_optimistic_conflicts`` opt-in's
classification branch (``_optimistic_conflict_retriable``) is composed here too.

This is the TOP of the package's internal graph: it imports
:mod:`parallax.snapshot.handle._read`, :mod:`~parallax.snapshot.handle._transaction`,
:mod:`~parallax.snapshot.handle._write_lowering`,
:mod:`~parallax.snapshot.handle._write_types`, and
:mod:`~parallax.snapshot.handle._planning` for the one Write Planner it builds
once per connected Metamodel, and nothing in the package imports it except
``handle/__init__.py``, which re-exports its three public names
(:class:`Database`, :func:`connect`, :class:`TransactionOptionConflictError`)
through the frozen ``__all__``. Because only those three cross the boundary,
every helper here keeps its leading underscore — the cross-module bare-name
convention the sibling modules follow has nothing to bite on.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from parallax.core.auto_retry import run_with_retry
from parallax.core.db_port import DbPort
from parallax.core.dialect import POSTGRES, Dialect

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`, not by
# per-name underscores, which under pyright strict would make every intra-package
# import a reportPrivateUsage error.
from parallax.core.entity import MetamodelBinding, MetamodelHub
from parallax.core.entity import Statement as EntityStatement

# First-party support, deliberately absent from `parallax.core.entity`'s exports:
# this composition root connects to an accepted `Metamodel`, so it needs both
# facts out of a hub.
from parallax.core.entity._hub import sealed_model
from parallax.core.metamodel import Metamodel, entity_by_name
from parallax.core.unit_work import (
    Clock,
    Concurrency,
    FlushExecutor,
    OptimisticLockConflictError,
    RollbackOnlyError,
    SubjectIdentity,
    SystemClock,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WritePlan,
    WritePlanner,
    active_unit_of_work,
    enforce_affected_rows,
    run_unit_of_work,
)
from parallax.snapshot.handle._planning import build_write_planner
from parallax.snapshot.handle._read import (
    Snapshot,
    declaring_metadata,
    deep_fetch_statement_pin,
    find,
    find_history,
    is_milestone_set_op,
    snapshot_from_find_result,
    snapshot_from_history_result,
)
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._write_lowering import stream_lowered

__all__ = ["Database", "TransactionOptionConflictError", "connect"]

# The transitional audit-neutral Subject Identity every production planning
# request carries until COR-55 implements the Principal boundary. Private,
# module-local, and nonempty: not a Principal implementation, a default
# identity, or a public caller option — COR-55 deletes this constant and
# threads a real captured Subject Identity through in its place.
_TRANSITIONAL_SUBJECT_IDENTITY: Final[SubjectIdentity] = SubjectIdentity(
    "cor-62-transitional-subject"
)


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
    :func:`~parallax.core.auto_retry.run_with_retry` (`m-opt-lock`
    "Retry contract").
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

    __slots__ = ("_binding", "_clock", "_dialect", "_meta", "_planner", "_port")

    def __init__(
        self,
        port: DbPort,
        meta: MetamodelHub | Metamodel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
    ) -> None:
        self._port = port
        self._meta: Metamodel
        self._binding: MetamodelBinding | None
        if isinstance(meta, MetamodelHub):
            sealed = sealed_model(meta)
            self._meta, self._binding = sealed.model, sealed.binding
        else:
            self._meta, self._binding = meta, None
        self._dialect = dialect
        self._clock: Clock = clock if clock is not None else SystemClock()
        # One Write Planner per connected Metamodel, reused across every
        # `transact()` attempt (`m-unit-work`: the planner is constructed once
        # per accepted Metamodel with its strategy adapters already wired).
        self._planner: WritePlanner = build_write_planner(self._meta)

    @classmethod
    def connect(
        cls,
        adapter: DbPort,
        meta: MetamodelHub | Metamodel,
        *,
        dialect: Dialect = POSTGRES,
        clock: Clock | None = None,
    ) -> Database:
        """Wire a concrete ``m-db-port`` adapter to the metamodel it will serve.

        The composition-root entry point (spec §8): only the root names a
        concrete adapter; everything above works against the port. ``dialect``
        defaults to the sole adapter's; ``clock`` defaults to the system clock
        (inject a fixed clock in tests).

        A class-backed hub additionally carries the Metamodel Binding every
        class-requiring capability needs — ``Snapshot[T]`` wrapping above all.
        A bare accepted Metamodel connects just as well and serves the whole
        neutral-row read path; only wrapping refuses.
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
        read_target = entity_by_name(self._meta, target)
        assert read_target is not None  # a statement's target is always declared
        pin = deep_fetch_statement_pin(op, declaring_metadata(self._meta, read_target))
        if is_milestone_set_op(op):
            history_result = find_history(op, self._meta, self._dialect, target, self._port)
            return snapshot_from_history_result(history_result, target, self._meta, self._binding)
        find_result = find(op, self._meta, self._dialect, target, self._port)
        return snapshot_from_find_result(find_result, target, self._meta, pin, self._binding)

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
                planner=self._planner,
                subject_identity=_TRANSITIONAL_SUBJECT_IDENTITY,
            )
        options = _ResolvedOptions(
            retries=retries if retries is not None else 10,
            concurrency=concurrency if concurrency is not None else "locking",
            retry_optimistic_conflicts=(
                retry_optimistic_conflicts if retry_optimistic_conflicts is not None else False
            ),
        )

        # The unit of work plans against the accepted model the ``Database`` already
        # holds; a joining call inherits the active unit of work's own.
        model = self._meta

        def attempt() -> T:
            def in_txn(conn: DbPort) -> T:
                def body(uow: UnitOfWork) -> T:
                    tx = Transaction(uow, conn, self._meta, self._dialect, self._binding)
                    # Published for joining calls; visible only while core's
                    # active-transaction binding is, so it needs no cleanup.
                    uow.companion = _Demarcation(tx=tx, options=options)
                    return fn(tx)

                return run_unit_of_work(
                    body,
                    settings=TransactionSettings(concurrency=options.concurrency),
                    clock=self._clock,
                    meta=model,
                    flush_executor=_flush_executor(conn, model, self._dialect),
                    # The injected Write Planner — `parallax.snapshot.handle`
                    # is the sole module cleared to import both `batch_write`
                    # and `m-unit-work`, so it alone builds the strategy
                    # adapters `build_write_planner` wires. The conformance
                    # compile lane calls the SAME factory, so the two lanes
                    # plan through one deterministic computation.
                    planner=self._planner,
                    subject_identity=_TRANSITIONAL_SUBJECT_IDENTITY,
                )

            return self._port.transaction(in_txn)

        return run_with_retry(
            attempt,
            retries=options.retries,
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

    The retry loop already recognizes the canonical conflict; what stays
    caller policy is whether a recognized conflict is RETRIED, which is what
    this predicate answers. It covers the SAME two raise shapes
    :func:`~parallax.core.auto_retry._retriable_failure` already distinguishes
    for a transient database failure: the conflict itself, or the rollback-only
    refusal whose ``__cause__`` preserves it (the JOIN case — an inner joined
    scope's own conflict marks the root rollback-only, and the outermost retry
    loop still applies per the original failure's category, spec §5). The
    remaining Write Effect Errors are never named here: a Stale Write, a Missing
    Target, and a Cardinality Corruption stay outside the retriable set
    unconditionally, opt-in or not.
    """
    if isinstance(exc, OptimisticLockConflictError):
        return True
    if isinstance(exc, RollbackOnlyError):
        return isinstance(exc.__cause__, OptimisticLockConflictError)
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


def _flush_executor(conn: DbPort, model: Metamodel, dialect: Dialect) -> FlushExecutor:
    """The unit of work's injected flush sink: lower each planned step, execute
    every statement in order, and hand each result back to the unit of work to
    interpret.

    The single write-lowering seam (:func:`stream_lowered`) run on the
    transaction's own connection, inside the still-open ``port.transaction``
    scope — so an abort rolls back force-flushed writes with everything else.
    Every step lowers to exactly one statement, and a temporal mutation's close
    precedes the rows it chains, so a failure on the close aborts BEFORE those
    rows ever execute.

    This executor performs NO classification of its own: the injected Write
    Planner already spent the concurrency mode while settling each step, and
    this reports only the driver's count to
    :func:`~parallax.core.unit_work.enforce_affected_rows`, which owns the
    authoritative reading of the step's Affected Rows Policy (ADR 0048).
    """

    def execute(plan: WritePlan) -> None:
        for step, statement in stream_lowered(plan, model, dialect):
            affected = conn.execute_write(
                dialect.to_driver_sql(statement.sql), list(statement.binds)
            )
            enforce_affected_rows(step, affected)

    return execute
