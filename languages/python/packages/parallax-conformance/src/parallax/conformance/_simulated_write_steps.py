from __future__ import annotations

from collections.abc import Iterable

from parallax.core._execution._write_lowering import stream_physical
from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.plan import WriteStepView

__all__ = ["SimulatedWriteSteps"]


class SimulatedWriteSteps:
    """A unit of work's step execution with no database behind it: each span
    is lowered once, through the dry traversal execution's own lowering
    answers, and succeeds without running anything.

    Only the statements of a span that lowered whole are kept, with their
    binds; nothing of the span itself is. A span that allocates answers the
    next of ``allocated_results`` as its keys, one tuple per such span and
    unchecked; one with none left to answer is a misconfigured simulation.
    Database gates and affected-row enforcement are not simulated.
    """

    __slots__ = ("_allocated", "_dialect", "_meta", "_payloads", "_statements")

    def __init__(
        self,
        payloads: WritePayloadPreparer,
        meta: Metamodel,
        dialect: Dialect,
        *,
        allocated_results: Iterable[tuple[object, ...]] = (),
    ) -> None:
        self._payloads = payloads
        self._meta = meta
        self._dialect = dialect
        self._allocated = iter(allocated_results)
        self._statements: list[LoweredStatement] = []

    @property
    def statements(self) -> tuple[LoweredStatement, ...]:
        """Every statement the spans executed so far lowered to, in order."""
        return tuple(self._statements)

    def __call__(self, steps: WriteStepView, /, *, allocates: bool) -> tuple[object, ...]:
        lowered = tuple(stream_physical(steps, self._payloads, self._meta, self._dialect))
        allocated: tuple[object, ...] = ()
        if allocates:
            scripted = next(self._allocated, None)
            if scripted is None:
                raise ValueError(
                    "a simulated span allocating keys found no scripted result to answer: "
                    "a simulation answers only the keys it is given"
                )
            allocated = scripted
        self._statements.extend(lowered)
        return allocated
