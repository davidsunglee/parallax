"""Scripted adapters at the DB-port's native seams, for the shared runtime's suites.

What a real pool or driver will not produce on demand — a checkout that fails
for a chosen reason, a hand-back or close that raises, a reading that cannot be
taken, a dial failure reported while a caller waits, a session the server ended
while it sat idle, a proof that reads back another login — is scripted here in
the seams' own terms, so a policy test enters where an adapter enters rather
than through a driver.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, cast

from parallax.core.internal.db_port import (
    CheckoutFailed,
    CheckoutReason,
    ConnectionLease,
    DialReason,
    DialRecord,
    ExecutionAccess,
    IdleReading,
    NotIdle,
    PoolMetrics,
    PoolPurpose,
    ProbeMismatch,
    Route,
    Row,
    SubmissionProgress,
)

if TYPE_CHECKING:
    import pytest

__all__ = [
    "PROVE",
    "RESTORE",
    "Clock",
    "ScriptedConnection",
    "ScriptedDriver",
    "ScriptedExecution",
    "ScriptedPool",
    "SessionLost",
    "checkout_failed",
    "submit",
]

PROVE = "prove"
"""What a readiness proof submits."""

RESTORE = "restore"
"""What restoring authorization records."""

OTHER_LOGIN = "the proof read another login"


def checkout_failed(reason: CheckoutReason, cause: BaseException | None = None) -> CheckoutFailed:
    """The failure a pool's checkout raises for ``reason``, chained to ``cause``."""
    failed = CheckoutFailed(reason)
    failed.__cause__ = cause
    return failed


class SessionLost(Exception):
    """A failure the scripted driver reads as a session the server ended.

    It is the only failure :meth:`ScriptedDriver.is_session_lost` accepts, and
    the only one :meth:`ScriptedDriver.is_session_broken` accepts on a broken
    connection.
    """


class ScriptedConnection:
    """One native connection: the state cleanup reads and the failures it meets.

    ``lost`` is a session the server ended while it sat idle: nothing about it
    looks different until something is submitted, and then that submission
    starts, the connection becomes broken with its state unknown, and ``lost``
    is raised. ``failure`` is raised by a submission that started on a healthy
    session, and ``after_answer`` once a submission was answered, as fetching
    or decoding would.
    ``on_submit`` runs with each submission's text before it starts.

    A proof reads back ``login``, or raises :class:`ProbeMismatch` with
    ``mismatch``, or for a login other than the one expected.
    """

    def __init__(
        self,
        *,
        idle: IdleReading = "idle",
        login: str = "runtime-login",
        mismatch: str | None = None,
        rows: list[Row] | None = None,
        failure: BaseException | None = None,
        after_answer: BaseException | None = None,
        lost: BaseException | None = None,
        when_lost: Callable[[], None] = lambda: None,
        on_submit: Callable[[str], None] | None = None,
        close_failure: BaseException | None = None,
        restore_failure: BaseException | None = None,
    ) -> None:
        self.idle: IdleReading = idle
        self.login = login
        self.mismatch = mismatch
        self.rows: list[Row] = rows if rows is not None else []
        self.failure = failure
        self.after_answer = after_answer
        self.lost = lost
        self.when_lost = when_lost
        self.on_submit = on_submit
        self.close_failure = close_failure
        self.restore_failure = restore_failure
        self.broken = False
        self.closed = False
        self.closes = 0
        self.submitted: list[str] = []
        self.prepared: list[tuple[object, ...]] = []
        self.limits: list[float] = []

    def submit(self, submission: SubmissionProgress, text: str, *prepared: object) -> list[Row]:
        if self.on_submit is not None:
            self.on_submit(text)
        self.submitted.append(text)
        self.prepared.append(prepared)
        submission.started = True
        lost = self.lost
        if lost is not None:
            self.broken = True
            self.idle = NotIdle("UNKNOWN")
            self.when_lost()
            raise lost
        if self.failure is not None:
            raise self.failure
        submission.answered = True
        if self.after_answer is not None:
            raise self.after_answer
        return self.rows

    def restore(self) -> None:
        self.submitted.append(RESTORE)
        if self.restore_failure is not None:
            raise self.restore_failure

    def close(self) -> None:
        self.closes += 1
        if self.close_failure is not None:
            raise self.close_failure
        self.closed = True


def submit(
    connection: ScriptedConnection, submission: SubmissionProgress, text: str, *prepared: object
) -> list[Row]:
    """The native operation submitting ``text`` with ``prepared`` inputs."""
    return connection.submit(submission, text, *prepared)


class ScriptedPool[C]:
    """A connection pool handing over its connections in turn, then the last again.

    ``checkout_failure``, ``hand_back_failure``, ``close_failure`` and
    ``metrics_failure`` are read at call time, so a test can change one between
    calls. ``on_check_out`` runs with the budget at the start of every checkout,
    before its outcome is decided: where a dial failure is reported to
    :attr:`dial_record` while a caller waits, or the clock moves during the wait.
    ``on_close`` runs at the start of every close, before its outcome is decided:
    where a test observes what the runtime has already done during teardown.

    Every budget asked for, every connection handed back and by which method,
    and every close are recorded.
    """

    def __init__(
        self,
        *connections: C,
        checkout_failure: BaseException | None = None,
        hand_back_failure: Exception | None = None,
        close_failure: BaseException | None = None,
        metrics_failure: BaseException | None = None,
    ) -> None:
        self._connections = list(connections)
        self.checkout_failure = checkout_failure
        self.hand_back_failure = hand_back_failure
        self.close_failure = close_failure
        self.metrics_failure = metrics_failure
        self.on_check_out: Callable[[float], None] | None = None
        self.on_close: Callable[[], None] | None = None
        self.dial_record: DialRecord | None = None
        self.available = 0
        self.budgets: list[float] = []
        self.check_ins: list[C] = []
        self.discards: list[C] = []
        self.returned: list[C] = []
        self.hand_backs = 0
        self.closes = 0

    def check_out(self, budget: float, /) -> C:
        self.budgets.append(budget)
        if self.on_check_out is not None:
            self.on_check_out(budget)
        if self.checkout_failure is not None:
            raise self.checkout_failure
        return self._connections[min(len(self.budgets), len(self._connections)) - 1]

    def check_in(self, connection: C, /) -> None:
        self._hand_back(connection)
        self.check_ins.append(connection)

    def discard(self, connection: C, /) -> None:
        self._hand_back(connection)
        self.discards.append(connection)

    def _hand_back(self, connection: C) -> None:
        self.hand_backs += 1
        if self.hand_back_failure is not None:
            raise self.hand_back_failure
        self.returned.append(connection)

    def metrics(self) -> PoolMetrics:
        if self.metrics_failure is not None:
            raise self.metrics_failure
        return PoolMetrics(
            pool_min=0,
            pool_max=10,
            pool_size=len(self._connections),
            pool_available=self.available,
            requests_waiting=0,
        )

    def close(self) -> None:
        self.closes += 1
        if self.on_close is not None:
            self.on_close()
        if self.close_failure is not None:
            raise self.close_failure


_REVOKED = "this scripted execution's scope has ended"


class ScriptedExecution:
    """Execution access whose every statement is one scripted submission run
    through the lease the driver opened it over."""

    def __init__(self, lease: ConnectionLease[ScriptedConnection], driver: ScriptedDriver) -> None:
        self._lease: ConnectionLease[ScriptedConnection] | None = lease
        self._driver = driver

    @property
    def lease(self) -> ConnectionLease[ScriptedConnection]:
        lease = self._lease
        if lease is None:
            raise RuntimeError(_REVOKED)
        return lease

    def submit(
        self, text: str, *prepared: object, replay_safe: bool = False, setup: bool = False
    ) -> list[Row]:
        return self.lease.run(submit, text, *prepared, replay_safe=replay_safe, setup=setup)

    def revoke(self) -> bool:
        failure = self._driver.revoke_failure
        if failure is not None:
            raise failure
        lease = self._lease
        self._lease = None
        return lease is not None and lease.suspect


class ScriptedDriver:
    """A native driver over :class:`ScriptedConnection` and :class:`ScriptedPool`.

    ``pools`` holds what opening each route's application pool, or the
    reservation pool under ``"reservation"``, returns — or raises, for an
    exception. A pool not named is a fresh one over one healthy connection,
    kept in ``pools`` once opened. Each pool keeps the dial record it was opened
    with, and a failure in ``recorded`` is reported to its route's record as
    the pool opens, as a retaining pool's first background dial would.

    Every pool opened, every execution handed out, and every authorization
    checked are recorded.
    """

    def __init__(
        self,
        *,
        pools: Mapping[str, ScriptedPool[ScriptedConnection] | BaseException] | None = None,
        recorded: Mapping[Route, tuple[DialReason, BaseException]] | None = None,
    ) -> None:
        self.pools: dict[str, ScriptedPool[ScriptedConnection] | BaseException] = dict(pools or {})
        self.recorded = dict(recorded or {})
        self.opened: list[tuple[Route, PoolPurpose]] = []
        self.executions: list[ScriptedExecution] = []
        self.authorizations: list[object] = []
        self.authorization_refusal: Exception | None = None
        self.revoke_failure: BaseException | None = None

    def pool(self, key: str) -> ScriptedPool[ScriptedConnection]:
        pool = self.pools[key]
        assert isinstance(pool, ScriptedPool)
        return pool

    def open_pool(
        self, route: Route, purpose: PoolPurpose, dial_record: DialRecord
    ) -> ScriptedPool[ScriptedConnection]:
        self.opened.append((route, purpose))
        key = route if purpose == "application" else purpose
        pool = self.pools.setdefault(key, ScriptedPool(ScriptedConnection()))
        if isinstance(pool, BaseException):
            raise pool
        pool.dial_record = dial_record
        if purpose == "application" and route in self.recorded:
            dial_record.report_failure(*self.recorded[route])
        return pool

    def open_execution(self, lease: ConnectionLease[ScriptedConnection]) -> ExecutionAccess:
        execution = ScriptedExecution(lease, self)
        self.executions.append(execution)
        return cast("ExecutionAccess", execution)

    def authorization(self, value: object, /) -> object:
        self.authorizations.append(value)
        if self.authorization_refusal is not None:
            raise self.authorization_refusal
        return value

    def read_idle(self, connection: ScriptedConnection) -> IdleReading:
        return connection.idle

    def close_connection(self, connection: ScriptedConnection) -> None:
        connection.close()

    def is_session_broken(self, connection: ScriptedConnection, failure: BaseException) -> bool:
        return connection.broken and isinstance(failure, SessionLost)

    def is_session_lost(self, failure: BaseException) -> bool:
        return isinstance(failure, SessionLost)

    def prove_readiness(
        self,
        connection: ScriptedConnection,
        submission: SubmissionProgress,
        expected_login: str | None,
    ) -> str:
        connection.submit(submission, PROVE)
        if connection.mismatch is not None:
            raise ProbeMismatch(connection.mismatch)
        if expected_login is not None and connection.login != expected_login:
            raise ProbeMismatch(OTHER_LOGIN)
        return connection.login

    def install_authorization(
        self, connection: ScriptedConnection, submission: SubmissionProgress, authorization: object
    ) -> None:
        connection.submit(submission, f"authorize {authorization}")

    def restore_authorization(self, connection: ScriptedConnection) -> None:
        connection.restore()

    def limit_statement_time(
        self, connection: ScriptedConnection, submission: SubmissionProgress, seconds: float
    ) -> None:
        connection.limits.append(seconds)
        connection.submit(submission, "limit")


class Clock:
    """A monotonic clock a proof moves by hand, read by every module that keeps time."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, now: float = 0.0) -> None:
        from parallax.core.internal.db_port._runtime import _context as context_module
        from parallax.core.internal.db_port._runtime import _pooled_runtime as runtime_module
        from parallax.core.internal.db_port._runtime import _startup as startup_module

        self.now = now
        for module in (context_module, runtime_module, startup_module):
            monkeypatch.setattr(module, "monotonic", lambda: self.now)
