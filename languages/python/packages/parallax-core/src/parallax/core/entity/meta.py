"""Runtime metamodel introspection (``meta`` / ``EntityMetaView``).

``meta(Order)`` (or ``meta("Order")``) returns a frozen ``EntityMetaView`` over
an entity's canonical metamodel record, with ``descriptor()`` re-exporting the
canonical dict form. ``meta_of(metamodel, "Order")`` produces the identical view
shape from a descriptor ingested from canonical YAML (the conformance adapter's
path), so the same view is available whether the metamodel came from classes or
ingested YAML (python.md §2). ``family`` resolves the entity's inheritance root,
strategy, and effective concrete-subtype set from its sibling records rather than
echoing the entity's own local inheritance block.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from parallax.core.descriptor import (
    AsOfAttribute,
    Attribute,
    Entity,
    InheritanceRole,
    Metamodel,
    Relationship,
    Temporal,
    ValueObject,
    effective_temporal,
    serialize,
)
from parallax.core.entity._validation import require_entity_record
from parallax.core.entity.base import (
    entity_record_of,
    entity_records,
    entity_registry,
    metamodel,
    registry_of,
)

__all__ = [
    "EntityMetaView",
    "FamilyView",
    "descriptor_document",
    "meta",
    "meta_of",
    "metamodel",
]


def _entity_of(target: type | str) -> Entity:
    if isinstance(target, str):
        registry = entity_registry()
        if target not in registry:
            raise KeyError(f"no entity named {target!r} is registered")
        target = registry[target]
    return require_entity_record(target, entity_record_of(target))


@dataclass(frozen=True, slots=True)
class FamilyView:
    """Resolved inheritance-family metadata for one entity's position.

    ``root``/``strategy``/``tag_column`` come from the family's abstract root;
    ``parent``/``tag_value`` are this entity's own; ``subtypes`` is the effective
    concrete-subtype set of this position (a concrete subtype resolves to itself;
    an abstract position to its concrete descendants), alphabetically ordered.
    """

    role: InheritanceRole
    root: str | None
    strategy: str | None
    parent: str | None
    tag_column: str | None
    tag_value: str | None
    subtypes: tuple[str, ...]


def _root_of(entity: Entity, by_name: Mapping[str, Entity]) -> Entity | None:
    """Walk the parent chain to the family's abstract root (``None`` if unresolved)."""
    current = entity
    guard: set[str] = set()
    while True:
        inheritance = current.inheritance
        if inheritance is None:
            return None
        if inheritance.role == "root":
            return current
        parent = inheritance.parent
        if parent is None or current.name in guard or parent not in by_name:
            return None
        guard.add(current.name)
        current = by_name[parent]


def _concrete_subtypes(position: str, by_name: Mapping[str, Entity]) -> tuple[str, ...]:
    """Every concrete-subtype name at or under ``position``, alphabetically ordered."""
    children: dict[str, list[str]] = {}
    for entity in by_name.values():
        inheritance = entity.inheritance
        if inheritance is not None and inheritance.parent is not None:
            children.setdefault(inheritance.parent, []).append(entity.name)
    result: set[str] = set()
    seen: set[str] = set()
    stack = [position]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        entity = by_name.get(name)
        if (
            entity is not None
            and entity.inheritance is not None
            and entity.inheritance.role == "concrete-subtype"
        ):
            result.add(name)
        stack.extend(children.get(name, []))
    return tuple(sorted(result))


@dataclass(frozen=True, slots=True)
class EntityMetaView:
    """A frozen introspection view over one entity's metamodel record.

    ``_context`` carries the sibling entities the entity was resolved within (its
    class registry, or an ingested metamodel), so ``family`` can resolve
    cross-entity metadata; it never affects the single-entity projections.
    """

    _entity: Entity
    _context: tuple[Entity, ...] = ()

    @property
    def name(self) -> str:
        return self._entity.name

    @property
    def namespace(self) -> str | None:
        return self._entity.namespace

    @property
    def table(self) -> str | None:
        return self._entity.table

    @property
    def temporal(self) -> Temporal:
        """The FAMILY-EFFECTIVE temporal classification (`m-descriptor`; ADR
        0026): for an inheritance participant, the family root's — an
        abstract-subtype or concrete-subtype declares no ``asOfAttributes``
        of its own even when its family is temporal, so `Entity.temporal`
        alone (a bare, non-flattening structural view) would misreport it
        ``non-temporal``. Introspection is one of the consumers the spec
        names as needing the effective classification, so this resolves
        through the sibling records `_context` carries, never the entity's
        own local axes directly."""
        return effective_temporal(Metamodel(entities=self._context), self._entity)

    @property
    def attributes(self) -> tuple[Attribute, ...]:
        return self._entity.attributes

    @property
    def primary_key(self) -> tuple[Attribute, ...]:
        return self._entity.primary_key

    @property
    def as_of(self) -> tuple[AsOfAttribute, ...]:
        """This entity's OWN LOCAL declared as-of axes — a non-flattening
        structural view (`m-descriptor` "A model-aware reader that does not
        flatten inheritance… MAY still surface a non-root participant's own,
        locally-empty asOfAttributes for structural inspection"). Use
        :attr:`temporal` for the family-EFFECTIVE classification."""
        return self._entity.as_of_attributes

    @property
    def relationships(self) -> tuple[Relationship, ...]:
        return self._entity.relationships

    @property
    def value_objects(self) -> tuple[ValueObject, ...]:
        return self._entity.value_objects

    @property
    def family(self) -> FamilyView | None:
        """The resolved inheritance-family view, or ``None`` outside a family."""
        inheritance = self._entity.inheritance
        if inheritance is None:
            return None
        by_name = {entity.name: entity for entity in self._context}
        by_name.setdefault(self._entity.name, self._entity)
        root = _root_of(self._entity, by_name)
        root_inheritance = root.inheritance if root is not None else None
        return FamilyView(
            role=inheritance.role,
            root=root.name if root is not None else None,
            strategy=root_inheritance.strategy if root_inheritance is not None else None,
            parent=inheritance.parent,
            tag_column=root_inheritance.tag_column if root_inheritance is not None else None,
            tag_value=inheritance.tag_value,
            subtypes=_concrete_subtypes(self._entity.name, by_name),
        )

    def descriptor(self) -> dict[str, object]:
        """The canonical single-entity descriptor document for this entity."""
        return serialize(Metamodel(entities=(self._entity,)))


def meta(target: type | str) -> EntityMetaView:
    """The introspection view for an entity class or a registered entity name.

    A CLASS's own sibling/resolution context is derived from ITS OWN D-20
    registration scope, never the process default, so ``family``'s
    cross-entity resolution can never cross into a foreign registry's
    same-named sibling: assembling a single-class :func:`metamodel` and
    reading its :func:`registry_of` (R3, COR-3 Phase 7 increment 7 round-2 --
    the module-private ``_registry_of_class`` this used to reach for directly
    is no longer a cross-module surface; these two ALREADY-public, ledger-D-20
    bridge functions give the identical scope). A bare canonical NAME has no
    class to derive a scope from at all, so it stays UNSCOPED: the process
    default registry's own records, an explicit, documented fallback (S2) --
    never a silent guess -- for that one no-class-in-hand case.

    ``target`` is validated via :func:`_entity_of` FIRST, before deriving the
    class-branch's scope: an unregistered name or a non-entity class raises
    THIS module's own ``KeyError``/``TypeError`` (unchanged shape), never
    :func:`metamodel`'s -- both raise the identical exception type for an
    invalid class, but validating here first keeps the error a property of
    ``meta()`` itself rather than an incidental side effect of how its scope
    happens to be derived.
    """
    entity = _entity_of(target)
    if isinstance(target, str):
        return EntityMetaView(entity, tuple(entity_records().values()))
    registry = registry_of(metamodel([target]))
    return EntityMetaView(entity, tuple(registry.records().values()))


def meta_of(descriptor: Metamodel, name: str) -> EntityMetaView:
    """The introspection view for ``name`` within an ingested descriptor.

    Produces the same ``EntityMetaView`` shape ``meta`` returns for a
    class-authored entity, so a metamodel ingested from canonical YAML (the
    conformance adapter's path) yields an equivalent view for a shared model.
    """
    return EntityMetaView(descriptor.entity(name), descriptor.entities)


def descriptor_document(classes: Sequence[type]) -> dict[str, object]:
    """The canonical descriptor document for a set of related entity classes."""
    return serialize(metamodel(classes))
