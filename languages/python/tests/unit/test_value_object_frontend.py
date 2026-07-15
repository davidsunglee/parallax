"""D-7 value-object class frontend: unit-level no-drift proof against
``models/customer.yaml``'s recursive ``Address`` / ``Geo`` / ``Point`` /
``Phone`` composite (COR-3 Phase 7 increment 6a). The full API-conformance
no-drift guard extension is blocked by the SAME single, global, process-wide
entity-registry constraint `read_models.py`/`read_stories.py` document
(ledger D-20 — no installed Customer mirror can share that canonical name
with the test-only `value_object_models.Customer`; D-21 covers the
Supplier/Branch value-object families separately); this is the build-time
proof that the ``ValueObject`` class frontend threads its declared structure
into the compiled entity record exactly as an ingested descriptor would.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

import value_object_models as vm
from parallax.conformance import case_format
from parallax.core import Attr
from parallax.core.descriptor import canonicalize
from parallax.core.entity import descriptor_document
from parallax.core.entity.errors import EntityDefinitionError
from parallax.core.entity.expressions import Predicate
from parallax.core.entity.value_object import ValueObject, VoField, structure_of, wire_names_of
from parallax.core.op_algebra import NestedComparison, NestedExists, serialize

pytestmark = pytest.mark.unit


def _customer_yaml() -> dict[str, object]:
    import yaml

    path = case_format.find_repo_root() / "core" / "compatibility" / "models" / "customer.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast("dict[str, object]", loaded)


def test_value_object_class_export_has_no_drift_from_the_corpus_customer_model() -> None:
    # Scoped to the Address/Geo/Point/Phone composite (this module's own
    # focus): `customer.yaml` also declares the `Location` / `Depot` deep-
    # fetch-witness relationships (D-14), out of scope for a VO-only mirror.
    corpus = canonicalize(_customer_yaml())
    entities = cast("list[dict[str, object]]", corpus["entities"])
    corpus_customer = next(e for e in entities if e["name"] == "Customer")
    mine = cast("dict[str, object]", descriptor_document([vm.Customer])["entity"])
    assert mine["attributes"] == corpus_customer["attributes"]
    assert mine["valueObjects"] == corpus_customer["valueObjects"]


def test_entity_rooted_nested_predicate_serializes_the_dotted_canonical_path() -> None:
    predicate = vm.Customer.address.city == "Berlin"
    assert isinstance(predicate, Predicate)
    assert serialize(predicate.op) == {
        "nestedEq": {"path": "Customer.address.city", "value": "Berlin"}
    }


def test_deeply_nested_entity_rooted_predicate_reaches_the_leaf() -> None:
    predicate = vm.Customer.address.geo.country == "DE"
    assert serialize(predicate.op) == {
        "nestedEq": {"path": "Customer.address.geo.country", "value": "DE"}
    }


def test_element_scoped_phone_predicate_has_no_leading_entity_prefix() -> None:
    predicate = vm.Phone.type == "home"
    assert serialize(predicate.op) == {"nestedEq": {"path": "type", "value": "home"}}


def test_element_scoped_predicate_composes_and_serializes_element_relative() -> None:
    predicate = vm.Phone.type == "home"
    op = predicate.op
    assert isinstance(op, NestedComparison)
    assert op.path == "type"


def test_element_scoped_path_chains_through_a_nested_value_object() -> None:
    # Mirrors the entity-rooted `AttributeExpr`'s own dynamic hop, but starting
    # from an ELEMENT-scope root (`Address` used directly, no leading entity
    # name) — the class docstring's own worked example.
    predicate = vm.Address.geo.country == "DE"
    assert serialize(predicate.op) == {"nestedEq": {"path": "geo.country", "value": "DE"}}


def test_element_scoped_dynamic_hop_rejects_a_private_name() -> None:
    with pytest.raises(AttributeError):
        vm.Address.geo.__getattr__("_hidden")


def test_element_scoped_predicate_operators_cover_every_comparison_and_membership_form() -> None:
    assert serialize((vm.Phone.type != "home").op) == {
        "nestedNotEq": {"path": "type", "value": "home"}
    }
    assert serialize((vm.Phone.number > "1").op) == {"nestedGt": {"path": "number", "value": "1"}}
    assert serialize((vm.Phone.number >= "1").op) == {"nestedGte": {"path": "number", "value": "1"}}
    assert serialize((vm.Phone.number < "9").op) == {"nestedLt": {"path": "number", "value": "9"}}
    assert serialize((vm.Phone.number <= "9").op) == {"nestedLte": {"path": "number", "value": "9"}}
    assert serialize(vm.Phone.type.is_(True).op) == {"nestedEq": {"path": "type", "value": True}}
    assert serialize(vm.Phone.type.in_(["home", "work"]).op) == {
        "nestedIn": {"path": "type", "values": ["home", "work"]}
    }
    assert serialize(vm.Phone.type.is_null().op) == {"nestedIsNull": {"path": "type"}}
    assert serialize(vm.Phone.type.is_not_null().op) == {"nestedIsNotNull": {"path": "type"}}
    with pytest.raises(TypeError):
        bool(vm.Phone.type)


def test_any_over_a_value_object_terminated_path_builds_nested_exists() -> None:
    predicate = vm.Customer.address.phones.any(
        vm.Phone.type == "home", vm.Phone.number == "555-9999"
    )
    op = predicate.op
    assert isinstance(op, NestedExists)
    assert op.path == "Customer.address.phones"
    assert serialize(predicate.op) == {
        "nestedExists": {
            "path": "Customer.address.phones",
            "where": {
                "and": {
                    "operands": [
                        {"nestedEq": {"path": "type", "value": "home"}},
                        {"nestedEq": {"path": "number", "value": "555-9999"}},
                    ]
                }
            },
        }
    }


def test_none_with_no_predicates_emits_the_bare_absence_test() -> None:
    predicate = vm.Customer.address.phones.none()
    assert serialize(predicate.op) == {"nestedNotExists": {"path": "Customer.address.phones"}}


def test_value_object_instances_round_trip_through_construction() -> None:
    phone = vm.Phone(type="home", number="555-1234")
    address = vm.Address(
        street="Main St",
        city="Berlin",
        geo=vm.Geo(country="DE", elevation=34.0, point=vm.Point(lat=52.5, lon=13.4)),
        phones=(phone,),
    )
    customer = vm.Customer(id=1, name="Ada", address=address)
    assert customer.address is address
    assert address.geo is not None
    assert address.geo.point is not None
    assert address.geo.point.lat == 52.5
    assert address.phones == (phone,)


def test_value_object_is_the_only_legal_json_column_input() -> None:
    with pytest.raises(Exception, match="never a raw dict"):
        vm.Customer(id=1, name="Ada", address={"street": "Main St", "city": "Berlin"})  # type: ignore[arg-type]


def test_to_document_serializes_a_value_object_instance_to_its_canonical_document() -> None:
    from parallax.core.entity.value_object import to_document

    phone = vm.Phone(type="home", number="555-1234")
    address = vm.Address(street="Main St", city="Berlin", geo=None, phones=(phone,))
    document = to_document(address)
    assert document == {
        "street": "Main St",
        "city": "Berlin",
        "geo": None,
        "phones": [{"type": "home", "number": "555-1234"}],
    }
    assert to_document(None) is None


def test_to_document_serializes_a_nested_single_value_object_field() -> None:
    from parallax.core.entity.value_object import to_document

    address = vm.Address(
        street="Main St",
        city="Berlin",
        geo=vm.Geo(country="DE", elevation=None, point=None),
        phones=(),
    )
    document = to_document(address)
    assert document is not None
    assert document["geo"] == {"country": "DE", "elevation": None, "point": None}


def test_a_cardinality_many_value_object_member_rejects_a_list_not_a_tuple() -> None:
    with pytest.raises(Exception, match="never a raw dict/list"):
        vm.Address(
            street="Main St",
            city="Berlin",
            geo=None,
            phones=[vm.Phone(type="home", number="1")],  # type: ignore[arg-type]
        )


def test_a_cardinality_many_value_object_member_rejects_a_non_value_object_element() -> None:
    with pytest.raises(Exception, match="is not a"):
        vm.Address(street="Main St", city="Berlin", geo=None, phones=(object(),))  # type: ignore[arg-type]


def test_structure_of_and_wire_names_of_reject_a_non_value_object_class() -> None:
    with pytest.raises(EntityDefinitionError, match="not a compiled ValueObject class"):
        structure_of(int)
    with pytest.raises(EntityDefinitionError, match="not a compiled ValueObject class"):
        wire_names_of(int)


def test_a_value_object_field_without_an_explicit_type_infers_the_neutral_type() -> None:
    class Inferred(ValueObject, frozen=True):
        flag: Attr[bool] = VoField()

    assert structure_of(Inferred).attributes[0].type == "boolean"


def test_a_value_object_decimal_field_without_an_explicit_precision_is_rejected() -> None:
    with pytest.raises(Exception, match="explicit precision"):

        class BadDecimal(ValueObject, frozen=True):  # pyright: ignore[reportUnusedClass]
            amount: Attr[Decimal] = VoField()


def test_a_value_object_union_typed_field_that_is_not_optional_is_rejected() -> None:
    # A `X | Y` union with no `None` member: `_strip_optional` leaves it
    # unchanged (its own single-nullable-member narrowing does not apply),
    # so type inference still fails — a Union is not a recognized neutral type.
    with pytest.raises(Exception, match="cannot infer a neutral type"):

        class BadUnion(ValueObject, frozen=True):  # pyright: ignore[reportUnusedClass]
            weird: Attr[int | str] = VoField()


def test_a_value_object_forward_ref_unresolvable_at_class_body_scope_falls_back_to_raw_text() -> (
    None
):
    # `_LocalOnly` resolves lexically here (pyright/ruff see a real name), but
    # the metaclass's own annotation resolver evaluates forward references
    # against the DEFINING MODULE's globals only, never the enclosing
    # function's locals — so it can't find `_LocalOnly` either, exercising
    # `_attr_inner`'s `NameError` fallback (the raw text is kept, and neutral-
    # type inference then rejects it exactly like any other unresolvable type).
    class _LocalOnly(ValueObject, frozen=True):
        pass

    with pytest.raises(Exception, match="cannot infer a neutral type"):

        class BadForwardRef(ValueObject, frozen=True):  # pyright: ignore[reportUnusedClass]
            weird: Attr[_LocalOnly] = VoField()


def test_a_tuple_typed_field_of_non_value_object_elements_is_rejected() -> None:
    # `tuple[int, ...]` is not `tuple[VOClass, ...]`: `vo_field_info` declines
    # it (not a value-object member), so it falls through to plain neutral-type
    # inference, which has no tuple mapping either.
    with pytest.raises(Exception, match="cannot infer a neutral type"):

        class BadTuple(ValueObject, frozen=True):  # pyright: ignore[reportUnusedClass]
            values: Attr[tuple[int, ...]] = VoField()


def test_a_stringized_non_attr_annotation_is_rejected() -> None:
    # This test module has `from __future__ import annotations`, so `plain`'s
    # annotation is the raw string `"int"` — exercises `_attr_inner`'s OWN
    # stringized-annotation branch (as opposed to the live-annotation fallback
    # `value_object_bad_models.py` exercises).
    with pytest.raises(EntityDefinitionError, match="must be annotated Attr"):

        class BadPlain(ValueObject, frozen=True):  # pyright: ignore[reportUnusedClass]
            plain: int


def test_a_value_object_field_not_annotated_attr_is_rejected() -> None:
    import value_object_bad_models as bad

    with pytest.raises(EntityDefinitionError, match="must be annotated Attr"):
        bad.build_non_attr_annotated_value_object()
