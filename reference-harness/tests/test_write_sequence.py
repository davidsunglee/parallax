"""Unit tests for the Phase 5 write-sequence machinery (no database).

These pin the DB-free invariants of a milestone-chaining write case: the
statement-count consistency check (sum of per-step counts == then.statements DML count
== roundTrips), the temporal DDL (a temporal entity's physical primary key spans
the as-of fromColumn so the milestone chain is admissible), and the as-of-aware
descriptor accessors. The full apply-DML-and-assert-table-state behavior is
exercised end-to-end against real Postgres by the compatibility suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import Case, discover_cases, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _assert_scenario_count_consistency,
    _assert_write_input_columns,
    _assert_write_step_count,
    _increment_marker,
    _is_computed_marker,
    _tag,
)
from reference_harness.ddl_builder import ddl_for

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _balance_model():
    return load_model(COMPATIBILITY_ROOT, "models/balance.yaml")


def _customer_model():
    return load_model(COMPATIBILITY_ROOT, "models/customer.yaml")


def _synthetic_case(raw: dict) -> Case:
    """A DB-free Case bound to the customer (value-object) model."""
    return Case(path=Path("synthetic.yaml"), raw=raw, model=_customer_model())


def test_write_sequence_cases_are_discovered_and_self_describe() -> None:
    cases = {c.path.stem: c for c in discover_cases(COMPATIBILITY_ROOT)}
    write_cases = [c for c in cases.values() if c.is_write_sequence]
    assert write_cases, "no write-sequence cases discovered"
    for case in write_cases:
        # Each declares a writeSequence + a then.tableState, no operation.
        assert case.write_sequence
        assert case.expected_table_state
        assert "operation" not in case.when


def test_write_step_count_consistency_holds_for_authored_cases() -> None:
    for case in discover_cases(COMPATIBILITY_ROOT):
        if case.is_write_sequence:
            # Must not raise: per-step counts sum to the DML count and roundTrips.
            _assert_write_step_count(case, "postgres")


def test_write_step_count_mismatch_is_rejected() -> None:
    case = next(c for c in discover_cases(COMPATIBILITY_ROOT) if c.is_write_sequence)
    # Corrupt the declared per-step statement count so the sum no longer matches
    # the then.statements DML count; the consistency check MUST fail.
    case.when["writeSequence"][0]["statements"] += 1
    with pytest.raises(CaseFailure):
        _assert_write_step_count(case, "postgres")


def _non_temporal_row_step(case) -> dict | None:
    """The first non-temporal write step that carries a neutral write input (①)."""
    for step in case.write_sequence:
        if step.get("rows") and not case.model.entity(step["entity"]).is_temporal:
            return step
    return None


def test_write_input_columns_hold_for_authored_cases() -> None:
    for case in discover_cases(COMPATIBILITY_ROOT):
        if case.is_write_sequence and "postgres" in case.golden_dialects:
            # Must not raise: every authored ① classifies against the model to the
            # golden's INSERT/SET column list, and its values match the binds.
            _assert_write_input_columns(case, "postgres")


def test_write_input_column_corruption_is_rejected() -> None:
    case = next(
        c
        for c in discover_cases(COMPATIBILITY_ROOT)
        if c.is_write_sequence and _non_temporal_row_step(c) is not None
    )
    step = _non_temporal_row_step(case)
    assert step is not None
    # Rename an attribute key in the first ① row to a non-attribute: the neutral
    # write input can no longer classify against the metamodel, so the ① ↔ ②
    # consistency gate MUST fail (it is no longer resting on a golden parse).
    row = step["rows"][0]
    key = next(iter(row))
    row["not_an_attribute"] = row.pop(key)
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _write_case_by_id(prefix: str):
    return next(c for c in discover_cases(COMPATIBILITY_ROOT) if c.path.stem.startswith(prefix))


def test_multi_attribute_audit_update_chains_all_new_values() -> None:
    # m-audit-write-004: a multi-attribute correction (acct + value). The close touches
    # ONLY out_z; the chained INSERT carries the entity's FULL physical row with EVERY
    # new value (Family B — a milestone always writes the whole row).
    case = _write_case_by_id("m-audit-write-004")
    close, chain = case.golden_statements("postgres")[1], case.golden_statements("postgres")[2]
    assert close == "update balance set out_z = ? where bal_id = ? and out_z = ?"
    assert chain.startswith("insert into balance(bal_id, acct_num, val, in_z, out_z)")
    # The chained INSERT binds carry BOTH corrected attributes (acct B, value 250.00).
    assert case.statement_binds(2)[:3] == [1, "B", 250.00]
    # Must not raise: ① (the update row carrying both new attributes) cross-checks ②.
    _assert_write_input_columns(case, "postgres")


def test_fk_delete_ordering_deletes_child_before_parent() -> None:
    # m-unit-work-007: the non-cascade FK-delete direction — the child OrderItem is
    # deleted BEFORE the parent Order it references (the reverse of the insert order).
    case = _write_case_by_id("m-unit-work-007")
    mutations = [step["mutation"] for step in case.write_sequence]
    assert mutations == ["insert", "insert", "delete", "delete"]
    sqls = [s["sql"]["postgres"] for s in case.then["statements"]]
    # The child delete (order_item) precedes the parent delete (orders).
    assert sqls[2] == "delete from order_item where id = ?"
    assert sqls[3] == "delete from orders where id = ?"
    assert sqls.index("delete from order_item where id = ?") < sqls.index(
        "delete from orders where id = ?"
    )
    # Must not raise: each delete ①'s pk value appears in its DELETE binds.
    _assert_write_input_columns(case, "postgres")


def test_collapsed_delete_input_requires_exact_ordered_binds() -> None:
    # m-batch-write-003: three buffered deletes collapse into ONE
    # `delete ... where id in (?, ?, ?)` binding EVERY pk. The ① ↔ ② cross-check MUST
    # require the collapsed binds equal the pk list EXACTLY and IN ORDER — a reordered
    # or extra bind is a corpus error, not a tolerated variant (the earlier membership
    # check accepted both).
    case = _write_case_by_id("m-batch-write-003")
    # As authored (binds [1, 2, 3] == the pk order) it passes.
    _assert_write_input_columns(case, "postgres")

    # Reordered binds (same set, wrong order) MUST now be rejected.
    reordered = _write_case_by_id("m-batch-write-003")
    reordered.then["statements"][0]["binds"] = [3, 2, 1]
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(reordered, "postgres")

    # An EXTRA bind (superset of the pks) MUST be rejected.
    extra = _write_case_by_id("m-batch-write-003")
    extra.then["statements"][0]["binds"] = [1, 2, 3, 4]
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(extra, "postgres")

    # A DUPLICATED bind (a pk repeated, another dropped) MUST be rejected.
    duplicated = _write_case_by_id("m-batch-write-003")
    duplicated.then["statements"][0]["binds"] = [1, 2, 2]
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(duplicated, "postgres")


# --- table-per-hierarchy tag on write (m-inheritance) ------------------------
#
# A table-per-hierarchy insert writes the tag column (`kind`) from the concrete
# subtype's tagValue, NOT from the neutral write input (①) — a framework-derived
# column, exactly like the version bump. A table-per-concrete-subtype insert has no tag.


def test_tph_insert_writes_tag_from_tag_value() -> None:
    # m-inheritance-007: the golden INSERT emits `kind` = the tagValue ('card'); the ①
    # row carries only the domain attributes. The ① ↔ ② cross-check MUST accept the
    # derived tag (its bind is the tagValue).
    case = _write_case_by_id("m-inheritance-007")
    (insert,) = case.golden_statements("postgres")
    assert insert == "insert into payment(id, kind, amount, card_network) values (?, ?, ?, ?)"
    assert case.statement_binds(0) == [10, "card", 200.00, "Mastercard"]
    assert "kind" not in case.write_sequence[0]["rows"][0]  # kind is derived, not authored
    _assert_write_input_columns(case, "postgres")


def test_tag_helper_reads_the_inheritance_metadata() -> None:
    case = _write_case_by_id("m-inheritance-007")
    assert _tag(case.model.entity("CardPayment")) == ("kind", "card")
    # The abstract root owns no rows and no tagValue, so it derives no tag.
    assert _tag(case.model.entity("Payment")) is None
    # A table-per-concrete-subtype entity has no tag (tagValue is absent).
    document = load_model(COMPATIBILITY_ROOT, "models/document.yaml")
    assert _tag(document.entity("Invoice")) is None


def test_tph_insert_rejects_wrong_tag_bind() -> None:
    # Corrupting the tag bind to the wrong tagValue MUST fail the cross-check: the
    # derived value is pinned to the model's tagValue.
    case = _write_case_by_id("m-inheritance-007")
    case.then["statements"][0]["binds"][1] = "cash"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_tph_insert_rejects_tag_authored_in_row() -> None:
    # Authoring the tag column in ① MUST be rejected — it is framework-derived from
    # tagValue, never authored (m-inheritance).
    case = _write_case_by_id("m-inheritance-007")
    case.write_sequence[0]["rows"][0]["kind"] = "card"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_tpcs_insert_targets_concrete_table_without_tag() -> None:
    # m-inheritance-010: a table-per-concrete-subtype INSERT targets the subtype's own
    # table with no tag column and no shared table.
    case = _write_case_by_id("m-inheritance-010")
    (insert,) = case.golden_statements("postgres")
    assert insert == "insert into invoice(id, title, amount_due) values (?, ?, ?)"
    assert "kind" not in insert and "payment" not in insert
    _assert_write_input_columns(case, "postgres")


# --- cascade delete ordering (m-cascade-delete) ------------------------------


def test_one_to_one_cascade_deletes_dependent_before_root() -> None:
    # m-cascade-delete-003: the dependent passport is deleted BEFORE the root person.
    case = _write_case_by_id("m-cascade-delete-003")
    sqls = [s["sql"]["postgres"] for s in case.then["statements"]]
    assert sqls == [
        "delete from passport where person_id = ?",
        "delete from person where id = ?",
    ]
    _assert_write_input_columns(case, "postgres")


def test_multi_root_cascade_deletes_each_roots_children_first() -> None:
    # m-cascade-delete-004: two roots cascaded in one sequence, each deleting its own
    # dependents (children) before its own root row.
    case = _write_case_by_id("m-cascade-delete-004")
    assert [step["mutation"] for step in case.write_sequence] == [
        "cascadeDelete",
        "cascadeDelete",
    ]
    sqls = [s["sql"]["postgres"] for s in case.then["statements"]]
    assert sqls[:3] == [
        "delete from order_status where order_id = ?",
        "delete from order_item where order_id = ?",
        "delete from orders where id = ?",
    ]
    # Each level's binds stay within one root (2, then 42) — not collapsed across roots.
    assert [case.statement_binds(i)[0] for i in range(6)] == [2, 2, 2, 42, 42, 42]
    _assert_write_input_columns(case, "postgres")


def test_non_dependent_relationship_is_not_cascaded() -> None:
    # m-cascade-delete-002: the cascade emits deletes only over dependent edges
    # (statuses, items) — never the non-dependent order_tag table.
    case = _write_case_by_id("m-cascade-delete-002")
    tables = [s["sql"]["postgres"].split()[2] for s in case.then["statements"]]
    assert tables == ["order_status", "order_item", "orders"]
    assert "order_tag" not in tables
    # The surviving order_tag rows (order 1's tags) are asserted unchanged.
    assert "order_tag" in case.expected_table_state


# --- detached merge-back no-op skip (m-detach) -------------------------------


def test_detach_noop_merge_back_issues_no_dml() -> None:
    # m-detach-004: the unmodified merge-back is a scenario NO-OP write step —
    # roundTrips 0 with NO golden SQL (the schema's zero-DML write), witnessing the
    # isModifiedSinceDetachment-false MUST. A writeSequence cannot express zero DML
    # (its schema requires >= 1 golden statement and roundTrips >= 1), so the no-op
    # skip lives in the scenario shape the schema provides for it.
    case = _write_case_by_id("m-detach-004")
    assert case.is_scenario
    (merge_back,) = [step for step in case.scenario if "write" in step]
    assert merge_back["roundTrips"] == 0
    assert "statements" not in merge_back
    # The per-step count-consistency check accepts the zero-round-trip write step.
    _assert_scenario_count_consistency(case, "postgres")


# --- role-aware DB-computed marker interpretation (COR-10) ------------------
#
# A DB-computed marker (`{computed}` / `{increment}`) is a SCALAR-ATTRIBUTE-only
# interpretation: a value-object (document) column ALWAYS binds its WHOLE literal
# document, even when that document is shaped like a marker. The role is resolved
# from `columnOrder(entity)`, never from the value's shape (m-value-object).


def _customer_insert_case(address, sql: str, binds: list) -> Case:
    return _synthetic_case(
        {
            "model": "models/customer.yaml",
            "tags": ["m-value-object"],
            "shape": "writeSequence",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "insert",
                        "entity": "Customer",
                        "rows": [{"id": 1, "name": "Ada", "address": address}],
                    }
                ]
            },
            "then": {
                "statements": [{"sql": {"postgres": sql}, "binds": binds}],
                "tableState": {"customer": [{"id": 1, "name": "Ada", "address": address}]},
            },
        }
    )


def _customer_update_case(address, sql: str, binds: list) -> Case:
    return _synthetic_case(
        {
            "model": "models/customer.yaml",
            "tags": ["m-value-object"],
            "shape": "writeSequence",
            "when": {
                "writeSequence": [
                    {
                        "mutation": "update",
                        "entity": "Customer",
                        "rows": [{"id": 1, "address": address}],
                    }
                ]
            },
            "then": {
                "statements": [{"sql": {"postgres": sql}, "binds": binds}],
                "tableState": {"customer": [{"id": 1, "name": "Ada", "address": address}]},
            },
        }
    )


@pytest.mark.parametrize(
    "document",
    [
        {"computed": "maxPlusOne"},
        {"increment": 1},
        {"computed": "x", "street": "Main"},
    ],
)
def test_marker_shaped_value_object_insert_binds_the_whole_document(document) -> None:
    # The `address` value-object column binds its whole document literally in
    # columnOrder position — the golden's third `?` carries it verbatim, so ① ↔ ②
    # agrees. (Before role-aware gating, the marker-shaped document was mistaken for
    # a DB-computed column and its literal bind was skipped, misaligning the binds.)
    case = _customer_insert_case(
        document,
        "insert into customer(id, name, address) values (?, ?, ?)",
        [1, "Ada", document],
    )
    _assert_write_input_columns(case, "postgres")


@pytest.mark.parametrize("document", [{"increment": 1}, {"computed": "maxPlusOne"}])
def test_marker_shaped_value_object_update_replaces_whole_document(document) -> None:
    # A whole-document UPDATE sets the value-object column exactly like a scalar
    # (`set address = ?`), binding the literal document — never the marker's
    # `col = col + ?` self-advance.
    case = _customer_update_case(
        document,
        "update customer set address = ? where id = ?",
        [document, 1],
    )
    _assert_write_input_columns(case, "postgres")


def test_scalar_attribute_marker_still_classifies_as_computed() -> None:
    # No regression: a SCALAR pk attribute carrying `{computed: maxPlusOne}` is still
    # a DB-computed column — its literal bind is skipped (the golden emits
    # `coalesce(max(id), ?) + ?`), and only the trailing literal columns (name +
    # the address document) supply binds.
    case = _customer_insert_case(
        {"street": "Main"},
        "insert into customer(id, name, address) values (coalesce(max(id), ?) + ?, ?, ?)",
        [0, 1, "Ada", {"street": "Main"}],
    )
    case.raw["when"]["writeSequence"][0]["rows"][0]["id"] = {"computed": "maxPlusOne"}
    # Must not raise: the scalar marker branch is taken (id's bind skipped), while
    # the value-object `address` still binds as one literal document.
    _assert_write_input_columns(case, "postgres")


def test_marker_helpers_are_shape_predicates_over_raw_values() -> None:
    # The low-level predicates still recognize a marker by shape; role-awareness
    # lives in the callers, which never invoke them on a value-object column.
    assert _is_computed_marker({"computed": "maxPlusOne"}) is True
    assert _increment_marker({"increment": 3}) == 3
    assert _is_computed_marker({"street": "Main"}) is False
    assert _increment_marker({"street": "Main"}) is None


def test_is_computed_marker_matches_exact_schema_shape() -> None:
    # The predicate mirrors the EXACT `writeComputedMarker` schema shape: a dict
    # with exactly one key `computed` whose value is exactly "maxPlusOne".
    assert _is_computed_marker({"computed": "maxPlusOne"}) is True
    # A multi-key dict is not the one-key marker shape the schema accepts.
    assert _is_computed_marker({"computed": "maxPlusOne", "street": "Main"}) is False
    assert _is_computed_marker({"computed": "x", "street": "Main"}) is False
    # A different `computed` value is outside the marker's enum.
    assert _is_computed_marker({"computed": "somethingElse"}) is False
    # A non-dict is never a marker.
    assert _is_computed_marker("computed") is False
    assert _is_computed_marker(None) is False


def test_increment_marker_matches_exact_schema_shape() -> None:
    # The predicate mirrors the EXACT `writeComputedMarker` schema shape: a dict
    # with exactly one key `increment` whose value is a JSON integer.
    assert _increment_marker({"increment": 1}) == 1
    assert _increment_marker({"increment": 0}) == 0
    # A multi-key dict is not the one-key marker shape the schema accepts.
    assert _increment_marker({"increment": 1, "street": "Main"}) is None
    # A JSON boolean is schema-type `boolean`, not `integer` — and Python's bool
    # is an int subclass, so it must be excluded explicitly.
    assert _increment_marker({"increment": True}) is None
    assert _increment_marker({"increment": False}) is None
    # A string / float `increment` is not a JSON integer.
    assert _increment_marker({"increment": "1"}) is None
    assert _increment_marker({"increment": 1.5}) is None
    # A non-dict is never a marker.
    assert _increment_marker("increment") is None
    assert _increment_marker(None) is None


def test_temporal_ddl_primary_key_spans_the_as_of_from_column() -> None:
    model = _balance_model()
    (create,) = ddl_for(model, "postgres")
    # The business key alone (bal_id) is not unique across milestones; the
    # physical primary key MUST include the as-of fromColumn (in_z).
    assert "primary key (bal_id, in_z)" in create
    # The interval columns are present and typed as instants.
    assert "in_z timestamptz not null" in create
    assert "out_z timestamptz not null" in create


def test_temporal_unique_index_matches_physical_primary_key() -> None:
    entity = _balance_model().root_entity
    unique_index = next(
        index for index in entity.definition["indices"] if index["name"] == "balance_pk"
    )
    assert unique_index == {
        "name": "balance_pk",
        "attributes": ["id", "processingFrom"],
        "unique": True,
    }


def test_balance_entity_is_unitemporal_processing() -> None:
    model = _balance_model()
    entity = model.root_entity
    assert entity.is_temporal
    (dimension,) = entity.as_of_attributes
    assert dimension["axis"] == "processing"
    assert entity.definition["temporal"] == "unitemporal-processing"
