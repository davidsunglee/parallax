"""Diagnostic observations, deliberately separate from independent golden grades."""

import os
from typing import Any

import pytest

from parallax.conformance import adapter, case_format, engine
from tests._support.case_corpus import reachable_cases
from tests._support.corpus import case_fixtures
from tests._support.lane_evidence import DOCUMENT_CASES, capture_document_exception
from tests._support.repo import validate_adapter_envelope

_CASES = [case for case in reachable_cases() if case.case_id in DOCUMENT_CASES]


@pytest.mark.parametrize("case", _CASES, ids=[case.case_id for case in _CASES])
def test_document_run_diagnostic(case: case_format.Case, profile_run: Any) -> None:
    if not os.environ.get("PARALLAX_LANE_EVIDENCE_DIR"):
        pytest.skip("diagnostic-only: enable lane evidence capture to probe document cases")
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))
    try:
        result = adapter.run_case(case.path, profile_run)
    except AssertionError as exc:
        capture_document_exception(case, exc)
        raise
    validate_adapter_envelope(result)
