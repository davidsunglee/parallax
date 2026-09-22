from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

import instance_state_overhead as report
from durations import Spans
from interpreter_matrix import IDENTITY_SCRIPT
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import validate
from parallax.conformance.workloads import workload_digest
from tests.unit._instance_state_support import ARMS, REPORTED, Scenario


def test_envelope_retains_the_complete_matrix_and_member_provenance() -> None:
    matrix = _matrix()
    envelope = report.build_envelope(
        BudgetContract.load(),
        report._provenance(  # pyright: ignore[reportPrivateUsage] - the entrypoint seam
            BudgetContract.load(), matrix
        ),
        matrix,
    )

    assert envelope.subject == report.SUBJECT
    assert envelope.authority == "non-authoritative"
    assert envelope.incomplete == ()
    assert envelope.errors == ()
    assert envelope.readings
    assert envelope.provenance.workload_digest == workload_digest()
    assert envelope.provenance.postgres == "not-used"
    assert envelope.provenance.sampling["scenarios"] == [scenario.name for scenario in REPORTED]
    validate(envelope)

    addresses = {(reading.workload, reading.cell) for reading in envelope.readings}
    assert len(addresses) == len(envelope.readings)
    assert addresses == _expected_addresses(tuple(matrix))


def test_envelope_comparisons_are_the_existing_advisory_rules() -> None:
    matrix = _matrix(compact_retention=0.90, compact_operation_ratio=2.0)
    contract = BudgetContract.load()
    envelope = report.build_envelope(
        contract,
        report._provenance(contract, matrix),  # pyright: ignore[reportPrivateUsage]
        matrix,
    )

    expected_cells = {
        "aggregate.retained.reduction",
        *(
            f"operation.{operation.name.replace(' ', '-')}.armAgainstArm"
            for operation in report.OPERATIONS
        ),
    }
    assert {comparison.cell for comparison in envelope.comparisons} == expected_cells
    aggregate = next(
        comparison
        for comparison in envelope.comparisons
        if comparison.cell == "aggregate.retained.reduction"
    )
    assert (aggregate.operator, aggregate.limit, aggregate.outcome) == (
        "at-least",
        report.AGGREGATE_TARGET,
        "outside",
    )
    operation_comparisons = [
        comparison
        for comparison in envelope.comparisons
        if comparison.cell.startswith("operation.")
    ]
    assert len(operation_comparisons) == len(report.OPERATIONS)
    assert all(
        (comparison.operator, comparison.limit, comparison.outcome)
        == ("at-most", report.REGRESSION_LIMIT, "outside")
        for comparison in operation_comparisons
    )
    reading_addresses = {(reading.workload, reading.cell) for reading in envelope.readings}
    assert all(
        (comparison.workload, comparison.cell) in reading_addresses
        for comparison in envelope.comparisons
    )


def test_successful_entrypoint_stdout_is_only_the_owned_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix = _matrix()
    runtime = next(iter(matrix))
    monkeypatch.setattr(report, "supported_minors", lambda: (runtime,))

    def child(selected_runtime: str, scenario: Scenario) -> report.Cell:
        return matrix[selected_runtime][scenario.name]

    monkeypatch.setattr(report, "in_a_child", child)

    assert report.main([]) == 0
    captured = capsys.readouterr()
    document = cast("Mapping[str, object]", json.loads(captured.out))
    assert captured.err == ""
    assert document["subject"] == report.SUBJECT
    assert cast("Sequence[object]", document["readings"])
    validate(document)


def _expected_addresses(runtimes: tuple[str, ...]) -> set[tuple[str, str]]:
    arm_metrics = {
        report._metric_name(name)  # pyright: ignore[reportPrivateUsage] - emitted contract
        for name in report.ArmReading._fields
    } | {"lifecycleBytes", "transientBytes", "unreproducedNs"}
    expected: set[tuple[str, str]] = set()
    for runtime in runtimes:
        for scenario in REPORTED:
            workload = f"cpython-{runtime}/{scenario.name}"
            expected.update((workload, cell) for cell in ("fields", "warmups"))
            expected.update(
                (workload, f"{arm.name}.{metric}") for arm in ARMS for metric in arm_metrics
            )
            expected.update(
                (workload, cell)
                for cell in (
                    "vsLegacy.retainedReduction",
                    "vsLegacy.bareReduction",
                    "vsOrdinary.retainedReduction",
                    "vsOrdinary.bareReduction",
                )
            )
            if scenario in report.SCENARIOS:
                expected.update((workload, cell) for cell in report.HEAD_ONLY_CELLS)
        workload = f"cpython-{runtime}"
        expected.update(
            (workload, f"{aggregate}.{metric}")
            for aggregate in (
                "aggregate.retained",
                "aggregate.bare",
                "vsOrdinary.retained",
            )
            for metric in ("before", "after", "reduction")
        )
        expected.update(
            (workload, f"operation.{operation.name.replace(' ', '-')}.{comparison}")
            for operation in report.OPERATIONS
            for comparison in ("armAgainstArm", "likeForLike", "vsOrdinary")
        )
    return expected


def _arm(
    scenario: Scenario,
    retained: int,
    operation_ratio: float,
    *,
    legacy: bool,
) -> report.ArmReading:
    cells = len(scenario.values) + len(scenario.unloaded)
    baseline_ns = float(max(cells, 1) * 100)
    scaled_ns = baseline_ns if legacy else baseline_ns * operation_ratio
    return report.ArmReading(
        cells=cells,
        retained_bytes=retained,
        bare_bytes=retained - max(cells, 1),
        peak_bytes=retained + max(cells, 1),
        construct_ns=scaled_ns,
        call_ns=baseline_ns / max(cells, 1),
        scaffolding_ns=0.0,
        read_ns=scaled_ns,
        dump_ns=scaled_ns,
    )


def _reading(
    scenario: Scenario,
    compact_retention: float,
    compact_operation_ratio: float,
) -> report.Reading:
    scale = max(len(scenario.values) + len(scenario.unloaded), 1)
    legacy_retained = scale * 100
    compact_retained = round(legacy_retained * compact_retention)
    return report.Reading(
        scenario.name,
        scenario.summary,
        len(scenario.values),
        BudgetContract.load().timing_warmups,
        _arm(scenario, legacy_retained * 2, 1.0, legacy=True),
        _arm(scenario, legacy_retained, 1.0, legacy=True),
        _arm(
            scenario,
            compact_retained,
            compact_operation_ratio,
            legacy=False,
        ),
        report.ProjectionReading(
            retained_bytes=scale * 10,
            peak_bytes=scale * 20,
            projection_ns=scale * 100.0,
            projection_reuse_ns=scale * 80.0,
            direct_wire_ns=scale * 90.0,
        )
        if scenario in report.SCENARIOS
        else None,
    )


def _matrix(
    *,
    compact_retention: float = 0.50,
    compact_operation_ratio: float = 1.0,
) -> report.Matrix:
    runtime = report.CURRENT_MINOR
    return {
        runtime: {
            scenario.name: _reading(
                scenario,
                compact_retention,
                compact_operation_ratio,
            )
            for scenario in REPORTED
        }
    }


def test_durations_time_every_scenario_child_without_changing_the_stdout_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix = _matrix()
    runtime = next(iter(matrix))
    monkeypatch.setattr(report, "supported_minors", lambda: (runtime,))
    asked: list[tuple[str, str]] = []

    def child(selected_runtime: str, scenario: Scenario) -> report.Cell:
        asked.append((selected_runtime, scenario.name))
        return matrix[selected_runtime][scenario.name]

    monkeypatch.setattr(report, "in_a_child", child)
    assert report.main([]) == 0
    plain = capsys.readouterr()
    plain_order = list(asked)
    asked.clear()
    sidecar = tmp_path / "durations.json"
    assert report.main(["--durations", str(sidecar)]) == 0
    timed = capsys.readouterr()
    assert asked == plain_order == [(runtime, scenario.name) for scenario in REPORTED]
    assert timed.out == plain.out
    assert timed.err == ""
    validate(cast("Mapping[str, object]", json.loads(timed.out)))
    spans = Spans.load(sidecar)
    assert [(span.scope, span.labels["runtime"], span.name) for span in spans.spans] == [
        ("scenario", selected_runtime, name) for selected_runtime, name in plain_order
    ]
    assert all(span.labels["member"] == report.SUBJECT for span in spans.spans)
    assert spans.unavailable == ()


def test_an_unwritable_sidecar_changes_neither_the_envelope_nor_the_exit_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    matrix = _matrix()
    runtime = next(iter(matrix))
    monkeypatch.setattr(report, "supported_minors", lambda: (runtime,))
    identity = json.dumps({"implementation": "CPython", "version": "3.14.7", "executable": "/p"})

    def probe(_command: Sequence[str], _environment: Mapping[str, str]) -> tuple[int, str, str]:
        return (0, identity, "")

    def child(selected_runtime: str, scenario: Scenario) -> report.Cell:
        return matrix[selected_runtime][scenario.name]

    monkeypatch.setattr(report, "run_probe", probe)
    monkeypatch.setattr(report, "in_a_child", child)
    assert report.main([]) == 0
    plain = capsys.readouterr()
    durations = tmp_path / "durations.json"
    metadata = tmp_path / "metadata.json"
    durations.mkdir()
    metadata.mkdir()
    assert report.main(["--durations", str(durations), "--metadata", str(metadata)]) == 0
    captured = capsys.readouterr()
    assert captured.out == plain.out
    assert captured.err.splitlines() == [
        f"telemetry sidecar {metadata} was not written: [Errno 21] Is a directory: '{metadata}'",
        f"telemetry sidecar {durations} was not written: [Errno 21] Is a directory: '{durations}'",
    ]


def test_the_entrypoint_takes_no_argument_but_durations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert report.main(["unexpected"]) == 2
    assert "usage:" in capsys.readouterr().err
    assert report.main(["--durations"]) == 2
    assert "usage:" in capsys.readouterr().err
    assert not (tmp_path / "durations.json").exists()


def test_metadata_probes_each_runtime_through_this_reports_own_launch_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    matrix = _matrix()
    runtime = next(iter(matrix))
    other = "9.99"
    monkeypatch.setattr(report, "supported_minors", lambda: (other, runtime))
    events: list[str] = []
    probed: list[tuple[list[str], dict[str, str]]] = []

    def probe(command: Sequence[str], environment: Mapping[str, str]) -> tuple[int, str, str]:
        probed.append((list(command), dict(environment)))
        events.append("probe")
        if command[0] == "uv":
            return (2, "", "no such interpreter")
        identity = {"implementation": "CPython", "version": "3.14.7", "executable": "/p"}
        return (0, json.dumps(identity), "")

    def child(selected_runtime: str, scenario: Scenario) -> report.Cell:
        events.append("child")
        return matrix.get(selected_runtime, matrix[runtime])[scenario.name]

    monkeypatch.setattr(report, "run_probe", probe)
    monkeypatch.setattr(report, "in_a_child", child)
    metadata = tmp_path / "metadata.json"
    assert report.main(["--metadata", str(metadata)]) == 0
    assert capsys.readouterr().err == ""
    assert events[:2] == ["probe", "probe"] and "probe" not in events[2:]
    assert probed[0][0] == [
        "uv",
        "run",
        "--frozen",
        "--python",
        other,
        "python",
        str(IDENTITY_SCRIPT),
    ]
    assert probed[0][1]["UV_PROJECT_ENVIRONMENT"].endswith(f"parallax-instance-state-{other}")
    assert probed[1][0] == [sys.executable, str(IDENTITY_SCRIPT)]
    assert "PYTHONPATH" in probed[1][1]
    recorded = json.loads(metadata.read_text(encoding="utf-8"))
    assert recorded["subject"] == report.SUBJECT
    assert recorded["runtimes"][other] == {
        "status": "unavailable",
        "reason": "the identity probe exited 2: no such interpreter",
    }
    assert recorded["runtimes"][runtime]["version"] == "3.14.7"


def test_the_report_declares_the_matrix_its_envelope_carries() -> None:
    runtimes = ("3.13", "3.14")
    assert report.expected_addresses(runtimes) == _expected_addresses(runtimes)
    matrix = _matrix()
    contract = BudgetContract.load()
    envelope = report.build_envelope(
        contract,
        report._provenance(contract, matrix),  # pyright: ignore[reportPrivateUsage] - the entrypoint seam
        matrix,
    )
    assert {(reading.workload, reading.cell) for reading in envelope.readings} == (
        report.expected_addresses(tuple(matrix))
    )
    assert all(reading.unit == report.unit_of(reading.cell) for reading in envelope.readings)
    assert {(comparison.workload, comparison.cell) for comparison in envelope.comparisons} == (
        report.expected_comparisons(tuple(matrix))
    )
    assert (
        frozenset(
            {
                "compact.projectionRetainedBytes",
                "compact.projectionTransientBytes",
                "compact.projectionPeakBytes",
                "compact.projectionNs",
                "compact.projectionReuseNs",
                "compact.directWireNs",
            }
        )
        == report.HEAD_ONLY_CELLS
    )
