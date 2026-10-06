"""Stored Sequence Spans and Balances, the observed writes of them, and the
planner and range-binding seams the unchanged-milestone suites drive."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from parallax.core import temporal_read
from parallax.core.base import INFINITY
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    PlanningRequest,
    RetainedObservation,
    buffered_write,
)
from parallax.core.unit_work.instructions import prepare_wire_write
from parallax.core.unit_work.materialized import BufferItem
from parallax.core.unit_work.write_planner import compose_writes
from parallax.core.write_plan import (
    ObjectKey,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
)
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.plan import (
    NO_OWNERSHIP,
    BoundRange,
    ExecutionUnit,
    Ownership,
    WritePlan,
)
from parallax.core.write_plan.steps import (
    PlannedWrite,
)
from parallax.snapshot.handle import build_write_planner
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import model
from tests.unit.core.unit_work._acquired_rows_support import acquired

SPANS = model("buffered-sequence-layout-twin-columns")
BALANCES = model("balance")
SPAN = EntityIdentity("parallax.compatibility", "SequenceSpan")
BALANCE = EntityIdentity("parallax.compatibility", "Balance")
T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
JAN, MAR, APR, MAY, JUN, AUG, OCT, DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 4, 5, 6, 8, 10, 12)
)


def span_row(
    start: dt.datetime, end: object, amount: int, label: str, memo: object = None
) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "amount": amount,
            "label": label,
            "memo": memo,
            "validStart": start,
            "validEnd": end,
            "txStart": T0,
            "txEnd": INFINITY,
        }
    )


def balance_row(value: str) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal(value),
            "txStart": T0,
            "txEnd": INFINITY,
        }
    )


def retained_state(
    meta: Metamodel, entity: EntityIdentity, row: PredecessorRow
) -> RetainedObservation:
    shape = temporal_read.view(meta).shape(entity)
    assert shape is not None
    key = ObjectKey(entity, (("id", 1),))
    state = TemporalStateKey(key, temporal_read.milestone_edge(shape, row, None))
    return RetainedObservation(state, TemporalObservation(predecessor=row), None)


def observed_write(
    meta: Metamodel,
    entity: str,
    mutation: KeyedMutation,
    evidence: RetainedObservation,
    *,
    valid_from: dt.datetime | None = None,
    until: dt.datetime | None = None,
    assigned: Mapping[str, object] | None = None,
    **members: object,
) -> BufferItem:
    prepared = prepare_wire_write(
        KeyedWrite(
            mutation, entity, ({"id": 1, **(assigned or {}), **members},), valid_from, until
        ),
        meta,
    )
    return buffered_write(prepared, evidence)


def planned(
    meta: Metamodel,
    *writes: BufferItem,
    concurrency: str = "optimistic",
    counts_unchanged_rows: bool = True,
    ownership: Ownership = NO_OWNERSHIP,
) -> WritePlan:
    return (
        build_write_planner(meta)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=instant_at("2024-11-01T00:00:00+00:00"),
                concurrency=concurrency,  # type: ignore[arg-type]
                buffered_writes=compose_writes(meta, list(writes)),
                ownership=ownership,
                counts_unchanged_rows=counts_unchanged_rows,
            )
        )
        .plan
    )


def bound_range(
    meta: Metamodel,
    plan: WritePlan,
    rows: Sequence[PredecessorRow],
    *,
    ownership: Ownership = NO_OWNERSHIP,
) -> tuple[ExecutionUnit, BoundRange]:
    (unit,) = plan.units
    deferred = unit.deferred
    assert deferred is not None
    return unit, build_write_planner(meta).bind_deferred(
        deferred,
        acquired(meta, deferred.acquisition, rows),
        ownership=ownership,
        actor_identity=TEST_ACTOR_IDENTITY,
        transaction_instant=instant_at("2024-11-01T00:00:00+00:00"),
    )


def step_kinds(steps: Iterable[PlannedWrite]) -> list[str]:
    return [type(step).__name__ for step in steps]


def opened_windows(steps: Sequence[PlannedWrite]) -> list[tuple[object, object, object]]:
    windows: list[tuple[object, object, object]] = []
    for step in steps:
        if isinstance(step, PlannedInsert):
            (entry,) = step.entries
            cells = {identity.name: value for identity, value in entry.row.attributes.items()}
            windows.append((cells["validStart"], cells["validEnd"], cells["amount"]))
    return windows


__all__ = [
    "APR",
    "AUG",
    "BALANCE",
    "BALANCES",
    "DEC",
    "JAN",
    "JUN",
    "MAR",
    "MAY",
    "OCT",
    "SPAN",
    "SPANS",
    "T0",
    "balance_row",
    "bound_range",
    "observed_write",
    "opened_windows",
    "planned",
    "retained_state",
    "span_row",
    "step_kinds",
]
