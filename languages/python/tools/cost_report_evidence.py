"""Put a retained historical sequential cost report beside a new sharded
assembly and say what the two runs cost, offline.

The comparison is one of execution cost, never of readings: the two captures
come from different commits and different runners, so their values are not
paired. What is compared is coverage — the multiset of every reading's
address and unit, the sample count behind each, and each subject's workload
and sampling protocol — and the wall-clock and runner-minute cost GitHub
recorded for each run. Every quantity is taken from GitHub's run and job
metadata or from the assembly's own sidecar, and a quantity the metadata does
not establish is unknown: it is never zero, never estimated, and a partial
total says which parts it lacks.

Head-only is compared with head-only. A paired historical job and a head-only
after run measure different work, and no ratio between them is a speedup.
Coverage or protocol differences are stated first and withhold any reduction
claim; an observed reduction is a historical before/after, never an isolated
cause. Runner minutes are job durations, never sums of nested spans, and the
sum of shard collection spans is a modeled serial-work total, not an observed
sequential duration.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, cast

from cost_report import ASSEMBLY_VERSION, DURATIONS_FILE, HEAD, PORTFOLIO_VERSION, Capture, Request
from durations import Spans

type Document = Mapping[str, object]
type Address = tuple[str, str, str, str, str, str]
"""A reading's (subject, runtime, window, workload, cell, unit); a reading
without a runtime or window carries the empty string there."""

HISTORICAL_JOB: Final = "python-report-cost"
HISTORICAL_HEAD_STEP: Final = "Measure head"
HISTORICAL_BASE_STEP: Final = "Measure merge-base"
HISTORICAL_UPLOAD_STEP: Final = "Upload head reports"

PLAN_JOB: Final = "plan"
MEASURE_JOB: Final = "measure"
ASSEMBLE_JOB: Final = "assemble"
CLEANUP_JOB: Final = "cleanup"
MEASURE_STEP: Final = "Measure base then head"
SHARD_UPLOAD_STEP: Final = "Upload the shard"

HEAD_ONLY: Final = "head-only"
PAIRED: Final = "paired"
UNKNOWN_SCOPE: Final = "unknown"

SUCCESS: Final = "success"
SKIPPED: Final = "skipped"
COMPLETED: Final = "completed"
DISPATCH_EVENT: Final = "workflow_dispatch"
SCHEDULE_EVENT: Final = "schedule"
PULL_REQUEST_EVENT: Final = "pull_request"

RUN_URL: Final = "https://github.com/{repository}/actions/runs/{run}"
JOB_URL: Final = "https://github.com/{repository}/actions/runs/{run}/job/{job}"

ORDINARY_CI_ROW: Final = (
    "| Ordinary CI | `python-report-cost` measured a fresh portfolio on every push and pull "
    "request (this before job) | `python-verify-cost` verifies the committed evidence only; "
    "fresh captures are the `cost-report` workflow's |"
)


# --------------------------------------------------------------------------- #
# GitHub metadata, as the run and jobs endpoints record it                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Run:
    id: str
    event: str
    head_sha: str
    attempt: int
    created_at: datetime | None
    status: str
    conclusion: str | None
    repository: str

    @classmethod
    def from_document(cls, document: object) -> Run:
        fields = _object(document, "run")
        return cls(
            _spelled(fields.get("id"), "run id"),
            _string(fields, "event"),
            _string(fields, "head_sha"),
            _integer(fields, "run_attempt"),
            _timestamp(fields.get("created_at")),
            _string(fields, "status"),
            _optional_string(fields, "conclusion"),
            _repository(fields),
        )

    @classmethod
    def load(cls, path: Path) -> Run:
        return cls.from_document(_load(path))

    @property
    def url(self) -> str:
        return RUN_URL.format(repository=self.repository, run=self.id)


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    status: str
    conclusion: str | None
    started_at: datetime | None
    completed_at: datetime | None

    @property
    def seconds(self) -> float | None:
        return _between(self.started_at, self.completed_at)

    @property
    def succeeded(self) -> bool:
        return self.status == COMPLETED and self.conclusion == SUCCESS


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    name: str
    status: str
    conclusion: str | None
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    steps: tuple[Step, ...]
    run_id: str | None
    run_attempt: int | None
    labels: tuple[str, ...]

    @property
    def seconds(self) -> float | None:
        if self.status != COMPLETED or self.conclusion == SKIPPED:
            return None
        return _between(self.started_at, self.completed_at)

    @property
    def succeeded(self) -> bool:
        return self.status == COMPLETED and self.conclusion == SUCCESS

    def step(self, name: str) -> Step | None:
        found = [step for step in self.steps if step.name == name]
        return found[0] if len(found) == 1 else None

    def url(self, run: Run) -> str:
        return JOB_URL.format(repository=run.repository, run=run.id, job=self.id)


def load_jobs(path: Path) -> tuple[Job, ...]:
    """The jobs of one run attempt, from a ``{jobs: [...]}`` document."""
    document = _object(_load(path), "jobs document")
    listed = document.get("jobs")
    if not isinstance(listed, Sequence) or isinstance(listed, str):
        raise ValueError(f"{path} jobs is not a list")
    return tuple(_job(entry) for entry in cast("Sequence[object]", listed))


def _job(entry: object) -> Job:
    fields = _object(entry, "job")
    steps = fields.get("steps", [])
    if not isinstance(steps, Sequence) or isinstance(steps, str):
        raise ValueError("job steps is not a list")
    labels = fields.get("labels", [])
    if not isinstance(labels, Sequence) or isinstance(labels, str):
        raise ValueError("job labels is not a list")
    return Job(
        _spelled(fields.get("id"), "job id"),
        _string(fields, "name"),
        _string(fields, "status"),
        _optional_string(fields, "conclusion"),
        _timestamp(fields.get("created_at")),
        _timestamp(fields.get("started_at")),
        _timestamp(fields.get("completed_at")),
        tuple(_step(step) for step in cast("Sequence[object]", steps)),
        _spelled(fields.get("run_id"), "job run_id") if fields.get("run_id") is not None else None,
        _integer(fields, "run_attempt") if fields.get("run_attempt") is not None else None,
        tuple(str(label) for label in cast("Sequence[object]", labels)),
    )


def _step(entry: object) -> Step:
    fields = _object(entry, "step")
    return Step(
        _string(fields, "name"),
        _string(fields, "status"),
        _optional_string(fields, "conclusion"),
        _timestamp(fields.get("started_at")),
        _timestamp(fields.get("completed_at")),
    )


def _repository(fields: Mapping[str, object]) -> str:
    repository = fields.get("repository")
    if isinstance(repository, Mapping):
        name = cast("Mapping[str, object]", repository).get("full_name")
        if isinstance(name, str) and name:
            return name
    url = fields.get("html_url")
    if isinstance(url, str) and "/actions/runs/" in url:
        return url.split("https://github.com/", 1)[-1].split("/actions/runs/", 1)[0]
    return "unknown"


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _between(started: datetime | None, completed: datetime | None) -> float | None:
    if started is None or completed is None:
        return None
    seconds = (completed - started).total_seconds()
    return seconds if seconds >= 0 else None


# --------------------------------------------------------------------------- #
# Coverage: what was measured, as a multiset of addresses and their samples    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Protocol:
    """One subject's workload and sampling identity, beside the digests that
    are displayed but do not decide identity."""

    subject: str
    commit: str
    workload_digest: str
    sampling: Mapping[str, str]
    contract_digest: str
    lock_digest: str
    cpython: str


@dataclass(frozen=True, slots=True)
class Coverage:
    readings: Mapping[Address, int]
    samples: Mapping[Address, tuple[int, ...]]
    protocols: Mapping[str, Protocol]

    @property
    def total(self) -> int:
        return sum(self.readings.values())

    @property
    def subjects(self) -> tuple[str, ...]:
        return tuple(sorted({address[0] for address in self.readings} | set(self.protocols)))


def coverage_of(envelopes: Sequence[Document]) -> Coverage:
    """The multiset of addresses over ``envelopes``, the sample counts behind
    each address in ascending order, and each subject's protocol."""
    readings: Counter[Address] = Counter()
    samples: dict[Address, list[int]] = {}
    protocols: dict[str, Protocol] = {}
    for envelope in envelopes:
        subject = str(envelope.get("subject"))
        for reading in cast("Sequence[object]", envelope.get("readings", ())):
            entry = _object(reading, "reading")
            address: Address = (
                subject,
                str(entry.get("runtime") or ""),
                str(entry.get("window") or ""),
                str(entry.get("workload")),
                str(entry.get("cell")),
                str(entry.get("unit")),
            )
            readings[address] += 1
            samples.setdefault(address, []).append(
                len(cast("Sequence[object]", entry.get("samples", ())))
            )
        provenance = envelope.get("provenance")
        if isinstance(provenance, Mapping):
            fields = cast("Mapping[str, object]", provenance)
            protocols[subject] = Protocol(
                subject,
                str(fields.get("commit", "unknown")),
                str(fields.get("workloadDigest", "unknown")),
                _flattened(fields.get("sampling")),
                str(fields.get("budgetContractDigest", "unknown")),
                str(fields.get("lockDigest", "unknown")),
                str(fields.get("cpython", "unknown")),
            )
    return Coverage(
        dict(readings),
        {address: tuple(sorted(counts)) for address, counts in samples.items()},
        protocols,
    )


def _flattened(value: object, prefix: str = "") -> dict[str, str]:
    """A nested sampling document as dotted keys, so a protocol difference
    names the one field that moved."""
    if isinstance(value, Mapping):
        flattened: dict[str, str] = {}
        for key, nested in cast("Mapping[object, object]", value).items():
            flattened.update(_flattened(nested, f"{prefix}{key}."))
        return flattened
    return {prefix.rstrip("."): json.dumps(value, sort_keys=True)}


@dataclass(frozen=True, slots=True)
class CoverageVerdict:
    missing: tuple[Address, ...]
    extra: tuple[Address, ...]
    recounted: tuple[tuple[Address, int, int], ...]
    resampled: tuple[tuple[Address, tuple[int, ...], tuple[int, ...]], ...]
    protocol_differences: tuple[str, ...]
    displayed_differences: tuple[str, ...]

    @property
    def equivalent(self) -> bool:
        return not (self.missing or self.extra or self.recounted or self.resampled)

    @property
    def same_protocol(self) -> bool:
        return not self.protocol_differences


def compare_coverage(before: Coverage, after: Coverage) -> CoverageVerdict:
    """Every way ``after`` measures other work than ``before``: addresses on
    one side alone, an address counted differently, an address sampled
    differently, and a subject whose workload digest or sampling protocol
    changed. Contract and lock digests are displayed, never judged."""
    missing = tuple(sorted(set(before.readings) - set(after.readings)))
    extra = tuple(sorted(set(after.readings) - set(before.readings)))
    shared = sorted(set(before.readings) & set(after.readings))
    recounted = tuple(
        (address, before.readings[address], after.readings[address])
        for address in shared
        if before.readings[address] != after.readings[address]
    )
    resampled = tuple(
        (address, before.samples[address], after.samples[address])
        for address in shared
        if before.samples[address] != after.samples[address]
    )
    protocol: list[str] = []
    displayed: list[str] = []
    for subject in sorted(set(before.protocols) | set(after.protocols)):
        first = before.protocols.get(subject)
        second = after.protocols.get(subject)
        if first is None or second is None:
            side = "before" if first is None else "after"
            protocol.append(f"{subject}: no provenance on the {side} side")
            continue
        if first.workload_digest != second.workload_digest:
            protocol.append(
                f"{subject}: workload digest {first.workload_digest} before, "
                f"{second.workload_digest} after"
            )
        for key in sorted(set(first.sampling) | set(second.sampling)):
            if first.sampling.get(key) != second.sampling.get(key):
                protocol.append(
                    f"{subject}: sampling {key} {first.sampling.get(key, 'absent')} before, "
                    f"{second.sampling.get(key, 'absent')} after"
                )
        if first.contract_digest != second.contract_digest:
            displayed.append(
                f"{subject}: Budget Contract digest {first.contract_digest} before, "
                f"{second.contract_digest} after"
            )
        if first.lock_digest != second.lock_digest:
            displayed.append(
                f"{subject}: lock digest {first.lock_digest} before, {second.lock_digest} after"
            )
    return CoverageVerdict(missing, extra, recounted, resampled, tuple(protocol), tuple(displayed))


# --------------------------------------------------------------------------- #
# The two sides                                                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Quantity:
    """Seconds the metadata establishes, or ``None`` with the reason it does
    not; ``note`` also qualifies a known value, such as a partial total."""

    seconds: float | None
    note: str = ""

    @classmethod
    def unknown(cls, reason: str) -> Quantity:
        return cls(None, reason)


@dataclass(frozen=True, slots=True)
class Timing:
    elapsed: Quantity
    measurement_path: Quantity
    runner: Quantity
    initial_queue: Quantity
    request_latency: Quantity
    setup: Quantity


@dataclass(frozen=True, slots=True)
class Historical:
    """The retained sequential report: one job of the ordinary CI run."""

    run: Run
    job: Job | None
    scope: str
    commit: str | None
    coverage: Coverage
    timing: Timing
    problems: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def sufficient(self) -> bool:
        return not self.problems


@dataclass(frozen=True, slots=True)
class ShardOutcome:
    id: str
    subject: str
    complete: bool
    reasons: tuple[str, ...]
    runtimes: Mapping[str, str]
    runner: str
    head_seconds: float | None
    setup_seconds: float | None
    job: Job | None


@dataclass(frozen=True, slots=True)
class Sharded:
    """The new assembly and the workflow run that produced it."""

    run: Run
    request: Request
    scope: str
    shards: tuple[ShardOutcome, ...]
    coverage: Coverage
    timing: Timing
    longest_job: Quantity
    dependent_wait: Quantity
    modeled_serial: Quantity
    internal_setup: Quantity
    problems: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return bool(self.shards) and all(shard.complete for shard in self.shards)

    @property
    def sufficient(self) -> bool:
        return not self.problems and self.complete


def historical(run: Run, jobs: Sequence[Job], portfolio: Document) -> Historical:
    """The historical side, cross-checked before any arithmetic: the one
    report job of the run, its head measurement step, and the portfolio it
    uploaded. A successful measurement inside a job that failed elsewhere is
    sufficient evidence; a failed, cancelled, or untimed measurement is not."""
    problems: list[str] = []
    notes: list[str] = []
    if portfolio.get("schemaVersion") != PORTFOLIO_VERSION:
        problems.append(
            f"the before portfolio has schemaVersion {portfolio.get('schemaVersion')!r}, "
            f"not the legacy {PORTFOLIO_VERSION}"
        )
    members = [
        _object(member, "member")
        for member in cast("Sequence[object]", portfolio.get("members", ()))
    ]
    failures = cast("Sequence[object]", portfolio.get("failures", ()))
    if failures:
        problems.append(f"the before portfolio records {len(failures)} collection failure(s)")
    coverage = coverage_of(members)
    commits = {protocol.commit for protocol in coverage.protocols.values()}
    commit = next(iter(commits)) if len(commits) == 1 else None
    if commit is None:
        problems.append(f"the before members name {len(commits)} producing commit(s), not one")
    elif commit != run.head_sha:
        problems.append(
            f"the before run's head_sha {run.head_sha} is not the portfolio's producing "
            f"commit {commit}"
        )
    named = [job for job in jobs if job.name == HISTORICAL_JOB]
    if len(named) != 1:
        problems.append(f"the before run has {len(named)} `{HISTORICAL_JOB}` job(s), not one")
        return Historical(
            run, None, UNKNOWN_SCOPE, commit, coverage, _unknown_timing(), tuple(problems), ()
        )
    job = named[0]
    _cross_check_job(job, run, problems, "before")
    head = job.step(HISTORICAL_HEAD_STEP)
    base = job.step(HISTORICAL_BASE_STEP)
    upload = job.step(HISTORICAL_UPLOAD_STEP)
    if base is None:
        scope = UNKNOWN_SCOPE
        problems.append(
            f"the before job has no `{HISTORICAL_BASE_STEP}` step, so its scope is unknown"
        )
    elif base.conclusion == SKIPPED:
        scope = HEAD_ONLY
    elif base.succeeded:
        scope = PAIRED
    else:
        scope = UNKNOWN_SCOPE
        problems.append(f"the before job's `{HISTORICAL_BASE_STEP}` step ended {base.conclusion}")
    if head is None:
        problems.append(f"the before job has no `{HISTORICAL_HEAD_STEP}` step")
    elif not head.succeeded:
        problems.append(
            f"the before job's `{HISTORICAL_HEAD_STEP}` step ended "
            f"{head.conclusion or head.status}, so its measurement is not evidence"
        )
    elif head.seconds is None:
        problems.append(f"the before job's `{HISTORICAL_HEAD_STEP}` step carries no timestamps")
    if upload is None or not upload.succeeded:
        problems.append(f"the before job's `{HISTORICAL_UPLOAD_STEP}` step did not succeed")
    if not job.succeeded and head is not None and head.succeeded:
        notes.append(
            f"the before job ended {job.conclusion}: its `{HISTORICAL_HEAD_STEP}` and "
            f"`{HISTORICAL_UPLOAD_STEP}` steps succeeded, and the failure is the job's separate "
            "verification of the committed evidence, not the measurement"
        )
    timing = Timing(
        _quantity(job.seconds, f"`{HISTORICAL_JOB}` job start to completion"),
        _quantity(
            head.seconds if head is not None else None,
            f"the `{HISTORICAL_HEAD_STEP}` step",
        ),
        _quantity(job.seconds, "the one report job's duration"),
        _quantity(
            _between(run.created_at, job.started_at),
            "run creation to the report job's start",
            "the run's created_at or the job's started_at is absent",
        ),
        _quantity(
            _between(run.created_at, job.completed_at),
            "run creation to the report job's completion",
            "the run's created_at or the job's completed_at is absent",
        ),
        _quantity(
            _between(job.started_at, head.started_at if head is not None else None),
            "job start to the head measurement's start, verification included",
            "the job's or the measurement step's started_at is absent",
        ),
    )
    return Historical(run, job, scope, commit, coverage, timing, tuple(problems), tuple(notes))


def sharded(run: Run, jobs: Sequence[Job], assembled: Path) -> Sharded:
    """The after side, cross-checked before any arithmetic: the assembly's
    request against the run, every planned shard's head against the request
    and its own envelope, and the workflow's jobs against the plan."""
    problems: list[str] = []
    notes: list[str] = []
    portfolio = _object(_load(assembled / "portfolio.json"), "assembled portfolio")
    if portfolio.get("schemaVersion") != ASSEMBLY_VERSION:
        raise ValueError(
            f"the assembled portfolio has schemaVersion {portfolio.get('schemaVersion')!r}, "
            f"not {ASSEMBLY_VERSION}"
        )
    request = Request.from_document(portfolio.get("request"))
    if request.run_id != run.id or request.run_attempt != run.attempt:
        problems.append(
            f"the assembly answers run {request.run_id} attempt {request.run_attempt}, "
            f"not run {run.id} attempt {run.attempt}"
        )
    if request.event != run.event:
        problems.append(f"the assembly's event {request.event} is not the run's {run.event}")
    if run.event == SCHEDULE_EVENT and run.head_sha != request.head_commit:
        problems.append(
            f"the scheduled run's head_sha {run.head_sha} is not the measured commit "
            f"{request.head_commit}"
        )
    if run.event == DISPATCH_EVENT:
        notes.append(
            f"the dispatch run's head_sha {run.head_sha} identifies the workflow's ref"
            + (
                f" (workflow revision {request.workflow_commit})"
                if run.head_sha == request.workflow_commit
                else f", which differs from the workflow revision {request.workflow_commit}"
            )
            + f"; the measured commit is the request's {request.head_commit}"
        )
    if run.event == PULL_REQUEST_EVENT:
        notes.append(
            f"the pull request run's head_sha {run.head_sha} is the event's ref; the measured "
            f"commit is the request's {request.head_commit}"
        )
    scope = PAIRED if request.base_commit is not None else HEAD_ONLY
    plan = [
        _object(shard, "planned shard")
        for shard in cast("Sequence[object]", portfolio.get("plan", ()))
    ]
    entries = {
        str(_object(entry, "assembled shard").get("id")): _object(entry, "assembled shard")
        for entry in cast("Sequence[object]", portfolio.get("shards", ()))
    }
    spans = _spans(assembled / DURATIONS_FILE, notes)
    head_seconds = _seconds_by_shard(spans, "collection")
    setup_seconds = _seconds_by_shard(spans, "setup")
    measure_jobs = _measure_jobs(jobs)
    outcomes: list[ShardOutcome] = []
    envelopes: list[Document] = []
    for planned in plan:
        shard_id = str(planned.get("id"))
        subject = str(planned.get("subject"))
        outcome = _shard_outcome(
            shard_id,
            subject,
            entries.get(shard_id),
            request,
            head_seconds.get(shard_id),
            setup_seconds.get(shard_id),
            measure_jobs.pop(shard_id, None),
            envelopes,
        )
        outcomes.append(outcome)
    for shard_id, job in measure_jobs.items():
        problems.append(f"measure job `{job.name}` names shard {shard_id!r}, which is not planned")
    for outcome in outcomes:
        if outcome.job is None:
            problems.append(f"shard {outcome.id} has no measure job in the run's jobs")
        elif not outcome.job.succeeded:
            problems.append(
                f"shard {outcome.id}'s measure job ended "
                f"{outcome.job.conclusion or outcome.job.status}"
            )
        elif (step := outcome.job.step(MEASURE_STEP)) is None or not step.succeeded:
            problems.append(
                f"shard {outcome.id}'s `{MEASURE_STEP}` step "
                + ("is absent" if step is None else f"ended {step.conclusion or step.status}")
            )
    plan_job = _unique(jobs, PLAN_JOB, run, problems)
    assemble_job = _unique(jobs, ASSEMBLE_JOB, run, problems)
    report_jobs = [job for job in jobs if job.name != CLEANUP_JOB]
    ended = [job.completed_at for job in report_jobs if job.completed_at is not None]
    timing = Timing(
        _quantity(
            _between(
                plan_job.started_at if plan_job is not None else None,
                max(ended) if ended and len(ended) == len(report_jobs) else None,
            ),
            "plan job start to the last report job's completion",
            "a report job's timestamp is absent",
        ),
        _longest(head_seconds, "the longest head shard collection span", "shard"),
        _runner_minutes(jobs),
        _quantity(
            _between(run.created_at, plan_job.started_at if plan_job is not None else None),
            "run creation to the plan job's start",
            "the run's created_at or the plan job's started_at is absent",
        ),
        _quantity(
            _between(
                run.created_at, assemble_job.completed_at if assemble_job is not None else None
            ),
            "run creation to the assemble job's completion",
            "the run's created_at or the assemble job's completed_at is absent",
        ),
        _setup(plan_job, assemble_job, outcomes),
    )
    return Sharded(
        run,
        request,
        scope,
        tuple(outcomes),
        coverage_of(envelopes),
        timing,
        _longest(
            {
                shard.id: shard.job.seconds
                for shard in outcomes
                if shard.job is not None and shard.job.seconds is not None
            },
            "the longest measure job",
            "shard",
        ),
        _dependent_wait(plan_job, outcomes),
        _modeled_serial(head_seconds, outcomes),
        _internal_setup(setup_seconds, outcomes),
        tuple(problems),
        tuple(notes),
    )


def _shard_outcome(
    shard_id: str,
    subject: str,
    entry: Document | None,
    request: Request,
    head_seconds: float | None,
    setup_seconds: float | None,
    job: Job | None,
    envelopes: list[Document],
) -> ShardOutcome:
    reasons: list[str] = []
    runtimes: dict[str, str] = {}
    runner = "unknown"
    if entry is None:
        reasons.append("the assembly has no entry for this planned shard")
        return ShardOutcome(
            shard_id,
            subject,
            False,
            tuple(reasons),
            runtimes,
            runner,
            head_seconds,
            setup_seconds,
            job,
        )
    for reason in cast("Sequence[object]", entry.get("reasons", ())):
        fields = _object(reason, "reason")
        if fields.get("side") == HEAD:
            reasons.append(f"{fields.get('code')}: {fields.get('message')}")
    head = entry.get("head")
    if not isinstance(head, Mapping):
        reasons.append("no head capture")
        return ShardOutcome(
            shard_id,
            subject,
            False,
            tuple(reasons),
            runtimes,
            runner,
            head_seconds,
            setup_seconds,
            job,
        )
    side = cast("Mapping[str, object]", head)
    try:
        capture = Capture.from_document(side.get("capture"))
    except (KeyError, TypeError, ValueError) as error:
        reasons.append(f"the head capture does not decode: {error}")
        return ShardOutcome(
            shard_id,
            subject,
            False,
            tuple(reasons),
            runtimes,
            runner,
            head_seconds,
            setup_seconds,
            job,
        )
    if capture.side != HEAD:
        reasons.append(f"the head capture's side is {capture.side}")
    if capture.commit != request.head_commit:
        reasons.append(f"the head capture measured {capture.commit}, not {request.head_commit}")
    for minor, status in capture.runtimes.items():
        document = status.document()
        runtimes[minor] = (
            f"{document.get('implementation')} {document.get('version')}"
            if document.get("status") == "available"
            else f"unavailable ({document.get('reason')})"
        )
    if capture.runner is not None:
        runner = f"{capture.runner.get('image')} {capture.runner.get('imageVersion')}"
    members = _subject_members(side.get("portfolio"), subject)
    if len(members) != 1:
        reasons.append(f"the head portfolio holds {len(members)} `{subject}` envelope(s), not one")
    else:
        envelope = members[0]
        provenance = envelope.get("provenance")
        producing = (
            cast("Mapping[str, object]", provenance).get("commit")
            if isinstance(provenance, Mapping)
            else None
        )
        if producing != request.head_commit:
            reasons.append(
                f"the head envelope's provenance names {producing}, not {request.head_commit}"
            )
        if envelope.get("incomplete") or envelope.get("errors"):
            reasons.append("the head envelope is incomplete or carries errors")
        if not reasons:
            envelopes.append(envelope)
    return ShardOutcome(
        shard_id,
        subject,
        not reasons,
        tuple(reasons),
        runtimes,
        runner,
        head_seconds,
        setup_seconds,
        job,
    )


def _subject_members(portfolio: object, subject: str) -> list[Document]:
    if not isinstance(portfolio, Mapping):
        return []
    listed = cast("Mapping[str, object]", portfolio).get("members", ())
    members: list[Document] = []
    for member in cast("Sequence[object]", listed):
        if isinstance(member, Mapping):
            fields = cast("Mapping[str, object]", member)
            if fields.get("subject") == subject:
                members.append(fields)
    return members


def _cross_check_job(job: Job, run: Run, problems: list[str], side: str) -> None:
    if job.run_id is not None and job.run_id != run.id:
        problems.append(f"the {side} job `{job.name}` belongs to run {job.run_id}, not {run.id}")
    if job.run_attempt is not None and job.run_attempt != run.attempt:
        problems.append(
            f"the {side} job `{job.name}` is attempt {job.run_attempt}, not {run.attempt}"
        )


def _unique(jobs: Sequence[Job], name: str, run: Run, problems: list[str]) -> Job | None:
    named = [job for job in jobs if job.name == name]
    if len(named) != 1:
        problems.append(f"the after run has {len(named)} `{name}` job(s), not one")
        return None
    _cross_check_job(named[0], run, problems, "after")
    if not named[0].succeeded:
        problems.append(
            f"the after run's `{name}` job ended {named[0].conclusion or named[0].status}"
        )
    return named[0]


def _measure_jobs(jobs: Sequence[Job]) -> dict[str, Job]:
    found: dict[str, Job] = {}
    for job in jobs:
        prefix = f"{MEASURE_JOB} ("
        if job.name.startswith(prefix) and job.name.endswith(")"):
            found[job.name[len(prefix) : -1]] = job
    return found


def _spans(path: Path, notes: list[str]) -> Spans | None:
    if not path.exists():
        notes.append(f"the assembly carries no {DURATIONS_FILE}; internal spans are unavailable")
        return None
    try:
        return Spans.load(path)
    except (KeyError, TypeError, ValueError, OSError) as error:
        notes.append(
            f"the assembly's {DURATIONS_FILE} does not decode ({error}); "
            "internal spans are unavailable"
        )
        return None


def _seconds_by_shard(spans: Spans | None, scope: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    if spans is None:
        return totals
    for span in spans.spans:
        if span.scope == scope and span.labels.get("side") == HEAD and "shard" in span.labels:
            totals[span.labels["shard"]] = totals.get(span.labels["shard"], 0.0) + span.seconds
    return totals


def _quantity(seconds: float | None, note: str, absent: str | None = None) -> Quantity:
    if seconds is None:
        return Quantity.unknown(absent or f"{note}: timestamps absent")
    return Quantity(seconds, note)


def _unknown_timing() -> Timing:
    unknown = Quantity.unknown("no report job identified")
    return Timing(unknown, unknown, unknown, unknown, unknown, unknown)


def _longest(seconds: Mapping[str, float | None], note: str, label: str) -> Quantity:
    known = {key: value for key, value in seconds.items() if value is not None}
    if not known:
        return Quantity.unknown(f"{note}: none recorded")
    longest = max(known, key=lambda key: known[key])
    return Quantity(known[longest], f"{note}, {label} `{longest}`")


def _runner_minutes(jobs: Sequence[Job]) -> Quantity:
    allocated = [job for job in jobs if job.conclusion != SKIPPED]
    known = [job for job in allocated if job.seconds is not None]
    total = sum(job.seconds or 0.0 for job in known)
    if len(known) < len(allocated):
        missing = ", ".join(f"`{job.name}`" for job in allocated if job.seconds is None)
        return Quantity(
            total,
            f"partial: {len(known)} of {len(allocated)} allocated jobs timed; {missing} unknown",
        )
    return Quantity(total, f"every allocated job's duration, {len(allocated)} jobs")


def _setup(
    plan_job: Job | None, assemble_job: Job | None, outcomes: Sequence[ShardOutcome]
) -> Quantity:
    parts: list[float] = []
    absent: list[str] = []
    if plan_job is None or plan_job.seconds is None:
        absent.append("the plan job")
    else:
        parts.append(plan_job.seconds)
    if assemble_job is None or assemble_job.seconds is None:
        absent.append("the assemble job")
    else:
        parts.append(assemble_job.seconds)
    pre: dict[str, float] = {}
    for outcome in outcomes:
        job = outcome.job
        step = job.step(MEASURE_STEP) if job is not None else None
        seconds = _between(
            job.started_at if job is not None else None,
            step.started_at if step is not None else None,
        )
        if seconds is None:
            absent.append(f"shard {outcome.id}'s measure job")
        else:
            pre[outcome.id] = seconds
    if absent:
        return Quantity.unknown("workflow-step setup: timestamps absent for " + ", ".join(absent))
    longest = max(pre, key=lambda key: pre[key]) if pre else None
    return Quantity(
        sum(parts) + (pre[longest] if longest is not None else 0.0),
        "plan job, the longest measure job's start-to-measurement (shard "
        + (f"`{longest}`" if longest is not None else "none")
        + "), and assemble job, in sequence; measure jobs' own setup runs concurrently",
    )


def _dependent_wait(plan_job: Job | None, outcomes: Sequence[ShardOutcome]) -> Quantity:
    starts = [
        outcome.job.started_at
        for outcome in outcomes
        if outcome.job is not None and outcome.job.started_at is not None
    ]
    if (
        plan_job is None
        or plan_job.completed_at is None
        or len(starts) != len(outcomes)
        or not starts
    ):
        return Quantity.unknown("plan completion or a measure job's start is absent")
    return Quantity(
        _between(plan_job.completed_at, min(starts)),
        "plan completion to the first measure job's start; dependent-job scheduling, "
        "not queue time alone",
    )


def _modeled_serial(
    head_seconds: Mapping[str, float], outcomes: Sequence[ShardOutcome]
) -> Quantity:
    if len(head_seconds) != len(outcomes) or not outcomes:
        return Quantity.unknown(
            f"head collection spans arrived for {len(head_seconds)} of {len(outcomes)} shards"
        )
    return Quantity(
        sum(head_seconds.values()),
        "sum of every shard's head collection span: modeled serial work, "
        "not an observed sequential duration",
    )


def _internal_setup(
    setup_seconds: Mapping[str, float], outcomes: Sequence[ShardOutcome]
) -> Quantity:
    if not setup_seconds:
        return Quantity.unknown("no head setup spans arrived")
    listed = ", ".join(
        f"`{outcome.id}` {_clock(setup_seconds[outcome.id])}"
        for outcome in outcomes
        if outcome.id in setup_seconds
    )
    return Quantity(
        max(setup_seconds.values()), f"the largest shard's head setup spans; per shard: {listed}"
    )


# --------------------------------------------------------------------------- #
# The evidence: both sides, the coverage verdict, and every caveat             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Evidence:
    before: Historical
    after: Sharded
    verdict: CoverageVerdict
    reduction: Quantity
    caveats: tuple[str, ...] = ()

    def render(self) -> str:
        return _render(self)


def evidence(before: Historical, after: Sharded) -> Evidence:
    """Both sides beside each other. A reduction is stated only for head-only
    against head-only, complete and equivalent coverage under one protocol,
    and sufficient measurement evidence on both sides; every other case
    withholds it and says why."""
    verdict = compare_coverage(before.coverage, after.coverage)
    caveats: list[str] = list(before.notes) + list(after.notes)
    withheld: list[str] = []
    if before.scope != after.scope or before.scope == UNKNOWN_SCOPE:
        withheld.append(f"scopes differ ({before.scope} before, {after.scope} after)")
        caveats.append(
            f"the before run is {before.scope} and the after run is {after.scope}; only like "
            "scopes are compared, and a paired job's duration is never divided by a head-only run's"
        )
    if not before.sufficient:
        withheld.append("before measurement evidence insufficient")
    if not after.complete:
        withheld.append("after coverage incomplete against its plan")
    if after.problems:
        withheld.append("after measurement evidence insufficient")
    if not verdict.equivalent:
        withheld.append("coverage mismatch")
    if not verdict.same_protocol:
        withheld.append("protocol differs")
    if before.timing.elapsed.seconds is None or after.timing.elapsed.seconds is None:
        withheld.append("an elapsed time is unknown")
    if before.commit is not None and before.commit != after.request.head_commit:
        caveats.append(
            f"the measured commits differ (before {before.commit}, after "
            f"{after.request.head_commit}); review their source differences rather than "
            "assuming equal work per reading"
        )
    caveats.append(
        "historical unknowns: the before run's per-member durations and internal setup attribution "
        "were not instrumented, and its interpreter patch versions beyond the parent CPython are "
        "not recorded; unknown is not zero"
    )
    caveats.extend(verdict.displayed_differences)
    if withheld:
        return Evidence(
            before, after, verdict, Quantity.unknown("; ".join(withheld)), tuple(caveats)
        )
    assert before.timing.elapsed.seconds is not None and after.timing.elapsed.seconds is not None
    delta = before.timing.elapsed.seconds - after.timing.elapsed.seconds
    percent = delta / before.timing.elapsed.seconds if before.timing.elapsed.seconds else 0.0
    return Evidence(
        before,
        after,
        verdict,
        Quantity(
            delta,
            f"{percent:+.1%} of the before elapsed: an observed historical before/after on "
            "different commits and runners, not an isolated causal speedup",
        ),
        tuple(caveats),
    )


def _render(result: Evidence) -> str:
    before, after = result.before, result.after
    lines = [
        "# Cost report evidence: historical sequential before, sharded after",
        "",
        "Execution cost of two runs, not readings: the captures come from different commits and "
        "runners and their values are never paired. Unknown is unknown, never zero.",
        "",
        "| | Before (historical) | After (sharded) |",
        "|---|---|---|",
        f"| Run | {_before_run(before)} | {_after_run(after)} |",
        f"| Measured commit | `{before.commit or 'unknown'}` | `{after.request.head_commit}` |",
        f"| Workflow revision | `{before.run.head_sha}` | `{after.request.workflow_commit}` |",
        f"| Scope | {before.scope} | {after.scope} |",
        f"| Partition | 1 runner, every member in sequence | {_partition(after)} |",
        _row("Report elapsed", before.timing.elapsed, after.timing.elapsed),
        _row(
            "Measurement critical path",
            before.timing.measurement_path,
            after.timing.measurement_path,
        ),
        f"| Longest measure job | same as the report job | {_cell(after.longest_job)} |",
        _row("Runner minutes", before.timing.runner, after.timing.runner, minutes=True),
        _row("Initial queue delay", before.timing.initial_queue, after.timing.initial_queue),
        f"| Dependent-job wait | none (one job) | {_cell(after.dependent_wait)} |",
        _row("Request latency", before.timing.request_latency, after.timing.request_latency),
        _row("Setup (workflow steps)", before.timing.setup, after.timing.setup),
        f"| Internal setup spans | unknown (not instrumented) | {_cell(after.internal_setup)} |",
        "| Modeled serial work | not applicable (observed sequentially) | "
        f"{_cell(after.modeled_serial)} |",
        f"| Runner image | {_before_image(before)} | {_after_images(after)} |",
        f"| Interpreters | {_before_interpreters(before)} | {_after_interpreters(after)} |",
        f"| Coverage | {_coverage(before.coverage)} | {_coverage(after.coverage)} |",
        f"| Observed reduction | {_reduction(result.reduction)} | |",
        ORDINARY_CI_ROW,
        "",
        "## Coverage verdict",
        "",
    ]
    lines += _coverage_lines(result)
    lines += ["", "## After coverage against its own plan", ""]
    for shard in after.shards:
        state = "complete" if shard.complete else "incomplete: " + "; ".join(shard.reasons)
        lines.append(
            f"- `{shard.id}` ({shard.subject}): {state}; head collection "
            f"{_clock(shard.head_seconds) if shard.head_seconds is not None else 'unknown'}"
        )
    lines += ["", "## Caveats", ""]
    lines += [f"- {caveat}" for caveat in result.caveats] or ["- none"]
    if before.problems or after.problems:
        lines += ["", "## Insufficient evidence", ""]
        lines += [f"- before: {problem}" for problem in before.problems]
        lines += [f"- after: {problem}" for problem in after.problems]
    return "\n".join(lines) + "\n"


def _coverage_lines(result: Evidence) -> list[str]:
    verdict = result.verdict
    lines: list[str] = []
    if verdict.equivalent and verdict.same_protocol:
        lines.append(
            "Equivalent: the same multiset of (subject, runtime, window, workload, cell, unit) "
            "addresses, the same sample count behind each, and the same workload digest and "
            "sampling protocol per subject."
        )
    else:
        lines.append(
            "**Mismatch: the two runs did not measure the same work. No unqualified reduction "
            "claim follows from these runs.**"
        )
        lines += _by_subject("missing after", [address for address in verdict.missing])
        lines += _by_subject("extra after", [address for address in verdict.extra])
        lines += _by_subject(
            "counted differently", [address for address, _, _ in verdict.recounted]
        )
        lines += _by_subject(
            "sampled differently", [address for address, _, _ in verdict.resampled]
        )
        lines += [f"- missing after: {_address(address)}" for address in verdict.missing]
        lines += [f"- extra after: {_address(address)}" for address in verdict.extra]
        lines += [
            f"- counted {before} before, {after} after: {_address(address)}"
            for address, before, after in verdict.recounted
        ]
        lines += [
            f"- sampled {list(before)} before, {list(after)} after: {_address(address)}"
            for address, before, after in verdict.resampled
        ]
        lines += [f"- protocol: {difference}" for difference in verdict.protocol_differences]
    return lines


def _before_run(before: Historical) -> str:
    spelled = (
        f"[{before.run.id}]({before.run.url}) attempt {before.run.attempt}, `{before.run.event}`"
    )
    if before.job is not None:
        spelled += f", [job {before.job.id}]({before.job.url(before.run)})"
    return spelled


def _after_run(after: Sharded) -> str:
    return f"[{after.run.id}]({after.run.url}) attempt {after.run.attempt}, `{after.run.event}`"


def _partition(after: Sharded) -> str:
    return f"{len(after.shards)} shard(s), " + ", ".join(f"`{shard.id}`" for shard in after.shards)


def _before_image(before: Historical) -> str:
    labels = ", ".join(before.job.labels) if before.job is not None else ""
    return f"unknown (labels: {labels or 'unknown'})"


def _after_images(after: Sharded) -> str:
    return "; ".join(f"`{shard.id}` {shard.runner}" for shard in after.shards) or "unknown"


def _coverage(coverage: Coverage) -> str:
    return (
        f"{coverage.total} readings over {len(coverage.readings)} addresses, "
        f"{len(coverage.subjects)} subject(s)"
    )


def _by_subject(label: str, addresses: Sequence[Address]) -> list[str]:
    counts = Counter(address[0] for address in addresses)
    return [f"- {label}, {subject}: {counts[subject]} address(es)" for subject in sorted(counts)]


def _row(label: str, before: Quantity, after: Quantity, *, minutes: bool = False) -> str:
    return f"| {label} | {_cell(before, minutes=minutes)} | {_cell(after, minutes=minutes)} |"


def _cell(quantity: Quantity, *, minutes: bool = False) -> str:
    if quantity.seconds is None:
        return f"unknown ({quantity.note})"
    spelled = f"{quantity.seconds / 60:.1f} min" if minutes else _clock(quantity.seconds)
    return f"{spelled} ({quantity.note})" if quantity.note else spelled


def _reduction(reduction: Quantity) -> str:
    if reduction.seconds is None:
        return f"withheld: {reduction.note}"
    sign = "-" if reduction.seconds >= 0 else "+"
    return f"{sign}{_clock(abs(reduction.seconds))} ({reduction.note})"


def _clock(seconds: float) -> str:
    whole = round(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{seconds:.0f} s" if seconds >= 10 else f"{seconds:.1f} s"


def _address(address: Address) -> str:
    subject, runtime, window, workload, cell, unit = address
    return f"{subject} | {runtime or '-'} | {window or '-'} | {workload} | {cell} | {unit}"


def _before_interpreters(before: Historical) -> str:
    parents = sorted({protocol.cpython for protocol in before.coverage.protocols.values()})
    minors = sorted({address[1] for address in before.coverage.readings if address[1]})
    spelled = ", ".join(parents) or "unknown"
    others = [
        minor for minor in minors if not any(parent.startswith(minor + ".") for parent in parents)
    ]
    if others:
        spelled += "; " + ", ".join(f"{minor} patch unknown" for minor in others)
    return spelled + " (parent CPython from provenance)"


def _after_interpreters(after: Sharded) -> str:
    versions = sorted({version for shard in after.shards for version in shard.runtimes.values()})
    return ", ".join(versions) or "unknown"


# --------------------------------------------------------------------------- #
# Document helpers and the entry point                                         #
# --------------------------------------------------------------------------- #
def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _object(document: object, label: str) -> Mapping[str, object]:
    if not isinstance(document, Mapping):
        raise ValueError(f"{label} is not an object")
    return cast("Mapping[str, object]", document)


def _string(fields: Mapping[str, object], key: str) -> str:
    value = fields.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} {value!r} is not a non-empty string")
    return value


def _optional_string(fields: Mapping[str, object], key: str) -> str | None:
    value = fields.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} {value!r} is not a string or null")
    return value


def _integer(fields: Mapping[str, object], key: str) -> int:
    value = fields.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} {value!r} is not an integer")
    return value


def _spelled(value: object, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int | str) or value == "":
        raise ValueError(f"{label} {value!r} is not an identifier")
    return str(value)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Put a retained sequential cost report beside a sharded assembly, offline."
    )
    parser.add_argument("--before-portfolio", type=Path, required=True, metavar="JSON")
    parser.add_argument("--after", type=Path, required=True, metavar="DIR")
    parser.add_argument("--before-run", type=Path, required=True, metavar="JSON")
    parser.add_argument("--after-run", type=Path, required=True, metavar="JSON")
    parser.add_argument("--before-jobs", type=Path, required=True, metavar="JSON")
    parser.add_argument("--after-jobs", type=Path, required=True, metavar="JSON")
    arguments = parser.parse_args(argv)
    try:
        before = historical(
            Run.load(arguments.before_run),
            load_jobs(arguments.before_jobs),
            _object(_load(arguments.before_portfolio), "before portfolio"),
        )
        after = sharded(
            Run.load(arguments.after_run), load_jobs(arguments.after_jobs), arguments.after
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f"{parser.prog}: error: {error}\n")
    print(evidence(before, after).render(), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
