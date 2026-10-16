"""Writers contending for accounts through the public ``db.transact`` path.

Every invocation reads one account inside its attempt and amends it from that
read. ``hot`` sends every writer to one account; ``disjoint`` gives each writer
its own. Each key mode runs first with ``max_retries=0``, which exposes every
first attempt's physical outcome, and then with the default bound, which
measures replay success and exhaustion. The offered load is the writer count,
each issuing its invocations back to back once all writers are ready.

The report keeps one sample per invocation and summarizes completion,
surfaced failures, latency percentiles, committed throughput, and attempts per
committed invocation.
"""

import threading
import time
from collections import Counter
from decimal import Decimal
from typing import Any

from _support import (
    Account,
    arguments,
    conditions,
    emit,
    failure,
    fixtures,
    observer,
    percentiles,
    pooled,
    provisioned,
    reset,
    scoped,
)

RETRY_MODES: tuple[int | None, ...] = (0, None)
KEY_MODES = ("hot", "disjoint")


def _invoke(db: Any, key: int, isolation: str, retries: int | None) -> dict[str, object]:
    calls = {"attempts": 0}

    def body(tx: Any) -> None:
        calls["attempts"] += 1
        current = tx.find(Account.where(Account.id == key)).result()
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
    db: Any, workers: int, invocations: int, keys: str, retries: int | None, isolation: str
) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    lock = threading.Lock()
    ready = threading.Barrier(workers + 1)

    def worker(index: int) -> None:
        key = 1 if keys == "hot" else index + 1
        ready.wait()
        for _ in range(invocations):
            sample = _invoke(db, key, isolation, retries)
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
        "maxRetries": "default" if retries is None else retries,
        "elapsedS": elapsed,
        "summary": summarize(samples, elapsed),
        "samples": samples,
    }


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

    args = arguments(__doc__ or "", extra=extra)
    workers, invocations = (2, 3) if args.smoke else (args.workers, args.invocations)
    rows = fixtures(account_rows=workers)
    runs: list[dict[str, object]] = []
    with provisioned(rows) as run, observer(run) as control:
        adapter = pooled(run, workers)
        for retries in RETRY_MODES:
            for keys in KEY_MODES:
                reset(run, rows)
                with scoped(adapter) as db:
                    runs.append(run_mode(db, workers, invocations, keys, retries, args.isolation))
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
            ),
            "runs": runs,
        }
    emit(report, args.out)


if __name__ == "__main__":
    main()
