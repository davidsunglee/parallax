"""Unit tests for deep-fetch object-graph comparison.

Graph comparison must use the same exact numeric semantics as flat row
comparison. The old graph path normalized leaves through ``float``-or-``int``
coercion and then compared serialized strings, which could make distinct
``Decimal`` values compare equal inside ``expectedGraph``.
"""

from __future__ import annotations

from decimal import Decimal

from reference_harness.case_runner import _graphs_equal


def test_distinct_high_precision_decimals_are_not_equal_in_graphs() -> None:
    # These two cent amounts collapse to the same binary float. A deep-fetch
    # graph with a decimal projection must still compare them exactly.
    actual = {"Order": [{"id": 1, "total": Decimal("1234567890123456.78")}]}
    expected = {"Order": [{"id": 1, "total": Decimal("1234567890123456.79")}]}
    assert not _graphs_equal(actual, expected)


def test_graph_numeric_spellings_compare_in_decimal_space() -> None:
    actual = {"Order": [{"id": 1, "total": Decimal("10.50")}]}
    expected = {"Order": [{"id": 1, "total": 10.5}]}
    assert _graphs_equal(actual, expected)


def test_graph_comparison_keeps_bool_out_of_numeric_space() -> None:
    actual = {"Order": [{"id": 1, "active": True}]}
    expected = {"Order": [{"id": 1, "active": 1}]}
    assert not _graphs_equal(actual, expected)


def test_graph_comparison_is_order_insensitive_for_nested_to_many_lists() -> None:
    actual = {
        "Order": [
            {
                "id": 1,
                "items": [
                    {"id": 11, "sku": "A-100"},
                    {"id": 12, "sku": "B-200"},
                ],
            },
            {"id": 2, "items": []},
        ]
    }
    expected = {
        "Order": [
            {"id": 2, "items": []},
            {
                "id": 1,
                "items": [
                    {"id": 12, "sku": "B-200"},
                    {"id": 11, "sku": "A-100"},
                ],
            },
        ]
    }
    assert _graphs_equal(actual, expected)
