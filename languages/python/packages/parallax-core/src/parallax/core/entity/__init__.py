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
    entity_records,
    entity_registry,
    snake_to_camel,
)
from parallax.core.entity.errors import (
    EntityDefinitionError,
    NameCollisionError,
    ReservedNameError,
)
from parallax.core.entity.expressions import (
    Attr,
    AttributeExpr,
    AttributeRef,
    Predicate,
    Rel,
    RelationshipRef,
)
from parallax.core.entity.fields import Field, FieldSpec, Relationship, RelationshipSpec
from parallax.core.entity.meta import (
    EntityMetaView,
    FamilyView,
    descriptor_document,
    meta,
    meta_of,
    metamodel,
)
from parallax.core.entity.statement import Statement

__all__ = [
    "Attr",
    "AttributeExpr",
    "AttributeRef",
    "Entity",
    "EntityConfig",
    "EntityDefinitionError",
    "EntityMeta",
    "EntityMetaView",
    "FamilyView",
    "Field",
    "FieldSpec",
    "NameCollisionError",
    "OrderByTerm",
    "Predicate",
    "Rel",
    "Relationship",
    "RelationshipRef",
    "RelationshipSpec",
    "ReservedNameError",
    "Statement",
    "camel_to_snake",
    "descriptor_document",
    "entity_records",
    "entity_registry",
    "meta",
    "meta_of",
    "metamodel",
    "snake_to_camel",
]
