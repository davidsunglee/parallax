"""Take one isolated Snapshot delivery reading: a Budget Contract cell, one
provider-free geometry read family address, one read-plan compilation address,
or one before/after control address.

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
from parallax.conformance.workloads import (
    PLAN_LEVEL_IDS,
    READ_GEOMETRY_ROOTS,
    STRUCTURAL_LAYOUTS,
    GeometryLevel,
    Workload,
    catalog,
)
from parallax.core.db_port import (
    DRIVER_MANAGED,
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
from parallax.core.entity import DomainModel
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.postgres import PostgresAdapter
from parallax.snapshot import prepare_model
from parallax.snapshot.handle import Database, ScopedDatabase
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._publication import read_projection
from parallax.snapshot.handle._read_plan import (
    DEFAULT_READ_PLAN_CACHE_CAPACITY,
    ReadPlan,
    ReadPlanCache,
)

WORKSPACE: Final = Path(__file__).resolve().parents[1]
INSTRUMENT_MODULE: Final = WORKSPACE / "tests" / "unit" / "memory_instruments.py"
SUPPORT_MODULE: Final = WORKSPACE / "tests" / "unit" / "_snapshot_materialization_support.py"
GEOMETRY_MODULE: Final = WORKSPACE / "tests" / "unit" / "_structural_geometry_support.py"
CONTROL_MODULE: Final = WORKSPACE / "tests" / "unit" / "_delivery_control_support.py"
sys.path.insert(0, str(WORKSPACE))

# `sys.path` gains the workspace above, so these imports cannot precede it; that is
# what the E402 suppression each one carries records.
from tests.unit import memory_instruments  # noqa: E402

if Path(memory_instruments.__file__ or "").resolve() != INSTRUMENT_MODULE:
    raise ImportError(
        f"this reading requires {INSTRUMENT_MODULE}, but resolved {memory_instruments.__file__}"
    )

from tests._support.db_port import projected_rows  # noqa: E402
from tests.unit import _delivery_control_support as control_support  # noqa: E402
from tests.unit import _snapshot_materialization_support as stress_support  # noqa: E402
from tests.unit import _structural_geometry_support as geometry_support  # noqa: E402

for module, expected_file in (
    (stress_support, SUPPORT_MODULE),
    (geometry_support, GEOMETRY_MODULE),
    (control_support, CONTROL_MODULE),
):
    if Path(module.__file__ or "").resolve() != expected_file:
        raise ImportError(f"this reading requires {expected_file}, but resolved {module.__file__}")

# E402 again, and imported below the guard proving each module is this workspace's own.
from tests.unit.memory_instruments import Seam, retained, untraced  # noqa: E402

PROVIDER_FREE_IDS: Final = frozenset({"conventional-fanout", "duplicate-include"})
GEOMETRY_PREFIX: Final = "read-"
GEOMETRY_METRICS: Final = ("elapsedUsPerRoot", "peakKiB", "retainedKiB")
PLAN_PREFIX: Final = "plan-"
PLAN_METRICS: Final = ("elapsedUs", "peakKiB", "retainedKiB")
PLAN_EDITION: Final = "snapshot-delivery-report"


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
_LOGIN: Final = "snapshot-delivery-report"


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

    @property
    def login_identity(self) -> str:
        return _LOGIN

    def login_execution(self) -> _SoleRuntime:
        return self

    def principal_execution(self, authorization: object) -> _SoleRuntime:
        del authorization
        return self

    def new_context(self) -> _SoleScope:
        return _SoleScope(self._connection)

    def close(self) -> None:
        return


class CatalogPort:
    """Provider-free positional rows for the two catalog workloads that grade CPU.

    One delivery consumes the root rows once; :meth:`reset` restores them for
    the next, so a root composed outside a window can serve every run inside it.
    """

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

    def reset(self) -> None:
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
            first_id = cast("int", self._orders[0]["id"])
            return projected_rows(
                sql,
                (
                    _item_row(row)
                    for parent in parents
                    for row in self._items[
                        (parent - first_id) * self._fanout : (parent - first_id + 1) * self._fanout
                    ]
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


def _eager(database: ScopedDatabase, workload: Workload) -> int:
    return len(database.wire.find(workload.query).results())


def _streamed(database: ScopedDatabase, workload: Workload, page_size: int) -> int:
    count = 0
    with database.wire.stream(workload.query, batch_size=page_size) as stream:
        for _root in stream:
            count += 1
    return count


def _last_streamed(
    database: ScopedDatabase,
    workload: Workload,
    page_size: int,
    *,
    collect_at_page_boundary: bool,
) -> object:
    latest: object | None = None
    with database.wire.stream(workload.query, batch_size=page_size) as stream:
        for count, root in enumerate(stream, start=1):
            latest = root
            if collect_at_page_boundary and count % page_size == 0:
                gc.collect()
    gc.collect()
    assert latest is not None
    return latest


def _first(database: ScopedDatabase, workload: Workload, page_size: int) -> object:
    with database.wire.stream(workload.query, batch_size=page_size) as stream:
        return next(iter(stream))


def _unprepared() -> None:
    """The preparation a seam that needs none between runs supplies."""


def _timed(
    work: Callable[[], object],
    *,
    warmups: int,
    measured: int,
    prepare: Callable[[], None] = _unprepared,
) -> tuple[float, ...]:
    """Elapsed milliseconds per measured run of ``work``, with ``prepare``
    restoring its precondition between runs and outside every timed region."""
    with untraced():
        for _ in range(warmups):
            prepare()
            work()
        samples: list[float] = []
        for _ in range(measured):
            prepare()
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
    with Database.connect(
        PostgresAdapter(connection_info, credentials=DRIVER_MANAGED), workload.domain_model
    ) as root:
        database = root.using_database_login()
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
        root = Database(_SoleRuntime(CatalogPort(workload, roots)), ORDERS_MODEL)
        database = root.using_database_login()
        try:
            return (
                _eager(database, workload)
                if page_size is None
                else _streamed(database, workload, page_size)
            )
        finally:
            root.close()

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
    *,
    collect_at_page_boundary: bool,
) -> tuple[float, str, tuple[float, ...]]:
    page_size = (
        (_page_size(path) if path.startswith("streamedMemory.page") else 1)
        if path.startswith("streamedMemory.")
        else None
    )
    with Database.connect(
        PostgresAdapter(connection_info, credentials=DRIVER_MANAGED), workload.domain_model
    ) as root:
        database = root.using_database_login()
        if page_size is None:
            database.wire.find(workload.query)
        else:
            _last_streamed(
                database, workload, page_size, collect_at_page_boundary=collect_at_page_boundary
            )
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
                held = _last_streamed(
                    database, workload, page_size, collect_at_page_boundary=collect_at_page_boundary
                )
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


def geometry_address(workload: str, path: str) -> tuple[GeometryLevel, str, str] | None:
    """The level, layout, and metric a geometry read address names, or absence
    for a Budget Contract address."""
    if not workload.startswith(GEOMETRY_PREFIX):
        return None
    level = geometry_support.level_named(workload.removeprefix(GEOMETRY_PREFIX))
    layout, _separator, metric = path.partition(".")
    if layout not in STRUCTURAL_LAYOUTS or metric not in GEOMETRY_METRICS:
        raise ValueError(f"{workload}.{path} is not a geometry read address")
    return level, layout, metric


def plan_address(workload: str, path: str) -> tuple[GeometryLevel, str, str] | None:
    """The level, layout, and metric a read-plan compilation address names, or
    absence for any other address."""
    if not workload.startswith(PLAN_PREFIX):
        return None
    level = geometry_support.level_named(workload.removeprefix(PLAN_PREFIX))
    if level.id not in PLAN_LEVEL_IDS:
        raise ValueError(f"{workload} is not a read-plan compilation level")
    layout, _separator, metric = path.partition(".")
    if layout not in STRUCTURAL_LAYOUTS or metric not in PLAN_METRICS:
        raise ValueError(f"{workload}.{path} is not a read-plan compilation address")
    return level, layout, metric


class ColdPlan:
    """One query's read plan compiled into an empty cache of production capacity.

    The prepared model, the validated query, and the cache itself are composed
    once, outside every window: model preparation is priced by the write member,
    preflight is query validation rather than planning, and production composes
    the cache when the handle is connected, before its first read. :meth:`plan`
    is the window — one ``ReadPlanCache.plan`` on a cache holding nothing — so
    what a window prices is the growth from an empty cache to one compiled
    entry, which is the plan production retains for the next delivery of that
    query. :meth:`reset` restores that empty cache, and every caller runs it
    outside the region it measures.
    """

    __slots__ = ("cache", "model", "query")

    def __init__(self, model: DomainModel, query: ObjectQuery[Any, Any]) -> None:
        self.model = read_projection(prepare_model(model, edition=PLAN_EDITION)).model
        self.query = preflight(object_query_node(query), model=self.model.meta, form="graph")
        self.cache = ReadPlanCache(DEFAULT_READ_PLAN_CACHE_CAPACITY)

    @classmethod
    def geometry(cls, level: GeometryLevel, layout: str) -> ColdPlan:
        """One geometry level's whole-table instance read under ``layout``."""
        selected = cast("geometry_support.Layout", layout)
        return cls(geometry_support.MODEL, geometry_support.read_query(level, selected))

    @classmethod
    def guarded(cls, width: int) -> ColdPlan:
        """The guarded include workload's read at ``width`` guarded positions."""
        return cls(control_support.GUARDED_MODEL, control_support.guarded_query(width))

    def plan(self) -> ReadPlan:
        return self.cache.plan(
            edition=PLAN_EDITION,
            model=self.model,
            dialect=POSTGRES,
            query=self.query,
            result_form="instance",
            preference=None,
        )

    def reset(self) -> None:
        self.cache = ReadPlanCache(DEFAULT_READ_PLAN_CACHE_CAPACITY)

    def cold(self, sample: Callable[[], None]) -> None:
        self.plan()
        sample()
        self.reset()

    def warm(self, sample: Callable[[], None]) -> None:
        self.plan()
        sample()


def _plan(
    level: GeometryLevel, layout: str, metric: str, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    """One geometry level's whole-table instance read compiled into an empty cache."""
    return _cold_plan(ColdPlan.geometry(level, layout), metric, warmups=warmups, measured=measured)


def _cold_plan(
    prepared: ColdPlan, metric: str, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    """``prepared``'s read compiled into its empty cache: each sample one
    compilation on a cache emptied outside the region it measures."""
    if metric == "elapsedUs":
        milliseconds = _timed(
            prepared.plan, warmups=warmups, measured=measured, prepare=prepared.reset
        )
        samples = tuple(elapsed * 1_000 for elapsed in milliseconds)
        return float(sorted(samples)[len(samples) // 2]), "us", samples
    if metric == "retainedKiB":
        tracemalloc.start()
        try:
            value = retained(prepared.cold) / 1_024
        finally:
            tracemalloc.stop()
        return value, "KiB", (value,)
    with untraced():
        for _ in range(warmups):
            prepared.reset()
            prepared.plan()
    prepared.reset()
    gc.collect()
    gc.collect()
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        held = prepared.plan()
        _, peak = tracemalloc.get_traced_memory()
        assert held is not None
    finally:
        tracemalloc.stop()
    value = max(0, peak - before) / 1_024
    return value, "KiB", (value,)


def _warm_plan(
    prepared: ColdPlan, metric: str, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    """``prepared``'s read hit on the cache already holding its one entry:
    the reuse a second delivery of the same query pays."""
    prepared.plan()
    if metric == "elapsedUs":
        milliseconds = _timed(prepared.plan, warmups=warmups, measured=measured)
        samples = tuple(elapsed * 1_000 for elapsed in milliseconds)
        return float(sorted(samples)[len(samples) // 2]), "us", samples
    tracemalloc.start()
    try:
        value = retained(prepared.warm) / 1_024
    finally:
        tracemalloc.stop()
    return value, "KiB", (value,)


def _traced(
    work: Callable[[], object],
    metric: str,
    *,
    prepare: Callable[[], None] = _unprepared,
) -> tuple[float, str, tuple[float, ...]]:
    """One traced run of ``work`` after one warm run of it: the bytes its
    product keeps reachable, or the high-water mark it rose to, above the level
    the process settled at before it, with ``prepare`` restoring its
    precondition outside both."""
    with untraced():
        prepare()
        work()
    prepare()
    gc.collect()
    gc.collect()
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        held = work()
        if metric == "retainedKiB":
            gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        value = (current if metric == "retainedKiB" else peak) - before
        assert held is not None
    finally:
        tracemalloc.stop()
    kib = max(0, value) / 1_024
    return kib, "KiB", (kib,)


def _last_root(stream: Any) -> object:
    latest: object | None = None
    with stream as delivery:
        for root in delivery:
            latest = root
    gc.collect()
    assert latest is not None
    return latest


def _lane_work(
    database: ScopedDatabase,
    lane: control_support.Lane,
    wire_query: object,
    typed_query: ObjectQuery[Any, Any],
    form: control_support.Form,
) -> Callable[[], object]:
    """One delivery through ``lane`` in ``form``, answering what it leaves the
    caller holding: the eager result, or the last streamed root."""
    if lane == "wire":
        view = database.wire
        if form == "eager":
            return lambda: view.find(cast("Any", wire_query))
        return lambda: _last_root(
            view.stream(cast("Any", wire_query), batch_size=control_support.PAGE_SIZE)
        )
    if form == "eager":
        return lambda: database.find(typed_query)
    return lambda: _last_root(database.stream(typed_query, batch_size=control_support.PAGE_SIZE))


def _measured_work(
    work: Callable[[], object],
    metric: str,
    *,
    warmups: int,
    measured: int,
    prepare: Callable[[], None] = _unprepared,
) -> tuple[float, str, tuple[float, ...]]:
    if metric == "elapsedUs":
        milliseconds = _timed(work, warmups=warmups, measured=measured, prepare=prepare)
        samples = tuple(elapsed * 1_000 for elapsed in milliseconds)
        return float(sorted(samples)[len(samples) // 2]), "us", samples
    return _traced(work, metric, prepare=prepare)


def _delivery_control(
    control: control_support.DeliveryControl, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    """One catalog workload delivered through either lane over provider-free
    rows, the root and its port composed outside the window."""
    workload = catalog()[control.workload_id]
    port = CatalogPort(workload, control.roots)
    root = Database(_SoleRuntime(port), ORDERS_MODEL)
    database = root.using_database_login()
    try:
        work = _lane_work(
            database,
            control.lane,
            workload.query,
            control_support.TYPED_QUERIES[control.workload_id],
            control.form,
        )
        return _measured_work(
            work, control.metric, warmups=warmups, measured=measured, prepare=port.reset
        )
    finally:
        root.close()


def _guarded_read(
    control: control_support.GuardedReadControl, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    """The guarded include workload delivered eagerly through either lane."""
    root = Database(
        control_support.GuardedPort(control.roots).open(), control_support.GUARDED_MODEL
    )
    database = root.using_database_login()
    try:
        query = control_support.guarded_query(control.width)
        work = _lane_work(database, control.lane, query, query, "eager")
        return _measured_work(work, control.metric, warmups=warmups, measured=measured)
    finally:
        root.close()


def _held(control: control_support.HeldControl) -> tuple[float, str, tuple[float, ...]]:
    """One eager Typed result's retained bytes: with the root still open and
    sharing its prepared model, or after the root has closed and the result is
    the only owner of whatever it keeps reachable."""
    query: ObjectQuery[Any, Any]
    if control.model == "small":
        query = control_support.TYPED_QUERIES[control_support.HELD_SMALL_WORKLOAD_ID]

        def compose() -> tuple[Database[Any], Callable[[], None]]:
            port = CatalogPort(
                catalog()[control_support.HELD_SMALL_WORKLOAD_ID], control_support.HELD_ROOTS
            )
            return Database(_SoleRuntime(port), ORDERS_MODEL), port.reset

    else:
        query = control_support.HELD_LARGE_QUERY

        def compose() -> tuple[Database[Any], Callable[[], None]]:
            port = control_support.held_large_port()
            return Database(port.open(), control_support.HELD_LARGE_MODEL), _unprepared

    if control.state == "shared":
        root, prepare = compose()
        database = root.using_database_login()
        try:
            return _traced(lambda: database.find(query), "retainedKiB", prepare=prepare)
        finally:
            root.close()

    def closed() -> object:
        root, _prepare = compose()
        try:
            return root.using_database_login().find(query)
        finally:
            root.close()

    return _traced(closed, "retainedKiB")


def _control(
    control: control_support.ControlAddress, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    match control:
        case control_support.DeliveryControl():
            return _delivery_control(control, warmups=warmups, measured=measured)
        case control_support.GuardedReadControl():
            return _guarded_read(control, warmups=warmups, measured=measured)
        case control_support.GuardedPlanControl(width=width, phase="cold", metric=metric):
            return _cold_plan(ColdPlan.guarded(width), metric, warmups=warmups, measured=measured)
        case control_support.GuardedPlanControl(width=width, metric=metric):
            return _warm_plan(ColdPlan.guarded(width), metric, warmups=warmups, measured=measured)
        case control_support.HeldControl():
            return _held(control)


def _geometry(
    level: GeometryLevel, layout: str, metric: str, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    """One geometry level's provider-free Wire find under ``layout``.

    The handle and its port are composed outside the window; every find inside
    it plans, materializes, and publishes ``READ_GEOMETRY_ROOTS`` freshly
    composed rows.
    """
    selected = cast("geometry_support.Layout", layout)
    roots = READ_GEOMETRY_ROOTS
    port = geometry_support.GeometryPort(level, selected, roots)
    root = Database(port.open(), geometry_support.MODEL)
    database = root.using_database_login()
    query = geometry_support.read_query(level, selected)
    try:
        if metric == "elapsedUsPerRoot":

            def work() -> int:
                return len(database.wire.find(query).results())

            milliseconds = _timed(work, warmups=warmups, measured=measured)
            samples = tuple(elapsed * 1_000 / roots for elapsed in milliseconds)
            return float(sorted(samples)[len(samples) // 2]), "us/root", samples
        if metric == "retainedKiB":

            def materialized(sample: Callable[[], None]) -> None:
                held = database.wire.find(query)
                sample()
                assert held is not None

            tracemalloc.start()
            try:
                value = retained(materialized) / 1_024
            finally:
                tracemalloc.stop()
            return value, "KiB", (value,)
        with untraced():
            for _ in range(warmups):
                database.wire.find(query)
        gc.collect()
        gc.collect()
        tracemalloc.start()
        try:
            before, _ = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            held = database.wire.find(query)
            _, peak = tracemalloc.get_traced_memory()
            assert held is not None
        finally:
            tracemalloc.stop()
        value = max(0, peak - before) / 1_024
        return value, "KiB", (value,)
    finally:
        root.close()


def measure(
    workload: Workload,
    path: str,
    roots: int,
    connection_info: str | None,
    *,
    warmups: int,
    measured: int,
    collect_at_page_boundary: bool,
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
        return _live_memory(
            workload,
            path,
            roots,
            connection_info,
            collect_at_page_boundary=collect_at_page_boundary,
        )
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
    # Where alone: the secret arrives as `PGPASSWORD` in this process's own
    # environment rather than on an argv line anything can read, which is what
    # `DRIVER_MANAGED` means at the two construction sites above.
    parser.add_argument("--connection-info")
    args = parser.parse_args(argv)
    contract = BudgetContract.load()
    if (args.warmups, args.measured) != (
        contract.timing_warmups,
        contract.timing_measured,
    ):
        parser.error("timing sampling counts do not match the Budget Contract")
    try:
        geometry = geometry_address(args.workload, args.cell)
        plan = plan_address(args.workload, args.cell)
        control = control_support.control_address(
            args.workload, args.cell, contract.memory_scaling_arms
        )
    except (KeyError, ValueError) as error:
        parser.error(str(error))
    if geometry is not None:
        level, layout, metric = geometry
        value, reading_unit, samples = _geometry(
            level, layout, metric, warmups=args.warmups, measured=args.measured
        )
    elif plan is not None:
        level, layout, metric = plan
        value, reading_unit, samples = _plan(
            level, layout, metric, warmups=args.warmups, measured=args.measured
        )
    elif control is not None:
        value, reading_unit, samples = _control(
            control, warmups=args.warmups, measured=args.measured
        )
    else:
        if args.workload not in catalog(contract):
            parser.error(f"{args.workload} is not a Budget Contract workload")
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
            collect_at_page_boundary=contract.memory_collect_at_page_boundary,
        )
    print(json.dumps({"value": value, "unit": reading_unit, "samples": samples}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
