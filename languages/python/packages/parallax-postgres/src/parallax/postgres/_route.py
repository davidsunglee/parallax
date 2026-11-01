from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, Final, Literal

import psycopg_pool

from parallax.core.base import INFINITY
from parallax.core.db_port import (
    CredentialSource,
    DatabaseStartupError,
    DriverManaged,
    Route,
    RouteReadiness,
    Row,
    report_route_readiness,
)
from parallax.postgres._connection import CONNECT_KWARGS, ConnectionEstablishment
from parallax.postgres._options import PoolOptions
from parallax.postgres._pool_metrics import PostgresPoolMetrics

if TYPE_CHECKING:
    from psycopg_pool.abc import KwargsParam

    from parallax.postgres._context import NativePool
    from parallax.postgres._endpoint import PostgresEndpoint

__all__ = ["PROBE_SQL", "PostgresRoute", "ProbeMismatch", "check_probe", "open_route"]

PROBE_SQL: Final = """SELECT
    1 AS ready,
    'infinity'::timestamptz AS temporal_bound,
    '{"ready": true}'::jsonb AS document,
    '7.038530691851209e-26'::float8::real AS float32_witness,
    0.30000000000000004::float8 AS float64_witness,
    session_user AS login_identity"""
"""The one statement that proves a route can serve.

It proves the decodings the read path cannot work without and that a bare
connectivity check does not exercise: an ordinary integer, the neutral sentinel a
temporal interval's open upper bound reads back as, a structured document
decoded to a mapping, and two floats that come back exactly only when the server
spells floats without rounding them. It also captures the authenticated
``session_user`` that database-login execution projects as its identity, and
that every other route must match. It reads no model, opens no explicit
transaction, and registers nothing — the connection it runs on was already
initialized like every other. It is a smoke probe, not a substitute for the
codec suites.

The Float64 witness needs all 17 significant digits. The Float32 witness is one
whose shortest spelling, parsed to the nearest binary64 and then narrowed, lands
on the adjacent binary32 value, so it also reads back exactly only through the
adapter's own Float32 loader.
"""

_FLOAT32_WITNESS: Final = 7.038530691851209e-26
_FLOAT64_WITNESS: Final = 0.30000000000000004
_ROUNDED_FLOATS = (
    "the session's extra_float_digits is at or below zero, so the server rounds float "
    "output, which no loader can recover; set it to 1 or more"
)
_OTHER_LOGIN = "the reader route authenticated a different database login than the writer"


class ProbeMismatch(Exception):
    """The probe ran but read back something other than what it asked for.

    That is a positive incompatibility rather than an outage: the same route
    would read the same thing back next time.
    """


def check_probe(rows: list[Row], expected_login: str | None) -> str:
    """The login the probe's ``rows`` authenticated, or :class:`ProbeMismatch`.

    ``expected_login``, where given, is the login every route must share.
    """
    if len(rows) != 1:
        raise ProbeMismatch(f"the startup probe returned {len(rows)} rows rather than one")
    (row,) = rows
    if len(row) != 6:
        raise ProbeMismatch(f"the startup probe returned {len(row)} columns rather than six")
    if row[0] != 1:
        raise ProbeMismatch("the startup probe did not read its integer back")
    if row[1] is not INFINITY:
        raise ProbeMismatch("the startup probe did not read an unbounded instant back")
    if row[2] != {"ready": True}:
        raise ProbeMismatch("the startup probe did not read its structured document back")
    if row[4] != _FLOAT64_WITNESS:
        raise ProbeMismatch(
            f"the startup probe did not read its Float64 back exactly: {_ROUNDED_FLOATS}"
        )
    if row[3] != _FLOAT32_WITNESS:
        raise ProbeMismatch(
            f"the startup probe did not read its Float32 back exactly: either the adapter's "
            f"Float32 loader is not installed, or {_ROUNDED_FLOATS}"
        )
    login = row[5]
    if not isinstance(login, str) or not login:
        raise ProbeMismatch("the startup probe did not read a nonempty session_user")
    if expected_login is not None and login != expected_login:
        raise ProbeMismatch(_OTHER_LOGIN)
    return login


type _State = Literal["unproven", "verified", "pending", "refused"]


class PostgresRoute:
    """One declared route: its native pool, how that pool establishes
    connections, its measurements, and whether it has proved it can serve.

    A route starts unproven, while startup proves it. Startup then makes it
    ``verified``, or ``pending`` where the reader could not be reached and its
    proof was deferred. A pending route proves itself on the connections it
    hands over: the first proof that succeeds makes it ``verified``, and the
    first that positively mismatches makes it ``refused`` for good. Those two
    transitions are decided under one lock, so the first one wins and nothing
    afterwards — a concurrent proof that also succeeded included — moves a
    refused route or admits work on it.
    """

    __slots__ = ("_lock", "_refusal", "_state", "establishment", "metrics", "pool", "route")

    def __init__(
        self, route: Route, pool: NativePool, establishment: ConnectionEstablishment
    ) -> None:
        self.route: Route = route
        self.pool = pool
        self.establishment = establishment
        self._state: _State = "unproven"
        self._refusal: ProbeMismatch | None = None
        self._lock = threading.Lock()
        self.metrics = PostgresPoolMetrics(pool, route, self.readiness)

    def readiness(self) -> RouteReadiness:
        """What a sample reports: an unproven route has proved nothing yet."""
        state = self._state
        return "pending" if state == "unproven" else state

    @property
    def awaiting_verification(self) -> bool:
        """Whether a connection this route hands over must prove it first."""
        return self._state == "pending"

    @property
    def refusal(self) -> ProbeMismatch | None:
        """The mismatch that refused this route, once one has."""
        return self._refusal

    def proved_at_startup(self) -> None:
        self._state = "verified"

    def defer_verification(self) -> None:
        self._state = "pending"
        report_route_readiness(self.route, "pending")

    def verified(self) -> ProbeMismatch | None:
        """Record a successful proof, answering the refusal that already stands
        in its way, if another proof refused the route first."""
        with self._lock:
            refusal = self._refusal
            if refusal is not None:
                return refusal
            transitioned = self._state == "pending"
            self._state = "verified"
        if transitioned:
            report_route_readiness(self.route, "verified")
        return None

    def refuse(self, mismatch: ProbeMismatch) -> None:
        """Record a positive mismatch, which refuses a route that was still pending.

        A route already verified stays verified: one connection that read
        something else back fails its own acquisition, and readiness is not
        revisited once it has been decided.
        """
        with self._lock:
            if self._state != "pending":
                return
            self._state = "refused"
            self._refusal = mismatch
        report_route_readiness(self.route, "refused")

    def abandon(self) -> None:
        """Close the pool of a runtime that is never published, reporting nothing."""
        self.metrics.detach()
        with contextlib.suppress(Exception):
            self.pool.close()


def open_route(
    endpoint: PostgresEndpoint,
    route: Route,
    *,
    acquire_timeout: float,
    prepare_threshold: int | None,
) -> PostgresRoute:
    """Create and open ``route``'s native pool over ``endpoint``, unproven."""
    establishment = ConnectionEstablishment()
    return PostgresRoute(
        route,
        _build_pool(endpoint, route, acquire_timeout, prepare_threshold, establishment),
        establishment,
    )


def _build_pool(
    endpoint: PostgresEndpoint,
    route: Route,
    acquire_timeout: float,
    prepare_threshold: int | None,
    establishment: ConnectionEstablishment,
) -> NativePool:
    """Create and open the native pool one route manages.

    ``open=False`` then an explicit open, because the driver's implicit opening
    is a deprecated default whose behavior is documented to change. The
    connection keyword arguments are the ones this adapter owns — autocommit,
    row shape, and prepared-statement policy — every dial goes through the
    establishment's connection class, and ``configure`` is where every
    connection, however it came to exist, is initialized and checked. The pool
    is named for its route, so the driver's own warnings say which route met
    them.

    Where a credential source is configured, those keywords become a CALLABLE
    the pool resolves on every connection attempt, which is what makes the
    secret late rather than frozen into configuration. Under
    :data:`~parallax.core.db_port.DRIVER_MANAGED` the static dictionary is
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
    base: dict[str, object] = {**CONNECT_KWARGS, "prepare_threshold": prepare_threshold}
    kwargs: KwargsParam = (
        base
        if isinstance(credentials, DriverManaged)
        else establishment.connect_kwargs(base, credentials)
    )
    pool: NativePool
    if isinstance(options, PoolOptions):
        pool = psycopg_pool.ConnectionPool(
            conninfo,
            connection_class=establishment.connection_class,
            kwargs=kwargs,
            open=False,
            configure=establishment,
            min_size=options.min_size,
            max_size=options.max_size,
            timeout=acquire_timeout,
            max_waiting=options.max_waiting,
            max_idle=options.max_idle,
            max_lifetime=options.max_lifetime,
            reconnect_timeout=options.reconnect_timeout,
            num_workers=options.num_workers,
            name=f"parallax-{route}",
        )
    else:
        pool = psycopg_pool.NullConnectionPool(
            conninfo,
            connection_class=establishment.connection_class,
            kwargs=kwargs,
            open=False,
            configure=establishment,
            max_size=options.max_size,
            timeout=acquire_timeout,
            max_waiting=options.max_waiting,
            max_lifetime=options.max_lifetime,
            reconnect_timeout=options.reconnect_timeout,
            num_workers=options.num_workers,
            name=f"parallax-{route}",
        )
    try:
        pool.open()
    except Exception as exc:
        with contextlib.suppress(Exception):
            pool.close()
        raise DatabaseStartupError(
            f"the database runtime's {route} connection pool could not be opened",
            route=route,
            phase="open",
        ) from exc
    return pool
