from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from parallax.conformance import case_format
from parallax.conformance.budget import BudgetContract
from parallax.conformance.workloads import catalog


def _delivery_fixtures() -> set[Path]:
    root = case_format.find_repo_root() / "core" / "compatibility" / "benchmarks"
    carrying: set[Path] = set()
    for path in root.glob("*.yaml"):
        document = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            continue
        if "objectQuery" in document or "delivery" in document:
            assert "objectQuery" in document and "delivery" in document, path.name
            carrying.add(path.resolve())
    return carrying


def test_catalog_contract_and_delivery_fixtures_are_one_exact_set() -> None:
    contract = BudgetContract.load()
    workloads = catalog()
    assert tuple(workloads) == contract.workload_ids
    assert {
        workload.fixture_path.resolve() for workload in workloads.values()
    } == _delivery_fixtures()
