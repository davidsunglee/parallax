"""The Attempt's walk over a flush's execution units, over a scripted port
(`m-execution`).

Every execution unit, bound range, and continuation round runs through the
production step executor over a span its owner lends, and each unit is reported
before any step of a later unit is taken, a deferred unit binding at its own
turn and a continuation round released before the next is pulled.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Final

import pytest

from parallax.core._execution._transaction._attempt import TxnAttempt
from parallax.core._execution._unit_work.uow import BindDeferredRange, DeferredWriteContinuation
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, entity_by_name
from parallax.core.unit_work import MissingTargetError
from parallax.core.write_plan import WritePlan
from parallax.core.write_plan.plan import (
    BoundRange,
    DeferredRange,
    ExecutionUnit,
    PlannedWrites,
    UnitEffects,
)
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedDelete,
    PlannedWrite,
)
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit.core._execution._execution_support import ACCOUNT, itself, scope
from tests.unit.core._execution._write_step_support import (
    POSITIONS,
    HeldSteps,
    close,
    opening,
    physical,
)

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
    attempt: TxnAttempt,
    plan: WritePlan,
    completed: _Reported,
    bind_deferred: BindDeferredRange = _unbound,
) -> None:
    attempt._execute_flush(  # pyright: ignore[reportPrivateUsage] - drives the executor over a hand-built plan
        plan, trigger="pre_commit", bind_deferred=bind_deferred, completed=completed
    )


def _run(port: ScriptedAdapter, body: Callable[[TxnAttempt], None]) -> None:
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

    def body(attempt: TxnAttempt) -> None:
        with pytest.raises(MissingTargetError):
            _flush(attempt, plan, reported, lambda _description: rounds)

    _run(port, body)
    assert rounds.pulled == [0]
    assert (rounds.finished, rounds.closed) == (0, 1)
    assert reported.units == []


def _run_positions(port: ScriptedAdapter, body: Callable[[TxnAttempt], None]) -> None:
    scope(port, POSITIONS).transact(body, itself, concurrency="locking")


def test_a_grouped_unit_reports_once_after_its_statement_and_a_failed_one_reports_none() -> None:
    first = (close(1), opening(1), opening(2), opening(3))
    second = (opening(5),)
    plan = WritePlan(
        steps=PlannedWrites((HeldSteps(ScriptedAdapter(), (*first, *second)),)),
        units=(ExecutionUnit(end=4), ExecutionUnit(end=5)),
    )

    port = ScriptedAdapter(Transact(Write(), Write(affected=3), Write()))
    reported = _Reported(port, ())
    _run_positions(port, lambda attempt: _flush(attempt, plan, reported))
    assert port.calls == [BeginCall(), *physical(*first), *physical(*second), CommitCall()]
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
    segment = HeldSteps(failing, (*first, *second))
    failed_plan = WritePlan(steps=PlannedWrites((segment,)), units=plan.units)
    unreported = _Reported(failing, ())

    def body(attempt: TxnAttempt) -> None:
        with pytest.raises(DatabaseError) as raised:
            _flush(attempt, failed_plan, unreported)
        assert raised.value is violation

    _run_positions(failing, body)
    assert unreported.units == []
    assert segment.taken == [0, 1, 2, 3]
