"""Evolution-case tests — DB-free (m-model-evolution).

An `evolution` case describes the difference between two accepted Metamodels
and executes nothing, so it is graded once rather than once per dialect and this
module is its sole runner — the counterpart of `test_rejected.py` for the other
dialect-free shape, and the selection the harness-lane partition there names.

What runs here is layer 1: `then.evolution` is an authored golden, so the harness
grades that it COULD be one — closed vocabularies, every identity resolving in
the endpoint that must hold it, every ordered sequence actually ordered. A
language implementation grades the value itself through the conformance adapter,
exactly as it grades golden SQL against a run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import Case, discover_cases
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_runner import run_case
from reference_harness.evolution_validate import validate_evolution

_COMPATIBILITY_ROOT = Path(__file__).resolve().parents[2] / "core" / "compatibility"


def evolution_cases() -> list[Case]:
    """Every authored evolution case. Also the selection `test_rejected.py`'s
    harness-lane partition measures this runner by."""
    return [case for case in discover_cases(_COMPATIBILITY_ROOT) if case.is_evolution]


_CASES = evolution_cases()


@pytest.mark.parametrize("case", _CASES, ids=[case.path.stem for case in _CASES])
def test_evolution_case_is_structurally_sound_db_free(case: Case) -> None:
    # `None` is a safe stand-in for the provider: describing the difference
    # between two accepted models reaches no dialect, provisioning, or execution.
    run_case(case, None)  # type: ignore[arg-type]


def test_the_evolution_population_is_non_empty() -> None:
    assert _CASES, "no evolution cases discovered under core/compatibility/cases"


def test_an_operation_naming_an_identity_neither_endpoint_declares_fails() -> None:
    case = _CASES[0]
    injected = {
        "kind": "AttributeAdded",
        "attribute": "parallax.compatibility.Absent.member",
    }
    findings = validate_evolution(_with_operations(case, [injected]))
    assert any("is not declared by the later endpoint" in finding for finding in findings)


def test_operations_out_of_canonical_order_fail() -> None:
    case = next(case for case in _CASES if len(_operations(case)) > 1)
    reversed_operations = list(reversed(_operations(case)))
    findings = validate_evolution(_with_operations(case, reversed_operations))
    assert any("canonical Model Location order" in finding for finding in findings)


def test_the_runner_reports_a_structural_finding_as_a_case_failure() -> None:
    case = next(case for case in _CASES if len(_operations(case)) > 1)
    broken = _with_operations(case, list(reversed(_operations(case))))
    with pytest.raises(CaseFailure, match="canonical Model Location order"):
        run_case(broken, None)  # type: ignore[arg-type]


def _operations(case: Case) -> list[dict[str, object]]:
    evolution = case.expected_evolution or {}
    return list(evolution.get("operations") or [])


def _with_operations(case: Case, operations: list[dict[str, object]]) -> Case:
    """``case`` with its authored operations replaced, leaving the corpus alone."""
    evolution = dict(case.expected_evolution or {})
    evolution["operations"] = operations
    raw = dict(case.raw)
    raw["then"] = {**raw["then"], "evolution": evolution}
    return Case(path=case.path, raw=raw, model=case.model, earlier_model=case.earlier_model)
