"""Discover every compatibility case and run it through the layered assertions.

For each available database provider (selected by ``PARALLAX_DATABASES``,
default: all registered), one container is booted for the whole module and every
case whose outcome depends on the dialect is run against it. This is the
m-case-format runner exercising the suite end-to-end: schema conformance, triple
equivalence, normalization determinism, and serde round-trip — against real
Postgres.

Requires Docker (Testcontainers). If no provider can be started, the suite errors
rather than silently passing, because the walking skeleton's whole point is the
real-database run.

The module's second half is the same runner exercised from the other side: a
shipped case damaged in one specific way, asserted to be REFUSED. It lives here
because the harness designates exactly one entry point to a live database — the
``provider`` fixture below — and both directions of the runner need one.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, dialect_executed_cases, discover_cases
from reference_harness.case_runner import CaseFailure, run_case
from reference_harness.providers import available_dialects, provider_for

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

# The excluded cases still round-trip through schema validation
# (test_schema_validate) and the profile gate (test_dep_graph); test_rejected.py
# is the sole runner for the `rejected` shape and pins the partition.
ALL_CASES = discover_cases(COMPATIBILITY_ROOT)
CASES = dialect_executed_cases(COMPATIBILITY_ROOT)
DIALECTS = available_dialects()


def _case_id(case) -> str:
    # Include the case's tags in the test id so module/feature selectors work,
    # e.g. ``pytest -k m-predicate`` runs every algebra case and ``pytest -k group`` runs
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


# --------------------------------------------------------------------------
# The streamed-delivery oracle: a delivery that reached the right rows the
# wrong way is refused (m-case-format "Streamed reads")
#
# A streamed case's `then.statements` is the pages' own `1 + L` groups
# concatenated, so almost everything that makes a stream a stream lives in the
# page partition rather than in the graph: the size each page asks for, the
# coordinate each later page continues from, and the statement a full final page
# costs to prove exhaustion. A grader that only assembled the roots and compared
# them to `then.graph` would accept every delivery below, which is why each is
# authored as a refusal rather than left to the corpus's own green run. The
# undamaged form of each case passes as an ordinary member of the sweep above.
# --------------------------------------------------------------------------

_DEEP_FETCH = "m-snapshot-read-027-streamed-deep-fetch"
_TERMINAL_PAGE = "m-snapshot-read-028-stream-empty-terminal-page"
_MIXED_DIRECTIONS = "m-snapshot-read-031-stream-order-mixed-directions"
_NULLABLE_PLACEMENT = "m-snapshot-read-032-stream-order-nullable-placement"


def _damaged(stem: str) -> Case:
    """A writable copy of the shipped case named *stem*."""
    return copy.deepcopy(next(case for case in ALL_CASES if case.path.stem == stem))


def _statements(case: Case) -> list[dict[str, Any]]:
    return case.then["statements"]


def test_a_page_seeking_from_the_wrong_root_is_refused(provider) -> None:
    """The continuation is the previous page's LAST root, derived rather than trusted."""
    case = _damaged(_DEEP_FETCH)
    _statements(case)[3]["binds"][3] = 1

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_page_asking_for_the_wrong_size_is_refused(provider) -> None:
    """The requested size is `batchSize`, not whatever the golden happens to bind."""
    case = _damaged(_DEEP_FETCH)
    _statements(case)[0]["binds"][-1] = 3

    with pytest.raises(CaseFailure, match="the size it is asking for"):
        run_case(case, provider)


def test_a_delivery_ending_on_a_full_page_is_refused(provider) -> None:
    """A full final page proves nothing, so dropping the terminal statement fails."""
    case = _damaged(_TERMINAL_PAGE)
    del _statements(case)[4]
    case.then["roundTrips"] = 4

    with pytest.raises(CaseFailure, match="the delivery is not exhausted"):
        run_case(case, provider)


def test_a_statement_after_the_delivery_ended_is_refused(provider) -> None:
    """A stream stops at its first short page, so nothing may follow it."""
    case = _damaged(_DEEP_FETCH)
    entries = _statements(case)
    entries.append(copy.deepcopy(entries[3]))
    case.then["roundTrips"] = 7

    with pytest.raises(CaseFailure, match="after the delivery ended"):
        run_case(case, provider)


def test_a_continuing_page_that_does_not_seek_is_refused(provider) -> None:
    """A continuing page carries a conjunct the first page has no coordinate for.

    The bind oracle alone would accept this: the binds are unchanged and still
    name the right coordinate. What refuses it is that the two root SQL texts are
    equal, which no keyset-paged delivery can produce.
    """
    case = _damaged(_DEEP_FETCH)
    entries = _statements(case)
    entries[3]["sql"] = copy.deepcopy(entries[0]["sql"])

    with pytest.raises(CaseFailure, match="repeats the FIRST page's root SQL"):
        run_case(case, provider)


def test_a_page_hoisting_the_wrong_leading_coordinate_is_refused(provider) -> None:
    """The hoisted range is DERIVED from the leading term's own coordinate.

    Its bind repeats a value the remainder binds again, so a golden that got it
    wrong still selects a plausible row set — and here selects the right one, the
    remainder being unchanged. What refuses it is that the derivation says which
    coordinate the range compares against.
    """
    case = _damaged(_MIXED_DIRECTIONS)
    _statements(case)[1]["binds"][0] = False

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_page_binding_the_wrong_tie_coordinate_is_refused(provider) -> None:
    """Every term of the order supplies its own coordinate, at every tie depth.

    The damaged bind is the second branch's `qty` coordinate — neither the
    leading term nor the primary key — so an oracle that continued from the last
    root's KEY alone, as a single-term order allows, would accept it.
    """
    case = _damaged(_MIXED_DIRECTIONS)
    _statements(case)[1]["binds"][3] = 5

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_page_dropping_its_hoisted_range_is_refused(provider) -> None:
    """The range is redundant by rows and required by contract.

    Removing it leaves a statement that selects exactly the same roots, so every
    result-level oracle passes; the delivery has simply given up the leading
    index range a non-nullable leading term is entitled to.
    """
    case = _damaged(_MIXED_DIRECTIONS)
    entry = _statements(case)[1]
    entry["sql"] = {
        dialect: sql.replace("where t0.active <= ? and (", "where (")
        for dialect, sql in entry["sql"].items()
    }
    del entry["binds"][0]

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        run_case(case, provider)


def test_a_continuing_page_respelling_its_seek_is_refused(provider) -> None:
    """Two pages seeking coordinates of the same NULLNESS seek the same way.

    The damaged page reorders one disjunction, which no bind comparison sees: the
    binds are unchanged, in the same positions, and the statement selects exactly
    the same rows. Only the text is different, and a delivery whose page
    statements drift apart is one whose seek is not a function of its order.
    """
    case = _damaged(_NULLABLE_PLACEMENT)
    entry = _statements(case)[2]
    entry["sql"] = {
        dialect: sql.replace(
            "where (t0.sku > ? or t0.sku is null or", "where (t0.sku is null or t0.sku > ? or"
        )
        for dialect, sql in entry["sql"].items()
    }

    with pytest.raises(CaseFailure, match="seeking the same shape of coordinates"):
        run_case(case, provider)
