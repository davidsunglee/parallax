"""Idiomatic Entity Classes for the frozen-node wrapping / statement-include /
narrowed-view unit tests.

Shaped after ``models/orders.yaml`` (relationships, deep-fetch paths) and
``models/animal.yaml`` (table-per-hierarchy inheritance, a polymorphic owner,
narrowed views) closely enough to drive ``parallax.snapshot.handle._wrap``
against corpus-shaped rows, and composed into the two Domain Models those tests
connect with.

Both families are declared here rather than borrowed from
``parallax.conformance``: these are structural fixtures for the wrap mechanics,
so they carry the shapes without the corpus's own indices, and the installed
mirrors carry those indices because the no-drift guard measures them. ``SnapOrder``
and its siblings keep names distinct from the mirrors to make the two easy to
tell apart in a failure.

This module deliberately avoids ``from __future__ import annotations`` so the
engine reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

import datetime as dt
from decimal import Decimal

from parallax.core import (
    ONE_TO_MANY,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Int32,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    rel,
)

__all__ = [
    "ANIMAL_MODEL",
    "SNAP_ORDERS_MODEL",
    "Animal",
    "AnimalOwner",
    "Cat",
    "Detail",
    "Dog",
    "Pet",
    "SnapOrder",
    "SnapOrderItem",
    "SnapOrderStatus",
    "Tag",
    "WildBoar",
]

_NS = "parallax.compatibility"


class Detail(ValueObject):
    note: Attr[str]


class Tag(ValueObject):
    label: Attr[str]
    detail: Attr[Detail | None]
    details: Attr[tuple[Detail, ...]]


class SnapOrder(Entity, table="snap_orders", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=255)
    sku: Attr[str | None] = attr(max_length=32)
    qty: Attr[int] = attr(type=Int32)
    price: Attr[Decimal] = attr(precision=18, scale=2)
    active: Attr[bool]
    ordered_on: Attr[dt.date]
    items: Rel[tuple["SnapOrderItem", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "order_id"), dependent=True
    )
    statuses: Rel[tuple["SnapOrderStatus", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "order_id"), dependent=True
    )


class SnapOrderItem(Entity, table="snap_order_item", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    sku: Attr[str] = attr(max_length=32)
    quantity: Attr[int] = attr(type=Int32)
    shipped_on: Attr[dt.date | None]
    order: Rel[SnapOrder | None] = rel(reverse_of="items")
    statuses: Rel[tuple["SnapOrderStatus", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "order_item_id"), dependent=True
    )


class SnapOrderStatus(Entity, table="snap_order_status", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    order_item_id: Attr[int | None]
    code: Attr[str] = attr(max_length=16)
    primary_tag: Attr[Tag | None]
    # A `many` occurrence is a possibly-empty collection and is never nullable
    # (m-value-object); a NULL document column still wraps to an empty tuple.
    tags: Attr[tuple[Tag, ...]]


SNAP_ORDERS_MODEL = DomainModel(SnapOrder, SnapOrderItem, SnapOrderStatus)


class Animal(
    Entity,
    table="animal",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    owner_id: Attr[int | None]


class Pet(Animal, namespace=_NS, inheritance=AbstractSubtype):
    license_id: Attr[str | None] = attr(max_length=16)


class Dog(Pet, namespace=_NS, inheritance=ConcreteSubtype(tag_value="dog")):
    bark_volume: Attr[int | None] = attr(type=Int32)


class Cat(Pet, namespace=_NS, inheritance=ConcreteSubtype(tag_value="cat")):
    indoor: Attr[bool | None]


class WildBoar(Animal, namespace=_NS, inheritance=ConcreteSubtype(tag_value="boar")):
    tusk_length: Attr[Decimal | None] = attr(precision=18, scale=2)


class AnimalOwner(Entity, table="person", namespace=_NS):
    """The animal family's polymorphic-owner SHAPE (``models/animal.yaml``'s own
    ``Person`` entity) under a distinct name, so a wrap failure names the
    fixture rather than the installed mirror."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    animals: Rel[tuple[Animal, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))
    pets: Rel[tuple[Pet, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))


ANIMAL_MODEL = DomainModel(Animal, Pet, Dog, Cat, WildBoar, AnimalOwner)
