"""The structural oracle for an `evolution` case's authored Evolution.

`then.evolution` is an authored golden, exactly like golden SQL: the harness owns
no differ and derives none. What it grades is that the authored value could be
one — its vocabularies are the closed ones, every identity it names resolves in
the endpoint that must hold it, and every sequence it declares ordered actually
is. A language implementation grades the VALUE through the conformance adapter.

The canonical order is re-derived here from the reference itself rather than
imported from any implementation: an Entity Identity is the outer key, the member
rank orders the positions inside one Entity, Value-Object containment paths
compare lexicographically, Valid Time precedes Transaction Time, and every
declaration-order operation sorts after every declaration operation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .case import Case, Model
from .database_binding import PhysicalTable, Placement
from .references import split_reference
from .temporality import TEMPORAL_DIMENSION_RANK, temporal_axes

__all__ = [
    "BEHAVIORAL_IMPACT_ORDER",
    "COORDINATION_REASON_ORDER",
    "DECLARATION_COLLECTION_ORDER",
    "FIELD_DELTA_ORDER",
    "EVOLUTION_OPERATION_KINDS",
    "canonical_operation_key",
    "validate_evolution",
]

# The member ranks canonical Model Location order fixes, plus the discriminator
# that sorts every declaration-order operation after every declaration operation.
_ENTITY, _ATTRIBUTE, _RELATIONSHIP, _VALUE_OBJECT, _VO_ATTRIBUTE, _AS_OF_AXIS, _INDEX = range(7)

_IDENTITY_MEMBER: Mapping[str, str] = {
    "EntityAdded": "entity",
    "EntityRemoved": "entity",
    "EntityAltered": "entity",
    "ConcreteSubtypeAdded": "entity",
    "ConcreteSubtypeRemoved": "entity",
    "AttributeAdded": "attribute",
    "AttributeRemoved": "attribute",
    "AttributeAltered": "attribute",
    "ValueObjectOccurrenceAdded": "valueObject",
    "ValueObjectOccurrenceRemoved": "valueObject",
    "ValueObjectOccurrenceAltered": "valueObject",
    "ValueObjectAttributeAdded": "valueObjectAttribute",
    "ValueObjectAttributeRemoved": "valueObjectAttribute",
    "ValueObjectAttributeAltered": "valueObjectAttribute",
    "RelationshipAdded": "relationship",
    "RelationshipRemoved": "relationship",
    "RelationshipAltered": "relationship",
    "AsOfAxisAdded": "entity",
    "AsOfAxisRemoved": "entity",
    "IndexAdded": "index",
    "IndexRemoved": "index",
    "IndexAltered": "index",
    "DeclarationOrderChanged": "owner",
    "TableRelocated": "entity",
    "SequenceRelocated": "sequence",
}

_RELOCATIONS = frozenset({"TableRelocated", "SequenceRelocated"})
_RELOCATION_DIALECTS = ("postgres", "mariadb")

EVOLUTION_OPERATION_KINDS: frozenset[str] = frozenset(_IDENTITY_MEMBER)

_MEMBER_RANK: Mapping[str, int] = {
    "EntityAdded": _ENTITY,
    "EntityRemoved": _ENTITY,
    "EntityAltered": _ENTITY,
    "ConcreteSubtypeAdded": _ENTITY,
    "ConcreteSubtypeRemoved": _ENTITY,
    "AttributeAdded": _ATTRIBUTE,
    "AttributeRemoved": _ATTRIBUTE,
    "AttributeAltered": _ATTRIBUTE,
    "RelationshipAdded": _RELATIONSHIP,
    "RelationshipRemoved": _RELATIONSHIP,
    "RelationshipAltered": _RELATIONSHIP,
    "ValueObjectOccurrenceAdded": _VALUE_OBJECT,
    "ValueObjectOccurrenceRemoved": _VALUE_OBJECT,
    "ValueObjectOccurrenceAltered": _VALUE_OBJECT,
    "ValueObjectAttributeAdded": _VO_ATTRIBUTE,
    "ValueObjectAttributeRemoved": _VO_ATTRIBUTE,
    "ValueObjectAttributeAltered": _VO_ATTRIBUTE,
    "AsOfAxisAdded": _AS_OF_AXIS,
    "AsOfAxisRemoved": _AS_OF_AXIS,
    "IndexAdded": _INDEX,
    "IndexRemoved": _INDEX,
    "IndexAltered": _INDEX,
}

# Each alteration's closed field-delta union, in the fixed order the deltas of one
# operation are emitted in.
FIELD_DELTA_ORDER: Mapping[str, tuple[str, ...]] = {
    "EntityAltered": (
        "StorageContainerChanged",
        "PersistenceChanged",
        "StorageLayoutChanged",
        "InheritanceChanged",
    ),
    "AttributeAltered": (
        "TypeChanged",
        "StorageChanged",
        "MultiplicityChanged",
        "PrimaryKeyChanged",
        "NullabilityChanged",
        "MaximumLengthChanged",
        "ReadOnlyChanged",
        "OptimisticLockingChanged",
    ),
    "ValueObjectOccurrenceAltered": (
        "StorageChanged",
        "MultiplicityChanged",
        "NullabilityChanged",
    ),
    "ValueObjectAttributeAltered": (
        "TypeChanged",
        "MultiplicityChanged",
        "NullabilityChanged",
    ),
    "RelationshipAltered": (
        "DeclarationFormChanged",
        "CardinalityChanged",
        "JoinChanged",
        "ReverseOfChanged",
        "DependencyChanged",
        "OrderingChanged",
    ),
    "IndexAltered": ("ComponentsChanged", "UniquenessChanged"),
}

BEHAVIORAL_IMPACT_ORDER: tuple[str, ...] = (
    "UniquenessEnforcementChanged",
    "ValueAdmissibilityChanged",
    "DeletePropagationChanged",
    "ConcurrencyControlChanged",
    "QueryResultMembershipChanged",
    "QueryResultOrderingChanged",
    "WriteCapabilityChanged",
)

COORDINATION_REASON_ORDER: tuple[str, ...] = (
    "AuthoringSurfaceChangeRequired",
    "DatabaseMigrationRequired",
)

DECLARATION_COLLECTION_ORDER: tuple[str, ...] = (
    "entityAttributes",
    "entityRelationships",
    "entityValueObjects",
    "entityIndices",
    "valueObjectAttributes",
    "nestedValueObjects",
)

# Which endpoints have to hold the identity an operation names: an addition names
# the later model's declaration, a removal the earlier model's, and everything
# else a declaration both retain.
_ADDED = frozenset(kind for kind in EVOLUTION_OPERATION_KINDS if kind.endswith("Added"))
_REMOVED = frozenset(kind for kind in EVOLUTION_OPERATION_KINDS if kind.endswith("Removed"))

# `DeclarationFormChanged` retains both complete declarations, which is why it is
# exclusive: the two forms do not expose the same fields.
_EXCLUSIVE_DELTAS = frozenset({"DeclarationFormChanged"})


@dataclass(frozen=True)
class _Endpoint:
    """One accepted model's declared identities, indexed for resolution."""

    entities: frozenset[str] = frozenset()
    attributes: frozenset[str] = frozenset()
    relationships: frozenset[str] = frozenset()
    indices: frozenset[str] = frozenset()
    value_objects: frozenset[str] = frozenset()
    value_object_attributes: frozenset[str] = frozenset()
    axes: frozenset[tuple[str, str]] = frozenset()
    allocators: frozenset[str] = frozenset()


@dataclass
class _Index:
    entities: set[str] = field(default_factory=set)
    attributes: set[str] = field(default_factory=set)
    relationships: set[str] = field(default_factory=set)
    indices: set[str] = field(default_factory=set)
    value_objects: set[str] = field(default_factory=set)
    value_object_attributes: set[str] = field(default_factory=set)
    axes: set[tuple[str, str]] = field(default_factory=set)
    allocators: set[str] = field(default_factory=set)


def _entity_spelling(definition: Mapping[str, Any]) -> str:
    namespace = definition.get("namespace")
    name = str(definition.get("name"))
    return f"{namespace}.{name}" if isinstance(namespace, str) and namespace else name


def _index_occurrences(
    index: _Index, owner: str, occurrences: Iterable[Any], path: tuple[str, ...]
) -> None:
    for occurrence in occurrences:
        if not isinstance(occurrence, Mapping):
            continue
        here = (*path, str(occurrence.get("name")))
        index.value_objects.add(".".join((owner, *here)))
        for attribute in occurrence.get("attributes") or []:
            if isinstance(attribute, Mapping):
                index.value_object_attributes.add(
                    ".".join((owner, *here, str(attribute.get("name"))))
                )
        _index_occurrences(index, owner, occurrence.get("valueObjects") or [], here)


def _index_attributes(index: _Index, owner: str, attributes: Iterable[Any]) -> None:
    for attribute in attributes:
        if not isinstance(attribute, Mapping):
            continue
        index.attributes.add(f"{owner}.{attribute.get('name')}")
        generation = attribute.get("pkGeneration")
        if isinstance(generation, Mapping) and generation.get("strategy") == "sequence":
            index.allocators.add(str(generation.get("name")))


def _endpoint(model: Model | None) -> _Endpoint:
    """Every identity ``model`` declares, or an empty endpoint for absence."""
    if model is None:
        return _Endpoint()
    index = _Index()
    for definition in model.entity_defs:
        owner = _entity_spelling(definition)
        index.entities.add(owner)
        _index_attributes(index, owner, definition.get("attributes") or [])
        for relationship in definition.get("relationships") or []:
            if isinstance(relationship, Mapping):
                index.relationships.add(f"{owner}.{relationship.get('name')}")
        for declared in definition.get("indices") or []:
            if isinstance(declared, Mapping):
                index.indices.add(f"{owner}.{declared.get('name')}")
        _index_occurrences(index, owner, definition.get("valueObjects") or [], ())
        for axis in temporal_axes(definition):
            index.axes.add((owner, axis.dimension))
    return _Endpoint(
        entities=frozenset(index.entities),
        attributes=frozenset(index.attributes),
        relationships=frozenset(index.relationships),
        indices=frozenset(index.indices),
        value_objects=frozenset(index.value_objects),
        value_object_attributes=frozenset(index.value_object_attributes),
        axes=frozenset(index.axes),
        allocators=frozenset(index.allocators),
    )


def _declared(endpoint: _Endpoint, member: str, spelling: str) -> bool:
    return (
        spelling
        in {
            "entity": endpoint.entities,
            "attribute": endpoint.attributes,
            "relationship": endpoint.relationships,
            "index": endpoint.indices,
            "valueObject": endpoint.value_objects,
            "valueObjectAttribute": endpoint.value_object_attributes,
            "owner": endpoint.entities | endpoint.value_objects,
            "sequence": endpoint.allocators,
        }[member]
    )


def canonical_operation_key(operation: Mapping[str, Any]) -> tuple[Any, ...]:
    """One operation's canonical inspection-order key.

    Entity Identity is the outer key, the member rank orders positions inside one
    Entity, containment paths compare lexicographically, and Valid Time precedes
    Transaction Time. Add, remove, and alter cannot tie at one logical identity,
    so the key carries no operation-kind rank and a rename's removal and addition
    stay in identity order rather than being forced removal-first. Every
    relocation follows every logical operation: table relocations in owner
    order, then sequence relocations in allocator-key codepoint order.
    """
    kind = str(operation.get("kind"))
    member = _IDENTITY_MEMBER.get(kind, "entity")
    spelling = str(operation.get(member, ""))
    if kind == "SequenceRelocated":
        return (3, "", spelling, 0, (), "", 0, 0)
    entity, path = split_reference(spelling)
    namespace, _, name = (entity or "").rpartition(".")
    if kind == "TableRelocated":
        return (2, namespace, name, 0, (), "", 0, 0)
    if kind == "DeclarationOrderChanged":
        collection = str(operation.get("collection"))
        rank = _VALUE_OBJECT if path else _ENTITY
        return (
            1,
            namespace,
            name,
            rank,
            path,
            "",
            0,
            _order_or_last(DECLARATION_COLLECTION_ORDER, collection),
        )
    rank = _MEMBER_RANK[kind]
    if rank == _VALUE_OBJECT:
        return (0, namespace, name, rank, path, "", 0, 0)
    if rank == _VO_ATTRIBUTE:
        return (0, namespace, name, rank, path[:-1], path[-1] if path else "", 0, 0)
    if rank == _AS_OF_AXIS:
        dimension = str(operation.get("dimension"))
        axis_rank = TEMPORAL_DIMENSION_RANK.get(dimension, len(TEMPORAL_DIMENSION_RANK))
        return (0, namespace, name, rank, (), "", axis_rank, 0)
    return (0, namespace, name, rank, (), path[0] if path else "", 0, 0)


def _order_or_last(order: Sequence[str], value: str) -> int:
    return order.index(value) if value in order else len(order)


def _sequence(node: Any) -> list[Mapping[str, Any]]:
    return [item for item in node or [] if isinstance(item, Mapping)]


def _is_ordered(items: Sequence[Any], key: Any) -> bool:
    keys = [key(item) for item in items]
    return keys == sorted(keys)


def validate_evolution(case: Case) -> list[str]:
    """Every structural finding in ``case``'s authored Evolution (empty ⇒ sound)."""
    evolution = case.expected_evolution
    if not isinstance(evolution, Mapping):
        return [f"{case.path.name}: evolution case declares no then.evolution"]

    later = _endpoint(case.model)
    earlier = _endpoint(case.earlier_model)
    findings: list[str] = []
    operations = _sequence(evolution.get("operations"))

    for position, operation in enumerate(operations):
        findings += _findings_for_operation(
            case, f"operations[{position}]", operation, earlier, later
        )
    if not _is_ordered(operations, canonical_operation_key):
        findings.append(
            f"{case.path.name}: then.evolution.operations is not in canonical Model Location order"
        )

    findings += _impact_findings(case, _sequence(evolution.get("behavioralImpacts")), operations)
    findings += _overlap_findings(
        case, _sequence(evolution.get("overlapVisibleOperations")), operations
    )
    findings += _requirement_findings(
        case, _sequence(evolution.get("coordinationRequirements")), operations
    )
    findings += _relocation_findings(case, evolution, operations)
    return findings


def _physical(table: PhysicalTable) -> dict[str, Any]:
    return {"qualifier": list(table.qualifier), "name": table.name}


def _relocations(earlier: Placement, later: Placement) -> list[dict[str, Any]]:
    """Every surviving owner's, then allocator's, relocation from *earlier* to
    *later*, in relocation order, spelled as an authored operation."""
    tables = [
        {
            "kind": "TableRelocated",
            "entity": owner,
            "earlier": _physical(earlier.tables[owner]),
            "later": _physical(table),
        }
        for owner, table in later.tables.items()
        if owner in earlier.tables and earlier.tables[owner] != table
    ]
    sequences = [
        {
            "kind": "SequenceRelocated",
            "sequence": allocator,
            "earlier": _physical(earlier.sequences[allocator]),
            "later": _physical(sequence),
        }
        for allocator, sequence in later.sequences.items()
        if allocator in earlier.sequences and earlier.sequences[allocator] != sequence
    ]
    return sorted(tables, key=canonical_operation_key) + sorted(
        sequences, key=canonical_operation_key
    )


def _relocation_findings(
    case: Case, evolution: Mapping[str, Any], operations: Sequence[Mapping[str, Any]]
) -> list[str]:
    """The authored relocations must be exactly those the two endpoints resolve
    to under each dialect's binding, and each needs a database migration."""
    authored = [
        dict(operation) for operation in operations if operation.get("kind") in _RELOCATIONS
    ]
    findings: list[str] = []
    if case.earlier_model is not None:
        for dialect in _RELOCATION_DIALECTS:
            expected = _relocations(
                case.placement(dialect, case.earlier_model, "earlierBinding"),
                case.placement(dialect, case.model, "laterBinding"),
            )
            if authored != expected:
                findings.append(
                    f"{case.path.name}: then.evolution's relocations {authored} are not the "
                    f"{dialect} endpoints' resolved relocations {expected}"
                )
    elif authored:
        findings.append(f"{case.path.name}: an absent earlier endpoint relocates nothing")
    migrating = [
        requirement.get("operation")
        for requirement in _sequence(evolution.get("coordinationRequirements"))
        if "DatabaseMigrationRequired" in (requirement.get("reasons") or [])
    ]
    for operation in authored:
        if operation not in migrating:
            subject = operation.get("entity") or operation.get("sequence")
            findings.append(
                f"{case.path.name}: {operation['kind']} of {subject} carries no "
                f"DatabaseMigrationRequired coordination requirement"
            )
    if authored and evolution.get("kind") != "coordinated":
        findings.append(
            f"{case.path.name}: an evolution relocating a table or sequence is coordinated"
        )
    return findings


def _findings_for_operation(
    case: Case,
    where: str,
    operation: Mapping[str, Any],
    earlier: _Endpoint,
    later: _Endpoint,
) -> list[str]:
    kind = str(operation.get("kind"))
    if kind not in EVOLUTION_OPERATION_KINDS:
        return [f"{case.path.name}: {where}: {kind!r} is not an Evolution Operation"]
    findings: list[str] = []
    member = _IDENTITY_MEMBER[kind]
    spelling = str(operation.get(member, ""))
    for endpoint, label in _resolving_endpoints(kind, earlier, later):
        if not _declared(endpoint, member, spelling):
            findings.append(
                f"{case.path.name}: {where}: {spelling!r} is not declared by the {label} endpoint"
            )
    if kind.startswith("AsOfAxis"):
        dimension = str(operation.get("dimension"))
        for endpoint, label in _resolving_endpoints(kind, earlier, later):
            if (spelling, dimension) not in endpoint.axes:
                findings.append(
                    f"{case.path.name}: {where}: {spelling} declares no {dimension} axis in "
                    f"the {label} endpoint"
                )
    findings += _delta_findings(case, where, kind, operation)
    if kind == "DeclarationOrderChanged":
        findings += _reorder_findings(case, where, operation)
    return findings


def _resolving_endpoints(
    kind: str, earlier: _Endpoint, later: _Endpoint
) -> list[tuple[_Endpoint, str]]:
    if kind in _ADDED:
        return [(later, "later")]
    if kind in _REMOVED:
        return [(earlier, "earlier")]
    return [(earlier, "earlier"), (later, "later")]


def _delta_findings(case: Case, where: str, kind: str, operation: Mapping[str, Any]) -> list[str]:
    order = FIELD_DELTA_ORDER.get(kind)
    if order is None:
        return []
    deltas = _sequence(operation.get("deltas"))
    kinds = [str(delta.get("kind")) for delta in deltas]
    findings: list[str] = []
    unknown = [name for name in kinds if name not in order]
    if unknown:
        findings.append(f"{case.path.name}: {where}: {kind} carries {unknown}, not its own deltas")
    if len(set(kinds)) != len(kinds):
        findings.append(f"{case.path.name}: {where}: {kind} repeats a field delta")
    ranked = [order.index(name) for name in kinds if name in order]
    if ranked != sorted(ranked):
        findings.append(f"{case.path.name}: {where}: {kind} deltas are not in fixed field order")
    exclusive = _EXCLUSIVE_DELTAS.intersection(kinds)
    if exclusive and len(kinds) > 1:
        findings.append(
            f"{case.path.name}: {where}: {sorted(exclusive)} is exclusive and admits no "
            f"accompanying delta"
        )
    return findings


def _reorder_findings(case: Case, where: str, operation: Mapping[str, Any]) -> list[str]:
    collection = str(operation.get("collection"))
    findings: list[str] = []
    if collection not in DECLARATION_COLLECTION_ORDER:
        findings.append(f"{case.path.name}: {where}: {collection!r} is not a local collection")
    before = list(operation.get("earlier") or [])
    after = list(operation.get("later") or [])
    if sorted(before) != sorted(after):
        findings.append(
            f"{case.path.name}: {where}: a reorder compares the SAME surviving identities, "
            f"and these two sequences name different ones"
        )
    elif before == after:
        findings.append(
            f"{case.path.name}: {where}: the two sequences are equal, so nothing was reordered"
        )
    return findings


def _impact_findings(
    case: Case, impacts: Sequence[Mapping[str, Any]], operations: Sequence[Mapping[str, Any]]
) -> list[str]:
    findings: list[str] = []
    for position, impact in enumerate(impacts):
        where = f"behavioralImpacts[{position}]"
        kind = str(impact.get("kind"))
        if kind not in BEHAVIORAL_IMPACT_ORDER:
            findings.append(f"{case.path.name}: {where}: {kind!r} is not a Behavioral Impact")
        findings += _caused_by_findings(case, where, impact.get("causedBy"), operations)
    keys = [
        (_order_or_last(BEHAVIORAL_IMPACT_ORDER, str(impact.get("kind"))), _scope_key(impact))
        for impact in impacts
    ]
    if keys != sorted(keys):
        findings.append(
            f"{case.path.name}: then.evolution.behavioralImpacts is not in closed variant order "
            f"and then scope identity"
        )
    return findings


_SCOPE_RANK: Mapping[str, int] = {
    "entity": _ENTITY,
    "attribute": _ATTRIBUTE,
    "relationship": _RELATIONSHIP,
    "valueObject": _VALUE_OBJECT,
    "valueObjectAttribute": _VO_ATTRIBUTE,
}


def _scope_key(impact: Mapping[str, Any]) -> tuple[Any, ...]:
    """One impact scope's canonical Model Location key.

    The same law the operations follow: Entity Identity outside, then the member
    rank, then the rank's own detail. A malformed scope sorts last rather than
    colliding with a well-formed one.
    """
    scope = impact.get("scope")
    if not isinstance(scope, Mapping) or len(scope) != 1:
        return ("", "", len(_SCOPE_RANK), (), "")
    member, spelling = next(iter(scope.items()))
    entity, path = split_reference(str(spelling))
    namespace, _, name = (entity or "").rpartition(".")
    rank = _SCOPE_RANK.get(str(member), len(_SCOPE_RANK))
    if rank == _VALUE_OBJECT:
        return (namespace, name, rank, path, "")
    if rank == _VO_ATTRIBUTE:
        return (namespace, name, rank, path[:-1], path[-1] if path else "")
    return (namespace, name, rank, (), path[0] if path else "")


def _caused_by_findings(
    case: Case, where: str, caused_by: Any, operations: Sequence[Mapping[str, Any]]
) -> list[str]:
    causes = _sequence(caused_by)
    findings: list[str] = []
    for cause in causes:
        if cause not in operations:
            findings.append(
                f"{case.path.name}: {where}.causedBy names an operation the evolution does "
                f"not describe: {cause.get('kind')}"
            )
    if not _is_ordered(causes, canonical_operation_key):
        findings.append(f"{case.path.name}: {where}.causedBy is not in canonical operation order")
    if len({canonical_operation_key(cause) for cause in causes}) != len(causes):
        findings.append(f"{case.path.name}: {where}.causedBy repeats an operation")
    return findings


def _overlap_findings(
    case: Case, overlap: Sequence[Mapping[str, Any]], operations: Sequence[Mapping[str, Any]]
) -> list[str]:
    findings = [
        f"{case.path.name}: then.evolution.overlapVisibleOperations names an operation the "
        f"evolution does not describe: {item.get('kind')}"
        for item in overlap
        if item not in operations
    ]
    if not _is_ordered(overlap, canonical_operation_key):
        findings.append(
            f"{case.path.name}: then.evolution.overlapVisibleOperations is not in canonical "
            f"operation order"
        )
    return findings


def _requirement_findings(
    case: Case,
    requirements: Sequence[Mapping[str, Any]],
    operations: Sequence[Mapping[str, Any]],
) -> list[str]:
    findings: list[str] = []
    for position, requirement in enumerate(requirements):
        where = f"coordinationRequirements[{position}]"
        operation = requirement.get("operation")
        if not isinstance(operation, Mapping) or operation not in operations:
            findings.append(
                f"{case.path.name}: {where}.operation is not one of the evolution's operations"
            )
        reasons = [str(reason) for reason in requirement.get("reasons") or []]
        unknown = [reason for reason in reasons if reason not in COORDINATION_REASON_ORDER]
        if unknown:
            findings.append(f"{case.path.name}: {where}.reasons carries {unknown}")
        ranked = [
            COORDINATION_REASON_ORDER.index(reason)
            for reason in reasons
            if reason in COORDINATION_REASON_ORDER
        ]
        if ranked != sorted(ranked) or len(set(ranked)) != len(ranked):
            findings.append(
                f"{case.path.name}: {where}.reasons is not the fixed reason order without repeats"
            )
    named = [
        operation
        for requirement in requirements
        if isinstance(operation := requirement.get("operation"), Mapping)
    ]
    if not _is_ordered(named, canonical_operation_key):
        findings.append(
            f"{case.path.name}: then.evolution.coordinationRequirements is not in canonical "
            f"operation order"
        )
    if len(named) != len({canonical_operation_key(operation) for operation in named}):
        findings.append(
            f"{case.path.name}: then.evolution.coordinationRequirements names one operation twice"
        )
    return findings
