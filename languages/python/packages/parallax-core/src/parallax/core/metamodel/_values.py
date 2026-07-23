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
from dataclasses import dataclass
from typing import Final

from parallax.core.base import NeutralType
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
    "ConcreteSubtype",
    "DefiningRelationshipDeclaration",
    "IndexMetadata",
    "Inheritance",
    "InheritanceMetadata",
    "InheritanceStrategy",
    "Max",
    "Multiplicity",
    "NestedValueObjectOccurrenceDeclaration",
    "NotPrimaryKey",
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
    """The ordering direction shared by relationship order and operation sort keys."""

    ASCENDING = enum.auto()
    DESCENDING = enum.auto()


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
container, and the reserved ``DocumentPath`` variant is not constructible."""


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


@dataclass(frozen=True, slots=True)
class AttributeMetadata:
    """One self-identifying scalar Attribute.

    Reference-free, so a frontend supplies it unchanged at the Unresolved seam
    and accepted Metadata reuses it. It duplicates neither its own name nor its
    Entity's container. A maximum length is either absent or positive; a
    nonpositive one raises :class:`ValueError`.
    """

    identity: AttributeIdentity
    type: NeutralType
    storage: StorageLocation
    primary_key: AttributePrimaryKey = NOT_PRIMARY_KEY
    nullable: bool = False
    max_length: int | None = None
    read_only: bool = False
    optimistic_locking: bool = False

    def __post_init__(self) -> None:
        if self.max_length is not None and self.max_length < 1:
            raise ValueError(f"an Attribute maximum length is positive, got {self.max_length}")


@dataclass(frozen=True, slots=True)
class AsOfAxisMetadata:
    """One temporal dimension over a half-open ``[start, end)`` Attribute pair.

    The dimension identifies the axis; there is no separate axis name, kind, or
    query default, and the axis repeats no physical column.
    """

    dimension: TemporalDimension
    start_attribute: AttributeIdentity
    end_attribute: AttributeIdentity


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


@dataclass(frozen=True, slots=True)
class UnresolvedRelationshipOrder:
    """One ordering term naming a target-local Attribute.

    The name repeats no Entity Reference because the relationship's target
    supplies its scope. An empty name raises :class:`ValueError`.
    """

    attribute: str
    direction: SortDirection = SortDirection.ASCENDING

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
