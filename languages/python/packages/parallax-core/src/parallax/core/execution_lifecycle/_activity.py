"""The composition seam, the per-root publisher, and the activity scopes that
drive it.

An activity is a SCOPE. Entering it emits Started, leaving it emits Finished
however the body leaves — including under a control-flow or fatal exception no
call site would have handled by hand — so balance is a property of the shape
rather than of any call site's discipline. A caller supplies only an outcome that
carries data it alone holds, such as the rows a query call returned; the failure
path is the scope's own business.

A Snapshot Stream is the one scope whose Finished may come before its exit. A
delivery that runs out of roots learns so inside the body, and WHEN exhaustion
was discovered is what its case asserts, so the outcome is emitted where it is
learned and the exit finds the activity already finished. Balance is unchanged —
one Finished per Started, whatever ends it first.

Delivery is the publisher's job rather than the activity's, so quarantine and
last-resort reporting are written once instead of once per activity kind, and an
activity stays small enough to be obviously correct.

:data:`INERT` stands in for both the no-Provider default and a declined root, so
no call site carries ``| None`` and none chooses between an early return and an
inline guard. Entering and leaving it allocates nothing, which is what keeps the
scope shape available on the default path at all.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Sized
from dataclasses import dataclass
from types import TracebackType
from typing import ClassVar, Final, Protocol, Self, runtime_checkable
from uuid import UUID, uuid4

from parallax.core.auto_retry import retriable_failure
from parallax.core.db_port import (
    AcquisitionReason,
    CleanupResult,
    CommitFailed,
    ConnectionAcquisitionError,
    IsolationLevel,
    RollbackTrigger,
)
from parallax.core.diagnostics import FailureDiagnostic, diagnostic_for, qualified_type
from parallax.core.execution_lifecycle._diagnostics import (
    ActivityFailure,
    CausedFailure,
    DirectFailure,
    database_diagnostic_for,
)
from parallax.core.execution_lifecycle._errors import (
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProviderError,
    ExecutionLifecycleReentryError,
)
from parallax.core.execution_lifecycle._events import (
    AcquisitionFailed,
    AcquisitionFinished,
    AcquisitionStarted,
    AttemptBeginFailed,
    AttemptCommitted,
    AttemptFailure,
    AttemptPhase,
    AttemptRollbackFailed,
    AttemptRolledBack,
    ConnectionAcquired,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallKind,
    DatabaseCallOutcome,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    DatabaseWriteCompleted,
    ExecutionEvent,
    JoinedInvocation,
    JoinedInvocationRaised,
    JoinedInvocationReturned,
    OuterInvocation,
    OuterInvocationCommitted,
    OuterInvocationFailed,
    ReadCompleted,
    ReadFailed,
    ReadFinished,
    ReadInterface,
    ReadStarted,
    ReleaseFinished,
    ReleaseStarted,
    RetryPolicy,
    RootExecution,
    SnapshotStreamFinished,
    SnapshotStreamOutcome,
    SnapshotStreamStarted,
    StreamBatchCompleted,
    StreamBatchFailed,
    StreamBatchFinished,
    StreamBatchStarted,
    StreamClosedEarly,
    StreamExhausted,
    StreamFailed,
    TransactionAttemptFinished,
    TransactionAttemptOutcome,
    TransactionAttemptStarted,
    TransactionInvocationFinished,
    TransactionInvocationStarted,
    WriteBatchCompleted,
    WriteBatchFailed,
    WriteBatchFinished,
    WriteBatchStarted,
)
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import Concurrency, WriteBatchTrigger


@runtime_checkable
class ExecutionLifecycleHandler(Protocol):
    """One accepted Root Execution's Handler.

    Invoked synchronously and serially for its one root, so per-root counters
    and correlation state belong here while shared, concurrency-safe exporters
    belong to the Provider. A Handler must not retain a borrowed Lowered
    Statement or its binds, and must not use unbounded state.
    """

    def handle(self, event: ExecutionEvent, /) -> None:
        """Receive one transition. An ordinary exception quarantines this
        Handler for the rest of its root and changes no execution semantics."""
        ...


class CompletingHandler:
    """A Handler that composes others and can say whether any of them received
    an event.

    Ordinary delivery answers nothing, and a Handler that swallowed an event is
    indistinguishable from one that exported it: what a Handler does with an
    event is the Handler's business. One question is not — whether a cleanup
    fact reached ANY Handler at all, because the fact has a restricted fallback
    log waiting for it and reporting it twice is as wrong as reporting it never.

    A leaf Handler answers that question by returning from :meth:`handle`
    without raising. A composite cannot: it contains each child's ordinary
    failure by contract, so it returns normally after quarantining every child
    it has. Inheriting this is how such a Handler says so, and the publisher
    resolves it ONCE per root rather than asking per event.

    It is not part of the public Handler contract: an application writes
    :class:`ExecutionLifecycleHandler`, and only the fan-out this package builds
    composes children whose delivery it has to answer for.
    """

    __slots__ = ()

    def handle_completing(self, event: ExecutionEvent, /) -> bool:
        """Deliver ``event`` and answer whether at least one leaf Handler
        beneath this one returned from ``handle`` normally."""
        raise NotImplementedError


@runtime_checkable
class ExecutionLifecycleProvider(Protocol):
    """The composition root's one lifecycle seam.

    ``open`` may run concurrently for different roots, and each accepted root
    gets a distinct Handler. The Provider owns the error reporter as well, which
    is what keeps ``connect`` to one lifecycle argument.
    """

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        """A fresh Handler for ``execution``, or ``None`` to decline it outright.

        Called before execution state, clocks, or database work. An ordinary
        failure aborts the operation through
        :class:`~parallax.core.execution_lifecycle.ExecutionLifecycleProviderError`
        and is never reinterpreted as a decline.
        """
        ...

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        """Receive one detached Handler failure, out of band.

        May be called concurrently. An ordinary failure here is best effort and
        never changes execution.
        """
        ...


class DeliveryState(threading.local):
    """Whether this thread is inside one Handle's lifecycle contexts right now.

    "Delivery" names all three of them — Provider opening, event delivery, and
    error reporting — because they share one answer: work reached through the
    originating Handle while any of them is running is re-entry.

    Per HANDLE and per THREAD, which is what neither half alone gets right. A
    plain instance flag would refuse a legitimate concurrent operation, since
    ``open`` may run for different roots of one Handle at the same time; a
    process-wide flag would refuse an unrelated Handle.
    """

    def __init__(self) -> None:
        """Materialize this thread's slot, which is what makes it free later.

        ``threading.local`` builds a thread's storage on first use and calls
        this again for each new thread, so writing the answer here moves the one
        allocation a thread owes off the first observed operation and onto
        whatever built or first touched the Handle — for the thread that called
        ``connect``, the connection itself.
        """
        self.active = False


@dataclass(frozen=True, slots=True)
class InstalledLifecycle:
    """One Handle's installed Provider, and the re-entry state guarding it.

    The two travel together because neither is usable alone: every lifecycle
    context is a call into ``provider``, and every such call has to be made
    inside ``delivering`` for the Handle's own entry points to be able to refuse
    the work that comes back out of it. Absence of this whole value — rather
    than a ``None`` provider inside it — is the default path.
    """

    provider: ExecutionLifecycleProvider
    delivering: DeliveryState


def installed_lifecycle(
    provider: ExecutionLifecycleProvider | None, /
) -> InstalledLifecycle | None:
    """What a Handle holds for ``provider``, or ``None`` for no Provider at all.

    Called once per Handle, so the per-Handle re-entry state exists exactly when
    there is a Provider whose contexts could produce re-entry.
    """
    return None if provider is None else InstalledLifecycle(provider, DeliveryState())


def refuse_reentry(installed: InstalledLifecycle | None, /) -> None:
    """Refuse an operation reached from inside this Handle's own lifecycle
    contexts, before execution state, clocks, or database work.

    Called at each public entry point of the Handle and of the Transaction it
    opened, which together are what the refusal is scoped to. A Handle with no
    Provider has no lifecycle context to be inside, so it answers from the
    absent installation without reading any state.
    """
    if installed is not None and installed.delivering.active:
        raise ExecutionLifecycleReentryError(
            "this operation was reached from inside a lifecycle context of the same "
            "Parallax handle — a provider opening, a handler receiving an event, or an "
            "error reporter — and is refused before any execution work; observe from a "
            "handler and act on it elsewhere"
        )


class ActivityTarget(Protocol):
    """What an activity reports as the Entity it ran against.

    Structural rather than the metamodel's own identity: this module observes
    `m-sql`, `m-db-port`, `m-db-error`, `m-unit-work` and `m-auto-retry` and
    names no model type. Passing the identity rather than its spelling is what
    keeps the canonical name UNBUILT on the default path — an activity reads
    ``canonical`` only where a Handler is waiting for it, so an unobserved read
    of a namespaced Entity builds no string nobody asked for.
    """

    @property
    def canonical(self) -> str: ...


class DatabaseCallActivity(Protocol):
    """One attempted round trip's scope.

    The completion methods are how the body reports the outcome only it holds.
    Neither announces failure: leaving the scope under an exception is what
    finishes a failed call.
    """

    def __enter__(self) -> DatabaseCallActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def read_completed(self, returned_rows: Sized, /) -> None:
        """The query call returned ``returned_rows``.

        The rows themselves rather than their count, for the same reason
        :class:`ActivityTarget` is passed rather than its spelling: sizing them
        is lifecycle work, and a count outside the interpreter's small-integer
        cache is an object the default path would build for nobody.
        """
        ...

    def write_completed(self, affected_rows: int, /) -> None:
        """The DML call reported ``affected_rows``, however short of what the
        step addressed that count falls."""
        ...


class WriteBatchActivity(Protocol):
    """One flushed Write Batch's scope.

    A batch exists only for a nonempty unit-of-work buffer, starts before
    planning, and completes even when planning reduces it to zero DML, which is
    what lets a planning failure be attributed to the batch rather than to the
    callback around it. Its success outcome carries no data, so leaving the
    scope normally IS its completion.
    """

    def __enter__(self) -> WriteBatchActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: ActivityTarget, /
    ) -> DatabaseCallActivity:
        """Open this batch's next Database Call over the exact ``statement``
        presented to the port."""
        ...

    def enforcing(self, call: DatabaseCallActivity, /) -> EnforcementScope:
        """Bracket the post-call enforcement of what ``call`` returned.

        The one relation causality cannot read off exception identity alone: a
        write call that COMPLETED can still be the cause of this batch's failure,
        because the shortfall in what it affected is only judged afterwards.
        Naming the call explicitly is what keeps proximity — "the last call" —
        from ever being the test.
        """
        ...


class EnforcementScope(Protocol):
    """The bracket a Write Batch attributes a post-call judgement through."""

    def __enter__(self) -> object: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...


class DatabaseCallScope(Protocol):
    """A scope that opens Database Calls, and the whole of what opening one needs.

    A Database Call's parent is a Read, a Write Batch, or a Stream Batch and
    never anything else, so an executor that only issues statements declares
    this rather than any one of them. Naming the narrower thing is what keeps an
    annotation from claiming a Read where another kind of scope opened the call,
    which the lifecycle's own rule that a batch never nests a duplicate Read
    forbids.
    """

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: ActivityTarget, /
    ) -> DatabaseCallActivity:
        """Open this scope's next Database Call over the exact ``statement``
        presented to the port."""
        ...


class ConnectionAcquisitionActivity(Protocol):
    """One acquisition's scope, around the call that asks for a connection.

    It is a SIBLING of the execution activities beside it rather than a lease
    enclosing them: the statements an operation runs are the operation's own
    children, and what the operation asked the adapter for is one more thing it
    did. Nothing opens inside this scope.

    Success is the default and needs no announcement — leaving the scope
    normally is an acquisition that was granted. A failed one announces the
    cleanup its own partial ownership already ran, which is the one fact the
    scope cannot read off the exception.
    """

    def __enter__(self) -> ConnectionAcquisitionActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def call_returned(self) -> None:
        """The acquisition call has come back, one way or the other.

        This is the endpoint the duration is measured to and the moment the hold
        begins, and it is announced rather than read off the way the scope is
        left because what a caller does between the two is not the call: reading
        a failed acquisition's cleanup fact off the resource is the caller's own
        work and belongs to neither interval.
        """
        ...

    def unacquired(self, cleanup_result: CleanupResult | None, /) -> None:
        """What the cleanup a failed acquisition already ran ESTABLISHED, or
        ``None`` where it never owned anything to clean up."""
        ...

    @property
    def held_since_ns(self) -> int | None:
        """When the acquisition call came back, for a scope that measured it.

        ``None`` where nothing is observing, which is what keeps the default
        path free of a clock read. It is the start of the HOLD rather than the
        end of the acquisition's own measurement: everything from here to the
        end of the release is time the operation occupied a connection,
        including this activity's own Finished delivery.
        """
        ...

    @property
    def cleanup_reported(self) -> bool:
        """Whether a Handler completed delivery of this activity's cleanup facts.

        Initial acceptance is not enough and neither is invocation: a return
        acknowledges delivery, and nothing less does. ``False`` where no
        Provider is installed, where every Handler was quarantined, and where
        the activity carried no cleanup fact to deliver — so a caller reads it
        as "report this yourself" rather than as "delivery failed".
        """
        ...


class ConnectionReleaseActivity(Protocol):
    """One release's scope, around the call that gives a connection back.

    Opened only where an acquisition succeeded, so a release in the stream is
    the end of a hold that existed. Its own result is announced rather than read
    off the way the scope was left: what a release established is a value the
    adapter reports, and an exception passing through says nothing about it.
    """

    def __enter__(self) -> ConnectionReleaseActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def call_returned(self) -> None:
        """The release call has come back, one way or the other.

        The endpoint of both the release's own duration and the hold it ends,
        announced for the same reason the acquisition's is: reading what the
        release established off the resource happens after the release.
        """
        ...

    def relinquished(self, cleanup_result: CleanupResult | None, /) -> None:
        """What letting the connection go ESTABLISHED."""
        ...

    @property
    def cleanup_reported(self) -> bool:
        """Whether a Handler completed delivery of this activity's cleanup facts."""
        ...


class ConnectionOwnerActivity(Protocol):
    """An activity that owns one operation's connection for its own lifetime.

    The three that do are a standalone Read, a Transaction Attempt, and a
    standalone Snapshot Stream — the same three that adopt a Model Edition,
    because a connection and a selection are held for exactly one operation.
    Participating work receives both and owns neither, so it never appears here.
    """

    def acquisition(self) -> ConnectionAcquisitionActivity:
        """The scope this activity's one acquisition runs inside."""
        ...

    def release(self, held_since_ns: int | None, /) -> ConnectionReleaseActivity:
        """The scope this activity's one release runs inside, over the hold that
        began at ``held_since_ns``."""
        ...


class ReadActivity(ConnectionOwnerActivity, Protocol):
    """One Read's scope: which children it may open, and nothing else.

    A Read's success outcome carries no data, so leaving the scope normally IS
    its completion and there is no method to forget.
    """

    def __enter__(self) -> ReadActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: ActivityTarget, /
    ) -> DatabaseCallActivity:
        """Open this Read's next Database Call over the exact ``statement``
        presented to the port."""
        ...


class StreamBatchActivity(Protocol):
    """One page's scope: the Database Calls it issues, and nothing else.

    A batch is the page-read activity in its own right and never nests a Read.
    Its success outcome carries no data, so leaving the scope normally IS its
    completion — the discipline a Read and a Write Batch already answer by.

    Constructing one emits nothing, because a page decides where its own batch
    starts: a participating page force-flushes first, and the dependency batch
    that flush runs is an ordered SIBLING of this scope rather than something
    inside it.
    """

    def __enter__(self) -> StreamBatchActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: ActivityTarget, /
    ) -> DatabaseCallActivity:
        """Open this page's next Database Call over the exact ``statement``
        presented to the port."""
        ...


class SnapshotStreamActivity(ConnectionOwnerActivity, Protocol):
    """One stream's scope: its pages, and which of its two non-failure endings
    it reached.

    A Read has one success outcome and therefore no method to forget. A stream
    has two — the delivery ran out, or the caller stopped early — and only the
    stream can tell them apart, so exhaustion is ANNOUNCED and leaving the scope
    without having announced it is Closed Early. That makes the caller-broke
    case the default rather than something a call site must remember to report.

    :meth:`exhausted` finishes the stream where exhaustion was discovered rather
    than deferring it to the scope's own exit, so an observer learns the outcome
    at the moment it became true. A caller error after that point therefore
    cannot rewrite it: the scope has nothing left to finish.
    """

    def __enter__(self) -> SnapshotStreamActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def batch(self) -> StreamBatchActivity:
        """The scope this stream's next requested page is prepared inside."""
        ...

    def exhausted(self) -> None:
        """The delivery ran out, which finishes the stream here."""
        ...


class TransactionAttemptActivity(ConnectionOwnerActivity, Protocol):
    """One physical attempt's scope: what runs inside it, and how it ended.

    Entering the scope is what starts the attempt, and it is entered before the
    ``m-db-port`` transaction call it brackets: the attempt adopted its Model
    Edition already, and whether the boundary then opens is the first thing it
    can report. Its terminal outcome is a value the port reports rather than an
    exception passing through, which is why an outcome is announced here
    instead of being read off the way the scope was left.
    """

    def __enter__(self) -> TransactionAttemptActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def begin_failed(self, error: Exception, /) -> None:
        """The boundary never opened, so the callback never ran and this
        attempt is over; terminal, whatever ``error``'s own category says."""
        ...

    def committed(self) -> None:
        """The attempt committed."""
        ...

    def rolled_back(self, trigger: RollbackTrigger, /) -> None:
        """``trigger`` ended the attempt and the rollback completed."""
        ...

    def rollback_failed(self, trigger: RollbackTrigger, rollback_error: Exception, /) -> None:
        """``trigger`` ended the attempt and undoing it did not complete."""
        ...

    def read(self, target: ActivityTarget, interface: ReadInterface, /) -> ReadActivity:
        """Open a participating Read under this attempt."""
        ...

    def write_batch(self, trigger: WriteBatchTrigger, /) -> WriteBatchActivity:
        """Open the Write Batch one flush of this attempt's buffer runs inside."""
        ...

    def snapshot_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> SnapshotStreamActivity:
        """Open a participating Snapshot Stream under this attempt.

        A stream is a CHILD of the attempt rather than of the pages it runs, so
        the dependency batch a page flushes out is its ordered sibling under the
        same attempt.
        """
        ...

    def joined_invocation(self) -> JoinedInvocationActivity:
        """Open the child Invocation a joining ``transact`` call runs inside."""
        ...


class JoinedInvocationActivity(Protocol):
    """A joining call's scope, which runs no attempt of its own.

    Returning and raising describe the nested callback alone; the physical
    transaction belongs to the invocation this one joined, and finishes with it.
    """

    def __enter__(self) -> JoinedInvocationActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...


class TransactionInvocationActivity(Protocol):
    """The outer invocation's scope — the root activity of a transaction.

    It spans every physical attempt the bounded retry loop runs and finishes
    committed or failed, which is the only pair of outcomes a caller of
    ``transact`` can be handed.
    """

    def __enter__(self) -> TransactionInvocationActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def attempt(self, edition: str, /) -> TransactionAttemptActivity:
        """The scope this invocation's next physical attempt runs inside,
        under the Model Edition that attempt adopted."""
        ...


class _InertActivity:
    """The shared do-nothing stand-in for every activity seam.

    One object satisfies every activity Protocol because each opener answers
    :data:`INERT` and every outcome method is empty, which is what lets the
    default path and a declined root run the same code as an observed one while
    allocating nothing, reading no clock, constructing no event, and leaving
    even an event's payload unread in the values it is handed.

    ``__enter__`` and ``__exit__`` are static because ``with`` reaches a special
    method through the descriptor protocol rather than through the bound-call
    optimization an ordinary ``obj.method(...)`` gets: an instance method would
    therefore have the interpreter materialize a method object at every entry,
    which is exactly the per-scope allocation the default path may not make. A
    ``staticmethod`` descriptor answers the underlying function itself. Being
    static is why they answer the singleton rather than ``self``, which is exact
    because this class exists solely to have :data:`INERT` as its one instance.

    Sameness is identity: :data:`INERT` is the one instance, construction
    answers it rather than making a second, and it stays that one instance
    through a copy, a deep copy, and a pickle round trip.
    """

    __slots__ = ()
    _instance: ClassVar[_InertActivity | None] = None

    def __new__(cls) -> _InertActivity:
        if _InertActivity._instance is None:
            _InertActivity._instance = super().__new__(cls)
        return _InertActivity._instance

    def __init_subclass__(cls) -> None:
        raise TypeError("_InertActivity admits one instance and therefore no subclass")

    def __repr__(self) -> str:
        return "INERT"

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> Self:
        return self

    def __reduce__(self) -> str:
        return "INERT"

    @staticmethod
    def __enter__() -> _InertActivity:
        return INERT

    @staticmethod
    def __exit__(
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: ActivityTarget, /
    ) -> _InertActivity:
        return self

    def enforcing(self, call: DatabaseCallActivity, /) -> _InertActivity:
        return self

    def read(self, target: ActivityTarget, interface: ReadInterface, /) -> _InertActivity:
        return self

    def write_batch(self, trigger: WriteBatchTrigger, /) -> _InertActivity:
        return self

    def snapshot_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> _InertActivity:
        return self

    def batch(self) -> _InertActivity:
        return self

    def joined_invocation(self) -> _InertActivity:
        return self

    def attempt(self, edition: str, /) -> _InertActivity:
        return self

    def acquisition(self) -> _InertActivity:
        return self

    def release(self, held_since_ns: int | None, /) -> _InertActivity:
        return self

    @property
    def held_since_ns(self) -> None:
        """No clock was read, so there is no moment to answer with."""
        return None

    @property
    def cleanup_reported(self) -> bool:
        """Nothing received anything, so a cleanup fact still needs reporting.

        This is what puts the restricted resource log on the default path: the
        failure-only fallback is a deliberate exception to "no Provider means no
        lifecycle work", because a connection nobody could give back is worth
        saying whether or not anyone is watching.
        """
        return False

    def call_returned(self) -> None: ...

    def unacquired(self, cleanup_result: CleanupResult | None, /) -> None: ...

    def relinquished(self, cleanup_result: CleanupResult | None, /) -> None: ...

    def read_completed(self, returned_rows: Sized, /) -> None: ...

    def write_completed(self, affected_rows: int, /) -> None: ...

    def begin_failed(self, error: Exception, /) -> None: ...

    def committed(self) -> None: ...

    def rolled_back(self, trigger: RollbackTrigger, /) -> None: ...

    def rollback_failed(self, trigger: RollbackTrigger, rollback_error: Exception, /) -> None: ...

    def exhausted(self) -> None: ...


INERT: Final = _InertActivity()
"""The one activity every unobserved operation runs against."""


def last_resort(execution_id: UUID, sequence: int, activity_id: int) -> None:
    """One sanitized correlation-only line, dropped silently if unavailable.

    The recursion-proof path: it reaches neither the Provider nor the logging
    configuration an application may have wired a Handler into, and carries no
    event, message, statement, or bind — only the three numbers that let the
    dropped report be located. ``sys.__stderr__`` is absent under some embedding
    and packaging topologies — missing outright as well as ``None`` — and
    writing to it can itself fail on a closed or detached stream, so finding the
    path and using it are contained together and every failure of either is "no
    path" rather than a failure of the query being observed.
    """
    try:
        stream = sys.__stderr__
        if stream is None:
            return
        stream.write(
            "parallax execution lifecycle: reporting a handler failure itself failed "
            f"(execution={execution_id} sequence={sequence} activity={activity_id})\n"
        )
    except Exception:
        return


def report_to(provider: ExecutionLifecycleProvider, error: ExecutionLifecycleHandlerError) -> None:
    """Hand ``error`` to ``provider``, containing an ordinary reporting failure.

    Reporting is best effort by contract: the Handler it describes is already
    quarantined and the execution it was observing has already begun, so a
    reporter that fails ordinarily costs one line on the last-resort path and
    nothing else. A control-flow or fatal exception is not contained — it
    deactivates the root through the caller that raised it.
    """
    try:
        provider.report_handler_error(error)
    except Exception:
        last_resort(error.execution_id, error.sequence, error.activity_id)


class _Publisher:
    """One root's delivery: its sequence and activity counters, its one Handler,
    and the containment around calling it.

    Quarantine is a state of this object rather than of any activity, which is
    what keeps it written once. Fan-out is deliberately NOT here: a
    :class:`ExecutionLifecycleProvider` that composes children answers a
    composite Handler, so child ordering and per-child quarantine stay a Provider
    concern and this class keeps exactly one Handler.
    """

    __slots__ = (
        "_activities",
        "_completing",
        "_execution_id",
        "_handler",
        "_installed",
        "_sequence",
    )

    def __init__(
        self,
        execution_id: UUID,
        installed: InstalledLifecycle,
        handler: ExecutionLifecycleHandler,
    ) -> None:
        self._execution_id = execution_id
        self._installed = installed
        self._handler: ExecutionLifecycleHandler | None = handler
        # Resolved once, because whether a Handler can answer for its children
        # is a property of the composition rather than of an event, and asking
        # per event would put the question on every delivery to pay for the two
        # that read the answer.
        self._completing = (
            handler.handle_completing if isinstance(handler, CompletingHandler) else None
        )
        self._sequence = 0
        self._activities = 0

    @property
    def execution_id(self) -> UUID:
        return self._execution_id

    @property
    def active(self) -> bool:
        """Whether this root still has a Handler that would see an event.

        False once a Handler was quarantined or lifecycle delivery was
        deactivated by a control-flow or fatal exception, and never true again:
        an activity that finds it false does the rest of its lifecycle work not
        at all rather than doing it and dropping the result at delivery. That is
        what makes cleanup after a fatal deactivation genuinely free of further
        event, sequence, and diagnostic work.
        """
        return self._handler is not None

    def take_sequence(self) -> int:
        """The next delivery position, taken immediately before delivery."""
        self._sequence += 1
        return self._sequence

    def open_activity(self) -> int:
        """The next activity ID, assigned by the Started transition that opens it."""
        self._activities += 1
        return self._activities

    def deliver(self, event: ExecutionEvent) -> bool:
        """Hand ``event`` to this root's Handler, containing whatever it does,
        and answer whether a Handler RECEIVED it.

        An ordinary failure quarantines the Handler for the remainder of the
        root and is reported to its Provider out of band; execution behavior is
        unchanged. A control-flow or fatal exception deactivates delivery for
        the root and propagates unchanged, producing no Handler Error, so the
        operation aborts and cleans up without further events.

        The answer exists for the transitions carrying a cleanup fact, which has
        a restricted fallback log waiting for it: reporting it in both places
        would report it twice and in neither would lose it. Initial acceptance
        is not enough and neither is invocation — a Handler that raised ON this
        event received nothing — and a fan-out that contained every one of its
        children's failures answers ``False`` too, which is exactly the case a
        composite's own normal return hides. Every other caller ignores the
        answer, because what a Handler does with an ordinary event is the
        Handler's business.

        A composite that answers ``False`` has no live leaf left and can never
        gain one, so it is quarantined here exactly as a Handler that raised is:
        the rest of the root would otherwise take Activity IDs, sequences and
        clock readings for events with no receiver, which is the very work
        quarantine exists to stop.

        Both the delivery and the reporting that may follow it happen inside
        this Handle's lifecycle context, so an operation the Handler starts back
        through the originating Handle is refused rather than observed. The flag
        is cleared in a ``finally``, which is what keeps a fatal exception from
        leaving the Handle refusing work forever.
        """
        handler = self._handler
        if handler is None:
            return False
        completing = self._completing
        delivering = self._installed.delivering
        delivering.active = True
        try:
            if completing is not None:
                received = completing(event)
                if not received:
                    self._quarantine()
                return received
            handler.handle(event)
        except Exception as failure:
            self._quarantine()
            self._report(event, handler, failure)
            return False
        except BaseException:
            self._quarantine()
            raise
        finally:
            delivering.active = False
        return True

    def _quarantine(self) -> None:
        """Drop every reference this root holds to its Handler.

        ``_completing`` is a bound method, so leaving it set would keep a
        composition and the whole provider tree under it alive for the rest of a
        root that may pause arbitrarily long, for a delivery that can never
        happen again.
        """
        self._handler = None
        self._completing = None

    def _report(
        self, event: ExecutionEvent, handler: ExecutionLifecycleHandler, failure: Exception
    ) -> None:
        report_to(
            self._installed.provider,
            ExecutionLifecycleHandlerError(
                execution_id=self._execution_id,
                sequence=event.sequence,
                activity_id=event.activity_id,
                handler_type=qualified_type(handler),
                fanout_path=(),
                diagnostic=diagnostic_for(failure),
            ),
        )


class _LiveActivity:
    """What every observed scope owns: its correlation, its place in the tree,
    and the one attribution it may later be asked to answer with.

    An attribution pairs one exception value with one of this scope's DIRECT
    children. Exactly two routes report that pair, and temporal proximity is
    never one of them: the child finishes failed with the value, or an explicit
    enforcement relation names an already-finished child for the value the
    enforcement itself raised.
    """

    __slots__ = ("_activity_id", "_attribution", "_parent", "_publisher")

    def __init__(self, publisher: _Publisher, parent: _LiveActivity | None) -> None:
        self._publisher = publisher
        self._parent = parent
        self._activity_id = 0
        self._attribution: tuple[BaseException, int, FailureDiagnostic] | None = None

    def _open(self) -> None:
        """Take this activity's ID, which its own Started transition assigns.

        Taken here rather than at construction because a scope is built before
        the preparation that decides whether it is entered at all: a page whose
        preparation raised before its batch opened ran no batch, and every
        activity numbered after it in that root would otherwise sit past a gap
        nothing explains.
        """
        self._activity_id = self._publisher.open_activity()

    @property
    def _parent_activity_id(self) -> int | None:
        parent = self._parent
        return None if parent is None else parent._activity_id

    def attribute(
        self, exc: BaseException, activity_id: int, diagnostic: FailureDiagnostic
    ) -> None:
        """Pair ``exc`` with the DIRECT child ``activity_id``, for a scope that
        may later fail with that value.

        A report arrives by one of exactly two routes, never by temporal
        proximity: the child finished failed with ``exc``, which is how a failure
        chains up one level at a time, or an explicit enforcement relation named
        an already-finished child for the value the enforcement itself raised —
        a write call that COMPLETED and whose shortfall was judged afterwards.
        The child named is the one this scope answers with for as long as it
        holds the pair, whichever route reported it.

        ONE slot, kept whether a caller went on to handle the failure or not, so
        what a scope keeps does not grow with the failures it has already seen or
        the attempts it has already retried. The reference is STRONG — Python's
        built-in exception types support no weak one, so a `ValueError` escaping
        a Database Call would fail the attribution rather than being recorded by
        it — which bounds retention to one exception and traceback graph rather
        than every failed child's, and leaves that one identity the only failure
        the scope can attribute.

        A report naming a DIFFERENT exception always takes the slot. A second
        report of the same exception takes it only when it names a HIGHER
        activity ID, because among children of one parent a child that reports
        later but started earlier can only be a scope the exception unwound out
        through — a joined invocation reporting after the read it encloses. So
        the slot ends up holding the highest-numbered child that has reported
        the identity it holds SINCE that identity took the slot; a report that
        evicted it takes its earlier reporters out of the running for good.

        What identity alone cannot see: a value raised more than once is one
        identity but several occurrences. A scope that re-raises a value one of
        its finished children reported is attributed to that child rather than
        reporting the raise as its own, and it names the highest-numbered child
        of that run of reports, which need not be the child whose occurrence is
        unwinding now. An exception stashed PAST a later failure escapes this
        only because the later failure is a different object: it evicts the
        slot, and the re-raise is then reported as the scope's own direct
        failure carrying that same exception's diagnostic.
        """
        attributed = self._attributed(exc)
        if attributed is not None and attributed[0] > activity_id:
            return
        self._attribution = (exc, activity_id, diagnostic)

    def _attributed(self, exc: BaseException) -> tuple[int, FailureDiagnostic] | None:
        """The child this activity holds for ``exc`` and that child's diagnostic,
        or ``None`` when the slot holds no failure or holds another exception."""
        attribution = self._attribution
        if attribution is None or attribution[0] is not exc:
            return None
        return attribution[1], attribution[2]

    def _failure(self, exc: BaseException) -> ActivityFailure:
        """How this activity's failure is attributed.

        Matched by exception IDENTITY against the ONE attribution this scope
        holds. A conversion error that merely unwound past a successful call is
        a direct failure however recently a child failed, and so is a value some
        report did pair with a child once a different failure took the slot: the
        failure is Caused exactly while the slot still holds that value, and it
        names whichever child the slot ended up on. Enclosing events reuse that
        child's own diagnostic object rather than rendering the same exception
        twice.
        """
        attributed = self._attributed(exc)
        if attributed is not None:
            activity_id, diagnostic = attributed
            return CausedFailure(diagnostic, activity_id)
        return DirectFailure(self._rendered(exc))

    def _rendered(self, exc: BaseException) -> FailureDiagnostic:
        """``exc`` projected for an activity with no child of its own to name.

        A joined invocation is the SIBLING of the read it encloses rather than
        its parent, so an exception leaving that read unwinds out through a
        scope owning no attribution for it. The shared parent holds one, and a
        higher activity ID than this scope's is exactly the case of a child that
        started after this scope did and therefore ran inside it: reusing its
        diagnostic renders the exception once rather than once per scope it
        unwinds through.
        """
        parent = self._parent
        if parent is not None:
            attributed = parent._attributed(exc)
            if attributed is not None and attributed[0] > self._activity_id:
                return attributed[1]
        return diagnostic_for(exc)

    def _propagated(self, exc: BaseException) -> ActivityFailure:
        """This activity's failure, told to its parent as the parent's own cause.

        Each level names its own DIRECT child, and every level reuses the one
        diagnostic the deepest failing activity rendered, so an enclosing failure
        costs no second render and the chain stays walkable one link at a time.
        """
        failure = self._failure(exc)
        parent = self._parent
        if parent is not None:
            parent.attribute(exc, self._activity_id, failure.diagnostic)
        return failure


class _LiveConnectionOwner(_LiveActivity):
    """An observed scope that owns one operation's connection.

    The two openers are written once here because a standalone Read, a
    Transaction Attempt, and a standalone Snapshot Stream answer them
    identically: an acquisition and a release are the owner's own children
    whichever of the three is asking, and the difference between the three is
    the shape of the operation between them rather than either end of it.

    A release is opened only over a hold that was measured. Where it was not,
    nothing observed the acquisition that opened the hold either — delivery for
    this root had already stopped — so the release is inert rather than a live
    scope with no beginning to report.
    """

    __slots__ = ()

    def acquisition(self) -> _LiveAcquisition:
        return _LiveAcquisition(self._publisher, self)

    def release(self, held_since_ns: int | None, /) -> ConnectionReleaseActivity:
        if held_since_ns is None:
            return INERT
        return _LiveRelease(self._publisher, self, held_since_ns)


class _LiveRead(_LiveConnectionOwner):
    """One observed Read: its Database Calls, and its own bracket.

    A root Read states the edition it adopted; a participating one states none,
    because the attempt it hangs under already did.
    """

    __slots__ = ("_edition", "_interface", "_target")

    _interface: ReadInterface

    def __init__(
        self,
        publisher: _Publisher,
        parent: _LiveActivity | None,
        target: ActivityTarget,
        interface: ReadInterface,
        edition: str | None,
    ) -> None:
        super().__init__(publisher, parent)
        self._target = target.canonical
        self._interface = interface
        self._edition = edition

    def __enter__(self) -> _LiveRead:
        publisher = self._publisher
        if not publisher.active:
            return self
        self._open()
        publisher.deliver(
            ReadStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                self._target,
                self._interface,
                self._edition,
            )
        )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        publisher = self._publisher
        if not publisher.active:
            return
        publisher.deliver(
            ReadFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                ReadCompleted() if exc is None else ReadFailed(self._propagated(exc)),
            )
        )

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: ActivityTarget, /
    ) -> _LiveDatabaseCall:
        return _LiveDatabaseCall(self._publisher, self, statement, kind, target)


class _LiveDatabaseCall(_LiveActivity):
    """One observed round trip, timed around the port invocation alone.

    The clock starts only after Started has been delivered and stops before
    Finished is constructed, so a slow Handler cannot inflate the duration of
    every call it observes.
    """

    __slots__ = ("_kind", "_outcome", "_started_ns", "_statement", "_target")

    _kind: DatabaseCallKind

    def __init__(
        self,
        publisher: _Publisher,
        parent: _LiveActivity,
        statement: LoweredStatement,
        kind: DatabaseCallKind,
        target: ActivityTarget,
    ) -> None:
        super().__init__(publisher, parent)
        self._statement = statement
        self._kind = kind
        self._target = target.canonical
        self._outcome: DatabaseCallOutcome | None = None
        self._started_ns = 0

    def __enter__(self) -> _LiveDatabaseCall:
        publisher = self._publisher
        if not publisher.active:
            return self
        self._open()
        publisher.deliver(
            DatabaseCallStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                self._target,
                self._kind,
                self._statement,
            )
        )
        if publisher.active:
            self._started_ns = time.perf_counter_ns()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        publisher = self._publisher
        if not publisher.active:
            return
        duration_ns = time.perf_counter_ns() - self._started_ns
        outcome = self._outcome
        if outcome is None:
            if exc is None:  # pragma: no cover - a completed call records its count
                raise RuntimeError(
                    "a Database Call scope left normally without reporting a completion; "
                    "the call sites record the driver's count on the statement after the "
                    "port returns"
                )
            diagnostic = database_diagnostic_for(exc)
            outcome = DatabaseCallFailed(diagnostic)
            parent = self._parent
            if parent is not None:
                parent.attribute(exc, self._activity_id, diagnostic.failure)
        publisher.deliver(
            DatabaseCallFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                self._statement,
                duration_ns,
                outcome,
            )
        )

    def read_completed(self, returned_rows: Sized, /) -> None:
        self._outcome = DatabaseReadCompleted(len(returned_rows))

    def write_completed(self, affected_rows: int, /) -> None:
        self._outcome = DatabaseWriteCompleted(affected_rows)


class _LiveEnforcement:
    """The bracket that lets a COMPLETED call be named as what caused a batch's
    failure.

    It records nothing on the way in: an enforcement that passes leaves the batch
    exactly as it found it, and only a judgement that raised is worth attributing.
    """

    __slots__ = ("_batch", "_call_id")

    def __init__(self, batch: _LiveWriteBatch, call_id: int) -> None:
        self._batch = batch
        self._call_id = call_id

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        if exc is None:
            return
        self._batch.attribute(exc, self._call_id, diagnostic_for(exc))


class _LiveAcquisition(_LiveActivity):
    """One observed acquisition, timed around the acquisition call alone.

    The clock starts after Started has been delivered and stops where the
    acquisition call comes back, exactly as a Database Call's does. Both
    endpoints are taken at the call rather than at the scope's own boundaries,
    so neither this activity's deliveries nor the caller's reading of a failed
    acquisition's cleanup fact is inside what the duration reports. The stopping
    reading is also where the HOLD starts, so everything after it — this
    activity's own Finished delivery, the Handlers that see it, the work the
    operation goes on to do — is time the connection was occupied.

    ``duration_ns`` measures a composition-level call rather than physical
    checkout: what it brackets is asking the adapter for a connection and
    getting an answer, which for a failed acquisition includes the cleanup the
    adapter ran over whatever it had taken.
    """

    __slots__ = ("_cleanup_result", "_completed_ns", "_held_since_ns", "_reported", "_started_ns")

    def __init__(self, publisher: _Publisher, parent: _LiveActivity) -> None:
        super().__init__(publisher, parent)
        self._started_ns = 0
        self._completed_ns = 0
        self._held_since_ns: int | None = None
        self._cleanup_result: CleanupResult | None = None
        self._reported = False

    @property
    def held_since_ns(self) -> int | None:
        return self._held_since_ns

    @property
    def cleanup_reported(self) -> bool:
        return self._reported

    def call_returned(self) -> None:
        if self._publisher.active:
            self._completed_ns = time.perf_counter_ns()

    def unacquired(self, cleanup_result: CleanupResult | None, /) -> None:
        self._cleanup_result = cleanup_result

    def __enter__(self) -> _LiveAcquisition:
        publisher = self._publisher
        if not publisher.active:
            return self
        self._open()
        publisher.deliver(
            AcquisitionStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
            )
        )
        if publisher.active:
            self._started_ns = time.perf_counter_ns()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        publisher = self._publisher
        if not publisher.active:
            return
        completed_ns = self._completed_ns
        self._held_since_ns = completed_ns
        duration_ns = completed_ns - self._started_ns
        if exc is None:
            publisher.deliver(
                AcquisitionFinished(
                    publisher.execution_id,
                    publisher.take_sequence(),
                    self._activity_id,
                    self._parent_activity_id,
                    duration_ns,
                    ConnectionAcquired(),
                )
            )
            return
        # Only a failed acquisition carries a cleanup fact, so only a failed one
        # can have delivered one. The answer comes from the delivery itself
        # rather than from whether the Handler is still live afterwards: a
        # Handler that raised ON this event received nothing.
        cleanup_result = self._cleanup_result
        delivered = publisher.deliver(
            AcquisitionFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                duration_ns,
                AcquisitionFailed(_acquisition_reason(exc), self._propagated(exc), cleanup_result),
            )
        )
        self._reported = delivered and cleanup_result is not None


class _LiveRelease(_LiveActivity):
    """One observed release, timed around the release call alone.

    It reports what letting go established and never anything about the outcome
    above it: a release problem is a fact about a resource, and the read that
    published, the stream that exhausted, or the transaction that committed
    keeps what it established. Its own failure route is therefore not an outcome
    at all — there is one Finished transition, carrying whatever the adapter
    reported, including nothing.
    """

    __slots__ = ("_cleanup_result", "_completed_ns", "_held_since_ns", "_reported", "_started_ns")

    def __init__(self, publisher: _Publisher, parent: _LiveActivity, held_since_ns: int) -> None:
        super().__init__(publisher, parent)
        self._held_since_ns = held_since_ns
        self._started_ns = 0
        self._completed_ns = 0
        self._cleanup_result: CleanupResult | None = None
        self._reported = False

    @property
    def cleanup_reported(self) -> bool:
        return self._reported

    def call_returned(self) -> None:
        if self._publisher.active:
            self._completed_ns = time.perf_counter_ns()

    def relinquished(self, cleanup_result: CleanupResult | None, /) -> None:
        self._cleanup_result = cleanup_result

    def __enter__(self) -> _LiveRelease:
        publisher = self._publisher
        if not publisher.active:
            return self
        self._open()
        publisher.deliver(
            ReleaseStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
            )
        )
        if publisher.active:
            self._started_ns = time.perf_counter_ns()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        del exc
        publisher = self._publisher
        if not publisher.active:
            return
        completed_ns = self._completed_ns
        cleanup_result = self._cleanup_result
        delivered = publisher.deliver(
            ReleaseFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                completed_ns - self._started_ns,
                completed_ns - self._held_since_ns,
                cleanup_result,
            )
        )
        self._reported = delivered and cleanup_result is not None


def _acquisition_reason(exc: BaseException) -> AcquisitionReason:
    """Why ``exc`` says no connection was granted.

    An adapter states the reason on its own refusal. Anything else escaping an
    acquisition — a Provider that failed, an interrupt, a defect in the adapter
    — took no connection either, and ``preparation_failed`` is the honest
    reading of it: establishing execution access is what did not happen.
    """
    if isinstance(exc, ConnectionAcquisitionError):
        return exc.reason
    return "preparation_failed"


class _LiveWriteBatch(_LiveActivity):
    """One observed flush: its Database Calls, and the enforcement that follows
    each of them."""

    __slots__ = ("_attempt", "_trigger")

    _trigger: WriteBatchTrigger

    def __init__(
        self, publisher: _Publisher, parent: _LiveTransactionAttempt, trigger: WriteBatchTrigger
    ) -> None:
        super().__init__(publisher, parent)
        self._attempt = parent
        self._trigger = trigger

    def __enter__(self) -> _LiveWriteBatch:
        publisher = self._publisher
        if not publisher.active:
            return self
        self._open()
        publisher.deliver(
            WriteBatchStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                self._trigger,
            )
        )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        publisher = self._publisher
        if not publisher.active:
            return
        if exc is None:
            outcome: WriteBatchCompleted | WriteBatchFailed = WriteBatchCompleted()
        else:
            outcome = WriteBatchFailed(self._propagated(exc))
            if self._trigger == "pre_commit":
                self._attempt.pre_commit_failed(exc)
        publisher.deliver(
            WriteBatchFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                outcome,
            )
        )

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: ActivityTarget, /
    ) -> _LiveDatabaseCall:
        return _LiveDatabaseCall(self._publisher, self, statement, kind, target)

    def enforcing(self, call: DatabaseCallActivity, /) -> _LiveEnforcement:
        return _LiveEnforcement(self, call._activity_id if isinstance(call, _LiveActivity) else 0)


class _LiveStreamBatch(_LiveActivity):
    """One observed page: its Database Calls, and its own bracket.

    Built where the page loop decides to run a page and OPENED where the page's
    own preparation puts it, which for a participating stream is after the
    force-flush. Construction takes no Activity ID for the same reason an attempt
    does not: a page whose preparation raised before the batch opened ran no
    batch, and every activity numbered after it in that root would otherwise sit
    past a gap nothing explains.
    """

    __slots__ = ()

    def __enter__(self) -> _LiveStreamBatch:
        publisher = self._publisher
        if not publisher.active:
            return self
        self._open()
        publisher.deliver(
            StreamBatchStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
            )
        )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        publisher = self._publisher
        if not publisher.active:
            return
        publisher.deliver(
            StreamBatchFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                StreamBatchCompleted() if exc is None else StreamBatchFailed(self._propagated(exc)),
            )
        )

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: ActivityTarget, /
    ) -> _LiveDatabaseCall:
        return _LiveDatabaseCall(self._publisher, self, statement, kind, target)


class _LiveSnapshotStream(_LiveConnectionOwner):
    """One observed stream: its pages, and the one ending it reached.

    The ending is delivered by whichever of the two routes reaches it first —
    :meth:`exhausted` where the delivery ran out, the scope's own exit
    otherwise — and only ever once. That is what lets exhaustion finish at the
    moment it is discovered while a caller error arriving afterwards finds
    nothing left to rewrite.

    It holds no page state at all, so what one stream costs is the same whether
    it delivered one page or a million. A root stream states the edition it
    adopted at entry; a participating one states none, because the attempt it
    hangs under already did.
    """

    __slots__ = ("_batch_size", "_edition", "_finished", "_interface", "_target")

    _interface: ReadInterface

    def __init__(
        self,
        publisher: _Publisher,
        parent: _LiveActivity | None,
        target: ActivityTarget,
        interface: ReadInterface,
        batch_size: int,
        edition: str | None,
    ) -> None:
        super().__init__(publisher, parent)
        self._target = target.canonical
        self._interface = interface
        self._batch_size = batch_size
        self._edition = edition
        self._finished = False

    def __enter__(self) -> _LiveSnapshotStream:
        publisher = self._publisher
        if not publisher.active:
            return self
        self._open()
        publisher.deliver(
            SnapshotStreamStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                self._target,
                self._interface,
                self._batch_size,
                self._edition,
            )
        )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        self._finish(StreamClosedEarly() if exc is None else StreamFailed(self._propagated(exc)))

    def batch(self) -> _LiveStreamBatch:
        return _LiveStreamBatch(self._publisher, self)

    def exhausted(self) -> None:
        """Finish the stream here, at the point exhaustion was discovered.

        The scope's own exit then has nothing left to emit, so an early close of
        an already-exhausted delivery is not a second outcome.
        """
        self._finish(StreamExhausted())

    def _finish(self, outcome: SnapshotStreamOutcome) -> None:
        publisher = self._publisher
        if self._finished or not publisher.active:
            return
        self._finished = True
        publisher.deliver(
            SnapshotStreamFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                outcome,
            )
        )


class _LiveTransactionAttempt(_LiveConnectionOwner):
    """One observed physical attempt, under the edition it adopted.

    The scope is entered before the port transaction call it brackets and
    finished however that call leaves — with the outcome the port reported
    rather than with whatever exception happens to be passing through. The
    edition is fixed at construction because adoption precedes the attempt:
    nothing between construction and entry can fail, so entry is what starts
    it and consumes its ID.
    """

    __slots__ = ("_edition", "_extra_retriable", "_outcome", "_pre_commit_failure")

    def __init__(
        self,
        publisher: _Publisher,
        parent: _LiveActivity,
        extra_retriable: Callable[[BaseException], bool] | None,
        edition: str,
    ) -> None:
        super().__init__(publisher, parent)
        self._extra_retriable = extra_retriable
        self._edition = edition
        self._outcome: TransactionAttemptOutcome | None = None
        self._pre_commit_failure: BaseException | None = None

    def __enter__(self) -> _LiveTransactionAttempt:
        publisher = self._publisher
        if not publisher.active:
            return self
        self._open()
        publisher.deliver(
            TransactionAttemptStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                self._edition,
            )
        )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        publisher = self._publisher
        if not publisher.active:
            return
        outcome = self._outcome
        if outcome is None:
            # The port gave up without reporting an outcome, which its contract
            # forbids. The attempt still ran and still has to be accounted for,
            # and rolled back is the honest reading: an adapter owes the boundary
            # an undo before it stops answering for it.
            outcome = AttemptRolledBack(
                self._attempt_failure("callback", exc if exc is not None else RuntimeError())
            )
        publisher.deliver(
            TransactionAttemptFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                outcome,
            )
        )

    def begin_failed(self, error: Exception, /) -> None:
        """Finish with the boundary's own refusal, told to the invocation as
        the invocation's cause.

        Attributed through :meth:`_propagated` rather than rendered directly,
        because the attempt may hold a child for this very failure: an
        Acquisition that could not produce a connection reports to the attempt
        under its own Activity ID, so the attempt names it. A boundary that
        refused to open on a connection this attempt did acquire is the
        attempt's own direct failure. Either way the invocation above names
        this attempt, under the ordinary chaining rule.

        It is still not an Attempt Failure: there is no phase inside an attempt
        that never opened its boundary to locate, and no classifier verdict to
        report, because it is terminal by rule.
        """
        if not self._publisher.active:
            return
        self._outcome = AttemptBeginFailed(self._propagated(error))

    def committed(self) -> None:
        self._outcome = AttemptCommitted()

    def rolled_back(self, trigger: RollbackTrigger, /) -> None:
        self._outcome = AttemptRolledBack(self._triggered(trigger))

    def rollback_failed(self, trigger: RollbackTrigger, rollback_error: Exception, /) -> None:
        self._outcome = AttemptRollbackFailed(
            self._triggered(trigger), diagnostic_for(rollback_error)
        )

    def read(self, target: ActivityTarget, interface: ReadInterface, /) -> _LiveRead:
        return _LiveRead(self._publisher, self, target, interface, None)

    def write_batch(self, trigger: WriteBatchTrigger, /) -> _LiveWriteBatch:
        return _LiveWriteBatch(self._publisher, self, trigger)

    def snapshot_stream(
        self, target: ActivityTarget, interface: ReadInterface, batch_size: int, /
    ) -> _LiveSnapshotStream:
        return _LiveSnapshotStream(self._publisher, self, target, interface, batch_size, None)

    def joined_invocation(self) -> _LiveJoinedInvocation:
        return _LiveJoinedInvocation(self._publisher, self)

    def pre_commit_failed(self, exc: BaseException) -> None:
        """Remember what the pre-commit batch failed with.

        The port reports a body failure without saying which half of the body
        produced it, and the two halves are different phases: the callback the
        caller wrote, and the automatic batch that follows it. Matching by
        exception identity is what tells them apart without the port having to
        know there are two.
        """
        self._pre_commit_failure = exc

    def _triggered(self, trigger: RollbackTrigger) -> AttemptFailure:
        """The attempt failure ``trigger`` describes.

        The value carried up is the triggering error rather than whatever
        composition goes on to raise from it, so a rollback failure — which
        surfaces as an error of its own — leaves the invocation reporting that
        error directly instead of pointing at an attempt it does not describe.
        """
        error = trigger.error
        phase: AttemptPhase = (
            "commit"
            if isinstance(trigger, CommitFailed)
            else ("pre_commit" if error is self._pre_commit_failure else "callback")
        )
        return self._attempt_failure(phase, error)

    def _attempt_failure(self, phase: AttemptPhase, error: BaseException) -> AttemptFailure:
        """This attempt's failure, reported to the invocation as the invocation's
        own cause.

        Every attempt that finishes failed reports its value up under its own
        Activity ID, the fabricated failure of a port that stopped answering for
        the boundary included: an invocation that goes on to fail with that value
        names the attempt rather than claiming the failure as its own.
        """
        failure = AttemptFailure(
            phase,
            self._failure(error),
            retriable_failure(error)
            or (self._extra_retriable is not None and self._extra_retriable(error)),
        )
        parent = self._parent
        if parent is not None:
            parent.attribute(error, self._activity_id, failure.failure.diagnostic)
        return failure


class _LiveJoinedInvocation(_LiveActivity):
    """One observed joining call: the nested callback, and nothing physical."""

    __slots__ = ()

    def __enter__(self) -> _LiveJoinedInvocation:
        publisher = self._publisher
        if not publisher.active:
            return self
        self._open()
        publisher.deliver(
            TransactionInvocationStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                JoinedInvocation(),
            )
        )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        publisher = self._publisher
        if not publisher.active:
            return
        publisher.deliver(
            TransactionInvocationFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                JoinedInvocationReturned()
                if exc is None
                else JoinedInvocationRaised(self._propagated(exc)),
            )
        )


class _LiveOuterInvocation(_LiveActivity):
    """One observed outer invocation: the root activity of a transaction.

    The one scope that does not ask whether delivery is still live before
    opening: it is entered immediately after the Provider accepted the root, so
    there is nothing that could have deactivated delivery in between.
    """

    __slots__ = ("_extra_retriable", "_invocation")

    def __init__(
        self,
        publisher: _Publisher,
        invocation: OuterInvocation,
        extra_retriable: Callable[[BaseException], bool] | None,
    ) -> None:
        super().__init__(publisher, None)
        self._invocation = invocation
        self._extra_retriable = extra_retriable

    def __enter__(self) -> _LiveOuterInvocation:
        publisher = self._publisher
        self._open()
        publisher.deliver(
            TransactionInvocationStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                None,
                self._invocation,
            )
        )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        publisher = self._publisher
        if not publisher.active:
            return
        publisher.deliver(
            TransactionInvocationFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                None,
                OuterInvocationCommitted()
                if exc is None
                else OuterInvocationFailed(self._failure(exc)),
            )
        )

    def attempt(self, edition: str, /) -> _LiveTransactionAttempt:
        return _LiveTransactionAttempt(self._publisher, self, self._extra_retriable, edition)


def _opened(
    installed: InstalledLifecycle, execution: RootExecution
) -> ExecutionLifecycleHandler | None:
    """Ask the installed Provider to open ``execution``, before any execution work.

    An ordinary failure aborts the operation and is never reinterpreted as a
    decline; a control-flow or fatal exception propagates unchanged, because
    nothing has begun that would need explaining. Opening is a lifecycle context
    like delivery is, so a Provider that calls back through this Handle is
    refused and that refusal becomes the Provider Error's own cause.
    """
    delivering = installed.delivering
    delivering.active = True
    try:
        return installed.provider.open(execution)
    except Exception as failure:
        raise ExecutionLifecycleProviderError(
            "the installed execution lifecycle provider failed to open a root execution, "
            "so the operation was refused before any execution work began"
        ) from failure
    finally:
        delivering.active = False


def open_read_root(
    installed: InstalledLifecycle | None,
    *,
    target: ActivityTarget,
    interface: ReadInterface,
    edition: str,
) -> ReadActivity:
    """The Read root activity for one standalone read, or :data:`INERT`.

    Called after deterministic public preflight, which is the earliest point at
    which the opening event's payload is both complete and validated: an invalid
    target or query therefore creates no root and calls no Provider. ``edition``
    is the Model Edition the read adopted before opening, which its Started
    transition states. With no Provider installed nothing at all is allocated
    here — no UUID, no descriptor, no publisher, no counter, no clock read, and
    not even the target's canonical spelling — and a declining Provider costs
    only the UUID, the descriptor, and the opening call, made inside this
    Handle's re-entry bracket.
    """
    if installed is None:
        return INERT
    execution = RootExecution(uuid4(), "read")
    handler = _opened(installed, execution)
    if handler is None:
        return INERT
    return _LiveRead(_Publisher(execution.id, installed, handler), None, target, interface, edition)


def open_snapshot_stream_root(
    installed: InstalledLifecycle | None,
    *,
    target: ActivityTarget,
    interface: ReadInterface,
    batch_size: int,
    edition: str,
) -> SnapshotStreamActivity:
    """The Snapshot Stream root activity for one standalone stream, or
    :data:`INERT`.

    Called at context entry, after the deterministic gate and the page plan the
    stream is refused by: an invalid target, an invalid query, or an order the
    continuation cannot compose therefore creates no root and calls no Provider,
    and a stream nobody entered creates none either. ``edition`` is the Model
    Edition the stream adopted at entry, which its Started transition states.
    With no Provider installed nothing at all is allocated here, the page size
    and the edition the Started transition would carry included.
    """
    if installed is None:
        return INERT
    execution = RootExecution(uuid4(), "snapshot_stream")
    handler = _opened(installed, execution)
    if handler is None:
        return INERT
    return _LiveSnapshotStream(
        _Publisher(execution.id, installed, handler), None, target, interface, batch_size, edition
    )


def open_transaction_root(
    installed: InstalledLifecycle | None,
    *,
    concurrency: Concurrency,
    retries: int,
    retry_optimistic_conflicts: bool,
    isolation: IsolationLevel | None,
    extra_retriable: Callable[[BaseException], bool] | None,
) -> TransactionInvocationActivity:
    """The Transaction Invocation root activity for one outermost ``transact``
    call, or :data:`INERT`.

    Called after the deterministic refusals a joining call is measured by —
    ownership and option conflict — and before any attempt adopts an edition,
    because a begin failure is an OUTCOME of an attempt of this invocation
    rather than a refusal of it. With no Provider installed nothing at all is allocated here,
    not even the resolved policy the Started transition would carry.

    ``extra_retriable`` is the caller's classification extension, the same one
    the bounded retry loop is given, so the verdict an attempt reports and the
    decision the loop takes read one policy rather than two spellings of it.
    Each side evaluates that policy where it needs the answer — the attempt when
    its outcome is built, the loop when it reaches its decision — so only an
    extension that answers differently for one exception can separate them.
    """
    if installed is None:
        return INERT
    execution = RootExecution(uuid4(), "transaction_invocation")
    handler = _opened(installed, execution)
    if handler is None:
        return INERT
    return _LiveOuterInvocation(
        _Publisher(execution.id, installed, handler),
        OuterInvocation(concurrency, RetryPolicy(retries, retry_optimistic_conflicts), isolation),
        extra_retriable,
    )
