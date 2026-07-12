"""Unit tests for the Phase 6 (m-unit-work) scenario machinery (no database).

These pin the DB-free invariants of a cache / identity scenario case: the
per-step round-trip / golden-SQL count consistency (each step's declared
roundTrips equals the golden SQL statements it lists; the steps total the
case-level roundTrips), and that a cache-hit step lists no golden SQL. The full
execute-and-assert behavior (cache-hit reuse, identity, read-lock, batched write)
is exercised end-to-end against real Postgres by the compatibility suite.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from reference_harness.case import discover_cases
from reference_harness.case_runner import (
    CaseFailure,
    _assert_action_on,
    _assert_scenario_count_consistency,
    _assert_scenario_normalization,
    _assert_scenario_reference_sql,
    _assert_scenario_sql_bookkeeping,
    _reuse_prior_rows,
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
            # A step is EXACTLY ONE of a read step (carries `find`), a write step
            # (carries `write`), or a lifecycle-action step (carries `action`,
            # m-case-format COR-30).
            kinds = ("find" in step) + ("write" in step) + ("action" in step)
            assert kinds == 1, "a scenario step is exactly one of find / write / action"
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


# --- per-scenario read reference SQL -----------------------------------------


class _ReferenceDb:
    dialect = "postgres"

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, list[object]]] = []

    def query(self, statement: str, binds: Sequence[object] = ()) -> list[dict[str, object]]:
        self.calls.append((statement, list(binds)))
        return self.rows


def test_scenario_read_reference_sql_is_a_bind_free_naive_oracle() -> None:
    case = _scenario_by_id("m-opt-lock-003")
    step = case.scenario[0]
    step["referenceSql"] = "select id from account where balance < 200.00"
    expected = [{"id": 1}, {"id": 3}]
    db = _ReferenceDb(expected)

    _assert_scenario_reference_sql(case, db, 0, step, expected)  # type: ignore[arg-type]

    assert db.calls == [("select id from account where balance < 200.00", [])]


def test_scenario_read_reference_sql_mismatch_fails_loudly() -> None:
    case = _scenario_by_id("m-opt-lock-003")
    step = case.scenario[0]
    step["referenceSql"] = "select id from account where balance < 200.00"

    with pytest.raises(CaseFailure, match="referenceSql rows != golden rows"):
        _assert_scenario_reference_sql(
            case,
            _ReferenceDb([]),  # type: ignore[arg-type]
            0,
            step,
            [{"id": 1}],
        )


def test_scenario_reference_sql_map_must_cover_its_golden_dialects() -> None:
    case = _scenario_by_id("m-opt-lock-003")
    case.scenario[0]["referenceSql"] = {"mariadb": "select id from account"}

    with pytest.raises(CaseFailure, match="referenceSql map keys"):
        _assert_scenario_sql_bookkeeping(case)


def test_scenario_read_golden_sql_must_be_canonical() -> None:
    case = _scenario_by_id("m-opt-lock-003")
    case.scenario[0]["statements"][0]["sql"]["postgres"] = "SELECT t0.id FROM account t0"

    with pytest.raises(CaseFailure, match="not canonical"):
        _assert_scenario_normalization(case, "postgres")


# --- zero-round-trip reuse: loud failure vs the ONE legitimate empty case -------
#
# `_reuse_prior_rows` must fail LOUDLY when a zero-round-trip step names a source
# that does not resolve (an empty reuse would let its identity / expectRows
# assertion pass vacuously), while still permitting the operation-backed list
# CONSTRUCTION that has not resolved yet (m-op-list-001 step 0 — no named source,
# no non-empty assertion).


def _any_case():
    """A discovered case whose `path.name` the reuse / on helpers cite in errors."""
    return next(iter(_scenario_cases()))


def test_reuse_prior_rows_permits_unresolved_construction() -> None:
    # A construction step (m-op-list-001 step 0): roundTrips 0, no golden SQL, no
    # named source, and asserts nothing — it reuses the empty set until first access.
    construction = {"find": {"all": {}}, "targetEntity": "Order", "roundTrips": 0}
    assert _reuse_prior_rows(_any_case(), construction, 0, []) == []


def test_reuse_prior_rows_raises_on_unresolved_named_source() -> None:
    # A re-access whose `on` names a step that does not exist yet: the pre-refactor
    # loud failure, restored — never a silent empty reuse.
    step = {"action": "access", "on": 5, "roundTrips": 0}
    with pytest.raises(CaseFailure):
        _reuse_prior_rows(_any_case(), step, 1, [[{"id": 1}]])


def test_reuse_prior_rows_raises_on_forward_same_object_as() -> None:
    # `sameObjectAs` pointing at the current (or a later) step cannot resolve to an
    # EARLIER result; the reuse MUST fail loudly rather than return [].
    step = {"action": "access", "on": 0, "sameObjectAs": 2, "roundTrips": 0}
    with pytest.raises(CaseFailure):
        _reuse_prior_rows(_any_case(), step, 2, [[{"id": 1}], []])


def test_reuse_prior_rows_rejects_construction_asserting_rows() -> None:
    # A no-source zero-round-trip step that asserts NON-EMPTY rows is not a valid
    # construction — a construction resolves no rows yet, so this fails loudly.
    step = {
        "find": {"all": {}},
        "targetEntity": "Order",
        "roundTrips": 0,
        "expectRows": [{"id": 1}],
    }
    with pytest.raises(CaseFailure):
        _reuse_prior_rows(_any_case(), step, 0, [])


# --- action `on` validation: earlier, in-range, unique --------------------------


def test_assert_action_on_accepts_earlier_unique_indices() -> None:
    # A coordinate-grouped load over two earlier sources, one statement group each.
    step = {"action": "load", "on": [0, 1], "path": "lines", "roundTrips": 2}
    pairs = [("select ...", [1]), ("select ...", [2])]
    _assert_action_on(_any_case(), 2, step, pairs)  # must not raise


def test_assert_action_on_rejects_forward_or_self_index() -> None:
    # `on` must name an EARLIER step — a self / forward index is an authoring error.
    step = {"action": "load", "on": 2, "path": "items", "roundTrips": 1}
    with pytest.raises(CaseFailure):
        _assert_action_on(_any_case(), 2, step, [("select ...", [])])


def test_assert_action_on_rejects_duplicate_index() -> None:
    # The array form is unique — a source is referenced at most once.
    step = {"action": "load", "on": [0, 0], "path": "lines", "roundTrips": 1}
    with pytest.raises(CaseFailure):
        _assert_action_on(_any_case(), 2, step, [("select ...", [])])


def test_assert_action_on_rejects_more_groups_than_sources() -> None:
    # A coordinate-grouped load must not run MORE statement groups than the sources
    # it references — every executed group is accounted for by a referenced source.
    step = {"action": "load", "on": [0, 1], "path": "lines", "roundTrips": 3}
    pairs = [("select ...", [1]), ("select ...", [2]), ("select ...", [3])]
    with pytest.raises(CaseFailure):
        _assert_action_on(_any_case(), 2, step, pairs)
