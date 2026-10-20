"""The one walk of a finalized Write Plan (`m-unit-work` *Execution units
complete before later work runs*), through simulated step execution.

Each unit's span executes and the unit completes before any step of a later
unit is taken, a unit with no step included; a deferred range binds at its
unit's turn on what earlier units published, reusing the starting rows it
retained that are still current; and a unit whose span answers another number
of allocated keys than the rows it opens completes nothing. Against simulated
stored rows, each span changes them as it executes, so a later unit reads what
earlier ones left, while what the attempt owns changes only as each unit
completes.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final, cast

import pytest

from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.simulated_temporal_store import SimulatedTemporalStore
from parallax.core import MAX, Attr, Bitemporal, DomainModel, Entity, attr, opt_lock, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    CompletionRequest,
    CoverageReadRequest,
    CoverageTerm,
    RowConsumer,
    RowRequest,
    TargetReadRequest,
    consume_coverage,
)
from parallax.core._execution._unit_work.instructions import (
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTargetWrite,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.write_runner import ExecuteWriteSteps, run_write_plan
from parallax.core.base import INFINITY
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, EntityMetadata, Metamodel, entity_by_name
from parallax.core.unit_work import (
    AdmittedWrite,
    Concurrency,
    KeyedWriteInstruction,
    PredicateSelection,
    PredicateWriteInstruction,
    RetainedObservation,
    RollbackOnlyError,
    TargetWriteInstruction,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WriteAssignment,
    WritePlanner,
    WritePlanningRequest,
    buffered_write,
)
from parallax.core.write_plan import (
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
    object_state_key_from_observation,
)
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    DeferredRange,
    OwnedEndpoint,
    PlannedWrites,
    SettledWrite,
    TemporalWriteOwnership,
    WritePlan,
)
from parallax.core.write_plan.steps import PlannedStep
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import (
    NO_ROW_READS,
    TEST_ACTOR_IDENTITY,
    retained_observation,
)
from tests.unit._corpus_identity_support import corpus_object_key
from tests.unit._where_position_model import WherePosition
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

    def step(self, index: int) -> PlannedStep:
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
            SettledWrite(end=2, claim=claims[0]),
            SettledWrite(end=2, claim=claims[1]),
            SettledWrite(end=3, claim=claims[2]),
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
        units=(SettledWrite(end=2, claim=claims[0]), SettledWrite(end=3, claim=claims[1])),
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
            SettledWrite(end=1, claim=claims[0]),
            SettledWrite(end=3, claim=claims[1]),
            SettledWrite(end=4, claim=claims[2]),
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
    plan = WritePlan(units=(SettledWrite(end=0, deferred=_Foreign()),))
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
        KeyedWriteInstruction(
            "insert",
            Span.identity.canonical,
            ({"id": {"computed": "maxPlusOne"}, "amount": 1},),
            valid_from=_MAR,
        ),
        _SPANS,
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared


def _span_amend(key: int) -> AdmittedWrite:
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
        KeyedWriteInstruction("amend", Span.identity.canonical, ({"id": key, "amount": 2},), _MAR),
        _SPANS,
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

    held: AcquireRows
    watch: Callable[[RowRequest], object]

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        self.watch(request)
        return self.held(request, consumer)


def _target(valid_from: dt.datetime, until: dt.datetime, value: str) -> PreparedTargetWrite:
    prepared = prepare_wire_write(
        TargetWriteInstruction(
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


def _observed_amend(key: int, claim: RetainedObservation) -> AdmittedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction("amend", "Position", ({"id": key, "value": "150.00"},), _APR),
        TARGET_POSITION,
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


def test_planning_and_deferred_binding_borrow_the_one_live_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The flush drains its batch after planning, and the earlier unit's
    # completion publishes into the very ownership the range then binds under.
    planned: list[TemporalWriteOwnership] = []
    bound: list[tuple[TemporalWriteOwnership, bool]] = []
    finalize, bind = WritePlanner.finalize, WritePlanner.bind_deferred

    def planning(planner: WritePlanner, request: WritePlanningRequest) -> WritePlan:
        planned.append(request.ownership)
        return finalize(planner, request)

    def binding(planner: WritePlanner, *args: Any, **kwargs: Any) -> BoundRange:
        ownership = kwargs["ownership"]
        # The earlier unit amended object 2 from April on, opening its current tail.
        opened = OwnedEndpoint(
            corpus_object_key("Position", ("id", 2)).entity, (2,), OPEN_BITEMPORAL_ENDS
        )
        bound.append((ownership, ownership.owns(opened)))
        return bind(planner, *args, **kwargs)

    monkeypatch.setattr(WritePlanner, "finalize", planning)
    monkeypatch.setattr(WritePlanner, "bind_deferred", binding)
    simulated = _simulated(TARGET_POSITION)
    held = HeldRows(TARGET_POSITION, [rectangle(_JAN, INFINITY, "100.00")], overlapping=True)
    uow = _uow(TARGET_POSITION, simulated, rows=held)
    uow.buffer(_observed_amend(2, _retained_row(2)))
    uow.buffer_target(_target(_APR, _SEP, "150.00"))
    live = uow._admission.ownership  # pyright: ignore[reportPrivateUsage] - the ownership both stages borrow
    uow.flush(trigger="pre_commit")
    assert planned == [live]
    assert planned[0] is live
    ((ownership, published),) = bound
    assert ownership is live
    assert published


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
# Simulated rows change as each span executes; ownership as each unit         #
# completes.                                                                   #
# --------------------------------------------------------------------------- #
def _stored(
    store: SimulatedTemporalStore, meta: Metamodel, entity: EntityMetadata, key: int
) -> list[tuple[object, ...]]:
    """Every row ``store`` holds current for ``entity`` ``key``, as
    ``(validStart, validEnd, txStart, acctNum, value)``, by Valid-Time start."""
    covered = store.acquisition(meta)(
        CoverageReadRequest(
            entity=entity,
            key_attribute=AttributeIdentity(entity.identity, "id"),
            terms=(CoverageTerm(key, ()),),
            locking=False,
        ),
        consume_coverage,
    )
    if covered is None:
        return []
    members = [
        PredecessorRow.over_row(
            covered.selection, covered.rows[index], covered.document(index), covered.absent
        ).members
        for index in range(len(covered))
    ]
    return sorted(
        (
            (row["validStart"], row["validEnd"], row["txStart"], row["acctNum"], row["value"])
            for row in members
        ),
        key=lambda stored: cast("dt.datetime", stored[0]),
    )


class RunnerTag(Entity, table="runner_tag", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_BARRIERED: Final = model_of(DomainModel(WherePosition, RunnerTag))
_BARRIERED_ENTITY: Final = entity_by_name(_BARRIERED, "WherePosition")
assert _BARRIERED_ENTITY is not None
_BARRIERED_POSITION: Final = _BARRIERED_ENTITY
_T0: Final = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_FEB, _AUG = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (2, 8))


def _barrier() -> PreparedPredicateWrite:
    barrier = prepare_wire_write(
        PredicateWriteInstruction(
            "amend",
            PredicateSelection(
                "RunnerTag",
                predicate_algebra.Comparison(
                    "eq", predicate_algebra.FieldSubject("RunnerTag.id"), 1
                ),
            ),
            assignments=(WriteAssignment("RunnerTag.label", "q"),),
        ),
        _BARRIERED,
    )
    assert isinstance(barrier, PreparedPredicateWrite)
    return barrier


def test_a_unit_kept_behind_a_barrier_binds_on_the_rows_and_ownership_earlier_units_left() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(
        _BARRIERED,
        _BARRIERED_POSITION,
        [
            {
                "id": 1,
                "acctNum": "A",
                "value": Decimal("100.00"),
                "validStart": _JAN,
                "validEnd": INFINITY,
                "txStart": _T0,
                "txEnd": INFINITY,
            }
        ],
    )
    observation = store.predecessor_for(_BARRIERED, _BARRIERED_POSITION, {"id": 1})
    assert observation is not None
    simulated = SimulatedWriteSteps(
        build_write_planner(_BARRIERED).payloads, _BARRIERED, POSTGRES, store=store
    )
    seen: list[tuple[int, list[tuple[object, ...]]]] = []

    def watch(request: RowRequest) -> None:
        seen.append((len(simulated.statements), _stored(store, _BARRIERED, _BARRIERED_POSITION, 1)))

    uow = _uow(
        _BARRIERED,
        simulated,
        rows=_Watched(store.acquisition(_BARRIERED), watch),
    )
    amendment = prepare_wire_write(
        KeyedWriteInstruction(
            "amendUntil",
            "WherePosition",
            ({"id": 1, "acctNum": "O"},),
            valid_from=_FEB,
            until=_APR,
        ),
        _BARRIERED,
    )
    assert isinstance(amendment, PreparedKeyedWrite)
    target = prepare_wire_write(
        TargetWriteInstruction(
            "amendUntil",
            "WherePosition",
            {"id": 1, "value": "175.00"},
            if_tx_start=_T0,
            valid_from=_JUN,
            until=_AUG,
        ),
        _BARRIERED,
    )
    assert isinstance(target, PreparedTargetWrite)
    with store.transaction(rollback=False):
        uow.buffer(
            buffered_write(amendment, retained_observation(amendment, _BARRIERED, observation))
        )
        uow.buffer_predicate(_barrier())
        uow.buffer_target(target)
        uow.flush(trigger="pre_commit")
    hundred, changed = Decimal("100.00"), Decimal("175.00")
    # The kept-back unit read its coverage once the earlier unit had executed,
    # and found the row that unit opened.
    ((executed, stored),) = seen
    assert executed > 0
    assert (_APR, INFINITY, _FIXED, "A", hundred) in stored
    # That row is the attempt's own, so it is revised rather than closed.
    assert "close" not in statement_kinds(simulated.statements[executed:])
    assert _stored(store, _BARRIERED, _BARRIERED_POSITION, 1) == [
        (_JAN, _FEB, _FIXED, "A", hundred),
        (_FEB, _APR, _FIXED, "O", hundred),
        (_APR, _JUN, _FIXED, "A", hundred),
        (_JUN, _AUG, _FIXED, "A", changed),
        (_AUG, INFINITY, _FIXED, "A", hundred),
    ]
