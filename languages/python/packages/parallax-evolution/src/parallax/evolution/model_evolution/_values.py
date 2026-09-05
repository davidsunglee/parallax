"""The closed Model Evolution vocabulary: operations, field deltas, Behavioral
Impacts, coordination requirements, and the two evolution results.

Every name ADR 0063 fixes is one frozen slotted record with no behavior, joined
by ``type`` unions a type checker matches exhaustively. A field delta name has
exactly one value type wherever it appears, so one class serves every owner that
carries it and the corpus spells each delta the same way everywhere.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

from parallax.core.base import NeutralType
from parallax.core.metamodel import (
    AsOfAxisLocation,
    AttributeIdentity,
    AttributeLocation,
    AttributePrimaryKey,
    Cardinality,
    EntityIdentity,
    EntityLocation,
    IndexIdentity,
    IndexLocation,
    Metamodel,
    ModelLocation,
    ModelLocationKey,
    Multiplicity,
    PersistenceMode,
    RelationshipIdentity,
    RelationshipJoin,
    RelationshipLocation,
    RelationshipOrder,
    StorageContainer,
    StorageLayout,
    StorageLocation,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeLocation,
    ValueObjectIdentity,
    ValueObjectLocation,
    canonical_location_key,
)
from parallax.core.metamodel import (
    InheritanceMetadata as Inheritance,
)
from parallax.core.metamodel import (
    RelationshipDeclaration as RelationshipFacts,
)

__all__ = [
    "ABSENT",
    "AS_OF_AXIS_DELTA_ORDER",
    "ATTRIBUTE_DELTA_ORDER",
    "BEHAVIORAL_IMPACT_ORDER",
    "COORDINATION_REASON_ORDER",
    "ENTITY_DELTA_ORDER",
    "INDEX_DELTA_ORDER",
    "LOCKING_FALLBACK",
    "RELATIONSHIP_DELTA_ORDER",
    "VALUE_OBJECT_ATTRIBUTE_DELTA_ORDER",
    "VALUE_OBJECT_OCCURRENCE_DELTA_ORDER",
    "WRITES_DISABLED",
    "Absent",
    "AsOfAxisAdded",
    "AsOfAxisAltered",
    "AsOfAxisDelta",
    "AsOfAxisRemoved",
    "AttributeAdded",
    "AttributeAltered",
    "AttributeDelta",
    "AttributeRemoved",
    "AttributeWriteCapability",
    "BehavioralImpact",
    "CardinalityChanged",
    "ComponentsChanged",
    "ConcreteSubtypeAdded",
    "ConcreteSubtypeRemoved",
    "ConcurrencyControl",
    "ConcurrencyControlChanged",
    "CoordinatedEvolution",
    "CoordinationReason",
    "CoordinationRequirement",
    "DeclarationCollection",
    "DeclarationFormChanged",
    "DeclarationIdentity",
    "DeclarationOrderChanged",
    "DeletePropagation",
    "DeletePropagationChanged",
    "DependencyChanged",
    "EndAttributeChanged",
    "EntityAdded",
    "EntityAltered",
    "EntityDelta",
    "EntityRemoved",
    "EntitySelectionFacts",
    "EntityWriteCapability",
    "EntityWriteShape",
    "Evolution",
    "EvolutionOperation",
    "IndexAdded",
    "IndexAltered",
    "IndexDelta",
    "IndexRemoved",
    "InheritanceChanged",
    "JoinChanged",
    "LockingFallback",
    "MaximumLengthChanged",
    "MultiplicityChanged",
    "NullabilityChanged",
    "OccurrenceAdmissibility",
    "OptimisticLockingChanged",
    "OrderingChanged",
    "PersistenceChanged",
    "PrimaryKeyChanged",
    "QueryResultMembershipChanged",
    "QueryResultOrderingChanged",
    "ReadOnlyChanged",
    "RelationshipAdded",
    "RelationshipAltered",
    "RelationshipDelta",
    "RelationshipRemoved",
    "RelationshipSelectionFacts",
    "ReverseOfChanged",
    "ScalarAdmissibility",
    "SelectionFacts",
    "SelectionScope",
    "StartAttributeChanged",
    "StorageChanged",
    "StorageContainerChanged",
    "StorageLayoutChanged",
    "TemporalAxisFacts",
    "TransactionTimeGated",
    "TypeChanged",
    "UnilateralEvolution",
    "UniqueTuple",
    "UniquenessChanged",
    "UniquenessEnforcementChanged",
    "ValueAdmissibility",
    "ValueAdmissibilityChanged",
    "ValueObjectAttributeAdded",
    "ValueObjectAttributeAltered",
    "ValueObjectAttributeDelta",
    "ValueObjectAttributeRemoved",
    "ValueObjectOccurrenceAdded",
    "ValueObjectOccurrenceAltered",
    "ValueObjectOccurrenceDelta",
    "ValueObjectOccurrenceRemoved",
    "ValuePath",
    "VersionGated",
    "WriteCapabilityChanged",
    "WriteCapabilityFacts",
    "WriteScope",
    "WritesDisabled",
    "WritesEnabled",
    "canonical_operation_key",
]


@dataclass(frozen=True, slots=True)
class Absent:
    """The explicit fresh-provisioning earlier endpoint.

    Absence is authored, never inferred from an empty accepted model or from
    inspecting a physical schema.
    """


ABSENT: Final[Absent] = Absent()


# --------------------------------------------------------------------------- #
# Field deltas. Each name carries one value type wherever it appears.          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class StorageContainerChanged:
    """The accepted Storage Container of a surviving Entity."""

    earlier: StorageContainer | None
    later: StorageContainer | None


@dataclass(frozen=True, slots=True)
class PersistenceChanged:
    """The accepted Persistence Mode of a surviving Entity."""

    earlier: PersistenceMode | None
    later: PersistenceMode | None


@dataclass(frozen=True, slots=True)
class StorageLayoutChanged:
    """The accepted Storage Layout of a surviving Entity."""

    earlier: StorageLayout | None
    later: StorageLayout | None


@dataclass(frozen=True, slots=True)
class InheritanceChanged:
    """The complete Inheritance Metadata of a surviving Entity.

    The whole value is retained so role, parent, strategy, the
    table-per-hierarchy tag Column, and a concrete subtype's tag value can never
    be reported as contradictory parallel changes.
    """

    earlier: Inheritance | None
    later: Inheritance | None


@dataclass(frozen=True, slots=True)
class TypeChanged:
    """The accepted Neutral Type of a surviving scalar value position."""

    earlier: NeutralType
    later: NeutralType


@dataclass(frozen=True, slots=True)
class StorageChanged:
    """The accepted Storage Location of a surviving Attribute or top-level
    Value Object occurrence."""

    earlier: StorageLocation
    later: StorageLocation


@dataclass(frozen=True, slots=True)
class PrimaryKeyChanged:
    """The complete primary-key value of a surviving Attribute, so membership
    and generation cannot form an invalid combination."""

    earlier: AttributePrimaryKey
    later: AttributePrimaryKey


@dataclass(frozen=True, slots=True)
class NullabilityChanged:
    """The declared nullability of a surviving value position or occurrence."""

    earlier: bool
    later: bool


@dataclass(frozen=True, slots=True)
class MaximumLengthChanged:
    """The declared String maximum length of a surviving Attribute."""

    earlier: int | None
    later: int | None


@dataclass(frozen=True, slots=True)
class ReadOnlyChanged:
    """Whether a surviving Attribute refuses caller update input."""

    earlier: bool
    later: bool


@dataclass(frozen=True, slots=True)
class OptimisticLockingChanged:
    """Whether a surviving Attribute carries the explicit optimistic version."""

    earlier: bool
    later: bool


@dataclass(frozen=True, slots=True)
class MultiplicityChanged:
    """The declared multiplicity of a surviving Value Object occurrence."""

    earlier: Multiplicity
    later: Multiplicity


@dataclass(frozen=True, slots=True)
class DeclarationFormChanged:
    """The complete earlier and later Relationship declaration.

    Exclusive: no other Relationship delta accompanies it, because the two forms
    do not expose the same fields.
    """

    earlier: RelationshipFacts
    later: RelationshipFacts


@dataclass(frozen=True, slots=True)
class CardinalityChanged:
    """The declared cardinality of a surviving defining Relationship."""

    earlier: Cardinality
    later: Cardinality


@dataclass(frozen=True, slots=True)
class JoinChanged:
    """The accepted join of a surviving defining Relationship."""

    earlier: RelationshipJoin
    later: RelationshipJoin


@dataclass(frozen=True, slots=True)
class ReverseOfChanged:
    """The peer a surviving reverse Relationship names."""

    earlier: RelationshipIdentity
    later: RelationshipIdentity


@dataclass(frozen=True, slots=True)
class DependencyChanged:
    """Whether a surviving defining Relationship declares its target dependent."""

    earlier: bool
    later: bool


@dataclass(frozen=True, slots=True)
class OrderingChanged:
    """The declared ordering terms of a surviving Relationship."""

    earlier: tuple[RelationshipOrder, ...]
    later: tuple[RelationshipOrder, ...]


@dataclass(frozen=True, slots=True)
class StartAttributeChanged:
    """The start Attribute of a surviving As-Of Axis."""

    earlier: AttributeIdentity
    later: AttributeIdentity


@dataclass(frozen=True, slots=True)
class EndAttributeChanged:
    """The end Attribute of a surviving As-Of Axis."""

    earlier: AttributeIdentity
    later: AttributeIdentity


@dataclass(frozen=True, slots=True)
class ComponentsChanged:
    """The ordered components of a surviving authored Index.

    Component order is retained because it changes the physical access path;
    the uniqueness Behavioral Impact independently treats a tuple as unordered.
    """

    earlier: tuple[AttributeIdentity, ...]
    later: tuple[AttributeIdentity, ...]


@dataclass(frozen=True, slots=True)
class UniquenessChanged:
    """Whether a surviving authored Index enforces uniqueness."""

    earlier: bool
    later: bool


type EntityDelta = (
    StorageContainerChanged | PersistenceChanged | StorageLayoutChanged | InheritanceChanged
)
type AttributeDelta = (
    TypeChanged
    | StorageChanged
    | PrimaryKeyChanged
    | NullabilityChanged
    | MaximumLengthChanged
    | ReadOnlyChanged
    | OptimisticLockingChanged
)
type ValueObjectOccurrenceDelta = StorageChanged | MultiplicityChanged | NullabilityChanged
type ValueObjectAttributeDelta = TypeChanged | NullabilityChanged
type RelationshipDelta = (
    DeclarationFormChanged
    | CardinalityChanged
    | JoinChanged
    | ReverseOfChanged
    | DependencyChanged
    | OrderingChanged
)
type AsOfAxisDelta = StartAttributeChanged | EndAttributeChanged
type IndexDelta = ComponentsChanged | UniquenessChanged

ENTITY_DELTA_ORDER: Final[tuple[type, ...]] = (
    StorageContainerChanged,
    PersistenceChanged,
    StorageLayoutChanged,
    InheritanceChanged,
)
ATTRIBUTE_DELTA_ORDER: Final[tuple[type, ...]] = (
    TypeChanged,
    StorageChanged,
    PrimaryKeyChanged,
    NullabilityChanged,
    MaximumLengthChanged,
    ReadOnlyChanged,
    OptimisticLockingChanged,
)
VALUE_OBJECT_OCCURRENCE_DELTA_ORDER: Final[tuple[type, ...]] = (
    StorageChanged,
    MultiplicityChanged,
    NullabilityChanged,
)
VALUE_OBJECT_ATTRIBUTE_DELTA_ORDER: Final[tuple[type, ...]] = (TypeChanged, NullabilityChanged)
RELATIONSHIP_DELTA_ORDER: Final[tuple[type, ...]] = (
    DeclarationFormChanged,
    CardinalityChanged,
    JoinChanged,
    ReverseOfChanged,
    DependencyChanged,
    OrderingChanged,
)
AS_OF_AXIS_DELTA_ORDER: Final[tuple[type, ...]] = (StartAttributeChanged, EndAttributeChanged)
INDEX_DELTA_ORDER: Final[tuple[type, ...]] = (ComponentsChanged, UniquenessChanged)


# --------------------------------------------------------------------------- #
# Evolution Operations.                                                        #
# --------------------------------------------------------------------------- #
class DeclarationCollection(enum.Enum):
    """The local collections whose relative order one operation can describe."""

    ENTITY_ATTRIBUTES = "entityAttributes"
    ENTITY_RELATIONSHIPS = "entityRelationships"
    ENTITY_VALUE_OBJECTS = "entityValueObjects"
    ENTITY_INDICES = "entityIndices"
    VALUE_OBJECT_ATTRIBUTES = "valueObjectAttributes"
    NESTED_VALUE_OBJECTS = "nestedValueObjects"


type DeclarationIdentity = (
    AttributeIdentity
    | RelationshipIdentity
    | ValueObjectIdentity
    | ValueObjectAttributeIdentity
    | IndexIdentity
)


@dataclass(frozen=True, slots=True)
class EntityAdded:
    """A whole Entity present only in the later endpoint, members suppressed."""

    entity: EntityIdentity


@dataclass(frozen=True, slots=True)
class EntityRemoved:
    """A whole Entity present only in the earlier endpoint, members suppressed."""

    entity: EntityIdentity


@dataclass(frozen=True, slots=True)
class EntityAltered:
    """A surviving Entity whose own accepted facts differ."""

    entity: EntityIdentity
    deltas: tuple[EntityDelta, ...]


@dataclass(frozen=True, slots=True)
class ConcreteSubtypeAdded:
    """A concrete subtype present only in the later endpoint."""

    entity: EntityIdentity


@dataclass(frozen=True, slots=True)
class ConcreteSubtypeRemoved:
    """A concrete subtype present only in the earlier endpoint."""

    entity: EntityIdentity


@dataclass(frozen=True, slots=True)
class AttributeAdded:
    """A scalar Attribute present only in the later endpoint."""

    attribute: AttributeIdentity


@dataclass(frozen=True, slots=True)
class AttributeRemoved:
    """A scalar Attribute present only in the earlier endpoint."""

    attribute: AttributeIdentity


@dataclass(frozen=True, slots=True)
class AttributeAltered:
    """A surviving scalar Attribute whose accepted facts differ."""

    attribute: AttributeIdentity
    deltas: tuple[AttributeDelta, ...]


@dataclass(frozen=True, slots=True)
class ValueObjectOccurrenceAdded:
    """A top-level or nested occurrence present only in the later endpoint."""

    value_object: ValueObjectIdentity


@dataclass(frozen=True, slots=True)
class ValueObjectOccurrenceRemoved:
    """A top-level or nested occurrence present only in the earlier endpoint."""

    value_object: ValueObjectIdentity


@dataclass(frozen=True, slots=True)
class ValueObjectOccurrenceAltered:
    """A surviving occurrence whose accepted facts differ."""

    value_object: ValueObjectIdentity
    deltas: tuple[ValueObjectOccurrenceDelta, ...]


@dataclass(frozen=True, slots=True)
class ValueObjectAttributeAdded:
    """A Value Object scalar leaf present only in the later endpoint."""

    value_object_attribute: ValueObjectAttributeIdentity


@dataclass(frozen=True, slots=True)
class ValueObjectAttributeRemoved:
    """A Value Object scalar leaf present only in the earlier endpoint."""

    value_object_attribute: ValueObjectAttributeIdentity


@dataclass(frozen=True, slots=True)
class ValueObjectAttributeAltered:
    """A surviving Value Object scalar leaf whose accepted facts differ."""

    value_object_attribute: ValueObjectAttributeIdentity
    deltas: tuple[ValueObjectAttributeDelta, ...]


@dataclass(frozen=True, slots=True)
class RelationshipAdded:
    """A Relationship declaration present only in the later endpoint."""

    relationship: RelationshipIdentity


@dataclass(frozen=True, slots=True)
class RelationshipRemoved:
    """A Relationship declaration present only in the earlier endpoint."""

    relationship: RelationshipIdentity


@dataclass(frozen=True, slots=True)
class RelationshipAltered:
    """A surviving Relationship declaration whose accepted facts differ."""

    relationship: RelationshipIdentity
    deltas: tuple[RelationshipDelta, ...]


@dataclass(frozen=True, slots=True)
class AsOfAxisAdded:
    """An As-Of Axis present only in the later endpoint."""

    entity: EntityIdentity
    dimension: TemporalDimension


@dataclass(frozen=True, slots=True)
class AsOfAxisRemoved:
    """An As-Of Axis present only in the earlier endpoint."""

    entity: EntityIdentity
    dimension: TemporalDimension


@dataclass(frozen=True, slots=True)
class AsOfAxisAltered:
    """A surviving As-Of Axis whose endpoint Attributes differ."""

    entity: EntityIdentity
    dimension: TemporalDimension
    deltas: tuple[AsOfAxisDelta, ...]


@dataclass(frozen=True, slots=True)
class IndexAdded:
    """An authored secondary Index present only in the later endpoint."""

    index: IndexIdentity


@dataclass(frozen=True, slots=True)
class IndexRemoved:
    """An authored secondary Index present only in the earlier endpoint."""

    index: IndexIdentity


@dataclass(frozen=True, slots=True)
class IndexAltered:
    """A surviving authored secondary Index whose definition differs."""

    index: IndexIdentity
    deltas: tuple[IndexDelta, ...]


@dataclass(frozen=True, slots=True)
class DeclarationOrderChanged:
    """One local collection whose surviving declarations changed relative order.

    ``earlier`` and ``later`` contain only identities present in both endpoints,
    so inserting a new member between two existing ones is addition rather than
    reordering.
    """

    collection: DeclarationCollection
    owner: EntityIdentity | ValueObjectIdentity
    earlier: tuple[DeclarationIdentity, ...]
    later: tuple[DeclarationIdentity, ...]


type EvolutionOperation = (
    EntityAdded
    | EntityRemoved
    | EntityAltered
    | ConcreteSubtypeAdded
    | ConcreteSubtypeRemoved
    | AttributeAdded
    | AttributeRemoved
    | AttributeAltered
    | ValueObjectOccurrenceAdded
    | ValueObjectOccurrenceRemoved
    | ValueObjectOccurrenceAltered
    | ValueObjectAttributeAdded
    | ValueObjectAttributeRemoved
    | ValueObjectAttributeAltered
    | RelationshipAdded
    | RelationshipRemoved
    | RelationshipAltered
    | AsOfAxisAdded
    | AsOfAxisRemoved
    | AsOfAxisAltered
    | IndexAdded
    | IndexRemoved
    | IndexAltered
    | DeclarationOrderChanged
)


def _model_location(operation: EvolutionOperation) -> ModelLocation:
    """The Model Location ``operation`` describes.

    A :class:`DeclarationOrderChanged` describes its owning collection, so its
    location is the owner's; the collection itself distinguishes two operations
    on one owner and is part of :func:`canonical_operation_key` instead.
    """
    match operation:
        case (
            EntityAdded()
            | EntityRemoved()
            | EntityAltered()
            | ConcreteSubtypeAdded()
            | ConcreteSubtypeRemoved()
        ):
            return EntityLocation(operation.entity)
        case AttributeAdded() | AttributeRemoved() | AttributeAltered():
            return AttributeLocation(operation.attribute)
        case RelationshipAdded() | RelationshipRemoved() | RelationshipAltered():
            return RelationshipLocation(operation.relationship)
        case (
            ValueObjectOccurrenceAdded()
            | ValueObjectOccurrenceRemoved()
            | ValueObjectOccurrenceAltered()
        ):
            return ValueObjectLocation(operation.value_object)
        case (
            ValueObjectAttributeAdded()
            | ValueObjectAttributeRemoved()
            | ValueObjectAttributeAltered()
        ):
            return ValueObjectAttributeLocation(operation.value_object_attribute)
        case AsOfAxisAdded() | AsOfAxisRemoved() | AsOfAxisAltered():
            return AsOfAxisLocation(operation.entity, operation.dimension)
        case IndexAdded() | IndexRemoved() | IndexAltered():
            return IndexLocation(operation.index)
        case DeclarationOrderChanged():
            owner = operation.owner
            if isinstance(owner, ValueObjectIdentity):
                return ValueObjectLocation(owner)
            return EntityLocation(owner)


_DECLARATION_ORDER_RANK: Final[dict[DeclarationCollection, int]] = {
    collection: rank for rank, collection in enumerate(DeclarationCollection)
}


def canonical_operation_key(operation: EvolutionOperation) -> tuple[int, ModelLocationKey, int]:
    """The inspection-order key: canonical Model Location, with every
    declaration-order operation sorted after every declaration operation and
    then by its collection.

    Add, remove, and alter cannot tie at one logical identity, so no
    operation-kind rank is needed and a rename's removal and addition stay in
    identity order rather than being forced removal-first.
    """
    if isinstance(operation, DeclarationOrderChanged):
        return (
            1,
            canonical_location_key(_model_location(operation)),
            _DECLARATION_ORDER_RANK[operation.collection],
        )
    return (0, canonical_location_key(_model_location(operation)), 0)


# --------------------------------------------------------------------------- #
# Behavioral Impacts and their endpoint facts.                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class UniqueTuple:
    """One secondary uniqueness rule as an unordered Attribute set, rendered in
    canonical identity order so equivalent authored Indices collapse."""

    attributes: tuple[AttributeIdentity, ...]


@dataclass(frozen=True, slots=True)
class ScalarAdmissibility:
    """The accepted value domain of one scalar position."""

    type: NeutralType
    nullable: bool
    max_length: int | None


@dataclass(frozen=True, slots=True)
class OccurrenceAdmissibility:
    """The accepted value domain of one Value Object occurrence position."""

    nullable: bool


type ValueAdmissibility = ScalarAdmissibility | OccurrenceAdmissibility
type ValuePath = AttributeIdentity | ValueObjectIdentity | ValueObjectAttributeIdentity


class DeletePropagation(enum.Enum):
    """The effective dependency policy of one Relationship."""

    PROPAGATES = "Propagates"
    DOES_NOT_PROPAGATE = "DoesNotPropagate"


@dataclass(frozen=True, slots=True)
class LockingFallback:
    """Reads take shared locks and writes carry no gate."""


LOCKING_FALLBACK: Final[LockingFallback] = LockingFallback()


@dataclass(frozen=True, slots=True)
class VersionGated:
    """Writes gate on an explicit version Attribute."""

    attribute: AttributeIdentity


@dataclass(frozen=True, slots=True)
class TransactionTimeGated:
    """Writes gate on the Transaction-Time start Attribute."""

    start_attribute: AttributeIdentity


type ConcurrencyControl = LockingFallback | VersionGated | TransactionTimeGated


@dataclass(frozen=True, slots=True)
class TemporalAxisFacts:
    """One axis of a selection's effective Temporal Shape."""

    dimension: TemporalDimension
    start_attribute: AttributeIdentity
    end_attribute: AttributeIdentity


@dataclass(frozen=True, slots=True)
class EntitySelectionFacts:
    """The predicate-free selection rule of one Entity position.

    ``axes`` is in canonical dimension order and names the effective Temporal
    Shape: empty is Non-Temporal, one Transaction-Time axis is
    Transaction-Time-Only, and both axes are Bitemporal.
    """

    concrete_entities: tuple[EntityIdentity, ...]
    axes: tuple[TemporalAxisFacts, ...]


@dataclass(frozen=True, slots=True)
class RelationshipSelectionFacts:
    """The predicate-free selection rule of one Relationship position."""

    target: EntityIdentity
    join: RelationshipJoin


type SelectionScope = EntityIdentity | RelationshipIdentity
type SelectionFacts = EntitySelectionFacts | RelationshipSelectionFacts


class EntityWriteShape(enum.Enum):
    """The effective temporal shape of an enabled Entity write surface."""

    NON_TEMPORAL = "NonTemporal"
    TRANSACTION_TIME_ONLY = "TransactionTimeOnly"
    BITEMPORAL = "Bitemporal"


@dataclass(frozen=True, slots=True)
class WritesDisabled:
    """The Entity admits no persistence operation."""


WRITES_DISABLED: Final[WritesDisabled] = WritesDisabled()


@dataclass(frozen=True, slots=True)
class WritesEnabled:
    """The Entity admits persistence operations of one temporal write shape."""

    shape: EntityWriteShape


type EntityWriteCapability = WritesDisabled | WritesEnabled


class AttributeWriteCapability(enum.Enum):
    """What caller input one Attribute admits."""

    FRAMEWORK_OWNED = "FrameworkOwned"
    CALLER_INSERT_ONLY = "CallerInsertOnly"
    CALLER_INSERT_AND_UPDATE = "CallerInsertAndUpdate"


type WriteScope = EntityIdentity | AttributeIdentity
type WriteCapabilityFacts = EntityWriteCapability | AttributeWriteCapability


@dataclass(frozen=True, slots=True)
class UniquenessEnforcementChanged:
    """One surviving Entity whose semantic set of secondary uniqueness rules
    differs. Derived primary-key uniqueness is excluded."""

    scope: EntityIdentity
    earlier: tuple[UniqueTuple, ...]
    later: tuple[UniqueTuple, ...]
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class ValueAdmissibilityChanged:
    """One surviving value-bearing path whose accepted domain differs."""

    scope: ValuePath
    earlier: ValueAdmissibility
    later: ValueAdmissibility
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class DeletePropagationChanged:
    """One surviving Relationship whose effective dependency policy differs."""

    scope: RelationshipIdentity
    earlier: DeletePropagation
    later: DeletePropagation
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class ConcurrencyControlChanged:
    """One surviving Entity whose behavior under the ``optimistic`` Concurrency
    Preference differs."""

    scope: EntityIdentity
    earlier: ConcurrencyControl
    later: ConcurrencyControl
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class QueryResultMembershipChanged:
    """One surviving query position whose predicate-free selection rule differs."""

    scope: SelectionScope
    earlier: SelectionFacts
    later: SelectionFacts
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class QueryResultOrderingChanged:
    """One surviving Relationship whose normalized ordering rule differs."""

    scope: RelationshipIdentity
    earlier: tuple[RelationshipOrder, ...]
    later: tuple[RelationshipOrder, ...]
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class WriteCapabilityChanged:
    """One surviving Entity or Attribute whose effective write surface differs."""

    scope: WriteScope
    earlier: WriteCapabilityFacts
    later: WriteCapabilityFacts
    caused_by: tuple[EvolutionOperation, ...]


type BehavioralImpact = (
    UniquenessEnforcementChanged
    | ValueAdmissibilityChanged
    | DeletePropagationChanged
    | ConcurrencyControlChanged
    | QueryResultMembershipChanged
    | QueryResultOrderingChanged
    | WriteCapabilityChanged
)

BEHAVIORAL_IMPACT_ORDER: Final[tuple[type, ...]] = (
    UniquenessEnforcementChanged,
    ValueAdmissibilityChanged,
    DeletePropagationChanged,
    ConcurrencyControlChanged,
    QueryResultMembershipChanged,
    QueryResultOrderingChanged,
    WriteCapabilityChanged,
)


# --------------------------------------------------------------------------- #
# Coordination and the two evolution results.                                  #
# --------------------------------------------------------------------------- #
class CoordinationReason(enum.Enum):
    """Why unilateral application of one operation is unavailable."""

    AUTHORING_SURFACE_CHANGE_REQUIRED = "AuthoringSurfaceChangeRequired"
    DATABASE_MIGRATION_REQUIRED = "DatabaseMigrationRequired"


COORDINATION_REASON_ORDER: Final[tuple[CoordinationReason, ...]] = (
    CoordinationReason.AUTHORING_SURFACE_CHANGE_REQUIRED,
    CoordinationReason.DATABASE_MIGRATION_REQUIRED,
)


@dataclass(frozen=True, slots=True)
class CoordinationRequirement:
    """One coordinated operation and its nonempty fixed-order reason set."""

    operation: EvolutionOperation
    reasons: tuple[CoordinationReason, ...]


@dataclass(frozen=True, slots=True)
class UnilateralEvolution:
    """A complete difference a live tenant may apply through the schema path.

    ``earlier`` is ``None`` only for the fresh-provisioning evolution from
    :data:`ABSENT`.
    """

    earlier: Metamodel | None
    later: Metamodel
    operations: tuple[EvolutionOperation, ...]
    behavioral_impacts: tuple[BehavioralImpact, ...]
    overlap_visible_operations: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class CoordinatedEvolution:
    """A complete difference whose application needs authoring, data, or rollout
    coordination. ``coordination_requirements`` is nonempty."""

    earlier: Metamodel
    later: Metamodel
    operations: tuple[EvolutionOperation, ...]
    behavioral_impacts: tuple[BehavioralImpact, ...]
    coordination_requirements: tuple[CoordinationRequirement, ...]


type Evolution = UnilateralEvolution | CoordinatedEvolution
