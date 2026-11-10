from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from itertools import chain
from typing import Final, Protocol

from parallax.core.internal.entity._members import AbstractSubtype, ConcreteSubtype
from parallax.core.internal.inheritance import InheritanceEntityView, inheritance_facet_of
from parallax.core.internal.metamodel import (
    AbstractRoot,
    AsOfAxisMetadata,
    AttributeMetadata,
    CompiledEntity,
    EntityIdentity,
    IndexMetadata,
    InheritanceMetadata,
    Metamodel,
    PersistenceMode,
    RelationshipIdentity,
    StorageContainer,
    StorageLayout,
    TemporalDimension,
    ValueObjectMetadata,
    inheritance_parent,
)
from parallax.core.internal.metamodel import AbstractSubtype as CompiledAbstractSubtype
from parallax.core.internal.metamodel import ConcreteSubtype as CompiledConcreteSubtype
from parallax.core.internal.relationship import (
    RelationshipFacet,
    RelationshipMetadata,
    relationship_facet_of,
)
from parallax.core.internal.temporal_read import ranked_axes, temporal_facet_of

__all__ = ["EntityMetadata", "EntityProfile", "describe_entities"]


class EntityProfile(Protocol):
    """One scope of an Entity's resolved metadata: what it declares, or what is
    in force on it.

    Both scopes share this shape. A declared profile answers only the Entity's
    own facts, so a subtype's root-owned container, persistence, layout, and
    primary key are absent there. An effective profile answers the facts in
    force, members inherited along the ancestry chain included, root first; its
    members are the declared profiles' own objects. Lookups answer ``None`` for
    a name or dimension the scope does not contain.
    """

    @property
    def container(self) -> StorageContainer | None: ...
    @property
    def persistence(self) -> PersistenceMode | None: ...
    @property
    def layout(self) -> StorageLayout | None: ...
    @property
    def primary_key(self) -> AttributeMetadata | None: ...
    @property
    def attributes(self) -> Sequence[AttributeMetadata]: ...
    @property
    def relationships(self) -> Sequence[RelationshipMetadata]: ...
    @property
    def value_objects(self) -> Sequence[ValueObjectMetadata]: ...
    @property
    def as_of_axes(self) -> Sequence[AsOfAxisMetadata]: ...
    def attribute(self, name: str) -> AttributeMetadata | None: ...
    def relationship(self, name: str) -> RelationshipMetadata | None: ...
    def value_object(self, name: str) -> ValueObjectMetadata | None: ...
    def as_of_axis(self, dimension: TemporalDimension) -> AsOfAxisMetadata | None: ...


class EntityMetadata(Protocol):
    """One Entity's resolved, read-only metadata within one Domain Model.

    ``inheritance`` is the role as its author spells it, with ``parent`` the
    resolved parent Entity. ``indices`` are the Entity's own.
    """

    @property
    def identity(self) -> EntityIdentity: ...
    @property
    def inheritance(self) -> AbstractRoot | AbstractSubtype | ConcreteSubtype | None: ...
    @property
    def parent(self) -> EntityIdentity | None: ...
    @property
    def indices(self) -> Sequence[IndexMetadata]: ...
    @property
    def declared(self) -> EntityProfile: ...
    @property
    def effective(self) -> EntityProfile: ...


class _MemberLookup(Protocol):
    def attribute(self, name: str) -> AttributeMetadata | None: ...
    def value_object(self, name: str) -> ValueObjectMetadata | None: ...


@dataclass(frozen=True, slots=True, eq=False)
class _EntityProfile:
    container: StorageContainer | None
    persistence: PersistenceMode | None
    layout: StorageLayout | None
    primary_key: AttributeMetadata | None
    attributes: Sequence[AttributeMetadata]
    relationships: Sequence[RelationshipMetadata]
    value_objects: Sequence[ValueObjectMetadata]
    as_of_axes: Sequence[AsOfAxisMetadata]
    _members: _MemberLookup = field(repr=False)
    _directions: RelationshipFacet = field(repr=False)
    _chain: tuple[EntityIdentity, ...] = field(repr=False)
    _axis: Callable[[TemporalDimension], AsOfAxisMetadata | None] = field(repr=False)

    def attribute(self, name: str) -> AttributeMetadata | None:
        return self._members.attribute(name)

    def relationship(self, name: str) -> RelationshipMetadata | None:
        # A relationship name is unique along an ancestry chain, so the first
        # position declaring it is the only one.
        for position in self._chain:
            found = self._directions.relationship(RelationshipIdentity(position, name))
            if found is not None:
                return found
        return None

    def value_object(self, name: str) -> ValueObjectMetadata | None:
        return self._members.value_object(name)

    def as_of_axis(self, dimension: TemporalDimension) -> AsOfAxisMetadata | None:
        return self._axis(dimension)


@dataclass(frozen=True, slots=True, eq=False)
class _EntityMetadata:
    identity: EntityIdentity
    inheritance: AbstractRoot | AbstractSubtype | ConcreteSubtype | None
    parent: EntityIdentity | None
    indices: Sequence[IndexMetadata]
    declared: _EntityProfile
    effective: _EntityProfile


_ABSTRACT_SUBTYPE: Final[AbstractSubtype] = AbstractSubtype()


def describe_entities(model: Metamodel) -> tuple[EntityMetadata, ...]:
    """Every accepted Entity of ``model`` resolved once, in canonical Entity order.

    Each fact comes from the owner that decides it: local declarations from the
    compiled Entity, paired directions from the relationship facet,
    family-effective members and root-owned facts from the inheritance facet,
    and effective As-Of Axes from the temporal facet. Members, inheritance
    selection windows, and relationship tuples are shared rather than copied.
    """
    families = inheritance_facet_of(model)
    directions = relationship_facet_of(model)
    temporal = temporal_facet_of(model)
    described: list[EntityMetadata] = []
    for compiled in model.entities:
        identity = compiled.identity
        family = families.entity(identity)
        shape = temporal.shape(identity)
        if family is None or shape is None:  # pragma: no cover - facets cover every Entity
            raise RuntimeError(f"Entity {identity.canonical!r} has no facet view")
        declared = _declared(compiled, family, directions)
        described.append(
            _EntityMetadata(
                identity=identity,
                inheritance=_authored_role(compiled.inheritance),
                parent=inheritance_parent(compiled.inheritance),
                indices=compiled.indices,
                declared=declared,
                effective=_effective(
                    family,
                    directions,
                    declared.relationships,
                    ranked_axes(shape),
                    partial(temporal.axis, identity),
                ),
            )
        )
    return tuple(described)


def _declared(
    compiled: CompiledEntity, family: InheritanceEntityView, directions: RelationshipFacet
) -> _EntityProfile:
    identity = compiled.identity
    return _EntityProfile(
        container=compiled.declared_container,
        persistence=compiled.declared_persistence,
        layout=compiled.declared_layout,
        primary_key=family.primary_key if family.root == identity else None,
        attributes=compiled.declared_attributes,
        relationships=directions.relationships(identity) or (),
        value_objects=compiled.declared_value_objects,
        as_of_axes=compiled.declared_as_of_axes,
        _members=compiled,
        _directions=directions,
        _chain=(identity,),
        _axis=compiled.as_of_axis,
    )


def _effective(
    family: InheritanceEntityView,
    directions: RelationshipFacet,
    declared_relationships: Sequence[RelationshipMetadata],
    as_of_axes: tuple[AsOfAxisMetadata, ...],
    axis: Callable[[TemporalDimension], AsOfAxisMetadata | None],
) -> _EntityProfile:
    ancestry = tuple(family.ancestry)
    relationships = (
        declared_relationships
        if len(ancestry) == 1
        else tuple(chain.from_iterable(directions.relationships(a) or () for a in ancestry))
    )
    selection = family.member_selection
    return _EntityProfile(
        container=family.container,
        persistence=family.persistence,
        layout=family.layout,
        primary_key=family.primary_key,
        attributes=selection.attributes,
        relationships=relationships,
        value_objects=selection.value_objects,
        as_of_axes=as_of_axes,
        _members=selection,
        _directions=directions,
        _chain=ancestry,
        _axis=axis,
    )


def _authored_role(
    role: InheritanceMetadata | None,
) -> AbstractRoot | AbstractSubtype | ConcreteSubtype | None:
    """``role`` as its author spells it: the parent is resolved apart from it."""
    match role:
        case None | AbstractRoot():
            return role
        case CompiledAbstractSubtype():
            return _ABSTRACT_SUBTYPE
        case CompiledConcreteSubtype(tag_value=tag_value):
            return ConcreteSubtype(tag_value)
