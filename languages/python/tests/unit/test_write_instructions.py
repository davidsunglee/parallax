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
from collections.abc import Mapping
from typing import Any, cast

import jsonschema
import pytest
from referencing import Registry, Resource

from _support.repo import REPO_ROOT
from parallax.conformance import models
from parallax.core import inheritance
from parallax.core import predicate as predicate_algebra
from parallax.core.unit_work import instructions as wi

_SCHEMAS = REPO_ROOT / "core" / "schemas"


def _schema(name: str) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((_SCHEMAS / name).read_text()))


_SCHEMA = _schema("write-instruction.schema.json")
# The write-instruction schema references the shared Entity-identity grammars and
# the Predicate a set-based write selects with across files, so a validator needs
# an `$id`-keyed registry to reach them.
_REGISTRY: Registry[Any] = Registry[Any]().with_resources(
    (schema["$id"], Resource[Any].from_contents(schema))
    for schema in (
        _SCHEMA,
        _schema("identity.schema.json"),
        _schema("predicate.schema.json"),
    )
)


def _validate(doc: object, schema: dict[str, Any]) -> None:
    validator = cast("Any", jsonschema.Draft202012Validator(schema, registry=_REGISTRY))
    validator.validate(doc)


_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_PAYMENT = _MODELS["payment"]
_BALANCE = _MODELS["balance"]
_POSITION = _MODELS["position"]
# Two Entities sharing one local name across namespaces — the corpus model the
# ambiguity rule is authored against (`m-predicate-048` / `-051`).
_SHARED_LOCAL_NAME = _MODELS["shared-local-name"]

_B1 = "2024-01-01T00:00:00.000000Z"
_B2 = "2024-06-01T00:00:00.000000Z"

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
            "rows": [{"id": {"computed": "maxPlusOne"}, "owner": "Ada", "balance": 1}],
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
    # the m-predicate serde contract), matching the schema-validated document.
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


def test_predicate_carries_a_canonical_predicate_node() -> None:
    instruction = wi.deserialize(
        {"mutation": "delete", "target": {"entity": "Account", "predicate": {"all": {}}}}
    )
    assert isinstance(instruction, wi.PredicateWrite)
    assert instruction.target.predicate == predicate_algebra.All()


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


def test_predicate_rejects_a_malformed_embedded_predicate() -> None:
    with pytest.raises(predicate_algebra.CanonicalDocumentError):
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
            "rows": [{"id": 9, "owner": "Ada", "balance": 1}],
        }
    )
    wi.prepare_typed_write(keyed, _ACCOUNT)
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Account.balance", "value": 0}],
        }
    )
    wi.prepare_typed_write(predicate, _ACCOUNT)


@pytest.mark.parametrize(
    ("member", "value"),
    [("price", "1.00"), ("orderedOn", "2024-07-01")],
)
def test_typed_preparation_does_not_decode_wire_literals(member: str, value: str) -> None:
    instruction = wi.KeyedWrite("update", "Order", ({"id": 1, member: value},))
    with pytest.raises(ValueError, match="does not match the declared type"):
        wi.prepare_typed_write(instruction, _MODELS["orders"])
    wi.prepare_wire_write(instruction, _MODELS["orders"])


def test_preparation_owns_nested_values_once_and_derivation_retains_them() -> None:
    address = {"street": "Main", "city": "Berlin"}
    instruction = wi.KeyedWrite(
        "insert",
        "Customer",
        ({"id": 9, "name": "Ada", "address": address},),
    )
    prepared = wi.prepare_typed_write(instruction, _MODELS["customer"])
    assert isinstance(prepared, wi.PreparedKeyedWrite)
    retained = prepared.rows[0]["address"]
    address["city"] = "Oslo"
    assert cast("Mapping[str, object]", retained)["city"] == "Berlin"
    derived = wi.derive_keyed_write(prepared, prepared.rows)
    assert derived.rows[0] is prepared.rows[0]
    assert derived.rows[0]["address"] is retained


def test_member_name_honesty_rejects_undeclared_row_member() -> None:
    keyed = wi.deserialize(
        {
            "mutation": "insert",
            "entity": "Account",
            "rows": [{"id": 9, "nonsense": 1}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="undeclared member"):
        wi.prepare_typed_write(keyed, _ACCOUNT)


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
            "rows": [{"id": 1, "amount": 200, "cardNetwork": "Visa"}],
        }
    )
    wi.prepare_typed_write(keyed, _PAYMENT)


def test_member_name_honesty_still_rejects_a_genuinely_undeclared_family_member() -> None:
    keyed = wi.deserialize(
        {
            "mutation": "insert",
            "entity": "CardPayment",
            "rows": [{"id": 1, "amount": 200.00, "nonsense": True}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="undeclared member"):
        wi.prepare_typed_write(keyed, _PAYMENT)


def test_member_name_honesty_rejects_foreign_assignment_owner() -> None:
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Balance.value", "value": 0.00}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="does not name a declared member"):
        wi.prepare_typed_write(predicate, _ACCOUNT)


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
        wi.prepare_typed_write(predicate, _ACCOUNT)


def test_member_name_honesty_rejects_unknown_entity() -> None:
    keyed = wi.deserialize({"mutation": "delete", "entity": "Ghost", "rows": [{"id": 1}]})
    with pytest.raises(wi.WriteInstructionError, match="unknown entity"):
        wi.prepare_typed_write(keyed, _ACCOUNT)


def test_an_ambiguous_bare_spelling_is_classified_apart_from_an_unknown_one() -> None:
    # `entity_by_name` answers one miss for two different mistakes. The write
    # boundary every externally produced instruction crosses tells them apart:
    # a bare spelling two namespaces share names the normative rule and reports
    # the canonical spellings that would resolve, while a name the model does
    # not declare at all stays the plain well-formedness refusal.
    keyed = wi.deserialize({"mutation": "delete", "entity": "SharedVariant", "rows": [{"id": 1}]})
    with pytest.raises(wi.InstructionRejectedError) as excinfo:
        wi.prepare_typed_write(keyed, _SHARED_LOCAL_NAME)
    assert excinfo.value.rule == "reference-ambiguous-entity-name"
    assert "archive.SharedVariant" in str(excinfo.value)
    assert "catalog.SharedVariant" in str(excinfo.value)

    unknown = wi.deserialize({"mutation": "delete", "entity": "Ghost", "rows": [{"id": 1}]})
    with pytest.raises(wi.WriteInstructionError, match="unknown entity") as plain:
        wi.prepare_typed_write(unknown, _SHARED_LOCAL_NAME)
    assert not isinstance(plain.value, wi.InstructionRejectedError)


def test_a_canonical_spelling_resolves_where_the_bare_one_is_ambiguous() -> None:
    keyed = wi.deserialize(
        {"mutation": "delete", "entity": "archive.SharedVariant", "rows": [{"id": 1}]}
    )
    wi.prepare_typed_write(keyed, _SHARED_LOCAL_NAME)


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
        wi.prepare_typed_write(wi.deserialize(instruction), _ACCOUNT)


@pytest.mark.parametrize(
    "instruction",
    [
        {
            "mutation": "updateUntil",
            "entity": "Position",
            "rows": [{"id": 1, "value": 5}],
            "validFrom": _B1,
            "until": _B2,
        },
        {"mutation": "terminate", "entity": "Balance", "rows": [{"id": 1}]},
    ],
    ids=["bitemporal-updateUntil", "audit-only-terminate"],
)
def test_a_milestone_verb_is_accepted_on_a_temporal_target(instruction: dict[str, Any]) -> None:
    model = _POSITION if instruction["entity"] == "Position" else _BALANCE
    wi.prepare_typed_write(wi.deserialize(instruction), model)


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
            "rows": [{"id": 1, "value": 5}, {"id": 2, "value": 6.00}],
            "validFrom": _B1,
        }
    )
    with pytest.raises(wi.InstructionRejectedError, match="carries 2 rows") as exc:
        wi.prepare_typed_write(plural, _POSITION)
    assert exc.value.rule == wi.TEMPORAL_KEYED_WRITE_MULTI_ROW
    assert isinstance(exc.value, wi.WriteInstructionError)


def test_a_plural_keyed_instruction_is_accepted_on_a_non_temporal_target() -> None:
    # The contrast that makes the rule the TARGET's: the same plural shape on a
    # versioned non-temporal entity is the set-based flush batching collapses.
    plural = wi.deserialize(
        {
            "mutation": "update",
            "entity": "Account",
            "rows": [{"id": 1, "balance": 5}, {"id": 2, "balance": 6}],
        }
    )
    wi.prepare_typed_write(plural, _ACCOUNT)


def test_a_milestone_verb_is_accepted_on_a_temporal_family_descendant() -> None:
    # Temporality is family-level metadata only the root declares
    # (`m-inheritance`), so a descendant whose OWN accepted Metadata carries no
    # axis still admits every milestone verb its family derives one for.
    rate = _MODELS["rate"]
    keyed = wi.deserialize(
        {
            "mutation": "terminate",
            "entity": "DepositRate",
            "rows": [{"id": 1}],
            "validFrom": _B1,
        }
    )
    wi.prepare_typed_write(keyed, rate)


def test_member_name_honesty_covers_value_object_members() -> None:
    # A top-level value-object name is a legal write-row key (m-value-object); the
    # honesty check accepts it alongside scalar attributes.
    customer = _MODELS["customer"]
    keyed = wi.deserialize(
        {
            "mutation": "insert",
            "entity": "Customer",
            "rows": [{"id": 9, "name": "Ada", "address": {"street": "Main", "city": "Berlin"}}],
        }
    )
    wi.prepare_typed_write(keyed, customer)


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
        wi.prepare_typed_write(predicate, _ACCOUNT)


def test_member_name_honesty_rejects_a_framework_owned_version_assignment() -> None:
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Account.version", "value": 5}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="framework-owned fields"):
        wi.prepare_typed_write(predicate, _ACCOUNT)


def test_member_name_honesty_rejects_a_scalar_type_mismatched_assignment() -> None:
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": {"all": {}}},
            "assignments": [{"attr": "Account.owner", "value": 42}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="does not match the declared type"):
        wi.prepare_typed_write(predicate, _ACCOUNT)


# --------------------------------------------------------------------------- #
# A value-object assignment validates its value against the declared composite #
# just as scalar assignments validate their values. A non-document value is    #
# rejected with the scalar branch's wording, while a well-formed document is   #
# accepted. `test_where_verbs.py` covers the typed-path half of this check.     #
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
        wi.prepare_typed_write(predicate, customer)


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
    wi.prepare_typed_write(predicate, customer)  # must not raise


# --------------------------------------------------------------------------- #
# A `None` assignment observes nullability through the serialized, case-authored #
# path (`inheritance/__init__.py`). `test_where_verbs.py` covers the typed path. #
# --------------------------------------------------------------------------- #
def test_member_name_honesty_rejects_a_non_nullable_value_object_assignment_of_none() -> None:
    # `models/shipment.yaml`'s `destination` is `nullable: false` (the corpus's
    # "required top-level value object missing" exemplar), so a `None`
    # assignment is invalid.
    shipment = _MODELS["shipment"]
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Shipment", "predicate": {"all": {}}},
            "assignments": [{"attr": "Shipment.destination", "value": None}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="required value object is absent"):
        wi.prepare_typed_write(predicate, shipment)


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
    wi.prepare_typed_write(predicate, customer)  # must not raise


# --------------------------------------------------------------------------- #
# The selecting predicate is measured with the WHOLE `validate_predicate`      #
# vocabulary, not just the rules the instruction schema states — and here,     #
# because this is the ONE model-aware gate every predicate-write ingress runs  #
# (`m-case-format` "The model-aware validator validates the predicate ... and  #
# checks its entity scope"). The two cases below come from different rule      #
# families so the pin covers the vocabulary rather than one rule.              #
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
    with pytest.raises(predicate_algebra.ModelRejectedError) as caught:
        wi.prepare_typed_write(predicate, _ACCOUNT)
    assert caught.value.rule == "between-bounds-inverted"


def test_a_predicate_writes_out_of_position_attribute_reference_is_rejected() -> None:
    orders = _MODELS["orders"]
    predicate = wi.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": "Order",
                "predicate": {"eq": {"attr": "OrderItem.sku", "value": "X"}},
            },
        }
    )
    with pytest.raises(predicate_algebra.ModelRejectedError) as caught:
        wi.prepare_typed_write(predicate, orders)
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
    with pytest.raises(predicate_algebra.ModelRejectedError) as caught:
        wi.prepare_typed_write(predicate, _ACCOUNT)
    assert caught.value.rule == "between-bounds-inverted"


# --------------------------------------------------------------------------- #
# Every query-wide clause `python.md` §5 rejects on a write target — ordering,  #
# the cap, Includes, Temporal Selection, result narrowing — is a clause of      #
# `m-object-query` rather than a Predicate node, so a write target carrying one #
# is a MALFORMED document rather than a rule a model-aware validator applies.   #
# The refusal is the Predicate serde's, one layer earlier, and it is            #
# structural: the shape has no spelling to reject.                              #
# --------------------------------------------------------------------------- #
_BARE_INNER: dict[str, Any] = {"lessThan": {"attr": "Account.balance", "value": 200.00}}


@pytest.mark.parametrize(
    ("clause", "predicate"),
    [
        ("orderBy", {"orderBy": {"operand": _BARE_INNER, "keys": [{"attr": "Account.balance"}]}}),
        ("limit", {"limit": {"operand": _BARE_INNER, "count": 5}}),
        (
            "asOf",
            {"asOf": {"operand": _BARE_INNER, "dimension": "valid-time", "coordinate": _B1}},
        ),
        ("history", {"history": {"operand": _BARE_INNER, "dimension": "valid-time"}}),
        (
            "deepFetch",
            {
                "deepFetch": {
                    "operand": _BARE_INNER,
                    "paths": [{"segments": [{"rel": "Account.entries"}]}],
                }
            },
        ),
    ],
    ids=["orderBy", "limit", "asOf", "history", "deepFetch"],
)
def test_a_query_clause_is_not_a_predicate_at_all(clause: str, predicate: dict[str, Any]) -> None:
    with pytest.raises(
        predicate_algebra.CanonicalDocumentError, match=f"unknown predicate node '{clause}'"
    ):
        wi.deserialize(
            {"mutation": "delete", "target": {"entity": "Account", "predicate": predicate}}
        )


@pytest.mark.parametrize(
    ("position", "predicate"),
    [
        (
            "and",
            {"and": {"operands": [{"limit": {"operand": _BARE_INNER, "count": 5}}, _BARE_INNER]}},
        ),
        ("not", {"not": {"operand": {"limit": {"operand": _BARE_INNER, "count": 5}}}}),
        (
            "exists",
            {"exists": {"rel": "Account.entries", "op": {"limit": {"operand": _BARE_INNER}}}},
        ),
    ],
    ids=["and", "not", "exists"],
)
def test_a_query_clause_is_no_more_spellable_inside_a_predicate(
    position: str, predicate: dict[str, Any]
) -> None:
    # Recursion belongs to the selection grammar alone, so a clause is
    # unspellable at every depth rather than refused at each one.
    assert position in predicate
    with pytest.raises(
        predicate_algebra.CanonicalDocumentError, match="unknown predicate node 'limit'"
    ):
        wi.deserialize(
            {"mutation": "delete", "target": {"entity": "Account", "predicate": predicate}}
        )


@pytest.mark.parametrize(
    ("position", "predicate"),
    [
        ("exists", {"exists": {"rel": "Order.items"}}),
        ("notExists", {"notExists": {"rel": "Order.items"}}),
    ],
    ids=["exists", "not-exists"],
)
def test_a_bare_navigation_filter_carrying_no_inner_predicate_is_accepted(
    position: str, predicate: dict[str, Any]
) -> None:
    # The optional inner `op` is absent — the recursion has nothing to descend
    # into and the predicate stays bare.
    assert position in predicate
    orders = _MODELS["orders"]
    instruction = wi.deserialize(
        {"mutation": "delete", "target": {"entity": "Order", "predicate": predicate}}
    )
    wi.prepare_typed_write(instruction, orders)  # must not raise


def test_a_top_level_narrow_is_a_predicate_scoped_filter() -> None:
    # `narrow` is the one entry of `python.md` §5's enumeration that survives in
    # the Predicate grammar, and it is unambiguously a FILTER there: whole-result
    # narrowing is `narrowTo` on the Object Query, which a write target has no
    # clause for. A write predicate narrowing its own position is therefore an
    # ordinary selection — this target earns the inheritance-family rejection
    # instead, for being a family at all.
    instruction = wi.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": "CardPayment",
                "predicate": {
                    "narrow": {
                        "to": ["CardPayment"],
                        "operand": {"eq": {"attr": "Payment.id", "value": 1}},
                    }
                },
            },
        }
    )
    with pytest.raises(inheritance.InheritanceError) as caught:
        wi.prepare_typed_write(instruction, _PAYMENT)
    assert caught.value.rule == "subtype-write-set-based-unsupported"


_ANIMAL = _MODELS["animal"]
# `Person` owns the polymorphic `animals` (-> the abstract root `Animal`) and is
# itself a plain non-family, non-temporal, unversioned entity — so a predicate
# write on it is legal and the narrow inside its navigation filter is the only
# thing under test.
_ANIMAL_TO_DOG_NARROW: dict[str, Any] = {"narrow": {"to": ["Dog"], "operand": {"all": {}}}}


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
    predicate_algebra.validate_predicate(
        next(e for e in _ANIMAL.entities if e.identity.name == "Person"),
        cast("wi.PredicateWrite", instruction).target.predicate,
        _ANIMAL,
    )
    wi.prepare_typed_write(instruction, _ANIMAL)  # must not raise


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
        wi.prepare_typed_write(instruction, _PAYMENT)
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
    with pytest.raises(predicate_algebra.ModelRejectedError) as caught:
        wi.prepare_typed_write(instruction, _PAYMENT)
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
        wi.prepare_typed_write(instruction, _PAYMENT)
    assert caught.value.rule == "subtype-write-set-based-unsupported"


def test_member_name_honesty_rejects_a_non_nullable_scalar_assignment_of_none() -> None:
    # `Shipment.name` declares no `nullable: true`, so an explicit `None`
    # assignment is refused just as it is for a required value object.
    shipment = _MODELS["shipment"]
    predicate = wi.deserialize(
        {
            "mutation": "update",
            "target": {"entity": "Shipment", "predicate": {"all": {}}},
            "assignments": [{"attr": "Shipment.name", "value": None}],
        }
    )
    with pytest.raises(wi.WriteInstructionError, match="required attribute is absent"):
        wi.prepare_typed_write(predicate, shipment)
