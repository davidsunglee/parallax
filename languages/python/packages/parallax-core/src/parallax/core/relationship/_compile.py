"""The Relationship Facet's Model Compiler (m-relationship).

Compilation runs only after the Rule Set accepted the candidate, so it decides
no validity and emits no issue: it pairs each defining declaration with the
reverse that names it, derives the reverse direction by exchanging the join
sides and inverting the cardinality, and indexes the result. The accepted local
declarations are read, never copied or replaced — a direction is a derived view
of them. Reaching a state validation ruled out raises, so the formation runner
reports a compiler contract failure rather than publishing a facet.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from parallax.core.metamodel import (
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
    RelationshipFacet,
    RelationshipMetadata,
    inverted,
    relationship_facet,
)

__all__ = ["MODEL_COMPILER", "RelationshipModelCompiler", "compile_facet"]


def compile_facet(metadata: CompiledMetadata) -> RelationshipFacet:
    """Compile every accepted declaration of ``metadata`` into one directional value."""
    defining: dict[RelationshipIdentity, DefiningRelationshipDeclaration] = {}
    reverse_of: dict[RelationshipIdentity, RelationshipIdentity] = {}
    for entity in metadata.entities:
        for declaration in entity.declared_relationships:
            match declaration:
                case DefiningRelationshipDeclaration():
                    defining[declaration.identity] = declaration
                case ReverseRelationshipDeclaration():
                    reverse_of[declaration.reverse_of] = declaration.identity

    by_entity: dict[EntityIdentity, tuple[RelationshipMetadata, ...]] = {}
    for entity in metadata.entities:
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
        by_entity[entity.identity] = tuple(directions)
    return relationship_facet(by_entity)


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
