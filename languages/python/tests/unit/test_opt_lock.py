"""``parallax.core.opt_lock`` unit tests (m-opt-lock, COR-3 Phase 8 increment 3).

Direct, isolated pins for the pure policy scope ``parallax.snapshot.handle``'s
write-lowering seam consumes: the observed-version requirement
(:func:`require_observed`), the runtime-computed advance (:func:`advance`), the
optimistic-only gate decision (:func:`gates`), the historical-observation
licensing check (:func:`check_locking_license`) and its error class, the
derived initial version, and the conflict error's own carried context. The
corpus-level composition (the gate/advance/conflict wired through real DML) is
pinned in ``test_write_lowering.py``; this file is the policy scope's own,
narrower unit boundary.
"""

from __future__ import annotations

import pytest

from parallax.core import opt_lock
from parallax.core.unit_work import Observation

pytestmark = pytest.mark.unit


def test_initial_version_is_one() -> None:
    assert opt_lock.INITIAL_VERSION == 1


def test_advance_is_runtime_computed_from_the_observed_value() -> None:
    assert opt_lock.advance(3) == 4
    assert opt_lock.advance(0) == 1


def test_gates_only_in_optimistic_mode() -> None:
    assert opt_lock.gates("optimistic") is True
    assert opt_lock.gates("locking") is False


class TestRequireObserved:
    def test_returns_the_observed_version(self) -> None:
        assert opt_lock.require_observed("Account", Observation(version=5)) == 5

    def test_raises_when_the_observation_is_none(self) -> None:
        with pytest.raises(opt_lock.UnobservedVersionError, match="Account"):
            opt_lock.require_observed("Account", None)

    def test_raises_when_the_observation_carries_no_version(self) -> None:
        # A temporal-only observation (in_z, no version) never licenses a
        # versioned advance either.
        with pytest.raises(opt_lock.UnobservedVersionError, match="Account"):
            opt_lock.require_observed("Account", Observation(in_z="2024-01-01T00:00:00+00:00"))


class TestCheckLockingLicense:
    def test_optimistic_mode_never_raises_regardless_of_pinning(self) -> None:
        opt_lock.check_locking_license("optimistic", latest_pinned=False)
        opt_lock.check_locking_license("optimistic", latest_pinned=True)

    def test_locking_mode_with_a_latest_pinned_observation_is_licensed(self) -> None:
        # A versioned non-temporal row satisfies this trivially (m-opt-lock).
        opt_lock.check_locking_license("locking", latest_pinned=True)

    def test_locking_mode_with_a_historical_observation_raises(self) -> None:
        with pytest.raises(opt_lock.HistoricalObservationError, match="latest-pinned"):
            opt_lock.check_locking_license("locking", latest_pinned=False)


def test_optimistic_lock_conflict_error_carries_its_context() -> None:
    key = (("id", 2),)
    error = opt_lock.OptimisticLockConflictError("Account", key, 1, 0)
    assert error.entity == "Account"
    assert error.key == key
    assert error.expected == 1
    assert error.actual == 0
    assert "Account" in str(error)
    assert "concurrent write changed the version first" in str(error)
