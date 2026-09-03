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
``provider`` fixture below — and both directions of the runner need one. What
belongs here is what THIS module still owns; every accepted-read refusal is
exercised against the read oracle's own seam under ``tests/oracle/``.

The graded MariaDB release floor is asserted here for the same reason: only a
live provider can report which server a floating image tag resolved to, and so is
the provider's isolation seam, whose whole claim is what a real server reports the
session running at.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, dialect_executed_cases, discover_cases
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_runner import run_case
from reference_harness.providers import available_dialects, provider_for

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

# The excluded cases still round-trip through schema validation
# (test_schema_validate) and the profile gate (test_dep_graph); test_rejected.py
# is the sole runner for the `rejected` shape and pins the partition.
ALL_CASES = discover_cases(COMPATIBILITY_ROOT)
CASES = dialect_executed_cases(COMPATIBILITY_ROOT)
DIALECTS = available_dialects()

# The graded MariaDB floor: 11.4.2, the first release of the 11.4 series carrying
# `innodb_snapshot_isolation`, without which the server has no setting under which
# Repeatable Read forbids the lost update. Grading from the 11.4 long-term-support
# series is a deliberate choice, so a release below this floor fails it whether or not
# it carries the variable.
_MARIADB_SNAPSHOT_ISOLATION_FLOOR = (11, 4, 2)

# Each engine's own way of reporting the level the session is running at, and what
# it answers for each portable level a case may declare (m-db-port). The provider
# maps the portable value; this is the read-back that proves the mapping arrived.
_ISOLATION_READBACK = {
    "postgres": "show transaction_isolation",
    "mariadb": "select @@transaction_isolation as transaction_isolation",
}
_REPORTED_ISOLATION = {
    "postgres": {
        "read-committed": "read committed",
        "repeatable-read": "repeatable read",
        "serializable": "serializable",
    },
    "mariadb": {
        "read-committed": "READ-COMMITTED",
        "repeatable-read": "REPEATABLE-READ",
        "serializable": "SERIALIZABLE",
    },
}


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


def test_the_booted_mariadb_meets_the_graded_isolation_floor(provider) -> None:
    # MariaDB's Repeatable Read forbids the lost update only with
    # `innodb_snapshot_isolation`, which no 11.4-series release below 11.4.2 has. The image
    # pin is a floating major.minor tag, so which server a run actually boots is
    # asserted here rather than remembered from the tag.
    if provider.dialect != "mariadb":
        pytest.skip("the snapshot-isolation floor is a MariaDB fact")
    reported = provider.query("select version() as version")[0]["version"]
    release = tuple(int(part) for part in reported.split("-")[0].split(".")[:3])
    assert release >= _MARIADB_SNAPSHOT_ISOLATION_FLOOR, (
        f"MariaDB {reported} is below the graded floor {_MARIADB_SNAPSHOT_ISOLATION_FLOOR}, the "
        "first 11.4-series release carrying innodb_snapshot_isolation; the graded Repeatable "
        "Read promise is not underwritten below it"
    )


def test_a_held_session_opens_at_each_declared_isolation(provider) -> None:
    # The provider is the harness's adapter for the sessions it owns, so a case
    # declaring a portable level names no engine spelling and no session variable.
    # What proves the mapping landed is the server's own report of the level the
    # session is running at.
    reported = _REPORTED_ISOLATION[provider.dialect]
    read_back = _ISOLATION_READBACK[provider.dialect]
    for level, expected in reported.items():
        with provider.open_session(level) as session:
            observed = session.query(read_back)[0]["transaction_isolation"]
        assert observed == expected, f"{provider.dialect} session at {level} reported {observed!r}"


def test_mariadb_runs_repeatable_read_with_snapshot_isolation_on(provider) -> None:
    # MariaDB's Repeatable Read forbids the lost update only with
    # `innodb_snapshot_isolation`, so what a session opened at that level is
    # RUNNING with is asserted against a real server rather than inferred from the
    # statements the provider issued.
    #
    # This half is live and image-dependent: on an image whose own default is ON,
    # a Repeatable Read session reports the flag on whether or not the provider
    # set it, and a Serializable session reports that same default whether or not
    # the provider wrongly set it too. Which levels carry the setting is therefore
    # pinned where a server default cannot mask it — `test_dialect_seam.py`, over
    # the provider's own per-level statements.
    if provider.dialect != "mariadb":
        pytest.skip("innodb_snapshot_isolation is a MariaDB setting")
    probe = "select @@innodb_snapshot_isolation as flag"
    with provider.open_session() as session:
        default = session.query(probe)[0]["flag"]
    with provider.open_session("repeatable-read") as session:
        assert session.query(probe)[0]["flag"] == 1
    with provider.open_session("serializable") as session:
        assert session.query(probe)[0]["flag"] == default


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_case(case, provider) -> None:
    run_case(case, provider)


# --------------------------------------------------------------------------
# One refusal the READ oracle never reaches: a streamed page whose seek is
# spelled in a shape m-sql does not admit is refused by the normalization layer
# this module still owns, BEFORE any delivery is graded. Every other streamed
# refusal is the oracle's own and is exercised through its public seam
# (``tests/oracle/test_stream_delivery.py``).
# --------------------------------------------------------------------------

_DOCUMENT_RESIDENT = "m-snapshot-read-035-stream-order-document-resident"

# The Document Path spellings the resident case's pages carry, per dialect: one
# hole per segment on Postgres, one whole JSON path on MariaDB.
_RESIDENT_EXTRACTIONS = {
    "postgres": (
        "cast(jsonb_extract_path_text(t0.payload, ?) as bigint)",
        "jsonb_extract_path_text(t0.payload, ?)",
    ),
    "mariadb": (
        "cast(json_value(t0.payload, ?) as signed)",
        "json_value(t0.payload, ?)",
    ),
}


def _respell_resident_pages(case: Case, was: str, now: str) -> None:
    """Rewrite every continuing page of the resident case, each dialect its own way."""
    for entry in _statements(case)[1:]:
        entry["sql"] = {
            dialect: sql.replace(
                was.format(*_RESIDENT_EXTRACTIONS[dialect]),
                now.format(*_RESIDENT_EXTRACTIONS[dialect]),
            )
            for dialect, sql in entry["sql"].items()
        }


def _damaged(stem: str) -> Case:
    """A writable copy of the shipped case named *stem*."""
    return copy.deepcopy(next(case for case in ALL_CASES if case.path.stem == stem))


def _statements(case: Case) -> list[dict[str, Any]]:
    return case.then["statements"]


def test_a_resident_branch_that_dropped_its_grouping_is_not_authorable(provider) -> None:
    """A tie's own two-way branch has to be grouped, and no golden may spell it flat.

    Ungrouped, `and` binds tighter than `or`, so the second branch becomes
    "destination at its coordinate and nights strictly after its own" OR "nights
    is null" — which admits every null-`nights` trip in the table whatever its
    destination, re-delivering roots the stream already published. The fixtures
    have no such trip, so the damaged pages return exactly the rows the correct
    ones return and bind exactly what they bind. What refuses them is the
    canonical-SQL rule rather than the seek oracle behind it: a disjunction
    grouped directly inside a disjunction is not a spelling m-sql admits, so the
    flat branch has no authorable form and the seek it would compose is never
    reached.
    """
    case = _damaged(_DOCUMENT_RESIDENT)
    _respell_resident_pages(case, "and ({0} < ? or {1} is null))", "and {0} < ? or {1} is null)")

    with pytest.raises(CaseFailure, match="is not canonical"):
        run_case(case, provider)
