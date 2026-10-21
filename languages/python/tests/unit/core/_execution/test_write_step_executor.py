"""The production step executor over a scripted port (`m-execution`).

Each step of the tuple it is handed is prepared and lowered only after every
earlier step was enforced; a step running alone is one Database Call enforced
as itself, a run of compatible single-entry inserts — temporal openings here —
is one multi-row insert, and an insert whose key the database allocates
answers that key. The statements execution runs are the ones a dry traversal
of the same steps answers.
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
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.core.execution_lifecycle import (
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseWriteCompleted,
    ExecutionLifecycleProvider,
)
from parallax.core.metamodel import AttributeIdentity, entity_by_name
from parallax.core.sql_gen import SqlGenError
from parallax.core.unit_work import KeyedWriteInstruction, MissingTargetError, WritePlanningRequest
from parallax.core.write_plan import WritePlan
from parallax.core.write_plan.plan import SettledWrite, WriteGroup
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedDelete,
    PlannedStep,
)
from tests._support.clock_probes import instant_at
from tests._support.db_port import Read, ReadCall, ScriptedAdapter, Write, WriteCall
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit.core._execution._execution_support import ACCOUNT
from tests.unit.core._execution._write_step_support import (
    POSITION,
    RecordingPreparer,
    alone,
    close,
    open_flush,
    opening,
    physical,
    run_plan,
    step_executor,
)

_GROUPED_INSERT_CAP: Final = "parallax.core._execution._write_lowering._GROUPED_INSERT_ROWS"


@dataclass
class _Executed:
    preparer: RecordingPreparer
    answered: tuple[object, ...] | None = None
    raised: BaseException | None = None


def _execute(
    port: ScriptedAdapter,
    steps: tuple[PlannedStep, ...],
    provider: ExecutionLifecycleProvider | None = None,
    *,
    failing: int | None = None,
    failure: BaseException | None = None,
) -> _Executed:
    executed = _Executed(RecordingPreparer(port, steps, failing=failing, failure=failure))
    try:
        with open_flush(provider) as flush:
            executed.answered = step_executor(port, payloads=executed.preparer).execute(
                steps, allocates=False, flush=flush
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


def test_a_shortfall_is_enforced_before_the_next_step_is_presented() -> None:
    port = ScriptedAdapter(Write(affected=0))
    with pytest.raises(MissingTargetError), open_flush() as flush:
        step_executor(port, _ACCOUNT_META).execute(
            (_delete(1), _delete(2)), allocates=False, flush=flush
        )
    assert len(port.calls) == 1


class Span(Bitemporal, table="span", namespace="parallax.execution.allocated"):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


_SPANS: Final = DomainModel(Span)


def test_allocating_steps_answer_the_keys_their_insert_returned() -> None:
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
    (group,) = plan.groups
    (write,) = group.writes
    assert write.opened.allocated
    port = ScriptedAdapter(Read(rows=[{"id": 42}]))
    with open_flush() as flush:
        answered = step_executor(port, meta).execute(group.steps, allocates=True, flush=flush)
    assert answered == (42,)
    # The insert ran as row-producing DML rather than as a counted write.
    assert [type(call) for call in port.calls] == [ReadCall]


# --------------------------------------------------------------------------- #
# Grouped temporal openings.                                                   #
# --------------------------------------------------------------------------- #


def test_a_run_of_openings_is_one_call_and_the_step_ending_it_is_prepared_only_after_it() -> None:
    openings = (opening(1), opening(2, Decimal(2)), opening(3, Decimal(3)))
    boundary = close(1)
    port = ScriptedAdapter(Write(affected=3), Write())
    provider = RecordingLifecycleProvider()
    executed = _execute(port, (*openings, boundary), provider)
    assert executed.raised is None
    assert port.calls == [*physical(*openings), alone(boundary)]
    # The close ending the run waited unprepared while the run's insert ran.
    assert executed.preparer.prepared == [(0, 0), (1, 0), (2, 0), (3, 1)]
    events = [event for root in provider.roots for event in root.events]
    started, _ = [event for event in events if isinstance(event, DatabaseCallStarted)]
    finished, _ = [event for event in events if isinstance(event, DatabaseCallFinished)]
    assert (started.kind, started.target) == ("write", POSITION.canonical)
    assert finished.outcome == DatabaseWriteCompleted(3)
    assert finished.shared_timing_id is None


def test_the_step_after_a_capped_run_is_prepared_only_once_its_statement_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_GROUPED_INSERT_CAP, 2)
    openings = (opening(1), opening(2), opening(3))
    port = ScriptedAdapter(Write(affected=2), Write())
    executed = _execute(port, openings)
    assert executed.raised is None
    assert port.calls == [*physical(*openings[:2]), *physical(openings[2])]
    assert executed.preparer.prepared == [(0, 0), (1, 0), (2, 1)]


def test_a_later_openings_refusal_inserts_the_prefix_then_propagates() -> None:
    prefix = (opening(1), opening(2))
    port = ScriptedAdapter(Write(affected=2))
    executed = _execute(port, (*prefix, opening(3, "no decimal"), opening(4)))
    assert isinstance(executed.raised, SqlGenError)
    assert port.calls == physical(*prefix)
    assert executed.preparer.positions == [0, 1, 2]


def test_a_later_opening_failing_to_be_prepared_inserts_the_prefix_then_propagates() -> None:
    prefix = (opening(1), opening(2))
    failure = RuntimeError("the third opening cannot be prepared")
    port = ScriptedAdapter(Write(affected=2))
    executed = _execute(port, (*prefix, opening(3), opening(4)), failing=2, failure=failure)
    assert executed.raised is failure
    assert port.calls == physical(*prefix)
    assert executed.preparer.positions == [0, 1, 2]


def test_the_prefixs_own_failure_wins_over_the_refusal_it_overtook() -> None:
    violation = DatabaseError(
        category="uniqueViolation", native_code="23505", message="duplicate key"
    )
    port = ScriptedAdapter(Write(raises=violation))
    executed = _execute(port, (opening(1), opening(2), opening(3, "no decimal")))
    assert executed.raised is violation
    assert violation.__context__ is None
    assert violation.__cause__ is None


def test_a_failure_preparing_the_first_opening_inserts_nothing() -> None:
    port = ScriptedAdapter()
    executed = _execute(port, (opening(1, "no decimal"), opening(2)))
    assert isinstance(executed.raised, SqlGenError)
    assert port.calls == []
    assert executed.preparer.prepared == [(0, 0)]


def test_a_control_flow_exception_preparing_a_later_opening_inserts_none_of_the_run() -> None:
    interrupt = KeyboardInterrupt()
    port = ScriptedAdapter()
    executed = _execute(port, (opening(1), opening(2), opening(3)), failing=2, failure=interrupt)
    assert executed.raised is interrupt
    assert port.calls == []


def test_the_statements_execution_runs_are_the_ones_a_dry_traversal_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_GROUPED_INSERT_CAP, 2)
    steps = (close(1), opening(1), opening(2), opening(3), close(2), opening(4))
    statements = physical(*steps)
    assert len(statements) == 5
    port = ScriptedAdapter(Write(), Write(affected=2), Write(), Write(), Write())
    executed = _execute(port, steps)
    assert executed.raised is None
    assert port.calls == statements
    assert all(isinstance(call, WriteCall) for call in port.calls)


def test_a_run_of_openings_never_reaches_into_a_later_groups_steps() -> None:
    first = (close(1), opening(1), opening(2), opening(3))
    second = (opening(5),)
    port = ScriptedAdapter(Write(), Write(affected=3), Write())
    plan = WritePlan((WriteGroup((SettledWrite(),), first), WriteGroup((SettledWrite(),), second)))
    completed: list[int] = []
    with open_flush() as flush:
        run_plan(port, plan, flush, completed=completed)
    assert port.calls == [*physical(*first), *physical(*second)]
    # Each group's write completed once its own statements ran.
    assert completed == [2, 3]


def test_a_group_whose_grouped_statement_fails_completes_nothing_and_prepares_no_later_step() -> (
    None
):
    violation = DatabaseError(
        category="uniqueViolation", native_code="23505", message="duplicate key"
    )
    port = ScriptedAdapter(Write(), Write(raises=violation))
    first = (close(1), opening(1), opening(2), opening(3))
    second = (opening(5),)
    preparer = RecordingPreparer(port, (*first, *second))
    plan = WritePlan((WriteGroup((SettledWrite(),), first), WriteGroup((SettledWrite(),), second)))
    completed: list[int] = []
    with pytest.raises(DatabaseError) as raised, open_flush() as flush:
        run_plan(port, plan, flush, payloads=preparer, completed=completed)
    assert raised.value is violation
    assert preparer.positions == [0, 1, 2, 3]
    assert completed == []


def _builders() -> set[int]:
    gc.collect()
    return {
        id(item) for item in gc.get_objects() if type(item).__name__ == "InsertStatementBuilder"
    }


def test_a_grouped_run_keeps_no_builder_alive_once_it_ran_or_its_failure_is_released() -> None:
    before = _builders()
    port = ScriptedAdapter(Write(affected=3))
    assert _execute(port, (opening(1), opening(2), opening(3))).raised is None
    assert _builders() <= before
    port = ScriptedAdapter(Write(affected=1))
    executed = _execute(port, (opening(1), opening(2, "no decimal")))
    assert isinstance(executed.raised, SqlGenError)
    executed.raised = None
    assert _builders() <= before
