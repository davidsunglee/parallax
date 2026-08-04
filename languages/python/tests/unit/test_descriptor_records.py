"""m-descriptor derived facts: temporal classification, preserved local
declarations, and the family-root ancestry walk (``declaring_entity``)."""

from __future__ import annotations

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.descriptor import _records
from parallax.descriptor._errors import DescriptorError
from parallax.descriptor._records import (
    AsOfAxisMetadata,
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    PkGenerator,
    ValueObject,
    concrete_descendant_names,
    declaring_entity,
    family_root_name,
)

_MODELS = corpus_models.load_models(
    case_format.find_repo_root() / "core" / "compatibility" / "models"
)

_PROC = AsOfAxisMetadata(
    dimension="transaction-time", start_attribute="tx_start", end_attribute="tx_end"
)
_BIZ = AsOfAxisMetadata(
    dimension="valid-time", start_attribute="valid_start", end_attribute="valid_end"
)


@pytest.mark.parametrize(
    ("axes", "expected"),
    [
        ((), "non-temporal"),
        ((_PROC,), "transaction-time-only"),
        ((_PROC, _BIZ), "bitemporal"),
    ],
)
def test_temporal_is_derived_from_the_as_of_axes(
    axes: tuple[AsOfAxisMetadata, ...], expected: str
) -> None:
    entity = Entity(
        name="E",
        table="e",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="valid_start", type="timestamp", column="b_in"),
            Attribute(name="valid_end", type="timestamp", column="b_out"),
            Attribute(name="tx_start", type="timestamp", column="in_z"),
            Attribute(name="tx_end", type="timestamp", column="out_z"),
        ),
        as_of_axes=axes,
    )
    assert entity.temporal == expected
    assert entity.is_temporal is bool(axes)


def test_valid_time_only_has_no_runtime_classification() -> None:
    entity = Entity(
        name="E",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        as_of_axes=(_BIZ,),
    )
    with pytest.raises(DescriptorError, match="Valid-Time-Only is deferred"):
        _ = entity.temporal


def test_corpus_temporal_classifications_match() -> None:
    assert _MODELS["account"].entity("Account").temporal == "non-temporal"
    assert _MODELS["balance"].entity("Balance").temporal == "transaction-time-only"


def test_primary_key_selects_declared_pk_attributes_in_order() -> None:
    balance = _MODELS["balance"].entity("Balance")
    assert tuple(a.name for a in balance.primary_key) == ("id",)


def test_records_preserve_local_declarations_and_their_effective_columns() -> None:
    account = _MODELS["account"].entity("Account")
    assert tuple((a.name, a.column) for a in account.attributes) == (
        ("id", "id"),
        ("owner", "owner"),
        ("balance", "balance"),
        ("version", "version"),
    )
    customer = _MODELS["customer"].entity("Customer")
    assert tuple((a.name, a.column) for a in customer.attributes) == (
        ("id", "id"),
        ("name", "name"),
    )
    assert tuple((v.name, v.storage_column) for v in customer.value_objects) == (
        ("address", "address"),
    )


def test_records_retain_the_tag_declaration_without_composing_a_column_sequence() -> None:
    # The framework-owned tag is a declaration on the root's strategy, and these
    # records carry it as one. Where it sits among the table's columns — and where
    # a document column sits — is `m-storage-layout`'s answer, not a descriptor fact.
    root = Entity(
        name="Animal",
        table="animal",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="name", type="string", column="name"),
        ),
        value_objects=(ValueObject(name="badge", column="badge"),),
    )
    assert root.inheritance is not None
    assert root.inheritance.tag_column == "kind"
    assert tuple(a.column for a in root.attributes) == ("id", "name")
    assert tuple(v.storage_column for v in root.value_objects) == ("badge",)
    assert not hasattr(_records, "column_order")


def test_pk_generator_generates_flags_max_and_sequence() -> None:
    assert PkGenerator(strategy="none").generates is False
    assert PkGenerator(strategy="max").generates is True
    assert PkGenerator(strategy="sequence", sequence_name="s").generates is True


# --------------------------------------------------------------------------- #
# Binding decision: temporality is a                                          #
# family-wide property; only the root may declare `asOfAxes`, and every       #
# descendant — abstract-subtype or concrete-subtype — inherits exactly that   #
# set. `declaring_entity` always resolves to the family root; a non-root      #
# participant that declares its own axes is rejected pre-SQL                  #
# (`parallax.conformance._descriptor_family.validate`).                       #
# --------------------------------------------------------------------------- #
def _synthetic_temporal_family() -> Metamodel:
    """A THREE-level TPH family — Root (temporal) -> Mid (abstract-subtype) ->
    Leaf (concrete) — proving `declaring_entity` resolves to the root from
    EVERY position in the chain, not just the immediate parent."""
    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="tx_start", type="timestamp", column="in_z"),
            Attribute(name="tx_end", type="timestamp", column="out_z"),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transaction-time", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    mid = Entity(
        name="Mid",
        inheritance=Inheritance(role="abstract-subtype", parent="Root"),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Mid", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return Metamodel(entities=(root, mid, leaf))


def _cyclic_pair() -> Metamodel:
    attrs = (Attribute(name="id", type="int64", column="id", primary_key=True),)
    return Metamodel(
        entities=(
            Entity(
                name="A",
                table="a",
                inheritance=Inheritance(role="concrete-subtype", parent="B"),
                attributes=attrs,
            ),
            Entity(
                name="B",
                table="b",
                inheritance=Inheritance(role="concrete-subtype", parent="A"),
                attributes=attrs,
            ),
        )
    )


def test_family_root_name_resolves_a_root_and_reports_none_off_a_family() -> None:
    meta = _synthetic_temporal_family()
    for name in ("Root", "Mid", "Leaf"):
        assert family_root_name(meta, meta.entity(name)) == "Root", name
    plain = Entity(name="Solo", table="solo", attributes=())
    assert family_root_name(Metamodel(entities=(plain,)), plain) is None


def test_family_root_name_is_none_for_an_ancestry_that_reaches_no_root() -> None:
    cyclic = _cyclic_pair()
    assert family_root_name(cyclic, cyclic.entity("A")) is None


def test_concrete_descendant_names_collects_every_concrete_at_or_below() -> None:
    # A concrete node that is itself a parent contributes BOTH itself and its
    # concrete descendants: the effective set is every concrete node at or below
    # the position, so descent never stops at the first concrete one.
    attrs = (Attribute(name="id", type="int64", column="id", primary_key=True),)
    meta = Metamodel(
        entities=(
            Entity(
                name="Root",
                inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
                attributes=attrs,
            ),
            Entity(
                name="Middle",
                table="middle",
                inheritance=Inheritance(role="concrete-subtype", parent="Root"),
                attributes=attrs,
            ),
            Entity(
                name="Below",
                table="below",
                inheritance=Inheritance(role="concrete-subtype", parent="Middle"),
                attributes=attrs,
            ),
        )
    )
    assert concrete_descendant_names(meta, "Root") == frozenset({"Middle", "Below"})
    assert concrete_descendant_names(meta, "Middle") == frozenset({"Middle", "Below"})
    assert concrete_descendant_names(meta, "Below") == frozenset({"Below"})


def test_concrete_descendant_names_terminates_on_a_cyclic_family() -> None:
    assert concrete_descendant_names(_cyclic_pair(), "A") == frozenset({"A", "B"})


def test_declaring_entity_resolves_to_the_family_root_from_every_position() -> None:
    meta = _synthetic_temporal_family()
    for name in ("Root", "Mid", "Leaf"):
        declaring = declaring_entity(meta, meta.entity(name))
        assert declaring.name == "Root", name
        assert declaring.as_of_axes == meta.entity("Root").as_of_axes


def test_declaring_entity_is_the_entity_itself_outside_a_family() -> None:
    # A non-inheritance temporal entity remains unaffected: `declaring_entity`
    # is a strict identity for it (m-inheritance only applies within a family).
    plain = Entity(
        name="Balance",
        table="balance",
        attributes=(
            Attribute(name="id", type="int64", column="bal_id", primary_key=True),
            Attribute(name="tx_start", type="timestamp", column="in_z"),
            Attribute(name="tx_end", type="timestamp", column="out_z"),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transaction-time", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    meta = Metamodel(entities=(plain,))
    assert declaring_entity(meta, plain) is plain
