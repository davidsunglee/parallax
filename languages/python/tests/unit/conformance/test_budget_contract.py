from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from cost_report import CANONICAL_PORTFOLIO
from parallax.conformance import case_format
from parallax.conformance.budget import BudgetContract
from parallax.conformance.workloads import workload_digest
from tests.unit import _write_lowering_support as lowering_support


def test_budget_contract_has_one_unique_positive_address_per_cell() -> None:
    contract = BudgetContract.load()
    cells = tuple(cell for workload in contract.workload_ids for cell in contract.cells(workload))
    addresses = tuple((cell.workload, cell.path) for cell in cells)
    assert len(cells) == 90
    assert len(addresses) == len(set(addresses))
    assert all(cell.value > 0 for cell in cells)
    assert set(contract.authority) == {"machine", "cpu", "cores", "ramGiB", "cpython", "postgres"}
    assert set(contract.sampling) == {"timing", "memory"}
    assert contract.timing_warmups == 3
    assert contract.timing_measured == 9
    assert contract.memory_collect_at_page_boundary is True
    assert contract.memory_children == 3
    assert contract.memory_scaling_arms == (200, 2_000)


# Authored contract and workload changes require recapture; the lock digest
# records the capture's dependencies and remains valid across later dependency
# updates, and an instrument edit is judged for comparability beside the evidence.
def test_committed_envelope_digests_match_their_inputs() -> None:
    repo = case_format.find_repo_root()
    portfolio = cast(
        "Mapping[str, object]",
        json.loads((repo / CANONICAL_PORTFOLIO).read_text(encoding="utf-8")),
    )
    members = cast("Sequence[Mapping[str, object]]", portfolio["members"])
    snapshot = next(member for member in members if member["subject"] == "snapshot-delivery")
    write = next(member for member in members if member["subject"] == "write-lowering")
    provenance = cast("Mapping[str, object]", snapshot["provenance"])
    write_provenance = cast("Mapping[str, object]", write["provenance"])

    assert provenance["budgetContractDigest"] == BudgetContract.load().digest
    assert provenance["workloadDigest"] == workload_digest()
    assert write_provenance["workloadDigest"] == lowering_support.write_lowering_digest()
    assert re.fullmatch(r"[0-9a-f]{64}", cast("str", provenance["lockDigest"]))


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


def test_budget_contract_rejects_malformed_sampling_protocols() -> None:
    contract = BudgetContract.load()
    with pytest.raises(ValueError, match=r"sampling\.timing is not a mapping"):
        _ = replace(contract, sampling={"timing": []}).timing_warmups
    with pytest.raises(
        ValueError,
        match=r"sampling\.memory\.children is not a positive integer",
    ):
        _ = replace(contract, sampling={"memory": {"children": 0}}).memory_children
    with pytest.raises(ValueError, match="scalingArms is not a sequence"):
        _ = replace(
            contract,
            sampling={"memory": {"scalingArms": 200}},
        ).memory_scaling_arms
    with pytest.raises(ValueError, match="must contain distinct scaling counts"):
        _ = replace(
            contract,
            sampling={"memory": {"scalingArms": [200, 200]}},
        ).memory_scaling_arms


@pytest.mark.parametrize("value", [None, 1, "true"])
def test_budget_contract_requires_boolean_page_collection(value: object) -> None:
    contract = BudgetContract.load()
    with pytest.raises(ValueError, match="collectAtPageBoundary is not a boolean"):
        _ = replace(
            contract, sampling={"memory": {"collectAtPageBoundary": value}}
        ).memory_collect_at_page_boundary
