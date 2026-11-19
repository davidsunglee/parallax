from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from parallax.core.internal.db_port import (
    PoolAvailable,
    PoolDetached,
    PoolMetrics,
    PoolPurpose,
    PoolSample,
    PoolUnavailable,
    Route,
    RouteReadiness,
)
from parallax.core.internal.diagnostics import diagnostic_for

__all__ = ["PostgresPoolMetrics"]


class MeasuredPool(Protocol):
    """The one thing a source asks of the pool it reads."""

    def metrics(self) -> PoolMetrics: ...


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

    __slots__ = ("_pool", "_purpose", "_readiness", "_route")

    def __init__(
        self,
        pool: MeasuredPool,
        route: Route,
        readiness: Callable[[], RouteReadiness],
        purpose: PoolPurpose = "application",
    ) -> None:
        self._pool: MeasuredPool | None = pool
        self._route: Route = route
        self._readiness = readiness
        self._purpose: PoolPurpose = purpose

    @property
    def route(self) -> Route:
        return self._route

    @property
    def purpose(self) -> PoolPurpose:
        return self._purpose

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
            metrics = pool.metrics()
        except Exception as exc:
            return PoolUnavailable(diagnostic_for(exc))
        return PoolAvailable(metrics, self._readiness())
