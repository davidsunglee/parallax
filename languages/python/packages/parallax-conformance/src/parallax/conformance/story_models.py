"""Idiomatic entity classes the API-suite write stories construct instances of.

Mirrors ``models/account.yaml`` and the ``Order`` / ``OrderItem`` scalar
surface of ``models/orders.yaml``. Owned by ``parallax.conformance`` (not the
test-suite's own ``mirrored_models`` / ``example_models``, which live under
``tests/`` and are unreachable from an installed ``parallax-conformance``
distribution) since ``stories.py`` — a real dev-only package module, exercised
by both the fake-port write no-drift guard and the real-Postgres story-run
suite — needs classes resolvable at ordinary import time, not only under
pytest's test-path magic. This module deliberately avoids
``from __future__ import annotations`` so the metaclass reads the live
``Attr[T]`` objects and infers each attribute's neutral type from ``T``.
"""

import datetime as dt
from decimal import Decimal

from parallax.core import Attr, Entity, EntityConfig, Field

_NS = "parallax.compatibility"

__all__ = ["Account", "Order", "OrderItem"]


class Account(Entity, frozen=True):
    """Mirror of ``models/account.yaml``."""

    __parallax__ = EntityConfig(table="account", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none")
    owner: Attr[str] = Field(max_length=64)
    balance: Attr[Decimal] = Field(type="decimal(18,2)")
    version: Attr[int] = Field(type="int32", optimistic_locking=True)


class Order(Entity, frozen=True):
    """Mirror of the ``Order`` scalar surface of ``models/orders.yaml``."""

    __parallax__ = EntityConfig(table="orders", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=255)
    sku: Attr[str | None] = Field(type="string", max_length=32, nullable=True, default=None)
    qty: Attr[int] = Field(type="int32")
    price: Attr[Decimal] = Field(type="decimal(18,2)")
    active: Attr[bool] = Field(default=False)
    ordered_on: Attr[dt.date] = Field(column="ordered_on")


class OrderItem(Entity, frozen=True):
    """Mirror of the ``OrderItem`` scalar surface of ``models/orders.yaml``."""

    __parallax__ = EntityConfig(table="order_item", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    order_id: Attr[int] = Field(column="order_id", type="int64")
    sku: Attr[str] = Field(max_length=32)
    quantity: Attr[int] = Field(type="int32")
    shipped_on: Attr[dt.date | None] = Field(
        type="date", column="shipped_on", nullable=True, default=None
    )
