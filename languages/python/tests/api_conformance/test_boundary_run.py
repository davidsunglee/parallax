"""Case-driven API-suite boundary runner (m-auto-retry / m-opt-lock, D-17;
COR-3 Phase 8 increment 6, m-api-conformance).

ONE parametrized test over EVERY reachable `boundary`-shape corpus case (the
`m-auto-retry`/`m-opt-lock`/`m-unit-work` bounded-retry loop-mechanics
branches a single-connection harness cannot provoke, `m-case-format`
"Boundary cases"): drives the REAL `db.transact` against the provisioned
database through `parallax.conformance.boundary_runner.FaultInjectingPort`
(wrapping the shipped `parallax-postgres` adapter), and grades `then.outcome`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from conftest import case_fixtures
from parallax.conformance import boundary_runner, case_format, engine
from parallax.conformance.boundary_runner import BoundaryAbort, FaultInjectingPort
from parallax.conformance.story_models import Account
from parallax.core import opt_lock
from parallax.core.db_error import DatabaseError
from parallax.snapshot import connect
from parallax.snapshot.handle import Transaction

pytestmark = pytest.mark.api_conformance

_CASES = boundary_runner.reachable_boundary_cases()
_CASE_IDS = [case.case_id for case in _CASES]

# `then.outcome` -> the neutral error category / type the case's failure kind
# surfaces as (m-db-error vocabulary; `opt_lock` for the conflict kind).
_FAILURE_CATEGORY: dict[str, str] = {
    "deadlock": "deadlock",
    "serialization-failure": "deadlock",
    "lock-wait-timeout": "lockWaitTimeout",
}


def _make_body(
    actions: list[str], *, raise_after: bool
) -> Any:  # Callable[[Transaction], Account | None]
    def body(tx: Transaction) -> Account | None:
        result = boundary_runner.run_boundary_actions(tx, actions)
        if raise_after:
            raise BoundaryAbort("scripted abort — no injected fault (m-unit-work-004)")
        return result

    return body


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_boundary_case_runs_through_the_shipped_surface(
    case: case_format.Case, provisioner: Any
) -> None:
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, case_fixtures(case))

    uow = boundary_runner.boundary_uow(case)
    actions = boundary_runner.boundary_actions(case)
    fault = boundary_runner.fault_kind(case)
    outcome = boundary_runner.outcome(case)
    persistent = fault is not None and outcome != "committed"

    port = FaultInjectingPort(provisioner.port, fault=fault, persistent=persistent)
    db = connect(port, meta)
    # The post-transaction verify read runs through a SEPARATE, un-instrumented
    # `Database` (the real adapter directly, no `FaultInjectingPort`): it is
    # out-of-band housekeeping, not part of the boundary mechanism under test,
    # and driving it through the SAME `port` would inflate `port.attempts`
    # beyond what `expected_attempts` (the MAIN `run()` call's own count)
    # predicts.
    verify_db = connect(provisioner.port, meta)
    raise_after = fault is None and outcome == "aborted"
    body = _make_body(actions, raise_after=raise_after)

    def run() -> Account | None:
        return db.transact(
            body,
            retries=uow.retries,
            concurrency=uow.concurrency,
            retry_optimistic_conflicts=uow.retry_optimistic_conflicts,
        )

    if outcome == "committed":
        result = run()
        assert result is not None
        assert result.balance == Decimal("251.00")  # 250.00 + one successful bump (m-opt-lock)
        verify = verify_db.transact(
            lambda tx: tx.find(Account.where(Account.id == boundary_runner.TARGET_ID)).result()
        )
        assert verify.balance == Decimal("251.00"), "the committed write must persist"
    elif outcome == "aborted":
        with pytest.raises(BoundaryAbort):
            run()
        verify = verify_db.transact(
            lambda tx: tx.find(Account.where(Account.id == boundary_runner.TARGET_ID)).result()
        )
        assert verify.balance == Decimal("250.00"), (
            "the withheld, force-flushed write must never persist"
        )
    elif outcome == "optimistic-lock-conflict":
        with pytest.raises(opt_lock.OptimisticLockConflictError):
            run()
    else:
        category = _FAILURE_CATEGORY[outcome]
        with pytest.raises(DatabaseError) as excinfo:
            run()
        assert excinfo.value.category == category, (case.case_id, excinfo.value)

    assert port.attempts == boundary_runner.expected_attempts(
        fault=fault,
        outcome_kind=outcome,
        retries=uow.retries,
        retry_optimistic_conflicts=uow.retry_optimistic_conflicts,
    ), case.case_id


def test_reachable_boundary_cases_cover_the_expected_eight() -> None:
    # Grep-verified complete set (D-17's own "the corpus's complete boundary
    # population" check): `m-auto-retry-001..005`, `m-opt-lock-010/011`,
    # `m-unit-work-004` — never a hand list at the RUNNER level (the corpus
    # itself drives `_CASES` above); this is a coverage assertion only.
    assert _CASE_IDS
    assert set(_CASE_IDS) == {
        "m-auto-retry-001",
        "m-auto-retry-002",
        "m-auto-retry-003",
        "m-auto-retry-004",
        "m-auto-retry-005",
        "m-opt-lock-010",
        "m-opt-lock-011",
        "m-unit-work-004",
    }
