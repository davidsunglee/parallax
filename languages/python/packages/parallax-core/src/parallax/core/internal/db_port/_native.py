from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from parallax.core.internal.db_port._pool_metrics import PoolMetrics

__all__ = [
    "CheckoutFailed",
    "CheckoutReason",
    "ConnectionPool",
    "DialReason",
    "DialRecord",
]

type DialReason = Literal[
    "unavailable", "authentication_refused", "credentials_refused", "preparation_failed"
]
"""The acquisition reasons establishing a connection can meet."""

type CheckoutReason = Literal["timeout", "queue_rejected", "closed"] | DialReason
"""The acquisition reasons one checkout can end with."""


class DialRecord(Protocol):
    """Where a pool reports what each physical connection attempt met.

    Every attempt reports exactly one outcome, from the thread that made it,
    before a checkout can hand over or refuse because of it: a classified
    failure, or usable once the connection has been initialized. Reporting does
    no I/O, calls nothing on the pool, and waits for nothing the pool holds.
    """

    def report_failure(self, reason: DialReason, cause: BaseException, /) -> None: ...

    def report_usable(self) -> None: ...


class CheckoutFailed(Exception):
    """A checkout that handed over no connection, and why.

    A dial reason describes a dial made and failed by this checkout call
    itself; what other attempts met reaches the runtime through the pool's
    :class:`DialRecord` instead. The native failure is chained as the cause
    where there is one.
    """

    def __init__(self, reason: CheckoutReason) -> None:
        super().__init__(reason)
        self.reason: CheckoutReason = reason


class ConnectionPool[C](Protocol):
    """The physical connections one route keeps for one purpose.

    :meth:`check_out` makes one fair wait within ``budget`` seconds, or raises
    :class:`CheckoutFailed`. A native dial MAY overrun the budget by its own
    timeout granularity; the runtime refuses such a late handover rather than
    running work on it.

    Every connection handed over comes back exactly once: through
    :meth:`check_in` while it remains reusable, or through :meth:`discard`
    once it has already been closed.

    :meth:`metrics` reads the pool's own bookkeeping without I/O and without
    taking a connection, and raises when no reading can be taken.
    :meth:`close` is idempotent.
    """

    def check_out(self, budget: float, /) -> C: ...

    def check_in(self, connection: C, /) -> None: ...

    def discard(self, connection: C, /) -> None: ...

    def metrics(self) -> PoolMetrics: ...

    def close(self) -> None: ...
