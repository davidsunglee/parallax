"""Declared-type comparison follows each polymorphic row's concrete participant."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from reference_harness.case import Case
from reference_harness.object_query_oracle import graph, row


def test_rows_compare_reused_sibling_members_by_family_variant(
    corpus_case: Callable[[str], Case],
) -> None:
    case = corpus_case("m-inheritance-124-document-layout-tph-sibling-path-reuse.yaml")
    entity = case.model.entity("Payment")
    actual = [
        {
            "id": 1,
            "detail": "visa-4242",
            "authorization_code": "AUTH-7",
            "familyVariant": "CardPayment",
        },
        {
            "id": 2,
            "detail": Decimal("12.50"),
            "authorization_code": None,
            "familyVariant": "CashPayment",
        },
    ]
    expected = [
        {
            "id": 1,
            "detail": "visa-4242",
            "authorization_code": "AUTH-7",
            "familyVariant": "CardPayment",
        },
        {
            "id": 2,
            "detail": "12.50",
            "authorization_code": None,
            "familyVariant": "CashPayment",
        },
    ]

    assert row.rows_equal(actual, expected, case.model, entity)


def test_graphs_compare_reused_sibling_members_by_family_variant(
    corpus_case: Callable[[str], Case],
) -> None:
    case = corpus_case("m-inheritance-123-document-layout-tph-broad-read.yaml")
    actual = {
        "Payment": [
            {
                "id": 1,
                "detail": "visa-4242",
                "authorizationCode": "AUTH-7",
                "familyVariant": "CardPayment",
            },
            {
                "id": 2,
                "detail": Decimal("12.50"),
                "familyVariant": "CashPayment",
            },
        ]
    }
    expected = {
        "Payment": [
            {
                "id": 1,
                "detail": "visa-4242",
                "authorizationCode": "AUTH-7",
                "familyVariant": "CardPayment",
            },
            {
                "id": 2,
                "detail": "12.50",
                "familyVariant": "CashPayment",
            },
        ]
    }

    assert graph.graphs_equal(actual, expected, case.model)
