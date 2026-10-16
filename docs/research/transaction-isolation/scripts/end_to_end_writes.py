"""Whole write workflows timed end to end, the licensing read included.

The committed keyed-write instrument opens its window after the source read; a
comparison between workflows needs that read inside the window, because the
keyed workflow pays for it and the conditional workflow does not. Each sample
here is one complete ``db.transact`` call against live PostgreSQL:

* ``keyed`` reads the object inside the attempt and amends it from that read;
* ``conditional`` states the revision it was handed (``amend_if``) and reads
  nothing of its own beyond what its flush owes;
* ``predicate`` selects the object by key with ``amend_where``.

Each workflow runs over a non-temporal versioned account, a
Transaction-Time-Only balance, and a bitemporal position, one fresh object per
invocation so every stated revision is the fixture's own. A second, smaller
pass records each invocation's statements and its traced Python allocation
peak and net retention.
"""

import datetime as dt
import time
import tracemalloc
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from _support import (
    Account,
    Balance,
    Position,
    arguments,
    conditions,
    emit,
    fixtures,
    observer,
    percentiles,
    pooled,
    provisioned,
    recorded,
    reset,
    scoped,
)

EPOCH = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
VALID_FROM = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
VALUE = Decimal("123.45")

Body = Callable[[Any, int], None]


def _keyed_account(tx: Any, key: int) -> None:
    current = tx.find(Account.where(Account.id == key)).result()
    tx.amend(current.edit(balance=VALUE))


def _keyed_balance(tx: Any, key: int) -> None:
    current = tx.find(Balance.where(Balance.id == key)).result()
    tx.amend(current.edit(value=VALUE))


def _keyed_position(tx: Any, key: int) -> None:
    current = tx.find(Position.where(Position.id == key).as_of(valid_time=VALID_FROM)).result()
    tx.amend(current.edit(value=VALUE))


WORKFLOWS: dict[tuple[str, str], Body] = {
    ("account", "keyed"): _keyed_account,
    ("account", "conditional"): lambda tx, key: tx.amend_if(
        Account, Account.balance.set(VALUE), key=key, version=1
    ),
    ("account", "predicate"): lambda tx, key: tx.amend_where(
        Account.where(Account.id == key), Account.balance.set(VALUE)
    ),
    ("balance", "keyed"): _keyed_balance,
    ("balance", "conditional"): lambda tx, key: tx.amend_if(
        Balance, Balance.value.set(VALUE), key=key, tx_start=EPOCH
    ),
    ("balance", "predicate"): lambda tx, key: tx.amend_where(
        Balance.where(Balance.id == key), Balance.value.set(VALUE)
    ),
    ("position", "keyed"): _keyed_position,
    ("position", "conditional"): lambda tx, key: tx.amend_if(
        Position, Position.value.set(VALUE), key=key, tx_start=EPOCH, valid_from=VALID_FROM
    ),
    ("position", "predicate"): lambda tx, key: tx.amend_where(
        Position.where(Position.id == key), Position.value.set(VALUE), valid_from=VALID_FROM
    ),
}


def timed(db: Any, body: Body, keys: int, isolation: str) -> list[float]:
    latencies: list[float] = []
    for key in range(1, keys + 1):
        started = time.perf_counter()
        db.transact(lambda tx, key=key: body(tx, key), isolation=isolation)
        latencies.append((time.perf_counter() - started) * 1000)
    return latencies


def shaped(
    db: Any, recording: Any, body: Body, keys: int, isolation: str
) -> list[dict[str, object]]:
    shapes: list[dict[str, object]] = []
    for key in range(1, keys + 1):
        recording.take()
        tracemalloc.start()
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        db.transact(lambda tx, key=key: body(tx, key), isolation=isolation)
        after, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        statements = recording.take()
        shapes.append(
            {
                "key": key,
                "peakBytes": peak - before,
                "netBytes": after - before,
                "statements": [
                    {"kind": entry["kind"], "sql": entry["sql"]} for entry in statements
                ],
            }
        )
    return shapes


def main() -> None:
    args = arguments(__doc__ or "")
    keys, shape_keys = (3, 2) if args.smoke else (400, 20)
    rows = fixtures(account_rows=keys, balance_rows=keys, position_rows=keys)
    results: list[dict[str, object]] = []
    with provisioned(rows) as run, observer(run) as control:
        plain = pooled(run, 1)
        adapter, recording = recorded(plain)
        for (target, workflow), body in WORKFLOWS.items():
            reset(run, rows)
            with scoped(plain) as db:
                latencies = timed(db, body, keys, args.isolation)
            reset(run, rows)
            with scoped(adapter) as db:
                shapes = shaped(db, recording, body, shape_keys, args.isolation)
            results.append(
                {
                    "target": target,
                    "workflow": workflow,
                    "summary": {
                        "invocations": len(latencies),
                        "latencyMs": percentiles(latencies),
                        "statementsPerInvocation": [len(shape["statements"]) for shape in shapes],  # type: ignore[arg-type]
                    },
                    "latenciesMs": latencies,
                    "shapes": shapes,
                }
            )
        report = {
            "driver": "end_to_end_writes",
            "conditions": conditions(
                control,
                args.isolation,
                objectsPerWorkflow=keys,
                shapedInvocations=shape_keys,
                pool={"minSize": 1, "maxSize": 1},
                window="one whole db.transact call, licensing read included",
            ),
            "results": results,
        }
    emit(report, args.out)


if __name__ == "__main__":
    main()
