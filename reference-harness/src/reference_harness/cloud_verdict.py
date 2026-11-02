"""Decide a relevance-gated class's required verdict from the run's own record::

    uv run python -m reference_harness.cloud_verdict --workflow <ci.yml> --job <class job>

`core/spec/language-testing.md` §9 makes this the required status of a class CI
runs only for relevant changes. It runs on a hosted runner beside the class job
rather than after it, so a class job whose runner never arrives cannot hold the
verdict open: the relevance job's answer arrives through the environment, and the
class job's cells are read from the jobs record of this exact run attempt, under
a deadline for every cell to appear and start and a later one for every cell to
finish. Everything this cannot establish is a failure, never a pass.

Environment:

* ``RELEVANCE_RESULT`` — the relevance job's result (``success`` to proceed);
* ``RELEVANT`` — its output: ``true`` or ``false``;
* ``GITHUB_REPOSITORY``, ``GITHUB_RUN_ID``, ``GITHUB_RUN_ATTEMPT``,
  ``GITHUB_API_URL`` — the run being judged, as the runner provides them;
* ``GITHUB_TOKEN`` — a token granted ``actions: read``.

Exit codes: 0 — the verdict passes; 1 — it fails; 2 — usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from reference_harness import ci_workflow

__all__ = [
    "COMPLETION_DEADLINE",
    "POLL_INTERVAL",
    "QUEUE_DEADLINE",
    "ApiFailure",
    "Attempt",
    "CellDeclarationError",
    "JobsRecord",
    "ObservedJob",
    "Verdict",
    "attempt_jobs",
    "expected_cells",
    "main",
    "supervise",
]

QUEUE_DEADLINE = 40 * 60.0
"""Seconds from the verdict's start by which every expected cell has started.

It exceeds the provider runner's own queue timeout, so a cell that the provider
gave up on is reported here rather than waited on for as long as the workflow
would keep a job queued."""

COMPLETION_DEADLINE = 110 * 60.0
"""Seconds from the verdict's start by which every expected cell has finished:
the queue deadline plus the class job's own timeout, with margin."""

POLL_INTERVAL = 20.0
"""Seconds between reads of the jobs record."""

_PROVIDER_KEY = "provider"
_MATRIX_REFERENCE = re.compile(r"\$\{\{\s*matrix\.(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*\}\}")
_ANY_EXPRESSION = re.compile(r"\$\{\{.*?\}\}")
_NOT_STARTED = frozenset({"queued", "waiting", "requested", "pending"})
_RUNNING = frozenset({"in_progress"})
_COMPLETED = "completed"
_PAGE_SIZE = 100


class CellDeclarationError(ValueError):
    """The class job does not declare a set of cells this can name."""


class ApiFailure(Exception):
    """The jobs record could not be read. A transient failure may be retried
    within the deadline in force; any other is final."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


@dataclass(frozen=True)
class Attempt:
    run_id: int
    attempt: int


@dataclass(frozen=True)
class ObservedJob:
    """One job of the run as the record lists it."""

    name: str
    run_id: int
    run_attempt: int
    status: str
    conclusion: str | None


@dataclass(frozen=True)
class Verdict:
    passed: bool
    reason: str


class JobsRecord(Protocol):
    def page(self, number: int) -> Any:
        """One page of this run attempt's jobs, as the API returns it."""
        ...


def expected_cells(workflow: ci_workflow.Workflow, job: str) -> tuple[str, ...]:
    """The display name of every cell *job*'s provider matrix owes a run.

    The cells are the matrix's ``include`` entries, each naming its provider,
    and the job's name renders each one by substituting matrix values, so the
    names are read from the one matrix rather than restated.
    """
    declared = next((entry for entry in workflow.jobs if entry.identifier == job), None)
    if declared is None:
        raise CellDeclarationError(f"the workflow declares no job `{job}`")
    if declared.name is None or declared.matrix is None:
        raise CellDeclarationError(f"`{job}` needs an explicit name and a provider matrix")
    include: Any = declared.matrix.get("include")
    if set(declared.matrix) != {"include"} or not isinstance(include, Sequence) or not include:
        raise CellDeclarationError(f"`{job}`'s matrix must be a non-empty `include` list alone")
    if _PROVIDER_KEY not in {match["key"] for match in _MATRIX_REFERENCE.finditer(declared.name)}:
        raise CellDeclarationError(f"`{job}`'s name must render `matrix.{_PROVIDER_KEY}`")
    cells = [_rendered(declared.name, entry, job) for entry in include]
    if len(set(cells)) != len(cells):
        raise CellDeclarationError(f"`{job}` names two cells alike")
    return tuple(cells)


def _rendered(template: str, entry: Any, job: str) -> str:
    if not isinstance(entry, Mapping) or _PROVIDER_KEY not in entry:
        raise CellDeclarationError(f"every `{job}` matrix entry names its `{_PROVIDER_KEY}`")
    values: Mapping[str, Any] = entry

    def substitute(match: re.Match[str]) -> str:
        key = match["key"]
        if key not in values:
            raise CellDeclarationError(f"`{job}`'s name reads `matrix.{key}`, which an entry lacks")
        return str(values[key])

    rendered = _MATRIX_REFERENCE.sub(substitute, template)
    if _ANY_EXPRESSION.search(rendered):
        raise CellDeclarationError(f"`{job}`'s name holds an expression other than a matrix value")
    return rendered


def _observed(entry: Any) -> ObservedJob:
    if not isinstance(entry, Mapping):
        raise ApiFailure("the jobs record lists a job that is not an object", transient=False)
    job: Mapping[str, Any] = entry
    name, run_id, run_attempt = job.get("name"), job.get("run_id"), job.get("run_attempt")
    status, conclusion = job.get("status"), job.get("conclusion")
    if (
        not isinstance(name, str)
        or type(run_id) is not int
        or type(run_attempt) is not int
        or not isinstance(status, str)
        or not (conclusion is None or isinstance(conclusion, str))
    ):
        raise ApiFailure("the jobs record lists a job missing a field it needs", transient=False)
    return ObservedJob(name, run_id, run_attempt, status, conclusion)


def attempt_jobs(record: JobsRecord) -> list[ObservedJob]:
    """Every job the record lists for the attempt, across every page.

    A count that changes while the pages are read — a job created between two
    reads — is transient: the next read sees a consistent record.
    """
    observed: list[ObservedJob] = []
    number = 1
    while True:
        page: Any = record.page(number)
        total: Any = page.get("total_count") if isinstance(page, Mapping) else None
        listed: Any = page.get("jobs") if isinstance(page, Mapping) else None
        if type(total) is not int or not isinstance(listed, list):
            raise ApiFailure("the jobs record is not a page of jobs", transient=False)
        entries: list[Any] = listed
        observed.extend(_observed(entry) for entry in entries)
        if len(observed) >= total or not entries:
            break
        number += 1
    if len(observed) != total:
        raise ApiFailure("the jobs record changed while it was read", transient=True)
    return observed


@dataclass(frozen=True)
class _Progress:
    """Cells not yet finished: those absent or unstarted, and those running."""

    unstarted: tuple[str, ...]
    running: tuple[str, ...]
    borrowed: tuple[str, ...]


type _CellState = Literal["unstarted", "borrowed", "running", "succeeded"]


def _cell_state(
    cell: str, observed: Sequence[ObservedJob], attempt: Attempt
) -> Verdict | _CellState:
    """Where *cell* stands in *attempt*, or the failing verdict it already settles."""
    matching = [job for job in observed if job.name == cell]
    if any(job.run_id != attempt.run_id for job in matching):
        return Verdict(False, f"the record lists `{cell}` under another run")
    current = [job for job in matching if job.run_attempt == attempt.attempt]
    if len(current) > 1:
        return Verdict(False, f"the record lists `{cell}` {len(current)} times in this attempt")
    if not current:
        return "borrowed" if matching else "unstarted"
    (job,) = current
    if job.status == _COMPLETED:
        if job.conclusion == "success":
            return "succeeded"
        return Verdict(False, f"`{cell}` concluded {job.conclusion or 'without a result'}")
    if job.status in _RUNNING:
        return "running"
    if job.status in _NOT_STARTED:
        return "unstarted"
    return Verdict(False, f"`{cell}` reports the unknown status `{job.status}`")


def _judged(
    expected: Sequence[str], observed: Sequence[ObservedJob], attempt: Attempt
) -> Verdict | _Progress:
    states: dict[str, _CellState] = {}
    for cell in expected:
        state = _cell_state(cell, observed, attempt)
        if isinstance(state, Verdict):
            return state
        states[cell] = state
    unstarted = tuple(cell for cell, state in states.items() if state in ("unstarted", "borrowed"))
    running = tuple(cell for cell, state in states.items() if state == "running")
    if not unstarted and not running:
        return Verdict(
            True, f"every cell succeeded in attempt {attempt.attempt}: {', '.join(expected)}"
        )
    borrowed = tuple(cell for cell, state in states.items() if state == "borrowed")
    return _Progress(unstarted, running, borrowed)


def _never_started(progress: _Progress, attempt: Attempt) -> Verdict:
    reason = (
        f"{', '.join(progress.unstarted)} did not start in attempt {attempt.attempt} within "
        f"{QUEUE_DEADLINE / 60:.0f} minutes; re-run all jobs, since a cell's success in an "
        f"earlier attempt is not this attempt's"
    )
    if progress.borrowed:
        reason += f" (an earlier attempt ran {', '.join(progress.borrowed)})"
    return Verdict(False, reason)


def _relevance_verdict(relevance: str, relevant: str) -> Verdict | None:
    """The verdict the relevance job settles alone, or ``None`` when the cells decide."""
    if relevance != "success":
        return Verdict(False, f"the relevance job did not succeed (result `{relevance or 'none'}`)")
    if relevant == "false":
        return Verdict(True, "the relevance job found this change not relevant")
    if relevant != "true":
        return Verdict(
            False, f"the relevance job answered `{relevant or 'nothing'}`, not true/false"
        )
    return None


def supervise(
    relevance: str,
    relevant: str,
    cells: Callable[[], Sequence[str]],
    record: JobsRecord,
    attempt: Attempt,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Verdict:
    """The required verdict for *attempt*.

    *cells* is consulted only once the relevance job has asked for the class, so
    a not-relevant change never depends on the class job's declaration.
    """
    settled = _relevance_verdict(relevance, relevant)
    if settled is not None:
        return settled
    try:
        expected = tuple(cells())
    except CellDeclarationError as refused:
        return Verdict(False, str(refused))
    start = clock()
    queue_deadline, completion_deadline = start + QUEUE_DEADLINE, start + COMPLETION_DEADLINE
    started_everything = False
    while True:
        now = clock()
        try:
            judged = _judged(expected, attempt_jobs(record), attempt)
        except ApiFailure as failure:
            deadline = completion_deadline if started_everything else queue_deadline
            if not failure.transient or now >= deadline:
                return Verdict(False, f"the jobs record could not be read: {failure}")
            sleep(POLL_INTERVAL)
            continue
        if isinstance(judged, Verdict):
            return judged
        started_everything = not judged.unstarted
        if judged.unstarted and now >= queue_deadline:
            return _never_started(judged, attempt)
        if now >= completion_deadline:
            return Verdict(
                False,
                f"{', '.join(judged.running)} did not finish within "
                f"{COMPLETION_DEADLINE / 60:.0f} minutes",
            )
        sleep(POLL_INTERVAL)


class _GitHubJobs:
    """The jobs record of one run attempt, read through the REST API."""

    def __init__(self, api: str, repository: str, attempt: Attempt, token: str) -> None:
        self._url = (
            f"{api}/repos/{repository}/actions/runs/{attempt.run_id}"
            f"/attempts/{attempt.attempt}/jobs?per_page={_PAGE_SIZE}"
        )
        self._token = token

    def page(self, number: int) -> Any:
        request = urllib.request.Request(
            f"{self._url}&page={number}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body: bytes = response.read()
        except urllib.error.HTTPError as refused:
            limited = refused.code == 403 and refused.headers.get("retry-after") is not None
            transient = refused.code >= 500 or refused.code == 429 or limited
            raise ApiFailure(f"HTTP {refused.code}", transient=transient) from refused
        except (urllib.error.URLError, OSError) as unreachable:
            raise ApiFailure(f"unreachable: {unreachable}", transient=True) from unreachable
        try:
            return json.loads(body)
        except ValueError as malformed:
            raise ApiFailure("the response is not JSON", transient=False) from malformed


def _attempt(environment: Mapping[str, str]) -> Attempt | None:
    try:
        return Attempt(int(environment["GITHUB_RUN_ID"]), int(environment["GITHUB_RUN_ATTEMPT"]))
    except (KeyError, ValueError):
        return None


def main(
    argv: list[str] | None = None,
    environment: Mapping[str, str] | None = None,
    record: Callable[[Attempt], JobsRecord] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="The required verdict of a relevance-gated class.")
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--job", required=True)
    try:
        arguments = parser.parse_args(argv)
    except SystemExit:
        return 2
    env = os.environ if environment is None else environment
    attempt = _attempt(env)
    if attempt is None:
        print("cloud verdict: GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT name no run", file=sys.stderr)
        return 2
    workflow_path: Path = arguments.workflow
    job: str = arguments.job

    def cells() -> Sequence[str]:
        workflow = ci_workflow.read(workflow_path)
        if workflow is None:
            raise CellDeclarationError(f"{workflow_path} does not exist")
        return expected_cells(workflow, job)

    jobs = (
        record(attempt)
        if record is not None
        else _GitHubJobs(
            env.get("GITHUB_API_URL", "https://api.github.com"),
            env.get("GITHUB_REPOSITORY", ""),
            attempt,
            env.get("GITHUB_TOKEN", ""),
        )
    )
    verdict = supervise(
        env.get("RELEVANCE_RESULT", ""), env.get("RELEVANT", ""), cells, jobs, attempt
    )
    print(f"cloud verdict {'passed' if verdict.passed else 'FAILED'}: {verdict.reason}")
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
