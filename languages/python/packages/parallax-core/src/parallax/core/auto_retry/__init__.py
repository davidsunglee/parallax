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
from collections.abc import Callable, Collection
from dataclasses import dataclass
from math import frexp, isfinite, ldexp
from typing import Final

from parallax.core._execution._unit_work.effects import OptimisticLockConflictError
from parallax.core._execution._unit_work.uow import RollbackOnlyError
from parallax.core.db_error import DatabaseError
from parallax.core.temporal_write import TemporalConflictError

__all__ = [
    "AdaptiveBackoff",
    "RetryCandidate",
    "RetryPolicy",
    "RetryTiming",
    "retry_eligible",
    "retry_policy",
    "run_with_retry",
]

_DURATION_SCALE_START: Final = 0.25
_DURATION_SCALE_LIMIT: Final = 8.0
"""The window a slower failed attempt calls for, in multiples of that attempt's
own measured duration: the first attempt's, doubled per attempt up to the limit.
How long a conflicting writer holds its rows depends on round trips and
application work that fixed delays cannot anticipate, and the failed attempt's
duration measures them where it ran. A window that stays shorter than an attempt
lets replays land inside the next conflicting one, while one that starts long
leaves a contended row idle."""

_RANDOM: Final = random.Random()


def _full_jitter(window: float) -> float:
    return _RANDOM.uniform(0.0, window)


def _doubled(value: float, doublings: int, *, limit: float) -> float:
    """``value`` doubled ``doublings`` times, saturating at ``limit``.

    Comparing binary exponents first keeps the cost constant and every
    intermediate finite for any attempt ordinal, across every positive finite
    ``value`` and ``limit``.
    """
    if frexp(value)[1] + doublings > frexp(limit)[1]:
        return limit
    return min(limit, ldexp(value, doublings))


def _positive_seconds(field: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a finite positive number of seconds, got {value!r}")
    try:
        seconds = float(value)
    except OverflowError:
        raise ValueError(f"{field} must be a finite number of seconds, got {value!r}") from None
    if not isfinite(seconds) or seconds <= 0.0:
        raise ValueError(f"{field} must be a finite positive number of seconds, got {value!r}")
    return seconds


@dataclass(frozen=True, slots=True, kw_only=True)
class AdaptiveBackoff:
    """The two timing inputs of the wait before each re-execution, in seconds.

    ``base_delay`` is the first window, doubled per attempt, and ``max_delay``
    is the longest window however long the failed attempt took. Each only
    bounds a full-jitter draw from above, which may land anywhere down to zero.
    Either may be an ``int`` and is held as a ``float``; an invalid value, a
    ``base_delay`` above ``max_delay`` included, raises ``ValueError``.
    """

    base_delay: float = 0.008
    max_delay: float = 1.0

    def __post_init__(self) -> None:
        base_delay = _positive_seconds("base_delay", self.base_delay)
        max_delay = _positive_seconds("max_delay", self.max_delay)
        if base_delay > max_delay:
            raise ValueError(f"base_delay {base_delay} must not exceed max_delay {max_delay}")
        object.__setattr__(self, "base_delay", base_delay)
        object.__setattr__(self, "max_delay", max_delay)

    def _window(self, failed_attempt: int, duration: float) -> float:
        doublings = failed_attempt - 1
        fixed = _doubled(self.base_delay, doublings, limit=self.max_delay)
        scale = _doubled(_DURATION_SCALE_START, doublings, limit=_DURATION_SCALE_LIMIT)
        return min(self.max_delay, max(fixed, scale * duration))


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryPolicy:
    """The complete retry configuration of an invocation.

    ``max_retries`` bounds re-executions rather than attempts: ``0`` runs the
    callback once and ``N`` admits at most ``N + 1`` attempts. It is an exact
    built-in ``int``. A policy is one value: naming one replaces an inherited
    policy whole, and its omitted fields take these built-in values rather than
    the inherited ones. An invalid value raises ``ValueError``.
    """

    max_retries: int = 10
    backoff: AdaptiveBackoff = AdaptiveBackoff()

    def __post_init__(self) -> None:
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError(f"max_retries must be a nonnegative int, got {self.max_retries!r}")
        _check_backoff(self.backoff)


def _check_backoff(value: object) -> None:
    if not isinstance(value, AdaptiveBackoff):
        raise ValueError(f"backoff must be an AdaptiveBackoff, got {value!r}")


def retry_policy(value: object) -> RetryPolicy:
    """``value`` as a retry policy, or ``ValueError``."""
    if not isinstance(value, RetryPolicy):
        raise ValueError(f"retry must be a RetryPolicy, got {value!r}")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryTiming:
    """What the loop measures, waits, and draws with; the framework's own
    seam, never an application option.

    ``monotonic`` reads seconds, and is unrelated to the transaction-time
    clock. ``jitter`` answers a wait from ``[0, window]``.
    """

    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    jitter: Callable[[float], float] = _full_jitter


_SYSTEM_TIMING: Final = RetryTiming()


def retry_eligible(
    failure: BaseException, /, *, recognized: Collection[BaseException] = ()
) -> bool:
    """Whether a rolled-back attempt's ``failure`` is a recoverable conflict.

    A transient database failure (the ``deadlock`` category), an internal
    Optimistic Lock Conflict, a Temporal Conflict, and a failure among the
    ``recognized`` conflicts its attempt's execution attributed to a statement
    are recoverable, directly or as the cause of the rollback-only refusal a
    caught one left behind. The verdict ignores the remaining budget.
    """
    cause = failure.__cause__ if isinstance(failure, RollbackOnlyError) else failure
    if isinstance(cause, OptimisticLockConflictError | TemporalConflictError):
        return True
    if any(cause is conflict for conflict in recognized):
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


def run_with_retry[T](
    attempt: Callable[[], T], *, policy: RetryPolicy, timing: RetryTiming = _SYSTEM_TIMING
) -> T:
    """Run ``attempt``, re-executing eligible candidates up to the policy's bound.

    Before each re-execution the loop sleeps a full-jitter delay. Its window is
    the longer of the doubling base delay and a doubling multiple of how long
    the failed attempt took, from handing it control to receiving its candidate,
    under the policy's maximum delay. Exhaustion re-raises the original failure
    with the attempt count in a note, and sleeps no more.
    """
    attempts = 0
    while True:
        attempts += 1
        started = timing.monotonic()
        try:
            return attempt()
        except RetryCandidate as candidate:
            failure = candidate.failure
        duration = timing.monotonic() - started
        if attempts > policy.max_retries:
            failure.add_note(
                f"bounded retry exhausted after {attempts} attempts "
                f"(max_retries={policy.max_retries})"
            )
            raise failure
        window = policy.backoff._window(attempts, duration)  # pyright: ignore[reportPrivateUsage] - the loop shares the backoff's module
        timing.sleep(timing.jitter(window))
