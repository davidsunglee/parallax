"""Writers contending for accounts through the public ``db.transact`` path.

Every invocation reads one account inside its attempt and amends it from that
read. ``hot`` sends every writer to one account; ``disjoint`` gives each writer
its own. Each key mode runs first under the disabled policy, which exposes every
first attempt's physical outcome, and then under the default policy, which
measures replay success and exhaustion. The offered load is the writer count,
each issuing its invocations back to back once all writers are ready.

With ``--backoff-grid`` the default-policy runs repeat once per candidate of the
grid below instead, each an adaptive public policy under the default bound.

With ``--environments`` both key modes run in every simulated environment of
``_support.ENVIRONMENTS``: client-side latency on each round trip, and
application work between an invocation's read and its amendment. Each run
records the latency its connections actually added. A discarded hot-key run
warms the database and the process first.

Every run states the complete policy it passed to ``retry=``, and the report
keeps one sample per invocation and summarizes completion, surfaced failures,
latency percentiles, committed throughput, and attempts per committed
invocation.
"""

import threading
import time
from collections import Counter
from decimal import Decimal
from typing import Any

from _support import (
    ENVIRONMENTS,
    REPLAY_POLICIES,
    WARM_UP_INVOCATIONS,
    Account,
    Environment,
    arguments,
    conditions,
    delayed,
    emit,
    environment_conditions,
    failure,
    fixtures,
    observer,
    pause,
    percentiles,
    pooled,
    provisioned,
    reported_policy,
    reset,
    scoped,
)

from parallax.core.execution import AdaptiveBackoff, RetryPolicy

KEY_MODES = ("hot", "disjoint")

# The grid candidates, as (base, cap) in seconds: each an adaptive policy's base
# and maximum delay under the default bound, not a fixed-only algorithm.
BACKOFF_BASES_S = (0.0005, 0.002, 0.008)
BACKOFF_CAPS_S = (0.025, 0.1, 0.4)
BACKOFF_GRID = tuple((base, cap) for base in BACKOFF_BASES_S for cap in BACKOFF_CAPS_S)


def adaptive_policies() -> dict[str, RetryPolicy]:
    """The grid's candidates as public policies, named by their millisecond delays."""
    return {
        f"adaptive-{base * 1000:g}/{cap * 1000:g}": RetryPolicy(
            backoff=AdaptiveBackoff(base_delay=base, max_delay=cap)
        )
        for base, cap in BACKOFF_GRID
    }


def measured_policies(grid: bool) -> dict[str, RetryPolicy]:
    """The policies a report without ``--environments`` runs, in order."""
    if grid:
        return {"disabled": REPLAY_POLICIES["disabled"], **adaptive_policies()}
    return dict(REPLAY_POLICIES)


def _invoke(
    db: Any, key: int, isolation: str, policy: RetryPolicy, think_s: float = 0.0
) -> dict[str, object]:
    calls = {"attempts": 0}

    def body(tx: Any) -> None:
        calls["attempts"] += 1
        current = tx.find(Account.where(Account.id == key)).result()
        if think_s:
            pause(think_s)
        tx.amend(current.edit(balance=current.balance + Decimal("1.00")))

    started = time.perf_counter()
    try:
        db.transact(body, isolation=isolation, retry=policy)
        outcome: object = "committed"
    except Exception as exc:
        outcome = failure(exc)
    return {
        "latencyMs": (time.perf_counter() - started) * 1000,
        "attempts": calls["attempts"],
        "outcome": outcome,
    }


def run_mode(
    db: Any,
    workers: int,
    invocations: int,
    keys: str,
    label: str,
    policy: RetryPolicy,
    isolation: str,
    think_s: float = 0.0,
) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    lock = threading.Lock()
    ready = threading.Barrier(workers + 1)

    def worker(index: int) -> None:
        key = 1 if keys == "hot" else index + 1
        ready.wait()
        for _ in range(invocations):
            sample = _invoke(db, key, isolation, policy, think_s)
            sample["worker"] = index
            with lock:
                samples.append(sample)

    threads = [
        threading.Thread(target=worker, args=(index,), name=f"writer-{index}")
        for index in range(workers)
    ]
    for thread in threads:
        thread.start()
    ready.wait()
    started = time.perf_counter()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started
    return {
        "keys": keys,
        "policy": label,
        "retry": reported_policy(policy),
        "elapsedS": elapsed,
        "summary": summarize(samples, elapsed),
        "samples": samples,
    }


def environment_runs(
    run: Any,
    rows: Any,
    workers: int,
    invocations: int,
    isolation: str,
    environment: Environment,
) -> list[dict[str, object]]:
    """Both key modes in ``environment``, once per replay policy."""
    adapter, latency = delayed(pooled(run, workers), environment)
    runs: list[dict[str, object]] = []
    for label, policy in REPLAY_POLICIES.items():
        for keys in KEY_MODES:
            reset(run, rows)
            latency.take()
            with scoped(adapter) as db:
                measured = run_mode(
                    db,
                    workers,
                    invocations,
                    keys,
                    label,
                    policy,
                    isolation,
                    think_s=environment.think_s,
                )
            measured.update({"environment": environment.name, "latency": latency.take()})
            runs.append(measured)
    return runs


def summarize(samples: list[dict[str, object]], elapsed: float) -> dict[str, object]:
    committed = [sample for sample in samples if sample["outcome"] == "committed"]
    failures = Counter(
        f"{outcome['type']}:{outcome['category']}:{outcome['nativeCode']}"
        for sample in samples
        if isinstance(outcome := sample["outcome"], dict)
    )
    attempts = sum(int(sample["attempts"]) for sample in samples)  # type: ignore[arg-type]
    return {
        "invocations": len(samples),
        "committed": len(committed),
        "completionRate": len(committed) / len(samples) if samples else None,
        "surfacedFailures": dict(failures),
        "latencyMs": percentiles([float(sample["latencyMs"]) for sample in samples]),  # type: ignore[arg-type]
        "committedLatencyMs": percentiles([float(sample["latencyMs"]) for sample in committed]),  # type: ignore[arg-type]
        "committedThroughputPerS": len(committed) / elapsed if elapsed else None,
        "attempts": attempts,
        "attemptsPerSuccess": attempts / len(committed) if committed else None,
    }


def main() -> None:
    def extra(parser: Any) -> None:
        parser.add_argument("--workers", type=int, default=8)
        parser.add_argument("--invocations", type=int, default=200, help="per writer")
        parser.add_argument(
            "--backoff-grid",
            action="store_true",
            help="repeat the default-bound runs for every adaptive grid candidate",
        )
        parser.add_argument(
            "--environments",
            action="store_true",
            help="run in every simulated environment under the disabled and default policies",
        )

    args = arguments(__doc__ or "", extra=extra)
    workers, invocations = (2, 3) if args.smoke else (args.workers, args.invocations)
    rows = fixtures(account_rows=workers)
    runs: list[dict[str, object]] = []
    with provisioned(rows) as run, observer(run) as control:
        if args.environments:
            reset(run, rows)
            with scoped(pooled(run, workers)) as db:
                run_mode(
                    db,
                    workers,
                    WARM_UP_INVOCATIONS,
                    "hot",
                    "default",
                    REPLAY_POLICIES["default"],
                    args.isolation,
                )
            for environment in ENVIRONMENTS:
                runs.extend(
                    environment_runs(run, rows, workers, invocations, args.isolation, environment)
                )
        else:
            adapter = pooled(run, workers)
            for label, policy in measured_policies(args.backoff_grid).items():
                for keys in KEY_MODES:
                    reset(run, rows)
                    with scoped(adapter) as db:
                        runs.append(
                            run_mode(db, workers, invocations, keys, label, policy, args.isolation)
                        )
        report = {
            "driver": "contention",
            "conditions": conditions(
                control,
                args.isolation,
                workers=workers,
                invocationsPerWorker=invocations,
                pool={"minSize": workers, "maxSize": workers},
                body="read one account in the attempt, then amend its balance",
                **({"backoffGrid": [list(c) for c in BACKOFF_GRID]} if args.backoff_grid else {}),
                **(environment_conditions() if args.environments else {}),
            ),
            "runs": runs,
        }
    emit(report, args.out)


if __name__ == "__main__":
    main()
