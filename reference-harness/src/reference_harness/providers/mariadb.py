"""Testcontainers-backed MariaDB provider (dialect = "mariadb").

The MariaDB concrete dialect behind the m-db-port database-provider seam,
proving "equivalent SQL per database, optimized per dialect" beyond Postgres.
MariaDB is fully open-source and exercises exactly the seam points Postgres does
not:

* **Read-lock divergence.** MariaDB has no ``for share``; the shared row lock is
  ``lock in share mode`` (MDEV-17514). The golden SQL carries that form per
  dialect; the m-sql normalizer renders it through the seam.
* **No native timestamp infinity.** MariaDB's ``DATETIME`` has no ``'infinity'``,
  so the open temporal upper bound (m-core/m-dialect) maps to a documented **max-sentinel**
  — ``9999-12-31 23:59:59.999999`` (the largest ``DATETIME(6)``). This provider
  translates the declared temporal-infinity marker to that sentinel on the way in
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
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from types import TracebackType
from typing import TYPE_CHECKING, Any

import pymysql
from pymysql.constants import FIELD_TYPE
from testcontainers.community.mysql import MySqlContainer

from .. import errors
from .._declared_contributor import TEMPORAL_INFINITY
from ..ddl_builder import quote_identifier
from ..document_codec import is_document
from . import register
from ._binds import adapt_document_scalar_binds

if TYPE_CHECKING:
    from . import Node

# The provisioning seam pins a MariaDB long-term-support series (m-case-format/DQ15).
# This pin must stay at or above 11.4.2, the first release carrying
# `innodb_snapshot_isolation`, without which Repeatable Read cannot forbid the lost
# update; the compatibility suite asserts the booted server against that floor.
MARIADB_IMAGE = "mariadb:12.3"

# MariaDB keys on the vendor errno; a code absent here is `errors.UNKNOWN`, so an
# unclassified error fails an assertion loudly rather than passing silently.
_CODES: dict[int, str] = {
    1062: errors.UNIQUE_VIOLATION,  # ER_DUP_ENTRY
    1213: errors.DEADLOCK,  # ER_LOCK_DEADLOCK
    1205: errors.LOCK_WAIT_TIMEOUT,  # ER_LOCK_WAIT_TIMEOUT
    # ER_CHECKREAD: a snapshot-isolation write/write conflict at Repeatable Read,
    # which the server itself rolls back like a deadlock.
    1020: errors.DEADLOCK,
}

# MariaDB has no native timestamp infinity; the open upper bound (m-core/m-dialect) is the
# largest representable DATETIME(6). This is the documented max-sentinel the seam
# substitutes for the suite's `infinity` literal.
_INFINITY_SENTINEL = _dt.datetime(9999, 12, 31, 23, 59, 59, 999999)
_INFINITY_LITERAL = "infinity"


def _to_db_bind(value: Any) -> Any:
    """Adapt a fixture / bind value for MariaDB binding.

    * the declared Timestamp infinity marker -> the max-sentinel ``DATETIME``
      (m-dialect);
    * a managed aware ``datetime`` -> naive UTC for MariaDB ``DATETIME``;
    * a portable document (``document_codec.is_document``) -> JSON text, because
      MariaDB's ``JSON`` is a text alias; serialization is this seam's job and sits
      below the bind, which is why a golden authors the document itself
      (m-case-format);
    * every other scalar passes through unchanged.
    """
    if value is TEMPORAL_INFINITY:
        return _INFINITY_SENTINEL
    if isinstance(value, _dt.datetime) and value.tzinfo is not None:
        return value.astimezone(_dt.UTC).replace(tzinfo=None)
    if is_document(value):
        return json.dumps(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _statement_binds(sql: str, binds: Sequence[Any]) -> tuple[Any, ...]:
    physical = adapt_document_scalar_binds(sql, binds, "mariadb")
    return tuple(_to_db_bind(value) for value in physical)


def _is_boolean_field(type_code: Any, column_length: Any) -> bool:
    """True for a MariaDB ``tinyint(1)`` result column — the ``boolean`` mapping.

    ``boolean`` is the ONLY neutral type that maps to ``tinyint(1)`` (ddl_builder),
    which pymysql reports as ``FIELD_TYPE.TINY`` with a display length of ``1`` and
    reads back as int ``0`` / ``1``. Every other integer column is a wider type code
    (``int32`` -> ``int`` / ``FIELD_TYPE.LONG``, ``int64`` -> ``bigint`` /
    ``FIELD_TYPE.LONGLONG``), so this never coerces a non-boolean integer.
    """
    return type_code == FIELD_TYPE.TINY and column_length == 1


def _from_db_value(value: Any, *, is_boolean: bool = False) -> Any:
    """Adapt a MariaDB-read value back to the suite's canonical form.

    * a ``tinyint(1)`` (``boolean``) column -> a real ``bool``: MariaDB has no
      native boolean, so pymysql reads the column back as int ``0`` / ``1``. The
      row comparator keeps ``bool`` OUT of numeric space (m-case-format layer 2:
      ``true`` is never ``1``), so an int would never match the fixture's boolean;
      the caller passes ``is_boolean`` from the column's ``tinyint(1)`` field
      metadata (:func:`_is_boolean_field`) so the value compares correctly. A NULL
      boolean column stays ``None``;
    * the max-sentinel ``DATETIME`` -> the literal ``"infinity"`` (m-dialect), so a
      current-row open bound compares to the fixture's ``infinity``;
    * a finite ``datetime`` -> a stable ISO-8601 UTC string with ``+00:00`` (the
      same shape the Postgres provider yields), so instant columns compare across
      dialects;
    * a bare ``date`` -> passed through unchanged as a ``datetime.date``,
      symmetric with the Postgres provider (which registers no ``date`` loader)
      and matching how a YAML-authored date scalar parses, so a ``date`` column
      compares equal across dialects; a ``bytes`` JSON payload is left to the
      caller (we never read JSON columns back for comparison in this phase).
    """
    if is_boolean and isinstance(value, int) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, _dt.datetime):
        if value == _INFINITY_SENTINEL:
            return _INFINITY_LITERAL
        return value.replace(tzinfo=_dt.UTC).isoformat()
    if isinstance(value, _dt.timedelta):
        # pymysql reads a `TIME` column as a `timedelta`; render it as a stable
        # `HH:MM:SS` string so a `time` column compares to a plain YAML string
        # (the Postgres provider already reads `time` as text). Sub-day values —
        # the only ones the suite carries — format cleanly via str().
        return str(value)
    return value


def _decode_rows(
    description: Sequence[Any],
    rows: Sequence[Sequence[Any]],
) -> list[dict[str, Any]]:
    """Decode a MariaDB cursor's fetched rows to the suite's canonical dicts.

    Reads each result column's ``tinyint(1)`` (``boolean``) flag from the cursor
    ``description`` once, then adapts every value through :func:`_from_db_value`.
    Shared verbatim by :meth:`MariaDbProvider.query` and :meth:`_MariaTxSession.query`
    so a future canonicalization change updates one decoding path.
    """
    columns = [(desc[0], _is_boolean_field(desc[1], desc[3])) for desc in description]
    return [
        {
            name: _from_db_value(value, is_boolean=is_boolean)
            for (name, is_boolean), value in zip(columns, row, strict=True)
        }
        for row in rows
    ]


class MariaDbProvider:
    """A clean, migrated, isolated MariaDB database for one suite run."""

    dialect = "mariadb"

    def __init__(
        self,
        connection: pymysql.connections.Connection,
        dbname: str,
        connect_params: dict[str, Any] | None = None,
    ) -> None:
        self._conn = connection
        self._dbname = dbname
        # Connection parameters for opening a second, independent connection to the
        # SAME database. A peer is created
        # by reconnecting with these and selecting the working database.
        self._connect_params = connect_params or {}

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
        col_list = ", ".join(quote_identifier(column, self.dialect) for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        target = quote_identifier(table, self.dialect)
        sql = f"insert into {target} ({col_list}) values ({placeholders})"
        with self._conn.cursor() as cur:
            cur.executemany(sql, [tuple(_to_db_bind(value) for value in row) for row in rows])
        self._conn.commit()

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        # The harness stores golden SQL with `?` placeholders (m-sql); pymysql uses
        # `%s`. Translate positional placeholders for execution, then adapt already-managed
        # declared values and temporal-infinity markers to MariaDB forms. No raw string
        # carrier is interpreted here.
        with self._conn.cursor() as cur:
            if binds:
                cur.execute(
                    _to_pymysql(sql, escape_percent=True),
                    tuple(_to_db_bind(value) for value in binds),
                )
            else:
                cur.execute(_to_pymysql(sql))
            return _decode_rows(cur.description, cur.fetchall())

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        with self._conn.cursor() as cur:
            if binds:
                affected = cur.execute(
                    _to_pymysql(sql, escape_percent=True),
                    _statement_binds(sql, binds),
                )
            else:
                affected = cur.execute(_to_pymysql(sql))
            self._conn.commit()
            return affected

    def native_error_code(self, exc: Exception) -> int | None:
        """The vendor errno pymysql packs into args[0] (else None)."""
        if exc.args and isinstance(exc.args[0], int):
            return exc.args[0]
        return None

    def classify_error(self, exc: Exception) -> str:
        """Map a raised pymysql error to a neutral m-db-error category (see errors.py)."""
        code = self.native_error_code(exc)
        return errors.UNKNOWN if code is None else _CODES.get(code, errors.UNKNOWN)

    @contextmanager
    def open_session(self) -> Iterator[_MariaTxSession]:
        """A second connection in MANUAL-commit mode, for lock contention.

        Mirrors the Postgres session. MariaDB's default
        ``innodb_lock_wait_timeout`` is 50s -- far too slow for the suite -- so it
        is lowered to 1s on open; a blocked lock then raises errno 1205 quickly.
        InnoDB detects deadlocks immediately (no timeout knob needed).
        """
        params = {**self._connect_params, "autocommit": False}
        conn = pymysql.connect(database=self._dbname, **params)
        try:
            with conn.cursor() as cur:
                cur.execute("set innodb_lock_wait_timeout = 1")
            conn.commit()
        except BaseException:
            conn.close()
            raise
        session = _MariaTxSession(conn)
        try:
            yield session
        finally:
            session.close()

    @contextmanager
    def open_peer(self) -> Iterator[Node]:
        """Yield a second, independent connection to the SAME MariaDB database.

        Cross-process coherence: node B reconnects with the provider's
        own connection parameters and ``USE``\\ s the working database, so it shares
        node A's data while holding its own session. MariaDB ``execute`` COMMITs,
        so a write on node A is visible to a read on node B — the observable half
        of cross-process coherence. Provisioning stays on node A; only the peer's
        read/write surface is used.

        The peer connects with ``autocommit=True`` so each read is its OWN
        transaction with a FRESH snapshot. Under MariaDB/InnoDB's default
        ``REPEATABLE READ`` a long-lived transaction would pin the snapshot taken
        at node B's first read and never see node A's later commit — which is the
        very thing a coherence re-fetch must observe. Autocommit reads model the
        app server's behavior exactly: a re-fetch after invalidation is a new
        query, not a read inside the stale snapshot. (Postgres' provider is already
        autocommit, so this aligns the two dialects.)
        """
        peer_params = {**self._connect_params, "autocommit": True}
        connection = pymysql.connect(database=self._dbname, **peer_params)
        peer = MariaDbProvider(connection, self._dbname, self._connect_params)
        try:
            yield peer
        finally:
            peer.close()

    def close(self) -> None:
        if self._conn is not None and self._conn.open:
            self._conn.close()


class _MariaTxSession:
    """A manual-commit MariaDB connection for two-node lock-contention cases."""

    dialect = "mariadb"

    def __init__(self, conn: pymysql.connections.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        """Run DML on the HELD transaction; return the affected-row count.

        The count is what makes an optimistic-lock conflict observable inside a
        buffered unit of work (m-opt-lock): a stale-version gate matches 0 rows.
        The two-node lock-contention callers ignore the return.
        """
        with self._conn.cursor() as cur:
            if binds:
                cur.execute(
                    _to_pymysql(sql, escape_percent=True),
                    _statement_binds(sql, binds),
                )
            else:
                cur.execute(_to_pymysql(sql))
            return cur.rowcount

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Fetch rows INSIDE the held transaction (concurrency-success `expectRows`).

        Mirrors the provider's ``query`` but runs on the HELD session connection so a
        locking SELECT (``lock in share mode``) both takes the shared lock and returns
        its rows inside the open unit of work.
        """
        with self._conn.cursor() as cur:
            if binds:
                cur.execute(
                    _to_pymysql(sql, escape_percent=True),
                    tuple(_to_db_bind(value) for value in binds),
                )
            else:
                cur.execute(_to_pymysql(sql))
            return _decode_rows(cur.description, cur.fetchall())

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        if self._conn is not None and self._conn.open:
            self._conn.close()


def _to_pymysql(sql: str, *, escape_percent: bool = False) -> str:
    """Translate `?` positional placeholders to pymysql's `%s`.

    pymysql treats a literal `%` (e.g. a `like '%a%'` pattern in a naive
    referenceSql) as a format token only when an args tuple is supplied. Escape
    literal percent signs on that path, then expand the placeholders. Bindless
    SQL must keep `%` unchanged because pymysql will not format it back.
    """
    escaped = sql.replace("%", "%%") if escape_percent else sql
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
        connect_params = _connect_params(container)
        connection = _connect_with_retry(connect_params, container.dbname)
        provider = MariaDbProvider(connection, container.dbname, connect_params)
        yield provider
    finally:
        if provider is not None:
            provider.close()
        elif connection is not None and connection.open:
            connection.close()
        container.stop()


def _connect_params(container: MySqlContainer) -> dict[str, Any]:
    """The pymysql connection parameters for the booted container (sans database).

    Shared by the provider's own connection and the peer connection, so a
    coherence case's node B reaches the same server with the same credentials.
    """
    return {
        "host": container.get_container_host_ip(),
        "port": int(container.get_exposed_port(container.port)),
        "user": container.username,
        "password": container.password,
        "autocommit": False,
    }


def _connect_with_retry(
    connect_params: dict[str, Any],
    dbname: str,
    attempts: int = 30,
    delay: float = 1.0,
) -> pymysql.connections.Connection:
    """Open a pymysql connection, retrying transient startup races.

    MariaDB's entrypoint logs ``ready for connections`` once during bootstrap and
    then restarts the server before the final ready state, so the first TCP
    handshake can be dropped (``Lost connection during query``). Retry until the
    server is genuinely accepting connections.
    """
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return pymysql.connect(database=dbname, **connect_params)
        except pymysql.err.OperationalError as exc:  # noqa: PERF203
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(f"could not connect to MariaDB after {attempts} attempts") from last_error


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
