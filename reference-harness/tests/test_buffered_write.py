"""The buffered scenario write is a general ordered keyed buffer (m-unit-work).

`compatibility-case.schema.json`'s `bufferedWriteSequence` is an ORDERED buffer of
one-or-more KEYED write instructions a unit of work accumulates and flushes
together. It spans a single keyed write, a mixed multi-object flush (insert /
update / delete of DIFFERENT objects), and the two-keyed same-object coalescing
pair alike — same-object folding at flush is the RUNTIME coalescing rule, not a
structural constraint, so no cross-entry same-entity / same-primary-key equality is
imposed. A golden-graded scenario's buffer may also carry target submissions,
and a state-graded one also readless predicate writes and refused submissions.

The structural half (one-or-more keyed entries, no predicate entry) is the JSON
Schema's; the model-aware rules JSON Schema cannot express, such as member-name
honesty, are the harness validator's. These DB-free probes pin both halves: the
general keyed shapes — a single write, a mixed multi-object flush, a buffer over
different entities / different keys, a temporal entry of several rows, and the
three same-transaction coalescing witnesses — are ACCEPTED; a predicate entry is
REJECTED in a golden-graded case (schema), and a materializing one outside a
state-graded case (harness); and a row naming a non-member is REJECTED
(harness).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from reference_harness.case import load_model
from reference_harness.schema_validate import _validate_buffered_write, validate_tree
from reference_harness.schemas import build_registry, load_schemas

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE = _REPO_ROOT / "core"
_COMPATIBILITY_ROOT = _CORE / "compatibility"
_SCHEMAS = load_schemas(_CORE)
_REGISTRY = build_registry(_SCHEMAS)
_CASE_URL = _SCHEMAS["compatibility-case.schema.json"]["$id"]
_OP = _SCHEMAS["predicate.schema.json"]


def _buffered_validator() -> Draft202012Validator:
    """A validator rooted at the case schema's `bufferedWriteSequence` def."""
    return Draft202012Validator(
        {"$ref": f"{_CASE_URL}#/$defs/bufferedWriteSequence"}, registry=_REGISTRY
    )


def _defs(model_rel: str) -> list[dict[str, Any]]:
    return load_model(_COMPATIBILITY_ROOT, model_rel).entity_defs


_ACCOUNT = _defs("models/account.yaml")
_ORDERS = _defs("models/orders.yaml")
_BALANCE = _defs("models/balance.yaml")
_POSITION = _defs("models/position.yaml")
_SEQUENCE = _defs("models/buffered-sequence-layout-twin-columns.yaml")


def _accepted(instructions: list[Any], entity_defs: list[dict[str, Any]]) -> bool:
    """A buffer is ACCEPTED only when BOTH layers pass — the schema structural shape
    (one-or-more submissions) and the harness's model-aware
    checks (member-name honesty, keyed applicability, framework provenance), asked
    here for an UNGROUPED step."""
    schema_ok = next(_buffered_validator().iter_errors(instructions), None) is None
    harness_errors: list[str] = []
    _validate_buffered_write(instructions, entity_defs, _OP, "probe", harness_errors)
    return schema_ok and not harness_errors


# --- the three coalescing witness shapes stay ACCEPTED (the pair is a special case) -

_WITNESS_AUDIT = [
    {
        "mutation": "insert",
        "entity": "Balance",
        "row": {"id": 9, "acctNum": "D", "value": 100.00},
        "at": "2024-06-01T00:00:00+00:00",
    },
    {
        "mutation": "amend",
        "entity": "Balance",
        "row": {"id": 9, "value": 150.00},
        "at": "2024-06-01T00:00:00+00:00",
    },
]

_WITNESS_BITEMP = [
    {
        "mutation": "insert",
        "entity": "Position",
        "row": {"id": 9, "acctNum": "D", "value": 100.00},
        "validFrom": "2024-01-01T00:00:00+00:00",
        "at": "2024-01-01T00:00:00+00:00",
    },
    {
        "mutation": "amend",
        "entity": "Position",
        "row": {"id": 9, "value": 150.00},
        "validFrom": "2024-01-01T00:00:00+00:00",
        "at": "2024-01-01T00:00:00+00:00",
    },
]

_WITNESS_UNIT_WORK = [
    {
        "mutation": "insert",
        "entity": "Account",
        "row": {"id": 9, "owner": "Noether", "balance": 5.00},
    },
    {"mutation": "delete", "entity": "Account", "row": {"id": 9}},
]


@pytest.mark.parametrize(
    ("instructions", "entity_defs"),
    [
        (_WITNESS_AUDIT, _BALANCE),
        (_WITNESS_BITEMP, _POSITION),
        (_WITNESS_UNIT_WORK, _ACCOUNT),
    ],
)
def test_coalescing_witness_shapes_are_accepted(
    instructions: list[Any], entity_defs: list[dict[str, Any]]
) -> None:
    assert _accepted(instructions, entity_defs), "a coalescing witness pair must validate"


# --- the general keyed shapes the migration demands are ACCEPTED ----------------


def test_single_keyed_write_is_accepted() -> None:
    # A buffer of one — the single INSERT / UPDATE / DELETE writes the migration adds.
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "row": {"id": 7, "owner": "N", "balance": 5.0},
        }
    ]
    assert _accepted(probe, _ACCOUNT)


def test_mixed_multi_object_flush_is_accepted() -> None:
    # Three different objects in one buffer (the m-unit-work-009 mixed flush): insert
    # account 9, update account 1, delete account 3.
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "row": {"id": 9, "owner": "N", "balance": 5.0},
        },
        {"mutation": "amend", "entity": "Account", "row": {"id": 1, "balance": 20.0}},
        {"mutation": "delete", "entity": "Account", "row": {"id": 3}},
    ]
    assert _accepted(probe, _ACCOUNT)


def test_buffer_over_different_entities_is_accepted() -> None:
    # A general buffer legitimately spans different entities — no same-entity constraint.
    probe = [
        {
            "mutation": "insert",
            "entity": "Order",
            "row": {
                "id": 1,
                "name": "A",
                "qty": 1,
                "price": 1.0,
                "active": True,
                "orderedOn": "2024-01-01",
            },
        },
        {"mutation": "delete", "entity": "OrderItem", "row": {"id": 1}},
    ]
    assert _accepted(probe, _ORDERS)


def test_buffer_over_different_primary_keys_is_accepted() -> None:
    # Same entity, two different keys (the m-concurrency-012 abort pair: insert account 9 +
    # gated update account 2) — no same-primary-key constraint.
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "row": {"id": 9, "owner": "N", "balance": 5.0},
        },
        {"mutation": "amend", "entity": "Account", "row": {"id": 2, "balance": 6.0}},
    ]
    assert _accepted(probe, _ACCOUNT)


# --- a predicate submission over a versioned target is refused ---------------


def test_a_predicate_submission_over_a_versioned_target_is_refused() -> None:
    # A versioned target's objects are each written against an observation of
    # them, which one readless statement cannot make (`m-batch-write`), so no
    # buffer carries such a submission, state-graded or not.
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "row": {"id": 9, "owner": "N", "balance": 5.0},
        },
        {"mutation": "delete", "target": {"entity": "Account", "predicate": {"true": {}}}},
    ]
    errors: list[str] = []
    _validate_buffered_write(probe, _ACCOUNT, _OP, "probe", errors)
    assert any("set-based-write-target-unsupported" in error for error in errors)
    assert not _accepted(probe, _ACCOUNT)


def _scenario_document(write: list[Any], **top: Any) -> dict[str, Any]:
    return {
        "model": "models/orders.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        **top,
        "when": {"scenario": [{"uow": "g", "write": write, "databaseCalls": 0}]},
        "then": {
            "tableState": {"px": {"order_item": []}},
            "units": {"g": {"outcome": "committed"}},
        },
    }


_PREDICATE_WRITE = {
    "mutation": "amend",
    "target": {
        "entity": "OrderItem",
        "predicate": {"lessThan": {"path": "OrderItem.quantity", "value": 3}},
    },
    "assignments": [{"attr": "OrderItem.sku", "value": "Z"}],
}


def test_a_golden_graded_buffer_is_keyed_and_a_state_graded_one_carries_predicate_writes() -> None:
    validator = Draft202012Validator({"$ref": _CASE_URL}, registry=_REGISTRY)
    golden = _scenario_document([_PREDICATE_WRITE])
    assert next(validator.iter_errors(golden), None) is not None
    state = _scenario_document(
        [_PREDICATE_WRITE],
        grading="state",
        compileEligibility={"mode": "run-only", "reason": "query-result-dependent"},
    )
    assert next(validator.iter_errors(state), None) is None


_TARGET_SUBMISSION = {
    "mutation": "amend",
    "entity": "OrderItem",
    "row": {"id": 1, "sku": "Z"},
    "ifVersion": 1,
}


def test_a_golden_graded_buffer_carries_a_target_submission_but_no_refused_one() -> None:
    validator = Draft202012Validator({"$ref": _CASE_URL}, registry=_REGISTRY)
    assert next(validator.iter_errors(_scenario_document([_TARGET_SUBMISSION])), None) is None
    refused = {**_TARGET_SUBMISSION, "expectError": "write-evidence-already-claimed"}
    assert next(validator.iter_errors(_scenario_document([refused])), None) is not None


_STATE_FIND = {"uow": "g", "objectQuery": {"target": "OrderItem", "predicate": {"true": {}}}}
_STATE_INSERT = {
    "mutation": "insert",
    "entity": "OrderItem",
    "row": {"id": 1, "quantity": 1, "sku": "A"},
}

_STATE_GRAPH_FIND = {
    "uow": "g",
    "objectQuery": {
        "target": "parallax.compatibility.Order",
        "predicate": {"true": {}},
        "includes": [{"segments": [{"rel": "parallax.compatibility.Order.items"}]}],
    },
    "expectGraph": {"OrderItem": []},
}


def _state_graded(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": "models/orders.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "grading": "state",
        "compileEligibility": {"mode": "run-only", "reason": "query-result-dependent"},
        "when": {"scenario": steps},
        "then": {
            "tableState": {"px": {"order_item": []}},
            "units": {"g": {"outcome": "committed"}},
        },
    }


@pytest.mark.parametrize(
    "steps",
    [
        pytest.param([{"uow": "g", "write": _PREDICATE_WRITE}], id="a-direct-predicate-write"),
        pytest.param([{"uow": "g", "write": "amend"}], id="a-write-label"),
        pytest.param(
            [_STATE_FIND, {"action": "mutate", "on": 0, "set": {"sku": "B"}}], id="an-action-step"
        ),
        pytest.param([_STATE_GRAPH_FIND], id="a-graph-observable"),
        pytest.param([_STATE_FIND, {**_STATE_FIND, "sameObjectAs": 0}], id="an-identity-claim"),
        pytest.param(
            [_STATE_FIND, {**_STATE_FIND, "differentObjectFrom": 0}], id="a-distinctness-claim"
        ),
        pytest.param(
            [{**_STATE_FIND, "expectError": "write-value-not-stored"}], id="a-find-refusal"
        ),
        pytest.param(
            [{"uow": "g", "write": [_STATE_INSERT], "expectError": "write-value-not-stored"}],
            id="a-write-step-refusal",
        ),
        pytest.param(
            [{"uow": "g", "write": [_STATE_INSERT], "expectRows": []}], id="a-write-step-result"
        ),
        pytest.param([_STATE_FIND, {**_STATE_FIND, "on": 0}], id="a-step-level-source"),
        pytest.param([{**_STATE_FIND, "identityAttr": "id"}], id="an-identity-attribute"),
        pytest.param([{"write": [_STATE_INSERT], "rollback": True}], id="a-step-level-fate"),
    ],
)
def test_a_state_graded_case_states_only_what_its_run_reports(steps: list[dict[str, Any]]) -> None:
    validator = Draft202012Validator({"$ref": _CASE_URL}, registry=_REGISTRY)
    control = _state_graded([_STATE_FIND, {"uow": "g", "write": [_STATE_INSERT]}])
    assert next(validator.iter_errors(control), None) is None
    assert next(validator.iter_errors(_state_graded(steps)), None) is not None


_T0 = "2023-12-01T00:00:00.000000Z"
_ACCOUNT_TARGET = {
    "mutation": "amend",
    "entity": "SequenceAccount",
    "row": {"id": 1, "balance": 5},
}
_TAG_TARGET = {"mutation": "amend", "entity": "SequenceTag", "row": {"id": 1, "quantity": 2}}
_SPAN_TARGET = {
    "mutation": "amend",
    "entity": "SequenceSpan",
    "row": {"id": 1, "amount": 5},
    "validFrom": _T0,
}
_BALANCE_TARGET = {"mutation": "amend", "entity": "Balance", "row": {"id": 1, "value": "5.00"}}


@pytest.mark.parametrize(
    ("entry", "entity_defs"),
    [
        pytest.param({**_ACCOUNT_TARGET, "ifVersion": 1}, _SEQUENCE, id="versioned"),
        pytest.param({**_SPAN_TARGET, "ifTxStart": _T0}, _SEQUENCE, id="bitemporal"),
        pytest.param(
            {"mutation": "delete", "entity": "SequenceAccount", "row": {"id": 1}, "ifVersion": 1},
            _SEQUENCE,
            id="a-versioned-deletion",
        ),
        pytest.param(
            {**_SPAN_TARGET, "mutation": "terminate", "row": {"id": 1}, "ifTxStart": _T0},
            _SEQUENCE,
            id="a-bitemporal-termination",
        ),
        pytest.param(
            {
                **_SPAN_TARGET,
                "mutation": "terminateUntil",
                "row": {"id": 1},
                "ifTxStart": _T0,
                "until": "2024-01-01T00:00:00.000000Z",
            },
            _SEQUENCE,
            id="a-bounded-bitemporal-termination",
        ),
        pytest.param(
            {**_BALANCE_TARGET, "mutation": "terminate", "row": {"id": 1}, "ifTxStart": _T0},
            _BALANCE,
            id="a-transaction-time-only-termination",
        ),
        pytest.param({**_BALANCE_TARGET, "ifTxStart": _T0}, _BALANCE, id="transaction-time-only"),
        pytest.param(
            {**_ACCOUNT_TARGET, "mutation": "replace", "ifVersion": 1},
            _SEQUENCE,
            id="a-replacement-omitting-only-nullable-members",
        ),
    ],
)
def test_a_target_submission_states_the_condition_its_target_takes(
    entry: dict[str, Any], entity_defs: list[dict[str, Any]]
) -> None:
    assert _accepted([entry], entity_defs)


@pytest.mark.parametrize(
    ("entry", "entity_defs"),
    [
        pytest.param(
            {**_ACCOUNT_TARGET, "row": {"balance": 5}, "ifVersion": 1},
            _SEQUENCE,
            id="a-target-without-its-key",
        ),
        pytest.param(
            {**_ACCOUNT_TARGET, "row": {"id": None, "balance": 5}, "ifVersion": 1},
            _SEQUENCE,
            id="a-target-keyed-by-null",
        ),
        pytest.param(
            {**_ACCOUNT_TARGET, "row": {"id": "not-an-int", "balance": 5}, "ifVersion": 1},
            _SEQUENCE,
            id="a-target-keyed-by-another-type",
        ),
        pytest.param(
            {**_ACCOUNT_TARGET, "row": {"id": 1, "balance": "five"}, "ifVersion": 1},
            _SEQUENCE,
            id="a-target-assigning-another-type",
        ),
        pytest.param(
            {**_ACCOUNT_TARGET, "row": {"id": 1, "version": 2}, "ifVersion": 1},
            _SEQUENCE,
            id="a-target-assigning-a-framework-owned-member",
        ),
        pytest.param(
            {**_ACCOUNT_TARGET, "mutation": "replace", "row": {"id": 1}, "ifVersion": 1},
            _SEQUENCE,
            id="a-replacement-omitting-a-required-member",
        ),
        pytest.param(
            {**_ACCOUNT_TARGET, "ifTxStart": _T0}, _SEQUENCE, id="a-versioned-target-by-its-start"
        ),
        pytest.param({**_TAG_TARGET, "ifVersion": 1}, _SEQUENCE, id="an-unversioned-revision"),
        pytest.param(
            {**_SPAN_TARGET, "mutation": "delete", "row": {"id": 1}, "ifTxStart": _T0},
            _SEQUENCE,
            id="a-temporal-deletion",
        ),
        pytest.param(
            {**_ACCOUNT_TARGET, "mutation": "terminate", "row": {"id": 1}, "ifVersion": 1},
            _SEQUENCE,
            id="a-non-temporal-termination",
        ),
        pytest.param(
            {**_ACCOUNT_TARGET, "mutation": "delete", "ifVersion": 1},
            _SEQUENCE,
            id="a-deletion-assigning-a-member",
        ),
        pytest.param(
            {**_SPAN_TARGET, "ifVersion": 1}, _SEQUENCE, id="a-temporal-target-by-a-version"
        ),
        pytest.param(
            {key: value for key, value in _SPAN_TARGET.items() if key != "validFrom"}
            | {"ifTxStart": _T0},
            _SEQUENCE,
            id="a-bitemporal-target-without-its-window",
        ),
        pytest.param(
            {**_BALANCE_TARGET, "ifTxStart": _T0, "validFrom": _T0},
            _BALANCE,
            id="a-transaction-time-only-target-with-a-window",
        ),
    ],
)
def test_a_target_submission_stating_another_condition_is_refused(
    entry: dict[str, Any], entity_defs: list[dict[str, Any]]
) -> None:
    errors: list[str] = []
    _validate_buffered_write([entry], entity_defs, _OP, "probe", errors)
    assert any("target write" in error for error in errors)


# --- a row naming a non-member is REJECTED (member honesty, harness) -------------


def test_row_naming_a_non_member_is_rejected() -> None:
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "row": {"id": 9, "owner": "N", "balance": 5.0, "bogus": 1},
        }
    ]
    errors: list[str] = []
    _validate_buffered_write(probe, _ACCOUNT, _OP, "probe", errors)
    assert any("bogus" in error and "not" in error for error in errors)
    assert not _accepted(probe, _ACCOUNT)


# --- the member-honesty check is wired into whole-tree validation ---------------


def _corrupt_witness(tmp_path: Path, mutate: Any) -> list[str]:
    core = tmp_path / "core"
    shutil.copytree(_CORE, core)
    case_path = (
        core
        / "compatibility"
        / "cases"
        / "m-temporal-write-008-same-tx-insert-update-coalesce.yaml"
    )
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    mutate(case)
    case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
    return validate_tree(core / "compatibility")


def test_whole_tree_validation_rejects_a_non_member_buffered_row_key(tmp_path: Path) -> None:
    def mutate(case: dict[str, Any]) -> None:
        # Name a key on the buffered INSERT row that is not a declared Balance member.
        case["when"]["scenario"][0]["write"][0]["row"]["bogus"] = 1

    errors = _corrupt_witness(tmp_path, mutate)
    assert any(
        "m-temporal-write-008" in error and "not" in error and "Balance" in error
        for error in errors
    )


# --- a keyed submission is one keyed write instruction (m-case-format) ----------


def test_a_keyed_submission_names_one_object_through_its_one_row() -> None:
    # A later row naming the target submission's object would otherwise write that
    # object beside the target submission while the entry reads as naming another.
    validator = Draft202012Validator({"$ref": _CASE_URL}, registry=_REGISTRY)
    insert = {"mutation": "insert", "entity": "OrderItem", "row": {"id": 3, "sku": "C"}}
    hidden = {key: value for key, value in insert.items() if key != "row"} | {
        "rows": [insert["row"], {"id": 1, "sku": "A"}]
    }
    assert (
        next(validator.iter_errors(_scenario_document([insert, _TARGET_SUBMISSION])), None) is None
    )
    assert (
        next(validator.iter_errors(_scenario_document([hidden, _TARGET_SUBMISSION])), None)
        is not None
    )


def test_a_value_object_document_with_any_keys_shares_its_buffer() -> None:
    # The field's declared role decides, never the value's shape: `address` is a
    # value object, so its literal document binds whole whatever keys it holds,
    # and the entry stays an ordinary caller-authored write that may share its
    # buffer.
    probe = [
        {
            "mutation": "amend",
            "entity": "Customer",
            "row": {"id": 1, "address": {"increment": 1}},
        },
        {"mutation": "delete", "entity": "Customer", "row": {"id": 2}},
    ]
    errors: list[str] = []
    _validate_buffered_write(probe, _defs("models/customer.yaml"), _OP, "probe", errors)
    assert errors == []
