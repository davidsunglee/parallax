"""``parallax.snapshot.handle._demarcation`` — the outermost transaction
demarcation and the flush edge.

:class:`Demarcation` is what ``Database.transact`` delegates to once re-entry
has been refused: sentinel-backed options, the join through the exact
originating handle with the option-conflict check, the ``m-auto-retry`` bounded
retry loop, the per-attempt adoption of the Serving Model's current selection,
and the flush executor it injects into the unit of work. A ``Database`` builds
exactly one at connect, over its port, clock, installed lifecycle, and Serving
Model; it has one adapter and is an internal seam rather than a Protocol.

Each outer attempt adopts one complete selection before the boundary is asked
to begin and retains it through commit or rollback: the attempt's lifecycle
activity opens carrying that edition, the :class:`Transaction` it hands the
callback is built over that selection's two projections, and the unit of work
plans through that selection's Write Planner. A retry adopts afresh, so one
invocation may run attempts under two editions; a join inherits the active
attempt's transaction and selection and adopts nothing. An ordinary failure
escaping the whole invocation surfaces as
:class:`~parallax.snapshot.handle._adoption.ExecutionFailure` under the edition
of the attempt that failed, applied after the retry loop has resolved so the
classifier saw the underlying error.

The injected executor is where the package's two halves meet: it lowers the
Write Plan the adopted :class:`~parallax.core.unit_work.WritePlanner` produces
through :func:`~parallax.snapshot.handle._write_lowering.stream_lowered` and runs
each statement on the transaction's own connection, so an abort rolls back
force-flushed writes with everything else. ``parallax.core.auto_retry`` may not
import ``parallax.core.opt_lock``, so the ``retry_optimistic_conflicts`` opt-in's
classification branch (``_optimistic_conflict_retriable``) is composed here too.

The three public refusals declared here — :class:`TransactionOptionConflictError`,
:class:`TransactionOwnershipError`, :class:`TransactionRollbackError` — are the
demarcation's own and are re-exported through ``handle/__init__.py``'s frozen
``__all__``; every other name keeps its leading underscore because nothing
outside this module reaches it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from parallax.core.auto_retry import check_retry_bound, run_with_retry
from parallax.core.db_port import (
    BeginFailed,
    Committed,
    ConnectionAcquisitionError,
    DatabaseConnection,
    DatabaseRuntime,
    IsolationLevel,
    RollbackFailed,
    RolledBack,
    TransactionOutcome,
    isolation_level,
)
from parallax.core.execution_lifecycle._activity import (
    INERT,
    InstalledLifecycle,
    TransactionAttemptActivity,
    WriteBatchActivity,
    open_transaction_root,
)
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    Clock,
    Concurrency,
    OptimisticLockConflictError,
    RollbackOnlyError,
    SubjectIdentity,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WriteBatchTrigger,
    WritePlan,
    WritePlanner,
    active_unit_of_work,
    capture_subject_identity,
    enforce_affected_rows,
    run_unit_of_work,
)

# Sibling implementation modules. None of these names carries a leading
# underscore, precisely because it crosses a module boundary: privacy is carried
# by the private MODULE names and by the package's frozen `__all__`.
from parallax.snapshot.handle._adoption import AdoptedExecution
from parallax.snapshot.handle._connection_lifecycle import enter_connection, exit_connection
from parallax.snapshot.handle._publication import (
    ServingModel,
    read_projection,
    write_projection,
)
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._write_lowering import stream_lowered

__all__ = [
    "Demarcation",
    "TransactionOptionConflictError",
    "TransactionOwnershipError",
    "TransactionRollbackError",
]

# The audit-neutral Subject Identity every production planning request carries
# while no Principal attributes one: private, module-local, and captured through
# the boundary's own nonempty check (`capture_subject_identity`) — never a
# Principal implementation, a default identity, or a public caller option.
# Attributed capture belongs to the outer database-operation boundary a Principal
# is read at, which is the only place that can name a subject.
_UNATTRIBUTED_SUBJECT_IDENTITY: Final[SubjectIdentity] = capture_subject_identity("unattributed")


class TransactionOptionConflictError(ValueError):
    """A joining ``db.transact`` call tried to re-negotiate the boundary.

    A joining call may not change the active transaction's settings: an explicit
    (non-``None``) option whose value conflicts with the outermost boundary's
    resolved setting raises; an explicit equal value and an omitted option are
    accepted (spec §5).
    """


class TransactionOwnershipError(RuntimeError):
    """A nested ``db.transact`` call was made through a foreign ``Database``.

    The active demarcation records the exact ``Database`` object that opened it,
    and a nested call joins only through that same object. An alias of the owner
    joins and receives the identical :class:`Transaction`; every different handle
    is refused even when it carries the same model, adapter, clock, or
    otherwise equivalent configuration, because the owner is scoped state rather
    than a registry keyed by any of those.

    The refusal precedes rollback-only joining, the option-conflict check,
    closure execution, Unit of Work mutation, SQL, and adapter access, and
    retains neither handle — :data:`code` and the message are its whole public
    state.
    """

    code: Final[str] = "transaction-owner-mismatch"


class TransactionRollbackError(RuntimeError):
    """The transaction could not be undone after something ended it.

    Two failures are live at once and reporting either alone misreports what
    happened: :attr:`triggering_error` ended the transaction, and
    :attr:`rollback_error` is why undoing it did not complete. The rollback error
    is the ``__cause__`` as well, so a reader of the traceback sees why the
    trigger is no longer the whole story.

    What the transaction left behind is therefore unknown, which is why this is
    never retried however retriable the trigger was, and why the port discards
    the connection it happened on. A control-flow or fatal trigger — a
    ``KeyboardInterrupt``, a cancellation — is never wrapped in this: it stays
    primary and carries the rollback failure as its own cause instead, so a
    shutdown in progress is not downgraded to an ordinary error.
    """

    def __init__(self, triggering_error: BaseException, rollback_error: Exception) -> None:
        super().__init__(
            f"the transaction could not be rolled back after {triggering_error!r}; "
            f"the rollback failed with {rollback_error!r}, so what it left behind is unknown"
        )
        self.triggering_error = triggering_error
        self.rollback_error = rollback_error


class _BeginFailure(Exception):
    """A begin failure in transit past the bounded retry loop.

    An attempt whose boundary never opened ran no callback, so
    `m-execution-lifecycle` makes its failure terminal however retriable the
    error's own category is — but ``m-auto-retry`` classifies by the exception
    it catches, and a begin failure is an ordinary
    :class:`~parallax.core.db_error.DatabaseError` like any other. Travelling
    as a type the loop does not catch is what makes it terminal;
    :meth:`Demarcation.transact` unwraps it immediately outside the loop, so
    nothing above ever sees this class.
    """

    def __init__(self, error: Exception) -> None:
        super().__init__(error)
        self.error = error


@dataclass(frozen=True, slots=True)
class _ResolvedOptions:
    """The outermost boundary's resolved ``db.transact`` options.

    ``concurrency`` also lives on the core :class:`TransactionSettings`;
    ``retries`` and ``retry_optimistic_conflicts`` are demarcation-level only
    (the core unit of work never sees them). ``retry_optimistic_conflicts``
    is stored for the join/conflict contract AND gates
    :func:`_optimistic_conflict_retriable` — the opt-in-only classification
    branch :meth:`Demarcation.transact` injects into
    :func:`~parallax.core.auto_retry.run_with_retry` (`m-opt-lock`
    "Retry contract").

    ``isolation`` is the one option with no resolved default of its own: it
    stays whatever the call named, because ``None`` here is a request for
    nothing rather than a stand-in for a value Parallax would supply. It is the
    vocabulary's own spelling of that request rather than the caller's object,
    so what a joining call is compared against, and what every adapter keys its
    per-level mapping by, is a plain level. Every physical attempt of this
    boundary asks the port for the same one, so a retry re-opens at the
    isolation the invocation asked for rather than at the database's default.
    """

    retries: int
    concurrency: Concurrency
    retry_optimistic_conflicts: bool
    isolation: IsolationLevel | None


@dataclass(frozen=True, slots=True)
class _Boundary:
    """What the outermost boundary publishes on the unit of work's ``companion``.

    A joining ``db.transact`` call needs the same :class:`Transaction` to hand
    its closure, the boundary's resolved options for the conflict check, the
    exact ``Database`` that opened the boundary so ownership can be settled
    before either, the physical attempt currently running — which is what a
    joined invocation is a child activity OF — and the Write Planner of the
    selection that attempt adopted, so a join plans through what it inherited
    rather than adopting anything. All five ride core's single per-thread active
    binding, so their visibility ends exactly when it does (no handle-owned
    thread-local, nothing to clean up). ``owner`` is a strong reference
    deliberately: it is scoped state whose lifetime is the boundary's, not a
    registry entry.
    """

    tx: Transaction
    options: _ResolvedOptions
    owner: object
    attempt: TransactionAttemptActivity
    planner: WritePlanner


class Demarcation:
    """One handle's callback demarcation, built once at connect.

    Holds what every invocation needs and nothing an invocation retains: the
    runtime every attempt acquires its connection from, the Clock the unit of
    work reads, the installed lifecycle every root and attempt reports through,
    and the Serving Model each attempt adopts from. Neither the selection nor a
    connection is held here — that is what makes both of them per attempt, so a
    retry adopts afresh and acquires afresh rather than replaying over what its
    predecessor left.
    """

    __slots__ = ("_clock", "_lifecycle", "_runtime", "_serving")

    def __init__(
        self,
        runtime: DatabaseRuntime,
        clock: Clock,
        lifecycle: InstalledLifecycle | None,
        serving: ServingModel,
    ) -> None:
        self._runtime = runtime
        self._clock = clock
        self._lifecycle = lifecycle
        self._serving = serving

    def transact[T](
        self,
        fn: Callable[[Transaction], T],
        *,
        owner: object,
        retries: int | None,
        concurrency: Concurrency | None,
        retry_optimistic_conflicts: bool | None,
        isolation: IsolationLevel | None,
    ) -> T:
        """Run ``fn(tx)`` in a transaction owned by ``owner``, returning its
        value only after commit.

        The public contract is ``Database.transact``'s. What is decided here:
        the deterministic refusals run first and keep their own types, the join
        path returns inside the active attempt without adopting or wrapping,
        and an outer invocation opens its root, runs the retry loop with one
        adoption per attempt, and is contextualized as a whole once the loop
        has resolved.
        """
        # Ahead of the join comparison below, because a level outside the
        # vocabulary is the CALL's own defect: comparing it first would report a
        # nonsense level as a disagreement with the active boundary, which reads
        # as though naming it correctly would have been accepted.
        requested = None if isolation is None else isolation_level(isolation)
        active = active_unit_of_work()
        if active is not None:
            boundary = active.companion
            if not isinstance(boundary, _Boundary):
                raise UnitOfWorkError(
                    "a bare unit of work is active on this thread; db.transact can "
                    "only join a transaction it opened"
                )
            if boundary.owner is not owner:
                raise TransactionOwnershipError(
                    "this Database did not open the active transaction, so it cannot "
                    "join it (transaction-owner-mismatch); only the exact Database "
                    "object that opened the boundary joins, however equivalent "
                    "another handle's model, adapter, or clock may be"
                )
            _check_join_options(
                boundary.options,
                retries=retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
                isolation=requested,
            )
            # The join path returns immediately and ignores these arguments in
            # favor of the active transaction's own (m-unit-work); rollback-only
            # foreclosure happens before the closure runs. The joined activity is
            # a child of the attempt currently running rather than a root of its
            # own, and it opens after the deterministic refusals above precisely
            # because those refusals reach no transaction at all. Nothing is
            # adopted and nothing is wrapped: the selection and the failure
            # contract are the outer invocation's.
            with boundary.attempt.joined_invocation():
                return run_unit_of_work(
                    lambda _: fn(boundary.tx),
                    settings=active.settings,
                    clock=active.clock,
                    meta=active.meta,
                    flush_executor=active.flush_executor,
                    write_batch_opening=active.write_batch_opening,
                    planner=boundary.planner,
                    subject_identity=_UNATTRIBUTED_SUBJECT_IDENTITY,
                )
        options = _ResolvedOptions(
            retries=retries if retries is not None else 10,
            concurrency=concurrency if concurrency is not None else "optimistic",
            retry_optimistic_conflicts=(
                retry_optimistic_conflicts if retry_optimistic_conflicts is not None else False
            ),
            isolation=requested,
        )
        # The last deterministic refusal, and it belongs here rather than at the
        # retry loop's own entry: the loop runs inside the root opened below, so
        # a bound rejected only there would have called the Provider and emitted
        # this invocation's Started and Finished first (`m-execution-lifecycle`).
        check_retry_bound(options.retries)

        extra_retriable = (
            _optimistic_conflict_retriable if options.retry_optimistic_conflicts else None
        )
        # The Root Execution opens after the deterministic refusals above and
        # spans every physical attempt below, and it opens BEFORE anything is
        # adopted: a Provider that fails to open keeps its own type, because no
        # edition has been taken that a failure could be reported under.
        root = open_transaction_root(
            self._lifecycle,
            concurrency=options.concurrency,
            retries=options.retries,
            retry_optimistic_conflicts=options.retry_optimistic_conflicts,
            isolation=options.isolation,
            extra_retriable=extra_retriable,
        )
        execution = AdoptedExecution(self._serving)

        def invoke() -> T:
            with root as invocation:

                def attempt() -> T:
                    # Adopted before the attempt opens, so the edition its
                    # Started event carries is the one the boundary is
                    # then asked to begin under — and a retry, re-entering
                    # here, adopts whatever is serving by then.
                    selection = execution.adopt()
                    read = read_projection(selection)
                    write = write_projection(selection)
                    meta = write.model.meta
                    with invocation.attempt(selection.edition) as physical:

                        def in_txn(conn: DatabaseConnection) -> T:
                            edge = _FlushEdge(conn, meta, physical)

                            def body(uow: UnitOfWork) -> T:
                                tx = Transaction(uow, conn, read, write, physical, self._lifecycle)
                                # Published for joining calls; visible only
                                # while core's active-transaction binding is,
                                # so it needs no cleanup.
                                uow.companion = _Boundary(
                                    tx=tx,
                                    options=options,
                                    owner=owner,
                                    attempt=physical,
                                    planner=write.planner,
                                )
                                return fn(tx)

                            return run_unit_of_work(
                                body,
                                settings=TransactionSettings(concurrency=options.concurrency),
                                clock=self._clock,
                                meta=meta,
                                flush_executor=edge.execute,
                                write_batch_opening=edge.opening,
                                # The adopted selection's Write Planner:
                                # retained by this unit of work for its life,
                                # and reused by every join into it rather than
                                # re-adopted.
                                planner=write.planner,
                                subject_identity=_UNATTRIBUTED_SUBJECT_IDENTITY,
                            )

                        # One connection for this attempt and everything inside
                        # it — the boundary, the reads, the write batches, the
                        # streams — acquired after the attempt started and given
                        # back before it finishes. A retry re-enters this closure
                        # and acquires again, so nothing of a failed attempt's
                        # resource is carried into its successor; the pool may
                        # well hand back the same physical connection, which is
                        # its business rather than this loop's.
                        resource = self._runtime.connection()
                        try:
                            conn = enter_connection(resource)
                        except ConnectionAcquisitionError as unacquired:
                            # No boundary opened and no callback ran, so this is
                            # the same terminal outcome a refused BEGIN reaches:
                            # there is nothing to undo and nothing to replay.
                            # There is also nothing to release — a failed entry
                            # already cleaned up whatever it took.
                            physical.begin_failed(unacquired)
                            raise _BeginFailure(unacquired) from unacquired
                        try:
                            settled = _attempted(
                                conn.transaction(in_txn, isolation=options.isolation), physical
                            )
                        except BaseException as failure:
                            exit_connection(resource, failure)
                            raise
                        exit_connection(resource, None)
                        return settled

                try:
                    return run_with_retry(
                        attempt, retries=options.retries, extra_retriable=extra_retriable
                    )
                except _BeginFailure as failed:
                    # Unwrapped here rather than at the port, so the loop sees a
                    # type it does not retry.
                    begin_failure = failed.error
                # Raised once the handler has been left, so the carrier enters
                # neither the cause nor the context of what leaves: the caller
                # reads exactly the error the port made, with the chain that
                # error already had — and the root's own Finished event,
                # delivered as this scope is left, attributes it to the attempt
                # that reported it.
                raise begin_failure

        # Contextualized around the whole invocation and outside the root scope:
        # the classifier saw every underlying error, the lifecycle reported it
        # under the attempt it came from, and what the caller receives names
        # the edition of the attempt that failed last.
        return execution.contextualized(invoke)


def _attempted[T](outcome: TransactionOutcome[T], attempt: TransactionAttemptActivity) -> T:
    """What one physical attempt answers, from the boundary outcome the port reported.

    The port reports what happened; this decides what a caller sees, which is the
    only place the two can be reconciled — the port cannot know that a rollback
    failure must never be retried while a rolled-back deadlock must be, and the
    retry loop cannot know which phase failed.

    A rolled-back transaction propagates its triggering error unchanged, so what
    a caller catches is what their own callback or the database raised. Only a
    failed rollback substitutes an error of its own, because then neither live
    error tells the whole story.

    It is also where the attempt activity learns its outcome, for the same
    reason: the port's report is the only account of what the boundary did. A
    boundary that never opened is one such outcome — the attempt had already
    adopted and started, so it finishes as begin-failed rather than not at all.
    """
    match outcome:
        case Committed(value):
            attempt.committed()
            return value
        case BeginFailed(error):
            attempt.begin_failed(error)
            raise _BeginFailure(error) from error
        case RolledBack(trigger):
            attempt.rolled_back(trigger)
            raise trigger.error
        case RollbackFailed(trigger, rollback_error):
            attempt.rollback_failed(trigger, rollback_error)
            triggering_error = trigger.error
            if isinstance(triggering_error, Exception):
                raise TransactionRollbackError(triggering_error, rollback_error) from rollback_error
            # A control-flow or fatal trigger stays primary: an interrupt or a
            # cancellation is not an ordinary failure to be wrapped in one.
            raise triggering_error from rollback_error


def _optimistic_conflict_retriable(exc: BaseException) -> bool:
    """The ``retry_optimistic_conflicts`` opt-in's own retriability verdict
    (`m-opt-lock` "Retry contract"; `m-auto-retry.md` "Which failures are
    retriable"; ADR 0008 / `python.md` §5) — injected into
    :func:`~parallax.core.auto_retry.run_with_retry` as its
    ``extra_retriable`` extension ONLY when the resolved option is set
    (:meth:`Demarcation.transact`, above).

    The retry loop already recognizes the canonical conflict; what stays
    caller policy is whether a recognized conflict is RETRIED, which is what
    this predicate answers. It covers the SAME two raise shapes
    :func:`~parallax.core.auto_retry.retriable_failure` already distinguishes
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


def _check_join_options(
    active: _ResolvedOptions,
    *,
    retries: int | None,
    concurrency: Concurrency | None,
    retry_optimistic_conflicts: bool | None,
    isolation: IsolationLevel | None,
) -> None:
    """Refuse a joining call's explicit option that conflicts with the boundary.

    ``isolation`` joins on the same terms as the other three, and the sentinel
    carries one more meaning there: a boundary opened without one is active at
    ``None``, so a joining call NAMING a level conflicts with it. That is the
    honest answer rather than a strict one — the transaction is already open, and
    an isolation is only a property of a boundary at the moment it opens.
    """
    _refuse_conflict("retries", retries, active.retries)
    _refuse_conflict("concurrency", concurrency, active.concurrency)
    _refuse_conflict(
        "retry_optimistic_conflicts", retry_optimistic_conflicts, active.retry_optimistic_conflicts
    )
    _refuse_conflict("isolation", isolation, active.isolation)


def _refuse_conflict(name: str, explicit: object | None, active_value: object) -> None:
    if explicit is not None and explicit != active_value:
        raise TransactionOptionConflictError(
            f"cannot join the active transaction with {name}={explicit!r}: the boundary "
            f"was opened with {name}={active_value!r} (a joining call may not "
            "re-negotiate; omit the option to inherit)"
        )


class _FlushEdge:
    """One attempt's flush edge: the Write Batch each flush runs inside, and the
    statements that flush's plan lowers to.

    The two are one object because they are one batch. The unit of work
    announces a flush before planning it and hands the finished plan over
    afterwards, so nothing passed through either call alone could carry the
    activity from the first to the second — and one flush is ONE Write Batch
    (`m-execution-lifecycle`) however many statements the plan lowers to, with
    each statement one Database Call child of it. A flush never nests: the
    executor reaches the port and nothing else, so the batch a call runs under is
    always the one most recently opened.
    """

    __slots__ = ("_attempt", "_batch", "_conn", "_model")

    def __init__(
        self,
        conn: DatabaseConnection,
        model: Metamodel,
        attempt: TransactionAttemptActivity,
    ) -> None:
        self._conn = conn
        self._model = model
        self._attempt = attempt
        self._batch: WriteBatchActivity = INERT

    def opening(self, trigger: WriteBatchTrigger) -> WriteBatchActivity:
        """The scope one flush of this attempt's buffer runs inside.

        The unit of work enters it before planning and leaves it when the flush
        is over, so a planning refusal is a failed batch rather than work outside
        every batch, and a batch planning reduces to no DML at all still
        completes.
        """
        batch = self._attempt.write_batch(trigger)
        self._batch = batch
        return batch

    def execute(self, plan: WritePlan, *, trigger: WriteBatchTrigger) -> None:
        """Lower each planned step, execute every statement in order, and hand
        each result back to the unit of work to interpret.

        The single write-lowering seam (:func:`stream_lowered`) run on the
        transaction's own connection, inside the still-open ``port.transaction``
        scope — so an abort rolls back force-flushed writes with everything else.
        Every step lowers to exactly one statement, and a temporal mutation's
        close precedes the rows it chains, so a failure on the close aborts
        BEFORE those rows ever execute.

        This performs NO classification of its own: the adopted Write Planner
        already spent the concurrency mode while settling each step, and this
        reports only the driver's count to
        :func:`~parallax.core.unit_work.enforce_affected_rows`, which owns the
        authoritative reading of the step's Affected Rows Policy (ADR 0048).
        That enforcement runs inside its own attribution bracket, because a
        shortfall is judged AFTER the call it judges has already completed: the
        bracket is what lets the batch's failure name that completed call
        instead of the enforcement being read as a failure of the batch itself.
        """
        # The trigger is the batch's, and the batch this runs inside already
        # carries it; taking it again here would be a second spelling of one
        # fact.
        del trigger
        dialect = self._conn.dialect
        batch = self._batch
        for step, statement in stream_lowered(plan, self._model, dialect):
            with batch.database_call(statement, "write", step.entity) as call:
                affected = self._conn.execute_write(
                    dialect.to_driver_sql(statement.sql), list(statement.binds)
                )
                call.write_completed(affected)
            with batch.enforcing(call):
                enforce_affected_rows(step, affected)
