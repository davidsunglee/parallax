"""Unit tests for deep-fetch object-graph comparison.

Graph comparison must use the same exact numeric semantics as flat row
comparison. The old graph path normalized leaves through ``float``-or-``int``
coercion and then compared serialized strings, which could make distinct
``Decimal`` values compare equal inside ``expectedGraph``.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import load_case, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _assert_child_ordering,
    _assert_deep_fetch,
    _FetchStep,
    _graphs_equal,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


class _RecordingEmptyRootDb:
    dialect = "postgres"

    def __init__(self) -> None:
        self.queries: list[tuple[str, list[Any]]] = []

    def query(self, sql: str, binds: list[Any] | None = None) -> list[dict[str, Any]]:
        self.queries.append((sql, list(binds or [])))
        return []


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


def test_empty_root_deep_fetch_executes_no_child_sql() -> None:
    case = load_case(
        COMPATIBILITY_ROOT,
        COMPATIBILITY_ROOT / "cases" / "0315-deep-fetch-empty-root.yaml",
    )
    db = _RecordingEmptyRootDb()

    _assert_deep_fetch(case, db)

    assert db.queries == [
        ("select t0.id, t0.name from orders t0 where t0.id = ?", [999]),
        ("select id, name from orders where id = 999", []),
    ]


def _orders_model():
    return load_model(COMPATIBILITY_ROOT, "models/orders.yaml")


def _items_step(order_by):
    model = _orders_model()
    return _FetchStep(
        rel_ref="Order.items",
        parent_entity=model.entity("Order"),
        child_entity=model.entity("OrderItem"),
        parent_attr="id",
        child_attr="orderId",
        cardinality="one-to-many",
        order_by=order_by,
    )


def test_child_ordering_accepts_rows_in_declared_desc_order():
    step = _items_step([{"attr": "id", "direction": "desc"}])
    buckets = {"Order.items": {1: [{"id": 12}, {"id": 11}]}}
    _assert_child_ordering("unit", [step], buckets)  # no raise


def test_child_ordering_rejects_rows_out_of_declared_order():
    # Ascending rows are exactly what the DB returns if ORDER BY is dropped.
    step = _items_step([{"attr": "id", "direction": "desc"}])
    buckets = {"Order.items": {1: [{"id": 11}, {"id": 12}]}}
    with pytest.raises(CaseFailure):
        _assert_child_ordering("unit", [step], buckets)


def test_child_ordering_ignores_relationships_without_orderby():
    step = _items_step(None)
    buckets = {"Order.items": {1: [{"id": 11}, {"id": 12}]}}
    _assert_child_ordering("unit", [step], buckets)  # no raise (unordered)


def test_child_ordering_multikey_mixed_direction_with_tiebreak():
    step = _items_step(
        [{"attr": "quantity", "direction": "desc"}, {"attr": "id", "direction": "asc"}]
    )
    # quantity desc, then id asc within the quantity=5 tie.
    buckets = {
        "Order.items": {
            1: [
                {"id": 12, "quantity": 9},
                {"id": 11, "quantity": 5},
                {"id": 13, "quantity": 5},
            ]
        }
    }
    _assert_child_ordering("unit", [step], buckets)  # no raise

    # Swapping the two quantity=5 rows violates the id-asc tie-break.
    bad = {
        "Order.items": {
            1: [
                {"id": 12, "quantity": 9},
                {"id": 13, "quantity": 5},
                {"id": 11, "quantity": 5},
            ]
        }
    }
    with pytest.raises(CaseFailure):
        _assert_child_ordering("unit", [step], bad)


def test_child_ordering_accepts_empty_bucket():
    step = _items_step([{"attr": "id", "direction": "desc"}])
    _assert_child_ordering("unit", [step], {"Order.items": {}})  # no raise


class _OrderedItemsWrongOrderDb:
    """Returns the order-1 root row, then its items in ASCENDING id order — i.e.
    what the DB would return if the declared `id desc` ORDER BY were dropped."""

    dialect = "postgres"

    def query(self, sql, binds=None):
        if "order_item" in sql:
            return [
                {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2},
                {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1},
            ]
        return [{"id": 1, "name": "Ada"}]


def test_deep_fetch_runner_enforces_child_ordering():
    # Guards the WIRING: _assert_deep_fetch must invoke the ordering oracle.
    # 0319 declares Order.items = id desc; the fake DB returns items ascending,
    # so the runner must raise — if the oracle call were removed, this fails.
    case = load_case(
        COMPATIBILITY_ROOT,
        COMPATIBILITY_ROOT / "cases" / "0319-deep-fetch-ordered-items-desc.yaml",
    )
    with pytest.raises(CaseFailure):
        _assert_deep_fetch(case, _OrderedItemsWrongOrderDb())


def test_child_ordering_skips_to_one_relationship():
    # A to-one step carrying orderBy must be skipped (order is a to-MANY concept),
    # even when its rows are out of the declared order.
    model = _orders_model()
    step = _FetchStep(
        rel_ref="OrderItem.order",
        parent_entity=model.entity("OrderItem"),
        child_entity=model.entity("Order"),
        parent_attr="orderId",
        child_attr="id",
        cardinality="many-to-one",
        order_by=[{"attr": "id", "direction": "desc"}],
    )
    _assert_child_ordering("unit", [step], {"OrderItem.order": {1: [{"id": 11}, {"id": 12}]}})
