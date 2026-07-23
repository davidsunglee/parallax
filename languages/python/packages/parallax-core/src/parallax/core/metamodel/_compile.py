"""The Metadata Compiler and the sole accepted metadata implementation (m-metamodel).

Compilation is the one issue-free step of Model Formation: it runs only after
every Rule Set accepted the candidate, so it decides no semantic validity,
pairs no relationships, inverts no cardinality, derives no inheritance, and
classifies no temporal behavior. It expands the already-valid Value Object
occurrence graph into path-identified Metadata, discards every Shape Key, and
builds the immutable local indexes accepted lookup uses. Reaching an impossible
state raises so the formation runner can report a compiler contract failure;
nothing here is a model issue.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, cast

from parallax.core.base import NeutralType
from parallax.core.metamodel._identities import (
    EntityIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.metamodel._issues import METAMODEL_MODULE
from parallax.core.metamodel._states import (
    CandidateMetamodel,
    CompiledMetadata,
    EntityDeclaration,
    EntityMetadata,
    FacetKey,
    Metamodel,
    NestedValueObjectMetadata,
    ValueObjectAttributeMetadata,
    ValueObjectMetadata,
)
from parallax.core.metamodel._values import (
    AsOfAxisMetadata,
    AttributeMetadata,
    IndexMetadata,
    InheritanceMetadata,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    PersistenceMode,
    RelationshipDeclaration,
    StorageContainer,
    StorageLocation,
    TemporalDimension,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)

__all__ = [
    "METADATA_COMPILER",
    "MetamodelMetadataCompiler",
    "accept_metamodel",
    "compile_metadata",
]


@dataclass(frozen=True, slots=True)
class _ValueObjectAttributeMetadata:
    identity: ValueObjectAttributeIdentity
    type: NeutralType
    nullable: bool


@dataclass(frozen=True, slots=True)
class _NestedValueObjectMetadata:
    identity: ValueObjectIdentity
    multiplicity: Multiplicity
    nullable: bool
    attributes: tuple[ValueObjectAttributeMetadata, ...]
    value_objects: tuple[NestedValueObjectMetadata, ...]
    _attribute_index: Mapping[str, ValueObjectAttributeMetadata] = field(
        init=False, repr=False, compare=False
    )
    _value_object_index: Mapping[str, NestedValueObjectMetadata] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _install_value_object_indexes(self)

    def attribute(self, name: str) -> ValueObjectAttributeMetadata | None:
        return self._attribute_index.get(name)

    def value_object(self, name: str) -> NestedValueObjectMetadata | None:
        return self._value_object_index.get(name)


@dataclass(frozen=True, slots=True)
class _ValueObjectMetadata:
    identity: ValueObjectIdentity
    storage: StorageLocation
    multiplicity: Multiplicity
    nullable: bool
    attributes: tuple[ValueObjectAttributeMetadata, ...]
    value_objects: tuple[NestedValueObjectMetadata, ...]
    _attribute_index: Mapping[str, ValueObjectAttributeMetadata] = field(
        init=False, repr=False, compare=False
    )
    _value_object_index: Mapping[str, NestedValueObjectMetadata] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _install_value_object_indexes(self)

    def attribute(self, name: str) -> ValueObjectAttributeMetadata | None:
        return self._attribute_index.get(name)

    def value_object(self, name: str) -> NestedValueObjectMetadata | None:
        return self._value_object_index.get(name)


def _install_value_object_indexes(
    metadata: _ValueObjectMetadata | _NestedValueObjectMetadata,
) -> None:
    """Build one composite's local member indexes on a frozen instance."""
    object.__setattr__(
        metadata,
        "_attribute_index",
        {member.identity.name: member for member in metadata.attributes},
    )
    object.__setattr__(
        metadata,
        "_value_object_index",
        {member.identity.path[-1]: member for member in metadata.value_objects},
    )


@dataclass(frozen=True, slots=True)
class _EntityMetadata:
    identity: EntityIdentity
    declared_container: StorageContainer | None
    declared_persistence: PersistenceMode | None
    declared_attributes: tuple[AttributeMetadata, ...]
    declared_relationships: tuple[RelationshipDeclaration, ...]
    declared_value_objects: tuple[ValueObjectMetadata, ...]
    declared_as_of_axes: tuple[AsOfAxisMetadata, ...]
    inheritance: InheritanceMetadata | None
    indices: tuple[IndexMetadata, ...]
    _attribute_index: Mapping[str, AttributeMetadata] = field(init=False, repr=False, compare=False)
    _relationship_index: Mapping[str, RelationshipDeclaration] = field(
        init=False, repr=False, compare=False
    )
    _value_object_index: Mapping[str, ValueObjectMetadata] = field(
        init=False, repr=False, compare=False
    )
    _axis_index: Mapping[TemporalDimension, AsOfAxisMetadata] = field(
        init=False, repr=False, compare=False
    )
    _index_index: Mapping[str, IndexMetadata] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_attribute_index",
            {member.identity.name: member for member in self.declared_attributes},
        )
        object.__setattr__(
            self,
            "_relationship_index",
            {member.identity.name: member for member in self.declared_relationships},
        )
        object.__setattr__(
            self,
            "_value_object_index",
            {member.identity.path[-1]: member for member in self.declared_value_objects},
        )
        object.__setattr__(
            self, "_axis_index", {axis.dimension: axis for axis in self.declared_as_of_axes}
        )
        object.__setattr__(
            self, "_index_index", {member.identity.name: member for member in self.indices}
        )

    def attribute(self, name: str) -> AttributeMetadata | None:
        return self._attribute_index.get(name)

    def relationship(self, name: str) -> RelationshipDeclaration | None:
        return self._relationship_index.get(name)

    def value_object(self, name: str) -> ValueObjectMetadata | None:
        return self._value_object_index.get(name)

    def as_of_axis(self, dimension: TemporalDimension) -> AsOfAxisMetadata | None:
        return self._axis_index.get(dimension)

    def index(self, name: str) -> IndexMetadata | None:
        return self._index_index.get(name)


@dataclass(frozen=True, slots=True)
class _CompiledMetadata:
    entities: tuple[EntityMetadata, ...]
    _by_identity: Mapping[EntityIdentity, EntityMetadata] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_by_identity", {entity.identity: entity for entity in self.entities}
        )

    def entity(self, identity: EntityIdentity) -> EntityMetadata | None:
        return self._by_identity.get(identity)


@dataclass(frozen=True, slots=True)
class _AcceptedMetamodel:
    metadata: CompiledMetadata
    facets: Mapping[FacetKey[Any], object]

    @property
    def entities(self) -> Sequence[EntityMetadata]:
        return self.metadata.entities

    def entity(self, identity: EntityIdentity) -> EntityMetadata | None:
        return self.metadata.entity(identity)

    def facet[T](self, key: FacetKey[T]) -> T:
        return cast(T, self.facets[key])


def compile_metadata(candidate: CandidateMetamodel) -> CompiledMetadata:
    """Compile an accepted candidate into the one immutable accepted graph."""
    return _CompiledMetadata(tuple(_entity_metadata(entity) for entity in candidate.entities))


def _entity_metadata(declaration: EntityDeclaration) -> EntityMetadata:
    return _EntityMetadata(
        identity=declaration.identity,
        declared_container=declaration.container,
        declared_persistence=declaration.persistence,
        declared_attributes=tuple(declaration.attributes),
        declared_relationships=tuple(declaration.relationships),
        declared_value_objects=tuple(
            _value_object_metadata(declaration.identity, occurrence)
            for occurrence in declaration.value_objects
        ),
        declared_as_of_axes=tuple(declaration.as_of_axes),
        inheritance=declaration.inheritance,
        indices=tuple(declaration.indices),
    )


def _value_object_metadata(
    entity: EntityIdentity, occurrence: ValueObjectOccurrenceDeclaration
) -> ValueObjectMetadata:
    identity = ValueObjectIdentity(entity, (occurrence.name,))
    attributes, nested = _expand_shape(entity, identity, occurrence.shape, frozenset())
    return _ValueObjectMetadata(
        identity=identity,
        storage=occurrence.storage,
        multiplicity=occurrence.multiplicity,
        nullable=occurrence.nullable,
        attributes=attributes,
        value_objects=nested,
    )


def _nested_value_object_metadata(
    entity: EntityIdentity,
    path: tuple[str, ...],
    occurrence: NestedValueObjectOccurrenceDeclaration,
    expanding: frozenset[ValueObjectShapeKey],
) -> NestedValueObjectMetadata:
    identity = ValueObjectIdentity(entity, path)
    attributes, nested = _expand_shape(entity, identity, occurrence.shape, expanding)
    return _NestedValueObjectMetadata(
        identity=identity,
        multiplicity=occurrence.multiplicity,
        nullable=occurrence.nullable,
        attributes=attributes,
        value_objects=nested,
    )


def _expand_shape(
    entity: EntityIdentity,
    identity: ValueObjectIdentity,
    shape: ValueObjectShapeDeclaration,
    expanding: frozenset[ValueObjectShapeKey],
) -> tuple[tuple[ValueObjectAttributeMetadata, ...], tuple[NestedValueObjectMetadata, ...]]:
    """One shape's members as path-identified Metadata, Shape Keys discarded.

    Reuse of one shape at several paths expands to distinct occurrence trees;
    reuse on a single path is a containment cycle ``m-value-object`` already
    rejected, so meeting one here is an impossible state.
    """
    if shape.key in expanding:
        raise RuntimeError(
            f"Value Object {identity.entity.canonical}.{'.'.join(identity.path)} "
            "expands a containment cycle that validation should have rejected"
        )
    below = expanding | {shape.key}
    attributes = tuple(
        _ValueObjectAttributeMetadata(
            identity=ValueObjectAttributeIdentity(identity, declared.name),
            type=declared.type,
            nullable=declared.nullable,
        )
        for declared in shape.attributes
    )
    nested = tuple(
        _nested_value_object_metadata(entity, (*identity.path, occurrence.name), occurrence, below)
        for occurrence in shape.value_objects
    )
    return attributes, nested


class MetamodelMetadataCompiler:
    """The one mandatory Metadata Compiler the Formation Manifest requires."""

    __slots__ = ()

    @property
    def owner(self) -> str:
        """The catalog identity that owns this compiler."""
        return METAMODEL_MODULE

    def compile(self, candidate: CandidateMetamodel) -> CompiledMetadata:
        """Compile ``candidate`` into Compiled Metadata, emitting no issues."""
        return compile_metadata(candidate)


METADATA_COMPILER: Final[MetamodelMetadataCompiler] = MetamodelMetadataCompiler()


def accept_metamodel(
    metadata: CompiledMetadata, facets: Mapping[FacetKey[Any], object]
) -> Metamodel:
    """Combine the exact Compiled Metadata graph with its complete facet set.

    The accepted Metamodel delegates lookup to that graph rather than copying or
    re-indexing it, and adds facet retrieval only. Retrieval is total for an
    accepted Formation Profile, which the formation runner establishes before
    any compiler runs.
    """
    return _AcceptedMetamodel(metadata, dict(facets))
