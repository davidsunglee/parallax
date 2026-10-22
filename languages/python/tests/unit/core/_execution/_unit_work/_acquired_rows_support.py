"""An in-memory row acquisition answering the rows a database holds, and
deferred ranges read and bound over it through the unit of work's own scoped
range binding."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from parallax.core import inheritance, temporal_read
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    CompletionRequest,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
)
from parallax.core._execution._unit_work.ranges import DeferredTemporalRange, RangeBindings
from parallax.core.entity._construction_input import ABSENT
from parallax.core.metamodel import Metamodel
from parallax.core.temporal_read import valid_time_coverage
from parallax.core.unit_work import TransactionInstant
from parallax.core.write_plan import PredecessorRow
from parallax.core.write_plan.keys import ObjectStateKey
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    SettledWrite,
    TemporalWriteOwnership,
)
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._positional_row_support import positional_row

__all__ = [
    "HeldRows",
    "bind_deferred",
    "bind_held",
    "coverage_read",
    "never_current",
    "range_bindings",
]


@dataclass(slots=True)
class HeldRows:
    """Every read answering ``rows``, as the database holds them: each
    positional over its target's members, its document beside it where any row
    has one. ``requests`` records each read asked of it, in order.

    A coverage read answers every row, or with ``overlapping`` only the rows
    whose Valid Time overlaps a window it names, as the database answers it."""

    model: Metamodel
    rows: Sequence[PredecessorRow] = ()
    requests: list[RowRequest] = field(default_factory=list[RowRequest])
    overlapping: bool = False

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        self.requests.append(request)
        view = inheritance.view(self.model).entity(request.entity.identity)
        assert view is not None
        selection = view.member_selection
        if isinstance(request, CompletionRequest):
            # The rows a target read answered are already judged whole.
            rows = request.rows
            return consumer(request, selection, iter(rows), ABSENT, request.documents, len(rows))
        held = self.rows
        if self.overlapping and isinstance(request, CoverageReadRequest):
            held = [row for row in held if self._overlaps(request, row)]
        positional = [positional_row(selection.shape, row.members, absent=ABSENT) for row in held]
        documented = any(row.document is not None for row in held)
        documents = [row.document for row in held] if documented else None
        return consumer(request, selection, iter(positional), ABSENT, documents, len(positional))

    def _overlaps(self, request: CoverageReadRequest, row: PredecessorRow) -> bool:
        key = row.members[request.key_attribute.name]
        windows = [term.valid_time_windows for term in request.terms if term.key_value == key]
        if not windows:
            return False
        if not all(windows):
            return True
        shape = temporal_read.view(self.model).shape(request.entity.identity)
        assert shape is not None
        coverage = valid_time_coverage(shape, row, None)
        assert coverage is not None
        return any(window.overlaps(coverage) for named in windows for window in named)


def never_current(state: ObjectStateKey, read_at: int) -> bool:
    """A freshness judge answering every retained row stale."""
    del state, read_at
    return False


def range_bindings(
    model: Metamodel,
    deferred: DeferredTemporalRange,
    acquire_rows: AcquireRows,
    *,
    transaction_instant: TransactionInstant,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
    current: Callable[[ObjectStateKey, int], bool] = never_current,
) -> RangeBindings:
    """The scoped binding a flush binds ``deferred`` through, reading through
    ``acquire_rows`` under ``ownership``, its retained rows judged by
    ``current``."""
    planner = build_write_planner(model)
    return RangeBindings(
        (deferred,),
        acquire_rows=acquire_rows,
        current=current,
        ownership=ownership,
        audit=planner.audit_decoration(
            actor_identity=TEST_ACTOR_IDENTITY, transaction_instant=transaction_instant
        ),
        payloads=planner.payloads,
    )


def bind_deferred(
    model: Metamodel,
    deferred: DeferredTemporalRange,
    acquire_rows: AcquireRows,
    *,
    transaction_instant: TransactionInstant,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
    current: Callable[[ObjectStateKey, int], bool] = never_current,
) -> BoundRange:
    """``deferred`` bound through its :func:`range_bindings`."""
    with range_bindings(
        model,
        deferred,
        acquire_rows,
        transaction_instant=transaction_instant,
        ownership=ownership,
        current=current,
    ) as bindings:
        (bound,) = bindings
    return bound


def bind_held(
    model: Metamodel,
    settled: SettledWrite,
    rows: Sequence[PredecessorRow],
    *,
    transaction_instant: TransactionInstant,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> BoundRange:
    """``settled write``'s deferred range bound, as the unit of work binds it at
    execution, to a coverage read finding ``rows`` under ``ownership``."""
    deferred = settled.deferred
    assert isinstance(deferred, DeferredTemporalRange)
    return bind_deferred(
        model,
        deferred,
        HeldRows(model, rows),
        transaction_instant=transaction_instant,
        ownership=ownership,
    )


def coverage_read(
    model: Metamodel, settled: SettledWrite, *, transaction_instant: TransactionInstant
) -> CoverageReadRequest:
    """The coverage read ``settled write``'s deferred range asks for when the unit of
    work binds it, observed as the read is asked for and before any binding."""
    deferred = settled.deferred
    assert isinstance(deferred, DeferredTemporalRange)
    observed = _ObservedRead()
    with contextlib.suppress(_ObservedRead):
        bind_deferred(model, deferred, observed, transaction_instant=transaction_instant)
    assert isinstance(observed.request, CoverageReadRequest)
    return observed.request


class _ObservedRead(Exception):
    """A row acquisition that records the read asked of it and ends the
    operation that asked."""

    request: RowRequest | None = None

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        del consumer
        self.request = request
        raise self
