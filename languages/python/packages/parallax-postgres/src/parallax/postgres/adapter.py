"""The concrete Postgres database adapter (psycopg) — a leaf production artifact.

``PostgresAdapter`` implements the abstract ``m-db-port`` over psycopg 3. It is
the sole psycopg declarer and is wired only at composition roots. It carries the
normalize-at-boundary contract: rows come back as attribute/column-keyed dicts of
managed Python values (psycopg already decodes `numeric` to ``Decimal``, `int8`
to ``int``, `timestamptz` to aware ``datetime``, and so on), never raw driver
text. ``execute`` runs row-returning reads; ``execute_write`` runs DML and returns
the affected-row count without appending row-returning clauses; ``transaction``
runs a callback in one transaction, committing on success and rolling back on any
exception.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import psycopg
from psycopg.rows import TupleRow, dict_row
from psycopg.types.json import Json, Jsonb

from parallax.core.db_port import DbPort, Row

__all__ = ["Json", "Jsonb", "PostgresAdapter"]


class PostgresAdapter:  # pragma: no cover - exercised by the Docker adapter/provider lanes
    """A psycopg-backed :class:`~parallax.core.db_port.DbPort` over one connection."""

    def __init__(self, connection: psycopg.Connection[TupleRow]) -> None:
        self._connection = connection

    @classmethod
    def connect(cls, conninfo: str, *, autocommit: bool = True) -> PostgresAdapter:
        """Open a psycopg connection from documented connection configuration."""
        return cls(psycopg.connect(conninfo, autocommit=autocommit))

    @property
    def connection(self) -> psycopg.Connection[TupleRow]:
        """The underlying psycopg connection (for provider-lane provisioning)."""
        return self._connection

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql.encode(), list(binds))
            if cursor.description is None:
                return []
            return [dict(row) for row in cursor.fetchall()]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(sql.encode(), list(binds))
            return cursor.rowcount

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        with self._connection.transaction():
            return body(self)

    def close(self) -> None:
        """Close the underlying connection."""
        self._connection.close()
