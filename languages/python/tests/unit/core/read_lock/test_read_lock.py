"""``parallax.core.read_lock`` unit tests (m-read-lock).

The pure strategy -> lock policy scope
(:func:`~parallax.core.read_lock.mode_for`) is exercised end-to-end by the
compile sweep. This file pins the policy function itself in isolation; which
strategy an Entity participates under is `m-opt-lock`'s own derivation, pinned
in ``test_opt_lock.py``, and the composition of the two is
``test_transaction_reads.py``'s per-level lock coverage.
"""

from __future__ import annotations

from parallax.core import read_lock


def test_the_locking_strategy_selects_the_shared_lock() -> None:
    assert read_lock.mode_for("locking") == "locking"


def test_the_optimistic_strategy_selects_the_optimistic_lock_mode() -> None:
    # `mode_for` is the strategy -> LockMode identity mapping; the "never a
    # lock" half of the Optimistic strategy's own contract is enforced at the
    # `m-sql` APPEND SITE (`sql_gen._compile._append_result_shape`'s own
    # `lock == "locking"` check — this module renders no SQL and owns no append
    # site, see the module docstring), proven end to end by the compile sweep
    # (`m-read-lock-005`).
    assert read_lock.mode_for("optimistic") == "optimistic"


def test_no_participation_selects_no_lock() -> None:
    # A non-transactional `Database.find`: there is no participation to derive
    # an Effective Concurrency Strategy from, so there is no lock to render.
    assert read_lock.mode_for(None) is None
