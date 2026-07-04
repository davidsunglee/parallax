"""Unit tests for the PK-generation oracle (case_runner._assert_pk_allocation).

The oracle re-derives the allocated primary keys and the advanced sequence
counter from the DECLARED pkGenerator config and asserts them against the real
DB state. These tests pin the pure derivation math and the failure path.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from reference_harness.case import discover_cases, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _assert_pk_allocation,
    _assert_write_input_columns,
    _expected_sequence_counter,
    _expected_sequence_ids,
    _pk_sequence_counter_column,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


# --- pure derivation -------------------------------------------------------


def test_sequence_ids_basic() -> None:
    # init 1, inc 1, batch 1 -> 1,2,3
    assert _expected_sequence_ids(1, 1, 1, 3) == [1, 2, 3]


def test_sequence_ids_initial_and_increment() -> None:
    # init 1000, inc 5, batch 1 -> 1000,1005,1010
    assert _expected_sequence_ids(1000, 5, 1, 3) == [1000, 1005, 1010]


def test_sequence_ids_batch_partial_and_full() -> None:
    # init 1, inc 1, batch 3
    assert _expected_sequence_ids(1, 1, 3, 2) == [1, 2]  # 2 of a block of 3
    assert _expected_sequence_ids(1, 1, 3, 4) == [1, 2, 3, 4]  # full block + 1


def test_sequence_ids_stride() -> None:
    # init 100, inc 10, batch 2 -> 100,110 | 120,130
    assert _expected_sequence_ids(100, 10, 2, 4) == [100, 110, 120, 130]


def test_sequence_counter_reserves_full_blocks() -> None:
    assert _expected_sequence_counter(1, 1, 1, 3) == 4  # 3 single-id blocks
    assert _expected_sequence_counter(1000, 5, 1, 3) == 1015  # 3 blocks of stride 5
    assert _expected_sequence_counter(1, 1, 3, 2) == 4  # 1 block of 3 reserved
    assert _expected_sequence_counter(1, 1, 3, 4) == 7  # 2 blocks of 3 reserved
    assert _expected_sequence_counter(100, 10, 2, 4) == 140  # 2 blocks of stride 20
    assert _expected_sequence_counter(1, 1, 3, 0) == 1  # nothing allocated


# --- oracle against a fake DB ----------------------------------------------


class _FakePkDb:
    """Returns canned rows for `_read_table`'s `select ... from <table> t0`."""

    dialect = "postgres"

    def __init__(self, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
        self._rows = rows_by_table

    def query(self, sql: str, binds: list[Any] | None = None) -> list[dict[str, Any]]:
        for table, rows in self._rows.items():
            if f" from {table} " in f"{sql} ":
                return rows
        return []


def _pass_case() -> SimpleNamespace:
    model = load_model(COMPATIBILITY_ROOT, "models/pk-sequence.yaml")
    return SimpleNamespace(
        model=model,
        write_sequence=[
            {"mutation": "update", "entity": "PkSequence"},
            {"mutation": "insert", "entity": "Pass"},
        ],
        path=Path("0627-unit.yaml"),
    )


def test_oracle_passes_for_correct_allocation() -> None:
    case = _pass_case()
    db = _FakePkDb(
        {
            "pass": [{"id": 1, "zone": "A"}, {"id": 2, "zone": "B"}],
            "pk_sequence": [{"name": "pass_seq", "next_val": 4}],
        }
    )
    _assert_pk_allocation(case, db)  # no raise


def test_oracle_rejects_wrong_ids() -> None:
    case = _pass_case()
    db = _FakePkDb(
        {
            "pass": [{"id": 1, "zone": "A"}, {"id": 3, "zone": "B"}],  # gap-skipped wrongly
            "pk_sequence": [{"name": "pass_seq", "next_val": 4}],
        }
    )
    with pytest.raises(CaseFailure):
        _assert_pk_allocation(case, db)


def test_oracle_rejects_wrong_counter() -> None:
    case = _pass_case()
    db = _FakePkDb(
        {
            "pass": [{"id": 1, "zone": "A"}, {"id": 2, "zone": "B"}],
            "pk_sequence": [{"name": "pass_seq", "next_val": 3}],  # should be 4
        }
    )
    with pytest.raises(CaseFailure):
        _assert_pk_allocation(case, db)


# --- _pk_sequence_counter_column guard tests ----------------------------------


def _fake_registry(name: str, attributes: list[dict]) -> SimpleNamespace:
    """Lightweight fake registry: the helper reads only .name and .attributes."""
    return SimpleNamespace(name=name, attributes=attributes)


def test_counter_column_returns_single_int64_non_pk_column() -> None:
    reg = _fake_registry(
        "PkSequence",
        [
            {"name": "name", "type": "string", "column": "name", "primaryKey": True},
            {"name": "nextVal", "type": "int64", "column": "next_val"},
        ],
    )
    assert _pk_sequence_counter_column(reg) == "next_val"


def test_counter_column_raises_for_two_int64_non_pk_columns() -> None:
    reg = _fake_registry(
        "PkSequence",
        [
            {"name": "name", "type": "string", "column": "name", "primaryKey": True},
            {"name": "nextVal", "type": "int64", "column": "next_val"},
            {"name": "extra", "type": "int64", "column": "extra_val"},
        ],
    )
    with pytest.raises(CaseFailure, match="exactly one"):
        _pk_sequence_counter_column(reg)


def test_counter_column_raises_for_zero_int64_non_pk_columns() -> None:
    reg = _fake_registry(
        "PkSequence",
        [
            {"name": "name", "type": "string", "column": "name", "primaryKey": True},
            {"name": "label", "type": "string", "column": "label"},
        ],
    )
    with pytest.raises(CaseFailure, match="exactly one"):
        _pk_sequence_counter_column(reg)


# --- ① write-input gate over the pk-gen corpus (DQ-D markers) ------------------


def _pkgen_write_input_cases() -> list:
    """pk-gen write-sequence cases carrying a neutral write input (① ``rows``)."""
    return [
        case
        for case in discover_cases(COMPATIBILITY_ROOT)
        if case.is_write_sequence
        and "postgres" in case.golden_sql
        and "pk-generation" in case.tags
        and any(step.get("rows") for step in case.write_sequence)
    ]


def _pkgen_case(stem_prefix: str):
    return next(
        c for c in discover_cases(COMPATIBILITY_ROOT) if c.path.stem.startswith(stem_prefix)
    )


def test_pkgen_write_input_holds_for_authored_cases() -> None:
    cases = _pkgen_write_input_cases()
    # The `max` (computed) and `sequence` (increment) families both carry ①.
    assert {case.path.stem[:4] for case in cases} >= {"0620", "0623"}
    for case in cases:
        # Must not raise: a `computed` pk column appears in the golden INSERT list
        # (its DB-derived bind skipped), an `increment` registry advance matches the
        # golden's `col = col + ?` shape plus its amount bind, and every allocated
        # insert's literal columns match their golden binds.
        _assert_write_input_columns(case, "postgres")


def test_pkgen_max_computed_literal_corruption_is_rejected() -> None:
    # `0620` is a pk-gen `max` insert: `{ id: { computed: maxPlusOne }, name: Ada }`.
    # The DB-computed `id` bind is skipped, but the LITERAL `name` is still cross-
    # checked — corrupt it so its ① value no longer matches the golden bind.
    case = _pkgen_case("0620")
    step = next(s for s in case.write_sequence if s.get("rows"))
    step["rows"][0]["name"] = "NotAda"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_pkgen_sequence_increment_amount_corruption_is_rejected() -> None:
    # `0623` step 1 advances the registry via `next_val = next_val + ?` by 1. Corrupt
    # the `{ increment: <n> }` amount so the DERIVED bind no longer matches the golden.
    case = _pkgen_case("0623")
    step = next(s for s in case.write_sequence if s["entity"] == "PkSequence")
    step["rows"][0]["nextVal"] = {"increment": 99}
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")
