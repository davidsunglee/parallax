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
from collections.abc import Callable, Generator, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from time import monotonic
from typing import Any, ClassVar, cast

import psycopg
import psycopg_pool
import pytest
from psycopg.adapt import AdaptersMap
from psycopg.pq import TransactionStatus
from psycopg.rows import TupleRow, tuple_row

from parallax.core.base import INFINITY, PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
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
    ReleaseUnconfirmed,
    Returned,
    Row,
)
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresRole
from parallax.postgres._connection import ConnectionEstablishment, IncompatibleSessionError
from parallax.postgres._context import PostgresConnectionContext, release
from parallax.postgres._runtime import PROBE_SQL, PostgresRuntime, open_runtime
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
        close_error: Exception | None = None,
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


def _pool(*connections: _FakeConnection, **kwargs: Any) -> Any:
    return cast("Any", _FakePool(*connections, **kwargs))


def _runtime(pool: Any, options: Any = None) -> PostgresRuntime:
    return PostgresRuntime(
        pool, options if options is not None else PoolOptions(), _establishment()
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
        pool,
        admit if admit is not None else runtime._admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        deadline if deadline is not None else monotonic() + 5.0,
        _establishment(),
        role,
    )


def _login_context(runtime: PostgresRuntime) -> Any:
    return runtime.login_execution().new_context()


# --------------------------------------------------------------------------- #
# Readiness: only a runtime that has proved it can execute is returned.        #
# --------------------------------------------------------------------------- #


def _opened(monkeypatch: pytest.MonkeyPatch, pool: Any) -> Any:
    """Make ``open_runtime`` build ``pool`` rather than a native one."""
    from parallax.postgres import _runtime as runtime_module

    def build(*_args: object, **_kwargs: object) -> Any:
        return pool

    monkeypatch.setattr(runtime_module, "_build_pool", build)
    return pool


def test_startup_probes_a_real_connection_and_gives_it_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Waiting for a minimum is not readiness: it says a connection exists rather
    # than that a statement works. The probe reads an integer, a neutral
    # unbounded instant, a structured document, two exact floats, and the
    # authenticated login through the same initialized execution an application
    # gets.
    pool = _opened(monkeypatch, _pool())
    runtime = open_runtime("", PoolOptions(min_size=1), 5, DRIVER_MANAGED)

    assert pool.waits and pool.checkouts
    assert pool.returned and pool.returned[0].statements == [PROBE_SQL]
    # A ready runtime publishes its measurements; what one answers is
    # `test_pool_metrics.py`'s.
    assert runtime.pool_metrics is not None
    assert runtime.login_identity == "runtime-login"


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

    open_runtime("", PoolOptions(min_size=0), 5, DRIVER_MANAGED)

    assert intents == [True]


def test_a_zero_minimum_and_on_demand_wait_for_nothing_and_still_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Neither retains capacity, so a native wait would either return having
    # proved nothing or establish a connection of its own and throw it away.
    for options in (PoolOptions(min_size=0), OnDemandOptions()):
        pool = _opened(monkeypatch, _pool())
        open_runtime("", options, 5, DRIVER_MANAGED)
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
        open_runtime("", PoolOptions(), 5, DRIVER_MANAGED)

    assert failed.value.phase == "open"
    assert isinstance(failed.value.__cause__, psycopg_pool.PoolTimeout)


def test_a_minimum_that_is_not_reached_fails_at_its_own_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _opened(monkeypatch, _pool(wait_error=psycopg_pool.PoolTimeout("not filled")))

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=2), 5, DRIVER_MANAGED)

    assert failed.value.phase == "minimum_ready"
    assert pool.closes == 1


def test_a_configuration_every_connection_is_refused_under_is_named_rather_than_timed_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Filling happens on the pool's own background path, where an initialization
    # refusal is retried and logged where the waiting caller never sees it. A
    # bare "timed out" names nothing an operator can fix.
    from parallax.postgres import _runtime as runtime_module

    establishment = _establishment()
    refusal = IncompatibleSessionError("this connection's client encoding is 'LATIN1'")
    establishment.last_refusal = refusal
    pool = _pool(wait_error=psycopg_pool.PoolTimeout("not filled"))

    def build(*_args: object, **_kwargs: object) -> Any:
        return pool

    monkeypatch.setattr(runtime_module, "_build_pool", build)
    monkeypatch.setattr(runtime_module, "ConnectionEstablishment", lambda: establishment)

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=1), 5, DRIVER_MANAGED)

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
    from parallax.postgres import _runtime as runtime_module

    establishment = _establishment()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    establishment.last_refusal = refusal
    pool = _pool(wait_error=psycopg_pool.PoolTimeout("not filled"))

    def build(*_args: object, **_kwargs: object) -> Any:
        return pool

    monkeypatch.setattr(runtime_module, "_build_pool", build)
    monkeypatch.setattr(runtime_module, "ConnectionEstablishment", lambda: establishment)

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=1), 5, Password("hunter2"))

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
        open_runtime("", PoolOptions(min_size=0), 5, DRIVER_MANAGED)

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
        open_runtime("", PoolOptions(min_size=0), 5, DRIVER_MANAGED)

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
        open_runtime("", PoolOptions(min_size=0), 5, DRIVER_MANAGED)

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
        open_runtime("", PoolOptions(min_size=0), 5, DRIVER_MANAGED)

    assert failed.value.phase == "release"
    assert isinstance(failed.value.cleanup_result, ReleaseUnconfirmed)
    assert failed.value.__cause__ is None
    assert pool.closes == 1


def test_readiness_shares_one_budget_that_is_never_restarted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A budget that stops the next phase from starting: it cannot interrupt a
    # native call in flight, and it does not begin a phase it cannot finish.
    from parallax.postgres import _runtime as runtime_module

    clock = iter([0.0, 0.0, 0.5, 99.0, 99.0, 99.0, 99.0])
    monkeypatch.setattr(runtime_module, "monotonic", lambda: next(clock))
    _opened(monkeypatch, _pool())

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=1), 5, DRIVER_MANAGED)

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

    runtime = open_runtime("", PoolOptions(min_size=0, startup_timeout=30.0), 5, DRIVER_MANAGED)

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
        open_runtime("", PoolOptions(min_size=0, startup_timeout=30.0), 5, DRIVER_MANAGED)

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
        (psycopg.OperationalError("could not connect"), "preparation_failed"),
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
    establishment.last_refusal = refusal
    pool = _pool(checkout_error=psycopg_pool.PoolTimeout("waited"))
    runtime = _runtime(pool)
    resource = PostgresConnectionContext(
        pool,
        runtime._admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        monotonic() + 5.0,
        establishment,
        None,
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
    establishment.last_refusal = refusal
    pool = _pool(checkout_error=psycopg_pool.PoolTimeout("waited"))
    runtime = _runtime(pool)
    resource = PostgresConnectionContext(
        pool,
        runtime._admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        monotonic() + 5.0,
        establishment,
        None,
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "credentials_refused"
    assert refused.value.__cause__ is refusal
    assert "authenticated" in str(refused.value)


def test_a_successful_initialization_clears_the_refusal_on_record() -> None:
    establishment = _establishment()
    establishment.last_refusal = IncompatibleSessionError("earlier")
    establishment(cast("Any", _Initializable()))
    assert establishment.last_refusal is None


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
        pool,
        runtime._admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        monotonic() + 5.0,
        _establishment(),
        None,
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


def test_each_acquisition_yields_fresh_execution_access() -> None:
    pool = _pool()
    first = _context(pool)
    second = _context(pool)
    with first as one, second as two:
        assert one is not two


def test_authority_binding_and_context_creation_acquire_nothing() -> None:
    pool = _pool()
    runtime = _runtime(pool)

    source = runtime.principal_execution(PostgresRole("tenant_reader"))
    first = source.new_context()
    second = source.new_context()

    assert first is not second
    assert pool.checkouts == []
    assert not hasattr(runtime, "connection")


def test_principal_acquisition_installs_the_role_before_execution_and_resets_it_on_exit() -> None:
    connection = _FakeConnection()
    runtime = _runtime(_pool(connection))
    resource = runtime.principal_execution(PostgresRole("tenant_reader")).new_context()

    with resource as scoped:
        scoped.execute("select current_user", [])

    assert "SET ROLE" in connection.statements[0]
    assert "tenant_reader" in connection.statements[0]
    assert connection.statements[1:] == ["select current_user", "RESET ROLE"]
    assert resource.cleanup_result == Returned()


def test_role_installation_failure_is_an_authorization_refusal_and_disposes_the_session() -> None:
    failure = RuntimeError("role denied")
    connection = _FakeConnection(execute_error=failure)
    pool = _pool(connection)
    resource = _context(pool, role=PostgresRole("tenant_reader"))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.__cause__ is failure
    assert isinstance(resource.cleanup_result, Invalidated)
    assert connection.closes == 1
    assert "RESET ROLE" not in connection.statements


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


def test_reused_session_does_not_bleed_principal_authority_into_later_acquisitions() -> None:
    connection = _FakeConnection()
    runtime = _runtime(_pool(connection))

    with runtime.principal_execution(PostgresRole("reader_a")).new_context():
        pass
    with runtime.principal_execution(PostgresRole("reader_b")).new_context():
        pass
    with runtime.login_execution().new_context():
        pass

    assert (
        sum(
            "SET ROLE" in statement and statement != "RESET ROLE"
            for statement in connection.statements
        )
        == 2
    )
    assert connection.statements.count("RESET ROLE") == 2
    assert "reader_a" in connection.statements[0]
    assert "reader_b" in connection.statements[2]


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

        self.now = now
        monkeypatch.setattr(context_module, "monotonic", lambda: self.now)
        monkeypatch.setattr(runtime_module, "monotonic", lambda: self.now)


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
        rows = scoped.execute("select id from t where id = any(%s)", [[1, 2]], read_only=True)
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


def test_a_broken_first_begin_opens_once_more_and_runs_its_callback_once() -> None:
    # The disposed original receives the characteristics and no reset; the
    # replacement receives the same mapped requests, the one callback, and
    # alone the outer boundary's reset.
    broken = _FakeConnection(lost=_lost())
    fresh = _FakeConnection(rows=[])
    pool = _pool(broken, fresh)
    ran: list[str] = []

    def body(port: DatabaseConnection) -> list[Row]:
        ran.append("body")
        return port.execute("select 1", [])

    resource = _context(pool)
    with resource as scoped:
        outcome = scoped.transaction(body, isolation="serializable", access_mode="read_only")

    requested = [("isolation_level", psycopg.IsolationLevel.SERIALIZABLE), ("read_only", True)]
    assert outcome == Committed([])
    assert ran == ["body"]
    assert broken.statements == ["BEGIN"]
    assert broken.characteristics == requested
    assert fresh.statements == ["BEGIN", "select 1", "COMMIT"]
    assert fresh.characteristics == [*requested, ("isolation_level", None), ("read_only", None)]
    assert pool.returned == [broken, fresh]
    assert resource.cleanup_result == Returned()


def test_a_broken_first_read_pipeline_is_submitted_once_more_whole_on_a_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The batch is the protected submission, not its first member: the
    # replacement receives every statement with the binds adapted once for
    # the original, and the original is handed back before it is asked for.
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
    batch = (
        PipelineStatement("select id from a where id = any(%s)", ([1, 2],)),
        PipelineStatement("select id from b where id = %s", (3,)),
    )

    with resource as scoped:
        rows = scoped.execute_pipeline(batch, read_only=True)
        assert resource.cleanup_result is None
        assert pool.returned == [broken]

    assert rows == [[(1,)], [(1,)]]
    assert len(adaptations) == 2
    assert broken.statements == ["select id from a where id = any(%s)"]
    assert fresh.statements == [statement.sql for statement in batch]
    assert fresh.binds[0] is broken.binds[0]
    assert len(pool.checkouts) == 2
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


def _undesignated_pipeline(port: DatabaseConnection) -> object:
    return port.execute_pipeline((PipelineStatement("select 1"),))


def _began(port: DatabaseConnection) -> object:
    return port.transaction(_read)


@pytest.mark.parametrize(
    "submit",
    [_row_producing, _count_only, _undesignated_pipeline],
    ids=["row-producing-dml", "count-only", "undesignated-pipeline"],
)
def test_a_broken_first_submission_that_is_not_replay_safe_is_never_resubmitted(
    submit: Callable[[DatabaseConnection], object],
) -> None:
    # A defaulted row-producing statement, a write, and a batch submitted
    # without read intent are never repeated: each spends the opportunity and
    # fails as it always has.
    broken = _FakeConnection(lost=_lost())
    pool = _pool(broken, _FakeConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(DatabaseError) as failed:
        submit(scoped)

    assert isinstance(failed.value.__cause__, psycopg.OperationalError)
    assert len(pool.checkouts) == 1
    assert len(broken.statements) == 1
    assert pool.returned == [broken]
    assert _issues(resource.cleanup_result) == [("inspect", "not-idle")]


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
            scoped.execute("select * from child where root_id = any(%s)", [keys], read_only=True)

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
    runtime = _runtime(pool, PoolOptions(acquire_timeout=3.0))

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
    runtime = _runtime(pool, PoolOptions(acquire_timeout=3.0))
    with _login_context(runtime):
        pass
    (given,) = pool.checkouts
    assert given is not None and 0.0 < given <= 3.0


def test_close_holds_no_lock_across_a_checkout() -> None:
    # Admission stops under the lock and the native close runs outside it, so an
    # acquisition that blocks cannot block a close.
    pool = _pool()
    runtime = _runtime(pool)
    resource = _login_context(runtime)
    with resource:
        runtime.close()
    assert pool.closes == 1


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


def test_the_on_demand_policy_selects_the_native_null_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Which record is supplied selects which behavior the runtime has, so there
    # is no mode flag beside the settings to disagree with them.
    from parallax.postgres import _runtime as runtime_module

    built: list[str] = []

    class _Null(_FakePool):
        def __init__(self, *_args: object, **kwargs: object) -> None:
            super().__init__()
            built.append(type(self).__name__)
            assert "min_size" not in kwargs
            assert "max_idle" not in kwargs

        def open(self) -> None:
            return

    monkeypatch.setattr(psycopg_pool, "NullConnectionPool", _Null)
    runtime_module._build_pool(  # pyright: ignore[reportPrivateUsage] - the module-private pool builder is this test's subject
        "", OnDemandOptions(), 5, _establishment(), DRIVER_MANAGED
    )
    assert built == ["_Null"]


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
    from parallax.postgres import _runtime as runtime_module

    configured: list[dict[str, object]] = []

    class _Recording(_FakePool):
        def __init__(self, *_args: object, **kwargs: object) -> None:
            super().__init__()
            configured.append(kwargs)

        def open(self) -> None:
            return

    monkeypatch.setattr(psycopg_pool, native, _Recording)
    runtime_module._build_pool(  # pyright: ignore[reportPrivateUsage] - the module-private pool builder is this test's subject
        "", options, 5, _establishment(), DRIVER_MANAGED
    )
    (kwargs,) = configured
    assert "check" not in kwargs
    assert kwargs["configure"] is not None


def test_a_probe_that_answers_more_than_one_row_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(rows=[dict(_PROBE_ROW), dict(_PROBE_ROW)])
    _opened(monkeypatch, _pool(connection))

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=0), 5, DRIVER_MANAGED)

    assert failed.value.phase == "probe"
    assert str(failed.value) == "the startup probe returned 2 rows rather than one"


def test_a_probe_that_cannot_run_fails_startup_with_the_failure_as_its_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("the statement failed")
    _opened(monkeypatch, _pool(_FakeConnection(execute_error=failure)))

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=0), 5, DRIVER_MANAGED)

    assert failed.value.phase == "probe"
    assert str(failed.value) == (
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
        open_runtime("", PoolOptions(min_size=0), 5, DRIVER_MANAGED)

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
    from parallax.postgres import _runtime as runtime_module

    _opened(monkeypatch, _pool())
    monkeypatch.setattr(runtime_module, "monotonic", lambda: 1e18)

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=0), 5, DRIVER_MANAGED)

    assert failed.value.phase == "acquire"


def test_configuration_opens_the_runtime_it_describes(monkeypatch: pytest.MonkeyPatch) -> None:
    # What `open` delegates to, and with what, is only observable by calling it,
    # so this is the one place the suite spells the acquisition the access guard
    # exists to refuse — over a stub, reaching no server.
    from parallax.postgres import adapter as adapter_module

    opened: list[tuple[str, object, object, object]] = []

    def open_runtime_stub(
        conninfo: str, options: object, prepare_threshold: object, credentials: object
    ) -> object:
        opened.append((conninfo, options, prepare_threshold, credentials))
        return "the runtime"

    monkeypatch.setattr(adapter_module, "open_runtime", open_runtime_stub)
    source = Password("hunter2")
    configured = adapter_module.PostgresAdapter(
        "host=localhost", credentials=source, prepare_threshold=None
    )

    assert configured.open() == "the runtime"  # database-access: open_runtime is stubbed above
    assert opened == [("host=localhost", configured.pool, None, source)]


def test_leaving_a_context_that_was_never_entered_does_nothing() -> None:
    # Total on every exit: a context a caller built and abandoned has taken
    # nothing, so leaving it releases nothing and reports nothing.
    pool = _pool()
    resource = _context(pool)
    resource.__exit__(None, None, None)
    assert (pool.returned, resource.cleanup_result) == ([], None)


def test_a_document_read_folds_its_adjacent_cells_on_the_scoped_execution() -> None:
    # The document-read projection is the read path's, and it runs on the scoped
    # execution rather than anywhere a pool can see.
    connection = _FakeConnection(rows=[{"id": 1, "doc_present": True, "doc": {"a": 1}}])
    resource = _context(_pool(connection))
    with resource as scoped:
        rows = scoped.execute("select id, doc_present, doc from t", [], [(1, 2)])
    (row,) = rows
    assert row == (1, PresentDocument({"a": 1}))


# --------------------------------------------------------------------------- #
# The credential: resolved per physical connection, or not supplied at all.    #
# --------------------------------------------------------------------------- #


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


def _built_kwargs(monkeypatch: pytest.MonkeyPatch, credentials: Any) -> Any:
    """The ``kwargs`` ``_build_pool`` hands the native pool under ``credentials``."""
    from parallax.postgres import _runtime as runtime_module

    recorded: list[Any] = []

    class _Recording(_FakePool):
        def __init__(self, *_args: object, **kwargs: object) -> None:
            super().__init__()
            recorded.append(kwargs["kwargs"])

        def open(self) -> None:
            return

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", _Recording)
    runtime_module._build_pool(  # pyright: ignore[reportPrivateUsage] - the module-private pool builder is this test's subject
        "", PoolOptions(), 5, _establishment(), credentials
    )
    (kwargs,) = recorded
    return kwargs


def test_the_driver_managed_declaration_supplies_no_password_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Declaring it is how a deployment says the driver and the server settle
    # authentication between themselves, so what the pool gets is the static
    # dictionary this adapter would pass anyway, with nothing added to it.
    kwargs = _built_kwargs(monkeypatch, DRIVER_MANAGED)

    assert not callable(kwargs)
    assert "password" not in kwargs
    assert kwargs == {"autocommit": True, "row_factory": tuple_row, "prepare_threshold": 5}


@pytest.mark.parametrize("credentials", [Password("hunter2"), _Refusing(RuntimeError("no"))])
def test_any_source_makes_the_connection_keywords_a_per_connection_callable(
    monkeypatch: pytest.MonkeyPatch, credentials: Any
) -> None:
    # A constant password is a source like any other, so both take the late
    # path: nothing about the pool's configuration says which kind it holds.
    assert callable(_built_kwargs(monkeypatch, credentials))


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
    assert establishment.last_refusal is None


def test_a_source_that_refuses_records_its_own_refusal_and_re_raises_it() -> None:
    # The pool creates most connections on a background path, so the refusal
    # reaches a waiting caller only by being on record.
    establishment = _establishment()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    resolve = establishment.connect_kwargs(_base_kwargs(), _Refusing(refusal))

    with pytest.raises(CredentialResolutionError) as raised:
        resolve()

    assert raised.value is refusal
    assert establishment.last_refusal is refusal


def test_any_other_exception_a_source_raises_is_wrapped_with_fixed_text() -> None:
    # Classification must not depend on a provider's discipline, and the pool's
    # own warning line prints the exception's text — so what surfaces is fixed
    # text with the original chained beneath it.
    establishment = _establishment()
    native = RuntimeError("could not sign for hunter2")
    resolve = establishment.connect_kwargs(_base_kwargs(), _Refusing(native))

    with pytest.raises(CredentialResolutionError) as raised:
        resolve()

    assert str(raised.value) == "the credential source could not produce a password"
    assert "hunter2" not in str(raised.value)
    assert raised.value.__cause__ is native
    assert establishment.last_refusal is raised.value


def test_a_resolved_credential_leaves_a_refusal_on_record_until_a_connection_is_usable() -> None:
    # Several workers dial at once over one record. A credential resolved for
    # one attempt establishes nothing — that attempt can still fail to dial or
    # to initialize — so clearing there would let it erase another attempt's
    # completed refusal and hand the waiting caller a bare timeout instead.
    establishment = _establishment()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    establishment.last_refusal = refusal

    establishment.connect_kwargs(_base_kwargs(), Password("hunter2"))()

    assert establishment.last_refusal is refusal

    establishment(cast("Any", _Initializable()))

    assert establishment.last_refusal is None


# --------------------------------------------------------------------------- #
# The native release this adapter's documented behavior rests on.              #
# --------------------------------------------------------------------------- #


class _NativeStub:
    """What the INSTALLED native pool creates, hands on, and closes.

    The pins below drive `psycopg_pool` itself rather than a fake of it. Two of
    this adapter's documented behaviors are the library's rather than its own —
    on-demand establishment bounded by the remaining acquisition budget, and an
    on-demand release going to a waiting borrower instead of being closed — so a
    release that changed either would otherwise change what the adapter promises
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


@contextmanager
def _opened_null_pool() -> Generator[Any]:
    """An OPEN native null pool over the stub, closed again on the way out.

    Open rather than merely constructed, because "is a borrower waiting" is a
    question a closed pool answers by closing the connection whatever the queue
    holds — which would make the pin pass for the wrong reason.
    """
    pool = _native_null_pool()
    pool.open()
    try:
        yield pool
    finally:
        pool.close()


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


def test_the_installed_pool_resolves_callable_keywords_on_every_physical_connect() -> None:
    # The per-physical-connection contract is the library's behavior, not this
    # adapter's: `_connect` resolves a callable `kwargs` on each attempt. A
    # release that stopped doing so would silently freeze one credential.
    resolutions = iter(["first-token", "second-token"])
    pool = _native_null_pool(kwargs=lambda: {"password": next(resolutions)})

    pool._connect()
    pool._connect()

    assert [created["password"] for created in _NativeStub.connects] == [
        "first-token",
        "second-token",
    ]


def test_an_establishment_keyword_overrides_what_the_connection_string_asked_for() -> None:
    # The other half of the same claim: the derived limit is passed as a keyword,
    # and a keyword wins over the same setting in the connection string.
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    resolved = conninfo_to_dict(make_conninfo("connect_timeout=30", connect_timeout=4))

    assert resolved["connect_timeout"] == "4"


def test_an_on_demand_release_is_handed_to_a_waiting_borrower_rather_than_closed() -> None:
    # `OnDemandOptions` documents that releasing closes the connection UNLESS a
    # caller is already waiting, which is why it bounds concurrency without
    # promising a brand-new physical connection per operation.
    with _opened_null_pool() as unwatched:
        alone = unwatched._connect()
        unwatched._add_to_pool(alone)
        assert alone.closed is True

    with _opened_null_pool() as queued:
        queued._waiting.append(object())
        handed = queued._connect()

        assert queued._maybe_close_connection(handed) is False
        assert handed.closed is False
        queued._waiting.clear()
