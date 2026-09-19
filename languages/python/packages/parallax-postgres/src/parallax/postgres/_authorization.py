"""PostgreSQL execution authority values."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from psycopg.sql import SQL, Identifier

from parallax.core.db_port import InvalidAuthorizationError

__all__ = ["PostgresRole"]


@dataclass(frozen=True, slots=True)
class PostgresRole:
    """A non-empty PostgreSQL role name bound to principal execution."""

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):  # pyright: ignore[reportUnnecessaryIsInstance] - validates untyped callers at the public boundary
            raise InvalidAuthorizationError("a PostgreSQL role name must be a string")
        if not self.name:
            raise InvalidAuthorizationError("a PostgreSQL role name must not be empty")


def install_role(connection: Any, role: PostgresRole) -> None:
    connection.execute(SQL("SET ROLE {}").format(Identifier(role.name)))


def restore_role(connection: Any, *, before_execute: Callable[[], None] | None = None) -> None:
    if before_execute is not None:
        before_execute()
    connection.execute("RESET ROLE")
