"""Unit tests for the Phase 8 full-bitemporal / business-temporal machinery (no
database).

These pin the DB-free invariants of the Phase 8 temporal slice: the bitemporal
DDL (a two-axis temporal entity's physical primary key spans BOTH as-of
fromColumns so the milestone rectangles are admissible), the temporal
classification of the new models (bitemporal vs unitemporal-business), and the
write-step-count consistency of the `*Until` rectangle-split write sequences (the
sum of per-step counts == goldenSql DML count == roundTrips). The full
apply-DML-and-assert-rectangle-state behavior and the both-axis as-of reads are
exercised end-to-end against real Postgres by the compatibility suite.
"""

from __future__ import annotations

from pathlib import Path

from reference_harness.case import discover_cases, load_model
from reference_harness.case_runner import _assert_write_step_count
from reference_harness.ddl_builder import ddl_for

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _position_model():
    return load_model(COMPATIBILITY_ROOT, "models/position.yaml")


def _reservation_model():
    return load_model(COMPATIBILITY_ROOT, "models/reservation.yaml")


def _phase8_cases():
    return [c for c in discover_cases(COMPATIBILITY_ROOT) if c.path.stem.startswith("08")]


def test_position_is_bitemporal_with_both_axes() -> None:
    entity = _position_model().root_entity
    assert entity.is_temporal
    assert entity.definition["temporal"] == "bitemporal"
    axes = {dim["axis"] for dim in entity.as_of_attributes}
    assert axes == {"business", "processing"}


def test_reservation_is_unitemporal_business() -> None:
    entity = _reservation_model().root_entity
    assert entity.is_temporal
    assert entity.definition["temporal"] == "unitemporal-business"
    (dimension,) = entity.as_of_attributes
    assert dimension["axis"] == "business"


def test_bitemporal_ddl_primary_key_spans_both_as_of_from_columns() -> None:
    (create,) = ddl_for(_position_model(), "postgres")
    # The business key alone (pos_id) is not unique across rectangles; the
    # physical primary key MUST include BOTH axes' fromColumns (from_z, in_z) so a
    # business-bounded rectangle and its inactivated original coexist.
    assert "primary key (pos_id, from_z, in_z)" in create
    for column in ("from_z", "thru_z", "in_z", "out_z"):
        assert f"{column} timestamptz not null" in create


def test_bitemporal_unique_index_matches_physical_primary_key() -> None:
    entity = _position_model().root_entity
    unique_index = next(
        index for index in entity.definition["indices"] if index["name"] == "position_pk"
    )
    assert unique_index == {
        "name": "position_pk",
        "attributes": ["id", "businessFrom", "processingFrom"],
        "unique": True,
    }


def test_business_only_ddl_primary_key_spans_the_business_from_column() -> None:
    (create,) = ddl_for(_reservation_model(), "postgres")
    assert "primary key (res_id, from_z)" in create


def test_business_only_unique_index_matches_physical_primary_key() -> None:
    entity = _reservation_model().root_entity
    unique_index = next(
        index
        for index in entity.definition["indices"]
        if index["name"] == "reservation_pk"
    )
    assert unique_index == {
        "name": "reservation_pk",
        "attributes": ["id", "businessFrom"],
        "unique": True,
    }


def test_bitemporal_history_case_suppresses_both_axes() -> None:
    history_case = next(
        c for c in _phase8_cases() if c.path.stem == "0804-bitemporal-history"
    )
    business_history = history_case.operation["history"]
    processing_history = business_history["operand"]["history"]
    assert business_history["asOfAttr"] == "Position.businessDate"
    assert processing_history["asOfAttr"] == "Position.processingDate"


def test_until_trio_write_step_counts_are_consistent() -> None:
    write_cases = [c for c in _phase8_cases() if c.is_write_sequence]
    assert write_cases, "no Phase 8 write-sequence cases discovered"
    for case in write_cases:
        # Must not raise: per-step counts sum to the DML count and roundTrips,
        # including the 4-statement updateUntil and 3-statement terminateUntil.
        _assert_write_step_count(case, "postgres")


def test_rectangle_split_has_inactivate_plus_three_inserts() -> None:
    update_until = next(
        c for c in _phase8_cases() if "update-until" in c.tags and c.is_write_sequence
    )
    # The updateUntil step is 4 statements: 1 inactivate UPDATE + head/middle/tail
    # inserts. With the leading insert that opens the original, 5 statements total.
    step = next(s for s in update_until.write_sequence if s["mutation"] == "updateUntil")
    assert step["statements"] == 4
    assert len(update_until.golden_statements("postgres")) == 5
