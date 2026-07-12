"""Metamodel records (m-descriptor).

The neutral, frozen ``slots`` dataclasses that make up a parsed model
descriptor — an in-memory instance of ``core/schemas/metamodel.schema.json``.
Every record is immutable and shareable; derived facts (an entity's effective
``temporal`` classification, its physical ``column_order``) are computed
accessors, never re-authored fields. The behavioural scopes (``m-pk-gen``,
``m-inheritance``, ``m-value-object``) build on these records; the entity
frontend exports them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

__all__ = [
    "UNSET",
    "AsOfAttribute",
    "Attribute",
    "Axis",
    "Cardinality",
    "Entity",
    "Index",
    "Inheritance",
    "InheritanceRole",
    "Metamodel",
    "Mutability",
    "NestedValueObject",
    "OrderByTerm",
    "PkGenerator",
    "PkStrategy",
    "Relationship",
    "RelationshipCardinality",
    "Temporal",
    "Unset",
    "ValueObject",
    "ValueObjectAttribute",
    "column_order",
]

Mutability = Literal["read-only", "transactional"]
Temporal = Literal[
    "non-temporal",
    "unitemporal-processing",
    "unitemporal-business",
    "bitemporal",
]
PkStrategy = Literal["none", "max", "sequence"]
RelationshipCardinality = Literal["one-to-one", "many-to-one", "one-to-many", "many-to-many"]
Cardinality = Literal["one", "many"]
Axis = Literal["processing", "business"]
InheritanceRole = Literal["root", "abstract-subtype", "concrete-subtype"]


class Unset:
    """Sentinel for an absent optional value distinct from ``None``.

    Only the attribute ``default`` needs it — a descriptor may explicitly author
    ``default: null``, which is distinct from declaring no default at all.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "UNSET"


UNSET: Final[Unset] = Unset()


@dataclass(frozen=True, slots=True)
class PkGenerator:
    """A primary-key generation strategy (m-pk-gen)."""

    strategy: PkStrategy
    sequence_name: str | None = None
    batch_size: int | None = None
    initial_value: int | None = None
    increment_size: int | None = None

    @property
    def generates(self) -> bool:
        """Whether the strategy allocates a key the caller did not supply."""
        return self.strategy in ("max", "sequence")


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
    default: object = UNSET


@dataclass(frozen=True, slots=True)
class OrderByTerm:
    """One ordering term of a to-many relationship."""

    attr: str
    direction: Literal["asc", "desc"] = "asc"


@dataclass(frozen=True, slots=True)
class Relationship:
    """A navigable association whose join is derived from the predicate."""

    name: str
    related_entity: str
    cardinality: RelationshipCardinality
    join: str
    reverse_name: str | None = None
    dependent: bool = False
    foreign_key: str | None = None
    order_by: tuple[OrderByTerm, ...] = ()


@dataclass(frozen=True, slots=True)
class Index:
    """A physical index over one or more attributes."""

    name: str
    attributes: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class AsOfAttribute:
    """A temporal dimension backed by a ``[from, to)`` interval (m-temporal-read)."""

    name: str
    from_column: str
    to_column: str
    axis: Axis
    to_is_inclusive: bool = False
    infinity: str = "infinity"
    default: Literal["now"] = "now"


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
    cardinality: Cardinality = "one"
    attributes: tuple[ValueObjectAttribute, ...] = ()
    value_objects: tuple[NestedValueObject, ...] = ()


@dataclass(frozen=True, slots=True)
class ValueObject:
    """A top-level embedded composite stored in one ``json`` document column."""

    name: str
    column: str
    mapping: Literal["json"] = "json"
    nullable: bool = False
    cardinality: Cardinality = "one"
    attributes: tuple[ValueObjectAttribute, ...] = ()
    value_objects: tuple[NestedValueObject, ...] = ()


@dataclass(frozen=True, slots=True)
class Entity:
    """One mapped entity: identity, attributes, temporal dimensions, and relations."""

    name: str
    namespace: str | None = None
    table: str | None = None
    mutability: Mutability = "read-only"
    attributes: tuple[Attribute, ...] = ()
    as_of_attributes: tuple[AsOfAttribute, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    indices: tuple[Index, ...] = ()
    value_objects: tuple[ValueObject, ...] = ()
    inheritance: Inheritance | None = None

    @property
    def primary_key(self) -> tuple[Attribute, ...]:
        """The primary-key attributes in declaration order."""
        return tuple(attr for attr in self.attributes if attr.primary_key)

    @property
    def temporal(self) -> Temporal:
        """The effective temporal classification, derived from the as-of axes."""
        axes = {axis.axis for axis in self.as_of_attributes}
        if not axes:
            return "non-temporal"
        if axes == {"processing", "business"}:
            return "bitemporal"
        if axes == {"processing"}:
            return "unitemporal-processing"
        return "unitemporal-business"

    @property
    def is_temporal(self) -> bool:
        """Whether the entity carries any temporal dimension."""
        return bool(self.as_of_attributes)


@dataclass(frozen=True, slots=True)
class Metamodel:
    """A parsed model descriptor: one or more mapped entities."""

    entities: tuple[Entity, ...] = field(default_factory=tuple)

    @property
    def by_name(self) -> dict[str, Entity]:
        """Entities keyed by name (declaration order preserved by ``dict``)."""
        return {entity.name: entity for entity in self.entities}

    def entity(self, name: str) -> Entity:
        """The entity named ``name`` (raises ``KeyError`` when absent)."""
        return self.by_name[name]


def column_order(entity: Entity) -> tuple[str, ...]:
    """The entity's own physical columns in canonical order.

    Primary-key columns first, then the inheritance ``tag`` column when this
    entity is the table-per-hierarchy root that declares it (m-sql: the tag sits
    immediately after the primary key), then the remaining scalar columns in
    declaration order, and finally each value object's single backing column in
    declaration order (m-value-object: the document column is positional, after
    the scalar attributes). The full inherited chain of a concrete subtype's
    shared table is resolved above this per-entity view (m-inheritance).
    """
    pk = [attr.column for attr in entity.attributes if attr.primary_key]
    tag: list[str] = []
    if entity.inheritance is not None and entity.inheritance.tag_column is not None:
        tag.append(entity.inheritance.tag_column)
    rest = [attr.column for attr in entity.attributes if not attr.primary_key]
    documents = [vo.column for vo in entity.value_objects]
    return (*pk, *tag, *rest, *documents)
