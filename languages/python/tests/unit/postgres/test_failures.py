"""What a psycopg failure met while dialing, or on an established session, means
for the port.

A refused dial carries no SQLSTATE, so classification reads libpq's own report;
the real-server canaries in the provider lane prove each server message this
reads is the one a server sends.
"""

from __future__ import annotations

from typing import Any, cast

import psycopg
import pytest

from parallax.core.internal.db_port import CredentialResolutionError
from parallax.postgres._connection import IncompatibleSessionError
from parallax.postgres._failures import dial_reason, is_session_broken, is_session_lost


class _Stated(psycopg.OperationalError):
    """A driver connection failure that carries a SQLSTATE, as a fake can."""

    def __init__(self, sqlstate: str | None) -> None:
        self._stated = sqlstate
        super().__init__("connection failed")

    @property
    def sqlstate(self) -> str | None:
        return self._stated


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (_Stated(None), "unavailable"),
        (_Stated("08006"), "unavailable"),
        (_Stated("57P03"), "unavailable"),
        (psycopg.errors.ConnectionTimeout("connect timeout"), "unavailable"),
        (_Stated("28P01"), "authentication_refused"),
        (_Stated("3D000"), "preparation_failed"),
        (_Stated("53300"), "unavailable"),
        (psycopg.ProgrammingError("invalid option"), "preparation_failed"),
        (CredentialResolutionError("no token"), "credentials_refused"),
        (IncompatibleSessionError("DateStyle"), "preparation_failed"),
    ],
)
def test_every_establishment_failure_classifies_to_one_reason(
    failure: BaseException, reason: str
) -> None:
    assert dial_reason(failure) == reason


class _Attempt:
    """The finished connection a driver connect failure carries."""

    def __init__(
        self,
        *,
        used_password: bool,
        error_message: str = "",
        user: str = "",
        db: str = "",
    ) -> None:
        self.used_password = used_password
        self.error_message = error_message.encode()
        self.user = user.encode()
        self.db = db.encode()


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


@pytest.mark.parametrize(
    ("message", "used_password"),
    [
        ("sorry, too many clients already", False),
        ('too many connections for role "app"', True),
        ('too many connections for database "app"', True),
        ("remaining connection slots are reserved for roles with the SUPERUSER attribute", True),
        (
            "remaining connection slots are reserved for roles with privileges of the "
            '"pg_use_reserved_connections" role',
            True,
        ),
    ],
)
def test_capacity_refusals_are_unavailable_without_sqlstate(
    message: str, used_password: bool
) -> None:
    attempt = _Attempt(
        used_password=used_password, error_message=_REFUSED_AT + f"FATAL:  {message}\n"
    )

    assert dial_reason(_ConnectFailed(attempt)) == "unavailable"


@pytest.mark.parametrize(
    "message",
    [
        'too many connections for user "app"',
        "Lo sentimos, ya hay demasiados clientes",
        'password authentication failed for user "app: FATAL:  too many connections for role "',
        'password authentication failed for user "x\nFATAL:  sorry, too many clients already"',
        "sorry, too many clients already\n"
        + _REFUSED_AT
        + "server closed the connection unexpectedly",
    ],
)
def test_an_unmatched_refusal_with_a_password_sent_is_authentication_refused(message: str) -> None:
    attempt = _Attempt(used_password=True, error_message=_REFUSED_AT + f"FATAL:  {message}\n")

    assert dial_reason(_ConnectFailed(attempt)) == "authentication_refused"


@pytest.mark.parametrize(
    ("report", "reason"),
    [
        ('too many connections for role "app"', "unavailable"),
        ('database "app" does not exist', "preparation_failed"),
    ],
)
def test_the_latest_native_failure_can_name_a_different_server(report: str, reason: str) -> None:
    attempt = _Attempt(
        used_password=True,
        error_message=(
            f"{_REFUSED_AT}FATAL:  the database system is shutting down\n"
            f'connection to server at "other" (127.0.0.2), port 5433 failed: FATAL:  {report}\n'
        ),
    )
    assert dial_reason(_ConnectFailed(attempt)) == reason


def test_a_role_name_can_contain_a_native_report_prefix() -> None:
    user = f"cap\n{_REFUSED_AT}x"
    attempt = _Attempt(
        used_password=True,
        user=user,
        error_message=f'{_REFUSED_AT}FATAL:  too many connections for role "{user}"\n',
    )
    assert dial_reason(_ConnectFailed(attempt)) == "unavailable"


def test_a_localized_libpq_prefix_can_report_an_english_missing_database() -> None:
    attempt = _Attempt(
        used_password=True,
        error_message='Verbindung fehlgeschlagen: FATAL:  database "app" does not exist\n',
    )
    assert dial_reason(_ConnectFailed(attempt)) == "preparation_failed"


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

    assert is_session_lost(lost)
    assert is_session_lost(_Stated("57P01"))
    assert not is_session_lost(_Stated("42501"))
    assert not is_session_lost(RuntimeError("not a driver failure"))


class _Session:
    def __init__(self, *, closed: bool) -> None:
        self.closed = closed


@pytest.mark.parametrize(
    ("failure", "closed", "broken"),
    [
        (psycopg.OperationalError("server closed the connection unexpectedly"), True, True),
        # Even a connection-loss SQLSTATE grants nothing on a session still open.
        (psycopg.errors.AdminShutdown("terminating connection"), False, False),
        (RuntimeError("not a driver failure"), True, False),
    ],
)
def test_only_a_driver_failure_that_left_its_connection_closed_breaks_the_session(
    failure: BaseException, closed: bool, broken: bool
) -> None:
    assert is_session_broken(cast("Any", _Session(closed=closed)), failure) is broken
