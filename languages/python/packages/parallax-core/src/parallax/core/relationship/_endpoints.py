"""Candidate-position Attribute lookup and the join-endpoint projection.

Rule Sets run in unspecified order over one Candidate Metamodel, so a Rule Set
that needs relationship facts cannot consume the Relationship Facet. This module
owns the bounded fact those Rule Sets need — which Attributes an accepted
Relationship Join designates — and the position lookup both it and this module's
own Rule Set resolve endpoints through, so the projection and the rejections it
sidesteps can never disagree about what "resolves locally" means.
"""

from __future__ import annotations

from collections.abc import Mapping

from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    CandidateMetamodel,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    inheritance_parent,
)

__all__ = ["AttributePositions", "endpoint", "project_join_endpoints"]


class AttributePositions:
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


def endpoint(
    entity: EntityIdentity, attribute: AttributeIdentity, positions: AttributePositions
) -> AttributeMetadata | None:
    """The Attribute ``attribute`` denotes at ``entity``, or absence.

    An endpoint is addressed at one Entity, so an Identity naming a different
    Entity denotes nothing here however that Attribute is declared elsewhere.
    """
    if attribute.entity != entity:
        return None
    return positions.at(entity).get(attribute.name)


def project_join_endpoints(candidate: CandidateMetamodel) -> frozenset[AttributeIdentity]:
    """The join endpoint Attributes of ``candidate``'s defining declarations.

    Pure, total, and issue-free: it emits nothing, returns no partial or
    provisional value, and never rejects, so a consuming Rule Set's result does
    not depend on when it asks.

    An endpoint is addressed at the position that names it, which for an
    inherited Attribute is not the Entity declaring it. The projection returns
    the Identity the resolved Attribute bears, because that is the Identity
    accepted Attribute Metadata carries and the only one a consumer classifying
    a declaration can compare against.

    Only a defining declaration is read. A reverse declaration introduces no
    Attribute of its own — the compiler swaps the sides of the same join and
    inverts cardinality for it — so every Attribute any direction names is
    already named by some defining declaration, and the projection never depends
    on reverse resolution.

    Both endpoints of a join are returned together or not at all: an endpoint of
    a malformed join is not locally resolvable. Such a model is rejected by this
    module's own Rule Set, and a consumer that classified the excluded Attribute
    differently in the meantime has not changed that outcome.
    """
    positions = AttributePositions(candidate)
    endpoints: set[AttributeIdentity] = set()
    for declaration in candidate.entities:
        for relationship in declaration.relationships:
            if not isinstance(relationship, DefiningRelationshipDeclaration):
                continue
            join = relationship.join
            source = endpoint(declaration.identity, join.source, positions)
            target = endpoint(join.target.entity, join.target, positions)
            if source is None or target is None:
                continue
            endpoints.update((source.identity, target.identity))
    return frozenset(endpoints)
