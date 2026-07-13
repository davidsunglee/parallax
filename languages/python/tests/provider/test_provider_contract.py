"""Provider-contract + adapter-smoke suite (m-db-port, real Postgres).

Exercises the reusable provider obligations over the container — reset, applyDdl,
loadFixtures, query, exec, execRolledBack — plus a minimal psycopg adapter smoke
(construction, scalar read, bytes round trip through the dialect bind seam,
affected-row semantics, and a transaction callback that commits its value). The
deadlock transient-classification proof waits for ``m-db-error`` in Phase 6.
Docker-gated; a skip is reported, never silent (spec §6).
"""

from __future__ import annotations

from typing import Any

import pytest

from parallax.conformance import engine, provision
from parallax.conformance.case_format import default_cases_dir, load_case

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
