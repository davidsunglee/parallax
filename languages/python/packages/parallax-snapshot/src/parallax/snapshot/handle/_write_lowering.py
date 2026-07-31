"""``parallax.snapshot.handle._write_lowering`` — a flush plan as its statements.

:func:`stream_lowered` is the single write-lowering seam: both the developer
transaction path (the ``FlushExecutor`` :meth:`Database.transact` injects) and
the conformance engine drive THIS function, so there is exactly one place a
flush plan becomes DML.

It composes the two halves the work is split into and adds nothing of its own.
:func:`~parallax.snapshot.handle._finalize.finalize_item` settles each buffered
item into finalized steps — resolving members, deriving framework-owned values,
expanding temporal topology, and spending the concurrency mode — and
:func:`~parallax.snapshot.handle._step_lowering.lower_step` renders each settled
step as the one statement it physically is. Every step therefore lowers 1:1, and
nothing here reads an instruction, an observation, a mode, or an instant.

This module sits ABOVE the two halves and below nothing else in the package: it
imports `_finalize`, `_step_lowering`, and `_write_types`, and none of those
imports back.
"""

from __future__ import annotations

from collections.abc import Iterator

from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import (
    Concurrency,
    ExactCount,
    FlushPlan,
    MissingTarget,
    PlannedInsert,
    StaleWrite,
)
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.snapshot.handle._finalize import finalize_item
from parallax.snapshot.handle._step_lowering import lower_step
from parallax.snapshot.handle._write_types import LoweredStatement

__all__ = ["stream_lowered"]


def stream_lowered(
    plan: FlushPlan, meta: Metamodel, dialect: Dialect, concurrency: Concurrency
) -> Iterator[tuple[PlannedStep, LoweredStatement]]:
    """Each of ``plan``'s steps paired with the statement it lowers to, in
    execution order.

    ``concurrency`` is the owning unit of work's participation mode, spent
    during finalization: it decides whether an observation-requiring write's
    gate is rendered at all. ``plan.tx_instant`` is the attempt's lazy
    Transaction Instant, consulted only where a temporal mutation expands, which
    is how a flush that declares no Transaction-Time boundary completes without
    reading the Clock Strategy (ADR 0010).

    A temporal mutation expands into a close followed immediately by its
    successors, so a close's own shortfall aborts BEFORE the rows it would have
    chained execute.
    """
    for planned in plan.writes:
        for step in finalize_item(planned, meta, concurrency, plan.tx_instant):
            expected, stale = _expectation(step)
            yield (
                step,
                LoweredStatement(
                    lower_step(step, meta, dialect),
                    expected_affected=expected,
                    stale_error=stale,
                ),
            )


def _expectation(step: PlannedStep) -> tuple[int | None, bool]:
    """The affected-row expectation the executor still checks per statement.

    A step's Affected Rows Policy is fully settled, but the authoritative
    enforcer that interprets it does not exist yet, so this reads the two facts
    today's executor understands: the expected count, and whether a shortfall is
    the non-retriable stale outcome an ungated observation-requiring write earns
    rather than the retriable gated conflict. A Missing Target policy — an
    observation-free keyed write against rows that may simply not be there — is
    settled but deliberately unenforced, because turning it on is a behavior
    change that belongs with the enforcer that owns the outcome.
    """
    if isinstance(step, PlannedInsert):
        return None, False
    policy = step.affected_rows
    if not isinstance(policy, ExactCount) or isinstance(policy.on_shortfall, MissingTarget):
        return None, False
    return policy.expected, isinstance(policy.on_shortfall, StaleWrite)
