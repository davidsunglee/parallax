"""Transaction execution provenance (m-execution-log), Docker-free.

Two halves. The record's own algebra — trace/batch causality, the non-empty
invariant, round-trip counting, the detached failure, the derived call view, and
a Transaction Result's execution refusals — is driven through
:mod:`parallax.core.execution_log` directly. The composition — that a retry's
attempts share ONE log, that a joined body appends to the outer one, that a
shortfall names the completed call it rejected — is driven end to end through the
real `db.transact` over the recording fake port, because that composition is
exactly what no unit of the module can state on its own.
"""

from __future__ import annotations

import gc
import weakref
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

import pytest
from _transact_support import (
    NEW_ROW,
    RecordingPort,
    account_db,
    deadlock,
    grace,
    new_account,
)

from _support import mirrored_models as mm
from parallax.conformance import execution_log_stories
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.execution_log import (
    AttemptRecorder,
    DatabaseCall,
    DatabaseCallFailed,
    ExecutionLog,
    ExecutionLogBuilder,
    ReadCompleted,
    ReadTrace,
    RetryPolicy,
    SealedExecutionLogError,
    TraceRecorder,
    TransactionInProgressError,
    TransactionNotCommittedError,
    TransactionResult,
    WriteBatchTrace,
    WriteCompleted,
)
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import MissingTargetError, OptimisticLockConflictError

_STATEMENT = LoweredStatement("select 1", (1,))
_OTHER_STATEMENT = LoweredStatement("update account set balance = ?", (2,))
_ACCOUNT_IDENTITY = EntityIdentity(namespace="parallax.compatibility", name="Account")
# The `m-execution-log-007` target row as the port returns it (account.yaml id 2).
_LINUS_ROW: Row = {"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}


def _builder() -> ExecutionLogBuilder:
    return ExecutionLogBuilder(
        concurrency="locking",
        retry_policy=RetryPolicy(max_retries=10, retry_optimistic_conflicts=False),
    )


def _opened() -> ExecutionLogBuilder:
    builder = _builder()
    builder.attempt_opened()
    return builder


# --------------------------------------------------------------------------- #
# The record's own algebra.                                                     #
# --------------------------------------------------------------------------- #
def test_an_attempt_is_active_before_its_body_runs() -> None:
    builder = _opened()
    log = builder.view()
    assert log.final_attempt.status == "active"
    assert log.committed_attempt is None
    assert not log.is_sealed
    assert log.concurrency == "locking"
    assert log.retry_policy == RetryPolicy(max_retries=10, retry_optimistic_conflicts=False)
    assert "attempts=1" in repr(log)
    assert "status='active'" in repr(log.final_attempt)


def test_a_flush_that_reached_no_call_appends_no_trace() -> None:
    builder = _opened()
    with builder.current.write_batch("finalization"):
        pass
    with builder.current.read_trace():
        pass
    assert builder.view().final_attempt.traces == ()
    assert builder.view().round_trips == 0


def test_an_announced_final_batch_carries_its_phase_before_it_is_planned() -> None:
    builder = _opened()
    builder.current.write_batch_starting("finalization")
    builder.current.failed(RuntimeError("planning the final batch failed"))
    failure = builder.view().final_attempt.failure
    assert failure is not None
    assert (failure.phase, failure.database_call) == ("finalization", None)
    assert builder.view().final_attempt.traces == ()


def test_an_announced_dependency_batch_leaves_the_attempt_in_the_body_phase() -> None:
    builder = _opened()
    builder.current.write_batch_starting("read_dependency")
    builder.current.failed(RuntimeError("planning the read-forced batch failed"))
    failure = builder.view().final_attempt.failure
    assert failure is not None and failure.phase == "body"


def test_a_read_result_and_the_attempt_reference_ONE_trace_object() -> None:
    builder = _opened()
    with builder.current.read_trace() as recorder:
        recorder.completed(_STATEMENT, "read", 7, ReadCompleted(2))
        surfaced = recorder.read_trace()
    assert builder.view().final_attempt.traces[0] is surfaced


def test_a_dependency_batch_stands_immediately_before_the_read_it_enabled() -> None:
    builder = _opened()
    with builder.current.write_batch("read_dependency") as batch:
        batch.completed(_STATEMENT, "write", 1, WriteCompleted(1))
    with builder.current.read_trace() as read:
        read.completed(_STATEMENT, "read", 1, ReadCompleted(1))
    traces = builder.view().final_attempt.traces
    assert [type(trace).__name__ for trace in traces] == ["WriteBatchTrace", "ReadTrace"]
    assert isinstance(traces[0], WriteBatchTrace) and traces[0].trigger == "read_dependency"


def test_a_failed_call_counts_one_round_trip_and_keeps_only_its_diagnostic() -> None:
    builder = _opened()
    error = deadlock()
    with pytest.raises(DatabaseError), builder.current.write_batch("finalization") as batch:
        batch.failed(_STATEMENT, "write", 3, error)
        raise error
    builder.current.failed(error)
    call = builder.view().final_attempt.calls[0]
    assert call.completion == DatabaseCallFailed("deadlock", "40P01", "deadlock detected")
    assert builder.view().round_trips == 1
    failure = builder.view().final_attempt.failure
    assert failure is not None
    assert (failure.phase, failure.code, failure.retry_eligible) == ("finalization", "40P01", False)
    assert failure.database_call is call
    # Detached: nothing on the record reaches the exception, its traceback, the
    # port, or any transaction state.
    assert error not in gc.get_referents(failure)
    assert not [value for value in gc.get_referents(failure) if isinstance(value, BaseException)]


def test_a_completed_call_that_fell_short_stays_a_completion() -> None:
    builder = _opened()
    shortfall = MissingTargetError(_ACCOUNT_IDENTITY, _key_target(), 1, 0)
    with pytest.raises(MissingTargetError), builder.current.write_batch("finalization") as batch:
        batch.completed(_STATEMENT, "write", 2, WriteCompleted(0))
        with batch.enforcing():
            raise shortfall
    builder.current.failed(shortfall)
    attempt = builder.view().final_attempt
    assert attempt.calls[0].completion == WriteCompleted(0)
    failure = attempt.failure
    assert failure is not None
    assert failure.code == "missing-target"
    assert failure.database_call is attempt.calls[0]


def test_only_a_call_the_failure_is_about_is_the_call_the_failure_names() -> None:
    # A dependency batch fails and the read that forced it out unwinds through
    # its own bracket, which recorded nothing: the empty bracket must not erase
    # the write call that actually failed.
    builder = _opened()
    error = deadlock()
    with (
        pytest.raises(DatabaseError),
        builder.current.read_trace(),
        builder.current.write_batch("read_dependency") as batch,
    ):
        batch.failed(_STATEMENT, "write", 1, error)
        raise error
    builder.current.failed(error)
    attempt = builder.view().final_attempt
    failure = attempt.failure
    assert failure is not None
    assert failure.database_call is attempt.calls[0]

    # The mirror image: a conversion failure after a call the port completed is
    # not about that call, so it names none.
    other = _opened()
    conversion = RuntimeError("the row could not be materialized")
    with pytest.raises(RuntimeError), other.current.read_trace() as read:
        read.completed(_STATEMENT, "read", 1, ReadCompleted(1))
        raise conversion
    other.current.failed(conversion)
    conversion_failure = other.view().final_attempt.failure
    assert conversion_failure is not None
    assert conversion_failure.database_call is None


def test_a_failure_the_caller_swallowed_is_not_inherited_by_what_fails_later() -> None:
    # The body catches the failed call and carries on, then fails for an
    # unrelated reason: the later failure is an arbitrary callback failure and
    # must name no call, however recently a call of its own failed.
    builder = _opened()
    caught = deadlock()
    with builder.current.write_batch("read_dependency") as batch:
        try:
            batch.failed(_STATEMENT, "write", 1, caught)
            raise caught
        except DatabaseError:
            pass
    unrelated = RuntimeError("the callback rejected the value it read")
    builder.current.failed(unrelated)
    failure = builder.view().final_attempt.failure
    assert failure is not None
    assert (failure.phase, failure.database_call) == ("body", None)

    # Same swallowed call, but the durability boundary is what fails: a commit
    # failure names none either, and the phase is the only thing that moved.
    committing = _opened()
    swallowed = deadlock()
    with committing.current.write_batch("finalization") as batch:
        try:
            batch.failed(_STATEMENT, "write", 1, swallowed)
            raise swallowed
        except DatabaseError:
            pass
    committing.current.entering_commit()
    committing.current.failed(RuntimeError("the commit was refused"))
    commit_failure = committing.view().final_attempt.failure
    assert commit_failure is not None
    assert (commit_failure.phase, commit_failure.database_call) == ("commit", None)


def test_a_rollback_only_refusal_names_the_call_the_doomed_failure_was_about() -> None:
    # The refusal is the boundary reporting a decision already made, so it is
    # about whatever doomed the transaction — here a call the port could not
    # complete, reached through the refusal's declared cause.
    from parallax.core.unit_work import RollbackOnlyError

    builder = _opened()
    error = deadlock()
    with builder.current.write_batch("read_dependency") as batch:
        try:
            batch.failed(_STATEMENT, "write", 1, error)
            raise error
        except DatabaseError:
            pass
    refusal = RollbackOnlyError("transaction is rollback-only; commit refused")
    refusal.__cause__ = error
    builder.current.failed(refusal)
    attempt = builder.view().final_attempt
    failure = attempt.failure
    assert failure is not None
    assert failure.database_call is attempt.calls[0]


def test_a_later_failed_call_does_not_displace_the_one_the_refusal_is_about() -> None:
    # A joined scope's failed call dooms the transaction and its caller swallows
    # it; a second call then fails and is swallowed too. The boundary's refusal
    # reports the decision the FIRST failure made, so the attempt names that
    # failure's call — recency is not what attribution is held against.
    from parallax.core.unit_work import RollbackOnlyError

    builder = _opened()
    doomed = deadlock()
    with builder.current.write_batch("read_dependency") as batch:
        try:
            batch.failed(_STATEMENT, "write", 1, doomed)
            raise doomed
        except DatabaseError:
            pass
    later = deadlock()
    with builder.current.write_batch("read_dependency") as batch:
        try:
            batch.failed(_OTHER_STATEMENT, "write", 1, later)
            raise later
        except DatabaseError:
            pass
    refusal = RollbackOnlyError("transaction is rollback-only; commit refused")
    refusal.__cause__ = doomed
    builder.current.failed(refusal)
    attempt = builder.view().final_attempt
    failure = attempt.failure
    assert failure is not None
    assert len(attempt.calls) == 2
    assert failure.database_call is attempt.calls[0]


def test_a_callback_failure_raised_from_a_swallowed_call_still_names_none() -> None:
    # `raise ... from` states an adjacency the CALLER chose, and what escapes is
    # arbitrary callback work, which references no call. Only a rollback-only
    # refusal — the boundary restating a decision an earlier failure made — is
    # read through to the failure behind it.
    builder = _opened()
    caught = deadlock()
    with builder.current.write_batch("read_dependency") as batch:
        try:
            batch.failed(_STATEMENT, "write", 1, caught)
            raise caught
        except DatabaseError as exc:
            rejected = RuntimeError("the callback gave up on the write")
            rejected.__cause__ = exc
    builder.current.failed(rejected)
    failure = builder.view().final_attempt.failure
    assert failure is not None
    assert (failure.phase, failure.code, failure.database_call) == ("body", None, None)


def test_an_unrelated_failure_crossing_the_enforcement_bracket_names_no_call() -> None:
    # `enforcing` brackets the Affected Rows Policy verdict on a completed call.
    # Anything else unwinding through it — an interrupt, a defect in the enforcer
    # — is not a verdict about that call, so the bracket's adjacency alone
    # attributes nothing.
    builder = _opened()
    interrupted = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt), builder.current.write_batch("finalization") as batch:
        batch.completed(_STATEMENT, "write", 1, WriteCompleted(1))
        with batch.enforcing():
            raise interrupted
    builder.current.failed(interrupted)
    attempt = builder.view().final_attempt
    failure = attempt.failure
    assert failure is not None
    assert attempt.calls[0].completion == WriteCompleted(1)
    assert failure.database_call is None


def test_a_self_caused_refusal_is_recorded_rather_than_recursed_on() -> None:
    # Python permits a cyclic declared cause. The log is an observer: reading a
    # failure's code and its call through such a chain must terminate, or the
    # observer would replace the very failure it is recording.
    from parallax.core.unit_work import RollbackOnlyError

    builder = _opened()
    refusal = RollbackOnlyError("transaction is rollback-only; commit refused")
    refusal.__cause__ = refusal
    builder.current.failed(refusal)
    attempt = builder.view().final_attempt
    failure = attempt.failure
    assert attempt.status == "rolled_back"
    assert failure is not None
    assert (failure.code, failure.database_call) == (None, None)


def test_a_live_log_does_not_pin_the_exception_a_swallowed_call_raised() -> None:
    # The log is reachable while the body still runs, so a caller that catches a
    # failed call and keeps reading its log must not thereby hold that exception,
    # its traceback, and every frame and local they close over alive until the
    # transaction terminates.
    builder = _opened()

    def swallow_a_failed_call() -> weakref.ref[BaseException]:
        error = deadlock()
        with builder.current.write_batch("read_dependency") as batch:
            try:
                batch.failed(_STATEMENT, "write", 1, error)
                raise error
            except DatabaseError:
                pass
        return weakref.ref(error)

    swallowed = swallow_a_failed_call()
    gc.collect()
    assert swallowed() is None
    assert not builder.view().is_sealed
    assert builder.view().final_attempt.status == "active"
    # A released exception cannot be the one now escaping, so the attempt that
    # goes on to fail for another reason names no call.
    builder.current.failed(RuntimeError("the callback rejected the value it read"))
    failure = builder.view().final_attempt.failure
    assert failure is not None and failure.database_call is None


def _key_target() -> Any:
    from parallax.core.unit_work import KeyTarget

    return KeyTarget((AttributeIdentity(entity=_ACCOUNT_IDENTITY, name="id"),), ((1,),))


def test_the_classifier_verdict_is_applied_to_an_already_recorded_failure() -> None:
    builder = _opened()
    conflict = OptimisticLockConflictError(_ACCOUNT_IDENTITY, _key_target(), 1, 0)
    builder.current.failed(conflict)
    builder.attempt_failed(conflict, retry_eligible=True)
    failure = builder.view().final_attempt.failure
    assert failure is not None
    assert failure.retry_eligible is True
    assert failure.code == "optimistic-lock-conflict"
    assert builder.view().final_attempt.status == "rolled_back"


def test_the_first_recorded_failure_wins_and_a_commit_phase_names_no_call() -> None:
    builder = _opened()
    with builder.current.read_trace() as read:
        read.completed(_STATEMENT, "read", 1, ReadCompleted(1))
    builder.current.entering_commit()
    first = RuntimeError("the durability boundary failed")
    builder.current.failed(first)
    builder.current.failed(RuntimeError("a second, later refusal"))
    failure = builder.view().final_attempt.failure
    assert failure is not None
    assert (failure.phase, failure.code, failure.database_call) == ("commit", None, None)
    assert failure.message == "the durability boundary failed"
    assert failure.error_type == "RuntimeError"


def test_a_rollback_only_refusal_reports_the_code_of_the_failure_that_doomed_it() -> None:
    from parallax.core.unit_work import RollbackOnlyError

    builder = _opened()
    doomed = RollbackOnlyError("transaction is rollback-only; commit refused")
    doomed.__cause__ = deadlock()
    builder.current.failed(doomed)
    failure = builder.view().final_attempt.failure
    assert failure is not None and failure.code == "40P01"

    bare = RollbackOnlyError("no cause at all")
    other = _opened()
    other.current.failed(bare)
    bare_failure = other.view().final_attempt.failure
    assert bare_failure is not None and bare_failure.code is None


def test_the_flattened_calls_are_a_derived_view_over_the_ordered_traces() -> None:
    builder = _opened()
    with builder.current.write_batch("read_dependency") as batch:
        batch.completed(_STATEMENT, "write", 1, WriteCompleted(1))
        batch.completed(_STATEMENT, "write", 1, WriteCompleted(1))
    with builder.current.read_trace() as read:
        read.completed(_STATEMENT, "read", 1, ReadCompleted(3))
    calls = builder.view().final_attempt.calls
    assert len(calls) == 3
    assert calls[2].kind == "read"
    assert calls[-1] is calls[2]
    assert [call.kind for call in calls] == ["write", "write", "read"]
    assert calls[1:] == (calls[1], calls[2])
    assert calls[-3] is calls[0]
    with pytest.raises(IndexError):
        _ = calls[3]
    with pytest.raises(IndexError):
        _ = calls[-4]
    # Derived, not stored: the view holds the traces themselves, so it retains no
    # per-call collection of its own.
    assert not any(isinstance(value, tuple) and value and value[0] is calls[0] for value in ())


def test_round_trips_sum_at_every_level_and_ignore_the_transaction_boundary() -> None:
    trace = ReadTrace((DatabaseCall(_STATEMENT, "read", 1, ReadCompleted(9)),))
    assert trace.round_trips == 1
    batch = WriteBatchTrace(
        "finalization", (DatabaseCall(_STATEMENT, "write", 1, WriteCompleted(1)),) * 2
    )
    assert batch.round_trips == 2


def test_a_transaction_result_refuses_its_execution_view_in_two_distinct_states() -> None:
    builder = _opened()
    live = TransactionResult(value=None, execution_log=builder.view())
    with pytest.raises(TransactionInProgressError):
        _ = live.execution
    builder.current.failed(RuntimeError("aborted"))
    builder.seal()
    with pytest.raises(TransactionNotCommittedError):
        _ = live.execution
    committed = _opened()
    committed.current.committed()
    committed.seal()
    result = TransactionResult(value=1, execution_log=committed.view())
    assert result.execution is committed.view().committed_attempt


def test_a_trace_recorder_seals_once_and_answers_the_same_object() -> None:
    recorder = TraceRecorder()
    assert not recorder.has_calls
    recorder.completed(_STATEMENT, "read", 1, ReadCompleted(0))
    assert recorder.read_trace() is recorder.read_trace()
    batch = TraceRecorder()
    batch.completed(_STATEMENT, "write", 1, WriteCompleted(1))
    assert batch.write_batch_trace("finalization") is batch.write_batch_trace("finalization")


def test_a_sealed_trace_recorder_refuses_a_later_call_rather_than_dropping_it() -> None:
    recorder = TraceRecorder()
    recorder.completed(_STATEMENT, "read", 1, ReadCompleted(0))
    trace = recorder.read_trace()
    with pytest.raises(SealedExecutionLogError):
        recorder.completed(_STATEMENT, "read", 1, ReadCompleted(1))
    assert trace.round_trips == 1


def test_a_sealed_log_refuses_every_further_write_to_itself_and_its_attempts() -> None:
    builder = _opened()
    recorder = builder.current
    builder.seal()
    with pytest.raises(SealedExecutionLogError):
        builder.attempt_opened()
    with pytest.raises(SealedExecutionLogError):
        recorder.committed()
    with pytest.raises(SealedExecutionLogError):
        recorder.entering_commit()
    with pytest.raises(SealedExecutionLogError):
        recorder.failed(RuntimeError("late"))
    with pytest.raises(SealedExecutionLogError):
        recorder.write_batch_starting("finalization")
    with pytest.raises(SealedExecutionLogError), recorder.read_trace():
        pass  # pragma: no cover - the bracket is refused before it opens
    assert builder.view().final_attempt.status == "active"


def test_an_impossible_kind_and_completion_pair_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="'read' Database Call admits"):
        DatabaseCall(_STATEMENT, "read", 1, WriteCompleted(1))
    with pytest.raises(ValueError, match="'write' Database Call admits"):
        DatabaseCall(_STATEMENT, "write", 1, ReadCompleted(1))
    failed = DatabaseCallFailed(None, None, "either kind admits a failed call")
    assert DatabaseCall(_STATEMENT, "read", 1, failed).completion is failed
    assert DatabaseCall(_STATEMENT, "write", 1, failed).completion is failed


def test_an_empty_trace_is_refused_because_a_trace_proves_work_that_happened() -> None:
    with pytest.raises(ValueError, match="Read Trace proves work"):
        ReadTrace(())
    with pytest.raises(ValueError, match="Write Batch Trace proves work"):
        WriteBatchTrace("finalization", ())


def test_an_attempt_recorder_writes_through_the_view_it_was_built_from() -> None:
    builder = _opened()
    attempt = builder.view().final_attempt
    recorder = AttemptRecorder(_attempt_state(attempt))
    recorder.committed()
    assert attempt.status == "committed"


def _attempt_state(attempt: Any) -> Any:
    # The view and its recorder share one state object, which is module-private
    # by construction; this reaches it the way the module's own builder does.
    return attempt._state


# --------------------------------------------------------------------------- #
# The composition: one log across a real `db.transact` invocation.              #
# --------------------------------------------------------------------------- #
class _WriteFaultPort(RecordingPort):
    """A recording port whose next writes fail — the failed-call arrangement
    `RecordingPort` itself has no need for."""

    def __init__(self, *, faults: Sequence[DatabaseError]) -> None:
        super().__init__()
        self.write_faults = list(faults)

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        if self.write_faults:
            raise self.write_faults.pop(0)
        return super().execute_write(sql, binds)


def test_one_log_spans_every_attempt_of_one_invocation() -> None:
    port = _WriteFaultPort(faults=[deadlock()])
    result = account_db(port).transact(lambda tx: tx.insert(new_account()))
    log = result.execution_log
    assert [attempt.status for attempt in log.attempts] == ["rolled_back", "committed"]
    assert log.committed_attempt is log.attempts[1]
    assert log.final_attempt is log.attempts[1]
    assert log.is_sealed
    # The failed call counts; begin / commit / rollback do not.
    assert log.round_trips == 2
    failure = log.attempts[0].failure
    assert failure is not None
    assert (failure.phase, failure.retry_eligible, failure.code) == ("finalization", True, "40P01")
    assert failure.database_call is log.attempts[0].calls[0]
    assert result.execution is log.attempts[1]


def test_a_failed_invocation_leaves_its_log_readable_from_the_retained_transaction() -> None:
    port = _WriteFaultPort(faults=[deadlock()] * 3)
    held: list[ExecutionLog] = []

    def body(tx: Any) -> None:
        held.append(tx.execution_log)
        tx.insert(new_account())

    with pytest.raises(DatabaseError):
        account_db(port).transact(body, retries=1)
    log = held[0]
    assert log.is_sealed
    assert len(log.attempts) == 2
    assert all(attempt.status == "rolled_back" for attempt in log.attempts)
    assert all(
        attempt.failure is not None and attempt.failure.retry_eligible for attempt in log.attempts
    )


def test_a_dependent_read_forces_a_batch_the_log_places_before_its_trace() -> None:
    port = RecordingPort(rows=[NEW_ROW])

    def body(tx: Any) -> None:
        tx.insert(new_account())
        tx.find(mm.Account.where(mm.Account.id == 7)).results()

    log = account_db(port).transact(body).execution_log
    traces = log.attempts[0].traces
    assert [type(trace).__name__ for trace in traces] == ["WriteBatchTrace", "ReadTrace"]
    assert isinstance(traces[0], WriteBatchTrace) and traces[0].trigger == "read_dependency"
    assert isinstance(traces[1], ReadTrace)
    assert "for share of t0" in traces[1].calls[0].statement.sql
    assert log.round_trips == 2


def test_a_snapshot_and_its_attempt_reference_the_same_read_trace() -> None:
    port = RecordingPort(rows=[dict(grace().__dict__ or {}) or NEW_ROW])

    def body(tx: Any) -> Any:
        return tx.find(mm.Account.where(mm.Account.id == 7))

    result = account_db(port).transact(body)
    assert result.value.execution is result.execution.traces[0]


def test_a_standalone_read_carries_its_own_trace_and_belongs_to_no_attempt() -> None:
    port = RecordingPort(rows=[NEW_ROW])
    snapshot = account_db(port).find(mm.Account.where(mm.Account.id == 7))
    assert snapshot.execution.round_trips == 1
    assert snapshot.execution.calls[0].completion == ReadCompleted(1)
    assert snapshot.execution.calls[0].duration_ns >= 0


def test_a_joined_body_appends_to_the_outer_log_rather_than_opening_a_second() -> None:
    port = RecordingPort(rows=[NEW_ROW])
    db = account_db(port)

    def outer(tx: Any) -> Any:
        joined = db.transact(lambda inner: inner.insert(new_account()))
        assert joined.execution_log is tx.execution_log
        with pytest.raises(TransactionInProgressError):
            _ = joined.execution
        return joined

    result = db.transact(outer)
    assert len(result.execution_log.attempts) == 1
    assert result.value.execution_log is result.execution_log
    # The joined result's own view opens once the outer boundary commits.
    assert result.value.execution is result.execution


def test_a_zero_row_shortfall_names_the_completed_call_the_enforcement_rejected() -> None:
    port = RecordingPort(rows=[NEW_ROW], write_affected=0)
    held: list[ExecutionLog] = []

    def body(tx: Any) -> None:
        held.append(tx.execution_log)
        current = tx.find(mm.Account.where(mm.Account.id == 7)).result()
        tx.update(current.edit(balance=Decimal("9.99")))

    with pytest.raises(OptimisticLockConflictError):
        account_db(port).transact(body, concurrency="optimistic")
    attempt = held[0].final_attempt
    assert attempt.status == "rolled_back"
    failure = attempt.failure
    assert failure is not None
    assert (failure.phase, failure.code, failure.retry_eligible) == (
        "finalization",
        "optimistic-lock-conflict",
        False,
    )
    offending = failure.database_call
    assert offending is attempt.calls[-1]
    assert offending is not None and offending.completion == WriteCompleted(0)


def test_a_read_that_failed_still_records_the_call_it_made() -> None:
    class _ReadFaultPort(RecordingPort):
        def execute(
            self,
            sql: str,
            binds: Sequence[Bind],
            document_reads: Sequence[tuple[int, int]] = (),
        ) -> list[Row]:
            del sql, binds, document_reads
            raise deadlock()

        def transaction[T](self, body: Callable[[DbPort], T]) -> T:
            return body(self)

    port = _ReadFaultPort()
    held: list[ExecutionLog] = []

    def body(tx: Any) -> None:
        held.append(tx.execution_log)
        tx.find(mm.Account.where(mm.Account.id == 7))

    with pytest.raises(DatabaseError):
        account_db(port).transact(body, retries=0)
    attempt = held[0].final_attempt
    assert attempt.round_trips == 1
    assert isinstance(attempt.calls[0].completion, DatabaseCallFailed)
    failure = attempt.failure
    assert failure is not None and failure.phase == "body"
    assert failure.database_call is attempt.calls[0]


# --------------------------------------------------------------------------- #
# The joined-lifecycle API-suite stories, driven Docker-free over the recording #
# port. `tests/api/test_execution_log_story.py` runs the SAME functions against #
# real Postgres and grades them against `m-execution-log-007`; this half proves #
# the observations they record are the ones the log actually holds.             #
# --------------------------------------------------------------------------- #
def test_the_joined_story_records_the_live_half_of_the_outer_log() -> None:
    port = RecordingPort(rows=[_LINUS_ROW])
    observed = execution_log_stories.a_joined_unit_of_work_appends_to_the_outer_live_log(
        account_db(port)
    )
    live = observed.live
    assert live.status_while_running == "active"
    assert live.shares_the_outer_log
    assert not live.sealed_while_running
    assert live.execution_refusal == "TransactionInProgressError"
    assert (live.traces_before_join, live.traces_after_join) == (1, 1)
    log = observed.result.execution_log
    assert log.is_sealed
    assert len(log.attempts) == 1
    assert [type(trace).__name__ for trace in observed.result.execution.traces] == [
        "ReadTrace",
        "WriteBatchTrace",
    ]


def test_the_rolled_back_join_story_records_the_second_intermediate_state() -> None:
    port = RecordingPort(rows=[_LINUS_ROW])
    observed = execution_log_stories.a_joined_result_of_a_rolled_back_transaction_has_no_execution(
        account_db(port)
    )
    assert observed.refusal == "TransactionNotCommittedError"
    log = observed.joined.execution_log
    assert log.is_sealed and log.committed_attempt is None
