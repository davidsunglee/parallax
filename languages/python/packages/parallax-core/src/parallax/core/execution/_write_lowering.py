from __future__ import annotations

from collections.abc import Iterator

from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.sql_gen._write import StepPayload, compile_write_step
from parallax.core.write_plan import WritePlan
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.steps import (
    PlannedClose,
    PlannedInsert,
    PlannedTemporalRevision,
    PlannedUpdate,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = ["lowered", "stream_lowered"]


def stream_lowered(
    plan: WritePlan, payloads: WritePayloadPreparer, meta: Metamodel, dialect: Dialect
) -> Iterator[tuple[PlannedStep, LoweredStatement]]:
    """Each of ``plan``'s steps paired with the statement it lowers to, in
    execution order, each lowered only when it is asked for.

    The step is yielded alongside its statement because the step — not the
    statement — carries the Affected Rows Policy the executor asks the unit of
    work to interpret. Pairing them here keeps that policy on the semantic
    value that owns it instead of copying it onto a physical one.

    A temporal mutation's finalized close precedes the successors it chains
    (`m-unit-work` "expand temporal topology in place"), so a close's own
    shortfall aborts BEFORE the rows it would have chained execute.
    """
    for step in plan.steps:
        yield (step, lowered(step, payloads, meta, dialect))


def lowered(
    step: PlannedStep, payloads: WritePayloadPreparer, meta: Metamodel, dialect: Dialect
) -> LoweredStatement:
    """The one statement ``step`` lowers to, storing the payload its statement
    demands: backing settlement already prepared where an entry carries it, and
    otherwise what ``payloads`` prepares now."""
    return compile_write_step(step, _demanded(step, payloads), meta, dialect)


def _demanded(step: PlannedStep, payloads: WritePayloadPreparer) -> StepPayload:
    match step:
        case PlannedInsert(entity=entity, entries=(entry,)):
            return (payloads.row(entity, entry) if entry.prepared is None else entry.prepared,)
        case PlannedInsert(entity=entity, entries=entries):
            return tuple(
                payloads.row(entity, entry) if entry.prepared is None else entry.prepared
                for entry in entries
            )
        case PlannedUpdate() | PlannedClose() | PlannedTemporalRevision():
            return payloads.assignments(step.entity, step.assignments)
        case _:
            return None
