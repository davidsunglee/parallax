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
    SET_BASED_WRITE_TARGET_UNSUPPORTED,
    PredicateWriteValidationError,
    validate_predicate_write,
)
from reference_harness.schema_validate import validate_tree
from reference_harness.schemas import build_registry, load_schemas
from reference_harness.value_object_resolve import RejectionError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_CASE_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"
_REGISTRY = build_registry(load_schemas(_REPO_ROOT / "core"))


def _schema() -> Draft202012Validator:
    return Draft202012Validator(
        json.loads(_CASE_SCHEMA_PATH.read_text(encoding="utf-8")), registry=_REGISTRY
    )


def _update_instruction(entity: str = "Wallet") -> dict[str, object]:
    return {
        "mutation": "amend",
        "target": {
            "entity": entity,
            "predicate": {"lessThan": {"path": f"{entity}.balance", "value": "200.00"}},
        },
        "assignments": [{"attr": f"{entity}.balance", "value": "0.00"}],
    }


def _scenario_case(instruction: dict[str, object]) -> dict[str, object]:
    return {
        "model": "models/wallet.yaml",
        "tags": ["m-batch-write"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "write": instruction,
                    "databaseCalls": 1,
                    "statements": [
                        {
                            "sql": {"postgres": "update wallet set balance = ? where id = ?"},
                            "binds": ["0.00", 1],
                        }
                    ],
                }
            ]
        },
        "then": {"databaseCalls": 1},
    }


def _account_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/account.yaml").root_entity


def _wallet_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/wallet.yaml").root_entity


def _orders_model():
    return load_model(_COMPATIBILITY_ROOT, "models/orders.yaml")


def _customer_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/customer.yaml").root_entity


def _position_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/position.yaml").root_entity


def _balance_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/balance.yaml").root_entity


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
    target["predicate"] = {"orderBy": [{"attr": "Wallet.balance"}]}
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
        ("delete", {"assignments": [{"attr": "Wallet.balance", "value": 0.00}]}),
        ("terminate", {}),
        ("terminateUntil", {}),
        ("delete", {"validFrom": "2024-01-01T00:00:00+00:00"}),
        ("delete", {"at": "2024-01-01T00:00:00+00:00"}),
    ],
)
def test_schema_enforces_predicate_write_verb_shape(
    mutation: str, edits: dict[str, object]
) -> None:
    instruction = _update_instruction()
    instruction["mutation"] = mutation
    if mutation != "amend":
        instruction.pop("assignments")
    instruction.update(edits)
    assert next(_schema().iter_errors(_scenario_case(instruction)), None) is not None


def test_an_amendment_assigning_nothing_is_a_valid_predicate_write() -> None:
    # The empty amendment is judged like any other, then dropped (`m-batch-write`).
    instruction = _update_instruction()
    instruction["assignments"] = []
    assert next(_schema().iter_errors(_scenario_case(instruction)), None) is None
    entity = _wallet_entity()
    validate_predicate_write(entity, instruction, [entity.definition])


def test_schema_requires_an_amendment_to_state_its_assignments() -> None:
    instruction = _update_instruction()
    instruction.pop("assignments")
    assert next(_schema().iter_errors(_scenario_case(instruction)), None) is not None


def test_model_validator_accepts_a_scoped_assignable_predicate_write() -> None:
    entity = _wallet_entity()
    validate_predicate_write(entity, _update_instruction(), [entity.definition])


@pytest.mark.parametrize(
    ("entity", "kind"),
    [
        (_account_entity(), "versioned"),
        (_balance_entity(), "temporal"),
        (_position_entity(), "temporal"),
    ],
    ids=["versioned", "transaction-time", "bitemporal"],
)
@pytest.mark.parametrize("mutation", ["amend", "delete"])
def test_a_target_needing_an_observation_is_refused_before_anything_it_carries(
    entity: Entity, kind: str, mutation: str
) -> None:
    # Each object such a target holds is written against an observation of it, which
    # one readless statement cannot make (`m-batch-write`); the refusal is heard
    # before the predicate, which names a stranger here, and any assignment.
    instruction: dict[str, object] = {
        "mutation": mutation,
        "target": {
            "entity": entity.name,
            "predicate": {"lessThan": {"path": "Wallet.balance", "value": "200.00"}},
        },
    }
    if mutation == "amend":
        instruction["assignments"] = [{"attr": f"{entity.name}.nonsense", "value": 1}]

    with pytest.raises(RejectionError) as refused:
        validate_predicate_write(entity, instruction, [entity.definition])

    assert refused.value.rule == SET_BASED_WRITE_TARGET_UNSUPPORTED
    assert kind in refused.value.detail


def test_schema_validation_refuses_a_scenario_predicate_write_of_a_versioned_target(
    tmp_path: Path,
) -> None:
    core = tmp_path / "core"
    shutil.copytree(_REPO_ROOT / "core", core)
    case_path = (
        core / "compatibility" / "cases" / "m-batch-write-005-predicate-delete-readless.yaml"
    )
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    case["model"] = "models/account.yaml"
    write = case["when"]["scenario"][0]["write"]
    write["target"] = {
        "entity": "parallax.compatibility.Account",
        "predicate": {
            "lessThan": {"path": "parallax.compatibility.Account.balance", "value": "200.00"}
        },
    }
    case["when"]["scenario"].pop(1)
    case["then"]["databaseCalls"] = 1
    case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")

    errors = validate_tree(core / "compatibility")

    assert any(
        "m-batch-write-005" in error and SET_BASED_WRITE_TARGET_UNSUPPORTED in error
        for error in errors
    ), errors


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
                    "entity": "Wallet",
                    "predicate": {"lessThan": {"path": "Account.balance", "value": "200.00"}},
                },
                "assignments": [{"attr": "Wallet.balance", "value": "0.00"}],
            },
            "inconsistent",
        ),
        (
            {
                "mutation": "amend",
                "target": {
                    "entity": "Wallet",
                    "predicate": {"true": {}},
                },
                "assignments": [
                    {"attr": "Wallet.balance", "value": "0.00"},
                    {"attr": "Wallet.balance", "value": "1.00"},
                ],
            },
            "duplicate",
        ),
        (
            {
                "mutation": "amend",
                "target": {"entity": "Wallet", "predicate": {"true": {}}},
                "assignments": [{"attr": "Wallet.id", "value": 2}],
            },
            "primary key",
        ),
    ],
)
def test_model_validator_rejects_invalid_predicate_write(
    instruction: dict[str, object], message: str
) -> None:
    entity = _wallet_entity()
    with pytest.raises(PredicateWriteValidationError, match=message):
        validate_predicate_write(entity, instruction, [entity.definition])
