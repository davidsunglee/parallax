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
)

__all__ = ["validate_entity", "validate_metamodel", "validate_optimistic_locking_root_owned"]

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
        validate_optimistic_locking_root_owned(entity)


def validate_entity(entity: Entity) -> None:
    """Validate one compiled entity record against the schema's domain rules.

    A single-entity view: this function's own ``optimisticLocking`` checks are
    the two purely LOCAL, single-entity rules — at most one version attribute
    per entity, and never combined with ``asOfAttributes`` on the same entity
    (a temporal entity derives its optimistic key from its processing axis
    instead) — both exact for any entity regardless of family membership.
    The family root-ownership rule (:func:`validate_optimistic_locking_root_owned`,
    ADR 0027) is ALSO single-entity (a non-root's own ``attributes`` fully
    determine it), but stays a separate function: :func:`validate_metamodel`
    calls it across a compiled family, and the entity frontend
    (``EntityMeta.__new__``) calls it directly at class-definition time for an
    inheritance participant, before any metamodel exists — the same
    organizational split as `validate_metamodel`'s inherited-attributes rule,
    which genuinely does need sibling records (and so has no frontend
    counterpart).
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
    _own_optimistic_locking = [attr for attr in entity.attributes if attr.optimistic_locking]
    if len(_own_optimistic_locking) > 1:
        raise DescriptorError(
            f"entity {entity.name!r}: at most one attribute may declare "
            f"optimisticLocking: true (the version attribute), found "
            f"{len(_own_optimistic_locking)}: "
            f"{[attr.name for attr in _own_optimistic_locking]}"
        )
    if entity.as_of_attributes and _own_optimistic_locking:
        raise DescriptorError(
            f"entity {entity.name!r}: a temporal entity derives its optimistic key from its "
            "processing axis and must not also declare an optimisticLocking attribute"
        )
    for attribute in entity.attributes:
        _validate_attribute(entity.name, attribute)
    for relationship in entity.relationships:
        _validate_relationship(entity.name, relationship)


def validate_optimistic_locking_root_owned(entity: Entity) -> None:
    """The ``m-opt-lock`` x ``m-inheritance`` family invariant (D-25, ADR 0027):
    only an inheritance family's ROOT may declare an ``optimisticLocking``
    version attribute; every descendant inherits it unchanged (or, for a
    non-versioned family, declares none of its own either) — a family is
    versioned together or not at all.

    A non-root ``entity`` (an ``abstract-subtype`` or ``concrete-subtype``)
    declaring its OWN ``optimisticLocking`` attribute is rejected outright,
    regardless of what the root declares — this fires for BOTH malformed
    shapes (a non-versioned root with a version-declaring descendant, and a
    versioned root whose descendant redeclares or adds a second version
    attribute of its own). Neither shape needs sibling records: a non-root
    entity's OWN ``attributes`` fully determine the verdict either way, so
    this is a pure, single-entity check — unlike :func:`validate_metamodel`'s
    other family-wide rule (`no attributes, directly or inherited`), which
    genuinely needs the ancestry chain. A no-op for a non-participant or the
    family root (:func:`validate_entity`'s own local checks — at most one per
    entity, never combined with ``asOfAttributes`` — are exact there; LOCAL ==
    EFFECTIVE for a root, so a root cannot combine an explicit version with a
    temporal axis either).

    This SUBSUMES the narrower rule this function used to check (a temporal
    descendant's own ``optimisticLocking`` attribute, resolved via the
    family-EFFECTIVE ``asOfAttributes`` — ADR 0026): a non-root can never
    declare its own version attribute at all now, temporal or not, so the
    temporal-family shape collapses into this general rule plus
    :func:`validate_entity`'s own composition check already applied AT the
    root (only the root ever legitimately carries BOTH a temporal axis and,
    mutually exclusively, an explicit version).
    """
    if entity.inheritance is None or entity.inheritance.role == "root":
        return
    if any(attr.optimistic_locking for attr in entity.attributes):
        raise DescriptorError(
            f"entity {entity.name!r}: only the inheritance family root may declare an "
            "optimisticLocking attribute; a descendant inherits it unchanged"
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
