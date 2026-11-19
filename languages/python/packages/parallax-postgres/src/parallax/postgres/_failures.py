from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import psycopg

from parallax.core.internal.db_port import CredentialResolutionError, DialReason

if TYPE_CHECKING:
    from psycopg.rows import TupleRow

__all__ = ["dial_reason", "is_session_broken", "is_session_lost"]


def dial_reason(failure: BaseException) -> DialReason:
    """Classify one failure met while establishing a connection.

    Connection SQLSTATEs, a server at its connection limit, and a driver
    failure to reach the server are unavailable. With no SQLSTATE, a capacity
    message takes precedence over the driver's indication that it sent a
    password. A password sent otherwise means the server refused the login
    or, when its message identifies a missing database, preparation failed.
    A codeless failure with no password sent leaves the route unavailable.

    Only a dial is classified here: a failure on an established session
    reports the password that session was opened with, which says nothing
    about why it ended; :func:`is_session_lost` reads those.
    """
    if isinstance(failure, CredentialResolutionError):
        return "credentials_refused"
    if isinstance(failure, psycopg.OperationalError):
        state = failure.sqlstate
        if state is None:
            message = _fatal_dial_message(failure)
            match: DialReason | None = next(
                (
                    reason
                    for pattern, reason in _SERVER_DIAL_MESSAGES.values()
                    if pattern.match(message)
                ),
                None,
            )
            if match == "unavailable" or _offered_password(failure):
                return "authentication_refused" if match is None else match
            return "unavailable"
        if state.startswith("08") or state in _UNAVAILABLE_DIAL_STATES:
            return "unavailable"
        if state.startswith("28"):
            return "authentication_refused"
    return "preparation_failed"


def is_session_broken(connection: psycopg.Connection[TupleRow], failure: BaseException) -> bool:
    """Whether ``failure`` left ``connection`` unusable: a driver failure after
    which the driver reports the connection closed, as it does once libpq
    finds the socket gone. An error's code alone says nothing about that."""
    return isinstance(failure, psycopg.Error) and connection.closed


def is_session_lost(failure: BaseException) -> bool:
    """Whether a failure on an established session says the session itself ended.

    That is a driver connection failure with no SQLSTATE or a connection-class
    one, or a server going away, rather than anything a statement provoked.
    """
    if not isinstance(failure, psycopg.OperationalError):
        return False
    state = failure.sqlstate
    return state is None or state.startswith("08") or state in _SERVER_GONE


def _offered_password(failure: psycopg.OperationalError) -> bool:
    try:
        attempt = failure.pgconn
        return attempt is not None and bool(attempt.used_password)
    except Exception:
        return False


_LIBPQ_DIAL_PREFIX: Final = re.compile(
    rb'^connection to server (?:at "[^\n]*?"(?: \([^\n)]+\))?, port [^\n]+?'
    rb'|on socket "[^\n]*?") failed: ',
    re.MULTILINE,
)


def _fatal_dial_message(failure: psycopg.OperationalError) -> str:
    try:
        attempt = failure.pgconn
        if attempt is None:
            return ""
        message = attempt.error_message
        # The startup packet's names are truncated to 63 bytes on the server.
        # A newline in one of these quoted values cannot start another report.
        for name in (attempt.user[:63], attempt.db[:63]):
            if b"\n" in name:
                quoted = b'"' + name + b'"'
                message = message.replace(quoted, quoted.replace(b"\n", b"\0"))
    except Exception:
        return ""

    reports = _LIBPQ_DIAL_PREFIX.split(message)
    latest = reports[-1].removesuffix(b"\n")
    marker = b"FATAL:  "
    if len(reports) == 1 and not latest.startswith(marker):
        # A localized libpq wrapper may still carry an English server message.
        before, found, detail = latest.rsplit(b"\n", 1)[-1].partition(marker)
        if found and before.endswith(b": "):
            latest = found + detail
    if latest.startswith(marker):
        return latest.removeprefix(marker).replace(b"\0", b"\n").decode("utf-8", "replace")
    return ""


_SERVER_DIAL_MESSAGES: Final[dict[str, tuple[re.Pattern[str], DialReason]]] = {
    "server-full": (re.compile(r"sorry, too many clients already"), "unavailable"),
    "connection-limit": (
        re.compile(r'too many connections for (?:role|database) "'),
        "unavailable",
    ),
    "reserved-slots": (re.compile(r"remaining connection slots are reserved for"), "unavailable"),
    # The server prints the database name unescaped, including any double quotes.
    "missing-database": (re.compile(r'database ".*" does not exist\Z'), "preparation_failed"),
}
_CANNOT_CONNECT_NOW: Final = "57P03"
_UNAVAILABLE_DIAL_STATES: Final = frozenset({_CANNOT_CONNECT_NOW, "53300"})
_SERVER_GONE: Final = frozenset({_CANNOT_CONNECT_NOW, "57P01", "57P02"})
