"""DB-free tests for the compile-eligibility declaration and its harness backstop.

The core amendment adds a `compileEligibility` declaration to a case (run-only,
with a `single-connection` / `query-result-dependent` reason) and a defined
`compile` adapter answer for a claimed-but-run-only case (`status: run-only` with
a `compile-run-only` diagnostic). These tests pin:

* the mechanical backstop (`schema_validate._check_compile_eligibility`) flags a
  detectable single-connection case left compile-eligible or mis-reasoned, and
  passes one correctly declared / a non-detectable one;
* the whole corpus is consistent under the backstop (every detectable case is
  declared);
* the conformance-adapter schema accepts a `run-only` compile envelope and
  rejects one missing the `compile-run-only` diagnostic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from reference_harness.schema_validate import _check_compile_eligibility

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMAS = _REPO_ROOT / "core" / "schemas"
_CASES = _REPO_ROOT / "core" / "compatibility" / "cases"


def _errors(case: dict[str, Any]) -> list[str]:
    out: list[str] = []
    _check_compile_eligibility(case, "case under-test", out)
    return out


# --- the mechanical backstop --------------------------------------------------


def test_conflict_shape_left_eligible_is_flagged() -> None:
    case = {"model": "models/account.yaml", "tags": ["m-opt-lock"], "shape": "conflict"}
    assert _errors(case)


def test_given_apply_left_eligible_is_flagged() -> None:
    case = {
        "model": "models/account.yaml",
        "tags": ["m-opt-lock"],
        "shape": "writeSequence",
        "given": {"apply": [{"sql": "update account set version = 2 where id = 1"}]},
    }
    assert _errors(case)


def test_when_concurrency_left_eligible_is_flagged() -> None:
    case = {
        "model": "models/account.yaml",
        "tags": ["m-db-error"],
        "shape": "error",
        "when": {"concurrency": {"rounds": []}},
    }
    assert _errors(case)


def test_detectable_case_with_wrong_reason_is_flagged() -> None:
    case = {
        "model": "models/account.yaml",
        "tags": ["m-opt-lock"],
        "shape": "conflict",
        "compileEligibility": {"mode": "run-only", "reason": "query-result-dependent"},
    }
    assert _errors(case)


def test_detectable_case_declared_single_connection_passes() -> None:
    case = {
        "model": "models/account.yaml",
        "tags": ["m-opt-lock"],
        "shape": "conflict",
        "compileEligibility": {"mode": "run-only", "reason": "single-connection"},
    }
    assert _errors(case) == []


def test_non_detectable_case_needs_no_declaration() -> None:
    case = {"model": "models/account.yaml", "tags": ["m-op-algebra"], "shape": "read"}
    assert _errors(case) == []


def test_query_result_dependent_case_is_allowed_without_a_marker() -> None:
    # A run-only declaration on a non-detectable (query-dependent) case is legitimate
    # and never flagged — the backstop only enforces the detectable direction.
    case = {
        "model": "models/pk-sequence.yaml",
        "tags": ["m-pk-gen"],
        "shape": "writeSequence",
        "compileEligibility": {"mode": "run-only", "reason": "query-result-dependent"},
    }
    assert _errors(case) == []


# --- corpus-wide consistency --------------------------------------------------


def test_whole_corpus_is_eligibility_consistent() -> None:
    import yaml

    problems: list[str] = []
    for path in sorted(_CASES.glob("*.yaml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        _check_compile_eligibility(case, f"case {path.name}", problems)
    assert problems == [], problems


# --- the run-only compile adapter answer --------------------------------------


def _adapter_validator() -> Draft202012Validator:
    schema = json.loads((_SCHEMAS / "conformance-adapter.schema.json").read_text())
    return Draft202012Validator(schema)


def _run_only_envelope() -> dict[str, Any]:
    return {
        "schemaVersion": "1",
        "command": "compile",
        "status": "run-only",
        "adapter": {"language": "python", "name": "parallax-conformance", "version": "0.1.0"},
        "case": "core/compatibility/cases/m-opt-lock-005-conflict.yaml",
        "dialect": "postgres",
        "caseShape": "conflict",
        "diagnostics": [
            {"code": "compile-run-only", "message": "single-connection conflict case is run-only"}
        ],
    }


def test_run_only_compile_envelope_is_valid() -> None:
    assert list(_adapter_validator().iter_errors(_run_only_envelope())) == []


def test_run_only_envelope_requires_the_compile_run_only_diagnostic() -> None:
    envelope = _run_only_envelope()
    envelope["diagnostics"] = [{"code": "some-other-code", "message": "x"}]
    assert list(_adapter_validator().iter_errors(envelope))


def test_run_only_status_is_only_valid_for_compile() -> None:
    envelope = _run_only_envelope()
    envelope["command"] = "run"
    assert list(_adapter_validator().iter_errors(envelope))
