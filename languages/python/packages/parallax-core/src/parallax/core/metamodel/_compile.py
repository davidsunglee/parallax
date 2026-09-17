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
from types import MappingProxyType
from typing import Any, Final, TypeGuard, cast, overload

from parallax.core.base import NeutralType
from parallax.core.metamodel._identities import (
    EntityIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.metamodel._issues import METAMODEL_MODULE
from parallax.core.metamodel._shape import Leaf, MemberShape, Occurrence
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
    StorageLayout,
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
    "is_compiled_metadata",
    "value_object_metadata",
]


@dataclass(frozen=True, slots=True)
class _ValueObjectAttributeMetadata:
    identity: ValueObjectAttributeIdentity
    definition: Leaf

    @property
    def type(self) -> NeutralType:
        return self.definition.type

    @property
    def nullable(self) -> bool:
        return self.definition.nullable


type _BoundMember = ValueObjectAttributeMetadata | NestedValueObjectMetadata


@dataclass(frozen=True, slots=True)
class _BindingRange[T](Sequence[T]):
    bindings: tuple[_BoundMember, ...]
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


@dataclass(frozen=True, slots=True)
class _OccurrenceMetadata:
    """Everything a top-level and a nested Value Object occurrence hold alike.

    The two Metadata shapes differ in exactly one fact — the Storage Location a
    top-level occurrence owns and a nested one cannot — so the members they
    share, including their local member indexes, are declared once here. This is
    shared implementation between two private classes and not a relation between
    the protocols they satisfy: neither occurrence protocol is a subtype of the
    other, and a consumer holding a nested occurrence still has no ``storage`` to
    read.

    Each index is installed as a read-only view over a mapping nothing else
    holds, so accepted lookup state is unreachable for mutation.
    """

    identity: ValueObjectIdentity
    definition: Occurrence
    members: tuple[_BoundMember, ...]
    _attributes: _BindingRange[ValueObjectAttributeMetadata] = field(
        init=False, repr=False, compare=False
    )
    _value_objects: _BindingRange[NestedValueObjectMetadata] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        leaf_count = sum(isinstance(member.definition, Leaf) for member in self.members)
        object.__setattr__(
            self,
            "_attributes",
            _BindingRange(self.members, 0, leaf_count),
        )
        object.__setattr__(
            self,
            "_value_objects",
            _BindingRange(self.members, leaf_count, len(self.members)),
        )

    @property
    def multiplicity(self) -> Multiplicity:
        return self.definition.multiplicity

    @property
    def nullable(self) -> bool:
        return self.definition.nullable

    @property
    def attributes(self) -> Sequence[ValueObjectAttributeMetadata]:
        return self._attributes

    @property
    def value_objects(self) -> Sequence[NestedValueObjectMetadata]:
        return self._value_objects

    @property
    def document_shape(self) -> MemberShape:
        return self.definition.shape

    def attribute(self, name: str) -> ValueObjectAttributeMetadata | None:
        position = self.definition.shape.position(name)
        if position is None or not isinstance(self.definition.shape.members[position], Leaf):
            return None
        return cast("ValueObjectAttributeMetadata", self.members[position])

    def value_object(self, name: str) -> NestedValueObjectMetadata | None:
        position = self.definition.shape.position(name)
        if position is None or not isinstance(self.definition.shape.members[position], Occurrence):
            return None
        return cast("NestedValueObjectMetadata", self.members[position])


@dataclass(frozen=True, slots=True)
class _NestedValueObjectMetadata(_OccurrenceMetadata):
    """One nested occurrence: the shared surface, owning no Storage Location."""


@dataclass(frozen=True, slots=True)
class _ValueObjectMetadata(_OccurrenceMetadata):
    """One top-level occurrence: the shared surface plus the location it owns."""

    storage: StorageLocation


@dataclass(frozen=True, slots=True)
class _EntityMetadata:
    identity: EntityIdentity
    declared_container: StorageContainer | None
    declared_persistence: PersistenceMode | None
    declared_layout: StorageLayout | None
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
            MappingProxyType({member.identity.name: member for member in self.declared_attributes}),
        )
        object.__setattr__(
            self,
            "_relationship_index",
            MappingProxyType(
                {member.identity.name: member for member in self.declared_relationships}
            ),
        )
        object.__setattr__(
            self,
            "_value_object_index",
            MappingProxyType(
                {member.identity.path[-1]: member for member in self.declared_value_objects}
            ),
        )
        object.__setattr__(
            self,
            "_axis_index",
            MappingProxyType({axis.dimension: axis for axis in self.declared_as_of_axes}),
        )
        object.__setattr__(
            self,
            "_index_index",
            MappingProxyType({member.identity.name: member for member in self.indices}),
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
            self,
            "_by_identity",
            MappingProxyType({entity.identity: entity for entity in self.entities}),
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


def is_compiled_metadata(value: object) -> TypeGuard[CompiledMetadata]:
    """Whether ``value`` is Compiled Metadata this module's compiler produced.

    ``m-metamodel`` owns the mandatory Metadata Compiler and this is its only
    output type, so provenance decides rather than the surface a value presents.
    Compilation runs only on an accepted candidate, which is nonempty, so an
    Entity-less graph is an impossible state rather than a model with nothing in
    it.

    Exists for the seam that receives a compiler's result and must classify a
    wrong-typed one as a contract failure rather than publish it as a Metamodel.
    """
    return isinstance(value, _CompiledMetadata) and bool(value.entities)


def _entity_metadata(declaration: EntityDeclaration) -> EntityMetadata:
    return _EntityMetadata(
        identity=declaration.identity,
        declared_container=declaration.container,
        declared_persistence=declaration.persistence,
        declared_layout=declaration.layout,
        declared_attributes=tuple(declaration.attributes),
        declared_relationships=tuple(declaration.relationships),
        declared_value_objects=tuple(
            value_object_metadata(declaration.identity, occurrence)
            for occurrence in declaration.value_objects
        ),
        declared_as_of_axes=tuple(declaration.as_of_axes),
        inheritance=declaration.inheritance,
        indices=tuple(declaration.indices),
    )


def value_object_metadata(
    entity: EntityIdentity, occurrence: ValueObjectOccurrenceDeclaration
) -> ValueObjectMetadata:
    """One top-level occurrence declaration expanded into path-identified Metadata.

    Expansion is a pure reading of the declaration — it decides no validity and
    consults no other Entity — so a frontend holding one declared occurrence can
    obtain its Metadata without a model. Compilation reaches the same function for
    every occurrence of every Entity it accepts, which is what keeps the shape a
    descriptor carries identical to the one the accepted model publishes.
    """
    identity = ValueObjectIdentity(entity, (occurrence.name,))
    members = _bind_shape(entity, identity, occurrence.shape, frozenset())
    return _ValueObjectMetadata(
        identity=identity,
        storage=occurrence.storage,
        definition=occurrence.definition,
        members=members,
    )


def _nested_value_object_metadata(
    entity: EntityIdentity,
    path: tuple[str, ...],
    occurrence: NestedValueObjectOccurrenceDeclaration,
    expanding: frozenset[ValueObjectShapeKey],
) -> NestedValueObjectMetadata:
    identity = ValueObjectIdentity(entity, path)
    members = _bind_shape(entity, identity, occurrence.shape, expanding)
    return _NestedValueObjectMetadata(
        identity=identity,
        definition=occurrence.definition,
        members=members,
    )


def _bind_shape(
    entity: EntityIdentity,
    identity: ValueObjectIdentity,
    shape: ValueObjectShapeDeclaration,
    expanding: frozenset[ValueObjectShapeKey],
) -> tuple[_BoundMember, ...]:
    """One shape's definitions bound to path identities, Shape Keys discarded.

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
    attributes: tuple[_BoundMember, ...] = tuple(
        _ValueObjectAttributeMetadata(
            identity=ValueObjectAttributeIdentity(identity, declared.name),
            definition=declared.definition,
        )
        for declared in shape.attributes
    )
    nested: tuple[_BoundMember, ...] = tuple(
        _nested_value_object_metadata(entity, (*identity.path, occurrence.name), occurrence, below)
        for occurrence in shape.value_objects
    )
    return attributes + nested


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
"""The single Metadata Compiler instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the compiler rather than constructing a second one."""


def accept_metamodel(
    metadata: CompiledMetadata, facets: Mapping[FacetKey[Any], object]
) -> Metamodel:
    """Combine the exact Compiled Metadata graph with its complete facet set.

    The accepted Metamodel delegates lookup to that graph rather than copying or
    re-indexing it, and adds facet retrieval only. Retrieval is total for an
    accepted Formation Profile, which the formation runner establishes before
    any compiler runs. The facet mapping is snapshotted into a read-only view, so
    a caller that keeps its own mapping cannot alter an accepted model's facets.
    """
    return _AcceptedMetamodel(metadata, MappingProxyType(dict(facets)))
