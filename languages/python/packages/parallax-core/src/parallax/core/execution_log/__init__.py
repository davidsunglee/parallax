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

Reading and writing are separated by construction. Every published RECORD type,
from :class:`ExecutionLog` down to :class:`DatabaseCall`, is a read-only value or
view. The two published protocols are the mirror image — write-only:
:class:`~parallax.core.auto_retry.AttemptObserver` and :class:`CallRecorder` are
what a retry loop and an executor are HANDED, and neither reads anything back, so
recording cannot become a channel an execution observes its own provenance
through. The concrete builders implementing them are deliberately absent from
``__all__`` and are named only where an execution is composed — the transaction
boundary, and the read executors that give a standalone read its own Read Trace.
A view and its builder share one private state object rather than reaching into
each other, which is what lets the view be handed out while the invocation is
still running:

* ``ExecutionLogBuilder`` — one per logical `transact` invocation, constructed
  BEFORE the retry loop because the log outlives any single attempt. It is the
  loop's :class:`~parallax.core.auto_retry.AttemptObserver`.
* ``AttemptRecorder`` — one per physical attempt; brackets each Read Trace and
  Write Batch Trace, and records the attempt's terminal status.
* ``TraceRecorder`` — the Database Call sink one trace is built from, and the
  concrete :class:`CallRecorder` an executor is handed.

Sealing is enforced, not merely announced: once the invocation terminates, every
builder over that record refuses further writes
(:class:`SealedExecutionLogError`), so a retained log describes what the
transaction did rather than whatever a stray reference appended afterwards.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable, Generator, Iterator, Sequence
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
    WriteEffectError,
)

__all__ = [
    "AttemptFailure",
    "AttemptObserver",
    "AttemptStatus",
    "CallCompletion",
    "CallKind",
    "CallRecorder",
    "DatabaseCall",
    "DatabaseCallFailed",
    "ExecutionLog",
    "FailurePhase",
    "ReadCompleted",
    "ReadTrace",
    "RetryPolicy",
    "SealedExecutionLogError",
    "Trace",
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

_ADMITTED_COMPLETION: Final[dict[CallKind, type[ReadCompleted] | type[WriteCompleted]]] = {
    "read": ReadCompleted,
    "write": WriteCompleted,
}


@dataclass(frozen=True, slots=True)
class DatabaseCall:
    """One ATTEMPTED round trip to the database.

    ``kind`` and ``completion`` are ONE closed algebra rather than two
    independent values: a ``read`` admits Read Completed or Database Call
    Failed and a ``write`` admits Write Completed or Database Call Failed, so
    the impossible pairs are refused at construction rather than reaching a
    reader that has no way to interpret them.

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

    def __post_init__(self) -> None:
        admitted = _ADMITTED_COMPLETION[self.kind]
        if isinstance(self.completion, (ReadCompleted, WriteCompleted)) and not isinstance(
            self.completion, admitted
        ):
            raise ValueError(
                f"a {self.kind!r} Database Call admits {admitted.__name__} or "
                f"DatabaseCallFailed, not {type(self.completion).__name__}"
            )


type _AttributableFailure = DatabaseError | WriteEffectError
"""The only two failures a Database Call is allowed to be the cause of: one the
port could not complete, and the Affected Rows Policy verdict on a completed one.

Both are closed families this module already names, so an exception that merely
unwinds through an instrumented bracket — a conversion error, a callback's own
refusal, an interrupt — is not a candidate at all.
"""

type _CallAttribution = tuple[weakref.ref[_AttributableFailure], DatabaseCall]
"""A WEAK reference to the failure a Database Call caused, paired with that call.

Causality is held against the PARTICULAR exception, so a failure that is not that
one — a later unrelated callback error, a commit failure after the caller swallowed
a failed call — names no call however recently a call failed.

The reference is weak because the log is reachable while the transaction body is
still running: a caller that catches a failed call and keeps reading its log must
not thereby pin that exception, its traceback, and every frame and local they
close over. An exception nothing else holds cannot be the one escaping now, so a
released referent attributes nothing and no causality the record could still have
stated is lost.
"""


def _refusal_chain(exc: BaseException) -> Iterator[BaseException]:
    """``exc`` followed by the failure each rollback-only refusal was raised from.

    A refusal is the boundary reporting a decision an EARLIER failure already
    made, so the failure that doomed the transaction is what both the attributed
    call and the failure code must be read from. No other declared cause is
    followed: an exception a caller raised ``from`` one it caught states an
    adjacency that caller chose, and such a failure is exactly the arbitrary
    callback failure that must not inherit the earlier one's call.

    Declared causes may form a cycle, so the walk stops at an exception it has
    already yielded rather than recursing forever.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ if isinstance(current, RollbackOnlyError) else None


def _non_empty(calls: tuple[DatabaseCall, ...], trace: str) -> None:
    if not calls:
        raise ValueError(
            f"a {trace} proves work that reached the database, so it holds at least one "
            "Database Call; a failure before the first call produces no trace at all"
        )


@dataclass(frozen=True, slots=True)
class ReadTrace:
    """The calls one read issued.

    NON-EMPTY by invariant, refused at construction: a trace proves work that
    reached the database, so planning that fails before its first call creates no
    trace at all. A read surfaced to a caller SHARES this object with the attempt
    that issued it — there is never a second record of the same call.
    """

    calls: tuple[DatabaseCall, ...]

    def __post_init__(self) -> None:
        _non_empty(self.calls, "Read Trace")

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

    def __post_init__(self) -> None:
        _non_empty(self.calls, "Write Batch Trace")

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


class SealedExecutionLogError(RuntimeError):
    """A builder was driven after the record it writes to had sealed.

    The log seals when the invocation terminates, so anything appended
    afterwards would belong to a graph every reader has already been handed.
    Refusing turns a silently lost Database Call — or a sealed view that changes
    under a caller — into the defect it is.
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
    equal ones. A call recorded after that sealing would belong to a trace
    already handed out, so it is refused rather than silently dropped.

    The recorder also remembers which of its calls each failure is ABOUT, naming
    the PARTICULAR exception rather than the moment: a call the port could not
    complete attributes the error it failed with, and a completed call attributes
    the Affected Rows Policy verdict that rejected it inside :meth:`enforcing`.
    Nothing else does, so a conversion or planning failure that merely unwinds
    past recorded calls attributes to none — an attempt failure states causality
    it was told about that exception, never causality inferred from one passing
    a bracket that happens to hold calls. Every such pairing is kept, because a
    caller may swallow one failed call and then be doomed by a second: which of
    them the attempt ends up naming is decided by the exception that escapes, not
    by which call failed last.
    """

    __slots__ = ("_attributions", "_calls", "_read_trace", "_sealed", "_write_batch_trace")

    def __init__(self) -> None:
        self._calls: list[DatabaseCall] = []
        self._attributions: list[_CallAttribution] = []
        self._sealed = False
        self._read_trace: ReadTrace | None = None
        self._write_batch_trace: WriteBatchTrace | None = None

    def completed(
        self,
        statement: LoweredStatement,
        kind: CallKind,
        duration_ns: int,
        completion: CallCompletion,
    ) -> None:
        self._append(DatabaseCall(statement, kind, duration_ns, completion))

    def failed(
        self, statement: LoweredStatement, kind: CallKind, duration_ns: int, error: DatabaseError
    ) -> None:
        call = DatabaseCall(
            statement,
            kind,
            duration_ns,
            DatabaseCallFailed(error.category, error.native_code, error.message),
        )
        self._append(call)
        self._attributions.append((weakref.ref(error), call))

    @contextmanager
    def enforcing(self) -> Generator[None]:
        """Bracket post-call enforcement of the call just recorded.

        A shortfall the enforcer rejects leaves the call itself a COMPLETION —
        it reached the database and reported a count — while the rejection is the
        attempt's failure, so the failure must still name that call. Only the
        enforcer's own closed verdict family attributes: anything else that
        unwinds through this bracket is no more ABOUT the call than what unwinds
        through the trace bracket around it.
        """
        try:
            yield
        except WriteEffectError as exc:
            if self._calls:
                self._attributions.append((weakref.ref(exc), self._calls[-1]))
            raise

    @property
    def has_calls(self) -> bool:
        """Whether anything reached the database; a bracket that recorded nothing
        appends no trace."""
        return bool(self._calls)

    @property
    def attributions(self) -> Sequence[_CallAttribution]:
        """Each exception one of this recorder's calls caused, paired with that
        call, in the order they failed; empty when nothing recorded here caused a
        failure."""
        return self._attributions

    def read_trace(self) -> ReadTrace:
        """This recorder's calls as a Read Trace, sealing the recorder."""
        self._sealed = True
        if self._read_trace is None:
            self._read_trace = ReadTrace(tuple(self._calls))
        return self._read_trace

    def write_batch_trace(self, trigger: WriteBatchTrigger) -> WriteBatchTrace:
        """This recorder's calls as a Write Batch Trace with its own trigger,
        sealing the recorder."""
        self._sealed = True
        if self._write_batch_trace is None:
            self._write_batch_trace = WriteBatchTrace(trigger, tuple(self._calls))
        return self._write_batch_trace

    def _append(self, call: DatabaseCall) -> None:
        if self._sealed:
            raise SealedExecutionLogError(
                "this trace has been sealed and handed out; the call recorded now would "
                "belong to a record no reader can reach"
            )
        self._calls.append(call)


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
        if position < 0:
            raise IndexError(index)
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
    attributions: list[_CallAttribution] = field(default_factory=list[_CallAttribution])
    sealed: bool = False


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
    them: a trace is sealed and appended once its work has succeeded OR raised,
    a bracket that reached the database not at all appends nothing and seals
    nothing, and every call a trace recorder attributed carries forward WITH THE
    EXCEPTION it was attributed to. So an empty bracket unwinding around a failed
    one cannot erase the call that failed, a conversion failure after a
    successful call cannot claim it, a caller that swallows a failed call and
    later raises something else — or lets the commit fail — leaves that later
    failure naming no call at all, and a second failed call does not displace the
    first one when the first is what the escaping failure was raised from.

    Attributions are held weakly and released outright once the attempt reaches a
    terminal state, so neither the live record nor the one a caller retains for
    the life of its log holds an exception, a traceback, or a frame the failure
    ran in.

    A ``finalization`` batch also moves the attempt's failure phase, because
    nothing an attempt records follows that batch. The move happens as early as
    the driver announces the batch (:meth:`write_batch_starting`) rather than
    when its bracket opens, so the planning a batch fails in is inside its own
    phase.
    """

    __slots__ = ("_state",)

    def __init__(self, state: _AttemptState) -> None:
        self._state = state

    @contextmanager
    def read_trace(self) -> Generator[TraceRecorder]:
        """Bracket one read, appending its Read Trace when it issued any call."""
        self._ensure_open()
        recorder = TraceRecorder()
        try:
            yield recorder
        finally:
            self._close(recorder, recorder.read_trace)

    def write_batch_starting(self, trigger: WriteBatchTrigger) -> None:
        """Note that a batch with this trigger is about to be PLANNED.

        Planning precedes the batch's first Database Call, so a flush that fails
        planning opens no bracket and appends no trace. Without this notice such
        a failure in the boundary-owned final batch would be recorded in the
        ``body`` phase, which is reserved for callback work, explicit reads, and
        the batches a read forced.
        """
        self._ensure_open()
        self._enter_batch_phase(trigger)

    @contextmanager
    def write_batch(self, trigger: WriteBatchTrigger) -> Generator[TraceRecorder]:
        """Bracket one flushed write batch, appending its Write Batch Trace when
        it issued any call."""
        self._ensure_open()
        self._enter_batch_phase(trigger)
        recorder = TraceRecorder()
        try:
            yield recorder
        finally:
            self._close(recorder, lambda: recorder.write_batch_trace(trigger))

    def _enter_batch_phase(self, trigger: WriteBatchTrigger) -> None:
        # Nothing an attempt records follows the finalization batch, so the
        # phase moves with the batch itself — announced or bracketed, whichever
        # this attempt's driver reaches first.
        if trigger == "finalization":
            self._state.phase = "finalization"

    def _close(self, recorder: TraceRecorder, seal: Callable[[], Trace]) -> None:
        if recorder.has_calls:
            self._state.traces.append(seal())
        self._state.attributions.extend(recorder.attributions)

    def entering_commit(self) -> None:
        """The body and its finalization batch are done; what remains is the
        durability boundary, which records no call of its own."""
        self._ensure_open()
        self._state.phase = "commit"

    def committed(self) -> None:
        self._ensure_open()
        self._state.status = "committed"
        self._state.attributions.clear()

    def failed(self, exc: BaseException) -> None:
        """Roll the attempt back, retaining ``exc``'s detached diagnostic.

        The failure names a Database Call only when ``exc`` — or the failure a
        rollback-only refusal reports a decision already made about — is one a
        trace recorder attributed to that call.

        Idempotent in the first caller's favour: the composition root records the
        failure where it knows the phase, and the retry loop only classifies it
        afterwards (:meth:`classify`).
        """
        self._ensure_open()
        if self._state.failure is not None:
            return
        self._state.status = "rolled_back"
        self._state.failure = AttemptFailure(
            phase=self._state.phase,
            error_type=type(exc).__name__,
            message=str(exc),
            code=_failure_code(exc),
            retry_eligible=False,
            database_call=self._attributed_call(exc),
        )
        self._state.attributions.clear()

    def _attributed_call(self, exc: BaseException) -> DatabaseCall | None:
        # Outward through the refusal chain first, so a failure that is itself
        # attributed names its own call rather than the one that doomed the
        # transaction before it.
        for link in _refusal_chain(exc):
            for attributed, call in self._state.attributions:
                if attributed() is link:
                    return call
        return None

    def classify(self, *, retry_eligible: bool) -> None:
        """Apply the retry classifier's verdict to the recorded failure."""
        self._ensure_open()
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

    def _ensure_open(self) -> None:
        if self._state.sealed:
            raise SealedExecutionLogError(
                "the invocation this attempt belongs to has terminated and its log has "
                "sealed; the attempt's record is what it did and cannot change"
            )


_WRITE_EFFECT_CODES: Final[dict[type[BaseException], str]] = {
    MissingTargetError: "missing-target",
    StaleWriteError: "stale-write",
    OptimisticLockConflictError: "optimistic-lock-conflict",
    CardinalityCorruptionError: "cardinality-corruption",
}


def _failure_code(exc: BaseException) -> str | None:
    """The stable Parallax or provider code ``exc`` carries, if any.

    Read through the same refusal chain the attributed call is: a rollback-only
    refusal is the boundary reporting a decision already made, so the failure
    that doomed the transaction is what a reader of the log needs named.
    """
    for link in _refusal_chain(exc):
        if isinstance(link, RollbackOnlyError):
            continue
        if isinstance(link, DatabaseError):
            return link.native_code
        return _WRITE_EFFECT_CODES.get(type(link))
    return None


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
        self._ensure_open()
        self._state.attempts.append(TransactionAttempt(_AttemptState()))

    def attempt_failed(self, exc: BaseException, *, retry_eligible: bool) -> None:
        self.current.failed(exc)
        self.current.classify(retry_eligible=retry_eligible)

    @property
    def current(self) -> AttemptRecorder:
        """The writer for the attempt now running."""
        return AttemptRecorder(self._current_state())

    def seal(self) -> None:
        """Terminate the invocation's record.

        Sealing reaches every attempt the log holds, not the log alone: a
        recorder handed out while the invocation ran would otherwise keep writing
        into a graph its readers have already been given.
        """
        self._state.sealed = True
        for attempt in self._state.attempts:
            _attempt_state(attempt).sealed = True

    def _current_state(self) -> _AttemptState:
        if not self._state.attempts:  # pragma: no cover - the loop opens one before the body runs
            raise TransactionInProgressError("no transaction attempt has opened yet")
        return _attempt_state(self._state.attempts[-1])

    def _ensure_open(self) -> None:
        if self._state.sealed:
            raise SealedExecutionLogError(
                "this invocation's Execution Log has sealed; it describes one terminated "
                "invocation and no further attempt can join it"
            )


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
