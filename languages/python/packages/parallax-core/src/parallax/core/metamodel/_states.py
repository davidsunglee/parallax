"""The formation-state and accepted-metadata protocol family (m-metamodel).

Formation is the gated progression ``UnresolvedMetamodel -> CandidateMetamodel
-> Metamodel``, and each state exposes strictly more capability than the last:
enumeration only, then canonical enumeration with total Entity lookup, then
accepted Metadata with local member lookup and typed facets. Protocols here
prescribe no concrete class or storage layout, so a frontend may satisfy them
with its own read-only objects rather than mirroring a record graph. They are
deliberately not ``runtime_checkable``: structural conformance is a static
guarantee, and a presence check over data members would not be sound.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, TypeGuard

from parallax.core.base import NeutralType
from parallax.core.metamodel._identities import (
    EntityIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.metamodel._values import (
    AsOfAxisMetadata,
    AttributeMetadata,
    IndexMetadata,
    InheritanceMetadata,
    Multiplicity,
    PersistenceMode,
    RelationshipDeclaration,
    StorageContainer,
    StorageLocation,
    TemporalDimension,
    UnresolvedInheritance,
    UnresolvedRelationshipDeclaration,
    ValueObjectOccurrenceDeclaration,
)

__all__ = [
    "CandidateMetamodel",
    "CompiledMetadata",
    "EntityDeclaration",
    "EntityMetadata",
    "FacetKey",
    "Metamodel",
    "NestedValueObjectMetadata",
    "UnresolvedEntityDeclaration",
    "UnresolvedMetamodel",
    "ValueObjectAttributeMetadata",
    "ValueObjectMetadata",
]


class UnresolvedEntityDeclaration(Protocol):
    """One Entity exactly as a frontend declares it.

    The shape is shallow and entirely local: no inherited member, effective
    view, facet, lookup, or behavioral authority. Reference-free facts reuse
    their final Metadata types, and only relationship, Value Object occurrence,
    and inheritance facts have separate Declaration types because they carry
    unresolved references or occurrence-relative identities.
    """

    @property
    def identity(self) -> EntityIdentity: ...
    @property
    def container(self) -> StorageContainer | None: ...
    @property
    def persistence(self) -> PersistenceMode | None: ...
    @property
    def attributes(self) -> Sequence[AttributeMetadata]: ...
    @property
    def relationships(self) -> Sequence[UnresolvedRelationshipDeclaration]: ...
    @property
    def value_objects(self) -> Sequence[ValueObjectOccurrenceDeclaration]: ...
    @property
    def as_of_axes(self) -> Sequence[AsOfAxisMetadata]: ...
    @property
    def inheritance(self) -> UnresolvedInheritance | None: ...
    @property
    def indices(self) -> Sequence[IndexMetadata]: ...


class UnresolvedMetamodel(Protocol):
    """The nonempty enumeration-only frontend view formation begins from.

    Duplicate identities are legal input, there is no lookup or uniqueness
    promise, and the outer order is diagnostic only. Every frontend rejects an
    empty source before this seam.
    """

    @property
    def entities(self) -> Sequence[UnresolvedEntityDeclaration]: ...


class EntityDeclaration(Protocol):
    """One Entity whose relationship and inheritance references are Identities.

    Resolution advances references and nothing else: the Value Object
    occurrence graph, every local sequence order, and the defining-versus-
    reverse relationship union are unchanged, and the shape still exposes no
    lookup, effective view, facet, or behavior.
    """

    @property
    def identity(self) -> EntityIdentity: ...
    @property
    def container(self) -> StorageContainer | None: ...
    @property
    def persistence(self) -> PersistenceMode | None: ...
    @property
    def attributes(self) -> Sequence[AttributeMetadata]: ...
    @property
    def relationships(self) -> Sequence[RelationshipDeclaration]: ...
    @property
    def value_objects(self) -> Sequence[ValueObjectOccurrenceDeclaration]: ...
    @property
    def as_of_axes(self) -> Sequence[AsOfAxisMetadata]: ...
    @property
    def inheritance(self) -> InheritanceMetadata | None: ...
    @property
    def indices(self) -> Sequence[IndexMetadata]: ...


class CandidateMetamodel(Protocol):
    """The only state a semantic Rule Set validates.

    It exists solely because foundational resolution succeeded. Enumeration is
    canonical Entity Identity order and lookup is total, nonthrowing, and
    expected amortized ``O(1)``; a miss returns absence.
    """

    @property
    def entities(self) -> Sequence[EntityDeclaration]: ...
    def entity(self, identity: EntityIdentity) -> EntityDeclaration | None: ...


class ValueObjectAttributeMetadata(Protocol):
    """One self-identifying scalar leaf of a Value Object occurrence.

    A leaf carries no Entity-only storage, primary-key, generation, locking, or
    container fact.
    """

    @property
    def identity(self) -> ValueObjectAttributeIdentity: ...
    @property
    def type(self) -> NeutralType: ...
    @property
    def nullable(self) -> bool: ...


class NestedValueObjectMetadata(Protocol):
    """One self-identifying nested Value Object occurrence.

    Its identity path has length two or more. A nested occurrence owns no
    Storage Location: the top-level occurrence's location covers the whole
    composite.
    """

    @property
    def identity(self) -> ValueObjectIdentity: ...
    @property
    def multiplicity(self) -> Multiplicity: ...
    @property
    def nullable(self) -> bool: ...
    @property
    def attributes(self) -> Sequence[ValueObjectAttributeMetadata]: ...
    @property
    def value_objects(self) -> Sequence[NestedValueObjectMetadata]: ...
    def attribute(self, name: str) -> ValueObjectAttributeMetadata | None: ...
    def value_object(self, name: str) -> NestedValueObjectMetadata | None: ...


class ValueObjectMetadata(Protocol):
    """One self-identifying top-level Value Object occurrence.

    Its identity path has length one, and it alone carries the occurrence's
    Storage Location. Structured-column storage under that location is
    intrinsic, so there is no mapping discriminator and no Value Object-specific
    cardinality algebra.
    """

    @property
    def identity(self) -> ValueObjectIdentity: ...
    @property
    def storage(self) -> StorageLocation: ...
    @property
    def multiplicity(self) -> Multiplicity: ...
    @property
    def nullable(self) -> bool: ...
    @property
    def attributes(self) -> Sequence[ValueObjectAttributeMetadata]: ...
    @property
    def value_objects(self) -> Sequence[NestedValueObjectMetadata]: ...
    def attribute(self, name: str) -> ValueObjectAttributeMetadata | None: ...
    def value_object(self, name: str) -> NestedValueObjectMetadata | None: ...


class EntityMetadata(Protocol):
    """One Entity's accepted local declaration view.

    Every property whose effective value may differ through inheritance carries
    the ``declared_`` qualifier, and no unqualified effective-looking alias
    exists; owner modules expose contextual effective views through compiled
    facets. Lookup is local-only, total, nonthrowing, and expected amortized
    ``O(1)``, and never exposes an inherited member.
    """

    @property
    def identity(self) -> EntityIdentity: ...
    @property
    def declared_container(self) -> StorageContainer | None: ...
    @property
    def declared_persistence(self) -> PersistenceMode | None: ...
    @property
    def declared_attributes(self) -> Sequence[AttributeMetadata]: ...
    @property
    def declared_relationships(self) -> Sequence[RelationshipDeclaration]: ...
    @property
    def declared_value_objects(self) -> Sequence[ValueObjectMetadata]: ...
    @property
    def declared_as_of_axes(self) -> Sequence[AsOfAxisMetadata]: ...
    @property
    def inheritance(self) -> InheritanceMetadata | None: ...
    @property
    def indices(self) -> Sequence[IndexMetadata]: ...
    def attribute(self, name: str) -> AttributeMetadata | None: ...
    def relationship(self, name: str) -> RelationshipDeclaration | None: ...
    def value_object(self, name: str) -> ValueObjectMetadata | None: ...
    def as_of_axis(self, dimension: TemporalDimension) -> AsOfAxisMetadata | None: ...
    def index(self, name: str) -> IndexMetadata | None: ...


class CompiledMetadata(Protocol):
    """The one immutable accepted Entity graph one formation produces.

    It owns the canonical Entity sequence and every immutable index accepted
    local lookup uses. Nothing downstream reconstructs it or builds a second
    normalized index over it.
    """

    @property
    def entities(self) -> Sequence[EntityMetadata]: ...
    def entity(self, identity: EntityIdentity) -> EntityMetadata | None: ...


@dataclass(frozen=True, slots=True)
class FacetKey[T]:
    """The typed key one compiling module's facet is installed and retrieved under.

    Identity is the owning module's catalog identity alone, so a module owns
    exactly one key and two keys naming one owner are the same key. The type
    parameter carries the facet's type through :meth:`Metamodel.facet` and is
    erased at run time, so ``accepts`` is its run-time counterpart: the owner's
    own decision procedure for "is this value my facet?", which the formation
    seam calls on whatever a compiler returned before installing it. Only the
    owner can answer that — a facet may be a Protocol, and no generic check can
    see through the erased parameter — so supplying ``accepts`` is part of
    declaring a key, and a value it rejects is a compiler contract failure.
    ``accepts`` never participates in equality or hashing, so an equal key may
    carry any check at all; the seam therefore calls the check on the key its own
    authoritative declaration holds, never one a contributor handed it.
    """

    owner: str
    accepts: Callable[[object], TypeGuard[T]] = field(compare=False)


class Metamodel(Protocol):
    """The accepted model: Compiled Metadata plus its complete facet set.

    It exists only after every formation rule succeeded and every compiler ran,
    and it is not a subtype of either formation input. ``facet`` is total for an
    accepted Formation Profile and is an internal collaboration seam — each
    owning module exposes its facet through a typed ``view(model)`` function
    instead.
    """

    @property
    def entities(self) -> Sequence[EntityMetadata]: ...
    def entity(self, identity: EntityIdentity) -> EntityMetadata | None: ...
    def facet[T](self, key: FacetKey[T]) -> T: ...
