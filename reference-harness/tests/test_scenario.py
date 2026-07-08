"""Unit tests for the Phase 6 (m-unit-work) scenario machinery (no database).

These pin the DB-free invariants of a cache / identity scenario case: the
per-step round-trip / golden-SQL count consistency (each step's declared
roundTrips equals the golden SQL statements it lists; the steps total the
case-level roundTrips), and that a cache-hit step lists no golden SQL. The full
execute-and-assert behavior (cache-hit reuse, identity, read-lock, batched write)
is exercised end-to-end against real Postgres by the compatibility suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import discover_cases
from reference_harness.case_runner import (
    CaseFailure,
    _assert_scenario_count_consistency,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _scenario_cases():
    return [c for c in discover_cases(COMPATIBILITY_ROOT) if c.is_scenario]


def test_scenario_cases_are_discovered_and_self_describe() -> None:
    cases = _scenario_cases()
    assert cases, "no scenario cases discovered"
    for case in cases:
        # Each carries a scenario (ordered steps) and no top-level operation.
        assert case.scenario
        assert "operation" not in case.when
        for step in case.scenario:
            assert "roundTrips" in step
            # A step is EITHER a read step (carries `find`) or a write step
            # (carries `write`), never both.
            assert ("find" in step) ^ ("write" in step)
            if "write" in step:
                # A committed / rolled-back write lists golden DML; a NO-OP write
                # (a versioned UPDATE that changes no attribute, m-opt-lock) issues no DML,
                # so it declares roundTrips 0 and lists none — like a cache hit.
                if step["roundTrips"] == 0:
                    assert not step.get("statements"), "a no-op write step lists no golden DML"
                else:
                    assert step.get("statements"), (
                        "a write step with round trips must list golden DML"
                    )


def test_cache_hit_scenario_has_a_zero_round_trip_step() -> None:
    case = next(c for c in _scenario_cases() if "cache-hit" in c.tags)
    # A cache-hit scenario must contain a step that costs zero round trips and
    # lists no golden SQL (it is served from the query cache).
    hits = [s for s in case.scenario if s["roundTrips"] == 0]
    assert hits, "cache-hit scenario has no zero-round-trip (hit) step"
    for hit in hits:
        assert not hit.get("statements"), "a cache-hit step must list no golden SQL"


def test_rollback_scenario_step_is_discovered_and_self_describes() -> None:
    case = next(
        (c for c in _scenario_cases() if any(step.get("rollback") for step in c.scenario)),
        None,
    )
    assert case is not None, "no rollback scenario case discovered (m-unit-work-002)"
    rollback_steps = [step for step in case.scenario if step.get("rollback")]
    for step in rollback_steps:
        # An ABORTED write step is still a write step that lists golden DML (it is
        # applied then rolled back) and declares its round trips (the DML executes).
        assert "write" in step
        assert step.get("statements"), "a rollback write step must list golden DML"
        assert step["roundTrips"] >= 1
    # The rolled-back step's statements are counted as round trips exactly like a
    # committed write, so the count-consistency check MUST still hold.
    _assert_scenario_count_consistency(case, "postgres")


def test_no_op_write_scenario_step_is_discovered_and_self_describes() -> None:
    case = next(
        (
            c
            for c in _scenario_cases()
            if any("write" in step and step["roundTrips"] == 0 for step in c.scenario)
        ),
        None,
    )
    assert case is not None, "no no-op-write scenario case discovered (m-opt-lock-001)"
    no_op_steps = [s for s in case.scenario if "write" in s and s["roundTrips"] == 0]
    for step in no_op_steps:
        # A NO-OP write (a versioned UPDATE that changes no attribute, m-opt-lock) issues
        # NO DML: it lists no golden SQL and costs zero round trips, mirroring a
        # cache-hit read step.
        assert not step.get("statements"), "a no-op write step must list no golden DML"
    # The zero-round-trip write step keeps the count-consistency check green.
    _assert_scenario_count_consistency(case, "postgres")


def _scenario_by_id(prefix: str):
    return next(c for c in _scenario_cases() if c.path.stem.startswith(prefix))


def test_read_your_own_writes_update_scenario_flushes_before_dependent_find() -> None:
    # m-unit-work-005: a committed UPDATE followed by a dependent find that MUST observe
    # the new value (read-your-own-writes for UPDATE).
    case = _scenario_by_id("m-unit-work-005")
    write, find = case.scenario
    assert "write" in write and write["write"] == "update"
    update_sql = write["statements"][0]["sql"]["postgres"]
    assert update_sql.startswith("update account set")
    assert "find" in find
    # The dependent find asserts the flushed new balance/version (the RYOW observable).
    assert find["expectRows"] == [{"id": 1, "owner": "Ada", "balance": 175.00, "version": 2}]
    _assert_scenario_count_consistency(case, "postgres")


def test_read_your_own_writes_delete_scenario_observes_absence() -> None:
    # m-unit-work-006: a committed DELETE followed by a dependent find that MUST observe
    # the row's ABSENCE (read-your-own-writes for DELETE).
    case = _scenario_by_id("m-unit-work-006")
    write, find = case.scenario
    assert "write" in write and write["write"] == "delete"
    assert write["statements"][0]["sql"]["postgres"] == "delete from account where id = ?"
    # The dependent find returns ZERO rows — the deletion is visible.
    assert find["expectRows"] == []
    _assert_scenario_count_consistency(case, "postgres")


def test_insert_update_combining_scenario_emits_exactly_one_insert() -> None:
    # m-unit-work-008: a buffered insert + a buffered update of the same new object
    # COMBINE into exactly ONE INSERT with the final values — no intervening UPDATE.
    case = _scenario_by_id("m-unit-work-008")
    write = case.scenario[0]
    assert "write" in write
    statements = write["statements"]
    assert len(statements) == 1, "combining must emit exactly one statement"
    sql = statements[0]["sql"]["postgres"]
    assert sql.startswith("insert into account") and "update" not in sql
    # The single INSERT carries the FINAL (post-combine) balance, not the initial one.
    assert statements[0]["binds"] == [8, "Turing", 99.00, 1]
    _assert_scenario_count_consistency(case, "postgres")


def test_scenario_count_consistency_holds_for_authored_cases() -> None:
    for case in _scenario_cases():
        # Must not raise: per-step counts match the golden SQL and total roundTrips.
        _assert_scenario_count_consistency(case, "postgres")


def test_scenario_step_count_mismatch_is_rejected() -> None:
    case = next(iter(_scenario_cases()))
    # Corrupt a step's declared roundTrips so it no longer matches the golden SQL
    # statement count it lists; the consistency check MUST fail.
    case.when["scenario"][0]["roundTrips"] += 1
    with pytest.raises(CaseFailure):
        _assert_scenario_count_consistency(case, "postgres")


def test_scenario_total_mismatch_is_rejected() -> None:
    case = next(iter(_scenario_cases()))
    # Corrupt the case-level roundTrips so it no longer equals the per-step sum.
    case.then["roundTrips"] += 1
    with pytest.raises(CaseFailure):
        _assert_scenario_count_consistency(case, "postgres")
