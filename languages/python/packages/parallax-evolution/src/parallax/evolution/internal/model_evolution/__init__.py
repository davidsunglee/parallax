from __future__ import annotations

from typing import Final, overload

from parallax.core.internal.base import UsageError
from parallax.core.internal.database_binding import ResolvedBinding, relocations_between
from parallax.evolution.internal.model_evolution._classify import classify
from parallax.evolution.internal.model_evolution._diff import diff
from parallax.evolution.internal.model_evolution._impacts import impacts
from parallax.evolution.internal.model_evolution._matching import Matching, match
from parallax.evolution.internal.model_evolution._values import (
    ABSENT,
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
    LogicalOperation,
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
    SequenceRelocated,
    StorageChanged,
    StorageContainerChanged,
    StorageLayoutChanged,
    TableRelocated,
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
    "ATTRIBUTE_DELTA_ORDER",
    "BEHAVIORAL_IMPACT_ORDER",
    "COORDINATION_REASON_ORDER",
    "ENTITY_DELTA_ORDER",
    "EVOLUTION_BACKEND_MISMATCH",
    "INDEX_DELTA_ORDER",
    "LOCKING_FALLBACK",
    "RELATIONSHIP_DELTA_ORDER",
    "VALUE_OBJECT_ATTRIBUTE_DELTA_ORDER",
    "VALUE_OBJECT_OCCURRENCE_DELTA_ORDER",
    "WRITES_DISABLED",
    "Absent",
    "AsOfAxisAdded",
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
    "LogicalOperation",
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
    "SequenceRelocated",
    "StorageChanged",
    "StorageContainerChanged",
    "StorageLayoutChanged",
    "TableRelocated",
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
    "evolve_resolved",
]


EVOLUTION_BACKEND_MISMATCH: Final = "evolution-backend-mismatch"
"""`evolve` was given endpoints bound for different backends."""


@overload
def evolve_resolved(earlier: Absent, later: ResolvedBinding) -> UnilateralEvolution: ...


@overload
def evolve_resolved(earlier: ResolvedBinding, later: ResolvedBinding) -> Evolution: ...


def evolve_resolved(earlier: ResolvedBinding | Absent, later: ResolvedBinding) -> Evolution:
    """Describe every difference between two models, each under its binding.

    The logical stage compares the two accepted Metamodels; the physical stage
    then reports every surviving table or sequence whose resolved physical
    object moved, after every logical operation, each coordinated by
    ``DatabaseMigrationRequired``. Endpoints bound for different backends are
    refused with ``evolution-backend-mismatch``: equal components on two
    engines are no evidence of one physical object.

    ``earlier`` is :data:`ABSENT` for fresh provisioning — an explicit sentinel,
    never inferred from an empty accepted model or from inspecting a physical
    schema. Provisioning is always unilateral: one entity-level addition per
    target Entity, which suppresses that Entity's members, and no Behavioral
    Impact or Overlap-Visible Operation, because no earlier scope survives.

    Equal endpoints return an empty :class:`UnilateralEvolution` retaining both,
    so the result is total without a third no-evolution kind.
    """
    if not isinstance(earlier, Absent) and earlier.dialect.name != later.dialect.name:
        raise UsageError(
            EVOLUTION_BACKEND_MISMATCH,
            f"the earlier model is bound for {earlier.dialect.name!r} and the later one for "
            f"{later.dialect.name!r}; evolution compares placements within one backend",
        )
    matching = match(earlier if isinstance(earlier, Absent) else earlier.meta, later.meta)
    operations = diff(matching)
    if isinstance(earlier, Absent):
        return UnilateralEvolution(
            earlier=None,
            later=later,
            operations=operations,
            behavioral_impacts=(),
            overlap_visible_operations=(),
        )
    return _assemble(earlier, later, matching, operations)


def _assemble(
    earlier: ResolvedBinding,
    later: ResolvedBinding,
    matching: Matching,
    logical: tuple[LogicalOperation, ...],
) -> Evolution:
    """Fold per-operation classification, the impacts, and every relocation
    into one result.

    Any nonempty reason set makes the whole evolution coordinated, carrying one
    requirement per coordinated operation in reported order; otherwise the
    overlap-visible operations are collected in the same order.
    """
    classifications = classify(matching, logical)
    behavioral_impacts = impacts(earlier.meta, matching, logical)
    relocations = relocations_between(earlier, later)
    operations: tuple[EvolutionOperation, ...] = (*logical, *relocations)
    requirements = (
        *(
            CoordinationRequirement(operation=operation, reasons=classification.reasons)
            for operation, classification in zip(logical, classifications, strict=True)
            if classification.reasons
        ),
        *(
            CoordinationRequirement(
                operation=relocation, reasons=(CoordinationReason.DATABASE_MIGRATION_REQUIRED,)
            )
            for relocation in relocations
        ),
    )
    if requirements:
        return CoordinatedEvolution(
            earlier=earlier,
            later=later,
            operations=operations,
            behavioral_impacts=behavioral_impacts,
            coordination_requirements=requirements,
        )
    return UnilateralEvolution(
        earlier=earlier,
        later=later,
        operations=operations,
        behavioral_impacts=behavioral_impacts,
        overlap_visible_operations=tuple(
            operation
            for operation, classification in zip(logical, classifications, strict=True)
            if classification.overlap_visible
        ),
    )
