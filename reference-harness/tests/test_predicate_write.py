"""Predicate-selected write contract tests (COR-35, no database)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from reference_harness.case import load_model
from reference_harness.predicate_write_validate import (
    PredicateWriteValidationError,
    validate_predicate_write,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_CASE_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"


def _schema() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_CASE_SCHEMA_PATH.read_text(encoding="utf-8")))


def _update_instruction() -> dict[str, object]:
    return {
        "mutation": "update",
        "target": {
            "entity": "Account",
            "predicate": {"lessThan": {"attr": "Account.balance", "value": 200.00}},
        },
        "assignments": [{"attr": "Account.balance", "value": 0.00}],
    }


def _scenario_case(instruction: dict[str, object]) -> dict[str, object]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-opt-lock"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "write": instruction,
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {"postgres": "update account set balance = ? where id = ?"},
                            "binds": [0.00, 1],
                        }
                    ],
                }
            ]
        },
        "then": {"roundTrips": 1},
    }


def _account_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/account.yaml").root_entity


def test_schema_accepts_structured_predicate_update() -> None:
    assert next(_schema().iter_errors(_scenario_case(_update_instruction())), None) is None


@pytest.mark.parametrize(
    ("mutation", "edits"),
    [
        ("update", {"assignments": []}),
        ("delete", {"assignments": [{"attr": "Account.balance", "value": 0.00}]}),
        ("terminate", {"assignments": [{"attr": "Account.balance", "value": 0.00}]}),
        ("terminateUntil", {"until": None}),
    ],
)
def test_schema_enforces_predicate_write_verb_shape(
    mutation: str, edits: dict[str, object]
) -> None:
    instruction = _update_instruction()
    instruction["mutation"] = mutation
    if mutation in {"delete", "terminate", "terminateUntil"}:
        instruction.pop("assignments")
    instruction.update({key: value for key, value in edits.items() if value is not None})
    assert next(_schema().iter_errors(_scenario_case(instruction)), None) is not None


def test_model_validator_accepts_a_scoped_assignable_predicate_write() -> None:
    entity = _account_entity()
    validate_predicate_write(entity, [entity.definition], _update_instruction())


@pytest.mark.parametrize(
    ("instruction", "message"),
    [
        (
            {
                "mutation": "update",
                "target": {
                    "entity": "Account",
                    "predicate": {"lessThan": {"attr": "Wallet.balance", "value": 200.00}},
                },
                "assignments": [{"attr": "Account.balance", "value": 0.00}],
            },
            "inconsistent",
        ),
        (
            {
                "mutation": "update",
                "target": {
                    "entity": "Account",
                    "predicate": {
                        "orderBy": {
                            "operand": {"all": {}},
                            "keys": [{"attr": "Account.balance"}],
                        }
                    },
                },
                "assignments": [{"attr": "Account.balance", "value": 0.00}],
            },
            "read modifier",
        ),
        (
            {
                "mutation": "update",
                "target": {
                    "entity": "Account",
                    "predicate": {"all": {}},
                },
                "assignments": [
                    {"attr": "Account.balance", "value": 0.00},
                    {"attr": "Account.balance", "value": 1.00},
                ],
            },
            "duplicate",
        ),
        (
            {
                "mutation": "update",
                "target": {"entity": "Account", "predicate": {"all": {}}},
                "assignments": [{"attr": "Account.version", "value": 2}],
            },
            "framework-owned",
        ),
    ],
)
def test_model_validator_rejects_invalid_predicate_write(
    instruction: dict[str, object], message: str
) -> None:
    entity = _account_entity()
    with pytest.raises(PredicateWriteValidationError, match=message):
        validate_predicate_write(entity, [entity.definition], instruction)
