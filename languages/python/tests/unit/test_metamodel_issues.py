"""m-metamodel: the Metamodel Issue value and its canonical ordering law."""

from __future__ import annotations

import random

import pytest

from parallax.core.metamodel import (
    MODEL_ROOT,
    AsOfAxisLocation,
    AttributeIdentity,
    AttributeLocation,
    EntityIdentity,
    EntityLocation,
    IndexIdentity,
    IndexLocation,
    MetamodelIssue,
    ModelLocation,
    RelationshipIdentity,
    RelationshipLocation,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeLocation,
    ValueObjectIdentity,
    ValueObjectLocation,
    canonical_issue_key,
    canonical_location_key,
    sort_issues,
)

pytestmark = pytest.mark.unit

_ALPHA = EntityIdentity("app", "Alpha")
_BETA = EntityIdentity("app", "Beta")
_OWNERLESS = EntityIdentity(None, "Alpha")
_ALPHA_VO = ValueObjectIdentity(_ALPHA, ("address",))

# One location of every rank on one Entity, in the canonical order the law
# fixes: Entity, Attribute, Relationship, Value Object, Value Object Attribute,
# As-Of Axis, Index.
_RANKED: tuple[ModelLocation, ...] = (
    EntityLocation(_ALPHA),
    AttributeLocation(AttributeIdentity(_ALPHA, "id")),
    RelationshipLocation(RelationshipIdentity(_ALPHA, "items")),
    ValueObjectLocation(_ALPHA_VO),
    ValueObjectAttributeLocation(ValueObjectAttributeIdentity(_ALPHA_VO, "city")),
    AsOfAxisLocation(_ALPHA, TemporalDimension.VALID_TIME),
    IndexLocation(IndexIdentity(_ALPHA, "alpha_pk")),
)


def _issue(location: ModelLocation, code: str = "metamodel-test") -> MetamodelIssue:
    return MetamodelIssue(code, location, message="explanatory only")


def test_the_model_root_sorts_before_every_located_issue() -> None:
    ordered = sort_issues([_issue(location) for location in _RANKED] + [_issue(MODEL_ROOT)])
    assert ordered[0].location == MODEL_ROOT


def test_locations_group_by_entity_then_fixed_member_rank() -> None:
    ordered = sort_issues(reversed([_issue(location) for location in _RANKED]))
    assert tuple(issue.location for issue in ordered) == _RANKED


def test_an_ownerless_entity_sorts_before_a_namespaced_one() -> None:
    ordered = sort_issues([_issue(EntityLocation(_ALPHA)), _issue(EntityLocation(_OWNERLESS))])
    assert [issue.location for issue in ordered] == [
        EntityLocation(_OWNERLESS),
        EntityLocation(_ALPHA),
    ]


def test_entities_group_before_member_rank_decides() -> None:
    alpha_index = _issue(IndexLocation(IndexIdentity(_ALPHA, "alpha_pk")))
    beta_entity = _issue(EntityLocation(_BETA))
    assert sort_issues([beta_entity, alpha_index]) == (alpha_index, beta_entity)


def test_value_object_paths_compare_lexicographically() -> None:
    shallow = ValueObjectLocation(ValueObjectIdentity(_ALPHA, ("address",)))
    deep = ValueObjectLocation(ValueObjectIdentity(_ALPHA, ("address", "geo")))
    sibling = ValueObjectLocation(ValueObjectIdentity(_ALPHA, ("billing",)))
    ordered = sort_issues([_issue(sibling), _issue(deep), _issue(shallow)])
    assert [issue.location for issue in ordered] == [shallow, deep, sibling]


def test_valid_time_precedes_transaction_time_within_an_axis_location() -> None:
    valid = AsOfAxisLocation(_ALPHA, TemporalDimension.VALID_TIME)
    transaction = AsOfAxisLocation(_ALPHA, TemporalDimension.TRANSACTION_TIME)
    ordered = sort_issues([_issue(transaction), _issue(valid)])
    assert [issue.location for issue in ordered] == [valid, transaction]


def test_code_breaks_ties_at_one_location() -> None:
    later = _issue(EntityLocation(_ALPHA), "metamodel-primary-key-missing")
    earlier = _issue(EntityLocation(_ALPHA), "metamodel-duplicate-entity-identity")
    assert sort_issues([later, earlier]) == (earlier, later)


def test_related_locations_break_ties_after_the_code() -> None:
    first = MetamodelIssue(
        "metamodel-local-member-collision",
        EntityLocation(_ALPHA),
        (AttributeLocation(AttributeIdentity(_ALPHA, "a")),),
    )
    second = MetamodelIssue(
        "metamodel-local-member-collision",
        EntityLocation(_ALPHA),
        (AttributeLocation(AttributeIdentity(_ALPHA, "b")),),
    )
    assert sort_issues([second, first]) == (first, second)


def test_message_participates_in_neither_equality_nor_ordering() -> None:
    terse = MetamodelIssue("metamodel-primary-key-missing", EntityLocation(_ALPHA), message="a")
    verbose = MetamodelIssue(
        "metamodel-primary-key-missing", EntityLocation(_ALPHA), message="zzz much longer"
    )
    assert terse == verbose
    assert hash(terse) == hash(verbose)
    assert canonical_issue_key(terse) == canonical_issue_key(verbose)


def test_equality_is_code_location_and_related() -> None:
    location = EntityLocation(_ALPHA)
    related = (AttributeLocation(AttributeIdentity(_ALPHA, "id")),)
    assert MetamodelIssue("x", location, related) == MetamodelIssue("x", location, related)
    assert MetamodelIssue("x", location, related) != MetamodelIssue("y", location, related)
    assert MetamodelIssue("x", location, related) != MetamodelIssue("x", location)
    assert MetamodelIssue("x", location) != MetamodelIssue("x", EntityLocation(_BETA))


def test_ordering_is_independent_of_emission_order() -> None:
    issues = [_issue(location) for location in _RANKED] + [_issue(MODEL_ROOT)]
    expected = sort_issues(issues)
    shuffler = random.Random(20260722)
    for _ in range(20):
        permuted = list(issues)
        shuffler.shuffle(permuted)
        assert sort_issues(permuted) == expected


def test_every_location_variant_produces_a_comparable_key() -> None:
    keys = [canonical_location_key(location) for location in (MODEL_ROOT, *_RANKED)]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)
