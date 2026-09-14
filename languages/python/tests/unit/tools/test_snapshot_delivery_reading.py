from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from snapshot_delivery_reading import (
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
