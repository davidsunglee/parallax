from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from types import TracebackType
from typing import TYPE_CHECKING, Literal

import psycopg
import psycopg_pool
from psycopg.pq import TransactionStatus
from psycopg.rows import TupleRow

from parallax.core.db_port import (
    CleanupCode,
    CleanupIssue,
    CleanupPhase,
    CleanupResult,
    ConnectionAcquisitionError,
    CredentialResolutionError,
    DatabaseConnection,
    Invalidated,
    ReleaseUnconfirmed,
    Returned,
)
from parallax.core.diagnostics import diagnostic_for
from parallax.postgres._authorization import (
    PostgresRole,
    _install_role,  # pyright: ignore[reportPrivateUsage] - the one role installation, run as the lease's first send
    _role_statement,  # pyright: ignore[reportPrivateUsage] - the one role installation, run as the lease's first send
)
from parallax.postgres._authorization import restore_role as _restore_role
from parallax.postgres._connection import ConnectionEstablishment, PostgresConnection

if TYPE_CHECKING:
    from parallax.postgres._connection import (
        _NativeOperation,  # pyright: ignore[reportPrivateUsage] - the runner's operation shape
    )

__all__ = ["NativePool", "PostgresConnectionContext"]

type NativePool = psycopg_pool.ConnectionPool[psycopg.Connection[TupleRow]]
"""Either native pool this adapter builds; the null pool is a subclass of it."""

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

type _FirstSend = Literal["available", "submitting", "spent"]


class _Condition(Exception):
    """A cleanup condition that no exception reported, stated as one.

    A cleanup issue carries a diagnostic, and an observation — a connection that
    is simply not idle — has no exception behind it. Raising one nowhere and
    projecting it here keeps every issue the same shape without ever putting
    native text into a condition Parallax itself decided.
    """


def _issue(phase: CleanupPhase, code: CleanupCode, exc: BaseException) -> CleanupIssue:
    return CleanupIssue(phase=phase, code=code, diagnostic=diagnostic_for(exc))


def checkout(
    pool: NativePool, deadline: float, establishment: ConnectionEstablishment
) -> psycopg.Connection[TupleRow]:
    """Take a connection out of ``pool`` within ``deadline``, or raise.

    The remaining budget is what the native checkout is given, so its own
    health-check recovery spends the caller's time rather than an additional
    allowance. Native failures map to the checkout-reachable acquisition reasons
    and keep their cause; authorization setup is classified later, after checkout.

    An expiry is reported as the refusal currently on record rather than as a
    ``timeout``: a configuration every new connection is refused under is what
    the caller has to fix, and the pool retries such failures in the background
    where nothing would otherwise reach the caller waiting on them. A single
    successful establishment clears the record, so a healthy runtime cannot
    report an old refusal for a later, unrelated timeout.

    An on-demand pool establishes on this thread, so a credential the source
    would not produce arrives here as itself rather than as a timeout, and is
    classified on the spot without consulting the record at all.
    """
    remaining = deadline - monotonic()
    if remaining <= 0.0:
        raise _expired(establishment, None)
    try:
        return pool.getconn(timeout=remaining)
    except psycopg_pool.PoolTimeout as exc:
        raise _expired(establishment, exc)  # noqa: B904 - the cause is chosen above
    except psycopg_pool.TooManyRequests as exc:
        raise ConnectionAcquisitionError(
            "the database runtime already has as many callers waiting as it admits",
            reason="queue_rejected",
        ) from exc
    except psycopg_pool.PoolClosed as exc:
        raise ConnectionAcquisitionError(
            "this Database is closed, so it opens no new database connection",
            reason="closed",
        ) from exc
    except CredentialResolutionError as exc:
        raise ConnectionAcquisitionError(
            "a database connection could not be authenticated",
            reason="credentials_refused",
        ) from exc
    except Exception as exc:
        raise ConnectionAcquisitionError(
            "a database connection could not be established or prepared",
            reason="preparation_failed",
        ) from exc


def _expired(
    establishment: ConnectionEstablishment, native: BaseException | None
) -> ConnectionAcquisitionError:
    """The failure a spent acquisition budget reports, and what it chains.

    An expiry names the establishment refusal on record where there is one, and
    the native timeout otherwise. The refusal is the more actionable of the two:
    it happened on the runtime's own background path, where the pool retries and
    logs it and nothing reaches the caller waiting on it, and a configuration
    every new connection is refused under is what an operator has to fix. A bare
    "timed out" names none of that.

    The two kinds a record can hold are two different things to fix — a
    credential the source would not produce, or a session the codecs cannot run
    under — so each reports its own reason and says so in its own words.
    """
    refusal = establishment.last_refusal
    if refusal is None:
        timed_out = ConnectionAcquisitionError(
            "no database connection became available within the acquisition timeout",
            reason="timeout",
        )
        timed_out.__cause__ = native
        return timed_out
    if isinstance(refusal, CredentialResolutionError):
        unauthenticated = ConnectionAcquisitionError(
            "no database connection could be authenticated within the acquisition timeout",
            reason="credentials_refused",
        )
        unauthenticated.__cause__ = refusal
        return unauthenticated
    unusable = ConnectionAcquisitionError(
        "no database connection became usable within the acquisition timeout; the last "
        "connection this runtime opened was refused as unusable",
        reason="preparation_failed",
    )
    unusable.__cause__ = refusal
    return unusable


def _status(connection: psycopg.Connection[TupleRow]) -> TransactionStatus | None:
    try:
        return TransactionStatus(connection.pgconn.transaction_status)
    except Exception:
        return None


def release(
    pool: NativePool,
    connection: psycopg.Connection[TupleRow],
    *,
    suspect: bool,
    restore_role: bool = False,
) -> CleanupResult:
    """End this connection's exclusive use, and report what that established.

    The sequence is finite — inspect, restore scoped authorization where reuse
    remains possible, dispose where either step or the execution says reuse
    cannot be established, then hand back exactly once — so the issues it can
    report are bounded by the steps rather than accumulated as history.

    Three refusals are deliberate. A failed physical close does NOT fall back to
    returning a connection that is still suspect, because balancing the
    accounting is not worth offering the next caller a session nothing can
    vouch for. A failed handoff is not retried and is not followed by a close,
    because a native return that raised may still have handed the connection to
    another caller. And a completed handoff is never inspected afterwards, for
    the same reason.
    """
    issues: list[CleanupIssue] = []
    dispose = suspect
    if suspect:
        issues.append(_issue("inspect", "suspect", _Condition("the execution marked it suspect")))
    else:
        status = _status(connection)
        if status is None:
            dispose = True
            issues.append(
                _issue("inspect", "state-unreadable", _Condition("its state could not be read"))
            )
        elif status != TransactionStatus.IDLE:
            dispose = True
            issues.append(_issue("inspect", "not-idle", _Condition(f"its state was {status.name}")))

    if not dispose and restore_role:
        try:
            _restore_role(connection)
        except Exception as exc:
            dispose = True
            issues.append(_issue("restore", "authorization-restore-failed", exc))

    if dispose:
        try:
            connection.close()
        except Exception as exc:
            issues.append(_issue("dispose", "close-failed", exc))
            return ReleaseUnconfirmed(tuple(issues))
    try:
        pool.putconn(connection)
    except Exception as exc:
        issues.append(_issue("return", "handoff-failed", exc))
        return ReleaseUnconfirmed(tuple(issues))
    return Invalidated(tuple(issues)) if dispose else Returned(tuple(issues))


class PostgresConnectionContext:
    """One single-use acquisition of a connection from a native pool.

    Creating it takes nothing. Entering it checks out, verifies the connection
    is idle, checks admission against the deadline, installs any bound role,
    rechecks admission after that provider work, and yields fresh execution
    access. Leaving it revokes that access and releases the connection once,
    restoring an installed role only where the session remains reusable.

    Entry is permitted once and once only, including after an entry that failed:
    a failed entry has already run cleanup over whatever it took and left what
    that established on :attr:`cleanup_result`, so a second attempt would be a
    second acquisition wearing the first one's identity.

    The context is the only holder of the physical connection for the whole
    lease: execution borrows the current one for each operation. That is what
    lets the lease's actual first submission — its role installation, an outer
    ``BEGIN``, or a read its caller designated — run once more if it meets a
    broken session: the connection is disposed of and handed back, another is
    taken within the original deadline, and the same prepared submission is
    made on it, all inside this one acquisition. Any other submission, the
    second attempt itself, and a write never are. Once no connection can be
    kept, the slot holds the cleanup that ended it instead, and that is what
    leaving reports.
    """

    __slots__ = (
        "_admit",
        "_authorized",
        "_cleanup_result",
        "_deadline",
        "_establishment",
        "_execution",
        "_first_send_state",
        "_pool",
        "_resource",
        "_role",
        "_suspect",
        "_used",
    )

    def __init__(
        self,
        pool: NativePool,
        admit: Admit,
        deadline: float,
        establishment: ConnectionEstablishment,
        role: PostgresRole | None,
    ) -> None:
        self._pool = pool
        self._admit = admit
        self._deadline = deadline
        self._establishment = establishment
        self._role = role
        self._used = False
        self._authorized = False
        self._suspect = False
        self._first_send_state: _FirstSend = "available"
        self._resource: psycopg.Connection[TupleRow] | CleanupResult | None = None
        self._execution: PostgresConnection | None = None
        self._cleanup_result: CleanupResult | None = None

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return self._cleanup_result

    def __enter__(self) -> DatabaseConnection:
        if self._used:
            raise RuntimeError(_ENTER_ONCE if self._execution is not None else _SPENT)
        self._used = True
        self._resource = checkout(self._pool, self._deadline, self._establishment)
        try:
            self._require_idle(self._current_native())
            self._admit(self._deadline)
        except BaseException:
            # Nothing modeled has run, so what was taken is given back through
            # the same path a completed scope uses: an idle connection returns
            # and a non-idle one is disposed of, without either decision being
            # made twice.
            self._cleanup_result = self._settled(suspect=False)
            raise
        role = self._role
        if role is not None:
            try:
                self._run_native(_install_role, _role_statement(role), replay_safe=True)
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
                self._admit(self._deadline)
            except BaseException:
                self._cleanup_result = self._settled(suspect=False, restore_role=True)
                self._authorized = False
                raise
        execution = PostgresConnection._from_context(self)  # pyright: ignore[reportPrivateUsage] - the facade borrowing this owner's connection
        self._execution = execution
        return execution

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
        revoked = False
        try:
            execution.revoke()
            revoked = True
        finally:
            self._execution = None
            self._cleanup_result = self._settled(
                suspect=self._suspect or not revoked, restore_role=self._authorized
            )
            self._authorized = False

    def _settled(self, *, suspect: bool, restore_role: bool = False) -> CleanupResult | None:
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
        return release(self._pool, resource, suspect=suspect, restore_role=restore_role)

    def _current_native(self) -> psycopg.Connection[TupleRow]:
        resource = self._resource
        if resource is None or isinstance(resource, Returned | Invalidated | ReleaseUnconfirmed):
            raise RuntimeError(_LOST)
        return resource

    def _mark_suspect(self) -> None:
        self._suspect = True

    def _start_first_send(self) -> None:
        if self._first_send_state == "available":
            self._first_send_state = "submitting"

    def _complete_first_send(self) -> None:
        if self._first_send_state == "submitting":
            self._first_send_state = "spent"

    def _run_native[T, *P](
        self, operation: _NativeOperation[T, *P], /, *prepared: *P, replay_safe: bool
    ) -> T:
        """Run ``operation`` on the current connection, replacing that connection
        once if this was the lease's first submission and it met a broken session.

        Replacement needs all three of: a raw driver failure while the first
        submission was in progress, a connection the driver now reports closed
        — which a broken one is — and an operation whose repetition can have no
        effect. An error's code, a suspect mark, and the shape of a result grant
        nothing. The opportunity is spent before anything else happens, by a
        failure as by a return, so the second invocation can never earn
        another; and that invocation runs outside the failure it answers, so
        whatever it raises is its own.
        """
        native = self._current_native()
        try:
            result = operation(native, self, *prepared)
        except BaseException as failure:
            submitting = self._first_send_state == "submitting"
            if submitting:
                self._first_send_state = "spent"
            if not (
                submitting
                and replay_safe
                and isinstance(failure, psycopg.Error)
                and native.closed
                and self._replace_native()
            ):
                raise
        else:
            self._complete_first_send()
            return result
        return operation(self._current_native(), self, *prepared)

    def _replace_native(self) -> bool:
        """Dispose of the current connection and hold a usable replacement in its
        place, answering whether one is now held.

        The broken connection is disposed of and handed back first, through the
        ordinary release, so its capacity returns before another is asked for;
        a release that could not be confirmed ends replacement, because nothing
        then vouches for what was handed back. The replacement is taken within
        what remains of this lease's own deadline — no new allowance, and no
        admission decision of its own — and must arrive idle like any
        checkout. When no usable replacement is held, the slot keeps the result
        of the last release, and the failure that asked for replacement stands.
        """
        disposed = self._settled(suspect=True)
        self._resource = disposed
        if isinstance(disposed, ReleaseUnconfirmed):
            return False
        try:
            self._resource = checkout(self._pool, self._deadline, self._establishment)
        except ConnectionAcquisitionError:
            return False
        try:
            self._require_idle(self._current_native())
        except ConnectionAcquisitionError:
            self._resource = self._settled(suspect=False)
            return False
        self._suspect = False
        return True

    def _require_idle(self, connection: psycopg.Connection[TupleRow]) -> None:
        """Refuse a checkout that did not hand over an idle connection.

        No modeled SQL runs on it and no unknown transaction is rolled back to
        make it usable: an adapter invariant this broken is reported, and the
        cleanup that follows disposes of the connection rather than silently
        reacquiring another.
        """
        status = _status(connection)
        if status == TransactionStatus.IDLE:
            return
        state = "unreadable" if status is None else status.name
        raise ConnectionAcquisitionError(
            f"the database runtime handed over a connection whose state is {state} rather "
            f"than idle, so no statement was run on it",
            reason="preparation_failed",
        )
