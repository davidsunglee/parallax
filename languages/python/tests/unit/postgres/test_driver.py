"""The native parts the runtime serves a Postgres configuration with.

Everything here is what a psycopg connection says, or what the adapter sends
it: which endpoint a pool dials, how a session's state and failures read, what
the readiness probe must decode, and the setup statements authorization and
statement bounds are spelled as. What the runtime does with each answer is the
policy suite's, over a scripted driver.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import psycopg
import pytest
from psycopg.pq import TransactionStatus
from psycopg.sql import Composable

from parallax.core.internal.base import INFINITY, UsageError
from parallax.core.internal.db_port import (
    AUTHORIZATION_INVALID,
    DialRecord,
    NotIdle,
    Password,
    PoolPurpose,
    ProbeMismatch,
    Route,
    RouteCapabilities,
    SubmissionProgress,
)
from parallax.core.internal.db_port._runtime._dial_record import DialLedger
from parallax.core.internal.dialect import POSTGRES
from parallax.postgres import (
    OnDemandOptions,
    PoolOptions,
    PostgresAdapter,
    PostgresEndpoint,
    PostgresRole,
)
from parallax.postgres._connection import DirectLease, NativeConnection, PostgresConnection
from parallax.postgres._driver import PROBE_SQL, PostgresDriver

_PROBE_ROW: tuple[object, ...] = (
    1,
    INFINITY,
    {"ready": True},
    7.038530691851209e-26,
    0.30000000000000004,
    "runtime-login",
)


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection
        self.description: object | None = None

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: bytes | Composable, binds: object = None) -> None:
        del binds
        connection = self._connection
        connection.sent.append(
            statement.as_string() if isinstance(statement, Composable) else statement.decode()
        )
        if connection.failure is not None:
            raise connection.failure
        self.description = () if connection.rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._connection.rows


class _PgConn:
    def __init__(self) -> None:
        self.status: TransactionStatus | Exception = TransactionStatus.IDLE

    @property
    def transaction_status(self) -> TransactionStatus:
        status = self.status
        if isinstance(status, Exception):
            raise status
        return status


class _Connection:
    """The psycopg connection surface the driver touches."""

    def __init__(
        self, *, rows: Sequence[tuple[object, ...]] = (), failure: Exception | None = None
    ) -> None:
        self.rows = list(rows)
        self.failure = failure
        self.pgconn = _PgConn()
        self.sent: list[str] = []
        self.closed = False

    def cursor(self, **_options: object) -> _Cursor:
        return _Cursor(self)

    def execute(self, statement: str) -> None:
        self.sent.append(statement)
        if self.failure is not None:
            raise self.failure

    def close(self) -> None:
        self.closed = True


def _native(connection: _Connection) -> NativeConnection:
    return cast("NativeConnection", connection)


def _driver(**configuration: Any) -> PostgresDriver:
    endpoint = PostgresEndpoint("host=writer", credentials=Password("hunter2"))
    return PostgresDriver(
        PostgresAdapter(writer=configuration.pop("writer", endpoint), **configuration)
    )


# --------------------------------------------------------------------------- #
# Pools and execution.                                                         #
# --------------------------------------------------------------------------- #


def test_each_pool_dials_its_route_s_endpoint_under_the_configured_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _driver as driver_module

    opened: list[tuple[object, ...]] = []

    def open_pool(
        endpoint: PostgresEndpoint,
        route: Route,
        purpose: PoolPurpose,
        dial_record: DialRecord,
        *,
        acquire_timeout: float,
        prepare_threshold: int | None,
    ) -> object:
        opened.append((endpoint, route, purpose, dial_record, acquire_timeout, prepare_threshold))
        return "the pool"

    monkeypatch.setattr(driver_module, "open_pool", open_pool)
    writer = PostgresEndpoint("host=writer", credentials=Password("hunter2"), pool=PoolOptions())
    reader = PostgresEndpoint(
        "host=reader", credentials=Password("hunter2"), pool=OnDemandOptions()
    )
    driver = _driver(writer=writer, reader=reader, acquire_timeout=3.0, prepare_threshold=None)
    record = DialLedger()

    for route, purpose in (
        ("writer", "application"),
        ("reader", "application"),
        ("writer", "reservation"),
    ):
        assert (
            driver.open_pool(cast("Route", route), cast("PoolPurpose", purpose), record)
            == "the pool"
        )

    assert opened == [
        (writer, "writer", "application", record, 3.0, None),
        (reader, "reader", "application", record, 3.0, None),
        (writer, "writer", "reservation", record, 3.0, None),
    ]


def test_a_reader_pool_is_refused_where_no_reader_is_configured() -> None:
    with pytest.raises(ValueError, match="no reader endpoint"):
        _driver().open_pool("reader", "application", DialLedger())


def test_execution_is_a_fresh_facade_over_the_lease_it_is_opened_with() -> None:
    connection = _Connection()
    lease = DirectLease(_native(connection))
    driver = _driver()

    execution = driver.open_execution(lease)

    assert isinstance(execution, PostgresConnection)
    assert execution is not driver.open_execution(lease)
    assert execution.execute("select 1", []) == []
    assert connection.sent == ["select 1"]
    assert execution.revoke() is False


def test_only_a_postgres_role_is_an_authorization_and_the_refusal_names_why() -> None:
    driver = _driver()
    role = PostgresRole("tenant_reader")

    assert driver.authorization(role) is role
    with pytest.raises(UsageError) as refused:
        driver.authorization("tenant_reader")

    assert refused.value.code == AUTHORIZATION_INVALID
    assert str(refused.value).endswith("PostgreSQL principal execution requires a PostgresRole")


# --------------------------------------------------------------------------- #
# What a session's state and failures say.                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("status", "reading"),
    [
        (TransactionStatus.IDLE, "idle"),
        (TransactionStatus.INTRANS, NotIdle("INTRANS")),
        (TransactionStatus.UNKNOWN, NotIdle("UNKNOWN")),
        (RuntimeError("the state is gone"), "unreadable"),
    ],
)
def test_a_session_s_idle_reading_names_its_state(
    status: TransactionStatus | Exception, reading: object
) -> None:
    connection = _Connection()
    connection.pgconn.status = status

    assert _driver().read_idle(_native(connection)) == reading


def test_closing_a_connection_closes_it_natively() -> None:
    connection = _Connection()

    _driver().close_connection(_native(connection))

    assert connection.closed


def test_the_session_predicates_are_the_failure_classification_s() -> None:
    driver = _driver()
    lost = psycopg.OperationalError("server closed the connection unexpectedly")
    connection = _Connection()

    assert not driver.is_session_broken(_native(connection), lost)
    connection.closed = True
    assert driver.is_session_broken(_native(connection), lost)
    assert driver.is_session_lost(lost)
    assert not driver.is_session_lost(psycopg.errors.InsufficientPrivilege("denied"))


# --------------------------------------------------------------------------- #
# The readiness probe.                                                         #
# --------------------------------------------------------------------------- #


def _prove(rows: Sequence[tuple[object, ...]], expected_login: str | None) -> str:
    """What a proof reading back ``rows`` answers."""
    connection = _native(_Connection(rows=rows))
    return _driver().prove_readiness(connection, SubmissionProgress(), expected_login)


def test_a_proof_submits_the_probe_once_and_answers_its_login() -> None:
    connection = _Connection(rows=[_PROBE_ROW])
    submission = SubmissionProgress()

    login = _driver().prove_readiness(_native(connection), submission, "runtime-login")

    assert login == "runtime-login"
    assert connection.sent == [PROBE_SQL]
    assert (submission.started, submission.answered) == (True, True)


def test_a_proof_whose_probe_fails_raises_the_raw_driver_failure_unanswered() -> None:
    failure = psycopg.OperationalError("server closed the connection unexpectedly")
    submission = SubmissionProgress()

    with pytest.raises(psycopg.OperationalError) as raised:
        _driver().prove_readiness(_native(_Connection(failure=failure)), submission, None)

    assert raised.value is failure
    assert (submission.started, submission.answered) == (True, False)


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_PROBE_ROW, _PROBE_ROW],
        [_PROBE_ROW[:5]],
        [(0, *_PROBE_ROW[1:])],
        [(1, "2026-01-01", *_PROBE_ROW[2:])],
        [(*_PROBE_ROW[:2], "not a document", *_PROBE_ROW[3:])],
        [(*_PROBE_ROW[:5], "")],
        [(*_PROBE_ROW[:5], 7)],
    ],
)
def test_a_probe_that_does_not_read_back_what_it_asked_for_is_a_mismatch(
    rows: list[tuple[object, ...]],
) -> None:
    with pytest.raises(ProbeMismatch):
        _prove(rows, None)


def test_a_probe_that_answers_more_than_one_row_says_how_many() -> None:
    with pytest.raises(ProbeMismatch, match="returned 2 rows rather than one"):
        _prove([_PROBE_ROW, _PROBE_ROW], None)


@pytest.mark.parametrize(
    ("ordinal", "decoded", "names_the_loader"),
    [
        # What `extra_float_digits = 0` spells the Float64 witness as.
        (4, 0.3, False),
        # The Float32 witness's shortest spelling parsed and then narrowed: what
        # a plain float loader reads, whatever the session setting.
        (3, 7.038531308148791e-26, True),
    ],
)
def test_a_probe_that_reads_a_float_back_inexactly_names_what_rounds_it(
    ordinal: int, decoded: float, names_the_loader: bool
) -> None:
    row = list(_PROBE_ROW)
    row[ordinal] = decoded

    with pytest.raises(ProbeMismatch) as mismatch:
        _prove([tuple(row)], None)

    reason = str(mismatch.value)
    assert "extra_float_digits is at or below zero" in reason
    assert ("Float32 loader is not installed" in reason) is names_the_loader


def test_a_probe_reading_another_login_than_the_one_every_route_shares_is_a_mismatch() -> None:
    assert _prove([_PROBE_ROW], None) == "runtime-login"
    with pytest.raises(ProbeMismatch, match="different database login"):
        _prove([_PROBE_ROW], "writer-login")


# --------------------------------------------------------------------------- #
# Session setup.                                                               #
# --------------------------------------------------------------------------- #


def test_an_authorization_is_installed_as_its_role_in_one_submission() -> None:
    connection = _Connection()
    submission = SubmissionProgress()

    role = PostgresRole('tenant"; reset role; --')

    _driver().install_authorization(_native(connection), submission, role)

    assert connection.sent == ['SET ROLE "tenant""; reset role; --"']
    assert (submission.started, submission.answered) == (True, True)


def test_a_refused_authorization_has_started_and_is_unanswered() -> None:
    connection = _Connection(failure=psycopg.errors.InsufficientPrivilege("denied"))
    submission = SubmissionProgress()

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _driver().install_authorization(_native(connection), submission, PostgresRole("tenant"))

    assert (submission.started, submission.answered) == (True, False)


def test_restoring_authorization_resets_the_role() -> None:
    connection = _Connection()

    _driver().restore_authorization(_native(connection))

    assert connection.sent == ["RESET ROLE"]


@pytest.mark.parametrize(
    ("seconds", "milliseconds"),
    [(5.0, 5000), (2.0001, 2001), (0.0001, 1), (0.0, 1), (-1.0, 1)],
)
def test_a_statement_bound_rounds_up_to_whole_milliseconds_and_never_to_no_limit(
    seconds: float, milliseconds: int
) -> None:
    connection = _Connection()
    submission = SubmissionProgress()

    _driver().limit_statement_time(_native(connection), submission, seconds)

    assert connection.sent == [f"SET statement_timeout = {milliseconds}"]
    assert (submission.started, submission.answered) == (True, True)


# --------------------------------------------------------------------------- #
# Composition.                                                                 #
# --------------------------------------------------------------------------- #


def test_configuration_composes_its_runtime_from_its_driver_and_its_declared_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # What `open` delegates to, and with what, is only observable by calling it,
    # so this is the one place the suite spells the acquisition the access guard
    # exists to refuse — over a stub, reaching no server.
    from parallax.postgres import _adapter as adapter_module

    composed: list[tuple[object, ...]] = []

    def open_runtime_stub(driver: object, /, **arguments: object) -> object:
        composed.append((driver, arguments))
        return "the runtime"

    monkeypatch.setattr(adapter_module, "open_runtime", open_runtime_stub)
    writer = PostgresEndpoint("host=localhost", credentials=Password("hunter2"))
    reader = PostgresEndpoint("host=replica", credentials=Password("hunter2"))
    single = PostgresAdapter(writer=writer, acquire_timeout=2.0, startup_timeout=4.0)
    deferred = PostgresAdapter(writer=writer, reader=reader)
    required = PostgresAdapter(writer=writer, reader=reader, reader_startup="required")

    for configured in (single, deferred, required):
        assert configured.open() == "the runtime"  # database-access: open_runtime is stubbed above

    every = RouteCapabilities.every_level()
    # A hot standby refuses SERIALIZABLE, so the reader never declares it.
    standby = RouteCapabilities(frozenset({"read_committed", "repeatable_read"}))
    assert all(isinstance(driver, PostgresDriver) for driver, _ in composed)
    # An omitted reader_startup defers a configured reader.
    assert [arguments for _, arguments in composed] == [
        {
            "dialect": POSTGRES,
            "routes": {"writer": every},
            "acquire_timeout": 2.0,
            "startup_timeout": 4.0,
            "reader_startup": "deferrable",
        },
        {
            "dialect": POSTGRES,
            "routes": {"writer": every, "reader": standby},
            "acquire_timeout": 15.0,
            "startup_timeout": 30.0,
            "reader_startup": "deferrable",
        },
        {
            "dialect": POSTGRES,
            "routes": {"writer": every, "reader": standby},
            "acquire_timeout": 15.0,
            "startup_timeout": 30.0,
            "reader_startup": "required",
        },
    ]
