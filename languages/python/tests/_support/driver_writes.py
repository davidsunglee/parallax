"""The parameterized writes a case database's driver was handed, and their grading.

A run lane reports each statement's binds re-encoded as Wire values, which
spells a managed scalar ``-0.0`` as ``0.0``: the driver bind is the only place
a scalar float write's sign is observable before the database stores it. The
recording wraps both halves of a case database and records each modeled
``execute_write`` before forwarding it: every write through the configuration a
``Database`` is composed from — its runtimes, acquisitions, connections, and
transaction bodies — and every write in a transaction body the lane runs on its
directly driven session. A statement the lane executes on that session outside
a transaction is one the case authors verbatim, such as ``given.apply``, and is
forwarded unrecorded.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from types import TracebackType

from parallax.conformance._database_control import CaseDatabase
from parallax.core.db_port import (
    Bind,
    CleanupResult,
    ConnectionContext,
    ConnectionContextSource,
    DatabaseConnection,
    DatabaseRuntime,
    DocumentReadOrdinals,
    IsolationLevel,
    PipelineStatement,
    PoolMetricsSource,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from tests._support.bind_positions import assert_zero_signs, statement_bind_positions
from tests._support.sweep_goldens import wire_binds

__all__ = ["RecordingCaseDatabase", "assert_driver_write_zero_signs"]

type DriverWrite = tuple[str, list[object]]

_WRITE_VERBS = ("insert", "update", "delete")


class _RecordingRuntime:
    def __init__(self, inner: DatabaseRuntime, writes: list[DriverWrite]) -> None:
        self._inner = inner
        self._writes = writes

    @property
    def dialect(self) -> Dialect:
        return self._inner.dialect

    @property
    def login_identity(self) -> str:
        return self._inner.login_identity

    @property
    def pool_metrics(self) -> PoolMetricsSource | None:
        return self._inner.pool_metrics

    def login_execution(self) -> ConnectionContextSource:
        return _RecordingSource(self._inner.login_execution(), self._writes)

    def principal_execution(self, authorization: object) -> ConnectionContextSource:
        return _RecordingSource(self._inner.principal_execution(authorization), self._writes)

    def close(self) -> None:
        self._inner.close()


class _RecordingSource:
    def __init__(self, inner: ConnectionContextSource, writes: list[DriverWrite]) -> None:
        self._inner = inner
        self._writes = writes

    def new_context(self) -> ConnectionContext:
        return _RecordingContext(self._inner.new_context(), self._writes)


class _RecordingContext:
    def __init__(self, inner: ConnectionContext, writes: list[DriverWrite]) -> None:
        self._inner = inner
        self._writes = writes

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return self._inner.cleanup_result

    def __enter__(self) -> DatabaseConnection:
        return _RecordingConnection(self._inner.__enter__(), self._writes)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._inner.__exit__(exc_type, exc, traceback)


class _RecordingConnection:
    def __init__(self, inner: DatabaseConnection, writes: list[DriverWrite]) -> None:
        self._inner = inner
        self._writes = writes

    @property
    def dialect(self) -> Dialect:
        return self._inner.dialect

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return self._inner.execute(sql, binds, document_reads)

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return self._inner.execute_pipeline(statements)

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self._writes.append((sql, list(binds)))
        return self._inner.execute_write(sql, binds)

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        writes = self._writes
        return self._inner.transaction(
            lambda connection: body(_RecordingConnection(connection, writes)), isolation=isolation
        )


class RecordingCaseDatabase(_RecordingConnection):
    """A case database that records every modeled parameterized write its driver
    receives."""

    def __init__(self, inner: CaseDatabase) -> None:
        super().__init__(inner, [])
        self._case = inner

    @property
    def writes(self) -> list[DriverWrite]:
        return self._writes

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return self._case.execute_write(sql, binds)

    def open(self) -> DatabaseRuntime:
        return _RecordingRuntime(self._case.open(), self._writes)


def assert_driver_write_zero_signs(
    model: Metamodel,
    dialect: Dialect,
    golden: Sequence[tuple[str, list[object]]],
    writes: Sequence[DriverWrite],
) -> None:
    """The recorded modeled writes are the golden writes, in order, and each
    carries the golden's zero sign at every declared float position."""
    golden_writes = [
        (sql, binds) for sql, binds in golden if sql.lstrip().lower().startswith(_WRITE_VERBS)
    ]
    assert [sql for sql, _binds in writes] == [
        dialect.to_driver_sql(sql) for sql, _binds in golden_writes
    ], "the driver writes are not the golden writes"
    for (golden_sql, golden_binds), (_driver_sql, driver_binds) in zip(
        golden_writes, writes, strict=True
    ):
        assert_zero_signs(
            wire_binds(driver_binds),
            wire_binds(golden_binds),
            statement_bind_positions(model, golden_sql, golden_binds),
            label="driver bind",
        )
