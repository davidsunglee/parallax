from __future__ import annotations

import sys
from collections.abc import Callable
from time import monotonic
from types import TracebackType
from typing import TYPE_CHECKING, Final

from parallax.core.internal.db_port import (
    CheckoutFailed,
    CheckoutReason,
    CleanupCode,
    CleanupIssue,
    CleanupPhase,
    CleanupResult,
    ConnectionAcquisitionError,
    ConnectionPool,
    DatabaseConnection,
    DialReason,
    ExecutionAccess,
    FallbackReason,
    Invalidated,
    NativeDriver,
    NativeOperation,
    NotIdle,
    ProbeMismatch,
    ReleaseUnconfirmed,
    Returned,
    RouteSelection,
    SubmissionProgress,
    displaced_control_flow,
)
from parallax.core.internal.db_port._runtime._route_plan import RoutePlan
from parallax.core.internal.diagnostics import diagnostic_for

if TYPE_CHECKING:
    from parallax.core.internal.db_port._runtime._dial_record import DialLedger
    from parallax.core.internal.db_port._runtime._pooled_route import PooledRoute

__all__ = ["OUTAGE_REASONS", "PooledConnectionContext", "Step", "check_out_within", "release"]

OUTAGE_REASONS: Final = frozenset({"unavailable", "timeout"})
"""The acquisition refusals that say only that no usable connection was
obtained in time: none was reached, one was lost before it could serve, or one
arrived after the budget. Every other refusal names something more specific
than an outage: a refused credential, login, or session, a full queue, or a
closed runtime."""

type Admit = Callable[[float], None]
"""The runtime's atomic admission check, raising when work may not proceed.

It takes the acquisition deadline, so expiry and closure are decided together in
one critical section rather than as two questions whose answers can change
between them.
"""

_ENTER_ONCE = "a database connection context is entered exactly once"
_SPENT = "this database connection context has already been used"
_LOST = (
    "this database connection was lost and could not be replaced, so this scope executes "
    "nothing further; acquire another one through the Database that owns the runtime"
)


class _Condition(Exception):
    """A cleanup condition that no exception reported, stated as one.

    A cleanup issue carries a diagnostic, and an observation — a connection that
    is simply not idle — has no exception behind it. Raising one nowhere and
    projecting it here keeps every issue the same shape without ever putting
    native text into a condition Parallax itself decided.
    """


def _issue(phase: CleanupPhase, code: CleanupCode, exc: BaseException) -> CleanupIssue:
    return CleanupIssue(phase=phase, code=code, diagnostic=diagnostic_for(exc))


def check_out_within[C](route: PooledRoute[C], deadline: float) -> C:
    """Take a connection out of ``route``'s pool within ``deadline``, or raise.

    The remaining budget is what the pool's checkout is given, so its wait
    spends the caller's time rather than an additional allowance. It is one
    fair wait: the pool queues the caller once, and nothing here polls it
    again. Checkout failures map to the checkout-reachable acquisition reasons
    and keep their native cause; authorization setup is classified later,
    after checkout.

    When the budget expires, report the latest dial failure still on record
    or ``timeout`` if the record is empty. A pool that dials on this thread
    reports its dial failure directly. A successful checkout clears the record.
    """
    dial_ledger = route.dial_ledger
    remaining = deadline - monotonic()
    if remaining <= 0.0:
        raise _expired(dial_ledger, None)
    try:
        connection = route.pool.check_out(remaining)
    except CheckoutFailed as failed:
        if failed.reason == "timeout":
            raise _expired(dial_ledger, failed.__cause__)  # noqa: B904 - the cause is chosen above
        raise ConnectionAcquisitionError(
            _CHECKOUT_FAILURES[failed.reason], reason=failed.reason
        ) from failed.__cause__
    dial_ledger.clear_on_handover()
    return connection


_CHECKOUT_FAILURES: Final[dict[CheckoutReason, str]] = {
    "timeout": "no database connection became available within the acquisition timeout",
    "queue_rejected": "the database runtime already has as many callers waiting as it admits",
    "closed": "this Database is closed, so it opens no new database connection",
    "unavailable": (
        "a database connection could not be established: its server could not be reached or is not "
        "accepting connections"
    ),
    "authentication_refused": (
        "a database connection was refused by its server once its login was offered"
    ),
    "credentials_refused": "a database connection could not be authenticated",
    "preparation_failed": "a database connection could not be established or prepared",
}

_EXPIRED_FAILURES: Final[dict[DialReason, str]] = {
    "unavailable": (
        "no database connection became available within the acquisition timeout; the last "
        "connection this route tried to open could not reach its server, or the server was not "
        "accepting connections"
    ),
    "authentication_refused": (
        "no database connection became available within the acquisition timeout; the last "
        "connection this route opened was refused by its server once its login was offered"
    ),
    "credentials_refused": (
        "no database connection could be authenticated within the acquisition timeout"
    ),
    "preparation_failed": (
        "no database connection became usable within the acquisition timeout; the last "
        "connection this route opened was refused as unusable"
    ),
}


def _expired(dial_ledger: DialLedger, native: BaseException | None) -> ConnectionAcquisitionError:
    failure = dial_ledger.latest_failure
    if failure is None:
        timed_out = ConnectionAcquisitionError(_CHECKOUT_FAILURES["timeout"], reason="timeout")
        timed_out.__cause__ = native
        return timed_out
    explained = ConnectionAcquisitionError(_EXPIRED_FAILURES[failure.reason], reason=failure.reason)
    explained.__cause__ = failure.cause
    return explained


_LATE_REPLACEMENT = (
    "the replacement database connection arrived after the acquisition's timeout, so nothing "
    "was submitted on it again"
)
_LOST_UNVERIFIED = (
    "the connection handed over while its route's readiness was pending was lost before it "
    "could be verified"
)
_UNVERIFIED = (
    "the connection handed over while its route's readiness was pending could not be verified"
)


def _refused(refusal: ProbeMismatch) -> ConnectionAcquisitionError:
    """The failure every acquisition on a refused route reports, chained to why."""
    refused = ConnectionAcquisitionError(
        "this route was refused when one of its connections was verified, so it serves nothing",
        reason="preparation_failed",
    )
    refused.__cause__ = refusal
    return refused


def release[C, A](
    driver: NativeDriver[C, A],
    pool: ConnectionPool[C],
    connection: C,
    *,
    suspect: bool,
    restore_authorization: bool = False,
) -> CleanupResult:
    """End this connection's exclusive use, and report what that established.

    The sequence is finite — inspect, restore scoped authorization where reuse
    remains possible, dispose where either step or the execution says reuse
    cannot be established, then hand back exactly once — checked in where it is
    reusable, discarded where it was disposed of — so the issues it can report
    are bounded by the steps rather than accumulated as history.

    Three refusals are deliberate. A failed physical close does NOT fall back to
    returning a connection that is still suspect, because balancing the
    accounting is not worth offering the next caller a session nothing can
    vouch for. A failed handoff is not retried and is not followed by a close,
    because a hand-back that raised may still have handed the connection to
    another caller. And a completed handoff is never inspected afterwards, for
    the same reason.
    """
    issues: list[CleanupIssue] = []
    dispose = suspect
    if suspect:
        issues.append(_issue("inspect", "suspect", _Condition("the execution marked it suspect")))
    else:
        reading = driver.read_idle(connection)
        if reading == "unreadable":
            dispose = True
            issues.append(
                _issue("inspect", "state-unreadable", _Condition("its state could not be read"))
            )
        elif isinstance(reading, NotIdle):
            dispose = True
            issues.append(
                _issue("inspect", "not-idle", _Condition(f"its state was {reading.state}"))
            )

    if not dispose and restore_authorization:
        try:
            driver.restore_authorization(connection)
        except Exception as exc:
            dispose = True
            issues.append(_issue("restore", "authorization-restore-failed", exc))

    if dispose:
        try:
            driver.close_connection(connection)
        except Exception as exc:
            issues.append(_issue("dispose", "close-failed", exc))
            return ReleaseUnconfirmed(tuple(issues))
    try:
        if dispose:
            pool.discard(connection)
        else:
            pool.check_in(connection)
    except Exception as exc:
        issues.append(_issue("return", "handoff-failed", exc))
        return ReleaseUnconfirmed(tuple(issues))
    return Invalidated(tuple(issues)) if dispose else Returned(tuple(issues))


type Step[C] = tuple["PooledRoute[C]", float]
"""One route an acquisition may be served on, and the absolute deadline by
which that route must have served it."""


class _FellBack(Exception):
    """Entry left the current step for the next one, which it now establishes."""


class PooledConnectionContext[C, A]:
    """One single-use acquisition of a connection, served on the first route of
    its plan that can serve it, and the lease its execution borrows that
    connection through.

    Creating it takes nothing. Entering it checks out, verifies the connection
    is idle, checks admission against the step's deadline, proves the
    connection where its route's readiness is still pending, installs any
    bound authorization, bounds statement time where the lease carries a
    statement deadline, rechecks admission after that provider work, and yields
    fresh execution access. Leaving it revokes that access and releases the
    connection once, restoring an installed authorization only where the
    session remains reusable.

    Entry is permitted once and once only, including after an entry that failed:
    a failed entry has already run cleanup over whatever it took and left what
    that established on :attr:`cleanup_result`, so a second attempt would be a
    second acquisition wearing the first one's identity.

    The context is the only holder of the physical connection for the whole
    lease: execution borrows the current one for each operation. That is what
    lets the lease's actual first submission — a pending route's proof, its
    authorization, an outer ``BEGIN``, or a read or batch of reads its
    caller designated — run once more if it meets a broken session: the
    connection is disposed of and handed back, another is taken within the
    step's deadline, and the same prepared submission is made on it, all
    inside this one acquisition. Any other submission, the second attempt
    itself, and a write never are. Once no connection can be kept, the slot
    holds the cleanup that ended it instead, and that is what leaving reports.

    A plan with a later step is a preferred one. Its earlier step spends at
    most its own share of the budget and gives way to the next only for a
    route that is unavailable or a connection lost while it was still
    being set up. A loss of that kind is the same one
    opportunity a first submission has, spent moving to the next route instead
    of retrying on this one, and only where the submission is setup: a proof,
    an authorization, or an outer ``BEGIN``. A designated read is modeled
    work, so its one replacement stays on the route that began serving it.
    Whatever the plan, entry reports the route it ended on as its selection,
    and how it got there, a failed entry's refusal included.
    """

    __slots__ = (
        "_admit",
        "_authorization",
        "_authorized",
        "_cleanup_result",
        "_driver",
        "_entering",
        "_execution",
        "_expected_login",
        "_first_send_available",
        "_opening",
        "_replacement_refusal",
        "_resource",
        "_route",
        "_selection",
        "_statement_deadline",
        "_step",
        "_step_deadline",
        "_steps",
        "_suspect",
        "_used",
    )

    def __init__(
        self,
        steps: tuple[Step[C], ...],
        admit: Admit,
        driver: NativeDriver[C, A],
        authorization: A | None,
        *,
        expected_login: str | None,
        statement_deadline: float | None = None,
    ) -> None:
        route, step_deadline = steps[0]
        self._steps = steps
        self._step = 0
        self._route = route
        self._step_deadline = step_deadline
        self._selection = RouteSelection(route.route)
        self._admit = admit
        self._driver = driver
        self._authorization = authorization
        self._expected_login = expected_login
        self._statement_deadline = statement_deadline
        self._used = False
        self._entering = False
        self._opening = False
        self._authorized = False
        self._suspect = False
        self._first_send_available = True
        self._replacement_refusal: ConnectionAcquisitionError | None = None
        self._resource: C | CleanupResult | None = None
        self._execution: ExecutionAccess | None = None
        self._cleanup_result: CleanupResult | None = None

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return self._cleanup_result

    @property
    def selection(self) -> RouteSelection | None:
        return self._selection if self._used else None

    @property
    def replacement_refusal(self) -> ConnectionAcquisitionError | None:
        """Why the replacement for a broken session was not taken, where its
        checkout refused one, as classified when it refused."""
        return self._replacement_refusal

    def __enter__(self) -> DatabaseConnection:
        if self._used:
            raise RuntimeError(_ENTER_ONCE if self._execution is not None else _SPENT)
        self._used = True
        try:
            return self._entered()
        except ConnectionAcquisitionError as refused:
            refused.selection = self._selection
            raise

    def _entered(self) -> DatabaseConnection:
        self._entering = True
        try:
            while True:
                try:
                    self._take()
                except _FellBack:
                    continue
                break
        finally:
            self._entering = False
        self._opening = True
        execution = self._driver.open_execution(self)
        self._execution = execution
        return execution

    def _take(self) -> None:
        """Establish this lease on the current step's route, or raise.

        A step a later one follows does not wait on a route already known to
        be unavailable unless it holds that route's one probe slot. The holder
        tries the route within the step's share, and everyone else moves on at
        once. The slot is given back however this step ends.
        """
        route = self._route
        refusal = route.refusal
        if refusal is not None:
            raise _refused(refusal)
        probing = False
        if self._step + 1 < len(self._steps) and route.known_unreachable():
            if not route.claim_probe():
                self._fall_back("unavailable")
            probing = True
        try:
            self._check_out(route)
            # Readiness is read again once the wait is over, because another
            # lease's proof may have refused the route during it.
            if route.awaiting_verification:
                self._verify(route)
            else:
                self._require_unrefused(route)
            self._authorize()
            self._limit_statement_time()
        finally:
            if probing:
                route.release_probe()

    def _require_unrefused(self, route: PooledRoute[C]) -> None:
        refusal = route.refusal
        if refusal is not None:
            self._cleanup_result = self._settled(suspect=False)
            raise _refused(refusal)

    def _fall_back(self, reason: FallbackReason) -> None:
        """Move to the next step, which entry then establishes from the start."""
        self._advance(reason)
        raise _FellBack

    def _advance(self, reason: FallbackReason) -> None:
        route, step_deadline = self._steps[self._step + 1]
        self._step += 1
        self._route = route
        self._step_deadline = step_deadline
        self._selection = RouteSelection(route.route, reason)

    def _check_out(self, route: PooledRoute[C]) -> None:
        try:
            self._resource = check_out_within(route, self._step_deadline)
        except ConnectionAcquisitionError as refused:
            fallback = RoutePlan.falls_back_on(refused.reason)
            if fallback is not None and self._step + 1 < len(self._steps):
                self._fall_back(fallback)
            # A step that fell back here first already disposed of what it
            # held; that disposal is what this acquisition's cleanup established.
            self._cleanup_result = self._settled(suspect=False)
            raise
        try:
            self._require_idle(self.current_connection())
            self._admit(self._step_deadline)
        except BaseException:
            # Nothing modeled has run, so what was taken is given back through
            # the same path a completed scope uses: an idle connection returns
            # and a non-idle one is disposed of, without either decision being
            # made twice.
            self._cleanup_result = self._settled(suspect=False)
            raise

    def _authorize(self) -> None:
        authorization = self._authorization
        if authorization is None:
            return
        try:
            self.run(
                self._driver.install_authorization, authorization, replay_safe=True, setup=True
            )
        except _FellBack:
            raise
        except ConnectionAcquisitionError:
            self._cleanup_result = self._settled(suspect=True)
            raise
        except BaseException as exc:
            self._cleanup_result = self._settled(suspect=True)
            if not isinstance(exc, Exception):
                raise
            raise ConnectionAcquisitionError(
                "the requested database principal could not be installed",
                reason="authorization_failed",
            ) from exc
        self._authorized = True
        try:
            self._admit(self._step_deadline)
        except BaseException:
            self._cleanup_result = self._settled(suspect=False, restore_authorization=True)
            self._authorized = False
            raise

    def _limit_statement_time(self) -> None:
        """Bound the session's statement time by what remains of the statement
        deadline, so a statement stalled on a live server — on a lock
        included — fails within it.

        Setup rather than a modeled statement, like the authorization. Only
        the reservation pool's single-route leases carry a statement deadline,
        so a lost session is replaced on that route rather than another, and
        every one of them installs its own, so the setting never outlives its
        purpose on a session another lease reuses.
        """
        deadline = self._statement_deadline
        if deadline is None:
            return
        try:
            self.run(
                self._driver.limit_statement_time,
                deadline - monotonic(),
                replay_safe=True,
                setup=True,
            )
        except ConnectionAcquisitionError:
            self._cleanup_result = self._settled(suspect=True)
            raise
        except BaseException as exc:
            self._cleanup_result = self._settled(suspect=True)
            if not isinstance(exc, Exception):
                raise
            raise ConnectionAcquisitionError(
                "the reservation's statement timeout could not be installed",
                reason="preparation_failed",
            ) from exc
        try:
            self._admit(self._step_deadline)
        except BaseException:
            self._cleanup_result = self._settled(
                suspect=False, restore_authorization=self._authorized
            )
            raise

    def _verify(self, route: PooledRoute[C]) -> None:
        """Prove this lease's connection before anything else runs on it.

        The proof is the lease's first submission, so a broken session met by
        it is replaced once like any other first send — and the replacement,
        acquired while the route is still pending, is proved by that same
        resubmission. Under a preferred plan that one opportunity moves the
        lease to the next route instead, which needs no proof of this one.
        Submitting it spends the opportunity, whatever the reading then turns
        out to say, so nothing after it earns another.

        A positive mismatch refuses the route; any other failure fails only
        this acquisition. A proof that succeeded still admits nothing on a
        route another lease refused in the meantime.
        """
        try:
            self.run(
                self._driver.prove_readiness, self._expected_login, replay_safe=True, setup=True
            )
        except _FellBack:
            raise
        except ProbeMismatch as mismatch:
            # Recorded before the cleanup, which an interrupt can cut short.
            try:
                route.mark_refused(mismatch)
            finally:
                self._cleanup_result = self._settled(suspect=True)
            raise _refused(mismatch)  # noqa: B904 - chained to the mismatch inside
        except ConnectionAcquisitionError:
            self._cleanup_result = self._settled(suspect=True)
            raise
        except BaseException as exc:
            self._cleanup_result = self._settled(suspect=True)
            if not isinstance(exc, Exception):
                raise
            lost = self._driver.is_session_lost(exc)
            raise ConnectionAcquisitionError(
                _LOST_UNVERIFIED if lost else _UNVERIFIED,
                reason="unavailable" if lost else "preparation_failed",
            ) from exc
        refusal = route.mark_verified()
        if refusal is not None:
            self._cleanup_result = self._settled(suspect=False)
            raise _refused(refusal)
        try:
            self._admit(self._step_deadline)
        except BaseException:
            self._cleanup_result = self._settled(suspect=False)
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        del exc_type, exc, traceback
        execution = self._execution
        if execution is None:
            return
        # Revoked before anything else, so the caller's own reference cannot
        # reach a connection this is about to hand to somebody else.
        #
        # Release is what the exit exists for, so it runs even if
        # revocation does not complete: this is the only path back to the pool,
        # and clearing the references first would make a second exit a silent
        # no-op over a connection nothing ever gave back. A revocation that did
        # not complete leaves a scope that may still reach the connection, so
        # what is given back is treated as suspect and disposed of.
        unsafe = True
        try:
            unsafe = execution.revoke()
        finally:
            self._execution = None
            self._cleanup_result = self._settled(
                suspect=self._suspect or unsafe, restore_authorization=self._authorized
            )
            self._authorized = False

    def _settled(
        self, *, suspect: bool, restore_authorization: bool = False
    ) -> CleanupResult | None:
        """End ownership of whatever the slot holds and answer what that established.

        A connection still held is released once; a slot already holding the
        cleanup that ended its connection answers that result without another
        close or handoff. The slot is emptied BEFORE a release begins, so a
        release that does not return — a fatal exception inside it — leaves
        nothing a later exit could release a second time.
        """
        resource = self._resource
        self._resource = None
        if resource is None or isinstance(resource, Returned | Invalidated | ReleaseUnconfirmed):
            return resource
        return release(
            self._driver,
            self._route.pool,
            resource,
            suspect=suspect,
            restore_authorization=restore_authorization,
        )

    def current_connection(self) -> C:
        resource = self._resource
        if resource is None or isinstance(resource, Returned | Invalidated | ReleaseUnconfirmed):
            raise RuntimeError(_LOST)
        return resource

    @property
    def suspect(self) -> bool:
        return self._suspect

    def mark_suspect(self) -> None:
        self._suspect = True

    def run[T, *P](
        self,
        operation: NativeOperation[C, T, *P],
        /,
        *prepared: *P,
        replay_safe: bool,
        setup: bool = False,
    ) -> T:
        """Run ``operation`` on the current connection, replacing that connection
        once if this was the lease's first submission and it met a broken session.

        Replacement needs all of: the lease's first submission started and
        unanswered when the operation failed, a driver that reports the
        session broken by that failure, and an operation whose repetition can
        have no effect. An error's code, a suspect mark, and the shape of a
        result grant nothing. A failure that took the place of an interrupt
        raised while the submission waited grants nothing either: that
        interrupt propagates as itself, rather than being answered by a
        resubmission that could succeed. A submission that started spends the
        opportunity, by a failure as by a return, so the second invocation can
        never earn another; and that invocation runs outside the failure it
        answers, so whatever it raises is its own.

        Where ``operation`` is ``setup`` and the plan has a later step, the
        replacement is taken from that step's route instead. Setup that is the
        first submission after entry — an outer ``BEGIN`` — is still the
        acquisition's, so once it has opened the lease is admitted against the
        step's deadline like any other setup phase. Setup whose replacement was
        refused as anything other than an outage raises that refusal rather
        than the loss: it says more about why the acquisition failed than the
        loss that asked for the replacement does.
        """
        connection = self.current_connection()
        opening = setup and self._opening
        self._opening = False
        first = self._first_send_available
        submission = SubmissionProgress()
        ambient = sys.exception()
        try:
            result = operation(connection, submission, *prepared)
        except BaseException as failure:
            if submission.started:
                self._first_send_available = False
            if not (
                first
                and submission.started
                and not submission.answered
                and replay_safe
                and isinstance(failure, Exception)
                and self._driver.is_session_broken(connection, failure)
            ):
                raise
            displaced = displaced_control_flow(failure, ambient)
            if displaced is None and not self._replace(setup=setup):
                raise
        else:
            if submission.started:
                self._first_send_available = False
            if opening:
                self._admit_opened()
            return result
        if displaced is not None:
            raise displaced
        result = operation(self.current_connection(), SubmissionProgress(), *prepared)
        if opening:
            self._admit_opened()
        return result

    def _admit_opened(self) -> None:
        """Admit a lease whose setup ended after entry, or refuse it.

        A refusal leaves the boundary that just opened to the lease's cleanup,
        which disposes of the session rather than undoing it.
        """
        try:
            self._admit(self._step_deadline)
        except ConnectionAcquisitionError as refused:
            self._suspect = True
            refused.selection = self._selection
            raise

    def _replace(self, *, setup: bool) -> bool:
        """Dispose of the current connection and hold a usable replacement in its
        place, answering whether one is now held.

        The broken connection is disposed of and handed back first, through the
        ordinary release, so its capacity returns before another is asked for;
        a release that could not be confirmed ends replacement, because nothing
        then vouches for what was handed back. The replacement is taken within
        what remains of the step's own deadline — no new allowance — and must
        arrive idle like any checkout. When no usable replacement is held, the
        slot keeps the result of the last release and the failure that asked
        for replacement stands; a checkout that refused one leaves its refusal
        on :attr:`replacement_refusal`, and raises it instead where ``setup``
        asked and it is no outage, since that refusal, rather than the loss,
        is what ended the acquisition. One that
        arrives after the deadline is given back unused and a timeout is raised
        instead, so nothing is resubmitted on it. A close is not checked here:
        the replacement is not another acquisition, so it does not end work
        already admitted.

        ``setup`` on a plan with a later step takes the replacement from that
        step's route, within what remains of the whole budget. While entry is
        still under way, entry itself establishes that route from the start;
        an outer ``BEGIN`` is the only setup after entry, and the lease ran no
        proof or authorization before it, or the ``BEGIN`` would not have been
        its first submission — so the bare checkout is all the next route
        needs.
        """
        disposed = self._settled(suspect=True)
        self._resource = disposed
        if isinstance(disposed, ReleaseUnconfirmed):
            return False
        if setup and self._step + 1 < len(self._steps):
            if self._entering:
                self._fall_back("connection_lost")
            self._advance("connection_lost")
        try:
            self._resource = check_out_within(self._route, self._step_deadline)
        except ConnectionAcquisitionError as refused:
            return self._refused_replacement(refused, setup=setup)
        try:
            self._require_idle(self.current_connection())
        except ConnectionAcquisitionError as refused:
            self._resource = self._settled(suspect=False)
            return self._refused_replacement(refused, setup=setup)
        if monotonic() >= self._step_deadline:
            self._resource = self._settled(suspect=False)
            late = ConnectionAcquisitionError(_LATE_REPLACEMENT, reason="timeout")
            late.selection = self._selection
            raise late
        self._suspect = False
        return True

    def _refused_replacement(self, refused: ConnectionAcquisitionError, *, setup: bool) -> bool:
        self._replacement_refusal = refused
        if setup and refused.reason not in OUTAGE_REASONS:
            refused.selection = self._selection
            raise refused
        return False

    def _require_idle(self, connection: C) -> None:
        """Refuse a checkout that did not hand over an idle connection.

        No modeled SQL runs on it and no unknown transaction is rolled back to
        make it usable: an adapter invariant this broken is reported, and the
        cleanup that follows disposes of the connection rather than silently
        reacquiring another.
        """
        reading = self._driver.read_idle(connection)
        if reading == "idle":
            return
        state = reading.state if isinstance(reading, NotIdle) else reading
        raise ConnectionAcquisitionError(
            f"the database runtime handed over a connection whose state is {state} rather "
            f"than idle, so no statement was run on it",
            reason="preparation_failed",
        )
