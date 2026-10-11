from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Final, NamedTuple

from parallax.core import temporal_read
from parallax.core.dialect import Dialect
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._write import (
    InsertStatementBuilder,
    StepPayload,
    compile_write_step,
    effect_bind_bound,
)
from parallax.core.write_plan.payload import RowPayload, WritePayloadPreparer
from parallax.core.write_plan.steps import (
    MaxPlusOne,
    PlannedClose,
    PlannedInsert,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = [
    "LoweredOpening",
    "LoweringCursor",
    "lowered",
    "lowered_within",
    "ordered_bind_bound",
    "stream_lowered",
    "stream_physical",
]

_OPENING_ENTRIES: Final = 64
"""The most entries one grouped opening statement inserts. It bounds the
statement a run of openings builds before that statement executes; a longer run
continues in another statement once this one has run."""


class LoweredOpening(NamedTuple):
    """One statement inserting a run of temporal openings, and how the run
    ended: at ``following``, the step that could not join it, taken but neither
    prepared nor lowered; at ``failure``, raised ordinarily taking, preparing,
    or appending a later opening, the statement then holding exactly the
    entries appended before it; or at neither, where the statement reached its
    capacity or the steps ran out."""

    statement: LoweredStatement
    following: PlannedStep | None
    failure: Exception | None


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

    def opening(self, step: PlannedStep) -> PlannedInsert | None:
        """``step`` where it can begin a grouped opening statement — a temporal
        Entity's single-entry insert holding no generated value — decided before
        its payload is demanded; ``None`` where it lowers alone."""
        if (
            isinstance(step, PlannedInsert)
            and len(step.entries) == 1
            and _temporal(self._meta, step.entity)
            and not _generates(step.entries[0])
        ):
            return step
        return None

    def lowered_opening(self, first: PlannedInsert) -> LoweredOpening:
        """``first`` and the compatible openings following it, as one
        multi-row statement.

        Before another step is taken the statement must have room for one more
        entry within the internal entry cap and the dialect's bind limit, and
        before a taken step's payload is demanded the step must be a
        single-entry insert of the same Entity naming the same members and
        holding no generated value; values, origins, and audit values may
        differ. Each entry's payload is the backing it already carries, or the
        one prepared now. ``first`` failing raises, and a control-flow or fatal
        exception propagates with nothing returned.
        """
        (entry,) = first.entries
        entity = first.entity
        members = entry.row.members
        payloads = self._payloads
        builder = InsertStatementBuilder(
            entity, entry, _row_payload(payloads, entity, entry), self._meta, self._dialect
        )
        binds = self._dialect.max_bind_parameters
        following: PlannedStep | None = None
        while builder.has_capacity(_OPENING_ENTRIES, binds):
            try:
                following = self.take()
                joining = _joining(following, entity, members)
                if joining is None:
                    break
                builder.append(joining, _row_payload(payloads, entity, joining))
            except Exception as error:
                return LoweredOpening(builder.finish(), None, error)
            following = None
        return LoweredOpening(builder.finish(), following, None)


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


def stream_physical(
    steps: Iterable[PlannedStep], payloads: WritePayloadPreparer, meta: Metamodel, dialect: Dialect
) -> Iterator[LoweredStatement]:
    """Each statement ``steps`` execute as, in order: a run of compatible
    temporal openings as the one statement inserting them all, and every other
    step as the one statement it lowers to.

    The runs are selected and lowered by the very cursor operations execution
    selects and lowers them by, so the statements a dry traversal of settled
    steps answers are the statements their execution runs. A run ended by a
    later opening's failure answers the statement holding the openings before
    it, then raises that failure.
    """
    cursor = LoweringCursor(steps, payloads, meta, dialect)
    step = cursor.take()
    while step is not None:
        first = cursor.opening(step)
        if first is None:
            yield cursor.lowered(step)
            step = cursor.take()
            continue
        statement, following, failure = cursor.lowered_opening(first)
        yield statement
        if failure is not None:
            raise failure
        step = cursor.take() if following is None else following


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


def _row_payload(
    payloads: WritePayloadPreparer, entity: EntityIdentity, entry: WriteRow
) -> RowPayload:
    return payloads.row(entity, entry) if entry.prepared is None else entry.prepared


def _temporal(meta: Metamodel, entity: EntityIdentity) -> bool:
    return isinstance(
        temporal_read.view(meta).shape(entity),
        temporal_read.TransactionTimeOnly | temporal_read.Bitemporal,
    )


def _generates(entry: WriteRow) -> bool:
    return any(isinstance(value, MaxPlusOne) for value in entry.row.attributes.values())


def _joining(
    step: PlannedStep | None,
    entity: EntityIdentity,
    members: frozenset[AttributeIdentity | ValueObjectIdentity],
) -> WriteRow | None:
    """``step``'s one entry where it can join a grouped opening of ``entity``
    whose entries name ``members``: placement follows the Entity and the
    members named, never the values held."""
    match step:
        case PlannedInsert(entity=other, entries=(entry,)) if (
            other == entity and entry.row.members == members and not _generates(entry)
        ):
            return entry
        case _:
            return None
