"""Postgres scoped-execution internal-seam unit tests (Docker-free).

The public exports are ``PostgresAdapter``, ``PostgresRole``, the two retention
policies, and ``isolation_spelling`` (§8 topology); psycopg bind mechanics and the scoped
connection under an acquisition stay internal. The bind-adaptation seam — the
neutral ``JsonDocument`` carrier becoming a psycopg ``Jsonb`` at the adapter
boundary — the `m-db-error` port-boundary re-raise (every psycopg exception
translated to a neutral ``DatabaseError``), and the per-connection setup and
transaction phases are all provable over a fake connection here; the
end-to-end deadlock witness lives in the provider lane and the resource
lifetimes in ``test_postgres_pool.py``.
"""

from __future__ import annotations

import decimal
import gc
import json
import struct
from collections.abc import Callable, Sequence
from types import FrameType, FunctionType, ModuleType, SimpleNamespace
from typing import Any, cast

import psycopg
import pytest
from psycopg import errors, postgres
from psycopg.abc import Dumper, Loader
from psycopg.adapt import AdaptersMap, PyFormat, Transformer
from psycopg.pq import ExecStatus, Format, TransactionStatus
from psycopg.rows import TupleRow
from psycopg.sql import Composable
from psycopg.types.json import Jsonb, JsonbLoader

import parallax.postgres
import parallax.postgres._connection as connection_module
from parallax.core.base import (
    INFINITY,
    SQL_NULL,
    STRING,
    FrozenMap,
    PresentDocument,
    TemporalBound,
)
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    ISOLATION_LEVELS,
    AccessMode,
    BeginFailed,
    CallbackRaised,
    CanonicalWriteStatement,
    CommitFailed,
    Committed,
    DatabaseConnection,
    JsonDocument,
    OrderedWriteResult,
    OrderedWriteResultComplete,
    OrderedWriteResultIntegrityError,
    OrderedWriteResultInterrupted,
    PipelineStatement,
    RollbackFailed,
    RolledBack,
    StatementFailed,
    StatementNotExecuted,
    isolation_level,
)
from parallax.core.dialect import PhysicalIndexName
from parallax.core.document_codec import (
    Present,
    SetScalar,
    apply_prepared_patches,
    prepare_patches,
)
from parallax.core.metamodel import (
    ValueObjectAttributeDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.wire._json import authored_token
from parallax.postgres import PostgresAdapter, isolation_spelling
from parallax.postgres._compiled_loaders import compiled_loaders
from parallax.postgres._connection import (
    ConnectionEstablishment,
    IncompatibleSessionError,
    PostgresConnection,
    adapt_binds,
    initialize_connection,
    translate_driver_error,
    translating_driver_errors,
)
from tests.unit.postgres._native_pipeline_support import (
    Result,
    Server,
    Statement,
    aborted,
    counted,
    failed,
    native_session,
    script,
    unowned,
)

# Read off the class rather than named again here: these seams are the adapter's
# own internals, so grading them under any other dialect would grade something
# the adapter never runs.
_DIALECT = PostgresAdapter.dialect


class _IntSubclass(int):
    """An ``int`` that is not exactly one."""


def test_public_surface_is_the_adapter_its_options_and_this_engines_isolation_spelling() -> None:
    assert parallax.postgres.__all__ == [
        "OnDemandOptions",
        "PoolOptions",
        "PostgresAdapter",
        "PostgresRole",
        "isolation_spelling",
    ]
    assert not hasattr(parallax.postgres, "Json")
    assert not hasattr(parallax.postgres, "Jsonb")


def test_every_portable_level_has_exactly_one_postgres_spelling() -> None:
    # The map is keyed by the port's own vocabulary, so a level added there with no
    # spelling here — or a spelling for a level the vocabulary does not name — is a
    # gap a caller meets as a KeyError on the level it asked for.
    spellings = {level: isolation_spelling(isolation_level(level)) for level in ISOLATION_LEVELS}
    assert spellings == {
        "read_committed": "read committed",
        "repeatable_read": "repeatable read",
        "serializable": "serializable",
    }


def testadapt_binds_wraps_json_documents_and_passes_scalars_through() -> None:
    adapted = adapt_binds([1, "x", JsonDocument({"city": "Oslo"}), None])
    assert adapted[0] == 1
    assert adapted[1] == "x"
    assert isinstance(adapted[2], Jsonb)
    assert adapted[3] is None


def testadapt_binds_wraps_the_document_value() -> None:
    document = {"geo": {"lat": 1}}
    (adapted,) = adapt_binds([JsonDocument(document)])
    assert isinstance(adapted, Jsonb)
    assert adapted.obj == document


def test_frozen_documents_dump_byte_equal_to_the_standard_json_settings() -> None:
    mutable = {"city": "Oslo", "tags": [{"label": "home"}], "active": True}
    frozen = FrozenMap({"city": "Oslo", "tags": ({"label": "home"},), "active": True})
    transformer = Transformer(postgres.adapters)

    baseline = transformer.dump_sequence([Jsonb(mutable)], [PyFormat.AUTO])
    actual = transformer.dump_sequence(adapt_binds([JsonDocument(frozen)]), [PyFormat.AUTO])

    assert actual == baseline


def test_frozen_document_dump_preserves_standard_unsupported_leaf_errors() -> None:
    transformer = Transformer(postgres.adapters)
    adapted = adapt_binds([JsonDocument(FrozenMap({"unsupported": object()}))])

    with pytest.raises(TypeError, match="not JSON serializable"):
        transformer.dump_sequence(adapted, [PyFormat.AUTO])


def test_a_patched_successor_binds_its_retained_numbers_with_their_exact_meaning() -> None:
    # The stored document arrives through the adapter's own loader, the codec
    # patches a declared leaf and carries the unknown members, and the bind
    # writes what was carried with the meaning it was read with.
    stored = connection_module._DocumentJsonbLoader(3802).load(  # pyright: ignore[reportPrivateUsage] - the registered loader is this test's subject
        b'{"city": "Oslo", "reading": 0.10000000000000001, "wide": 1e999, "plain": 0.1}'
    )
    shape = ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration(name="city", type=STRING, nullable=True),),
    ).member_shape
    successor = apply_prepared_patches(
        stored, prepare_patches(shape, [SetScalar(("city",), Present("Bergen"))])
    )
    (dumped,) = Transformer(postgres.adapters).dump_sequence(
        adapt_binds([JsonDocument(successor)]), [PyFormat.AUTO]
    )

    assert dumped is not None
    assert json.loads(bytes(dumped), parse_float=decimal.Decimal) == {
        "city": "Bergen",
        "reading": decimal.Decimal("0.10000000000000001"),
        "wide": decimal.Decimal("1e999"),
        "plain": decimal.Decimal("0.1"),
    }


# -- port-boundary re-raise (m-db-error) ----------------------------------------


def test_translate_driver_error_maps_a_unique_violation() -> None:
    error = translate_driver_error(_DIALECT, errors.UniqueViolation("dup key"))
    assert error.category == "uniqueViolation"
    assert error.native_code == "23505"
    assert error.violates_unique_index
    assert error.message == "dup key"


class _NamedUniqueViolation(errors.UniqueViolation):
    """A `23505` whose libpq diagnostics name the index it violated.

    libpq treats an index as a constraint even when no constraint syntax created
    it, so a bare `create unique index` reports its own name in this field —
    which is what makes the name correlate with a rollout's own provenance.
    """

    @property
    def diag(self) -> Any:
        return SimpleNamespace(constraint_name="pxi_widget_label_0f1e2d3c")


def test_translate_driver_error_forwards_the_violated_index_name() -> None:
    error = translate_driver_error(_DIALECT, _NamedUniqueViolation("dup key"))
    assert error.violated_index == PhysicalIndexName("pxi_widget_label_0f1e2d3c")


class _NamedCheckViolation(errors.CheckViolation):
    """A `23514` whose libpq diagnostics name the check it violated."""

    @property
    def diag(self) -> Any:
        return SimpleNamespace(constraint_name="pxc_tx_balance_c54215aec2277be436e89b2c6506715d")


def test_translate_driver_error_keeps_a_checks_name_without_reading_it_as_an_index() -> None:
    error = translate_driver_error(_DIALECT, _NamedCheckViolation("check failed"))
    assert (error.category, error.native_code) == ("constraintViolation", "23514")
    assert error.constraint_name == "pxc_tx_balance_c54215aec2277be436e89b2c6506715d"
    assert error.violated_index is None
    assert not error.is_retriable


def test_translate_driver_error_reports_no_index_when_the_diagnostics_name_none() -> None:
    # A duplicate whose detecting path named no constraint is an ordinary
    # negative correlation, not a defect: the adapter interprets nothing.
    error = translate_driver_error(_DIALECT, errors.UniqueViolation("dup key"))
    assert error.violates_unique_index
    assert error.violated_index is None


def test_translate_driver_error_is_uncategorized_without_sqlstate() -> None:
    # A driver failure with no SQLSTATE (a dropped connection) stays uncategorized.
    error = translate_driver_error(_DIALECT, psycopg.OperationalError("connection closed"))
    assert error.category is None
    assert error.native_code is None
    assert error.message == "connection closed"


def test_translating_driver_errors_reraises_as_a_database_error() -> None:
    with pytest.raises(DatabaseError) as exc_info, translating_driver_errors(_DIALECT):
        raise errors.DeadlockDetected("deadlock detected")
    assert exc_info.value.category == "deadlock"
    assert exc_info.value.is_retriable
    assert exc_info.value.native_code == "40P01"


def test_translating_driver_errors_passes_a_clean_block() -> None:
    with translating_driver_errors(_DIALECT):
        value = 1 + 1
    assert value == 2


def test_translating_driver_errors_passes_a_non_driver_exception() -> None:
    class _Boom(Exception):
        pass

    with pytest.raises(_Boom), translating_driver_errors(_DIALECT):
        raise _Boom


class _FakeCursor:
    """A psycopg-cursor stand-in whose ``execute`` raises a preset driver error.

    Every statement it is handed is appended to the list its connection gave it,
    so a test can ask what the adapter actually sent and in what order. A
    statement arrives either as the encoded text the port sends or as a composed
    statement, so the list holds both and :func:`_sent_sql` renders either one.
    """

    def __init__(self, error: psycopg.Error | None, executed: list[object]) -> None:
        self._error = error
        self._executed = executed
        self.description: object | None = None
        self.rowcount = 0

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(
        self, sql: bytes | Composable, _binds: object = None, *, prepare: bool | None = None
    ) -> None:
        del prepare
        self._executed.append(sql)
        if self._error is not None:
            raise self._error

    def fetchall(self) -> list[tuple[object, ...]]:
        return []


class _FakeTxn:
    """A ``connection.transaction()`` stand-in, faithful about what it hides.

    Entry decides, as psycopg does, from the session's own status whether it
    opens the outer transaction — a ``BEGIN`` composed from the connection's
    characteristics at that moment — or a savepoint inside one, and raises the
    begin failure the connection holds without leaving the session in a
    transaction. Commit raises the failure asked of it. A ROLLBACK failure does
    NOT raise: psycopg's own transaction context catches it, logs a warning,
    and lets the exception that triggered the rollback carry on — which is why
    the adapter asks the connection to roll back a second time, and why this
    stand-in leaves that failure to :meth:`_FakeConnection.rollback` rather than
    raising it here. A stand-in that raised it would prove a boundary the real
    driver never presents.
    """

    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection
        self._outer = False

    def __enter__(self) -> _FakeTxn:
        connection = self._connection
        self._outer = connection.pgconn.transaction_status == TransactionStatus.IDLE
        connection.boundary.append(
            ("BEGIN", connection.isolation_level, connection.read_only)
            if self._outer
            else "SAVEPOINT"
        )
        if connection.begin_error is not None:
            raise connection.begin_error
        if self._outer:
            connection.pgconn.transaction_status = TransactionStatus.INTRANS
        return self

    def __exit__(self, _exc_type: object, exc: BaseException | None, _tb: object) -> bool:
        connection = self._connection
        committing = exc is None
        if self._outer:
            connection.boundary.append("COMMIT" if committing else "ROLLBACK")
            connection.pgconn.transaction_status = connection.status_after_boundary
        else:
            connection.boundary.append("RELEASE" if committing else "ROLLBACK TO")
        if committing and connection.commit_error is not None:
            raise connection.commit_error
        return False


class _FakePipeline:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def __enter__(self) -> _FakePipeline:
        self._events.append("pipeline-enter")
        return self

    def __exit__(self, *_: object) -> bool:
        self._events.append("pipeline-exit")
        return False


class _RecordingAdapters(AdaptersMap):
    """A connection's own adapter map over psycopg's defaults, as a real
    connection's is, recording every adapter registered on it."""

    def __init__(self) -> None:
        super().__init__(postgres.adapters)
        self.registered: list[tuple[object, object]] = []

    def register_loader(self, oid: int | str, loader: type[Loader]) -> None:
        super().register_loader(oid, loader)
        self.registered.append((oid, loader))

    def register_dumper(self, cls: type | str | None, dumper: type[Dumper]) -> None:
        super().register_dumper(cls, dumper)
        self.registered.append((cls, dumper))


class _FakeInfo:
    """A ``connection.info`` stand-in answering the two settings initialization checks.

    Both are read off established connection parameters rather than by running
    SQL, so a stand-in supplies them as values and the check costs no statement
    here either.
    """

    def __init__(self, *, encoding: str = "utf-8", date_style: str | None = "ISO, MDY") -> None:
        self.encoding = encoding
        self._date_style = date_style

    def parameter_status(self, name: str) -> str | None:
        return self._date_style if name == "DateStyle" else None


class _FakePgConn:
    """The libpq status a session reports, readable or failing to be read."""

    def __init__(self) -> None:
        self.status = TransactionStatus.IDLE
        self.status_error: Exception | None = None

    @property
    def transaction_status(self) -> TransactionStatus:
        if self.status_error is not None:
            raise self.status_error
        return self.status

    @transaction_status.setter
    def transaction_status(self, status: TransactionStatus) -> None:
        self.status = status


class _FakeConnection:
    """A minimal psycopg-connection stand-in for the boundary tests.

    Each injected failure is a public attribute read at call time, so one
    connection — and therefore one adapter — can be driven through each failure
    site in turn. ``begin_error`` is set for the invocation that needs it: a
    boundary that fails to begin reaches neither commit nor rollback.
    ``rollback_error`` belongs to the connection rather than to the transaction
    context because that is where a real rollback failure becomes visible.

    ``boundary`` records, in order, each characteristic the driver accepted and
    each transaction command its context would send, which is the whole
    observable of a boundary's characteristics: the driver composes its
    ``BEGIN`` from them and sends nothing when they are assigned. As psycopg
    does, an assignment is refused unless the session is idle, and
    ``refuse_assignment`` can refuse one it would otherwise accept.
    """

    def __init__(
        self,
        *,
        cursor_error: psycopg.Error | None = None,
        begin_error: BaseException | None = None,
        commit_error: psycopg.Error | None = None,
        rollback_error: psycopg.Error | None = None,
        encoding: str = "utf-8",
        date_style: str | None = "ISO, MDY",
    ) -> None:
        self.info = _FakeInfo(encoding=encoding, date_style=date_style)
        self.pgconn = _FakePgConn()
        self.cursor_error = cursor_error
        self.begin_error = begin_error
        self.commit_error = commit_error
        self.rollback_error = rollback_error
        self.refuse_assignment: Callable[[str, object], BaseException | None] = (
            lambda _name, _value: None
        )
        self.status_after_boundary = TransactionStatus.IDLE
        self.adapters = _RecordingAdapters()
        self.rollbacks = 0
        self.closed = False
        self.executed: list[object] = []
        self.boundary: list[object] = []
        self.begins = 0
        self.pipeline_events: list[str] = []
        self._isolation_level: psycopg.IsolationLevel | None = None
        self._read_only: bool | None = None

    @property
    def isolation_level(self) -> psycopg.IsolationLevel | None:
        return self._isolation_level

    @isolation_level.setter
    def isolation_level(self, value: psycopg.IsolationLevel | None) -> None:
        self._accept("isolation_level", value)
        self._isolation_level = value

    @property
    def read_only(self) -> bool | None:
        return self._read_only

    @read_only.setter
    def read_only(self, value: bool | None) -> None:
        self._accept("read_only", value)
        self._read_only = value

    def _accept(self, name: str, value: object) -> None:
        refusal = self.refuse_assignment(name, value)
        if refusal is not None:
            raise refusal
        if self.pgconn.transaction_status != TransactionStatus.IDLE:
            raise errors.ProgrammingError(f"can't change {name!r} now")
        self.boundary.append((name, value))

    def cursor(self, **_: object) -> _FakeCursor:
        return _FakeCursor(self.cursor_error, self.executed)

    def transaction(self) -> _FakeTxn:
        self.begins += 1
        return _FakeTxn(self)

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self.pipeline_events)

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self) -> None:
        self.closed = True


def _direct_execution(connection: _FakeConnection) -> PostgresConnection:
    """The scoped execution an acquisition of ``connection`` would yield.

    Initialization is applied first, exactly as a runtime applies it to every
    physical connection before anything may use it.
    """
    native = cast("psycopg.Connection[TupleRow]", connection)
    initialize_connection(native)
    return PostgresConnection(native)


def _sent_sql(connection: _FakeConnection) -> list[str]:
    """The statements the adapter handed the driver, as the driver would render them."""
    return [
        statement.as_string()
        if isinstance(statement, Composable)
        else cast("bytes", statement).decode()
        for statement in connection.executed
    ]


def test_adapter_registers_boundary_value_adapters() -> None:
    # A `real` decodes exactly and native `timestamptz` infinity normalizes to
    # the m-core sentinel through the compiled loaders psycopg's implementation
    # runs, documents decode through the adapter's own JSON loaders, and the
    # sentinel binds through the adapter's own dumper.
    connection = _FakeConnection()
    _direct_execution(connection)
    loaders = compiled_loaders(psycopg.pq.__impl__)
    assert connection.adapters.registered == [
        ("float4", loaders.float4),
        ("timestamptz", loaders.timestamptz),
        ("jsonb", connection_module._DocumentJsonbLoader),  # pyright: ignore[reportPrivateUsage] - the registered loader is this test's subject
        ("jsonb", connection_module._DocumentJsonbBinaryLoader),  # pyright: ignore[reportPrivateUsage] - the registered loader is this test's subject
        (TemporalBound, connection_module._NativeInfinityDumper),  # pyright: ignore[reportPrivateUsage] - the registered dumper is this test's subject
        (connection_module._Int8Array, connection_module._Int8ArrayBinaryDumper),  # pyright: ignore[reportPrivateUsage] - the registered dumper is this test's subject
    ]


def _dumped(adapters: AdaptersMap, bind: object) -> tuple[bytes | None, int, Format]:
    """What a statement sends for ``bind`` under ``adapters``: its bytes, its
    parameter type OID, and its format."""
    transformer = Transformer(adapters)
    (dumped,) = transformer.dump_sequence(adapt_binds([bind]), [PyFormat.AUTO])
    assert transformer.types is not None
    assert transformer.formats is not None
    ((oid,), (format_,)) = (transformer.types, transformer.formats)
    return (None if dumped is None else bytes(dumped), oid, format_)


def test_the_open_bound_binds_exactly_as_its_string_spelling_does() -> None:
    # Untyped text, so the server infers the parameter's type from the
    # statement around it, as it does for the spelling.
    connection = _FakeConnection()
    _direct_execution(connection)

    assert _dumped(connection.adapters, INFINITY) == (b"infinity", 0, Format.TEXT)
    assert _dumped(connection.adapters, "infinity") == _dumped(connection.adapters, INFINITY)


def test_the_open_bound_dumper_is_registered_on_the_connection_alone() -> None:
    connection = _FakeConnection()
    _direct_execution(connection)
    dumper = connection_module._NativeInfinityDumper  # pyright: ignore[reportPrivateUsage] - the registered dumper is this test's subject

    assert connection.adapters.get_dumper(TemporalBound, PyFormat.AUTO) is dumper
    assert postgres.adapters.get_dumper(TemporalBound, PyFormat.AUTO) is not dumper
    assert AdaptersMap(postgres.adapters).get_dumper(TemporalBound, PyFormat.AUTO) is not dumper


def _int8_array(values: Sequence[int]) -> bytes:
    """The binary ``int8[]`` wire form of a one-dimensional array without nulls."""
    head = struct.pack("!IIIII", 1, 0, 20, len(values), 1)
    return head + b"".join(struct.pack("!iq", 8, value) for value in values)


@pytest.mark.parametrize(
    "values",
    [
        pytest.param([7], id="one"),
        pytest.param([1, 2, 42], id="small"),
        pytest.param([-1, 0, 2**31, -(2**31) - 1], id="negative-and-beyond-int32"),
        pytest.param([-(2**63), 2**63 - 1], id="int8-bounds"),
    ],
)
def test_an_integer_list_binds_as_one_binary_int8_array_whatever_its_magnitudes(
    values: list[int],
) -> None:
    connection = _FakeConnection()
    _direct_execution(connection)

    (adapted,) = adapt_binds([values])
    assert type(adapted) is connection_module._Int8Array  # pyright: ignore[reportPrivateUsage] - the bound carrier is this test's subject
    assert adapted == values
    assert adapted is not values
    assert _dumped(connection.adapters, values) == (_int8_array(values), 1016, Format.BINARY)


@pytest.mark.parametrize(
    "bind",
    [
        pytest.param([True, False], id="bool-list"),
        pytest.param([1.5, 2.0], id="float-list"),
        pytest.param([decimal.Decimal(1)], id="decimal-list"),
        pytest.param(["1", "2"], id="string-list"),
        pytest.param([], id="empty-list"),
        pytest.param((1, 2), id="int-tuple"),
        pytest.param(1, id="int"),
        pytest.param(True, id="bool"),
        pytest.param(None, id="null"),
    ],
)
def test_every_other_bind_passes_through_bind_adaptation_unchanged(bind: object) -> None:
    (adapted,) = adapt_binds([bind])
    assert adapted is bind


@pytest.mark.parametrize(
    ("values", "refusal"),
    [
        pytest.param([1, True], TypeError, id="bool"),
        pytest.param([1, None], TypeError, id="null"),
        pytest.param([1, 2.0], TypeError, id="float"),
        pytest.param([1, decimal.Decimal(2)], TypeError, id="decimal"),
        pytest.param([1, "2"], TypeError, id="string"),
        pytest.param([1, _IntSubclass(2)], TypeError, id="int-subclass"),
        pytest.param([1, 2**63], ValueError, id="above-int8"),
        pytest.param([-(2**63) - 1, 1], ValueError, id="below-int8"),
    ],
)
def test_an_integer_list_refuses_an_element_it_cannot_bind_as_int8(
    values: list[object], refusal: type[Exception]
) -> None:
    with pytest.raises(refusal, match="integer array bind"):
        adapt_binds([values])


def test_the_integer_array_dumper_is_registered_on_the_connection_alone() -> None:
    connection = _FakeConnection()
    _direct_execution(connection)
    carrier = connection_module._Int8Array  # pyright: ignore[reportPrivateUsage] - the bound carrier is this test's subject
    dumper = connection_module._Int8ArrayBinaryDumper  # pyright: ignore[reportPrivateUsage] - the registered dumper is this test's subject

    assert connection.adapters.get_dumper(carrier, PyFormat.AUTO) is dumper
    assert postgres.adapters.get_dumper(carrier, PyFormat.AUTO) is not dumper
    assert AdaptersMap(postgres.adapters).get_dumper(carrier, PyFormat.AUTO) is not dumper


@pytest.mark.parametrize(
    ("loader", "prefix"),
    [
        (connection_module._DocumentJsonbLoader, b""),  # pyright: ignore[reportPrivateUsage] - the registered loader is this test's subject
        (connection_module._DocumentJsonbBinaryLoader, b"\x01"),  # pyright: ignore[reportPrivateUsage] - the registered loader is this test's subject
    ],
)
def test_jsonb_loaders_decode_strictly_and_return_json_null_as_none(
    loader: type[JsonbLoader], prefix: bytes
) -> None:
    load = loader(3802).load

    assert load(prefix + b"null") is None
    document = cast("dict[str, object]", load(prefix + b'{"inexact": 0.1, "wide": 1e999}'))
    assert authored_token(cast("float", document["inexact"])) == "0.1"
    assert authored_token(cast("float", document["wide"])) == "1e999"
    with pytest.raises(json.JSONDecodeError, match="duplicate object member name 'x'"):
        load(prefix + b'{"x": 1, "x": 2}')
    with pytest.raises(json.JSONDecodeError, match="invalid JSON numeric constant 'NaN'"):
        load(prefix + b'{"x": NaN}')


def test_jsonb_loaders_accept_driver_buffers_without_retaining_member_names() -> None:
    text = connection_module._DocumentJsonbLoader(3802)  # pyright: ignore[reportPrivateUsage]
    binary = connection_module._DocumentJsonbBinaryLoader(3802)  # pyright: ignore[reportPrivateUsage]

    text_first = cast("dict[str, object]", text.load(memoryview(b'{"shared":1}')))
    text_second = cast("dict[str, object]", text.load(memoryview(b'{"shared":2}')))
    binary_first = cast("dict[str, object]", binary.load(memoryview(b'\x01{"shared":1}')))
    binary_second = cast("dict[str, object]", binary.load(memoryview(b'\x01{"shared":2}')))

    assert text_first == {"shared": 1}
    assert text_second == {"shared": 2}
    assert binary_first == {"shared": 1}
    assert binary_second == {"shared": 2}
    assert not hasattr(text, "_names")
    assert not hasattr(binary, "_names")
    with pytest.raises(psycopg.DataError, match="unknown jsonb binary format"):
        binary.load(b"\x02{}")


class _Result:
    """One statement's result as the driver holds it: its width and loaded records."""

    def __init__(self, width: int, records: list[tuple[object, ...]]) -> None:
        self.width = width
        self.records = records


class _ResultCursor(_FakeCursor):
    """A cursor honoring psycopg's row-factory protocol.

    The row factory is asked for a row maker when a result attaches — inside
    ``execute``, or at pipeline sync — and ``fetchall`` builds every row through
    that maker. A cursor left on the connection's ``tuple_row`` answers the
    driver's own record list.
    """

    def __init__(
        self,
        connection: _ResultConnection,
        result: _Result | None,
        row_factory: Callable[[object], Callable[[tuple[object, ...]], object]] | None,
    ) -> None:
        super().__init__(None, [])
        self._connection = connection
        self._ordinal = len(connection.result_cursors)
        self._result = result
        self._row_factory = row_factory
        self._make_row: Callable[[tuple[object, ...]], object] | None = None
        self.row_factory_kind = "folding" if row_factory is not None else "default"

    def _event(self, name: str) -> None:
        self._connection.pipeline_events.append(f"cursor-{self._ordinal}-{name}")

    def __enter__(self) -> _ResultCursor:
        self._event("enter")
        return self

    def __exit__(self, *_: object) -> bool:
        self._event("exit")
        return False

    def execute(
        self, sql: bytes | Composable, binds: object = None, *, prepare: bool | None = None
    ) -> None:
        del prepare
        self._event(f"execute:{sql!r}:{binds!r}")
        if self._connection.in_pipeline:
            self._connection.unsynced.append(self)
        else:
            self.attach()

    def attach(self) -> None:
        result = self._result
        self.description = (
            None
            if result is None
            else tuple(SimpleNamespace(name=f"c{index}") for index in range(result.width))
        )
        self._event("attach")
        if self._row_factory is not None:
            self._make_row = self._row_factory(self)

    def fetchall(self) -> list[tuple[object, ...]]:
        self._event("fetch")
        records = [] if self._result is None else self._result.records
        make_row = self._make_row
        if make_row is None:
            return records
        return [cast("tuple[object, ...]", make_row(record)) for record in records]


class _SyncingPipeline(_FakePipeline):
    def __init__(self, connection: _ResultConnection) -> None:
        super().__init__(connection.pipeline_events)
        self._connection = connection

    def __enter__(self) -> _SyncingPipeline:
        super().__enter__()
        self._connection.in_pipeline = True
        return self

    def __exit__(self, *_: object) -> bool:
        self._connection.in_pipeline = False
        for cursor in self._connection.unsynced:
            cursor.attach()
        self._connection.unsynced.clear()
        return super().__exit__()


class _ResultConnection(_FakeConnection):
    def __init__(self, *results: _Result | None) -> None:
        super().__init__()
        self._results = list(results)
        self.result_cursors: list[_ResultCursor] = []
        self.unsynced: list[_ResultCursor] = []
        self.in_pipeline = False

    def cursor(self, **options: object) -> _ResultCursor:
        row_factory = cast(
            "Callable[[object], Callable[[tuple[object, ...]], object]] | None",
            options.get("row_factory"),
        )
        cursor = _ResultCursor(self, self._results.pop(0), row_factory)
        self.result_cursors.append(cursor)
        return cursor

    def pipeline(self) -> _SyncingPipeline:
        return _SyncingPipeline(self)


def test_an_unpaired_result_is_the_drivers_own_row_list() -> None:
    records: list[tuple[object, ...]] = [(1, None), (2, {"kept": True})]
    connection = _ResultConnection(_Result(2, records))

    rows = _direct_execution(connection).execute("select id, document", [])

    assert rows is records
    assert connection.result_cursors[0].row_factory_kind == "default"


def test_a_paired_result_folds_sql_null_and_present_json_null_by_presence() -> None:
    connection = _ResultConnection(
        _Result(3, [(1, False, None), (2, True, None), (3, True, {"value": 1})])
    )

    rows = _direct_execution(connection).execute("select id, present, document", [], ((1, 2),))

    assert rows == [(1, SQL_NULL), (2, PresentDocument(None)), (3, PresentDocument({"value": 1}))]
    assert connection.result_cursors[0].row_factory_kind == "folding"


@pytest.mark.parametrize(
    ("document_reads", "record", "expected"),
    [
        ((), (7, None), (7, None)),
        (((0, 1),), (True, {"a": 1}, "tail"), (PresentDocument({"a": 1}), "tail")),
        (((2, 3),), ("head", 7, False, None), ("head", 7, SQL_NULL)),
        (
            ((1, 2), (4, 5)),
            (7, True, {"value": 1}, "kept", False, None),
            (7, PresentDocument({"value": 1}), "kept", SQL_NULL),
        ),
        (
            ((4, 5), (1, 2)),
            (7, True, {"value": 1}, "kept", True, None),
            (7, PresentDocument({"value": 1}), "kept", PresentDocument(None)),
        ),
    ],
    ids=["no-pairs", "leading-pair", "trailing-pair", "two-pairs", "unordered-pairs"],
)
def test_paired_rows_are_built_directly_in_their_final_shape(
    document_reads: tuple[tuple[int, int], ...],
    record: tuple[object, ...],
    expected: tuple[object, ...],
) -> None:
    connection = _ResultConnection(_Result(len(record), [record]))
    assert _direct_execution(connection).execute("select", [], document_reads) == [expected]


@pytest.mark.parametrize(
    ("width", "document_reads", "message"),
    [
        (3, ((0, 2),), "adjacent, zero-based"),
        (3, ((-1, 0),), "adjacent, zero-based"),
        (3, ((1, 3),), "adjacent, zero-based"),
        (3, ((0, 1), (1, 2)), "must not overlap"),
    ],
    ids=["non-adjacent", "negative", "outside-the-projection", "overlapping"],
)
def test_malformed_pair_metadata_is_judged_at_attachment_and_refused_at_fetch(
    width: int, document_reads: tuple[tuple[int, int], ...], message: str
) -> None:
    connection = _ResultConnection(_Result(width, [(True,) * width]))

    with pytest.raises(ValueError, match=message):
        _direct_execution(connection).execute("select", [], document_reads)

    assert connection.pipeline_events == [
        "cursor-0-enter",
        "cursor-0-execute:b'select':[]",
        "cursor-0-attach",
        "cursor-0-exit",
    ]


def test_malformed_pair_metadata_in_a_pipeline_is_refused_after_every_result_syncs() -> None:
    connection = _ResultConnection(_Result(3, []), _Result(1, [(1,)]))

    with pytest.raises(ValueError, match="adjacent, zero-based"):
        _direct_execution(connection).execute_pipeline(
            (
                PipelineStatement("select malformed", document_reads=((0, 2),)),
                PipelineStatement("select 1"),
            )
        )

    assert connection.pipeline_events == [
        "pipeline-enter",
        "cursor-0-enter",
        "cursor-0-execute:b'select malformed':[]",
        "cursor-1-enter",
        "cursor-1-execute:b'select 1':[]",
        "cursor-0-attach",
        "cursor-1-attach",
        "pipeline-exit",
        "cursor-1-exit",
        "cursor-0-exit",
    ]


def test_a_paired_row_whose_width_disagrees_with_its_description_is_refused() -> None:
    connection = _ResultConnection(_Result(3, [(1, True)]))
    with pytest.raises(ValueError, match="does not match its result description"):
        _direct_execution(connection).execute("select", [], ((1, 2),))


@pytest.mark.parametrize("document_reads", [(), ((0, 1),)], ids=["unpaired", "paired"])
def test_a_result_without_a_description_yields_no_rows_and_is_not_fetched(
    document_reads: tuple[tuple[int, int], ...],
) -> None:
    connection = _ResultConnection(None)

    assert _direct_execution(connection).execute("set local x = 1", [], document_reads) == []
    assert "cursor-0-fetch" not in connection.pipeline_events


def test_execute_pipeline_owns_one_cursor_per_statement_and_fetches_after_sync() -> None:
    records: list[tuple[object, ...]] = [(1,), (2,)]
    connection = _ResultConnection(_Result(1, records), _Result(2, [(False, None), (True, None)]))
    rows = _direct_execution(connection).execute_pipeline(
        (
            PipelineStatement("select unnest(%s::bigint[])", ([1, 2],)),
            PipelineStatement("select present, document", document_reads=((0, 1),)),
        )
    )

    assert rows == [[(1,), (2,)], [(SQL_NULL,), (PresentDocument(None),)]]
    assert rows[0] is records
    assert connection.pipeline_events == [
        "pipeline-enter",
        "cursor-0-enter",
        "cursor-0-execute:b'select unnest(%s::bigint[])':[[1, 2]]",
        "cursor-1-enter",
        "cursor-1-execute:b'select present, document':[]",
        "cursor-0-attach",
        "cursor-1-attach",
        "pipeline-exit",
        "cursor-0-fetch",
        "cursor-1-fetch",
        "cursor-1-exit",
        "cursor-0-exit",
    ]


def test_execute_and_execute_pipeline_return_the_same_rows_for_the_same_result() -> None:
    def result() -> _Result:
        return _Result(3, [(1, False, None), (2, True, None), (3, True, {"a": 1})])

    ordinary = _direct_execution(_ResultConnection(result())).execute("select", [], ((1, 2),))
    (pipelined,) = _direct_execution(_ResultConnection(result())).execute_pipeline(
        (PipelineStatement("select", document_reads=((1, 2),)),)
    )

    assert pipelined == ordinary


def test_a_designated_read_submits_and_answers_exactly_what_an_undesignated_one_does() -> None:
    def result() -> _Result:
        return _Result(3, [(1, False, None), (2, True, {"a": 1})])

    def submitted(read_only: bool) -> tuple[object, list[str]]:
        single = _ResultConnection(result())
        batch = _ResultConnection(result(), result())
        rows = (
            _direct_execution(single).execute("select", [7], ((1, 2),), read_only=read_only),
            _direct_execution(batch).execute_pipeline(
                (
                    PipelineStatement("select", (7,), ((1, 2),)),
                    PipelineStatement("select", (8,), ((1, 2),)),
                ),
                read_only=read_only,
            ),
        )
        return rows, single.pipeline_events + batch.pipeline_events

    assert submitted(read_only=True) == submitted(read_only=False)


def test_execute_pipeline_returns_an_empty_result_for_a_statement_without_rows() -> None:
    assert _direct_execution(_ResultConnection(None)).execute_pipeline(
        (PipelineStatement("set local application_name = 'parallax'"),)
    ) == [[]]


def test_execute_reraises_a_driver_error_at_the_boundary() -> None:
    adapter = _direct_execution(_FakeConnection(cursor_error=errors.UniqueViolation("dup")))
    with pytest.raises(DatabaseError) as exc_info:
        adapter.execute("select 1", [])
    assert exc_info.value.violates_unique_index
    assert exc_info.value.native_code == "23505"


def test_the_adapter_reads_pipeline_availability_from_the_libpq_psycopg_loaded() -> None:
    assert connection_module._PIPELINED is psycopg.capabilities.has_pipeline()  # pyright: ignore[reportPrivateUsage] - the availability the facade selects on


@pytest.mark.parametrize("pipelined", [True, False], ids=["pipeline", "no-pipeline"])
def test_a_scope_holds_its_ordered_write_operation_exactly_where_libpq_can_pipeline(
    monkeypatch: pytest.MonkeyPatch, pipelined: bool
) -> None:
    monkeypatch.setattr(connection_module, "_PIPELINED", pipelined)
    facade = _direct_execution(_FakeConnection())
    transport = facade.ordered_write_transport
    if not pipelined:
        assert transport is None
        return
    # Stored once: every read answers the same operation of this scope.
    assert transport is not None
    assert transport is facade.ordered_write_transport
    assert transport == facade._ordered_writes  # pyright: ignore[reportPrivateUsage] - the scope's own operation


def test_execute_write_reraises_a_driver_error_at_the_boundary() -> None:
    adapter = _direct_execution(_FakeConnection(cursor_error=errors.DeadlockDetected("deadlock")))
    with pytest.raises(DatabaseError) as exc_info:
        adapter.execute_write("update gauge set v = %s", [1])
    assert exc_info.value.category == "deadlock"
    assert exc_info.value.native_code == "40P01"


# --------------------------------------------------------------------------- #
# The ordered write operation, over a real psycopg connection whose libpq      #
# session is scripted. The live proofs are test_postgres_ordered_writes.py's.  #
# --------------------------------------------------------------------------- #

_WRITES = (
    Statement("update a set v = 1"),
    Statement("update b set v = 2"),
    Statement("delete from c"),
)


def _ordered_writes(
    facade: PostgresConnection, statements: Sequence[CanonicalWriteStatement] = _WRITES
) -> OrderedWriteResult:
    return facade._ordered_writes(statements)  # pyright: ignore[reportPrivateUsage] - the operation is qualified here before the facade advertises it


def _written(
    monkeypatch: pytest.MonkeyPatch,
    server: Server,
    statements: Sequence[CanonicalWriteStatement] = _WRITES,
) -> tuple[OrderedWriteResult, PostgresConnection]:
    with native_session(monkeypatch, server) as native:
        facade = PostgresConnection(native)
        return _ordered_writes(facade, statements), facade


def _raising(error: type[BaseException], message: str, at: int) -> Callable[[int], None]:
    def hook(call: int) -> None:
        if call == at:
            raise error(message)

    return hook


def test_ordered_writes_answer_each_statement_its_own_count_in_presentation_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Canonical SQL is converted once: a literal `%` crosses doubled for the
    # driver's parameter style, which a bare `%` would break.
    statements = (
        Statement("update \"rate%\" set v = 1 where k = '?'"),
        Statement("update b set v = 2"),
        Statement("delete from c"),
    )
    server = Server(script([counted(1)], [counted(0)], [counted(3)]))

    result, facade = _written(monkeypatch, server, statements)

    assert result == OrderedWriteResultComplete((1, 0, 3))
    assert server.sent == [
        b"update \"rate%\" set v = 1 where k = '?'",
        b"update b set v = 2",
        b"delete from c",
        "sync",
    ]
    assert server.pipeline_status == 0
    assert not facade.suspect


def test_counts_handed_over_while_later_statements_queue_stay_with_their_statements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(script([counted(2)], [counted(0)], [counted(1)]))
    server.early = True

    result, _facade = _written(monkeypatch, server)

    assert result == OrderedWriteResultComplete((2, 0, 1))
    assert server.handed_early == 4


def test_a_statement_error_is_its_own_failure_and_confirms_what_it_kept_from_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def answer() -> Callable[[bytes], list[Result]]:
        return script([counted(1)], [failed("23505", "duplicate key", constraint="coverage_pkey")])

    statements = (*_WRITES, Statement("delete from d"))
    first, facade = _written(monkeypatch, Server(answer()), statements)
    second, _ = _written(monkeypatch, Server(answer()), statements)

    assert isinstance(first, OrderedWriteResultComplete)
    count, failure, *skipped = first.outcomes
    assert count == 1
    assert skipped == [StatementNotExecuted(), StatementNotExecuted()]
    assert isinstance(failure, StatementFailed)
    error = failure.error
    assert isinstance(error, DatabaseError)
    assert (error.category, error.native_code, error.message) == (
        "uniqueViolation",
        "23505",
        "duplicate key",
    )
    assert error.violated_index == PhysicalIndexName("coverage_pkey")
    assert isinstance(error.__cause__, errors.UniqueViolation)
    assert error.__traceback__ is None
    assert error.__cause__.__traceback__ is None
    assert isinstance(second, OrderedWriteResultComplete)
    repeated = second.outcomes[1]
    assert isinstance(repeated, StatementFailed)
    assert repeated.error is not error
    assert not facade.suspect


def _reaches(root: object, target: object) -> bool:
    """Whether ``target`` is reachable from ``root`` through object references,
    short of classes, modules, functions, and frames (a frame would arrive only
    through a traceback, which is asserted on directly)."""
    opaque = (type, ModuleType, FunctionType, FrameType)
    seen: set[int] = set()
    pending = [root]
    while pending:
        item = pending.pop()
        if item is target:
            return True
        if id(item) in seen or isinstance(item, opaque):
            continue
        seen.add(id(item))
        pending.extend(gc.get_referents(item))
    return False


def test_a_statement_failure_keeps_neither_its_connection_nor_its_statements_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(script([failed("23505", "duplicate key")]))
    with native_session(monkeypatch, server) as native:
        result = _ordered_writes(PostgresConnection(native))

        assert isinstance(result, OrderedWriteResultComplete)
        failure = result.outcomes[0]
        assert isinstance(failure, StatementFailed)
        assert failure.error.__context__ is None
        assert not _reaches(failure.error, native)
        assert not any(_reaches(failure.error, statement) for statement in _WRITES)


@pytest.mark.parametrize(
    ("answered", "native_code"),
    [
        (
            [failed("57P01", "terminating connection", severity=b"FATAL")],
            "57P01",
        ),
        ([unowned("server closed the connection unexpectedly")], None),
        ([failed("23505", "duplicate key"), unowned("server closed the connection")], "23505"),
    ],
    ids=["session-ending", "raised-by-libpq", "beside-another-result"],
)
def test_a_failure_its_statement_did_not_cause_interrupts_rather_than_failing_it(
    monkeypatch: pytest.MonkeyPatch, answered: list[Result], native_code: str | None
) -> None:
    result, facade = _written(monkeypatch, Server(script([counted(1)], answered)))

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((1,), 2, 0)
    assert isinstance(result.error, DatabaseError)
    assert result.error.native_code == native_code
    assert facade.suspect


@pytest.mark.parametrize(
    ("answered", "description"),
    [
        ([Result(ExecStatus.TUPLES_OK)], "result status TUPLES_OK"),
        ([Result(ExecStatus.COMMAND_OK)], "no affected-row count"),
        ([counted(1), counted(1)], "2 results"),
        ([Result(99)], "result status 99"),
    ],
    ids=["rows", "uncounted", "two-results", "unknown-status"],
)
def test_a_result_no_count_only_statement_produces_is_an_integrity_failure(
    monkeypatch: pytest.MonkeyPatch, answered: list[Result], description: str
) -> None:
    server = Server(script([counted(1)], answered, [counted(1)]))
    with native_session(monkeypatch, server) as native:
        facade = PostgresConnection(native)
        with pytest.raises(OrderedWriteResultIntegrityError) as refused:
            _ordered_writes(facade)

    message = str(refused.value)
    assert f"statement 1 of an ordered write with {description}," in message
    assert "update" not in message
    assert facade.suspect


def test_results_collected_by_an_exit_that_failed_are_left_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server()
    server.on_fetch = _raising(psycopg.OperationalError, "consuming input failed", at=2)

    result, facade = _written(monkeypatch, server)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((), 3, 0)
    assert isinstance(result.error, DatabaseError)
    assert result.error.native_code is None
    assert isinstance(result.error.__cause__, psycopg.OperationalError)
    assert facade.suspect


def test_results_collected_while_queueing_survive_an_exit_that_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(script([counted(1)], [counted(0)], [counted(1)]))
    server.early = True
    server.on_communicate = _raising(psycopg.OperationalError, "sending sync failed", at=4)

    result, facade = _written(monkeypatch, server)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((1, 0, 1), 0, 0)
    assert facade.suspect


def test_results_arriving_after_a_driver_call_failed_are_never_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The failed read dropped the first statement's answer, so what psycopg
    # pairs with that statement afterwards belongs to something else.
    server = Server()

    def lose(call: int) -> None:
        if call == 2:
            server.lose("consuming input failed")

    server.on_communicate = lose

    result, facade = _written(monkeypatch, server)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((), 2, 1)
    assert server.sent == [b"update a set v = 1", b"update b set v = 2", "sync"]
    assert facade.suspect


class _Unrenderable:
    @property
    def sql(self) -> str:
        raise ValueError("no canonical text")

    @property
    def binds(self) -> Sequence[object]:
        return ()


def test_statements_never_handed_to_the_driver_are_the_unsent_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = (_WRITES[0], _Unrenderable(), _WRITES[1])

    result, facade = _written(monkeypatch, Server(), statements)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((), 1, 2)
    assert isinstance(result.error, ValueError)
    assert facade.suspect


def test_a_statement_the_driver_refused_to_send_is_unconfirmed_and_the_rest_unsent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server()
    server.refuse = lambda query: query == b"update b set v = 2"

    result, _facade = _written(monkeypatch, server)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((), 2, 1)
    assert isinstance(result.error, DatabaseError)
    assert isinstance(result.error.__cause__, psycopg.OperationalError)


def _owing_deallocation(native: psycopg.Connection[TupleRow]) -> None:
    native._prepared._to_flush.append(b"_pg3_0")  # pyright: ignore[reportPrivateUsage] - the deallocation a pipeline's own eviction leaves owed


def _deallocation() -> object:
    return (
        ("close", b"_pg3_0")
        if psycopg.capabilities.has_send_close_prepared()
        else b"DEALLOCATE _pg3_0"
    )


def test_prepared_cache_maintenance_between_statements_answers_none_of_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server()
    with native_session(monkeypatch, server) as native:
        _owing_deallocation(native)
        result = _ordered_writes(PostgresConnection(native))

    assert result == OrderedWriteResultComplete((1, 1, 1))
    assert server.sent == [
        b"update a set v = 1",
        _deallocation(),
        b"update b set v = 2",
        b"delete from c",
        "sync",
    ]


def test_failed_prepared_cache_maintenance_interrupts_without_blaming_a_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(script([failed("23505", "duplicate key")]))
    with native_session(monkeypatch, server) as native:
        _owing_deallocation(native)
        facade = PostgresConnection(native)
        result = _ordered_writes(facade)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((), 3, 0)
    assert isinstance(result.error, DatabaseError)
    assert isinstance(result.error.__cause__, errors.PipelineAborted)
    assert facade.suspect


def test_an_abort_no_confirmed_failure_explains_ends_what_is_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, facade = _written(monkeypatch, Server(script([counted(1)], [aborted()], [counted(1)])))

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((1,), 2, 0)
    assert isinstance(result.error, DatabaseError)
    assert (result.error.category, result.error.native_code) == (None, None)
    assert "before answering every statement" in result.error.message
    assert facade.suspect


def test_answers_that_stop_arriving_leave_the_rest_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server()

    def vanish(call: int) -> None:
        if call == 2:
            server.answers.clear()

    server.on_fetch = vanish

    result, facade = _written(monkeypatch, server)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((1,), 2, 0)
    assert facade.suspect


@pytest.mark.parametrize("phase", ["queueing", "exit"])
def test_control_flow_propagates_as_itself_and_leaves_the_scope_suspect(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    server = Server()
    if phase == "queueing":
        server.on_communicate = _raising(KeyboardInterrupt, "", at=2)
    else:
        server.on_fetch = _raising(KeyboardInterrupt, "", at=1)
    with native_session(monkeypatch, server) as native:
        facade = PostgresConnection(native)
        with pytest.raises(KeyboardInterrupt):
            _ordered_writes(facade)

    assert facade.suspect
    assert server.pipeline_status == 0


@pytest.mark.parametrize("phase", ["queueing", "exit"])
@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_an_interrupt_psycopg_cancels_propagates_past_failed_maintenance_behind_it(
    monkeypatch: pytest.MonkeyPatch, phase: str, interrupt: type[BaseException]
) -> None:
    # The statement is blocked when the interrupt arrives. Psycopg cancels it
    # and collects what remains; the deallocation queued behind it is aborted,
    # and that abort is what psycopg raises in the interrupt's place.
    server = Server(script([failed("57014", "canceling statement due to user request")]))
    raised = interrupt()

    def interrupt_once() -> None:
        server.on_wait = lambda: None
        raise raised

    def block(call: int) -> None:
        if call == 2:
            server.early = True
            server.held = True

    if phase == "queueing":
        server.on_communicate = block
    else:
        server.held = True
    server.on_wait = interrupt_once
    with native_session(monkeypatch, server) as native:
        _owing_deallocation(native)
        server.transaction_status = TransactionStatus.ACTIVE
        facade = PostgresConnection(native)
        with pytest.raises(interrupt) as propagated:
            _ordered_writes(facade)
        server.transaction_status = TransactionStatus.IDLE

    assert propagated.value is raised
    assert propagated.value.__context__ is None
    assert facade.suspect


def test_an_interrupt_already_being_handled_is_not_the_writes_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server(script([failed("23505", "duplicate key")]))
    with native_session(monkeypatch, server) as native:
        _owing_deallocation(native)
        facade = PostgresConnection(native)
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            result = _ordered_writes(facade)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert isinstance(result.error, DatabaseError)
    assert isinstance(result.error.__cause__, errors.PipelineAborted)
    assert facade.suspect


def test_a_connection_that_cannot_open_a_pipeline_sends_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server()
    with native_session(monkeypatch, server) as native:
        facade = PostgresConnection(native)
        server.finish()
        result = _ordered_writes(facade)

    assert isinstance(result, OrderedWriteResultInterrupted)
    assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == ((), 0, 3)
    assert server.sent == []
    assert facade.suspect


def test_a_saved_ordered_write_operation_runs_nothing_once_its_scope_is_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = Server()
    with native_session(monkeypatch, server) as native:
        facade = PostgresConnection(native)
        saved = facade._ordered_writes  # pyright: ignore[reportPrivateUsage] - a reference kept past its scope
        facade.revoke()
        with pytest.raises(RuntimeError, match="scope has ended"):
            saved(_WRITES)

    assert server.sent == []


class _BodyFailure(Exception):
    """A transaction body's own error — what makes the boundary roll back."""


def _translated(error: Exception) -> DatabaseError:
    """The neutral error a boundary outcome carries, which every failure the port
    itself makes must already be (`m-db-error` translation boundary)."""
    assert isinstance(error, DatabaseError)
    return error


def test_every_failed_port_invocation_reports_its_own_error_instance() -> None:
    # m-db-port failure identity, over every error the port itself makes: a
    # statement failure raised by `execute`, one raised by `execute_write`, and
    # each failure of the boundary `transaction` owns -- its begin, its commit,
    # and its rollback, all three of which the adapter classifies where they
    # occur. The driver here hands back ONE reused exception object for all of
    # them -- the input the rule exists to stop an adapter passing on -- so
    # distinctness can only come from classifying at the failing call. Driving
    # every site over one adapter also rules out reuse ACROSS paths, which a
    # per-path cache would produce while each path alone looked clean. This is
    # what lets a caller (an activity attributing its own failure) tell which
    # invocation the error it holds came from.
    driver_error = errors.UniqueViolation("dup")
    connection = _FakeConnection(cursor_error=driver_error, commit_error=driver_error)
    adapter = _direct_execution(connection)

    def raised(invoke: Callable[[], object]) -> DatabaseError:
        with pytest.raises(DatabaseError) as exc_info:
            invoke()
        return exc_info.value

    def failing_begin() -> DatabaseError:
        # Scoped to this invocation: a boundary that never begins reaches
        # neither the commit nor the rollback site below.
        connection.begin_error = driver_error
        try:
            outcome = adapter.transaction(lambda _port: None)
        finally:
            connection.begin_error = None
        assert isinstance(outcome, BeginFailed)
        return _translated(outcome.error)

    def failing_commit() -> DatabaseError:
        outcome = adapter.transaction(lambda _port: None)
        assert isinstance(outcome, RolledBack)
        trigger = outcome.trigger
        assert isinstance(trigger, CommitFailed)
        return _translated(trigger.error)

    def failing_rollback() -> DatabaseError:
        def body(_port: object) -> None:
            raise _BodyFailure

        connection.rollback_error = driver_error
        try:
            outcome = adapter.transaction(body)
        finally:
            connection.rollback_error = None
        assert isinstance(outcome, RollbackFailed)
        return _translated(outcome.rollback_error)

    invocations: tuple[Callable[[], DatabaseError], ...] = (
        lambda: raised(lambda: adapter.execute("select 1", [])),
        lambda: raised(lambda: adapter.execute_pipeline((PipelineStatement("select 1"),))),
        lambda: raised(lambda: adapter.execute_write("insert into gauge (v) values (%s)", [1])),
        failing_begin,
        failing_commit,
        failing_rollback,
    )
    reported = [invoke() for invoke in (*invocations, *invocations)]

    assert len({id(error) for error in reported}) == len(reported)
    assert {(error.category, error.native_code, error.message) for error in reported} == {
        ("uniqueViolation", "23505", "dup")
    }


def test_transaction_commits_and_reports_the_body_value() -> None:
    assert _direct_execution(_FakeConnection()).transaction(lambda _port: "kept") == Committed(
        "kept"
    )


def test_the_transaction_scoped_port_reports_the_boundarys_own_dialect() -> None:
    # The port a body holds spells the statements that boundary is about to run,
    # so it answers the dialect of the port that opened the boundary rather than
    # resolving one of its own.
    outcome = _direct_execution(_FakeConnection()).transaction(lambda port: port.dialect)
    assert outcome == Committed(PostgresAdapter.dialect)


def test_transaction_reports_a_boundary_that_never_began() -> None:
    # No attempt ran, so there is nothing to undo and nothing to re-execute; the
    # body is what proves it, by never running. The driver counted the context
    # it could not enter as open, so the session is left suspect for disposal
    # rather than reset.
    connection = _FakeConnection(begin_error=errors.OperationalError("the connection is closed"))
    execution = _direct_execution(connection)
    ran: list[str] = []
    outcome = execution.transaction(lambda _port: ran.append("body"))
    assert isinstance(outcome, BeginFailed)
    assert _translated(outcome.error).category is None
    assert ran == []
    assert connection.rollbacks == 0
    assert execution.suspect
    assert connection.boundary == [
        ("isolation_level", None),
        ("read_only", None),
        ("BEGIN", None, None),
    ]


_DRIVER_LEVELS: dict[str, psycopg.IsolationLevel] = {
    "read_committed": psycopg.IsolationLevel.READ_COMMITTED,
    "repeatable_read": psycopg.IsolationLevel.REPEATABLE_READ,
    "serializable": psycopg.IsolationLevel.SERIALIZABLE,
}

_CLEARED: list[object] = [("isolation_level", None), ("read_only", None)]


@pytest.mark.parametrize("access_mode", [None, "read_only", "read_write"])
@pytest.mark.parametrize("isolation", [None, *sorted(ISOLATION_LEVELS)])
def test_each_request_travels_in_the_drivers_begin_and_is_cleared_after_it(
    isolation: str | None, access_mode: AccessMode | None
) -> None:
    # Every pair, including each request alone and neither, reaches the
    # attributes the driver composes its BEGIN from before the context is
    # entered, so the boundary sends no statement beyond the body's own; and the
    # outer boundary leaves both cleared, so the session's own defaults govern
    # the next one.
    connection = _FakeConnection()
    outcome = _direct_execution(connection).transaction(
        lambda port: port.execute("select 1", []),
        isolation=None if isolation is None else isolation_level(isolation),
        access_mode=access_mode,
    )
    level = None if isolation is None else _DRIVER_LEVELS[isolation]
    read_only = None if access_mode is None else access_mode == "read_only"
    assert outcome == Committed([])
    assert connection.boundary == [
        ("isolation_level", level),
        ("read_only", read_only),
        ("BEGIN", level, read_only),
        "COMMIT",
        *_CLEARED,
    ]
    assert _sent_sql(connection) == ["select 1"]


@pytest.mark.parametrize(
    "requested",
    [
        {"isolation": "snapshot"},
        {"access_mode": "read-write"},
        {"isolation": "serializable", "access_mode": "write"},
    ],
)
def test_a_request_outside_the_vocabulary_changes_nothing_and_opens_nothing(
    requested: dict[str, str],
) -> None:
    connection = _FakeConnection()
    ran: list[str] = []
    with pytest.raises(KeyError):
        _direct_execution(connection).transaction(
            lambda _port: ran.append("body"), **cast("dict[str, Any]", requested)
        )
    assert connection.boundary == []
    assert connection.begins == 0
    assert ran == []


@pytest.mark.parametrize(
    "requested",
    [{"isolation": "serializable"}, {"access_mode": "read_only"}],
)
def test_a_refused_begin_runs_no_callback_and_leaves_its_session_to_disposal(
    requested: dict[str, str],
) -> None:
    # The server refused the command and left the session idle, but the driver
    # still counts the context it could not enter: nothing resets the
    # characteristics of a session cleanup is about to dispose of, and nothing
    # sends a rollback to repair it.
    connection = _FakeConnection(begin_error=errors.SyntaxError("syntax error at or near"))
    execution = _direct_execution(connection)
    ran: list[str] = []
    outcome = execution.transaction(
        lambda _port: ran.append("body"), **cast("dict[str, Any]", requested)
    )
    assert isinstance(outcome, BeginFailed)
    assert _translated(outcome.error).native_code == "42601"
    assert ran == []
    assert execution.suspect
    assert connection.rollbacks == 0
    assert connection.pgconn.status == TransactionStatus.IDLE
    assert connection.boundary[-1] == ("BEGIN", connection.isolation_level, connection.read_only)
    assert not connection.closed


def test_a_failed_entry_that_is_no_driver_error_propagates_as_itself_and_leaves_it_suspect() -> (
    None
):
    stale = AssertionError()
    connection = _FakeConnection(begin_error=stale)
    execution = _direct_execution(connection)
    with pytest.raises(AssertionError) as raised:
        execution.transaction(lambda _port: None, isolation="serializable")
    assert raised.value is stale
    assert execution.suspect
    assert connection.boundary[-1] == ("BEGIN", psycopg.IsolationLevel.SERIALIZABLE, None)


def _refusing_resets(error: BaseException) -> Callable[[str, object], BaseException | None]:
    return lambda _name, value: error if value is None else None


def _commits(_port: object) -> str:
    return "kept"


def _raises(_port: object) -> None:
    raise _BodyFailure


@pytest.mark.parametrize(
    ("body", "commit_error", "ending", "expected"),
    [
        (_commits, None, "COMMIT", Committed),
        (_raises, None, "ROLLBACK", RolledBack),
        (_commits, errors.SerializationFailure("serialize"), "COMMIT", RolledBack),
    ],
    ids=["committed", "callback-rolled-back", "commit-rolled-back"],
)
def test_a_failed_reset_keeps_the_outcome_and_leaves_the_session_suspect(
    body: Callable[[object], object],
    commit_error: psycopg.Error | None,
    ending: str,
    expected: type[object],
) -> None:
    connection = _FakeConnection(commit_error=commit_error)
    connection.refuse_assignment = _refusing_resets(errors.OperationalError("reset refused"))
    execution = _direct_execution(connection)
    outcome = execution.transaction(body, isolation="serializable", access_mode="read_only")
    assert isinstance(outcome, expected)
    assert execution.suspect
    assert connection.boundary[-1] == ending


def test_a_rollback_failure_leaves_its_characteristics_to_disposal() -> None:
    attempted: list[tuple[str, object]] = []

    def record(name: str, value: object) -> None:
        attempted.append((name, value))

    connection = _FakeConnection(rollback_error=errors.OperationalError("the connection is lost"))
    connection.refuse_assignment = record
    execution = _direct_execution(connection)
    outcome = execution.transaction(_raises, isolation="serializable", access_mode="read_only")
    assert isinstance(outcome, RollbackFailed)
    assert execution.suspect
    assert attempted == [
        ("isolation_level", psycopg.IsolationLevel.SERIALIZABLE),
        ("read_only", True),
    ]


def test_a_fatal_reset_failure_propagates_and_leaves_the_session_suspect() -> None:
    interrupt = KeyboardInterrupt()
    connection = _FakeConnection()
    connection.refuse_assignment = _refusing_resets(interrupt)
    execution = _direct_execution(connection)
    with pytest.raises(KeyboardInterrupt) as raised:
        execution.transaction(_commits, isolation="serializable")
    assert raised.value is interrupt
    assert execution.suspect


def test_a_session_its_boundary_left_unsafe_is_not_reset() -> None:
    connection = _FakeConnection()
    connection.status_after_boundary = TransactionStatus.UNKNOWN
    execution = _direct_execution(connection)
    assert execution.transaction(_commits, isolation="serializable") == Committed("kept")
    assert execution.suspect
    assert connection.boundary[-1] == "COMMIT"


def test_a_session_whose_state_became_unreadable_is_not_reset() -> None:
    connection = _FakeConnection()
    execution = _direct_execution(connection)

    def body(_port: object) -> str:
        connection.pgconn.status_error = RuntimeError("the state is gone")
        return "kept"

    assert execution.transaction(body, access_mode="read_only") == Committed("kept")
    assert execution.suspect
    assert connection.boundary[-1] == "COMMIT"


def test_a_refused_assignment_opens_nothing_and_clears_what_it_assigned() -> None:
    # A refusal before entry says nothing about the driver's transaction
    # bookkeeping, so the session is not suspect; the characteristic already
    # assigned is cleared like any boundary's.
    connection = _FakeConnection()
    connection.refuse_assignment = lambda name, value: (
        errors.OperationalError("refused") if (name, value) == ("read_only", True) else None
    )
    execution = _direct_execution(connection)
    ran: list[str] = []
    outcome = execution.transaction(
        lambda _port: ran.append("body"), isolation="serializable", access_mode="read_only"
    )
    assert isinstance(outcome, BeginFailed)
    assert _translated(outcome.error).message == "refused"
    assert ran == []
    assert connection.begins == 0
    assert not execution.suspect
    assert connection.boundary == [
        ("isolation_level", psycopg.IsolationLevel.SERIALIZABLE),
        *_CLEARED,
    ]


def test_a_refused_assignment_whose_reset_fails_keeps_its_failure_and_is_suspect() -> None:
    connection = _FakeConnection()
    connection.refuse_assignment = lambda name, value: (
        errors.OperationalError(f"refused {name}") if value in (True, None) else None
    )
    execution = _direct_execution(connection)
    outcome = execution.transaction(
        lambda _port: None, isolation="serializable", access_mode="read_only"
    )
    assert isinstance(outcome, BeginFailed)
    assert _translated(outcome.error).message == "refused read_only"
    assert execution.suspect


def test_an_assignment_failure_that_is_no_driver_error_propagates_as_itself() -> None:
    refusal = ValueError("not a driver error")
    connection = _FakeConnection()
    connection.refuse_assignment = lambda name, value: (
        refusal if (name, value) == ("read_only", True) else None
    )
    execution = _direct_execution(connection)
    with pytest.raises(ValueError, match="not a driver error") as raised:
        execution.transaction(lambda _port: None, isolation="serializable", access_mode="read_only")
    assert raised.value is refusal
    assert connection.begins == 0
    assert not execution.suspect
    assert connection.boundary == [
        ("isolation_level", psycopg.IsolationLevel.SERIALIZABLE),
        *_CLEARED,
    ]


def test_a_nested_call_asking_for_nothing_joins_through_a_savepoint_untouched() -> None:
    connection = _FakeConnection()
    execution = _direct_execution(connection)
    joined: list[object] = []

    def body(port: DatabaseConnection) -> str:
        joined.append(port.transaction(lambda inner: inner.execute("select 1", [])))
        return "outer"

    outcome = execution.transaction(body, isolation="repeatable_read", access_mode="read_only")
    assert outcome == Committed("outer")
    assert joined == [Committed([])]
    assert not execution.suspect
    assert connection.boundary == [
        ("isolation_level", psycopg.IsolationLevel.REPEATABLE_READ),
        ("read_only", True),
        ("BEGIN", psycopg.IsolationLevel.REPEATABLE_READ, True),
        "SAVEPOINT",
        "RELEASE",
        "COMMIT",
        *_CLEARED,
    ]


@pytest.mark.parametrize("requested", [{"isolation": "serializable"}, {"access_mode": "read_only"}])
def test_a_nested_call_asking_for_a_characteristic_is_refused_before_its_savepoint(
    requested: dict[str, str],
) -> None:
    connection = _FakeConnection()
    execution = _direct_execution(connection)
    ran: list[str] = []
    refused: list[object] = []

    def body(port: DatabaseConnection) -> str:
        refused.append(
            port.transaction(
                lambda _inner: ran.append("inner"), **cast("dict[str, Any]", requested)
            )
        )
        return "outer"

    assert execution.transaction(body) == Committed("outer")
    (inner,) = refused
    assert isinstance(inner, BeginFailed)
    assert ran == []
    assert not execution.suspect
    assert connection.boundary == [*_CLEARED, ("BEGIN", None, None), "COMMIT", *_CLEARED]


def test_a_nested_call_whose_savepoint_fails_to_enter_leaves_the_session_suspect() -> None:
    connection = _FakeConnection()
    execution = _direct_execution(connection)
    refused: list[object] = []

    def body(port: DatabaseConnection) -> str:
        connection.begin_error = errors.OperationalError("savepoint refused")
        try:
            refused.append(port.transaction(lambda _inner: None))
        finally:
            connection.begin_error = None
        return "outer"

    assert execution.transaction(body) == Committed("outer")
    (inner,) = refused
    assert isinstance(inner, BeginFailed)
    assert execution.suspect
    assert connection.boundary[-2:] == ["SAVEPOINT", "COMMIT"]


def test_transaction_reports_a_commit_time_driver_error_as_rolled_back() -> None:
    outcome = _direct_execution(
        _FakeConnection(commit_error=errors.SerializationFailure("serialize"))
    ).transaction(lambda _port: None)
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CommitFailed)
    # A serialization failure at commit (40001) shares the retriable deadlock category.
    assert _translated(trigger.error).category == "deadlock"
    assert _translated(trigger.error).native_code == "40001"


def test_a_reported_boundary_failure_keeps_the_driver_exception_as_its_cause() -> None:
    # A statement failure is raised `from` the psycopg exception it classified,
    # so a caller reading the traceback sees the driver's own words. A boundary
    # failure is reported rather than raised, and chaining it here is what keeps
    # that reading the same for both.
    driver_error = errors.SerializationFailure("serialize")
    outcome = _direct_execution(_FakeConnection(commit_error=driver_error)).transaction(
        lambda _port: None
    )
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CommitFailed)
    assert trigger.error.__cause__ is driver_error


def test_transaction_reports_a_non_driver_body_error_unchanged() -> None:
    class _Boom(Exception):
        pass

    raised_by_the_body = _Boom()

    def body(_port: object) -> None:
        raise raised_by_the_body

    assert _direct_execution(_FakeConnection()).transaction(body) == RolledBack(
        CallbackRaised(raised_by_the_body)
    )


def test_transaction_reports_a_body_raised_driver_error_unchanged() -> None:
    # m-db-port scopes translation to the errors the PORT makes; an exception the
    # caller's own body raised is not one of them, however psycopg-shaped it is.
    # The identical object reaches the caller, so a body-authored deadlock-class
    # exception cannot read as a retriable DatabaseError to m-auto-retry and have
    # the body replayed over a failure the database never reported.
    raised_by_the_body = errors.DeadlockDetected("the caller's own deadlock")

    def body(_port: object) -> None:
        raise raised_by_the_body

    outcome = _direct_execution(_FakeConnection()).transaction(body)
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CallbackRaised)
    assert trigger.error is raised_by_the_body


def test_transaction_reports_a_rollback_failure_beside_the_body_error_that_triggered_it() -> None:
    # The other side of the same boundary: the rollback the body triggered is the
    # port's own work, so ITS driver failure classifies as one -- and neither
    # error replaces the other, because a caller needs the trigger to know what
    # went wrong and the rollback failure to know that undoing it did not happen.
    raised_by_the_body = errors.DeadlockDetected("the caller's own deadlock")

    def body(_port: object) -> None:
        raise raised_by_the_body

    connection = _FakeConnection(rollback_error=errors.UniqueViolation("dup"))
    execution = _direct_execution(connection)
    outcome = execution.transaction(body)
    assert isinstance(outcome, RollbackFailed)
    assert outcome.trigger == CallbackRaised(raised_by_the_body)
    assert _translated(outcome.rollback_error).violates_unique_index
    assert _translated(outcome.rollback_error).native_code == "23505"
    # The transaction's outcome is unknown, so the connection is not offered for
    # reuse; disposing of it belongs to the acquisition that will end next.
    assert execution.suspect


def test_transaction_separates_a_rollback_failure_raised_as_the_bodys_own_object() -> None:
    # The same two failures over a driver that caches ONE exception object for
    # every failure -- the input m-db-port already requires an adapter to
    # withstand. Body and rollback then fail with the identical object, so
    # neither its type nor its identity says which occurrence is which: an
    # adapter reading identity alone reports the rollback's failure as the
    # body's, which m-auto-retry would read as a caller error the port never
    # made. Where each failure occurred is what separates them, so the body's
    # object stays the trigger and the boundary's own rollback classifies.
    reused = errors.UniqueViolation("dup")

    def body(_port: object) -> None:
        raise reused

    outcome = _direct_execution(_FakeConnection(rollback_error=reused)).transaction(body)
    assert isinstance(outcome, RollbackFailed)
    assert outcome.trigger == CallbackRaised(reused)
    assert outcome.rollback_error is not reused
    assert _translated(outcome.rollback_error).violates_unique_index


def test_transaction_reports_a_rollback_failure_after_a_failed_commit() -> None:
    # Both halves of the boundary failed: the commit that ended the work, and the
    # rollback that could not undo it. The commit failure stays the trigger --
    # replacing it with the rollback's would lose why the transaction ended.
    connection = _FakeConnection(
        commit_error=errors.SerializationFailure("serialize"),
        rollback_error=errors.OperationalError("the connection is lost"),
    )
    execution = _direct_execution(connection)
    outcome = execution.transaction(lambda _port: None)
    assert isinstance(outcome, RollbackFailed)
    trigger = outcome.trigger
    assert isinstance(trigger, CommitFailed)
    assert _translated(trigger.error).native_code == "40001"
    assert _translated(outcome.rollback_error).category is None
    assert execution.suspect


def test_transaction_reports_a_body_raised_base_exception_unchanged() -> None:
    # Reporting the body's failure must not change what it IS: a base-level
    # exception stays base-level and stays the same object, so a cancellation or
    # interrupt is neither translated nor made catchable as an ordinary error on
    # the way out.
    raised_by_the_body = KeyboardInterrupt()

    def body(_port: object) -> None:
        raise raised_by_the_body

    outcome = _direct_execution(_FakeConnection()).transaction(body)
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CallbackRaised)
    assert trigger.error is raised_by_the_body


def test_a_connection_whose_client_encoding_is_not_utf_8_is_refused() -> None:
    # SQL crosses this boundary as UTF-8 bytes and a stored document is decoded
    # as UTF-8 text, so another encoding corrupts both. The refusal names the
    # setting and its effective value, which are session configuration rather
    # than credentials.
    connection = _FakeConnection(encoding="latin1")
    with pytest.raises(IncompatibleSessionError, match="client encoding"):
        initialize_connection(cast("psycopg.Connection[TupleRow]", connection))


def test_a_connection_whose_date_style_is_not_iso_is_refused() -> None:
    # A finite `timestamptz` is decoded from its text form, which psycopg's
    # loader reads in ISO order; the field order WITHIN ISO does not affect that
    # and is left alone.
    connection = _FakeConnection(date_style="German, DMY")
    with pytest.raises(IncompatibleSessionError, match="DateStyle"):
        initialize_connection(cast("psycopg.Connection[TupleRow]", connection))

    for accepted in ("ISO, MDY", "ISO, DMY", "ISO, YMD"):
        initialize_connection(
            cast("psycopg.Connection[TupleRow]", _FakeConnection(date_style=accepted))
        )


def test_the_per_connection_setup_records_a_refusal_and_reraises_it() -> None:
    # A pool creates most of its connections on its own background path, where a
    # refusal is retried and logged where a caller waiting for one never sees
    # it; the record is what lets the eventual timeout say what is wrong.
    establishment = ConnectionEstablishment()
    refused = _FakeConnection(encoding="latin1")

    with pytest.raises(IncompatibleSessionError) as raised:
        establishment(cast("psycopg.Connection[TupleRow]", refused))

    assert establishment.last_refusal is raised.value
    establishment(cast("psycopg.Connection[TupleRow]", _FakeConnection()))
    assert establishment.last_refusal is None
