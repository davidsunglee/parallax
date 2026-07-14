"""Write-instruction IR + serde unit tests (m-unit-work, Docker-free).

Proves the canonical write-instruction serde round-trip contract
(``serialize(deserialize(x)) == x``) over every instruction shape — keyed and
predicate-selected, non-temporal / audit-only / bitemporal bounded and unbounded
— cross-checked against ``core/schemas/write-instruction.schema.json`` itself, plus
the structural rejection branches (the axis-explicit business-bound pairing, the
forbidden observation control keys, the smuggled processing-instant alias `at`),
and the metamodel-aware member-name honesty validator.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast

import jsonschema
import pytest

from conftest import REPO_ROOT
from parallax.conformance import models
from parallax.core import op_algebra
from parallax.core.unit_work import instructions as wi

pytestmark = pytest.mark.unit

_SCHEMA = cast(
    "dict[str, Any]",
    json.loads((REPO_ROOT / "core" / "schemas" / "write-instruction.schema.json").read_text()),
)
_validate = cast("Callable[[object, object], None]", jsonschema.validate)

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_BALANCE = _MODELS["balance"]
_POSITION = _MODELS["position"]

_B1 = "2024-01-01T00:00:00+00:00"
_B2 = "2024-06-01T00:00:00+00:00"

# Every canonical instruction shape, authored in the axis-explicit spelling with no
# processing instant (Clock context) — the coalescing witnesses' target buffered
# form and the full keyed/predicate mutation surface.
_INSTRUCTIONS: list[tuple[str, dict[str, Any]]] = [
    (
        "keyed-insert-nontemporal",
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "owner": "Noether", "balance": 5.00}],
        },
    ),
    (
        "keyed-update-nontemporal-sparse",
        {
            "mutation": "update",
            "entity": "Account",
            "rows": [{"id": 1, "balance": 0.00}],
        },
    ),
    (
        "keyed-delete-nontemporal",
        {
            "mutation": "delete",
            "entity": "Account",
            "rows": [{"id": 9}],
        },
    ),
    (
        "keyed-insert-audit",
        {
            "mutation": "insert",
            "entity": "Balance",
            "rows": [{"id": 9, "acctNum": "D", "value": 100.00}],
        },
    ),
    (
        "keyed-terminate-audit",
        {
            "mutation": "terminate",
            "entity": "Balance",
            "rows": [{"id": 9}],
        },
    ),
    (
        "keyed-insert-bitemporal-plain",
        {
            "mutation": "insert",
            "entity": "Position",
            "rows": [{"id": 9, "acctNum": "D", "value": 100.00}],
            "businessFrom": _B1,
        },
    ),
    (
        "keyed-insertUntil-bitemporal-bounded",
        {
            "mutation": "insertUntil",
            "entity": "Position",
            "rows": [{"id": 9, "acctNum": "D", "value": 100.00}],
            "businessFrom": _B1,
            "businessTo": _B2,
        },
    ),
    (
        "keyed-updateUntil-bitemporal-bounded",
        {
            "mutation": "updateUntil",
            "entity": "Position",
            "rows": [{"id": 9, "value": 150.00}],
            "businessFrom": _B1,
            "businessTo": _B2,
        },
    ),
    (
        "keyed-terminateUntil-bitemporal-bounded",
        {
            "mutation": "terminateUntil",
            "entity": "Position",
            "rows": [{"id": 9}],
            "businessFrom": _B1,
            "businessTo": _B2,
        },
    ),
    (
        "keyed-insert-valueobject-document",
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "owner": "Noether", "balance": 5.00}],
        },
    ),
    (
        "keyed-insert-computed-marker",
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": {"computed": "maxPlusOne"}, "owner": "Ada", "balance": 1.00}],
        },
    ),
    (
        "predicate-update-nontemporal",
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Account.balance", "value": 0.00}],
        },
    ),
    (
        "predicate-delete-nontemporal",
        {
            "mutation": "delete",
            "target": {
                "entity": "Account",
                "predicate": {"eq": {"attr": "Account.id", "value": 1}},
            },
        },
    ),
    (
        "predicate-terminate-audit",
        {
            "mutation": "terminate",
            "target": {"entity": "Balance", "predicate": {"all": {}}},
        },
    ),
    (
        "predicate-update-bitemporal-plain",
        {
            "mutation": "update",
            "target": {"entity": "Position", "predicate": {"all": {}}},
            "assignments": [{"attr": "Position.value", "value": 150.00}],
            "businessFrom": _B1,
        },
    ),
    (
        "predicate-updateUntil-bitemporal-bounded",
        {
            "mutation": "updateUntil",
            "target": {"entity": "Position", "predicate": {"all": {}}},
            "assignments": [{"attr": "Position.value", "value": 150.00}],
            "businessFrom": _B1,
            "businessTo": _B2,
        },
    ),
    (
        "predicate-terminateUntil-bitemporal-bounded",
        {
            "mutation": "terminateUntil",
            "target": {"entity": "Position", "predicate": {"all": {}}},
            "businessFrom": _B1,
            "businessTo": _B2,
        },
    ),
]


@pytest.mark.parametrize("doc", [d for _, d in _INSTRUCTIONS], ids=[i for i, _ in _INSTRUCTIONS])
def test_every_shape_validates_against_the_schema(doc: dict[str, Any]) -> None:
    _validate(doc, _SCHEMA)


@pytest.mark.parametrize("doc", [d for _, d in _INSTRUCTIONS], ids=[i for i, _ in _INSTRUCTIONS])
def test_serde_round_trip(doc: dict[str, Any]) -> None:
    # serialize(deserialize(x)) == x for every canonical shape (the write-side of
    # the m-op-algebra serde contract), matching the schema-validated document.
    assert wi.serialize(wi.deserialize(doc)) == doc


def test_python_construction_round_trips() -> None:
    instruction = wi.KeyedWrite(
        mutation="insertUntil",
        entity="Position",
        rows=({"id": 9, "value": 150.00},),
        business_from=_B1,
        business_to=_B2,
    )
    assert wi.deserialize(wi.serialize(instruction)) == instruction


def test_keyed_rows_are_frozen_views() -> None:
    instruction = wi.KeyedWrite(mutation="delete", entity="Account", rows=({"id": 9},))
    with pytest.raises(TypeError):
        cast("dict[str, object]", instruction.rows[0])["id"] = 10


def test_predicate_carries_a_canonical_operation_node() -> None:
    instruction = wi.deserialize(
        {"mutation": "delete", "target": {"entity": "Account", "predicate": {"all": {}}}}
    )
    assert isinstance(instruction, wi.PredicateWrite)
    assert instruction.target.predicate == op_algebra.All()


# --------------------------------------------------------------------------- #
# Structural rejection.                                                        #
# --------------------------------------------------------------------------- #
def test_processing_instant_alias_is_rejected() -> None:
    # `at` is the corpus's Clock-context alias; it is NOT a canonical instruction
    # field, so no caller-facing shape can smuggle a processing instant in (ADR 0010).
    with pytest.raises(wi.WriteInstructionError, match="unexpected key"):
        wi.deserialize(
            {
                "mutation": "insert",
                "entity": "Balance",
                "rows": [{"id": 9, "value": 100.00}],
                "at": _B2,
            }
        )


@pytest.mark.parametrize("forbidden", ["observedVersion", "observedInZ"])
def test_forbidden_observation_control_key_is_rejected(forbidden: str) -> None:
    # The transaction observation is attached per row at flush, never authored on
    # the durable instruction (ADR 0013).
    with pytest.raises(wi.WriteInstructionError, match="forbidden observation control key"):
        wi.deserialize(
            {
                "mutation": "update",
                "entity": "Account",
                "rows": [{"id": 1, "balance": 0.00, forbidden: 3}],
            }
        )


def test_ambiguous_and_shapeless_instructions_are_rejected() -> None:
    with pytest.raises(wi.WriteInstructionError, match="ambiguous"):
        wi.deserialize(
            {
                "mutation": "delete",
                "entity": "Account",
                "rows": [{"id": 1}],
                "target": {"entity": "Account", "predicate": {"all": {}}},
            }
        )
    with pytest.raises(wi.WriteInstructionError, match=r"`rows`.*or.*`target`"):
        wi.deserialize({"mutation": "delete", "entity": "Account"})
    with pytest.raises(wi.WriteInstructionError, match="must be a mapping"):
        wi.deserialize([1, 2, 3])


@pytest.mark.parametrize(
    "doc, match",
    [
        ({"entity": "Account", "rows": [{"id": 1}]}, "missing required"),
        (
            {"mutation": "insert", "entity": "Account", "rows": [{"id": 1}], "note": "x"},
            "unexpected key",
        ),
        (
            {"mutation": "nope", "entity": "Account", "rows": [{"id": 1}]},
            "`mutation` must be one of",
        ),
        ({"mutation": "insert", "entity": "", "rows": [{"id": 1}]}, "non-empty entity name"),
        ({"mutation": "insert", "entity": "Account", "rows": []}, "non-empty list"),
        ({"mutation": "insert", "entity": "Account", "rows": [1]}, "each row must be a mapping"),
        (
            {"mutation": "insert", "entity": "Account", "rows": [{"id": 1}], "businessTo": _B2},
            "MUST NOT carry `businessTo`",
        ),
        (
            {
                "mutation": "insertUntil",
                "entity": "Position",
                "rows": [{"id": 1}],
                "businessFrom": _B1,
            },
            "MUST carry both",
        ),
        (
            {"mutation": "insert", "entity": "Account", "rows": [{"id": 1}], "businessFrom": ""},
            "non-empty instant string",
        ),
    ],
)
def test_keyed_structural_rejections(doc: dict[str, Any], match: str) -> None:
    with pytest.raises(wi.WriteInstructionError, match=match):
        wi.deserialize(doc)


@pytest.mark.parametrize(
    "doc, match",
    [
        (
            {"mutation": "update", "target": {"entity": "Account", "predicate": {"all": {}}}},
            "MUST carry `assignments`",
        ),
        (
            {
                "mutation": "delete",
                "target": {"entity": "Account", "predicate": {"all": {}}},
                "assignments": [{"attr": "Account.balance", "value": 0}],
            },
            "MUST NOT carry `assignments`",
        ),
        (
            {"mutation": "insert", "target": {"entity": "Account", "predicate": {"all": {}}}},
            "`mutation` must be one of",
        ),
        ({"mutation": "delete", "target": [1, 2]}, "`target` must be a mapping"),
        ({"mutation": "delete", "target": {"entity": "Account"}}, "missing required"),
        (
            {"mutation": "delete", "target": {"entity": "Account", "predicate": 5}},
            "`target.predicate` must be a mapping",
        ),
        (
            {
                "mutation": "update",
                "target": {"entity": "Account", "predicate": {"all": {}}},
                "assignments": [],
            },
            "non-empty list",
        ),
        (
            {
                "mutation": "update",
                "target": {"entity": "Account", "predicate": {"all": {}}},
                "assignments": [{"attr": "balance", "value": 0}],
            },
            "`Class.member` reference",
        ),
        (
            {
                "mutation": "updateUntil",
                "target": {"entity": "Position", "predicate": {"all": {}}},
                "assignments": [{"attr": "Position.value", "value": 0}],
                "businessFrom": _B1,
            },
            "MUST carry both",
        ),
    ],
)
def test_predicate_structural_rejections(doc: dict[str, Any], match: str) -> None:
    with pytest.raises(wi.WriteInstructionError, match=match):
        wi.deserialize(doc)


def test_predicate_rejects_a_malformed_embedded_operation() -> None:
    with pytest.raises(op_algebra.OperationError):
        wi.deserialize(
            {
                "mutation": "delete",
                "target": {"entity": "Account", "predicate": {"bogusNode": {}}},
            }
        )


# --------------------------------------------------------------------------- #
# Member-name honesty (metamodel-aware validation).                            #
# --------------------------------------------------------------------------- #
def test_member_name_honesty_accepts_declared_members() -> None:
    keyed = wi.deserialize(
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "owner": "Ada", "balance": 1.00}],
        }
    )
    wi.validate_instruction(keyed, _ACCOUNT)
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Account.balance", "value": 0.00}],
        }
    )
    wi.validate_instruction(predicate, _ACCOUNT)


def test_member_name_honesty_rejects_undeclared_row_member() -> None:
    keyed = wi.deserialize(
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "nonsense": 1}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="undeclared member"):
        wi.validate_instruction(keyed, _ACCOUNT)


def test_member_name_honesty_rejects_foreign_assignment_owner() -> None:
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Balance.value", "value": 0.00}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="does not name a declared member"):
        wi.validate_instruction(predicate, _ACCOUNT)


def test_member_name_honesty_rejects_unknown_entity() -> None:
    keyed = wi.deserialize({"mutation": "delete", "entity": "Ghost", "rows": [{"id": 1}]})
    with pytest.raises(wi.WriteInstructionError, match="unknown entity"):
        wi.validate_instruction(keyed, _ACCOUNT)


def test_member_name_honesty_covers_value_object_members() -> None:
    # A top-level value-object name is a legal write-row key (m-value-object); the
    # honesty check accepts it alongside scalar attributes.
    customer = _MODELS["customer"]
    keyed = wi.deserialize(
        {
            "mutation": "insert",
            "entity": "Customer",
            "rows": [{"id": 9, "name": "Ada", "address": {"city": "Berlin"}}],
        }
    )
    wi.validate_instruction(keyed, customer)
