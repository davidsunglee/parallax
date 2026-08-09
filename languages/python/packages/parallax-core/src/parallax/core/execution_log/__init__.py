"""``parallax.core.execution_log`` enforcement scope (m-execution-log).

Transaction execution provenance: the read-only record of what a transaction
actually did, from one Database Call up through the retry-spanning Execution Log
a `db.transact` invocation returns.

The module is a **composition-level observer**. It names `m-sql` (the Lowered
Statement a call ran), `m-db-port` (the call boundary), `m-db-error` (the
category a failed call classified to), `m-unit-work` (the transaction, its write
batches, and their two triggers) and `m-auto-retry` (the retry policy and the
classifier's verdict); none of them names it. Two vocabularies it observes are
therefore imported rather than restated — :data:`~parallax.core.unit_work.WriteBatchTrigger`
is m-unit-work's own closed flush-trigger set and
:class:`~parallax.core.auto_retry.AttemptObserver` is the retry loop's own
publication point — so the observed keeps one spelling of each fact.

Reading and writing are separated by construction. Every published type is a
read-only value or view; every mutation goes through a **builder** the
composition root holds and no consumer ever sees. A view and its builder share
one private state object rather than reaching into each other, which is what
lets the view be handed out while the invocation is still running:

* :class:`ExecutionLogBuilder` — one per logical `transact` invocation,
  constructed BEFORE the retry loop because the log outlives any single attempt.
  It is the loop's :class:`~parallax.core.auto_retry.AttemptObserver`.
* :class:`AttemptRecorder` — one per physical attempt; brackets each Read Trace
  and Write Batch Trace, and records the attempt's terminal status.
* :class:`TraceRecorder` — the Database Call sink one trace is built from,
  and the concrete :class:`CallRecorder` an executor is handed.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Final, Literal, Protocol, overload

from parallax.core.auto_retry import AttemptObserver
from parallax.core.db_error import Category, DatabaseError
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    Concurrency,
    MissingTargetError,
    OptimisticLockConflictError,
    RollbackOnlyError,
    StaleWriteError,
    WriteBatchTrigger,
)

__all__ = [
    "AttemptFailure",
    "AttemptObserver",
    "AttemptRecorder",
    "AttemptStatus",
    "CallCompletion",
    "CallKind",
    "CallRecorder",
    "DatabaseCall",
    "DatabaseCallFailed",
    "ExecutionLog",
    "ExecutionLogBuilder",
    "FailurePhase",
    "ReadCompleted",
    "ReadTrace",
    "RetryPolicy",
    "Trace",
    "TraceRecorder",
    "TransactionAttempt",
    "TransactionInProgressError",
    "TransactionNotCommittedError",
    "TransactionResult",
    "WriteBatchTrace",
    "WriteBatchTrigger",
    "WriteCompleted",
]

type CallKind = Literal["read", "write"]
"""Whether a Database Call ran a query or DML — retained so a FAILED call stays
classifiable without parsing its SQL."""

type AttemptStatus = Literal["active", "committed", "rolled_back"]
"""One Transaction Attempt's lifecycle position. ``active`` is visible before the
attempt's body runs, so the log never shows a gap."""

type FailurePhase = Literal["body", "finalization", "commit"]
"""Where an attempt failed, stated without exposing a stack location or an
internal planner stage: ``body`` covers callback work, explicit reads, and the
write batches a read forced; ``finalization`` the boundary-owned final batch;
``commit`` the durability boundary."""


@dataclass(frozen=True, slots=True)
class ReadCompleted:
    """A query call's completion: the PHYSICAL number of rows the statement
    returned — never a count of result roots, unique graph nodes, or projection
    views."""

    returned_rows: int


@dataclass(frozen=True, slots=True)
class WriteCompleted:
    """A DML call's completion: the affected-row count the driver reported.

    A count that falls short of what the step addressed is still a COMPLETION —
    the call reached the database and came back. Post-call enforcement of that
    shortfall is the attempt's failure, not the call's.
    """

    affected_rows: int


@dataclass(frozen=True, slots=True)
class DatabaseCallFailed:
    """A call the port could not complete: the detached diagnostic alone.

    The raised exception, its traceback, and every scrap of transaction state are
    deliberately absent — a retained log must not pin an exception graph alive.
    """

    category: Category | None
    native_code: str | None
    message: str


type CallCompletion = ReadCompleted | WriteCompleted | DatabaseCallFailed
"""How a Database Call ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class DatabaseCall:
    """One ATTEMPTED round trip to the database.

    ``statement`` is retained BY REFERENCE — its binds are not copied, so a
    retained log retains and exposes whatever sensitive domain values they carry.
    ``duration_ns`` is measured monotonically around the port invocation alone,
    failed invocations included; it is informational and MUST NOT affect
    execution or conformance, and no wall-clock timestamp is retained.
    """

    statement: LoweredStatement
    kind: CallKind
    duration_ns: int
    completion: CallCompletion


@dataclass(frozen=True, slots=True)
class ReadTrace:
    """The calls one read issued.

    NON-EMPTY by invariant: a trace proves work that reached the database, so
    planning that fails before its first call creates no trace at all. A read
    surfaced to a caller SHARES this object with the attempt that issued it —
    there is never a second record of the same call.
    """

    calls: tuple[DatabaseCall, ...]

    @property
    def round_trips(self) -> int:
        """Every attempted call counts one, a failed one included."""
        return len(self.calls)


@dataclass(frozen=True, slots=True)
class WriteBatchTrace:
    """The calls one flushed write batch issued, naming the m-unit-work trigger
    that produced it.

    A ``read_dependency`` batch appears immediately BEFORE the Read Trace it
    enabled, which is how the log exposes that causality without anyone
    acquiring a public flush operation. A ``finalization`` batch is the
    attempt's last trace. Non-empty by the same invariant as a Read Trace.
    """

    trigger: WriteBatchTrigger
    calls: tuple[DatabaseCall, ...]

    @property
    def round_trips(self) -> int:
        return len(self.calls)


type Trace = ReadTrace | WriteBatchTrace
"""The two things an attempt records, in the order they reached the database."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """The invocation's effective retry configuration, after defaults and
    outer-transaction inheritance are resolved. Only the RESOLVED value is
    retained: whether the caller supplied it or inherited it is not."""

    max_retries: int
    retry_optimistic_conflicts: bool


@dataclass(frozen=True, slots=True)
class AttemptFailure:
    """The DETACHED diagnostic a rolled-back attempt retains.

    ``retry_eligible`` is the classifier's verdict under the effective policy —
    a CLASSIFICATION, independent of the remaining budget and claiming nothing
    about whether another attempt occurred. ``database_call`` names the existing
    call a failed port invocation, or post-call enforcement of a completed one,
    referenced; planning, arbitrary callback, and commit failures name none.
    """

    phase: FailurePhase
    error_type: str
    message: str
    code: str | None
    retry_eligible: bool
    database_call: DatabaseCall | None


class TransactionInProgressError(RuntimeError):
    """A Transaction Result's common execution view was asked for while the
    outer transaction was still running.

    A joined invocation shares the outer transaction's live log, so its result
    describes a physical transaction that has not yet reached an outcome.
    """


class TransactionNotCommittedError(RuntimeError):
    """A Transaction Result's common execution view was asked for after the
    outer transaction rolled back.

    The joined body returned, but the transaction it joined never committed, so
    there is no committed attempt for the view to name.
    """


class CallRecorder(Protocol):
    """Where an executor hands each Database Call it made.

    An executor holds this narrow view of a trace under construction: it can
    report a completed or a failed call and can read nothing back, so recording
    cannot become a channel the execution reads its own provenance through.
    """

    def completed(
        self,
        statement: LoweredStatement,
        kind: CallKind,
        duration_ns: int,
        completion: CallCompletion,
    ) -> None:
        """Record a call the port completed."""
        ...

    def failed(
        self, statement: LoweredStatement, kind: CallKind, duration_ns: int, error: DatabaseError
    ) -> None:
        """Record a call the port could not complete, keeping only its detached
        diagnostic."""
        ...


class TraceRecorder:
    """The append-only Database Call sink one trace is built from.

    :meth:`read_trace` and :meth:`write_batch_trace` seal the recorder and are
    idempotent: a second call answers the SAME object, which is what lets a read
    result and the attempt that issued it reference one trace rather than two
    equal ones.
    """

    __slots__ = ("_calls", "_read_trace", "_write_batch_trace")

    def __init__(self) -> None:
        self._calls: list[DatabaseCall] = []
        self._read_trace: ReadTrace | None = None
        self._write_batch_trace: WriteBatchTrace | None = None

    def completed(
        self,
        statement: LoweredStatement,
        kind: CallKind,
        duration_ns: int,
        completion: CallCompletion,
    ) -> None:
        self._calls.append(DatabaseCall(statement, kind, duration_ns, completion))

    def failed(
        self, statement: LoweredStatement, kind: CallKind, duration_ns: int, error: DatabaseError
    ) -> None:
        self._calls.append(
            DatabaseCall(
                statement,
                kind,
                duration_ns,
                DatabaseCallFailed(error.category, error.native_code, error.message),
            )
        )

    @property
    def last_call(self) -> DatabaseCall | None:
        """The most recently recorded call — the one an enclosing failure
        references when it was that call, or the enforcement of it, that failed."""
        return self._calls[-1] if self._calls else None

    def read_trace(self) -> ReadTrace:
        """This recorder's calls as a Read Trace."""
        if self._read_trace is None:
            self._read_trace = ReadTrace(tuple(self._calls))
        return self._read_trace

    def write_batch_trace(self, trigger: WriteBatchTrigger) -> WriteBatchTrace:
        """This recorder's calls as a Write Batch Trace with its own trigger."""
        if self._write_batch_trace is None:
            self._write_batch_trace = WriteBatchTrace(trigger, tuple(self._calls))
        return self._write_batch_trace


class _CallsView(Sequence[DatabaseCall]):
    """An attempt's flattened calls, derived on access rather than stored.

    Constructing it copies nothing and its length is computed from the trace
    count, so the convenience projection costs no storage and no work
    proportional to the number of calls.
    """

    __slots__ = ("_traces",)

    def __init__(self, traces: Sequence[Trace]) -> None:
        self._traces = traces

    def __len__(self) -> int:
        return sum(len(trace.calls) for trace in self._traces)

    @overload
    def __getitem__(self, index: int) -> DatabaseCall: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[DatabaseCall]: ...

    def __getitem__(self, index: int | slice) -> DatabaseCall | Sequence[DatabaseCall]:
        if isinstance(index, slice):
            return tuple(self)[index]
        position = index + len(self) if index < 0 else index
        for trace in self._traces:
            if position < len(trace.calls):
                return trace.calls[position]
            position -= len(trace.calls)
        raise IndexError(index)

    def __iter__(self) -> Iterator[DatabaseCall]:
        for trace in self._traces:
            yield from trace.calls


@dataclass(slots=True)
class _AttemptState:
    """One attempt's mutable record, shared by its view and its recorder."""

    status: AttemptStatus = "active"
    traces: list[Trace] = field(default_factory=list[Trace])
    failure: AttemptFailure | None = None
    phase: FailurePhase = "body"
    offending_call: DatabaseCall | None = None


class TransactionAttempt:
    """One PHYSICAL attempt of a logical transaction invocation (read-only)."""

    __slots__ = ("_state",)

    def __init__(self, state: _AttemptState) -> None:
        self._state = state

    @property
    def status(self) -> AttemptStatus:
        return self._state.status

    @property
    def traces(self) -> Sequence[Trace]:
        """The Read Traces and Write Batch Traces this attempt produced, in the
        order the work reached the database."""
        return tuple(self._state.traces)

    @property
    def calls(self) -> Sequence[DatabaseCall]:
        """Every call of every trace, flattened — a derived view, not a second
        collection of references."""
        return _CallsView(self._state.traces)

    @property
    def round_trips(self) -> int:
        return sum(trace.round_trips for trace in self._state.traces)

    @property
    def failure(self) -> AttemptFailure | None:
        return self._state.failure

    def __repr__(self) -> str:
        return (
            f"TransactionAttempt(status={self._state.status!r}, "
            f"traces={len(self._state.traces)}, round_trips={self.round_trips})"
        )


class AttemptRecorder:
    """The append-only writer for one Transaction Attempt.

    The two bracketing helpers own the causality rules so no caller restates
    them: a trace is appended once its work has succeeded OR raised, an empty
    one is never appended at all, and an exception escaping a bracket marks that
    bracket's last call as the one an attempt failure references. Opening a
    ``finalization`` batch also moves the attempt's failure phase, because
    nothing an attempt records follows that batch.
    """

    __slots__ = ("_state",)

    def __init__(self, state: _AttemptState) -> None:
        self._state = state

    @contextmanager
    def read_trace(self) -> Generator[TraceRecorder]:
        """Bracket one read, appending its Read Trace when it issued any call."""
        recorder = TraceRecorder()
        errored = False
        try:
            yield recorder
        except BaseException:
            errored = True
            raise
        finally:
            self._close(recorder, recorder.read_trace(), errored=errored)

    @contextmanager
    def write_batch(self, trigger: WriteBatchTrigger) -> Generator[TraceRecorder]:
        """Bracket one flushed write batch, appending its Write Batch Trace when
        it issued any call."""
        if trigger == "finalization":
            self._state.phase = "finalization"
        recorder = TraceRecorder()
        errored = False
        try:
            yield recorder
        except BaseException:
            errored = True
            raise
        finally:
            self._close(recorder, recorder.write_batch_trace(trigger), errored=errored)

    def _close(self, recorder: TraceRecorder, trace: Trace, *, errored: bool) -> None:
        if trace.calls:
            self._state.traces.append(trace)
        if errored:
            self._state.offending_call = recorder.last_call

    def entering_commit(self) -> None:
        """The body and its finalization batch are done; what remains is the
        durability boundary, which records no call of its own."""
        self._state.phase = "commit"

    def committed(self) -> None:
        self._state.status = "committed"

    def failed(self, exc: BaseException) -> None:
        """Roll the attempt back, retaining ``exc``'s detached diagnostic.

        Idempotent in the first caller's favour: the composition root records the
        failure where it knows the phase, and the retry loop only classifies it
        afterwards (:meth:`classify`).
        """
        if self._state.failure is not None:
            return
        self._state.status = "rolled_back"
        self._state.failure = AttemptFailure(
            phase=self._state.phase,
            error_type=type(exc).__name__,
            message=str(exc),
            code=_failure_code(exc),
            retry_eligible=False,
            database_call=self._state.offending_call,
        )

    def classify(self, *, retry_eligible: bool) -> None:
        """Apply the retry classifier's verdict to the recorded failure."""
        failure = self._state.failure
        if failure is None:  # pragma: no cover - the raiser records before the loop classifies
            return
        self._state.failure = AttemptFailure(
            phase=failure.phase,
            error_type=failure.error_type,
            message=failure.message,
            code=failure.code,
            retry_eligible=retry_eligible,
            database_call=failure.database_call,
        )


_WRITE_EFFECT_CODES: Final[dict[type[BaseException], str]] = {
    MissingTargetError: "missing-target",
    StaleWriteError: "stale-write",
    OptimisticLockConflictError: "optimistic-lock-conflict",
    CardinalityCorruptionError: "cardinality-corruption",
}


def _failure_code(exc: BaseException) -> str | None:
    """The stable Parallax or provider code ``exc`` carries, if any.

    A rollback-only refusal is unwrapped to the failure that doomed the
    transaction: the refusal is the boundary reporting a decision already made,
    and its cause is what a reader of the log needs named.
    """
    if isinstance(exc, RollbackOnlyError):
        return None if exc.__cause__ is None else _failure_code(exc.__cause__)
    if isinstance(exc, DatabaseError):
        return exc.native_code
    return _WRITE_EFFECT_CODES.get(type(exc))


@dataclass(slots=True)
class _LogState:
    """One invocation's mutable record, shared by its view and its builder."""

    concurrency: Concurrency
    retry_policy: RetryPolicy
    attempts: list[TransactionAttempt] = field(default_factory=list[TransactionAttempt])
    sealed: bool = False


class ExecutionLog:
    """The read-only record of ONE logical transaction invocation.

    It spans every physical attempt the retry loop ran, is reachable from the
    active transaction while its body runs, seals when the invocation terminates,
    and may outlive the transaction it describes. A joined invocation shares this
    same object rather than opening a second one.
    """

    __slots__ = ("_state",)

    def __init__(self, state: _LogState) -> None:
        self._state = state

    @property
    def concurrency(self) -> Concurrency:
        """The resolved effective participation mode, retained once."""
        return self._state.concurrency

    @property
    def retry_policy(self) -> RetryPolicy:
        return self._state.retry_policy

    @property
    def attempts(self) -> Sequence[TransactionAttempt]:
        return tuple(self._state.attempts)

    @property
    def final_attempt(self) -> TransactionAttempt:
        """The current or latest attempt — looser than a Transaction Result's own
        execution view, which names the committed attempt or refuses."""
        if not self._state.attempts:  # pragma: no cover - the loop opens one before the body runs
            raise TransactionInProgressError("no transaction attempt has opened yet")
        return self._state.attempts[-1]

    @property
    def committed_attempt(self) -> TransactionAttempt | None:
        """The attempt that committed, absent until and unless one does."""
        for attempt in self._state.attempts:
            if attempt.status == "committed":
                return attempt
        return None

    @property
    def is_sealed(self) -> bool:
        """Whether the invocation has terminated, so no further attempt, trace,
        or call can be appended."""
        return self._state.sealed

    @property
    def round_trips(self) -> int:
        """Every attempted call across every attempt, failed calls included and
        begin / commit / rollback excluded."""
        return sum(attempt.round_trips for attempt in self._state.attempts)

    def __repr__(self) -> str:
        return (
            f"ExecutionLog(attempts={len(self._state.attempts)}, "
            f"round_trips={self.round_trips}, sealed={self._state.sealed})"
        )


class ExecutionLogBuilder:
    """The append-only writer behind one :class:`ExecutionLog` view.

    Constructed BEFORE the retry loop, because the log spans every attempt and
    must outlive any one of them, and handed to that loop as its
    :class:`~parallax.core.auto_retry.AttemptObserver`: the loop opens each
    attempt and reports the classifier's verdict, while the composition root
    records where an attempt failed and whether it committed.
    """

    __slots__ = ("_state", "_view")

    def __init__(self, *, concurrency: Concurrency, retry_policy: RetryPolicy) -> None:
        self._state = _LogState(concurrency=concurrency, retry_policy=retry_policy)
        self._view = ExecutionLog(self._state)

    def view(self) -> ExecutionLog:
        """The one stable read-only log object, live from here on and never
        replaced by a snapshot."""
        return self._view

    def attempt_opened(self) -> None:
        """Open an attempt, visible as ``active`` before its body runs."""
        self._state.attempts.append(TransactionAttempt(_AttemptState()))

    def attempt_failed(self, exc: BaseException, *, retry_eligible: bool) -> None:
        self.current.failed(exc)
        self.current.classify(retry_eligible=retry_eligible)

    @property
    def current(self) -> AttemptRecorder:
        """The writer for the attempt now running."""
        return AttemptRecorder(self._current_state())

    def seal(self) -> None:
        """Terminate the invocation's record."""
        self._state.sealed = True

    def _current_state(self) -> _AttemptState:
        if not self._state.attempts:  # pragma: no cover - the loop opens one before the body runs
            raise TransactionInProgressError("no transaction attempt has opened yet")
        return _attempt_state(self._state.attempts[-1])


def _attempt_state(attempt: TransactionAttempt) -> _AttemptState:
    # The view and its recorder share one state object; the view is the only
    # place it is reachable from, and both live in this module.
    return attempt._state  # pyright: ignore[reportPrivateUsage] - the view/recorder pair's shared state, module-private by construction


@dataclass(frozen=True, slots=True)
class TransactionResult[T]:
    """What a transaction invocation returns: the body's value together with the
    whole Execution Log.

    :attr:`execution` is the common view — the committed attempt — so the
    ordinary caller reads one attempt and the interested caller reads the log.
    """

    value: T
    execution_log: ExecutionLog

    @property
    def execution(self) -> TransactionAttempt:
        """The committed attempt.

        A JOINED result shares the outer transaction's live log, so this view is
        unavailable while that transaction is still active
        (:class:`TransactionInProgressError`) and REMAINS unavailable if it later
        rolls back (:class:`TransactionNotCommittedError`).
        """
        committed = self.execution_log.committed_attempt
        if committed is not None:
            return committed
        if self.execution_log.is_sealed:
            raise TransactionNotCommittedError(
                "the transaction this result joined rolled back, so it has no committed "
                "attempt; read `execution_log.attempts` for what each attempt did"
            )
        raise TransactionInProgressError(
            "the transaction this result joined is still active, so no attempt has "
            "committed yet; read `execution_log` for the work recorded so far"
        )
