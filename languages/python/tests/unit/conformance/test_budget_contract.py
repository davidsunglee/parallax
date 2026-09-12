from __future__ import annotations

from pathlib import Path

import pytest

from parallax.conformance.budget import BudgetContract


def test_budget_contract_transcribes_every_absolute_table_cell() -> None:
    contract = BudgetContract.load()
    actual = {
        (cell.workload, cell.path): cell.value
        for workload in contract.workload_ids
        for cell in contract.cells(workload)
    }
    assert actual == {
        ("conventional-fanout", "live.eager.maxMs"): 12.5,
        ("conventional-fanout", "live.eager.minRootsPerSecond"): 16000,
        ("conventional-fanout", "live.page32.maxMs"): 20,
        ("conventional-fanout", "live.page32.minRootsPerSecond"): 10000,
        ("conventional-fanout", "live.page128.maxMs"): 15.5,
        ("conventional-fanout", "live.page128.minRootsPerSecond"): 12903,
        ("conventional-fanout", "firstResult.page1.maxMs"): 1.5,
        ("conventional-fanout", "firstResult.page32.maxMs"): 2.5,
        ("conventional-fanout", "providerFreeCpu.eager.maxMs"): 10.5,
        ("conventional-fanout", "providerFreeCpu.eager.minRootsPerSecond"): 19048,
        ("conventional-fanout", "providerFreeCpu.page32.maxMs"): 13,
        ("conventional-fanout", "providerFreeCpu.page32.minRootsPerSecond"): 15385,
        ("conventional-fanout", "eagerMemory.retainedKiB"): 800,
        ("conventional-fanout", "eagerMemory.peakKiB"): 1350,
        ("conventional-fanout", "streamedMemory.retainedKiB"): 64,
        ("conventional-fanout", "streamedMemory.page1PeakKiB"): 64,
        ("conventional-fanout", "streamedMemory.page32PeakKiB"): 256,
        ("conventional-fanout", "streamedMemory.page128PeakKiB"): 768,
        ("duplicate-include", "live.eager.maxMs"): 18,
        ("duplicate-include", "live.eager.minRootsPerSecond"): 11111,
        ("duplicate-include", "live.page32.maxMs"): 24,
        ("duplicate-include", "live.page32.minRootsPerSecond"): 8333,
        ("duplicate-include", "live.page128.maxMs"): 22,
        ("duplicate-include", "live.page128.minRootsPerSecond"): 9091,
        ("duplicate-include", "firstResult.page1.maxMs"): 1.5,
        ("duplicate-include", "firstResult.page32.maxMs"): 3.0,
        ("duplicate-include", "providerFreeCpu.eager.maxMs"): 14.5,
        ("duplicate-include", "providerFreeCpu.eager.minRootsPerSecond"): 13793,
        ("duplicate-include", "providerFreeCpu.page32.maxMs"): 17,
        ("duplicate-include", "providerFreeCpu.page32.minRootsPerSecond"): 11765,
        ("duplicate-include", "eagerMemory.retainedKiB"): 820,
        ("duplicate-include", "eagerMemory.peakKiB"): 1500,
        ("duplicate-include", "streamedMemory.retainedKiB"): 64,
        ("duplicate-include", "streamedMemory.page1PeakKiB"): 64,
        ("duplicate-include", "streamedMemory.page32PeakKiB"): 320,
        ("duplicate-include", "streamedMemory.page128PeakKiB"): 1100,
        ("document-heavy", "live.eager.maxMs"): 22,
        ("document-heavy", "live.eager.minRootsPerSecond"): 9091,
        ("document-heavy", "live.page32.maxMs"): 28,
        ("document-heavy", "live.page32.minRootsPerSecond"): 7143,
        ("document-heavy", "live.page128.maxMs"): 27,
        ("document-heavy", "live.page128.minRootsPerSecond"): 7407,
        ("document-heavy", "firstResult.page1.maxMs"): 2.0,
        ("document-heavy", "firstResult.page32.maxMs"): 3.5,
        ("document-heavy", "eagerMemory.retainedKiB"): 975,
        ("document-heavy", "eagerMemory.peakKiB"): 1900,
        ("document-heavy", "streamedMemory.retainedKiB"): 64,
        ("document-heavy", "streamedMemory.page1PeakKiB"): 96,
        ("document-heavy", "streamedMemory.page32PeakKiB"): 400,
        ("document-heavy", "streamedMemory.page128PeakKiB"): 1280,
        ("versioned-document", "live.eager.maxMs"): 5.5,
        ("versioned-document", "live.eager.minRootsPerSecond"): 36364,
        ("versioned-document", "live.page32.maxMs"): 8,
        ("versioned-document", "live.page32.minRootsPerSecond"): 25000,
        ("versioned-document", "live.page128.maxMs"): 6.75,
        ("versioned-document", "live.page128.minRootsPerSecond"): 29630,
        ("versioned-document", "firstResult.page1.maxMs"): 0.6,
        ("versioned-document", "firstResult.page32.maxMs"): 1.0,
        ("versioned-document", "eagerMemory.retainedKiB"): 275,
        ("versioned-document", "eagerMemory.peakKiB"): 475,
        ("versioned-document", "streamedMemory.retainedKiB"): 64,
        ("versioned-document", "streamedMemory.page1PeakKiB"): 64,
        ("versioned-document", "streamedMemory.page32PeakKiB"): 144,
        ("versioned-document", "streamedMemory.page128PeakKiB"): 336,
        ("bitemporal-current", "live.eager.maxMs"): 6.5,
        ("bitemporal-current", "live.eager.minRootsPerSecond"): 30769,
        ("bitemporal-current", "live.page32.maxMs"): 10,
        ("bitemporal-current", "live.page32.minRootsPerSecond"): 20000,
        ("bitemporal-current", "live.page128.maxMs"): 8,
        ("bitemporal-current", "live.page128.minRootsPerSecond"): 25000,
        ("bitemporal-current", "firstResult.page1.maxMs"): 1.0,
        ("bitemporal-current", "firstResult.page32.maxMs"): 1.25,
        ("bitemporal-current", "eagerMemory.retainedKiB"): 330,
        ("bitemporal-current", "eagerMemory.peakKiB"): 425,
        ("bitemporal-current", "streamedMemory.retainedKiB"): 64,
        ("bitemporal-current", "streamedMemory.page1PeakKiB"): 64,
        ("bitemporal-current", "streamedMemory.page32PeakKiB"): 144,
        ("bitemporal-current", "streamedMemory.page128PeakKiB"): 352,
        ("stress-columns", "stress.maxUsPerProjection"): 175,
        ("stress-columns", "stress.minProjectionsPerSecond"): 5714,
        ("stress-columns", "stress.retainedBPerProjection"): 2800,
        ("stress-columns", "stress.transientBPerProjection"): 3328,
        ("stress-columns", "stress.peakFor64KiB"): 400,
        ("stress-columns", "stress.preparedSetKiB"): 64,
        ("stress-document", "stress.maxUsPerProjection"): 210,
        ("stress-document", "stress.minProjectionsPerSecond"): 4762,
        ("stress-document", "stress.retainedBPerProjection"): 3200,
        ("stress-document", "stress.transientBPerProjection"): 3328,
        ("stress-document", "stress.peakFor64KiB"): 425,
        ("stress-document", "stress.preparedSetKiB"): 80,
    }


def test_budget_contract_carries_the_authority_and_sampling_protocol() -> None:
    contract = BudgetContract.load()
    assert contract.authority == {
        "machine": "Mac17,4",
        "cpu": "Apple M5",
        "cores": 10,
        "ramGiB": 32,
        "cpython": "3.14.7",
        "postgres": "18.6",
    }
    assert contract.sampling == {
        "timing": {
            "warmups": 3,
            "measured": 9,
            "medianMeetsCeiling": True,
            "secondSlowestMax": 1.25,
        },
        "memory": {
            "children": 3,
            "medianMeetsCeiling": True,
            "individualMax": 1.10,
            "scalingArms": [200, 2000],
            "armGrowthMaxKiB": 16,
        },
    }


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
