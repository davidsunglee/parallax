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
from collections.abc import Mapping

from parallax.core.descriptor.errors import DescriptorError
from parallax.core.descriptor.records import (
    Attribute,
    Entity,
    Metamodel,
    PkGenerator,
    Relationship,
    effective_as_of_attributes,
)

__all__ = ["validate_entity", "validate_metamodel", "validate_temporal_optimistic_locking"]

# The metamodel.schema.json `identifier` and `neutralType` patterns, verbatim.
_IDENTIFIER = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_NEUTRAL_TYPE = re.compile(
    r"^(boolean|int32|int64|float32|float64|string|bytes|date|time|timestamp|uuid|json"
    r"|decimal\([0-9]+,[0-9]+\))$"
)
_INTEGRAL: frozenset[str] = frozenset({"int32", "int64"})


def validate_metamodel(metamodel: Metamodel) -> None:
    """Validate every entity of ``metamodel`` (raises :class:`DescriptorError`).

    An inheritance participant MAY omit its own ``attributes`` when its members are
    wholly inherited (``metamodel.schema.json`` entity conditional; m-inheritance
    "Inherited members"). Its members come from the family, so — rather than the
    per-entity local block — validation derives the full inherited attribute chain
    (root → … → self) and rejects a participant that has none directly or inherited.
    """
    by_name = metamodel.by_name
    for entity in metamodel.entities:
        validate_entity(entity)
    for entity in metamodel.entities:
        if entity.inheritance is not None and not _effective_attributes(entity, by_name):
            raise DescriptorError(
                f"entity {entity.name!r}: declares no attributes, directly or inherited"
            )
    for entity in metamodel.entities:
        validate_temporal_optimistic_locking(metamodel, entity)


def validate_entity(entity: Entity) -> None:
    """Validate one compiled entity record against the schema's domain rules.

    A single-entity view: the optimistic-lock/temporal composition check here
    reads only ``entity``'s own LOCAL ``as_of_attributes``, so it is exact for
    a non-participant (local IS effective there) and for a family root (whose
    local axes ARE the family's), but blind to a descendant whose family is
    temporal through the root alone — :func:`validate_metamodel` closes that
    gap with :func:`validate_temporal_optimistic_locking` once sibling records
    are available to resolve the family-EFFECTIVE axes (ADR 0026).
    """
    if not entity.name:
        raise DescriptorError("entity name must be non-empty")
    if entity.table is not None and not entity.table:
        raise DescriptorError(f"entity {entity.name!r}: table must be non-empty")
    # A non-inheritance entity MUST declare its own attributes; an inheritance
    # participant MAY omit them (its chain is inherited — the schema entity
    # conditional). The family-wide non-empty check lives in `validate_metamodel`,
    # which alone has the sibling records to derive the inherited chain.
    if entity.inheritance is None and not entity.attributes:
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


def validate_temporal_optimistic_locking(metamodel: Metamodel, entity: Entity) -> None:
    """The ``m-opt-lock`` x ``m-descriptor`` composition rule, applied
    FAMILY-EFFECTIVELY (ADR 0026): ``entity`` MUST NOT carry its own
    ``optimisticLocking`` attribute while its family's EFFECTIVE temporal
    classification is temporal — even when ``entity``'s own LOCAL
    ``as_of_attributes`` is empty, which is the normal (and only legal) shape
    for an inheritance descendant in a temporal family (only the root may
    declare ``asOfAttributes`` — `m-inheritance` "Inherited members").
    Resolving from local ``as_of_attributes`` alone (as :func:`validate_entity`
    does, for a single entity with no sibling context) would silently ACCEPT
    a descendant's `optimisticLocking` attribute the schema-level rule means
    to forbid. Idempotent with :func:`validate_entity`'s own local check for a
    non-participant or a family root (LOCAL == EFFECTIVE there).
    """
    if not any(attr.optimistic_locking for attr in entity.attributes):
        return
    if effective_as_of_attributes(metamodel, entity):
        raise DescriptorError(
            f"entity {entity.name!r}: a temporal entity derives its optimistic key from its "
            "processing axis and must not also declare an optimisticLocking attribute"
        )


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


def _effective_attributes(entity: Entity, by_name: Mapping[str, Entity]) -> tuple[Attribute, ...]:
    """The entity's own attributes plus every ancestor's (root → … → self).

    Walks the inheritance ``parent`` chain within the descriptor, accumulating each
    node's declared attributes — the same inherited chain reads and DDL derive
    (m-inheritance "Inherited members"). A pure descriptor traversal: the
    m-descriptor scope must not depend on m-inheritance (§7 dependency graph). The
    ``seen`` guard keeps a malformed (cyclic) family resolving to what it can reach
    rather than looping; an unresolved parent simply ends the walk.
    """
    collected: list[Attribute] = []
    current: Entity | None = entity
    seen: set[str] = set()
    while current is not None and current.name not in seen:
        seen.add(current.name)
        collected.extend(current.attributes)
        inheritance = current.inheritance
        current = None
        if inheritance is not None and inheritance.parent is not None:
            current = by_name.get(inheritance.parent)
    return tuple(collected)


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
