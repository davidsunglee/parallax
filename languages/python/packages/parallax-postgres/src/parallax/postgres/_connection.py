from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

import psycopg
from psycopg import postgres
from psycopg.abc import AdaptContext, Buffer
from psycopg.adapt import Dumper
from psycopg.errors import error_from_result
from psycopg.pq import DiagnosticField, ExecStatus, TransactionStatus
from psycopg.pq.abc import PGresult
from psycopg.rows import RowMaker, TupleRow, tuple_row
from psycopg.types.array import ListBinaryDumper
from psycopg.types.json import Jsonb, JsonbBinaryLoader, JsonbLoader

from parallax.core.base import TemporalBound
from parallax.core.db_error import DatabaseError, classify_error
from parallax.core.db_port import (
    AccessMode,
    BeginFailed,
    CallbackRaised,
    CanonicalWriteStatement,
    CommitFailed,
    Committed,
    ConfirmedWriteOutcome,
    CredentialResolutionError,
    CredentialSource,
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    JsonDocument,
    OrderedWriteResult,
    OrderedWriteResultComplete,
    OrderedWriteResultIntegrityError,
    OrderedWriteResultInterrupted,
    OrderedWriteTransport,
    PipelineStatement,
    RollbackFailed,
    RollbackTrigger,
    RolledBack,
    Row,
    StatementFailed,
    StatementNotExecuted,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.wire._json import dump_document, prepared_loads
from parallax.postgres._compiled_loaders import compiled_loaders

if TYPE_CHECKING:
    from parallax.postgres._context import PostgresConnectionContext

__all__ = [
    "CONNECT_KWARGS",
    "ConnectionEstablishment",
    "IncompatibleSessionError",
    "PostgresConnection",
    "initialize_connection",
]

_REVOKED = (
    "this database connection's scope has ended; acquire another one through the Database "
    "that owns the runtime"
)

_CREDENTIAL_REFUSAL = "the credential source could not produce a password"

# Resolved once, as the adapter is imported: psycopg fixes its implementation
# when it is imported, so an implementation the loaders cannot run under is
# refused before any connection exists.
_TEXT_LOADERS = compiled_loaders(psycopg.pq.__impl__)

# Resolved once, as the adapter is imported: the libpq psycopg loaded fixes
# whether a pipeline can run on any connection this process opens.
_PIPELINED = psycopg.capabilities.has_pipeline()


class _DocumentJsonbLoader(JsonbLoader):
    def __init__(self, oid: int, context: AdaptContext | None = None) -> None:
        super().__init__(oid, context)
        self._decode = prepared_loads()

    def load(self, data: Buffer) -> object:
        return self._decode(data if isinstance(data, bytes) else bytes(data))


class _DocumentJsonbBinaryLoader(JsonbBinaryLoader):
    def __init__(self, oid: int, context: AdaptContext | None = None) -> None:
        super().__init__(oid, context)
        self._decode = prepared_loads()

    def load(self, data: Buffer) -> object:
        if data and data[0] != 1:
            return super().load(data)
        value = data[1:]
        return self._decode(value if isinstance(value, bytes) else bytes(value))


class _NativeInfinityDumper(Dumper):
    """Binds the m-core open upper bound as PostgreSQL's native ``infinity``.

    It dumps text under OID 0, exactly as the bound's string spelling binds, so
    the server infers the parameter's type from the statement around it on
    every route, as it does for any unannotated bind.
    """

    def dump(self, obj: object) -> Buffer:
        del obj
        return b"infinity"


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


def reported_failure(dialect: Dialect, exc: psycopg.Error) -> DatabaseError:
    """The neutral error for a driver failure that is reported rather than raised.

    A statement failure ``execute`` meets reaches its caller through
    ``raise ... from``, which is what leaves the driver's own exception on it as
    the cause. A transaction outcome's boundary failure, and a statement failure
    or interruption an ordered write result carries, are reported instead, so the
    same chaining happens here: without it the psycopg exception the
    classification came from would be dropped on the way into the report, and a
    caller raising the error later would see no cause at all.
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


class _Int8Array(list[int]):
    """A nonempty list of exact ``int`` values, bound as one binary ``int8[]``."""

    __slots__ = ()


class _Int8ArrayBinaryDumper(ListBinaryDumper):
    """Dumps an :class:`_Int8Array` without inspecting its elements first.

    psycopg's own list dumper scans every list it binds to choose ``int2[]``,
    ``int4[]``, ``int8[]`` or ``numeric[]`` by magnitude. A fixed type skips that
    scan, and the statement's array cast (`m-dialect` array parameter cast form)
    keeps the comparison in the subject's own type whatever the array arrives as.
    """

    oid = postgres.types["int8"].array_oid
    element_oid = postgres.types["int8"].oid


_INT8_BOUNDS = (-(2**63), 2**63 - 1)


def _int8_array(values: list[object]) -> _Int8Array:
    # The int8 element dumper would bind ``True`` as 1 and ``None`` as a NULL
    # element, so anything but an exact in-range ``int`` is refused here.
    if {*map(type, values)} != {int}:
        raise TypeError("an integer array bind holds an element that is not an exact int")
    integers = cast("list[int]", values)
    if min(integers) < _INT8_BOUNDS[0] or max(integers) > _INT8_BOUNDS[1]:
        raise ValueError("an integer array bind holds an element outside the int8 range")
    return _Int8Array(integers)


def adapt_binds(binds: Sequence[object]) -> list[object]:
    """Adapt neutral binds to psycopg's driver bind types at the adapter boundary.

    A :class:`~parallax.core.db_port.JsonDocument` (the neutral ``json`` /
    value-object carrier) becomes a psycopg ``Jsonb``. A nonempty list whose
    first element is an exact ``int`` becomes an :class:`_Int8Array`, bound as
    binary ``int8[]`` on a connection :func:`initialize_connection` prepared; an
    element of any other type, or outside the int8 range, is refused rather than
    converted. Every other bind passes through unchanged. This keeps the psycopg
    bind mechanics internal to the adapter — no driver type is exported to the
    developer surface (m-db-port).
    """
    return [
        Jsonb(bind.value, dumps=dump_document)
        if isinstance(bind, JsonDocument)
        else _int8_array(cast("list[object]", bind))
        if type(bind) is list and bind and type(cast("list[object]", bind)[0]) is int
        else bind
        for bind in binds
    ]


type _Parse = Callable[[object, object], object]


class _DocumentReadRows:
    """The row factory of one cursor reading adjacent ``(presence, document)`` pairs.

    Psycopg calls it once per result the cursor receives, and it judges the pair
    metadata against that result's width then. A refusal is recorded rather
    than raised, because at pipeline sync psycopg abandons the remaining results
    of a factory that raises anything but a driver error, leaving the
    connection unusable; :func:`_fetch` raises it instead. The row maker builds
    each final provider-neutral row directly from the loaded cells, dropping
    every presence cell and folding its document through the dialect.
    """

    __slots__ = ("_pairs", "_parse", "refusal")

    def __init__(self, dialect: Dialect, document_reads: Sequence[DocumentReadOrdinals]) -> None:
        self._parse: _Parse = dialect.parse_owned_document_read
        self._pairs = tuple(document_reads)
        self.refusal: str | None = None

    def __call__(self, cursor: psycopg.Cursor[Any]) -> RowMaker[Row]:
        description = cursor.description
        width = 0 if description is None else len(description)
        self.refusal = None if description is None else _pair_refusal(self._pairs, width)
        if description is None or self.refusal is not None:
            return tuple
        if len(self._pairs) == 1:
            ((presence, _document),) = self._pairs
            return _single_pair_rows(self._parse, width, presence)
        presences = {document: presence for presence, document in self._pairs}
        omitted = frozenset(presences.values())
        schedule = tuple(
            (ordinal, presences.get(ordinal)) for ordinal in range(width) if ordinal not in omitted
        )
        return _scheduled_rows(self._parse, width, schedule)


def _pair_refusal(pairs: tuple[DocumentReadOrdinals, ...], width: int) -> str | None:
    occupied: set[int] = set()
    for presence, document in pairs:
        if document != presence + 1 or presence < 0 or document >= width:
            return "document-read ordinals must be adjacent, zero-based, and within the projection"
        if presence in occupied or document in occupied:
            return "document-read ordinal pairs must not overlap"
        occupied.update((presence, document))
    return None


def _single_pair_rows(parse: _Parse, width: int, presence: int) -> RowMaker[Row]:
    document = presence + 1
    rest = document + 1

    def row(values: Sequence[Any]) -> Row:
        if len(values) != width:
            raise ValueError("a database row does not match its result description")
        return (*values[:presence], parse(values[presence], values[document]), *values[rest:])

    return row


def _scheduled_rows(
    parse: _Parse, width: int, schedule: tuple[tuple[int, int | None], ...]
) -> RowMaker[Row]:
    def row(values: Sequence[Any]) -> Row:
        if len(values) != width:
            raise ValueError("a database row does not match its result description")
        return tuple(
            values[ordinal] if presence is None else parse(values[presence], values[ordinal])
            for ordinal, presence in schedule
        )

    return row


def _cursor(
    connection: psycopg.Connection[TupleRow], rows: _DocumentReadRows | None
) -> psycopg.Cursor[Row]:
    return connection.cursor() if rows is None else connection.cursor(row_factory=rows)


def _fetch(cursor: psycopg.Cursor[Row], rows: _DocumentReadRows | None) -> list[Row]:
    if cursor.description is None:
        return []
    if rows is not None and rows.refusal is not None:
        raise ValueError(rows.refusal)
    return cursor.fetchall()


def _document_read_rows(
    dialect: Dialect, document_reads: Sequence[DocumentReadOrdinals]
) -> _DocumentReadRows | None:
    return _DocumentReadRows(dialect, document_reads) if document_reads else None


type _NativeOperation[T, *P] = Callable[
    [psycopg.Connection[TupleRow], PostgresConnectionContext | None, *P], T
]
"""One native operation over the connection it is handed, and its prepared inputs.

Its connection context, when it has one, is the lease whose first submission it
may be: it marks the start of its driver submission immediately before the
driver is called and its completion as soon as the submission has answered,
before any result is fetched or caller work runs. Direct execution hands it no
context, and nothing is marked.
"""

type _PreparedStatement = tuple[bytes, list[object], Sequence[DocumentReadOrdinals]]


def _start_first_send(context: PostgresConnectionContext | None) -> None:
    if context is not None:
        context._start_first_send()  # pyright: ignore[reportPrivateUsage] - the lease's own first-send marker


def _complete_first_send(context: PostgresConnectionContext | None) -> None:
    if context is not None:
        context._complete_first_send()  # pyright: ignore[reportPrivateUsage] - the lease's own first-send marker


def _execute_rows(
    connection: psycopg.Connection[TupleRow],
    context: PostgresConnectionContext | None,
    dialect: Dialect,
    sql: bytes,
    binds: list[object],
    document_reads: Sequence[DocumentReadOrdinals],
) -> list[Row]:
    rows = _document_read_rows(dialect, document_reads)
    with _cursor(connection, rows) as cursor:
        _start_first_send(context)
        cursor.execute(sql, binds)
        _complete_first_send(context)
        return _fetch(cursor, rows)


def _execute_pipeline(
    connection: psycopg.Connection[TupleRow],
    context: PostgresConnectionContext | None,
    dialect: Dialect,
    statements: tuple[_PreparedStatement, ...],
) -> list[list[Row]]:
    """Present ``statements`` in one pipeline, then fetch each one's rows.

    The batch's submission is complete only once the pipeline has
    synchronized: a queued statement has not been answered, so queueing alone
    proves nothing about the round trip.
    """
    with contextlib.ExitStack() as cursors:
        pending: list[tuple[psycopg.Cursor[Row], _DocumentReadRows | None]] = []
        with connection.pipeline():
            for sql, binds, document_reads in statements:
                rows = _document_read_rows(dialect, document_reads)
                cursor = cursors.enter_context(_cursor(connection, rows))
                pending.append((cursor, rows))
                _start_first_send(context)
                cursor.execute(sql, binds)
        _complete_first_send(context)
        return [_fetch(cursor, rows) for cursor, rows in pending]


def _execute_write(
    connection: psycopg.Connection[TupleRow],
    context: PostgresConnectionContext | None,
    sql: bytes,
    binds: list[object],
) -> int:
    with connection.cursor() as cursor:
        _start_first_send(context)
        cursor.execute(sql, binds)
        _complete_first_send(context)
        return cursor.rowcount


CONNECT_KWARGS: dict[str, object] = {"autocommit": True, "row_factory": tuple_row}
"""The driver configuration every owned physical connection is created with.

``autocommit`` leaves the session outside a transaction between statements, so a
standalone read or a stream page gains no implicit whole-operation transaction
and an explicit boundary is the only thing that opens one. ``row_factory``
fixes the shape rows arrive in, so a result read without document pairs is
returned exactly as the driver built it; only a cursor reading document pairs
overrides it, with the row factory that folds them.

``close_returns`` is deliberately absent, which leaves the driver's own default:
closing a connection closes it. The opposite would make the disposal step of
cleanup silently hand a poisoned connection back as a healthy return.
"""


def initialize_connection(connection: psycopg.Connection[TupleRow]) -> None:
    """Prepare one newly created physical connection, or refuse it.

    Called once per connection, before anything may use it, and for every way
    one comes into existence. It installs the loaders the read path depends on,
    the open upper bound's dumper and the integer array dumper, on the
    connection's own adapter map so that psycopg's process-wide defaults stay
    untouched, and then checks the two effective session settings those
    loaders cannot work without that a
    connection reports — the client encoding and the date style — reading both
    off the established connection's own parameters rather than by running SQL,
    so the check costs no round trip on any creation path.

    A refusal here is a refusal of the CONNECTION, not of a statement: nothing
    modeled has run, and what would run next would decode wrongly.
    """
    # A `real` decodes to the exact binary32 value it spells, and native
    # `timestamptz` infinity normalizes at the port boundary (m-db-port) to the
    # neutral m-core sentinel rather than raising psycopg's out-of-range error;
    # that sentinel binds back as native infinity.
    connection.adapters.register_loader("float4", _TEXT_LOADERS.float4)
    connection.adapters.register_loader("timestamptz", _TEXT_LOADERS.timestamptz)
    connection.adapters.register_loader("jsonb", _DocumentJsonbLoader)
    connection.adapters.register_loader("jsonb", _DocumentJsonbBinaryLoader)
    connection.adapters.register_dumper(TemporalBound, _NativeInfinityDumper)
    connection.adapters.register_dumper(_Int8Array, _Int8ArrayBinaryDumper)
    _require_supported_session(connection)


def _require_supported_session(connection: psycopg.Connection[TupleRow]) -> None:
    """Refuse an effective session the current codecs cannot execute under.

    Two settings are checked here and the rest are the application's own. SQL
    crosses this boundary as UTF-8 bytes and a stored document is decoded as
    UTF-8 text, so a client encoding that is anything else corrupts both. A
    finite ``timestamptz`` is decoded from its text form, which psycopg's loader
    reads in ISO order, so a non-ISO ``DateStyle`` makes instants decode wrongly
    or not at all — the field order within ISO (``MDY``, ``DMY``, ``YMD``) does
    not affect that and is left alone.

    A third, ``extra_float_digits``, is load-bearing too: at zero or below the
    server rounds float output, which no loader can recover. A connection does
    not report it, so it is not checked here; the runtime's startup probe reads
    exact floats back instead.

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


class ConnectionEstablishment:
    """Everything a native pool needs to bring one connection into existence, and
    the last refusal met doing it.

    Two callbacks and one record. :meth:`connect_kwargs` produces the driver
    keywords each physical connection is dialed with, resolving the credential
    source as it goes; ``__call__`` is the pool's ``configure``, initializing
    the connection that resulted. Both write the one record, which is why they
    live together: the write discipline is stated once rather than agreed on by
    two modules.

    The record exists because a pool creates most of its connections on its own
    background path: a refusal there is retried and logged where a caller
    waiting for a connection never sees it, and what that caller eventually gets
    is a bare timeout naming nothing to fix. Keeping the last refusal lets the
    timeout say what is actually wrong.

    One record serves every attempt, because a pool dials several at once on
    several workers and the caller it answers is waiting on the pool rather than
    on any one of them. Two rules arbitrate the writes. The most recent refusal
    wins, so a caller is told the last thing establishment actually met rather
    than the first. Only a connection that became USABLE clears the record, so
    what ends a refusal is the outcome a caller could have been handed — a
    resolved credential is not one, since the connection it was resolved for may
    still fail to dial or to initialize, and clearing there would let one
    attempt's partial progress erase another's completed refusal and leave a
    bare timeout in its place. The record therefore reads: the last refusal met
    since the last connection became usable, or nothing if one has since.
    """

    __slots__ = ("last_refusal",)

    def __init__(self) -> None:
        self.last_refusal: IncompatibleSessionError | CredentialResolutionError | None = None

    def __call__(self, connection: psycopg.Connection[TupleRow]) -> None:
        try:
            initialize_connection(connection)
        except IncompatibleSessionError as refusal:
            self.last_refusal = refusal
            raise
        self.last_refusal = None

    def connect_kwargs(
        self, base: dict[str, object], source: CredentialSource
    ) -> Callable[[], dict[str, object]]:
        """The pool's ``kwargs``, resolved anew for every connection attempt.

        psycopg_pool calls this on each connection attempt and on no other
        occasion, which is what the seam asks for: the credential is an input to
        connecting, so an attempt that never reaches a connection has already
        asked and a retried attempt asks again, while a reused retained
        connection never reaches it at all. A fresh dictionary comes back each
        time, so the secret is never written into the base the next connection
        would inherit.

        Anything the source raises that is not already a
        :class:`~parallax.core.db_port.CredentialResolutionError` is wrapped in
        one with fixed text and the original chained, so classification does not
        depend on a provider's discipline and the pool's own warning line — which
        prints the exception's text — carries nothing a source put in a message.

        A refusal is recorded; a credential is not, because producing one
        establishes nothing. Initialization is where a connection proves usable
        and therefore where the record clears.
        """

        def resolve() -> dict[str, object]:
            try:
                credential = source.resolve()
            except CredentialResolutionError as refusal:
                self.last_refusal = refusal
                raise
            except Exception as exc:
                refusal = CredentialResolutionError(_CREDENTIAL_REFUSAL)
                self.last_refusal = refusal
                raise refusal from exc
            return {**base, "password": credential.secret}

        return resolve


_COMMAND_OK = ExecStatus.COMMAND_OK
_FATAL_ERROR = ExecStatus.FATAL_ERROR
_PIPELINE_ABORTED = ExecStatus.PIPELINE_ABORTED
_NOT_EXECUTED = StatementNotExecuted()
_UNANSWERED = "PostgreSQL ended an ordered write before answering every statement it was sent"


@dataclass(frozen=True, slots=True)
class _Unowned:
    """A failure a statement's result carried that the statement did not cause,
    such as the session ending around it."""

    error: DatabaseError


@dataclass(frozen=True, slots=True)
class _Unexpected:
    """A result no count-only statement produces, described without its content."""

    description: str


type _Established = ConfirmedWriteOutcome | _Unowned | _Unexpected


class _ResultIntake:
    """What one ordered write's count cursors record their results through.

    Psycopg pairs each result with the cursor whose command produced it by queue
    position. A driver call that raises can drop results it had already taken
    from libpq while their queue positions remain, so a result handed over after
    one raises could pair with the wrong cursor and is never trusted.
    """

    __slots__ = ("_dialect", "_encoding", "accepting", "recorded")

    def __init__(self, dialect: Dialect, encoding: str) -> None:
        self._dialect = dialect
        self._encoding = encoding
        self.accepting = True
        self.recorded = 0

    def established(self, results: list[PGresult]) -> _Established:
        self.recorded += 1
        if len(results) != 1:
            for result in results:
                if result.status == _FATAL_ERROR:
                    return _Unowned(self._error(result))
            return _Unexpected(f"{len(results)} results")
        result = results[0]
        status = result.status
        if status == _COMMAND_OK:
            count = result.command_tuples
            return _Unexpected("no affected-row count") if count is None else count
        if status == _PIPELINE_ABORTED:
            return _NOT_EXECUTED
        if status != _FATAL_ERROR:
            return _Unexpected(f"result status {_status_name(status)}")
        error = self._error(result)
        # A statement's own failure is an ERROR the server raised with a
        # SQLSTATE. A FATAL or PANIC ends the session wherever it happens to be,
        # and an error libpq raises itself carries no SQLSTATE at all.
        owned = result.error_field(DiagnosticField.SEVERITY_NONLOCALIZED) == b"ERROR" and (
            result.error_field(DiagnosticField.SQLSTATE) is not None
        )
        return StatementFailed(error) if owned else _Unowned(error)

    def _error(self, result: PGresult) -> DatabaseError:
        return reported_failure(self._dialect, error_from_result(result, self._encoding))


def _status_name(status: int) -> str:
    try:
        return ExecStatus(status).name
    except ValueError:
        return str(status)


class _CountCursor(psycopg.Cursor[TupleRow]):
    """One presented statement's cursor, recording the outcome its result
    establishes instead of attaching the result.

    Psycopg checks a result before attaching it and raises on a failed or
    aborted one, so both hooks are replaced: recording in the check is what
    keeps those outcomes, and attaching nothing keeps no result set or row
    machinery.
    """

    __slots__ = ("_intake", "outcome")

    def __init__(self, connection: psycopg.Connection[TupleRow], intake: _ResultIntake) -> None:
        super().__init__(connection)
        self._intake = intake
        self.outcome: _Established | None = None

    def _check_results(self, results: list[PGresult]) -> None:
        intake = self._intake
        if intake.accepting:
            self.outcome = intake.established(results)

    def _set_results(self, results: list[PGresult]) -> None:
        del results


def _write_in_order(
    connection: psycopg.Connection[TupleRow],
    context: PostgresConnectionContext | None,
    dialect: Dialect,
    statements: Sequence[CanonicalWriteStatement],
) -> OrderedWriteResult:
    """Present ``statements`` in one pipeline and answer what it established.

    The pipeline's exit is its one synchronization, so its results arrive while
    later statements are queued or as it exits. An exit that raises leaves the
    results it recorded untrusted; one that returns lost none.

    Each statement executes unprepared, so no preparation command of its own
    shares the result queue. Prepared-cache maintenance psycopg queues between
    statements answers no statement, and its failure ends collection.
    """
    ambient = sys.exception()
    intake = _ResultIntake(dialect, connection.info.encoding)
    cursors: list[_CountCursor] = []
    settled: int | None = None
    try:
        with connection.pipeline():
            try:
                for statement in statements:
                    query = dialect.to_driver_sql(statement.sql).encode()
                    binds = adapt_binds(statement.binds)
                    cursor = _CountCursor(connection, intake)
                    cursors.append(cursor)
                    _start_first_send(context)
                    cursor.execute(query, binds, prepare=False)
            except BaseException:
                intake.accepting = False
                raise
            settled = intake.recorded
    except Exception as escaped:
        displaced = _displaced_control_flow(escaped, ambient)
        if displaced is None:
            trusted = intake.recorded if settled is None else settled
            return _answered(dialect, cursors[:trusted], len(cursors), len(statements), escaped)
    else:
        return _answered(dialect, cursors[: intake.recorded], len(cursors), len(statements), None)
    raise displaced


def _displaced_control_flow(
    escaped: Exception, ambient: BaseException | None
) -> BaseException | None:
    """The control-flow exception raised during the write that ``escaped``
    took the place of, if any.

    Psycopg answers an interrupt while it waits by cancelling the statement and
    collecting what remains. A count cursor records the cancellation rather
    than raising it, so a failure later in that collection, such as aborted
    prepared-cache maintenance, escapes instead and carries the interrupt only
    as context. ``ambient`` is the exception already being handled when the
    write began; its context chain predates the write.
    """
    context = escaped.__context__
    while context is not None and context is not ambient:
        if not isinstance(context, Exception):
            return context
        context = context.__context__
    return None


def _answered(
    dialect: Dialect,
    recorded: list[_CountCursor],
    sent: int,
    presented: int,
    escaped: Exception | None,
) -> OrderedWriteResult:
    """The result the ``recorded`` cursors establish for ``presented``
    statements, of which only the first ``sent`` ever reached psycopg.

    Psycopg hands results over in queue order, so the cursors that recorded one
    are always a leading run.
    """
    established: list[_Established] = []
    for index, cursor in enumerate(recorded):
        outcome = cast("_Established", cursor.outcome)
        if isinstance(outcome, _Unexpected):
            raise OrderedWriteResultIntegrityError(
                f"PostgreSQL answered statement {index} of an ordered write with "
                f"{outcome.description}, which no count-only statement produces"
            )
        established.append(outcome)
    confirmed = _confirmed(established)
    if escaped is None and len(confirmed) == presented:
        return OrderedWriteResultComplete(confirmed)
    return OrderedWriteResultInterrupted(
        confirmed,
        sent - len(confirmed),
        presented - sent,
        _interruption(dialect, established, escaped),
    )


def _confirmed(established: list[_Established]) -> tuple[ConfirmedWriteOutcome, ...]:
    """The leading outcomes each established for its own statement.

    An aborted statement is confirmed unexecuted only behind a confirmed
    failure; an abort with no failure before it was caused by something no
    statement owns.
    """
    confirmed: list[ConfirmedWriteOutcome] = []
    failed = False
    for outcome in established:
        if isinstance(outcome, _Unowned | _Unexpected) or (
            isinstance(outcome, StatementNotExecuted) and not failed
        ):
            break
        failed = failed or isinstance(outcome, StatementFailed)
        confirmed.append(outcome)
    return tuple(confirmed)


def _interruption(
    dialect: Dialect, established: list[_Established], escaped: Exception | None
) -> Exception:
    for outcome in established:
        if isinstance(outcome, _Unowned):
            return outcome.error
    if escaped is None:
        return classify_error(dialect, None, _UNANSWERED)
    return reported_failure(dialect, escaped) if isinstance(escaped, psycopg.Error) else escaped


class PostgresConnection:
    """One acquisition's execution access: a :class:`DatabaseConnection` over a
    psycopg connection somebody else owns the lifetime of.

    It runs statements and demarcates transactions, and it does nothing about
    the connection's life. Built over a native connection, it is direct access
    to a session its owner manages, and it never replaces that session. Built
    from a connection context, it holds no connection at all: every operation
    borrows the context's current one, which is how a connection the context
    replaced is the one the next operation reaches. Revocation is how the owner
    ends the scope: the access is cleared, so a caller holding this past its
    acquisition executes nothing and — more importantly — retains nothing.
    """

    dialect: Dialect = POSTGRES
    """The one place this adapter's SQL spelling is stated.

    Declared on the class, so a composition root reads it off the class itself
    without opening a connection, and every dialect decision made here — error
    classification, document-read parsing — consults it rather than a module
    name that could drift from it.
    """

    __slots__ = ("_connection", "_context", "_ordered", "_suspect")

    def __init__(self, connection: psycopg.Connection[TupleRow]) -> None:
        self._grant(connection, None)

    @classmethod
    def _from_context(cls, context: PostgresConnectionContext) -> PostgresConnection:
        execution = cls.__new__(cls)
        execution._grant(None, context)
        return execution

    def _grant(
        self,
        connection: psycopg.Connection[TupleRow] | None,
        context: PostgresConnectionContext | None,
    ) -> None:
        self._connection = connection
        self._context = context
        self._suspect = False
        self._ordered: OrderedWriteTransport | None = self._ordered_writes if _PIPELINED else None

    @property
    def suspect(self) -> bool:
        """Whether reuse of this connection could not be established.

        Set where a boundary could not be brought back to a known state — a
        transaction context that failed to enter, a rollback that failed, or
        characteristics that could not be cleared. Under a connection context
        it is the context's own record for its current connection.
        It is a report for cleanup to act on, not an action: this class closes
        nothing and returns nothing.
        """
        context = self._context
        if context is not None:
            return context._suspect  # pyright: ignore[reportPrivateUsage] - the owner's record for its current connection
        return self._suspect

    def revoke(self) -> bool:
        """End this scope's access and report whether it left the connection suspect.

        Idempotent, and it never touches the connection itself. Clearing the
        access here is what makes a later call raise before reaching a driver
        instead of running on a connection somebody else now holds, and what
        leaves a saved reference reaching neither a connection nor the context
        that could replace one.
        """
        suspect = self.suspect
        self._connection = None
        self._context = None
        return suspect

    def _current_native(self) -> psycopg.Connection[TupleRow]:
        context = self._context
        if context is not None:
            return context._current_native()  # pyright: ignore[reportPrivateUsage] - the owner's current connection
        connection = self._connection
        if connection is None:
            raise RuntimeError(_REVOKED)
        return connection

    def _invoke_native[T, *P](
        self, operation: _NativeOperation[T, *P], /, *prepared: *P, replay_safe: bool
    ) -> T:
        context = self._context
        if context is not None:
            return context._run_native(operation, *prepared, replay_safe=replay_safe)  # pyright: ignore[reportPrivateUsage] - the owner's one native-operation runner
        return operation(self._current_native(), None, *prepared)

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        """Run one statement and return its rows.

        Under a connection context, a ``read_only`` submission that is the
        lease's first and meets a broken session is submitted once more,
        unchanged, on the connection the context replaces it with; nothing else
        is ever resubmitted.
        """
        query = sql.encode()
        adapted = adapt_binds(binds)
        with translating_driver_errors(self.dialect):
            return self._invoke_native(
                _execute_rows, self.dialect, query, adapted, document_reads, replay_safe=read_only
            )

    def execute_pipeline(
        self,
        statements: Sequence[PipelineStatement],
        *,
        read_only: bool = False,
    ) -> list[list[Row]]:
        del read_only
        if not statements:
            self._current_native()
            return []
        prepared = tuple(
            (statement.sql.encode(), adapt_binds(statement.binds), statement.document_reads)
            for statement in statements
        )
        with translating_driver_errors(self.dialect):
            return self._invoke_native(_execute_pipeline, self.dialect, prepared, replay_safe=False)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        query = sql.encode()
        adapted = adapt_binds(binds)
        with translating_driver_errors(self.dialect):
            return self._invoke_native(_execute_write, query, adapted, replay_safe=False)

    @property
    def ordered_write_transport(self) -> OrderedWriteTransport | None:
        """This scope's ordered write operation, stored once, where the libpq
        psycopg loaded can run a pipeline; None where it cannot."""
        return self._ordered

    def _ordered_writes(self, statements: Sequence[CanonicalWriteStatement]) -> OrderedWriteResult:
        """The ordered write transport operation over this scope's connection.

        An interruption leaves the connection in a state nothing established,
        as does any exception escaping it, so either marks this scope suspect
        for its cleanup to dispose of; the connection is reached anew on every
        call, so a saved reference to this operation runs nothing once the
        scope is revoked.
        """
        self._current_native()
        if not statements:
            return OrderedWriteResultComplete(())
        try:
            result = self._invoke_native(
                _write_in_order, self.dialect, statements, replay_safe=False
            )
        except BaseException:
            self._mark_suspect()
            raise
        if isinstance(result, OrderedWriteResultInterrupted):
            self._mark_suspect()
        return result

    def _mark_suspect(self) -> None:
        context = self._context
        if context is not None:
            context._mark_suspect()  # pyright: ignore[reportPrivateUsage] - the owner's record for its current connection
        else:
            self._suspect = True

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
        access_mode: AccessMode | None = None,
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

        A requested ``isolation`` or ``access_mode`` travels inside the driver's
        own ``BEGIN``: each maps to the driver attribute it composes that command
        from, assigned while the session is idle, so the request governs this
        transaction alone and costs no request of its own. A request the
        database refuses ends the boundary
        :class:`~parallax.core.db_port.BeginFailed`: no work of the caller's was
        attempted, and a request silently downgraded to one the caller did not
        make is worse than one refused. Once the outer boundary ends, both
        attributes are cleared so the session's own defaults govern the next one.

        Under a connection context, an outer ``BEGIN`` that is the lease's first
        submission and meets a broken session is opened once more, with the same
        characteristics, on the connection the context replaces it with; the
        callback runs only once a boundary has opened, so it never runs twice.

        A call made while this session's transaction is already open joins it
        through a savepoint and leaves the characteristics to the outer
        boundary; the driver refuses a characteristic requested there, before
        the savepoint opens.
        """
        connection = self._current_native()
        # Resolved before the driver is touched, so a request outside its
        # vocabulary — a type violation the handle's own check would have
        # caught — changes no driver state and opens nothing.
        isolation_level, read_only = _transaction_characteristics(isolation, access_mode)
        outer = _idle(connection)
        try:
            try:
                boundary = self._invoke_native(
                    _open_transaction,
                    self,
                    isolation_level,
                    read_only,
                    outer or isolation is not None or access_mode is not None,
                    replay_safe=outer,
                )
            except psycopg.Error as exc:
                return BeginFailed(reported_failure(self.dialect, exc))
            try:
                value = body(self)
            except BaseException as raised:
                return self._rollback_transaction(CallbackRaised(raised), boundary=boundary)
            try:
                boundary.__exit__(None, None, None)
            except psycopg.Error as exc:
                return self._rollback_transaction(
                    CommitFailed(reported_failure(self.dialect, exc)), boundary=None
                )
            return Committed(value)
        finally:
            if outer:
                self._clear_characteristics()

    def _clear_characteristics(self) -> None:
        """Leave the session's own defaults to govern the next boundary, or mark
        it suspect where that cannot be established.

        A suspect session is left as it is: disposal, not repair, ends its use,
        and a session whose transaction context failed to enter may report idle
        while the driver's own bookkeeping says otherwise. So is a scope with no
        connection left to clear. A failure here never replaces the outcome the
        boundary already reached.
        """
        if self.suspect:
            return
        try:
            connection = self._current_native()
        except RuntimeError:
            return
        try:
            if not _idle(connection):
                self._mark_suspect()
                return
            connection.isolation_level = None
            connection.read_only = None
        except BaseException as exc:
            self._mark_suspect()
            if not isinstance(exc, Exception):
                raise

    def _rollback_transaction(
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
            self._current_native().rollback()
        except psycopg.Error as exc:
            rollback_error = reported_failure(self.dialect, exc)
            self._mark_suspect()
            return RollbackFailed(trigger, rollback_error)
        return RolledBack(trigger)


def _idle(connection: psycopg.Connection[TupleRow]) -> bool:
    try:
        return connection.pgconn.transaction_status == TransactionStatus.IDLE
    except Exception:
        return False


def _open_transaction(
    connection: psycopg.Connection[TupleRow],
    context: PostgresConnectionContext | None,
    execution: PostgresConnection,
    isolation: psycopg.IsolationLevel | None,
    read_only: bool | None,
    characterize: bool,
) -> contextlib.AbstractContextManager[psycopg.Transaction]:
    """Enter a fresh driver transaction context on ``connection``, carrying the
    mapped characteristics where ``characterize`` asks for them.

    The driver counts a transaction context as open before it sends ``BEGIN``
    and does not uncount one whose entry failed, so any failed entry leaves the
    session unfit for reuse even when the server reports it idle; the session
    is marked suspect for disposal rather than repaired. A refused assignment
    happens before entry and says nothing about that bookkeeping.
    """
    if characterize:
        connection.isolation_level = isolation
        connection.read_only = read_only
    boundary = connection.transaction()
    _start_first_send(context)
    try:
        boundary.__enter__()
    except BaseException:
        execution._mark_suspect()  # pyright: ignore[reportPrivateUsage] - the same-module facade this entry opens for
        raise
    _complete_first_send(context)
    return boundary


_ISOLATION_LEVELS: Final[dict[IsolationLevel, psycopg.IsolationLevel]] = {
    "read_committed": psycopg.IsolationLevel.READ_COMMITTED,
    "repeatable_read": psycopg.IsolationLevel.REPEATABLE_READ,
    "serializable": psycopg.IsolationLevel.SERIALIZABLE,
}

_READ_ONLY: Final[dict[AccessMode, bool]] = {"read_only": True, "read_write": False}


def _transaction_characteristics(
    isolation: IsolationLevel | None, access_mode: AccessMode | None
) -> tuple[psycopg.IsolationLevel | None, bool | None]:
    """The driver's ``isolation_level`` and ``read_only`` values for a boundary's
    requests; a request naming nothing maps to ``None``, the session's own default.
    """
    return (
        None if isolation is None else _ISOLATION_LEVELS[isolation],
        None if access_mode is None else _READ_ONLY[access_mode],
    )
