"""``parallax.conformance.boundary_runner`` unit tests (Docker-free fake ports).

Pins what the real-database suite (`tests/api/test_boundary_run.py`) composes
but cannot observe: the `given.sessionDefault` reading no case's outcome
reveals, the `then.outcome` map, the fault-injecting decorators' firing at
every seam, and the attempt-count formula.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import boundary_runner, case_format
from parallax.conformance.boundary_runner import (
    FaultInjectingPort,
    ResourceFaultingContext,
    fault_injecting_adapter,
)
from parallax.conformance.class_models import MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core.internal.base import UsageError
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import (
    BeginFailed,
    Bind,
    ConnectionAcquisitionError,
    DatabaseAdapter,
    DatabaseConnection,
    DocumentReadOrdinals,
    Invalidated,
    MappingRow,
    OrderedWriteResultComplete,
    OrderedWriteResultInterrupted,
    ReleaseUnconfirmed,
    Returned,
    RouteCapabilities,
    RouteSelection,
    Row,
    StatementFailed,
    StatementNotExecuted,
    TransactionOutcome,
)
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.core.internal.execution import (
    AdaptiveBackoff,
    RetryPolicy,
    TxnOptions,
)
from parallax.core.internal.sql_gen import LoweredStatement
from parallax.snapshot import Database, ScopedDatabase, TxnContext
from tests._support.case_corpus import case as corpus_case
from tests._support.db_port import (
    ConnectsAsItself,
    Ordered,
    OrderedCall,
    ScriptedAdapter,
    ScriptEntry,
    Transact,
    WriteCall,
    body_outcome,
)
from tests._support.errors import raises_code
from tests._support.root_ownership import own_root

_ACCOUNT = MODELS["account"]
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def _steps(*actions: str) -> list[boundary_runner.BoundaryStep]:
    """The steps a body of plain actions runs, none of them naming an option."""
    return [boundary_runner.BoundaryStep(action, {}) for action in actions]


def _case(
    document: dict[str, Any],
    *,
    case_id: str = "m-auto-retry-900",
    model: str = "models/account.yaml",
) -> case_format.Case:
    return case_format.Case(
        path=Path(f"{case_id}.yaml"),
        case_id=case_id,
        shape="boundary",
        tags=("m-auto-retry", "slice-snapshot-1"),
        model=model,
        document=document,
    )


_ACCOUNT_TARGET = boundary_runner.boundary_target(_case({}))


# --------------------------------------------------------------------------- #
# given.sessionDefault / then.outcome reading.                                #
# --------------------------------------------------------------------------- #


def test_session_default_absent_is_none() -> None:
    assert boundary_runner.session_default(_case({})) is None


def test_session_default_reads_the_declared_default() -> None:
    case = _case({"given": {"sessionDefault": "read-uncommitted"}})
    assert boundary_runner.session_default(case) == "read-uncommitted"


def test_outcome_reads_the_declared_outcome() -> None:
    case = _case({"then": {"outcome": "committed"}})
    assert boundary_runner.outcome(case, POSTGRES) == "committed"


def test_outcome_reads_the_running_dialects_entry_of_a_keyed_map() -> None:
    case = _case({"then": {"outcome": {"postgres": "committed", "mariadb": "connection-refused"}}})
    assert boundary_runner.outcome(case, POSTGRES) == "committed"


def test_outcome_of_a_dialect_the_map_omits_is_absent() -> None:
    # A dialect the map omits is one the case makes no claim about, which is a
    # different answer from an outcome it expects — the runner skips rather than
    # grading a promise the case never made.
    case = _case({"then": {"outcome": {"mariadb": "connection-refused"}}})
    assert boundary_runner.outcome(case, POSTGRES) is None


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


def test_translated_isolation_setup_failure_classifies_to_no_category() -> None:
    # A refused session setup is a request the engine would not honor, not a
    # contention: leaving it uncategorized is what keeps the retry loop from
    # reading it as retriable.
    exc = boundary_runner.translated_fault("isolation-setup-failure")
    assert exc.category is None
    assert exc.native_code == "22023"
    assert exc.is_transient is False


# --------------------------------------------------------------------------- #
# run_boundary_actions: the action -> verb mapping, incl. branches no         #
# reachable corpus case reaches.                                              #
# --------------------------------------------------------------------------- #
class _FakePort(ConnectsAsItself):
    dialect: Dialect = POSTGRES

    def __init__(self, *, rows: list[MappingRow]) -> None:
        self.rows = rows
        self.writes: list[tuple[str, tuple[object, ...]]] = []
        # One physical transaction attempt is one demarcation (`m-unit-work`),
        # so counting the boundary here is how a retry is observed at all: an
        # invocation retains no record of what it did. The level each boundary
        # was asked for is kept beside the count, because no lifecycle event
        # states an attempt's own level.
        self.boundaries = 0
        self.levels: list[str | None] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        del sql, binds, document_reads
        return [tuple(row.values()) for row in self.rows]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.writes.append((sql, tuple(binds)))
        return 1

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        self.boundaries += 1
        self.levels.append(isolation)
        return body_outcome(self, body)


def _faulted(
    adapter: DatabaseAdapter[Any], *, fault: str | None, persistent: bool
) -> DatabaseAdapter[Any]:
    """``adapter`` with ``fault`` armed on every connection it acquires."""
    return fault_injecting_adapter(adapter, fault=fault, persistent=persistent)


def _db(adapter: DatabaseAdapter[Any]) -> ScopedDatabase:
    return own_root(
        Database.connect(adapter, _ACCOUNT, clock=FixedClock(_FIXED))
    ).using_database_login()


def _context(runtime: Any) -> Any:
    return runtime.login_source().new_context("writer_only")


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


def test_fault_injecting_port_answers_a_setup_failure_as_a_boundary_never_opened() -> None:
    # The one fault that is not a failure of the WORK: it is ANSWERED at the
    # boundary seam rather than raised at the write seam, so the inner port is
    # never asked to open anything and the body never runs.
    inner = _FakePort(rows=[])
    port = FaultInjectingPort(inner, fault="isolation-setup-failure", persistent=False)
    ran: list[str] = []

    def body(_conn: DatabaseConnection) -> str:
        ran.append("body")  # pragma: no cover - the body must never run
        return "unreachable"

    outcome = port.transaction(body, isolation="serializable")
    assert isinstance(outcome, BeginFailed)
    unopened = outcome.error
    assert isinstance(unopened, DatabaseError)
    assert unopened.native_code == "22023"
    assert inner.boundaries == 0
    assert ran == []


def test_an_access_mode_setup_failure_is_a_boundary_that_never_opened() -> None:
    inner = _FakePort(rows=[])
    port = FaultInjectingPort(inner, fault="access-mode-setup-failure", persistent=False)
    outcome = port.transaction(lambda _conn: "unreachable", access_mode="read_only")
    assert isinstance(outcome, BeginFailed)
    unopened = outcome.error
    assert isinstance(unopened, DatabaseError)
    assert unopened.category is None
    assert inner.boundaries == 0


def test_a_setup_failure_leaves_the_write_seam_alone() -> None:
    # The kinds do not overlap: a fault answered at the boundary is not also
    # raised at the write seam, which would report one failure twice.
    inner = _FakePort(rows=[])
    port = FaultInjectingPort(inner, fault="isolation-setup-failure", persistent=False)
    assert port.execute_write("update x set y = 1", []) == 1


def test_a_setup_failure_surfaces_terminally_after_one_attempt() -> None:
    # A boundary that never opened ran no callback, so `db.transact` surfaces
    # the port's own error rather than retrying it, however the loop is
    # configured.
    inner = _FakePort(rows=[])

    def fn(tx: TxnContext) -> Any:
        return boundary_runner.run_boundary_actions(tx, _steps("read"), _ACCOUNT_TARGET)

    with pytest.raises(DatabaseError) as unopened:
        _db(_faulted(inner, fault="isolation-setup-failure", persistent=False)).transact(
            fn, isolation="serializable"
        )
    assert unopened.value.category is None
    assert inner.boundaries == 0


_PRESENTED: tuple[LoweredStatement, ...] = (
    LoweredStatement("update x set y = ? where id = ?", (1, 1)),
    LoweredStatement("update x set y = ? where id = ?", (2, 2)),
    LoweredStatement("delete from x where id = ?", (3,)),
)


def _presented(*statements: LoweredStatement) -> OrderedCall:
    return OrderedCall(
        tuple(
            WriteCall(POSTGRES.to_driver_sql(statement.sql), statement.binds)
            for statement in statements
        )
    )


def _ordered_port(
    fault: str | None, *script: ScriptEntry
) -> tuple[FaultInjectingPort, ScriptedAdapter]:
    inner = ScriptedAdapter(*script, ordered=True)
    return FaultInjectingPort(inner, fault=fault, persistent=False), inner


def test_a_raised_fault_fails_the_first_statement_and_executes_none_after_it() -> None:
    port, inner = _ordered_port("deadlock")
    transport = port.ordered_write_transport
    assert transport is not None
    result = transport(_PRESENTED)
    assert isinstance(result, OrderedWriteResultComplete)
    failed, *skipped = result.outcomes
    assert isinstance(failed, StatementFailed)
    assert isinstance(failed.error, DatabaseError)
    assert failed.error.category == "deadlock"
    assert skipped == [StatementNotExecuted(), StatementNotExecuted()]
    assert inner.calls == []
    # Fired once: the next invocation reaches the inner port.
    with pytest.raises(AssertionError, match="unscripted ordered"):
        transport(_PRESENTED)


def test_a_conflict_matches_no_row_for_the_first_statement_and_runs_the_rest() -> None:
    port, inner = _ordered_port(
        "optimistic-lock-conflict", Ordered(OrderedWriteResultComplete((1, 1)))
    )
    transport = port.ordered_write_transport
    assert transport is not None
    assert transport(_PRESENTED) == OrderedWriteResultComplete((0, 1, 1))
    assert inner.calls == [_presented(*_PRESENTED[1:])]


def test_a_conflict_on_a_lone_statement_reaches_no_inner_port() -> None:
    port, inner = _ordered_port("optimistic-lock-conflict")
    transport = port.ordered_write_transport
    assert transport is not None
    assert transport(_PRESENTED[:1]) == OrderedWriteResultComplete((0,))
    assert inner.calls == []


def test_a_conflict_keeps_the_interruption_the_rest_of_the_invocation_met() -> None:
    lost = DatabaseError(category=None, native_code="08006", message="connection lost")
    port, _inner = _ordered_port(
        "optimistic-lock-conflict", Ordered(OrderedWriteResultInterrupted((1,), 1, 0, lost))
    )
    transport = port.ordered_write_transport
    assert transport is not None
    assert transport(_PRESENTED) == OrderedWriteResultInterrupted((0, 1), 1, 0, lost)


def test_the_transaction_callbacks_connection_keeps_the_ordered_interception() -> None:
    port, _inner = _ordered_port("deadlock", Transact())
    seen: list[DatabaseConnection] = []

    def body(connection: DatabaseConnection) -> None:
        seen.append(connection)

    port.transaction(body)
    (connection,) = seen
    assert isinstance(connection, FaultInjectingPort)
    transport = connection.ordered_write_transport
    assert transport is not None
    result = transport(_PRESENTED[:1])
    assert isinstance(result, OrderedWriteResultComplete)
    assert isinstance(result.outcomes[0], StatementFailed)


# --------------------------------------------------------------------------- #
# expected_attempts: derived from m-auto-retry.md / m-concurrency.md's own       #
# retriability rules, never a per-case hand table — exercised over the real   #
# corpus's own 8 combinations plus the branches they don't cover.             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _AttemptsCase:
    fault: str | None
    outcome_kind: str
    max_retries: int
    expected: int


# The oracle takes the bound the outer invocation RESOLVES to, so a case that
# omits it reaches the oracle as the root's built-in 10 rather than as an
# absence the oracle would have to resolve for itself.
_ATTEMPTS_CASES: list[_AttemptsCase] = [
    # m-auto-retry-001: transient, first-attempt-only (don't-care), committed.
    _AttemptsCase("serialization-failure", "committed", 10, 2),
    # m-auto-retry-004 / -007: a zero bound, explicit or the root's, disables the loop.
    _AttemptsCase("serialization-failure", "serialization-failure", 0, 1),
    # m-auto-retry-008: an explicit bound of 1 over a zero root admits the retry.
    _AttemptsCase("serialization-failure", "committed", 1, 2),
    # m-auto-retry-005: persistent, bound exhausted.
    _AttemptsCase("serialization-failure", "serialization-failure", 2, 3),
    # m-concurrency-010 / -024: a conflict under a zero bound surfaces after one attempt.
    _AttemptsCase("optimistic-lock-conflict", "optimistic-lock-conflict", 0, 1),
    # m-concurrency-011 / -025: a conflict is replayed to success.
    _AttemptsCase("optimistic-lock-conflict", "committed", 10, 2),
    _AttemptsCase("optimistic-lock-conflict", "committed", 1, 2),
    # A conflict that persists exhausts the bound like a transient does.
    _AttemptsCase("optimistic-lock-conflict", "optimistic-lock-conflict", 2, 3),
    # m-unit-work-004: no fault, the scripted closure itself aborts.
    _AttemptsCase(None, "aborted", 10, 1),
    _AttemptsCase(None, "committed", 10, 1),
    # lock-wait-timeout is never retriable.
    _AttemptsCase("lock-wait-timeout", "lock-wait-timeout", 10, 1),
    # m-execution-lifecycle-008: a boundary that never opened is ONE attempt —
    # the one that adopted and started before the boundary was asked to begin —
    # and it is terminal however the loop is configured.
    _AttemptsCase("isolation-setup-failure", "boundary-failed", 10, 1),
    # m-execution-lifecycle-009: an acquisition that granted nothing is the same
    # terminal begin failure reached one step earlier, and m-execution-lifecycle-010:
    # an unconfirmed release changes no outcome at all, so the
    # attempt it followed commits and there is nothing to retry.
    _AttemptsCase("connection-acquisition-failure", "boundary-failed", 10, 1),
    _AttemptsCase("connection-cleanup-failure", "committed", 10, 1),
]


@pytest.mark.parametrize("case", _ATTEMPTS_CASES)
def test_expected_attempts(case: _AttemptsCase) -> None:
    assert (
        boundary_runner.expected_attempts(
            fault=case.fault, outcome_kind=case.outcome_kind, max_retries=case.max_retries
        )
        == case.expected
    )


# The root-configured corpus witnesses, each as the values its outer invocation
# resolves to and the attempt count that follows: the same resolution the
# real-database runner grades against, read off the corpus rather than restated
# per case in that runner.
_ROOT_WITNESS_ATTEMPTS: dict[str, tuple[int, str, str, int]] = {
    "m-auto-retry-007": (0, "optimistic", "read_committed", 1),
    "m-auto-retry-008": (1, "optimistic", "read_committed", 2),
    "m-auto-retry-009": (10, "optimistic", "repeatable_read", 2),
    "m-auto-retry-010": (10, "optimistic", "repeatable_read", 2),
    "m-execution-001": (2, "locking", "repeatable_read", 1),
    "m-concurrency-024": (0, "optimistic", "read_committed", 1),
    "m-concurrency-025": (1, "optimistic", "read_committed", 2),
    "m-unit-work-037": (2, "locking", "repeatable_read", 1),
    "m-unit-work-038": (10, "optimistic", "read_committed", 1),
    "m-unit-work-040": (5, "optimistic", "read_committed", 1),
    "m-unit-work-041": (10, "optimistic", "serializable", 1),
}


_TUNED_BACKOFF = AdaptiveBackoff(base_delay=0.002, max_delay=0.05)
_RETRY_POLICY_WITNESSES: dict[str, RetryPolicy] = {
    "m-auto-retry-011": RetryPolicy(max_retries=2, backoff=_TUNED_BACKOFF),
    "m-auto-retry-012": RetryPolicy(max_retries=1),
    "m-auto-retry-013": RetryPolicy(backoff=AdaptiveBackoff(max_delay=0.5)),
    "m-auto-retry-014": RetryPolicy(max_retries=2, backoff=_TUNED_BACKOFF),
    "m-auto-retry-015": RetryPolicy(max_retries=2),
    "m-auto-retry-016": RetryPolicy(max_retries=2, backoff=_TUNED_BACKOFF),
}


@pytest.mark.parametrize("case_id", sorted(_RETRY_POLICY_WITNESSES))
def test_a_retry_policy_witness_resolves_the_whole_policy_it_authors(case_id: str) -> None:
    case = corpus_case(case_id)
    assert case_format.effective_options(case).retry == _RETRY_POLICY_WITNESSES[case_id]


@pytest.mark.parametrize("case_id", sorted(_ROOT_WITNESS_ATTEMPTS))
def test_a_root_configured_witness_resolves_its_effective_options_and_attempts(
    case_id: str,
) -> None:
    case = corpus_case(case_id)
    max_retries, concurrency, isolation, attempts = _ROOT_WITNESS_ATTEMPTS[case_id]
    effective = case_format.effective_options(case)
    assert effective == TxnOptions(
        retry=RetryPolicy(max_retries=max_retries),
        concurrency=concurrency,  # pyright: ignore[reportArgumentType] - a corpus spelling
        isolation=isolation,  # pyright: ignore[reportArgumentType] - a corpus spelling
    )
    # Neither placement was flattened into the other: the root record holds
    # only what `given.databaseOptions` wrote, and the request only what
    # `when.uow` wrote, so production — not the reader — meets them.
    root = case_format.database_options(case)
    requests = case_format.transaction_keywords(case)
    given = cast("dict[str, Any]", case.document.get("given") or {})
    when = cast("dict[str, Any]", case.document.get("when") or {})
    assert (root != TxnOptions()) == bool(given.get("databaseOptions"))
    assert bool(requests) == bool(when.get("uow"))
    outcome = boundary_runner.outcome(case, POSTGRES)
    assert outcome is not None
    assert (
        boundary_runner.expected_attempts(
            fault=boundary_runner.fault_kind(case),
            outcome_kind=outcome,
            max_retries=effective.retry.max_retries,
        )
        == attempts
    )


# --------------------------------------------------------------------------- #
# Per-attempt port observations, driven from the corpus's own root-configured  #
# boundary cases: the outer lifecycle event states one level for the whole     #
# invocation, and only the port sees what each attempt asked for.              #
# --------------------------------------------------------------------------- #
_PER_ATTEMPT_LEVEL_CASES: tuple[str, ...] = (
    "m-auto-retry-006",
    "m-auto-retry-009",
    "m-auto-retry-010",
    "m-unit-work-037",
    "m-unit-work-041",
)


@pytest.mark.parametrize("case_id", _PER_ATTEMPT_LEVEL_CASES)
def test_every_attempt_of_a_root_configured_case_opens_at_the_resolved_level(
    case_id: str,
) -> None:
    # The runner's own two seams, over a scripted port: the root record goes to
    # `connect` and the authored request to the call, exactly as the
    # real-database runner hands them over. What the port then records is the
    # level EVERY attempt was opened at — the retried attempt of a deadlock case
    # included — and it is the level the case resolves for itself, whether that
    # value came from the root, from the call, or from the call over the root.
    case = corpus_case(case_id)
    fault = boundary_runner.fault_kind(case)
    outcome = boundary_runner.outcome(case, POSTGRES)
    assert outcome is not None
    port = _FakePort(rows=[{"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}])
    db = own_root(
        Database.connect(
            _faulted(port, fault=fault, persistent=outcome != "committed"),
            _ACCOUNT,
            options=case_format.database_options(case),
            clock=FixedClock(_FIXED),
        )
    ).using_database_login()
    steps = boundary_runner.boundary_steps(case)
    requests = case_format.transaction_keywords(case)

    def fn(tx: TxnContext) -> Any:
        return boundary_runner.run_boundary_actions(tx, steps, _ACCOUNT_TARGET, database=db)

    if outcome == "committed":
        db.transact(fn, **requests)
    else:
        with raises_code(UsageError, "transaction-option-conflict"):
            db.transact(fn, **requests)
    effective = case_format.effective_options(case)
    attempts = boundary_runner.expected_attempts(
        fault=fault, outcome_kind=outcome, max_retries=effective.retry.max_retries
    )
    assert port.boundaries == attempts
    assert port.levels == [effective.isolation] * attempts


# --------------------------------------------------------------------------- #
# The two RESOURCE seams: an acquisition that grants nothing, and a release    #
# whose transfer cannot be confirmed.                                         #
# --------------------------------------------------------------------------- #
def test_an_acquisition_fault_refuses_before_it_takes_anything() -> None:
    # It never enters the inner context, so no real connection is taken and none
    # can leak. What it reports is the shape a non-idle checkout reaches: a
    # connection taken, found unusable, disposed of deliberately, and refused.
    inner = _FakePort(rows=[])
    faulted = _faulted(inner, fault="connection-acquisition-failure", persistent=False)
    context = _context(faulted.open())

    before = context.cleanup_result
    assert before is None, "a context nobody entered has established nothing"
    with pytest.raises(ConnectionAcquisitionError) as refused:
        context.__enter__()

    assert refused.value.reason == "preparation_failed"
    # It is refused on the writer route the shipped adapter's one endpoint
    # serves, reported on the context and the failure alike.
    assert refused.value.selection == context.selection == RouteSelection("writer")
    established = context.cleanup_result
    assert isinstance(established, Invalidated)
    assert [(issue.phase, issue.code) for issue in established.issues] == [("inspect", "not-idle")]


def test_a_one_shot_acquisition_fault_lets_the_next_acquisition_through() -> None:
    # One `_FaultState` is closed over per configuration, so a one-shot
    # injection stays one-shot across a whole retry loop even though every
    # attempt acquires a connection of its own.
    inner = _FakePort(rows=[])
    runtime = _faulted(inner, fault="connection-acquisition-failure", persistent=False).open()

    with pytest.raises(ConnectionAcquisitionError):
        _context(runtime).__enter__()
    passed = _context(runtime)
    with passed as scoped:
        assert scoped is inner
    # A context the fault let through reports what the inner one selected.
    assert passed.selection == RouteSelection("writer")


def test_a_persistent_acquisition_fault_refuses_every_acquisition() -> None:
    inner = _FakePort(rows=[])
    runtime = _faulted(inner, fault="connection-acquisition-failure", persistent=True).open()

    for _ in range(2):
        with pytest.raises(ConnectionAcquisitionError):
            _context(runtime).__enter__()


def test_a_cleanup_fault_lets_the_connection_go_back_and_reports_that_it_did_not() -> None:
    # The inner context does its whole job first, so the real connection
    # genuinely goes back; only the REPORT is simulated. A suite that actually
    # stranded a connection per case would exhaust the server long before the
    # corpus ran out of cases.
    inner = _FakePort(rows=[])
    runtime = _faulted(inner, fault="connection-cleanup-failure", persistent=False).open()

    context = _context(runtime)
    with context as scoped:
        assert scoped is inner
    established = context.cleanup_result
    assert isinstance(established, ReleaseUnconfirmed)
    assert [(issue.phase, issue.code) for issue in established.issues] == [
        ("return", "handoff-failed")
    ]


def test_a_spent_cleanup_fault_reports_what_the_inner_context_established() -> None:
    inner = _FakePort(rows=[])
    runtime = _faulted(inner, fault="connection-cleanup-failure", persistent=False).open()

    first = _context(runtime)
    with first:
        pass
    second = _context(runtime)
    with second:
        pass

    assert isinstance(first.cleanup_result, ReleaseUnconfirmed)
    # The inner double reclaims nothing and says so as a completed return, which
    # is what a spent one-shot injection then passes straight through.
    assert second.cleanup_result == Returned()


def test_a_resource_faulting_adapter_stands_in_for_the_configuration_it_decorates() -> None:
    inner = _FakePort(rows=[])
    faulted = _faulted(inner, fault="connection-cleanup-failure", persistent=False)
    runtime = faulted.open()

    assert faulted.dialect is inner.dialect
    assert runtime.dialect is inner.dialect
    assert runtime.routes == {"writer": RouteCapabilities.every_level()}
    assert runtime.pool_metrics == ()
    assert runtime.login_identity == "test-login"
    assert isinstance(runtime.login_source().new_context("writer_only"), ResourceFaultingContext)
    assert isinstance(
        runtime.principal_source(object()).new_context("writer_only"), ResourceFaultingContext
    )
    runtime.close()


def test_a_fault_injecting_adapter_stands_in_for_the_configuration_it_decorates() -> None:
    # A decorator reports the dialect of the thing it stands in for and authors
    # none of its own (`m-db-port`), and that rule reaches the lifetime half for
    # the same reason it reaches the execution half: what a caller lowers SQL in
    # must be what executes it. Everything else about the resource is the inner
    # runtime's, measurements included.
    inner = _FakePort(rows=[])
    faulted = _faulted(inner, fault=None, persistent=False)
    runtime = faulted.open()

    assert faulted.dialect is inner.dialect
    assert runtime.dialect is inner.dialect
    assert runtime.pool_metrics == ()
    assert runtime.login_identity == "test-login"
    with runtime.login_source().new_context("writer_only") as scoped:
        assert isinstance(scoped, FaultInjectingPort)
    with runtime.principal_source(object()).new_context("writer_only") as scoped:
        assert isinstance(scoped, FaultInjectingPort)
    runtime.close()
