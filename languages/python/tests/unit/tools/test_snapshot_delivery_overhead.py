from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

import snapshot_delivery_overhead as report
from interpreter_matrix import CURRENT_MINOR, authority_minor
from parallax.conformance import workloads
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import Diagnostic, validate
from parallax.conformance.workloads import workload_digest
from snapshot_delivery_overhead import (
    GEOMETRY_METRICS,
    LIVE_WINDOW,
    PROVIDER_FREE_WINDOW,
    STRESS_WINDOW,
    ChildReading,
    ChildRequest,
    _child_command,  # pyright: ignore[reportPrivateUsage] - child protocol is under test
    addresses,
    build_envelope,
    canary,
    expanded_cells,
    expected_readings,
    geometry_cells,
    is_memory_cell,
    unit,
    window_of,
)


def test_child_command_carries_the_contract_sampling_counts_and_its_runtime() -> None:
    current = _child_command(
        ChildRequest("workload", "live.eager.maxMs", 17, warmups=5, measured=11)
    )
    other = _child_command(
        ChildRequest("workload", "live.eager.maxMs", 17, warmups=5, measured=11, runtime="9.99")
    )
    assert current[0] == sys.executable
    assert current[-6:] == ["--roots", "17", "--warmups", "5", "--measured", "11"]
    assert other[:6] == ["uv", "run", "--frozen", "--python", "9.99", "python"]
    assert other[-6:] == current[-6:]


def test_geometry_cells_cover_every_level_layout_and_metric() -> None:
    cells = geometry_cells()
    assert len(cells) == (
        len(workloads.GEOMETRY_LEVELS) * len(workloads.STRUCTURAL_LAYOUTS) * len(GEOMETRY_METRICS)
    )
    assert {cell.workload for cell in cells} == {
        f"read-{level.id}" for level in workloads.GEOMETRY_LEVELS
    }
    for cell in cells:
        assert window_of(cell.path) == PROVIDER_FREE_WINDOW
        assert unit(cell.path) == ("us/root" if cell.path.endswith("elapsedUsPerRoot") else "KiB")
        assert is_memory_cell(cell.path) == (not cell.path.endswith("elapsedUsPerRoot"))


def test_addresses_cross_every_runtime_with_contract_and_geometry_cells() -> None:
    contract = BudgetContract.load()
    expected = addresses(contract, ("3.13", "3.14"))
    assert len(expected) == 2 * (len(expanded_cells(contract)) + len(geometry_cells()))
    assert len(set(expected)) == len(expected)
    assert window_of("live.eager.maxMs") == LIVE_WINDOW
    assert window_of("providerFreeCpu.eager.maxMs") == PROVIDER_FREE_WINDOW
    assert window_of("stress.maxUsPerProjection") == STRESS_WINDOW


def _results(
    contract: BudgetContract, runtimes: tuple[str, ...]
) -> dict[tuple[str, str, str], list[ChildReading]]:
    results: dict[tuple[str, str, str], list[ChildReading]] = {}
    for runtime, workload, path in addresses(contract, runtimes):
        count = expected_readings(contract, path)
        samples = () if is_memory_cell(path) else (1.0,) * contract.timing_measured
        results[(runtime, workload, path)] = [
            ChildReading(1.0, unit(path), samples) for _ in range(count)
        ]
    return results


def test_envelope_compares_the_authority_runtime_alone_and_labels_every_reading() -> None:
    contract = BudgetContract.load()
    runtimes = ("3.13", "3.14")
    provenance = replace(
        canary(contract, lambda _request: ChildReading(1.0, "ms", (1.0,) * 9)).provenance,
        dirty=True,
    )
    envelope = build_envelope(contract, provenance, _results(contract, runtimes), runtimes)
    validate(envelope)
    assert envelope.incomplete == () and envelope.errors == ()
    assert {(r.runtime, r.workload, r.cell) for r in envelope.readings} == set(
        addresses(contract, runtimes)
    )
    assert all(reading.window == window_of(reading.cell) for reading in envelope.readings)
    assert {(c.workload, c.cell) for c in envelope.comparisons} == {
        (cell.workload, cell.path) for cell in expanded_cells(contract)
    }
    assert authority_minor(contract.authority) in runtimes
    assert all(comparison.outcome != "unavailable" for comparison in envelope.comparisons)


def test_a_runtime_short_of_a_reading_is_named_and_withholds_every_comparison() -> None:
    contract = BudgetContract.load()
    provenance = replace(
        canary(contract, lambda _request: ChildReading(1.0, "ms", (1.0,) * 9)).provenance,
        dirty=True,
    )
    results = _results(contract, (CURRENT_MINOR,))
    missing = geometry_cells()[0]
    del results[(CURRENT_MINOR, missing.workload, missing.path)]
    envelope = build_envelope(contract, provenance, results, (CURRENT_MINOR,))
    assert envelope.incomplete == (
        Diagnostic(
            "cell-unavailable",
            f"CPython {CURRENT_MINOR} {missing.workload}.{missing.path}: expected "
            f"{expected_readings(contract, missing.path)} isolated reading(s), received 0",
        ),
    )
    assert all(comparison.outcome == "unavailable" for comparison in envelope.comparisons)


# Review Cadence requires a fresh capture whenever an instrument changes, so the
# digest a capture records has to move when one does.
def test_the_evidence_digest_covers_the_instruments_that_took_the_readings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instrument = tmp_path / "snapshot_delivery_reading.py"
    instrument.write_text("# an instrument\n", encoding="utf-8")
    monkeypatch.setattr(report, "INSTRUMENTS", (instrument,))
    original = report.evidence_digest()
    instrument.write_text("# an edited instrument\n", encoding="utf-8")
    assert report.evidence_digest() != original
    assert report.evidence_digest() != workload_digest()
