"""The relationship Model Formation Rule Set (m-relationship).

Everything this module rejects is a statement about one association: whether its
join reaches the Attributes it names, whether the declared cardinality is
something the join can deliver, whether a reverse declaration names a defining
peer that points back at it, whether one association is claimed twice, and
whether an ordering belongs to the direction that declares it. Reference absence
is not here — foundational resolution owns it, so a candidate's references
already name existing positions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeLocation,
    AttributeMetadata,
    CandidateMetamodel,
    Cardinality,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    IssueCode,
    MetamodelIssue,
    Multiplicity,
    PrimaryKey,
    RelationshipDeclaration,
    RelationshipIdentity,
    RelationshipLocation,
    RelationshipOrder,
    ReverseRelationshipDeclaration,
    inheritance_parent,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.relationship._facet import RELATIONSHIP_MODULE

__all__ = [
    "CARDINALITY_JOIN_MISMATCH",
    "DEFINING_DUPLICATE",
    "ISSUE_CODES",
    "JOIN_SOURCE_INVALID",
    "JOIN_TARGET_INVALID",
    "ORDER_ATTRIBUTE_INVALID",
    "ORDER_ON_TO_ONE",
    "REVERSE_CYCLE",
    "REVERSE_INCONSISTENT",
    "REVERSE_NOT_DEFINING",
    "RULE_SET",
    "RelationshipRuleSet",
]

JOIN_SOURCE_INVALID: Final[IssueCode] = "relationship-join-source-invalid"
"""A defining join's source names no Attribute of the declaring Entity, either
because it is addressed at another Entity or because neither the Entity nor its
ancestry declares it."""

JOIN_TARGET_INVALID: Final[IssueCode] = "relationship-join-target-invalid"
"""A defining join's target names no Attribute of the Entity its own reference
established. The target Entity is that Identity's Entity component, so this is
about the member alone."""

CARDINALITY_JOIN_MISMATCH: Final[IssueCode] = "relationship-cardinality-join-mismatch"
"""Neither side the cardinality declares to be One is joined on its Entity's
primary key, so the join cannot identify the single row that side promises."""

REVERSE_CYCLE: Final[IssueCode] = "relationship-reverse-cycle"
"""Following a reverse declaration's peers reaches no defining declaration
because the chain closes on itself, directly or through other reverses."""

REVERSE_NOT_DEFINING: Final[IssueCode] = "relationship-reverse-not-defining"
"""A reverse declaration names a declaration that is not a defining one. A
reverse derives its mapping facts from its peer, so naming a peer that owns none
leaves it with nothing to derive."""

REVERSE_INCONSISTENT: Final[IssueCode] = "relationship-reverse-inconsistent"
"""A reverse declaration's Entity is not the one its defining peer targets, so
the two declarations describe different associations rather than two directions
of one."""

DEFINING_DUPLICATE: Final[IssueCode] = "relationship-defining-duplicate"
"""More than one reverse declaration claims one defining declaration as the
association it reverses, so that association is bidirectional twice over."""

ORDER_ON_TO_ONE: Final[IssueCode] = "relationship-order-on-to-one"
"""Ordering is declared for a direction whose target Multiplicity is One. A
direction reaching at most one Entity has nothing to order."""

ORDER_ATTRIBUTE_INVALID: Final[IssueCode] = "relationship-order-attribute-invalid"
"""An ordering term names no Attribute of the direction's target Entity. A term
orders the Entities the direction reaches, so its scope is that target."""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset(
    {
        JOIN_SOURCE_INVALID,
        JOIN_TARGET_INVALID,
        CARDINALITY_JOIN_MISMATCH,
        REVERSE_CYCLE,
        REVERSE_NOT_DEFINING,
        REVERSE_INCONSISTENT,
        DEFINING_DUPLICATE,
        ORDER_ON_TO_ONE,
        ORDER_ATTRIBUTE_INVALID,
    }
)
"""This module's complete owned Issue Code set, as the Formation Manifest
declares it."""


class _Attributes:
    """Attribute lookup by local name at a candidate position, ancestry included.

    A declared inheritance parent extends a position's Attribute set, so a join
    endpoint or ordering term may name an Attribute an ancestor declares. The
    walk is purely structural over the parent links the candidate carries and
    stops on a cycle; family coherence is ``m-inheritance``'s rule. Each position
    is collected once, so repeated lookups over one candidate stay cheap.
    """

    __slots__ = ("_candidate", "_positions")

    _candidate: CandidateMetamodel
    _positions: dict[EntityIdentity, Mapping[str, AttributeMetadata]]

    def __init__(self, candidate: CandidateMetamodel) -> None:
        self._candidate = candidate
        self._positions = {}

    def at(self, entity: EntityIdentity) -> Mapping[str, AttributeMetadata]:
        """Every Attribute applicable at ``entity``, keyed by local name."""
        collected = self._positions.get(entity)
        if collected is None:
            collected = self._collect(entity)
            self._positions[entity] = collected
        return collected

    def _collect(self, entity: EntityIdentity) -> Mapping[str, AttributeMetadata]:
        collected: dict[str, AttributeMetadata] = {}
        visited: set[EntityIdentity] = set()
        position = self._candidate.entity(entity)
        while position is not None and position.identity not in visited:
            visited.add(position.identity)
            for attribute in position.attributes:
                collected.setdefault(attribute.identity.name, attribute)
            parent = inheritance_parent(position.inheritance)
            position = None if parent is None else self._candidate.entity(parent)
        return collected


def _endpoint(
    entity: EntityIdentity, attribute: AttributeIdentity, attributes: _Attributes
) -> AttributeMetadata | None:
    """The Attribute ``attribute`` denotes at ``entity``, or absence.

    An endpoint is addressed at one Entity, so an Identity naming a different
    Entity denotes nothing here however that Attribute is declared elsewhere.
    """
    if attribute.entity != entity:
        return None
    return attributes.at(entity).get(attribute.name)


def _identifies_a_one_side(
    cardinality: Cardinality, source: AttributeMetadata, target: AttributeMetadata
) -> bool:
    """Whether the join identifies a single row on a side the cardinality calls One.

    Every cardinality has at least one One side, and the model fact that
    identifies a single row is the primary key. A One side joined on a non-key
    Attribute is identified only by a physical uniqueness constraint, which the
    model does not state, so at least one One side must be the key side.
    """
    if cardinality.source is Multiplicity.ONE and isinstance(source.primary_key, PrimaryKey):
        return True
    return cardinality.target is Multiplicity.ONE and isinstance(target.primary_key, PrimaryKey)


def _order_issues(
    location: RelationshipLocation,
    order_by: Sequence[RelationshipOrder],
    target: EntityIdentity,
    attributes: _Attributes,
) -> list[MetamodelIssue]:
    """The ordering terms of one direction that name no Attribute of its target.

    Several terms may name one unreachable Attribute, and that is one defect
    about one Attribute, so each is reported once.
    """
    issues: list[MetamodelIssue] = []
    reported: set[AttributeIdentity] = set()
    for term in order_by:
        if _endpoint(target, term.attribute, attributes) is not None:
            continue
        if term.attribute in reported:
            continue
        reported.add(term.attribute)
        issues.append(
            MetamodelIssue(
                ORDER_ATTRIBUTE_INVALID,
                location,
                (AttributeLocation(term.attribute),),
                message=(
                    f"ordering term {term.attribute.name!r} names no Attribute of "
                    f"{target.canonical!r}"
                ),
            )
        )
    return issues


def _defining_issues(
    owner: EntityIdentity,
    declaration: DefiningRelationshipDeclaration,
    attributes: _Attributes,
) -> list[MetamodelIssue]:
    """The defects of one defining declaration, which owns every mapping fact."""
    location = RelationshipLocation(declaration.identity)
    join = declaration.join
    issues: list[MetamodelIssue] = []
    source = _endpoint(owner, join.source, attributes)
    if source is None:
        issues.append(
            MetamodelIssue(
                JOIN_SOURCE_INVALID,
                location,
                (AttributeLocation(join.source),),
                message=f"the join source names no Attribute of {owner.canonical!r}",
            )
        )
    target = _endpoint(join.target.entity, join.target, attributes)
    if target is None:
        issues.append(
            MetamodelIssue(
                JOIN_TARGET_INVALID,
                location,
                (AttributeLocation(join.target),),
                message=(f"the join target names no Attribute of {join.target.entity.canonical!r}"),
            )
        )
    if (
        source is not None
        and target is not None
        and not _identifies_a_one_side(declaration.cardinality, source, target)
    ):
        issues.append(
            MetamodelIssue(
                CARDINALITY_JOIN_MISMATCH,
                location,
                (AttributeLocation(join.source), AttributeLocation(join.target)),
                message="no side declared One is joined on its Entity's primary key",
            )
        )
    issues.extend(_order_issues(location, declaration.order_by, join.target.entity, attributes))
    if declaration.cardinality.target is Multiplicity.ONE and declaration.order_by:
        issues.append(
            MetamodelIssue(
                ORDER_ON_TO_ONE,
                location,
                message="a direction whose target Multiplicity is One declares an ordering",
            )
        )
    return issues


def _closes_a_cycle(
    start: ReverseRelationshipDeclaration,
    declarations: Mapping[RelationshipIdentity, RelationshipDeclaration],
) -> bool:
    """Whether following ``start``'s peers revisits a declaration.

    A chain of reverse declarations is finite, so it either reaches a defining
    declaration or closes on itself; only the second is a cycle.
    """
    visited = {start.identity}
    current = declarations.get(start.reverse_of)
    while isinstance(current, ReverseRelationshipDeclaration):
        if current.identity in visited:
            return True
        visited.add(current.identity)
        current = declarations.get(current.reverse_of)
    return False


def _reverse_issues(
    owner: EntityIdentity,
    declaration: ReverseRelationshipDeclaration,
    declarations: Mapping[RelationshipIdentity, RelationshipDeclaration],
    attributes: _Attributes,
) -> list[MetamodelIssue]:
    """The defects of one reverse declaration, which derives from its peer."""
    location = RelationshipLocation(declaration.identity)
    related = (RelationshipLocation(declaration.reverse_of),)
    peer = declarations.get(declaration.reverse_of)
    if not isinstance(peer, DefiningRelationshipDeclaration):
        if _closes_a_cycle(declaration, declarations):
            return [
                MetamodelIssue(
                    REVERSE_CYCLE,
                    location,
                    related,
                    message="the chain of reverse declarations reaches no defining declaration",
                )
            ]
        return [
            MetamodelIssue(
                REVERSE_NOT_DEFINING,
                location,
                related,
                message="the named declaration owns no join to derive this direction from",
            )
        ]

    issues: list[MetamodelIssue] = []
    if peer.join.target.entity != owner:
        issues.append(
            MetamodelIssue(
                REVERSE_INCONSISTENT,
                location,
                related,
                message=(
                    f"the defining declaration targets "
                    f"{peer.join.target.entity.canonical!r}, not {owner.canonical!r}"
                ),
            )
        )
    target = peer.identity.source_entity
    issues.extend(_order_issues(location, declaration.order_by, target, attributes))
    # Inversion exchanges the sides, so this direction's target Multiplicity is
    # the defining direction's source Multiplicity.
    if peer.cardinality.source is Multiplicity.ONE and declaration.order_by:
        issues.append(
            MetamodelIssue(
                ORDER_ON_TO_ONE,
                location,
                message="a direction whose target Multiplicity is One declares an ordering",
            )
        )
    return issues


def _declaration_key(identity: RelationshipIdentity) -> tuple[str, str, str]:
    namespace, name = identity.source_entity.sort_key
    return (namespace, name, identity.name)


def _duplicate_claim_issues(candidate: CandidateMetamodel) -> list[MetamodelIssue]:
    """The defining declarations more than one reverse declaration claims.

    A defining declaration owns one association's mapping facts, and a reverse
    declaration turns that association bidirectional by naming it. That claim is
    exclusive: a second reverse would derive the same direction under a second
    name and leave the defining direction with two peers to report. Several
    defining declarations may join one Attribute pair — they are distinct
    associations that happen to share a foreign key, each free to order its own
    direction — so the defining side carries no such exclusivity.
    """
    claimants: dict[RelationshipIdentity, list[RelationshipIdentity]] = {}
    for entity in candidate.entities:
        for declaration in entity.relationships:
            if isinstance(declaration, ReverseRelationshipDeclaration):
                claimants.setdefault(declaration.reverse_of, []).append(declaration.identity)
    issues: list[MetamodelIssue] = []
    for claiming in claimants.values():
        if len(claiming) < 2:
            continue
        first, *extras = sorted(claiming, key=_declaration_key)
        issues.extend(
            MetamodelIssue(
                DEFINING_DUPLICATE,
                RelationshipLocation(extra),
                (RelationshipLocation(first),),
                message="another reverse declaration already claims this association",
            )
            for extra in extras
        )
    return issues


def validate_relationships(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Every relationship defect of ``candidate``, reported rather than the first."""
    attributes = _Attributes(candidate)
    declarations: dict[RelationshipIdentity, RelationshipDeclaration] = {
        declaration.identity: declaration
        for entity in candidate.entities
        for declaration in entity.relationships
    }
    issues: list[MetamodelIssue] = []
    for entity in candidate.entities:
        for declaration in entity.relationships:
            match declaration:
                case DefiningRelationshipDeclaration():
                    issues.extend(_defining_issues(entity.identity, declaration, attributes))
                case ReverseRelationshipDeclaration():
                    issues.extend(
                        _reverse_issues(entity.identity, declaration, declarations, attributes)
                    )
    issues.extend(_duplicate_claim_issues(candidate))
    return tuple(issues)


class RelationshipRuleSet:
    """This module's Model Formation Rule Set: issues only, never a facet."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this Rule Set and its Issue Codes."""
        return RELATIONSHIP_MODULE

    @property
    def issue_codes(self) -> frozenset[IssueCode]:
        """The complete owned code set every emission is held to."""
        return ISSUE_CODES

    def validate(self, candidate: CandidateMetamodel) -> Sequence[MetamodelIssue]:
        """Report every relationship defect ``candidate`` carries."""
        return validate_relationships(candidate)


RULE_SET: Final[RelationshipRuleSet] = RelationshipRuleSet()
"""The single Rule Set instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the Rule Set rather than constructing a second one."""
