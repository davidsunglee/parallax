from __future__ import annotations

import json
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
    CONTROL_GROUP,
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
    control_cells,
    diagnostic,
    expanded_cells,
    expected_readings,
    geometry_cells,
    is_memory_cell,
    plan_cells,
    selection,
    unit,
    window_of,
    workload_selection,
)
from tests.unit import _delivery_control_support as control_support


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
        len(expanded_cells(contract))
        + len(geometry_cells())
        + len(plan_cells())
        + len(control_cells(contract))
    )
    assert len(set(expected)) == len(expected)
    without = addresses(contract, ("3.13", "3.14"), controls=False)
    assert set(without) == set(expected) - {
        address for address in expected if address[1].startswith(report.CONTROL_PREFIX)
    }
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

    def close(self) -> None:
        self.resets.append("closed")


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
        for name in (*contract.workload_ids, GEOMETRY_GROUP, PLAN_GROUP, CONTROL_GROUP)
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


# --------------------------------------------------------------------------- #
# Workload selection: a slice of the matrix as evidence, never a diagnostic    #
# --------------------------------------------------------------------------- #
def test_workload_selection_names_exact_contract_ids_and_the_three_groups() -> None:
    contract = BudgetContract.load()
    assert workload_selection([], contract) is report.every_cell
    first = contract.workload_ids[0]
    chosen = workload_selection([first, PLAN_GROUP], contract)
    assert chosen(first, "live.eager.maxMs")
    assert not chosen(contract.workload_ids[1], "live.eager.maxMs")
    assert all(chosen(cell.workload, cell.path) for cell in plan_cells())
    assert not any(chosen(cell.workload, cell.path) for cell in geometry_cells())
    assert not any(chosen(cell.workload, cell.path) for cell in control_cells(contract))
    controls = workload_selection([CONTROL_GROUP], contract)
    assert all(controls(cell.workload, cell.path) for cell in control_cells(contract))
    assert not any(controls(cell.workload, cell.path) for cell in plan_cells())
    geometry = workload_selection([GEOMETRY_GROUP], contract)
    assert all(geometry(cell.workload, cell.path) for cell in geometry_cells())
    assert not geometry(first, "live.eager.maxMs")
    with pytest.raises(ValueError, match="unknown workload read-depth-1, unknown"):
        workload_selection(["unknown", "read-depth-1", first], contract)
    assert report.workload_names(contract) == (
        *contract.workload_ids,
        GEOMETRY_GROUP,
        PLAN_GROUP,
        CONTROL_GROUP,
    )


def _measured_selection(
    selected: report.Selection,
) -> tuple[list[ChildRequest], _FakeProvisioner, report.CostReportEnvelope]:
    contract = BudgetContract.load()
    asked: list[ChildRequest] = []

    def runner(request: ChildRequest) -> ChildReading:
        asked.append(request)
        samples = () if is_memory_cell(request.cell) else (1.0,) * request.measured
        return ChildReading(1.0, unit(request.cell), samples)

    provisioner = _FakeProvisioner()
    envelope = report.measure(
        contract, cast("Provisioner", provisioner), runner, ("3.13", "3.14"), selected=selected
    )
    validate(envelope)
    return asked, provisioner, envelope


def test_a_selected_measurement_reads_and_compares_the_selected_addresses_alone() -> None:
    contract = BudgetContract.load()
    first = contract.workload_ids[0]
    chosen = workload_selection([first, GEOMETRY_GROUP], contract)
    asked, provisioner, envelope = _measured_selection(chosen)
    expected = report.selected_addresses(contract, ("3.13", "3.14"), chosen)
    assert {(r.runtime, r.workload, r.cell) for r in envelope.readings} == set(expected)
    assert envelope.incomplete == () and envelope.errors == ()
    assert {(c.workload, c.cell) for c in envelope.comparisons} == {
        (cell.workload, cell.path) for cell in expanded_cells(contract) if cell.workload == first
    }
    assert all(comparison.outcome != "unavailable" for comparison in envelope.comparisons)
    assert {(request.workload, request.cell) for request in asked} == {
        (workload, cell) for _runtime, workload, cell in expected
    }
    assert len(asked) == sum(expected_readings(contract, cell) for _r, _w, cell in expected)
    assert provisioner.resets == [type(workloads.catalog(contract)[first].model).__name__] * (
        len(contract.memory_scaling_arms) * 2
    )
    assert "provenance" in envelope.document()


def test_a_workload_split_over_every_name_covers_the_whole_matrix_exactly_once() -> None:
    contract = BudgetContract.load()
    whole_requests, _provisioner, whole = _measured_selection(report.every_cell)
    sliced: list[ChildRequest] = []
    readings: list[tuple[str | None, str, str]] = []
    for name in report.workload_names(contract):
        asked, _provisioner, envelope = _measured_selection(workload_selection([name], contract))
        sliced += asked
        readings += [(r.runtime, r.workload, r.cell) for r in envelope.readings]
    assert sorted(map(repr, sliced)) == sorted(map(repr, whole_requests))
    assert sorted(readings) == sorted((r.runtime, r.workload, r.cell) for r in whole.readings)
    assert len(readings) == len(set(readings))


def test_selection_spans_cover_only_the_selected_workloads_and_groups() -> None:
    contract = BudgetContract.load()
    spans = Spans()
    first = contract.workload_ids[-1]
    provisioner = _FakeProvisioner()
    report.measure(
        contract,
        cast("Provisioner", provisioner),
        lambda request: ChildReading(
            1.0, unit(request.cell), () if is_memory_cell(request.cell) else (1.0,) * 9
        ),
        ("3.14",),
        spans=spans,
        selected=workload_selection([first, PLAN_GROUP], contract),
    )
    assert [
        (span.name, span.labels["runtime"]) for span in spans.spans if span.scope == "workload"
    ] == [
        (first, "3.14"),
        (PLAN_GROUP, "3.14"),
    ]


def test_a_workload_slice_is_selected_evidence_and_never_a_diagnostic_or_canary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(*_arguments: object, **_options: object) -> None:
        raise AssertionError("no measurement may start")

    monkeypatch.setattr(report, "Provisioner", never)
    for arguments in (
        ["--diagnostic", "--workload", "plan"],
        ["--canary", "--workload", "plan"],
        ["--workload", "no-such-workload"],
        ["--diagnostic", "--metadata", str(tmp_path / "m.json")],
        ["--canary", "--metadata", str(tmp_path / "m.json")],
    ):
        with pytest.raises(SystemExit) as refused:
            report.main(arguments)
        assert refused.value.code == 2
        assert "workload" in capsys.readouterr().err
    assert not (tmp_path / "m.json").exists()


def test_an_unwritable_sidecar_changes_neither_the_envelope_nor_the_exit_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = json.dumps({"implementation": "CPython", "version": "3.99.1", "executable": "/p"})

    def probe(_command: Sequence[str], _environment: Mapping[str, str]) -> tuple[int, str, str]:
        return (0, identity, "")

    def child(request: ChildRequest) -> ChildReading:
        samples = () if is_memory_cell(request.cell) else (1.0,) * request.measured
        return ChildReading(1.0, unit(request.cell), samples)

    monkeypatch.setattr(report, "run_probe", probe)
    monkeypatch.setattr(report, "run_child", child)
    monkeypatch.setattr(report, "Provisioner", _FakeProvisioner)
    assert report.main(["--workload", PLAN_GROUP]) == 0
    plain = capsys.readouterr()
    durations = tmp_path / "durations.json"
    metadata = tmp_path / "metadata.json"
    durations.mkdir()
    metadata.mkdir()
    arguments = [
        "--workload",
        PLAN_GROUP,
        "--metadata",
        str(metadata),
        "--durations",
        str(durations),
    ]
    assert report.main(arguments) == 0
    captured = capsys.readouterr()
    assert captured.out == plain.out
    assert captured.err.splitlines() == [
        f"telemetry sidecar {metadata} was not written: [Errno 21] Is a directory: '{metadata}'",
        f"telemetry sidecar {durations} was not written: [Errno 21] Is a directory: '{durations}'",
    ]


def test_the_entrypoint_measures_a_slice_with_identities_probed_before_any_reading(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = BudgetContract.load()
    events: list[str] = []
    identity = json.dumps({"implementation": "CPython", "version": "3.99.1", "executable": "/p"})

    def probe(command: Sequence[str], environment: Mapping[str, str]) -> tuple[int, str, str]:
        events.append(f"probe {command[-1] if command[0] == 'uv' else 'current'}")
        assert environment["PYTHONHASHSEED"] == "0"
        return (0, identity, "") if "uv" not in command[0] else (1, "", "no 3.13 here")

    def child(request: ChildRequest) -> ChildReading:
        events.append("child")
        samples = () if is_memory_cell(request.cell) else (1.0,) * request.measured
        return ChildReading(1.0, unit(request.cell), samples)

    monkeypatch.setattr(report, "run_probe", probe)
    monkeypatch.setattr(report, "run_child", child)
    monkeypatch.setattr(report, "Provisioner", _FakeProvisioner)
    metadata = tmp_path / "metadata.json"
    durations = tmp_path / "durations.json"
    assert (
        report.main(
            ["--workload", PLAN_GROUP, "--metadata", str(metadata), "--durations", str(durations)]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    document = cast("dict[str, object]", json.loads(captured.out))
    validate(document)
    readings = cast("list[dict[str, object]]", document["readings"])
    assert {(r["runtime"], r["workload"], r["cell"]) for r in readings} == set(
        report.selected_addresses(
            contract, report.supported_minors(), workload_selection([PLAN_GROUP], contract)
        )
    )
    assert document["comparisons"] == []
    assert document["incomplete"] == []
    probes = [event for event in events if event.startswith("probe")]
    assert len(probes) == len(report.supported_minors())
    assert events[: len(probes)] == probes
    recorded = json.loads(metadata.read_text(encoding="utf-8"))
    assert recorded["subject"] == report.SUBJECT
    statuses = {runtime: status["status"] for runtime, status in recorded["runtimes"].items()}
    assert set(statuses) == set(report.supported_minors())
    assert statuses[CURRENT_MINOR] == "available"
    assert recorded["runtimes"][CURRENT_MINOR]["version"] == "3.99.1"
    other = next(minor for minor in report.supported_minors() if minor != CURRENT_MINOR)
    assert recorded["runtimes"][other] == {
        "status": "unavailable",
        "reason": "the identity probe exited 1: no 3.13 here",
    }
    spans = Spans.load(durations)
    assert [span.name for span in spans.spans if span.scope == "setup"][: len(probes)] == [
        "identity"
    ] * len(probes)
    assert {span.name for span in spans.spans if span.scope == "workload"} == {PLAN_GROUP}


# --------------------------------------------------------------------------- #
# The control group: the before/after matrix, spelled once and expanded here   #
# --------------------------------------------------------------------------- #
def test_control_cells_expand_the_control_matrix_in_their_windows_and_units() -> None:
    contract = BudgetContract.load()
    cells = control_cells(contract)
    arms = len(contract.memory_scaling_arms)
    delivery = len(control_support.DELIVERY_WORKLOAD_IDS) * 2 * 2 * arms * 3
    guarded = len(control_support.GUARD_WIDTHS) * (
        3 + 2 + 2 * len(control_support.GUARDED_ROOTS) * 3
    )
    held = len(control_support.HELD_MODELS) * len(control_support.HELD_STATES)
    assert len(cells) == delivery + guarded + held
    assert len({(cell.workload, cell.path) for cell in cells}) == len(cells)
    assert all(cell.workload.startswith(report.CONTROL_PREFIX) for cell in cells)
    assert {cell.workload for cell in cells} == {
        *(f"control-delivery-{name}" for name in control_support.DELIVERY_WORKLOAD_IDS),
        *(f"control-guarded-{width}" for width in control_support.GUARD_WIDTHS),
        control_support.HELD_WORKLOAD,
    }
    for cell in cells:
        assert not report.needs_database(cell.path)
        assert unit(cell.path) == ("us" if cell.path.endswith(".elapsedUs") else "KiB")
        assert is_memory_cell(cell.path) == (not cell.path.endswith(".elapsedUs"))
        assert expected_readings(contract, cell.path) == (
            1 if cell.path.endswith(".elapsedUs") else contract.memory_children
        )
        window = window_of(cell.path, cell.workload)
        if cell.workload == control_support.HELD_WORKLOAD:
            assert window == report.RESULT_HELD_WINDOW
        elif cell.path.startswith("plan.cold."):
            assert window == report.PLAN_WINDOW
        elif cell.path.startswith("plan.warm."):
            assert window == report.WARM_PLAN_WINDOW
        else:
            assert window == report.CONTROL_DELIVERY_WINDOW
    assert {
        cell.path.split(".")[2] for cell in cells if cell.workload.startswith("control-delivery-")
    } == {f"roots{arm}" for arm in contract.memory_scaling_arms}
    assert set(report.WINDOW_DESCRIPTIONS) >= {
        report.WARM_PLAN_WINDOW,
        report.CONTROL_DELIVERY_WINDOW,
        report.RESULT_HELD_WINDOW,
    }
