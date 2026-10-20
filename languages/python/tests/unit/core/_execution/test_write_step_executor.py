"""The production step executor over a scripted port (`m-execution`).

Each step of a borrowed span is taken from its sequence once and lowered only
after every earlier step was enforced; a step running alone is one Database
Call enforced as itself, a run of compatible temporal openings is one multi-row
insert, and an insert whose key the database allocates answers that key. The
statements execution runs are the ones a dry traversal of the same steps
answers.
"""

from __future__ import annotations

import datetime as dt
import gc
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core import MAX, Attr, Bitemporal, DomainModel, attr
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import PreparedKeyedWrite, prepare_typed_write
from parallax.core._execution._write_lowering import LoweringCursor
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.core.execution_lifecycle import (
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseWriteCompleted,
    ExecutionLifecycleProvider,
)
from parallax.core.metamodel import AttributeIdentity, entity_by_name
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.unit_work import KeyedWriteInstruction, MissingTargetError, WritePlanningRequest
from parallax.core.write_plan import WritePlan
from parallax.core.write_plan.plan import ExecutionUnit, PlannedWrites
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedDelete,
    PlannedWrite,
)
from tests._support.clock_probes import instant_at
from tests._support.db_port import Read, ReadCall, ScriptedAdapter, Write, WriteCall
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit.core._execution._execution_support import ACCOUNT
from tests.unit.core._execution._write_step_support import (
    POSITION,
    HeldSteps,
    alone,
    close,
    opening,
    physical,
    run_plan,
    step_executor,
    write_batch,
)

_OPENING_CAP: Final = "parallax.core._execution._write_lowering._OPENING_ENTRY_CAP"


@dataclass
class _Executed:
    """What one execution of a span did: what it answered or what it raised."""

    segment: HeldSteps
    answered: tuple[object, ...] | None = None
    raised: BaseException | None = None


def _execute(segment: HeldSteps, provider: ExecutionLifecycleProvider | None = None) -> _Executed:
    """Execute ``segment`` as one span inside one Write Batch over its port,
    recording whatever it raised."""
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


# --------------------------------------------------------------------------- #
# Steps running alone.                                                         #
# --------------------------------------------------------------------------- #

_ACCOUNT_META: Final = model_of(ACCOUNT)
_ACCOUNT: Final = entity_by_name(_ACCOUNT_META, "Account")
assert _ACCOUNT is not None
_ID: Final = AttributeIdentity(_ACCOUNT.identity, "id")


def _delete(key: int) -> PlannedDelete:
    return PlannedDelete(
        entity=_ACCOUNT.identity,
        target=KeyTarget((_ID,), ((key,),)),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(1, MISSING_TARGET),
    )


def test_a_shortfall_is_enforced_before_the_next_step_is_taken() -> None:
    port = ScriptedAdapter(Write(affected=0))
    segment = HeldSteps(port, (_delete(1), _delete(2)))
    view = PlannedWrites((segment,)).view(0, len(segment))
    with pytest.raises(MissingTargetError), write_batch() as batch:
        step_executor(port, _ACCOUNT_META).execute(view, allocates=False, batch=batch)
    assert segment.asked == [(0, 0)]
    assert len(port.calls) == 1


class Span(Bitemporal, table="span", namespace="parallax.execution.allocated"):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


_SPANS: Final = DomainModel(Span)


def test_an_allocating_span_answers_the_keys_its_insert_returned() -> None:
    meta = model_of(_SPANS)
    prepared = prepare_typed_write(
        KeyedWriteInstruction(
            "insert",
            Span.identity.canonical,
            ({"id": {"computed": "maxPlusOne"}, "amount": 1},),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        ),
        meta,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    plan = build_write_planner(meta).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-01-10T00:00:00+00:00"),
            concurrency="optimistic",
            buffered_writes=[prepared],
        )
    )
    (unit,) = plan.units
    assert unit.opened.allocated
    port = ScriptedAdapter(Read(rows=[{"id": 42}]))
    with write_batch() as batch:
        answered = step_executor(port, meta).execute(
            plan.steps.view(0, unit.end), allocates=True, batch=batch
        )
    assert answered == (42,)
    # The insert ran as row-producing DML rather than as a counted write.
    assert [type(call) for call in port.calls] == [ReadCall]


# --------------------------------------------------------------------------- #
# Grouped temporal openings.                                                   #
# --------------------------------------------------------------------------- #


def test_a_run_of_openings_is_one_call_and_the_step_ending_it_is_lowered_only_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openings = (opening(1), opening(2, Decimal(2)), opening(3, Decimal(3)))
    boundary = close(1)
    port = ScriptedAdapter(Write(affected=3), Write())
    lowered_at: list[int] = []
    lowered_alone = LoweringCursor.lowered

    def lowering(cursor: LoweringCursor, step: PlannedWrite) -> LoweredStatement:
        lowered_at.append(len(port.calls))
        return lowered_alone(cursor, step)

    monkeypatch.setattr(LoweringCursor, "lowered", lowering)
    provider = RecordingLifecycleProvider()
    executed = _execute(HeldSteps(port, (*openings, boundary)), provider)
    assert executed.raised is None
    assert port.calls == [*physical(*openings), alone(boundary)]
    # The close ending the run was taken, unprepared, before the run's insert
    # ran, and lowered only once it had.
    assert executed.segment.asked == [(0, 0), (1, 0), (2, 0), (3, 0)]
    assert lowered_at == [1]
    events = [event for root in provider.roots for event in root.events]
    started, _ = [event for event in events if isinstance(event, DatabaseCallStarted)]
    finished, _ = [event for event in events if isinstance(event, DatabaseCallFinished)]
    assert (started.kind, started.target) == ("write", POSITION.canonical)
    assert finished.outcome == DatabaseWriteCompleted(3)
    assert finished.shared_timing_id is None


def test_the_step_after_a_capped_run_is_taken_only_once_its_statement_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_OPENING_CAP, 2)
    openings = (opening(1), opening(2), opening(3))
    port = ScriptedAdapter(Write(affected=2), Write())
    executed = _execute(HeldSteps(port, openings))
    assert executed.raised is None
    assert port.calls == [*physical(*openings[:2]), *physical(openings[2])]
    assert executed.segment.asked == [(0, 0), (1, 0), (2, 1)]


def test_a_later_openings_refusal_inserts_the_prefix_then_propagates() -> None:
    prefix = (opening(1), opening(2))
    port = ScriptedAdapter(Write(affected=2))
    executed = _execute(HeldSteps(port, (*prefix, opening(3, "no decimal"), opening(4))))
    assert isinstance(executed.raised, SqlGenError)
    assert port.calls == physical(*prefix)
    assert executed.segment.taken == [0, 1, 2]


def test_a_later_step_failing_to_be_built_inserts_the_prefix_then_propagates() -> None:
    prefix = (opening(1), opening(2))
    failure = RuntimeError("the third opening's backing cannot be rebuilt")
    port = ScriptedAdapter(Write(affected=2))
    executed = _execute(HeldSteps(port, (*prefix, opening(3)), failing=2, failure=failure))
    assert executed.raised is failure
    assert port.calls == physical(*prefix)


def test_the_prefixs_own_failure_wins_over_the_refusal_it_overtook() -> None:
    violation = DatabaseError(
        category="uniqueViolation", native_code="23505", message="duplicate key"
    )
    port = ScriptedAdapter(Write(raises=violation))
    executed = _execute(HeldSteps(port, (opening(1), opening(2), opening(3, "no decimal"))))
    assert executed.raised is violation
    assert violation.__context__ is None
    assert violation.__cause__ is None


def test_a_failure_preparing_the_first_opening_inserts_nothing() -> None:
    port = ScriptedAdapter()
    executed = _execute(HeldSteps(port, (opening(1, "no decimal"), opening(2))))
    assert isinstance(executed.raised, SqlGenError)
    assert port.calls == []
    assert executed.segment.asked == [(0, 0)]


def test_a_control_flow_exception_taking_a_later_opening_inserts_none_of_the_run() -> None:
    interrupt = KeyboardInterrupt()
    port = ScriptedAdapter()
    executed = _execute(
        HeldSteps(port, (opening(1), opening(2), opening(3)), failing=2, failure=interrupt)
    )
    assert executed.raised is interrupt
    assert port.calls == []


def test_the_statements_a_span_runs_are_the_ones_its_dry_traversal_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_OPENING_CAP, 2)
    steps = (close(1), opening(1), opening(2), opening(3), close(2), opening(4))
    statements = physical(*steps)
    assert len(statements) == 5
    port = ScriptedAdapter(Write(), Write(affected=2), Write(), Write(), Write())
    executed = _execute(HeldSteps(port, steps))
    assert executed.raised is None
    assert port.calls == statements
    assert all(isinstance(call, WriteCall) for call in port.calls)


@dataclass
class _Claim:
    """Source authority recording how many port calls had been made when a
    unit spent it."""

    port: ScriptedAdapter
    spent_at: int | None = None

    def consume(self) -> None:
        self.spent_at = len(self.port.calls)


def test_a_run_of_openings_never_reaches_into_a_later_units_span() -> None:
    first = (close(1), opening(1), opening(2), opening(3))
    second = (opening(5),)
    port = ScriptedAdapter(Write(), Write(affected=3), Write())
    claims = (_Claim(port), _Claim(port))
    plan = WritePlan(
        steps=PlannedWrites((HeldSteps(port, (*first, *second)),)),
        units=(ExecutionUnit(end=4, claim=claims[0]), ExecutionUnit(end=5, claim=claims[1])),
    )
    with write_batch() as batch:
        run_plan(port, plan, batch)
    assert port.calls == [*physical(*first), *physical(*second)]
    # Each unit completed once its own statements ran.
    assert [claim.spent_at for claim in claims] == [2, 3]


def test_a_unit_whose_grouped_statement_fails_completes_nothing_and_takes_no_later_step() -> None:
    violation = DatabaseError(
        category="uniqueViolation", native_code="23505", message="duplicate key"
    )
    port = ScriptedAdapter(Write(), Write(raises=violation))
    segment = HeldSteps(port, (close(1), opening(1), opening(2), opening(3), opening(5)))
    claims = (_Claim(port), _Claim(port))
    plan = WritePlan(
        steps=PlannedWrites((segment,)),
        units=(ExecutionUnit(end=4, claim=claims[0]), ExecutionUnit(end=5, claim=claims[1])),
    )
    with pytest.raises(DatabaseError) as raised, write_batch() as batch:
        run_plan(port, plan, batch)
    assert raised.value is violation
    assert segment.taken == [0, 1, 2, 3]
    assert [claim.spent_at for claim in claims] == [None, None]


def _builders() -> set[int]:
    gc.collect()
    return {
        id(item) for item in gc.get_objects() if type(item).__name__ == "InsertStatementBuilder"
    }


def test_a_grouped_run_keeps_no_builder_alive_once_it_ran_or_its_failure_is_released() -> None:
    before = _builders()
    port = ScriptedAdapter(Write(affected=3))
    assert _execute(HeldSteps(port, (opening(1), opening(2), opening(3)))).raised is None
    assert _builders() <= before
    port = ScriptedAdapter(Write(affected=1))
    executed = _execute(HeldSteps(port, (opening(1), opening(2, "no decimal"))))
    assert isinstance(executed.raised, SqlGenError)
    executed.raised = None
    assert _builders() <= before
