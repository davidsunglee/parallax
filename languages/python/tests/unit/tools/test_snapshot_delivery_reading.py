from __future__ import annotations

import sys
from inspect import signature
from types import SimpleNamespace
from typing import Any

import pytest

import snapshot_delivery_reading
from parallax.conformance.workloads import GEOMETRY_LEVELS, catalog, plan_levels
from parallax.snapshot.handle import Database
from snapshot_delivery_reading import (
    GEOMETRY_METRICS,
    PLAN_METRICS,
    CatalogPort,
    ColdPlan,
    _geometry,  # pyright: ignore[reportPrivateUsage] - the geometry reading is under test
    _last_streamed,  # pyright: ignore[reportPrivateUsage] - drain protocol is under test
    _plan,  # pyright: ignore[reportPrivateUsage] - the plan reading is under test
    _timed,  # pyright: ignore[reportPrivateUsage] - sampling protocol is under test
    geometry_address,
    plan_address,
)
from tests.unit.memory_instruments import in_a_child_interpreter, retained, serve_one_measurement


class _Stream:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = iter(values)
        self.closed = False

    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *_args: object) -> None:
        self.closed = True

    def __iter__(self) -> _Stream:
        return self

    def __next__(self) -> object:
        return next(self._values)


class _Wire:
    def __init__(self, stream: _Stream) -> None:
        self._stream = stream

    def stream(self, _query: object, *, batch_size: int) -> _Stream:
        del batch_size
        return self._stream


def test_last_streamed_drains_and_closes_the_delivery() -> None:
    stream = _Stream(("first", "middle", "last"))
    database = SimpleNamespace(wire=_Wire(stream))
    workload = SimpleNamespace(query=object())

    latest = _last_streamed(
        database,  # type: ignore[arg-type]
        workload,  # type: ignore[arg-type]
        1,
        collect_at_page_boundary=False,
    )

    assert latest == "last"
    assert stream.closed


def test_timed_uses_the_supplied_sampling_counts() -> None:
    calls = 0

    def work() -> Any:
        nonlocal calls
        calls += 1
        return None

    samples = _timed(work, warmups=2, measured=4)

    assert calls == 6
    assert len(samples) == 4


@pytest.mark.parametrize("collect_at_page_boundary", [True, False])
def test_stream_collection_happens_before_the_next_page_and_after_close(
    monkeypatch: pytest.MonkeyPatch, collect_at_page_boundary: bool
) -> None:
    events: list[object] = []

    class ObservedStream(_Stream):
        def __next__(self) -> object:
            value = super().__next__()
            events.append(value)
            return value

        def __exit__(self, *_args: object) -> None:
            super().__exit__(*_args)
            events.append("closed")

    monkeypatch.setattr(snapshot_delivery_reading.gc, "collect", lambda: events.append("gc"))
    stream = ObservedStream((1, 2, 3, 4, 5))
    latest = _last_streamed(
        SimpleNamespace(wire=_Wire(stream)),  # type: ignore[arg-type]
        SimpleNamespace(query=object()),  # type: ignore[arg-type]
        2,
        collect_at_page_boundary=collect_at_page_boundary,
    )

    assert latest == 5
    assert events == (
        [1, 2, "gc", 3, 4, "gc", 5, "closed", "gc"]
        if collect_at_page_boundary
        else [1, 2, 3, 4, 5, "closed", "gc"]
    )


def test_catalog_port_preserves_child_fanout_for_offset_parent_keys() -> None:
    workload = catalog()["conventional-fanout"]
    rows = workload.rows(2)
    parents = [row["id"] for row in rows.entity("parallax.compatibility.Order")]
    port = CatalogPort(workload, 2)

    returned = port.execute("select t0.id, t0.order_id from order_item t0", [parents])

    expected = rows.entity("parallax.compatibility.OrderItem")
    assert returned == [(row["id"], row["orderId"]) for row in expected]
    assert len(returned) == 2 * rows.fanout


def test_geometry_addresses_name_a_level_layout_and_metric() -> None:
    level, layout, metric = geometry_address("read-depth-4", "document.peakKiB") or (None,) * 3
    assert level is GEOMETRY_LEVELS[1]
    assert (layout, metric) == ("document", "peakKiB")
    assert geometry_address("conventional-fanout", "live.eager.maxMs") is None
    with pytest.raises(KeyError):
        geometry_address("read-unknown", "columns.peakKiB")
    with pytest.raises(ValueError, match="not a geometry read address"):
        geometry_address("read-depth-4", "columns.unknown")


@in_a_child_interpreter
def test_a_geometry_level_reads_every_metric_over_a_provider_free_find() -> None:
    level = GEOMETRY_LEVELS[0]
    for metric in GEOMETRY_METRICS:
        value, reading_unit, samples = _geometry(level, "columns", metric, warmups=1, measured=2)
        assert value > 0
        assert reading_unit == ("us/root" if metric == "elapsedUsPerRoot" else "KiB")
        assert len(samples) == (2 if metric == "elapsedUsPerRoot" else 1)


def test_plan_addresses_name_a_frozen_level_layout_and_metric() -> None:
    level, layout, metric = plan_address("plan-depth-8", "document.elapsedUs") or (None,) * 3
    assert level is not None and level.id == "depth-8"
    assert (layout, metric) == ("document", "elapsedUs")
    assert plan_address("read-depth-8", "document.peakKiB") is None
    assert plan_address("conventional-fanout", "live.eager.maxMs") is None
    with pytest.raises(ValueError, match="not a read-plan compilation level"):
        plan_address("plan-many-8", "columns.retainedKiB")
    with pytest.raises(ValueError, match="not a read-plan compilation address"):
        plan_address("plan-depth-1", "columns.elapsedUsPerRoot")
    with pytest.raises(KeyError):
        plan_address("plan-unknown", "columns.retainedKiB")


def test_the_plan_window_reads_a_cache_of_the_capacity_a_production_handle_composes() -> None:
    composed = signature(Database.connect).parameters["read_plan_cache_capacity"].default
    cache = ColdPlan(plan_levels()[0], "columns").cache
    statistics = cache._statistics()  # pyright: ignore[reportPrivateUsage] - the cache's own census

    assert statistics.capacity == composed


@in_a_child_interpreter
def test_a_cold_plan_checkpoint_prices_one_entry_in_a_cache_composed_before_the_window() -> None:
    import tracemalloc

    level = plan_levels()[0]
    for layout in ("columns", "document"):
        prepared = ColdPlan(level, layout)
        composed = prepared.cache._statistics()  # pyright: ignore[reportPrivateUsage] - the cache's own census
        tracemalloc.start()
        try:
            cold = retained(prepared.cold)
            reopened = prepared.cache._statistics()  # pyright: ignore[reportPrivateUsage] - the cache's own census
            prepared.plan()
            planted = prepared.cache._statistics()  # pyright: ignore[reportPrivateUsage] - the cache's own census
            warm = retained(prepared.warm)
            statistics = prepared.cache._statistics()  # pyright: ignore[reportPrivateUsage] - the cache's own census
        finally:
            tracemalloc.stop()
        assert (composed.size, composed.hits, composed.misses) == (0, 0, 0), layout
        assert (reopened.size, reopened.hits, reopened.misses) == (0, 0, 0), layout
        assert (planted.size, planted.hits, planted.misses) == (1, 0, 1), layout
        assert cold > 4 * 1_024, (layout, cold)
        assert warm < 512, (layout, warm)
        assert statistics.size == 1 and statistics.misses == 1 and statistics.hits > 0
        for metric in PLAN_METRICS:
            value, reading_unit, samples = _plan(level, layout, metric, warmups=1, measured=2)
            assert value > 0
            assert reading_unit == ("us" if metric == "elapsedUs" else "KiB")
            assert len(samples) == (2 if metric == "elapsedUs" else 1)


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
