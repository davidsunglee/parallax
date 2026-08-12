"""Closed metadata vocabularies and leaf metadata shapes (m-metamodel).

The value layer both formation inputs and accepted Metadata share. Two
spellings carry the closed algebras: an ``enum.Enum`` for a set whose members
carry no payload, and one frozen dataclass per variant behind a ``type`` alias
where any member does — with a module-level singleton for that union's nullary
members. Invalid payloads raise at construction, so an unrepresentable model
fact never reaches a consumer.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Final

from parallax.core.base import NeutralType, String
from parallax.core.metamodel._identities import (
    AttributeIdentity,
    AttributeReference,
    EntityIdentity,
    EntityReference,
    IndexIdentity,
    RelationshipIdentity,
    RelationshipReference,
)

__all__ = [
    "APPLICATION_ASSIGNED",
    "COLUMNS",
    "MAX",
    "NOT_PRIMARY_KEY",
    "TABLE_PER_CONCRETE_SUBTYPE",
    "AbstractRoot",
    "AbstractSubtype",
    "ApplicationAssigned",
    "AsOfAxisMetadata",
    "AttributeMetadata",
    "AttributePrimaryKey",
    "Cardinality",
    "Column",
    "Columns",
    "ConcreteSubtype",
    "DefiningRelationshipDeclaration",
    "Document",
    "IndexMetadata",
    "Inheritance",
    "InheritanceMetadata",
    "InheritanceStrategy",
    "Max",
    "Multiplicity",
    "NestedValueObjectOccurrenceDeclaration",
    "NotPrimaryKey",
    "NullPlacement",
    "PersistenceMode",
    "PkGeneration",
    "PrimaryKey",
    "RelationshipDeclaration",
    "RelationshipJoin",
    "RelationshipOrder",
    "ReverseRelationshipDeclaration",
    "Sequence",
    "SortDirection",
    "StorageContainer",
    "StorageLayout",
    "StorageLocation",
    "Table",
    "TablePerConcreteSubtype",
    "TablePerHierarchy",
    "TemporalDimension",
    "UnresolvedDefiningRelationshipDeclaration",
    "UnresolvedInheritance",
    "UnresolvedRelationshipDeclaration",
    "UnresolvedRelationshipJoin",
    "UnresolvedRelationshipOrder",
    "UnresolvedReverseRelationshipDeclaration",
    "ValueObjectAttributeDeclaration",
    "ValueObjectOccurrenceDeclaration",
    "ValueObjectShapeDeclaration",
    "ValueObjectShapeKey",
]


class PersistenceMode(enum.Enum):
    """Whether Parallax accepts persistence writes for an Entity family.

    Unrelated to in-memory mutation, security policy, Transaction Time, or
    Unit-of-Work demarcation. ``READ_WRITE`` is the standalone and root default.
    """

    READ_WRITE = enum.auto()
    READ_ONLY = enum.auto()


class Multiplicity(enum.Enum):
    """The shared one/many algebra used by relationship sides and Value Objects."""

    ONE = enum.auto()
    MANY = enum.auto()


class SortDirection(enum.Enum):
    """The ordering direction shared by relationship order and Object Query Sort Keys."""

    ASCENDING = enum.auto()
    DESCENDING = enum.auto()


class NullPlacement(enum.Enum):
    """Where NULLs sort on one ordering key, independent of its Sort Direction.

    NULLS_LAST is the canonical placement in either direction, so an authoring
    frontend that omits placement normalizes to it. The two members denote an
    observable order only on a nullable Attribute.
    """

    NULLS_FIRST = enum.auto()
    NULLS_LAST = enum.auto()


class TemporalDimension(enum.Enum):
    """The closed temporal axis vocabulary.

    Member values are the canonical axis rank — Valid Time precedes Transaction
    Time wherever axes are ordered, including canonical issue ordering.
    """

    VALID_TIME = 0
    TRANSACTION_TIME = 1


class Cardinality(enum.Enum):
    """Direct relationship cardinality as source and target Multiplicity.

    Direct many-to-many is absent by construction; that model shape is an
    explicit association Entity with two relationships.
    """

    ONE_TO_ONE = enum.auto()
    MANY_TO_ONE = enum.auto()
    ONE_TO_MANY = enum.auto()

    @property
    def source(self) -> Multiplicity:
        """The declaring side's Multiplicity."""
        return Multiplicity.MANY if self is Cardinality.MANY_TO_ONE else Multiplicity.ONE

    @property
    def target(self) -> Multiplicity:
        """The referenced side's Multiplicity."""
        return Multiplicity.MANY if self is Cardinality.ONE_TO_MANY else Multiplicity.ONE


@dataclass(frozen=True, slots=True)
class Table:
    """An Entity's physical table; an empty name raises :class:`ValueError`."""

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a Table name is nonempty")


type StorageContainer = Table
"""The Entity-wide physical container. The reserved ``DocumentCollection``
variant is not constructible in this contract."""


@dataclass(frozen=True, slots=True)
class Column:
    """A mapped top-level member's physical column; an empty name raises
    :class:`ValueError`."""

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a Column name is nonempty")


type StorageLocation = Column
"""A mapped top-level member's physical placement. It never repeats the
container, and the reserved ``ContainerDocument`` variant is not constructible.

A Document Path is not a Storage Location: it is derived by
``m-storage-layout`` from the accepted model rather than declared, so no member
carries one here under any layout."""


@dataclass(frozen=True, slots=True)
class Columns:
    """Conventional layout: each mapped Attribute owns its own Column and each
    top-level Value Object occurrence its own Structured Column."""


# The shared :class:`Columns` instance, on the same value-object terms.
COLUMNS: Final[Columns] = Columns()


@dataclass(frozen=True, slots=True)
class Document:
    """Relational Document Layout: one shared Structured Column carries every
    document-resident member of the governed rows.

    ``column`` is always resolved — a frontend may supply a conventional name the
    author omitted, but no accepted layout value carries an unresolved one.
    """

    column: Column


type StorageLayout = Columns | Document
"""The root-owned physical mapping policy of one independent mapping owner.

Only a standalone Entity or a family root declares it, and a descendant's
declaration is a family-invariant rejection rather than an override. ``Columns``
has no authoring spelling: declaring nothing selects it."""


@dataclass(frozen=True, slots=True)
class ApplicationAssigned:
    """The application supplies the key value."""


# The shared instance of the nullary variant above. Variants are frozen value
# objects, so this is an allocation convenience rather than an identity: a fresh
# ``ApplicationAssigned()`` equals it and matches the same patterns.
APPLICATION_ASSIGNED: Final[ApplicationAssigned] = ApplicationAssigned()


@dataclass(frozen=True, slots=True)
class Max:
    """The framework allocates from the stored maximum key."""


# The shared :class:`Max` instance, on the same value-object terms.
MAX: Final[Max] = Max()


@dataclass(frozen=True, slots=True)
class Sequence:
    """The framework allocates from a named database sequence in batches.

    Every parameter is complete at this seam: descriptor omissions are replaced
    by their semantic defaults before acceptance. An empty name, or a
    nonpositive batch or increment size, raises :class:`ValueError`; the initial
    value is unconstrained.
    """

    name: str
    batch_size: int = 1
    initial_value: int = 1
    increment_size: int = 1

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a Sequence name is nonempty")
        if self.batch_size < 1:
            raise ValueError(f"a Sequence batch size is positive, got {self.batch_size}")
        if self.increment_size < 1:
            raise ValueError(f"a Sequence increment size is positive, got {self.increment_size}")


type PkGeneration = ApplicationAssigned | Max | Sequence
"""The normalized primary-key generation algebra."""


@dataclass(frozen=True, slots=True)
class NotPrimaryKey:
    """The Attribute is not part of its Entity's primary key."""


# The shared :class:`NotPrimaryKey` instance, on the same value-object terms.
NOT_PRIMARY_KEY: Final[NotPrimaryKey] = NotPrimaryKey()


@dataclass(frozen=True, slots=True)
class PrimaryKey:
    """The Attribute is the Entity's primary key, with its generation."""

    generation: PkGeneration = APPLICATION_ASSIGNED


type AttributePrimaryKey = NotPrimaryKey | PrimaryKey
"""An Attribute's primary-key state. Generation lives only on the key branch,
so a non-key Attribute cannot carry a meaningless generation value."""


@dataclass(frozen=True, slots=True)
class TablePerHierarchy:
    """One shared family table discriminated by a framework-owned tag column.

    The tag column is a plain physical name rather than a Storage Location: it
    holds no mapped model member, so nothing addresses it by member identity.
    An empty name raises :class:`ValueError`.
    """

    tag_column: str

    def __post_init__(self) -> None:
        if not self.tag_column:
            raise ValueError("a table-per-hierarchy tag column is nonempty")


@dataclass(frozen=True, slots=True)
class TablePerConcreteSubtype:
    """One table per concrete subtype; abstract positions are tableless."""


# The shared :class:`TablePerConcreteSubtype` instance, on the same
# value-object terms.
TABLE_PER_CONCRETE_SUBTYPE: Final[TablePerConcreteSubtype] = TablePerConcreteSubtype()

type InheritanceStrategy = TablePerHierarchy | TablePerConcreteSubtype
"""The root-owned physical mapping strategy for an inheritance family."""


@dataclass(frozen=True, slots=True)
class AbstractRoot:
    """The rowless root of a closed family; it alone declares the strategy."""

    strategy: InheritanceStrategy


@dataclass(frozen=True, slots=True)
class AbstractSubtype[Parent]:
    """A rowless intermediate position under ``parent``."""

    parent: Parent


@dataclass(frozen=True, slots=True)
class ConcreteSubtype[Parent]:
    """A row-bearing position under ``parent``, tagged under a hierarchy strategy.

    A tag value is either absent or nonempty, so the two spellings of "no tag"
    cannot both exist; an empty tag value raises :class:`ValueError`. Whether
    absence is legal depends on the root's strategy, which a family-wide rule
    decides rather than this variant.
    """

    parent: Parent
    tag_value: str | None = None

    def __post_init__(self) -> None:
        if self.tag_value is not None and not self.tag_value:
            raise ValueError("a Concrete Subtype tag value is either absent or nonempty")


type Inheritance[Parent] = AbstractRoot | AbstractSubtype[Parent] | ConcreteSubtype[Parent]
"""The parent-parameterized inheritance algebra; the variant is the role, so no
parallel role field exists and no descendant copies the root strategy."""

type InheritanceMetadata = Inheritance[EntityIdentity]
"""Inheritance whose parent reference has been resolved."""

type UnresolvedInheritance = Inheritance[EntityReference]
"""Inheritance as a frontend declares it."""


def inheritance_parent[Parent](inheritance: Inheritance[Parent] | None) -> Parent | None:
    """The parent reference this inheritance position extends, or ``None``.

    An absent inheritance (a standalone Entity) and an :class:`AbstractRoot`
    extend nothing; an :class:`AbstractSubtype` and a :class:`ConcreteSubtype`
    extend the parent they carry. The variant is the role, so the parent reads
    off the algebra without a separate role field. Resolved and unresolved
    inheritance share the walk, so ``Parent`` is an ``EntityIdentity`` or an
    ``EntityReference`` respectively.
    """
    match inheritance:
        case None | AbstractRoot():
            return None
        case AbstractSubtype(parent) | ConcreteSubtype(parent, _):
            return parent


@dataclass(frozen=True, slots=True)
class AttributeMetadata:
    """One self-identifying scalar Attribute.

    Reference-free, so a frontend supplies it unchanged at the Unresolved seam
    and accepted Metadata reuses it. It duplicates neither its own name nor its
    Entity's container. A maximum length bounds text width, so it is either
    absent or a positive length on a String Attribute; a nonpositive length, or
    one on any other type, raises :class:`ValueError`. Both constraints are local
    to one Attribute, so no Rule Set owns them.

    ``framework_owned`` answers who supplies the value — the framework, never
    the caller — and is derived rather than authored, by
    :func:`designate_framework_owned`. It carries no local invariant, because
    the fact is a function of the Entity as well as the Attribute and so cannot
    be checked from here.
    """

    identity: AttributeIdentity
    type: NeutralType
    storage: StorageLocation
    primary_key: AttributePrimaryKey = NOT_PRIMARY_KEY
    nullable: bool = False
    max_length: int | None = None
    read_only: bool = False
    optimistic_locking: bool = False
    framework_owned: bool = False

    def __post_init__(self) -> None:
        if self.max_length is None:
            return
        if self.max_length < 1:
            raise ValueError(f"an Attribute maximum length is positive, got {self.max_length}")
        if not isinstance(self.type, String):
            raise ValueError(f"only a String Attribute bounds its length, not {self.type}")


@dataclass(frozen=True, slots=True)
class AsOfAxisMetadata:
    """One temporal dimension over a half-open ``[start, end)`` Attribute pair.

    The dimension identifies the axis; there is no separate axis name, kind, or
    query default, and the axis repeats no physical column.
    """

    dimension: TemporalDimension
    start_attribute: AttributeIdentity
    end_attribute: AttributeIdentity


def designate_framework_owned(
    attributes: Iterable[AttributeMetadata], as_of_axes: Iterable[AsOfAxisMetadata]
) -> tuple[AttributeMetadata, ...]:
    """One Entity's declared Attributes with ``framework_owned`` derived.

    The designation is true of the optimistic-lock version Attribute and of
    every As-Of Axis endpoint, so it is a function of two levels: a flag on the
    Attribute, and axis membership knowable only from the Entity. A frontend
    calls this while assembling an Entity's declarations, which is what lets a
    surface holding one declared member and no model state the same verdict as
    one holding the whole model.

    Total rather than additive: the designation each Attribute leaves with is
    derived from these arguments alone, whatever it arrived carrying.
    """
    endpoints = {
        identity for axis in as_of_axes for identity in (axis.start_attribute, axis.end_attribute)
    }
    return tuple(
        attribute
        if attribute.framework_owned == (owned := _is_framework_owned(attribute, endpoints))
        else replace(attribute, framework_owned=owned)
        for attribute in attributes
    )


def _is_framework_owned(attribute: AttributeMetadata, endpoints: set[AttributeIdentity]) -> bool:
    return attribute.optimistic_locking or attribute.identity in endpoints


@dataclass(frozen=True, slots=True)
class IndexMetadata:
    """One local Index over an ordered Attribute Identity sequence.

    Indices are never inherited and repeat no column names; storage consumers
    resolve those through Attribute Metadata. An empty component sequence stays
    constructible so foundational resolution can locate and report it.
    """

    identity: IndexIdentity
    attributes: tuple[AttributeIdentity, ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class RelationshipJoin:
    """One source-to-target Attribute equality between two resolved positions."""

    source: AttributeIdentity
    target: AttributeIdentity


@dataclass(frozen=True, slots=True)
class UnresolvedRelationshipJoin:
    """A join whose target still names its Entity through a reference."""

    source: AttributeIdentity
    target: AttributeReference


@dataclass(frozen=True, slots=True)
class RelationshipOrder:
    """One resolved ordering term over a target-local Attribute."""

    attribute: AttributeIdentity
    direction: SortDirection = SortDirection.ASCENDING
    nulls: NullPlacement = NullPlacement.NULLS_LAST


@dataclass(frozen=True, slots=True)
class UnresolvedRelationshipOrder:
    """One ordering term naming a target-local Attribute.

    The name repeats no Entity Reference because the relationship's target
    supplies its scope. An empty name raises :class:`ValueError`.
    """

    attribute: str
    direction: SortDirection = SortDirection.ASCENDING
    nulls: NullPlacement = NullPlacement.NULLS_LAST

    def __post_init__(self) -> None:
        if not self.attribute:
            raise ValueError("a relationship ordering term names a nonempty Attribute")


@dataclass(frozen=True, slots=True)
class UnresolvedDefiningRelationshipDeclaration:
    """The declaration that owns one association's mapping facts.

    Its only target is ``join.target.entity``; there is no separate target,
    reverse name, or foreign-key hint.
    """

    identity: RelationshipIdentity
    cardinality: Cardinality
    join: UnresolvedRelationshipJoin
    dependent: bool = False
    order_by: tuple[UnresolvedRelationshipOrder, ...] = ()


@dataclass(frozen=True, slots=True)
class UnresolvedReverseRelationshipDeclaration:
    """The declaration that names, and never repeats, a defining declaration."""

    identity: RelationshipIdentity
    reverse_of: RelationshipReference
    order_by: tuple[UnresolvedRelationshipOrder, ...] = ()


type UnresolvedRelationshipDeclaration = (
    UnresolvedDefiningRelationshipDeclaration | UnresolvedReverseRelationshipDeclaration
)
"""Relationship authoring as a frontend supplies it."""


@dataclass(frozen=True, slots=True)
class DefiningRelationshipDeclaration:
    """A defining declaration whose references are canonical Identities."""

    identity: RelationshipIdentity
    cardinality: Cardinality
    join: RelationshipJoin
    dependent: bool = False
    order_by: tuple[RelationshipOrder, ...] = ()


@dataclass(frozen=True, slots=True)
class ReverseRelationshipDeclaration:
    """A reverse declaration whose peer is a canonical Relationship Identity."""

    identity: RelationshipIdentity
    reverse_of: RelationshipIdentity
    order_by: tuple[RelationshipOrder, ...] = ()


type RelationshipDeclaration = DefiningRelationshipDeclaration | ReverseRelationshipDeclaration
"""The identity-resolved declaration union accepted Entity Metadata preserves.
Pairing, join swapping, and cardinality inversion belong to ``m-relationship``."""


class ValueObjectShapeKey:
    """An opaque formation-local token denoting one reusable shape declaration.

    Equality and hashing are its entire contract, and they are reference-based:
    each occurrence of one declaration node carries the same key, while
    structurally equal distinct nodes carry distinct keys. A key has no
    spelling, order, serialization, cross-formation identity, Model Location, or
    accepted-Metadata representation.
    """

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class ValueObjectAttributeDeclaration:
    """One scalar leaf of a Value Object shape; an empty name raises
    :class:`ValueError`."""

    name: str
    type: NeutralType
    nullable: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a Value Object Attribute name is nonempty")


@dataclass(frozen=True, slots=True)
class ValueObjectShapeDeclaration:
    """One reusable Value Object shape: its scalar leaves and nested occurrences.

    Shapes are storage-neutral; only a top-level occurrence owns a Storage
    Location.
    """

    key: ValueObjectShapeKey
    attributes: tuple[ValueObjectAttributeDeclaration, ...] = ()
    value_objects: tuple[NestedValueObjectOccurrenceDeclaration, ...] = ()


@dataclass(frozen=True, slots=True)
class NestedValueObjectOccurrenceDeclaration:
    """One Value Object occurrence inside another shape.

    An empty name raises :class:`ValueError`. A ``MANY`` occurrence that is also
    nullable stays constructible here; rejecting it is a semantic rule.
    """

    name: str
    shape: ValueObjectShapeDeclaration
    multiplicity: Multiplicity = Multiplicity.ONE
    nullable: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a nested Value Object occurrence name is nonempty")


@dataclass(frozen=True, slots=True)
class ValueObjectOccurrenceDeclaration:
    """One top-level Value Object occurrence on an Entity.

    It owns the occurrence's Storage Location; structured-column storage under
    that location is intrinsic, so no mapping discriminator exists. An empty
    name raises :class:`ValueError`. A ``MANY`` occurrence that is also nullable
    stays constructible here; rejecting it is a semantic rule.
    """

    name: str
    storage: StorageLocation
    shape: ValueObjectShapeDeclaration
    multiplicity: Multiplicity = Multiplicity.ONE
    nullable: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a Value Object occurrence name is nonempty")
