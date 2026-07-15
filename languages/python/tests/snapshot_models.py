"""Idiomatic entity classes for the frozen-node wrapping / statement-include /
narrowed-view unit tests (COR-3 Phase 7 increment 6a).

Shaped after ``models/orders.yaml`` (relationships, deep-fetch paths) and
``models/animal.yaml`` (table-per-hierarchy inheritance, a polymorphic owner,
narrowed views) closely enough to drive ``parallax.snapshot.wrap`` against
corpus-shaped rows, but under class names distinct from the corpus's own
(``SnapOrder`` / ``AnimalOwner`` rather than ``Order`` / ``Person``) — the
class registry is a single GLOBAL process-wide namespace
(``parallax.core.entity.entity_registry()``), and
``parallax.conformance.story_models.Order`` / ``mirrored_models.Person``
already claim those names for their own no-drift guards. Assembled into a
self-contained :class:`~parallax.core.descriptor.Metamodel` via
``parallax.core.entity.metamodel(...)`` rather than corpus YAML ingestion, so
these tests never depend on (or collide with) any other module's registered
classes. This module deliberately avoids ``from __future__ import annotations``
so the metaclass reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.

Lives at the top level of ``tests/`` (moved from ``tests/unit/`` in increment
6b): ``Animal``/``Pet``/``Dog``/``Cat``/``WildBoar`` (declared with their real
corpus names, unlike the renamed ``SnapOrder``/``AnimalOwner`` siblings) are
reused by the API Conformance Suite's animal-family inheritance/narrow examples
that never reference the polymorphic owner. Reaching the owner side
(``models/animal.yaml``'s own ``Person``) is NOT reproducible from the suite
today: it would collide with ``mirrored_models.Person`` (``models/person.yaml``)
in the same shared registry, so the owner-relationship cases stay
case-scoped-skipped (`api_suite.CASE_SKIP_REASONS`) rather than silently
mis-resolving whichever "Person" a dict happened to keep.
"""

import datetime as dt
from decimal import Decimal

from parallax.core import Attr, Entity, EntityConfig, Field, Rel, Relationship
from parallax.core.entity.base import Concrete, FamilyRoot
from parallax.core.entity.value_object import ValueObject, VoField

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


class Animal(Entity, frozen=True):
    __parallax__ = EntityConfig(
        namespace=_NS,
        mutability="transactional",
        inheritance=FamilyRoot(strategy="table-per-hierarchy", tag="kind"),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=32)
    owner_id: Attr[int | None] = Field(type="int64", column="owner_id", nullable=True, default=None)


class Pet(Animal, frozen=True):
    license_id: Attr[str | None] = Field(
        type="string", max_length=16, column="license_id", nullable=True, default=None
    )


class Dog(Pet, frozen=True):
    __parallax__ = EntityConfig(inheritance=Concrete(tag_value="dog"))

    bark_volume: Attr[int | None] = Field(
        type="int32", column="bark_volume", nullable=True, default=None
    )


class Cat(Pet, frozen=True):
    __parallax__ = EntityConfig(inheritance=Concrete(tag_value="cat"))

    indoor: Attr[bool | None] = Field(type="boolean", column="indoor", nullable=True, default=None)


class WildBoar(Animal, frozen=True):
    __parallax__ = EntityConfig(inheritance=Concrete(tag_value="boar"))

    tusk_length: Attr[Decimal | None] = Field(
        type="decimal(18,2)", column="tusk_length", nullable=True, default=None
    )


class AnimalOwner(Entity, frozen=True):
    """The animal family's polymorphic owner (``models/animal.yaml``'s
    ``Person`` entity, renamed here to avoid the global class-registry
    collision with ``mirrored_models.Person``, a different corpus model)."""

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
