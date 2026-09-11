"""The rejected lane, driven database-free: the three-way ``when`` dispatch
and the three-form ``when.write`` inside it, the rule each classified corpus
input returns, and every refusal the lane translates into an ``EngineError``
naming the case — an input the validators accept, a malformed input, and a
``when`` carrying none or several of the three inputs.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from parallax.conformance import case_format
from parallax.conformance._lanes import rejected
from parallax.conformance._mechanism.envelope import EngineError


@functools.cache
def _corpus_by_id() -> Mapping[str, case_format.Case]:
    return {case.case_id: case for case in case_format.load_cases()}


def _load_case(case_id: str) -> case_format.Case:
    # Loads by id directly from the corpus, independent of `sweep.
    # IMPLEMENTED_MODULES` reachability: these lane-level tests exercise
    # `run_rejected_case` on its own terms, never gated on whether the case has
    # ALSO been flipped visible in the sweep.
    return _corpus_by_id()[case_id]


def _synthetic_rejected(when: dict[str, object]) -> case_format.Case:
    return case_format.Case(
        path=Path("m-predicate-998-synthetic-rejected.yaml"),
        case_id="m-predicate-998",
        shape="rejected",
        tags=("m-predicate", "rejected", "slice-snapshot-1"),
        model="models/animal.yaml",
        document={"model": "models/animal.yaml", "when": when, "then": {"rejectedRule": "x"}},
    )


def test_run_rejected_case_query_dispatch_classifies_the_rule() -> None:
    case = _load_case("m-inheritance-040")
    assert rejected.run_rejected_case(case) == "narrow-outside-position"


def test_run_rejected_case_query_dispatch_over_a_value_object_model() -> None:
    case = _load_case("m-value-object-034")
    assert rejected.run_rejected_case(case) == "nested-path-first-segment-not-value-object"


def test_run_rejected_case_model_dispatch_reuses_the_phase_3_validator() -> None:
    case = _load_case("m-inheritance-020")
    assert rejected.run_rejected_case(case) == "inheritance-unknown-parent"


def test_run_rejected_case_write_dispatch_classifies_the_rule() -> None:
    case = _load_case("m-value-object-039")
    assert rejected.run_rejected_case(case) == "write-required-attribute-missing"


def test_run_rejected_case_write_dispatch_over_an_inheritance_model() -> None:
    case = _load_case("m-inheritance-088")
    assert rejected.run_rejected_case(case) == "abstract-write-target"


def test_run_rejected_case_refuses_a_bare_row_naming_an_undeclared_member() -> None:
    # An undeclared name resolves to no declared position, so no rule of the closed
    # vocabulary is about it. Grading the row anyway reports whichever rule some OTHER
    # member violates — here the missing required `owner` — and the case passes while
    # testing a member it never named. The keyed instruction form refuses the same
    # way, so one neutral write row is judged one way whichever form carries it.
    graded: dict[str, object] = {"id": 1, "balance": "10.00"}
    assert (
        rejected.run_rejected_case(_synthetic_bare_row(graded, "models/account.yaml"))
        == "write-required-attribute-missing"
    )
    with pytest.raises(EngineError, match=r"names undeclared member\(s\) \['bogus'\]"):
        rejected.run_rejected_case(
            _synthetic_bare_row({**graded, "bogus": 1}, "models/account.yaml")
        )


def test_a_bare_row_carries_the_shared_observation_control_key() -> None:
    # `observedVersion` is flush-time context the shared row vocabulary admits at
    # every row position, so it is not a member name to refuse; the row is graded on
    # its declared members alone.
    row: dict[str, object] = {"id": 1, "balance": "10.00", "observedVersion": 3}
    assert (
        rejected.run_rejected_case(_synthetic_bare_row(row, "models/account.yaml"))
        == "write-required-attribute-missing"
    )


def test_the_subtype_protocol_classifies_the_family_names_member_honesty_would_claim() -> None:
    # `tagValue` names no declared member either, but `m-inheritance` orders the
    # payload-shape rules first and gives it a rule of its own. Asking member honesty
    # before them would report an authoring failure for an input the corpus grades as
    # `subtype-write-metadata-field` (m-inheritance-087).
    row: dict[str, object] = {"id": 1, "amount": "10.00", "tagValue": "card"}
    assert (
        rejected.run_rejected_case(_synthetic_bare_row(row, "models/payment.yaml"))
        == "subtype-write-metadata-field"
    )


def _synthetic_bare_row(row: dict[str, object], model: str) -> case_format.Case:
    return case_format.Case(
        path=Path("m-value-object-996-synthetic-rejected.yaml"),
        case_id="m-value-object-996",
        shape="rejected",
        tags=("m-value-object", "rejected", "slice-snapshot-1"),
        model=model,
        document={"model": model, "when": {"write": row}, "then": {"rejectedRule": "x"}},
    )


def _synthetic_keyed_rejected(write: dict[str, object], model: str) -> case_format.Case:
    return case_format.Case(
        path=Path("m-unit-work-997-synthetic-rejected.yaml"),
        case_id="m-unit-work-997",
        shape="rejected",
        tags=("m-unit-work", "rejected", "slice-snapshot-1"),
        model=model,
        document={"model": model, "when": {"write": write}, "then": {"rejectedRule": "x"}},
    )


def test_run_rejected_case_keyed_write_dispatch_classifies_the_rule() -> None:
    case = _load_case("m-unit-work-016")
    assert rejected.run_rejected_case(case) == "temporal-keyed-write-multi-row"


def test_run_rejected_case_keyed_write_names_its_own_entity_not_the_default_target() -> None:
    # A keyed instruction brings its own handle, so the rule is judged against the
    # entity the instruction names rather than the model's default write root —
    # which here is `Tenant`, neither of the two entities written below. The same
    # plural rows are refused on the temporal entity and accepted on the
    # non-temporal one, so the handle, not the model, is what decided it.
    plural_temporal: dict[str, object] = {
        "mutation": "update",
        "entity": "Lease",
        "rows": [{"id": 1, "term": "annual"}, {"id": 2, "term": "monthly"}],
    }
    plural_non_temporal: dict[str, object] = {
        "mutation": "update",
        "entity": "LeaseNote",
        "rows": [{"id": 1, "text": "first"}, {"id": 2, "text": "second"}],
    }
    model = "models/lease.yaml"
    assert (
        rejected.run_rejected_case(_synthetic_keyed_rejected(plural_temporal, model))
        == "temporal-keyed-write-multi-row"
    )
    with pytest.raises(EngineError, match="accepted a keyed write instruction"):
        rejected.run_rejected_case(_synthetic_keyed_rejected(plural_non_temporal, model))


def test_run_rejected_case_raises_for_a_malformed_keyed_instruction() -> None:
    malformed: dict[str, object] = {"mutation": "update", "rows": [{"id": 1}]}
    with pytest.raises(EngineError, match="missing required key"):
        rejected.run_rejected_case(_synthetic_keyed_rejected(malformed, "models/position.yaml"))


@pytest.mark.parametrize(
    "write",
    [[{"id": 1, "value": 150.00}], [{"id": 1, "value": 150.00}, {"id": 2, "value": 250.00}]],
)
def test_run_rejected_case_refuses_the_conflict_multi_key_array(
    write: list[dict[str, object]],
) -> None:
    # The array is the conflict lane's multi-key form and carries no member for
    # this dispatch to read. Asking it for one instead reaches the bare-row arm
    # with a list, which decodes as a mapping of pairs and fails on the row's own
    # data rather than on the form — a raw carrier error where the case's defect
    # is that no rejected lane defines this input at all.
    case = _synthetic_keyed_rejected(cast("dict[str, object]", write), "models/position.yaml")
    with pytest.raises(EngineError, match="multi-key form"):
        rejected.run_rejected_case(case)


def test_a_default_target_over_a_multi_family_model_is_refused() -> None:
    # The default-target convention names "the family root", singular, so a
    # model carrying several families has no default to resolve and the case
    # must name its target explicitly — never an arbitrary one of them.
    case = case_format.Case(
        path=Path("m-inheritance-997-synthetic-rejected.yaml"),
        case_id="m-inheritance-997",
        shape="rejected",
        tags=("m-inheritance", "rejected", "slice-snapshot-1"),
        model="models/workshop.yaml",
        document={
            "model": "models/workshop.yaml",
            "when": {"write": {"id": 1}},
            "then": {"rejectedRule": "x"},
        },
    )
    with pytest.raises(EngineError, match="no single inheritance family root"):
        rejected.run_rejected_case(case)


def test_run_rejected_case_raises_when_the_query_is_unexpectedly_accepted() -> None:
    valid: dict[str, object] = {"objectQuery": {"target": "Animal", "predicate": {"all": {}}}}
    with pytest.raises(EngineError, match="accepted an Object Query"):
        rejected.run_rejected_case(_synthetic_rejected(valid))


def test_run_rejected_case_raises_when_model_unexpectedly_accepted() -> None:
    valid_model: dict[str, object] = {
        "model": {
            "entities": [
                {
                    "name": "Widget",
                    "table": "widget",
                    "attributes": [
                        {"name": "id", "type": "int64", "column": "id", "primaryKey": True}
                    ],
                }
            ]
        }
    }
    with pytest.raises(EngineError, match="accepted an inline model"):
        rejected.run_rejected_case(_synthetic_rejected(valid_model))


def test_run_rejected_case_raises_when_write_unexpectedly_accepted() -> None:
    valid_write: dict[str, object] = {
        "write": {"id": 1, "owner": "Ada", "balance": "100.00", "version": 1}
    }
    document: dict[str, object] = {
        "model": "models/account.yaml",
        "when": valid_write,
        "then": {"rejectedRule": "x"},
    }
    case = case_format.Case(
        path=Path("m-unit-work-998-synthetic-rejected.yaml"),
        case_id="m-unit-work-998",
        shape="rejected",
        tags=("m-unit-work", "rejected", "slice-snapshot-1"),
        model="models/account.yaml",
        document=document,
    )
    with pytest.raises(EngineError, match="accepted a write"):
        rejected.run_rejected_case(case)


def test_run_rejected_case_raises_for_a_malformed_query() -> None:
    malformed_query: dict[str, object] = {
        "objectQuery": {"target": "Animal", "predicate": {"eq": {}}}
    }
    with pytest.raises(EngineError, match="missing required key"):
        rejected.run_rejected_case(_synthetic_rejected(malformed_query))


def test_run_rejected_case_raises_for_a_malformed_inline_model() -> None:
    # The family door parses shape only, so a document that is not a descriptor
    # at all is ITS refusal — reported against the case rather than graded as a
    # family rule, because no rule was violated by a model that never parsed.
    malformed_model: dict[str, object] = {"model": {"entities": [{"attributes": []}]}}
    with pytest.raises(EngineError, match="`name` must be a string"):
        rejected.run_rejected_case(_synthetic_rejected(malformed_model))


def test_run_rejected_case_raises_for_an_inline_model_the_schema_refuses() -> None:
    # The second door's own refusal, which the first cannot reach: a document
    # whose families are well formed but whose canonical schema they are not.
    # The family validator has no schema phase and returns, so this arrives at
    # `domain_model_from_document` and is a `DescriptorSchemaError` — an engine
    # report, never a graded rule, since a rejected case names a model rule.
    schema_invalid: dict[str, object] = {
        "model": {
            "entities": [
                {
                    "name": "Widget",
                    "table": "widget",
                    "attributes": [
                        {"name": "id", "type": "int64", "primaryKey": True},
                        {"name": "x", "type": "notatype"},
                    ],
                }
            ]
        }
    }
    with pytest.raises(EngineError, match="schema violation"):
        rejected.run_rejected_case(_synthetic_rejected(schema_invalid))


def test_run_rejected_case_raises_when_when_carries_none_of_the_three_inputs() -> None:
    with pytest.raises(EngineError, match="EXACTLY ONE"):
        rejected.run_rejected_case(_synthetic_rejected({}))


def test_run_rejected_case_raises_when_when_carries_a_query_and_a_model() -> None:
    # The schema `oneOf` cannot protect a caller that reaches the engine without
    # schema validation (a hand-built synthetic case, here) — the engine's own
    # mirror guard must still refuse a multi-input `when`.
    when: dict[str, object] = {"objectQuery": {}, "model": {"entities": []}}
    with pytest.raises(EngineError, match="EXACTLY ONE"):
        rejected.run_rejected_case(_synthetic_rejected(when))


def test_run_rejected_case_raises_when_when_carries_a_query_and_a_write() -> None:
    when: dict[str, object] = {"objectQuery": {}, "write": {}}
    with pytest.raises(EngineError, match="EXACTLY ONE"):
        rejected.run_rejected_case(_synthetic_rejected(when))


def test_run_rejected_case_raises_when_when_carries_model_and_write() -> None:
    when: dict[str, object] = {"model": {"entities": []}, "write": {}}
    with pytest.raises(EngineError, match="EXACTLY ONE"):
        rejected.run_rejected_case(_synthetic_rejected(when))
