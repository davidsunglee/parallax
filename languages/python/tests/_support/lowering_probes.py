"""Planning and lowering one write instruction, for suites that pin a single
write's DML.

Each settled step lowers alone through the shipped seam
(:func:`~parallax.core._execution._write_lowering.lowered`), one statement per
Planned Step, whatever statements execution then groups them into. A unit test
usually pins the statements of one instruction, so this plans it — through the
SAME production wiring :func:`~parallax.core._execution._planning.build_write_planner`
builds — as the buffer it means, one admitted write per keyed instruction of a
sequence, or as the one statement a predicate-selected write executes as, and
hands back the lowered statements in order.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import cast

from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import (
    WriteInstruction,
)
from parallax.core._execution._unit_work.preparation import (
    PreparedInstruction,
    PreparedPredicateInstruction,
    PreparedTargetInstruction,
)
from parallax.core._execution._write_lowering import lowered
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.planned_step import StateObservation
from parallax.core.internal.planned_step.payload import WritePayloadPreparer
from parallax.core.internal.planned_step.steps import PlannedStep
from parallax.core.internal.planned_step.write_effects import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    TemporalWriteOwnership,
)
from parallax.core.internal.sql_gen import LoweredStatement
from parallax.core.internal.unit_work import (
    KeyedWriteInstruction,
    TransactionInstant,
    WritePlanningRequest,
)
from parallax.core.internal.write_payload import LayoutPayloadPreparer
from tests._support.bindings import bound_model
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    observed_buffer,
    observed_write,
    plan_steps,
)
from tests._support.write_preparation import prepare_instruction, write_preparation_of

__all__ = ["lower_instruction", "lower_instruction_steps", "lowered_steps"]


def lowered_steps(
    steps: Iterable[PlannedStep], payloads: WritePayloadPreparer, meta: Metamodel, dialect: Dialect
) -> Iterator[tuple[PlannedStep, LoweredStatement]]:
    """Each of ``steps`` paired with the one statement it lowers to alone, in
    order, each lowered only when it is asked for."""
    for step in steps:
        yield step, lowered(step, payloads, bound_model(meta), dialect)


def lower_instruction(
    instruction: WriteInstruction | Sequence[KeyedWriteInstruction],
    model: Metamodel,
    dialect: Dialect = POSTGRES,
    concurrency: ConcurrencyPreference = "locking",
    tx_instant: TransactionInstant | None = None,
    *,
    observation: StateObservation | None = None,
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
    instruction: WriteInstruction | Sequence[KeyedWriteInstruction],
    model: Metamodel,
    dialect: Dialect = POSTGRES,
    concurrency: ConcurrencyPreference = "locking",
    tx_instant: TransactionInstant | None = None,
    *,
    observation: StateObservation | None = None,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> list[tuple[PlannedStep, LoweredStatement]]:
    """The same, paired with the settled step each statement came from."""
    return list(
        _stream(instruction, model, dialect, concurrency, tx_instant, observation, ownership)
    )


def _stream(
    instruction: WriteInstruction | Sequence[KeyedWriteInstruction],
    model: Metamodel,
    dialect: Dialect,
    concurrency: ConcurrencyPreference,
    tx_instant: TransactionInstant | None,
    observation: StateObservation | None,
    ownership: TemporalWriteOwnership,
) -> list[tuple[PlannedStep, LoweredStatement]]:
    instant = inert_instant() if tx_instant is None else tx_instant
    planner = build_write_planner(bound_model(model))
    prepared = None if isinstance(instruction, Sequence) else _prepared(instruction, model)
    if isinstance(prepared, PreparedPredicateInstruction):
        assert observation is None  # a readless predicate write observes nothing
        steps: tuple[PlannedStep, ...] = (
            planner.predicate_step(
                prepared, actor_identity=TEST_ACTOR_IDENTITY, transaction_instant=instant
            ),
        )
    else:
        if prepared is None:
            assert observation is None  # an observation is evidence about one object
            writes = observed_buffer(
                cast("Sequence[KeyedWriteInstruction]", instruction), model, None
            )
        else:
            writes = [observed_write(prepared, model, observation)]
        steps = plan_steps(
            planner.finalize(
                WritePlanningRequest(
                    actor_identity=TEST_ACTOR_IDENTITY,
                    transaction_instant=instant,
                    preference=concurrency,
                    composed_writes=writes,
                    ownership=ownership,
                    counts_unchanged_rows=dialect.counts_unchanged_rows,
                )
            )
        )
    return list(lowered_steps(steps, LayoutPayloadPreparer(bound_model(model)), model, dialect))


def _prepared(instruction: WriteInstruction, model: Metamodel) -> PreparedInstruction:
    prepared = prepare_instruction(instruction, write_preparation_of(model))
    assert not isinstance(
        prepared, PreparedTargetInstruction
    )  # a target write buffers through its UoW
    return prepared
