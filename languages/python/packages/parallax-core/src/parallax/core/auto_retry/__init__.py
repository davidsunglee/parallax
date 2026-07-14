"""``parallax.core.auto_retry`` enforcement scope (m-auto-retry).

The unit-of-work boundary's **bounded automatic retry** loop. The demarcation
layer (``db.transact``, `parallax.snapshot.handle`) wraps each transaction
attempt in :func:`run_with_retry`; this module owns only the loop *policy* —
which failures are retriable, the re-execution bound, and the diagnosable
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
state rather than replaying a stale shadow. No cached state exists to
invalidate in this slice (the identity map lands with a later phase and must
hook its invalidation here when it does).

Optimistic-lock conflicts are **not** classifiable yet: no optimistic-conflict
error category exists until ``m-opt-lock`` (COR-3 Phase 8). ``db.transact``
accepts and stores ``retry_optimistic_conflicts`` for the join/conflict
contract, but the predicate here deliberately has no parameter for it — the
opt-in joins the retriable set when the conflict type exists to classify.
"""

from __future__ import annotations

from collections.abc import Callable

from parallax.core.db_error import DatabaseError
from parallax.core.unit_work import RollbackOnlyError

__all__ = ["run_with_retry"]


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


def run_with_retry[T](attempt: Callable[[], T], *, retries: int) -> T:
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
    """
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")
    attempts = 0
    while True:
        attempts += 1
        try:
            return attempt()
        except (DatabaseError, RollbackOnlyError) as exc:
            if not _retriable_failure(exc):
                raise
            if attempts > retries:
                exc.add_note(
                    f"bounded retry exhausted after {attempts} attempts (retries={retries})"
                )
                raise
