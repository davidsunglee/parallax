from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

import cost_report
import cost_report_adapter as adapter
from cost_report import (
    HEAD,
    HISTORY_FILE,
    REQUEST_FILE,
    SHARDS,
    History,
    Request,
    assemble,
    discover,
    plan_ids,
    write_assembly,
)
from parallax.conformance.budget import BudgetContract
from tests.unit.tools._cost_report_support import (
    clean,
    member_envelopes,
    shard_envelopes,
    write_capture,
)

type Document = dict[str, Any]

WORKFLOW_SHA = "f" * 40


@pytest.fixture(scope="module")
def contract() -> BudgetContract:
    return BudgetContract.load()


@pytest.fixture(scope="module")
def head_commit() -> str:
    return cost_report.git_head()


@pytest.fixture(scope="module")
def sliced(contract: BudgetContract) -> dict[str, Document]:
    """Each planned shard's clean envelope, keyed by shard id."""
    return shard_envelopes(
        {
            subject: clean(document, contract)
            for subject, document in member_envelopes(contract).items()
        },
        contract,
    )


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "cost@example.invalid")
    _git(repo, "config", "user.name", "Cost Report")
    _commit(repo, "root")
    return repo


def _environment(event: str, **values: str) -> dict[str, str]:
    environment = {
        adapter.EVENT_VARIABLE: event,
        adapter.REPOSITORY_VARIABLE: "owner/parallax",
        adapter.RUN_ID_VARIABLE: "100",
        adapter.RUN_ATTEMPT_VARIABLE: "2",
        adapter.WORKFLOW_SHA_VARIABLE: WORKFLOW_SHA,
        adapter.BRANCH_VARIABLE: "main",
        adapter.REF_VARIABLE: "requested",
        adapter.PULL_REQUEST_VARIABLE: "",
        adapter.EVENT_BASE_VARIABLE: "",
        adapter.LAYOUT_VARIABLE: "",
        adapter.REQUEST_ID_VARIABLE: "",
    }
    environment.update(values)
    return environment


# --------------------------------------------------------------------------- #
# Plan: the immutable request from event values and the checkout             #
# --------------------------------------------------------------------------- #
def test_a_pull_request_plan_pins_the_head_and_the_merge_base_from_the_event(
    tmp_path: Path, repository: Path
) -> None:
    root = _git(repository, "rev-parse", "HEAD")
    _git(repository, "checkout", "-q", "-b", "feature")
    head = _commit(repository, "feature")
    _git(repository, "checkout", "-q", "main")
    event_base = _commit(repository, "main-moved")
    _git(repository, "checkout", "-q", head)
    environment = _environment(
        "pull_request",
        **{
            adapter.REF_VARIABLE: head,
            adapter.PULL_REQUEST_VARIABLE: "7",
            adapter.EVENT_BASE_VARIABLE: event_base,
        },
    )
    out = tmp_path / "request"
    planned = adapter.plan(environment, out, repository)
    request = planned.request
    assert request.event == "pull_request"
    assert request.head_commit == head
    assert request.base_commit == root
    assert request.event_base_commit == event_base
    assert request.pull_request == 7
    assert request.is_pull_request
    assert request.layout == "sharded"
    assert request.requested_ref == head
    assert request.workflow_commit == WORKFLOW_SHA
    assert request.run == ("owner/parallax/runs/100/attempts/2", "100", 2)
    assert planned.shards == plan_ids("sharded") == [shard.id for shard in SHARDS]
    assert Request.load(out / REQUEST_FILE) == request
    assert planned.outputs() == (
        f"shards={json.dumps(planned.shards)}\n"
        f"head={head}\n"
        f"base={root}\n"
        "layout=sharded\n"
        "request-id=owner/parallax/runs/100/attempts/2\n"
    )


def test_a_dispatch_keeps_the_callers_request_id_and_layout_and_names_no_base(
    tmp_path: Path, repository: Path
) -> None:
    head = _git(repository, "rev-parse", "HEAD")
    environment = _environment(
        "workflow_dispatch",
        **{
            adapter.REF_VARIABLE: "main",
            adapter.LAYOUT_VARIABLE: "sequential",
            adapter.REQUEST_ID_VARIABLE: "experiment-1",
        },
    )
    planned = adapter.plan(environment, tmp_path / "request", repository)
    assert planned.shards == ["all"]
    assert planned.request.request_id == "experiment-1"
    assert planned.request.requested_ref == "main"
    assert planned.request.head_commit == head
    assert planned.request.base_commit is None
    assert planned.request.event_base_commit is None
    assert planned.request.pull_request is None
    assert not planned.request.is_pull_request
    assert "base=\n" in planned.outputs()
    assert "layout=sequential\n" in planned.outputs()


def test_a_scheduled_plan_measures_head_only_under_a_derived_id(
    tmp_path: Path, repository: Path
) -> None:
    planned = adapter.plan(_environment("schedule"), tmp_path / "request", repository)
    assert planned.request.event == "schedule"
    assert planned.request.base_commit is None
    assert planned.request.request_id == "owner/parallax/runs/100/attempts/2"
    assert planned.request.layout == "sharded"
    assert planned.shards == plan_ids("sharded")


def test_an_event_base_the_checkout_lacks_is_fetched_from_origin(
    tmp_path: Path, repository: Path
) -> None:
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(repository), str(clone))
    _git(clone, "config", "user.email", "cost@example.invalid")
    _git(clone, "config", "user.name", "Cost Report")
    _git(clone, "checkout", "-q", "-b", "feature")
    head = _commit(clone, "feature")
    moved = _commit(repository, "main-moved")
    assert (
        subprocess.run(
            ["git", "cat-file", "-e", f"{moved}^{{commit}}"], cwd=clone, check=False
        ).returncode
        != 0
    )
    environment = _environment(
        "pull_request",
        **{
            adapter.REF_VARIABLE: head,
            adapter.PULL_REQUEST_VARIABLE: "8",
            adapter.EVENT_BASE_VARIABLE: moved,
        },
    )
    request = adapter.pin_request(environment, clone)
    assert request.base_commit == _git(repository, "rev-parse", "main~1")
    assert request.event_base_commit == moved


def test_a_request_that_cannot_be_pinned_names_what_is_missing(repository: Path) -> None:
    unfetchable = "0" * 40
    cases: list[tuple[dict[str, str], type[Exception], str]] = [
        (_environment("pull_request"), ValueError, adapter.PULL_REQUEST_VARIABLE),
        (
            _environment("pull_request", **{adapter.PULL_REQUEST_VARIABLE: "7"}),
            ValueError,
            adapter.EVENT_BASE_VARIABLE,
        ),
        (
            _environment("schedule", **{adapter.PULL_REQUEST_VARIABLE: "7"}),
            ValueError,
            "names no pull request",
        ),
        (
            _environment("workflow_dispatch", **{adapter.EVENT_BASE_VARIABLE: "0" * 40}),
            ValueError,
            "names no pull request",
        ),
        (_environment("schedule", **{adapter.REF_VARIABLE: ""}), ValueError, adapter.REF_VARIABLE),
        (
            _environment("schedule", **{adapter.WORKFLOW_SHA_VARIABLE: "short"}),
            ValueError,
            "workflowCommit",
        ),
        (
            _environment("schedule", **{adapter.LAYOUT_VARIABLE: "parallel"}),
            ValueError,
            "layout",
        ),
        (_environment(""), ValueError, adapter.EVENT_VARIABLE),
        (
            _environment(
                "workflow_dispatch",
                **{adapter.REQUEST_ID_VARIABLE: f'trace\nhead={"a" * 40}\nshards=["all"]'},
            ),
            ValueError,
            f"{adapter.REQUEST_ID_VARIABLE} 'trace\\nhead=",
        ),
        (
            _environment("workflow_dispatch", **{adapter.REQUEST_ID_VARIABLE: "trace\r"}),
            ValueError,
            "is not a single line",
        ),
        (
            _environment(
                "pull_request",
                **{adapter.PULL_REQUEST_VARIABLE: "7", adapter.EVENT_BASE_VARIABLE: unfetchable},
            ),
            subprocess.CalledProcessError,
            "",
        ),
    ]
    for environment, expected, message in cases:
        with pytest.raises(expected) as error:
            adapter.pin_request(environment, repository)
        assert message in str(error.value)


def test_the_plan_command_prints_the_outputs_and_fails_loudly(
    tmp_path: Path,
    head_commit: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name, value in _environment("schedule", **{adapter.REF_VARIABLE: "main"}).items():
        monkeypatch.setenv(name, value)
    out = tmp_path / "request"
    assert adapter.main(["plan", "--out", str(out)]) == 0
    printed = capsys.readouterr()
    assert printed.err == ""
    assert f"head={head_commit}\n" in printed.out
    assert f"shards={json.dumps(plan_ids('sharded'))}\n" in printed.out
    assert Request.load(out / REQUEST_FILE).head_commit == head_commit
    monkeypatch.setenv(adapter.PULL_REQUEST_VARIABLE, "7")
    assert adapter.main(["plan", "--out", str(tmp_path / "again")]) == 1
    printed = capsys.readouterr()
    assert printed.out == ""
    assert "the request cannot be pinned" in printed.err
    assert not (tmp_path / "again").exists()
    with pytest.raises(SystemExit) as usage:
        adapter.main(["plan"])
    assert usage.value.code == 2


# --------------------------------------------------------------------------- #
# History: the previous nightly, obtained through gh or stated unavailable    #
# --------------------------------------------------------------------------- #
def _run(identifier: int, created: str, head: str, **fields: object) -> dict[str, object]:
    return {
        "id": identifier,
        "run_attempt": 1,
        "head_sha": head,
        "created_at": created,
        "event": "schedule",
        "conclusion": "success",
        **fields,
    }


def test_the_previous_nightly_is_the_newest_successful_scheduled_run_but_this_one() -> None:
    head = "a" * 40
    runs: list[object] = [
        _run(5, "2026-09-18T06:00:00Z", head),
        _run(4, "2026-09-17T06:00:00Z", head),
        _run(6, "2026-09-17T06:00:00Z", head, run_attempt=3),
        _run(7, "2026-09-19T06:00:00Z", head, conclusion="failure"),
        _run(8, "2026-09-19T06:00:00Z", head, event="workflow_dispatch"),
        _run(9, "2026-09-19T06:00:00Z", head, run_attempt="1"),
        {"id": 10},
        "not a run",
    ]
    assert adapter.previous_nightly(runs, "100") == adapter.NightlyRun(
        "5", 1, head, "2026-09-18T06:00:00Z"
    )
    assert adapter.previous_nightly(runs, "5") == adapter.NightlyRun(
        "6", 3, head, "2026-09-17T06:00:00Z"
    )
    assert adapter.previous_nightly(runs[3:], "100") is None
    assert adapter.previous_nightly([], "100") is None


def _portfolio(text: str) -> Callable[[Path], None]:
    def stage(directory: Path) -> None:
        (directory / "portfolio.json").write_text(text, encoding="utf-8")

    return stage


class _Gh:
    """A fake ``gh``: it lists runs and artifacts as told and, on download,
    materializes what the test stages into the directory asked for."""

    def __init__(
        self,
        runs: object = None,
        artifacts: object = None,
        stage: Callable[[Path], None] | None = None,
        *,
        answers: dict[str, tuple[int, str, str]] | None = None,
    ) -> None:
        self.runs = runs
        self.artifacts = artifacts
        self.stage = stage
        self.answers = answers or {}
        self.calls: list[list[str]] = []

    def __call__(self, arguments: Sequence[str]) -> tuple[int, str, str]:
        self.calls.append(list(arguments))
        if arguments[0] in self.answers:
            return self.answers[arguments[0]]
        if arguments[0] == "api" and "/workflows/" in arguments[1]:
            return (0, json.dumps(self.runs), "")
        if arguments[0] == "api":
            return (0, json.dumps(self.artifacts), "")
        assert arguments[:2] == ["run", "download"]
        directory = Path(arguments[arguments.index("--dir") + 1])
        assert directory.is_absolute()
        directory.mkdir(parents=True)
        if self.stage is not None:
            self.stage(directory)
        return (0, "", "")


def _listing(*runs: dict[str, object]) -> dict[str, object]:
    return {"workflow_runs": list(runs)}


def _artifacts(*names: str, expired: bool = False) -> dict[str, object]:
    return {"artifacts": [{"name": name, "expired": expired, "id": 1} for name in names]}


def _previous_nightly(
    root: Path, head: str, sliced: dict[str, Document], request_id: str
) -> tuple[Path, Request]:
    """A complete nightly at ``head``, assembled and written under ``root``."""
    request = Request.from_document(
        {
            **cost_report.local_request("sharded").document(),
            "headCommit": head,
            "requestId": request_id,
            "event": "schedule",
            "runId": request_id,
            "runAttempt": 1,
        }
    )
    inputs = root / "inputs"
    for shard in SHARDS:
        write_capture(
            inputs,
            f"cost-report-shard-{shard.id}-attempt-1",
            shard,
            HEAD,
            request,
            sliced[shard.id],
            pair=f"{request_id}-{shard.id}",
        )
    assembled = root / "assembled"
    write_assembly(assemble(discover(inputs), SHARDS, request), inputs, discover(inputs), assembled)
    return assembled, request


def test_the_previous_nightly_is_obtained_verified_and_placed_for_assembly(
    tmp_path: Path, head_commit: str, sliced: dict[str, Document]
) -> None:
    assembled, previous_request = _previous_nightly(
        tmp_path / "night-1", head_commit, sliced, "night-1"
    )

    def stage(directory: Path) -> None:
        shutil.copytree(assembled, directory, dirs_exist_ok=True)

    gh = _Gh(
        _listing(
            _run(41, "2026-09-17T06:00:00Z", head_commit),
            _run(100, "2026-09-18T06:00:00Z", head_commit),
        ),
        _artifacts("cost-report-assembled-attempt-1", "cost-report-request-attempt-1"),
        stage,
    )
    out = tmp_path / "previous"
    selection = adapter.select_history(_environment("schedule"), out, gh)
    assert selection.available
    assert selection.run == adapter.NightlyRun("41", 1, head_commit, "2026-09-17T06:00:00Z")
    assert selection.artifact == "cost-report-assembled-attempt-1"
    assert gh.calls == [
        [
            "api",
            "repos/owner/parallax/actions/workflows/cost-report.yml/runs"
            "?event=schedule&branch=main&status=success&per_page=50",
        ],
        ["api", "repos/owner/parallax/actions/runs/41/artifacts?per_page=100"],
        [
            "run",
            "download",
            "41",
            "--repo",
            "owner/parallax",
            "--name",
            "cost-report-assembled-attempt-1",
            "--dir",
            gh.calls[2][-1],
        ],
    ]
    assert not Path(gh.calls[2][-1]).exists()
    recorded = json.loads((out / HISTORY_FILE).read_text(encoding="utf-8"))
    assert recorded == {
        "schemaVersion": 1,
        "workflow": "cost-report.yml",
        "run": {
            "id": "41",
            "attempt": 1,
            "headCommit": head_commit,
            "createdAt": "2026-09-17T06:00:00Z",
        },
        "artifact": "cost-report-assembled-attempt-1",
        "reason": None,
    }
    history = History.load(out)
    assert history.reason is None
    previous_head = history.head(SHARDS[0].id)
    assert previous_head is not None and previous_head.capture is not None
    assert previous_head.capture.request == previous_request
    assert selection.describe().startswith("previous nightly: run 41 attempt 1")


@pytest.mark.parametrize(
    ("gh", "reason"),
    [
        (
            _Gh(answers={"api": (1, "", "HTTP 403: Resource not accessible")}),
            "gh api repos/owner/parallax/actions/workflows/cost-report.yml/runs"
            "?event=schedule&branch=main&status=success&per_page=50 exited 1: "
            "HTTP 403: Resource not accessible",
        ),
        (_Gh(answers={"api": (127, "", "gh is not installed")}), "exited 127: gh is not installed"),
        (_Gh(answers={"api": (0, "<html>", "")}), "answered no JSON"),
        (_Gh({"total_count": 0}), "the answer holds no workflow_runs list"),
        (_Gh(_listing()), "no prior successful schedule run of cost-report.yml on main"),
        (
            _Gh(_listing(_run(100, "2026-09-18T06:00:00Z", "a" * 40))),
            "no prior successful schedule run of cost-report.yml on main",
        ),
        (
            _Gh(_listing(_run(41, "2026-09-17T06:00:00Z", "a" * 40)), {"artifacts": None}),
            "the answer holds no artifacts list",
        ),
        (
            _Gh(_listing(_run(41, "2026-09-17T06:00:00Z", "a" * 40)), _artifacts("other")),
            "run 41 has no artifact cost-report-assembled-attempt-1",
        ),
        (
            _Gh(
                _listing(_run(41, "2026-09-17T06:00:00Z", "a" * 40, run_attempt=2)),
                _artifacts("cost-report-assembled-attempt-2", expired=True),
            ),
            "artifact cost-report-assembled-attempt-2 of run 41 has expired",
        ),
        (
            _Gh(
                _listing(_run(41, "2026-09-17T06:00:00Z", "a" * 40)),
                _artifacts("cost-report-assembled-attempt-1"),
                answers={"run": (1, "", "no artifact matches")},
            ),
            "downloading cost-report-assembled-attempt-1 exited 1: no artifact matches",
        ),
        (
            _Gh(
                _listing(_run(41, "2026-09-17T06:00:00Z", "a" * 40)),
                _artifacts("cost-report-assembled-attempt-1"),
            ),
            "the artifact holds no readable portfolio.json",
        ),
        (
            _Gh(
                _listing(_run(41, "2026-09-17T06:00:00Z", "a" * 40)),
                _artifacts("cost-report-assembled-attempt-1"),
                _portfolio("[]"),
            ),
            "the artifact's portfolio.json is not an object",
        ),
        (
            _Gh(
                _listing(_run(41, "2026-09-17T06:00:00Z", "a" * 40)),
                _artifacts("cost-report-assembled-attempt-1"),
                _portfolio('{"schemaVersion": 1}'),
            ),
            "has schemaVersion 1, expected 2",
        ),
        (
            _Gh(
                _listing(_run(41, "2026-09-17T06:00:00Z", "a" * 40)),
                _artifacts("cost-report-assembled-attempt-1"),
                _portfolio('{"schemaVersion": 2, "request": {"schemaVersion": 1}}'),
            ),
            "the artifact's request does not decode",
        ),
    ],
)
def test_whatever_cannot_be_obtained_is_stated_and_read_by_assembly_as_unavailable_history(
    tmp_path: Path, gh: _Gh, reason: str
) -> None:
    out = tmp_path / "previous"
    selection = adapter.select_history(_environment("schedule"), out, gh)
    assert not selection.available
    assert selection.reason is not None and reason in selection.reason
    assert not (out / "portfolio.json").exists()
    recorded = json.loads((out / HISTORY_FILE).read_text(encoding="utf-8"))
    assert recorded["reason"] == selection.reason
    assert (recorded["run"] is None) == (selection.run is None)
    assert History.load(out).reason == selection.reason
    assert selection.describe() == f"previous nightly unavailable: {selection.reason}"


def test_an_artifact_answering_another_commit_or_an_unfetchable_one_is_unavailable(
    tmp_path: Path, head_commit: str, repository: Path, sliced: dict[str, Document]
) -> None:
    assembled, _ = _previous_nightly(tmp_path / "night-1", head_commit, sliced, "night-1")

    def stage(directory: Path) -> None:
        (directory / "portfolio.json").write_bytes((assembled / "portfolio.json").read_bytes())

    other = "b" * 40
    gh = _Gh(
        _listing(_run(41, "2026-09-17T06:00:00Z", other)),
        _artifacts("cost-report-assembled-attempt-1"),
        stage,
    )
    mismatch = adapter.select_history(_environment("schedule"), tmp_path / "mismatch", gh)
    assert mismatch.reason == (
        f"the artifact answers a request for {head_commit}, the run measured {other}"
    )
    gh = _Gh(
        _listing(_run(41, "2026-09-17T06:00:00Z", head_commit)),
        _artifacts("cost-report-assembled-attempt-1"),
        stage,
    )
    unfetchable = adapter.select_history(
        _environment("schedule"), tmp_path / "unfetchable", gh, repository
    )
    assert unfetchable.reason is not None
    assert unfetchable.reason.startswith(
        f"the producing commit {head_commit} could not be fetched: "
    )
    assert not (tmp_path / "unfetchable" / "portfolio.json").exists()
    assert History.load(tmp_path / "unfetchable").reason == unfetchable.reason


def test_a_history_marker_that_states_no_reason_leaves_the_generic_one(tmp_path: Path) -> None:
    out = tmp_path / "previous"
    out.mkdir()
    generic = f"no previous assembly at {out / 'portfolio.json'}"
    for text in ("{", "[]", '{"schemaVersion": 2, "reason": "old"}', '{"schemaVersion": 1}'):
        (out / HISTORY_FILE).write_text(text, encoding="utf-8")
        assert History.load(out).reason == generic
    (out / HISTORY_FILE).write_text('{"schemaVersion": 1, "reason": "stated"}', encoding="utf-8")
    assert History.load(out).reason == "stated"


def test_the_history_command_runs_gh_and_reports_its_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in _environment("schedule").items():
        monkeypatch.setenv(name, value)
    gh = _Gh(_listing())
    monkeypatch.setattr(adapter, "run_gh", gh)
    out = tmp_path / "previous"
    assert adapter.main(["history", "--out", str(out)]) == 0
    assert capsys.readouterr().out == (
        "previous nightly unavailable: no prior successful schedule run of "
        "cost-report.yml on main\n"
    )
    assert (out / HISTORY_FILE).exists()


def test_run_gh_invokes_gh_and_reports_a_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    class _Completed:
        returncode = 3
        stdout = "{}"
        stderr = "warn"

    def run(command: list[str], **options: Any) -> _Completed:
        calls.append({"command": command, **options})
        return _Completed()

    monkeypatch.setattr(adapter.subprocess, "run", run)
    assert adapter.run_gh(["api", "repos"]) == (3, "{}", "warn")
    assert calls == [
        {"command": ["gh", "api", "repos"], "capture_output": True, "text": True, "check": False}
    ]

    def missing(command: list[str], **options: Any) -> _Completed:
        raise OSError("gh is not installed")

    monkeypatch.setattr(adapter.subprocess, "run", missing)
    assert adapter.run_gh(["api", "repos"]) == (127, "", "gh is not installed")


# --------------------------------------------------------------------------- #
# The workflow's data flow, end to end, through the tool                       #
# --------------------------------------------------------------------------- #
def test_a_nightly_with_no_artifacts_and_no_history_assembles_every_shard_as_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_dir = tmp_path / "request"
    planned = adapter.plan(_environment("schedule", **{adapter.REF_VARIABLE: "main"}), request_dir)
    previous = tmp_path / "previous"
    selection = adapter.select_history(_environment("schedule"), previous, _Gh(_listing()))
    assembled = tmp_path / "assembled"
    assert (
        cost_report.main(
            [
                "--assemble",
                str(tmp_path / "inputs"),
                "--request",
                str(request_dir / REQUEST_FILE),
                "--against",
                str(previous),
                "--out",
                str(assembled),
            ]
        )
        == 0
    )
    capsys.readouterr()
    document = json.loads((assembled / "portfolio.json").read_text(encoding="utf-8"))
    assert document["request"] == planned.request.document()
    assert [entry["id"] for entry in document["shards"]] == planned.shards
    for entry in document["shards"]:
        assert entry["head"] is None and entry["base"] is None
        assert entry["pairing"] == "unavailable"
        assert [(reason["code"], reason["side"]) for reason in entry["reasons"]] == [
            ("head-missing", "head"),
            ("history-unavailable", "base"),
        ]
        assert entry["reasons"][1]["message"] == selection.reason
    assert document["failures"] == []
    summary = (assembled / "summary.md").read_text(encoding="utf-8")
    assert f"Previous nightly: unavailable ({selection.reason})." in summary
    assert "Critical path: unavailable" in summary


def test_a_nightly_pairs_cross_runner_with_the_predecessor_the_adapter_obtained(
    tmp_path: Path,
    head_commit: str,
    sliced: dict[str, Document],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assembled_before, _ = _previous_nightly(tmp_path / "night-1", head_commit, sliced, "night-1")

    def stage(directory: Path) -> None:
        shutil.copytree(assembled_before, directory, dirs_exist_ok=True)

    gh = _Gh(
        _listing(_run(41, "2026-09-17T06:00:00Z", head_commit)),
        _artifacts("cost-report-assembled-attempt-1"),
        stage,
    )
    previous = tmp_path / "previous"
    assert adapter.select_history(_environment("schedule"), previous, gh).available
    request_dir = tmp_path / "request"
    planned = adapter.plan(_environment("schedule", **{adapter.REF_VARIABLE: "main"}), request_dir)
    inputs = tmp_path / "inputs"
    for shard in SHARDS:
        write_capture(
            inputs,
            adapter.SHARD_ARTIFACT.format(shard=shard.id, attempt=2),
            shard,
            HEAD,
            planned.request,
            sliced[shard.id],
            pair=f"night-2-{shard.id}",
        )
    assembled = tmp_path / "assembled"
    assert (
        cost_report.main(
            [
                "--assemble",
                str(inputs),
                "--request",
                str(request_dir / REQUEST_FILE),
                "--against",
                str(previous),
                "--out",
                str(assembled),
            ]
        )
        == 0
    )
    capsys.readouterr()
    document = json.loads((assembled / "portfolio.json").read_text(encoding="utf-8"))
    assert document["failures"] == []
    for entry in document["shards"]:
        assert entry["pairing"] == "cross-runner"
        assert entry["reasons"] == []
        assert entry["head"]["capture"]["request"]["requestId"] == planned.request.request_id
        assert entry["base"]["capture"]["request"]["requestId"] == "night-1"
        assert entry["sources"] == [f"cost-report-shard-{entry['id']}-attempt-2/head/{entry['id']}"]
    assert sorted(path.name for path in (assembled / "raw").iterdir()) == sorted(
        adapter.SHARD_ARTIFACT.format(shard=shard.id, attempt=2) for shard in SHARDS
    )
