from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, Literal

from parallax.core.internal.db_port import report_route_readiness
from parallax.core.internal.db_port._runtime._route_metrics import PooledRouteMetricsSource

if TYPE_CHECKING:
    from parallax.core.internal.db_port import (
        ConnectionPool,
        PoolPurpose,
        ProbeMismatch,
        Route,
        RouteReadiness,
    )
    from parallax.core.internal.db_port._runtime._dial_record import DialLedger

__all__ = ["PooledRoute"]

type _State = Literal["unproven", "verified", "pending", "refused"]


class PooledRoute[C]:
    """One declared route's pool, the latest failure establishing its
    connections, its metrics source, and whether it has proved it can serve.

    A route starts unproven, while startup proves it. Startup then makes it
    ``verified``, or ``pending`` where the reader was unavailable and its
    proof was deferred. A pending route proves itself on the connections it
    hands over: the first proof that succeeds makes it ``verified``, and the
    first that positively mismatches makes it ``refused`` for good. Those two
    transitions are decided under one lock, so the first one wins and nothing
    afterwards — a concurrent proof that also succeeded included — moves a
    refused route or admits work on it.
    """

    __slots__ = (
        "_lock",
        "_probe_slot",
        "_refusal",
        "_state",
        "dial_ledger",
        "metrics",
        "pool",
        "route",
    )

    def __init__(
        self,
        route: Route,
        pool: ConnectionPool[C],
        dial_ledger: DialLedger,
        purpose: PoolPurpose = "application",
    ) -> None:
        self.route: Route = route
        self.pool = pool
        self.dial_ledger = dial_ledger
        self._state: _State = "unproven"
        self._refusal: ProbeMismatch | None = None
        self._lock = threading.Lock()
        self._probe_slot = threading.Lock()
        self.metrics = PooledRouteMetricsSource(pool, route, self.readiness, purpose)

    def known_unreachable(self) -> bool:
        """Whether this route's latest dial failed as unavailable and it holds
        no idle connection that could serve regardless.

        A retained connection is handed over without dialing, so an idle one
        makes the record irrelevant to the next checkout. A pool whose metrics
        cannot be read is taken to hold none.
        """
        failure = self.dial_ledger.latest_failure
        if failure is None or failure.reason != "unavailable":
            return False
        try:
            available = self.pool.metrics().pool_available
        except Exception:
            return True
        return available <= 0

    def claim_probe(self) -> bool:
        """Take the one slot that lets an acquisition try this route while it is
        known to be unavailable, answering whether this caller now holds it.

        Other preferred acquisitions can move on while the holder tries the
        route. The holder gives the slot back with :meth:`release_probe`
        however its attempt ends.
        """
        return self._probe_slot.acquire(blocking=False)

    def release_probe(self) -> None:
        self._probe_slot.release()

    def readiness(self) -> RouteReadiness:
        """What a sample reports: an unproven route has proved nothing yet."""
        state = self._state
        return "pending" if state == "unproven" else state

    @property
    def awaiting_verification(self) -> bool:
        """Whether a connection this route hands over must prove it first.

        Read under the transition lock, so an answer of no on a refused route
        is always followed by :attr:`refusal` naming it.
        """
        with self._lock:
            return self._state == "pending"

    @property
    def refusal(self) -> ProbeMismatch | None:
        """The mismatch that refused this route, once one has."""
        return self._refusal

    def start_verified(self) -> None:
        self._state = "verified"

    def start_pending(self) -> None:
        self._state = "pending"
        report_route_readiness(self.route, "pending")

    def mark_verified(self) -> ProbeMismatch | None:
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

    def mark_refused(self, mismatch: ProbeMismatch) -> None:
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
        """Attempt to close the pool of a runtime that is never published; an
        ordinary close failure is suppressed, and nothing is reported."""
        self.metrics.detach()
        with contextlib.suppress(Exception):
            self.pool.close()
