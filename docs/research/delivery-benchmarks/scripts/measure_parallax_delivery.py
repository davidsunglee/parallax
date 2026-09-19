from __future__ import annotations

import cProfile
import datetime as dt
import gc
import json
import platform
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any, Final, cast

PYTHON_ROOT: Final = Path(__file__).resolve().parents[4] / "languages" / "python"
sys.path.insert(0, str(PYTHON_ROOT))

from parallax.conformance.profile import profile_for  # noqa: E402
from parallax.conformance.story_models import (  # noqa: E402
    ORDERS_MODEL,
    POSITION_MODEL,
    Order,
    Position,
)
from parallax.core import LATEST  # noqa: E402
from parallax.core.base import PresentDocument  # noqa: E402
from parallax.core.db_port import (  # noqa: E402
    CleanupResult,
    DatabaseConnection,
    DocumentReadOrdinals,
    PipelineStatement,
    Returned,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect  # noqa: E402
from parallax.core.entity._model import model_of  # noqa: E402
from parallax.snapshot import connect  # noqa: E402
from parallax.snapshot.handle import Database, ScopedDatabase  # noqa: E402
from tests._support.db_port import projected_row  # noqa: E402
from tests._support.mirrored_models import (  # noqa: E402
    DOCUMENT_LAYOUT_MODEL,
    Ledger,
    Traveler,
)

ROOTS: Final = 200
FANOUT: Final = 4
PAGE_SIZES: Final = (1, 8, 32, 128)
WARMUPS: Final = 3
PROVIDER_FREE_REPEATS: Final = 10
POSTGRES_REPEATS: Final = 5


@dataclass(frozen=True)
class Timing:
    wall_ms: float
    cpu_ms: float
    first_ms: float
    roots_per_second: float
    cpu_share: float


@dataclass(frozen=True)
class Memory:
    retained_bytes: int
    peak_bytes: int
    transient_bytes: int


@dataclass(frozen=True)
class Reading:
    provider: str
    workload: str
    delivery: str
    page_size: int | None
    roots: int
    timing: Timing
    memory: Memory


@dataclass(frozen=True)
class Contributor:
    provider: str
    workload: str
    delivery: str
    name: str
    calls: int
    self_ms: float
    cumulative_ms: float


_RETURNED: Final[CleanupResult] = Returned()


class _Scope:
    __slots__ = ("_connection", "_left")

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection
        self._left = False

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return _RETURNED if self._left else None

    def __enter__(self) -> DatabaseConnection:
        return self._connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._left = True


class _Runtime:
    dialect: Dialect = POSTGRES

    __slots__ = ("_connection",)

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection

    @property
    def pool_metrics(self) -> None:
        return None

    @property
    def login_identity(self) -> str:
        return "delivery-research"

    def login_execution(self) -> _Runtime:
        return self

    def principal_execution(self, authorization: object) -> _Runtime:
        del authorization
        return self

    def new_context(self) -> _Scope:
        return _Scope(self._connection)

    def close(self) -> None:
        return None


def _order_row(order_id: int) -> Row:
    return {
        "id": order_id,
        "name": f"order-{order_id}",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
        "parallax_seek_0": order_id,
    }


def _item_row(item_id: int, order_id: int) -> Row:
    return {
        "id": item_id,
        "order_id": order_id,
        "sku": "SKU",
        "quantity": 1,
        "shipped_on": dt.date(2024, 2, 1),
    }


class GeneratingPort:
    dialect: Dialect = POSTGRES

    __slots__ = ("_delivered", "_page", "_total")

    def __init__(self, total: int) -> None:
        self._total = total
        self._delivered = 0
        self._page: tuple[int, ...] = ()

    def reset(self) -> None:
        self._delivered = 0
        self._page = ()

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del document_reads
        if "order_item t0" in sql:
            return [
                _item_row(parent * 100 + offset, parent)
                for parent in self._page
                for offset in range(FANOUT)
            ]
        if " limit " in sql.lower():
            requested = cast("int", binds[-1])
            first = cast("int", binds[0]) + 1 if "t0.id >" in sql else 1
            last = min(first + requested, self._total + 1)
        else:
            first, last = 1, self._total + 1
        self._page = tuple(range(first, last))
        self._delivered = last - 1
        return [projected_row(sql, _order_row(order_id)) for order_id in self._page]

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return [
            self.execute(statement.sql, statement.binds, statement.document_reads)
            for statement in statements
        ]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        raise NotImplementedError


@dataclass(frozen=True)
class Workload:
    name: str
    database: ScopedDatabase
    query: Any
    reset: Callable[[], None]
    roots: int = ROOTS


def _operation(workload: Workload, delivery: str, page_size: int | None) -> tuple[object, int]:
    workload.reset()
    if delivery == "eager":
        return workload.database.find(workload.query), workload.roots
    assert page_size is not None
    last: object = None
    count = 0
    with workload.database.stream(workload.query, batch_size=page_size) as stream:
        for last in stream:
            count += 1
    if count != workload.roots:
        raise AssertionError((workload.name, count, workload.roots))
    return last, count


def _timing(workload: Workload, delivery: str, page_size: int | None, repeats: int) -> Timing:
    for _ in range(WARMUPS):
        _operation(workload, delivery, page_size)
    wall: list[float] = []
    cpu: list[float] = []
    first: list[float] = []
    for _ in range(repeats):
        workload.reset()
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        if delivery == "eager":
            held = workload.database.find(workload.query)
            first_at = time.perf_counter()
            count = workload.roots
        else:
            assert page_size is not None
            count = 0
            held = None
            with workload.database.stream(workload.query, batch_size=page_size) as stream:
                iterator = iter(stream)
                try:
                    held = next(iterator)
                    count = 1
                except StopIteration:
                    pass
                first_at = time.perf_counter()
                for held in iterator:
                    count += 1
        cpu_end = time.process_time()
        wall_end = time.perf_counter()
        if count != workload.roots:
            raise AssertionError((workload.name, count, workload.roots, held))
        wall.append(wall_end - wall_start)
        cpu.append(cpu_end - cpu_start)
        first.append(first_at - wall_start)
    wall_s = statistics.median(wall)
    cpu_s = statistics.median(cpu)
    return Timing(
        wall_ms=wall_s * 1_000,
        cpu_ms=cpu_s * 1_000,
        first_ms=statistics.median(first) * 1_000,
        roots_per_second=workload.roots / wall_s,
        cpu_share=cpu_s / wall_s,
    )


def _memory(workload: Workload, delivery: str, page_size: int | None) -> Memory:
    for _ in range(WARMUPS):
        _operation(workload, delivery, page_size)
    gc.collect()
    gc.collect()
    tracemalloc.start()
    try:
        floor, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        held, _ = _operation(workload, delivery, page_size)
        gc.collect()
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        if held is None:
            raise AssertionError("the measured operation retained no result")
    finally:
        tracemalloc.stop()
    retained = current - floor
    return Memory(
        retained_bytes=retained,
        peak_bytes=peak - floor,
        transient_bytes=peak - current,
    )


def _reading(
    provider: str,
    workload: Workload,
    delivery: str,
    page_size: int | None,
    repeats: int,
) -> Reading:
    return Reading(
        provider=provider,
        workload=workload.name,
        delivery=delivery,
        page_size=page_size,
        roots=workload.roots,
        timing=_timing(workload, delivery, page_size, repeats),
        memory=_memory(workload, delivery, page_size),
    )


def _profile(
    provider: str,
    workload: Workload,
    delivery: str,
    page_size: int | None,
    repeats: int,
) -> list[Contributor]:
    profiler = cProfile.Profile()
    for _ in range(repeats):
        profiler.runcall(_operation, workload, delivery, page_size)
    rows: list[tuple[str, int, float, float]] = []
    for entry in profiler.getstats():
        code = entry.code
        if not hasattr(code, "co_filename"):
            continue
        filename = cast("str", code.co_filename)
        if "/packages/parallax-" not in filename:
            continue
        label = f"{Path(filename).name}:{code.co_name}"
        rows.append((label, entry.callcount, entry.inlinetime, entry.totaltime))
    return [
        Contributor(provider, workload.name, delivery, name, calls, own * 1_000, cumulative * 1_000)
        for name, calls, own, cumulative in sorted(rows, key=lambda item: item[2], reverse=True)[:10]
    ]


def _orders_fixtures() -> dict[str, object]:
    return {
        "parallax.compatibility.Order": [
            {
                "id": root,
                "name": f"order-{root}",
                "sku": "A-100",
                "qty": 5,
                "price": "10.50",
                "active": True,
                "orderedOn": "2024-01-05",
            }
            for root in range(1, ROOTS + 1)
        ],
        "parallax.compatibility.OrderItem": [
            {
                "id": root * 100 + offset,
                "orderId": root,
                "sku": "SKU",
                "quantity": 1,
                "shippedOn": "2024-02-01",
            }
            for root in range(1, ROOTS + 1)
            for offset in range(FANOUT)
        ],
    }


def _document_fixtures() -> dict[str, object]:
    fixtures: dict[str, object] = {
        "parallax.compatibility.Traveler": [
            {
                "id": root,
                "displayName": f"traveler-{root}",
                "score": root,
                "joinedOn": "2026-01-15",
                "note": "north wing",
                "address": {"city": "Oslo", "geo": {"country": "NO"}},
                "tags": [{"label": "founder"}, {"label": "staff"}],
            }
            for root in range(1, ROOTS + 1)
        ],
        "parallax.compatibility.Trip": [
            {
                "id": root * 100 + offset,
                "travelerId": root,
                "destination": "Oslo",
                "nights": 3,
            }
            for root in range(1, ROOTS + 1)
            for offset in range(FANOUT)
        ],
        "parallax.compatibility.Ledger": [
            {
                "id": root,
                "version": 1,
                "label": f"ledger-{root}",
                "balance": "250.00",
                "details": {"code": "opening"},
            }
            for root in range(1, ROOTS + 1)
        ],
    }
    return fixtures


def _position_fixtures() -> dict[str, object]:
    return {
        "parallax.compatibility.Position": [
            {
                "id": root,
                "acctNum": f"acct-{root}",
                "value": "100.00",
                "validStart": "2024-01-01T00:00:00.000000Z",
                "validEnd": "infinity",
                "txStart": "2024-01-01T00:00:00.000000Z",
                "txEnd": "infinity",
            }
            for root in range(1, ROOTS + 1)
        ]
    }


def _measure_workloads(provider: str, workloads: Sequence[Workload], repeats: int) -> tuple[list[Reading], list[Contributor]]:
    readings: list[Reading] = []
    contributors: list[Contributor] = []
    for workload in workloads:
        readings.append(_reading(provider, workload, "eager", None, repeats))
        for page_size in PAGE_SIZES:
            readings.append(_reading(provider, workload, "stream", page_size, repeats))
        contributors.extend(_profile(provider, workload, "eager", None, 3))
        contributors.extend(_profile(provider, workload, "stream", 32, 3))
    return readings, contributors


@contextmanager
def _provider_free() -> Any:
    port = GeneratingPort(ROOTS)
    root = Database(_Runtime(port), ORDERS_MODEL)
    database = root.using_database_login()
    try:
        yield (
            Workload(
                "conventional-fanout",
                database,
                Order.where(Order.all).include(Order.items),
                port.reset,
            ),
            Workload(
                "duplicate-include",
                database,
                Order.where(Order.all).include(Order.items, Order.items_by_ship_date),
                port.reset,
            ),
        )
    finally:
        root.close()


def _live_workloads(run: Any) -> tuple[list[Reading], list[Contributor]]:
    readings: list[Reading] = []
    contributors: list[Contributor] = []

    run.reset(model_of(ORDERS_MODEL), _orders_fixtures())
    with connect(run.port, ORDERS_MODEL) as root:
        database = root.using_database_login()
        workloads = (
            Workload(
                "conventional-fanout",
                database,
                Order.where(Order.all).include(Order.items),
                lambda: None,
            ),
            Workload(
                "duplicate-include",
                database,
                Order.where(Order.all).include(Order.items, Order.items_by_ship_date),
                lambda: None,
            ),
        )
        new_readings, new_contributors = _measure_workloads(
            "postgres", workloads, POSTGRES_REPEATS
        )
        readings.extend(new_readings)
        contributors.extend(new_contributors)

    run.reset(model_of(DOCUMENT_LAYOUT_MODEL), _document_fixtures())
    with connect(run.port, DOCUMENT_LAYOUT_MODEL) as root:
        database = root.using_database_login()
        workloads = (
            Workload(
                "document-heavy",
                database,
                Traveler.where(Traveler.all).include(Traveler.trips),
                lambda: None,
            ),
            Workload(
                "versioned-document",
                database,
                Ledger.where(Ledger.all),
                lambda: None,
            ),
        )
        new_readings, new_contributors = _measure_workloads(
            "postgres", workloads, POSTGRES_REPEATS
        )
        readings.extend(new_readings)
        contributors.extend(new_contributors)

    run.reset(model_of(POSITION_MODEL), _position_fixtures())
    with connect(run.port, POSITION_MODEL) as root:
        database = root.using_database_login()
        workload = Workload(
            "bitemporal-current",
            database,
            Position.where(Position.all).as_of(valid_time=LATEST, tx_time=LATEST),
            lambda: None,
        )
        new_readings, new_contributors = _measure_workloads(
            "postgres", (workload,), POSTGRES_REPEATS
        )
        readings.extend(new_readings)
        contributors.extend(new_contributors)

    return readings, contributors


def main() -> None:
    readings: list[Reading] = []
    contributors: list[Contributor] = []
    with _provider_free() as workloads:
        new_readings, new_contributors = _measure_workloads(
            "provider-free", workloads, PROVIDER_FREE_REPEATS
        )
        readings.extend(new_readings)
        contributors.extend(new_contributors)
    with profile_for("pg-full").provisioned() as run:
        new_readings, new_contributors = _live_workloads(run)
        readings.extend(new_readings)
        contributors.extend(new_contributors)
    print(
        json.dumps(
            {
                "conditions": {
                    "python": platform.python_version(),
                    "platform": f"{sys.platform}/{platform.machine()}",
                    "roots": ROOTS,
                    "fanout": FANOUT,
                    "page_sizes": PAGE_SIZES,
                    "warmups": WARMUPS,
                    "provider_free_repeats": PROVIDER_FREE_REPEATS,
                    "postgres_repeats": POSTGRES_REPEATS,
                    "memory_scope": "Python allocations traced after Database/model preparation",
                },
                "readings": [asdict(reading) for reading in readings],
                "contributors": [asdict(contributor) for contributor in contributors],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
