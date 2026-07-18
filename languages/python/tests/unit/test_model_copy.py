"""D-16 full graduation (DQ1, COR-3 Phase 7 increment 6a): the validating
``model_copy`` override and its Change Record — ``changed_fields`` /
``effective_change_set`` / ``full_row`` / ``primary_key_row`` /
``canonical_row`` (spec §3/§5). The version column's own advance is
framework-owned end to end at the write seam (`m-opt-lock`, COR-3 Phase 8
increment 3) — ``framework_owned_advance`` retired with the provisional M4-era
shape it reproduced; see ``test_write_lowering.py`` / ``test_opt_lock.py``.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

import mirrored_models as mm
import snapshot_models as sm
import value_object_models as vm
from parallax.core.base import INFINITY
from parallax.core.descriptor import UNSET
from parallax.core.entity import (
    EntityDefinitionError,
    ModelCopyError,
    ProvenanceError,
    canonical_row,
    changed_fields,
    effective_change_set,
    entity_record_of,
    full_row,
    primary_key_row,
    wire_names_of,
)
from parallax.core.entity.base import FrameworkOwnedAxisError

pytestmark = pytest.mark.unit


def _account(balance: str = "100.00", version: int = 1) -> mm.Account:
    return mm.Account(id=1, owner="Ada", balance=Decimal(balance), version=version)


# --------------------------------------------------------------------------- #
# Provenance and the Change Record.                                          #
# --------------------------------------------------------------------------- #
def test_a_fresh_instance_carries_no_change_record() -> None:
    assert changed_fields(_account()) is None


def test_model_copy_records_the_earliest_original_value() -> None:
    original = _account(balance="100.00")
    edited = original.model_copy(update={"balance": Decimal("175.00")})
    assert edited.balance == Decimal("175.00")
    changes = changed_fields(edited)
    assert changes is not None
    assert changes["balance"] == Decimal("100.00")


def test_copies_of_copies_merge_records_keeping_the_earliest_original() -> None:
    original = _account(balance="100.00")
    once = original.model_copy(update={"balance": Decimal("150.00")})
    twice = once.model_copy(update={"balance": Decimal("200.00")})
    changes = changed_fields(twice)
    assert changes is not None
    assert changes["balance"] == Decimal("100.00")  # earliest, not 150.00
    assert twice.balance == Decimal("200.00")


def test_a_net_zero_chain_still_tracks_the_touch_but_drops_from_the_effective_set() -> None:
    original = _account(balance="100.00")
    round_tripped = original.model_copy(update={"balance": Decimal("200.00")}).model_copy(
        update={"balance": Decimal("100.00")}
    )
    changes = changed_fields(round_tripped)
    assert changes is not None
    assert "balance" in changes  # touched...
    assert effective_change_set(round_tripped) == {}  # ...but nets to zero


def test_effective_change_set_includes_only_touched_and_different_fields() -> None:
    original = _account(balance="100.00")
    edited = original.model_copy(update={"balance": Decimal("175.00")})
    assert effective_change_set(edited) == {"balance": Decimal("175.00")}


def test_a_plain_copy_with_no_update_carries_forward_the_existing_record() -> None:
    original = _account(balance="100.00")
    edited = original.model_copy(update={"balance": Decimal("175.00")})
    plain = edited.model_copy()
    assert changed_fields(plain) == changed_fields(edited)


def test_effective_change_set_raises_provenance_error_for_a_fresh_instance() -> None:
    with pytest.raises(ProvenanceError, match="Change Record"):
        effective_change_set(_account())


# --------------------------------------------------------------------------- #
# model_copy validation: unknown / primary-key / framework-owned / relationship. #
# --------------------------------------------------------------------------- #
def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ModelCopyError, match="unknown field"):
        _account().model_copy(update={"shoe_size": 9})


def test_primary_key_field_is_rejected() -> None:
    with pytest.raises(ModelCopyError, match="primary-key"):
        _account().model_copy(update={"id": 2})


def test_framework_owned_field_is_rejected() -> None:
    with pytest.raises(ModelCopyError, match="framework-owned"):
        _account().model_copy(update={"version": 99})


def test_relationship_field_is_rejected() -> None:
    person = mm.Person(id=1, name="Ada")
    with pytest.raises(ModelCopyError, match="relationship"):
        person.model_copy(update={"passport": None})


def test_an_invalid_scalar_value_raises_at_copy_time_not_at_the_database() -> None:
    with pytest.raises(Exception):  # noqa: B017 - Pydantic's own validation error type
        _account().model_copy(update={"balance": "not-a-decimal"})


# --------------------------------------------------------------------------- #
# Write-row builders (spec §5).                                              #
# --------------------------------------------------------------------------- #
def test_full_row_projects_every_field_the_caller_set() -> None:
    account = _account(balance="5.00", version=1)
    assert full_row(account) == {
        "id": 1,
        "owner": "Ada",
        "balance": Decimal("5.00"),
        "version": 1,
    }


def test_primary_key_row_projects_only_the_declared_keys() -> None:
    assert primary_key_row(_account()) == {"id": 1}


def test_canonical_row_translates_python_names_to_canonical_names() -> None:
    account = _account()
    assert canonical_row(account, {"balance": Decimal("9.99")}) == {"balance": Decimal("9.99")}


def test_full_row_serializes_a_value_object_member_to_its_canonical_document() -> None:
    address = vm.Address(street="Main St", city="Berlin", geo=None, phones=())
    customer = vm.Customer(id=1, name="Ada", address=address)
    row = full_row(customer)
    assert row["address"] == {"street": "Main St", "city": "Berlin", "geo": None, "phones": []}


def test_full_row_serializes_a_cardinality_many_value_object_member_to_a_list_of_documents() -> (
    None
):
    tag = sm.Tag(label="a", detail=None, details=())
    status = sm.SnapOrderStatus(
        id=1,
        order_id=1,
        order_item_id=None,
        code="shipped",
        primary_tag=None,
        tags=(tag,),
    )
    row = full_row(status)
    assert row["tags"] == [{"label": "a", "detail": None, "details": []}]


def test_wire_names_of_rejects_a_non_compiled_entity_class() -> None:
    with pytest.raises(EntityDefinitionError, match="not a compiled Parallax entity class"):
        wire_names_of(int)


# --------------------------------------------------------------------------- #
# D-31 (COR-3 Phase 8 increment 7 completion round): axis-governed attributes #
# are optional at construction, and a caller-supplied one on a fresh instance #
# raises loudly at `full_row` (the `insert`/`insert_until` Create Payload     #
# seam) rather than being silently discarded downstream.                     #
# --------------------------------------------------------------------------- #
def test_an_audit_only_instance_constructs_cleanly_without_axis_values() -> None:
    balance = mm.Balance(id=1, acct_num="A", value=Decimal("100.00"))
    assert balance.processing_from is None
    assert balance.processing_to is None
    assert full_row(balance) == {"id": 1, "acctNum": "A", "value": Decimal("100.00")}


def test_a_bitemporal_instance_constructs_cleanly_without_axis_values() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    assert branch.business_from is None
    assert branch.business_to is None
    assert branch.processing_from is None
    assert branch.processing_to is None
    assert full_row(branch) == {"id": 1, "name": "Central", "address": None}


def test_supplying_a_processing_axis_value_at_construction_raises_on_full_row() -> None:
    balance = mm.Balance(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        processing_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    )
    with pytest.raises(FrameworkOwnedAxisError, match="processing_from"):
        full_row(balance)


def test_supplying_a_business_axis_value_at_construction_raises_on_full_row() -> None:
    branch = mm.Branch(
        id=1, name="Central", address=None, business_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    )
    with pytest.raises(FrameworkOwnedAxisError, match="business_from"):
        full_row(branch)


def test_a_non_temporal_class_declares_no_axis_governed_fields() -> None:
    assert wire_names_of(mm.Account).axis_governed_py == frozenset()


def test_the_exported_descriptor_carries_no_default_for_an_axis_attribute() -> None:
    # D-31's Pydantic-level `None` default is a frontend construction
    # affordance ONLY — the compiled descriptor stays byte-identical (the
    # descriptor no-drift guard is the proof; this pin is the unit-level
    # half of it).
    record = entity_record_of(mm.Balance)
    assert record is not None
    processing_from = next(a for a in record.attributes if a.name == "processingFrom")
    assert processing_from.default is UNSET


# --------------------------------------------------------------------------- #
# Discovered building the COR-3 Phase 8 increment 7 completion round's        #
# temporal write-family stories: a materialized CURRENT milestone's real      #
# `out_z`/`thru_z` value is the framework's own open-interval sentinel        #
# (`TemporalBound.INFINITY` — every real Postgres current row decodes to      #
# exactly this, `parallax.postgres.adapter._InfinityTimestamptzLoader`),      #
# which the WRAP construction that materializes it never validates           #
# (`model_construct`) — so `model_copy`'s own untouched-field revalidation    #
# must carry an axis-governed field's CURRENT value forward WITHOUT ever     #
# passing it back through the validating constructor.                        #
# --------------------------------------------------------------------------- #
def test_model_copy_carries_forward_an_untouched_axis_fields_infinity_sentinel() -> None:
    balance = mm.Balance.model_construct(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        processing_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        processing_to=INFINITY,
    )
    copy = balance.model_copy(update={"value": Decimal("150.00")})
    assert copy.value == Decimal("150.00")
    assert copy.processing_to is INFINITY  # carried forward, never re-validated


def test_model_copy_still_validates_an_explicitly_touched_axis_field() -> None:
    balance = mm.Balance.model_construct(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        processing_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        processing_to=INFINITY,
    )
    with pytest.raises(ValueError, match="processing_to"):
        balance.model_copy(update={"processing_to": "not-a-datetime"})
