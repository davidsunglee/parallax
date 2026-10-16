"""What PostgreSQL's unchanged-milestone guard costs: WAL per write, and replay
when two guards meet.

An optimistic amendment of a Transaction-Time-Only balance that restates its
current value rewrites the milestone in place (``set in_z = in_z``) to hold its
gate, creating a new physical row version with no semantic change. The same
amendment under the Locking preference keeps the milestone without a
statement, and an amendment that does change the value closes the milestone
and chains a successor. Each runs serially, one balance per invocation, and
reports the WAL bytes between ``pg_current_wal_insert_lsn()`` readings around
it, which include whatever the server wrote meanwhile.

The replay section has two writers repeatedly guarding the same balance; at
Repeatable Read their physical rewrites refuse each other although no value
changes, so attempts per committed invocation measure the guard's replay cost.
"""

import threading
import time
from decimal import Decimal
from typing import Any

from _support import (
    Balance,
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
    scalar,
    scoped,
)

WAL_MODES: dict[str, dict[str, object]] = {
    "guard": {"concurrency": "optimistic", "change": False},
    "locking-keeps-the-milestone": {"concurrency": "locking", "change": False},
    "change": {"concurrency": "optimistic", "change": True},
}


def _lsn(control: Any) -> str:
    return str(scalar(control, "select pg_current_wal_insert_lsn()"))


def _wal_bytes(control: Any, before: str, after: str) -> int:
    return int(scalar(control, f"select pg_wal_lsn_diff('{after}', '{before}')"))


def wal_mode(db: Any, control: Any, keys: int, mode: str, isolation: str) -> dict[str, object]:
    concurrency, change = WAL_MODES[mode]["concurrency"], WAL_MODES[mode]["change"]
    samples: list[dict[str, object]] = []
    for key in range(1, keys + 1):

        def body(tx: Any, key: int = key) -> None:
            current = tx.find(Balance.where(Balance.id == key)).result()
            value = current.value + Decimal("1.00") if change else current.value
            tx.amend(current.edit(value=value))

        before = _lsn(control)
        started = time.perf_counter()
        db.transact(body, isolation=isolation, concurrency=concurrency)
        elapsed = time.perf_counter() - started
        samples.append(
            {
                "key": key,
                "walBytes": _wal_bytes(control, before, _lsn(control)),
                "latencyMs": elapsed * 1000,
            }
        )
    wal = [int(sample["walBytes"]) for sample in samples]  # type: ignore[arg-type]
    return {
        "mode": mode,
        "summary": {
            "walBytesPerWrite": percentiles([float(value) for value in wal]),
            "writes": len(wal),
        },
        "samples": samples,
    }


def guard_replay(
    db: Any, writers: int, invocations: int, isolation: str, retries: int | None
) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    lock = threading.Lock()
    ready = threading.Barrier(writers + 1)

    def worker(index: int) -> None:
        ready.wait()
        for _ in range(invocations):
            calls = {"attempts": 0}

            def body(tx: Any, calls: dict[str, int] = calls) -> None:
                calls["attempts"] += 1
                current = tx.find(Balance.where(Balance.id == 1)).result()
                tx.amend(current.edit(value=current.value))

            options: dict[str, object] = {"isolation": isolation}
            if retries is not None:
                options["max_retries"] = retries
            started = time.perf_counter()
            try:
                db.transact(body, **options)
                outcome: object = "committed"
            except Exception as exc:
                outcome = failure(exc)
            with lock:
                samples.append(
                    {
                        "worker": index,
                        "attempts": calls["attempts"],
                        "latencyMs": (time.perf_counter() - started) * 1000,
                        "outcome": outcome,
                    }
                )

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(writers)]
    for thread in threads:
        thread.start()
    ready.wait()
    started = time.perf_counter()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started
    committed = [sample for sample in samples if sample["outcome"] == "committed"]
    attempts = sum(int(sample["attempts"]) for sample in samples)  # type: ignore[arg-type]
    return {
        "maxRetries": "default" if retries is None else retries,
        "summary": {
            "invocations": len(samples),
            "committed": len(committed),
            "attemptsPerSuccess": attempts / len(committed) if committed else None,
            "latencyMs": percentiles([float(sample["latencyMs"]) for sample in samples]),  # type: ignore[arg-type]
            "committedThroughputPerS": len(committed) / elapsed if elapsed else None,
        },
        "samples": samples,
    }


def main() -> None:
    args = arguments(__doc__ or "")
    keys, writers, invocations = (3, 2, 3) if args.smoke else (200, 2, 200)
    rows = fixtures(balance_rows=keys)
    with provisioned(rows) as run, observer(run) as control:
        adapter = pooled(run, writers)
        wal: list[dict[str, object]] = []
        replay: list[dict[str, object]] = []
        with scoped(adapter) as db:
            for mode in WAL_MODES:
                reset(run, rows)
                wal.append(wal_mode(db, control, keys, mode, args.isolation))
            for retries in (0, None):
                reset(run, rows)
                replay.append(guard_replay(db, writers, invocations, args.isolation, retries))
        report = {
            "driver": "guard_wal",
            "conditions": conditions(
                control,
                args.isolation,
                balances=keys,
                writers=writers,
                invocationsPerWriter=invocations,
            ),
            "wal": wal,
            "replay": replay,
        }
    emit(report, args.out)


if __name__ == "__main__":
    main()
