"""The pool metrics source the internal-behavior suites drive a scripted runtime with."""

from __future__ import annotations

from parallax.core.internal.db_port import (
    PoolAvailable,
    PoolDetached,
    PoolMeasurements,
    PoolSample,
    Route,
    RouteReadiness,
)

__all__ = ["DetachableSource"]


class DetachableSource:
    """A pool source over one fixed reading, detached by its runtime's close.

    A script says nothing about a pool, so what a sample answers here is a
    constant. What is NOT constant is the thing worth doubling: a source is
    stable for its runtime's life and stops answering when that runtime closes,
    so a suite watching a pool across a handle's whole life can do it without a
    driver.
    """

    def __init__(
        self,
        measurements: PoolMeasurements | None = None,
        *,
        route: Route = "writer",
        readiness: RouteReadiness = "verified",
    ) -> None:
        self.route: Route = route
        self.readiness: RouteReadiness = readiness
        self.measurements = (
            measurements
            if measurements is not None
            else PoolMeasurements(
                pool_min=1, pool_max=2, pool_size=1, pool_available=1, requests_waiting=0
            )
        )
        self.attached = True
        self.samples = 0

    def sample(self) -> PoolSample:
        self.samples += 1
        return PoolAvailable(self.measurements, self.readiness) if self.attached else PoolDetached()

    def detach(self) -> None:
        self.attached = False
