"""A temporal Position's stored rectangles, observations, and caller-addressed
and observed writes, shared by the admission and range-binding suites."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    RetainedObservation,
    TargetWrite,
    buffered_write,
)
from parallax.core.unit_work.instructions import (
    TargetMutation,
    prepare_wire_write,
)
from parallax.core.unit_work.materialized import (
    ObservedKeyedWrite,
    TargetKeyedWrite,
    target_write,
)
from parallax.core.write_plan import (
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
)
from parallax.core.write_plan.keys import TemporalStateKey
from tests.unit._corpus_model_support import corpus_records, formed

POSITION = formed(corpus_records()["position"])
FAMILIES = inheritance.view(POSITION)
ENTITY = EntityIdentity("parallax.compatibility", "Position")
OBJECT = ObjectKey(ENTITY, (("id", 1),))
T0 = dt.datetime(2023, 12, 1, tzinfo=dt.UTC)
T1 = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
JAN, MAR, JUN, SEP, DEC = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 9, 12))


def rectangle(
    start: dt.datetime, end: object, value: str, tx_start: dt.datetime = T0
) -> PredecessorRow:
    return PredecessorRow(
        members={
            "id": 1,
            "acctNum": "A",
            "value": Decimal(value),
            "validStart": start,
            "validEnd": end,
            "txStart": tx_start,
            "txEnd": INFINITY,
        }
    )


def retained(predecessor: PredecessorRow) -> RetainedObservation:
    observation = TemporalObservation(predecessor=predecessor)
    shape = temporal_read.view(POSITION).shape(ENTITY)
    assert shape is not None
    state = TemporalStateKey(OBJECT, temporal_read.milestone_edge(shape, predecessor, None))
    return RetainedObservation(state, observation, None)


def addressed_write(
    *,
    replaces: bool = False,
    valid_from: dt.datetime = MAR,
    until: dt.datetime | None = SEP,
    tx_start: dt.datetime = T0,
    **members: object,
) -> TargetKeyedWrite:
    mutation: TargetMutation = (
        ("replace" if until is None else "replaceUntil")
        if replaces
        else ("amend" if until is None else "amendUntil")
    )
    return target_write(
        prepare_wire_write(
            TargetWrite(
                mutation,
                "Position",
                {"id": 1, **members},
                if_tx_start=tx_start,
                valid_from=valid_from,
                until=until,
            ),
            POSITION,
        ),
        FAMILIES,
    )


def observed_write(
    mutation: KeyedMutation,
    evidence: RetainedObservation,
    *,
    valid_from: dt.datetime = MAR,
    until: dt.datetime | None = SEP,
    **members: object,
) -> ObservedKeyedWrite:
    prepared = prepare_wire_write(
        KeyedWrite(mutation, "Position", ({"id": 1, **members},), valid_from, until), POSITION
    )
    item = buffered_write(prepared, evidence)
    assert isinstance(item, ObservedKeyedWrite)
    return item


START = retained(rectangle(JAN, JUN, "100.00"))
LATER = retained(rectangle(JUN, INFINITY, "200.00"))
RESTATED = retained(rectangle(JAN, JUN, "100.00", tx_start=T1))
FEB, APR, MAY, JUL, AUG, OCT = (
    dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (2, 4, 5, 7, 8, 10)
)
T = dt.datetime(2024, 10, 1, tzinfo=dt.UTC)
WHOLE = retained(rectangle(JAN, INFINITY, "100.00"))

__all__ = [
    "APR",
    "AUG",
    "DEC",
    "ENTITY",
    "FAMILIES",
    "FEB",
    "JAN",
    "JUL",
    "JUN",
    "LATER",
    "MAR",
    "MAY",
    "OBJECT",
    "OCT",
    "POSITION",
    "RESTATED",
    "SEP",
    "START",
    "T0",
    "T1",
    "WHOLE",
    "T",
    "addressed_write",
    "observed_write",
    "rectangle",
    "retained",
]
