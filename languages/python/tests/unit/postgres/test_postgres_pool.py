"""The Postgres runtime's resource lifetimes, over a fake native pool (Docker-free).

Three things live here and nowhere else, so they are proven here rather than
against a container: what readiness establishes before a handle is published,
what one acquisition is allowed to do, and what releasing one establishes.
The failures that matter most are the ones a real server will not produce on
demand — a checkout that hands over a connection in a transaction, a physical
close that raises, a native return that raises after it may already have handed
the connection to somebody else — so the native pool and its connections are
fakes with those failures scripted, and the live proofs are in the provider lane.

The pins are deliberately pessimistic about cleanup. A cleanup result says what
was ESTABLISHED, so the interesting assertions are the ones that refuse to claim
more than that: a failed disposal does not fall back to returning a suspect
connection, a failed handoff is not retried, and a completed handoff is never
inspected afterwards.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from time import monotonic
from typing import Any, ClassVar, cast

import psycopg
import psycopg_pool
import pytest
from psycopg.adapt import AdaptersMap
from psycopg.pq import TransactionStatus
from psycopg.rows import TupleRow

from parallax.core.internal.base import INFINITY
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import (
    DRIVER_MANAGED,
    RESOURCE_LOGGER_NAME,
    BeginFailed,
    Committed,
    ConnectionAcquisitionError,
    CredentialResolutionError,
    DatabaseConnection,
    DatabaseStartupError,
    Invalidated,
    OrderedWriteResult,
    OrderedWriteResultComplete,
    OrderedWriteResultInterrupted,
    Password,
    PipelineStatement,
    PoolDetached,
    ReleaseUnconfirmed,
    Returned,
    RouteCapabilities,
    RouteSelection,
    Row,
)
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresEndpoint, PostgresRole
from parallax.postgres._connection import (
    ConnectionEstablishment,
    IncompatibleSessionError,
    dial_reason,
    session_lost,
)
from parallax.postgres._context import PostgresConnectionContext, checkout, release
from parallax.postgres._route import PROBE_SQL, PostgresRoute, ProbeMismatch
from parallax.postgres._route_plan import RoutePlan
from parallax.postgres._runtime import PostgresRuntime
from parallax.postgres._startup import open_runtime
from tests.unit.postgres._native_pipeline_support import Server, Statement, native_session

_PROBE_ROW = {
    "ready": 1,
    "temporal_bound": INFINITY,
    "document": {"ready": True},
    "float32_witness": 7.038530691851209e-26,
    "float64_witness": 0.30000000000000004,
    "login_identity": "runtime-login",
}


class _Column:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeCursor:
    """A cursor whose row factory, when given one, builds each row once its result attaches."""

    def __init__(
        self,
        connection: _FakeConnection,
        row_factory: Callable[[_FakeCursor], Callable[[tuple[object, ...]], object]] | None,
    ) -> None:
        self._connection = connection
        self._row_factory = row_factory
        self._make_row: Callable[[tuple[object, ...]], object] | None = None
        self.description: list[_Column] | None = None
        self.rowcount = 0

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return

    def execute(self, sql: object, binds: Sequence[object] | None = None) -> None:
        text = sql.decode() if isinstance(sql, bytes) else str(sql)
        self._connection.submit(text, binds)
        if self._connection.execute_error is not None:
            raise self._connection.execute_error
        rows = self._connection.rows
        self.description = [_Column(name) for name in rows[0]] if rows else None
        if self._row_factory is not None:
            self._make_row = self._row_factory(self)

    def fetchall(self) -> list[object]:
        records = [tuple(row.values()) for row in self._connection.rows]
        make_row = self._make_row
        return [*records] if make_row is None else [make_row(record) for record in records]


class _FakePgConn:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    @property
    def transaction_status(self) -> int:
        if self._connection.status_error is not None:
            raise self._connection.status_error
        return int(self._connection.status)


class _FakeTransaction:
    """A driver transaction context whose entry raises the connection's begin
    failure, leaving the session idle as a server-refused ``BEGIN`` does."""

    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> _FakeTransaction:
        connection = self._connection
        connection.submit("BEGIN", None)
        if connection.begin_error is not None:
            raise connection.begin_error
        connection.status = TransactionStatus.INTRANS
        return self

    def __exit__(self, exc_type: object, exc: BaseException | None, tb: object) -> bool:
        del exc_type, tb
        self._connection.statements.append("COMMIT" if exc is None else "ROLLBACK")
        self._connection.status = TransactionStatus.IDLE
        return False


class _FakeConnection:
    """One physical connection: the state cleanup inspects and the failures it meets.

    ``lost`` is a session the server ended while it sat idle: nothing about it
    looks different until something is submitted, and then that submission
    raises ``lost`` and the driver reports the connection closed with its
    state unknown, as psycopg does once libpq finds the socket gone.
    ``when_lost`` runs at that moment, for a proof that needs time to have
    passed by then.
    """

    def __init__(
        self,
        *,
        rows: list[dict[str, object]] | None = None,
        status: TransactionStatus = TransactionStatus.IDLE,
        status_error: Exception | None = None,
        close_error: BaseException | None = None,
        execute_error: BaseException | None = None,
        reset_error: Exception | None = None,
        begin_error: Exception | None = None,
        lost: psycopg.Error | None = None,
        when_lost: Callable[[], None] = lambda: None,
    ) -> None:
        self.rows = rows if rows is not None else [dict(_PROBE_ROW)]
        self.begin_error = begin_error
        self.characteristics: list[tuple[str, object]] = []
        self.status = status
        self.status_error = status_error
        self.close_error = close_error
        self.execute_error: BaseException | None = execute_error
        self.reset_error = reset_error
        self.lost = lost
        self.when_lost = when_lost
        self.closed = False
        self.statements: list[str] = []
        self.binds: list[Sequence[object] | None] = []
        self.closes = 0
        self.pgconn = _FakePgConn(self)

    def submit(self, text: str, binds: Sequence[object] | None) -> None:
        self.statements.append(text)
        self.binds.append(binds)
        lost = self.lost
        if lost is not None:
            self.closed = True
            self.status = TransactionStatus.UNKNOWN
            self.when_lost()
            raise lost

    def cursor(
        self,
        *,
        row_factory: Callable[[_FakeCursor], Callable[[tuple[object, ...]], object]] | None = None,
    ) -> _FakeCursor:
        return _FakeCursor(self, row_factory)

    def execute(self, sql: object, binds: Sequence[object] | None = None) -> _FakeCursor:
        text = sql.decode() if isinstance(sql, bytes) else str(sql)
        if text == "RESET ROLE" and self.reset_error is not None:
            self.statements.append(text)
            raise self.reset_error
        cursor = self.cursor()
        cursor.execute(sql, binds)
        return cursor

    @property
    def isolation_level(self) -> object:
        return None

    @isolation_level.setter
    def isolation_level(self, value: object) -> None:
        self.characteristics.append(("isolation_level", value))

    @property
    def read_only(self) -> object:
        return None

    @read_only.setter
    def read_only(self, value: object) -> None:
        self.characteristics.append(("read_only", value))

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def pipeline(self) -> AbstractContextManager[None]:
        return nullcontext()

    def rollback(self) -> None:
        return

    def close(self) -> None:
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class _FakePool:
    """The native pool, scripted at the four calls the runtime makes of it."""

    def __init__(
        self,
        *connections: _FakeConnection,
        checkout_error: BaseException | None = None,
        putconn_error: Exception | None = None,
        wait_error: Exception | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self._connections = list(connections) or [_FakeConnection()]
        self.checkout_error = checkout_error
        self.putconn_error = putconn_error
        self.wait_error = wait_error
        self.close_error = close_error
        self.checkouts: list[float | None] = []
        self.returned: list[_FakeConnection] = []
        self.handoffs = 0
        self.waits: list[float] = []
        self.closes = 0
        self.late_by: float = 0.0
        self.available = 0

    def wait(self, timeout: float = 30.0) -> None:
        self.waits.append(timeout)
        if self.wait_error is not None:
            raise self.wait_error

    def getconn(self, timeout: float | None = None) -> _FakeConnection:
        self.checkouts.append(timeout)
        if self.checkout_error is not None:
            raise self.checkout_error
        return self._connections[min(len(self.checkouts), len(self._connections)) - 1]

    def putconn(self, conn: _FakeConnection) -> None:
        self.handoffs += 1
        if self.putconn_error is not None:
            raise self.putconn_error
        self.returned.append(conn)

    def close(self) -> None:
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error

    def get_stats(self) -> dict[str, object]:
        return {
            "pool_min": 0,
            "pool_max": 10,
            "pool_size": len(self._connections),
            "pool_available": self.available,
            "requests_waiting": 0,
        }


def _pool(*connections: _FakeConnection, **kwargs: Any) -> Any:
    return cast("Any", _FakePool(*connections, **kwargs))


def _runtime(pool: Any, *, acquire_timeout: float = 15.0) -> PostgresRuntime:
    return PostgresRuntime(
        PostgresRoute("writer", pool, _establishment()), acquire_timeout=acquire_timeout
    )


def _open_runtime(
    options: PoolOptions | OnDemandOptions, credentials: Any = DRIVER_MANAGED
) -> PostgresRuntime:
    return open_runtime(
        PostgresEndpoint("", credentials=credentials, pool=options),
        None,
        acquire_timeout=15.0,
        startup_timeout=30.0,
        reader_startup="deferrable",
        prepare_threshold=5,
    )


def _establishment() -> ConnectionEstablishment:
    return ConnectionEstablishment()


def _context(
    pool: Any,
    *,
    deadline: float | None = None,
    admit: Any = None,
    role: PostgresRole | None = None,
) -> Any:
    runtime = _runtime(pool)
    return PostgresConnectionContext(
        (
            (
                PostgresRoute("writer", pool, _establishment()),
                deadline if deadline is not None else monotonic() + 5.0,
            ),
        ),
        admit if admit is not None else runtime._admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        role,
        expected_login=None,
    )


def _login_context(runtime: PostgresRuntime) -> Any:
    return runtime.login_source().new_context("writer_only")


# --------------------------------------------------------------------------- #
# Readiness: only a runtime that has proved it can execute is returned.        #
# --------------------------------------------------------------------------- #


def _opened(monkeypatch: pytest.MonkeyPatch, pool: Any) -> Any:
    """Make ``open_runtime`` build ``pool`` rather than a native one."""
    from parallax.postgres import _route as route_module

    def build(*_args: object, **_kwargs: object) -> Any:
        return pool

    monkeypatch.setattr(route_module, "_build_pool", build)
    return pool


def test_the_startup_probe_is_submitted_as_a_designated_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _connection as connection_module

    intents: list[bool] = []
    execute = connection_module.PostgresConnection.execute

    def recording(
        execution: connection_module.PostgresConnection,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[tuple[int, int]] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        intents.append(read_only)
        return execute(execution, sql, binds, document_reads, read_only=read_only)

    monkeypatch.setattr(connection_module.PostgresConnection, "execute", recording)
    _opened(monkeypatch, _pool())

    _open_runtime(PoolOptions(min_size=0))

    assert intents == [True]


def test_a_zero_minimum_and_on_demand_wait_for_nothing_and_still_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Neither retains capacity, so a native wait would either return having
    # proved nothing or establish a connection of its own and throw it away.
    for options in (PoolOptions(min_size=0), OnDemandOptions()):
        pool = _opened(monkeypatch, _pool())
        _open_runtime(options)
        assert pool.waits == []
        assert len(pool.checkouts) == 1
        assert pool.returned


def test_a_pool_that_will_not_open_fails_startup_at_the_open_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `open=False` then an explicit open, because the driver's implicit opening
    # is a deprecated default whose behavior is documented to change — so the
    # open is a phase of readiness with a failure of its own.
    class _Refusing(_FakePool):
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            super().__init__()

        def open(self) -> None:
            raise psycopg_pool.PoolTimeout("the pool would not open")

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", _Refusing)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions())

    assert failed.value.phase == "open"
    assert isinstance(failed.value.__cause__, psycopg_pool.PoolTimeout)


def test_a_minimum_that_is_not_reached_fails_at_its_own_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _opened(monkeypatch, _pool(wait_error=psycopg_pool.PoolTimeout("not filled")))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=2))

    assert failed.value.phase == "minimum_ready"
    assert pool.closes == 1


def test_a_configuration_every_connection_is_refused_under_is_named_rather_than_timed_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Filling happens on the pool's own background path, where an initialization
    # refusal is retried and logged where the waiting caller never sees it. A
    # bare "timed out" names nothing an operator can fix.
    from parallax.postgres import _route as route_module

    establishment = _establishment()
    refusal = IncompatibleSessionError("this connection's client encoding is 'LATIN1'")
    establishment.failed(refusal)
    pool = _pool(wait_error=psycopg_pool.PoolTimeout("not filled"))

    def build(*_args: object, **_kwargs: object) -> Any:
        return pool

    monkeypatch.setattr(route_module, "_build_pool", build)
    monkeypatch.setattr(route_module, "ConnectionEstablishment", lambda: establishment)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=1))

    assert failed.value.phase == "minimum_ready"
    assert failed.value.__cause__ is refusal
    assert "usable" in str(failed.value)


def test_a_source_that_authenticates_nothing_is_named_rather_than_timed_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same recorded-refusal channel carrying the other kind, and the wait
    # says which one it found: a credential no source would produce and a
    # session the codecs cannot run under are different things to fix. Startup
    # still spends its whole budget first — a refusal here is retried with
    # backoff rather than ending readiness on the spot.
    from parallax.postgres import _route as route_module

    establishment = _establishment()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    establishment.failed(refusal)
    pool = _pool(wait_error=psycopg_pool.PoolTimeout("not filled"))

    def build(*_args: object, **_kwargs: object) -> Any:
        return pool

    monkeypatch.setattr(route_module, "_build_pool", build)
    monkeypatch.setattr(route_module, "ConnectionEstablishment", lambda: establishment)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=1), Password("hunter2"))

    assert failed.value.phase == "minimum_ready"
    assert failed.value.__cause__ is refusal
    assert "authenticated" in str(failed.value)


def test_a_startup_acquisition_that_fails_carries_its_phase_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _opened(
        monkeypatch, _pool(checkout_error=psycopg_pool.PoolTimeout("no connection available"))
    )

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=0))

    assert failed.value.phase == "acquire"
    assert isinstance(failed.value.__cause__, ConnectionAcquisitionError)
    assert pool.closes == 1


@pytest.mark.parametrize(
    "row",
    [
        {**_PROBE_ROW, "ready": 0},
        {**_PROBE_ROW, "temporal_bound": "2026-01-01"},
        {**_PROBE_ROW, "document": "not a document"},
        {**_PROBE_ROW, "login_identity": ""},
        {**_PROBE_ROW, "login_identity": 7},
        {name: value for name, value in _PROBE_ROW.items() if name != "login_identity"},
    ],
)
def test_a_probe_that_does_not_read_back_what_it_asked_for_fails_startup(
    monkeypatch: pytest.MonkeyPatch, row: dict[str, object]
) -> None:
    connection = _FakeConnection(rows=[row])
    pool = _opened(monkeypatch, _pool(connection))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=0))

    assert failed.value.phase == "probe"
    # The probe scope is released on the way out rather than leaked.
    assert pool.returned == [connection]
    assert pool.closes == 1


@pytest.mark.parametrize(
    ("witness", "decoded", "names_the_loader"),
    [
        # What `extra_float_digits = 0` spells the Float64 witness as.
        ("float64_witness", 0.3, False),
        # The Float32 witness's shortest spelling parsed and then narrowed: what
        # a plain float loader reads, whatever the session setting.
        ("float32_witness", 7.038531308148791e-26, True),
    ],
)
def test_a_probe_that_reads_a_float_back_inexactly_names_what_rounds_it(
    monkeypatch: pytest.MonkeyPatch, witness: str, decoded: float, names_the_loader: bool
) -> None:
    connection = _FakeConnection(rows=[{**_PROBE_ROW, witness: decoded}])
    _opened(monkeypatch, _pool(connection))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=0))

    assert failed.value.phase == "probe"
    reason = str(failed.value)
    assert "extra_float_digits is at or below zero" in reason
    assert ("Float32 loader is not installed" in reason) is names_the_loader


def test_a_probe_scope_whose_release_cannot_be_confirmed_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A successful probe followed by an unconfirmed release is not a
    # ready runtime: the connection's fate is unknown and nothing else will
    # revisit it.
    pool = _opened(monkeypatch, _pool(putconn_error=RuntimeError("the return failed")))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=0))

    assert failed.value.phase == "release"
    assert isinstance(failed.value.cleanup_result, ReleaseUnconfirmed)
    assert failed.value.__cause__ is None
    assert pool.closes == 1


def test_readiness_shares_one_budget_that_is_never_restarted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A budget that stops the next phase from starting: it cannot interrupt a
    # native call in flight, and it does not begin a phase it cannot finish.
    from parallax.postgres import _startup as startup_module

    clock = iter([0.0, 0.0, 0.5, 99.0, 99.0, 99.0, 99.0])
    monkeypatch.setattr(startup_module, "monotonic", lambda: next(clock))
    _opened(monkeypatch, _pool())

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=1))

    assert failed.value.phase in {"acquire", "minimum_ready"}


def test_a_broken_startup_probe_is_replaced_within_the_one_startup_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The probe is a designated read and its context's first submission, so it
    # gets the same one replacement as any other — taken from what remains of
    # the startup budget, which nothing restarts.
    clock = _Clock(monkeypatch)
    broken = _FakeConnection(lost=_lost(), when_lost=lambda: setattr(clock, "now", 10.0))
    fresh = _FakeConnection()
    pool = _opened(monkeypatch, _pool(broken, fresh))

    runtime = _open_runtime(PoolOptions(min_size=0))

    assert runtime.login_identity == "runtime-login"
    assert pool.checkouts == [30.0, 20.0]
    assert broken.statements == fresh.statements == [PROBE_SQL]
    assert pool.returned == [broken, fresh]


def test_a_broken_startup_probe_past_its_budget_takes_no_replacement_and_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(monkeypatch)
    original = _lost()
    broken = _FakeConnection(lost=original, when_lost=lambda: setattr(clock, "now", 31.0))
    pool = _opened(monkeypatch, _pool(broken, _FakeConnection()))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=0))

    assert failed.value.phase == "probe"
    cause = failed.value.__cause__
    assert isinstance(cause, DatabaseError) and cause.__cause__ is original
    assert pool.checkouts == [30.0]
    assert _issues(failed.value.cleanup_result) == [("inspect", "suspect")]
    assert pool.closes == 1


# --------------------------------------------------------------------------- #
# Acquisition: what a checkout is allowed to become.                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("native", "reason"),
    [
        (psycopg_pool.PoolTimeout("waited"), "timeout"),
        (psycopg_pool.TooManyRequests("queued"), "queue_rejected"),
        (psycopg_pool.PoolClosed("closed"), "closed"),
        (psycopg.OperationalError("could not connect"), "unavailable"),
        (psycopg.ProgrammingError("invalid connection option"), "preparation_failed"),
        (CredentialResolutionError("RDS IAM token could not be generated"), "credentials_refused"),
    ],
)
def test_every_native_checkout_failure_maps_to_its_own_reason(
    native: Exception, reason: str
) -> None:
    # A credential refusal is in the table because an on-demand pool
    # establishes on the acquiring thread: what the source raised comes out of
    # the checkout itself rather than being read back off the record, so it is
    # classified here without the record being consulted at all.
    resource = _context(_pool(checkout_error=native))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == reason
    assert refused.value.__cause__ is native
    # Nothing was taken, so there is nothing to have cleaned up.
    assert resource.cleanup_result is None


def test_an_expired_budget_refuses_before_asking_the_pool_for_anything() -> None:
    pool = _pool()
    resource = _context(pool, deadline=monotonic() - 1.0)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert pool.checkouts == []


def test_a_timeout_names_the_initialization_refusal_on_record() -> None:
    # The pool retries an initialization refusal in the background, so the
    # waiting caller would otherwise get a bare timeout naming nothing to fix.
    establishment = _establishment()
    refusal = IncompatibleSessionError("this connection's DateStyle is 'German'")
    establishment.failed(refusal)
    pool = _pool(checkout_error=psycopg_pool.PoolTimeout("waited"))
    runtime = _runtime(pool)
    resource = PostgresConnectionContext(
        ((PostgresRoute("writer", pool, establishment), monotonic() + 5.0),),
        runtime._admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        None,
        expected_login=None,
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is refusal


def test_a_timeout_names_the_credential_refusal_on_record() -> None:
    # A retained pool resolves the credential on its own worker threads, so a
    # source that produces none reaches a waiting caller only by being on
    # record — and it is a reason of its own rather than a preparation that
    # failed, because nothing was ever offered to the server.
    establishment = _establishment()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    establishment.failed(refusal)
    pool = _pool(checkout_error=psycopg_pool.PoolTimeout("waited"))
    runtime = _runtime(pool)
    resource = PostgresConnectionContext(
        ((PostgresRoute("writer", pool, establishment), monotonic() + 5.0),),
        runtime._admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        None,
        expected_login=None,
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "credentials_refused"
    assert refused.value.__cause__ is refusal
    assert "authenticated" in str(refused.value)


def test_a_successful_initialization_clears_the_refusal_on_record() -> None:
    establishment = _establishment()
    establishment.failed(IncompatibleSessionError("earlier"))
    establishment(cast("Any", _Initializable()))
    assert establishment.last_failure is None


class _Initializable:
    """A connection whose initialization succeeds: the two settings and its own
    adapter map over psycopg's defaults."""

    def __init__(self) -> None:
        self.info = _Info()
        self.adapters = AdaptersMap(psycopg.adapters)


class _Info:
    encoding = "utf-8"

    def parameter_status(self, name: str) -> str | None:
        return "ISO, MDY" if name == "DateStyle" else None


def test_the_remaining_budget_is_what_the_native_checkout_is_given() -> None:
    pool = _pool()
    _context(pool, deadline=monotonic() + 2.0).__enter__()
    (given,) = pool.checkouts
    assert given is not None and 0.0 < given <= 2.0


def test_a_checkout_that_hands_over_a_connection_in_a_transaction_is_refused() -> None:
    # No modeled SQL runs on it and no unknown transaction is rolled back to
    # make it usable: an adapter invariant this broken is reported.
    connection = _FakeConnection(status=TransactionStatus.INTRANS)
    pool = _pool(connection)
    resource = _context(pool)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert connection.statements == []
    # The partial ownership is cleaned up, and a connection in this state is
    # disposed of rather than offered to the next caller.
    assert isinstance(resource.cleanup_result, Invalidated)
    assert connection.closes == 1


def test_a_late_native_success_is_released_rather_than_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The caller has already been waiting past what it asked for; its own
    # timeout handling is a better answer than work starting after the budget.
    # The budget is live when the checkout starts and spent when it returns,
    # which is the race a cooperative deadline can only lose.
    from parallax.postgres import _runtime as runtime_module

    connection = _FakeConnection()
    pool = _pool(connection)
    runtime = _runtime(pool)
    monkeypatch.setattr(runtime_module, "monotonic", lambda: 1e18)
    resource = PostgresConnectionContext(
        ((PostgresRoute("writer", pool, _establishment()), monotonic() + 5.0),),
        runtime._admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        None,
        expected_login=None,
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert connection.statements == []
    assert resource.cleanup_result == Returned()
    assert pool.returned == [connection]


def test_a_context_is_entered_exactly_once_and_a_failed_entry_spends_it() -> None:
    pool = _pool()
    resource = _context(pool)
    with resource, pytest.raises(RuntimeError):
        resource.__enter__()
    with pytest.raises(RuntimeError):
        resource.__enter__()

    failed = _context(_pool(checkout_error=psycopg_pool.PoolClosed("closed")))
    with pytest.raises(ConnectionAcquisitionError):
        failed.__enter__()
    with pytest.raises(RuntimeError):
        failed.__enter__()


def test_leaving_a_scope_revokes_the_execution_it_yielded() -> None:
    # Enforced by clearing the native reference, so a reference kept past the
    # exit executes nothing and — more importantly — RETAINS nothing.
    connection = _FakeConnection()
    resource = _context(_pool(connection))
    with resource as scoped:
        scoped.execute("select 1", [])
    with pytest.raises(RuntimeError, match="scope has ended"):
        scoped.execute("select 1", [])
    assert connection.statements == ["select 1"]


def test_a_refused_begin_disposes_of_its_session_and_later_work_takes_a_fresh_one() -> None:
    # The server refused the command and reports the session idle, but the
    # driver still counts the context that failed to enter, so the session is
    # disposed of rather than reset or offered for reuse; the next acquisition
    # runs on another physical connection.
    refused = _FakeConnection(begin_error=psycopg.errors.SyntaxError("syntax error"))
    fresh = _FakeConnection(rows=[])
    pool = _pool(refused, fresh)
    ran: list[str] = []

    def never_runs(_port: DatabaseConnection) -> None:
        ran.append("body")

    def reads(port: DatabaseConnection) -> list[Row]:
        return port.execute("select 1", [])

    first = _context(pool)
    with first as scoped:
        outcome = scoped.transaction(never_runs, isolation="serializable", access_mode="read_only")
    second = _context(pool)
    with second as scoped:
        assert scoped.transaction(reads) == Committed([])

    assert isinstance(outcome, BeginFailed)
    assert ran == []
    assert refused.status == TransactionStatus.IDLE
    assert refused.characteristics == [
        ("isolation_level", psycopg.IsolationLevel.SERIALIZABLE),
        ("read_only", True),
    ]
    assert isinstance(first.cleanup_result, Invalidated)
    assert [(issue.phase, issue.code) for issue in first.cleanup_result.issues] == [
        ("inspect", "suspect")
    ]
    assert refused.closes == 1
    assert fresh.statements == ["BEGIN", "select 1", "COMMIT"]
    assert second.cleanup_result == Returned()
    assert pool.returned == [refused, fresh]


def test_the_runtime_declares_one_writer_route_serving_every_read_only_level() -> None:
    runtime = _runtime(_pool())

    assert dict(runtime.routes) == {"writer": RouteCapabilities.every_level()}
    assert runtime.routes["writer"].read_only_isolation == frozenset(
        {"read_committed", "repeatable_read", "serializable"}
    )
    with pytest.raises(TypeError):
        cast("Any", runtime.routes)["reader"] = RouteCapabilities(frozenset())


def test_a_writer_only_acquisition_selects_the_writer_once_entered() -> None:
    pool = _pool()
    resource = _runtime(pool).login_source().new_context("writer_only")

    assert resource.selection is None
    with resource:
        assert resource.selection == RouteSelection("writer")
    assert resource.selection == RouteSelection("writer")


@pytest.mark.parametrize("policy", ["reader_only", "reader_preferred"])
def test_a_writer_only_runtime_refuses_to_build_a_reader_context(policy: str) -> None:
    # Core resolves every policy against the declared routes first, so being
    # asked for one this runtime cannot serve is a caller defect, refused before
    # anything is taken.
    pool = _pool()

    with pytest.raises(ValueError, match="does not serve"):
        _runtime(pool).login_source().new_context(cast("Any", policy))

    assert pool.checkouts == []


def test_a_refused_entry_reports_the_writer_on_the_context_and_the_failure_alike() -> None:
    pool = _pool(checkout_error=psycopg_pool.PoolTimeout("waited"))
    resource = _login_context(_runtime(pool))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert refused.value.selection == RouteSelection("writer")
    assert resource.selection == RouteSelection("writer")


def test_authority_binding_and_context_creation_acquire_nothing() -> None:
    pool = _pool()
    runtime = _runtime(pool)

    source = runtime.principal_source(PostgresRole("tenant_reader"))
    first = source.new_context("writer_only")
    second = source.new_context("writer_only")

    assert first is not second
    assert pool.checkouts == []
    assert not hasattr(runtime, "connection")


def test_role_installation_preserves_a_control_flow_exception() -> None:
    connection = _FakeConnection(execute_error=KeyboardInterrupt())
    resource = _context(_pool(connection), role=PostgresRole("tenant_reader"))

    with pytest.raises(KeyboardInterrupt):
        resource.__enter__()

    assert isinstance(resource.cleanup_result, Invalidated)
    assert connection.closes == 1
    assert "RESET ROLE" not in connection.statements


def test_admission_is_checked_again_after_successful_role_installation() -> None:
    connection = _FakeConnection()
    calls = 0

    def admit(_deadline: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionAcquisitionError("closed during authorization", reason="closed")

    pool = _pool(connection)
    resource = _context(pool, admit=admit, role=PostgresRole("tenant_reader"))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "closed"
    assert calls == 2
    assert connection.statements[-1] == "RESET ROLE"
    assert resource.cleanup_result == Returned()
    assert pool.returned == [connection]


def test_role_restoration_failure_forces_disposal_and_is_reported() -> None:
    connection = _FakeConnection(reset_error=RuntimeError("reset denied"))
    pool = _pool(connection)
    resource = _context(pool, role=PostgresRole("tenant_reader"))

    with resource:
        pass

    result = resource.cleanup_result
    assert isinstance(result, Invalidated)
    assert [(issue.phase, issue.code) for issue in result.issues] == [
        ("restore", "authorization-restore-failed")
    ]
    assert connection.closes == 1
    assert pool.returned == [connection]


# --------------------------------------------------------------------------- #
# First use: one replacement of a broken connection, inside the one lease.     #
# --------------------------------------------------------------------------- #


def _lost(message: str = "server closed the connection unexpectedly") -> psycopg.Error:
    return psycopg.OperationalError(message)


class _Clock:
    """A monotonic clock a proof moves by hand, read by every module that keeps time."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, now: float = 0.0) -> None:
        from parallax.postgres import _context as context_module
        from parallax.postgres import _runtime as runtime_module
        from parallax.postgres import _startup as startup_module

        self.now = now
        monkeypatch.setattr(context_module, "monotonic", lambda: self.now)
        monkeypatch.setattr(runtime_module, "monotonic", lambda: self.now)
        monkeypatch.setattr(startup_module, "monotonic", lambda: self.now)


def _admitted(_deadline: float) -> None:
    return


def _issues(result: object) -> list[tuple[str, str]]:
    assert isinstance(result, Returned | Invalidated | ReleaseUnconfirmed)
    return [(issue.phase, issue.code) for issue in result.issues]


def test_a_broken_first_designated_read_is_submitted_once_more_on_a_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same prepared statement reaches the replacement: bind adaptation ran
    # once, and the integer array it built is the one object both sessions were
    # handed. The original is disposed of and handed back before the
    # replacement is asked for, and no cleanup is published while in use.
    from parallax.postgres import _connection as connection_module

    adaptations: list[Sequence[object]] = []
    adapt = connection_module.adapt_binds

    def counted(binds: Sequence[object]) -> list[object]:
        adaptations.append(binds)
        return adapt(binds)

    monkeypatch.setattr(connection_module, "adapt_binds", counted)
    broken = _FakeConnection(lost=_lost())
    fresh = _FakeConnection(rows=[{"id": 1}])
    pool = _pool(broken, fresh)
    resource = _context(pool)

    with resource as scoped:
        rows = scoped.execute("select id from t where id = any(?)", [[1, 2]], read_only=True)
        assert resource.cleanup_result is None
        assert pool.returned == [broken]

    assert rows == [(1,)]
    assert len(adaptations) == 1
    assert broken.statements == fresh.statements == ["select id from t where id = any(%s)"]
    (sent,) = broken.binds
    assert fresh.binds == [sent]
    assert sent is not None and sent[0] == [1, 2]
    assert len(pool.checkouts) == 2
    assert (broken.closes, fresh.closes) == (1, 0)
    assert pool.returned == [broken, fresh]
    assert resource.cleanup_result == Returned()


def test_a_replaced_read_pipeline_that_breaks_again_reports_its_own_failure() -> None:
    second = _lost("the replacement was lost too")
    pool = _pool(_FakeConnection(lost=_lost()), _FakeConnection(lost=second), _FakeConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(DatabaseError) as failed:
        _read_pipeline(scoped)

    assert failed.value.__cause__ is second
    assert len(pool.checkouts) == 2


def _read(port: DatabaseConnection) -> object:
    return port.execute("select 1", [], read_only=True)


def _row_producing(port: DatabaseConnection) -> object:
    return port.execute("insert into t (v) values (1) returning id", [])


def _count_only(port: DatabaseConnection) -> object:
    return port.execute_write("update t set v = 1", [])


def _read_pipeline(port: DatabaseConnection) -> object:
    return port.execute_pipeline((PipelineStatement("select 1"),), read_only=True)


def _began(port: DatabaseConnection) -> object:
    return port.transaction(_read)


class _NamedCheckViolation(psycopg.errors.CheckViolation):
    @property
    def diag(self) -> Any:
        return type("Diagnostic", (), {"constraint_name": "pxc_t_window"})()


@pytest.mark.parametrize(
    ("refusal", "category"),
    [
        (_NamedCheckViolation("check failed"), "constraintViolation"),
        (psycopg.errors.DeadlockDetected("deadlock detected"), "deadlock"),
        (psycopg.errors.AdminShutdown("terminating connection"), None),
    ],
)
def test_a_refusal_on_a_healthy_connection_is_never_a_reason_to_replace_it(
    refusal: psycopg.Error, category: str | None
) -> None:
    # The SQLSTATE grants nothing, not even a connection-loss code: only a
    # connection the driver reports closed does, and this one is open. The
    # failure keeps its classification and its structured diagnostics.
    connection = _FakeConnection(execute_error=refusal)
    pool = _pool(connection, _FakeConnection())

    with _context(pool) as scoped, pytest.raises(DatabaseError) as failed:
        scoped.execute("select 1", [], read_only=True)

    assert failed.value.category == category
    assert failed.value.__cause__ is refusal
    if category == "constraintViolation":
        assert failed.value.constraint_name == "pxc_t_window"
    assert len(pool.checkouts) == 1


@pytest.mark.parametrize(
    "first",
    [_read, _row_producing, _count_only, _read_pipeline, _began],
    ids=["read", "row-producing", "count-only", "read-pipeline", "begin"],
)
def test_a_connection_lost_after_the_first_submission_is_not_replaced(
    first: Callable[[DatabaseConnection], object],
) -> None:
    # Whatever the first submission was, once it answered the opportunity is
    # gone: a later read designated as one cannot earn it back.
    connection = _FakeConnection(rows=[{"n": 1}])
    pool = _pool(connection, _FakeConnection())

    with _context(pool) as scoped:
        first(scoped)
        connection.lost = _lost()
        with pytest.raises(DatabaseError):
            scoped.execute("select 2", [], read_only=True)

    assert len(pool.checkouts) == 1


def test_a_child_read_after_its_root_has_no_opportunity_to_claim() -> None:
    # A single child fetch is a designated read through the same seam as its
    # root, carrying the keys the root just gathered; the root already spent
    # the lease's one opportunity, and designation does not reopen it.
    connection = _FakeConnection(rows=[{"id": 3}, {"id": 4}])
    pool = _pool(connection, _FakeConnection())

    with _context(pool) as scoped:
        keys = [row[0] for row in scoped.execute("select id from root", [], read_only=True)]
        connection.lost = _lost()
        with pytest.raises(DatabaseError):
            scoped.execute("select * from child where root_id = any(?)", [keys], read_only=True)

    assert connection.binds[-1] == [[3, 4]]
    assert len(pool.checkouts) == 1
    assert pool.returned == [connection]


def test_a_fatal_first_submission_spends_the_opportunity_and_propagates_as_itself() -> None:
    connection = _FakeConnection(execute_error=KeyboardInterrupt())
    pool = _pool(connection, _FakeConnection())

    with _context(pool) as scoped:
        with pytest.raises(KeyboardInterrupt):
            scoped.execute("select 1", [], read_only=True)
        connection.execute_error = None
        connection.lost = _lost()
        with pytest.raises(DatabaseError):
            scoped.execute("select 2", [], read_only=True)

    assert len(pool.checkouts) == 1


def _lost_while_draining(interrupt: BaseException) -> psycopg.Error:
    # Psycopg answers an interrupt during a wait by cancelling and draining the
    # statement; a session that breaks during the drain raises its driver
    # failure in the interrupt's place, carrying the interrupt as context.
    lost = _lost()
    lost.__context__ = interrupt
    return lost


@pytest.mark.parametrize("first", [_read, _began], ids=["read", "begin"])
@pytest.mark.parametrize("interrupted", [KeyboardInterrupt, SystemExit])
def test_an_interrupt_a_broken_first_submission_displaced_propagates_and_is_not_replaced(
    first: Callable[[DatabaseConnection], object], interrupted: type[BaseException]
) -> None:
    interrupt = interrupted()
    broken = _FakeConnection(lost=_lost_while_draining(interrupt))
    pool = _pool(broken, _FakeConnection())
    resource = _context(pool)

    with resource as scoped:
        with pytest.raises(interrupted) as raised:
            first(scoped)
        assert raised.value is interrupt
        broken.lost = _lost_while_draining(KeyboardInterrupt())
        with pytest.raises(DatabaseError):
            scoped.execute("select 2", [], read_only=True)

    assert len(pool.checkouts) == 1
    assert pool.returned == [broken]


def test_an_interrupt_a_broken_role_installation_displaced_propagates_and_is_not_replaced() -> None:
    interrupt = KeyboardInterrupt()
    broken = _FakeConnection(lost=_lost_while_draining(interrupt))
    pool = _pool(broken, _FakeConnection())
    resource = _context(pool, role=PostgresRole("tenant_reader"))

    with pytest.raises(KeyboardInterrupt) as raised:
        resource.__enter__()

    assert raised.value is interrupt
    assert len(pool.checkouts) == 1
    assert pool.returned == [broken]


def test_an_interrupt_already_being_handled_is_not_one_the_failure_displaced() -> None:
    # Work run while an earlier interrupt is handled inherits it as context
    # without the submission having been interrupted, so replacement proceeds.
    broken = _FakeConnection(lost=_lost())
    fresh = _FakeConnection(rows=[{"n": 1}])
    pool = _pool(broken, fresh)

    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        with _context(pool) as scoped:
            rows = scoped.execute("select 1", [], read_only=True)

    assert rows == [(1,)]
    assert len(pool.checkouts) == 2
    assert pool.returned == [broken, fresh]


def test_a_replacement_that_also_breaks_reports_its_own_failure_and_is_not_replaced() -> None:
    first, second = _lost("the first session is gone"), _lost("the second session is gone")
    broken = _FakeConnection(lost=first)
    also_broken = _FakeConnection(lost=second)
    pool = _pool(broken, also_broken, _FakeConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(DatabaseError) as failed:
        scoped.execute("select 1", [], read_only=True)

    assert failed.value.__cause__ is second
    assert second.__context__ is None
    assert len(pool.checkouts) == 2
    assert pool.returned == [broken, also_broken]
    assert _issues(resource.cleanup_result) == [("inspect", "not-idle")]


def test_an_unavailable_replacement_preserves_the_original_failure_and_its_cleanup() -> None:
    # The original was disposed of and handed back, and that is what the
    # context reports once it exits — published then, and only then.
    original = _lost()
    broken = _FakeConnection(lost=original)
    pool = _pool(broken, _FakeConnection())
    broken.when_lost = lambda: setattr(pool, "checkout_error", psycopg_pool.PoolTimeout("waited"))
    resource = _context(pool)
    ran: list[str] = []

    def body(_port: DatabaseConnection) -> None:
        ran.append("body")

    with resource as scoped:
        outcome = scoped.transaction(body, isolation="serializable")
        assert resource.cleanup_result is None
        with pytest.raises(RuntimeError, match="could not be replaced"):
            scoped.execute("select 1", [])

    assert isinstance(outcome, BeginFailed)
    assert outcome.error.__cause__ is original
    assert ran == []
    assert len(pool.checkouts) == 2
    # Disposal ended its use, so the characteristics were never reset on it.
    assert broken.characteristics == [
        ("isolation_level", psycopg.IsolationLevel.SERIALIZABLE),
        ("read_only", None),
    ]
    assert (broken.closes, pool.returned) == (1, [broken])
    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]


def test_a_replacement_that_is_not_idle_is_given_back_and_its_cleanup_is_what_is_reported() -> None:
    original = _lost()
    broken = _FakeConnection(lost=original)
    busy = _FakeConnection(status=TransactionStatus.INTRANS)
    pool = _pool(broken, busy)
    resource = _context(pool)

    with resource as scoped, pytest.raises(DatabaseError) as failed:
        scoped.execute("select 1", [], read_only=True)

    assert failed.value.__cause__ is original
    assert busy.statements == []
    assert pool.returned == [broken, busy]
    assert _issues(resource.cleanup_result) == [("inspect", "not-idle")]
    assert busy.closes == 1


def test_a_disposal_that_failed_ends_replacement_and_is_reported_without_repeating_it() -> None:
    broken = _FakeConnection(lost=_lost(), close_error=RuntimeError("close failed"))
    pool = _pool(broken, _FakeConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(DatabaseError):
        scoped.execute("select 1", [], read_only=True)

    result = resource.cleanup_result
    assert isinstance(result, ReleaseUnconfirmed)
    assert _issues(result) == [("inspect", "suspect"), ("dispose", "close-failed")]
    assert (len(pool.checkouts), pool.handoffs, broken.closes) == (1, 0, 1)
    resource.__exit__(None, None, None)
    assert resource.cleanup_result is result
    assert broken.closes == 1


def test_a_handoff_that_failed_is_neither_retried_nor_followed_by_a_close_or_a_checkout() -> None:
    broken = _FakeConnection(lost=_lost())
    pool = _pool(broken, _FakeConnection(), putconn_error=RuntimeError("the return failed"))
    resource = _context(pool)

    with resource as scoped:
        with pytest.raises(DatabaseError):
            scoped.execute("select 1", [], read_only=True)
        saved = scoped

    assert _issues(resource.cleanup_result) == [
        ("inspect", "suspect"),
        ("return", "handoff-failed"),
    ]
    assert (len(pool.checkouts), pool.handoffs, broken.closes) == (1, 1, 1)
    with pytest.raises(RuntimeError, match="scope has ended"):
        saved.execute("select 1", [])


def test_a_control_flow_exception_while_replacing_keeps_its_precedence() -> None:
    # Interrupted while taking the replacement: the interrupt propagates, and
    # the disposal already established is what the exit reports.
    broken = _FakeConnection(lost=_lost())
    pool = _pool(broken, _FakeConnection())
    broken.when_lost = lambda: setattr(pool, "checkout_error", KeyboardInterrupt())
    resource = _context(pool)

    with resource as scoped, pytest.raises(KeyboardInterrupt):
        scoped.execute("select 1", [], read_only=True)

    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]
    assert pool.returned == [broken]


def test_a_disposal_interrupted_part_way_is_never_attempted_again() -> None:
    # A release that does not return established nothing to report, and the
    # slot it emptied leaves the exit nothing to release a second time.
    broken = _FakeConnection(lost=_lost(), close_error=KeyboardInterrupt())
    pool = _pool(broken, _FakeConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(KeyboardInterrupt):
        scoped.execute("select 1", [], read_only=True)

    assert resource.cleanup_result is None
    assert (broken.closes, pool.handoffs, len(pool.checkouts)) == (1, 0, 1)


def test_a_replacement_spends_only_what_remains_of_the_original_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(monkeypatch)
    broken = _FakeConnection(lost=_lost())
    pool = _pool(broken, _FakeConnection(rows=[]))
    resource = _context(pool, deadline=10.0, admit=_admitted)

    with resource as scoped:
        clock.now = 4.0
        scoped.execute("select 1", [], read_only=True)

    assert pool.checkouts == [10.0, 6.0]


def test_no_replacement_is_asked_for_once_the_deadline_has_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The budget gates the next checkout; it never interrupts admitted work,
    # which may still run after it has expired.
    clock = _Clock(monkeypatch)
    original = _lost()
    broken = _FakeConnection(lost=original)
    pool = _pool(broken, _FakeConnection())
    resource = _context(pool, deadline=10.0, admit=_admitted)

    with resource as scoped, pytest.raises(DatabaseError) as failed:
        clock.now = 11.0
        scoped.execute("select 1", [], read_only=True)

    assert failed.value.__cause__ is original
    assert pool.checkouts == [10.0]

    healthy = _FakeConnection(rows=[{"n": 1}])
    late = _context(_pool(healthy), deadline=12.0, admit=_admitted)
    with late as scoped:
        clock.now = 99.0
        assert scoped.execute("select 1", [], read_only=True) == [(1,)]


def test_each_new_owner_has_a_budget_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock(monkeypatch)
    broken = _FakeConnection(lost=_lost())
    pool = _pool(_FakeConnection(), broken, _FakeConnection(rows=[]))
    runtime = _runtime(pool, acquire_timeout=3.0)

    with _login_context(runtime):
        clock.now = 50.0
    with _login_context(runtime) as scoped:
        clock.now = 51.0
        scoped.execute("select 1", [], read_only=True)

    assert pool.checkouts == [3.0, 3.0, 2.0]


def test_a_broken_role_installation_is_replaced_and_still_rechecks_admission() -> None:
    broken = _FakeConnection(lost=_lost())
    fresh = _FakeConnection(rows=[])
    pool = _pool(broken, fresh)
    admissions: list[float] = []
    resource = _context(pool, admit=admissions.append, role=PostgresRole("tenant_reader"))

    with resource as scoped:
        scoped.execute("select current_user", [])

    assert len(broken.statements) == 1 and "SET ROLE" in broken.statements[0]
    assert "SET ROLE" in fresh.statements[0] and "tenant_reader" in fresh.statements[0]
    assert fresh.statements[1:] == ["select current_user", "RESET ROLE"]
    assert len(admissions) == 2
    assert pool.returned == [broken, fresh]
    assert resource.cleanup_result == Returned()


def test_final_admission_after_a_replaced_role_installation_can_still_refuse() -> None:
    broken = _FakeConnection(lost=_lost())
    fresh = _FakeConnection()
    calls = 0

    def admit(_deadline: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionAcquisitionError("closed during authorization", reason="closed")

    pool = _pool(broken, fresh)
    resource = _context(pool, admit=admit, role=PostgresRole("tenant_reader"))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "closed"
    assert fresh.statements[-1] == "RESET ROLE"
    assert pool.returned == [broken, fresh]
    assert resource.cleanup_result == Returned()


def test_a_role_installation_that_cannot_be_replaced_is_an_authorization_failure() -> None:
    original = _lost()
    broken = _FakeConnection(lost=original)
    pool = _pool(broken, _FakeConnection())
    broken.when_lost = lambda: setattr(pool, "checkout_error", psycopg_pool.PoolTimeout("waited"))
    resource = _context(pool, role=PostgresRole("tenant_reader"))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.__cause__ is original
    assert pool.returned == [broken]
    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]


def test_a_replaced_role_installation_that_is_refused_reports_its_own_refusal() -> None:
    refusal = psycopg.errors.InsufficientPrivilege("permission denied to set role")
    broken = _FakeConnection(lost=_lost())
    refusing = _FakeConnection(execute_error=refusal)
    pool = _pool(broken, refusing)
    resource = _context(pool, role=PostgresRole("tenant_reader"))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.__cause__ is refusal
    assert pool.returned == [broken, refusing]
    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]
    assert "RESET ROLE" not in refusing.statements


def test_a_role_refused_on_a_healthy_connection_is_not_replaced() -> None:
    connection = _FakeConnection(
        execute_error=psycopg.errors.InsufficientPrivilege("permission denied to set role")
    )
    pool = _pool(connection, _FakeConnection())

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _context(pool, role=PostgresRole("tenant_reader")).__enter__()

    assert refused.value.reason == "authorization_failed"
    assert len(pool.checkouts) == 1


def test_an_installed_role_spends_the_opportunity_before_execution() -> None:
    connection = _FakeConnection(rows=[])
    pool = _pool(connection, _FakeConnection())

    with _context(pool, role=PostgresRole("tenant_reader")) as scoped:
        connection.lost = _lost()
        outcome = scoped.transaction(_read)

    assert isinstance(outcome, BeginFailed)
    assert len(pool.checkouts) == 1


def test_an_ordered_write_spends_the_opportunity_however_it_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Completed, interrupted and reported as a result, and escaping: none is
    # ever resubmitted, and each leaves nothing for a later read to claim.
    def lose(call: int) -> None:
        if call == 1:
            raise psycopg.OperationalError("consuming input failed")

    def interrupt(call: int) -> None:
        if call == 1:
            raise KeyboardInterrupt

    for on_fetch, escapes in ((None, False), (lose, False), (interrupt, True)):
        server = Server()
        if on_fetch is not None:
            server.on_fetch = on_fetch
        with native_session(monkeypatch, server) as native:
            pool = _pool(cast("Any", native))
            scope = _context(pool)
            with scope as facade:
                if escapes:
                    with pytest.raises(KeyboardInterrupt):
                        facade._ordered_writes((Statement("update a set v = 1"),))
                else:
                    facade._ordered_writes((Statement("update a set v = 1"),))
                assert scope._first_send_state == "spent"
            assert len(pool.checkouts) == 1


def test_empty_ordered_work_submits_nothing_and_leaves_the_opportunity_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The port's ordered-write contract takes nonempty input; an empty batch
    # here is the adapter's private no-submission guard, answering complete.
    server = Server()
    with native_session(monkeypatch, server) as native:
        scope = _context(_pool(cast("Any", native)))
        with scope as facade:
            assert facade._ordered_writes(()) == OrderedWriteResultComplete(())
            assert facade.execute_pipeline(()) == []
            assert scope._first_send_state == "available"
        assert server.sent == []
        with pytest.raises(RuntimeError, match="scope has ended"):
            facade._ordered_writes(())
        with pytest.raises(RuntimeError, match="scope has ended"):
            facade.execute_pipeline(())


# --------------------------------------------------------------------------- #
# Release: what a cleanup result is allowed to claim.                          #
# --------------------------------------------------------------------------- #


def test_an_idle_untrusted_free_connection_is_offered_for_reuse() -> None:
    connection = _FakeConnection()
    pool = _pool(connection)

    result = release(pool, cast("Any", connection), suspect=False)

    assert result == Returned()
    assert connection.closes == 0
    assert pool.returned == [connection]


def test_an_execution_that_declared_the_connection_suspect_disposes_of_it_first() -> None:
    # Disposal BEFORE the handoff, and the handoff still happens: disposal alone
    # would leak the capacity, and a handoff alone would offer a connection
    # nothing may reuse.
    connection = _FakeConnection()
    pool = _pool(connection)

    result = release(pool, cast("Any", connection), suspect=True)

    assert isinstance(result, Invalidated)
    assert [(issue.phase, issue.code) for issue in result.issues] == [("inspect", "suspect")]
    assert connection.closes == 1
    assert pool.returned == [connection]


def test_a_connection_whose_state_cannot_be_read_is_disposed_of() -> None:
    connection = _FakeConnection(status_error=RuntimeError("the state is gone"))
    pool = _pool(connection)

    result = release(pool, cast("Any", connection), suspect=False)

    assert isinstance(result, Invalidated)
    assert [issue.code for issue in result.issues] == ["state-unreadable"]
    assert connection.closes == 1


def test_a_connection_that_is_not_idle_is_disposed_of_rather_than_repaired() -> None:
    connection = _FakeConnection(status=TransactionStatus.INERROR)
    pool = _pool(connection)

    result = release(pool, cast("Any", connection), suspect=False)

    assert isinstance(result, Invalidated)
    assert [issue.code for issue in result.issues] == ["not-idle"]
    assert connection.statements == []


@pytest.mark.parametrize(
    "connection",
    [
        _FakeConnection(),
        _FakeConnection(status=TransactionStatus.INERROR),
        _FakeConnection(status_error=RuntimeError("state unavailable")),
    ],
)
def test_unsafe_principal_release_skips_role_restoration(connection: _FakeConnection) -> None:
    result = release(
        _pool(connection),
        cast("Any", connection),
        suspect=connection.status == TransactionStatus.IDLE and connection.status_error is None,
        restore_role=True,
    )

    assert isinstance(result, Invalidated)
    assert "RESET ROLE" not in connection.statements


def test_a_failed_disposal_does_not_fall_back_to_returning_a_suspect_connection() -> None:
    # Balancing the accounting is not worth offering the next caller a session
    # nothing can vouch for, and a closed flag after a failed close establishes
    # no disposal.
    connection = _FakeConnection(close_error=RuntimeError("close failed"))
    pool = _pool(connection)

    result = release(pool, cast("Any", connection), suspect=True)

    assert isinstance(result, ReleaseUnconfirmed)
    assert [issue.code for issue in result.issues] == ["suspect", "close-failed"]
    assert pool.returned == []


def test_a_failed_handoff_is_neither_retried_nor_followed_by_a_close() -> None:
    # A native return that raised may still have handed the connection to
    # another caller, so retrying it or closing afterwards risks destroying
    # somebody else's session.
    connection = _FakeConnection()
    pool = _pool(connection, putconn_error=RuntimeError("the return failed"))

    result = release(pool, cast("Any", connection), suspect=False)

    assert isinstance(result, ReleaseUnconfirmed)
    assert [(issue.phase, issue.code) for issue in result.issues] == [("return", "handoff-failed")]
    assert connection.closes == 0


def test_a_cleanup_issue_carries_a_detached_diagnostic_and_no_live_object() -> None:
    connection = _FakeConnection(status=TransactionStatus.INTRANS)
    result = release(_pool(connection), cast("Any", connection), suspect=False)

    (issue,) = result.issues
    assert isinstance(issue.diagnostic.message, str)
    assert issue.diagnostic.qualified_type.endswith("_Condition")
    assert not hasattr(issue.diagnostic, "__traceback__")


def test_a_release_unconfirmed_result_must_name_at_least_one_issue() -> None:
    with pytest.raises(ValueError, match="at least one cleanup issue"):
        ReleaseUnconfirmed(())


def _ordered_write_scope(
    monkeypatch: pytest.MonkeyPatch, server: Server
) -> tuple[OrderedWriteResult, Any, Any, psycopg.Connection[TupleRow]]:
    """One acquisition that presents a single ordered write, and what releasing
    it established."""
    with native_session(monkeypatch, server) as native:
        pool = _pool(cast("Any", native))
        scope = _context(pool)
        with scope as facade:
            result = facade._ordered_writes((Statement("update a set v = 1"),))
        return result, scope.cleanup_result, pool, native


def test_an_interrupted_ordered_write_disposes_of_its_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server()

    def lose(call: int) -> None:
        if call == 1:
            raise psycopg.OperationalError("consuming input failed")

    server.on_fetch = lose

    result, cleanup, pool, native = _ordered_write_scope(monkeypatch, server)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert isinstance(cleanup, Invalidated)
    assert [(issue.phase, issue.code) for issue in cleanup.issues] == [("inspect", "suspect")]
    assert native.closed
    assert pool.returned == [native]


def test_a_completed_ordered_write_leaves_its_connection_reusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, cleanup, pool, native = _ordered_write_scope(monkeypatch, Server())

    assert result == OrderedWriteResultComplete((1,))
    assert cleanup == Returned()
    assert pool.returned == [native]


# --------------------------------------------------------------------------- #
# Admission and shutdown.                                                      #
# --------------------------------------------------------------------------- #


def test_close_is_idempotent_and_permanent() -> None:
    pool = _pool()
    runtime = _runtime(pool)

    runtime.close()
    runtime.close()

    assert pool.closes == 1
    with pytest.raises(ConnectionAcquisitionError) as refused:
        _login_context(runtime).__enter__()
    assert refused.value.reason == "closed"


def test_a_scope_admitted_before_a_close_may_still_finish() -> None:
    # Admission is decided once, immediately before the connection is handed
    # over: later work in an admitted scope uses what it was given, including
    # statements it has not issued yet.
    connection = _FakeConnection()
    pool = _pool(connection)
    runtime = _runtime(pool)

    with _login_context(runtime) as scoped:
        runtime.close()
        scoped.execute("select 1", [])

    assert connection.statements == ["select 1"]
    assert pool.returned == [connection]


def test_a_native_close_problem_is_reported_rather_than_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Close is what a caller runs while unwinding; a handle that refused to
    # close would leave them nothing better to do. So the problem leaves as a
    # report on the restricted resource logger — carrying the phase, the code
    # and fixed text, and nothing the native failure said — rather than as an
    # exception, and a close that reported nothing would be a silently lost
    # runtime.
    runtime = _runtime(_pool(close_error=RuntimeError("connection to host=secret refused")))

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME):
        runtime.close()

    (record,) = caplog.records
    assert record.name == RESOURCE_LOGGER_NAME
    assert "return/handoff-failed" in record.getMessage()
    assert "secret" not in record.getMessage()
    assert record.exc_info is None


def test_the_ordinary_acquisition_budget_comes_from_the_configured_timeout() -> None:
    pool = _pool()
    runtime = _runtime(pool, acquire_timeout=3.0)
    with _login_context(runtime):
        pass
    (given,) = pool.checkouts
    assert given is not None and 0.0 < given <= 3.0


def test_a_runtime_answers_the_dialect_its_statements_are_spelled_in() -> None:
    assert _runtime(_pool()).dialect.name == "postgres"


def test_login_identity_is_unavailable_before_startup_completion() -> None:
    runtime = _runtime(_pool())

    with pytest.raises(RuntimeError, match="not completed startup"):
        _ = runtime.login_identity


def test_startup_completion_installs_the_login_exactly_once() -> None:
    runtime = _runtime(_pool())

    runtime._complete_startup(  # pyright: ignore[reportPrivateUsage] - direct startup state pin
        "first-login"
    )

    assert runtime.login_identity == "first-login"
    with pytest.raises(RuntimeError, match="already completed startup"):
        runtime._complete_startup(  # pyright: ignore[reportPrivateUsage] - direct startup state pin
            "second-login"
        )


@pytest.mark.parametrize(
    ("options", "native"),
    [(PoolOptions(), "ConnectionPool"), (OnDemandOptions(), "NullConnectionPool")],
    ids=["retaining", "on-demand"],
)
def test_neither_native_pool_is_given_a_check_to_run_at_checkout(
    monkeypatch: pytest.MonkeyPatch, options: Any, native: str
) -> None:
    # A checkout hands over what the pool holds without a round trip; a
    # connection that broke while idle is found by its first submission.
    from parallax.postgres import _route as route_module

    configured: list[dict[str, object]] = []

    class _Recording(_FakePool):
        def __init__(self, *_args: object, **kwargs: object) -> None:
            super().__init__()
            configured.append(kwargs)

        def open(self) -> None:
            return

    monkeypatch.setattr(psycopg_pool, native, _Recording)
    establishment = _establishment()
    route_module._build_pool(  # pyright: ignore[reportPrivateUsage] - the module-private pool builder is this test's subject
        PostgresEndpoint("", credentials=DRIVER_MANAGED, pool=options),
        "reader",
        15.0,
        5,
        establishment,
    )
    (kwargs,) = configured
    assert "check" not in kwargs
    assert kwargs["configure"] is establishment
    # Every dial goes through the route's own observed class, and the pool is
    # named for its route so the driver's own warnings say which one they met.
    assert kwargs["connection_class"] is establishment.connection_class
    assert kwargs["name"] == "parallax-reader"


def test_a_probe_that_answers_more_than_one_row_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(rows=[dict(_PROBE_ROW), dict(_PROBE_ROW)])
    _opened(monkeypatch, _pool(connection))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=0))

    assert failed.value.phase == "probe"
    assert str(failed.value) == (
        "database-startup-failed: the startup probe returned 2 rows rather than one"
    )


def test_a_probe_that_cannot_run_fails_startup_with_the_failure_as_its_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("the statement failed")
    _opened(monkeypatch, _pool(_FakeConnection(execute_error=failure)))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=0))

    assert failed.value.phase == "probe"
    assert str(failed.value) == (
        "database-startup-failed: "
        "the database runtime's startup probe did not return what it asked for"
    )
    assert failed.value.__cause__ is failure


def test_a_control_flow_exception_in_the_probe_keeps_its_own_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An interpreter being torn down is not a runtime that failed to become
    # ready. Translating one would hand a caller who interrupted the process an
    # ordinary startup error it might catch and carry on from, so the fatal and
    # control-flow exceptions propagate as themselves — after the same release
    # every other probe failure reaches.
    connection = _FakeConnection(execute_error=KeyboardInterrupt())
    pool = _opened(monkeypatch, _pool(connection))

    with pytest.raises(KeyboardInterrupt):
        _open_runtime(PoolOptions(min_size=0))

    assert pool.returned == [connection]
    assert pool.closes == 1


def test_an_exit_whose_revocation_fails_still_gives_the_connection_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The exit is the only path back to the pool, so a revocation that does not
    # complete must not strand a connection outside it — and what does come back
    # is disposed of first, because a scope that may still reach it is not one
    # to offer the next caller.
    from parallax.postgres import _connection as connection_module

    def refuse(_self: object) -> bool:
        raise RuntimeError("the scope could not be revoked")

    monkeypatch.setattr(connection_module.PostgresConnection, "revoke", refuse)
    connection = _FakeConnection()
    pool = _pool(connection)
    resource = _context(pool)

    with pytest.raises(RuntimeError), resource:
        pass

    assert connection.closes == 1
    assert pool.returned == [connection]
    assert isinstance(resource.cleanup_result, Invalidated)


def test_a_budget_already_spent_refuses_to_begin_the_next_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _startup as startup_module

    _opened(monkeypatch, _pool())
    monkeypatch.setattr(startup_module, "monotonic", lambda: 1e18)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=0))

    assert failed.value.phase == "acquire"


def test_configuration_opens_the_runtime_it_describes(monkeypatch: pytest.MonkeyPatch) -> None:
    # What `open` delegates to, and with what, is only observable by calling it,
    # so this is the one place the suite spells the acquisition the access guard
    # exists to refuse — over a stub, reaching no server.
    from parallax.postgres import _adapter as adapter_module

    opened: list[tuple[object, ...]] = []

    def open_runtime_stub(
        writer: object,
        reader: object,
        *,
        acquire_timeout: object,
        startup_timeout: object,
        reader_startup: object,
        prepare_threshold: object,
    ) -> object:
        opened.append(
            (writer, reader, acquire_timeout, startup_timeout, reader_startup, prepare_threshold)
        )
        return "the runtime"

    monkeypatch.setattr(adapter_module, "open_runtime", open_runtime_stub)
    writer = PostgresEndpoint("host=localhost", credentials=Password("hunter2"))
    reader = PostgresEndpoint("host=replica", credentials=Password("hunter2"))
    single = adapter_module.PostgresAdapter(
        writer=writer, acquire_timeout=2.0, startup_timeout=4.0, prepare_threshold=None
    )
    deferred = adapter_module.PostgresAdapter(writer=writer, reader=reader)
    required = adapter_module.PostgresAdapter(
        writer=writer, reader=reader, reader_startup="required"
    )

    for configured in (single, deferred, required):
        assert configured.open() == "the runtime"  # database-access: open_runtime is stubbed above
    # An omitted reader_startup defers a configured reader.
    assert opened == [
        (writer, None, 2.0, 4.0, "deferrable", None),
        (writer, reader, 15.0, 30.0, "deferrable", 5),
        (writer, reader, 15.0, 30.0, "required", 5),
    ]


def test_leaving_a_context_that_was_never_entered_does_nothing() -> None:
    # Total on every exit: a context a caller built and abandoned has taken
    # nothing, so leaving it releases nothing and reports nothing.
    pool = _pool()
    resource = _context(pool)
    resource.__exit__(None, None, None)
    assert (pool.returned, resource.cleanup_result) == ([], None)


# --------------------------------------------------------------------------- #
# The credential: resolved per physical connection, or not supplied at all.    #
# --------------------------------------------------------------------------- #


def _recorded(establishment: ConnectionEstablishment) -> BaseException | None:
    failure = establishment.last_failure
    return None if failure is None else failure.cause


def _base_kwargs() -> dict[str, object]:
    """A stand-in for the driver keywords this adapter owns."""
    return {"autocommit": True}


class _Refusing:
    """A source that raises what it was built with, counting how often it is asked."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def resolve(self) -> Password:
        self.calls += 1
        raise self.error


def test_each_physical_connection_gets_fresh_keywords_carrying_the_resolved_secret() -> None:
    # A fresh dictionary per connection, because the base is what the NEXT
    # connection would inherit: writing the secret into it would outlive the
    # connection it was resolved for.
    establishment = _establishment()
    base: dict[str, object] = {"autocommit": True}
    resolve = establishment.connect_kwargs(base, Password("hunter2"))

    first, second = resolve(), resolve()

    assert first == {"autocommit": True, "password": "hunter2"}
    assert first is not second
    assert base == {"autocommit": True}
    assert establishment.last_failure is None


def test_a_source_that_refuses_records_its_own_refusal_and_re_raises_it() -> None:
    # The pool creates most connections on a background path, so the refusal
    # reaches a waiting caller only by being on record.
    establishment = _establishment()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    resolve = establishment.connect_kwargs(_base_kwargs(), _Refusing(refusal))

    with pytest.raises(CredentialResolutionError) as raised:
        resolve()

    assert raised.value is refusal
    assert _recorded(establishment) is refusal


def test_any_other_exception_a_source_raises_is_wrapped_with_fixed_text() -> None:
    # Classification must not depend on a provider's discipline, and the pool's
    # own warning line prints the exception's text — so what surfaces is fixed
    # text with the original chained beneath it.
    establishment = _establishment()
    native = RuntimeError("could not sign for hunter2")
    resolve = establishment.connect_kwargs(_base_kwargs(), _Refusing(native))

    with pytest.raises(CredentialResolutionError) as raised:
        resolve()

    assert str(raised.value) == (
        "credential-resolution-failed: the credential source could not produce a password"
    )
    assert "hunter2" not in str(raised.value)
    assert raised.value.__cause__ is native
    assert _recorded(establishment) is raised.value


def test_a_resolved_credential_leaves_a_refusal_on_record_until_a_connection_is_usable() -> None:
    # Several workers dial at once over one record. A credential resolved for
    # one attempt establishes nothing — that attempt can still fail to dial or
    # to initialize — so clearing there would let it erase another attempt's
    # completed refusal and hand the waiting caller a bare timeout instead.
    establishment = _establishment()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    establishment.failed(refusal)

    establishment.connect_kwargs(_base_kwargs(), Password("hunter2"))()

    assert _recorded(establishment) is refusal

    establishment(cast("Any", _Initializable()))

    assert establishment.last_failure is None


# --------------------------------------------------------------------------- #
# The native release this adapter's documented behavior rests on.              #
# --------------------------------------------------------------------------- #


class _NativeStub:
    """What the INSTALLED native pool creates, hands on, and closes.

    The pins below drive `psycopg_pool` itself rather than a fake of it. One of
    this adapter's documented behaviors is the library's rather than its own —
    on-demand establishment bounded by the remaining acquisition budget — so a
    release that changed it would otherwise change what the adapter promises
    without changing a line of it.
    """

    connects: ClassVar[list[dict[str, object]]] = []

    def __init__(self) -> None:
        self._pool: object = None
        self._created_at = 0.0
        self._expire_at = 0.0
        self.closed = False
        self.pgconn = _FakePgConn(_FakeConnection())

    @classmethod
    def connect(cls, conninfo: str, **kwargs: object) -> _NativeStub:
        cls.connects.append({"conninfo": conninfo, **kwargs})
        return cls()

    def close(self) -> None:
        self.closed = True


def _native_null_pool(conninfo: str = "", **kwargs: Any) -> Any:
    _NativeStub.connects = []
    return cast(
        "Any",
        psycopg_pool.NullConnectionPool(
            conninfo, connection_class=cast("Any", _NativeStub), open=False, **kwargs
        ),
    )


def test_on_demand_establishment_is_bounded_by_the_remaining_budget_and_rounded() -> None:
    # `OnDemandOptions` documents this as the reason `acquire_timeout` is the
    # control that matters there: the establishment limit is whatever remains of
    # the acquisition budget, rounded to whole seconds with a floor of one.
    pool = _native_null_pool("connect_timeout=30")

    pool._connect(timeout=4.4)
    pool._connect(timeout=0.2)

    assert [created["connect_timeout"] for created in _NativeStub.connects] == [4, 1]


def test_an_establishment_keyword_overrides_what_the_connection_string_asked_for() -> None:
    # The other half of the same claim: the derived limit is passed as a keyword,
    # and a keyword wins over the same setting in the connection string.
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    resolved = conninfo_to_dict(make_conninfo("connect_timeout=30", connect_timeout=4))

    assert resolved["connect_timeout"] == "4"


# --------------------------------------------------------------------------- #
# Routes: a writer and a reader, one admission, readiness proved or deferred.  #
# --------------------------------------------------------------------------- #


class _Stated(psycopg.OperationalError):
    """A driver connection failure that carries a SQLSTATE, as a fake can."""

    def __init__(self, sqlstate: str | None) -> None:
        self._stated = sqlstate
        super().__init__("connection failed")

    @property
    def sqlstate(self) -> str | None:
        return self._stated


class _Hooked(_FakeConnection):
    """A connection that runs ``on_submit`` with each statement before it answers."""

    def __init__(self, on_submit: Callable[[str], None], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.on_submit = on_submit

    def submit(self, text: str, binds: Sequence[object] | None) -> None:
        self.on_submit(text)
        super().submit(text, binds)


def _routed(
    writer_pool: Any,
    reader_pool: Any,
    *,
    reader_readiness: str = "verified",
    acquire_timeout: float = 15.0,
) -> PostgresRuntime:
    """A started runtime over two fake pools, its reader verified or pending."""
    reader = PostgresRoute("reader", reader_pool, _establishment())
    runtime = PostgresRuntime(
        PostgresRoute("writer", writer_pool, _establishment()),
        reader,
        acquire_timeout=acquire_timeout,
    )
    runtime._complete_startup("runtime-login")  # pyright: ignore[reportPrivateUsage] - the startup transition this harness stands in for
    if reader_readiness == "verified":
        reader.proved_at_startup()
    else:
        reader.defer_verification()
    return runtime


def _reader_route(runtime: PostgresRuntime) -> PostgresRoute:
    reader = runtime._reader  # pyright: ignore[reportPrivateUsage] - the route whose readiness these proofs read
    assert reader is not None
    return reader


def _reader_context(runtime: PostgresRuntime, role: PostgresRole | None = None) -> Any:
    source = runtime.login_source() if role is None else runtime.principal_source(role)
    return source.new_context("reader_only")


def _opened_routes(monkeypatch: pytest.MonkeyPatch, **pools: Any) -> list[tuple[str, Any]]:
    """Make ``open_runtime`` build each route's pool from ``pools``, recording
    the order routes were opened in and what each was built from."""
    from parallax.postgres import _route as route_module

    built: list[tuple[str, Any]] = []

    def build(endpoint: Any, route: str, *_args: object) -> Any:
        built.append((route, endpoint))
        return pools[route]

    monkeypatch.setattr(route_module, "_build_pool", build)
    return built


def _open_routed(
    writer: PoolOptions | OnDemandOptions = PoolOptions(min_size=0),  # noqa: B008 - immutable configuration
    reader: PoolOptions | OnDemandOptions = PoolOptions(min_size=0),  # noqa: B008 - immutable configuration
    *,
    reader_startup: Any = "deferrable",
) -> PostgresRuntime:
    return open_runtime(
        PostgresEndpoint("host=writer", credentials=DRIVER_MANAGED, pool=writer),
        PostgresEndpoint("host=reader", credentials=DRIVER_MANAGED, pool=reader),
        acquire_timeout=15.0,
        startup_timeout=30.0,
        reader_startup=reader_startup,
        prepare_threshold=5,
    )


def _resource_records(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == RESOURCE_LOGGER_NAME]


@pytest.mark.parametrize(
    ("policy", "has_reader", "steps"),
    [
        ("writer_only", False, [("writer", 1.0)]),
        ("writer_only", True, [("writer", 1.0)]),
        ("reader_only", True, [("reader", 1.0)]),
        ("reader_preferred", True, [("reader", 0.5), ("writer", 1.0)]),
    ],
)
def test_each_policy_plans_its_routes_and_their_shares_of_the_budget(
    policy: Any, has_reader: bool, steps: list[tuple[str, float]]
) -> None:
    plan = RoutePlan.for_policy(policy, has_reader=has_reader)
    assert [(step.route, step.share) for step in plan.steps] == steps


@pytest.mark.parametrize(
    ("policy", "has_reader"),
    [("reader_only", False), ("reader_preferred", False)],
)
def test_a_policy_with_no_route_to_serve_it_is_refused_by_the_plan(
    policy: Any, has_reader: bool
) -> None:
    with pytest.raises(ValueError, match="does not serve"):
        RoutePlan.for_policy(policy, has_reader=has_reader)


@pytest.mark.parametrize(
    ("failure", "fallback"),
    [
        ("unavailable", "unavailable"),
        ("connection_lost", "connection_lost"),
        ("timeout", None),
        ("queue_rejected", None),
        ("closed", None),
        ("preparation_failed", None),
        ("authorization_failed", None),
        ("authentication_refused", None),
        ("credentials_refused", None),
    ],
)
def test_only_an_unreachable_route_or_a_lost_setup_connection_falls_back(
    failure: Any, fallback: str | None
) -> None:
    assert RoutePlan.falls_back_on(failure) == fallback


def test_a_routed_runtime_declares_a_reader_that_cannot_begin_serializable() -> None:
    # A hot standby refuses SERIALIZABLE, so the reader never claims it and core
    # refuses that request before anything is acquired.
    runtime = _routed(_pool(), _pool())

    assert dict(runtime.routes) == {
        "writer": RouteCapabilities.every_level(),
        "reader": RouteCapabilities(frozenset({"read_committed", "repeatable_read"})),
    }
    assert [source.route for source in runtime.pool_metrics] == ["writer", "reader"]
    with pytest.raises(TypeError):
        cast("Any", runtime.routes)["reader"] = RouteCapabilities.every_level()


def test_a_reader_lease_s_refusal_reports_the_reader() -> None:
    runtime = _routed(_pool(), _pool(checkout_error=psycopg_pool.PoolTimeout("waited")))
    resource = _reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert (refused.value.reason, refused.value.selection) == (
        "timeout",
        RouteSelection("reader"),
    )


def test_closing_detaches_both_sources_then_closes_both_pools_whatever_one_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    writer_pool = _pool(close_error=RuntimeError("the writer would not close"))
    reader_pool = _pool()
    runtime = _routed(writer_pool, reader_pool)
    sources = runtime.pool_metrics

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME):
        runtime.close()
        runtime.close()

    assert (writer_pool.closes, reader_pool.closes) == (1, 1)
    assert all(isinstance(source.sample(), PoolDetached) for source in sources)
    assert len(_resource_records(caplog)) == 1
    # One admission decision serves both routes.
    with pytest.raises(ConnectionAcquisitionError) as refused:
        _reader_context(runtime).__enter__()
    assert refused.value.reason == "closed"


def test_an_interrupted_close_still_closes_every_later_pool() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool, reader_pool = _pool(close_error=interrupt), _pool()
    runtime = _routed(writer_pool, reader_pool)

    with pytest.raises(KeyboardInterrupt) as raised:
        runtime.close()

    assert raised.value is interrupt
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_an_interrupted_abandonment_still_abandons_every_other_opened_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interrupt = KeyboardInterrupt()
    writer_pool = _pool()
    reader_pool = _pool(
        _FakeConnection(rows=[{**_PROBE_ROW, "login_identity": "other"}]), close_error=interrupt
    )
    _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    with pytest.raises(KeyboardInterrupt) as raised:
        _open_routed()

    assert raised.value is interrupt
    assert isinstance(raised.value.__context__, DatabaseStartupError)
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_pool_whose_open_is_interrupted_is_closed_and_the_interrupt_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[_FakePool] = []

    class _Interrupted(_FakePool):
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            super().__init__()
            built.append(self)

        def open(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", _Interrupted)

    with pytest.raises(KeyboardInterrupt):
        _open_runtime(PoolOptions())

    (pool,) = built
    assert pool.closes == 1


def test_routed_startup_opens_both_pools_before_proving_the_writer_then_the_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Opening both first is what lets a retaining reader's workers dial while
    # the writer is being proved, so the two share the one budget's wall time.
    writer_pool, reader_pool = _pool(), _pool()
    order: list[str] = []
    writer_pool.wait = lambda timeout=30.0: order.append("writer waited")
    built = _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    runtime = _open_routed(PoolOptions(min_size=1), OnDemandOptions(max_size=20))

    assert [route for route, _endpoint in built] == ["writer", "reader"]
    assert order == ["writer waited"]
    assert writer_pool.returned[0].statements == reader_pool.returned[0].statements == [PROBE_SQL]
    assert runtime.login_identity == "runtime-login"
    assert [sample.readiness for sample in _available_samples(runtime)] == [
        "verified",
        "verified",
    ]
    # Each route keeps the retention and capacity its own endpoint configured.
    (_, writer_endpoint), (_, reader_endpoint) = built
    assert writer_endpoint.pool == PoolOptions(min_size=1)
    assert reader_endpoint.pool == OnDemandOptions(max_size=20)


def _available_samples(runtime: PostgresRuntime) -> list[Any]:
    samples = [source.sample() for source in runtime.pool_metrics]
    assert all(type(sample).__name__ == "PoolAvailable" for sample in samples), samples
    return samples


def test_routed_startup_proves_the_reader_within_what_remains_of_the_one_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(monkeypatch)
    writer = _Hooked(lambda _text: setattr(clock, "now", 12.0))
    reader_pool = _pool()
    _opened_routes(monkeypatch, writer=_pool(writer), reader=reader_pool)

    _open_routed()

    assert reader_pool.checkouts == [18.0]


def test_a_reader_that_authenticates_another_login_fails_startup_and_closes_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer_pool = _pool()
    reader_pool = _pool(_FakeConnection(rows=[{**_PROBE_ROW, "login_identity": "other"}]))
    _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed()

    assert (failed.value.route, failed.value.phase) == ("reader", "probe")
    assert "different database login" in str(failed.value)
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_writer_that_fails_startup_names_the_writer_and_closes_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer_pool = _pool(checkout_error=psycopg_pool.PoolTimeout("waited"))
    reader_pool = _pool()
    _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed()

    assert (failed.value.route, failed.value.phase) == ("writer", "acquire")
    assert reader_pool.checkouts == []
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_pool_that_will_not_open_closes_the_writer_pool_already_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _route as route_module

    writer_pool = _pool()

    def build(_endpoint: Any, route: str, *_args: object) -> Any:
        if route == "reader":
            raise DatabaseStartupError("no reader pool", route="reader", phase="open")
        return writer_pool

    monkeypatch.setattr(route_module, "_build_pool", build)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed()

    assert (failed.value.route, failed.value.phase) == ("reader", "open")
    assert writer_pool.checkouts == []
    assert writer_pool.closes == 1


def test_a_pool_that_will_not_open_names_its_route(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Refusing(_FakePool):
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            super().__init__()

        def open(self) -> None:
            raise psycopg_pool.PoolTimeout("the pool would not open")

    monkeypatch.setattr(psycopg_pool, "NullConnectionPool", _Refusing)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(reader=OnDemandOptions())

    assert (failed.value.route, failed.value.phase) == ("reader", "open")


def test_a_runtime_that_cannot_be_constructed_closes_both_pools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _startup as startup_module

    writer_pool, reader_pool = _pool(), _pool()
    _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    def refuse(*_args: object, **_kwargs: object) -> Any:
        raise RuntimeError("the runtime could not be built")

    monkeypatch.setattr(startup_module, "PostgresRuntime", refuse)

    with pytest.raises(RuntimeError, match="could not be built"):
        _open_routed()

    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


@pytest.mark.parametrize(
    "unreachable",
    [
        pytest.param(lambda: psycopg_pool.PoolTimeout("waited"), id="spent-share"),
        pytest.param(lambda: _lost("connection refused"), id="refused-dial"),
    ],
)
def test_an_unreachable_reader_is_left_pending_under_deferrable_startup(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    unreachable: Callable[[], BaseException],
) -> None:
    reader_pool = _pool(checkout_error=unreachable())
    _opened_routes(monkeypatch, writer=_pool(), reader=reader_pool)

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME):
        runtime = _open_routed()

    assert _reader_route(runtime).readiness() == "pending"
    assert [sample.readiness for sample in _available_samples(runtime)] == [
        "verified",
        "pending",
    ]
    (notice,) = _resource_records(caplog)
    assert notice.startswith("the database runtime's reader route started unverified")
    assert reader_pool.closes == 0
    runtime.close()


def test_an_unreachable_reader_fails_startup_when_it_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer_pool = _pool()
    reader_pool = _pool(checkout_error=_lost("connection refused"))
    _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(reader_startup="required")

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError) and cause.reason == "unavailable"
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_whose_budget_ran_out_between_phases_is_left_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Running out names no refusal, so it is an outage's symptom. The startup
    # clock reads the deadline, the writer's two phase checks, and then the
    # reader's first, by which time the one budget is gone.
    from parallax.postgres import _startup as startup_module

    _Clock(monkeypatch)
    readings = iter([0.0, 0.0, 0.0, 31.0])
    monkeypatch.setattr(startup_module, "monotonic", lambda: next(readings))
    reader_pool = _pool()
    _opened_routes(monkeypatch, writer=_pool(), reader=reader_pool)

    runtime = _open_routed()

    assert _reader_route(runtime).readiness() == "pending"
    assert reader_pool.checkouts == []


def test_a_reader_whose_budget_ran_out_with_a_refusal_on_record_fails_deferrable_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same spent budget as above, but the reader's own background dials
    # were refused meanwhile, so it is no outage.
    from parallax.postgres import _route as route_module
    from parallax.postgres import _startup as startup_module

    _Clock(monkeypatch)
    readings = iter([0.0, 0.0, 0.0, 31.0])
    monkeypatch.setattr(startup_module, "monotonic", lambda: next(readings))
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    establishments = iter([_establishment(), reader_establishment := _establishment()])
    reader_establishment.failed(refusal)
    monkeypatch.setattr(route_module, "ConnectionEstablishment", lambda: next(establishments))
    writer_pool, reader_pool = _pool(), _pool()
    _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed()

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    assert failed.value.__cause__ is refusal
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


@pytest.mark.parametrize(
    "refusal",
    [
        pytest.param(CredentialResolutionError("RDS IAM token could not be generated"), id="creds"),
        pytest.param(
            IncompatibleSessionError("this connection's DateStyle is 'German'"), id="codec"
        ),
    ],
)
def test_a_reader_refused_rather_than_unreachable_fails_even_deferrable_startup(
    monkeypatch: pytest.MonkeyPatch, refusal: Exception
) -> None:
    # A retaining reader's minimum fills on its own background path, so what
    # its wait meets is read off the reader's own record.
    from parallax.postgres import _route as route_module

    writer_pool = _pool()
    reader_pool = _pool(wait_error=psycopg_pool.PoolTimeout("not filled"))
    establishments = iter([_establishment(), reader_establishment := _establishment()])
    reader_establishment.failed(refusal)
    monkeypatch.setattr(route_module, "ConnectionEstablishment", lambda: next(establishments))
    _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(reader=PoolOptions(min_size=1))

    assert (failed.value.route, failed.value.phase) == ("reader", "minimum_ready")
    assert failed.value.__cause__ is refusal
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_minimum_that_met_only_an_unreachable_server_is_left_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _route as route_module

    reader_pool = _pool(wait_error=psycopg_pool.PoolTimeout("not filled"))
    establishments = iter([_establishment(), reader_establishment := _establishment()])
    reader_establishment.failed(_lost("connection refused"))
    monkeypatch.setattr(route_module, "ConnectionEstablishment", lambda: next(establishments))
    _opened_routes(monkeypatch, writer=_pool(), reader=reader_pool)

    runtime = _open_routed(reader=PoolOptions(min_size=1))

    assert _reader_route(runtime).readiness() == "pending"


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (_lost("connection refused"), "could reach its server"),
        (_Stated("28P01"), "accepted once its login was offered"),
    ],
)
def test_a_minimum_wait_names_the_dial_failure_on_record(
    monkeypatch: pytest.MonkeyPatch, failure: psycopg.OperationalError, message: str
) -> None:
    from parallax.postgres import _route as route_module

    establishment = _establishment()
    establishment.failed(failure)
    _opened(monkeypatch, _pool(wait_error=psycopg_pool.PoolTimeout("not filled")))
    monkeypatch.setattr(route_module, "ConnectionEstablishment", lambda: establishment)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(PoolOptions(min_size=1))

    assert (failed.value.route, failed.value.phase) == ("writer", "minimum_ready")
    assert message in str(failed.value)


def test_a_reader_probe_lost_with_no_replacement_is_left_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The replacement's checkout times out, so the probe's own driver failure
    # stands — and a lost connection is an outage.
    reader_pool = _pool(_FakeConnection(lost=_lost()))
    reader_pool.checkout_error = None
    calls = iter([None, psycopg_pool.PoolTimeout("waited")])
    getconn = reader_pool.getconn

    def failing_getconn(timeout: float | None = None) -> Any:
        error = next(calls)
        if error is not None:
            raise error
        return getconn(timeout)

    reader_pool.getconn = failing_getconn
    _opened_routes(monkeypatch, writer=_pool(), reader=reader_pool)

    runtime = _open_routed()

    assert _reader_route(runtime).readiness() == "pending"


def test_a_reader_probe_that_fails_for_another_reason_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader_pool = _pool(_FakeConnection(execute_error=RuntimeError("the statement failed")))
    _opened_routes(monkeypatch, writer=_pool(), reader=reader_pool)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed()

    assert (failed.value.route, failed.value.phase) == ("reader", "probe")


def test_a_reader_probe_whose_release_is_unconfirmed_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader_pool = _pool(putconn_error=RuntimeError("the return failed"))
    _opened_routes(monkeypatch, writer=_pool(), reader=reader_pool)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed()

    assert (failed.value.route, failed.value.phase) == ("reader", "release")


@pytest.mark.parametrize("failure", ["lost-probe", "late-checkout"])
def test_a_reader_outage_whose_cleanup_is_unconfirmed_fails_deferrable_startup(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    # Unreachable and timed out are outages, but what was taken could not be
    # shown to have been given back, which no deferral waits out.
    clock = _Clock(monkeypatch)
    handoff = RuntimeError("the return failed")
    if failure == "lost-probe":
        reader_pool = _pool(_FakeConnection(lost=_lost()), putconn_error=handoff)
    else:
        reader_pool = _pool(putconn_error=handoff)
        getconn = reader_pool.getconn

        def late(timeout: float | None = None) -> Any:
            clock.now = 31.0
            return getconn(timeout)

        reader_pool.getconn = late
    writer_pool = _pool()
    _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed()

    assert failed.value.route == "reader"
    assert failed.value.phase == ("probe" if failure == "lost-probe" else "acquire")
    assert isinstance(failed.value.cleanup_result, ReleaseUnconfirmed)
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_pending_reader_proves_each_connection_before_its_role_and_then_serves(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reader_pool = _pool(_FakeConnection(), _FakeConnection())
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    reader = _reader_route(runtime)

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME):
        with _reader_context(runtime, PostgresRole("tenant_reader")) as scoped:
            scoped.execute("select 1", [])
        with _reader_context(runtime) as scoped:
            scoped.execute("select 2", [])

    first, second = reader_pool.returned
    assert first.statements[0] == PROBE_SQL
    assert "SET ROLE" in first.statements[1]
    assert first.statements[2:] == ["select 1", "RESET ROLE"]
    # Verified now, so a later connection is not proved again.
    assert second.statements == ["select 2"]
    assert reader.readiness() == "verified"
    notices = _resource_records(caplog)
    assert notices[-1] == "the database runtime's reader route was verified and now serves its work"
    assert sum("verified and now serves" in notice for notice in notices) == 1


def test_a_pending_reader_s_proof_spends_the_first_send_before_its_role(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The proof was the lease's first submission, so a role installation that
    # then meets a broken session is not a second opportunity.
    connection = _Hooked(lambda text: _lose_after_probe(connection, text))
    reader_pool = _pool(connection, _FakeConnection())
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    resource = _reader_context(runtime, PostgresRole("tenant_reader"))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert len(reader_pool.checkouts) == 1
    assert _reader_route(runtime).readiness() == "verified"


def _lose_after_probe(connection: _FakeConnection, text: str) -> None:
    if text != PROBE_SQL:
        connection.lost = _lost()


def _no_body(_port: DatabaseConnection) -> None:
    return None


def test_a_pending_reader_s_proof_spends_the_first_send_before_its_begin() -> None:
    connection = _Hooked(lambda text: _lose_after_probe(connection, text))
    reader_pool = _pool(connection, _FakeConnection())
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with _reader_context(runtime) as scoped:
        outcome = scoped.transaction(_no_body, isolation="repeatable_read", access_mode="read_only")

    assert isinstance(outcome, BeginFailed)
    assert len(reader_pool.checkouts) == 1


def test_a_pending_reader_s_proof_spends_the_first_send_before_a_modeled_read() -> None:
    connection = _Hooked(lambda text: _lose_after_probe(connection, text))
    reader_pool = _pool(connection, _FakeConnection())
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with _reader_context(runtime) as scoped, pytest.raises(DatabaseError):
        scoped.execute("select 1", [], read_only=True)

    assert len(reader_pool.checkouts) == 1


def test_a_broken_proof_is_replaced_once_and_the_replacement_is_proved() -> None:
    broken = _FakeConnection(lost=_lost())
    fresh = _FakeConnection()
    reader_pool = _pool(broken, fresh)
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with _reader_context(runtime) as scoped:
        scoped.execute("select 1", [], read_only=True)

    assert broken.statements == [PROBE_SQL]
    assert fresh.statements == [PROBE_SQL, "select 1"]
    assert _reader_route(runtime).readiness() == "verified"


def test_a_proof_lost_beyond_replacement_fails_its_acquisition_as_unavailable() -> None:
    # An outage is not an incompatibility, so the route stays pending for the
    # next acquisition to prove.
    reader_pool = _pool(
        _FakeConnection(lost=_lost()), _FakeConnection(lost=_lost()), _FakeConnection()
    )
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    resource = _reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "unavailable"
    assert isinstance(refused.value.__cause__, psycopg.OperationalError)
    assert refused.value.selection == RouteSelection("reader")
    assert _reader_route(runtime).readiness() == "pending"
    assert isinstance(resource.cleanup_result, Invalidated)
    with _reader_context(runtime):
        pass
    assert _reader_route(runtime).readiness() == "verified"


def test_a_proof_that_fails_for_an_unknown_reason_changes_no_readiness() -> None:
    failure = RuntimeError("the statement failed")
    reader_pool = _pool(_FakeConnection(execute_error=failure))
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _reader_context(runtime).__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is failure
    assert _reader_route(runtime).readiness() == "pending"


def test_a_control_flow_exception_in_a_proof_keeps_its_own_propagation() -> None:
    # The connection is still disposed of, and an interrupt is no evidence
    # about the route, so its readiness is untouched.
    connection = _FakeConnection(execute_error=KeyboardInterrupt())
    runtime = _routed(_pool(), _pool(connection), reader_readiness="pending")
    resource = _reader_context(runtime)

    with pytest.raises(KeyboardInterrupt):
        resource.__enter__()

    assert connection.closes == 1 and isinstance(resource.cleanup_result, Invalidated)
    assert _reader_route(runtime).readiness() == "pending"


def test_a_proof_that_reads_another_login_refuses_the_route_for_good(
    caplog: pytest.LogCaptureFixture,
) -> None:
    other = _FakeConnection(rows=[{**_PROBE_ROW, "login_identity": "other"}])
    reader_pool = _pool(other, _FakeConnection())
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    resource = _reader_context(runtime)

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME):
        with pytest.raises(ConnectionAcquisitionError) as refused:
            resource.__enter__()
        with pytest.raises(ConnectionAcquisitionError) as later:
            _reader_context(runtime).__enter__()

    assert refused.value.reason == later.value.reason == "preparation_failed"
    mismatch = refused.value.__cause__
    assert isinstance(mismatch, ProbeMismatch) and later.value.__cause__ is mismatch
    # The mismatched connection is disposed of; the later acquisition takes nothing.
    assert other.closes == 1 and isinstance(resource.cleanup_result, Invalidated)
    assert len(reader_pool.checkouts) == 1
    assert _reader_route(runtime).readiness() == "refused"
    assert [sample.readiness for sample in _available_samples(runtime)][1] == "refused"
    assert _resource_records(caplog)[-1].startswith(
        "the database runtime's reader route was refused"
    )


def test_a_proof_that_succeeds_after_a_concurrent_refusal_admits_nothing() -> None:
    reader_pool: Any = None

    def refuse_meanwhile(_text: str) -> None:
        _reader_route(runtime).refuse(ProbeMismatch("another lease read another login"))

    late = _Hooked(refuse_meanwhile)
    reader_pool = _pool(late)
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    resource = _reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert str(refused.value.__cause__) == "another lease read another login"
    # The connection itself proved compatible, so it is returned rather than disposed of.
    assert resource.cleanup_result == Returned()
    assert _reader_route(runtime).readiness() == "refused"


def test_a_route_refused_while_a_checkout_waited_admits_nothing_handed_over() -> None:
    connection = _FakeConnection()
    reader_pool = _pool(connection)
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    mismatch = ProbeMismatch("another lease read another login")
    getconn = reader_pool.getconn

    def refused_meanwhile(timeout: float | None = None) -> Any:
        _reader_route(runtime).refuse(mismatch)
        return getconn(timeout)

    reader_pool.getconn = refused_meanwhile
    resource = _reader_context(runtime, PostgresRole("tenant_reader"))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is mismatch
    assert connection.statements == []
    assert resource.cleanup_result == Returned()


def test_a_mismatch_whose_disposal_is_interrupted_still_refuses_the_route() -> None:
    other = _FakeConnection(
        rows=[{**_PROBE_ROW, "login_identity": "other"}], close_error=KeyboardInterrupt()
    )
    runtime = _routed(_pool(), _pool(other), reader_readiness="pending")

    with pytest.raises(KeyboardInterrupt):
        _reader_context(runtime).__enter__()

    assert _reader_route(runtime).readiness() == "refused"


def test_a_transient_proof_failure_never_downgrades_a_concurrently_verified_route() -> None:
    def verify_meanwhile_then_lose(_text: str) -> None:
        _reader_route(runtime).verified()
        connection.lost = _lost()

    connection = _Hooked(verify_meanwhile_then_lose)
    reader_pool = _pool(connection, _FakeConnection(lost=_lost()))
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with pytest.raises(ConnectionAcquisitionError):
        _reader_context(runtime).__enter__()

    assert _reader_route(runtime).readiness() == "verified"


def test_a_mismatch_on_a_verified_route_fails_only_its_own_acquisition() -> None:
    def verify_meanwhile(_text: str) -> None:
        _reader_route(runtime).verified()

    connection = _Hooked(verify_meanwhile, rows=[{**_PROBE_ROW, "login_identity": "other"}])
    runtime = _routed(_pool(), _pool(connection), reader_readiness="pending")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _reader_context(runtime).__enter__()

    assert refused.value.reason == "preparation_failed"
    assert _reader_route(runtime).readiness() == "verified"


def test_simultaneous_proofs_each_run_and_the_route_is_verified_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Both connections were handed over while the route was pending, so each
    # proves itself; the first success verifies and the second changes nothing.
    nested: list[Any] = []

    def acquire_meanwhile(text: str) -> None:
        if text == PROBE_SQL and not nested:
            inner = _reader_context(runtime)
            nested.append(inner)
            with inner:
                pass

    outer = _Hooked(acquire_meanwhile)
    inner_connection = _FakeConnection()
    reader_pool = _pool(outer, inner_connection)
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME), _reader_context(runtime):
        pass

    assert outer.statements == inner_connection.statements == [PROBE_SQL]
    assert _reader_route(runtime).readiness() == "verified"
    assert sum("verified and now serves" in notice for notice in _resource_records(caplog)) == 1


def test_a_pending_proof_still_spends_the_acquisition_s_own_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(monkeypatch)
    slow = _Hooked(lambda _text: setattr(clock, "now", 20.0))
    reader_pool = _pool(slow)
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    resource = _reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert resource.cleanup_result == Returned()
    assert _reader_route(runtime).readiness() == "verified"


# --------------------------------------------------------------------------- #
# Classifying what establishing a connection met.                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (_Stated(None), "unavailable"),
        (_Stated("08006"), "unavailable"),
        (_Stated("57P03"), "unavailable"),
        (psycopg.errors.ConnectionTimeout("connect timeout"), "unavailable"),
        (_Stated("28P01"), "authentication_refused"),
        (_Stated("3D000"), "preparation_failed"),
        (_Stated("53300"), "preparation_failed"),
        (psycopg.ProgrammingError("invalid option"), "preparation_failed"),
        (CredentialResolutionError("no token"), "credentials_refused"),
        (IncompatibleSessionError("DateStyle"), "preparation_failed"),
    ],
)
def test_every_establishment_failure_classifies_to_one_reason(
    failure: BaseException, reason: str
) -> None:
    assert dial_reason(failure) == reason


def test_a_timed_out_wait_is_an_outage_only_when_a_dial_failed_during_it() -> None:
    # A failure already history when the wait began says nothing about why it
    # ran out: a healthy saturated pool must not read as an unreachable one.
    establishment = _establishment()
    historic = _lost("connection refused")
    establishment.failed(historic)
    pool = _pool(checkout_error=psycopg_pool.PoolTimeout("waited"))
    route = PostgresRoute("reader", pool, establishment)

    with pytest.raises(ConnectionAcquisitionError) as saturated:
        checkout(route, monotonic() + 5.0)

    fresh = _lost("connection refused")

    def dial_during_the_wait(timeout: float | None = None) -> Any:
        del timeout
        establishment.failed(fresh)
        raise psycopg_pool.PoolTimeout("waited")

    pool.getconn = dial_during_the_wait
    with pytest.raises(ConnectionAcquisitionError) as unavailable:
        checkout(route, monotonic() + 5.0)

    assert saturated.value.reason == "timeout"
    assert unavailable.value.reason == "unavailable"
    assert unavailable.value.__cause__ is fresh


@pytest.mark.parametrize(
    "native", ["NullConnectionPool", "ConnectionPool"], ids=["on-demand", "retaining"]
)
def test_the_installed_pools_dial_through_the_route_s_observed_connection_class(
    monkeypatch: pytest.MonkeyPatch, native: str
) -> None:
    # The hook is the library's public `connection_class`: on-demand dials on
    # the caller's thread and retaining on its own workers, and both reach it.
    refused = _lost("connection refused")

    def refuse(cls: type[Any], conninfo: str = "", **kwargs: object) -> Any:
        del cls, conninfo, kwargs
        raise refused

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(refuse))
    establishment = _establishment()
    options: dict[str, Any] = {"min_size": 0, "max_size": 1} if native == "ConnectionPool" else {}
    pool = getattr(psycopg_pool, native)(
        "",
        connection_class=establishment.connection_class,
        configure=establishment,
        open=False,
        num_workers=1,
        reconnect_timeout=5.0,
        **options,
    )
    pool.open()
    try:
        with pytest.raises(ConnectionAcquisitionError) as failed:
            checkout(PostgresRoute("reader", pool, establishment), monotonic() + 0.5)
    finally:
        pool.close()

    assert failed.value.reason == "unavailable"
    recorded = establishment.last_failure
    assert recorded is not None and recorded.cause is refused


def test_an_observed_dial_that_succeeds_records_nothing_until_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    establishment = _establishment()
    earlier = _lost("connection refused")
    establishment.failed(earlier)
    dialed = object()

    def dial(cls: type[Any], conninfo: str = "", **kwargs: object) -> Any:
        del cls, conninfo, kwargs
        return dialed

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(dial))

    assert establishment.connection_class.connect("") is dialed
    recorded = establishment.last_failure
    assert recorded is not None and recorded.cause is earlier


# --------------------------------------------------------------------------- #
# Preferred fallback: the reader within half the budget, then the writer.     #
# --------------------------------------------------------------------------- #


def _preferred(runtime: PostgresRuntime, role: PostgresRole | None = None) -> Any:
    source = runtime.login_source() if role is None else runtime.principal_source(role)
    return source.new_context("reader_preferred")


def _refusing(failure: BaseException, *, after: Callable[[], None] = lambda: None) -> Any:
    """A pool whose every checkout runs ``after`` and then raises ``failure``."""
    pool = _pool()

    def getconn(timeout: float | None = None) -> Any:
        pool.checkouts.append(timeout)
        after()
        raise failure

    pool.getconn = getconn
    return pool


def test_a_healthy_reader_serves_a_preferred_acquisition_within_half_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Clock(monkeypatch)
    writer_pool, reader_pool = _pool(), _pool()
    resource = _preferred(_routed(writer_pool, reader_pool))

    with resource as scoped:
        scoped.execute("select 1", [])

    assert reader_pool.checkouts == [7.5]
    assert writer_pool.checkouts == []
    assert resource.selection == RouteSelection("reader")


def test_an_unreachable_reader_falls_back_to_the_writer_with_what_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An on-demand reader dials on this thread, so its failure surfaces at
    # once and the writer gets everything the reader did not spend.
    clock = _Clock(monkeypatch)
    writer_pool = _pool()
    reader_pool = _refusing(_lost("connection refused"), after=lambda: setattr(clock, "now", 3.0))
    resource = _preferred(_routed(writer_pool, reader_pool))

    with resource as scoped:
        scoped.execute("select 1", [])

    assert reader_pool.checkouts == [7.5]
    assert writer_pool.checkouts == [12.0]
    assert writer_pool.returned[0].statements == ["select 1"]
    assert resource.selection == RouteSelection("writer", "unavailable")


def test_a_reader_share_spent_while_its_dials_failed_falls_back_at_the_share_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A retaining reader dials on its own workers and cannot wake a waiter, so
    # a failure recorded during the wait is noticed when the share runs out.
    clock = _Clock(monkeypatch)
    writer_pool = _pool()
    reader_pool = _refusing(psycopg_pool.PoolTimeout("waited"))
    runtime = _routed(writer_pool, reader_pool)

    def dial_fails_meanwhile() -> None:
        _reader_route(runtime).establishment.failed(_lost("connection refused"))
        clock.now = 7.5

    reader_pool.getconn = _refusing(
        psycopg_pool.PoolTimeout("waited"), after=dial_fails_meanwhile
    ).getconn
    resource = _preferred(runtime)

    with resource:
        pass

    assert writer_pool.checkouts == [7.5]
    assert resource.selection == RouteSelection("writer", "unavailable")


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        pytest.param(psycopg_pool.PoolTimeout("waited"), "timeout", id="saturated"),
        pytest.param(psycopg_pool.TooManyRequests("queue full"), "queue_rejected", id="queue"),
        pytest.param(psycopg_pool.PoolClosed("closed"), "closed", id="closed"),
        pytest.param(_Stated("28P01"), "authentication_refused", id="login-refused"),
        pytest.param(CredentialResolutionError("no token"), "credentials_refused", id="creds"),
        pytest.param(_Stated("3D000"), "preparation_failed", id="invalid-setup"),
    ],
)
def test_a_reader_that_is_busy_refused_or_closed_ends_a_preferred_acquisition(
    failure: BaseException, reason: str
) -> None:
    # None of these is something the writer would fix, and a busy reader is
    # never mistaken for one that cannot be reached.
    writer_pool = _pool()
    resource = _preferred(_routed(writer_pool, _pool(checkout_error=failure)))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == reason
    assert refused.value.selection == RouteSelection("reader")
    assert writer_pool.checkouts == []


def test_a_role_the_reader_denies_is_not_a_reason_to_fall_back() -> None:
    denied = psycopg.errors.InsufficientPrivilege("permission denied to set role")
    writer_pool = _pool()
    resource = _preferred(
        _routed(writer_pool, _pool(_FakeConnection(execute_error=denied))), PostgresRole("tenant")
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.selection == RouteSelection("reader")
    assert writer_pool.checkouts == []


def test_a_reader_success_after_its_share_is_refused_rather_than_used_or_fallen_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(monkeypatch)
    writer_pool = _pool()
    connection = _FakeConnection()
    reader_pool = _pool(connection)
    getconn = reader_pool.getconn

    def late(timeout: float | None = None) -> Any:
        clock.now = 8.0
        return getconn(timeout)

    reader_pool.getconn = late
    resource = _preferred(_routed(writer_pool, reader_pool))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert writer_pool.checkouts == []
    assert reader_pool.returned == [connection]


def test_a_refused_reader_ends_a_preferred_acquisition_as_a_configuration_failure() -> None:
    writer_pool = _pool()
    runtime = _routed(writer_pool, _pool(), reader_readiness="pending")
    mismatch = ProbeMismatch("another login")
    _reader_route(runtime).refuse(mismatch)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _preferred(runtime).__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is mismatch
    assert writer_pool.checkouts == []


def test_a_writer_that_also_fails_after_a_fallback_reports_the_writer_and_the_fallback() -> None:
    resource = _preferred(
        _routed(
            _pool(checkout_error=psycopg_pool.PoolTimeout("waited")),
            _pool(checkout_error=_lost("connection refused")),
        )
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert refused.value.selection == RouteSelection("writer", "unavailable")
    assert resource.selection == RouteSelection("writer", "unavailable")


# --------------------------------------------------------------------------- #
# The probe slot: one demand re-dial of a reader known to be unreachable.     #
# --------------------------------------------------------------------------- #


def _known_unreachable(runtime: PostgresRuntime) -> PostgresRoute:
    reader = _reader_route(runtime)
    reader.establishment.failed(_lost("connection refused"))
    return reader


def test_one_acquisition_holds_the_probe_slot_and_concurrent_ones_fall_back_at_once() -> None:
    # Only the holder waits on the reader; whoever arrives meanwhile goes to
    # the writer without queueing on the route that just failed.
    writer_pool = _pool(_FakeConnection(), _FakeConnection())
    reader_connection = _FakeConnection()
    reader_pool = _pool(reader_connection)
    runtime = _routed(writer_pool, reader_pool)
    reader = _known_unreachable(runtime)
    concurrent: list[Any] = []
    getconn = reader_pool.getconn

    def recovering(timeout: float | None = None) -> Any:
        meanwhile = _preferred(runtime)
        with meanwhile:
            concurrent.append(meanwhile.selection)
        return getconn(timeout)

    reader_pool.getconn = recovering
    holder = _preferred(runtime)

    with holder:
        pass
    reader_pool.getconn = getconn

    assert concurrent == [RouteSelection("writer", "unavailable")]
    assert len(reader_pool.checkouts) == 1
    assert holder.selection == RouteSelection("reader")
    # The holder's checkout cleared the record, and the slot was given back.
    assert reader.establishment.last_failure is None
    assert reader.claim_probe()
    reader.release_probe()
    with _preferred(runtime) as scoped:
        scoped.execute("select 1", [])
    assert len(reader_pool.checkouts) == 2


def test_a_reader_with_an_idle_connection_is_tried_whatever_its_record_says() -> None:
    reader_pool = _pool()
    reader_pool.available = 1
    runtime = _routed(_pool(), reader_pool)
    reader = _known_unreachable(runtime)
    assert reader.claim_probe()

    try:
        resource = _preferred(runtime)
        with resource:
            pass
    finally:
        reader.release_probe()

    assert resource.selection == RouteSelection("reader")


def test_a_reader_whose_pool_cannot_be_measured_is_taken_to_hold_no_idle_connection() -> None:
    reader_pool = _pool()

    def unmeasurable() -> dict[str, object]:
        raise RuntimeError("the pool's bookkeeping could not be read")

    reader_pool.get_stats = unmeasurable
    runtime = _routed(_pool(), reader_pool)
    reader = _known_unreachable(runtime)
    assert reader.claim_probe()

    try:
        resource = _preferred(runtime)
        with resource:
            pass
    finally:
        reader.release_probe()

    assert reader_pool.checkouts == []
    assert resource.selection == RouteSelection("writer", "unavailable")


def test_a_probe_holder_whose_wait_saw_no_fresh_failure_times_out_rather_than_falling_back() -> (
    None
):
    # Historical evidence lets the holder try the reader, but says nothing
    # about why its own wait ran out: that is a saturated or slow route.
    writer_pool = _pool()
    runtime = _routed(writer_pool, _pool(checkout_error=psycopg_pool.PoolTimeout("waited")))
    reader = _known_unreachable(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _preferred(runtime).__enter__()

    assert refused.value.reason == "timeout"
    assert writer_pool.checkouts == []
    assert reader.claim_probe()
    reader.release_probe()


def test_a_strict_reader_always_demands_the_reader_whatever_its_record_says() -> None:
    reader_pool = _pool()
    runtime = _routed(_pool(), reader_pool)
    reader = _known_unreachable(runtime)
    assert reader.claim_probe()

    try:
        with _reader_context(runtime):
            pass
    finally:
        reader.release_probe()

    assert len(reader_pool.checkouts) == 1


def test_a_handed_over_connection_clears_whatever_failure_was_on_record() -> None:
    establishment = _establishment()
    establishment.failed(CredentialResolutionError("no token"))

    checkout(PostgresRoute("reader", _pool(), establishment), monotonic() + 5.0)

    assert establishment.last_failure is None


# --------------------------------------------------------------------------- #
# Setup that loses its connection moves to the writer; modeled reads do not.  #
# --------------------------------------------------------------------------- #


def test_a_reader_lost_installing_the_principal_falls_back_and_installs_it_on_the_writer() -> None:
    reader_connection = _FakeConnection(lost=_lost())
    writer_connection = _FakeConnection()
    reader_pool, writer_pool = _pool(reader_connection), _pool(writer_connection)
    resource = _preferred(_routed(writer_pool, reader_pool), PostgresRole("tenant_reader"))

    with resource as scoped:
        scoped.execute("select current_user", [])

    assert reader_connection.closes == 1
    assert len(reader_pool.checkouts) == 1
    assert "SET ROLE" in writer_connection.statements[0]
    assert writer_connection.statements[1:] == ["select current_user", "RESET ROLE"]
    assert resource.selection == RouteSelection("writer", "connection_lost")


def test_a_fallen_back_role_installation_earns_no_second_replacement() -> None:
    writer_connection = _FakeConnection(lost=_lost())
    writer_pool = _pool(writer_connection, _FakeConnection())
    resource = _preferred(
        _routed(writer_pool, _pool(_FakeConnection(lost=_lost()))), PostgresRole("tenant_reader")
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.selection == RouteSelection("writer", "connection_lost")
    assert len(writer_pool.checkouts) == 1


def test_a_reader_lost_at_its_first_begin_opens_the_boundary_on_the_writer_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(monkeypatch)
    reader_connection = _FakeConnection(lost=_lost(), when_lost=lambda: setattr(clock, "now", 2.0))
    writer_connection = _FakeConnection()
    reader_pool, writer_pool = _pool(reader_connection), _pool(writer_connection)
    resource = _preferred(_routed(writer_pool, reader_pool))
    bodies: list[object] = []

    def body(port: DatabaseConnection) -> list[Row]:
        bodies.append(port)
        return port.execute("select 1", [])

    with resource as scoped:
        assert resource.selection == RouteSelection("reader")
        outcome = scoped.transaction(body, isolation="repeatable_read", access_mode="read_only")

    assert isinstance(outcome, Committed)
    assert len(bodies) == 1
    assert reader_connection.statements == ["BEGIN"]
    assert reader_connection.closes == 1
    assert writer_pool.checkouts == [13.0]
    assert writer_connection.statements == ["BEGIN", "select 1", "COMMIT"]
    assert ("read_only", True) in writer_connection.characteristics
    assert resource.selection == RouteSelection("writer", "connection_lost")


@pytest.mark.parametrize("ending", ["late", "closed"])
def test_a_boundary_that_opens_past_its_step_or_its_runtime_runs_no_callback(
    monkeypatch: pytest.MonkeyPatch, ending: str
) -> None:
    # The reader's half ends at 5.0; a BEGIN answering at 20.0, or after the
    # runtime closed, is no allowance of its own.
    clock = _Clock(monkeypatch)

    def slow_begin(text: str) -> None:
        if text != "BEGIN":
            return
        if ending == "late":
            clock.now = 20.0
        else:
            runtime.close()

    reader_connection = _Hooked(slow_begin)
    runtime = _routed(_pool(), _pool(reader_connection), acquire_timeout=10.0)
    resource = _preferred(runtime)

    with resource as scoped, pytest.raises(ConnectionAcquisitionError) as refused:
        scoped.transaction(_no_body)

    assert refused.value.reason == ("timeout" if ending == "late" else "closed")
    assert refused.value.selection == RouteSelection("reader")
    assert reader_connection.statements == ["BEGIN"]
    assert reader_connection.closes == 1
    assert isinstance(resource.cleanup_result, Invalidated)


def test_a_writer_replacement_that_arrives_past_the_deadline_runs_no_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(monkeypatch)
    writer_connection = _FakeConnection()
    writer_pool = _pool(writer_connection)
    getconn = writer_pool.getconn

    def late(timeout: float | None = None) -> Any:
        clock.now = 20.0
        return getconn(timeout)

    writer_pool.getconn = late
    resource = _preferred(
        _routed(writer_pool, _pool(_FakeConnection(lost=_lost())), acquire_timeout=10.0)
    )

    with resource as scoped, pytest.raises(ConnectionAcquisitionError) as refused:
        scoped.transaction(_no_body)

    assert refused.value.reason == "timeout"
    assert refused.value.selection == RouteSelection("writer", "connection_lost")
    assert writer_connection.statements == ["BEGIN"]
    assert writer_connection.closes == 1


def test_a_begin_after_the_principal_was_installed_is_no_second_opportunity() -> None:
    def lose_after_role(text: str) -> None:
        if text == "BEGIN":
            reader_connection.lost = _lost()

    reader_connection = _Hooked(lose_after_role)
    writer_pool = _pool()
    resource = _preferred(_routed(writer_pool, _pool(reader_connection)), PostgresRole("tenant"))

    with resource as scoped:
        outcome = scoped.transaction(_no_body, access_mode="read_only")

    assert isinstance(outcome, BeginFailed)
    assert writer_pool.checkouts == []
    assert resource.selection == RouteSelection("reader")


def test_a_pending_reader_s_lost_proof_falls_back_and_leaves_the_reader_pending() -> None:
    writer_connection = _FakeConnection()
    writer_pool = _pool(writer_connection)
    runtime = _routed(writer_pool, _pool(_FakeConnection(lost=_lost())), reader_readiness="pending")
    resource = _preferred(runtime, PostgresRole("tenant_reader"))

    with resource:
        pass

    assert _reader_route(runtime).readiness() == "pending"
    # The writer is verified, so it runs no proof, and the role is installed there.
    assert "SET ROLE" in writer_connection.statements[0]
    assert PROBE_SQL not in writer_connection.statements
    assert resource.selection == RouteSelection("writer", "connection_lost")


def test_a_modeled_read_s_replacement_stays_on_the_reader_it_began_on() -> None:
    broken, fresh = _FakeConnection(lost=_lost()), _FakeConnection()
    reader_pool, writer_pool = _pool(broken, fresh), _pool()
    resource = _preferred(_routed(writer_pool, reader_pool))

    with resource as scoped:
        scoped.execute("select 1", [], read_only=True)

    assert fresh.statements == ["select 1"]
    assert writer_pool.checkouts == []
    assert resource.selection == RouteSelection("reader")


def test_a_reader_disposal_that_cannot_be_confirmed_refuses_the_fallback() -> None:
    reader_connection = _FakeConnection(lost=_lost(), close_error=RuntimeError("no close"))
    writer_pool = _pool()
    resource = _preferred(
        _routed(writer_pool, _pool(reader_connection)), PostgresRole("tenant_reader")
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert isinstance(resource.cleanup_result, ReleaseUnconfirmed)
    assert writer_pool.checkouts == []


def test_an_interrupt_a_lost_reader_setup_displaced_propagates_and_falls_back_nowhere() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool = _pool()
    resource = _preferred(
        _routed(writer_pool, _pool(_FakeConnection(lost=_lost_while_draining(interrupt)))),
        PostgresRole("tenant_reader"),
    )

    with pytest.raises(KeyboardInterrupt) as raised:
        resource.__enter__()

    assert raised.value is interrupt
    assert writer_pool.checkouts == []


# --------------------------------------------------------------------------- #
# Demand re-dial: the installed pools recover a reader without background     #
# probing once their own reconnection gives up.                               #
# --------------------------------------------------------------------------- #


class _RecoveringStub(_NativeStub):
    """A native connection whose first ``refusals`` dials fail."""

    refusals: ClassVar[int] = 0

    @classmethod
    def connect(cls, conninfo: str, **kwargs: object) -> _NativeStub:
        if cls.refusals > 0:
            cls.refusals -= 1
            raise _lost("connection refused")
        return super().connect(conninfo, **kwargs)


def test_a_retaining_pool_that_gave_up_reconnecting_grows_again_on_later_demand() -> None:
    # The library relinquishes the capacity a failed growth held once its own
    # reconnection deadline passes, so the next checkout schedules a dial of
    # its own: demand alone recovers a reader nothing probes in the background.
    # Its own retry is immediate under a zero deadline, so two refusals spend it.
    _RecoveringStub.refusals = 2
    _NativeStub.connects = []
    pool = psycopg_pool.ConnectionPool(
        "",
        connection_class=cast("Any", _RecoveringStub),
        open=False,
        min_size=0,
        max_size=1,
        num_workers=1,
        reconnect_timeout=0.0,
    )
    pool.open()
    try:
        with pytest.raises(psycopg_pool.PoolTimeout):
            pool.getconn(timeout=0.5)
        recovered = pool.getconn(timeout=2.0)
        pool.putconn(recovered)
    finally:
        pool.close()

    assert len(_NativeStub.connects) == 1


def test_an_on_demand_pool_dials_again_on_every_later_demand() -> None:
    _RecoveringStub.refusals = 1
    _NativeStub.connects = []
    pool = psycopg_pool.NullConnectionPool(
        "", connection_class=cast("Any", _RecoveringStub), open=False, num_workers=1
    )
    pool.open()
    try:
        with pytest.raises(psycopg.OperationalError):
            pool.getconn(timeout=1.0)
        recovered = pool.getconn(timeout=1.0)
        pool.putconn(recovered)
    finally:
        pool.close()

    assert len(_NativeStub.connects) == 1


# --------------------------------------------------------------------------- #
# A refusal the server sends while connecting carries no SQLSTATE.             #
# --------------------------------------------------------------------------- #


class _Attempt:
    """The finished connection a driver connect failure carries."""

    def __init__(self, *, used_password: bool, error_message: str = "") -> None:
        self.used_password = used_password
        self.error_message = error_message.encode()


class _ConnectFailed(psycopg.OperationalError):
    def __init__(self, attempt: _Attempt | None) -> None:
        super().__init__("connection failed")
        self._attempt = attempt

    @property
    def pgconn(self) -> Any:
        return self._attempt


@pytest.mark.parametrize(
    ("attempt", "reason"),
    [
        pytest.param(_Attempt(used_password=True), "authentication_refused", id="password-sent"),
        pytest.param(_Attempt(used_password=False), "unavailable", id="no-password-sent"),
        pytest.param(None, "unavailable", id="never-reached"),
    ],
)
def test_a_connect_refusal_after_a_password_was_sent_reads_as_the_server_refusing_it(
    attempt: _Attempt | None, reason: str
) -> None:
    assert dial_reason(_ConnectFailed(attempt)) == reason


_REFUSED_AT = 'connection to server at "127.0.0.1", port 5432 failed: '


@pytest.mark.parametrize(
    ("server_said", "reason"),
    [
        pytest.param(
            'FATAL:  database "app" does not exist\n', "preparation_failed", id="missing-database"
        ),
        pytest.param(
            'FATAL:  database "a"b" does not exist\n',
            "preparation_failed",
            id="missing-database-quoted-name",
        ),
        pytest.param(
            'FATAL:  password authentication failed for user "app"\n',
            "authentication_refused",
            id="rejected-password",
        ),
        pytest.param(
            'FATAL:  password authentication failed for user "x: FATAL:  database "a" '
            'does not exist"\n',
            "authentication_refused",
            id="login-naming-the-message",
        ),
        pytest.param(
            "FATAL:  Datenbank »app« existiert nicht\n", "authentication_refused", id="translated"
        ),
        pytest.param(
            'FATAL:  database "app" is missing\n', "authentication_refused", id="reworded"
        ),
        pytest.param(
            'FATAL:  database "app" does not exist\n'
            + _REFUSED_AT
            + 'FATAL:  password authentication failed for user "app"\n',
            "authentication_refused",
            id="not-the-last-thing-reported",
        ),
    ],
)
def test_only_the_exact_missing_database_message_relabels_a_password_refusal(
    server_said: str, reason: str
) -> None:
    refused = _ConnectFailed(_Attempt(used_password=True, error_message=_REFUSED_AT + server_said))

    assert dial_reason(refused) == reason
    assert RoutePlan.falls_back_on(dial_reason(refused)) is None


class _MessageUnreadable:
    used_password = True

    @property
    def error_message(self) -> bytes:
        raise psycopg.OperationalError("the connection is closed")


def test_a_password_refusal_whose_message_cannot_be_read_reads_as_the_login_refused() -> None:
    assert (
        dial_reason(_ConnectFailed(cast("Any", _MessageUnreadable()))) == "authentication_refused"
    )


def test_a_missing_database_message_without_a_password_sent_still_reads_as_unreachable() -> None:
    attempt = _Attempt(
        used_password=False, error_message=_REFUSED_AT + 'FATAL:  database "app" does not exist\n'
    )

    assert dial_reason(_ConnectFailed(attempt)) == "unavailable"


class _Unreadable:
    @property
    def used_password(self) -> bool:
        raise psycopg.OperationalError("the connection is closed")


def test_a_connect_failure_whose_attempt_cannot_be_read_reads_as_unreachable() -> None:
    assert dial_reason(_ConnectFailed(cast("Any", _Unreadable()))) == "unavailable"


def test_a_lost_established_session_is_lost_whatever_password_opened_it() -> None:
    lost = _ConnectFailed(_Attempt(used_password=True))

    assert session_lost(lost)
    assert session_lost(_Stated("57P01"))
    assert not session_lost(_Stated("42501"))
    assert not session_lost(RuntimeError("not a driver failure"))


def test_a_reader_the_server_refuses_once_its_password_is_sent_fails_deferrable_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = _ConnectFailed(_Attempt(used_password=True))
    writer_pool, reader_pool = _pool(), _pool(checkout_error=refused)
    _opened_routes(monkeypatch, writer=writer_pool, reader=reader_pool)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed()

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError)
    assert cause.reason == "authentication_refused"
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)
