"""Unit tests for the Phase 7 (m-detach / m-opt-lock) machinery (no database).

These pin the DB-free invariants of the lifecycle-detach (m-detach) write-sequence
cases and the optimistic-lock (m-opt-lock) conflict cases: a conflict case is
discovered and self-describes (carries `then.affectedRows`, an optional
`given.apply`, and a single golden UPDATE); the conflict / success counts are 0
/ 1; and the m-detach detached-update case opts into `given.fixtures`. The full
execute-and-assert behavior (given.apply + golden UPDATE, affected-row count,
merge-back table state) is exercised end-to-end against real Postgres by the
compatibility suite.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from reference_harness.case import discover_cases
from reference_harness.case_runner import (
    CaseFailure,
    _assert_conflict_input,
    _assert_scenario_conflict_abort,
    _entry_pairs,
    _has_version_gate,
    _scenario_root_entity,
    _version_column,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _case_id(stem: str) -> str:
    """The per-module id prefix of a case stem (drops the trailing ``-<slug>``)."""
    return re.match(r"(m-[a-z0-9-]+-\d{3})", stem).group(1)


def _cases():
    return discover_cases(COMPATIBILITY_ROOT)


def _conflict_cases():
    return [c for c in _cases() if c.is_conflict]


def _versioned_conflict_cases():
    """Conflict cases whose model carries an explicit optimistic-lock version."""
    return [
        c
        for c in _conflict_cases()
        if any(a.get("optimisticLocking") for e in c.model.entities for a in e.attributes)
    ]


def _temporal_conflict_close_cases():
    """Processing-only temporal conflict-close cases (no version, no business axis).

    The audit-only optimistic / locking closes (`m-temporal-read-009` through
    `m-temporal-read-012`) gate on the observed processing-from (`in_z`), never a
    version column. The bitemporal closes (`m-bitemp-write-004` / `m-bitemp-write-005`)
    carry a business axis too and are pinned in `test_bitemporal`.
    """
    cases = []
    for case in _conflict_cases():
        entities = case.model.entities
        has_version = any(a.get("optimisticLocking") for e in entities for a in e.attributes)
        axes = {dim.get("axis") for e in entities for dim in e.as_of_attributes}
        if not has_version and "processing" in axes and "business" not in axes:
            cases.append(case)
    return cases


def test_conflict_cases_are_discovered_and_self_describe() -> None:
    cases = _conflict_cases()
    assert cases, "no conflict (m-opt-lock) cases discovered"
    for case in cases:
        # A conflict case carries then.affectedRows and no operation/scenario.
        assert "operation" not in case.when
        assert not case.is_scenario
        assert not case.is_write_sequence
        if case.attempts:
            # Retry form: the golden UPDATE + affected count live per attempt.
            for attempt in case.attempts:
                assert attempt["affectedRows"] is not None
                assert attempt["statements"]
        else:
            # Single form: one golden UPDATE per dialect + a then.affectedRows count.
            assert case.expected_affected_rows is not None
            for dialect in case.golden_dialects:
                assert len(case.golden_statements(dialect)) == 1


def test_retry_conflict_sequence_self_describes() -> None:
    cases = [c for c in _conflict_cases() if c.attempts]
    assert cases, "no m-opt-lock retry-conflict (attempts) case discovered"
    for case in cases:
        # The retry contract: a stale-version attempt affects 0, then a fresh-
        # version retry affects 1. Both outcomes must appear, in that order.
        outcomes = [a["affectedRows"] for a in case.attempts]
        assert 0 in outcomes and 1 in outcomes
        assert outcomes.index(0) < outcomes.index(1)


def test_conflict_and_success_counts_present() -> None:
    cases = _conflict_cases()
    counts = {c.expected_affected_rows for c in cases}
    # The optimistic-lock pair: a conflict affects 0 rows, a success affects 1.
    assert 0 in counts, "no optimistic-lock conflict case (expectedAffectedRows 0)"
    assert 1 in counts, "no optimistic-lock success case (expectedAffectedRows 1)"


def test_conflict_case_apply_is_optional_but_present_for_the_conflict() -> None:
    conflict = next(c for c in _conflict_cases() if c.expected_affected_rows == 0)
    # The conflict case simulates a concurrent writer via an out-of-band given.apply.
    assert conflict.apply, "conflict case must carry a given.apply"
    success = next(c for c in _conflict_cases() if c.expected_affected_rows == 1)
    # The success case has no concurrent writer.
    assert not success.apply


def test_conflict_input_holds_for_authored_versioned_cases() -> None:
    cases = _versioned_conflict_cases()
    assert cases, "no versioned conflict (m-opt-lock) case discovered"
    for case in cases:
        # Must not raise: each authored ① `write` (single form) / per-attempt `write`
        # (retry form) classifies against the model to the golden's SET column list
        # (+ the derived version) and its binds (advance `observedVersion + 1`, pk,
        # gate `observedVersion`) — a genuine ① ↔ ② cross-check, not a golden parse.
        _assert_conflict_input(case, "postgres")


def test_conflict_input_observed_version_corruption_is_rejected() -> None:
    case = copy.deepcopy(
        next(
            c
            for c in _versioned_conflict_cases()
            if isinstance(c.write, dict) and "observedVersion" in c.write
        )
    )
    # Corrupt the observed version in ①: the derived advance (`observedVersion + 1`)
    # AND the trailing gate bind no longer agree with the authored golden binds, so
    # the ① ↔ ② consistency gate MUST fail (it no longer rests on a golden parse).
    case.when["write"]["observedVersion"] = case.when["write"]["observedVersion"] + 5
    with pytest.raises(CaseFailure):
        _assert_conflict_input(case, "postgres")


def test_temporal_conflict_close_input_holds_for_authored_cases() -> None:
    cases = _temporal_conflict_close_cases()
    # The Phase 4 processing-axis close family all carry ① (write + at [+ observedInZ]);
    # COR-26 adds m-audit-write-006, the SAME gated close tagged under m-audit-write.
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-temporal-read-009",
        "m-temporal-read-010",
        "m-temporal-read-011",
        "m-temporal-read-012",
        "m-audit-write-006",
    }
    for case in cases:
        # Must not raise: each close ① derives out_z = at (+ the in_z = observedInZ gate
        # in optimistic mode) and cross-checks the derived binds against the golden
        # binds — a binds-only ① ↔ ② check (the SET column out_z stays metamodel-fixed).
        _assert_conflict_input(case, "postgres")


def test_audit_write_optimistic_gated_close_binds_in_z_gate() -> None:
    # m-audit-write-006 witnesses the OPTIMISTIC-gated close of an audit-only chaining
    # update: a single gated close UPDATE keyed on the observed processing-from (in_z),
    # with no business discriminator (balance has no business axis). It is the audit-only
    # analogue of the bitemporal gate (m-bitemp-write-004), reusing that shape.
    case = next(c for c in _conflict_cases() if c.path.stem.startswith("m-audit-write-006"))
    assert "m-audit-write" in case.tags and "m-opt-lock" in case.tags
    assert case.concurrency_mode == "optimistic"
    assert case.observed_in_z is not None  # the in_z gate token
    assert case.expected_affected_rows == 1  # the gate MATCHES the observed milestone
    (statement,) = case.golden_statements("postgres")
    # The gated audit close carries the `and in_z = ?` gate but NO business `from_z`
    # gate (audit-only), unlike the bitemporal close.
    assert "in_z = ?" in statement
    assert "from_z" not in statement
    # Must not raise: the derived close binds [at, pk, infinity, observedInZ] cross-check
    # the golden binds.
    _assert_conflict_input(case, "postgres")


def test_temporal_conflict_close_observed_in_z_corruption_is_rejected() -> None:
    case = copy.deepcopy(
        next(
            c
            for c in _temporal_conflict_close_cases()
            if c.path.stem.startswith("m-temporal-read-009")
        )
    )
    # Corrupt the observed in_z gate token: the DERIVED `and in_z = ?` gate bind no
    # longer matches the golden gate bind, so the ① ↔ ② temporal-close gate MUST fail
    # (the gate value is derived from `observedInZ`, never read from the golden).
    case.when["observedInZ"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_conflict_input(case, "postgres")


def test_temporal_conflict_close_retry_gates_each_attempt() -> None:
    case = copy.deepcopy(
        next(
            c
            for c in _temporal_conflict_close_cases()
            if c.path.stem.startswith("m-temporal-read-011")
        )
    )
    # The retry form carries a close ① per attempt; corrupting the retry attempt's
    # observed in_z desyncs its derived gate bind from the golden, so the per-attempt
    # ① ↔ ② gate MUST fail.
    case.when["attempts"][1]["observedInZ"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_conflict_input(case, "postgres")


def test_detached_update_loads_fixtures() -> None:
    detached_updates = [c for c in _cases() if c.is_write_sequence and "detached-update" in c.tags]
    assert detached_updates, "no m-detach detached-update write-sequence case discovered"
    for case in detached_updates:
        # The original persisted row must exist before the merge-back UPDATE.
        assert case.load_fixtures


# --- conflict-abort scenario helper (m-opt-lock-012, m-opt-lock + m-unit-work) ---
#
# `_assert_scenario_conflict_abort` is the DB-free guard that makes a rolled-back
# unit of work a CONSEQUENCE of a detected optimistic-lock conflict, not a vacuous
# abort. These pin its accept/reject decision directly (no Docker), driving it with
# the REAL m-opt-lock-012 case so `concurrency_mode`, `expected_affected_rows`, the
# root entity, and the version column all resolve authentically. The full
# execute-and-rollback behavior is exercised end-to-end against real Postgres by the
# compatibility suite.


def _conflict_abort_scenario():
    """The real m-opt-lock-012 case + its conflict-abort step, split into gated / non-gated.

    The version-gated write (the conflicting `... and version = ?` UPDATE) and the
    non-gated write(s) are resolved from the case's OWN scenario statements via the
    SAME version column the harness gates on (`_version_column` over the scenario root
    entity), so the `executed` lists below are built from authentic golden SQL rather
    than hand-typed strings.
    """
    case = next(c for c in _cases() if c.path.stem.startswith("m-opt-lock-012"))
    index, step = next((i, s) for i, s in enumerate(case.scenario) if s.get("rollback"))
    version_col = _version_column(_scenario_root_entity(case))
    assert version_col is not None, "the scenario root entity must carry a version column"
    statements = [sql for sql, _binds in _entry_pairs(step.get("statements"), "postgres")]
    gated = [sql for sql in statements if _has_version_gate(sql, version_col)]
    non_gated = [sql for sql in statements if not _has_version_gate(sql, version_col)]
    # The authored abort step lists exactly one gated write and at least one non-gated
    # write (the buffered insert), so the corruptions below are well-formed.
    assert len(gated) == 1 and non_gated, "m-opt-lock-012 abort step shape changed"
    return case, index, gated[0], non_gated


def test_conflict_abort_helper_holds_for_the_authored_conflict() -> None:
    # Positive anchor (c): the REAL version-gated write paired with the conflict count
    # (0 rows — a stale-version gate that matched nothing, `updatedRows != 1`) MUST
    # pass. The helper accepts the genuine conflict, so the rejections below prove it
    # bites only the corruptions, not everything.
    case, index, gated_sql, non_gated = _conflict_abort_scenario()
    executed = [(sql, 1) for sql in non_gated] + [(gated_sql, 0)]
    # Must not raise: affected 0 == then.affectedRows 0, so the abort is a consequence
    # of a detected conflict.
    _assert_scenario_conflict_abort(case, index, executed)


def test_conflict_abort_rejects_fresh_gated_update_affecting_one_row() -> None:
    # (a) a version-gated write that affected 1 row is NO conflict — `updatedRows != 1`
    # is the conflict signal, so a rollback on a NON-conflicting gated write MUST fail
    # the case rather than pass on the abort alone.
    case, index, gated_sql, non_gated = _conflict_abort_scenario()
    executed = [(sql, 1) for sql in non_gated] + [(gated_sql, 1)]
    with pytest.raises(CaseFailure):
        _assert_scenario_conflict_abort(case, index, executed)


def test_conflict_abort_rejects_missing_gated_update() -> None:
    # (b) an aborted step whose executed writes list NO version-gated write (only the
    # non-gated buffered insert) never detected a conflict — the helper MUST fail
    # ("exactly one version-gated write, found 0"), so a vacuous abort cannot pass.
    case, index, _gated_sql, non_gated = _conflict_abort_scenario()
    executed = [(sql, 1) for sql in non_gated]
    with pytest.raises(CaseFailure):
        _assert_scenario_conflict_abort(case, index, executed)


def test_conflict_abort_rejects_non_optimistic_unit_of_work() -> None:
    # A `then.affectedRows` conflict signal requires the version gate: if the unit of
    # work is not `concurrency: optimistic`, there is no gate to conflict on, so the
    # helper MUST reject even the genuine 0-row conflict shape.
    case, index, gated_sql, non_gated = _conflict_abort_scenario()
    case = copy.deepcopy(case)
    case.when["uow"]["concurrency"] = "locking"
    assert case.concurrency_mode != "optimistic"
    executed = [(sql, 1) for sql in non_gated] + [(gated_sql, 0)]
    with pytest.raises(CaseFailure):
        _assert_scenario_conflict_abort(case, index, executed)


def test_conflict_abort_rejects_affected_rows_one_as_no_conflict() -> None:
    # A conflict-abort scenario MUST declare a `!= 1` count (0 for a stale-version
    # gate): then.affectedRows == 1 is NOT a conflict, so the helper rejects it before
    # ever inspecting the executed writes.
    case, index, gated_sql, non_gated = _conflict_abort_scenario()
    case = copy.deepcopy(case)
    case.then["affectedRows"] = 1
    executed = [(sql, 1) for sql in non_gated] + [(gated_sql, 1)]
    with pytest.raises(CaseFailure):
        _assert_scenario_conflict_abort(case, index, executed)
