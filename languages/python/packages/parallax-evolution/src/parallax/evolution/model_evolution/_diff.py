"""Evolution Operations from one :class:`~._matching.Matching`, in inspection order.

A parent addition or removal suppresses every operation for the declarations it
contains, so an Entity present in one endpoint alone is one entity-level
operation and nothing else — which is also what makes the fresh-provisioning
evolution, whose every Entity is an addition, the same code path rather than a
second differ.

The generic Entity variants exclude concrete-subtype add and remove, and each
Entity's role is read from the endpoint that declares it: the later model for an
addition, the earlier one for a removal. An alteration reports the accepted
declarations that differ; whether the difference needs coordination is the
classifier's question, asked of the effective facts.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from parallax.core.metamodel import AttributeMetadata, ConcreteSubtype, EntityMetadata
from parallax.evolution.model_evolution._matching import Matching
from parallax.evolution.model_evolution._values import (
    AttributeAdded,
    AttributeAltered,
    AttributeDelta,
    AttributeRemoved,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    EntityAdded,
    EntityAltered,
    EntityDelta,
    EntityRemoved,
    EvolutionOperation,
    InheritanceChanged,
    MaximumLengthChanged,
    NullabilityChanged,
    OptimisticLockingChanged,
    PersistenceChanged,
    PrimaryKeyChanged,
    ReadOnlyChanged,
    StorageChanged,
    StorageContainerChanged,
    StorageLayoutChanged,
    TypeChanged,
    canonical_operation_key,
)

__all__ = ["diff"]


def diff(matching: Matching) -> tuple[EvolutionOperation, ...]:
    """Every Evolution Operation the two endpoints differ by."""
    return _ordered([*_entity_operations(matching), *_attribute_operations(matching)])


def _entity_operations(matching: Matching) -> Iterator[EvolutionOperation]:
    for facts in matching.entities.added.values():
        yield _added(facts.declaration)
    for facts in matching.entities.removed.values():
        yield _removed(facts.declaration)
    for identity, (earlier, later) in matching.entities.surviving.items():
        deltas = _entity_deltas(earlier.declaration, later.declaration)
        if deltas:
            yield EntityAltered(identity, deltas)


def _attribute_operations(matching: Matching) -> Iterator[EvolutionOperation]:
    for identity in matching.attributes.added:
        if identity.entity not in matching.entities.added:
            yield AttributeAdded(identity)
    for identity in matching.attributes.removed:
        if identity.entity not in matching.entities.removed:
            yield AttributeRemoved(identity)
    for identity, (earlier, later) in matching.attributes.surviving.items():
        deltas = _attribute_deltas(earlier, later)
        if deltas:
            yield AttributeAltered(identity, deltas)


def _added(entity: EntityMetadata) -> EvolutionOperation:
    """The one entity-level addition for ``entity``'s role in the later endpoint."""
    if isinstance(entity.inheritance, ConcreteSubtype):
        return ConcreteSubtypeAdded(entity.identity)
    return EntityAdded(entity.identity)


def _removed(entity: EntityMetadata) -> EvolutionOperation:
    """The one entity-level removal for ``entity``'s role in the earlier endpoint."""
    if isinstance(entity.inheritance, ConcreteSubtype):
        return ConcreteSubtypeRemoved(entity.identity)
    return EntityRemoved(entity.identity)


def _entity_deltas(earlier: EntityMetadata, later: EntityMetadata) -> tuple[EntityDelta, ...]:
    """The Entity's own changed declarations, in the fixed field order.

    Inheritance is compared as one whole value, so a role, parent, strategy, tag
    Column, and tag value are never reported as contradictory parallel changes.
    """
    deltas: list[EntityDelta] = []
    if earlier.declared_container != later.declared_container:
        deltas.append(StorageContainerChanged(earlier.declared_container, later.declared_container))
    if earlier.declared_persistence != later.declared_persistence:
        deltas.append(PersistenceChanged(earlier.declared_persistence, later.declared_persistence))
    if earlier.declared_layout != later.declared_layout:
        deltas.append(StorageLayoutChanged(earlier.declared_layout, later.declared_layout))
    if earlier.inheritance != later.inheritance:
        deltas.append(InheritanceChanged(earlier.inheritance, later.inheritance))
    return tuple(deltas)


def _attribute_deltas(
    earlier: AttributeMetadata, later: AttributeMetadata
) -> tuple[AttributeDelta, ...]:
    """The Attribute's changed declarations, in the fixed field order.

    The derived framework-ownership designation is never a delta of its own: the
    optimistic-locking and As-Of Axis operations report its independent causes.
    """
    deltas: list[AttributeDelta] = []
    if earlier.type != later.type:
        deltas.append(TypeChanged(earlier.type, later.type))
    if earlier.storage != later.storage:
        deltas.append(StorageChanged(earlier.storage, later.storage))
    if earlier.primary_key != later.primary_key:
        deltas.append(PrimaryKeyChanged(earlier.primary_key, later.primary_key))
    if earlier.nullable != later.nullable:
        deltas.append(NullabilityChanged(earlier.nullable, later.nullable))
    if earlier.max_length != later.max_length:
        deltas.append(MaximumLengthChanged(earlier.max_length, later.max_length))
    if earlier.read_only != later.read_only:
        deltas.append(ReadOnlyChanged(earlier.read_only, later.read_only))
    if earlier.optimistic_locking != later.optimistic_locking:
        deltas.append(
            OptimisticLockingChanged(earlier.optimistic_locking, later.optimistic_locking)
        )
    return tuple(deltas)


def _ordered(operations: Iterable[EvolutionOperation]) -> tuple[EvolutionOperation, ...]:
    return tuple(sorted(operations, key=canonical_operation_key))
