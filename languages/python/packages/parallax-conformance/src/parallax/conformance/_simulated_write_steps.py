from __future__ import annotations

from collections.abc import Callable, Iterable

from parallax.conformance.simulated_temporal_store import (
    SimulatedStoreError,
    SimulatedTemporalStore,
)
from parallax.core._execution._write_lowering import stream_physical
from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel
from parallax.core.sql_gen import LoweredStatement
from parallax.core.write_plan.payload import PatchedDocument, WritePayloadPreparer
from parallax.core.write_plan.steps import (
    PlannedDelete,
    PlannedStep,
    PlannedTemporalRevision,
    PlannedUpdate,
    WriteRow,
)

__all__ = ["SimulatedWriteSteps"]


class SimulatedWriteSteps:
    """A unit of work's step execution with no database behind it: each
    sequence of steps succeeds without running anything, changing the rows of
    ``store`` as executing it would change a database's, and lowering through
    the dry traversal execution's own lowering answers where it
    ``record_statements``.

    Only the statements of steps that lowered whole are kept, with their
    binds; nothing of the steps themselves is. Recording lowers every step
    before any is applied to the store, so a lowering failure leaves the store
    unchanged and outranks a store's refusal. A refusal stops the store's
    changes from the step it refused on and is raised once the steps lowered
    whole; without recording, nothing is lowered. Either way the store's own
    transaction answers for what failed steps left.

    Steps that allocate answer the next of ``allocated_results`` as their
    keys, one tuple per such execution and unchecked; one with none left to
    answer is a misconfigured simulation. A predicate-selected step executed
    for its count (:meth:`counted`) answers the next of ``counts``, or zero
    once none is left: no simulated row is matched. A store is never answered keys no
    database allocated, so a simulation with one is given none. Database gates
    and affected-row enforcement are not simulated. Recording hands the
    payloads it lowers to the capture hooks a unit of work gives, as execution
    does; without recording nothing is captured.
    """

    __slots__ = (
        "_allocated",
        "_counts",
        "_dialect",
        "_meta",
        "_payloads",
        "_record",
        "_statements",
        "_store",
    )

    def __init__(
        self,
        payloads: WritePayloadPreparer,
        meta: Metamodel,
        dialect: Dialect,
        *,
        store: SimulatedTemporalStore | None = None,
        record_statements: bool = True,
        allocated_results: Iterable[tuple[object, ...]] = (),
        counts: Iterable[int] = (),
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
        allocates: bool,
        capture_insert: Callable[[WriteRow, object | None], None] | None = None,
        capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
        | None = None,
    ) -> tuple[object, ...]:
        lowered: tuple[LoweredStatement, ...] = ()
        if self._record:
            lowered = tuple(
                stream_physical(
                    steps,
                    self._payloads,
                    self._meta,
                    self._dialect,
                    capture_insert=capture_insert,
                    capture_revision=capture_revision,
                )
            )
        store = self._store
        if store is not None:
            refusal = _first_refusal(store, self._meta, steps)
            if refusal is not None:
                raise refusal
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


def _first_refusal(
    store: SimulatedTemporalStore, meta: Metamodel, steps: tuple[PlannedStep, ...]
) -> SimulatedStoreError | None:
    for step in steps:
        try:
            store.apply(meta, step)
        except SimulatedStoreError as refusal:
            return refusal.with_traceback(None)
    return None
