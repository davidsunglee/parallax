"""Runtime metamodel introspection (``meta`` / ``EntityMetaView``).

``meta(Order)`` (or ``meta("Order")``) returns a frozen view over an entity's
canonical metamodel record, with ``descriptor()`` re-exporting the canonical
dict form. The same view type serves a class-authored entity and one ingested
from canonical YAML — both are :class:`~parallax.core.descriptor.Entity`
records under the hood.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from parallax.core.descriptor import (
    AsOfAttribute,
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    Relationship,
    Temporal,
    ValueObject,
    serialize,
)
from parallax.core.entity.base import entity_record_of, entity_registry

__all__ = ["EntityMetaView", "descriptor_document", "meta", "metamodel"]


def _entity_of(target: type | str) -> Entity:
    if isinstance(target, str):
        registry = entity_registry()
        if target not in registry:
            raise KeyError(f"no entity named {target!r} is registered")
        target = registry[target]
    record = entity_record_of(target)
    if record is None:
        raise TypeError(f"{target!r} is not a Parallax entity class")
    return record


@dataclass(frozen=True, slots=True)
class EntityMetaView:
    """A frozen introspection view over one entity's metamodel record."""

    _entity: Entity

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
        return self._entity.temporal

    @property
    def attributes(self) -> tuple[Attribute, ...]:
        return self._entity.attributes

    @property
    def primary_key(self) -> tuple[Attribute, ...]:
        return self._entity.primary_key

    @property
    def as_of(self) -> tuple[AsOfAttribute, ...]:
        return self._entity.as_of_attributes

    @property
    def relationships(self) -> tuple[Relationship, ...]:
        return self._entity.relationships

    @property
    def value_objects(self) -> tuple[ValueObject, ...]:
        return self._entity.value_objects

    @property
    def family(self) -> Inheritance | None:
        return self._entity.inheritance

    def descriptor(self) -> dict[str, object]:
        """The canonical single-entity descriptor document for this entity."""
        return serialize(Metamodel(entities=(self._entity,)))


def meta(target: type | str) -> EntityMetaView:
    """The introspection view for an entity class or a registered entity name."""
    return EntityMetaView(_entity_of(target))


def metamodel(classes: Sequence[type]) -> Metamodel:
    """Assemble one :class:`Metamodel` from a set of related entity classes."""
    return Metamodel(entities=tuple(_entity_of(cls) for cls in classes))


def descriptor_document(classes: Sequence[type]) -> dict[str, object]:
    """The canonical descriptor document for a set of related entity classes."""
    return serialize(metamodel(classes))
