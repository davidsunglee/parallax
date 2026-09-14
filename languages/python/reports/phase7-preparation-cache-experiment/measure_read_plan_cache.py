from __future__ import annotations

import gc
import json
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from tools.snapshot_delivery_reading import CatalogPort

from parallax.conformance.budget import BudgetContract
from parallax.conformance.story_models import Order
from parallax.conformance.workloads import catalog
from parallax.core import continuation
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.object_query._fluent import object_query_node
from parallax.core.object_query._validated import ContinuationCoordinate, ValidatedObjectQuery
from parallax.postgres import _connection as postgres_connection
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.handle._read import find
from parallax.snapshot.handle._read_plan import ReadPlanCache

WORKLOAD = catalog(BudgetContract.load())["duplicate-include"]
META = model_of(WORKLOAD.domain_model)
MODEL = CatalogedModel(META)


def query(value: int, family: str) -> ValidatedObjectQuery:
    authored = Order.where(Order.id == value)
    if family == "items":
        authored = authored.include(Order.items)
    elif family == "duplicate":
        authored = authored.include(Order.items).include(Order.items_by_ship_date)
    return preflight(object_query_node(authored), model=META, form="graph")


EAGER_TRACE = tuple(
    query(value, family)
    for value, family in (
        (1, "duplicate"),
        (2, "duplicate"),
        (1, "duplicate"),
        (1, "items"),
        (2, "items"),
        (1, "items"),
        (3, "duplicate"),
        (1, "duplicate"),
        (1, "root"),
        (2, "root"),
        (1, "root"),
        (2, "duplicate"),
    )
)

STREAM_BASE = preflight(WORKLOAD.query, model=META, form="graph")
STREAM_PAGES = continuation.plan(STREAM_BASE, META)
STREAM_TRACE = (
    STREAM_PAGES.first(limit=32),
    STREAM_PAGES.after(ContinuationCoordinate((32,)), limit=32),
    STREAM_PAGES.after(ContinuationCoordinate((64,)), limit=32),
    STREAM_PAGES.after(ContinuationCoordinate((96,)), limit=32),
    STREAM_PAGES.first(limit=128),
    STREAM_PAGES.after(ContinuationCoordinate((128,)), limit=128),
    STREAM_PAGES.after(ContinuationCoordinate((256,)), limit=128),
    STREAM_PAGES.after(ContinuationCoordinate((384,)), limit=128),
    STREAM_PAGES.first(limit=32),
    STREAM_PAGES.after(ContinuationCoordinate((416,)), limit=32),
)


def median_ms(operation: Callable[[], object], samples: int = 21) -> float:
    measured: list[float] = []
    for _ in range(samples):
        started = time.perf_counter_ns()
        operation()
        measured.append((time.perf_counter_ns() - started) / 1_000_000)
    return statistics.median(measured)


def plan_one(planner: ReadPlanCache, selected: ValidatedObjectQuery) -> None:
    planner.plan(
        edition="edition-a",
        model=MODEL,
        dialect=POSTGRES,
        query=selected,
        result_form="instance",
        preference=None,
    )


def planning_trace(capacity: int, selected: Sequence[ValidatedObjectQuery]) -> ReadPlanCache:
    cache = ReadPlanCache(capacity)
    for query_ in selected:
        plan_one(cache, query_)
    return cache


def delivery_trace(capacity: int, selected: Sequence[ValidatedObjectQuery]) -> None:
    cache = ReadPlanCache(capacity)
    port = CatalogPort(WORKLOAD, 200)
    for query_ in selected:
        result = find(query_, MODEL, port, edition="edition-a", planner=cache)
        del result


def retained_kib(capacity: int, selected: Sequence[ValidatedObjectQuery]) -> dict[str, float]:
    gc.collect()
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    cache = planning_trace(capacity, selected)
    gc.collect()
    retained = tracemalloc.get_traced_memory()[0] - before
    del cache
    gc.collect()
    released = tracemalloc.get_traced_memory()[0] - before
    tracemalloc.stop()
    return {"retainedBytes": retained, "afterReleaseBytes": released}


def trace_measurements(selected: Sequence[ValidatedObjectQuery]) -> dict[str, object]:
    results: dict[str, object] = {}
    for capacity in (0, 1, 2, 4, 8, 16, 32):
        label = "noCrossDeliveryReuse" if capacity == 0 else f"capacity{capacity}"
        cache = planning_trace(capacity, selected)
        samples = tuple(retained_kib(capacity, selected) for _ in range(3))
        retention = {
            key: statistics.median(sample[key] for sample in samples)
            for key in ("retainedBytes", "afterReleaseBytes")
        }
        results[label] = {
            "planningMedianMs": median_ms(
                lambda capacity=capacity: planning_trace(capacity, selected)
            ),
            "deliveryMedianMs": median_ms(
                lambda capacity=capacity: delivery_trace(capacity, selected)
            ),
            "statistics": asdict(cache._statistics()),
            "retention": retention,
        }
    return results


def postgres_loader_retention(unique_names: int = 5000) -> dict[str, float | int]:
    gc.collect()
    tracemalloc.start()
    loader = postgres_connection._DocumentJsonbLoader(3802)
    before = tracemalloc.get_traced_memory()[0]
    for index in range(unique_names):
        loader.load(f'{{"member{index}":{index}}}'.encode())
    gc.collect()
    retained = (tracemalloc.get_traced_memory()[0] - before) / 1024
    del loader
    gc.collect()
    released = (tracemalloc.get_traced_memory()[0] - before) / 1024
    tracemalloc.stop()
    return {
        "uniqueNames": unique_names,
        "retainedKiBWhileLoaderLives": retained,
        "afterLoaderReleaseKiB": released,
    }


print(
    json.dumps(
        {
            "authority": "non-authoritative",
            "command": (
                "uv run python reports/phase7-preparation-cache-experiment/"
                "measure_read_plan_cache.py"
            ),
            "traceDefinitions": {
                "eager": {"requests": len(EAGER_TRACE), "queryFamilies": 3, "literals": 3},
                "streaming": {
                    "requests": len(STREAM_TRACE),
                    "pageSizes": [32, 128],
                    "continuationCoordinates": 7,
                },
            },
            "eager": trace_measurements(EAGER_TRACE),
            "streaming": trace_measurements(STREAM_TRACE),
            "postgresLoader": postgres_loader_retention(),
        },
        indent=2,
        sort_keys=True,
    )
)
