from __future__ import annotations

import contextlib
import math
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final, Self

import psycopg
import psycopg_pool
from psycopg.rows import TupleRow

from parallax.core.internal.db_port import (
    CheckoutFailed,
    CredentialResolutionError,
    CredentialSource,
    DialRecord,
    DriverManaged,
    PoolMetrics,
    PoolPurpose,
    Route,
)
from parallax.postgres._connection import CONNECT_KWARGS, NativeConnection, initialize_connection
from parallax.postgres._failures import dial_reason
from parallax.postgres._options import PoolOptions, reservation_retention

if TYPE_CHECKING:
    from psycopg_pool.abc import KwargsParam

    from parallax.postgres._endpoint import PostgresEndpoint

__all__ = [
    "DialObserver",
    "NativePool",
    "PostgresPool",
    "open_pool",
    "reservation_socket_options",
]

type NativePool = psycopg_pool.ConnectionPool[NativeConnection]
"""Either native pool this adapter builds; the null pool is a subclass of it."""

_CREDENTIAL_REFUSAL = "the credential source could not produce a password"


class PostgresPool:
    """One native pool, in either retention mode, as the runtime's connection pool.

    An on-demand pool dials on the checking-out thread, so its dial failure
    comes out of :meth:`check_out` itself and is classified there; a retaining
    pool dials on its own workers, whose failures reach the runtime only
    through the pool's dial record.

    Both accounting methods are the native return. The native pool already
    tells the two apart by the connection's state: a closed connection is
    counted as a bad return and its capacity replaced, and :meth:`discard` is
    only ever handed one that is already closed.
    """

    __slots__ = ("_native",)

    def __init__(self, native: NativePool) -> None:
        self._native = native

    def check_out(self, budget: float, /) -> NativeConnection:
        try:
            return self._native.getconn(timeout=budget)
        except psycopg_pool.PoolTimeout as exc:
            raise CheckoutFailed("timeout") from exc
        except psycopg_pool.TooManyRequests as exc:
            raise CheckoutFailed("queue_rejected") from exc
        except psycopg_pool.PoolClosed as exc:
            raise CheckoutFailed("closed") from exc
        except Exception as exc:
            raise CheckoutFailed(dial_reason(exc)) from exc

    def check_in(self, connection: NativeConnection, /) -> None:
        self._native.putconn(connection)

    def discard(self, connection: NativeConnection, /) -> None:
        self._native.putconn(connection)

    def metrics(self) -> PoolMetrics:
        return _pool_metrics(self._native.get_stats())

    def close(self) -> None:
        self._native.close()


class DialObserver:
    """The native hooks through which one pool's dials report to its dial record.

    Three hooks, each reporting what its own step met. :meth:`connect_kwargs`
    produces the driver keywords each physical connection is dialed with,
    resolving the credential source as it goes; :attr:`connection_class` is the
    class the pool dials through, observing the socket and authentication step
    itself; and ``__call__`` is the pool's ``configure``, initializing the
    connection that resulted. Each step that fails reports the failure and
    stops the attempt, so no failure is reported twice, and only
    initialization reports a connection usable.

    Every hook runs on the thread making the attempt: a retaining pool's
    worker, or the caller an on-demand pool dials for. Classification happens
    before the report, so the record holds nothing while a failure is read.
    """

    __slots__ = ("_dial_record", "connection_class")

    def __init__(self, dial_record: DialRecord) -> None:
        self._dial_record = dial_record
        self.connection_class: type[NativeConnection] = _observed_connections(self._report)

    def _report(self, failure: BaseException) -> None:
        self._dial_record.report_failure(dial_reason(failure), failure)

    def __call__(self, connection: NativeConnection) -> None:
        try:
            initialize_connection(connection)
        except Exception as refusal:
            self._report(refusal)
            raise
        self._dial_record.report_usable()

    def connect_kwargs(
        self, base: dict[str, object], source: CredentialSource
    ) -> Callable[[], dict[str, object]]:
        """The pool's ``kwargs``, resolved anew for every connection attempt.

        psycopg_pool calls this on each connection attempt and on no other
        occasion, which is what the seam asks for: the credential is an input to
        connecting, so an attempt that never reaches a connection has already
        asked and a retried attempt asks again, while a reused retained
        connection never reaches it at all. A fresh dictionary comes back each
        time, so the secret is never written into the base the next connection
        would inherit.

        Anything the source raises that is not already a
        :class:`~parallax.core.internal.db_port.CredentialResolutionError` is wrapped in
        one with fixed text and the original chained, so classification does not
        depend on a provider's discipline and the pool's own warning line — which
        prints the exception's text — carries nothing a source put in a message.
        """

        def resolve() -> dict[str, object]:
            try:
                credential = source.resolve()
            except CredentialResolutionError as refusal:
                self._report(refusal)
                raise
            except Exception as exc:
                refusal = CredentialResolutionError(_CREDENTIAL_REFUSAL)
                self._report(refusal)
                raise refusal from exc
            return {**base, "password": credential.secret}

        return resolve


def _observed_connections(
    report: Callable[[BaseException], None],
) -> type[NativeConnection]:
    """A connection class whose failed dials are reported through ``report``.

    The pool sends every dial through its ``connection_class``, on its own
    workers and on an acquiring caller's thread alike, so this is the one place
    that sees the socket and authentication step whoever made it. One class per
    observer keeps each pool's record its own. A dial that completes reports
    nothing: the connection it produced is not usable until it has been
    initialized.
    """

    class _ObservedConnection(psycopg.Connection[TupleRow]):
        @classmethod
        def connect(cls, conninfo: str = "", **kwargs: Any) -> Self:
            try:
                return super().connect(conninfo, **kwargs)
            except Exception as failure:
                report(failure)
                raise

    return _ObservedConnection


def open_pool(
    endpoint: PostgresEndpoint,
    route: Route,
    purpose: PoolPurpose,
    dial_record: DialRecord,
    *,
    acquire_timeout: float,
    prepare_threshold: int | None,
) -> PostgresPool:
    """Create and open the native pool serving ``route`` for ``purpose``, its
    dials reporting to ``dial_record``, or raise the native failure having
    closed what it built.

    A reservation pool dials ``endpoint`` with its credentials under
    :func:`~parallax.postgres._options.reservation_retention`, so it holds no
    connection until the first reservation, and every connection it opens
    carries :func:`reservation_socket_options`.
    """
    connect_options: Mapping[str, object] = {}
    if purpose == "reservation":
        endpoint = replace(endpoint, pool=reservation_retention(endpoint.pool))
        connect_options = reservation_socket_options(acquire_timeout)
    return PostgresPool(
        _open_psycopg_pool(
            endpoint,
            route,
            purpose,
            DialObserver(dial_record),
            acquire_timeout=acquire_timeout,
            prepare_threshold=prepare_threshold,
            connect_options=connect_options,
        )
    )


def reservation_socket_options(acquire_timeout: float) -> Mapping[str, object]:
    """libpq keepalive and unacknowledged-send limits for a reservation
    connection, so the kernel ends one whose server vanished mid-statement
    about ``acquire_timeout`` seconds in.

    An approximate bound: a server that is alive but stalled is the session
    ``statement_timeout`` setup installs, and nothing here is tied to a wall
    clock.
    """
    seconds = max(1, math.ceil(acquire_timeout))
    return {
        "keepalives": 1,
        "keepalives_idle": 1,
        "keepalives_interval": 1,
        "keepalives_count": seconds,
        "tcp_user_timeout": seconds * 1000,
    }


def _open_psycopg_pool(
    endpoint: PostgresEndpoint,
    route: Route,
    purpose: PoolPurpose,
    observer: DialObserver,
    *,
    acquire_timeout: float,
    prepare_threshold: int | None,
    connect_options: Mapping[str, object],
) -> NativePool:
    """Create and open the native pool.

    ``open=False`` then an explicit open, because the driver's implicit opening
    is a deprecated default whose behavior is documented to change. The
    connection keyword arguments are the ones this adapter owns — autocommit,
    row shape, and prepared-statement policy — every dial goes through the
    observer's connection class, and ``configure`` is where every connection,
    however it came to exist, is initialized and checked. The pool is named for
    its route, so the driver's own warnings say which route met them.

    Where a credential source is configured, those keywords become a CALLABLE
    the pool resolves on every connection attempt, which is what makes the
    secret late rather than frozen into configuration. Under
    :data:`~parallax.core.internal.db_port.DRIVER_MANAGED` the static dictionary is
    passed exactly as it would be otherwise and carries no ``password`` at all,
    leaving authentication to the driver and the server.

    No ``reset`` callback is configured. Native return already brings a
    connection back to a usable state or discards it, and a reset callback runs
    after that decision rather than instead of it — so it could not prevent an
    unexpected transaction being rolled back for reuse, which is exactly the
    outcome this adapter refuses by disposing of such a connection itself.

    No ``check`` callback is configured either, so a checkout costs no round
    trip. A connection the server ended while it sat idle is found by its first
    submission instead, which the connection context replaces where that
    submission can be repeated.
    """
    conninfo = endpoint.connection_string
    options = endpoint.pool
    credentials: CredentialSource | DriverManaged = endpoint.credentials
    base: dict[str, object] = {
        **CONNECT_KWARGS,
        **connect_options,
        "prepare_threshold": prepare_threshold,
    }
    name = f"parallax-{route}" if purpose == "application" else f"parallax-{route}-{purpose}"
    kwargs: KwargsParam = (
        base
        if isinstance(credentials, DriverManaged)
        else observer.connect_kwargs(base, credentials)
    )
    pool: NativePool
    if isinstance(options, PoolOptions):
        pool = psycopg_pool.ConnectionPool(
            conninfo,
            connection_class=observer.connection_class,
            kwargs=kwargs,
            open=False,
            configure=observer,
            min_size=options.min_size,
            max_size=options.max_size,
            timeout=acquire_timeout,
            max_waiting=options.max_waiting,
            max_idle=options.max_idle,
            max_lifetime=options.max_lifetime,
            reconnect_timeout=options.reconnect_timeout,
            num_workers=options.num_workers,
            name=name,
        )
    else:
        pool = psycopg_pool.NullConnectionPool(
            conninfo,
            connection_class=observer.connection_class,
            kwargs=kwargs,
            open=False,
            configure=observer,
            max_size=options.max_size,
            timeout=acquire_timeout,
            max_waiting=options.max_waiting,
            max_lifetime=options.max_lifetime,
            reconnect_timeout=options.reconnect_timeout,
            num_workers=options.num_workers,
            name=name,
        )
    try:
        pool.open()
    except BaseException:
        # Nobody else holds it yet, so nothing else would ever close it.
        with contextlib.suppress(Exception):
            pool.close()
        raise
    return pool


_GAUGES: Final = ("pool_min", "pool_max", "pool_size", "pool_available", "requests_waiting")
"""The five readings a sample must carry to be a reading at all.

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
    """Statistics that were read and could not be believed.

    It names no key and no value: what a pool answered is the pool's, and
    repeating it into a diagnostic an application may export is the disclosure
    the pool metrics contract keeps deliberate.
    """


def _pool_metrics(stats: Mapping[str, object]) -> PoolMetrics:
    """``stats`` as metrics, or :class:`_MalformedStatistics` where it is not a reading.

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
        values[name] = _integer(stats.get(name))
    for name in _COUNTERS:
        if name in stats:
            values[name] = _integer(stats[name])
    return PoolMetrics(**values)


def _integer(value: object) -> int:
    """``value`` as a nonnegative reading, or :class:`_MalformedStatistics`.

    ``bool`` is refused although it is an ``int``: a pool reporting ``True`` for
    a size has reported a state flag, and recording it as one connection would
    publish a number nothing measured. Everything else that is not an exact
    ``int`` — a float, a string, a decimal — is refused for the same reason,
    since coercing it would be this module deciding what the pool meant.
    """
    if type(value) is not int or value < 0:
        raise _MalformedStatistics(
            "the connection pool's statistics did not carry the measurements a sample reports"
        )
    return value
