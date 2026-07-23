"""The fixed foundational resolver (m-metamodel).

Resolution is the one gate between a frontend's Unresolved Metamodel and the
Candidate Metamodel semantic Rule Sets validate. It aggregates every
foundational issue — identity grammar, duplicate identities, unresolvable
references, local member collisions, reserved temporal names, standalone
primary keys, indices, and As-Of Axes — and either rejects with all of them or
produces a candidate whose relationship and inheritance references are
canonical Identities. It advances references and nothing else: it never pairs
relationship directions, swaps joins, inverts cardinality, derives inheritance,
or implements another module's semantic rules.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Final

from parallax.core.base import Timestamp
from parallax.core.metamodel._identities import (
    AttributeIdentity,
    EntityIdentity,
    EntityReference,
    RelationshipIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    resolve_entity_reference,
)
from parallax.core.metamodel._issues import (
    AsOfAxisLocation,
    AttributeLocation,
    EntityLocation,
    IndexLocation,
    IssueCode,
    MetamodelIssue,
    ModelLocation,
    RelationshipLocation,
    ValueObjectAttributeLocation,
    ValueObjectLocation,
    sort_issues,
)
from parallax.core.metamodel._states import (
    CandidateMetamodel,
    EntityDeclaration,
    UnresolvedEntityDeclaration,
    UnresolvedMetamodel,
)
from parallax.core.metamodel._values import (
    AbstractRoot,
    AbstractSubtype,
    AsOfAxisMetadata,
    AttributeMetadata,
    ConcreteSubtype,
    DefiningRelationshipDeclaration,
    IndexMetadata,
    InheritanceMetadata,
    PersistenceMode,
    PrimaryKey,
    RelationshipDeclaration,
    RelationshipJoin,
    RelationshipOrder,
    ReverseRelationshipDeclaration,
    StorageContainer,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedInheritance,
    UnresolvedReverseRelationshipDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)

__all__ = [
    "AS_OF_ATTRIBUTE_DUPLICATE",
    "AS_OF_ATTRIBUTE_MISSING",
    "AS_OF_ATTRIBUTE_OWNER",
    "AS_OF_ATTRIBUTE_TYPE",
    "AS_OF_DIMENSION_DUPLICATE",
    "DUPLICATE_ENTITY_IDENTITY",
    "INDEX_ATTRIBUTE_DUPLICATE",
    "INDEX_ATTRIBUTE_MISSING",
    "INDEX_ATTRIBUTE_NOT_LOCAL",
    "INDEX_EMPTY",
    "INVALID_ENTITY_IDENTITY",
    "LOCAL_MEMBER_COLLISION",
    "PRIMARY_KEY_MISSING",
    "PRIMARY_KEY_MULTIPLE",
    "RESOLVER_ISSUE_CODES",
    "TEMPORAL_MEMBER_RESERVED",
    "UNRESOLVED_ATTRIBUTE_REFERENCE",
    "UNRESOLVED_ENTITY_REFERENCE",
    "UNRESOLVED_RELATIONSHIP_REFERENCE",
    "Rejected",
    "ResolutionResult",
    "Resolved",
    "resolve",
]

INVALID_ENTITY_IDENTITY: Final[IssueCode] = "metamodel-invalid-entity-identity"
DUPLICATE_ENTITY_IDENTITY: Final[IssueCode] = "metamodel-duplicate-entity-identity"
UNRESOLVED_ENTITY_REFERENCE: Final[IssueCode] = "metamodel-unresolved-entity-reference"
UNRESOLVED_ATTRIBUTE_REFERENCE: Final[IssueCode] = "metamodel-unresolved-attribute-reference"
UNRESOLVED_RELATIONSHIP_REFERENCE: Final[IssueCode] = "metamodel-unresolved-relationship-reference"
LOCAL_MEMBER_COLLISION: Final[IssueCode] = "metamodel-local-member-collision"
TEMPORAL_MEMBER_RESERVED: Final[IssueCode] = "metamodel-temporal-member-reserved"
PRIMARY_KEY_MISSING: Final[IssueCode] = "metamodel-primary-key-missing"
PRIMARY_KEY_MULTIPLE: Final[IssueCode] = "metamodel-primary-key-multiple"
INDEX_EMPTY: Final[IssueCode] = "metamodel-index-empty"
INDEX_ATTRIBUTE_MISSING: Final[IssueCode] = "metamodel-index-attribute-missing"
INDEX_ATTRIBUTE_NOT_LOCAL: Final[IssueCode] = "metamodel-index-attribute-not-local"
INDEX_ATTRIBUTE_DUPLICATE: Final[IssueCode] = "metamodel-index-attribute-duplicate"
AS_OF_DIMENSION_DUPLICATE: Final[IssueCode] = "metamodel-as-of-dimension-duplicate"
AS_OF_ATTRIBUTE_MISSING: Final[IssueCode] = "metamodel-as-of-attribute-missing"
AS_OF_ATTRIBUTE_OWNER: Final[IssueCode] = "metamodel-as-of-attribute-owner"
AS_OF_ATTRIBUTE_TYPE: Final[IssueCode] = "metamodel-as-of-attribute-type"
AS_OF_ATTRIBUTE_DUPLICATE: Final[IssueCode] = "metamodel-as-of-attribute-duplicate"

RESOLVER_ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset(
    {
        INVALID_ENTITY_IDENTITY,
        DUPLICATE_ENTITY_IDENTITY,
        UNRESOLVED_ENTITY_REFERENCE,
        UNRESOLVED_ATTRIBUTE_REFERENCE,
        UNRESOLVED_RELATIONSHIP_REFERENCE,
        LOCAL_MEMBER_COLLISION,
        TEMPORAL_MEMBER_RESERVED,
        PRIMARY_KEY_MISSING,
        PRIMARY_KEY_MULTIPLE,
        INDEX_EMPTY,
        INDEX_ATTRIBUTE_MISSING,
        INDEX_ATTRIBUTE_NOT_LOCAL,
        INDEX_ATTRIBUTE_DUPLICATE,
        AS_OF_DIMENSION_DUPLICATE,
        AS_OF_ATTRIBUTE_MISSING,
        AS_OF_ATTRIBUTE_OWNER,
        AS_OF_ATTRIBUTE_TYPE,
        AS_OF_ATTRIBUTE_DUPLICATE,
    }
)
"""The resolver's complete owned Issue Code set, as the Formation Manifest
declares it. No other module may emit a ``metamodel-*`` code."""

# The Attribute names each Temporal Dimension reserves once an Entity declares
# that dimension. Only the axis's own start and end Attributes may bear them.
_CONVENTIONAL_TEMPORAL_NAMES: Final[Mapping[TemporalDimension, tuple[str, str]]] = {
    TemporalDimension.VALID_TIME: ("valid_start", "valid_end"),
    TemporalDimension.TRANSACTION_TIME: ("tx_start", "tx_end"),
}


@dataclass(frozen=True, slots=True)
class _EntityDeclaration:
    identity: EntityIdentity
    container: StorageContainer | None
    persistence: PersistenceMode | None
    attributes: tuple[AttributeMetadata, ...]
    relationships: tuple[RelationshipDeclaration, ...]
    value_objects: tuple[ValueObjectOccurrenceDeclaration, ...]
    as_of_axes: tuple[AsOfAxisMetadata, ...]
    inheritance: InheritanceMetadata | None
    indices: tuple[IndexMetadata, ...]


@dataclass(frozen=True, slots=True)
class _CandidateMetamodel:
    entities: tuple[EntityDeclaration, ...]
    _by_identity: Mapping[EntityIdentity, EntityDeclaration] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_by_identity", {entity.identity: entity for entity in self.entities}
        )

    def entity(self, identity: EntityIdentity) -> EntityDeclaration | None:
        return self._by_identity.get(identity)


@dataclass(frozen=True, slots=True)
class Resolved:
    """Foundational resolution succeeded; semantic validation may proceed."""

    candidate: CandidateMetamodel


@dataclass(frozen=True, slots=True)
class Rejected:
    """Foundational resolution failed; no candidate exists and no Rule Set runs."""

    issues: tuple[MetamodelIssue, ...]


type ResolutionResult = Resolved | Rejected
"""The resolver's exact collaboration result."""


def resolve(unresolved: UnresolvedMetamodel) -> ResolutionResult:
    """Resolve ``unresolved`` into a Candidate Metamodel or every issue blocking it.

    Aggregating: the result names every foundational defect in the model, not
    the first one found. Resolution never partially succeeds — a rejected model
    yields no candidate at all.
    """
    declarations = tuple(unresolved.entities)
    issues: list[MetamodelIssue] = []
    index: dict[EntityIdentity, UnresolvedEntityDeclaration] = {}
    for declaration in declarations:
        identity = declaration.identity
        if not _well_formed_entity_name(identity.name):
            issues.append(
                MetamodelIssue(
                    INVALID_ENTITY_IDENTITY,
                    EntityLocation(identity),
                    message=(f"Entity name {identity.name!r} is not a nonempty dot-free name"),
                )
            )
        if identity in index:
            issues.append(
                MetamodelIssue(
                    DUPLICATE_ENTITY_IDENTITY,
                    EntityLocation(identity),
                    message=f"two declarations resolve to Entity {identity.canonical!r}",
                )
            )
        else:
            index[identity] = declaration

    entities: list[EntityDeclaration] = []
    for declaration in declarations:
        issues.extend(_collision_issues(declaration))
        issues.extend(_temporal_reservation_issues(declaration))
        issues.extend(_primary_key_issues(declaration))
        issues.extend(_index_issues(declaration, index))
        issues.extend(_axis_issues(declaration))
        relationships, relationship_issues = _resolve_relationships(declaration, index)
        inheritance, inheritance_issues = _resolve_inheritance(declaration, index)
        issues.extend(relationship_issues)
        issues.extend(inheritance_issues)
        entities.append(
            _EntityDeclaration(
                identity=declaration.identity,
                container=declaration.container,
                persistence=declaration.persistence,
                attributes=tuple(declaration.attributes),
                relationships=relationships,
                value_objects=tuple(declaration.value_objects),
                as_of_axes=tuple(declaration.as_of_axes),
                inheritance=inheritance,
                indices=tuple(declaration.indices),
            )
        )

    if issues:
        return Rejected(sort_issues(issues))
    return Resolved(
        _CandidateMetamodel(tuple(sorted(entities, key=lambda entity: entity.identity.sort_key)))
    )


def _well_formed_entity_name(name: str) -> bool:
    return bool(name) and "." not in name


def _local_member_positions(
    declaration: UnresolvedEntityDeclaration,
) -> Iterator[tuple[str, ModelLocation]]:
    """Every navigable local member name of ``declaration`` with its location.

    Attributes, relationships, and top-level Value Objects share one navigable
    namespace, so they are enumerated together.
    """
    for attribute in declaration.attributes:
        yield attribute.identity.name, AttributeLocation(attribute.identity)
    for relationship in declaration.relationships:
        yield relationship.identity.name, RelationshipLocation(relationship.identity)
    for occurrence in declaration.value_objects:
        yield (
            occurrence.name,
            ValueObjectLocation(ValueObjectIdentity(declaration.identity, (occurrence.name,))),
        )


def _collision_issues(declaration: UnresolvedEntityDeclaration) -> list[MetamodelIssue]:
    issues = _name_collision_issues(_local_member_positions(declaration))
    for occurrence in declaration.value_objects:
        issues.extend(
            _shape_collision_issues(
                declaration.identity, (occurrence.name,), occurrence.shape, frozenset()
            )
        )
    return issues


def _name_collision_issues(
    positions: Iterable[tuple[str, ModelLocation]],
) -> list[MetamodelIssue]:
    issues: list[MetamodelIssue] = []
    first: dict[str, ModelLocation] = {}
    for name, location in positions:
        declared = first.get(name)
        if declared is None:
            first[name] = location
            continue
        issues.append(
            MetamodelIssue(
                LOCAL_MEMBER_COLLISION,
                location,
                (declared,),
                message=f"the local member name {name!r} is already declared",
            )
        )
    return issues


def _shape_collision_issues(
    entity: EntityIdentity,
    path: tuple[str, ...],
    shape: ValueObjectShapeDeclaration,
    visited: frozenset[ValueObjectShapeKey],
) -> list[MetamodelIssue]:
    """Collisions inside one Value Object occurrence and everything below it.

    A shape reached twice on one containment path is a containment cycle that
    ``m-value-object`` reports; this walk stops there rather than recursing.
    """
    if shape.key in visited:
        return []
    identity = ValueObjectIdentity(entity, path)
    positions: list[tuple[str, ModelLocation]] = [
        (
            attribute.name,
            ValueObjectAttributeLocation(ValueObjectAttributeIdentity(identity, attribute.name)),
        )
        for attribute in shape.attributes
    ]
    positions.extend(
        (nested.name, ValueObjectLocation(ValueObjectIdentity(entity, (*path, nested.name))))
        for nested in shape.value_objects
    )
    issues = _name_collision_issues(positions)
    below = visited | {shape.key}
    for nested in shape.value_objects:
        issues.extend(_shape_collision_issues(entity, (*path, nested.name), nested.shape, below))
    return issues


def _temporal_reservation_issues(
    declaration: UnresolvedEntityDeclaration,
) -> list[MetamodelIssue]:
    reserved: dict[str, TemporalDimension] = {}
    framework: set[AttributeIdentity] = set()
    for axis in declaration.as_of_axes:
        for name in _CONVENTIONAL_TEMPORAL_NAMES[axis.dimension]:
            reserved[name] = axis.dimension
        framework.add(axis.start_attribute)
        framework.add(axis.end_attribute)
    if not reserved:
        return []

    issues: list[MetamodelIssue] = []

    def reject(name: str, location: ModelLocation) -> None:
        dimension = reserved.get(name)
        if dimension is None:
            return
        issues.append(
            MetamodelIssue(
                TEMPORAL_MEMBER_RESERVED,
                location,
                (AsOfAxisLocation(declaration.identity, dimension),),
                message=f"the member name {name!r} is reserved by this Entity's temporal shape",
            )
        )

    for attribute in declaration.attributes:
        if attribute.identity not in framework:
            reject(attribute.identity.name, AttributeLocation(attribute.identity))
    for relationship in declaration.relationships:
        reject(relationship.identity.name, RelationshipLocation(relationship.identity))
    for occurrence in declaration.value_objects:
        reject(
            occurrence.name,
            ValueObjectLocation(ValueObjectIdentity(declaration.identity, (occurrence.name,))),
        )
    return issues


def _primary_key_issues(declaration: UnresolvedEntityDeclaration) -> list[MetamodelIssue]:
    """The standalone-Entity primary-key rules.

    An inheritance participant's key is family-wide and root-owned, so
    ``m-inheritance`` owns its equivalent rules.
    """
    if declaration.inheritance is not None:
        return []
    keys = [
        attribute
        for attribute in declaration.attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
    location = EntityLocation(declaration.identity)
    if not keys:
        return [
            MetamodelIssue(
                PRIMARY_KEY_MISSING,
                location,
                message="a standalone Entity declares one primary-key Attribute",
            )
        ]
    if len(keys) > 1:
        return [
            MetamodelIssue(
                PRIMARY_KEY_MULTIPLE,
                location,
                tuple(AttributeLocation(attribute.identity) for attribute in keys),
                message=f"{len(keys)} primary-key Attributes are declared; exactly one is allowed",
            )
        ]
    return []


def _index_issues(
    declaration: UnresolvedEntityDeclaration,
    index: Mapping[EntityIdentity, UnresolvedEntityDeclaration],
) -> list[MetamodelIssue]:
    local = {attribute.identity.name for attribute in declaration.attributes}
    issues: list[MetamodelIssue] = []
    for declared_index in declaration.indices:
        location = IndexLocation(declared_index.identity)
        if not declared_index.attributes:
            issues.append(
                MetamodelIssue(
                    INDEX_EMPTY, location, message="an Index declares at least one Attribute"
                )
            )
        seen: set[AttributeIdentity] = set()
        for component in declared_index.attributes:
            related = (AttributeLocation(component),)
            if component in seen:
                issues.append(
                    MetamodelIssue(
                        INDEX_ATTRIBUTE_DUPLICATE,
                        location,
                        related,
                        message=f"Attribute {component.name!r} occurs more than once in the Index",
                    )
                )
            seen.add(component)
            if component.entity != declaration.identity:
                issues.append(
                    MetamodelIssue(
                        INDEX_ATTRIBUTE_NOT_LOCAL,
                        location,
                        related,
                        message="an Index component belongs to another Entity",
                    )
                )
            elif component.name not in local:
                inherited = _applicable_attribute(declaration, component.name, index) is not None
                issues.append(
                    MetamodelIssue(
                        INDEX_ATTRIBUTE_NOT_LOCAL if inherited else INDEX_ATTRIBUTE_MISSING,
                        location,
                        related,
                        message=(
                            f"Index component {component.name!r} is inherited"
                            if inherited
                            else f"Index component {component.name!r} names no declared Attribute"
                        ),
                    )
                )
    return issues


def _axis_issues(declaration: UnresolvedEntityDeclaration) -> list[MetamodelIssue]:
    local = {attribute.identity.name: attribute for attribute in declaration.attributes}
    issues: list[MetamodelIssue] = []
    seen: set[TemporalDimension] = set()
    for axis in declaration.as_of_axes:
        location = AsOfAxisLocation(declaration.identity, axis.dimension)
        if axis.dimension in seen:
            issues.append(
                MetamodelIssue(
                    AS_OF_DIMENSION_DUPLICATE,
                    location,
                    message="one Temporal Dimension is declared more than once",
                )
            )
        seen.add(axis.dimension)
        if axis.start_attribute == axis.end_attribute:
            issues.append(
                MetamodelIssue(
                    AS_OF_ATTRIBUTE_DUPLICATE,
                    location,
                    (AttributeLocation(axis.start_attribute),),
                    message="an axis start and end identify the same Attribute",
                )
            )
        for endpoint in (axis.start_attribute, axis.end_attribute):
            issues.extend(_axis_endpoint_issues(declaration.identity, location, endpoint, local))
    return issues


def _axis_endpoint_issues(
    entity: EntityIdentity,
    location: AsOfAxisLocation,
    endpoint: AttributeIdentity,
    local: Mapping[str, AttributeMetadata],
) -> list[MetamodelIssue]:
    related = (AttributeLocation(endpoint),)
    if endpoint.entity != entity:
        return [
            MetamodelIssue(
                AS_OF_ATTRIBUTE_OWNER,
                location,
                related,
                message="an axis Attribute belongs to another Entity",
            )
        ]
    attribute = local.get(endpoint.name)
    if attribute is None:
        return [
            MetamodelIssue(
                AS_OF_ATTRIBUTE_MISSING,
                location,
                related,
                message=f"axis Attribute {endpoint.name!r} does not exist",
            )
        ]
    if not isinstance(attribute.type, Timestamp):
        return [
            MetamodelIssue(
                AS_OF_ATTRIBUTE_TYPE,
                location,
                related,
                message=f"axis Attribute {endpoint.name!r} is not a Timestamp",
            )
        ]
    return []


def _declared_parent(inheritance: UnresolvedInheritance | None) -> EntityReference | None:
    match inheritance:
        case None | AbstractRoot():
            return None
        case AbstractSubtype(parent) | ConcreteSubtype(parent, _):
            return parent


def _applicable_attribute(
    declaration: UnresolvedEntityDeclaration,
    name: str,
    index: Mapping[EntityIdentity, UnresolvedEntityDeclaration],
) -> AttributeMetadata | None:
    """The Attribute ``name`` denotes at ``declaration``'s position, or absence.

    A declared inheritance parent extends the position's Attribute set, so a
    reference into a family member resolves against the ancestry chain as well
    as the local declarations. The walk is purely structural over the parent
    links the declaration already carries and stops on a cycle; family
    coherence is ``m-inheritance``'s rule.
    """
    current: UnresolvedEntityDeclaration | None = declaration
    seen: set[EntityIdentity] = set()
    while current is not None and current.identity not in seen:
        seen.add(current.identity)
        for attribute in current.attributes:
            if attribute.identity.name == name:
                return attribute
        parent = _declared_parent(current.inheritance)
        if parent is None:
            return None
        current = index.get(resolve_entity_reference(current.identity, parent))
    return None


def _resolve_relationships(
    declaration: UnresolvedEntityDeclaration,
    index: Mapping[EntityIdentity, UnresolvedEntityDeclaration],
) -> tuple[tuple[RelationshipDeclaration, ...], list[MetamodelIssue]]:
    resolved: list[RelationshipDeclaration] = []
    issues: list[MetamodelIssue] = []
    for relationship in declaration.relationships:
        match relationship:
            case UnresolvedDefiningRelationshipDeclaration():
                declared, defining_issues = _resolve_defining(declaration, relationship, index)
            case UnresolvedReverseRelationshipDeclaration():
                declared, defining_issues = _resolve_reverse(declaration, relationship, index)
        issues.extend(defining_issues)
        if declared is not None:
            resolved.append(declared)
    return tuple(resolved), issues


def _resolve_defining(
    declaration: UnresolvedEntityDeclaration,
    relationship: UnresolvedDefiningRelationshipDeclaration,
    index: Mapping[EntityIdentity, UnresolvedEntityDeclaration],
) -> tuple[RelationshipDeclaration | None, list[MetamodelIssue]]:
    location = RelationshipLocation(relationship.identity)
    target_identity = resolve_entity_reference(
        declaration.identity, relationship.join.target.entity
    )
    target = index.get(target_identity)
    if target is None:
        return None, [_unresolved_entity(location, target_identity)]

    issues: list[MetamodelIssue] = []
    target_name = relationship.join.target.name
    if _applicable_attribute(target, target_name, index) is None:
        issues.append(
            _unresolved_attribute(location, AttributeIdentity(target_identity, target_name))
        )
    order_by: list[RelationshipOrder] = []
    for term in relationship.order_by:
        term_identity = AttributeIdentity(target_identity, term.attribute)
        if _applicable_attribute(target, term.attribute, index) is None:
            issues.append(_unresolved_attribute(location, term_identity))
            continue
        order_by.append(RelationshipOrder(term_identity, term.direction))
    if issues:
        return None, issues
    return (
        DefiningRelationshipDeclaration(
            identity=relationship.identity,
            cardinality=relationship.cardinality,
            join=RelationshipJoin(
                source=relationship.join.source,
                target=AttributeIdentity(target_identity, target_name),
            ),
            dependent=relationship.dependent,
            order_by=tuple(order_by),
        ),
        issues,
    )


def _resolve_reverse(
    declaration: UnresolvedEntityDeclaration,
    relationship: UnresolvedReverseRelationshipDeclaration,
    index: Mapping[EntityIdentity, UnresolvedEntityDeclaration],
) -> tuple[RelationshipDeclaration | None, list[MetamodelIssue]]:
    location = RelationshipLocation(relationship.identity)
    peer_entity = resolve_entity_reference(declaration.identity, relationship.reverse_of.entity)
    peer = index.get(peer_entity)
    if peer is None:
        return None, [_unresolved_entity(location, peer_entity)]

    peer_identity = RelationshipIdentity(peer_entity, relationship.reverse_of.name)
    if not any(declared.identity == peer_identity for declared in peer.relationships):
        return None, [
            MetamodelIssue(
                UNRESOLVED_RELATIONSHIP_REFERENCE,
                location,
                (RelationshipLocation(peer_identity),),
                message=(
                    f"Entity {peer_entity.canonical!r} declares no relationship "
                    f"{relationship.reverse_of.name!r}"
                ),
            )
        ]

    issues: list[MetamodelIssue] = []
    order_by: list[RelationshipOrder] = []
    for term in relationship.order_by:
        term_identity = AttributeIdentity(peer_entity, term.attribute)
        if _applicable_attribute(peer, term.attribute, index) is None:
            issues.append(_unresolved_attribute(location, term_identity))
            continue
        order_by.append(RelationshipOrder(term_identity, term.direction))
    if issues:
        return None, issues
    return (
        ReverseRelationshipDeclaration(
            identity=relationship.identity,
            reverse_of=peer_identity,
            order_by=tuple(order_by),
        ),
        issues,
    )


def _resolve_inheritance(
    declaration: UnresolvedEntityDeclaration,
    index: Mapping[EntityIdentity, UnresolvedEntityDeclaration],
) -> tuple[InheritanceMetadata | None, list[MetamodelIssue]]:
    inheritance = declaration.inheritance
    match inheritance:
        case None:
            return None, []
        case AbstractRoot():
            return inheritance, []
        case AbstractSubtype(parent):
            resolved, issues = _resolve_parent(declaration, parent, index)
            return (None if resolved is None else AbstractSubtype(resolved)), issues
        case ConcreteSubtype(parent, tag_value):
            resolved, issues = _resolve_parent(declaration, parent, index)
            return (None if resolved is None else ConcreteSubtype(resolved, tag_value)), issues


def _resolve_parent(
    declaration: UnresolvedEntityDeclaration,
    parent: EntityReference,
    index: Mapping[EntityIdentity, UnresolvedEntityDeclaration],
) -> tuple[EntityIdentity | None, list[MetamodelIssue]]:
    identity = resolve_entity_reference(declaration.identity, parent)
    if identity in index:
        return identity, []
    return None, [_unresolved_entity(EntityLocation(declaration.identity), identity)]


def _unresolved_entity(location: ModelLocation, target: EntityIdentity) -> MetamodelIssue:
    return MetamodelIssue(
        UNRESOLVED_ENTITY_REFERENCE,
        location,
        (EntityLocation(target),),
        message=f"no declaration resolves to Entity {target.canonical!r}",
    )


def _unresolved_attribute(location: ModelLocation, target: AttributeIdentity) -> MetamodelIssue:
    return MetamodelIssue(
        UNRESOLVED_ATTRIBUTE_REFERENCE,
        location,
        (AttributeLocation(target),),
        message=(f"Entity {target.entity.canonical!r} has no applicable Attribute {target.name!r}"),
    )
