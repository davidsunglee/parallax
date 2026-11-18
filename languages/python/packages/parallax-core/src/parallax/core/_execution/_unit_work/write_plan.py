from __future__ import annotations

from collections.abc import Generator, Hashable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from parallax.core.internal.planned_step.steps import PlannedInsert, PlannedStep
from parallax.core.internal.planned_step.write_effects import (
    BoundRange,
    EffectShapeOf,
    EffectSpan,
    WriteEffects,
)

if TYPE_CHECKING:
    from parallax.core._execution._unit_work.acquisition_spans import AcquisitionSpan

__all__ = [
    "PlanEntry",
    "SettledWrite",
    "WriteGroup",
    "WritePlan",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class SettledWrite(WriteEffects):
    """One caller write after settlement in a Write Plan: the Planned Steps it
    executes, in order, and the effects their success publishes.

    Its effects are published only once every step of its Write Group has
    succeeded, and before any later group executes. Removals are retired before
    openings are registered, so a row removed and reopened at the same
    coordinates remains owned, and an insertion whose last row the write
    removed still stands when a row the write opened continues it.

    ``source_evidence`` holds, by identity, the Read Evidence of every source
    whose write it settled, so those sources stay published for as long as it
    is reachable. Nothing interprets it.
    """

    steps: tuple[PlannedStep, ...]
    source_evidence: tuple[object, ...] = ()

    @classmethod
    def from_bound(cls, bound: BoundRange, *, source_evidence: tuple[object, ...]) -> SettledWrite:
        """``bound``'s steps and every effect it publishes, settled for the
        write whose sources ``source_evidence`` holds; ``bound`` itself is not
        kept."""
        return cls(
            steps=bound.steps,
            source_evidence=source_evidence,
            changed=bound.changed,
            advanced=bound.advanced,
            destroyed=bound.destroyed,
            removed=bound.removed,
            opened=bound.opened,
            derived=bound.derived,
            current_outputs=bound.current_outputs,
        )


@dataclass(frozen=True, slots=True)
class WriteGroup:
    """Writes that execute and complete together.

    ``steps`` holds their steps in execution order. Each of ``writes``
    completes, in order, only once every one of ``steps`` has succeeded, and
    before any step of a later group executes, so no write of a group may
    depend on another's completion. ``effect_spans`` are the grouped effects
    among ``steps``, in order and never overlapping.
    """

    writes: tuple[SettledWrite, ...]
    steps: tuple[PlannedStep, ...]
    effect_spans: tuple[EffectSpan, ...] = ()

    def __post_init__(self) -> None:
        if not self.writes:
            raise ValueError("a Write Group holds at least one write")
        reached = 0
        for span in self.effect_spans:
            if not reached <= span.start < span.stop - 1 < len(self.steps):
                raise ValueError(
                    "a Write Group's effect spans each hold at least two of its steps, in "
                    "order and never overlapping"
                )
            reached = span.stop

    @classmethod
    def from_writes(
        cls, writes: Iterable[SettledWrite], *, effect_shape: EffectShapeOf
    ) -> WriteGroup:
        """The group of ``writes``: every write's effects laid out shape by
        shape, then every write's inserts, each write's own order kept within
        both. One write keeps its own steps and has no effect spans.

        Effects are laid out in one pass, in blocks of one ``effect_shape``
        each, in the order each block first appears. An effect joins the
        latest block of its shape unless that block precedes the block holding
        its own write's previous effect, in which case it opens a later block
        of that shape. An effect of no shape stands alone as a barrier that no
        later effect is moved across. Each block of two or more becomes an
        :class:`EffectSpan`.

        ``writes`` is consumed as it yields, and a second is asked for only
        once the first is in hand. Where it or the layout fails, the writes
        taken are released here and a suspended producer of them is closed.
        """
        source = iter(writes)
        write: SettledWrite | None = None
        following: SettledWrite | None = None
        assembly: _Layout | None = None
        try:
            write = next(source, None)
            if write is None:
                raise ValueError("a Write Group holds at least one write")
            following = next(source, None)
            if following is None:
                return cls((write,), write.steps)
            assembly = _Layout(effect_shape)
            while write is not None:
                assembly.add(write)
                write, following = following, None
                if write is None:
                    write = next(source, None)
            steps, spans = assembly.finish()
            return cls(tuple(assembly.writes), steps, spans)
        except BaseException:
            write = following = None
            if assembly is not None:
                assembly.release()
            if isinstance(source, Generator):
                source.close()
            raise


class _Layout:
    """A Write Group's steps as its writes are laid out: the effect blocks in
    first-appearance order, the shape of each, the latest block of each shape
    still open to later effects, and every insert, in write order."""

    __slots__ = ("_blocks", "_effect_shape", "_inserts", "_open", "_shapes", "writes")

    def __init__(self, effect_shape: EffectShapeOf) -> None:
        self._effect_shape = effect_shape
        self.writes: list[SettledWrite] = []
        self._blocks: list[list[PlannedStep]] = []
        self._shapes: list[Hashable | None] = []
        self._open: dict[Hashable, int] = {}
        self._inserts: list[PlannedStep] = []

    def add(self, write: SettledWrite) -> None:
        self.writes.append(write)
        blocks, shapes, opened = self._blocks, self._shapes, self._open
        previous = -1
        try:
            for step in write.steps:
                if isinstance(step, PlannedInsert):
                    self._inserts.append(step)
                    continue
                shape = self._effect_shape(step)
                block = None if shape is None else opened.get(shape)
                if block is None or block < previous:
                    block = len(blocks)
                    blocks.append([])
                    shapes.append(shape)
                    if shape is None:
                        opened.clear()
                    else:
                        opened[shape] = block
                blocks[block].append(step)
                previous = block
        except BaseException:
            # A failure's traceback keeps this frame, which must not keep the
            # write and its source evidence once the group releases it.
            del write
            raise

    def finish(self) -> tuple[tuple[PlannedStep, ...], tuple[EffectSpan, ...]]:
        steps: list[PlannedStep] = []
        spans: list[EffectSpan] = []
        for block, shape in zip(self._blocks, self._shapes, strict=True):
            if shape is not None and len(block) > 1:
                spans.append(EffectSpan(len(steps), len(steps) + len(block), shape))
            steps.extend(block)
        steps.extend(self._inserts)
        return tuple(steps), tuple(spans)

    def release(self) -> None:
        self.writes.clear()
        self._blocks.clear()
        self._shapes.clear()
        self._open.clear()
        self._inserts.clear()


type PlanEntry = WriteGroup | AcquisitionSpan
"""One element of a Write Plan: a Write Group, or an acquisition span of
deferred writes, which are grouped only as they are bound."""


@dataclass(frozen=True, slots=True)
class WritePlan:
    """One flush's finalized writes in execution order, entry by entry.

    A plan of no entry is the one canonical result for complete cancellation
    or known no-op elimination; there is no empty-plan sentinel and no second
    result variant.
    """

    entries: tuple[PlanEntry, ...] = ()
