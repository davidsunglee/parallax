"""Negative-validation (`rejected` shape) tests — DB-free (m-value-object, Q7).

A `rejected` case (m-case-format resolved Q7) asserts a model-aware validator
refuses an operation OR a write **before any SQL is emitted**, naming the violated
normative rule in `then.rejectedRule`. These tests exercise, without a database:

* every authored `rejected` case runs through :func:`run_case` with NO provider —
  the pre-SQL refusal needs no dialect / provisioning / execution — and its named
  rule is the one the validator raises;
* the model-aware validators (:mod:`op_validate` / :mod:`write_validate`) ACCEPT
  valid operations / documents and RAISE the exact rule for each misuse;
* the runner FAILS loudly when a valid input is (mis)authored as rejected or the
  wrong rule is named; and
* the purely regex-level negatives (an empty path after the value-object name, a
  bad-cased segment) are the OPERATION SCHEMA's job — they are rejected by
  `operation.schema.json`'s `nestedRef` grammar, NOT by a `rejected` case
  (resolved Q7 keeps them as schema-validation unit tests).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from reference_harness.case import Case, discover_cases, load_model
from reference_harness.case_runner import ALL_REJECTED_RULES, CaseFailure, run_case
from reference_harness.inheritance import (
    ABSTRACT_WRITE_TARGET,
    INHERITANCE_CONCRETE_WITHOUT_ABSTRACT_ROOT,
    INHERITANCE_MISSING_ROOT,
    INHERITANCE_MISSING_TAG_VALUE,
    INHERITANCE_MULTIPLE_ROOTS,
    INHERITANCE_UNKNOWN_PARENT,
    MODEL_REJECTED_RULES,
    SUBTYPE_WRITE_METADATA_FIELD,
    SUBTYPE_WRITE_SET_BASED_UNSUPPORTED,
    SUBTYPE_WRITE_SIBLING_ATTRIBUTE,
    WRITE_REJECTED_RULES,
    validate_family,
)
from reference_harness.op_validate import validate_operation
from reference_harness.value_object_resolve import (
    NESTED_LITERAL_TYPE_MISMATCH,
    NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
    NESTED_PATH_UNKNOWN_MEMBER,
    WRITE_REQUIRED_ATTRIBUTE_MISSING,
    WRITE_REQUIRED_VALUE_OBJECT_MISSING,
    WRITE_VALUE_TYPE_MISMATCH,
    RejectionError,
)
from reference_harness.write_validate import validate_subtype_write, validate_write

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_OPERATION_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "operation.schema.json"


def _rejected_cases() -> list[Case]:
    return [c for c in discover_cases(_COMPATIBILITY_ROOT) if c.shape == "rejected"]


def _customer_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/customer.yaml").root_entity


def _contact_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/contact.yaml").root_entity


# --- the authored corpus runs DB-free and rejects with the named rule -------


def test_rejected_cases_exist() -> None:
    cases = _rejected_cases()
    assert cases, "no rejected-shape cases discovered"
    # Every named rule is a member of the closed vocabulary (value-object / operation
    # rules plus the inheritance family-invariant rules).
    for case in cases:
        assert case.rejected_rule in ALL_REJECTED_RULES, (
            f"{case.path.name}: {case.rejected_rule!r} is not a known rejectedRule"
        )


def test_inheritance_model_negatives_are_covered() -> None:
    """The corpus pins every inheritance family invariant as a portable model
    rejected case (m-inheritance, resolved Q3/Q4): each `when.model` case's named
    rule is in the closed inheritance vocabulary, and the corpus covers the whole
    set of family invariants across its cases."""
    model_cases = [c for c in _rejected_cases() if "model" in c.when]
    assert model_cases, "no inheritance `when.model` rejected cases discovered"
    used = {c.rejected_rule for c in model_cases}
    for rule in used:
        assert rule in MODEL_REJECTED_RULES, f"{rule!r} is not an inheritance model rule"
    # Structural invariants that a family MUST reject have at least one witness.
    assert {INHERITANCE_UNKNOWN_PARENT, INHERITANCE_MULTIPLE_ROOTS} <= used


# --- inheritance family invariants closed by the Phase 3 review --------------
#
# Two family invariants the per-entity metamodel schema deliberately delegates to
# the semantic validator (m-inheritance): under table-per-hierarchy every concrete
# subtype MUST declare a `tagValue` (else its rows are indistinguishable in the
# shared table), and a family has EXACTLY ONE root (zero roots is as invalid as
# more than one). These are the reproduce-then-green regressions for the two holes
# the review found: before the fix `validate_family` ACCEPTED both malformed
# descriptors.


def _tph_root(**overrides: Any) -> dict[str, Any]:
    definition = {
        "name": "Animal",
        "inheritance": {
            "role": "root",
            "strategy": "table-per-hierarchy",
            "tag": {"column": "kind"},
        },
        "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
    }
    definition.update(overrides)
    return definition


def test_tph_concrete_subtype_missing_tag_value_is_rejected() -> None:
    # A table-per-hierarchy concrete subtype with NO `tagValue` is schema-valid (the
    # per-entity schema leaves tagValue optional) but semantically invalid: the shared
    # table cannot discriminate its rows. The semantic validator MUST reject it.
    descriptor = {
        "entities": [
            _tph_root(),
            {
                "name": "Dog",
                "table": "animal",
                "inheritance": {"role": "concrete-subtype", "parent": "Animal"},
                "attributes": [
                    {
                        "name": "barkVolume",
                        "type": "int32",
                        "column": "bark_volume",
                        "nullable": True,
                    }
                ],
            },
        ]
    }
    with pytest.raises(RejectionError) as exc:
        validate_family(descriptor)
    assert exc.value.rule == INHERITANCE_MISSING_TAG_VALUE


def test_zero_root_abstract_orphan_family_is_rejected() -> None:
    # An abstract-only orphan chain (an `abstract-subtype` whose parent is a plain,
    # non-inheritance entity): inheritance participants exist, there are ZERO roots and
    # no concrete subtype, so check #6 (concrete-without-abstract-root) never fires. A
    # family has exactly one root, so the zero-root shape MUST be rejected as
    # missing-root rather than silently accepted.
    descriptor = {
        "entities": [
            {
                "name": "Widget",
                "table": "widget",
                "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
            },
            {
                "name": "Pet",
                "inheritance": {"role": "abstract-subtype", "parent": "Widget"},
                "attributes": [
                    {
                        "name": "licenseId",
                        "type": "string",
                        "column": "license_id",
                        "nullable": True,
                    }
                ],
            },
        ]
    }
    with pytest.raises(RejectionError) as exc:
        validate_family(descriptor)
    assert exc.value.rule == INHERITANCE_MISSING_ROOT


def test_concrete_without_abstract_root_is_not_reclassified_as_missing_root() -> None:
    # Guard the taxonomy boundary: m-inheritance-023's descriptor (a concrete subtype
    # whose parent is a plain entity) has zero roots too, but check #6 runs BEFORE the
    # zero-root check, so it MUST still resolve to concrete-without-abstract-root — the
    # missing-root rule is reserved for the abstract-orphan shape with no concrete.
    descriptor = {
        "entities": [
            {
                "name": "Widget",
                "table": "widget",
                "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
            },
            {
                "name": "Gadget",
                "table": "gadget",
                "inheritance": {"role": "concrete-subtype", "parent": "Widget"},
                "attributes": [
                    {"name": "voltage", "type": "int32", "column": "voltage", "nullable": True}
                ],
            },
        ]
    }
    with pytest.raises(RejectionError) as exc:
        validate_family(descriptor)
    assert exc.value.rule == INHERITANCE_CONCRETE_WITHOUT_ABSTRACT_ROOT


def test_the_authored_corpus_covers_both_operation_and_write_negatives() -> None:
    used = {c.rejected_rule for c in _rejected_cases()}
    # Operation negatives (the four contract clauses + the typed-literal MUST).
    assert {
        NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
        "deep-fetch-value-object-segment",
        "navigate-value-object-target",
        "find-root-value-object",
        NESTED_LITERAL_TYPE_MISMATCH,
    } <= used
    # Write negatives (required attribute / nested VO / type mismatch).
    assert {
        WRITE_REQUIRED_ATTRIBUTE_MISSING,
        WRITE_REQUIRED_VALUE_OBJECT_MISSING,
        WRITE_VALUE_TYPE_MISMATCH,
    } <= used


# --- concrete-subtype WRITE negatives (m-inheritance, Phase 7) ----------------
#
# A write to an inheritance family is a concrete-subtype write: its accepted fields
# are exactly the target's ancestry chain. `validate_subtype_write` refuses a keyless
# (set-based) payload, a framework-owned metadata field, a sibling / unrelated-branch
# attribute, and an abstract target — each with its own rule, checked payload-shape
# first (keyless -> metadata -> sibling) then target-validity (abstract).


def _payment_model():
    return load_model(_COMPATIBILITY_ROOT, "models/payment.yaml")


def _subtype_write(row: dict[str, Any]) -> None:
    model = _payment_model()
    validate_subtype_write(model.root_entity, model.entity_defs, row)


def test_subtype_write_negatives_are_covered() -> None:
    # The corpus pins all four Phase-7 subtype-write rules as portable rejected cases.
    used = {c.rejected_rule for c in _rejected_cases()}
    assert WRITE_REJECTED_RULES <= used


def test_subtype_write_accepts_a_valid_concrete_payload() -> None:
    # A keyed payload whose fields all fit a concrete subtype's ancestry chain, aimed at
    # that concrete subtype, is accepted (no raise). CardPayment is the model's second
    # entity, so resolve it explicitly rather than via root_entity (the abstract root).
    model = _payment_model()
    card = model.entity("CardPayment")
    validate_subtype_write(
        card, model.entity_defs, {"id": 10, "amount": 200.00, "cardNetwork": "Visa"}
    )


def test_subtype_write_is_noop_on_non_inheritance_entity() -> None:
    # A non-inheritance entity is out of scope — value-object write validation owns it.
    entity = _customer_entity()
    validate_subtype_write(entity, [entity.definition], {"id": 1, "name": "Ada"})  # no raise


def test_subtype_write_rejects_sibling_attribute() -> None:
    with pytest.raises(RejectionError) as exc:
        _subtype_write({"id": 10, "amount": 200.00, "cardNetwork": "Visa", "tendered": 25.00})
    assert exc.value.rule == SUBTYPE_WRITE_SIBLING_ATTRIBUTE


def test_subtype_write_rejects_metadata_field() -> None:
    with pytest.raises(RejectionError) as exc:
        _subtype_write({"id": 10, "amount": 200.00, "tagValue": "card"})
    assert exc.value.rule == SUBTYPE_WRITE_METADATA_FIELD


def test_subtype_write_rejects_tag_column_in_payload() -> None:
    # The raw tag column name (`kind`) is framework-owned metadata too.
    with pytest.raises(RejectionError) as exc:
        _subtype_write({"id": 10, "amount": 200.00, "kind": "card"})
    assert exc.value.rule == SUBTYPE_WRITE_METADATA_FIELD


def test_subtype_write_rejects_abstract_target() -> None:
    with pytest.raises(RejectionError) as exc:
        _subtype_write({"id": 10, "amount": 200.00, "cardNetwork": "Visa"})
    assert exc.value.rule == ABSTRACT_WRITE_TARGET


def test_subtype_write_rejects_keyless_set_based_write() -> None:
    with pytest.raises(RejectionError) as exc:
        _subtype_write({"amount": 200.00, "cardNetwork": "Visa"})
    assert exc.value.rule == SUBTYPE_WRITE_SET_BASED_UNSUPPORTED


@pytest.mark.parametrize("case", _rejected_cases(), ids=[c.path.stem for c in _rejected_cases()])
def test_rejected_case_is_refused_pre_sql_db_free(case: Case) -> None:
    # `None` is a safe stand-in for the provider: a rejected case is refused with NO
    # database (no dialect / provisioning / execution is reached).
    run_case(case, None)  # type: ignore[arg-type]


# --- the validators ACCEPT valid inputs (no false rejections) ---------------


def test_validate_operation_accepts_valid_nested_predicates() -> None:
    entity = _customer_entity()
    validate_operation(entity, {"nestedEq": {"path": "Customer.address.city", "value": "Oslo"}})
    validate_operation(
        entity, {"nestedGte": {"path": "Customer.address.geo.elevation", "value": 5}}
    )
    validate_operation(entity, {"nestedIsNull": {"path": "Customer.address.geo.point.lat"}})
    validate_operation(
        entity,
        {
            "nestedExists": {
                "path": "Customer.address.phones",
                "where": {
                    "and": {
                        "operands": [
                            {"nestedEq": {"path": "type", "value": "home"}},
                            {"nestedEq": {"path": "number", "value": "555-9999"}},
                        ]
                    }
                },
            }
        },
    )
    # A normal scalar predicate rooted at the ENTITY is not a find-root misuse.
    validate_operation(entity, {"eq": {"attr": "Customer.name", "value": "Ada"}})


def test_validate_write_accepts_complete_and_null_documents() -> None:
    entity = _contact_entity()
    complete = {
        "id": 1,
        "name": "Acme",
        "address": {
            "street": "1 Main St",
            "city": "Oslo",
            "geo": {"country": "NO", "point": {"lat": 59.9, "lon": 10.7}},
            "phones": [{"type": "home", "number": "555"}],
        },
    }
    validate_write(entity, complete)  # no raise
    # A nullable top-level value object may be null (binds SQL NULL); an empty `many`
    # array satisfies a nullable to-many member.
    validate_write(entity, {"id": 2, "name": "Beacon", "address": None})
    complete_empty_phones = json.loads(json.dumps(complete))
    complete_empty_phones["address"]["phones"] = []
    validate_write(entity, complete_empty_phones)


# --- the validators RAISE the exact rule ------------------------------------


def test_unknown_first_segment_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_operation(
            _customer_entity(), {"nestedEq": {"path": "Customer.contact.city", "value": "x"}}
        )
    assert exc.value.rule == NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT


def test_unknown_intermediate_segment_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_operation(
            _customer_entity(), {"nestedEq": {"path": "Customer.address.bogus.x", "value": "x"}}
        )
    assert exc.value.rule == NESTED_PATH_UNKNOWN_MEMBER


def test_unknown_leaf_attribute_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_operation(
            _customer_entity(), {"nestedEq": {"path": "Customer.address.bogus", "value": "x"}}
        )
    assert exc.value.rule == NESTED_PATH_UNKNOWN_MEMBER


def test_membership_literal_type_mismatch_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_operation(
            _customer_entity(), {"nestedIn": {"path": "Customer.address.city", "values": [1, 2]}}
        )
    assert exc.value.rule == NESTED_LITERAL_TYPE_MISMATCH


def test_scoped_where_undeclared_member_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_operation(
            _customer_entity(),
            {
                "nestedExists": {
                    "path": "Customer.address.phones",
                    "where": {"nestedEq": {"path": "bogus", "value": "x"}},
                }
            },
        )
    assert exc.value.rule == NESTED_PATH_UNKNOWN_MEMBER


# --- value-object rules fire at ANY depth in the queried entity's op tree -----
#
# `validate_operation` descends through the SAME-entity boolean combinators
# (and/or/not/group), so a nested-predicate violation buried inside a combinator is
# rejected with its exact rule — not silently accepted because it is not top-level.
# These regression tests pin that recursion (case m-value-object-018 shows nested
# predicates nesting inside `and`, so this path is real).


def test_nested_path_violation_buried_inside_and_is_rejected() -> None:
    entity = _customer_entity()
    operation = {
        "and": {
            "operands": [
                {"nestedEq": {"path": "Customer.address.city", "value": "Oslo"}},  # valid
                {"nestedEq": {"path": "Customer.contact.city", "value": "x"}},  # buried violation
            ]
        }
    }
    with pytest.raises(RejectionError) as exc:
        validate_operation(entity, operation)
    assert exc.value.rule == NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT


def test_nested_literal_type_mismatch_buried_inside_or_not_group_is_rejected() -> None:
    # A mistyped literal (string against a float64 leaf) buried under or -> not ->
    # group is still caught with the literal-type rule, proving every combinator is
    # traversed and resolution stays against the SAME root entity throughout.
    entity = _customer_entity()
    operation = {
        "or": {
            "operands": [
                {"eq": {"attr": "Customer.name", "value": "Ada"}},
                {
                    "not": {
                        "operand": {
                            "group": {
                                "operand": {
                                    "nestedGt": {
                                        "path": "Customer.address.geo.elevation",
                                        "value": "not-a-number",
                                    }
                                }
                            }
                        }
                    }
                },
            ]
        }
    }
    with pytest.raises(RejectionError) as exc:
        validate_operation(entity, operation)
    assert exc.value.rule == NESTED_LITERAL_TYPE_MISMATCH


def test_write_present_but_null_required_value_object_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_write(
            _contact_entity(),
            {"id": 1, "address": {"street": "S", "city": "C", "geo": None}},
        )
    assert exc.value.rule == WRITE_REQUIRED_VALUE_OBJECT_MISSING


def test_write_deep_type_mismatch_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_write(
            _contact_entity(),
            {
                "id": 1,
                "address": {
                    "street": "S",
                    "city": "C",
                    "geo": {"country": "NO", "point": {"lat": "not-a-number", "lon": 2.0}},
                },
            },
        )
    assert exc.value.rule == WRITE_VALUE_TYPE_MISMATCH


# --- the runner FAILS on a mis-authored rejected case -----------------------


def _rejected_doc(operation: dict[str, Any], rule: str) -> Case:
    from reference_harness.case import Model

    raw = {
        "model": "models/customer.yaml",
        "tags": ["m-value-object"],
        "shape": "rejected",
        "when": {"operation": operation},
        "then": {"rejectedRule": rule},
    }
    model = load_model(_COMPATIBILITY_ROOT, "models/customer.yaml")
    assert isinstance(model, Model)
    return Case(path=Path("m-value-object-999-x.yaml"), raw=raw, model=model)


def test_runner_fails_when_a_valid_operation_is_authored_as_rejected() -> None:
    # A perfectly valid nested predicate authored as `rejected` must FAIL — the
    # validator accepts it, so the expected pre-SQL rejection never happens.
    case = _rejected_doc(
        {"nestedEq": {"path": "Customer.address.city", "value": "Oslo"}},
        NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
    )
    with pytest.raises(CaseFailure):
        run_case(case, None)  # type: ignore[arg-type]


def test_runner_fails_when_the_named_rule_is_wrong() -> None:
    # The input IS rejected, but with a DIFFERENT rule than the case names.
    case = _rejected_doc(
        {"nestedEq": {"path": "Customer.contact.city", "value": "x"}},
        NESTED_LITERAL_TYPE_MISMATCH,  # actual rule: first-segment-not-value-object
    )
    with pytest.raises(CaseFailure):
        run_case(case, None)  # type: ignore[arg-type]


# --- the _assert_schema XOR guard: EXACTLY ONE of operation/write (COR-10, Q7) --
#
# A defense-in-depth mirror of the schema `oneOf`: even a case that reaches the
# runner without schema validation MUST carry EXACTLY ONE invalid input, so
# `_assert_schema` raises loudly on BOTH-present or NEITHER-present.


def _rejected_case_with_when(
    when: dict[str, Any],
    rule: str = NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
) -> Case:
    from reference_harness.case import Model

    raw = {
        "model": "models/customer.yaml",
        "tags": ["m-value-object"],
        "shape": "rejected",
        "when": when,
        "then": {"rejectedRule": rule},
    }
    model = load_model(_COMPATIBILITY_ROOT, "models/customer.yaml")
    assert isinstance(model, Model)
    return Case(path=Path("m-value-object-999-x.yaml"), raw=raw, model=model)


def test_assert_schema_rejects_both_operation_and_write() -> None:
    from reference_harness.case_runner import _assert_schema

    case = _rejected_case_with_when(
        {
            "operation": {"nestedEq": {"path": "Customer.contact.city", "value": "x"}},
            "write": {"id": 1, "name": "Acme", "address": {"city": "Oslo"}},
        }
    )
    with pytest.raises(CaseFailure, match="EXACTLY ONE"):
        _assert_schema(case)


def test_assert_schema_rejects_neither_operation_nor_write() -> None:
    from reference_harness.case_runner import _assert_schema

    case = _rejected_case_with_when({})
    with pytest.raises(CaseFailure, match="EXACTLY ONE"):
        _assert_schema(case)


# --- regex-level negatives stay OPERATION-SCHEMA unit tests (resolved Q7) ----


def _operation_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_OPERATION_SCHEMA_PATH.read_text(encoding="utf-8")))


def _op_valid(operation: dict[str, Any]) -> bool:
    return next(_operation_validator().iter_errors(operation), None) is None


def test_schema_accepts_a_well_formed_nested_path() -> None:
    assert _op_valid({"nestedEq": {"path": "Customer.address.city", "value": "Oslo"}})
    assert _op_valid({"nestedEq": {"path": "Customer.address.geo.country", "value": "NO"}})


def test_schema_rejects_empty_path_after_value_object_name() -> None:
    # `Customer.address` has NO field segment after the value-object name — the
    # `nestedRef` grammar requires at least one, so the operation schema rejects it.
    assert not _op_valid({"nestedEq": {"path": "Customer.address", "value": "x"}})


def test_schema_rejects_trailing_dot_path() -> None:
    assert not _op_valid({"nestedEq": {"path": "Customer.address.", "value": "x"}})


def test_schema_rejects_bad_segment_casing() -> None:
    # An uppercase value-object segment and an uppercase field segment both violate
    # the lowercase-initial segment grammar.
    assert not _op_valid({"nestedEq": {"path": "Customer.Address.city", "value": "x"}})
    assert not _op_valid({"nestedEq": {"path": "Customer.address.City", "value": "x"}})
