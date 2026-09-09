"""What one pool sample answers, over a native pool whose statistics are scripted.

Sampling is the only place a native mapping becomes a Parallax value, so this is
where the distance between the two is pinned: which keys a reading must carry,
which are absent exactly when they are zero, what a value has to BE to count as
a measurement, and what a reading does when the runtime it belongs to is closing
underneath it.

The pins are deliberately conservative about what a number means. A pool that
answered something unreadable produces no measurement rather than a coerced one;
a counter the pool never incremented reads zero because that is what the pool
means by omitting it; and no relationship between two fields is checked at all,
because the reading is taken field by field and a "contradiction" between two of
them is an ordinary race rather than a broken pool.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Any, cast

import pytest

from parallax.core.db_port import (
    PoolAvailable,
    PoolDetached,
    PoolMeasurements,
    PoolUnavailable,
)
from parallax.postgres._options import PoolOptions
from parallax.postgres._pool_metrics import PostgresPoolMetrics
from parallax.postgres._runtime import PostgresRuntime

_GAUGES: dict[str, object] = {
    "pool_min": 1,
    "pool_max": 10,
    "pool_size": 4,
    "pool_available": 3,
    "requests_waiting": 0,
}

_COUNTERS: dict[str, object] = {
    "requests_num": 17,
    "requests_queued": 2,
    "requests_wait_ms": 45,
    "requests_errors": 1,
    "connections_num": 5,
    "connections_ms": 130,
    "connections_errors": 1,
    "connections_lost": 2,
    "returns_bad": 3,
}


class _StatsPool:
    """A native pool that answers ``get_stats`` and counts being asked."""

    def __init__(
        self,
        *readings: Mapping[str, object],
        raises: BaseException | None = None,
        on_read: Any = None,
    ) -> None:
        self._readings = list(readings) or [{**_GAUGES, **_COUNTERS}]
        self._raises = raises
        self._on_read = on_read
        self.reads = 0
        self.closes = 0

    def get_stats(self) -> Mapping[str, object]:
        self.reads += 1
        if self._on_read is not None:
            self._on_read()
        if self._raises is not None:
            raise self._raises
        return self._readings[min(self.reads, len(self._readings)) - 1]

    def close(self) -> None:
        self.closes += 1


def _source(pool: _StatsPool) -> PostgresPoolMetrics:
    return PostgresPoolMetrics(pool)


def _available(pool: _StatsPool) -> PoolMeasurements:
    sample = _source(pool).sample()
    assert isinstance(sample, PoolAvailable)
    return sample.measurements


# --------------------------------------------------------------------------- #
# A reading that succeeded.                                                    #
# --------------------------------------------------------------------------- #


def test_a_full_native_reading_becomes_measurements_field_for_field() -> None:
    measurements = _available(_StatsPool({**_GAUGES, **_COUNTERS}))

    assert measurements == PoolMeasurements(
        pool_min=1,
        pool_max=10,
        pool_size=4,
        pool_available=3,
        requests_waiting=0,
        requests_num=17,
        requests_queued=2,
        requests_wait_ms=45,
        requests_errors=1,
        connections_num=5,
        connections_ms=130,
        connections_errors=1,
        connections_lost=2,
        returns_bad=3,
    )


def test_counters_the_pool_never_incremented_read_as_zero() -> None:
    # The native pool omits a counter it has never touched, and "never touched"
    # is what zero says. A gauge is not defaulted this way, which is the next
    # test: the pool supplies every gauge on every successful call.
    measurements = _available(_StatsPool(dict(_GAUGES)))

    assert measurements.requests_num == 0
    assert measurements.connections_lost == 0
    assert measurements.returns_bad == 0
    assert measurements.pool_max == 10


def test_a_measurement_the_contract_does_not_name_is_ignored() -> None:
    # `usage_ms` is the concrete instance: the native pool populates it only
    # from a checkout context this adapter does not use, so it is a key the
    # contract deliberately omits rather than one it never expected.
    measurements = _available(
        _StatsPool({**_GAUGES, "usage_ms": 900, "something_a_later_release_added": 7})
    )

    assert measurements.pool_size == 4
    assert not hasattr(measurements, "usage_ms")


def test_no_relationship_between_two_fields_is_checked() -> None:
    # The reading is taken field by field rather than atomically, so more
    # available than managed is a pool measured mid-change, not a broken one.
    measurements = _available(_StatsPool({**_GAUGES, "pool_size": 1, "pool_available": 4}))

    assert measurements.pool_size == 1
    assert measurements.pool_available == 4


def test_each_sample_reports_what_that_reading_said_and_remembers_nothing() -> None:
    # Counters can reset — the pool is free to start over — so a later reading
    # lower than an earlier one is reported as it stands rather than corrected
    # upwards from a remembered maximum.
    pool = _StatsPool({**_GAUGES, "requests_num": 40}, {**_GAUGES, "requests_num": 2})
    source = _source(pool)

    first, second = source.sample(), source.sample()

    assert isinstance(first, PoolAvailable)
    assert isinstance(second, PoolAvailable)
    assert first.measurements.requests_num == 40
    assert second.measurements.requests_num == 2


# --------------------------------------------------------------------------- #
# A reading that is not a reading.                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("missing", sorted(_GAUGES))
def test_a_missing_gauge_makes_the_sample_unavailable(missing: str) -> None:
    reading = {**_GAUGES, **_COUNTERS}
    del reading[missing]

    assert isinstance(_source(_StatsPool(reading)).sample(), PoolUnavailable)


@pytest.mark.parametrize(
    "value",
    [True, False, 1.0, "4", None, Ellipsis, -1],
    ids=["true", "false", "float", "string", "null", "object", "negative"],
)
@pytest.mark.parametrize("field", ["pool_size", "requests_num"])
def test_a_measurement_that_is_not_a_nonnegative_integer_makes_it_unavailable(
    field: str, value: object
) -> None:
    # A gauge and a counter, because the refusal is about the VALUE rather than
    # about which half of the contract it belongs to. `True` is refused although
    # it is an `int`: a pool reporting a flag where a size belongs has reported
    # no size, and recording it as one connection would publish a number nothing
    # measured.
    sample = _source(_StatsPool({**_GAUGES, **_COUNTERS, field: value})).sample()

    assert isinstance(sample, PoolUnavailable)


def test_an_unavailable_sample_names_no_key_and_no_value_it_read() -> None:
    # What a pool answered is the pool's. The diagnostic says a reading did not
    # carry what a sample reports, which is the whole of what an exporter may
    # be handed about a mapping nobody audited.
    sample = _source(_StatsPool({**_GAUGES, "pool_size": "enormous"})).sample()

    assert isinstance(sample, PoolUnavailable)
    assert "enormous" not in sample.diagnostic.message
    assert "pool_size" not in sample.diagnostic.message


def test_a_pool_that_raises_answers_unavailable_with_a_detached_diagnostic() -> None:
    failure = RuntimeError("the pool refused to be measured")
    sample = _source(_StatsPool(raises=failure)).sample()

    assert isinstance(sample, PoolUnavailable)
    assert sample.diagnostic.qualified_type == "builtins.RuntimeError"
    assert sample.diagnostic.message == "the pool refused to be measured"
    # Detached: every field is a plain string or flag, so an exporter retaining
    # samples retains no exception, traceback, or cause graph.
    assert all(
        isinstance(getattr(sample.diagnostic, field.name), str | bool | None)
        for field in fields(sample.diagnostic)
    )


def test_an_unavailable_source_is_still_attached_and_samples_again() -> None:
    # Unavailable is not detachment and not a terminal state: the runtime is
    # alive, so the next sample an exporter chooses to take is a live one.
    pool = _StatsPool({"pool_min": 1}, {**_GAUGES, **_COUNTERS})
    source = _source(pool)

    assert isinstance(source.sample(), PoolUnavailable)
    assert isinstance(source.sample(), PoolAvailable)


def test_a_control_flow_exception_from_the_pool_is_not_an_unavailable_sample() -> None:
    # Ordinary failures are contained because an exporter asking on its own
    # cadence should not have to defend against them. An interpreter being torn
    # down is not one of those, and keeps its own propagation.
    with pytest.raises(KeyboardInterrupt):
        _source(_StatsPool(raises=KeyboardInterrupt())).sample()


# --------------------------------------------------------------------------- #
# Detachment.                                                                  #
# --------------------------------------------------------------------------- #


def test_a_detached_source_answers_detached_and_reaches_no_pool() -> None:
    pool = _StatsPool()
    source = _source(pool)
    source.detach()

    assert isinstance(source.sample(), PoolDetached)
    assert isinstance(source.sample(), PoolDetached)
    assert pool.reads == 0


def test_detaching_twice_changes_nothing() -> None:
    source = _source(_StatsPool())
    source.detach()
    source.detach()

    assert isinstance(source.sample(), PoolDetached)


def test_a_sample_already_reading_when_detachment_happens_completes() -> None:
    # The handshake is the pool itself: detachment happens INSIDE the native
    # call this sample is in the middle of, which is the exact interleaving a
    # thread-timing test would be trying to arrange.
    holder: list[PostgresPoolMetrics] = []
    pool = _StatsPool(on_read=lambda: holder[0].detach())
    source = _source(pool)
    holder.append(source)

    inflight = source.sample()

    assert isinstance(inflight, PoolAvailable)
    assert isinstance(source.sample(), PoolDetached)


# --------------------------------------------------------------------------- #
# What the runtime does with the source it owns.                               #
# --------------------------------------------------------------------------- #


def _runtime(pool: _StatsPool) -> PostgresRuntime:
    from parallax.postgres._connection import ConnectionPreparation

    return PostgresRuntime(cast("Any", pool), PoolOptions(), ConnectionPreparation())


def test_a_runtime_publishes_one_source_that_stays_the_same_object() -> None:
    # Stable identity is what lets an exporter hold it: a close changes the
    # ANSWER rather than which object answers.
    runtime = _runtime(_StatsPool())
    before = runtime.pool_metrics

    runtime.close()

    assert before is not None
    assert runtime.pool_metrics is before


def test_the_source_detaches_before_the_native_close_even_when_that_close_fails() -> None:
    # The ordering handshake is the close itself: the fake pool samples the
    # source from inside `close`, so what it records is what a sample taken
    # during the teardown would have seen. A close that then fails does not
    # widen that window, because detachment already happened.
    seen: list[object] = []

    class _ClosingPool(_StatsPool):
        def close(self) -> None:
            super().close()
            seen.append(runtime_holder[0].pool_metrics)
            seen.append(cast("Any", runtime_holder[0].pool_metrics).sample())
            raise RuntimeError("the native pool would not close")

    runtime_holder: list[PostgresRuntime] = []
    pool = _ClosingPool()
    runtime = _runtime(pool)
    runtime_holder.append(runtime)

    runtime.close()

    assert pool.closes == 1
    assert isinstance(seen[1], PoolDetached)


def test_a_closed_runtime_takes_no_measurement_however_often_it_is_asked() -> None:
    pool = _StatsPool()
    runtime = _runtime(pool)
    source = runtime.pool_metrics
    assert source is not None
    assert isinstance(source.sample(), PoolAvailable)

    runtime.close()
    reads_at_close = pool.reads

    assert isinstance(source.sample(), PoolDetached)
    assert pool.reads == reads_at_close
