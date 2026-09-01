"""The standard-library logging built-in, and the only ``import logging`` here.

:class:`LoggingLifecycleProvider` accepts a Logger an application already
configured and owns nothing else — no queue, listener, sink, overflow policy,
flush, or shutdown. Asynchronous delivery is the standard library's queue
handlers; structlog, Loguru, and OpenTelemetry are Providers an application
writes. That is what keeps all of them out of this package.

Every field travels through ``extra=``, so the application's formatter decides
rendering and nothing here composes a human sentence out of values a machine
wanted. No record carries SQL or a bind at either detail — that separation is
what lets :data:`SAFE` be the production default rather than a reduced mode
somebody has to remember to select.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Final, Literal, NamedTuple, assert_never, cast

from parallax.core.execution_lifecycle._activity import ExecutionLifecycleHandler
from parallax.core.execution_lifecycle._diagnostics import (
    ActivityFailure,
    CausedFailure,
    DatabaseFailureDiagnostic,
    DirectFailure,
    FailureDiagnostic,
)
from parallax.core.execution_lifecycle._errors import ExecutionLifecycleHandlerError
from parallax.core.execution_lifecycle._events import (
    ActivityFinished,
    AttemptCommitted,
    AttemptFailure,
    AttemptRollbackFailed,
    AttemptRolledBack,
    DatabaseCallFailed,
    DatabaseCallFinished,
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
    ReadStarted,
    RootExecution,
    SnapshotStreamFinished,
    SnapshotStreamStarted,
    StreamBatchCompleted,
    StreamBatchFailed,
    StreamBatchFinished,
    StreamBatchStarted,
    StreamClosedEarly,
    StreamExhausted,
    StreamFailed,
    TransactionAttemptFinished,
    TransactionAttemptStarted,
    TransactionInvocationFinished,
    TransactionInvocationStarted,
    WriteBatchCompleted,
    WriteBatchFailed,
    WriteBatchFinished,
    WriteBatchStarted,
)

__all__ = ["LifecycleLogDetail", "LoggingLifecycleProvider"]

type LifecycleLogDetail = Literal["SAFE", "DIAGNOSTIC"]
"""How much of a failure a record carries.

``SAFE`` carries correlation, the transition and its outcome, the entity and
interface, the counters, the duration, the failure's type and stable code, the
database category and native code, and the truncation flags. ``DIAGNOSTIC`` adds
the bounded message and rendered stack. Neither carries SQL or binds.
"""

_MESSAGE: Final = "parallax execution lifecycle %s"
"""One deferred-formatting message per record: the transition name, and every
other field through ``extra`` where a formatter can reach it structurally."""

_HANDLER_ERROR_MESSAGE: Final = "parallax execution lifecycle handler error"


class _Projected[T](NamedTuple):
    """One event answered for the log: how loudly, what to call it, whether it
    carries the root summary, and what will describe the rest once the Logger
    has said it wants the record.

    ``summarizes`` is answered by the same exhaustive match that answers the
    rest, rather than by a second list of Finished types that could silently
    fall behind the event union. ``subject`` is the value that match already
    narrowed and ``render`` is the renderer chosen for it, so the pairing is
    checked where the arm creates it and describing the event later needs no
    second match over the algebra.
    """

    level: int
    transition: str
    summarizes: bool
    subject: T
    render: Callable[[T, LifecycleLogDetail], dict[str, object]]


class _Counters:
    """One root's running totals — the only state a built-in Handler accumulates.

    Ten integers, so per-root state is bounded however long the root runs, how
    many times it retries, or how large its results are. They are what the root
    summary reports instead of the events they were read from.
    """

    __slots__ = (
        "affected_rows",
        "attempts",
        "database_calls",
        "database_duration_ns",
        "events",
        "joined_invocations",
        "reads",
        "returned_rows",
        "stream_batches",
        "write_batches",
    )

    def __init__(self) -> None:
        self.events = 0
        self.reads = 0
        self.write_batches = 0
        self.stream_batches = 0
        self.database_calls = 0
        self.database_duration_ns = 0
        self.returned_rows = 0
        self.affected_rows = 0
        self.attempts = 0
        self.joined_invocations = 0


def _diagnostic_fields(
    diagnostic: FailureDiagnostic, detail: LifecycleLogDetail
) -> dict[str, object]:
    fields: dict[str, object] = {
        "error_type": diagnostic.qualified_type,
        "error_code": diagnostic.code,
        "message_truncated": diagnostic.message_truncated,
        "stack_truncated": diagnostic.stack_truncated,
    }
    if detail == "DIAGNOSTIC":
        fields["error_message"] = diagnostic.message
        fields["error_stack"] = diagnostic.stack
    return fields


def _rollback_diagnostic_fields(
    diagnostic: FailureDiagnostic, detail: LifecycleLogDetail
) -> dict[str, object]:
    """The same projection under its own key prefix.

    A failed rollback reports two live failures at once — what ended the attempt
    and why undoing it did not complete — so the second set is spelled out here
    rather than composed, keeping every record's keys literal and constant.
    """
    fields: dict[str, object] = {
        "rollback_error_type": diagnostic.qualified_type,
        "rollback_error_code": diagnostic.code,
        "rollback_message_truncated": diagnostic.message_truncated,
        "rollback_stack_truncated": diagnostic.stack_truncated,
    }
    if detail == "DIAGNOSTIC":
        fields["rollback_error_message"] = diagnostic.message
        fields["rollback_error_stack"] = diagnostic.stack
    return fields


def _failure_fields(failure: ActivityFailure, detail: LifecycleLogDetail) -> dict[str, object]:
    """A failure's diagnostic, plus the direct child it is attributed to.

    ``cause_activity`` names this activity's OWN child rather than the deepest
    activity beneath it, so a reader walks a cause one record at a time — which
    is also why an unattributed failure omits the key rather than reporting a
    null cause that would read as "nothing caused this".
    """
    match failure:
        case DirectFailure(diagnostic):
            return _diagnostic_fields(diagnostic, detail)
        case CausedFailure(diagnostic, cause_activity_id):
            fields = _diagnostic_fields(diagnostic, detail)
            fields["cause_activity"] = cause_activity_id
            return fields
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _database_failure_fields(
    diagnostic: DatabaseFailureDiagnostic, detail: LifecycleLogDetail
) -> dict[str, object]:
    fields = _diagnostic_fields(diagnostic.failure, detail)
    fields["database_category"] = diagnostic.category
    fields["database_native_code"] = diagnostic.native_code
    return fields


def _attempt_failure_fields(
    failure: AttemptFailure, detail: LifecycleLogDetail
) -> dict[str, object]:
    fields = _failure_fields(failure.failure, detail)
    fields["phase"] = failure.phase
    fields["retry_eligible"] = failure.retry_eligible
    return fields


type _NoPayload = TransactionAttemptStarted | StreamBatchStarted
type _Completed = ReadCompleted | WriteBatchCompleted | StreamBatchCompleted
type _Committed = OuterInvocationCommitted | AttemptCommitted
type _ActivityFailed = (
    ReadFailed | WriteBatchFailed | OuterInvocationFailed | StreamFailed | StreamBatchFailed
)


def _no_fields(_event: _NoPayload, _detail: LifecycleLogDetail) -> dict[str, object]:
    return {}


def _read_started_fields(event: ReadStarted, _detail: LifecycleLogDetail) -> dict[str, object]:
    return {"target": event.target, "interface": event.interface}


def _write_batch_started_fields(
    event: WriteBatchStarted, _detail: LifecycleLogDetail
) -> dict[str, object]:
    return {"trigger": event.trigger}


def _database_call_started_fields(
    event: DatabaseCallStarted, _detail: LifecycleLogDetail
) -> dict[str, object]:
    return {"target": event.target, "call_kind": event.kind}


def _invocation_started_fields(
    event: TransactionInvocationStarted, _detail: LifecycleLogDetail
) -> dict[str, object]:
    match event.invocation:
        case OuterInvocation(concurrency=concurrency, retry_policy=policy):
            return {
                "invocation": "outer",
                "concurrency": concurrency,
                "retries": policy.retries,
                "retry_optimistic_conflicts": policy.retry_optimistic_conflicts,
            }
        case JoinedInvocation():
            return {"invocation": "joined"}
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _stream_started_fields(
    event: SnapshotStreamStarted, _detail: LifecycleLogDetail
) -> dict[str, object]:
    return {
        "target": event.target,
        "interface": event.interface,
        "batch_size": event.batch_size,
    }


def _completed_fields(_outcome: _Completed, _detail: LifecycleLogDetail) -> dict[str, object]:
    return {"outcome": "completed"}


def _failed_fields(outcome: _ActivityFailed, detail: LifecycleLogDetail) -> dict[str, object]:
    return {"outcome": "failed", **_failure_fields(outcome.failure, detail)}


def _committed_fields(_outcome: _Committed, _detail: LifecycleLogDetail) -> dict[str, object]:
    return {"outcome": "committed"}


def _returned_fields(
    _outcome: JoinedInvocationReturned, _detail: LifecycleLogDetail
) -> dict[str, object]:
    return {"outcome": "returned"}


def _raised_fields(
    outcome: JoinedInvocationRaised, detail: LifecycleLogDetail
) -> dict[str, object]:
    return {"outcome": "raised", **_failure_fields(outcome.failure, detail)}


def _exhausted_fields(_outcome: StreamExhausted, _detail: LifecycleLogDetail) -> dict[str, object]:
    return {"outcome": "exhausted"}


def _closed_early_fields(
    _outcome: StreamClosedEarly, _detail: LifecycleLogDetail
) -> dict[str, object]:
    return {"outcome": "closedEarly"}


def _database_read_fields(
    event: DatabaseCallFinished, _detail: LifecycleLogDetail
) -> dict[str, object]:
    outcome = cast(DatabaseReadCompleted, event.outcome)
    return {
        "outcome": "readCompleted",
        "returned_rows": outcome.returned_rows,
        "duration_ns": event.duration_ns,
    }


def _database_write_fields(
    event: DatabaseCallFinished, _detail: LifecycleLogDetail
) -> dict[str, object]:
    outcome = cast(DatabaseWriteCompleted, event.outcome)
    return {
        "outcome": "writeCompleted",
        "affected_rows": outcome.affected_rows,
        "duration_ns": event.duration_ns,
    }


def _database_call_failed_fields(
    event: DatabaseCallFinished, detail: LifecycleLogDetail
) -> dict[str, object]:
    outcome = cast(DatabaseCallFailed, event.outcome)
    return {
        "outcome": "failed",
        **_database_failure_fields(outcome.diagnostic, detail),
        "duration_ns": event.duration_ns,
    }


def _rolled_back_fields(
    outcome: AttemptRolledBack, detail: LifecycleLogDetail
) -> dict[str, object]:
    return {"outcome": "rolledBack", **_attempt_failure_fields(outcome.failure, detail)}


def _rollback_failed_fields(
    outcome: AttemptRollbackFailed, detail: LifecycleLogDetail
) -> dict[str, object]:
    return {
        "outcome": "rollbackFailed",
        **_attempt_failure_fields(outcome.triggering_failure, detail),
        **_rollback_diagnostic_fields(outcome.rollback_failure, detail),
    }


def _finished_level(event: ActivityFinished, failed: bool) -> int:
    """DEBUG for an ordinary non-root Finished, and the root's own summary level.

    The root activity is the only one whose end is the operation's end, so it is
    the only one an application wants at INFO when nothing went wrong and at
    ERROR when something did.
    """
    if event.parent_activity_id is None:
        return logging.ERROR if failed else logging.INFO
    return logging.DEBUG


def _read_projection(event: ReadFinished, transition: str) -> _Projected[Any]:
    match event.outcome:
        case ReadCompleted() as outcome:
            projected = _Projected(
                _finished_level(event, False), transition, True, outcome, _completed_fields
            )
            return projected
        case ReadFailed() as outcome:
            projected = _Projected(
                _finished_level(event, True), transition, True, outcome, _failed_fields
            )
            return projected
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _write_batch_projection(event: WriteBatchFinished, transition: str) -> _Projected[Any]:
    match event.outcome:
        case WriteBatchCompleted() as outcome:
            projected = _Projected(
                _finished_level(event, False), transition, True, outcome, _completed_fields
            )
            return projected
        case WriteBatchFailed() as outcome:
            projected = _Projected(
                _finished_level(event, True), transition, True, outcome, _failed_fields
            )
            return projected
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _database_call_projection(event: DatabaseCallFinished, transition: str) -> _Projected[Any]:
    """The one activity whose renderer describes the EVENT rather than the outcome.

    ``duration_ns`` is reported for every ending a call has and lives outside the
    outcome that says which ending it was, so each renderer takes the whole event
    and reaches the ending this arm already established.
    """
    match event.outcome:
        case DatabaseReadCompleted():
            projected = _Projected(
                _finished_level(event, False), transition, True, event, _database_read_fields
            )
            return projected
        case DatabaseWriteCompleted():
            projected = _Projected(
                _finished_level(event, False), transition, True, event, _database_write_fields
            )
            return projected
        case DatabaseCallFailed():
            projected = _Projected(
                _finished_level(event, True), transition, True, event, _database_call_failed_fields
            )
            return projected
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _invocation_projection(
    event: TransactionInvocationFinished, transition: str
) -> _Projected[Any]:
    match event.outcome:
        case OuterInvocationCommitted() as outcome:
            projected = _Projected(
                _finished_level(event, False), transition, True, outcome, _committed_fields
            )
            return projected
        case OuterInvocationFailed() as outcome:
            projected = _Projected(
                _finished_level(event, True), transition, True, outcome, _failed_fields
            )
            return projected
        case JoinedInvocationReturned() as outcome:
            projected = _Projected(
                _finished_level(event, False), transition, True, outcome, _returned_fields
            )
            return projected
        case JoinedInvocationRaised() as outcome:
            projected = _Projected(
                _finished_level(event, True), transition, True, outcome, _raised_fields
            )
            return projected
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _attempt_projection(event: TransactionAttemptFinished, transition: str) -> _Projected[Any]:
    """An attempt's outcome and the level it is worth, which is its own rule.

    A rollback that FAILED is an error whatever ended the attempt, because what
    the transaction left behind is then unknown. A rollback that succeeded is a
    warning exactly when the classifier says the failure is retry-eligible: that
    is the one the invocation may go on to survive, so it is worth seeing while
    a terminal one is already reported by the failed root above it.
    """
    match event.outcome:
        case AttemptCommitted() as outcome:
            projected = _Projected(logging.DEBUG, transition, True, outcome, _committed_fields)
            return projected
        case AttemptRolledBack() as outcome:
            level = logging.WARNING if outcome.failure.retry_eligible else logging.DEBUG
            projected = _Projected(level, transition, True, outcome, _rolled_back_fields)
            return projected
        case AttemptRollbackFailed() as outcome:
            projected = _Projected(
                logging.ERROR, transition, True, outcome, _rollback_failed_fields
            )
            return projected
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _stream_projection(event: SnapshotStreamFinished, transition: str) -> _Projected[Any]:
    match event.outcome:
        case StreamExhausted() as outcome:
            projected = _Projected(
                _finished_level(event, False), transition, True, outcome, _exhausted_fields
            )
            return projected
        case StreamClosedEarly() as outcome:
            projected = _Projected(
                _finished_level(event, False), transition, True, outcome, _closed_early_fields
            )
            return projected
        case StreamFailed() as outcome:
            projected = _Projected(
                _finished_level(event, True), transition, True, outcome, _failed_fields
            )
            return projected
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _stream_batch_projection(event: StreamBatchFinished, transition: str) -> _Projected[Any]:
    match event.outcome:
        case StreamBatchCompleted() as outcome:
            projected = _Projected(
                _finished_level(event, False), transition, True, outcome, _completed_fields
            )
            return projected
        case StreamBatchFailed() as outcome:
            projected = _Projected(
                _finished_level(event, True), transition, True, outcome, _failed_fields
            )
            return projected
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _projected(event: ExecutionEvent) -> _Projected[Any]:
    """``event`` as a level, a transition name, and the renderer that describes it.

    The one exhaustive match over the event union: a transition added to the
    algebra fails to type-check here until it is answered, which is what makes
    this Handler's coverage of the algebra a compile-time fact rather than a
    property re-established by inspection. It answers the level without
    describing anything, so the Logger can be asked about a record before the
    work of describing it is done.

    The arms stay flat. Exhaustiveness is proved by subtracting matched members
    from the union, and a nested subpattern subtracts nothing, so folding an
    outcome match into an arm here would turn the guard below into a runtime
    branch.
    """
    match event:
        case ReadStarted():
            projected = _Projected(logging.DEBUG, "readStarted", False, event, _read_started_fields)
            return projected
        case ReadFinished():
            return _read_projection(event, "readFinished")
        case WriteBatchStarted():
            projected = _Projected(
                logging.DEBUG, "writeBatchStarted", False, event, _write_batch_started_fields
            )
            return projected
        case WriteBatchFinished():
            return _write_batch_projection(event, "writeBatchFinished")
        case DatabaseCallStarted():
            projected = _Projected(
                logging.DEBUG, "databaseCallStarted", False, event, _database_call_started_fields
            )
            return projected
        case DatabaseCallFinished():
            return _database_call_projection(event, "databaseCallFinished")
        case TransactionInvocationStarted():
            projected = _Projected(
                logging.DEBUG,
                "transactionInvocationStarted",
                False,
                event,
                _invocation_started_fields,
            )
            return projected
        case TransactionInvocationFinished():
            return _invocation_projection(event, "transactionInvocationFinished")
        case TransactionAttemptStarted():
            projected = _Projected(
                logging.DEBUG, "transactionAttemptStarted", False, event, _no_fields
            )
            return projected
        case TransactionAttemptFinished():
            return _attempt_projection(event, "transactionAttemptFinished")
        case SnapshotStreamStarted():
            projected = _Projected(
                logging.DEBUG, "snapshotStreamStarted", False, event, _stream_started_fields
            )
            return projected
        case SnapshotStreamFinished():
            return _stream_projection(event, "snapshotStreamFinished")
        case StreamBatchStarted():
            projected = _Projected(logging.DEBUG, "streamBatchStarted", False, event, _no_fields)
            return projected
        case StreamBatchFinished():
            return _stream_batch_projection(event, "streamBatchFinished")
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


class _LoggingHandler:
    """One root's Handler: its correlation, its counters, and one record per event.

    The root's own canonical text is spelled once here rather than per event,
    and the counters are the whole of what accumulates: a Handler that kept the
    events themselves in order to summarize them would be the retained log this
    module exists to replace.

    The Logger is asked its own level before anything is described, and a
    transition it would drop is described not at all. That is the standard
    idiom's standard trade, taken deliberately: a Logger whose ``isEnabledFor``
    and ``log`` disagree loses a record here as it would with any library that
    guards. What makes it safe to take is that the level asked about is the
    exact level ``Logger.log`` is given, answered by the same match that names
    the transition, rather than a bound on it.
    """

    __slots__ = (
        "_counters",
        "_detail",
        "_execution_id",
        "_execution_kind",
        "_logger",
    )

    _detail: LifecycleLogDetail

    def __init__(
        self, logger: logging.Logger, detail: LifecycleLogDetail, execution: RootExecution
    ) -> None:
        self._logger = logger
        self._detail = detail
        self._execution_id = str(execution.id)
        self._execution_kind = execution.kind
        self._counters = _Counters()

    def handle(self, event: ExecutionEvent, /) -> None:
        """Count the event, then describe it as one record the Logger will keep.

        The counters move for EVERY event whatever the level, because the root
        summary reports what the whole operation did and a total that skipped
        the transitions nobody logged would be wrong rather than cheaper. The
        description is the opposite: it is the only expensive thing here, and a
        Logger below the level would throw all of it away.
        """
        self._count(event)
        projected = _projected(event)
        if not self._logger.isEnabledFor(projected.level):
            return
        fields = projected.render(projected.subject, self._detail)
        fields["execution_id"] = self._execution_id
        fields["execution_kind"] = self._execution_kind
        fields["sequence"] = event.sequence
        fields["activity"] = event.activity_id
        fields["parent_activity"] = event.parent_activity_id
        fields["transition"] = projected.transition
        if projected.summarizes and event.parent_activity_id is None:
            self._summarize(fields)
        self._logger.log(projected.level, _MESSAGE, projected.transition, extra=fields)

    def _count(self, event: ExecutionEvent) -> None:
        """Which totals this event moves.

        Deliberately partial rather than exhaustive: the summary reports the
        work an operation did, and which facts are worth a running total is a
        choice this Handler makes, not a property of the event algebra.
        """
        counters = self._counters
        counters.events += 1
        if isinstance(event, DatabaseCallFinished):
            counters.database_calls += 1
            counters.database_duration_ns += event.duration_ns
            outcome = event.outcome
            if isinstance(outcome, DatabaseReadCompleted):
                counters.returned_rows += outcome.returned_rows
            elif isinstance(outcome, DatabaseWriteCompleted):
                counters.affected_rows += outcome.affected_rows
        elif isinstance(event, ReadStarted):
            counters.reads += 1
        elif isinstance(event, WriteBatchStarted):
            counters.write_batches += 1
        elif isinstance(event, StreamBatchStarted):
            counters.stream_batches += 1
        elif isinstance(event, TransactionAttemptStarted):
            counters.attempts += 1
        elif isinstance(event, TransactionInvocationStarted) and isinstance(
            event.invocation, JoinedInvocation
        ):
            counters.joined_invocations += 1

    def _summarize(self, fields: dict[str, object]) -> None:
        counters = self._counters
        fields["total_events"] = counters.events
        fields["total_reads"] = counters.reads
        fields["total_write_batches"] = counters.write_batches
        fields["total_stream_batches"] = counters.stream_batches
        fields["total_database_calls"] = counters.database_calls
        fields["total_database_duration_ns"] = counters.database_duration_ns
        fields["total_returned_rows"] = counters.returned_rows
        fields["total_affected_rows"] = counters.affected_rows
        fields["total_attempts"] = counters.attempts
        fields["total_joined_invocations"] = counters.joined_invocations


class LoggingLifecycleProvider:
    """Log every accepted root through a Logger the application configured.

    It accepts every root and opens one Handler per root, holding nothing
    across roots itself: the Logger is the application's, and everything about
    where records go, how they are buffered, and when they are flushed belongs
    to the handlers configured on it.

    Levels follow what an operator reads rather than what the algebra
    distinguishes: every Started and every ordinary non-root Finished at
    ``DEBUG``, the root's summary at ``INFO`` when it succeeded and ``ERROR``
    when it did not, a retry-eligible rollback at ``WARNING``, and a failed
    rollback at ``ERROR``.
    """

    __slots__ = ("_detail", "_logger")

    _detail: LifecycleLogDetail

    def __init__(self, logger: logging.Logger, /, *, detail: LifecycleLogDetail = "SAFE") -> None:
        self._logger = logger
        self._detail = detail

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        return _LoggingHandler(self._logger, self._detail, execution)

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        """Log a Handler failure this Provider was told about.

        Correlation-only by construction: the reported error carries no event,
        statement, or bind, so this cannot become a second route onto borrowed
        data however verbose the detail is set.
        """
        fields: dict[str, object] = {
            "execution_id": str(error.execution_id),
            "sequence": error.sequence,
            "activity": error.activity_id,
            "handler_type": error.handler_type,
            "fanout_path": error.fanout_path,
            **_diagnostic_fields(error.diagnostic, self._detail),
        }
        self._logger.log(logging.ERROR, _HANDLER_ERROR_MESSAGE, extra=fields)
