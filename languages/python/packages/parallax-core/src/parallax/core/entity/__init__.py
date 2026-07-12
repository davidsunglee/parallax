"""``parallax.core.entity`` enforcement scope (entity/statement frontend, support).

The developer-facing class frontend's **definition half**: the frozen entity
base and its metaclass, the ``Attr[T]`` / ``Rel[T]`` typed-access carriers, the
``Field`` / ``Relationship`` declaration helpers, and ``meta`` introspection
that re-exports the canonical descriptor. The statement half (predicate and
temporal-read building) lands with the read path in a later phase. This support
scope may import ``m-descriptor``, ``m-op-algebra``, and ``m-temporal-read``.
"""

from __future__ import annotations

from parallax.core.descriptor import OrderByTerm
from parallax.core.entity.base import (
    Entity,
    EntityConfig,
    EntityMeta,
    camel_to_snake,
    entity_registry,
    snake_to_camel,
)
from parallax.core.entity.errors import (
    EntityDefinitionError,
    NameCollisionError,
    ReservedNameError,
)
from parallax.core.entity.expressions import Attr, AttributeRef, Rel, RelationshipRef
from parallax.core.entity.fields import Field, FieldSpec, Relationship, RelationshipSpec
from parallax.core.entity.meta import (
    EntityMetaView,
    descriptor_document,
    meta,
    metamodel,
)

__all__ = [
    "Attr",
    "AttributeRef",
    "Entity",
    "EntityConfig",
    "EntityDefinitionError",
    "EntityMeta",
    "EntityMetaView",
    "Field",
    "FieldSpec",
    "NameCollisionError",
    "OrderByTerm",
    "Rel",
    "Relationship",
    "RelationshipRef",
    "RelationshipSpec",
    "ReservedNameError",
    "camel_to_snake",
    "descriptor_document",
    "entity_registry",
    "meta",
    "metamodel",
    "snake_to_camel",
]
