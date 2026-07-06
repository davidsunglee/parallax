"""DB-free schema tests for the boundary-case api-conformance-lane invariant.

A boundary case (`m-auto-retry` / `m-opt-lock` bounded automatic retry) is a
runtime-loop observable the single-connection harness cannot provoke, so it lives
on the `api-conformance` lane and is satisfied by each language's API Conformance
Suite. The
compatibility-case schema ENFORCES that invariant: a boundary case must pin
`lane: api-conformance` and carry no golden SQL. Without the pin, a boundary case
that forgets `lane` would default to `harness`, then hit compile/run paths not
shaped for it (the TypeScript `runCompile` would fall through to read compilation
on an absent `operation`; the reference harness would bypass its early skip).
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "core" / "schemas" / "compatibility-case.schema.json"
)


def _case_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()))


def _valid_boundary_case() -> dict:
    """A minimal well-formed boundary case (models the `m-unit-work-004` abort case)."""
    return {
        "model": "models/account.yaml",
        "tags": ["m-unit-work", "abort", "slice-mvp-1"],
        "shape": "boundary",
        "lane": "api-conformance",
        "when": {
            "boundary": [
                {"action": "read", "note": "observe the row"},
                {"action": "update", "note": "buffer/flush a write"},
            ],
        },
        "then": {"outcome": "aborted"},
    }


def test_schema_accepts_boundary_case_on_the_api_conformance_lane() -> None:
    assert list(_case_validator().iter_errors(_valid_boundary_case())) == []


def test_schema_rejects_boundary_case_missing_lane() -> None:
    """Omitting `lane` must fail — it would otherwise default to `harness`."""
    case = _valid_boundary_case()
    del case["lane"]
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a boundary case that omits lane (it would default to harness)"
    )


def test_schema_rejects_boundary_case_on_the_harness_lane() -> None:
    """Explicitly mis-setting `lane: harness` must fail — the lane is pinned."""
    case = _valid_boundary_case()
    case["lane"] = "harness"
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a boundary case whose lane is not api-conformance"
    )


def test_schema_rejects_boundary_case_with_golden_sql() -> None:
    """A boundary case carries no golden SQL — the DML stays per-language."""
    case = _valid_boundary_case()
    case["then"]["statements"] = [
        {"sql": {"postgres": "update account set balance = ? where id = ?"}, "binds": [999.0, 2]}
    ]
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a boundary case that carries golden SQL"
    )
