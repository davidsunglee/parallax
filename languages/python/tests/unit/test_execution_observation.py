"""The adapter's `execution` observation (m-conformance-adapter, m-execution-log).

The renderer that turns the provenance a run PRODUCED into the closed union a
case's `then.execution` authors. Docker-free: the provenance is built here, so
what these pin is the rendering and its two refusals — an attempt the run left
`active`, and a call whose statement index would name no emission — rather than
any execution.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from parallax.conformance import engine
from parallax.core.db_error import DatabaseError
from parallax.core.execution_log import (
    DatabaseCall,
    ExecutionLogBuilder,
    ReadCompleted,
    ReadTrace,
    RetryPolicy,
    TraceRecorder,
    WriteCompleted,
)
from parallax.core.sql_gen import LoweredStatement

_READ = LoweredStatement("select 1", (1,))
_WRITE = LoweredStatement("update account set balance = ?", (2,))


def _emissions(count: int) -> list[engine.Emission]:
    return [engine.Emission("/operation", f"sql-{index}", ()) for index in range(count)]


def _builder(*, concurrency: str = "locking", retries: int = 10) -> ExecutionLogBuilder:
    return ExecutionLogBuilder(
        concurrency=cast("Any", concurrency),
        retry_policy=RetryPolicy(max_retries=retries, retry_optimistic_conflicts=False),
    )


def test_a_standalone_read_renders_the_bare_read_trace_arm() -> None:
    recorder = TraceRecorder()
    recorder.completed(_READ, "read", 5, ReadCompleted(1))
    observed = engine.execution_observation(recorder.read_trace(), _emissions(1))
    assert observed == {
        "readTrace": {
            "calls": [
                {
                    "kind": "read",
                    "completion": {"readCompleted": {"returnedRows": 1}},
                    "statement": 0,
                }
            ],
            "roundTrips": 1,
        }
    }


def test_a_transactional_run_renders_the_whole_log_with_wire_spellings() -> None:
    builder = _builder()
    builder.attempt_opened()
    with builder.current.write_batch("read_dependency") as batch:
        batch.completed(_WRITE, "write", 1, WriteCompleted(1))
    with builder.current.read_trace() as read:
        read.completed(_READ, "read", 1, ReadCompleted(2))
    builder.current.committed()
    builder.seal()

    observed = engine.execution_observation(builder.view(), _emissions(2))
    log = cast("dict[str, Any]", observed["transactionLog"])
    assert log["concurrency"] == "locking"
    assert log["retryPolicy"] == {"maxRetries": 10, "retryOptimisticConflicts": False}
    assert log["roundTrips"] == 2
    attempt = cast("list[dict[str, Any]]", log["attempts"])[0]
    # The wire spells the trigger and the status with hyphens; Python does not.
    assert attempt["status"] == "committed"
    assert attempt["traces"][0]["writeBatch"]["trigger"] == "read-dependency"
    assert attempt["traces"][1]["readTrace"]["calls"][0]["statement"] == 1
    assert "failure" not in attempt


def test_a_rolled_back_attempt_renders_its_failure_and_the_call_it_names() -> None:
    builder = _builder(concurrency="optimistic", retries=1)
    builder.attempt_opened()
    with (
        pytest.raises(RuntimeError),
        builder.current.write_batch("finalization") as batch,
    ):
        batch.completed(_WRITE, "write", 1, WriteCompleted(0))
        with batch.enforcing():
            raise RuntimeError("the enforcement rejected it")
    builder.current.failed(RuntimeError("the enforcement rejected it"))
    builder.attempt_failed(RuntimeError("the enforcement rejected it"), retry_eligible=True)
    builder.seal()

    log = cast("dict[str, Any]", engine.execution_observation(builder.view(), _emissions(1)))
    attempt = cast("list[dict[str, Any]]", log["transactionLog"]["attempts"])[0]
    assert attempt["status"] == "rolled-back"
    # No `code`: the failure carries none, and an absent key is the honest report.
    assert attempt["failure"] == {
        "phase": "finalization",
        "retryEligible": True,
        "databaseCall": 0,
    }


def test_the_call_a_failure_names_is_found_by_identity_rather_than_by_equality() -> None:
    # An EQUAL call is not the referenced call: two runs of one statement whose
    # durations tied would otherwise render the first call's index for a failure
    # about the second, naming the wrong statement while staying in range.
    builder = _builder()
    builder.attempt_opened()
    with builder.current.write_batch("finalization") as batch:
        batch.completed(_WRITE, "write", 1, WriteCompleted(1))
    builder.current.failed(RuntimeError("planning the next batch failed"))
    state = _attempt_state(builder.view().final_attempt)
    state.failure = replace(
        state.failure, database_call=DatabaseCall(_WRITE, "write", 1, WriteCompleted(1))
    )
    builder.seal()

    with pytest.raises(engine.EngineError, match="`databaseCall` index would"):
        engine.execution_observation(builder.view(), _emissions(1))


def _attempt_state(attempt: Any) -> Any:
    # The view and its recorder share one state object, which is module-private
    # by construction; this reaches it the way the module's own builder does.
    return attempt._state


def test_a_failure_carrying_a_provider_code_renders_it_beside_the_phase() -> None:
    from _transact_support import deadlock

    builder = _builder()
    builder.attempt_opened()
    error = deadlock()
    with pytest.raises(DatabaseError), builder.current.write_batch("finalization") as batch:
        batch.failed(_WRITE, "write", 1, error)
        raise error
    builder.current.failed(error)
    builder.attempt_failed(error, retry_eligible=True)
    builder.seal()

    log = cast("dict[str, Any]", engine.execution_observation(builder.view(), _emissions(1)))
    attempt = cast("list[dict[str, Any]]", log["transactionLog"]["attempts"])[0]
    assert attempt["failure"]["code"] == "40P01"


def test_a_lane_with_no_emissions_omits_every_statement_index() -> None:
    builder = _builder()
    builder.attempt_opened()
    with builder.current.write_batch("finalization") as batch:
        batch.completed(_WRITE, "write", 1, WriteCompleted(1))
    builder.current.committed()
    builder.seal()

    log = cast("dict[str, Any]", engine.execution_observation(builder.view(), []))
    call = log["transactionLog"]["attempts"][0]["traces"][0]["writeBatch"]["calls"][0]
    assert call == {"kind": "write", "completion": {"writeCompleted": {"affectedRows": 1}}}


def test_a_failed_call_renders_only_its_portable_category() -> None:
    from _transact_support import deadlock

    recorder = TraceRecorder()
    recorder.failed(_READ, "read", 1, deadlock())
    observed = cast("dict[str, Any]", engine.execution_observation(recorder.read_trace(), []))
    assert observed["readTrace"]["calls"][0]["completion"] == {"failed": {"category": "deadlock"}}


def test_more_calls_than_emissions_is_named_loudly_rather_than_indexed_past_the_end() -> None:
    recorder = TraceRecorder()
    recorder.completed(_READ, "read", 1, ReadCompleted(1))
    recorder.completed(_READ, "read", 1, ReadCompleted(1))
    with pytest.raises(engine.EngineError, match="statement index would name nothing"):
        engine.execution_observation(recorder.read_trace(), _emissions(1))


def test_an_attempt_the_run_left_active_is_refused_rather_than_rendered() -> None:
    builder = _builder()
    builder.attempt_opened()
    with builder.current.read_trace() as read:
        read.completed(_READ, "read", 1, ReadCompleted(1))
    with pytest.raises(engine.EngineError, match="'active' attempt"):
        engine.execution_observation(builder.view(), _emissions(1))


def test_the_renderer_can_never_be_handed_an_empty_read_trace() -> None:
    # The non-empty invariant is a construction-time refusal rather than a rule
    # the renderer restates, so a zero-round-trip trace that looked structurally
    # like a full one can never reach an observation at all.
    with pytest.raises(ValueError, match="Read Trace proves work"):
        ReadTrace(())
