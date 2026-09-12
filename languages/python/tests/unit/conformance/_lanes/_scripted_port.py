"""The scenario lanes' scripted in-memory port: a ``DatabaseConnection`` fake
answering each read from a call-ordered script of row pages and each write
from a script of affected-row counts, recording the SQL it was handed.

Unlike the recording fakes in :mod:`tests.unit.conformance._recording_ports`,
which answer one constant row set for every read and report every write as
one row affected, a script distinguishes successive calls: the write core's
delivery-settlement and read-your-own-writes pins need a page sequence, and a
two-session interleaved choreography needs each connection scripted with its
OWN sequence to reproduce a real stale-version mismatch deterministically,
with no real database involved.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from parallax.core.db_port import DatabaseConnection, MappingRow, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from tests._support.db_port import ConnectsAsItself, body_outcome, projected_row

__all__ = ["ScriptedPort"]


class ScriptedPort(ConnectsAsItself):
    """A ``DatabaseConnection`` fake with per-call SCRIPTED read rows and
    write-affected counts: each ``execute`` answers the next page of
    ``read_rows`` projected to the statement's own columns (an empty page once
    the script is spent) and each
    ``execute_write`` the next count of ``write_affected`` (one row once it
    is), and both record the statement they were handed. A transaction ends
    exactly as its body did, through :func:`body_outcome`; ``raise_on_read``
    makes every read raise the given failure instead, standing in for a
    worker thread's own unexpected defect.

    Every method here is a plain synchronous, in-memory call that never blocks
    on real I/O, so there is nothing for an interleaved execution's termination
    ladder to unblock: an execution wrapping this port declares that trust
    truthfully rather than as a shortcut around it.

    ``dialect`` is a constructor argument rather than the class attribute every
    other double declares, because the two-session pins hand the peer session a
    DIFFERENT dialect from the main port's, so a statement's own spelling names
    the connection that compiled it."""

    def __init__(
        self,
        *,
        dialect: Dialect = POSTGRES,
        read_rows: Sequence[list[MappingRow]] = (),
        write_affected: Sequence[int] = (),
        raise_on_read: BaseException | None = None,
    ) -> None:
        self.dialect = dialect
        self._read_rows = [list(rows) for rows in read_rows]
        self._write_affected = list(write_affected)
        self._raise_on_read = raise_on_read
        self.reads: list[tuple[str, tuple[object, ...]]] = []
        self.writes: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        if self._raise_on_read is not None:
            raise self._raise_on_read
        self.reads.append((sql, tuple(binds)))
        rows = self._read_rows.pop(0) if self._read_rows else []
        return [projected_row(sql, row, document_reads) for row in rows]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, tuple(binds)))
        return self._write_affected.pop(0) if self._write_affected else 1

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        return body_outcome(self, body)

    def close(self) -> None:
        self.closed = True
