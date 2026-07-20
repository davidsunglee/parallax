"""``parallax.core.read_lock`` enforcement scope (m-read-lock).

The pure, query-free read-lock POLICY scope (COR-3 Phase 8 increment 6):
`m-read-lock` is the default (`locking`-mode) correctness strategy — an
in-transaction **object find** that intends to write acquires the dialect's
shared row lock; `optimistic` mode takes no lock, ever (`m-opt-lock` recovers
correctness at write time instead) — the composed result :func:`mode_for`
and `m-sql`'s own append site produce together (see :func:`mode_for`'s own
docstring for exactly which half each owns). Per the dependency graph this
module owns only the MODE -> lock-parameter mapping: it depends on
``m-unit-work`` (whose
:data:`~parallax.core.unit_work.Concurrency` selects the strategy) and
``m-dialect`` (whose :data:`~parallax.core.dialect.LockMode` / ``read_lock_suffix``
render it) — the two DAG edges `modules.md` declares for `m-read-lock`.

This module renders **no SQL** and owns **no append site**: `m-dialect` keeps
:meth:`~parallax.core.dialect.Dialect.read_lock_suffix` (the suffix text) and
``m-sql``/`~parallax.core.sql_gen.compile` keeps the append decision (a
`distinct` projection/aggregation suppresses the suffix and never errors —
`m-sql` *Read-lock suffix*, `m-read-lock.md` "Automatic read-lock
correctness": a projection's result rows have no identifiable base row to
lock, and per ADR 0002 a projection is plain unmanaged data that never enters
the write path). That data-shape-driven suppression stays where the compiled
read's own shape (``distinct``) is visible; :func:`mode_for` is the SEPARATE,
mode-driven half every transactional read consumer re-derives through, rather
than re-deriving the mode -> lock mapping inline at each call site:
:meth:`~parallax.snapshot.handle.Transaction.find`, the materializing
predicate-write resolve in `~parallax.snapshot.handle`, and the conformance
engine's own `~parallax.conformance.engine._lower_find`.

Prior art (Reladomo; semantics, not idioms): the shared read lock mirrors
``FullTransactionalParticipationMode`` (a read enrolls with
``lockInDatabase=true``, applying the dialect's own lock suffix); optimistic
mode mirrors ``ReadCacheWithOptimisticLockingTxParticipationMode`` (no read
locks at all — the version gate recovers correctness at write time,
``docs/research/reladomo/09-transactions-locking.md``).
"""

from __future__ import annotations

from parallax.core.dialect import LockMode
from parallax.core.unit_work import Concurrency

__all__ = ["mode_for"]


def mode_for(concurrency: Concurrency | None) -> LockMode | None:
    """The read-lock policy: the ``m-dialect`` :data:`LockMode` an
    in-transaction object find's compiled read carries, derived from the
    owning unit of work's participation mode (`m-read-lock` "Automatic
    read-lock correctness"; `m-opt-lock.md` L16-20).

    ``Concurrency`` and ``LockMode`` are the SAME closed vocabulary
    (``Literal["locking", "optimistic"]``), declared independently by
    ``m-unit-work`` and ``m-dialect`` per the dependency graph, so this
    mapping is the identity function — but it is the single seam that
    legally names BOTH vocabularies and states that coincidence as POLICY,
    rather than three call sites each silently assuming it holds.
    ``locking`` carries through to `m-sql`'s append site
    (`~parallax.core.sql_gen.compile._append_result_shape`), which appends
    the dialect's shared-row-lock suffix; ``optimistic`` carries through
    unchanged too, but the SAME append site never triggers for it (only
    ``"locking"`` does) — the "optimistic mode takes no lock, ever" half of
    the policy is therefore enforced at the append site's own mode check,
    not by this function returning ``None`` for it (`m-read-lock-005`'s own
    compile-sweep witness proves the composed result). ``None`` (no owning
    unit of work — a non-transactional
    :meth:`~parallax.snapshot.handle.Database.find`, or a scenario whose
    write steps are all READLESS predicate writes and so license no lock at
    all, `~parallax.conformance.engine._scenario_needs_lock`) passes through
    unchanged: there is no participation mode to derive a lock from either
    way, and ``None`` also never triggers the append site.
    """
    return concurrency
