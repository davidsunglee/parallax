"""An in-memory row acquisition answering the rows a database holds, and
deferred ranges read and bound over it through the Write Groups their
acquisition span yields."""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.acquisition_spans import (
    AcquisitionSpan,
    SpanWriteGroups,
    form_spans,
    write_groups,
)
from parallax.core._execution._unit_work.ranges import DeferredRange
from parallax.core._execution._unit_work.row_acquisition import (
    AcquireRows,
    CompletionRequest,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
)
from parallax.core.internal import inheritance, temporal_read
from parallax.core.internal.entity._construction_input import ABSENT
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.planned_step import PredecessorRow
from parallax.core.internal.planned_step.keys import ObjectStateKey
from parallax.core.internal.planned_step.write_effects import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    TemporalWriteOwnership,
)
from parallax.core.internal.temporal_read import valid_time_coverage
from parallax.core.internal.unit_work import TransactionInstant
from tests._support.bindings import bound_model
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._positional_row_support import positional_row

__all__ = [
    "HeldRows",
    "alone",
    "bind_deferred",
    "bind_held",
    "coverage_read",
    "span_groups",
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
        entity = (
            request.read_key.entity if isinstance(request, CoverageReadRequest) else request.entity
        )
        view = inheritance.inheritance_facet_of(self.model).entity(entity.identity)
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
        read_key = request.read_key
        key = row.members[read_key.key_attribute.name]
        terms = [term for term in request.terms if term.key_value == key]
        windows = [term.valid_time_windows for term in terms if term.valid_time_windows]
        if not terms:
            return False
        if len(windows) != len(terms):
            return True
        shape = temporal_read.temporal_facet_of(self.model).shape(read_key.entity.identity)
        assert shape is not None
        coverage = valid_time_coverage(shape, row, None)
        assert coverage is not None
        return any(window.overlaps(coverage) for named in windows for window in named)


def _never_current(state: ObjectStateKey, read_at: int) -> bool:
    """A freshness judge answering every retained row stale."""
    del state, read_at
    return False


def span_groups(
    model: Metamodel,
    span: AcquisitionSpan,
    acquire_rows: AcquireRows,
    *,
    transaction_instant: TransactionInstant,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
    current: Callable[[ObjectStateKey, int], bool] = _never_current,
) -> SpanWriteGroups:
    """The Write Groups a flush binds ``span``'s deferred writes into,
    reading through ``acquire_rows`` under ``ownership``, their retained rows
    judged by ``current``."""
    planner = build_write_planner(bound_model(model))
    return write_groups(
        span,
        acquire_rows=acquire_rows,
        current=current,
        ownership=ownership,
        audit=planner.audit_decoration(
            actor_identity=TEST_ACTOR_IDENTITY, transaction_instant=transaction_instant
        ),
        payloads=planner.payloads,
    )


def alone(deferred: DeferredRange) -> AcquisitionSpan:
    """The acquisition span of ``deferred`` alone, as formation spans a
    deferred write no neighbour shares with."""
    (span,) = form_spans((deferred,))
    return span


def bind_deferred(
    model: Metamodel,
    span: AcquisitionSpan,
    acquire_rows: AcquireRows,
    *,
    transaction_instant: TransactionInstant,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
    current: Callable[[ObjectStateKey, int], bool] = _never_current,
) -> BoundRange:
    """The one deferred write of ``span`` bound, through its
    :func:`span_groups`: the one write of the one Write Group they answer,
    whose steps are its own."""
    with span_groups(
        model,
        span,
        acquire_rows,
        transaction_instant=transaction_instant,
        ownership=ownership,
        current=current,
    ) as groups:
        (group,) = groups
    (bound,) = group.writes
    assert isinstance(bound, BoundRange)
    assert group.steps is bound.steps
    return bound


def bind_held(
    model: Metamodel,
    span: AcquisitionSpan,
    rows: Sequence[PredecessorRow],
    *,
    transaction_instant: TransactionInstant,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> BoundRange:
    """The one deferred write of ``span`` bound, as the unit of work binds it
    at execution, to a coverage read finding ``rows`` under ``ownership``."""
    return bind_deferred(
        model,
        span,
        HeldRows(model, rows),
        transaction_instant=transaction_instant,
        ownership=ownership,
    )


def coverage_read(
    model: Metamodel, span: AcquisitionSpan, *, transaction_instant: TransactionInstant
) -> CoverageReadRequest:
    """The coverage read the one deferred write of ``span`` asks for when the
    unit of work binds it, observed as the read is asked for and before any
    binding."""
    observed = _ObservedRead()
    with contextlib.suppress(_ObservedRead):
        bind_deferred(model, span, observed, transaction_instant=transaction_instant)
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
