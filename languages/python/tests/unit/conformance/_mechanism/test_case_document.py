"""The conformance engine's case-document facts: what a case SAYS, read off
its document alone.

Docker-free. Compile eligibility is read from the case's own declaration, and a
predicate-write step's ``write`` translates to the canonical instruction shape
with its Clock-context ``at`` dropped.
"""

from __future__ import annotations

import functools
from pathlib import Path

from parallax.conformance import case_format, sweep
from parallax.conformance._mechanism import case_document


@functools.cache
def _corpus() -> tuple[case_format.Case, ...]:
    return tuple(case_format.load_cases())


def _case(case_id: str) -> case_format.Case:
    return next(
        case for case in sweep.reachable_cases(cases=list(_corpus())) if case.case_id == case_id
    )


def _synthetic(document: dict[str, object]) -> case_format.Case:
    return case_format.Case(
        path=Path("m-predicate-999-synthetic.yaml"),
        case_id="m-predicate-999",
        shape="read",
        tags=("m-predicate", "slice-snapshot-1"),
        model="models/orders.yaml",
        document=document,
    )


def test_eligibility_reads_the_case_declaration() -> None:
    assert case_document.eligibility(_case("m-value-object-001")) is None
    cases = _corpus()
    run_only = [c for c in cases if case_document.eligibility(c) is not None]
    assert run_only, "the corpus declares at least one run-only case"
    first = case_document.eligibility(run_only[0])
    assert first is not None and first.reason  # a non-empty reason


def test_eligibility_non_run_only_declaration_is_compile_eligible() -> None:
    case = _synthetic({"compileEligibility": {"mode": "eligible"}})
    assert case_document.eligibility(case) is None


def test_canonical_predicate_doc_preserves_valid_time_bounds_and_drops_at() -> None:
    # `at` is Clock context, never an instruction field. Valid-Time bounds
    # already use their canonical instruction spelling.
    doc = case_document.canonical_predicate_doc(
        {
            "mutation": "terminateUntil",
            "target": {
                "entity": "Position",
                "predicate": {"eq": {"attr": "Position.id", "value": 1}},
            },
            "at": "2024-10-01T00:00:00+00:00",
            "validFrom": "2024-07-01T00:00:00+00:00",
            "until": "2024-09-01T00:00:00+00:00",
        }
    )
    assert "at" not in doc
    assert doc["validFrom"] == "2024-07-01T00:00:00+00:00"
    assert doc["until"] == "2024-09-01T00:00:00+00:00"
