"""The buffered scenario write is a general ordered keyed buffer (m-unit-work).

`compatibility-case.schema.json`'s `bufferedWriteSequence` is an ORDERED buffer of
one-or-more KEYED write instructions a unit of work accumulates and flushes
together. It spans a single keyed write, a mixed multi-object flush (insert /
update / delete of DIFFERENT objects), and the two-keyed same-object coalescing
pair alike — same-object folding at flush is the RUNTIME coalescing rule, not a
structural constraint, so no cross-entry same-entity / same-primary-key equality is
imposed. Predicate-selected instructions inside a buffer stay EXCLUDED (keyed-only).

The structural half (one-or-more keyed entries, no predicate entry) is the JSON
Schema's; the per-entry member-name honesty JSON Schema cannot express is the
harness validator's. These DB-free probes pin both halves: the general keyed shapes
— a single write, a mixed multi-object flush, a buffer over different entities /
different keys, and the three same-transaction coalescing witnesses — are ACCEPTED;
a predicate-in-buffer entry is REJECTED (schema); and a row naming a non-member is
REJECTED (harness).
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
_OP = _SCHEMAS["operation.schema.json"]


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


def _accepted(instructions: list[Any], entity_defs: list[dict[str, Any]]) -> bool:
    """A buffer is ACCEPTED only when BOTH layers pass — the schema structural shape
    (one-or-more keyed entries, no predicate entry) and the harness member-name check."""
    schema_ok = next(_buffered_validator().iter_errors(instructions), None) is None
    harness_errors: list[str] = []
    _validate_buffered_write(instructions, entity_defs, _OP, "probe", harness_errors)
    return schema_ok and not harness_errors


# --- the three coalescing witness shapes stay ACCEPTED (the pair is a special case) -

_WITNESS_AUDIT = [
    {
        "mutation": "insert",
        "entity": "Balance",
        "rows": [{"id": 9, "acctNum": "D", "value": 100.00}],
        "at": "2024-06-01T00:00:00+00:00",
    },
    {
        "mutation": "update",
        "entity": "Balance",
        "rows": [{"id": 9, "value": 150.00}],
        "at": "2024-06-01T00:00:00+00:00",
    },
]

_WITNESS_BITEMP = [
    {
        "mutation": "insert",
        "entity": "Position",
        "rows": [{"id": 9, "acctNum": "D", "value": 100.00}],
        "validFrom": "2024-01-01T00:00:00+00:00",
        "at": "2024-01-01T00:00:00+00:00",
    },
    {
        "mutation": "update",
        "entity": "Position",
        "rows": [{"id": 9, "value": 150.00}],
        "at": "2024-01-01T00:00:00+00:00",
    },
]

_WITNESS_UNIT_WORK = [
    {
        "mutation": "insert",
        "entity": "Account",
        "rows": [{"id": 9, "owner": "Noether", "balance": 5.00}],
    },
    {"mutation": "delete", "entity": "Account", "rows": [{"id": 9}]},
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
            "rows": [{"id": 7, "owner": "N", "balance": 5.0}],
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
            "rows": [{"id": 9, "owner": "N", "balance": 5.0}],
        },
        {"mutation": "update", "entity": "Account", "rows": [{"id": 1, "balance": 20.0}]},
        {"mutation": "delete", "entity": "Account", "rows": [{"id": 3}]},
    ]
    assert _accepted(probe, _ACCOUNT)


def test_buffer_over_different_entities_is_accepted() -> None:
    # A general buffer legitimately spans different entities — no same-entity constraint.
    probe = [
        {
            "mutation": "insert",
            "entity": "Order",
            "rows": [
                {
                    "id": 1,
                    "name": "A",
                    "qty": 1,
                    "price": 1.0,
                    "active": True,
                    "orderedOn": "2024-01-01",
                }
            ],
        },
        {"mutation": "delete", "entity": "OrderItem", "rows": [{"id": 1}]},
    ]
    assert _accepted(probe, _ORDERS)


def test_buffer_over_different_primary_keys_is_accepted() -> None:
    # Same entity, two different keys (the m-opt-lock-012 abort pair: insert account 9 +
    # gated update account 2) — no same-primary-key constraint.
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "owner": "N", "balance": 5.0}],
        },
        {"mutation": "update", "entity": "Account", "rows": [{"id": 2, "balance": 6.0}]},
    ]
    assert _accepted(probe, _ACCOUNT)


# --- a predicate-in-buffer entry is REJECTED (keyed-only, schema) ---------------


def test_predicate_entry_in_buffer_is_rejected() -> None:
    # A predicate-selected instruction is the one generality the buffered form still
    # excludes (the JSON Schema's keyed-only structural rejection).
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "owner": "N", "balance": 5.0}],
        },
        {"mutation": "delete", "target": {"entity": "Account", "predicate": {"all": {}}}},
    ]
    assert next(_buffered_validator().iter_errors(probe), None) is not None
    assert not _accepted(probe, _ACCOUNT)


# --- a row naming a non-member is REJECTED (member honesty, harness) -------------


def test_row_naming_a_non_member_is_rejected() -> None:
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "owner": "N", "balance": 5.0, "bogus": 1}],
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
        core / "compatibility" / "cases" / "m-audit-write-008-same-tx-insert-update-coalesce.yaml"
    )
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    mutate(case)
    case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
    return validate_tree(core / "compatibility")


def test_whole_tree_validation_rejects_a_non_member_buffered_row_key(tmp_path: Path) -> None:
    def mutate(case: dict[str, Any]) -> None:
        # Name a key on the buffered INSERT row that is not a declared Balance member.
        case["when"]["scenario"][0]["write"][0]["rows"][0]["bogus"] = 1

    errors = _corrupt_witness(tmp_path, mutate)
    assert any(
        "m-audit-write-008" in error and "not" in error and "Balance" in error for error in errors
    )
