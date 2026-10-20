from __future__ import annotations

from collections.abc import Iterable, Iterator

from parallax.conformance.simulated_temporal_store import (
    SimulatedStoreError,
    SimulatedTemporalStore,
)
from parallax.core._execution._write_lowering import stream_physical
from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.plan import WriteStepView
from parallax.core.write_plan.steps import PlannedStep

__all__ = ["SimulatedWriteSteps"]


class SimulatedWriteSteps:
    """A unit of work's step execution with no database behind it: each span
    is taken once and succeeds without running anything, changing the rows of
    ``store`` as executing it would change a database's, and lowering through
    the dry traversal execution's own lowering answers where it
    ``record_statements``.

    Only the statements of a span that lowered whole are kept, with their
    binds; nothing of the span itself is. Recording lowers each step after
    applying it to the store, in the one traversal; a lowering failure then
    outranks a store's refusal of the span, which is raised once the span
    lowered whole and leaves the store unchanged from that step on. Without
    recording, nothing is lowered and a store refusal raises at once. Either
    way the store's own transaction answers for what a failed span left.

    A span that allocates answers the next of ``allocated_results`` as its
    keys, one tuple per such span and unchecked; one with none left to answer
    is a misconfigured simulation. A store is never answered keys no database
    allocated, so a simulation with one is given none. Database gates and
    affected-row enforcement are not simulated.
    """

    __slots__ = ("_allocated", "_dialect", "_meta", "_payloads", "_record", "_statements", "_store")

    def __init__(
        self,
        payloads: WritePayloadPreparer,
        meta: Metamodel,
        dialect: Dialect,
        *,
        store: SimulatedTemporalStore | None = None,
        record_statements: bool = True,
        allocated_results: Iterable[tuple[object, ...]] = (),
    ) -> None:
        allocated = tuple(allocated_results)
        if store is None and not record_statements:
            raise ValueError("a simulation with no store to change records the statements it runs")
        if store is not None and allocated:
            raise ValueError(
                "a simulation changing a store answers no scripted keys: no database "
                "allocated them, so no stored row could carry them"
            )
        self._payloads = payloads
        self._meta = meta
        self._dialect = dialect
        self._store = store
        self._record = record_statements
        self._allocated = iter(allocated)
        self._statements: list[LoweredStatement] = []

    @property
    def statements(self) -> tuple[LoweredStatement, ...]:
        """Every statement the spans executed so far lowered to, in order."""
        return tuple(self._statements)

    def __call__(self, steps: WriteStepView, /, *, allocates: bool) -> tuple[object, ...]:
        store = self._store
        lowered: tuple[LoweredStatement, ...] = ()
        if store is None:
            lowered = self._lowered(steps)
        elif self._record:
            applied = _Applied(steps, store, self._meta)
            lowered = self._lowered(applied)
            if applied.refusal is not None:
                raise applied.refusal
        else:
            for step in steps:
                store.apply(self._meta, step)
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

    def _lowered(self, steps: Iterable[PlannedStep]) -> tuple[LoweredStatement, ...]:
        return tuple(stream_physical(steps, self._payloads, self._meta, self._dialect))


class _Applied:
    """One recorded ``span``, each of its steps applied to ``store`` as
    lowering takes it from the one traversal.

    The store's first refusal is kept, with no traceback into the span, and
    stops every later change; any other failure propagates as the step is
    taken."""

    __slots__ = ("_meta", "_store", "refusal", "span")

    def __init__(self, span: WriteStepView, store: SimulatedTemporalStore, meta: Metamodel) -> None:
        self.span = span
        self._store = store
        self._meta = meta
        self.refusal: SimulatedStoreError | None = None

    def __iter__(self) -> Iterator[PlannedStep]:
        for step in self.span:
            if self.refusal is None:
                try:
                    self._store.apply(self._meta, step)
                except SimulatedStoreError as refusal:
                    self.refusal = refusal.with_traceback(None)
            yield step
