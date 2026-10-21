"""The conformance engine's case-document facts: what a case SAYS, read off
its document alone.

Docker-free. Compile eligibility is read from the case's own declaration, and a
predicate-write step's ``write`` translates to the canonical instruction shape
with its Clock-context ``at`` dropped.
"""

from __future__ import annotations

from pathlib import Path

from parallax.conformance import case_format
from parallax.conformance._mechanism import case_document
from tests._support.case_corpus import case as corpus_case
from tests._support.case_corpus import cases as corpus_cases


def _case(case_id: str) -> case_format.Case:
    return corpus_case(case_id, reachable=True)


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
    cases = corpus_cases()
    run_only = [c for c in cases if case_document.eligibility(c) is not None]
    assert run_only, "the corpus declares at least one run-only case"
    first = case_document.eligibility(run_only[0])
    assert first is not None and first.reason  # a non-empty reason


def test_eligibility_non_run_only_declaration_is_compile_eligible() -> None:
    case = _synthetic({"compileEligibility": {"mode": "eligible"}})
    assert case_document.eligibility(case) is None
