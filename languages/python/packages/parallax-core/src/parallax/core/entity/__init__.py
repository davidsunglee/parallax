"""``parallax.core.entity`` enforcement scope (entity/statement frontend, support).

The developer-facing class frontend: the frozen entity base and its metaclass,
the ``Attr[T]`` / ``Rel[T]`` typed-access carriers, the ``Field`` /
``Relationship`` declaration helpers, canonical descriptor export, the statement
surface (predicate / temporal-read / deep-fetch-include / subtype-narrowing
building), the ``ValueObject`` class frontend (D-7), and the closed-world
relationship load-state vocabulary (``is_loaded`` / ``narrowed``,
``UnloadedRelationshipError``) the frozen snapshot-node wrapper attaches. This
support scope may import ``m-descriptor``, ``m-op-algebra`` (reaching
``m-inheritance`` transitively), and ``m-temporal-read``.
"""

from __future__ import annotations

from parallax.core.descriptor import OrderByTerm
from parallax.core.entity.base import (
    Bitemporal,
    Concrete,
    Entity,
    EntityConfig,
    EntityMeta,
    EntityRegistry,
    FamilyRoot,
    ModelCopyError,
    ProvenanceError,
    ScopedMetamodel,
    TxTemporal,
    WireNames,
    camel_to_snake,
    canonical_row,
    changed_fields,
    default_registry,
    descriptor_document,
    effective_change_set,
    entity_record_of,
    entity_records,
    entity_registry,
    full_row,
    metamodel,
    primary_key_row,
    registry_of,
    resolve_entity_class,
    snake_to_camel,
    wire_names_of,
)
from parallax.core.entity.errors import (
    EntityDefinitionError,
    NameCollisionError,
    RegistryCollisionError,
    ReservedNameError,
)
from parallax.core.entity.expressions import (
    UNLOADED,
    Attr,
    AttributeExpr,
    AttributeRef,
    ElementAttributeExpr,
    Predicate,
    Rel,
    RelationshipPath,
    RelationshipRef,
    UnloadedRelationshipError,
)
from parallax.core.entity.fields import (
    Field,
    FieldSpec,
    Relationship,
    RelationshipSpec,
    ReverseRelationship,
    ReverseRelationshipSpec,
)
from parallax.core.entity.graph_state import is_loaded, narrowed
from parallax.core.entity.statement import Statement, UnsupportedFeatureError
from parallax.core.entity.value_object import ValueObject, VoField, VoFieldSpec

__all__ = [
    "UNLOADED",
    "Attr",
    "AttributeExpr",
    "AttributeRef",
    "Bitemporal",
    "Concrete",
    "ElementAttributeExpr",
    "Entity",
    "EntityConfig",
    "EntityDefinitionError",
    "EntityMeta",
    "EntityRegistry",
    "FamilyRoot",
    "Field",
    "FieldSpec",
    "ModelCopyError",
    "NameCollisionError",
    "OrderByTerm",
    "Predicate",
    "ProvenanceError",
    "RegistryCollisionError",
    "Rel",
    "Relationship",
    "RelationshipPath",
    "RelationshipRef",
    "RelationshipSpec",
    "ReservedNameError",
    "ReverseRelationship",
    "ReverseRelationshipSpec",
    "ScopedMetamodel",
    "Statement",
    "TxTemporal",
    "UnloadedRelationshipError",
    "UnsupportedFeatureError",
    "ValueObject",
    "VoField",
    "VoFieldSpec",
    "WireNames",
    "camel_to_snake",
    "canonical_row",
    "changed_fields",
    "default_registry",
    "descriptor_document",
    "effective_change_set",
    "entity_record_of",
    "entity_records",
    "entity_registry",
    "full_row",
    "is_loaded",
    "metamodel",
    "narrowed",
    "primary_key_row",
    "registry_of",
    "resolve_entity_class",
    "snake_to_camel",
    "wire_names_of",
]
