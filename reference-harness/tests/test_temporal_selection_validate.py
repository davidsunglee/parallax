"""Canonical temporal-selection completeness checks."""

from reference_harness.inheritance import Family
from reference_harness.temporal_selection_validate import (
    normalize_authored_temporal_selections,
    validate_temporal_selections,
)

_FAMILY = Family(
    [
        {"name": "Order", "attributes": []},
        {"name": "Balance", "temporality": "transaction-time", "attributes": []},
        {"name": "Position", "temporality": "bitemporal", "attributes": []},
    ]
)


def test_non_temporal_read_needs_no_selection() -> None:
    assert validate_temporal_selections({"all": {}}, "Order", _FAMILY) == []


def test_temporal_read_reports_each_missing_declared_dimension() -> None:
    assert validate_temporal_selections({"all": {}}, "Balance", _FAMILY) == [
        "temporal read of Balance is missing selections for ['transaction-time']; "
        "canonical operations name exactly one selection per declared dimension"
    ]
    assert validate_temporal_selections(
        {
            "asOf": {
                "operand": {"all": {}},
                "dimension": "valid-time",
                "coordinate": "latest",
            }
        },
        "Position",
        _FAMILY,
    ) == [
        "temporal read of Position is missing selections for ['transaction-time']; "
        "canonical operations name exactly one selection per declared dimension"
    ]


def test_complete_mixed_selections_under_a_result_wrapper_accept() -> None:
    operation = {
        "limit": {
            "count": 1,
            "operand": {
                "history": {
                    "operand": {
                        "asOf": {
                            "operand": {"all": {}},
                            "dimension": "transaction-time",
                            "coordinate": "latest",
                        }
                    },
                    "dimension": "valid-time",
                }
            },
        }
    }
    assert validate_temporal_selections(operation, "Position", _FAMILY) == []


def test_duplicate_and_undeclared_selections_are_reported() -> None:
    duplicate = {
        "asOf": {
            "operand": {"history": {"operand": {"all": {}}, "dimension": "transaction-time"}},
            "dimension": "transaction-time",
            "coordinate": "latest",
        }
    }
    assert validate_temporal_selections(duplicate, "Balance", _FAMILY) == [
        "temporal read of Balance repeats selections for ['transaction-time']; "
        "canonical operations name exactly one selection per declared dimension"
    ]
    undeclared = {"history": {"operand": {"all": {}}, "dimension": "valid-time"}}
    assert validate_temporal_selections(undeclared, "Balance", _FAMILY) == [
        "temporal read of Balance is missing selections for ['transaction-time']; "
        "canonical operations name exactly one selection per declared dimension",
        "temporal read of Balance selects undeclared dimensions ['valid-time']; "
        "canonical operations name exactly one selection per declared dimension",
    ]


def test_authored_transaction_time_omission_normalizes_inside_valid_time() -> None:
    authored = {"history": {"operand": {"all": {}}, "dimension": "valid-time"}}
    assert normalize_authored_temporal_selections(authored, "Position", _FAMILY) == {
        "history": {
            "operand": {
                "asOf": {
                    "operand": {"all": {}},
                    "dimension": "transaction-time",
                    "coordinate": "latest",
                }
            },
            "dimension": "valid-time",
        }
    }
