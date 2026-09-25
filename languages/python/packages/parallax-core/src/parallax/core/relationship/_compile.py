from __future__ import annotations

import heapq
from collections.abc import Mapping, Sequence
from typing import Any, Final

from parallax.core.metamodel import (
    Cardinality,
    CompiledMetadata,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    FacetKey,
    RelationshipIdentity,
    RelationshipJoin,
    ReverseRelationshipDeclaration,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.relationship._facet import (
    FACET_KEY,
    RELATIONSHIP_MODULE,
    EntityRelationships,
    RelationshipFacet,
    RelationshipMetadata,
    inverted,
    relationship_facet,
)

__all__ = ["MODEL_COMPILER"]


def compile_facet(metadata: CompiledMetadata) -> RelationshipFacet:
    """Compile every accepted declaration of ``metadata`` into one directional
    value, and every Entity into its referential rank."""
    position = {entity.identity: index for index, entity in enumerate(metadata.entities)}
    defining: dict[RelationshipIdentity, DefiningRelationshipDeclaration] = {}
    reverse_of: dict[RelationshipIdentity, RelationshipIdentity] = {}
    # Only a defining declaration contributes a foreign-key edge: a reverse one
    # denotes the same association, and a one-to-one's cardinality does not say
    # which side holds the key.
    dependents: list[list[int]] = [[] for _ in metadata.entities]
    for index, entity in enumerate(metadata.entities):
        for declaration in entity.declared_relationships:
            match declaration:
                case DefiningRelationshipDeclaration():
                    defining[declaration.identity] = declaration
                    target = position[declaration.join.target.entity]
                    if declaration.cardinality is Cardinality.MANY_TO_ONE:
                        dependents[target].append(index)
                    elif declaration.cardinality is Cardinality.ONE_TO_MANY:
                        dependents[index].append(target)
                case ReverseRelationshipDeclaration():
                    reverse_of[declaration.reverse_of] = declaration.identity
    ranks = _referential_ranks(dependents)

    by_entity: dict[EntityIdentity, EntityRelationships] = {}
    for index, entity in enumerate(metadata.entities):
        directions: list[RelationshipMetadata] = []
        for declaration in entity.declared_relationships:
            match declaration:
                case DefiningRelationshipDeclaration():
                    peer = reverse_of.get(declaration.identity)
                    directions.append(
                        RelationshipMetadata(
                            identity=declaration.identity,
                            cardinality=declaration.cardinality,
                            join=declaration.join,
                            reverse=None if peer is None else peer.name,
                            dependent=declaration.dependent,
                            order_by=declaration.order_by,
                        )
                    )
                case ReverseRelationshipDeclaration():
                    directions.append(_reverse_direction(declaration, defining))
        by_entity[entity.identity] = EntityRelationships(tuple(directions), ranks[index])
    return relationship_facet(by_entity)


def _referential_ranks(dependents: Sequence[Sequence[int]]) -> list[int]:
    """Each canonical Entity position's referential rank.

    ``dependents[p]`` lists the positions holding a foreign key to ``p``, once per
    edge. Among the Entities whose prerequisites are all ranked, the earliest in
    canonical order ranks next. An Entity on a referential cycle, a
    self-reference included, never becomes ready, so once none is, every Entity
    still unranked follows in canonical order.
    """
    waiting = [0] * len(dependents)
    for held in dependents:
        for dependent in held:
            waiting[dependent] += 1
    ready = [index for index, count in enumerate(waiting) if count == 0]
    ranks = [-1] * len(dependents)
    rank = 0
    while ready:
        index = heapq.heappop(ready)
        ranks[index] = rank
        rank += 1
        for dependent in dependents[index]:
            waiting[dependent] -= 1
            if waiting[dependent] == 0:
                heapq.heappush(ready, dependent)
    for index, assigned in enumerate(ranks):
        if assigned < 0:
            ranks[index] = rank
            rank += 1
    return ranks


def _reverse_direction(
    declaration: ReverseRelationshipDeclaration,
    defining: Mapping[RelationshipIdentity, DefiningRelationshipDeclaration],
) -> RelationshipMetadata:
    """The direction a reverse declaration names, derived from its defining peer.

    The peer owns every mapping fact, so the derivation is mechanical: the join
    sides exchange places, the cardinality inverts, and dependency carries over.
    Only the ordering is the reverse declaration's own, because it orders the
    Entities this direction reaches rather than the ones the peer reaches.
    """
    peer = defining.get(declaration.reverse_of)
    if peer is None:
        raise RuntimeError(
            f"relationship {declaration.identity.source_entity.canonical}."
            f"{declaration.identity.name} reverses "
            f"{declaration.reverse_of.source_entity.canonical}.{declaration.reverse_of.name}, "
            "which validation should have established as a defining declaration"
        )
    return RelationshipMetadata(
        identity=declaration.identity,
        cardinality=inverted(peer.cardinality),
        join=RelationshipJoin(source=peer.join.target, target=peer.join.source),
        reverse=peer.identity.name,
        dependent=peer.dependent,
        order_by=declaration.order_by,
    )


class RelationshipModelCompiler:
    """This module's Model Compiler: one facet, no prerequisite facet, no issues."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this compiler."""
        return RELATIONSHIP_MODULE

    @property
    def facet_key(self) -> FacetKey[RelationshipFacet]:
        """The key the compiled facet is installed under."""
        return FACET_KEY

    @property
    def requires(self) -> frozenset[FacetKey[Any]]:
        """The facets this compiler reads; relationship formation reads none."""
        return frozenset()

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> RelationshipFacet:
        """Compile ``metadata``'s relationship directions into the symmetric facet."""
        return compile_facet(metadata)


MODEL_COMPILER: Final[RelationshipModelCompiler] = RelationshipModelCompiler()
"""The single Model Compiler instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the compiler rather than constructing a second one."""
