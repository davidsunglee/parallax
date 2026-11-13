from __future__ import annotations

from collections.abc import Callable, Iterable

from parallax.core._execution._write_lowering import stream_physical
from parallax.core.internal.database_binding import ResolvedBinding
from parallax.core.internal.dialect import Dialect
from parallax.core.internal.sql_gen import LoweredStatement
from parallax.core.internal.write_plan.payload import PatchedDocument, WritePayloadPreparer
from parallax.core.internal.write_plan.plan import EffectSpan
from parallax.core.internal.write_plan.steps import (
    PlannedDelete,
    PlannedStep,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)

__all__ = ["SimulatedWriteSteps"]


class SimulatedWriteSteps:
    """A unit of work's step execution with no database behind it: each
    sequence of steps succeeds without running anything, lowering through the
    dry traversal execution's own lowering answers.

    Only the statements of steps that lowered whole are kept, with their
    binds; nothing of the steps themselves is.

    Steps that allocate answer the next of ``allocated_results`` as their
    keys, one tuple per such execution and unchecked; one with none left to
    answer is a misconfigured simulation. A predicate-selected step executed
    for its count (:meth:`counted`) answers the next of ``counts``, or zero
    once none is left: no simulated row is matched. Database gates and
    affected-row enforcement are not simulated. Lowering hands the payloads it
    lowers to the capture hooks a unit of work gives, as execution does.
    """

    __slots__ = (
        "_allocated",
        "_counts",
        "_dialect",
        "_payloads",
        "_resolved",
        "_statements",
    )

    def __init__(
        self,
        payloads: WritePayloadPreparer,
        resolved: ResolvedBinding,
        dialect: Dialect,
        *,
        allocated_results: Iterable[tuple[object, ...]] = (),
        counts: Iterable[int] = (),
    ) -> None:
        self._payloads = payloads
        self._resolved = resolved
        self._dialect = dialect
        self._allocated = iter(allocated_results)
        self._counts = iter(counts)
        self._statements: list[LoweredStatement] = []

    @property
    def statements(self) -> tuple[LoweredStatement, ...]:
        """Every statement the executed steps so far lowered to, in order."""
        return tuple(self._statements)

    def __call__(
        self,
        steps: tuple[PlannedStep, ...],
        /,
        *,
        effect_spans: tuple[EffectSpan, ...] = (),
        allocates: bool,
        capture_insert: Callable[[WriteRow, object | None], None] | None = None,
        capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
        | None = None,
    ) -> tuple[object, ...]:
        lowered = tuple(
            stream_physical(
                steps,
                self._payloads,
                self._resolved,
                self._dialect,
                effect_spans=effect_spans,
                capture_insert=capture_insert,
                capture_revision=capture_revision,
            )
        )
        allocated: tuple[object, ...] = ()
        if allocates:
            scripted = next(self._allocated, None)
            if scripted is None:
                raise ValueError(
                    "simulated steps allocating keys found no scripted result to answer: "
                    "a simulation answers only the keys it is given"
                )
            allocated = scripted
        self._statements.extend(lowered)
        return allocated

    def counted(self, step: PlannedUpdate | PlannedDelete, /) -> int:
        """Execute ``step`` as :meth:`__call__` executes a sequence of one,
        answering the next scripted count."""
        self((step,), allocates=False)
        return next(self._counts, 0)
