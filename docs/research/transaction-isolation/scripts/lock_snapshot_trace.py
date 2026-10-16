"""The SQL Parallax actually emits for each two-transaction witness schedule, and
the lock and snapshot ordering PostgreSQL reports while it runs.

Each schedule drives two real ``db.transact`` callbacks through the public API,
handing control between them at named checkpoints. At every checkpoint the
observer records each backend's state, wait event, and snapshot horizon
(``age(backend_xmin)``); the recording connection records every statement in
the order it reached the database. Each schedule runs with ``max_retries=0``
first, so the first attempt's physical outcome is visible, and then with the
default bound, so any replay is too.
"""

import datetime as dt
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from _support import (
    Account,
    Balance,
    Gate,
    OrderItem,
    activity,
    arguments,
    await_lock_wait,
    concurrently,
    conditions,
    emit,
    failure,
    fixtures,
    observer,
    pooled,
    provisioned,
    recorded,
    reset,
    scoped,
)

ORDERS = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Linus"}]
ITEMS = [{"id": 11, "orderId": 1, "sku": "A-100"}, {"id": 12, "orderId": 1, "sku": "B-200"}]


class Trace:
    def __init__(self, control: Any) -> None:
        self._control = control
        self.checkpoints: list[dict[str, object]] = []
        self._started = time.perf_counter()

    def checkpoint(self, name: str) -> None:
        self.checkpoints.append(
            {
                "name": name,
                "at": time.perf_counter() - self._started,
                "backends": activity(self._control),
            }
        )


def _transaction(
    db: Any, body: Callable[[Any], object], retries: int | None, isolation: str
) -> Callable[[], object]:
    calls = {"attempts": 0}

    def counted(tx: Any) -> object:
        calls["attempts"] += 1
        return body(tx)

    def run() -> object:
        options: dict[str, object] = {"isolation": isolation}
        if retries is not None:
            options["max_retries"] = retries
        try:
            db.transact(counted, **options)
        except Exception as exc:
            return {"outcome": failure(exc), "attempts": calls["attempts"]}
        return {"outcome": "committed", "attempts": calls["attempts"]}

    return run


def gate_race(
    db: Any, gate: Gate, trace: Trace, retries: int | None, isolation: str
) -> list[Callable[[], object]]:
    """B reads account 1; A amends it and commits; B then amends from its read."""

    def b(tx: Any) -> None:
        current = tx.find(Account.where(Account.id == 1)).result()
        trace.checkpoint("b-read")
        gate.open("b-read")
        gate.wait("a-done")
        tx.amend(current.edit(balance=current.balance + Decimal("1.00")))

    def a(tx: Any) -> None:
        gate.wait("b-read")
        current = tx.find(Account.where(Account.id == 1)).result()
        tx.amend(current.edit(balance=current.balance + Decimal("10.00")))

    def a_then_signal() -> object:
        result = _transaction(db, a, retries, isolation)()
        trace.checkpoint("a-committed")
        gate.open("a-done")
        return result

    return [_transaction(db, b, retries, isolation), a_then_signal]


def fixed_revision(
    db: Any, gate: Gate, trace: Trace, retries: int | None, isolation: str
) -> list[Callable[[], object]]:
    """B's snapshot predates A's change; B then states the revision A replaced."""

    def b(tx: Any) -> None:
        tx.find(Account.where(Account.id == 2)).result()
        trace.checkpoint("b-snapshot")
        gate.open("b-snapshot")
        gate.wait("a-done")
        tx.amend_if(Account, Account.balance.set(Decimal("300.00")), key=1, version=1)

    def a(tx: Any) -> None:
        gate.wait("b-snapshot")
        current = tx.find(Account.where(Account.id == 1)).result()
        tx.amend(current.edit(balance=Decimal("999.00")))

    def a_then_signal() -> object:
        result = _transaction(db, a, retries, isolation)()
        trace.checkpoint("a-committed")
        gate.open("a-done")
        return result

    return [_transaction(db, b, retries, isolation), a_then_signal]


def _holding(
    gate: Gate, trace: Trace, change: Callable[[Any], None], flush: Callable[[Any], object]
) -> Callable[[Any], None]:
    """A body that makes its change, flushes it with a read, and holds it until
    the peer is seen waiting on it."""

    def body(tx: Any) -> None:
        change(tx)
        flush(tx)
        trace.checkpoint("a-holds")
        gate.open("a-holds")
        gate.wait("b-waiting")

    return body


def _releaser(control: Any, gate: Gate, trace: Trace) -> Callable[[], object]:
    def release() -> object:
        gate.wait("a-holds")
        waited = await_lock_wait(control, bound=5.0)
        trace.checkpoint("b-waiting" if waited else "b-never-waited")
        gate.open("b-waiting")
        return {"waited": waited}

    return release


def key_selecting_delete(
    db: Any, gate: Gate, trace: Trace, retries: int | None, isolation: str, control: Any
) -> list[Callable[[], object]]:
    """A moves item 11 to order 2 and holds; B deletes Ada's items by key selection."""

    def change(tx: Any) -> None:
        item = tx.find(OrderItem.where(OrderItem.id == 11)).result()
        tx.amend(item.edit(order_id=2))

    def b(tx: Any) -> None:
        gate.wait("a-holds")
        tx.delete_where(OrderItem.where(OrderItem.order.name == "Ada"))

    a = _holding(gate, trace, change, lambda tx: tx.find(OrderItem.where(OrderItem.id == 0)))
    return [
        _transaction(db, a, retries, isolation),
        _transaction(db, b, retries, isolation),
        _releaser(control, gate, trace),
    ]


def guard_then_write(
    db: Any, gate: Gate, trace: Trace, retries: int | None, isolation: str, control: Any
) -> list[Callable[[], object]]:
    """A's unchanged amendment guards balance 1 and holds; B closes the milestone."""

    def change(tx: Any) -> None:
        current = tx.find(Balance.where(Balance.id == 1)).result()
        tx.amend(current.edit(value=current.value))

    def b(tx: Any) -> None:
        gate.wait("a-holds")
        current = tx.find(Balance.where(Balance.id == 1)).result()
        tx.amend(current.edit(value=Decimal("999.00")))

    a = _holding(gate, trace, change, lambda tx: tx.find(Balance.where(Balance.id == 0)))
    return [
        _transaction(db, a, retries, isolation),
        _transaction(db, b, retries, isolation),
        _releaser(control, gate, trace),
    ]


SCHEDULES: dict[str, tuple[Callable[..., list[Callable[[], object]]], bool]] = {
    "gate-race": (gate_race, False),
    "fixed-revision": (fixed_revision, False),
    "key-selecting-delete": (key_selecting_delete, True),
    "guard-then-write": (guard_then_write, True),
}


def _rows(control: Any) -> dict[str, list[list[object]]]:
    return {
        "account": [
            list(row)
            for row in control.execute("select id, balance, version from account order by id", [])
        ],
        "order_item": [
            list(row)
            for row in control.execute("select id, order_id, sku from order_item order by id", [])
        ],
        "balance": [
            [str(cell) for cell in row]
            for row in control.execute(
                "select bal_id, val, in_z, out_z from balance order by bal_id, in_z", []
            )
        ],
    }


def main() -> None:
    args = arguments(__doc__ or "")
    rows = fixtures(account_rows=2, balance_rows=1, orders=ORDERS, items=ITEMS)
    traces: list[dict[str, object]] = []
    with provisioned(rows) as run, observer(run) as control:
        adapter, recording = recorded(pooled(run, 4))
        for name, (schedule, needs_control) in SCHEDULES.items():
            for retries in (0, None):
                reset(run, rows)
                recording.take()
                gate = Gate()
                trace = Trace(control)
                with scoped(adapter) as db:
                    extra = (control,) if needs_control else ()
                    bodies = schedule(db, gate, trace, retries, args.isolation, *extra)
                    results = concurrently(*bodies)
                traces.append(
                    {
                        "schedule": name,
                        "maxRetries": "default" if retries is None else retries,
                        "results": [
                            r if not isinstance(r, BaseException) else failure(r) for r in results
                        ],
                        "statements": recording.take(),
                        "checkpoints": trace.checkpoints,
                        "finalState": _rows(control),
                    }
                )
        report = {
            "driver": "lock_snapshot_trace",
            "conditions": conditions(control, args.isolation, schedules=list(SCHEDULES), pool=4),
            "capturedAt": dt.datetime.now(dt.UTC).isoformat(),
            "traces": traces,
        }
    emit(report, args.out)


if __name__ == "__main__":
    main()
