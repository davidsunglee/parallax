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
from typing import Final, Literal, NamedTuple, assert_never

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
    ReadOutcome,
    ReadStarted,
    RootExecution,
    SnapshotStreamFinished,
    SnapshotStreamOutcome,
    SnapshotStreamStarted,
    StreamBatchCompleted,
    StreamBatchFailed,
    StreamBatchFinished,
    StreamBatchOutcome,
    StreamBatchStarted,
    StreamClosedEarly,
    StreamExhausted,
    StreamFailed,
    TransactionAttemptFinished,
    TransactionAttemptOutcome,
    TransactionAttemptStarted,
    TransactionInvocation,
    TransactionInvocationFinished,
    TransactionInvocationOutcome,
    TransactionInvocationStarted,
    WriteBatchCompleted,
    WriteBatchFailed,
    WriteBatchFinished,
    WriteBatchOutcome,
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


class _Rendered(NamedTuple):
    """One event projected for the log: what to say, how loudly, and whether it
    closes an activity.

    ``finished`` is answered by the same exhaustive match that answers the rest,
    rather than by a second list of Finished types that could silently fall
    behind the event union.
    """

    level: int
    transition: str
    fields: dict[str, object]
    finished: bool


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


def _invocation_fields(invocation: TransactionInvocation) -> dict[str, object]:
    match invocation:
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


def _read_outcome(
    outcome: ReadOutcome, detail: LifecycleLogDetail
) -> tuple[dict[str, object], bool]:
    match outcome:
        case ReadCompleted():
            return {"outcome": "completed"}, False
        case ReadFailed(failure):
            return {"outcome": "failed", **_failure_fields(failure, detail)}, True
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _write_batch_outcome(
    outcome: WriteBatchOutcome, detail: LifecycleLogDetail
) -> tuple[dict[str, object], bool]:
    match outcome:
        case WriteBatchCompleted():
            return {"outcome": "completed"}, False
        case WriteBatchFailed(failure):
            return {"outcome": "failed", **_failure_fields(failure, detail)}, True
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _database_call_outcome(
    outcome: DatabaseCallOutcome, detail: LifecycleLogDetail
) -> tuple[dict[str, object], bool]:
    match outcome:
        case DatabaseReadCompleted(returned_rows):
            return {"outcome": "readCompleted", "returned_rows": returned_rows}, False
        case DatabaseWriteCompleted(affected_rows):
            return {"outcome": "writeCompleted", "affected_rows": affected_rows}, False
        case DatabaseCallFailed(diagnostic):
            return {"outcome": "failed", **_database_failure_fields(diagnostic, detail)}, True
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _invocation_outcome(
    outcome: TransactionInvocationOutcome, detail: LifecycleLogDetail
) -> tuple[dict[str, object], bool]:
    match outcome:
        case OuterInvocationCommitted():
            return {"outcome": "committed"}, False
        case OuterInvocationFailed(failure):
            return {"outcome": "failed", **_failure_fields(failure, detail)}, True
        case JoinedInvocationReturned():
            return {"outcome": "returned"}, False
        case JoinedInvocationRaised(failure):
            return {"outcome": "raised", **_failure_fields(failure, detail)}, True
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _stream_outcome(
    outcome: SnapshotStreamOutcome, detail: LifecycleLogDetail
) -> tuple[dict[str, object], bool]:
    match outcome:
        case StreamExhausted():
            return {"outcome": "exhausted"}, False
        case StreamClosedEarly():
            return {"outcome": "closedEarly"}, False
        case StreamFailed(failure):
            return {"outcome": "failed", **_failure_fields(failure, detail)}, True
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _stream_batch_outcome(
    outcome: StreamBatchOutcome, detail: LifecycleLogDetail
) -> tuple[dict[str, object], bool]:
    match outcome:
        case StreamBatchCompleted():
            return {"outcome": "completed"}, False
        case StreamBatchFailed(failure):
            return {"outcome": "failed", **_failure_fields(failure, detail)}, True
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _attempt_outcome(
    outcome: TransactionAttemptOutcome, detail: LifecycleLogDetail
) -> tuple[dict[str, object], int]:
    """An attempt's outcome and the level it is worth, which is its own rule.

    A rollback that FAILED is an error whatever ended the attempt, because what
    the transaction left behind is then unknown. A rollback that succeeded is a
    warning exactly when the classifier says the failure is retry-eligible: that
    is the one the invocation may go on to survive, so it is worth seeing while
    a terminal one is already reported by the failed root above it.
    """
    match outcome:
        case AttemptCommitted():
            return {"outcome": "committed"}, logging.DEBUG
        case AttemptRolledBack(failure):
            fields = {"outcome": "rolledBack", **_attempt_failure_fields(failure, detail)}
            return fields, logging.WARNING if failure.retry_eligible else logging.DEBUG
        case AttemptRollbackFailed(triggering, rollback):
            fields = {
                "outcome": "rollbackFailed",
                **_attempt_failure_fields(triggering, detail),
                **_rollback_diagnostic_fields(rollback, detail),
            }
            return fields, logging.ERROR
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


def _finished_level(event: ActivityFinished, failed: bool) -> int:
    """DEBUG for an ordinary non-root Finished, and the root's own summary level.

    The root activity is the only one whose end is the operation's end, so it is
    the only one an application wants at INFO when nothing went wrong and at
    ERROR when something did.
    """
    if event.parent_activity_id is None:
        return logging.ERROR if failed else logging.INFO
    return logging.DEBUG


def _rendered(event: ExecutionEvent, detail: LifecycleLogDetail) -> _Rendered:
    """``event`` as a level, a transition name, and the fields that describe it.

    The one exhaustive match over the event union: a transition added to the
    algebra fails to type-check here until it is answered, which is what makes
    this Handler's coverage of the algebra a compile-time fact rather than a
    review habit.
    """
    match event:
        case ReadStarted(target=target, interface=interface):
            fields: dict[str, object] = {"target": target, "interface": interface}
            return _Rendered(logging.DEBUG, "readStarted", fields, False)
        case ReadFinished(outcome=outcome):
            read_fields, failed = _read_outcome(outcome, detail)
            return _Rendered(_finished_level(event, failed), "readFinished", read_fields, True)
        case WriteBatchStarted(trigger=trigger):
            return _Rendered(logging.DEBUG, "writeBatchStarted", {"trigger": trigger}, False)
        case WriteBatchFinished(outcome=outcome):
            batch_fields, failed = _write_batch_outcome(outcome, detail)
            return _Rendered(
                _finished_level(event, failed), "writeBatchFinished", batch_fields, True
            )
        case DatabaseCallStarted(target=target, kind=kind):
            fields = {"target": target, "call_kind": kind}
            return _Rendered(logging.DEBUG, "databaseCallStarted", fields, False)
        case DatabaseCallFinished(duration_ns=duration_ns, outcome=outcome):
            call_fields, failed = _database_call_outcome(outcome, detail)
            call_fields["duration_ns"] = duration_ns
            return _Rendered(
                _finished_level(event, failed), "databaseCallFinished", call_fields, True
            )
        case TransactionInvocationStarted(invocation=invocation):
            return _Rendered(
                logging.DEBUG,
                "transactionInvocationStarted",
                _invocation_fields(invocation),
                False,
            )
        case TransactionInvocationFinished(outcome=outcome):
            invocation_fields, failed = _invocation_outcome(outcome, detail)
            return _Rendered(
                _finished_level(event, failed),
                "transactionInvocationFinished",
                invocation_fields,
                True,
            )
        case TransactionAttemptStarted():
            return _Rendered(logging.DEBUG, "transactionAttemptStarted", {}, False)
        case TransactionAttemptFinished(outcome=outcome):
            attempt_fields, level = _attempt_outcome(outcome, detail)
            return _Rendered(level, "transactionAttemptFinished", attempt_fields, True)
        case SnapshotStreamStarted(target=target, interface=interface, batch_size=batch_size):
            fields = {"target": target, "interface": interface, "batch_size": batch_size}
            return _Rendered(logging.DEBUG, "snapshotStreamStarted", fields, False)
        case SnapshotStreamFinished(outcome=outcome):
            stream_fields, failed = _stream_outcome(outcome, detail)
            return _Rendered(
                _finished_level(event, failed), "snapshotStreamFinished", stream_fields, True
            )
        case StreamBatchStarted():
            return _Rendered(logging.DEBUG, "streamBatchStarted", {}, False)
        case StreamBatchFinished(outcome=outcome):
            page_fields, failed = _stream_batch_outcome(outcome, detail)
            return _Rendered(
                _finished_level(event, failed), "streamBatchFinished", page_fields, True
            )
        case _ as unreachable:  # pragma: no cover - exhaustiveness guard
            assert_never(unreachable)


class _LoggingHandler:
    """One root's Handler: its correlation, its counters, and one record per event.

    The root's own canonical text is spelled once here rather than per event,
    and the counters are the whole of what accumulates: a Handler that kept the
    events themselves in order to summarize them would be the retained log this
    module exists to replace.
    """

    __slots__ = ("_counters", "_detail", "_execution_id", "_execution_kind", "_logger")

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
        self._count(event)
        rendered = _rendered(event, self._detail)
        fields = rendered.fields
        fields["execution_id"] = self._execution_id
        fields["execution_kind"] = self._execution_kind
        fields["sequence"] = event.sequence
        fields["activity"] = event.activity_id
        fields["parent_activity"] = event.parent_activity_id
        fields["transition"] = rendered.transition
        if rendered.finished and event.parent_activity_id is None:
            self._summarize(fields)
        self._logger.log(rendered.level, _MESSAGE, rendered.transition, extra=fields)

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
