from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from parallax.core._execution._unit_work.acquisition import AcquireRows, consume_coverage
from parallax.core._execution._unit_work.admission import UnitOfWorkError
from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core._execution._unit_work.ranges import (
    DeferredTemporalRange,
    coverage_reads,
    retained_completion,
)
from parallax.core._execution._unit_work.strategy import ActorIdentity
from parallax.core._execution._unit_work.write_planner import WritePlanner
from parallax.core.write_plan.keys import ObjectStateKey
from parallax.core.write_plan.plan import (
    BoundRange,
    DeferredRange,
    ExecutionUnit,
    TemporalWriteOwnership,
    UnitEffects,
    WritePlan,
    WriteStepView,
)
from parallax.core.write_plan.predecessor_rows import PredecessorRows

if TYPE_CHECKING:
    from parallax.core._execution._unit_work.uow import UnitOfWork

__all__ = ["ExecuteWriteSteps", "acquire_and_bind_range", "run_write_plan"]


class ExecuteWriteSteps(Protocol):
    """How a flush has one span of Planned Writes executed: a unit's planned
    steps, or the steps its deferred range bound.

    A normal return means every step of the span executed and its effect was
    enforced, in order; it completes no unit and commits nothing. With
    ``allocates``, it answers the key the database allocated for each row a
    row-producing insert of the span opened, in step order, and otherwise none.
    The span is borrowed: nothing of it stays reachable once the call returns.
    """

    def __call__(self, steps: WriteStepView, /, *, allocates: bool) -> tuple[object, ...]: ...


def run_write_plan(owner: UnitOfWork, plan: WritePlan, execute: ExecuteWriteSteps, /) -> None:
    """Execute ``plan``'s units in order through ``execute``, completing each
    in ``owner`` as soon as its steps succeeded and before any step of a later
    unit is taken.

    A deferred unit binds at its turn, against the ownership and continuity
    every earlier unit published: to the retained rows it reuses and the
    coverage they leave. A unit with no step still
    completes. A unit that fails completes nothing, and nothing after it is
    prepared, bound, or executed.
    """
    complete = owner._complete_unit  # pyright: ignore[reportPrivateUsage] - the owner's completion
    steps = plan.steps
    start = 0
    for unit in plan.units:
        allocated = execute(steps.view(start, unit.end), allocates=bool(unit.opened.allocated))
        start = unit.end
        _require_allocated(unit, allocated)
        deferred = unit.deferred
        complete(unit, unit if deferred is None else _deferred(owner, deferred, execute), allocated)


def _require_allocated(unit: ExecutionUnit, allocated: tuple[object, ...]) -> None:
    expected = len(unit.opened.allocated)
    if len(allocated) != expected:
        raise UnitOfWorkError(
            f"an execution unit opening {expected} row(s) whose keys the database allocates "
            f"executed answering {len(allocated)} key(s)"
        )


def _deferred(
    owner: UnitOfWork, deferred: DeferredRange, execute: ExecuteWriteSteps
) -> UnitEffects:
    """What ``deferred`` publishes once bound under ``owner``'s current
    ownership and executed: the range's bound effects."""
    bound = acquire_and_bind_range(
        deferred,
        acquire_rows=owner.acquire_rows,
        planner=owner._planner,  # pyright: ignore[reportPrivateUsage] - the owner's binding inputs
        ownership=owner._admission.ownership,  # pyright: ignore[reportPrivateUsage] - the owner's binding inputs
        actor_identity=owner._actor_identity,  # pyright: ignore[reportPrivateUsage] - the owner's binding inputs
        transaction_instant=owner._transaction_instant,  # pyright: ignore[reportPrivateUsage] - the owner's binding inputs
        current=owner._current,  # pyright: ignore[reportPrivateUsage] - the owner's freshness check
    )
    execute(bound.steps.view(0, len(bound.steps)), allocates=False)
    return bound


def acquire_and_bind_range(
    description: DeferredRange,
    /,
    *,
    acquire_rows: AcquireRows,
    planner: WritePlanner,
    ownership: TemporalWriteOwnership,
    actor_identity: ActorIdentity,
    transaction_instant: TransactionInstant,
    current: Callable[[ObjectStateKey, int], bool] | None = None,
) -> BoundRange:
    """``description`` read and bound: the starting rows it retained that are
    still ``current`` completed through ``acquire_rows``, which reads nothing
    for them, then only the coverage nothing it holds covers read through
    ``acquire_rows``, every row sealed as Predecessor Rows while its read's
    resources are live, then bound by the ``planner`` that finalized it under
    ``ownership``, each row it produces and close it emits audited once.

    Without ``current`` no retained row is judged current, so each is
    discarded unjudged and its coverage read instead.

    A description ``planner`` did not finalize as a range is refused before
    anything is read.
    """
    if not isinstance(description, DeferredTemporalRange):
        raise TypeError(
            f"a deferred range this planner did not finalize cannot be bound: {description!r}"
        )
    completion = retained_completion(description, current or _never_current)
    reused = None if completion is None else acquire_rows(completion, consume_coverage)
    acquired: list[PredecessorRows] = []
    for request in coverage_reads(description, reused):
        rows = acquire_rows(request, consume_coverage)
        if rows is not None:
            acquired.append(rows)
    return planner.bind_deferred(
        description,
        reused,
        acquired,
        ownership=ownership,
        actor_identity=actor_identity,
        transaction_instant=transaction_instant,
    )


def _never_current(state: ObjectStateKey, read_at: int) -> bool:
    del state, read_at
    return False
