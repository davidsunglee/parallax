"""Writers contending for accounts through the public ``db.transact`` path.

Every invocation reads one account inside its attempt and amends it from that
read. ``hot`` sends every writer to one account; ``disjoint`` gives each writer
its own. Each key mode runs first with ``max_retries=0``, which exposes every
first attempt's physical outcome, and then with the default bound, which
measures replay success and exhaustion. The offered load is the writer count,
each issuing its invocations back to back once all writers are ready.

With ``--backoff-grid`` the default-bound runs repeat once per candidate of the
full-jitter backoff grid below, each with the arm's internal base and cap
substituted for the run. An arm without that backoff replays immediately and
runs the default bound once. Every run records the backoff it measured.

With ``--environments`` both key modes run in every simulated environment of
``_support.ENVIRONMENTS``: client-side latency on each round trip, and
application work between an invocation's read and its amendment. There the
default-bound runs repeat once per replay policy of
``_support.REPLAY_POLICIES``, each substituted for the arm's own
duration-scaled window, and each run records the latency its connections
actually added and every replay wait's failed-attempt duration and window.
A discarded hot-key run warms the database and the process first.

The report keeps one sample per invocation and summarizes completion,
surfaced failures, latency percentiles, committed throughput, and attempts per
committed invocation.
"""

import threading
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from decimal import Decimal
from typing import Any

from _support import (
    ENVIRONMENTS,
    REPLAY_POLICIES,
    WARM_UP_INVOCATIONS,
    Account,
    Environment,
    Waits,
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
    replay_policy,
    reset,
    scaled_policy,
    scoped,
)

RETRY_MODES: tuple[int | None, ...] = (0, None)
KEY_MODES = ("hot", "disjoint")

# The full-jitter backoff candidates, as (base, cap) in seconds: the first
# attempt's ceiling, doubled per attempt up to the cap. An arm's provisional
# constants are the middle cell.
BACKOFF_BASES_S = (0.0005, 0.002, 0.008)
BACKOFF_CAPS_S = (0.025, 0.1, 0.4)
BACKOFF_GRID = tuple((base, cap) for base in BACKOFF_BASES_S for cap in BACKOFF_CAPS_S)


def fixed_backoff() -> dict[str, float] | None:
    """The arm's own fixed backoff base and cap, or ``None`` for an arm without
    them."""
    from parallax.core import auto_retry

    base = getattr(auto_retry, "_BASE_S", None)
    cap = getattr(auto_retry, "_CAP_S", None)
    return None if base is None or cap is None else {"baseS": base, "capS": cap}


def arm_backoff() -> dict[str, float] | None:
    """The arm's own backoff, fixed or duration-scaled, or ``None`` for an arm
    that replays immediately."""
    return fixed_backoff() or scaled_policy()


@contextmanager
def backoff(candidate: tuple[float, float]) -> Iterator[None]:
    """Run with ``candidate`` as the arm's backoff base and cap."""
    from parallax.core import auto_retry

    saved = auto_retry._BASE_S, auto_retry._CAP_S
    auto_retry._BASE_S, auto_retry._CAP_S = candidate
    try:
        yield
    finally:
        auto_retry._BASE_S, auto_retry._CAP_S = saved


def default_bound_backoffs(grid: bool) -> list[tuple[float, float] | None]:
    """The backoffs the default-bound runs measure: every grid candidate where
    asked and the arm has a fixed backoff to substitute, else the arm's own."""
    return list(BACKOFF_GRID) if grid and fixed_backoff() is not None else [None]


def _invoke(
    db: Any, key: int, isolation: str, retries: int | None, think_s: float = 0.0
) -> dict[str, object]:
    calls = {"attempts": 0}

    def body(tx: Any) -> None:
        calls["attempts"] += 1
        current = tx.find(Account.where(Account.id == key)).result()
        if think_s:
            pause(think_s)
        tx.amend(current.edit(balance=current.balance + Decimal("1.00")))

    options: dict[str, object] = {"isolation": isolation}
    if retries is not None:
        options["max_retries"] = retries
    started = time.perf_counter()
    try:
        db.transact(body, **options)
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
    retries: int | None,
    isolation: str,
    candidate: tuple[float, float] | None = None,
    think_s: float = 0.0,
) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    lock = threading.Lock()
    ready = threading.Barrier(workers + 1)

    def worker(index: int) -> None:
        key = 1 if keys == "hot" else index + 1
        ready.wait()
        for _ in range(invocations):
            sample = _invoke(db, key, isolation, retries, think_s)
            sample["worker"] = index
            with lock:
                samples.append(sample)

    threads = [
        threading.Thread(target=worker, args=(index,), name=f"writer-{index}")
        for index in range(workers)
    ]
    for thread in threads:
        thread.start()
    measured = arm_backoff() if candidate is None else {"baseS": candidate[0], "capS": candidate[1]}
    with nullcontext() if candidate is None else backoff(candidate):
        ready.wait()
        started = time.perf_counter()
        for thread in threads:
            thread.join()
        elapsed = time.perf_counter() - started
    return {
        "keys": keys,
        "maxRetries": "default" if retries is None else retries,
        "backoff": "immediate" if measured is None else measured,
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
    """Both key modes in ``environment``: at ``max_retries=0`` once, then at the
    default bound once per replay policy."""
    adapter, latency = delayed(pooled(run, workers), environment)
    runs: list[dict[str, object]] = []
    for retries in RETRY_MODES:
        for policy in ["scaled"] if retries == 0 else list(REPLAY_POLICIES):
            for keys in KEY_MODES:
                reset(run, rows)
                waits = Waits()
                latency.take()
                with scoped(adapter) as db, replay_policy(policy, waits):
                    measured = run_mode(
                        db,
                        workers,
                        invocations,
                        keys,
                        retries,
                        isolation,
                        think_s=environment.think_s,
                    )
                measured.update(
                    {
                        "environment": environment.name,
                        "backoff": policy,
                        "latency": latency.take(),
                        "replayWaits": waits.take(),
                    }
                )
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
            help="repeat the default-bound runs for every backoff candidate",
        )
        parser.add_argument(
            "--environments",
            action="store_true",
            help="run in every simulated environment, the default bound once per replay policy",
        )

    args = arguments(__doc__ or "", extra=extra)
    workers, invocations = (2, 3) if args.smoke else (args.workers, args.invocations)
    rows = fixtures(account_rows=workers)
    runs: list[dict[str, object]] = []
    with provisioned(rows) as run, observer(run) as control:
        if args.environments:
            reset(run, rows)
            with scoped(pooled(run, workers)) as db:
                run_mode(db, workers, WARM_UP_INVOCATIONS, "hot", None, args.isolation)
            for environment in ENVIRONMENTS:
                runs.extend(
                    environment_runs(run, rows, workers, invocations, args.isolation, environment)
                )
        else:
            adapter = pooled(run, workers)
            for retries in RETRY_MODES:
                candidates = [None] if retries == 0 else default_bound_backoffs(args.backoff_grid)
                for candidate in candidates:
                    for keys in KEY_MODES:
                        reset(run, rows)
                        with scoped(adapter) as db:
                            runs.append(
                                run_mode(
                                    db,
                                    workers,
                                    invocations,
                                    keys,
                                    retries,
                                    args.isolation,
                                    candidate,
                                )
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
                retry="the arm's own replay policy",
                **({"backoffGrid": [list(c) for c in BACKOFF_GRID]} if args.backoff_grid else {}),
                **(environment_conditions() if args.environments else {}),
            ),
            "runs": runs,
        }
    emit(report, args.out)


if __name__ == "__main__":
    main()
