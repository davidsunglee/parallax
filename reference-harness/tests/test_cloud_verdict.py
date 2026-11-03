"""The relevance-gated verdict over scripted run records: every way the class's
cells can fail to prove themselves must fail the verdict, and only two states
pass it."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from reference_harness import ci_workflow
from reference_harness.cloud_verdict import (
    COMPLETION_DEADLINE,
    POLL_INTERVAL,
    QUEUE_DEADLINE,
    ApiFailure,
    Attempt,
    CellDeclarationError,
    Verdict,
    _GitHubJobs,  # pyright: ignore[reportPrivateUsage]
    attempt_jobs,
    expected_cells,
    main,
    supervise,
)

_ATTEMPT = Attempt(run_id=41, attempt=2)
_CELL = "python-check-cloud (aws)"
_REPO_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _job(
    name: str = _CELL,
    status: str = "completed",
    conclusion: str | None = "success",
    *,
    run_id: int = 41,
    attempt: int = 2,
) -> dict[str, Any]:
    return {
        "name": name,
        "run_id": run_id,
        "run_attempt": attempt,
        "status": status,
        "conclusion": conclusion,
        # Neither proves anything about execution on its own.
        "started_at": "2026-11-02T00:00:00Z",
        "runner_name": "codebuild",
    }


@dataclass
class _Clock:
    now: float = 1_000.0
    slept: list[float] = field(default_factory=list[float])

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@dataclass
class _Record:
    """A jobs record answering from a script of reads; each read is the pages the
    record holds then, or a failure raised instead."""

    reads: list[Sequence[Mapping[str, Any]] | ApiFailure]
    asked: list[int] = field(default_factory=list[int])
    _current: Sequence[Mapping[str, Any]] | ApiFailure | None = None

    def page(self, number: int) -> Any:
        self.asked.append(number)
        if number == 1:
            self._current = self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]
        current = self._current
        if isinstance(current, ApiFailure):
            raise current
        assert current is not None
        return current[number - 1]


def _pages(*jobs: dict[str, Any], size: int = 100) -> list[dict[str, Any]]:
    chunks = [list(jobs[start : start + size]) for start in range(0, len(jobs), size)] or [[]]
    return [{"total_count": len(jobs), "jobs": chunk} for chunk in chunks]


def _judge(
    record: _Record,
    clock: _Clock | None = None,
    *,
    relevance: str = "success",
    relevant: str = "true",
    cells: Callable[[], Sequence[str]] = lambda: [_CELL],
) -> Verdict:
    paced = clock or _Clock()
    return supervise(relevance, relevant, cells, record, _ATTEMPT, clock=paced, sleep=paced.sleep)


# --------------------------------------------------------------------------
# The relevance job settles the verdict alone in exactly one passing case
# --------------------------------------------------------------------------
def test_a_change_found_not_relevant_passes_without_reading_the_record() -> None:
    record = _Record([])
    verdict = _judge(record, relevant="false")
    assert verdict.passed
    assert record.asked == []


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", ""])
def test_a_relevance_job_that_did_not_succeed_fails_the_verdict(result: str) -> None:
    verdict = _judge(_Record([]), relevance=result, relevant="false")
    assert not verdict.passed
    assert "did not succeed" in verdict.reason


@pytest.mark.parametrize("answer", ["", "yes", "TRUE"])
def test_a_relevance_answer_that_is_neither_true_nor_false_fails_the_verdict(answer: str) -> None:
    verdict = _judge(_Record([]), relevant=answer)
    assert not verdict.passed
    assert "not true/false" in verdict.reason


def test_an_undeclarable_cell_set_fails_the_verdict() -> None:
    def refused() -> Sequence[str]:
        raise CellDeclarationError("the workflow declares no job `x`")

    verdict = _judge(_Record([]), cells=refused)
    assert not verdict.passed
    assert "no job `x`" in verdict.reason


# --------------------------------------------------------------------------
# A relevant change passes only when every cell succeeded in this attempt
# --------------------------------------------------------------------------
def test_every_cell_completed_successfully_passes() -> None:
    verdict = _judge(_Record([_pages(_job(), _job("cloud-verdict", "in_progress", None))]))
    assert verdict.passed
    assert "attempt 2" in verdict.reason


def test_a_cell_is_waited_for_through_queueing_and_execution() -> None:
    clock = _Clock()
    record = _Record(
        [
            _pages(),
            _pages(_job(status="queued", conclusion=None)),
            _pages(_job(status="in_progress", conclusion=None)),
            _pages(_job()),
        ]
    )
    assert _judge(record, clock).passed
    assert clock.slept == [POLL_INTERVAL] * 3


@pytest.mark.parametrize(
    "conclusion", ["failure", "cancelled", "skipped", "timed_out", "neutral", "stale", None]
)
def test_a_cell_that_completed_without_success_fails_at_once(conclusion: str | None) -> None:
    clock = _Clock()
    verdict = _judge(_Record([_pages(_job(conclusion=conclusion))]), clock)
    assert not verdict.passed
    assert _CELL in verdict.reason
    assert clock.slept == []


def test_an_unknown_status_fails() -> None:
    verdict = _judge(_Record([_pages(_job(status="paused", conclusion=None))]))
    assert not verdict.passed
    assert "unknown status `paused`" in verdict.reason


def test_a_cell_recorded_twice_in_one_attempt_fails() -> None:
    verdict = _judge(_Record([_pages(_job(), _job())]))
    assert not verdict.passed
    assert "2 times" in verdict.reason


def test_a_cell_recorded_under_another_run_fails() -> None:
    verdict = _judge(_Record([_pages(_job(run_id=40))]))
    assert not verdict.passed
    assert "another run" in verdict.reason


def test_every_expected_cell_is_owed() -> None:
    clock = _Clock()
    record = _Record([_pages(_job())])
    verdict = _judge(record, clock, cells=lambda: [_CELL, "python-check-cloud (gcp)"])
    assert not verdict.passed
    assert "python-check-cloud (gcp)" in verdict.reason


# --------------------------------------------------------------------------
# Deadlines: a cell never discovered or never started, and one never finishing
# --------------------------------------------------------------------------
def test_a_cell_never_discovered_fails_at_the_queue_deadline_with_a_rerun_instruction() -> None:
    clock = _Clock()
    verdict = _judge(_Record([_pages()]), clock)
    assert not verdict.passed
    assert "re-run all jobs" in verdict.reason
    assert clock.now - 1_000.0 >= QUEUE_DEADLINE
    assert clock.now - 1_000.0 < QUEUE_DEADLINE + POLL_INTERVAL + 1


def test_a_cell_waiting_for_other_runs_can_start_after_fifty_minutes() -> None:
    clock = _Clock()
    waiting = [_pages(_job(status="pending", conclusion=None))] * int(50 * 60 / POLL_INTERVAL)
    record = _Record(
        [
            *waiting,
            _pages(_job(status="queued", conclusion=None)),
            _pages(_job(status="in_progress", conclusion=None)),
            _pages(_job()),
        ]
    )
    assert _judge(record, clock).passed
    assert clock.now - 1_000.0 >= 50 * 60


def test_a_cell_never_started_fails_at_the_queue_deadline() -> None:
    clock = _Clock()
    verdict = _judge(_Record([_pages(_job(status="queued", conclusion=None))]), clock)
    assert not verdict.passed
    assert "did not start" in verdict.reason
    assert clock.now - 1_000.0 < COMPLETION_DEADLINE


def test_a_cell_that_started_may_run_past_the_queue_deadline_but_not_the_completion_deadline() -> (
    None
):
    clock = _Clock()
    verdict = _judge(_Record([_pages(_job(status="in_progress", conclusion=None))]), clock)
    assert not verdict.passed
    assert "did not finish" in verdict.reason
    assert clock.now - 1_000.0 >= COMPLETION_DEADLINE


def test_an_earlier_attempts_success_is_not_borrowed() -> None:
    # A partial rerun leaves the cell's earlier record in place; it proves
    # nothing about this attempt, so the cell is absent until it runs again.
    verdict = _judge(_Record([_pages(_job(attempt=1))]))
    assert not verdict.passed
    assert "re-run all jobs" in verdict.reason
    assert "an earlier attempt ran" in verdict.reason


def test_an_earlier_attempts_record_beside_this_attempts_success_passes() -> None:
    assert _judge(_Record([_pages(_job(attempt=1, conclusion="failure"), _job())])).passed


# --------------------------------------------------------------------------
# Reading the record: pagination, transient and final failures
# --------------------------------------------------------------------------
def test_every_page_of_the_record_is_read() -> None:
    others = [_job(f"job-{index}", "completed", "success") for index in range(150)]
    record = _Record([_pages(*others, _job(), size=100)])
    assert _judge(record).passed
    assert record.asked == [1, 2]


def test_a_record_that_changes_while_it_is_read_is_read_again() -> None:
    clock = _Clock()
    shifting: list[dict[str, Any]] = [
        {"total_count": 101, "jobs": [_job()]},
        {"total_count": 101, "jobs": []},
    ]
    record = _Record([shifting, _pages(_job())])
    assert _judge(record, clock).passed
    assert clock.slept == [POLL_INTERVAL]


def test_a_transient_failure_is_retried_within_the_deadline() -> None:
    clock = _Clock()
    record = _Record([ApiFailure("HTTP 502", transient=True), _pages(_job())])
    assert _judge(record, clock).passed


def test_a_transient_failure_that_outlasts_the_queue_deadline_fails() -> None:
    clock = _Clock()
    verdict = _judge(_Record([ApiFailure("HTTP 503", transient=True)]), clock)
    assert not verdict.passed
    assert "HTTP 503" in verdict.reason
    assert clock.now - 1_000.0 >= QUEUE_DEADLINE
    assert clock.now - 1_000.0 < COMPLETION_DEADLINE


def test_once_every_cell_started_a_transient_failure_is_retried_until_completion() -> None:
    clock = _Clock()
    record = _Record(
        [
            _pages(_job(status="in_progress", conclusion=None)),
            ApiFailure("HTTP 500", transient=True),
        ]
    )
    verdict = _judge(record, clock)
    assert not verdict.passed
    assert clock.now - 1_000.0 >= COMPLETION_DEADLINE


def test_a_final_failure_fails_at_once() -> None:
    clock = _Clock()
    verdict = _judge(_Record([ApiFailure("HTTP 404", transient=False)]), clock)
    assert not verdict.passed
    assert clock.slept == []


@pytest.mark.parametrize(
    "page",
    [
        [],
        {"jobs": []},
        {"total_count": "1", "jobs": []},
        {"total_count": 1, "jobs": "none"},
        {"total_count": 1, "jobs": ["text"]},
        {"total_count": 1, "jobs": [{"name": _CELL}]},
        {"total_count": 1, "jobs": [{**_job(), "run_attempt": "2"}]},
        {"total_count": 1, "jobs": [{**_job(), "conclusion": 1}]},
    ],
)
def test_a_malformed_record_is_a_final_failure(page: Any) -> None:
    with pytest.raises(ApiFailure) as failed:
        attempt_jobs(_Record([[page]]))
    assert not failed.value.transient


# --------------------------------------------------------------------------
# The cells, named from the one provider matrix
# --------------------------------------------------------------------------
def _workflow(job: dict[str, Any]) -> ci_workflow.Workflow:
    return ci_workflow.Workflow(
        frozenset({"push"}),
        (
            ci_workflow.Job(
                identifier="python-check-cloud",
                invoked=(),
                steps=(),
                name=job.get("name"),
                matrix=job.get("matrix"),
            ),
        ),
    )


def test_the_real_workflow_owes_one_aws_cell() -> None:
    workflow = ci_workflow.read(_REPO_WORKFLOW)
    assert workflow is not None
    assert expected_cells(workflow, "python-check-cloud") == ("python-check-cloud (aws)",)


def test_each_matrix_entry_is_one_cell_named_by_its_values() -> None:
    workflow = _workflow(
        {
            "name": "cloud (${{ matrix.provider }} on ${{matrix.runner}})",
            "matrix": {
                "include": [{"provider": "aws", "runner": "a"}, {"provider": "gcp", "runner": "b"}]
            },
        }
    )
    assert expected_cells(workflow, "python-check-cloud") == (
        "cloud (aws on a)",
        "cloud (gcp on b)",
    )


@pytest.mark.parametrize(
    ("job", "refusal"),
    [
        ({"matrix": {"include": [{"provider": "aws"}]}}, "explicit name"),
        ({"name": "x ${{ matrix.provider }}"}, "explicit name"),
        ({"name": "x ${{ matrix.provider }}", "matrix": {"provider": ["aws"]}}, "`include` list"),
        ({"name": "x ${{ matrix.provider }}", "matrix": {"include": []}}, "`include` list"),
        ({"name": "x", "matrix": {"include": [{"provider": "aws"}]}}, "render `matrix.provider`"),
        (
            {"name": "x ${{ matrix.provider }}", "matrix": {"include": [{"runner": "a"}]}},
            "names its",
        ),
        ({"name": "x ${{ matrix.provider }}", "matrix": {"include": ["aws"]}}, "names its"),
        (
            {
                "name": "x ${{ matrix.provider }} ${{ matrix.size }}",
                "matrix": {"include": [{"provider": "aws"}]},
            },
            "which an entry lacks",
        ),
        (
            {
                "name": "x ${{ matrix.provider }} ${{ github.sha }}",
                "matrix": {"include": [{"provider": "aws"}]},
            },
            "other than a matrix value",
        ),
        (
            {
                "name": "x ${{ matrix.provider }}",
                "matrix": {"include": [{"provider": "aws"}, {"provider": "aws"}]},
            },
            "two cells alike",
        ),
    ],
)
def test_a_cell_set_the_verdict_cannot_name_is_refused(job: dict[str, Any], refusal: str) -> None:
    with pytest.raises(CellDeclarationError, match=refusal):
        expected_cells(_workflow(job), "python-check-cloud")


def test_an_undeclared_class_job_is_refused() -> None:
    with pytest.raises(CellDeclarationError, match="no job `missing`"):
        expected_cells(_workflow({}), "missing")


# --------------------------------------------------------------------------
# The command and its REST reader
# --------------------------------------------------------------------------
_ENVIRONMENT = {
    "GITHUB_RUN_ID": "41",
    "GITHUB_RUN_ATTEMPT": "2",
    "RELEVANCE_RESULT": "success",
    "RELEVANT": "true",
}


def test_the_command_passes_when_the_real_workflows_cell_succeeded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        ["--workflow", str(_REPO_WORKFLOW), "--job", "python-check-cloud"],
        _ENVIRONMENT,
        lambda attempt: _Record([_pages(_job())]) if attempt == _ATTEMPT else _Record([]),
    )
    assert code == 0
    assert "cloud verdict passed" in capsys.readouterr().out


def test_the_command_fails_on_a_missing_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["--workflow", str(tmp_path / "ci.yml"), "--job", "python-check-cloud"],
        _ENVIRONMENT,
        lambda _attempt: _Record([]),
    )
    assert code == 1
    assert "does not exist" in capsys.readouterr().out


def test_the_command_needs_a_run_to_judge() -> None:
    assert main(["--workflow", "ci.yml", "--job", "x"], {"GITHUB_RUN_ID": "41"}) == 2


def test_the_command_needs_its_arguments() -> None:
    assert main([], _ENVIRONMENT) == 2


def _respond(monkeypatch: pytest.MonkeyPatch, outcome: bytes | BaseException) -> list[str]:
    requested: list[str] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> Any:
        requested.append(request.full_url)
        assert request.get_header("Authorization") == "Bearer token"
        assert timeout > 0
        if isinstance(outcome, BaseException):
            raise outcome
        return io.BytesIO(outcome)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return requested


def _refusal(code: int, **headers: str) -> urllib.error.HTTPError:
    message = Message()
    for key, value in headers.items():
        message[key] = value
    return urllib.error.HTTPError("https://api.github.test", code, "refused", message, None)


def test_the_rest_reader_asks_for_this_attempts_jobs_page_by_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = _respond(monkeypatch, json.dumps({"total_count": 0, "jobs": []}).encode())
    jobs = _GitHubJobs("https://api.github.test", "owner/repo", _ATTEMPT, "token")
    assert jobs.page(3) == {"total_count": 0, "jobs": []}
    assert requested == [
        "https://api.github.test/repos/owner/repo/actions/runs/41/attempts/2/jobs?per_page=100&page=3"
    ]


@pytest.mark.parametrize(
    ("outcome", "transient"),
    [
        (_refusal(502), True),
        (_refusal(429), True),
        (_refusal(403, **{"retry-after": "60"}), True),
        (_refusal(403), False),
        (_refusal(404), False),
        (urllib.error.URLError("unreachable"), True),
        (TimeoutError("slow"), True),
        (b"not json", False),
    ],
)
def test_the_rest_reader_tells_transient_failures_from_final_ones(
    monkeypatch: pytest.MonkeyPatch, outcome: bytes | BaseException, transient: bool
) -> None:
    _respond(monkeypatch, outcome)
    with pytest.raises(ApiFailure) as failed:
        _GitHubJobs("https://api.github.test", "owner/repo", _ATTEMPT, "token").page(1)
    assert failed.value.transient is transient
