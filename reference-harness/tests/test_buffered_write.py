"""The buffered scenario write is the m-unit-work coalescing PAIR, nothing wider.

`compatibility-case.schema.json`'s `bufferedWriteSequence` exists ONLY to let the
three same-transaction coalescing witnesses (`m-audit-write-008`,
`m-bitemp-write-014`, `m-unit-work-010`) encode both mutations explicitly. It is
constrained to exactly that shape — exactly TWO keyed instructions, entry 0 a keyed
`insert`, entry 1 a keyed `update` / `delete`, both naming the SAME entity and the
SAME primary-key identity — and NOT a general N-instruction ordered buffer (which
stays the deferred string-label→structured migration). The structural half is the
JSON Schema's; the cross-entry same-object equalities it cannot express are the
harness validator's. These DB-free probes pin both halves: the reviewer's four
generality probes are REJECTED, and the three witness shapes are ACCEPTED.
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
    """A buffered pair is ACCEPTED only when BOTH layers pass — exactly the
    reviewer's direct probe (schema structural shape + harness cross-entry check)."""
    schema_ok = next(_buffered_validator().iter_errors(instructions), None) is None
    harness_errors: list[str] = []
    _validate_buffered_write(instructions, entity_defs, _OP, "probe", harness_errors)
    return schema_ok and not harness_errors


# --- the three witness shapes are ACCEPTED -------------------------------------

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
        "businessFrom": "2024-01-01T00:00:00+00:00",
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


# --- the four generality probes are REJECTED -----------------------------------


def test_probe_two_deletes_without_a_leading_insert_is_rejected() -> None:
    # No leading insert: entry 0 is not a keyed `insert`, so it is not a coalescing
    # pair (the JSON Schema's structural rejection).
    probe = [
        {"mutation": "delete", "entity": "Account", "rows": [{"id": 9}]},
        {"mutation": "delete", "entity": "Account", "rows": [{"id": 9}]},
    ]
    assert not _accepted(probe, _ACCOUNT)


def test_probe_different_entities_is_rejected() -> None:
    # Two different entities are not the SAME object, so not a coalescing pair (the
    # harness cross-entry same-entity check).
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
    errors: list[str] = []
    _validate_buffered_write(probe, _ORDERS, _OP, "probe", errors)
    assert any("SAME entity" in error for error in errors)
    assert not _accepted(probe, _ORDERS)


def test_probe_same_entity_different_primary_keys_is_rejected() -> None:
    # Same entity but two different keys: the inserted object is not the one updated,
    # so not a coalescing pair (the harness cross-entry same-primary-key check).
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "owner": "N", "balance": 5.0}],
        },
        {"mutation": "update", "entity": "Account", "rows": [{"id": 10, "balance": 6.0}]},
    ]
    errors: list[str] = []
    _validate_buffered_write(probe, _ACCOUNT, _OP, "probe", errors)
    assert any("SAME primary-key identity" in error for error in errors)
    assert not _accepted(probe, _ACCOUNT)


def test_probe_two_predicate_deletes_is_rejected() -> None:
    # A predicate-selected instruction is the speculative generality the buffered form
    # excludes (the JSON Schema's keyed-only structural rejection).
    probe = [
        {"mutation": "delete", "target": {"entity": "Account", "predicate": {"all": {}}}},
        {"mutation": "delete", "target": {"entity": "Account", "predicate": {"all": {}}}},
    ]
    assert next(_buffered_validator().iter_errors(probe), None) is not None
    assert not _accepted(probe, _ACCOUNT)


def test_probe_three_keyed_entries_is_rejected() -> None:
    # A third instruction is the general N-instruction buffer the form is NOT — the
    # deferred migration contract, kept out (the JSON Schema's exactly-two rejection).
    probe = [
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "owner": "N", "balance": 5.0}],
        },
        {"mutation": "update", "entity": "Account", "rows": [{"id": 9, "balance": 6.0}]},
        {"mutation": "delete", "entity": "Account", "rows": [{"id": 9}]},
    ]
    assert next(_buffered_validator().iter_errors(probe), None) is not None
    assert not _accepted(probe, _ACCOUNT)


# --- the cross-entry check is wired into whole-tree validation ------------------


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


def test_whole_tree_validation_rejects_a_different_key_coalescing_pair(tmp_path: Path) -> None:
    def mutate(case: dict[str, Any]) -> None:
        # Point the buffered UPDATE at a different object than the INSERT.
        case["when"]["scenario"][0]["write"][1]["rows"][0]["id"] = 99

    errors = _corrupt_witness(tmp_path, mutate)
    assert any(
        "m-audit-write-008" in error and "SAME primary-key identity" in error for error in errors
    )
