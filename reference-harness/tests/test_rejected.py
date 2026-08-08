"""Negative-validation (`rejected` shape) tests — DB-free (m-value-object, Q7).

A `rejected` case (m-case-format resolved Q7) asserts a model-aware validator
refuses an operation OR a write **before any SQL is emitted**, naming the violated
normative rule in `then.rejectedRule`. These tests exercise, without a database:

* every authored `rejected` case runs through :func:`run_case` with NO provider —
  the pre-SQL refusal needs no dialect / provisioning / execution — and its named
  rule is the one the validator raises. This module is their sole runner, and the
  partition against the dialect-parametrized collection is pinned here;
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

from reference_harness.case import Case, dialect_executed_cases, discover_cases, load_model
from reference_harness.case_runner import ALL_REJECTED_RULES, CaseFailure, run_case
from reference_harness.inheritance import (
    ABSTRACT_WRITE_TARGET,
    INHERITANCE_CONCRETE_WITHOUT_ABSTRACT_ROOT,
    INHERITANCE_MISSING_CONCRETE_SUBTYPE,
    INHERITANCE_MISSING_ROOT,
    INHERITANCE_MISSING_TAG_VALUE,
    INHERITANCE_TEMPORALITY_NOT_ROOT_OWNED,
    INHERITANCE_UNKNOWN_PARENT,
    MODEL_REJECTED_RULES,
    SUBTYPE_WRITE_METADATA_FIELD,
    SUBTYPE_WRITE_SET_BASED_UNSUPPORTED,
    SUBTYPE_WRITE_SIBLING_ATTRIBUTE,
    WRITE_REJECTED_RULES,
    resolve_effective_definition,
    validate_family,
)
from reference_harness.keyed_write_validate import (
    TEMPORAL_KEYED_WRITE_MULTI_ROW,
    validate_keyed_write,
)
from reference_harness.metamodel import (
    METAMODEL_INDEX_IDENTITY_DUPLICATE,
)
from reference_harness.metamodel import (
    MODEL_REJECTED_RULES as METAMODEL_MODEL_REJECTED_RULES,
)
from reference_harness.op_validate import validate_operation
from reference_harness.storage_layout import (
    MODEL_REJECTED_RULES as STORAGE_LAYOUT_MODEL_REJECTED_RULES,
)
from reference_harness.storage_layout import (
    STORAGE_LAYOUT_COLUMN_COLLISION,
    STORAGE_LAYOUT_TABLE_MAPPING_COLLISION,
)
from reference_harness.temporality import derive_temporal_structure
from reference_harness.value_object_resolve import (
    BETWEEN_BOUNDS_INVERTED,
    FIND_ROOT_VALUE_OBJECT,
    NESTED_LITERAL_TYPE_MISMATCH,
    NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
    NESTED_PATH_UNKNOWN_MEMBER,
    NESTED_STRING_PREDICATE_NON_STRING_MEMBER,
    WRITE_REQUIRED_ATTRIBUTE_MISSING,
    WRITE_REQUIRED_VALUE_OBJECT_MISSING,
    WRITE_VALUE_TYPE_MISMATCH,
    RejectionError,
    literal_matches_type,
)
from reference_harness.write_validate import (
    framework_owned_names,
    validate_subtype_write,
    validate_write,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_OPERATION_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "operation.schema.json"


def _rejected_cases() -> list[Case]:
    return [c for c in discover_cases(_COMPATIBILITY_ROOT) if c.shape == "rejected"]


def _customer_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/customer.yaml").root_entity


def _contact_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/contact.yaml").root_entity


def _order_entity():
    return load_model(_COMPATIBILITY_ROOT, "models/orders.yaml").root_entity


# --- the authored corpus runs DB-free and rejects with the named rule -------


def test_rejected_cases_exist() -> None:
    cases = _rejected_cases()
    assert cases, "no rejected-shape cases discovered"
    # Every named rule is a member of the closed owner vocabularies.
    for case in cases:
        assert case.rejected_rule in ALL_REJECTED_RULES, (
            f"{case.path.name}: {case.rejected_rule!r} is not a known rejectedRule"
        )


def test_model_negatives_use_closed_owner_vocabularies() -> None:
    """Every model rejection belongs to the resolver, Inheritance, or Storage Layout."""
    model_cases = [c for c in _rejected_cases() if "model" in c.when]
    assert model_cases, "no `when.model` rejected cases discovered"
    used = {c.rejected_rule for c in model_cases}
    allowed = (
        METAMODEL_MODEL_REJECTED_RULES | MODEL_REJECTED_RULES | STORAGE_LAYOUT_MODEL_REJECTED_RULES
    )
    assert not (unexpected := used - allowed), (
        f"model rejection rules are outside the closed owner vocabularies: {sorted(unexpected)}"
    )
    # Structural invariants that a family MUST reject have at least one witness.
    assert {INHERITANCE_UNKNOWN_PARENT, INHERITANCE_MISSING_ROOT} <= used
    assert {
        STORAGE_LAYOUT_TABLE_MAPPING_COLLISION,
        STORAGE_LAYOUT_COLUMN_COLLISION,
    } <= used
    assert METAMODEL_INDEX_IDENTITY_DUPLICATE in used


# --- inheritance family invariants -------------------------------------------
#
# Two family invariants the per-entity metamodel schema deliberately delegates to
# the semantic validator (m-inheritance): under table-per-hierarchy every concrete
# subtype MUST declare a `tagValue` (else its rows are indistinguishable in the
# shared table), and a family has EXACTLY ONE root — a statement about one family's
# own ancestry, so a descriptor declaring SEVERAL independent rooted families is
# legal and only the zero-root shape is rejected.


def _tph_root(**overrides: Any) -> dict[str, Any]:
    definition = {
        "name": "Animal",
        "table": "animal",
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


def test_independent_families_in_one_descriptor_are_accepted() -> None:
    # Two families that share no ancestry, each rooted and each under its OWN
    # strategy. "Exactly one root" is asked of a family, not of the descriptor, and
    # the strategy-scoped checks are likewise per family: resolving one strategy for
    # the whole descriptor would apply the table-per-hierarchy shared-table rule to
    # the table-per-concrete-subtype family (or the reverse) and reject a legal model.
    descriptor = {
        "entities": [
            _tph_root(),
            {
                "name": "Dog",
                "inheritance": {"role": "concrete-subtype", "parent": "Animal", "tagValue": "dog"},
                "attributes": [
                    {"name": "barkVolume", "type": "int32", "column": "bark_volume"},
                ],
            },
            {
                "name": "Document",
                "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
                "attributes": [
                    {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                ],
            },
            {
                "name": "Invoice",
                "table": "invoice",
                "inheritance": {"role": "concrete-subtype", "parent": "Document"},
                "attributes": [{"name": "total", "type": "int64", "column": "total"}],
            },
        ]
    }
    validate_family(descriptor)


def test_zero_root_family_beside_a_rooted_one_is_rejected() -> None:
    # A rooted family does not answer for its neighbour: the abstract-orphan chain
    # (`Pet` under the plain `Widget`) reaches no root of its own and MUST still be
    # rejected, even though the descriptor declares a perfectly valid family too.
    descriptor = {
        "entities": [
            _tph_root(),
            {
                "name": "Dog",
                "inheritance": {"role": "concrete-subtype", "parent": "Animal", "tagValue": "dog"},
                "attributes": [
                    {"name": "barkVolume", "type": "int32", "column": "bark_volume"},
                ],
            },
            {
                "name": "Widget",
                "table": "widget",
                "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
            },
            {
                "name": "Pet",
                "inheritance": {"role": "abstract-subtype", "parent": "Widget"},
                "attributes": [
                    {"name": "licenseId", "type": "string", "column": "license_id"},
                ],
            },
        ]
    }
    with pytest.raises(RejectionError) as exc:
        validate_family(descriptor)
    assert exc.value.rule == INHERITANCE_MISSING_ROOT


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


def test_a_family_with_no_concrete_subtype_is_rejected() -> None:
    # Every other family rule passes — the parent resolves, there is exactly one
    # root, the root owns the shared table, no descendant repeats it, and the
    # tagValue rules have no concrete subtype to ask about. That is the point:
    # only concrete subtypes own rows, so this family's every position resolves
    # over the EMPTY effective concrete set and needs a rule of its own.
    descriptor = {
        "entities": [
            _tph_root(),
            {
                "name": "Pet",
                "inheritance": {"role": "abstract-subtype", "parent": "Animal"},
                "attributes": [
                    {"name": "licenseId", "type": "string", "column": "license_id"},
                ],
            },
        ]
    }
    with pytest.raises(RejectionError) as exc:
        validate_family(descriptor)
    assert exc.value.rule == INHERITANCE_MISSING_CONCRETE_SUBTYPE


def test_a_rooted_family_with_no_concrete_is_rejected_beside_a_complete_one() -> None:
    # The rule is asked per family: a complete neighbour does not answer for the
    # concrete-less one, exactly as it does not answer for a rootless one.
    descriptor = {
        "entities": [
            _tph_root(),
            {
                "name": "Dog",
                "inheritance": {"role": "concrete-subtype", "parent": "Animal", "tagValue": "dog"},
                "attributes": [{"name": "barkVolume", "type": "int32", "column": "bark_volume"}],
            },
            {
                "name": "Document",
                "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
                "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
            },
        ]
    }
    with pytest.raises(RejectionError) as exc:
        validate_family(descriptor)
    assert exc.value.rule == INHERITANCE_MISSING_CONCRETE_SUBTYPE


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


def test_descendant_temporality_under_a_non_temporal_root_is_rejected() -> None:
    # Temporality is a family-wide property (the binding root-ownership
    # decision): a NON-temporal TPH root with an abstract-subtype that
    # declares its own profile MUST be rejected, regardless of the root's own
    # temporal state.
    descriptor = {
        "entities": [
            _tph_root(),
            {
                "name": "Pet",
                "inheritance": {"role": "abstract-subtype", "parent": "Animal"},
                "temporality": "transaction-time",
            },
            {
                "name": "Dog",
                "inheritance": {"role": "concrete-subtype", "parent": "Pet", "tagValue": "dog"},
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
    assert exc.value.rule == INHERITANCE_TEMPORALITY_NOT_ROOT_OWNED


def test_descendant_temporality_under_a_temporal_root_is_rejected() -> None:
    # A TEMPORAL TPCS root whose concrete subtype widens the profile MUST also
    # be rejected: a descendant may not redeclare, add, remove, override, or
    # shadow the family profile even when the root itself is temporal.
    descriptor = {
        "entities": [
            {
                "name": "Rate",
                "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
                "temporality": "transaction-time",
                "attributes": [
                    {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                    {"name": "amount", "type": "decimal(18,2)", "column": "amount"},
                ],
            },
            {
                "name": "DepositRate",
                "table": "deposit_rate",
                "inheritance": {"role": "concrete-subtype", "parent": "Rate"},
                "temporality": "bitemporal",
                "attributes": [
                    {"name": "grade", "type": "string", "column": "grade", "nullable": True},
                ],
            },
        ]
    }
    with pytest.raises(RejectionError) as exc:
        validate_family(descriptor)
    assert exc.value.rule == INHERITANCE_TEMPORALITY_NOT_ROOT_OWNED


def test_resolve_effective_definition_inherits_temporality_from_the_root_only() -> None:
    # `DepositRate` declares no `temporality` of its own; the flattened
    # definition surfaces the ROOT's profile (never a nearer, non-root ancestor —
    # a valid descriptor never HAS one, per the invariant above), and with it the
    # root's derived endpoint attributes.
    entity_defs = derive_temporal_structure(
        {
            "entities": [
                {
                    "name": "Rate",
                    "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
                    "temporality": "transaction-time",
                    "attributes": [
                        {"name": "id", "type": "int64", "column": "id", "primaryKey": True},
                    ],
                },
                {
                    "name": "DepositRate",
                    "table": "deposit_rate",
                    "inheritance": {"role": "concrete-subtype", "parent": "Rate"},
                    "attributes": [{"name": "grade", "type": "string", "column": "grade"}],
                },
            ]
        }
    )["entities"]
    resolved = resolve_effective_definition(entity_defs, "DepositRate")
    assert resolved["temporality"] == "transaction-time"
    assert [attribute["column"] for attribute in resolved["attributes"]] == [
        "id",
        "in_z",
        "out_z",
        "grade",
    ]


def test_the_authored_corpus_covers_both_operation_and_write_negatives() -> None:
    used = {c.rejected_rule for c in _rejected_cases()}
    # Operation negatives (the four contract clauses, the typed-literal MUST, and
    # the bound-ordering MUST).
    assert {
        NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
        "deep-fetch-value-object-segment",
        "navigate-value-object-target",
        "find-root-value-object",
        NESTED_LITERAL_TYPE_MISMATCH,
        BETWEEN_BOUNDS_INVERTED,
    } <= used
    # Write negatives (required attribute / nested VO / type mismatch).
    assert {
        WRITE_REQUIRED_ATTRIBUTE_MISSING,
        WRITE_REQUIRED_VALUE_OBJECT_MISSING,
        WRITE_VALUE_TYPE_MISMATCH,
    } <= used


# --- concrete-subtype WRITE negatives (m-inheritance) -------------------------
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
    # The corpus pins all four subtype-write rules as portable rejected cases.
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


# --- keyed-instruction shape (m-unit-work) ------------------------------------
#
# The third `when.write` form. Unlike a bare write row it names its own entity, so
# the judgement is about the instruction's shape against THAT target's temporal
# profile rather than about a payload against the model's default write root.


def _lease_model():
    return load_model(_COMPATIBILITY_ROOT, "models/lease.yaml")


def _rejected_keyed_doc(instruction: dict[str, Any], rule: str) -> Case:
    raw = {
        "model": "models/lease.yaml",
        "tags": ["m-unit-work"],
        "shape": "rejected",
        "when": {"write": instruction},
        "then": {"rejectedRule": rule},
    }
    return Case(path=Path("m-unit-work-999-x.yaml"), raw=raw, model=_lease_model())


def test_keyed_write_rejects_plural_rows_on_a_temporal_target() -> None:
    instruction = {
        "mutation": "update",
        "entity": "Lease",
        "rows": [{"id": 1, "term": "annual"}, {"id": 2, "term": "monthly"}],
    }
    with pytest.raises(RejectionError) as exc:
        validate_keyed_write(_lease_model().entity("Lease"), instruction)
    assert exc.value.rule == TEMPORAL_KEYED_WRITE_MULTI_ROW


def test_keyed_write_accepts_plural_rows_on_a_non_temporal_target() -> None:
    # The contrast that makes the rule the TARGET's: the same plural shape against
    # a non-temporal entity of the same model is the set-based flush m-batch-write
    # collapses, not a refusal.
    instruction = {
        "mutation": "update",
        "entity": "LeaseNote",
        "rows": [{"id": 1, "text": "first"}, {"id": 2, "text": "second"}],
    }
    validate_keyed_write(_lease_model().entity("LeaseNote"), instruction)


def test_keyed_write_accepts_a_single_row_on_a_temporal_target() -> None:
    instruction = {"mutation": "update", "entity": "Lease", "rows": [{"id": 1, "term": "annual"}]}
    validate_keyed_write(_lease_model().entity("Lease"), instruction)


def test_runner_fails_when_a_keyed_instruction_is_accepted() -> None:
    # A single-row temporal instruction authored as rejected: the validator accepts
    # it, so the expected pre-SQL rejection never happens.
    case = _rejected_keyed_doc(
        {"mutation": "update", "entity": "Lease", "rows": [{"id": 1, "term": "annual"}]},
        TEMPORAL_KEYED_WRITE_MULTI_ROW,
    )
    with pytest.raises(CaseFailure, match="did not match its pre-SQL refusal"):
        run_case(case, None)  # type: ignore[arg-type]


def test_runner_fails_when_a_keyed_instruction_names_an_undeclared_entity() -> None:
    # A keyed instruction resolves against the handle it authored and nothing else,
    # so an unknown handle is an authoring failure rather than a silent fallback to
    # the model's default write root.
    case = _rejected_keyed_doc(
        {"mutation": "update", "entity": "Sublease", "rows": [{"id": 1}, {"id": 2}]},
        TEMPORAL_KEYED_WRITE_MULTI_ROW,
    )
    with pytest.raises(CaseFailure, match="does not declare"):
        run_case(case, None)  # type: ignore[arg-type]


def test_runner_fails_a_keyed_instruction_naming_an_undeclared_member() -> None:
    # Payload honesty precedes the instruction's shape, so a plural instruction whose
    # rows also name nothing real fails as an authoring defect instead of being
    # classified with the singleton rule it never reached. That is the precedence the
    # canonical `validate_instruction` applies (undeclared members refuse before the
    # temporal singleton); without it the two implementations answer the SAME
    # schema-valid input with different verdicts.
    case = _rejected_keyed_doc(
        {
            "mutation": "update",
            "entity": "Lease",
            "rows": [{"id": 1, "notAMember": 7}, {"id": 2, "notAMember": 8}],
        },
        TEMPORAL_KEYED_WRITE_MULTI_ROW,
    )
    with pytest.raises(CaseFailure, match="are not attributes or value objects"):
        run_case(case, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("case", _rejected_cases(), ids=[c.path.stem for c in _rejected_cases()])
def test_rejected_case_is_refused_pre_sql_db_free(case: Case) -> None:
    # `None` is a safe stand-in for the provider: a rejected case is refused with NO
    # database (no dialect / provisioning / execution is reached).
    run_case(case, None)  # type: ignore[arg-type]


def test_rejected_and_dialect_executed_cases_partition_the_harness_lane() -> None:
    # Each side is the selection its runner really parametrizes over — this module's
    # `_rejected_cases`, and `dialect_executed_cases`, which is what the
    # dialect-parametrized runner collects. The lane they must cover is recomputed
    # here from `discover_cases`, so an exclusion added to either selection strands
    # the cases it drops instead of shrinking both sides of the comparison at once.
    harness_lane = {
        c.path for c in discover_cases(_COMPATIBILITY_ROOT) if c.lane != "api-conformance"
    }
    rejected = {c.path for c in _rejected_cases()}
    dialect_executed = {c.path for c in dialect_executed_cases(_COMPATIBILITY_ROOT)}

    assert rejected, "no rejected cases discovered under core/compatibility/cases"
    assert dialect_executed, "no dialect-executed cases discovered under core/compatibility/cases"
    assert rejected <= harness_lane, (
        "a rejected case outside the harness lane would be run here and nowhere else"
    )
    assert rejected.isdisjoint(dialect_executed)
    assert rejected | dialect_executed == harness_lane


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
    validate_operation(
        entity,
        {"nestedBetween": {"path": "Customer.address.geo.elevation", "lower": 5, "upper": 12}},
    )
    validate_operation(
        entity, {"nestedNotIn": {"path": "Customer.address.city", "values": ["Oslo"]}}
    )
    validate_operation(
        entity,
        {
            "nestedExists": {
                "path": "Customer.address.phones",
                "where": {
                    "and": {
                        "operands": [
                            {
                                "nestedBetween": {
                                    "path": "number",
                                    "lower": "555-9000",
                                    "upper": "555-9999",
                                }
                            },
                            {"nestedNotIn": {"path": "type", "values": ["work"]}},
                        ]
                    }
                },
            }
        },
    )
    # A normal scalar predicate rooted at the ENTITY is not a find-root misuse.
    validate_operation(entity, {"eq": {"attr": "Customer.name", "value": "Ada"}})


def _complete_contact_row() -> dict[str, Any]:
    """A Contact write row every declared member of which is present and well-typed.

    A rejected write probe mutates ONE position of this row, so the rule it raises is
    the one that position's defect names rather than whichever member the row also
    happened to omit.
    """
    return {
        "id": 1,
        "name": "Acme",
        "address": {
            "street": "1 Main St",
            "city": "Oslo",
            "geo": {"country": "NO", "point": {"lat": 59.9, "lon": 10.7}},
            "phones": [{"type": "home", "number": "555"}],
        },
    }


def test_validate_write_accepts_complete_and_null_documents() -> None:
    entity = _contact_entity()
    complete = _complete_contact_row()
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


def test_negated_membership_literal_type_mismatch_rejected() -> None:
    # The negated form carries the identical typed-literal obligation; the two share
    # one arm rather than the negation reaching an untyped shortcut.
    with pytest.raises(RejectionError) as exc:
        validate_operation(
            _customer_entity(), {"nestedNotIn": {"path": "Customer.address.city", "values": [42]}}
        )
    assert exc.value.rule == NESTED_LITERAL_TYPE_MISMATCH


def _element_where(where: dict[str, Any]) -> dict[str, Any]:
    return {"nestedExists": {"path": "Customer.address.phones", "where": where}}


@pytest.mark.parametrize(
    "node",
    [
        {"nestedBetween": {"path": "Customer.address.city", "lower": 42, "upper": 7}},
        _element_where({"nestedBetween": {"path": "number", "lower": 42, "upper": 7}}),
    ],
    ids=["path-scoped", "element-scoped"],
)
def test_nested_range_bound_type_mismatch_is_reported_before_the_ordering(
    node: dict[str, Any],
) -> None:
    # Both bounds mistype a `string` leaf AND are inverted as raw numbers, so this
    # discriminates the check order: a validator that ordered the bounds before
    # resolving the subject would report the inversion and blame the wrong thing.
    with pytest.raises(RejectionError) as exc:
        validate_operation(_customer_entity(), node)
    assert exc.value.rule == NESTED_LITERAL_TYPE_MISMATCH


@pytest.mark.parametrize(
    "node",
    [
        {"nestedBetween": {"path": "Customer.address.geo.elevation", "lower": 12, "upper": 5}},
        _element_where({"nestedBetween": {"path": "type", "lower": "work", "upper": "home"}}),
    ],
    ids=["path-scoped", "element-scoped"],
)
def test_nested_range_with_inverted_bounds_rejected_in_both_scopes(node: dict[str, Any]) -> None:
    # Correctly typed bounds, so resolution passes and the shared bound-ordering rule
    # is what fires — the same rule the top-level `between` obeys, at both scopes.
    with pytest.raises(RejectionError) as exc:
        validate_operation(_customer_entity(), node)
    assert exc.value.rule == BETWEEN_BOUNDS_INVERTED


# --- nested string predicates (m-op-algebra non-string-member rule) -----------


@pytest.mark.parametrize(
    "tag", ["nestedLike", "nestedNotLike", "nestedStartsWith", "nestedEndsWith", "nestedContains"]
)
def test_nested_string_predicate_accepts_a_string_member_in_both_scopes(tag: str) -> None:
    entity = _customer_entity()
    validate_operation(entity, {tag: {"path": "Customer.address.city", "value": "Os"}})
    validate_operation(
        entity, {tag: {"path": "Customer.address.city", "value": "Os", "caseInsensitive": True}}
    )
    validate_operation(entity, _element_where({tag: {"path": "number", "value": "555"}}))


@pytest.mark.parametrize(
    "tag", ["nestedLike", "nestedNotLike", "nestedStartsWith", "nestedEndsWith", "nestedContains"]
)
def test_nested_string_predicate_on_a_numeric_member_reports_the_member_not_the_literal(
    tag: str,
) -> None:
    # `geo.elevation` is float64 and the literal is a string, so BOTH nested rules
    # apply — which is what discriminates their order. A validator checking the
    # literal first would blame the value for the member's problem.
    with pytest.raises(RejectionError) as exc:
        validate_operation(
            _customer_entity(), {tag: {"path": "Customer.address.geo.elevation", "value": "1"}}
        )
    assert exc.value.rule == NESTED_STRING_PREDICATE_NON_STRING_MEMBER


@pytest.mark.parametrize(
    "node",
    [
        {"nestedStartsWith": {"path": "Contact.address.phones.expires", "value": "2024"}},
        {
            "nestedExists": {
                "path": "Contact.address.phones",
                "where": {"nestedEndsWith": {"path": "expires", "value": "-01"}},
            }
        },
    ],
    ids=["path-scoped", "element-scoped"],
)
def test_nested_string_predicate_on_a_date_member_rejected_in_both_scopes(
    node: dict[str, Any],
) -> None:
    # The hole the dedicated rule closes: a `date` member carries the portable string
    # literal, so `literal_matches_type` finds '2024' perfectly well-typed for it and
    # the typed-literal rule alone would ACCEPT a text pattern over a date.
    with pytest.raises(RejectionError) as exc:
        validate_operation(_contact_entity(), node)
    assert exc.value.rule == NESTED_STRING_PREDICATE_NON_STRING_MEMBER


# --- range bound ordering (m-op-algebra) -------------------------------------
#
# The bounds are compared by LITERAL KIND, so the rule fires on two numbers or two
# strings and stands aside for every other pairing. It is the one operation rule that
# consults no declared structure: both operands are authored on the node itself.


def _between(lower: Any, upper: Any) -> dict[str, Any]:
    return {"between": {"attr": "Order.price", "lower": lower, "upper": upper}}


@pytest.mark.parametrize(
    ("lower", "upper"),
    [(50.75, 20.00), (5, 1), ("2024-05-01", "2024-02-01"), ("b", "a")],
)
def test_between_with_inverted_same_kind_bounds_rejected(lower: Any, upper: Any) -> None:
    with pytest.raises(RejectionError) as exc:
        validate_operation(_order_entity(), _between(lower, upper))
    assert exc.value.rule == BETWEEN_BOUNDS_INVERTED


@pytest.mark.parametrize(
    ("lower", "upper"),
    [
        (20.00, 50.75),
        (5, 5),
        ("a", "a"),
        ("2024-02-01", "2024-05-01"),
        (5, "1"),
        ("5", 1),
        (None, 1),
        (5, None),
        (True, False),
    ],
)
def test_between_bounds_the_rule_stands_aside_for_are_accepted(lower: Any, upper: Any) -> None:
    # Ordered and equal same-kind bounds are legal ranges; a mixed-kind pair, a null
    # bound, and a boolean pair are all skipped rather than guessed.
    validate_operation(_order_entity(), _between(lower, upper))


def test_between_bound_ordering_is_checked_at_any_depth() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_operation(
            _order_entity(),
            {"and": {"operands": [{"all": {}}, _between(50.75, 20.00)]}},
        )
    assert exc.value.rule == BETWEEN_BOUNDS_INVERTED


def test_between_rooted_at_a_value_object_still_reports_the_find_root_rule() -> None:
    # The subject is checked before the bounds, so a value-object-rooted range names
    # the root misuse rather than blaming its (also inverted) bounds.
    with pytest.raises(RejectionError) as exc:
        validate_operation(
            _customer_entity(),
            {"between": {"attr": "address.city", "lower": "b", "upper": "a"}},
        )
    assert exc.value.rule == FIND_ROOT_VALUE_OBJECT


def test_deep_fetch_path_root_narrow_naming_a_value_object_rejected() -> None:
    # A path-ROOT guard resolves at the queried position, so both its members name
    # Entities. A value object has no identity, no position, and no concrete
    # subtypes, so naming one there is the same refusal a value-object-rooted
    # attribute reference gets — reported against the guard, not against a segment.
    for narrow in (
        {"entity": "address", "to": ["Customer"]},
        {"entity": "Customer", "to": ["address"]},
    ):
        with pytest.raises(RejectionError) as exc:
            validate_operation(
                _customer_entity(),
                {
                    "deepFetch": {
                        "operand": {"all": {}},
                        "paths": [{"narrow": narrow, "segments": [{"rel": "Customer.locations"}]}],
                    }
                },
            )
        assert exc.value.rule == FIND_ROOT_VALUE_OBJECT


def test_deep_fetch_path_root_narrow_over_entities_is_accepted() -> None:
    # The subtype-position rules themselves belong to the inheritance walk, so a
    # guard naming Entities passes this validator untouched.
    validate_operation(
        _customer_entity(),
        {
            "deepFetch": {
                "operand": {"all": {}},
                "paths": [
                    {
                        "narrow": {"entity": "Customer", "to": ["Customer"]},
                        "segments": [{"rel": "Customer.locations"}],
                    }
                ],
            }
        },
    )


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
    row = _complete_contact_row()
    row["address"]["geo"] = None
    with pytest.raises(RejectionError) as exc:
        validate_write(_contact_entity(), row)
    assert exc.value.rule == WRITE_REQUIRED_VALUE_OBJECT_MISSING


def test_write_deep_type_mismatch_rejected() -> None:
    row = _complete_contact_row()
    row["address"]["geo"]["point"]["lat"] = "not-a-number"
    with pytest.raises(RejectionError) as exc:
        validate_write(_contact_entity(), row)
    assert exc.value.rule == WRITE_VALUE_TYPE_MISMATCH


# --- the bare write row's complete cell table (m-case-format "What decides a bare
# --- write row") -------------------------------------------------------------
#
# A rejected `when.write` row is decided position by position, so what an
# implementation may be asked is the cross product of the six declared position
# kinds with the value classes a schema-valid row can author at one. The schema
# closes the DISPATCH question and cannot close this one — it is model-blind, and
# `writeRowValue` admits every JSON value — so the specification enumerates the
# cells and these pin the harness against that enumeration. The corpus pins the
# same cells across BOTH graders; these reach the ones no rejected case witnesses,
# including every accepted cell, which no case can express.


_ABSENT = object()


def _contact_row_at(path: str, value: Any) -> dict[str, Any]:
    """The complete Contact row with the member at dotted *path* replaced.

    ``_ABSENT`` removes the key; every other value is authored as written. A `many`
    element is addressed by its index (``address.phones.0.number``).
    """
    row = _complete_contact_row()
    node: Any = row
    *parents, leaf = path.split(".")
    for parent in parents:
        node = node[int(parent)] if parent.isdigit() else node[parent]
    if value is _ABSENT:
        node.pop(leaf, None)
    else:
        node[leaf] = value
    return row


# Contact declares `id` / `name` (required attributes), a nullable `one` `address`,
# and inside it required `street` / `city`, a required nested `one` `geo`, and a
# `many` `phones` whose element attributes are nullable.
@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        # Attribute, nullable: false — absent and explicit null are the same absence.
        ("name", _ABSENT, WRITE_REQUIRED_ATTRIBUTE_MISSING),
        ("name", None, WRITE_REQUIRED_ATTRIBUTE_MISSING),
        ("name", "Acme", None),
        ("id", 7, None),
        ("id", "seven", WRITE_VALUE_TYPE_MISMATCH),
        ("id", True, WRITE_VALUE_TYPE_MISMATCH),
        ("id", {"street": "x"}, WRITE_VALUE_TYPE_MISMATCH),
        ("id", [1], WRITE_VALUE_TYPE_MISMATCH),
        # Attribute, nullable: true — absence and null are both licensed.
        ("address.phones.0.number", _ABSENT, None),
        ("address.phones.0.number", None, None),
        ("address.phones.0.number", 555, WRITE_VALUE_TYPE_MISMATCH),
        # Value Object `one`, nullable: true — a null document binds SQL NULL.
        ("address", _ABSENT, None),
        ("address", None, None),
        ("address", "1 Main St", WRITE_VALUE_TYPE_MISMATCH),
        ("address", [{"street": "x"}], WRITE_VALUE_TYPE_MISMATCH),
        # Value Object `one`, nullable: false (nested).
        ("address.geo", _ABSENT, WRITE_REQUIRED_VALUE_OBJECT_MISSING),
        ("address.geo", None, WRITE_REQUIRED_VALUE_OBJECT_MISSING),
        ("address.geo", 42, WRITE_VALUE_TYPE_MISMATCH),
        # Value Object `many` — absence IS the empty collection, null is not a state
        # the model gives it, and the value bound is a list OF DOCUMENTS.
        ("address.phones", _ABSENT, None),
        ("address.phones", [], None),
        ("address.phones", None, WRITE_REQUIRED_VALUE_OBJECT_MISSING),
        ("address.phones", "555", WRITE_VALUE_TYPE_MISMATCH),
        ("address.phones", {"number": "555"}, WRITE_VALUE_TYPE_MISMATCH),
        ("address.phones", ["555"], WRITE_VALUE_TYPE_MISMATCH),
    ],
)
def test_bare_write_row_cell(path: str, value: Any, expected: str | None) -> None:
    entity = _contact_entity()
    row = _contact_row_at(path, value)
    if expected is None:
        validate_write(entity, row)
        return
    with pytest.raises(RejectionError) as exc:
        validate_write(entity, row)
    assert exc.value.rule == expected


def test_bare_write_row_classifies_in_declaration_order() -> None:
    # Two defects in one row: `name` absent (an Attribute) and `address.geo` absent
    # (a Value Object). Declaration order puts every Attribute before every Value
    # Object, so the rule is the model's answer rather than the row's key order —
    # the property that lets two independent graders classify one row identically.
    defects = {"id": 1, "address": {"street": "S", "city": "C"}}
    reversed_order = {"address": {"street": "S", "city": "C"}, "id": 1}
    for row in (defects, reversed_order):
        with pytest.raises(RejectionError) as exc:
            validate_write(_contact_entity(), row)
        assert exc.value.rule == WRITE_REQUIRED_ATTRIBUTE_MISSING


def test_bare_write_row_exempts_framework_owned_attributes() -> None:
    # The framework supplies these values, so their absence is no caller omission:
    # Account's `version` carries `optimisticLocking`, and Balance's Transaction-Time
    # endpoints are derived structure rather than authored members. A row omitting
    # both is complete.
    account = load_model(_COMPATIBILITY_ROOT, "models/account.yaml").root_entity
    assert "version" in framework_owned_names(account)
    validate_write(account, {"id": 1, "owner": "Ada", "balance": "10.00"})

    balance = load_model(_COMPATIBILITY_ROOT, "models/balance.yaml").root_entity
    assert {"txStart", "txEnd"} <= framework_owned_names(balance)
    validate_write(balance, {"id": 1, "acctNum": "A", "value": "10.00"})


def test_db_computed_marker_is_exempt_at_a_scalar_and_refused_in_a_document() -> None:
    # A marker is disambiguated by the position's declared metamodel ROLE, never by
    # the value's shape: it stands for a value the DB computes at a scalar Attribute
    # column, and a value object binds its whole document even when that document
    # happens to be shaped like one.
    account = load_model(_COMPATIBILITY_ROOT, "models/account.yaml").root_entity
    validate_write(account, {"id": {"computed": "maxPlusOne"}, "owner": "Ada", "balance": "1.00"})

    row = _complete_contact_row()
    row["address"]["geo"]["point"]["lat"] = {"computed": "maxPlusOne"}
    with pytest.raises(RejectionError) as exc:
        validate_write(_contact_entity(), row)
    assert exc.value.rule == WRITE_VALUE_TYPE_MISMATCH


# The neutral type vocabulary is CLOSED, and membership asks whether the authored
# PORTABLE literal decodes to a value of the space. Decoding is many-to-one where the
# document encoding is one-to-one, so the two directions are pinned together: a
# non-canonical spelling the portable grammar admits is a member (uppercase hex, a
# hyphenless UUID, an unpadded time, a non-UTC offset), while a literal that names no
# value is not (an integer beyond its width, a number whose magnitude the declared
# float width cannot hold, a decimal the scale cannot hold, text with no UTF-8
# encoding, a separator inside a hex spelling, a malformed spelling, a
# sub-microsecond instant).
#
# A float literal is where "names a value" is WIDEST: every number in range names the
# float of the declared width nearest it, so an inexact one is a member and stores as
# the value it names. The integer / fraction carrier the loader chose is not a
# distinction — `16777217` and `16777217.0` are one JSON number — and exactness is
# deliberately not the rule, since a canonical float32 spelling is itself routinely
# inexact (`m-case-format` "In-space").
#
# The grammar is bounded ABOVE as well: a spelling only the host parser takes —
# ``uuid.UUID``'s brace-wrapped and ``urn:uuid:`` forms and its indifference to
# hyphen position, ``fromisoformat``'s week dates, basic-format runs, and arbitrary
# date/time separator, ``decimal.Decimal``'s digit separators, leading ``+``,
# surrounding space, and exponent — is NOT a member, or a second language would have
# to reproduce Python rather than the neutral contract (ADR 0016).
@pytest.mark.parametrize(
    ("neutral_type", "value", "matches"),
    [
        ("boolean", True, True),
        ("boolean", 1, False),
        ("int32", 2**31 - 1, True),
        ("int32", 2**31, False),
        ("int32", True, False),
        ("int64", 2**63 - 1, True),
        ("int64", 2**63, False),
        ("float64", 1.5, True),
        ("float64", "1.5", False),
        ("float64", True, False),
        ("float64", 9007199254740992, True),
        ("float64", 9007199254740993, True),
        ("float64", 9007199254740993.0, True),
        ("float64", 10**400, False),
        ("float64", 1.7976931348623157e308, True),
        ("float32", 1.5, True),
        ("float32", 16777216, True),
        ("float32", 16777217, True),
        ("float32", 16777217.0, True),
        ("float32", 1e30, True),
        ("float32", 1048576.25, True),
        ("float32", 2**31 - 1, True),
        ("float32", 1e39, False),
        ("float32", 1e100, False),
        ("float32", 1.7976931348623157e308, False),
        ("string", "s", True),
        ("string", 1, False),
        ("string", "\ud800", False),
        ("decimal(4,2)", "12.34", True),
        ("decimal(4,2)", "-12.34", True),
        ("decimal(4,2)", "0.50", True),
        ("decimal(4,2)", 12, True),
        ("decimal(4,2)", "12.345", False),
        ("decimal(4,2)", "123.45", False),
        ("decimal(4,2)", "not-a-decimal", False),
        ("decimal(4,2)", "1_2.34", False),
        ("decimal(4,2)", "+12.34", False),
        ("decimal(4,2)", " 12.34 ", False),
        ("decimal(4,2)", "1.234e1", False),
        ("decimal(4,2)", "012.34", False),
        ("decimal(4,2)", "NaN", False),
        ("bytes", "00ff", True),
        ("bytes", "00FF", True),
        ("bytes", "0a1B", True),
        ("bytes", "", True),
        ("bytes", "0f0", False),
        ("bytes", "00 ff", False),
        ("bytes", "0z", False),
        ("date", "2024-01-01", True),
        ("date", "not-a-date", False),
        ("date", "2024-02-30", False),
        ("date", "20240101", False),
        ("date", "2024-W01-1", False),
        ("date", "2024-1-1", False),
        ("time", "12:00:00", True),
        ("time", "12:00", True),
        ("time", "12:00:00+00:00", False),
        ("time", "T12:00:00", False),
        ("time", "1200", False),
        ("timestamp", "2024-01-01T00:00:00Z", True),
        ("timestamp", "2024-01-01T00:00:00+00:00", True),
        ("timestamp", "2024-01-01T00:00:00+02:00", True),
        ("timestamp", "2024-01-01T00:00:00", False),
        ("timestamp", "2024-01-01 00:00:00+00:00", False),
        ("timestamp", "2024-01-01X00:00:00+00:00", False),
        ("timestamp", "20240101T000000Z", False),
        ("timestamp", "2024-W01-1T00:00:00Z", False),
        ("timestamp", "2024-01-01T00:00:00.1234567+00:00", False),
        ("timestamp", "2024-01-01T00:00:00.1234560+00:00", True),
        ("uuid", "123e4567-e89b-12d3-a456-426614174000", True),
        ("uuid", "123E4567-E89B-12D3-A456-426614174000", True),
        ("uuid", "123e4567e89b12d3a456426614174000", True),
        ("uuid", "{123e4567-e89b-12d3-a456-426614174000}", False),
        ("uuid", "urn:uuid:123e4567-e89b-12d3-a456-426614174000", False),
        ("uuid", "123e4567-e89b12d3-a456-426614174000", False),
        ("uuid", "not-a-uuid", False),
        ("json", {"any": "value"}, True),
    ],
)
def test_portable_literal_membership(neutral_type: str, value: Any, matches: bool) -> None:
    assert literal_matches_type(value, neutral_type) is matches


def test_the_case_format_leaf_encoding_witness_authors_decodable_spellings() -> None:
    # Every spelling `m-document-codec-001` authors is a member of its declared type
    # even though the document stores a different, canonical spelling for four of
    # them. Grading membership against the STORED form instead would refuse the one
    # case whose whole subject is that the two differ.
    authored = {
        "bytes": "0A1B",
        "uuid": "123E4567-E89B-12D3-A456-426614174000",
        "time": "09:30",
        "timestamp": "2026-01-15T11:30:00+02:00",
        "decimal(6,2)": 5,
    }
    assert all(
        literal_matches_type(value, neutral_type) for neutral_type, value in authored.items()
    )


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


def test_runner_fails_a_handleless_input_against_a_multi_family_model() -> None:
    # A bare row and an operation both name no target, so both resolve the model's
    # DEFAULT write root. A model declaring several families names no single root, so
    # there is no default: the case must carry its own handle. Resolving it to
    # whichever entity is declared first would grade a rule against an entity the
    # case never named, which is the failure this refusal replaces. The instruction
    # forms beside it name their own handle and are unaffected — the corpus's own
    # m-batch-write-009 is a predicate write on exactly such a model.
    from reference_harness.case import Model

    model = load_model(_COMPATIBILITY_ROOT, "models/workshop.yaml")
    assert isinstance(model, Model)
    raw = {
        "model": "models/workshop.yaml",
        "tags": ["m-value-object"],
        "shape": "rejected",
        "when": {"write": {"id": 1}},
        "then": {"rejectedRule": WRITE_REQUIRED_ATTRIBUTE_MISSING},
    }
    case = Case(path=Path("m-value-object-998-x.yaml"), raw=raw, model=model)
    with pytest.raises(CaseFailure, match="no default write root"):
        run_case(case, None)  # type: ignore[arg-type]


def _bare_row_case(model_rel: str, row: dict[str, Any], rule: str) -> Case:
    from reference_harness.case import Model

    model = load_model(_COMPATIBILITY_ROOT, model_rel)
    assert isinstance(model, Model)
    raw = {
        "model": model_rel,
        "tags": ["m-value-object"],
        "shape": "rejected",
        "when": {"write": row},
        "then": {"rejectedRule": rule},
    }
    return Case(path=Path("m-value-object-997-x.yaml"), raw=raw, model=model)


def test_runner_fails_a_bare_row_naming_an_undeclared_member() -> None:
    # An undeclared name resolves to no declared position, so no rule of the closed
    # vocabulary is about it. Grading the row anyway reports whichever rule some OTHER
    # member violates — here the missing required `owner` — and the case passes while
    # testing a member it never named. The keyed instruction form refuses the same
    # way, so one neutral write row is judged one way whichever form carries it.
    case = _bare_row_case(
        "models/account.yaml",
        {"id": 1, "balance": "10.00", "bogus": 1},
        WRITE_REQUIRED_ATTRIBUTE_MISSING,
    )
    with pytest.raises(CaseFailure, match=r"names \['bogus'\]"):
        run_case(case, None)  # type: ignore[arg-type]


def test_a_bare_row_carries_the_shared_observation_control_key() -> None:
    # `observedVersion` is flush-time context the shared row vocabulary admits at
    # every row position, so it is not a member name to refuse. The row below is
    # graded on its declared members alone, which is why the missing `owner` is what
    # the runner reports.
    case = _bare_row_case(
        "models/account.yaml",
        {"id": 1, "balance": "10.00", "observedVersion": 3},
        WRITE_REQUIRED_ATTRIBUTE_MISSING,
    )
    run_case(case, None)  # type: ignore[arg-type]


def test_the_subtype_protocol_classifies_the_family_names_member_honesty_would_claim() -> None:
    # `tagValue` names no declared member either, but `m-inheritance` orders the
    # payload-shape rules first and gives it a rule of its own. Asking member honesty
    # before them would report a case-authoring failure for an input the corpus grades
    # as `subtype-write-metadata-field` (m-inheritance-087).
    from reference_harness.inheritance import SUBTYPE_WRITE_METADATA_FIELD

    case = _bare_row_case(
        "models/payment.yaml",
        {"id": 1, "amount": "10.00", "tagValue": "card"},
        SUBTYPE_WRITE_METADATA_FIELD,
    )
    run_case(case, None)  # type: ignore[arg-type]


# --- the _assert_schema XOR guard: EXACTLY ONE of operation/write ------------
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


@pytest.mark.parametrize(
    "write",
    [
        [{"id": 1, "name": "Acme", "address": {"city": "Oslo"}}],
        [{"id": 1, "name": "Acme"}, {"id": 2, "name": "Zenith"}],
    ],
)
def test_rejected_write_refuses_the_conflict_multi_key_array(write: list[Any]) -> None:
    # The array is the conflict lane's multi-key form and carries no member for a
    # rejected case's dispatch to read, so it is refused by SHAPE. Reading it
    # through the single-row conflict accessor instead answers a one-element array
    # with its row and a longer one with nothing — grading a bare row the case
    # never authored, or an empty one, and in both directions reporting that
    # validation ACCEPTED an input no rejected lane defines.
    from reference_harness.case_runner import _assert_rejected

    case = _rejected_case_with_when({"write": write})
    with pytest.raises(CaseFailure, match="multi-key form"):
        _assert_rejected(case)


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
