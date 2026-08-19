"""The concrete Postgres database adapter (psycopg) — a leaf production artifact.

``PostgresAdapter`` implements the abstract ``m-db-port`` over psycopg 3. It is
the sole psycopg declarer and is wired only at composition roots. It carries the
normalize-at-boundary contract: rows come back as attribute/column-keyed dicts of
managed Python values (psycopg already decodes `numeric` to ``Decimal``, `int8`
to ``int``, `timestamptz` to aware ``datetime``, and so on), never raw driver
text. ``execute`` runs row-returning reads; ``execute_write`` runs DML and returns
the affected-row count without appending row-returning clauses; ``transaction``
runs a callback in one transaction, committing on success, rolling back on any
exception, and reporting which phase decided the outcome.

The adapter is also the `m-db-error` **port boundary**: every psycopg exception
raised by work the port itself performs — a statement, or the transaction
boundary's begin, commit, or rollback — becomes a neutral
:class:`~parallax.core.db_error.DatabaseError` carrying the classified category,
the preserved native SQLSTATE, and the driver message, so no driver exception
type produced by the PORT ever crosses above it (`m-db-port`
normalize-at-boundary, `m-db-error`); a statement raises it and a transaction
boundary carries it back in its outcome. An exception the caller's own
``transaction`` body raises is not the port's work and is not translated
(`m-db-port`). Category interpretation is delegated to the pure dialect strategy;
the adapter only extracts psycopg's driver-specific SQLSTATE and message.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Generator, Sequence

import psycopg
from psycopg.rows import TupleRow, dict_row
from psycopg.types.datetime import TimestamptzLoader
from psycopg.types.json import Jsonb, JsonbBinaryLoader, JsonbLoader

from parallax.core.base import INFINITY, AuthoredNumber
from parallax.core.db_error import DatabaseError, classify_error
from parallax.core.db_port import (
    BeginFailed,
    CallbackRaised,
    CommitFailed,
    Committed,
    DbPort,
    DocumentReadOrdinals,
    JsonDocument,
    RollbackFailed,
    RollbackTrigger,
    RolledBack,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES

__all__ = ["PostgresAdapter"]


class _PresentJsonNull:
    __slots__ = ()


_PRESENT_JSON_NULL = _PresentJsonNull()


def _load_json_preserving_null(data: str | bytes) -> object:
    """Decode a stored document, retaining what a plain parse would discard.

    A present JSON null keeps a distinct sentinel, so absence and a stored null stay
    two states. A number keeps the digits it was stored with
    (:class:`~parallax.core.base.AuthoredNumber`), because a float leaf's canonical
    spelling is a property of those digits: parsing them into a binary float first
    makes ``0.1`` and ``0.10000000000000001`` one value, and the read that must refuse
    the second would have nothing left to refuse it by.
    """
    value = json.loads(data, parse_float=AuthoredNumber)
    return _PRESENT_JSON_NULL if value is None else value


class _DocumentJsonbLoader(JsonbLoader):
    _loads = staticmethod(_load_json_preserving_null)


class _DocumentJsonbBinaryLoader(JsonbBinaryLoader):
    _loads = staticmethod(_load_json_preserving_null)


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


def boundary_failure(exc: psycopg.Error) -> DatabaseError:
    """The neutral error a transaction outcome carries for a boundary failure.

    A statement failure reaches its caller through ``raise ... from``, which is
    what leaves the driver's own exception on it as the cause. A boundary failure
    is reported rather than raised, so the same chaining happens here: without it
    the psycopg exception the classification came from would be dropped on the way
    into the outcome, and a caller re-raising the error later would see no cause
    at all.
    """
    error = translate_driver_error(exc)
    error.__cause__ = exc
    return error


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


def fold_document_reads(
    names: Sequence[str],
    rows: Sequence[Sequence[object]],
    document_reads: Sequence[DocumentReadOrdinals],
) -> list[Row]:
    """Fold raw adjacent document cells into provider-neutral managed rows."""
    pairs = tuple(document_reads)
    occupied: set[int] = set()
    for presence, document in pairs:
        if document != presence + 1 or presence < 0 or document >= len(names):
            raise ValueError(
                "document-read ordinals must be adjacent, zero-based, and within the projection"
            )
        if presence in occupied or document in occupied:
            raise ValueError("document-read ordinal pairs must not overlap")
        occupied.update((presence, document))

    by_document = {document: presence for presence, document in pairs}
    omitted = {presence for presence, _document in pairs}
    managed: list[Row] = []
    for raw in rows:
        if len(raw) != len(names):
            raise ValueError("a database row does not match its result description")
        row: Row = {}
        for ordinal, (name, value) in enumerate(zip(names, raw, strict=True)):
            if ordinal in omitted:
                continue
            presence = by_document.get(ordinal)
            if value is _PRESENT_JSON_NULL:
                value = None
            row[name] = (
                POSTGRES.parse_document_read(raw[presence], value)
                if presence is not None
                else value
            )
        managed.append(row)
    return managed


class PostgresAdapter:  # pragma: no cover - exercised by the Docker adapter/provider lanes
    """A psycopg-backed :class:`~parallax.core.db_port.DbPort` over one connection."""

    def __init__(self, connection: psycopg.Connection[TupleRow]) -> None:
        self._connection = connection
        # Normalize native `timestamptz` infinity at the port boundary (m-db-port):
        # a temporal interval's open upper bound reads back as the neutral m-core
        # infinity sentinel rather than raising psycopg's out-of-range error.
        connection.adapters.register_loader("timestamptz", _InfinityTimestamptzLoader)
        connection.adapters.register_loader("jsonb", _DocumentJsonbLoader)
        connection.adapters.register_loader("jsonb", _DocumentJsonbBinaryLoader)

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

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        with translating_driver_errors():
            if document_reads:
                with self._connection.cursor() as cursor:
                    cursor.execute(sql.encode(), adapt_binds(binds))
                    if cursor.description is None:
                        return []
                    names = [column.name for column in cursor.description]
                    return fold_document_reads(names, cursor.fetchall(), document_reads)
            with self._connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(sql.encode(), adapt_binds(binds))
                if cursor.description is None:
                    return []
                return [
                    {
                        name: None if value is _PRESENT_JSON_NULL else value
                        for name, value in row.items()
                    }
                    for row in cursor.fetchall()
                ]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        with translating_driver_errors(), self._connection.cursor() as cursor:
            cursor.execute(sql.encode(), adapt_binds(binds))
            return cursor.rowcount

    def transaction[T](self, body: Callable[[DbPort], T]) -> TransactionOutcome[T]:
        """Run ``body`` in one transaction and report which boundary phase decided
        the outcome.

        Every phase the port itself performs translates, not only the statements
        inside it: a driver error at the begin, at the commit (a deferred
        constraint, a serialization failure), or at the rollback an escaping body
        triggers becomes a neutral ``DatabaseError``, exactly as a statement error
        raised through the port methods above does — but it is REPORTED rather
        than raised, because which phase failed is what decides whether the work
        may be retried and whether this connection is still trustworthy.

        An exception ``body`` itself raises is the CALLER's failure rather than
        one the port made, so :class:`~parallax.core.db_port.CallbackRaised`
        carries the identical object (``m-db-port``). Translating it would
        substitute a port error for the caller's own — and a body-authored
        deadlock-class exception would then read as retriable to
        ``m-auto-retry``, which would replay the body over a failure the database
        never reported. Catching it at its own call site is what keeps it
        distinguishable from the rollback it triggers even when the driver raises
        one reused exception object for both.

        The driver's transaction context is driven a phase at a time rather than
        through a ``with`` statement, because a ``with`` reports only the single
        exception that escapes it: begin, commit, and rollback would arrive
        indistinguishable, and a rollback failure — which psycopg's context logs
        and discards — would not arrive at all.
        """
        boundary = self._connection.transaction()
        try:
            boundary.__enter__()
        except psycopg.Error as exc:
            return BeginFailed(boundary_failure(exc))
        try:
            value = body(self)
        except BaseException as raised:
            return self._undone(CallbackRaised(raised), boundary=boundary)
        try:
            boundary.__exit__(None, None, None)
        except psycopg.Error as exc:
            return self._undone(CommitFailed(boundary_failure(exc)), boundary=None)
        return Committed(value)

    def _undone(
        self,
        trigger: RollbackTrigger,
        *,
        boundary: contextlib.AbstractContextManager[psycopg.Transaction] | None,
    ) -> RolledBack | RollbackFailed:
        """Undo the transaction ``trigger`` ended, reporting whether the undo completed.

        ``boundary`` is the driver's still-open transaction context when the
        callback failed, and ``None`` once a failed commit has already closed it.

        The connection is asked to roll back after that context has exited
        because psycopg's own exit logs and discards a failed ROLLBACK rather
        than raising it, so a rollback failure would otherwise be invisible to
        this port. The second request is a no-op when the transaction already
        ended — the driver sends nothing on an idle session — and is where a
        connection too broken to undo the work raises an error this port can
        classify. Then the outcome of the work is unknown, so the connection is
        discarded rather than handed back for more.
        """
        error = trigger.error
        try:
            if boundary is not None:
                boundary.__exit__(type(error), error, error.__traceback__)
            self._connection.rollback()
        except psycopg.Error as exc:
            rollback_error = boundary_failure(exc)
            self._discard()
            return RollbackFailed(trigger, rollback_error)
        return RolledBack(trigger)

    def _discard(self) -> None:
        """Drop the connection whose transaction outcome is unknown.

        Closing a connection already broken enough to fail a rollback may itself
        fail, and that failure adds nothing to what the rollback error already
        reports.
        """
        with contextlib.suppress(psycopg.Error):
            self.close()

    def close(self) -> None:
        """Close the underlying connection."""
        self._connection.close()
