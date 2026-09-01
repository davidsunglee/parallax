"""Typed literals are refused before a compatibility case reaches provisioning."""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import Case, Model
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_preflight import preflight_case_literals


def _case(*, predicate_value: object = "2026-01-15", fixture_value: object = "10.50") -> Case:
    descriptor = {
        "entity": {
            "name": "Reading",
            "namespace": "example",
            "table": "reading",
            "attributes": [
                {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                {"name": "amount", "type": "decimal(12,2)", "column": "amount"},
                {"name": "day", "type": "date", "column": "day"},
            ],
        }
    }
    model = Model(
        Path("reading.yaml"),
        descriptor,
        {"example.Reading": [{"id": 1, "amount": fixture_value, "day": "2026-01-15"}]},
    )
    document = {
        "shape": "read",
        "when": {
            "objectQuery": {
                "target": "example.Reading",
                "predicate": {"eq": {"attr": "example.Reading.day", "value": predicate_value}},
            }
        },
        "then": {"rows": [{"id": 1, "amount": "10.50", "day": "2026-01-15"}]},
    }
    return Case(Path("synthetic.yaml"), document, model)


def test_preflight_accepts_canonical_fixture_predicate_and_expected_literals() -> None:
    preflight_case_literals(_case())


def test_preflight_refuses_a_predicate_literal_at_its_authored_coordinate() -> None:
    with pytest.raises(CaseFailure, match=r"when\.objectQuery\.predicate.*names no date"):
        preflight_case_literals(_case(predicate_value="15 January 2026"))


def test_preflight_refuses_a_fixture_before_any_lane_can_provision_it() -> None:
    with pytest.raises(CaseFailure, match=r"fixtures\.example\.Reading\[0\]\.amount"):
        preflight_case_literals(_case(fixture_value=10.555))
