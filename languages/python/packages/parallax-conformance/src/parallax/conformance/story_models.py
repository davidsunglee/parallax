"""Idiomatic entity classes the API-suite stories construct instances of.

Mirrors ``models/account.yaml`` and the FULL ``models/orders.yaml`` family
(``Order`` / ``OrderItem`` / ``OrderStatus`` / ``OrderTag``, every declared
relationship included). Owned by ``parallax.conformance`` (not the
test-suite's own ``mirrored_models``, which lives under ``tests/`` and is
unreachable from an installed ``parallax-conformance`` distribution) since
``stories.py`` / ``graph_stories.py`` — real dev-only package modules,
exercised by the fake-port write no-drift guard and the real-Postgres
story-run suite alike — need classes resolvable at ordinary import time, not
only under pytest's test-path magic.

``Order`` / ``OrderItem`` started (M4) as the write stories' scalar-only
surface; COR-3 Phase 7 increment 6b widens them to the family's full
relationship set (plus the two sibling entities orders.yaml itself declares,
``OrderStatus`` / ``OrderTag``) so the SAME classes also serve the API
Conformance Suite's navigate / deep-fetch / snapshot-graph examples and
stories — one "Order" per process (the entity class registry is a single
global namespace keyed by canonical name), never a second, differently-scoped
mirror racing it. This module deliberately avoids
``from __future__ import annotations`` so the metaclass reads the live
``Attr[T]`` objects and infers each attribute's neutral type from ``T``.
"""

import datetime as dt
from decimal import Decimal

from parallax.core import (
    Attr,
    Bitemporal,
    Entity,
    EntityConfig,
    Field,
    OrderByTerm,
    Rel,
    Relationship,
    RelationshipJoin,
    RelationshipTarget,
    ReverseRelationship,
)

_NS = "parallax.compatibility"

__all__ = ["Account", "Order", "OrderItem", "OrderStatus", "OrderTag", "Position", "Wallet"]


class Account(Entity, frozen=True):
    """Mirror of ``models/account.yaml``."""

    __parallax__ = EntityConfig(table="account", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none")
    owner: Attr[str] = Field(max_length=64)
    balance: Attr[Decimal] = Field(type="decimal(18,2)")
    version: Attr[int] = Field(type="int32", optimistic_locking=True)


class Wallet(Entity, frozen=True):
    """Mirror of ``models/wallet.yaml``: Account minus the optimistic-lock
    ``version`` column and no temporal axis — the readless set-based write
    family's own witness (``m-batch-write-005``, COR-3 Phase 8 increment 7
    completion round): a predicate write over an unversioned, non-temporal
    entity has nothing to gate per row, so it lowers to ONE predicate-shaped
    statement, no materializing read."""

    __parallax__ = EntityConfig(table="wallet", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none")
    owner: Attr[str] = Field(max_length=64)
    balance: Attr[Decimal] = Field(type="decimal(18,2)")


class Position(Bitemporal, frozen=True):
    """Mirror of ``models/position.yaml`` (full bitemporal): the write-family
    stories' own bitemporal-insert / ``insertUntil`` / ``updateUntil`` witness
    (``m-bitemp-write-001/-003``). Every axis-governed attribute
    (``valid_start``/``valid_end``/``tx_start``/``tx_end``) is optional at
    construction: a fresh instance names only its payload, and the
    write path stamps the rest."""

    __parallax__ = EntityConfig(table="position", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", column="pos_id", type="int64")
    acct_num: Attr[str] = Field(max_length=32, column="acct_num")
    value: Attr[Decimal] = Field(type="decimal(18,2)", column="val")


class Order(Entity, frozen=True):
    """Mirror of the ``Order`` entity of ``models/orders.yaml`` (the full
    relationship set: to-many ``items``/``statuses``/``tags`` plus the
    alternate-ordering ``itemsByShipDate`` path over the same join)."""

    __parallax__ = EntityConfig(table="orders", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=255)
    sku: Attr[str | None] = Field(type="string", max_length=32, nullable=True, default=None)
    qty: Attr[int] = Field(type="int32")
    price: Attr[Decimal] = Field(type="decimal(18,2)")
    active: Attr[bool] = Field(default=False)
    ordered_on: Attr[dt.date] = Field(column="ordered_on")
    items: Rel[tuple["OrderItem", ...]] = Relationship(
        cardinality="one-to-many",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="OrderItem", attribute="orderId")
        ),
        dependent=True,
        order_by=[OrderByTerm(attr="id", direction="desc")],
    )
    statuses: Rel[tuple["OrderStatus", ...]] = Relationship(
        cardinality="one-to-many",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="OrderStatus", attribute="orderId")
        ),
        dependent=True,
    )
    tags: Rel[tuple["OrderTag", ...]] = Relationship(
        cardinality="one-to-many",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="OrderTag", attribute="orderId")
        ),
        order_by=[
            OrderByTerm(attr="priority", direction="desc"),
            OrderByTerm(attr="label", direction="asc"),
        ],
    )
    items_by_ship_date: Rel[tuple["OrderItem", ...]] = Relationship(
        cardinality="one-to-many",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="OrderItem", attribute="orderId")
        ),
        order_by=[OrderByTerm(attr="shippedOn", direction="asc")],
    )


class OrderItem(Entity, frozen=True):
    """Mirror of the ``OrderItem`` entity of ``models/orders.yaml`` (the
    to-one ``order`` back-reference and the item-level ``statuses`` hop)."""

    __parallax__ = EntityConfig(table="order_item", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    order_id: Attr[int] = Field(column="order_id", type="int64")
    sku: Attr[str] = Field(max_length=32)
    quantity: Attr[int] = Field(type="int32")
    shipped_on: Attr[dt.date | None] = Field(
        type="date", column="shipped_on", nullable=True, default=None
    )
    order: Rel["Order"] = ReverseRelationship(reverse_of="Order.items")
    statuses: Rel[tuple["OrderStatus", ...]] = Relationship(
        cardinality="one-to-many",
        join=RelationshipJoin(
            source="id",
            target=RelationshipTarget(entity="OrderStatus", attribute="orderItemId"),
        ),
        dependent=True,
        order_by=[OrderByTerm(attr="code", direction="asc")],
    )


class OrderStatus(Entity, frozen=True):
    """Mirror of the ``OrderStatus`` entity of ``models/orders.yaml``: each
    status belongs to an ``Order`` and OPTIONALLY to a specific ``OrderItem``
    (a nullable many-to-one — the to-one navigate/deep-fetch nullable shape)."""

    __parallax__ = EntityConfig(table="order_status", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    order_id: Attr[int] = Field(column="order_id", type="int64")
    order_item_id: Attr[int | None] = Field(
        type="int64", column="order_item_id", nullable=True, default=None
    )
    code: Attr[str] = Field(max_length=16)
    order: Rel["Order"] = ReverseRelationship(reverse_of="Order.statuses")
    order_item: Rel["OrderItem"] = ReverseRelationship(reverse_of="OrderItem.statuses")


class OrderTag(Entity, frozen=True):
    """Mirror of the ``OrderTag`` entity of ``models/orders.yaml``."""

    __parallax__ = EntityConfig(table="order_tag", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    order_id: Attr[int] = Field(column="order_id", type="int64")
    label: Attr[str] = Field(max_length=32)
    priority: Attr[int] = Field(type="int32")
    order: Rel["Order"] = ReverseRelationship(reverse_of="Order.tags")
