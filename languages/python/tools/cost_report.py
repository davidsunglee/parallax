"""Collect every quantitative Python report into one fail-late portfolio."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import Diagnostic, validate

REPO: Final = Path(__file__).resolve().parents[3]
WORKSPACE: Final = Path(__file__).resolve().parents[1]
PORTFOLIO_VERSION: Final = 1


@dataclass(frozen=True, slots=True)
class Member:
    recipe: str
    script: str
    subject: str
    required: bool = False
    envelope: bool = False


MEMBERS: Final = (
    Member(
        "python-report-snapshot-delivery",
        "snapshot_delivery_overhead.py",
        "snapshot-delivery",
        required=True,
        envelope=True,
    ),
    Member("python-report-lifecycle-overhead", "lifecycle_overhead.py", "lifecycle-overhead"),
    Member("python-report-instance-state", "instance_state_overhead.py", "instance-state"),
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
    return document


def legacy_envelope(
    member: Member,
    provenance: Mapping[str, object],
    authority: object,
    output: str,
) -> Mapping[str, object]:
    diagnostic = Diagnostic(
        "legacy-evidence-report",
        f"{member.recipe} remains text evidence; its successful output is retained separately",
    )
    document: dict[str, object] = {
        "schemaVersion": 1,
        "subject": member.subject,
        "provenance": dict(provenance),
        "authority": authority,
        "readings": [],
        "comparisons": [],
        "incomplete": [diagnostic.__dict__]
        if hasattr(diagnostic, "__dict__")
        else [{"code": diagnostic.code, "message": diagnostic.message}],
        "errors": [],
    }
    validate(document)
    return document


def collect(runner: Runner = run_member) -> tuple[list[MemberResult], bool]:
    """Attempt every member and fail only after required envelope validation."""
    results: list[MemberResult] = []
    provenance: Mapping[str, object] | None = None
    authority: object = "non-authoritative"
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
            if member.envelope:
                envelope = _decoded(member, stdout)
                provenance = cast("Mapping[str, object]", envelope["provenance"])
                authority = envelope["authority"]
            elif provenance is None:
                raise ValueError("the required Snapshot delivery envelope supplied no provenance")
            else:
                envelope = legacy_envelope(member, provenance, authority, stdout)
            results.append(MemberResult(member, envelope))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
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


def _snapshot(document: Mapping[str, object]) -> Mapping[str, object] | None:
    members = cast("Sequence[Mapping[str, object]]", document.get("members", ()))
    return next(
        (member for member in members if member.get("subject") == "snapshot-delivery"), None
    )


def verify(document: Mapping[str, object], contract: BudgetContract | None = None) -> list[str]:
    """Return every reason the required portfolio is not authoritative and within."""
    active = contract or BudgetContract.load()
    snapshot = _snapshot(document)
    if snapshot is None:
        return ["the portfolio has no required snapshot-delivery envelope"]
    failures: list[str] = []
    try:
        validate(snapshot)
    except (KeyError, TypeError, ValueError) as error:
        return [f"the snapshot-delivery envelope is invalid: {error}"]
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
    readings = cast("Sequence[Mapping[str, object]]", snapshot.get("readings", ()))
    for reading in readings:
        cell = str(reading.get("cell"))
        samples = [_number(value) for value in cast("Sequence[object]", reading.get("samples", ()))]
        if not cell.startswith("streamedMemory.") or len(samples) != 6:
            continue
        growth = statistics.median(samples[3:]) - statistics.median(samples[:3])
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
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BASE", "HEAD"))
    args = parser.parse_args(argv)
    if args.verify is not None:
        failures = verify(_load(args.verify))
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
