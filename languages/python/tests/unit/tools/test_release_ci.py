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
            "html_url": "https://github.com/owner/project/actions/runs/21",
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


def _retained(monkeypatch: pytest.MonkeyPatch, bundle: Path) -> dict[str, Any]:
    _fixtures(monkeypatch, bundle)
    result = ci.successful_ci(REPOSITORY, SOURCE)
    result["database"] = ci.database_evidence(REPOSITORY, bundle, result)
    (bundle / "ci.json").write_text(json.dumps(result))
    return result


def test_recovery_verifies_retained_evidence_after_remote_artifacts_expire(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _retained(monkeypatch, tmp_path)

    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("recovery must not query or download expiring workflow evidence")

    monkeypatch.setattr(ci, "gh_api", unavailable)
    monkeypatch.setattr(ci.subprocess, "check_output", unavailable)
    for artifact in captured["database"]["artifacts"]:
        artifact["expired"] = True
    (tmp_path / "ci.json").write_text(json.dumps(captured))
    result = ci.verify_retained(REPOSITORY, tmp_path, SOURCE)
    assert result["database"]["status"] == "passed"
    assert len(result["database"]["observations"]) == 8


@pytest.mark.parametrize("change", ["missing", "changed", "no_hash"])
def test_recovery_refuses_missing_or_changed_retained_archives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    captured = _retained(monkeypatch, tmp_path)
    artifact = captured["database"]["artifacts"][-1]
    path = tmp_path / "ci-database" / f"{artifact['name']}.zip"
    if change == "missing":
        path.unlink()
    elif change == "changed":
        path.write_bytes(path.read_bytes() + b"changed")
    else:
        del artifact["retained_sha256"]
        (tmp_path / "ci.json").write_text(json.dumps(captured))
    with pytest.raises((ValueError, FileNotFoundError)):
        ci.verify_retained(REPOSITORY, tmp_path, SOURCE)


@pytest.mark.parametrize(
    "change", ["source", "repository", "run_source", "event", "failed_job", "external_status"]
)
def test_recovery_revalidates_original_source_and_successful_ci(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    captured = _retained(monkeypatch, tmp_path)
    if change == "source":
        captured["source_sha"] = "b" * 40
    elif change == "repository":
        captured["repository"] = "other/project"
    elif change == "run_source":
        captured["run"]["head_sha"] = "b" * 40
    elif change == "event":
        captured["run"]["event"] = "schedule"
    elif change == "failed_job":
        captured["jobs"][0]["conclusion"] = "failure"
    else:
        captured["commit_status"] = {"statuses": [{"state": "failure"}], "state": "failure"}
    (tmp_path / "ci.json").write_text(json.dumps(captured))
    with pytest.raises(ValueError):
        ci.verify_retained(REPOSITORY, tmp_path, SOURCE)


def test_recovery_rechecks_database_observations_in_captured_archives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _retained(monkeypatch, tmp_path)
    artifact = captured["database"]["artifacts"][-1]
    path = tmp_path / "ci-database" / f"{artifact['name']}.zip"
    with zipfile.ZipFile(path) as archive:
        record = json.loads(archive.read("postgres-versions/postgres-123.json"))
    record["observed"] = "18.6"
    raw = _archive({"postgres-versions/postgres-123.json": record})
    path.write_bytes(raw)
    artifact["retained_sha256"] = hashlib.sha256(raw).hexdigest()
    (tmp_path / "ci.json").write_text(json.dumps(captured))
    with pytest.raises(ValueError, match="server version"):
        ci.verify_retained(REPOSITORY, tmp_path, SOURCE)


def test_recovery_cli_uses_only_retained_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _retained(monkeypatch, tmp_path)
    (tmp_path / "release-manifest.json").write_text(json.dumps({"source_sha": SOURCE}))

    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("retained verification must not contact GitHub")

    monkeypatch.setattr(ci, "gh_api", unavailable)
    monkeypatch.setattr(ci.subprocess, "check_output", unavailable)
    monkeypatch.setattr(
        "sys.argv",
        [
            "release_ci.py",
            "--repository",
            REPOSITORY,
            "--bundle",
            str(tmp_path),
            "--retained",
        ],
    )
    ci.main()
    assert json.loads((tmp_path / "ci.json").read_text())["database"]["status"] == "passed"
