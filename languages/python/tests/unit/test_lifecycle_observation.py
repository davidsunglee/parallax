"""The conformance run observation, over synthetic delivered streams.

`then.statements`, `then.roundTrips`, and `then.executionLifecycle` are three
projections of ONE delivery (`m-execution-lifecycle`), and this is where each is
pinned against events built by hand rather than against events a run happened to
produce: the corpus exercises the transitions its own six cases reach, and the
algebra has fourteen. What the adapter must be able to spell is all of them, so
a transition landing in the union without a portable spelling is a failure here
rather than the day a case first reaches it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from parallax import conformance
from parallax.conformance._lifecycle_observation import (
    LifecycleObservation,
    LifecycleRun,
    StatementIndexError,
    execution_lifecycle_observation,
    lifecycle_run,
)
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
    FailureDiagnostic,
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
from parallax.core.execution_lifecycle._diagnostics import DatabaseFailureDiagnostic
from parallax.core.execution_lifecycle.testing import RecordedRoot
from parallax.core.sql_gen import LoweredStatement

_EXECUTION = uuid4()
_STATEMENT = LoweredStatement("select 1 from account", ())


def _diagnostic(code: str | None = None) -> FailureDiagnostic:
    return FailureDiagnostic(
        qualified_type="builtins.ValueError",
        message="boom",
        code=code,
        stack="",
        message_truncated=False,
        stack_truncated=False,
    )


def _root(kind: str, *events: ExecutionEvent) -> RecordedRoot:
    return RecordedRoot(RootExecution(_EXECUTION, kind), tuple(events))  # pyright: ignore[reportArgumentType] - the kind is the caller's literal


def _roots(observation: dict[str, object]) -> list[dict[str, Any]]:
    """The observation's own roots, typed for a test that reads them by key."""
    return cast("list[dict[str, Any]]", observation["roots"])


def _portable(*events: ExecutionEvent, statements: list[str] | None = None) -> list[dict[str, Any]]:
    observation = execution_lifecycle_observation(
        [_root("READ", *events)], statements if statements is not None else []
    )
    return cast("list[dict[str, Any]]", _roots(observation)[0]["events"])


def _transition(event: ExecutionEvent, statements: list[str] | None = None) -> dict[str, Any]:
    portable = _portable(event, statements=statements)[0]
    return {name: value for name, value in portable.items() if name not in _ENVELOPE}


_ENVELOPE = frozenset({"sequence", "activity", "parent"})


# --- the correlation envelope every event carries -----------------------------


def test_every_event_states_its_correlation_and_names_its_transition() -> None:
    started = ReadStarted(_EXECUTION, 1, 1, None, "Account", "TYPED")
    call = DatabaseCallStarted(_EXECUTION, 2, 2, 1, "Account", "READ", _STATEMENT)
    events = _portable(started, call)
    assert events[0]["sequence"] == 1
    assert events[0]["activity"] == 1
    # `null` on the root activity is the ASSERTION rather than an omission, so
    # the key is present on every event.
    assert events[0]["parent"] is None
    assert events[1]["parent"] == 1
    assert set(events[0]) == {"sequence", "activity", "parent", "readStarted"}


def test_a_root_states_its_kind_and_its_first_observation_index() -> None:
    read = _root("READ", ReadStarted(_EXECUTION, 1, 1, None, "Account", "ROWS"))
    invocation = _root(
        "TRANSACTION_INVOCATION",
        TransactionInvocationStarted(_EXECUTION, 1, 1, None, JoinedInvocation()),
    )
    stream = _root(
        "SNAPSHOT_STREAM", SnapshotStreamStarted(_EXECUTION, 1, 1, None, "Account", "WIRE", 100)
    )
    roots = _roots(execution_lifecycle_observation([read, invocation, stream], []))
    assert [root["execution"] for root in roots] == [1, 2, 3]
    assert [root["kind"] for root in roots] == [
        "read",
        "transaction-invocation",
        "snapshot-stream",
    ]


# --- the portable spelling of every transition the algebra admits --------------


def test_a_read_states_its_target_and_the_interface_that_publishes_it() -> None:
    assert _transition(ReadStarted(_EXECUTION, 1, 1, None, "Account", "TYPED")) == {
        "readStarted": {"target": "Account", "interface": "typed"}
    }
    assert _transition(ReadStarted(_EXECUTION, 1, 1, None, "Account", "WIRE")) == {
        "readStarted": {"target": "Account", "interface": "wire"}
    }
    assert _transition(ReadFinished(_EXECUTION, 2, 1, None, ReadCompleted())) == {
        "readFinished": {"outcome": "completed"}
    }
    failed = ReadFailed(CausedFailure(_diagnostic(), 2))
    assert _transition(ReadFinished(_EXECUTION, 2, 1, None, failed)) == {
        "readFinished": {"outcome": "failed", "attribution": "caused", "cause": 2}
    }


def test_a_write_batch_states_the_trigger_that_produced_it() -> None:
    assert _transition(WriteBatchStarted(_EXECUTION, 1, 1, None, "read_dependency")) == {
        "writeBatchStarted": {"trigger": "read-dependency"}
    }
    assert _transition(WriteBatchStarted(_EXECUTION, 1, 1, None, "pre_commit")) == {
        "writeBatchStarted": {"trigger": "pre-commit"}
    }
    assert _transition(WriteBatchFinished(_EXECUTION, 2, 1, None, WriteBatchCompleted())) == {
        "writeBatchFinished": {"outcome": "completed"}
    }
    failed = WriteBatchFailed(DirectFailure(_diagnostic()))
    assert _transition(WriteBatchFinished(_EXECUTION, 2, 1, None, failed)) == {
        "writeBatchFinished": {"outcome": "failed", "attribution": "direct"}
    }


def test_a_database_call_names_its_statement_by_index_and_never_by_text() -> None:
    started = DatabaseCallStarted(_EXECUTION, 1, 1, None, "Account", "WRITE", _STATEMENT)
    assert _transition(started, statements=[_STATEMENT.sql]) == {
        "databaseCallStarted": {"target": "Account", "kind": "write", "statement": 0}
    }
    # A lane authoring no golden SQL leaves the index absent rather than
    # inventing one, which is exactly what its cases author.
    assert _transition(started) == {"databaseCallStarted": {"target": "Account", "kind": "write"}}
    read = DatabaseCallStarted(_EXECUTION, 1, 1, None, "Account", "READ", _STATEMENT)
    assert _transition(read) == {"databaseCallStarted": {"target": "Account", "kind": "read"}}


def test_a_database_call_outcome_carries_its_own_count_or_its_category() -> None:
    read = DatabaseCallFinished(_EXECUTION, 1, 1, None, _STATEMENT, 7, DatabaseReadCompleted(3))
    assert _transition(read) == {
        "databaseCallFinished": {"outcome": "readCompleted", "returnedRows": 3}
    }
    write = DatabaseCallFinished(_EXECUTION, 1, 1, None, _STATEMENT, 7, DatabaseWriteCompleted(0))
    assert _transition(write) == {
        "databaseCallFinished": {"outcome": "writeCompleted", "affectedRows": 0}
    }
    failure = DatabaseCallFailed(DatabaseFailureDiagnostic(_diagnostic(), "deadlock", "40P01"))
    failed = DatabaseCallFinished(_EXECUTION, 1, 1, None, _STATEMENT, 7, failure)
    # The neutral category is portable; the driver's native code is not.
    assert _transition(failed) == {
        "databaseCallFinished": {"outcome": "failed", "category": "deadlock"}
    }
    unclassified = DatabaseCallFailed(DatabaseFailureDiagnostic(_diagnostic("gone"), None, None))
    call = DatabaseCallFinished(_EXECUTION, 1, 1, None, _STATEMENT, 7, unclassified)
    assert _transition(call) == {
        "databaseCallFinished": {"outcome": "failed", "category": None, "code": "gone"}
    }


def test_an_outer_invocation_states_the_policy_a_joined_one_inherits() -> None:
    outer = OuterInvocation("locking", RetryPolicy(3, True))
    assert _transition(TransactionInvocationStarted(_EXECUTION, 1, 1, None, outer)) == {
        "transactionInvocationStarted": {
            "invocation": "outer",
            "concurrency": "locking",
            "retries": 3,
            "retryOptimisticConflicts": True,
        }
    }
    assert _transition(
        TransactionInvocationStarted(_EXECUTION, 1, 1, None, JoinedInvocation())
    ) == {"transactionInvocationStarted": {"invocation": "joined"}}


def test_an_invocation_outcome_tells_the_boundary_from_the_nested_callback() -> None:
    for outcome, expected in (
        (OuterInvocationCommitted(), {"outcome": "committed"}),
        (JoinedInvocationReturned(), {"outcome": "returned"}),
        (
            OuterInvocationFailed(DirectFailure(_diagnostic("stale"))),
            {"outcome": "failed", "attribution": "direct", "code": "stale"},
        ),
        (
            JoinedInvocationRaised(CausedFailure(_diagnostic(), 4)),
            {"outcome": "raised", "attribution": "caused", "cause": 4},
        ),
    ):
        assert _transition(TransactionInvocationFinished(_EXECUTION, 1, 1, None, outcome)) == {
            "transactionInvocationFinished": expected
        }


def test_an_attempt_states_its_phase_and_the_classifier_verdict() -> None:
    assert _transition(TransactionAttemptStarted(_EXECUTION, 1, 1, None)) == {
        "transactionAttemptStarted": {}
    }
    assert _transition(TransactionAttemptFinished(_EXECUTION, 2, 1, None, AttemptCommitted())) == {
        "transactionAttemptFinished": {"outcome": "committed"}
    }
    rolled = AttemptRolledBack(
        AttemptFailure("PRE_COMMIT", CausedFailure(_diagnostic(), 3), retry_eligible=True)
    )
    assert _transition(TransactionAttemptFinished(_EXECUTION, 2, 1, None, rolled)) == {
        "transactionAttemptFinished": {
            "outcome": "rolledBack",
            "phase": "pre-commit",
            "retryEligible": True,
            "attribution": "caused",
            "cause": 3,
        }
    }
    failed_rollback = AttemptRollbackFailed(
        AttemptFailure("CALLBACK", DirectFailure(_diagnostic()), retry_eligible=False),
        _diagnostic("undo-failed"),
    )
    assert _transition(TransactionAttemptFinished(_EXECUTION, 2, 1, None, failed_rollback)) == {
        "transactionAttemptFinished": {
            "outcome": "rollbackFailed",
            "phase": "callback",
            "retryEligible": False,
            "attribution": "direct",
            # Two live failures collide on one event, so the second one's own
            # stable code is prefixed rather than overwriting the first's.
            "rollbackCode": "undo-failed",
        }
    }
    commit_phase = AttemptRolledBack(
        AttemptFailure("COMMIT", DirectFailure(_diagnostic()), retry_eligible=True)
    )
    finished = _transition(TransactionAttemptFinished(_EXECUTION, 2, 1, None, commit_phase))
    assert finished["transactionAttemptFinished"]["phase"] == "commit"


def test_a_stream_states_the_page_size_that_makes_its_batches_countable() -> None:
    started = SnapshotStreamStarted(_EXECUTION, 1, 1, None, "Account", "ROWS", 500)
    assert _transition(started) == {
        "snapshotStreamStarted": {"target": "Account", "interface": "rows", "batchSize": 500}
    }
    for outcome, expected in (
        (StreamExhausted(), {"outcome": "exhausted"}),
        (StreamClosedEarly(), {"outcome": "closedEarly"}),
        (
            StreamFailed(DirectFailure(_diagnostic())),
            {"outcome": "failed", "attribution": "direct"},
        ),
    ):
        assert _transition(SnapshotStreamFinished(_EXECUTION, 2, 1, None, outcome)) == {
            "snapshotStreamFinished": expected
        }


def test_a_stream_batch_names_no_page_of_its_own() -> None:
    assert _transition(StreamBatchStarted(_EXECUTION, 1, 1, None)) == {"streamBatchStarted": {}}
    assert _transition(StreamBatchFinished(_EXECUTION, 2, 1, None, StreamBatchCompleted())) == {
        "streamBatchFinished": {"outcome": "completed"}
    }
    failed = StreamBatchFailed(CausedFailure(_diagnostic(), 9))
    assert _transition(StreamBatchFinished(_EXECUTION, 2, 1, None, failed)) == {
        "streamBatchFinished": {"outcome": "failed", "attribution": "caused", "cause": 9}
    }


# --- the statement index reconciles two independently built orders -------------


def test_a_call_beyond_the_reported_emissions_is_an_adapter_defect() -> None:
    call = DatabaseCallStarted(_EXECUTION, 1, 1, None, "Account", "READ", _STATEMENT)
    with pytest.raises(StatementIndexError, match="would name nothing"):
        _portable(call, call, statements=[_STATEMENT.sql])


def test_a_call_whose_index_would_name_a_different_statement_is_an_adapter_defect() -> None:
    call = DatabaseCallStarted(_EXECUTION, 1, 1, None, "Account", "READ", _STATEMENT)
    with pytest.raises(StatementIndexError, match="would name a different statement"):
        _portable(call, statements=["select 2 from account"])


# --- the statement and count projections of the same delivery ------------------


class _Handler:
    """Stands in for the Handle a Provider is installed on."""

    def __init__(self, observation: LifecycleObservation) -> None:
        self.handler = observation.provider.open(RootExecution(_EXECUTION, "READ"))

    def deliver(self, *events: ExecutionEvent) -> None:
        assert self.handler is not None
        for event in events:
            self.handler.handle(event)


def _call(kind: str, sql: str) -> DatabaseCallStarted:
    return DatabaseCallStarted(_EXECUTION, 1, 1, None, "Account", kind, LoweredStatement(sql, ()))  # pyright: ignore[reportArgumentType] - the kind is the caller's literal


def test_the_statements_a_run_reports_are_the_ones_its_calls_borrowed() -> None:
    observation = LifecycleObservation()
    handle = _Handler(observation)
    handle.deliver(_call("READ", "select 1"), _call("WRITE", "insert 1"), _call("READ", "select 2"))

    assert [statement.sql for statement in observation.statements] == [
        "select 1",
        "insert 1",
        "select 2",
    ]
    # The read/write split is the call's own kind, which is what keeps a
    # force-flush's DML off the find step that triggered it.
    assert [statement.sql for statement in observation.reads] == ["select 1", "select 2"]
    assert [statement.sql for statement in observation.writes] == ["insert 1"]
    assert observation.round_trips == 3


def test_a_step_reads_its_own_statements_from_the_mark_it_took() -> None:
    observation = LifecycleObservation()
    handle = _Handler(observation)
    handle.deliver(_call("READ", "select 1"))
    mark = observation.round_trips
    handle.deliver(_call("WRITE", "insert 1"), _call("READ", "select 2"))

    assert [statement.sql for statement in observation.since(mark)] == ["insert 1", "select 2"]
    assert [statement.sql for statement in observation.since(mark, "read")] == ["select 2"]


def test_a_failed_call_is_the_round_trip_it_was_charged_for() -> None:
    observation = LifecycleObservation()
    handle = _Handler(observation)
    failure = DatabaseCallFailed(DatabaseFailureDiagnostic(_diagnostic(), "deadlock", "40P01"))
    handle.deliver(
        _call("WRITE", "insert 1"),
        DatabaseCallFinished(_EXECUTION, 2, 1, None, LoweredStatement("insert 1", ()), 5, failure),
    )
    # Read off Started rather than off its Finished peer: a call the database
    # never answered still reached it.
    assert observation.round_trips == 1


# --- the run collects what its several handles each observed -------------------


def test_a_run_answers_the_roots_its_handles_opened_in_order() -> None:
    run = LifecycleRun()
    first = run.observation()
    second = run.observation()
    first.provider.open(RootExecution(uuid4(), "READ"))
    second.provider.open(RootExecution(uuid4(), "TRANSACTION_INVOCATION"))
    first.provider.open(RootExecution(uuid4(), "READ"))

    assert [root.execution.kind for root in run.roots] == [
        "READ",
        "READ",
        "TRANSACTION_INVOCATION",
    ]


def test_an_entry_point_grading_no_oracle_still_drives_a_run() -> None:
    supplied = LifecycleRun()
    assert lifecycle_run(supplied) is supplied
    own = lifecycle_run(None)
    assert own is not supplied
    assert own.roots == ()


# --- the port is no longer an observation seam --------------------------------


def test_no_conformance_module_recovers_a_statement_from_driver_text() -> None:
    """The retirement of the capturing port, stated where it can regress.

    A decorator that observes at the Database Port sees DRIVER SQL and has to
    recover the canonical spelling to report it (`Dialect.from_driver_sql`); a
    Database Call carries the canonical Lowered Statement it borrowed, so an
    engine reading its statements off the delivered stream never travels that
    direction. The recovery call is therefore the signature of the seam this
    ticket retired, and its absence is the completeness of that retirement —
    including the defect class it takes with it, since a recovery that drifted
    from the outward translation would silently report a statement nobody ran.
    """
    package = Path(str(conformance.__file__)).parent
    recovering = sorted(
        source.name
        for source in package.rglob("*.py")
        if "from_driver_sql" in source.read_text(encoding="utf-8")
    )
    assert recovering == []
