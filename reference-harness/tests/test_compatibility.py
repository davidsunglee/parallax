"""Discover every compatibility case and run it through the layered assertions.

For each available database provider (selected by ``PARALLAX_DATABASES``,
default: all registered), one container is booted for the whole module and every
case is run against it. This is the M12 runner exercising the suite end-to-end:
schema conformance, triple equivalence, normalization determinism, and serde
round-trip — against real Postgres.

Requires Docker (Testcontainers). If no provider can be started, the suite errors
rather than silently passing, because the walking skeleton's whole point is the
real-database run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reference_harness.case import discover_cases
from reference_harness.case_runner import run_case
from reference_harness.providers import available_dialects, provider_for

# reference-harness/tests/ -> reference-harness/ -> repo root -> core/compatibility
_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

CASES = discover_cases(COMPATIBILITY_ROOT)
DIALECTS = available_dialects()


def _case_id(case) -> str:
    return case.path.stem


@pytest.fixture(scope="session", params=DIALECTS)
def provider(request):
    dialect = request.param
    with provider_for(dialect) as db:
        yield db


def test_cases_discovered() -> None:
    assert CASES, "no compatibility cases discovered under core/compatibility/cases"


def test_a_dialect_is_available() -> None:
    assert DIALECTS, (
        "no database providers available; set PARALLAX_DATABASES or ensure a "
        "provider is registered"
    )


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_case(case, provider) -> None:
    run_case(case, provider)
