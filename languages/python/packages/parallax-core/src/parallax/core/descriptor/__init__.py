"""``parallax.core.descriptor`` enforcement scope (m-descriptor).

The metamodel hub: frozen record types for a parsed model descriptor, hand-rolled
snake-to-camel serde round-tripping the ``metamodel.schema.json`` shape, and the
derived facts (``temporal``, ``column_order``) the behavioural scopes and the
entity frontend build on. ``m-descriptor`` depends only on ``m-core``.
"""

from __future__ import annotations

from parallax.core.descriptor.errors import DescriptorError
from parallax.core.descriptor.neutral_type import (
    NEUTRAL_FROM_PY,
    infer_neutral_type,
    snake_to_camel,
)
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
    declaring_entity,
    effective_as_of_attributes,
    effective_temporal,
)
from parallax.core.descriptor.serde import canonicalize, deserialize, serialize
from parallax.core.descriptor.validate import (
    validate_entity,
    validate_metamodel,
    validate_temporal_optimistic_locking,
)
from parallax.core.descriptor.vo_path import (
    VoPathMiss,
    find_value_object,
    find_vo_member,
    resolve_vo_leaf,
)

__all__ = [
    "NEUTRAL_FROM_PY",
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
    "VoPathMiss",
    "canonicalize",
    "column_order",
    "declaring_entity",
    "deserialize",
    "effective_as_of_attributes",
    "effective_temporal",
    "find_value_object",
    "find_vo_member",
    "infer_neutral_type",
    "resolve_vo_leaf",
    "serialize",
    "snake_to_camel",
    "validate_entity",
    "validate_metamodel",
    "validate_temporal_optimistic_locking",
]
