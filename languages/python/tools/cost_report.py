"""Collect every quantitative Python report into one fail-late portfolio, verify
committed evidence, and compare two portfolios cell by cell.

Verification separates what makes evidence invalid — a missing or incomplete
required envelope, a non-authoritative or dirty capture, an unpublished
producing commit, stale workload or dependency digests, and a memory ceiling or
scaling limit exceeded — from what makes it adverse: a timing ceiling exceeded is
reported and never fails. Comparison pairs readings only when their subject,
runtime, window, workload, cell, and unit all agree, names every cell present on
one side alone, and judges a timing delta against one explicit noise allowance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import Reading, validate
from snapshot_delivery_overhead import (
    addresses as snapshot_addresses,
)
from snapshot_delivery_overhead import (
    comparison as snapshot_comparison,
)
from snapshot_delivery_overhead import (
    evidence_digest as snapshot_evidence_digest,
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
    "languages/python/docs/structural-metadata-envelope/before/portfolio.json"
)
"""The repository's current cost portfolio and CI's verification input, relative
to the repository root."""
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
        if reading_document.get("window") != window_of(path):
            raise ValueError(f"{_spelled(address)} reading window is not {window_of(path)!r}")
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
    """Compare retained dependencies with a lock file without reclassifying authority."""
    snapshot = _snapshot(document)
    if snapshot is None:
        return False, "lock freshness unavailable: expected one snapshot-delivery envelope"
    provenance = _provenance(snapshot)
    if provenance is None:
        return False, "lock freshness unavailable: snapshot-delivery provenance is not a mapping"
    recorded = provenance.get("lockDigest")
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
    commit = str(provenance.get("commit", ""))
    if provenance.get("dirty") is not False:
        failures.append(f"the {subject} envelope was not produced from a clean tree")
    if not is_published(commit):
        failures.append(
            f"the {subject} envelope's producing commit {commit[:12]} is not an ancestor "
            "of the inspected head"
        )
    if provenance.get("workloadDigest") != expected_digest:
        failures.append(f"the {subject} envelope's workload digest is stale")
    return failures


def _scaling_failures(snapshot: Document, contract: BudgetContract) -> list[str]:
    memory = cast("Mapping[str, object]", contract.sampling["memory"])
    arm_limit = _number(memory["armGrowthMaxKiB"])
    arm_size = contract.memory_children
    arm_count = len(contract.memory_scaling_arms)
    compared = authority_minor(contract.authority)
    failures: list[str] = []
    for reading in _readings(snapshot):
        cell = str(reading.get("cell"))
        if not cell.startswith("streamedMemory.") or reading.get("runtime") != compared:
            continue
        samples = [_number(value) for value in cast("Sequence[object]", reading.get("samples", ()))]
        arm_medians = [
            statistics.median(samples[index * arm_size : (index + 1) * arm_size])
            for index in range(arm_count)
        ]
        growth = max(arm_medians[1:]) - arm_medians[0]
        if growth > arm_limit:
            failures.append(
                f"{reading.get('workload')}.{cell} grows {growth:.3f} KiB between memory arms"
            )
    return failures


def verify(document: Document, contract: BudgetContract | None = None) -> list[str]:
    """Every reason the required portfolio is not fresh, authoritative, complete,
    published, and within its memory limits.

    A timing ceiling exceeded is not among them: see :func:`advisories`.
    """
    active = contract or BudgetContract.load()
    snapshot, failures = _required_member(document, SNAPSHOT_SUBJECT)
    if snapshot is None:
        return failures
    fresh, freshness = lock_freshness(document)
    if not fresh:
        failures.append(freshness)
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
    failures += _provenance_failures(snapshot, SNAPSHOT_SUBJECT, snapshot_evidence_digest())
    for comparison in cast("Sequence[Document]", snapshot.get("comparisons", ())):
        if comparison.get("outcome") == "within" or comparison.get("unit") in TIMING_UNITS:
            continue
        failures.append(
            f"{comparison.get('workload')}.{comparison.get('cell')} is {comparison.get('outcome')}"
        )
    failures += _scaling_failures(snapshot, active)
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
    failures += _provenance_failures(write, WRITE_SUBJECT, write_report.evidence_digest())
    commits = {
        str(cast("Document", member["provenance"])["commit"]) for member in (snapshot, write)
    }
    if len(commits) != 1:
        failures.append("the snapshot-delivery and write-lowering envelopes name different commits")
    return failures


def advisories(document: Document) -> list[str]:
    """Every timing ceiling the required evidence exceeds, reported and not failed."""
    snapshot = _snapshot(document)
    if snapshot is None:
        return []
    return [
        f"advisory: {comparison.get('workload')}.{comparison.get('cell')} is "
        f"{comparison.get('outcome')} its timing ceiling"
        for comparison in cast("Sequence[Document]", snapshot.get("comparisons", ()))
        if comparison.get("outcome") != "within" and comparison.get("unit") in TIMING_UNITS
    ]


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
    args = parser.parse_args(argv)
    if args.lock_file is not None and args.freshness_only is None:
        parser.error("--lock-file requires --freshness-only")
    if args.freshness_only is not None:
        fresh, freshness = lock_freshness(_load(args.freshness_only), args.lock_file)
        print(freshness)
        return 0 if fresh else 1
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
