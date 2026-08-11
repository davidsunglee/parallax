"""Unit tests for the dialect-agnostic ``equivalentEncodings`` case check.

A read or scenario read step MAY carry ``equivalentEncodings`` — alternate
authoring-surface encodings that normalize to its canonical operation. The runner
proves the equivalence without a database, including the model-aware
Transaction-Time omission default.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import Case, Model
from reference_harness.case_runner import CaseFailure, _assert_equivalent_encodings
from reference_harness.serde import canonical


def _case(operation: dict, equivalent_encodings: list[dict] | None = None) -> Case:
    when: dict = {"operation": operation, "targetEntity": "Order"}
    if equivalent_encodings is not None:
        when["equivalentEncodings"] = equivalent_encodings
    raw: dict = {"shape": "read", "when": when}
    model = Model(
        path=Path("models/none.yaml"),
        descriptor={"entity": {"name": "Order", "attributes": []}},
        fixtures={},
    )
    return Case(path=Path("cases/none.yaml"), raw=raw, model=model)


# The canonical grouped intent `(a OR b) AND c`, authored keys-first.
_OPERATION = {
    "and": {
        "operands": [
            {"group": {"operand": {"or": {"operands": [{"x": 1}, {"y": 2}]}}}},
            {"eq": {"attr": "Order.active", "value": True}},
        ]
    }
}


def test_matching_encoding_passes() -> None:
    # Same tree, object keys authored in a different order — canonicalization
    # sorts keys, so it MUST collapse to the same node.
    reordered = {
        "and": {
            "operands": [
                {"group": {"operand": {"or": {"operands": [{"x": 1}, {"y": 2}]}}}},
                {"eq": {"value": True, "attr": "Order.active"}},
            ]
        }
    }
    _assert_equivalent_encodings(_case(_OPERATION, [reordered]))  # no raise


def test_mismatched_encoding_raises() -> None:
    # A genuinely different tree (the `group` node dropped) must NOT be accepted
    # as an equivalent encoding — precedence is carried, not erased.
    ungrouped = {
        "and": {
            "operands": [
                {"or": {"operands": [{"x": 1}, {"y": 2}]}},
                {"eq": {"attr": "Order.active", "value": True}},
            ]
        }
    }
    with pytest.raises(CaseFailure):
        _assert_equivalent_encodings(_case(_OPERATION, [ungrouped]))


def test_absent_field_is_a_noop() -> None:
    _assert_equivalent_encodings(_case(_OPERATION))  # no raise


def test_omitted_transaction_time_normalizes_to_explicit_latest() -> None:
    operation = {
        "asOf": {
            "operand": {"all": {}},
            "dimension": "transaction-time",
            "coordinate": "latest",
        }
    }
    raw = {
        "shape": "read",
        "when": {
            "targetEntity": "Balance",
            "operation": operation,
            "equivalentEncodings": [{"all": {}}],
        },
    }
    model = Model(
        path=Path("models/balance.yaml"),
        descriptor={
            "entity": {"name": "Balance", "temporality": "transaction-time", "attributes": []}
        },
        fixtures={},
    )
    _assert_equivalent_encodings(Case(path=Path("cases/balance.yaml"), raw=raw, model=model))


def test_scenario_step_normalizes_its_own_equivalent_encoding() -> None:
    operation = {
        "asOf": {
            "operand": {"all": {}},
            "dimension": "transaction-time",
            "coordinate": "latest",
        }
    }
    raw = {
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "targetEntity": "Balance",
                    "find": operation,
                    "equivalentEncodings": [{"all": {}}],
                    "roundTrips": 1,
                }
            ]
        },
    }
    model = Model(
        path=Path("models/balance.yaml"),
        descriptor={
            "entity": {"name": "Balance", "temporality": "transaction-time", "attributes": []}
        },
        fixtures={},
    )
    _assert_equivalent_encodings(Case(path=Path("cases/balance.yaml"), raw=raw, model=model))


def test_include_paths_are_an_order_insensitive_canonicalized_set() -> None:
    maximal = {
        "segments": [
            {"rel": "Order.items"},
            {"rel": "OrderItem.statuses"},
        ]
    }
    canonical_operation = {
        "deepFetch": {
            "operand": {"all": {}},
            "paths": [maximal, {"segments": [{"rel": "Order.statuses"}]}],
        }
    }
    alternate = {
        "deepFetch": {
            "operand": {"all": {}},
            "paths": [
                {"segments": [{"rel": "Order.statuses"}]},
                {"segments": [{"rel": "Order.items"}]},
                maximal,
                maximal,
            ],
        }
    }
    assert canonical(alternate) == canonical(canonical_operation)


def test_include_canonicalization_keeps_broad_and_narrowed_paths_distinct() -> None:
    broad = {"segments": [{"rel": "Person.pets"}]}
    narrowed = {"segments": [{"rel": "Person.pets", "narrow": {"to": ["Dog"]}}]}
    operation = {"deepFetch": {"operand": {"all": {}}, "paths": [narrowed, broad, narrowed]}}
    assert canonical(operation)["deepFetch"]["paths"] == [broad, narrowed]


def test_canonicalization_keeps_other_list_order_significant() -> None:
    and_left = {"and": {"operands": [{"x": 1}, {"y": 2}]}}
    and_right = {"and": {"operands": [{"y": 2}, {"x": 1}]}}
    or_left = {"or": {"operands": [{"x": 1}, {"y": 2}]}}
    or_right = {"or": {"operands": [{"y": 2}, {"x": 1}]}}
    narrow_left = {"narrow": {"to": ["Cat", "Dog"], "operand": {"all": {}}}}
    narrow_right = {"narrow": {"to": ["Dog", "Cat"], "operand": {"all": {}}}}
    assert canonical(and_left) != canonical(and_right)
    assert canonical(or_left) != canonical(or_right)
    assert canonical(narrow_left) != canonical(narrow_right)
