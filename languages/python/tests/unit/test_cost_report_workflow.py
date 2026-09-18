from __future__ import annotations

from typing import Any, cast

import pytest
import yaml

import cost_report_adapter as adapter
from cost_report import LAYOUTS
from tests._support.repo import REPO_ROOT

WORKFLOW = REPO_ROOT / ".github" / "workflows" / adapter.WORKFLOW_FILE
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

ELIGIBLE = "github.event_name != 'pull_request' || github.event.label.name == 'cost-report'"
LABEL_EVENT = "github.event_name == 'pull_request' && github.event.label.name == 'cost-report'"
REQUESTED_REF = "${{ github.event.pull_request.head.sha || inputs.ref || github.sha }}"
RESOLVED_HEAD = "${{ needs.plan.outputs.head }}"
ATTEMPT = "${{ github.run_attempt }}"
TEMP = "${{ runner.temp }}/cost-report"
SAME_REPOSITORY = "github.event.pull_request.head.repo.full_name == github.repository"


def _workflow() -> dict[object, Any]:
    return cast("dict[object, Any]", yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))


def _triggers(workflow: dict[object, Any]) -> dict[str, Any]:
    """The ``on`` block, which YAML 1.1 parses as the boolean key ``True``."""
    return cast("dict[str, Any]", workflow["on"] if "on" in workflow else workflow[True])


def _job(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", _workflow()["jobs"][name])


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", job["steps"])


def _named(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in _steps(job) if step.get("name") == name)


def _using(job: dict[str, Any], action: str) -> list[dict[str, Any]]:
    return [step for step in _steps(job) if str(step.get("uses", "")).startswith(action)]


def _artifact(name: str) -> str:
    return name.format(attempt=ATTEMPT, shard="${{ matrix.shard }}")


# --------------------------------------------------------------------------- #
# Events, eligibility, and concurrency                                        #
# --------------------------------------------------------------------------- #
def test_the_report_answers_a_label_a_dispatch_and_the_nightly_and_never_a_push() -> None:
    workflow = _workflow()
    triggers = _triggers(workflow)
    assert set(triggers) == {"pull_request", "workflow_dispatch", "schedule"}
    assert triggers["pull_request"] == {"types": ["labeled"]}
    assert triggers["schedule"] == [{"cron": "0 6 * * *"}]
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"ref", "layout", "request-id"}
    assert inputs["ref"]["type"] == "string"
    assert inputs["ref"]["required"] is True
    assert inputs["layout"]["type"] == "choice"
    assert inputs["layout"]["options"] == list(LAYOUTS)
    assert inputs["layout"]["default"] == adapter.DEFAULT_LAYOUT
    assert inputs["request-id"]["required"] is False
    assert inputs["request-id"]["type"] == "string"
    assert "pull_request_target" not in WORKFLOW.read_text(encoding="utf-8")
    assert "${{ inputs.request-id }}" in workflow["run-name"]
    assert "${{ github.event_name }}" in workflow["run-name"]


def test_eligibility_is_the_event_expression_and_the_plan_alone_gates_on_it() -> None:
    workflow = _workflow()
    jobs = workflow["jobs"]
    assert list(jobs) == ["plan", "measure", "assemble", "cleanup"]
    assert jobs["plan"]["if"] == ELIGIBLE
    assert "if" not in jobs["measure"]
    assert jobs["measure"]["needs"] == "plan"
    assert jobs["assemble"]["if"] == f"always() && ({ELIGIBLE})"
    assert jobs["assemble"]["needs"] == ["plan", "measure"]
    assert jobs["cleanup"]["if"] == f"always() && {LABEL_EVENT}"
    assert jobs["cleanup"]["needs"] == ["plan", "measure", "assemble"]


def test_a_running_report_is_never_cancelled_and_the_group_is_the_request() -> None:
    workflow = _workflow()
    group = workflow["concurrency"]["group"]
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert group.startswith("cost-report-${{ github.event_name }}-")
    assert "github.event.pull_request.number || inputs.ref || github.ref_name" in group
    assert "github.ref }}" not in group
    assert "github.head_ref" not in group


def test_every_job_is_bounded_and_none_hides_its_outcome() -> None:
    for name, job in _workflow()["jobs"].items():
        assert "timeout-minutes" in job, name
        assert "continue-on-error" not in job, name
        assert job["runs-on"] == "ubuntu-latest", name
    assert _job("measure")["timeout-minutes"] == 300


# --------------------------------------------------------------------------- #
# Untrusted input: event values reach shell only through the environment      #
# --------------------------------------------------------------------------- #
def test_no_shell_step_interpolates_an_expression() -> None:
    for name, job in _workflow()["jobs"].items():
        for step in _steps(job):
            script = step.get("run")
            if script is None:
                continue
            assert "${{" not in script, (name, step.get("name"))
            assert "pull_request_target" not in script


def test_the_only_write_permission_is_the_cleanup_jobs_and_it_checks_nothing_out() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert "permissions" not in jobs["plan"]
    assert "permissions" not in jobs["measure"]
    assert jobs["assemble"]["permissions"] == {"contents": "read", "actions": "read"}
    assert jobs["cleanup"]["permissions"] == {"pull-requests": "write"}
    for step in _steps(jobs["cleanup"]):
        assert "uses" not in step
    tokens = [
        (name, step.get("name"))
        for name, job in jobs.items()
        for step in _steps(job)
        if "GH_TOKEN" in step.get("env", {})
    ]
    assert tokens == [
        ("assemble", "Obtain the previous nightly"),
        ("cleanup", "Remove the one-shot label"),
    ]


# --------------------------------------------------------------------------- #
# Plan: one resolved commit, the immutable request, the tool's shard ids      #
# --------------------------------------------------------------------------- #
def test_the_plan_checks_out_the_requested_ref_once_with_history_and_pins_it() -> None:
    job = _job("plan")
    (checkout,) = _using(job, "actions/checkout@")
    assert checkout["with"] == {"ref": REQUESTED_REF, "fetch-depth": 0}
    (uv,) = _using(job, "astral-sh/setup-uv@")
    assert uv["with"]["python-version"] == "3.14"
    assert _named(job, "Sync Python workspace (frozen)")["run"] == "uv sync --frozen"
    step = _named(job, "Pin the request and plan its shards")
    assert step["id"] == "plan"
    assert step["working-directory"] == "languages/python"
    assert set(step["env"]) == set(adapter.EVENT_VARIABLES)
    assert step["env"][adapter.REF_VARIABLE] == REQUESTED_REF
    assert step["env"][adapter.PULL_REQUEST_VARIABLE] == "${{ github.event.pull_request.number }}"
    assert step["env"][adapter.EVENT_BASE_VARIABLE] == "${{ github.event.pull_request.base.sha }}"
    assert step["env"][adapter.LAYOUT_VARIABLE] == "${{ inputs.layout }}"
    assert step["env"][adapter.REQUEST_ID_VARIABLE] == "${{ inputs.request-id }}"
    assert step["run"] == (
        "uv run python tools/cost_report_adapter.py plan "
        '--out "$RUNNER_TEMP/cost-report/request" >> "$GITHUB_OUTPUT"'
    )
    assert job["outputs"] == {
        name: f"${{{{ steps.plan.outputs.{name} }}}}"
        for name in ("shards", "head", "base", "layout", "request-id")
    }
    upload = _named(job, "Upload the request")
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"] == {
        "name": _artifact(adapter.REQUEST_ARTIFACT),
        "path": f"{TEMP}/request/",
        "if-no-files-found": "error",
    }
    assert "if" not in upload


# --------------------------------------------------------------------------- #
# Measure: one runner per planned shard, base then head, upload regardless    #
# --------------------------------------------------------------------------- #
def test_each_shard_measures_the_resolved_head_on_its_own_runner() -> None:
    job = _job("measure")
    assert job["strategy"] == {
        "fail-fast": False,
        "matrix": {"shard": "${{ fromJSON(needs.plan.outputs.shards) }}"},
    }
    (checkout,) = _using(job, "actions/checkout@")
    assert checkout["with"] == {"ref": RESOLVED_HEAD, "fetch-depth": 0}
    (request,) = _using(job, "actions/download-artifact@")
    assert request["with"] == {
        "name": _artifact(adapter.REQUEST_ARTIFACT),
        "path": f"{TEMP}/request/",
    }
    measure = _named(job, "Measure base then head")
    assert measure["env"] == {"SHARD": "${{ matrix.shard }}"}
    assert measure["working-directory"] == "languages/python"
    assert measure["run"] == (
        'uv run python tools/cost_report.py --shard "$SHARD" '
        '--request "$RUNNER_TEMP/cost-report/request/request.json" '
        '--out "$RUNNER_TEMP/cost-report/reports"'
    )
    assert "if" not in measure
    upload = _named(job, "Upload the shard")
    assert upload["if"] == "always()"
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"] == {
        "name": _artifact(adapter.SHARD_ARTIFACT),
        "path": f"{TEMP}/reports/",
    }
    names = [step.get("name") for step in _steps(job)]
    assert names.index("Measure base then head") < names.index("Upload the shard")
    assert not any("just" in str(step.get("run", "")) for step in _steps(job))


# --------------------------------------------------------------------------- #
# Assemble: always after the requested work, this attempt's artifacts alone   #
# --------------------------------------------------------------------------- #
def test_assembly_runs_after_any_measurement_outcome_over_this_attempts_artifacts() -> None:
    job = _job("assemble")
    diagnostic = _named(job, "Report a plan that did not complete")
    assert diagnostic["if"] == "needs.plan.result != 'success'"
    assert diagnostic["env"] == {
        "PLAN_RESULT": "${{ needs.plan.result }}",
        "MEASURE_RESULT": "${{ needs.measure.result }}",
    }
    assert "coverage of this run is unknown" in diagnostic["run"]
    assert diagnostic["run"].rstrip().endswith("exit 1")
    assert _steps(job)[0] is diagnostic
    (checkout,) = _using(job, "actions/checkout@")
    assert checkout["with"] == {"ref": RESOLVED_HEAD, "fetch-depth": 0}
    request, shards = _using(job, "actions/download-artifact@")
    assert request["with"] == {
        "name": _artifact(adapter.REQUEST_ARTIFACT),
        "path": f"{TEMP}/request/",
    }
    assert shards["with"] == {
        "pattern": f"cost-report-shard-*-attempt-{ATTEMPT}",
        "path": f"{TEMP}/inputs/",
        "merge-multiple": False,
    }
    plain = _named(job, "Assemble the shards")
    assert plain["if"] == "github.event_name != 'schedule'"
    assert plain["run"] == (
        'uv run python tools/cost_report.py --assemble "$RUNNER_TEMP/cost-report/inputs" '
        '--request "$RUNNER_TEMP/cost-report/request/request.json" '
        '--out "$RUNNER_TEMP/cost-report/assembled"'
    )
    nightly = _named(job, "Assemble the shards against the previous nightly")
    assert nightly["if"] == "github.event_name == 'schedule'"
    assert nightly["run"] == (
        'uv run python tools/cost_report.py --assemble "$RUNNER_TEMP/cost-report/inputs" '
        '--request "$RUNNER_TEMP/cost-report/request/request.json" '
        '--against "$RUNNER_TEMP/cost-report/previous" '
        '--out "$RUNNER_TEMP/cost-report/assembled"'
    )
    render = _named(job, "Render the assembled summary")
    assert render["if"] == "always() && needs.plan.result == 'success'"
    assert render["run"] == (
        'cat "$RUNNER_TEMP/cost-report/assembled/summary.md" >> "$GITHUB_STEP_SUMMARY"'
    )
    upload = _named(job, "Upload the assembly")
    assert upload["if"] == "always() && needs.plan.result == 'success'"
    assert upload["with"] == {
        "name": _artifact(adapter.ASSEMBLED_ARTIFACT),
        "path": f"{TEMP}/assembled/",
    }
    names = [step.get("name") for step in _steps(job)]
    assert names.index("Assemble the shards") < names.index("Render the assembled summary")
    assert names.index("Render the assembled summary") < names.index("Upload the assembly")


def test_a_nightly_obtains_its_predecessor_through_the_adapter_before_assembling() -> None:
    job = _job("assemble")
    history = _named(job, "Obtain the previous nightly")
    assert history["if"] == "github.event_name == 'schedule'"
    assert history["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert history["working-directory"] == "languages/python"
    assert history["run"] == (
        "uv run python tools/cost_report_adapter.py history "
        '--out "$RUNNER_TEMP/cost-report/previous"'
    )
    names = [step.get("name") for step in _steps(job)]
    assert names.index("Obtain the previous nightly") < names.index(
        "Assemble the shards against the previous nightly"
    )
    assert job["permissions"]["actions"] == "read"


# --------------------------------------------------------------------------- #
# Cleanup: the one-shot label, without a checkout                             #
# --------------------------------------------------------------------------- #
def test_the_label_is_removed_for_a_same_repository_request_and_reported_for_a_fork() -> None:
    job = _job("cleanup")
    remove = _named(job, "Remove the one-shot label")
    assert remove["if"] == SAME_REPOSITORY
    assert remove["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "GH_REPO": "${{ github.repository }}",
        "PULL_REQUEST": "${{ github.event.pull_request.number }}",
    }
    assert remove["run"] == 'gh pr edit "$PULL_REQUEST" --remove-label cost-report'
    fork = _named(job, "Report a fork's label as not removable")
    assert fork["if"] == SAME_REPOSITORY.replace("==", "!=")
    assert fork["env"] == {"PULL_REQUEST": "${{ github.event.pull_request.number }}"}
    assert "GH_TOKEN" not in fork["env"]
    assert '>> "$GITHUB_STEP_SUMMARY"' in fork["run"]
    assert "::warning::" in fork["run"]
    assert "re-adds it" in fork["run"]


# --------------------------------------------------------------------------- #
# Ordinary CI                                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("trigger", ["workflow_dispatch", "schedule"])
def test_ordinary_ci_verifies_only_and_carries_no_observation_trigger(trigger: str) -> None:
    ci = cast("dict[object, Any]", yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8")))
    assert trigger not in _triggers(ci)
    assert "python-report-cost" not in ci["jobs"]
    assert "python-verify-cost" in ci["jobs"]
