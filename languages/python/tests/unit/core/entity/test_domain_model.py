"""``DomainModel`` construction: argument validation, formation, and realization.

Each test declares the classes its own scenario needs, so a failure names the
declaration it is about. Nothing here isolates one construction from another:
composing a class into a model binds nothing, so the same class is free to
appear in as many models as any test cares to build.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from typing import get_args

import pytest

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_ONE,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    UsageError,
    ValueObject,
    attr,
    rel,
)
from parallax.core.internal.entity._errors import MetamodelDefinitionCode
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.inheritance import inheritance_facet_of
from parallax.core.internal.model_formation import MetamodelValidationError
from tests._support.errors import raises_code

_SPEC_CODES = frozenset(
    {"metamodel-empty", "metamodel-invalid-entity-class", "metamodel-duplicate-entity-class"}
)


def _value_object_class() -> type:
    class Point(ValueObject):
        x: Attr[int]

    return Point


class _ReusablePoint(ValueObject):
    x: Attr[int]


class _ReusableFirst(Entity, table="reusable_first", name="ReusableFirst"):
    id: Attr[int] = attr(primary_key=True)
    point: Attr[_ReusablePoint]


class _ReusableSecond(Entity, table="reusable_second", name="ReusableSecond"):
    id: Attr[int] = attr(primary_key=True)
    location: Attr[_ReusablePoint]


class _ReusableBrokenFirst(Entity, table="reusable_broken_first", name="ReusableBroken"):
    id: Attr[int] = attr(primary_key=True)
    point: Attr[_ReusablePoint]


class _ReusableBrokenSecond(Entity, table="reusable_broken_second", name="ReusableBroken"):
    id: Attr[int] = attr(primary_key=True)
    location: Attr[_ReusablePoint]


def test_a_model_over_no_source_is_empty_with_no_argument_index() -> None:
    with raises_code(UsageError, "metamodel-empty") as caught:
        DomainModel()
    assert "argument" not in caught.value.args[1]


@pytest.mark.parametrize(
    "make_argument",
    [
        pytest.param(lambda: dict, id="ordinary-class"),
        pytest.param(lambda: Entity, id="framework-root"),
        pytest.param(lambda: TxTemporal, id="temporal-framework-root"),
        pytest.param(_value_object_class, id="value-object-class"),
        pytest.param(lambda: "Widget", id="not-a-class"),
    ],
)
def test_an_argument_that_is_not_a_domain_entity_class_is_rejected_by_position(
    make_argument: Callable[[], object],
) -> None:
    class Widget(Entity, table="widget"):
        id: Attr[int] = attr(primary_key=True)

    with raises_code(UsageError, "metamodel-invalid-entity-class") as caught:
        DomainModel(Widget, make_argument())  # pyright: ignore[reportArgumentType] - deliberate non-Entity-Class argument drives constructor validation
    assert caught.value.args[1].startswith("argument 1 ")


def test_a_repeated_class_object_is_rejected_at_its_own_index() -> None:
    class Gadget(Entity, table="gadget"):
        id: Attr[int] = attr(primary_key=True)

    class Doodad(Entity, table="doodad"):
        id: Attr[int] = attr(primary_key=True)

    with raises_code(UsageError, "metamodel-duplicate-entity-class") as caught:
        DomainModel(Gadget, Doodad, Gadget)
    assert caught.value.args[1].startswith("argument 2 ")


def test_arguments_are_checked_left_to_right() -> None:
    class Sprocket(Entity, table="sprocket"):
        id: Attr[int] = attr(primary_key=True)

    # Argument 1 is invalid and argument 2 repeats argument 0; the leftmost
    # defect is the one reported.
    with raises_code(UsageError, "metamodel-invalid-entity-class") as caught:
        DomainModel(Sprocket, object(), Sprocket)  # pyright: ignore[reportArgumentType] - deliberate non-Entity-Class argument drives constructor validation
    assert caught.value.args[1].startswith("argument 1 ")


def test_the_definition_code_set_is_closed() -> None:
    assert frozenset(get_args(MetamodelDefinitionCode.__value__)) == _SPEC_CODES


def test_two_distinct_classes_sharing_one_identity_reach_whole_model_validation() -> None:
    class First(Entity, table="first", name="Shared"):
        id: Attr[int] = attr(primary_key=True)

    class Second(Entity, table="second", name="Shared"):
        id: Attr[int] = attr(primary_key=True)

    with pytest.raises(MetamodelValidationError) as caught:
        DomainModel(First, Second)
    assert [issue.code for issue in caught.value.issues] == ["metamodel-duplicate-entity-identity"]


class _Stamp(ValueObject):
    tx_start: Attr[_dt.datetime]
    valid_end: Attr[_dt.datetime]


def test_a_transaction_time_base_refuses_a_valid_time_endpoint_name_before_formation() -> None:
    # The pre-injection guard still owns every temporal-base case, including a
    # dimension the base does not derive: it refuses at class definition, before
    # the shared resolver could judge the same name.
    with raises_code(UsageError, "entity-reserved-member-name") as caught:

        class Reading(TxTemporal, table="reading"):  # pyright: ignore[reportUnusedClass] - class creation itself is the rejection, so nothing binds
            id: Attr[int] = attr(primary_key=True)
            valid_start: Attr[_dt.datetime]

    assert "temporal base" in caught.value.args[1]


def test_a_nested_value_object_member_may_bear_a_temporal_endpoint_name() -> None:
    class Receipt(Bitemporal, table="receipt"):
        id: Attr[int] = attr(primary_key=True)
        stamp: Attr[_Stamp]

    class Note(Entity, table="note"):
        id: Attr[int] = attr(primary_key=True)
        stamp: Attr[_Stamp]

    models = DomainModel(Receipt, Note)
    assert [entity.identity.name for entity in models.entities] == ["Note", "Receipt"]


def test_a_target_outside_the_candidate_set_is_a_model_defect() -> None:
    class Elsewhere(Entity, table="elsewhere"):
        id: Attr[int] = attr(primary_key=True)

    class Dangling(Entity, table="dangling"):
        id: Attr[int] = attr(primary_key=True)
        elsewhere_id: Attr[int]
        elsewhere: Rel[Elsewhere] = rel(cardinality=MANY_TO_ONE, join=("elsewhere_id", "id"))

    # `Elsewhere` exists as a class but is not composed into this model, and
    # resolution is confined to the candidate set.
    with pytest.raises(MetamodelValidationError) as caught:
        DomainModel(Dangling)
    assert [issue.code for issue in caught.value.issues] == [
        "metamodel-unresolved-entity-reference"
    ]


def test_every_annotation_mismatch_is_reported_together_in_canonical_order() -> None:
    class Coupon(Entity, table="coupon", namespace="sales"):
        id: Attr[int] = attr(primary_key=True)

    class Order(Entity, table="orders", namespace="sales"):
        id: Attr[int] = attr(primary_key=True)
        coupon_id: Attr[int | None]
        coupon: Rel[Coupon] = rel(cardinality=MANY_TO_ONE, join=("coupon_id", "id"))
        customer_id: Attr[int]
        customer: Rel[Customer | None] = rel(cardinality=MANY_TO_ONE, join=("customer_id", "id"))

    class Customer(Entity, table="customer", namespace="sales"):
        id: Attr[int] = attr(primary_key=True)
        orders: Rel[Order] = rel(reverse_of="customer")

    with raises_code(UsageError, "entity-relationship-annotation-mismatch") as caught:
        DomainModel(Order, Customer, Coupon)
    reported = [line.strip() for line in caught.value.args[1].splitlines()[1:]]
    assert reported == [
        "Customer.orders spells Rel[T] but the accepted model requires Rel[tuple[T, ...]]",
        "Order.coupon spells Rel[T] but the accepted model requires Rel[T | None]",
        "Order.customer spells Rel[T | None] but the accepted model requires Rel[T]",
    ]


def test_a_to_one_direction_may_not_be_spelled_many() -> None:
    class Shelf(Entity, table="shelf"):
        id: Attr[int] = attr(primary_key=True)

    class Book(Entity, table="book"):
        id: Attr[int] = attr(primary_key=True)
        shelf_id: Attr[int]
        shelf: Rel[tuple[Shelf, ...]] = rel(cardinality=MANY_TO_ONE, join=("shelf_id", "id"))

    with raises_code(UsageError, "entity-relationship-annotation-mismatch") as caught:
        DomainModel(Shelf, Book)
    reported = [line.strip() for line in caught.value.args[1].splitlines()[1:]]
    assert reported == [
        "Book.shelf spells Rel[tuple[T, ...]] but the accepted model requires Rel[T]"
    ]


def test_an_agreeing_annotation_set_seals() -> None:
    class Coupon(Entity, table="coupon"):
        id: Attr[int] = attr(primary_key=True)

    class Order(Entity, table="orders"):
        id: Attr[int] = attr(primary_key=True)
        coupon_id: Attr[int | None]
        coupon: Rel[Coupon | None] = rel(cardinality=MANY_TO_ONE, join=("coupon_id", "id"))
        customer_id: Attr[int]
        customer: Rel[Customer] = rel(cardinality=MANY_TO_ONE, join=("customer_id", "id"))

    class Customer(Entity, table="customer"):
        id: Attr[int] = attr(primary_key=True)
        orders: Rel[tuple[Order, ...]] = rel(reverse_of="customer")
        profile: Rel[Profile | None] = rel(reverse_of="customer")

    class Profile(Entity, table="profile"):
        id: Attr[int] = attr(primary_key=True)
        customer_id: Attr[int]
        customer: Rel[Customer] = rel(cardinality=ONE_TO_ONE, join=("customer_id", "id"))

    models = DomainModel(Order, Customer, Coupon, Profile)
    assert [entity.identity.name for entity in models.entities] == [
        "Coupon",
        "Customer",
        "Order",
        "Profile",
    ]


def test_an_inherited_join_source_decides_optionality_family_effectively() -> None:
    class Region(Entity, table="region"):
        id: Attr[int] = attr(primary_key=True)

    class Site(
        Entity, table="site", inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind"))
    ):
        id: Attr[int] = attr(primary_key=True)
        region_id: Attr[int | None]

    class Depot(Site, inheritance=ConcreteSubtype(tag_value="depot")):
        # The join source is declared on `Site` and addressed at `Depot`, so the
        # loaded-null answer follows the family-effective attribute.
        region: Rel[Region | None] = rel(cardinality=MANY_TO_ONE, join=("region_id", "id"))

    models = DomainModel(Region, Site, Depot)
    assert models.entity(Depot).declared.relationships[0].identity.name == "region"


def test_a_failed_realization_leaves_its_classes_composable() -> None:
    class Node(Entity, table="node"):
        id: Attr[int] = attr(primary_key=True)

    class Edge(Entity, table="edge"):
        id: Attr[int] = attr(primary_key=True)
        node_id: Attr[int]
        node: Rel[Node | None] = rel(cardinality=MANY_TO_ONE, join=("node_id", "id"))

    with raises_code(UsageError, "entity-relationship-annotation-mismatch"):
        DomainModel(Node, Edge)

    models = DomainModel(Node)
    assert models.entity(Node).identity.name == "Node"


def test_one_class_composes_into_any_number_of_models() -> None:
    class Region(Entity, table="region"):
        id: Attr[int] = attr(primary_key=True)

    class Site(Entity, table="site"):
        id: Attr[int] = attr(primary_key=True)
        region_id: Attr[int]
        region: Rel[Region] = rel(cardinality=MANY_TO_ONE, join=("region_id", "id"))

    narrow = DomainModel(Region)
    wide = DomainModel(Region, Site)

    assert narrow.entity(Region).identity == wide.entity(Region).identity
    assert [entity.identity.name for entity in narrow.entities] == ["Region"]
    assert [entity.identity.name for entity in wide.entities] == ["Region", "Site"]


def test_reusable_value_object_definitions_survive_successful_and_failed_formations() -> None:
    first = DomainModel(_ReusableFirst)
    with pytest.raises(MetamodelValidationError):
        DomainModel(_ReusableBrokenFirst, _ReusableBrokenSecond)
    second = DomainModel(_ReusableSecond)
    first_occurrence = first.entity(_ReusableFirst).declared.value_object("point")
    second_occurrence = second.entity(_ReusableSecond).declared.value_object("location")
    assert first_occurrence is not None
    assert second_occurrence is not None
    assert first_occurrence.document_shape is second_occurrence.document_shape
    assert first_occurrence.attributes[0].definition is second_occurrence.attributes[0].definition


def test_an_entity_class_the_model_did_not_compose_names_no_entity_of_it() -> None:
    class Composed(Entity, table="composed"):
        id: Attr[int] = attr(primary_key=True)

    class Absent(Entity, table="absent"):
        id: Attr[int] = attr(primary_key=True)

    models = DomainModel(Composed)
    with raises_code(UsageError, "metamodel-entity-not-found"):
        models.entity(Absent)


def test_a_partial_family_publishes_a_narrower_effective_concrete_set() -> None:
    # The intended per-model semantics rather than a defect: an Entity's
    # effective concrete-subtype set is a fact of the model that composed it, so
    # the same root legitimately answers different sets in two models.
    class Animal(
        Entity, table="animal", inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind"))
    ):
        id: Attr[int] = attr(primary_key=True)

    class Dog(Animal, inheritance=ConcreteSubtype(tag_value="dog")):
        pass

    class Cat(Animal, inheritance=ConcreteSubtype(tag_value="cat")):
        pass

    dogs_only = DomainModel(Animal, Dog)
    both = DomainModel(Animal, Dog, Cat)

    assert _concretes(dogs_only, Animal) == ("Dog",)
    assert _concretes(both, Animal) == ("Cat", "Dog")


def _concretes(models: DomainModel, root: type) -> tuple[str, ...]:
    position = inheritance_facet_of(model_of(models)).entity(models.entity(root).identity)
    assert position is not None
    return tuple(identity.name for identity in position.concrete_subtypes)
