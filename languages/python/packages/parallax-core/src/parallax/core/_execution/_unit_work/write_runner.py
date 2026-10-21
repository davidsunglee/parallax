from __future__ import annotations

from collections.abc import Callable, Iterable
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
from parallax.core.document_codec import apply_prepared_patches
from parallax.core.write_plan.keys import ObjectStateKey
from parallax.core.write_plan.payload import PatchedDocument
from parallax.core.write_plan.plan import (
    BoundRange,
    CurrentRowOutput,
    DeferredRange,
    SettledWrite,
    TemporalWriteOwnership,
    WritePlan,
)
from parallax.core.write_plan.predecessor_rows import PredecessorRows
from parallax.core.write_plan.steps import (
    PlannedDelete,
    PlannedStep,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)

if TYPE_CHECKING:
    from parallax.core._execution._unit_work.uow import UnitOfWork

__all__ = ["ExecuteCountedStep", "ExecuteWriteSteps", "acquire_and_bind_range", "run_write_plan"]


class ExecuteWriteSteps(Protocol):
    """How a flush has one sequence of Planned Steps executed: a Write Group's
    steps, or the steps a deferred range bound.

    A normal return means every step executed and its effect was enforced, in
    order; it completes no settled write and commits nothing. With
    ``allocates``, it answers the key the database allocated for each row a
    row-producing insert of the steps opened, in step order, and otherwise
    none. Nothing of the steps stays reachable from it once the call returns.

    Where they are given, each insert entry's lowering hands
    ``capture_insert`` the entry and the Structured Column document its payload
    stores, ``None`` where it stores none, and each temporal revision's
    lowering hands ``capture_revision`` the revision and the patches its
    payload applies to that document, ``None`` where it applies none, as the
    payloads are demanded.
    """

    def __call__(
        self,
        steps: tuple[PlannedStep, ...],
        /,
        *,
        allocates: bool,
        capture_insert: Callable[[WriteRow, object | None], None] | None = None,
        capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
        | None = None,
    ) -> tuple[object, ...]: ...


class ExecuteCountedStep(Protocol):
    """How a predicate-selected write's one statement executes: lowered,
    executed, and enforced as a step of a Write Group is, answering the
    affected-row count its configured driver reported for it."""

    def __call__(self, step: PlannedUpdate | PlannedDelete, /) -> int: ...


class _CurrentRowCapture:
    """The current rows one running group's writes describe
    (:attr:`~parallax.core.write_plan.plan.WriteCompletion.current_outputs`),
    each staged with the document its emitter's payload stores as normal
    lowering demands that payload, until its write completes.

    The group's outputs are indexed by emitter once, so a captured entry or
    revision finds its own description whatever the steps' order. What a
    failed group staged is never taken.
    """

    __slots__ = ("_outputs", "_staged")

    def __init__(self, outputs: Iterable[CurrentRowOutput]) -> None:
        self._outputs = {id(output.emitter): output for output in outputs}
        self._staged: dict[int, object | None] = {}

    @classmethod
    def of(cls, writes: Iterable[BoundRange | SettledWrite]) -> _CurrentRowCapture | None:
        """The capture of every output ``writes`` describe, or ``None`` where
        they describe none."""
        outputs = [output for write in writes for output in write.current_outputs]
        return cls(outputs) if outputs else None

    def capture_insert(self, entry: WriteRow, document: object | None) -> None:
        output = self._outputs.get(id(entry))
        if output is not None and output.emitter is entry:
            self._staged[id(output)] = document

    def capture_revision(
        self, revision: PlannedTemporalRevision, patched: PatchedDocument | None
    ) -> None:
        output = self._outputs.get(id(revision))
        if output is None or output.emitter is not revision:
            return
        document = output.predecessor_document
        self._staged[id(output)] = (
            document if patched is None else apply_prepared_patches(document, patched.patches)
        )

    def take_rows(
        self, outputs: Iterable[CurrentRowOutput]
    ) -> tuple[tuple[CurrentRowOutput, object | None], ...]:
        """Each of ``outputs`` its execution captured, with the document it
        stored, released from this capture."""
        staged = self._staged
        return tuple((output, staged.pop(id(output))) for output in outputs if id(output) in staged)

    def execute(
        self, execute: ExecuteWriteSteps, steps: tuple[PlannedStep, ...], *, allocates: bool
    ) -> tuple[object, ...]:
        return execute(
            steps,
            allocates=allocates,
            capture_insert=self.capture_insert,
            capture_revision=self.capture_revision,
        )


def run_write_plan(
    owner: UnitOfWork, plan: WritePlan, execute: ExecuteWriteSteps, /, *, captures: bool = True
) -> None:
    """Execute ``plan``'s Write Groups in order through ``execute``,
    completing each settled write of a group in ``owner``, in order, as soon as
    the group's steps succeeded and before any step of a later group executes.

    A deferred settled write binds at its turn, against the ownership every
    earlier one published: to the retained rows it reuses, the current rows
    the attempt holds for continuing sources, and the coverage they leave. A
    settled write with no step still completes. A group that fails completes
    none of its writes, and nothing after it is prepared, bound, or executed.

    Where it ``captures``, the current rows a group's writes describe are
    captured as their payloads are demanded and published with each write's
    completion; a flush no later submission follows captures none.
    """
    complete = owner._complete_write  # pyright: ignore[reportPrivateUsage] - the owner's completion
    for group in plan.groups:
        writes = group.writes
        expected = sum(len(write.opened.allocated) for write in writes)
        capture = _CurrentRowCapture.of(writes) if captures else None
        if capture is None:
            allocated = execute(group.steps, allocates=bool(expected))
        else:
            allocated = capture.execute(execute, group.steps, allocates=bool(expected))
        if len(allocated) != expected:
            raise UnitOfWorkError(
                f"a Write Group opening {expected} row(s) whose keys the database allocates "
                f"executed answering {len(allocated)} key(s)"
            )
        first = 0
        for write in writes:
            stop = first + len(write.opened.allocated)
            deferred = write.deferred
            if deferred is None:
                captured = () if capture is None else capture.take_rows(write.current_outputs)
                complete(write, allocated[first:stop], captured)
            else:
                bound, captured = _execute_deferred_range(owner, deferred, execute, captures)
                complete(bound, allocated[first:stop], captured)
            first = stop


def _execute_deferred_range(
    owner: UnitOfWork, deferred: DeferredRange, execute: ExecuteWriteSteps, captures: bool
) -> tuple[BoundRange, tuple[tuple[CurrentRowOutput, object | None], ...]]:
    """What ``deferred`` publishes once bound under ``owner``'s current
    ownership and executed: the range's bound completion, and the current rows
    its execution captured where it ``captures``."""
    bound = acquire_and_bind_range(
        deferred,
        acquire_rows=owner.acquire_rows,
        planner=owner._planner,  # pyright: ignore[reportPrivateUsage] - the owner's binding inputs
        ownership=owner._admission.ownership,  # pyright: ignore[reportPrivateUsage] - the owner's binding inputs
        actor_identity=owner._actor_identity,  # pyright: ignore[reportPrivateUsage] - the owner's binding inputs
        transaction_instant=owner._transaction_instant,  # pyright: ignore[reportPrivateUsage] - the owner's binding inputs
        current=owner._current,  # pyright: ignore[reportPrivateUsage] - the owner's freshness check
    )
    capture = _CurrentRowCapture.of((bound,)) if captures else None
    if capture is None:
        execute(bound.steps, allocates=False)
        return bound, ()
    capture.execute(execute, bound.steps, allocates=False)
    return bound, capture.take_rows(bound.current_outputs)


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
    for them, then only the coverage nothing it holds or ``ownership`` holds
    for it covers read through ``acquire_rows``, every row sealed as
    Predecessor Rows while its read's resources are live, then bound by the
    ``planner`` that finalized it under ``ownership``, each row it produces and
    close it emits audited once.

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
    return planner.bind_range(
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
