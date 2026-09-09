"""The shared ``m-db-port`` doubles: one script, one recording, one refusal.

Each double is an ADAPTER, so it is what a ``Database`` is connected from and
what owns the runtime, acquisition contexts, and scoped connections underneath.
Every acquisition yields a FRESH connection facade over the one script, and
leaving that acquisition revokes the facade — so a suite proves that an
operation released what it took by watching the facade stop working, exactly as
it would against a real runtime. The script itself is shared across
acquisitions, which is what keeps one chronology readable across a retry.

The verbs are also available on the adapter directly, for the suites that drive
an executor rather than a handle and need a connection without composing one.
That is a convenience of the double and not a shape any production adapter has.

``ScriptedAdapter`` answers by POSITION — each call takes the next entry of an
immutable script, and a call the script does not reach is a failure at the call
rather than a silently different answer. The script is a TREE: a ``Transact``
entry nests the entries its body may run, so which side of a transaction
boundary a call landed on is stated by the shape rather than left implicit.
``RefusingAdapter`` answers nothing at all, for a path asserted to reach no
database, so it records nothing either. What ``ScriptedAdapter`` records is one
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
    CleanupResult,
    CommitFailed,
    Committed,
    ConnectionAcquisitionError,
    ConnectionContext,
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    PoolMetricsSource,
    Returned,
    RollbackFailed,
    RolledBack,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect

__all__ = [
    "BeginCall",
    "CommitCall",
    "ConnectsAsItself",
    "PortCall",
    "Read",
    "ReadCall",
    "RefusingAdapter",
    "RollbackCall",
    "ScriptEntry",
    "ScriptedAdapter",
    "ScriptedContext",
    "ScriptedRuntime",
    "SoleConnectionRuntime",
    "SoleConnectionScope",
    "Transact",
    "Write",
    "WriteCall",
    "body_outcome",
]

_REVOKED = "this scripted connection's scope has ended"

_RETURNED: Final[CleanupResult] = Returned()
"""What a completed relinquishment establishes where nothing had to be reclaimed."""


class SoleConnectionScope:
    """One acquisition of a double that IS its own connection.

    There is nothing to check out and nothing to give back, but "nothing to give
    back" is still a completed relinquishment rather than an absent one: the
    contract is that an acquisition which was entered reports what its exit
    ESTABLISHED, and ``None`` is reserved for a context nobody entered or one
    whose entry never reached ownership. So this reports :class:`Returned` from
    the moment it is left, and nothing before that.
    """

    __slots__ = ("_connection", "_left")

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection
        self._left = False

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return _RETURNED if self._left else None

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


class SoleConnectionRuntime:
    """The minimal runtime around one in-memory connection."""

    __slots__ = ("_connection", "closed")

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection
        self.closed = False

    @property
    def dialect(self) -> Dialect:
        return self._connection.dialect

    @property
    def pool_metrics(self) -> PoolMetricsSource | None:
        return None

    def connection(self) -> ConnectionContext:
        if self.closed:
            raise ConnectionAcquisitionError(
                "this runtime is closed, so it opens no new connection", reason="closed"
            )
        return SoleConnectionScope(self._connection)

    def close(self) -> None:
        self.closed = True


class ConnectsAsItself:
    """A double that is its own configuration as well as its own connection.

    A production adapter is configuration and a connection is what one
    acquisition of it yields; a double small enough to be both saves every suite
    that drives an executor directly from composing a resource lifetime it does
    not care about. What it costs is that such a double proves nothing about
    acquisition — the suites that grade THAT use ``ScriptedAdapter``, whose
    every acquisition yields a fresh revocable facade.
    """

    def open(self) -> SoleConnectionRuntime:
        return SoleConnectionRuntime(cast("DatabaseConnection", self))


def body_outcome[T](
    port: DatabaseConnection, body: Callable[[DatabaseConnection], T]
) -> TransactionOutcome[T]:
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

    isolation: IsolationLevel | None = None


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


class _ScriptedConnection:
    """One acquisition's execution access over a shared script.

    A fresh one per acquisition, revoked when that acquisition ends: after
    revocation every verb raises before reaching the script, which is how a
    suite proves an operation gave its connection back without inspecting a
    pool.
    """

    def __init__(self, adapter: ScriptedAdapter) -> None:
        self._adapter: ScriptedAdapter | None = adapter
        self.dialect = adapter.dialect

    def revoke(self) -> None:
        self._adapter = None

    def _script(self) -> ScriptedAdapter:
        adapter = self._adapter
        if adapter is None:
            raise RuntimeError(_REVOKED)
        return adapter

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return self._script().execute(sql, binds, document_reads)

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return self._script().execute_write(sql, binds)

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        adapter = self._script()
        return adapter.transaction(body, isolation=isolation, on=self)


class ScriptedContext:
    """One scripted acquisition, single-use exactly as a real one is."""

    def __init__(self, runtime: ScriptedRuntime) -> None:
        self._runtime = runtime
        self._connection: _ScriptedConnection | None = None
        self._spent = False
        self._cleanup_result: CleanupResult | None = None

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return self._cleanup_result

    def __enter__(self) -> DatabaseConnection:
        if self._spent:
            raise RuntimeError("a scripted connection context is entered exactly once")
        self._spent = True
        adapter = self._runtime.adapter
        # Closure first: a runtime that stopped admitting refuses whatever a
        # script had planned for this acquisition, exactly as a real one does.
        if self._runtime.closed:
            raise ConnectionAcquisitionError("this scripted runtime is closed", reason="closed")
        refusal = adapter.next_acquisition_failure()
        if refusal is not None:
            # A scripted acquisition failure reports cleanup facts only where the
            # script gave it some: absence is the default because a checkout that
            # never took anything has nothing to have cleaned up.
            self._cleanup_result = adapter.scripted_cleanup_result()
            adapter.cleanups.append(self._cleanup_result)
            raise refusal
        adapter.acquisitions += 1
        connection = _ScriptedConnection(adapter)
        self._connection = connection
        return connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        del exc_type, exc, traceback
        connection = self._connection
        self._connection = None
        if connection is None:
            return
        connection.revoke()
        self._cleanup_result = self._runtime.adapter.next_cleanup_result()
        self._runtime.adapter.cleanups.append(self._cleanup_result)


class ScriptedRuntime:
    """The runtime a scripted adapter opens: acquisitions over one script."""

    def __init__(self, adapter: ScriptedAdapter) -> None:
        self.adapter = adapter
        self.closed = False

    @property
    def dialect(self) -> Dialect:
        return self.adapter.dialect

    @property
    def pool_metrics(self) -> PoolMetricsSource | None:
        return None

    def connection(self) -> ConnectionContext:
        return ScriptedContext(self)

    def close(self) -> None:
        self.closed = True
        self.adapter.closes += 1


class ScriptedAdapter:
    """An ``m-db-port`` adapter answering each call with the next script entry.

    Used as a context manager, leaving the block normally asserts that every
    entry was reached: an unconsumed one means the code under test did less than
    the script said.

    ``acquisition_failures`` and ``cleanup_results`` are consumed positionally by
    successive acquisitions and releases, with anything past their end
    succeeding — so a suite names the third acquisition's timeout without
    writing the two before it. ``acquisitions``, ``cleanups``, and ``closes``
    record what actually happened.
    """

    dialect: Dialect

    def __init__(
        self,
        *script: ScriptEntry,
        dialect: Dialect = POSTGRES,
        acquisition_failures: Sequence[ConnectionAcquisitionError | None] = (),
        cleanup_results: Sequence[CleanupResult | None] = (),
    ) -> None:
        seen: dict[int, Exception] = {}
        for failure in _failures(script):
            if id(failure) in seen:
                raise ValueError("one failure instance cannot be reported by two calls")
            seen[id(failure)] = failure
        self.dialect = dialect
        self.calls: list[PortCall] = []
        self.acquisitions = 0
        self.closes = 0
        self.cleanups: list[CleanupResult | None] = []
        self._acquisition_failures = list(acquisition_failures)
        self._cleanup_results = list(cleanup_results)
        self._scopes = [_Scope(script)]
        self._unreached = False

    def open(self) -> ScriptedRuntime:
        return ScriptedRuntime(self)

    def next_acquisition_failure(self) -> ConnectionAcquisitionError | None:
        if not self._acquisition_failures:
            return None
        return self._acquisition_failures.pop(0)

    def next_cleanup_result(self) -> CleanupResult:
        """What the next completed release reports, defaulting to a clean return."""
        if not self._cleanup_results:
            return _RETURNED
        scripted = self._cleanup_results.pop(0)
        return _RETURNED if scripted is None else scripted

    def scripted_cleanup_result(self) -> CleanupResult | None:
        """What a FAILED entry reports, which is nothing unless a script said so."""
        if not self._cleanup_results:
            return None
        return self._cleanup_results.pop(0)

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
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
        on: DatabaseConnection | None = None,
    ) -> TransactionOutcome[T]:
        """``on`` is the connection the body is handed, defaulting to this adapter.

        A body inside a transaction receives the SAME scoped connection the
        attempt acquired, so an acquisition passes its own facade here and the
        direct-execution convenience passes nothing.
        """
        entry = self._scopes[-1].take(Transact, f"isolation={isolation!r}")
        self.calls.append(BeginCall(isolation))
        if entry.begin is not None:
            return BeginFailed(entry.begin)
        scope = _Scope(entry.body)
        self._scopes.append(scope)
        try:
            outcome = body_outcome(on if on is not None else cast("DatabaseConnection", self), body)
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


class RefusingAdapter:
    """An adapter asserting that no database interaction is permitted.

    Every statement and every boundary is a failure at the call, and so is
    ACQUIRING one at all — which is the stronger proof pooling makes available:
    a path rejected before it reaches a database now demonstrably takes no
    connection either. Its dialect stays readable: refusal is about resources
    and SQL, and dialect metadata must be discoverable without either.
    """

    dialect: Dialect

    def __init__(self, *, dialect: Dialect = POSTGRES) -> None:
        self.dialect = dialect

    def open(self) -> RefusingAdapter:
        return self

    @property
    def pool_metrics(self) -> PoolMetricsSource | None:
        return None

    def connection(self) -> ConnectionContext:
        raise AssertionError("no acquisition expected — this adapter refuses the database")

    def close(self) -> None:
        return

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
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        del body, isolation
        raise AssertionError("no transaction expected — this port refuses the database")
