"""Planned Steps of the corpus Position model, a span handing them out lazily,
the production step executor over a scripted port, the Flush it executes
inside, and a Write Plan's units run through it."""

from __future__ import annotations

import datetime as dt
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
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
from parallax.core.metamodel import AttributeIdentity, Metamodel, entity_by_name
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import TransactionSettings, UnitOfWork
from parallax.core.write_plan import SUPERSEDED, WritePlan
from parallax.core.write_plan.plan import WriteStepView
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


@dataclass
class HeldSteps:
    """A segment handing out ``steps`` only when asked, recording each position
    asked with how many port calls had been made by then, and raising
    ``failure`` instead of building the step at ``failing``."""

    port: ScriptedAdapter
    steps: tuple[PlannedStep, ...]
    failing: int | None = None
    failure: BaseException | None = None
    asked: list[tuple[int, int]] = field(default_factory=list[tuple[int, int]])

    def __len__(self) -> int:
        return len(self.steps)

    def step(self, index: int) -> PlannedStep:
        self.asked.append((index, len(self.port.calls)))
        if index == self.failing and self.failure is not None:
            raise self.failure
        return self.steps[index]

    @property
    def taken(self) -> list[int]:
        return [index for index, _calls in self.asked]


def step_executor(port: ScriptedAdapter, meta: Metamodel = POSITION_META) -> WriteStepExecutor:
    """The production executor of an attempt over ``port``, preparing payloads
    through the planner an attempt adopts."""
    return WriteStepExecutor(port, payloads=build_write_planner(meta).payloads, meta=meta)


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
) -> None:
    """``plan`` run unit by unit by a fresh unit of work, each span executed by
    the production executor of an attempt over ``port`` as calls of
    ``flush``."""
    executor = step_executor(port, meta)

    def execute(steps: WriteStepView, /, *, allocates: bool) -> tuple[object, ...]:
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
