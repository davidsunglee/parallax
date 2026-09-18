"""Collect every quantitative Python report into one fail-late portfolio, verify
committed evidence, and compare two portfolios cell by cell.

Verification separates what makes evidence invalid — a missing, malformed, or
incomplete required envelope, a snapshot-delivery envelope that is not
authoritative, a capture taken from a dirty tree, a workload digest that
disagrees with the inspected checkout, and members produced at different
commits — from what is merely drift or an adverse reading: a timing or memory
ceiling exceeded, a reading past the memory gate the cost class blocks on, a
scaling arm grown past its limit, a dependency lock that moved since the
capture, and a producing commit the inspected head no longer descends from are
each reported as an advisory and never fail. The write-lowering envelope's
sampling protocol is its own, so it is non-authoritative by construction and
verification accepts it so.
``--freshness-only`` reports a moved lock as the same advisory and fails only
when the portfolio establishes no freshness at all: no single snapshot-delivery
member, or provenance whose recorded lock digest is absent or malformed.

A workload digest covers what was measured — the frozen workload manifest and
the fixture and model sources defining it — and never the instruments that
measured it. A capture is taken once at its producing commit; the blocking
memory gates are the cost class's, and whether a later instrument edit leaves
two captures comparable is a judgement recorded beside the evidence.

Comparison pairs readings only when their subject, runtime, window, workload,
cell, and unit all agree, names every cell present on one side alone, and
judges a timing delta against one explicit noise allowance.

Collection records how long each member took beside what it measured: a
``durations.json`` sidecar of spans taken outside every measured window, folded
from each member's own sidecar. Durations are telemetry, so a member that
writes none, or one whose sidecar does not decode, leaves its attribution
unavailable and its envelope untouched.

A capture is also partitioned into shards, each one member or one workload
slice of the Snapshot member, so that separate runners can measure them and an
assembly can put the results beside each other without pretending they are
one capture. ``--plan`` prints the partition, ``--shard`` measures one shard
(its head, after the request's base when one is named, through the base
checkout's own tool, on the same runner), and ``--assemble`` reconciles what
arrived against the plan and the immutable request, keeping every envelope's
provenance whole and naming every cell it could not compare.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, cast

from jsonschema import ValidationError

import write_lowering_overhead as write_report
from durations import Spans, render
from interpreter_matrix import (
    RuntimeIdentity,
    RuntimeStatus,
    RuntimeUnavailable,
    authority_minor,
    load_metadata,
    runtime_status,
    supported_minors,
)
from parallax.conformance.budget import BudgetContract, MemoryGates, reading_bytes
from parallax.conformance.cost_envelope import Reading, validate
from parallax.conformance.workloads import workload_digest
from snapshot_delivery_overhead import (
    Selection,
    every_cell,
    expanded_cells,
    expected_readings,
    is_scaling_cell,
    selected_addresses,
    window_of,
    workload_selection,
)
from snapshot_delivery_overhead import (
    comparison as snapshot_comparison,
)
from snapshot_delivery_overhead import (
    operator as snapshot_operator,
)
from snapshot_delivery_overhead import (
    unit as snapshot_unit,
)

WORKSPACE: Final = Path(__file__).resolve().parents[1]
PORTFOLIO_VERSION: Final = 1
CANONICAL_PORTFOLIO: Final = Path(
    "languages/python/docs/structural-metadata-envelope/recovered/portfolio.json"
)
"""The repository's current cost portfolio and CI's verification input, relative
to the repository root. The `before/` and `after/` captures beside it are the
retained comparison bases, not verification inputs."""

EVIDENCE_DIRECTORY: Final = (WORKSPACE.parents[1] / CANONICAL_PORTFOLIO).resolve().parents[1]
"""Where the committed captures live, the current one and its comparison bases
alike. A diagnostic run is not evidence, so no path it writes may land here; a
member script's own diagnostic is printed and writes nothing anywhere."""
SNAPSHOT_SUBJECT: Final = "snapshot-delivery"
WRITE_SUBJECT: Final = write_report.SUBJECT
TIMING_NOISE_ALLOWANCE: Final = 0.05
"""The relative allowance a timing delta between two captures must exceed to be
read as anything but noise. Two identical quiet captures on the capture runner
agreed within it on 89 of 90 elapsed medians, the last at 5.3%."""

MEMORY_NOISE_ALLOWANCE: Final = 0.03
"""The same allowance for a byte reading: retained checkpoints between two
identical captures differed by up to 2.8%, high-water marks by under 1%, in
steps of a few dozen bytes. Counts carry no allowance and compare exactly."""

LOCK_FRESHNESS_UNAVAILABLE: Final = "lock freshness unavailable"
"""Prefix of the one freshness answer that is not a comparison, and the only one
``--freshness-only`` fails on."""

LOCK_DIGEST_PATTERN: Final = re.compile("[0-9a-f]{64}")
"""The envelope schema's digest shape, restated because ``--freshness-only``
answers from a portfolio it deliberately does not validate."""

TIMING_UNITS: Final = frozenset(
    {"ms", "roots/s", "us/projection", "projections/s", "us/row", "us", "us/root"}
)
COUNT_UNITS: Final = frozenset({"calls/row"})


@dataclass(frozen=True, slots=True)
class Member:
    recipe: str
    script: str
    subject: str
    required: bool = False


MEMBERS: Final = (
    Member(
        "python-report-snapshot-delivery",
        "snapshot_delivery_overhead.py",
        SNAPSHOT_SUBJECT,
        required=True,
    ),
    Member("python-report-lifecycle-overhead", "lifecycle_overhead.py", "lifecycle-overhead"),
    Member("python-report-instance-state", "instance_state_overhead.py", "instance-state"),
    Member(
        "python-report-write-lowering",
        "write_lowering_overhead.py",
        WRITE_SUBJECT,
        required=True,
    ),
)


@dataclass(frozen=True, slots=True)
class MemberResult:
    member: Member
    envelope: Mapping[str, object] | None
    failure: str | None = None


@dataclass(frozen=True, slots=True)
class Collection:
    """Every member's outcome, in ``MEMBERS`` order, beside the spans the
    collection recorded around and inside them."""

    results: tuple[MemberResult, ...]
    durations: Spans

    @property
    def failed_required(self) -> bool:
        return any(result.member.required and result.envelope is None for result in self.results)


type Runner = Callable[[Member, Sequence[str]], tuple[int, str, str]]
"""Runs one member script with the given arguments and answers its exit
status, stdout, and stderr."""
type Document = Mapping[str, object]
type ReadingAddress = tuple[str, str, str]
"""A reading's (runtime, workload, cell) address within one subject."""

COLLECTION_SPAN: Final = "python-report-cost"
DURATIONS_OPTION: Final = "--durations"
DURATIONS_FILE: Final = "durations.json"
METADATA_OPTION: Final = "--metadata"
WORKLOAD_OPTION: Final = "--workload"


def report_recipes() -> frozenset[str]:
    """The collector's member recipe names."""
    return frozenset(member.recipe for member in MEMBERS)


def run_member(member: Member, arguments: Sequence[str] = ()) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(WORKSPACE / "tools" / member.script), *arguments],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _decoded(member: Member, output: str, selected: Selection = every_cell) -> Document:
    document = cast("Document", json.loads(output))
    validate(document)
    if document.get("subject") != member.subject:
        raise ValueError(
            f"{member.recipe} emitted subject {document.get('subject')!r}, "
            f"expected {member.subject!r}"
        )
    validate_matrix(document, member.subject, BudgetContract.load(), selected)
    return document


def validate_matrix(
    document: Document,
    subject: str,
    contract: BudgetContract,
    selected: Selection = every_cell,
    runtimes: Sequence[str] | None = None,
) -> None:
    """Validate the exact reading matrix of a required subject against
    ``contract``, the addresses ``selected``, and the ``runtimes`` measured,
    every supported minor unless named; other subjects have none."""
    if subject == SNAPSHOT_SUBJECT:
        validate_snapshot_matrix(document, contract, selected, runtimes)
    if subject == WRITE_SUBJECT:
        validate_write_lowering_matrix(document, runtimes)


def _readings(document: Document) -> Sequence[Document]:
    return cast("Sequence[Document]", document.get("readings", ()))


def _indexed(documents: Iterable[Document], *, label: str) -> dict[ReadingAddress, Document]:
    indexed: dict[ReadingAddress, Document] = {}
    for document in documents:
        address = (
            str(document.get("runtime", "")),
            str(document["workload"]),
            str(document["cell"]),
        )
        if address in indexed:
            raise ValueError(f"duplicate {label} {_spelled(address)}")
        indexed[address] = document
    return indexed


def _spelled(address: ReadingAddress) -> str:
    runtime, workload, cell = address
    prefix = f"CPython {runtime} " if runtime else ""
    return f"{prefix}{workload}.{cell}"


def _inexact(expected: Iterable[ReadingAddress], actual: Iterable[ReadingAddress]) -> list[str]:
    wanted = set(expected)
    found = set(actual)
    return [
        *(f"missing {_spelled(address)}" for address in sorted(wanted - found)),
        *(f"unexpected {_spelled(address)}" for address in sorted(found - wanted)),
    ]


def _exact(
    expected: Iterable[ReadingAddress], actual: Iterable[ReadingAddress], *, label: str
) -> None:
    details = _inexact(expected, actual)
    if details:
        raise ValueError(f"{label} matrix is not exact: {', '.join(details)}")


def _samples(document: Document) -> tuple[float, ...]:
    return tuple(_number(value) for value in cast("Sequence[object]", document["samples"]))


def validate_snapshot_matrix(
    document: Document,
    contract: BudgetContract,
    selected: Selection = every_cell,
    runtimes: Sequence[str] | None = None,
) -> None:
    """Validate the exact contract-derived Snapshot report matrix on every
    supported runtime among the addresses ``selected``, with comparisons of the
    selected contract cells on the authority runtime alone."""
    minors = tuple(runtimes) if runtimes is not None else supported_minors()
    expected = selected_addresses(contract, minors, selected)
    readings = _indexed(_readings(document), label="Snapshot reading")
    _exact(expected, readings, label="Snapshot reading")
    comparisons = _indexed(
        cast("Sequence[Document]", document["comparisons"]), label="Snapshot comparison"
    )
    contract_cells = {
        (cell.workload, cell.path): cell
        for cell in expanded_cells(contract)
        if selected(cell.workload, cell.path)
    }
    _exact(
        (("", workload, path) for workload, path in contract_cells),
        comparisons,
        label="Snapshot comparison",
    )
    memory_children = contract.memory_children
    for address in expected:
        runtime, workload, path = address
        reading_document = readings[address]
        expected_unit = snapshot_unit(path)
        if reading_document["unit"] != expected_unit:
            raise ValueError(
                f"{_spelled(address)} reading unit {reading_document['unit']!r}, "
                f"expected {expected_unit!r}"
            )
        window = window_of(path, workload)
        if reading_document.get("window") != window:
            raise ValueError(f"{_spelled(address)} reading window is not {window!r}")
        samples = _samples(reading_document)
        sample_count = (
            expected_readings(contract, path)
            if expected_readings(contract, path) > 1
            else contract.timing_measured
        )
        if len(samples) != sample_count:
            raise ValueError(
                f"{_spelled(address)} has {len(samples)} samples, expected {sample_count}"
            )
        value_samples = samples[:memory_children] if is_scaling_cell(path) else samples
        expected_value = statistics.median(value_samples)
        actual_value = _number(reading_document["value"])
        if actual_value != expected_value:
            raise ValueError(
                f"{_spelled(address)} value {actual_value} disagrees with "
                f"sample median {expected_value}"
            )
        cell = contract_cells.get((workload, path))
        if cell is None or runtime != authority_minor(contract.authority):
            continue
        reading = Reading(workload, path, actual_value, expected_unit, samples)
        expected_comparison = snapshot_comparison(cell, reading, contract, complete=True)
        comparison_document = comparisons[("", workload, path)]
        fields = {
            "operator": snapshot_operator(path),
            "limit": float(cell.value),
            "unit": expected_unit,
            "outcome": expected_comparison.outcome,
        }
        for name, expected_field in fields.items():
            if comparison_document[name] != expected_field:
                raise ValueError(
                    f"{workload}.{path} comparison {name} "
                    f"{comparison_document[name]!r}, expected {expected_field!r}"
                )


def validate_write_lowering_matrix(
    document: Document, runtimes: Sequence[str] | None = None
) -> None:
    """Validate the exact runtime-by-case write matrix, its windows, and units.

    The matrix is exact under one whole counter vocabulary: the current one a
    child answers, or the legacy one the retained captures were taken under,
    across every keyed-write case on every runtime. A matrix that mixes the two
    anywhere, or carries a counter from neither, is exact under none."""
    readings = _indexed(_readings(document), label="write-lowering reading")
    minors = tuple(runtimes) if runtimes is not None else supported_minors()
    vocabularies = {
        name: write_report.expected_addresses(minors, call_names)
        for name, call_names in write_report.CALL_VOCABULARIES.items()
    }
    found = frozenset(readings)
    if found not in vocabularies.values():
        closest, expected = min(vocabularies.items(), key=lambda item: len(item[1] ^ found))
        raise ValueError(
            "write-lowering reading matrix is not exact under any one counter vocabulary; "
            f"against the {closest} vocabulary: {', '.join(_inexact(expected, found))}"
        )
    if cast("Sequence[object]", document.get("comparisons", ())):
        raise ValueError("write-lowering evidence declares no comparisons")
    for address, reading_document in readings.items():
        _runtime, case, cell = address
        window = write_report.WINDOWS[case]
        if reading_document.get("window") != window:
            raise ValueError(f"{_spelled(address)} reading window is not {window!r}")
        expected_unit = (
            "calls/row" if cell.startswith("calls.") else write_report.unit_of(window, cell)
        )
        if reading_document["unit"] != expected_unit:
            raise ValueError(
                f"{_spelled(address)} reading unit {reading_document['unit']!r}, "
                f"expected {expected_unit!r}"
            )
        samples = _samples(reading_document)
        sample_count = write_report.samples_expected(cell)
        if len(samples) != sample_count:
            raise ValueError(
                f"{_spelled(address)} has {len(samples)} samples, expected {sample_count}"
            )
        if _number(reading_document["value"]) != statistics.median(samples):
            raise ValueError(f"{_spelled(address)} value disagrees with its sample median")


def collect(runner: Runner = run_member, spans: Spans | None = None) -> Collection:
    """Attempt every member in order and fail only after required envelope
    validation. Each member runs inside its own span and is asked for a
    durations sidecar of its own, folded into ``spans`` when it arrives."""
    recorder = spans if spans is not None else Spans()
    results: list[MemberResult] = []
    with (
        tempfile.TemporaryDirectory(prefix="parallax-durations-") as scratch,
        recorder.span("collection", COLLECTION_SPAN),
    ):
        for member in MEMBERS:
            result, _runtimes = _attempt(member, (), Path(scratch), recorder, runner)
            results.append(result)
    return Collection(tuple(results), recorder)


def _attempt(
    member: Member,
    arguments: Sequence[str],
    scratch: Path,
    recorder: Spans,
    runner: Runner,
    selected: Selection = every_cell,
) -> tuple[MemberResult, dict[str, RuntimeStatus]]:
    """Run one member once inside a member span, asking it for both sidecars,
    and decode its envelope against the addresses ``selected``."""
    sidecar = scratch / f"{member.subject}.json"
    metadata = scratch / f"{member.subject}.metadata.json"
    with recorder.span("member", member.subject, member=member.subject):
        returncode, stdout, stderr = runner(
            member,
            [*arguments, DURATIONS_OPTION, str(sidecar), METADATA_OPTION, str(metadata)],
        )
    result = _result(member, returncode, stdout, stderr, selected)
    _fold(recorder, member, sidecar)
    return result, _identities(metadata)


def _result(
    member: Member, returncode: int, stdout: str, stderr: str, selected: Selection = every_cell
) -> MemberResult:
    if returncode != 0:
        return MemberResult(member, None, f"exit {returncode}: {stderr.strip() or stdout.strip()}")
    try:
        return MemberResult(member, _decoded(member, stdout, selected))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as error:
        return MemberResult(member, None, str(error))


def _identities(metadata: Path) -> dict[str, RuntimeStatus]:
    """Every supported runtime's recorded identity, or why it is unknown."""
    runtimes = supported_minors()
    if not metadata.exists():
        return dict.fromkeys(runtimes, RuntimeUnavailable("the member wrote no metadata sidecar"))
    try:
        recorded = load_metadata(metadata)
    except (KeyError, TypeError, ValueError, OSError) as error:
        return dict.fromkeys(
            runtimes, RuntimeUnavailable(f"the member's metadata sidecar does not decode: {error}")
        )
    return {
        runtime: recorded.get(
            runtime, RuntimeUnavailable("the member recorded no identity for this runtime")
        )
        for runtime in runtimes
    }


def _fold(recorder: Spans, member: Member, sidecar: Path) -> None:
    if not sidecar.exists():
        recorder.missing("member", member.subject, "the member wrote no durations sidecar")
        return
    try:
        loaded = Spans.load(sidecar)
    except (KeyError, TypeError, ValueError, OSError) as error:
        recorder.missing(
            "member", member.subject, f"the member's durations sidecar does not decode: {error}"
        )
        return
    for span in loaded.spans:
        recorder.add(replace(span, labels={"member": member.subject, **span.labels}))
    for entry in loaded.unavailable:
        recorder.missing(entry.scope, entry.name, entry.reason)


def portfolio_document(results: Sequence[MemberResult]) -> dict[str, object]:
    return {
        "schemaVersion": PORTFOLIO_VERSION,
        "members": [result.envelope for result in results if result.envelope is not None],
        "failures": [
            {
                "recipe": result.member.recipe,
                "required": result.member.required,
                "message": result.failure,
            }
            for result in results
            if result.failure is not None
        ],
    }


def _summary(document: Document, durations: Spans | None = None) -> str:
    members = cast("Sequence[Document]", document.get("members", ()))
    failures = cast("Sequence[Document]", document.get("failures", ()))
    lines = [
        "# Python cost report",
        "",
        "| Subject | Authority | Runtimes | Readings | Within | Outside | Unavailable |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for member in members:
        comparisons = cast("Sequence[Document]", member.get("comparisons", ()))
        outcomes = [comparison.get("outcome") for comparison in comparisons]
        runtimes = sorted(
            {str(reading.get("runtime")) for reading in _readings(member) if "runtime" in reading}
        )
        lines.append(
            f"| {member.get('subject')} | {member.get('authority')} | "
            f"{', '.join(runtimes) or '-'} | "
            f"{len(_readings(member))} | "
            f"{outcomes.count('within')} | {outcomes.count('outside')} | "
            f"{outcomes.count('unavailable')} |"
        )
    if failures:
        lines += ["", "## Collection failures", ""]
        lines += [
            f"- `{failure.get('recipe')}` "
            f"({'required' if failure.get('required') else 'optional'}): "
            f"{failure.get('message')}"
            for failure in failures
        ]
    lines += [
        "",
        "Budget outcomes are advisory. This collector fails only for a missing "
        "or invalid required envelope.",
    ]
    if durations is not None:
        lines += ["", render(durations).rstrip("\n")]
    return "\n".join(lines) + "\n"


def write_portfolio(collection: Collection, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    document = portfolio_document(collection.results)
    (out / "portfolio.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "summary.md").write_text(_summary(document, collection.durations), encoding="utf-8")
    collection.durations.write(out / DURATIONS_FILE)
    for result in collection.results:
        if result.envelope is not None:
            (out / f"{result.member.subject}.json").write_text(
                json.dumps(result.envelope, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )


def _members(document: Document, subject: str) -> tuple[Document, ...]:
    members = cast("Sequence[Document]", document.get("members", ()))
    return tuple(member for member in members if member.get("subject") == subject)


def _snapshot(document: Document) -> Document | None:
    snapshots = _members(document, SNAPSHOT_SUBJECT)
    return snapshots[0] if len(snapshots) == 1 else None


def _provenance(member: Document) -> Document | None:
    provenance = member.get("provenance")
    return cast("Document", provenance) if isinstance(provenance, Mapping) else None


def lock_freshness(document: Document, lock_path: Path | None = None) -> tuple[bool, str]:
    """Compare retained dependencies with a lock file without reclassifying
    authority. Provenance carrying no well-formed lock digest answers
    ``LOCK_FRESHNESS_UNAVAILABLE`` rather than drift, because no comparison was
    made."""
    snapshot = _snapshot(document)
    if snapshot is None:
        return False, f"{LOCK_FRESHNESS_UNAVAILABLE}: expected one snapshot-delivery envelope"
    provenance = _provenance(snapshot)
    if provenance is None:
        return False, f"{LOCK_FRESHNESS_UNAVAILABLE}: snapshot-delivery provenance is not a mapping"
    recorded = provenance.get("lockDigest")
    if not isinstance(recorded, str) or LOCK_DIGEST_PATTERN.fullmatch(recorded) is None:
        return False, (
            f"{LOCK_FRESHNESS_UNAVAILABLE}: snapshot-delivery provenance records "
            f"lockDigest={recorded!r}"
        )
    inspected = lock_path or WORKSPACE / "uv.lock"
    current = hashlib.sha256(inspected.read_bytes()).hexdigest()
    digests = f"recorded lockDigest={recorded}; inspected lockDigest={current} ({inspected})"
    if recorded != current:
        return False, f"stale snapshot-delivery evidence: {digests}"
    return True, f"snapshot-delivery lock freshness matches: {digests}"


def is_published(commit: str) -> bool:
    """Whether ``commit`` is an ancestor of the inspected checkout's head, so
    every checkout of that head can resolve it."""
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=WORKSPACE,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _required_member(document: Document, subject: str) -> tuple[Document | None, list[str]]:
    members = _members(document, subject)
    if not members:
        return None, [f"the portfolio has no required {subject} envelope"]
    if len(members) != 1:
        return None, [f"the portfolio has more than one {subject} envelope"]
    return members[0], []


def _provenance_failures(member: Document, subject: str, expected_digest: str) -> list[str]:
    failures: list[str] = []
    provenance = _provenance(member)
    if provenance is None:
        return [f"the {subject} envelope has no provenance"]
    if provenance.get("dirty") is not False:
        failures.append(f"the {subject} envelope was not produced from a clean tree")
    if provenance.get("workloadDigest") != expected_digest:
        failures.append(f"the {subject} envelope's workload digest is stale")
    return failures


def _unpublished(member: Document, subject: str) -> list[str]:
    provenance = _provenance(member)
    if provenance is None:
        return []
    commit = str(provenance.get("commit", ""))
    if is_published(commit):
        return []
    return [
        f"advisory: the {subject} envelope's producing commit {commit[:12]} is not an "
        "ancestor of the inspected head"
    ]


def _scaling_growth(snapshot: Document, contract: BudgetContract) -> list[str]:
    memory = cast("Mapping[str, object]", contract.sampling["memory"])
    arm_limit = _number(memory["armGrowthMaxKiB"])
    arm_size = contract.memory_children
    arm_count = len(contract.memory_scaling_arms)
    compared = authority_minor(contract.authority)
    grown: list[str] = []
    for reading in _readings(snapshot):
        cell = str(reading.get("cell"))
        if not cell.startswith("streamedMemory.") or reading.get("runtime") != compared:
            continue
        samples = [_number(value) for value in cast("Sequence[object]", reading.get("samples", ()))]
        if len(samples) < arm_size * arm_count:
            continue
        arm_medians = [
            statistics.median(samples[index * arm_size : (index + 1) * arm_size])
            for index in range(arm_count)
        ]
        growth = max(arm_medians[1:]) - arm_medians[0]
        if growth > arm_limit:
            grown.append(
                f"advisory: {reading.get('workload')}.{cell} grows {growth:.3f} KiB between "
                "memory arms"
            )
    return grown


def is_diagnostic(document: Document) -> bool:
    """Whether ``document`` is a diagnostic reading set, or carries one as a member."""
    members = cast("Sequence[object]", document.get("members", ()))
    return bool(document.get("diagnostic")) or any(
        isinstance(member, Mapping) and bool(cast("Document", member).get("diagnostic"))
        for member in members
    )


def verify(document: Document, contract: BudgetContract | None = None) -> list[str]:
    """Every reason the required portfolio is not valid evidence: a missing,
    malformed, or incomplete required envelope, a snapshot-delivery envelope
    that is not authoritative, a capture taken from a dirty tree, a workload
    digest disagreeing with the inspected checkout, or members produced at
    different commits.

    The write-lowering envelope's authority is not among these: its sampling
    protocol is its own, so it is non-authoritative by construction. Neither is
    a ceiling exceeded, a memory gate passed, an arm grown, a moved lock, or an
    unpublished producing commit: see :func:`advisories`.
    """
    if is_diagnostic(document):
        return ["a diagnostic reading set is not evidence and cannot be verified"]
    active = contract or BudgetContract.load()
    snapshot, failures = _required_member(document, SNAPSHOT_SUBJECT)
    if snapshot is None:
        return failures
    try:
        validate(snapshot)
        validate_snapshot_matrix(snapshot, active)
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        return [*failures, f"the snapshot-delivery envelope is invalid: {error}"]
    if snapshot.get("authority") != "authoritative":
        failures.append("the snapshot-delivery envelope is not authoritative")
    if snapshot.get("incomplete"):
        failures.append("the snapshot-delivery envelope is incomplete")
    if snapshot.get("errors"):
        failures.append("the snapshot-delivery envelope contains errors")
    failures += _provenance_failures(snapshot, SNAPSHOT_SUBJECT, workload_digest())
    write, write_failures = _required_member(document, WRITE_SUBJECT)
    failures += write_failures
    if write is None:
        return failures
    try:
        validate(write)
        validate_write_lowering_matrix(write)
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        return [*failures, f"the write-lowering envelope is invalid: {error}"]
    if write.get("incomplete") or write.get("errors"):
        failures.append("the write-lowering envelope is incomplete")
    failures += _provenance_failures(
        write, WRITE_SUBJECT, write_report.lowering_support.write_lowering_digest()
    )
    commits = {
        str(cast("Document", member["provenance"])["commit"]) for member in (snapshot, write)
    }
    if len(commits) != 1:
        failures.append("the snapshot-delivery and write-lowering envelopes name different commits")
    return failures


def _gate_advisories(document: Document, gates: MemoryGates) -> list[str]:
    """Every reading of a required member past the memory gate at its address,
    on whichever runtime read it. The gate blocks in the cost class, where the
    same window is read again in an interpreter of its own; here it is stated."""
    indexed = {(gate.subject, gate.workload, gate.cell): gate for gate in gates.gates}
    reported: list[str] = []
    for subject in (SNAPSHOT_SUBJECT, WRITE_SUBJECT):
        members = _members(document, subject)
        if len(members) != 1:
            continue
        for reading in _readings(members[0]):
            address = (subject, str(reading["workload"]), str(reading["cell"]))
            gate = indexed.get(address)
            if gate is None:
                continue
            unit = str(reading.get("unit"))
            spelled = _spelled((str(reading.get("runtime", "")), address[1], address[2]))
            if unit != gate.unit:
                reported.append(
                    f"advisory: {subject} {spelled} is read in {unit} and gated in {gate.unit}"
                )
                continue
            value = _number(reading["value"])
            if not gate.within(value):
                reported.append(
                    f"advisory: {subject} {spelled} is outside its memory gate "
                    f"({reading_bytes(value, unit):.0f} B over {gate.max_bytes} B; "
                    "the cost class gates it)"
                )
    return reported


def advisories(
    document: Document,
    contract: BudgetContract | None = None,
    gates: MemoryGates | None = None,
) -> list[str]:
    """Everything reported about the required evidence that never fails it: a
    timing or memory ceiling exceeded, a reading past its memory gate, a
    scaling arm grown past its limit, a dependency lock that moved since the
    capture, and a producing commit the inspected head no longer descends from.
    A lock comparison that could not be made at all is reported here the same
    way: the provenance it needs is required of the envelope, so :func:`verify`
    refuses one lacking it.

    None of these makes a capture wrong. A ceiling is the cost class's to gate,
    and a memory gate blocks there and only there; a lock bump or a rebase
    changes nothing a reading measured; and a capture is taken once, so drift is
    stated beside the evidence rather than used to demand another hour of the
    runner.
    """
    if is_diagnostic(document):
        return []
    snapshot = _snapshot(document)
    if snapshot is None:
        return []
    active = contract or BudgetContract.load()
    reported: list[str] = []
    fresh, freshness = lock_freshness(document)
    if not fresh:
        reported.append(f"advisory: {freshness}")
    reported += _unpublished(snapshot, SNAPSHOT_SUBJECT)
    for comparison in cast("Sequence[Document]", snapshot.get("comparisons", ())):
        if comparison.get("outcome") == "within":
            continue
        kind = "timing" if comparison.get("unit") in TIMING_UNITS else "memory"
        reported.append(
            f"advisory: {comparison.get('workload')}.{comparison.get('cell')} is "
            f"{comparison.get('outcome')} its {kind} ceiling"
        )
    with contextlib.suppress(KeyError, TypeError, ValueError):
        reported += _scaling_growth(snapshot, active)
    write = _members(document, WRITE_SUBJECT)
    if len(write) == 1:
        reported += _unpublished(write[0], WRITE_SUBJECT)
    with contextlib.suppress(KeyError, TypeError, ValueError):
        reported += _gate_advisories(document, gates or MemoryGates.load())
    return reported


type PairAddress = tuple[str, str, str, str]
"""A comparable reading's (runtime, window, workload, cell) address within one subject."""


def _pairs(member: Document) -> dict[PairAddress, Document]:
    return {
        (
            str(reading.get("runtime", "")),
            str(reading.get("window", "")),
            str(reading["workload"]),
            str(reading["cell"]),
        ): reading
        for reading in _readings(member)
    }


def _verdict(unit: str, base: float, head: float) -> str:
    if unit in COUNT_UNITS:
        return "exact" if base == head else "changed"
    if base == 0:
        return "incomparable"
    change = (head - base) / base
    if unit in TIMING_UNITS:
        if abs(change) <= TIMING_NOISE_ALLOWANCE:
            return "within noise"
        faster = change < 0 if unit.startswith(("ms", "us")) else change > 0
        return "faster" if faster else "slower"
    if abs(change) <= MEMORY_NOISE_ALLOWANCE:
        return "within noise"
    return "smaller" if change < 0 else "larger"


def _spelled_pair(address: PairAddress) -> str:
    runtime, window, workload, cell = address
    return f"{runtime or '-'} | {window or '-'} | {workload} | {cell}"


def compare(base: Document, head: Document) -> str:
    """Render advisory deltas between two portfolios, pairing readings only on
    identical subject, runtime, window, workload, cell, and unit."""
    lines = [
        "# Python cost report comparison",
        "",
        f"Timing deltas within {TIMING_NOISE_ALLOWANCE:.0%} and byte deltas within "
        f"{MEMORY_NOISE_ALLOWANCE:.0%} are read as noise; count deltas are exact. A cell "
        "present on one side alone, or whose unit differs, is not compared.",
    ]
    subjects = sorted(
        {
            str(member.get("subject"))
            for document in (base, head)
            for member in cast("Sequence[Document]", document.get("members", ()))
        }
    )
    for subject in subjects:
        base_members = _members(base, subject)
        head_members = _members(head, subject)
        lines += ["", f"## {subject}", ""]
        if len(base_members) != 1 or len(head_members) != 1:
            lines.append(f"The {subject} envelope is unavailable on one side.")
            continue
        lines += _comparison_rows(base_members[0], head_members[0])
    lines += ["", "Deltas are advisory and never ratchet the Budget Contract."]
    return "\n".join(lines) + "\n"


COMPARISON_HEADER: Final[tuple[str, str]] = (
    "| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |",
    "|---|---|---|---|---:|---:|---:|---:|---|",
)


def _comparison_rows(base_member: Document, head_member: Document) -> list[str]:
    base_pairs = _pairs(base_member)
    head_pairs = _pairs(head_member)
    lines: list[str] = list(COMPARISON_HEADER)
    for address in sorted(base_pairs.keys() | head_pairs.keys()):
        previous = base_pairs.get(address)
        current = head_pairs.get(address)
        if previous is None or current is None:
            side = "base" if previous is None else "head"
            lines.append(f"| {_spelled_pair(address)} | | | | | missing on {side} |")
            continue
        unit = str(current.get("unit"))
        if unit != previous.get("unit"):
            lines.append(
                f"| {_spelled_pair(address)} | | | | | incomparable: "
                f"{previous.get('unit')} against {unit} |"
            )
            continue
        base_value = _number(previous["value"])
        head_value = _number(current["value"])
        delta = head_value - base_value
        percent = f" ({delta / base_value:+.2%})" if base_value else ""
        samples = min(
            len(cast("Sequence[object]", previous.get("samples", ()))),
            len(cast("Sequence[object]", current.get("samples", ()))),
        )
        lines.append(
            f"| {_spelled_pair(address)} | {base_value:.3f} | {head_value:.3f} | "
            f"{delta:+.3f} {unit}{percent} | {samples} | "
            f"{_verdict(unit, base_value, head_value)} |"
        )
    return lines


def _load(path: Path) -> Document:
    return cast("Document", json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- #
# Shards: the partition plan, and one shard's collection                       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Shard:
    """One unit of the partition: a whole member, or the Snapshot member over
    the named workloads alone."""

    id: str
    member: Member
    workloads: frozenset[str] | None = None

    @property
    def subject(self) -> str:
        return self.member.subject

    def selection(self, contract: BudgetContract) -> Selection:
        if self.workloads is None:
            return every_cell
        return workload_selection(sorted(self.workloads), contract)

    def document(self) -> dict[str, object]:
        return {
            "id": self.id,
            "subject": self.subject,
            "workloads": sorted(self.workloads) if self.workloads is not None else None,
        }


SNAPSHOT_MEMBER: Final = next(member for member in MEMBERS if member.subject == SNAPSHOT_SUBJECT)


def _snapshot_shard(name: str, *workloads: str) -> Shard:
    return Shard(f"snapshot-{name}", SNAPSHOT_MEMBER, frozenset(workloads))


SHARDS: Final[tuple[Shard, ...]] = (
    _snapshot_shard("duplicate-include", "duplicate-include"),
    _snapshot_shard("document-heavy", "document-heavy"),
    _snapshot_shard("conventional-fanout", "conventional-fanout"),
    _snapshot_shard("bitemporal-current", "bitemporal-current"),
    _snapshot_shard("versioned-document", "versioned-document"),
    _snapshot_shard(
        "geometry-plan-stress", "geometry", "plan", "stress-columns", "stress-document"
    ),
    *(Shard(member.subject, member) for member in MEMBERS if member is not SNAPSHOT_MEMBER),
)
"""The partition plan, heaviest shard first so the matrix's longest job starts
first. The Snapshot member dominates a whole-member capture (about 2.5 hours
against 5 minutes for the next member on a hosted runner), so it is split by
workload from its measured attribution: each of its five heavy workloads (23 to
27 minutes summed over both supported minors) is a shard of its own, and the
four small ones (geometry 16 minutes, the rest about a minute each) share one,
since another runner would cost more setup than it saves. Every other member
is one whole shard. A split is a change to this data with its test rather than
a new recipe, and a shard whose coverage changes takes a new id, so an old base
or nightly capture of the same id can never be paired with different work."""

ALL_SHARDS: Final = "all"
SHARD_ID_PATTERN: Final = re.compile("[a-z0-9][a-z0-9-]*")
LAYOUTS: Final = ("sharded", "sequential")
CAPTURE_FILE: Final = "capture.json"
REQUEST_FILE: Final = "request.json"
UNAVAILABLE_FILE: Final = "unavailable.json"
SELF_CAPTURE_FILE: Final = "self-capture.json"
HISTORY_FILE: Final = "history.json"
"""What the workflow adapter writes beside a previous nightly it could or
could not obtain: the run it selected and, when no assembly arrived, why."""
CAPTURE_VERSION: Final = 1
HISTORY_VERSION: Final = 1
MARKER_VERSION: Final = 1
REQUEST_VERSION: Final = 1
ASSEMBLY_VERSION: Final = 2
HEAD: Final = "head"
BASE: Final = "base"
SIDES: Final = (HEAD, BASE)


def validate_plan(
    plan: Sequence[Shard],
    contract: BudgetContract | None = None,
    runtimes: Sequence[str] | None = None,
) -> None:
    """``ValueError`` unless ``plan`` names each shard uniquely and safely,
    covers every other member exactly once as a whole, and covers every
    Snapshot address on every supported runtime exactly once."""
    seen: set[str] = set()
    for shard in plan:
        if SHARD_ID_PATTERN.fullmatch(shard.id) is None or shard.id == ALL_SHARDS:
            raise ValueError(f"shard id {shard.id!r} is reserved or unsafe")
        if shard.id in seen:
            raise ValueError(f"shard id {shard.id!r} is not unique")
        seen.add(shard.id)
        if shard.member not in MEMBERS:
            raise ValueError(f"shard {shard.id!r} names a member the collector does not run")
        if shard.workloads is not None and shard.subject != SNAPSHOT_SUBJECT:
            raise ValueError(f"shard {shard.id!r} splits {shard.subject}, which has no workloads")
        if shard.workloads is not None and not shard.workloads:
            raise ValueError(f"shard {shard.id!r} selects no workload")
    active = contract if contract is not None else BudgetContract.load()
    minors = tuple(runtimes) if runtimes is not None else supported_minors()
    for member in MEMBERS:
        shards = [shard for shard in plan if shard.member == member]
        if member.subject != SNAPSHOT_SUBJECT or all(s.workloads is None for s in shards):
            if len(shards) != 1:
                raise ValueError(f"{member.subject} must be one whole shard, found {len(shards)}")
            continue
        if any(shard.workloads is None for shard in shards):
            raise ValueError(f"{member.subject} mixes a whole-member shard with workload shards")
        covered: dict[tuple[str, str, str], str] = {}
        for shard in shards:
            for address in selected_addresses(active, minors, shard.selection(active)):
                if address in covered:
                    raise ValueError(
                        f"{_spelled(address)} is covered by both {covered[address]!r} "
                        f"and {shard.id!r}"
                    )
                covered[address] = shard.id
        missing = [
            address
            for address in selected_addresses(active, minors, every_cell)
            if address not in covered
        ]
        if missing:
            raise ValueError(f"no shard covers {_spelled(missing[0])}")


def plan_ids(layout: str, plan: Sequence[Shard] | None = None) -> list[str]:
    """What a matrix runs for ``layout``: every shard id, or ``all`` alone."""
    if layout not in LAYOUTS:
        raise ValueError(f"layout {layout!r} is not one of {list(LAYOUTS)}")
    shards = plan if plan is not None else SHARDS
    return [ALL_SHARDS] if layout == "sequential" else [shard.id for shard in shards]


def shard_arguments(shard: Shard) -> list[str]:
    """The member options that narrow it to ``shard``'s workloads."""
    arguments: list[str] = []
    if shard.workloads is not None:
        for workload in sorted(shard.workloads):
            arguments += [WORKLOAD_OPTION, workload]
    return arguments


@dataclass(frozen=True, slots=True)
class ShardResult:
    """One shard's member outcome, its spans, and the runtime identities its
    member recorded."""

    shard: Shard
    result: MemberResult
    durations: Spans
    runtimes: Mapping[str, RuntimeStatus]

    @property
    def failed_required(self) -> bool:
        return self.shard.member.required and self.result.envelope is None


def collect_shard(
    shard: Shard, runner: Runner = run_member, spans: Spans | None = None
) -> ShardResult:
    """Run ``shard``'s member once over the shard's addresses alone, through
    the same primitive :func:`collect` runs whole members with."""
    recorder = spans if spans is not None else Spans()
    selected = shard.selection(BudgetContract.load())
    with (
        tempfile.TemporaryDirectory(prefix="parallax-durations-") as scratch,
        recorder.span("collection", shard.id, shard=shard.id),
    ):
        result, runtimes = _attempt(
            shard.member, shard_arguments(shard), Path(scratch), recorder, runner, selected
        )
    return ShardResult(shard, result, recorder, runtimes)


# --------------------------------------------------------------------------- #
# Request and capture: what was asked for, and what one runner produced         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Request:
    """The immutable request one report answers: which commits, which layout,
    and which workflow run asked. Every capture embeds it whole, so assembly
    expects what was requested rather than what happened to arrive."""

    request_id: str
    event: str
    requested_ref: str
    head_commit: str
    base_commit: str | None
    event_base_commit: str | None
    pull_request: int | None
    layout: str
    workflow_commit: str
    run_id: str | None
    run_attempt: int | None

    @property
    def is_pull_request(self) -> bool:
        return self.event == "pull_request" or self.pull_request is not None

    @property
    def run(self) -> tuple[str, str | None, int | None]:
        return (self.request_id, self.run_id, self.run_attempt)

    def document(self) -> dict[str, object]:
        return {
            "schemaVersion": REQUEST_VERSION,
            "requestId": self.request_id,
            "event": self.event,
            "requestedRef": self.requested_ref,
            "headCommit": self.head_commit,
            "baseCommit": self.base_commit,
            "eventBaseCommit": self.event_base_commit,
            "pullRequest": self.pull_request,
            "layout": self.layout,
            "workflowCommit": self.workflow_commit,
            "runId": self.run_id,
            "runAttempt": self.run_attempt,
        }

    @classmethod
    def from_document(cls, document: object) -> Request:
        fields = _object(document, "request")
        if fields.get("schemaVersion") != REQUEST_VERSION:
            raise ValueError(
                f"request schemaVersion {fields.get('schemaVersion')!r} is unsupported"
            )
        layout = _text(fields, "layout")
        if layout not in LAYOUTS:
            raise ValueError(f"request layout {layout!r} is not one of {list(LAYOUTS)}")
        return cls(
            _text(fields, "requestId"),
            _text(fields, "event"),
            _text(fields, "requestedRef"),
            _commit(_text(fields, "headCommit"), "headCommit"),
            _optional_commit(fields, "baseCommit"),
            _optional_commit(fields, "eventBaseCommit"),
            _optional_integer(fields, "pullRequest"),
            layout,
            _commit(_text(fields, "workflowCommit"), "workflowCommit"),
            _optional_text(fields, "runId"),
            _optional_integer(fields, "runAttempt"),
        )

    @classmethod
    def load(cls, path: Path) -> Request:
        return cls.from_document(_load(path))

    def write(self, path: Path) -> None:
        _write_json(path, self.document())


COMMIT_PATTERN: Final = re.compile("[0-9a-f]{40}")


def _object(document: object, label: str) -> Mapping[str, object]:
    if not isinstance(document, Mapping):
        raise ValueError(f"{label} is not an object")
    return cast("Mapping[str, object]", document)


def _text(fields: Mapping[str, object], key: str) -> str:
    value = fields.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} {value!r} is not a non-empty string")
    return value


def _optional_text(fields: Mapping[str, object], key: str) -> str | None:
    value = fields.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise ValueError(f"{key} {value!r} is neither a string, an integer, nor null")
    return str(value)


def _optional_integer(fields: Mapping[str, object], key: str) -> int | None:
    value = fields.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} {value!r} is neither an integer nor null")
    return value


def _commit(value: str, key: str) -> str:
    if COMMIT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{key} {value!r} is not a full commit hash")
    return value


def _optional_commit(fields: Mapping[str, object], key: str) -> str | None:
    value = fields.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} {value!r} is neither a commit nor null")
    return _commit(value, key)


def git_head(repo: Path | None = None) -> str:
    """The commit the inspected checkout is at."""
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo or WORKSPACE,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def local_request(layout: str, base_commit: str | None = None) -> Request:
    """A fresh request for the current checkout: the head is this commit, the
    workflow is this commit, and nothing ran on a hosted runner."""
    head = git_head()
    return Request(
        f"local-{uuid.uuid4().hex}",
        "local",
        head,
        head,
        base_commit,
        None,
        None,
        layout,
        head,
        None,
        None,
    )


RUNNER_IMAGE_VARIABLE: Final = "ImageOS"
RUNNER_IMAGE_VERSION_VARIABLE: Final = "ImageVersion"
"""What a GitHub-hosted runner names its image and image version with."""


def runner_identity() -> dict[str, str] | None:
    """The hosted runner image, when the environment names one."""
    image = os.environ.get(RUNNER_IMAGE_VARIABLE)
    version = os.environ.get(RUNNER_IMAGE_VERSION_VARIABLE)
    if image and version:
        return {"image": image, "imageVersion": version}
    return None


@dataclass(frozen=True, slots=True)
class Capture:
    """What one runner produced for one side of one shard, beside the request
    it answered and the pair its invocation belongs to."""

    request: Request
    shard_id: str
    subject: str
    workloads: tuple[str, ...] | None
    side: str
    commit: str
    pair_id: str
    runtimes: Mapping[str, RuntimeStatus]
    runner: Mapping[str, str] | None

    def document(self) -> dict[str, object]:
        return {
            "schemaVersion": CAPTURE_VERSION,
            "request": self.request.document(),
            "shard": {
                "id": self.shard_id,
                "subject": self.subject,
                "workloads": list(self.workloads) if self.workloads is not None else None,
            },
            "side": self.side,
            "commit": self.commit,
            "pairId": self.pair_id,
            "runtimes": {
                runtime: self.runtimes[runtime].document() for runtime in sorted(self.runtimes)
            },
            "runner": dict(self.runner) if self.runner is not None else None,
        }

    @classmethod
    def from_document(cls, document: object) -> Capture:
        fields = _object(document, "capture")
        if fields.get("schemaVersion") != CAPTURE_VERSION:
            raise ValueError(
                f"capture schemaVersion {fields.get('schemaVersion')!r} is unsupported"
            )
        shard = _object(fields.get("shard"), "capture shard")
        workloads = shard.get("workloads")
        if workloads is not None and (
            not isinstance(workloads, Sequence)
            or isinstance(workloads, str)
            or not all(isinstance(name, str) for name in cast("Sequence[object]", workloads))
        ):
            raise ValueError(f"capture shard workloads {workloads!r} are not names or null")
        if workloads is not None:
            names = cast("Sequence[str]", workloads)
            if not names or len(set(names)) != len(names):
                raise ValueError(
                    f"capture shard workloads {workloads!r} are not distinct names or null"
                )
        side = _text(fields, "side")
        if side not in SIDES:
            raise ValueError(f"capture side {side!r} is not one of {list(SIDES)}")
        runtimes = _object(fields.get("runtimes"), "capture runtimes")
        runner = fields.get("runner")
        if runner is not None:
            runner_fields = _object(runner, "capture runner")
            if set(runner_fields) != {"image", "imageVersion"} or not all(
                isinstance(value, str) for value in runner_fields.values()
            ):
                raise ValueError(f"capture runner {runner!r} is not an image and version")
        return cls(
            Request.from_document(fields.get("request")),
            _text(shard, "id"),
            _text(shard, "subject"),
            tuple(cast("Sequence[str]", workloads)) if workloads is not None else None,
            side,
            _commit(_text(fields, "commit"), "capture commit"),
            _text(fields, "pairId"),
            {str(runtime): runtime_status(status) for runtime, status in runtimes.items()},
            cast("Mapping[str, str]", runner) if runner is not None else None,
        )

    def write(self, path: Path) -> None:
        _write_json(path, self.document())


def _write_json(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_shard(
    result: ShardResult, request: Request, side: str, commit: str, pair_id: str, out: Path
) -> None:
    """One shard directory: the legacy-shape one-member portfolio, its
    envelope, summary, and durations, and the capture beside them."""
    write_portfolio(Collection((result.result,), result.durations), out)
    Capture(
        request,
        result.shard.id,
        result.shard.subject,
        tuple(sorted(result.shard.workloads)) if result.shard.workloads is not None else None,
        side,
        commit,
        pair_id,
        result.runtimes,
        runner_identity(),
    ).write(out / CAPTURE_FILE)


# --------------------------------------------------------------------------- #
# Base self-measurement: the base checkout's own tool, on this runner           #
# --------------------------------------------------------------------------- #
type BaseRunner = Callable[[Path, Sequence[str]], tuple[int, str, str]]
"""Runs the collector of the checkout whose Python workspace is the given
path, with the given arguments, and answers its exit status, stdout, and
stderr."""

BASE_ENVIRONMENT_EXCLUDED: Final = frozenset(
    {
        "VIRTUAL_ENV",
        "UV_PROJECT_ENVIRONMENT",
        "PYTHONPATH",
        "PYTHONHOME",
        "COV_CORE_SOURCE",
        "COV_CORE_CONFIG",
        "COV_CORE_DATAFILE",
        "COVERAGE_PROCESS_START",
    }
)


def run_base(workspace: Path, arguments: Sequence[str]) -> tuple[int, str, str]:
    """The base checkout's collector through its own frozen environment,
    never this checkout's."""
    environment = {
        name: value for name, value in os.environ.items() if name not in BASE_ENVIRONMENT_EXCLUDED
    }
    try:
        completed = subprocess.run(
            ["uv", "run", "--frozen", "python", "tools/cost_report.py", *arguments],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return 127, "", str(error)
    return completed.returncode, completed.stdout, completed.stderr


@dataclass(frozen=True, slots=True)
class Unavailability:
    code: str
    message: str

    def document(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message}

    @classmethod
    def from_document(cls, document: object) -> Unavailability:
        fields = _object(document, "reason")
        return cls(_text(fields, "code"), _text(fields, "message"))


@dataclass(frozen=True, slots=True)
class BaseResult:
    shard_id: str
    commit: str
    reason: Unavailability | None
    capture: Capture | None = None

    @property
    def measured(self) -> bool:
        return self.reason is None


type WorktreeFactory = Callable[[str], contextlib.AbstractContextManager[Path]]


@contextlib.contextmanager
def base_worktree(commit: str, repo: Path | None = None) -> Generator[Path]:
    """A detached worktree of ``commit`` under a temporary directory, removed
    on the way out whatever happened inside."""
    root = repo if repo is not None else WORKSPACE.parents[1]
    scratch = Path(tempfile.mkdtemp(prefix="parallax-base-"))
    worktree = scratch / "checkout"
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), commit],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        yield worktree
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            cwd=root,
            capture_output=True,
            check=False,
        )
        shutil.rmtree(scratch, ignore_errors=True)


def _base_plan(runner: BaseRunner, workspace: Path) -> list[str] | Unavailability:
    returncode, stdout, stderr = runner(workspace, ["--plan", "--layout", "sharded"])
    if returncode != 0:
        return Unavailability(
            "base-plan-failed",
            f"the base's plan exited {returncode}: {stderr.strip() or stdout.strip()}",
        )
    try:
        plan = json.loads(stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as error:
        return Unavailability("base-plan-failed", f"the base's plan is not JSON: {error}")
    if not isinstance(plan, list) or not all(
        isinstance(entry, str) for entry in cast("list[object]", plan)
    ):
        return Unavailability("base-plan-failed", f"the base's plan is not a list of ids: {plan!r}")
    return cast("list[str]", plan)


def measure_base(
    commit: str,
    shard_id: str,
    out: Path,
    request: Request,
    pair_id: str,
    runner: BaseRunner = run_base,
    worktree: WorktreeFactory | None = None,
) -> BaseResult:
    """Measure ``shard_id`` at ``commit`` with that commit's own tool and
    import the result as ``out/<shard_id>``, wrapped with ``request``, the
    base side, and ``pair_id``; or record why the base is unavailable."""
    destination = out / shard_id
    checkout_of = worktree if worktree is not None else base_worktree
    try:
        with checkout_of(commit) as checkout:
            result = _measure_base_in(
                checkout, commit, shard_id, destination, request, pair_id, runner
            )
    except subprocess.CalledProcessError as error:
        result = BaseResult(
            shard_id,
            commit,
            Unavailability(
                "base-checkout-failed",
                f"git could not check out {commit}: {error.stderr.strip() or error}",
            ),
        )
    if result.reason is not None:
        _write_json(
            destination / UNAVAILABLE_FILE,
            {
                "schemaVersion": MARKER_VERSION,
                "shard": shard_id,
                "side": BASE,
                "baseCommit": commit,
                "reason": result.reason.document(),
            },
        )
    return result


def _measure_base_in(
    checkout: Path,
    commit: str,
    shard_id: str,
    destination: Path,
    request: Request,
    pair_id: str,
    runner: BaseRunner,
) -> BaseResult:
    workspace = checkout / "languages" / "python"
    plan = _base_plan(runner, workspace)
    if isinstance(plan, Unavailability):
        return BaseResult(shard_id, commit, plan)
    if shard_id not in plan:
        return BaseResult(
            shard_id,
            commit,
            Unavailability(
                "missing-base-support", f"the base's plan {plan} has no shard {shard_id!r}"
            ),
        )
    with tempfile.TemporaryDirectory(prefix="parallax-base-staging-") as staging:
        staged = Path(staging).resolve()
        returncode, stdout, stderr = runner(workspace, ["--shard", shard_id, "--out", str(staged)])
        produced = staged / HEAD / shard_id
        if not (produced / CAPTURE_FILE).exists():
            return BaseResult(
                shard_id,
                commit,
                Unavailability(
                    "base-collection-failed",
                    f"the base's collection exited {returncode} and wrote no capture: "
                    f"{stderr.strip() or stdout.strip()}",
                ),
            )
        try:
            measured = Capture.from_document(_load(produced / CAPTURE_FILE))
        except (KeyError, TypeError, ValueError) as error:
            return BaseResult(
                shard_id,
                commit,
                Unavailability(
                    "base-output-malformed", f"the base's capture does not decode: {error}"
                ),
            )
        if measured.commit != commit:
            return BaseResult(
                shard_id,
                commit,
                Unavailability(
                    "base-commit-mismatch",
                    f"the base measured {measured.commit}, not the requested {commit}",
                ),
            )
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(produced, destination)
    (destination / CAPTURE_FILE).rename(destination / SELF_CAPTURE_FILE)
    wrapped = replace(measured, request=request, side=BASE, pair_id=pair_id)
    wrapped.write(destination / CAPTURE_FILE)
    return BaseResult(shard_id, commit, None, wrapped)


def run_shards(
    ids: Sequence[str],
    request: Request,
    out: Path,
    runner: Runner = run_member,
    base_runner: BaseRunner = run_base,
    plan: Sequence[Shard] | None = None,
) -> int:
    """Measure each requested shard in plan order on this runner under one
    fresh pair id, the request's base before the head when one is named,
    writing every result before answering; non-zero only when a required head
    envelope is missing."""
    out.mkdir(parents=True, exist_ok=True)
    request.write(out / REQUEST_FILE)
    failed_required = False
    for shard in plan if plan is not None else SHARDS:
        if shard.id not in ids:
            continue
        pair_id = uuid.uuid4().hex
        if request.base_commit is not None:
            measure_base(request.base_commit, shard.id, out / BASE, request, pair_id, base_runner)
        result = collect_shard(shard, runner)
        write_shard(result, request, HEAD, request.head_commit, pair_id, out / HEAD / shard.id)
        failed_required = failed_required or result.failed_required
    return 1 if failed_required else 0


# --------------------------------------------------------------------------- #
# Assembly: what arrived, reconciled against what was planned                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ShardCapture:
    """One directory found among the assembly inputs: a capture, an
    unavailable marker, or something that decodes as neither."""

    source: str
    capture: Capture | None = None
    portfolio: Document | None = None
    durations: Spans | None = None
    durations_reason: str | None = None
    unavailable: Unavailability | None = None
    unavailable_shard: str | None = None
    unavailable_commit: str | None = None
    problems: tuple[str, ...] = ()

    @property
    def shard_id(self) -> str | None:
        if self.capture is not None:
            return self.capture.shard_id
        return self.unavailable_shard

    @property
    def side(self) -> str | None:
        if self.capture is not None:
            return self.capture.side
        return BASE if self.unavailable is not None else None

    @property
    def envelope(self) -> Document | None:
        if self.capture is None or self.portfolio is None:
            return None
        members = _members(self.portfolio, self.capture.subject)
        return members[0] if len(members) == 1 else None


def discover(root: Path) -> list[ShardCapture]:
    """Every capture or unavailable marker under ``root``, in path order,
    duplicates included; the source is the directory's path under ``root``."""
    found: list[ShardCapture] = []
    for directory in sorted(
        {path.parent for name in (CAPTURE_FILE, UNAVAILABLE_FILE) for path in root.rglob(name)}
    ):
        found.append(_discovered(directory, directory.relative_to(root).as_posix()))
    return found


def _discovered(directory: Path, source: str) -> ShardCapture:
    problems: list[str] = []
    capture: Capture | None = None
    portfolio: Document | None = None
    durations: Spans | None = None
    durations_reason: str | None = None
    unavailable: Unavailability | None = None
    unavailable_shard: str | None = None
    unavailable_commit: str | None = None
    if (directory / CAPTURE_FILE).exists():
        try:
            capture = Capture.from_document(_load(directory / CAPTURE_FILE))
        except (KeyError, TypeError, ValueError, OSError) as error:
            problems.append(f"{CAPTURE_FILE} does not decode: {error}")
        try:
            portfolio = _load(directory / "portfolio.json")
            if not isinstance(cast("object", portfolio), Mapping):
                raise TypeError("the portfolio is not an object")
        except (TypeError, ValueError, OSError) as error:
            problems.append(f"portfolio.json does not decode: {error}")
        if (directory / DURATIONS_FILE).exists():
            try:
                durations = Spans.load(directory / DURATIONS_FILE)
            except (KeyError, TypeError, ValueError, OSError) as error:
                durations_reason = f"the durations sidecar does not decode: {error}"
        else:
            durations_reason = "no durations sidecar arrived"
    if (directory / UNAVAILABLE_FILE).exists():
        try:
            marker = _object(_load(directory / UNAVAILABLE_FILE), "unavailable marker")
            if marker.get("schemaVersion") != MARKER_VERSION:
                raise ValueError(
                    f"unavailable marker schemaVersion {marker.get('schemaVersion')!r} "
                    "is unsupported"
                )
            unavailable = Unavailability.from_document(marker.get("reason"))
            unavailable_shard = _text(marker, "shard")
            if marker.get("side") != BASE:
                raise ValueError(f"unavailable marker side {marker.get('side')!r} is not base")
            unavailable_commit = _commit(
                _text(marker, "baseCommit"), "unavailable marker baseCommit"
            )
        except (KeyError, TypeError, ValueError, OSError) as error:
            problems.append(f"{UNAVAILABLE_FILE} does not decode: {error}")
    return ShardCapture(
        source,
        capture,
        portfolio,
        durations,
        durations_reason,
        unavailable,
        unavailable_shard,
        unavailable_commit,
        tuple(problems),
    )


@dataclass(frozen=True, slots=True)
class Reason:
    code: str
    side: str | None
    message: str

    def document(self) -> dict[str, object]:
        return {"code": self.code, "side": self.side, "message": self.message}


@dataclass(frozen=True, slots=True)
class Failure:
    code: str
    message: str
    shard: str | None = None
    side: str | None = None
    source: str | None = None

    def document(self) -> dict[str, object]:
        return {
            "code": self.code,
            "shard": self.shard,
            "side": self.side,
            "source": self.source,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class History:
    """The previous nightly assembly, when one could be read."""

    document: Document | None
    reason: str | None = None

    @classmethod
    def load(cls, path: Path | None) -> History:
        if path is None:
            return cls(None, None)
        portfolio = path / "portfolio.json"
        if not portfolio.exists():
            stated = _stated_history_reason(path / HISTORY_FILE)
            return cls(None, stated or f"no previous assembly at {portfolio}")
        try:
            document = _load(portfolio)
        except (ValueError, OSError) as error:
            return cls(None, f"the previous assembly does not decode: {error}")
        if not isinstance(cast("object", document), Mapping):
            return cls(None, "the previous assembly is not an object")
        if document.get("schemaVersion") != ASSEMBLY_VERSION:
            return cls(
                None,
                f"the previous assembly has schemaVersion {document.get('schemaVersion')!r}, "
                f"expected {ASSEMBLY_VERSION}",
            )
        shards = document.get("shards")
        if not isinstance(shards, list):
            return cls(None, "the previous assembly shards is not a list")
        entries = cast("list[object]", shards)
        if not all(
            isinstance(entry, Mapping) and isinstance(cast("Document", entry).get("id"), str)
            for entry in entries
        ):
            return cls(None, "the previous assembly holds a shard entry without a string id")
        return cls(document, None)

    def head(self, shard_id: str) -> ShardCapture | None:
        """The previous head of ``shard_id``: none when the assembly has no
        such entry or the entry has no head, and a problem when it has more
        than one entry or the head does not decode."""
        if self.document is None:
            return None
        source = f"against/{shard_id}"
        entries = [
            entry
            for entry in cast("Sequence[Document]", self.document["shards"])
            if entry.get("id") == shard_id
        ]
        if not entries:
            return None
        if len(entries) > 1:
            return ShardCapture(
                source,
                problems=(f"the previous assembly holds {len(entries)} entries for {shard_id!r}",),
            )
        head = entries[0].get("head")
        if head is None:
            return None
        try:
            recorded = _object(head, "previous head")
            capture = Capture.from_document(recorded.get("capture"))
            portfolio = _object(recorded.get("portfolio"), "previous portfolio")
        except (KeyError, TypeError, ValueError) as error:
            return ShardCapture(source, problems=(f"the previous head does not decode: {error}",))
        return ShardCapture(source, capture, portfolio, None, "previous durations are not carried")


def _stated_history_reason(marker: Path) -> str | None:
    """The reason the adapter recorded for obtaining no previous assembly, when
    the marker is present and decodes to one."""
    if not marker.exists():
        return None
    try:
        document = _load(marker)
    except (ValueError, OSError):
        return None
    if not isinstance(cast("object", document), Mapping):
        return None
    if document.get("schemaVersion") != HISTORY_VERSION:
        return None
    reason = document.get("reason")
    return reason if isinstance(reason, str) and reason else None


type ContractSource = Callable[[str], BudgetContract]


def contract_at(commit: str) -> BudgetContract:
    """The Budget Contract as authored at ``commit``."""
    authored = subprocess.run(
        ["git", "show", f"{commit}:languages/python/spec/budget-contract.yaml"],
        cwd=WORKSPACE,
        capture_output=True,
        check=True,
    ).stdout
    return BudgetContract.from_bytes(WORKSPACE / "spec" / "budget-contract.yaml", authored)


@dataclass(frozen=True, slots=True)
class ShardAssembly:
    shard: Shard
    head: ShardCapture | None
    base: ShardCapture | None
    pairing: str
    reasons: tuple[Reason, ...]
    sources: tuple[str, ...]
    comparison: tuple[str, ...]

    def document(self) -> dict[str, object]:
        return {
            "id": self.shard.id,
            "base": _side_document(self.base),
            "head": _side_document(self.head),
            "pairing": self.pairing,
            "reasons": [reason.document() for reason in self.reasons],
            "sources": list(self.sources),
        }


def _side_document(side: ShardCapture | None) -> dict[str, object] | None:
    if side is None or side.capture is None:
        return None
    return {"portfolio": side.portfolio, "capture": side.capture.document()}


@dataclass(frozen=True, slots=True)
class Assembly:
    request: Request
    plan: tuple[Shard, ...]
    shards: tuple[ShardAssembly, ...]
    failures: tuple[Failure, ...]
    durations: Spans
    history: History

    def document(self) -> dict[str, object]:
        return {
            "schemaVersion": ASSEMBLY_VERSION,
            "request": self.request.document(),
            "plan": [shard.document() for shard in self.plan],
            "shards": [shard.document() for shard in self.shards],
            "failures": [failure.document() for failure in self.failures],
        }

    def summary(self) -> str:
        return _assembly_summary(self)


SAME_RUNNER: Final = "same-runner"
CROSS_RUNNER: Final = "cross-runner"
UNPAIRED: Final = "unavailable"


def assemble(
    captures: Sequence[ShardCapture],
    plan: Sequence[Shard],
    request: Request,
    history: History | None = None,
    contracts: ContractSource = contract_at,
) -> Assembly:
    """Reconcile ``captures`` against ``plan`` and ``request``: one entry per
    planned shard whatever arrived, every side validated against its own
    recorded selection and producing contract, and comparisons only between
    matched, compatible cells."""
    previous = history if history is not None else History(None, None)
    failures: list[Failure] = []
    by_shard: dict[str, list[ShardCapture]] = {shard.id: [] for shard in plan}
    for capture in captures:
        if capture.problems:
            failures.extend(
                Failure("input-malformed", problem, capture.shard_id, capture.side, capture.source)
                for problem in capture.problems
            )
            continue
        if capture.capture is not None and capture.capture.request.run != request.run:
            failures.append(
                Failure(
                    "request-mismatch",
                    f"the capture answers request {capture.capture.request.run}, not {request.run}",
                    capture.shard_id,
                    capture.side,
                    capture.source,
                )
            )
            continue
        if (
            capture.unavailable is not None
            and request.base_commit is not None
            and capture.unavailable_commit != request.base_commit
        ):
            failures.append(
                Failure(
                    "request-mismatch",
                    f"the marker names base {capture.unavailable_commit}, "
                    f"the request names {request.base_commit}",
                    capture.shard_id,
                    capture.side,
                    capture.source,
                )
            )
            continue
        if capture.shard_id not in by_shard:
            failures.append(
                Failure(
                    "unexpected-shard",
                    f"shard {capture.shard_id!r} is not in the plan",
                    capture.shard_id,
                    capture.side,
                    capture.source,
                )
            )
            continue
        by_shard[capture.shard_id].append(capture)
    merged = Spans()
    assembled: list[ShardAssembly] = []
    for shard in plan:
        entry = _reconcile(shard, by_shard[shard.id], request, previous, contracts, failures)
        assembled.append(entry)
        for side in (entry.base, entry.head):
            _merge_durations(merged, shard.id, side, request)
    return Assembly(request, tuple(plan), tuple(assembled), tuple(failures), merged, previous)


def _merge_durations(
    merged: Spans, shard_id: str, side: ShardCapture | None, request: Request
) -> None:
    if side is None or side.capture is None:
        return
    name = f"{shard_id}/{side.capture.side}"
    if side.durations is None:
        merged.missing("collection", name, side.durations_reason or "no durations arrived")
        return
    attribution = {
        "shard": shard_id,
        "side": side.capture.side,
        "source": side.source,
        "request": side.capture.request.request_id,
        "run": side.capture.request.run_id or "-",
    }
    for span in side.durations.spans:
        merged.add(replace(span, labels={**attribution, **span.labels}))
    for entry in side.durations.unavailable:
        merged.missing(entry.scope, f"{name} {entry.name}", entry.reason)


def _reconcile(
    shard: Shard,
    arrived: Sequence[ShardCapture],
    request: Request,
    history: History,
    contracts: ContractSource,
    failures: list[Failure],
) -> ShardAssembly:
    reasons: list[Reason] = []
    sources = tuple(capture.source for capture in arrived)
    head = _unique(
        shard,
        HEAD,
        [c for c in arrived if c.side == HEAD],
        request.head_commit,
        contracts,
        reasons,
        failures,
    )
    base_candidates = [c for c in arrived if c.side == BASE]
    pairing = UNPAIRED
    base: ShardCapture | None = None
    if request.base_commit is not None:
        base = _unique(
            shard, BASE, base_candidates, request.base_commit, contracts, reasons, failures
        )
        if base is not None and head is not None:
            assert base.capture is not None and head.capture is not None
            if base.capture.pair_id == head.capture.pair_id:
                pairing = SAME_RUNNER
            else:
                reasons.append(
                    Reason(
                        "pair-mismatch",
                        BASE,
                        f"the base capture belongs to invocation {base.capture.pair_id}, "
                        f"the head to {head.capture.pair_id}; a base measured by another "
                        "invocation is never paired",
                    )
                )
    else:
        if base_candidates:
            for candidate in base_candidates:
                failures.append(
                    Failure(
                        "unexpected-base",
                        "a base arrived for a request that names no base commit",
                        shard.id,
                        BASE,
                        candidate.source,
                    )
                )
        if history.reason is not None:
            reasons.append(Reason("history-unavailable", BASE, history.reason))
        elif history.document is not None:
            base = _previous(shard, history, contracts, reasons)
            if base is not None:
                pairing = CROSS_RUNNER
        else:
            reasons.append(Reason("base-not-requested", BASE, "the request names no base commit"))
    comparison = _compared(base if pairing != UNPAIRED else None, head, pairing, reasons)
    return ShardAssembly(shard, head, base, pairing, tuple(reasons), sources, tuple(comparison))


def _previous(
    shard: Shard, history: History, contracts: ContractSource, reasons: list[Reason]
) -> ShardCapture | None:
    previous = history.head(shard.id)
    if previous is None:
        reasons.append(
            Reason(
                "history-missing-shard", BASE, f"the previous assembly has no head for {shard.id!r}"
            )
        )
        return None
    if previous.problems:
        reasons.append(Reason("history-invalid", BASE, "; ".join(previous.problems)))
        return None
    assert previous.capture is not None
    side_reasons = _side_reasons(shard, previous, previous.capture.commit, contracts)
    reasons.extend(replace(reason, side=BASE) for reason in side_reasons)
    return previous if not side_reasons else None


def _unique(
    shard: Shard,
    side: str,
    candidates: Sequence[ShardCapture],
    expected_commit: str,
    contracts: ContractSource,
    reasons: list[Reason],
    failures: list[Failure],
) -> ShardCapture | None:
    if not candidates:
        reasons.append(Reason(f"{side}-missing", side, f"no {side} capture arrived"))
        return None
    if len(candidates) > 1:
        listed = ", ".join(candidate.source for candidate in candidates)
        reasons.append(
            Reason(f"{side}-duplicate", side, f"{len(candidates)} {side} inputs arrived: {listed}")
        )
        for candidate in candidates:
            failures.append(
                Failure(
                    "duplicate-capture",
                    f"one of {len(candidates)} {side} inputs",
                    shard.id,
                    side,
                    candidate.source,
                )
            )
        return None
    (only,) = candidates
    if only.capture is None:
        assert only.unavailable is not None
        reasons.append(Reason(only.unavailable.code, side, only.unavailable.message))
        return None
    side_reasons = _side_reasons(shard, only, expected_commit, contracts, planned=side == HEAD)
    for reason in side_reasons:
        reasons.append(replace(reason, side=side))
        failures.append(Failure(reason.code, reason.message, shard.id, side, only.source))
    return only if not side_reasons else None


def _side_reasons(
    shard: Shard,
    side: ShardCapture,
    expected_commit: str,
    contracts: ContractSource,
    *,
    planned: bool = False,
) -> list[Reason]:
    """Every reason one side is not valid evidence for ``shard``, judged
    against the selection the capture itself records; a ``planned`` side was
    measured by this checkout's own tool, so it must also record the planned
    selection and every supported runtime."""
    assert side.capture is not None
    capture = side.capture
    reasons: list[Reason] = []
    if capture.subject != shard.subject:
        reasons.append(
            Reason(
                "capture-mismatch",
                None,
                f"the capture is of {capture.subject}, not {shard.subject}",
            )
        )
        return reasons
    if planned:
        expected_workloads = tuple(sorted(shard.workloads)) if shard.workloads is not None else None
        if capture.workloads != expected_workloads:
            reasons.append(
                Reason(
                    "capture-mismatch",
                    None,
                    f"the capture selected {capture.workloads}, "
                    f"the plan selects {expected_workloads}",
                )
            )
            return reasons
        if set(capture.runtimes) != set(supported_minors()):
            reasons.append(
                Reason(
                    "capture-mismatch",
                    None,
                    f"the capture records runtimes {sorted(capture.runtimes)}, "
                    f"the plan measures {list(supported_minors())}",
                )
            )
            return reasons
    if capture.commit != expected_commit:
        reasons.append(
            Reason(
                "commit-mismatch",
                None,
                f"the capture measured {capture.commit}, expected {expected_commit}",
            )
        )
    if side.portfolio is None:
        reasons.append(Reason("envelope-missing", None, "no portfolio arrived"))
        return reasons
    if is_diagnostic(side.portfolio):
        reasons.append(Reason("diagnostic", None, "a diagnostic reading set is not evidence"))
        return reasons
    envelope = side.envelope
    if envelope is None:
        recorded = [
            str(cast("Document", failure).get("message"))
            for failure in cast("Sequence[object]", side.portfolio.get("failures", ()))
            if isinstance(failure, Mapping)
        ]
        reasons.append(
            Reason(
                "envelope-missing",
                None,
                f"the portfolio holds no single {shard.subject} envelope"
                + (f": {'; '.join(recorded)}" if recorded else ""),
            )
        )
        return reasons
    try:
        validate(envelope)
        contract = contracts(str(cast("Document", envelope["provenance"])["commit"]))
        validate_matrix(
            envelope,
            shard.subject,
            contract,
            workload_selection(capture.workloads or (), contract),
            sorted(capture.runtimes),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        ValidationError,
        subprocess.CalledProcessError,
    ) as error:
        reasons.append(Reason("envelope-invalid", None, f"the envelope is invalid: {error}"))
        return reasons
    provenance = _provenance(envelope)
    assert provenance is not None
    if provenance.get("commit") != capture.commit:
        reasons.append(
            Reason(
                "provenance-commit-mismatch",
                None,
                f"the envelope was produced at {provenance.get('commit')}, "
                f"the capture says {capture.commit}",
            )
        )
    if provenance.get("dirty") is not False:
        reasons.append(
            Reason("provenance-dirty", None, "the envelope was not produced from a clean tree")
        )
    if (envelope.get("incomplete") or envelope.get("errors")) and shard.member.required:
        reasons.append(
            Reason(
                "envelope-incomplete", None, "the required envelope is incomplete or carries errors"
            )
        )
    return reasons


def _compared(
    base: ShardCapture | None,
    head: ShardCapture | None,
    pairing: str,
    reasons: list[Reason],
) -> list[str]:
    """One shard's comparison rows: paired cells for every compatible runtime,
    and one row naming why each other cell is unavailable."""
    if head is None or head.envelope is None:
        return ["No head envelope is available; nothing was compared."]
    head_envelope = head.envelope
    if base is None or base.envelope is None:
        why = "; ".join(f"{r.code}: {r.message}" for r in reasons if r.side == BASE)
        return _unavailable_rows(head_envelope, f"base unavailable ({why or 'no base'})")
    base_envelope = base.envelope
    whole, per_runtime = _incompatibilities(base, head)
    reasons.extend(replace(reason, side=BASE) for reason in (*whole, *per_runtime.values()))
    if whole:
        why = "; ".join(f"{r.code}: {r.message}" for r in whole)
        return _unavailable_rows(head_envelope, f"incompatible ({why})")
    lines: list[str] = []
    if pairing == CROSS_RUNNER:
        lines += [
            "Cross-runner comparison: the two sides were measured on different runners on "
            "different runs, and the noise allowances were calibrated on same-runner pairs.",
            "",
        ]
    excluded = set(per_runtime)
    lines += _comparison_rows(
        _without_runtimes(base_envelope, excluded), _without_runtimes(head_envelope, excluded)
    )
    for runtime in sorted(excluded):
        reason = per_runtime[runtime]
        lines += [
            f"| {_spelled_pair(address)} | | | | | unavailable: {reason.code}: {reason.message} |"
            for address in sorted(
                {a for a in _pairs(base_envelope) if a[0] == runtime}
                | {a for a in _pairs(head_envelope) if a[0] == runtime}
            )
        ]
    return lines


def _unavailable_rows(envelope: Document, why: str) -> list[str]:
    return [
        *COMPARISON_HEADER,
        *(
            f"| {_spelled_pair(address)} | | | | | unavailable: {why} |"
            for address in sorted(_pairs(envelope))
        ),
    ]


def _without_runtimes(envelope: Document, runtimes: set[str]) -> Document:
    return {
        **envelope,
        "readings": [
            reading
            for reading in _readings(envelope)
            if str(reading.get("runtime", "")) not in runtimes
        ],
    }


def _incompatibilities(
    base: ShardCapture, head: ShardCapture
) -> tuple[list[Reason], dict[str, Reason]]:
    """Why cells of a shard cannot be compared: reasons that exclude the
    whole shard (a selection, workload, or sampling mismatch), and per
    runtime, one that excludes its cells (an interpreter not the same full
    version on both sides, or one whose identity is unknown)."""
    assert base.capture is not None and head.capture is not None
    base_envelope = base.envelope
    head_envelope = head.envelope
    assert base_envelope is not None and head_envelope is not None
    whole: list[Reason] = []
    if base.capture.workloads != head.capture.workloads:
        whole.append(
            Reason(
                "selection-mismatch",
                None,
                f"base selected {base.capture.workloads}, head selected {head.capture.workloads}",
            )
        )
    base_provenance = _provenance(base_envelope) or {}
    head_provenance = _provenance(head_envelope) or {}
    if base_provenance.get("workloadDigest") != head_provenance.get("workloadDigest"):
        whole.append(
            Reason(
                "workload-digest-mismatch",
                None,
                "the two sides measured different workload sources",
            )
        )
    if base_provenance.get("sampling") != head_provenance.get("sampling"):
        whole.append(
            Reason("sampling-mismatch", None, "the two sides sampled under different protocols")
        )
    per_runtime: dict[str, Reason] = {}
    runtimes = {
        str(reading.get("runtime", ""))
        for reading in (*_readings(base_envelope), *_readings(head_envelope))
    }
    for runtime in sorted(runtimes):
        if runtime == "":
            if base_provenance.get("cpython") != head_provenance.get("cpython"):
                per_runtime[runtime] = Reason(
                    "runtime-mismatch",
                    None,
                    f"the in-process interpreter is {base_provenance.get('cpython')} on base "
                    f"and {head_provenance.get('cpython')} on head",
                )
            continue
        base_status = base.capture.runtimes.get(runtime, RuntimeUnavailable("not recorded"))
        head_status = head.capture.runtimes.get(runtime, RuntimeUnavailable("not recorded"))
        unknown = [
            f"{side} ({status.reason})"
            for side, status in ((BASE, base_status), (HEAD, head_status))
            if isinstance(status, RuntimeUnavailable)
        ]
        if isinstance(base_status, RuntimeUnavailable) or isinstance(
            head_status, RuntimeUnavailable
        ):
            per_runtime[runtime] = Reason(
                "runtime-unavailable",
                None,
                f"CPython {runtime} identity is unknown on {' and '.join(unknown)}",
            )
        elif not _same_interpreter(base_status, head_status):
            per_runtime[runtime] = Reason(
                "runtime-mismatch",
                None,
                f"CPython {runtime} is {base_status.implementation} {base_status.version} on "
                f"base and {head_status.implementation} {head_status.version} on head",
            )
    return whole, per_runtime


def _same_interpreter(base: RuntimeIdentity, head: RuntimeIdentity) -> bool:
    return (base.implementation, base.version) == (head.implementation, head.version)


def _assembly_summary(assembly: Assembly) -> str:
    request = assembly.request
    lines = [
        "# Python cost report assembly",
        "",
        f"Request `{request.request_id}` ({request.event}, {request.layout} layout): head "
        f"`{request.head_commit}`, base `{request.base_commit or 'none'}`, workflow "
        f"`{request.workflow_commit}`, run {request.run_id or '-'} attempt "
        f"{request.run_attempt if request.run_attempt is not None else '-'}.",
        "",
        "## Coverage",
        "",
        "| Shard | Subject | Workloads | Head | Base | Pairing | Reasons |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in assembly.shards:
        lines.append(
            f"| {entry.shard.id} | {entry.shard.subject} | "
            f"{', '.join(sorted(entry.shard.workloads)) if entry.shard.workloads else 'all'} | "
            f"{_presence(entry.head)} | {_presence(entry.base)} | {entry.pairing} | "
            f"{'; '.join(f'{r.code} ({r.side or "shard"})' for r in entry.reasons) or '-'} |"
        )
    present = sum(1 for entry in assembly.shards if entry.head is not None)
    lines += [
        "",
        f"Planned {len(assembly.plan)} shard(s); {present} with a valid head capture; "
        f"{len(assembly.failures)} collection failure(s).",
    ]
    if assembly.history.reason is not None:
        lines.append(f"Previous nightly: unavailable ({assembly.history.reason}).")
    if assembly.failures:
        lines += ["", "## Collection failures", ""]
        lines += [
            f"- `{failure.code}` shard {failure.shard or '-'} side {failure.side or '-'} "
            f"source `{failure.source or '-'}`: {failure.message}"
            for failure in assembly.failures
        ]
    for entry in assembly.shards:
        lines += ["", f"## {entry.shard.id}", ""]
        for reason in entry.reasons:
            lines.append(f"- {reason.side or 'shard'} `{reason.code}`: {reason.message}")
        if entry.reasons:
            lines.append("")
        for label, side in ((HEAD, entry.head), (BASE, entry.base)):
            lines += _provenance_lines(label, side)
        lines += ["", f"Pairing: {entry.pairing}.", "", *entry.comparison]
    lines += ["", _critical_path(assembly), "", render(_outer(assembly.durations)).rstrip("\n")]
    return "\n".join(lines) + "\n"


def _presence(side: ShardCapture | None) -> str:
    if side is None:
        return "unavailable"
    return f"`{side.source}`"


def _provenance_lines(label: str, side: ShardCapture | None) -> list[str]:
    if side is None or side.capture is None:
        return [f"- {label}: unavailable"]
    capture = side.capture
    runtimes = ", ".join(
        f"{runtime} = "
        + (
            f"{status.implementation} {status.version}"
            if isinstance(status, RuntimeIdentity)
            else f"unavailable ({status.reason})"
        )
        for runtime, status in sorted(capture.runtimes.items())
    )
    runner = (
        f"{capture.runner['image']} {capture.runner['imageVersion']}"
        if capture.runner is not None
        else "unknown runner"
    )
    lines = [
        f"- {label}: commit `{capture.commit}`, pair `{capture.pair_id}`, {runner}, "
        f"request `{capture.request.request_id}` run {capture.request.run_id or '-'}, "
        f"runtimes {runtimes or '-'}, source `{side.source}`"
    ]
    provenance = _provenance(side.envelope) if side.envelope is not None else None
    if provenance is not None:
        lines.append(
            f"  - provenance: {provenance.get('machine')} / {provenance.get('cpu')} / "
            f"{provenance.get('os')} / CPython {provenance.get('cpython')} / PostgreSQL "
            f"{provenance.get('postgres')}; workload digest `{provenance.get('workloadDigest')}`, "
            f"contract digest `{provenance.get('budgetContractDigest')}`, lock digest "
            f"`{provenance.get('lockDigest')}`"
        )
    return lines


def _critical_path(assembly: Assembly) -> str:
    """The longest shard's base-then-head collection time: what one runner
    spent measuring, never a sum across runners."""
    per_shard: dict[str, float] = {}
    for span in assembly.durations.spans:
        if span.scope == "collection" and "shard" in span.labels:
            per_shard[span.labels["shard"]] = (
                per_shard.get(span.labels["shard"], 0.0) + span.seconds
            )
    if not per_shard:
        return "Critical path: unavailable, no shard collection span arrived."
    longest = max(per_shard, key=lambda shard: per_shard[shard])
    return (
        f"Critical path: {per_shard[longest]:.3f} s on shard `{longest}` (its base and head "
        "collection spans, which run one after the other on one runner). Shards on separate "
        "runners run concurrently and are never summed."
    )


def _outer(spans: Spans) -> Spans:
    """The collection and member spans alone, for a readable table."""
    outer = Spans()
    for span in spans.spans:
        if span.scope in {"collection", "member"}:
            outer.add(span)
    for entry in spans.unavailable:
        outer.missing(entry.scope, entry.name, entry.reason)
    return outer


def write_assembly(
    assembly: Assembly, inputs: Path, captures: Sequence[ShardCapture], out: Path
) -> None:
    """The assembled artifact, with every input retained raw under its source."""
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "portfolio.json", assembly.document())
    assembly.durations.write(out / DURATIONS_FILE)
    (out / "summary.md").write_text(assembly.summary(), encoding="utf-8")
    for capture in captures:
        if capture.source.startswith("against/"):
            continue
        destination = out / "raw" / capture.source
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(inputs / capture.source, destination)


DIAGNOSTIC_PREFIX: Final = "diagnostic-"
"""What a diagnostic reading file is named with, beside the subject it reads."""


def diagnostic_arguments(
    member: Member, selections: Sequence[str], runtimes: Sequence[str]
) -> list[str]:
    """The diagnostic invocation of one member script for the chosen subset."""
    option = "--case" if member.subject == WRITE_SUBJECT else "--select"
    arguments = ["--diagnostic"]
    for pattern in selections:
        arguments += [option, pattern]
    for runtime in runtimes:
        arguments += ["--runtime", runtime]
    return arguments


def diagnose(
    subjects: Sequence[str],
    selections: Sequence[str],
    runtimes: Sequence[str],
    out: Path | None,
    runner: Runner = run_member,
) -> int:
    """Take diagnostic readings from the chosen required members and write or
    print each member's diagnostic document; never a portfolio, and never into
    the directory the committed capture lives in."""
    members = [member for member in MEMBERS if member.required and member.subject in subjects]
    unknown = set(subjects) - {member.subject for member in members}
    if unknown or not members:
        print(
            f"diagnostic members are {[m.subject for m in MEMBERS if m.required]}", file=sys.stderr
        )
        return 2
    if out is not None and out.resolve().is_relative_to(EVIDENCE_DIRECTORY):
        print(f"a diagnostic run writes nothing into {EVIDENCE_DIRECTORY}", file=sys.stderr)
        return 2
    status = 0
    for member in members:
        returncode, stdout, stderr = runner(
            member, diagnostic_arguments(member, selections, runtimes)
        )
        if returncode != 0:
            print(
                f"{member.recipe} diagnostic exited {returncode}: {stderr.strip()}", file=sys.stderr
            )
            status = 1
            continue
        document = cast("Document", json.loads(stdout))
        if not document.get("diagnostic"):
            print(f"{member.recipe} did not answer a diagnostic document", file=sys.stderr)
            status = 1
            continue
        rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
        if out is None:
            print(rendered, end="")
        else:
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{DIAGNOSTIC_PREFIX}{member.subject}.json").write_text(
                rendered, encoding="utf-8"
            )
    return status


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a number, received {value!r}")
    return float(value)


def resolve_commit(ref: str) -> str | None:
    """The full commit ``ref`` names in the inspected checkout, or ``None``."""
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() or None if completed.returncode == 0 else None


def _shard_request(
    parser: argparse.ArgumentParser, shard: str, request_path: Path | None, base_ref: str | None
) -> Request:
    layout = "sequential" if shard == ALL_SHARDS else "sharded"
    base = None
    if base_ref is not None:
        base = resolve_commit(base_ref)
        if base is None:
            parser.error(f"--base-commit {base_ref!r} is not a commit of this checkout")
    if request_path is None:
        return local_request(layout, base)
    try:
        request = Request.load(request_path)
    except (KeyError, TypeError, ValueError, OSError) as error:
        parser.error(f"--request {request_path} does not hold a request: {error}")
    if request.layout != layout:
        parser.error(f"--shard {shard} is the {layout} layout; the request says {request.layout}")
    if base is not None and request.base_commit != base:
        parser.error(f"--base-commit {base} disagrees with the request's {request.base_commit}")
    head = git_head()
    if request.head_commit != head:
        parser.error(f"the request's head {request.head_commit} is not the checkout's {head}")
    return request


def _assembly_request(
    parser: argparse.ArgumentParser, inputs: Path, request_path: Path | None
) -> Request:
    path = request_path if request_path is not None else inputs / REQUEST_FILE
    try:
        return Request.load(path)
    except (KeyError, TypeError, ValueError, OSError) as error:
        parser.error(f"{path} does not hold the request to assemble against: {error}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--freshness-only", type=Path, metavar="PORTFOLIO")
    parser.add_argument("--lock-file", type=Path, help="lock inspected by --freshness-only")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BASE", "HEAD"))
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="take readings for a subset of members, workloads, and runtimes; not evidence",
    )
    parser.add_argument("--member", action="append", default=[], help="a required member subject")
    parser.add_argument("--select", action="append", default=[], help="workload or case pattern")
    parser.add_argument("--runtime", action="append", default=[], help="CPython minor")
    parser.add_argument("--plan", action="store_true", help="print the shard ids a layout runs")
    parser.add_argument("--layout", choices=LAYOUTS, help="the layout --plan prints")
    parser.add_argument("--shard", metavar="ID", help=f"measure one shard, or {ALL_SHARDS!r}")
    parser.add_argument("--base-commit", metavar="COMMIT", help="measure this base first")
    parser.add_argument("--request", type=Path, help="the immutable request being answered")
    parser.add_argument("--assemble", type=Path, metavar="INPUT", help="reconcile shard outputs")
    parser.add_argument("--against", type=Path, metavar="PREVIOUS", help="a previous assembly")
    args = parser.parse_args(argv)
    modes = [
        name
        for name, chosen in (
            ("--diagnostic", args.diagnostic),
            ("--plan", args.plan),
            ("--shard", args.shard is not None),
            ("--assemble", args.assemble is not None),
            ("--freshness-only", args.freshness_only is not None),
            ("--verify", args.verify is not None),
            ("--compare", args.compare is not None),
        )
        if chosen
    ]
    if len(modes) > 1:
        parser.error(f"{' and '.join(modes)} are separate modes")
    if args.lock_file is not None and args.freshness_only is None:
        parser.error("--lock-file requires --freshness-only")
    if (args.member or args.select or args.runtime) and not args.diagnostic:
        parser.error("--member, --select, and --runtime are diagnostic options")
    if args.layout is not None and not args.plan:
        parser.error("--layout is a --plan option")
    if args.base_commit is not None and args.shard is None:
        parser.error("--base-commit is a --shard option")
    if args.against is not None and args.assemble is None:
        parser.error("--against is an --assemble option")
    if args.request is not None and args.shard is None and args.assemble is None:
        parser.error("--request is a --shard or --assemble option")
    if args.diagnostic:
        subjects = args.member or [member.subject for member in MEMBERS if member.required]
        return diagnose(subjects, args.select, args.runtime, args.out)
    if args.plan:
        validate_plan(SHARDS)
        print(json.dumps(plan_ids(args.layout or "sharded")))
        return 0
    if args.shard is not None:
        if args.out is None:
            parser.error("--out is required when collecting a shard")
        ids = plan_ids("sharded") if args.shard == ALL_SHARDS else [args.shard]
        if args.shard not in {*plan_ids("sharded"), ALL_SHARDS}:
            parser.error(
                f"shard {args.shard!r} is not one of {plan_ids('sharded')} or {ALL_SHARDS!r}"
            )
        validate_plan(SHARDS)
        request = _shard_request(parser, args.shard, args.request, args.base_commit)
        return run_shards(ids, request, args.out, run_member, run_base)
    if args.assemble is not None:
        if args.out is None:
            parser.error("--out is required when assembling")
        request = _assembly_request(parser, args.assemble, args.request)
        if args.against is not None and (
            request.is_pull_request or request.base_commit is not None
        ):
            parser.error("--against pairs a nightly with its predecessor, never a pull request")
        validate_plan(SHARDS)
        captures = discover(args.assemble) if args.assemble.exists() else []
        assembly = assemble(captures, SHARDS, request, History.load(args.against))
        write_assembly(assembly, args.assemble, captures, args.out)
        print(assembly.summary(), end="")
        return 0
    if args.freshness_only is not None:
        fresh, freshness = lock_freshness(_load(args.freshness_only), args.lock_file)
        print(freshness if fresh else f"advisory: {freshness}")
        return 0 if fresh or not freshness.startswith(LOCK_FRESHNESS_UNAVAILABLE) else 1
    if args.verify is not None:
        document = _load(args.verify)
        fresh, freshness = lock_freshness(document)
        if fresh:
            print(freshness)
        for advisory in advisories(document):
            print(advisory)
        failures = verify(document)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1 if failures else 0
    if args.compare is not None:
        print(compare(_load(args.compare[0]), _load(args.compare[1])), end="")
        return 0
    if args.out is None:
        parser.error("--out is required when collecting")
    collection = collect(run_member)
    write_portfolio(collection, args.out)
    print(_summary(portfolio_document(collection.results), collection.durations), end="")
    return 1 if collection.failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
