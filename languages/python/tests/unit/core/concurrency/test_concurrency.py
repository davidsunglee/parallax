"""m-concurrency: the strategy vocabulary, the version arithmetic, and each
question the Concurrency Facet answers over formed corpus models."""

from __future__ import annotations

from typing import Final

import pytest

from parallax.conformance import models
from parallax.core import concurrency
from parallax.core.concurrency import (
    CONCURRENCY_PREFERENCES,
    ConcurrencyPreference,
    ConcurrencyStrategy,
    EvidenceKind,
    ExplicitVersion,
    TransactionTimeVersion,
    Unversioned,
    concurrency_preference,
)
from parallax.core.metamodel import AttributeIdentity, EntityIdentity

_MODELS = models.load_models()
_PREFERENCES: Final[tuple[ConcurrencyPreference, ...]] = ("locking", "optimistic")


def _entity(name: str) -> EntityIdentity:
    return EntityIdentity("parallax.compatibility", name)


def _facet(stem: str) -> concurrency.ConcurrencyFacet:
    return concurrency.view(_MODELS[stem])


# --------------------------------------------------------------------------
# The vocabulary.
# --------------------------------------------------------------------------


class _UnhashableName(str):
    """A ``str`` no set can be asked about, so the validator is proved to compare."""

    __hash__ = None  # type: ignore[assignment]


def test_the_vocabulary_is_exactly_two_preferences() -> None:
    assert set(CONCURRENCY_PREFERENCES) == {"locking", "optimistic"}


@pytest.mark.parametrize("preference", sorted(CONCURRENCY_PREFERENCES))
def test_every_preference_of_the_vocabulary_is_returned_unchanged(preference: str) -> None:
    assert concurrency_preference(preference) == preference


@pytest.mark.parametrize(
    "value",
    [
        "pessimistic",
        "LOCKING",
        "",
        None,
        True,
        3,
        [],
        {"concurrency": "locking"},
        _UnhashableName("bogus"),
    ],
)
def test_anything_outside_the_vocabulary_is_refused_by_naming_the_whole_set(value: object) -> None:
    with pytest.raises(ValueError, match=r"concurrency must be one of \['locking', 'optimistic'\]"):
        concurrency_preference(value)


def test_an_accepted_preference_comes_back_as_a_plain_hashable_str() -> None:
    preference = concurrency_preference(_UnhashableName("locking"))

    assert preference == "locking"
    assert {preference: "keyable"}


# --------------------------------------------------------------------------
# The version arithmetic.
# --------------------------------------------------------------------------


def test_a_new_lineage_opens_at_version_one() -> None:
    assert concurrency.INITIAL_VERSION == 1


def test_a_write_advances_the_observed_version_by_one() -> None:
    assert concurrency.next_version(3) == 4
    assert concurrency.next_version(0) == 1


# --------------------------------------------------------------------------
# The four questions, over every version source and inheritance families.
# --------------------------------------------------------------------------

_SOURCES: Final = [
    pytest.param("animal", "Person", Unversioned, id="unversioned"),
    pytest.param("animal", "Dog", Unversioned, id="unversioned-family-descendant"),
    pytest.param("account", "Account", ExplicitVersion, id="explicit-version"),
    pytest.param("appliance", "Oven", ExplicitVersion, id="explicit-version-family-descendant"),
    pytest.param("balance", "Balance", TransactionTimeVersion, id="transaction-time"),
    pytest.param("position", "Position", TransactionTimeVersion, id="bitemporal"),
    pytest.param("instrument", "Bond", TransactionTimeVersion, id="temporal-family-descendant"),
]


@pytest.mark.parametrize(("stem", "entity", "variant"), _SOURCES)
def test_a_locking_preference_locks_every_family_and_an_optimistic_one_falls_back_unversioned(
    stem: str, entity: str, variant: type[object]
) -> None:
    facet = _facet(stem)
    expected: dict[ConcurrencyPreference, ConcurrencyStrategy] = {
        "locking": "locking",
        "optimistic": "locking" if variant is Unversioned else "optimistic",
    }
    assert {
        preference: facet.effective_strategy(_entity(entity), preference)
        for preference in _PREFERENCES
    } == expected


@pytest.mark.parametrize(("stem", "entity", "variant"), _SOURCES)
def test_a_family_settles_against_its_observation_exactly_when_it_is_versioned(
    stem: str, entity: str, variant: type[object]
) -> None:
    expected: EvidenceKind = "object" if variant is Unversioned else "observation"
    assert _facet(stem).settles_against(_entity(entity)) == expected


@pytest.mark.parametrize(("stem", "entity", "variant"), _SOURCES)
def test_only_an_explicit_version_names_a_version_attribute(
    stem: str, entity: str, variant: type[object]
) -> None:
    facet = _facet(stem)
    source = facet.version_source(_entity(entity))
    assert isinstance(source, variant)
    attribute = facet.version_attribute(_entity(entity))
    if isinstance(source, ExplicitVersion):
        assert attribute is source.attribute
    else:
        assert attribute is None


def test_a_family_descendant_names_its_roots_version_attribute() -> None:
    facet = _facet("appliance")
    assert facet.version_attribute(_entity("Oven")) == AttributeIdentity(
        _entity("Appliance"), "version"
    )
    assert facet.version_attribute(_entity("Oven")) is facet.version_attribute(_entity("Appliance"))


def test_a_transaction_time_family_names_its_milestone_start_as_its_version_source() -> None:
    assert _facet("balance").version_source(_entity("Balance")) == TransactionTimeVersion(
        AttributeIdentity(_entity("Balance"), "txStart")
    )


# --------------------------------------------------------------------------
# An Entity the model lacks.
# --------------------------------------------------------------------------


def test_an_entity_the_model_lacks_answers_each_question_the_safe_way() -> None:
    # A shared lock is always safe, there is nothing to project or compare, and
    # reading the miss as an object claim would let an unrecognized write claim
    # an object on the strength of what was missing.
    facet = _facet("account")
    missing = EntityIdentity("elsewhere", "Account")
    for preference in _PREFERENCES:
        assert facet.effective_strategy(missing, preference) == "locking"
    assert facet.version_attribute(missing) is None
    assert facet.version_source(missing) is None
    with pytest.raises(KeyError, match="no Entity this model declares"):
        facet.settles_against(missing)
