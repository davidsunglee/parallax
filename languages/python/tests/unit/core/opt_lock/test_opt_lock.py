"""``parallax.core.opt_lock`` unit tests (m-opt-lock).

Direct, isolated pins for the pure policy scope ``parallax.snapshot.handle``'s
write-lowering seam consumes: the observed-version requirement
(:func:`require_observed`), the runtime-computed advance
(:func:`advance`), the per-Entity strategy derivation
(:func:`effective_strategy`), the derived initial version, and the
write-evidence policy each compiled Optimistic Key answers the unit of work
through, which the module-level functions delegate to. A keyed temporal
close's own observation requirement is not here: it is settled at the write
verb, as the write-evidence rule, and pinned where that rule is.
The corpus-level composition (the gate and advance wired through real DML) is
pinned in ``test_write_lowering.py``; this file is the policy scope's own,
narrower unit boundary.
"""

from __future__ import annotations

import datetime as dt
from typing import get_args

import pytest

from parallax.conformance import models
from parallax.core import opt_lock
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.opt_lock._facet import UNVERSIONED, Unversioned
from parallax.core.unit_work import (
    INSERT_MUTATIONS,
    Concurrency,
    KeyedMutation,
    ObjectKey,
    PredecessorRow,
    RetainedObservation,
    TemporalObservation,
    VersionObservation,
    WriteEvidencePolicy,
)
from parallax.core.unit_work.planner import VersionedStateKey

_VERSION = AttributeIdentity(
    entity=EntityIdentity(namespace="parallax.compatibility", name="Account"), name="version"
)
_TX_START = AttributeIdentity(
    entity=EntityIdentity(namespace="parallax.compatibility", name="Balance"), name="txStart"
)


def _temporal() -> TemporalObservation:
    return TemporalObservation(
        predecessor=PredecessorRow(
            members={"id": 1, "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC)}
        )
    )


def test_initial_version_is_one() -> None:
    assert opt_lock.INITIAL_VERSION == 1


def test_advance_is_runtime_computed_from_the_observed_value() -> None:
    assert opt_lock.advance(3) == 4
    assert opt_lock.advance(0) == 1


class TestEffectiveStrategy:
    def test_the_locking_preference_forces_locking_on_every_key(self) -> None:
        assert opt_lock.effective_strategy("locking", UNVERSIONED) == "locking"
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
        assert opt_lock.effective_strategy("optimistic", UNVERSIONED) == "locking"

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


# --------------------------------------------------------------------------
# The write-evidence policy every compiled key answers.
# --------------------------------------------------------------------------
_MODELS = models.load_models()


def _compiled(stem: str, entity: str) -> opt_lock.OptimisticKey:
    """The key the corpus model ``stem`` compiled for ``entity``."""
    model = _MODELS[stem]
    return opt_lock.view(model).required_key(
        EntityIdentity(namespace="parallax.compatibility", name=entity)
    )


_UNVERSIONED_KEY = _compiled("animal", "Person")
_EXPLICIT_KEY = _compiled("account", "Account")
_TT_DERIVED_KEY = _compiled("balance", "Balance")
_OBJECT = ObjectKey(EntityIdentity("parallax.compatibility", "Account"), (("id", 1),))
_RETAINED = RetainedObservation(
    VersionedStateKey(_OBJECT, 4), VersionObservation(observed_version=4), None
)
_MUTATIONS: tuple[KeyedMutation, ...] = get_args(KeyedMutation)
_PREFERENCES: tuple[Concurrency, ...] = ("locking", "optimistic")


def test_the_compiled_keys_are_the_three_variants() -> None:
    assert isinstance(_UNVERSIONED_KEY, Unversioned)
    assert isinstance(_EXPLICIT_KEY, opt_lock.ExplicitVersion)
    assert isinstance(_TT_DERIVED_KEY, opt_lock.TransactionTimeDerived)
    policies: tuple[WriteEvidencePolicy, ...] = (_UNVERSIONED_KEY, _EXPLICIT_KEY, _TT_DERIVED_KEY)
    assert len(policies) == 3


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (_UNVERSIONED_KEY, {"locking": "locking", "optimistic": "locking"}),
        (_EXPLICIT_KEY, {"locking": "locking", "optimistic": "optimistic"}),
        (_TT_DERIVED_KEY, {"locking": "locking", "optimistic": "optimistic"}),
    ],
    ids=["unversioned", "explicit-version", "transaction-time-derived"],
)
def test_each_key_derives_its_effective_strategy_and_the_module_function_delegates(
    key: opt_lock.OptimisticKey, expected: dict[Concurrency, Concurrency]
) -> None:
    for preference in _PREFERENCES:
        assert key.effective_strategy(preference) == expected[preference]
        assert opt_lock.effective_strategy(preference, key) == expected[preference]


@pytest.mark.parametrize(
    ("key", "existing_row"),
    [
        (_UNVERSIONED_KEY, _OBJECT),
        (_EXPLICIT_KEY, _RETAINED),
        (_TT_DERIVED_KEY, _RETAINED),
    ],
    ids=["unversioned", "explicit-version", "transaction-time-derived"],
)
def test_each_key_settles_every_mutation_and_the_module_function_delegates(
    key: opt_lock.OptimisticKey, existing_row: object
) -> None:
    # An insert settles against nothing under every key; every other keyed
    # mutation settles against the object for an unversioned family and the
    # observed state for a versioned one, whichever the other argument holds.
    for mutation in _MUTATIONS:
        expected = None if mutation in INSERT_MUTATIONS else existing_row
        answered = key.settled_evidence(mutation, object_key=_OBJECT, observation=_RETAINED)
        delegated = opt_lock.settled_evidence(
            key, mutation, object_key=_OBJECT, observation=_RETAINED
        )
        assert answered is expected, mutation
        assert delegated is expected, mutation


def test_a_key_handed_none_of_the_evidence_its_arm_reads_settles_nothing() -> None:
    assert _EXPLICIT_KEY.settled_evidence("update", object_key=_OBJECT, observation=None) is None
    assert _UNVERSIONED_KEY.settled_evidence("delete", object_key=None, observation=_RETAINED) is (
        None
    )


def test_the_keys_keep_their_value_equality_and_family_sharing() -> None:
    assert _UNVERSIONED_KEY == Unversioned() == UNVERSIONED
    assert hash(_UNVERSIONED_KEY) == hash(Unversioned())
    explicit = _EXPLICIT_KEY
    assert isinstance(explicit, opt_lock.ExplicitVersion)
    assert opt_lock.ExplicitVersion(explicit.attribute) == explicit
    assert hash(opt_lock.ExplicitVersion(explicit.attribute)) == hash(explicit)
    assert opt_lock.view(_MODELS["appliance"]).required_key(
        EntityIdentity("parallax.compatibility", "Oven")
    ) is opt_lock.view(_MODELS["appliance"]).required_key(
        EntityIdentity("parallax.compatibility", "Appliance")
    )
