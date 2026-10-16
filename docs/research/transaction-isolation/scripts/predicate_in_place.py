"""COR-211's predicate-write schedules on PostgreSQL, in the key-selecting form
Parallax emits and the historical in-place form it replaced.

Transaction A changes one input of the predicate — the target's correlation
column, a column of the target the predicate tests, or the joined row alone —
and holds the change. Transaction B's predicate UPDATE or DELETE runs before A
commits, waits where it must, and finishes after A commits. Each schedule runs
at Read Committed and Repeatable Read.

The key-selecting statement is the one Parallax emits for the predicate, read
off a rolled-back transaction; the in-place statement is the historical
comparison form, which production no longer emits. ``--compare`` grades the
observed outcomes against the table COR-211's PostgreSQL probes recorded and
exits nonzero on any disagreement.
"""

import argparse
import sys
from collections.abc import Mapping
from typing import Any

from _support import (
    Order,
    OrderItem,
    await_lock_wait,
    concurrently,
    emit,
    fixtures,
    observer,
    provisioned,
    recorded,
    reset,
    scoped,
)

CHANGES: dict[str, tuple[str, tuple[object, ...]]] = {
    "correlation": ("update order_item set order_id = %s where id = %s", (2, 11)),
    "own": ("update order_item set sku = %s where id = %s", ("X-1", 11)),
    "joined": ("update orders set name = %s where id = %s", ("Zed", 1)),
}
_EXISTS = "exists (select 1 from orders t1 where t1.id = order_id and t1.name = %s)"
IN_PLACE: dict[tuple[str, str], tuple[str, tuple[object, ...]]] = {
    ("delete", "name"): (f"delete from order_item where {_EXISTS}", ("Ada",)),
    ("update", "name"): (f"update order_item set sku = %s where {_EXISTS}", ("Z", "Ada")),
    ("delete", "own"): (f"delete from order_item where {_EXISTS} and sku = %s", ("Ada", "A-100")),
    ("update", "own"): (
        f"update order_item set sku = %s where {_EXISTS} and sku = %s",
        ("Z", "Ada", "A-100"),
    ),
}
# The COR-211 table as the COR-214 ticket records it (historical PostgreSQL probes).
RECORDED: dict[tuple[str, str, str], str] = {
    ("correlation", "key-selecting", "read_committed"): "writes-target",
    ("correlation", "in-place", "read_committed"): "skips-target",
    ("correlation", "key-selecting", "repeatable_read"): "serialization-failure",
    ("correlation", "in-place", "repeatable_read"): "serialization-failure",
    ("own", "key-selecting", "read_committed"): "writes-target",
    ("own", "in-place", "read_committed"): "skips-target",
    ("own", "key-selecting", "repeatable_read"): "serialization-failure",
    ("own", "in-place", "repeatable_read"): "serialization-failure",
    ("joined", "key-selecting", "read_committed"): "acts-on-snapshot",
    ("joined", "in-place", "read_committed"): "acts-on-snapshot",
    ("joined", "key-selecting", "repeatable_read"): "acts-on-snapshot",
    ("joined", "in-place", "repeatable_read"): "acts-on-snapshot",
}
ORDERS = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Linus"}, {"id": 42, "name": "Grace"}]
ITEMS = [
    {"id": 11, "orderId": 1, "sku": "A-100"},
    {"id": 12, "orderId": 1, "sku": "B-200"},
    {"id": 21, "orderId": 2, "sku": "A-300"},
]
SPELLING = {"read_committed": "read committed", "repeatable_read": "repeatable read"}


class _Discard(Exception):
    """Rolls back the transaction that only exists to show its statement."""


def emitted(run: Any, verb: str, predicate: str) -> tuple[str, tuple[object, ...]]:
    """The statement Parallax flushes for the predicate write, in driver form."""
    query = OrderItem.where(OrderItem.order.name == "Ada")
    if predicate == "own":
        query = OrderItem.where((OrderItem.order.name == "Ada") & (OrderItem.sku == "A-100"))
    adapter, recording = recorded(run.port)

    def body(tx: Any) -> None:
        if verb == "delete":
            tx.delete_where(query)
        else:
            tx.amend_where(query, OrderItem.sku.set("Z"))
        tx.find(Order.where(Order.id == 0))  # a read flushes the pending write first
        raise _Discard

    with scoped(adapter) as db:
        try:
            db.transact(body, max_retries=0)
        except Exception as exc:  # the discard, wrapped in its execution context
            if not isinstance(getattr(exc, "cause", exc), _Discard):
                raise
    (statement,) = [entry for entry in recording.take() if entry["kind"] == "write"]
    sql = str(statement["sql"])
    if "?" in sql:
        sql = run.port.dialect.to_driver_sql(sql)
    return sql, tuple(_bind(value) for value in statement["binds"])


def _bind(text: object) -> object:
    return int(text) if isinstance(text, str) and text.isdigit() else text


def _session(run: Any, isolation: str) -> Any:
    session = run.control(autocommit=False)
    session.execute(f"set transaction isolation level {SPELLING[isolation]}", [])
    return session


def run_schedule(
    run: Any, isolation: str, change: str, statement: tuple[str, tuple[object, ...]]
) -> dict[str, object]:
    reset(run, fixtures(orders=ORDERS, items=ITEMS))
    a, b = _session(run, isolation), _session(run, isolation)
    try:
        change_sql, change_binds = CHANGES[change]
        a.execute_write(change_sql, list(change_binds))
        with observer(run) as control:
            sql, binds = statement

            def write() -> int:
                return b.execute_write(sql, list(binds))

            def release() -> bool:
                waited = await_lock_wait(control, bound=2.0)
                a.execute("commit", [])
                return waited

            affected, waited = concurrently(write, release)
        if isinstance(affected, BaseException):
            b.execute("rollback", [])
        else:
            b.execute("commit", [])
    finally:
        a.close()
        b.close()
    with observer(run) as control:
        rows = {row[0]: row[1] for row in control.execute("select id, sku from order_item", [])}
    return _outcome(change, affected, bool(waited), rows)


def _outcome(
    change: str, affected: object, waited: bool, rows: Mapping[int, str]
) -> dict[str, object]:
    observed: dict[str, object] = {"waited": waited, "items": dict(sorted(rows.items()))}
    if isinstance(affected, BaseException):
        code = getattr(affected, "native_code", None) or getattr(affected, "sqlstate", None)
        observed["error"] = code or repr(affected)
        observed["class"] = "serialization-failure" if code == "40001" else f"error-{code}"
        return observed
    observed["affected"] = affected
    target_written = 11 not in rows or rows[11] == "Z"
    if change == "joined":
        observed["class"] = "acts-on-snapshot" if target_written else "excludes-target"
    else:
        observed["class"] = "writes-target" if target_written else "skips-target"
    return observed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="exit nonzero on any disagreement")
    parser.add_argument("--out", help="write the JSON report here instead of stdout")
    args = parser.parse_args()
    rows: list[dict[str, object]] = []
    with provisioned(fixtures(orders=ORDERS, items=ITEMS)) as run:
        for verb in ("delete", "update"):
            for change in CHANGES:
                predicate = "own" if change == "own" else "name"
                forms = {
                    "key-selecting": emitted(run, verb, predicate),
                    "in-place": IN_PLACE[(verb, predicate)],
                }
                for form, statement in forms.items():
                    for isolation in SPELLING:
                        observed = run_schedule(run, isolation, change, statement)
                        expected = RECORDED[(change, form, isolation)]
                        rows.append(
                            {
                                "verb": verb,
                                "change": change,
                                "form": form,
                                "isolation": isolation,
                                "sql": statement[0],
                                "expected": expected,
                                "agrees": observed["class"] == expected,
                                **observed,
                            }
                        )
    disagreements = [row for row in rows if not row["agrees"]]
    for row in rows:
        mark = "ok" if row["agrees"] else "DISAGREES"
        print(
            f"{row['verb']:6} {row['change']:11} {row['form']:13} {row['isolation']:15} "
            f"{row['class']:22} expected {row['expected']:22} {mark}",
            file=sys.stderr,
        )
    from pathlib import Path

    emit({"driver": "predicate_in_place", "schedules": rows}, Path(args.out) if args.out else None)
    if args.compare and disagreements:
        print(
            f"{len(disagreements)} schedule(s) disagree with the recorded COR-211 table",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
