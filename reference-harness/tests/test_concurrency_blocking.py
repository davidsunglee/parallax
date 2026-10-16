"""DB-free tests for blocking steps, per-statement affected rows, and the table
state a `when.concurrency` choreography may state (m-case-format *Error cases*).

The live two-session runs are the witness cases `test_compatibility.py` drives
against both engines; here fakes stand in for the provider and its sessions so
the runner's own release, wait, and grading rules are pinned without a database.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from reference_harness.case import Case, Model
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_runner import _assert_schema, _run_concurrency_rounds
from reference_harness.schemas import build_registry, load_schemas

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"
_REGISTRY = build_registry(load_schemas(_REPO_ROOT / "core"))

_UPDATE = {"postgres": "update account set balance = ? where id = ?"}
_DELETE = {"postgres": "delete from account where id = ?"}


def _entry(sql: dict[str, str], binds: list[Any]) -> dict[str, Any]:
    return {"sql": sql, "binds": binds}


def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()), registry=_REGISTRY)


def _case(raw: dict[str, Any]) -> Case:
    descriptor = {"entity": {"name": "Account", "table": "account", "attributes": []}}
    model = Model(path=Path("account.yaml"), descriptor=descriptor)
    return Case(path=Path("m-batch-write-900-x.yaml"), raw=raw, model=model)


def _success(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "shape": "concurrencySuccess",
        "when": {"concurrency": {"rounds": rounds}},
        "tags": ["m-batch-write", "concurrency"],
    }


def _blocking_rounds() -> list[dict[str, Any]]:
    return [
        {"A": {"kind": "write", "statements": [_entry(_UPDATE, [1, 1])], "affectedRows": [1]}},
        {
            "B": {
                "kind": "write",
                "blocks": True,
                "statements": [_entry(_DELETE, [1])],
                "affectedRows": [1],
            }
        },
        {"A": {"kind": "commit"}},
        {"B": {"kind": "commit"}},
    ]


# --- schema ------------------------------------------------------------------


def test_schema_accepts_a_blocking_write_and_its_affected_rows() -> None:
    assert list(_validator().iter_errors(_success(_blocking_rounds()))) == []


def test_schema_accepts_a_blocking_statement_step_on_the_error_shape() -> None:
    case = {
        "model": "models/account.yaml",
        "shape": "error",
        "when": {
            "concurrency": {
                "rounds": [
                    {"A": {"statements": [_entry(_UPDATE, [1, 1])]}},
                    {"B": {"blocks": True, "statements": [_entry(_DELETE, [1])]}},
                    {"A": {"kind": "commit"}},
                ]
            }
        },
        "then": {
            "errorClass": "deadlock",
            "nativeCode": {"postgres": "40001"},
            "tableState": {"account": [{"id": 1}]},
        },
        "tags": ["m-batch-write", "concurrency"],
    }
    assert list(_validator().iter_errors(case)) == []


@pytest.mark.parametrize(
    "step",
    [
        {"kind": "commit", "blocks": True},
        {"kind": "write", "blocks": True, "statements": [_entry(_UPDATE, [1, 1])] * 2},
        {
            "kind": "read",
            "statements": [_entry(_UPDATE, [1, 1])],
            "expectRows": [],
            "affectedRows": [0],
        },
        {"kind": "write", "statements": [_entry(_UPDATE, [1, 1])], "blocks": False},
        {"kind": "write", "statements": [_entry(_UPDATE, [1, 1])], "affectedRows": []},
    ],
    ids=[
        "commit-blocks",
        "two-blocking-statements",
        "read-counts-rows",
        "blocks-false",
        "no-counts",
    ],
)
def test_schema_refuses_a_malformed_blocking_or_counting_step(step: dict[str, Any]) -> None:
    assert list(_validator().iter_errors(_success([{"A": step}])))


def test_schema_refuses_affected_rows_on_the_error_shape() -> None:
    case = {
        "model": "models/account.yaml",
        "shape": "error",
        "when": {
            "concurrency": {
                "rounds": [{"A": {"statements": [_entry(_UPDATE, [1, 1])], "affectedRows": [1]}}]
            }
        },
        "then": {"errorClass": "deadlock", "nativeCode": {"postgres": "40001"}},
        "tags": ["m-batch-write", "concurrency"],
    }
    assert list(_validator().iter_errors(case))


# --- pre-flight ---------------------------------------------------------------


def test_runner_refuses_a_blocking_step_nothing_releases() -> None:
    rounds = _blocking_rounds()
    del rounds[2]  # A never acts after B's blocking step, so nothing releases it
    with pytest.raises(CaseFailure, match=r"/concurrency/rounds/1/B: a blocking step needs"):
        _assert_schema(_case(_success(rounds)))


def test_runner_refuses_a_blocking_nodes_next_step_before_its_release() -> None:
    rounds = _blocking_rounds()
    rounds[2], rounds[3] = rounds[3], rounds[2]  # B commits before A releases the lock
    with pytest.raises(CaseFailure, match=r"/concurrency/rounds/1/B: a blocking step needs"):
        _assert_schema(_case(_success(rounds)))


def test_runner_accepts_a_release_in_the_round_of_the_nodes_next_step() -> None:
    rounds = _blocking_rounds()
    rounds[2:] = [{"A": {"kind": "commit"}, "B": {"kind": "commit"}}]
    _assert_schema(_case(_success(rounds)))  # must not raise


def test_runner_refuses_a_blocking_step_while_its_peers_blocking_step_is_outstanding() -> None:
    rounds = _blocking_rounds()
    rounds[2:] = [
        {"A": {"kind": "write", "blocks": True, "statements": [_entry(_UPDATE, [2, 2])]}},
        {"A": {"kind": "commit"}, "B": {"kind": "commit"}},
    ]
    with pytest.raises(
        CaseFailure, match=r"/concurrency/rounds/2/A: a blocking step must wait alone; node B is"
    ):
        _assert_schema(_case(_success(rounds)))


def test_runner_refuses_a_peer_step_in_a_blocking_steps_round() -> None:
    rounds = _blocking_rounds()
    rounds[1]["A"] = {"kind": "write", "statements": [_entry(_UPDATE, [2, 2])]}
    with pytest.raises(
        CaseFailure, match=r"/concurrency/rounds/1/B: a blocking step must wait alone; node A acts"
    ):
        _assert_schema(_case(_success(rounds)))


def test_runner_refuses_affected_rows_that_miscount_the_statements() -> None:
    rounds = _blocking_rounds()
    rounds[0]["A"]["affectedRows"] = [1, 1]
    with pytest.raises(CaseFailure, match=r"/concurrency/rounds/0/A: affectedRows states 2"):
        _assert_schema(_case(_success(rounds)))


# --- the runner over fake sessions ------------------------------------------


class _Lock:
    """One row lock the fake sessions share; ``waiting`` is what the provider's
    lock-wait view reports."""

    def __init__(self) -> None:
        self.held = False
        self.released = threading.Event()
        self.waiting = 0
        self.guard = threading.Lock()


class _Session:
    def __init__(self, node: str, lock: _Lock, *, waits: bool) -> None:
        self.node = node
        self.lock = lock
        self.waits = waits
        self.calls: list[str] = []

    def execute(self, sql: str, binds: Any = ()) -> int:
        self.calls.append(sql)
        if self.node == "A":
            self.lock.held = True
        elif self.waits and self.lock.held:
            with self.lock.guard:
                self.lock.waiting += 1
            assert self.lock.released.wait(timeout=5)
            with self.lock.guard:
                self.lock.waiting -= 1
        return 1

    def commit(self) -> None:
        self.calls.append("commit")
        if self.node == "A":
            self.lock.released.set()

    def rollback(self) -> None:
        self.calls.append("rollback")

    def extend_lock_wait(self) -> None:
        self.calls.append("extend_lock_wait")


class _Execution:
    def __init__(self, sessions: dict[str, _Session]) -> None:
        self._sessions = iter(sessions.values())

    @contextlib.contextmanager
    def open_session(self, isolation: str | None = None) -> Iterator[_Session]:
        yield next(self._sessions)


class _Db:
    def __init__(self, lock: _Lock) -> None:
        self.lock = lock

    def lock_waits(self) -> int:
        with self.lock.guard:
            return self.lock.waiting


def _run(rounds: list[dict[str, Any]], *, waits: bool) -> tuple[list[str], dict[str, _Session]]:
    lock = _Lock()
    sessions = {node: _Session(node, lock, waits=waits) for node in ("A", "B")}

    def run_step(node: str, session: Any, step: object) -> None:
        if not isinstance(step, dict):
            return
        if step.get("kind") == "commit":
            session.commit()
            return
        for entry in step["statements"]:
            session.execute(entry["sql"]["postgres"], entry["binds"])

    case = _case(_success(rounds))
    failures = _run_concurrency_rounds(case, _Execution(sessions), _Db(lock), rounds, run_step)  # type: ignore[arg-type]
    return failures, sessions


def test_a_blocking_round_ends_on_the_wait_and_its_node_resumes_after_the_release() -> None:
    failures, sessions = _run(_blocking_rounds(), waits=True)
    assert failures == []
    assert sessions["B"].calls == [
        "extend_lock_wait",
        _DELETE["postgres"],
        "commit",
        "rollback",
    ]


def test_a_blocking_step_that_never_waits_fails_the_choreography() -> None:
    failures, _ = _run(_blocking_rounds(), waits=False)
    assert failures == [
        "/concurrency/rounds/1/B: the blocking step's statement never waited on a lock"
    ]
