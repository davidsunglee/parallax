"""The one walk of a finalized Write Plan (`m-unit-work` *Execution units
complete before later work runs*), through simulated step execution.

Each unit's span executes and the unit completes before any step of a later
unit is taken, a unit with no step included; a deferred range binds at its
unit's turn on what earlier units published, reusing the starting rows it
retained that are still current; a deferred group executes round by round,
each round released before the next is prepared, and publishes once, after its
last round, closing its preparation however it ends; and a unit whose span
answers another number of allocated keys than the rows it opens completes
nothing.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import MAX, Attr, Bitemporal, DomainModel, attr, opt_lock, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work import ranges as ranges_module
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    CompletionRequest,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
    TargetReadRequest,
)
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedTargetWrite,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.ranges import GroupContinuation
from parallax.core._execution._unit_work.write_runner import ExecuteWriteSteps, run_write_plan
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    BufferItem,
    Concurrency,
    KeyedWrite,
    MaterializedWriteGroup,
    PredicateSelection,
    PredicateWrite,
    RetainedObservation,
    RollbackOnlyError,
    TargetWrite,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WriteAssignment,
    WritePlanningRequest,
    buffered_write,
)
from parallax.core.write_plan import (
    ObjectKey,
    ObjectStateKey,
    PredecessorRow,
    TemporalObservation,
    object_state_key_from_observation,
)
from parallax.core.write_plan.plan import DeferredRange, ExecutionUnit, PlannedWrites, WritePlan
from parallax.core.write_plan.steps import PlannedWrite
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import NO_ROW_READS, TEST_ACTOR_IDENTITY
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._temporal_group_support import temporal_group
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows
from tests.unit.core._execution._unit_work._flush_support import ObservedSteps, statement_kinds
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    POSITION as TARGET_POSITION,
)
from tests.unit.core._execution._unit_work._temporal_targets_support import (
    T0,
    rectangle,
)
from tests.unit.core._execution._write_step_support import POSITION_META, close

_FIXED: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _uow(
    meta: Metamodel,
    steps: ExecuteWriteSteps,
    *,
    rows: AcquireRows = NO_ROW_READS,
    concurrency: Concurrency = "optimistic",
) -> UnitOfWork:
    return UnitOfWork(
        settings=TransactionSettings(concurrency=concurrency),
        lifetime=TxnAttemptLifetime(),
        clock=FixedClock(_FIXED),
        meta=meta,
        execute_write_steps=steps,
        acquire_rows=rows,
        planner=build_write_planner(meta),
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(meta).required_key,
    )


def _simulated(meta: Metamodel, *allocated: tuple[object, ...]) -> SimulatedWriteSteps:
    return SimulatedWriteSteps(
        build_write_planner(meta).payloads, meta, POSTGRES, allocated_results=allocated
    )


# --------------------------------------------------------------------------- #
# Each unit completes before any step of a later unit is taken.               #
# --------------------------------------------------------------------------- #
@dataclass
class _Claim:
    """Source authority recording whether a unit spent it."""

    consumed: bool = False

    def consume(self) -> None:
        self.consumed = True


@dataclass
class _Taken:
    """Position closes built only when asked, recording which of ``claims``
    were spent as each step is taken, and raising ``failure`` instead of
    building the step at ``failing``."""

    keys: tuple[int, ...]
    claims: tuple[_Claim, ...]
    failing: int | None = None
    failure: Exception | None = None
    taken: list[tuple[int, tuple[bool, ...]]] = field(
        default_factory=list[tuple[int, tuple[bool, ...]]]
    )

    def __len__(self) -> int:
        return len(self.keys)

    def step(self, index: int) -> PlannedWrite:
        self.taken.append((index, tuple(claim.consumed for claim in self.claims)))
        if index == self.failing and self.failure is not None:
            raise self.failure
        return close(self.keys[index])


def test_each_unit_completes_before_any_step_of_the_next_is_taken() -> None:
    claims = (_Claim(), _Claim(), _Claim())
    segment = _Taken((1, 2, 3), claims)
    plan = WritePlan(
        steps=PlannedWrites((segment,)),
        units=(
            ExecutionUnit(end=2, claim=claims[0]),
            ExecutionUnit(end=2, claim=claims[1]),
            ExecutionUnit(end=3, claim=claims[2]),
        ),
    )
    simulated = _simulated(POSITION_META)
    run_write_plan(_uow(POSITION_META, simulated), plan, simulated)
    # The unit with no step completes where the first ends, before the step
    # after it is even taken; every step is taken exactly once.
    assert segment.taken == [
        (0, (False, False, False)),
        (1, (False, False, False)),
        (2, (True, True, False)),
    ]
    assert all(claim.consumed for claim in claims)
    assert statement_kinds(simulated.statements) == ["close", "close", "close"]


def test_a_unit_whose_span_fails_completes_nothing_and_no_later_step_is_taken() -> None:
    claims = (_Claim(), _Claim())
    failure = ValueError("the second step cannot be built")
    segment = _Taken((1, 2, 3), claims, failing=1, failure=failure)
    plan = WritePlan(
        steps=PlannedWrites((segment,)),
        units=(ExecutionUnit(end=2, claim=claims[0]), ExecutionUnit(end=3, claim=claims[1])),
    )
    simulated = _simulated(POSITION_META)
    with pytest.raises(ValueError, match="cannot be built") as raised:
        run_write_plan(_uow(POSITION_META, simulated), plan, simulated)
    assert raised.value is failure
    assert [index for index, _spent in segment.taken] == [0, 1]
    assert not any(claim.consumed for claim in claims)
    assert simulated.statements == ()


def test_each_unit_spans_one_execution_of_its_own_steps() -> None:
    claims = (_Claim(), _Claim(), _Claim())
    plan = WritePlan(
        steps=PlannedWrites((_Taken((1, 2, 3, 4), claims),)),
        units=(
            ExecutionUnit(end=1, claim=claims[0]),
            ExecutionUnit(end=3, claim=claims[1]),
            ExecutionUnit(end=4, claim=claims[2]),
        ),
    )
    spans: list[tuple[int, tuple[bool, ...]]] = []
    simulated = _simulated(POSITION_META)

    def observe(position: int) -> None:
        spans.append((len(simulated.statements), tuple(claim.consumed for claim in claims)))

    steps = ObservedSteps(simulated, observe=observe)
    run_write_plan(_uow(POSITION_META, steps), plan, steps)
    # A run of a unit's steps never reaches into the next unit's.
    assert spans == [
        (0, (False, False, False)),
        (1, (True, False, False)),
        (3, (True, True, False)),
    ]


class _Foreign(DeferredRange):
    __slots__ = ()


def test_a_deferred_description_no_planner_finalized_is_refused_before_anything_is_read() -> None:
    held = HeldRows(POSITION_META)
    simulated = _simulated(POSITION_META)
    plan = WritePlan(units=(ExecutionUnit(end=0, deferred=_Foreign()),))
    with pytest.raises(TypeError, match="did not finalize"):
        run_write_plan(_uow(POSITION_META, simulated, rows=held), plan, simulated)
    assert held.requests == []


# --------------------------------------------------------------------------- #
# A unit opening rows whose keys the database allocates.                      #
# --------------------------------------------------------------------------- #
class Span(Bitemporal, table="span", namespace="parallax.runner.allocated"):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


_SPANS: Final = model_of(DomainModel(Span))
_MAR: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


def _span_insert() -> PreparedKeyedWrite:
    prepared = prepare_typed_write(
        KeyedWrite(
            "insert",
            Span.identity.canonical,
            ({"id": {"computed": "maxPlusOne"}, "amount": 1},),
            valid_from=_MAR,
        ),
        _SPANS,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _span_amend(key: int) -> BufferItem:
    members = {
        "id": key,
        "amount": 1,
        "validStart": _MAR,
        "validEnd": INFINITY,
        "txStart": _FIXED,
        "txEnd": INFINITY,
    }
    observation = TemporalObservation(predecessor=PredecessorRow(members))
    shape = temporal_read.view(_SPANS).shape(Span.identity)
    assert shape is not None
    state = object_state_key_from_observation(
        ObjectKey(Span.identity, (("id", key),)), observation, shape
    )
    prepared = prepare_typed_write(
        KeyedWrite("amend", Span.identity.canonical, ({"id": key, "amount": 2},), _MAR), _SPANS
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return buffered_write(prepared, RetainedObservation(state, observation, None))


def test_the_rows_a_unit_opens_are_owned_under_the_keys_its_span_answered() -> None:
    simulated = _simulated(_SPANS, (42,))
    uow = _uow(_SPANS, simulated)
    uow.buffer(_span_insert())
    uow.read(lambda: None)
    uow.buffer(_span_amend(42))
    uow.flush(trigger="pre_commit")
    # The row opened under key 42 is the attempt's own, so it is revised in
    # place rather than closed and succeeded.
    assert statement_kinds(simulated.statements) == ["insert", "update"]


@pytest.mark.parametrize("answered", [(), (41, 42)], ids=["none", "too-many"])
def test_a_unit_answered_another_number_of_keys_than_it_opens_completes_nothing(
    answered: tuple[object, ...],
) -> None:
    plan = build_write_planner(_SPANS).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at("2024-01-10T00:00:00+00:00"),
            concurrency="optimistic",
            buffered_writes=[_span_insert()],
        )
    )
    (unit,) = plan.units
    assert len(unit.opened.allocated) == 1
    claim = _Claim()
    claimed = WritePlan(steps=plan.steps, units=(dataclasses.replace(unit, claim=claim),))
    simulated = _simulated(_SPANS, answered)
    with pytest.raises(UnitOfWorkError, match=rf"opening 1 row\(s\).*{len(answered)} key\(s\)"):
        run_write_plan(_uow(_SPANS, simulated), claimed, simulated)
    assert not claim.consumed


def test_a_flush_whose_unit_answered_the_wrong_keys_dooms_the_attempt() -> None:
    uow = _uow(_SPANS, _simulated(_SPANS, ()))
    uow.buffer(_span_insert())
    with pytest.raises(UnitOfWorkError, match="key"):
        uow.read(lambda: None)
    with pytest.raises(RollbackOnlyError):
        uow.read(lambda: None)


# --------------------------------------------------------------------------- #
# A deferred range binds at its unit's turn.                                   #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class _Watched:
    """``held``'s answers, ``watch`` called with each read as it is asked for."""

    held: HeldRows
    watch: Callable[[RowRequest], object]

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        self.watch(request)
        return self.held(request, consumer)


def _target(valid_from: dt.datetime, until: dt.datetime, value: str) -> PreparedTargetWrite:
    prepared = prepare_wire_write(
        TargetWrite(
            "amendUntil",
            "Position",
            {"id": 1, "value": value},
            if_tx_start=T0,
            valid_from=valid_from,
            until=until,
        ),
        TARGET_POSITION,
    )
    assert isinstance(prepared, PreparedTargetWrite)
    return prepared


_JAN, _APR, _JUN, _SEP = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 4, 6, 9))


def _observed_amend(key: int, claim: RetainedObservation) -> BufferItem:
    prepared = prepare_wire_write(
        KeyedWrite("amend", "Position", ({"id": key, "value": "150.00"},), _APR), TARGET_POSITION
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return buffered_write(prepared, claim)


def _retained_row(key: int) -> RetainedObservation:
    row = {**rectangle(_JAN, INFINITY, "100.00").members, "id": key}
    observation = TemporalObservation(predecessor=PredecessorRow(row))
    shape = temporal_read.view(TARGET_POSITION).shape(
        corpus_object_key("Position", ("id", key)).entity
    )
    assert shape is not None
    state = object_state_key_from_observation(
        corpus_object_key("Position", ("id", key)), observation, shape
    )
    return RetainedObservation(state, observation, None)


def test_a_deferred_range_binds_only_once_every_earlier_unit_completed() -> None:
    claim = _retained_row(2)
    simulated = _simulated(TARGET_POSITION)
    reads: list[tuple[type[RowRequest], bool, int]] = []

    def watch(request: RowRequest) -> None:
        reads.append((type(request), claim.consumed, len(simulated.statements)))

    held = HeldRows(TARGET_POSITION, [rectangle(_JAN, INFINITY, "100.00")], overlapping=True)
    uow = _uow(TARGET_POSITION, simulated, rows=_Watched(held, watch))
    uow.buffer(_observed_amend(2, claim))
    uow.buffer_target(_target(_APR, _SEP, "150.00"))
    uow.flush(trigger="pre_commit")
    # The earlier unit had executed and spent its source when the range read
    # its coverage; the range's own steps ran after.
    ((kind, spent, executed),) = reads
    assert (kind, spent) == (CoverageReadRequest, True)
    assert 0 < executed < len(simulated.statements)


def test_a_retained_row_still_current_at_its_units_turn_is_completed_without_a_read() -> None:
    held = HeldRows(TARGET_POSITION, [rectangle(_JAN, _JUN, "100.00")], overlapping=True)
    simulated = _simulated(TARGET_POSITION)
    uow = _uow(TARGET_POSITION, simulated, rows=held, concurrency="locking")
    uow.buffer_target(_target(_APR, _SEP, "150.00"))
    held.rows = [rectangle(_JAN, _JUN, "100.00"), rectangle(_JUN, INFINITY, "200.00")]
    uow.flush(trigger="pre_commit")
    target, completion, coverage = held.requests
    assert isinstance(target, TargetReadRequest)
    # The retained row is reused as read, and only what it leaves is read.
    assert isinstance(completion, CompletionRequest)
    assert isinstance(coverage, CoverageReadRequest)
    (term,) = coverage.terms
    assert term.valid_time_windows == (temporal_read.TimeInterval(_JUN, _SEP),)
    # Both rows the window reaches close, and the parts they leave open as
    # one insert.
    assert statement_kinds(simulated.statements) == ["close", "close", "insert"]


# --------------------------------------------------------------------------- #
# A deferred group executes round by round and publishes once.                #
# --------------------------------------------------------------------------- #
_GROUPED: Final = corpus_model("position")
_SELECTED_FROM: Final = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
_SELECTED_UNTIL: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _member_row(key: int, value: str = "100.00") -> dict[str, object]:
    return {
        "id": key,
        "acctNum": "A",
        "value": Decimal(value),
        "validStart": _JAN,
        "validEnd": INFINITY,
        "txStart": _JAN,
        "txEnd": INFINITY,
    }


def _state(row: dict[str, object]) -> ObjectStateKey:
    shape = temporal_read.view(_GROUPED).shape(corpus_object_key("Position", ("id", 1)).entity)
    assert shape is not None
    return object_state_key_from_observation(
        corpus_object_key("Position", ("id", row["id"])),
        TemporalObservation(predecessor=PredecessorRow(row)),
        shape,
    )


def _amended(*rows: dict[str, object]) -> MaterializedWriteGroup:
    return temporal_group(
        PredicateWrite(
            "amendUntil",
            PredicateSelection(
                "Position",
                predicate_algebra.Comparison(
                    "eq", predicate_algebra.FieldSubject("Position.value"), "100.00"
                ),
            ),
            (WriteAssignment("Position.value", Decimal("150.00")),),
            _SELECTED_FROM,
            _SELECTED_UNTIL,
        ),
        _GROUPED,
        rows,
    )


class _Tracked(PlannedWrites):
    """A round's Planned Writes, as they were pulled, that a weak reference
    can tell is still alive."""


@dataclass
class _Lifecycle:
    """What the group's continuation saw: at each pull, how many statements
    had run, whether the round before it was still alive, and whether the
    group's selected states had been published as changed; and how often it
    finished and closed."""

    observations: tuple[RetainedObservation, ...]
    statements: Callable[[], int]
    pulls: list[tuple[int, bool, bool]] = field(default_factory=list[tuple[int, bool, bool]])
    previous: weakref.ref[_Tracked] | None = None
    finished: int = 0
    closed: int = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pull, finish, close_ = (
            GroupContinuation.pull,
            GroupContinuation.finish,
            GroupContinuation.close,
        )
        lifecycle = self

        def pulling(continuation: GroupContinuation) -> PlannedWrites | None:
            previous = lifecycle.previous
            lifecycle.pulls.append(
                (
                    lifecycle.statements(),
                    previous is not None and previous() is not None,
                    any(observation.invalidated for observation in lifecycle.observations),
                )
            )
            writes = pull(continuation)
            if writes is None:
                lifecycle.previous = None
                return None
            tracked = _Tracked(writes.segments)
            lifecycle.previous = weakref.ref(tracked)
            return tracked

        def finishing(continuation: GroupContinuation) -> object:
            lifecycle.finished += 1
            return finish(continuation)

        def closing(continuation: GroupContinuation) -> None:
            lifecycle.closed += 1
            close_(continuation)

        monkeypatch.setattr(GroupContinuation, "pull", pulling)
        monkeypatch.setattr(GroupContinuation, "finish", finishing)
        monkeypatch.setattr(GroupContinuation, "close", closing)


def _grouped(
    monkeypatch: pytest.MonkeyPatch,
    steps: Callable[[SimulatedWriteSteps], ExecuteWriteSteps],
    *rows: dict[str, object],
) -> tuple[UnitOfWork, SimulatedWriteSteps, _Lifecycle]:
    """A unit of work holding the amendment of ``rows`` as one deferred group
    settled one object a round, each selected state retained, with what its
    continuation sees recorded."""
    monkeypatch.setattr(ranges_module, "_GROUP_OBJECTS", 1)
    simulated = _simulated(_GROUPED)
    uow = _uow(_GROUPED, steps(simulated), rows=HeldRows(_GROUPED), concurrency="locking")
    observations = tuple(
        uow.retain(
            RetainedObservation(
                _state(row), TemporalObservation(predecessor=PredecessorRow(row)), None
            )
        )
        for row in rows
    )
    uow.buffer(_amended(*rows))
    lifecycle = _Lifecycle(observations, lambda: len(simulated.statements))
    lifecycle.install(monkeypatch)
    return uow, simulated, lifecycle


def test_each_round_executes_and_is_released_before_the_next_is_prepared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow, simulated, lifecycle = _grouped(
        monkeypatch, lambda simulated: simulated, _member_row(1), _member_row(2), _member_row(3)
    )
    uow.flush(trigger="pre_commit")
    # One object a round, two statements each: its close, and one insert
    # opening its head, changed part, and tail. Nothing is published before
    # the last round.
    assert lifecycle.pulls == [
        (0, False, False),
        (2, False, False),
        (4, False, False),
        (6, False, False),
    ]
    assert (lifecycle.finished, lifecycle.closed) == (1, 1)
    assert all(observation.invalidated for observation in lifecycle.observations)
    assert statement_kinds(simulated.statements) == ["close", "insert"] * 3


def test_an_empty_round_is_executed_and_does_not_end_the_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The selected milestone already holds the assigned value under the
    # shared lock: its round executes nothing, and the next answers none.
    spans: list[int] = []
    uow, simulated, lifecycle = _grouped(
        monkeypatch,
        lambda simulated: ObservedSteps(simulated, observe=spans.append),
        _member_row(1, "150.00"),
    )
    uow.flush(trigger="pre_commit")
    assert [statements for statements, _alive, _published in lifecycle.pulls] == [0, 0]
    # The group unit's own empty span, then its one empty round.
    assert spans == [0, 1]
    assert simulated.statements == ()
    assert (lifecycle.finished, lifecycle.closed) == (1, 1)


def test_a_failed_round_closes_the_group_once_and_prepares_and_publishes_nothing_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("the second round failed")
    uow, _simulated_steps, lifecycle = _grouped(
        monkeypatch,
        # The group's own empty span, then its first and second rounds.
        lambda simulated: ObservedSteps(simulated, failing=2, failure=failure),
        _member_row(1),
        _member_row(2),
        _member_row(3),
    )
    with pytest.raises(RuntimeError, match="second round") as raised:
        uow.flush(trigger="pre_commit")
    assert raised.value is failure
    assert len(lifecycle.pulls) == 2
    assert (lifecycle.finished, lifecycle.closed) == (0, 1)
    assert not any(observation.invalidated for observation in lifecycle.observations)
    with pytest.raises(RollbackOnlyError):
        uow.read(lambda: None)


def test_a_close_failing_after_an_earlier_failure_is_noted_on_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("the round failed")
    uow, _simulated_steps, _lifecycle = _grouped(
        monkeypatch,
        lambda simulated: ObservedSteps(simulated, failing=1, failure=failure),
        _member_row(1),
    )

    def failing_close(continuation: GroupContinuation) -> None:
        raise LookupError("closing failed")

    monkeypatch.setattr(GroupContinuation, "close", failing_close)
    with pytest.raises(RuntimeError) as raised:
        uow.flush(trigger="pre_commit")
    assert raised.value is failure
    assert any("closing failed" in note for note in raised.value.__notes__)


def test_a_close_failing_after_every_round_succeeded_refuses_the_units_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow, _simulated_steps, lifecycle = _grouped(
        monkeypatch, lambda simulated: simulated, _member_row(1)
    )
    closing = LookupError("closing failed")

    def failing_close(continuation: GroupContinuation) -> None:
        raise closing

    monkeypatch.setattr(GroupContinuation, "close", failing_close)
    with pytest.raises(LookupError) as raised:
        uow.flush(trigger="pre_commit")
    assert raised.value is closing
    assert not any(observation.invalidated for observation in lifecycle.observations)


def test_a_finish_failing_closes_the_group_and_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uow, _simulated_steps, lifecycle = _grouped(
        monkeypatch, lambda simulated: simulated, _member_row(1)
    )
    finishing = LookupError("finishing failed")

    def failing_finish(continuation: GroupContinuation) -> object:
        raise finishing

    monkeypatch.setattr(GroupContinuation, "finish", failing_finish)
    with pytest.raises(LookupError) as raised:
        uow.flush(trigger="pre_commit")
    assert raised.value is finishing
    assert lifecycle.closed == 1
    assert not any(observation.invalidated for observation in lifecycle.observations)
