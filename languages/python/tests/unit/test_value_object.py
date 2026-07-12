"""m-value-object: recursive path resolution and any-element detection."""

from __future__ import annotations

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core import value_object as vo
from parallax.core.descriptor import NestedValueObject, ValueObject, ValueObjectAttribute

pytestmark = pytest.mark.unit

_MODELS = corpus_models.load_models(
    case_format.find_repo_root() / "core" / "compatibility" / "models"
)


def _address() -> ValueObject:
    (customer,) = _MODELS["customer"].entities
    (address,) = customer.value_objects
    return address


def test_document_column_is_the_top_level_backing_column() -> None:
    assert vo.document_column(_address()) == "address"


def test_member_resolves_direct_children() -> None:
    address = _address()
    assert isinstance(vo.member(address, "city"), ValueObjectAttribute)
    assert isinstance(vo.member(address, "geo"), NestedValueObject)
    assert vo.member(address, "missing") is None


@pytest.mark.parametrize(
    ("path", "expected_type"),
    [
        (["city"], "string"),
        (["geo", "country"], "string"),
        (["geo", "point", "lat"], "float64"),
        (["phones", "number"], "string"),
    ],
)
def test_resolve_and_leaf_type_walk_nested_paths(path: list[str], expected_type: str) -> None:
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
    many = ValueObject(
        name="tags",
        column="tags",
        cardinality="many",
        attributes=(ValueObjectAttribute(name="label", type="string"),),
    )
    assert vo.crosses_many(many, ["label"]) is True


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
