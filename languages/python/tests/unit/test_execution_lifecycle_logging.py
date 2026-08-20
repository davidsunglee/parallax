"""What the logging built-in writes, and what it refuses to write
(m-execution-lifecycle, Docker-free).

Two claims carry the whole module. The first is a SAFETY claim: no record
carries SQL or a bind at either detail, which is what lets ``SAFE`` be the
production default rather than a reduced mode somebody has to select. The
second is a COMPLETENESS claim: the level rule and the field set answer every
transition in the algebra, the four stream ones included, so an operator reading
the records is not silently missing a kind of work.

Every assertion reads the structured payload rather than the rendered line. The
fields travel through ``extra=`` precisely so the application's formatter
decides rendering, and what this module owns is which fields exist and what they
say.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final, NoReturn, get_args
from uuid import UUID, uuid4

import pytest
from _transact_support import ACCOUNT, FIXED, NEW_ROW, RecordingPort, deadlock, new_account

from parallax.core.db_error import DatabaseError
from parallax.core.execution_lifecycle import (
    AttemptCommitted,
    AttemptFailure,
    AttemptRollbackFailed,
    AttemptRolledBack,
    CausedFailure,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    DatabaseWriteCompleted,
    DirectFailure,
    ExecutionEvent,
    ExecutionLifecycleHandlerError,
    JoinedInvocation,
    JoinedInvocationRaised,
    JoinedInvocationReturned,
    LifecycleLogDetail,
    LoggingLifecycleProvider,
    OuterInvocation,
    OuterInvocationCommitted,
    OuterInvocationFailed,
    ReadCompleted,
    ReadFailed,
    ReadFinished,
    ReadStarted,
    RetryPolicy,
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
from parallax.core.execution_lifecycle import _logging as _logging_module
from parallax.core.execution_lifecycle._diagnostics import (
    database_diagnostic_for,
    diagnostic_for,
)
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction

EXECUTION = RootExecution(uuid4(), "READ")
TRANSACTION = RootExecution(uuid4(), "TRANSACTION_INVOCATION")
STREAM = RootExecution(uuid4(), "SNAPSHOT_STREAM")
STATEMENT = LoweredStatement("select id from account where id = ?", (7,))

_STANDARD: Final = frozenset(
    vars(logging.LogRecord("logger", logging.INFO, "path", 0, "message", None, None))
) | {"message", "asctime"}
"""Everything ``logging`` puts on a record itself, so what is left is the payload.

The two added by hand are the ones a FORMATTER interpolates onto a record rather
than the constructor: pytest's capture handler formats what it captures, so
``message`` is present here and absent from a record nothing has rendered.
"""


@dataclass(frozen=True, slots=True)
class _Written:
    """One record, split into what an operator filters on and what a formatter
    renders."""

    level: int
    message: str
    fields: dict[str, object]


def _written(record: logging.LogRecord) -> _Written:
    return _Written(
        record.levelno,
        record.getMessage(),
        {key: value for key, value in vars(record).items() if key not in _STANDARD},
    )


def _logger(level: int = logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger(f"parallax.test.{uuid4().hex}")
    logger.setLevel(level)
    return logger


def _records(
    caplog: pytest.LogCaptureFixture,
    events: list[ExecutionEvent],
    *,
    execution: RootExecution = EXECUTION,
    detail: LifecycleLogDetail = "SAFE",
) -> list[_Written]:
    """What one root's Handler writes for ``events``, in order."""
    logger = _logger()
    handler = LoggingLifecycleProvider(logger, detail=detail).open(execution)
    assert handler is not None
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        for event in events:
            handler.handle(event)
    return [_written(record) for record in caplog.records]


_DATABASE_FAILURE: Final = database_diagnostic_for(
    DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
)


class _Described(Exception):
    """Raised in place of describing an event.

    A description is proven ABSENT by the delivery completing and PRESENT by this
    escaping, so neither direction rests on a counter a reader has to trust.
    """


def _describes_nothing(event: ExecutionEvent, detail: LifecycleLogDetail) -> NoReturn:
    raise _Described(type(event).__name__)


class _Collecting(logging.Handler):
    """A Handler keeping whatever its Logger gave it, at that Logger's own level.

    ``caplog`` captures by SETTING the Logger's level, which is the state a test
    about levels has to vary rather than fix, so capture is a Handler here.
    """

    def __init__(self) -> None:
        super().__init__(logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _failure(message: str = "the row vanished") -> DirectFailure:
    return DirectFailure(diagnostic_for(RuntimeError(message)))


def _attempt_failure(*, retry_eligible: bool) -> AttemptFailure:
    return AttemptFailure("CALLBACK", _failure(), retry_eligible)


def _db(port: RecordingPort, provider: Any) -> Database:
    return connect(port, ACCOUNT, clock=FixedClock(FIXED), lifecycle_provider=provider)


def test_a_started_transition_carries_its_correlation_and_its_own_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    (record,) = _records(caplog, [ReadStarted(EXECUTION.id, 1, 1, None, "Account", "TYPED")])
    assert record.level == logging.DEBUG
    assert record.message == "parallax execution lifecycle readStarted"
    assert record.fields == {
        "execution_id": str(EXECUTION.id),
        "execution_kind": "READ",
        "sequence": 1,
        "activity": 1,
        "parent_activity": None,
        "transition": "readStarted",
        "target": "Account",
        "interface": "TYPED",
    }


def test_neither_detail_carries_a_statement_or_a_bind(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The separation the production default rests on: a Database Call borrows
    # the exact statement it ran, and no record projects any of it.
    events: list[ExecutionEvent] = [
        DatabaseCallStarted(EXECUTION.id, 1, 2, 1, "Account", "READ", STATEMENT),
        DatabaseCallFinished(EXECUTION.id, 2, 2, 1, STATEMENT, 4_000, DatabaseReadCompleted(3)),
    ]
    for detail in ("SAFE", "DIAGNOSTIC"):
        for record in _records(caplog, events, detail=detail):
            rendered = repr(record.fields).lower()
            assert "select" not in rendered
            assert "account where" not in rendered
            assert 7 not in record.fields.values(), "the bind the statement carried"
        caplog.clear()


def test_a_database_call_reports_its_duration_row_count_and_neutral_category(
    caplog: pytest.LogCaptureFixture,
) -> None:
    failed = database_diagnostic_for(
        DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
    )
    completed, write, failure = _records(
        caplog,
        [
            DatabaseCallFinished(EXECUTION.id, 1, 2, 1, STATEMENT, 4_000, DatabaseReadCompleted(3)),
            DatabaseCallFinished(
                EXECUTION.id, 2, 3, 1, STATEMENT, 8_000, DatabaseWriteCompleted(2)
            ),
            DatabaseCallFinished(
                EXECUTION.id, 3, 4, 1, STATEMENT, 1_000, DatabaseCallFailed(failed)
            ),
        ],
    )
    assert completed.fields["outcome"] == "readCompleted"
    assert (completed.fields["returned_rows"], completed.fields["duration_ns"]) == (3, 4_000)
    assert (write.fields["outcome"], write.fields["affected_rows"]) == ("writeCompleted", 2)
    assert failure.fields["outcome"] == "failed"
    assert failure.fields["database_category"] == "deadlock"
    assert failure.fields["database_native_code"] == "40P01"
    assert failure.level == logging.DEBUG, "an ordinary non-root Finished"


def test_only_diagnostic_detail_carries_the_bounded_message_and_stack(
    caplog: pytest.LogCaptureFixture,
) -> None:
    finished = ReadFinished(EXECUTION.id, 1, 1, None, ReadFailed(_failure()))
    (safe,) = _records(caplog, [finished])
    assert str(safe.fields["error_type"]).endswith(".RuntimeError")
    assert safe.fields["error_code"] is None
    assert (safe.fields["message_truncated"], safe.fields["stack_truncated"]) == (False, False)
    assert "error_message" not in safe.fields
    assert "error_stack" not in safe.fields

    caplog.clear()
    (diagnostic,) = _records(caplog, [finished], detail="DIAGNOSTIC")
    assert diagnostic.fields["error_message"] == "the row vanished"
    assert "RuntimeError" in str(diagnostic.fields["error_stack"])


def test_a_caused_failure_names_the_direct_child_it_is_attributed_to(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caused = CausedFailure(diagnostic_for(RuntimeError("the call failed")), 2)
    (record,) = _records(caplog, [ReadFinished(EXECUTION.id, 1, 1, None, ReadFailed(caused))])
    assert record.fields["cause_activity"] == 2

    caplog.clear()
    (direct,) = _records(caplog, [ReadFinished(EXECUTION.id, 1, 1, None, ReadFailed(_failure()))])
    assert "cause_activity" not in direct.fields, "an unattributed failure names no cause at all"


def test_the_root_summary_is_info_when_it_succeeded_and_error_when_it_did_not(
    caplog: pytest.LogCaptureFixture,
) -> None:
    events: list[ExecutionEvent] = [
        ReadStarted(EXECUTION.id, 1, 1, None, "Account", "TYPED"),
        DatabaseCallStarted(EXECUTION.id, 2, 2, 1, "Account", "READ", STATEMENT),
        DatabaseCallFinished(EXECUTION.id, 3, 2, 1, STATEMENT, 4_000, DatabaseReadCompleted(3)),
        ReadFinished(EXECUTION.id, 4, 1, None, ReadCompleted()),
    ]
    *_, summary = _records(caplog, events)
    assert summary.level == logging.INFO
    assert summary.fields["total_events"] == 4
    assert summary.fields["total_reads"] == 1
    assert summary.fields["total_database_calls"] == 1
    assert summary.fields["total_returned_rows"] == 3
    assert summary.fields["total_database_duration_ns"] == 4_000

    caplog.clear()
    failed = [*events[:-1], ReadFinished(EXECUTION.id, 4, 1, None, ReadFailed(_failure()))]
    *_, failing = _records(caplog, failed)
    assert failing.level == logging.ERROR
    assert failing.fields["total_events"] == 4


def test_a_non_root_finished_carries_no_summary_at_all(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The summary is the ROOT's, so a nested activity closing does not restate
    # the whole operation's totals under a second set of keys.
    (record,) = _records(caplog, [WriteBatchFinished(EXECUTION.id, 1, 3, 2, WriteBatchCompleted())])
    assert "total_events" not in record.fields


def test_only_a_retry_eligible_rollback_is_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A rollback the invocation may still survive is worth an operator's
    # attention on its own; a terminal one is already reported by the failed
    # root above it, which is where the whole story is.
    eligible, terminal, committed = _records(
        caplog,
        [
            TransactionAttemptFinished(
                TRANSACTION.id, 1, 2, 1, AttemptRolledBack(_attempt_failure(retry_eligible=True))
            ),
            TransactionAttemptFinished(
                TRANSACTION.id, 2, 3, 1, AttemptRolledBack(_attempt_failure(retry_eligible=False))
            ),
            TransactionAttemptFinished(TRANSACTION.id, 3, 4, 1, AttemptCommitted()),
        ],
        execution=TRANSACTION,
    )
    assert eligible.level == logging.WARNING
    assert eligible.fields["outcome"] == "rolledBack"
    assert eligible.fields["phase"] == "CALLBACK"
    assert eligible.fields["retry_eligible"] is True
    assert terminal.level == logging.DEBUG
    assert (committed.level, committed.fields["outcome"]) == (logging.DEBUG, "committed")


def test_a_failed_rollback_is_an_error_carrying_both_live_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    outcome = AttemptRollbackFailed(
        _attempt_failure(retry_eligible=True),
        diagnostic_for(
            DatabaseError(category="connectionDead", native_code="08006", message="gone")
        ),
    )
    (record,) = _records(
        caplog,
        [TransactionAttemptFinished(TRANSACTION.id, 1, 2, 1, outcome)],
        execution=TRANSACTION,
        detail="DIAGNOSTIC",
    )
    assert record.level == logging.ERROR
    assert record.fields["outcome"] == "rollbackFailed"
    assert record.fields["error_message"] == "the row vanished"
    assert record.fields["rollback_error_message"] == "connectionDead [08006]: gone"
    assert str(record.fields["rollback_error_type"]).endswith(".DatabaseError")

    caplog.clear()
    (safe,) = _records(
        caplog,
        [TransactionAttemptFinished(TRANSACTION.id, 1, 2, 1, outcome)],
        execution=TRANSACTION,
    )
    # The rollback failure is bounded by the same detail rule its trigger is: a
    # second live failure is no reason for one of them to carry a message the
    # operator did not ask for.
    assert str(safe.fields["rollback_error_type"]).endswith(".DatabaseError")
    assert "rollback_error_message" not in safe.fields
    assert "rollback_error_stack" not in safe.fields


def test_an_outer_invocation_states_the_policy_it_resolved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    outer, joined = _records(
        caplog,
        [
            TransactionInvocationStarted(
                TRANSACTION.id, 1, 1, None, OuterInvocation("locking", RetryPolicy(10, True))
            ),
            TransactionInvocationStarted(TRANSACTION.id, 2, 3, 2, JoinedInvocation()),
        ],
        execution=TRANSACTION,
    )
    assert outer.fields["invocation"] == "outer"
    assert outer.fields["concurrency"] == "locking"
    assert outer.fields["retries"] == 10
    assert outer.fields["retry_optimistic_conflicts"] is True
    assert joined.fields["invocation"] == "joined"
    assert "concurrency" not in joined.fields, "a joined call resolved no policy of its own"


def test_every_invocation_and_batch_outcome_has_its_own_spelling(
    caplog: pytest.LogCaptureFixture,
) -> None:
    records = _records(
        caplog,
        [
            TransactionInvocationFinished(TRANSACTION.id, 1, 1, None, OuterInvocationCommitted()),
            TransactionInvocationFinished(
                TRANSACTION.id, 2, 1, None, OuterInvocationFailed(_failure())
            ),
            TransactionInvocationFinished(TRANSACTION.id, 3, 3, 2, JoinedInvocationReturned()),
            TransactionInvocationFinished(
                TRANSACTION.id, 4, 3, 2, JoinedInvocationRaised(_failure())
            ),
            WriteBatchStarted(TRANSACTION.id, 5, 4, 2, "pre_commit"),
            WriteBatchFinished(TRANSACTION.id, 6, 4, 2, WriteBatchCompleted()),
            WriteBatchFinished(TRANSACTION.id, 7, 5, 2, WriteBatchFailed(_failure())),
            TransactionAttemptStarted(TRANSACTION.id, 8, 6, 1),
        ],
        execution=TRANSACTION,
    )
    assert [record.fields.get("outcome") for record in records] == [
        "committed",
        "failed",
        "returned",
        "raised",
        None,
        "completed",
        "failed",
        None,
    ]
    assert records[4].fields["trigger"] == "pre_commit"
    assert [record.level for record in records] == [
        logging.INFO,
        logging.ERROR,
        logging.DEBUG,
        logging.DEBUG,
        logging.DEBUG,
        logging.DEBUG,
        logging.DEBUG,
        logging.DEBUG,
    ]


def test_the_stream_vocabulary_logs_like_every_other_transition(
    caplog: pytest.LogCaptureFixture,
) -> None:
    records = _records(
        caplog,
        [
            SnapshotStreamStarted(STREAM.id, 1, 1, None, "Account", "WIRE", 500),
            StreamBatchStarted(STREAM.id, 2, 2, 1),
            StreamBatchFinished(STREAM.id, 3, 2, 1, StreamBatchCompleted()),
            StreamBatchFinished(STREAM.id, 4, 3, 1, StreamBatchFailed(_failure())),
            SnapshotStreamFinished(STREAM.id, 5, 1, None, StreamExhausted()),
            SnapshotStreamFinished(STREAM.id, 6, 1, None, StreamClosedEarly()),
            SnapshotStreamFinished(STREAM.id, 7, 1, None, StreamFailed(_failure())),
        ],
        execution=STREAM,
    )
    assert records[0].fields["target"] == "Account"
    assert records[0].fields["interface"] == "WIRE"
    assert records[0].fields["batch_size"] == 500
    assert [record.fields.get("outcome") for record in records[2:]] == [
        "completed",
        "failed",
        "exhausted",
        "closedEarly",
        "failed",
    ]
    # Closing early is how a caller stops reading rather than a failure of the
    # stream, so it summarizes at the level exhaustion does.
    assert [record.level for record in records[4:]] == [
        logging.INFO,
        logging.INFO,
        logging.ERROR,
    ]
    # Page batches are counted for the root summary exactly as reads and write
    # batches are, so a stream's own work is not invisible to it.
    assert records[4].fields["total_stream_batches"] == 1


def _concrete_transitions(alias: Any) -> set[type]:
    """Every concrete transition ``alias`` admits, through the union aliases.

    Derived from the algebra rather than restated, so a transition added to it
    joins the expectation below without anyone remembering to say so.
    """
    value = getattr(alias, "__value__", alias)
    found: set[type] = set()
    for member in get_args(value):
        if isinstance(member, type):
            found.add(member)
        else:
            found |= _concrete_transitions(member)
    return found


def test_the_logger_answers_every_transition_the_algebra_admits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The closure claim, at runtime and in one place: the event union is what a
    # consumer has to be exhaustive over, and this is the consumer that is. The
    # stream half has no emitter until streaming itself exists, which is exactly
    # why the closure needs stating here rather than being a byproduct of some
    # suite that happens to drive every kind of work.
    every: list[ExecutionEvent] = [
        ReadStarted(EXECUTION.id, 1, 1, None, "Account", "TYPED"),
        ReadFinished(EXECUTION.id, 2, 1, None, ReadCompleted()),
        WriteBatchStarted(EXECUTION.id, 3, 2, 1, "read_dependency"),
        WriteBatchFinished(EXECUTION.id, 4, 2, 1, WriteBatchCompleted()),
        DatabaseCallStarted(EXECUTION.id, 5, 3, 2, "Account", "WRITE", STATEMENT),
        DatabaseCallFinished(EXECUTION.id, 6, 3, 2, STATEMENT, 9, DatabaseWriteCompleted(1)),
        TransactionInvocationStarted(EXECUTION.id, 7, 4, 1, JoinedInvocation()),
        TransactionInvocationFinished(EXECUTION.id, 8, 4, 1, JoinedInvocationReturned()),
        TransactionAttemptStarted(EXECUTION.id, 9, 5, 1),
        TransactionAttemptFinished(EXECUTION.id, 10, 5, 1, AttemptCommitted()),
        SnapshotStreamStarted(EXECUTION.id, 11, 6, 1, "Account", "ROWS", 100),
        SnapshotStreamFinished(EXECUTION.id, 12, 6, 1, StreamExhausted()),
        StreamBatchStarted(EXECUTION.id, 13, 7, 6),
        StreamBatchFinished(EXECUTION.id, 14, 7, 6, StreamBatchCompleted()),
    ]
    assert {type(event) for event in every} == _concrete_transitions(ExecutionEvent)

    records = _records(caplog, every)
    assert len({record.fields["transition"] for record in records}) == len(every)


def test_a_handler_error_is_logged_correlation_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = _logger()
    provider = LoggingLifecycleProvider(logger, detail="DIAGNOSTIC")
    error = ExecutionLifecycleHandlerError(
        execution_id=EXECUTION.id,
        sequence=3,
        activity_id=2,
        handler_type="app.metrics.Exporter",
        fanout_path=(1, 0),
        diagnostic=diagnostic_for(RuntimeError("the exporter queue is full")),
    )
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        provider.report_handler_error(error)
    (record,) = [_written(captured) for captured in caplog.records]
    assert record.level == logging.ERROR
    assert record.message == "parallax execution lifecycle handler error"
    assert record.fields["handler_type"] == "app.metrics.Exporter"
    assert record.fields["fanout_path"] == (1, 0)
    assert record.fields["error_message"] == "the exporter queue is full"
    assert "transition" not in record.fields, "a report is not a transition of the stream"


def test_a_logger_below_the_level_is_told_nothing(caplog: pytest.LogCaptureFixture) -> None:
    logger = _logger(logging.WARNING)
    handler = LoggingLifecycleProvider(logger).open(EXECUTION)
    assert handler is not None
    with caplog.at_level(logging.WARNING, logger=logger.name):
        handler.handle(ReadStarted(EXECUTION.id, 1, 1, None, "Account", "TYPED"))
        handler.handle(ReadFinished(EXECUTION.id, 2, 1, None, ReadCompleted()))
    assert caplog.records == []


def test_only_a_root_activity_or_an_attempt_finishing_is_worth_more_than_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The premise the level guard rests on, graded over every shape that can be
    # worth more than DEBUG rather than asserted in a docstring. The guard skips
    # describing a transition when the Logger would keep no DEBUG record, so a
    # level above DEBUG reaching any OTHER shape would be a record silently lost.
    root = _failure("the root failed")
    for record in _records(
        caplog,
        [
            ReadStarted(EXECUTION.id, 1, 1, None, "Account", "TYPED"),
            ReadFinished(EXECUTION.id, 2, 1, None, ReadFailed(root)),
            ReadFinished(EXECUTION.id, 3, 2, 1, ReadFailed(root)),
            WriteBatchFinished(EXECUTION.id, 4, 3, 1, WriteBatchFailed(root)),
            DatabaseCallFinished(
                EXECUTION.id, 5, 4, 3, STATEMENT, 9, DatabaseCallFailed(_DATABASE_FAILURE)
            ),
            TransactionInvocationFinished(EXECUTION.id, 6, 1, None, OuterInvocationFailed(root)),
            TransactionInvocationFinished(EXECUTION.id, 7, 5, 1, JoinedInvocationRaised(root)),
            TransactionAttemptStarted(EXECUTION.id, 8, 6, 1),
            TransactionAttemptFinished(
                EXECUTION.id, 9, 6, 1, AttemptRolledBack(_attempt_failure(retry_eligible=True))
            ),
            TransactionAttemptFinished(
                EXECUTION.id, 10, 7, 1, AttemptRolledBack(_attempt_failure(retry_eligible=False))
            ),
            TransactionAttemptFinished(
                EXECUTION.id,
                11,
                8,
                1,
                AttemptRollbackFailed(
                    _attempt_failure(retry_eligible=True), diagnostic_for(RuntimeError("stuck"))
                ),
            ),
            SnapshotStreamFinished(EXECUTION.id, 12, 9, 1, StreamFailed(root)),
            StreamBatchFinished(EXECUTION.id, 13, 10, 9, StreamBatchFailed(root)),
        ],
    ):
        above_debug = record.level > logging.DEBUG
        root_activity = record.fields["parent_activity"] is None
        attempt = record.fields["transition"] == "transactionAttemptFinished"
        assert not above_debug or root_activity or attempt, record.fields["transition"]


def test_a_transition_the_logger_would_drop_is_never_described(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The saving, stated as the absence of work rather than as a duration: a
    # Logger that keeps no DEBUG record makes no field mapping for a transition
    # that could only have been DEBUG. Remove the guard and the count is three.
    monkeypatch.setattr(_logging_module, "_rendered", _describes_nothing)
    handler = LoggingLifecycleProvider(_logger(logging.WARNING)).open(EXECUTION)
    assert handler is not None
    handler.handle(ReadStarted(EXECUTION.id, 1, 2, 1, "Account", "TYPED"))
    handler.handle(DatabaseCallStarted(EXECUTION.id, 2, 3, 2, "Account", "READ", STATEMENT))
    handler.handle(ReadFinished(EXECUTION.id, 3, 2, 1, ReadCompleted()))

    with pytest.raises(_Described, match="ReadFinished"):
        handler.handle(ReadFinished(EXECUTION.id, 4, 1, None, ReadCompleted()))


def test_a_logger_that_emits_what_its_level_excludes_is_still_told_everything() -> None:
    # The guard's premise is a property of `logging.Logger.log` rather than of
    # every Logger an application may configure: a subclass whose `log` emits
    # what it is handed receives a DEBUG record today at a level that keeps
    # none, and describing nothing for it would DELETE that record rather than
    # skip building one nobody would see. So the guard is not taken at all for
    # a Logger that does not ask its own level first.
    class _Unconditional(logging.Logger):
        def log(self, level: int, msg: object, *args: object, **kwargs: Any) -> None:
            extra = kwargs.get("extra")
            self.handle(
                self.makeRecord(self.name, level, __file__, 0, msg, args, None, extra=extra)
            )

    logger = _Unconditional(f"parallax.test.{uuid4().hex}")
    logger.setLevel(logging.CRITICAL)
    collected = _Collecting()
    logger.addHandler(collected)
    handler = LoggingLifecycleProvider(logger).open(EXECUTION)
    assert handler is not None
    handler.handle(ReadStarted(EXECUTION.id, 1, 2, 1, "Account", "TYPED"))

    written = [_written(record) for record in collected.records]
    assert [record.level for record in written] == [logging.DEBUG]
    assert written[0].fields["transition"] == "readStarted"


def test_a_logger_carrying_another_loggers_log_is_still_told_everything() -> None:
    # Being the standard implementation is not enough; it has to be the standard
    # implementation of THIS Logger. A Logger carrying another one's bound `log`
    # runs `logging.Logger.log` against the OTHER Logger's level, so the level
    # asked here and the level that decides the record belong to two different
    # objects: a configured CRITICAL in front of a DEBUG target emits the record
    # through the target today, and consulting the front object's level would
    # delete it. Both are configuration an application can reach — a bound method
    # assigned onto an instance is ordinary Python — so the guard reads the
    # receiver as well as the function, and is not taken for a borrowed method.
    target = _logger(logging.DEBUG)
    collected = _Collecting()
    target.addHandler(collected)
    front = _logger(logging.CRITICAL)
    front.log = target.log
    handler = LoggingLifecycleProvider(front).open(EXECUTION)
    assert handler is not None
    handler.handle(ReadStarted(EXECUTION.id, 1, 2, 1, "Account", "TYPED"))

    written = [_written(record) for record in collected.records]
    assert [record.level for record in written] == [logging.DEBUG]
    assert written[0].fields["transition"] == "readStarted"


def test_a_logger_that_answers_its_level_once_is_asked_exactly_once() -> None:
    # The guard asks the Logger a question its own `log` will ask again, which is
    # free only while asking twice answers twice the same. A Logger whose
    # `isEnabledFor` is stateful — a rate limiter, a sampler, a first-of-each-kind
    # filter — answers the second call differently by design, and a guard taking
    # the first answer for itself would leave `log` with the second and lose the
    # record. The number of times such a Logger is consulted is therefore part of
    # what it observes, and it is what it was before any guard existed: once per
    # record.
    class _AnsweredOnce(logging.Logger):
        def __init__(self, name: str) -> None:
            super().__init__(name)
            self.asked = 0

        def isEnabledFor(self, level: int) -> bool:
            self.asked += 1
            return self.asked == 1

    logger = _AnsweredOnce(f"parallax.test.{uuid4().hex}")
    collected = _Collecting()
    logger.addHandler(collected)
    handler = LoggingLifecycleProvider(logger).open(EXECUTION)
    assert handler is not None
    handler.handle(ReadStarted(EXECUTION.id, 1, 2, 1, "Account", "TYPED"))

    written = [_written(record) for record in collected.records]
    assert logger.asked == 1
    assert [record.level for record in written] == [logging.DEBUG]
    assert written[0].fields["transition"] == "readStarted"


def test_a_globally_disabled_logging_system_describes_nothing_either(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `logging.disable` is process-wide and `isEnabledFor` answers it, so asking
    # the Logger rather than reading its level is what makes the guard agree with
    # `Logger.log` under every way a record can be suppressed.
    monkeypatch.setattr(_logging_module, "_rendered", _describes_nothing)
    handler = LoggingLifecycleProvider(_logger()).open(EXECUTION)
    assert handler is not None
    logging.disable(logging.CRITICAL)
    try:
        handler.handle(ReadStarted(EXECUTION.id, 1, 2, 1, "Account", "TYPED"))
    finally:
        logging.disable(logging.NOTSET)


def test_a_handlers_own_level_does_not_decide_whether_a_record_is_built(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The equivalence this rests on is with `Logger.log`, which consults the
    # LOGGER and nothing else; a Handler filters records that already exist. So a
    # Handler set above DEBUG must change nothing about what is built, or a
    # second Handler under the same Logger would stop seeing records it gets
    # today.
    logger = _logger()
    quiet = logging.Handler(logging.ERROR)
    logger.addHandler(quiet)
    try:
        handler = LoggingLifecycleProvider(logger).open(EXECUTION)
        assert handler is not None
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            handler.handle(ReadStarted(EXECUTION.id, 1, 2, 1, "Account", "TYPED"))
    finally:
        logger.removeHandler(quiet)
    assert [record.levelno for record in caplog.records] == [logging.DEBUG]


def test_the_root_summary_totals_survive_a_level_that_dropped_every_debug_record() -> None:
    # Where the guard had to go, and why it is AFTER the counters rather than
    # before them: the summary reports the work the whole operation did, so a
    # total that counted only the transitions somebody logged would be wrong at
    # every production level — and an ERROR Logger is one that describes three
    # of these fourteen events and keeps one.
    def totals(level: int) -> tuple[dict[str, object], int]:
        logger = _logger(level)
        collected = _Collecting()
        logger.addHandler(collected)
        port = RecordingPort(rows=[NEW_ROW])
        port.txn_faults = [deadlock(), deadlock()]
        db = _db(port, LoggingLifecycleProvider(logger))
        try:
            with pytest.raises(DatabaseError):
                db.transact(lambda tx: tx.insert(new_account()), retries=1)
        finally:
            logger.removeHandler(collected)
        written = [_written(record) for record in collected.records]
        summary = written[-1]
        assert summary.level == logging.ERROR
        assert summary.fields["transition"] == "transactionInvocationFinished"
        totalled = {key: value for key, value in summary.fields.items() if key.startswith("total_")}
        assert isinstance(totalled.pop("total_database_duration_ns"), int), (
            "a measured duration accumulates from the same events but is not a count of them"
        )
        return totalled, len(written)

    described, every_record = totals(logging.DEBUG)
    assert described["total_events"] == 14
    assert every_record == 14

    quiet, one_record = totals(logging.ERROR)
    assert one_record == 1, "the failed root is the only record an ERROR Logger keeps"
    assert quiet == described


def test_a_whole_transaction_through_connect_reads_as_one_operation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # End to end through the seam an application installs: the levels an
    # operator would filter on, over a retry that succeeded, from a real
    # ``db.transact``.
    logger = _logger()
    port = RecordingPort(rows=[NEW_ROW])
    port.txn_faults.append(deadlock())
    db = _db(port, LoggingLifecycleProvider(logger))

    def body(tx: Transaction) -> None:
        tx.insert(new_account())

    with caplog.at_level(logging.DEBUG, logger=logger.name):
        db.transact(body)

    written = [_written(record) for record in caplog.records]
    filtered = [(record.level, record.fields["transition"]) for record in written]
    assert (logging.WARNING, "transactionAttemptFinished") in filtered
    assert filtered[-1] == (logging.INFO, "transactionInvocationFinished")
    summary = written[-1].fields
    assert summary["total_attempts"] == 2
    assert summary["total_write_batches"] == 2
    assert summary["total_affected_rows"] == 2
    assert UUID(str(summary["execution_id"])).version == 4
