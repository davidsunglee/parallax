"""Planning and lowering one write instruction, for suites that pin a single
write's DML.

The shipped seam (:func:`~parallax.core.execution._write_lowering.stream_lowered`) is
plan-scoped, because a Write Plan is what the executor holds. A unit test
usually pins the statements of one instruction, so this plans it — through the
SAME production wiring :func:`~parallax.core.execution._planning.build_write_planner`
builds — as the one-instruction buffer it means, and hands back the lowered
statements in order.
"""

from __future__ import annotations

from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.execution._planning import build_write_planner
from parallax.core.execution._write_lowering import stream_lowered
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import Concurrency, TransactionInstant, WritePlanningRequest
from parallax.core.unit_work.instructions import (
    PreparedTargetWrite,
    PreparedWrite,
    WriteInstruction,
    prepare_typed_write,
)
from parallax.core.write_plan import WriteObservation
from parallax.core.write_plan.plan import NO_TEMPORAL_WRITE_OWNERSHIP, TemporalWriteOwnership
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_write

__all__ = ["lower_instruction", "lower_instruction_steps"]


def lower_instruction(
    instruction: WriteInstruction,
    model: Metamodel,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
    *,
    observation: WriteObservation | None = None,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> list[LoweredStatement]:
    """Every statement one instruction plans and lowers to, in execution order,
    for an attempt owning what ``ownership`` names."""
    return [
        statement
        for _step, statement in _stream(
            instruction, model, dialect, concurrency, tx_instant, observation, ownership
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
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> list[tuple[PlannedStep, LoweredStatement]]:
    """The same, paired with the settled step each statement came from."""
    return list(
        _stream(instruction, model, dialect, concurrency, tx_instant, observation, ownership)
    )


def _stream(
    instruction: WriteInstruction,
    model: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: TransactionInstant | None,
    observation: WriteObservation | None,
    ownership: TemporalWriteOwnership,
) -> list[tuple[PlannedStep, LoweredStatement]]:
    instant = inert_instant() if tx_instant is None else tx_instant
    plan = build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant,
            concurrency=concurrency,
            buffered_writes=[observed_write(_prepared(instruction, model), model, observation)],
            ownership=ownership,
            counts_unchanged_rows=dialect.counts_unchanged_rows,
        )
    )
    return list(stream_lowered(plan, model, dialect))


def _prepared(instruction: WriteInstruction, model: Metamodel) -> PreparedWrite:
    prepared = prepare_typed_write(instruction, model)
    assert not isinstance(prepared, PreparedTargetWrite)  # a target write buffers through its UoW
    return prepared
