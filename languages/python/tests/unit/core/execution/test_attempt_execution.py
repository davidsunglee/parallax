"""The Attempt's flush execution over a scripted port (`m-execution`).

Every execution unit, bound range, and continuation round runs through one step
driver over a span its owner lends: each step is taken from its sequence once,
lowered only after every earlier step was enforced, and each unit is reported
before any step of a later unit is taken, a deferred unit binding at its own
turn and a continuation round released before the next is pulled.
"""

from __future__ import annotations

import datetime as dt
import gc
import weakref
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.class_models import MODELS
from parallax.core import MAX, Attr, Bitemporal, DomainModel, attr
from parallax.core.base import INFINITY as OPEN
from parallax.core.db_error import DatabaseError
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.execution._attempt import Attempt
from parallax.core.execution._planning import build_write_planner
from parallax.core.execution._write_lowering import LoweringCursor, stream_physical
from parallax.core.execution_lifecycle import (
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseWriteCompleted,
)
from parallax.core.metamodel import AttributeIdentity, entity_by_name
from parallax.core.sql_gen import SqlGenError
from parallax.core.unit_work import KeyedWrite, MissingTargetError, WritePlanningRequest
from parallax.core.unit_work.instructions import PreparedKeyedWrite, prepare_typed_write
from parallax.core.unit_work.uow import BindDeferredRange, DeferredWriteContinuation
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import SUPERSEDED, WritePlan
from parallax.core.write_plan.plan import (
    BoundRange,
    DeferredRange,
    ExecutionUnit,
    PlannedWrites,
    UnitEffects,
)
from parallax.core.write_plan.steps import (
    INFINITY,
    MISSING_TARGET,
    NEW_LINEAGE,
    STALE_WRITE,
    UNGATED,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedWrite,
    WriteRow,
)
from tests._support.clock_probes import instant_at
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.opening_selection import select_grouped_openings
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit.core.execution._execution_support import ACCOUNT, itself, scope

_META: Final = model_of(ACCOUNT)
_ACCOUNT: Final = entity_by_name(_META, "Account")
assert _ACCOUNT is not None
_ID: Final = AttributeIdentity(_ACCOUNT.identity, "id")


def _delete(key: int) -> PlannedDelete:
    return PlannedDelete(
        entity=_ACCOUNT.identity,
        target=KeyTarget((_ID,), ((key,),)),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(1, MISSING_TARGET),
    )


class _Taken:
    """A segment that builds each step only when asked for it, as a lazily
    backed segment does, recording every position it was asked for."""

    def __init__(self, *keys: int) -> None:
        self._keys = keys
        self.asked: list[int] = []

    def __len__(self) -> int:
        return len(self._keys)

    def step(self, index: int) -> PlannedWrite:
        self.asked.append(index)
        return _delete(self._keys[index])


class _Deferred(DeferredRange):
    __slots__ = ()


@dataclass
class _Reported:
    """Every unit the flush reported, with how many statements had run and
    which steps had been taken when it was."""

    port: ScriptedAdapter
    segments: tuple[_Taken, ...]
    units: list[tuple[ExecutionUnit, UnitEffects | None, tuple[object, ...]]] = field(
        default_factory=list[tuple[ExecutionUnit, UnitEffects | None, tuple[object, ...]]]
    )
    seen: list[tuple[int, tuple[tuple[int, ...], ...]]] = field(
        default_factory=list[tuple[int, tuple[tuple[int, ...], ...]]]
    )

    def mark(self) -> None:
        self.seen.append(
            (_writes(self.port), tuple(tuple(segment.asked) for segment in self.segments))
        )

    def __call__(
        self,
        unit: ExecutionUnit,
        bound: UnitEffects | None,
        /,
        *,
        allocated: tuple[object, ...] = (),
    ) -> None:
        self.units.append((unit, bound, allocated))
        self.mark()


def _writes(port: ScriptedAdapter) -> int:
    return sum(isinstance(call, WriteCall) for call in port.calls)


def _unbound(description: DeferredRange, /) -> BoundRange | DeferredWriteContinuation:
    raise AssertionError(f"no unit of this plan defers, yet {description!r} was bound")


def _flush(
    attempt: Attempt,
    plan: WritePlan,
    completed: _Reported,
    bind_deferred: BindDeferredRange = _unbound,
) -> None:
    attempt._execute_flush(  # pyright: ignore[reportPrivateUsage] - drives the executor over a hand-built plan
        plan, trigger="pre_commit", bind_deferred=bind_deferred, completed=completed
    )


def _run(port: ScriptedAdapter, body: Callable[[Attempt], None]) -> None:
    scope(port).transact(body, itself, concurrency="locking")


def test_each_unit_is_reported_before_any_step_of_the_next_is_taken() -> None:
    first, second = _Taken(1, 2), _Taken(3)
    plan = WritePlan(
        steps=PlannedWrites((first, second)),
        units=(ExecutionUnit(end=2), ExecutionUnit(end=2), ExecutionUnit(end=3)),
    )
    port = ScriptedAdapter(Transact(Write(times=3)))
    reported = _Reported(port, (first, second))
    _run(port, lambda attempt: _flush(attempt, plan, reported))
    assert [unit for unit, _bound, _allocated in reported.units] == list(plan.units)
    assert all(bound is None and allocated == () for _unit, bound, allocated in reported.units)
    # The empty middle unit completes where the first ends, before the step
    # after it is even taken; every step is taken exactly once.
    assert reported.seen == [(2, ((0, 1), ())), (2, ((0, 1), ())), (3, ((0, 1), (0,)))]


def test_a_shortfall_takes_no_later_step_and_reports_no_unit() -> None:
    steps = _Taken(1, 2)
    plan = WritePlan(steps=PlannedWrites((steps,)), units=(ExecutionUnit(end=2),))
    port = ScriptedAdapter(Transact(Write(affected=0)))
    reported = _Reported(port, (steps,))

    def body(attempt: Attempt) -> None:
        with pytest.raises(MissingTargetError):
            _flush(attempt, plan, reported)

    _run(port, body)
    assert steps.asked == [0]
    assert reported.units == []
    assert _writes(port) == 1


def test_a_deferred_unit_binds_at_its_turn_and_runs_what_it_bound() -> None:
    planned, bound_steps = _Taken(1), _Taken(2, 3)
    deferred = _Deferred()
    plan = WritePlan(
        steps=PlannedWrites((planned,)),
        units=(ExecutionUnit(end=1), ExecutionUnit(end=1, deferred=deferred)),
    )
    port = ScriptedAdapter(Transact(Write(times=3)))
    reported = _Reported(port, (planned, bound_steps))
    bound = BoundRange(steps=PlannedWrites((bound_steps,)))

    def bind(description: DeferredRange, /) -> BoundRange:
        assert description is deferred
        reported.mark()
        return bound

    _run(port, lambda attempt: _flush(attempt, plan, reported, bind))
    assert [(unit, effects) for unit, effects, _allocated in reported.units] == [
        (plan.units[0], None),
        (plan.units[1], bound),
    ]
    # Binding happens once the earlier unit was reported, and the bound steps
    # run, each taken once, before the deferred unit is.
    assert reported.seen == [(1, ((0,), ())), (1, ((0,), ())), (3, ((0,), (0, 1)))]


@dataclass
class _Rounds:
    """A continuation preparing ``rounds`` in turn, keeping nothing of a round
    it handed over but a way to tell whether it is still alive."""

    port: ScriptedAdapter
    rounds: Iterator[tuple[int, ...]]
    effects: UnitEffects = field(default_factory=UnitEffects)
    pulled: list[int] = field(default_factory=list[int])
    finished: int = 0
    closed: int = 0
    previous: weakref.ref[_Taken] | None = None
    released: list[bool] = field(default_factory=list[bool])

    def pull(self) -> PlannedWrites | None:
        if self.previous is not None:
            self.released.append(self.previous() is None)
        self.pulled.append(_writes(self.port))
        keys = next(self.rounds, None)
        if keys is None:
            return None
        segment = _Taken(*keys)
        self.previous = weakref.ref(segment)
        return PlannedWrites((segment,))

    def finish(self) -> UnitEffects:
        self.finished += 1
        return self.effects

    def close(self) -> None:
        self.closed += 1


def _continued_plan() -> tuple[WritePlan, _Deferred]:
    deferred = _Deferred()
    return WritePlan(units=(ExecutionUnit(end=0, deferred=deferred),)), deferred


def test_each_round_runs_and_is_released_before_the_next_is_pulled() -> None:
    plan, deferred = _continued_plan()
    port = ScriptedAdapter(Transact(Write(times=3)))
    rounds = _Rounds(port, iter([(1, 2), (), (3,)]))
    reported = _Reported(port, ())

    def bind(description: DeferredRange, /) -> DeferredWriteContinuation:
        assert description is deferred
        return rounds

    _run(port, lambda attempt: _flush(attempt, plan, reported, bind))
    assert rounds.pulled == [0, 2, 2, 3]
    assert rounds.released == [True, True, True]
    assert (rounds.finished, rounds.closed) == (1, 1)
    assert [(unit, effects) for unit, effects, _allocated in reported.units] == [
        (plan.units[0], rounds.effects)
    ]


def test_a_failed_round_closes_its_continuation_once_and_pulls_nothing_more() -> None:
    plan, _deferred = _continued_plan()
    port = ScriptedAdapter(Transact(Write(), Write(affected=0)))
    rounds = _Rounds(port, iter([(1, 2), (3,)]))
    reported = _Reported(port, ())

    def body(attempt: Attempt) -> None:
        with pytest.raises(MissingTargetError):
            _flush(attempt, plan, reported, lambda _description: rounds)

    _run(port, body)
    assert rounds.pulled == [0]
    assert (rounds.finished, rounds.closed) == (0, 1)
    assert reported.units == []


class Span(Bitemporal, table="span", namespace="parallax.execution.allocated"):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


_SPANS: Final = DomainModel(Span)


def test_a_unit_opening_allocated_rows_is_reported_with_the_keys_its_insert_answered() -> None:
    meta = model_of(_SPANS)
    prepared = prepare_typed_write(
        KeyedWrite(
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
    port = ScriptedAdapter(Transact(Read(rows=[{"id": 42}])))
    reported = _Reported(port, ())
    scope(port, _SPANS).transact(
        lambda attempt: _flush(attempt, plan, reported), itself, concurrency="optimistic"
    )
    assert reported.units == [(unit, None, (42,))]
    assert _writes(port) == 0


# --------------------------------------------------------------------------- #
# Grouped temporal openings.                                                   #
# --------------------------------------------------------------------------- #

_POSITIONS: Final = MODELS["position"]
_POSITION_META: Final = model_of(_POSITIONS)
_POSITION_ENTITY = entity_by_name(_POSITION_META, "Position")
assert _POSITION_ENTITY is not None
_POSITION: Final = _POSITION_ENTITY.identity
_OPENING_CAP: Final = "parallax.core.execution._write_lowering._OPENING_ENTRY_CAP"
_AT: Final = dt.datetime(2024, 2, 15, tzinfo=dt.UTC)


def _position(name: str) -> AttributeIdentity:
    return AttributeIdentity(_POSITION, name)


def _opening(month: int, value: object = Decimal("1.00")) -> PlannedInsert:
    """Position 1's opening over ``month``, at ``value``."""
    row = PlannedRow(
        attributes={
            _position("id"): 1,
            _position("acctNum"): "A-1",
            _position("value"): value,
            _position("validStart"): dt.datetime(2024, month, 1, tzinfo=dt.UTC),
            _position("validEnd"): dt.datetime(2024, month + 1, 1, tzinfo=dt.UTC),
            _position("txStart"): _AT,
            _position("txEnd"): OPEN,
        }
    )
    return PlannedInsert(entity=_POSITION, entries=(WriteRow(row=row, origin=NEW_LINEAGE),))


def _close(key: int) -> PlannedClose:
    return PlannedClose(
        entity=_POSITION,
        target=MilestoneTarget(
            key_attributes=(_position("id"),),
            key_values=(key,),
            end_attributes=(_position("validEnd"), _position("txEnd")),
            end_values=(INFINITY, INFINITY),
        ),
        assignments=PlannedAssignments(attributes={_position("txEnd"): _AT}),
        cause=SUPERSEDED,
        concurrency=UNGATED,
        affected_rows=ExactCount(1, STALE_WRITE),
    )


@dataclass
class _Held:
    """A segment handing out ``steps`` only when asked, recording each position
    asked with how many writes had run by then, and raising ``failure`` instead
    of building the step at ``failing``."""

    port: ScriptedAdapter
    steps: tuple[PlannedWrite, ...]
    failing: int | None = None
    failure: BaseException | None = None
    asked: list[tuple[int, int]] = field(default_factory=list[tuple[int, int]])

    def __len__(self) -> int:
        return len(self.steps)

    def step(self, index: int) -> PlannedWrite:
        self.asked.append((index, _writes(self.port)))
        if index == self.failing and self.failure is not None:
            raise self.failure
        return self.steps[index]


def _physical(*steps: PlannedWrite) -> list[WriteCall]:
    """The writes a dry traversal of ``steps`` answers, as the port receives them."""
    return [
        WriteCall(POSTGRES.to_driver_sql(statement.sql), statement.binds)
        for statement in stream_physical(
            steps, LayoutPayloadPreparer(_POSITION_META), _POSITION_META, POSTGRES
        )
    ]


def _openings_run(
    port: ScriptedAdapter, segment: _Held, provider: RecordingLifecycleProvider | None = None
) -> list[PlannedWrite | BaseException | None]:
    """Run the grouped opening operation from ``segment``'s first step inside one
    Write Batch, answering the step after the run or what it raised."""
    answered: list[PlannedWrite | BaseException | None] = []

    def body(attempt: Attempt) -> None:
        with attempt._open_write_batch("pre_commit"):  # pyright: ignore[reportPrivateUsage] - one batch around the operation
            cursor = LoweringCursor(
                PlannedWrites((segment,)).view(0, len(segment)),
                LayoutPayloadPreparer(_POSITION_META),
                _POSITION_META,
                POSTGRES,
            )
            step = cursor.take()
            assert step is not None
            first = cursor.opening(step)
            assert first is not None
            try:
                answered.append(attempt._run_openings(first, cursor))  # pyright: ignore[reportPrivateUsage] - the operation under proof
            except BaseException as raised:
                answered.append(raised)

    scope(port, _POSITIONS, provider=provider).transact(body, itself, concurrency="locking")
    return answered


def test_a_run_of_openings_is_one_database_call_answering_the_step_after_it_unlowered() -> None:
    openings = (_opening(1), _opening(2, Decimal(2)), _opening(3, Decimal(3)))
    boundary = _close(1)
    port = ScriptedAdapter(Transact(Write(affected=3)))
    segment = _Held(port, (*openings, boundary))
    provider = RecordingLifecycleProvider()
    assert _openings_run(port, segment, provider) == [boundary]
    assert port.calls == [BeginCall(), *_physical(*openings), CommitCall()]
    assert segment.asked == [(0, 0), (1, 0), (2, 0), (3, 0)]
    events = [event for root in provider.roots for event in root.events]
    (started,) = [event for event in events if isinstance(event, DatabaseCallStarted)]
    (finished,) = [event for event in events if isinstance(event, DatabaseCallFinished)]
    assert (started.kind, started.target) == ("write", _POSITION.canonical)
    assert finished.outcome == DatabaseWriteCompleted(3)
    assert finished.shared_timing_id is None


def test_the_step_after_a_capped_run_is_taken_only_once_its_statement_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_OPENING_CAP, 2)
    openings = (_opening(1), _opening(2), _opening(3))
    port = ScriptedAdapter(Transact(Write(affected=2)))
    segment = _Held(port, openings)
    assert _openings_run(port, segment) == [openings[2]]
    assert port.calls == [BeginCall(), *_physical(*openings[:2]), CommitCall()]
    assert segment.asked == [(0, 0), (1, 0), (2, 1)]


def test_a_later_openings_refusal_inserts_the_prefix_then_propagates() -> None:
    prefix = (_opening(1), _opening(2))
    port = ScriptedAdapter(Transact(Write(affected=2)))
    segment = _Held(port, (*prefix, _opening(3, "no decimal"), _opening(4)))
    (raised,) = _openings_run(port, segment)
    assert isinstance(raised, SqlGenError)
    assert port.calls == [BeginCall(), *_physical(*prefix), CommitCall()]
    assert [index for index, _writes_by_then in segment.asked] == [0, 1, 2]


def test_a_later_step_failing_to_be_built_inserts_the_prefix_then_propagates() -> None:
    prefix = (_opening(1), _opening(2))
    failure = RuntimeError("the third opening's backing cannot be rebuilt")
    port = ScriptedAdapter(Transact(Write(affected=2)))
    segment = _Held(port, (*prefix, _opening(3)), failing=2, failure=failure)
    assert _openings_run(port, segment) == [failure]
    assert port.calls == [BeginCall(), *_physical(*prefix), CommitCall()]


def test_the_prefixs_own_failure_wins_over_the_refusal_it_overtook() -> None:
    violation = DatabaseError(
        category="uniqueViolation", native_code="23505", message="duplicate key"
    )
    port = ScriptedAdapter(Transact(Write(raises=violation)))
    segment = _Held(port, (_opening(1), _opening(2), _opening(3, "no decimal")))
    (raised,) = _openings_run(port, segment)
    assert raised is violation
    assert violation.__context__ is None
    assert violation.__cause__ is None


def test_a_failure_preparing_the_first_opening_inserts_nothing() -> None:
    port = ScriptedAdapter(Transact())
    segment = _Held(port, (_opening(1, "no decimal"), _opening(2)))
    (raised,) = _openings_run(port, segment)
    assert isinstance(raised, SqlGenError)
    assert port.calls == [BeginCall(), CommitCall()]
    assert segment.asked == [(0, 0)]


def test_a_control_flow_exception_taking_a_later_opening_inserts_none_of_the_run() -> None:
    interrupt = KeyboardInterrupt()
    port = ScriptedAdapter(Transact())
    segment = _Held(port, (_opening(1), _opening(2), _opening(3)), failing=2, failure=interrupt)
    assert _openings_run(port, segment) == [interrupt]
    assert port.calls == [BeginCall(), CommitCall()]


def _run_positions(port: ScriptedAdapter, body: Callable[[Attempt], None]) -> None:
    scope(port, _POSITIONS).transact(body, itself, concurrency="locking")


def test_a_grouped_unit_reports_once_after_its_statement_and_a_failed_one_reports_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    select_grouped_openings(monkeypatch)
    first = (_close(1), _opening(1), _opening(2), _opening(3))
    second = (_opening(5),)
    plan = WritePlan(
        steps=PlannedWrites((_Held(ScriptedAdapter(), (*first, *second)),)),
        units=(ExecutionUnit(end=4), ExecutionUnit(end=5)),
    )

    port = ScriptedAdapter(Transact(Write(), Write(affected=3), Write()))
    reported = _Reported(port, ())
    _run_positions(port, lambda attempt: _flush(attempt, plan, reported))
    assert port.calls == [BeginCall(), *_physical(*first), *_physical(*second), CommitCall()]
    assert [
        (unit, writes)
        for (unit, _bound, _allocated), (writes, _asked) in zip(
            reported.units, reported.seen, strict=True
        )
    ] == [(plan.units[0], 2), (plan.units[1], 3)]

    violation = DatabaseError(
        category="uniqueViolation", native_code="23505", message="duplicate key"
    )
    failing = ScriptedAdapter(Transact(Write(), Write(raises=violation)))
    segment = _Held(failing, (*first, *second))
    failed_plan = WritePlan(steps=PlannedWrites((segment,)), units=plan.units)
    unreported = _Reported(failing, ())

    def body(attempt: Attempt) -> None:
        with pytest.raises(DatabaseError) as raised:
            _flush(attempt, failed_plan, unreported)
        assert raised.value is violation

    _run_positions(failing, body)
    assert unreported.units == []
    assert [index for index, _writes_by_then in segment.asked] == [0, 1, 2, 3]


def test_a_flushed_runs_statements_are_the_ones_its_dry_traversal_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_OPENING_CAP, 2)
    select_grouped_openings(monkeypatch)
    steps = (_close(1), _opening(1), _opening(2), _opening(3), _close(2), _opening(4))
    physical = _physical(*steps)
    assert len(physical) == 5
    port = ScriptedAdapter(Transact(Write(), Write(affected=2), Write(), Write(), Write()))
    plan = WritePlan(steps=PlannedWrites((_Held(port, steps),)), units=(ExecutionUnit(end=6),))
    _run_positions(port, lambda attempt: _flush(attempt, plan, _Reported(port, ())))
    assert port.calls == [BeginCall(), *physical, CommitCall()]


def _builders() -> set[int]:
    gc.collect()
    return {
        id(item) for item in gc.get_objects() if type(item).__name__ == "InsertStatementBuilder"
    }


def test_a_grouped_run_keeps_no_builder_alive_once_it_ran_or_its_failure_is_released() -> None:
    before = _builders()
    port = ScriptedAdapter(Transact(Write(affected=3)))
    assert _openings_run(port, _Held(port, (_opening(1), _opening(2), _opening(3)))) == [None]
    assert _builders() <= before
    port = ScriptedAdapter(Transact(Write(affected=1)))
    answered = _openings_run(port, _Held(port, (_opening(1), _opening(2, "no decimal"))))
    assert isinstance(answered[0], SqlGenError)
    answered.clear()
    assert _builders() <= before
