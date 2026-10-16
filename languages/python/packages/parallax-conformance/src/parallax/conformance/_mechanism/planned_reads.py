from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance._mechanism.sole_connection import ConnectsAsItself, body_outcome
from parallax.conformance._mechanism.transaction_control import read_only, transact, underlying
from parallax.conformance.case_format import TransactionKeywords, read_only_keywords
from parallax.core.db_port import (
    AccessMode,
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect
from parallax.core.execution import ServingModel, TxnOptions
from parallax.core.object_query import ObjectQueryNode
from parallax.core.sql_gen import LoweredStatement
from parallax.snapshot import Database, ReadOnlyTxnContext, ScopedDatabase, TxnContext

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
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
        access_mode: AccessMode | None = None,
    ) -> TransactionOutcome[T]:
        del isolation, access_mode
        return body_outcome(self, body)


def planned_read(
    serving: ServingModel,
    options: TxnOptions,
    dialect: Dialect,
    query: ObjectQueryNode,
    *,
    form: Literal["rows", "graph"] = "graph",
    transaction: TransactionKeywords | None = None,
    access_mode: AccessMode = "read_write",
) -> tuple[LoweredStatement, ...]:
    """The read statements production issues for ``query`` before any row arrives.

    The read runs through the public Snapshot surface — ``read_rows`` for the
    row form, ``wire.find`` for the graph form — inside a transaction with
    ``transaction``'s keywords when given, opened through the entrypoint
    ``access_mode`` selects, so the lock suffix is the one that transaction's
    resolved preference and the target's Optimistic Lock Facet produce, or none
    at all in a read-only one.
    """
    observation = LifecycleObservation()
    with Database.connect(
        _EmptyDatabase(dialect),
        serving,
        options=options,
        lifecycle_provider=observation.provider,
    ) as root:
        db = root.using_database_login()

        def read(source: ScopedDatabase | TxnContext | ReadOnlyTxnContext) -> object:
            return source.read_rows(query) if form == "rows" else source.wire.find(query)

        if transaction is None:
            underlying(lambda: read(db))
        elif access_mode == "read_only":
            read_only(db, read, **read_only_keywords(transaction, where="a read-only read"))
        else:
            transact(db, read, **transaction)
    return observation.since(0, "read")
