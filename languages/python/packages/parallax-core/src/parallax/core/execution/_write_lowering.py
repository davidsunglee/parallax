from __future__ import annotations

from collections.abc import Iterable, Iterator

from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._write import StepPayload, compile_write_step, effect_bind_bound
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.steps import (
    PlannedClose,
    PlannedInsert,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = [
    "LoweringCursor",
    "lowered",
    "lowered_within",
    "ordered_bind_bound",
    "stream_lowered",
]


class LoweringCursor:
    """``steps`` taken one at a time, each lowered only when asked, storing the
    payload its statement demands.

    Execution's route from a borrowed span of Planned Writes to statements:
    each step is taken from its sequence exactly once and taking it lowers
    nothing, so a step can be looked at before anything is prepared for it, and
    a lazily built step is never built again to be lowered or enforced.
    """

    __slots__ = ("_dialect", "_meta", "_payloads", "_steps")

    def __init__(
        self,
        steps: Iterable[PlannedStep],
        payloads: WritePayloadPreparer,
        meta: Metamodel,
        dialect: Dialect,
    ) -> None:
        self._steps = iter(steps)
        self._payloads = payloads
        self._meta = meta
        self._dialect = dialect

    def take(self) -> PlannedStep | None:
        """The next step, or ``None`` once the span is exhausted."""
        return next(self._steps, None)

    def lowered(self, step: PlannedStep) -> LoweredStatement:
        return lowered(step, self._payloads, self._meta, self._dialect)

    def ordered_bound(self, step: PlannedStep) -> int | None:
        return ordered_bind_bound(step, self._dialect)

    def lowered_within(self, step: PlannedStep, bound: int) -> LoweredStatement:
        return lowered_within(step, bound, self._payloads, self._meta, self._dialect)


def stream_lowered(
    steps: Iterable[PlannedStep], payloads: WritePayloadPreparer, meta: Metamodel, dialect: Dialect
) -> Iterator[tuple[PlannedStep, LoweredStatement]]:
    """Each of ``steps`` paired with the statement it lowers to, in order,
    each taken from ``steps`` and lowered only when it is asked for.

    ``steps`` is a plan's sequence, or a span borrowed from it, a bound range,
    or a continuation round. The step is yielded alongside its statement
    because the step — not the statement — carries the Affected Rows Policy
    the executor asks the unit of work to interpret. Pairing them here keeps
    that policy on the very value the statement was lowered from, so a lazily
    rebuilt step is never rebuilt again to be enforced.

    A temporal mutation's finalized close precedes the successors it chains
    (`m-unit-work` "expand temporal topology in place"), so a close's own
    shortfall aborts BEFORE the rows it would have chained execute.
    """
    for step in steps:
        yield (step, lowered(step, payloads, meta, dialect))


def lowered(
    step: PlannedStep, payloads: WritePayloadPreparer, meta: Metamodel, dialect: Dialect
) -> LoweredStatement:
    """The one statement ``step`` lowers to, storing the payload its statement
    demands: backing settlement already prepared where an entry carries it, and
    otherwise what ``payloads`` prepares now."""
    return compile_write_step(step, _demanded(step, payloads), meta, dialect)


def ordered_bind_bound(step: PlannedStep, dialect: Dialect) -> int | None:
    """The most binds ``step``'s statement may carry where ordered write
    transport can present it, decided before its payload is demanded; ``None``
    where it cannot.

    Only a count-only temporal effect qualifies — a close, guard, revision, or
    removal — and only one whose statement fits the dialect's bind limit on its
    own. Every other step, and one whose bound exceeds that limit, runs alone.
    """
    match step:
        case (
            PlannedClose()
            | PlannedTemporalRevision()
            | PlannedTemporalRemoval()
            | PlannedTemporalGuard()
        ):
            bound = effect_bind_bound(step)
            return bound if bound <= dialect.max_bind_parameters else None
        case _:
            return None


def lowered_within(
    step: PlannedStep,
    bound: int,
    payloads: WritePayloadPreparer,
    meta: Metamodel,
    dialect: Dialect,
) -> LoweredStatement:
    """``step``'s one statement, which carries no more than the ``bound`` binds
    its shape promised before its payload was demanded.

    A statement exceeding its promise is refused as a lowering failure rather
    than presented to transport selected on the strength of that promise.
    """
    statement = lowered(step, payloads, meta, dialect)
    binds = len(statement.binds)
    if binds > bound:
        raise SqlGenError(
            f"{step.entity.canonical}: a statement carrying {binds} binds exceeds the "
            f"{bound} its shape promised before its payload was prepared"
        )
    return statement


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
