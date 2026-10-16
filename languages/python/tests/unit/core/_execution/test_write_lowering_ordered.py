"""Which steps ordered write transport may carry, decided before payload demand
(execution's lowering seam, `m-execution`, `m-dialect`).

A count-only temporal effect promises an upper bound on its statement's binds
from the step alone, and qualifies only where that bound fits the dialect's
limit. The promise is checked against what lowering actually produced, so a
statement exceeding it is refused as a lowering failure rather than presented.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from decimal import Decimal
from typing import Final

import pytest

from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._write_lowering import lowered, lowered_within, ordered_bind_bound
from parallax.core.base import INFINITY as OPEN
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.sql_gen import SqlGenError
from parallax.core.write_plan import SUPERSEDED
from parallax.core.write_plan.steps import (
    INFINITY,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    UNGATED,
    ExactCount,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedInsert,
    PlannedRow,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedWrite,
    TemporalGate,
    WriteRow,
)
from tests.unit._corpus_model_support import model
from tests.unit._corpus_model_support import target as entity_of

_T0: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_T1: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _effects(
    entity: EntityIdentity, owner: EntityIdentity, revised: dict[AttributeIdentity, object]
) -> list[PlannedWrite]:
    """Every count-only temporal effect on ``entity``, whose key and temporal
    members ``owner`` declares; its revision assigns ``revised``."""

    def attr(name: str) -> AttributeIdentity:
        return AttributeIdentity(owner, name)

    slot = MilestoneTarget(
        key_attributes=(attr("id"),),
        key_values=(1,),
        end_attributes=(attr("validEnd"), attr("txEnd")),
        end_values=(INFINITY, INFINITY),
    )
    gate = TemporalGate(start_attribute=attr("txStart"), observed_start=_T0)
    return [
        PlannedClose(
            entity=entity,
            target=slot,
            assignments=PlannedAssignments(attributes={attr("txEnd"): _T1}),
            cause=SUPERSEDED,
            concurrency=UNGATED,
            affected_rows=ExactCount(1, STALE_WRITE),
        ),
        PlannedTemporalGuard(
            entity=entity,
            target=slot,
            concurrency=gate,
            affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
        ),
        PlannedTemporalRemoval(
            entity=entity,
            target=slot,
            concurrency=gate,
            affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
        ),
        PlannedTemporalRevision(
            entity=entity,
            target=slot,
            assignments=PlannedAssignments(attributes=revised),
            concurrency=gate,
            affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
        ),
    ]


def _cases() -> list[tuple[str, Metamodel, PlannedWrite]]:
    position = model("position")
    columns = entity_of(position, "Position").identity
    tags = model("scalar-collection-lifecycle-layout-twin-document")
    document = entity_of(tags, "TagSpan").identity
    instrument = model("instrument")
    bond = entity_of(instrument, "Bond").identity
    root = entity_of(instrument, "Instrument").identity
    cases: list[tuple[str, Metamodel, PlannedWrite]] = []
    revisions: tuple[tuple[str, Metamodel, EntityIdentity, EntityIdentity, dict[str, object]], ...]
    revisions = (
        ("columns", position, columns, columns, {"value": Decimal("2.50")}),
        (
            "document",
            tags,
            document,
            document,
            {"amount": 5, "marks": (1, 2, 3), "validStart": _T0},
        ),
        ("table-per-hierarchy", instrument, bond, root, {"price": Decimal("1.00")}),
    )
    for label, meta, entity, owner, revised in revisions:
        assigned: dict[AttributeIdentity, object] = {
            AttributeIdentity(owner, name): value for name, value in revised.items()
        }
        if entity == bond:
            assigned[AttributeIdentity(bond, "coupon")] = Decimal("2.00")
        effects = _effects(entity, owner, assigned)
        cases.extend((f"{label}-{type(step).__name__}", meta, step) for step in effects)
    return cases


@pytest.mark.parametrize(
    ("label", "meta", "step"), _cases(), ids=[label for label, _meta, _step in _cases()]
)
def test_every_temporal_effect_promises_a_bound_its_statement_keeps(
    label: str, meta: Metamodel, step: PlannedWrite
) -> None:
    del label
    bound = ordered_bind_bound(step, POSTGRES)
    assert bound is not None
    statement = lowered_within(step, bound, build_write_planner(meta).payloads, meta, POSTGRES)
    assert len(statement.binds) <= bound
    assert statement == lowered(step, build_write_planner(meta).payloads, meta, POSTGRES)


def test_an_insert_never_qualifies_for_ordered_transport() -> None:
    meta = model("position")
    entity = entity_of(meta, "Position").identity

    def attr(name: str) -> AttributeIdentity:
        return AttributeIdentity(entity, name)

    row = PlannedRow(
        attributes={
            attr("id"): 1,
            attr("acctNum"): "A-1",
            attr("value"): Decimal("1.00"),
            attr("validStart"): _T0,
            attr("validEnd"): OPEN,
            attr("txStart"): _T1,
            attr("txEnd"): OPEN,
        }
    )
    insert = PlannedInsert(entity=entity, entries=(WriteRow(row=row, origin=NEW_LINEAGE),))
    assert ordered_bind_bound(insert, POSTGRES) is None


def test_an_effect_whose_bound_exceeds_the_dialect_limit_runs_alone() -> None:
    meta = model("position")
    entity = entity_of(meta, "Position").identity
    close, guard, *_ = _effects(entity, entity, {AttributeIdentity(entity, "value"): Decimal("1")})
    # A close's bound is six and a guard's five.
    narrow = replace(POSTGRES, max_bind_parameters=5)
    assert ordered_bind_bound(close, narrow) is None
    assert ordered_bind_bound(guard, narrow) == 5


def test_a_statement_exceeding_the_bound_it_promised_is_a_lowering_failure() -> None:
    meta = model("position")
    entity = entity_of(meta, "Position").identity
    close, *_ = _effects(entity, entity, {AttributeIdentity(entity, "value"): Decimal("1")})
    payloads = build_write_planner(meta).payloads
    with pytest.raises(SqlGenError, match="carrying 4 binds exceeds the 3 its shape promised"):
        lowered_within(close, 3, payloads, meta, POSTGRES)
