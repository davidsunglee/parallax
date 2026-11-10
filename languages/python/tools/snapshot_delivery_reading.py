"""Take one isolated Snapshot delivery reading: a Budget Contract cell, one
provider-free geometry or scalar-type read family address, one read-plan
compilation address, one before/after control address, or one wide fan-out cell.

This script is imported by nothing. It is the sole report-side reader of the
whole-interpreter memory instruments and answers its parent with one JSON line.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import importlib.util
import json
import sys
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import ModuleType, TracebackType
from typing import TYPE_CHECKING, Any, Final, cast

from parallax.conformance.budget import BudgetContract
from parallax.conformance.story_models import ORDERS_MODEL, OrderItem
from parallax.conformance.vo_models import CUSTOMER_MODEL, Location
from parallax.conformance.workloads import (
    PLAN_LEVEL_IDS,
    PUBLICATION_PREFIX,
    READ_GEOMETRY_ROOTS,
    STRUCTURAL_LAYOUTS,
    WIDE_FANOUT_CELLS,
    WIDE_FANOUT_WORKLOAD,
    GeometryLevel,
    ScriptedRows,
    Workload,
    catalog,
)
from parallax.core import ObjectQuery
from parallax.core._execution._publication import read_projection
from parallax.core._execution._read_query import resolve_read_query
from parallax.core.internal.db_port import (
    DRIVER_MANAGED,
    ArrayBind,
    CleanupResult,
    DatabaseConnection,
    DocumentReadOrdinals,
    MappingRow,
    OrderedWriteTransport,
    PipelineStatement,
    Returned,
    Route,
    RouteCapabilities,
    RoutePolicy,
    RouteSelection,
    Row,
    TransactionOutcome,
)
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.core.internal.entity import DomainModel
from parallax.core.internal.entity._authored_resolver import object_query_node
from parallax.core.internal.execution import prepare_model
from parallax.core.internal.read_delivery import InvalidData
from parallax.core.internal.read_delivery._read_plan import (
    DEFAULT_READ_PLAN_CACHE_CAPACITY,
    ReadPlan,
    ReadPlanCache,
)
from parallax.postgres import PostgresAdapter, PostgresEndpoint
from parallax.snapshot import Database, ScopedDatabase, SharingScope, Snapshot, SnapshotStream
from production_origins import ORIGINS_FIELD, loaded_origins, require_source_origins

WORKSPACE: Final = Path(__file__).resolve().parents[1]
SUPPORT_DIRECTORY: Final = WORKSPACE / "tests" / "unit"
INSTRUMENT_MODULE: Final = SUPPORT_DIRECTORY / "memory_instruments.py"
sys.path.insert(0, str(WORKSPACE))

# `sys.path` gains the workspace above, so these imports cannot precede it; that is
# what the E402 suppression each one carries records.
from tests.unit import memory_instruments  # noqa: E402

if Path(memory_instruments.__file__ or "").resolve() != INSTRUMENT_MODULE:
    raise ImportError(
        f"this reading requires {INSTRUMENT_MODULE}, but resolved {memory_instruments.__file__}"
    )

from tests._support.db_port import projected_rows  # noqa: E402
from tests.unit._workload_spelling_support import (  # noqa: E402
    CONTROL_PREFIX,
    GEOMETRY_PREFIX,
    PLAN_PREFIX,
    SCALAR_PREFIX,
)

# E402 again, and imported below the guard proving the module is this workspace's own.
from tests.unit.memory_instruments import Seam, retained, untraced  # noqa: E402


def _deferred(name: str) -> ModuleType:
    """The support module ``tests.unit.<name>``, proven to be this workspace's
    own file now but executed only when first used.

    Every family's support module builds its models when it runs, and every
    collection inside a window walks whatever has been built, so a child runs
    only the module its address reads.
    """
    qualified = f"tests.unit.{name}"
    expected = SUPPORT_DIRECTORY / f"{name}.py"
    spec = importlib.util.find_spec(qualified)
    origin = None if spec is None else spec.origin
    if spec is None or spec.loader is None or Path(origin or "").resolve() != expected:
        raise ImportError(f"this reading requires {expected}, but resolved {origin}")
    if qualified in sys.modules:
        return sys.modules[qualified]
    spec.loader = importlib.util.LazyLoader(spec.loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


if TYPE_CHECKING:
    from tests.unit import _delivery_control_support as control_support
    from tests.unit import _scalar_type_support as scalar_support
    from tests.unit import _snapshot_materialization_support as stress_support
    from tests.unit import _structural_geometry_support as geometry_support
else:
    control_support = _deferred("_delivery_control_support")
    scalar_support = _deferred("_scalar_type_support")
    stress_support = _deferred("_snapshot_materialization_support")
    geometry_support = _deferred("_structural_geometry_support")

PROVIDER_FREE_IDS: Final = frozenset({"conventional-fanout", "duplicate-include"})
GEOMETRY_METRICS: Final = ("elapsedUsPerRoot", "peakKiB", "retainedKiB")
PLAN_METRICS: Final = ("elapsedUs", "peakKiB", "retainedKiB")
PLAN_EDITION: Final = "snapshot-delivery-report"
STREAMED_RETAINED_PAGE_SIZE: Final = 128
"""The page size a ``streamedMemory.retainedKiB`` reading drains at: the largest
the contract reads, whose drain runs the fewest statements."""
REPEATED_FANOUT_ID: Final = "repeated-fanout"
INVALID_ROOTS_ID: Final = "invalid-roots"
SCALED_RESULT_FACTOR: Final = 10
"""How much larger than the fixture's own scale an ``x10`` reading's result is,
at the same page size."""
WIDE_FANOUT_ORDERS: Final = 1
WIDE_FANOUT_ITEMS: Final = 1_000
_ITEM_ENTITY: Final = "parallax.compatibility.OrderItem"
_ORDER_ENTITY: Final = "parallax.compatibility.Order"
_CUSTOMER_ENTITY: Final = "parallax.compatibility.Customer"
_LOCATION_ENTITY: Final = "parallax.compatibility.Location"
_DEPOT_ENTITY: Final = "parallax.compatibility.Depot"


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


def _root_item_row(row: Mapping[str, object]) -> MappingRow:
    return {**_item_row(row), "parallax_seek_0": row["id"]}


def _customer_row(row: Mapping[str, object]) -> MappingRow:
    return {"id": row["id"], "name": row["name"], "address": row["address"]}


def _root_location_row(row: Mapping[str, object]) -> MappingRow:
    return {
        "id": row["id"],
        "customer_id": row["customerId"],
        "label": row["label"],
        "address": row["address"],
        "parallax_seek_0": row["id"],
    }


def _depot_row(row: Mapping[str, object]) -> MappingRow:
    return {
        "id": row["id"],
        "customer_id": row["customerId"],
        "label": row["label"],
        "address": row["address"],
    }


_RETURNED: Final[CleanupResult] = Returned()
_LOGIN: Final = "snapshot-delivery-report"
_ROUTES: Final[Mapping[Route, RouteCapabilities]] = {"writer": RouteCapabilities.every_level()}
_SERVED: Final = RouteSelection("writer")


class _SoleScope:
    __slots__ = ("_connection", "_entered", "_left")

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection
        self._entered = False
        self._left = False

    @property
    def selection(self) -> RouteSelection | None:
        return _SERVED if self._entered else None

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return _RETURNED if self._left else None

    def __enter__(self) -> DatabaseConnection:
        self._entered = True
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
    def routes(self) -> Mapping[Route, RouteCapabilities]:
        return _ROUTES

    @property
    def pool_metrics(self) -> tuple[()]:
        return ()

    @property
    def login_identity(self) -> str:
        return _LOGIN

    def login_source(self) -> _SoleRuntime:
        return self

    def principal_source(self, authorization: object) -> _SoleRuntime:
        del authorization
        return self

    def new_context(self, policy: RoutePolicy, /) -> _SoleScope:
        del policy
        return _SoleScope(self._connection)

    def close(self) -> None:
        return


class _PagedPort:
    """Positional rows of one generated dataset, its roots delivered page by page.

    One delivery consumes the root rows once; :meth:`reset` restores them for
    the next, so a root composed outside a window can serve every run inside it.
    """

    dialect: Dialect = POSTGRES
    ordered_write_transport: OrderedWriteTransport | None = None
    __slots__ = ("_delivered",)

    def __init__(self) -> None:
        self._delivered = 0

    def reset(self) -> None:
        self._delivered = 0

    def _next_roots(
        self, roots: Sequence[Mapping[str, object]], sql: str, binds: Sequence[object]
    ) -> Sequence[Mapping[str, object]]:
        limited = " limit " in sql
        size = cast("int", binds[-1]) if limited else len(roots)
        taken = min(size, len(roots) - self._delivered)
        selected = roots[self._delivered : self._delivered + taken]
        self._delivered += taken - 1 if taken == size and limited else taken
        return selected

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        raise NotImplementedError

    def execute_pipeline(
        self, statements: Sequence[PipelineStatement], *, read_only: bool = False
    ) -> list[list[Row]]:
        return [
            self.execute(
                statement.sql, statement.binds, statement.document_reads, read_only=read_only
            )
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
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        del body, isolation, access_mode
        raise NotImplementedError


class _ProviderFreeOrders(_PagedPort):
    """Positional rows of one ``orders-tree`` dataset."""

    __slots__ = ("_fanout", "_first_id", "_items", "_orders")

    def __init__(self, rows: ScriptedRows) -> None:
        super().__init__()
        self._fanout = rows.fanout
        self._orders = rows.entity(_ORDER_ENTITY)
        self._items = rows.entity(_ITEM_ENTITY)
        self._first_id = cast("int", self._orders[0]["id"])

    def _items_of(self, parent: int) -> Sequence[Mapping[str, object]]:
        offset = parent - self._first_id
        return self._items[offset * self._fanout : (offset + 1) * self._fanout]


class CatalogPort(_ProviderFreeOrders):
    """Provider-free positional rows for the two catalog workloads that grade CPU."""

    __slots__ = ()

    def __init__(self, workload: Workload, total: int) -> None:
        if workload.id not in PROVIDER_FREE_IDS:
            raise ValueError(f"{workload.id} has no provider-free CPU cell")
        super().__init__(workload.rows(total))

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        del document_reads
        if "order_item t0" in sql:
            parents = cast("list[int]", cast("ArrayBind", binds[0]).values)
            return projected_rows(
                sql, (_item_row(row) for parent in parents for row in self._items_of(parent))
            )
        return projected_rows(sql, map(_order_row, self._next_roots(self._orders, sql, binds)))


class RepeatedFanoutPort(_ProviderFreeOrders):
    """Provider-free positional rows for ``OrderItem`` roots that reach their
    Order and go back out to its items, one page of them at a time, so what a
    stream costs is the page's and not the dataset's."""

    __slots__ = ()

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        del document_reads
        if "order_item t0" in sql and "order_id = any" not in sql:
            return projected_rows(
                sql, map(_root_item_row, self._next_roots(self._items, sql, binds))
            )
        parents = cast("list[int]", cast("ArrayBind", binds[0]).values)
        if "order_item t0" not in sql:
            return projected_rows(
                sql, (_order_row(self._orders[parent - self._first_id]) for parent in parents)
            )
        return projected_rows(
            sql, (_item_row(row) for parent in parents for row in reversed(self._items_of(parent)))
        )


class InvalidRootsPort(_PagedPort):
    """Provider-free positional rows for ``Location`` roots that reach their
    Customer and go out to its Depots, one page of them at a time, with every
    tenth root's own document missing a required member."""

    __slots__ = ("_customers", "_depots", "_fanout", "_first_id", "_locations")

    def __init__(self, rows: ScriptedRows) -> None:
        super().__init__()
        self._fanout = rows.fanout
        self._customers = rows.entity(_CUSTOMER_ENTITY)
        self._locations = rows.entity(_LOCATION_ENTITY)
        self._depots = rows.entity(_DEPOT_ENTITY)
        self._first_id = cast("int", self._customers[0]["id"])

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        if " from location t0" in sql:
            roots = self._next_roots(self._locations, sql, binds)
            return projected_rows(sql, map(_root_location_row, roots), document_reads)
        offsets = [
            parent - self._first_id
            for parent in cast("list[int]", cast("ArrayBind", binds[0]).values)
        ]
        if " from customer t0" in sql:
            customers = (_customer_row(self._customers[offset]) for offset in offsets)
            return projected_rows(sql, customers, document_reads)
        depots = (
            _depot_row(row)
            for offset in offsets
            for row in self._depots[offset * self._fanout : (offset + 1) * self._fanout]
        )
        return projected_rows(sql, depots, document_reads)


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


def _verify_live(connection_info: str, workload: str) -> None:
    from parallax.conformance._lifecycle_observation import LifecycleObservation
    from tests._support import live_read_workloads

    observation = LifecycleObservation()
    with Database.connect(
        PostgresAdapter(writer=PostgresEndpoint(connection_info, credentials=DRIVER_MANAGED)),
        live_read_workloads.domain_model(workload),
        lifecycle_provider=observation.provider,
    ) as root:
        live_read_workloads.verify(root.using_database_login(), workload, observation)


def _representative_live(
    workload: str,
    path: str,
    roots: int,
    connection_info: str | None,
    *,
    warmups: int,
    measured: int,
) -> tuple[float, str, tuple[float, ...]]:
    from tests._support import live_read_workloads

    address = live_read_workloads.address(workload, path)
    if address is None or roots != live_read_workloads.ROOTS or connection_info is None:
        raise ValueError("live reads require a frozen address, 200 roots, and a live connection")
    subject, lane, form = address
    _verify_live(connection_info, subject)
    with Database.connect(
        PostgresAdapter(writer=PostgresEndpoint(connection_info, credentials=DRIVER_MANAGED)),
        live_read_workloads.domain_model(subject),
    ) as root:
        database = root.using_database_login()
        samples = _timed(
            lambda: live_read_workloads.read(database, subject, lane, form),
            warmups=warmups,
            measured=measured,
        )
    return float(sorted(samples)[len(samples) // 2]), "ms", samples


def _live_timing(
    workload: Workload,
    path: str,
    roots: int,
    connection_info: str,
    *,
    warmups: int,
    measured: int,
) -> tuple[float, str, tuple[float, ...]]:
    if workload.id == "conventional-fanout" and path in {"live.eager.maxMs", "live.page32.maxMs"}:
        _verify_live(connection_info, workload.id)
    with Database.connect(
        PostgresAdapter(writer=PostgresEndpoint(connection_info, credentials=DRIVER_MANAGED)),
        workload.domain_model,
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
    memory_instruments.require_own_interpreter("Snapshot live_memory")
    page_size = (
        (
            _page_size(path)
            if path.startswith("streamedMemory.page")
            else STREAMED_RETAINED_PAGE_SIZE
        )
        if path.startswith("streamedMemory.")
        else None
    )
    with Database.connect(
        PostgresAdapter(writer=PostgresEndpoint(connection_info, credentials=DRIVER_MANAGED)),
        workload.domain_model,
    ) as root:
        database = root.using_database_login()
        if page_size is None:
            database.wire.find(workload.query)
        else:
            _last_streamed(database, workload, page_size, collect_at_page_boundary=False)
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
    """One stress layout's prepared model, validated query, read plan, and port,
    composed outside every window.

    :meth:`read_root` executes the root statement a run then consumes, and every
    caller runs it outside the region it measures; :meth:`run` is the window.
    """

    __slots__ = ("model", "plan", "port", "query", "root")

    def __init__(self, layout: Any) -> None:
        self.model = read_projection(
            prepare_model(stress_support.workload(layout), edition="snapshot-delivery-report")
        ).model
        self.query = stress_support.query(layout, self.model.meta)
        self.plan = stress_support.read_plan(self.model, self.query)
        reads = stress_support.compiled_levels(layout, self.plan)
        self.port = stress_support.StressPort(
            reads, stress_support.rows_per_level(layout, self.model, self.plan, reads)
        )
        self.root = None

    def read_root(self) -> None:
        self.root = stress_support.read_root(self.model, self.query, self.plan, self.port)

    def run(self) -> object:
        root = self.root
        assert root is not None
        self.root = None
        return stress_support.build_page(self.model, root, self.port)

    def seam(self) -> Seam:
        def run(sample: Callable[[], None]) -> None:
            page = self.run()
            sample()
            assert page is not None
            self.read_root()

        return run


def _stress_layout(workload: str) -> Any:
    name = "columns" if workload == "stress-columns" else "document"
    return next(layout for layout in stress_support.LAYOUTS if layout == name)


def _stress_timing(
    prepared: _PreparedStress, path: str, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    milliseconds = _timed(
        prepared.run, warmups=warmups, measured=measured, prepare=prepared.read_root
    )
    projections = stress_support.PROJECTIONS_PER_BATCH
    if path.endswith("maxUsPerProjection"):
        samples = tuple(elapsed * 1_000 / projections for elapsed in milliseconds)
        return float(sorted(samples)[len(samples) // 2]), "us/projection", samples
    samples = tuple(projections * 1_000 / elapsed for elapsed in milliseconds)
    return float(sorted(samples)[len(samples) // 2]), "projections/s", samples


def _stress_memory(prepared: _PreparedStress, path: str) -> tuple[float, str, tuple[float, ...]]:
    memory_instruments.require_own_interpreter("Snapshot stress_memory")
    if path.endswith("preparedSetKiB"):

        def planned(sample: Callable[[], None]) -> None:
            plan = stress_support.read_plan(prepared.model, prepared.query)
            sample()
            assert plan is not None

        tracemalloc.start()
        try:
            value = retained(planned) / 1_024
        finally:
            tracemalloc.stop()
        return value, "KiB", (value,)
    tracemalloc.start()
    try:
        prepared.read_root()
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
    for any other address."""
    if not workload.startswith(GEOMETRY_PREFIX):
        return None
    level = geometry_support.level_named(workload.removeprefix(GEOMETRY_PREFIX))
    layout, metric = _read_cell(workload, path, "geometry")
    return level, layout, metric


def scalar_address(workload: str, path: str) -> tuple[scalar_support.ScalarType, str, str] | None:
    """The scalar type, layout, and metric a scalar-type read address names, or
    absence for any other address."""
    if not workload.startswith(SCALAR_PREFIX):
        return None
    scalar = scalar_support.read_address(workload)
    if scalar is None:
        return None
    layout, metric = _read_cell(workload, path, "scalar-type")
    return scalar, layout, metric


def _read_cell(workload: str, path: str, family: str) -> tuple[str, str]:
    layout, _separator, metric = path.partition(".")
    if layout not in STRUCTURAL_LAYOUTS or metric not in GEOMETRY_METRICS:
        raise ValueError(f"{workload}.{path} is not a {family} read address")
    return layout, metric


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
    read-query resolution is validation rather than planning, and production composes
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
        self.query = resolve_read_query(object_query_node(query, model), model=self.model.meta)
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
    if metric != "elapsedUs":
        memory_instruments.require_own_interpreter("Snapshot cold_plan")
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
    memory_instruments.require_own_interpreter("Snapshot traced")
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


@dataclass(frozen=True, slots=True)
class _SharedWorkload:
    """What a publication workload's reading composes: its port over generated
    rows, its model, the Typed spelling of its query, the two hops of its one
    include path, and whether its result holds invalid roots a checked read
    must pass."""

    port: Callable[[ScriptedRows], _PagedPort]
    model: DomainModel
    query: Callable[[], ObjectQuery[Any, Any]]
    root_entity: str
    hops: tuple[str, str]
    checked: bool


def repeated_fanout_query() -> ObjectQuery[Any, Any]:
    """The Typed spelling of the ``repeated-fanout`` fixture's query."""
    return OrderItem.where(OrderItem.all).include(OrderItem.order.items)


def invalid_roots_query() -> ObjectQuery[Any, Any]:
    """The Typed spelling of the ``invalid-roots`` fixture's query."""
    return Location.where(Location.all).include(Location.customer.depots)


_SHARED_WORKLOADS: Final[Mapping[str, _SharedWorkload]] = {
    REPEATED_FANOUT_ID: _SharedWorkload(
        RepeatedFanoutPort,
        ORDERS_MODEL,
        repeated_fanout_query,
        _ITEM_ENTITY,
        ("order", "items"),
        checked=False,
    ),
    INVALID_ROOTS_ID: _SharedWorkload(
        InvalidRootsPort,
        CUSTOMER_MODEL,
        invalid_roots_query,
        _LOCATION_ENTITY,
        ("customer", "depots"),
        checked=True,
    ),
}


class _FanoutRead:
    """One lane's read of a publication workload at one sharing scope."""

    __slots__ = ("_checked", "_database", "_lane", "_query", "_scope", "_wire_query")

    def __init__(
        self,
        database: ScopedDatabase,
        workload: Workload,
        shared: _SharedWorkload,
        lane: str,
        scope: SharingScope,
    ) -> None:
        self._database = database
        self._lane = lane
        self._scope: SharingScope = scope
        self._query = shared.query()
        self._wire_query = workload.query
        self._checked = shared.checked

    def eager(self) -> Snapshot[Any]:
        if self._lane == "wire":
            return self._database.wire.find(self._wire_query, sharing_scope=self._scope)
        return self._database.find(self._query, sharing_scope=self._scope)

    def results(self) -> Sequence[Any]:
        snapshot = self.eager()
        return snapshot.checked().results() if self._checked else snapshot.results()

    def stream(self, page_size: int) -> SnapshotStream[Any]:
        if self._lane == "wire":
            return self._database.wire.stream(
                self._wire_query, batch_size=page_size, sharing_scope=self._scope
            )
        return self._database.stream(self._query, batch_size=page_size, sharing_scope=self._scope)

    def delivered(self, stream: SnapshotStream[Any], root: Any) -> object:
        return cast("object", stream.wire(root)) if self._lane == "projected" else root

    def last_delivered(
        self, page_size: int, *, until: int | None, collect_at_page_boundary: bool
    ) -> object:
        """What the delivery of root ``until`` left the caller holding, the
        stream closed; every root's when ``until`` is absent."""
        latest: object | None = None
        with self.stream(page_size) as stream:
            roots = stream.checked() if self._checked else stream
            for count, root in enumerate(roots, start=1):
                latest = self.delivered(stream, root)
                if collect_at_page_boundary and count % page_size == 0:
                    gc.collect()
                if count == until:
                    break
        gc.collect()
        assert latest is not None
        return latest


def _unique_nodes(lane: str, hops: tuple[str, str], roots: Sequence[Any]) -> int:
    """The distinct published objects along the read's one include path, an
    invalid root's counted from the diagnostic graph it carries."""
    parent, children = hops
    nodes: set[int] = set()
    for delivered in roots:
        root: Any = (
            cast("InvalidData[Any]", delivered).data
            if isinstance(delivered, InvalidData)
            else delivered
        )
        reached: Any = getattr(root, parent) if lane == "typed" else root[parent]
        below: Sequence[object] = (
            getattr(reached, children) if lane == "typed" else reached[children]
        )
        nodes.update(id(node) for node in (root, reached, *below))
    return len(nodes)


def _fanout_reading(
    workload: Workload,
    rows: ScriptedRows,
    cell: str,
    *,
    warmups: int,
    measured: int,
    collect_at_page_boundary: bool,
) -> tuple[float, str, tuple[float, ...]]:
    """One ``<lane>.<scope>.<reading>`` of ``rows``: the whole read, planning
    included, with the root and port composed outside the window. A traced
    read rewinds the port before it answers, so the port's cursor is not
    priced as what the read retained."""
    lane, scope, *reading = cell.split(".")
    metric = reading[-1]
    shared = _SHARED_WORKLOADS[workload.id]
    port = shared.port(rows)
    root = Database(_SoleRuntime(port), shared.model)
    read = _FanoutRead(
        root.using_database_login(), workload, shared, lane, cast("SharingScope", scope)
    )
    try:
        if metric == "uniqueNodes":
            nodes = float(_unique_nodes(lane, shared.hops, read.results()))
            return nodes, "nodes", (nodes,) * measured
        if metric == "maxMs":
            samples = _timed(read.eager, warmups=warmups, measured=measured, prepare=port.reset)
            return float(sorted(samples)[len(samples) // 2]), "ms", samples
        if not reading[0].startswith("page"):
            work: Callable[[], object] = read.eager
        else:
            page_size = _page_size(reading[0])
            until = len(rows.entity(shared.root_entity)) // 2 if "earlyClose" in reading else None

            def work() -> object:
                held = read.last_delivered(
                    page_size, until=until, collect_at_page_boundary=collect_at_page_boundary
                )
                return held if until is None else until

        def rewound() -> object:
            held = work()
            port.reset()
            return held

        return _traced(rewound, metric, prepare=port.reset)
    finally:
        root.close()


def _publication(
    workload: Workload,
    path: str,
    *,
    warmups: int,
    measured: int,
    collect_at_page_boundary: bool,
) -> tuple[float, str, tuple[float, ...]]:
    """One ``publication.*`` cell, at the fixture's own scale or at ``x10``."""
    scale = SCALED_RESULT_FACTOR if ".x10." in path else 1
    return _fanout_reading(
        workload,
        workload.rows(workload.roots * scale),
        path.removeprefix(PUBLICATION_PREFIX),
        warmups=warmups,
        measured=measured,
        collect_at_page_boundary=collect_at_page_boundary,
    )


def _wide_fanout(
    workload: Workload, cell: str, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    """One wide fan-out cell, whose every root reaches every item of one Order."""
    return _fanout_reading(
        workload,
        workload.rows(WIDE_FANOUT_ORDERS, fanout=WIDE_FANOUT_ITEMS),
        cell,
        warmups=warmups,
        measured=measured,
        collect_at_page_boundary=False,
    )


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
        level = geometry_support.level_named(control_support.HELD_LARGE_LEVEL_ID)
        layout = control_support.HELD_LARGE_LAYOUT
        query = geometry_support.read_query(level, layout)

        def compose() -> tuple[Database[Any], Callable[[], None]]:
            port = geometry_support.GeometryPort(level, layout, control_support.HELD_ROOTS)
            return Database(port.open(), geometry_support.MODEL), _unprepared

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
    """One geometry level's provider-free Wire find under ``layout``."""
    selected = cast("geometry_support.Layout", layout)
    return _structural_read(
        geometry_support.GeometryPort(level, selected, READ_GEOMETRY_ROOTS),
        geometry_support.MODEL,
        geometry_support.read_query(level, selected),
        metric,
        warmups=warmups,
        measured=measured,
    )


def _scalar_read(
    scalar_type: scalar_support.ScalarType, layout: str, metric: str, *, warmups: int, measured: int
) -> tuple[float, str, tuple[float, ...]]:
    """One scalar type's provider-free Wire find under ``layout``, at the roots a
    geometry read materializes."""
    selected = cast("scalar_support.Layout", layout)
    return _structural_read(
        scalar_support.ScalarTypePort(
            scalar_support.entity_class(scalar_type, selected), READ_GEOMETRY_ROOTS
        ),
        scalar_support.MODEL,
        scalar_support.read_query(scalar_type, selected),
        metric,
        warmups=warmups,
        measured=measured,
    )


def _structural_read(
    port: Any,
    model: DomainModel,
    query: ObjectQuery[Any, Any],
    metric: str,
    *,
    warmups: int,
    measured: int,
) -> tuple[float, str, tuple[float, ...]]:
    """One provider-free Wire find of ``query`` over ``port``.

    The handle and its port are composed outside the window; every find inside
    it plans, materializes, and publishes ``READ_GEOMETRY_ROOTS`` freshly
    composed rows.
    """
    if metric != "elapsedUsPerRoot":
        memory_instruments.require_own_interpreter("Snapshot structural_read")
    roots = READ_GEOMETRY_ROOTS
    root = Database(port.open(), model)
    database = root.using_database_login()
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
    if path.startswith(PUBLICATION_PREFIX):
        return _publication(
            workload,
            path,
            warmups=warmups,
            measured=measured,
            collect_at_page_boundary=collect_at_page_boundary,
        )
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


def _workload_reading(
    parser: argparse.ArgumentParser, args: argparse.Namespace, contract: BudgetContract
) -> tuple[float, str, tuple[float, ...]]:
    """The reading of a wide fan-out cell or a Budget Contract cell."""
    if args.workload == WIDE_FANOUT_WORKLOAD:
        if args.cell not in WIDE_FANOUT_CELLS:
            parser.error(f"{args.workload}.{args.cell} is not a wide fan-out cell")
        return _wide_fanout(
            catalog(contract)[REPEATED_FANOUT_ID],
            args.cell,
            warmups=args.warmups,
            measured=args.measured,
        )
    if args.workload not in catalog(contract):
        parser.error(f"{args.workload} is not a Budget Contract workload")
    if args.cell not in {cell.path for cell in contract.cells(args.workload)}:
        parser.error(f"{args.workload}.{args.cell} is not a Budget Contract cell")
    return measure(
        catalog(contract)[args.workload],
        args.cell,
        args.roots,
        args.connection_info,
        warmups=args.warmups,
        measured=args.measured,
        collect_at_page_boundary=contract.memory_collect_at_page_boundary,
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
        scalar = scalar_address(args.workload, args.cell)
        plan = plan_address(args.workload, args.cell)
        control = (
            control_support.control_address(
                args.workload, args.cell, contract.memory_scaling_root_counts
            )
            if args.workload.startswith(CONTROL_PREFIX)
            else None
        )
    except (KeyError, ValueError) as error:
        parser.error(str(error))
    require_source_origins()
    if args.workload.startswith("live-read-"):
        value, reading_unit, samples = _representative_live(
            args.workload,
            args.cell,
            args.roots,
            args.connection_info,
            warmups=args.warmups,
            measured=args.measured,
        )
    elif geometry is not None:
        level, layout, metric = geometry
        value, reading_unit, samples = _geometry(
            level, layout, metric, warmups=args.warmups, measured=args.measured
        )
    elif scalar is not None:
        scalar_type, layout, metric = scalar
        value, reading_unit, samples = _scalar_read(
            scalar_type, layout, metric, warmups=args.warmups, measured=args.measured
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
        value, reading_unit, samples = _workload_reading(parser, args, contract)
    origins = loaded_origins()
    print(
        json.dumps(
            {"value": value, "unit": reading_unit, "samples": samples, ORIGINS_FIELD: origins}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
