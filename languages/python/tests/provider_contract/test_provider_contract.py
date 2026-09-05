"""Provider-contract + adapter-smoke suite (m-db-port / m-db-error, real Postgres).

Exercises the reusable provider obligations over the container — reset, applyDdl,
loadFixtures, query, exec, execRolledBack, peer — plus a minimal psycopg adapter
smoke (construction, scalar read, bytes round trip through the dialect bind seam,
affected-row semantics, and a transaction callback that commits its value). The
`m-db-error` translation-boundary proof completes the smoke: two crossed-update
`peer` connections provoke a genuine `40P01`, and the port boundary re-raises it as
a neutral ``DatabaseError`` -- narrowed to the FULL-shape assertions
(`is_retriable`, `violates_unique_index`,
the preserved driver message) the corpus's own case-driven grading of this SAME
choreography (`m-db-error-004`, `parallax.conformance.concurrency_runner`) does not
check; the exact `errorClass`/`nativeCode` pin lives there now. Docker-gated; a
skip is reported, never silent (spec §6).
"""

from __future__ import annotations

import threading
from contextlib import suppress
from typing import Any

import pytest

from parallax.conformance import engine, models, provision
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.models import default_models_dir
from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    ISOLATION_LEVELS,
    BeginFailed,
    CallbackRaised,
    CommitFailed,
    Committed,
    RollbackFailed,
    RolledBack,
    isolation_level,
)
from parallax.core.dialect import POSTGRES
from parallax.evolution.model_evolution import ABSENT, evolve
from parallax.evolution.schema_delta import schema_delta
from parallax.postgres import adapter as adapter_module
from parallax.postgres import isolation_spelling


def _grade_case() -> Any:
    return load_case(default_cases_dir() / "m-descriptor-001-quoted-reserved-identifier.yaml")


def test_reset_apply_ddl_load_fixtures_and_query(profile_run: Any) -> None:
    case = _grade_case()
    meta = engine.load_case_metamodel(case)
    profile_run.reset(meta, provision.load_fixtures(str(case.document["model"])))
    rows = profile_run.port.execute('select t0.id, t0."order", t0.label from grade t0', [])
    assert len(rows) == 3
    assert {r["label"] for r in rows} == {"low", "mid", "high"}


def test_exec_affected_rows_matched_and_unmatched(profile_run: Any) -> None:
    case = _grade_case()
    meta = engine.load_case_metamodel(case)
    profile_run.reset(meta, provision.load_fixtures(str(case.document["model"])))
    matched = profile_run.port.execute_write(
        "update grade set label = %s where id = %s", ["top", 3]
    )
    assert matched == 1
    unmatched = profile_run.port.execute_write(
        "update grade set label = %s where id = %s", ["x", 99]
    )
    assert unmatched == 0


def test_scalar_read_returns_managed_values(profile_run: Any) -> None:
    (row,) = profile_run.port.execute("select 1 as one, 'x'::text as who", [])
    assert row == {"one": 1, "who": "x"}


def test_live_structured_document_reads_preserve_sql_null_and_json_null(
    profile_run: Any,
) -> None:
    sql = "select false as present, null::jsonb as document union all select true, 'null'::jsonb"
    assert profile_run.port.execute(sql, [], document_reads=((0, 1),)) == [
        {"document": SQL_NULL},
        {"document": PresentDocument(None)},
    ]
    assert profile_run.port.execute(
        "select null::jsonb as sql_null, 'null'::jsonb as json_null", []
    ) == [{"sql_null": None, "json_null": None}]

    for binary in (False, True):
        with profile_run.port.connection.cursor(binary=binary) as cursor:
            cursor.execute(b"select 'null'::jsonb")
            assert cursor.fetchone() == (adapter_module._PRESENT_JSON_NULL,)  # pyright: ignore[reportPrivateUsage]


def test_transaction_commits_and_reports_the_body_value(profile_run: Any) -> None:
    case = _grade_case()
    meta = engine.load_case_metamodel(case)
    profile_run.reset(meta, provision.load_fixtures(str(case.document["model"])))

    def body(port: Any) -> str:
        port.execute_write("update grade set label = %s where id = %s", ["committed", 1])
        return "done"

    assert profile_run.port.transaction(body) == Committed("done")
    (row,) = profile_run.port.execute("select t0.label from grade t0 where t0.id = %s", [1])
    assert row["label"] == "committed"


def test_every_portable_level_opens_the_boundary_at_its_spelling(profile_run: Any) -> None:
    # The mapping proved on the shipped adapter path rather than on a fake
    # connection: for each portable level, the level the database reports for the
    # transaction the callback is running in is this engine's own name for the
    # one that was asked for. A rename is the whole of Postgres' mapping, so a
    # mapping that dropped a level, or crossed two of them, is what this catches;
    # what a level then FORBIDS is graded by the corpus, not here.
    observed: list[str] = []

    def body(port: Any) -> None:
        (row,) = port.execute("show transaction_isolation", [])
        observed.append(str(row["transaction_isolation"]))

    for level in sorted(ISOLATION_LEVELS):
        assert profile_run.port.transaction(body, isolation=isolation_level(level)) == Committed(
            None
        )
    # An omitted level asks for nothing, so the boundary after three explicit
    # ones reports the connection's own default rather than the last request:
    # the setting is the boundary's and outlives none of them.
    assert profile_run.port.transaction(body) == Committed(None)
    assert observed == [
        *(isolation_spelling(isolation_level(level)) for level in sorted(ISOLATION_LEVELS)),
        "read committed",
    ]


def test_exec_rolled_back_leaves_no_effect(profile_run: Any) -> None:
    case = _grade_case()
    meta = engine.load_case_metamodel(case)
    profile_run.reset(meta, provision.load_fixtures(str(case.document["model"])))

    class _Rollback(Exception):
        pass

    def body(port: Any) -> None:
        port.execute_write("update grade set label = %s where id = %s", ["ghost", 2])
        raise _Rollback

    outcome = profile_run.port.transaction(body)
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CallbackRaised)
    assert isinstance(trigger.error, _Rollback)
    (row,) = profile_run.port.execute("select t0.label from grade t0 where t0.id = %s", [2])
    assert row["label"] == "mid"


# --------------------------------------------------------------------------- #
# The two obligations only a real catalog and a real violation can discharge    #
# (`database-provider-test-contract.md` §2): a derived Physical Index Name at   #
# exactly this engine's identifier limit, kept byte for byte; and a duplicate   #
# whose neutral error names the index it violated by that same name.            #
# --------------------------------------------------------------------------- #
def _provision(profile_run: Any, model_file: str) -> Any:
    """Provision ``model_file``'s schema through the shipped generator, returning
    the Unilateral Evolution the statements came from."""
    model = models.load_model(default_models_dir() / model_file)
    for statement in provision.reset_statements():
        profile_run.port.execute_write(statement, [])
    for statement in provision.schema_statements(model):
        profile_run.port.execute_write(statement, [])
    return evolve(ABSENT, model)


def test_a_name_at_the_identifier_limit_is_stored_exactly_as_generated(
    profile_run: Any,
) -> None:
    """The one proof a pure test cannot make: a name the generator shortened to
    fit is what the server actually holds.

    The readable half of this model's name runs far past the budget, so the
    generator cut it to exactly 63 bytes — Postgres' own limit. A server that
    truncated further, or normalized the name at all, would report something else
    from its catalog, and the fingerprint the name is unique by would be the half
    that lost characters.
    """
    delta = schema_delta(_provision(profile_run, "evolution-long-names-v1.yaml"), POSTGRES)
    (created,) = delta.created_indices
    assert len(created.physical_index_name.value.encode()) == POSTGRES.max_identifier_bytes

    (row,) = profile_run.port.execute(
        "select t0.indexname from pg_indexes t0 where t0.tablename = %s and t0.indexname = %s",
        [created.physical_table.name, created.physical_index_name.value],
    )
    assert row["indexname"] == created.physical_index_name.value
    # The fingerprint is the half truncation never touches, so it survives whole.
    assert row["indexname"].endswith(created.physical_index_name.value[-32:])


def test_a_duplicate_names_the_index_it_violated_by_its_created_name(
    profile_run: Any,
) -> None:
    """A unique violation reaches the caller carrying the Physical Index Name the
    rollout that created the index already recorded.

    This is the whole correlation contract: the host holds `createdIndices` from
    its own Schema Delta, catches a neutral ``DatabaseError``, and matches the two
    without parsing a driver message or knowing a dialect.
    """
    delta = schema_delta(_provision(profile_run, "error-cases.yaml"), POSTGRES)
    (created,) = [entry for entry in delta.created_indices if entry.unique]

    profile_run.port.execute_write("insert into tag (id, name) values (%s, %s)", [1, "first"])
    with pytest.raises(DatabaseError) as raised:
        profile_run.port.execute_write("insert into tag (id, name) values (%s, %s)", [2, "first"])

    assert raised.value.violates_unique_index
    assert raised.value.violated_index == created.physical_index_name


# --------------------------------------------------------------------------- #
# The boundary outcomes the adapter smoke contract names                       #
# (`database-provider-test-contract.md` §2): a committed value above, a        #
# callback-triggered rollback above, and the three below — a boundary that     #
# never began, a commit-triggered rollback, and each of the two rollbacks that #
# could not complete. Only a real database produces them: a commit failure     #
# needs a constraint that fires at COMMIT, and a rollback failure needs a      #
# session that is gone by the time the undo is sent.                           #
# --------------------------------------------------------------------------- #
def _terminate(executioner: Any, victim: Any) -> None:
    """End ``victim``'s own database session from a second connection.

    The only way to make a genuine ROLLBACK fail: the session it would run in no
    longer exists, so the undo cannot be sent and what the transaction left
    behind is unknown.
    """
    (row,) = victim.execute("select pg_backend_pid() as pid", [])
    executioner.execute("select pg_terminate_backend(%s) as terminated", [row["pid"]])


@pytest.mark.adapter_smoke
def test_transaction_reports_a_boundary_that_never_began(profile_run: Any) -> None:
    # A closed connection is the reachable begin failure. What makes it distinct
    # from every other unhappy outcome is that the callback never runs, so there
    # is nothing to undo and nothing to re-execute.
    port = profile_run.peer()
    port.close()
    ran: list[str] = []

    def never_runs(_conn: Any) -> None:
        ran.append("body")

    outcome = port.transaction(never_runs)
    assert isinstance(outcome, BeginFailed)
    assert isinstance(outcome.error, DatabaseError)
    assert ran == []


@pytest.mark.adapter_smoke
def test_transaction_reports_a_commit_failure_as_rolled_back(profile_run: Any) -> None:
    # A DEFERRABLE INITIALLY DEFERRED unique constraint is checked at COMMIT, so
    # the duplicate the body inserts succeeds as a statement and the durability
    # call is what fails — the one failure no `execute_write` can report.
    port = profile_run.peer()
    for statement in provision.reset_statements():
        port.execute_write(statement, [])
    port.execute_write(
        "create table deferred_tag (id integer primary key, tag integer, "
        "constraint deferred_tag_unique unique (tag) deferrable initially deferred)",
        [],
    )
    port.execute_write("insert into deferred_tag (id, tag) values (1, 1)", [])

    def duplicate(conn: Any) -> int:
        return conn.execute_write("insert into deferred_tag (id, tag) values (2, 1)", [])

    outcome = port.transaction(duplicate)
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CommitFailed)
    assert isinstance(trigger.error, DatabaseError)
    assert trigger.error.violates_unique_index
    # The rollback completed, so the connection is usable and nothing landed.
    assert port.execute("select count(*) as n from deferred_tag", []) == [{"n": 1}]


@pytest.mark.adapter_smoke
def test_transaction_reports_a_rollback_that_could_not_undo_the_callbacks_failure(
    profile_run: Any,
) -> None:
    class _Rollback(Exception):
        pass

    port = profile_run.peer()
    executioner = profile_run.peer()

    def body(conn: Any) -> None:
        _terminate(executioner, conn)
        raise _Rollback

    outcome = port.transaction(body)
    assert isinstance(outcome, RollbackFailed)
    trigger = outcome.trigger
    assert isinstance(trigger, CallbackRaised)
    # Both live errors survive: the callback's failure ended the transaction, and
    # the rollback failure is why undoing it did not happen.
    assert isinstance(trigger.error, _Rollback)
    assert isinstance(outcome.rollback_error, DatabaseError)


@pytest.mark.adapter_smoke
def test_transaction_reports_a_rollback_that_could_not_undo_a_failed_commit(
    profile_run: Any,
) -> None:
    port = profile_run.peer()
    executioner = profile_run.peer()

    def body(conn: Any) -> str:
        _terminate(executioner, conn)
        return "unreachable"

    outcome = port.transaction(body)
    assert isinstance(outcome, RollbackFailed)
    trigger = outcome.trigger
    # The commit is what ended the transaction, so it stays the trigger rather
    # than being replaced by the rollback failure that followed it.
    assert isinstance(trigger, CommitFailed)
    assert isinstance(trigger.error, DatabaseError)
    assert isinstance(outcome.rollback_error, DatabaseError)


@pytest.mark.adapter_smoke
def test_deadlock_is_reraised_as_a_retriable_database_error(profile_run: Any) -> None:
    """A genuine two-connection `40P01` surfaces above the port as a neutral
    ``DatabaseError`` — the adapter's own translation-boundary contract.

    Round 1 acquires the crossed row locks (A holds row 1, B holds row 2); Round 2
    crosses them (A waits for row 2, B waits for row 1), forming a cycle Postgres
    breaks by victimizing one transaction, whose UPDATE raises `40P01`. Each worker
    rolls back in its ``finally`` so the victim releases its locks and the survivor
    completes, so exactly one victim is observed. The victim choice is
    non-deterministic; the classification is not.

    NARROWED: the trigger
    choreography here is structurally identical to `m-db-error-004`'s own
    corpus case, which grades case-driven, byte-exact against the golden
    `errorClass`/`nativeCode` through `parallax.conformance.concurrency_runner`
    (`tests/compatibility/test_run_sweep.py::test_concurrency_rounds`) — so the
    `category`/`native_code` exact-value pins retire from here (redundant with
    that grading) and only the assertions the corpus's own `then` block never
    declares survive: the adapter populates the FULL `DatabaseError` shape
    (`is_retriable`, `violates_unique_index`, the preserved driver `message`),
    a provider-contract obligation the case format has no vocabulary for.
    """
    port = profile_run.port
    for statement in provision.reset_statements():
        port.execute_write(statement, [])
    port.execute_write("create table gauge (id integer primary key, v integer)", [])
    port.execute_write("insert into gauge (id, v) values (1, 0), (2, 0)", [])

    a = profile_run.peer(autocommit=False)
    b = profile_run.peer(autocommit=False)
    victims: list[DatabaseError] = []
    record = threading.Lock()

    def cross(peer: Any, value: int, row_id: int) -> None:
        try:
            peer.execute_write("update gauge set v = %s where id = %s", [value, row_id])
        except DatabaseError as exc:
            with record:
                victims.append(exc)
        finally:
            # Roll back regardless: a victim releases its locks so the survivor can
            # finish; the survivor discards its speculative update.
            with suppress(Exception):
                peer.connection.rollback()

    try:
        # Round 1: A locks row 1, B locks row 2 (no contention yet).
        a.execute_write("update gauge set v = %s where id = %s", [10, 1])
        b.execute_write("update gauge set v = %s where id = %s", [20, 2])

        # Round 2: each wants the row the other holds -> a guaranteed cycle.
        worker_a = threading.Thread(target=cross, args=(a, 11, 2))
        worker_b = threading.Thread(target=cross, args=(b, 21, 1))
        worker_a.start()
        worker_b.start()
        worker_a.join(timeout=20)
        worker_b.join(timeout=20)
        assert not worker_a.is_alive() and not worker_b.is_alive(), "deadlock did not resolve"
    finally:
        a.close()
        b.close()

    assert len(victims) == 1, f"expected exactly one deadlock victim, got {len(victims)}"
    victim = victims[0]
    # `category`/`native_code` exact-value pins are not asserted here: graded
    # byte-exact against the corpus golden by `m-db-error-004`'s own
    # case-driven proof now (`test_run_sweep.test_concurrency_rounds`).
    assert victim.is_retriable
    assert not victim.violates_unique_index
    assert victim.message  # the preserved driver message crosses the port
