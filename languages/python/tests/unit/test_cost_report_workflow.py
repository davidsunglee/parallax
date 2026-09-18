from __future__ import annotations

from typing import Any, cast

import yaml

from tests._support.repo import REPO_ROOT

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "cost-report.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict[object, Any]:
    return cast("dict[object, Any]", yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))


def _triggers(workflow: dict[object, Any]) -> dict[str, Any]:
    """The ``on`` block, which YAML 1.1 parses as the boolean key ``True``."""
    return cast("dict[str, Any]", workflow["on"] if "on" in workflow else workflow[True])


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", job["steps"])


def _named(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in _steps(job) if step.get("name") == name)


def _using(job: dict[str, Any], action: str) -> dict[str, Any]:
    return next(step for step in _steps(job) if str(step.get("uses", "")).startswith(action))


def test_the_bootstrap_is_dispatched_by_ref_and_identifies_its_run_by_request() -> None:
    workflow = _workflow()
    triggers = _triggers(workflow)
    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"ref", "request-id"}
    assert inputs["ref"]["required"] is True
    assert inputs["ref"]["type"] == "string"
    assert inputs["request-id"]["required"] is False
    assert inputs["request-id"]["type"] == "string"
    assert "${{ inputs.ref }}" in workflow["run-name"]
    assert "${{ inputs.request-id }}" in workflow["run-name"]
    assert workflow["permissions"] == {"contents": "read"}


def test_the_bootstrap_never_cancels_a_running_report_and_bounds_a_hung_one() -> None:
    workflow = _workflow()
    assert workflow["concurrency"] == {
        "group": "cost-report-${{ inputs.ref }}",
        "cancel-in-progress": False,
    }
    assert set(workflow["jobs"]) == {"measure"}
    job = workflow["jobs"]["measure"]
    assert job["timeout-minutes"] == 300
    assert job["runs-on"] == "ubuntu-latest"
    assert job["env"] == {"UV_FROZEN": "1"}
    assert "continue-on-error" not in job


def test_the_bootstrap_measures_one_resolved_commit_with_the_frozen_setup() -> None:
    job = _workflow()["jobs"]["measure"]
    assert _using(job, "actions/checkout@")["with"]["ref"] == "${{ inputs.ref }}"
    assert _using(job, "astral-sh/setup-uv@")["with"]["python-version"] == "3.14"
    assert _using(job, "extractions/setup-just@")
    sync = _named(job, "Sync Python workspace (frozen)")
    assert sync["working-directory"] == "languages/python"
    assert sync["run"] == "uv sync --frozen"
    resolved = _named(job, "Identify the measured commit")
    assert resolved["id"] == "measured"
    assert 'sha=$MEASURED_SHA" >> "$GITHUB_OUTPUT"' in resolved["run"]
    assert "$(git rev-parse HEAD)" in resolved["run"]
    assert resolved["env"]["WORKFLOW_SHA"] == "${{ github.workflow_sha }}"
    assert resolved["env"]["REQUEST_ID"] == "${{ inputs.request-id }}"
    assert "${{ inputs" not in resolved["run"]
    measure = _named(job, "Measure head")
    assert measure["run"] == "just python-report-cost"
    assert "if" not in measure


def test_the_bootstrap_uploads_reports_and_renders_the_summary_after_any_outcome() -> None:
    job = _workflow()["jobs"]["measure"]
    steps = [step.get("name") for step in _steps(job)]
    assert (
        steps.index("Measure head") < steps.index("Upload reports") < steps.index("Render summary")
    )
    upload = _named(job, "Upload reports")
    assert upload["if"] == "always()"
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"] == {
        "name": "cost-report-sequential-${{ steps.measured.outputs.sha }}",
        "path": "languages/python/reports/",
    }
    summary = _named(job, "Render summary")
    assert summary["if"] == "always()"
    assert summary["run"] == 'cat languages/python/reports/summary.md >> "$GITHUB_STEP_SUMMARY"'


def test_ordinary_ci_keeps_its_report_job_until_the_observation_workflow_replaces_it() -> None:
    ci = cast("dict[object, Any]", yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8")))
    assert "python-report-cost" in ci["jobs"]
    assert "workflow_dispatch" not in _triggers(ci)
    assert "schedule" not in _triggers(ci)
