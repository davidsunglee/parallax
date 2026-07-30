"""``parallax.core.opt_lock`` unit tests (m-opt-lock).

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
from parallax.core.unit_work import (
    HISTORICAL_PINNED,
    LATEST_PINNED,
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
)


def _temporal() -> TemporalObservation:
    return TemporalObservation(
        predecessor=PredecessorRow(members={"id": 1, "tx_start": "2024-01-01T00:00:00+00:00"})
    )


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
        assert opt_lock.require_observed("Account", VersionObservation(observed_version=5)) == 5

    def test_raises_when_the_observation_is_none(self) -> None:
        with pytest.raises(opt_lock.UnobservedVersionError, match="Account"):
            opt_lock.require_observed("Account", None)

    def test_raises_for_a_temporal_observation(self) -> None:
        # A Temporal Observation names a predecessor milestone, never a version,
        # so it never licenses a versioned advance either.
        with pytest.raises(opt_lock.UnobservedVersionError, match="Account"):
            opt_lock.require_observed("Account", _temporal())


class TestCheckLockingLicense:
    def test_optimistic_mode_never_raises_regardless_of_pinning(self) -> None:
        opt_lock.check_locking_license("optimistic", HISTORICAL_PINNED)
        opt_lock.check_locking_license("optimistic", LATEST_PINNED)

    def test_locking_mode_with_a_latest_pinned_observation_is_licensed(self) -> None:
        # A versioned non-temporal row satisfies this trivially (m-opt-lock).
        opt_lock.check_locking_license("locking", LATEST_PINNED)

    def test_locking_mode_with_a_historical_observation_raises(self) -> None:
        with pytest.raises(opt_lock.HistoricalObservationError, match="latest-pinned"):
            opt_lock.check_locking_license("locking", HISTORICAL_PINNED)


def test_optimistic_lock_conflict_error_carries_its_context() -> None:
    key = (("id", 2),)
    error = opt_lock.OptimisticLockConflictError("Account", key, 1, 0)
    assert error.entity == "Account"
    assert error.key == key
    assert error.expected == 1
    assert error.actual == 0
    assert "Account" in str(error)
    assert "concurrent write changed the version first" in str(error)


class TestClassifyMismatch:
    """The single mismatch-to-error classification both render-seam call sites
    (`parallax.snapshot.handle`'s flush executor,
    `parallax.conformance.engine`'s standalone conflict-close probe) share."""

    def test_gated_mismatch_is_the_retriable_conflict(self) -> None:
        key = (("id", 2),)
        error = opt_lock.classify_mismatch("Account", key, 1, 0, stale_error=False)
        assert isinstance(error, opt_lock.OptimisticLockConflictError)
        assert error.entity == "Account"
        assert error.key == key
        assert error.expected == 1
        assert error.actual == 0

    def test_ungated_mismatch_is_the_non_retriable_stale_write(self) -> None:
        key = (("id", 2),)
        error = opt_lock.classify_mismatch("Balance", key, 1, 0, stale_error=True)
        assert isinstance(error, opt_lock.StaleWriteError)
        assert error.entity == "Balance"
        assert error.key == key

    def test_a_none_actual_count_normalizes_to_zero(self) -> None:
        error = opt_lock.classify_mismatch("Account", (("id", 1),), 1, None, stale_error=False)
        assert error.actual == 0
