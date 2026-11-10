"""Case-driven API-suite boundary runner (m-auto-retry / m-concurrency,
m-api-conformance).

ONE parametrized test over EVERY reachable `boundary`-shape corpus case (the
`m-auto-retry`/`m-concurrency`/`m-unit-work` bounded-retry loop-mechanics
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
from parallax.conformance.boundary_runner import (
    BoundaryAbort,
    BoundaryTarget,
    fault_injecting_adapter,
)
from parallax.conformance.class_models import MODELS
from parallax.core import ConflictError, Entity
from parallax.core._execution._unit_work.effects import shortfall
from parallax.core.execution_lifecycle import TransactionAttemptStarted
from parallax.core.internal.base import UsageError
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import AcquisitionReason, ConnectionAcquisitionError
from parallax.core.internal.execution import (
    ServingModel,
    prepare_model,
)
from parallax.core.internal.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.internal.unit_work import OPTIMISTIC_LOCK_CONFLICT
from parallax.core.internal.write_plan.steps import KeyTarget
from parallax.snapshot import ReadOnlyTxnContext, ScopedDatabase, TxnContext, connect
from tests._support.corpus import case_document, case_fixtures
from tests._support.errors import raises_code

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
    target: BoundaryTarget[Any],
    *,
    raise_after: bool,
    db: ScopedDatabase,
    scope_for: Callable[[case_format.ActorSelection], ScopedDatabase],
) -> Any:  # Callable[[Transaction], Entity | None]
    def body(tx: TxnContext | ReadOnlyTxnContext) -> Entity | None:
        result = boundary_runner.run_boundary_actions(
            tx, steps, target, database=db, scope_for=scope_for
        )
        if raise_after:
            raise BoundaryAbort("scripted abort — no injected fault (m-unit-work-004)")
        return result

    return body


def _assert_outcome(
    case: case_format.Case,
    outcome: str,
    run: Callable[[], Entity | None],
    *,
    steps: list[boundary_runner.BoundaryStep],
    target: BoundaryTarget[Any],
    fault: str | None,
    verify_db: ScopedDatabase,
) -> None:
    """Invoke the boundary and assert it ends as ``outcome`` states, leaving the
    persisted amount that outcome implies."""
    if outcome == "committed":
        result = run()
        assert result is not None
        expected_amount = (
            target.committed if any(step.action == "amend" for step in steps) else target.baseline
        )
        assert target.amount(result) == expected_amount
        assert _persisted_amount(verify_db, target) == expected_amount, (
            "the committed write must persist"
        )
    elif outcome == "aborted":
        with pytest.raises(BoundaryAbort):
            run()
        assert _persisted_amount(verify_db, target) == target.baseline, (
            "the withheld, force-flushed write must never persist"
        )
    elif outcome == "optimistic-lock-conflict":
        with raises_code(ConflictError, OPTIMISTIC_LOCK_CONFLICT):
            run()
    elif outcome == "option-conflict":
        with raises_code(UsageError, "transaction-option-conflict"):
            run()
        assert _persisted_amount(verify_db, target) == target.baseline, (
            "a refused joining option dooms the boundary it tried to renegotiate"
        )
    elif outcome == "authority-mismatch":
        with raises_code(UsageError, "transaction-authority-mismatch"):
            run()
    elif outcome == "access-mode-mismatch":
        with raises_code(UsageError, "transaction-access-mode-mismatch") as refused:
            run()
        assert refused.value.code == "transaction-access-mode-mismatch"
        assert _persisted_amount(verify_db, target) == target.baseline, (
            "a refused joining access mode leaves nothing persisted"
        )
    elif outcome == "boundary-failed":
        # The boundary never opened, so what surfaces is the error the port made
        # rather than a classified failure of the work. WHICH error is the fault's
        # own: a refused session setup is a database error carrying no category,
        # because nothing above may read a request the engine would not honor as
        # a contention worth retrying, while an acquisition that granted no
        # connection never reached the database at all and surfaces the
        # acquisition failure itself, which is outside the `m-db-error`
        # categories by contract. Either way the attempt had adopted before it
        # asked the boundary to begin, so the failure is noted with the edition
        # it ran under.
        if fault == "connection-acquisition-failure":
            with pytest.raises(ConnectionAcquisitionError) as unacquired:
                run()
            assert unacquired.value.reason == "preparation_failed", case.case_id
            assert unacquired.value.__notes__ == [_edition_note(case)]
        else:
            with pytest.raises(DatabaseError) as unopened:
                run()
            assert unopened.value.category is None, (case.case_id, unopened.value)
            assert unopened.value.__notes__ == [_edition_note(case)]
    else:
        category = _FAILURE_CATEGORY[outcome]
        with pytest.raises(DatabaseError) as excinfo:
            run()
        assert excinfo.value.category == category, (case.case_id, excinfo.value)


def _edition_note(case: case_format.Case) -> str:
    return f"raised in a transaction under model edition {engine.case_edition(case)!r}"


def _persisted_amount(verify_db: ScopedDatabase, target: BoundaryTarget[Any]) -> Decimal:
    return target.amount(verify_db.transact(target.find))


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
    profile_run.reset(engine.load_case_setup_metamodel(case), case_fixtures(case))
    meta = MODELS[Path(case.model).stem]
    target = boundary_runner.boundary_target(case)

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
    body = _make_body(steps, target, raise_after=raise_after, db=db, scope_for=scope_for)

    def run() -> Entity | None:
        if case_format.access_mode(case) == "read_only":
            return db.read_only(
                body, **case_format.read_only_keywords(requests, where=f"{case.case_id}: when.uow")
            )
        return db.transact(body, **requests)

    _assert_outcome(
        case, outcome, run, steps=steps, target=target, fault=fault, verify_db=verify_db
    )

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
        fault=fault, outcome_kind=outcome, max_retries=effective.retry.max_retries
    ), case.case_id

    then = cast("dict[str, Any]", case_document(case)["then"])
    expected_database_calls = then.get("databaseCalls")
    if expected_database_calls is not None:
        assert observed.database_calls == expected_database_calls, case.case_id

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
    # population): `m-auto-retry-001` and `-004..016`, `m-concurrency-010/011/024/025`, its
    # Transaction-Time-Only analogue `m-temporal-read-011`,
    # `m-unit-work-004`, the isolation pair `m-unit-work-035/036`, the four
    # root-configured join cases `m-unit-work-037/038/040/041`, the root-default
    # resolution case `m-execution-001`, the four read-only and access-mode
    # cases `m-execution-002..005`, and the six
    # `m-execution-lifecycle` spine cases whose observables need an injected
    # fault or a joined boundary — never a hand list at the RUNNER level (the
    # corpus itself drives `_CASES` above); this is a coverage assertion only.
    assert _CASE_IDS
    assert set(_CASE_IDS) == {
        "m-auto-retry-001",
        "m-auto-retry-004",
        "m-auto-retry-005",
        "m-auto-retry-006",
        "m-auto-retry-007",
        "m-auto-retry-008",
        "m-auto-retry-009",
        "m-auto-retry-010",
        "m-auto-retry-011",
        "m-auto-retry-012",
        "m-auto-retry-013",
        "m-auto-retry-014",
        "m-auto-retry-015",
        "m-auto-retry-016",
        "m-execution-001",
        "m-execution-002",
        "m-execution-003",
        "m-execution-004",
        "m-execution-005",
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
        "m-concurrency-010",
        "m-concurrency-011",
        "m-concurrency-024",
        "m-concurrency-025",
        "m-temporal-read-011",
        "m-unit-work-004",
        "m-unit-work-035",
        "m-unit-work-036",
        "m-unit-work-037",
        "m-unit-work-038",
        "m-unit-work-040",
        "m-unit-work-041",
    }


_BASELINE = Decimal("250.00")
_COMMITTED = Decimal("251.00")
_AMOUNT_TARGET = BoundaryTarget[Any](
    find=lambda _tx: None,
    edit=lambda stored: stored,
    amount=lambda stored: stored,
    baseline=_BASELINE,
    committed=_COMMITTED,
)
_AMEND = boundary_runner.BoundaryStep("amend", {})
_CASE = _CASES[0]
_EDITION = engine.case_edition(_CASE)


class _PersistedAmount:
    def __init__(self, amount: Decimal) -> None:
        self._amount = amount

    def transact(self, _find: object) -> Decimal:
        return self._amount


def _returning(result: Decimal | None) -> Callable[[], Entity | None]:
    return lambda: cast("Entity | None", result)


def _failing(failure: Exception, edition: str = _EDITION) -> Callable[[], Entity | None]:
    def run() -> Entity | None:
        failure.add_note(f"raised in a transaction under model edition {edition!r}")
        raise failure

    return run


def _refused(category: str | None) -> DatabaseError:
    return DatabaseError(
        category=cast("Any", category), native_code=None, message="the database refused"
    )


def _unacquired(reason: AcquisitionReason = "preparation_failed") -> ConnectionAcquisitionError:
    return ConnectionAcquisitionError("no connection", reason=reason)


def _conflict() -> ConflictError:
    account = EntityIdentity("parallax.compatibility", "Account")
    target = KeyTarget(key_attributes=(AttributeIdentity(account, "id"),), key_values=((2,),))
    return shortfall(OPTIMISTIC_LOCK_CONFLICT, account, target, 1, 0)


def _grade(
    outcome: str,
    run: Callable[[], Entity | None],
    persisted: Decimal = _BASELINE,
    *,
    amends: bool = False,
    fault: str | None = None,
) -> None:
    _assert_outcome(
        _CASE,
        outcome,
        run,
        steps=[_AMEND] if amends else [],
        target=_AMOUNT_TARGET,
        fault=fault,
        verify_db=cast("ScopedDatabase", _PersistedAmount(persisted)),
    )


_ABORT = BoundaryAbort("scripted")
_OPTION_REFUSAL = UsageError("transaction-option-conflict", "refused")
_AUTHORITY_REFUSAL = UsageError("transaction-authority-mismatch", "refused")
_ACCESS_MODE_REFUSAL = UsageError("transaction-access-mode-mismatch", "refused")
_ACQUISITION_FAULT = "connection-acquisition-failure"


def test_assert_outcome_accepts_each_outcome_ending_as_it_states() -> None:
    _grade("committed", _returning(_BASELINE))
    _grade("committed", _returning(_COMMITTED), _COMMITTED, amends=True)
    _grade("aborted", _failing(_ABORT))
    _grade("optimistic-lock-conflict", _failing(_conflict()))
    _grade("option-conflict", _failing(_OPTION_REFUSAL))
    _grade("authority-mismatch", _failing(_AUTHORITY_REFUSAL))
    _grade("access-mode-mismatch", _failing(_ACCESS_MODE_REFUSAL))
    _grade("boundary-failed", _failing(_unacquired()), fault=_ACQUISITION_FAULT)
    _grade("boundary-failed", _failing(_refused(None)))
    _grade("deadlock", _failing(_refused("deadlock")))


@pytest.mark.parametrize(
    ("outcome", "run", "persisted", "amends", "fault"),
    [
        pytest.param("committed", _returning(None), _BASELINE, False, None, id="committed-nothing"),
        pytest.param(
            "committed", _returning(_BASELINE), _COMMITTED, True, None, id="an-unamended-result"
        ),
        pytest.param(
            "committed", _returning(_COMMITTED), _BASELINE, True, None, id="an-unpersisted-amend"
        ),
        pytest.param("aborted", _failing(_ABORT), _COMMITTED, False, None, id="a-durable-abort"),
        pytest.param(
            "option-conflict",
            _failing(_OPTION_REFUSAL),
            _COMMITTED,
            False,
            None,
            id="a-durable-option-conflict",
        ),
        pytest.param(
            "access-mode-mismatch",
            _failing(_ACCESS_MODE_REFUSAL),
            _COMMITTED,
            False,
            None,
            id="a-durable-access-mode-mismatch",
        ),
        pytest.param(
            "boundary-failed",
            _failing(_unacquired("closed")),
            _BASELINE,
            False,
            _ACQUISITION_FAULT,
            id="another-acquisition-reason",
        ),
        pytest.param(
            "boundary-failed",
            _failing(_unacquired(), "another-edition"),
            _BASELINE,
            False,
            _ACQUISITION_FAULT,
            id="an-acquisition-under-another-edition",
        ),
        pytest.param(
            "boundary-failed",
            _failing(_refused("deadlock")),
            _BASELINE,
            False,
            None,
            id="a-classified-boundary-failure",
        ),
        pytest.param(
            "boundary-failed",
            _failing(_refused(None), "another-edition"),
            _BASELINE,
            False,
            None,
            id="a-boundary-failure-under-another-edition",
        ),
        pytest.param(
            "deadlock",
            _failing(_refused("lockWaitTimeout")),
            _BASELINE,
            False,
            None,
            id="another-failure-category",
        ),
    ],
)
def test_assert_outcome_refuses_a_run_ending_otherwise(
    outcome: str,
    run: Callable[[], Entity | None],
    persisted: Decimal,
    amends: bool,
    fault: str | None,
) -> None:
    with pytest.raises(AssertionError):
        _grade(outcome, run, persisted, amends=amends, fault=fault)


@pytest.mark.parametrize(
    ("outcome", "fault"),
    [
        ("aborted", None),
        ("optimistic-lock-conflict", None),
        ("option-conflict", None),
        ("authority-mismatch", None),
        ("access-mode-mismatch", None),
        ("boundary-failed", _ACQUISITION_FAULT),
        ("boundary-failed", None),
        ("deadlock", None),
    ],
)
def test_assert_outcome_refuses_a_run_that_raised_nothing(outcome: str, fault: str | None) -> None:
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        _grade(outcome, _returning(_BASELINE), fault=fault)


@pytest.mark.parametrize(
    ("outcome", "fault"),
    [
        ("aborted", None),
        ("optimistic-lock-conflict", None),
        ("option-conflict", None),
        ("authority-mismatch", None),
        ("access-mode-mismatch", None),
        ("boundary-failed", _ACQUISITION_FAULT),
        ("boundary-failed", None),
        ("deadlock", None),
    ],
)
def test_assert_outcome_lets_a_failure_of_another_type_escape(
    outcome: str, fault: str | None
) -> None:
    with pytest.raises(ValueError, match="another failure"):
        _grade(outcome, _failing(ValueError("another failure")), fault=fault)
