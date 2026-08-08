"""Write-instruction IR + serde unit tests (m-unit-work, Docker-free).

Proves the canonical write-instruction serde round-trip contract
(``serialize(deserialize(x)) == x``) over every instruction shape — keyed and
predicate-selected, non-temporal / audit-only / bitemporal bounded and unbounded
— cross-checked against ``core/schemas/write-instruction.schema.json`` itself, plus
the structural rejection branches (the axis-explicit Valid-Time-bound pairing, the
forbidden observation control keys, the smuggled Transaction-Time alias `at`),
and the metamodel-aware member-name honesty validator.
"""

from __future__ import annotations

import json
from typing import Any, cast

import jsonschema
import pytest
from referencing import Registry, Resource

from _support.repo import REPO_ROOT
from parallax.conformance import models
from parallax.core import inheritance, op_algebra
from parallax.core.unit_work import instructions as wi

_SCHEMAS = REPO_ROOT / "core" / "schemas"


def _schema(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((_SCHEMAS / name).read_text()))


_SCHEMA = _schema("write-instruction.schema.json")
# The write-instruction schema references the shared Entity-identity grammars
# across files, so a validator needs an `$id`-keyed registry to reach them.
_REGISTRY: Registry[Any] = Registry[Any]().with_resources(
    (schema["$id"], Resource[Any].from_contents(schema))
    for schema in (_SCHEMA, _schema("identity.schema.json"))
)


def _validate(doc: object, schema: dict[str, Any]) -> None:
    validator = cast("Any", jsonschema.Draft202012Validator(schema, registry=_REGISTRY))
    validator.validate(doc)


_MODELS = models.load_models()
_ACCOUNT = models.accepted_model(_MODELS["account"])
_PAYMENT = models.accepted_model(_MODELS["payment"])
_BALANCE = models.accepted_model(_MODELS["balance"])
_POSITION = models.accepted_model(_MODELS["position"])

_B1 = "2024-01-01T00:00:00+00:00"
_B2 = "2024-06-01T00:00:00+00:00"

# Every canonical instruction shape, authored in the axis-explicit spelling with no
# Transaction-Time instant (Clock context) — the coalescing witnesses' target buffered
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
            "validFrom": _B1,
        },
    ),
    (
        "keyed-insertUntil-bitemporal-bounded",
        {
            "mutation": "insertUntil",
            "entity": "Position",
            "rows": [{"id": 9, "acctNum": "D", "value": 100.00}],
            "validFrom": _B1,
            "until": _B2,
        },
    ),
    (
        "keyed-updateUntil-bitemporal-bounded",
        {
            "mutation": "updateUntil",
            "entity": "Position",
            "rows": [{"id": 9, "value": 150.00}],
            "validFrom": _B1,
            "until": _B2,
        },
    ),
    (
        "keyed-terminateUntil-bitemporal-bounded",
        {
            "mutation": "terminateUntil",
            "entity": "Position",
            "rows": [{"id": 9}],
            "validFrom": _B1,
            "until": _B2,
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
            "validFrom": _B1,
        },
    ),
    (
        "predicate-updateUntil-bitemporal-bounded",
        {
            "mutation": "updateUntil",
            "target": {"entity": "Position", "predicate": {"all": {}}},
            "assignments": [{"attr": "Position.value", "value": 150.00}],
            "validFrom": _B1,
            "until": _B2,
        },
    ),
    (
        "predicate-terminateUntil-bitemporal-bounded",
        {
            "mutation": "terminateUntil",
            "target": {"entity": "Position", "predicate": {"all": {}}},
            "validFrom": _B1,
            "until": _B2,
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
        valid_from=_B1,
        until=_B2,
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
def test_transaction_time_alias_is_rejected() -> None:
    # `at` is the corpus's Clock-context alias; it is NOT a canonical instruction
    # field, so no caller-facing shape can smuggle a Transaction-Time instant in (ADR 0010).
    with pytest.raises(wi.WriteInstructionError, match="unexpected key"):
        wi.deserialize(
            {
                "mutation": "insert",
                "entity": "Balance",
                "rows": [{"id": 9, "value": 100.00}],
                "at": _B2,
            }
        )


@pytest.mark.parametrize("forbidden", ["observedVersion", "observedTxStart", "observedValidStart"])
def test_forbidden_observation_control_key_is_rejected(forbidden: str) -> None:
    # The transaction observation is attached per row at flush, never authored on
    # the durable instruction (ADR 0013). All THREE keys `write-instruction.schema.json`
    # forbids on a durable row are refused here, including BOTH halves of the observed
    # milestone's own edge coordinate — an accepted `observedValidStart` would let the
    # canonical parser's language contradict the neutral schema and silently retain a
    # control field the instruction cannot mean.
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
            {"mutation": "insert", "entity": "Account", "rows": [{"id": 1}], "until": _B2},
            "MUST NOT carry `until`",
        ),
        (
            {
                "mutation": "insertUntil",
                "entity": "Position",
                "rows": [{"id": 1}],
                "validFrom": _B1,
            },
            "MUST carry both",
        ),
        (
            {"mutation": "insert", "entity": "Account", "rows": [{"id": 1}], "validFrom": ""},
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
                "validFrom": _B1,
                "until": _B2,
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
                "validFrom": _B1,
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
            "assignments": [{"attr": "Account.balance", "value": 0}],
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
    # (`family_attributes`), decides validity.
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
    # `python.md` §5 requires each field to be assigned at most once. The same
    # member assigned twice raises even though each
    # individual assignment is otherwise well-formed.
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [
                {"attr": "Account.balance", "value": 1},
                {"attr": "Account.balance", "value": 2},
            ],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="is duplicated"):
        wi.validate_instruction(predicate, _ACCOUNT)


def test_member_name_honesty_rejects_unknown_entity() -> None:
    keyed = wi.deserialize({"mutation": "delete", "entity": "Ghost", "rows": [{"id": 1}]})
    with pytest.raises(wi.WriteInstructionError, match="unknown entity"):
        wi.validate_instruction(keyed, _ACCOUNT)


# --------------------------------------------------------------------------- #
# Target/mutation applicability (m-case-format "requires only the temporal      #
# coordinates the target profile uses").                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "instruction",
    [
        {
            "mutation": "updateUntil",
            "entity": "Account",
            "rows": [{"id": 1, "balance": 5.00}],
            "validFrom": _B1,
            "until": _B2,
        },
        {"mutation": "terminate", "entity": "Account", "rows": [{"id": 1}]},
        {
            "mutation": "updateUntil",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Account.balance", "value": 0}],
            "validFrom": _B1,
            "until": _B2,
        },
        {
            "mutation": "terminateUntil",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "validFrom": _B1,
            "until": _B2,
        },
    ],
    ids=[
        "keyed-updateUntil",
        "keyed-terminate",
        "predicate-updateUntil",
        "predicate-terminateUntil",
    ],
)
def test_a_milestone_verb_is_rejected_on_a_non_temporal_target(
    instruction: dict[str, Any],
) -> None:
    # `Account` is versioned and non-temporal, so it has no milestone for a
    # bounded or closing verb to address. The validator owns this because it is
    # the one model-aware gate every ingress crosses: a predicate-selected
    # milestone verb reaching the buffering seam instead resolves against a real
    # connection first, and settles as an ordinary versioned write that consumes
    # the row's version while dropping the bounds the caller wrote.
    with pytest.raises(wi.WriteInstructionError, match="temporal milestone verb"):
        wi.validate_instruction(wi.deserialize(instruction), _ACCOUNT)


@pytest.mark.parametrize(
    "instruction",
    [
        {
            "mutation": "updateUntil",
            "entity": "Position",
            "rows": [{"id": 1, "value": 5.00}],
            "validFrom": _B1,
            "until": _B2,
        },
        {"mutation": "terminate", "entity": "Balance", "rows": [{"id": 1}]},
    ],
    ids=["bitemporal-updateUntil", "audit-only-terminate"],
)
def test_a_milestone_verb_is_accepted_on_a_temporal_target(instruction: dict[str, Any]) -> None:
    model = _POSITION if instruction["entity"] == "Position" else _BALANCE
    wi.validate_instruction(wi.deserialize(instruction), model)


def test_a_plural_keyed_instruction_is_rejected_on_a_temporal_target() -> None:
    # The converse half of the target-profile quadrant above. Each row of a
    # milestone chain closes its own milestone, consumes its own observation, and
    # opens its own successors, so several rows under one instruction denote
    # several chains rather than one wider write (m-unit-work). The refusal
    # carries a `rule`, since the corpus grades it as a named pre-SQL rejection.
    plural = wi.deserialize(
        {
            "mutation": "update",
            "entity": "Position",
            "rows": [{"id": 1, "value": 5.00}, {"id": 2, "value": 6.00}],
            "validFrom": _B1,
        }
    )
    with pytest.raises(wi.InstructionRejectedError, match="carries 2 rows") as exc:
        wi.validate_instruction(plural, _POSITION)
    assert exc.value.rule == wi.TEMPORAL_KEYED_WRITE_MULTI_ROW
    assert isinstance(exc.value, wi.WriteInstructionError)


def test_a_plural_keyed_instruction_is_accepted_on_a_non_temporal_target() -> None:
    # The contrast that makes the rule the TARGET's: the same plural shape on a
    # versioned non-temporal entity is the set-based flush batching collapses.
    plural = wi.deserialize(
        {
            "mutation": "update",
            "entity": "Account",
            "rows": [{"id": 1, "balance": 5.00}, {"id": 2, "balance": 6.00}],
        }
    )
    wi.validate_instruction(plural, _ACCOUNT)


def test_a_milestone_verb_is_accepted_on_a_temporal_family_descendant() -> None:
    # Temporality is family-level metadata only the root declares
    # (`m-inheritance`), so a descendant whose OWN accepted Metadata carries no
    # axis still admits every milestone verb its family derives one for.
    rate = models.accepted_model(_MODELS["rate"])
    keyed = wi.deserialize(
        {
            "mutation": "terminate",
            "entity": "DepositRate",
            "rows": [{"id": 1}],
            "validFrom": _B1,
        }
    )
    wi.validate_instruction(keyed, rate)


def test_member_name_honesty_covers_value_object_members() -> None:
    # A top-level value-object name is a legal write-row key (m-value-object); the
    # honesty check accepts it alongside scalar attributes.
    customer = models.accepted_model(_MODELS["customer"])
    keyed = wi.deserialize(
        {
            "mutation": "insert",
            "entity": "Customer",
            "rows": [{"id": 9, "name": "Ada", "address": {"city": "Berlin"}}],
        }
    )
    wi.validate_instruction(keyed, customer)


# --------------------------------------------------------------------------- #
# The engine/serialized-path half of the shared assignment check               #
# (`python.md:667-676`; `m-case-format.md:700`): a CASE-AUTHORED PredicateWrite #
# assignment naming a primary-key or framework-owned (version) column, or       #
# carrying an ill-typed scalar value, is rejected with the SAME classification  #
# `entity.expressions.AttributeExpr.set` raises at build time for the typed     #
# path (`test_where_verbs.py`'s own `test_set_on_a_primary_key_attribute_       #
# raises` / `..._framework_owned_version_attribute_raises` / `..._a_mismatched_ #
# type_raises`) and for the edited copy (`test_model_free_authoring.py`'s own    #
# three-surface parity block) — one validator, three callers.                    #
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
# A value-object assignment validates its value against the declared composite #
# just as scalar assignments validate their values. A non-document value is    #
# rejected with the scalar branch's wording, while a well-formed document is   #
# accepted. `test_where_verbs.py` covers the typed-path half of this check.     #
# --------------------------------------------------------------------------- #
def test_member_name_honesty_rejects_a_non_document_value_object_assignment() -> None:
    customer = models.accepted_model(_MODELS["customer"])
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
    customer = models.accepted_model(_MODELS["customer"])
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
# A `None` assignment observes nullability through the serialized, case-authored #
# path (`inheritance/__init__.py`). `test_where_verbs.py` covers the typed path. #
# --------------------------------------------------------------------------- #
def test_member_name_honesty_rejects_a_non_nullable_value_object_assignment_of_none() -> None:
    # `models/shipment.yaml`'s `destination` is `nullable: false` (the corpus's
    # "required top-level value object missing" exemplar), so a `None`
    # assignment is invalid.
    shipment = models.accepted_model(_MODELS["shipment"])
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
    customer = models.accepted_model(_MODELS["customer"])
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Customer", "predicate": {"all": {}}},
            "assignments": [{"attr": "Customer.address", "value": None}],
        }
    )
    wi.validate_instruction(predicate, customer)  # must not raise


# --------------------------------------------------------------------------- #
# The selecting predicate is measured with the WHOLE `validate_operation`      #
# vocabulary, not just the rules the instruction schema states — and here,     #
# because this is the ONE model-aware gate every predicate-write ingress runs  #
# (`m-case-format` "The model-aware validator validates the predicate ...,     #
# checks entity scope and bare-predicate rules"). The two cases below come     #
# from different rule families so the pin covers the vocabulary rather than    #
# one rule.                                                                    #
# --------------------------------------------------------------------------- #
def test_a_predicate_writes_inverted_between_window_is_rejected() -> None:
    predicate = wi.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": "Account",
                "predicate": {"between": {"attr": "Account.id", "lower": 10, "upper": 1}},
            },
        }
    )
    with pytest.raises(op_algebra.OperationRejectedError) as caught:
        wi.validate_instruction(predicate, _ACCOUNT)
    assert caught.value.rule == "between-bounds-inverted"


def test_a_predicate_writes_out_of_position_attribute_reference_is_rejected() -> None:
    orders = models.accepted_model(_MODELS["orders"])
    predicate = wi.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": "Order",
                "predicate": {"eq": {"attr": "OrderItem.sku", "value": "X"}},
            },
        }
    )
    with pytest.raises(op_algebra.OperationRejectedError) as caught:
        wi.validate_instruction(predicate, orders)
    assert caught.value.rule == "attribute-outside-active-position"


def test_a_predicate_writes_scope_is_judged_before_its_assignments() -> None:
    # `m-case-format` orders the model-aware validator: predicate and entity
    # scope first, then the assignment rules. An instruction that fails BOTH
    # must report the predicate, so the caller is not sent to fix an assignment
    # while the selection itself can match nothing.
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {
                "entity": "Account",
                "predicate": {"between": {"attr": "Account.id", "lower": 10, "upper": 1}},
            },
            "assignments": [{"attr": "Account.id", "value": 2}],
        }
    )
    with pytest.raises(op_algebra.OperationRejectedError) as caught:
        wi.validate_instruction(predicate, _ACCOUNT)
    assert caught.value.rule == "between-bounds-inverted"


# --------------------------------------------------------------------------- #
# The bare-predicate rule (`m-case-format` `target.predicate`: "one schema-valid #
# `m-op-algebra` operation; it is a bare write predicate, never a result         #
# modifier"; `python.md` §5: "`order_by`, `limit`, `include`, `as_of`,           #
# `history` / `as_of_range`, and `narrow` are all rejected on any write          #
# target"). Every one of these is a VALID READ operation, so                     #
# `validate_operation` — which the read path shares — cannot carry the rule;     #
# it is a rule of the write instruction and has its own refusal.                 #
# --------------------------------------------------------------------------- #
_BARE_INNER: dict[str, Any] = {"lessThan": {"attr": "Account.balance", "value": 200.00}}
_NON_BARE_PREDICATES: list[tuple[str, dict[str, Any]]] = [
    ("orderBy", {"orderBy": {"operand": _BARE_INNER, "keys": [{"attr": "Account.balance"}]}}),
    ("limit", {"limit": {"operand": _BARE_INNER, "count": 5}}),
    ("distinct", {"distinct": {"operand": _BARE_INNER}}),
    ("asOf", {"asOf": {"operand": _BARE_INNER, "dimension": "valid-time", "coordinate": _B1}}),
    (
        "asOfRange",
        {
            "asOfRange": {
                "operand": _BARE_INNER,
                "dimension": "valid-time",
                "start": _B1,
                "end": _B2,
            }
        },
    ),
    ("history", {"history": {"operand": _BARE_INNER, "dimension": "valid-time"}}),
]


@pytest.mark.parametrize(
    ("wrapper", "predicate"), _NON_BARE_PREDICATES, ids=[w for w, _p in _NON_BARE_PREDICATES]
)
def test_a_result_modifier_is_never_a_bare_write_predicate(
    wrapper: str, predicate: dict[str, Any]
) -> None:
    instruction = wi.deserialize(
        {"mutation": "delete", "target": {"entity": "Account", "predicate": predicate}}
    )
    with pytest.raises(wi.WriteInstructionError, match=f"`{wrapper}` is a result modifier"):
        wi.validate_instruction(instruction, _ACCOUNT)


@pytest.mark.parametrize(
    ("position", "predicate"),
    [
        (
            "and",
            {"and": {"operands": [{"limit": {"operand": _BARE_INNER, "count": 5}}, _BARE_INNER]}},
        ),
        (
            "or",
            {"or": {"operands": [_BARE_INNER, {"limit": {"operand": _BARE_INNER, "count": 5}}]}},
        ),
        ("not", {"not": {"operand": {"limit": {"operand": _BARE_INNER, "count": 5}}}}),
        ("group", {"group": {"operand": {"limit": {"operand": _BARE_INNER, "count": 5}}}}),
    ],
    ids=["and", "or", "not", "group"],
)
def test_a_result_modifier_hidden_in_the_boolean_spine_is_rejected(
    position: str, predicate: dict[str, Any]
) -> None:
    # `and(limit(...), ...)` round-trips through the algebra's serde, and a
    # nested directive lowers exactly as a root one does, so the rule is checked
    # at every position rather than only at the root.
    assert position in predicate
    instruction = wi.deserialize(
        {"mutation": "delete", "target": {"entity": "Account", "predicate": predicate}}
    )
    with pytest.raises(wi.WriteInstructionError, match="`limit` is a result modifier"):
        wi.validate_instruction(instruction, _ACCOUNT)


@pytest.mark.parametrize(
    ("position", "predicate"),
    [
        (
            "navigate",
            {
                "navigate": {
                    "rel": "Order.items",
                    "op": {"limit": {"operand": {"eq": {"attr": "OrderItem.sku", "value": "X"}}}},
                }
            },
        ),
        (
            "exists",
            {
                "exists": {
                    "rel": "Order.items",
                    "op": {"limit": {"operand": {"eq": {"attr": "OrderItem.sku", "value": "X"}}}},
                }
            },
        ),
        (
            "notExists",
            {
                "notExists": {
                    "rel": "Order.items",
                    "op": {"limit": {"operand": {"eq": {"attr": "OrderItem.sku", "value": "X"}}}},
                }
            },
        ),
    ],
    ids=["navigate", "exists", "not-exists"],
)
def test_a_result_modifier_inside_a_navigation_filter_is_rejected(
    position: str, predicate: dict[str, Any]
) -> None:
    assert position in predicate
    orders = models.accepted_model(_MODELS["orders"])
    body = cast("dict[str, Any]", predicate[position])
    body["op"]["limit"]["count"] = 5
    instruction = wi.deserialize(
        {"mutation": "delete", "target": {"entity": "Order", "predicate": predicate}}
    )
    with pytest.raises(wi.WriteInstructionError, match="`limit` is a result modifier"):
        wi.validate_instruction(instruction, orders)


@pytest.mark.parametrize(
    ("position", "predicate"),
    [
        ("exists", {"exists": {"rel": "Order.items"}}),
        ("notExists", {"notExists": {"rel": "Order.items"}}),
    ],
    ids=["exists", "not-exists"],
)
def test_a_bare_navigation_filter_carrying_no_inner_operation_is_accepted(
    position: str, predicate: dict[str, Any]
) -> None:
    # The optional inner `op` is absent — the recursion has nothing to descend
    # into and the predicate stays bare.
    assert position in predicate
    orders = models.accepted_model(_MODELS["orders"])
    instruction = wi.deserialize(
        {"mutation": "delete", "target": {"entity": "Order", "predicate": predicate}}
    )
    wi.validate_instruction(instruction, orders)  # must not raise


# A `narrow` is the one entry of `python.md` §5's enumeration whose meaning is
# POSITIONAL. `m-op-algebra` draws the line: a top-level narrow is "the node a
# whole-result narrowing produces" — the `.narrow()` clause on the write target
# — while "a `narrow` appearing as a predicate term inside a boolean combinator
# is a filter" over the unchanged position, as is one inside a navigation
# filter's `op`, where it narrows the relationship target the hop reaches. The
# refused half first.
def test_a_whole_result_narrow_is_never_a_bare_write_predicate() -> None:
    # The narrow wraps the WHOLE predicate, which is the result position: it is
    # refused BEFORE the inheritance-family rejection this target would also
    # earn.
    instruction = wi.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": "CardPayment",
                "predicate": {
                    "narrow": {
                        "entity": "Payment",
                        "to": ["CardPayment"],
                        "operand": {"eq": {"attr": "Payment.id", "value": 1}},
                    }
                },
            },
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="whole-result narrowing"):
        wi.validate_instruction(instruction, _PAYMENT)


_ANIMAL = models.accepted_model(_MODELS["animal"])
# `Person` owns the polymorphic `animals` (-> the abstract root `Animal`) and is
# itself a plain non-family, non-temporal, unversioned entity — so a predicate
# write on it is legal and the narrow inside its navigation filter is the only
# thing under test.
_ANIMAL_TO_DOG_NARROW: dict[str, Any] = {
    "narrow": {"entity": "Animal", "to": ["Dog"], "operand": {"all": {}}}
}


@pytest.mark.parametrize(
    ("position", "predicate"),
    [
        ("exists", {"exists": {"rel": "Person.animals", "op": _ANIMAL_TO_DOG_NARROW}}),
        ("notExists", {"notExists": {"rel": "Person.animals", "op": _ANIMAL_TO_DOG_NARROW}}),
        ("navigate", {"navigate": {"rel": "Person.animals", "op": _ANIMAL_TO_DOG_NARROW}}),
        (
            "and",
            {
                "and": {
                    "operands": [
                        {"eq": {"attr": "Person.name", "value": "Ada"}},
                        {"exists": {"rel": "Person.animals", "op": _ANIMAL_TO_DOG_NARROW}},
                    ]
                }
            },
        ),
        (
            "or",
            {
                "or": {
                    "operands": [
                        {"eq": {"attr": "Person.name", "value": "Ada"}},
                        {"exists": {"rel": "Person.animals", "op": _ANIMAL_TO_DOG_NARROW}},
                    ]
                }
            },
        ),
        (
            "not",
            {
                "not": {
                    "operand": {"exists": {"rel": "Person.animals", "op": _ANIMAL_TO_DOG_NARROW}}
                }
            },
        ),
        (
            "group",
            {
                "group": {
                    "operand": {"exists": {"rel": "Person.animals", "op": _ANIMAL_TO_DOG_NARROW}}
                }
            },
        ),
    ],
    ids=["exists", "not-exists", "navigate", "and", "or", "not", "group"],
)
def test_a_predicate_scoped_narrow_is_a_filter_and_is_accepted(
    position: str, predicate: dict[str, Any]
) -> None:
    assert position in predicate
    instruction = wi.deserialize(
        {"mutation": "delete", "target": {"entity": "Person", "predicate": predicate}}
    )
    op_algebra.validate_operation(
        next(e for e in _ANIMAL.entities if e.identity.name == "Person"),
        cast("wi.PredicateWrite", instruction).target.predicate,
        _ANIMAL,
    )
    wi.validate_instruction(instruction, _ANIMAL)  # must not raise


def test_a_result_modifier_inside_a_predicate_scoped_narrow_is_still_rejected() -> None:
    # Admitting the narrow does not admit what it wraps: the recursion descends
    # through a filter narrow's own operand exactly as it does a boolean one's.
    instruction = wi.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": "Person",
                "predicate": {
                    "exists": {
                        "rel": "Person.animals",
                        "op": {
                            "narrow": {
                                "entity": "Animal",
                                "to": ["Dog"],
                                "operand": {"limit": {"operand": {"all": {}}, "count": 5}},
                            }
                        },
                    }
                },
            },
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="`limit` is a result modifier"):
        wi.validate_instruction(instruction, _ANIMAL)


def test_a_deep_fetch_is_never_a_bare_write_predicate() -> None:
    orders = models.accepted_model(_MODELS["orders"])
    instruction = wi.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": "Order",
                "predicate": {
                    "deepFetch": {
                        "operand": {"eq": {"attr": "Order.id", "value": 1}},
                        "paths": [{"segments": [{"rel": "Order.items"}]}],
                    }
                },
            },
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="`deepFetch` is a result modifier"):
        wi.validate_instruction(instruction, orders)


# --------------------------------------------------------------------------- #
# The inheritance-family rejection is stated HERE, in the one model-aware       #
# validator both predicate-write ingresses call, so the typed `_where` verbs    #
# and the conformance engine classify one instruction identically. Its position #
# is fixed from both sides: AFTER the predicate rules `m-case-format` orders    #
# first, and BEFORE the assignments, which `python.md` §5 requires — "every     #
# assigned attribute or value-object member must be declared by the exact       #
# target entity — set-based writes already reject inheritance-family targets,   #
# so ancestry resolution never arises."                                         #
# --------------------------------------------------------------------------- #
def test_a_predicate_write_on_an_inheritance_family_target_is_rejected() -> None:
    instruction = wi.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": "CardPayment",
                "predicate": {"eq": {"attr": "CardPayment.id", "value": 1}},
            },
        }
    )
    with pytest.raises(inheritance.InheritanceError) as caught:
        wi.validate_instruction(instruction, _PAYMENT)
    assert caught.value.rule == "subtype-write-set-based-unsupported"


def test_an_invalid_predicate_outranks_the_inheritance_family_rejection() -> None:
    instruction = wi.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": "CardPayment",
                "predicate": {"between": {"attr": "CardPayment.id", "lower": 10, "upper": 1}},
            },
        }
    )
    with pytest.raises(op_algebra.OperationRejectedError) as caught:
        wi.validate_instruction(instruction, _PAYMENT)
    assert caught.value.rule == "between-bounds-inverted"


def test_the_inheritance_family_rejection_outranks_the_assignment_rules() -> None:
    # The assignment names the DECLARING root (`Payment.amount`) while the
    # target names the concrete subtype, which the exact-target assignment rule
    # refuses. The family rejection must come first, or the caller is told to
    # fix an assignment on a write that is unsupported whatever it assigns.
    instruction = wi.deserialize(
        {
            "mutation": "update",
            "target": {
                "entity": "CardPayment",
                "predicate": {"eq": {"attr": "CardPayment.id", "value": 1}},
            },
            "assignments": [{"attr": "Payment.amount", "value": 1.00}],
        }
    )
    with pytest.raises(inheritance.InheritanceError) as caught:
        wi.validate_instruction(instruction, _PAYMENT)
    assert caught.value.rule == "subtype-write-set-based-unsupported"


def test_member_name_honesty_rejects_a_non_nullable_scalar_assignment_of_none() -> None:
    # `Shipment.name` declares no `nullable: true`, so an explicit `None`
    # assignment is refused just as it is for a required value object.
    shipment = models.accepted_model(_MODELS["shipment"])
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Shipment", "predicate": {"all": {}}},
            "assignments": [{"attr": "Shipment.name", "value": None}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="required attribute is absent"):
        wi.validate_instruction(predicate, shipment)
