"""Lookup parity between the descriptor-backed and the alternate Metamodel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeGuard, cast

import pytest

import fake_metamodel as fake
from parallax.conformance import case_format
from parallax.core._formation_profile import form_metamodel
from parallax.core.descriptor import parse_document, records, unresolved_metamodel
from parallax.core.metamodel import (
    EntityIdentity,
    EntityMetadata,
    FacetKey,
    Metamodel,
    NestedValueObjectMetadata,
    PersistenceMode,
    TemporalDimension,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def formed() -> Metamodel:
    """The parity model as the descriptor path forms it."""
    loaded = case_format.safe_load_yaml(fake.PARITY_DESCRIPTOR)
    assert isinstance(loaded, dict)
    document = cast("Mapping[str, object]", loaded)
    return form_metamodel(unresolved_metamodel(parse_document(document)))


@pytest.fixture(scope="module")
def alternate() -> Metamodel:
    """The parity model as the alternate implementation states it."""
    return fake.parity_model()


_ENTITIES = (fake.LEDGER, fake.ACCOUNT, fake.AUDIT, fake.ENTRY)


def _entity(model: Metamodel, identity: EntityIdentity) -> EntityMetadata:
    found = model.entity(identity)
    assert found is not None, identity
    return found


def _leaf(
    left: ValueObjectAttributeMetadata | None, right: ValueObjectAttributeMetadata | None
) -> None:
    """Assert two scalar Value Object leaves agree.

    The metadata protocols prescribe no concrete class, so two implementations
    of one leaf are never equal values; the contract is what they answer.
    """
    assert left is not None and right is not None
    assert left.identity == right.identity
    assert left.type == right.type
    assert left.nullable == right.nullable


def _occurrence(
    left: NestedValueObjectMetadata | ValueObjectMetadata,
    right: NestedValueObjectMetadata | ValueObjectMetadata,
) -> None:
    """Assert two Value Object occurrences agree member for member."""
    assert left.identity == right.identity
    assert left.multiplicity is right.multiplicity
    assert left.nullable == right.nullable

    assert len(left.attributes) == len(right.attributes)
    for attribute, other in zip(left.attributes, right.attributes, strict=True):
        _leaf(attribute, other)
        _leaf(left.attribute(attribute.identity.name), right.attribute(other.identity.name))

    assert len(left.value_objects) == len(right.value_objects)
    for below, other in zip(left.value_objects, right.value_objects, strict=True):
        _occurrence(below, other)
        assert left.value_object(below.identity.path[-1]) is below
        assert right.value_object(other.identity.path[-1]) is other

    assert left.attribute("nothing") is None
    assert right.attribute("nothing") is None
    assert left.value_object("nothing") is None
    assert right.value_object("nothing") is None


def test_the_alternate_implementation_constructs_no_descriptor_record() -> None:
    for entity in fake.parity_model().entities:
        assert type(entity).__module__ != records.__name__


def test_both_implementations_enumerate_in_canonical_identity_order(
    formed: Metamodel, alternate: Metamodel
) -> None:
    expected = list(_ENTITIES)
    assert [entity.identity for entity in formed.entities] == expected
    assert [entity.identity for entity in alternate.entities] == expected


@pytest.mark.parametrize("identity", _ENTITIES, ids=lambda identity: identity.canonical)
def test_both_implementations_agree_on_one_entity(
    formed: Metamodel, alternate: Metamodel, identity: EntityIdentity
) -> None:
    left, right = _entity(formed, identity), _entity(alternate, identity)
    assert left.identity == right.identity
    assert left.declared_container == right.declared_container
    assert left.declared_persistence == right.declared_persistence
    assert list(left.declared_attributes) == list(right.declared_attributes)
    assert list(left.declared_relationships) == list(right.declared_relationships)
    assert list(left.declared_as_of_axes) == list(right.declared_as_of_axes)
    assert list(left.indices) == list(right.indices)
    assert left.inheritance == right.inheritance

    assert len(left.declared_value_objects) == len(right.declared_value_objects)
    for occurrence, other in zip(
        left.declared_value_objects, right.declared_value_objects, strict=True
    ):
        assert occurrence.storage == other.storage
        _occurrence(occurrence, other)


@pytest.mark.parametrize("identity", _ENTITIES, ids=lambda identity: identity.canonical)
def test_both_implementations_resolve_local_members_the_same_way(
    formed: Metamodel, alternate: Metamodel, identity: EntityIdentity
) -> None:
    left, right = _entity(formed, identity), _entity(alternate, identity)
    for attribute in left.declared_attributes:
        assert right.attribute(attribute.identity.name) == attribute
    for relationship in left.declared_relationships:
        assert right.relationship(relationship.identity.name) == relationship
    for index in left.indices:
        assert right.index(index.identity.name) == index
    for occurrence in left.declared_value_objects:
        assert right.value_object(occurrence.identity.path[-1]) is not None
    for dimension in TemporalDimension:
        assert (left.as_of_axis(dimension) is None) == (right.as_of_axis(dimension) is None)
        assert left.as_of_axis(dimension) == right.as_of_axis(dimension)


@pytest.mark.parametrize("identity", _ENTITIES, ids=lambda identity: identity.canonical)
def test_both_implementations_return_absence_on_a_miss(
    formed: Metamodel, alternate: Metamodel, identity: EntityIdentity
) -> None:
    for model in (formed, alternate):
        entity = _entity(model, identity)
        assert entity.attribute("nothing") is None
        assert entity.relationship("nothing") is None
        assert entity.value_object("nothing") is None
        assert entity.index("nothing") is None
        assert model.entity(EntityIdentity("nowhere", identity.name)) is None


def test_read_only_persistence_and_the_temporal_axis_survive_both_paths(
    formed: Metamodel, alternate: Metamodel
) -> None:
    for model in (formed, alternate):
        audit = _entity(model, fake.AUDIT)
        assert audit.declared_persistence is PersistenceMode.READ_ONLY
        axis = audit.as_of_axis(TemporalDimension.TRANSACTION_TIME)
        assert axis is not None
        assert axis.start_attribute.name == "tx_start"
        assert audit.as_of_axis(TemporalDimension.VALID_TIME) is None
    ledger = _entity(alternate, fake.LEDGER)
    assert ledger.declared_persistence is None


def _is_text(value: object) -> TypeGuard[str]:
    """The stand-in facet type check the fixture's key carries."""
    return isinstance(value, str)


def test_the_alternate_implementation_serves_the_facets_it_is_given() -> None:
    key: FacetKey[str] = FacetKey("m-fixture", _is_text)
    model = fake.parity_model({key: "installed"})
    assert model.facet(key) == "installed"
