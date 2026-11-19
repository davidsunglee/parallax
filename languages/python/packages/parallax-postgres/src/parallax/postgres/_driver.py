from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

from psycopg.pq import TransactionStatus

from parallax.core.internal.base import INFINITY, UsageError
from parallax.core.internal.db_port import (
    AUTHORIZATION_INVALID,
    ConnectionLease,
    DialRecord,
    IdleReading,
    NotIdle,
    PoolPurpose,
    ProbeMismatch,
    Route,
    Row,
    SubmissionProgress,
)
from parallax.core.internal.dialect import POSTGRES
from parallax.postgres._authorization import (
    PostgresRole,
    install_setup,
    restore_role,
    role_statement,
    statement_timeout,
)
from parallax.postgres._connection import (
    NativeConnection,
    PostgresConnection,
    _execute_rows,  # pyright: ignore[reportPrivateUsage] - the one read operation, submitting the proof
)
from parallax.postgres._failures import is_session_broken, is_session_lost
from parallax.postgres._pool import PostgresPool, open_pool

if TYPE_CHECKING:
    from parallax.postgres._adapter import PostgresAdapter

__all__ = ["PROBE_SQL", "PostgresDriver"]

PROBE_SQL: Final = """SELECT
    1 AS ready,
    'infinity'::timestamptz AS temporal_bound,
    '{"ready": true}'::jsonb AS document,
    '7.038530691851209e-26'::float8::real AS float32_witness,
    0.30000000000000004::float8 AS float64_witness,
    session_user AS login_identity"""
"""The one statement that proves a route can serve.

It proves the decodings the read path cannot work without and that a bare
connectivity check does not exercise: an ordinary integer, the neutral sentinel a
temporal interval's open upper bound reads back as, a structured document
decoded to a mapping, and two floats that come back exactly only when the server
spells floats without rounding them. It also captures the authenticated
``session_user`` that database-login execution projects as its identity, and
that every other route must match. It reads no model, opens no explicit
transaction, and registers nothing — the connection it runs on was already
initialized like every other. It is a smoke probe, not a substitute for the
codec suites.

The Float64 witness needs all 17 significant digits. The Float32 witness is one
whose shortest spelling, parsed to the nearest binary64 and then narrowed, lands
on the adjacent binary32 value, so it also reads back exactly only through the
adapter's own Float32 loader.
"""

_PROBE: Final = PROBE_SQL.encode()
_FLOAT32_WITNESS: Final = 7.038530691851209e-26
_FLOAT64_WITNESS: Final = 0.30000000000000004
_ROUNDED_FLOATS = (
    "the session's extra_float_digits is at or below zero, so the server rounds float "
    "output, which no loader can recover; set it to 1 or more"
)
_OTHER_LOGIN = "the reader route authenticated a different database login than the writer"
_NOT_A_ROLE = "PostgreSQL principal execution requires a PostgresRole"


def _check_probe(rows: list[Row], expected_login: str | None) -> str:
    """The login the probe's ``rows`` authenticated, or :class:`ProbeMismatch`.

    ``expected_login``, where given, is the login every route must share.
    """
    if len(rows) != 1:
        raise ProbeMismatch(f"the startup probe returned {len(rows)} rows rather than one")
    (row,) = rows
    if len(row) != 6:
        raise ProbeMismatch(f"the startup probe returned {len(row)} columns rather than six")
    if row[0] != 1:
        raise ProbeMismatch("the startup probe did not read its integer back")
    if row[1] is not INFINITY:
        raise ProbeMismatch("the startup probe did not read an unbounded instant back")
    if row[2] != {"ready": True}:
        raise ProbeMismatch("the startup probe did not read its structured document back")
    if row[4] != _FLOAT64_WITNESS:
        raise ProbeMismatch(
            f"the startup probe did not read its Float64 back exactly: {_ROUNDED_FLOATS}"
        )
    if row[3] != _FLOAT32_WITNESS:
        raise ProbeMismatch(
            f"the startup probe did not read its Float32 back exactly: either the adapter's "
            f"Float32 loader is not installed, or {_ROUNDED_FLOATS}"
        )
    login = row[5]
    if not isinstance(login, str) or not login:
        raise ProbeMismatch("the startup probe did not read a nonempty session_user")
    if expected_login is not None and login != expected_login:
        raise ProbeMismatch(_OTHER_LOGIN)
    return login


class PostgresDriver:
    """The native parts the runtime serves one :class:`PostgresAdapter` configuration with.

    It reads endpoints, credentials, retention, and the prepared-statement
    threshold from the configuration it was given, never from copies of them,
    and the acquisition timeout that is the runtime's budget is also each
    native pool's own timeout.
    """

    __slots__ = ("_configuration",)

    def __init__(self, configuration: PostgresAdapter) -> None:
        self._configuration = configuration

    def open_pool(
        self, route: Route, purpose: PoolPurpose, dial_record: DialRecord
    ) -> PostgresPool:
        configuration = self._configuration
        endpoint = configuration.writer if route == "writer" else configuration.reader
        if endpoint is None:
            raise ValueError("no reader endpoint is configured")
        return open_pool(
            endpoint,
            route,
            purpose,
            dial_record,
            acquire_timeout=configuration.acquire_timeout,
            prepare_threshold=configuration.prepare_threshold,
        )

    def open_execution(self, lease: ConnectionLease[NativeConnection]) -> PostgresConnection:
        return PostgresConnection(lease)

    def authorization(self, value: object, /) -> PostgresRole:
        if not isinstance(value, PostgresRole):
            raise UsageError(AUTHORIZATION_INVALID, _NOT_A_ROLE)
        return value

    def read_idle(self, connection: NativeConnection) -> IdleReading:
        try:
            status = TransactionStatus(connection.pgconn.transaction_status)
        except Exception:
            return "unreadable"
        return "idle" if status == TransactionStatus.IDLE else NotIdle(status.name)

    def close_connection(self, connection: NativeConnection) -> None:
        connection.close()

    def is_session_broken(self, connection: NativeConnection, failure: BaseException) -> bool:
        return is_session_broken(connection, failure)

    def is_session_lost(self, failure: BaseException) -> bool:
        return is_session_lost(failure)

    def prove_readiness(
        self,
        connection: NativeConnection,
        submission: SubmissionProgress,
        expected_login: str | None,
    ) -> str:
        no_binds: list[object] = []
        rows = _execute_rows(connection, submission, POSTGRES, _PROBE, no_binds, ())
        return _check_probe(rows, expected_login)

    def install_authorization(
        self,
        connection: NativeConnection,
        submission: SubmissionProgress,
        authorization: PostgresRole,
    ) -> None:
        install_setup(connection, submission, role_statement(authorization))

    def restore_authorization(self, connection: NativeConnection) -> None:
        restore_role(connection)

    def limit_statement_time(
        self, connection: NativeConnection, submission: SubmissionProgress, seconds: float
    ) -> None:
        """Install ``seconds`` as the session's ``statement_timeout``, rounded up
        to whole milliseconds and never below one, because zero is the
        setting's spelling of no limit at all."""
        milliseconds = max(1, math.ceil(seconds * 1000))
        install_setup(connection, submission, statement_timeout(milliseconds))
