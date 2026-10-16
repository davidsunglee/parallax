"""What every transaction-isolation driver shares.

A driver runs inside one arm's Python workspace (``capture.py`` starts it with
``uv run --project <arm>/languages/python``), so everything here must exist in
every arm a checkpoint measures. The measured work goes through the public
Snapshot API; provisioning and SQL recording use the conformance tooling the
corpus runners already rely on.
"""

import argparse
import datetime as dt
import json
import platform
import statistics
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from parallax.conformance import constants
from parallax.conformance._decoration import DecoratingAdapter
from parallax.conformance.models import accepted_model_of
from parallax.conformance.profile import profile_for
from parallax.core import (
    ONE_TO_MANY,
    Attr,
    Bitemporal,
    DomainModel,
    Entity,
    Int32,
    Rel,
    TxTemporal,
    attr,
    rel,
)
from parallax.snapshot import ScopedDatabase, connect

ISOLATIONS = ("read_committed", "repeatable_read")
NAMESPACE = "cor214"
UTC = dt.UTC


class Account(Entity, table="account", namespace=NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str] = attr(max_length=64)
    balance: Attr[Decimal] = attr(precision=18, scale=2)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class Balance(TxTemporal, table="balance", namespace=NAMESPACE):
    id: Attr[int] = attr(primary_key=True, column="bal_id")
    acct_num: Attr[str] = attr(max_length=32)
    value: Attr[Decimal] = attr(column="val", precision=18, scale=2)


class Position(Bitemporal, table="position", namespace=NAMESPACE):
    id: Attr[int] = attr(primary_key=True, column="pos_id")
    acct_num: Attr[str] = attr(max_length=32)
    value: Attr[Decimal] = attr(column="val", precision=18, scale=2)


class Order(Entity, table="orders", namespace=NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=255)
    items: Rel[tuple["OrderItem", ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "order_id"))


class OrderItem(Entity, table="order_item", namespace=NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    sku: Attr[str] = attr(max_length=32)
    order: Rel[Order | None] = rel(reverse_of="items")


MODEL = DomainModel(Account, Balance, Position, Order, OrderItem)

EPOCH = "2024-01-01T00:00:00.000000Z"
INFINITY = "infinity"


def accounts(count: int) -> list[dict[str, object]]:
    return [
        {"id": key, "owner": f"owner-{key}", "balance": "100.00", "version": 1}
        for key in range(1, count + 1)
    ]


def balances(count: int) -> list[dict[str, object]]:
    return [
        {
            "id": key,
            "acctNum": f"acct-{key}",
            "value": "100.00",
            "txStart": EPOCH,
            "txEnd": INFINITY,
        }
        for key in range(1, count + 1)
    ]


def positions(count: int) -> list[dict[str, object]]:
    return [
        {
            "id": key,
            "acctNum": f"acct-{key}",
            "value": "100.00",
            "validStart": EPOCH,
            "validEnd": INFINITY,
            "txStart": EPOCH,
            "txEnd": INFINITY,
        }
        for key in range(1, count + 1)
    ]


def fixtures(
    *,
    account_rows: int = 0,
    balance_rows: int = 0,
    position_rows: int = 0,
    orders: Sequence[Mapping[str, object]] = (),
    items: Sequence[Mapping[str, object]] = (),
) -> dict[str, list[Mapping[str, object]]]:
    return {
        f"{NAMESPACE}.Account": list(accounts(account_rows)),
        f"{NAMESPACE}.Balance": list(balances(balance_rows)),
        f"{NAMESPACE}.Position": list(positions(position_rows)),
        f"{NAMESPACE}.Order": list(orders),
        f"{NAMESPACE}.OrderItem": list(items),
    }


def arguments(
    description: str, *, extra: Callable[[argparse.ArgumentParser], None] | None = None
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--isolation", choices=ISOLATIONS, default="read_committed")
    parser.add_argument("--smoke", action="store_true", help="tiny samples; a tooling check only")
    parser.add_argument("--out", type=Path, help="write the JSON report here instead of stdout")
    if extra is not None:
        extra(parser)
    return parser.parse_args()


def emit(document: Mapping[str, object], out: Path | None) -> None:
    text = json.dumps(document, indent=2, sort_keys=True, default=str) + "\n"
    if out is None:
        sys.stdout.write(text)
    else:
        out.write_text(text)


@contextmanager
def provisioned(rows: Mapping[str, Sequence[Mapping[str, object]]]) -> Iterator[Any]:
    """A pinned PostgreSQL container holding ``MODEL``'s schema and ``rows``."""
    with profile_for("pg-full").provisioned() as run:
        run.reset(accepted_model_of(MODEL), rows)
        yield run


def reset(run: Any, rows: Mapping[str, Sequence[Mapping[str, object]]]) -> None:
    run.reset(accepted_model_of(MODEL), rows)


def pooled(run: Any, size: int) -> Any:
    """``run``'s database behind a pool of exactly ``size`` connections."""
    from parallax.postgres import PoolOptions

    return run.configured(pool=PoolOptions(min_size=size, max_size=size))


@contextmanager
def scoped(adapter: Any) -> Iterator[ScopedDatabase]:
    with connect(adapter, MODEL) as root:
        yield root.using_database_login()


# --------------------------------------------------------------- recording


class Recording:
    """Every statement the decorated connections ran, in order, per thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.statements: list[dict[str, object]] = []

    def record(self, kind: str, sql: str, binds: Sequence[object]) -> None:
        with self._lock:
            self.statements.append(
                {
                    "thread": threading.current_thread().name,
                    "kind": kind,
                    "sql": sql,
                    "binds": [str(bind) for bind in binds],
                    "at": time.perf_counter(),
                }
            )

    def take(self) -> list[dict[str, object]]:
        with self._lock:
            taken, self.statements = self.statements, []
        return taken


class _RecordingConnection:
    def __init__(self, inner: Any, recording: Recording) -> None:
        self._inner = inner
        self._recording = recording
        transport = inner.ordered_write_transport
        self._transport = None if transport is None else self._recorded_transport(transport)

    def _recorded_transport(
        self, transport: Callable[[Sequence[Any]], Any]
    ) -> Callable[[Sequence[Any]], Any]:
        def send(statements: Sequence[Any]) -> Any:
            for statement in statements:
                self._recording.record("write", statement.sql, tuple(statement.binds))
            return transport(statements)

        return send

    @property
    def dialect(self) -> Any:
        return self._inner.dialect

    @property
    def ordered_write_transport(self) -> Any:
        return self._transport

    def execute(self, sql: str, binds: Sequence[Any], document_reads: Sequence[Any] = ()) -> Any:
        self._recording.record("read", sql, binds)
        return self._inner.execute(sql, binds, document_reads)

    def execute_pipeline(self, statements: Sequence[Any]) -> Any:
        for statement in statements:
            self._recording.record("read", statement.sql, statement.binds)
        return self._inner.execute_pipeline(statements)

    def execute_write(self, sql: str, binds: Sequence[Any]) -> int:
        self._recording.record("write", sql, binds)
        return self._inner.execute_write(sql, binds)

    def transaction(self, body: Callable[[Any], Any], **options: Any) -> Any:
        return self._inner.transaction(lambda _connection: body(self), **options)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def recorded(adapter: Any) -> tuple[Any, Recording]:
    recording = Recording()
    return DecoratingAdapter(
        adapter, lambda inner: _RecordingConnection(inner, recording)
    ), recording


# ---------------------------------------------------------------- observing


@contextmanager
def observer(run: Any) -> Iterator[Any]:
    """An autocommit session of its own, so each read sees the server now."""
    with closing(run.control(autocommit=True)) as control:
        yield control


def scalar(control: Any, sql: str, binds: Sequence[object] = ()) -> Any:
    (row,) = control.execute(sql, list(binds))
    return row[0]


ACTIVITY = (
    "select pid, state, wait_event_type, wait_event, age(backend_xmin) as xmin_age, "
    "left(query, 160) as query from pg_stat_activity "
    "where datname = current_database() and pid <> pg_backend_pid() "
    "and backend_type = 'client backend' "
    "order by pid"
)
ACTIVITY_COLUMNS = ("pid", "state", "waitEventType", "waitEvent", "xminAge", "query")


def activity(control: Any) -> list[dict[str, object]]:
    return [dict(zip(ACTIVITY_COLUMNS, row, strict=True)) for row in control.execute(ACTIVITY, [])]


def lock_waits(control: Any) -> int:
    return int(
        scalar(
            control,
            "select count(*) from pg_stat_activity "
            "where datname = current_database() and wait_event_type = 'Lock'",
        )
    )


def await_lock_wait(control: Any, *, bound: float = 10.0) -> bool:
    deadline = time.monotonic() + bound
    while time.monotonic() < deadline:
        if lock_waits(control):
            return True
        time.sleep(0.01)
    return False


_SETTINGS = (
    "server_version",
    "default_transaction_isolation",
    "max_connections",
    "shared_buffers",
    "synchronous_commit",
    "wal_level",
    "autovacuum",
    "lock_timeout",
    "deadlock_timeout",
)


def conditions(control: Any, isolation: str, **workload: object) -> dict[str, object]:
    """The server, settings, and workload a report was taken under."""
    return {
        "isolation": isolation,
        "image": constants.POSTGRES_IMAGE,
        "version": scalar(control, "select version()"),
        "settings": {name: scalar(control, f"show {name}") for name in _SETTINGS},
        "cpython": platform.python_version(),
        "workload": dict(workload),
    }


# ----------------------------------------------------------------- outcomes


def failure(exc: BaseException) -> dict[str, object]:
    """A raised failure as a driver reports it, unwrapped from its execution
    context and named by type, neutral category, and native code."""
    cause = getattr(exc, "cause", None)
    if type(exc).__name__ == "ExecutionFailure" and isinstance(cause, BaseException):
        exc = cause
    return {
        "type": type(exc).__name__,
        "category": getattr(exc, "category", None),
        "nativeCode": getattr(exc, "native_code", None),
        "notes": list(getattr(exc, "__notes__", ())),
    }


def percentiles(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None}
    if len(values) == 1:
        return {"p50": values[0], "p95": values[0], "p99": values[0]}
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return {"p50": cuts[49], "p95": cuts[94], "p99": cuts[98]}


class Gate:
    """Named one-shot signals two transaction threads hand each other."""

    def __init__(self) -> None:
        self._events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def _event(self, name: str) -> threading.Event:
        with self._lock:
            return self._events.setdefault(name, threading.Event())

    def open(self, name: str) -> None:
        self._event(name).set()

    def wait(self, name: str, *, bound: float = 30.0) -> None:
        if not self._event(name).wait(timeout=bound):
            raise TimeoutError(f"no transaction opened {name!r} within {bound}s")


def concurrently(*bodies: Callable[[], object]) -> list[object]:
    """Run each body on its own thread; answer each one's result or failure."""
    results: list[object] = [None] * len(bodies)

    def run(index: int, body: Callable[[], object]) -> None:
        try:
            results[index] = body()
        except BaseException as exc:  # reported as the body's outcome
            results[index] = exc

    threads = [
        threading.Thread(target=run, args=(index, body), name=f"txn-{index}")
        for index, body in enumerate(bodies)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    return results
