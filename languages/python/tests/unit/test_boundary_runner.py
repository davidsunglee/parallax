"""``parallax.conformance.boundary_runner`` unit tests (Docker-free fake ports).

Pins the pure pieces the real-database suite (`tests/api/test_boundary_run.py`)
composes against real Postgres: `when.uow`/
`when.boundary`/`given.fault` parsing, the action -> verb mapping (incl. its
branches no reachable corpus case reaches — `create`/`delete`/`terminate`),
the fault-injecting port decorator's firing/attempt-counting behavior, and
the attempt-count formula.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from _support.db_port import body_outcome
from parallax.conformance import boundary_runner, case_format
from parallax.conformance.boundary_runner import FaultInjectingPort
from parallax.conformance.class_models import MODELS
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    Bind,
    Committed,
    DbPort,
    DocumentReadOrdinals,
    Row,
    TransactionOutcome,
)
from parallax.core.unit_work import FixedClock
from parallax.snapshot.handle import Database, Transaction

_ACCOUNT = MODELS["account"]
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _case(document: dict[str, Any], *, case_id: str = "m-auto-retry-900") -> case_format.Case:
    return case_format.Case(
        path=Path(f"{case_id}.yaml"),
        case_id=case_id,
        shape="boundary",
        tags=("m-auto-retry", "slice-snapshot-1"),
        model="models/account.yaml",
        document=document,
    )


# --------------------------------------------------------------------------- #
# when.uow / when.boundary / given.fault / then.outcome parsing.              #
# --------------------------------------------------------------------------- #
def test_boundary_uow_leaves_every_omitted_option_to_db_transact() -> None:
    # A case declaring no `when.uow` supplies no argument at all, so
    # `db.transact` resolves each option itself (`optimistic`, 10 retries, no
    # conflict opt-in) — the runner never restates a default that could drift
    # from production's.
    uow = boundary_runner.boundary_uow(_case({}))
    assert uow.concurrency is None
    assert uow.retries is None
    assert uow.retry_optimistic_conflicts is None


def test_boundary_uow_reads_declared_fields() -> None:
    case = _case(
        {
            "when": {
                "uow": {"concurrency": "optimistic", "retries": 2, "retryOptimisticConflicts": True}
            }
        }
    )
    uow = boundary_runner.boundary_uow(case)
    assert uow.concurrency == "optimistic"
    assert uow.retries == 2
    assert uow.retry_optimistic_conflicts is True


def test_boundary_actions_reads_the_ordered_list() -> None:
    case = _case({"when": {"boundary": [{"action": "read"}, {"action": "update"}]}})
    assert boundary_runner.boundary_actions(case) == ["read", "update"]


def test_fault_kind_absent_is_none() -> None:
    assert boundary_runner.fault_kind(_case({})) is None


def test_fault_kind_reads_the_declared_fault() -> None:
    case = _case({"given": {"fault": "deadlock"}})
    assert boundary_runner.fault_kind(case) == "deadlock"


def test_outcome_reads_the_declared_outcome() -> None:
    case = _case({"then": {"outcome": "committed"}})
    assert boundary_runner.outcome(case) == "committed"


# --------------------------------------------------------------------------- #
# translated_fault: the m-db-error vocabulary the decorator simulates.        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("kind", "category", "native"),
    [
        ("serialization-failure", "deadlock", "40001"),
        ("deadlock", "deadlock", "40P01"),
        ("lock-wait-timeout", "lockWaitTimeout", "55P03"),
    ],
)
def test_translated_fault_matches_the_db_error_vocabulary(
    kind: str, category: str, native: str
) -> None:
    exc = boundary_runner.translated_fault(kind)
    assert exc.category == category
    assert exc.native_code == native


# --------------------------------------------------------------------------- #
# run_boundary_actions: the action -> verb mapping, incl. branches no         #
# reachable corpus case reaches.                                              #
# --------------------------------------------------------------------------- #
class _FakePort:
    def __init__(self, *, rows: list[Row]) -> None:
        self.rows = rows
        self.writes: list[tuple[str, tuple[object, ...]]] = []
        self.ops: list[str] = []
        # One physical transaction attempt is one demarcation (`m-unit-work`),
        # so counting the boundary here is how a retry is observed at all: an
        # invocation retains no record of what it did.
        self.boundaries = 0

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del sql, binds, document_reads
        self.ops.append("read")
        return [dict(row) for row in self.rows]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.writes.append((sql, tuple(binds)))
        self.ops.append("write")
        return 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        self.boundaries += 1
        return body_outcome(self, body)


def _db(port: DbPort) -> Database:
    return Database.connect(port, _ACCOUNT, clock=FixedClock(_FIXED))


def test_run_boundary_actions_read_then_update() -> None:
    port = _FakePort(rows=[{"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}])

    def fn(tx: Transaction) -> Any:
        return boundary_runner.run_boundary_actions(tx, ["read", "update"])

    result = _db(port).transact(fn)
    assert result is not None
    assert result.balance == Decimal("251.00")
    assert len(port.writes) == 1


def test_run_boundary_actions_join_runs_the_rest_inside_a_joined_unit_of_work() -> None:
    # A joined call shares the outer transaction (`m-unit-work`), so the write
    # after the `join` buffers onto the SAME unit of work and reaches the
    # database under the OUTER boundary's pre-commit batch —
    # `m-execution-lifecycle-006`.
    port = _FakePort(rows=[{"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}])
    db = _db(port)

    def fn(tx: Transaction) -> Any:
        return boundary_runner.run_boundary_actions(tx, ["read", "join", "update"], database=db)

    result = db.transact(fn)
    assert result is not None
    assert result.balance == Decimal("251.00")
    assert len(port.writes) == 1
    # One boundary: the join opened no second transaction, and its buffered
    # write reached the database after the read, under the outer boundary.
    assert port.boundaries == 1
    assert port.ops == ["read", "write"]


def test_a_join_without_the_owning_database_is_refused() -> None:
    port = _FakePort(rows=[])

    def fn(tx: Transaction) -> Any:
        return boundary_runner.run_boundary_actions(tx, ["join"])

    with pytest.raises(AssertionError, match="needs the Database that opened the boundary"):
        _db(port).transact(fn)


def test_run_boundary_actions_create() -> None:
    port = _FakePort(rows=[])

    def fn(tx: Transaction) -> Any:
        return boundary_runner.run_boundary_actions(tx, ["create"])

    result = _db(port).transact(fn)
    assert result is not None
    assert result.id == 90
    assert len(port.writes) == 1


def test_run_boundary_actions_read_then_delete() -> None:
    port = _FakePort(rows=[{"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}])

    def fn(tx: Transaction) -> Any:
        return boundary_runner.run_boundary_actions(tx, ["read", "delete"])

    result = _db(port).transact(fn)
    assert result is None
    assert len(port.writes) == 1


def test_run_boundary_actions_terminate_refuses() -> None:
    port = _FakePort(rows=[])

    def fn(tx: Transaction) -> Any:
        return boundary_runner.run_boundary_actions(tx, ["terminate"])

    with pytest.raises(AssertionError, match="no legal target"):
        _db(port).transact(fn)


def test_run_boundary_actions_update_without_a_prior_read_raises() -> None:
    port = _FakePort(rows=[])

    def fn(tx: Transaction) -> Any:
        return boundary_runner.run_boundary_actions(tx, ["update"])

    with pytest.raises(AssertionError, match="prior `read`"):
        _db(port).transact(fn)


def test_run_boundary_actions_delete_without_a_prior_read_raises() -> None:
    port = _FakePort(rows=[])

    def fn(tx: Transaction) -> Any:
        return boundary_runner.run_boundary_actions(tx, ["delete"])

    with pytest.raises(AssertionError, match="prior `read`"):
        _db(port).transact(fn)


# --------------------------------------------------------------------------- #
# FaultInjectingPort: firing and persistence.                                 #
# --------------------------------------------------------------------------- #
def test_fault_injecting_port_fires_once_by_default() -> None:
    inner = _FakePort(rows=[])
    port = FaultInjectingPort(inner, fault="deadlock", persistent=False)
    with pytest.raises(DatabaseError):
        port.execute_write("update x set y = 1", [])
    # A second call, same instance: the state already fired, so it passes through.
    assert port.execute_write("update x set y = 1", []) == 1


def test_fault_injecting_port_fires_every_attempt_when_persistent() -> None:
    inner = _FakePort(rows=[])
    port = FaultInjectingPort(inner, fault="deadlock", persistent=True)
    with pytest.raises(DatabaseError):
        port.execute_write("update x set y = 1", [])
    with pytest.raises(DatabaseError):
        port.execute_write("update x set y = 1", [])


def test_fault_injecting_port_optimistic_conflict_returns_zero_never_raises() -> None:
    inner = _FakePort(rows=[])
    port = FaultInjectingPort(inner, fault="optimistic-lock-conflict", persistent=False)
    assert port.execute_write("update x set version = 2 where id = 1 and version = 1", []) == 0
    # The inner (real) port never saw the faulted call.
    assert inner.writes == []
    # The next call passes through to the inner port.
    assert port.execute_write("update x set version = 2 where id = 1 and version = 1", []) == 1
    assert inner.writes == [("update x set version = 2 where id = 1 and version = 1", ())]


def test_fault_injecting_port_no_fault_passes_reads_and_writes_through() -> None:
    inner = _FakePort(rows=[{"id": 1}])
    port = FaultInjectingPort(inner, fault=None, persistent=False)
    assert port.execute("select 1", []) == [{"id": 1}]
    assert port.execute_write("update x set y = 1", []) == 1


def test_fault_injecting_port_delegates_every_transaction_call() -> None:
    inner = _FakePort(rows=[])
    port = FaultInjectingPort(inner, fault=None, persistent=False)

    def body(_conn: DbPort) -> str:
        return "ok"

    assert port.transaction(body) == Committed("ok")
    assert port.transaction(body) == Committed("ok")


def test_fault_injecting_port_state_survives_nested_transaction_wrapping() -> None:
    # `_db(port).transact(...)`'s own retry loop calls `.transaction()` fresh
    # per attempt on the TOP-LEVEL port; each call wraps a NESTED copy sharing
    # the SAME `_state` — a deadlock on attempt 1 (one-shot) is retried away.
    inner = _FakePort(
        rows=[{"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}]
    )
    port = FaultInjectingPort(inner, fault="deadlock", persistent=False)
    db = _db(port)

    def fn(tx: Transaction) -> Any:
        return boundary_runner.run_boundary_actions(tx, ["read", "update"])

    result = db.transact(fn)
    assert result is not None
    assert result.balance == Decimal("251.00")
    # The faulted attempt, then the retried (successful) one — counted at the
    # boundary each attempt opens, which is what the retry loop produced.
    assert inner.boundaries == 2


# --------------------------------------------------------------------------- #
# expected_attempts: derived from m-auto-retry.md / m-opt-lock.md's own       #
# retriability rules, never a per-case hand table — exercised over the real   #
# corpus's own 8 combinations plus the branches they don't cover.             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _AttemptsCase:
    fault: str | None
    outcome_kind: str
    retries: int | None
    retry_optimistic_conflicts: bool | None
    expected: int


_ATTEMPTS_CASES: list[_AttemptsCase] = [
    # m-auto-retry-001/002: transient, first-attempt-only (don't-care), committed.
    _AttemptsCase("serialization-failure", "committed", None, False, 2),
    _AttemptsCase("serialization-failure", "committed", None, True, 2),
    # m-auto-retry-003: no fault at all.
    _AttemptsCase(None, "committed", None, True, 1),
    # m-auto-retry-004: retries: 0 disables the loop.
    _AttemptsCase("serialization-failure", "serialization-failure", 0, False, 1),
    # m-auto-retry-005: persistent, bound exhausted.
    _AttemptsCase("serialization-failure", "serialization-failure", 2, False, 3),
    # m-opt-lock-010: conflict without the opt-in — not retriable.
    _AttemptsCase("optimistic-lock-conflict", "optimistic-lock-conflict", None, False, 1),
    # m-opt-lock-011: conflict with the opt-in — retried to success.
    _AttemptsCase("optimistic-lock-conflict", "committed", None, True, 2),
    # An omitted `retryOptimisticConflicts` reaches the oracle as `None` and
    # resolves to the same off posture an explicit `false` declares.
    _AttemptsCase("optimistic-lock-conflict", "optimistic-lock-conflict", None, None, 1),
    # m-unit-work-004: no fault, the scripted closure itself aborts.
    _AttemptsCase(None, "aborted", None, False, 1),
    # lock-wait-timeout is never retriable, opt-in or not.
    _AttemptsCase("lock-wait-timeout", "lock-wait-timeout", None, True, 1),
]


@pytest.mark.parametrize("case", _ATTEMPTS_CASES)
def test_expected_attempts(case: _AttemptsCase) -> None:
    assert (
        boundary_runner.expected_attempts(
            fault=case.fault,
            outcome_kind=case.outcome_kind,
            retries=case.retries,
            retry_optimistic_conflicts=case.retry_optimistic_conflicts,
        )
        == case.expected
    )


# --------------------------------------------------------------------------- #
# reachable_boundary_cases: shape filtering.                                  #
# --------------------------------------------------------------------------- #
def test_reachable_boundary_cases_filters_by_shape() -> None:
    boundary = _case({}, case_id="m-auto-retry-901")
    other = case_format.Case(
        path=Path("m-core-001.yaml"),
        case_id="m-core-001",
        shape="read",
        tags=("m-core", "slice-snapshot-1"),
        model="models/grade.yaml",
        document={},
    )
    assert boundary_runner.reachable_boundary_cases([boundary, other]) == [boundary]


def test_reachable_boundary_cases_defaults_to_the_loaded_corpus() -> None:
    cases = boundary_runner.reachable_boundary_cases()
    assert cases
    assert all(case.shape == "boundary" for case in cases)
