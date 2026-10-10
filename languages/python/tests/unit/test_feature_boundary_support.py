from __future__ import annotations

import hashlib
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from parallax.core import DomainModel
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.execution._preflight import preflight
from parallax.core.object_query import deserialize
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.read_delivery._read_plan import ReadPlan
from tests.unit import _feature_boundary_support as support


def test_manifest_is_bounded_unique_and_measures_operations() -> None:
    assert len(support.CASES) == 30
    assert len({case.name for case in support.CASES}) == 30
    assert all(case.units == 1 for case in support.CASES)
    assert {case.window for case in support.CASES} == set(support.WINDOW_DESCRIPTIONS)


def test_digest_fingerprints_the_workload_source() -> None:
    assert (
        support.workload_digest() == hashlib.sha256(Path(support.__file__).read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("size", (0, 8, 128))
@pytest.mark.parametrize(
    ("scalar_type", "managed_cycle", "encoded_cycle"),
    (
        ("integer", (0, 1, 2, 3), (0, 1, 2, 3)),
        (
            "string",
            ("value-0", "value-1", "value-2", "value-3"),
            ("value-0", "value-1", "value-2", "value-3"),
        ),
        (
            "decimal",
            (Decimal("0.25"), Decimal("1.25"), Decimal("2.25"), Decimal("3.25")),
            ("0.25", "1.25", "2.25", "3.25"),
        ),
    ),
)
def test_scalar_windows_keep_order_duplicates_and_canonical_values(
    scalar_type: str,
    size: int,
    managed_cycle: tuple[object, ...],
    encoded_cycle: tuple[object, ...],
) -> None:
    with support.driver_for(f"scalar-collection.{scalar_type}.size-{size}.encode") as driver:
        driver.prepare()
        assert driver.run() == encoded_cycle * (size // 4)
    with support.driver_for(f"scalar-collection.{scalar_type}.size-{size}.decode") as driver:
        driver.prepare()
        assert driver.run() == (managed_cycle * (size // 4), ())


_TARGET = "feature.boundary.Holder"
_PREDICATES: Mapping[str, Mapping[str, object]] = {
    "shallow-scalar": {"eq": {"path": f"{_TARGET}.id", "value": 7}},
    "scalar-any": {"any": {"path": f"{_TARGET}.labels", "where": {"eq": {"value": "urgent"}}}},
    "nested-all": {
        "all": {
            "path": f"{_TARGET}.parcels",
            "where": {"any": {"path": "labels", "where": {"eq": {"value": "urgent"}}}},
        }
    },
    "two-hop-to-one": {"eq": {"path": f"{_TARGET}.owner.team.name", "value": "operations"}},
    "quantifier-through-to-one": {
        "any": {"path": f"{_TARGET}.owner.labels", "where": {"eq": {"value": "urgent"}}}
    },
    "subtype-narrowing": {
        "narrow": {
            "path": f"{_TARGET}.vehicle",
            "to": ["feature.boundary.Car"],
            "operand": {"greaterThan": {"path": "seats", "value": 2}},
        }
    },
}


@pytest.mark.parametrize("shape", tuple(_PREDICATES))
def test_typed_binding_resolves_the_independently_authored_predicate(shape: str) -> None:
    with support.driver_for(f"predicate.{shape}.binding") as driver:
        driver.prepare()
        actual = cast("ResolvedObjectQuery", driver.run())
    model = model_of(
        DomainModel(
            support.Team, support.Person, support.Vehicle, support.Car, support.Bike, support.Holder
        )
    )
    canonical = deserialize({"target": _TARGET, "predicate": _PREDICATES[shape]})
    expected = preflight(canonical, model=model, form="graph")
    assert actual == expected


@pytest.mark.parametrize("shape", tuple(_PREDICATES))
def test_cold_plan_compiles_literals_and_resets_the_cache(shape: str) -> None:
    expected_value = {
        "shallow-scalar": 7,
        "two-hop-to-one": "operations",
        "subtype-narrowing": 2,
    }.get(shape, "urgent")
    with support.driver_for(f"predicate.{shape}.cold-plan") as driver:
        driver.prepare()
        first = cast("ReadPlan", driver.run())
        driver.prepare()
        second = cast("ReadPlan", driver.run())
    first_read, _rows = first.root_read()
    second_read, _rows = second.root_read()
    assert first_read is not second_read
    assert first_read.statement == second_read.statement
    assert expected_value in first_read.statement.binds
    assert "feature_holder" in first_read.statement.sql
    assert POSTGRES.to_driver_sql(first_read.statement.sql)


def test_unknown_case_is_refused_before_a_driver_is_created() -> None:
    with pytest.raises(KeyError, match="unknown"), support.driver_for("unknown"):
        pass
