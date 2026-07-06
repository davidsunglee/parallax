"""Discover every compatibility case and run it through the layered assertions.

For each available database provider (selected by ``PARALLAX_DATABASES``,
default: all registered), one container is booted for the whole module and every
case is run against it. This is the m-case-format runner exercising the suite end-to-end:
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

# api-conformance-lane cases (boundary retry cases, read-lock matrix reads) are
# schema-validated by the harness but satisfied by each language's API Conformance
# Suite, so they are NOT executed here. They still round-trip through schema
# validation (test_schema_validate) and the profile gate (test_dep_graph).
ALL_CASES = discover_cases(COMPATIBILITY_ROOT)
CASES = [c for c in ALL_CASES if c.lane != "api-conformance"]
DIALECTS = available_dialects()


def _case_id(case) -> str:
    # Include the case's tags in the test id so module/feature selectors work,
    # e.g. ``pytest -k m-op-algebra`` runs every algebra case and ``pytest -k group`` runs
    # the group-precedence pair. Tags are sanitized to id-safe tokens.
    tags = "-".join(tag.replace(" ", "_") for tag in case.tags)
    return f"{case.path.stem}-{tags}" if tags else case.path.stem


@pytest.fixture(scope="session", params=DIALECTS)
def provider(request):
    dialect = request.param
    with provider_for(dialect) as db:
        yield db


def test_cases_discovered() -> None:
    assert CASES, "no compatibility cases discovered under core/compatibility/cases"


def test_api_conformance_lane_cases_are_not_executed() -> None:
    # DB-free pin: the api-conformance lane is filtered out of the executed set (the
    # m-case-format harness only schema-validates it), yet the cases DO exist in the corpus —
    # a regression that silently ran or dropped them fails here without Docker.
    executed = {c.path.name for c in CASES}
    skipped = {c.path.name for c in ALL_CASES if c.lane == "api-conformance"}
    assert skipped, "expected some api-conformance-lane cases in the corpus"
    assert executed.isdisjoint(skipped), "an api-conformance case leaked into the executed set"
    for case in ALL_CASES:
        if case.lane == "api-conformance":
            # run_case must early-return (schema-validate only) without a database —
            # None is a safe stand-in because no provisioning/execution is reached.
            run_case(case, None)  # type: ignore[arg-type]


def test_a_dialect_is_available() -> None:
    assert DIALECTS, (
        "no database providers available; set PARALLAX_DATABASES or ensure a provider is registered"
    )


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_case(case, provider) -> None:
    run_case(case, provider)
