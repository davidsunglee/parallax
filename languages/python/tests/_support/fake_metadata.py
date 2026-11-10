"""An alternate Compiled Metadata implementation and the parity model it pins.

The class-free seam promises that behavior depends on the metamodel protocols
and never on how a model was stored, so a second metadata implementation that
shares no code with the descriptor path is the proof. These classes hold plain
dictionary indices over the shared metamodel value types and construct no
descriptor record; :data:`PARITY_DESCRIPTOR` is the same model written as
descriptor text, so a suite can ask both implementations the same question and
compare answers. An accepted model is always the real one: a suite that needs a
Metamodel passes fake metadata through ``accept_metamodel`` and reads facets
through their owners' accessors.

The parity model is small but not degenerate: an ownerless Entity enumerates
ahead of namespaced ones, document order differs from canonical order, a
relative and an exact Entity Reference each appear, one Entity is read-only and
Transaction-Time, and one carries a nested and a Many Value Object occurrence.

Cross-surface so the unit tests and the API Conformance Suite share one fixture,
and never imported by production code.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

from parallax.core import concurrency, inheritance, relationship, storage_layout, temporal_read
from parallax.core._formation_profile import BUILTIN_MANIFEST
from parallax.core.base import (
    DATE,
    INT64,
    STRING,
    TIMESTAMP,
    NeutralType,
    Numeric,
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
    CompiledEntity,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    IndexIdentity,
    IndexMetadata,
    InheritanceMetadata,
    MemberShape,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    OccurrenceDefinition,
    PersistenceMode,
    PkGeneration,
    PrimaryKey,
    RelationshipDeclaration,
    RelationshipIdentity,
    RelationshipJoin,
    RelationshipOrder,
    ReverseRelationshipDeclaration,
    ScalarDefinition,
    SortDirection,
    StorageContainer,
    StorageLayout,
    StorageLocation,
    Table,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectAttributeMetadata,
    ValueObjectIdentity,
    ValueObjectMetadata,
    accept_metamodel,
    default_column_name,
)
from parallax.core.metamodel._accepted import FacetKey
from parallax.core.model_formation import ModelCompilerRequirement


class FakeValueObjectAttributeMetadata:
    """One scalar leaf of a Value Object occurrence."""

    def __init__(
        self,
        identity: ValueObjectAttributeIdentity,
        type: NeutralType,
        *,
        nullable: bool = False,
        multiplicity: Multiplicity = Multiplicity.ONE,
    ) -> None:
        self.identity = identity
        self.type = type
        self.nullable = nullable
        self.multiplicity = multiplicity
        self.definition = ScalarDefinition(identity.name, type, nullable, multiplicity)


class FakeNestedValueObjectMetadata:
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
        self.document_shape = MemberShape.of(self.attributes, self.value_objects)
        self.definition = OccurrenceDefinition(
            identity.path[-1], multiplicity, nullable, self.document_shape
        )
        self.members = (*self.attributes, *self.value_objects)
        self._attributes = {member.identity.name: member for member in self.attributes}
        self._value_objects = {member.identity.path[-1]: member for member in self.value_objects}

    def attribute(self, name: str) -> ValueObjectAttributeMetadata | None:
        return self._attributes.get(name)

    def value_object(self, name: str) -> NestedValueObjectMetadata | None:
        return self._value_objects.get(name)


class FakeValueObjectMetadata:
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
        self.document_shape = MemberShape.of(self.attributes, self.value_objects)
        self.definition = OccurrenceDefinition(
            identity.path[-1], multiplicity, nullable, self.document_shape
        )
        self.members = (*self.attributes, *self.value_objects)
        self._attributes = {member.identity.name: member for member in self.attributes}
        self._value_objects = {member.identity.path[-1]: member for member in self.value_objects}

    def attribute(self, name: str) -> ValueObjectAttributeMetadata | None:
        return self._attributes.get(name)

    def value_object(self, name: str) -> NestedValueObjectMetadata | None:
        return self._value_objects.get(name)


class FakeCompiledEntity:
    """One Entity's accepted local view over plain dictionary indices."""

    def __init__(
        self,
        identity: EntityIdentity,
        *,
        declared_container: StorageContainer | None = None,
        declared_persistence: PersistenceMode | None = None,
        declared_layout: StorageLayout | None = None,
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
        self.declared_layout = declared_layout
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


class FakeCompiledMetadata:
    """Compiled Metadata whose Entity set is supplied outright.

    Enumeration is canonically sorted here rather than assumed of the caller, so
    a suite may build the metadata in any order and still compare against a
    formed model.
    """

    def __init__(self, entities: Sequence[CompiledEntity]) -> None:
        self.entities = tuple(sorted(entities, key=lambda entity: entity.identity.sort_key))
        self._entities = {entity.identity: entity for entity in self.entities}

    def entity(self, identity: EntityIdentity) -> CompiledEntity | None:
        return self._entities.get(identity)


_ACCESSORS: Final[Mapping[FacetKey[Any], Callable[[Metamodel], object]]] = {
    inheritance.FACET_KEY: inheritance.inheritance_facet_of,
    relationship.FACET_KEY: relationship.relationship_facet_of,
    temporal_read.FACET_KEY: temporal_read.temporal_facet_of,
    concurrency.FACET_KEY: concurrency.concurrency_facet_of,
    storage_layout.FACET_KEY: storage_layout.storage_layout_facet_of,
}


def facets_of(model: Metamodel) -> dict[FacetKey[Any], object]:
    """Every built-in facet ``model`` carries, each read through its owner's accessor.

    The built-in Formation Manifest is the canonical list of facet keys, so an
    owner the manifest gains or loses fails here rather than going unread.
    """
    compiled = {
        entry.compiler.facet_key
        for entry in BUILTIN_MANIFEST.entries
        if isinstance(entry.compiler, ModelCompilerRequirement)
    }
    assert set(_ACCESSORS) == compiled
    return {key: read(model) for key, read in _ACCESSORS.items()}


def with_facet(model: Metamodel, key: FacetKey[Any], facet: object) -> Metamodel:
    """``model`` accepted again over its own metadata, with ``facet`` under ``key``."""
    return accept_metamodel(model, facets_of(model) | {key: facet})


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
    temporality: transaction-time
    attributes:
      - name: id
        type: int64
        primaryKey: true
"""
"""The parity model as descriptor text, matching :func:`parity_metadata` exactly."""


def _primary_key_index(entity: EntityIdentity, table: str, *ends: str) -> IndexMetadata:
    """The unique primary-key Index an accepted Metamodel derives for ``entity``.

    An alternate implementation carries the derived Index like any other, so the
    parity descriptor beside it authors none.
    """
    return IndexMetadata(
        identity=IndexIdentity(entity, f"{table}_pk"),
        attributes=(
            AttributeIdentity(entity, "id"),
            *(AttributeIdentity(entity, end) for end in ends),
        ),
        unique=True,
    )


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
    framework_owned: bool = False,
) -> AttributeMetadata:
    """One Attribute whose column defaults from its canonical name.

    ``framework_owned`` is stated rather than derived here, as the derived
    primary-key Index beside it is: this alternate implementation carries the
    accepted facts a frontend computes, without recomputing them.
    """
    return AttributeMetadata(
        identity=AttributeIdentity(entity, name),
        type=type,
        storage=Column(default_column_name(name) if column is None else column),
        primary_key=PrimaryKey(generation) if key else NOT_PRIMARY_KEY,
        nullable=nullable,
        max_length=max_length,
        framework_owned=framework_owned,
    )


def _account() -> CompiledEntity:
    contact = ValueObjectIdentity(ACCOUNT, ("contact",))
    address = ValueObjectIdentity(ACCOUNT, ("contact", "address"))
    phones = ValueObjectIdentity(ACCOUNT, ("contact", "phones"))
    return FakeCompiledEntity(
        ACCOUNT,
        declared_container=Table("account"),
        declared_attributes=(
            _attribute(ACCOUNT, "id", INT64, key=True, generation=MAX),
            _attribute(ACCOUNT, "ledgerLabel", STRING, column="ledger_label", max_length=40),
            _attribute(ACCOUNT, "balance", Numeric(18, 2)),
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
            FakeValueObjectMetadata(
                contact,
                Column("contact_doc"),
                nullable=True,
                attributes=(
                    FakeValueObjectAttributeMetadata(
                        ValueObjectAttributeIdentity(contact, "email"), STRING
                    ),
                ),
                value_objects=(
                    FakeNestedValueObjectMetadata(
                        address,
                        attributes=(
                            FakeValueObjectAttributeMetadata(
                                ValueObjectAttributeIdentity(address, "street"), STRING
                            ),
                            FakeValueObjectAttributeMetadata(
                                ValueObjectAttributeIdentity(address, "city"), STRING
                            ),
                        ),
                    ),
                    FakeNestedValueObjectMetadata(
                        phones,
                        multiplicity=Multiplicity.MANY,
                        attributes=(
                            FakeValueObjectAttributeMetadata(
                                ValueObjectAttributeIdentity(phones, "number"), STRING
                            ),
                        ),
                    ),
                ),
            ),
        ),
        indices=(_primary_key_index(ACCOUNT, "account"),),
    )


def parity_metamodel(facets: Mapping[FacetKey[Any], object] | None = None) -> Metamodel:
    """The parity model accepted over its alternate metadata, with optional facets."""
    return accept_metamodel(parity_metadata(), facets or {})


def parity_metadata() -> FakeCompiledMetadata:
    """The parity model as alternate Compiled Metadata."""
    return FakeCompiledMetadata(
        (
            _account(),
            FakeCompiledEntity(
                LEDGER,
                declared_container=Table("ledger"),
                declared_attributes=(
                    _attribute(LEDGER, "id", INT64, key=True),
                    _attribute(LEDGER, "label", STRING, max_length=40),
                ),
                indices=(_primary_key_index(LEDGER, "ledger"),),
            ),
            FakeCompiledEntity(
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
                indices=(_primary_key_index(ENTRY, "entry"),),
            ),
            FakeCompiledEntity(
                AUDIT,
                declared_container=Table("audit"),
                declared_persistence=PersistenceMode.READ_ONLY,
                declared_attributes=(
                    _attribute(AUDIT, "id", INT64, key=True),
                    _attribute(AUDIT, "txStart", TIMESTAMP, column="in_z", framework_owned=True),
                    _attribute(AUDIT, "txEnd", TIMESTAMP, column="out_z", framework_owned=True),
                ),
                declared_as_of_axes=(
                    AsOfAxisMetadata(
                        dimension=TemporalDimension.TRANSACTION_TIME,
                        start_attribute=AttributeIdentity(AUDIT, "txStart"),
                        end_attribute=AttributeIdentity(AUDIT, "txEnd"),
                    ),
                ),
                indices=(_primary_key_index(AUDIT, "audit", "txEnd"),),
            ),
        ),
    )
