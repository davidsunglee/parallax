"""Testcontainers-backed MariaDB provider (dialect = "mariadb").

The **second** concrete dialect behind the M11 database-provider seam (Phase 10),
proving "equivalent SQL per database, optimized per dialect" beyond Postgres.
MariaDB is fully open-source and exercises exactly the seam points Postgres does
not:

* **Read-lock divergence.** MariaDB has no ``for share``; the shared row lock is
  ``lock in share mode`` (MDEV-17514). The golden SQL carries that form per
  dialect; the M3 normalizer renders it through the seam.
* **No native timestamp infinity.** MariaDB's ``DATETIME`` has no ``'infinity'``,
  so the open temporal upper bound (M0/M11) maps to a documented **max-sentinel**
  — ``9999-12-31 23:59:59.999999`` (the largest ``DATETIME(6)``). This provider
  translates the suite's ``infinity`` literal to that sentinel on the way in
  (fixture loads, binds) and back to ``"infinity"`` on the way out (reads), so a
  fixture authored once against native-infinity Postgres compares identically
  here — the only place the difference is allowed to surface.

It is booted via testcontainers-python's MySQL-compatible container pointed at a
``mariadb`` image, driven by the ``pymysql`` client.
"""

from __future__ import annotations

import datetime as _dt
import json
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from types import TracebackType
from typing import Any

import pymysql
from testcontainers.mysql import MySqlContainer

from . import register

# Pinned at a current stable MariaDB major (M12/DQ15). Refresh on new majors.
MARIADB_IMAGE = "mariadb:11.4"

# MariaDB has no native timestamp infinity; the open upper bound (M0/M11) is the
# largest representable DATETIME(6). This is the documented max-sentinel the seam
# substitutes for the suite's `infinity` literal.
_INFINITY_SENTINEL = _dt.datetime(9999, 12, 31, 23, 59, 59, 999999)
_INFINITY_LITERAL = "infinity"


def _to_db_bind(value: Any) -> Any:
    """Adapt a fixture / bind value for MariaDB binding.

    * the suite's ``infinity`` literal -> the max-sentinel ``DATETIME`` (M11);
    * an ISO-8601 instant string -> a naive UTC ``datetime`` (MariaDB ``DATETIME``
      is timezone-naive; every instant in the suite is UTC, so we drop the offset
      after normalizing to UTC);
    * a ``dict`` / ``list`` valueObject -> a JSON string (MariaDB ``JSON`` column);
    * every other scalar passes through unchanged.
    """
    if value == _INFINITY_LITERAL:
        return _INFINITY_SENTINEL
    if isinstance(value, str):
        instant = _parse_iso_instant(value)
        if instant is not None:
            return instant
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _parse_iso_instant(text: str) -> _dt.datetime | None:
    """Parse an ISO-8601 instant to a naive UTC ``datetime``, else ``None``.

    Only strings that are full ISO-8601 timestamps (carrying a ``T`` separator)
    are treated as instants, so a plain ``date`` / ``time`` / business string is
    left alone. The result is shifted to UTC and made naive to match MariaDB's
    timezone-naive ``DATETIME`` storage.
    """
    if "T" not in text:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_dt.UTC).replace(tzinfo=None)
    return parsed


def _from_db_value(value: Any) -> Any:
    """Adapt a MariaDB-read value back to the suite's canonical form.

    * the max-sentinel ``DATETIME`` -> the literal ``"infinity"`` (M11), so a
      current-row open bound compares to the fixture's ``infinity``;
    * a finite ``datetime`` -> a stable ISO-8601 UTC string with ``+00:00`` (the
      same shape the Postgres provider yields), so instant columns compare across
      dialects;
    * a ``date`` -> its ISO string; a ``bytes`` JSON payload is left to the
      caller (we never read JSON columns back for comparison in this phase).
    """
    if isinstance(value, _dt.datetime):
        if value == _INFINITY_SENTINEL:
            return _INFINITY_LITERAL
        return value.replace(tzinfo=_dt.UTC).isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    return value


class MariaDbProvider:
    """A clean, migrated, isolated MariaDB database for one suite run."""

    dialect = "mariadb"

    def __init__(self, connection: pymysql.connections.Connection, dbname: str) -> None:
        self._conn = connection
        self._dbname = dbname

    # --- DatabaseProvider seam ---------------------------------------------

    def reset(self) -> None:
        """Drop and recreate the working schema — a clean, empty database."""
        with self._conn.cursor() as cur:
            cur.execute(f"drop database if exists {self._dbname}")
            cur.execute(f"create database {self._dbname}")
            cur.execute(f"use {self._dbname}")
        self._conn.commit()

    def apply_ddl(self, statements: Sequence[str]) -> None:
        with self._conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
        self._conn.commit()

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
            cur.executemany(
                sql, [tuple(_to_db_bind(value) for value in row) for row in rows]
            )
        self._conn.commit()

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        # The harness stores golden SQL with `?` placeholders (M3); pymysql uses
        # `%s`. Translate positional placeholders for execution, and translate the
        # `infinity` literal / ISO instants in the binds to MariaDB forms.
        with self._conn.cursor() as cur:
            if binds:
                cur.execute(
                    _to_pymysql(sql), tuple(_to_db_bind(value) for value in binds)
                )
            else:
                cur.execute(_to_pymysql(sql))
            column_names = [desc[0] for desc in cur.description]
            return [
                {name: _from_db_value(value) for name, value in zip(column_names, row, strict=True)}
                for row in cur.fetchall()
            ]

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        with self._conn.cursor() as cur:
            if binds:
                affected = cur.execute(
                    _to_pymysql(sql), tuple(_to_db_bind(value) for value in binds)
                )
            else:
                affected = cur.execute(_to_pymysql(sql))
            self._conn.commit()
            return affected

    def close(self) -> None:
        if self._conn is not None and self._conn.open:
            self._conn.close()


def _to_pymysql(sql: str) -> str:
    """Translate `?` positional placeholders to pymysql's `%s`.

    pymysql treats a literal `%` (e.g. a `like '%a%'` pattern in a naive
    referenceSql) as a format token, so we also escape bare `%` that are not the
    `%s` we just produced. The golden SQL uses `?` placeholders exclusively, so we
    escape first, then expand the placeholders.
    """
    escaped = sql.replace("%", "%%")
    return escaped.replace("?", "%s")


@contextmanager
def mariadb_provider() -> Iterator[MariaDbProvider]:
    """Boot a pinned MariaDB container and yield a provider bound to it."""
    container = MySqlContainer(
        MARIADB_IMAGE,
        # MariaDB prints a single "ready for connections" line, unlike MySQL's
        # double line the default check string expects.
        wait_strategy_check_string=r".*ready for connections.*",
    )
    container.start()
    provider: MariaDbProvider | None = None
    connection: pymysql.connections.Connection | None = None
    try:
        connection = _connect_with_retry(container)
        provider = MariaDbProvider(connection, container.dbname)
        yield provider
    finally:
        if provider is not None:
            provider.close()
        elif connection is not None and connection.open:
            connection.close()
        container.stop()


def _connect_with_retry(
    container: MySqlContainer, attempts: int = 30, delay: float = 1.0
) -> pymysql.connections.Connection:
    """Open a pymysql connection, retrying transient startup races.

    MariaDB's entrypoint logs ``ready for connections`` once during bootstrap and
    then restarts the server before the final ready state, so the first TCP
    handshake can be dropped (``Lost connection during query``). Retry until the
    server is genuinely accepting connections.
    """
    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(container.port))
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return pymysql.connect(
                host=host,
                port=port,
                user=container.username,
                password=container.password,
                database=container.dbname,
                autocommit=False,
            )
        except pymysql.err.OperationalError as exc:  # noqa: PERF203
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(
        f"could not connect to MariaDB after {attempts} attempts"
    ) from last_error


class _MariaDbFactory:
    """Callable + context-manager adapter so the registry can ``with factory()``."""

    def __call__(self) -> _MariaDbFactory:
        self._cm = mariadb_provider()
        return self

    def __enter__(self) -> MariaDbProvider:
        return self._cm.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        return self._cm.__exit__(exc_type, exc, tb)


register("mariadb", _MariaDbFactory())
