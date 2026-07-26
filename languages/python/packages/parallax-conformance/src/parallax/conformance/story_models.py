"""Idiomatic Entity Classes the API-suite stories construct instances of.

Mirrors ``models/account.yaml``, ``models/wallet.yaml``, ``models/position.yaml``
and the FULL ``models/orders.yaml`` family (``Order`` / ``OrderItem`` /
``OrderStatus`` / ``OrderTag``, every declared relationship included), each
composed into the sealed hub named for its corpus model. ``Order`` / ``OrderItem``
carry the family's full relationship set so the SAME classes serve the API
Conformance Suite's navigate / deep-fetch / snapshot-graph examples and stories.

Owned by ``parallax.conformance`` (not the test suite's own ``mirrored_models``,
which lives under ``tests/`` and is unreachable from an installed
``parallax-conformance`` distribution) since ``stories.py`` / ``graph_stories.py``
— real dev-only package modules, exercised by the fake-port write no-drift guard
and the real-Postgres story-run suite alike — need classes resolvable at ordinary
import time, not only under pytest's test-path magic.

This module deliberately avoids ``from __future__ import annotations`` so the
engine reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

import datetime as dt
from decimal import Decimal

from parallax.core import (
    ONE_TO_MANY,
    Attr,
    Bitemporal,
    Entity,
    Int32,
    MetamodelHub,
    Rel,
    attr,
    desc,
    index,
    rel,
)

_NS = "parallax.compatibility"

__all__ = [
    "ACCOUNT_MODEL",
    "ORDERS_MODEL",
    "POSITION_MODEL",
    "WALLET_MODEL",
    "Account",
    "Order",
    "OrderItem",
    "OrderStatus",
    "OrderTag",
    "Position",
    "Wallet",
]


class Account(
    Entity,
    table="account",
    namespace=_NS,
    indices=(index("account_pk", "id", unique=True), index("account_owner", "owner")),
):
    """Mirror of ``models/account.yaml``."""

    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str] = attr(max_length=64)
    balance: Attr[Decimal] = attr(precision=18, scale=2)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


ACCOUNT_MODEL = MetamodelHub(Account)


class Wallet(
    Entity,
    table="wallet",
    namespace=_NS,
    indices=(index("wallet_pk", "id", unique=True), index("wallet_owner", "owner")),
):
    """Mirror of ``models/wallet.yaml``: Account minus the optimistic-lock
    ``version`` column and no temporal axis — the readless set-based write
    family's own witness (``m-batch-write-005``): a predicate write over an
    unversioned, non-temporal entity has nothing to gate per row, so it lowers
    to ONE predicate-shaped statement, no materializing read."""

    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str] = attr(max_length=64)
    balance: Attr[Decimal] = attr(precision=18, scale=2)


WALLET_MODEL = MetamodelHub(Wallet)


class Position(
    Bitemporal,
    table="position",
    namespace=_NS,
    indices=(
        index("position_pk", "id", "valid_start", "tx_start", unique=True),
        index("position_acct", "acct_num"),
    ),
):
    """Mirror of ``models/position.yaml`` (full bitemporal): the write-family
    stories' own bitemporal-insert / ``insertUntil`` / ``updateUntil`` witness
    (``m-bitemp-write-001/-003``). Every axis-governed attribute
    (``valid_start``/``valid_end``/``tx_start``/``tx_end``) is optional at
    construction: a fresh instance names only its payload, and the write path
    stamps the rest."""

    id: Attr[int] = attr(primary_key=True, column="pos_id")
    acct_num: Attr[str] = attr(column="acct_num", max_length=32)
    value: Attr[Decimal] = attr(column="val", precision=18, scale=2)


POSITION_MODEL = MetamodelHub(Position)


class Order(
    Entity,
    table="orders",
    namespace=_NS,
    indices=(index("orders_pk", "id", unique=True), index("orders_sku", "sku")),
):
    """Mirror of the ``Order`` entity of ``models/orders.yaml`` (the full
    relationship set: to-many ``items``/``statuses``/``tags`` plus the
    alternate-ordering ``itemsByShipDate`` path over the same join)."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=255)
    sku: Attr[str | None] = attr(max_length=32)
    qty: Attr[int] = attr(type=Int32)
    price: Attr[Decimal] = attr(precision=18, scale=2)
    active: Attr[bool]
    ordered_on: Attr[dt.date] = attr(column="ordered_on")
    items: Rel[tuple["OrderItem", ...]] = rel(
        cardinality=ONE_TO_MANY,
        join=("id", "order_id"),
        dependent=True,
        order_by=(desc("id"),),
    )
    statuses: Rel[tuple["OrderStatus", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "order_id"), dependent=True
    )
    tags: Rel[tuple["OrderTag", ...]] = rel(
        cardinality=ONE_TO_MANY,
        join=("id", "order_id"),
        order_by=(desc("priority"), "label"),
    )
    items_by_ship_date: Rel[tuple["OrderItem", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "order_id"), order_by=("shipped_on",)
    )


class OrderItem(
    Entity,
    table="order_item",
    namespace=_NS,
    indices=(
        index("order_item_pk", "id", unique=True),
        index("order_item_order_id", "order_id"),
    ),
):
    """Mirror of the ``OrderItem`` entity of ``models/orders.yaml`` (the
    to-one ``order`` back-reference and the item-level ``statuses`` hop)."""

    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int] = attr(column="order_id")
    sku: Attr[str] = attr(max_length=32)
    quantity: Attr[int] = attr(type=Int32)
    shipped_on: Attr[dt.date | None] = attr(column="shipped_on")
    order: Rel[Order | None] = rel(reverse_of="items")
    statuses: Rel[tuple["OrderStatus", ...]] = rel(
        cardinality=ONE_TO_MANY,
        join=("id", "order_item_id"),
        dependent=True,
        order_by=("code",),
    )


class OrderStatus(
    Entity,
    table="order_status",
    namespace=_NS,
    indices=(
        index("order_status_pk", "id", unique=True),
        index("order_status_order_id", "order_id"),
    ),
):
    """Mirror of the ``OrderStatus`` entity of ``models/orders.yaml``: each
    status belongs to an ``Order`` and OPTIONALLY to a specific ``OrderItem``
    (a nullable many-to-one — the to-one navigate/deep-fetch nullable shape)."""

    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int] = attr(column="order_id")
    order_item_id: Attr[int | None] = attr(column="order_item_id")
    code: Attr[str] = attr(max_length=16)
    order: Rel[Order | None] = rel(reverse_of="statuses")
    order_item: Rel[OrderItem | None] = rel(reverse_of="statuses")


class OrderTag(
    Entity,
    table="order_tag",
    namespace=_NS,
    indices=(
        index("order_tag_pk", "id", unique=True),
        index("order_tag_order_id", "order_id"),
    ),
):
    """Mirror of the ``OrderTag`` entity of ``models/orders.yaml``."""

    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int] = attr(column="order_id")
    label: Attr[str] = attr(max_length=32)
    priority: Attr[int] = attr(type=Int32)
    order: Rel[Order | None] = rel(reverse_of="tags")


ORDERS_MODEL = MetamodelHub(Order, OrderItem, OrderStatus, OrderTag)
