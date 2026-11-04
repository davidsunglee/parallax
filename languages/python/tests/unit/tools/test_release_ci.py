from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

import release_ci as ci

SOURCE = "a" * 40
REPOSITORY = "owner/project"


def _job(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "completed",
        "conclusion": "success",
        "run_id": 21,
        "run_attempt": 2,
        "started_at": "2026-11-04T10:00:00Z",
        "completed_at": "2026-11-04T10:01:00Z",
    }


def _result(selected: tuple[str, ...] = ("18.6", "18.7")) -> dict[str, Any]:
    return {
        "source_sha": SOURCE,
        "status": "passed",
        "run": {
            "id": 21,
            "run_attempt": 2,
            "head_sha": SOURCE,
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-11-04T09:59:00Z",
            "run_started_at": "2026-11-04T10:00:00Z",
            "updated_at": "2026-11-04T10:01:00Z",
        },
        "jobs": [
            _job("cloud-verdict"),
            *[
                _job(f"python-check-db ({runtime}, {shard}, {postgres})")
                for postgres in selected
                for runtime in ("3.14.10", "3.15.2")
                for shard in ("1/2", "2/2")
            ],
        ],
    }


def _archive(documents: dict[str, Any]) -> bytes:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        for name, value in documents.items():
            archive.writestr(name, json.dumps(value))
    return content.getvalue()


def _fixtures(
    monkeypatch: pytest.MonkeyPatch, bundle: Path, selected: tuple[str, ...] = ("18.6", "18.7")
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[int, dict[str, Any]]]:
    result = _result(selected)
    (bundle / "wheel-manifest.json").write_text(
        json.dumps({"targets": [{"postgres_version": selected[-1]}]})
    )
    identity = {"source_sha": SOURCE, "run_id": "21", "run_attempt": "2"}
    documents: dict[int, dict[str, Any]] = {
        10: {"postgres-matrix.json": {**identity, "postgres_versions": list(selected)}}
    }
    artifacts: list[dict[str, Any]] = [{"id": 10, "name": "postgres-matrix-21-2"}]
    for index, job in enumerate(result["jobs"][1:]):
        runtime, shard, postgres = job["name"][len("python-check-db (") : -1].split(", ")
        documents[index + 20] = {
            "postgres-versions/postgres-123.json": {
                **identity,
                "selected": postgres,
                "observed": f"{postgres} (Debian build)",
                "matched": True,
                "python_version": runtime,
                "shard": shard,
            }
        }
        artifacts.append({"id": index + 20, "name": f"db-test-timings-2-{index}"})

    def response(path: str) -> dict[str, Any]:
        if "/artifacts?" in path:
            return {"artifacts": artifacts}
        if "/jobs?" in path:
            return {"jobs": result["jobs"]}
        if "/workflows/" in path:
            return {"workflow_runs": [result["run"]]}
        if path.endswith("/status"):
            return {"statuses": [], "state": "pending"}
        raise AssertionError(path)

    def download(command: list[str]) -> bytes:
        assert command[:2] == ["gh", "api"]
        artifact_id = int(command[2].split("/")[-2])
        return _archive(documents[artifact_id])

    monkeypatch.setattr(ci, "gh_api", response)
    monkeypatch.setattr(ci.subprocess, "check_output", download)
    return result, artifacts, documents


def test_source_ci_and_all_database_cells_are_retained(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixtures(monkeypatch, tmp_path)
    result = ci.successful_ci(REPOSITORY, SOURCE)
    proof = ci.database_evidence(REPOSITORY, tmp_path, result)
    assert proof["status"] == "passed"
    assert len(proof["observations"]) == 8
    assert len(list((tmp_path / "ci-database").glob("*.zip"))) == 9
    assert json.loads((tmp_path / "ci-database/summary.json").read_text()) == proof


def test_floor_equals_latest_requires_only_one_postgres_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, _, _ = _fixtures(monkeypatch, tmp_path, ("18.6",))
    assert len(ci.database_evidence(REPOSITORY, tmp_path, result)["observations"]) == 4


@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch"])
def test_periodic_cloud_only_ci_cannot_satisfy_source_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, event: str
) -> None:
    result, _, _ = _fixtures(monkeypatch, tmp_path)
    result["run"]["event"] = event
    with pytest.raises(ValueError, match="no push/pull-request"):
        ci.successful_ci(REPOSITORY, SOURCE)


@pytest.mark.parametrize("change", ["wrong_source", "failed_run", "failed_job", "missing_cloud"])
def test_unsuccessful_or_wrong_source_ci_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    result, _, _ = _fixtures(monkeypatch, tmp_path)
    if change == "wrong_source":
        result["run"]["head_sha"] = "b" * 40
    elif change == "failed_run":
        result["run"]["conclusion"] = "failure"
    elif change == "failed_job":
        result["jobs"][1]["conclusion"] = "failure"
    else:
        result["jobs"].pop(0)
    with pytest.raises(ValueError):
        ci.successful_ci(REPOSITORY, SOURCE)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_sha", "b" * 40),
        ("run_id", "99"),
        ("run_attempt", "1"),
        ("selected", "18.8"),
        ("observed", "18.6"),
        ("matched", False),
        ("python_version", "3.16.0"),
        ("shard", "3/3"),
    ],
)
def test_mismatched_observation_refuses_the_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str, value: Any
) -> None:
    result, _, documents = _fixtures(monkeypatch, tmp_path)
    documents[24]["postgres-versions/postgres-123.json"][field] = value
    with pytest.raises(ValueError):
        ci.database_evidence(REPOSITORY, tmp_path, result)


@pytest.mark.parametrize("change", ["missing", "duplicate", "old_attempt", "expired", "empty"])
def test_incomplete_artifact_evidence_refuses_the_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    result, artifacts, documents = _fixtures(monkeypatch, tmp_path)
    if change == "missing":
        artifacts.pop()
    elif change == "duplicate":
        artifacts.append(copy.deepcopy(artifacts[-1]))
    elif change == "old_attempt":
        artifacts[-1]["name"] = "db-test-timings-1-7"
    elif change == "expired":
        artifacts[-1]["expired"] = True
    else:
        documents[27] = {}
    with pytest.raises(ValueError):
        ci.database_evidence(REPOSITORY, tmp_path, result)


def test_wheels_must_use_the_latest_main_suite_postgres(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, _, _ = _fixtures(monkeypatch, tmp_path)
    (tmp_path / "wheel-manifest.json").write_text(
        json.dumps({"targets": [{"postgres_version": "18.6"}]})
    )
    with pytest.raises(ValueError, match="latest PostgreSQL"):
        ci.database_evidence(REPOSITORY, tmp_path, result)


def test_retained_archive_digest_and_paths_are_verified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, artifacts, _ = _fixtures(monkeypatch, tmp_path)
    raw = _archive({"../postgres-matrix.json": {}})

    def download(command: list[str]) -> bytes:
        del command
        return raw

    monkeypatch.setattr(ci.subprocess, "check_output", download)
    artifacts[0]["digest"] = "sha256:wrong"
    with pytest.raises(ValueError, match="digest"):
        ci.database_evidence(REPOSITORY, tmp_path, result)
    artifacts[0]["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match="unsafe"):
        ci.database_evidence(REPOSITORY, tmp_path, result)


@pytest.mark.parametrize("change", ["one_cell", "one_runtime"])
def test_ci_job_matrix_cannot_drop_a_supported_minor_or_shard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    result, _, _ = _fixtures(monkeypatch, tmp_path)
    if change == "one_cell":
        result["jobs"].pop()
    else:
        result["jobs"] = [job for job in result["jobs"] if "3.14.10" not in job["name"]]
    with pytest.raises(ValueError):
        ci.database_evidence(REPOSITORY, tmp_path, result)
