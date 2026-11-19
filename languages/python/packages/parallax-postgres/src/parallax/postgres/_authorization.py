from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from psycopg.sql import SQL, Composed, Identifier, Literal

from parallax.core.internal.base import UsageError
from parallax.core.internal.db_port import AUTHORIZATION_INVALID, SubmissionProgress

if TYPE_CHECKING:
    import psycopg
    from psycopg.rows import TupleRow

__all__ = ["PostgresRole", "install_setup", "restore_role", "role_statement", "statement_timeout"]


@dataclass(frozen=True, slots=True)
class PostgresRole:
    """A non-empty PostgreSQL role name bound to principal execution."""

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):  # pyright: ignore[reportUnnecessaryIsInstance] - validates untyped callers at the public boundary
            raise UsageError(AUTHORIZATION_INVALID, "a PostgreSQL role name must be a string")
        if not self.name:
            raise UsageError(AUTHORIZATION_INVALID, "a PostgreSQL role name must not be empty")


def role_statement(role: PostgresRole) -> Composed:
    return SQL("SET ROLE {}").format(Identifier(role.name))


def statement_timeout(milliseconds: int) -> Composed:
    return SQL("SET statement_timeout = {}").format(Literal(milliseconds))


def install_setup(
    connection: psycopg.Connection[TupleRow],
    submission: SubmissionProgress,
    statement: Composed,
) -> None:
    """Run one session setup statement as a submission of its own."""
    with connection.cursor() as cursor:
        submission.started = True
        cursor.execute(statement)
        submission.answered = True


def restore_role(connection: Any) -> None:
    connection.execute("RESET ROLE")
