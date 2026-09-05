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

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from parallax.core.metamodel import (
    ApplicationAssigned,
    AttributeIdentity,
    AttributeLocation,
    AttributeMetadata,
    EntityIdentity,
    EntityLocation,
    IndexIdentity,
    IndexMetadata,
    Metamodel,
    ModelLocation,
    ModelLocationKey,
    PersistenceMode,
    PrimaryKey,
    RelationshipIdentity,
    RelationshipLocation,
    RelationshipOrder,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeLocation,
    ValueObjectAttributeMetadata,
    ValueObjectIdentity,
    ValueObjectLocation,
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
from parallax.evolution.model_evolution._matching import (
    EntityFacts,
    Matching,
    Occurrence,
    RelationshipFacts,
)
from parallax.evolution.model_evolution._values import (
    BEHAVIORAL_IMPACT_ORDER,
    LOCKING_FALLBACK,
    WRITES_DISABLED,
    AsOfAxisAdded,
    AsOfAxisAltered,
    AsOfAxisRemoved,
    AttributeAdded,
    AttributeAltered,
    AttributeRemoved,
    AttributeWriteCapability,
    BehavioralImpact,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    ConcurrencyControl,
    ConcurrencyControlChanged,
    DeclarationFormChanged,
    DeletePropagation,
    DeletePropagationChanged,
    DependencyChanged,
    EntityAltered,
    EntitySelectionFacts,
    EntityWriteCapability,
    EntityWriteShape,
    EvolutionOperation,
    IndexAdded,
    IndexAltered,
    IndexRemoved,
    InheritanceChanged,
    JoinChanged,
    OccurrenceAdmissibility,
    OptimisticLockingChanged,
    OrderingChanged,
    PersistenceChanged,
    QueryResultMembershipChanged,
    QueryResultOrderingChanged,
    RelationshipAltered,
    RelationshipSelectionFacts,
    ReverseOfChanged,
    ScalarAdmissibility,
    TemporalAxisFacts,
    TransactionTimeGated,
    UniquenessEnforcementChanged,
    UniqueTuple,
    ValueAdmissibilityChanged,
    ValueObjectAttributeAltered,
    ValueObjectOccurrenceAltered,
    VersionGated,
    WriteCapabilityChanged,
    WritesEnabled,
)

__all__ = ["impacts"]

type _Located = tuple[BehavioralImpact, ModelLocation]


@dataclass(frozen=True, slots=True)
class _Endpoint:
    """The facets one endpoint answers an impact's questions with.

    The inheritance view of each Entity and the navigable direction of each
    Relationship already travel on the Matching, so only the two family-level
    facets an Entity is read through are held here.
    """

    temporal: TemporalFacet
    locks: OptimisticLockFacet


@dataclass(frozen=True, slots=True)
class _Analysis:
    matching: Matching
    operations: tuple[EvolutionOperation, ...]
    earlier: _Endpoint
    later: _Endpoint
    altered_attributes: Mapping[AttributeIdentity, AttributeAltered]
    altered_occurrences: Mapping[ValueObjectIdentity, ValueObjectOccurrenceAltered]
    altered_members: Mapping[ValueObjectAttributeIdentity, ValueObjectAttributeAltered]


def impacts(
    earlier: Metamodel, matching: Matching, operations: Sequence[EvolutionOperation]
) -> tuple[BehavioralImpact, ...]:
    """Every Behavioral Impact the two endpoints differ by, in canonical order."""
    described = tuple(operations)
    analysis = _Analysis(
        matching=matching,
        operations=described,
        earlier=_Endpoint(temporal_view(earlier), opt_lock_view(earlier)),
        later=_Endpoint(temporal_view(matching.later), opt_lock_view(matching.later)),
        altered_attributes={
            operation.attribute: operation
            for operation in described
            if isinstance(operation, AttributeAltered)
        },
        altered_occurrences={
            operation.value_object: operation
            for operation in described
            if isinstance(operation, ValueObjectOccurrenceAltered)
        },
        altered_members={
            operation.value_object_attribute: operation
            for operation in described
            if isinstance(operation, ValueObjectAttributeAltered)
        },
    )
    located = [
        *_uniqueness_enforcement(analysis),
        *_value_admissibility(analysis),
        *_delete_propagation(analysis),
        *_concurrency_control(analysis),
        *_query_result_membership(analysis),
        *_query_result_ordering(analysis),
        *_write_capability(analysis),
    ]
    return tuple(impact for impact, _ in sorted(located, key=_order))


def _order(located: _Located) -> tuple[int, ModelLocationKey]:
    impact, location = located
    return (BEHAVIORAL_IMPACT_ORDER.index(type(impact)), canonical_location_key(location))


# --------------------------------------------------------------------------- #
# Uniqueness enforcement.                                                      #
# --------------------------------------------------------------------------- #
def _uniqueness_enforcement(analysis: _Analysis) -> Iterator[_Located]:
    """One impact per surviving Entity whose secondary uniqueness rules differ.

    A rule is an unordered Attribute set, so authored Indices differing only in
    component order or name collapse into one, and reordering an Index's
    components changes no rule at all. Derived primary-key uniqueness is not
    among them: the derived Index is not authored and never reaches the pairing.
    """
    for identity in analysis.matching.entities.surviving:
        before = _unique_rules(_indices_of(analysis, identity, later=False))
        after = _unique_rules(_indices_of(analysis, identity, later=True))
        if before == after:
            continue
        yield (
            UniquenessEnforcementChanged(
                scope=identity,
                earlier=before,
                later=after,
                caused_by=_enforcement_causes(analysis, identity),
            ),
            EntityLocation(identity),
        )


def _indices_of(analysis: _Analysis, entity: EntityIdentity, *, later: bool) -> list[IndexMetadata]:
    """One endpoint's authored Indices of ``entity``."""
    paired = analysis.matching.indices
    endpoint = paired.added if later else paired.removed
    present = [index for identity, index in endpoint.items() if identity.entity == entity]
    present.extend(
        surviving[1 if later else 0]
        for identity, surviving in paired.surviving.items()
        if identity.entity == entity
    )
    return present


def _unique_rules(indices: Iterable[IndexMetadata]) -> tuple[UniqueTuple, ...]:
    rules = {rule for index in indices if (rule := _rule(index)) is not None}
    return tuple(sorted(rules, key=_rule_key))


def _rule(index: IndexMetadata) -> UniqueTuple | None:
    """The uniqueness rule ``index`` enforces, as an unordered Attribute set."""
    if not index.unique:
        return None
    return UniqueTuple(tuple(sorted(set(index.attributes), key=_attribute_key)))


def _rule_key(rule: UniqueTuple) -> tuple[tuple[tuple[str, str], str], ...]:
    return tuple(_attribute_key(component) for component in rule.attributes)


def _attribute_key(attribute: AttributeIdentity) -> tuple[tuple[str, str], str]:
    return (attribute.entity.sort_key, attribute.name)


def _enforcement_causes(
    analysis: _Analysis, entity: EntityIdentity
) -> tuple[EvolutionOperation, ...]:
    """The Index operations on ``entity`` whose own rule contribution moved."""
    return tuple(
        operation
        for operation in analysis.operations
        if isinstance(operation, IndexAdded | IndexRemoved | IndexAltered)
        and operation.index.entity == entity
        and _moves_a_rule(analysis, operation.index)
    )


def _moves_a_rule(analysis: _Analysis, index: IndexIdentity) -> bool:
    paired = analysis.matching.indices
    surviving = paired.surviving.get(index)
    if surviving is not None:
        return _rule(surviving[0]) != _rule(surviving[1])
    added = paired.added.get(index)
    if added is not None:
        return _rule(added) is not None
    removed = paired.removed.get(index)
    return removed is not None and _rule(removed) is not None


# --------------------------------------------------------------------------- #
# Value admissibility.                                                         #
# --------------------------------------------------------------------------- #
def _value_admissibility(analysis: _Analysis) -> Iterator[_Located]:
    """One impact per surviving value-bearing path whose accepted domain differs.

    Member addition and removal stay their own operations rather than becoming
    admissibility impacts, so only surviving positions are compared, and an
    occurrence admits only the presence of a value: its multiplicity is
    structural rather than a value domain.
    """
    for identity, (earlier, later) in analysis.matching.attributes.surviving.items():
        before, after = _scalar(earlier), _scalar(later)
        if before == after:
            continue
        yield (
            ValueAdmissibilityChanged(
                scope=identity,
                earlier=before,
                later=after,
                caused_by=(analysis.altered_attributes[identity],),
            ),
            AttributeLocation(identity),
        )
    for occurrence, (
        before_occurrence,
        after_occurrence,
    ) in analysis.matching.value_objects.surviving.items():
        before_admits = _occurrence(before_occurrence)
        after_admits = _occurrence(after_occurrence)
        if before_admits == after_admits:
            continue
        yield (
            ValueAdmissibilityChanged(
                scope=occurrence,
                earlier=before_admits,
                later=after_admits,
                caused_by=(analysis.altered_occurrences[occurrence],),
            ),
            ValueObjectLocation(occurrence),
        )
    for member, (
        before_member,
        after_member,
    ) in analysis.matching.value_object_attributes.surviving.items():
        before_leaf, after_leaf = _leaf(before_member), _leaf(after_member)
        if before_leaf == after_leaf:
            continue
        yield (
            ValueAdmissibilityChanged(
                scope=member,
                earlier=before_leaf,
                later=after_leaf,
                caused_by=(analysis.altered_members[member],),
            ),
            ValueObjectAttributeLocation(member),
        )


def _scalar(attribute: AttributeMetadata) -> ScalarAdmissibility:
    return ScalarAdmissibility(attribute.type, attribute.nullable, attribute.max_length)


def _leaf(member: ValueObjectAttributeMetadata) -> ScalarAdmissibility:
    """A Value Object scalar leaf bounds no String: it owns no length fact."""
    return ScalarAdmissibility(member.type, member.nullable, None)


def _occurrence(occurrence: Occurrence) -> OccurrenceAdmissibility:
    return OccurrenceAdmissibility(occurrence.nullable)


# --------------------------------------------------------------------------- #
# Delete propagation.                                                          #
# --------------------------------------------------------------------------- #
def _delete_propagation(analysis: _Analysis) -> Iterator[_Located]:
    """One impact per surviving Relationship whose dependency policy differs."""
    for identity, (earlier, later) in analysis.matching.relationships.surviving.items():
        before, after = _propagation(earlier), _propagation(later)
        if before == after:
            continue
        yield (
            DeletePropagationChanged(
                scope=identity,
                earlier=before,
                later=after,
                caused_by=_relationship_causes(
                    analysis,
                    identity,
                    (earlier, later),
                    (DependencyChanged, ReverseOfChanged, DeclarationFormChanged),
                    through_peer=True,
                ),
            ),
            RelationshipLocation(identity),
        )


def _propagation(facts: RelationshipFacts) -> DeletePropagation:
    if facts.direction.dependent:
        return DeletePropagation.PROPAGATES
    return DeletePropagation.DOES_NOT_PROPAGATE


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
        case AsOfAxisAdded() | AsOfAxisRemoved() | AsOfAxisAltered():
            # A Transaction-Time family derives its version from the milestone
            # start; a Valid-Time axis alone moves no gate.
            return (
                operation.entity in family
                and operation.dimension is TemporalDimension.TRANSACTION_TIME
            )
        case EntityAltered():
            return operation.entity == entity and _carries(operation.deltas, InheritanceChanged)
        case _:
            return False


# --------------------------------------------------------------------------- #
# Query result membership.                                                     #
# --------------------------------------------------------------------------- #
def _query_result_membership(analysis: _Analysis) -> Iterator[_Located]:
    """One impact per surviving Entity or Relationship position whose
    predicate-free selection differs."""
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
    for relationship, (
        before_facts,
        after_facts,
    ) in analysis.matching.relationships.surviving.items():
        before_reached = _reached(before_facts)
        after_reached = _reached(after_facts)
        if before_reached == after_reached:
            continue
        yield (
            QueryResultMembershipChanged(
                scope=relationship,
                earlier=before_reached,
                later=after_reached,
                caused_by=_relationship_causes(
                    analysis,
                    relationship,
                    (before_facts, after_facts),
                    (JoinChanged, ReverseOfChanged, DeclarationFormChanged),
                    through_peer=True,
                ),
            ),
            RelationshipLocation(relationship),
        )


def _selection(endpoint: _Endpoint, facts: EntityFacts) -> EntitySelectionFacts:
    return EntitySelectionFacts(
        concrete_entities=tuple(facts.family.concrete_subtypes),
        axes=_axes(endpoint, facts.declaration.identity),
    )


def _reached(facts: RelationshipFacts) -> RelationshipSelectionFacts:
    """The rows one navigation denotes: its target Entity and effective join."""
    return RelationshipSelectionFacts(
        target=facts.direction.join.target.entity, join=facts.direction.join
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
    family = _family(earlier, later)
    return tuple(
        operation
        for operation in analysis.operations
        if _moves_the_denoted_rows(operation, denoted, family)
    )


def _moves_the_denoted_rows(
    operation: EvolutionOperation,
    denoted: frozenset[EntityIdentity],
    family: frozenset[EntityIdentity],
) -> bool:
    match operation:
        case ConcreteSubtypeAdded() | ConcreteSubtypeRemoved():
            return operation.entity in denoted
        case AsOfAxisAdded() | AsOfAxisRemoved() | AsOfAxisAltered():
            # An axis is the family root's, and it decides the temporal shape
            # every position of that family selects through.
            return operation.entity in family
        case EntityAltered():
            return operation.entity in denoted and _carries(operation.deltas, InheritanceChanged)
        case _:
            return False


# --------------------------------------------------------------------------- #
# Query result ordering.                                                       #
# --------------------------------------------------------------------------- #
def _query_result_ordering(analysis: _Analysis) -> Iterator[_Located]:
    """One impact per surviving Relationship whose ordering rule differs.

    A direction's ordering is its own declaration's, never its peer's, so a
    reverse declaration orders the Entities it reaches rather than the ones the
    defining declaration reaches.
    """
    for identity, (earlier, later) in analysis.matching.relationships.surviving.items():
        before, after = _ordering(earlier), _ordering(later)
        if before == after:
            continue
        yield (
            QueryResultOrderingChanged(
                scope=identity,
                earlier=before,
                later=after,
                caused_by=_relationship_causes(
                    analysis,
                    identity,
                    (earlier, later),
                    (OrderingChanged, DeclarationFormChanged),
                    through_peer=False,
                ),
            ),
            RelationshipLocation(identity),
        )


def _ordering(facts: RelationshipFacts) -> tuple[RelationshipOrder, ...]:
    return tuple(facts.direction.order_by)


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
                caused_by=_attribute_input_causes(analysis, identity),
            ),
            AttributeLocation(identity),
        )


def _attribute_input_causes(
    analysis: _Analysis, attribute: AttributeIdentity
) -> tuple[EvolutionOperation, ...]:
    """The operations that moved what one Attribute admits from a caller.

    Its own alteration, and any As-Of Axis operation naming it as an endpoint:
    framework ownership is derived from axis membership rather than declared, so
    an axis arriving at or leaving an Attribute moves what a caller may supply
    without that Attribute's own declaration changing at all.
    """
    return tuple(
        operation
        for operation in analysis.operations
        if _moves_attribute_input(analysis, operation, attribute)
    )


def _moves_attribute_input(
    analysis: _Analysis, operation: EvolutionOperation, attribute: AttributeIdentity
) -> bool:
    match operation:
        case AttributeAltered():
            return operation.attribute == attribute
        case AsOfAxisAdded() | AsOfAxisRemoved() | AsOfAxisAltered():
            return attribute in _axis_endpoints(analysis, operation)
        case _:
            return False


def _axis_endpoints(
    analysis: _Analysis, operation: AsOfAxisAdded | AsOfAxisRemoved | AsOfAxisAltered
) -> frozenset[AttributeIdentity]:
    """Every Attribute the named axis position uses as an endpoint, on either
    endpoint of the evolution."""
    key = (operation.entity, operation.dimension)
    paired = analysis.matching.as_of_axes
    surviving = paired.surviving.get(key)
    present = (
        surviving
        if surviving is not None
        else tuple(
            axis for axis in (paired.added.get(key), paired.removed.get(key)) if axis is not None
        )
    )
    return frozenset(
        endpoint for axis in present for endpoint in (axis.start_attribute, axis.end_attribute)
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
        case AsOfAxisAdded() | AsOfAxisRemoved() | AsOfAxisAltered():
            return operation.entity in family
        case EntityAltered():
            return (
                operation.entity in family and _carries(operation.deltas, PersistenceChanged)
            ) or (operation.entity == entity and _carries(operation.deltas, InheritanceChanged))
        case _:
            return False


# --------------------------------------------------------------------------- #
# Shared reads over an operation, a family, and a Relationship pair.           #
# --------------------------------------------------------------------------- #
def _family(earlier: EntityFacts, later: EntityFacts) -> frozenset[EntityIdentity]:
    """Every position whose declarations reach this Entity on either endpoint."""
    return frozenset(earlier.family.ancestry) | frozenset(later.family.ancestry)


def _relationship_causes(
    analysis: _Analysis,
    identity: RelationshipIdentity,
    surviving: tuple[RelationshipFacts, RelationshipFacts],
    deltas: tuple[type, ...],
    *,
    through_peer: bool,
) -> tuple[EvolutionOperation, ...]:
    """The Relationship alterations that moved the fact under analysis.

    ``through_peer`` extends the search to the peer declaration, for the facts a
    reverse direction derives from its defining declaration rather than owning.
    """
    named = {identity}
    if through_peer:
        named |= {peer for facts in surviving if (peer := _peer(facts)) is not None}
    return tuple(
        operation
        for operation in analysis.operations
        if isinstance(operation, RelationshipAltered)
        and operation.relationship in named
        and _carries(operation.deltas, deltas)
    )


def _peer(facts: RelationshipFacts) -> RelationshipIdentity | None:
    """The declaration on the far Entity naming this association's other side."""
    if facts.direction.reverse is None:
        return None
    return RelationshipIdentity(facts.direction.join.target.entity, facts.direction.reverse)


def _carries(deltas: Sequence[object], delta: type | tuple[type, ...]) -> bool:
    return any(isinstance(member, delta) for member in deltas)
