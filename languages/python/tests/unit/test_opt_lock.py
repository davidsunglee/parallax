"""``parallax.core.opt_lock`` unit tests (m-opt-lock).

Direct, isolated pins for the pure policy scope ``parallax.snapshot.handle``'s
write-lowering seam consumes: the observed-version requirement
(:func:`require_observed`), the runtime-computed advance (:func:`advance`), the
optimistic-only gate decision (:func:`gates`), and the derived initial version.
The corpus-level composition (the gate and advance wired through real DML) is
pinned in ``test_write_lowering.py``; this file is the policy scope's own,
narrower unit boundary.
"""

from __future__ import annotations

import pytest

from parallax.core import opt_lock
from parallax.core.unit_work import (
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
)


def _temporal() -> TemporalObservation:
    return TemporalObservation(
        predecessor=PredecessorRow(members={"id": 1, "txStart": "2024-01-01T00:00:00+00:00"})
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
