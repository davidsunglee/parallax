"""The composition seam, the per-root publisher, and the activity scopes that
drive it.

An activity is a SCOPE. Entering it emits Started, leaving it emits Finished
however the body leaves — including under a control-flow or fatal exception no
call site would have handled by hand — so balance is a property of the shape
rather than of any call site's discipline. A caller supplies only an outcome that
carries data it alone holds, such as the rows a query call returned; the failure
path is the scope's own business.

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
import time
from collections.abc import Callable, Sized
from types import TracebackType
from typing import Final, Protocol, runtime_checkable
from uuid import UUID, uuid4

from parallax.core.auto_retry import retriable_failure
from parallax.core.db_port import CommitFailed, RollbackTrigger
from parallax.core.execution_lifecycle._diagnostics import (
    ActivityFailure,
    CausedFailure,
    DirectFailure,
    FailureDiagnostic,
    database_diagnostic_for,
    diagnostic_for,
    qualified_type,
)
from parallax.core.execution_lifecycle._errors import (
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProviderError,
)
from parallax.core.execution_lifecycle._events import (
    AttemptCommitted,
    AttemptFailure,
    AttemptPhase,
    AttemptRollbackFailed,
    AttemptRolledBack,
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
    RetryPolicy,
    RootExecution,
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


class ReadActivity(Protocol):
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


class TransactionAttemptActivity(Protocol):
    """One physical attempt's scope: what runs inside it, and how it ended.

    The scope brackets the whole ``m-db-port`` transaction call, but the attempt
    itself begins only once the boundary has begun — which only the port body
    knows — so :meth:`begun` is what opens it and a boundary that never began
    runs no attempt at all. Its terminal outcome is likewise a value the port
    reports rather than an exception passing through, which is why an outcome is
    announced here instead of being read off the way the scope was left.
    """

    def __enter__(self) -> TransactionAttemptActivity: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def begun(self) -> None:
        """The boundary began, so this attempt is running."""
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

    def attempt(self) -> TransactionAttemptActivity:
        """The scope this invocation's next physical attempt runs inside."""
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
    """

    __slots__ = ()

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

    def joined_invocation(self) -> _InertActivity:
        return self

    def attempt(self) -> _InertActivity:
        return self

    def read_completed(self, returned_rows: Sized, /) -> None: ...

    def write_completed(self, affected_rows: int, /) -> None: ...

    def begun(self) -> None: ...

    def committed(self) -> None: ...

    def rolled_back(self, trigger: RollbackTrigger, /) -> None: ...

    def rollback_failed(self, trigger: RollbackTrigger, rollback_error: Exception, /) -> None: ...


INERT: Final = _InertActivity()
"""The one activity every unobserved operation runs against."""


def _last_resort(execution_id: UUID, sequence: int, activity_id: int) -> None:
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


class _Publisher:
    """One root's delivery: its sequence and activity counters, its one Handler,
    and the containment around calling it.

    Quarantine is a state of this object rather than of any activity, which is
    what keeps it written once. Fan-out is deliberately NOT here: a
    :class:`ExecutionLifecycleProvider` that composes children answers a
    composite Handler, so child ordering and per-child quarantine stay a Provider
    concern and this class keeps exactly one Handler.
    """

    __slots__ = ("_activities", "_execution_id", "_handler", "_provider", "_sequence")

    def __init__(
        self,
        execution_id: UUID,
        provider: ExecutionLifecycleProvider,
        handler: ExecutionLifecycleHandler,
    ) -> None:
        self._execution_id = execution_id
        self._provider = provider
        self._handler: ExecutionLifecycleHandler | None = handler
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

    def deliver(self, event: ExecutionEvent) -> None:
        """Hand ``event`` to this root's Handler, containing whatever it does.

        An ordinary failure quarantines the Handler for the remainder of the
        root and is reported to its Provider out of band; execution behavior is
        unchanged. A control-flow or fatal exception deactivates delivery for
        the root and propagates unchanged, producing no Handler Error, so the
        operation aborts and cleans up without further events.
        """
        handler = self._handler
        if handler is None:
            return
        try:
            handler.handle(event)
        except Exception as failure:
            self._handler = None
            self._report(event, handler, failure)
        except BaseException:
            self._handler = None
            raise

    def _report(
        self, event: ExecutionEvent, handler: ExecutionLifecycleHandler, failure: Exception
    ) -> None:
        error = ExecutionLifecycleHandlerError(
            execution_id=self._execution_id,
            sequence=event.sequence,
            activity_id=event.activity_id,
            handler_type=qualified_type(handler),
            fanout_path=(),
            diagnostic=diagnostic_for(failure),
        )
        try:
            self._provider.report_handler_error(error)
        except Exception:
            _last_resort(self._execution_id, event.sequence, event.activity_id)


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

        Taken here rather than at construction because an attempt is built
        before the boundary that decides whether it runs at all: a transaction
        that never began must consume no ID, or every activity after it in that
        root would be numbered past a gap nothing explains.
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


class _LiveRead(_LiveActivity):
    """One observed Read: its Database Calls, and its own bracket."""

    __slots__ = ("_interface", "_target")

    _interface: ReadInterface

    def __init__(
        self,
        publisher: _Publisher,
        parent: _LiveActivity | None,
        target: ActivityTarget,
        interface: ReadInterface,
    ) -> None:
        super().__init__(publisher, parent)
        self._target = target.canonical
        self._interface = interface

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


class _LiveTransactionAttempt(_LiveActivity):
    """One observed physical attempt.

    The scope brackets the whole port transaction call, so an attempt that began
    is finished however that call leaves — but the attempt starts only when the
    port body says the boundary began, and ends with the outcome the port
    reported rather than with whatever exception happens to be passing through.
    """

    __slots__ = ("_extra_retriable", "_outcome", "_pre_commit_failure", "_started")

    def __init__(
        self,
        publisher: _Publisher,
        parent: _LiveActivity,
        extra_retriable: Callable[[BaseException], bool] | None,
    ) -> None:
        super().__init__(publisher, parent)
        self._extra_retriable = extra_retriable
        self._started = False
        self._outcome: TransactionAttemptOutcome | None = None
        self._pre_commit_failure: BaseException | None = None

    def __enter__(self) -> _LiveTransactionAttempt:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None:
        publisher = self._publisher
        if not self._started or not publisher.active:
            return
        outcome = self._outcome
        if outcome is None:
            # The port gave up without reporting an outcome, which its contract
            # forbids. The attempt still ran and still has to be accounted for,
            # and rolled back is the honest reading: an adapter owes the boundary
            # an undo before it stops answering for it.
            outcome = AttemptRolledBack(
                self._attempt_failure("CALLBACK", exc if exc is not None else RuntimeError())
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

    def begun(self) -> None:
        publisher = self._publisher
        if not publisher.active:
            return
        self._started = True
        self._open()
        publisher.deliver(
            TransactionAttemptStarted(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
            )
        )

    def committed(self) -> None:
        self._outcome = AttemptCommitted()

    def rolled_back(self, trigger: RollbackTrigger, /) -> None:
        self._outcome = AttemptRolledBack(self._triggered(trigger))

    def rollback_failed(self, trigger: RollbackTrigger, rollback_error: Exception, /) -> None:
        self._outcome = AttemptRollbackFailed(
            self._triggered(trigger), diagnostic_for(rollback_error)
        )

    def read(self, target: ActivityTarget, interface: ReadInterface, /) -> _LiveRead:
        return _LiveRead(self._publisher, self, target, interface)

    def write_batch(self, trigger: WriteBatchTrigger, /) -> _LiveWriteBatch:
        return _LiveWriteBatch(self._publisher, self, trigger)

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
            "COMMIT"
            if isinstance(trigger, CommitFailed)
            else ("PRE_COMMIT" if error is self._pre_commit_failure else "CALLBACK")
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

    def attempt(self) -> _LiveTransactionAttempt:
        return _LiveTransactionAttempt(self._publisher, self, self._extra_retriable)


def _opened(
    provider: ExecutionLifecycleProvider, execution: RootExecution
) -> ExecutionLifecycleHandler | None:
    """Ask ``provider`` to open ``execution``, before any execution work.

    An ordinary failure aborts the operation and is never reinterpreted as a
    decline; a control-flow or fatal exception propagates unchanged, because
    nothing has begun that would need explaining.
    """
    try:
        return provider.open(execution)
    except Exception as failure:
        raise ExecutionLifecycleProviderError(
            "the installed execution lifecycle provider failed to open a root execution, "
            "so the operation was refused before any execution work began"
        ) from failure


def open_read_root(
    provider: ExecutionLifecycleProvider | None,
    *,
    target: ActivityTarget,
    interface: ReadInterface,
) -> ReadActivity:
    """The Read root activity for one standalone read, or :data:`INERT`.

    Called after deterministic public preflight, which is the earliest point at
    which the opening event's payload is both complete and validated: an invalid
    target or query therefore creates no root and calls no Provider. With no
    Provider installed nothing at all is allocated here — no UUID, no
    descriptor, no publisher, no counter, no clock read, and not even the
    target's canonical spelling — and a declining Provider costs only the UUID,
    the descriptor, and the opening call.
    """
    if provider is None:
        return INERT
    execution = RootExecution(uuid4(), "READ")
    handler = _opened(provider, execution)
    if handler is None:
        return INERT
    return _LiveRead(_Publisher(execution.id, provider, handler), None, target, interface)


def open_transaction_root(
    provider: ExecutionLifecycleProvider | None,
    *,
    concurrency: Concurrency,
    retries: int,
    retry_optimistic_conflicts: bool,
    extra_retriable: Callable[[BaseException], bool] | None,
) -> TransactionInvocationActivity:
    """The Transaction Invocation root activity for one outermost ``transact``
    call, or :data:`INERT`.

    Called after the deterministic refusals a joining call is measured by —
    ownership and option conflict — and before the boundary is asked to begin,
    because a begin failure is an OUTCOME of this invocation rather than a
    refusal of it. With no Provider installed nothing at all is allocated here,
    not even the resolved policy the Started transition would carry.

    ``extra_retriable`` is the caller's classification extension, the same one
    the bounded retry loop is given, so the verdict an attempt reports and the
    decision the loop takes read one policy rather than two spellings of it.
    Each side evaluates that policy where it needs the answer — the attempt when
    its outcome is built, the loop when it reaches its decision — so only an
    extension that answers differently for one exception can separate them.
    """
    if provider is None:
        return INERT
    execution = RootExecution(uuid4(), "TRANSACTION_INVOCATION")
    handler = _opened(provider, execution)
    if handler is None:
        return INERT
    return _LiveOuterInvocation(
        _Publisher(execution.id, provider, handler),
        OuterInvocation(concurrency, RetryPolicy(retries, retry_optimistic_conflicts)),
        extra_retriable,
    )
