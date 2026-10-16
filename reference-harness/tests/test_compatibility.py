"""Discover every compatibility case and run it through the layered assertions.

For each available database provider (selected by ``PARALLAX_DATABASES``,
default: all registered), one container is booted for the whole session and
every case whose outcome depends on the dialect is run against it. This is the
m-case-format runner exercising the suite end-to-end: schema conformance, triple
equivalence, normalization determinism, and serde round-trip — against real
Postgres.

Requires Docker (Testcontainers). If no provider can be started, the suite errors
rather than silently passing, because the walking skeleton's whole point is the
real-database run.

The module's second half is the same runner exercised from the other side: a
shipped case damaged in one specific way, asserted to be REFUSED. It lives here
because both directions of the runner need a live database, and the harness
designates exactly one way to one — the ``provider`` fixture in ``conftest.py``.
What belongs here is what THIS module still owns; every accepted-read refusal is
exercised against the read oracle's own seam under ``tests/oracle/``.

The graded MariaDB release floor is asserted here for the same reason: only a
live provider can report which release the pinned image actually runs, and so is
the provider's isolation seam, whose whole claim is what a real server reports the
session running at.
"""

from __future__ import annotations

import copy
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from reference_harness import errors
from reference_harness._case_execution import CaseExecution
from reference_harness.case import Case, dialect_executed_cases, discover_cases
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_runner import run_case
from reference_harness.providers import available_dialects, mariadb
from reference_harness.provisioning import provision

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

# The excluded cases still round-trip through schema validation
# (test_schema_validate) and the profile gate (test_dep_graph); test_rejected.py
# is the sole runner for the `rejected` shape and pins the partition.
ALL_CASES = discover_cases(COMPATIBILITY_ROOT)
CASES = dialect_executed_cases(COMPATIBILITY_ROOT)

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
            run_case(case, None)


def test_a_dialect_is_available() -> None:
    assert available_dialects(), (
        "no database providers available; set PARALLAX_DATABASES or ensure a provider is registered"
    )


def test_the_booted_mariadb_meets_the_graded_isolation_floor(provider) -> None:
    # Below the floor MariaDB's snapshot isolation can refuse a row an uncommitted
    # writer holds, or let a waiting write overwrite that writer's commit. A digest
    # names an image rather than a release, so the release a run actually boots is
    # asserted here rather than remembered from the pin.
    if provider.dialect != "mariadb":
        pytest.skip("the snapshot-isolation floor is a MariaDB fact")
    reported = provider.query("select version() as version")[0]["version"]
    release = tuple(int(part) for part in reported.split("-")[0].split(".")[:3])
    assert release >= mariadb.MARIADB_RELEASE_FLOOR, (
        f"MariaDB {reported} is below the graded floor {mariadb.MARIADB_RELEASE_FLOOR}; the "
        "graded Repeatable Read promise is not underwritten below it"
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


def test_mariadb_restores_snapshot_isolation_after_every_attempt(provider, monkeypatch) -> None:
    # The session owner saves `innodb_snapshot_isolation` before configuring an
    # attempt and restores it once the attempt's transaction settles. Each connection
    # here starts with the setting OFF, as state some earlier user of the connection
    # left, so a restore that wrote anything else would show; it is read back from
    # the real server just before the owner closes the connection. Two attempts per
    # level prove the choreography repeats rather than holding for the first only.
    if provider.dialect != "mariadb":
        pytest.skip("innodb_snapshot_isolation is a MariaDB setting")
    probe = "select @@session.innodb_snapshot_isolation"
    connect = mariadb.pymysql.connect
    restored: list[int] = []

    def connect_with_prior_state(**params):
        connection = connect(**params)
        with connection.cursor() as cur:
            cur.execute("set session innodb_snapshot_isolation = OFF")
        close = connection.close

        def read_back_then_close() -> None:
            with connection.cursor() as cur:
                cur.execute(probe)
                ((value,),) = cur.fetchall()
            restored.append(value)
            close()

        connection.close = read_back_then_close
        return connection

    monkeypatch.setattr(mariadb.pymysql, "connect", connect_with_prior_state)
    during: dict[str, list[int]] = {}
    for level in ("repeatable-read", "serializable"):
        for _ in range(2):
            with provider.open_session(level) as session:
                during.setdefault(level, []).append(session.query(f"{probe} as flag")[0]["flag"])
                session.commit()
    assert during == {"repeatable-read": [1, 1], "serializable": [0, 0]}
    assert restored == [0, 0, 0, 0]


def test_lock_waits_reports_a_session_waiting_on_its_peers_row_lock(provider) -> None:
    # The lock-wait view is what lets a choreography prove a blocking step waits.
    # The waiting session lifts its budget first, so the wait outlasts the polls
    # (InnoDB refreshes its view only after 100 ms without a reader).
    provider.reset()
    provider.apply_ddl(["create table gauge (id bigint primary key, v int not null)"])
    provider.execute("insert into gauge (id, v) values (?, ?)", [1, 0])
    finished: list[int] = []
    with (
        provider.open_session("read-committed") as holder,
        provider.open_session("read-committed") as waiter,
    ):
        holder.execute("update gauge set v = ? where id = ?", [1, 1])
        waiter.extend_lock_wait()
        statement = threading.Thread(
            target=lambda: finished.append(
                waiter.execute("update gauge set v = ? where id = ?", [2, 1])
            )
        )
        statement.start()
        seen = []
        for _ in range(40):
            seen.append(provider.lock_waits())
            if seen[-1]:
                break
            time.sleep(0.15)
        holder.commit()
        statement.join(timeout=10)
        waiter.commit()
    assert seen[-1] == 1
    assert finished == [1]
    time.sleep(0.15)
    assert provider.lock_waits() == 0


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


# --------------------------------------------------------------------------
# A to-one hop's scalar subquery evaluates every declared candidate. Two
# table-per-concrete-subtype branches keying the same id are two candidates for
# one reference, and the database refuses the statement rather than answering
# with either (m-sql *Single-valued traversal*): PostgreSQL raises SQLSTATE 21000
# and MariaDB errno 1242. No neutral category names the failure, so it reaches the
# caller unclassified, through the database execution route.
# --------------------------------------------------------------------------

_DUPLICATE_CANDIDATE_CODE = {"postgres": "21000", "mariadb": 1242}


@pytest.mark.parametrize(
    "stem",
    [
        "m-predicate-090-dotted-field-of-polymorphic-target-tpcs",
        # A subtype test over the reached target evaluates every declared branch,
        # so the selection cannot hide the second candidate.
        "m-predicate-088-target-local-subtype-membership-tpcs",
        # Behind a joined parking the vehicle hop keeps its scalar subquery, so the
        # twin fails it although it reaches no dealer and a narrowing excludes it.
        "m-predicate-114-dotted-field-around-an-unproven-hop",
        "m-predicate-116-target-local-subtype-membership-around-an-unproven-hop",
    ],
)
def test_a_to_one_hop_reaching_two_candidates_fails_through_the_database(
    provider, stem: str
) -> None:
    case = _damaged(stem)
    provision(case, provider)
    execution = CaseExecution(case, provider)
    execution.execute(
        "insert into traversal_bike (id, maker, gears) values (?, ?, ?)", [5, "Twin", 3]
    )
    (statement,) = _statements(case)
    sql, binds = statement["sql"][provider.dialect], statement.get("binds", [])
    with pytest.raises(Exception) as raised:  # noqa: PT011 - each driver raises its own type
        execution.query(sql, binds)
    assert provider.native_error_code(raised.value) == _DUPLICATE_CANDIDATE_CODE[provider.dialect]
    assert provider.classify_error(raised.value) == errors.UNKNOWN


# A relationship match is existential over the same declared candidates: two
# concrete tables keying the same id are two candidates to match, not an
# ambiguity, so the statement answers rather than failing (m-predicate
# *Presence*). The parking whose car matches is selected beside the twin bike.
def test_a_relationship_match_over_two_candidates_answers(provider) -> None:
    case = _damaged("m-predicate-105-relationship-match-narrows-its-own-candidate")
    provision(case, provider)
    execution = CaseExecution(case, provider)
    execution.execute(
        "insert into traversal_bike (id, maker, gears) values (?, ?, ?)", [5, "Twin", 3]
    )
    (statement,) = _statements(case)
    sql, binds = statement["sql"][provider.dialect], statement.get("binds", [])
    assert [row["id"] for row in execution.query(sql, binds)] == [30]
