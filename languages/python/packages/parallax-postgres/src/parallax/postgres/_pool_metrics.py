"""Reading the native pool's own bookkeeping, and stopping when the runtime does.

The driver's pool keeps counters and gauges of its own and hands them out as a
plain mapping. Everything here is about the distance between that mapping and
the neutral :class:`~parallax.core.db_port.PoolMeasurements` an exporter
receives: which keys are required, which are absent when they are zero, what a
value has to be to be a measurement at all, and what happens to a reading taken
while the runtime is closing.

The source is created with the runtime and lives exactly as long as it does. It
is the same object before and after the close, which is what lets an exporter
hold it: what a close changes is the ANSWER — every later sample reports the
runtime gone — rather than the identity of the thing being asked.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol

from parallax.core.db_port import (
    PoolAvailable,
    PoolDetached,
    PoolMeasurements,
    PoolSample,
    PoolUnavailable,
)
from parallax.core.diagnostics import diagnostic_for

__all__ = ["NativeStatistics", "PostgresPoolMetrics"]


class NativeStatistics(Protocol):
    """The one thing this module asks a native pool for.

    Its values are annotated ``object`` rather than ``int`` deliberately. The
    driver declares integers, and that declaration is a promise about a release
    rather than a fact about the mapping this receives at runtime — so what is
    read is validated, and the annotation says which of the two this code is
    written against.
    """

    def get_stats(self) -> Mapping[str, object]: ...


_GAUGES: Final = ("pool_min", "pool_max", "pool_size", "pool_available", "requests_waiting")
"""The five measurements a reading must carry to be a reading at all.

The native pool supplies each of them on every successful call, whatever the
pool has done so far, because each describes the pool's current shape rather
than counting something that may not have happened yet. One missing is a pool
that did not answer the question asked, not a pool whose shape is zero.
"""

_COUNTERS: Final = (
    "requests_num",
    "requests_queued",
    "requests_wait_ms",
    "requests_errors",
    "connections_num",
    "connections_ms",
    "connections_errors",
    "connections_lost",
    "returns_bad",
)
"""The nine accumulated counters, each absent until the pool first increments it.

``usage_ms`` is deliberately not among them. The native pool populates it only
from its own convenience checkout context, which this adapter does not use
because that context settles transactions Parallax settles itself — so the
counter would be a constant zero, and a zero that means "never measured" is
worse than a field nobody offered.
"""


class _MalformedStatistics(Exception):
    """Statistics that were read and could not be believed, stated as a failure.

    A sample carries a diagnostic and a mapping that is merely wrong raises
    nothing, so the refusal is raised nowhere and projected here — the same
    device a cleanup issue uses for a condition no exception reported. It names
    no key and no value: what a pool answered is the pool's, and repeating it
    into a diagnostic an application may export is the disclosure this contract
    keeps deliberate.
    """


class PostgresPoolMetrics:
    """The stable source over one native pool, until that pool's runtime closes.

    Detachment is a single attribute becoming ``None``, and every sample reads it
    once into a local before touching it. That is the whole concurrency
    contract, and it is stated in terms of where a sample BEGAN: one that read
    the pool before a detach carries on and answers with what it measured, one
    that reads after answers detached. So a sample can still be inside the
    native read while the pool it read from is being closed. That read copies
    the pool's own counters and measures and takes no lock, so it neither waits
    for the teardown nor delays it — which is why this holds none either.
    """

    __slots__ = ("_pool",)

    def __init__(self, pool: NativeStatistics) -> None:
        self._pool: NativeStatistics | None = pool

    def detach(self) -> None:
        """Give up the pool. Idempotent, and never reversed.

        Called by the runtime BEFORE it closes the pool, so every sample begun
        from here on reaches nothing: the reference is gone before the teardown
        starts, and a slow or failing close does not widen that window. A sample
        that took the reference earlier is not revoked by this and may complete.
        """
        self._pool = None

    def sample(self) -> PoolSample:
        pool = self._pool
        if pool is None:
            return PoolDetached()
        try:
            stats = pool.get_stats()
            measurements = _measurements(stats)
        except Exception as exc:
            return PoolUnavailable(diagnostic_for(exc))
        if measurements is None:
            return PoolUnavailable(
                diagnostic_for(
                    _MalformedStatistics(
                        "the connection pool's statistics did not carry the measurements a "
                        "sample reports"
                    )
                )
            )
        return PoolAvailable(measurements)


def _measurements(stats: Mapping[str, object]) -> PoolMeasurements | None:
    """``stats`` as measurements, or ``None`` where it is not a reading.

    Unknown keys are ignored rather than refused: the pool is free to instrument
    something new, and a Parallax release that broke on it would make a driver
    upgrade a Parallax problem. Absent counters read as zero, which is what the
    pool means by omitting them. Absent gauges and unreadable values do not — and
    a counter the mapping carries with an unreadable value is unreadable rather
    than absent, which is why membership decides that and never the value.

    No relationship between fields is checked. The reading is not atomic, so
    ``pool_available`` may exceed a ``pool_size`` read a moment earlier, and a
    check for that would turn an ordinary race into an unavailable sample.
    """
    values: dict[str, int] = {}
    for name in _GAUGES:
        measurement = _integer(stats.get(name))
        if measurement is None:
            return None
        values[name] = measurement
    for name in _COUNTERS:
        if name not in stats:
            continue
        measurement = _integer(stats[name])
        if measurement is None:
            return None
        values[name] = measurement
    return PoolMeasurements(**values)


def _integer(value: object) -> int | None:
    """``value`` as a nonnegative measurement, or ``None`` if it is not one.

    ``bool`` is refused although it is an ``int``: a pool reporting ``True`` for
    a size has reported a state flag, and recording it as one connection would
    publish a number nothing measured. Everything else that is not an exact
    ``int`` — a float, a string, a decimal — is refused for the same reason,
    since coercing it would be this module deciding what the pool meant.
    """
    if type(value) is not int or value < 0:
        return None
    return value
