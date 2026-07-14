"""``parallax.core.descriptor`` enforcement scope (m-descriptor).

The metamodel hub: frozen record types for a parsed model descriptor, hand-rolled
snake-to-camel serde round-tripping the ``metamodel.schema.json`` shape, and the
derived facts (``temporal``, ``column_order``) the behavioural scopes and the
entity frontend build on. ``m-descriptor`` depends only on ``m-core``.
"""

from __future__ import annotations

from parallax.core.descriptor.errors import DescriptorError
from parallax.core.descriptor.records import (
    UNSET,
    AsOfAttribute,
    Attribute,
    Axis,
    Entity,
    Index,
    Inheritance,
    InheritanceRole,
    Metamodel,
    NestedValueObject,
    OrderByTerm,
    PkGenerator,
    PkStrategy,
    Relationship,
    Temporal,
    ValueObject,
    ValueObjectAttribute,
    column_order,
)
from parallax.core.descriptor.serde import canonicalize, deserialize, serialize
from parallax.core.descriptor.validate import validate_entity, validate_metamodel

__all__ = [
    "UNSET",
    "AsOfAttribute",
    "Attribute",
    "Axis",
    "DescriptorError",
    "Entity",
    "Index",
    "Inheritance",
    "InheritanceRole",
    "Metamodel",
    "NestedValueObject",
    "OrderByTerm",
    "PkGenerator",
    "PkStrategy",
    "Relationship",
    "Temporal",
    "ValueObject",
    "ValueObjectAttribute",
    "canonicalize",
    "column_order",
    "deserialize",
    "serialize",
    "validate_entity",
    "validate_metamodel",
]
