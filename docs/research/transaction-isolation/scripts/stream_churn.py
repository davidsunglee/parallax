"""A long streamed read beside writers that keep changing the rows it reads.

The reader streams every account page by page with a per-root consumer delay;
``fast`` consumes without delay and ``slow`` sleeps between roots. In the
``transaction-held`` placement the stream runs inside one ``db.transact`` at the
requested isolation, so its transaction stays open for the whole delivery; in
the ``standalone`` placement ``db.stream`` acquires a connection per page and
holds no transaction between pages. Writers amend random accounts in their own
short transactions until the reader finishes.

A sampler records, at a fixed interval, the client's traced Python memory, the
oldest snapshot any backend of the database holds (``age(backend_xmin)``),
the dead and live tuples ``pgstattuple`` counts in ``account``, the
relation and index sizes, and the writers' commits so far. After the reader
releases, the same figures are read once more before and after a ``VACUUM``,
which is the cleanup the reader's snapshot had held back. Dead tuples here are
superseded MVCC versions, not temporal history: ``account`` is non-temporal.
"""

import random
import threading
import time
import tracemalloc
from decimal import Decimal
from typing import Any

from _support import (
    Account,
    arguments,
    conditions,
    emit,
    fixtures,
    observer,
    percentiles,
    pooled,
    provisioned,
    reset,
    scalar,
    scoped,
)

STATS = (
    "select coalesce(max(age(backend_xmin)), 0) from pg_stat_activity "
    "where datname = current_database() and pid <> pg_backend_pid()"
)
TUPLES = "select dead_tuple_count, tuple_count from pgstattuple('account')"


def _server(control: Any) -> dict[str, object]:
    tuples = control.execute(TUPLES, [])
    dead, live = tuples[0] if tuples else (None, None)
    return {
        "oldestXminAge": int(scalar(control, STATS)),
        "deadTuples": dead,
        "liveTuples": live,
        "relationBytes": int(scalar(control, "select pg_relation_size('account')")),
        "indexBytes": int(scalar(control, "select pg_indexes_size('account')")),
    }


class _Churn:
    """Writers amending random accounts, and a sampler watching the server, for
    as long as one reader runs."""

    def __init__(self, db: Any, control: Any, *, roots: int, interval: float) -> None:
        self._db = db
        self._control = control
        self._roots = roots
        self._interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.commits = 0
        self.timeline: list[dict[str, object]] = []
        self.started = time.perf_counter()

    def _writer(self, seed: int) -> None:
        chooser = random.Random(seed)
        while not self._stop.is_set():
            key = chooser.randint(1, self._roots)

            def body(tx: Any, key: int = key) -> None:
                current = tx.find(Account.where(Account.id == key)).result()
                tx.amend(current.edit(balance=current.balance + Decimal("1.00")))

            try:
                self._db.transact(body)
            except Exception:  # a lost race is churn too; only commits are counted
                continue
            with self._lock:
                self.commits += 1

    def _sampler(self) -> None:
        while not self._stop.is_set():
            current, peak = tracemalloc.get_traced_memory()
            self.timeline.append(
                {
                    "at": time.perf_counter() - self.started,
                    "clientTracedBytes": current,
                    "clientPeakBytes": peak,
                    "writerCommits": self.commits,
                    **_server(self._control),
                }
            )
            self._stop.wait(self._interval)

    def start(self, writers: int) -> list[threading.Thread]:
        threads = [
            threading.Thread(target=self._writer, args=(seed,), daemon=True)
            for seed in range(writers)
        ]
        threads.append(threading.Thread(target=self._sampler, daemon=True))
        for thread in threads:
            thread.start()
        return threads

    def stop(self, threads: list[threading.Thread]) -> None:
        self._stop.set()
        for thread in threads:
            thread.join(timeout=30)


class _Reader:
    def __init__(self, delay: float, started: float) -> None:
        self._delay = delay
        self._started = started
        self.roots = 0
        self.first_root_s: float | None = None

    def consume(self, stream: Any) -> None:
        for _account in stream:
            if self.first_root_s is None:
                self.first_root_s = time.perf_counter() - self._started
            self.roots += 1
            if self._delay:
                time.sleep(self._delay)


def run_placement(
    db: Any,
    control: Any,
    *,
    roots: int,
    page: int,
    delay: float,
    writers: int,
    placement: str,
    isolation: str,
    interval: float,
) -> dict[str, object]:
    control.execute("create extension if not exists pgstattuple", [])
    tracemalloc.start()
    churn = _Churn(db, control, roots=roots, interval=interval)
    reader = _Reader(delay, churn.started)
    threads = churn.start(writers)
    reader_started = time.perf_counter()
    query = Account.where(Account.all)
    if placement == "transaction-held":

        def held(tx: Any) -> None:
            with tx.stream(query, batch_size=page) as stream:
                reader.consume(stream)

        db.transact(held, isolation=isolation)
    else:
        with db.stream(query, batch_size=page) as stream:
            reader.consume(stream)
    reader_elapsed = time.perf_counter() - reader_started
    churn.stop(threads)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    released = _server(control)
    control.execute("vacuum account", [])
    vacuumed = _server(control)
    ages = [float(sample["oldestXminAge"]) for sample in churn.timeline]  # type: ignore[arg-type]
    return {
        "placement": placement,
        "delay": delay,
        "summary": {
            "rootsDelivered": reader.roots,
            "firstRootS": reader.first_root_s,
            "readerElapsedS": reader_elapsed,
            "writerCommits": churn.commits,
            "writerThroughputPerS": churn.commits / reader_elapsed if reader_elapsed else None,
            "clientPeakTracedBytes": peak,
            "oldestXminAge": percentiles(ages),
            "afterRelease": released,
            "afterVacuum": vacuumed,
        },
        "timeline": churn.timeline,
    }


def main() -> None:
    args = arguments(__doc__ or "")
    if args.smoke:
        roots, page, writers, interval, delays = 40, 10, 1, 0.05, {"fast": 0.0, "slow": 0.002}
    else:
        roots, page, writers, interval, delays = 20000, 500, 2, 0.25, {"fast": 0.0, "slow": 0.0005}
    rows = fixtures(account_rows=roots)
    runs: list[dict[str, object]] = []
    with provisioned(rows) as run, observer(run) as control:
        adapter = pooled(run, writers + 1)
        with scoped(adapter) as db:
            for placement in ("transaction-held", "standalone"):
                for speed, delay in delays.items():
                    reset(run, rows)
                    result = run_placement(
                        db,
                        control,
                        roots=roots,
                        page=page,
                        delay=delay,
                        writers=writers,
                        placement=placement,
                        isolation=args.isolation,
                        interval=interval,
                    )
                    result["consumer"] = speed
                    runs.append(result)
        report = {
            "driver": "stream_churn",
            "conditions": conditions(
                control,
                args.isolation,
                roots=roots,
                pageSize=page,
                writers=writers,
                consumerDelayS=delays,
                sampleIntervalS=interval,
                memory="tracemalloc over the whole driver process, writers and sampler included",
            ),
            "runs": runs,
        }
    emit(report, args.out)


if __name__ == "__main__":
    main()
