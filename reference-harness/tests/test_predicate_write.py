"""Predicate-selected write contract tests (COR-35, no database)."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from reference_harness.case import Entity, load_model
from reference_harness.predicate_write_validate import (
    PredicateWriteValidationError,
    validate_predicate_write,
    validate_predicate_write_materialization,
)
from reference_harness.schema_validate import validate_tree
from reference_harness.schemas import build_registry, load_schemas

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_CASE_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"
_REGISTRY = build_registry(load_schemas(_REPO_ROOT / "core"))


def _schema() -> Draft202012Validator:
    return Draft202012Validator(
        json.loads(_CASE_SCHEMA_PATH.read_text(encoding="utf-8")), registry=_REGISTRY
    )


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


def _orders_model():
    return load_model(_COMPATIBILITY_ROOT, "models/orders.yaml")


def _customer_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/customer.yaml").root_entity


def _position_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/position.yaml").root_entity


def _balance_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/balance.yaml").root_entity


def _materializing_find(
    entity: Entity, predicate: dict[str, object], rows: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "targetEntity": entity.name,
        "find": predicate,
        "roundTrips": 1,
        "statements": [
            {
                "sql": {"postgres": "select t0.id from account t0"},
                "binds": [],
            }
        ],
        "expectRows": rows,
    }


def test_schema_accepts_structured_predicate_update() -> None:
    assert next(_schema().iter_errors(_scenario_case(_update_instruction())), None) is None


@pytest.mark.parametrize(
    "literal",
    [
        {"street": "Main", "city": "Oslo"},
        [{"street": "Main", "city": "Oslo"}],
    ],
)
def test_schema_accepts_object_and_array_predicate_write_literals(literal: object) -> None:
    instruction = _update_instruction()
    instruction["assignments"] = [{"attr": "Customer.address", "value": literal}]

    assert next(_schema().iter_errors(_scenario_case(instruction)), None) is None


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
    validate_predicate_write(entity, _update_instruction())


def test_materialization_validator_accepts_a_matching_versioned_find() -> None:
    entity = _account_entity()
    instruction = _update_instruction()
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)

    validate_predicate_write_materialization(
        entity,
        [
            _materializing_find(
                entity,
                {"lessThan": {"value": 200.00, "attr": "Account.balance"}},
                [{"id": 1, "balance": 100.00, "version": 1}],
            )
        ],
        instruction,
    )


def test_materialization_validator_rejects_readless_versioned_write() -> None:
    with pytest.raises(PredicateWriteValidationError, match="preceding materializing find"):
        validate_predicate_write_materialization(_account_entity(), [], _update_instruction())


def test_materialization_validator_rejects_differently_predicated_find() -> None:
    entity = _account_entity()
    with pytest.raises(PredicateWriteValidationError, match="matching canonical predicate"):
        validate_predicate_write_materialization(
            entity,
            [_materializing_find(entity, {"all": {}}, [{"id": 1, "version": 1}])],
            _update_instruction(),
        )


def test_materialization_validator_rejects_unobservable_matching_find() -> None:
    entity = _account_entity()
    instruction = _update_instruction()
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)

    with pytest.raises(PredicateWriteValidationError, match="real resolving read"):
        validate_predicate_write_materialization(
            entity,
            [{"targetEntity": "Account", "find": predicate}],
            instruction,
        )


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        ({"roundTrips": 0}, "roundTrips: 1"),
        ({"roundTrips": 2}, "roundTrips: 1"),
        ({"statements": []}, "authored golden read statement"),
    ],
)
def test_materialization_validator_rejects_a_cache_hit_or_non_resolving_find(
    edit: dict[str, object], message: str
) -> None:
    entity = _account_entity()
    instruction = _update_instruction()
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)
    find = _materializing_find(entity, predicate, [{"id": 1, "balance": 100.00, "version": 1}])
    find.update(edit)

    with pytest.raises(PredicateWriteValidationError, match=message):
        validate_predicate_write_materialization(entity, [find], instruction)


def test_materialization_validator_accepts_a_real_zero_match_resolution() -> None:
    entity = _account_entity()
    instruction = _update_instruction()
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)

    validate_predicate_write_materialization(
        entity, [_materializing_find(entity, predicate, [])], instruction
    )


def test_materialization_validator_rejects_missing_current_scalar_assignment_value() -> None:
    entity = _account_entity()
    instruction = _update_instruction()
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)

    with pytest.raises(PredicateWriteValidationError, match="balance"):
        validate_predicate_write_materialization(
            entity,
            [_materializing_find(entity, predicate, [{"id": 1, "version": 1}])],
            instruction,
        )


def test_materialization_validator_accepts_temporal_milestone_observations() -> None:
    entity = _position_entity()
    instruction = {
        "mutation": "terminate",
        "target": {
            "entity": "Position",
            "predicate": {"eq": {"attr": "Position.id", "value": 1}},
        },
        "at": "2024-10-01T00:00:00+00:00",
        "validFrom": "2024-07-01T00:00:00+00:00",
    }
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)

    validate_predicate_write_materialization(
        entity,
        [
            _materializing_find(
                entity,
                predicate,
                [
                    {
                        "pos_id": 1,
                        "acct_num": "A",
                        "val": 200.00,
                        "from_z": "2024-06-01T00:00:00+00:00",
                        "thru_z": "infinity",
                        "in_z": "2024-04-01T00:00:00+00:00",
                        "out_z": "infinity",
                    }
                ],
            )
        ],
        instruction,
    )


def test_materialization_validator_rejects_missing_temporal_carried_payload() -> None:
    entity = _position_entity()
    instruction = {
        "mutation": "terminate",
        "target": {
            "entity": "Position",
            "predicate": {"eq": {"attr": "Position.id", "value": 1}},
        },
        "at": "2024-10-01T00:00:00+00:00",
        "validFrom": "2024-07-01T00:00:00+00:00",
    }
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)
    row = {
        "pos_id": 1,
        "val": 200.00,
        "from_z": "2024-06-01T00:00:00+00:00",
        "thru_z": "infinity",
        "in_z": "2024-04-01T00:00:00+00:00",
        "out_z": "infinity",
    }

    with pytest.raises(PredicateWriteValidationError, match="acct_num"):
        validate_predicate_write_materialization(
            entity, [_materializing_find(entity, predicate, [row])], instruction
        )


def test_materialization_validator_requires_transaction_temporal_update_payload() -> None:
    entity = _balance_entity()
    instruction = {
        "mutation": "update",
        "target": {
            "entity": "Balance",
            "predicate": {"eq": {"attr": "Balance.id", "value": 1}},
        },
        "assignments": [{"attr": "Balance.value", "value": 300.00}],
        "at": "2024-10-01T00:00:00+00:00",
    }
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)
    row = {
        "bal_id": 1,
        "val": 200.00,
        "in_z": "2024-04-01T00:00:00+00:00",
        "out_z": "infinity",
    }

    with pytest.raises(PredicateWriteValidationError, match="acct_num"):
        validate_predicate_write_materialization(
            entity, [_materializing_find(entity, predicate, [row])], instruction
        )


def test_materialization_validator_does_not_require_transaction_terminate_payload() -> None:
    entity = _balance_entity()
    instruction = {
        "mutation": "terminate",
        "target": {
            "entity": "Balance",
            "predicate": {"eq": {"attr": "Balance.id", "value": 1}},
        },
        "at": "2024-10-01T00:00:00+00:00",
    }
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)

    validate_predicate_write_materialization(
        entity,
        [
            _materializing_find(
                entity,
                predicate,
                [
                    {
                        "bal_id": 1,
                        "in_z": "2024-04-01T00:00:00+00:00",
                        "out_z": "infinity",
                    }
                ],
            )
        ],
        instruction,
    )


def test_materialization_validator_requires_a_whole_value_object_for_noop_planning() -> None:
    definition = deepcopy(_customer_entity().definition)
    definition["attributes"].append(
        {
            "name": "version",
            "type": "int32",
            "column": "version",
            "optimisticLocking": True,
        }
    )
    entity = Entity(definition=definition)
    instruction = {
        "mutation": "update",
        "target": {"entity": "Customer", "predicate": {"all": {}}},
        "assignments": [
            {
                "attr": "Customer.address",
                "value": {"street": "Main", "city": "Oslo", "phones": []},
            }
        ],
    }
    predicate = instruction["target"]["predicate"]
    assert isinstance(predicate, dict)

    with pytest.raises(PredicateWriteValidationError, match="address"):
        validate_predicate_write_materialization(
            entity,
            [_materializing_find(entity, predicate, [{"id": 1, "version": 1}])],
            instruction,
        )

    validate_predicate_write_materialization(
        entity,
        [
            _materializing_find(
                entity,
                predicate,
                [
                    {
                        "id": 1,
                        "version": 1,
                        "address": {"street": "Main", "city": "Oslo"},
                    }
                ],
            )
        ],
        instruction,
    )


def test_materialization_validator_rejects_temporal_write_without_a_find() -> None:
    instruction = {
        "mutation": "terminate",
        "target": {
            "entity": "Position",
            "predicate": {"eq": {"attr": "Position.id", "value": 1}},
        },
        "at": "2024-10-01T00:00:00+00:00",
        "validFrom": "2024-07-01T00:00:00+00:00",
    }

    with pytest.raises(PredicateWriteValidationError, match="preceding materializing find"):
        validate_predicate_write_materialization(_position_entity(), [], instruction)


def test_materialization_validator_allows_readless_unversioned_update_and_delete() -> None:
    entity = load_model(_COMPATIBILITY_ROOT, "models/wallet.yaml").root_entity
    update = {
        "mutation": "update",
        "target": {
            "entity": "Wallet",
            "predicate": {"lessThan": {"attr": "Wallet.balance", "value": 200.00}},
        },
        "assignments": [{"attr": "Wallet.balance", "value": 0.00}],
    }
    delete = {
        "mutation": "delete",
        "target": {
            "entity": "Wallet",
            "predicate": {"lessThan": {"attr": "Wallet.balance", "value": 200.00}},
        },
    }

    validate_predicate_write_materialization(entity, [], update)
    validate_predicate_write_materialization(entity, [], delete)


def test_schema_validation_rejects_a_readless_versioned_predicate_write(tmp_path: Path) -> None:
    core = tmp_path / "core"
    shutil.copytree(_REPO_ROOT / "core", core)
    case_path = (
        core
        / "compatibility"
        / "cases"
        / ("m-opt-lock-014-set-based-mixed-noop-materialize-locking.yaml")
    )
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    case["when"]["scenario"].pop(0)
    case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")

    errors = validate_tree(core / "compatibility")

    assert any(
        "m-opt-lock-014" in error and "requires a preceding materializing find" in error
        for error in errors
    )


def test_schema_validation_rejects_a_cache_hit_as_predicate_materialization(tmp_path: Path) -> None:
    core = tmp_path / "core"
    shutil.copytree(_REPO_ROOT / "core", core)
    case_path = (
        core
        / "compatibility"
        / "cases"
        / ("m-opt-lock-014-set-based-mixed-noop-materialize-locking.yaml")
    )
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    materialize = case["when"]["scenario"][0]
    materialize["roundTrips"] = 0
    materialize.pop("statements")
    case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")

    errors = validate_tree(core / "compatibility")

    assert any("m-opt-lock-014" in error and "real resolving read" in error for error in errors)


@pytest.mark.parametrize("operator", ["navigate", "exists", "notExists"])
def test_model_validator_accepts_related_entity_predicate_scope(operator: str) -> None:
    model = _orders_model()
    instruction = {
        "mutation": "update",
        "target": {
            "entity": "Order",
            "predicate": {
                operator: {
                    "rel": "Order.items",
                    "op": {"eq": {"attr": "OrderItem.sku", "value": "A-1"}},
                }
            },
        },
        "assignments": [{"attr": "Order.name", "value": "Renamed"}],
    }

    validate_predicate_write(model.root_entity, instruction)


@pytest.mark.parametrize("operator", ["nestedExists", "nestedNotExists"])
def test_model_validator_scopes_nested_exists_by_its_value_object_path(operator: str) -> None:
    """A ``nestedExists`` / ``nestedNotExists`` predicate contributes the class named
    by its required value-object ``path`` (``Class.valueObject``) to the scope check.

    So the same-class form (here carrying an element-scoped ``where`` whose
    element-relative refs name no class) stays in scope, while a path naming a
    DIFFERENT class is rejected as inconsistent. This pins that these where-bearing
    tags are NOT silently skipped by the shared reference-class walk.
    """
    entity = _customer_entity()

    validate_predicate_write(
        entity,
        {
            "mutation": "delete",
            "target": {
                "entity": "Customer",
                "predicate": {
                    operator: {
                        "path": "Customer.address.phones",
                        "where": {"nestedEq": {"path": "type", "value": "home"}},
                    }
                },
            },
        },
    )

    with pytest.raises(PredicateWriteValidationError, match="inconsistent"):
        validate_predicate_write(
            entity,
            {
                "mutation": "delete",
                "target": {
                    "entity": "Customer",
                    "predicate": {operator: {"path": "Wallet.address"}},
                },
            },
        )


def test_model_validator_accepts_atomic_top_level_value_object_assignment() -> None:
    entity = _customer_entity()
    instruction = {
        "mutation": "update",
        "target": {"entity": "Customer", "predicate": {"all": {}}},
        "assignments": [
            {
                "attr": "Customer.address",
                "value": {"street": "Main", "city": "Oslo", "phones": []},
            }
        ],
    }

    validate_predicate_write(entity, instruction)


def test_model_validator_accepts_array_for_many_value_object_assignment() -> None:
    entity = _customer_entity()
    definition = deepcopy(entity.definition)
    definition["valueObjects"][0]["multiplicity"] = "many"
    many_entity = Entity(definition=definition)
    instruction = {
        "mutation": "update",
        "target": {"entity": "Customer", "predicate": {"all": {}}},
        "assignments": [
            {
                "attr": "Customer.address",
                "value": [{"street": "Main", "city": "Oslo", "phones": []}],
            }
        ],
    }

    validate_predicate_write(many_entity, instruction)


def test_model_validator_rejects_non_document_value_object_assignment() -> None:
    entity = _customer_entity()
    instruction = {
        "mutation": "update",
        "target": {"entity": "Customer", "predicate": {"all": {}}},
        "assignments": [{"attr": "Customer.address", "value": ["not a document"]}],
    }

    with pytest.raises(PredicateWriteValidationError, match="value object"):
        validate_predicate_write(entity, instruction)


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
        validate_predicate_write(entity, instruction)
