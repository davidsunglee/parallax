"""``parallax.core.auto_retry`` enforcement scope (m-auto-retry).

The unit-of-work boundary's **bounded automatic retry** loop. The demarcation
layer (``db.transact``, `parallax.snapshot.handle`) wraps each transaction
attempt in :func:`run_with_retry`; this module owns the loop *policy* — which
failures are retriable, the re-execution bound, and the diagnosable
exhaustion — per its two DAG edges:

- ``m-db-error`` supplies the retriability predicate: the ``deadlock`` category
  (a true deadlock or a serialization failure) is retriable by default;
  ``lockWaitTimeout`` and every other category are not.
- ``m-unit-work`` supplies :class:`RollbackOnlyError`, whose **cause** must keep
  its retriability classification: an inner failure that dooms the transaction
  surfaces at commit as ``RollbackOnlyError from <original>`` even when the
  outer callback caught it, and the retry loop still applies per the original
  failure's category (spec §5).

The m-auto-retry rollback / fresh-state steps are the caller's obligations, met
by construction: each ``attempt`` runs ``port.transaction(...)`` (the adapter
rolls the database back on any raise) around a **fresh** unit of work (a new
buffer, new observations, a re-read Clock), so a re-execution re-reads current
state rather than replaying a stale shadow. No cached state currently exists
to invalidate; an identity map, if one is added, must hook its invalidation
into this path.

**Optimistic-lock conflicts**:
:class:`~parallax.core.unit_work.OptimisticLockConflictError` is a Write Effect
Error the affected-row enforcer raises, not a
:class:`~parallax.core.db_error.DatabaseError` — a gate mismatch is a
STRUCTURALLY different signal from a transient database failure, never forced
into that hierarchy just to reuse one predicate. The Write Effect Error family
is owned by ``m-unit-work``, which this module already depends on, so the
canonical conflict is named DIRECTLY here rather than injected by a composition
root whose only purpose would be carrying a type across a module boundary.
Recognizing it is not the same as retrying it: a conflict is caught
so the caller's ``extra_retriable`` opt-in can be consulted, and stays
non-retriable when that opt-in is absent.

The remaining Write Effect Errors — Missing Target, Stale Write, and Cardinality
Corruption — are **never** retriable under any option, so this module never
names them and they propagate untouched. The opt-in
(``retry_optimistic_conflicts``) gates only the EXTENSION's verdict; this
module's transient-failure branch never consults it, so a deadlock or
serialization failure stays retriable regardless of the flag.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from parallax.core.db_error import DatabaseError
from parallax.core.unit_work import OptimisticLockConflictError, RollbackOnlyError

__all__ = ["AttemptObserver", "run_with_retry"]


class AttemptObserver(Protocol):
    """Where :func:`run_with_retry` publishes the loop's own two facts.

    Declared here rather than by the observer, because the retry loop is the one
    participant that knows them: that an attempt is about to run, and — on a
    failure — the classifier's verdict under the effective policy. That verdict
    is a CLASSIFICATION, not a history: it is reported the same way whether or
    not the remaining bound allows another attempt, so an exhausted retriable
    failure stays distinguishable from one the classifier refused.

    The loop never reads an observer back, so an observer that raises breaks the
    transaction it is observing; implementations record and return.
    """

    def attempt_opened(self) -> None:
        """One attempt is about to run."""
        ...

    def attempt_failed(self, exc: BaseException, *, retry_eligible: bool) -> None:
        """The running attempt raised ``exc``, which the classifier admits into
        the retriable set (``retry_eligible``) or does not."""
        ...


def _retriable_failure(exc: BaseException) -> bool:
    """Whether ``exc``'s retriability-bearing core is a retriable database error.

    Two raise shapes carry one: the failure itself (a ``deadlock``-category
    :class:`DatabaseError`), and the rollback-only commit refusal whose
    ``__cause__`` preserves the original failure's classification (spec §5 —
    the outer callback may have caught the original, but the retry loop still
    applies per its category).
    """
    if isinstance(exc, RollbackOnlyError):
        return isinstance(exc.__cause__, DatabaseError) and exc.__cause__.is_retriable
    return isinstance(exc, DatabaseError) and exc.is_retriable


def run_with_retry[T](
    attempt: Callable[[], T],
    *,
    retries: int,
    extra_retriable: Callable[[BaseException], bool] | None = None,
    on_attempt: AttemptObserver | None = None,
) -> T:
    """Run ``attempt`` under the m-auto-retry bounded re-execution loop.

    ``retries`` bounds **re-executions** (not total attempts): the default the
    demarcation layer resolves is 10, and ``0`` disables the loop entirely, so
    even a retriable failure surfaces after the first attempt. On a retriable
    failure with re-executions left the closure runs again — against fresh
    state, per the caller obligations documented on the module. A failure that
    is not retriable re-raises immediately; a retriable failure that exhausts
    the bound re-raises with the attempt count attached as an exception note,
    so the surfaced error is still the failure itself (same type, same
    category) and carries its retry history diagnosably.

    ``extra_retriable`` is consulted ONLY for an exception this
    module's own :func:`_retriable_failure` calls non-retriable, so the two
    predicates compose as an OR, never override one another (a transient
    database failure's retriability is decided here, unconditionally on the
    injected extension).

    ``on_attempt`` observes the loop without participating in it: it is told
    that an attempt is opening, and told the classifier's verdict on a failure
    the loop catches. A failure OUTSIDE the caught set never reaches the
    observer, which is the honest report — the classifier was never consulted,
    so the verdict is the absence of one rather than a false negative.
    """
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")
    exception_types: tuple[type[BaseException], ...] = (
        DatabaseError,
        RollbackOnlyError,
        OptimisticLockConflictError,
    )
    attempts = 0
    while True:
        attempts += 1
        if on_attempt is not None:
            on_attempt.attempt_opened()
        try:
            return attempt()
        except exception_types as exc:
            retriable = _retriable_failure(exc) or (
                extra_retriable is not None and extra_retriable(exc)
            )
            if on_attempt is not None:
                on_attempt.attempt_failed(exc, retry_eligible=retriable)
            if not retriable:
                raise
            if attempts > retries:
                exc.add_note(
                    f"bounded retry exhausted after {attempts} attempts (retries={retries})"
                )
                raise
