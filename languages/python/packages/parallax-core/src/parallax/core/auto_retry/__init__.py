"""Each attempt must own rollback and fresh transaction state.

The caller classifies a rolled-back attempt's failure once, with
:func:`retry_eligible`, and hands an eligible one to the loop as a
:class:`RetryCandidate` only after the attempt released its connection and
finished reporting. Failures before begin, incomplete rollbacks, and anything a
later cleanup step raised never become candidates, so they leave the loop on
their first attempt whatever their underlying error is."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Final

from parallax.core._execution._unit_work.effects import OptimisticLockConflictError
from parallax.core._execution._unit_work.uow import RollbackOnlyError
from parallax.core.db_error import DatabaseError

__all__ = ["RetryCandidate", "check_retry_bound", "retry_eligible", "run_with_retry"]

_FLOOR_FIRST_S: Final = 0.008
_FLOOR_LIMIT_S: Final = 0.025
"""The shortest full-jitter window, in seconds: the first attempt's, doubled
per attempt up to the limit. These are the constants contention evidence
selected where attempts take a few milliseconds."""

_SCALE_FIRST: Final = 0.25
_SCALE_LIMIT: Final = 8.0
"""The window a slower failed attempt calls for instead, in multiples of that
attempt's own measured duration: the first attempt's, doubled per attempt up to
the limit. How long a conflicting writer holds its rows depends on round trips
and application work that fixed delays cannot anticipate, and the failed
attempt's duration measures them where it ran. A window that stays shorter than
an attempt lets replays land inside the next conflicting one, while one that
starts long leaves a contended row idle."""

_CEILING_S: Final = 1.0
"""The longest window, in seconds, however long the failed attempt took."""

_rng = random.Random()
_sleep: Callable[[float], None] = time.sleep
_clock: Callable[[], float] = time.monotonic


def check_retry_bound(retries: int, /) -> None:
    """Validate before opening a transaction or an observation scope."""
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")


def retry_eligible(failure: BaseException, /) -> bool:
    """Whether a rolled-back attempt's ``failure`` is a recoverable conflict.

    A transient database failure (the ``deadlock`` category) and an internal
    Optimistic Lock Conflict are recoverable, directly or as the cause of the
    rollback-only refusal a caught one left behind. The verdict ignores the
    remaining budget.
    """
    cause = failure.__cause__ if isinstance(failure, RollbackOnlyError) else failure
    if isinstance(cause, OptimisticLockConflictError):
        return True
    return isinstance(cause, DatabaseError) and cause.is_retriable


class RetryCandidate(Exception):
    """An eligible attempt failure in transit to :func:`run_with_retry`.

    Raised once the failed attempt has rolled back, released its connection,
    and finished reporting, so nothing but the loop ever handles it; the loop
    re-raises :attr:`failure` itself, outside its own handler, so the caller's
    exception and its chain are exactly the original's.
    """

    def __init__(self, failure: Exception) -> None:
        super().__init__(failure)
        self.failure = failure


def run_with_retry[T](attempt: Callable[[], T], *, retries: int) -> T:
    """``retries`` counts re-executions after the first attempt.

    Before each re-execution the loop sleeps a full-jitter delay. Its window
    grows with the attempts already made and is the longer of a fixed window
    and one scaled by how long the failed attempt took, from handing it control
    to receiving its candidate, under an absolute ceiling. Exhaustion re-raises
    the original failure with the attempt count in a note, and sleeps no more.
    """
    check_retry_bound(retries)
    attempts = 0
    while True:
        attempts += 1
        started = _clock()
        try:
            return attempt()
        except RetryCandidate as candidate:
            failure = candidate.failure
        elapsed = _clock() - started
        if attempts > retries:
            failure.add_note(
                f"bounded retry exhausted after {attempts} attempts (retries={retries})"
            )
            raise failure
        _sleep(_delay(attempts, elapsed, _rng))


def _delay(attempt: int, elapsed: float, rng: random.Random) -> float:
    """The wait after ``attempt`` failed having taken ``elapsed`` seconds."""
    return rng.uniform(0.0, _window(attempt, elapsed))


def _window(attempt: int, elapsed: float) -> float:
    # Doubling stops long past either limit, so a large bound never overflows a float.
    doublings = min(attempt - 1, 32)
    floor = min(_FLOOR_LIMIT_S, _FLOOR_FIRST_S * 2**doublings)
    scaled = min(_SCALE_FIRST * 2**doublings, _SCALE_LIMIT) * elapsed
    return min(_CEILING_S, max(floor, scaled))
