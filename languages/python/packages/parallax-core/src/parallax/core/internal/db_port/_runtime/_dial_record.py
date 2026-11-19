from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parallax.core.internal.db_port._native import DialReason

__all__ = ["DialFailure", "DialLedger"]


@dataclass(frozen=True, slots=True)
class DialFailure:
    reason: DialReason
    cause: BaseException


class DialLedger:
    """The latest failure one pool met establishing a connection, until a
    connection becomes usable.

    A pool creates most of its connections on its own background path: a
    failure there is retried and logged where a caller waiting for a connection
    never sees it, and what that caller eventually gets is a bare timeout. The
    ledger lets an expired checkout report the latest dial failure even when
    the pool made no attempt during that wait.

    One ledger serves every attempt on the pool, because a pool dials several
    at once and the caller it answers is waiting on the pool rather than on any
    one of them. The most recent failure wins, so a caller is told the last
    thing establishment actually met. Only a connection that became USABLE —
    one initialized, or one the pool handed over — clears it: a resolved
    credential or a completed dial may still fail to dial or to initialize, and
    clearing there would let one attempt's partial progress erase another's
    completed failure.

    Writes are serialized; a read is one load of an immutable value.
    """

    __slots__ = ("_latest", "_lock")

    def __init__(self) -> None:
        self._latest: DialFailure | None = None
        self._lock = threading.Lock()

    @property
    def latest_failure(self) -> DialFailure | None:
        return self._latest

    def report_failure(self, reason: DialReason, cause: BaseException, /) -> None:
        failure = DialFailure(reason, cause)
        with self._lock:
            self._latest = failure

    def report_usable(self) -> None:
        with self._lock:
            self._latest = None

    def clear_on_handover(self) -> None:
        """Record that the pool handed over a connection, which ends whatever
        failure was on record, even where that connection was retained long
        before the failure was."""
        if self._latest is not None:
            self.report_usable()
