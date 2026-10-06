from __future__ import annotations

import datetime as dt

import pytest

from parallax.core import MAX, Attr, Bitemporal, DomainModel, Entity, TxTemporal, attr
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.unit_work import KeyedWrite, PlanningRequest
from parallax.core.unit_work.instructions import PreparedTargetWrite, prepare_typed_write
from parallax.core.write_plan import WritePlan
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    AllocatedOpening,
)
from parallax.core.write_plan.steps import (
    INFINITY,
    RETURNED_MAX_PLUS_ONE,
    Finite,
    PlannedInsert,
    TemporalUpperBound,
)
from parallax.snapshot.handle import build_write_planner, stream_lowered
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY

_NAMESPACE = "allocated.planner"
_MAR, _JUN = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (3, 6))


class Log(TxTemporal, table="log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


class Span(Bitemporal, table="span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


class Plain(Entity, table="plain", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


_META = model_of(DomainModel(Log, Span, Plain))


def _plan(
    entity: type[Entity], *, valid_from: dt.datetime | None = None, until: dt.datetime | None = None
) -> WritePlan:
    prepared = prepare_typed_write(
        KeyedWrite(
            "insertUntil" if until is not None else "insert",
            entity.identity.canonical,
            ({"id": {"computed": "maxPlusOne"}, "amount": 1},),
            valid_from=valid_from,
            until=until,
        ),
        _META,
    )
    assert not isinstance(prepared, PreparedTargetWrite)
    return (
        build_write_planner(_META)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=instant_at("2024-01-10T00:00:00+00:00"),
                concurrency="optimistic",
                buffered_writes=[prepared],
            )
        )
        .plan
    )


@pytest.mark.parametrize(
    ("entity", "bounds", "ends"),
    [
        (Log, {}, TRANSACTION_TIME_ENDS),
        (Span, {"valid_from": _MAR}, OPEN_BITEMPORAL_ENDS),
        (Span, {"valid_from": _MAR, "until": _JUN}, (Finite(instant=_JUN), INFINITY)),
    ],
    ids=["transaction-time", "bitemporal-open", "bitemporal-bounded"],
)
def test_a_temporal_insert_answers_the_key_the_database_allocates(
    entity: type[Entity], bounds: dict[str, dt.datetime], ends: tuple[TemporalUpperBound, ...]
) -> None:
    plan = _plan(entity, **bounds)
    (unit,) = plan.units
    assert unit.opened.allocated == (AllocatedOpening(entity.identity, ends),)
    assert tuple(unit.opened.continued) == ()
    ((step, statement),) = stream_lowered(plan, _META, POSTGRES)
    assert isinstance(step, PlannedInsert)
    assert RETURNED_MAX_PLUS_ONE in step.entries[0].row.attributes.values()
    assert statement.sql.endswith(" returning id")


def test_a_non_temporal_insert_records_no_allocated_row_and_answers_nothing() -> None:
    plan = _plan(Plain)
    (unit,) = plan.units
    assert unit.opened.allocated == ()
    ((_step, statement),) = stream_lowered(plan, _META, POSTGRES)
    assert "returning" not in statement.sql
