"""``parallax.core.descriptor`` enforcement scope (m-descriptor).

The metamodel hub: frozen record types for a parsed model descriptor, hand-rolled
snake-to-camel serde round-tripping the ``metamodel.schema.json`` shape, the
three-phase text ingestion contract (``parse_json`` / ``parse_yaml``, and the
``DescriptorSyntaxError`` / ``DescriptorSchemaError`` / ``DescriptorValueError``
failure family), canonical export, and the derived facts (``temporal``,
``column_order``) the behavioural scopes and the entity frontend build on.
``m-descriptor`` depends only on ``m-core``.
"""

from __future__ import annotations

from parallax.core.descriptor.errors import (
    DescriptorError,
    DescriptorSchemaError,
    DescriptorSchemaViolation,
    DescriptorSyntaxError,
    DescriptorValueError,
    DescriptorValueViolation,
)
from parallax.core.descriptor.export import DescriptorExportError, export_document
from parallax.core.descriptor.ingest import ingest_document, parse_json, parse_yaml
from parallax.core.descriptor.neutral_type import (
    NEUTRAL_FROM_PY,
    infer_neutral_type,
    snake_to_camel,
)
from parallax.core.descriptor.records import (
    UNSET,
    AsOfAxisMetadata,
    Attribute,
    DefiningRelationship,
    Entity,
    Index,
    Inheritance,
    InheritanceRole,
    Metamodel,
    Multiplicity,
    NestedValueObject,
    OrderByTerm,
    PkGenerator,
    PkStrategy,
    Relationship,
    RelationshipCardinality,
    RelationshipDeclaration,
    RelationshipJoin,
    RelationshipTarget,
    ReverseRelationship,
    Temporal,
    TemporalDimension,
    ValueObject,
    ValueObjectAttribute,
    column_order,
    concrete_descendant_names,
    declaring_entity,
    effective_as_of_axes,
    effective_temporal,
    family_root_name,
)
from parallax.core.descriptor.serde import (
    canonicalize,
    deserialize,
    parse_document,
    serialize,
)
from parallax.core.descriptor.type_spelling import parse_type_spelling
from parallax.core.descriptor.unresolved import unresolved_metamodel
from parallax.core.descriptor.validate import (
    validate_entity,
    validate_metamodel,
    validate_optimistic_locking_root_owned,
)

__all__ = [
    "NEUTRAL_FROM_PY",
    "UNSET",
    "AsOfAxisMetadata",
    "Attribute",
    "DefiningRelationship",
    "DescriptorError",
    "DescriptorExportError",
    "DescriptorSchemaError",
    "DescriptorSchemaViolation",
    "DescriptorSyntaxError",
    "DescriptorValueError",
    "DescriptorValueViolation",
    "Entity",
    "Index",
    "Inheritance",
    "InheritanceRole",
    "Metamodel",
    "Multiplicity",
    "NestedValueObject",
    "OrderByTerm",
    "PkGenerator",
    "PkStrategy",
    "Relationship",
    "RelationshipCardinality",
    "RelationshipDeclaration",
    "RelationshipJoin",
    "RelationshipTarget",
    "ReverseRelationship",
    "Temporal",
    "TemporalDimension",
    "ValueObject",
    "ValueObjectAttribute",
    "canonicalize",
    "column_order",
    "concrete_descendant_names",
    "declaring_entity",
    "deserialize",
    "effective_as_of_axes",
    "effective_temporal",
    "export_document",
    "family_root_name",
    "infer_neutral_type",
    "ingest_document",
    "parse_document",
    "parse_json",
    "parse_type_spelling",
    "parse_yaml",
    "serialize",
    "snake_to_camel",
    "unresolved_metamodel",
    "validate_entity",
    "validate_metamodel",
    "validate_optimistic_locking_root_owned",
]
