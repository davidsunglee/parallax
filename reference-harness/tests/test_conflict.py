"""Unit tests for the Phase 7 (M9 / M10) machinery (no database).

These pin the DB-free invariants of the lifecycle-detach (M9) write-sequence
cases and the optimistic-lock (M10) conflict cases: a conflict case is
discovered and self-describes (carries `expectedAffectedRows`, an optional
`precondition`, and a single golden UPDATE); the conflict / success counts are 0
/ 1; and the M9 detached-update case opts into `loadFixtures`. The full
execute-and-assert behavior (precondition + golden UPDATE, affected-row count,
merge-back table state) is exercised end-to-end against real Postgres by the
compatibility suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import discover_cases
from reference_harness.case_runner import CaseFailure, _assert_conflict_input

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


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


def test_conflict_cases_are_discovered_and_self_describe() -> None:
    cases = _conflict_cases()
    assert cases, "no conflict (M10) cases discovered"
    for case in cases:
        # A conflict case carries expectedAffectedRows and no operation/scenario.
        assert "operation" not in case.raw
        assert not case.is_scenario
        assert not case.is_write_sequence
        if case.attempts:
            # Retry form: the golden UPDATE + affected count live per attempt.
            for attempt in case.attempts:
                assert attempt["expectedAffectedRows"] is not None
                assert attempt["goldenSql"]
        else:
            # Single form: one golden UPDATE per dialect + a top-level count.
            assert case.expected_affected_rows is not None
            for dialect in case.golden_sql:
                assert len(case.golden_statements(dialect)) == 1


def test_retry_conflict_sequence_self_describes() -> None:
    cases = [c for c in _conflict_cases() if c.attempts]
    assert cases, "no M10 retry-conflict (attempts) case discovered"
    for case in cases:
        # The retry contract: a stale-version attempt affects 0, then a fresh-
        # version retry affects 1. Both outcomes must appear, in that order.
        outcomes = [a["expectedAffectedRows"] for a in case.attempts]
        assert 0 in outcomes and 1 in outcomes
        assert outcomes.index(0) < outcomes.index(1)


def test_conflict_and_success_counts_present() -> None:
    cases = _conflict_cases()
    counts = {c.expected_affected_rows for c in cases}
    # The optimistic-lock pair: a conflict affects 0 rows, a success affects 1.
    assert 0 in counts, "no optimistic-lock conflict case (expectedAffectedRows 0)"
    assert 1 in counts, "no optimistic-lock success case (expectedAffectedRows 1)"


def test_conflict_case_precondition_is_optional_but_present_for_the_conflict() -> None:
    conflict = next(c for c in _conflict_cases() if c.expected_affected_rows == 0)
    # The conflict case simulates a concurrent writer via an out-of-band precondition.
    assert conflict.precondition, "conflict case must carry a precondition"
    success = next(c for c in _conflict_cases() if c.expected_affected_rows == 1)
    # The success case has no concurrent writer.
    assert not success.precondition


def test_conflict_input_holds_for_authored_versioned_cases() -> None:
    cases = _versioned_conflict_cases()
    assert cases, "no versioned conflict (M10) case discovered"
    for case in cases:
        # Must not raise: each authored ① `write` (single form) / per-attempt `write`
        # (retry form) classifies against the model to the golden's SET column list
        # (+ the derived version) and its binds (advance `observedVersion + 1`, pk,
        # gate `observedVersion`) — a genuine ① ↔ ② cross-check, not a golden parse.
        _assert_conflict_input(case, "postgres")


def test_conflict_input_observed_version_corruption_is_rejected() -> None:
    case = next(
        c
        for c in _versioned_conflict_cases()
        if isinstance(c.raw.get("write"), dict) and "observedVersion" in c.raw["write"]
    )
    # Corrupt the observed version in ①: the derived advance (`observedVersion + 1`)
    # AND the trailing gate bind no longer agree with the authored golden binds, so
    # the ① ↔ ② consistency gate MUST fail (it no longer rests on a golden parse).
    case.raw["write"]["observedVersion"] = case.raw["write"]["observedVersion"] + 5
    with pytest.raises(CaseFailure):
        _assert_conflict_input(case, "postgres")


def test_detached_update_loads_fixtures() -> None:
    detached_updates = [c for c in _cases() if c.is_write_sequence and "detached-update" in c.tags]
    assert detached_updates, "no M9 detached-update write-sequence case discovered"
    for case in detached_updates:
        # The original persisted row must exist before the merge-back UPDATE.
        assert case.load_fixtures
