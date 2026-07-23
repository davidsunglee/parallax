"""The Inheritance Facet and its typed retrieval (m-inheritance).

An inheritance family answers questions no single Entity can: which concrete
variants a polymorphic position denotes, which members apply there, which
physical container and discriminator a read or write of it targets, and which
Persistence Mode the family's root fixed. This module owns those answers as one
immutable per-formation view, precomputed once so behavioral modules never walk
an ancestry again.

The projection law lives here rather than in the compiler because an Entity's
own supersets are defined as its one-member position: computing both through the
same operation makes that equality hold by construction. Every Metadata value a
view returns is the accepted declaration itself, so an inherited member still
names the ancestor that introduced it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Protocol, TypeGuard

from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    FacetKey,
    InheritanceStrategy,
    Metamodel,
    PersistenceMode,
    RelationshipDeclaration,
    StorageContainer,
    ValueObjectMetadata,
)

__all__ = [
    "FACET_KEY",
    "INHERITANCE_MODULE",
    "InheritanceEntityFacts",
    "InheritanceEntityView",
    "InheritanceFacet",
    "InheritancePositionView",
    "inheritance_facet",
    "is_inheritance_facet",
    "view",
]

INHERITANCE_MODULE: Final[str] = "m-inheritance"
"""The catalog identity that owns inheritance formation, its Issue Codes, and
the Inheritance Facet."""


class InheritancePositionView(Protocol):
    """The projection an arbitrary resolved position denotes.

    A position is one Entity, or the resolved members of a narrowing, and it
    denotes the union of their effective concrete-subtype sets. The two superset
    sequences are the abstract-read projection over that set: each contributing
    Entity appears once, so every Attribute and Value Object appears exactly
    once with its declaring identity preserved.
    """

    @property
    def concrete_subtypes(self) -> Sequence[EntityIdentity]: ...
    @property
    def superset_attributes(self) -> Sequence[AttributeMetadata]: ...
    @property
    def superset_value_objects(self) -> Sequence[ValueObjectMetadata]: ...


class InheritanceEntityView(Protocol):
    """One Entity's family-effective view, covering standalone Entities too.

    A standalone Entity has the trivial view: it is its own root, its ancestry
    and concrete-subtype set are itself alone, it has no strategy or tag, and
    its applicable members are its own. For a participant, ``ancestry`` runs
    root first, the ``applicable_*`` sequences are that chain's declared members
    in chain order, and ``container``/``tag_column``/``tag_value`` are the
    physical facts the root's strategy fixes. ``persistence`` is the effective
    root-owned mode and is never absent.
    """

    @property
    def entity(self) -> EntityIdentity: ...
    @property
    def root(self) -> EntityIdentity: ...
    @property
    def strategy(self) -> InheritanceStrategy | None: ...
    @property
    def ancestry(self) -> Sequence[EntityIdentity]: ...
    @property
    def concrete_subtypes(self) -> Sequence[EntityIdentity]: ...
    @property
    def container(self) -> StorageContainer | None: ...
    @property
    def tag_column(self) -> str | None: ...
    @property
    def tag_value(self) -> str | None: ...
    @property
    def persistence(self) -> PersistenceMode: ...
    @property
    def applicable_attributes(self) -> Sequence[AttributeMetadata]: ...
    @property
    def applicable_relationships(self) -> Sequence[RelationshipDeclaration]: ...
    @property
    def applicable_value_objects(self) -> Sequence[ValueObjectMetadata]: ...
    @property
    def superset_attributes(self) -> Sequence[AttributeMetadata]: ...
    @property
    def superset_value_objects(self) -> Sequence[ValueObjectMetadata]: ...
    def applicable_attribute(self, name: str) -> AttributeMetadata | None: ...
    def applicable_relationship(self, name: str) -> RelationshipDeclaration | None: ...
    def applicable_value_object(self, name: str) -> ValueObjectMetadata | None: ...


class InheritanceFacet(Protocol):
    """Every accepted Entity's family-effective answers, precomputed once.

    ``entity`` is total, nonthrowing, and expected amortized ``O(1)``, absent
    only for an Identity the model does not contain. ``position`` resolves an
    arbitrary member set and is absent for an unknown member or for members
    spread across more than one family; a standalone Entity forms a position
    only alone. Duplicate and overlapping members are valid input, and a
    position whose effective set is empty yields empty sequences rather than
    absence.
    """

    def entity(self, identity: EntityIdentity) -> InheritanceEntityView | None: ...
    def position(self, members: Sequence[EntityIdentity]) -> InheritancePositionView | None: ...


@dataclass(frozen=True, slots=True)
class InheritanceEntityFacts:
    """One Entity's family structure, as its compiler derived it.

    The compiler decides ancestry, descent, and the physical facts a strategy
    fixes; the facet derives the projection supersets from these. The two
    ``declared_*`` sequences are the Entity's own accepted members, which the
    projection law concatenates for every contributing Entity.
    """

    entity: EntityIdentity
    root: EntityIdentity
    strategy: InheritanceStrategy | None
    ancestry: tuple[EntityIdentity, ...]
    concrete_subtypes: tuple[EntityIdentity, ...]
    container: StorageContainer | None
    tag_column: str | None
    tag_value: str | None
    persistence: PersistenceMode
    applicable_attributes: tuple[AttributeMetadata, ...]
    applicable_relationships: tuple[RelationshipDeclaration, ...]
    applicable_value_objects: tuple[ValueObjectMetadata, ...]
    declared_attributes: tuple[AttributeMetadata, ...]
    declared_value_objects: tuple[ValueObjectMetadata, ...]


@dataclass(frozen=True, slots=True)
class _InheritancePositionView:
    concrete_subtypes: tuple[EntityIdentity, ...]
    superset_attributes: tuple[AttributeMetadata, ...]
    superset_value_objects: tuple[ValueObjectMetadata, ...]


@dataclass(frozen=True, slots=True)
class _InheritanceEntityView:
    """One compiled Entity view over read-only indexes nothing else holds."""

    entity: EntityIdentity
    root: EntityIdentity
    strategy: InheritanceStrategy | None
    ancestry: tuple[EntityIdentity, ...]
    concrete_subtypes: tuple[EntityIdentity, ...]
    container: StorageContainer | None
    tag_column: str | None
    tag_value: str | None
    persistence: PersistenceMode
    applicable_attributes: tuple[AttributeMetadata, ...]
    applicable_relationships: tuple[RelationshipDeclaration, ...]
    applicable_value_objects: tuple[ValueObjectMetadata, ...]
    superset_attributes: tuple[AttributeMetadata, ...]
    superset_value_objects: tuple[ValueObjectMetadata, ...]
    _attribute_index: Mapping[str, AttributeMetadata] = field(init=False, repr=False, compare=False)
    _relationship_index: Mapping[str, RelationshipDeclaration] = field(
        init=False, repr=False, compare=False
    )
    _value_object_index: Mapping[str, ValueObjectMetadata] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_attribute_index",
            MappingProxyType(
                {member.identity.name: member for member in self.applicable_attributes}
            ),
        )
        object.__setattr__(
            self,
            "_relationship_index",
            MappingProxyType(
                {member.identity.name: member for member in self.applicable_relationships}
            ),
        )
        object.__setattr__(
            self,
            "_value_object_index",
            MappingProxyType(
                {member.identity.path[-1]: member for member in self.applicable_value_objects}
            ),
        )

    def applicable_attribute(self, name: str) -> AttributeMetadata | None:
        return self._attribute_index.get(name)

    def applicable_relationship(self, name: str) -> RelationshipDeclaration | None:
        return self._relationship_index.get(name)

    def applicable_value_object(self, name: str) -> ValueObjectMetadata | None:
        return self._value_object_index.get(name)


def _project(
    facts: Mapping[EntityIdentity, InheritanceEntityFacts], effective: tuple[EntityIdentity, ...]
) -> _InheritancePositionView:
    """The projection superset over an effective concrete-subtype set.

    Ancestors contribute first: traversing the effective set in canonical order
    and appending each member's root-first ancestor chain, an ancestor that is
    not itself in the set contributes at its first encounter. Then the effective
    members contribute, in canonical order. Each contributor's own members keep
    declaration order, so the result is a duplicate-free concatenation.
    """
    contributors: list[EntityIdentity] = []
    encountered = set(effective)
    for concrete in effective:
        for ancestor in facts[concrete].ancestry[:-1]:
            if ancestor in encountered:
                continue
            encountered.add(ancestor)
            contributors.append(ancestor)
    contributors.extend(effective)
    return _InheritancePositionView(
        concrete_subtypes=effective,
        superset_attributes=tuple(
            member for identity in contributors for member in facts[identity].declared_attributes
        ),
        superset_value_objects=tuple(
            member for identity in contributors for member in facts[identity].declared_value_objects
        ),
    )


def _entity_view(
    position: InheritanceEntityFacts, projection: _InheritancePositionView
) -> InheritanceEntityView:
    return _InheritanceEntityView(
        entity=position.entity,
        root=position.root,
        strategy=position.strategy,
        ancestry=position.ancestry,
        concrete_subtypes=position.concrete_subtypes,
        container=position.container,
        tag_column=position.tag_column,
        tag_value=position.tag_value,
        persistence=position.persistence,
        applicable_attributes=position.applicable_attributes,
        applicable_relationships=position.applicable_relationships,
        applicable_value_objects=position.applicable_value_objects,
        superset_attributes=projection.superset_attributes,
        superset_value_objects=projection.superset_value_objects,
    )


class _InheritanceFacet:
    """The compiled facet: one view per accepted Entity, plus position resolution."""

    __slots__ = ("_facts", "_views")

    _facts: Mapping[EntityIdentity, InheritanceEntityFacts]
    _views: Mapping[EntityIdentity, InheritanceEntityView]

    def __init__(self, positions: Sequence[InheritanceEntityFacts]) -> None:
        facts = {position.entity: position for position in positions}
        self._facts = MappingProxyType(facts)
        self._views = MappingProxyType(
            {
                position.entity: _entity_view(position, _project(facts, position.concrete_subtypes))
                for position in positions
            }
        )

    def entity(self, identity: EntityIdentity) -> InheritanceEntityView | None:
        return self._views.get(identity)

    def position(self, members: Sequence[EntityIdentity]) -> InheritancePositionView | None:
        families: set[EntityIdentity] = set()
        effective: set[EntityIdentity] = set()
        for member in members:
            known = self._facts.get(member)
            if known is None:
                return None
            families.add(known.root)
            effective.update(known.concrete_subtypes)
        # A family identity per member also settles the empty and cross-family
        # inputs: no member names no family, and members of two families name
        # two, neither of which denotes a single position.
        if len(families) != 1:
            return None
        return _project(self._facts, tuple(sorted(effective, key=_canonical)))


def _canonical(identity: EntityIdentity) -> tuple[str, str]:
    return identity.sort_key


def inheritance_facet(positions: Sequence[InheritanceEntityFacts]) -> InheritanceFacet:
    """The facet serving ``positions``, which names every Entity of one model.

    An Entity missing from ``positions`` is unknown to the facet, so the
    compiler supplies a record for every accepted Entity — including the
    standalone ones that participate in no family.
    """
    return _InheritanceFacet(positions)


def is_inheritance_facet(value: object) -> TypeGuard[InheritanceFacet]:
    """Whether ``value`` is an Inheritance Facet this module compiled.

    ``m-inheritance`` owns the sole compiler for its facet and this is its only
    output type, so provenance decides rather than the surface a value presents.

    Exists for the formation seam that receives a compiler's result and must
    classify a wrong-typed one as a contract failure rather than install it.
    """
    return isinstance(value, _InheritanceFacet)


FACET_KEY: Final[FacetKey[InheritanceFacet]] = FacetKey(INHERITANCE_MODULE, is_inheritance_facet)
"""The typed key this module's facet is installed and retrieved under."""


def view(model: Metamodel) -> InheritanceFacet:
    """``model``'s Inheritance Facet.

    The typed retrieval every behavioral consumer uses, so generic facet lookup
    stays an internal formation seam. Total for an accepted Metamodel, which by
    construction carries the complete facet set.
    """
    return model.facet(FACET_KEY)
