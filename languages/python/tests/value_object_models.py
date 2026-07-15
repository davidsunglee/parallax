"""Idiomatic ``ValueObject`` + entity classes mirroring ``models/customer.yaml``
(D-7 value-object spelling, COR-3 Phase 7 increment 6a) — the recursive
``Address`` / ``Geo`` / ``Point`` / ``Phone`` composite, one nested VO
(``geo`` -> ``point``) and one ``cardinality: many`` member (``phones``).
This module deliberately avoids ``from __future__ import annotations`` so the
metaclass reads the live ``Attr[T]`` objects directly.

Lives at the top level of ``tests/`` (moved from ``tests/unit/`` in increment
6b): the unit lane and the API Conformance Suite's VO traversal examples share
these SAME classes (a second copy would race the single process-wide entity
registry), and only a module on ``pythonpath = ["tools", "tests"]`` resolves
reliably regardless of collection order.
"""

from parallax.core import Attr, Entity, EntityConfig, Field
from parallax.core.entity.value_object import ValueObject, VoField

_NS = "parallax.compatibility"


class Point(ValueObject, frozen=True):
    lat: Attr[float | None] = VoField(type="float64", nullable=True, default=None)
    lon: Attr[float | None] = VoField(type="float64", nullable=True, default=None)


class Geo(ValueObject, frozen=True):
    country: Attr[str] = VoField(type="string")
    elevation: Attr[float | None] = VoField(type="float64", nullable=True, default=None)
    point: Attr[Point | None] = VoField(nullable=True, default=None)


class Phone(ValueObject, frozen=True):
    type: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    number: Attr[str | None] = VoField(type="string", nullable=True, default=None)


class Address(ValueObject, frozen=True):
    street: Attr[str] = VoField(type="string")
    city: Attr[str] = VoField(type="string")
    geo: Attr[Geo | None] = VoField(nullable=True, default=None)
    phones: Attr[tuple[Phone, ...]] = VoField(nullable=True, default=())


class Customer(Entity, frozen=True):
    """Mirror of ``models/customer.yaml``."""

    __parallax__ = EntityConfig(table="customer", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    address: Attr[Address | None] = Field(nullable=True, default=None)
