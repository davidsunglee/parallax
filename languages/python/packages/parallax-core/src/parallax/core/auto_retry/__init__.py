"""Each attempt must own rollback and fresh transaction state.

The caller classifies a rolled-back attempt's failure once, with
:func:`retry_eligible`, and hands an eligible one to the loop as a
:class:`RetryCandidate` only after the attempt released its connection and
finished reporting. Failures before begin, incomplete rollbacks, and anything a
later cleanup step raised never become candidates, so they leave the loop on
their first attempt whatever their underlying error is."""

from __future__ import annotations

from collections.abc import Callable

from parallax.core._execution._unit_work.effects import OptimisticLockConflictError
from parallax.core._execution._unit_work.uow import RollbackOnlyError
from parallax.core.db_error import DatabaseError

__all__ = ["RetryCandidate", "check_retry_bound", "retry_eligible", "run_with_retry"]


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

    Exhaustion re-raises the original failure with the attempt count in a note.
    """
    check_retry_bound(retries)
    attempts = 0
    while True:
        attempts += 1
        try:
            return attempt()
        except RetryCandidate as candidate:
            failure = candidate.failure
        if attempts > retries:
            failure.add_note(
                f"bounded retry exhausted after {attempts} attempts (retries={retries})"
            )
            raise failure
