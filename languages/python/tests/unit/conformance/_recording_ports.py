"""The conformance engine's own in-memory ports, answering canned rows and
recording the SQL they were handed.

Each is a ``ConnectsAsItself`` over the shared ``m-db-port`` doubles. None
scripts a boundary: every transaction they run ends exactly as its body did,
through :func:`body_outcome`. What one of them varies is stated on its
constructor rather than by subclassing it, so a port that reports a zero-row
shortfall, or fails its parameterized write, or answers successive reads from a
script, is still the one recording fake.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    Committed,
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from tests._support.db_port import ConnectsAsItself, body_outcome, projected_row
from tests._support.document_reads import fold_mapping_rows

__all__ = ["FakeDbPort", "FakeWritePort", "QueueDbPort"]


class FakeDbPort(ConnectsAsItself):
    """An in-memory port that records executed SQL and returns canned rows."""

    dialect: Dialect = POSTGRES

    def __init__(self, rows: list[Row]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, list[object]]] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        self.executed.append((sql, list(binds)))
        return fold_mapping_rows(self.rows, document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        return body_outcome(self, body)


class FakeWritePort(ConnectsAsItself):
    """An in-memory ``m-db-port`` recording DML + read execution and commit/rollback.

    ``find_rows`` is what every read answers, folded through the projection the
    statement asked for, unless ``read_script`` is given: then each read takes
    the script's next result verbatim and an exhausted script answers no rows,
    so a retry sequence's successive source reads observe successive
    generations of one row. A write is recorded and reports one affected row,
    except that a statement starting with any spelling in ``zero_affected_for``
    (the DRIVER spelling, so a golden write is named as it reaches the port)
    reports a zero-row shortfall, and a parameterized statement raises
    ``parameterized_write_failure`` after being recorded — a case's own
    bind-free ``given.apply`` writer still lands, so the failure is the
    parameterized write's own.
    """

    dialect: Dialect = POSTGRES

    def __init__(
        self,
        find_rows: list[Row] | None = None,
        *,
        zero_affected_for: tuple[str, ...] = (),
        parameterized_write_failure: DatabaseError | None = None,
        read_script: Sequence[list[Row]] | None = None,
    ) -> None:
        self.find_rows = find_rows if find_rows is not None else []
        self.writes: list[tuple[str, list[object]]] = []
        self.reads: list[tuple[str, list[object]]] = []
        self.commits = 0
        self.rollbacks = 0
        self._zero_affected_for = zero_affected_for
        self._parameterized_write_failure = parameterized_write_failure
        self._read_script = None if read_script is None else list(read_script)

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        self.reads.append((sql, list(binds)))
        if self._read_script is not None:
            return self._read_script.pop(0) if self._read_script else []
        return fold_mapping_rows(self.find_rows, document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, list(binds)))
        if binds and self._parameterized_write_failure is not None:
            raise self._parameterized_write_failure
        return 0 if sql.startswith(self._zero_affected_for) else 1

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        outcome = body_outcome(self, body)
        if isinstance(outcome, Committed):
            self.commits += 1
        else:
            self.rollbacks += 1
        return outcome


class QueueDbPort(ConnectsAsItself):
    """A fake ``m-db-port`` returning one canned response per ``execute()`` call.

    A read case's own ``given.corrupt`` writes through this port before the read
    runs, so a stand-in for one answers a write with one affected row and
    records nothing; it opens no transaction of its own.
    """

    dialect: Dialect = POSTGRES

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        self._responses = list(responses)

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return [projected_row(sql, row) for row in self._responses.pop(0)]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        return 1

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        raise NotImplementedError
