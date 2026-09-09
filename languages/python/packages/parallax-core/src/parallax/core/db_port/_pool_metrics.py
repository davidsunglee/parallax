"""What a runtime publishes for pool-wide observation, stated neutrally.

A runtime that manages a pool keeps bookkeeping an operator wants — how much
capacity exists, how much of it is idle, how many callers are queued — and one
that manages no pool keeps none. :class:`PoolMetricsSource` is the handle to the
former; ``None`` is the honest answer for the latter.

The handle is named here, in the lifetime contract, rather than beside the
observation machinery that consumes it, because it is a property of the RESOURCE:
what may be measured is decided by what the runtime owns, and who is interested
is decided somewhere else entirely.

Sampling is a QUESTION, never a subscription. Nothing here polls, caches, or
schedules; an exporter asks when it wants a reading and receives one of three
answers, each a value it may keep. Two of the three carry nothing live: a
diagnostic is the detached projection every other resource fact uses, and a
detached source answers about itself rather than about a pool it no longer
reaches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from parallax.core.diagnostics import FailureDiagnostic

__all__ = [
    "PoolAvailable",
    "PoolDetached",
    "PoolMeasurements",
    "PoolMetricsSource",
    "PoolSample",
    "PoolUnavailable",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class PoolMeasurements:
    """One reading of a pool's own bookkeeping, as integers.

    Five **gauges** describe the pool as it is right now. ``pool_min`` and
    ``pool_max`` are the configured retention bounds; ``pool_size`` is the
    capacity the pool currently manages, which includes connections it has
    reserved but not finished preparing; ``pool_available`` is how much of that
    is idle and immediately takeable; ``requests_waiting`` is the length of the
    queue of callers waiting for one.

    The remaining nine are **counters**, accumulated since the runtime opened.
    ``requests_num`` counts checkout calls, ``requests_queued`` the ones that
    had to queue, ``requests_wait_ms`` the milliseconds those queued waits
    took, and ``requests_errors`` the checkout calls that reported an error.
    ``connections_num`` counts connection attempts, ``connections_ms`` the time
    successful attempts took to establish, ``connections_errors`` the ones that
    failed, ``connections_lost`` the connections found broken, and
    ``returns_bad`` the ones handed back in a state that could not be reused.

    They are the pool's own facts and mean exactly what the pool means by them.
    In particular: a counter includes the pool's own housekeeping as well as
    application work, and MAY reset; a queue length MAY include entries whose
    own wait has already timed out and that have not been removed yet; a
    millisecond counter is accumulated whole milliseconds rather than an
    average; and a reading is taken field by field rather than atomically, so
    two fields of one value may describe instants a moment apart. Nothing here
    is a count of connections actively executing: ``pool_size`` minus
    ``pool_available`` is not that number, and no such gauge exists.

    A counter absent from a successful reading is zero, which is why the
    counters default: the pool omits a counter it has never incremented, and
    "never incremented" is what zero says. A gauge is not defaulted, because a
    missing gauge is a reading that could not be taken rather than a zero one.
    """

    pool_min: int
    pool_max: int
    pool_size: int
    pool_available: int
    requests_waiting: int
    requests_num: int = 0
    requests_queued: int = 0
    requests_wait_ms: int = 0
    requests_errors: int = 0
    connections_num: int = 0
    connections_ms: int = 0
    connections_errors: int = 0
    connections_lost: int = 0
    returns_bad: int = 0


@dataclass(frozen=True, slots=True)
class PoolAvailable:
    """The source read its pool and these are the measurements."""

    measurements: PoolMeasurements


@dataclass(frozen=True, slots=True)
class PoolUnavailable:
    """The source is still attached and this reading did not happen.

    Attached is the point: the runtime is alive and the next sample may well
    succeed, so an exporter that asks again later is asking a live source. What
    it must not do is treat this as a measurement — there is no stale reading, no
    substituted zero, and no immediate retry here, because a reading nobody took
    is not a value and the cadence is the exporter's own.
    """

    diagnostic: FailureDiagnostic


@dataclass(frozen=True, slots=True)
class PoolDetached:
    """The runtime this source belonged to has been closed.

    Terminal and self-describing: a detached source reaches no pool, takes no
    measurement, and answers this to every later sample. It carries no
    diagnostic because nothing went wrong — a closed runtime having no
    bookkeeping to report is the ordinary end of its life.
    """


type PoolSample = PoolAvailable | PoolUnavailable | PoolDetached
"""What one :meth:`PoolMetricsSource.sample` answered: a closed union of three.

The three are exhaustive and mutually exclusive, so an exporter that handles all
three has handled everything, and none of them is a degraded form of another.
"""


class PoolMetricsSource(Protocol):
    """A stable, read-only handle on one runtime's pool bookkeeping.

    Stable means its identity does not change for the runtime's life, shutdown
    included: a holder keeps the same object throughout, and what changes when
    the runtime closes is what the handle can answer rather than which object
    answers.

    Reading through it never runs SQL, never takes a connection, and never
    exposes a credential or a native connection: it reads bookkeeping the
    runtime already maintains.
    """

    def sample(self) -> PoolSample:
        """Take one reading now, and answer with one of the three outcomes.

        Total for ordinary failures: a pool that refuses to be read answers
        :class:`PoolUnavailable` rather than raising, because an exporter
        sampling on its own cadence has no call to defend against the reading it
        asked for. A control-flow or fatal exception is not an ordinary failure
        and is not contained.

        Concurrent with everything, the runtime's own close included. A sample
        already in progress when the runtime closes MAY complete and answer with
        the measurements it had taken; every sample begun after that answers
        :class:`PoolDetached`.
        """
        ...
