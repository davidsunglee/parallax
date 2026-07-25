"""m-descriptor derived facts: temporal classification, column order, and the
family-root ancestry walk (``declaring_entity``)."""

from __future__ import annotations

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core.descriptor import (
    AsOfAxisMetadata,
    Attribute,
    DescriptorError,
    Entity,
    Inheritance,
    Metamodel,
    PkGenerator,
    ValueObject,
    column_order,
    declaring_entity,
)

pytestmark = pytest.mark.unit

_MODELS = corpus_models.load_models(
    case_format.find_repo_root() / "core" / "compatibility" / "models"
)

_PROC = AsOfAxisMetadata(
    dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
)
_BIZ = AsOfAxisMetadata(
    dimension="validTime", start_attribute="valid_start", end_attribute="valid_end"
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


def test_column_order_places_pk_first_then_scalars_then_documents() -> None:
    account = _MODELS["account"].entity("Account")
    assert column_order(account) == ("id", "owner", "balance", "version")
    customer = _MODELS["customer"].entity("Customer")
    assert column_order(customer) == ("id", "name", "address")


def test_column_order_slots_the_tag_column_after_the_primary_key() -> None:
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
    assert column_order(root) == ("id", "kind", "name", "badge")


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
                dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
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
                dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    meta = Metamodel(entities=(plain,))
    assert declaring_entity(meta, plain) is plain
