"""What the suites grading a deep Include path share: one scripted five-level read,
and one family whose continuations only their declarations can spell.

``Order.items.statuses.order.items`` crosses no back-reference, so it executes to
its leaf: order 1 reaches order 2 through a status, and order 2's own items are the
terminal level. Item 12 keeps a loaded-empty ``statuses``, so every read of it
states an ending as well as a leaf.

The family renames ``Animal.toys`` to ``playthings`` and ``Animal.vet`` to
``attendingVet``, declares both on the abstract root a concrete inherits them from,
and gives two siblings an identically named relationship of their own.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Final, cast

import pytest

from parallax.conformance.story_models import Order
from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Rel,
    TablePerHierarchy,
    attr,
    rel,
)
from parallax.core.object_query._fluent import ObjectQuery
from tests._support.db_port import Read

__all__ = [
    "BACK_REFERENCE_READS",
    "DEEP_READS",
    "FAMILY",
    "FAMILY_NS",
    "LEAF_ITEMS",
    "Animal",
    "Bell",
    "Cat",
    "Collar",
    "Dog",
    "Keeper",
    "Maker",
    "Toy",
    "back_reference_query",
    "deep_order_query",
    "deep_order_reads",
    "family_reads",
    "item_row",
    "order_row",
    "status_row",
    "typed_leaf_items",
    "wire_leaf_items",
]

FAMILY_NS: Final = "parallax.tests.deep"
LEAF_ITEMS: Final = [31, 32]


class Maker(Entity, table="deep_maker", namespace=FAMILY_NS):
    id: Attr[int] = attr(primary_key=True)


class Toy(Entity, table="deep_toy", namespace=FAMILY_NS):
    id: Attr[int] = attr(primary_key=True)
    animal_id: Attr[int]
    maker_id: Attr[int | None]
    maker: Rel[Maker | None] = rel(cardinality=MANY_TO_ONE, join=("maker_id", "id"))


class Collar(Entity, table="deep_collar", namespace=FAMILY_NS):
    id: Attr[int] = attr(primary_key=True)
    dog_id: Attr[int]


class Bell(Entity, table="deep_bell", namespace=FAMILY_NS):
    id: Attr[int] = attr(primary_key=True)
    cat_id: Attr[int]


class Animal(
    Entity,
    table="deep_animal",
    namespace=FAMILY_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    keeper_id: Attr[int | None]
    vet_id: Attr[int | None]
    keeper: Rel[Keeper | None] = rel(reverse_of="animals")
    toys: Rel[tuple[Toy, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "animal_id"), name="playthings"
    )
    vet: Rel[Maker | None] = rel(
        cardinality=MANY_TO_ONE, join=("vet_id", "id"), name="attendingVet"
    )


class Dog(Animal, namespace=FAMILY_NS, inheritance=ConcreteSubtype(tag_value="dog")):
    gear: Rel[tuple[Collar, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "dog_id"))


class Cat(Animal, namespace=FAMILY_NS, inheritance=ConcreteSubtype(tag_value="cat")):
    gear: Rel[tuple[Bell, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "cat_id"))


class Keeper(Entity, table="deep_keeper", namespace=FAMILY_NS):
    id: Attr[int] = attr(primary_key=True)
    animals: Rel[tuple[Animal, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "keeper_id"))


FAMILY: Final = DomainModel(Keeper, Animal, Dog, Cat, Toy, Maker, Collar, Bell)


def family_reads() -> tuple[Read, ...]:
    """Keeper 1's ``animals.toys.maker``: a Dog whose toys reach a maker and a null,
    and a Cat with loaded-empty toys."""
    return (
        Read(rows=[{"id": 1}]),
        Read(
            rows=[
                {"id": 2, "kind": "dog", "keeper_id": 1, "vet_id": None},
                {"id": 3, "kind": "cat", "keeper_id": 1, "vet_id": None},
            ]
        ),
        Read(
            rows=[
                {"id": 10, "animal_id": 2, "maker_id": 100},
                {"id": 11, "animal_id": 2, "maker_id": None},
            ]
        ),
        Read(rows=[{"id": 100}]),
    )


def order_row(order_id: int) -> dict[str, object]:
    return {
        "id": order_id,
        "name": f"order-{order_id}",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
    }


def item_row(item_id: int, order_id: int) -> dict[str, object]:
    return {
        "id": item_id,
        "order_id": order_id,
        "sku": "SKU",
        "quantity": 1,
        "shipped_on": dt.date(2024, 2, 1),
    }


def status_row(status_id: int, order_id: int, item_id: int) -> dict[str, object]:
    return {"id": status_id, "order_id": order_id, "order_item_id": item_id, "code": "NEW"}


def deep_order_query() -> ObjectQuery[Order, Order]:
    return Order.where(Order.id == 1).include(Order.items.statuses.order.items)


def back_reference_query() -> ObjectQuery[Order, Order]:
    """``OrderItem.order`` inverts the ``Order.items`` hop it arrives over, so the
    path continues past a back-reference level."""
    return Order.where(Order.id == 1).include(Order.items.order.items)


def deep_order_reads() -> tuple[Read, ...]:
    """The five statements :func:`deep_order_query` issues, one per level."""
    return (
        Read(rows=[order_row(1)]),
        Read(rows=[item_row(11, 1), item_row(12, 1)]),
        Read(rows=[status_row(21, 2, 11)]),
        Read(rows=[order_row(2)]),
        Read(rows=[item_row(31, 2), item_row(32, 2)]),
    )


def typed_leaf_items(order: Any) -> list[int]:
    """The terminal item ids a Typed root reached, having read each loaded ending."""
    first, second = order.items
    assert second.statuses == ()
    (status,) = first.statuses
    return [item.id for item in status.order.items]


def wire_leaf_items(order: Any) -> list[int]:
    """The terminal item ids a Wire root reached, having read each loaded ending."""
    first, second = order["items"]
    assert second["statuses"] == []
    (status,) = first["statuses"]
    return [cast("int", item["id"]) for item in status["order"]["items"]]


def _found(reader: Any) -> Any:
    return reader.find(deep_order_query()).result()


def _wire_found(reader: Any) -> Any:
    return reader.wire.find(deep_order_query()).result()


def _sole_streamed(stream: Any) -> Any:
    with stream:
        (root,) = list(stream)
    return root


def _streamed(reader: Any) -> Any:
    return _sole_streamed(reader.stream(deep_order_query(), batch_size=10))


def _wire_streamed(reader: Any) -> Any:
    return _sole_streamed(reader.wire.stream(deep_order_query(), batch_size=10))


DEEP_READS: Final = [
    pytest.param(_found, typed_leaf_items, id="find"),
    pytest.param(_wire_found, wire_leaf_items, id="wire-find"),
    pytest.param(_streamed, typed_leaf_items, id="stream"),
    pytest.param(_wire_streamed, wire_leaf_items, id="wire-stream"),
]
"""Each read a database or a transaction offers, beside the leaf reader its result
form takes."""


def _back_reference_found(reader: Any) -> object:
    return reader.find(back_reference_query())


def _back_reference_wire_found(reader: Any) -> object:
    return reader.wire.find(back_reference_query())


def _back_reference_streamed(reader: Any) -> object:
    with reader.stream(back_reference_query()) as stream:
        return list(stream)


def _back_reference_wire_streamed(reader: Any) -> object:
    with reader.wire.stream(back_reference_query()) as stream:
        return list(stream)


BACK_REFERENCE_READS: Final = [
    pytest.param(_back_reference_found, id="find"),
    pytest.param(_back_reference_wire_found, id="wire-find"),
    pytest.param(_back_reference_streamed, id="stream"),
    pytest.param(_back_reference_wire_streamed, id="wire-stream"),
]
"""Each read a database or a transaction offers, over a path that continues past a
back-reference."""
