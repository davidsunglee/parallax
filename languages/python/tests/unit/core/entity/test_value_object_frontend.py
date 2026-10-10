"""The Value Object class frontend.

The structural no-drift proof runs against ``models/customer.yaml``'s recursive
``Address`` / ``Geo`` / ``Point`` / ``Phone`` composite: the class declarations in
``value_object_models`` must compile to the same member names, types,
nullability, and multiplicities the corpus authors. The remaining cases cover
element-scoped expressions, the document serializer's omission policy, and the
rejections a Value Object body owns.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance import case_format
from parallax.core import Attr, Entity, ValueObject, attr
from parallax.core.base import Decimal as NeutralDecimal
from parallax.core.base import Float64, NeutralType, String
from parallax.core.entity import EntityDefinitionError, Predicate
from parallax.core.entity._declaration import shape_of
from parallax.core.entity._expressions import (
    AssignableScalarExpr,
    AuthoredPath,
    AuthoredPresence,
    ManyValueObjectExpr,
    PreparedOperation,
    ScalarExpr,
    ValueObjectExpr,
)
from parallax.core.metamodel import (
    Column,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    Occurrence,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
)
from parallax.core.predicate import QueryDefinitionError
from parallax.core.predicate._interpretation import COMPARE
from tests._support import value_object_models as vm
from tests._support.query_probes import predicate_document
from tests.unit.core.entity._value_object_document_support import inserted_document
from tests.unit.core.entity.value_object_bad_models import (
    build_copy_verb_value_object,
    build_entity_only_option_value_object,
    build_framework_slot_annotated_value_object,
    build_framework_slot_shadowing_value_object,
    build_header_bearing_value_object,
    build_non_attr_annotated_value_object,
    build_pydantic_namespace_value_object,
)

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


def _field(expression: object) -> ScalarExpr[Any, Any]:
    """The query-only field carrier a Value Object's class access yields.

    Statically the descriptor is typed by its ``Attr[T]`` annotation on the
    Value Object, so the runtime carrier is narrowed once here.
    """
    assert isinstance(expression, ScalarExpr)
    assert not isinstance(expression, AssignableScalarExpr)
    return cast("ScalarExpr[Any, Any]", expression)


def _phone_where(predicate: Predicate[Any]) -> object:
    """``predicate`` exported inside the quantifier over the phones it reads."""
    query = vm.Customer.where(vm.Customer.address.phones.any(predicate))
    return predicate_document(query, vm.CUSTOMER_MODEL)["any"]["where"]  # type: ignore[index] - the exported document's shape


def _customer_where(predicate: Predicate[Any]) -> dict[str, object]:
    return predicate_document(vm.Customer.where(predicate), vm.CUSTOMER_MODEL)


def test_value_object_class_access_builds_relative_paths() -> None:
    predicate = _field(vm.Phone.type) == "home"
    assert isinstance(predicate, Predicate)
    assert _phone_where(predicate) == {"eq": {"path": "type", "value": "home"}}


def test_every_relative_field_operator_builds_the_ordinary_scalar_node() -> None:
    phone_type = _field(vm.Phone.type)
    assert _phone_where(phone_type != "home") == {"notEq": {"path": "type", "value": "home"}}
    assert _phone_where(phone_type > "a") == {"greaterThan": {"path": "type", "value": "a"}}
    assert _phone_where(phone_type >= "a") == {"greaterThanEquals": {"path": "type", "value": "a"}}
    assert _phone_where(phone_type < "z") == {"lessThan": {"path": "type", "value": "z"}}
    assert _phone_where(phone_type <= "z") == {"lessThanEquals": {"path": "type", "value": "z"}}
    assert _phone_where(phone_type.in_(["home", "work"])) == {
        "in": {"path": "type", "values": ["home", "work"]}
    }
    assert _phone_where(phone_type.not_in(["work"])) == {
        "notIn": {"path": "type", "values": ["work"]}
    }
    assert _phone_where(phone_type.between("a", "z")) == {
        "between": {"path": "type", "lower": "a", "upper": "z"}
    }
    assert _phone_where(phone_type.like("ho%")) == {"like": {"path": "type", "value": "ho%"}}
    assert _phone_where(phone_type.not_like("ho%")) == {"notLike": {"path": "type", "value": "ho%"}}
    assert _phone_where(phone_type.starts_with("ho")) == {
        "startsWith": {"path": "type", "value": "ho"}
    }
    assert _phone_where(phone_type.ends_with("me")) == {"endsWith": {"path": "type", "value": "me"}}
    assert _phone_where(phone_type.contains("om", case_insensitive=True)) == {
        "contains": {"path": "type", "value": "om", "caseInsensitive": True}
    }
    assert _phone_where(phone_type.is_null()) == {"isNull": {"path": "type"}}
    assert _phone_where(phone_type.is_not_null()) == {"isNotNull": {"path": "type"}}


def test_a_boolean_field_reads_as_an_explicit_equality() -> None:
    class Toggle(ValueObject):
        enabled: Attr[bool | None]

    authored = _field(Toggle.enabled).is_(True).authored
    assert isinstance(authored, PreparedOperation)
    assert (authored.operator, authored.operands) == (COMPARE["eq"], (True,))


def test_a_single_value_object_hop_continues_the_relative_path() -> None:
    geo = vm.Address.geo
    assert isinstance(geo, ValueObjectExpr)
    compared = (geo.country == "DE").authored
    present, absent = geo.exists().authored, geo.not_exists().authored
    assert isinstance(compared, PreparedOperation)
    assert isinstance(compared.subject, AuthoredPath)
    assert compared.subject.names == ("geo", "country")
    assert isinstance(present, AuthoredPresence) and isinstance(absent, AuthoredPresence)
    assert (present.negated, present.target.names) == (False, ("geo",))
    assert (absent.negated, absent.target.names) == (True, ("geo",))


def test_a_many_value_object_is_quantified_rather_than_traversed() -> None:
    phones = vm.Address.phones
    assert isinstance(phones, ManyValueObjectExpr)
    assert not hasattr(phones, "number")
    assert predicate_document(
        vm.Customer.where(vm.Customer.address.phones.any(_field(vm.Phone.type) == "home")),
        vm.CUSTOMER_MODEL,
    ) == {
        "any": {
            "path": "parallax.compatibility.Customer.address.phones",
            "where": {"eq": {"path": "type", "value": "home"}},
        }
    }


def test_a_value_object_expression_answers_no_private_name_and_has_no_truth_value() -> None:
    # The hop resolves any public name dynamically, so the private-name guard is
    # what keeps a dunder probe (copy, pickle) from being read as a member.
    geo = vm.Address.geo
    with pytest.raises(AttributeError, match="_missing"):
        _ = geo._missing
    with pytest.raises(TypeError, match="has no truth value"):
        bool(geo)
    with pytest.raises(TypeError, match="has no truth value"):
        bool(_field(vm.Phone.number))


def test_field_access_refuses_unknown_members_and_nonnullable_null_checks() -> None:
    with pytest.raises(AttributeError, match="missing"):
        _ = vm.Address.missing  # type: ignore[attr-defined] - deliberately undeclared member
    with pytest.raises(AttributeError, match="declares no member 'missing'"):
        _ = vm.Customer.address.missing
    with pytest.raises(QueryDefinitionError, match="non-nullable member"):
        _field(vm.Address.city).is_null()


def test_an_entity_rooted_value_object_predicate_carries_the_dotted_canonical_path() -> None:
    predicate: Predicate[Any] = vm.Customer.address.geo.country == "DE"
    assert isinstance(predicate, Predicate)
    assert _customer_where(predicate) == {
        "eq": {"path": "parallax.compatibility.Customer.address.geo.country", "value": "DE"}
    }


def test_invalid_nested_operand_reports_the_complete_developer_input_rule() -> None:
    with pytest.raises(QueryDefinitionError) as caught:
        _ = vm.Customer.address.geo.elevation == "high"
    message = str(caught.value)
    assert "parallax.compatibility.Customer.address.geo.elevation" in message
    assert "declared NeutralType" in message
    assert "supplied Python carrier str" in message
    assert "developer-input rule violated" in message


def test_invalid_relative_operand_reports_the_complete_developer_input_rule() -> None:
    with pytest.raises(QueryDefinitionError) as caught:
        _field(vm.Geo.elevation).__eq__(None)
    message = str(caught.value)
    assert "elevation" in message
    assert "declared NeutralType" in message
    assert "supplied Python carrier NoneType" in message
    assert "developer-input rule violated" in message


def test_a_dotted_range_membership_and_match_carry_the_whole_path() -> None:
    assert _customer_where(vm.Customer.address.geo.elevation.between(5, 12)) == {
        "between": {
            "path": "parallax.compatibility.Customer.address.geo.elevation",
            "lower": 5,
            "upper": 12,
        }
    }
    assert _customer_where(vm.Customer.address.city.not_in(["Oslo"])) == {
        "notIn": {"path": "parallax.compatibility.Customer.address.city", "values": ["Oslo"]}
    }
    assert _customer_where(vm.Customer.address.city.starts_with("Os")) == {
        "startsWith": {"path": "parallax.compatibility.Customer.address.city", "value": "Os"}
    }
    assert _customer_where(vm.Customer.address.city.like("OS%", case_insensitive=True)) == {
        "like": {
            "path": "parallax.compatibility.Customer.address.city",
            "value": "OS%",
            "caseInsensitive": True,
        }
    }
    # The fluent surface never authors an explicit `caseInsensitive: false`.
    assert _customer_where(vm.Customer.name.starts_with("A")) == {
        "startsWith": {"path": "parallax.compatibility.Customer.name", "value": "A"}
    }
    assert _customer_where(vm.Customer.name.not_in(["Ada"])) == {
        "notIn": {"path": "parallax.compatibility.Customer.name", "values": ["Ada"]}
    }
    assert _customer_where(vm.Customer.id.between(1, 3)) == {
        "between": {"path": "parallax.compatibility.Customer.id", "lower": 1, "upper": 3}
    }


def _stored_document(address: vm.Address) -> Mapping[str, object]:
    return inserted_document(vm.CUSTOMER_MODEL, vm.Customer(id=1, name="Ada", address=address))


def test_the_document_omits_a_member_the_caller_never_set() -> None:
    address = vm.Address(street="a", city="b", geo=vm.Geo(country="DE"))
    assert _stored_document(address)["geo"] == {"country": "DE"}


def test_a_many_occurrence_always_renders_even_when_empty() -> None:
    document = _stored_document(vm.Address(street="a", city="b"))
    assert document == {"street": "a", "city": "b", "phones": []}

    absent_many = vm.Address.model_construct(street="a", city="b")
    absent_many.__pydantic_fields_set__.discard("phones")
    assert _stored_document(absent_many) == {"street": "a", "city": "b", "phones": []}


def test_the_document_renders_nested_occurrences_recursively() -> None:
    address = vm.Address(
        street="a",
        city="b",
        geo=vm.Geo(country="DE", point=vm.Point(lat=1.0, lon=2.0)),
        phones=(vm.Phone(type="home", number="1"),),
    )
    assert _stored_document(address) == {
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


def test_a_value_object_class_retains_its_document_shape_with_nested_identity() -> None:
    address = shape_of(vm.Address)
    geo = shape_of(vm.Geo)

    assert address.document_shape == address.shape.member_shape
    nested = address.document_shape.member("geo")
    assert isinstance(nested, Occurrence)
    assert nested.shape is geo.document_shape


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
        (build_copy_verb_value_object, "entity-reserved-member-name"),
    ],
)
def test_a_value_object_body_outside_the_grammar_is_rejected(build: object, code: str) -> None:
    assert callable(build)
    with pytest.raises(EntityDefinitionError) as caught:
        build()
    assert caught.value.code == code


def test_a_value_object_still_declares_the_entity_only_reserved_spellings() -> None:
    # The reservation narrows with the surface it protects: a Value Object has no
    # query root and no declaration protocol, so those names name nothing here and
    # stay ordinary members. The copy verb is the one spelling that left this
    # family when a Value Object gained an `edit` of its own.
    class Audit(ValueObject):
        identity: Attr[str]
        where: Attr[str]

    assert {leaf.name for leaf in shape_of(Audit).shape.attributes} == {"identity", "where"}


def test_shape_lookup_rejects_a_class_the_engine_never_built() -> None:
    with pytest.raises(EntityDefinitionError) as caught:
        shape_of(int)
    assert caught.value.code == "entity-annotation-invalid"


def test_a_value_object_is_frozen_without_declaring_it() -> None:
    phone = vm.Phone(type="home", number="1")
    with pytest.raises(ValueError, match="frozen"):
        phone.number = "2"  # pyright: ignore[reportAttributeAccessIssue] - frozen value object: the write must raise
