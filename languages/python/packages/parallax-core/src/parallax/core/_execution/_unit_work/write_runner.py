from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from parallax.core.internal.document_codec import apply_prepared_patches
from parallax.core.internal.planned_step.payload import DocumentPatches
from parallax.core.internal.planned_step.steps import (
    PlannedDelete,
    PlannedStep,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)
from parallax.core.internal.planned_step.write_effects import (
    CurrentRowCapture,
    CurrentRowOutput,
    EffectSpan,
    WriteEffects,
)

__all__ = ["ExecuteCountedStep", "ExecuteWriteSteps"]


class ExecuteWriteSteps(Protocol):
    """How a flush has one sequence of Planned Steps executed: a Write
    Group's steps, with the effect spans among them it may present as grouped
    effects.

    A normal return means every step executed and its effect was enforced, in
    order; it completes no settled write and commits nothing. Nothing of the
    steps stays reachable from it once the call returns. Where ``capture`` is
    given, it receives each demanded payload as lowering demands it.
    """

    def __call__(
        self,
        steps: tuple[PlannedStep, ...],
        /,
        *,
        effect_spans: tuple[EffectSpan, ...] = (),
        capture: CurrentRowCapture | None = None,
    ) -> None: ...


class ExecuteCountedStep(Protocol):
    """How a predicate-selected write's one statement executes: lowered,
    executed, and enforced as a step of a Write Group is, answering the
    affected-row count its configured driver reported for it."""

    def __call__(self, step: PlannedUpdate | PlannedDelete, /) -> int: ...


class _GroupRowCapture:
    """The current rows the writes of one running Write Group describe
    (:attr:`~parallax.core.internal.planned_step.write_effects.WriteEffects.current_outputs`),
    each staged with the document its emitter's payload stores as normal
    lowering demands that payload, until its write completes.

    The outputs are indexed by emitter once, so a captured entry or revision
    finds its own description whatever the steps' order. What failed steps
    staged is never taken, and :meth:`release` drops it.
    """

    __slots__ = ("_outputs", "_staged")

    def __init__(self, outputs: Iterable[CurrentRowOutput]) -> None:
        self._outputs = {id(output.emitter): output for output in outputs}
        self._staged: dict[int, object | None] = {}

    @classmethod
    def for_writes(cls, writes: Iterable[WriteEffects]) -> _GroupRowCapture | None:
        """The capture of every output ``writes`` describe, or ``None`` where
        they describe none."""
        outputs = [output for write in writes for output in write.current_outputs]
        return cls(outputs) if outputs else None

    def inserted(self, entry: WriteRow, document: object | None, /) -> None:
        output = self._outputs.get(id(entry))
        if output is not None and output.emitter is entry:
            self._staged[id(output)] = document

    def revised(
        self, revision: PlannedTemporalRevision, patches: DocumentPatches | None, /
    ) -> None:
        output = self._outputs.get(id(revision))
        if output is None or output.emitter is not revision:
            return
        document = output.predecessor_document
        self._staged[id(output)] = (
            document if patches is None else apply_prepared_patches(document, patches.patches)
        )

    def take_rows(
        self, outputs: Iterable[CurrentRowOutput]
    ) -> tuple[tuple[CurrentRowOutput, object | None], ...]:
        """Each of ``outputs`` its execution captured, with the document it
        stored, released from this capture together with its description."""
        described = self._outputs
        staged = self._staged
        taken: list[tuple[CurrentRowOutput, object | None]] = []
        for output in outputs:
            emitter = id(output.emitter)
            if described.get(emitter) is output:
                del described[emitter]
            if id(output) in staged:
                taken.append((output, staged.pop(id(output))))
        return tuple(taken)

    def release(self) -> None:
        """Drop every description and staged document this capture still
        holds, whether or not its writes completed."""
        self._outputs.clear()
        self._staged.clear()
