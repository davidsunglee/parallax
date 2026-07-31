"""Lowering one plan item, for suites that pin a single write's DML.

The shipped seam (:func:`~parallax.snapshot.handle.stream_lowered`) is
plan-scoped, because a flush plan is what the executor holds. A unit test
usually pins the statements of one instruction, so this wraps that instruction
in the one-item plan it means and hands back the lowered statements in order.
"""

from __future__ import annotations

from _support.clock_probes import inert_instant
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    Concurrency,
    FlushPlan,
    PlannedWrite,
    TransactionInstant,
)
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.snapshot.handle import LoweredStatement, stream_lowered

__all__ = ["lower_planned", "lower_planned_steps"]


def lower_planned(
    planned: PlannedWrite,
    model: Metamodel,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
) -> list[LoweredStatement]:
    """Every statement one plan item lowers to, in execution order."""
    return [lowered for _step, lowered in _stream(planned, model, dialect, concurrency, tx_instant)]


def lower_planned_steps(
    planned: PlannedWrite,
    model: Metamodel,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
    tx_instant: TransactionInstant | None = None,
) -> list[tuple[PlannedStep, LoweredStatement]]:
    """The same, paired with the settled step each statement came from."""
    return list(_stream(planned, model, dialect, concurrency, tx_instant))


def _stream(
    planned: PlannedWrite,
    model: Metamodel,
    dialect: Dialect,
    concurrency: Concurrency,
    tx_instant: TransactionInstant | None,
) -> list[tuple[PlannedStep, LoweredStatement]]:
    instant = inert_instant() if tx_instant is None else tx_instant
    plan = FlushPlan(writes=(planned,), tx_instant=instant)
    return list(stream_lowered(plan, model, dialect, concurrency))
