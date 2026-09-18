"""Adapt one hosted cost-report run to the collector.

The workflow passes event values through environment variables and makes no
decision of its own. ``plan`` resolves those values against the checkout into
the immutable ``request.json`` every shard embeds, and prints the outputs the
workflow's other jobs read. ``history`` serves a scheduled run: it
selects the latest prior successful scheduled run of this workflow, downloads
that run's assembled artifact, requires the artifact's request to name the
commit the run measured, and fetches that object so assembly can validate the
previous evidence. Whatever it cannot obtain is stated in a marker the
assembly reads, never a reason the current run fails.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from cost_report import (
    ASSEMBLY_VERSION,
    HISTORY_FILE,
    HISTORY_VERSION,
    REQUEST_FILE,
    REQUEST_VERSION,
    SHARDS,
    WORKSPACE,
    Document,
    Request,
    git_head,
    plan_ids,
    validate_plan,
)

WORKFLOW_FILE: Final = "cost-report.yml"
REQUEST_ARTIFACT: Final = "cost-report-request-attempt-{attempt}"
SHARD_ARTIFACT: Final = "cost-report-shard-{shard}-attempt-{attempt}"
ASSEMBLED_ARTIFACT: Final = "cost-report-assembled-attempt-{attempt}"
"""Artifact names carry the run attempt, so a rerun can never collide with or
silently mix into an earlier attempt's immutable artifacts."""

EVENT_VARIABLE: Final = "GITHUB_EVENT_NAME"
REPOSITORY_VARIABLE: Final = "GITHUB_REPOSITORY"
RUN_ID_VARIABLE: Final = "GITHUB_RUN_ID"
RUN_ATTEMPT_VARIABLE: Final = "GITHUB_RUN_ATTEMPT"
WORKFLOW_SHA_VARIABLE: Final = "GITHUB_WORKFLOW_SHA"
BRANCH_VARIABLE: Final = "GITHUB_REF_NAME"
"""The run identity GitHub itself exports to every step."""

REF_VARIABLE: Final = "COST_REPORT_REF"
PULL_REQUEST_VARIABLE: Final = "COST_REPORT_PULL_REQUEST"
EVENT_BASE_VARIABLE: Final = "COST_REPORT_EVENT_BASE"
LAYOUT_VARIABLE: Final = "COST_REPORT_LAYOUT"
REQUEST_ID_VARIABLE: Final = "COST_REPORT_REQUEST_ID"
EVENT_VARIABLES: Final = (
    REF_VARIABLE,
    PULL_REQUEST_VARIABLE,
    EVENT_BASE_VARIABLE,
    LAYOUT_VARIABLE,
    REQUEST_ID_VARIABLE,
)
"""What the workflow's plan step passes from the event, each empty when the
event carries no such value."""

PULL_REQUEST_EVENT: Final = "pull_request"
SCHEDULE_EVENT: Final = "schedule"
DEFAULT_LAYOUT: Final = "sharded"
NIGHTLY_PAGE: Final = 50


def _git(arguments: Sequence[str], repo: Path | None) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo or WORKSPACE,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def ensure_commit(commit: str, repo: Path | None = None) -> None:
    """Fetch ``commit`` from ``origin`` unless the checkout already holds it;
    ``CalledProcessError`` when it cannot be obtained."""
    probe = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=repo or WORKSPACE,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0:
        return
    _git(["fetch", "--no-tags", "origin", commit], repo)


def merge_base(head: str, base: str, repo: Path | None = None) -> str:
    return _git(["merge-base", head, base], repo)


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "")
    if not value:
        raise ValueError(f"{name} is not set")
    return value


def _optional(environment: Mapping[str, str], name: str) -> str | None:
    return environment.get(name) or None


def _single_line(value: str, name: str) -> str:
    """A value that becomes one ``$GITHUB_OUTPUT`` record cannot span lines,
    or the lines after the first would be read as records of their own."""
    if value.splitlines() != [value]:
        raise ValueError(f"{name} {value!r} is not a single line")
    return value


def derived_request_id(repository: str, run_id: str, attempt: int) -> str:
    return f"{repository}/runs/{run_id}/attempts/{attempt}"


def pin_request(environment: Mapping[str, str], repo: Path | None = None) -> Request:
    """The immutable request the event asks for, resolved against the
    checkout: its head is the checked-out commit, and a pull request's base is
    the merge base of that head with the event's base commit."""
    event = _required(environment, EVENT_VARIABLE)
    repository = _required(environment, REPOSITORY_VARIABLE)
    run_id = _required(environment, RUN_ID_VARIABLE)
    attempt = int(_required(environment, RUN_ATTEMPT_VARIABLE))
    pull_request = _optional(environment, PULL_REQUEST_VARIABLE)
    event_base = _optional(environment, EVENT_BASE_VARIABLE)
    request_id = _optional(environment, REQUEST_ID_VARIABLE)
    if request_id is not None:
        _single_line(request_id, REQUEST_ID_VARIABLE)
    head = git_head(repo)
    base: str | None = None
    if event == PULL_REQUEST_EVENT:
        if pull_request is None or event_base is None:
            raise ValueError(
                f"a {PULL_REQUEST_EVENT} request names {PULL_REQUEST_VARIABLE} "
                f"and {EVENT_BASE_VARIABLE}"
            )
        ensure_commit(event_base, repo)
        base = merge_base(head, event_base, repo)
    elif pull_request is not None or event_base is not None:
        raise ValueError(f"a {event} request names no pull request and no event base")
    return Request.from_document(
        {
            "schemaVersion": REQUEST_VERSION,
            "requestId": request_id or derived_request_id(repository, run_id, attempt),
            "event": event,
            "requestedRef": _required(environment, REF_VARIABLE),
            "headCommit": head,
            "baseCommit": base,
            "eventBaseCommit": event_base,
            "pullRequest": int(pull_request) if pull_request is not None else None,
            "layout": _optional(environment, LAYOUT_VARIABLE) or DEFAULT_LAYOUT,
            "workflowCommit": _required(environment, WORKFLOW_SHA_VARIABLE),
            "runId": run_id,
            "runAttempt": attempt,
        }
    )


@dataclass(frozen=True, slots=True)
class Plan:
    request: Request
    shards: list[str]

    def outputs(self) -> str:
        """The ``$GITHUB_OUTPUT`` records the workflow's other jobs read."""
        lines = (
            ("shards", json.dumps(self.shards)),
            ("head", self.request.head_commit),
            ("base", self.request.base_commit or ""),
            ("layout", self.request.layout),
            ("request-id", self.request.request_id),
        )
        return "".join(f"{name}={value}\n" for name, value in lines)


def plan(environment: Mapping[str, str], out: Path, repo: Path | None = None) -> Plan:
    """Pin the request under ``out`` and answer the shard ids its layout runs."""
    validate_plan(SHARDS)
    request = pin_request(environment, repo)
    out.mkdir(parents=True, exist_ok=True)
    request.write(out / REQUEST_FILE)
    return Plan(request, plan_ids(request.layout))


# --------------------------------------------------------------------------- #
# The previous nightly a scheduled run compares with                          #
# --------------------------------------------------------------------------- #
type Gh = Callable[[Sequence[str]], tuple[int, str, str]]


def run_gh(arguments: Sequence[str]) -> tuple[int, str, str]:
    """``gh`` with ``arguments``, answering its exit status and both streams;
    a ``gh`` that cannot start answers 127."""
    try:
        completed = subprocess.run(["gh", *arguments], capture_output=True, text=True, check=False)
    except OSError as error:
        return (127, "", str(error))
    return (completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True, slots=True)
class NightlyRun:
    id: str
    attempt: int
    head_commit: str
    created_at: str

    def document(self) -> dict[str, object]:
        return {
            "id": self.id,
            "attempt": self.attempt,
            "headCommit": self.head_commit,
            "createdAt": self.created_at,
        }


def _nightly_run(fields: Mapping[str, object]) -> NightlyRun | None:
    identifier = fields.get("id")
    attempt = fields.get("run_attempt")
    head = fields.get("head_sha")
    created = fields.get("created_at")
    if (
        isinstance(identifier, bool)
        or not isinstance(identifier, int | str)
        or isinstance(attempt, bool)
        or not isinstance(attempt, int)
        or not isinstance(head, str)
        or not isinstance(created, str)
    ):
        return None
    return NightlyRun(str(identifier), attempt, head, created)


def previous_nightly(runs: Sequence[object], current_run_id: str) -> NightlyRun | None:
    """The latest successful scheduled run among ``runs`` other than the
    current one: newest creation first, the higher run id breaking a tie."""
    candidates: list[NightlyRun] = []
    for entry in runs:
        if not isinstance(entry, Mapping):
            continue
        fields = cast("Mapping[str, object]", entry)
        if fields.get("event") != SCHEDULE_EVENT or fields.get("conclusion") != "success":
            continue
        run = _nightly_run(fields)
        if run is not None and run.id != current_run_id:
            candidates.append(run)
    if not candidates:
        return None
    return max(candidates, key=lambda run: (run.created_at, int(run.id) if run.id.isdigit() else 0))


@dataclass(frozen=True, slots=True)
class HistorySelection:
    """What ``history`` found: the run it selected, the artifact it obtained,
    or the reason it obtained none."""

    run: NightlyRun | None
    artifact: str | None
    reason: str | None

    @property
    def available(self) -> bool:
        return self.reason is None

    def document(self) -> dict[str, object]:
        return {
            "schemaVersion": HISTORY_VERSION,
            "workflow": WORKFLOW_FILE,
            "run": self.run.document() if self.run is not None else None,
            "artifact": self.artifact,
            "reason": self.reason,
        }

    def describe(self) -> str:
        if self.reason is not None:
            return f"previous nightly unavailable: {self.reason}"
        assert self.run is not None
        return (
            f"previous nightly: run {self.run.id} attempt {self.run.attempt} "
            f"measured {self.run.head_commit}, artifact {self.artifact}"
        )


class _Unobtainable(Exception):
    """Why the previous nightly's assembly could not be obtained."""


def _api(gh: Gh, path: str) -> object:
    code, stdout, stderr = gh(["api", path])
    if code != 0:
        raise _Unobtainable(f"gh api {path} exited {code}: {stderr.strip() or stdout.strip()}")
    try:
        return cast("object", json.loads(stdout))
    except ValueError as error:
        raise _Unobtainable(f"gh api {path} answered no JSON: {error}") from error


def _listed(answer: object, key: str) -> list[object]:
    listed = cast("Mapping[str, object]", answer).get(key) if isinstance(answer, Mapping) else None
    if not isinstance(listed, list):
        raise _Unobtainable(f"the answer holds no {key} list")
    return cast("list[object]", listed)


def _artifact_state(artifacts: Sequence[object], name: str) -> bool | None:
    """Whether the named artifact is expired, or ``None`` when the run has
    none of that name."""
    for entry in artifacts:
        if not isinstance(entry, Mapping):
            continue
        fields = cast("Mapping[str, object]", entry)
        if fields.get("name") == name:
            return fields.get("expired") is True
    return None


def _artifact_head(directory: Path) -> str:
    """The head commit the downloaded assembly's request names."""
    portfolio = directory / "portfolio.json"
    try:
        document = cast("object", json.loads(portfolio.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        raise _Unobtainable(f"the artifact holds no readable portfolio.json: {error}") from error
    if not isinstance(document, Mapping):
        raise _Unobtainable("the artifact's portfolio.json is not an object")
    fields = cast("Document", document)
    if fields.get("schemaVersion") != ASSEMBLY_VERSION:
        raise _Unobtainable(
            f"the artifact's portfolio.json has schemaVersion "
            f"{fields.get('schemaVersion')!r}, expected {ASSEMBLY_VERSION}"
        )
    try:
        return Request.from_document(fields.get("request")).head_commit
    except (KeyError, TypeError, ValueError) as error:
        raise _Unobtainable(f"the artifact's request does not decode: {error}") from error


def select_history(
    environment: Mapping[str, str],
    out: Path,
    gh: Gh = run_gh,
    repo: Path | None = None,
) -> HistorySelection:
    """Obtain the previous nightly's assembled artifact under ``out`` and
    record the selection there, stating instead of failing whatever could not
    be obtained."""
    repository = _required(environment, REPOSITORY_VARIABLE)
    current = _required(environment, RUN_ID_VARIABLE)
    branch = _required(environment, BRANCH_VARIABLE)
    run: NightlyRun | None = None
    artifact: str | None = None
    try:
        listing = _api(
            gh,
            f"repos/{repository}/actions/workflows/{WORKFLOW_FILE}/runs"
            f"?event={SCHEDULE_EVENT}&branch={branch}&status=success&per_page={NIGHTLY_PAGE}",
        )
        run = previous_nightly(_listed(listing, "workflow_runs"), current)
        if run is None:
            raise _Unobtainable(
                f"no prior successful {SCHEDULE_EVENT} run of {WORKFLOW_FILE} on {branch}"
            )
        artifact = ASSEMBLED_ARTIFACT.format(attempt=run.attempt)
        inventory = _api(gh, f"repos/{repository}/actions/runs/{run.id}/artifacts?per_page=100")
        expired = _artifact_state(_listed(inventory, "artifacts"), artifact)
        if expired is None:
            raise _Unobtainable(f"run {run.id} has no artifact {artifact}")
        if expired:
            raise _Unobtainable(f"artifact {artifact} of run {run.id} has expired")
        _obtain(gh, repository, run, artifact, out, repo)
    except _Unobtainable as why:
        selection = HistorySelection(run, artifact, str(why))
    else:
        selection = HistorySelection(run, artifact, None)
    out.mkdir(parents=True, exist_ok=True)
    (out / HISTORY_FILE).write_text(
        json.dumps(selection.document(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return selection


def _obtain(
    gh: Gh, repository: str, run: NightlyRun, artifact: str, out: Path, repo: Path | None
) -> None:
    with tempfile.TemporaryDirectory(prefix="parallax-history-") as scratch:
        staging = Path(scratch) / "previous"
        code, stdout, stderr = gh(
            [
                "run",
                "download",
                run.id,
                "--repo",
                repository,
                "--name",
                artifact,
                "--dir",
                str(staging),
            ]
        )
        if code != 0:
            raise _Unobtainable(
                f"downloading {artifact} exited {code}: {stderr.strip() or stdout.strip()}"
            )
        head = _artifact_head(staging)
        if head != run.head_commit:
            raise _Unobtainable(
                f"the artifact answers a request for {head}, the run measured {run.head_commit}"
            )
        try:
            ensure_commit(run.head_commit, repo)
        except subprocess.CalledProcessError as error:
            raise _Unobtainable(
                f"the producing commit {run.head_commit} could not be fetched: "
                f"{_detail(error) or error}"
            ) from error
        shutil.copytree(staging, out, dirs_exist_ok=True)


def _detail(error: subprocess.CalledProcessError) -> str:
    stderr = cast("object", error.stderr)
    return stderr.strip() if isinstance(stderr, str) else ""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planned = commands.add_parser("plan", help="pin the request and print the run's outputs")
    planned.add_argument("--out", type=Path, required=True, help="where request.json is written")
    history = commands.add_parser("history", help="obtain the previous nightly's assembly")
    history.add_argument("--out", type=Path, required=True, help="where the assembly lands")
    args = parser.parse_args(argv)
    if args.command == "plan":
        try:
            pinned = plan(os.environ, args.out)
        except (ValueError, subprocess.CalledProcessError) as error:
            detail = _detail(error) if isinstance(error, subprocess.CalledProcessError) else ""
            print(
                f"the request cannot be pinned: {error}{': ' + detail if detail else ''}",
                file=sys.stderr,
            )
            return 1
        print(pinned.outputs(), end="")
        return 0
    selection = select_history(os.environ, args.out, run_gh)
    print(selection.describe())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
