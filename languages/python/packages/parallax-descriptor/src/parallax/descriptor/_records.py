from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal

from parallax.core.metamodel import TemporalDimension as CanonicalTemporalDimension
from parallax.core.metamodel import default_column_name

__all__ = [
    "TEMPORAL_DIMENSIONS",
    "AsOfAxisMetadata",
    "Attribute",
    "DefiningRelationship",
    "DocumentLayout",
    "Entity",
    "Index",
    "Inheritance",
    "InheritanceRole",
    "Layout",
    "Metamodel",
    "Multiplicity",
    "NestedValueObject",
    "OrderByTerm",
    "Persistence",
    "PkGenerator",
    "PkStrategy",
    "RelationshipCardinality",
    "RelationshipDeclaration",
    "RelationshipJoin",
    "RelationshipTarget",
    "ReverseRelationship",
    "TemporalDimension",
    "Temporality",
    "ValueObject",
    "ValueObjectAttribute",
    "parent_identity",
]

Persistence = Literal["read-write", "read-only"]
"""The Persistence Mode an entity declares: whether Parallax accepts writes for
its family. Read Write is the semantic default a standalone entity or family
root falls back to when it declares none, so the two spellings are a declaration
and never a computed effective mode."""

Temporality = Literal["nontemporal", "transaction-time", "bitemporal"]
"""The Temporality Profile an entity declares: the temporal shape its family
carries. Every As-Of Axis, its two endpoint attributes, and their framework-fixed
columns are derived from it, so it is the only temporal fact a descriptor
spells."""

PkStrategy = Literal["none", "max", "sequence"]
RelationshipCardinality = Literal["one-to-one", "many-to-one", "one-to-many"]
Multiplicity = Literal["one", "many"]
TemporalDimension = Literal["valid-time", "transaction-time"]
InheritanceRole = Literal["root", "abstract-subtype", "concrete-subtype"]

TEMPORAL_DIMENSIONS: Final[Mapping[CanonicalTemporalDimension, TemporalDimension]] = (
    MappingProxyType(
        {
            CanonicalTemporalDimension.VALID_TIME: "valid-time",
            CanonicalTemporalDimension.TRANSACTION_TIME: "transaction-time",
        }
    )
)
"""How a descriptor spells each canonical Temporal Dimension."""


@dataclass(frozen=True, slots=True)
class PkGenerator:
    """A primary-key generation strategy (m-pk-gen)."""

    strategy: PkStrategy
    sequence_name: str | None = None
    batch_size: int | None = None
    initial_value: int | None = None
    increment_size: int | None = None


@dataclass(frozen=True, slots=True)
class Attribute:
    """A scalar entity attribute mapped to one physical column."""

    name: str
    type: str
    column: str
    primary_key: bool = False
    nullable: bool = False
    max_length: int | None = None
    read_only: bool = False
    optimistic_locking: bool = False
    pk_generator: PkGenerator | None = None


@dataclass(frozen=True, slots=True)
class OrderByTerm:
    """One ordering term of a to-many relationship.

    ``nulls`` is the authored Null Placement, independent of ``direction``; the
    descriptor's omitted spelling normalizes to ``last`` here, so a canonical
    export omits it again.
    """

    attr: str
    direction: Literal["asc", "desc"] = "asc"
    nulls: Literal["first", "last"] = "last"


@dataclass(frozen=True, slots=True)
class RelationshipTarget:
    """The sole target of a defining relationship join."""

    entity: str
    attribute: str


@dataclass(frozen=True, slots=True)
class RelationshipJoin:
    """One structured source-to-target attribute equality."""

    source: str
    target: RelationshipTarget


@dataclass(frozen=True, slots=True)
class DefiningRelationship:
    """The declaration that owns one association's mapping facts."""

    name: str
    cardinality: RelationshipCardinality
    join: RelationshipJoin
    dependent: bool = False
    order_by: tuple[OrderByTerm, ...] = ()


@dataclass(frozen=True, slots=True)
class ReverseRelationship:
    """A declaration that names, but does not repeat, a defining relationship."""

    name: str
    reverse_of: str
    order_by: tuple[OrderByTerm, ...] = ()


type RelationshipDeclaration = DefiningRelationship | ReverseRelationship


@dataclass(frozen=True, slots=True)
class Index:
    """A physical index over one or more attributes."""

    name: str
    attributes: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class AsOfAxisMetadata:
    """One canonical temporal dimension over two declared Attributes."""

    dimension: TemporalDimension
    start_attribute: str
    end_attribute: str


@dataclass(frozen=True, slots=True)
class Inheritance:
    """An entity's position in a closed inheritance tree (m-inheritance)."""

    role: InheritanceRole
    strategy: Literal["table-per-hierarchy", "table-per-concrete-subtype"] | None = None
    parent: str | None = None
    tag_column: str | None = None
    tag_value: str | None = None


@dataclass(frozen=True, slots=True)
class ValueObjectAttribute:
    """A typed field of a value object; carries no per-field column."""

    name: str
    type: str
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class NestedValueObject:
    """A value object nested inside another; shares the top-level column."""

    name: str
    nullable: bool = False
    multiplicity: Multiplicity = "one"
    attributes: tuple[ValueObjectAttribute, ...] = ()
    value_objects: tuple[NestedValueObject, ...] = ()


@dataclass(frozen=True, slots=True)
class ValueObject:
    """A top-level embedded composite stored in one ``json`` document column."""

    name: str
    column: str | None = None
    nullable: bool = False
    multiplicity: Multiplicity = "one"
    attributes: tuple[ValueObjectAttribute, ...] = ()
    value_objects: tuple[NestedValueObject, ...] = ()

    @property
    def storage_column(self) -> str:
        """The explicit column override or portable default for this occurrence."""
        return default_column_name(self.name) if self.column is None else self.column


@dataclass(frozen=True, slots=True)
class DocumentLayout:
    """One shared Structured Column carrying the mapping's document-resident state.

    The column name is required here because the canonical descriptor always
    carries the resolved one: a frontend that supplies a conventional name the
    author omitted resolves it before export.
    """

    column: str


type Layout = DocumentLayout
"""The Storage Layout an entity declares. Conventional Columns storage has no
spelling — omitting `layout` is what selects it — so the only member is the
document form."""


@dataclass(frozen=True, slots=True)
class Entity:
    """One mapped entity: identity, attributes, temporal dimensions, and relations.

    ``persistence`` is the mode this entity *declares*, and ``None`` records that
    it declared none. The distinction is load-bearing: Persistence is family-wide
    and root-owned, so absence on a standalone entity or a family root means the
    Read Write default while absence on a descendant means inherit — and a
    descendant that declares any mode at all is invalid. Normalizing an omitted
    property to the default would erase the only evidence of that.

    ``layout`` and ``temporality`` read the same way and for the same reason:
    each is family-wide and root-owned, and ``None`` is both the root's default
    — Columns storage, Non-Temporal — and the inherit signal on a descendant.

    ``attributes`` and ``as_of_axes`` are the *derived* temporal structure once
    ``temporality`` names a profile: the two endpoint attributes per axis follow
    every authored attribute, and the axes reference them. Nothing else in the
    record distinguishes a derived member from an authored one, because past
    this point nothing needs to.
    """

    name: str
    namespace: str | None = None
    table: str | None = None
    persistence: Persistence | None = None
    layout: Layout | None = None
    temporality: Temporality | None = None
    attributes: tuple[Attribute, ...] = ()
    as_of_axes: tuple[AsOfAxisMetadata, ...] = ()
    relationships: tuple[RelationshipDeclaration, ...] = ()
    indices: tuple[Index, ...] = ()
    value_objects: tuple[ValueObject, ...] = ()
    inheritance: Inheritance | None = None

    @property
    def canonical_name(self) -> str:
        """The exact Entity spelling used for model-wide identity and lookup."""
        return self.name if self.namespace is None else f"{self.namespace}.{self.name}"


def parent_identity(entity: Entity, parent: str | None) -> str | None:
    """The CANONICAL name a ``parent`` reference authored on ``entity`` names,
    or ``None`` when it names nothing.

    A dot-qualified reference is exact and a bare one is relative to the
    declaring entity's own namespace (`m-metamodel` "References and foundational
    resolution"). There is no model-wide unique-name fallback, so a bare parent
    never reaches a same-named entity of another namespace.
    """
    if parent is None or entity.namespace is None or "." in parent:
        return parent
    return f"{entity.namespace}.{parent}"


@dataclass(frozen=True, slots=True)
class Metamodel:
    """A parsed model descriptor: one or more mapped entities."""

    entities: tuple[Entity, ...] = field(default_factory=tuple)

    @property
    def by_name(self) -> dict[str, Entity]:
        """Entities keyed by exact identity plus only unambiguous local aliases."""
        result = {entity.canonical_name: entity for entity in self.entities}
        local_counts: dict[str, int] = {}
        for entity in self.entities:
            local_counts[entity.name] = local_counts.get(entity.name, 0) + 1
        for entity in self.entities:
            if local_counts[entity.name] == 1:
                result[entity.name] = entity
        return result

    def entity(self, name: str) -> Entity:
        """The entity named ``name`` (raises ``KeyError`` when absent)."""
        return self.by_name[name]
