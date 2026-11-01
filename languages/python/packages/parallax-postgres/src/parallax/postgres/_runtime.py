from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from parallax.core.db_port import (
    CleanupIssue,
    ConnectionAcquisitionError,
    ConnectionContext,
    ConnectionContextSource,
    InvalidAuthorizationError,
    PoolMetricsSource,
    ReleaseUnconfirmed,
    Route,
    RouteCapabilities,
    RoutePolicy,
    report_resource_issues,
)
from parallax.core.diagnostics import diagnostic_for
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres._authorization import PostgresRole
from parallax.postgres._context import PostgresConnectionContext
from parallax.postgres._route_plan import planned_route

if TYPE_CHECKING:
    from parallax.postgres._route import PostgresRoute

__all__ = ["PostgresRuntime"]

_CLOSED = "this Database is closed, so it opens no new database connection"

_WRITER: Final = RouteCapabilities.every_level()
_READER: Final = RouteCapabilities(frozenset({"read_committed", "repeatable_read"}))
"""A hot standby begins a read-only transaction at these levels and refuses
``serializable``, so a reader route never declares it."""


class PostgresRuntime:
    """One independent running Postgres resource, owned by one connected handle.

    Two runtimes built from one configuration share nothing: closing either
    leaves the other working, which is what makes reusing configuration safe.
    It serves its writer route through one pool and, where one is configured,
    its reader route through another; both share one admission decision and
    one close.
    """

    dialect: Dialect = POSTGRES

    __slots__ = (
        "_acquire_timeout",
        "_admission",
        "_closed",
        "_login_identity",
        "_reader",
        "_routes",
        "_writer",
    )

    def __init__(
        self,
        writer: PostgresRoute,
        reader: PostgresRoute | None = None,
        *,
        acquire_timeout: float,
    ) -> None:
        self._writer = writer
        self._reader = reader
        self._acquire_timeout = acquire_timeout
        self._routes: Mapping[Route, RouteCapabilities] = MappingProxyType(
            {"writer": _WRITER} if reader is None else {"writer": _WRITER, "reader": _READER}
        )
        self._closed = False
        self._login_identity: str | None = None
        # Held only across the two field reads that decide admission, never
        # across a checkout, a statement, or a callback: an acquisition that
        # blocks must not be able to block a close.
        self._admission = threading.Lock()

    @property
    def routes(self) -> Mapping[Route, RouteCapabilities]:
        return self._routes

    @property
    def pool_metrics(self) -> tuple[PoolMetricsSource, ...]:
        """One source per route's pool, each the same object for the runtime's whole life.

        A pool is what each route manages, so there is always something to
        measure and this is never empty. Each source stays the same object
        across the close as well: an exporter holding one keeps a handle that
        answers detached rather than a handle that has gone stale.
        """
        return tuple(route.metrics for route in self._served())

    @property
    def login_identity(self) -> str:
        """The authenticated login captured by this runtime's readiness probe."""
        identity = self._login_identity
        if identity is None:
            raise RuntimeError("the database runtime has not completed startup")
        return identity

    def _complete_startup(self, login: str) -> None:
        """Install the writer's validated login exactly once."""
        if self._login_identity is not None:
            raise RuntimeError("the database runtime has already completed startup")
        self._login_identity = login

    def login_source(self) -> ConnectionContextSource:
        """Bind execution under the authenticated login without acquiring."""
        return _PostgresContextSource(self, None)

    def principal_source(self, authorization: PostgresRole) -> ConnectionContextSource:
        """Bind execution under ``authorization`` without acquiring."""
        if not isinstance(authorization, PostgresRole):  # pyright: ignore[reportUnnecessaryIsInstance] - validates untyped callers at the public boundary
            raise InvalidAuthorizationError(
                "PostgreSQL principal execution requires a PostgresRole"
            )
        return _PostgresContextSource(self, authorization)

    def acquisition(self, route: PostgresRoute, deadline: float) -> PostgresConnectionContext:
        """A fresh acquisition on ``route`` bounded by ``deadline`` rather than by
        the ordinary budget.

        Startup uses this: readiness has one budget of its own that the
        acquisition it makes has to fit inside, rather than an ordinary
        acquisition timeout added to it. The route is still unproven, so the
        lease runs no proof of its own: startup's probe is that proof.
        """
        return PostgresConnectionContext(route, self._admit, deadline, None, expected_login=None)

    def _context(self, role: PostgresRole | None, policy: RoutePolicy) -> PostgresConnectionContext:
        reader = self._reader
        planned = planned_route(policy, has_reader=reader is not None)
        route = reader if planned == "reader" and reader is not None else self._writer
        return PostgresConnectionContext(
            route,
            self._admit,
            monotonic() + self._acquire_timeout,
            role,
            expected_login=self._login_identity,
        )

    def _served(self) -> tuple[PostgresRoute, ...]:
        reader = self._reader
        return (self._writer,) if reader is None else (self._writer, reader)

    def close(self) -> None:
        """Stop admitting work and close every route's native pool. Idempotent and permanent.

        Admission stops first, so nothing is admitted on any route while the
        pools are being torn down. Each native close then refuses waiting and
        future checkouts, closes what is idle, and closes what comes back
        later; it neither drains borrowers nor interrupts their statements, so
        an operation already running finishes on the connection it holds and
        that connection is closed when it is returned.

        Every metrics source detaches between the two, so every sample begun
        after that reaches nothing — and a native close that is slow or that
        fails delays nothing about that, because detachment has already happened
        by then. A sample already inside the native read may complete and report
        what it measured; that read copies bookkeeping and waits for nothing
        this close holds.

        Problems closing are reported through the restricted resource logger and
        never raised, and one route's failure to close does not stop the
        other's: close is what a caller runs while unwinding, and a handle that
        refused to close would leave them nothing better to do.
        """
        with self._admission:
            if self._closed:
                return
            self._closed = True
        routes = self._served()
        for route in routes:
            route.metrics.detach()
        for route in routes:
            try:
                route.pool.close()
            except Exception as exc:
                report_resource_issues("shutdown", _shutdown_issue(exc))

    def _admit(self, deadline: float) -> None:
        """Decide, in one critical section, whether this acquisition may proceed.

        Expiry and closure together, because either alone can change while the
        other is being asked. A late native success is refused here rather than
        admitted: the caller has already been waiting past what it asked for,
        and its own timeout handling is a better answer than work starting after
        the budget it was given.
        """
        with self._admission:
            if self._closed:
                raise ConnectionAcquisitionError(_CLOSED, reason="closed")
            if monotonic() >= deadline:
                raise ConnectionAcquisitionError(
                    "database acquisition exceeded its timeout during checkout or provider "
                    "setup, so no modeled statement was run",
                    reason="timeout",
                )


@dataclass(frozen=True, slots=True)
class _PostgresContextSource:
    runtime: PostgresRuntime
    role: PostgresRole | None

    def new_context(self, policy: RoutePolicy, /) -> ConnectionContext:
        return self.runtime._context(self.role, policy)  # pyright: ignore[reportPrivateUsage] - source is runtime-owned


def _shutdown_issue(exc: Exception) -> ReleaseUnconfirmed:
    return ReleaseUnconfirmed(
        (CleanupIssue(phase="return", code="handoff-failed", diagnostic=diagnostic_for(exc)),)
    )
