from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import chain
from types import MappingProxyType
from typing import Final, Protocol, TypeGuard, cast, overload

from parallax.core.inheritance._declaration_order import declaration_order
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    FacetKey,
    InheritanceStrategy,
    MemberIdentity,
    MemberShape,
    Metamodel,
    PersistenceMode,
    RelationshipDeclaration,
    StorageContainer,
    ValueObjectMetadata,
)
from parallax.core.metamodel._shape import BoundShape

__all__ = [
    "FACET_KEY",
    "INHERITANCE_MODULE",
    "EntityMemberSelection",
    "InheritanceEntityFacts",
    "InheritanceEntityView",
    "InheritanceFacet",
    "InheritanceFamilyView",
    "InheritancePositionView",
    "inheritance_facet",
    "member_selection",
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
    root-owned mode and is never absent. ``primary_key`` is the family's one key
    Attribute: the root's accepted declaration, the same object at every
    position of the family.
    """

    @property
    def entity(self) -> EntityIdentity: ...
    @property
    def root(self) -> EntityIdentity: ...
    @property
    def primary_key(self) -> AttributeMetadata: ...
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
    def applicable_value_object(self, name: str) -> ValueObjectMetadata | None: ...


class InheritanceFamilyView(Protocol):
    """One family's complete declaration sequence, dormant branches included.

    Every family participant contributes its declared members once, in the
    order ``m-inheritance`` fixes, so the root's superset sequences are
    prefixes of these. A standalone Entity's sequence is its own declarations.
    """

    @property
    def attributes(self) -> Sequence[AttributeMetadata]: ...
    @property
    def value_objects(self) -> Sequence[ValueObjectMetadata]: ...


class InheritanceFacet(Protocol):
    """Every accepted Entity's family-effective answers, precomputed once.

    ``entity`` is total, nonthrowing, and expected amortized ``O(1)``, absent
    only for an Identity the model does not contain. ``position`` resolves an
    arbitrary member set and is absent for an unknown member or for members
    spread across more than one family; a standalone Entity forms a position
    only alone. Duplicate and overlapping members are valid input, and a
    position whose effective set is empty yields empty sequences rather than
    absence. ``family`` is expected amortized ``O(1)`` and absent for any
    Identity that is not a family root; every standalone Entity is its own
    root.
    """

    def entity(self, identity: EntityIdentity) -> InheritanceEntityView | None: ...
    def position(self, members: Sequence[EntityIdentity]) -> InheritancePositionView | None: ...
    def family(self, root: EntityIdentity) -> InheritanceFamilyView | None: ...


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
    primary_key: AttributeMetadata
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

    def __hash__(self) -> int:
        return hash(tuple(self))


@dataclass(frozen=True, slots=True, init=False, repr=False, match_args=False)
class EntityMemberSelection:
    """One Entity's complete inheritance-effective member selection."""

    __match_args__ = ("shape", "bindings", "attribute_count")

    _members: BoundShape[AttributeMetadata, ValueObjectMetadata]
    _position_by_identity: Mapping[MemberIdentity, int] = field(repr=False, compare=False)
    _identities: _BindingIdentities = field(repr=False, compare=False)

    def __init__(
        self, shape: MemberShape, bindings: tuple[_EntityBinding, ...], attribute_count: int
    ) -> None:
        members: BoundShape[AttributeMetadata, ValueObjectMetadata] = BoundShape(
            shape, bindings, attribute_count
        )
        positions = {binding.identity: position for position, binding in enumerate(bindings)}
        if len(positions) != len(bindings):
            raise ValueError("an Entity member selection assigns each identity one position")
        object.__setattr__(self, "_members", members)
        object.__setattr__(self, "_position_by_identity", MappingProxyType(positions))
        object.__setattr__(self, "_identities", _BindingIdentities(bindings))

    def __repr__(self) -> str:
        return (
            f"{type(self).__qualname__}(shape={self.shape!r}, bindings={self.bindings!r}, "
            f"attribute_count={self.attribute_count!r})"
        )

    @property
    def shape(self) -> MemberShape:
        return self._members.shape

    @property
    def bindings(self) -> tuple[_EntityBinding, ...]:
        return self._members.bindings

    @property
    def attribute_count(self) -> int:
        return self._members.leaf_count

    @property
    def attributes(self) -> Sequence[AttributeMetadata]:
        return self._members.leaves

    @property
    def value_objects(self) -> Sequence[ValueObjectMetadata]:
        return self._members.occurrences

    @property
    def identities(self) -> Sequence[MemberIdentity]:
        return self._identities

    @property
    def index(self) -> Mapping[MemberIdentity, int]:
        return self._position_by_identity

    def position(self, member: MemberIdentity) -> int:
        return self._position_by_identity[member]

    def binding(self, name: str) -> _EntityBinding | None:
        return self._members.binding(name)

    def attribute(self, name: str) -> AttributeMetadata | None:
        return self._members.leaf(name)

    def value_object(self, name: str) -> ValueObjectMetadata | None:
        return self._members.occurrence(name)


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
    primary_key: AttributeMetadata
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
        return self.member_selection.attribute(name)

    def applicable_value_object(self, name: str) -> ValueObjectMetadata | None:
        return self.member_selection.value_object(name)


type _Members = tuple[tuple[AttributeMetadata, ...], tuple[ValueObjectMetadata, ...]]


@dataclass(frozen=True, slots=True, eq=False)
class _Concatenated[T](Sequence[T]):
    """``prefix`` followed by ``suffix``, joined without copying either."""

    prefix: tuple[T, ...]
    suffix: tuple[T, ...]

    def __len__(self) -> int:
        return len(self.prefix) + len(self.suffix)

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[T]: ...

    def __getitem__(self, index: int | slice) -> T | Sequence[T]:
        if isinstance(index, slice):
            return (*self.prefix, *self.suffix)[index]
        boundary = len(self.prefix)
        if index < 0:
            index += len(self)
            if index < 0:
                raise IndexError("family declaration index out of range")
        if index < boundary:
            return self.prefix[index]
        return self.suffix[index - boundary]

    def __iter__(self) -> Iterator[T]:
        return chain(self.prefix, self.suffix)


@dataclass(frozen=True, slots=True)
class _InheritanceFamilyView:
    attributes: Sequence[AttributeMetadata]
    value_objects: Sequence[ValueObjectMetadata]


_NO_SUFFIXES: Final[Mapping[EntityIdentity, _Members]] = MappingProxyType({})


def _declared[T](members: Sequence[T]) -> tuple[T, ...]:
    return members if isinstance(members, tuple) else tuple(members)


def _members(
    facts: Mapping[EntityIdentity, InheritanceEntityFacts], contributors: Sequence[EntityIdentity]
) -> _Members:
    """The declared members ``contributors`` add, in contributor order.

    A lone contributor's accepted declaration tuples are the answer itself, so a
    standalone Entity's supersets are its declarations rather than copies.
    """
    if len(contributors) == 1:
        declared = facts[contributors[0]].declared
        return _declared(declared.declared_attributes), _declared(declared.declared_value_objects)
    return (
        tuple(
            member
            for identity in contributors
            for member in facts[identity].declared.declared_attributes
        ),
        tuple(
            member
            for identity in contributors
            for member in facts[identity].declared.declared_value_objects
        ),
    )


def _chains(
    facts: Mapping[EntityIdentity, InheritanceEntityFacts], effective: Sequence[EntityIdentity]
) -> tuple[tuple[EntityIdentity, ...], ...]:
    return tuple(facts[concrete].ancestry for concrete in effective)


def _project(
    facts: Mapping[EntityIdentity, InheritanceEntityFacts], effective: tuple[EntityIdentity, ...]
) -> _InheritancePositionView:
    contributors, _ = declaration_order(_chains(facts, effective))
    return _InheritancePositionView(effective, *_members(facts, contributors))


def _entity_view(position: InheritanceEntityFacts, superset: _Members) -> _InheritanceEntityView:
    return _InheritanceEntityView(
        entity=position.entity,
        root=position.root,
        primary_key=position.primary_key,
        strategy=position.strategy,
        ancestry=position.ancestry,
        concrete_subtypes=position.concrete_subtypes,
        container=position.container,
        tag_column=position.tag_column,
        tag_value=position.tag_value,
        persistence=position.persistence,
        member_selection=position.member_selection,
        applicable_relationships=position.applicable_relationships,
        superset_attributes=superset[0],
        superset_value_objects=superset[1],
    )


class _InheritanceFacet:
    """The compiled facet: one view per accepted Entity, position resolution,
    and each root's family declaration sequence.

    A root's supersets are its family declaration sequence's prefix, so only a family with
    dormant participants retains anything more: the members of that suffix.
    """

    __slots__ = ("_facts", "_suffixes", "_views")

    _facts: Mapping[EntityIdentity, InheritanceEntityFacts]
    _suffixes: Mapping[EntityIdentity, _Members]
    _views: Mapping[EntityIdentity, _InheritanceEntityView]

    def __init__(self, positions: Sequence[InheritanceEntityFacts]) -> None:
        facts = {position.entity: position for position in positions}
        dormant: dict[EntityIdentity, list[EntityIdentity]] = {}
        for position in positions:
            if not position.concrete_subtypes:
                dormant.setdefault(position.root, []).append(position.entity)
        views: dict[EntityIdentity, _InheritanceEntityView] = {}
        suffixes: dict[EntityIdentity, _Members] = {}
        for position in positions:
            contributors, prefix = declaration_order(
                _chains(facts, position.concrete_subtypes),
                dormant.get(position.entity, ()),
                position.entity,
            )
            views[position.entity] = _entity_view(position, _members(facts, contributors[:prefix]))
            if prefix < len(contributors):
                suffixes[position.entity] = _members(facts, contributors[prefix:])
        self._facts = MappingProxyType(facts)
        self._views = MappingProxyType(views)
        self._suffixes = MappingProxyType(suffixes) if suffixes else _NO_SUFFIXES

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

    def family(self, root: EntityIdentity) -> InheritanceFamilyView | None:
        view = self._views.get(root)
        if view is None or view.root != root:
            return None
        suffix = self._suffixes.get(root)
        if suffix is None:
            return _InheritanceFamilyView(view.superset_attributes, view.superset_value_objects)
        attributes, value_objects = suffix
        return _InheritanceFamilyView(
            _Concatenated(view.superset_attributes, attributes),
            _Concatenated(view.superset_value_objects, value_objects),
        )


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
