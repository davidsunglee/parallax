"""What an idle key-reservation pool costs the interpreter before it connects.

The pool is the production one: the reservation pool ``PostgresDriver.open_pool``
opens over a writer endpoint at its default retention, reporting to a real dial
ledger, whose reservation capacity is one connection, kept by one worker, with
nothing retained at the minimum, so opening it starts the pool's threads and
dials nothing. Its
credential source refuses and records being asked, so an accidental connection
attempt fails the reading rather than measuring a connection that should not
exist.

Two cells. ``pool-open-live`` reads the Python bytes reachable while one such
pool is open; ``pool-start-close-cycle`` reads what repeated opening and
closing accumulates and what one cycle allocates and frees again. The
accumulated figure is reported rather than graded: each pool builds its own
connection class, and how many of those the collector has yet to free at the
sample moves it by kilobytes without growing with the cycles. The process's
thread count is read beside them, before the pool, while it is open, and once
it closed. Every byte figure is what ``tracemalloc`` traces through CPython's
allocator: a connected session, libpq's own memory, thread stacks, and the
server's side are in none of them.
"""

from __future__ import annotations

import sys
import threading
import tracemalloc
from collections.abc import Callable
from typing import Final

import pytest

from parallax.core.internal.db_port import CredentialResolutionError, Password, PoolPurpose
from parallax.core.internal.db_port._runtime._dial_record import DialLedger
from parallax.postgres import PoolOptions, PostgresAdapter
from parallax.postgres._driver import PostgresDriver
from parallax.postgres._endpoint import PostgresEndpoint
from parallax.postgres._pool import PostgresPool
from tests._support.pooled_key_diagnostic import requested, write_readings
from tests.unit.memory_instruments import (
    REPEATS,
    WARMUP,
    Seam,
    allocation,
    in_a_child_interpreter,
    retained,
    serve_one_measurement,
)

_SCHEMA: Final = "parallax.diagnostic.pooled-primary-keys.pool-memory/1"


class _Refusing:
    """A credential source that records being asked and refuses: asking is
    what a connection attempt does first."""

    def __init__(self) -> None:
        self.asked = threading.Event()

    def resolve(self) -> Password:
        self.asked.set()
        raise CredentialResolutionError("this pool is measured idle and must never connect")


def _endpoint(credentials: _Refusing, options: PoolOptions) -> PostgresEndpoint:
    return PostgresEndpoint("host=127.0.0.1 port=1", credentials=credentials, pool=options)


def _opened(credentials: _Refusing, options: PoolOptions, purpose: PoolPurpose) -> PostgresPool:
    configuration = PostgresAdapter(
        writer=_endpoint(credentials, options), acquire_timeout=1.0, prepare_threshold=None
    )
    return PostgresDriver(configuration).open_pool("writer", purpose, DialLedger())


def _pool(credentials: _Refusing) -> PostgresPool:
    """The reservation pool a writer at its default retention opens."""
    return _opened(credentials, PoolOptions(), "reservation")


def never_dialed(credentials: _Refusing, pool: PostgresPool) -> None:
    """Refuse a pool that asked for a credential, counted a connection attempt,
    or served a checkout."""
    metrics = pool.metrics()
    attempted = metrics.connections_num + metrics.requests_num
    if credentials.asked.is_set() or attempted:
        raise AssertionError(f"the idle pool reached for a connection: {metrics}")


def _threads_around() -> tuple[int, int, int]:
    """Threads before one idle pool opens, while it is open, and once it closed,
    after checking it dialed nothing."""
    credentials = _Refusing()
    before = threading.active_count()
    pool = _pool(credentials)
    opened = threading.active_count()
    never_dialed(credentials, pool)
    pool.close()
    return before, opened, threading.active_count()


def _open_live(credentials: _Refusing) -> Seam:
    def seam(sample: Callable[[], None]) -> None:
        pool = _pool(credentials)
        sample()
        pool.close()

    return seam


def _cycle(credentials: _Refusing) -> Seam:
    def seam(sample: Callable[[], None]) -> None:
        _pool(credentials).close()
        sample()

    return seam


def _reading[T](measure: Callable[[], T]) -> T:
    tracemalloc.start()
    try:
        return measure()
    finally:
        tracemalloc.stop()


def _record(cell: str, readings: dict[str, object]) -> None:
    mode, out = requested()
    if out is not None:
        write_readings(out, cell, {"schema": _SCHEMA, "mode": mode, "cell": cell, **readings})


@in_a_child_interpreter
def test_an_open_idle_pool_holds_its_threads_until_it_closes() -> None:
    credentials = _Refusing()
    retained_bytes = _reading(lambda: retained(_open_live(credentials)))
    before, opened, closed = _threads_around()
    assert not credentials.asked.is_set()
    assert opened > before
    assert closed == before
    assert retained_bytes > 0
    _record(
        "pool-open-live",
        {
            "retainedBytes": retained_bytes,
            "warmup": WARMUP,
            "threads": {"before": before, "open": opened, "closed": closed},
        },
    )


@in_a_child_interpreter
def test_an_idle_pool_opened_and_closed_repeatedly_dials_nothing_and_ends_its_threads() -> None:
    credentials = _Refusing()
    kept, transient = _reading(lambda: allocation(_cycle(credentials)))
    before, opened, closed = _threads_around()
    assert not credentials.asked.is_set()
    assert closed == before
    assert transient > 0
    _record(
        "pool-start-close-cycle",
        {
            "keptOverRepeatsBytes": kept,
            "repeats": REPEATS,
            "warmup": WARMUP,
            "transientBytes": transient,
            "threads": {"before": before, "open": opened, "closed": closed},
        },
    )


def test_a_pool_that_reaches_for_a_connection_fails_the_reading() -> None:
    credentials = _Refusing()
    pool = _opened(credentials, PoolOptions(min_size=1, max_size=1, num_workers=1), "application")
    try:
        assert credentials.asked.wait(timeout=10.0)
        with pytest.raises(AssertionError, match="reached for a connection"):
            never_dialed(credentials, pool)
    finally:
        pool.close()


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
