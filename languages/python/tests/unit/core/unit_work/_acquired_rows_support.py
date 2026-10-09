"""An in-memory row acquisition answering the rows a database holds, and
deferred ranges read and bound through the unit of work's own acquisition and
binding over it."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from parallax.core import inheritance, temporal_read
from parallax.core.entity._construction_input import ABSENT
from parallax.core.execution._planning import build_write_planner
from parallax.core.metamodel import Metamodel
from parallax.core.temporal_read import valid_time_coverage
from parallax.core.unit_work import TransactionInstant
from parallax.core.unit_work.acquisition import (
    CompletionRequest,
    CoverageReadRequest,
    RowConsumer,
    RowRequest,
)
from parallax.core.unit_work.ranges import DeferredGroupRange
from parallax.core.unit_work.uow import bind_deferred_range
from parallax.core.write_plan import PredecessorRow
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    ExecutionUnit,
    PlannedWrites,
    TemporalWriteOwnership,
    UnitEffects,
)
from parallax.core.write_plan.steps import PlannedWrite
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._positional_row_support import positional_row

__all__ = ["DrivenGroup", "HeldRows", "bind_held", "coverage_read", "drive_group"]


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


def bind_held(
    model: Metamodel,
    unit: ExecutionUnit,
    rows: Sequence[PredecessorRow],
    *,
    transaction_instant: TransactionInstant,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> BoundRange:
    """``unit``'s deferred range bound, as the unit of work binds it at
    execution, to a coverage read finding ``rows`` under ``ownership``."""
    deferred = unit.deferred
    assert deferred is not None
    return bind_deferred_range(
        deferred,
        acquire_rows=HeldRows(model, rows),
        planner=build_write_planner(model),
        ownership=ownership,
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=transaction_instant,
    )


def coverage_read(
    model: Metamodel, unit: ExecutionUnit, *, transaction_instant: TransactionInstant
) -> CoverageReadRequest:
    """The coverage read ``unit``'s deferred range asks for when the unit of
    work binds it, observed as the read is asked for and before any binding."""
    deferred = unit.deferred
    assert deferred is not None
    observed = _ObservedRead()
    with contextlib.suppress(_ObservedRead):
        bind_deferred_range(
            deferred,
            acquire_rows=observed,
            planner=build_write_planner(model),
            ownership=NO_TEMPORAL_WRITE_OWNERSHIP,
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=transaction_instant,
        )
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


@dataclass(frozen=True, slots=True)
class DrivenGroup:
    """What driving one deferred group to exhaustion did: each round's
    writes, in order, every read asked of its acquisition, and the effects it
    finished with."""

    rounds: tuple[PlannedWrites, ...]
    reads: tuple[RowRequest, ...]
    effects: UnitEffects

    @property
    def steps(self) -> list[PlannedWrite]:
        return [step for writes in self.rounds for step in writes]


def drive_group(
    model: Metamodel,
    unit: ExecutionUnit,
    rows: Sequence[PredecessorRow] = (),
    *,
    transaction_instant: TransactionInstant,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> DrivenGroup:
    """``unit``'s deferred group driven as the executor drives it — every round
    pulled until none remains, then finished and closed — each coverage read
    answering the rows of ``rows`` it overlaps under ``ownership``."""
    deferred = unit.deferred
    assert isinstance(deferred, DeferredGroupRange)
    held = HeldRows(model, rows, overlapping=True)
    continuation = build_write_planner(model).continue_group(
        deferred,
        acquire_rows=held,
        ownership=ownership,
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=transaction_instant,
    )
    rounds: list[PlannedWrites] = []
    while (writes := continuation.pull()) is not None:
        rounds.append(writes)
    effects = continuation.finish()
    continuation.close()
    return DrivenGroup(tuple(rounds), tuple(held.requests), effects)
