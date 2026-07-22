"""m-descriptor derived facts: temporal classification and column order."""

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
    PkGenerator,
    ValueObject,
    column_order,
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
