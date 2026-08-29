"""Case-driven API-suite boundary runner (m-auto-retry / m-opt-lock,
m-api-conformance).

ONE parametrized test over EVERY reachable `boundary`-shape corpus case (the
`m-auto-retry`/`m-opt-lock`/`m-unit-work` bounded-retry loop-mechanics
branches a single-connection harness cannot provoke, `m-case-format`
"Boundary cases"): drives the REAL `db.transact` against the provisioned
database through `parallax.conformance.boundary_runner.FaultInjectingPort`
(wrapping the shipped `parallax-postgres` adapter), and grades `then.outcome`.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from _support.corpus import case_document, case_fixtures
from parallax.conformance import boundary_runner, case_format, engine
from parallax.conformance._lifecycle_observation import (
    LifecycleObservation,
    execution_lifecycle_observation,
)
from parallax.conformance.boundary_runner import BoundaryAbort, FaultInjectingPort
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.db_error import DatabaseError
from parallax.core.execution_lifecycle import TransactionAttemptStarted
from parallax.core.unit_work import OptimisticLockConflictError
from parallax.snapshot import connect
from parallax.snapshot.handle import Transaction

_CASES = boundary_runner.reachable_boundary_cases()
_CASE_IDS = [case.case_id for case in _CASES]

# `then.outcome` -> the neutral error category / type the case's failure kind
# surfaces as (m-db-error vocabulary; the Write Effect Error family for the
# conflict kind).
_FAILURE_CATEGORY: dict[str, str] = {
    "deadlock": "deadlock",
    "serialization-failure": "deadlock",
    "lock-wait-timeout": "lockWaitTimeout",
}


def _make_body(
    actions: list[str], *, raise_after: bool, db: Any
) -> Any:  # Callable[[Transaction], Account | None]
    def body(tx: Transaction) -> Account | None:
        result = boundary_runner.run_boundary_actions(tx, actions, database=db)
        if raise_after:
            raise BoundaryAbort("scripted abort — no injected fault (m-unit-work-004)")
        return result

    return body


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_boundary_case_runs_through_the_shipped_surface(
    case: case_format.Case, profile_run: Any
) -> None:
    profile_run.reset(engine.load_case_metamodel(case), case_fixtures(case))
    meta = MODELS[Path(case.model).stem]

    uow = boundary_runner.boundary_uow(case)
    actions = boundary_runner.boundary_actions(case)
    fault = boundary_runner.fault_kind(case)
    outcome = boundary_runner.outcome(case)
    persistent = fault is not None and outcome != "committed"

    port = FaultInjectingPort(profile_run.port, fault=fault, persistent=persistent)
    # What the boundary did is observable only WHILE it runs: a failing
    # invocation answers no result, and nothing it returns describes what its
    # attempts did (`m-execution-lifecycle` — observability is transient and
    # belongs to an installed Provider). One installed Provider therefore
    # answers all three of this suite's questions — the statements that reached
    # the wire, how many attempts ran, and the event stream the case authors —
    # because all three are projections of one delivery.
    observed = LifecycleObservation()
    db = connect(port, meta, lifecycle_provider=observed.provider)
    # The post-transaction verify read runs through a SEPARATE, un-instrumented
    # `Database` (the real adapter directly, no `FaultInjectingPort`): it is
    # out-of-band housekeeping, not part of the boundary mechanism under test,
    # and driving it through the SAME `port` would arm the fault against it.
    verify_db = connect(profile_run.port, meta)
    raise_after = fault is None and outcome == "aborted"
    body = _make_body(actions, raise_after=raise_after, db=db)

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
        with pytest.raises(OptimisticLockConflictError):
            run()
    else:
        category = _FAILURE_CATEGORY[outcome]
        with pytest.raises(DatabaseError) as excinfo:
            run()
        assert excinfo.value.category == category, (case.case_id, excinfo.value)

    # How many attempts ran is what the boundary itself did — one Transaction
    # Attempt activity is one physical attempt — never a count the fault
    # decorator kept beside it: a second tally could agree with the oracle while
    # the loop did something else. An attempt begins only after a successful
    # begin, so this counts attempts rather than demarcations that never ran one.
    attempts = sum(
        1
        for root in observed.roots
        for event in root.events
        if isinstance(event, TransactionAttemptStarted)
    )
    assert attempts == boundary_runner.expected_attempts(
        fault=fault,
        outcome_kind=outcome,
        retries=uow.retries,
        retry_optimistic_conflicts=uow.retry_optimistic_conflicts,
    ), case.case_id

    then = cast("dict[str, Any]", case_document(case)["then"])
    expected_round_trips = then.get("roundTrips")
    if expected_round_trips is not None:
        assert observed.round_trips == expected_round_trips, case.case_id

    # The stream itself, where the case authors it. A boundary case carries no
    # golden SQL, so every Database Call names its statement by no index at all
    # — `kind` and the outcome are the whole portable oracle here.
    expected_lifecycle = then.get("executionLifecycle")
    if expected_lifecycle is not None:
        assert execution_lifecycle_observation(observed.roots, []) == expected_lifecycle, (
            case.case_id
        )


def test_reachable_boundary_cases_cover_the_expected_eleven() -> None:
    # Grep-verified complete set (the corpus's complete boundary
    # population): `m-auto-retry-001..005`, `m-opt-lock-010/011`,
    # `m-unit-work-004`, and the three `m-execution-lifecycle` spine cases whose
    # observables need an injected fault or a joined boundary — never a hand list
    # at the RUNNER level (the corpus itself drives `_CASES` above); this is a
    # coverage assertion only.
    assert _CASE_IDS
    assert set(_CASE_IDS) == {
        "m-auto-retry-001",
        "m-auto-retry-002",
        "m-auto-retry-003",
        "m-auto-retry-004",
        "m-auto-retry-005",
        "m-execution-lifecycle-004",
        "m-execution-lifecycle-005",
        "m-execution-lifecycle-006",
        "m-opt-lock-010",
        "m-opt-lock-011",
        "m-unit-work-004",
    }
