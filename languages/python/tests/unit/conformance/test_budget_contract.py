from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import cost_report
from cost_report import CANONICAL_PORTFOLIO
from parallax.conformance import case_format
from parallax.conformance.budget import (
    BYTE_UNITS,
    GATED_WINDOWS,
    BudgetContract,
    MemoryGate,
    MemoryGates,
    derive_memory_gates,
    memory_ceiling,
    reading_bytes,
)
from parallax.conformance.workloads import ACQUISITION_LEVELS, workload_digest
from tests.unit import _write_lowering_support as lowering_support

AFTER_PORTFOLIO = Path("languages/python/docs/structural-metadata-envelope/after/portfolio.json")


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


# A retained capture keeps the digest measured at its producing commit. The
# Snapshot workload is unchanged and remains current; the authority migration
# changed write-instrument source without a recapture, so verification must name
# that member stale instead of making the historical evidence claim new inputs.
# The producing commits were squash-merged, so whole-portfolio verification runs
# only in a clone that still carries them; the digest facts are checked everywhere.
def test_committed_envelope_digests_preserve_their_provenance() -> None:
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
    assert write_provenance["workloadDigest"] != lowering_support.write_lowering_digest()
    assert re.fullmatch(r"[0-9a-f]{64}", cast("str", provenance["lockDigest"]))
    for member in members:
        commit = cast("str", cast("Mapping[str, object]", member["provenance"])["commit"])
        if cost_report.resolve_commit(commit) is None:
            pytest.skip(f"producing commit {commit} is not in this clone")
    assert cost_report.verify(portfolio) == [
        "the write-lowering envelope's workload digest is stale"
    ]


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
    missing_fixture = BudgetContract(
        tmp_path / "contract.yaml", 1, {}, {}, {"x": {}}, "a", b"authored"
    )
    with pytest.raises(ValueError, match="fixture is not a string"):
        missing_fixture.fixture("x")
    with pytest.raises(ValueError, match="cells is not a mapping"):
        missing_fixture.cells("x")

    invalid_cell = BudgetContract(
        tmp_path / "contract.yaml", 1, {}, {}, {"x": {"cells": {"bad": "value"}}}, "a", b"authored"
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


# --------------------------------------------------------------------------
# The memory gates
# --------------------------------------------------------------------------
def _basis_portfolio(gates: MemoryGates) -> Mapping[str, object]:
    repo = case_format.find_repo_root()
    return cast(
        "Mapping[str, object]",
        json.loads((repo / gates.basis_portfolio).read_text(encoding="utf-8")),
    )


def _basis_addresses(portfolio: Mapping[str, object]) -> dict[tuple[str, str, str], str]:
    """Every byte-unit reading address of a gated window in the basis capture, with its unit."""
    addresses: dict[tuple[str, str, str], str] = {}
    for member in cast("Sequence[Mapping[str, object]]", portfolio["members"]):
        for reading in cast("Sequence[Mapping[str, object]]", member["readings"]):
            unit = str(reading["unit"])
            if unit in BYTE_UNITS and reading.get("window") in GATED_WINDOWS:
                addresses[
                    (str(member["subject"]), str(reading["workload"]), str(reading["cell"]))
                ] = unit
    return addresses


# The gates are the byte readings of the retained capture the file names as its
# basis under one rule, and the rule is executable: a gate edited by hand, a
# gate missing for a basis address, or a gate for an address the basis never
# read fails here, so the ceilings the cost class blocks on are never a
# transcription.
def test_every_memory_gate_is_the_basis_reading_under_the_stated_rule() -> None:
    gates = MemoryGates.load()
    portfolio = _basis_portfolio(gates)
    assert gates.basis_portfolio == CANONICAL_PORTFOLIO
    assert gates.headroom == 1.10
    assert gates.document() == derive_memory_gates(portfolio, gates.headroom)
    basis = _basis_addresses(portfolio)
    assert set(gates.addresses) == set(basis)
    assert len(gates.addresses) == len(set(gates.addresses)) == 154
    for gate in gates.gates:
        assert gate.unit == basis[(gate.subject, gate.workload, gate.cell)]
        assert gate.max_bytes > 0
    windows = {
        str(reading.get("window"))
        for member in cast("Sequence[Mapping[str, object]]", portfolio["members"])
        for reading in cast("Sequence[Mapping[str, object]]", member["readings"])
    }
    assert GATED_WINDOWS.issubset(windows)


# The retained `after/` capture carries the legacy counter names on every keyed
# case and both runtimes; renaming all 184 of them to the current vocabulary
# derives exactly the ceilings the unrenamed file derives, because the rule
# reads byte units alone and a `calls.*` cell is neither a gate nor a change
# to one.
def test_the_derivation_is_indifferent_to_the_counter_vocabulary() -> None:
    repo = case_format.find_repo_root()
    after = cast(
        "Mapping[str, object]",
        json.loads((repo / AFTER_PORTFOLIO).read_text(encoding="utf-8")),
    )
    renamed_portfolio = json.loads(json.dumps(after))
    renamed = {
        "calls.encodeDocument": "calls.encodeManagedDocument",
        "calls.encodeMany": "calls.encodeManagedMany",
    }
    counters = 0
    for member in cast("Sequence[dict[str, object]]", renamed_portfolio["members"]):
        for reading in cast("Sequence[dict[str, object]]", member["readings"]):
            cell = str(reading["cell"])
            if cell in renamed:
                reading["cell"] = renamed[cell]
                counters += 1
    assert counters == 2 * 46 * 2
    derived = derive_memory_gates(renamed_portfolio, 1.10)
    assert derived == derive_memory_gates(after, 1.10)
    assert sum(len(cells) for workloads in derived.values() for cells in workloads.values()) == 154


def test_the_derivation_rule_is_the_largest_runtime_reading_scaled_and_rounded_up() -> None:
    assert reading_bytes(1.5, "KiB") == 1_536.0
    assert reading_bytes(1_536.0, "B/row") == 1_536.0
    assert reading_bytes(1_536.0, "B") == 1_536.0
    with pytest.raises(ValueError, match="not a byte unit"):
        reading_bytes(1.0, "ms")
    assert memory_ceiling([3_618.0, 3_674.0], "B/row", 1.10) == 4_042
    assert memory_ceiling([50.8359375, 51.09375], "KiB", 1.10) == 57_552
    assert memory_ceiling([110.0], "B/row", 1.10) == 121
    gate = MemoryGate("s", "w", "c.retainedKiB", "KiB", 57_552)
    assert gate.within(56.2)
    assert not gate.within(56.3)


def test_the_derivation_reads_only_byte_units_of_gated_windows_and_one_unit_per_address() -> None:
    def reading(
        workload: str, cell: str, unit: str, value: float, window: str, runtime: str
    ) -> dict[str, object]:
        return {
            "workload": workload,
            "cell": cell,
            "unit": unit,
            "value": value,
            "window": window,
            "runtime": runtime,
        }

    portfolio = {
        "members": [
            {
                "subject": "write-lowering",
                "readings": [
                    reading("w", "retainedBytes", "B/row", 100.0, "keyed-write", "3.13"),
                    reading("w", "retainedBytes", "B/row", 110.0, "keyed-write", "3.14"),
                    reading("w", "elapsedUs", "us/row", 5.0, "keyed-write", "3.14"),
                    reading("w", "calls.applyPatches", "calls/row", 1.0, "keyed-write", "3.14"),
                ],
            },
            {
                "subject": "snapshot-delivery",
                "readings": [
                    reading(
                        "read-x", "columns.peakKiB", "KiB", 2.0, "provider-free-delivery", "3.14"
                    ),
                    reading("stress-x", "stress.peakFor64KiB", "KiB", 400.0, "positional", "3.14"),
                ],
            },
        ]
    }
    assert derive_memory_gates(portfolio, 1.10) == {
        "write-lowering": {"w": {"retainedBytes": {"unit": "B/row", "maxBytes": 121}}},
        "snapshot-delivery": {"read-x": {"columns.peakKiB": {"unit": "KiB", "maxBytes": 2_253}}},
    }
    mixed = {
        "members": [
            {
                "subject": "write-lowering",
                "readings": [
                    reading("w", "retainedBytes", "B/row", 100.0, "keyed-write", "3.13"),
                    reading("w", "retainedBytes", "B", 110.0, "keyed-write", "3.14"),
                ],
            }
        ]
    }
    with pytest.raises(ValueError, match="more than one unit"):
        derive_memory_gates(mixed, 1.10)
    unnumbered = {
        "members": [
            {
                "subject": "write-lowering",
                "readings": [reading("w", "retainedBytes", "B/row", True, "keyed-write", "3.13")],
            }
        ]
    }
    with pytest.raises(TypeError, match="not a number"):
        derive_memory_gates(unnumbered, 1.10)


# Timing never gates; the allowances the report reads a delta against are stated
# beside the gates so one document carries the whole memory-versus-timing
# policy, and pinned to the report's own constants so neither drifts.
def test_the_advisory_allowances_beside_the_gates_are_the_reports_own() -> None:
    gates = MemoryGates.load()
    assert gates.advisory == {
        "timingNoiseAllowance": cost_report.TIMING_NOISE_ALLOWANCE,
        "memoryNoiseAllowance": cost_report.MEMORY_NOISE_ALLOWANCE,
        "timingNoiseFloor": 0.15,
    }
    readme = (
        case_format.find_repo_root()
        / "languages/python/docs/structural-metadata-envelope/README.md"
    ).read_text(encoding="utf-8")
    assert "roughly ±15%" in readme


def test_the_scaling_domains_order_the_acquisition_levels_per_layout() -> None:
    gates = MemoryGates.load()
    assert [domain.name for domain in gates.scaling] == [
        "acquisition.columns",
        "acquisition.document",
    ]
    for domain in gates.scaling:
        layout = domain.name.removeprefix("acquisition.")
        assert domain.subject == "write-lowering"
        assert domain.ordered == tuple(
            f"acquisition.{level.id}.{layout}" for level in ACQUISITION_LEVELS
        )
        assert domain.non_increasing == ("retainedBytes", "transientBytes")
        for workload in domain.ordered:
            for cell in domain.non_increasing:
                assert gates.gate(domain.subject, workload, cell).unit == "B/row"
    assert gates.subject_gates("write-lowering")
    assert gates.workload_gates("snapshot-delivery", "plan-depth-1")
    with pytest.raises(KeyError, match="no memory gate"):
        gates.gate("write-lowering", "unknown", "retainedBytes")


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("[]", "not a mapping"),
        ("schemaVersion: 2", "unsupported schemaVersion"),
        ("schemaVersion: 1\nbasis: []", "basis is not a mapping"),
        ("schemaVersion: 1\nbasis: {headroom: 1.1}", "basis.portfolio is not a path"),
        ("schemaVersion: 1\nbasis: {portfolio: p, headroom: 0.9}", "headroom is not a factor"),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: []",
            "advisory is not a mapping",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {x: no}",
            "every advisory allowance is a named number",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\ngates: {}",
            "gates is not a non-empty mapping",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\ngates: {s: 1}",
            "every gated subject is a named mapping",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
            "gates: {s: {w: 1}}",
            "every gated workload is a named mapping",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
            "gates: {s: {w: {c: 1}}}",
            "every gate is a named mapping",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
            "gates: {s: {w: {c: {unit: ms, maxBytes: 1}}}}",
            "unit is not a byte unit",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
            "gates: {s: {w: {c: {unit: B, maxBytes: 0}}}}",
            "maxBytes is not a positive integer",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
            "gates: {s: {w: {c: {unit: B, maxBytes: 1}}}}\nscaling: []",
            "scaling is not a mapping",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
            "gates: {s: {w: {c: {unit: B, maxBytes: 1}}}}\nscaling: {d: 1}",
            "every scaling domain is a named mapping",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
            "gates: {s: {w: {c: {unit: B, maxBytes: 1}}}}\nscaling: {d: {ordered: [a, b]}}",
            "subject is not a string",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
            "gates: {s: {w: {c: {unit: B, maxBytes: 1}}}}\n"
            "scaling: {d: {subject: s, ordered: [a], nonIncreasing: [c]}}",
            "ordered names fewer than 2 cells",
        ),
        (
            "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {}\n"
            "gates: {s: {w: {c: {unit: B, maxBytes: 1}}}}\n"
            "scaling: {d: {subject: s, ordered: [a, b], nonIncreasing: c}}",
            "nonIncreasing names fewer than 1 cells",
        ),
    ],
)
def test_memory_gates_reject_malformed_documents(
    tmp_path: Path, document: str, message: str
) -> None:
    path = tmp_path / "memory-gates.yaml"
    path.write_text(document, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        MemoryGates.from_bytes(path, document.encode("utf-8"))


def test_memory_gates_without_a_scaling_block_load_with_no_domains(tmp_path: Path) -> None:
    document = (
        "schemaVersion: 1\nbasis: {portfolio: p, headroom: 1.1}\nadvisory: {a: 0.5}\n"
        "gates: {s: {w: {c: {unit: KiB, maxBytes: 2048}}}}\n"
    )
    path = tmp_path / "memory-gates.yaml"
    gates = MemoryGates.from_bytes(path, document.encode("utf-8"))
    assert gates.scaling == ()
    assert gates.advisory == {"a": 0.5}
    assert gates.gates == (MemoryGate("s", "w", "c", "KiB", 2_048),)
    assert gates.gate("s", "w", "c").within(2.0)
    assert gates.digest != MemoryGates.load().digest
