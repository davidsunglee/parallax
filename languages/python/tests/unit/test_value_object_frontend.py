"""The Value Object class frontend.

The structural no-drift proof runs against ``models/customer.yaml``'s recursive
``Address`` / ``Geo`` / ``Point`` / ``Phone`` composite: the class declarations in
``value_object_models`` must compile to the same member names, types,
nullability, and multiplicities the corpus authors. The remaining cases cover
element-scoped expressions, the document serializer's omission policy, and the
rejections a Value Object body owns.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest
from value_object_bad_models import (
    build_entity_only_option_value_object,
    build_header_bearing_value_object,
    build_non_attr_annotated_value_object,
)

import value_object_models as vm
from parallax.conformance import case_format
from parallax.core import Attr, ValueObject, attr
from parallax.core.base import Decimal as NeutralDecimal
from parallax.core.base import Float64, NeutralType, String
from parallax.core.entity import ElementAttributeExpr, EntityDefinitionError, Predicate, to_document
from parallax.core.entity._declaration import shape_of
from parallax.core.metamodel import (
    Column,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
)
from parallax.core.op_algebra import serialize

pytestmark = pytest.mark.unit

_CORPUS_TYPES: dict[str, NeutralType] = {
    "string": String(),
    "float64": Float64(),
}


def _corpus_customer() -> dict[str, object]:
    path = case_format.find_repo_root() / "core" / "compatibility" / "models" / "customer.yaml"
    loaded = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    entities = cast("list[dict[str, object]]", cast("dict[str, object]", loaded)["entities"])
    return next(entity for entity in entities if entity["name"] == "Customer")


def _assert_shape_matches(shape: ValueObjectShapeDeclaration, corpus: dict[str, object]) -> None:
    """Compare one declared shape against its corpus spelling, leaves first."""
    leaves = cast("list[dict[str, object]]", corpus.get("attributes", []))
    assert list(shape.attributes) == [
        ValueObjectAttributeDeclaration(
            name=cast("str", leaf["name"]),
            type=_CORPUS_TYPES[cast("str", leaf["type"])],
            nullable=bool(leaf.get("nullable", False)),
        )
        for leaf in leaves
    ]
    nested = cast("list[dict[str, object]]", corpus.get("valueObjects", []))
    assert [occurrence.name for occurrence in shape.value_objects] == [
        cast("str", member["name"]) for member in nested
    ]
    for occurrence, member in zip(shape.value_objects, nested, strict=True):
        assert isinstance(occurrence, NestedValueObjectOccurrenceDeclaration)
        assert occurrence.nullable is bool(member.get("nullable", False))
        expected = Multiplicity.MANY if member.get("multiplicity") == "many" else Multiplicity.ONE
        assert occurrence.multiplicity is expected
        _assert_shape_matches(occurrence.shape, member)


def test_the_declared_composite_has_no_drift_from_the_corpus_customer_model() -> None:
    corpus = _corpus_customer()
    declared = vm.Customer.value_objects
    corpus_occurrences = cast("list[dict[str, object]]", corpus["valueObjects"])
    assert [occurrence.name for occurrence in declared] == [
        cast("str", member["name"]) for member in corpus_occurrences
    ]
    for occurrence, member in zip(declared, corpus_occurrences, strict=True):
        assert isinstance(occurrence, ValueObjectOccurrenceDeclaration)
        assert occurrence.storage == Column(cast("str", member["name"]))
        assert occurrence.nullable is bool(member.get("nullable", False))
        _assert_shape_matches(occurrence.shape, member)


def test_a_value_object_occurrence_owns_its_storage_and_nested_ones_do_not() -> None:
    (address,) = vm.Customer.value_objects
    assert address.storage == Column("address")
    geo = address.shape.value_objects[0]
    assert not hasattr(geo, "storage")


def test_element_scoped_access_builds_paths_with_no_entity_prefix() -> None:
    expression = vm.Phone.type
    assert isinstance(expression, ElementAttributeExpr)
    predicate = expression == "home"
    assert isinstance(predicate, Predicate)
    assert serialize(predicate.op) == {"nestedEq": {"path": "type", "value": "home"}}


def test_an_entity_rooted_nested_predicate_carries_the_dotted_canonical_path() -> None:
    predicate = vm.Customer.address.geo.country == "DE"
    assert isinstance(predicate, Predicate)
    assert serialize(predicate.op) == {
        "nestedEq": {"path": "Customer.address.geo.country", "value": "DE"}
    }


def test_the_document_omits_a_member_the_caller_never_set() -> None:
    assert to_document(vm.Geo(country="DE")) == {"country": "DE"}
    assert to_document(None) is None


def test_a_many_occurrence_always_renders_even_when_empty() -> None:
    document = to_document(vm.Address(street="a", city="b"))
    assert document == {"street": "a", "city": "b", "phones": []}


def test_the_document_renders_nested_occurrences_recursively() -> None:
    address = vm.Address(
        street="a",
        city="b",
        geo=vm.Geo(country="DE", point=vm.Point(lat=1.0, lon=2.0)),
        phones=(vm.Phone(type="home", number="1"),),
    )
    assert to_document(address) == {
        "street": "a",
        "city": "b",
        "geo": {"country": "DE", "point": {"lat": 1.0, "lon": 2.0}},
        "phones": [{"type": "home", "number": "1"}],
    }


def test_a_value_object_member_takes_instances_only() -> None:
    with pytest.raises(TypeError, match="never a raw mapping"):
        vm.Address(street="a", city="b", geo={"country": "DE"})  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError, match="never a raw mapping"):
        vm.Address(street="a", city="b", phones=({"type": "home"},))  # pyright: ignore[reportArgumentType]


def test_a_many_occurrence_requires_a_tuple() -> None:
    with pytest.raises(TypeError, match="requires a tuple"):
        vm.Address(street="a", city="b", phones=[vm.Phone(type="home")])  # pyright: ignore[reportArgumentType]


def test_one_shape_is_minted_per_class_and_shared_by_every_occurrence() -> None:
    assert shape_of(vm.Address).shape is vm.Customer.value_objects[0].shape
    assert shape_of(vm.Geo).shape is vm.Customer.value_objects[0].shape.value_objects[0].shape


def test_a_value_object_scalar_admits_the_naming_and_type_shaping_options() -> None:
    class Money(ValueObject):
        amount_due: Attr[Decimal] = attr(precision=12, scale=4, name="due")

    (leaf,) = shape_of(Money).shape.attributes
    assert leaf.name == "due"
    assert leaf.type == NeutralDecimal(12, 4)


@pytest.mark.parametrize(
    ("build", "code"),
    [
        (build_non_attr_annotated_value_object, "entity-annotation-invalid"),
        (build_entity_only_option_value_object, "entity-option-context-invalid"),
        (build_header_bearing_value_object, "entity-header-unknown-option"),
    ],
)
def test_a_value_object_body_outside_the_grammar_is_rejected(build: object, code: str) -> None:
    builder = cast("object", build)
    assert callable(builder)
    with pytest.raises(EntityDefinitionError) as caught:
        builder()
    assert caught.value.code == code


def test_shape_lookup_rejects_a_class_the_engine_never_built() -> None:
    with pytest.raises(EntityDefinitionError) as caught:
        shape_of(int)
    assert caught.value.code == "entity-annotation-invalid"


def test_a_value_object_is_frozen_without_declaring_it() -> None:
    phone = vm.Phone(type="home", number="1")
    with pytest.raises(ValueError, match="frozen"):
        phone.number = "2"  # pyright: ignore[reportAttributeAccessIssue]
