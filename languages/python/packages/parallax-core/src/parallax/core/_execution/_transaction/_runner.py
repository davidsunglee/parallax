from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, cast

from parallax.core._execution._adoption import AdoptedExecution
from parallax.core._execution._connection_lifecycle import enter_connection, exit_connection
from parallax.core._execution._options import (
    OMITTED,
    Omitted,
    ReadOnlyTxnOptions,
    TxnOptions,
    check_max_retries,
    check_retry_optimistic_conflicts,
)
from parallax.core._execution._publication import (
    ModelSelection,
    ServingModel,
    read_projection,
    write_projection,
)
from parallax.core._execution._transaction._attempt import ReadOnlyTxnAttempt, TxnAttempt
from parallax.core._execution._transaction._lifetime import ActiveBinding, TxnAttemptLifetime
from parallax.core._execution._unit_work.clock import Clock
from parallax.core._execution._unit_work.effects import OptimisticLockConflictError
from parallax.core._execution._unit_work.strategy import concurrency_preference
from parallax.core._execution._unit_work.uow import Concurrency, RollbackOnlyError
from parallax.core.auto_retry import run_with_retry
from parallax.core.db_port import (
    AccessMode,
    BeginFailed,
    Committed,
    DatabaseConnection,
    IsolationLevel,
    RollbackFailed,
    RolledBack,
    TransactionOutcome,
    isolation_level,
)
from parallax.core.execution_authority._authority import ExecutionCapture, same_execution
from parallax.core.execution_lifecycle._activity import (
    InstalledLifecycle,
    TransactionAttemptActivity,
    TransactionInvocationActivity,
    open_transaction_root,
    refuse_reentry,
)
from parallax.core.read_delivery._read_plan import ReadPlanner

__all__ = [
    "TransactionAccessModeError",
    "TransactionAuthorityError",
    "TransactionOptionConflictError",
    "TransactionOwnershipError",
    "TransactionRollbackError",
    "TransactionRunner",
]


class TransactionOptionConflictError(ValueError):
    """A joining invocation tried to re-negotiate the boundary.

    A joining call may not change the active transaction's settings: an explicit
    option whose value conflicts with the active transaction's resolved
    ``options`` raises; an explicit equal value and an omitted option are
    accepted.
    """


class TransactionOwnershipError(RuntimeError):
    """A nested invocation was made through a foreign resource root.

    The active transaction records the shared resource identity behind the
    Database Root that opened it. Scopes derived from that root or any root alias
    join and receive the identical transaction; a scope from every other
    root is refused even when it carries the same model, adapter, clock, or
    otherwise equivalent configuration.

    The refusal precedes rollback-only joining, the authority, access-mode, and
    option checks, closure execution, Unit of Work mutation, SQL, and adapter
    access, and retains neither scope — :data:`code` and the message are its
    whole public state.
    """

    code: Final[str] = "transaction-owner-mismatch"


class TransactionAuthorityError(RuntimeError):
    """A joining scope carries a different captured execution authority."""

    code: Final[str] = "transaction-authority-mismatch"


class TransactionAccessModeError(RuntimeError):
    """A nested invocation's entrypoint selects the other access mode.

    A read-only transaction admits only read-only joins and a writable one only
    writable joins, because joining reuses the active attempt and the native
    transaction it opened in its mode. Refused after ownership, rollback-only,
    and authority, and before the explicit options are compared or the joined
    callback runs.
    """

    code: Final[str] = "transaction-access-mode-mismatch"


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
    as a type the loop does not catch is what makes it terminal; the runner
    unwraps it immediately outside the loop, so nothing above ever sees this
    class.
    """

    def __init__(self, error: Exception) -> None:
        super().__init__(error)
        self.error = error


@dataclass(frozen=True, slots=True)
class _ActiveTransaction:
    """What the outermost attempt binds for joining invocations.

    A joining call needs the ``context`` the outer attempt's callback was
    handed, the shared resource ``root`` that opened it so ownership can be
    settled first, the ``capture`` that fixes execution authority, and the
    ``attempt`` currently running — whose mode, lifetime, and resolved options
    the join is admitted against and whose activity a joined invocation is a
    child of. All four are visible exactly while the binding is, so their
    visibility ends with the attempt's callback and completion. ``root`` is a
    strong reference deliberately: it is resource-scoped state whose lifetime
    is the transaction's, not a registry entry.
    """

    attempt: TxnAttempt | ReadOnlyTxnAttempt
    context: object
    root: object
    capture: ExecutionCapture


_ACTIVE: Final = ActiveBinding[_ActiveTransaction]()
"""The one active-transaction binding of every runner: a join through another
resource root must find the active transaction to be refused by it."""

type _AttemptFactory[A] = Callable[
    [DatabaseConnection, TransactionAttemptActivity, TxnAttemptLifetime], A
]
"""How one invocation constructs each of its attempts once the connection, the
attempt activity, and the attempt's lifetime exist."""


class TransactionRunner:
    """One resource root's transaction runner, built once at connect.

    Holds what every invocation shares and nothing scope-specific: the resource
    identity used for ownership, the Clock the unit of work reads, the installed
    lifecycle every root and attempt reports through, the Serving Model each
    attempt adopts from, and the read planner transactions participate through.
    The calling scope supplies its capture and defaults. Neither the selection,
    a connection, nor the active transaction is held here — that is
    what makes the first two per attempt, so a retry adopts afresh and acquires
    afresh rather than replaying over what its predecessor left, and what keeps
    the active transaction on the one per-thread binding alone.

    Writable and read-only invocations take one path: the same refusals, the
    same admission sequence when joining, and the same attempt lifecycle when
    outermost. They differ in the attempt each constructs, the options each
    resolves, and the access mode each asks the port for.
    """

    __slots__ = ("_clock", "_lifecycle", "_planner", "_root", "_serving")

    def __init__(
        self,
        root: object,
        clock: Clock,
        lifecycle: InstalledLifecycle | None,
        serving: ServingModel,
        planner: ReadPlanner,
    ) -> None:
        self._root = root
        self._clock = clock
        self._lifecycle = lifecycle
        self._serving = serving
        self._planner = planner

    def transact[Tx, T](
        self,
        fn: Callable[[Tx], T],
        context_for: Callable[[TxnAttempt], Tx],
        *,
        capture: ExecutionCapture,
        defaults: TxnOptions,
        max_retries: int | Omitted,
        concurrency: Concurrency | Omitted,
        retry_optimistic_conflicts: bool | Omitted,
        isolation: IsolationLevel | Omitted,
    ) -> T:
        """Run ``fn`` in a writable transaction under ``capture``, returning its
        value after commit.

        The public contract is the lifecycle scope's ``transact``. What is
        decided here: the deterministic refusals run first and keep their own
        types, the join path returns inside the active attempt without adopting
        or wrapping, and an outer invocation resolves its options once, opens its
        root, runs the retry loop with one adoption per attempt, and is
        contextualized as a whole once the loop has resolved.

        Each attempt is constructed fully wired before ``context_for``
        receives it, and ``fn`` is handed what that factory answered. A retry
        constructs a fresh attempt and asks the factory again; a join reuses the
        active context and asks nothing.
        """
        refuse_reentry(self._lifecycle)
        # Every explicit value is validated ahead of the join comparison below,
        # because a value outside its field's contract is the CALL's own defect:
        # comparing it first would report a nonsense value as a disagreement
        # with the active transaction, which reads as though naming it
        # correctly would have been accepted. An omitted keyword is left as the
        # marker until it is resolved — against the scope for an outer
        # invocation, against the active transaction for a join.
        bound = max_retries if isinstance(max_retries, Omitted) else check_max_retries(max_retries)
        preference = (
            concurrency if isinstance(concurrency, Omitted) else concurrency_preference(concurrency)
        )
        opt_in = (
            retry_optimistic_conflicts
            if isinstance(retry_optimistic_conflicts, Omitted)
            else check_retry_optimistic_conflicts(retry_optimistic_conflicts)
        )
        level = isolation if isinstance(isolation, Omitted) else isolation_level(isolation)
        active = _ACTIVE.active()
        if active is not None:
            joined = self._admitted(active, capture, TxnAttempt)
            _check_join_options(
                joined.options,
                max_retries=bound,
                concurrency=preference,
                retry_optimistic_conflicts=opt_in,
                isolation=level,
            )
            return _joined(joined, cast("Tx", active.context), fn)
        options = _resolved(
            defaults,
            max_retries=bound,
            concurrency=preference,
            retry_optimistic_conflicts=opt_in,
            isolation=level,
        )
        extra_retriable = (
            _optimistic_conflict_retriable if options.retry_optimistic_conflicts else None
        )
        # The Root Execution opens after the deterministic refusals above and
        # spans every physical attempt below, and it opens BEFORE anything is
        # adopted: a Provider that fails to open keeps its own type, because no
        # edition has been taken that a failure could be reported under.
        root = open_transaction_root(
            self._lifecycle,
            access_mode="read_write",
            concurrency=options.concurrency,
            retries=options.max_retries,
            retry_optimistic_conflicts=options.retry_optimistic_conflicts,
            isolation=options.isolation,
            extra_retriable=extra_retriable,
        )

        def attempt_for(selection: ModelSelection) -> _AttemptFactory[TxnAttempt]:
            read = read_projection(selection)
            write = write_projection(selection)
            return lambda conn, physical, lifetime: TxnAttempt(
                conn,
                read,
                write,
                physical,
                lifecycle=self._lifecycle,
                planner=self._planner,
                options=options,
                clock=self._clock,
                actor=capture.actor,
                lifetime=lifetime,
            )

        return self._invoke(
            fn,
            context_for,
            attempt_for,
            root=root,
            capture=capture,
            retries=options.max_retries,
            isolation=options.isolation,
            access_mode="read_write",
            extra_retriable=extra_retriable,
        )

    def read_only[Tx, T](
        self,
        fn: Callable[[Tx], T],
        context_for: Callable[[ReadOnlyTxnAttempt], Tx],
        *,
        capture: ExecutionCapture,
        defaults: TxnOptions,
        max_retries: int | Omitted,
        isolation: IsolationLevel | Omitted,
    ) -> T:
        """Run ``fn`` in a read-only transaction under ``capture``, returning
        its value after commit.

        :meth:`transact`'s path with a read-only attempt: the same refusals and
        join admission, a :class:`ReadOnlyTxnOptions` record resolved from the
        retry bound and isolation alone, and a boundary every attempt asks the
        port to open read-only.
        """
        refuse_reentry(self._lifecycle)
        bound = max_retries if isinstance(max_retries, Omitted) else check_max_retries(max_retries)
        level = isolation if isinstance(isolation, Omitted) else isolation_level(isolation)
        active = _ACTIVE.active()
        if active is not None:
            joined = self._admitted(active, capture, ReadOnlyTxnAttempt)
            _refuse_conflict("max_retries", bound, joined.options.max_retries)
            _refuse_conflict("isolation", level, joined.options.isolation)
            return _joined(joined, cast("Tx", active.context), fn)
        options = ReadOnlyTxnOptions(
            max_retries=defaults.max_retries if isinstance(bound, Omitted) else bound,
            isolation=defaults.isolation if isinstance(level, Omitted) else level,
        )
        root = open_transaction_root(
            self._lifecycle,
            access_mode="read_only",
            concurrency=None,
            retries=options.max_retries,
            retry_optimistic_conflicts=False,
            isolation=options.isolation,
            extra_retriable=None,
        )

        def attempt_for(selection: ModelSelection) -> _AttemptFactory[ReadOnlyTxnAttempt]:
            read = read_projection(selection)
            return lambda conn, physical, lifetime: ReadOnlyTxnAttempt(
                conn,
                read,
                physical,
                lifecycle=self._lifecycle,
                planner=self._planner,
                options=options,
                lifetime=lifetime,
            )

        return self._invoke(
            fn,
            context_for,
            attempt_for,
            root=root,
            capture=capture,
            retries=options.max_retries,
            isolation=options.isolation,
            access_mode="read_only",
            extra_retriable=None,
        )

    def _admitted[A: (TxnAttempt, ReadOnlyTxnAttempt)](
        self, active: _ActiveTransaction, capture: ExecutionCapture, mode: type[A]
    ) -> A:
        """The active attempt, once a joining invocation of ``mode`` is admitted
        to it, in this order: a transaction this resource root opened, not
        rollback-only, under the same execution authority, and in the joining
        entrypoint's access mode. Explicit options are the caller's to compare
        next."""
        if active.root is not self._root:
            raise TransactionOwnershipError(
                "this scope does not belong to the runtime that opened the active "
                "transaction (transaction-owner-mismatch)"
            )
        attempt = active.attempt
        attempt.lifetime.refuse_join()
        if not same_execution(active.capture, capture):
            raise TransactionAuthorityError(
                "the joining scope carries different execution authority "
                "(transaction-authority-mismatch)"
            )
        if not isinstance(attempt, mode):
            raise TransactionAccessModeError(
                f"a {_mode_name(mode)} invocation cannot join the active "
                f"{_mode_name(type(attempt))} transaction (transaction-access-mode-mismatch)"
            )
        return attempt

    def _invoke[A: (TxnAttempt, ReadOnlyTxnAttempt), Tx, T](
        self,
        fn: Callable[[Tx], T],
        context_for: Callable[[A], Tx],
        attempt_for: Callable[[ModelSelection], _AttemptFactory[A]],
        *,
        root: TransactionInvocationActivity,
        capture: ExecutionCapture,
        retries: int,
        isolation: IsolationLevel,
        access_mode: AccessMode,
        extra_retriable: Callable[[BaseException], bool] | None,
    ) -> T:
        """Run one outermost invocation: the retry loop over physical attempts,
        each adopting, acquiring, and opening its boundary afresh, the whole
        contextualized once the loop has resolved."""
        execution = AdoptedExecution(self._serving)

        def invoke() -> T:
            with root as invocation:

                def attempt() -> T:
                    # Adopted before the attempt opens, so the edition its
                    # Started event carries is the one the boundary is
                    # then asked to begin under — and a retry, re-entering
                    # here, adopts whatever is serving by then.
                    selection = execution.adopt()
                    construct = attempt_for(selection)
                    with invocation.attempt(selection.edition) as physical:

                        def in_txn(conn: DatabaseConnection) -> T:
                            attempted = construct(conn, physical, TxnAttemptLifetime())
                            context = context_for(attempted)
                            active = _ActiveTransaction(attempted, context, self._root, capture)
                            return _completed(attempted, active, fn, context)

                        # One connection for this attempt and everything inside
                        # it — the boundary, the reads, the write batches, the
                        # streams — acquired after the attempt started and given
                        # back before it finishes. A retry re-enters this closure
                        # and acquires again, so nothing of a failed attempt's
                        # resource is carried into its successor; the pool may
                        # well hand back the same physical connection, which is
                        # its business rather than this loop's.
                        resource = capture.source.new_context()
                        try:
                            conn, held_since_ns = enter_connection(resource, physical)
                        except Exception as unacquired:
                            # No boundary opened and no callback ran, so this is
                            # the same terminal outcome a refused BEGIN reaches:
                            # there is nothing to undo and nothing to replay.
                            # There is also nothing left to release here — a
                            # failed entry already ran its own cleanup and
                            # reported what that established.
                            #
                            # Every ordinary failure of the acquisition takes
                            # this route, not just the adapter's own refusal: an
                            # attempt that never got a connection never opened a
                            # boundary, whatever the reason the Acquisition
                            # derived for it.
                            physical.begin_failed(unacquired)
                            raise _BeginFailure(unacquired) from unacquired
                        try:
                            settled = _attempted(
                                conn.transaction(
                                    in_txn, isolation=isolation, access_mode=access_mode
                                ),
                                physical,
                            )
                        except BaseException as failure:
                            exit_connection(resource, physical, held_since_ns, failure)
                            raise
                        exit_connection(resource, physical, held_since_ns, None)
                        return settled

                try:
                    return run_with_retry(attempt, retries=retries, extra_retriable=extra_retriable)
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


def _completed[Tx, T](
    attempt: TxnAttempt | ReadOnlyTxnAttempt,
    active: _ActiveTransaction,
    fn: Callable[[Tx], T],
    context: Tx,
) -> T:
    """Run the outermost callback with ``active`` bound for joining calls, then
    complete the attempt's work, answering the callback's value only once the
    attempt may commit.

    A callback that returned normally still refuses the commit when a failure it
    caught made the attempt rollback-only; otherwise the attempt completes its
    own work — a writable attempt's pre-commit flush — while its lifetime still
    admits work. Anything escaping withholds the value and discards what the
    attempt held. Either way every handle and stream of the attempt is fenced
    and the binding cleared before the port settles the native transaction.
    """
    lifetime = attempt.lifetime
    with _ACTIVE.bound(active):
        try:
            result = fn(context)
            lifetime.refuse_commit()
            attempt.complete()
            return result
        except BaseException:
            attempt.discard()
            raise
        finally:
            lifetime.close()


def _joined[Tx, T](
    attempt: TxnAttempt | ReadOnlyTxnAttempt, context: Tx, fn: Callable[[Tx], T]
) -> T:
    """Run an admitted joining callback on the active ``context``.

    The join returns immediately; commit, abort, and retry belong to the
    outermost attempt, whose activity the joined one is a child of. A failure
    escaping the joined callback dooms the shared lifetime, keeping the first
    cause, before it propagates, so an outer callback that catches it still
    cannot commit. Nothing is adopted and nothing is wrapped: the selection and
    the failure contract are the outer invocation's.
    """
    with attempt.joined_invocation():
        try:
            return fn(context)
        except BaseException as failure:
            attempt.lifetime.doom(failure)
            raise


def _mode_name(kind: type[TxnAttempt | ReadOnlyTxnAttempt]) -> str:
    return "read-only" if kind is ReadOnlyTxnAttempt else "writable"


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


def _resolved(
    defaults: TxnOptions,
    *,
    max_retries: int | Omitted,
    concurrency: Concurrency | Omitted,
    retry_optimistic_conflicts: bool | Omitted,
    isolation: IsolationLevel | Omitted,
) -> TxnOptions:
    """The options an outer invocation runs under: each explicit value, else
    the scope's default for that field.

    Every explicit value has already been validated, so the record built here
    re-runs the same rules over values known to pass them. The scope's own
    record is answered as itself whenever the resolved values are its own —
    every keyword omitted, or explicit values equal to the defaults — so an
    invocation that changes nothing allocates nothing.
    """
    bound = defaults.max_retries if isinstance(max_retries, Omitted) else max_retries
    preference = defaults.concurrency if isinstance(concurrency, Omitted) else concurrency
    opt_in = (
        defaults.retry_optimistic_conflicts
        if isinstance(retry_optimistic_conflicts, Omitted)
        else retry_optimistic_conflicts
    )
    level = defaults.isolation if isinstance(isolation, Omitted) else isolation
    if (
        bound == defaults.max_retries
        and preference == defaults.concurrency
        and opt_in == defaults.retry_optimistic_conflicts
        and level == defaults.isolation
    ):
        return defaults
    return TxnOptions(
        max_retries=bound,
        concurrency=preference,
        retry_optimistic_conflicts=opt_in,
        isolation=level,
    )


def _optimistic_conflict_retriable(exc: BaseException) -> bool:
    """The ``retry_optimistic_conflicts`` opt-in's own retriability verdict
    (`m-opt-lock` "Retry contract"; `m-auto-retry.md` "Which failures are
    retriable"; ADR 0008 / the Python binding) — injected into
    :func:`~parallax.core.auto_retry.run_with_retry` as its
    ``extra_retriable`` extension ONLY when the resolved option is set
    (:meth:`TransactionRunner.transact`, above).

    The retry loop already recognizes the canonical conflict; what stays
    caller policy is whether a recognized conflict is RETRIED, which is what
    this predicate answers. It covers the SAME two raise shapes
    :func:`~parallax.core.auto_retry.retriable_failure` already distinguishes
    for a transient database failure: the conflict itself, or the rollback-only
    refusal whose ``__cause__`` preserves it (the JOIN case — an inner joined
    scope's own conflict marks the root rollback-only, and the outermost retry
    loop still applies per the original failure's category). The
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
    active: TxnOptions,
    *,
    max_retries: int | Omitted,
    concurrency: Concurrency | Omitted,
    retry_optimistic_conflicts: bool | Omitted,
    isolation: IsolationLevel | Omitted,
) -> None:
    """Refuse a joining call's explicit option that conflicts with the active
    transaction's resolved record.

    Every field is compared on the same terms: an omitted keyword inherits, an
    explicit value equal to the resolved one is accepted, and an explicit
    different value is refused. The record is complete — the opening scope
    resolved every field the transaction opened with — so the comparison never
    needs a default of its own, and a partial request is never materialized as a
    record merely to be compared.
    """
    _refuse_conflict("max_retries", max_retries, active.max_retries)
    _refuse_conflict("concurrency", concurrency, active.concurrency)
    _refuse_conflict(
        "retry_optimistic_conflicts", retry_optimistic_conflicts, active.retry_optimistic_conflicts
    )
    _refuse_conflict("isolation", isolation, active.isolation)


def _refuse_conflict(name: str, explicit: object, active_value: object) -> None:
    if explicit is not OMITTED and explicit != active_value:
        raise TransactionOptionConflictError(
            f"cannot join the active transaction with {name}={explicit!r}: the transaction "
            f"was opened with {name}={active_value!r} (a joining call may not "
            "re-negotiate; omit the option to inherit)"
        )
