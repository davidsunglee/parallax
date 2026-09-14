from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import snapshot_delivery_reading
from parallax.conformance.workloads import catalog
from snapshot_delivery_reading import (
    CatalogPort,
    _last_streamed,  # pyright: ignore[reportPrivateUsage] - drain protocol is under test
    _timed,  # pyright: ignore[reportPrivateUsage] - sampling protocol is under test
)


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
