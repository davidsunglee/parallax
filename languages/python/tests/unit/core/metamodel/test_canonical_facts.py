from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from parallax.core import (
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    DomainModel,
    Entity,
    attr,
    index,
)
from parallax.core.internal.base import INT64, UsageError
from parallax.core.internal.entity._declaration import declaration_of
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    NOT_PRIMARY_KEY,
    AssignmentRestriction,
    AttributeIdentity,
    AttributeMetadata,
    AttributePrimaryKey,
    Column,
    EntityIdentity,
    IndexIdentity,
    IndexMetadata,
    PrimaryKey,
    Sequence,
    derive_temporal_structure,
    designate_framework_owned,
    judge_assignment,
)
from parallax.core.internal.metamodel._resolve import INDEX_ATTRIBUTE_MISSING
from parallax.descriptor import domain_model_from_document, export_document
from tests.unit._metamodel_support import Declaration, codes, key, source


class PlainItem(Entity, name="Item", table="items", indices=(index("items_label", "label"),)):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]


class TemporalItem(
    Bitemporal, name="Item", table="items", indices=(index("items_label", "label"),)
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]


@pytest.mark.parametrize("Item", [PlainItem, TemporalItem])
def test_declaration_facts_survive_repeated_formation_and_descriptor_roundtrip(
    Item: type[Entity],
) -> None:
    declaration = declaration_of(Item)
    primary, authored = declaration.indices
    assert declaration.declared_primary_key_index is primary
    assert declaration.authored_indices == (authored,)
    models = (DomainModel(Item), DomainModel(Item))
    for domain in models:
        public = domain.entity(Item)
        assert public.declared_primary_key_index is primary
        assert public.authored_indices[0] is authored
        assert public.indices[0] is primary
        accepted = model_of(domain).entity(declaration.identity)
        assert accepted is not None
        assert accepted.declared_primary_key_index is primary
        assert accepted.authored_indices[0] is authored
        assert accepted.indices[0] is primary
        assert accepted.index(primary.identity.name) is primary
        assert accepted.index(authored.identity.name) is authored
        assert all(
            actual is declared
            for actual, declared in zip(
                accepted.declared_attributes, declaration.attributes, strict=True
            )
        )
        assert all(
            actual is declared
            for actual, declared in zip(
                accepted.declared_as_of_axes, declaration.as_of_axes, strict=True
            )
        )
        assert all(
            actual.write_capability is declared.write_capability
            for actual, declared in zip(
                accepted.declared_attributes, declaration.attributes, strict=True
            )
        )
    document = export_document(models[0])
    rebuilt = domain_model_from_document(document)
    equivalent = model_of(rebuilt).entity(declaration.identity)
    assert equivalent is not None
    assert equivalent.declared_primary_key_index == primary
    assert equivalent.authored_indices == declaration.authored_indices
    assert equivalent.declared_attributes == declaration.attributes
    assert equivalent.declared_as_of_axes == declaration.as_of_axes
    assert export_document(rebuilt) == document
    assert declaration_of(Item) is declaration


def test_tableless_root_owns_the_only_local_primary_key_index() -> None:
    class Holding(Bitemporal, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
        id: Attr[int] = attr(primary_key=True)

    class Equity(Holding, table="equities", inheritance=ConcreteSubtype()):
        symbol: Attr[str]

    root = declaration_of(Holding)
    child = declaration_of(Equity)
    model = model_of(DomainModel(Holding, Equity))
    accepted = model.entity(root.identity)
    inherited = model.entity(child.identity)
    assert accepted is not None and inherited is not None
    assert accepted.declared_primary_key_index is root.declared_primary_key_index
    assert root.declared_primary_key_index is not None
    assert root.declared_primary_key_index.identity.name == "holding_pk"
    assert [part.name for part in root.declared_primary_key_index.attributes] == [
        "id",
        "validEnd",
        "txEnd",
    ]
    assert child.declared_primary_key_index is None
    assert inherited.declared_primary_key_index is None
    assert inherited.authored_indices == inherited.indices == ()


@pytest.mark.parametrize(
    ("primary_key", "read_only", "owned", "generated", "insert", "restriction"),
    [
        (NOT_PRIMARY_KEY, False, False, False, True, None),
        (NOT_PRIMARY_KEY, True, False, False, True, AssignmentRestriction.READ_ONLY),
        (NOT_PRIMARY_KEY, False, True, False, False, AssignmentRestriction.FRAMEWORK_OWNED),
        (NOT_PRIMARY_KEY, True, True, False, False, AssignmentRestriction.READ_ONLY),
        (
            PrimaryKey(APPLICATION_ASSIGNED),
            False,
            False,
            False,
            True,
            AssignmentRestriction.PRIMARY_KEY,
        ),
        (
            PrimaryKey(APPLICATION_ASSIGNED),
            True,
            True,
            False,
            False,
            AssignmentRestriction.PRIMARY_KEY,
        ),
        (PrimaryKey(MAX), False, False, True, False, AssignmentRestriction.PRIMARY_KEY),
        (PrimaryKey(Sequence("keys")), True, True, True, False, AssignmentRestriction.PRIMARY_KEY),
    ],
)
def test_attribute_capabilities_preserve_assignment_precedence(
    primary_key: AttributePrimaryKey,
    read_only: bool,
    owned: bool,
    generated: bool,
    insert: bool,
    restriction: AssignmentRestriction | None,
) -> None:
    attribute = AttributeMetadata(
        AttributeIdentity(EntityIdentity(None, "Item"), "id"),
        INT64,
        Column("id"),
        primary_key=primary_key,
        read_only=read_only,
        framework_owned=owned,
    )
    assert attribute.generated_key is generated
    capability = attribute.write_capability
    assert capability.caller_insert is insert
    assert capability.caller_update is (restriction is None)
    assert capability.assignment_restriction is restriction
    if restriction is None:
        judge_assignment(attribute, 1)
    else:
        with pytest.raises(UsageError) as caught:
            judge_assignment(attribute, "wrong type")
        assert (
            caught.value.code
            == {
                AssignmentRestriction.PRIMARY_KEY: "write-assignment-primary-key",
                AssignmentRestriction.READ_ONLY: "write-assignment-read-only",
                AssignmentRestriction.FRAMEWORK_OWNED: "write-assignment-framework-owned",
            }[restriction]
        )
    with pytest.raises(FrozenInstanceError):
        capability.caller_insert = not insert  # pyright: ignore[reportAttributeAccessIssue]


def test_final_designation_reuses_matching_capabilities_and_replaces_stale_ones() -> None:
    attribute = AttributeMetadata(
        AttributeIdentity(EntityIdentity(None, "Item"), "version"),
        INT64,
        Column("version"),
        optimistic_locking=True,
    )
    (designated,) = designate_framework_owned((attribute,), ())
    assert designated is not attribute
    assert designated.write_capability.caller_insert is False
    assert (
        designated.write_capability.assignment_restriction is AssignmentRestriction.FRAMEWORK_OWNED
    )
    assert designate_framework_owned((designated,), ())[0] is designated
    (ordinary,) = designate_framework_owned((replace(designated, optimistic_locking=False),), ())
    assert ordinary.write_capability.caller_insert is True
    assert ordinary.write_capability.caller_update is True


def test_temporal_profiles_reuse_immutable_axis_definitions() -> None:
    tx = derive_temporal_structure("transaction-time")
    both = derive_temporal_structure("bitemporal")
    assert derive_temporal_structure("transaction-time") is tx
    assert derive_temporal_structure("bitemporal") is both
    assert both[1] is tx[0]
    with pytest.raises(FrozenInstanceError):
        tx[0].end = tx[0].start  # pyright: ignore[reportAttributeAccessIssue]


def test_a_custom_producers_primary_index_is_validated_on_every_resolution() -> None:
    identity = EntityIdentity(None, "Item")
    invalid = IndexMetadata(
        IndexIdentity(identity, "item_pk"), (AttributeIdentity(identity, "absent"),), unique=True
    )
    declaration = Declaration(
        identity,
        attributes=(key(identity),),
        declared_primary_key_index=invalid,
    )
    for _ in range(2):
        assert codes(source(declaration)) == (INDEX_ATTRIBUTE_MISSING,)


@pytest.mark.parametrize("derived", [False, True])
def test_custom_combined_view_cannot_hide_an_index_from_validation(derived: bool) -> None:
    entity = EntityIdentity(None, "Item")
    invalid = IndexMetadata(
        IndexIdentity(entity, "item_pk"), (AttributeIdentity(entity, "absent"),), unique=True
    )
    original = Declaration(entity, attributes=(key(entity),))

    class InconsistentView:
        identity = original.identity
        container = original.container
        persistence = original.persistence
        layout = original.layout
        attributes = original.attributes
        relationships = original.relationships
        value_objects = original.value_objects
        as_of_axes = original.as_of_axes
        inheritance = original.inheritance
        declared_primary_key_index = invalid if derived else None
        authored_indices = () if derived else (invalid,)
        indices: tuple[IndexMetadata, ...] = ()

    assert codes(source(InconsistentView())) == (INDEX_ATTRIBUTE_MISSING,)
