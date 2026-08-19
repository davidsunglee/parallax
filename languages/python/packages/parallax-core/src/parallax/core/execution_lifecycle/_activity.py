"""The composition seam, the per-root publisher, and the activity scopes that
drive it.

An activity is a SCOPE. Entering it emits Started, leaving it emits Finished
however the body leaves — including under a control-flow or fatal exception no
call site would have handled by hand — so balance is a property of the shape
rather than a rule a reviewer checks. A caller supplies only an outcome that
carries data it alone knows, such as a row count; the failure path is the
scope's own business.

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
from types import TracebackType
from typing import Final, Protocol, runtime_checkable
from uuid import UUID, uuid4

from parallax.core.execution_lifecycle._diagnostics import (
    ActivityFailure,
    CausedFailure,
    DirectFailure,
    FailureDiagnostic,
    database_diagnostic_for,
    diagnostic_for,
)
from parallax.core.execution_lifecycle._errors import (
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProviderError,
)
from parallax.core.execution_lifecycle._events import (
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallKind,
    DatabaseCallOutcome,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    DatabaseWriteCompleted,
    ExecutionEvent,
    ReadCompleted,
    ReadFailed,
    ReadFinished,
    ReadInterface,
    ReadStarted,
    RootExecution,
)
from parallax.core.sql_gen import LoweredStatement


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


class DatabaseCallActivity(Protocol):
    """One attempted round trip's scope.

    The completion methods are how the body reports a count only it knows.
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

    def read_completed(self, returned_rows: int, /) -> None:
        """The query call returned ``returned_rows`` physical rows."""
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
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: str, /
    ) -> DatabaseCallActivity:
        """Open this batch's next Database Call over the exact ``statement``
        presented to the port."""
        ...


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
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: str, /
    ) -> DatabaseCallActivity:
        """Open this Read's next Database Call over the exact ``statement``
        presented to the port."""
        ...


class _InertActivity:
    """The shared do-nothing stand-in for every activity seam.

    One object satisfies every activity Protocol because each opener answers
    itself and every outcome method is empty, which is what lets the default
    path and a declined root run the same code as an observed one while
    allocating nothing, reading no clock, and constructing no event.
    """

    __slots__ = ()

    def __enter__(self) -> _InertActivity:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: str, /
    ) -> _InertActivity:
        return self

    def read_completed(self, returned_rows: int, /) -> None: ...

    def write_completed(self, affected_rows: int, /) -> None: ...


INERT: Final = _InertActivity()
"""The one activity every unobserved operation runs against."""


def _qualified_type(value: object) -> str:
    runtime_type = type(value)
    return f"{runtime_type.__module__}.{runtime_type.__qualname__}"


def _last_resort(execution_id: UUID, sequence: int, activity_id: int) -> None:
    """One sanitized correlation-only line, dropped silently if unavailable.

    The recursion-proof path: it reaches neither the Provider nor the logging
    configuration an application may have wired a Handler into, and carries no
    event, message, statement, or bind — only the three numbers that let the
    dropped report be located. ``sys.__stderr__`` is absent under some embedding
    and packaging topologies, and writing to it can itself fail on a closed or
    detached stream, so both are treated as "no path" rather than as failures of
    the query being observed.
    """
    stream = sys.__stderr__
    if stream is None:
        return
    try:
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
            handler_type=_qualified_type(handler),
            fanout_path=(),
            diagnostic=diagnostic_for(failure),
        )
        try:
            self._provider.report_handler_error(error)
        except Exception:
            _last_resort(self._execution_id, event.sequence, event.activity_id)


class _LiveActivity:
    """What every observed scope owns: its correlation, its place in the tree,
    and the failures its children told it they caused."""

    __slots__ = ("_activity_id", "_attributions", "_parent", "_publisher")

    def __init__(self, publisher: _Publisher, parent: _LiveActivity | None) -> None:
        self._publisher = publisher
        self._parent = parent
        self._activity_id = publisher.open_activity()
        self._attributions: list[tuple[BaseException, int, FailureDiagnostic]] = []

    @property
    def _parent_activity_id(self) -> int | None:
        parent = self._parent
        return None if parent is None else parent._activity_id

    def _attribute(
        self, exc: BaseException, activity_id: int, diagnostic: FailureDiagnostic
    ) -> None:
        """Record that ``activity_id`` produced ``exc``, for a parent that may
        later fail with it.

        The reference is STRONG, which a scope can afford where a retained
        record could not: an attribution lives exactly as long as the activity
        that may still fail with it, so a caller that swallows a failed call
        pins that exception only until the enclosing scope closes. A weak
        reference is not an option in any case — Python's built-in exception
        types do not support one, so a `ValueError` escaping a Database Call
        would fail the attribution rather than being recorded by it.
        """
        self._attributions.append((exc, activity_id, diagnostic))

    def _failure(self, exc: BaseException) -> ActivityFailure:
        """How this activity's failure is attributed.

        Matched by exception IDENTITY, never by which child finished most
        recently: a conversion error that merely unwound past a successful call
        is a direct failure, while the exact exception a child reported names
        that child. Enclosing events reuse the child's own diagnostic object
        rather than rendering the same exception twice.
        """
        for attributed, activity_id, diagnostic in self._attributions:
            if attributed is exc:
                return CausedFailure(diagnostic, activity_id)
        return DirectFailure(diagnostic_for(exc))


class _LiveRead(_LiveActivity):
    """One observed Read: its Database Calls, and its own bracket."""

    __slots__ = ("_interface", "_target")

    _interface: ReadInterface

    def __init__(
        self,
        publisher: _Publisher,
        parent: _LiveActivity | None,
        target: str,
        interface: ReadInterface,
    ) -> None:
        super().__init__(publisher, parent)
        self._target = target
        self._interface = interface

    def __enter__(self) -> _LiveRead:
        publisher = self._publisher
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
        publisher.deliver(
            ReadFinished(
                publisher.execution_id,
                publisher.take_sequence(),
                self._activity_id,
                self._parent_activity_id,
                ReadCompleted() if exc is None else ReadFailed(self._failure(exc)),
            )
        )

    def database_call(
        self, statement: LoweredStatement, kind: DatabaseCallKind, target: str, /
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
        target: str,
    ) -> None:
        super().__init__(publisher, parent)
        self._statement = statement
        self._kind = kind
        self._target = target
        self._outcome: DatabaseCallOutcome | None = None
        self._started_ns = 0

    def __enter__(self) -> _LiveDatabaseCall:
        publisher = self._publisher
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
                parent._attribute(exc, self._activity_id, diagnostic.failure)
        publisher = self._publisher
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

    def read_completed(self, returned_rows: int, /) -> None:
        self._outcome = DatabaseReadCompleted(returned_rows)

    def write_completed(self, affected_rows: int, /) -> None:
        self._outcome = DatabaseWriteCompleted(affected_rows)


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
    provider: ExecutionLifecycleProvider | None, *, target: str, interface: ReadInterface
) -> ReadActivity:
    """The Read root activity for one standalone read, or :data:`INERT`.

    Called after deterministic public preflight, which is the earliest point at
    which the opening event's payload is both complete and validated: an invalid
    target or query therefore creates no root and calls no Provider. With no
    Provider installed nothing at all is allocated here — no UUID, no
    descriptor, no publisher, no counter, and no clock read — and a declining
    Provider costs only the UUID, the descriptor, and the opening call.
    """
    if provider is None:
        return INERT
    execution = RootExecution(uuid4(), "READ")
    handler = _opened(provider, execution)
    if handler is None:
        return INERT
    return _LiveRead(_Publisher(execution.id, provider, handler), None, target, interface)
