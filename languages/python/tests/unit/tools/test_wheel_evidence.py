from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

import wheel_evidence as evidence
from interpreter_matrix import WORKSPACE
from python_workspace import load_workspace

_SOURCE = "a" * 40
_OBSERVED = "2026-11-04T12:10:00+00:00"
_TARGETS = [
    {"id": f"target-{i}", "runner": "native", "arch": "x86_64", "platform": "linux"}
    for i in range(4)
]
type Document = dict[str, Any]


def _write(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def _job(target: str, python: str) -> Document:
    return {
        "name": f"build / wheel ({target}, {python})",
        "id": f"{target}-{python}",
        "run_id": 42,
        "run_attempt": 2,
        "created_at": "2026-11-04T12:00:05Z",
        "started_at": "2026-11-04T12:00:10Z",
        "completed_at": "2026-11-04T12:02:10Z",
        "status": "completed",
        "conclusion": "success",
    }


def _run() -> Document:
    return {
        "id": 42,
        "run_attempt": 2,
        "created_at": "2026-11-04T12:00:00Z",
        "run_started_at": "2026-11-04T12:00:03Z",
        "updated_at": "2026-11-04T12:03:00Z",
        "status": "completed",
    }


def _target(root: Path, target: str, python: str) -> Path:
    directory = root / f"{target}-{python}"
    wheel = (
        directory / "wheelhouse" / f"parallax_postgres-0.1.0-cp{python.replace('.', '')}-native.whl"
    )
    wheel.parent.mkdir(parents=True)
    wheel.write_bytes(f"{target}/{python} candidate".encode())
    _write(
        directory / "target.json",
        {
            "target": target,
            "python": python,
            "source_sha": _SOURCE,
            "run_id": "42",
            "run_attempt": 2,
            "status": "passed",
            "postgres_version": "18.6",
            "timings": {"setup_seconds": 10.5, "build_repair_seconds": 30.25},
        },
    )
    companions: list[Document] = []
    for member in load_workspace(WORKSPACE).members:
        if member.name == "parallax-postgres":
            continue
        name = member.name.replace("-", "_")
        path = directory / "companions" / f"{name}-0.1.0-py3-none-any.whl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{name} candidate".encode())
        companions.append(
            {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    companions.sort(key=lambda entry: entry["filename"])
    driver: Document = {
        "status": "passed",
        "elapsed_seconds": 12.5,
        "install_seconds": 7,
        "test_seconds": 5.5,
        "tests": {"passed": 81, "skipped": 0, "failed": 0, "errors": 0},
        "psycopg_version": "3.3.6",
        "libpq_version": 180006,
    }
    _write(
        directory / "validation" / "validation.json",
        {
            "status": "passed",
            "postgres_version": "18.6",
            "wheel": {
                "filename": wheel.name,
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            },
            "drivers": {name: {**driver, "implementation": name} for name in ("binary", "c")},
            "companions": companions,
        },
    )
    source = directory / "source"
    shutil.copytree(directory / "wheelhouse", source / "wheelhouse")
    shutil.copytree(directory / "companions", source / "companions")
    shutil.copytree(directory / "validation", source / "validation")
    sdists: list[dict[str, str]] = []
    for member in load_workspace(WORKSPACE).members:
        if member.name == "parallax-conformance":
            continue
        path = directory / "sdists" / f"{member.name.replace('-', '_')}-0.1.0.tar.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{member.name} source".encode())
        sdists.append(
            {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    _write(
        source / "source.json",
        {
            "status": "passed",
            "sdists": sorted(sdists, key=lambda item: item["filename"]),
            "wheels": sorted(
                [
                    {
                        "filename": wheel.name,
                        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                    },
                    *[
                        entry
                        for entry in companions
                        if not entry["filename"].startswith("parallax_conformance-")
                    ],
                ],
                key=lambda item: item["filename"],
            ),
            "build_seconds": 22.5,
            "elapsed_seconds": 52.0,
        },
    )
    return directory


@pytest.fixture
def matrix(tmp_path: Path) -> tuple[Path, list[Document], Document]:
    jobs: list[Document] = []
    for target in _TARGETS:
        for python in ("3.14", "3.15"):
            _target(tmp_path, target["id"], python)
            jobs.append(_job(target["id"], python))
    return tmp_path, jobs, _run()


def _summarize(matrix: tuple[Path, list[Document], Document]) -> Document:
    root, jobs, run = matrix
    return evidence.summarize(root, _TARGETS, jobs, run, _SOURCE, 2, observed_at=_OBSERVED)


def test_complete_matrix_binds_eight_exact_retained_wheels_and_sixteen_driver_runs(
    matrix: tuple[Path, list[Document], Document],
) -> None:
    summary = _summarize(matrix)
    assert summary["status"] == "passed"
    assert summary["findings"] == []
    assert summary["expected_targets"] == summary["validated_targets"] == 8
    assert sum(len(target["drivers"]) for target in summary["targets"]) == 16
    assert {target["python"] for target in summary["targets"]} == {"3.14", "3.15"}
    root, _, _ = matrix
    for target in summary["targets"]:
        wheel = target["wheel"]
        path = root / target["evidence_path"] / "wheelhouse" / wheel["filename"]
        assert not Path(target["evidence_path"]).is_absolute()
        assert wheel["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_job_queue_workflow_wall_time_and_parallel_runner_time_are_distinct(
    matrix: tuple[Path, list[Document], Document],
) -> None:
    summary = _summarize(matrix)
    execution = summary["execution"]
    assert execution["workflow_queue_seconds"] == 3
    assert execution["workflow_elapsed_seconds"] == 180
    assert execution["workflow_execution_observed_seconds"] == 177
    assert execution["aggregate_runner_seconds"] == 8 * 120
    assert {target["ci_job"]["queue_seconds"] for target in summary["targets"]} == {5}


def test_job_without_its_own_creation_timestamp_has_unknown_queue_time() -> None:
    job = _job("native", "3.14")
    del job["created_at"]
    assert evidence.job_timings(job, _OBSERVED)["queue_seconds"] is None


def test_skipped_job_has_no_runner_time_despite_synthetic_reversed_timestamps(
    matrix: tuple[Path, list[Document], Document],
) -> None:
    _, jobs, _ = matrix
    skipped = {
        **_job("bootstrap", "3.15"),
        "conclusion": "skipped",
        "started_at": "2026-11-04T12:00:10Z",
        "completed_at": "2026-11-04T12:00:09Z",
    }
    jobs.append(skipped)
    summary = _summarize(matrix)
    assert summary["status"] == "passed"
    execution = summary["execution"]
    assert execution["aggregate_runner_seconds"] == 8 * 120
    timing = execution["jobs"][-1]
    assert timing["started_at"] == skipped["started_at"]
    assert timing["completed_at"] == skipped["completed_at"]
    assert timing["queue_seconds"] is None
    assert timing["runner_seconds"] == 0
    assert timing["runner_seconds_final"] is True


def test_executed_job_with_reversed_timestamps_is_still_rejected() -> None:
    job = {**_job("native", "3.14"), "completed_at": "2026-11-04T12:00:09Z"}
    with pytest.raises(ValueError, match="timestamp interval must be finite and nonnegative"):
        evidence.job_timings(job, _OBSERVED)


def test_running_aggregation_reports_observed_elapsed_without_fabricating_final_totals() -> None:
    run = {**_run(), "status": "in_progress"}
    job = {**_job("native", "3.14"), "status": "in_progress", "completed_at": None}
    skipped = {**_job("bootstrap", "3.15"), "conclusion": "skipped"}
    timing = evidence.execution_timings([job, skipped], run, _OBSERVED)
    assert timing["workflow_elapsed_seconds"] is None
    assert timing["aggregate_runner_seconds"] is None
    assert timing["workflow_elapsed_observed_seconds"] == 600
    assert timing["aggregate_runner_observed_seconds"] == 590
    assert timing["workflow_completed_at"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sha", "b" * 40),
        ("run_attempt", 1),
        ("run_id", 41),
        ("status", "failed"),
        ("postgres_version", "18.5"),
    ],
)
def test_mismatched_or_failed_target_never_counts_as_validated(
    matrix: tuple[Path, list[Document], Document],
    field: str,
    value: object,
) -> None:
    root, _, _ = matrix
    path = next(root.rglob("target.json"))
    record = json.loads(path.read_text())
    record[field] = value
    _write(path, record)
    summary = _summarize(matrix)
    assert summary["status"] == "failed"
    assert summary["validated_targets"] == 7
    assert summary["findings"]
    assert summary["failed_target_evidence"][0]["reported_target"][field] == value


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unexpected", "corrupt"])
def test_missing_duplicate_unexpected_or_unreadable_records_fail_closed(
    matrix: tuple[Path, list[Document], Document],
    mutation: str,
) -> None:
    root, _, _ = matrix
    path = next(root.rglob("target.json"))
    if mutation == "missing":
        path.unlink()
    elif mutation == "duplicate":
        _write(root / "duplicate" / "target.json", json.loads(path.read_text()))
    elif mutation == "unexpected":
        _target(root, "outside-matrix", "3.14")
    else:
        path.write_text("truncated {")
    summary = _summarize(matrix)
    assert summary["status"] == "failed"
    assert summary["findings"]


def test_modified_retained_wheel_is_refused_even_after_validation_passed(
    matrix: tuple[Path, list[Document], Document],
) -> None:
    root, _, _ = matrix
    next(root.rglob("parallax_postgres-*.whl")).write_bytes(b"rebuilt bytes")
    summary = _summarize(matrix)
    assert summary["status"] == "failed"
    assert "retained wheel identity" in " ".join(summary["findings"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("implementation", "python"),
        ("tests", {"passed": 0, "skipped": 0, "failed": 0, "errors": 0}),
        ("tests", {"passed": 80, "skipped": 1, "failed": 0, "errors": 0}),
        ("elapsed_seconds", float("nan")),
    ],
)
def test_driver_failure_wrong_implementation_empty_or_skipped_suite_is_not_success(
    matrix: tuple[Path, list[Document], Document],
    field: str,
    value: object,
) -> None:
    root, _, _ = matrix
    path = next(root.rglob("validation.json"))
    validation = json.loads(path.read_text())
    validation["drivers"]["c"][field] = value
    _write(path, validation)
    assert _summarize(matrix)["status"] == "failed"


def test_postgresql_versions_must_match_the_selected_version_and_each_other(
    matrix: tuple[Path, list[Document], Document],
) -> None:
    root, _, _ = matrix
    path = next(root.rglob("target.json"))
    record = json.loads(path.read_text())
    record["postgres_version"] = "18.7"
    _write(path, record)
    validation_path = path.parent / "validation" / "validation.json"
    validation = json.loads(validation_path.read_text())
    validation["postgres_version"] = "18.7"
    _write(validation_path, validation)
    _write(path.parent / "source" / "validation" / "validation.json", validation)
    assert "different PostgreSQL versions" in " ".join(_summarize(matrix)["findings"])


@pytest.mark.parametrize("mutate", ["missing", "failed", "attempt"])
def test_successful_validation_cannot_replace_missing_or_failed_ci_job_evidence(
    matrix: tuple[Path, list[Document], Document],
    mutate: str,
) -> None:
    _, jobs, _ = matrix
    if mutate == "missing":
        jobs.pop()
    elif mutate == "failed":
        jobs[0]["conclusion"] = "failure"
    else:
        jobs[0]["run_attempt"] = 1
    assert _summarize(matrix)["status"] == "failed"


def _cli(tmp_path: Path, declaration: list[Document]) -> tuple[int, Document, Path]:
    root = tmp_path / "targets"
    root.mkdir()
    targets, jobs, run = (tmp_path / f"{name}.json" for name in ("matrix", "jobs", "run"))
    _write(targets, declaration)
    _write(jobs, {"jobs": []})
    _write(run, _run())
    output = tmp_path / "summary"
    status = evidence.main(
        [
            "--root",
            str(root),
            "--repository",
            "owner/repo",
            "--run-id",
            "42",
            "--attempt",
            "2",
            "--source-sha",
            _SOURCE,
            "--output",
            str(output),
            "--targets",
            str(targets),
            "--jobs",
            str(jobs),
            "--run",
            str(run),
        ]
    )
    return status, json.loads((output / "manifest.json").read_text()), output


def test_cli_writes_failure_evidence_before_returning_failure(tmp_path: Path) -> None:
    status, summary, output = _cli(tmp_path, _TARGETS)
    assert status == 1
    assert len(summary["findings"]) == 8
    assert "failed" in (output / "summary.md").read_text()


def test_cli_expects_no_evidence_from_a_retired_target(tmp_path: Path) -> None:
    _, summary, _ = _cli(tmp_path, [*_TARGETS, {"id": "retired", "retired": "0.2"}])
    assert summary["expected_targets"] == 8
    assert not any("retired" in finding for finding in summary["findings"])


def test_cli_refuses_a_declaration_with_no_current_target(tmp_path: Path) -> None:
    status, summary, _ = _cli(tmp_path, [{"id": "retired", "retired": "0.2"}])
    assert status == 1
    assert summary["findings"] == ["target declaration names no current target"]


def test_changed_companion_bytes_cannot_be_replaced_after_validation(
    matrix: tuple[Path, list[Document], Document],
) -> None:
    root, _, _ = matrix
    next(root.rglob("parallax_core-*.whl")).write_bytes(b"changed core")
    summary = _summarize(matrix)
    assert summary["status"] == "failed"
    assert "companion identities differ" in " ".join(summary["findings"])


def test_all_targets_must_have_validated_the_same_companion_bytes(
    matrix: tuple[Path, list[Document], Document],
) -> None:
    root, _, _ = matrix
    wheel = next(root.rglob("parallax_core-*.whl"))
    wheel.write_bytes(b"different but individually validated core")
    validation_path = wheel.parent.parent / "validation" / "validation.json"
    validation = json.loads(validation_path.read_text())
    for companion in validation["companions"]:
        if companion["filename"] == wheel.name:
            companion["sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    _write(validation_path, validation)
    summary = _summarize(matrix)
    assert summary["status"] == "failed"
    assert "different companion artifacts" in " ".join(summary["findings"])


def test_incomplete_companion_set_is_never_a_complete_installation_proof(
    matrix: tuple[Path, list[Document], Document],
) -> None:
    root, _, _ = matrix
    next(root.rglob("parallax_core-*.whl")).unlink()
    assert "companion wheels do not match" in " ".join(_summarize(matrix)["findings"])


@pytest.mark.parametrize("mutation", ["missing", "sdist", "wheel", "driver", "version"])
def test_source_installation_proof_is_required_for_every_target(
    matrix: tuple[Path, list[Document], Document],
    mutation: str,
) -> None:
    root, _, _ = matrix
    directory = next(root.rglob("target.json")).parent
    if mutation == "missing":
        (directory / "source" / "source.json").unlink()
    elif mutation == "sdist":
        next((directory / "sdists").glob("*.tar.gz")).write_bytes(b"different source")
    elif mutation == "wheel":
        next((directory / "source" / "wheelhouse").glob("*.whl")).write_bytes(b"different build")
    else:
        path = directory / "source" / "validation" / "validation.json"
        validation = json.loads(path.read_text())
        if mutation == "driver":
            validation["drivers"]["binary"]["tests"]["skipped"] = 1
        else:
            validation["postgres_version"] = "18.7"
        _write(path, validation)
    assert _summarize(matrix)["status"] == "failed"


def test_targets_cannot_validate_different_retained_source_inputs(
    matrix: tuple[Path, list[Document], Document],
) -> None:
    root, _, _ = matrix
    path = next(root.rglob("target.json")).parent
    sdist = next((path / "sdists").glob("*.tar.gz"))
    sdist.write_bytes(b"different source validated in one cell")
    source_path = path / "source" / "source.json"
    record = json.loads(source_path.read_text())
    for identity in record["sdists"]:
        if identity["filename"] == sdist.name:
            identity["sha256"] = hashlib.sha256(sdist.read_bytes()).hexdigest()
    _write(source_path, record)
    summary = _summarize(matrix)
    assert summary["status"] == "failed"
    assert "different source distributions" in " ".join(summary["findings"])
