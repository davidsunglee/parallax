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

import re
from pathlib import Path

import pytest

from reference_harness.case import discover_cases, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _assert_conflict_input,
    _assert_write_input_columns,
    _assert_write_step_count,
)
from reference_harness.ddl_builder import ddl_for

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _case_id(stem: str) -> str:
    """The per-module id prefix of a case stem (drops the trailing ``-<slug>``)."""
    return re.match(r"(m-[a-z0-9-]+-\d{3})", stem).group(1)


def _position_model():
    return load_model(COMPATIBILITY_ROOT, "models/position.yaml")


def _reservation_model():
    return load_model(COMPATIBILITY_ROOT, "models/reservation.yaml")


_PHASE8_MODULES = ("m-temporal-read", "m-bitemp-write", "m-business-only")


def _phase8_cases():
    """The full-bitemporal + business-temporal single-entity cases (formerly the 08xx
    range): reads/writes on the bitemporal/business models, excluding the audit-only
    reads and the relationship-propagation deep-fetch cases (which also carry a
    temporal flavor but file under `m-navigate`)."""
    return [
        c
        for c in discover_cases(COMPATIBILITY_ROOT)
        if any(c.path.stem.startswith(f"{module}-") for module in _PHASE8_MODULES)
        and ("bitemporal" in c.tags or "business_temporal" in c.tags)
    ]


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
        index for index in entity.definition["indices"] if index["name"] == "reservation_pk"
    )
    assert unique_index == {
        "name": "reservation_pk",
        "attributes": ["id", "businessFrom"],
        "unique": True,
    }


def test_bitemporal_history_case_suppresses_both_axes() -> None:
    history_case = next(
        c for c in _phase8_cases() if c.path.stem == "m-temporal-read-016-bitemporal-history"
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


def _temporal_write_input_cases():
    """Audit-only write-sequence cases carrying a temporal neutral write input (①)."""
    return [
        case
        for case in discover_cases(COMPATIBILITY_ROOT)
        if case.is_write_sequence
        and "postgres" in case.golden_dialects
        and any(
            step.get("rows") and case.model.entity(step["entity"]).is_temporal
            for step in case.write_sequence
        )
    ]


def test_temporal_write_input_holds_for_authored_cases() -> None:
    cases = _temporal_write_input_cases()
    # The Phase 3 in-slice audit trio all carry ① (rows + at).
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-audit-write-001",
        "m-audit-write-002",
        "m-audit-write-003",
    }
    for case in cases:
        # Must not raise: each audit-only ① derives in_z = at / out_z = infinity and
        # the full-row binds that cross-check the authored golden binds.
        _assert_write_input_columns(case, "postgres")


def test_temporal_write_input_at_corruption_is_rejected() -> None:
    case = next(
        c for c in _temporal_write_input_cases() if c.path.stem.startswith("m-audit-write-001")
    )
    step = next(s for s in case.write_sequence if s.get("rows"))
    # Corrupt the transaction instant: the DERIVED in_z bind no longer matches the
    # golden in_z bind, so the ① ↔ ② temporal gate MUST fail (in_z is derived from
    # `at`, never read from the golden).
    step["at"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _until_write_cases():
    """Full-bitemporal `*Until` rectangle-split write-sequence cases
    (`m-bitemp-write-001`-`m-bitemp-write-003`)."""
    return [
        case
        for case in _phase8_cases()
        if case.is_write_sequence
        and any(
            step.get("mutation") in ("insertUntil", "updateUntil", "terminateUntil")
            for step in case.write_sequence
        )
    ]


def test_until_write_input_holds_for_authored_cases() -> None:
    cases = _until_write_cases()
    # The `*Until` trio all carry the valid-time window ① (rows + at + until).
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-bitemp-write-001",
        "m-bitemp-write-002",
        "m-bitemp-write-003",
    }
    for case in cases:
        # Must not raise: the close binds [at, pk, infinity], every chained insert
        # opens at fresh processing [at, infinity), and the business window bounds
        # (businessFrom / until) appear among the chained inserts' business-axis binds.
        _assert_write_input_columns(case, "postgres")


def test_until_write_input_window_corruption_is_rejected() -> None:
    case = next(c for c in _until_write_cases() if c.path.stem.startswith("m-bitemp-write-001"))
    step = next(s for s in case.write_sequence if s.get("until"))
    # Corrupt the business valid-time window end: `until` no longer appears among the
    # chained inserts' business-axis binds, so the `*Until` ① ↔ ② window gate MUST
    # fail (the window bounds are DERIVED from `at`/`until`, never read from golden).
    step["until"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _business_write_cases():
    """Business-temporal-only milestone-chaining write cases
    (`m-business-only-001`-`m-business-only-003`)."""
    return [
        case
        for case in discover_cases(COMPATIBILITY_ROOT)
        if case.is_write_sequence
        and "postgres" in case.golden_dialects
        and any(step.get("businessAt") for step in case.write_sequence)
    ]


def test_business_write_input_holds_for_authored_cases() -> None:
    cases = _business_write_cases()
    # The business-only insert / update-chaining / terminate trio all carry ①
    # (rows + businessAt).
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-business-only-001",
        "m-business-only-002",
        "m-business-only-003",
    }
    for case in cases:
        # Must not raise: each business-only ① derives from_z = businessAt /
        # thru_z = infinity and the full-row binds that cross-check the golden binds
        # (the same close-and-chain shape as the audit-only axis, driven by business
        # date rather than transaction instant).
        _assert_write_input_columns(case, "postgres")


def test_business_write_input_business_at_corruption_is_rejected() -> None:
    case = next(c for c in _business_write_cases() if c.path.stem.startswith("m-business-only-003"))
    step = next(s for s in case.write_sequence if s.get("businessAt"))
    # Corrupt the business instant: the DERIVED from_z bind no longer matches the
    # golden from_z bind, so the business-temporal ① ↔ ② gate MUST fail (from_z is
    # derived from `businessAt`, never read from the golden).
    step["businessAt"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _bitemporal_conflict_close_cases():
    """Bitemporal conflict-close cases (`m-bitemp-write-004` / `m-bitemp-write-005`):
    a business + processing axis."""
    return [
        case
        for case in discover_cases(COMPATIBILITY_ROOT)
        if case.is_conflict
        and any(
            dim.get("axis") == "business"
            for entity in case.model.entities
            for dim in entity.as_of_attributes
        )
    ]


def test_bitemporal_conflict_close_input_holds_for_authored_cases() -> None:
    cases = _bitemporal_conflict_close_cases()
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-bitemp-write-004",
        "m-bitemp-write-005",
    }
    for case in cases:
        # Must not raise: the close ① derives [at, pk, infinity, businessFrom,
        # observedInZ] — the metamodel names the from_z discriminator column, ①
        # supplies its VALUE (businessFrom), which the metamodel cannot know.
        _assert_conflict_input(case, "postgres")


def test_bitemporal_conflict_close_business_from_corruption_is_rejected() -> None:
    case = next(
        c
        for c in _bitemporal_conflict_close_cases()
        if c.path.stem.startswith("m-bitemp-write-004")
    )
    # Corrupt the business discriminator VALUE: the DERIVED from_z gate bind no longer
    # matches the golden bind, so the bitemporal close ① ↔ ② gate MUST fail.
    case.when["write"]["businessFrom"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_conflict_input(case, "postgres")


def test_rectangle_split_has_inactivate_plus_three_inserts() -> None:
    update_until = next(
        c for c in _phase8_cases() if "update-until" in c.tags and c.is_write_sequence
    )
    # The updateUntil step is 4 statements: 1 inactivate UPDATE + head/middle/tail
    # inserts. With the leading insert that opens the original, 5 statements total.
    step = next(s for s in update_until.write_sequence if s["mutation"] == "updateUntil")
    assert step["statements"] == 4
    assert len(update_until.golden_statements("postgres")) == 5
