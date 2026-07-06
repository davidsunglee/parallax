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

from reference_harness.case import discover_cases, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _assert_write_input_columns,
    _assert_write_step_count,
)
from reference_harness.ddl_builder import ddl_for

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _balance_model():
    return load_model(COMPATIBILITY_ROOT, "models/balance.yaml")


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
