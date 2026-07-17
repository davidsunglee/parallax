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
state rather than replaying a stale shadow. No cached state exists to
invalidate in this slice (the identity map lands with a later phase and must
hook its invalidation here when it does).

**Optimistic-lock conflicts** (`m-opt-lock`, COR-3 Phase 8 increment 6):
``OptimisticLockConflictError`` (`parallax.core.opt_lock`) is a plain
``RuntimeError``, not a :class:`~parallax.core.db_error.DatabaseError` — the
``updatedRows != 1`` gate mismatch is a STRUCTURALLY different signal from a
transient database failure, never forced into that hierarchy just to reuse
one predicate (`m-opt-lock` "Conflict detection"). This module's own DAG edges
name ``m-db-error`` and ``m-unit-work`` only — never ``m-opt-lock`` (the
import-linter contract forbids the edge) — so :func:`run_with_retry` cannot
name that type directly; it instead accepts an OPTIONAL, injected retriability
extension (``extra_retriable_types`` / ``extra_retriable``) the demarcation
layer supplies (`parallax.snapshot.handle.Database.transact`, which legally
imports both this module and ``opt_lock``): a SECOND classification branch
composed alongside :func:`_retriable_failure`, never an inheritance change to
:class:`~parallax.core.opt_lock.OptimisticLockConflictError` itself. The
opt-in (``retry_optimistic_conflicts``) gates the EXTENSION's own verdict —
this module's transient-failure branch never consults it, so a deadlock or
serialization failure stays retriable regardless of the flag
(`m-auto-retry.md` "Which failures are retriable").
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


def run_with_retry[T](
    attempt: Callable[[], T],
    *,
    retries: int,
    extra_retriable_types: tuple[type[BaseException], ...] = (),
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

    ``extra_retriable_types`` widens the caught set beyond this module's own
    :class:`DatabaseError` / :class:`RollbackOnlyError` (e.g. the demarcation
    layer's own :class:`~parallax.core.opt_lock.OptimisticLockConflictError`,
    a plain ``RuntimeError`` this module may not import — see the module
    docstring); ``extra_retriable`` is consulted ONLY for an exception this
    module's own :func:`_retriable_failure` calls non-retriable, so the two
    predicates compose as an OR, never override one another (a transient
    database failure's retriability is decided here, unconditionally on the
    injected extension).
    """
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")
    exception_types: tuple[type[BaseException], ...] = (
        DatabaseError,
        RollbackOnlyError,
        *extra_retriable_types,
    )
    attempts = 0
    while True:
        attempts += 1
        try:
            return attempt()
        except exception_types as exc:
            retriable = _retriable_failure(exc) or (
                extra_retriable is not None and extra_retriable(exc)
            )
            if not retriable:
                raise
            if attempts > retries:
                exc.add_note(
                    f"bounded retry exhausted after {attempts} attempts (retries={retries})"
                )
                raise
