"""Unit tests for the Phase 11 cross-process coherence runner logic, DB-free.

The end-to-end two-node observation (node B re-fetches node A's committed write)
runs against a real database in the compatibility suite (``-k coherence``). These
tests cover the dialect-agnostic seam logic that needs no database: the case shape
is recognized, its per-step golden SQL is canonical, its read-step operations
survive the serde round-trip, and a missing assertion is rejected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import Case, discover_cases, load_case
from reference_harness.case_runner import (
    CaseFailure,
    _assert_coherence_normalization,
    _assert_schema,
    _assert_serde,
    _coherence_has_golden,
    _coherence_step_statements,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

COHERENCE_CASES = [
    case for case in discover_cases(COMPATIBILITY_ROOT) if case.is_coherence
]


def test_coherence_cases_exist() -> None:
    assert COHERENCE_CASES, "no coherence cases discovered (expected 11xx-*.yaml)"


@pytest.mark.parametrize("case", COHERENCE_CASES, ids=lambda c: c.path.stem)
def test_coherence_case_is_well_formed(case: Case) -> None:
    # Recognized as a coherence case and structurally valid.
    assert case.is_coherence
    _assert_schema(case)
    # The final step is a node-B re-fetch that asserts observeRows.
    last = case.coherence[-1]
    assert last["node"] == "B"
    assert last["kind"] == "read"
    assert "observeRows" in last


@pytest.mark.parametrize("case", COHERENCE_CASES, ids=lambda c: c.path.stem)
def test_coherence_has_a_write_step(case: Case) -> None:
    # A coherence case must commit a write on node A that node B then observes.
    writers = [s for s in case.coherence if s["kind"] == "write" and s["node"] == "A"]
    assert writers, f"{case.path.name}: coherence case has no node-A write step"


@pytest.mark.parametrize("case", COHERENCE_CASES, ids=lambda c: c.path.stem)
def test_coherence_golden_is_canonical_per_dialect(case: Case) -> None:
    for dialect in ("postgres", "mariadb"):
        if _coherence_has_golden(case, dialect):
            # Each step's golden SQL is a fixed point of M3 normalization.
            _assert_coherence_normalization(case, dialect)


@pytest.mark.parametrize("case", COHERENCE_CASES, ids=lambda c: c.path.stem)
def test_coherence_read_operations_roundtrip(case: Case) -> None:
    # Layer 4: every read step's operation (and the descriptor) survives serde.
    _assert_serde(case)


def test_step_statements_handles_single_and_missing() -> None:
    step_single = {"goldenSql": {"postgres": "select 1"}}
    assert _coherence_step_statements(step_single, "postgres") == ["select 1"]
    # A write step with no golden SQL for a dialect yields nothing.
    assert _coherence_step_statements({"goldenSql": {}}, "postgres") == []
    assert _coherence_step_statements({}, "postgres") == []


def test_coherence_without_assertion_is_rejected() -> None:
    # A coherence case whose steps assert nothing fails the structural check.
    bogus = Case(
        path=Path("bogus-coherence.yaml"),
        raw={
            "model": "models/account.yaml",
            "tags": ["coherence"],
            "coherence": [
                {"node": "A", "kind": "write", "goldenSql": {"postgres": "select 1"}},
                {"node": "B", "kind": "read", "goldenSql": {"postgres": "select 1"}},
            ],
        },
        model=load_case(
            COMPATIBILITY_ROOT, COMPATIBILITY_ROOT / "cases" / "1101-coherence-refetch.yaml"
        ).model,
    )
    with pytest.raises(CaseFailure):
        _assert_schema(bogus)
