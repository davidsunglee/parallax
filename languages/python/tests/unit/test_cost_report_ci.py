from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from cost_report import CANONICAL_PORTFOLIO
from tests._support.repo import REPO_ROOT

VERIFY_JOB = "python-verify-cost"
SHIM_INTERPRETER = "/bin/sh"
STEP_SHELL = "bash"
STEP_SHELL_RUNNABLE = shutil.which(STEP_SHELL) is not None and Path(SHIM_INTERPRETER).exists()


def _workflow() -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")),
    )


def _job() -> dict[str, Any]:
    return cast("dict[str, Any]", _workflow()["jobs"][VERIFY_JOB])


def _steps(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["name"]: step for step in job["steps"] if "name" in step}


def test_ordinary_ci_verifies_committed_evidence_and_measures_nothing() -> None:
    workflow = _workflow()
    assert "python-report-cost" not in workflow["jobs"]
    job = _job()
    assert "continue-on-error" not in job
    assert "needs" not in job
    assert list(_steps(job)) == [
        "Identify the inspected head",
        "Verify committed evidence against head lock",
        "Check committed evidence against event merge lock",
    ]
    for step in job["steps"]:
        script = str(step.get("run", ""))
        assert "python-report-cost" not in script
        assert "--shard" not in script
        assert "--out" not in script
        assert not str(step.get("uses", "")).startswith("actions/upload-artifact@")
        assert not str(step.get("uses", "")).startswith("actions/download-artifact@")


@pytest.mark.skipif(
    not STEP_SHELL_RUNNABLE,
    reason=f"grades a Linux CI step body, which needs {STEP_SHELL} and a {SHIM_INTERPRETER} shim",
)
@pytest.mark.parametrize("fresh", [True, False])
def test_head_verification_failure_still_exposes_freshness_in_summary(
    tmp_path: Path, fresh: bool
) -> None:
    steps = _steps(_job())
    step = steps["Verify committed evidence against head lock"]
    assert "if" not in step
    assert f"--verify {CANONICAL_PORTFOLIO.as_posix()}" in step["run"]
    uv = tmp_path / "uv"
    freshness = "lock freshness matches" if fresh else "stale snapshot-delivery evidence"
    uv.write_text(
        f"#!{SHIM_INTERPRETER}\necho '{freshness}'\necho 'outside budget' >&2\nexit 1\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    summary = tmp_path / "summary.md"
    completed = subprocess.run(
        [STEP_SHELL, "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_STEP_SUMMARY": str(summary),
            "HEAD_SHA": "inspected-head",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    rendered = summary.read_text(encoding="utf-8")
    assert "head lock inspected-head" in rendered
    assert freshness in rendered
    assert "outside budget" in rendered


def test_pr_freshness_checks_event_merge_lock_without_moving_measurement_checkouts() -> None:
    job = _job()
    checkout = next(
        step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha || github.sha }}"
    assert checkout["with"]["fetch-depth"] == 0
    identify = _steps(job)["Identify the inspected head"]
    assert 'HEAD_SHA=$(git rev-parse HEAD)" >> "$GITHUB_ENV"' in identify["run"]
    step = _steps(job)["Check committed evidence against event merge lock"]
    assert step["if"] == "github.event_name == 'pull_request' && !cancelled()"
    assert step["env"]["MERGE_SHA"] == "${{ github.sha }}"
    script = step["run"]
    assert "event merge lock $MERGE_SHA" in script
    assert 'git show "$MERGE_SHA:languages/python/uv.lock"' in script
    assert f"--freshness-only {CANONICAL_PORTFOLIO.as_posix()}" in script
    assert '--lock-file "$RUNNER_TEMP/event-merge-uv.lock"' in script
    assert 'tee -a "$GITHUB_STEP_SUMMARY"' in script
    assert "git checkout" not in script
