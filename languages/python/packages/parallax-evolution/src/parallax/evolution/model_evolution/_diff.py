"""Evolution Operations from one :class:`~._matching.Matching`, in inspection order.

A parent addition or removal suppresses every operation for the declarations it
contains, so an Entity present in one endpoint alone is one entity-level
operation and nothing else — which is also what makes the fresh-provisioning
evolution, whose every Entity is an addition, the same code path rather than a
second differ. A Value Object occurrence suppresses its nested members the same
way, at every depth.

The generic Entity variants exclude concrete-subtype add and remove, and each
Entity's role is read from the endpoint that declares it: the later model for an
addition, the earlier one for a removal. An alteration reports the accepted
declarations that differ; whether the difference needs coordination is the
classifier's question, asked of the effective facts.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import cast

from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeMetadata,
    ConcreteSubtype,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    EntityMetadata,
    IndexMetadata,
    RelationshipDeclaration,
    ReverseRelationshipDeclaration,
    ValueObjectAttributeMetadata,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.evolution.model_evolution._matching import Matching, Occurrence
from parallax.evolution.model_evolution._values import (
    AsOfAxisAdded,
    AsOfAxisAltered,
    AsOfAxisDelta,
    AsOfAxisRemoved,
    AttributeAdded,
    AttributeAltered,
    AttributeDelta,
    AttributeRemoved,
    CardinalityChanged,
    ComponentsChanged,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    DeclarationFormChanged,
    DeclarationOrderChanged,
    DependencyChanged,
    EndAttributeChanged,
    EntityAdded,
    EntityAltered,
    EntityDelta,
    EntityRemoved,
    EvolutionOperation,
    IndexAdded,
    IndexAltered,
    IndexDelta,
    IndexRemoved,
    InheritanceChanged,
    JoinChanged,
    MaximumLengthChanged,
    MultiplicityChanged,
    NullabilityChanged,
    OptimisticLockingChanged,
    OrderingChanged,
    PersistenceChanged,
    PrimaryKeyChanged,
    ReadOnlyChanged,
    RelationshipAdded,
    RelationshipAltered,
    RelationshipDelta,
    RelationshipRemoved,
    ReverseOfChanged,
    StartAttributeChanged,
    StorageChanged,
    StorageContainerChanged,
    StorageLayoutChanged,
    TypeChanged,
    UniquenessChanged,
    ValueObjectAttributeAdded,
    ValueObjectAttributeAltered,
    ValueObjectAttributeDelta,
    ValueObjectAttributeRemoved,
    ValueObjectOccurrenceAdded,
    ValueObjectOccurrenceAltered,
    ValueObjectOccurrenceDelta,
    ValueObjectOccurrenceRemoved,
    canonical_operation_key,
)

__all__ = ["diff"]


def diff(matching: Matching) -> tuple[EvolutionOperation, ...]:
    """Every Evolution Operation the two endpoints differ by."""
    return _ordered(
        [
            *_entity_operations(matching),
            *_attribute_operations(matching),
            *_value_object_operations(matching),
            *_value_object_attribute_operations(matching),
            *_relationship_operations(matching),
            *_as_of_axis_operations(matching),
            *_index_operations(matching),
            *_declaration_order_operations(matching),
        ]
    )


# --------------------------------------------------------------------------- #
# Suppression: a contained declaration is described by its container's own      #
# addition or removal, never a second time.                                     #
# --------------------------------------------------------------------------- #
def _entity_covers(matching: Matching, entity: EntityIdentity, *, added: bool) -> bool:
    return entity in (matching.entities.added if added else matching.entities.removed)


def _occurrence_covers(
    matching: Matching, occurrence: ValueObjectIdentity, *, added: bool, own: bool
) -> bool:
    """Whether an ancestor occurrence — or, with ``own``, the occurrence itself —
    is present in one endpoint alone."""
    paired = matching.value_objects.added if added else matching.value_objects.removed
    depth = len(occurrence.path) + 1 if own else len(occurrence.path)
    return any(
        ValueObjectIdentity(occurrence.entity, occurrence.path[:length]) in paired
        for length in range(1, depth)
    )


def _suppressed_occurrence(
    matching: Matching, occurrence: ValueObjectIdentity, *, added: bool
) -> bool:
    return _entity_covers(matching, occurrence.entity, added=added) or _occurrence_covers(
        matching, occurrence, added=added, own=False
    )


def _suppressed_member(matching: Matching, occurrence: ValueObjectIdentity, *, added: bool) -> bool:
    return _entity_covers(matching, occurrence.entity, added=added) or _occurrence_covers(
        matching, occurrence, added=added, own=True
    )


# --------------------------------------------------------------------------- #
# One generator per declaration kind.                                          #
# --------------------------------------------------------------------------- #
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
        if not _entity_covers(matching, identity.entity, added=True):
            yield AttributeAdded(identity)
    for identity in matching.attributes.removed:
        if not _entity_covers(matching, identity.entity, added=False):
            yield AttributeRemoved(identity)
    for identity, (earlier, later) in matching.attributes.surviving.items():
        deltas = _attribute_deltas(earlier, later)
        if deltas:
            yield AttributeAltered(identity, deltas)


def _value_object_operations(matching: Matching) -> Iterator[EvolutionOperation]:
    for identity in matching.value_objects.added:
        if not _suppressed_occurrence(matching, identity, added=True):
            yield ValueObjectOccurrenceAdded(identity)
    for identity in matching.value_objects.removed:
        if not _suppressed_occurrence(matching, identity, added=False):
            yield ValueObjectOccurrenceRemoved(identity)
    for identity, (earlier, later) in matching.value_objects.surviving.items():
        deltas = _occurrence_deltas(identity, earlier, later)
        if deltas:
            yield ValueObjectOccurrenceAltered(identity, deltas)


def _value_object_attribute_operations(matching: Matching) -> Iterator[EvolutionOperation]:
    for identity in matching.value_object_attributes.added:
        if not _suppressed_member(matching, identity.value_object, added=True):
            yield ValueObjectAttributeAdded(identity)
    for identity in matching.value_object_attributes.removed:
        if not _suppressed_member(matching, identity.value_object, added=False):
            yield ValueObjectAttributeRemoved(identity)
    for identity, (earlier, later) in matching.value_object_attributes.surviving.items():
        deltas = _value_object_attribute_deltas(earlier, later)
        if deltas:
            yield ValueObjectAttributeAltered(identity, deltas)


def _relationship_operations(matching: Matching) -> Iterator[EvolutionOperation]:
    for identity in matching.relationships.added:
        if not _entity_covers(matching, identity.source_entity, added=True):
            yield RelationshipAdded(identity)
    for identity in matching.relationships.removed:
        if not _entity_covers(matching, identity.source_entity, added=False):
            yield RelationshipRemoved(identity)
    for identity, (earlier, later) in matching.relationships.surviving.items():
        deltas = _relationship_deltas(earlier.declaration, later.declaration)
        if deltas:
            yield RelationshipAltered(identity, deltas)


def _as_of_axis_operations(matching: Matching) -> Iterator[EvolutionOperation]:
    for entity, dimension in matching.as_of_axes.added:
        if not _entity_covers(matching, entity, added=True):
            yield AsOfAxisAdded(entity, dimension)
    for entity, dimension in matching.as_of_axes.removed:
        if not _entity_covers(matching, entity, added=False):
            yield AsOfAxisRemoved(entity, dimension)
    for (entity, dimension), (earlier, later) in matching.as_of_axes.surviving.items():
        deltas = _axis_deltas(earlier, later)
        if deltas:
            yield AsOfAxisAltered(entity, dimension, deltas)


def _index_operations(matching: Matching) -> Iterator[EvolutionOperation]:
    for identity in matching.indices.added:
        if not _entity_covers(matching, identity.entity, added=True):
            yield IndexAdded(identity)
    for identity in matching.indices.removed:
        if not _entity_covers(matching, identity.entity, added=False):
            yield IndexRemoved(identity)
    for identity, (earlier, later) in matching.indices.surviving.items():
        deltas = _index_deltas(earlier, later)
        if deltas:
            yield IndexAltered(identity, deltas)


def _declaration_order_operations(matching: Matching) -> Iterator[EvolutionOperation]:
    """One operation per local collection whose surviving declarations moved.

    The comparison is over surviving identities alone, so an insertion between
    two of them is the addition it already is, and the later model is never
    normalized back into the earlier order.
    """
    for order in matching.collection_orders:
        if order.earlier != order.later:
            yield DeclarationOrderChanged(
                collection=order.collection,
                owner=order.owner,
                earlier=order.earlier,
                later=order.later,
            )


# --------------------------------------------------------------------------- #
# Field deltas, each in the fixed field order its alteration fixes.            #
# --------------------------------------------------------------------------- #
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


def _occurrence_deltas(
    identity: ValueObjectIdentity, earlier: Occurrence, later: Occurrence
) -> tuple[ValueObjectOccurrenceDelta, ...]:
    """The occurrence's changed declarations, in the fixed field order.

    Only a top-level occurrence owns a Storage Location, so only a containment
    path of length one can report one changing.
    """
    deltas: list[ValueObjectOccurrenceDelta] = []
    if len(identity.path) == 1:
        before = cast("ValueObjectMetadata", earlier).storage
        after = cast("ValueObjectMetadata", later).storage
        if before != after:
            deltas.append(StorageChanged(before, after))
    if earlier.multiplicity != later.multiplicity:
        deltas.append(MultiplicityChanged(earlier.multiplicity, later.multiplicity))
    if earlier.nullable != later.nullable:
        deltas.append(NullabilityChanged(earlier.nullable, later.nullable))
    return tuple(deltas)


def _value_object_attribute_deltas(
    earlier: ValueObjectAttributeMetadata, later: ValueObjectAttributeMetadata
) -> tuple[ValueObjectAttributeDelta, ...]:
    """A scalar leaf's changed declarations; it owns no Column, key, or bound."""
    deltas: list[ValueObjectAttributeDelta] = []
    if earlier.type != later.type:
        deltas.append(TypeChanged(earlier.type, later.type))
    if earlier.nullable != later.nullable:
        deltas.append(NullabilityChanged(earlier.nullable, later.nullable))
    return tuple(deltas)


def _relationship_deltas(
    earlier: RelationshipDeclaration, later: RelationshipDeclaration
) -> tuple[RelationshipDelta, ...]:
    """The Relationship's changed declarations, in the fixed field order.

    A declaration that changed form retains both complete declarations and
    reports nothing else, because the defining and reverse forms do not expose
    the same fields.
    """
    deltas: list[RelationshipDelta] = []
    match earlier, later:
        case DefiningRelationshipDeclaration(), DefiningRelationshipDeclaration():
            if earlier.cardinality != later.cardinality:
                deltas.append(CardinalityChanged(earlier.cardinality, later.cardinality))
            if earlier.join != later.join:
                deltas.append(JoinChanged(earlier.join, later.join))
            if earlier.dependent != later.dependent:
                deltas.append(DependencyChanged(earlier.dependent, later.dependent))
        case ReverseRelationshipDeclaration(), ReverseRelationshipDeclaration():
            if earlier.reverse_of != later.reverse_of:
                deltas.append(ReverseOfChanged(earlier.reverse_of, later.reverse_of))
        case _:
            return (DeclarationFormChanged(earlier, later),)
    if earlier.order_by != later.order_by:
        deltas.append(OrderingChanged(earlier.order_by, later.order_by))
    return tuple(deltas)


def _axis_deltas(earlier: AsOfAxisMetadata, later: AsOfAxisMetadata) -> tuple[AsOfAxisDelta, ...]:
    """The surviving axis's changed endpoints; its dimension is its identity."""
    deltas: list[AsOfAxisDelta] = []
    if earlier.start_attribute != later.start_attribute:
        deltas.append(StartAttributeChanged(earlier.start_attribute, later.start_attribute))
    if earlier.end_attribute != later.end_attribute:
        deltas.append(EndAttributeChanged(earlier.end_attribute, later.end_attribute))
    return tuple(deltas)


def _index_deltas(earlier: IndexMetadata, later: IndexMetadata) -> tuple[IndexDelta, ...]:
    """The authored Index's changed definition; component order is retained
    because it changes the physical access path."""
    deltas: list[IndexDelta] = []
    if earlier.attributes != later.attributes:
        deltas.append(ComponentsChanged(earlier.attributes, later.attributes))
    if earlier.unique != later.unique:
        deltas.append(UniquenessChanged(earlier.unique, later.unique))
    return tuple(deltas)


def _ordered(operations: Iterable[EvolutionOperation]) -> tuple[EvolutionOperation, ...]:
    return tuple(sorted(operations, key=canonical_operation_key))
