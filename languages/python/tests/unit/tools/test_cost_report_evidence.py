from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

import cost_report_evidence as evidence_tool
from cost_report import (
    DURATIONS_FILE,
    HEAD,
    SHARDS,
    MemberResult,
    Request,
    ShardResult,
    assemble,
    discover,
    git_head,
    local_request,
    write_assembly,
    write_shard,
)
from cost_report_evidence import (
    HEAD_ONLY,
    HISTORICAL_BASE_STEP,
    HISTORICAL_HEAD_STEP,
    HISTORICAL_JOB,
    HISTORICAL_UPLOAD_STEP,
    MEASURE_STEP,
    ORDINARY_CI_ROW,
    PAIRED,
    SHARD_UPLOAD_STEP,
    Coverage,
    Historical,
    Job,
    Run,
    Sharded,
    compare_coverage,
    coverage_of,
    evidence,
    historical,
    load_jobs,
    sharded,
)
from durations import Spans
from parallax.conformance.budget import BudgetContract
from tests._support.repo import REPO_ROOT
from tests.unit.tools._cost_report_support import (
    clean,
    identities,
    member_envelopes,
    write_capture,
)

type Document = dict[str, Any]

BEFORE_RUN = "35343050954"
BEFORE_JOB = "105593153404"
BEFORE_COMMIT = "d7c838dd0b2b39543473604caffc89851c4ae6fe"
AFTER_RUN = "424242"
REPOSITORY = "davidsunglee/parallax"
CLOCK = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def contract() -> BudgetContract:
    return BudgetContract.load()


@pytest.fixture(scope="module")
def head_commit() -> str:
    return git_head()


@pytest.fixture(scope="module")
def envelopes(contract: BudgetContract) -> dict[str, Document]:
    return {
        subject: clean(document, contract)
        for subject, document in member_envelopes(contract).items()
    }


@pytest.fixture(scope="module")
def before_portfolio(contract: BudgetContract, envelopes: dict[str, Document]) -> Document:
    """The same work as the after fixtures, captured at the frozen baseline's
    commit rather than this checkout's."""
    return {
        "schemaVersion": 1,
        "members": [clean(envelopes[shard.subject], contract, BEFORE_COMMIT) for shard in SHARDS],
        "failures": [],
    }


# --------------------------------------------------------------------------- #
# GitHub metadata fixtures                                                    #
# --------------------------------------------------------------------------- #
def _at(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    return (CLOCK + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def _run(
    run_id: str,
    event: str,
    head_sha: str,
    *,
    attempt: int = 1,
    created: float | None = 0.0,
    conclusion: str | None = "success",
) -> Document:
    return {
        "id": int(run_id),
        "event": event,
        "head_sha": head_sha,
        "run_attempt": attempt,
        "created_at": _at(created),
        "status": "completed",
        "conclusion": conclusion,
        "repository": {"full_name": REPOSITORY},
    }


def _step(
    name: str, started: float | None, completed: float | None, conclusion: str = "success"
) -> Document:
    return {
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "started_at": _at(started),
        "completed_at": _at(completed),
    }


def _job(
    job_id: str,
    name: str,
    started: float | None,
    completed: float | None,
    steps: Sequence[Document] = (),
    *,
    conclusion: str = "success",
    run_id: str | None = None,
    attempt: int | None = 1,
    created: float | None = None,
) -> Document:
    return {
        "id": int(job_id),
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "run_id": int(run_id) if run_id is not None else None,
        "run_attempt": attempt,
        "created_at": _at(created),
        "started_at": _at(started),
        "completed_at": _at(completed),
        "labels": ["ubuntu-latest"],
        "steps": list(steps),
    }


def _before_jobs(
    *,
    job_conclusion: str = "failure",
    head_conclusion: str = "success",
    base_conclusion: str = "skipped",
    upload_conclusion: str = "success",
    head_started: float | None = 17.0,
    head_completed: float | None = 10674.0,
    job_started: float | None = 4.0,
    job_completed: float | None = 10676.0,
) -> Document:
    """The frozen baseline's shape: a report job that failed its verification
    step while measuring and uploading the head successfully."""
    steps = [
        _step("Set up job", 4.0, 6.0),
        _step("Verify committed evidence against head lock", 12.0, 17.0, "failure"),
        _step(HISTORICAL_BASE_STEP, 17.0, 17.0, base_conclusion),
        _step(HISTORICAL_HEAD_STEP, head_started, head_completed, head_conclusion),
        _step(HISTORICAL_UPLOAD_STEP, 10674.0, 10675.0, upload_conclusion),
    ]
    return {
        "jobs": [
            _job("1", "check-gates", 3.0, 13.0, run_id=BEFORE_RUN),
            _job(
                BEFORE_JOB,
                HISTORICAL_JOB,
                job_started,
                job_completed,
                steps,
                conclusion=job_conclusion,
                run_id=BEFORE_RUN,
            ),
            _job("3", "commitlint", 1.0, 0.0, conclusion="skipped", run_id=BEFORE_RUN),
        ]
    }


def _after_jobs(
    shards: Sequence[str],
    *,
    measure_seconds: Sequence[float] | None = None,
    measure_conclusions: Sequence[str] | None = None,
    step_conclusions: Sequence[str] | None = None,
    assemble_completed: float | None = 2760.0,
    run_id: str = AFTER_RUN,
    attempt: int = 1,
) -> Document:
    """One plan job, one measure job per shard, one assemble job, and a
    skipped cleanup: what a dispatched sharded run's jobs look like."""
    seconds = measure_seconds or [600.0 * (index + 1) for index in range(len(shards))]
    conclusions = measure_conclusions or ["success"] * len(shards)
    steps = step_conclusions or ["success"] * len(shards)
    jobs = [_job("10", "plan", 10.0, 70.0, run_id=run_id, attempt=attempt)]
    for index, shard in enumerate(shards):
        started = 80.0
        measuring = started + 40.0
        jobs.append(
            _job(
                str(100 + index),
                f"measure ({shard})",
                started,
                started + seconds[index],
                [
                    _step("Set up job", started, started + 5.0),
                    _step(MEASURE_STEP, measuring, started + seconds[index] - 5.0, steps[index]),
                    _step(
                        SHARD_UPLOAD_STEP, started + seconds[index] - 5.0, started + seconds[index]
                    ),
                ],
                conclusion=conclusions[index],
                run_id=run_id,
                attempt=attempt,
                created=72.0,
            )
        )
    jobs.append(_job("200", "assemble", 2700.0, assemble_completed, run_id=run_id, attempt=attempt))
    jobs.append(
        _job("300", "cleanup", 2761.0, 2760.0, conclusion="skipped", run_id=run_id, attempt=attempt)
    )
    return {"jobs": jobs}


def _jobs(document: Document) -> tuple[Job, ...]:
    return tuple(evidence_tool._job(entry) for entry in document["jobs"])  # pyright: ignore[reportPrivateUsage] - decoding seam


def _dispatch_request(head: str, *, run_id: str = AFTER_RUN, attempt: int = 1) -> Request:
    return Request.from_document(
        {
            **local_request("sharded").document(),
            "requestId": "req-evidence",
            "event": "workflow_dispatch",
            "requestedRef": head,
            "runId": run_id,
            "runAttempt": attempt,
        }
    )


def _assembled(
    root: Path,
    request: Request,
    envelopes: dict[str, Document],
    *,
    skip: Sequence[str] = (),
    seconds: Sequence[float] | None = None,
) -> Path:
    inputs = root / "inputs"
    for index, shard in enumerate(SHARDS):
        if shard.id in skip:
            continue
        write_capture(
            inputs,
            f"cost-report-shard-{shard.id}-attempt-1",
            shard,
            HEAD,
            request,
            envelopes[shard.subject],
            pair=f"pair-{shard.id}",
            seconds=seconds[index] if seconds is not None else 500.0 * (index + 1),
        )
    captures = discover(inputs)
    out = root / "assembled"
    write_assembly(assemble(captures, SHARDS, request), inputs, captures, out)
    return out


def _before(portfolio: Document, jobs: Document | None = None) -> Historical:
    return historical(
        Run.from_document(_run(BEFORE_RUN, "push", BEFORE_COMMIT, created=0.0)),
        _jobs(jobs or _before_jobs()),
        portfolio,
    )


def _after(
    assembled: Path,
    request: Request,
    jobs: Document | None = None,
    *,
    event: str = "workflow_dispatch",
    head_sha: str | None = None,
) -> Sharded:
    return sharded(
        Run.from_document(_run(AFTER_RUN, event, head_sha or request.workflow_commit, created=0.0)),
        _jobs(jobs or _after_jobs([shard.id for shard in SHARDS])),
        assembled,
    )


# --------------------------------------------------------------------------- #
# The historical side                                                          #
# --------------------------------------------------------------------------- #
def test_the_frozen_baseline_is_a_successful_measurement_inside_a_failed_advisory_job(
    before_portfolio: Document,
) -> None:
    before = _before(before_portfolio)
    assert before.sufficient and before.problems == ()
    assert before.scope == HEAD_ONLY
    assert before.commit == BEFORE_COMMIT
    assert before.job is not None and before.job.id == BEFORE_JOB
    assert before.timing.elapsed.seconds == 10672.0
    assert before.timing.measurement_path.seconds == 10657.0
    assert before.timing.runner.seconds == 10672.0
    assert before.timing.initial_queue.seconds == 4.0
    assert before.timing.request_latency.seconds == 10676.0
    assert before.timing.setup.seconds == 13.0
    (note,) = before.notes
    assert "ended failure" in note and "separate verification" in note
    assert before.coverage.total == sum(
        len(member["readings"]) for member in before_portfolio["members"]
    )


@pytest.mark.parametrize("conclusion", ["cancelled", "failure", "timed_out"])
def test_a_failed_or_cancelled_historical_measurement_is_insufficient_but_its_cost_is_known(
    before_portfolio: Document, conclusion: str
) -> None:
    before = _before(
        before_portfolio,
        _before_jobs(job_conclusion=conclusion, head_conclusion=conclusion),
    )
    assert not before.sufficient
    assert any(f"ended {conclusion}" in problem for problem in before.problems)
    assert before.timing.elapsed.seconds == 10672.0
    assert before.timing.measurement_path.seconds == 10657.0
    assert before.notes == ()


def test_missing_timestamps_leave_a_quantity_unknown_rather_than_zero(
    before_portfolio: Document,
) -> None:
    before = _before(before_portfolio, _before_jobs(head_completed=None, job_completed=None))
    assert before.timing.elapsed.seconds is None and "absent" in before.timing.elapsed.note
    assert before.timing.measurement_path.seconds is None
    assert before.timing.runner.seconds is None
    assert before.timing.request_latency.seconds is None
    assert before.timing.initial_queue.seconds == 4.0
    assert any("carries no timestamps" in problem for problem in before.problems)
    run = Run.from_document(_run(BEFORE_RUN, "push", BEFORE_COMMIT, created=None))
    without_creation = historical(run, _jobs(_before_jobs()), before_portfolio)
    assert without_creation.timing.initial_queue.seconds is None
    assert without_creation.timing.request_latency.seconds is None
    assert without_creation.timing.elapsed.seconds == 10672.0


def test_the_historical_side_is_cross_checked_against_its_run_before_arithmetic(
    before_portfolio: Document, contract: BudgetContract
) -> None:
    other_commit = "b" * 40
    moved = historical(
        Run.from_document(_run(BEFORE_RUN, "push", other_commit)),
        _jobs(_before_jobs()),
        before_portfolio,
    )
    assert any("is not the portfolio's producing commit" in p for p in moved.problems)
    foreign = deepcopy(_before_jobs())
    foreign["jobs"][1]["run_id"] = 1
    foreign["jobs"][1]["run_attempt"] = 2
    stray = _before(before_portfolio, foreign)
    assert any("belongs to run 1" in p for p in stray.problems)
    assert any("is attempt 2" in p for p in stray.problems)
    twice = deepcopy(_before_jobs())
    twice["jobs"].append(deepcopy(twice["jobs"][1]))
    unidentified = _before(before_portfolio, twice)
    assert unidentified.job is None and unidentified.scope == "unknown"
    assert unidentified.timing.elapsed.seconds is None
    split = deepcopy(before_portfolio)
    split["members"][0] = clean(split["members"][0], contract, other_commit)
    assert any("2 producing commit(s)" in p for p in _before(split).problems)


def test_a_paired_historical_job_is_never_divided_by_a_head_only_after_run(
    tmp_path: Path,
    head_commit: str,
    envelopes: dict[str, Document],
    before_portfolio: Document,
) -> None:
    before = _before(before_portfolio, _before_jobs(base_conclusion="success"))
    assert before.scope == PAIRED and before.sufficient
    request = _dispatch_request(head_commit)
    after = _after(_assembled(tmp_path, request, envelopes), request)
    assert after.scope == HEAD_ONLY
    result = evidence(before, after)
    assert result.reduction.seconds is None
    assert result.reduction.note == "scopes differ (paired before, head-only after)"
    assert "never divided by a head-only" in result.render()


# --------------------------------------------------------------------------- #
# Coverage                                                                     #
# --------------------------------------------------------------------------- #
def test_legacy_readings_without_runtime_or_window_share_the_address_vocabulary() -> None:
    coverage = coverage_of(
        [
            {
                "subject": "lifecycle-overhead",
                "readings": [
                    {"workload": "w", "cell": "c", "unit": "us", "value": 1.0},
                    {"workload": "w", "cell": "c", "unit": "us", "value": 2.0},
                    {
                        "workload": "w",
                        "cell": "d",
                        "unit": "us",
                        "value": 3.0,
                        "runtime": "3.13",
                        "window": "win",
                        "samples": [1, 2, 3],
                    },
                ],
                "provenance": {
                    "commit": "c" * 40,
                    "workloadDigest": "w" * 64,
                    "sampling": {"timing": {"pairs": 3}},
                    "cpython": "3.14.7",
                },
            }
        ]
    )
    assert coverage.readings == {
        ("lifecycle-overhead", "", "", "w", "c", "us"): 2,
        ("lifecycle-overhead", "3.13", "win", "w", "d", "us"): 1,
    }
    assert coverage.samples == {
        ("lifecycle-overhead", "", "", "w", "c", "us"): (0, 0),
        ("lifecycle-overhead", "3.13", "win", "w", "d", "us"): (3,),
    }
    protocol = coverage.protocols["lifecycle-overhead"]
    assert protocol.sampling == {"timing.pairs": "3"}
    assert protocol.contract_digest == "unknown" and protocol.lock_digest == "unknown"
    assert coverage.subjects == ("lifecycle-overhead",)


def _perturbed(portfolio: Document, change: str) -> Document:
    altered = deepcopy(portfolio)
    member = altered["members"][0]
    readings = cast("list[Document]", member["readings"])
    if change == "missing":
        readings.pop()
    elif change == "extra":
        readings.append({**readings[0], "cell": "another.cell"})
    elif change == "recounted":
        readings.append(deepcopy(readings[0]))
    elif change == "resampled":
        readings[0]["samples"] = [*readings[0]["samples"], 1.0]
    return altered


@pytest.mark.parametrize("change", ["missing", "extra", "recounted", "resampled"])
def test_every_way_of_measuring_different_work_is_named_and_withholds_the_claim(
    before_portfolio: Document, change: str
) -> None:
    before = coverage_of(before_portfolio["members"])
    after = coverage_of(_perturbed(before_portfolio, change)["members"])
    verdict = compare_coverage(before, after)
    assert not verdict.equivalent and verdict.same_protocol
    counts = (
        len(verdict.missing),
        len(verdict.extra),
        len(verdict.recounted),
        len(verdict.resampled),
    )
    assert (
        counts
        == {
            "missing": (1, 0, 0, 0),
            "extra": (0, 1, 0, 0),
            "recounted": (0, 0, 1, 1),
            "resampled": (0, 0, 0, 1),
        }[change]
    )
    assert compare_coverage(before, before).equivalent


def test_a_workload_or_sampling_change_withholds_the_claim_while_digests_are_displayed(
    before_portfolio: Document,
) -> None:
    before = coverage_of(before_portfolio["members"])
    altered = deepcopy(before_portfolio)
    snapshot = altered["members"][0]
    snapshot["provenance"]["workloadDigest"] = "f" * 64
    write = altered["members"][3]
    write["provenance"]["sampling"]["retainedWarmups"] = 7
    lifecycle = altered["members"][1]
    lifecycle["provenance"]["lockDigest"] = "e" * 64
    lifecycle["provenance"]["budgetContractDigest"] = "d" * 64
    verdict = compare_coverage(before, coverage_of(altered["members"]))
    assert verdict.equivalent and not verdict.same_protocol
    assert verdict.protocol_differences == (
        "snapshot-delivery: workload digest "
        f"{before.protocols['snapshot-delivery'].workload_digest} before, {'f' * 64} after",
        "write-lowering: sampling retainedWarmups 1 before, 7 after",
    )
    assert len(verdict.displayed_differences) == 2
    assert all("lifecycle-overhead" in shown for shown in verdict.displayed_differences)
    absent = compare_coverage(before, Coverage({}, {}, {}))
    assert "snapshot-delivery: no provenance on the after side" in absent.protocol_differences


# --------------------------------------------------------------------------- #
# The sharded side                                                             #
# --------------------------------------------------------------------------- #
def test_a_complete_sharded_run_reports_its_cost_from_job_durations_and_head_spans(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _dispatch_request(head_commit)
    after = _after(_assembled(tmp_path, request, envelopes), request)
    assert after.sufficient and after.complete and after.problems == ()
    assert after.scope == HEAD_ONLY
    assert [shard.id for shard in after.shards] == [shard.id for shard in SHARDS]
    assert after.timing.elapsed.seconds == 2750.0
    assert after.timing.measurement_path.seconds == 2000.0
    assert f"shard `{SHARDS[-1].id}`" in after.timing.measurement_path.note
    assert after.longest_job.seconds == 2400.0
    assert after.timing.runner.seconds == 60.0 + 600.0 + 1200.0 + 1800.0 + 2400.0 + 60.0
    assert "6 jobs" in after.timing.runner.note
    assert after.timing.initial_queue.seconds == 10.0
    assert after.dependent_wait.seconds == 10.0
    assert "not queue time alone" in after.dependent_wait.note
    assert after.timing.request_latency.seconds == 2760.0
    assert after.timing.setup.seconds == 60.0 + 40.0 + 60.0
    assert after.modeled_serial.seconds == 500.0 + 1000.0 + 1500.0 + 2000.0
    assert "modeled serial work" in after.modeled_serial.note
    assert after.internal_setup.seconds is None
    assert all(
        shard.runtimes == {"3.13": "CPython 3.13.1", "3.14": "CPython 3.14.1"}
        for shard in after.shards
    )
    assert after.coverage == coverage_of([envelopes[shard.subject] for shard in SHARDS])
    (note,) = after.notes
    assert "identifies the workflow's ref" in note and request.head_commit in note


def test_runner_minutes_are_partial_when_an_allocated_job_lacks_a_timestamp(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _dispatch_request(head_commit)
    assembled = _assembled(tmp_path, request, envelopes)
    jobs = _after_jobs([shard.id for shard in SHARDS], assemble_completed=None)
    after = _after(assembled, request, jobs)
    assert after.timing.runner.seconds == 60.0 + 600.0 + 1200.0 + 1800.0 + 2400.0
    assert after.timing.runner.note.startswith("partial: 5 of 6 allocated jobs timed")
    assert "`assemble`" in after.timing.runner.note
    assert after.timing.elapsed.seconds is None
    assert after.timing.request_latency.seconds is None
    assert after.timing.setup.seconds is None


def test_after_coverage_is_validated_against_its_own_plan_even_without_a_historical_comparison(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document], before_portfolio: Document
) -> None:
    request = _dispatch_request(head_commit)
    missing = SHARDS[2]
    after = _after(_assembled(tmp_path, request, envelopes, skip=[missing.id]), request)
    assert not after.complete
    outcome = next(shard for shard in after.shards if shard.id == missing.id)
    assert not outcome.complete
    assert (
        outcome.reasons[0].startswith("head-missing:") and outcome.reasons[-1] == "no head capture"
    )
    assert all(shard.complete for shard in after.shards if shard.id != missing.id)
    assert after.coverage.subjects == tuple(
        sorted(shard.subject for shard in SHARDS if shard.id != missing.id)
    )
    before = _before(before_portfolio, _before_jobs(head_conclusion="cancelled"))
    result = evidence(before, after)
    assert result.reduction.seconds is None
    assert "after coverage incomplete against its plan" in result.reduction.note
    assert "before measurement evidence insufficient" in result.reduction.note
    rendered = result.render()
    assert f"- `{missing.id}` ({missing.subject}): incomplete: head-missing:" in rendered
    assert "## Insufficient evidence" in rendered


def test_a_cancelled_or_failed_measure_job_makes_the_after_evidence_insufficient(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _dispatch_request(head_commit)
    assembled = _assembled(tmp_path, request, envelopes)
    ids = [shard.id for shard in SHARDS]
    cancelled = _after(
        assembled,
        request,
        _after_jobs(ids, measure_conclusions=["success", "cancelled", "success", "success"]),
    )
    assert cancelled.complete and not cancelled.sufficient
    assert cancelled.problems == (f"shard {ids[1]}'s measure job ended cancelled",)
    failed_step = _after(
        assembled,
        request,
        _after_jobs(ids, step_conclusions=["success", "success", "failure", "success"]),
    )
    assert failed_step.problems == (f"shard {ids[2]}'s `{MEASURE_STEP}` step ended failure",)
    absent = _after(assembled, request, _after_jobs([*ids[:-1], "stray"]))
    assert f"shard {ids[-1]} has no measure job in the run's jobs" in absent.problems
    assert any("'stray', which is not planned" in problem for problem in absent.problems)


def test_the_measured_commit_is_the_requests_and_never_a_dispatch_runs_head_sha(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _dispatch_request(head_commit)
    assembled = _assembled(tmp_path, request, envelopes)
    other = "a" * 40
    dispatched = _after(assembled, request, head_sha=other)
    assert dispatched.sufficient
    assert dispatched.request.head_commit == head_commit
    (note,) = dispatched.notes
    assert f"differs from the workflow revision {request.workflow_commit}" in note
    scheduled_request = Request.from_document({**request.document(), "event": "schedule"})
    scheduled = _assembled(tmp_path / "scheduled", scheduled_request, envelopes)
    moved = _after(scheduled, scheduled_request, event="schedule", head_sha=other)
    assert not moved.sufficient
    assert any("is not the measured commit" in problem for problem in moved.problems)
    same = _after(scheduled, scheduled_request, event="schedule", head_sha=head_commit)
    assert same.sufficient and same.notes == ()


def test_run_attempt_and_event_are_cross_checked_before_arithmetic(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _dispatch_request(head_commit)
    assembled = _assembled(tmp_path, request, envelopes)
    ids = [shard.id for shard in SHARDS]
    other_run = sharded(
        Run.from_document(_run("7", "workflow_dispatch", request.workflow_commit)),
        _jobs(_after_jobs(ids, run_id="7")),
        assembled,
    )
    assert any("not run 7 attempt 1" in problem for problem in other_run.problems)
    other_attempt = sharded(
        Run.from_document(_run(AFTER_RUN, "workflow_dispatch", request.workflow_commit, attempt=2)),
        _jobs(_after_jobs(ids, attempt=2)),
        assembled,
    )
    assert any("attempt 1, not run" in problem for problem in other_attempt.problems)
    other_event = _after(assembled, request, event="pull_request")
    assert any(
        "event workflow_dispatch is not the run's pull_request" in p for p in other_event.problems
    )
    foreign_jobs = _after(assembled, request, _after_jobs(ids, run_id="9"))
    assert any("belongs to run 9, not 424242" in problem for problem in foreign_jobs.problems)


def test_a_head_capture_that_disagrees_with_the_request_is_incomplete(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document]
) -> None:
    request = _dispatch_request(head_commit)
    assembled = _assembled(tmp_path, request, envelopes)
    portfolio = json.loads((assembled / "portfolio.json").read_text(encoding="utf-8"))
    first = portfolio["shards"][0]
    first["head"]["capture"]["commit"] = "a" * 40
    second = portfolio["shards"][1]
    second["head"]["portfolio"]["members"][0]["provenance"]["commit"] = "a" * 40
    third = portfolio["shards"][2]
    third["head"]["portfolio"]["members"][0]["incomplete"] = [{"code": "x", "message": "y"}]
    fourth = portfolio["shards"][3]
    fourth["reasons"] = [{"code": "envelope-invalid", "side": "head", "message": "bad"}]
    (assembled / "portfolio.json").write_text(json.dumps(portfolio), encoding="utf-8")
    after = _after(assembled, request)
    assert not after.complete
    reasons = [shard.reasons for shard in after.shards]
    assert any("measured " + "a" * 40 in reason for reason in reasons[0])
    assert any("provenance names " + "a" * 40 in reason for reason in reasons[1])
    assert reasons[2] == ("the head envelope is incomplete or carries errors",)
    assert reasons[3] == ("envelope-invalid: bad",)
    assert after.coverage.total == 0


def _spans_with_setup(shard_id: str, subject: str, setup_seconds: float) -> Spans:
    elapsed = [0.0]
    spans = Spans(clock=lambda: elapsed[0], now=lambda: CLOCK + timedelta(seconds=elapsed[0]))
    with spans.span("collection", shard_id, shard=shard_id):
        with spans.span("setup", "provisioner", member=subject):
            elapsed[0] += setup_seconds
        with spans.span("member", subject, member=subject):
            elapsed[0] += 100.0
    return spans


def test_the_measurement_path_reads_head_spans_and_a_missing_sidecar_is_unknown(
    tmp_path: Path, head_commit: str, envelopes: dict[str, Document], contract: BudgetContract
) -> None:
    request = _dispatch_request(head_commit)
    inputs = tmp_path / "inputs"
    for index, shard in enumerate(SHARDS):
        spans = _spans_with_setup(shard.id, shard.subject, 30.0 * (index + 1))
        result = ShardResult(
            shard,
            MemberResult(shard.member, envelopes[shard.subject]),
            spans,
            identities(),
        )
        write_shard(
            result,
            request,
            HEAD,
            head_commit,
            f"pair-{shard.id}",
            inputs / shard.id / HEAD / shard.id,
        )
    captures = discover(inputs)
    out = tmp_path / "assembled"
    write_assembly(assemble(captures, SHARDS, request), inputs, captures, out)
    after = _after(out, request)
    assert after.timing.measurement_path.seconds == 220.0
    assert after.internal_setup.seconds == 120.0
    assert f"`{SHARDS[0].id}` 30 s" in after.internal_setup.note
    assert after.modeled_serial.seconds == 130.0 + 160.0 + 190.0 + 220.0
    (out / DURATIONS_FILE).unlink()
    without = _after(out, request)
    assert without.timing.measurement_path.seconds is None
    assert without.modeled_serial.seconds is None
    assert without.internal_setup.seconds is None
    assert without.longest_job.seconds == 2400.0
    assert any(f"carries no {DURATIONS_FILE}" in note for note in without.notes)
    (out / DURATIONS_FILE).write_text("{", encoding="utf-8")
    corrupt = _after(out, request)
    assert corrupt.timing.measurement_path.seconds is None
    assert any("does not decode" in note for note in corrupt.notes)


# --------------------------------------------------------------------------- #
# The evidence                                                                 #
# --------------------------------------------------------------------------- #
def test_equivalent_coverage_under_one_protocol_yields_an_observed_historical_reduction(
    tmp_path: Path,
    head_commit: str,
    envelopes: dict[str, Document],
    before_portfolio: Document,
) -> None:
    before = _before(before_portfolio)
    request = _dispatch_request(head_commit)
    after = _after(_assembled(tmp_path, request, envelopes), request)
    result = evidence(before, after)
    assert result.verdict.equivalent and result.verdict.same_protocol
    assert result.reduction.seconds == 10672.0 - 2750.0
    assert result.reduction.note.startswith(f"{(10672.0 - 2750.0) / 10672.0:+.1%}")
    assert "not an isolated causal speedup" in result.reduction.note
    assert any(
        f"before {BEFORE_COMMIT}, after {head_commit}" in caveat for caveat in result.caveats
    )
    assert any("unknown is not zero" in caveat for caveat in result.caveats)
    rendered = result.render()
    assert "| Scope | head-only | head-only |" in rendered
    assert (
        "| Report elapsed | 2h 57m 52s (`python-report-cost` job start to completion) | 45m 50s"
        in rendered
    )
    assert "| Runner minutes | 177.9 min (the one report job's duration) | 102.0 min" in rendered
    assert "| Observed reduction | -2h 12m 02s (" in rendered
    assert "Equivalent: the same multiset" in rendered
    assert ORDINARY_CI_ROW in rendered
    assert (
        "| Interpreters | 3.14.7; 3.13 patch unknown (parent CPython from provenance) | "
        "CPython 3.13.1, CPython 3.14.1 |"
    ) in rendered
    assert (
        "| Internal setup spans | unknown (not instrumented) | "
        "unknown (no head setup spans arrived) |"
    ) in rendered
    assert "Modeled serial work | not applicable (observed sequentially) | 1h 23m 20s" in rendered


def test_a_coverage_or_protocol_mismatch_is_prominent_and_withholds_the_claim(
    tmp_path: Path,
    head_commit: str,
    envelopes: dict[str, Document],
    before_portfolio: Document,
) -> None:
    before = _before(_perturbed(before_portfolio, "missing"))
    request = _dispatch_request(head_commit)
    after = _after(_assembled(tmp_path, request, envelopes), request)
    result = evidence(before, after)
    assert result.reduction.seconds is None and result.reduction.note == "coverage mismatch"
    rendered = result.render()
    assert "**Mismatch: the two runs did not measure the same work." in rendered
    assert "- extra after, snapshot-delivery: 1 address(es)" in rendered
    assert "| Observed reduction | withheld: coverage mismatch | |" in rendered
    altered = deepcopy(before_portfolio)
    altered["members"][3]["provenance"]["sampling"]["measured"] = 5
    with_protocol = evidence(_before(altered), after)
    assert with_protocol.reduction.note == "protocol differs"
    assert (
        "- protocol: write-lowering: sampling measured 5 before, 9 after" in with_protocol.render()
    )


# --------------------------------------------------------------------------- #
# The entry point and the workflow's names                                     #
# --------------------------------------------------------------------------- #
def test_the_entry_point_renders_the_evidence_and_refuses_unreadable_inputs(
    tmp_path: Path,
    head_commit: str,
    envelopes: dict[str, Document],
    before_portfolio: Document,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _dispatch_request(head_commit)
    assembled = _assembled(tmp_path, request, envelopes)
    paths = {
        "before-portfolio": tmp_path / "before-portfolio.json",
        "before-run": tmp_path / "before-run.json",
        "after-run": tmp_path / "after-run.json",
        "before-jobs": tmp_path / "before-jobs.json",
        "after-jobs": tmp_path / "after-jobs.json",
    }
    paths["before-portfolio"].write_text(json.dumps(before_portfolio), encoding="utf-8")
    paths["before-run"].write_text(
        json.dumps(_run(BEFORE_RUN, "push", BEFORE_COMMIT)), encoding="utf-8"
    )
    paths["after-run"].write_text(
        json.dumps(_run(AFTER_RUN, "workflow_dispatch", request.workflow_commit)), encoding="utf-8"
    )
    paths["before-jobs"].write_text(json.dumps(_before_jobs()), encoding="utf-8")
    paths["after-jobs"].write_text(
        json.dumps(_after_jobs([shard.id for shard in SHARDS])), encoding="utf-8"
    )
    arguments = [f"--{name}={path}" for name, path in paths.items()] + [f"--after={assembled}"]
    assert evidence_tool.main(arguments) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Cost report evidence: historical sequential before, sharded after")
    assert "| Observed reduction | -2h 12m 02s" in out
    assert len(load_jobs(paths["before-jobs"])) == 3
    paths["before-jobs"].write_text('{"jobs": "none"}', encoding="utf-8")
    with pytest.raises(SystemExit) as refused:
        evidence_tool.main(arguments)
    assert refused.value.code == 2
    assert "jobs is not a list" in capsys.readouterr().err
    paths["before-jobs"].unlink()
    with pytest.raises(SystemExit) as absent:
        evidence_tool.main(arguments)
    assert absent.value.code == 2


def test_the_after_job_and_step_names_are_the_workflows() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "cost-report.yml").read_text(encoding="utf-8")
    )
    jobs = cast("dict[str, Any]", workflow["jobs"])
    assert set(jobs) == {
        evidence_tool.PLAN_JOB,
        evidence_tool.MEASURE_JOB,
        evidence_tool.ASSEMBLE_JOB,
        evidence_tool.CLEANUP_JOB,
    }
    measure_steps = [step.get("name") for step in jobs[evidence_tool.MEASURE_JOB]["steps"]]
    assert MEASURE_STEP in measure_steps and SHARD_UPLOAD_STEP in measure_steps
