"""The one walk of a finalized Write Plan (`m-unit-work` *Write Groups
complete before later work runs*), through simulated step execution.

Each Write Group's own steps execute, and every settled write of the group
completes before any step of a later group executes, a write with no step
included; a deferred range binds at its write's turn on what earlier writes
published, reusing the starting rows it retained that are still current; and a
group whose steps answer another number of allocated keys than the rows its
writes open completes nothing. Against simulated stored rows, each execution
changes them, so a later write reads what earlier ones left, while what the
attempt owns changes only as each write completes.
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
from parallax.core._execution._unit_work.write_runner import (
    ExecuteCountedStep,
    ExecuteWriteSteps,
    _CurrentRowCapture,  # pyright: ignore[reportPrivateUsage] - the capture a running group builds
    run_write_plan,
)
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
    CurrentRowOutput,
    DeferredRange,
    SettledWrite,
    TemporalRowCoordinates,
    TemporalWriteOwnership,
    WriteGroup,
    WritePlan,
)
from parallax.core.write_plan.steps import PlannedStep
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import (
    NO_COUNTED_STEPS,
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
from tests.unit.core._execution._write_step_support import (
    POSITION,
    POSITION_META,
    close,
    insert,
    revision,
)

_FIXED: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _uow(
    meta: Metamodel,
    steps: ExecuteWriteSteps,
    *,
    rows: AcquireRows = NO_ROW_READS,
    concurrency: Concurrency = "optimistic",
    counted: ExecuteCountedStep = NO_COUNTED_STEPS,
) -> UnitOfWork:
    return UnitOfWork(
        settings=TransactionSettings(concurrency=concurrency),
        lifetime=TxnAttemptLifetime(),
        clock=FixedClock(_FIXED),
        meta=meta,
        execute_write_steps=steps,
        execute_counted_step=counted,
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
# Each Write Group's settled writes complete before a later group executes.   #
# --------------------------------------------------------------------------- #
@dataclass
class _Executions:
    """Each execution's steps beside the settled writes completed before it,
    counted by the changes they recorded in ``uow``."""

    steps: ObservedSteps
    uow: UnitOfWork | None = None
    seen: list[tuple[tuple[PlannedStep, ...], int]] = field(
        default_factory=list[tuple[tuple[PlannedStep, ...], int]]
    )

    def __post_init__(self) -> None:
        self.steps.observe = self._observe

    def _observe(self, position: int, steps: tuple[PlannedStep, ...]) -> None:
        del position
        uow = self.uow
        assert uow is not None
        self.seen.append((steps, uow.freshness))

    def run(self, plan: WritePlan) -> None:
        self.uow = _uow(POSITION_META, self.steps)
        run_write_plan(self.uow, plan, self.steps)


def _group(*writes: SettledWrite, steps: tuple[PlannedStep, ...] = ()) -> WriteGroup:
    return WriteGroup(writes, steps)


def _changing(key: int) -> SettledWrite:
    """A settled write whose completion records one change."""
    return SettledWrite(changed=(corpus_object_key("Position", ("id", key)),))


def test_each_group_executes_its_own_steps_once_every_earlier_group_completed() -> None:
    plan = WritePlan(
        (
            _group(_changing(1), steps=(close(1), close(2))),
            _group(_changing(2)),
            _group(_changing(3), steps=(close(3),)),
        )
    )
    simulated = _simulated(POSITION_META)
    executions = _Executions(ObservedSteps(simulated))
    executions.run(plan)
    # Each execution is handed its group's own tuple, a group with no step
    # included, and a settled write with no step completes once it ran.
    assert [steps for steps, _completed in executions.seen] == [
        group.steps for group in plan.groups
    ]
    assert all(
        steps is group.steps
        for (steps, _completed), group in zip(executions.seen, plan.groups, strict=True)
    )
    assert [completed for _steps, completed in executions.seen] == [0, 1, 2]
    assert executions.uow is not None and executions.uow.freshness == 3
    assert statement_kinds(simulated.statements) == ["close", "close", "close"]


def test_every_settled_write_of_a_group_completes_once_its_steps_succeeded() -> None:
    plan = WritePlan(
        (
            _group(_changing(1), _changing(2), steps=(close(1), close(2))),
            _group(_changing(3), steps=(close(3),)),
        )
    )
    executions = _Executions(ObservedSteps(_simulated(POSITION_META)))
    executions.run(plan)
    assert [completed for _steps, completed in executions.seen] == [0, 2]


def test_a_group_whose_steps_fail_completes_nothing_and_no_later_group_executes() -> None:
    failure = ValueError("the group's steps fail")
    plan = WritePlan(
        (
            _group(_changing(1), steps=(close(1),)),
            _group(_changing(2), _changing(3), steps=(close(2), close(3))),
            _group(SettledWrite(), steps=(close(4),)),
        )
    )
    simulated = _simulated(POSITION_META)
    executions = _Executions(ObservedSteps(simulated, failing=1, failure=failure))
    with pytest.raises(ValueError, match="steps fail") as raised:
        executions.run(plan)
    assert raised.value is failure
    # The earlier group stays published; the failed one publishes nothing.
    assert executions.steps.executions == 2
    assert executions.uow is not None and executions.uow.freshness == 1
    assert statement_kinds(simulated.statements) == ["close"]


class _Foreign(DeferredRange):
    __slots__ = ()


def test_a_deferred_description_no_planner_finalized_is_refused_before_anything_is_read() -> None:
    held = HeldRows(POSITION_META)
    simulated = _simulated(POSITION_META)
    plan = WritePlan((_group(SettledWrite(deferred=_Foreign())),))
    with pytest.raises(TypeError, match="did not finalize"):
        run_write_plan(_uow(POSITION_META, simulated, rows=held), plan, simulated)
    assert held.requests == []


# --------------------------------------------------------------------------- #
# A settled write opening rows whose keys the database allocates.             #
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


def test_the_rows_a_settled_write_opens_are_owned_under_the_keys_its_steps_answered() -> None:
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
def test_a_write_answered_another_number_of_keys_than_it_opens_completes_nothing(
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
    (group,) = plan.groups
    (write,) = group.writes
    assert len(write.opened.allocated) == 1
    changing = WritePlan(
        (
            WriteGroup(
                (dataclasses.replace(write, changed=(ObjectKey(Span.identity, (("id", 1),)),)),),
                group.steps,
            ),
        )
    )
    simulated = _simulated(_SPANS, answered)
    uow = _uow(_SPANS, simulated)
    with pytest.raises(UnitOfWorkError, match=rf"opening 1 row\(s\).*{len(answered)} key\(s\)"):
        run_write_plan(uow, changing, simulated)
    assert uow.freshness == 0


def test_a_flush_whose_write_answered_the_wrong_keys_dooms_the_attempt() -> None:
    uow = _uow(_SPANS, _simulated(_SPANS, ()))
    uow.buffer(_span_insert())
    with pytest.raises(UnitOfWorkError, match="key"):
        uow.read(lambda: None)
    with pytest.raises(RollbackOnlyError):
        uow.read(lambda: None)


def test_a_capture_stages_only_the_emitters_its_outputs_describe() -> None:
    described, other = revision(1), revision(2)
    (entry,) = insert(1).entries
    output = CurrentRowOutput(
        coordinates=TemporalRowCoordinates(POSITION, (1,), OPEN_BITEMPORAL_ENDS),
        valid_time_coverage=None,
        row=entry,
        emitter=described,
    )
    capture = _CurrentRowCapture((output,))
    capture.capture_revision(other, None)
    capture.capture_insert(entry, None)
    assert capture.take_rows((output,)) == ()
    capture.capture_revision(described, None)
    assert capture.take_rows((output,)) == ((output, None),)
    assert capture.take_rows((output,)) == ()


# --------------------------------------------------------------------------- #
# A deferred range binds at its settled write's turn.                         #
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


def test_a_deferred_range_binds_only_once_every_earlier_write_completed() -> None:
    simulated = _simulated(TARGET_POSITION)
    reads: list[tuple[type[RowRequest], int, int]] = []
    uow: UnitOfWork | None = None

    def watch(request: RowRequest) -> None:
        assert uow is not None
        reads.append((type(request), uow.freshness, len(simulated.statements)))

    held = HeldRows(TARGET_POSITION, [rectangle(_JAN, INFINITY, "100.00")], overlapping=True)
    uow = _uow(TARGET_POSITION, simulated, rows=_Watched(held, watch))
    uow.buffer(_observed_amend(2, _retained_row(2)))
    uow.buffer_target(_target(_APR, _SEP, "150.00"))
    uow.flush(trigger="pre_commit")
    # The earlier write had executed and completed when the range read its
    # coverage; the range's own steps ran after.
    ((kind, completed, executed),) = reads
    assert (kind, completed) == (CoverageReadRequest, 1)
    assert 0 < executed < len(simulated.statements)


def test_a_deferred_write_executes_its_group_then_the_exact_steps_its_range_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans: list[WritePlan] = []
    ranges: list[BoundRange] = []
    finalize, bind = WritePlanner.finalize, WritePlanner.bind_range

    def planning(planner: WritePlanner, request: WritePlanningRequest) -> WritePlan:
        plans.append(finalize(planner, request))
        return plans[-1]

    def binding(planner: WritePlanner, *arguments: Any, **keywords: Any) -> BoundRange:
        ranges.append(bind(planner, *arguments, **keywords))
        return ranges[-1]

    monkeypatch.setattr(WritePlanner, "finalize", planning)
    monkeypatch.setattr(WritePlanner, "bind_range", binding)
    executed: list[tuple[PlannedStep, ...]] = []
    steps = ObservedSteps(
        _simulated(TARGET_POSITION), observe=lambda _position, held: executed.append(held)
    )
    held = HeldRows(TARGET_POSITION, [rectangle(_JAN, INFINITY, "100.00")], overlapping=True)
    uow = _uow(TARGET_POSITION, steps, rows=held)
    uow.buffer(_observed_amend(2, _retained_row(2)))
    uow.buffer_target(_target(_APR, _SEP, "150.00"))
    uow.flush(trigger="pre_commit")
    ((planned, deferred),) = [plan.groups for plan in plans]
    (settled,) = deferred.writes
    (bound,) = ranges
    assert settled.deferred is not None
    assert deferred.steps == ()
    assert bound.steps
    assert [id(held) for held in executed] == [
        id(planned.steps),
        id(deferred.steps),
        id(bound.steps),
    ]


def test_planning_and_deferred_binding_borrow_the_one_live_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The flush drains its buffer after planning, and the earlier write's
    # completion publishes into the very ownership the range then binds under.
    planned: list[TemporalWriteOwnership] = []
    bound: list[tuple[TemporalWriteOwnership, bool]] = []
    finalize, bind = WritePlanner.finalize, WritePlanner.bind_range

    def planning(planner: WritePlanner, request: WritePlanningRequest) -> WritePlan:
        planned.append(request.ownership)
        return finalize(planner, request)

    def binding(planner: WritePlanner, *args: Any, **kwargs: Any) -> BoundRange:
        ownership = kwargs["ownership"]
        # The earlier write amended object 2 from April on, opening its current tail.
        opened = TemporalRowCoordinates(
            corpus_object_key("Position", ("id", 2)).entity, (2,), OPEN_BITEMPORAL_ENDS
        )
        bound.append((ownership, ownership.owns(opened)))
        return bind(planner, *args, **kwargs)

    monkeypatch.setattr(WritePlanner, "finalize", planning)
    monkeypatch.setattr(WritePlanner, "bind_range", binding)
    simulated = _simulated(TARGET_POSITION)
    held = HeldRows(TARGET_POSITION, [rectangle(_JAN, INFINITY, "100.00")], overlapping=True)
    uow = _uow(TARGET_POSITION, simulated, rows=held)
    uow.buffer(_observed_amend(2, _retained_row(2)))
    uow.buffer_target(_target(_APR, _SEP, "150.00"))
    live = uow._admission.ownership  # pyright: ignore[reportPrivateUsage] - the ownership both stages borrow
    uow.flush(trigger="read_dependency")
    assert planned == [live]
    assert planned[0] is live
    ((ownership, published),) = bound
    assert ownership is live
    assert published


def test_a_retained_row_still_current_at_its_writes_turn_is_completed_without_a_read() -> None:
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
# Simulated rows change as each group executes; ownership as each write       #
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


_PREDICATED: Final = model_of(DomainModel(WherePosition, RunnerTag))
_PREDICATED_ENTITY: Final = entity_by_name(_PREDICATED, "WherePosition")
assert _PREDICATED_ENTITY is not None
_PREDICATED_POSITION: Final = _PREDICATED_ENTITY
_T0: Final = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
_FEB, _AUG = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (2, 8))


def _tag_predicate_write() -> PreparedPredicateWrite:
    prepared = prepare_wire_write(
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
        _PREDICATED,
    )
    assert isinstance(prepared, PreparedPredicateWrite)
    return prepared


def test_a_write_after_a_predicate_write_continues_from_what_the_earlier_write_left() -> None:
    store = SimulatedTemporalStore()
    store.seed_fixtures(
        _PREDICATED,
        _PREDICATED_POSITION,
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
    observation = store.predecessor_for(_PREDICATED, _PREDICATED_POSITION, {"id": 1})
    assert observation is not None
    simulated = SimulatedWriteSteps(
        build_write_planner(_PREDICATED).payloads, _PREDICATED, POSTGRES, store=store
    )
    seen: list[RowRequest] = []

    uow = _uow(
        _PREDICATED,
        simulated,
        rows=_Watched(store.acquisition(_PREDICATED), seen.append),
        counted=simulated.counted,
    )
    amendment = prepare_wire_write(
        KeyedWriteInstruction(
            "amendUntil",
            "WherePosition",
            ({"id": 1, "acctNum": "O"},),
            valid_from=_FEB,
            until=_APR,
        ),
        _PREDICATED,
    )
    assert isinstance(amendment, PreparedKeyedWrite)
    later = prepare_wire_write(
        KeyedWriteInstruction(
            "amendUntil",
            "WherePosition",
            ({"id": 1, "value": "175.00"},),
            valid_from=_JUN,
            until=_AUG,
        ),
        _PREDICATED,
    )
    assert isinstance(later, PreparedKeyedWrite)
    observed = uow.retain(retained_observation(amendment, _PREDICATED, observation))
    with store.transaction(rollback=False):
        uow.buffer(buffered_write(amendment, observed))
        # The predicate write executes the earlier amendment in its own flush.
        uow.execute_predicate(_tag_predicate_write())
        executed = len(simulated.statements)
        # A later write of the same source continues through what the earlier
        # write left of the state they observed.
        uow.buffer(buffered_write(later, observed))
        uow.flush(trigger="pre_commit")
    hundred, changed = Decimal("100.00"), Decimal("175.00")
    # The later write reads nothing: the attempt holds the row the earlier
    # write opened, and revises it rather than closing it.
    assert seen == []
    assert "close" not in statement_kinds(simulated.statements[executed:])
    assert _stored(store, _PREDICATED, _PREDICATED_POSITION, 1) == [
        (_JAN, _FEB, _FIXED, "A", hundred),
        (_FEB, _APR, _FIXED, "O", hundred),
        (_APR, _JUN, _FIXED, "A", hundred),
        (_JUN, _AUG, _FIXED, "A", changed),
        (_AUG, INFINITY, _FIXED, "A", hundred),
    ]
