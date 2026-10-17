"""Ordered write transport through the production step executor (`m-execution`,
`m-db-port`, `m-execution-lifecycle`).

A connection holding ordered write transport receives each run of two or more
contiguous count-only temporal effects in one invocation, and an effect that
would be its run's only one runs alone. The result is proved well formed
before any of it is read, then enforced in original order against the exact
steps the statements were lowered from, and nothing after the run is lowered
before that. Every presented statement stays one Database Call, finished from
the same result with the invocation's shared timing. These cases drive a
scripted port, so each result — malformed ones included — is whatever the case
says the transport answered.
"""

from __future__ import annotations

import gc
from collections.abc import Callable
from dataclasses import dataclass, field, replace

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core._execution._write_lowering import LoweredOpening, LoweringCursor
from parallax.core._execution._write_step_executor import (
    _LoweredWriteChunk,  # pyright: ignore[reportPrivateUsage] - the chunk is the presented sequence itself
)
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    OrderedWriteResultComplete,
    OrderedWriteResultIntegrityError,
    OrderedWriteResultInterrupted,
    StatementFailed,
    StatementNotExecuted,
)
from parallax.core.dialect import POSTGRES
from parallax.core.execution_lifecycle import (
    CausedFailure,
    DatabaseCallFailed,
    DatabaseCallFinished,
    DatabaseCallNotExecuted,
    DatabaseCallStarted,
    DatabaseCallUnconfirmed,
    DatabaseWriteCompleted,
    DirectFailure,
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProvider,
    RootExecution,
    WriteBatchFailed,
    WriteBatchFinished,
)
from parallax.core.execution_lifecycle._activity import INERT
from parallax.core.metamodel import EntityIdentity
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    OptimisticLockConflictError,
    StaleWriteError,
)
from parallax.core.write_plan.plan import PlannedWrites
from parallax.core.write_plan.steps import PlannedInsert, PlannedWrite
from tests._support.db_port import (
    Ordered,
    OrderedCall,
    ScriptedAdapter,
    Write,
    WriteCall,
)
from tests.unit.core._execution._write_step_support import (
    POSITION,
    HeldSteps,
    alone,
    close,
    guard,
    insert,
    ordered,
    removal,
    revision,
    slot,
    statement,
    step_executor,
    write_batch,
)

_CAP = "parallax.core._execution._write_step_executor._ORDERED_STATEMENTS"


def _deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


def _lost() -> DatabaseError:
    return DatabaseError(category=None, native_code="08006", message="connection lost")


@dataclass
class _Executed:
    """What one execution of a span did: what it answered or what it raised."""

    segment: HeldSteps
    answered: tuple[object, ...] | None = None
    raised: BaseException | None = None


def _execute_held(
    segment: HeldSteps, provider: ExecutionLifecycleProvider | None = None
) -> _Executed:
    """Execute ``segment`` as one span inside one Write Batch over its port.

    A failure is caught outside the batch and recorded, so the batch finishes
    with it and the script reads as the calls alone.
    """
    executed = _Executed(segment)
    view = PlannedWrites((segment,)).view(0, len(segment))
    try:
        with write_batch(provider) as batch:
            executed.answered = step_executor(segment.port).execute(
                view, allocates=False, batch=batch
            )
    except BaseException as raised:
        executed.raised = raised
    return executed


def _execute(
    port: ScriptedAdapter, *steps: PlannedWrite, provider: ExecutionLifecycleProvider | None = None
) -> _Executed:
    return _execute_held(HeldSteps(port, steps), provider)


# --------------------------------------------------------------------------- #
# Selection: which steps share an invocation, and when each is taken.          #
# --------------------------------------------------------------------------- #


def test_a_run_of_mixed_effects_crosses_the_port_once_as_canonical_statements() -> None:
    steps = (close(1), guard(2), removal(3), revision(4))
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1, 1, 1, 1))), ordered=True)
    executed = _execute(port, *steps)
    assert executed.raised is None
    # The adapter converted each canonical statement itself, once: execution
    # converting first would have doubled every placeholder's percent sign.
    assert port.calls == [ordered(*steps)]
    assert executed.answered == ()


def test_a_connection_without_ordered_transport_runs_and_lowers_each_effect_alone() -> None:
    steps = (close(1), close(2), close(3))
    port = ScriptedAdapter(Write(times=3))
    executed = _execute(port, *steps)
    assert executed.raised is None
    assert port.calls == [alone(step) for step in steps]
    # Each effect is taken only once the one before it ran: nothing is
    # gathered into a chunk ahead of its turn.
    assert executed.segment.asked == [(0, 0), (1, 1), (2, 2)]


def _lowering_recorded(
    monkeypatch: pytest.MonkeyPatch, steps: tuple[PlannedWrite, ...], port: ScriptedAdapter
) -> list[tuple[int, int]]:
    """Where each of ``steps`` lowering alone or beginning a grouped opening is
    recorded: its position, with how many port calls had been made by then."""
    lowered_at: list[tuple[int, int]] = []
    lowered_alone = LoweringCursor.lowered
    lowered_opening = LoweringCursor.lowered_opening

    def lowering(cursor: LoweringCursor, step: PlannedWrite) -> LoweredStatement:
        lowered_at.append((steps.index(step), len(port.calls)))
        return lowered_alone(cursor, step)

    def grouping(cursor: LoweringCursor, first: PlannedInsert) -> LoweredOpening:
        lowered_at.append((steps.index(first), len(port.calls)))
        return lowered_opening(cursor, first)

    monkeypatch.setattr(LoweringCursor, "lowered", lowering)
    monkeypatch.setattr(LoweringCursor, "lowered_opening", grouping)
    return lowered_at


def test_a_step_transport_cannot_carry_ends_the_run_untouched_until_the_run_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = (close(1), close(2), insert(9), close(3), close(4))
    port = ScriptedAdapter(
        Ordered(OrderedWriteResultComplete((1, 1))),
        Write(),
        Ordered(OrderedWriteResultComplete((1, 1))),
        ordered=True,
    )
    lowered_at = _lowering_recorded(monkeypatch, steps, port)
    executed = _execute(port, *steps)
    assert executed.raised is None
    assert port.calls == [
        ordered(close(1), close(2)),
        alone(insert(9)),
        ordered(close(3), close(4)),
    ]
    # The insert was taken to end the run — the one step looked ahead — and
    # lowered only once the run before it had been enforced; the close after it
    # was taken, unprepared, to end the insert's own statement.
    assert executed.segment.asked == [(0, 0), (1, 0), (2, 0), (3, 1), (4, 2)]
    assert lowered_at == [(2, 1)]


def test_an_effect_that_would_be_its_runs_only_one_runs_alone_before_anything_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = (close(1), insert(9), guard(2))
    port = ScriptedAdapter(Write(times=3), ordered=True)
    lowered_at = _lowering_recorded(monkeypatch, steps, port)
    executed = _execute(port, *steps)
    assert executed.raised is None
    assert port.calls == [alone(step) for step in steps]
    # The insert was taken, unprepared, to decide the close runs alone, and
    # lowered only once the close ran; the guard, taken to end the insert's
    # statement, was lowered once that ran and, the last step, ran alone too.
    assert executed.segment.asked == [(0, 0), (1, 0), (2, 1)]
    assert lowered_at == [(0, 0), (1, 1), (2, 2)]


def _reaches(error: BaseException, held: object) -> bool:
    """Whether any frame ``error`` propagated through still holds ``held``."""
    trace = error.__traceback__
    while trace is not None:
        if any(value is held for value in trace.tb_frame.f_locals.values()):
            return True
        trace = trace.tb_next
    return False


@pytest.mark.parametrize(
    ("failure", "affected", "raised"),
    [
        (RuntimeError("the next step cannot be rebuilt"), 1, "failure"),
        (RuntimeError("never raised"), 0, "shortfall"),
        (KeyboardInterrupt(), 1, "failure"),
    ],
    ids=["ordinary", "shortfall-wins", "fatal"],
)
def test_a_lone_effects_look_ahead_failing_runs_it_alone_only_for_an_ordinary_failure(
    failure: BaseException, affected: int, raised: str
) -> None:
    steps = (close(1), close(2))
    ordinary = isinstance(failure, Exception)
    port = ScriptedAdapter(*((Write(affected=affected),) if ordinary else ()), ordered=True)
    executed = _execute_held(HeldSteps(port, steps, failing=1, failure=failure))
    propagated = executed.raised
    if raised == "shortfall":
        assert isinstance(propagated, StaleWriteError)
        assert propagated.__context__ is None
        assert not _reaches(propagated, failure)
    else:
        assert propagated is failure
    # Nothing was lowered before the look ahead, so a fatal one runs nothing.
    assert port.calls == ([alone(steps[0])] if ordinary else [])


def test_the_statement_cap_ends_a_run_before_another_step_is_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_CAP, 2)
    steps = tuple(close(key) for key in range(1, 6))
    port = ScriptedAdapter(
        Ordered(OrderedWriteResultComplete((1, 1)), times=2), Write(), ordered=True
    )
    executed = _execute(port, *steps)
    assert executed.raised is None
    # The last close, the only one left after the cap, runs alone.
    assert port.calls == [ordered(*steps[:2]), ordered(*steps[2:4]), alone(steps[4])]
    assert executed.segment.asked == [(0, 0), (1, 0), (2, 1), (3, 1), (4, 2)]


def test_an_effect_whose_parameter_ceiling_exceeds_the_dialect_limit_runs_alone() -> None:
    narrow = replace(POSTGRES, max_bind_parameters=5)
    # A close's ceiling is six parameters and a guard's five, so only the guard fits.
    port = ScriptedAdapter(
        Write(), Ordered(OrderedWriteResultComplete((1, 1))), dialect=narrow, ordered=True
    )
    executed = _execute(port, close(1), guard(2), guard(3))
    assert executed.raised is None
    assert [type(call) for call in port.calls] == [WriteCall, OrderedCall]


# --------------------------------------------------------------------------- #
# Interpretation: validated whole, then enforced in original order.            #
# --------------------------------------------------------------------------- #


def test_an_earlier_shortfall_outranks_a_later_statement_failure() -> None:
    failure = _deadlock()
    result = OrderedWriteResultComplete((1, 0, StatementFailed(failure), StatementNotExecuted()))
    provider = RecordingLifecycleProvider()
    port = ScriptedAdapter(Ordered(result), ordered=True)
    executed = _execute(port, close(1), close(2), close(3), close(4), provider=provider)
    assert isinstance(executed.raised, StaleWriteError)
    calls = _finished_calls(provider)
    assert [type(call.outcome) for call in calls] == [
        DatabaseWriteCompleted,
        DatabaseWriteCompleted,
        DatabaseCallFailed,
        DatabaseCallNotExecuted,
    ]
    # The batch names the call whose count fell short, not the later failure.
    batch = _batch_failure(provider)
    assert isinstance(batch, CausedFailure)
    assert batch.cause_activity_id == calls[1].activity_id


def test_a_confirmed_statement_failure_propagates_as_itself_from_its_own_call() -> None:
    failure = _deadlock()
    provider = RecordingLifecycleProvider()
    result = OrderedWriteResultComplete((1, StatementFailed(failure), StatementNotExecuted()))
    port = ScriptedAdapter(Ordered(result), ordered=True)
    executed = _execute(port, close(1), close(2), close(3), provider=provider)
    assert executed.raised is failure
    calls = _finished_calls(provider)
    failed = calls[1].outcome
    assert isinstance(failed, DatabaseCallFailed)
    assert failed.diagnostic.category == "deadlock"
    batch = _batch_failure(provider)
    assert isinstance(batch, CausedFailure)
    assert batch.cause_activity_id == calls[1].activity_id


def test_an_excess_count_is_a_cardinality_corruption_of_its_own_step() -> None:
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1, 2))), ordered=True)
    executed = _execute(port, close(1), close(2))
    assert isinstance(executed.raised, CardinalityCorruptionError)
    assert executed.raised.target == slot(2)


def test_each_count_is_enforced_against_the_exact_step_it_was_lowered_from() -> None:
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1, 0))), ordered=True)
    executed = _execute(port, close(1), guard(2))
    assert isinstance(executed.raised, OptimisticLockConflictError)
    assert executed.raised.target == slot(2)


def _malformed() -> list[tuple[str, object]]:
    error = _lost()
    return [
        ("not-a-result", (1, 1)),
        ("too-few-outcomes", OrderedWriteResultComplete((0,))),
        ("too-many-outcomes", OrderedWriteResultComplete((0, 1, 1))),
        ("outcomes-not-a-tuple", OrderedWriteResultComplete([0, 1])),  # type: ignore[arg-type]
        ("negative-count", OrderedWriteResultComplete((0, -1))),
        ("boolean-count", OrderedWriteResultComplete((0, True))),
        ("unknown-outcome", OrderedWriteResultComplete((0, "1"))),  # type: ignore[arg-type]
        ("skipped-without-failure", OrderedWriteResultComplete((0, StatementNotExecuted()))),
        (
            "failure-not-an-exception",
            OrderedWriteResultComplete((0, StatementFailed(KeyboardInterrupt()))),  # type: ignore[arg-type]
        ),
        ("partition-too-short", OrderedWriteResultInterrupted((0,), 0, 0, error)),
        ("boolean-span", OrderedWriteResultInterrupted((0,), True, 0, error)),
        ("negative-span", OrderedWriteResultInterrupted((0,), 2, -1, error)),
        ("interruption-not-an-exception", OrderedWriteResultInterrupted((0,), 1, 0, "lost")),  # type: ignore[arg-type]
        ("confirmed-not-a-tuple", OrderedWriteResultInterrupted([0], 1, 0, error)),  # type: ignore[arg-type]
    ]


@pytest.mark.parametrize(
    ("label", "result"), _malformed(), ids=[label for label, _ in _malformed()]
)
def test_a_malformed_result_outranks_the_earlier_shortfall_it_reports(
    label: str, result: object
) -> None:
    del label
    provider = RecordingLifecycleProvider()
    port = ScriptedAdapter(Ordered(result), ordered=True)
    executed = _execute(port, close(1), close(2), provider=provider)
    assert isinstance(executed.raised, OrderedWriteResultIntegrityError)
    # The diagnostic is structure, never a statement or a value it was handed.
    assert "update" not in str(executed.raised)
    calls = _finished_calls(provider)
    assert [type(call.outcome) for call in calls] == [DatabaseCallUnconfirmed] * 2
    assert isinstance(_batch_failure(provider), DirectFailure)


def test_an_interruption_reports_its_confirmed_unconfirmed_and_unsent_statements() -> None:
    interruption = _lost()
    provider = RecordingLifecycleProvider()
    result = OrderedWriteResultInterrupted((1,), 2, 1, interruption)
    port = ScriptedAdapter(Ordered(result), ordered=True)
    executed = _execute(port, close(1), close(2), close(3), close(4), provider=provider)
    assert executed.raised is interruption
    calls = _finished_calls(provider)
    assert [type(call.outcome) for call in calls] == [
        DatabaseWriteCompleted,
        DatabaseCallUnconfirmed,
        DatabaseCallUnconfirmed,
        DatabaseCallNotExecuted,
    ]
    unconfirmed = [call.outcome for call in calls[1:3]]
    assert isinstance(unconfirmed[0], DatabaseCallUnconfirmed)
    # One diagnostic describes the one interruption for every call it left.
    assert unconfirmed[0] is unconfirmed[1]
    assert unconfirmed[0].diagnostic.native_code == "08006"
    # A primary interruption names no call as its cause.
    assert isinstance(_batch_failure(provider), DirectFailure)


def test_an_earlier_shortfall_outranks_the_interruption_after_it() -> None:
    provider = RecordingLifecycleProvider()
    result = OrderedWriteResultInterrupted((0,), 2, 0, _lost())
    port = ScriptedAdapter(Ordered(result), ordered=True)
    executed = _execute(port, close(1), close(2), close(3), provider=provider)
    assert isinstance(executed.raised, StaleWriteError)
    calls = _finished_calls(provider)
    assert [type(call.outcome) for call in calls] == [
        DatabaseWriteCompleted,
        DatabaseCallUnconfirmed,
        DatabaseCallUnconfirmed,
    ]
    batch = _batch_failure(provider)
    assert isinstance(batch, CausedFailure)
    assert batch.cause_activity_id == calls[0].activity_id


def test_a_confirmed_failure_before_an_interruption_propagates_as_itself() -> None:
    failure = _deadlock()
    result = OrderedWriteResultInterrupted(
        (StatementFailed(failure), StatementNotExecuted()), 0, 1, _lost()
    )
    port = ScriptedAdapter(Ordered(result), ordered=True)
    executed = _execute(port, close(1), close(2), close(3))
    assert executed.raised is failure


def test_an_exception_escaping_transport_leaves_every_call_unconfirmed() -> None:
    escaped = _lost()
    provider = RecordingLifecycleProvider()
    port = ScriptedAdapter(Ordered(raises=escaped), ordered=True)
    executed = _execute(port, close(1), close(2), close(3), provider=provider)
    assert executed.raised is escaped
    calls = _finished_calls(provider)
    assert [type(call.outcome) for call in calls] == [DatabaseCallUnconfirmed] * 3
    assert isinstance(_batch_failure(provider), DirectFailure)


def test_a_fatal_exception_escaping_transport_closes_every_call_and_stays_primary() -> None:
    provider = RecordingLifecycleProvider()
    port = ScriptedAdapter(Ordered(raises=KeyboardInterrupt()), ordered=True)
    executed = _execute(port, close(1), close(2), provider=provider)
    assert isinstance(executed.raised, KeyboardInterrupt)
    assert [type(call.outcome) for call in _finished_calls(provider)] == [
        DatabaseCallUnconfirmed
    ] * 2


# --------------------------------------------------------------------------- #
# Preparation failures drain only the prefix already lowered.                  #
# --------------------------------------------------------------------------- #


def _failing_at(
    monkeypatch: pytest.MonkeyPatch, failing: PlannedWrite, failure: BaseException
) -> None:
    real = LoweringCursor.lowered_within

    def lowering(
        cursor: LoweringCursor, step: PlannedWrite, parameter_ceiling: int
    ) -> LoweredStatement:
        if step is failing:
            raise failure
        return real(cursor, step, parameter_ceiling)

    monkeypatch.setattr(LoweringCursor, "lowered_within", lowering)


def test_a_later_lowering_failure_presents_the_prefix_then_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = (close(1), close(2), close(3), close(4))
    failure = SqlGenError("the third close cannot be rendered")
    _failing_at(monkeypatch, steps[2], failure)
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1, 1))), ordered=True)
    executed = _execute(port, *steps)
    assert executed.raised is failure
    assert port.calls == [ordered(*steps[:2])]
    # Nothing after the failing step is taken.
    assert executed.segment.taken == [0, 1, 2]


@pytest.mark.parametrize("presented", [True, False], ids=["ordinary", "fatal"])
def test_a_later_effect_failing_to_be_taken_drains_only_an_ordinary_failures_prefix(
    presented: bool,
) -> None:
    # Built per case: a failure kept past the case would keep what its
    # traceback reached alive into every later one.
    failure = (
        RuntimeError("the predecessor cannot be rebuilt") if presented else KeyboardInterrupt()
    )
    steps = (close(1), close(2), close(3))
    entries = (Ordered(OrderedWriteResultComplete((1, 1))),) if presented else ()
    port = ScriptedAdapter(*entries, ordered=True)
    executed = _execute_held(HeldSteps(port, steps, failing=2, failure=failure))
    assert executed.raised is failure
    assert port.calls == ([ordered(*steps[:2])] if presented else [])


def test_a_prefix_failure_wins_over_the_lowering_failure_it_overtook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = (close(1), close(2), close(3))
    overtaken = SqlGenError("never raised")
    _failing_at(monkeypatch, steps[1], overtaken)
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((0,))), ordered=True)
    executed = _execute(port, *steps)
    assert isinstance(executed.raised, StaleWriteError)
    assert executed.raised.__context__ is None
    assert not _reaches(executed.raised, overtaken)
    assert port.calls == [ordered(steps[0])]


def test_a_failure_lowering_the_first_effect_presents_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = (close(1), close(2))
    failure = SqlGenError("the first close cannot be rendered")
    _failing_at(monkeypatch, steps[0], failure)
    port = ScriptedAdapter(ordered=True)
    executed = _execute(port, *steps)
    assert executed.raised is failure
    assert port.calls == []


def test_a_fatal_exception_lowering_a_later_effect_presents_none_of_the_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = (close(1), close(2), close(3))
    _failing_at(monkeypatch, steps[1], KeyboardInterrupt())
    port = ScriptedAdapter(ordered=True)
    executed = _execute(port, *steps)
    assert isinstance(executed.raised, KeyboardInterrupt)
    assert port.calls == []


def test_a_statement_exceeding_its_promised_parameter_ceiling_is_a_lowering_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steps = (close(1), guard(2))
    promised = {id(steps[0]): 6, id(steps[1]): 3}

    def promise(step: PlannedWrite) -> int:
        return promised[id(step)]

    monkeypatch.setattr(
        "parallax.core._execution._write_lowering.effect_parameter_ceiling", promise
    )
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1,))), ordered=True)
    executed = _execute(port, *steps)
    assert isinstance(executed.raised, SqlGenError)
    assert "exceeds the 3" in str(executed.raised)
    # It was selected on that promise, so the prefix drains rather than the
    # step falling back to a call of its own.
    assert port.calls == [ordered(steps[0])]


# --------------------------------------------------------------------------- #
# Observation: one call per presented statement, sharing one timing.           #
# --------------------------------------------------------------------------- #


def _events(provider: RecordingLifecycleProvider) -> list[ExecutionEvent]:
    return [event for root in provider.roots for event in root.events]


def _finished_calls(provider: RecordingLifecycleProvider) -> list[DatabaseCallFinished]:
    return [event for event in _events(provider) if isinstance(event, DatabaseCallFinished)]


def _batch_failure(provider: RecordingLifecycleProvider) -> object:
    (finished,) = [event for event in _events(provider) if isinstance(event, WriteBatchFinished)]
    assert isinstance(finished.outcome, WriteBatchFailed)
    return finished.outcome.failure


def test_every_presented_statement_is_one_call_sharing_the_invocations_timing() -> None:
    provider = RecordingLifecycleProvider()
    steps = (close(1), guard(2), insert(9), close(3))
    port = ScriptedAdapter(
        Ordered(OrderedWriteResultComplete((1, 1))), Write(times=2), ordered=True
    )
    executed = _execute(port, *steps, provider=provider)
    assert executed.raised is None
    events = _events(provider)
    calls = [
        event for event in events if isinstance(event, DatabaseCallStarted | DatabaseCallFinished)
    ]
    # Both Starteds precede both Finisheds, each in presentation order, under
    # contiguous Activity IDs.
    kinds = [(type(event).__name__, event.activity_id) for event in calls]
    first = calls[0].activity_id
    assert kinds[:4] == [
        ("DatabaseCallStarted", first),
        ("DatabaseCallStarted", first + 1),
        ("DatabaseCallFinished", first),
        ("DatabaseCallFinished", first + 1),
    ]
    finished = [event for event in calls if isinstance(event, DatabaseCallFinished)]
    pair, lone, last = finished[:2], finished[2], finished[3]
    assert [call.shared_timing_id for call in pair] == [first, first]
    assert pair[0].duration_ns == pair[1].duration_ns
    # Calls that ran alone share no timing, the last close included.
    assert lone.shared_timing_id is None
    assert last.shared_timing_id is None
    started = [event for event in calls if isinstance(event, DatabaseCallStarted)]
    assert [event.kind for event in started] == ["write"] * 4
    assert all(event.target == "parallax.compatibility.Position" for event in started)
    assert started[0].statement is pair[0].statement


@dataclass
class _Tripping:
    """A Provider whose Handler raises ``failure`` at the first event ``trips``
    answers for, recording every event it was handed before then."""

    trips: Callable[[ExecutionEvent, int], bool]
    failure: BaseException
    seen: list[ExecutionEvent] = field(default_factory=list[ExecutionEvent])
    reported: list[ExecutionLifecycleHandlerError] = field(
        default_factory=list[ExecutionLifecycleHandlerError]
    )

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        return self

    def handle(self, event: ExecutionEvent, /) -> None:
        self.seen.append(event)
        if self.trips(event, len(self.seen)):
            raise self.failure

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.reported.append(error)


def _nth(kind: type[ExecutionEvent], n: int) -> Callable[[ExecutionEvent, int], bool]:
    counted: list[ExecutionEvent] = []

    def trips(event: ExecutionEvent, _seen: int) -> bool:
        if isinstance(event, kind):
            counted.append(event)
        return isinstance(event, kind) and len(counted) == n

    return trips


def test_a_started_delivery_aborting_the_root_invokes_nothing_and_finishes_nothing() -> None:
    provider = _Tripping(_nth(DatabaseCallStarted, 1), KeyboardInterrupt())
    port = ScriptedAdapter(ordered=True)
    executed = _execute(port, close(1), close(2), provider=provider)
    assert isinstance(executed.raised, KeyboardInterrupt)
    assert port.calls == []
    assert not [event for event in provider.seen if isinstance(event, DatabaseCallFinished)]
    assert provider.reported == []


def test_a_finished_delivery_aborting_the_root_emits_nothing_more() -> None:
    provider = _Tripping(_nth(DatabaseCallFinished, 2), KeyboardInterrupt())
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1, 1, 1))), ordered=True)
    executed = _execute(port, close(1), close(2), close(3), provider=provider)
    assert isinstance(executed.raised, KeyboardInterrupt)
    finished = [event for event in provider.seen if isinstance(event, DatabaseCallFinished)]
    assert len(finished) == 2
    assert provider.seen[-1] is finished[-1], "delivery stopped at the aborting event"


def test_an_unconfirmed_delivery_aborting_the_root_keeps_the_fatal_exception_primary() -> None:
    interrupted = KeyboardInterrupt()
    provider = _Tripping(_nth(DatabaseCallFinished, 1), SystemExit())
    port = ScriptedAdapter(Ordered(raises=interrupted), ordered=True)
    executed = _execute(port, close(1), close(2), provider=provider)
    assert executed.raised is interrupted
    finished = [event for event in provider.seen if isinstance(event, DatabaseCallFinished)]
    assert len(finished) == 1
    assert provider.seen[-1] is finished[-1], "delivery stopped at the aborting event"


@pytest.mark.parametrize(
    "trips",
    [
        _nth(DatabaseCallStarted, 1),
        _nth(DatabaseCallStarted, 2),
        _nth(DatabaseCallFinished, 1),
    ],
    ids=["first-started", "second-started", "first-finished"],
)
def test_an_ordinary_handler_failure_quarantines_the_handler_and_changes_no_execution(
    trips: Callable[[ExecutionEvent, int], bool],
) -> None:
    provider = _Tripping(trips, RuntimeError("the exporter is full"))
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1, 0))), ordered=True)
    executed = _execute(port, close(1), close(2), provider=provider)
    assert isinstance(executed.raised, StaleWriteError)
    assert port.calls == [ordered(close(1), close(2))]
    assert len(provider.reported) == 1


@pytest.mark.parametrize(
    ("partition", "finished_before"),
    [(((1, 1), 1, 1), 1), (((1,), 2, 1), 2), (((1,), 1, 2), 3)],
    ids=["during-confirmed", "during-unconfirmed", "during-unsent"],
)
def test_a_handler_quarantined_while_an_interruption_finishes_its_calls_sees_no_more(
    partition: tuple[tuple[int, ...], int, int], finished_before: int
) -> None:
    confirmed, unconfirmed, unsent = partition
    result = OrderedWriteResultInterrupted(confirmed, unconfirmed, unsent, _lost())
    provider = _Tripping(_nth(DatabaseCallFinished, finished_before), RuntimeError("full"))
    port = ScriptedAdapter(Ordered(result), ordered=True)
    executed = _execute(port, close(1), close(2), close(3), close(4), provider=provider)
    assert executed.raised is not None
    finished = [event for event in provider.seen if isinstance(event, DatabaseCallFinished)]
    assert len(finished) == finished_before
    assert len(provider.reported) == 1


def test_a_handler_quarantined_before_the_run_opens_no_observation_of_it() -> None:
    provider = _Tripping(
        lambda event, _seen: type(event).__name__ == "WriteBatchStarted", RuntimeError("full")
    )
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1, 1))), ordered=True)
    executed = _execute(port, close(1), close(2), provider=provider)
    assert executed.raised is None
    assert not [event for event in provider.seen if isinstance(event, DatabaseCallStarted)]


def test_a_chunk_reads_as_its_statements_and_holds_each_exact_original() -> None:
    originals = (close(1), guard(2))
    statements = tuple(statement(step) for step in originals)
    chunk = _LoweredWriteChunk()
    for original, lowered_statement in zip(originals, statements, strict=True):
        chunk.append(original, lowered_statement)
    assert len(chunk) == 2
    assert chunk[1] is statements[1]
    assert list(chunk[:1]) == [statements[0]]
    assert list(chunk) == list(statements)
    assert chunk.step(0) is originals[0]
    assert chunk.target(1) is POSITION
    chunk.seal()
    with pytest.raises(RuntimeError, match="admits no further statement"):
        chunk.append(close(3), statements[0])
    assert len(chunk) == 2


class _Clockless:
    """A ``time`` module whose monotonic clock refuses to be read."""

    @staticmethod
    def perf_counter_ns() -> int:
        raise AssertionError("an unobserved ordered invocation reads no lifecycle clock")


class _Declining:
    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        return None

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(f"a declined root reports nothing, yet {error!r} arrived")


@pytest.mark.parametrize("provider", [None, _Declining()], ids=["no-provider", "declined"])
def test_an_unobserved_invocation_reads_no_lifecycle_clock(
    monkeypatch: pytest.MonkeyPatch, provider: ExecutionLifecycleProvider | None
) -> None:
    monkeypatch.setattr("parallax.core.execution_lifecycle._activity.time", _Clockless)
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1, 1))), ordered=True)
    executed = _execute(port, close(1), close(2), provider=provider)
    assert executed.raised is None
    assert port.calls == [ordered(close(1), close(2))]


class _Untouchable:
    """Presented statements refusing every inspection."""

    def __len__(self) -> int:
        raise AssertionError("an unobserved ordered invocation counts no statement")

    def __getitem__(self, index: int, /) -> LoweredStatement:
        raise AssertionError("an unobserved ordered invocation reads no statement")

    def target(self, index: int, /) -> EntityIdentity:
        raise AssertionError("an unobserved ordered invocation spells no target")


def test_the_inert_observation_hands_the_statements_on_without_reading_them() -> None:
    statements = _Untouchable()
    answered = OrderedWriteResultComplete((1,))
    handed: list[object] = []

    def transport(presented: _Untouchable) -> OrderedWriteResultComplete:
        handed.append(presented)
        return answered

    with INERT.ordered_calls(statements) as calls:
        result = calls.invoke(transport, statements)
        calls.finish_calls(result)
        with calls.enforcing(0):
            pass
    assert calls is INERT
    assert result is answered
    assert handed == [statements]


class _Counting:
    """A Provider whose Handlers keep a count and nothing they are handed."""

    def __init__(self) -> None:
        self.events = 0

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        return self

    def handle(self, event: ExecutionEvent, /) -> None:
        del event
        self.events += 1

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(f"a counting handler never fails, yet {error!r} arrived")


def _alive(*names: str) -> set[int]:
    gc.collect()
    return {id(item) for item in gc.get_objects() if type(item).__name__ in names}


def test_an_observed_run_leaves_neither_its_chunk_nor_its_observation_alive() -> None:
    kinds = ("_LoweredWriteChunk", "_LiveOrderedCalls")
    before = _alive(*kinds)
    provider = _Counting()
    steps = tuple(close(key) for key in range(1, 41))
    port = ScriptedAdapter(Ordered(OrderedWriteResultComplete((1,) * 40)), ordered=True)
    executed = _execute(port, *steps, provider=provider)
    assert executed.raised is None
    # Every call started and finished, and none of it outlived the execution.
    assert provider.events >= 80
    assert _alive(*kinds) <= before
