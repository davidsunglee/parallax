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
from typing import Any, cast

import pytest
from value_object_bad_models import (
    build_entity_only_option_value_object,
    build_framework_slot_annotated_value_object,
    build_framework_slot_shadowing_value_object,
    build_header_bearing_value_object,
    build_non_attr_annotated_value_object,
    build_pydantic_namespace_value_object,
)

from _support import value_object_models as vm
from parallax.conformance import case_format
from parallax.core import Attr, Entity, ValueObject, attr
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
from parallax.core.predicate import serialize

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


_DECLARATION_REQUIRED: frozenset[tuple[str, ...]] = frozenset(
    {
        ("address", "city"),
        ("address", "geo", "country"),
    }
)


def _assert_shape_matches(
    shape: ValueObjectShapeDeclaration, corpus: dict[str, object], path: tuple[str, ...]
) -> None:
    """Compare one declared shape against its corpus spelling, leaves first."""
    leaves = cast("list[dict[str, object]]", corpus.get("attributes", []))
    assert list(shape.attributes) == [
        ValueObjectAttributeDeclaration(
            name=cast("str", leaf["name"]),
            type=_CORPUS_TYPES[cast("str", leaf["type"])],
            nullable=False
            if (*path, cast("str", leaf["name"])) in _DECLARATION_REQUIRED
            else bool(leaf.get("nullable", False)),
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
        _assert_shape_matches(occurrence.shape, member, (*path, occurrence.name))


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
        _assert_shape_matches(occurrence.shape, member, (occurrence.name,))


def test_a_top_level_occurrence_derives_storage_while_nested_members_remain_columnless() -> None:
    class Recipient(Entity, table="recipient"):
        id: Attr[int] = attr(primary_key=True)
        mailing_address: Attr[vm.Address]

    (mailing_address,) = Recipient.value_objects
    assert mailing_address.storage == Column("mailing_address")
    geo = next(
        occurrence for occurrence in mailing_address.shape.value_objects if occurrence.name == "geo"
    )
    assert not hasattr(geo, "storage")
    assert all(not hasattr(attribute, "storage") for attribute in mailing_address.shape.attributes)


def _element(expression: object) -> ElementAttributeExpr[Any, Any]:
    """The element-scoped carrier a Value Object's class access yields.

    Statically the descriptor is typed by its ``Attr[T]`` annotation, so the
    element-scoped runtime carrier is narrowed once here. Its own parameters are
    erased rather than recovered: an ``isinstance`` narrowing answers the class,
    never what it was specialized with.
    """
    assert isinstance(expression, ElementAttributeExpr)
    return cast("ElementAttributeExpr[Any, Any]", expression)


def test_element_scoped_access_builds_paths_with_no_entity_prefix() -> None:
    expression = vm.Phone.type
    assert isinstance(expression, ElementAttributeExpr)
    predicate = expression == "home"
    assert isinstance(predicate, Predicate)
    assert serialize(predicate.node) == {"nestedEq": {"path": "type", "value": "home"}}


def test_every_element_scoped_operator_builds_its_own_nested_node() -> None:
    # The element-relative spelling of the whole predicate surface: one
    # `nested*` node per operator, each path element-rooted with no entity
    # prefix, as a quantifier's interior requires.
    phone_type = _element(vm.Phone.type)
    assert serialize((phone_type != "home").node) == {
        "nestedNotEq": {"path": "type", "value": "home"}
    }
    assert serialize((phone_type > "a").node) == {"nestedGt": {"path": "type", "value": "a"}}
    assert serialize((phone_type >= "a").node) == {"nestedGte": {"path": "type", "value": "a"}}
    assert serialize((phone_type < "z").node) == {"nestedLt": {"path": "type", "value": "z"}}
    assert serialize((phone_type <= "z").node) == {"nestedLte": {"path": "type", "value": "z"}}
    assert serialize(phone_type.in_(["home", "work"]).node) == {
        "nestedIn": {"path": "type", "values": ["home", "work"]}
    }
    assert serialize(phone_type.not_in(["work"]).node) == {
        "nestedNotIn": {"path": "type", "values": ["work"]}
    }
    assert serialize(phone_type.between("a", "z").node) == {
        "nestedBetween": {"path": "type", "lower": "a", "upper": "z"}
    }
    assert serialize(phone_type.like("ho%").node) == {
        "nestedLike": {"path": "type", "value": "ho%"}
    }
    assert serialize(phone_type.not_like("ho%").node) == {
        "nestedNotLike": {"path": "type", "value": "ho%"}
    }
    assert serialize(phone_type.starts_with("ho").node) == {
        "nestedStartsWith": {"path": "type", "value": "ho"}
    }
    assert serialize(phone_type.ends_with("me").node) == {
        "nestedEndsWith": {"path": "type", "value": "me"}
    }
    assert serialize(phone_type.contains("om", case_insensitive=True).node) == {
        "nestedContains": {"path": "type", "value": "om", "caseInsensitive": True}
    }
    assert serialize(phone_type.is_null().node) == {"nestedIsNull": {"path": "type"}}
    assert serialize(phone_type.is_not_null().node) == {"nestedIsNotNull": {"path": "type"}}


def test_a_boolean_element_reads_as_an_explicit_nested_equality() -> None:
    class Toggle(ValueObject):
        enabled: Attr[bool | None]

    predicate = _element(Toggle.enabled).is_(True)
    assert serialize(predicate.node) == {"nestedEq": {"path": "enabled", "value": True}}


def test_an_element_scoped_hop_stays_element_relative_however_deep_it_goes() -> None:
    # A nested occurrence continues the element path rather than restarting it,
    # so an interior predicate over a nested leaf never grows an entity prefix.
    predicate = _element(vm.Address.geo).country == "DE"
    assert serialize(predicate.node) == {"nestedEq": {"path": "geo.country", "value": "DE"}}


def test_an_element_expression_answers_no_private_name_and_has_no_truth_value() -> None:
    # The hop resolves any public name dynamically, so the private-name guard is
    # what keeps a dunder probe (copy, pickle) from being read as a member.
    element = _element(vm.Phone.number)
    with pytest.raises(AttributeError, match="_missing"):
        _ = element._missing
    with pytest.raises(TypeError, match="has no truth value"):
        bool(element)


def test_an_entity_rooted_nested_predicate_carries_the_dotted_canonical_path() -> None:
    predicate = vm.Customer.address.geo.country == "DE"
    assert isinstance(predicate, Predicate)
    assert serialize(predicate.node) == {
        "nestedEq": {"path": "parallax.compatibility.Customer.address.geo.country", "value": "DE"}
    }


def test_a_nested_range_and_negated_membership_stay_nested_rather_than_scalar() -> None:
    # `.between(...)` / `.not_in(...)` follow `.in_(...)`: on a value-object path they
    # build the NESTED node carrying the whole dotted path, not the scalar node over a
    # truncated `Class.member` reference.
    assert serialize(vm.Customer.address.geo.elevation.between(5, 12).node) == {
        "nestedBetween": {
            "path": "parallax.compatibility.Customer.address.geo.elevation",
            "lower": 5,
            "upper": 12,
        }
    }
    assert serialize(vm.Customer.address.city.not_in(["Oslo"]).node) == {
        "nestedNotIn": {"path": "parallax.compatibility.Customer.address.city", "values": ["Oslo"]}
    }
    assert serialize(vm.Customer.address.city.starts_with("Os").node) == {
        "nestedStartsWith": {"path": "parallax.compatibility.Customer.address.city", "value": "Os"}
    }
    assert serialize(vm.Customer.address.city.like("OS%", case_insensitive=True).node) == {
        "nestedLike": {
            "path": "parallax.compatibility.Customer.address.city",
            "value": "OS%",
            "caseInsensitive": True,
        }
    }
    # A non-nested attribute on the same Entity keeps the scalar spelling, and the
    # fluent surface never authors an explicit `caseInsensitive: false`.
    assert serialize(vm.Customer.name.starts_with("A").node) == {
        "startsWith": {"attr": "parallax.compatibility.Customer.name", "value": "A"}
    }
    # A non-nested attribute on the same Entity keeps the scalar spellings.
    assert serialize(vm.Customer.name.not_in(["Ada"]).node) == {
        "notIn": {"attr": "parallax.compatibility.Customer.name", "values": ["Ada"]}
    }
    assert serialize(vm.Customer.id.between(1, 3).node) == {
        "between": {"attr": "parallax.compatibility.Customer.id", "lower": 1, "upper": 3}
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
        vm.Address(street="a", city="b", geo={"country": "DE"})
    with pytest.raises(TypeError, match="never a raw mapping"):
        vm.Address(street="a", city="b", phones=({"type": "home"},))


def test_a_many_occurrence_requires_a_tuple() -> None:
    with pytest.raises(TypeError, match="requires a tuple"):
        vm.Address(street="a", city="b", phones=[vm.Phone(type="home")])


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
        (build_framework_slot_shadowing_value_object, "entity-reserved-member-name"),
        (build_framework_slot_annotated_value_object, "entity-reserved-member-name"),
        (build_pydantic_namespace_value_object, "entity-reserved-member-name"),
    ],
)
def test_a_value_object_body_outside_the_grammar_is_rejected(build: object, code: str) -> None:
    assert callable(build)
    with pytest.raises(EntityDefinitionError) as caught:
        build()
    assert caught.value.code == code


def test_a_value_object_still_declares_the_entity_only_reserved_spellings() -> None:
    # The reservation narrows with the surface it protects: a Value Object has no
    # query root, no declaration protocol, and no copy verb, so those names name
    # nothing here and stay ordinary members.
    class Audit(ValueObject):
        identity: Attr[str]
        edit: Attr[str]

    assert {leaf.name for leaf in shape_of(Audit).shape.attributes} == {"identity", "edit"}


def test_shape_lookup_rejects_a_class_the_engine_never_built() -> None:
    with pytest.raises(EntityDefinitionError) as caught:
        shape_of(int)
    assert caught.value.code == "entity-annotation-invalid"


def test_a_value_object_is_frozen_without_declaring_it() -> None:
    phone = vm.Phone(type="home", number="1")
    with pytest.raises(ValueError, match="frozen"):
        phone.number = "2"  # pyright: ignore[reportAttributeAccessIssue] - frozen value object: the write must raise
