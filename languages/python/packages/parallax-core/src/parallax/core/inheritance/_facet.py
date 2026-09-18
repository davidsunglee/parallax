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

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import islice
from types import MappingProxyType
from typing import Final, Protocol, TypeGuard, cast, overload

from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    FacetKey,
    InheritanceStrategy,
    Leaf,
    MemberIdentity,
    MemberShape,
    Metamodel,
    PersistenceMode,
    RelationshipDeclaration,
    StorageContainer,
    ValueObjectMetadata,
)

__all__ = [
    "FACET_KEY",
    "INHERITANCE_MODULE",
    "EntityMemberSelection",
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
    def member_selection(self) -> EntityMemberSelection: ...
    @property
    def applicable_attributes(self) -> Sequence[AttributeMetadata]: ...
    @property
    def applicable_relationships(self) -> Sequence[RelationshipDeclaration]: ...
    @property
    def applicable_value_objects(self) -> Sequence[ValueObjectMetadata]: ...
    @property
    def applicable_document_shape(self) -> MemberShape: ...
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
    member_selection: EntityMemberSelection
    applicable_relationships: tuple[RelationshipDeclaration, ...]
    declared: EntityMetadata


type _EntityBinding = AttributeMetadata | ValueObjectMetadata


@dataclass(frozen=True, slots=True)
class _BindingRange[T](Sequence[T]):
    bindings: tuple[_EntityBinding, ...]
    start: int
    stop: int

    def __len__(self) -> int:
        return self.stop - self.start

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[T]: ...

    def __getitem__(self, index: int | slice) -> T | Sequence[T]:
        if isinstance(index, slice):
            return cast("Sequence[T]", self.bindings[self.start : self.stop][index])
        position = index if index >= 0 else len(self) + index
        if position < 0 or position >= len(self):
            raise IndexError(index)
        return cast("T", self.bindings[self.start + position])

    def __iter__(self) -> Iterator[T]:
        # The Sequence mixin would index every element through Python-level
        # `__getitem__`; each case below walks the shared tuple in C without
        # copying the window.
        if self.start == self.stop:
            return iter(())
        bindings = cast("tuple[T, ...]", self.bindings)
        if self.start == 0 and self.stop == len(bindings):
            return iter(bindings)
        return islice(bindings, self.start, self.stop)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sequence):
            return False
        compared = cast("Sequence[object]", other)
        return len(self) == len(compared) and all(
            left == right for left, right in zip(self, compared, strict=True)
        )


@dataclass(frozen=True, slots=True)
class _BindingIdentities(Sequence[MemberIdentity]):
    bindings: tuple[_EntityBinding, ...]

    def __len__(self) -> int:
        return len(self.bindings)

    @overload
    def __getitem__(self, index: int) -> MemberIdentity: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[MemberIdentity]: ...

    def __getitem__(self, index: int | slice) -> MemberIdentity | Sequence[MemberIdentity]:
        if isinstance(index, slice):
            return tuple(binding.identity for binding in self.bindings[index])
        return self.bindings[index].identity

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sequence):
            return False
        compared = cast("Sequence[object]", other)
        return len(self) == len(compared) and all(
            left == right for left, right in zip(self, compared, strict=True)
        )


@dataclass(frozen=True, slots=True)
class EntityMemberSelection:
    """One Entity's complete inheritance-effective member selection."""

    shape: MemberShape
    bindings: tuple[_EntityBinding, ...]
    attribute_count: int
    _position_by_identity: Mapping[MemberIdentity, int] = field(
        init=False, repr=False, compare=False
    )
    _attributes: _BindingRange[AttributeMetadata] = field(init=False, repr=False, compare=False)
    _value_objects: _BindingRange[ValueObjectMetadata] = field(
        init=False, repr=False, compare=False
    )
    _identities: _BindingIdentities = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if len(self.shape.members) != len(self.bindings):
            raise ValueError("an Entity member selection aligns every shape member to one binding")
        positions = {binding.identity: position for position, binding in enumerate(self.bindings)}
        if len(positions) != len(self.bindings):
            raise ValueError("an Entity member selection assigns each identity one position")
        if not 0 <= self.attribute_count <= len(self.bindings):
            raise ValueError("an Entity member selection counts its attributes within its bindings")
        object.__setattr__(self, "_position_by_identity", MappingProxyType(positions))
        object.__setattr__(self, "_identities", _BindingIdentities(self.bindings))
        object.__setattr__(
            self,
            "_attributes",
            _BindingRange(self.bindings, 0, self.attribute_count),
        )
        object.__setattr__(
            self,
            "_value_objects",
            _BindingRange(self.bindings, self.attribute_count, len(self.bindings)),
        )

    @property
    def attributes(self) -> Sequence[AttributeMetadata]:
        return self._attributes

    @property
    def value_objects(self) -> Sequence[ValueObjectMetadata]:
        return self._value_objects

    @property
    def identities(self) -> Sequence[MemberIdentity]:
        return self._identities

    @property
    def index(self) -> Mapping[MemberIdentity, int]:
        return self._position_by_identity

    def position(self, member: MemberIdentity) -> int:
        return self._position_by_identity[member]

    def binding(self, name: str) -> _EntityBinding | None:
        position = self.shape.position(name)
        return None if position is None else self.bindings[position]


def member_selection(
    attributes: Sequence[AttributeMetadata], value_objects: Sequence[ValueObjectMetadata]
) -> EntityMemberSelection:
    bindings: tuple[_EntityBinding, ...] = (*attributes, *value_objects)
    return EntityMemberSelection(
        shape=MemberShape.of(attributes, value_objects),
        bindings=bindings,
        attribute_count=len(attributes),
    )


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
    member_selection: EntityMemberSelection
    applicable_relationships: tuple[RelationshipDeclaration, ...]
    superset_attributes: tuple[AttributeMetadata, ...]
    superset_value_objects: tuple[ValueObjectMetadata, ...]
    _relationship_index: Mapping[str, RelationshipDeclaration] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_relationship_index",
            MappingProxyType(
                {member.identity.name: member for member in self.applicable_relationships}
            ),
        )

    @property
    def applicable_attributes(self) -> Sequence[AttributeMetadata]:
        return self.member_selection.attributes

    @property
    def applicable_value_objects(self) -> Sequence[ValueObjectMetadata]:
        return self.member_selection.value_objects

    @property
    def applicable_document_shape(self) -> MemberShape:
        return self.member_selection.shape

    def applicable_attribute(self, name: str) -> AttributeMetadata | None:
        binding = self.member_selection.binding(name)
        position = self.member_selection.shape.position(name)
        if position is None or not isinstance(self.member_selection.shape.members[position], Leaf):
            return None
        return cast("AttributeMetadata", binding)

    def applicable_relationship(self, name: str) -> RelationshipDeclaration | None:
        return self._relationship_index.get(name)

    def applicable_value_object(self, name: str) -> ValueObjectMetadata | None:
        binding = self.member_selection.binding(name)
        position = self.member_selection.shape.position(name)
        if position is None or isinstance(self.member_selection.shape.members[position], Leaf):
            return None
        return cast("ValueObjectMetadata", binding)


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
            member
            for identity in contributors
            for member in facts[identity].declared.declared_attributes
        ),
        superset_value_objects=tuple(
            member
            for identity in contributors
            for member in facts[identity].declared.declared_value_objects
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
        member_selection=position.member_selection,
        applicable_relationships=position.applicable_relationships,
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
