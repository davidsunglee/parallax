"""``MetamodelHub`` construction: argument validation, formation, and realization.

Every class here is declared inside its test. A successful construction claims
its classes permanently, so a module-level model would make the suite's
constructions interfere with each other — fresh class objects are the isolation
mechanism the design prescribes.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_ONE,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Entity,
    EntityDefinitionError,
    MetamodelDefinitionError,
    MetamodelHub,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    ValueObject,
    attr,
    rel,
)
from parallax.core.entity import METAMODEL_DEFINITION_CODES
from parallax.core.model_formation import MetamodelValidationError

pytestmark = pytest.mark.unit

_SPEC_CODES = frozenset(
    {"metamodel-empty", "metamodel-invalid-entity-class", "metamodel-duplicate-entity-class"}
)


def _value_object_class() -> type:
    class Point(ValueObject):
        x: Attr[int]

    return Point


def test_a_hub_over_no_source_is_empty_with_no_argument_index() -> None:
    with pytest.raises(MetamodelDefinitionError) as caught:
        MetamodelHub()
    assert caught.value.code == "metamodel-empty"
    assert caught.value.index is None


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

    with pytest.raises(MetamodelDefinitionError) as caught:
        MetamodelHub(Widget, make_argument())  # pyright: ignore[reportArgumentType]
    assert caught.value.code == "metamodel-invalid-entity-class"
    assert caught.value.index == 1


def test_a_repeated_class_object_is_rejected_at_its_own_index() -> None:
    class Gadget(Entity, table="gadget"):
        id: Attr[int] = attr(primary_key=True)

    class Doodad(Entity, table="doodad"):
        id: Attr[int] = attr(primary_key=True)

    with pytest.raises(MetamodelDefinitionError) as caught:
        MetamodelHub(Gadget, Doodad, Gadget)
    assert caught.value.code == "metamodel-duplicate-entity-class"
    assert caught.value.index == 2


def test_arguments_are_checked_left_to_right() -> None:
    class Sprocket(Entity, table="sprocket"):
        id: Attr[int] = attr(primary_key=True)

    # Argument 1 is invalid and argument 2 repeats argument 0; the leftmost
    # defect is the one reported.
    with pytest.raises(MetamodelDefinitionError) as caught:
        MetamodelHub(Sprocket, object(), Sprocket)  # pyright: ignore[reportArgumentType]
    assert (caught.value.code, caught.value.index) == ("metamodel-invalid-entity-class", 1)


def test_the_definition_code_set_is_closed() -> None:
    assert METAMODEL_DEFINITION_CODES == _SPEC_CODES
    with pytest.raises(ValueError, match="not a metamodel definition code"):
        MetamodelDefinitionError(code="metamodel-made-up", message="nope")


def test_two_distinct_classes_sharing_one_identity_reach_whole_model_validation() -> None:
    class First(Entity, table="first", name="Shared"):
        id: Attr[int] = attr(primary_key=True)

    class Second(Entity, table="second", name="Shared"):
        id: Attr[int] = attr(primary_key=True)

    with pytest.raises(MetamodelValidationError) as caught:
        MetamodelHub(First, Second)
    assert [issue.code for issue in caught.value.issues] == ["metamodel-duplicate-entity-identity"]


def test_a_target_outside_the_candidate_set_is_a_model_defect() -> None:
    class Elsewhere(Entity, table="elsewhere"):
        id: Attr[int] = attr(primary_key=True)

    class Dangling(Entity, table="dangling"):
        id: Attr[int] = attr(primary_key=True)
        elsewhere_id: Attr[int]
        elsewhere: Rel[Elsewhere] = rel(cardinality=MANY_TO_ONE, join=("elsewhere_id", "id"))

    # `Elsewhere` exists as a class but is not composed into this hub, and
    # resolution is confined to the candidate set.
    with pytest.raises(MetamodelValidationError) as caught:
        MetamodelHub(Dangling)
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

    with pytest.raises(EntityDefinitionError) as caught:
        MetamodelHub(Order, Customer, Coupon)
    assert caught.value.code == "entity-relationship-annotation-mismatch"
    reported = [line.strip() for line in caught.value.message.splitlines()[1:]]
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

    with pytest.raises(EntityDefinitionError) as caught:
        MetamodelHub(Shelf, Book)
    assert caught.value.code == "entity-relationship-annotation-mismatch"
    reported = [line.strip() for line in caught.value.message.splitlines()[1:]]
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

    models = MetamodelHub(Order, Customer, Coupon, Profile)
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

    models = MetamodelHub(Region, Site, Depot)
    assert models.meta(Depot).declared_relationships[0].identity.name == "region"


def test_a_failed_realization_publishes_no_binding() -> None:
    class Node(Entity, table="node"):
        id: Attr[int] = attr(primary_key=True)

    class Edge(Entity, table="edge"):
        id: Attr[int] = attr(primary_key=True)
        node_id: Attr[int]
        node: Rel[Node | None] = rel(cardinality=MANY_TO_ONE, join=("node_id", "id"))

    with pytest.raises(EntityDefinitionError):
        MetamodelHub(Node, Edge)

    # Realization raised before the claim, so `Node` was never bound and a
    # corrected hub still owns it.
    models = MetamodelHub(Node)
    assert models.meta(Node).identity.name == "Node"
