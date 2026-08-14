"""``parallax.core.read_lock`` enforcement scope (m-read-lock).

The pure, query-free read-lock POLICY scope:
`m-read-lock` is the **Locking Effective Concurrency Strategy** — an
in-transaction **object find** that intends to write acquires the dialect's
shared row lock; the same object find under the Optimistic strategy omits that lock
(`m-opt-lock` recovers correctness at write time instead) — the composed result :func:`mode_for`
and `m-sql`'s own append site produce together (see :func:`mode_for`'s own
docstring for exactly which half each owns). Per the dependency graph this
module owns only the STRATEGY -> lock-parameter mapping: it depends on
``m-unit-work`` (whose
:data:`~parallax.core.unit_work.Concurrency` spells the strategy) and
``m-dialect`` (whose :data:`~parallax.core.dialect.LockMode` / ``read_lock_suffix``
render it) — the two DAG edges `modules.md` declares for `m-read-lock`. Which
strategy an Entity participates under is `m-opt-lock`'s derivation
(:func:`~parallax.core.opt_lock.effective_strategy`), one DAG level above this
scope; nothing here reads a Concurrency Preference.

This module renders **no SQL** and owns **no append site**: `m-dialect` keeps
:meth:`~parallax.core.dialect.Dialect.read_lock_suffix` (the suffix text) and
``m-sql``/`~parallax.core.sql_gen` keeps the append decision. :func:`mode_for`
is the SEPARATE, strategy-driven half every supported object-find consumer
re-derives through, rather
than re-deriving the strategy -> lock mapping inline at each call site:
:meth:`~parallax.snapshot.handle.Transaction.find`, the materializing
predicate-write resolve in `~parallax.snapshot.handle`, and the conformance
engine's own `~parallax.conformance.engine._compile_find`.

Prior art (Reladomo; semantics, not idioms): the shared read lock mirrors
``FullTransactionalParticipationMode`` (a read enrolls with
``lockInDatabase=true``, applying the dialect's own lock suffix); optimistic
mode mirrors ``ReadCacheWithOptimisticLockingTxParticipationMode`` (no read
locks on its object reads — the version gate recovers correctness at write time,
``docs/research/reladomo/09-transactions-locking.md``).
"""

from __future__ import annotations

from parallax.core.dialect import LockMode
from parallax.core.unit_work import Concurrency

__all__ = ["mode_for"]


def mode_for(strategy: Concurrency | None) -> LockMode | None:
    """The read-lock policy: the ``m-dialect`` :data:`LockMode` an
    in-transaction object find's compiled read carries, given the Effective
    Concurrency Strategy of the Entity that read materializes (`m-read-lock`
    "Automatic read-lock correctness"; `m-opt-lock.md` L16-20).

    The argument is the ALREADY-DERIVED strategy, never a raw Concurrency
    Preference: an unversioned Non-Temporal Entity read under the `optimistic`
    preference resolves to Locking and locks here, and one deep-fetch level of a
    transaction may therefore lock while the next does not.

    ``Concurrency`` and ``LockMode`` are the SAME closed vocabulary
    (``Literal["locking", "optimistic"]``), declared independently by
    ``m-unit-work`` and ``m-dialect`` per the dependency graph, so this
    mapping is the identity function — but it is the single seam that
    legally names BOTH vocabularies and states that coincidence as POLICY,
    rather than three call sites each silently assuming it holds.
    ``locking`` carries through to `m-sql`'s append site
    (`~parallax.core.sql_gen._compile._append_result_shape`), which appends
    the dialect's shared-row-lock suffix; ``optimistic`` carries through
    unchanged too, but the SAME append site never triggers for it (only
    ``"locking"`` does) — the "an Optimistic object find omits the shared lock"
    half of the policy is therefore enforced at the append site's own check,
    not by this function returning ``None`` for it (`m-read-lock-005`'s own
    compile-sweep witness proves the composed result). ``None`` (no owning
    unit of work — a non-transactional
    :meth:`~parallax.snapshot.handle.Database.find`, or an adapter's own
    non-participating verification read) passes through
    unchanged: there is no participation to derive a strategy from either
    way, and ``None`` also never triggers the append site.
    """
    return strategy
