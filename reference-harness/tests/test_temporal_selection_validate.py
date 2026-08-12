"""Canonical temporal-selection completeness checks."""

from typing import Any

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

_LATEST_TX: dict[str, Any] = {"asOf": "latest"}


def _query(target: str, **clauses: Any) -> dict[str, Any]:
    return {"target": target, "predicate": {"all": {}}, **clauses}


def test_non_temporal_read_needs_no_selection() -> None:
    assert validate_temporal_selections(_query("Order"), _FAMILY) == []


def test_temporal_read_reports_each_missing_declared_dimension() -> None:
    assert validate_temporal_selections(_query("Balance"), _FAMILY) == [
        "temporal read of Balance is missing selections for ['transaction-time']; "
        "a canonical Object Query names exactly one selection per declared dimension"
    ]
    assert validate_temporal_selections(
        _query("Position", temporal={"valid-time": {"asOf": "latest"}}), _FAMILY
    ) == [
        "temporal read of Position is missing selections for ['transaction-time']; "
        "a canonical Object Query names exactly one selection per declared dimension"
    ]


def test_complete_mixed_selections_accept_beside_any_other_clause() -> None:
    # Every clause is a sibling, so a query carrying a cap and Includes states its
    # temporal selections in exactly the same one place a bare query does.
    query = _query(
        "Position",
        temporal={"transaction-time": _LATEST_TX, "valid-time": {"history": {}}},
        limit=1,
        includes=[{"segments": [{"rel": "Position.trades"}]}],
    )
    assert validate_temporal_selections(query, _FAMILY) == []


def test_undeclared_selections_are_reported() -> None:
    # A dimension keys the map, so a REPEATED selection has no spelling at all;
    # what remains is naming a dimension the target does not declare, reported
    # beside the declared one it left unselected.
    undeclared = _query("Balance", temporal={"valid-time": {"history": {}}})
    assert validate_temporal_selections(undeclared, _FAMILY) == [
        "temporal read of Balance is missing selections for ['transaction-time']; "
        "a canonical Object Query names exactly one selection per declared dimension",
        "temporal read of Balance selects undeclared dimensions ['valid-time']; "
        "a canonical Object Query names exactly one selection per declared dimension",
    ]


def test_authored_transaction_time_omission_normalizes_beside_valid_time() -> None:
    authored = _query("Position", temporal={"valid-time": {"history": {}}})
    assert normalize_authored_temporal_selections(authored, _FAMILY) == _query(
        "Position",
        temporal={"valid-time": {"history": {}}, "transaction-time": _LATEST_TX},
    )


def test_authored_transaction_time_omission_normalizes_beside_every_other_clause() -> None:
    # Normalization fills one clause and touches no other, so it is independent of
    # what else the query carries — which is what the flat query makes structural
    # rather than a rule about wrapper order.
    authored = _query("Position", narrowTo=["Position"], temporal={"valid-time": {"history": {}}})
    assert normalize_authored_temporal_selections(authored, _FAMILY) == _query(
        "Position",
        narrowTo=["Position"],
        temporal={"valid-time": {"history": {}}, "transaction-time": _LATEST_TX},
    )


def test_a_selected_transaction_time_is_left_exactly_as_authored() -> None:
    authored = _query(
        "Position",
        temporal={
            "transaction-time": {"asOf": "2024-01-01T00:00:00Z"},
            "valid-time": {"history": {}},
        },
    )
    assert normalize_authored_temporal_selections(authored, _FAMILY) == authored


def test_a_non_temporal_target_normalizes_to_itself() -> None:
    authored = _query("Order")
    assert normalize_authored_temporal_selections(authored, _FAMILY) is authored
