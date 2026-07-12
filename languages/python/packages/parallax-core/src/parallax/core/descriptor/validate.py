"""Schema-equivalent domain validation for compiled metamodel records.

``metamodel.schema.json`` constrains a descriptor beyond the structural parsing
``serde`` performs — neutral-type membership, ``maxLength >= 1``, the
optimistic-lock composition rule, PK-generator bounds, and canonical-identifier
names. ``parallax-core`` ships no JSON-schema validator (its only runtime
dependencies are ``pydantic`` and ``pyyaml``), so these pure-Python validators
reproduce the schema's domain rules over the frozen records. The entity frontend
runs them at class-definition time, so an invalid record (for example
``Field(type="widget")``) is rejected before the class is registered and can
never be exported — the database never sees an invalid value (python.md §2).
"""

from __future__ import annotations

import re

from parallax.core.descriptor.errors import DescriptorError
from parallax.core.descriptor.records import (
    Attribute,
    Entity,
    Metamodel,
    PkGenerator,
    Relationship,
)

__all__ = ["validate_entity", "validate_metamodel"]

# The metamodel.schema.json `identifier` and `neutralType` patterns, verbatim.
_IDENTIFIER = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_NEUTRAL_TYPE = re.compile(
    r"^(boolean|int32|int64|float32|float64|string|bytes|date|time|timestamp|uuid|json"
    r"|decimal\([0-9]+,[0-9]+\))$"
)
_INTEGRAL: frozenset[str] = frozenset({"int32", "int64"})


def validate_metamodel(metamodel: Metamodel) -> None:
    """Validate every entity of ``metamodel`` (raises :class:`DescriptorError`)."""
    for entity in metamodel.entities:
        validate_entity(entity)


def validate_entity(entity: Entity) -> None:
    """Validate one compiled entity record against the schema's domain rules."""
    if not entity.name:
        raise DescriptorError("entity name must be non-empty")
    if entity.table is not None and not entity.table:
        raise DescriptorError(f"entity {entity.name!r}: table must be non-empty")
    if not entity.attributes:
        raise DescriptorError(f"entity {entity.name!r}: declares no attributes")
    if entity.as_of_attributes and any(attr.optimistic_locking for attr in entity.attributes):
        raise DescriptorError(
            f"entity {entity.name!r}: a temporal entity derives its optimistic key from its "
            "processing axis and must not also declare an optimisticLocking attribute"
        )
    for attribute in entity.attributes:
        _validate_attribute(entity.name, attribute)
    for relationship in entity.relationships:
        _validate_relationship(entity.name, relationship)


def _validate_attribute(entity_name: str, attr: Attribute) -> None:
    where = f"entity {entity_name!r} attribute {attr.name!r}"
    if _IDENTIFIER.match(attr.name) is None:
        raise DescriptorError(f"{where}: not a canonical camelCase identifier")
    if _NEUTRAL_TYPE.match(attr.type) is None:
        raise DescriptorError(f"{where}: {attr.type!r} is not a neutral type")
    if not attr.column:
        raise DescriptorError(f"{where}: column must be non-empty")
    if attr.max_length is not None and attr.max_length < 1:
        raise DescriptorError(f"{where}: maxLength must be >= 1, got {attr.max_length}")
    if attr.optimistic_locking and attr.type not in _INTEGRAL:
        raise DescriptorError(
            f"{where}: an optimisticLocking version must be int32 or int64, got {attr.type!r}"
        )
    if attr.pk_generator is not None:
        _validate_pk_generator(where, attr.pk_generator)


def _validate_pk_generator(where: str, pk: PkGenerator) -> None:
    if pk.batch_size is not None and pk.batch_size < 1:
        raise DescriptorError(f"{where}: pk-generator batchSize must be >= 1, got {pk.batch_size}")
    if pk.increment_size is not None and pk.increment_size < 1:
        raise DescriptorError(
            f"{where}: pk-generator incrementSize must be >= 1, got {pk.increment_size}"
        )


def _validate_relationship(entity_name: str, rel: Relationship) -> None:
    where = f"entity {entity_name!r} relationship {rel.name!r}"
    if _IDENTIFIER.match(rel.name) is None:
        raise DescriptorError(f"{where}: not a canonical camelCase identifier")
    if not rel.related_entity:
        raise DescriptorError(f"{where}: relatedEntity must be non-empty")
    if not rel.join:
        raise DescriptorError(f"{where}: join must be non-empty")
    if rel.reverse_name is not None and _IDENTIFIER.match(rel.reverse_name) is None:
        raise DescriptorError(f"{where}: reverseName {rel.reverse_name!r} is not an identifier")
