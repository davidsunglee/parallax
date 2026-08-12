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
    StorageLayout,
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
    "ambiguous_entity_spellings",
    "entity_by_name",
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
    def layout(self) -> StorageLayout | None: ...
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
    def layout(self) -> StorageLayout | None: ...
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
    def declared_layout(self) -> StorageLayout | None: ...
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


def entity_by_name(model: Metamodel, name: str) -> EntityMetadata | None:
    """The accepted Metadata a bare-or-canonical Entity spelling names within
    ``model``, or ``None`` when it names none — rejecting an ambiguous bare name.

    An exact canonical spelling (``<namespace>.<name>``, or a bare ``<name>`` for
    an ownerless Entity) matches that Entity. A bare local name matches only when
    exactly one Entity carries it; a bare name two Entities share across distinct
    namespaces is ambiguous and misses, never a silent first match. This is the
    accepted-model counterpart of a descriptor record graph's own by-name lookup,
    so a frontend resolving a spelling against a bare accepted model agrees with
    one resolving through a scoped record graph. A free utility over the protocol,
    never a protocol method: the accepted ``Metamodel`` seam itself stays
    Identity-keyed and accepts no name string.

    This is the rule for an Entity spelling in a REFERENCE position — a
    predicate's, a query's, or a write instruction's — and the only one:
    validation and lowering both resolve such a spelling here, which is what
    makes "preflight accepted this reference" imply "lowering resolves it".
    :func:`~parallax.core.metamodel.resolve_entity_reference` is the DECLARATION
    rule and answers a different question — what a reference means where it was
    declared — so it never adjudicates a reference position.
    """
    bare: EntityMetadata | None = None
    bare_matches = 0
    for entity in model.entities:
        identity = entity.identity
        if identity.canonical == name:
            return entity
        if identity.name == name:
            bare = entity
            bare_matches += 1
    return bare if bare_matches == 1 else None


def ambiguous_entity_spellings(model: Metamodel, name: str) -> tuple[str, ...]:
    """The sorted canonical spellings ``name`` is shared by when it is a bare
    local name two or more namespaces of ``model`` declare, and the empty tuple
    when it names at most one Entity.

    This classifies :func:`entity_by_name`'s miss, which answers two different
    mistakes the same way: a spelling that resolves nowhere because it is shared,
    and one that resolves nowhere because the model does not declare it at all.
    Every boundary telling those apart asks here and raises its OWN carrier — the
    normative `reference-ambiguous-entity-name` refusal in the vocabulary that
    boundary reports in — so the classification and the sorted spellings a
    refusal names exist once while no carrier is imposed on any caller.

    Reached through this defining module by each boundary that needs it rather
    than through the package's public surface: it composes a refusal's message
    from a miss :func:`entity_by_name` already reported, so it is a collaboration
    between first-party boundaries and no part of what a developer resolves a
    spelling with.
    """
    shared = sorted(
        entity.identity.canonical for entity in model.entities if entity.identity.name == name
    )
    return tuple(shared) if len(shared) > 1 else ()
