"""The identity-paired view of two endpoints every later stage reads.

Declarations are paired exactly once, by structured identity and never by
guessing a rename, so the differ, the classifier, and the impact analyzers never
re-pair. The value is internal to this scope and dies with the ``evolve`` call
that built it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from parallax.core.inheritance import InheritanceEntityView
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    IndexIdentity,
    IndexMetadata,
    Metamodel,
    NestedValueObjectMetadata,
    RelationshipDeclaration,
    RelationshipIdentity,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeMetadata,
    ValueObjectIdentity,
    ValueObjectMetadata,
    derive_primary_key_index,
)
from parallax.core.relationship import RelationshipMetadata
from parallax.core.relationship import view as relationship_view
from parallax.evolution.model_evolution._values import (
    Absent,
    DeclarationCollection,
    DeclarationIdentity,
)

__all__ = [
    "AxisKey",
    "CollectionOrder",
    "EntityFacts",
    "Matching",
    "Occurrence",
    "Paired",
    "RelationshipFacts",
    "match",
]

type AxisKey = tuple[EntityIdentity, TemporalDimension]
"""An As-Of Axis position: its Entity and the Temporal Dimension that identifies
it. The dimension participates in identity, so changing it is a removal and an
addition rather than an alteration."""

type Occurrence = ValueObjectMetadata | NestedValueObjectMetadata
"""A Value Object occurrence at either depth. A containment path of length one
is the top-level occurrence that owns the Storage Location; a longer one is
nested and owns none."""


@dataclass(frozen=True, slots=True)
class EntityFacts:
    """One Entity's accepted declaration beside its family-effective view.

    Both answer at one key because both are needed at once: a field delta
    reports the accepted declaration, while classification and the Behavioral
    Impacts compare the effective ancestry, physical facts, and Persistence Mode
    the family's root fixes.
    """

    declaration: EntityMetadata
    family: InheritanceEntityView


@dataclass(frozen=True, slots=True)
class RelationshipFacts:
    """One Relationship's accepted declaration beside its navigable direction.

    A reverse declaration exposes neither cardinality nor join; both are the
    defining peer's, derived once by ``m-relationship``. Classification and the
    Behavioral Impacts compare the direction, so a change made on the peer is
    seen from this side too, while a field delta still reports what this side
    itself declares.
    """

    declaration: RelationshipDeclaration
    direction: RelationshipMetadata


@dataclass(frozen=True, slots=True)
class CollectionOrder:
    """One local collection's surviving identities in each endpoint's order.

    Only identities present in BOTH endpoints appear, so inserting a new
    declaration between two existing ones leaves the two sequences equal and is
    reported as an addition rather than as a reordering.
    """

    collection: DeclarationCollection
    owner: EntityIdentity | ValueObjectIdentity
    earlier: tuple[DeclarationIdentity, ...]
    later: tuple[DeclarationIdentity, ...]


@dataclass(frozen=True, slots=True)
class Paired[I, D]:
    """One declaration kind's declarations, partitioned by which endpoints hold them."""

    added: Mapping[I, D]
    removed: Mapping[I, D]
    surviving: Mapping[I, tuple[D, D]]


@dataclass(frozen=True, slots=True)
class Matching:
    """Both accepted endpoints and their identity-paired declarations.

    ``earlier`` is ``None`` only for the fresh-provisioning evolution, where
    every later declaration is an addition.
    """

    earlier: Metamodel | None
    later: Metamodel
    entities: Paired[EntityIdentity, EntityFacts]
    attributes: Paired[AttributeIdentity, AttributeMetadata]
    value_objects: Paired[ValueObjectIdentity, Occurrence]
    value_object_attributes: Paired[ValueObjectAttributeIdentity, ValueObjectAttributeMetadata]
    relationships: Paired[RelationshipIdentity, RelationshipFacts]
    as_of_axes: Paired[AxisKey, AsOfAxisMetadata]
    indices: Paired[IndexIdentity, IndexMetadata]
    collection_orders: tuple[CollectionOrder, ...]


def pair[I, D](earlier: Sequence[tuple[I, D]], later: Sequence[tuple[I, D]]) -> Paired[I, D]:
    """Partition two identity-keyed declaration sequences into one :class:`Paired`."""
    earlier_by_identity = dict(earlier)
    later_by_identity = dict(later)
    return Paired(
        added=MappingProxyType(
            {
                identity: declaration
                for identity, declaration in later_by_identity.items()
                if identity not in earlier_by_identity
            }
        ),
        removed=MappingProxyType(
            {
                identity: declaration
                for identity, declaration in earlier_by_identity.items()
                if identity not in later_by_identity
            }
        ),
        surviving=MappingProxyType(
            {
                identity: (earlier_by_identity[identity], declaration)
                for identity, declaration in later_by_identity.items()
                if identity in earlier_by_identity
            }
        ),
    )


def match(earlier: Metamodel | Absent, later: Metamodel) -> Matching:
    """Pair both endpoints' declarations by structured identity."""
    earlier_model = None if isinstance(earlier, Absent) else earlier
    value_objects = _paired(earlier_model, later, _value_objects)
    return Matching(
        earlier=earlier_model,
        later=later,
        entities=_paired(earlier_model, later, _entities),
        attributes=_paired(earlier_model, later, _attributes),
        value_objects=value_objects,
        value_object_attributes=_paired(earlier_model, later, _value_object_attributes),
        relationships=_paired(earlier_model, later, _relationships),
        as_of_axes=_paired(earlier_model, later, _as_of_axes),
        indices=_paired(earlier_model, later, _indices),
        collection_orders=_collection_orders(earlier_model, later),
    )


def _paired[I, D](
    earlier: Metamodel | None,
    later: Metamodel,
    declarations: Callable[[Metamodel], Sequence[tuple[I, D]]],
) -> Paired[I, D]:
    """``declarations`` of both endpoints paired; absence declares nothing."""
    return pair(() if earlier is None else declarations(earlier), declarations(later))


def _entities(model: Metamodel) -> tuple[tuple[EntityIdentity, EntityFacts], ...]:
    facet = inheritance_view(model)
    paired: list[tuple[EntityIdentity, EntityFacts]] = []
    for entity in model.entities:
        family = facet.entity(entity.identity)
        if family is None:  # pragma: no cover - the facet covers every accepted Entity
            continue
        paired.append((entity.identity, EntityFacts(entity, family)))
    return tuple(paired)


def _attributes(model: Metamodel) -> tuple[tuple[AttributeIdentity, AttributeMetadata], ...]:
    """Every declared scalar Attribute, keyed by its own Identity.

    Declared rather than applicable: an inherited member belongs to the ancestor
    that introduced it, so pairing the applicable sequences would describe one
    declaration once per descendant.
    """
    return tuple(
        (attribute.identity, attribute)
        for entity in model.entities
        for attribute in entity.declared_attributes
    )


def _occurrences(occurrence: Occurrence) -> Iterator[Occurrence]:
    """``occurrence`` and every occurrence nested inside it, outermost first."""
    yield occurrence
    for nested in occurrence.value_objects:
        yield from _occurrences(nested)


def _declared_occurrences(model: Metamodel) -> Iterator[Occurrence]:
    for entity in model.entities:
        for occurrence in entity.declared_value_objects:
            yield from _occurrences(occurrence)


def _value_objects(model: Metamodel) -> tuple[tuple[ValueObjectIdentity, Occurrence], ...]:
    return tuple((occurrence.identity, occurrence) for occurrence in _declared_occurrences(model))


def _value_object_attributes(
    model: Metamodel,
) -> tuple[tuple[ValueObjectAttributeIdentity, ValueObjectAttributeMetadata], ...]:
    return tuple(
        (member.identity, member)
        for occurrence in _declared_occurrences(model)
        for member in occurrence.attributes
    )


def _relationships(
    model: Metamodel,
) -> tuple[tuple[RelationshipIdentity, RelationshipFacts], ...]:
    facet = relationship_view(model)
    paired: list[tuple[RelationshipIdentity, RelationshipFacts]] = []
    for entity in model.entities:
        for declaration in entity.declared_relationships:
            direction = facet.relationship(declaration.identity)
            if direction is None:  # pragma: no cover - the facet covers every declaration
                continue
            paired.append((declaration.identity, RelationshipFacts(declaration, direction)))
    return tuple(paired)


def _as_of_axes(model: Metamodel) -> tuple[tuple[AxisKey, AsOfAxisMetadata], ...]:
    return tuple(
        ((entity.identity, axis.dimension), axis)
        for entity in model.entities
        for axis in entity.declared_as_of_axes
    )


def _authored_indices(entity: EntityMetadata) -> tuple[IndexMetadata, ...]:
    """``entity``'s Indices without the derived primary-key one.

    The derived Index is not independently authored, so it never receives an
    Index operation and never contributes a uniqueness rule of its own: its
    changes are reported through the causal primary-key Attribute or As-Of Axis
    operation instead.
    """
    derived = derive_primary_key_index(
        entity=entity.identity,
        container=entity.declared_container,
        attributes=entity.declared_attributes,
        as_of_axes=entity.declared_as_of_axes,
    )
    return tuple(
        index for index in entity.indices if derived is None or index.identity != derived.identity
    )


def _indices(model: Metamodel) -> tuple[tuple[IndexIdentity, IndexMetadata], ...]:
    return tuple(
        (index.identity, index) for entity in model.entities for index in _authored_indices(entity)
    )


def _collection_orders(earlier: Metamodel | None, later: Metamodel) -> tuple[CollectionOrder, ...]:
    """Each local collection an owner surviving in both endpoints declares.

    Absence declares nothing, so provisioning compares no order at all.
    """
    if earlier is None:
        return ()
    before = dict(_local_collections(earlier))
    after = dict(_local_collections(later))
    orders: list[CollectionOrder] = []
    for key, sequence in after.items():
        previous = before.get(key)
        if previous is None:
            continue
        surviving = frozenset(previous) & frozenset(sequence)
        collection, owner = key
        orders.append(
            CollectionOrder(
                collection=collection,
                owner=owner,
                earlier=tuple(item for item in previous if item in surviving),
                later=tuple(item for item in sequence if item in surviving),
            )
        )
    return tuple(orders)


type _CollectionKey = tuple[DeclarationCollection, EntityIdentity | ValueObjectIdentity]


def _local_collections(
    model: Metamodel,
) -> Iterator[tuple[_CollectionKey, tuple[DeclarationIdentity, ...]]]:
    """Every local collection of ``model``, in its declared order."""
    for entity in model.entities:
        owner = entity.identity
        yield (
            (DeclarationCollection.ENTITY_ATTRIBUTES, owner),
            tuple(member.identity for member in entity.declared_attributes),
        )
        yield (
            (DeclarationCollection.ENTITY_RELATIONSHIPS, owner),
            tuple(member.identity for member in entity.declared_relationships),
        )
        yield (
            (DeclarationCollection.ENTITY_VALUE_OBJECTS, owner),
            tuple(member.identity for member in entity.declared_value_objects),
        )
        yield (
            (DeclarationCollection.ENTITY_INDICES, owner),
            tuple(index.identity for index in _authored_indices(entity)),
        )
        for declared in entity.declared_value_objects:
            for occurrence in _occurrences(declared):
                yield (
                    (DeclarationCollection.VALUE_OBJECT_ATTRIBUTES, occurrence.identity),
                    tuple(member.identity for member in occurrence.attributes),
                )
                yield (
                    (DeclarationCollection.NESTED_VALUE_OBJECTS, occurrence.identity),
                    tuple(nested.identity for nested in occurrence.value_objects),
                )
