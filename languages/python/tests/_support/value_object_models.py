"""Idiomatic Value Object and Entity classes mirroring ``models/customer.yaml``.

The recursive ``Address`` / ``Geo`` / ``Point`` / ``Phone`` composite, with one
nested occurrence (``geo`` -> ``point``) and one Many occurrence (``phones``).
This module deliberately omits ``from __future__ import annotations`` so the
engine reads the live ``Attr[T]`` objects directly; the stringized path has its
own probes.

It is cross-surface rather than under ``tests/unit/`` because the unit tests and
the API Conformance Suite's Value Object examples share these same classes, and
only a module on the configured ``pythonpath`` resolves reliably regardless of
collection order.
"""

from parallax.core import Attr, DomainModel, Entity, ValueObject, attr

_NS = "parallax.compatibility"


class Point(ValueObject):
    lat: Attr[float | None]
    lon: Attr[float | None]


class Geo(ValueObject):
    country: Attr[str]
    elevation: Attr[float | None]
    point: Attr[Point | None]


class Phone(ValueObject):
    type: Attr[str | None]
    number: Attr[str | None]


class Address(ValueObject):
    street: Attr[str]
    city: Attr[str]
    geo: Attr[Geo | None]
    phones: Attr[tuple[Phone, ...]]


class Customer(Entity, table="customer", namespace=_NS):
    """Mirror of ``models/customer.yaml``'s ``Customer``."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    address: Attr[Address | None]


CUSTOMER_MODEL = DomainModel(Customer)
"""``models/customer.yaml``'s Customer alone — the Domain Model the Value Object
examples are executed against."""
