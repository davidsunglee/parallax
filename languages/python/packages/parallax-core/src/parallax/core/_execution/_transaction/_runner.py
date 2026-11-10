from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Final, Literal, cast

from parallax.core._execution._adoption import AdoptedExecution
from parallax.core._execution._connection_lifecycle import (
    TransactionPreparation,
    exit_connection,
)
from parallax.core._execution._options import (
    OMITTED,
    Omitted,
    ReadOnlyTxnOptions,
    TxnOptions,
)
from parallax.core._execution._publication import (
    ModelSelection,
    ServingModel,
    read_projection,
    write_projection,
)
from parallax.core._execution._routing import OperationRouting, read_only_policy
from parallax.core._execution._transaction._attempt import ReadOnlyTxnAttempt, TxnAttempt
from parallax.core._execution._transaction._lifetime import ActiveBinding, TxnAttemptLifetime
from parallax.core._execution._unit_work.clock import Clock
from parallax.core.execution_lifecycle._activity import (
    InstalledLifecycle,
    TransactionAttemptActivity,
    TransactionInvocationActivity,
    open_transaction_root,
    refuse_reentry,
)
from parallax.core.internal.auto_retry import (
    RetryPolicy,
    _RetryCandidate,  # pyright: ignore[reportPrivateUsage] - only the runner hands the loop a candidate
    retry_eligible,
    retry_policy,
    run_with_retry,
)
from parallax.core.internal.base import ParallaxError, UsageError
from parallax.core.internal.concurrency import ConcurrencyPreference, concurrency_preference
from parallax.core.internal.db_port import (
    AccessMode,
    BeginFailed,
    Committed,
    DatabaseConnection,
    IsolationLevel,
    RollbackFailed,
    RolledBack,
    Route,
    RouteCapabilities,
    RoutePolicy,
    isolation_level,
)
from parallax.core.internal.execution_authority._authority import ExecutionAuthority, same_authority
from parallax.core.internal.read_delivery._read_plan import ReadPlanner

__all__ = [
    "TRANSACTION_ACCESS_MODE_MISMATCH",
    "TRANSACTION_AUTHORITY_MISMATCH",
    "TRANSACTION_OPTION_CONFLICT",
    "TRANSACTION_OWNER_MISMATCH",
    "TransactionJoinCode",
    "TransactionRollbackError",
    "TransactionRunner",
]

type TransactionJoinCode = Literal[
    "transaction-owner-mismatch",
    "transaction-authority-mismatch",
    "transaction-access-mode-mismatch",
    "transaction-option-conflict",
]
"""Why a nested invocation was refused the active transaction, in the order it
is judged.

The active transaction records the shared resource identity behind the Database
Root that opened it: scopes derived from that root or any root alias join, and
a scope from every other root is refused even when it carries an equivalent
configuration. A joining scope must then carry the same execution authority and
select the active transaction's access mode, because joining reuses the native
transaction the attempt opened in its mode. Last, an explicit option whose value
differs from the active transaction's resolved one is refused; an equal value
and an omitted option are accepted. Every refusal precedes the joined callback,
Unit of Work mutation, SQL, and adapter access, and retains neither scope.
"""

TRANSACTION_OWNER_MISMATCH: Final = "transaction-owner-mismatch"
TRANSACTION_AUTHORITY_MISMATCH: Final = "transaction-authority-mismatch"
TRANSACTION_ACCESS_MODE_MISMATCH: Final = "transaction-access-mode-mismatch"
TRANSACTION_OPTION_CONFLICT: Final = "transaction-option-conflict"


class TransactionRollbackError(ParallaxError):
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
            "transaction-rollback-failed",
            f"the transaction could not be rolled back after {triggering_error!r}; "
            f"the rollback failed with {rollback_error!r}, so what it left behind is unknown",
        )
        self.triggering_error = triggering_error
        self.rollback_error = rollback_error


@dataclass(frozen=True, slots=True)
class _ActiveTransaction:
    """What the outermost attempt binds for joining invocations.

    A joining call needs the ``context`` the outer attempt's callback was
    handed, the shared resource ``root`` that opened it so ownership can be
    settled first, the ``authority`` that fixes execution authority, and the
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
    authority: ExecutionAuthority


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
    The calling scope supplies its authority, defaults, and read policy. Neither the selection,
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
        authority: ExecutionAuthority,
        defaults: TxnOptions,
        retry: RetryPolicy | Omitted,
        concurrency: ConcurrencyPreference | Omitted,
        isolation: IsolationLevel | Omitted,
    ) -> T:
        """Run ``fn`` in a writable transaction under ``authority``, returning its
        value after commit.

        The public contract is the lifecycle scope's ``transact``. What is
        decided here: the deterministic refusals run first and carry no edition
        note, the join path returns inside the active attempt without adopting
        or noting, and an outer invocation resolves its options once, opens its
        root, runs the retry loop with one adoption per attempt, and notes its
        edition on a failure once the loop has resolved.

        Each attempt is constructed fully wired before ``context_for``
        receives it, and ``fn`` is handed what that factory answered. A retry
        constructs a fresh attempt and asks the factory again; a join reuses the
        active context and asks nothing. Every attempt of an outer invocation
        requests the writer, whatever the calling scope's read policy.
        """
        refuse_reentry(self._lifecycle)
        # Every explicit value is validated ahead of the join comparison below,
        # because a value outside its field's contract is the CALL's own defect:
        # comparing it first would report a nonsense value as a disagreement
        # with the active transaction, which reads as though naming it
        # correctly would have been accepted. An omitted keyword is left as the
        # marker until it is resolved — against the scope for an outer
        # invocation, against the active transaction for a join.
        requested_retry = retry if isinstance(retry, Omitted) else retry_policy(retry)
        preference = (
            concurrency if isinstance(concurrency, Omitted) else concurrency_preference(concurrency)
        )
        level = isolation if isinstance(isolation, Omitted) else isolation_level(isolation)
        active = _ACTIVE.active()
        if active is not None:
            joined = self._admitted(active, authority, TxnAttempt)
            _check_join_options(
                joined.options, retry=requested_retry, concurrency=preference, isolation=level
            )
            return _joined(joined, cast("Tx", active.context), fn)
        options = _resolved_options(
            defaults, retry=requested_retry, concurrency=preference, isolation=level
        )
        # The Root Execution opens after the deterministic refusals above and
        # spans every physical attempt below, and it opens BEFORE anything is
        # adopted: a Provider that fails to open keeps its own type, because no
        # edition has been taken that a failure could be reported under.
        root = open_transaction_root(
            self._lifecycle,
            access_mode="read_write",
            concurrency=options.concurrency,
            retry=options.retry,
            isolation=options.isolation,
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
                actor=authority.actor,
                lifetime=lifetime,
            )

        return self._invoke(
            fn,
            context_for,
            attempt_for,
            root=root,
            authority=authority,
            routing=OperationRouting(authority.source, "writer_only"),
            retry=options.retry,
            isolation=options.isolation,
            access_mode="read_write",
        )

    def read_only[Tx, T](
        self,
        fn: Callable[[Tx], T],
        context_for: Callable[[ReadOnlyTxnAttempt], Tx],
        *,
        authority: ExecutionAuthority,
        defaults: TxnOptions,
        read_policy: RoutePolicy,
        routes: Mapping[Route, RouteCapabilities],
        retry: RetryPolicy | Omitted,
        isolation: IsolationLevel | Omitted,
    ) -> T:
        """Run ``fn`` in a read-only transaction under ``authority``, returning
        its value after commit.

        :meth:`transact`'s path with a read-only attempt: the same refusals and
        join admission, a :class:`ReadOnlyTxnOptions` record resolved from the
        Retry Policy and isolation alone, and a boundary every attempt asks the
        port to open read-only. An outer invocation's attempts request
        ``read_policy``, refused before anything is observed or acquired where
        its route declares no read-only transaction at the resolved isolation;
        a join never consults it.
        """
        refuse_reentry(self._lifecycle)
        requested_retry = retry if isinstance(retry, Omitted) else retry_policy(retry)
        level = isolation if isinstance(isolation, Omitted) else isolation_level(isolation)
        active = _ACTIVE.active()
        if active is not None:
            joined = self._admitted(active, authority, ReadOnlyTxnAttempt)
            _refuse_conflict("retry", requested_retry, joined.options.retry)
            _refuse_conflict("isolation", level, joined.options.isolation)
            return _joined(joined, cast("Tx", active.context), fn)
        options = ReadOnlyTxnOptions(
            retry=defaults.retry if isinstance(requested_retry, Omitted) else requested_retry,
            isolation=defaults.isolation if isinstance(level, Omitted) else level,
        )
        policy = read_only_policy(read_policy, options.isolation, routes)
        root = open_transaction_root(
            self._lifecycle,
            access_mode="read_only",
            concurrency=None,
            retry=options.retry,
            isolation=options.isolation,
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
            authority=authority,
            routing=OperationRouting(authority.source, policy),
            retry=options.retry,
            isolation=options.isolation,
            access_mode="read_only",
        )

    def _admitted[A: (TxnAttempt, ReadOnlyTxnAttempt)](
        self, active: _ActiveTransaction, authority: ExecutionAuthority, mode: type[A]
    ) -> A:
        """The active attempt, once a joining invocation of ``mode`` is admitted
        to it, in this order: a transaction this resource root opened, not
        rollback-only, under the same execution authority, and in the joining
        entrypoint's access mode. Explicit options are the caller's to compare
        next."""
        if active.root is not self._root:
            raise UsageError(
                TRANSACTION_OWNER_MISMATCH,
                "this scope does not belong to the runtime that opened the active transaction",
            )
        attempt = active.attempt
        attempt.lifetime.refuse_join()
        if not same_authority(active.authority, authority):
            raise UsageError(
                TRANSACTION_AUTHORITY_MISMATCH,
                "the joining scope carries different execution authority",
            )
        if not isinstance(attempt, mode):
            raise UsageError(
                TRANSACTION_ACCESS_MODE_MISMATCH,
                f"a {_mode_name(mode)} invocation cannot join the active "
                f"{_mode_name(type(attempt))} transaction",
            )
        return attempt

    def _invoke[A: (TxnAttempt, ReadOnlyTxnAttempt), Tx, T](
        self,
        fn: Callable[[Tx], T],
        context_for: Callable[[A], Tx],
        attempt_for: Callable[[ModelSelection], _AttemptFactory[A]],
        *,
        root: TransactionInvocationActivity,
        authority: ExecutionAuthority,
        routing: OperationRouting,
        retry: RetryPolicy,
        isolation: IsolationLevel,
        access_mode: AccessMode,
    ) -> T:
        """Run one outermost invocation: the retry loop over physical attempts,
        each adopting, acquiring through ``routing``, and opening its boundary
        afresh, the whole noted with its edition once the loop has resolved."""
        execution = AdoptedExecution(self._serving)

        def invoke() -> T:
            with root as invocation:

                def physical_attempt(replayable: list[Exception]) -> T:
                    # Adopted before the attempt opens, so the edition its
                    # Started event carries is the one the boundary is
                    # then asked to begin under — and a retry, re-entering
                    # here, adopts whatever is serving by then.
                    selection = execution.adopt()
                    construct = attempt_for(selection)
                    with invocation.attempt(selection.edition) as physical:
                        lifetime = TxnAttemptLifetime()
                        # One connection for this attempt and everything inside
                        # it — the boundary, the reads, the flushes, the
                        # streams — acquired after the attempt started and given
                        # back before it finishes. A retry re-enters this closure
                        # and acquires again, so nothing of a failed attempt's
                        # resource is carried into its successor; the pool may
                        # well hand back the same physical connection, which is
                        # its business rather than this loop's.
                        resource = routing.new_context()
                        preparation = TransactionPreparation(resource, physical, routing)

                        def in_txn(conn: DatabaseConnection) -> T:
                            # The boundary has opened, so the route the lease
                            # ended on is final before anything of the attempt
                            # exists or its callback runs.
                            preparation.granted()
                            attempted = construct(conn, physical, lifetime)
                            context = context_for(attempted)
                            active = _ActiveTransaction(attempted, context, self._root, authority)
                            return _completed(attempted, active, fn, context)

                        try:
                            conn = preparation.enter()
                        except BaseException as unacquired:
                            # No boundary opened and no callback ran, so this is
                            # the same terminal outcome a refused BEGIN reaches:
                            # there is nothing to undo and nothing to replay.
                            # There is also nothing left to release here — a
                            # failed entry already ran its own cleanup and
                            # reported what that established.
                            #
                            # Every failure of the acquisition takes this
                            # route, not just the adapter's own refusal — an
                            # interrupt included: an attempt that never got a
                            # connection never opened a boundary, whatever the
                            # reason the Acquisition derived for it.
                            physical.begin_failed(unacquired)
                            raise
                        try:
                            settled = _attempted(
                                _opened(
                                    conn,
                                    in_txn,
                                    preparation,
                                    physical,
                                    isolation=isolation,
                                    access_mode=access_mode,
                                ),
                                physical,
                                replayable,
                                lifetime.recognized_conflicts,
                            )
                        except BaseException as failure:
                            if preparation.releasable:
                                exit_connection(
                                    resource, physical, preparation.held_since_ns, failure
                                )
                            raise
                        exit_connection(resource, physical, preparation.held_since_ns, None)
                        return settled

                def attempt() -> T:
                    replayable: list[Exception] = []
                    try:
                        return physical_attempt(replayable)
                    except Exception as failure:
                        # Carried only here, so release and reporting ran with the
                        # original failure live and chained nothing to a carrier;
                        # whatever a cleanup step raised instead ends the
                        # invocation.
                        if not (replayable and replayable[0] is failure):
                            raise
                        raise _RetryCandidate(failure) from None

                # The loop handles only what an attempt handed it as a retry
                # candidate; every other failure, a refused begin included,
                # passes straight through it as the caller's own error.
                return run_with_retry(attempt, policy=retry)

        # Noted around the whole invocation and outside the root scope: the
        # classifier saw every failure before this transaction's edition note,
        # the lifecycle reported it under the attempt it came from, and the note
        # names the edition of the attempt that failed last, after any
        # exhaustion note.
        return execution.noting_edition("transaction", invoke)


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
    cannot commit. Nothing is adopted and nothing is noted: the selection and
    the edition note are the outer invocation's.
    """
    with attempt.joined_invocation():
        try:
            return fn(context)
        except BaseException as failure:
            attempt.lifetime.doom(failure)
            raise


def _mode_name(kind: type[TxnAttempt | ReadOnlyTxnAttempt]) -> str:
    return "read-only" if kind is ReadOnlyTxnAttempt else "writable"


def _opened[T](
    conn: DatabaseConnection,
    body: Callable[[DatabaseConnection], T],
    preparation: TransactionPreparation,
    attempt: TransactionAttemptActivity,
    *,
    isolation: IsolationLevel,
    access_mode: AccessMode,
) -> Committed[T] | RolledBack | RollbackFailed:
    """The outcome of the attempt's boundary over ``conn``, once it opened.

    A boundary that never opened — refused, or interrupted by whatever escaped
    before ``body`` ran — leaves the acquisition unprepared: it is settled as
    failed by that, cleaning the lease up as its own, and the attempt finishes
    begin-failed by the same failure, so no Release follows it.
    """
    try:
        outcome = conn.transaction(body, isolation=isolation, access_mode=access_mode)
    except BaseException as failure:
        if preparation.pending:
            _begin_failed(preparation, attempt, failure)
        raise
    if isinstance(outcome, BeginFailed):
        error = outcome.error
        _begin_failed(preparation, attempt, error)
        raise error
    return outcome


def _begin_failed(
    preparation: TransactionPreparation,
    attempt: TransactionAttemptActivity,
    failure: BaseException,
) -> None:
    """Settle a boundary that never opened, however its cleanup ends: the
    attempt is begin-failed by ``failure`` even where the cleanup was cut short."""
    try:
        preparation.unprepared(failure)
    finally:
        attempt.begin_failed(failure)


def _attempted[T](
    outcome: Committed[T] | RolledBack | RollbackFailed,
    attempt: TransactionAttemptActivity,
    replayable: list[Exception],
    recognized: Collection[BaseException],
) -> T:
    """What one physical attempt whose boundary opened answers, from the outcome
    the port reported.

    The port reports what happened; this decides what a caller sees, which is the
    only place the two can be reconciled — the port cannot know that a rollback
    failure must never be retried while a rolled-back deadlock must be, and the
    retry loop cannot know which phase failed.

    A completed rollback is the one outcome classified for replay, once, beside
    the statement failures the attempt's execution ``recognized`` as recoverable
    conflicts: the attempt reports that verdict, and an eligible failure is recorded in
    ``replayable`` before it propagates, unchanged like any other, so the
    attempt's cleanup sees it and what a caller catches is what their own
    callback or the database raised. Only a failed rollback substitutes an error
    of its own, because then neither live error tells the whole story; it still
    reports the verdict on its trigger, and is never replayed.

    It is also where the attempt activity learns its outcome, for the same
    reason: the port's report is the only account of what the boundary did. A
    boundary that never opened is settled before this, as the acquisition it
    left unprepared: the attempt finishes begin-failed, terminal however
    retriable the error's own category is.
    """
    match outcome:
        case Committed(value):
            attempt.committed()
            return value
        case RolledBack(trigger):
            error = trigger.error
            eligible = retry_eligible(error, recognized=recognized)
            attempt.rolled_back(trigger, eligible)
            if eligible and isinstance(error, Exception):
                replayable.append(error)
            raise error
        case RollbackFailed(trigger, rollback_error):
            attempt.rollback_failed(
                trigger, rollback_error, retry_eligible(trigger.error, recognized=recognized)
            )
            triggering_error = trigger.error
            if isinstance(triggering_error, Exception):
                raise TransactionRollbackError(triggering_error, rollback_error) from rollback_error
            # A control-flow or fatal trigger stays primary: an interrupt or a
            # cancellation is not an ordinary failure to be wrapped in one.
            raise triggering_error from rollback_error


def _resolved_options(
    defaults: TxnOptions,
    *,
    retry: RetryPolicy | Omitted,
    concurrency: ConcurrencyPreference | Omitted,
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
    policy = defaults.retry if isinstance(retry, Omitted) else retry
    preference = defaults.concurrency if isinstance(concurrency, Omitted) else concurrency
    level = defaults.isolation if isinstance(isolation, Omitted) else isolation
    if (
        policy == defaults.retry
        and preference == defaults.concurrency
        and level == defaults.isolation
    ):
        return defaults
    return TxnOptions(retry=policy, concurrency=preference, isolation=level)


def _check_join_options(
    active: TxnOptions,
    *,
    retry: RetryPolicy | Omitted,
    concurrency: ConcurrencyPreference | Omitted,
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
    _refuse_conflict("retry", retry, active.retry)
    _refuse_conflict("concurrency", concurrency, active.concurrency)
    _refuse_conflict("isolation", isolation, active.isolation)


def _refuse_conflict(name: str, explicit: object, active_value: object) -> None:
    if explicit is not OMITTED and explicit != active_value:
        raise UsageError(
            TRANSACTION_OPTION_CONFLICT,
            f"cannot join the active transaction with {name}={explicit!r}: the transaction "
            f"was opened with {name}={active_value!r} (a joining call may not "
            "re-negotiate; omit the option to inherit)",
        )
