"""The buffered scenario write is a general ordered keyed buffer (m-unit-work).

`compatibility-case.schema.json`'s `bufferedWriteSequence` is an ORDERED buffer of
one-or-more KEYED write instructions a unit of work accumulates and flushes
together. It spans a single keyed write, a mixed multi-object flush (insert /
update / delete of DIFFERENT objects), and the two-keyed same-object coalescing
pair alike — same-object folding at flush is the RUNTIME coalescing rule, not a
structural constraint, so no cross-entry same-entity / same-primary-key equality is
imposed. Predicate-selected instructions inside a buffer stay EXCLUDED (keyed-only).

The generality is over objects and mutations, not over PROVENANCE: an entry
assigning a DB-computed write marker states a statement the framework issues
rather than a write a caller authors, so it is a choreography unit of its own —
the buffer's only entry, in an ungrouped step.

The structural half (one-or-more keyed entries, no predicate entry) is the JSON
Schema's; the three model-aware rules JSON Schema cannot express — member-name
honesty, the temporal singleton (`m-unit-work`: an entry on a temporal entity
carries exactly one row), and that framework provenance — are the harness
validator's. These DB-free probes pin both halves: the general keyed shapes — a
single write, a mixed multi-object flush, a buffer over different entities /
different keys, and the three same-transaction coalescing witnesses — are
ACCEPTED; a predicate-in-buffer entry is REJECTED (schema); and a row naming a
non-member, a plural temporal entry, or a marker entry sharing its buffer or its
group, is REJECTED (harness).
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
_PK_SEQUENCE = _defs("models/pk-sequence.yaml")


def _accepted(instructions: list[Any], entity_defs: list[dict[str, Any]]) -> bool:
    """A buffer is ACCEPTED only when BOTH layers pass — the schema structural shape
    (one-or-more keyed entries, no predicate entry) and the harness's three model-aware
    checks (member-name honesty, the temporal singleton, framework provenance), asked
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
        core / "compatibility" / "cases" / "m-txtime-write-008-same-tx-insert-update-coalesce.yaml"
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
        "m-txtime-write-008" in error and "not" in error and "Balance" in error for error in errors
    )


# --- a temporal entry carries exactly one row (m-unit-work) ---------------------


def test_a_plural_temporal_buffer_entry_is_rejected() -> None:
    # Each row of a milestone chain closes its own milestone, consumes its own
    # observation, and chains its own successors, so a temporal keyed instruction
    # carries exactly one row. The shared `rows` array admits a plural authoring
    # because the bound depends on whether the target is temporal, which only the
    # model knows — so the rule is decided here, at the authoring boundary both
    # implementations read, rather than separately inside each.
    probe = [
        {
            "mutation": "update",
            "entity": "Balance",
            "rows": [{"id": 1, "value": 150.00}, {"id": 2, "value": 250.00}],
            "at": "2024-06-01T00:00:00+00:00",
        }
    ]
    assert next(_buffered_validator().iter_errors(probe), None) is None
    errors: list[str] = []
    _validate_buffered_write(probe, _BALANCE, _OP, "probe", errors)
    assert any("exactly one" in error and "Balance" in error for error in errors)


def test_a_plural_non_temporal_buffer_entry_is_accepted() -> None:
    # The contrast: a non-temporal entry legitimately carries several rows — the
    # set-based flush `m-batch-write` collapses. Only the temporal target's own
    # milestone chain forbids it.
    probe = [
        {
            "mutation": "update",
            "entity": "Account",
            "rows": [{"id": 1, "balance": 5.0}, {"id": 2, "balance": 5.0}],
        }
    ]
    assert _accepted(probe, _ACCOUNT)


def test_whole_tree_validation_rejects_a_plural_temporal_buffer_entry(tmp_path: Path) -> None:
    def mutate(case: dict[str, Any]) -> None:
        case["when"]["scenario"][0]["write"][0]["rows"].append({"id": 2, "value": 1.0})

    errors = _corrupt_witness(tmp_path, mutate)
    assert any(
        "m-txtime-write-008" in error and "exactly one" in error and "Balance" in error
        for error in errors
    )


# --- a framework-marker entry is a choreography unit of its own -----------------

_REGISTRY_ADVANCE = {
    "mutation": "update",
    "entity": "PkSequence",
    "rows": [{"name": "badge_seq", "nextVal": {"increment": 1}}],
}

_BADGE_INSERT = {"mutation": "insert", "entity": "Badge", "rows": [{"id": 1, "holder": "Bo"}]}


def test_a_lone_framework_marker_entry_is_accepted() -> None:
    # The one composition the marker admits: its own buffer, its own unit. The
    # statement is the PK allocator's, and this is the shape that lets a runner
    # issue it without pretending a public verb accepted it.
    assert _accepted([_REGISTRY_ADVANCE], _PK_SEQUENCE)


def test_a_framework_marker_beside_a_caller_authored_entry_is_rejected() -> None:
    # No public verb accepts a DB-computed write marker, so this buffer asks a
    # single unit to state its registry advance around the write verbs and its
    # insert through them — half its DML outside the boundary the other half runs
    # in. Structurally schema-valid, which is why the model-aware layer decides it.
    probe = [_REGISTRY_ADVANCE, _BADGE_INSERT]
    assert next(_buffered_validator().iter_errors(probe), None) is None
    errors: list[str] = []
    _validate_buffered_write(probe, _PK_SEQUENCE, _OP, "probe", errors)
    assert any("only entry" in error for error in errors)


def test_two_framework_marker_entries_in_one_buffer_are_rejected() -> None:
    # Nothing here is caller-authored, so the rule that decides it is cardinality
    # rather than mixture: each marker is a unit of its own, and one buffer cannot
    # be two units.
    second = {**_REGISTRY_ADVANCE, "rows": [{"name": "ticket_seq", "nextVal": {"increment": 5}}]}
    probe = [_REGISTRY_ADVANCE, second]
    errors: list[str] = []
    _validate_buffered_write(probe, _PK_SEQUENCE, _OP, "probe", errors)
    assert any("only entry" in error for error in errors)


def test_a_framework_marker_entry_inside_a_uow_group_is_rejected() -> None:
    # A group's held unit of work buffers each entry through a public verb, so a
    # marker entry inside one has nothing to be buffered through — the same
    # entry the ungrouped buffer of one accepts.
    errors: list[str] = []
    _validate_buffered_write([_REGISTRY_ADVANCE], _PK_SEQUENCE, _OP, "probe", errors, grouped=True)
    assert any("`uow` group" in error for error in errors)


def test_a_value_object_document_shaped_like_a_marker_is_not_framework_work() -> None:
    # The field's declared role decides, never the value's shape: `address` is a
    # value object, so its literal document binds whole even when its only key
    # spells a marker — and the entry stays an ordinary caller-authored write that
    # may share its buffer.
    probe = [
        {
            "mutation": "update",
            "entity": "Customer",
            "rows": [{"id": 1, "address": {"increment": 1}}],
        },
        {"mutation": "delete", "entity": "Customer", "rows": [{"id": 2}]},
    ]
    errors: list[str] = []
    _validate_buffered_write(probe, _defs("models/customer.yaml"), _OP, "probe", errors)
    assert errors == []
