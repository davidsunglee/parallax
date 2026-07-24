"""m-value-object: recursive path resolution and any-element detection."""

from __future__ import annotations

import pytest
from _metamodel_support import Declaration, identity, key, source

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core import value_object as vo
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import FLOAT64, STRING, NeutralType
from parallax.core.metamodel import (
    Column,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    Table,
    ValueObjectAttributeDeclaration,
    ValueObjectMetadata,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)

pytestmark = pytest.mark.unit

_MODELS = corpus_models.load_models(
    case_format.find_repo_root() / "core" / "compatibility" / "models"
)


def _model(stem: str) -> Metamodel:
    return corpus_models.accepted_model(_MODELS[stem])


def _address() -> ValueObjectMetadata:
    customer = _model("customer").entity(EntityIdentity("parallax.compatibility", "Customer"))
    assert customer is not None
    (address,) = customer.declared_value_objects
    return address


def test_document_column_is_the_top_level_backing_column() -> None:
    assert vo.document_column(_address()) == "address"


def test_member_resolves_direct_children() -> None:
    address = _address()
    assert vo.member(address, "city") is address.attribute("city")
    assert vo.member(address, "geo") is address.value_object("geo")
    assert vo.member(address, "missing") is None


@pytest.mark.parametrize(
    ("path", "expected_type"),
    [
        (["city"], STRING),
        (["geo", "country"], STRING),
        (["geo", "point", "lat"], FLOAT64),
        (["phones", "number"], STRING),
    ],
)
def test_resolve_and_leaf_type_walk_nested_paths(
    path: list[str], expected_type: NeutralType
) -> None:
    assert vo.leaf_type(_address(), path) == expected_type


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (["city"], False),
        (["geo"], False),  # path exhausts on a cardinality-one nested VO
        (["geo", "country"], False),
        (["geo", "point", "lat"], False),
        (["phones", "number"], True),
    ],
)
def test_crosses_many_flags_paths_through_many_members(path: list[str], expected: bool) -> None:
    assert vo.crosses_many(_address(), path) is expected


def test_crosses_many_is_true_for_a_many_top_level_value_object() -> None:
    # No corpus model declares a to-many occurrence at the top level, so the
    # branch is proven over a hand-built model rather than a corpus one.
    owner = identity("Tagged")
    occurrence = ValueObjectOccurrenceDeclaration(
        name="tags",
        storage=Column("tags"),
        shape=ValueObjectShapeDeclaration(
            key=ValueObjectShapeKey(),
            attributes=(ValueObjectAttributeDeclaration("label", type=STRING),),
        ),
        multiplicity=Multiplicity.MANY,
    )
    model = form_metamodel(
        source(
            Declaration(
                identity=owner,
                container=Table("tagged"),
                attributes=(key(owner),),
                value_objects=(occurrence,),
            )
        )
    )
    entity = model.entity(owner)
    assert entity is not None
    tags = entity.value_object("tags")
    assert tags is not None
    assert vo.crosses_many(tags, ["label"]) is True


@pytest.mark.parametrize(
    "path",
    [
        [],  # empty path
        ["unknown"],  # unknown segment
        ["city", "deeper"],  # scalar is not the final segment
        ["geo"],  # path ends on a nested value object, not a leaf
    ],
)
def test_resolve_rejects_malformed_paths(path: list[str]) -> None:
    with pytest.raises(vo.ValueObjectError):
        vo.resolve(_address(), path)
