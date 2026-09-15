"""Collect every quantitative Python report into one fail-late portfolio."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from jsonschema import ValidationError

from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import Reading, validate
from snapshot_delivery_overhead import (
    comparison as snapshot_comparison,
)
from snapshot_delivery_overhead import (
    expanded_cells,
    is_memory_cell,
    is_scaling_cell,
)
from snapshot_delivery_overhead import (
    operator as snapshot_operator,
)
from snapshot_delivery_overhead import (
    unit as snapshot_unit,
)

WORKSPACE: Final = Path(__file__).resolve().parents[1]
PORTFOLIO_VERSION: Final = 1


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
        "snapshot-delivery",
        required=True,
    ),
    Member("python-report-lifecycle-overhead", "lifecycle_overhead.py", "lifecycle-overhead"),
    Member("python-report-instance-state", "instance_state_overhead.py", "instance-state"),
    Member("python-report-write-lowering", "write_lowering_overhead.py", "write-lowering"),
)


@dataclass(frozen=True, slots=True)
class MemberResult:
    member: Member
    envelope: Mapping[str, object] | None
    failure: str | None = None


type Runner = Callable[[Member], tuple[int, str, str]]


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


def _decoded(member: Member, output: str) -> Mapping[str, object]:
    document = cast("Mapping[str, object]", json.loads(output))
    validate(document)
    if document.get("subject") != member.subject:
        raise ValueError(
            f"{member.recipe} emitted subject {document.get('subject')!r}, "
            f"expected {member.subject!r}"
        )
    if member.subject == "snapshot-delivery":
        validate_snapshot_matrix(document, BudgetContract.load())
    return document


def _matrix(
    documents: Sequence[Mapping[str, object]],
    *,
    label: str,
) -> dict[tuple[str, str], Mapping[str, object]]:
    indexed: dict[tuple[str, str], Mapping[str, object]] = {}
    for document in documents:
        address = (str(document["workload"]), str(document["cell"]))
        if address in indexed:
            raise ValueError(f"duplicate Snapshot {label} {address[0]}.{address[1]}")
        indexed[address] = document
    return indexed


def validate_snapshot_matrix(document: Mapping[str, object], contract: BudgetContract) -> None:
    """Validate the exact contract-derived Snapshot report matrix."""
    cells = expanded_cells(contract)
    expected = {(cell.workload, cell.path): cell for cell in cells}
    readings = _matrix(
        cast("Sequence[Mapping[str, object]]", document["readings"]), label="reading"
    )
    comparisons = _matrix(
        cast("Sequence[Mapping[str, object]]", document["comparisons"]),
        label="comparison",
    )
    for label, actual in (("reading", readings), ("comparison", comparisons)):
        missing = expected.keys() - actual.keys()
        extra = actual.keys() - expected.keys()
        if missing or extra:
            details = [
                *(f"missing {workload}.{cell}" for workload, cell in sorted(missing)),
                *(f"unexpected {workload}.{cell}" for workload, cell in sorted(extra)),
            ]
            raise ValueError(f"Snapshot {label} matrix is not exact: {', '.join(details)}")

    memory_children = contract.memory_children
    scaling_arms = contract.memory_scaling_arms
    for address, cell in expected.items():
        reading_document = readings[address]
        expected_unit = snapshot_unit(cell.path)
        if reading_document["unit"] != expected_unit:
            raise ValueError(
                f"{cell.workload}.{cell.path} reading unit {reading_document['unit']!r}, "
                f"expected {expected_unit!r}"
            )
        samples = tuple(
            _number(value) for value in cast("Sequence[object]", reading_document["samples"])
        )
        sample_count = (
            memory_children * len(scaling_arms)
            if is_scaling_cell(cell.path)
            else memory_children
            if is_memory_cell(cell.path)
            else contract.timing_measured
        )
        if len(samples) != sample_count:
            raise ValueError(
                f"{cell.workload}.{cell.path} has {len(samples)} samples, expected {sample_count}"
            )
        value_samples = samples[:memory_children] if is_scaling_cell(cell.path) else samples
        expected_value = statistics.median(value_samples)
        actual_value = _number(reading_document["value"])
        if actual_value != expected_value:
            raise ValueError(
                f"{cell.workload}.{cell.path} value {actual_value} disagrees with "
                f"sample median {expected_value}"
            )
        reading = Reading(
            cell.workload,
            cell.path,
            actual_value,
            expected_unit,
            samples,
        )
        expected_comparison = snapshot_comparison(cell, reading, contract, complete=True)
        comparison_document = comparisons[address]
        fields = {
            "operator": snapshot_operator(cell.path),
            "limit": float(cell.value),
            "unit": expected_unit,
            "outcome": expected_comparison.outcome,
        }
        for name, expected_value in fields.items():
            if comparison_document[name] != expected_value:
                raise ValueError(
                    f"{cell.workload}.{cell.path} comparison {name} "
                    f"{comparison_document[name]!r}, expected {expected_value!r}"
                )


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


def _summary(document: Mapping[str, object]) -> str:
    members = cast("Sequence[Mapping[str, object]]", document.get("members", ()))
    failures = cast("Sequence[Mapping[str, object]]", document.get("failures", ()))
    lines = [
        "# Python cost report",
        "",
        "| Subject | Authority | Readings | Within | Outside | Unavailable |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for member in members:
        comparisons = cast("Sequence[Mapping[str, object]]", member.get("comparisons", ()))
        outcomes = [comparison.get("outcome") for comparison in comparisons]
        lines.append(
            f"| {member.get('subject')} | {member.get('authority')} | "
            f"{len(cast('Sequence[object]', member.get('readings', ())))} | "
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


def _snapshots(document: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    members = cast("Sequence[Mapping[str, object]]", document.get("members", ()))
    return tuple(member for member in members if member.get("subject") == "snapshot-delivery")


def _snapshot(document: Mapping[str, object]) -> Mapping[str, object] | None:
    snapshots = _snapshots(document)
    return snapshots[0] if len(snapshots) == 1 else None


def lock_freshness(
    document: Mapping[str, object], lock_path: Path | None = None
) -> tuple[bool, str]:
    """Compare retained dependencies with a lock file without reclassifying authority."""
    snapshot = _snapshot(document)
    if snapshot is None:
        return False, "lock freshness unavailable: expected one snapshot-delivery envelope"
    provenance = snapshot.get("provenance")
    if not isinstance(provenance, Mapping):
        return False, "lock freshness unavailable: snapshot-delivery provenance is not a mapping"
    recorded = cast("Mapping[str, object]", provenance).get("lockDigest")
    inspected = lock_path or WORKSPACE / "uv.lock"
    current = hashlib.sha256(inspected.read_bytes()).hexdigest()
    digests = f"recorded lockDigest={recorded}; inspected lockDigest={current} ({inspected})"
    if recorded != current:
        return False, f"stale snapshot-delivery evidence: {digests}"
    return True, f"snapshot-delivery lock freshness matches: {digests}"


def verify(document: Mapping[str, object], contract: BudgetContract | None = None) -> list[str]:
    """Return every reason the required portfolio is not fresh, authoritative, and within."""
    active = contract or BudgetContract.load()
    snapshots = _snapshots(document)
    if not snapshots:
        return ["the portfolio has no required snapshot-delivery envelope"]
    if len(snapshots) != 1:
        return ["the portfolio has more than one snapshot-delivery envelope"]
    snapshot = snapshots[0]
    fresh, freshness = lock_freshness(document)
    failures: list[str] = [] if fresh else [freshness]
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
    comparisons = cast("Sequence[Mapping[str, object]]", snapshot.get("comparisons", ()))
    for comparison in comparisons:
        if comparison.get("outcome") != "within":
            failures.append(
                f"{comparison.get('workload')}.{comparison.get('cell')} is "
                f"{comparison.get('outcome')}"
            )
    memory = cast("Mapping[str, object]", active.sampling["memory"])
    arm_limit = _number(memory["armGrowthMaxKiB"])
    arm_size = active.memory_children
    arm_count = len(active.memory_scaling_arms)
    readings = cast("Sequence[Mapping[str, object]]", snapshot.get("readings", ()))
    for reading in readings:
        cell = str(reading.get("cell"))
        samples = [_number(value) for value in cast("Sequence[object]", reading.get("samples", ()))]
        if not cell.startswith("streamedMemory."):
            continue
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


def compare(base: Mapping[str, object], head: Mapping[str, object]) -> str:
    """Render advisory directional deltas between two portfolio documents."""
    base_snapshot = _snapshot(base)
    head_snapshot = _snapshot(head)
    lines = ["# Python cost report comparison", ""]
    if base_snapshot is None or head_snapshot is None:
        return (
            "\n".join([*lines, "A Snapshot delivery envelope is unavailable on one side."]) + "\n"
        )
    base_readings = {
        (reading.get("workload"), reading.get("cell")): reading
        for reading in cast("Sequence[Mapping[str, object]]", base_snapshot.get("readings", ()))
    }
    lines += [
        "| Workload | Cell | Base | Head | Delta |",
        "|---|---|---:|---:|---:|",
    ]
    for reading in cast("Sequence[Mapping[str, object]]", head_snapshot.get("readings", ())):
        key = (reading.get("workload"), reading.get("cell"))
        previous = base_readings.get(key)
        if previous is None:
            continue
        base_value = _number(previous["value"])
        head_value = _number(reading["value"])
        lines.append(
            f"| {key[0]} | {key[1]} | {base_value:.3f} | {head_value:.3f} | "
            f"{head_value - base_value:+.3f} {reading.get('unit')} |"
        )
    lines += ["", "Deltas are advisory and never ratchet the Budget Contract."]
    return "\n".join(lines) + "\n"


def _load(path: Path) -> Mapping[str, object]:
    return cast("Mapping[str, object]", json.loads(path.read_text(encoding="utf-8")))


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
