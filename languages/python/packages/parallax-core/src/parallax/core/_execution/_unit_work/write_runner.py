from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from parallax.core.document_codec import apply_prepared_patches
from parallax.core.write_plan.payload import PatchedDocument
from parallax.core.write_plan.plan import BoundRange, CurrentRowOutput, SettledWrite
from parallax.core.write_plan.steps import (
    PlannedDelete,
    PlannedStep,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)

__all__ = ["ExecuteCountedStep", "ExecuteWriteSteps"]


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
    """The current rows the writes of one running group or bound range describe
    (:attr:`~parallax.core.write_plan.plan.WriteCompletion.current_outputs`),
    each staged with the document its emitter's payload stores as normal
    lowering demands that payload, until its write completes.

    The outputs are indexed by emitter once, so a captured entry or revision
    finds its own description whatever the steps' order. What failed steps
    staged is never taken.
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
