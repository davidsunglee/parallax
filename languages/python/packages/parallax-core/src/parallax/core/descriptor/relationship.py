"""Canonical relationship declarations and compiled directional facet.

Entities retain the closed defining/reverse declaration union required for
portable descriptor round-tripping. Behavioral modules consume only the
directional :class:`Relationship` values compiled here: structured joins,
canonical target Entity spellings, and an optional peer name.
"""

from __future__ import annotations

from parallax.core.descriptor.errors import DescriptorError
from parallax.core.descriptor.records import (
    DefiningRelationship,
    Entity,
    Metamodel,
    Relationship,
    RelationshipCardinality,
    RelationshipDeclaration,
    RelationshipJoin,
    RelationshipTarget,
    ReverseRelationship,
)

__all__ = ["relationship_target", "relationships_for"]

_INVERSE: dict[RelationshipCardinality, RelationshipCardinality] = {
    "one-to-one": "one-to-one",
    "many-to-one": "one-to-many",
    "one-to-many": "many-to-one",
}


def _entity_reference(owner: Entity, reference: str) -> str:
    if "." in reference or owner.namespace is None:
        return reference
    return f"{owner.namespace}.{reference}"


def _reverse_reference(owner: Entity, reference: str) -> tuple[str, str]:
    entity_reference, separator, relationship_name = reference.rpartition(".")
    if not separator or not entity_reference or not relationship_name:
        raise DescriptorError(
            f"entity {owner.canonical_name!r}: reverseOf must name Entity.relationship"
        )
    return _entity_reference(owner, entity_reference), relationship_name


def relationship_target(owner: Entity, declaration: RelationshipDeclaration) -> str:
    """Return a declaration's target Entity without compiling association facts."""
    if isinstance(declaration, DefiningRelationship):
        return _entity_reference(owner, declaration.join.target.entity)
    target, _ = _reverse_reference(owner, declaration.reverse_of)
    return target


def relationships_for(meta: Metamodel, entity: str | Entity) -> tuple[Relationship, ...]:
    """Compile one Entity's canonical directional Relationship facet values.

    Compilation is pure and retains no parallel metadata graph. The defining
    declaration remains the sole owner of cardinality, join, dependency, and
    target facts; a reverse direction derives those facts mechanically.
    """
    owner = meta.entity(entity) if isinstance(entity, str) else entity
    entities = {candidate.canonical_name: candidate for candidate in meta.entities}
    defining: dict[tuple[str, str], DefiningRelationship] = {}
    reverse_by_defining: dict[tuple[str, str], tuple[Entity, ReverseRelationship]] = {}

    for candidate_owner in meta.entities:
        for declaration in candidate_owner.relationships:
            if isinstance(declaration, DefiningRelationship):
                key = (candidate_owner.canonical_name, declaration.name)
                defining[key] = declaration

    for reverse_owner in meta.entities:
        for declaration in reverse_owner.relationships:
            if not isinstance(declaration, ReverseRelationship):
                continue
            defining_entity, defining_name = _reverse_reference(
                reverse_owner, declaration.reverse_of
            )
            key = (defining_entity, defining_name)
            if reverse_owner is not owner and key[0] != owner.canonical_name:
                continue
            peer = defining.get(key)
            if peer is None:
                if reverse_owner is not owner:
                    # Compiling one Entity's facet must not be blocked by an
                    # unrelated reverse declaration elsewhere in a temporary
                    # scoped frontend model. Formation still rejects that
                    # declaration when its own owner is compiled.
                    continue
                raise DescriptorError(
                    f"entity {reverse_owner.canonical_name!r} relationship "
                    f"{declaration.name!r}: reverseOf {declaration.reverse_of!r} "
                    "does not name a defining relationship"
                )
            peer_owner = entities.get(defining_entity)
            if peer_owner is None:
                raise DescriptorError(
                    f"entity {reverse_owner.canonical_name!r} relationship "
                    f"{declaration.name!r}: reverseOf references unknown entity "
                    f"{defining_entity!r}"
                )
            peer_target = _entity_reference(peer_owner, peer.join.target.entity)
            if peer_target != reverse_owner.canonical_name:
                raise DescriptorError(
                    f"entity {reverse_owner.canonical_name!r} relationship "
                    f"{declaration.name!r}: reverseOf targets {peer_target!r}, not the "
                    "declaring entity"
                )
            if key in reverse_by_defining:
                raise DescriptorError(
                    f"relationship {defining_entity}.{defining_name} has more than one reverse"
                )
            reverse_by_defining[key] = (reverse_owner, declaration)

    compiled: list[Relationship] = []
    for declaration in owner.relationships:
        if isinstance(declaration, DefiningRelationship):
            target = _entity_reference(owner, declaration.join.target.entity)
            reverse = reverse_by_defining.get((owner.canonical_name, declaration.name))
            compiled.append(
                Relationship(
                    name=declaration.name,
                    cardinality=declaration.cardinality,
                    join=RelationshipJoin(
                        source=declaration.join.source,
                        target=RelationshipTarget(
                            entity=target,
                            attribute=declaration.join.target.attribute,
                        ),
                    ),
                    reverse=reverse[1].name if reverse is not None else None,
                    dependent=declaration.dependent,
                    order_by=declaration.order_by,
                )
            )
            continue

        defining_entity, defining_name = _reverse_reference(owner, declaration.reverse_of)
        peer = defining.get((defining_entity, defining_name))
        if peer is None:
            raise DescriptorError(
                f"entity {owner.canonical_name!r} relationship {declaration.name!r}: "
                f"reverseOf {declaration.reverse_of!r} does not name a defining relationship"
            )
        compiled.append(
            Relationship(
                name=declaration.name,
                cardinality=_INVERSE[peer.cardinality],
                join=RelationshipJoin(
                    source=peer.join.target.attribute,
                    target=RelationshipTarget(
                        entity=defining_entity,
                        attribute=peer.join.source,
                    ),
                ),
                reverse=defining_name,
                dependent=peer.dependent,
                order_by=declaration.order_by,
            )
        )
    return tuple(compiled)
