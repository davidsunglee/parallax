from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from psycopg.sql import SQL, Composed, Identifier, Literal

from parallax.core.internal.base import UsageError
from parallax.core.internal.db_port import AUTHORIZATION_INVALID
from parallax.postgres._connection import (
    _complete_first_send,  # pyright: ignore[reportPrivateUsage] - the lease's shared first-send markers
    _start_first_send,  # pyright: ignore[reportPrivateUsage] - the lease's shared first-send markers
)

if TYPE_CHECKING:
    import psycopg
    from psycopg.rows import TupleRow

    from parallax.postgres._context import PostgresConnectionContext

__all__ = ["PostgresRole", "install_role", "restore_role", "statement_timeout"]


@dataclass(frozen=True, slots=True)
class PostgresRole:
    """A non-empty PostgreSQL role name bound to principal execution."""

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):  # pyright: ignore[reportUnnecessaryIsInstance] - validates untyped callers at the public boundary
            raise UsageError(AUTHORIZATION_INVALID, "a PostgreSQL role name must be a string")
        if not self.name:
            raise UsageError(AUTHORIZATION_INVALID, "a PostgreSQL role name must not be empty")


def _role_statement(role: PostgresRole) -> Composed:
    return SQL("SET ROLE {}").format(Identifier(role.name))


def statement_timeout(milliseconds: int) -> Composed:
    return SQL("SET statement_timeout = {}").format(Literal(milliseconds))


def _install_setup(
    connection: psycopg.Connection[TupleRow],
    context: PostgresConnectionContext | None,
    statement: Composed,
) -> None:
    """Run one session setup statement as the lease's possible first send."""
    with connection.cursor() as cursor:
        _start_first_send(context)
        cursor.execute(statement)
        _complete_first_send(context)


def install_role(connection: Any, role: PostgresRole) -> None:
    _install_setup(connection, None, _role_statement(role))


def restore_role(connection: Any) -> None:
    connection.execute("RESET ROLE")
