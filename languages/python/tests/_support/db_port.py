"""The shared ``m-db-port`` doubles: one script, one recording, one refusal.

``ScriptedPort`` answers by POSITION — each call takes the next entry of an
immutable script, and a call the script does not reach is a failure at the call
rather than a silently different answer. The script is a TREE: a ``Transact``
entry nests the entries its body may run, so which side of a transaction
boundary a call landed on is stated by the shape rather than left implicit.
``RefusingPort`` answers nothing at all, for a path asserted to reach no
database, so it records nothing either. What ``ScriptedPort`` records is one
flat chronology of :data:`PortCall` values, where the
``begin``/``commit``/``rollback`` markers already carry the scope the script had
to nest to express.

A row handed to :class:`Read` is ALREADY MANAGED — a document cell arrives as a
``PresentDocument`` or ``SQL_NULL``, never as the raw mapping a driver would
return — because folding a projection is the concrete adapter's own boundary
contract and belongs to the tests that grade it. And no exception instance may
appear twice in one script: ``m-db-port`` requires a failure a port reports to
be shared with no other invocation, and a double that broke that rule would let
a suite pin behavior no adapter can produce.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Self, cast

from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    BeginFailed,
    Bind,
    CallbackRaised,
    CommitFailed,
    Committed,
    DbPort,
    DocumentReadOrdinals,
    RollbackFailed,
    RolledBack,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect

__all__ = [
    "BeginCall",
    "CommitCall",
    "PortCall",
    "Read",
    "ReadCall",
    "RefusingPort",
    "RollbackCall",
    "ScriptEntry",
    "ScriptedPort",
    "Transact",
    "Write",
    "WriteCall",
    "body_outcome",
]


def body_outcome[T](port: DbPort, body: Callable[[DbPort], T]) -> TransactionOutcome[T]:
    """Run ``body`` on ``port`` and report what the body alone decided.

    Committed with its value, or rolled back carrying the exception it raised —
    including a base-level one, which a fake boundary undoes as readily as any
    other and which the composition root re-raises from the outcome.

    A fake port that scripts no boundary failure has no boundary of its own:
    nothing can fail at its begin, its commit, or its rollback, so every
    transaction it runs ends exactly as the body did. The doubles that stay
    bespoke route through here rather than restating that reading.
    """
    try:
        return Committed(body(port))
    except BaseException as raised:
        return RolledBack(CallbackRaised(raised))


# --------------------------------------------------------------------------- #
# The recording: one ordered chronology of typed calls.                       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ReadCall:
    """A row-returning statement, as the port received it."""

    sql: str
    binds: tuple[Bind, ...] = ()


@dataclass(frozen=True, slots=True)
class WriteCall:
    """A DML statement, as the port received it."""

    sql: str
    binds: tuple[Bind, ...] = ()


@dataclass(frozen=True, slots=True)
class BeginCall:
    """A transaction boundary opened, carrying the isolation the caller asked for."""

    isolation: str | None = None


@dataclass(frozen=True, slots=True)
class CommitCall:
    """The boundary the last ``BeginCall`` opened ended by committing."""


@dataclass(frozen=True, slots=True)
class RollbackCall:
    """The boundary the last ``BeginCall`` opened ended by rolling back."""


type PortCall = ReadCall | WriteCall | BeginCall | CommitCall | RollbackCall


# --------------------------------------------------------------------------- #
# The script: what the next call of each kind is answered with.               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Read:
    """The next ``execute``: these already-managed rows, or this failure.

    ``times`` answers that many successive reads the same way, which is how a
    paging lane says "the fourth page fails" without naming the three before it.
    """

    rows: Sequence[Mapping[str, object]] = ()
    raises: DatabaseError | None = None
    times: int = 1


@dataclass(frozen=True, slots=True)
class Write:
    """The next ``execute_write``: this affected-row count, or this failure."""

    affected: int = 1
    raises: DatabaseError | None = None
    times: int = 1


@dataclass(frozen=True, slots=True, init=False)
class Transact:
    """The next ``transaction``, and the entries its body may run inside it.

    A boundary failure is a clause here rather than an entry of its own, so a
    commit failure belonging to no transaction is unwritable: ``begin`` never
    opens and the body never runs, ``commit`` fails after a body that returned,
    and ``rollback`` fails the undo whatever triggered it.
    """

    body: tuple[ScriptEntry, ...]
    begin: DatabaseError | None
    commit: DatabaseError | None
    rollback: DatabaseError | None
    times: int

    def __init__(
        self,
        *body: ScriptEntry,
        begin: DatabaseError | None = None,
        commit: DatabaseError | None = None,
        rollback: DatabaseError | None = None,
        times: int = 1,
    ) -> None:
        if begin is not None and body:
            raise ValueError("a boundary that never opens runs no body")
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "begin", begin)
        object.__setattr__(self, "commit", commit)
        object.__setattr__(self, "rollback", rollback)
        object.__setattr__(self, "times", times)


type ScriptEntry = Read | Write | Transact


def _failures(entries: Sequence[ScriptEntry]) -> Iterator[Exception]:
    """Every failure the script would report, once per reporting call."""
    for entry in entries:
        for _ in range(entry.times):
            if isinstance(entry, Transact):
                clauses = (entry.begin, entry.commit, entry.rollback)
                yield from (clause for clause in clauses if clause is not None)
                yield from _failures(entry.body)
            elif entry.raises is not None:
                yield entry.raises


@dataclass(slots=True)
class _Scope:
    """How far one script level has been consumed."""

    entries: Sequence[ScriptEntry]
    index: int = 0
    used: int = 0

    def take[T: ScriptEntry](self, kind: type[T], detail: str) -> T:
        while self.index < len(self.entries):
            entry = self.entries[self.index]
            if self.used == entry.times:
                self.index += 1
                self.used = 0
                continue
            if not isinstance(entry, kind):
                break
            self.used += 1
            return entry
        raise AssertionError(f"unscripted {kind.__name__.lower()}: {detail}")

    @property
    def consumed(self) -> bool:
        remaining = self.entries[self.index :]
        return not remaining or (len(remaining) == 1 and self.used == remaining[0].times)


class ScriptedPort:
    """An ``m-db-port`` answering each call with the next entry of its script.

    Used as a context manager, leaving the block normally asserts that every
    entry was reached: an unconsumed one means the code under test did less than
    the script said.
    """

    dialect: Dialect

    def __init__(self, *script: ScriptEntry, dialect: Dialect = POSTGRES) -> None:
        seen: dict[int, Exception] = {}
        for failure in _failures(script):
            if id(failure) in seen:
                raise ValueError("one failure instance cannot be reported by two calls")
            seen[id(failure)] = failure
        self.dialect = dialect
        self.calls: list[PortCall] = []
        self._scopes = [_Scope(script)]
        self._unreached = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is None and (self._unreached or not self._scopes[0].consumed):
            raise AssertionError("the script was not consumed")

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del document_reads
        entry = self._scopes[-1].take(Read, sql)
        self.calls.append(ReadCall(sql, tuple(binds)))
        if entry.raises is not None:
            raise entry.raises
        return [projected_row(sql, row) for row in entry.rows]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        entry = self._scopes[-1].take(Write, sql)
        self.calls.append(WriteCall(sql, tuple(binds)))
        if entry.raises is not None:
            raise entry.raises
        return entry.affected

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        entry = self._scopes[-1].take(Transact, f"isolation={isolation!r}")
        self.calls.append(BeginCall(isolation))
        if entry.begin is not None:
            return BeginFailed(entry.begin)
        scope = _Scope(entry.body)
        self._scopes.append(scope)
        try:
            outcome = body_outcome(cast("DbPort", self), body)
        finally:
            self._scopes.pop()
        self._unreached = self._unreached or not scope.consumed
        if entry.commit is not None and isinstance(outcome, Committed):
            outcome = RolledBack(CommitFailed(entry.commit))
        self.calls.append(CommitCall() if isinstance(outcome, Committed) else RollbackCall())
        if entry.rollback is not None and isinstance(outcome, RolledBack):
            return RollbackFailed(outcome.trigger, entry.rollback)
        return outcome


_CAPTURE_CELL: Final = re.compile(r"(?:select |, )(\w+)\.\"?(\w+)\"? (parallax_seek_\d+)")


def projected_row(sql: str, row: Mapping[str, object]) -> Row:
    """``row`` as a fresh dict, carrying the coordinate cells ``sql`` selected.

    A paging read projects one hidden cell per Continuation Order term, so a
    stand-in database owes them exactly as a real one does. They are derived
    from the statement rather than authored per script because they are a
    RESTATEMENT of columns the script already carries — what the term's own
    expression evaluated to — and a script spelling them again could only
    disagree with itself.

    Only the plain alias-qualified form is derivable here; a script whose page
    orders by a document-resident member has to be answered by a double that
    knows the extraction, and is refused rather than silently under-projected.
    """
    materialized = dict(row)
    cells = _CAPTURE_CELL.findall(sql)
    if len(cells) != sql.count(" parallax_seek_"):
        raise AssertionError(f"a scripted read cannot derive every coordinate cell of {sql!r}")
    for _alias, column, cell in cells:
        materialized[cell] = materialized[column]
    return materialized


class RefusingPort:
    """An ``m-db-port`` asserting that no database interaction is permitted.

    Every statement and every boundary is a failure at the call, which is what
    a path proven to be rejected before it reaches a database needs. Its dialect
    stays readable: refusal is about SQL, and dialect metadata must be
    discoverable without a connection.
    """

    dialect: Dialect

    def __init__(self, *, dialect: Dialect = POSTGRES) -> None:
        self.dialect = dialect

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del sql, binds, document_reads
        raise AssertionError("no read expected — this port refuses the database")

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        del sql, binds
        raise AssertionError("no write expected — this port refuses the database")

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        del body, isolation
        raise AssertionError("no transaction expected — this port refuses the database")
