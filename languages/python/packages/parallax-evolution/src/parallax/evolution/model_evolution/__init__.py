"""``parallax.evolution.model_evolution`` enforcement scope (m-model-evolution).

The total, ordered description of every difference between two accepted
Metamodels, named in the model's own terms. :func:`evolve` returns the closed
choice of :class:`UnilateralEvolution` — the only kind a live tenant may apply
through the schema path — or :class:`CoordinatedEvolution`, which is an equally
complete description whose application needs authoring, data, or rollout
coordination. Both retain their accepted endpoints, so a consumer resolves any
identity an operation names without holding a model of its own.

The description is at model altitude and is pure: it makes no provider or
database call, prescribes no migration procedure, severity, or retry, and names
no dialect. Physical statements are ``m-schema-delta``'s, derived from a
Unilateral Evolution and the later endpoint's Storage Layout.

``m-model-evolution`` depends on ``m-metamodel`` for the accepted declarations
and identities, and on ``m-inheritance``, ``m-relationship``,
``m-temporal-read``, and ``m-opt-lock`` for the effective facts classification
and Behavioral Impacts compare; it re-derives none of those facets.
"""

from __future__ import annotations

from typing import overload

from parallax.core.metamodel import Metamodel
from parallax.evolution.model_evolution._classify import classify
from parallax.evolution.model_evolution._diff import diff
from parallax.evolution.model_evolution._impacts import impacts
from parallax.evolution.model_evolution._matching import Matching, match
from parallax.evolution.model_evolution._values import (
    ABSENT,
    AS_OF_AXIS_DELTA_ORDER,
    ATTRIBUTE_DELTA_ORDER,
    BEHAVIORAL_IMPACT_ORDER,
    COORDINATION_REASON_ORDER,
    ENTITY_DELTA_ORDER,
    INDEX_DELTA_ORDER,
    LOCKING_FALLBACK,
    RELATIONSHIP_DELTA_ORDER,
    VALUE_OBJECT_ATTRIBUTE_DELTA_ORDER,
    VALUE_OBJECT_OCCURRENCE_DELTA_ORDER,
    WRITES_DISABLED,
    Absent,
    AsOfAxisAdded,
    AsOfAxisAltered,
    AsOfAxisDelta,
    AsOfAxisRemoved,
    AttributeAdded,
    AttributeAltered,
    AttributeDelta,
    AttributeRemoved,
    AttributeWriteCapability,
    BehavioralImpact,
    CardinalityChanged,
    ComponentsChanged,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    ConcurrencyControl,
    ConcurrencyControlChanged,
    CoordinatedEvolution,
    CoordinationReason,
    CoordinationRequirement,
    DeclarationCollection,
    DeclarationFormChanged,
    DeclarationIdentity,
    DeclarationOrderChanged,
    DeletePropagation,
    DeletePropagationChanged,
    DependencyChanged,
    EndAttributeChanged,
    EntityAdded,
    EntityAltered,
    EntityDelta,
    EntityRemoved,
    EntitySelectionFacts,
    EntityWriteCapability,
    EntityWriteShape,
    Evolution,
    EvolutionOperation,
    IndexAdded,
    IndexAltered,
    IndexDelta,
    IndexRemoved,
    InheritanceChanged,
    JoinChanged,
    LockingFallback,
    MaximumLengthChanged,
    MultiplicityChanged,
    NullabilityChanged,
    OccurrenceAdmissibility,
    OptimisticLockingChanged,
    OrderingChanged,
    PersistenceChanged,
    PrimaryKeyChanged,
    QueryResultMembershipChanged,
    QueryResultOrderingChanged,
    ReadOnlyChanged,
    RelationshipAdded,
    RelationshipAltered,
    RelationshipDelta,
    RelationshipRemoved,
    RelationshipSelectionFacts,
    ReverseOfChanged,
    ScalarAdmissibility,
    SelectionFacts,
    SelectionScope,
    StartAttributeChanged,
    StorageChanged,
    StorageContainerChanged,
    StorageLayoutChanged,
    TemporalAxisFacts,
    TransactionTimeGated,
    TypeChanged,
    UnilateralEvolution,
    UniquenessChanged,
    UniquenessEnforcementChanged,
    UniqueTuple,
    ValueAdmissibility,
    ValueAdmissibilityChanged,
    ValueObjectAttributeAdded,
    ValueObjectAttributeAltered,
    ValueObjectAttributeDelta,
    ValueObjectAttributeRemoved,
    ValueObjectOccurrenceAdded,
    ValueObjectOccurrenceAltered,
    ValueObjectOccurrenceDelta,
    ValueObjectOccurrenceRemoved,
    ValuePath,
    VersionGated,
    WriteCapabilityChanged,
    WriteCapabilityFacts,
    WriteScope,
    WritesDisabled,
    WritesEnabled,
    canonical_operation_key,
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
    "evolve",
]


@overload
def evolve(earlier: Absent, later: Metamodel) -> UnilateralEvolution: ...


@overload
def evolve(earlier: Metamodel, later: Metamodel) -> Evolution: ...


def evolve(earlier: Metamodel | Absent, later: Metamodel) -> Evolution:
    """Describe every difference between two accepted Metamodels.

    Provisioning is unilateral by TYPE: passing :data:`ABSENT` narrows the
    result, so a consumer that only accepts a Unilateral Evolution — the schema
    generator above all — needs no runtime check on that path.

    ``earlier`` is :data:`ABSENT` for fresh provisioning — an explicit sentinel,
    never inferred from an empty accepted model or from inspecting a physical
    schema. Provisioning is always unilateral: one entity-level addition per
    target Entity, which suppresses that Entity's members, and no Behavioral
    Impact or Overlap-Visible Operation, because no earlier scope survives.

    Equal endpoints return an empty :class:`UnilateralEvolution` retaining both
    models, so the result is total without a third no-evolution kind.
    """
    matching = match(earlier, later)
    operations = diff(matching)
    if matching.earlier is None:
        return UnilateralEvolution(
            earlier=None,
            later=later,
            operations=operations,
            behavioral_impacts=(),
            overlap_visible_operations=(),
        )
    return _assemble(matching.earlier, matching, operations)


def _assemble(
    earlier: Metamodel,
    matching: Matching,
    operations: tuple[EvolutionOperation, ...],
) -> Evolution:
    """Fold per-operation classification and the impacts into one result.

    Any nonempty reason set makes the whole evolution coordinated, carrying one
    requirement per coordinated operation in canonical operation order;
    otherwise the overlap-visible operations are collected in the same order.
    """
    classifications = classify(matching, operations)
    behavioral_impacts = impacts(earlier, matching, operations)
    requirements = tuple(
        CoordinationRequirement(operation=operation, reasons=classification.reasons)
        for operation, classification in zip(operations, classifications, strict=True)
        if classification.reasons
    )
    if requirements:
        return CoordinatedEvolution(
            earlier=earlier,
            later=matching.later,
            operations=operations,
            behavioral_impacts=behavioral_impacts,
            coordination_requirements=requirements,
        )
    return UnilateralEvolution(
        earlier=earlier,
        later=matching.later,
        operations=operations,
        behavioral_impacts=behavioral_impacts,
        overlap_visible_operations=tuple(
            operation
            for operation, classification in zip(operations, classifications, strict=True)
            if classification.overlap_visible
        ),
    )
