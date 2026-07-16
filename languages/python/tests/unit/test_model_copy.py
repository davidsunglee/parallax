"""D-16 full graduation (DQ1, COR-3 Phase 7 increment 6a): the validating
``model_copy`` override and its Change Record — ``changed_fields`` /
``effective_change_set`` / ``full_row`` / ``primary_key_row`` /
``canonical_row`` (spec §3/§5). The version column's own advance is
framework-owned end to end at the write seam (`m-opt-lock`, COR-3 Phase 8
increment 3) — ``framework_owned_advance`` retired with the provisional M4-era
shape it reproduced; see ``test_write_lowering.py`` / ``test_opt_lock.py``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

import mirrored_models as mm
import snapshot_models as sm
import value_object_models as vm
from parallax.core.entity import (
    EntityDefinitionError,
    ModelCopyError,
    ProvenanceError,
    canonical_row,
    changed_fields,
    effective_change_set,
    full_row,
    primary_key_row,
    wire_names_of,
)

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
