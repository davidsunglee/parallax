from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests._support.repo import REPO_ROOT


def _job() -> Any:
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    return workflow["jobs"]["python-report-cost"]


def test_advisory_verification_preserves_collection_and_upload_after_failure() -> None:
    job = _job()
    assert job["continue-on-error"] is True
    steps = {step["name"]: step for step in job["steps"] if "name" in step}
    assert steps["Measure merge-base"]["if"] == (
        "github.event_name == 'pull_request' && !cancelled()"
    )
    assert steps["Measure head"]["if"] == "always() && !cancelled()"
    assert steps["Upload merge-base reports"]["if"] == (
        "github.event_name == 'pull_request' && always()"
    )
    assert steps["Upload head reports"]["if"] == "always()"
    assert steps["Render combined summary"]["if"] == "always()"
    assert "just python-report-cost" in steps["Measure head"]["run"]
    assert "python-report-cost" in steps["Measure merge-base"]["run"]
    for name in ("Upload merge-base reports", "Upload head reports"):
        assert steps[name]["uses"].startswith("actions/upload-artifact@")


@pytest.mark.parametrize("fresh", [True, False])
def test_head_verification_failure_still_exposes_freshness_in_summary(
    tmp_path: Path, fresh: bool
) -> None:
    steps = {step["name"]: step for step in _job()["steps"] if "name" in step}
    step = steps["Verify committed evidence against head lock"]
    assert "--verify languages/python/docs/snapshot-delivery-envelope/portfolio.json" in step["run"]
    uv = tmp_path / "uv"
    freshness = "lock freshness matches" if fresh else "stale snapshot-delivery evidence"
    uv.write_text(
        f"#!/bin/sh\necho '{freshness}'\necho 'outside budget' >&2\nexit 1\n", encoding="utf-8"
    )
    uv.chmod(0o755)
    summary = tmp_path / "summary.md"
    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
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
    step = next(
        step
        for step in job["steps"]
        if step.get("name") == "Check committed evidence against event merge lock"
    )
    assert step["if"] == "github.event_name == 'pull_request' && !cancelled()"
    assert step["env"]["MERGE_SHA"] == "${{ github.sha }}"
    script = step["run"]
    assert "event merge lock $MERGE_SHA" in script
    assert 'git show "$MERGE_SHA:languages/python/uv.lock"' in script
    assert (
        "--freshness-only languages/python/docs/snapshot-delivery-envelope/portfolio.json" in script
    )
    assert '--lock-file "$RUNNER_TEMP/event-merge-uv.lock"' in script
    assert 'tee -a "$GITHUB_STEP_SUMMARY"' in script
    assert "git checkout" not in script
