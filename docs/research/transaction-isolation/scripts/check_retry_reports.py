"""Checks the fixed-name reports of the authored retry smokes.

Reads ``grid.json``, ``environments.json``, ``guard-normal.json``, and
``guard-environments.json`` from ``--smoke-dir``, the outputs of ``contention.py``
and ``guard_wal.py`` run with ``--smoke``, and exits nonzero on a structural or
functional failure: a run matrix of the wrong shape, a policy not stated whole,
a sample count off the smoke's load, an attempt past its policy's bound, or a
failure of the drivers' own use of the API. It provisions nothing, and judges no
timing percentile or conflict count, because a smoke's are not evidence.
"""

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

KEY_MODES = ("hot", "disjoint")
ENVIRONMENTS = ("local", "rtt-2ms", "rtt-5ms+think")
GRID_BASES_MS = (0.5, 2, 8)
GRID_CAPS_MS = (25, 100, 400)

BUILT_IN_BACKOFF = {"baseDelay": 0.008, "maxDelay": 1.0}
DISABLED = {"maxRetries": 0, "backoff": BUILT_IN_BACKOFF}
DEFAULT = {"maxRetries": 10, "backoff": BUILT_IN_BACKOFF}

SMOKE_WRITERS = 2
SMOKE_INVOCATIONS = 3
SMOKE_BALANCES = 3
WAL_MODES = 3
SAMPLES_PER_RUN = SMOKE_WRITERS * SMOKE_INVOCATIONS

API_FAILURES = frozenset(
    {
        "AttributeError",
        "ImportError",
        "ModuleNotFoundError",
        "NameError",
        "TypeError",
        "ValueError",
    }
)
"""What a driver's own misuse of the public API surfaces as, unlike the conflicts
its workload exists to provoke."""

RETIRED_RUN_FIELDS = ("maxRetries", "backoff", "replayWaits")


def _grid_policies() -> dict[str, dict[str, object]]:
    return {
        f"adaptive-{base:g}/{cap:g}": {
            "maxRetries": 10,
            "backoff": {"baseDelay": base / 1000, "maxDelay": cap / 1000},
        }
        for base in GRID_BASES_MS
        for cap in GRID_CAPS_MS
    }


def _policy_problems(where: str, policy: object) -> Iterator[str]:
    if not isinstance(policy, Mapping) or set(policy) != {"maxRetries", "backoff"}:
        yield f"{where}: retry must state maxRetries and backoff, got {policy!r}"
        return
    bound = policy["maxRetries"]
    if type(bound) is not int or bound < 0:
        yield f"{where}: maxRetries must be a nonnegative integer, got {bound!r}"
    backoff = policy["backoff"]
    if not isinstance(backoff, Mapping) or set(backoff) != {"baseDelay", "maxDelay"}:
        yield f"{where}: backoff must state baseDelay and maxDelay, got {backoff!r}"
        return
    delays = (backoff["baseDelay"], backoff["maxDelay"])
    if not all(isinstance(delay, int | float) and math.isfinite(delay) for delay in delays):
        yield f"{where}: delays must be finite numbers, got {backoff!r}"
    elif not 0 < delays[0] <= delays[1]:
        yield f"{where}: delays must satisfy 0 < baseDelay <= maxDelay, got {backoff!r}"


def _run_problems(where: str, run: Mapping[str, Any], expected: object) -> Iterator[str]:
    """What is wrong with one replay run measured under the ``expected`` policy."""
    policy = run.get("retry")
    yield from _policy_problems(where, policy)
    if policy != expected:
        yield f"{where}: ran under {policy!r}, expected {expected!r}"
    for retired in RETIRED_RUN_FIELDS:
        if retired in run:
            yield f"{where}: states {retired}, which the driver no longer observes"
    samples = run.get("samples")
    if not isinstance(samples, list):
        yield f"{where}: states no samples"
        return
    if len(samples) != SAMPLES_PER_RUN:
        yield f"{where}: holds {len(samples)} samples, expected {SAMPLES_PER_RUN}"
    if run.get("summary", {}).get("invocations") != len(samples):
        yield f"{where}: its summary counts other invocations than its {len(samples)} samples"
    bound = policy.get("maxRetries") if isinstance(policy, Mapping) else None
    for index, sample in enumerate(samples):
        yield from _sample_problems(f"{where} sample {index}", sample, bound)


def _sample_problems(where: str, sample: Mapping[str, Any], bound: object) -> Iterator[str]:
    attempts = sample.get("attempts")
    if type(attempts) is not int or attempts < 1:
        yield f"{where}: attempts must be a positive integer, got {attempts!r}"
    elif type(bound) is int and attempts > bound + 1:
        yield f"{where}: made {attempts} attempts, past the bound {bound}"
    outcome = sample.get("outcome")
    if outcome == "committed":
        return
    if not isinstance(outcome, Mapping):
        yield f"{where}: outcome must be committed or a failure, got {outcome!r}"
    elif outcome.get("type") in API_FAILURES:
        yield f"{where}: failed with {outcome.get('type')}, the driver's own API use"


def _matrix_problems(
    name: str, actual: Sequence[tuple[object, ...]], expected: Sequence[tuple[object, ...]]
) -> Iterator[str]:
    if Counter(actual) != Counter(expected):
        yield f"{name}: ran {sorted(map(repr, actual))}, expected {sorted(map(repr, expected))}"


def _workload_problems(
    name: str, report: Mapping[str, Any], driver: str, expected: Mapping[str, object]
) -> Iterator[str]:
    if report.get("driver") != driver:
        yield f"{name}: driver is {report.get('driver')!r}, expected {driver!r}"
    workload = report.get("conditions", {}).get("workload", {})
    for field, value in expected.items():
        if workload.get(field) != value:
            yield f"{name}: workload {field} is {workload.get(field)!r}, expected {value!r}"


_CONTENTION_LOAD = {"workers": SMOKE_WRITERS, "invocationsPerWorker": SMOKE_INVOCATIONS}
_GUARD_LOAD = {
    "writers": SMOKE_WRITERS,
    "invocationsPerWriter": SMOKE_INVOCATIONS,
    "balances": SMOKE_BALANCES,
}


def check_grid(report: Mapping[str, Any]) -> list[str]:
    """Two disabled-policy runs, then nine adaptive candidates over both key modes."""
    policies: dict[str, object] = {"disabled": DISABLED, **_grid_policies()}
    runs = report.get("runs", [])
    problems = list(_workload_problems("grid.json", report, "contention", _CONTENTION_LOAD))
    expected = [(label, keys) for label in policies for keys in KEY_MODES]
    actual = [(run.get("policy"), run.get("keys")) for run in runs]
    problems.extend(_matrix_problems("grid.json", actual, expected))
    for index, run in enumerate(runs):
        where = f"grid.json run {index}"
        problems.extend(_run_problems(where, run, policies.get(run.get("policy"))))
    return problems


def check_environments(report: Mapping[str, Any]) -> list[str]:
    """Disabled and default policies over both key modes in every environment."""
    policies: dict[str, object] = {"disabled": DISABLED, "default": DEFAULT}
    runs = report.get("runs", [])
    name = "environments.json"
    problems = list(_workload_problems(name, report, "contention", _CONTENTION_LOAD))
    expected = [
        (environment, label, keys)
        for environment in ENVIRONMENTS
        for label in policies
        for keys in KEY_MODES
    ]
    actual = [(run.get("environment"), run.get("policy"), run.get("keys")) for run in runs]
    problems.extend(_matrix_problems(name, actual, expected))
    for index, run in enumerate(runs):
        where = f"{name} run {index}"
        problems.extend(_run_problems(where, run, policies.get(run.get("policy"))))
    return problems


def check_guard_normal(report: Mapping[str, Any]) -> list[str]:
    """The WAL workload, then the guard replay under disabled and default policies."""
    policies: dict[str, object] = {"disabled": DISABLED, "default": DEFAULT}
    name = "guard-normal.json"
    wal = report.get("wal", [])
    replay = report.get("replay", [])
    problems = list(_workload_problems(name, report, "guard_wal", _GUARD_LOAD))
    if len(wal) != WAL_MODES:
        problems.append(f"{name}: ran {len(wal)} WAL modes, expected {WAL_MODES}")
    for mode in wal:
        writes = mode.get("summary", {}).get("writes")
        if writes != SMOKE_BALANCES:
            problems.append(
                f"{name}: WAL mode {mode.get('mode')!r} wrote {writes!r}, expected {SMOKE_BALANCES}"
            )
    actual = [(run.get("policy"),) for run in replay]
    problems.extend(_matrix_problems(name, actual, [(label,) for label in policies]))
    for index, run in enumerate(replay):
        where = f"{name} replay {index}"
        problems.extend(_run_problems(where, run, policies.get(run.get("policy"))))
    return problems


def check_guard_environments(report: Mapping[str, Any]) -> list[str]:
    """Only the guard replay, under disabled and default policies in every environment."""
    policies: dict[str, object] = {"disabled": DISABLED, "default": DEFAULT}
    name = "guard-environments.json"
    replay = report.get("replay", [])
    problems = list(_workload_problems(name, report, "guard_wal", _GUARD_LOAD))
    if report.get("wal"):
        problems.append(f"{name}: ran the WAL workload, which --environments omits")
    expected = [(environment, label) for environment in ENVIRONMENTS for label in policies]
    actual = [(run.get("environment"), run.get("policy")) for run in replay]
    problems.extend(_matrix_problems(name, actual, expected))
    for index, run in enumerate(replay):
        where = f"{name} replay {index}"
        problems.extend(_run_problems(where, run, policies.get(run.get("policy"))))
    return problems


CHECKS: dict[str, Callable[[Mapping[str, Any]], list[str]]] = {
    "grid.json": check_grid,
    "environments.json": check_environments,
    "guard-normal.json": check_guard_normal,
    "guard-environments.json": check_guard_environments,
}


def check_smoke_dir(directory: Path) -> list[str]:
    """Every problem with the four smoke reports under ``directory``."""
    problems: list[str] = []
    for name, check in CHECKS.items():
        path = directory / name
        try:
            report = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{name}: unreadable: {exc}")
            continue
        problems.extend(check(report))
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-dir", type=Path, required=True)
    args = parser.parse_args()
    problems = check_smoke_dir(args.smoke_dir)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(1)
    print(f"check_retry_reports: {len(CHECKS)} reports OK under {args.smoke_dir}")


if __name__ == "__main__":
    main()
