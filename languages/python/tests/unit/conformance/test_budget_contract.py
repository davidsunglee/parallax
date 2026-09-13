from __future__ import annotations

from pathlib import Path

import pytest

from parallax.conformance.budget import BudgetContract


def test_budget_contract_has_one_unique_positive_address_per_cell() -> None:
    contract = BudgetContract.load()
    cells = tuple(cell for workload in contract.workload_ids for cell in contract.cells(workload))
    addresses = tuple((cell.workload, cell.path) for cell in cells)
    assert len(cells) == 90
    assert len(addresses) == len(set(addresses))
    assert all(cell.value > 0 for cell in cells)
    assert set(contract.authority) == {"machine", "cpu", "cores", "ramGiB", "cpython", "postgres"}
    assert set(contract.sampling) == {"timing", "memory"}


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("[]", "not a mapping"),
        ("schemaVersion: 2", "unsupported schemaVersion"),
        (
            "schemaVersion: 1\nauthority: []\nsampling: {}\nworkloads: {x: {}}",
            "authority is not a mapping",
        ),
        (
            "schemaVersion: 1\nauthority: {}\nsampling: []\nworkloads: {x: {}}",
            "sampling is not a mapping",
        ),
        (
            "schemaVersion: 1\nauthority: {}\nsampling: {}\nworkloads: []",
            "workloads is not a non-empty mapping",
        ),
        (
            "schemaVersion: 1\nauthority: {}\nsampling: {}\nworkloads: {x: 1}",
            "every workload is a named mapping",
        ),
    ],
)
def test_budget_contract_rejects_malformed_documents(
    tmp_path: Path, document: str, message: str
) -> None:
    path = tmp_path / f"contract-{message[:4]}.yaml"
    path.write_text(document, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        BudgetContract.load(path)


def test_budget_contract_rejects_missing_fixture_and_non_numeric_cells(tmp_path: Path) -> None:
    missing_fixture = BudgetContract(tmp_path / "contract.yaml", 1, {}, {}, {"x": {}}, "a")
    with pytest.raises(ValueError, match="fixture is not a string"):
        missing_fixture.fixture("x")
    with pytest.raises(ValueError, match="cells is not a mapping"):
        missing_fixture.cells("x")

    invalid_cell = BudgetContract(
        tmp_path / "contract.yaml", 1, {}, {}, {"x": {"cells": {"bad": "value"}}}, "a"
    )
    with pytest.raises(ValueError, match="budget cell must be numeric"):
        invalid_cell.cells("x")
