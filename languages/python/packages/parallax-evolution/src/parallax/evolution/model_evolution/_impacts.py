"""Behavioral Impacts derived from the two endpoints.

Each impact compares effective facts read through the owning module's facet on
both endpoints — never re-derived here — on scopes present in the earlier
endpoint. A wholly new Entity's members are described by its own addition, so a
parent addition contributes no impact of its own.

An analyzer emits each impact beside the Model Location its scope occupies,
because the analyzer already knows which kind of position it reports on; one
sort over the closed variant order and that location is the whole ordering law.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from parallax.core.metamodel import (
    ApplicationAssigned,
    AttributeIdentity,
    AttributeLocation,
    AttributeMetadata,
    EntityIdentity,
    EntityLocation,
    Metamodel,
    ModelLocation,
    ModelLocationKey,
    PersistenceMode,
    PrimaryKey,
    TemporalDimension,
    canonical_location_key,
)
from parallax.core.opt_lock import (
    ExplicitVersion,
    OptimisticKey,
    OptimisticLockFacet,
    TransactionTimeDerived,
)
from parallax.core.opt_lock import view as opt_lock_view
from parallax.core.temporal_read import Bitemporal, TemporalFacet, TransactionTimeOnly
from parallax.core.temporal_read import view as temporal_view
from parallax.evolution.model_evolution._matching import EntityFacts, Matching
from parallax.evolution.model_evolution._values import (
    BEHAVIORAL_IMPACT_ORDER,
    LOCKING_FALLBACK,
    WRITES_DISABLED,
    AttributeAdded,
    AttributeAltered,
    AttributeRemoved,
    AttributeWriteCapability,
    BehavioralImpact,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    ConcurrencyControl,
    ConcurrencyControlChanged,
    EntityAltered,
    EntitySelectionFacts,
    EntityWriteCapability,
    EntityWriteShape,
    EvolutionOperation,
    InheritanceChanged,
    OptimisticLockingChanged,
    PersistenceChanged,
    QueryResultMembershipChanged,
    ScalarAdmissibility,
    TemporalAxisFacts,
    TransactionTimeGated,
    ValueAdmissibilityChanged,
    VersionGated,
    WriteCapabilityChanged,
    WritesEnabled,
)

__all__ = ["impacts"]

type _Located = tuple[BehavioralImpact, ModelLocation]


@dataclass(frozen=True, slots=True)
class _Endpoint:
    """The facets one endpoint answers an impact's questions with.

    The inheritance view of each Entity already travels on the Matching, so only
    the two family-level facets an Entity is read through are held here.
    """

    temporal: TemporalFacet
    locks: OptimisticLockFacet


@dataclass(frozen=True, slots=True)
class _Analysis:
    matching: Matching
    operations: tuple[EvolutionOperation, ...]
    earlier: _Endpoint
    later: _Endpoint


def impacts(
    earlier: Metamodel, matching: Matching, operations: Sequence[EvolutionOperation]
) -> tuple[BehavioralImpact, ...]:
    """Every Behavioral Impact the two endpoints differ by, in canonical order."""
    analysis = _Analysis(
        matching=matching,
        operations=tuple(operations),
        earlier=_Endpoint(temporal_view(earlier), opt_lock_view(earlier)),
        later=_Endpoint(temporal_view(matching.later), opt_lock_view(matching.later)),
    )
    located = [
        *_value_admissibility(analysis),
        *_concurrency_control(analysis),
        *_query_result_membership(analysis),
        *_write_capability(analysis),
    ]
    return tuple(impact for impact, _ in sorted(located, key=_order))


def _order(located: _Located) -> tuple[int, ModelLocationKey]:
    impact, location = located
    return (BEHAVIORAL_IMPACT_ORDER.index(type(impact)), canonical_location_key(location))


# --------------------------------------------------------------------------- #
# Value admissibility.                                                         #
# --------------------------------------------------------------------------- #
def _value_admissibility(analysis: _Analysis) -> Iterator[_Located]:
    """One impact per surviving scalar position whose accepted domain differs.

    Member addition and removal stay their own operations rather than becoming
    admissibility impacts, so only surviving positions are compared.
    """
    altered = _altered_attributes(analysis.operations)
    for identity, (earlier, later) in analysis.matching.attributes.surviving.items():
        before = _admissibility(earlier)
        after = _admissibility(later)
        if before == after:
            continue
        yield (
            ValueAdmissibilityChanged(
                scope=identity, earlier=before, later=after, caused_by=(altered[identity],)
            ),
            AttributeLocation(identity),
        )


def _admissibility(attribute: AttributeMetadata) -> ScalarAdmissibility:
    return ScalarAdmissibility(attribute.type, attribute.nullable, attribute.max_length)


def _altered_attributes(
    operations: Sequence[EvolutionOperation],
) -> dict[AttributeIdentity, AttributeAltered]:
    return {
        operation.attribute: operation
        for operation in operations
        if isinstance(operation, AttributeAltered)
    }


# --------------------------------------------------------------------------- #
# Concurrency control.                                                         #
# --------------------------------------------------------------------------- #
def _concurrency_control(analysis: _Analysis) -> Iterator[_Located]:
    """One impact per surviving Entity whose behavior under the ``optimistic``
    Concurrency Preference differs.

    The grain stays per Entity even though the Optimistic Lock Facet is
    family-uniform, because an inheritance change can move a surviving Entity
    between effective families.
    """
    for identity, (earlier, later) in analysis.matching.entities.surviving.items():
        before = _control(analysis.earlier.locks.key(identity))
        after = _control(analysis.later.locks.key(identity))
        if before == after:
            continue
        yield (
            ConcurrencyControlChanged(
                scope=identity,
                earlier=before,
                later=after,
                caused_by=_version_causes(analysis, identity, earlier, later),
            ),
            EntityLocation(identity),
        )


def _control(key: OptimisticKey | None) -> ConcurrencyControl:
    match key:
        case ExplicitVersion(attribute):
            return VersionGated(attribute)
        case TransactionTimeDerived(start_attribute):
            return TransactionTimeGated(start_attribute)
        case _:
            return LOCKING_FALLBACK


def _version_causes(
    analysis: _Analysis, entity: EntityIdentity, earlier: EntityFacts, later: EntityFacts
) -> tuple[EvolutionOperation, ...]:
    family = _family(earlier, later)
    return tuple(
        operation
        for operation in analysis.operations
        if _moves_the_optimistic_key(analysis.matching, operation, entity, family)
    )


def _moves_the_optimistic_key(
    matching: Matching,
    operation: EvolutionOperation,
    entity: EntityIdentity,
    family: frozenset[EntityIdentity],
) -> bool:
    match operation:
        case AttributeAdded():
            return (
                operation.attribute.entity in family
                and matching.attributes.added[operation.attribute].optimistic_locking
            )
        case AttributeRemoved():
            return (
                operation.attribute.entity in family
                and matching.attributes.removed[operation.attribute].optimistic_locking
            )
        case AttributeAltered():
            return operation.attribute.entity in family and _carries(
                operation.deltas, OptimisticLockingChanged
            )
        case EntityAltered():
            return operation.entity == entity and _carries(operation.deltas, InheritanceChanged)
        case _:
            return False


# --------------------------------------------------------------------------- #
# Query result membership.                                                     #
# --------------------------------------------------------------------------- #
def _query_result_membership(analysis: _Analysis) -> Iterator[_Located]:
    """One impact per surviving Entity whose predicate-free selection differs."""
    for identity, (earlier, later) in analysis.matching.entities.surviving.items():
        before = _selection(analysis.earlier, earlier)
        after = _selection(analysis.later, later)
        if before == after:
            continue
        yield (
            QueryResultMembershipChanged(
                scope=identity,
                earlier=before,
                later=after,
                caused_by=_membership_causes(analysis, earlier, later),
            ),
            EntityLocation(identity),
        )


def _selection(endpoint: _Endpoint, facts: EntityFacts) -> EntitySelectionFacts:
    return EntitySelectionFacts(
        concrete_entities=tuple(facts.family.concrete_subtypes),
        axes=_axes(endpoint, facts.declaration.identity),
    )


def _axes(endpoint: _Endpoint, entity: EntityIdentity) -> tuple[TemporalAxisFacts, ...]:
    """The effective Temporal Shape, as its axes in canonical dimension order."""
    return tuple(
        TemporalAxisFacts(axis.dimension, axis.start_attribute, axis.end_attribute)
        for dimension in TemporalDimension
        if (axis := endpoint.temporal.axis(entity, dimension)) is not None
    )


def _membership_causes(
    analysis: _Analysis, earlier: EntityFacts, later: EntityFacts
) -> tuple[EvolutionOperation, ...]:
    denoted = frozenset(earlier.family.concrete_subtypes) | frozenset(
        later.family.concrete_subtypes
    )
    return tuple(
        operation
        for operation in analysis.operations
        if _moves_the_denoted_rows(operation, denoted)
    )


def _moves_the_denoted_rows(
    operation: EvolutionOperation, denoted: frozenset[EntityIdentity]
) -> bool:
    match operation:
        case ConcreteSubtypeAdded() | ConcreteSubtypeRemoved():
            return operation.entity in denoted
        case EntityAltered():
            return operation.entity in denoted and _carries(operation.deltas, InheritanceChanged)
        case _:
            return False


# --------------------------------------------------------------------------- #
# Write capability.                                                            #
# --------------------------------------------------------------------------- #
def _write_capability(analysis: _Analysis) -> Iterator[_Located]:
    """The Entity write surfaces that changed, and the Attribute input
    capabilities no Entity-level change already dominates."""
    dominated: set[EntityIdentity] = set()
    for identity, (earlier, later) in analysis.matching.entities.surviving.items():
        before = _entity_writes(analysis.earlier, earlier)
        after = _entity_writes(analysis.later, later)
        if before == after:
            continue
        dominated.add(identity)
        yield (
            WriteCapabilityChanged(
                scope=identity,
                earlier=before,
                later=after,
                caused_by=_write_surface_causes(analysis, identity, earlier, later),
            ),
            EntityLocation(identity),
        )
    altered = _altered_attributes(analysis.operations)
    for identity, (earlier_member, later_member) in analysis.matching.attributes.surviving.items():
        before_input = _attribute_writes(earlier_member)
        after_input = _attribute_writes(later_member)
        if before_input == after_input or identity.entity in dominated:
            continue
        yield (
            WriteCapabilityChanged(
                scope=identity,
                earlier=before_input,
                later=after_input,
                caused_by=(altered[identity],),
            ),
            AttributeLocation(identity),
        )


def _entity_writes(endpoint: _Endpoint, facts: EntityFacts) -> EntityWriteCapability:
    if facts.family.persistence is PersistenceMode.READ_ONLY:
        return WRITES_DISABLED
    return WritesEnabled(_write_shape(endpoint, facts.declaration.identity))


def _write_shape(endpoint: _Endpoint, entity: EntityIdentity) -> EntityWriteShape:
    match endpoint.temporal.shape(entity):
        case Bitemporal():
            return EntityWriteShape.BITEMPORAL
        case TransactionTimeOnly():
            return EntityWriteShape.TRANSACTION_TIME_ONLY
        case _:
            return EntityWriteShape.NON_TEMPORAL


def _attribute_writes(attribute: AttributeMetadata) -> AttributeWriteCapability:
    """What caller input one Attribute admits.

    A generated primary key joins the derived framework-owned designations,
    because the framework rather than the caller supplies its value; an
    application-assigned key and a read-only Attribute admit insert input alone.
    """
    if attribute.framework_owned or _generated(attribute):
        return AttributeWriteCapability.FRAMEWORK_OWNED
    if attribute.read_only or isinstance(attribute.primary_key, PrimaryKey):
        return AttributeWriteCapability.CALLER_INSERT_ONLY
    return AttributeWriteCapability.CALLER_INSERT_AND_UPDATE


def _generated(attribute: AttributeMetadata) -> bool:
    return isinstance(attribute.primary_key, PrimaryKey) and not isinstance(
        attribute.primary_key.generation, ApplicationAssigned
    )


def _write_surface_causes(
    analysis: _Analysis, entity: EntityIdentity, earlier: EntityFacts, later: EntityFacts
) -> tuple[EvolutionOperation, ...]:
    family = _family(earlier, later)
    return tuple(
        operation
        for operation in analysis.operations
        if _moves_the_write_surface(operation, entity, family)
    )


def _moves_the_write_surface(
    operation: EvolutionOperation, entity: EntityIdentity, family: frozenset[EntityIdentity]
) -> bool:
    match operation:
        case EntityAltered():
            return (
                operation.entity in family and _carries(operation.deltas, PersistenceChanged)
            ) or (operation.entity == entity and _carries(operation.deltas, InheritanceChanged))
        case _:
            return False


# --------------------------------------------------------------------------- #
# Shared reads over an operation and a family.                                 #
# --------------------------------------------------------------------------- #
def _family(earlier: EntityFacts, later: EntityFacts) -> frozenset[EntityIdentity]:
    """Every position whose declarations reach this Entity on either endpoint."""
    return frozenset(earlier.family.ancestry) | frozenset(later.family.ancestry)


def _carries(deltas: Sequence[object], delta: type) -> bool:
    return any(isinstance(member, delta) for member in deltas)
