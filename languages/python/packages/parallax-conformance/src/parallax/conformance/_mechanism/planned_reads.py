from __future__ import annotations

from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Literal

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance._mechanism.transaction_control import transact, underlying
from parallax.conformance.case_format import TransactionKeywords
from parallax.core.db_port import (
    CallbackRaised,
    CleanupResult,
    Committed,
    ConnectionContext,
    ConnectionContextSource,
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    PipelineStatement,
    Returned,
    RolledBack,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect
from parallax.core.object_query import ObjectQueryNode
from parallax.core.sql_gen import LoweredStatement
from parallax.snapshot import DatabaseOptions, handle
from parallax.snapshot.handle import ServingModel

__all__ = ["planned_read"]


class _EmptyDatabase:
    """A database holding no rows, which answers every read with none.

    A read over it runs every step production takes before its first result
    arrives, so the statements it issues are the ones production plans for the
    query; what an empty root result prevents is only the child levels, whose
    binds are the parent keys a result would have supplied.
    """

    def __init__(self, dialect: Dialect) -> None:
        self.dialect = dialect
        self._closed = False

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del sql, binds, document_reads
        return []

    def execute_pipeline(
        self, statements: Sequence[PipelineStatement]
    ) -> list[list[Row]]:  # pragma: no cover - no planned read pipelines
        return [[] for _ in statements]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise AssertionError(f"a planned read must not write: {sql!r}")

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        del isolation
        try:
            return Committed(body(self))
        except BaseException as raised:
            return RolledBack(CallbackRaised(raised))

    def open(self) -> _EmptyDatabase:
        return self

    @property
    def pool_metrics(self) -> None:
        return None

    @property
    def login_identity(self) -> str:
        return "conformance-planned-read"

    def login_execution(self) -> ConnectionContextSource:
        return self

    def principal_execution(
        self, authorization: object
    ) -> ConnectionContextSource:  # pragma: no cover - planned reads use the login
        del authorization
        return self

    def new_context(self) -> ConnectionContext:
        return _Acquisition(self)

    def close(self) -> None:
        self._closed = True


class _Acquisition:
    def __init__(self, connection: _EmptyDatabase) -> None:
        self._connection = connection
        self._left = False

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return Returned() if self._left else None

    def __enter__(self) -> DatabaseConnection:
        return self._connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._left = True


def planned_read(
    serving: ServingModel,
    options: DatabaseOptions,
    dialect: Dialect,
    query: ObjectQueryNode,
    *,
    form: Literal["rows", "graph"] = "graph",
    transaction: TransactionKeywords | None = None,
) -> tuple[LoweredStatement, ...]:
    """The read statements production issues for ``query`` before any row arrives.

    The read runs through the public Snapshot surface — ``read_rows`` for the
    row form, ``wire.find`` for the graph form — inside ``db.transact`` with
    ``transaction``'s keywords when given, so the lock suffix is the one that
    transaction's resolved preference and the target's Optimistic Lock Facet
    produce.
    """
    observation = LifecycleObservation()
    with handle.Database.connect(
        _EmptyDatabase(dialect),
        serving,
        options=options,
        lifecycle_provider=observation.provider,
    ) as root:
        db = root.using_database_login()

        def read(source: handle.ScopedDatabase | handle.Transaction) -> object:
            return source.read_rows(query) if form == "rows" else source.wire.find(query)

        if transaction is None:
            underlying(lambda: read(db))
        else:
            transact(db, read, **transaction)
    return observation.since(0, "read")
