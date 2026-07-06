"""Unit tests for the Phase 11 cross-process coherence runner logic, DB-free.

The end-to-end two-node observation (node B re-fetches node A's committed write)
runs against a real database in the compatibility suite (``-k coherence``). These
tests cover the dialect-agnostic seam logic that needs no database: the case shape
is recognized, its per-step golden SQL is canonical, its read-step operations
survive the serde round-trip, and a missing assertion is rejected.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, discover_cases, load_case
from reference_harness.case_runner import (
    CaseFailure,
    _assert_coherence,
    _assert_coherence_identity,
    _assert_coherence_normalization,
    _assert_schema,
    _assert_serde,
    _coherence_has_golden,
    _coherence_step_statements,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

COHERENCE_CASES = [case for case in discover_cases(COMPATIBILITY_ROOT) if case.is_coherence]


class _RecordingNode:
    dialect = "postgres"

    def __init__(self, name: str, calls: list[tuple[str, str, str, list[Any]]]) -> None:
        self.name = name
        self.calls = calls

    def query(self, sql: str, binds: list[Any] | None = None) -> list[dict[str, Any]]:
        self.calls.append((self.name, "query", sql, list(binds or [])))
        return [{"marker": sql}]

    def execute(self, sql: str, binds: list[Any] | None = None) -> int:
        self.calls.append((self.name, "execute", sql, list(binds or [])))
        return 1


class _RecordingProvider(_RecordingNode):
    def __init__(self) -> None:
        super().__init__("A", [])
        self.peer = _RecordingNode("B", self.calls)

    def reset(self) -> None:
        self.calls.append((self.name, "reset", "", []))

    def apply_ddl(self, statements: list[str]) -> None:
        for statement in statements:
            self.calls.append((self.name, "apply_ddl", statement, []))

    def load(self, table: str, columns: list[str], rows: list[list[Any]]) -> None:
        self.calls.append((self.name, "load", table, [columns, rows]))

    @contextmanager
    def open_peer(self):
        yield self.peer


def test_coherence_cases_exist() -> None:
    assert COHERENCE_CASES, "no coherence cases discovered (expected m-coherence-*.yaml)"


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
            # Each step's golden SQL is a fixed point of m-sql normalization.
            _assert_coherence_normalization(case, dialect)


@pytest.mark.parametrize("case", COHERENCE_CASES, ids=lambda c: c.path.stem)
def test_coherence_read_operations_roundtrip(case: Case) -> None:
    # Layer 4: every read step's operation (and the descriptor) survives serde.
    _assert_serde(case)


def test_step_statements_handles_single_and_missing() -> None:
    step_single = {"statements": [{"sql": {"postgres": "select 1"}}]}
    assert _coherence_step_statements(step_single, "postgres") == ["select 1"]
    # A write step with no golden SQL for a dialect yields nothing.
    assert _coherence_step_statements({"statements": []}, "postgres") == []
    assert _coherence_step_statements({}, "postgres") == []


def test_coherence_executes_every_statement_with_its_own_binds() -> None:
    case = load_case(
        COMPATIBILITY_ROOT, COMPATIBILITY_ROOT / "cases" / "m-coherence-001-refetch.yaml"
    )
    raw = dict(case.raw)
    raw["when"] = {
        "coherence": [
            {
                "node": "A",
                "kind": "write",
                "statements": [
                    {"sql": {"postgres": "update account set balance = ?"}, "binds": [999]},
                    {"sql": {"postgres": "insert into account(id) values (?)"}, "binds": [9]},
                ],
            },
            {
                "node": "B",
                "kind": "read",
                "statements": [
                    {"sql": {"postgres": "select 1"}},
                    {"sql": {"postgres": "select 2"}, "binds": [2]},
                ],
                "observeRows": [{"marker": "select 2"}],
            },
        ]
    }
    provider = _RecordingProvider()

    _assert_coherence(Case(path=Path("multi-coherence.yaml"), raw=raw, model=case.model), provider)

    assert provider.calls[-4:] == [
        ("A", "execute", "update account set balance = ?", [999]),
        ("A", "execute", "insert into account(id) values (?)", [9]),
        ("B", "query", "select 1", []),
        ("B", "query", "select 2", [2]),
    ]


def test_coherence_without_assertion_is_rejected() -> None:
    # A coherence case whose steps assert nothing fails the structural check.
    bogus = Case(
        path=Path("bogus-coherence.yaml"),
        raw={
            "model": "models/account.yaml",
            "tags": ["coherence"],
            "shape": "coherence",
            "when": {
                "coherence": [
                    {
                        "node": "A",
                        "kind": "write",
                        "statements": [{"sql": {"postgres": "select 1"}}],
                    },
                    {
                        "node": "B",
                        "kind": "read",
                        "statements": [{"sql": {"postgres": "select 1"}}],
                    },
                ],
            },
        },
        model=load_case(
            COMPATIBILITY_ROOT,
            COMPATIBILITY_ROOT / "cases" / "m-coherence-001-refetch.yaml",
        ).model,
    )
    with pytest.raises(CaseFailure):
        _assert_schema(bogus)


# --- coherence identity preservation (sameObjectAs) --------------------------


def _read_step(same_object_as: int | None = None) -> dict[str, Any]:
    step: dict[str, Any] = {
        "node": "B",
        "kind": "read",
        "statements": [{"sql": {"postgres": "select 1"}}],
    }
    if same_object_as is not None:
        step["sameObjectAs"] = same_object_as
    return step


def _identity_case(coherence: list[dict[str, Any]]) -> Case:
    """A minimal coherence Case over the account model for identity-helper tests."""
    model = load_case(
        COMPATIBILITY_ROOT, COMPATIBILITY_ROOT / "cases" / "m-coherence-001-refetch.yaml"
    ).model
    return Case(
        path=Path("identity-coherence.yaml"),
        raw={
            "model": "models/account.yaml",
            "tags": ["coherence"],
            "shape": "coherence",
            "when": {"coherence": coherence},
        },
        model=model,
    )


def test_identity_same_pk_same_node_passes() -> None:
    case = _identity_case([_read_step(), _read_step(same_object_as=0)])
    results = [[{"id": 2}], [{"id": 2}]]
    # Does not raise.
    _assert_coherence_identity(case, 1, case.coherence[1], results, "id")


def test_identity_mismatched_pk_fails() -> None:
    case = _identity_case([_read_step(), _read_step(same_object_as=0)])
    results = [[{"id": 2}], [{"id": 3}]]
    with pytest.raises(CaseFailure, match="same object"):
        _assert_coherence_identity(case, 1, case.coherence[1], results, "id")


def test_identity_reference_to_write_step_fails() -> None:
    case = _identity_case(
        [
            {
                "node": "B",
                "kind": "write",
                "statements": [{"sql": {"postgres": "update account set balance = ?"}}],
            },
            _read_step(same_object_as=0),
        ]
    )
    results = [[], [{"id": 2}]]
    with pytest.raises(CaseFailure, match="must reference a read step"):
        _assert_coherence_identity(case, 1, case.coherence[1], results, "id")


def test_identity_across_nodes_fails() -> None:
    case = _identity_case(
        [
            {"node": "A", "kind": "read", "statements": [{"sql": {"postgres": "select 1"}}]},
            _read_step(same_object_as=0),
        ]
    )
    results = [[{"id": 2}], [{"id": 2}]]
    with pytest.raises(CaseFailure, match="same node"):
        _assert_coherence_identity(case, 1, case.coherence[1], results, "id")


def test_identity_empty_witness_fails() -> None:
    case = _identity_case([_read_step(), _read_step(same_object_as=0)])
    results = [[], [{"id": 2}]]  # referenced step observed no row
    with pytest.raises(CaseFailure, match="empty"):
        _assert_coherence_identity(case, 1, case.coherence[1], results, "id")


def test_identity_reference_must_be_earlier() -> None:
    case = _identity_case([_read_step(), _read_step(same_object_as=1)])
    results = [[{"id": 2}], [{"id": 2}]]
    with pytest.raises(CaseFailure, match="EARLIER"):
        _assert_coherence_identity(case, 1, case.coherence[1], results, "id")


def test_identity_this_step_empty_fails() -> None:
    case = _identity_case([_read_step(), _read_step(same_object_as=0)])
    results = [[{"id": 2}], []]  # this step (the re-fetch) observed no row
    with pytest.raises(CaseFailure, match="empty"):
        _assert_coherence_identity(case, 1, case.coherence[1], results, "id")


def test_write_step_with_sameobjectas_is_rejected() -> None:
    case = _identity_case(
        [
            _read_step(),
            {
                "node": "A",
                "kind": "write",
                "statements": [{"sql": {"postgres": "update account set balance = ?"}}],
                "sameObjectAs": 0,
            },
        ]
    )
    with pytest.raises(CaseFailure, match="write step"):
        _assert_schema(case)
