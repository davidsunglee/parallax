"""Idiomatic entity classes for the frozen-node wrapping / statement-include /
narrowed-view unit tests (COR-3 Phase 7 increment 6a).

Shaped after ``models/orders.yaml`` (relationships, deep-fetch paths) and
``models/animal.yaml`` (table-per-hierarchy inheritance, a polymorphic owner,
narrowed views) closely enough to drive ``parallax.snapshot.wrap`` against
corpus-shaped rows, but ``SnapOrder``/``SnapOrderItem``/``SnapOrderStatus``
stay under class names distinct from the corpus's own ``Order``/``OrderItem``/
``OrderStatus`` (``parallax.conformance.story_models`` already claims those
names for its own no-drift guard). Assembled into a self-contained
:class:`~parallax.core.descriptor.Metamodel` via
``parallax.core.entity.metamodel(...)`` rather than corpus YAML ingestion.
This module deliberately avoids ``from __future__ import annotations`` so the
metaclass reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.

Lives at the top level of ``tests/`` (moved from ``tests/unit/`` in increment
6b): ``Animal``/``Pet``/``Dog``/``Cat``/``WildBoar`` (declared with their real
corpus names) are **re-exported** from ``parallax.conformance.read_models``
(the installed package's own mirror, which the API Conformance Suite's
real-database read stories execute against `db.find`), so the unit lane's
frontend/wrap tests here and the API-suite's execution both resolve the exact
SAME registered class rather than a second, differently-scoped copy racing it
in the same registry.

``AnimalOwner`` stays LOCAL and distinctly named — deliberately, not out of
necessity: before ledger D-20 (COR-3 Phase 8 increment 7) the animal family's
real owner (``models/animal.yaml``'s own ``Person``) could not coexist with
``read_models.Person`` (``models/person.yaml``) in the single, global,
process-wide entity registry, so this module renamed its OWN owner fixture to
sidestep the collision entirely. D-20's explicit
:class:`~parallax.core.entity.base.EntityRegistry` scoping now lets the two
coexist (the REAL, production-reachable animal-family owner is installed as
`parallax.conformance.animal_owner.Person`, scoped to its own registry, and
drives the owner-relationship stories for real) — but ``AnimalOwner`` here
tests `parallax.snapshot.wrap`'s narrowed-view / closed-world MECHANICS in the
unit lane and needs no corpus-exact name to do that, so it stays as its own
structural fixture rather than becoming a third alias for the same class.
"""

import datetime as dt
from decimal import Decimal

from parallax.conformance.read_models import Animal, Cat, Dog, Pet, WildBoar
from parallax.core import Attr, Entity, EntityConfig, Field, Rel, Relationship
from parallax.core.entity.value_object import ValueObject, VoField

__all__ = [
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


class Detail(ValueObject, frozen=True):
    note: Attr[str] = VoField(type="string")


class Tag(ValueObject, frozen=True):
    label: Attr[str] = VoField(type="string")
    detail: Attr[Detail | None] = VoField(nullable=True, default=None)
    details: Attr[tuple[Detail, ...]] = VoField(nullable=True, default=())


class SnapOrder(Entity, frozen=True):
    __parallax__ = EntityConfig(table="snap_orders", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=255)
    sku: Attr[str | None] = Field(type="string", max_length=32, nullable=True, default=None)
    qty: Attr[int] = Field(type="int32")
    price: Attr[Decimal] = Field(type="decimal(18,2)")
    active: Attr[bool] = Field(default=False)
    ordered_on: Attr[dt.date] = Field(column="ordered_on")
    items: Rel[tuple["SnapOrderItem", ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = SnapOrderItem.orderId",
        related_entity="SnapOrderItem",
        reverse_name="order",
        dependent=True,
        foreign_key="order_id",
    )
    statuses: Rel[tuple["SnapOrderStatus", ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = SnapOrderStatus.orderId",
        related_entity="SnapOrderStatus",
        reverse_name="order",
        dependent=True,
        foreign_key="order_id",
    )


class SnapOrderItem(Entity, frozen=True):
    __parallax__ = EntityConfig(table="snap_order_item", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    order_id: Attr[int] = Field(column="order_id", type="int64")
    sku: Attr[str] = Field(max_length=32)
    quantity: Attr[int] = Field(type="int32")
    shipped_on: Attr[dt.date | None] = Field(
        type="date", column="shipped_on", nullable=True, default=None
    )
    order: Rel["SnapOrder"] = Relationship(
        cardinality="many-to-one",
        join="this.orderId = SnapOrder.id",
        related_entity="SnapOrder",
        reverse_name="items",
        foreign_key="order_id",
    )
    statuses: Rel[tuple["SnapOrderStatus", ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = SnapOrderStatus.orderItemId",
        related_entity="SnapOrderStatus",
        reverse_name="orderItem",
        dependent=True,
        foreign_key="order_item_id",
    )


class SnapOrderStatus(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="snap_order_status", namespace=_NS, mutability="transactional"
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    order_id: Attr[int] = Field(column="order_id", type="int64")
    order_item_id: Attr[int | None] = Field(
        type="int64", column="order_item_id", nullable=True, default=None
    )
    code: Attr[str] = Field(max_length=16)
    primary_tag: Attr[Tag | None] = Field(nullable=True, default=None)
    tags: Attr[tuple[Tag, ...]] = Field(nullable=True, default=())


class AnimalOwner(Entity, frozen=True):
    """A LOCAL structural fixture for ``parallax.snapshot.wrap``'s narrowed-
    view / closed-world unit tests: the animal family's polymorphic-owner
    SHAPE (``models/animal.yaml``'s own ``Person`` entity), under a distinct
    name by choice, not necessity (see module docstring) — the REAL,
    production-reachable owner is `parallax.conformance.animal_owner.Person`."""

    __parallax__ = EntityConfig(table="person", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=32)
    animals: Rel[tuple["Animal", ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = Animal.ownerId",
        related_entity="Animal",
        reverse_name="owner",
        foreign_key="owner_id",
    )
    pets: Rel[tuple["Pet", ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = Pet.ownerId",
        related_entity="Pet",
        reverse_name="owner",
        foreign_key="owner_id",
    )
