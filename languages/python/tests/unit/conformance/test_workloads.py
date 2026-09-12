from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from parallax.conformance import case_format
from parallax.conformance.budget import BudgetContract
from parallax.conformance.story_models import ACCOUNT_MODEL, ORDERS_MODEL, Order
from parallax.conformance.workloads import Workload, catalog, workload_digest
from parallax.core import deep_fetch, inheritance
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.sql_gen._compile import compile_read
from parallax.snapshot.handle._preflight import preflight


def test_every_workload_loads_and_compiles_its_query_and_delivery_sizes() -> None:
    for workload in catalog().values():
        assert workload.model.entity(workload.query.target) is not None
        assert workload.page_sizes == tuple(sorted(set(workload.page_sizes)))
        validated = preflight(workload.query, model=workload.model, form="graph")
        plan = deep_fetch.plan(
            validated,
            workload.model,
            projection=deep_fetch.ReadProjectionRequest("all", True),
        )
        compile_read(plan.root, workload.model, POSTGRES, result_form="instance")
        for level in plan.levels:
            if level.is_back_reference:
                continue
            compile_read(level.query_for([0]), workload.model, POSTGRES, result_form="instance")


def test_generated_workloads_preserve_the_fixture_scale_and_fanout() -> None:
    for workload in catalog().values():
        rows = workload.rows(workload.roots)
        assert rows.roots == workload.roots
        assert rows.fanout == workload.fanout
        assert len(rows.entity(rows.root_entity)) == workload.roots


class _MissingInheritance:
    def entity(self, identity: EntityIdentity) -> None:
        return None


def test_class_backed_consumer_must_match_the_complete_fixture_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workload = catalog()["conventional-fanout"]
    workload.validate_class_backed(ORDERS_MODEL, Order.where(Order.all).include(Order.items))
    with pytest.raises(ValueError, match="class-backed query differs"):
        workload.validate_class_backed(ORDERS_MODEL, Order.where(Order.active == True))  # noqa: E712
    with pytest.raises(ValueError, match="class-backed metadata differs"):
        workload.validate_class_backed(ACCOUNT_MODEL)
    descriptor_view = inheritance.view(workload.model)
    views = iter((_MissingInheritance(), descriptor_view))

    def next_view(_model: Metamodel) -> Any:
        return next(views)

    monkeypatch.setattr(inheritance, "view", next_view)
    with pytest.raises(ValueError, match="class-backed facets differ"):
        workload.validate_class_backed(ORDERS_MODEL)


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
    with pytest.raises(ValueError, match="dataset is not a mapping"):
        _ = _workload({}).roots
    with pytest.raises(ValueError, match="malformed generated dataset"):
        _workload({"dataset": {"generate": {}}}).rows(1)
    with pytest.raises(ValueError, match=r"dataset\.generate is not a mapping"):
        _ = _workload({"dataset": {}}).roots
    with pytest.raises(ValueError, match=r"generate\.rows must be positive"):
        _ = _workload({"dataset": {"generate": {"rows": 0}}}).roots
    with pytest.raises(ValueError, match=r"generate\.fanout must be positive"):
        _ = _workload({"dataset": {"generate": {"fanout": 0}}}).fanout
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


def test_catalog_rejects_duplicate_fixture_ownership(tmp_path: Path) -> None:
    contract_path = tmp_path / "a" / "b" / "c" / "contract.yaml"
    fixture = tmp_path / "core" / "compatibility" / "shared.yaml"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("{}", encoding="utf-8")
    contract = BudgetContract(
        contract_path,
        1,
        {},
        {},
        {
            "first": {"fixture": "shared.yaml"},
            "second": {"fixture": "shared.yaml"},
        },
        "a",
    )
    with pytest.raises(
        ValueError,
        match="workloads 'first' and 'second' both own",
    ):
        catalog(contract)
