"""Take one isolated Snapshot delivery Budget Contract cell reading.

This script is imported by nothing. It is the sole report-side reader of the
whole-interpreter memory instruments and answers its parent with one JSON line.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import json
import sys
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from time import perf_counter
from types import TracebackType
from typing import Any, Final, cast

from parallax.conformance.budget import BudgetContract
from parallax.conformance.story_models import ORDERS_MODEL
from parallax.conformance.workloads import Workload, catalog
from parallax.core.db_port import (
    CleanupResult,
    DatabaseConnection,
    DocumentReadOrdinals,
    MappingRow,
    PipelineStatement,
    Returned,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres import PostgresAdapter
from parallax.snapshot.handle import Database

WORKSPACE: Final = Path(__file__).resolve().parents[1]
INSTRUMENT_MODULE: Final = WORKSPACE / "tests" / "unit" / "memory_instruments.py"
SUPPORT_MODULE: Final = WORKSPACE / "tests" / "unit" / "_snapshot_materialization_support.py"
sys.path.insert(0, str(WORKSPACE))

from tests.unit import memory_instruments  # noqa: E402

if Path(memory_instruments.__file__ or "").resolve() != INSTRUMENT_MODULE:
    raise ImportError(
        f"this reading requires {INSTRUMENT_MODULE}, but resolved {memory_instruments.__file__}"
    )

from tests._support.db_port import projected_rows  # noqa: E402
from tests.unit import _snapshot_materialization_support as stress_support  # noqa: E402

if Path(stress_support.__file__ or "").resolve() != SUPPORT_MODULE:
    raise ImportError(
        f"this reading requires {SUPPORT_MODULE}, but resolved {stress_support.__file__}"
    )

from tests.unit.memory_instruments import Seam, retained, untraced  # noqa: E402

PROVIDER_FREE_IDS: Final = frozenset({"conventional-fanout", "duplicate-include"})


def _order_row(row: Mapping[str, object]) -> MappingRow:
    return {
        "id": row["id"],
        "name": row["name"],
        "sku": row["sku"],
        "qty": row["qty"],
        "price": row["price"],
        "active": row["active"],
        "ordered_on": dt.date.fromisoformat(cast("str", row["orderedOn"])),
        "parallax_seek_0": row["id"],
    }


def _item_row(row: Mapping[str, object]) -> MappingRow:
    return {
        "id": row["id"],
        "order_id": row["orderId"],
        "sku": row["sku"],
        "quantity": row["quantity"],
        "shipped_on": dt.date.fromisoformat(cast("str", row["shippedOn"])),
    }


_RETURNED: Final[CleanupResult] = Returned()


class _SoleScope:
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
        del exc_type, exc, traceback
        self._left = True


class _SoleRuntime:
    dialect: Dialect = POSTGRES
    __slots__ = ("_connection",)

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection

    @property
    def pool_metrics(self) -> None:
        return None

    def connection(self) -> _SoleScope:
        return _SoleScope(self._connection)

    def close(self) -> None:
        return


class CatalogPort:
    """Provider-free positional rows for the two catalog workloads that grade CPU."""

    dialect: Dialect = POSTGRES
    __slots__ = ("_delivered", "_fanout", "_items", "_orders")

    def __init__(self, workload: Workload, total: int) -> None:
        if workload.id not in PROVIDER_FREE_IDS:
            raise ValueError(f"{workload.id} has no provider-free CPU cell")
        rows = workload.rows(total)
        self._fanout = rows.fanout
        self._orders = rows.entity("parallax.compatibility.Order")
        self._items = rows.entity("parallax.compatibility.OrderItem")
        self._delivered = 0

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del document_reads
        if "order_item t0" in sql:
            parents = cast("list[int]", binds[0])
            return projected_rows(
                sql,
                (
                    _item_row(row)
                    for parent in parents
                    for row in self._items[(parent - 1) * self._fanout : parent * self._fanout]
                ),
            )
        limited = " limit " in sql
        size = cast("int", binds[-1]) if limited else len(self._orders)
        taken = min(size, len(self._orders) - self._delivered)
        selected = self._orders[self._delivered : self._delivered + taken]
        self._delivered += taken - 1 if taken == size and limited else taken
        return projected_rows(sql, (_order_row(row) for row in selected))

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return [
            self.execute(statement.sql, statement.binds, statement.document_reads)
            for statement in statements
        ]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql, binds
        raise NotImplementedError

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
    ) -> TransactionOutcome[T]:
        del body, isolation
        raise NotImplementedError


def _eager(database: Database, workload: Workload) -> int:
    return len(database.wire.find(workload.query).results())


def _streamed(database: Database, workload: Workload, page_size: int) -> int:
    count = 0
    with database.wire.stream(workload.query, batch_size=page_size) as stream:
        for _root in stream:
            count += 1
    return count


def _last_streamed(database: Database, workload: Workload, page_size: int) -> object:
    latest: object | None = None
    with database.wire.stream(workload.query, batch_size=page_size) as stream:
        for root in stream:
            latest = root
    assert latest is not None
    return latest


def _first(database: Database, workload: Workload, page_size: int) -> object:
    with database.wire.stream(workload.query, batch_size=page_size) as stream:
        return next(iter(stream))


def _timed(work: Callable[[], object], *, warmups: int, measured: int) -> tuple[float, ...]:
    with untraced():
        for _ in range(warmups):
            work()
        samples: list[float] = []
        for _ in range(measured):
            started = perf_counter()
            work()
            samples.append((perf_counter() - started) * 1_000)
    return tuple(samples)


def _page_size(path: str) -> int:
    for size in (128, 32, 1):
        if f"page{size}" in path:
            return size
    raise ValueError(f"{path}: no page size")


def _live_timing(
    workload: Workload,
    path: str,
    roots: int,
    connection_info: str,
    *,
    warmups: int,
    measured: int,
) -> tuple[float, str, tuple[float, ...]]:
    with Database.connect(PostgresAdapter(connection_info), workload.domain_model) as database:
        work: Callable[[], object]
        if path.startswith("live.eager"):

            def eager_work() -> int:
                return _eager(database, workload)

            work = eager_work
        elif path.startswith("live.page"):

            def stream_work() -> int:
                return _streamed(database, workload, _page_size(path))

            work = stream_work
        elif path.startswith("firstResult.page"):

            def first_work() -> object:
                return _first(database, workload, _page_size(path))

            work = first_work
        else:
            raise ValueError(path)
        milliseconds = _timed(work, warmups=warmups, measured=measured)
    if path.endswith("minRootsPerSecond"):
        samples = tuple(roots * 1_000 / elapsed for elapsed in milliseconds)
        return float(sorted(samples)[len(samples) // 2]), "roots/s", samples
    return float(sorted(milliseconds)[len(milliseconds) // 2]), "ms", milliseconds


def _provider_free(
    workload: Workload, path: str, roots: int, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    page_size = 32 if ".page32." in path else None

    def work() -> int:
        database = Database(_SoleRuntime(CatalogPort(workload, roots)), ORDERS_MODEL)
        try:
            return (
                _eager(database, workload)
                if page_size is None
                else _streamed(database, workload, page_size)
            )
        finally:
            database.close()

    milliseconds = _timed(work, warmups=warmups, measured=measured)
    if path.endswith("minRootsPerSecond"):
        samples = tuple(roots * 1_000 / elapsed for elapsed in milliseconds)
        return float(sorted(samples)[len(samples) // 2]), "roots/s", samples
    return float(sorted(milliseconds)[len(milliseconds) // 2]), "ms", milliseconds


def _live_memory(
    workload: Workload,
    path: str,
    roots: int,
    connection_info: str,
) -> tuple[float, str, tuple[float, ...]]:
    page_size = (
        (_page_size(path) if path.startswith("streamedMemory.page") else 1)
        if path.startswith("streamedMemory.")
        else None
    )
    with Database.connect(PostgresAdapter(connection_info), workload.domain_model) as database:
        if page_size is None:
            database.wire.find(workload.query)
        else:
            _last_streamed(database, workload, page_size)
        gc.collect()
        gc.collect()
        tracemalloc.start()
        try:
            before, _ = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            if page_size is None:
                held = database.wire.find(workload.query)
                gc.collect()
                current, peak = tracemalloc.get_traced_memory()
            else:
                held = _last_streamed(database, workload, page_size)
                gc.collect()
                current, peak = tracemalloc.get_traced_memory()
            value = current - before if path.endswith("retainedKiB") else peak - before
            assert held is not None
        finally:
            tracemalloc.stop()
    kib = max(0, value) / 1_024
    return kib, "KiB", (kib,)


class _PreparedStress:
    __slots__ = ("bound", "layout", "meta", "model", "plan", "reads", "rows")

    def __init__(self, layout: Any) -> None:
        from parallax.snapshot import prepare_model
        from parallax.snapshot.handle._publication import read_projection

        self.layout = layout
        self.meta = stress_support.metamodel(layout)
        self.model = read_projection(
            prepare_model(stress_support.workload(layout), edition="snapshot-delivery-report")
        ).model
        self.plan = stress_support.fetch_plan(stress_support.query(layout, self.meta), self.meta)
        self.reads = stress_support.compiled_levels(layout, self.plan, self.meta)
        self.bound = stress_support.prepared_levels(self.model, self.reads)
        self.rows = stress_support.rows_per_level(layout, self.model, self.plan, self.reads)

    def run(self) -> object:
        return stress_support.batch(self.model, self.plan, self.bound, self.rows)

    def seam(self) -> Seam:
        def run(sample: Callable[[], None]) -> None:
            page = self.run()
            sample()
            assert page is not None

        return run


def _stress_layout(workload: str) -> Any:
    name = "columns" if workload == "stress-columns" else "document"
    return next(layout for layout in stress_support.LAYOUTS if layout == name)


def _stress_timing(
    prepared: _PreparedStress, path: str, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    milliseconds = _timed(prepared.run, warmups=warmups, measured=measured)
    projections = stress_support.PROJECTIONS_PER_BATCH
    if path.endswith("maxUsPerProjection"):
        samples = tuple(elapsed * 1_000 / projections for elapsed in milliseconds)
        return float(sorted(samples)[len(samples) // 2]), "us/projection", samples
    samples = tuple(projections * 1_000 / elapsed for elapsed in milliseconds)
    return float(sorted(samples)[len(samples) // 2]), "projections/s", samples


def _stress_memory(prepared: _PreparedStress, path: str) -> tuple[float, str, tuple[float, ...]]:
    if path.endswith("preparedSetKiB"):

        def compiled(sample: Callable[[], None]) -> None:
            plan = stress_support.fetch_plan(
                stress_support.query(prepared.layout, prepared.meta), prepared.meta
            )
            reads = stress_support.compiled_levels(prepared.layout, plan, prepared.meta)
            bound = stress_support.prepared_levels(prepared.model, reads)
            sample()
            assert bound is not None

        tracemalloc.start()
        try:
            value = retained(compiled) / 1_024
        finally:
            tracemalloc.stop()
        return value, "KiB", (value,)
    tracemalloc.start()
    try:
        retained_bytes = retained(prepared.seam())
        gc.collect()
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        page = prepared.run()
        _, peak = tracemalloc.get_traced_memory()
        peak_bytes = peak - before
        assert page is not None
    finally:
        tracemalloc.stop()
    projections = stress_support.PROJECTIONS_PER_BATCH
    if path.endswith("retainedBPerProjection"):
        value, reading_unit = retained_bytes / projections, "B/projection"
    elif path.endswith("transientBPerProjection"):
        value, reading_unit = (peak_bytes - retained_bytes) / projections, "B/projection"
    else:
        value, reading_unit = peak_bytes / 1_024, "KiB"
    value = max(0.0, value)
    return value, reading_unit, (value,)


def measure(
    workload: Workload,
    path: str,
    roots: int,
    connection_info: str | None,
    *,
    warmups: int,
    measured: int,
) -> tuple[float, str, tuple[float, ...]]:
    if path.startswith("providerFreeCpu."):
        return _provider_free(workload, path, roots, warmups=warmups, measured=measured)
    if path.startswith("stress."):
        prepared = _PreparedStress(_stress_layout(workload.id))
        return (
            _stress_memory(prepared, path)
            if path.endswith(
                (
                    "retainedBPerProjection",
                    "transientBPerProjection",
                    "peakFor64KiB",
                    "preparedSetKiB",
                )
            )
            else _stress_timing(prepared, path, warmups=warmups, measured=measured)
        )
    if connection_info is None:
        raise ValueError(f"{path} requires --connection-info")
    if path.startswith(("eagerMemory.", "streamedMemory.")):
        return _live_memory(workload, path, roots, connection_info)
    return _live_timing(
        workload,
        path,
        roots,
        connection_info,
        warmups=warmups,
        measured=measured,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--cell", required=True)
    parser.add_argument("--roots", required=True, type=int)
    parser.add_argument("--warmups", required=True, type=int)
    parser.add_argument("--measured", required=True, type=int)
    parser.add_argument("--connection-info")
    args = parser.parse_args(argv)
    contract = BudgetContract.load()
    if (args.warmups, args.measured) != (
        contract.timing_warmups,
        contract.timing_measured,
    ):
        parser.error("timing sampling counts do not match the Budget Contract")
    workload = catalog(contract)[args.workload]
    if args.cell not in {cell.path for cell in contract.cells(args.workload)}:
        parser.error(f"{args.workload}.{args.cell} is not a Budget Contract cell")
    value, reading_unit, samples = measure(
        workload,
        args.cell,
        args.roots,
        args.connection_info,
        warmups=args.warmups,
        measured=args.measured,
    )
    print(json.dumps({"value": value, "unit": reading_unit, "samples": samples}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
