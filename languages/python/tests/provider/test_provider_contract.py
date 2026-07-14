"""Provider-contract + adapter-smoke suite (m-db-port / m-db-error, real Postgres).

Exercises the reusable provider obligations over the container — reset, applyDdl,
loadFixtures, query, exec, execRolledBack, peer — plus a minimal psycopg adapter
smoke (construction, scalar read, bytes round trip through the dialect bind seam,
affected-row semantics, and a transaction callback that commits its value). The
`m-db-error` transient-classification proof completes the smoke: two crossed-update
`peer` connections provoke a genuine `40P01`, and the port boundary re-raises it as
a neutral, retriable ``DatabaseError`` carrying the preserved SQLSTATE and driver
message. Docker-gated; a skip is reported, never silent (spec §6).
"""

from __future__ import annotations

import threading
from contextlib import suppress
from typing import Any

import pytest

from parallax.conformance import engine, provision
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.core.db_error import DatabaseError

pytestmark = pytest.mark.provider_contract


def _grade_case() -> Any:
    return load_case(default_cases_dir() / "m-descriptor-001-quoted-reserved-identifier.yaml")


def test_reset_apply_ddl_load_fixtures_and_query(provisioner: Any) -> None:
    case = _grade_case()
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, provision.load_fixtures(str(case.document["model"])))
    rows = provisioner.port.execute('select t0.id, t0."order", t0.label from grade t0', [])
    assert len(rows) == 3
    assert {r["label"] for r in rows} == {"low", "mid", "high"}


def test_exec_affected_rows_matched_and_unmatched(provisioner: Any) -> None:
    case = _grade_case()
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, provision.load_fixtures(str(case.document["model"])))
    matched = provisioner.port.execute_write(
        "update grade set label = %s where id = %s", ["top", 3]
    )
    assert matched == 1
    unmatched = provisioner.port.execute_write(
        "update grade set label = %s where id = %s", ["x", 99]
    )
    assert unmatched == 0


def test_scalar_read_returns_managed_values(provisioner: Any) -> None:
    (row,) = provisioner.port.execute("select 1 as one, 'x'::text as who", [])
    assert row == {"one": 1, "who": "x"}


def test_transaction_commits_and_returns_its_value(provisioner: Any) -> None:
    case = _grade_case()
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, provision.load_fixtures(str(case.document["model"])))

    def body(port: Any) -> str:
        port.execute_write("update grade set label = %s where id = %s", ["committed", 1])
        return "done"

    assert provisioner.port.transaction(body) == "done"
    (row,) = provisioner.port.execute("select t0.label from grade t0 where t0.id = %s", [1])
    assert row["label"] == "committed"


def test_exec_rolled_back_leaves_no_effect(provisioner: Any) -> None:
    case = _grade_case()
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, provision.load_fixtures(str(case.document["model"])))

    class _Rollback(Exception):
        pass

    def body(port: Any) -> None:
        port.execute_write("update grade set label = %s where id = %s", ["ghost", 2])
        raise _Rollback

    with pytest.raises(_Rollback):
        provisioner.port.transaction(body)
    (row,) = provisioner.port.execute("select t0.label from grade t0 where t0.id = %s", [2])
    assert row["label"] == "mid"


@pytest.mark.adapter_smoke
def test_deadlock_is_reraised_as_a_retriable_database_error(provisioner: Any) -> None:
    """A genuine two-connection `40P01` surfaces above the port as a neutral,
    retriable ``DatabaseError`` — the `m-db-error` transient-classification proof.

    Round 1 acquires the crossed row locks (A holds row 1, B holds row 2); Round 2
    crosses them (A waits for row 2, B waits for row 1), forming a cycle Postgres
    breaks by victimizing one transaction, whose UPDATE raises `40P01`. Each worker
    rolls back in its ``finally`` so the victim releases its locks and the survivor
    completes, so exactly one victim is observed. The victim choice is
    non-deterministic; the classification is not.
    """
    port = provisioner.port
    for statement in provision.reset_statements():
        port.execute_write(statement, [])
    port.execute_write("create table gauge (id integer primary key, v integer)", [])
    port.execute_write("insert into gauge (id, v) values (1, 0), (2, 0)", [])

    a = provisioner.peer(autocommit=False)
    b = provisioner.peer(autocommit=False)
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
    assert victim.category == "deadlock"
    assert victim.is_retriable
    assert not victim.violates_unique_index
    assert victim.native_code == "40P01"
    assert victim.message  # the preserved driver message crosses the port
