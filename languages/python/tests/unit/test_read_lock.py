"""``parallax.core.read_lock`` unit tests (m-read-lock, COR-3 Phase 8 increment 6).

The pure mode -> lock policy scope (:func:`~parallax.core.read_lock.mode_for`):
mode x find-vs-projection is exercised end-to-end by the compile sweep (the
`distinct` suppression lives at the `m-sql` append site, out of this module's
scope by design — see the module docstring); this file pins the policy
function itself in isolation.
"""

from __future__ import annotations

import pytest

from parallax.core import read_lock

pytestmark = pytest.mark.unit


def test_locking_mode_selects_the_shared_lock() -> None:
    assert read_lock.mode_for("locking") == "locking"


def test_optimistic_mode_selects_the_optimistic_lock_mode() -> None:
    # `mode_for` is the mode -> LockMode identity mapping; the "never a lock"
    # half of optimistic mode's own contract is enforced at the `m-sql` APPEND
    # SITE (`sql_gen.compile._append_result_shape`'s own `lock == "locking"`
    # check — this module renders no SQL and owns no append site, see the
    # module docstring), proven end to end by the compile sweep
    # (`m-read-lock-005`).
    assert read_lock.mode_for("optimistic") == "optimistic"


def test_no_participation_mode_selects_no_lock() -> None:
    # A non-transactional `Database.find`, or a scenario whose write steps are
    # all readless predicate writes (`_scenario_needs_lock`'s own suppression):
    # there is no unit-of-work concurrency mode to derive a lock from either
    # way.
    assert read_lock.mode_for(None) is None
