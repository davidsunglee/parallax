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
rolls the database back on any failure and reports whether the rollback
completed) around a **fresh** unit of work (a new
buffer, new observations, a re-read Clock), so a re-execution re-reads current
state rather than replaying a stale shadow. No cached state currently exists
to invalidate; an identity map, if one is added, must hook its invalidation
into this path.

The loop classifies the exception an attempt raises, so an outcome that must not
be re-executed however its error classifies — a transaction that never began, a
rollback that did not complete — is kept out of the loop by the caller rather
than made a second policy here.

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

from parallax.core.db_error import DatabaseError
from parallax.core.unit_work import OptimisticLockConflictError, RollbackOnlyError

__all__ = ["check_retry_bound", "retriable_failure", "run_with_retry"]


def check_retry_bound(retries: int, /) -> None:
    """Refuse a re-execution bound this loop cannot run.

    Published because the refusal must be reachable BEFORE the loop is entered:
    a demarcation layer resolves the caller's own bound while its deterministic
    refusals are still running, and a bound rejected only on entry would be
    rejected from inside every scope opened around the loop. Both callers reach
    the one verdict rather than two spellings of it.
    """
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")


def retriable_failure(exc: BaseException, /) -> bool:
    """Whether ``exc``'s retriability-bearing core is a retriable database error.

    Two raise shapes carry one: the failure itself (a ``deadlock``-category
    :class:`DatabaseError`), and the rollback-only commit refusal whose
    ``__cause__`` preserves the original failure's classification (spec §5 —
    the outer callback may have caught the original, but the retry loop still
    applies per its category).

    Published because the verdict outlives the decision it drives: an observer
    reports whether an attempt's failure was retry-eligible *under the effective
    policy* independently of the budget that remained, and this loop reaches its
    own verdict after the attempt it belongs to has already ended. One function
    answering both is what keeps the reported verdict and the taken decision from
    classifying by different rules, each calling it where it needs the answer.
    It states this module's own half alone: a caller's
    ``extra_retriable`` extension composes with it as an OR, exactly as
    :func:`run_with_retry` does below.
    """
    if isinstance(exc, RollbackOnlyError):
        return isinstance(exc.__cause__, DatabaseError) and exc.__cause__.is_retriable
    return isinstance(exc, DatabaseError) and exc.is_retriable


def run_with_retry[T](
    attempt: Callable[[], T],
    *,
    retries: int,
    extra_retriable: Callable[[BaseException], bool] | None = None,
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
    module's own :func:`retriable_failure` calls non-retriable, so the two
    predicates compose as an OR, never override one another (a transient
    database failure's retriability is decided here, unconditionally on the
    injected extension). It must decide from the exception alone: an observer
    reporting an attempt's retry eligibility asks the same extension at a
    different point in that failure's life, and only an answer that varies can
    make the two differ.
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
