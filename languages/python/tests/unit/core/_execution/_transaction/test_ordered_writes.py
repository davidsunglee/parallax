"""Ordered write transport in a flush of a real attempt (`m-execution`).

The attempt executes each span of its flush's plan through its own step
executor inside the flush's Write Batch, so a unit's run of count-only temporal
effects crosses the port as one invocation, and the failure that run
propagates is the one whose retry verdict the attempt reports. Which steps one
invocation carries, and how its result is enforced, belong to the production
step executor's own suite.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._transaction._attempt import TxnAttempt
from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    OrderedWriteResultComplete,
    OrderedWriteResultIntegrityError,
    StatementFailed,
    StatementNotExecuted,
)
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle import AttemptRolledBack, TransactionAttemptFinished
from parallax.core.unit_work import (
    MaterializedWriteGroup,
    PredicateSelection,
    PredicateWriteInstruction,
)
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Ordered,
    OrderedCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit._temporal_group_support import temporal_group
from tests.unit.core._execution._execution_support import itself, scope
from tests.unit.core._execution._write_step_support import POSITION_META, POSITIONS, T0


def _terminated(*keys: int) -> MaterializedWriteGroup:
    """The termination, from where they start, of the selected Positions
    ``keys``: one unit closing each, and opening nothing."""
    return temporal_group(
        PredicateWriteInstruction(
            "terminate",
            PredicateSelection(
                "Position",
                predicate_algebra.Comparison(
                    "eq", predicate_algebra.FieldSubject("Position.acctNum"), "A-1"
                ),
            ),
            valid_from=T0,
        ),
        POSITION_META,
        [
            {
                "id": key,
                "acctNum": "A-1",
                "value": Decimal("1.00"),
                "validStart": T0,
                "validEnd": INFINITY,
                "txStart": T0,
                "txEnd": INFINITY,
            }
            for key in keys
        ],
    )


def test_a_units_run_of_closes_is_one_invocation_and_a_lone_close_runs_alone() -> None:
    port = ScriptedAdapter(
        Transact(Write(), Ordered(OrderedWriteResultComplete((1, 1))), Write()), ordered=True
    )

    def body(attempt: TxnAttempt) -> None:
        for keys in ((1,), (2, 3), (4,)):
            attempt.uow.buffer(_terminated(*keys))

    scope(port, POSITIONS).transact(body, itself, concurrency="locking")
    calls = port.calls
    assert [type(call) for call in calls] == [
        BeginCall,
        WriteCall,
        OrderedCall,
        WriteCall,
        CommitCall,
    ]
    (_begin, _first, run, _last, _commit) = calls
    assert isinstance(run, OrderedCall)
    assert len(run.writes) == 2


def _deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


@pytest.mark.parametrize(
    ("raised", "eligible"),
    [(_deadlock, True), (lambda: OrderedWriteResultComplete((1,)), False)],
    ids=["deadlocked-statement", "malformed-result"],
)
def test_the_attempt_reports_the_retry_verdict_of_the_failure_that_propagated(
    raised: Callable[[], object], eligible: bool
) -> None:
    answer = raised()
    result = (
        OrderedWriteResultComplete((StatementFailed(answer), StatementNotExecuted()))
        if isinstance(answer, DatabaseError)
        else answer
    )
    provider = RecordingLifecycleProvider()
    port = ScriptedAdapter(Transact(Ordered(result)), ordered=True)

    def body(attempt: TxnAttempt) -> None:
        attempt.uow.buffer(_terminated(1, 2))

    with pytest.raises(ExecutionFailure) as failed:
        scope(port, POSITIONS, provider=provider).transact(
            body, itself, concurrency="locking", max_retries=0
        )
    assert failed.value.cause is answer or isinstance(
        failed.value.cause, OrderedWriteResultIntegrityError
    )
    assert port.calls[-1] == RollbackCall()
    (finished,) = [
        event
        for root in provider.roots
        for event in root.events
        if isinstance(event, TransactionAttemptFinished)
    ]
    assert isinstance(finished.outcome, AttemptRolledBack)
    assert finished.outcome.failure.retry_eligible is eligible
