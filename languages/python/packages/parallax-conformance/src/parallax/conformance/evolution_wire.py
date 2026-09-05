"""The corpus spelling of an Evolution and its Schema Delta, as `then` JSON.

`parallax.evolution` exports typed values and no serialization, because model
altitude is the point — a host renders an Evolution in its own words. The JSON
spelling belongs to `m-case-format`, and its only consumer is the conformance
adapter, so the encoder sits here beside the case-format parser rather than in
the wheel.

Every accepted value is spelled the way the model descriptor spells it, so an
`earlier` or `later` fact reads as the model it was authored in rather than as a
second vocabulary a case author has to learn.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Final, cast

from parallax.core.base import (
    Boolean,
    Bytes,
    Date,
    Decimal,
    Float32,
    Float64,
    Int32,
    Int64,
    Json,
    String,
    Time,
    Timestamp,
    Uuid,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    ApplicationAssigned,
    AttributeIdentity,
    Cardinality,
    Column,
    Columns,
    ConcreteSubtype,
    DefiningRelationshipDeclaration,
    Document,
    EntityIdentity,
    IndexIdentity,
    Inheritance,
    InheritanceStrategy,
    Max,
    Multiplicity,
    NotPrimaryKey,
    NullPlacement,
    PersistenceMode,
    PkGeneration,
    PrimaryKey,
    RelationshipIdentity,
    RelationshipJoin,
    RelationshipOrder,
    ReverseRelationshipDeclaration,
    SortDirection,
    Table,
    TablePerHierarchy,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.descriptor._type_spelling import format_type_spelling
from parallax.evolution.model_evolution import (
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
    CoordinatedEvolution,
    CoordinationReason,
    CoordinationRequirement,
    DeclarationCollection,
    DeclarationOrderChanged,
    DeletePropagation,
    EntityAdded,
    EntityAltered,
    EntityRemoved,
    EntitySelectionFacts,
    EntityWriteShape,
    Evolution,
    EvolutionOperation,
    IndexAdded,
    IndexAltered,
    IndexRemoved,
    LockingFallback,
    OccurrenceAdmissibility,
    RelationshipAdded,
    RelationshipAltered,
    RelationshipRemoved,
    RelationshipSelectionFacts,
    ScalarAdmissibility,
    TemporalAxisFacts,
    TransactionTimeGated,
    UnilateralEvolution,
    UniqueTuple,
    ValueObjectAttributeAdded,
    ValueObjectAttributeAltered,
    ValueObjectAttributeRemoved,
    ValueObjectOccurrenceAdded,
    ValueObjectOccurrenceAltered,
    ValueObjectOccurrenceRemoved,
    VersionGated,
    WritesDisabled,
    WritesEnabled,
)
from parallax.evolution.schema_delta import (
    PhysicalLocation,
    SchemaDelta,
    UnsupportedSchemaEvolutionError,
)

__all__ = ["evolution_observation", "schema_cell", "unsupported_cell"]

_DIMENSIONS: Final[dict[TemporalDimension, str]] = {
    TemporalDimension.VALID_TIME: "valid-time",
    TemporalDimension.TRANSACTION_TIME: "transaction-time",
}

_CARDINALITIES: Final[dict[Cardinality, str]] = {
    Cardinality.ONE_TO_ONE: "one-to-one",
    Cardinality.MANY_TO_ONE: "many-to-one",
    Cardinality.ONE_TO_MANY: "one-to-many",
}

_MULTIPLICITIES: Final[dict[Multiplicity, str]] = {
    Multiplicity.ONE: "one",
    Multiplicity.MANY: "many",
}

# The Neutral Type algebra's arms, so a type reaches `m-descriptor`'s own
# spelling rather than a second one written here.
_NEUTRAL_TYPES: Final[tuple[type, ...]] = (
    Boolean,
    Int32,
    Int64,
    Float32,
    Float64,
    Decimal,
    String,
    Bytes,
    Date,
    Time,
    Timestamp,
    Uuid,
    Json,
)

_PERSISTENCE: Final[dict[PersistenceMode, str]] = {
    PersistenceMode.READ_WRITE: "read-write",
    PersistenceMode.READ_ONLY: "read-only",
}

_DIRECTIONS: Final[dict[SortDirection, str]] = {
    SortDirection.ASCENDING: "asc",
    SortDirection.DESCENDING: "desc",
}

_NULL_PLACEMENTS: Final[dict[NullPlacement, str]] = {
    NullPlacement.NULLS_FIRST: "first",
    NullPlacement.NULLS_LAST: "last",
}

_WRITE_SHAPES: Final[dict[EntityWriteShape, str]] = {
    EntityWriteShape.NON_TEMPORAL: "NonTemporal",
    EntityWriteShape.TRANSACTION_TIME_ONLY: "TransactionTimeOnly",
    EntityWriteShape.BITEMPORAL: "Bitemporal",
}

# Every closed vocabulary an endpoint fact can be, with the spelling the corpus
# gives it. Each is an `enum.Enum` over ints, so the lookup is by membership
# rather than by value.
_VOCABULARIES: Final[tuple[tuple[type[Enum], dict[Any, str]], ...]] = (
    (TemporalDimension, dict(_DIMENSIONS)),
    (Cardinality, dict(_CARDINALITIES)),
    (Multiplicity, dict(_MULTIPLICITIES)),
    (PersistenceMode, dict(_PERSISTENCE)),
    (SortDirection, dict(_DIRECTIONS)),
    (NullPlacement, dict(_NULL_PLACEMENTS)),
    (DeletePropagation, {member: member.value for member in DeletePropagation}),
    (EntityWriteShape, {member: member.value for member in EntityWriteShape}),
    (CoordinationReason, {member: member.value for member in CoordinationReason}),
    (DeclarationCollection, {member: member.value for member in DeclarationCollection}),
    (
        AttributeWriteCapability,
        {member: member.value for member in AttributeWriteCapability},
    ),
)


class EvolutionSpellingError(ValueError):
    """A value the corpus spelling of an Evolution does not define."""


def evolution_observation(evolution: Evolution) -> dict[str, Any]:
    """``evolution`` as the complete ``then.evolution`` value a case asserts."""
    observation: dict[str, Any] = {
        "kind": "unilateral" if isinstance(evolution, UnilateralEvolution) else "coordinated",
        "operations": [_operation(operation) for operation in evolution.operations],
        "behavioralImpacts": [_impact(impact) for impact in evolution.behavioral_impacts],
        "overlapVisibleOperations": [],
        "coordinationRequirements": [],
    }
    if isinstance(evolution, UnilateralEvolution):
        observation["overlapVisibleOperations"] = [
            _operation(operation) for operation in evolution.overlap_visible_operations
        ]
    if isinstance(evolution, CoordinatedEvolution):
        observation["coordinationRequirements"] = [
            _requirement(requirement) for requirement in evolution.coordination_requirements
        ]
    return observation


def schema_cell(delta: SchemaDelta) -> dict[str, Any]:
    """``delta`` as the ``then.schema`` cell for the dialect that produced it."""
    return {
        "delta": {
            "statements": list(delta.statements),
            "createdIndices": [
                {
                    "physicalIndexName": created.physical_index_name.value,
                    "physicalTable": created.physical_table.name,
                    "logicalIndexIdentity": _index(created.logical_index_identity),
                    "unique": created.unique,
                }
                for created in delta.created_indices
            ],
        }
    }


def unsupported_cell(error: UnsupportedSchemaEvolutionError) -> dict[str, Any]:
    """A refusing Dialect's ``then.schema`` cell: every operation it cannot render.

    The dialect-neutral reason each refusal carries is deliberately not spelled:
    a cell asserts WHICH operations a dialect cannot render, and pinning a
    renderer's prose would make a reworded message a corpus failure.
    """
    return {
        "unsupported": {
            "operations": [
                {
                    "kind": operation.kind,
                    "physicalLocation": _physical_location(operation.location),
                    "causedBy": [_operation(cause) for cause in operation.caused_by],
                }
                for operation in error.operations
            ]
        }
    }


def _physical_location(location: PhysicalLocation) -> dict[str, str]:
    spelled = {"table": location.table.name}
    if location.column is not None:
        spelled["column"] = location.column.name
    if location.index is not None:
        spelled["index"] = location.index.value
    return spelled


# --------------------------------------------------------------------------- #
# Identities.                                                                  #
# --------------------------------------------------------------------------- #
def _entity(identity: EntityIdentity) -> str:
    return identity.canonical


def _attribute(identity: AttributeIdentity) -> str:
    return f"{identity.entity.canonical}.{identity.name}"


def _relationship(identity: RelationshipIdentity) -> str:
    return f"{identity.source_entity.canonical}.{identity.name}"


def _index(identity: IndexIdentity) -> str:
    return f"{identity.entity.canonical}.{identity.name}"


def _value_object(identity: ValueObjectIdentity) -> str:
    return ".".join((identity.entity.canonical, *identity.path))


def _value_object_attribute(identity: ValueObjectAttributeIdentity) -> str:
    return f"{_value_object(identity.value_object)}.{identity.name}"


def _declaration(identity: object) -> str:
    match identity:
        case AttributeIdentity():
            return _attribute(identity)
        case RelationshipIdentity():
            return _relationship(identity)
        case IndexIdentity():
            return _index(identity)
        case ValueObjectAttributeIdentity():
            return _value_object_attribute(identity)
        case ValueObjectIdentity():
            return _value_object(identity)
        case _:
            raise EvolutionSpellingError(f"no declaration spelling for {identity!r}")


def _scope(identity: object) -> dict[str, str]:
    """A Behavioral Impact scope, named by the kind of identity it is."""
    match identity:
        case EntityIdentity():
            return {"entity": _entity(identity)}
        case AttributeIdentity():
            return {"attribute": _attribute(identity)}
        case RelationshipIdentity():
            return {"relationship": _relationship(identity)}
        case ValueObjectAttributeIdentity():
            return {"valueObjectAttribute": _value_object_attribute(identity)}
        case ValueObjectIdentity():
            return {"valueObject": _value_object(identity)}
        case _:
            raise EvolutionSpellingError(f"no scope spelling for {identity!r}")


# --------------------------------------------------------------------------- #
# Operations and their field deltas.                                           #
# --------------------------------------------------------------------------- #
def _operation(operation: EvolutionOperation) -> dict[str, Any]:
    match operation:
        case EntityAdded() | EntityRemoved() | ConcreteSubtypeAdded() | ConcreteSubtypeRemoved():
            return {"kind": type(operation).__name__, "entity": _entity(operation.entity)}
        case EntityAltered():
            return _altered(operation, "entity", _entity(operation.entity))
        case AttributeAdded() | AttributeRemoved():
            return {
                "kind": type(operation).__name__,
                "attribute": _attribute(operation.attribute),
            }
        case AttributeAltered():
            return _altered(operation, "attribute", _attribute(operation.attribute))
        case ValueObjectOccurrenceAdded() | ValueObjectOccurrenceRemoved():
            return {
                "kind": type(operation).__name__,
                "valueObject": _value_object(operation.value_object),
            }
        case ValueObjectOccurrenceAltered():
            return _altered(operation, "valueObject", _value_object(operation.value_object))
        case ValueObjectAttributeAdded() | ValueObjectAttributeRemoved():
            return {
                "kind": type(operation).__name__,
                "valueObjectAttribute": _value_object_attribute(operation.value_object_attribute),
            }
        case ValueObjectAttributeAltered():
            return _altered(
                operation,
                "valueObjectAttribute",
                _value_object_attribute(operation.value_object_attribute),
            )
        case RelationshipAdded() | RelationshipRemoved():
            return {
                "kind": type(operation).__name__,
                "relationship": _relationship(operation.relationship),
            }
        case RelationshipAltered():
            return _altered(operation, "relationship", _relationship(operation.relationship))
        case AsOfAxisAdded() | AsOfAxisRemoved():
            return {
                "kind": type(operation).__name__,
                "entity": _entity(operation.entity),
                "dimension": _DIMENSIONS[operation.dimension],
            }
        case AsOfAxisAltered():
            return {
                "kind": type(operation).__name__,
                "entity": _entity(operation.entity),
                "dimension": _DIMENSIONS[operation.dimension],
                "deltas": [_delta(delta) for delta in operation.deltas],
            }
        case IndexAdded() | IndexRemoved():
            return {"kind": type(operation).__name__, "index": _index(operation.index)}
        case IndexAltered():
            return _altered(operation, "index", _index(operation.index))
        case DeclarationOrderChanged():
            return {
                "kind": type(operation).__name__,
                "collection": operation.collection.value,
                "owner": _declaration(operation.owner)
                if isinstance(operation.owner, ValueObjectIdentity)
                else _entity(operation.owner),
                "earlier": [_declaration(item) for item in operation.earlier],
                "later": [_declaration(item) for item in operation.later],
            }


def _altered(operation: Any, member: str, spelling: str) -> dict[str, Any]:
    return {
        "kind": type(operation).__name__,
        member: spelling,
        "deltas": [_delta(delta) for delta in operation.deltas],
    }


def _delta(delta: Any) -> dict[str, Any]:
    return {
        "kind": type(delta).__name__,
        "earlier": _fact(delta.earlier),
        "later": _fact(delta.later),
    }


# --------------------------------------------------------------------------- #
# Behavioral Impacts.                                                          #
# --------------------------------------------------------------------------- #
def _impact(impact: BehavioralImpact) -> dict[str, Any]:
    return {
        "kind": type(impact).__name__,
        "scope": _scope(impact.scope),
        "earlier": _fact(impact.earlier),
        "later": _fact(impact.later),
        "causedBy": [_operation(cause) for cause in impact.caused_by],
    }


def _requirement(requirement: CoordinationRequirement) -> dict[str, Any]:
    return {
        "operation": _operation(requirement.operation),
        "reasons": [reason.value for reason in requirement.reasons],
    }


# --------------------------------------------------------------------------- #
# Accepted values, spelled as the model descriptor spells them.                #
# --------------------------------------------------------------------------- #
def _fact(value: object) -> Any:
    """One accepted endpoint value, spelled as the model descriptor spells it.

    A fact outside these shapes is refused rather than guessed: an authored
    expectation compares against this spelling exactly, so inventing one would
    make a case pass against a value no descriptor could have declared.
    """
    match value:
        case None | bool() | str():
            return value
        case tuple():
            return [_fact(item) for item in cast("tuple[object, ...]", value)]
        case Table() | Column():
            return value.name
        case EntityIdentity():
            return _entity(value)
        case AttributeIdentity():
            return _attribute(value)
        case RelationshipIdentity():
            return _relationship(value)
        case Columns():
            return "columns"
        case Document():
            return {"document": {"column": value.column.name}}
        case NotPrimaryKey():
            return False
        case PrimaryKey():
            return {"generation": _generation(value.generation)}
        case AbstractRoot():
            return {"role": "root", **_strategy(value.strategy)}
        case AbstractSubtype() | ConcreteSubtype():
            return _descendant(cast("Inheritance[EntityIdentity]", value))
        case RelationshipJoin():
            return {"source": _attribute(value.source), "target": _attribute(value.target)}
        case RelationshipOrder():
            return {
                "attribute": _attribute(value.attribute),
                "direction": _DIRECTIONS[value.direction],
                "nulls": _NULL_PLACEMENTS[value.nulls],
            }
        case DefiningRelationshipDeclaration():
            return {
                "name": value.identity.name,
                "cardinality": _CARDINALITIES[value.cardinality],
                "join": _fact(value.join),
                "dependent": value.dependent,
                "orderBy": _fact(value.order_by),
            }
        case ReverseRelationshipDeclaration():
            return {
                "name": value.identity.name,
                "reverseOf": _relationship(value.reverse_of),
                "orderBy": _fact(value.order_by),
            }
        case UniqueTuple():
            return [_attribute(component) for component in value.attributes]
        case ScalarAdmissibility():
            return {
                "type": format_type_spelling(value.type),
                "nullable": value.nullable,
                "maxLength": value.max_length,
            }
        case OccurrenceAdmissibility():
            return {"nullable": value.nullable}
        case LockingFallback():
            return {"gate": "LockingFallback"}
        case VersionGated():
            return {"gate": "VersionGated", "attribute": _attribute(value.attribute)}
        case TransactionTimeGated():
            return {
                "gate": "TransactionTimeGated",
                "startAttribute": _attribute(value.start_attribute),
            }
        case TemporalAxisFacts():
            return {
                "dimension": _DIMENSIONS[value.dimension],
                "startAttribute": _attribute(value.start_attribute),
                "endAttribute": _attribute(value.end_attribute),
            }
        case EntitySelectionFacts():
            return {
                "concreteEntities": [_entity(entity) for entity in value.concrete_entities],
                "axes": _fact(value.axes),
            }
        case RelationshipSelectionFacts():
            return {"target": _entity(value.target), "join": _fact(value.join)}
        case WritesDisabled():
            return {"writes": "Disabled"}
        case WritesEnabled():
            return {"writes": "Enabled", "shape": _WRITE_SHAPES[value.shape]}
        case _:
            return _enumerated(value)


def _enumerated(value: object) -> Any:
    """A closed vocabulary's own spelling, a Neutral Type, or a plain integer.

    ``int`` is matched here rather than beside the scalars above because every
    closed vocabulary this module spells is an ``enum.Enum`` over ints, and an
    ``int`` pattern would swallow one before its own arm ran.
    """
    for vocabulary, spellings in _VOCABULARIES:
        if isinstance(value, vocabulary):
            return spellings[value]
    if isinstance(value, int):
        return value
    if isinstance(value, _NEUTRAL_TYPES):
        return format_type_spelling(value)
    raise EvolutionSpellingError(f"no corpus spelling for {value!r}")


def _strategy(strategy: InheritanceStrategy) -> dict[str, Any]:
    if isinstance(strategy, TablePerHierarchy):
        return {"strategy": "table-per-hierarchy", "tag": {"column": strategy.tag_column}}
    return {"strategy": "table-per-concrete-subtype"}


def _descendant(inheritance: Inheritance[EntityIdentity]) -> dict[str, Any]:
    """A non-root participant: its role, its parent, and a concrete tag value."""
    if isinstance(inheritance, AbstractSubtype):
        return {"role": "abstract-subtype", "parent": _entity(inheritance.parent)}
    subtype = cast("ConcreteSubtype[EntityIdentity]", inheritance)
    spelled: dict[str, Any] = {"role": "concrete-subtype", "parent": _entity(subtype.parent)}
    if subtype.tag_value is not None:
        spelled["tag"] = {"value": subtype.tag_value}
    return spelled


def _generation(generation: PkGeneration) -> Any:
    match generation:
        case ApplicationAssigned():
            return "application-assigned"
        case Max():
            return "max"
        case _:
            return {
                "strategy": "sequence",
                "name": generation.name,
                "batchSize": generation.batch_size,
                "initialValue": generation.initial_value,
                "incrementSize": generation.increment_size,
            }
