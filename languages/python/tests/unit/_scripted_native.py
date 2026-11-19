"""Scripted adapters at the DB-port's native seams, for the lifecycle policy suites.

What a real pool will not produce on demand — a checkout that fails for a chosen
reason, a hand-back or close that raises, a reading that cannot be taken, a dial
failure reported while a caller waits — is scripted here in the seam's own terms,
so a policy test enters where an adapter enters rather than through a driver.
"""

from __future__ import annotations

from collections.abc import Callable

from parallax.core.internal.db_port import (
    CheckoutFailed,
    CheckoutReason,
    DialRecord,
    PoolMetrics,
)

__all__ = ["ScriptedPool", "checkout_failed"]


def checkout_failed(reason: CheckoutReason, cause: BaseException | None = None) -> CheckoutFailed:
    """The failure a pool's checkout raises for ``reason``, chained to ``cause``."""
    failed = CheckoutFailed(reason)
    failed.__cause__ = cause
    return failed


class ScriptedPool[C]:
    """A connection pool handing over its connections in turn, then the last again.

    ``checkout_failure``, ``hand_back_failure``, ``close_failure`` and
    ``metrics_failure`` are read at call time, so a test can change one between
    calls. ``on_check_out`` runs with the budget at the start of every checkout,
    before its outcome is decided: where a dial failure is reported to
    :attr:`dial_record` while a caller waits, or the clock moves during the wait.

    Every budget asked for, every connection handed back and by which method,
    and every close are recorded.
    """

    def __init__(
        self,
        *connections: C,
        checkout_failure: BaseException | None = None,
        hand_back_failure: Exception | None = None,
        close_failure: BaseException | None = None,
        metrics_failure: BaseException | None = None,
    ) -> None:
        self._connections = list(connections)
        self.checkout_failure = checkout_failure
        self.hand_back_failure = hand_back_failure
        self.close_failure = close_failure
        self.metrics_failure = metrics_failure
        self.on_check_out: Callable[[float], None] | None = None
        self.dial_record: DialRecord | None = None
        self.available = 0
        self.budgets: list[float] = []
        self.check_ins: list[C] = []
        self.discards: list[C] = []
        self.returned: list[C] = []
        self.hand_backs = 0
        self.closes = 0

    def check_out(self, budget: float, /) -> C:
        self.budgets.append(budget)
        if self.on_check_out is not None:
            self.on_check_out(budget)
        if self.checkout_failure is not None:
            raise self.checkout_failure
        return self._connections[min(len(self.budgets), len(self._connections)) - 1]

    def check_in(self, connection: C, /) -> None:
        self._hand_back(connection)
        self.check_ins.append(connection)

    def discard(self, connection: C, /) -> None:
        self._hand_back(connection)
        self.discards.append(connection)

    def _hand_back(self, connection: C) -> None:
        self.hand_backs += 1
        if self.hand_back_failure is not None:
            raise self.hand_back_failure
        self.returned.append(connection)

    def metrics(self) -> PoolMetrics:
        if self.metrics_failure is not None:
            raise self.metrics_failure
        return PoolMetrics(
            pool_min=0,
            pool_max=10,
            pool_size=len(self._connections),
            pool_available=self.available,
            requests_waiting=0,
        )

    def close(self) -> None:
        self.closes += 1
        if self.close_failure is not None:
            raise self.close_failure
