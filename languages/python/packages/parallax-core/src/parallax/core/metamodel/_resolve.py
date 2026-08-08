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

import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, TypeGuard

from parallax.core.base import Timestamp
from parallax.core.metamodel._identities import (
    AttributeIdentity,
    EntityIdentity,
    EntityReference,
    IndexIdentity,
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
from parallax.core.metamodel._temporal_structure import CONVENTIONAL_TEMPORAL_NAMES
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
    StorageLayout,
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
    "INDEX_IDENTITY_DUPLICATE",
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
    "is_candidate_metamodel",
    "resolve",
]

# `identity.schema.json` `$defs/entityLocalName`, mirrored so a descriptor
# installed from native classes is legal exactly where the same descriptor
# authored as a document is.
_ENTITY_LOCAL_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")

INVALID_ENTITY_IDENTITY: Final[IssueCode] = "metamodel-invalid-entity-identity"
"""An Entity name is empty, carries a dot, or does not begin capitalized. The
namespace half of the grammar is unconstructible, so only the name can reach
resolution malformed."""

DUPLICATE_ENTITY_IDENTITY: Final[IssueCode] = "metamodel-duplicate-entity-identity"
"""Two or more declarations resolve to one Entity Identity. Duplicates are legal
frontend input, so this is reported once per identity, not once per extra
declaration, and every other check still runs over every declaration."""

UNRESOLVED_ENTITY_REFERENCE: Final[IssueCode] = "metamodel-unresolved-entity-reference"
"""A relationship target, reverse peer owner, or inheritance parent names an
Entity no declaration bears. The lexical rule alone decides the Identity: there
is no global unique-name fallback that could rescue the reference."""

UNRESOLVED_ATTRIBUTE_REFERENCE: Final[IssueCode] = "metamodel-unresolved-attribute-reference"
"""A join target or ordering term names an Attribute its Entity does not declare
and does not inherit. Its Entity resolved; only the member did not."""

UNRESOLVED_RELATIONSHIP_REFERENCE: Final[IssueCode] = "metamodel-unresolved-relationship-reference"
"""A reverse declaration names a relationship its peer Entity does not declare.
Whether the named peer is actually a defining declaration is
``m-relationship``'s rule, not this one."""

LOCAL_MEMBER_COLLISION: Final[IssueCode] = "metamodel-local-member-collision"
"""Two local members share a name in one navigable namespace: Attributes,
relationships, and top-level Value Object occurrences share an Entity's, and
scalars and nested occurrences share one shape's. Shadowing an inherited member
is ``m-inheritance``'s rule."""

TEMPORAL_MEMBER_RESERVED: Final[IssueCode] = "metamodel-temporal-member-reserved"
"""A member that is not the axis's own endpoint bears a conventional temporal
name the Entity's declared dimensions reserve. Reservation follows the declared
axes, so the same name is free on a non-temporal Entity."""

PRIMARY_KEY_MISSING: Final[IssueCode] = "metamodel-primary-key-missing"
"""A standalone Entity declares no primary-key Attribute. An inheritance
participant's key is family-wide and root-owned, so ``m-inheritance`` reports
its equivalent."""

PRIMARY_KEY_MULTIPLE: Final[IssueCode] = "metamodel-primary-key-multiple"
"""A standalone Entity declares more than one primary-key Attribute. Composite
keys are not part of the contract, so this is a defect rather than a shape."""

INDEX_IDENTITY_DUPLICATE: Final[IssueCode] = "metamodel-index-identity-duplicate"
"""Two Indices of one Entity bear one name, so ``EntityMetadata.index`` has no
single answer for it. Identity alone decides: a frontend hands a derived Index
over as an ordinary one, so it claims its name like any other, and components
neither cause nor excuse the collision."""

INDEX_EMPTY: Final[IssueCode] = "metamodel-index-empty"
"""An Index declares no Attribute component."""

INDEX_ATTRIBUTE_MISSING: Final[IssueCode] = "metamodel-index-attribute-missing"
"""An Index component names an Attribute of its own Entity that nothing in the
Entity's ancestry declares either."""

INDEX_ATTRIBUTE_NOT_LOCAL: Final[IssueCode] = "metamodel-index-attribute-not-local"
"""An Index component exists but is not local: it belongs to another Entity, or
it is inherited rather than declared here. A component that exists nowhere is
``metamodel-index-attribute-missing`` instead."""

INDEX_ATTRIBUTE_DUPLICATE: Final[IssueCode] = "metamodel-index-attribute-duplicate"
"""One Attribute occurs more than once among an Index's components."""

AS_OF_DIMENSION_DUPLICATE: Final[IssueCode] = "metamodel-as-of-dimension-duplicate"
"""One Entity declares the same Temporal Dimension on more than one axis."""

AS_OF_ATTRIBUTE_MISSING: Final[IssueCode] = "metamodel-as-of-attribute-missing"
"""An axis endpoint names an Attribute of its own Entity that the Entity does
not declare. Axis endpoints are local-only, so ancestry is not consulted."""

AS_OF_ATTRIBUTE_OWNER: Final[IssueCode] = "metamodel-as-of-attribute-owner"
"""An axis endpoint names an Attribute of another Entity. Ownership is checked
before existence, so a foreign endpoint never reports as missing."""

AS_OF_ATTRIBUTE_TYPE: Final[IssueCode] = "metamodel-as-of-attribute-type"
"""An axis endpoint exists and is local but is not a Timestamp."""

AS_OF_ATTRIBUTE_DUPLICATE: Final[IssueCode] = "metamodel-as-of-attribute-duplicate"
"""One axis names the same Attribute as both its start and its end. Two axes
sharing an endpoint is not this code; each axis is judged alone."""

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
        INDEX_IDENTITY_DUPLICATE,
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


@dataclass(frozen=True, slots=True)
class _EntityDeclaration:
    identity: EntityIdentity
    container: StorageContainer | None
    persistence: PersistenceMode | None
    layout: StorageLayout | None
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
            self,
            "_by_identity",
            MappingProxyType({entity.identity: entity for entity in self.entities}),
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


def is_candidate_metamodel(value: object) -> TypeGuard[CandidateMetamodel]:
    """Whether ``value`` is a Candidate Metamodel this resolver produced.

    Resolution is fixed and is the sole source of the state semantic Rule Sets
    validate, so provenance decides: a value that merely presents the surface
    came from somewhere else, and :class:`Resolved` is a plain carrier that
    cannot vouch for what a defective resolver seated in it. A candidate is also
    nonempty, because the frontend source formation begins from is.

    Exists for the seam that receives a resolution result and must classify a
    wrong-typed one as a contract failure rather than let it reach a Rule Set.
    """
    return isinstance(value, _CandidateMetamodel) and bool(value.entities)


def resolve(unresolved: UnresolvedMetamodel) -> ResolutionResult:
    """Resolve ``unresolved`` into a Candidate Metamodel or every issue blocking it.

    Aggregating: the result names every foundational defect in the model, not
    the first one found, and names each of them once — a legal model can make
    one defect reachable from several duplicate declarations or from a component
    repeated within one declaration, and each such defect is reported where it
    is discovered. Resolution never partially succeeds — a rejected model yields
    no candidate at all.
    """
    declarations = tuple(unresolved.entities)
    issues: list[MetamodelIssue] = []
    index: dict[EntityIdentity, list[UnresolvedEntityDeclaration]] = {}
    for declaration in declarations:
        identity = declaration.identity
        bearers = index.setdefault(identity, [])
        # An Identity's grammar is a property of the Identity, and duplication is
        # a property of the set of declarations bearing it, so each is judged
        # once for the Identity rather than once per bearer.
        if not bearers and not _well_formed_entity_name(identity.name):
            issues.append(
                MetamodelIssue(
                    INVALID_ENTITY_IDENTITY,
                    EntityLocation(identity),
                    message=(f"Entity name {identity.name!r} is not a capitalized dot-free name"),
                )
            )
        if len(bearers) == 1:
            issues.append(
                MetamodelIssue(
                    DUPLICATE_ENTITY_IDENTITY,
                    EntityLocation(identity),
                    message=f"two declarations resolve to Entity {identity.canonical!r}",
                )
            )
        bearers.append(declaration)

    entities: list[EntityDeclaration] = []
    # Duplicate Identities are legal input, so one Entity's defect is reachable
    # from every declaration bearing its Identity. Such a defect is reported for
    # the Identity, not once per bearer; a repetition from any other source stays
    # in the result, where the formation seam holds this emitter to distinct
    # issue identities like any other.
    reached: dict[EntityIdentity, set[MetamodelIssue]] = {}
    for declaration in declarations:
        declared: list[MetamodelIssue] = []
        declared.extend(_collision_issues(declaration))
        declared.extend(_temporal_reservation_issues(declaration))
        declared.extend(_primary_key_issues(declaration))
        declared.extend(_index_issues(declaration, index))
        declared.extend(_axis_issues(declaration))
        relationships, relationship_issues = _resolve_relationships(declaration, index)
        inheritance, inheritance_issues = _resolve_inheritance(declaration, index)
        declared.extend(relationship_issues)
        declared.extend(inheritance_issues)
        sibling = reached.setdefault(declaration.identity, set())
        issues.extend(issue for issue in declared if issue not in sibling)
        sibling.update(declared)
        entities.append(
            _EntityDeclaration(
                identity=declaration.identity,
                container=declaration.container,
                persistence=declaration.persistence,
                layout=declaration.layout,
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
    """An Entity's local name is dot-free and begins capitalized.

    The capitalization is what makes the Entity segment of a dotted reference
    identifiable without consulting a model, so it is the same rule the
    serialized grammars enforce (``identity.schema.json``) rather than a
    convention the accepted-model path could hold independently.
    """
    return _ENTITY_LOCAL_NAME.match(name) is not None


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
    """The colliding positions among ``positions``, each named once.

    Two members of one category that share a name also share a Model Location,
    so a name declared three times over collides at one position rather than at
    two; the collision is reported for the position, not for each repetition.
    """
    issues: list[MetamodelIssue] = []
    first: dict[str, ModelLocation] = {}
    colliding: set[ModelLocation] = set()
    for name, location in positions:
        declared = first.get(name)
        if declared is None:
            first[name] = location
            continue
        if location in colliding:
            continue
        colliding.add(location)
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
    """The members bearing a name this Entity's temporal shape reserves.

    Members repeating one name share a Model Location, so the reservation is
    reported for the position rather than for each repetition.
    """
    reserved: dict[str, TemporalDimension] = {}
    framework: set[AttributeIdentity] = set()
    for axis in declaration.as_of_axes:
        for name in CONVENTIONAL_TEMPORAL_NAMES[axis.dimension]:
            reserved[name] = axis.dimension
        framework.add(axis.start_attribute)
        framework.add(axis.end_attribute)
    if not reserved:
        return []

    issues: list[MetamodelIssue] = []
    rejected: set[ModelLocation] = set()

    def reject(name: str, location: ModelLocation) -> None:
        dimension = reserved.get(name)
        if dimension is None or location in rejected:
            return
        rejected.add(location)
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
    index: Mapping[EntityIdentity, Sequence[UnresolvedEntityDeclaration]],
) -> list[MetamodelIssue]:
    """The Index defects of one declaration, each position and component judged once.

    An Index position is one name of one Entity, so every Index bearing that
    name shares a Model Location: bearing it twice is one repetition defect, and
    a component defect two such Indices both carry is one defect reached twice.
    A component occurring several times in one Index is likewise one repetition
    defect and one component, so the repetition is reported when it is first
    observed and the component's locality is judged on its first occurrence
    alone.
    """
    local = {attribute.identity.name for attribute in declaration.attributes}
    issues: list[MetamodelIssue] = []
    names: Counter[IndexIdentity] = Counter()
    reached: dict[IndexIdentity, set[MetamodelIssue]] = {}
    for declared_index in declaration.indices:
        identity = declared_index.identity
        location = IndexLocation(identity)
        names[identity] += 1
        if names[identity] == 2:
            issues.append(
                MetamodelIssue(
                    INDEX_IDENTITY_DUPLICATE,
                    location,
                    message=f"two Indices of this Entity bear the name {identity.name!r}",
                )
            )
        declared_issues: list[MetamodelIssue] = []
        if not declared_index.attributes:
            declared_issues.append(
                MetamodelIssue(
                    INDEX_EMPTY, location, message="an Index declares at least one Attribute"
                )
            )
        occurrences: Counter[AttributeIdentity] = Counter()
        for component in declared_index.attributes:
            related = (AttributeLocation(component),)
            occurrences[component] += 1
            if occurrences[component] == 2:
                declared_issues.append(
                    MetamodelIssue(
                        INDEX_ATTRIBUTE_DUPLICATE,
                        location,
                        related,
                        message=f"Attribute {component.name!r} occurs more than once in the Index",
                    )
                )
            if occurrences[component] > 1:
                continue
            if component.entity != declaration.identity:
                declared_issues.append(
                    MetamodelIssue(
                        INDEX_ATTRIBUTE_NOT_LOCAL,
                        location,
                        related,
                        message="an Index component belongs to another Entity",
                    )
                )
            elif component.name not in local:
                inherited = _applicable_attribute((declaration,), component.name, index)
                declared_issues.append(
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
        position = reached.setdefault(identity, set())
        issues.extend(issue for issue in declared_issues if issue not in position)
        position.update(declared_issues)
    return issues


def _axis_issues(declaration: UnresolvedEntityDeclaration) -> list[MetamodelIssue]:
    """The As-Of Axis defects of one declaration, each position judged once.

    An axis position is one Temporal Dimension of one Entity, so every axis
    declaring one dimension shares a Model Location: declaring the dimension
    twice is one repetition defect, and an endpoint defect two such axes both
    carry is one defect reached twice. An axis whose start and end name one
    Attribute likewise has a single endpoint to judge.
    """
    local = {attribute.identity.name: attribute for attribute in declaration.attributes}
    issues: list[MetamodelIssue] = []
    dimensions: Counter[TemporalDimension] = Counter()
    reached: dict[TemporalDimension, set[MetamodelIssue]] = {}
    for axis in declaration.as_of_axes:
        location = AsOfAxisLocation(declaration.identity, axis.dimension)
        dimensions[axis.dimension] += 1
        if dimensions[axis.dimension] == 2:
            issues.append(
                MetamodelIssue(
                    AS_OF_DIMENSION_DUPLICATE,
                    location,
                    message="one Temporal Dimension is declared more than once",
                )
            )
        declared: list[MetamodelIssue] = []
        if axis.start_attribute == axis.end_attribute:
            declared.append(
                MetamodelIssue(
                    AS_OF_ATTRIBUTE_DUPLICATE,
                    location,
                    (AttributeLocation(axis.start_attribute),),
                    message="an axis start and end identify the same Attribute",
                )
            )
        for endpoint in dict.fromkeys((axis.start_attribute, axis.end_attribute)):
            declared.extend(_axis_endpoint_issues(declaration.identity, location, endpoint, local))
        position = reached.setdefault(axis.dimension, set())
        issues.extend(issue for issue in declared if issue not in position)
        position.update(declared)
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
    positions: Iterable[UnresolvedEntityDeclaration],
    name: str,
    index: Mapping[EntityIdentity, Sequence[UnresolvedEntityDeclaration]],
) -> bool:
    """Whether ``name`` denotes an Attribute applicable at any of ``positions``.

    A declared inheritance parent extends a position's Attribute set, so a
    reference into a family member is satisfied by the ancestry chain as well as
    by the local declarations. Duplicate identities are legal input, so every
    declaration bearing an ancestor's Identity is consulted and the answer never
    depends on which one a frontend enumerated first. The walk is purely
    structural over the parent links the declarations already carry and stops on
    a cycle; family coherence is ``m-inheritance``'s rule.
    """
    pending = list(positions)
    expanded: set[EntityIdentity] = set()
    while pending:
        current = pending.pop()
        if any(attribute.identity.name == name for attribute in current.attributes):
            return True
        parent = _declared_parent(current.inheritance)
        if parent is None:
            continue
        ancestor = resolve_entity_reference(current.identity, parent)
        if ancestor in expanded:
            continue
        expanded.add(ancestor)
        pending.extend(index.get(ancestor, ()))
    return False


def _resolve_relationships(
    declaration: UnresolvedEntityDeclaration,
    index: Mapping[EntityIdentity, Sequence[UnresolvedEntityDeclaration]],
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


def _unresolvable_attribute(
    location: ModelLocation,
    entity: EntityIdentity,
    bearers: Sequence[UnresolvedEntityDeclaration],
    index: Mapping[EntityIdentity, Sequence[UnresolvedEntityDeclaration]],
    issues: list[MetamodelIssue],
) -> Callable[[str], bool]:
    """A predicate over ``entity``'s Attribute names that records each miss once.

    One relationship reaches one Attribute of the far Entity from its join
    target and from every ordering term, so a name that resolves nowhere is one
    unresolved reference however many of those reached it. The predicate appends
    that reference to ``issues`` the first time it answers true for a name.
    """
    reported: set[AttributeIdentity] = set()

    def unresolvable(name: str) -> bool:
        if _applicable_attribute(bearers, name, index):
            return False
        target = AttributeIdentity(entity, name)
        if target not in reported:
            reported.add(target)
            issues.append(_unresolved_attribute(location, target))
        return True

    return unresolvable


def _resolve_defining(
    declaration: UnresolvedEntityDeclaration,
    relationship: UnresolvedDefiningRelationshipDeclaration,
    index: Mapping[EntityIdentity, Sequence[UnresolvedEntityDeclaration]],
) -> tuple[RelationshipDeclaration | None, list[MetamodelIssue]]:
    location = RelationshipLocation(relationship.identity)
    target_identity = resolve_entity_reference(
        declaration.identity, relationship.join.target.entity
    )
    target = index.get(target_identity, ())
    if not target:
        return None, [_unresolved_entity(location, target_identity)]

    issues: list[MetamodelIssue] = []
    unresolvable = _unresolvable_attribute(location, target_identity, target, index, issues)
    target_name = relationship.join.target.name
    unresolvable(target_name)
    order_by: list[RelationshipOrder] = []
    for term in relationship.order_by:
        if unresolvable(term.attribute):
            continue
        order_by.append(
            RelationshipOrder(
                AttributeIdentity(target_identity, term.attribute), term.direction, term.nulls
            )
        )
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
    index: Mapping[EntityIdentity, Sequence[UnresolvedEntityDeclaration]],
) -> tuple[RelationshipDeclaration | None, list[MetamodelIssue]]:
    location = RelationshipLocation(relationship.identity)
    peer_entity = resolve_entity_reference(declaration.identity, relationship.reverse_of.entity)
    peer = index.get(peer_entity, ())
    if not peer:
        return None, [_unresolved_entity(location, peer_entity)]

    peer_identity = RelationshipIdentity(peer_entity, relationship.reverse_of.name)
    if not any(
        declared.identity == peer_identity for bearer in peer for declared in bearer.relationships
    ):
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
    unresolvable = _unresolvable_attribute(location, peer_entity, peer, index, issues)
    order_by: list[RelationshipOrder] = []
    for term in relationship.order_by:
        if unresolvable(term.attribute):
            continue
        order_by.append(
            RelationshipOrder(
                AttributeIdentity(peer_entity, term.attribute), term.direction, term.nulls
            )
        )
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
    index: Mapping[EntityIdentity, Sequence[UnresolvedEntityDeclaration]],
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
    index: Mapping[EntityIdentity, Sequence[UnresolvedEntityDeclaration]],
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
