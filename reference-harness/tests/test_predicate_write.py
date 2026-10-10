"""DB-free predicate-selected write contract tests."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from reference_harness.case import Case, Entity, Model, load_model
from reference_harness.case_runner import _validate_rejected_predicate_write
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
        "mutation": "amend",
        "target": {
            "entity": "Account",
            "predicate": {"lessThan": {"path": "Account.balance", "value": "200.00"}},
        },
        "assignments": [{"attr": "Account.balance", "value": "0.00"}],
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
                            "binds": ["0.00", 1],
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
        "objectQuery": {"target": entity.name, "predicate": predicate},
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


def test_schema_refuses_a_result_shaping_clause_in_a_write_selection() -> None:
    # A set-based write selects rows and shapes no result, and its `predicate` is
    # exactly the selection grammar — which carries no ordering, no cap, and no
    # Includes at all. The refusal is therefore the SCHEMA's, with nothing left for
    # a validator to restate.
    instruction = _update_instruction()
    target = instruction["target"]
    assert isinstance(target, dict)
    target["predicate"] = {"orderBy": [{"attr": "Account.balance"}]}
    assert next(_schema().iter_errors(_scenario_case(instruction)), None) is not None


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
        ("amend", {"assignments": []}),
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
    validate_predicate_write(entity, _update_instruction(), [entity.definition])


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
                {"lessThan": {"value": "200.00", "path": "Account.balance"}},
                [{"id": 1, "balance": "100.00", "version": 1}],
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
            [_materializing_find(entity, {"true": {}}, [{"id": 1, "version": 1}])],
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
            [{"objectQuery": {"target": "Account", "predicate": predicate}}],
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
            "predicate": {"eq": {"path": "Position.id", "value": 1}},
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
            "predicate": {"eq": {"path": "Position.id", "value": 1}},
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
        "mutation": "amend",
        "target": {
            "entity": "Balance",
            "predicate": {"eq": {"path": "Balance.id", "value": 1}},
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
            "predicate": {"eq": {"path": "Balance.id", "value": 1}},
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
        "mutation": "amend",
        "target": {"entity": "Customer", "predicate": {"true": {}}},
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
            "predicate": {"eq": {"path": "Position.id", "value": 1}},
        },
        "at": "2024-10-01T00:00:00+00:00",
        "validFrom": "2024-07-01T00:00:00+00:00",
    }

    with pytest.raises(PredicateWriteValidationError, match="preceding materializing find"):
        validate_predicate_write_materialization(_position_entity(), [], instruction)


def test_materialization_validator_allows_readless_unversioned_update_and_delete() -> None:
    entity = load_model(_COMPATIBILITY_ROOT, "models/wallet.yaml").root_entity
    update = {
        "mutation": "amend",
        "target": {
            "entity": "Wallet",
            "predicate": {"lessThan": {"path": "Wallet.balance", "value": 200.00}},
        },
        "assignments": [{"attr": "Wallet.balance", "value": 0.00}],
    }
    delete = {
        "mutation": "delete",
        "target": {
            "entity": "Wallet",
            "predicate": {"lessThan": {"path": "Wallet.balance", "value": 200.00}},
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


@pytest.mark.parametrize("operator", ["any", "none", "all"])
def test_model_validator_accepts_related_entity_predicate_scope(operator: str) -> None:
    model = _orders_model()
    instruction = {
        "mutation": "amend",
        "target": {
            "entity": "Order",
            "predicate": {
                operator: {
                    "path": "Order.items",
                    "where": {"eq": {"path": "sku", "value": "A-1"}},
                }
            },
        },
        "assignments": [{"attr": "Order.name", "value": "Renamed"}],
    }

    validate_predicate_write(model.root_entity, instruction, model.entity_defs)


@pytest.mark.parametrize("operator", ["any", "none"])
def test_model_validator_scopes_a_quantifier_by_its_path(operator: str) -> None:
    """A quantifier contributes the class its Entity-qualified ``path`` names to
    the scope check, while its ``where``'s relative paths name none.

    So the same-class form stays in scope, while a path naming a DIFFERENT class is
    rejected as inconsistent — these where-bearing tags are NOT silently skipped by
    the shared reference-class walk.
    """
    model = load_model(_COMPATIBILITY_ROOT, "models/customer.yaml")
    entity = model.root_entity

    validate_predicate_write(
        entity,
        {
            "mutation": "delete",
            "target": {
                "entity": "Customer",
                "predicate": {
                    operator: {
                        "path": "Customer.address.phones",
                        "where": {"eq": {"path": "type", "value": "home"}},
                    }
                },
            },
        },
        model.entity_defs,
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
            model.entity_defs,
        )


def test_model_validator_accepts_atomic_top_level_value_object_assignment() -> None:
    entity = _customer_entity()
    instruction = {
        "mutation": "amend",
        "target": {"entity": "Customer", "predicate": {"true": {}}},
        "assignments": [
            {
                "attr": "Customer.address",
                "value": {"street": "Main", "city": "Oslo", "phones": []},
            }
        ],
    }

    validate_predicate_write(entity, instruction, [entity.definition])


def test_model_validator_accepts_omitted_nested_many_assignment() -> None:
    entity = _customer_entity()
    instruction = {
        "mutation": "amend",
        "target": {"entity": "Customer", "predicate": {"true": {}}},
        "assignments": [
            {
                "attr": "Customer.address",
                "value": {"street": "Main", "city": "Oslo"},
            }
        ],
    }

    validate_predicate_write(entity, instruction, [entity.definition])


def test_model_validator_accepts_omitted_nullable_nested_one_assignment() -> None:
    entity = _customer_entity()
    instruction = {
        "mutation": "amend",
        "target": {"entity": "Customer", "predicate": {"true": {}}},
        "assignments": [
            {
                "attr": "Customer.address",
                "value": {"street": "Main", "city": "Oslo", "phones": []},
            }
        ],
    }

    validate_predicate_write(entity, instruction, [entity.definition])


def test_rejected_oracle_does_not_certify_assignment_missing_required_nested_one() -> None:
    model = deepcopy(load_model(_COMPATIBILITY_ROOT, "models/contact.yaml"))
    model.entity_defs[0]["layout"] = {"document": {"column": "payload"}}
    assert isinstance(model, Model)
    instruction = {
        "mutation": "amend",
        "target": {"entity": "Contact", "predicate": {"true": {}}},
        "assignments": [
            {
                "attr": "Contact.address",
                "value": {"street": "Main", "city": "Oslo", "phones": []},
            }
        ],
    }
    case = Case(
        path=Path("predicate-write-required-nested-one.yaml"),
        raw={
            "model": "models/contact.yaml",
            "tags": ["m-batch-write"],
            "shape": "rejected",
            "when": {"write": instruction},
            "then": {"rejectedRule": "write-value-type-mismatch"},
        },
        model=model,
    )

    with pytest.raises(PredicateWriteValidationError, match="Contact.address.geo.*non-nullable"):
        _validate_rejected_predicate_write(case, instruction)


def test_model_validator_accepts_array_for_many_value_object_assignment() -> None:
    entity = _customer_entity()
    definition = deepcopy(entity.definition)
    definition["valueObjects"][0]["multiplicity"] = "many"
    many_entity = Entity(definition=definition)
    instruction = {
        "mutation": "amend",
        "target": {"entity": "Customer", "predicate": {"true": {}}},
        "assignments": [
            {
                "attr": "Customer.address",
                "value": [{"street": "Main", "city": "Oslo", "phones": []}],
            }
        ],
    }

    validate_predicate_write(many_entity, instruction, [many_entity.definition])


def test_model_validator_rejects_non_document_value_object_assignment() -> None:
    entity = _customer_entity()
    instruction = {
        "mutation": "amend",
        "target": {"entity": "Customer", "predicate": {"true": {}}},
        "assignments": [{"attr": "Customer.address", "value": ["not a document"]}],
    }

    with pytest.raises(PredicateWriteValidationError, match="value object"):
        validate_predicate_write(entity, instruction, [entity.definition])


@pytest.mark.parametrize(
    ("instruction", "message"),
    [
        (
            {
                "mutation": "amend",
                "target": {
                    "entity": "Account",
                    "predicate": {"lessThan": {"path": "Wallet.balance", "value": "200.00"}},
                },
                "assignments": [{"attr": "Account.balance", "value": "0.00"}],
            },
            "inconsistent",
        ),
        (
            {
                "mutation": "amend",
                "target": {
                    "entity": "Account",
                    "predicate": {"true": {}},
                },
                "assignments": [
                    {"attr": "Account.balance", "value": "0.00"},
                    {"attr": "Account.balance", "value": "1.00"},
                ],
            },
            "duplicate",
        ),
        (
            {
                "mutation": "amend",
                "target": {"entity": "Account", "predicate": {"true": {}}},
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
        validate_predicate_write(entity, instruction, [entity.definition])


def _position_amendment(valid_from: str, until: str | None = None) -> dict[str, object]:
    instruction: dict[str, object] = {
        "mutation": "amend" if until is None else "amendUntil",
        "target": {
            "entity": "Position",
            "predicate": {"eq": {"path": "Position.value", "value": 100}},
        },
        "assignments": [{"attr": "Position.value", "value": 300}],
        "at": "2024-10-01T00:00:00+00:00",
        "validFrom": valid_from,
    }
    if until is not None:
        instruction["until"] = until
    return instruction


def _selection_at(
    entity: Entity, instruction: dict[str, object], valid_time: str, thru_z: str
) -> dict[str, object]:
    target = instruction["target"]
    assert isinstance(target, dict)
    find = _materializing_find(
        entity,
        target["predicate"],
        [
            {
                "pos_id": 1,
                "acct_num": "A",
                "val": 100,
                "from_z": "2024-01-01T00:00:00+00:00",
                "thru_z": thru_z,
                "in_z": "2024-04-01T00:00:00+00:00",
                "out_z": "infinity",
            }
        ],
    )
    query = find["objectQuery"]
    assert isinstance(query, dict)
    query["temporal"] = {"transaction-time": {"asOf": "latest"}, "valid-time": {"asOf": valid_time}}
    return find


def test_a_bitemporal_amendments_find_selects_at_its_valid_from() -> None:
    entity = _position_entity()
    instruction = _position_amendment("2024-03-01T00:00:00+00:00", "2024-05-01T00:00:00+00:00")
    covering = "2024-06-01T00:00:00+00:00"
    validate_predicate_write_materialization(
        entity,
        [_selection_at(entity, instruction, "2024-03-01T00:00:00+00:00", covering)],
        instruction,
    )
    with pytest.raises(PredicateWriteValidationError, match="as of the amendment's validFrom"):
        validate_predicate_write_materialization(
            entity, [_selection_at(entity, instruction, "latest", covering)], instruction
        )


def test_a_golden_bitemporal_amendments_selection_covers_its_window() -> None:
    entity = _position_entity()
    instruction = _position_amendment("2024-03-01T00:00:00+00:00")
    find = _selection_at(
        entity, instruction, "2024-03-01T00:00:00+00:00", "2024-06-01T00:00:00+00:00"
    )
    with pytest.raises(PredicateWriteValidationError, match="ends before the amendment's window"):
        validate_predicate_write_materialization(entity, [find], instruction)


def test_a_bitemporal_amendment_resolves_through_a_selection_at_its_valid_from() -> None:
    entity = _position_entity()
    instruction = _position_amendment("2024-03-01T00:00:00+00:00", "2024-05-01T00:00:00+00:00")
    covering = "2024-06-01T00:00:00+00:00"
    validate_predicate_write_materialization(
        entity,
        [
            _selection_at(entity, instruction, "2024-02-01T00:00:00+00:00", covering),
            _selection_at(entity, instruction, "2024-03-01T00:00:00+00:00", covering),
        ],
        instruction,
    )
