"""Idiomatic entity classes for the API Conformance Suite's statement examples.

Mirrors the ``Order`` scalar surface of ``models/orders.yaml`` so the operation
no-drift guard can build idiomatic statements and prove their serialization equals
the corpus operation. Like ``mirrored_models``, this module avoids
``from __future__ import annotations`` so the metaclass reads the live ``Attr[T]``
objects and infers each attribute's neutral type from ``T``.
"""

import datetime as dt
from decimal import Decimal

from parallax.core import Attr, Entity, EntityConfig, Field

_NS = "parallax.compatibility"


class Order(Entity, frozen=True):
    """Mirror of the ``Order`` scalar surface of ``models/orders.yaml``."""

    __parallax__ = EntityConfig(table="orders", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=255)
    sku: Attr[str] = Field(max_length=32, nullable=True)
    qty: Attr[int] = Field(type="int32")
    price: Attr[Decimal] = Field(type="decimal(18,2)")
    active: Attr[bool]
    ordered_on: Attr[dt.date] = Field(column="ordered_on")
