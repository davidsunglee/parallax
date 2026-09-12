from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from parallax.conformance import case_format
from parallax.conformance.budget import BudgetContract
from parallax.conformance.workloads import Workload, catalog, workload_digest
from parallax.core.metamodel import Metamodel


def test_every_workload_loads_its_model_query_and_delivery_sizes() -> None:
    for workload in catalog().values():
        assert workload.model.entity(workload.query.target) is not None
        assert workload.page_sizes == (1, 32, 128)


def test_generated_workloads_preserve_the_fixture_scale_and_fanout() -> None:
    workloads = catalog()
    for workload_id, expected_fanout in {
        "conventional-fanout": 5,
        "duplicate-include": 5,
        "document-heavy": 5,
        "versioned-document": 1,
        "bitemporal-current": 1,
        "stress-columns": 4,
        "stress-document": 4,
    }.items():
        rows = workloads[workload_id].rows(200)
        assert rows.roots == 200
        assert rows.fanout == expected_fanout
        assert len(rows.entity(rows.root_entity)) == 200


def test_workload_digest_covers_the_catalog_inputs() -> None:
    digest = workload_digest()
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert workload_digest(catalog()) == digest


def test_orders_tree_rows_are_lazy_sequences_with_exact_relationship_keys() -> None:
    rows = catalog()["conventional-fanout"].rows(3)
    orders = rows.entity("parallax.compatibility.Order")
    items = rows.entity("parallax.compatibility.OrderItem")
    statuses = rows.entity("parallax.compatibility.OrderStatus")
    assert orders[-1]["id"] == 3
    assert [row["id"] for row in orders[1:3]] == [2, 3]
    assert items[5]["orderId"] == 2
    assert statuses[25]["orderId"] == 2
    assert statuses[25]["orderItemId"] == 6
    assert len(tuple(statuses)) == 75
    assert rows.entity("missing") == ()
    with pytest.raises(IndexError):
        _ = orders[3]


def _workload(document: Mapping[str, object]) -> Workload:
    fixture = (
        case_format.find_repo_root() / "core" / "compatibility" / "benchmarks" / "synthetic.yaml"
    )
    return Workload("synthetic", fixture, document)


@pytest.mark.parametrize("recipe", ["accounts-sequential", "document-milestones"])
def test_legacy_recipe_names_remain_available_to_fixture_consumers(recipe: str) -> None:
    workload = _workload({"dataset": {"generate": {"rows": 2, "recipe": recipe}}})
    rows = workload.rows(2)
    assert len(rows.entity(rows.root_entity)) == 2


class _Provisioner:
    def __init__(self) -> None:
        self.rows: Mapping[str, object] | None = None

    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None:
        assert any(
            entity.identity.canonical == "parallax.compatibility.Order" for entity in model.entities
        )
        self.rows = fixtures


def test_inline_rows_can_be_scaled_down_and_provisioned() -> None:
    workload = _workload(
        {
            "model": "models/orders.yaml",
            "dataset": {"rows": {"parallax.compatibility.Order": [{"id": 1}]}},
            "objectQuery": {"target": "parallax.compatibility.Order", "predicate": {"all": {}}},
            "delivery": {"pageSizes": [1]},
        }
    )
    rows = workload.rows(1)
    assert rows.entity(rows.root_entity) == ({"id": 1},)
    provisioner = _Provisioner()
    workload.provision(provisioner, 1)
    assert provisioner.rows is not None
    with pytest.raises(ValueError, match="inline dataset has only 1 roots"):
        workload.rows(2)


def test_workload_reports_malformed_fixture_members() -> None:
    with pytest.raises(ValueError, match="positive built-in int"):
        catalog()["conventional-fanout"].rows(0)
    with pytest.raises(ValueError, match="pageSizes is not an array"):
        _ = _workload({"delivery": "bad"}).page_sizes
    with pytest.raises(ValueError, match="positive integers"):
        _ = _workload({"delivery": {"pageSizes": [0]}}).page_sizes
    with pytest.raises(ValueError, match="model is not a string"):
        _ = _workload({}).model_path
    with pytest.raises(ValueError, match="objectQuery is not a mapping"):
        _ = _workload({}).query
    with pytest.raises(ValueError, match="dataset is not a mapping"):
        _workload({}).rows(1)
    with pytest.raises(ValueError, match="malformed generated dataset"):
        _workload({"dataset": {"generate": {}}}).rows(1)
    with pytest.raises(ValueError, match="dataset has no rows or generator"):
        _workload({"dataset": {}}).rows(1)
    with pytest.raises(ValueError, match="unknown benchmark dataset recipe"):
        _workload({"dataset": {"generate": {"recipe": "unknown"}}}).rows(1)


def test_catalog_rejects_a_fixture_that_is_not_a_mapping(tmp_path: Path) -> None:
    contract_path = tmp_path / "a" / "b" / "c" / "contract.yaml"
    fixture = tmp_path / "core" / "compatibility" / "bad.yaml"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("[]", encoding="utf-8")
    contract = BudgetContract(
        contract_path,
        1,
        {},
        {},
        {"bad": {"fixture": "bad.yaml"}},
        "a",
    )
    with pytest.raises(ValueError, match="benchmark fixture is not a mapping"):
        catalog(contract)
