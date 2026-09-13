"""Scoped execution over one psycopg connection, and the setup every one gets.

This is the `m-db-error` **port boundary** and the `m-db-port`
normalize-at-boundary contract in one place: every psycopg exception raised by
work the connection itself performs — a statement, or the transaction boundary's
begin, commit, or rollback — becomes a neutral
:class:`~parallax.core.db_error.DatabaseError` carrying the classified category,
the preserved native SQLSTATE, the driver message, and the violated Physical
Index Name a unique violation reports, so no driver exception type produced by
execution ever crosses above it. An exception the caller's own ``transaction``
body raises is not this module's work and is not translated. Category
interpretation is delegated to the pure dialect strategy; only psycopg's
driver-specific SQLSTATE, its message, and the structured ``diag.constraint_name``
beside them are extracted here, and no message text is ever parsed.

:func:`initialize_connection` is the other half: the once-per-physical-connection
setup that makes a connection usable at all. It runs for every way a connection
comes into existence — initial capacity, growth, replacement, and on-demand
establishment — because a codec installed on some connections and not others is
a decoding bug that appears under load and nowhere else.

Execution here is SCOPED. A :class:`PostgresConnection` is created per
acquisition and revoked when that acquisition ends: after revocation it holds no
native connection and every verb refuses before reaching a driver. It never
closes, returns, or replaces a connection — deciding that is cleanup's, which is
why a boundary this module cannot bring back to a reusable state marks the
execution SUSPECT and reports the outcome instead of disposing of anything.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Generator, Sequence

import psycopg
from psycopg.rows import TupleRow, tuple_row
from psycopg.sql import SQL, Literal
from psycopg.types.datetime import TimestamptzLoader
from psycopg.types.json import Jsonb, JsonbBinaryLoader, JsonbLoader

from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError, classify_error
from parallax.core.db_port import (
    BeginFailed,
    CallbackRaised,
    CommitFailed,
    Committed,
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    JsonDocument,
    PipelineStatement,
    RollbackFailed,
    RollbackTrigger,
    RolledBack,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.wire import loads
from parallax.postgres._isolation import isolation_spelling

__all__ = [
    "CONNECT_KWARGS",
    "ConnectionPreparation",
    "IncompatibleSessionError",
    "PostgresConnection",
    "adapt_binds",
    "boundary_failure",
    "fold_document_reads",
    "initialize_connection",
    "translate_driver_error",
    "translating_driver_errors",
]

_REVOKED = (
    "this database connection's scope has ended; acquire another one through the Database "
    "that owns the runtime"
)


class _PresentJsonNull:
    __slots__ = ()


_PRESENT_JSON_NULL = _PresentJsonNull()


def _load_json_preserving_null(data: str | bytes) -> object:
    """Decode a stored document, retaining what a plain parse would discard.

    A present JSON null keeps a distinct sentinel, so absence and a stored null stay
    two states. Strict Wire loading retains number tokens privately until the
    document codec resolves each leaf's declared type.
    """
    value = loads(data)
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


class IncompatibleSessionError(Exception):
    """A physical connection's effective session settings cannot carry this
    adapter's codecs, so it is refused before any modeled SQL.

    Refused rather than repaired: silently issuing ``SET`` would give the
    application a session it did not ask for, and silently continuing would
    decode values wrongly in ways that surface as data rather than as an error.
    The message names the setting and the effective value, which are session
    configuration rather than credentials.
    """


def translate_driver_error(dialect: Dialect, exc: psycopg.Error) -> DatabaseError:
    """The `m-db-error` re-raise target for a psycopg exception (port boundary).

    Extracts psycopg's driver-specific SQLSTATE (``exc.sqlstate`` — ``None`` for a
    non-database failure such as a dropped connection), its message, and the
    structured constraint name libpq reports beside them, then delegates category
    interpretation to ``m-db-error`` (which consults ``dialect``'s own code
    table). libpq treats an index as a constraint whether or not it was created
    with constraint syntax, so a bare ``create unique index`` reports its own
    name there; the adapter forwards it and interprets nothing, and never reads
    the message text. A non-database failure carries no diagnostics at all.

    Each call builds its own error, which is what satisfies the port's
    failure-identity rule (``m-db-port``): no two invocations share an instance,
    so the object a caller catches names the invocation that raised it.
    """
    diagnostic = getattr(exc, "diag", None)
    return classify_error(
        dialect,
        exc.sqlstate,
        str(exc),
        constraint_name=None if diagnostic is None else diagnostic.constraint_name,
    )


def boundary_failure(dialect: Dialect, exc: psycopg.Error) -> DatabaseError:
    """The neutral error a transaction outcome carries for a boundary failure.

    A statement failure reaches its caller through ``raise ... from``, which is
    what leaves the driver's own exception on it as the cause. A boundary failure
    is reported rather than raised, so the same chaining happens here: without it
    the psycopg exception the classification came from would be dropped on the way
    into the outcome, and a caller re-raising the error later would see no cause
    at all.
    """
    error = translate_driver_error(dialect, exc)
    error.__cause__ = exc
    return error


@contextlib.contextmanager
def translating_driver_errors(dialect: Dialect) -> Generator[None]:
    """Re-raise any psycopg exception inside the block as a neutral ``DatabaseError``.

    A :class:`~parallax.core.db_error.DatabaseError` raised by an inner port call
    is **not** a ``psycopg.Error``, so a nested transaction never re-wraps an
    already-translated error, and a non-driver exception (a rollback signal, a
    callback's own error) propagates unchanged.
    """
    try:
        yield
    except psycopg.Error as exc:
        raise translate_driver_error(dialect, exc) from exc


def adapt_binds(binds: Sequence[object]) -> list[object]:
    """Adapt neutral binds to psycopg's driver bind types at the adapter boundary.

    A :class:`~parallax.core.db_port.JsonDocument` (the neutral ``json`` /
    value-object carrier) becomes a psycopg ``Jsonb``; every other bind passes
    through unchanged. This keeps the psycopg bind mechanics internal to the
    adapter — no driver type is exported to the developer surface (m-db-port).
    """
    return [Jsonb(bind.value) if isinstance(bind, JsonDocument) else bind for bind in binds]


def fold_document_reads(
    dialect: Dialect,
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
        row: list[object] = []
        for ordinal, value in enumerate(raw):
            if ordinal in omitted:
                continue
            presence = by_document.get(ordinal)
            if value is _PRESENT_JSON_NULL:
                value = None
            row.append(
                dialect.parse_document_read(raw[presence], value) if presence is not None else value
            )
        managed.append(tuple(row))
    return managed


CONNECT_KWARGS: dict[str, object] = {"autocommit": True, "row_factory": tuple_row}
"""The driver configuration every owned physical connection is created with.

``autocommit`` leaves the session outside a transaction between statements, so a
standalone read or a stream page gains no implicit whole-operation transaction
and an explicit boundary is the only thing that opens one. ``row_factory``
fixes the shape rows arrive in, so nothing downstream depends on a per-cursor
override to get it right.

``close_returns`` is deliberately absent, which leaves the driver's own default:
closing a connection closes it. The opposite would make the disposal step of
cleanup silently hand a poisoned connection back as a healthy return.
"""


def initialize_connection(connection: psycopg.Connection[TupleRow]) -> None:
    """Prepare one newly created physical connection, or refuse it.

    Called once per connection, before anything may use it, and for every way
    one comes into existence. It installs the three loaders the read path
    depends on and then checks the two effective session settings those loaders
    cannot work without — the client encoding and the date style — reading both
    off the established connection's own parameters rather than by running SQL,
    so the check costs no round trip on any creation path.

    A refusal here is a refusal of the CONNECTION, not of a statement: nothing
    modeled has run, and what would run next would decode wrongly.
    """
    # Normalize native `timestamptz` infinity at the port boundary (m-db-port):
    # a temporal interval's open upper bound reads back as the neutral m-core
    # infinity sentinel rather than raising psycopg's out-of-range error.
    connection.adapters.register_loader("timestamptz", _InfinityTimestamptzLoader)
    connection.adapters.register_loader("jsonb", _DocumentJsonbLoader)
    connection.adapters.register_loader("jsonb", _DocumentJsonbBinaryLoader)
    _require_supported_session(connection)


def _require_supported_session(connection: psycopg.Connection[TupleRow]) -> None:
    """Refuse an effective session the current codecs cannot execute under.

    Two settings are load-bearing and the rest are the application's own. SQL
    crosses this boundary as UTF-8 bytes and a stored document is decoded as
    UTF-8 text, so a client encoding that is anything else corrupts both. A
    finite ``timestamptz`` is decoded from its text form, which psycopg's loader
    reads in ISO order, so a non-ISO ``DateStyle`` makes instants decode wrongly
    or not at all — the field order within ISO (``MDY``, ``DMY``, ``YMD``) does
    not affect that and is left alone.

    Everything else a connection string, service file, environment, or server
    default establishes is preserved: the time zone, a stronger default
    isolation, a read-only session, a search path, statement and lock timeouts.
    Nothing here overwrites a setting, and there is no general session validator
    behind it.
    """
    encoding = connection.info.encoding
    if encoding.lower().replace("-", "_") not in {"utf_8", "utf8"}:
        raise IncompatibleSessionError(
            f"this connection's client encoding is {encoding!r}; Parallax sends SQL and decodes "
            f"stored documents as UTF-8, so it cannot execute under another encoding"
        )
    date_style = connection.info.parameter_status("DateStyle") or ""
    if not date_style.upper().startswith("ISO"):
        raise IncompatibleSessionError(
            f"this connection's DateStyle is {date_style!r}; Parallax decodes timestamps from "
            f"their ISO text form, so it cannot execute under another output style"
        )


class ConnectionPreparation:
    """The per-connection setup a native pool calls, remembering its last refusal.

    The record exists because a pool creates most of its connections on its own
    background path: an initialization refusal there is retried and logged where
    a caller waiting for a connection never sees it, and what that caller
    eventually gets is a bare timeout naming nothing to fix. Keeping the last
    refusal lets the timeout say what is actually wrong.

    A successful initialization clears it, so the record describes the runtime
    now rather than something it recovered from.
    """

    __slots__ = ("last_refusal",)

    def __init__(self) -> None:
        self.last_refusal: IncompatibleSessionError | None = None

    def __call__(self, connection: psycopg.Connection[TupleRow]) -> None:
        try:
            initialize_connection(connection)
        except IncompatibleSessionError as refusal:
            self.last_refusal = refusal
            raise
        self.last_refusal = None


class PostgresConnection:
    """One acquisition's execution access: a :class:`DatabaseConnection` over a
    psycopg connection somebody else owns the lifetime of.

    It runs statements and demarcates transactions, and it does nothing about
    the connection's life. Revocation is how the owner ends the scope: the
    native reference is cleared, so a caller holding this past its acquisition
    executes nothing and — more importantly — retains nothing.
    """

    dialect: Dialect = POSTGRES
    """The one place this adapter's SQL spelling is stated.

    Declared on the class, so a composition root reads it off the class itself
    without opening a connection, and every dialect decision made here — error
    classification, document-read parsing — consults it rather than a module
    name that could drift from it.
    """

    __slots__ = ("_connection", "_suspect")

    def __init__(self, connection: psycopg.Connection[TupleRow]) -> None:
        self._connection: psycopg.Connection[TupleRow] | None = connection
        self._suspect = False

    @property
    def suspect(self) -> bool:
        """Whether reuse of this connection could not be established.

        Set where a boundary could not be brought back to a known state — a
        rollback that failed, an empty transaction that could not be undone.
        It is a report for cleanup to act on, not an action: this class closes
        nothing and returns nothing.
        """
        return self._suspect

    def revoke(self) -> bool:
        """End this scope's access and report whether it left the connection suspect.

        Idempotent, and it never touches the connection itself. Clearing the
        reference here is what makes a later call raise before reaching a driver
        instead of running on a connection somebody else now holds.
        """
        self._connection = None
        return self._suspect

    def _native(self) -> psycopg.Connection[TupleRow]:
        connection = self._connection
        if connection is None:
            raise RuntimeError(_REVOKED)
        return connection

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        connection = self._native()
        with translating_driver_errors(self.dialect), connection.cursor() as cursor:
            cursor.execute(sql.encode(), adapt_binds(binds))
            if cursor.description is None:
                return []
            names = [column.name for column in cursor.description]
            if document_reads:
                return fold_document_reads(self.dialect, names, cursor.fetchall(), document_reads)
            return [
                tuple(None if value is _PRESENT_JSON_NULL else value for value in raw)
                for raw in cursor.fetchall()
            ]

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        connection = self._native()
        with translating_driver_errors(self.dialect), contextlib.ExitStack() as cursors:
            pending: list[tuple[psycopg.Cursor[TupleRow], tuple[DocumentReadOrdinals, ...]]] = []
            with connection.pipeline():
                for statement in statements:
                    cursor = cursors.enter_context(connection.cursor())
                    pending.append((cursor, statement.document_reads))
                    cursor.execute(statement.sql.encode(), adapt_binds(statement.binds))

            results: list[list[Row]] = []
            for cursor, document_reads in pending:
                if cursor.description is None:
                    results.append([])
                    continue
                names = [column.name for column in cursor.description]
                raw = cursor.fetchall()
                if document_reads:
                    results.append(fold_document_reads(self.dialect, names, raw, document_reads))
                else:
                    results.append(
                        [
                            tuple(None if value is _PRESENT_JSON_NULL else value for value in row)
                            for row in raw
                        ]
                    )
            return results

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        connection = self._native()
        with translating_driver_errors(self.dialect), connection.cursor() as cursor:
            cursor.execute(sql.encode(), adapt_binds(binds))
            return cursor.rowcount

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
    ) -> TransactionOutcome[T]:
        """Run ``body`` in one transaction and report which boundary phase decided
        the outcome.

        Every phase this connection itself performs translates, not only the
        statements inside it: a driver error at the begin, at the commit (a
        deferred constraint, a serialization failure), or at the rollback an
        escaping body triggers becomes a neutral ``DatabaseError``, exactly as a
        statement error raised through the verbs above does — but it is REPORTED
        rather than raised, because which phase failed is what decides whether the
        work may be retried and whether this connection is still trustworthy.

        An exception ``body`` itself raises is the CALLER's failure rather than
        one this made, so :class:`~parallax.core.db_port.CallbackRaised` carries
        the identical object (``m-db-port``). Translating it would substitute a
        port error for the caller's own — and a body-authored deadlock-class
        exception would then read as retriable to ``m-auto-retry``, which would
        replay the body over a failure the database never reported. Catching it
        at its own call site is what keeps it distinguishable from the rollback
        it triggers even when the driver raises one reused exception object for
        both.

        The driver's transaction context is driven a phase at a time rather than
        through a ``with`` statement, because a ``with`` reports only the single
        exception that escapes it: begin, commit, and rollback would arrive
        indistinguishable, and a rollback failure — which psycopg's context logs
        and discards — would not arrive at all.

        A requested ``isolation`` is part of opening the boundary rather than
        part of the work inside it: it is applied to the transaction just begun,
        before the body sees a connection, so it governs this transaction alone
        and leaves the session's own default untouched for the next one. An
        explicit boundary opens on an autocommit session exactly as it does on
        any other, so autocommit changes none of this. Postgres forbids each
        portable level's anomalies under its own name for it, so this maps the
        request to that name and asks for it; a level Postgres nonetheless
        refuses ends the boundary
        :class:`~parallax.core.db_port.BeginFailed`: no work of the caller's was
        attempted, and a request silently downgraded to a level the caller did
        not ask for is worse than one refused.
        """
        connection = self._native()
        # Resolved before the physical transaction exists, so a level outside the
        # vocabulary — a type violation the handle's own check would have caught —
        # cannot leave an empty transaction open on the connection.
        spelling = None if isolation is None else isolation_spelling(isolation)
        boundary = connection.transaction()
        try:
            boundary.__enter__()
        except psycopg.Error as exc:
            return BeginFailed(boundary_failure(self.dialect, exc))
        if spelling is not None:
            unopened = self._at_isolation(spelling, boundary=boundary)
            if unopened is not None:
                return unopened
        try:
            value = body(self)
        except BaseException as raised:
            return self._undone(CallbackRaised(raised), boundary=boundary)
        try:
            boundary.__exit__(None, None, None)
        except psycopg.Error as exc:
            return self._undone(CommitFailed(boundary_failure(self.dialect, exc)), boundary=None)
        return Committed(value)

    def _at_isolation(
        self,
        spelling: str,
        *,
        boundary: contextlib.AbstractContextManager[psycopg.Transaction],
    ) -> BeginFailed | None:
        """Ask the transaction just begun for ``spelling``, or report it unopened.

        Postgres accepts a level only as a transaction's first statement, which
        is what makes this part of opening the boundary rather than of the work
        inside it.

        The mapped name arrives as the bound VALUE of the transaction-scoped
        setting rather than as SQL text it is composed into, so what the
        statement can express is one level and never a second transaction mode
        or a second statement — a property of the request's SHAPE, which holds
        however the mapping above is later spelled.

        A refusal leaves a transaction that began and did nothing. Undoing it is
        this connection's business rather than the caller's, and the outcome
        reported is the one for a boundary that never opened as asked — no work
        of the caller's ran, so there is nothing to retry and nothing for a
        caller to undo. A connection too broken to undo an empty transaction is
        marked suspect, since what it would run next is unknown; disposing of it
        is the acquisition's cleanup, which is the one place that can also
        settle the accounting for it.
        """
        request = SQL("set local transaction_isolation = {}").format(Literal(spelling))
        try:
            with self._native().cursor() as cursor:
                cursor.execute(request)
        except psycopg.Error as exc:
            try:
                boundary.__exit__(type(exc), exc, exc.__traceback__)
                self._native().rollback()
            except psycopg.Error:
                self._suspect = True
            return BeginFailed(boundary_failure(self.dialect, exc))
        return None

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
        than raising it, so a rollback failure would otherwise be invisible here.
        The second request is a no-op when the transaction already ended — the
        driver sends nothing on an idle session — and is where a connection too
        broken to undo the work raises an error this can classify. Then the
        outcome of the work is unknown, so the connection is marked suspect and
        the acquisition's cleanup disposes of it rather than offering it for
        reuse.
        """
        error = trigger.error
        try:
            if boundary is not None:
                boundary.__exit__(type(error), error, error.__traceback__)
            self._native().rollback()
        except psycopg.Error as exc:
            rollback_error = boundary_failure(self.dialect, exc)
            self._suspect = True
            return RollbackFailed(trigger, rollback_error)
        return RolledBack(trigger)
