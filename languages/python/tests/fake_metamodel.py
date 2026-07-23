"""An alternate accepted-Metamodel implementation and the parity model it pins.

The class-free seam promises that behavior depends on the metamodel protocols
and never on how a model was stored, so a second implementation that shares no
code with the descriptor path is the proof. These classes hold plain dictionary
indexes over the shared metamodel value types and construct no descriptor
record; :data:`PARITY_DESCRIPTOR` is the same model written as descriptor text,
so a suite can ask both implementations the same question and compare answers.

The parity model is small but not degenerate: an ownerless Entity enumerates
ahead of namespaced ones, document order differs from canonical order, a
relative and an exact Entity Reference each appear, one Entity is read-only and
Transaction-Time, and one carries a nested and a Many Value Object occurrence.

Top-level so the unit lane and the API Conformance Suite share one fixture, and
never imported by production code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

from parallax.core.base import (
    DATE,
    INT64,
    STRING,
    TIMESTAMP,
    Decimal,
    NeutralType,
)
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    NOT_PRIMARY_KEY,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    Cardinality,
    Column,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    EntityMetadata,
    FacetKey,
    IndexIdentity,
    IndexMetadata,
    InheritanceMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    PersistenceMode,
    PkGeneration,
    PrimaryKey,
    RelationshipDeclaration,
    RelationshipIdentity,
    RelationshipJoin,
    RelationshipOrder,
    ReverseRelationshipDeclaration,
    SortDirection,
    StorageContainer,
    StorageLocation,
    Table,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeMetadata,
    ValueObjectIdentity,
    ValueObjectMetadata,
)


class FakeValueObjectAttribute:
    """One scalar leaf of a Value Object occurrence."""

    def __init__(
        self, identity: ValueObjectAttributeIdentity, type: NeutralType, *, nullable: bool = False
    ) -> None:
        self.identity = identity
        self.type = type
        self.nullable = nullable


class FakeNestedValueObject:
    """One nested Value Object occurrence with dictionary member lookup."""

    def __init__(
        self,
        identity: ValueObjectIdentity,
        *,
        multiplicity: Multiplicity = Multiplicity.ONE,
        nullable: bool = False,
        attributes: Sequence[ValueObjectAttributeMetadata] = (),
        value_objects: Sequence[NestedValueObjectMetadata] = (),
    ) -> None:
        self.identity = identity
        self.multiplicity = multiplicity
        self.nullable = nullable
        self.attributes = tuple(attributes)
        self.value_objects = tuple(value_objects)
        self._attributes = {member.identity.name: member for member in self.attributes}
        self._value_objects = {member.identity.path[-1]: member for member in self.value_objects}

    def attribute(self, name: str) -> ValueObjectAttributeMetadata | None:
        return self._attributes.get(name)

    def value_object(self, name: str) -> NestedValueObjectMetadata | None:
        return self._value_objects.get(name)


class FakeValueObject:
    """One top-level Value Object occurrence and the storage it owns."""

    def __init__(
        self,
        identity: ValueObjectIdentity,
        storage: StorageLocation,
        *,
        multiplicity: Multiplicity = Multiplicity.ONE,
        nullable: bool = False,
        attributes: Sequence[ValueObjectAttributeMetadata] = (),
        value_objects: Sequence[NestedValueObjectMetadata] = (),
    ) -> None:
        self.identity = identity
        self.storage = storage
        self.multiplicity = multiplicity
        self.nullable = nullable
        self.attributes = tuple(attributes)
        self.value_objects = tuple(value_objects)
        self._attributes = {member.identity.name: member for member in self.attributes}
        self._value_objects = {member.identity.path[-1]: member for member in self.value_objects}

    def attribute(self, name: str) -> ValueObjectAttributeMetadata | None:
        return self._attributes.get(name)

    def value_object(self, name: str) -> NestedValueObjectMetadata | None:
        return self._value_objects.get(name)


class FakeEntity:
    """One Entity's accepted local view over plain dictionary indexes."""

    def __init__(
        self,
        identity: EntityIdentity,
        *,
        declared_container: StorageContainer | None = None,
        declared_persistence: PersistenceMode | None = None,
        declared_attributes: Sequence[AttributeMetadata] = (),
        declared_relationships: Sequence[RelationshipDeclaration] = (),
        declared_value_objects: Sequence[ValueObjectMetadata] = (),
        declared_as_of_axes: Sequence[AsOfAxisMetadata] = (),
        inheritance: InheritanceMetadata | None = None,
        indices: Sequence[IndexMetadata] = (),
    ) -> None:
        self.identity = identity
        self.declared_container = declared_container
        self.declared_persistence = declared_persistence
        self.declared_attributes = tuple(declared_attributes)
        self.declared_relationships = tuple(declared_relationships)
        self.declared_value_objects = tuple(declared_value_objects)
        self.declared_as_of_axes = tuple(declared_as_of_axes)
        self.inheritance = inheritance
        self.indices = tuple(indices)
        self._attributes = {member.identity.name: member for member in self.declared_attributes}
        self._relationships = {
            member.identity.name: member for member in self.declared_relationships
        }
        self._value_objects = {
            member.identity.path[-1]: member for member in self.declared_value_objects
        }
        self._axes = {axis.dimension: axis for axis in self.declared_as_of_axes}
        self._indices = {member.identity.name: member for member in self.indices}

    def attribute(self, name: str) -> AttributeMetadata | None:
        return self._attributes.get(name)

    def relationship(self, name: str) -> RelationshipDeclaration | None:
        return self._relationships.get(name)

    def value_object(self, name: str) -> ValueObjectMetadata | None:
        return self._value_objects.get(name)

    def as_of_axis(self, dimension: TemporalDimension) -> AsOfAxisMetadata | None:
        return self._axes.get(dimension)

    def index(self, name: str) -> IndexMetadata | None:
        return self._indices.get(name)


class FakeMetamodel:
    """An accepted model whose Entity order and facet set are supplied outright.

    Enumeration is canonically sorted here rather than assumed of the caller, so
    a suite may build the model in any order and still compare against a
    formed one.
    """

    def __init__(
        self,
        entities: Sequence[EntityMetadata],
        facets: Mapping[FacetKey[Any], object] | None = None,
    ) -> None:
        self.entities = tuple(sorted(entities, key=lambda entity: entity.identity.sort_key))
        self.facets = dict(facets or {})
        self._entities = {entity.identity: entity for entity in self.entities}

    def entity(self, identity: EntityIdentity) -> EntityMetadata | None:
        return self._entities.get(identity)

    def facet[T](self, key: FacetKey[T]) -> T:
        return cast("T", self.facets[key])


NAMESPACE: Final[str] = "parallax.fake"

LEDGER: Final[EntityIdentity] = EntityIdentity(None, "Ledger")
ACCOUNT: Final[EntityIdentity] = EntityIdentity(NAMESPACE, "Account")
ENTRY: Final[EntityIdentity] = EntityIdentity(NAMESPACE, "Entry")
AUDIT: Final[EntityIdentity] = EntityIdentity(NAMESPACE, "Audit")

PARITY_DESCRIPTOR: Final[str] = """
entities:
  - name: Account
    namespace: parallax.fake
    table: account
    attributes:
      - name: id
        type: int64
        primaryKey: true
        pkGeneration: max
      - name: ledgerLabel
        type: string
        column: ledger_label
        maxLength: 40
      - name: balance
        type: decimal(18,2)
      - name: openedOn
        type: date
        column: opened_on
        nullable: true
    relationships:
      - name: entries
        cardinality: one-to-many
        join:
          source: id
          target: { entity: Entry, attribute: accountId }
        dependent: true
        orderBy:
          - { attribute: postedOn, direction: desc }
          - { attribute: id }
    valueObjects:
      - name: contact
        column: contact_doc
        nullable: true
        attributes:
          - name: email
            type: string
        valueObjects:
          - name: address
            attributes:
              - name: street
                type: string
              - name: city
                type: string
          - name: phones
            multiplicity: many
            attributes:
              - name: number
                type: string
    indices:
      - name: account_pk
        attributes: [id]
        unique: true
  - name: Ledger
    table: ledger
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: label
        type: string
        maxLength: 40
  - name: Entry
    namespace: parallax.fake
    table: entry
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: accountId
        type: int64
        column: account_id
      - name: postedOn
        type: date
        column: posted_on
    relationships:
      - name: account
        reverseOf: parallax.fake.Account.entries
  - name: Audit
    namespace: parallax.fake
    table: audit
    persistence: read-only
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: tx_start
        type: timestamp
        column: in_z
      - name: tx_end
        type: timestamp
        column: out_z
    asOfAxes:
      - dimension: transactionTime
        startAttribute: tx_start
        endAttribute: tx_end
"""
"""The parity model as descriptor text, matching :func:`parity_model` exactly."""


def _attribute(
    entity: EntityIdentity,
    name: str,
    type: NeutralType,
    *,
    column: str | None = None,
    key: bool = False,
    generation: PkGeneration = APPLICATION_ASSIGNED,
    nullable: bool = False,
    max_length: int | None = None,
) -> AttributeMetadata:
    """One Attribute whose column defaults to its own name."""
    return AttributeMetadata(
        identity=AttributeIdentity(entity, name),
        type=type,
        storage=Column(name if column is None else column),
        primary_key=PrimaryKey(generation) if key else NOT_PRIMARY_KEY,
        nullable=nullable,
        max_length=max_length,
    )


def _account() -> EntityMetadata:
    contact = ValueObjectIdentity(ACCOUNT, ("contact",))
    address = ValueObjectIdentity(ACCOUNT, ("contact", "address"))
    phones = ValueObjectIdentity(ACCOUNT, ("contact", "phones"))
    return FakeEntity(
        ACCOUNT,
        declared_container=Table("account"),
        declared_attributes=(
            _attribute(ACCOUNT, "id", INT64, key=True, generation=MAX),
            _attribute(ACCOUNT, "ledgerLabel", STRING, column="ledger_label", max_length=40),
            _attribute(ACCOUNT, "balance", Decimal(18, 2)),
            _attribute(ACCOUNT, "openedOn", DATE, column="opened_on", nullable=True),
        ),
        declared_relationships=(
            DefiningRelationshipDeclaration(
                identity=RelationshipIdentity(ACCOUNT, "entries"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=RelationshipJoin(
                    source=AttributeIdentity(ACCOUNT, "id"),
                    target=AttributeIdentity(ENTRY, "accountId"),
                ),
                dependent=True,
                order_by=(
                    RelationshipOrder(
                        AttributeIdentity(ENTRY, "postedOn"), SortDirection.DESCENDING
                    ),
                    RelationshipOrder(AttributeIdentity(ENTRY, "id"), SortDirection.ASCENDING),
                ),
            ),
        ),
        declared_value_objects=(
            FakeValueObject(
                contact,
                Column("contact_doc"),
                nullable=True,
                attributes=(
                    FakeValueObjectAttribute(
                        ValueObjectAttributeIdentity(contact, "email"), STRING
                    ),
                ),
                value_objects=(
                    FakeNestedValueObject(
                        address,
                        attributes=(
                            FakeValueObjectAttribute(
                                ValueObjectAttributeIdentity(address, "street"), STRING
                            ),
                            FakeValueObjectAttribute(
                                ValueObjectAttributeIdentity(address, "city"), STRING
                            ),
                        ),
                    ),
                    FakeNestedValueObject(
                        phones,
                        multiplicity=Multiplicity.MANY,
                        attributes=(
                            FakeValueObjectAttribute(
                                ValueObjectAttributeIdentity(phones, "number"), STRING
                            ),
                        ),
                    ),
                ),
            ),
        ),
        indices=(
            IndexMetadata(
                identity=IndexIdentity(ACCOUNT, "account_pk"),
                attributes=(AttributeIdentity(ACCOUNT, "id"),),
                unique=True,
            ),
        ),
    )


def parity_model(facets: Mapping[FacetKey[Any], object] | None = None) -> Metamodel:
    """The parity model as an alternate implementation, with optional facets."""
    return FakeMetamodel(
        (
            _account(),
            FakeEntity(
                LEDGER,
                declared_container=Table("ledger"),
                declared_attributes=(
                    _attribute(LEDGER, "id", INT64, key=True),
                    _attribute(LEDGER, "label", STRING, max_length=40),
                ),
            ),
            FakeEntity(
                ENTRY,
                declared_container=Table("entry"),
                declared_attributes=(
                    _attribute(ENTRY, "id", INT64, key=True),
                    _attribute(ENTRY, "accountId", INT64, column="account_id"),
                    _attribute(ENTRY, "postedOn", DATE, column="posted_on"),
                ),
                declared_relationships=(
                    ReverseRelationshipDeclaration(
                        identity=RelationshipIdentity(ENTRY, "account"),
                        reverse_of=RelationshipIdentity(ACCOUNT, "entries"),
                    ),
                ),
            ),
            FakeEntity(
                AUDIT,
                declared_container=Table("audit"),
                declared_persistence=PersistenceMode.READ_ONLY,
                declared_attributes=(
                    _attribute(AUDIT, "id", INT64, key=True),
                    _attribute(AUDIT, "tx_start", TIMESTAMP, column="in_z"),
                    _attribute(AUDIT, "tx_end", TIMESTAMP, column="out_z"),
                ),
                declared_as_of_axes=(
                    AsOfAxisMetadata(
                        dimension=TemporalDimension.TRANSACTION_TIME,
                        start_attribute=AttributeIdentity(AUDIT, "tx_start"),
                        end_attribute=AttributeIdentity(AUDIT, "tx_end"),
                    ),
                ),
            ),
        ),
        facets,
    )
