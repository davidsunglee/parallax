"""Ordered write transport across a flush's execution units (`m-execution`).

A run of count-only temporal effects never reaches into a later unit, each unit
is reported before any step of the next is taken, and the failure a run
propagates is the one whose retry verdict the attempt reports. Which steps one
invocation carries, and how its result is enforced, belong to the production
step executor's own suite.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core._execution._transaction._attempt import TxnAttempt
from parallax.core._execution._unit_work.uow import DeferredWriteContinuation
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    OrderedWriteResultComplete,
    OrderedWriteResultIntegrityError,
    StatementFailed,
    StatementNotExecuted,
)
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle import AttemptRolledBack, TransactionAttemptFinished
from parallax.core.unit_work import StaleWriteError
from parallax.core.write_plan import WritePlan
from parallax.core.write_plan.plan import (
    BoundRange,
    DeferredRange,
    ExecutionUnit,
    PlannedWrites,
    UnitEffects,
)
from parallax.core.write_plan.steps import PlannedWrite
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Ordered,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
)
from tests.unit.core._execution._execution_support import itself, scope
from tests.unit.core._execution._write_step_support import (
    POSITIONS,
    HeldSteps,
    alone,
    close,
    ordered,
)


def _unbound(description: DeferredRange, /) -> BoundRange | DeferredWriteContinuation:
    raise AssertionError(f"no unit of this plan defers, yet {description!r} was bound")


@dataclass
class _Flushed:
    """What one flush did: the units it reported and whatever it raised."""

    segment: HeldSteps
    reported: list[ExecutionUnit] = field(default_factory=list[ExecutionUnit])
    raised: BaseException | None = None


def _flush(
    port: ScriptedAdapter, *steps: PlannedWrite, units: tuple[ExecutionUnit, ...]
) -> _Flushed:
    """Flush ``steps`` as one Write Batch of a fresh attempt over ``port``.

    A failure is caught inside the attempt's callback and recorded, so the
    transaction around it commits and the script reads as the calls alone.
    """
    flushed = _Flushed(HeldSteps(port, steps))
    plan = WritePlan(steps=PlannedWrites((flushed.segment,)), units=units)

    def completed(
        unit: ExecutionUnit, bound: UnitEffects | None, /, *, allocated: tuple[object, ...] = ()
    ) -> None:
        del bound, allocated
        flushed.reported.append(unit)

    def body(attempt: TxnAttempt) -> None:
        try:
            with attempt._open_write_batch("pre_commit"):  # pyright: ignore[reportPrivateUsage] - one batch around a hand-built plan
                attempt._execute_flush(  # pyright: ignore[reportPrivateUsage] - drives the executor over a hand-built plan
                    plan, trigger="pre_commit", bind_deferred=_unbound, completed=completed
                )
        except BaseException as raised:
            flushed.raised = raised

    scope(port, POSITIONS).transact(body, itself, concurrency="locking")
    return flushed


def test_a_run_never_crosses_a_unit_and_each_unit_reports_before_the_next_is_taken() -> None:
    steps = (close(1), close(2), close(3), close(4))
    port = ScriptedAdapter(
        Transact(Write(), Ordered(OrderedWriteResultComplete((1, 1))), Write()),
        ordered=True,
    )
    units = (ExecutionUnit(end=1), ExecutionUnit(end=3), ExecutionUnit(end=4))
    flushed = _flush(port, *steps, units=units)
    assert flushed.raised is None
    # The first unit's close would be the only one of its run, since a run
    # never reaches into the next unit, so it runs alone; so does the last's.
    assert port.calls == [
        BeginCall(),
        alone(steps[0]),
        ordered(*steps[1:3]),
        alone(steps[3]),
        CommitCall(),
    ]
    assert flushed.reported == list(units)


def test_a_failed_run_publishes_nothing_and_takes_no_later_units_step() -> None:
    steps = (close(1), close(2), close(3))
    port = ScriptedAdapter(Transact(Ordered(OrderedWriteResultComplete((1, 0)))), ordered=True)
    flushed = _flush(port, *steps, units=(ExecutionUnit(end=2), ExecutionUnit(end=3)))
    assert isinstance(flushed.raised, StaleWriteError)
    assert flushed.reported == []
    assert flushed.segment.taken == [0, 1]


def _never_completed(
    unit: ExecutionUnit, bound: UnitEffects | None, /, *, allocated: tuple[object, ...] = ()
) -> None:
    raise AssertionError(f"a failed run reports no unit, yet {unit!r} was reported")


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
    steps = (close(1), close(2))
    plan = WritePlan(steps=PlannedWrites((HeldSteps(port, steps),)), units=(ExecutionUnit(end=2),))

    def body(attempt: TxnAttempt) -> None:
        with attempt._open_write_batch("pre_commit"):  # pyright: ignore[reportPrivateUsage] - one batch around a hand-built plan
            attempt._execute_flush(  # pyright: ignore[reportPrivateUsage] - drives the executor over a hand-built plan
                plan, trigger="pre_commit", bind_deferred=_unbound, completed=_never_completed
            )

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
