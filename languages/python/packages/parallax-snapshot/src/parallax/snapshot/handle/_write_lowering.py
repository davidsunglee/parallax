from __future__ import annotations

from collections.abc import Iterator

from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.write_plan import WritePlan
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = ["lowered", "stream_lowered"]


def stream_lowered(
    plan: WritePlan, meta: Metamodel, dialect: Dialect
) -> Iterator[tuple[PlannedStep, LoweredStatement]]:
    """Each of ``plan``'s steps paired with the statement it lowers to, in
    execution order.

    The step is yielded alongside its statement because the step — not the
    statement — carries the Affected Rows Policy the executor asks the unit of
    work to interpret. Pairing them here keeps that policy on the semantic
    value that owns it instead of copying it onto a physical one.

    A temporal mutation's finalized close precedes the successors it chains
    (`m-unit-work` "expand temporal topology in place"), so a close's own
    shortfall aborts BEFORE the rows it would have chained execute.
    """
    for step in plan.steps:
        yield (step, compile_write_step(step, meta, dialect))


def lowered(step: PlannedStep, meta: Metamodel, dialect: Dialect) -> LoweredStatement:
    """The one statement ``step`` lowers to — a step no plan held in advance,
    which a deferred range bound at execution."""
    return compile_write_step(step, meta, dialect)
