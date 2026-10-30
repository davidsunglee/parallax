"""m-storage-layout: each temporal Table's axes and their interval check names."""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from parallax.core import storage_layout
from parallax.core.metamodel import Column, Metamodel, Table, TemporalDimension
from parallax.core.storage_layout import PhysicalTemporalAxis, TableLayout
from parallax.core.storage_layout._temporal import constraint_name
from tests.unit._corpus_model_support import corpus, corpus_records, formed

_INTERVAL = (("lt", (Column("in_z"), Column("out_z"))),)


def _layout(model: Metamodel, table: str) -> TableLayout:
    layout = storage_layout.view(model).table(Table(table))
    assert layout is not None
    return layout


def _names(model: Metamodel) -> dict[str, tuple[str, str | None]]:
    named: dict[str, tuple[str, str | None]] = {}
    for layout in storage_layout.view(model).tables:
        constraints = layout.temporal_constraints
        if constraints is not None:
            valid = constraints.valid_axis
            named[layout.table.name] = (
                constraints.transaction_axis.interval_check_name,
                None if valid is None else valid.interval_check_name,
            )
    return named


def _selects_own_slots(layout: TableLayout, axis: PhysicalTemporalAxis) -> None:
    assert axis.start in layout.columns
    assert axis.end in layout.columns
    assert layout.contribution(axis.declaration.start_attribute) is axis.start
    assert layout.contribution(axis.declaration.end_attribute) is axis.end


def test_a_transaction_time_table_carries_one_interval_check() -> None:
    layout = _layout(corpus()["balance"], "balance")
    constraints = layout.temporal_constraints
    assert constraints is not None
    assert constraints.valid_axis is None
    axis = constraints.transaction_axis
    assert axis.declaration.dimension is TemporalDimension.TRANSACTION_TIME
    assert (axis.start.column, axis.end.column) == (Column("in_z"), Column("out_z"))
    assert axis.interval_check_name == "pxc_tx_balance_c54215aec2277be436e89b2c6506715d"
    _selects_own_slots(layout, axis)


def test_a_bitemporal_table_carries_both_interval_checks() -> None:
    layout = _layout(corpus()["position"], "position")
    constraints = layout.temporal_constraints
    assert constraints is not None
    valid = constraints.valid_axis
    assert valid is not None
    assert valid.declaration.dimension is TemporalDimension.VALID_TIME
    assert (valid.start.column, valid.end.column) == (Column("from_z"), Column("thru_z"))
    assert _names(corpus()["position"]) == {
        "position": (
            "pxc_tx_position_05e7b5d0b3866810c782a91a8d1f7971",
            "pxc_valid_position_9c4697753a4cc41ed976ab6ee1f1f88b",
        )
    }
    _selects_own_slots(layout, valid)
    _selects_own_slots(layout, constraints.transaction_axis)


@pytest.mark.parametrize(
    ("stem", "table", "ends"),
    [("balance", "balance", ("out_z",)), ("position", "position", ("thru_z", "out_z"))],
)
def test_the_axis_ends_are_the_tables_own_end_slots_valid_time_first(
    stem: str, table: str, ends: tuple[str, ...]
) -> None:
    layout = _layout(corpus()[stem], table)
    constraints = layout.temporal_constraints
    assert constraints is not None
    assert tuple(slot.column.name for slot in constraints.axis_ends) == ends
    assert constraints.axis_ends == tuple(
        slot for slot in constraints.primary_key.columns if slot not in constraints.logical_key
    )


def test_a_non_temporal_table_has_no_temporal_constraints() -> None:
    assert _layout(corpus()["payment"], "payment").temporal_constraints is None


def test_a_shared_table_carries_the_roots_axes_once() -> None:
    model = corpus()["instrument"]
    layout = _layout(model, "instrument")
    constraints = layout.temporal_constraints
    assert constraints is not None and constraints.valid_axis is not None
    root = model.entity(constraints.transaction_axis.declaration.start_attribute.entity)
    assert root is not None
    assert root.inheritance is not None and root.declared_container == Table("instrument")
    _selects_own_slots(layout, constraints.transaction_axis)
    _selects_own_slots(layout, constraints.valid_axis)


def test_each_concrete_table_carries_the_roots_axes_over_its_own_slots() -> None:
    model = corpus()["rate"]
    deposit = _layout(model, "deposit_rate").temporal_constraints
    loan = _layout(model, "loan_rate").temporal_constraints
    assert deposit is not None and loan is not None
    assert deposit.transaction_axis.declaration == loan.transaction_axis.declaration
    assert deposit.transaction_axis.start != loan.transaction_axis.start
    assert _names(model) == {
        "deposit_rate": (
            "pxc_tx_deposit_rate_414fd0086fa88b25167aa860be1092ee",
            "pxc_valid_deposit_rate_3097360c14aad9c89002e5dbda0af17b",
        ),
        "loan_rate": (
            "pxc_tx_loan_rate_363a31cea1b97498697d7a6fb5a555ba",
            "pxc_valid_loan_rate_e484575d67cc8dc583c0e35f7e6bc9a2",
        ),
    }


def test_the_storage_layout_does_not_move_a_name() -> None:
    # Under Document the endpoints stay direct Columns beside the shared
    # Structured Column, so the twins' physical definitions are the same.
    columns = corpus()["shared-coverage-layout-twin-columns"]
    document = corpus()["shared-coverage-layout-twin-document"]
    assert _names(columns) == _names(document)
    layout = _layout(document, "coverage_span")
    constraints = layout.temporal_constraints
    assert constraints is not None
    _selects_own_slots(layout, constraints.transaction_axis)


def test_unrelated_identities_and_declaration_order_do_not_move_a_name() -> None:
    position = corpus_records()["position"]
    balance = corpus_records()["balance"]
    (entity,) = position.entities
    renamed = dataclasses.replace(entity, name="Holding", namespace="elsewhere")
    together = formed(dataclasses.replace(position, entities=(*balance.entities, renamed)))
    reversed_order = formed(dataclasses.replace(position, entities=(renamed, *balance.entities)))
    expected = _names(corpus()["position"]) | _names(corpus()["balance"])
    assert _names(together) == expected
    assert _names(reversed_order) == expected


def test_the_fingerprint_hashes_the_complete_encoding() -> None:
    encoding = (
        b"\x00\x00\x00\x05pxc-1"
        b"\x00\x00\x00\x07balance"
        b"\x00\x00\x00\x02tx"
        b"\x00\x00\x00\x011"
        b"\x00\x00\x00\x02lt"
        b"\x00\x00\x00\x012"
        b"\x00\x00\x00\x04in_z"
        b"\x00\x00\x00\x05out_z"
    )
    fingerprint = hashlib.sha256(encoding).hexdigest()[:32]
    assert constraint_name(Table("balance"), "tx", _INTERVAL) == f"pxc_tx_balance_{fingerprint}"


def test_operand_group_boundaries_reach_the_fingerprint() -> None:
    one_group = constraint_name(Table("t"), "tx", _INTERVAL)
    two_groups = constraint_name(
        Table("t"), "tx", (("lt", (Column("in_z"),)), ("lt", (Column("out_z"),)))
    )
    assert one_group != two_groups


@pytest.mark.parametrize(
    ("table", "kind", "expected"),
    [
        (
            'Ünïcode Tàble "quoted" name that runs well past the readable budget',
            "tx",
            "pxc_tx_n_code_t_ble_quoted_nam_358522fa9e0b137ec644de840165c1c9",
        ),
        (
            'Ünïcode Tàble "quoted" name that runs well past the readable budget',
            "valid",
            "pxc_valid_n_code_t_ble_quoted_f007c893325cc71df9afe6e3f0adeb82",
        ),
        ("a" * 80, "tx", "pxc_tx_aaaaaaaaaaaaaaaaaaaaaaa_d4730c4aedc190f433484ce5737639c4"),
        ('Order"Lines', "tx", "pxc_tx_order_lines_2bc6d189d76f385c53728c05b4c17085"),
        ("Ωμέγα", "tx", "pxc_tx_table_59f0e8b3fa6d6ad94c6e41195b5b8032"),
        ("__x__", "valid", "pxc_valid_x_8fdc84ca18bb53fe6935cf5138695843"),
    ],
)
def test_only_the_readable_prefix_bends_to_the_63_byte_budget(
    table: str, kind: str, expected: str
) -> None:
    name = constraint_name(Table(table), kind, _INTERVAL)
    assert name == expected
    assert len(name.encode("utf-8")) <= 63


def _keys(model: Metamodel) -> dict[str, tuple[str, str, tuple[str, ...]]]:
    named: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for layout in storage_layout.view(model).tables:
        constraints = layout.temporal_constraints
        if constraints is not None:
            named[layout.table.name] = (
                constraints.primary_key_name,
                constraints.exclusion_name,
                tuple(slot.column.name for slot in constraints.logical_key),
            )
    return named


def test_a_temporal_table_names_its_own_primary_key_and_exclusion() -> None:
    layout = _layout(corpus()["position"], "position")
    constraints = layout.temporal_constraints
    assert constraints is not None
    assert constraints.primary_key is layout.primary_key_index
    assert _keys(corpus()["position"]) == {
        "position": (
            "pxc_pk_position_6033a9b256fa65fb6a06ae764dd7905d",
            "pxc_excl_position_e5c6616a7f7cfbf6c981cf0ad0f86610",
            ("pos_id",),
        )
    }


def test_a_shared_table_keys_history_by_the_root_key_and_never_the_tag() -> None:
    model = corpus()["instrument"]
    layout = _layout(model, "instrument")
    constraints = layout.temporal_constraints
    assert constraints is not None
    assert [slot.column.name for slot in constraints.logical_key] == ["id"]
    assert all(slot in layout.columns for slot in constraints.logical_key)
    assert not any(
        slot.tier is storage_layout.ColumnTier.DISCRIMINATOR for slot in constraints.logical_key
    )


def test_each_concrete_table_keys_its_own_history() -> None:
    keys = _keys(corpus()["rate"])
    assert keys["deposit_rate"][2] == keys["loan_rate"][2] == ("id",)
    assert keys["deposit_rate"][:2] != keys["loan_rate"][:2]


def test_the_storage_layout_does_not_move_a_key_or_exclusion_name() -> None:
    columns = corpus()["shared-coverage-layout-twin-columns"]
    document = corpus()["shared-coverage-layout-twin-document"]
    assert _keys(columns) == _keys(document)


def test_unrelated_identities_do_not_move_a_key_or_exclusion_name() -> None:
    position = corpus_records()["position"]
    (entity,) = position.entities
    renamed = formed(
        dataclasses.replace(
            position, entities=(dataclasses.replace(entity, name="Holding", namespace="x"),)
        )
    )
    assert _keys(renamed) == _keys(corpus()["position"])


def _encoded(*fields: str) -> bytes:
    return b"".join(len(field.encode()).to_bytes(4, "big") + field.encode() for field in fields)


def test_the_primary_key_and_exclusion_fingerprints_hash_their_complete_encodings() -> None:
    primary_key = _encoded("pxc-1", "balance", "pk", "1", "unique", "2", "bal_id", "out_z")
    exclusion = _encoded(
        "pxc-1", "balance", "excl", "2", "eq", "1", "bal_id", "overlap", "2", "in_z", "out_z"
    )
    assert _keys(corpus()["balance"])["balance"] == (
        f"pxc_pk_balance_{hashlib.sha256(primary_key).hexdigest()[:32]}",
        f"pxc_excl_balance_{hashlib.sha256(exclusion).hexdigest()[:32]}",
        ("bal_id",),
    )


def test_a_bitemporal_exclusion_lists_valid_time_before_transaction_time() -> None:
    exclusion = _encoded(
        "pxc-1",
        "position",
        "excl",
        "3",
        "eq",
        "1",
        "pos_id",
        "overlap",
        "2",
        "from_z",
        "thru_z",
        "overlap",
        "2",
        "in_z",
        "out_z",
    )
    assert _keys(corpus()["position"])["position"][1] == (
        f"pxc_excl_position_{hashlib.sha256(exclusion).hexdigest()[:32]}"
    )
