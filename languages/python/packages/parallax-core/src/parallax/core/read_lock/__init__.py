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
    :meth:`~parallax.snapshot.handle.ScopedDatabase.find`, or an adapter's own
    non-participating verification read) passes through
    unchanged: there is no participation to derive a strategy from either
    way, and ``None`` also never triggers the append site.
    """
    return strategy
