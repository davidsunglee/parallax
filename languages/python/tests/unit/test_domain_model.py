"""``DomainModel`` construction: argument validation, formation, and realization.

Each test declares the classes its own scenario needs, so a failure names the
declaration it is about. Nothing here isolates one construction from another:
composing a class into a model binds nothing, so the same class is free to
appear in as many models as any test cares to build.
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
    DomainModel,
    Entity,
    EntityDefinitionError,
    MetamodelDefinitionError,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    ValueObject,
    attr,
    rel,
)
from parallax.core.entity import METAMODEL_DEFINITION_CODES, MetamodelLookupError
from parallax.core.entity._model import class_index, model_of
from parallax.core.inheritance import view as inheritance_view
from parallax.core.model_formation import MetamodelValidationError

_SPEC_CODES = frozenset(
    {"metamodel-empty", "metamodel-invalid-entity-class", "metamodel-duplicate-entity-class"}
)


def _value_object_class() -> type:
    class Point(ValueObject):
        x: Attr[int]

    return Point


def test_a_model_over_no_source_is_empty_with_no_argument_index() -> None:
    with pytest.raises(MetamodelDefinitionError) as caught:
        DomainModel()
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
        DomainModel(Widget, make_argument())  # pyright: ignore[reportArgumentType] - deliberate non-Entity-Class argument drives constructor validation
    assert caught.value.code == "metamodel-invalid-entity-class"
    assert caught.value.index == 1


def test_a_repeated_class_object_is_rejected_at_its_own_index() -> None:
    class Gadget(Entity, table="gadget"):
        id: Attr[int] = attr(primary_key=True)

    class Doodad(Entity, table="doodad"):
        id: Attr[int] = attr(primary_key=True)

    with pytest.raises(MetamodelDefinitionError) as caught:
        DomainModel(Gadget, Doodad, Gadget)
    assert caught.value.code == "metamodel-duplicate-entity-class"
    assert caught.value.index == 2


def test_arguments_are_checked_left_to_right() -> None:
    class Sprocket(Entity, table="sprocket"):
        id: Attr[int] = attr(primary_key=True)

    # Argument 1 is invalid and argument 2 repeats argument 0; the leftmost
    # defect is the one reported.
    with pytest.raises(MetamodelDefinitionError) as caught:
        DomainModel(Sprocket, object(), Sprocket)  # pyright: ignore[reportArgumentType] - deliberate non-Entity-Class argument drives constructor validation
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
        DomainModel(First, Second)
    assert [issue.code for issue in caught.value.issues] == ["metamodel-duplicate-entity-identity"]


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

    with pytest.raises(EntityDefinitionError) as caught:
        DomainModel(Order, Customer, Coupon)
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
        DomainModel(Shelf, Book)
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
    assert models.meta(Depot).declared_relationships[0].identity.name == "region"


def test_a_failed_realization_leaves_its_classes_composable() -> None:
    class Node(Entity, table="node"):
        id: Attr[int] = attr(primary_key=True)

    class Edge(Entity, table="edge"):
        id: Attr[int] = attr(primary_key=True)
        node_id: Attr[int]
        node: Rel[Node | None] = rel(cardinality=MANY_TO_ONE, join=("node_id", "id"))

    with pytest.raises(EntityDefinitionError):
        DomainModel(Node, Edge)

    models = DomainModel(Node)
    assert models.meta(Node).identity.name == "Node"


def test_one_class_composes_into_any_number_of_models() -> None:
    class Region(Entity, table="region"):
        id: Attr[int] = attr(primary_key=True)

    class Site(Entity, table="site"):
        id: Attr[int] = attr(primary_key=True)
        region_id: Attr[int]
        region: Rel[Region] = rel(cardinality=MANY_TO_ONE, join=("region_id", "id"))

    narrow = DomainModel(Region)
    wide = DomainModel(Region, Site)

    assert narrow.meta(Region).identity == wide.meta(Region).identity
    assert [entity.identity.name for entity in narrow.entities] == ["Region"]
    assert [entity.identity.name for entity in wide.entities] == ["Region", "Site"]


def test_an_entity_class_the_model_did_not_compose_names_no_entity_of_it() -> None:
    class Composed(Entity, table="composed"):
        id: Attr[int] = attr(primary_key=True)

    class Absent(Entity, table="absent"):
        id: Attr[int] = attr(primary_key=True)

    models = DomainModel(Composed)
    with pytest.raises(MetamodelLookupError) as caught:
        models.meta(Absent)
    assert caught.value.code == "metamodel-entity-not-found"


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
    position = inheritance_view(model_of(models)).entity(models.meta(root).identity)
    assert position is not None
    return tuple(identity.name for identity in position.concrete_subtypes)


def test_a_class_backed_model_indexes_every_class_it_composed_both_ways() -> None:
    class Widget(Entity, table="widget"):
        id: Attr[int] = attr(primary_key=True)

    models = DomainModel(Widget)
    index = class_index(models)
    assert index is not None
    identity = index.identity_of(Widget)
    assert identity is not None
    assert index.class_of(identity) is Widget
