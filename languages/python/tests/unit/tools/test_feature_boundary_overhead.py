from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

import feature_boundary_overhead as report
from durations import Spans
from interpreter_matrix import CURRENT_MINOR, HASH_SEED, RuntimeIdentity, supported_minors
from parallax.conformance.budget import BudgetContract


def _answer(case: str) -> dict[str, object]:
    return {
        "case": case,
        "window": report.WINDOWS[case],
        "units": report.UNITS[case],
        "samples": {
            metric: [float(index + 1) for index in range(report.samples_expected(metric))]
            for metric in report.METRICS
        },
        "warmups": report.WARMUPS,
        "measured": report.MEASURED,
        "retainedWarmups": report.RETAINED_WARMUPS,
    }


def _child(_runtime: str, case: str) -> report.Cell:
    return report.decode_child(json.dumps(_answer(case)), case)


def test_canary_has_the_complete_supported_matrix_and_protocol() -> None:
    document = report.canary(BudgetContract.load()).document()
    report.validate_matrix(document)
    readings = cast("list[dict[str, object]]", document["readings"])
    assert len(readings) == len(supported_minors()) * len(report.CASE_NAMES) * len(report.METRICS)
    assert {str(reading["runtime"]) for reading in readings} == set(supported_minors())
    assert document["authority"] == "non-authoritative"
    assert cast("Mapping[str, object]", document["provenance"])["sampling"] == report.sampling()


def test_fake_children_run_once_per_case_on_every_runtime() -> None:
    calls: list[tuple[str, str]] = []

    def child(runtime: str, case: str) -> report.Cell:
        calls.append((runtime, case))
        return _child(runtime, case)

    spans = Spans()
    matrix = report.timed_matrix(supported_minors(), report.CASE_NAMES, spans, child)
    assert calls == [
        (runtime, case) for runtime in supported_minors() for case in report.CASE_NAMES
    ]
    assert report.missing_cells(matrix, supported_minors(), report.CASE_NAMES) == []


@pytest.mark.parametrize("replacement", [None, [], {"case": "wrong"}])
def test_child_non_objects_and_incomplete_answers_are_rejected(replacement: object) -> None:
    result = report.decode_child(json.dumps(replacement), report.CASE_NAMES[0])
    assert isinstance(result, str)
    assert "did not decode" in result


@pytest.mark.parametrize(
    "field,value",
    [
        ("case", "wrong"),
        ("window", "wrong"),
        ("units", 2),
        ("units", True),
        ("units", 1.0),
        ("warmups", 2),
        ("measured", 8),
        ("measured", 9.0),
        ("retainedWarmups", 1),
    ],
)
def test_child_protocol_disagreement_is_rejected(field: str, value: object) -> None:
    case = report.CASE_NAMES[0]
    answer = _answer(case)
    answer[field] = value
    assert isinstance(report.decode_child(json.dumps(answer), case), str)


@pytest.mark.parametrize(
    "samples", [[1.0], [float("nan")] * 9, [float("inf")] * 9, [-1.0] * 9, [True] * 9, [0.0] * 9]
)
def test_child_timing_samples_are_exact_and_finite(samples: list[object]) -> None:
    case = report.CASE_NAMES[0]
    answer = _answer(case)
    cast("dict[str, object]", answer["samples"])["elapsedUs"] = samples
    assert isinstance(report.decode_child(json.dumps(answer), case), str)


def test_child_command_uses_pinned_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    case = report.CASE_NAMES[0]

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert str(report.READING_SCRIPT) in command
        assert command[-5:] == [case, "--warmups", "3", "--measured", "9"]
        env = cast("Mapping[str, str]", kwargs["env"])
        assert env["PYTHONHASHSEED"] == HASH_SEED
        assert env["PARALLAX_OWN_INTERPRETER"] == "1"
        return subprocess.CompletedProcess(command, 0, json.dumps(_answer(case)), "")

    monkeypatch.setattr(report.subprocess, "run", run)
    assert isinstance(report.in_a_child(CURRENT_MINOR, case), report.ChildReading)


@pytest.mark.parametrize("status", [0, 4])
def test_empty_or_failed_children_are_missing(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], status, "", "failed")

    monkeypatch.setattr(report.subprocess, "run", run)
    case = report.CASE_NAMES[0]
    cell = report.in_a_child(CURRENT_MINOR, case)
    assert isinstance(cell, str)
    assert report.missing_cells({CURRENT_MINOR: {case: cell}}, (CURRENT_MINOR,), (case,))


def test_unstartable_child_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("unavailable")

    monkeypatch.setattr(report.subprocess, "run", unavailable)
    assert "could not be started" in str(report.in_a_child(CURRENT_MINOR, report.CASE_NAMES[0]))


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "runtime",
        "window",
        "unit",
        "median",
        "samples",
        "protocol",
        "errors",
    ],
)
def test_envelope_validation_rejects_inexact_evidence(change: str) -> None:
    document = copy.deepcopy(report.canary(BudgetContract.load()).document())
    readings = cast("list[dict[str, object]]", document["readings"])
    reading = readings[0]
    if change == "missing":
        readings.pop()
    elif change == "duplicate":
        readings.append(copy.deepcopy(reading))
    elif change in {"runtime", "window", "unit"}:
        reading[change] = "wrong"
    elif change == "median":
        reading["value"] = 11
    elif change == "samples":
        reading["samples"] = [10.0]
    elif change == "protocol":
        sampling = cast(
            "dict[str, object]", cast("dict[str, object]", document["provenance"])["sampling"]
        )
        sampling["retainedWarmups"] = 1
    else:
        document["errors"] = [{"code": "failed", "message": "failed"}]
    with pytest.raises(ValueError):
        report.validate_matrix(document)


def test_diagnostic_is_not_an_envelope() -> None:
    document = report.diagnostic((CURRENT_MINOR,), (report.CASE_NAMES[0],), _child)
    assert document["diagnostic"] is True
    assert len(cast("list[object]", document["readings"])) == len(report.METRICS)
    assert "provenance" not in document


@pytest.mark.parametrize(
    "arguments",
    [
        ["--select", "*"],
        ["--runtime", CURRENT_MINOR],
        ["--diagnostic", "--out", "capture.json"],
        ["--diagnostic", "--metadata", "metadata.json"],
        ["--diagnostic", "--canary"],
        ["--canary", "--durations", "durations.json"],
        ["--diagnostic", "--runtime", "0.0"],
        ["--diagnostic", "--select", "no-case"],
    ],
)
def test_cli_refuses_selection_as_evidence(arguments: list[str]) -> None:
    with pytest.raises(SystemExit, match="2"):
        report.main(arguments)


def test_measured_cli_writes_envelope_metadata_and_durations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(report, "in_a_child", _child)
    probes: list[str] = []

    def probe(runtime: str, namespace: str) -> RuntimeIdentity:
        probes.append(runtime)
        assert namespace == report.ENVIRONMENT_NAMESPACE
        return RuntimeIdentity("CPython", runtime + ".1", "/python")

    monkeypatch.setattr(report, "probe_runtime", probe)
    out, metadata, durations = (
        tmp_path / name for name in ("capture.json", "metadata.json", "durations.json")
    )
    assert (
        report.main(["--out", str(out), "--metadata", str(metadata), "--durations", str(durations)])
        == 0
    )
    report.validate_matrix(json.loads(out.read_text()))
    assert probes == list(supported_minors())
    assert json.loads(metadata.read_text())["subject"] == report.SUBJECT
    assert durations.is_file()


def test_incomplete_capture_does_not_write_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def failed(runtime: str, case: str) -> report.Cell:
        return "failed"

    monkeypatch.setattr(report, "in_a_child", failed)
    out = tmp_path / "capture.json"
    assert report.main(["--out", str(out)]) == 3
    assert not out.exists()


def test_canary_cli_writes_synthetic_evidence(tmp_path: Path) -> None:
    out = tmp_path / "capture.json"
    assert report.main(["--canary", "--out", str(out)]) == 0
    report.validate_matrix(json.loads(out.read_text()))
