"""Case-driven API-suite boundary runner (m-auto-retry / m-opt-lock,
m-api-conformance).

ONE parametrized test over EVERY reachable `boundary`-shape corpus case (the
`m-auto-retry`/`m-opt-lock`/`m-unit-work` bounded-retry loop-mechanics
branches a single-connection harness cannot provoke, `m-case-format`
"Boundary cases"): drives the REAL `db.transact` against the provisioned
database through `parallax.conformance.boundary_runner`'s fault-injecting adapter
(wrapping the shipped `parallax-postgres` adapter), and grades `then.outcome`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import boundary_runner, case_format, engine
from parallax.conformance._lifecycle_observation import (
    LifecycleObservation,
    execution_lifecycle_observation,
)
from parallax.conformance.boundary_runner import BoundaryAbort, fault_injecting_adapter
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import ConnectionAcquisitionError
from parallax.core.execution_lifecycle import TransactionAttemptStarted
from parallax.core.unit_work import OptimisticLockConflictError
from parallax.snapshot import ServingModel, connect, prepare_model
from parallax.snapshot.handle import (
    ScopedDatabase,
    Transaction,
    TransactionAuthorityError,
    TransactionOptionConflictError,
)
from tests._support.adoption import raises_contextualized
from tests._support.corpus import case_document, case_fixtures

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


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: object


def _make_body(
    steps: list[boundary_runner.BoundaryStep],
    *,
    raise_after: bool,
    db: ScopedDatabase,
    scope_for: Callable[[case_format.ActorSelection], ScopedDatabase],
) -> Any:  # Callable[[Transaction], Account | None]
    def body(tx: Transaction) -> Account | None:
        result = boundary_runner.run_boundary_actions(tx, steps, database=db, scope_for=scope_for)
        if raise_after:
            raise BoundaryAbort("scripted abort — no injected fault (m-unit-work-004)")
        return result

    return body


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_boundary_case_runs_through_the_shipped_surface(
    case: case_format.Case, profile_run: Any, request: pytest.FixtureRequest
) -> None:
    dialect = profile_run.port.dialect
    outcome = boundary_runner.outcome(case, dialect)
    if outcome is None:
        # A dialect the case's own outcome map omits is one it makes no claim
        # about (`m-case-format`), so there is nothing here to grade — the same
        # rule a dialect-keyed `then.sql` already carries.
        pytest.skip(f"{case.case_id} states no outcome for {dialect.name}")
    profile_run.reset(engine.load_case_metamodel(case), case_fixtures(case))
    meta = MODELS[Path(case.model).stem]

    # Two seams, each carried its own way: the root record the case configures
    # goes to `connect`, and exactly the fields `when.uow` authored go to the
    # call, so an omitted one reaches production omitted and is resolved there
    # — against that root — rather than restated here.
    root = case_format.database_options(case)
    requests = case_format.transaction_keywords(case)
    steps = boundary_runner.boundary_steps(case)
    fault = boundary_runner.fault_kind(case)
    persistent = fault is not None and outcome != "committed"

    # A case declaring `given.sessionDefault` runs through configuration whose
    # connections carry that default before the adapter initializes one, which
    # is the intake seam the obligation names; every other case runs through the
    # provisioned configuration.
    default = boundary_runner.session_default(case)
    configured = (
        profile_run.port if default is None else profile_run.adapter_for_session_default(default)
    )
    # The fault is armed where the connection is acquired, so it is one fault
    # across the whole retry loop rather than one per attempt.
    port = fault_injecting_adapter(configured, fault=fault, persistent=persistent)
    # What the boundary did is observable only WHILE it runs: a failing
    # invocation answers no result, and nothing it returns describes what its
    # attempts did (`m-execution-lifecycle` — observability is transient and
    # belongs to an installed Provider). One installed Provider therefore
    # answers all three of this suite's questions — the statements that reached
    # the wire, how many attempts ran, and the event stream the case authors —
    # because all three are projections of one delivery.
    observed = LifecycleObservation()
    # Prepared explicitly under the case's own edition — the model descriptor's
    # stem — so the attempt events the case authors carry the literal it names
    # (`m-conformance-adapter`).
    serving = ServingModel(prepare_model(meta, edition=engine.case_edition(case)))
    database_root = connect(port, serving, options=root, lifecycle_provider=observed.provider)
    request.addfinalizer(database_root.close)

    scopes: dict[int, ScopedDatabase] = {}

    def scope_for(selection: case_format.ActorSelection) -> ScopedDatabase:
        key = id(selection)
        if key not in scopes:
            if isinstance(selection, case_format.SubjectSelection):
                principal = _Principal(
                    selection.subject,
                    profile_run.authorization(selection.database_authorization),
                )
                scopes[key] = database_root.using_principal(principal)
            else:
                scopes[key] = database_root.using_database_login()
        return scopes[key]

    outer_selection = case_format.actor_selection(case)
    db = (
        database_root.using_database_login()
        if outer_selection is None
        else scope_for(outer_selection)
    )
    # The post-transaction verify read runs through a SEPARATE, un-instrumented
    # `Database` (the real adapter directly, no `FaultInjectingPort`): it is
    # out-of-band housekeeping, not part of the boundary mechanism under test,
    # and driving it through the SAME `port` would arm the fault against it.
    verify_root = connect(profile_run.port, meta)
    request.addfinalizer(verify_root.close)
    verify_db = verify_root.using_database_login()
    raise_after = fault is None and outcome == "aborted"
    body = _make_body(steps, raise_after=raise_after, db=db, scope_for=scope_for)

    def run() -> Account | None:
        return db.transact(body, **requests)

    if outcome == "committed":
        result = run()
        assert result is not None
        expected_balance = (
            Decimal("251.00")
            if any(step.action == "update" for step in steps)
            else Decimal("250.00")
        )
        assert result.balance == expected_balance
        verify = verify_db.transact(
            lambda tx: tx.find(Account.where(Account.id == boundary_runner.TARGET_ID)).result()
        )
        assert verify.balance == expected_balance, "the committed write must persist"
    elif outcome == "aborted":
        with raises_contextualized(BoundaryAbort):
            run()
        verify = verify_db.transact(
            lambda tx: tx.find(Account.where(Account.id == boundary_runner.TARGET_ID)).result()
        )
        assert verify.balance == Decimal("250.00"), (
            "the withheld, force-flushed write must never persist"
        )
    elif outcome == "optimistic-lock-conflict":
        with raises_contextualized(OptimisticLockConflictError):
            run()
    elif outcome == "option-conflict":
        with raises_contextualized(TransactionOptionConflictError):
            run()
        verify = verify_db.transact(
            lambda tx: tx.find(Account.where(Account.id == boundary_runner.TARGET_ID)).result()
        )
        assert verify.balance == Decimal("250.00"), (
            "a refused joining option dooms the boundary it tried to renegotiate"
        )
    elif outcome == "authority-mismatch":
        with raises_contextualized(TransactionAuthorityError):
            run()
    elif outcome == "boundary-failed":
        # The boundary never opened, so what surfaces is the error the port made
        # rather than a classified failure of the work. WHICH error is the fault's
        # own: a refused session setup is a database error carrying no category,
        # because nothing above may read a request the engine would not honor as
        # a contention worth retrying, while an acquisition that granted no
        # connection never reached the database at all and surfaces the
        # acquisition failure itself, which is outside the `m-db-error`
        # categories by contract. Either way the attempt had adopted before it
        # asked the boundary to begin, so the failure names the edition it ran
        # under.
        if fault == "connection-acquisition-failure":
            with raises_contextualized(ConnectionAcquisitionError) as unacquired:
                run()
            assert unacquired.value.reason == "preparation_failed", case.case_id
            assert unacquired.edition == engine.case_edition(case)
        else:
            with raises_contextualized(DatabaseError) as unopened:
                run()
            assert unopened.value.category is None, (case.case_id, unopened.value)
            assert unopened.edition == engine.case_edition(case)
    else:
        category = _FAILURE_CATEGORY[outcome]
        with raises_contextualized(DatabaseError) as excinfo:
            run()
        assert excinfo.value.category == category, (case.case_id, excinfo.value)

    # How many attempts ran is what the boundary itself did — one Transaction
    # Attempt activity is one physical attempt — never a count the fault
    # decorator kept beside it: a second tally could agree with the oracle while
    # the loop did something else. An attempt starts before its boundary is
    # asked to begin, so a boundary that never opened is one attempt too.
    attempts = sum(
        1
        for execution in observed.roots
        for event in execution.events
        if isinstance(event, TransactionAttemptStarted)
    )
    # The oracle resolves the same two values for itself — the authored request
    # over the configured root — and compares; nothing it resolves reaches the
    # call above.
    effective = case_format.effective_options(case)
    assert attempts == boundary_runner.expected_attempts(
        fault=fault,
        outcome_kind=outcome,
        max_retries=effective.max_retries,
        retry_optimistic_conflicts=effective.retry_optimistic_conflicts,
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


def test_reachable_boundary_cases_cover_the_expected_population() -> None:
    # Grep-verified complete set (the corpus's complete boundary
    # population): `m-auto-retry-001..011`, `m-opt-lock-010/011/024/025`,
    # `m-unit-work-004`, the isolation pair `m-unit-work-035/036`, the five
    # root-configured join cases `m-unit-work-037..041`, and the six
    # `m-execution-lifecycle` spine cases whose observables need an injected
    # fault or a joined boundary — never a hand list at the RUNNER level (the
    # corpus itself drives `_CASES` above); this is a coverage assertion only.
    assert _CASE_IDS
    assert set(_CASE_IDS) == {
        "m-auto-retry-001",
        "m-auto-retry-002",
        "m-auto-retry-003",
        "m-auto-retry-004",
        "m-auto-retry-005",
        "m-auto-retry-006",
        "m-auto-retry-007",
        "m-auto-retry-008",
        "m-auto-retry-009",
        "m-auto-retry-010",
        "m-auto-retry-011",
        "m-execution-lifecycle-004",
        "m-execution-lifecycle-005",
        "m-execution-lifecycle-006",
        "m-execution-lifecycle-008",
        "m-execution-lifecycle-009",
        "m-execution-lifecycle-010",
        "m-execution-authority-001",
        "m-execution-authority-002",
        "m-execution-authority-003",
        "m-execution-authority-004",
        "m-execution-authority-005",
        "m-opt-lock-010",
        "m-opt-lock-011",
        "m-opt-lock-024",
        "m-opt-lock-025",
        "m-unit-work-004",
        "m-unit-work-035",
        "m-unit-work-036",
        "m-unit-work-037",
        "m-unit-work-038",
        "m-unit-work-039",
        "m-unit-work-040",
        "m-unit-work-041",
    }
