"""An in-memory row acquisition answering the rows a database holds, and
deferred ranges read and bound through the unit of work's own acquisition and
binding over it."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from parallax.core import inheritance
from parallax.core.entity._construction_input import ABSENT
from parallax.core.execution._planning import build_write_planner
from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import TransactionInstant
from parallax.core.unit_work.acquisition import CoverageReadRequest, RowConsumer, RowReadRequest
from parallax.core.unit_work.uow import bind_deferred_range
from parallax.core.write_plan import PredecessorRow
from parallax.core.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    BoundRange,
    ExecutionUnit,
    TemporalWriteOwnership,
)
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._positional_row_support import positional_row

__all__ = ["HeldRows", "bind_held", "coverage_read"]


@dataclass(slots=True)
class HeldRows:
    """Every read answering ``rows``, as the database holds them: each
    positional over its target's members, its document beside it where any row
    has one. ``requests`` records each read asked of it, in order."""

    model: Metamodel
    rows: Sequence[PredecessorRow] = ()
    requests: list[RowReadRequest] = field(default_factory=list[RowReadRequest])

    def __call__[Request: RowReadRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        self.requests.append(request)
        view = inheritance.view(self.model).entity(request.entity.identity)
        assert view is not None
        selection = view.member_selection
        positional = [
            positional_row(selection.shape, row.members, absent=ABSENT) for row in self.rows
        ]
        documents = (
            [row.document for row in self.rows]
            if any(row.document is not None for row in self.rows)
            else None
        )
        return consumer(request, selection, iter(positional), ABSENT, documents, len(positional))


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

    request: RowReadRequest | None = None

    def __call__[Request: RowReadRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        del consumer
        self.request = request
        raise self
