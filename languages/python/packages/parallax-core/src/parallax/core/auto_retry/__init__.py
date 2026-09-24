"""Each attempt must own rollback and fresh transaction state.

The caller must keep failures before begin and incomplete rollbacks outside this
loop, even when their underlying error would otherwise qualify for retry."""

from __future__ import annotations

from collections.abc import Callable

from parallax.core.db_error import DatabaseError
from parallax.core.unit_work import OptimisticLockConflictError, RollbackOnlyError

__all__ = ["retriable_failure", "run_with_retry"]


def check_retry_bound(retries: int, /) -> None:
    """Validate before opening a transaction or an observation scope."""
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")


def retriable_failure(exc: BaseException, /) -> bool:
    """Classify without considering the remaining budget or caller extensions."""
    if isinstance(exc, RollbackOnlyError):
        return isinstance(exc.__cause__, DatabaseError) and exc.__cause__.is_retriable
    return isinstance(exc, DatabaseError) and exc.is_retriable


def run_with_retry[T](
    attempt: Callable[[], T],
    *,
    retries: int,
    extra_retriable: Callable[[BaseException], bool] | None = None,
) -> T:
    """``retries`` counts re-executions after the first attempt.

    Exhaustion re-raises the original failure with the attempt count in a note.
    ``extra_retriable`` adds eligibility; it cannot veto the built-in policy.
    It must depend only on the exception, because lifecycle observation consults
    it separately from this loop.
    """
    check_retry_bound(retries)
    exception_types: tuple[type[BaseException], ...] = (
        DatabaseError,
        RollbackOnlyError,
        OptimisticLockConflictError,
    )
    attempts = 0
    while True:
        attempts += 1
        try:
            return attempt()
        except exception_types as exc:
            retriable = retriable_failure(exc) or (
                extra_retriable is not None and extra_retriable(exc)
            )
            if not retriable:
                raise
            if attempts > retries:
                exc.add_note(
                    f"bounded retry exhausted after {attempts} attempts (retries={retries})"
                )
                raise
