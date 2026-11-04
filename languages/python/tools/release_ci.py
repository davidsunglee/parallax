"""Require successful source CI and retain its complete database compatibility proof."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import time
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

from interpreter_matrix import supported_minors
from postgres_matrix import versions
from release_setup import gh_api
from wheel_evidence import execution_timings

type Document = dict[str, Any]
type Cell = tuple[str, str, str]
_DATABASE_JOB = re.compile(
    r"python-check-db \((?P<python>3\.\d+\.\d+), (?P<shard>\d+/\d+), (?P<postgres>18\.\d+)\)"
)


def _pages(path: str, field: str) -> list[Document]:
    collected: list[Document] = []
    page = 1
    while True:
        batch: list[Document] = gh_api(f"{path}?per_page=100&page={page}")[field]
        collected.extend(batch)
        if len(batch) < 100:
            return collected
        page += 1


def _successful_run(run: Document, source: str) -> None:
    if run["head_sha"] != source or run["event"] not in ("push", "pull_request"):
        raise ValueError("CI run does not validate the candidate source")
    if run["status"] != "completed" or run["conclusion"] != "success":
        raise ValueError(f"CI {run['id']} is {run['status']}/{run['conclusion']}")


def _successful_checks(jobs: Sequence[Document], status: Document) -> None:
    failed = [
        job["name"]
        for job in jobs
        if job["status"] != "completed" or job["conclusion"] not in ("success", "skipped")
    ]
    verdicts = [job for job in jobs if job["name"] == "cloud-verdict"]
    if failed or len(verdicts) != 1 or verdicts[0]["conclusion"] != "success":
        raise ValueError(f"CI has failed or missing gates: {failed}")
    if status["statuses"] and status["state"] != "success":
        raise ValueError("external commit status checks have not succeeded")


def successful_ci(repository: str, source: str) -> Document:
    if not re.fullmatch("[0-9a-f]{40}", source):
        raise ValueError("source must be a full commit SHA")
    prefix = f"repos/{repository}"
    runs = gh_api(f"{prefix}/actions/workflows/ci.yml/runs?head_sha={source}&per_page=100")[
        "workflow_runs"
    ]
    candidates = [
        run
        for run in runs
        if run["head_sha"] == source and run["event"] in ("push", "pull_request")
    ]
    if not candidates:
        raise ValueError("no push/pull-request CI run exists for candidate source")
    run = max(candidates, key=lambda candidate: candidate["id"])
    _successful_run(run, source)
    jobs = _pages(f"{prefix}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs", "jobs")
    status = gh_api(f"{prefix}/commits/{source}/status")
    _successful_checks(jobs, status)
    return {
        "repository": repository,
        "source_sha": source,
        "status": "passed",
        "run": run,
        "jobs": jobs,
        "commit_status": status,
        "timings": execution_timings(jobs, run, run["updated_at"]),
    }


def _identity(document: Document, result: Document) -> None:
    expected = {
        "source_sha": result["source_sha"],
        "run_id": result["run"]["id"],
        "run_attempt": result["run"]["run_attempt"],
    }
    for key, value in expected.items():
        if str(document.get(key)) != str(value):
            raise ValueError(f"database evidence has mismatched {key}")


def _job_cells(jobs: Sequence[Document], selected: Sequence[str]) -> set[Cell]:
    cells: set[Cell] = set()
    for job in jobs:
        if not str(job["name"]).startswith("python-check-db"):
            continue
        match = _DATABASE_JOB.fullmatch(job["name"])
        if match is None or job["conclusion"] != "success":
            raise ValueError("main database suite has an unsuccessful or unrecognized cell")
        cell = match["postgres"], match["python"], match["shard"]
        if cell in cells:
            raise ValueError("main database suite has a duplicate cell")
        cells.add(cell)
    runtimes = {cell[1] for cell in cells}
    if {".".join(runtime.split(".")[:2]) for runtime in runtimes} != set(supported_minors()):
        raise ValueError("main database suite does not cover every supported Python minor")
    if len(runtimes) != len(supported_minors()):
        raise ValueError("main database suite has inconsistent Python patch versions")
    shards = {cell[2] for cell in cells}
    totals = {int(shard.split("/")[1]) for shard in shards}
    if len(totals) != 1:
        raise ValueError("main database suite has inconsistent shard counts")
    total = totals.pop()
    if total <= 0 or shards != {f"{index}/{total}" for index in range(1, total + 1)}:
        raise ValueError("main database suite is missing a shard")
    expected = {
        (postgres, runtime, shard)
        for postgres in selected
        for runtime in runtimes
        for shard in shards
    }
    if cells != expected:
        raise ValueError("main database suite is missing a PostgreSQL/Python/shard combination")
    return cells


def _archive_bytes(repository: str, artifact: Document, output: Path, retained: bool) -> bytes:
    path = output / f"{artifact['name']}.zip"
    if retained:
        expected = artifact.get("retained_sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("retained database evidence lacks its captured archive hash")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("retained database evidence archive hash differs from its capture")
    else:
        if artifact.get("expired"):
            raise ValueError(f"database evidence artifact {artifact['name']} has expired")
        raw = subprocess.check_output(
            ["gh", "api", f"repos/{repository}/actions/artifacts/{artifact['id']}/zip"]
        )
    checksum = hashlib.sha256(raw).hexdigest()
    declared = artifact.get("digest")
    if declared is not None and declared != f"sha256:{checksum}":
        raise ValueError("database evidence archive hash differs from GitHub's digest")
    if not retained:
        output.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        artifact["retained_sha256"] = checksum
    return raw


def _archive(
    repository: str, artifact: Document, output: Path, *, retained: bool = False
) -> list[tuple[str, Document]]:
    raw = _archive_bytes(repository, artifact, output, retained)
    documents: list[tuple[str, Document]] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                raise ValueError("database evidence archive contains an unsafe path")
            if member.is_dir() or path.suffix != ".json":
                continue
            if path.name == "postgres-matrix.json" or (
                "postgres-versions" in path.parts and path.name.startswith("postgres-")
            ):
                document = json.loads(archive.read(member))
                if not isinstance(document, dict):
                    raise ValueError("database evidence must contain JSON objects")
                documents.append((member.filename, cast("Document", document)))
    return documents


def _selection(documents: list[tuple[str, Document]], result: Document) -> Document:
    if len(documents) != 1 or PurePosixPath(documents[0][0]).name != "postgres-matrix.json":
        raise ValueError("database matrix artifact must contain exactly one selection record")
    selection = documents[0][1]
    _identity(selection, result)
    raw_selected: Any = selection["postgres_versions"]
    if not isinstance(raw_selected, list) or not raw_selected:
        raise ValueError("database matrix selection is invalid")
    selected = cast("list[Any]", raw_selected)
    if any(not isinstance(version, str) for version in selected):
        raise ValueError("database matrix selection is invalid")
    if versions(selected[-1]) != selected:
        raise ValueError("database matrix must contain unique supported floor/latest releases")
    return selection


def _observations(
    repository: str,
    artifacts: Sequence[Document],
    output: Path,
    result: Document,
    expected: set[Cell],
    *,
    retained: bool = False,
) -> list[Document]:
    observed: set[Cell] = set()
    observations: list[Document] = []
    for artifact in artifacts:
        records = _archive(repository, artifact, output, retained=retained)
        if not records:
            raise ValueError("database test artifact has no server-version observations")
        artifact_cells: set[Cell] = set()
        for _path, record in records:
            _identity(record, result)
            if record.get("matched") is not True or str(record.get("observed", "")).split()[
                0:1
            ] != [record.get("selected")]:
                raise ValueError("database server version does not match the selected release")
            cell = record["selected"], record["python_version"], record["shard"]
            if cell not in expected:
                raise ValueError("database observation is not a required CI cell")
            artifact_cells.add(cell)
            observations.append(record)
        if len(artifact_cells) != 1 or observed & artifact_cells:
            raise ValueError("database evidence artifacts must identify distinct main-suite cells")
        observed.update(artifact_cells)
    if observed != expected:
        raise ValueError("database evidence is missing a required main-suite cell")
    return observations


def database_evidence(
    repository: str, bundle: Path, result: Document, *, retained: bool = False
) -> Document:
    run = result["run"]
    attempt = run["run_attempt"]
    artifacts = (
        result["database"]["artifacts"]
        if retained
        else _pages(f"repos/{repository}/actions/runs/{run['id']}/artifacts", "artifacts")
    )
    matrix_name = f"postgres-matrix-{run['id']}-{attempt}"
    matrix_artifacts = [artifact for artifact in artifacts if artifact["name"] == matrix_name]
    test_artifacts = [
        artifact
        for artifact in artifacts
        if re.fullmatch(rf"db-test-timings-{attempt}-\d+", artifact["name"])
    ]
    if len(matrix_artifacts) != 1 or not test_artifacts:
        raise ValueError("successful CI has no complete retained database evidence")
    if len({artifact["name"] for artifact in test_artifacts}) != len(test_artifacts):
        raise ValueError("database evidence has duplicate artifact names")
    output = bundle / "ci-database"
    documents = _archive(repository, matrix_artifacts[0], output, retained=retained)
    selection = _selection(documents, result)
    selected = selection["postgres_versions"]
    wheel = json.loads((bundle / "wheel-manifest.json").read_text(encoding="utf-8"))
    if {target["postgres_version"] for target in wheel["targets"]} != {selected[-1]}:
        raise ValueError(
            "wheel validation did not use the latest PostgreSQL tested by the main suite"
        )
    expected = _job_cells(result["jobs"], selected)
    if len(test_artifacts) != len(expected):
        raise ValueError(
            "database evidence artifact count differs from successful main-suite cells"
        )
    observations = _observations(
        repository, test_artifacts, output, result, expected, retained=retained
    )
    proof = {
        "status": "passed",
        "selection": selection,
        "observations": observations,
        "artifacts": [*matrix_artifacts, *test_artifacts],
    }
    (output / "summary.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


def verify_retained(repository: str, bundle: Path, source: str) -> Document:
    """Recheck evidence recovered from the workflow's verified candidate archive."""
    result: Document = json.loads((bundle / "ci.json").read_text(encoding="utf-8"))
    if (
        result.get("repository") != repository
        or result.get("source_sha") != source
        or result.get("status") != "passed"
        or result.get("database", {}).get("status") != "passed"
    ):
        raise ValueError("retained CI does not match the candidate repository/source")
    _successful_run(result["run"], source)
    _successful_checks(result["jobs"], result["commit_status"])
    result["database"] = database_evidence(repository, bundle, result, retained=True)
    return result


def _wait_for_ci(repository: str, source: str, attempts: int) -> Document:
    for attempt in range(attempts):
        try:
            return successful_ci(repository, source)
        except ValueError as error:
            print(str(error), flush=True)
            if attempt + 1 == attempts:
                raise
            time.sleep(30)
    raise ValueError("no successful CI result")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=120)
    parser.add_argument("--retained", action="store_true")
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be positive")
    manifest = json.loads((args.bundle / "release-manifest.json").read_text(encoding="utf-8"))
    if args.retained:
        result = verify_retained(args.repository, args.bundle, manifest["source_sha"])
    else:
        result = _wait_for_ci(args.repository, manifest["source_sha"], args.attempts)
        result["database"] = database_evidence(args.repository, args.bundle, result)
    (args.bundle / "ci.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"Validated source {manifest['source_sha']} against successful CI "
        f"{result['run']['html_url']}"
    )


if __name__ == "__main__":
    main()
