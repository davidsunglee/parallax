"""Planning and lowering one write instruction, for suites that pin a single
write's DML.

The shipped seam (:func:`~parallax.snapshot.handle.stream_lowered`) is
plan-scoped, because a Write Plan is what the executor holds. A unit test
usually pins the statements of one instruction, so this plans it — through the
SAME production wiring :func:`~parallax.snapshot.handle.build_write_planner`
builds — as the one-instruction buffer it means, and hands back the lowered
statements in order.
"""

from __future__ import annotations

from _support.clock_probes import inert_instant
from _support.planner_probes import TEST_SUBJECT_IDENTITY
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import Statement
from parallax.core.unit_work import (
    Concurrency,
    KeyedWrite,
    ObservedKeyedWrite,
    PlanningRequest,
    TransactionInstant,
    WriteInstruction,
    WriteObservation,
)
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.snapshot.handle import build_write_planner, stream_lowered

__all__ = ["lower_instruction", "lower_instruction_steps"]


def lower_instruction(
    instruction: WriteInstruction,
    model: Metamodel,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
    *,
    observation: WriteObservation | None = None,
) -> list[Statement]:
    """Every statement one instruction plans and lowers to, in execution order."""
    return [
        statement
        for _step, statement in _stream(
            instruction, model, dialect, concurrency, tx_instant, observation
        )
    ]


def lower_instruction_steps(
    instruction: WriteInstruction,
    model: Metamodel,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
    *,
    observation: WriteObservation | None = None,
) -> list[tuple[PlannedStep, Statement]]:
    """The same, paired with the settled step each statement came from."""
    return list(_stream(instruction, model, dialect, concurrency, tx_instant, observation))


def _stream(
    instruction: WriteInstruction,
    model: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: TransactionInstant | None,
    observation: WriteObservation | None,
) -> list[tuple[PlannedStep, Statement]]:
    instant = inert_instant() if tx_instant is None else tx_instant
    buffered: WriteInstruction | ObservedKeyedWrite = instruction
    if observation is not None:
        assert isinstance(instruction, KeyedWrite)  # only a keyed write carries an observation
        buffered = ObservedKeyedWrite(instruction=instruction, observation=observation)
    plan = build_write_planner(model).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=instant,
            concurrency=concurrency,
            buffered_writes=[buffered],
        )
    )
    return list(stream_lowered(plan, model, dialect))
