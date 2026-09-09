"""Waiting for an overlap to HAPPEN rather than for time to pass.

What a concurrency pin needs and a timed negative wait cannot give it. That a
contender has not finished within some interval is also true of a contender the
scheduler has not started, so a pin resting on one can pass while the overlap it
exists for never happens — and the implementations these pins condemn behave
correctly for threads that never overlap. Failing to take a claim is the
contender ARRIVING while the first holder still has it, which is that overlap
itself: a pin waits for it rather than for time to pass.
"""

from __future__ import annotations

import threading
from typing import Any, Protocol, cast

__all__ = ["Claim", "ObservedClaim", "observing"]


class Claim(Protocol):
    def acquire(self, blocking: bool = ..., timeout: float = ...) -> bool: ...
    def release(self) -> None: ...


class ObservedClaim:
    """One of an object's own claims, announcing the thread that FINDS IT HELD."""

    def __init__(self, claim: Claim) -> None:
        self._claim = claim
        self.contended = threading.Event()

    def __enter__(self) -> None:
        if not self._claim.acquire(blocking=False):
            self.contended.set()
            self._claim.acquire()

    def __exit__(self, *exc: object) -> None:
        self._claim.release()


def observing(owner: object, claim: str) -> ObservedClaim:
    """Wrap a live object's named claim, leaving the claim itself the same object.

    Installable while a thread already holds it: that holder entered through the
    original lock and leaves through it, so only arrivals after this call are
    observed — which are exactly the contenders a pin is proving something about.
    """
    private = cast("Any", owner)
    observed = ObservedClaim(getattr(private, claim))
    setattr(private, claim, observed)
    return observed
