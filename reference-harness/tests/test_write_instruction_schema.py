"""DB-free tests for the canonical write-instruction schema (m-unit-work).

`write-instruction.schema.json` is the write-side analogue of
`operation.schema.json`: the canonical, axis-explicit vocabulary a unit of work
buffers. These tests pin the two instruction shapes (keyed + predicate), the
axis-explicit business bounds, the absence of a processing-instant field, and the
verb / bound conditionals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "core" / "schemas" / "write-instruction.schema.json"
)


def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


def _valid(doc: dict[str, Any]) -> bool:
    return next(_validator().iter_errors(doc), None) is None


def test_schema_is_meta_valid() -> None:
    Draft202012Validator.check_schema(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


# --- keyed instructions -------------------------------------------------------


def test_keyed_plain_insert_is_valid() -> None:
    assert _valid({"mutation": "insert", "entity": "Balance", "rows": [{"id": 1, "value": 100.0}]})


def test_keyed_plain_temporal_carries_business_from_only() -> None:
    assert _valid(
        {
            "mutation": "update",
            "entity": "Balance",
            "rows": [{"id": 1, "value": 150.0}],
            "businessFrom": "2024-06-01T00:00:00+00:00",
        }
    )


def test_keyed_until_requires_business_to() -> None:
    doc = {
        "mutation": "updateUntil",
        "entity": "Position",
        "rows": [{"id": 1, "value": 9}],
        "businessFrom": "2024-01-01T00:00:00+00:00",
        "businessTo": "2024-06-01T00:00:00+00:00",
    }
    assert _valid(doc)
    del doc["businessTo"]
    assert not _valid(doc)


def test_keyed_plain_mutation_rejects_business_to() -> None:
    assert not _valid(
        {"mutation": "insert", "entity": "Balance", "rows": [{"id": 1}], "businessTo": "x"}
    )


def test_keyed_rejects_a_processing_instant_field() -> None:
    # The processing instant is Clock-supplied context, never an instruction field.
    assert not _valid(
        {"mutation": "insert", "entity": "Balance", "rows": [{"id": 1}], "at": "2024-01-01"}
    )


def test_keyed_value_object_document_and_pk_marker_rows() -> None:
    assert _valid(
        {
            "mutation": "insert",
            "entity": "Customer",
            "rows": [{"id": {"computed": "maxPlusOne"}, "address": {"city": "Oslo"}}],
        }
    )


# --- predicate instructions ---------------------------------------------------


def test_predicate_update_requires_assignments() -> None:
    doc = {
        "mutation": "update",
        "target": {
            "entity": "Account",
            "predicate": {"lessThan": {"attr": "Account.balance", "value": 200}},
        },
        "assignments": [{"attr": "Account.balance", "value": 0}],
    }
    assert _valid(doc)
    del doc["assignments"]
    assert not _valid(doc)


def test_predicate_delete_rejects_assignments() -> None:
    assert not _valid(
        {
            "mutation": "delete",
            "target": {
                "entity": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 1}},
            },
            "assignments": [{"attr": "Account.balance", "value": 0}],
        }
    )


def test_predicate_until_requires_business_to() -> None:
    doc = {
        "mutation": "terminateUntil",
        "target": {"entity": "Position", "predicate": {"eq": {"attr": "Position.id", "value": 1}}},
        "businessTo": "2024-06-01T00:00:00+00:00",
    }
    assert _valid(doc)
    del doc["businessTo"]
    assert not _valid(doc)


def test_instruction_rejects_unknown_top_level_key() -> None:
    assert not _valid(
        {"mutation": "insert", "entity": "Balance", "rows": [{"id": 1}], "bogus": True}
    )
