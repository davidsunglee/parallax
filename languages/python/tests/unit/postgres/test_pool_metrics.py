"""What one pool sample answers, over a pool whose readings are scripted.

The source owns a sample's outcome and its own lifetime: a reading the pool
gave is reported as it stands, a reading the pool could not give is an
unavailable sample rather than a substituted one, and a source the runtime
detached reaches nothing. What a native reading must carry to count as one is
the pool's own mapping, pinned with it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
from typing import Any, cast

import pytest

from parallax.core.internal.db_port import (
    PoolAvailable,
    PoolDetached,
    PoolMetrics,
    PoolUnavailable,
    RouteReadiness,
)
from parallax.core.internal.db_port._runtime._dial_record import DialLedger
from parallax.postgres._pool import PostgresPool
from parallax.postgres._pool_metrics import PostgresPoolMetrics
from parallax.postgres._route import PostgresRoute
from parallax.postgres._runtime import PostgresRuntime


def _metrics(**counters: int) -> PoolMetrics:
    return PoolMetrics(
        pool_min=1, pool_max=10, pool_size=4, pool_available=3, requests_waiting=0, **counters
    )


class _MeasuredPool:
    def __init__(
        self,
        *readings: PoolMetrics | BaseException,
        on_read: Callable[[], None] | None = None,
    ) -> None:
        self._readings = list(readings) or [_metrics()]
        self._on_read = on_read
        self.reads = 0
        self.closes = 0

    def metrics(self) -> PoolMetrics:
        self.reads += 1
        if self._on_read is not None:
            self._on_read()
        reading = self._readings[min(self.reads, len(self._readings)) - 1]
        if isinstance(reading, BaseException):
            raise reading
        return reading

    def close(self) -> None:
        self.closes += 1


def _source(pool: _MeasuredPool, readiness: RouteReadiness = "verified") -> PostgresPoolMetrics:
    return PostgresPoolMetrics(pool, "writer", lambda: readiness)


@pytest.mark.parametrize("readiness", ["verified", "pending", "refused"])
def test_a_reading_reports_the_readiness_of_the_route_its_pool_serves(
    readiness: RouteReadiness,
) -> None:
    # A pool whose route is pending or refused is still measurable: the
    # metrics say what the pool did, and the readiness whether its route
    # serves at all.
    sample = _source(_MeasuredPool(), readiness).sample()

    assert isinstance(sample, PoolAvailable)
    assert sample.metrics == _metrics()
    assert sample.readiness == readiness


def test_each_sample_reports_what_that_reading_said_and_remembers_nothing() -> None:
    # Counters can reset — the pool is free to start over — so a later reading
    # lower than an earlier one is reported as it stands rather than corrected
    # upwards from a remembered maximum.
    source = _source(_MeasuredPool(_metrics(requests_num=40), _metrics(requests_num=2)))

    first, second = source.sample(), source.sample()

    assert isinstance(first, PoolAvailable)
    assert isinstance(second, PoolAvailable)
    assert first.metrics.requests_num == 40
    assert second.metrics.requests_num == 2


# --------------------------------------------------------------------------- #
# A reading that is not a reading.                                             #
# --------------------------------------------------------------------------- #


def test_a_pool_that_raises_answers_unavailable_with_a_detached_diagnostic() -> None:
    sample = _source(_MeasuredPool(RuntimeError("the pool refused to be measured"))).sample()

    assert isinstance(sample, PoolUnavailable)
    assert sample.diagnostic.qualified_type == "builtins.RuntimeError"
    assert sample.diagnostic.message == "the pool refused to be measured"
    # Detached: every field is a plain string or flag, so an exporter retaining
    # samples retains no exception, traceback, or cause graph.
    assert all(
        isinstance(getattr(sample.diagnostic, field.name), str | bool | None)
        for field in fields(sample.diagnostic)
    )


class _NativeStatistics:
    def __init__(self, stats: dict[str, object]) -> None:
        self._stats = stats

    def get_stats(self) -> dict[str, object]:
        return self._stats


def test_a_native_reading_that_cannot_be_believed_is_unavailable_and_names_nothing_it_read() -> (
    None
):
    # What a pool answered is the pool's. The diagnostic says a reading did not
    # carry what a sample reports, which is the whole of what an exporter may
    # be handed about a mapping nobody audited.
    native = _NativeStatistics({"pool_size": "enormous"})
    source = PostgresPoolMetrics(PostgresPool(cast("Any", native)), "writer", lambda: "verified")

    sample = source.sample()

    assert isinstance(sample, PoolUnavailable)
    assert sample.diagnostic.qualified_type.endswith("_MalformedStatistics")
    assert "enormous" not in sample.diagnostic.message
    assert "pool_size" not in sample.diagnostic.message


def test_an_unavailable_source_is_still_attached_and_samples_again() -> None:
    # Unavailable is not detachment and not a terminal state: the runtime is
    # alive, so the next sample an exporter chooses to take is a live one.
    source = _source(_MeasuredPool(RuntimeError("not this time"), _metrics()))

    assert isinstance(source.sample(), PoolUnavailable)
    assert isinstance(source.sample(), PoolAvailable)


def test_a_control_flow_exception_from_the_pool_is_not_an_unavailable_sample() -> None:
    # Ordinary failures are contained because an exporter asking on its own
    # cadence should not have to defend against them. An interpreter being torn
    # down is not one of those, and keeps its own propagation.
    with pytest.raises(KeyboardInterrupt):
        _source(_MeasuredPool(KeyboardInterrupt())).sample()


# --------------------------------------------------------------------------- #
# Detachment.                                                                  #
# --------------------------------------------------------------------------- #


def test_a_detached_source_answers_detached_and_reaches_no_pool() -> None:
    pool = _MeasuredPool()
    source = _source(pool)
    source.detach()

    assert isinstance(source.sample(), PoolDetached)
    assert isinstance(source.sample(), PoolDetached)
    assert pool.reads == 0


def test_detaching_twice_changes_nothing() -> None:
    source = _source(_MeasuredPool())
    source.detach()
    source.detach()

    assert isinstance(source.sample(), PoolDetached)


def test_a_sample_already_reading_when_detachment_happens_completes() -> None:
    # The handshake is the pool itself: detachment happens INSIDE the read this
    # sample is in the middle of, which is the exact interleaving a
    # thread-timing test would be trying to arrange.
    holder: list[PostgresPoolMetrics] = []
    source = _source(_MeasuredPool(on_read=lambda: holder[0].detach()))
    holder.append(source)

    inflight = source.sample()

    assert isinstance(inflight, PoolAvailable)
    assert isinstance(source.sample(), PoolDetached)


# --------------------------------------------------------------------------- #
# What the runtime does with the source it owns.                               #
# --------------------------------------------------------------------------- #


def _runtime(pool: _MeasuredPool) -> PostgresRuntime:
    return PostgresRuntime(
        PostgresRoute("writer", cast("Any", pool), DialLedger()),
        reservation=PostgresRoute(
            "writer", cast("Any", _MeasuredPool()), DialLedger(), "reservation"
        ),
        acquire_timeout=15.0,
    )


def test_the_source_detaches_before_the_pool_closes_even_when_that_close_fails() -> None:
    # The ordering handshake is the close itself: the pool samples the source
    # from inside `close`, so what it records is what a sample taken during the
    # teardown would have seen. A close that then fails does not widen that
    # window, because detachment already happened.
    seen: list[object] = []

    class _ClosingPool(_MeasuredPool):
        def close(self) -> None:
            super().close()
            seen.append(runtime_holder[0].pool_metrics[0].sample())
            raise RuntimeError("the pool would not close")

    runtime_holder: list[PostgresRuntime] = []
    pool = _ClosingPool()
    runtime = _runtime(pool)
    runtime_holder.append(runtime)

    runtime.close()

    assert pool.closes == 1
    assert pool.reads == 0
    assert isinstance(seen[0], PoolDetached)
