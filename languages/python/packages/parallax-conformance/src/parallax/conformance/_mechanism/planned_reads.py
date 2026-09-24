from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance._mechanism.sole_connection import ConnectsAsItself, body_outcome
from parallax.conformance._mechanism.transaction_control import transact, underlying
from parallax.conformance.case_format import TransactionKeywords
from parallax.core.db_port import (
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect
from parallax.core.object_query import ObjectQueryNode
from parallax.core.sql_gen import LoweredStatement
from parallax.snapshot import DatabaseOptions, handle
from parallax.snapshot.handle import ServingModel

__all__ = ["planned_read"]


class _EmptyDatabase(ConnectsAsItself):
    """A database holding no rows, which answers every read with none.

    A read over it runs every step production takes before its first result
    arrives, so the statements it issues are the ones production plans for the
    query; what an empty root result prevents is only the child levels, whose
    binds are the parent keys a result would have supplied.
    """

    def __init__(self, dialect: Dialect) -> None:
        self.dialect = dialect

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del sql, binds, document_reads
        return []

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise AssertionError(f"a planned read must not write: {sql!r}")

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        del isolation
        return body_outcome(self, body)


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
