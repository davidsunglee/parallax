"""Planned Steps of the corpus Position model, a payload preparer recording
when each is prepared, the production step executor over a scripted port, the
Flush it executes inside, and a Write Plan's groups run through it."""

from __future__ import annotations

import datetime as dt
from collections.abc import Generator
from contextlib import contextmanager
from decimal import Decimal
from typing import Final

from parallax.conformance.class_models import MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import opt_lock
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work.write_runner import run_write_plan
from parallax.core._execution._write_lowering import lowered, stream_physical
from parallax.core._execution._write_step_executor import WriteStepExecutor
from parallax.core.base import INFINITY as OPEN
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
from parallax.core.execution_lifecycle._activity import (
    FlushActivity,
    installed_lifecycle,
    open_transaction_root,
)
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel, entity_by_name
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import TransactionSettings, UnitOfWork
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan import SUPERSEDED, WritePlan
from parallax.core.write_plan.payload import AssignmentPayload, RowPayload, WritePayloadPreparer
from parallax.core.write_plan.steps import (
    INFINITY,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    UNGATED,
    ExactCount,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedInsert,
    PlannedRow,
    PlannedStep,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    TemporalGate,
    WriteRow,
)
from tests._support.db_port import OrderedCall, ScriptedAdapter, WriteCall
from tests._support.planner_probes import NO_ROW_READS, TEST_ACTOR_IDENTITY

POSITIONS: Final = MODELS["position"]
POSITION_META: Final = model_of(POSITIONS)
_ENTITY = entity_by_name(POSITION_META, "Position")
assert _ENTITY is not None
POSITION: Final = _ENTITY.identity
T0: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
T1: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def position_attribute(name: str) -> AttributeIdentity:
    return AttributeIdentity(POSITION, name)


def slot(key: int) -> MilestoneTarget:
    """Position ``key``'s current row."""
    return MilestoneTarget(
        key_attributes=(position_attribute("id"),),
        key_values=(key,),
        end_attributes=(position_attribute("validEnd"), position_attribute("txEnd")),
        end_values=(INFINITY, INFINITY),
    )


_GATE: Final = TemporalGate(start_attribute=position_attribute("txStart"), observed_start=T0)


def close(key: int) -> PlannedClose:
    return PlannedClose(
        entity=POSITION,
        target=slot(key),
        assignments=PlannedAssignments(attributes={position_attribute("txEnd"): T1}),
        cause=SUPERSEDED,
        concurrency=UNGATED,
        affected_rows=ExactCount(1, STALE_WRITE),
    )


def guard(key: int) -> PlannedTemporalGuard:
    return PlannedTemporalGuard(
        entity=POSITION,
        target=slot(key),
        concurrency=_GATE,
        affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
    )


def removal(key: int) -> PlannedTemporalRemoval:
    return PlannedTemporalRemoval(
        entity=POSITION,
        target=slot(key),
        concurrency=UNGATED,
        affected_rows=ExactCount(1, STALE_WRITE),
    )


def revision(key: int) -> PlannedTemporalRevision:
    return PlannedTemporalRevision(
        entity=POSITION,
        target=slot(key),
        assignments=PlannedAssignments(attributes={position_attribute("value"): Decimal("2.50")}),
        concurrency=_GATE,
        affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
    )


def insert(key: int) -> PlannedInsert:
    """Position ``key``'s opening over every Valid Time."""
    return _opened(key, T0, OPEN, Decimal("1.00"))


def opening(month: int, value: object = Decimal("1.00")) -> PlannedInsert:
    """Position 1's opening over ``month``, at ``value``."""
    return _opened(
        1,
        dt.datetime(2024, month, 1, tzinfo=dt.UTC),
        dt.datetime(2024, month + 1, 1, tzinfo=dt.UTC),
        value,
    )


def _opened(key: int, start: dt.datetime, end: object, value: object) -> PlannedInsert:
    row = PlannedRow(
        attributes={
            position_attribute("id"): key,
            position_attribute("acctNum"): "A-1",
            position_attribute("value"): value,
            position_attribute("validStart"): start,
            position_attribute("validEnd"): end,
            position_attribute("txStart"): T1,
            position_attribute("txEnd"): OPEN,
        }
    )
    return PlannedInsert(entity=POSITION, entries=(WriteRow(row=row, origin=NEW_LINEAGE),))


class RecordingPreparer(LayoutPayloadPreparer):
    """``meta``'s own payload preparer for ``steps``, recording the position of
    each step it prepares a payload for with how many ``port`` calls had been
    made by then, and raising ``failure`` instead of preparing the step at
    ``failing``."""

    __slots__ = ("_positions", "failing", "failure", "port", "prepared")

    def __init__(
        self,
        port: ScriptedAdapter,
        steps: tuple[PlannedStep, ...],
        meta: Metamodel = POSITION_META,
        *,
        failing: int | None = None,
        failure: BaseException | None = None,
    ) -> None:
        super().__init__(meta)
        self.port = port
        self.failing = failing
        self.failure = failure
        self.prepared: list[tuple[int, int]] = []
        self._positions = {
            id(source): index for index, step in enumerate(steps) for source in _sources(step)
        }

    @property
    def positions(self) -> list[int]:
        return [index for index, _calls in self.prepared]

    def row(self, entity: EntityIdentity, write_row: WriteRow) -> RowPayload:
        self._prepare(write_row)
        return super().row(entity, write_row)

    def assignments(
        self, entity: EntityIdentity, assignments: PlannedAssignments
    ) -> AssignmentPayload:
        self._prepare(assignments)
        return super().assignments(entity, assignments)

    def _prepare(self, source: object) -> None:
        index = self._positions[id(source)]
        self.prepared.append((index, len(self.port.calls)))
        if index == self.failing and self.failure is not None:
            raise self.failure


def _sources(step: PlannedStep) -> tuple[object, ...]:
    """What a payload is prepared from for ``step``: each entry an insert
    holds, or the assignments an update, close, or revision carries."""
    match step:
        case PlannedInsert(entries=entries):
            return entries
        case PlannedUpdate() | PlannedClose() | PlannedTemporalRevision():
            return (step.assignments,)
        case _:
            return ()


def step_executor(
    port: ScriptedAdapter,
    meta: Metamodel = POSITION_META,
    payloads: WritePayloadPreparer | None = None,
) -> WriteStepExecutor:
    """The production executor of an attempt over ``port``, preparing payloads
    through ``payloads`` or else the planner an attempt adopts."""
    return WriteStepExecutor(
        port,
        payloads=build_write_planner(meta).payloads if payloads is None else payloads,
        meta=meta,
    )


@contextmanager
def open_flush(
    provider: ExecutionLifecycleProvider | None = None,
) -> Generator[FlushActivity]:
    """A pre-commit Flush of one attempt, observed by ``provider`` where
    one is given and inert otherwise."""
    with (
        open_transaction_root(
            installed_lifecycle(provider),
            access_mode="read_write",
            concurrency="locking",
            retries=0,
            isolation=None,
        ) as invocation,
        invocation.attempt("test") as attempt,
    ):
        with attempt.flush("pre_commit") as flush:
            yield flush
        attempt.committed()


def run_plan(
    port: ScriptedAdapter,
    plan: WritePlan,
    flush: FlushActivity,
    meta: Metamodel = POSITION_META,
    payloads: WritePayloadPreparer | None = None,
) -> None:
    """``plan`` run group by group by a fresh unit of work, each group's steps
    executed by the production executor of an attempt over ``port`` as calls
    of ``flush``, preparing payloads through ``payloads`` where given."""
    executor = step_executor(port, meta, payloads)

    def execute(steps: tuple[PlannedStep, ...], /, *, allocates: bool) -> tuple[object, ...]:
        return executor.execute(steps, allocates=allocates, flush=flush)

    planner = build_write_planner(meta)
    uow = UnitOfWork(
        settings=TransactionSettings(),
        lifetime=TxnAttemptLifetime(),
        clock=FixedClock(T1),
        meta=meta,
        execute_write_steps=execute,
        acquire_rows=NO_ROW_READS,
        planner=planner,
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(meta).required_key,
    )
    run_write_plan(uow, plan, execute)


def statement(step: PlannedStep) -> LoweredStatement:
    return lowered(step, build_write_planner(POSITION_META).payloads, POSITION_META, POSTGRES)


def alone(step: PlannedStep) -> WriteCall:
    """The write the port receives for ``step`` run as a call of its own."""
    lowered_step = statement(step)
    return WriteCall(POSTGRES.to_driver_sql(lowered_step.sql), lowered_step.binds)


def ordered(*steps: PlannedStep) -> OrderedCall:
    """The invocation an adapter records for ``steps``: each statement in the
    driver form converted once from its canonical SQL."""
    return OrderedCall(tuple(alone(step) for step in steps))


def physical(*steps: PlannedStep) -> list[WriteCall]:
    """The writes a dry traversal of ``steps`` answers, as the port receives them."""
    return [
        WriteCall(POSTGRES.to_driver_sql(lowered_step.sql), lowered_step.binds)
        for lowered_step in stream_physical(
            steps, build_write_planner(POSITION_META).payloads, POSITION_META, POSTGRES
        )
    ]
