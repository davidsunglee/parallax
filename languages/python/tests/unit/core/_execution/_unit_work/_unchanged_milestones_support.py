"""Stored Sequence Spans and Balances, the observed writes of them, and the
planner seam the unchanged-milestone suites drive."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from decimal import Decimal

from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import prepare_wire_write
from parallax.core._execution._unit_work.write_items import AdmittedWrite
from parallax.core.internal import temporal_read
from parallax.core.internal.base import INFINITY
from parallax.core.internal.metamodel import EntityIdentity, Metamodel
from parallax.core.internal.unit_work import (
    KeyedMutation,
    KeyedWriteInstruction,
    RetainedObservation,
    WritePlanningRequest,
    admitted_write,
)
from parallax.core.internal.write_plan import (
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
)
from parallax.core.internal.write_plan.keys import TemporalObjectStateKey
from parallax.core.internal.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    TemporalWriteOwnership,
    WritePlan,
)
from parallax.core.internal.write_plan.steps import (
    PlannedStep,
)
from tests._support.bindings import bound_model
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, admitted_writes
from tests._support.write_preparation import write_preparation_of
from tests.unit._corpus_model_support import model

SPANS = model("buffered-sequence-layout-twin-columns")
BALANCES = model("balance")
SPAN = EntityIdentity("parallax.compatibility", "SequenceSpan")
BALANCE = EntityIdentity("parallax.compatibility", "Balance")
T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
NOW = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
"""The planning attempt's instant, which every row it opened carries."""
JAN, MAR, JUN, OCT, DEC = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 10, 12)
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


def balance_row(value: str, tx_start: dt.datetime = T0) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal(value),
            "txStart": tx_start,
            "txEnd": INFINITY,
        }
    )


def retained_state(
    meta: Metamodel, entity: EntityIdentity, row: PredecessorRow
) -> RetainedObservation:
    shape = temporal_read.temporal_facet_of(meta).shape(entity)
    assert shape is not None
    key = ObjectKey(entity, (("id", 1),))
    state = TemporalObjectStateKey(key, temporal_read.milestone_edge(shape, row, None))
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
) -> AdmittedWrite:
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            mutation, entity, ({"id": 1, **(assigned or {}), **members},), valid_from, until
        ),
        write_preparation_of(meta),
    )
    return admitted_write(prepared, evidence, evidence.key.object)


def planned(
    meta: Metamodel,
    *writes: AdmittedWrite,
    concurrency: str = "optimistic",
    counts_unchanged_rows: bool = True,
    ownership: TemporalWriteOwnership = NO_TEMPORAL_WRITE_OWNERSHIP,
) -> WritePlan:
    return build_write_planner(bound_model(meta)).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant_at(NOW.isoformat()),
            preference=concurrency,  # type: ignore[arg-type]
            composed_writes=admitted_writes(meta, list(writes)),
            ownership=ownership,
            counts_unchanged_rows=counts_unchanged_rows,
        )
    )


def step_kinds(steps: Iterable[PlannedStep]) -> list[str]:
    return [type(step).__name__ for step in steps]


__all__ = [
    "BALANCE",
    "BALANCES",
    "DEC",
    "JAN",
    "JUN",
    "MAR",
    "NOW",
    "OCT",
    "SPAN",
    "SPANS",
    "T0",
    "balance_row",
    "observed_write",
    "planned",
    "retained_state",
    "span_row",
    "step_kinds",
]
