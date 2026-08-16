"""``parallax.core.opt_lock`` unit tests (m-opt-lock).

Direct, isolated pins for the pure policy scope ``parallax.snapshot.handle``'s
write-lowering seam consumes: the observed-version requirement
(:func:`require_observed`), the runtime-computed advance
(:func:`advance`), the per-Entity strategy derivation
(:func:`effective_strategy`), and the derived initial version. A keyed temporal
close's own observation requirement is not here: it is settled at the write
verb, as the write-evidence rule, and pinned where that rule is.
The corpus-level composition (the gate and advance wired through real DML) is
pinned in ``test_write_lowering.py``; this file is the policy scope's own,
narrower unit boundary.
"""

from __future__ import annotations

import pytest

from parallax.core import opt_lock
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.unit_work import (
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
)

_VERSION = AttributeIdentity(
    entity=EntityIdentity(namespace="parallax.compatibility", name="Account"), name="version"
)
_TX_START = AttributeIdentity(
    entity=EntityIdentity(namespace="parallax.compatibility", name="Balance"), name="txStart"
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


class TestEffectiveStrategy:
    def test_the_locking_preference_forces_locking_on_every_key(self) -> None:
        assert opt_lock.effective_strategy("locking", opt_lock.UNVERSIONED) == "locking"
        assert (
            opt_lock.effective_strategy("locking", opt_lock.ExplicitVersion(_VERSION)) == "locking"
        )
        assert (
            opt_lock.effective_strategy("locking", opt_lock.TransactionTimeDerived(_TX_START))
            == "locking"
        )

    def test_the_optimistic_preference_gates_wherever_the_model_supplies_a_version(self) -> None:
        assert (
            opt_lock.effective_strategy("optimistic", opt_lock.ExplicitVersion(_VERSION))
            == "optimistic"
        )
        assert (
            opt_lock.effective_strategy("optimistic", opt_lock.TransactionTimeDerived(_TX_START))
            == "optimistic"
        )

    def test_an_unversioned_family_falls_back_to_locking_under_the_optimistic_preference(
        self,
    ) -> None:
        assert opt_lock.effective_strategy("optimistic", opt_lock.UNVERSIONED) == "locking"

    def test_an_entity_the_facet_does_not_name_takes_the_same_locking_fallback(self) -> None:
        assert opt_lock.effective_strategy("optimistic", None) == "locking"


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
