from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import snapshot_delivery_overhead as report
from durations import Spans
from interpreter_matrix import CURRENT_MINOR, authority_minor
from parallax.conformance import workloads
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import Diagnostic, validate
from parallax.conformance.cost_envelope import validate as validate_envelope
from parallax.conformance.provision import Provisioner
from parallax.core.metamodel import Metamodel
from snapshot_delivery_overhead import (
    GEOMETRY_GROUP,
    GEOMETRY_METRICS,
    LIVE_WINDOW,
    PLAN_GROUP,
    PLAN_METRICS,
    PLAN_WINDOW,
    PROVIDER_FREE_WINDOW,
    STRESS_WINDOW,
    ChildReading,
    ChildRequest,
    _child_command,  # pyright: ignore[reportPrivateUsage] - child protocol is under test
    addresses,
    build_envelope,
    canary,
    diagnostic,
    expanded_cells,
    expected_readings,
    geometry_cells,
    is_memory_cell,
    plan_cells,
    selection,
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


def test_plan_cells_cover_the_frozen_levels_under_both_layouts_in_their_own_window() -> None:
    cells = plan_cells()
    assert len(cells) == (
        len(workloads.plan_levels()) * len(workloads.STRUCTURAL_LAYOUTS) * len(PLAN_METRICS)
    )
    assert {cell.workload for cell in cells} == {
        f"plan-{level_id}" for level_id in workloads.PLAN_LEVEL_IDS
    }
    for cell in cells:
        assert window_of(cell.path, cell.workload) == PLAN_WINDOW
        assert window_of(cell.path) == PROVIDER_FREE_WINDOW
        assert unit(cell.path) == ("us" if cell.path.endswith(".elapsedUs") else "KiB")
        assert is_memory_cell(cell.path) == (not cell.path.endswith(".elapsedUs"))
        assert expected_readings(BudgetContract.load(), cell.path) == (
            1 if cell.path.endswith(".elapsedUs") else BudgetContract.load().memory_children
        )


def test_addresses_cross_every_runtime_with_contract_and_geometry_cells() -> None:
    contract = BudgetContract.load()
    expected = addresses(contract, ("3.13", "3.14"))
    assert len(expected) == 2 * (
        len(expanded_cells(contract)) + len(geometry_cells()) + len(plan_cells())
    )
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
    assert all(
        reading.window == window_of(reading.cell, reading.workload) for reading in envelope.readings
    )
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


def _documents(document: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    """The JSON objects a diagnostic document lists under ``key``."""
    listed = document[key]
    assert isinstance(listed, list)
    return [cast("Mapping[str, object]", entry) for entry in cast("list[object]", listed)]


def test_a_diagnostic_run_is_printed_and_can_write_over_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    evidence = tmp_path / "portfolio.json"
    evidence.write_text("the committed capture\n", encoding="utf-8")

    with pytest.raises(SystemExit) as refused:
        report.main(["--diagnostic", "--select", "plan-*", "--out", str(evidence)])

    assert refused.value.code == 2
    assert "diagnostic" in capsys.readouterr().err
    assert evidence.read_text(encoding="utf-8") == "the committed capture\n"


def test_a_diagnostic_run_answers_only_the_chosen_addresses_and_is_no_envelope() -> None:
    contract = BudgetContract.load()
    asked: list[ChildRequest] = []

    def runner(request: ChildRequest) -> ChildReading:
        asked.append(request)
        samples = () if is_memory_cell(request.cell) else (1.0,) * request.measured
        return ChildReading(1.0, unit(request.cell), samples)

    document = diagnostic(
        contract, runner, ("3.13",), selection(["plan-*"], ["*.retainedKiB"]), None
    )
    assert document["diagnostic"] is True
    assert document["runtimes"] == ["3.13"]
    assert document["unavailable"] == []
    readings = _documents(document, "readings")
    assert {(r["runtime"], r["workload"], r["cell"]) for r in readings} == {
        ("3.13", cell.workload, cell.path)
        for cell in plan_cells()
        if cell.path.endswith(".retainedKiB")
    }
    assert all(r["window"] == PLAN_WINDOW for r in readings)
    assert {request.workload for request in asked} == {cell.workload for cell in plan_cells()}
    assert "provenance" not in document and "comparisons" not in document
    with pytest.raises(Exception):  # noqa: B017 - any schema or semantic refusal proves it is no envelope
        validate_envelope(document)


def test_a_diagnostic_run_names_live_cells_it_cannot_provision() -> None:
    contract = BudgetContract.load()
    document = diagnostic(
        contract,
        lambda request: ChildReading(1.0, unit(request.cell), (1.0,) * request.measured),
        (CURRENT_MINOR,),
        selection(["conventional-fanout"], ["live.eager.maxMs"]),
        None,
    )
    assert document["readings"] == []
    unavailable = _documents(document, "unavailable")
    assert any(item["code"] == "cell-unprovisioned" for item in unavailable)


def test_selection_matches_workload_and_cell_patterns_and_defaults_to_everything() -> None:
    assert selection([], [])("anything", "any.cell")
    chosen = selection(["read-*", "plan-depth-1"], ["columns.*"])
    assert chosen("read-depth-8", "columns.peakKiB")
    assert chosen("plan-depth-1", "columns.elapsedUs")
    assert not chosen("plan-depth-8", "columns.elapsedUs")
    assert not chosen("read-depth-8", "document.peakKiB")


class _FakePort:
    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[object] = (),
    ) -> list[tuple[str]]:
        del binds, document_reads
        assert sql == "show server_version"
        return [("18.6",)]


class _FakeProvisioner:
    """Records every schema reset a workload asks for and never opens anything."""

    def __init__(self) -> None:
        self.resets: list[str] = []
        self.port = _FakePort()
        self.connection_info = "postgresql://fake"

    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None:
        del fixtures
        self.resets.append(type(model).__name__)


def _measured(spans: Spans | None) -> tuple[list[ChildRequest], _FakeProvisioner, Sequence[str]]:
    contract = BudgetContract.load()
    asked: list[ChildRequest] = []

    def runner(request: ChildRequest) -> ChildReading:
        asked.append(request)
        samples = () if is_memory_cell(request.cell) else (1.0,) * request.measured
        return ChildReading(1.0, unit(request.cell), samples)

    provisioner = _FakeProvisioner()
    envelope = report.measure(
        contract, cast("Provisioner", provisioner), runner, ("3.13", "3.14"), spans=spans
    )
    validate(envelope)
    return asked, provisioner, [f"{r.runtime} {r.workload}.{r.cell}" for r in envelope.readings]


def test_recording_spans_changes_no_request_provisioning_or_reading() -> None:
    plain_requests, plain_provisioner, plain_readings = _measured(None)
    spans = Spans()
    timed_requests, timed_provisioner, timed_readings = _measured(spans)
    assert timed_requests == plain_requests
    assert timed_provisioner.resets == plain_provisioner.resets
    assert timed_readings == plain_readings
    contract = BudgetContract.load()
    assert len(plain_requests) == sum(
        expected_readings(contract, cell)
        for _runtime, _workload, cell in addresses(contract, ("3.13", "3.14"))
    )
    assert [(r.warmups, r.measured) for r in plain_requests] == [
        (contract.timing_warmups, contract.timing_measured)
    ] * len(plain_requests)
    assert plain_provisioner.resets


def test_snapshot_spans_cover_every_workload_and_group_on_every_runtime_with_provisioning() -> None:
    contract = BudgetContract.load()
    spans = Spans()
    _measured(spans)
    workload_spans = [span for span in spans.spans if span.scope == "workload"]
    assert [(span.name, span.labels["runtime"]) for span in workload_spans] == [
        (name, runtime)
        for runtime in ("3.13", "3.14")
        for name in (*contract.workload_ids, GEOMETRY_GROUP, PLAN_GROUP)
    ]
    assert all(span.labels["member"] == report.SUBJECT for span in spans.spans)
    setup_spans = [span for span in spans.spans if span.scope == "setup"]
    assert {span.name for span in setup_spans} == {"provision"}
    provisioned = {(span.labels["workload"], span.labels["roots"]) for span in setup_spans}
    live_workloads = {
        cell.workload for cell in expanded_cells(contract) if report.needs_database(cell.path)
    }
    assert {workload for workload, _roots in provisioned} == live_workloads
    assert {roots for _workload, roots in provisioned} == {
        str(arm) for arm in contract.memory_scaling_arms
    }
    assert {span.scope for span in spans.spans} == {"workload", "setup"}
    assert spans.unavailable == ()


def test_durations_are_recorded_for_a_measurement_and_refused_beside_a_diagnostic_or_canary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for arguments in (
        ["--diagnostic", "--durations", str(tmp_path / "d.json")],
        ["--canary", "--durations", str(tmp_path / "d.json")],
    ):
        with pytest.raises(SystemExit) as refused:
            report.main(arguments)
        assert refused.value.code == 2
        assert "--durations" in capsys.readouterr().err
    assert not (tmp_path / "d.json").exists()
