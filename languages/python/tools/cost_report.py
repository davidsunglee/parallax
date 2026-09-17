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
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import statistics
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from jsonschema import ValidationError

import write_lowering_overhead as write_report
from interpreter_matrix import authority_minor, supported_minors
from parallax.conformance.budget import BudgetContract, MemoryGates, reading_bytes
from parallax.conformance.cost_envelope import Reading, validate
from parallax.conformance.workloads import workload_digest
from snapshot_delivery_overhead import (
    addresses as snapshot_addresses,
)
from snapshot_delivery_overhead import (
    comparison as snapshot_comparison,
)
from snapshot_delivery_overhead import (
    expanded_cells,
    expected_readings,
    is_scaling_cell,
    window_of,
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
    "languages/python/docs/structural-metadata-envelope/after/portfolio.json"
)
"""The repository's current cost portfolio and CI's verification input, relative
to the repository root. The `before/` capture beside it is the retained
comparison base, not a verification input."""

EVIDENCE_DIRECTORY: Final = (WORKSPACE.parents[1] / CANONICAL_PORTFOLIO).resolve().parents[1]
"""Where the committed captures live, the current one and its comparison base
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


type Runner = Callable[[Member], tuple[int, str, str]]
type Document = Mapping[str, object]
type ReadingAddress = tuple[str, str, str]
"""A reading's (runtime, workload, cell) address within one subject."""


def report_recipes() -> frozenset[str]:
    """The collector's member recipe names."""
    return frozenset(member.recipe for member in MEMBERS)


def run_member(member: Member) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(WORKSPACE / "tools" / member.script)],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _decoded(member: Member, output: str) -> Document:
    document = cast("Document", json.loads(output))
    validate(document)
    if document.get("subject") != member.subject:
        raise ValueError(
            f"{member.recipe} emitted subject {document.get('subject')!r}, "
            f"expected {member.subject!r}"
        )
    if member.subject == SNAPSHOT_SUBJECT:
        validate_snapshot_matrix(document, BudgetContract.load())
    if member.subject == WRITE_SUBJECT:
        validate_write_lowering_matrix(document)
    return document


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


def _exact(
    expected: Iterable[ReadingAddress], actual: Iterable[ReadingAddress], *, label: str
) -> None:
    wanted = set(expected)
    found = set(actual)
    missing = wanted - found
    extra = found - wanted
    if missing or extra:
        details = [
            *(f"missing {_spelled(address)}" for address in sorted(missing)),
            *(f"unexpected {_spelled(address)}" for address in sorted(extra)),
        ]
        raise ValueError(f"{label} matrix is not exact: {', '.join(details)}")


def _samples(document: Document) -> tuple[float, ...]:
    return tuple(_number(value) for value in cast("Sequence[object]", document["samples"]))


def validate_snapshot_matrix(document: Document, contract: BudgetContract) -> None:
    """Validate the exact contract-derived Snapshot report matrix on every
    supported runtime, with comparisons on the authority runtime alone."""
    runtimes = supported_minors()
    expected = snapshot_addresses(contract, runtimes)
    readings = _indexed(_readings(document), label="Snapshot reading")
    _exact(expected, readings, label="Snapshot reading")
    comparisons = _indexed(
        cast("Sequence[Document]", document["comparisons"]), label="Snapshot comparison"
    )
    contract_cells = {(cell.workload, cell.path): cell for cell in expanded_cells(contract)}
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


def validate_write_lowering_matrix(document: Document) -> None:
    """Validate the exact runtime-by-case write matrix, its windows, and units."""
    readings = _indexed(_readings(document), label="write-lowering reading")
    _exact(
        write_report.expected_addresses(supported_minors()),
        readings,
        label="write-lowering reading",
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


def collect(runner: Runner = run_member) -> tuple[list[MemberResult], bool]:
    """Attempt every member and fail only after required envelope validation."""
    results: list[MemberResult] = []
    for member in MEMBERS:
        returncode, stdout, stderr = runner(member)
        if returncode != 0:
            results.append(
                MemberResult(
                    member,
                    None,
                    f"exit {returncode}: {stderr.strip() or stdout.strip()}",
                )
            )
            continue
        try:
            envelope = _decoded(member, stdout)
            results.append(MemberResult(member, envelope))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as error:
            results.append(MemberResult(member, None, str(error)))
    failed_required = any(result.member.required and result.envelope is None for result in results)
    return results, failed_required


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


def _summary(document: Document) -> str:
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
    return "\n".join(lines) + "\n"


def write_portfolio(results: Sequence[MemberResult], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    document = portfolio_document(results)
    (out / "portfolio.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "summary.md").write_text(_summary(document), encoding="utf-8")
    for result in results:
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
        base_pairs = _pairs(base_members[0])
        head_pairs = _pairs(head_members[0])
        lines += [
            "| Runtime | Window | Workload | Cell | Base | Head | Delta | Samples | Verdict |",
            "|---|---|---|---|---:|---:|---:|---:|---|",
        ]
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
    lines += ["", "Deltas are advisory and never ratchet the Budget Contract."]
    return "\n".join(lines) + "\n"


def _load(path: Path) -> Document:
    return cast("Document", json.loads(path.read_text(encoding="utf-8")))


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


def run_member_diagnostic(member: Member, arguments: Sequence[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, str(WORKSPACE / "tools" / member.script), *arguments],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def diagnose(
    subjects: Sequence[str],
    selections: Sequence[str],
    runtimes: Sequence[str],
    out: Path | None,
    runner: Callable[[Member, Sequence[str]], tuple[int, str, str]] = run_member_diagnostic,
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
    args = parser.parse_args(argv)
    if args.lock_file is not None and args.freshness_only is None:
        parser.error("--lock-file requires --freshness-only")
    if (args.member or args.select or args.runtime) and not args.diagnostic:
        parser.error("--member, --select, and --runtime are diagnostic options")
    if args.diagnostic:
        if args.verify is not None or args.compare is not None or args.freshness_only is not None:
            parser.error("--diagnostic takes readings and neither verifies nor compares")
        subjects = args.member or [member.subject for member in MEMBERS if member.required]
        return diagnose(subjects, args.select, args.runtime, args.out)
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
    results, failed_required = collect()
    write_portfolio(results, args.out)
    print(_summary(portfolio_document(results)), end="")
    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
