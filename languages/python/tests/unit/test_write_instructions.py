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
_PAYMENT = _MODELS["payment"]
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
            {
                "mutation": "terminate",
                "target": {"entity": "Balance", "predicate": {"all": {}}},
                "assignments": [{"attr": "Balance.value", "value": 0}],
            },
            "MUST NOT carry `assignments`",
        ),
        (
            {
                "mutation": "terminateUntil",
                "target": {"entity": "Position", "predicate": {"all": {}}},
                "assignments": [{"attr": "Position.value", "value": 0}],
                "businessFrom": _B1,
                "businessTo": _B2,
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


def test_member_name_honesty_accepts_a_family_participants_inherited_members() -> None:
    # A concrete-subtype keyed write naming a ROOT-declared inherited member
    # (`id` / `amount`, Payment's own) alongside its OWN declared member
    # (`cardNetwork`) is well-formed (m-inheritance "Inherited members") — the
    # ancestry-effective member set, not CardPayment's bare local declarations
    # (`family_attributes`), decides honesty (COR-3 Phase 8 increment 3).
    keyed = wi.deserialize(
        {
            "mutation": "insert",
            "entity": "CardPayment",
            "rows": [{"id": 1, "amount": 200.00, "cardNetwork": "Visa"}],
        }
    )
    wi.validate_instruction(keyed, _PAYMENT)


def test_member_name_honesty_still_rejects_a_genuinely_undeclared_family_member() -> None:
    keyed = wi.deserialize(
        {
            "mutation": "insert",
            "entity": "CardPayment",
            "rows": [{"id": 1, "amount": 200.00, "nonsense": True}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="undeclared member"):
        wi.validate_instruction(keyed, _PAYMENT)


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


def test_member_name_honesty_rejects_a_duplicate_assignment() -> None:
    # COR-3 Phase 8 increment 5 (python.md §5 "each field may be assigned at
    # most once"): the SAME member assigned twice raises, even though each
    # individual assignment is otherwise well-formed.
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [
                {"attr": "Account.balance", "value": 1.00},
                {"attr": "Account.balance", "value": 2.00},
            ],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="is duplicated"):
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


# --------------------------------------------------------------------------- #
# Finding 3 — the engine/serialized-path half of the shared assignment check   #
# (`python.md:667-676`; `m-case-format.md:700`): a CASE-AUTHORED PredicateWrite #
# assignment naming a primary-key or framework-owned (version) column, or       #
# carrying an ill-typed scalar value, is rejected with the SAME classification  #
# `entity.expressions.AttributeExpr.set` raises at build time for the typed     #
# path (`test_where_verbs.py`'s own `test_set_on_a_primary_key_attribute_       #
# raises` / `..._framework_owned_version_attribute_raises` / `..._a_mismatched_ #
# type_raises`) — the "one validator, two callers" pattern.                     #
# --------------------------------------------------------------------------- #
def test_member_name_honesty_rejects_a_primary_key_assignment() -> None:
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Account.id", "value": 2}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="primary-key fields may not be assigned"):
        wi.validate_instruction(predicate, _ACCOUNT)


def test_member_name_honesty_rejects_a_framework_owned_version_assignment() -> None:
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Account.version", "value": 5}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="framework-owned fields"):
        wi.validate_instruction(predicate, _ACCOUNT)


def test_member_name_honesty_rejects_a_scalar_type_mismatched_assignment() -> None:
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Account.owner", "value": 42}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="does not match the declared type"):
        wi.validate_instruction(predicate, _ACCOUNT)


# --------------------------------------------------------------------------- #
# Confirmation-pass residual P3 -- a VALUE-OBJECT-targeted assignment's VALUE   #
# is validated against its declared composite too (the prior round's check     #
# validated only scalar targets, silently accepting `Customer.address.set(42)` #
# and the equivalent case-authored form): a non-document value is rejected     #
# with the SAME wording style the scalar branch uses; a well-formed document   #
# stays structurally accepted (D-26 -- a value-object target is not itself     #
# rejected). `test_where_verbs.py`'s own `test_set_on_a_...` pins are the      #
# typed-path half of this SAME shared check.                                   #
# --------------------------------------------------------------------------- #
def test_member_name_honesty_rejects_a_non_document_value_object_assignment() -> None:
    customer = _MODELS["customer"]
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Customer", "predicate": {"all": {}}},
            "assignments": [{"attr": "Customer.address", "value": 42}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="does not match the declared type"):
        wi.validate_instruction(predicate, customer)


def test_member_name_honesty_accepts_a_well_formed_value_object_assignment() -> None:
    customer = _MODELS["customer"]
    document: dict[str, object] = {
        "street": "1 Aurora Ave",
        "city": "Oslo",
        "geo": None,
        "phones": [],
    }
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Customer", "predicate": {"all": {}}},
            "assignments": [{"attr": "Customer.address", "value": document}],
        }
    )
    wi.validate_instruction(predicate, customer)  # must not raise


# --------------------------------------------------------------------------- #
# Confirmation-pass residual B (round 2, `inheritance/__init__.py:667`): a     #
# `None` assignment's nullability-aware handling through the SERIALIZED/       #
# case-authored path -- `test_where_verbs.py`'s own `test_set_on_a_..._with_  #
# none_...` pins are the typed-path half of this SAME shared check.           #
# --------------------------------------------------------------------------- #
def test_member_name_honesty_rejects_a_non_nullable_value_object_assignment_of_none() -> None:
    # `models/shipment.yaml`'s `destination` is `nullable: false` (the corpus's
    # own "required top-level value object missing" exemplar) -- before the
    # fix, `if value is not None:` skipped validation entirely for a `None`
    # assignment, regardless of nullability.
    shipment = _MODELS["shipment"]
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Shipment", "predicate": {"all": {}}},
            "assignments": [{"attr": "Shipment.destination", "value": None}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="required value object is absent"):
        wi.validate_instruction(predicate, shipment)


def test_member_name_honesty_accepts_a_nullable_value_object_assignment_of_none() -> None:
    # `Customer.address` is `nullable: true` -- an explicit `None` stays a
    # legal clearing assignment.
    customer = _MODELS["customer"]
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Customer", "predicate": {"all": {}}},
            "assignments": [{"attr": "Customer.address", "value": None}],
        }
    )
    wi.validate_instruction(predicate, customer)  # must not raise


def test_member_name_honesty_rejects_a_non_nullable_scalar_assignment_of_none() -> None:
    # The scalar branch's own extension of residual B: `Shipment.name`
    # declares no `nullable: true` -- an explicit `None` assignment must be
    # refused too, the SAME class of bug as the value-object branch.
    shipment = _MODELS["shipment"]
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Shipment", "predicate": {"all": {}}},
            "assignments": [{"attr": "Shipment.name", "value": None}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="required attribute is absent"):
        wi.validate_instruction(predicate, shipment)
