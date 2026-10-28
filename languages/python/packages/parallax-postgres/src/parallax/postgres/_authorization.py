from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from psycopg.sql import SQL, Composed, Identifier

from parallax.core.db_port import InvalidAuthorizationError
from parallax.postgres._connection import (
    _complete_first_send,  # pyright: ignore[reportPrivateUsage] - the lease's shared first-send markers
    _start_first_send,  # pyright: ignore[reportPrivateUsage] - the lease's shared first-send markers
)

if TYPE_CHECKING:
    import psycopg
    from psycopg.rows import TupleRow

    from parallax.postgres._context import PostgresConnectionContext

__all__ = ["PostgresRole", "install_role", "restore_role"]


@dataclass(frozen=True, slots=True)
class PostgresRole:
    """A non-empty PostgreSQL role name bound to principal execution."""

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):  # pyright: ignore[reportUnnecessaryIsInstance] - validates untyped callers at the public boundary
            raise InvalidAuthorizationError("a PostgreSQL role name must be a string")
        if not self.name:
            raise InvalidAuthorizationError("a PostgreSQL role name must not be empty")


def _role_statement(role: PostgresRole) -> Composed:
    return SQL("SET ROLE {}").format(Identifier(role.name))


def _install_role(
    connection: psycopg.Connection[TupleRow],
    context: PostgresConnectionContext | None,
    statement: Composed,
) -> None:
    with connection.cursor() as cursor:
        _start_first_send(context)
        cursor.execute(statement)
        _complete_first_send(context)


def install_role(connection: Any, role: PostgresRole) -> None:
    _install_role(connection, None, _role_statement(role))


def restore_role(connection: Any) -> None:
    connection.execute("RESET ROLE")
