"""Exact structural grading after declared-type canonical projection."""

from __future__ import annotations

from decimal import Decimal

from reference_harness._structural import is_structural_sequence
from reference_harness.case import FrozenDict, FrozenList
from reference_harness.case_assertions import rows_equal, scalars_equal
from reference_harness.portable_literal import AuthoredInteger, AuthoredNumber, values_equal


def test_distinct_high_precision_decimals_are_not_equal() -> None:
    # Two different cent amounts beyond float's ~15-16 significant digits. float()
    # collapses both to the SAME double; exact Decimal comparison must not.
    a = [{"amount": Decimal("1234567890123456.78")}]
    b = [{"amount": Decimal("1234567890123456.79")}]
    assert not rows_equal(a, b)


def test_untyped_carrier_differences_are_not_repaired() -> None:
    assert not rows_equal([{"n": Decimal("2.0")}], [{"n": 2}])
    assert not rows_equal([{"n": 2}], [{"n": 2.0}])
    assert not rows_equal([{"p": Decimal("10.50")}], [{"p": 10.5}])


def test_declared_type_projection_is_the_only_cross_carrier_equivalence() -> None:
    assert values_equal(Decimal("10.50"), "10.50", "decimal(12,2)", None)
    assert not scalars_equal(Decimal("10.50"), "10.50", None)


def test_retained_json_number_tokens_equal_the_same_native_carrier() -> None:
    assert scalars_equal(AuthoredInteger("2"), 2, None)
    assert scalars_equal(AuthoredNumber("1.5"), 1.5, None)
    assert not scalars_equal(AuthoredInteger("2"), 2.0, None)


def test_bool_and_none_stay_out_of_numeric_space() -> None:
    assert scalars_equal(True, True, None)
    assert not scalars_equal(True, 1, None)  # bool is not coerced into 1
    assert scalars_equal(None, None, None)
    assert not scalars_equal(None, 0, None)  # None never enters Decimal space


def test_tolerance_allows_inexact_match() -> None:
    actual = Decimal("1.5811388300841897")  # an irrational stddev as Postgres returns it
    authored = 1.5811388301  # the human-readable rounded value in the fixture
    assert not scalars_equal(actual, authored, None)  # exact: they differ
    assert scalars_equal(actual, authored, Decimal("1e-9"))  # tolerant: match


def test_tolerance_still_catches_real_differences() -> None:
    # A tolerant case does not become a free pass: integral columns stay
    # effectively exact (an off-by-one is ~1e9x the tolerance).
    assert not scalars_equal(Decimal("2"), 3, Decimal("1e-9"))
    assert not rows_equal([{"c": 5}], [{"c": 6}], tolerance=Decimal("1e-9"))


def test_order_insensitive_multiset() -> None:
    assert rows_equal([{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 1}])
    assert not rows_equal([{"id": 1}], [{"id": 1}, {"id": 2}])


def test_ordinary_and_frozen_nested_wire_containers_compare_by_structure() -> None:
    ordinary = [
        {
            "id": 1,
            "payload": {"labels": ["alpha", {"rank": 2}], "active": True},
        }
    ]
    frozen = [
        FrozenDict(
            {
                "id": 1,
                "payload": FrozenDict(
                    {
                        "labels": FrozenList(["alpha", FrozenDict({"rank": 2})]),
                        "active": True,
                    }
                ),
            }
        )
    ]

    assert rows_equal(ordinary, frozen)
    assert rows_equal(frozen, ordinary)


def test_nested_structural_comparison_keeps_keys_positions_and_scalar_types_exact() -> None:
    frozen = [
        FrozenDict(
            {
                "payload": FrozenDict(
                    {"values": FrozenList([FrozenDict({"kind": "count", "value": 1}), 2])}
                )
            }
        )
    ]

    assert not rows_equal([{"payload": {"values": [{"kind": "total", "value": 1}, 2]}}], frozen)
    assert not rows_equal([{"payload": {"values": [2, {"kind": "count", "value": 1}]}}], frozen)
    assert not rows_equal([{"payload": {"values": [{"kind": "count", "value": 1.0}, 2]}}], frozen)


def test_structural_sequences_exclude_every_text_and_binary_scalar_carrier() -> None:
    assert is_structural_sequence([1, 2])
    assert is_structural_sequence(FrozenList([1, 2]))
    assert not is_structural_sequence("12")
    assert not is_structural_sequence(b"12")
    assert not is_structural_sequence(bytearray(b"12"))
    assert not is_structural_sequence(memoryview(b"12"))
