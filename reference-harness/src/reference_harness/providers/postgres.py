"""Testcontainers-backed Postgres provider (dialect = "postgres").

Boots a real Postgres in a container (clean / migrated / isolated) and satisfies
the ``DatabaseProvider`` seam. Per M12/DQ15 the image is pinned at the latest
stable Postgres major; bump the tag as new majors ship.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from types import TracebackType
from typing import Any

import psycopg
from testcontainers.postgres import PostgresContainer

from . import register

# Pinned at the latest stable Postgres major (M12/DQ15). Refresh on new majors.
POSTGRES_IMAGE = "postgres:17"


class PostgresProvider:
    """A clean, migrated, isolated Postgres database for one suite run."""

    dialect = "postgres"

    def __init__(self, connection_url: str) -> None:
        self._conn = psycopg.connect(connection_url, autocommit=True)

    # --- DatabaseProvider seam ---------------------------------------------

    def reset(self) -> None:
        """Drop and recreate the ``public`` schema — a clean, empty database."""
        with self._conn.cursor() as cur:
            cur.execute("drop schema if exists public cascade")
            cur.execute("create schema public")

    def apply_ddl(self, statements: Sequence[str]) -> None:
        with self._conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)

    def load(
        self,
        table: str,
        columns: Sequence[str],
        rows: Sequence[Sequence[Any]],
    ) -> None:
        if not rows:
            return
        col_list = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"insert into {table} ({col_list}) values ({placeholders})"
        with self._conn.cursor() as cur:
            cur.executemany(sql, [tuple(row) for row in rows])

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        # The harness stores golden SQL with `?` placeholders (M3); psycopg uses
        # `%s`. Translate positional placeholders for execution. `?` never
        # appears literally in our SQL outside a placeholder position.
        with self._conn.cursor() as cur:
            if binds:
                cur.execute(sql.replace("?", "%s"), tuple(binds))
            else:
                # No binds: execute the SQL verbatim with NO params, so psycopg
                # does not treat literal `%` (e.g. a `like '%a%'` pattern in a
                # naive referenceSql) as a parameter placeholder.
                cur.execute(sql)
            column_names = [desc.name for desc in cur.description]
            return [dict(zip(column_names, row, strict=True)) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()


@contextmanager
def postgres_provider() -> Iterator[PostgresProvider]:
    """Boot a pinned Postgres container and yield a provider bound to it."""
    container = PostgresContainer(POSTGRES_IMAGE)
    container.start()
    provider: PostgresProvider | None = None
    try:
        # driver=None yields a plain postgresql:// URL that psycopg 3 accepts.
        url = container.get_connection_url(driver=None)
        provider = PostgresProvider(url)
        yield provider
    finally:
        if provider is not None:
            provider.close()
        container.stop()


class _PostgresFactory:
    """Callable + context-manager adapter so the registry can ``with factory()``."""

    def __call__(self) -> _PostgresFactory:
        self._cm = postgres_provider()
        return self

    def __enter__(self) -> PostgresProvider:
        return self._cm.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        return self._cm.__exit__(exc_type, exc, tb)


register("postgres", _PostgresFactory())
