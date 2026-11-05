"""Bind a complete native wheel matrix to its retained bytes and CI timings."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from interpreter_matrix import WORKSPACE, supported_minors
from python_workspace import load_workspace
from validate_source import identities, production_paths
from wheel_build import TARGETS
from wheel_build import targets as current_targets

_DRIVERS = ("binary", "c")
type Document = dict[str, Any]


def _document(path: Path) -> Document:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must hold an object")
    return cast("Document", value)


def _seconds(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a duration")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError(f"timestamp {value!r} has no timezone")
    return instant


def _between(start: object, end: object) -> float | None:
    before, after = _instant(start), _instant(end)
    if before is None or after is None:
        return None
    return _seconds((after - before).total_seconds(), "timestamp interval")


def job_timings(job: Mapping[str, Any], observed_at: str) -> Document:
    completed = job.get("status") == "completed"
    skipped = completed and job.get("conclusion") == "skipped"
    end = job.get("completed_at") if completed else observed_at
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "status": job.get("status"),
        "conclusion": job.get("conclusion"),
        "runner_id": job.get("runner_id"),
        "runner_name": job.get("runner_name"),
        "labels": job.get("labels"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "queue_seconds": None
        if skipped
        else _between(job.get("created_at"), job.get("started_at")),
        "runner_seconds": 0.0 if skipped else _between(job.get("started_at"), end),
        "runner_seconds_final": skipped or (completed and job.get("completed_at") is not None),
    }


def execution_timings(
    jobs: Sequence[Mapping[str, Any]], run: Mapping[str, Any], observed_at: str
) -> Document:
    """Final times stay null until complete; running jobs contribute observed time.

    A job without its own creation timestamp has unknown queue delay. The run's
    creation timestamp cannot substitute for when a dependent job became ready.
    """
    observed = [job_timings(job, observed_at) for job in jobs]
    completed = run.get("status") == "completed"
    end = run.get("updated_at") if completed else observed_at
    runner_seconds = sum(job["runner_seconds"] or 0.0 for job in observed)
    final = all(job["runner_seconds_final"] for job in observed)
    elapsed = _between(run.get("created_at"), end)
    return {
        "observed_at": observed_at,
        "workflow_status": run.get("status"),
        "workflow_created_at": run.get("created_at"),
        "workflow_started_at": run.get("run_started_at"),
        "workflow_completed_at": end if completed else None,
        "workflow_completion_basis": "run.updated_at" if completed else None,
        "workflow_queue_seconds": _between(run.get("created_at"), run.get("run_started_at")),
        "workflow_elapsed_seconds": elapsed if completed else None,
        "workflow_elapsed_observed_seconds": elapsed,
        "workflow_execution_observed_seconds": _between(run.get("run_started_at"), end),
        "aggregate_runner_seconds": runner_seconds if final else None,
        "aggregate_runner_observed_seconds": runner_seconds,
        "jobs": observed,
    }


def _identity(record: Document, expected: Mapping[str, object]) -> None:
    for field, value in expected.items():
        actual = record.get(field)
        if str(actual) != str(value):
            raise ValueError(f"{field} is {actual!r}; expected {value!r}")
    if record.get("status") != "passed":
        raise ValueError(f"target status is {record.get('status')!r}")


def _version(version: object) -> str:
    if not isinstance(version, str) or not re.fullmatch(r"18\.\d+", version):
        raise ValueError(f"PostgreSQL version {version!r} is not an exact 18.x version")
    if int(version.split(".")[1]) < 6:
        raise ValueError(f"PostgreSQL version {version!r} is below 18.6")
    return version


def _driver_result(driver: str, record: Document) -> Document:
    if record.get("status") != "passed" or record.get("implementation") != driver:
        raise ValueError(f"{driver} implementation did not pass: {record.get('status')!r}")
    counts = record.get("tests", {})
    passed = counts.get("passed")
    if not isinstance(passed, int) or isinstance(passed, bool) or passed <= 0:
        raise ValueError(f"{driver} has no passing tests")
    if any(counts.get(field) != 0 for field in ("skipped", "failed", "errors")):
        raise ValueError(f"{driver} has missing or nonzero skipped/failed/error counts")
    return {
        "status": "passed",
        "elapsed_seconds": _seconds(record.get("elapsed_seconds"), f"{driver} elapsed"),
        "install_seconds": record.get("install_seconds"),
        "test_seconds": record.get("test_seconds"),
        "tests": counts,
        "psycopg_version": record.get("psycopg_version"),
        "libpq_version": record.get("libpq_version"),
    }


def _validated_wheel(directory: Path, validation: Document) -> Document:
    wheels = sorted((directory / "wheelhouse").glob("*.whl"))
    if len(wheels) != 1 or not wheels[0].name.startswith("parallax_postgres-"):
        raise ValueError(f"expected exactly one adapter wheel, found {[p.name for p in wheels]}")
    wheel = wheels[0]
    identity = {"filename": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
    if validation.get("wheel") != identity:
        raise ValueError("retained wheel identity differs from the validated artifact")
    return identity


def _companions(directory: Path, validation: Document) -> list[Document]:
    wheels = sorted((directory / "companions").glob("*.whl"))
    expected = {
        member.name.replace("-", "_")
        for member in load_workspace(WORKSPACE).members
        if member.name != "parallax-postgres"
    }
    names = [wheel.name.split("-", 1)[0] for wheel in wheels]
    if len(names) != len(expected) or set(names) != expected:
        raise ValueError("retained companion wheels do not match the workspace distributions")
    identities = [
        {"filename": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
        for wheel in wheels
    ]
    if validation.get("companions") != identities:
        raise ValueError("retained companion identities differ from the validated artifacts")
    return identities


def _source_install(directory: Path, version: str) -> Document:
    source = directory / "source"
    record = _document(source / "source.json")
    if record.get("status") != "passed":
        raise ValueError("source installation did not pass")
    sdists = identities(production_paths(directory / "sdists", "*.tar.gz"))
    if record.get("sdists") != sdists:
        raise ValueError("retained sdists differ from the source-install inputs")
    validation = _document(source / "validation" / "validation.json")
    if validation.get("status") != "passed" or validation.get("postgres_version") != version:
        raise ValueError("source installation did not validate the selected PostgreSQL version")
    wheel = _validated_wheel(source, validation)
    companions = _companions(source, validation)
    wheels = sorted(
        [
            wheel,
            *[
                entry
                for entry in companions
                if not entry["filename"].startswith("parallax_conformance-")
            ],
        ],
        key=lambda entry: entry["filename"],
    )
    if record.get("wheels") != wheels:
        raise ValueError("source-built wheels differ from the source-build record")
    return {
        "status": "passed",
        "sdists": sdists,
        "wheel": wheel,
        "companions": companions,
        "drivers": {name: _driver_result(name, validation["drivers"][name]) for name in _DRIVERS},
        "build_seconds": _seconds(record.get("build_seconds"), "source build"),
        "elapsed_seconds": _seconds(record.get("elapsed_seconds"), "source installation"),
    }


def _cell_record(
    path: Path, expected: Mapping[str, object], jobs: Sequence[Document], observed_at: str
) -> Document:
    record = _document(path)
    _identity(record, expected)
    version = _version(record.get("postgres_version"))
    validation = _document(path.parent / "validation" / "validation.json")
    if validation.get("status") != "passed" or validation.get("postgres_version") != version:
        raise ValueError("validation did not pass against the selected PostgreSQL version")
    drivers = {name: _driver_result(name, validation["drivers"][name]) for name in _DRIVERS}
    name = f"wheel ({record['target']}, {record['python']})"
    matching = [job for job in jobs if str(job.get("name", "")).split(" / ")[-1] == name]
    if len(matching) != 1:
        raise ValueError(f"expected one successful CI job named {name!r}")
    job = matching[0]
    if job.get("status") != "completed" or job.get("conclusion") != "success":
        raise ValueError(f"CI job {name!r} did not complete successfully")
    for field in ("run_id", "run_attempt"):
        if str(job.get(field)) != str(expected[field]):
            raise ValueError(f"CI job {name!r} has mismatched {field}")
    timings = record.get("timings", {})
    return {
        **record,
        "wheel": _validated_wheel(path.parent, validation),
        "companions": _companions(path.parent, validation),
        "source_install": _source_install(path.parent, version),
        "evidence_path": str(path.parent),
        "drivers": drivers,
        "postgres_version": version,
        "timings": {
            field: _seconds(timings.get(field), field)
            for field in ("setup_seconds", "build_repair_seconds")
        },
        "ci_job": job_timings(matching[0], observed_at),
    }


def _discover(root: Path) -> tuple[dict[tuple[str, str], list[Path]], list[str]]:
    indexed: dict[tuple[str, str], list[Path]] = {}
    findings: list[str] = []
    for path in sorted(root.rglob("target.json")):
        try:
            record = _document(path)
            key = (str(record["target"]), str(record["python"]))
            indexed.setdefault(key, []).append(path)
        except (OSError, KeyError, ValueError) as error:
            findings.append(f"{path}: {error}")
    return indexed, findings


def _failed_evidence(path: Path, root: Path, target: str, python: str) -> Document:
    result: Document = {
        "target": target,
        "python": python,
        "path": str(path.parent.relative_to(root)),
    }
    for field, file in (
        ("reported_target", path),
        ("reported_validation", path.parent / "validation" / "validation.json"),
        ("reported_source", path.parent / "source" / "source.json"),
        ("reported_source_validation", path.parent / "source" / "validation" / "validation.json"),
    ):
        try:
            result[field] = _document(file)
        except OSError, ValueError:
            result[field] = None
    return result


def summarize(
    root: Path,
    expected_targets: Sequence[Mapping[str, Any]],
    jobs: Sequence[Document],
    run: Mapping[str, Any],
    source_sha: str,
    attempt: int,
    *,
    observed_at: str | None = None,
) -> Document:
    observed_at = observed_at or datetime.now(UTC).isoformat()
    indexed, findings = _discover(root)
    expected = {
        (str(target["id"]), minor) for target in expected_targets for minor in supported_minors()
    }
    findings.extend(f"unexpected target {key}" for key in sorted(indexed.keys() - expected))
    cells: list[Document] = []
    failed_evidence: list[Document] = []
    for target, python in sorted(expected):
        paths = indexed.get((target, python), [])
        if len(paths) != 1:
            findings.append(f"{target}/{python}: expected one target record, found {len(paths)}")
            continue
        identity = {
            "target": target,
            "python": python,
            "source_sha": source_sha,
            "run_id": run["id"],
            "run_attempt": attempt,
        }
        try:
            cell = _cell_record(paths[0], identity, jobs, observed_at)
            cell["evidence_path"] = str(Path(cell["evidence_path"]).relative_to(root))
            cells.append(cell)
        except (OSError, KeyError, TypeError, ValueError) as error:
            findings.append(f"{target}/{python}: {error}")
            failed_evidence.append(_failed_evidence(paths[0], root, target, python))
    companion_sets = {json.dumps(cell["companions"], sort_keys=True) for cell in cells}
    if len(companion_sets) > 1:
        findings.append("wheel targets used different companion artifacts")
    source_sets = {json.dumps(cell["source_install"]["sdists"], sort_keys=True) for cell in cells}
    if len(source_sets) > 1:
        findings.append("wheel targets used different source distributions")
    versions = {cell["postgres_version"] for cell in cells}
    if len(versions) > 1:
        findings.append(f"wheel targets used different PostgreSQL versions: {sorted(versions)}")
    return {
        "schema_version": 1,
        "status": "failed" if findings else "passed",
        "source_sha": source_sha,
        "run_id": str(run["id"]),
        "run_attempt": attempt,
        "expected_targets": len(expected),
        "validated_targets": len(cells),
        "findings": findings,
        "targets": cells,
        "failed_target_evidence": failed_evidence,
        "execution": execution_timings(jobs, run, observed_at),
    }


def _api(path: str) -> Any:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN is required to read the run's execution record")
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    request = urllib.request.Request(
        f"{api}/{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _ci_records(repository: str, run_id: str, attempt: int) -> tuple[Document, list[Document]]:
    prefix = f"repos/{repository}/actions/runs/{run_id}/attempts/{attempt}"
    run: Document = _api(prefix)
    jobs: list[Document] = []
    page = 1
    while True:
        found: list[Document] = _api(f"{prefix}/jobs?per_page=100&page={page}")["jobs"]
        jobs.extend(found)
        if len(found) < 100:
            return run, jobs
        page += 1


def render(summary: Document) -> str:
    execution = summary.get("execution", {})
    lines = [
        f"Wheel validation: **{summary['status']}**",
        "",
        f"Source `{summary['source_sha']}`; run {summary['run_id']}, "
        f"attempt {summary['run_attempt']}.",
        "",
        "| Target | Python | Setup (s) | Build/repair (s) | Binary (s) | C (s) | "
        "Source build (s) | Source binary (s) | Source C (s) | Queue (s) | Runner (s) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in summary.get("targets", []):
        phases = cell["timings"]
        drivers, job = cell["drivers"], cell["ci_job"]
        durations = [
            phases["setup_seconds"],
            phases["build_repair_seconds"],
            drivers["binary"]["elapsed_seconds"],
            drivers["c"]["elapsed_seconds"],
            cell["source_install"]["build_seconds"],
            cell["source_install"]["drivers"]["binary"]["elapsed_seconds"],
            cell["source_install"]["drivers"]["c"]["elapsed_seconds"],
            job["queue_seconds"],
            job["runner_seconds"],
        ]
        formatted = ["unknown" if value is None else f"{value:.2f}" for value in durations]
        lines.append(f"| {cell['target']} | {cell['python']} | {' | '.join(formatted)} |")
    lines.extend(
        [
            "",
            "Workflow elapsed at observation: "
            f"{execution.get('workflow_elapsed_observed_seconds')} s; "
            "aggregate observed runner time: "
            f"{execution.get('aggregate_runner_observed_seconds')} s.",
            "Final workflow and aggregate runner totals remain null until all jobs finish. "
            "Queue delay is unknown when a job has no creation timestamp. "
            "Parallel runner durations overlap and are not workflow elapsed time.",
        ]
    )
    if summary.get("findings"):
        lines.extend(["", *[f"- {finding}" for finding in summary["findings"]]])
    return "\n".join(lines) + "\n"


def write_summary(output: Path, summary: Document) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "summary.md").write_text(render(summary), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets", type=Path, default=TARGETS)
    parser.add_argument("--jobs", type=Path)
    parser.add_argument("--run", type=Path)
    args = parser.parse_args(argv)
    summary: Document = {
        "status": "failed",
        "source_sha": args.source_sha,
        "run_id": args.run_id,
        "run_attempt": args.attempt,
        "findings": [],
    }
    try:
        targets = current_targets(args.targets)
        if not targets:
            raise ValueError("target declaration names no current target")
        if len({target["id"] for target in targets}) != len(targets):
            raise ValueError("target declaration contains duplicate ids")
        if (args.jobs is None) != (args.run is None):
            raise ValueError("--jobs and --run must be supplied together")
        if args.jobs is not None and args.run is not None:
            run, jobs = _document(args.run), _document(args.jobs)["jobs"]
        else:
            run, jobs = _ci_records(args.repository, args.run_id, args.attempt)
        if str(run.get("id")) != args.run_id or int(run.get("run_attempt", 0)) != args.attempt:
            raise ValueError("execution record is from a different run or attempt")
        summary = summarize(args.root, targets, jobs, run, args.source_sha, args.attempt)
    except (OSError, KeyError, TypeError, ValueError) as error:
        summary["findings"].append(str(error))
    write_summary(args.output, summary)
    print(render(summary))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
