"""``parallax.snapshot.handle._write_lowering`` — a Write Plan as its statements.

:func:`stream_lowered` is the single write-lowering seam: both the developer
transaction path (the ``FlushExecutor`` :meth:`Database.transact` injects) and
the conformance engine drive THIS function, so there is exactly one place a
Write Plan becomes DML.

Every step in a :class:`~parallax.core.unit_work.WritePlan` already carries its
target, row topology, concurrency decision, and expected effect settled — the
Write Planner (:mod:`~parallax.snapshot.handle._planning`) decided all of that
before this function ever runs — so lowering answers only the physical
question :func:`~parallax.snapshot.handle._step_lowering.lower_step` renders:
which Columns participate, in which order, quoted for which dialect. Nothing
here reads an instruction, an observation, a mode, or an instant.

This module sits ABOVE ``_step_lowering`` and below nothing else in the
package: it imports `_step_lowering`, which does not import back.
"""

from __future__ import annotations

from collections.abc import Iterator

from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import WritePlan
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.snapshot.handle._step_lowering import lower_step

__all__ = ["stream_lowered"]


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
        yield (step, lower_step(step, meta, dialect))
