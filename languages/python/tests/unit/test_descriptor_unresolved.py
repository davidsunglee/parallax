"""The descriptor-backed Unresolved Metamodel adapter and its resolution-free parse."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import case_format
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import DATE, INT64, STRING, TIMESTAMP, Decimal
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    NOT_PRIMARY_KEY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    AttributeIdentity,
    Cardinality,
    Column,
    ConcreteSubtype,
    DefiningRelationshipDeclaration,
    Document,
    EntityIdentity,
    ExactEntityReference,
    IndexIdentity,
    Multiplicity,
    PersistenceMode,
    PrimaryKey,
    RelationshipIdentity,
    RelativeEntityReference,
    ReverseRelationshipDeclaration,
    Sequence,
    SortDirection,
    Table,
    TablePerHierarchy,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedEntityDeclaration,
    UnresolvedMetamodel,
    UnresolvedReverseRelationshipDeclaration,
)
from parallax.core.model_formation import MetamodelValidationError
from parallax.descriptor import _records as records
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._errors import DescriptorError
from parallax.descriptor._serde import deserialize, parse_document
from parallax.descriptor._type_spelling import parse_type_spelling

_MODELS = sorted(
    (case_format.find_repo_root() / "core" / "compatibility" / "models").glob("*.yaml")
)


def _document(text: str) -> Mapping[str, object]:
    loaded = case_format.safe_load_yaml(text)
    assert isinstance(loaded, dict)
    return cast("Mapping[str, object]", loaded)


def _view(text: str) -> UnresolvedMetamodel:
    return unresolved_metamodel(parse_document(_document(text)))


def _only(text: str) -> UnresolvedEntityDeclaration:
    entities = _view(text).entities
    assert len(entities) == 1
    return entities[0]


_ACCOUNT = """
entity:
  name: Account
  namespace: parallax.fixture
  table: account
  attributes:
    - name: id
      type: int64
      primaryKey: true
"""


# --------------------------------------------------------------------------- #
# The corpus forms end to end.                                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", _MODELS, ids=lambda path: path.stem)
def test_every_corpus_model_forms_through_the_adapter(path: Path) -> None:
    document = _document(path.read_text(encoding="utf-8"))
    model = form_metamodel(unresolved_metamodel(parse_document(document)))

    identities = [entity.identity for entity in model.entities]
    assert identities == sorted(identities, key=lambda identity: identity.sort_key)
    for entity in model.entities:
        assert model.entity(entity.identity) is entity
        for attribute in entity.declared_attributes:
            assert entity.attribute(attribute.identity.name) is attribute


def test_accepted_lookup_returns_absence_for_an_unknown_entity() -> None:
    model = form_metamodel(_view(_ACCOUNT))
    assert model.entity(EntityIdentity("parallax.fixture", "Account")) is not None
    assert model.entity(EntityIdentity(None, "Account")) is None
    assert model.entity(EntityIdentity("elsewhere", "Account")) is None


# --------------------------------------------------------------------------- #
# The parse path resolves nothing.                                             #
# --------------------------------------------------------------------------- #
def test_parse_leaves_a_relationship_target_unresolved() -> None:
    text = """
    entity:
      name: Account
      namespace: parallax.fixture
      table: account
      attributes:
        - name: id
          type: int64
          primaryKey: true
      relationships:
        - name: entries
          cardinality: one-to-many
          join:
            source: id
            target: { entity: Entry, attribute: accountId }
    """
    parsed = parse_document(_document(text))
    declaration = parsed.entities[0].relationships[0]
    assert isinstance(declaration, records.DefiningRelationship)
    # Unqualified as authored: qualification is the resolver's answer, not parse's.
    assert declaration.join.target.entity == "Entry"


def test_parse_accepts_a_model_the_legacy_deserializer_rejects() -> None:
    text = """
    entity:
      name: Account
      namespace: parallax.fixture
      table: account
      attributes:
        - name: id
          type: int64
          primaryKey: true
      relationships:
        - name: entries
          cardinality: one-to-many
          join:
            source: id
            target: { entity: Missing, attribute: accountId }
    """
    document = _document(text)
    parse_document(document)
    with pytest.raises(DescriptorError, match="unknown entity"):
        deserialize(document)


def test_parse_rejects_an_empty_or_ambiguous_source() -> None:
    with pytest.raises(DescriptorError, match="must not be empty"):
        parse_document({"entities": []})
    with pytest.raises(DescriptorError, match="exactly one"):
        parse_document({})
    with pytest.raises(DescriptorError, match="exactly one"):
        parse_document({"entity": {}, "entities": []})


def test_the_adapter_rejects_an_empty_record_model() -> None:
    with pytest.raises(DescriptorError, match="declares no entity"):
        unresolved_metamodel(records.Metamodel())


# --------------------------------------------------------------------------- #
# A model value's own refusal is a fact about the descriptor.                   #
# --------------------------------------------------------------------------- #
def test_an_empty_namespace_is_a_descriptor_rejection_naming_its_entity() -> None:
    key = records.Attribute(name="id", type="int64", column="id", primary_key=True)
    entity = records.Entity(name="Account", namespace="", table="account", attributes=(key,))
    with pytest.raises(DescriptorError, match=r"entity '\.Account': an Entity namespace"):
        unresolved_metamodel(records.Metamodel((entity,)))


def test_a_bounded_length_on_a_non_text_attribute_is_a_descriptor_rejection() -> None:
    key = records.Attribute(name="id", type="int64", column="id", primary_key=True, max_length=8)
    entity = records.Entity(name="Account", table="account", attributes=(key,))
    with pytest.raises(DescriptorError, match="only a String Attribute bounds its length"):
        unresolved_metamodel(records.Metamodel((entity,)))


# --------------------------------------------------------------------------- #
# Persistence: what the Entity declared, not what it resolves to.               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        (None, None),
        ("read-write", PersistenceMode.READ_WRITE),
        ("read-only", PersistenceMode.READ_ONLY),
    ],
    ids=["omitted", "read-write", "read-only"],
)
def test_the_adapter_reports_the_persistence_the_record_declared(
    declared: records.Persistence | None, expected: PersistenceMode | None
) -> None:
    key = records.Attribute(name="id", type="int64", column="id", primary_key=True)
    entity = records.Entity(
        name="Account", table="account", persistence=declared, attributes=(key,)
    )
    (declaration,) = unresolved_metamodel(records.Metamodel((entity,))).entities
    assert declaration.persistence is expected


def test_the_adapter_resolves_the_structured_column_a_document_layout_names() -> None:
    key = records.Attribute(name="id", type="int64", column="id", primary_key=True)
    layout = records.DocumentLayout(column="payload")
    entity = records.Entity(name="Account", table="account", layout=layout, attributes=(key,))
    (declaration,) = unresolved_metamodel(records.Metamodel((entity,))).entities
    assert declaration.layout == Document(Column("payload"))
    plain = records.Entity(name="Account", table="account", attributes=(key,))
    (bare,) = unresolved_metamodel(records.Metamodel((plain,))).entities
    assert bare.layout is None


def test_an_authored_read_write_stays_distinguishable_from_an_omitted_one() -> None:
    def declaration(spelling: str) -> UnresolvedEntityDeclaration:
        text = f"""
        entity:
          name: Account
          table: account
          {spelling}
          attributes:
            - name: id
              type: int64
              primaryKey: true
        """
        return _only(text)

    assert declaration("persistence: read-write").persistence is PersistenceMode.READ_WRITE
    assert declaration("").persistence is None


# --------------------------------------------------------------------------- #
# The seam is enumeration-only over unmirrored declarations.                    #
# --------------------------------------------------------------------------- #
def _reachable(value: object) -> Iterator[object]:
    yield value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            yield from _reachable(getattr(value, field.name))
    elif isinstance(value, tuple):
        for item in cast("tuple[object, ...]", value):
            yield from _reachable(item)


def test_no_descriptor_record_reaches_the_unresolved_seam() -> None:
    view = _view(_REFERENCES)
    for declaration in view.entities:
        for reachable in _reachable(declaration):
            assert type(reachable).__module__ != records.__name__, reachable


def test_the_unresolved_seam_exposes_no_lookup() -> None:
    view = _view(_ACCOUNT)
    assert not hasattr(view, "entity")
    declaration = view.entities[0]
    for absent in ("attribute", "relationship", "value_object", "as_of_axis", "index"):
        assert not hasattr(declaration, absent)


def test_duplicate_identities_are_enumerated_rather_than_deduplicated() -> None:
    text = """
    entities:
      - name: Account
        namespace: parallax.fixture
        table: first
        attributes:
          - name: id
            type: int64
            primaryKey: true
      - name: Account
        namespace: parallax.fixture
        table: second
        attributes:
          - name: id
            type: int64
            primaryKey: true
    """
    view = _view(text)
    assert [declaration.container for declaration in view.entities] == [
        Table("first"),
        Table("second"),
    ]
    with pytest.raises(MetamodelValidationError) as failure:
        form_metamodel(view)
    assert [issue.code for issue in failure.value.issues] == ["metamodel-duplicate-entity-identity"]


# --------------------------------------------------------------------------- #
# Entity References.                                                           #
# --------------------------------------------------------------------------- #
_REFERENCES = """
entities:
  - name: Account
    namespace: parallax.fixture
    table: account
    attributes:
      - name: id
        type: int64
        primaryKey: true
    relationships:
      - name: entries
        cardinality: one-to-many
        join:
          source: id
          target: { entity: Entry, attribute: accountId }
      - name: audits
        cardinality: one-to-many
        join:
          source: id
          target: { entity: parallax.other.Audit, attribute: accountId }
  - name: Entry
    namespace: parallax.fixture
    table: entry
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: accountId
        type: int64
        column: account_id
    relationships:
      - name: account
        reverseOf: parallax.fixture.Account.entries
  - name: Audit
    namespace: parallax.other
    table: audit
    attributes:
      - name: id
        type: int64
        primaryKey: true
      - name: accountId
        type: int64
        column: account_id
"""


def test_a_bare_spelling_is_relative_and_a_qualified_one_is_exact() -> None:
    account, entry, _ = _view(_REFERENCES).entities
    relative, exact = account.relationships
    assert isinstance(relative, UnresolvedDefiningRelationshipDeclaration)
    assert relative.join.target.entity == RelativeEntityReference("Entry")
    assert isinstance(exact, UnresolvedDefiningRelationshipDeclaration)
    assert exact.join.target.entity == ExactEntityReference(
        EntityIdentity("parallax.other", "Audit")
    )

    reverse = entry.relationships[0]
    assert isinstance(reverse, UnresolvedReverseRelationshipDeclaration)
    assert reverse.reverse_of.entity == ExactEntityReference(
        EntityIdentity("parallax.fixture", "Account")
    )
    assert reverse.reverse_of.name == "entries"


def test_both_reference_spellings_resolve_to_their_named_entity() -> None:
    model = form_metamodel(_view(_REFERENCES))
    account = model.entity(EntityIdentity("parallax.fixture", "Account"))
    assert account is not None

    entries = account.relationship("entries")
    assert isinstance(entries, DefiningRelationshipDeclaration)
    assert entries.join.target == AttributeIdentity(
        EntityIdentity("parallax.fixture", "Entry"), "accountId"
    )
    audits = account.relationship("audits")
    assert isinstance(audits, DefiningRelationshipDeclaration)
    assert audits.join.target == AttributeIdentity(
        EntityIdentity("parallax.other", "Audit"), "accountId"
    )

    entry = model.entity(EntityIdentity("parallax.fixture", "Entry"))
    assert entry is not None
    reverse = entry.relationship("account")
    assert isinstance(reverse, ReverseRelationshipDeclaration)
    assert reverse.reverse_of == RelationshipIdentity(account.identity, "entries")
    assert entry.relationship("missing") is None


def test_an_ownerless_reference_never_falls_back_to_a_namespaced_entity() -> None:
    text = """
    entities:
      - name: Account
        table: account
        attributes:
          - name: id
            type: int64
            primaryKey: true
        relationships:
          - name: entries
            cardinality: one-to-many
            join:
              source: id
              target: { entity: Entry, attribute: accountId }
      - name: Entry
        namespace: parallax.fixture
        table: entry
        attributes:
          - name: id
            type: int64
            primaryKey: true
          - name: accountId
            type: int64
            column: account_id
    """
    # `Entry` is relative to the ownerless declarer, so it names an ownerless
    # Entry — the namespaced one is a different Entity, not a fallback.
    with pytest.raises(MetamodelValidationError) as failure:
        form_metamodel(_view(text))
    (issue,) = failure.value.issues
    assert issue.code == "metamodel-unresolved-entity-reference"


def test_a_missing_relationship_target_is_rejected_by_formation() -> None:
    text = """
    entity:
      name: Account
      namespace: parallax.fixture
      table: account
      attributes:
        - name: id
          type: int64
          primaryKey: true
      relationships:
        - name: entries
          cardinality: one-to-many
          join:
            source: id
            target: { entity: Missing, attribute: accountId }
    """
    with pytest.raises(MetamodelValidationError) as failure:
        form_metamodel(_view(text))
    assert [issue.code for issue in failure.value.issues] == [
        "metamodel-unresolved-entity-reference"
    ]


# --------------------------------------------------------------------------- #
# Local facts become their final Metadata values.                              #
# --------------------------------------------------------------------------- #
def test_attributes_carry_structured_types_storage_and_generation() -> None:
    text = """
    entity:
      name: Account
      namespace: parallax.fixture
      table: account
      persistence: read-only
      attributes:
        - name: id
          type: int64
          primaryKey: true
          pkGeneration:
            strategy: sequence
            name: account_ids
            batchSize: 20
            initialValue: 7
        - name: label
          type: string
          maxLength: 40
          readOnly: true
        - name: balance
          type: decimal(18,2)
          optimisticLocking: true
        - name: openedOn
          type: date
          nullable: true
        - name: legacyName
          type: string
          column: legacyName
      indices:
        - name: account_pk
          attributes: [id]
          unique: true
    """
    declaration = _only(text)
    assert declaration.identity == EntityIdentity("parallax.fixture", "Account")
    assert declaration.container == Table("account")
    assert declaration.persistence is PersistenceMode.READ_ONLY

    identifier, label, balance, opened, legacy = declaration.attributes
    assert identifier.identity == AttributeIdentity(declaration.identity, "id")
    assert identifier.type == INT64
    assert identifier.storage == Column("id")
    assert identifier.primary_key == PrimaryKey(
        Sequence(name="account_ids", batch_size=20, initial_value=7, increment_size=1)
    )
    assert label.type == STRING
    assert label.max_length == 40
    assert label.read_only
    assert balance.type == Decimal(18, 2)
    assert balance.optimistic_locking
    assert balance.primary_key is NOT_PRIMARY_KEY
    assert opened.type == DATE
    assert opened.storage == Column("opened_on")
    assert opened.nullable
    assert legacy.storage == Column("legacyName")

    (index,) = declaration.indices
    assert index.identity == IndexIdentity(declaration.identity, "account_pk")
    assert index.attributes == (AttributeIdentity(declaration.identity, "id"),)
    assert index.unique


@pytest.mark.parametrize(
    ("spelling", "generation"),
    [("application-assigned", APPLICATION_ASSIGNED), ("max", MAX)],
)
def test_the_nullary_generation_spellings_normalize(spelling: str, generation: object) -> None:
    text = f"""
    entity:
      name: Account
      namespace: parallax.fixture
      table: account
      attributes:
        - name: id
          type: int64
          primaryKey: true
          pkGeneration: {spelling}
    """
    assert _only(text).attributes[0].primary_key == PrimaryKey(cast("Any", generation))


def test_a_declared_key_without_a_generator_is_application_assigned() -> None:
    key = records.Attribute(name="id", type="int64", column="id", primary_key=True)
    entity = records.Entity(name="Account", table="account", attributes=(key,))
    (declaration,) = unresolved_metamodel(records.Metamodel((entity,))).entities
    assert declaration.attributes[0].primary_key == PrimaryKey(APPLICATION_ASSIGNED)


def test_a_sequence_generation_without_a_name_is_rejected() -> None:
    key = records.Attribute(
        name="id",
        type="int64",
        column="id",
        primary_key=True,
        pk_generator=records.PkGenerator(strategy="sequence"),
    )
    entity = records.Entity(name="Account", table="account", attributes=(key,))
    with pytest.raises(DescriptorError, match="names its sequence"):
        unresolved_metamodel(records.Metamodel((entity,)))


def test_a_temporal_entity_keys_its_axis_by_dimension() -> None:
    text = """
    entity:
      name: Balance
      namespace: parallax.fixture
      table: balance
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
        - dimension: transaction-time
          startAttribute: tx_start
          endAttribute: tx_end
    """
    declaration = _only(text)
    (axis,) = declaration.as_of_axes
    assert axis.dimension.name == "TRANSACTION_TIME"
    assert axis.start_attribute == AttributeIdentity(declaration.identity, "tx_start")
    assert axis.end_attribute == AttributeIdentity(declaration.identity, "tx_end")
    assert declaration.attributes[1].type == TIMESTAMP


def test_relationship_facts_become_structured_declarations() -> None:
    account, entry, _ = _view(_REFERENCES).entities
    defining = account.relationships[0]
    assert isinstance(defining, UnresolvedDefiningRelationshipDeclaration)
    assert defining.identity.source_entity == account.identity
    assert defining.identity.name == "entries"
    assert defining.cardinality is Cardinality.ONE_TO_MANY
    assert defining.join.source == AttributeIdentity(account.identity, "id")
    assert defining.join.target.name == "accountId"
    assert not defining.dependent
    assert defining.order_by == ()
    assert entry.relationships[0].identity.name == "account"


def test_ordering_terms_keep_their_direction_and_order() -> None:
    text = """
    entities:
      - name: Account
        namespace: parallax.fixture
        table: account
        attributes:
          - name: id
            type: int64
            primaryKey: true
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
      - name: Entry
        namespace: parallax.fixture
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
    """
    account = _view(text).entities[0]
    defining = account.relationships[0]
    assert isinstance(defining, UnresolvedDefiningRelationshipDeclaration)
    assert defining.dependent
    assert [(term.attribute, term.direction) for term in defining.order_by] == [
        ("postedOn", SortDirection.DESCENDING),
        ("id", SortDirection.ASCENDING),
    ]


def test_value_object_occurrences_keep_shape_storage_and_multiplicity() -> None:
    text = """
    entity:
      name: Customer
      namespace: parallax.fixture
      table: customer
      attributes:
        - name: id
          type: int64
          primaryKey: true
      valueObjects:
        - name: contact
          column: contact_doc
          nullable: true
          attributes:
            - name: email
              type: string
          valueObjects:
            - name: phones
              multiplicity: many
              attributes:
                - name: number
                  type: string
    """
    (contact,) = _only(text).value_objects
    assert contact.name == "contact"
    assert contact.storage == Column("contact_doc")
    assert contact.multiplicity is Multiplicity.ONE
    assert contact.nullable
    assert [member.name for member in contact.shape.attributes] == ["email"]
    (phones,) = contact.shape.value_objects
    assert phones.multiplicity is Multiplicity.MANY
    assert phones.shape.attributes[0].type == STRING


def test_an_omitted_value_object_column_uses_the_portable_derived_default() -> None:
    text = """
    entity:
      name: Customer
      namespace: parallax.fixture
      table: customer
      attributes:
        - name: id
          type: int64
          primaryKey: true
      valueObjects:
        - name: contactDetails
          attributes:
            - name: email
              type: string
    """
    (contact,) = _only(text).value_objects
    assert contact.storage == Column("contact_details")


def test_every_shape_declaration_carries_its_own_key() -> None:
    text = """
    entity:
      name: Customer
      namespace: parallax.fixture
      table: customer
      attributes:
        - name: id
          type: int64
          primaryKey: true
      valueObjects:
        - name: home
          attributes:
            - name: city
              type: string
        - name: work
          attributes:
            - name: city
              type: string
    """
    home, work = _only(text).value_objects
    # Structurally equal but separately authored, so the declarations are distinct.
    assert home.shape.key != work.shape.key
    assert home.shape.key == home.shape.key


# --------------------------------------------------------------------------- #
# Inheritance positions.                                                       #
# --------------------------------------------------------------------------- #
def test_inheritance_roles_become_the_structured_union() -> None:
    text = """
    entities:
      - name: Animal
        namespace: parallax.fixture
        table: animal
        inheritance:
          role: root
          strategy: table-per-hierarchy
          tag:
            column: kind
        attributes:
          - name: id
            type: int64
            primaryKey: true
      - name: Pet
        namespace: parallax.fixture
        inheritance:
          role: abstract-subtype
          parent: Animal
      - name: Dog
        namespace: parallax.fixture
        inheritance:
          role: concrete-subtype
          parent: Pet
          tagValue: dog
    """
    animal, pet, dog = _view(text).entities
    assert animal.inheritance == AbstractRoot(TablePerHierarchy("kind"))
    assert pet.inheritance == AbstractSubtype(RelativeEntityReference("Animal"))
    assert dog.inheritance == ConcreteSubtype(RelativeEntityReference("Pet"), "dog")
    assert pet.container is None


def test_a_table_per_concrete_subtype_root_carries_no_tag_column() -> None:
    text = """
    entities:
      - name: Document
        namespace: parallax.fixture
        inheritance:
          role: root
          strategy: table-per-concrete-subtype
        attributes:
          - name: id
            type: int64
            primaryKey: true
      - name: Memo
        namespace: parallax.fixture
        table: memo
        inheritance:
          role: concrete-subtype
          parent: Document
    """
    document, memo = _view(text).entities
    assert document.inheritance == AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)
    assert memo.inheritance == ConcreteSubtype(RelativeEntityReference("Document"), None)


@pytest.mark.parametrize(
    ("inheritance", "message"),
    [
        (records.Inheritance(role="root"), "declares a strategy"),
        (
            records.Inheritance(role="root", strategy="table-per-hierarchy"),
            "declares a tag column",
        ),
        (records.Inheritance(role="concrete-subtype"), "names its parent"),
    ],
)
def test_an_incoherent_inheritance_record_is_rejected(
    inheritance: records.Inheritance, message: str
) -> None:
    entity = records.Entity(name="Animal", table="animal", inheritance=inheritance)
    with pytest.raises(DescriptorError, match=message):
        unresolved_metamodel(records.Metamodel((entity,)))


# --------------------------------------------------------------------------- #
# Type spellings.                                                              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("spelling", "expected"),
    [
        ("int64", INT64),
        ("string", STRING),
        ("timestamp", TIMESTAMP),
        ("decimal(18,2)", Decimal(18, 2)),
        ("decimal(1,0)", Decimal(1, 0)),
    ],
)
def test_a_valid_spelling_denotes_its_structured_type(spelling: str, expected: object) -> None:
    assert parse_type_spelling(spelling) == expected


@pytest.mark.parametrize(
    "spelling",
    ["", "Int64", "decimal", "decimal(18)", "decimal(0,9)", "decimal(2,5)", "decimal(09,2)"],
)
def test_an_unrepresentable_spelling_denotes_nothing(spelling: str) -> None:
    assert parse_type_spelling(spelling) is None


def test_an_unrepresentable_attribute_spelling_is_rejected() -> None:
    text = """
    entity:
      name: Account
      namespace: parallax.fixture
      table: account
      attributes:
        - name: id
          type: decimal(2,5)
          primaryKey: true
    """
    with pytest.raises(DescriptorError, match="not a neutral type spelling"):
        _view(text)


def test_an_unrepresentable_value_object_spelling_is_rejected() -> None:
    text = """
    entity:
      name: Customer
      namespace: parallax.fixture
      table: customer
      attributes:
        - name: id
          type: int64
          primaryKey: true
      valueObjects:
        - name: contact
          valueObjects:
            - name: phone
              attributes:
                - name: number
                  type: telephone
    """
    with pytest.raises(DescriptorError, match=r"contact\.phone\.number"):
        _view(text)
