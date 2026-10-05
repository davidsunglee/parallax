"""Unit tests for the m-opt-lock machinery (no database).

These pin the DB-free invariants of optimistic-lock conflict cases: a conflict
case is discovered and self-describes (carries `then.affectedRows`, an optional
`given.apply`, and a single golden write), and the conflict / success counts are
0 / 1. The full execute-and-assert behavior is exercised end to end against real
Postgres by the compatibility suite.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from reference_harness.case import discover_cases
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_runner import _assert_conflict_input, _assert_schema
from reference_harness.write_plan import has_version_gate

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
    assert cases, "no conflict (m-opt-lock) cases discovered"
    for case in cases:
        # A conflict case carries then.affectedRows and no query/scenario.
        assert "objectQuery" not in case.when
        assert not case.is_scenario
        assert not case.is_write_sequence
        if case.attempts:
            # Retry form: the golden write + affected count live per attempt.
            for attempt in case.attempts:
                assert attempt["affectedRows"] is not None
                assert attempt["statements"]
        else:
            # Single form: one golden write per dialect + a then.affectedRows count.
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


def test_conflict_write_rows_normalizes_both_authored_forms() -> None:
    single = [c for c in _conflict_cases() if isinstance(c.when.get("write"), dict)]
    assert single, "no single-row conflict case discovered"
    for case in single:
        assert case.write_rows == [case.when["write"]]
    # The array form has no corpus witness: a conflict attempt is settled
    # against a value a read published, and a multi-key shortfall needs the
    # read to have answered fewer rows than the write addresses — a state
    # correct locking makes unreachable. The normalization stays, because it is
    # what makes "one authored form per row count" true of the reader rather
    # than of the cases that happen to exist.
    case = copy.deepcopy(single[0])
    case.when["write"] = [dict(single[0].when["write"]), {"id": 999}]
    assert case.write_rows == list(case.when["write"])


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
            if isinstance(c.when.get("write"), dict) and "observedVersion" in c.when["write"]
        )
    )
    # Corrupt the observed version in ①: the derived advance (`observedVersion + 1`)
    # AND the trailing gate bind no longer agree with the authored golden binds, so
    # the ① ↔ ② consistency gate MUST fail (it no longer rests on a golden parse).
    case.when["write"]["observedVersion"] = case.when["write"]["observedVersion"] + 5
    with pytest.raises(CaseFailure):
        _assert_conflict_input(case, "postgres")


def test_conflict_input_gate_presence_follows_the_declared_mode() -> None:
    cases = _versioned_conflict_cases()
    # Every versioned conflict the corpus still authors runs in `optimistic`: a
    # conflict attempt settles against a value a read published, and a Locking
    # target's write is licensed only by a read of its own transaction, which no
    # concurrent writer can be interposed after. The Locking arm of gate presence
    # is graded by the writeSequence cases that render it (`m-opt-lock-002`) and
    # by the Python interface's own planner suites.
    assert {c.concurrency_mode for c in cases} == {"optimistic"}
    for case in cases:
        flipped = copy.deepcopy(case)
        flipped.when["uow"] = {**flipped.uow, "concurrency": "locking"}
        # Gate presence is decided by the declared concurrency mode ALONE, so
        # flipping the mode desyncs ① from ② for EVERY authored versioned
        # conflict whichever verb it writes: the golden now renders a gate the
        # mode forbids.
        with pytest.raises(CaseFailure):
            _assert_conflict_input(flipped, "postgres")


# --- gate detection (m-opt-lock "the gate binds last") ---------------------------
#
# Whether a statement gates is a decision about its OUTER predicate alone. Three
# other places name the version column and are not a gate — an `UPDATE`'s own SET
# clause, a nested subquery's `WHERE`, and (under a quoting dialect) the same
# column under a different surface — so the decision is made on the parsed tree.
# These drive `has_version_gate` directly with the shapes a text scan gets wrong.


@pytest.mark.parametrize(
    ("dialect", "statement"),
    [
        ("postgres", 'update account set balance = ? where id = ? and "version" = ?'),
        ("mariadb", "update account set balance = ? where id = ? and `version` = ?"),
    ],
    ids=["postgres-double-quoted", "mariadb-backticked"],
)
def test_a_quoted_version_column_is_still_the_gate(dialect: str, statement: str) -> None:
    assert has_version_gate(statement, "version", dialect)


def test_a_subquery_predicate_is_not_the_outer_gate() -> None:
    # The last ` where ` in the text belongs to the SELECT, and its `version = ?` is a
    # conjunct of that inner predicate — the outer UPDATE renders no gate at all.
    statement = (
        "update account set balance = ? where id in (select id from staging where version = ?)"
    )
    assert not has_version_gate(statement, "version", "postgres")


def test_an_outer_gate_followed_by_a_subquery_is_still_detected() -> None:
    # The gate is a top-level conjunct even when a subquery sits beside it, so gate
    # detection cannot depend on the gate being the statement's trailing text.
    statement = (
        "update account set balance = ? "
        "where id in (select id from staging where owner = ?) and version = ?"
    )
    assert has_version_gate(statement, "version", "postgres")


def test_a_set_clause_version_advance_is_not_a_gate() -> None:
    # The framework-derived advance is written in BOTH modes, so reading it as a gate
    # would report every versioned update gated and silently defeat the mode check.
    statement = "update account set balance = ?, version = ? where id = ?"
    assert not has_version_gate(statement, "version", "postgres")


def test_a_column_merely_ending_in_the_version_name_is_not_the_gate() -> None:
    statement = "update account set balance = ? where id = ? and prior_version = ?"
    assert not has_version_gate(statement, "version", "postgres")


def test_an_unparsable_statement_carries_no_gate() -> None:
    assert not has_version_gate("update account set where and", "version", "postgres")


def test_observed_edge_entitlement_holds_for_every_authored_conflict_case() -> None:
    cases = _conflict_cases()
    assert cases, "no conflict (m-opt-lock) case discovered"
    for case in cases:
        # Must not raise: every authored conflict case either names no observed
        # milestone at all, or names one on a Bitemporal single-attempt close.
        _assert_schema(case)
        _assert_conflict_input(case, "postgres")


def test_a_non_temporal_conflict_target_may_not_name_an_observed_milestone() -> None:
    case = copy.deepcopy(_versioned_conflict_cases()[0])
    case.when["observedValidStart"] = "2024-01-01T00:00:00+00:00"
    # A versioned target holds one row per key and no milestone to observe, so
    # the coordinate is read by nothing: the versioned cross-check never looks at
    # it, and the case would grade a claim it never made.
    with pytest.raises(CaseFailure, match=re.escape("no milestone to observe")):
        _assert_schema(case)


def test_a_non_temporal_conflict_target_may_not_name_an_observed_gate_either() -> None:
    case = copy.deepcopy(_versioned_conflict_cases()[0])
    case.when["observedTxStart"] = "2024-01-01T00:00:00+00:00"
    # The gate half is unentitled for the same reason as the Valid-Time half: a
    # versioned close gates on `write.observedVersion`, so the milestone
    # coordinate reaches nothing that could read it.
    with pytest.raises(CaseFailure, match=re.escape("no milestone to observe")):
        _assert_schema(case)


def test_a_non_temporal_retry_attempt_may_not_name_an_observed_gate() -> None:
    case = copy.deepcopy(_versioned_conflict_cases()[0])
    case.when["attempts"] = [
        {
            "statements": case.when.get("statements", []),
            "affectedRows": 1,
            "write": {"id": 1, "observedVersion": 1},
            "observedTxStart": "2024-01-01T00:00:00+00:00",
        }
    ]
    # The entitlement is a property of the target, so it holds wherever the
    # coordinate is spelled — the attempt's own fields included.
    with pytest.raises(CaseFailure, match=re.escape("no milestone to observe")):
        _assert_schema(case)
