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
    _expected_asof_suffix,
    _FetchStep,
    _graphs_equal,
    _root_asof_pins,
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


def test_child_ordering_places_nulls_last_ascending():
    step = _items_step([{"attr": "id", "direction": "asc"}])
    buckets = {"Order.items": {1: [{"id": 10}, {"id": 20}, {"id": None}]}}
    _assert_child_ordering("unit", [step], buckets)  # no raise


def test_child_ordering_places_nulls_last_descending():
    step = _items_step([{"attr": "id", "direction": "desc"}])
    # NULLs sort last even for desc: non-null descending, then NULL.
    buckets = {"Order.items": {1: [{"id": 20}, {"id": 10}, {"id": None}]}}
    _assert_child_ordering("unit", [step], buckets)  # no raise


def test_child_ordering_rejects_nulls_first():
    step = _items_step([{"attr": "id", "direction": "asc"}])
    buckets = {"Order.items": {1: [{"id": None}, {"id": 10}, {"id": 20}]}}
    with pytest.raises(CaseFailure):
        _assert_child_ordering("unit", [step], buckets)


def test_child_ordering_null_vs_null_tiebreak_by_next_key():
    step = _items_step(
        [{"attr": "quantity", "direction": "asc"}, {"attr": "id", "direction": "asc"}]
    )
    # Both NULL on key 1 → equal there → tiebroken by id asc.
    ok = {"Order.items": {1: [{"id": 11, "quantity": None}, {"id": 13, "quantity": None}]}}
    _assert_child_ordering("unit", [step], ok)  # no raise
    bad = {"Order.items": {1: [{"id": 13, "quantity": None}, {"id": 11, "quantity": None}]}}
    with pytest.raises(CaseFailure):
        _assert_child_ordering("unit", [step], bad)


def test_child_ordering_rejects_unprojected_orderby_key():
    # orderBy key 'sku' is not present in the returned rows → cannot verify.
    step = _items_step([{"attr": "sku", "direction": "asc"}])
    buckets = {"Order.items": {1: [{"id": 11}, {"id": 12}]}}
    with pytest.raises(CaseFailure):
        _assert_child_ordering("unit", [step], buckets)


def test_policy_model_is_temporal_and_relational():
    model = load_model(COMPATIBILITY_ROOT, "models/policy.yaml")
    coverage = model.entity("Coverage")
    assert coverage.is_temporal
    assert {a["axis"] for a in coverage.as_of_attributes} == {"business", "processing"}
    assert coverage.relationship_by_name("policy")["cardinality"] == "many-to-one"
    assert model.entity("Policy").relationship_by_name("coverages")["relatedEntity"] == "Coverage"
    assert coverage.relationship_by_name("claims")["cardinality"] == "one-to-many"


def _policy_model():
    return load_model(COMPATIBILITY_ROOT, "models/policy.yaml")


def test_expected_suffix_both_latest():
    coverage = _policy_model().entity("Coverage")
    # No pins -> both axes default to latest -> equality on each axis.
    assert _expected_asof_suffix(coverage, {}) == ["infinity", "infinity"]


def test_expected_suffix_business_past_processing_latest():
    coverage = _policy_model().entity("Coverage")
    pins = {"business": "2024-03-01T00:00:00+00:00"}  # processing defaults to latest
    assert _expected_asof_suffix(coverage, pins) == [
        "2024-03-01T00:00:00+00:00", "2024-03-01T00:00:00+00:00", "infinity",
    ]


def test_expected_suffix_business_latest_processing_past():
    coverage = _policy_model().entity("Coverage")
    pins = {"processing": "2024-02-01T00:00:00+00:00"}  # business defaults to latest
    assert _expected_asof_suffix(coverage, pins) == [
        "infinity", "2024-02-01T00:00:00+00:00", "2024-02-01T00:00:00+00:00",
    ]


def test_expected_suffix_both_past_is_business_first():
    coverage = _policy_model().entity("Coverage")
    pins = {"business": "2024-03-01T00:00:00+00:00", "processing": "2024-02-01T00:00:00+00:00"}
    assert _expected_asof_suffix(coverage, pins) == [
        "2024-03-01T00:00:00+00:00", "2024-03-01T00:00:00+00:00",
        "2024-02-01T00:00:00+00:00", "2024-02-01T00:00:00+00:00",
    ]


def test_expected_suffix_processing_only_latest():
    line = load_model(COMPATIBILITY_ROOT, "models/invoice.yaml").entity("InvoiceLine")
    assert _expected_asof_suffix(line, {}) == ["infinity"]


def test_expected_suffix_non_temporal_child_is_empty():
    note = load_model(COMPATIBILITY_ROOT, "models/lease.yaml").entity("LeaseNote")
    assert _expected_asof_suffix(note, {"processing": "2024-02-01T00:00:00+00:00"}) == []


def test_root_pins_reads_nested_asof_by_axis():
    case = load_case(
        COMPATIBILITY_ROOT, COMPATIBILITY_ROOT / "cases" / "0327-deepfetch-temporal-both-past.yaml"
    )
    assert _root_asof_pins(case) == {
        "business": "2024-03-01T00:00:00+00:00",
        "processing": "2024-02-01T00:00:00+00:00",
    }


def test_root_pins_peels_result_directives_before_asof():
    # 0336 wraps the temporal root in `limit(orderBy(asOf(asOf(all))))`. The pin
    # collector MUST descend past the result directives first (exactly as the root
    # compile peels distinct/orderBy/limit before the temporal wrappers); otherwise a
    # directive-wrapped root seeds NO pins and the child wrongly defaults to now.
    case = load_case(
        COMPATIBILITY_ROOT,
        COMPATIBILITY_ROOT / "cases" / "0336-deepfetch-temporal-ordered-root.yaml",
    )
    assert _root_asof_pins(case) == {
        "business": "2024-03-01T00:00:00+00:00",
        "processing": "now",
    }


class _WrongAsofChildDb:
    """Returns both fully-current Policies and both fully-current Coverages,
    matching 0324's expectedGraph exactly. The ONLY thing that can fail is the
    corrupted as-of suffix in the authored binds. Used to prove the suffix
    enforcement block is load-bearing: without it, the graph matches and no
    CaseFailure is raised."""
    dialect = "postgres"

    def query(self, sql, binds=None):
        if "coverage" in sql:
            return [
                {"id": 10, "policy_id": 1, "amount": Decimal("700.00")},
                {"id": 20, "policy_id": 2, "amount": Decimal("300.00")},
            ]
        return [{"id": 1, "name": "Auto"}, {"id": 2, "name": "Home"}]


def test_deep_fetch_enforces_propagated_asof_suffix(tmp_path):
    # An otherwise-valid case whose child as-of suffix is WRONG must raise.
    # Build it from 0324 with a corrupted level-1 suffix bind.
    import yaml
    src = yaml.safe_load(
        (COMPATIBILITY_ROOT / "cases" / "0324-deepfetch-temporal-both-latest.yaml").read_text()
    )
    src["binds"][1][-1] = "2099-01-01T00:00:00+00:00"  # not the propagated `infinity`
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(src))
    case = load_case(COMPATIBILITY_ROOT, bad)
    with pytest.raises(CaseFailure):
        _assert_deep_fetch(case, _WrongAsofChildDb())


def test_existing_non_temporal_deep_fetch_still_passes():
    # Backward-compat guard: 0311 (non-temporal Order.items) has no as-of suffix.
    case = load_case(
        COMPATIBILITY_ROOT,
        COMPATIBILITY_ROOT / "cases" / "0311-deep-fetch-to-many.yaml",
    )

    class _OrdersDb:
        dialect = "postgres"
        def query(self, sql, binds=None):
            if "order_item" in sql:
                return [
                    {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1},
                    {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2},
                    {"id": 21, "order_id": 2, "sku": "A-300", "quantity": 4},
                    {"id": 422, "order_id": 42, "sku": "B-200", "quantity": 5},
                    {"id": 421, "order_id": 42, "sku": "A-999", "quantity": 3},
                ]
            return [
                {"id": 1, "name": "Ada", "price": Decimal("10.50")},
                {"id": 2, "name": "Linus", "price": Decimal("20.00")},
                {"id": 3, "name": "ada", "price": Decimal("30.25")},
                {"id": 4, "name": "Margaret", "price": Decimal("40.00")},
                {"id": 5, "name": "Alan", "price": Decimal("50.75")},
                {"id": 42, "name": "Grace", "price": Decimal("99.99")},
            ]

    _assert_deep_fetch(case, _OrdersDb())  # no raise
