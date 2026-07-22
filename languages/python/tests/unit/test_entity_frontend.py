"""Entity frontend (definition half): descriptor export and rejections."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import cast

import pytest

import frontend_probes
import mirrored_models as mm
from parallax.conformance import case_format
from parallax.core import (
    Attr,
    Bitemporal,
    Entity,
    EntityConfig,
    EntityDefinitionError,
    Field,
    NameCollisionError,
    Rel,
    Relationship,
    RelationshipJoin,
    RelationshipTarget,
    ReservedNameError,
    TxTemporal,
)
from parallax.core.descriptor import (
    AsOfAxisMetadata as AsOfAxisRecord,
)
from parallax.core.descriptor import (
    DefiningRelationship,
    canonicalize,
)
from parallax.core.entity import (
    AttributeRef,
    RelationshipRef,
    ScopedMetamodel,
    camel_to_snake,
    descriptor_document,
    entity_record_of,
    metamodel,
    snake_to_camel,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("stem, classes", mm.MIRRORED, ids=[stem for stem, _ in mm.MIRRORED])
def test_mirrored_class_export_matches_the_corpus_logical_model(
    stem: str, classes: list[type]
) -> None:
    corpus = mm.drop_indices(canonicalize(_raw_model(stem)))
    assert descriptor_document(classes) == corpus


def _raw_model(stem: str) -> dict[str, object]:
    path = case_format.find_repo_root() / "core" / "compatibility" / "models" / f"{stem}.yaml"
    loaded = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast("dict[str, object]", loaded)


@pytest.mark.parametrize(
    ("snake", "camel"),
    [("id", "id"), ("order_id", "orderId"), ("person_id", "personId"), ("a_b_c", "aBC")],
)
def test_snake_to_camel_conversion(snake: str, camel: str) -> None:
    assert snake_to_camel(snake) == camel


@pytest.mark.parametrize(
    ("entity_name", "table"),
    [("Account", "account"), ("OrderItem", "order_item"), ("PkSequence", "pk_sequence")],
)
def test_camel_to_snake_default_table(entity_name: str, table: str) -> None:
    assert camel_to_snake(entity_name) == table


def test_metamodel_assembles_related_classes() -> None:
    assembled = metamodel([mm.Person, mm.Passport])
    assert tuple(e.name for e in assembled.entities) == ("Person", "Passport")
    assert isinstance(assembled, ScopedMetamodel)
    assert assembled.registry is not None


def test_metamodel_of_no_classes_stays_unscoped() -> None:
    # S2 (COR-3 Phase 7 increment 7 round-2): no class/registry context at all
    # -- the one documented case the untagged, UNSCOPED shape legitimately
    # survives in (never a silent guess at a scope with nothing to derive it
    # from).
    assembled = metamodel([])
    assert not isinstance(assembled, ScopedMetamodel)
    assert assembled.entities == ()


def test_metamodel_rejects_a_non_entity_class() -> None:
    with pytest.raises(TypeError, match="is not a Parallax entity class"):
        metamodel([int])


def test_attribute_descriptor_get_on_class_and_instance() -> None:
    account = mm.Account(id=1, owner="alice", balance=Decimal("9.99"), version=1)
    descriptor = mm.Account.__dict__["owner"]
    # Class access yields the expression object (the seed of a predicate); its
    # underlying reference identifies the attribute.
    assert descriptor.__get__(None, mm.Account).ref == AttributeRef("Account", "owner")
    assert descriptor.__get__(account, mm.Account) == "alice"
    # Normal instance access returns the stored value (non-data descriptor).
    assert account.owner == "alice"


def test_relationship_descriptor_get_on_class_and_instance() -> None:
    descriptor = mm.Passport.__dict__["holder"]
    # Class access yields a RelationshipPath (the include/any/none seed); its
    # `.ref` mirrors AttributeExpr's own class-access identity, and `.target`
    # is the declared relationship's own related entity.
    path = descriptor.__get__(None, mm.Passport)
    assert path.ref == RelationshipRef("Passport", "holder")
    assert path.target == "Person"
    person = mm.Person(id=2, name="p")
    carrier = _Carrier()
    carrier.holder = person  # a materialized peer lives in the instance __dict__
    assert descriptor.__get__(carrier, mm.Passport) is person


class _Carrier:
    """A plain object whose ``__dict__`` stands in for a materialized instance."""

    holder: object


def test_attribute_ref_str_and_relationship_ref_str() -> None:
    assert str(AttributeRef("Account", "owner")) == "Account.owner"
    assert str(RelationshipRef("Person", "passport")) == "Person.passport"


class WithStringRel(Entity, frozen=True):
    """A relationship declared under ``from __future__ import annotations`` (a string)."""

    __parallax__ = EntityConfig(table="with_string_rel", mutability="transactional")

    id: Attr[int] = Field(primary_key=True, type="int64")
    peer: Rel[object] = Relationship(
        cardinality="many-to-one",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="Peer", attribute="id")
        ),
    )


def test_string_annotation_relationship_is_unwrapped() -> None:
    record = entity_record_of(WithStringRel)
    assert record is not None
    relationship = record.relationships[0]
    assert isinstance(relationship, DefiningRelationship)
    assert relationship.join.target.entity == "Peer"


class FutureInferred(Entity, frozen=True):
    """Neutral-type inference under ``from __future__ import annotations`` (no ``type=``).

    This module stringizes annotations, so ``Attr[int]`` reaches the metaclass as
    the string ``"Attr[int]"``; inference must still resolve the inner type.
    """

    __parallax__ = EntityConfig(table="future_inferred", mutability="transactional")

    id: Attr[int] = Field(primary_key=True)
    name: Attr[str]
    active: Attr[bool] = Field(default=False)
    amount: Attr[Decimal] = Field(type="decimal(9,2)")


def test_future_annotations_infer_neutral_types_without_explicit_type() -> None:
    record = entity_record_of(FutureInferred)
    assert record is not None
    by_name = {attr.name: attr for attr in record.attributes}
    assert by_name["id"].type == "int64"
    assert by_name["name"].type == "string"
    assert by_name["active"].type == "boolean"
    assert by_name["amount"].type == "decimal(9,2)"


def test_future_annotation_explicit_type_survives_unresolvable_inner() -> None:
    # A name visible only in function scope is absent from the module globals the
    # resolver evaluates against, so the inner type stays a string; an explicit
    # `type=` means inference is never consulted and the class still compiles —
    # the fallback path that keeps forward references from breaking definitions.
    class LocalOnly:
        pass

    class WidgetWithUnresolvedInner(Entity, frozen=True):
        __parallax__ = EntityConfig(table="widget", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="int64")
        payload: Attr[LocalOnly] = Field(type="int64")

    record = entity_record_of(WidgetWithUnresolvedInner)
    assert record is not None
    assert {attr.name for attr in record.attributes} == {"id", "payload"}


def _define_invalid_neutral_type() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="widget")

    return Bad


def test_invalid_neutral_type_is_rejected_at_definition() -> None:
    with pytest.raises(EntityDefinitionError, match="not a neutral type"):
        _define_invalid_neutral_type()


def _define_out_of_range_max_length() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="int64")
        label: Attr[str] = Field(type="string", max_length=0)

    return Bad


def test_out_of_range_max_length_is_rejected_at_definition() -> None:
    with pytest.raises(EntityDefinitionError, match="maxLength"):
        _define_out_of_range_max_length()


def _define_wrong_typed_pk_generator() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(
            primary_key=True,
            type="int64",
            pk_generator={"strategy": "sequence", "batchSize": "not-an-int"},
        )

    return Bad


def test_wrong_typed_pk_generator_mapping_is_rejected_at_definition() -> None:
    # The malformed batchSize used to be coerced to None and the class defined
    # successfully, exporting a bare `pkGeneration: sequence`; now it is rejected.
    with pytest.raises(EntityDefinitionError, match="pk generator: `batchSize`"):
        _define_wrong_typed_pk_generator()


def _define_explicit_none_pk_generator() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(
            primary_key=True,
            type="int64",
            pk_generator={"strategy": "sequence", "batchSize": None},
        )

    return Bad


def test_explicit_none_pk_generator_field_is_rejected_at_definition() -> None:
    # A present optional key carrying `None` (distinct from an omitted key) is a
    # malformed declaration rejected when the class body is evaluated, naming the
    # offending NoneType — never silently normalized to a bare sequence strategy.
    with pytest.raises(EntityDefinitionError, match=r"`batchSize`.*NoneType"):
        _define_explicit_none_pk_generator()


def _define_omitted_optional_pk_generator() -> type:
    class Seq(Entity, frozen=True):
        __parallax__ = EntityConfig(table="seq_bare", mutability="transactional")

        id: Attr[int] = Field(
            primary_key=True,
            type="int64",
            pk_generator={"strategy": "sequence"},
        )

    return Seq


def test_omitted_optional_pk_generator_field_defines_and_exports() -> None:
    # Omitting every optional key (absent != None) is valid and collapses to the
    # bare sequence strategy, confirming the present-None rejection does not leak
    # into the legitimately-partial object form.
    seq = _define_omitted_optional_pk_generator()
    exported = cast("dict[str, object]", descriptor_document([seq])["entity"])
    attributes = cast("list[dict[str, object]]", exported["attributes"])
    assert attributes[0]["pkGeneration"] == "sequence"


def test_object_form_pk_generator_defines_and_exports() -> None:
    class SeqObjectForm(Entity, frozen=True):
        __parallax__ = EntityConfig(table="seq", mutability="transactional")

        id: Attr[int] = Field(
            primary_key=True,
            type="int64",
            pk_generator={
                "strategy": "sequence",
                "sequenceName": "seq_ids",
                "batchSize": 5,
                "initialValue": 100,
                "incrementSize": 10,
            },
        )

    exported = cast("dict[str, object]", descriptor_document([SeqObjectForm])["entity"])
    attributes = cast("list[dict[str, object]]", exported["attributes"])
    assert attributes[0]["pkGeneration"] == {
        "strategy": "sequence",
        "name": "seq_ids",
        "batchSize": 5,
        "initialValue": 100,
        "incrementSize": 10,
    }


def _define_string_plain_field() -> type:
    class Bad(Entity, frozen=True):
        __parallax__ = EntityConfig(table="bad", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="int64")
        qty: int = 5

    return Bad


def test_string_plain_annotation_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="Attr"):
        _define_string_plain_field()


def test_field_default_becomes_the_instance_default() -> None:
    class Toggle(Entity, frozen=True):
        __parallax__ = EntityConfig(table="toggle", mutability="transactional")

        id: Attr[int] = Field(primary_key=True, type="int64")
        active: Attr[bool] = Field(type="boolean", default=True)

    assert Toggle(id=1).active is True


def test_reserved_field_name_is_rejected() -> None:
    with pytest.raises(ReservedNameError):
        frontend_probes.define_reserved_name()


def test_canonical_name_collision_is_rejected() -> None:
    with pytest.raises(NameCollisionError):
        frontend_probes.define_name_collision()


def test_non_attr_field_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="Attr"):
        frontend_probes.define_non_attr_field()


def test_entity_without_attributes_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="no attributes"):
        frontend_probes.define_no_attributes()


def test_relationship_without_a_relationship_spec_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="Relationship"):
        frontend_probes.define_relationship_without_spec()


def test_bad_parallax_config_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="EntityConfig"):
        frontend_probes.define_bad_config()


def test_bad_mutability_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="mutability"):
        frontend_probes.define_bad_mutability()


def test_decimal_without_precision_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="decimal"):
        frontend_probes.define_decimal_without_type()


def test_unmapped_python_type_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="neutral type"):
        frontend_probes.define_unmapped_attribute()


def test_tx_temporal_base_declares_the_transaction_time_axis() -> None:
    # The temporal class spelling: extending `TxTemporal` injects the standard
    # `tx_start`/`tx_end` attributes (columns `in_z`/`out_z`) and the
    # Transaction-Time axis metadata into the shape owner's compiled record;
    # the effective temporal classification derives from the injected axes
    # exactly as for an ingested descriptor, and the typed statement surface
    # accepts the declared axis.
    from mirrored_models import Balance
    from parallax.core.entity import entity_records

    record = entity_records()["Balance"]
    assert record.temporal == "transaction-time-only"
    (axis,) = record.as_of_axes
    assert (axis.dimension, axis.start_attribute, axis.end_attribute) == (
        "transactionTime",
        "tx_start",
        "tx_end",
    )
    by_name = {attr.name: attr for attr in record.attributes}
    assert by_name["tx_start"].column == "in_z"
    assert by_name["tx_end"].column == "out_z"
    pinned = Balance.where().as_of(tx_time=dt.datetime(2024, 4, 1, tzinfo=dt.UTC))
    assert "asOf" in pinned.serialize()


def test_bitemporal_base_declares_both_axes_valid_time_first() -> None:
    # The standalone `Bitemporal` selection: both axes injected in canonical
    # Valid-Time-first order, the standard attributes appended AFTER the
    # user-declared members over the stable physical columns.
    class _FrontendBitemporalQuote(Bitemporal, frozen=True):
        __parallax__ = EntityConfig(table="frontend_bitemporal_quote")

        id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
        px: Attr[Decimal] = Field(type="decimal(18,2)")

    record = entity_record_of(_FrontendBitemporalQuote)
    assert record is not None
    assert record.temporal == "bitemporal"
    assert [
        (axis.dimension, axis.start_attribute, axis.end_attribute) for axis in record.as_of_axes
    ] == [
        ("validTime", "valid_start", "valid_end"),
        ("transactionTime", "tx_start", "tx_end"),
    ]
    assert [(attr.name, attr.column) for attr in record.attributes] == [
        ("id", "id"),
        ("px", "px"),
        ("valid_start", "from_z"),
        ("valid_end", "thru_z"),
        ("tx_start", "in_z"),
        ("tx_end", "out_z"),
    ]


def test_base_declared_entity_compiles_to_the_hand_authored_record() -> None:
    # Record equivalence: a base-declared entity and a class body hand-authoring
    # the identical standard `Attr` declarations compile to the same record —
    # the injection is invisible downstream (same attributes, columns, neutral
    # types, and axis metadata; only the class name differs).
    from dataclasses import replace

    class _FrontendEquivalenceTx(TxTemporal, frozen=True):
        __parallax__ = EntityConfig(table="frontend_equiv_ledger")

        id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
        amount: Attr[Decimal] = Field(type="decimal(18,2)")

    class _FrontendEquivalenceHand(Entity, frozen=True):
        __parallax__ = EntityConfig(table="frontend_equiv_ledger")

        id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
        amount: Attr[Decimal] = Field(type="decimal(18,2)")
        tx_start: Attr[dt.datetime] = Field(name="tx_start", column="in_z")
        tx_end: Attr[dt.datetime] = Field(name="tx_end", column="out_z")

    base_record = entity_record_of(_FrontendEquivalenceTx)
    hand_record = entity_record_of(_FrontendEquivalenceHand)
    assert base_record is not None
    assert hand_record is not None
    expected = replace(
        hand_record,
        name="_FrontendEquivalenceTx",
        as_of_axes=(
            AsOfAxisRecord(
                dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    assert base_record == expected


def test_redeclaring_a_standard_temporal_attribute_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="reserved"):

        class _FrontendBadRedeclare(TxTemporal, frozen=True):  # pyright: ignore[reportUnusedClass]
            __parallax__ = EntityConfig(table="frontend_bad_redeclare")

            id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
            tx_start: Attr[dt.datetime] = Field(name="tx_start", column="in_z")


def test_extending_both_temporal_bases_is_rejected() -> None:
    with pytest.raises(EntityDefinitionError, match="mutually exclusive"):

        class _FrontendBadDualBase(  # pyright: ignore[reportUnusedClass]
            TxTemporal, Bitemporal, frozen=True
        ):
            __parallax__ = EntityConfig(table="frontend_bad_dual_base")

            id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
