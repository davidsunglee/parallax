"""Frontend probes exercising the live-annotation (non-string) metaclass paths.

This module deliberately omits ``from __future__ import annotations`` so the
metaclass sees real ``Attr[T]`` objects and neutral-type inference runs against
the concrete ``T``. Each ``define_*`` helper builds a class whose definition is
expected to fail; the trailing ``return`` keeps the class referenced for the type
checker even though the metaclass raises before it runs.
"""

from decimal import Decimal

from parallax.core import Attr, Entity, EntityConfig, Field, Rel

_CFG = EntityConfig(table="bad", mutability="transactional")


def define_decimal_without_type() -> type:
    """A decimal attribute with no explicit precision — rejected at definition."""

    class Bad(Entity, frozen=True):
        __parallax__ = _CFG

        id: Attr[int] = Field(primary_key=True)
        amount: Attr[Decimal]

    return Bad


def define_unmapped_attribute() -> type:
    """An attribute whose Python type has no neutral mapping — rejected."""

    class Widget:
        pass

    class Bad(Entity, frozen=True):
        __parallax__ = _CFG

        id: Attr[int] = Field(primary_key=True)
        widget: Attr[Widget]

    return Bad


def define_reserved_name() -> type:
    """A field reusing a reserved query-root name — rejected."""

    class Bad(Entity, frozen=True):
        __parallax__ = _CFG

        where: Attr[int] = Field(primary_key=True)

    return Bad


def define_name_collision() -> type:
    """Two fields resolving to the same canonical name — rejected."""

    class Bad(Entity, frozen=True):
        __parallax__ = _CFG

        order_id: Attr[int] = Field(primary_key=True)
        orderId: Attr[int]

    return Bad


def define_non_attr_field() -> type:
    """A plain field annotation that is not ``Attr``/``Rel`` — rejected."""

    class Bad(Entity, frozen=True):
        __parallax__ = _CFG

        qty: int = 5

    return Bad


def define_no_attributes() -> type:
    """An entity with no declared attributes — rejected."""

    class Bad(Entity, frozen=True):
        __parallax__ = _CFG

    return Bad


def define_relationship_without_spec() -> type:
    """A ``Rel`` field missing its ``Relationship(...)`` metadata — rejected."""

    class Bad(Entity, frozen=True):
        __parallax__ = _CFG

        id: Attr[int] = Field(primary_key=True)
        peer: Rel[object]

    return Bad


def define_bad_config() -> type:
    """A ``__parallax__`` that is not an ``EntityConfig`` — rejected."""

    class Bad(Entity, frozen=True):
        __parallax__ = "wrong"

        id: Attr[int] = Field(primary_key=True)

    return Bad


def define_bad_mutability() -> type:
    """An out-of-range mutability keyword — rejected."""

    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="frozen")

        id: Attr[int] = Field(primary_key=True)

    return Bad
