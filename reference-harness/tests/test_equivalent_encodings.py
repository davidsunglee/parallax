"""Unit tests for the dialect-agnostic ``equivalentEncodings`` case check.

A case MAY carry ``equivalentEncodings`` — a list of alternate surface encodings
that an implementation's serde might emit (e.g. a prefix vs a fluent spelling of
the same grouped predicate). Each one MUST canonicalize to the case's canonical
``operation``; the runner proves it without a database (pure serde). This
generalizes the former bespoke group-precedence test into the fixture model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import Case, Model
from reference_harness.case_runner import CaseFailure, _assert_equivalent_encodings


def _case(operation: dict, equivalent_encodings: list[dict] | None = None) -> Case:
    raw: dict = {"operation": operation, "goldenSql": {}}
    if equivalent_encodings is not None:
        raw["equivalentEncodings"] = equivalent_encodings
    model = Model(path=Path("models/none.yaml"), descriptor={}, fixtures={})
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
