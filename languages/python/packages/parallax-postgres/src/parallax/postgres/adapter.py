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

The adapter is also the `m-db-error` **port boundary**: every psycopg exception
raised by work the port itself performs — a statement, or the transaction
boundary's begin, commit, or rollback — is re-raised as a neutral
:class:`~parallax.core.db_error.DatabaseError` carrying the classified category,
the preserved native SQLSTATE, and the driver message, so no driver exception
type raised by the PORT ever crosses above it (`m-db-port`
normalize-at-boundary, `m-db-error`). An exception the caller's own
``transaction`` body raises is not the port's work and is not translated
(`m-db-port`). Category interpretation is delegated to the pure dialect strategy;
the adapter only extracts psycopg's driver-specific SQLSTATE and message.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Generator, Sequence

import psycopg
from psycopg.rows import TupleRow, dict_row
from psycopg.types.datetime import TimestamptzLoader
from psycopg.types.json import Jsonb

from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError, classify_error
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.dialect import POSTGRES

__all__ = ["PostgresAdapter"]


class _InfinityTimestamptzLoader(TimestamptzLoader):  # pragma: no cover - Docker read lane
    """Read a ``timestamptz`` back, mapping native ``infinity`` to the neutral sentinel.

    A temporal interval's open upper bound reads back as Postgres native
    ``infinity``, which is outside ``datetime``'s range — psycopg's default loader
    raises *timestamp too large*. The port normalizes it to the ``m-core``
    :data:`~parallax.core.base.INFINITY` (``TemporalBound``) so no driver-specific
    sentinel and no out-of-range value crosses the port boundary (``m-db-port``
    normalize-at-boundary); the grader renders it back to the canonical ``infinity``
    literal. A finite instant delegates to the default loader.
    """

    def load(self, data: object) -> object:  # type: ignore[override] - psycopg loader hook is typed Buffer; the port widens to object
        if bytes(data) == b"infinity":  # type: ignore[arg-type] - psycopg hands the loader a raw buffer at runtime
            return INFINITY
        return super().load(data)  # type: ignore[arg-type] - psycopg hands the loader a raw buffer at runtime


def translate_driver_error(exc: psycopg.Error) -> DatabaseError:
    """The `m-db-error` re-raise target for a psycopg exception (port boundary).

    Extracts psycopg's driver-specific SQLSTATE (``exc.sqlstate`` — ``None`` for a
    non-database failure such as a dropped connection) and message, then delegates
    category interpretation to ``m-db-error`` (which consults the pure Postgres
    dialect code table). This module-internal seam is the psycopg half of the
    normalize-at-boundary contract; it is not part of the ``parallax.postgres``
    public export (``PostgresAdapter`` alone — §8).

    Each call builds its own error, which is what satisfies the port's
    failure-identity rule (``m-db-port``): no two invocations share an instance,
    so the object a caller catches names the invocation that raised it.
    """
    return classify_error(POSTGRES, exc.sqlstate, str(exc))


@contextlib.contextmanager
def translating_driver_errors() -> Generator[None]:
    """Re-raise any psycopg exception inside the block as a neutral ``DatabaseError``.

    A :class:`~parallax.core.db_error.DatabaseError` raised by an inner port call
    is **not** a ``psycopg.Error``, so a nested transaction never re-wraps an
    already-translated error, and a non-driver exception (a rollback signal, a
    callback's own error) propagates unchanged.
    """
    try:
        yield
    except psycopg.Error as exc:
        raise translate_driver_error(exc) from exc


@contextlib.contextmanager
def _translating_boundary_errors(from_body: list[BaseException]) -> Generator[None]:
    """Translate a psycopg failure of the transaction BOUNDARY, and only that.

    Wrapping the whole boundary is what puts its begin and the rollback an
    escaping body triggers inside a translating block alongside its commit. The
    body runs inside that block too, so this skips exactly the object
    ``from_body`` records: an exception the caller's body raised is the caller's
    failure, not one the port made, and ``m-db-port`` has it cross the seam
    unchanged. A psycopg exception raised by that rollback is a different object
    and is translated.
    """
    try:
        yield
    except psycopg.Error as exc:
        if any(exc is escaped for escaped in from_body):
            raise
        raise translate_driver_error(exc) from exc


@contextlib.contextmanager
def _recording_body_failure(from_body: list[BaseException]) -> Generator[None]:
    """Record what the caller's transaction body raised, and re-raise it as is.

    Identity is the only thing that separates a body's own psycopg exception from
    the boundary's: both reach the translating block as a ``psycopg.Error``
    propagating out of the same ``with``.
    """
    try:
        yield
    except BaseException as exc:
        from_body.append(exc)
        raise


def adapt_binds(binds: Sequence[object]) -> list[object]:
    """Adapt neutral binds to psycopg's driver bind types at the adapter boundary.

    Module-internal seam (not part of the ``parallax.postgres`` public export,
    which is ``PostgresAdapter`` alone — §8).

    A :class:`~parallax.core.db_port.JsonDocument` (the neutral ``json`` /
    value-object carrier) becomes a psycopg ``Jsonb``; every other bind passes
    through unchanged. This keeps the psycopg bind mechanics internal to the
    adapter — no driver type is exported to the developer surface (m-db-port).
    """
    return [Jsonb(bind.value) if isinstance(bind, JsonDocument) else bind for bind in binds]


class PostgresAdapter:  # pragma: no cover - exercised by the Docker adapter/provider lanes
    """A psycopg-backed :class:`~parallax.core.db_port.DbPort` over one connection."""

    def __init__(self, connection: psycopg.Connection[TupleRow]) -> None:
        self._connection = connection
        # Normalize native `timestamptz` infinity at the port boundary (m-db-port):
        # a temporal interval's open upper bound reads back as the neutral m-core
        # infinity sentinel rather than raising psycopg's out-of-range error.
        connection.adapters.register_loader("timestamptz", _InfinityTimestamptzLoader)

    @classmethod
    def connect(
        cls, conninfo: str, *, autocommit: bool = True, prepare_threshold: int | None = 5
    ) -> PostgresAdapter:
        """Open a psycopg connection from documented connection configuration.

        ``prepare_threshold`` defaults to psycopg's own (server-side
        auto-preparation after 5 identical executions) — the right default
        for an ordinary long-lived application connection against one stable
        schema. A caller whose SAME connection sees a table's shape change
        underneath an identical query TEXT across its own lifetime (a
        schema-reset-per-case test harness, never a deployed app) should pass
        ``prepare_threshold=None`` to disable it: Postgres's own "cached plan
        must not change result type" error is a server-side prepared-plan
        cache invalidation, not a Parallax-level concern.
        """
        return cls(
            psycopg.connect(conninfo, autocommit=autocommit, prepare_threshold=prepare_threshold)
        )

    @property
    def connection(self) -> psycopg.Connection[TupleRow]:
        """The underlying psycopg connection (for provider-lane provisioning)."""
        return self._connection

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        with translating_driver_errors(), self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql.encode(), adapt_binds(binds))
            if cursor.description is None:
                return []
            return [dict(row) for row in cursor.fetchall()]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        with translating_driver_errors(), self._connection.cursor() as cursor:
            cursor.execute(sql.encode(), adapt_binds(binds))
            return cursor.rowcount

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        """Run ``body`` in one transaction, committing on success and rolling
        back on any exception.

        The whole boundary translates, not only the statements inside it: a
        driver error at its begin, at its commit (a deferred constraint, a
        serialization failure), or at the rollback an escaping body triggers
        reaches the caller as a neutral ``DatabaseError``, exactly as a statement
        error raised through the port methods above does.

        An exception ``body`` itself raises is the CALLER's failure rather than
        one the port made, so it crosses the seam unchanged even when it is a
        psycopg exception (``m-db-port``). Translating it would substitute a port
        error for the caller's own — and a body-authored deadlock-class exception
        would then read as retriable to ``m-auto-retry``, which would replay the
        body over a failure the database never reported.
        """
        from_body: list[BaseException] = []
        with (
            _translating_boundary_errors(from_body),
            self._connection.transaction(),
            _recording_body_failure(from_body),
        ):
            return body(self)

    def close(self) -> None:
        """Close the underlying connection."""
        self._connection.close()
