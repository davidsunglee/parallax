"""One acquisition: checkout, admission, revocation, and the single cleanup path.

Everything a connection's exclusive-use lifetime needs is here and nowhere else,
because every way an acquisition can end has to reach the same relinquishment.
A statement that failed, a conversion that failed, a transaction that could not
be rolled back, a stream a caller abandoned, an observer that raised, a
``KeyboardInterrupt`` — all of them leave through :meth:`PostgresConnectionContext.__exit__`,
and it is the one place that decides between offering a connection for reuse and
disposing of it.

The decision is deliberately pessimistic and deliberately unrepairing. Reuse is
offered only for a connection that is idle and that the execution did not
declare suspect. Anything else is disposed of FIRST and then handed back for
accounting, so capacity is never leaked and a connection nothing can vouch for
is never offered to the next caller. Nothing here tries to repair a state in
order to reuse it, and nothing inspects a connection after handing it off:
after a handoff the connection may already belong to somebody else.
"""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from types import TracebackType

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
    DatabaseConnection,
    Invalidated,
    Returned,
    Unrelinquished,
)
from parallax.core.diagnostics import diagnostic_for
from parallax.postgres._connection import ConnectionPreparation, PostgresConnection

__all__ = ["Admit", "NativePool", "PostgresConnectionContext", "checkout", "relinquish"]

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
    pool: NativePool, deadline: float, preparation: ConnectionPreparation
) -> psycopg.Connection[TupleRow]:
    """Take a connection out of ``pool`` within ``deadline``, or raise.

    The remaining budget is what the native checkout is given, so its own
    health-check recovery spends the caller's time rather than an additional
    allowance. Native failures map to the four acquisition reasons and keep
    their cause.

    An expiry is reported as ``preparation_failed`` rather than ``timeout``
    when a connection initialization refusal is currently on record: a
    configuration every new connection is refused under is what the caller has
    to fix, and the pool retries such failures in the background where nothing
    would otherwise reach the caller waiting on them. A single successful
    initialization clears the record, so a healthy runtime cannot report an old
    refusal for a later, unrelated timeout.
    """
    remaining = deadline - monotonic()
    if remaining <= 0.0:
        raise _expired(preparation, None)
    try:
        return pool.getconn(timeout=remaining)
    except psycopg_pool.PoolTimeout as exc:
        raise _expired(preparation, exc)  # noqa: B904 - the cause is chosen above
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
    except Exception as exc:
        raise ConnectionAcquisitionError(
            "a database connection could not be established or prepared",
            reason="preparation_failed",
        ) from exc


def _expired(
    preparation: ConnectionPreparation, native: BaseException | None
) -> ConnectionAcquisitionError:
    """The failure a spent acquisition budget reports, and what it chains.

    An expiry names the initialization refusal on record where there is one, and
    the native timeout otherwise. The refusal is the more actionable of the two:
    it happened on the runtime's own background path, where the pool retries and
    logs it and nothing reaches the caller waiting on it, and a configuration
    every new connection is refused under is what an operator has to fix. A bare
    "timed out" names none of that.
    """
    refusal = preparation.last_refusal
    if refusal is None:
        timed_out = ConnectionAcquisitionError(
            "no database connection became available within the acquisition timeout",
            reason="timeout",
        )
        timed_out.__cause__ = native
        return timed_out
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


def relinquish(
    pool: NativePool, connection: psycopg.Connection[TupleRow], *, suspect: bool
) -> CleanupResult:
    """End this connection's exclusive use, and report what that established.

    The sequence is finite — inspect, dispose where inspection or the execution
    says reuse cannot be established, hand back exactly once — so the issues it
    can report are bounded by the steps rather than accumulated as history.

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

    if dispose:
        try:
            connection.close()
        except Exception as exc:
            issues.append(_issue("dispose", "close-failed", exc))
            return Unrelinquished(tuple(issues))
    try:
        pool.putconn(connection)
    except Exception as exc:
        issues.append(_issue("return", "handoff-failed", exc))
        return Unrelinquished(tuple(issues))
    return Invalidated(tuple(issues)) if dispose else Returned(tuple(issues))


class PostgresConnectionContext:
    """One single-use acquisition of a connection from a native pool.

    Creating it takes nothing. Entering it checks out, verifies the connection
    is idle, checks admission against the deadline, and yields fresh execution
    access. Leaving it revokes that access and relinquishes the connection once.

    Entry is permitted once and once only, including after an entry that failed:
    a failed entry has already run cleanup over whatever it took and left what
    that established on :attr:`cleanup_result`, so a second attempt would be a
    second acquisition wearing the first one's identity.
    """

    __slots__ = (
        "_admit",
        "_cleanup_result",
        "_deadline",
        "_execution",
        "_native",
        "_pool",
        "_preparation",
        "_spent",
    )

    def __init__(
        self,
        pool: NativePool,
        admit: Admit,
        deadline: float,
        preparation: ConnectionPreparation,
    ) -> None:
        self._pool = pool
        self._admit = admit
        self._deadline = deadline
        self._preparation = preparation
        self._spent = False
        self._native: psycopg.Connection[TupleRow] | None = None
        self._execution: PostgresConnection | None = None
        self._cleanup_result: CleanupResult | None = None

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return self._cleanup_result

    def __enter__(self) -> DatabaseConnection:
        if self._spent:
            raise RuntimeError(_SPENT if self._native is None else _ENTER_ONCE)
        self._spent = True
        connection = checkout(self._pool, self._deadline, self._preparation)
        try:
            self._require_idle(connection)
            self._admit(self._deadline)
        except BaseException:
            # Nothing modeled has run, so what was taken is given back through
            # the same path a completed scope uses: an idle connection returns
            # and a non-idle one is disposed of, without either decision being
            # made twice.
            self._cleanup_result = relinquish(self._pool, connection, suspect=False)
            raise
        self._native = connection
        execution = PostgresConnection(connection)
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
        connection = self._native
        execution = self._execution
        if connection is None or execution is None:
            return
        # Revoked before anything else, so the caller's own reference cannot
        # reach a connection this is about to hand to somebody else — and so the
        # native reference cleanup needs is held here rather than through it.
        #
        # Relinquishment is what the exit exists for, so it runs even if
        # revocation does not complete: this is the only path back to the pool,
        # and clearing the references first would make a second exit a silent
        # no-op over a connection nothing ever gave back. A revocation that did
        # not complete leaves a scope that may still reach the connection, so
        # what is given back is treated as suspect and disposed of.
        suspect = True
        try:
            suspect = execution.revoke()
        finally:
            self._native = None
            self._execution = None
            self._cleanup_result = relinquish(self._pool, connection, suspect=suspect)

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
