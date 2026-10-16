"""Run one checkpoint's drivers against each of its arms and keep what they report.

An arm is a package source and an isolation level, spelled ``<ref>[@<level>]``.
Each arm gets a detached git worktree at its commit; every driver of the
checkpoint runs from this directory under that worktree's own locked Python
environment (``uv run --frozen --project <worktree>/languages/python``), so the
current drivers measure the arm's packages.

A retained capture refuses to start unless the preflight passes — a clean tree,
resolvable refs, an idle machine, and a reachable Docker daemon. Each driver's
full report, with its per-invocation and per-sample arrays, goes under
``--raw-dir``, outside the repository; ``captures/<checkpoint>/<arm>/`` keeps
each report reduced to its summaries beside a ``provenance.json`` that records
every full report's size and digest. ``--smoke`` runs every driver with tiny
samples, skips the preflight, and keeps nothing: it checks that the tooling
still runs against an arm. ``--verify`` checks a retained capture: complete
provenance, reduced reports, arms that differ only in their commit or
isolation, and the size budget.
"""

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
RESEARCH = SCRIPTS.parent
REPO = RESEARCH.parents[2]
CAPTURES = RESEARCH / "captures"
RAW_CAPTURES = Path.home() / ".local/share/parallax/evidence/cor-214/transaction-isolation-captures"
SIZE_BUDGET_BYTES = 1024 * 1024
IDLE_LOAD_PER_CORE = 0.25
LEVELS = ("read_committed", "repeatable_read")


Report = dict[str, Any]


def _percentiles(values: Sequence[float]) -> dict[str, float | None]:
    # The drivers' own summary statistic, `_support.percentiles`.
    if not values:
        return {"p50": None, "p95": None, "p99": None}
    if len(values) == 1:
        return {"p50": values[0], "p95": values[0], "p99": values[0]}
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return {"p50": cuts[49], "p95": cuts[94], "p99": cuts[98]}


def _span(values: Sequence[float]) -> dict[str, float] | None:
    return {"min": min(values), "max": max(values)} if values else None


def _invocation_figures(samples: list[Report]) -> Report:
    """Failure counts and spans, and the nearest-rank p99 time to success, which
    scores a failed invocation as unbounded and is ``None`` when unbounded."""
    failed = [sample for sample in samples if sample["outcome"] != "committed"]
    to_success = sorted(
        float(sample["latencyMs"]) if sample["outcome"] == "committed" else math.inf
        for sample in samples
    )
    p99 = to_success[math.ceil(0.99 * len(to_success)) - 1] if to_success else math.inf
    return {
        "surfacedFailures": dict(
            Counter(
                f"{outcome['type']}:{outcome['category']}:{outcome['nativeCode']}"
                for outcome in (sample["outcome"] for sample in failed)
            )
        ),
        "surfacedFailureAttempts": _span([int(sample["attempts"]) for sample in failed]),
        "surfacedFailureLatencyMs": _span([float(sample["latencyMs"]) for sample in failed]),
        "p99ToSuccessMs": None if math.isinf(p99) else p99,
    }


def _reduce_contention(report: Report) -> None:
    for run in report["runs"]:
        if (samples := run.pop("samples", None)) is not None:
            run["summary"].update(_invocation_figures(samples))


def _reduce_guard_wal(report: Report) -> None:
    for replay in report["replay"]:
        if (samples := replay.pop("samples", None)) is not None:
            replay["summary"].update(_invocation_figures(samples))
    for mode in report["wal"]:
        mode.pop("samples", None)


def _reduce_end_to_end_writes(report: Report) -> None:
    for result in report["results"]:
        result.pop("latenciesMs", None)
        if isinstance(counts := result["summary"].get("statementsPerInvocation"), list):
            result["summary"]["statementsPerInvocation"] = {
                str(count): invocations for count, invocations in sorted(Counter(counts).items())
            }
        if (shapes := result.pop("shapes", None)) is None:
            continue
        statements: list[object] = []
        for shape in shapes:
            if shape["statements"] not in statements:
                statements.append(shape["statements"])
        result["summary"].update(
            {
                "shapedPeakBytes": _percentiles([shape["peakBytes"] for shape in shapes]),
                "shapedNetBytes": _percentiles([shape["netBytes"] for shape in shapes]),
                "shapedStatements": statements,
            }
        )


def _reduce_stream_churn(report: Report) -> None:
    for run in report["runs"]:
        run.pop("timeline", None)


def _reduce_lock_snapshot_trace(report: Report) -> None:
    for trace in report["traces"]:
        trace.pop("checkpoints", None)
        trace.pop("statements", None)


def _reduce_read_retention(report: Report) -> None:
    for run in report["runs"]:
        run["memory"].pop("heldBytes", None)
        run["memory"].pop("peakBytes", None)
        run["timing"].pop("elapsedS", None)
        run["timing"].pop("firstRootS", None)


def _reduce_snapshot_delivery(report: Report) -> None:
    for reading in report["readings"]:
        reading.pop("samples", None)


@dataclass(frozen=True, slots=True)
class Driver:
    """A command an arm runs: a script of this directory, or a tool of the arm's
    own Python tree. A script takes ``--isolation``, ``--out``, and
    ``--smoke``, after the ``options`` a checkpoint runs it with; a tool takes
    the arguments its evidence or smoke run needs. ``reduce`` drops a full
    report's per-invocation and per-sample arrays in place, summarizing what
    the research notes quote from them."""

    name: str
    reduce: Callable[[Report], None]
    tool: tuple[str, ...] = ()
    smoke_tool: tuple[str, ...] = ()
    options: tuple[str, ...] = ()

    def command(self, arm: "Arm", out: Path, *, smoke: bool) -> list[str]:
        if not self.tool:
            command = [
                str(SCRIPTS / f"{self.name}.py"),
                *self.options,
                "--isolation",
                arm.isolation,
                "--out",
                str(out),
            ]
            return [*command, "--smoke"] if smoke else command
        if smoke:
            return list(self.smoke_tool)
        return [*self.tool, "--out", str(out)]

    def retained(self, report: Report) -> Report:
        reduced = copy.deepcopy(report)
        self.reduce(reduced)
        return reduced


LOCK_SNAPSHOT_TRACE = Driver("lock_snapshot_trace", _reduce_lock_snapshot_trace)
CONTENTION = Driver("contention", _reduce_contention)
# The default-bound writers once per backoff candidate, for the checkpoint that
# selects the backoff.
CONTENTION_BACKOFF_GRID = Driver("contention", _reduce_contention, options=("--backoff-grid",))
GUARD_WAL = Driver("guard_wal", _reduce_guard_wal)
# The writers and the guard/guard replay alone, in every simulated environment,
# the default bound once per replay policy, for the checkpoint that tests
# whether the backoff carries across environments.
CONTENTION_ENVIRONMENTS = Driver("contention", _reduce_contention, options=("--environments",))
GUARD_REPLAY_ENVIRONMENTS = Driver("guard_wal", _reduce_guard_wal, options=("--environments",))
STREAM_CHURN = Driver("stream_churn", _reduce_stream_churn)
# Writable and read-only transaction-held streams side by side in one arm, for
# the checkpoints whose every arm has read-only transactions.
STREAM_CHURN_READ_ONLY = Driver("stream_churn", _reduce_stream_churn, options=("--read-only",))
END_TO_END_WRITES = Driver("end_to_end_writes", _reduce_end_to_end_writes)
# Standalone and read-only eager and streamed reads, for the checkpoints whose
# every arm has read-only transactions.
READ_RETENTION = Driver("read_retention", _reduce_read_retention)
SNAPSHOT_DELIVERY = Driver(
    "snapshot_delivery",
    _reduce_snapshot_delivery,
    tool=(
        "tools/snapshot_delivery_overhead.py",
        "--workload",
        "conventional-fanout",
        "--workload",
        "versioned-document",
        "--workload",
        "bitemporal-current",
    ),
    smoke_tool=(
        "tools/snapshot_delivery_overhead.py",
        "--diagnostic",
        "--select",
        "conventional-fanout",
        "--runtime",
        f"{sys.version_info.major}.{sys.version_info.minor}",
    ),
)


@dataclass(frozen=True, slots=True)
class Checkpoint:
    attribution: str
    drivers: tuple[Driver, ...]
    arms: tuple[str, ...] = ()


C0_SOURCE = "7b465769dc87521c758a06d3d1fbfe3f55edba92"
C7_SOURCE = "0581fd3959c3a1996edad08f8141f7dc7d36c851"
CHECKPOINTS: dict[str, Checkpoint] = {
    "C0": Checkpoint(
        "current behavior at explicit Read Committed and Repeatable Read, and the "
        "delivery, selective-retry, and immediate-replay baselines",
        (LOCK_SNAPSHOT_TRACE, CONTENTION, GUARD_WAL, STREAM_CHURN, END_TO_END_WRITES),
        (f"{C0_SOURCE}@read_committed", f"{C0_SOURCE}@repeatable_read"),
    ),
    "C1": Checkpoint("writable versus read-only reads at one isolation", (STREAM_CHURN_READ_ONLY,)),
    "C2": Checkpoint(
        "existing versus strict source admission, evidence retained", (END_TO_END_WRITES,)
    ),
    "C3": Checkpoint(
        "selective versus automatic optimistic replay at Read Committed",
        (CONTENTION, LOCK_SNAPSHOT_TRACE),
    ),
    "C4": Checkpoint(
        "immediate replay versus bounded randomized backoff",
        (CONTENTION_BACKOFF_GRID, GUARD_WAL),
    ),
    "C5": Checkpoint(
        "standalone and read-only reads before and after evidence removal",
        (SNAPSHOT_DELIVERY, STREAM_CHURN_READ_ONLY, READ_RETENTION),
    ),
    "C6": Checkpoint(
        "the C0 source versus the final design",
        (
            LOCK_SNAPSHOT_TRACE,
            CONTENTION,
            GUARD_WAL,
            STREAM_CHURN,
            END_TO_END_WRITES,
            SNAPSHOT_DELIVERY,
        ),
    ),
    "C7": Checkpoint(
        "fixed versus duration-scaled replay backoff across simulated environments",
        (CONTENTION_ENVIRONMENTS, GUARD_REPLAY_ENVIRONMENTS),
        (f"{C7_SOURCE}@read_committed", f"{C7_SOURCE}@repeatable_read"),
    ),
}


@dataclass(frozen=True, slots=True)
class Arm:
    ref: str
    isolation: str
    commit: str = ""

    @classmethod
    def parse(cls, text: str) -> "Arm":
        ref, _, level = text.partition("@")
        level = level or "read_committed"
        if level not in LEVELS:
            raise SystemExit(f"arm {text!r}: the level must be one of {', '.join(LEVELS)}")
        return cls(ref, level)

    @property
    def label(self) -> str:
        return f"{(self.commit or self.ref)[:12]}-{self.isolation}"


def _git(*args: str, cwd: Path = REPO) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sysctl(name: str) -> str | None:
    if sys.platform != "darwin":
        return None
    completed = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=False)
    return completed.stdout.strip() or None


def machine() -> dict[str, object]:
    memory = _sysctl("hw.memsize")
    return {
        "model": _sysctl("hw.model") or platform.machine(),
        "cpu": _sysctl("machdep.cpu.brand_string") or platform.processor() or "unknown",
        "cores": os.cpu_count(),
        "ramGiB": round(int(memory) / 1024**3) if memory else None,
        "os": platform.platform(),
    }


def preflight(arms: Sequence[Arm]) -> list[Arm]:
    problems: list[str] = []
    if _git("status", "--porcelain"):
        problems.append("the working tree is not clean")
    resolved: list[Arm] = []
    for arm in arms:
        try:
            commit = _git("rev-parse", "--verify", f"{arm.ref}^{{commit}}")
        except subprocess.CalledProcessError:
            problems.append(f"arm {arm.ref!r} names no commit")
            continue
        resolved.append(Arm(arm.ref, arm.isolation, commit))
    load = os.getloadavg()[0]
    ceiling = IDLE_LOAD_PER_CORE * (os.cpu_count() or 1)
    if load >= ceiling:
        problems.append(
            f"the 1-minute load average {load:.2f} is not below the idle ceiling {ceiling:.2f}"
        )
    if subprocess.run(["docker", "info"], capture_output=True, check=False).returncode != 0:
        problems.append("Docker is not reachable")
    if problems:
        raise SystemExit("preflight refused the capture:\n  " + "\n  ".join(problems))
    return resolved


@contextmanager
def worktree(arm: Arm, parent: Path) -> Iterator[Path]:
    path = parent / arm.label
    _git("worktree", "add", "--detach", str(path), arm.commit or arm.ref)
    try:
        yield path
    finally:
        _git("worktree", "remove", "--force", str(path))


def run_driver(
    driver: Driver, arm: Arm, tree: Path, raw: Path, out: Path, *, smoke: bool
) -> dict[str, object]:
    project = tree / "languages" / "python"
    command = [
        "uv",
        "run",
        "--frozen",
        "--project",
        str(project),
        "python",
        *driver.command(arm, raw, smoke=smoke),
    ]
    environment = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    started = time.perf_counter()
    completed = subprocess.run(
        command, cwd=project, env=environment, capture_output=True, text=True, check=False
    )
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        failure = f"{driver.name} failed against {arm.label} ({completed.returncode})"
        raise SystemExit(f"{failure}:\n{completed.stderr[-4000:]}")
    if driver.tool and smoke:
        raw.write_text(completed.stdout)
    record: dict[str, object] = {
        "command": command[6:],
        "elapsedS": round(elapsed, 3),
        "bytes": raw.stat().st_size,
        "sha256": _digest(raw),
    }
    if not (driver.tool and smoke):
        report = json.loads(raw.read_text())
        record["conditions"] = tool_conditions(report) if driver.tool else report.get("conditions")
        out.write_text(json.dumps(driver.retained(report), indent=2, sort_keys=True) + "\n")
    return record


# What an arm tool's own provenance states about its arm rather than about the
# conditions it measured under.
ARM_FACTS = ("commit", "lockDigest", "budgetContract")


def tool_conditions(envelope: dict[str, object]) -> dict[str, object] | None:
    provenance = envelope.get("provenance")
    if not isinstance(provenance, dict):
        return None
    return {key: value for key, value in provenance.items() if key not in ARM_FACTS}


def capturing_tree() -> dict[str, object]:
    """The tree the drivers run from, read once before any arm writes into it."""
    return {
        "commit": _git("rev-parse", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
        "scripts": {path.name: _digest(path) for path in sorted(SCRIPTS.glob("*.py"))},
    }


def provenance(
    checkpoint: str,
    arm: Arm,
    tree: Path,
    source: dict[str, object],
    drivers: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "checkpoint": checkpoint,
        "attribution": CHECKPOINTS[checkpoint].attribution,
        "arm": {"ref": arm.ref, "commit": arm.commit, "isolation": arm.isolation},
        "lockDigest": _digest(tree / "languages" / "python" / "uv.lock"),
        "capture": source,
        "machine": machine(),
        "loadAverage": list(os.getloadavg()),
        "capturedAt": dt.datetime.now(dt.UTC).isoformat(),
        "drivers": drivers,
    }


def capture(checkpoint: str, arms: Sequence[Arm], raw_root: Path, *, smoke: bool) -> None:
    spec = CHECKPOINTS[checkpoint]
    source = capturing_tree()
    with tempfile.TemporaryDirectory(prefix=f"parallax-{checkpoint}-") as scratch:
        parent = Path(scratch)
        for arm in arms:
            resolved = (
                arm
                if arm.commit
                else Arm(
                    arm.ref, arm.isolation, _git("rev-parse", "--verify", f"{arm.ref}^{{commit}}")
                )
            )
            target = (
                parent / "out" / resolved.label if smoke else CAPTURES / checkpoint / resolved.label
            )
            raw = (parent / "raw" if smoke else raw_root / checkpoint) / resolved.label
            target.mkdir(parents=True, exist_ok=smoke)
            raw.mkdir(parents=True, exist_ok=smoke)
            with worktree(resolved, parent) as tree:
                records = {
                    driver.name: run_driver(
                        driver,
                        resolved,
                        tree,
                        raw / f"{driver.name}.json",
                        target / f"{driver.name}.json",
                        smoke=smoke,
                    )
                    for driver in spec.drivers
                }
                document = provenance(checkpoint, resolved, tree, source, records)
            (target / "provenance.json").write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n"
            )
            for name, record in records.items():
                elapsed, size = record["elapsedS"], record["bytes"]
                print(f"{checkpoint} {resolved.label} {name}: {elapsed}s, {size} bytes")
    if smoke:
        print(f"{checkpoint} smoke passed for {len(arms)} arm(s); nothing was retained")


def _comparable(document: dict[str, object]) -> dict[str, object]:
    drivers = document.get("drivers")
    conditions = {}
    if isinstance(drivers, dict):
        for name, record in drivers.items():
            facts = dict(record.get("conditions") or {})
            facts.pop("isolation", None)
            conditions[name] = facts
    capture_facts = document.get("capture") or {}
    return {
        "machine": document.get("machine"),
        "scripts": capture_facts.get("scripts") if isinstance(capture_facts, dict) else None,
        "conditions": conditions,
    }


REQUIRED = ("checkpoint", "arm", "lockDigest", "capture", "machine", "capturedAt", "drivers")


def _arm_problems(checkpoint: str, arm: Path) -> tuple[list[str], dict[str, object] | None]:
    source = arm / "provenance.json"
    if not source.is_file():
        return [f"{arm.name}: no provenance.json"], None
    document = json.loads(source.read_text())
    problems = [f"{arm.name}: provenance lacks {key}" for key in REQUIRED if key not in document]
    if (document.get("capture") or {}).get("dirty"):
        problems.append(f"{arm.name}: captured from a dirty tree")
    for driver in CHECKPOINTS[checkpoint].drivers:
        report = arm / f"{driver.name}.json"
        if not report.is_file():
            problems.append(f"{arm.name}: no report from {driver.name}")
            continue
        content = json.loads(report.read_text())
        if driver.retained(content) != content:
            problems.append(f"{arm.name}: {driver.name} keeps raw samples")
    drivers = document.get("drivers")
    records = drivers if isinstance(drivers, dict) else {}
    problems.extend(
        f"{arm.name}: {driver.name} recorded no measurement conditions"
        for driver in CHECKPOINTS[checkpoint].drivers
        if not (records.get(driver.name) or {}).get("conditions")
    )
    return problems, document


def _pairing_problems(documents: dict[str, dict[str, object]]) -> list[str]:
    problems: list[str] = []
    comparable = {name: _comparable(document) for name, document in documents.items()}
    if comparable:
        (first_name, first), *rest = comparable.items()
        problems.extend(
            f"{name} differs from {first_name} in {key}, not only in commit or isolation"
            for name, facts in rest
            for key in facts
            if facts[key] != first[key]
        )
    arms = [
        (document["arm"]["commit"], document["arm"]["isolation"]) for document in documents.values()
    ]
    if len(set(arms)) != len(arms):
        problems.append("two arms name the same commit and isolation")
    return problems


def verify(checkpoint: str) -> int:
    root = CAPTURES / checkpoint
    arms = sorted(path for path in root.iterdir() if path.is_dir()) if root.is_dir() else []
    problems: list[str] = []
    if len(arms) < 2:
        problems.append(f"{root} holds {len(arms)} arm(s); a checkpoint pairs at least two")
    documents: dict[str, dict[str, object]] = {}
    for arm in arms:
        found, document = _arm_problems(checkpoint, arm)
        problems.extend(found)
        if document is not None:
            documents[arm.name] = document
    problems.extend(_pairing_problems(documents))
    size = (
        sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
        if root.is_dir()
        else 0
    )
    if size > SIZE_BUDGET_BYTES:
        problems.append(f"{root} holds {size} bytes, over the {SIZE_BUDGET_BYTES}-byte budget")
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print(f"{checkpoint}: {len(arms)} arms verified, {size} bytes")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("checkpoint", choices=sorted(CHECKPOINTS))
    parser.add_argument(
        "--arm", action="append", default=[], help="<ref>[@read_committed|@repeatable_read]"
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=RAW_CAPTURES,
        help=f"where full driver reports go (default {RAW_CAPTURES})",
    )
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        return verify(args.checkpoint)
    texts = args.arm or list(CHECKPOINTS[args.checkpoint].arms)
    if len(texts) < 2:
        parser.error(f"{args.checkpoint} has no recorded arms; name each with --arm")
    arms = [Arm.parse(text) for text in texts]
    if not args.smoke:
        arms = preflight(arms)
        for existing in (CAPTURES / args.checkpoint, args.raw_dir / args.checkpoint):
            if existing.exists() and any(existing.iterdir()):
                parser.error(f"{existing} already holds a capture; remove it to recapture")
    if shutil.which("uv") is None:
        parser.error("uv is not on PATH")
    capture(args.checkpoint, arms, args.raw_dir, smoke=args.smoke)
    return 0


if __name__ == "__main__":
    sys.exit(main())
