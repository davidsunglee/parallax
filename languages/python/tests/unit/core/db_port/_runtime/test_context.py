"""One acquisition's lease: checkout, setup, first-use replacement, and release.

The failures that matter most are the ones a real server will not produce on
demand — a checkout that hands over a connection in a transaction, a physical
close that raises, a hand-back that raises after it may already have handed
the connection to somebody else — so the pool and the driver are scripted at
their seams with those failures, and the live proofs are in the provider lane.

The pins are deliberately pessimistic about cleanup. A cleanup result says what
was ESTABLISHED, so the interesting assertions are the ones that refuse to claim
more than that: a failed disposal does not fall back to returning a suspect
connection, a failed handoff is not retried, and a completed handoff is never
inspected afterwards.
"""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import Any, cast

import pytest

from parallax.core.internal.db_port import (
    ConnectionAcquisitionError,
    CredentialResolutionError,
    IdleReading,
    Invalidated,
    NotIdle,
    ProbeMismatch,
    ReleaseUnconfirmed,
    Returned,
    RouteSelection,
    SubmissionProgress,
)
from parallax.core.internal.db_port._runtime._context import (
    PooledConnectionContext,
    check_out_within,
    release,
)
from parallax.core.internal.db_port._runtime._dial_record import DialLedger
from parallax.core.internal.db_port._runtime._pooled_route import PooledRoute
from tests.unit.core.db_port._runtime._composition import (
    Pool,
    issues_of,
    login_context,
    lost_session,
    pool_of,
    pooled_runtime,
    preferred_context,
    reader_context,
    reader_route_of,
    routed,
    whatever_budget,
)
from tests.unit.core.db_port._runtime._scripted_native import (
    RESTORE,
    Clock,
    ScriptedConnection,
    ScriptedDriver,
    SessionLost,
    checkout_failed,
)


def _context(
    pool: Pool,
    *,
    deadline: float | None = None,
    admit: Any = None,
    authorization: object = None,
    ledger: DialLedger | None = None,
) -> Any:
    runtime = pooled_runtime(pool)
    return PooledConnectionContext(
        (
            (
                PooledRoute("writer", pool, DialLedger() if ledger is None else ledger),
                monotonic() + 5.0 if deadline is None else deadline,
            ),
        ),
        runtime._admit if admit is None else admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        ScriptedDriver(),
        authorization,
        expected_login=None,
    )


def _admitted(_deadline: float) -> None:
    return


def _unsent(_connection: ScriptedConnection, _submission: SubmissionProgress) -> None:
    return None


def _lost_while_draining(interrupt: BaseException) -> SessionLost:
    # A driver may answer an interrupt during a wait by finishing its exchange
    # with the server; a session that breaks then raises its driver failure in
    # the interrupt's place, carrying the interrupt as context.
    lost = lost_session()
    lost.__context__ = interrupt
    return lost


def _set_up_on(setup: str, pool: Pool) -> Any:
    """Run the setup named ``setup`` as the first submission of a lease over ``pool``."""
    if setup == "proof":
        resource = reader_context(routed(pool_of(), pool, reader_readiness="pending"))
        resource.__enter__()
    elif setup == "role":
        _context(pool, authorization="tenant_reader").__enter__()
    elif setup == "statement-bound":
        pooled_runtime(pool_of(), reservation=pool).reservation_source().new_context(
            monotonic() + 5.0
        ).__enter__()
    else:
        with _context(pool) as scoped:
            scoped.submit("BEGIN", replay_safe=True, setup=True)


def _readings(monkeypatch: pytest.MonkeyPatch, *readings: IdleReading) -> list[IdleReading]:
    """Have every scripted connection read as ``readings`` in turn, answering
    the list of those not yet read."""
    remaining = list(readings)

    def read_idle(_driver: object, _connection: object) -> IdleReading:
        return remaining.pop(0)

    monkeypatch.setattr(ScriptedDriver, "read_idle", read_idle)
    return remaining


def _release(connection: ScriptedConnection, pool: Pool | None = None, **kwargs: Any) -> Any:
    return release(
        ScriptedDriver(), pool_of(connection) if pool is None else pool, connection, **kwargs
    )


def _refusing(failure: BaseException, *, after: Callable[[], None] = lambda: None) -> Pool:
    """A pool whose every checkout runs ``after`` and then raises ``failure``."""
    pool = pool_of(checkout_failure=failure)
    pool.on_check_out = whatever_budget(lambda: after())
    return pool


# --------------------------------------------------------------------------- #
# Acquisition: what a checkout is allowed to become.                          #
# --------------------------------------------------------------------------- #


def test_an_expired_budget_refuses_before_asking_the_pool_for_anything() -> None:
    pool = pool_of()
    resource = _context(pool, deadline=monotonic() - 1.0)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert pool.budgets == []


@pytest.mark.parametrize(
    "reason",
    [
        "queue_rejected",
        "closed",
        "unavailable",
        "authentication_refused",
        "credentials_refused",
        "preparation_failed",
    ],
)
def test_every_checkout_failure_maps_to_its_own_reason_and_keeps_its_native_cause(
    reason: Any,
) -> None:
    # A dial reason here is one the checkout's own dial met, so it is reported
    # as it stands without the record being consulted at all.
    native = RuntimeError("what the pool met")
    resource = _context(pool_of(checkout_failure=checkout_failed(reason, native)))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == reason
    assert refused.value.__cause__ is native
    # Nothing was taken, so there is nothing to have cleaned up.
    assert resource.cleanup_result is None


def test_a_timeout_with_nothing_on_record_is_a_bare_timeout_caused_by_the_wait() -> None:
    native = RuntimeError("couldn't get a connection")
    ledger = DialLedger()
    resource = _context(pool_of(checkout_failure=checkout_failed("timeout", native)), ledger=ledger)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert refused.value.__cause__ is native
    assert ledger.latest_failure is None


def test_a_timeout_names_the_initialization_refusal_on_record() -> None:
    # The pool retries an initialization refusal in the background, so the
    # waiting caller would otherwise get a bare timeout naming nothing to fix.
    ledger = DialLedger()
    refusal = RuntimeError("this connection's DateStyle is 'German'")
    ledger.report_failure("preparation_failed", refusal)
    resource = _context(pool_of(checkout_failure=checkout_failed("timeout")), ledger=ledger)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is refusal


def test_a_timeout_names_the_credential_refusal_on_record() -> None:
    # A retained pool resolves the credential on its own worker threads, so a
    # source that produces none reaches a waiting caller only by being on
    # record — and it is a reason of its own rather than a preparation that
    # failed, because nothing was ever offered to the server.
    ledger = DialLedger()
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    ledger.report_failure("credentials_refused", refusal)
    resource = _context(pool_of(checkout_failure=checkout_failed("timeout")), ledger=ledger)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "credentials_refused"
    assert refused.value.__cause__ is refusal
    assert "authenticated" in str(refused.value)


def test_the_remaining_budget_is_what_the_pool_s_one_wait_is_given() -> None:
    pool = pool_of()
    _context(pool, deadline=monotonic() + 2.0).__enter__()
    (given,) = pool.budgets
    assert 0.0 < given <= 2.0


@pytest.mark.parametrize(
    ("reading", "state"), [(NotIdle("INTRANS"), "INTRANS"), ("unreadable", "unreadable")]
)
def test_a_checkout_that_hands_over_a_connection_that_is_not_idle_is_refused(
    monkeypatch: pytest.MonkeyPatch, reading: Any, state: str
) -> None:
    # No modeled SQL runs on it and no unknown transaction is rolled back to
    # make it usable: an adapter invariant this broken is reported. The reading
    # that refused it is the one its cleanup decides on, so a state that reads
    # differently afterwards cannot turn the disposal into a return.
    connection = ScriptedConnection()
    readings = _readings(monkeypatch, reading, "idle")
    pool = pool_of(connection)
    resource = _context(pool)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert f"whose state is {state} rather than idle" in str(refused.value)
    assert connection.submitted == []
    # The partial ownership is cleaned up, and a connection in this state is
    # disposed of rather than offered to the next caller.
    assert isinstance(resource.cleanup_result, Invalidated)
    assert issues_of(resource.cleanup_result) == [
        ("inspect", "state-unreadable" if reading == "unreadable" else "not-idle")
    ]
    assert connection.closes == 1
    assert readings == ["idle"]


def test_a_late_native_success_is_released_rather_than_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The caller has already been waiting past what it asked for; its own
    # timeout handling is a better answer than work starting after the budget.
    # The budget is live when the checkout starts and spent when it returns,
    # which is the race a cooperative deadline can only lose.
    from parallax.core.internal.db_port._runtime import _pooled_runtime as runtime_module

    connection = ScriptedConnection()
    pool = pool_of(connection)
    monkeypatch.setattr(runtime_module, "monotonic", lambda: 1e18)
    ledger = DialLedger()
    ledger.report_failure("unavailable", lost_session("connection refused"))
    resource = _context(pool, ledger=ledger)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert connection.submitted == []
    assert resource.cleanup_result == Returned()
    assert pool.check_ins == [connection]
    # The handover still cleared the record: the route did hand over a connection.
    assert ledger.latest_failure is None


@pytest.mark.parametrize(
    "failure", [RuntimeError("the execution could not be built"), KeyboardInterrupt()]
)
def test_execution_access_that_cannot_be_opened_is_a_failed_entry_that_gave_back_its_connection(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    # The caller never holds execution access, so it has nothing to leave:
    # entry's own cleanup is the only path back to the pool.
    def refuse(_driver: object, _lease: object) -> object:
        raise failure

    monkeypatch.setattr(ScriptedDriver, "open_execution", refuse)
    connection = ScriptedConnection()
    pool = pool_of(connection)
    resource = _context(pool, authorization="tenant_reader")

    with pytest.raises(type(failure)) as raised:
        resource.__enter__()

    assert raised.value is failure
    assert connection.submitted == ["authorize tenant_reader", RESTORE]
    assert resource.cleanup_result == Returned()
    assert pool.check_ins == [connection]
    with pytest.raises(RuntimeError, match="already been used"):
        resource.__enter__()


def test_a_context_is_entered_exactly_once_and_a_failed_entry_spends_it() -> None:
    pool = pool_of()
    resource = _context(pool)
    with resource, pytest.raises(RuntimeError):
        resource.__enter__()
    with pytest.raises(RuntimeError):
        resource.__enter__()

    failed = _context(pool_of(checkout_failure=checkout_failed("closed")))
    with pytest.raises(ConnectionAcquisitionError):
        failed.__enter__()
    with pytest.raises(RuntimeError):
        failed.__enter__()


def test_entering_opens_fresh_execution_over_the_context_and_leaving_revokes_it() -> None:
    # The driver's execution borrows the context as its lease, and a reference
    # kept past the exit reaches nothing.
    connection = ScriptedConnection()
    driver = ScriptedDriver()
    runtime = pooled_runtime(pool_of(connection), driver=driver)
    resource = login_context(runtime)

    with resource as scoped:
        assert scoped.lease is resource
        scoped.submit("select 1")
    with pytest.raises(RuntimeError, match="scope has ended"):
        scoped.submit("select 1")

    assert driver.executions == [scoped]
    assert connection.submitted == ["select 1"]


def test_an_execution_that_left_its_connection_suspect_has_it_disposed_of() -> None:
    # A boundary execution could not bring back to a known state is disposed
    # of rather than reset or offered for reuse; the next acquisition runs on
    # another physical connection.
    suspect, fresh = ScriptedConnection(), ScriptedConnection()
    pool = pool_of(suspect, fresh)

    first = _context(pool)
    with first as scoped:
        scoped.lease.mark_suspect()
        assert scoped.lease.suspect
    second = _context(pool)
    with second as scoped:
        scoped.submit("select 1")

    assert issues_of(first.cleanup_result) == [("inspect", "suspect")]
    assert suspect.closes == 1
    assert fresh.submitted == ["select 1"]
    assert second.cleanup_result == Returned()
    assert pool.returned == [suspect, fresh]


def test_an_installed_authorization_is_restored_before_its_connection_is_reused() -> None:
    connection = ScriptedConnection()
    pool = pool_of(connection)
    resource = _context(pool, authorization="tenant_reader")

    with resource as scoped:
        scoped.submit("select current_user")

    assert connection.submitted == ["authorize tenant_reader", "select current_user", RESTORE]
    assert resource.cleanup_result == Returned()


def test_role_installation_preserves_a_control_flow_exception() -> None:
    connection = ScriptedConnection(failure=KeyboardInterrupt())
    resource = _context(pool_of(connection), authorization="tenant_reader")

    with pytest.raises(KeyboardInterrupt):
        resource.__enter__()

    assert isinstance(resource.cleanup_result, Invalidated)
    assert connection.closes == 1
    assert RESTORE not in connection.submitted


def test_admission_is_checked_again_after_successful_role_installation() -> None:
    connection = ScriptedConnection()
    calls = 0

    def admit(_deadline: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionAcquisitionError("closed during authorization", reason="closed")

    pool = pool_of(connection)
    resource = _context(pool, admit=admit, authorization="tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "closed"
    assert calls == 2
    assert connection.submitted[-1] == RESTORE
    assert resource.cleanup_result == Returned()
    assert pool.returned == [connection]


def test_role_restoration_failure_forces_disposal_and_is_reported() -> None:
    connection = ScriptedConnection(restore_failure=RuntimeError("reset denied"))
    pool = pool_of(connection)
    resource = _context(pool, authorization="tenant_reader")

    with resource:
        pass

    result = resource.cleanup_result
    assert isinstance(result, Invalidated)
    assert [(issue.phase, issue.code) for issue in result.issues] == [
        ("restore", "authorization-restore-failed")
    ]
    assert connection.closes == 1
    assert pool.returned == [connection]


# --------------------------------------------------------------------------- #
# First use: one replacement of a broken connection, inside the one lease.    #
# --------------------------------------------------------------------------- #


def test_a_broken_first_designated_read_is_submitted_once_more_on_a_replacement() -> None:
    # The same prepared inputs reach the replacement: the one object both
    # sessions were handed. The original is disposed of and handed back before
    # the replacement is asked for, and no cleanup is published while in use.
    binds = [[1, 2]]
    broken = ScriptedConnection(lost=lost_session())
    fresh = ScriptedConnection(rows=[(1,)])
    pool = pool_of(broken, fresh)
    resource = _context(pool)

    with resource as scoped:
        rows = scoped.submit("select id from t where id = any(?)", binds, replay_safe=True)
        assert resource.cleanup_result is None
        assert pool.returned == [broken]

    assert rows == [(1,)]
    assert broken.submitted == fresh.submitted == ["select id from t where id = any(?)"]
    assert broken.prepared[0][0] is binds
    assert fresh.prepared[0][0] is binds
    assert len(pool.budgets) == 2
    assert (broken.closes, fresh.closes) == (1, 0)
    assert pool.returned == [broken, fresh]
    assert resource.cleanup_result == Returned()


@pytest.mark.parametrize(
    "refusal",
    [SessionLost("terminating connection"), RuntimeError("deadlock detected")],
    ids=["loss-on-a-healthy-session", "statement-refusal"],
)
def test_a_refusal_on_a_healthy_connection_is_never_a_reason_to_replace_it(
    refusal: Exception,
) -> None:
    # Only a session the driver reports broken grants replacement, whatever
    # the failure says about itself, and the failure propagates as itself.
    connection = ScriptedConnection(failure=refusal)
    pool = pool_of(connection, ScriptedConnection())

    with _context(pool) as scoped, pytest.raises(type(refusal)) as failed:
        scoped.submit("select 1", replay_safe=True)

    assert failed.value is refusal
    assert len(pool.budgets) == 1


def test_a_failure_on_a_broken_session_the_driver_does_not_classify_is_not_replaced() -> None:
    connection = ScriptedConnection(failure=RuntimeError("not a driver failure"))
    connection.broken = True
    pool = pool_of(connection, ScriptedConnection())

    with _context(pool) as scoped, pytest.raises(RuntimeError):
        scoped.submit("select 1", replay_safe=True)

    assert len(pool.budgets) == 1


@pytest.mark.parametrize(
    ("replay_safe", "setup"),
    [(True, False), (False, False), (True, True)],
    ids=["read", "write", "begin"],
)
def test_a_connection_lost_after_the_first_submission_is_not_replaced(
    replay_safe: bool, setup: bool
) -> None:
    # Whatever the first submission was, once it answered the opportunity is
    # gone: a later read designated as one cannot earn it back.
    connection = ScriptedConnection()
    pool = pool_of(connection, ScriptedConnection())

    with _context(pool) as scoped:
        scoped.submit("first", replay_safe=replay_safe, setup=setup)
        connection.lost = lost_session()
        with pytest.raises(SessionLost):
            scoped.submit("select 2", replay_safe=True)

    assert len(pool.budgets) == 1


def test_a_write_that_meets_a_broken_session_first_is_never_replaced() -> None:
    broken = ScriptedConnection(lost=lost_session())
    pool = pool_of(broken, ScriptedConnection())

    with _context(pool) as scoped, pytest.raises(SessionLost):
        scoped.submit("update t set v = 1")

    assert len(pool.budgets) == 1
    assert broken.submitted == ["update t set v = 1"]


def test_a_child_read_after_its_root_has_no_opportunity_to_claim() -> None:
    # A single child fetch is a designated read through the same seam as its
    # root, carrying the keys the root just gathered; the root already spent
    # the lease's one opportunity, and designation does not reopen it.
    connection = ScriptedConnection(rows=[(3,), (4,)])
    pool = pool_of(connection, ScriptedConnection())

    with _context(pool) as scoped:
        keys = [row[0] for row in scoped.submit("select id from root", replay_safe=True)]
        connection.lost = lost_session()
        with pytest.raises(SessionLost):
            scoped.submit("select * from child", keys, replay_safe=True)

    assert connection.prepared[-1] == ([3, 4],)
    assert len(pool.budgets) == 1
    assert pool.returned == [connection]


def test_a_fatal_first_submission_spends_the_opportunity_and_propagates_as_itself() -> None:
    connection = ScriptedConnection(failure=KeyboardInterrupt())
    pool = pool_of(connection, ScriptedConnection())

    with _context(pool) as scoped:
        with pytest.raises(KeyboardInterrupt):
            scoped.submit("select 1", replay_safe=True)
        connection.failure = None
        connection.lost = lost_session()
        with pytest.raises(SessionLost):
            scoped.submit("select 2", replay_safe=True)

    assert len(pool.budgets) == 1


def test_a_failure_after_the_answer_has_spent_the_opportunity() -> None:
    # Fetching and decoding come after the submission answered, so their
    # failure is never one a replacement could repair, even on a session the
    # driver then reports broken.
    connection = ScriptedConnection(after_answer=lost_session("lost while fetching"))
    connection.broken = True
    pool = pool_of(connection, ScriptedConnection())

    with _context(pool) as scoped, pytest.raises(SessionLost):
        scoped.submit("select 1", replay_safe=True)

    assert len(pool.budgets) == 1


def test_an_operation_that_submits_nothing_leaves_the_opportunity_open() -> None:
    def refuses_before_sending(
        _connection: ScriptedConnection, _submission: SubmissionProgress
    ) -> None:
        raise ValueError("refused before anything was sent")

    broken = ScriptedConnection()
    fresh = ScriptedConnection(rows=[(1,)])
    pool = pool_of(broken, fresh)

    with _context(pool) as scoped:
        scoped.lease.run(_unsent, replay_safe=False)
        with pytest.raises(ValueError, match="before anything was sent"):
            scoped.lease.run(refuses_before_sending, replay_safe=True)
        broken.lost = lost_session()
        assert scoped.submit("select 1", replay_safe=True) == [(1,)]

    assert len(pool.budgets) == 2
    assert broken.submitted == fresh.submitted == ["select 1"]


@pytest.mark.parametrize("setup", [False, True], ids=["read", "begin"])
@pytest.mark.parametrize("interrupted", [KeyboardInterrupt, SystemExit])
def test_an_interrupt_a_broken_first_submission_displaced_propagates_and_is_not_replaced(
    setup: bool, interrupted: type[BaseException]
) -> None:
    interrupt = interrupted()
    broken = ScriptedConnection(lost=_lost_while_draining(interrupt))
    pool = pool_of(broken, ScriptedConnection())
    resource = _context(pool)

    with resource as scoped:
        with pytest.raises(interrupted) as raised:
            scoped.submit("first", replay_safe=True, setup=setup)
        assert raised.value is interrupt
        broken.lost = _lost_while_draining(KeyboardInterrupt())
        with pytest.raises(SessionLost):
            scoped.submit("select 2", replay_safe=True)

    assert len(pool.budgets) == 1
    assert pool.returned == [broken]


def test_an_interrupt_a_broken_role_installation_displaced_propagates_and_is_not_replaced() -> None:
    interrupt = KeyboardInterrupt()
    broken = ScriptedConnection(lost=_lost_while_draining(interrupt))
    pool = pool_of(broken, ScriptedConnection())
    resource = _context(pool, authorization="tenant_reader")

    with pytest.raises(KeyboardInterrupt) as raised:
        resource.__enter__()

    assert raised.value is interrupt
    assert len(pool.budgets) == 1
    assert pool.returned == [broken]


def test_an_interrupt_already_being_handled_is_not_one_the_failure_displaced() -> None:
    # Work run while an earlier interrupt is handled inherits it as context
    # without the submission having been interrupted, so replacement proceeds.
    broken = ScriptedConnection(lost=lost_session())
    fresh = ScriptedConnection(rows=[(1,)])
    pool = pool_of(broken, fresh)

    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        with _context(pool) as scoped:
            rows = scoped.submit("select 1", replay_safe=True)

    assert rows == [(1,)]
    assert len(pool.budgets) == 2
    assert pool.returned == [broken, fresh]


def test_a_replacement_that_also_breaks_reports_its_own_failure_and_is_not_replaced() -> None:
    first, second = (
        lost_session("the first session is gone"),
        lost_session("the second session is gone"),
    )
    broken = ScriptedConnection(lost=first)
    also_broken = ScriptedConnection(lost=second)
    pool = pool_of(broken, also_broken, ScriptedConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(SessionLost) as failed:
        scoped.submit("select 1", replay_safe=True)

    assert failed.value is second
    assert second.__context__ is None
    assert len(pool.budgets) == 2
    assert pool.returned == [broken, also_broken]
    assert issues_of(resource.cleanup_result) == [("inspect", "not-idle")]


def test_an_unavailable_replacement_preserves_the_original_failure_and_its_cleanup() -> None:
    # The original was disposed of and handed back, and that is what the
    # context reports once it exits — published then, and only then.
    original = lost_session()
    broken = ScriptedConnection(lost=original)
    pool = pool_of(broken, ScriptedConnection())
    broken.when_lost = lambda: setattr(pool, "checkout_failure", checkout_failed("timeout"))
    resource = _context(pool)

    with resource as scoped:
        with pytest.raises(SessionLost) as failed:
            scoped.submit("BEGIN", replay_safe=True, setup=True)
        assert resource.cleanup_result is None
        with pytest.raises(RuntimeError, match="could not be replaced"):
            scoped.submit("select 1")

    assert failed.value is original
    assert len(pool.budgets) == 2
    assert (broken.closes, pool.returned) == (1, [broken])
    assert issues_of(resource.cleanup_result) == [("inspect", "suspect")]


def test_a_replacement_that_is_not_idle_is_given_back_and_its_cleanup_is_what_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = lost_session()
    broken = ScriptedConnection(lost=original)
    busy = ScriptedConnection()
    # The original's checkout reads it idle; the replacement's one reading
    # refuses it and decides its disposal, however it would read afterwards.
    readings = _readings(monkeypatch, "idle", NotIdle("INTRANS"), "idle")
    pool = pool_of(broken, busy)
    resource = _context(pool)

    with resource as scoped, pytest.raises(SessionLost) as failed:
        scoped.submit("select 1", replay_safe=True)

    assert failed.value is original
    assert busy.submitted == []
    assert pool.returned == [broken, busy]
    assert issues_of(resource.cleanup_result) == [("inspect", "not-idle")]
    assert busy.closes == 1
    assert readings == ["idle"]


def test_a_disposal_that_failed_ends_replacement_and_is_reported_without_repeating_it() -> None:
    broken = ScriptedConnection(lost=lost_session(), close_failure=RuntimeError("close failed"))
    pool = pool_of(broken, ScriptedConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(SessionLost):
        scoped.submit("select 1", replay_safe=True)

    result = resource.cleanup_result
    assert isinstance(result, ReleaseUnconfirmed)
    assert issues_of(result) == [("inspect", "suspect"), ("dispose", "close-failed")]
    assert (len(pool.budgets), pool.hand_backs, broken.closes) == (1, 0, 1)
    resource.__exit__(None, None, None)
    assert resource.cleanup_result is result
    assert broken.closes == 1


def test_a_handoff_that_failed_is_neither_retried_nor_followed_by_a_close_or_a_checkout() -> None:
    broken = ScriptedConnection(lost=lost_session())
    pool = pool_of(
        broken, ScriptedConnection(), hand_back_failure=RuntimeError("the return failed")
    )
    resource = _context(pool)

    with resource as scoped, pytest.raises(SessionLost):
        scoped.submit("select 1", replay_safe=True)

    assert issues_of(resource.cleanup_result) == [
        ("inspect", "suspect"),
        ("return", "handoff-failed"),
    ]
    assert (len(pool.budgets), pool.hand_backs, broken.closes) == (1, 1, 1)


def test_a_control_flow_exception_while_replacing_keeps_its_precedence() -> None:
    # Interrupted while taking the replacement: the interrupt propagates, and
    # the disposal already established is what the exit reports.
    broken = ScriptedConnection(lost=lost_session())
    pool = pool_of(broken, ScriptedConnection())
    broken.when_lost = lambda: setattr(pool, "checkout_failure", KeyboardInterrupt())
    resource = _context(pool)

    with resource as scoped, pytest.raises(KeyboardInterrupt):
        scoped.submit("select 1", replay_safe=True)

    assert issues_of(resource.cleanup_result) == [("inspect", "suspect")]
    assert pool.returned == [broken]


def test_a_disposal_interrupted_part_way_is_never_attempted_again() -> None:
    # A release that does not return established nothing to report, and the
    # slot it emptied leaves the exit nothing to release a second time.
    broken = ScriptedConnection(lost=lost_session(), close_failure=KeyboardInterrupt())
    pool = pool_of(broken, ScriptedConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(KeyboardInterrupt):
        scoped.submit("select 1", replay_safe=True)

    assert resource.cleanup_result is None
    assert (broken.closes, pool.hand_backs, len(pool.budgets)) == (1, 0, 1)


def test_a_replacement_spends_only_what_remains_of_the_original_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    broken = ScriptedConnection(lost=lost_session())
    pool = pool_of(broken, ScriptedConnection())
    resource = _context(pool, deadline=10.0, admit=_admitted)

    with resource as scoped:
        clock.now = 4.0
        scoped.submit("select 1", replay_safe=True)

    assert pool.budgets == [10.0, 6.0]


def test_no_replacement_is_asked_for_once_the_deadline_has_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The budget gates the next checkout; it never interrupts admitted work,
    # which may still run after it has expired.
    clock = Clock(monkeypatch)
    original = lost_session()
    broken = ScriptedConnection(lost=original)
    pool = pool_of(broken, ScriptedConnection())
    resource = _context(pool, deadline=10.0, admit=_admitted)

    with resource as scoped, pytest.raises(SessionLost) as failed:
        clock.now = 11.0
        scoped.submit("select 1", replay_safe=True)

    assert failed.value is original
    assert pool.budgets == [10.0]

    healthy = ScriptedConnection(rows=[(1,)])
    late = _context(pool_of(healthy), deadline=12.0, admit=_admitted)
    with late as scoped:
        clock.now = 99.0
        assert scoped.submit("select 1", replay_safe=True) == [(1,)]


@pytest.mark.parametrize("work", ["proof", "authorization", "statement-bound", "designated-read"])
def test_a_replacement_handed_over_past_the_deadline_is_given_back_unused_and_refused(
    monkeypatch: pytest.MonkeyPatch, work: str
) -> None:
    # Native checkout can overrun the budget it was given; what it hands over
    # then is refused by admission rather than resubmitted on.
    clock = Clock(monkeypatch)
    broken, late = ScriptedConnection(lost=lost_session()), ScriptedConnection()
    pool = pool_of(broken, late)

    def overrun(_budget: float) -> None:
        if len(pool.budgets) == 2:
            clock.now = 11.0

    pool.on_check_out = overrun
    resource: Any
    if work == "proof":
        runtime = routed(pool_of(), pool, reader_readiness="pending", acquire_timeout=10.0)
        resource = reader_context(runtime)
    elif work == "statement-bound":
        resource = (
            pooled_runtime(pool_of(), reservation=pool).reservation_source().new_context(10.0)
        )
    else:
        authorization = "tenant" if work == "authorization" else None
        resource = _context(pool, deadline=10.0, authorization=authorization)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        if work == "designated-read":
            with resource as scoped:
                scoped.submit("select 1", replay_safe=True)
        else:
            resource.__enter__()

    assert refused.value.reason == "timeout"
    assert refused.value.selection == RouteSelection("reader" if work == "proof" else "writer")
    assert late.submitted == []
    assert pool.check_ins == [late]
    assert resource.cleanup_result == Returned()


def test_a_runtime_closed_while_a_replacement_is_taken_lets_the_admitted_read_finish() -> None:
    # The replacement is not another acquisition: a close refuses new ones and
    # leaves admitted work to finish.
    pool = pool_of(ScriptedConnection(lost=lost_session()), ScriptedConnection(rows=[(1,)]))
    runtime = pooled_runtime(pool)

    def close_meanwhile(_budget: float) -> None:
        if len(pool.budgets) == 2:
            runtime.close()

    pool.on_check_out = close_meanwhile

    with login_context(runtime) as scoped:
        assert scoped.submit("select 1", replay_safe=True) == [(1,)]
    with pytest.raises(ConnectionAcquisitionError) as refused:
        login_context(runtime).__enter__()

    assert refused.value.reason == "closed"


def test_each_new_owner_has_a_budget_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock(monkeypatch)
    broken = ScriptedConnection(lost=lost_session())
    pool = pool_of(ScriptedConnection(), broken, ScriptedConnection())
    runtime = pooled_runtime(pool, acquire_timeout=3.0)

    with login_context(runtime):
        clock.now = 50.0
    with login_context(runtime) as scoped:
        clock.now = 51.0
        scoped.submit("select 1", replay_safe=True)

    assert pool.budgets == [3.0, 3.0, 2.0]


def test_a_broken_role_installation_is_replaced_and_still_rechecks_admission() -> None:
    broken = ScriptedConnection(lost=lost_session())
    fresh = ScriptedConnection()
    pool = pool_of(broken, fresh)
    admissions: list[float] = []
    resource = _context(pool, admit=admissions.append, authorization="tenant_reader")

    with resource as scoped:
        scoped.submit("select current_user")

    assert broken.submitted == ["authorize tenant_reader"]
    assert fresh.submitted == ["authorize tenant_reader", "select current_user", RESTORE]
    # At the first checkout and after the role; the replacement is not another
    # acquisition.
    assert len(admissions) == 2
    assert pool.returned == [broken, fresh]
    assert resource.cleanup_result == Returned()


def test_final_admission_after_a_replaced_role_installation_can_still_refuse() -> None:
    broken = ScriptedConnection(lost=lost_session())
    fresh = ScriptedConnection()
    calls = 0

    def admit(_deadline: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionAcquisitionError("closed during authorization", reason="closed")

    pool = pool_of(broken, fresh)
    resource = _context(pool, admit=admit, authorization="tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "closed"
    assert fresh.submitted[-1] == RESTORE
    assert pool.returned == [broken, fresh]
    assert resource.cleanup_result == Returned()


def test_a_role_installation_that_cannot_be_replaced_is_an_authorization_failure() -> None:
    original = lost_session()
    broken = ScriptedConnection(lost=original)
    pool = pool_of(broken, ScriptedConnection())
    broken.when_lost = lambda: setattr(pool, "checkout_failure", checkout_failed("timeout"))
    resource = _context(pool, authorization="tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.__cause__ is original
    assert pool.returned == [broken]
    assert issues_of(resource.cleanup_result) == [("inspect", "suspect")]


def test_a_replaced_role_installation_that_is_refused_reports_its_own_refusal() -> None:
    refusal = RuntimeError("permission denied to set role")
    broken = ScriptedConnection(lost=lost_session())
    refusing = ScriptedConnection(failure=refusal)
    pool = pool_of(broken, refusing)
    resource = _context(pool, authorization="tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.__cause__ is refusal
    assert pool.returned == [broken, refusing]
    assert issues_of(resource.cleanup_result) == [("inspect", "suspect")]
    assert RESTORE not in refusing.submitted


@pytest.mark.parametrize("setup", ["proof", "role", "statement-bound", "outer-begin"])
@pytest.mark.parametrize(
    "refusal",
    ["credentials_refused", "authentication_refused", "preparation_failed", "not-idle"],
)
def test_setup_whose_replacement_was_refused_reports_that_refusal_rather_than_the_loss(
    setup: str, refusal: Any
) -> None:
    cause = RuntimeError("the replacement was refused")
    broken = ScriptedConnection(lost=lost_session())
    if refusal == "not-idle":
        pool = pool_of(broken, ScriptedConnection(idle=NotIdle("INTRANS")))
    else:
        pool = pool_of(broken, ScriptedConnection())
        broken.when_lost = lambda: setattr(
            pool, "checkout_failure", checkout_failed(refusal, cause)
        )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _set_up_on(setup, pool)

    if refusal == "not-idle":
        assert refused.value.reason == "preparation_failed"
        assert "INTRANS" in str(refused.value)
    else:
        assert refused.value.reason == refusal
        assert refused.value.__cause__ is cause
    route = "reader" if setup == "proof" else "writer"
    assert refused.value.selection == RouteSelection(route)


def test_a_role_refused_on_a_healthy_connection_is_not_replaced() -> None:
    connection = ScriptedConnection(failure=RuntimeError("permission denied to set role"))
    pool = pool_of(connection, ScriptedConnection())

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _context(pool, authorization="tenant_reader").__enter__()

    assert refused.value.reason == "authorization_failed"
    assert len(pool.budgets) == 1


def test_an_installed_role_spends_the_opportunity_before_execution() -> None:
    connection = ScriptedConnection()
    pool = pool_of(connection, ScriptedConnection())

    with _context(pool, authorization="tenant_reader") as scoped:
        connection.lost = lost_session()
        with pytest.raises(SessionLost):
            scoped.submit("BEGIN", replay_safe=True, setup=True)

    assert len(pool.budgets) == 1


@pytest.mark.parametrize(
    "ending",
    [None, RuntimeError("the write failed"), KeyboardInterrupt()],
    ids=["completed", "failed", "interrupted"],
)
def test_a_write_spends_the_opportunity_however_it_ends(ending: BaseException | None) -> None:
    # None is ever resubmitted, and each leaves nothing for a later read to claim.
    connection = ScriptedConnection(failure=ending)
    pool = pool_of(connection, ScriptedConnection())

    with _context(pool) as scoped:
        if ending is None:
            scoped.submit("update a set v = 1")
        else:
            with pytest.raises(type(ending)):
                scoped.submit("update a set v = 1")
        connection.failure = None
        connection.lost = lost_session()
        with pytest.raises(SessionLost):
            scoped.submit("select 1", replay_safe=True)

    assert len(pool.budgets) == 1


# --------------------------------------------------------------------------- #
# Release: what a cleanup result is allowed to claim.                         #
# --------------------------------------------------------------------------- #


def test_an_idle_untrusted_free_connection_is_offered_for_reuse() -> None:
    connection = ScriptedConnection()
    pool = pool_of(connection)

    result = _release(connection, pool, suspect=False)

    assert result == Returned()
    assert connection.closes == 0
    assert (pool.check_ins, pool.discards) == ([connection], [])


def test_an_execution_that_declared_the_connection_suspect_disposes_of_it_first() -> None:
    # Disposal BEFORE the handoff, and the handoff still happens: disposal alone
    # would leak the capacity, and a handoff alone would offer a connection
    # nothing may reuse.
    connection = ScriptedConnection()
    pool = pool_of(connection)
    closed_when_discarded: list[bool] = []
    discard = pool.discard

    def discard_closed(handed: ScriptedConnection) -> None:
        closed_when_discarded.append(handed.closed)
        discard(handed)

    pool.discard = discard_closed

    result = _release(connection, pool, suspect=True)

    assert isinstance(result, Invalidated)
    assert [(issue.phase, issue.code) for issue in result.issues] == [("inspect", "suspect")]
    assert connection.closes == 1
    assert (pool.check_ins, pool.discards) == ([], [connection])
    assert closed_when_discarded == [True]


def test_a_connection_whose_state_cannot_be_read_is_disposed_of() -> None:
    connection = ScriptedConnection(idle="unreadable")

    result = _release(connection, suspect=False)

    assert isinstance(result, Invalidated)
    assert [issue.code for issue in result.issues] == ["state-unreadable"]
    assert connection.closes == 1


def test_a_connection_that_is_not_idle_is_disposed_of_rather_than_repaired() -> None:
    connection = ScriptedConnection(idle=NotIdle("INERROR"))

    result = _release(connection, suspect=False, restore_authorization=True)

    assert isinstance(result, Invalidated)
    (issue,) = result.issues
    assert issue.code == "not-idle"
    assert issue.diagnostic.message == "its state was INERROR"
    assert connection.submitted == []


@pytest.mark.parametrize(
    ("connection", "suspect"),
    [
        (ScriptedConnection(), True),
        (ScriptedConnection(idle=NotIdle("INERROR")), False),
        (ScriptedConnection(idle="unreadable"), False),
    ],
)
def test_unsafe_principal_release_skips_role_restoration(
    connection: ScriptedConnection, suspect: bool
) -> None:
    result = _release(connection, suspect=suspect, restore_authorization=True)

    assert isinstance(result, Invalidated)
    assert RESTORE not in connection.submitted


def test_a_failed_disposal_does_not_fall_back_to_returning_a_suspect_connection() -> None:
    # Balancing the accounting is not worth offering the next caller a session
    # nothing can vouch for, and a closed flag after a failed close establishes
    # no disposal.
    connection = ScriptedConnection(close_failure=RuntimeError("close failed"))
    pool = pool_of(connection)

    result = _release(connection, pool, suspect=True)

    assert isinstance(result, ReleaseUnconfirmed)
    assert [issue.code for issue in result.issues] == ["suspect", "close-failed"]
    assert pool.hand_backs == 0


@pytest.mark.parametrize("suspect", [False, True], ids=["check-in", "discard"])
def test_a_failed_handoff_is_neither_retried_nor_followed_by_a_close(suspect: bool) -> None:
    # A hand-back that raised may still have handed the connection to another
    # caller, so retrying it or closing afterwards risks destroying somebody
    # else's session.
    connection = ScriptedConnection()
    pool = pool_of(connection, hand_back_failure=RuntimeError("the return failed"))

    result = _release(connection, pool, suspect=suspect)

    assert isinstance(result, ReleaseUnconfirmed)
    assert [(issue.phase, issue.code) for issue in result.issues][-1] == (
        "return",
        "handoff-failed",
    )
    assert pool.hand_backs == 1
    assert connection.closes == (1 if suspect else 0)


def test_a_cleanup_issue_carries_a_detached_diagnostic_and_no_live_object() -> None:
    connection = ScriptedConnection(idle=NotIdle("INTRANS"))
    result = _release(connection, suspect=False)

    (issue,) = result.issues
    assert isinstance(issue.diagnostic.message, str)
    assert issue.diagnostic.qualified_type.endswith("_Condition")
    assert not hasattr(issue.diagnostic, "__traceback__")


def test_a_release_unconfirmed_result_must_name_at_least_one_issue() -> None:
    with pytest.raises(ValueError, match="at least one cleanup issue"):
        ReleaseUnconfirmed(())


# --------------------------------------------------------------------------- #
# Leaving: revocation, and a context never entered.                           #
# --------------------------------------------------------------------------- #


def test_an_exit_whose_revocation_fails_still_gives_the_connection_back() -> None:
    # The exit is the only path back to the pool, so a revocation that does not
    # complete must not strand a connection outside it — and what does come back
    # is disposed of first, because a scope that may still reach it is not one
    # to offer the next caller.
    connection = ScriptedConnection()
    pool = pool_of(connection)
    driver = ScriptedDriver()
    driver.revoke_failure = RuntimeError("the scope could not be revoked")
    resource = login_context(pooled_runtime(pool, driver=driver))

    with pytest.raises(RuntimeError), resource:
        pass

    assert connection.closes == 1
    assert pool.returned == [connection]
    assert isinstance(resource.cleanup_result, Invalidated)


def test_leaving_a_context_that_was_never_entered_does_nothing() -> None:
    # Total on every exit: a context a caller built and abandoned has taken
    # nothing, so leaving it releases nothing and reports nothing.
    pool = pool_of()
    resource = _context(pool)
    resource.__exit__(None, None, None)
    assert (pool.returned, resource.cleanup_result) == ([], None)


# --------------------------------------------------------------------------- #
# The dial record: what a spent checkout reports, and what clears it.         #
# --------------------------------------------------------------------------- #


def test_a_spent_checkout_reports_the_latest_dial_failure() -> None:
    ledger = DialLedger()
    earlier = lost_session("earlier connection refusal")
    ledger.report_failure("unavailable", earlier)
    pool = pool_of(checkout_failure=checkout_failed("timeout"))
    route = PooledRoute("reader", pool, ledger)

    with pytest.raises(ConnectionAcquisitionError) as before_wait:
        check_out_within(route, monotonic() + 5.0)

    fresh = CredentialResolutionError("later credential refusal")
    pool.on_check_out = whatever_budget(lambda: ledger.report_failure("credentials_refused", fresh))
    with pytest.raises(ConnectionAcquisitionError) as during_wait:
        check_out_within(route, monotonic() + 5.0)

    assert before_wait.value.reason == "unavailable"
    assert before_wait.value.__cause__ is earlier
    assert during_wait.value.reason == "credentials_refused"
    assert during_wait.value.__cause__ is fresh


def test_a_handed_over_connection_clears_whatever_failure_was_on_record() -> None:
    ledger = DialLedger()
    ledger.report_failure("credentials_refused", CredentialResolutionError("no token"))

    check_out_within(PooledRoute("reader", pool_of(), ledger), monotonic() + 5.0)

    assert ledger.latest_failure is None


# --------------------------------------------------------------------------- #
# Preferred fallback: the reader within half the budget, then the writer.     #
# --------------------------------------------------------------------------- #


def test_a_healthy_reader_serves_a_preferred_acquisition_within_half_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Clock(monkeypatch)
    writer_pool, reader_pool = pool_of(), pool_of()
    resource = preferred_context(routed(writer_pool, reader_pool))

    with resource as scoped:
        scoped.submit("select 1")

    assert reader_pool.budgets == [7.5]
    assert writer_pool.budgets == []
    assert resource.selection == RouteSelection("reader")


def test_an_unreachable_reader_falls_back_to_the_writer_with_what_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An on-demand reader dials on this thread, so its failure surfaces at
    # once and the writer gets everything the reader did not spend.
    clock = Clock(monkeypatch)
    writer_pool = pool_of()
    reader_pool = _refusing(
        checkout_failed("unavailable", lost_session("connection refused")),
        after=lambda: setattr(clock, "now", 3.0),
    )
    resource = preferred_context(routed(writer_pool, reader_pool))

    with resource as scoped:
        scoped.submit("select 1")

    assert reader_pool.budgets == [7.5]
    assert writer_pool.budgets == [12.0]
    assert writer_pool.returned[0].submitted == ["select 1"]
    assert resource.selection == RouteSelection("writer", "unavailable")


def test_a_reader_share_spent_while_its_dials_failed_falls_back_at_the_share_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A retaining reader dials on its own workers and cannot wake a waiter, so
    # a failure recorded during the wait is noticed when the share runs out.
    clock = Clock(monkeypatch)
    writer_pool = pool_of()
    reader_pool = pool_of(checkout_failure=checkout_failed("timeout"))
    runtime = routed(writer_pool, reader_pool)

    def dial_fails_meanwhile(_budget: float) -> None:
        reader_route_of(runtime).dial_ledger.report_failure(
            "unavailable", lost_session("connection refused")
        )
        clock.now = 7.5

    reader_pool.on_check_out = dial_fails_meanwhile
    resource = preferred_context(runtime)

    with resource:
        pass

    assert writer_pool.budgets == [7.5]
    assert resource.selection == RouteSelection("writer", "unavailable")


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param("timeout", id="saturated"),
        pytest.param("queue_rejected", id="queue"),
        pytest.param("closed", id="closed"),
        pytest.param("authentication_refused", id="login-refused"),
        pytest.param("credentials_refused", id="creds"),
        pytest.param("preparation_failed", id="invalid-setup"),
    ],
)
def test_a_reader_that_is_busy_refused_or_closed_ends_a_preferred_acquisition(
    reason: Any,
) -> None:
    # No failed dial is on record for the busy reader.
    writer_pool = pool_of()
    resource = preferred_context(
        routed(writer_pool, pool_of(checkout_failure=checkout_failed(reason)))
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == reason
    assert refused.value.selection == RouteSelection("reader")
    assert writer_pool.budgets == []


def test_a_role_the_reader_denies_is_not_a_reason_to_fall_back() -> None:
    denied = RuntimeError("permission denied to set role")
    writer_pool = pool_of()
    resource = preferred_context(
        routed(writer_pool, pool_of(ScriptedConnection(failure=denied))), "tenant"
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.selection == RouteSelection("reader")
    assert writer_pool.budgets == []


def test_a_reader_success_after_its_share_is_refused_rather_than_used_or_fallen_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    writer_pool = pool_of()
    connection = ScriptedConnection()
    reader_pool = pool_of(connection)
    reader_pool.on_check_out = whatever_budget(lambda: setattr(clock, "now", 8.0))
    resource = preferred_context(routed(writer_pool, reader_pool))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert writer_pool.budgets == []
    assert reader_pool.returned == [connection]


def test_a_refused_reader_ends_a_preferred_acquisition_as_a_configuration_failure() -> None:
    writer_pool = pool_of()
    runtime = routed(writer_pool, pool_of(), reader_readiness="pending")
    mismatch = ProbeMismatch("another login")
    reader_route_of(runtime).mark_refused(mismatch)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        preferred_context(runtime).__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is mismatch
    assert writer_pool.budgets == []


def test_a_writer_that_also_fails_after_a_fallback_reports_the_writer_and_the_fallback() -> None:
    resource = preferred_context(
        routed(
            pool_of(checkout_failure=checkout_failed("timeout")),
            pool_of(
                checkout_failure=checkout_failed("unavailable", lost_session("connection refused"))
            ),
        )
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert refused.value.selection == RouteSelection("writer", "unavailable")
    assert resource.selection == RouteSelection("writer", "unavailable")


# --------------------------------------------------------------------------- #
# Setup that loses its connection moves to the writer; modeled reads do not.  #
# --------------------------------------------------------------------------- #


def test_a_reader_lost_installing_the_principal_falls_back_and_installs_it_on_the_writer() -> None:
    reader_connection = ScriptedConnection(lost=lost_session())
    writer_connection = ScriptedConnection()
    reader_pool, writer_pool = pool_of(reader_connection), pool_of(writer_connection)
    resource = preferred_context(routed(writer_pool, reader_pool), "tenant_reader")

    with resource as scoped:
        scoped.submit("select current_user")

    assert reader_connection.closes == 1
    assert len(reader_pool.budgets) == 1
    assert writer_connection.submitted == [
        "authorize tenant_reader",
        "select current_user",
        RESTORE,
    ]
    assert resource.selection == RouteSelection("writer", "connection_lost")


def test_a_fallen_back_role_installation_earns_no_second_replacement() -> None:
    writer_connection = ScriptedConnection(lost=lost_session())
    writer_pool = pool_of(writer_connection, ScriptedConnection())
    resource = preferred_context(
        routed(writer_pool, pool_of(ScriptedConnection(lost=lost_session()))), "tenant_reader"
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.selection == RouteSelection("writer", "connection_lost")
    assert len(writer_pool.budgets) == 1


def test_a_reader_lost_at_its_first_begin_opens_the_boundary_on_the_writer_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    reader_connection = ScriptedConnection(
        lost=lost_session(), when_lost=lambda: setattr(clock, "now", 2.0)
    )
    writer_connection = ScriptedConnection()
    reader_pool, writer_pool = pool_of(reader_connection), pool_of(writer_connection)
    resource = preferred_context(routed(writer_pool, reader_pool))

    with resource as scoped:
        assert resource.selection == RouteSelection("reader")
        scoped.submit("BEGIN", replay_safe=True, setup=True)
        scoped.submit("select 1")

    assert reader_connection.submitted == ["BEGIN"]
    assert reader_connection.closes == 1
    assert writer_pool.budgets == [13.0]
    assert writer_connection.submitted == ["BEGIN", "select 1"]
    assert resource.selection == RouteSelection("writer", "connection_lost")


@pytest.mark.parametrize("ending", ["late", "closed"])
def test_a_boundary_that_opens_past_its_step_or_its_runtime_is_refused_as_the_acquisition_s(
    monkeypatch: pytest.MonkeyPatch, ending: str
) -> None:
    # The reader's half ends at 5.0; a BEGIN answering at 20.0, or after the
    # runtime closed, is no allowance of its own.
    clock = Clock(monkeypatch)

    def slow_begin(text: str) -> None:
        if text != "BEGIN":
            return
        if ending == "late":
            clock.now = 20.0
        else:
            runtime.close()

    reader_connection = ScriptedConnection(on_submit=slow_begin)
    runtime = routed(pool_of(), pool_of(reader_connection), acquire_timeout=10.0)
    resource = preferred_context(runtime)

    with resource as scoped, pytest.raises(ConnectionAcquisitionError) as refused:
        scoped.submit("BEGIN", replay_safe=True, setup=True)

    assert refused.value.reason == ("timeout" if ending == "late" else "closed")
    assert refused.value.selection == RouteSelection("reader")
    assert reader_connection.submitted == ["BEGIN"]
    assert reader_connection.closes == 1
    assert isinstance(resource.cleanup_result, Invalidated)


def test_a_writer_replacement_that_arrives_past_the_deadline_is_refused_unused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    writer_connection = ScriptedConnection()
    writer_pool = pool_of(writer_connection)
    writer_pool.on_check_out = whatever_budget(lambda: setattr(clock, "now", 20.0))
    resource = preferred_context(
        routed(writer_pool, pool_of(ScriptedConnection(lost=lost_session())), acquire_timeout=10.0)
    )

    with resource as scoped, pytest.raises(ConnectionAcquisitionError) as refused:
        scoped.submit("BEGIN", replay_safe=True, setup=True)

    assert refused.value.reason == "timeout"
    assert refused.value.selection == RouteSelection("writer", "connection_lost")
    assert writer_connection.submitted == []
    assert writer_pool.check_ins == [writer_connection]
    assert resource.cleanup_result == Returned()


def test_a_begin_after_the_principal_was_installed_is_no_second_opportunity() -> None:
    def lose_at_begin(text: str) -> None:
        if text == "BEGIN":
            reader_connection.lost = lost_session()

    reader_connection = ScriptedConnection(on_submit=lose_at_begin)
    writer_pool = pool_of()
    resource = preferred_context(routed(writer_pool, pool_of(reader_connection)), "tenant")

    with resource as scoped, pytest.raises(SessionLost):
        scoped.submit("BEGIN", replay_safe=True, setup=True)

    assert writer_pool.budgets == []
    assert resource.selection == RouteSelection("reader")


def test_a_pending_reader_s_lost_proof_falls_back_and_leaves_the_reader_pending() -> None:
    writer_connection = ScriptedConnection()
    writer_pool = pool_of(writer_connection)
    runtime = routed(
        writer_pool, pool_of(ScriptedConnection(lost=lost_session())), reader_readiness="pending"
    )
    resource = preferred_context(runtime, "tenant_reader")

    with resource:
        pass

    assert reader_route_of(runtime).readiness() == "pending"
    # The writer is verified, so it runs no proof, and the role is installed there.
    assert writer_connection.submitted == ["authorize tenant_reader", RESTORE]
    assert resource.selection == RouteSelection("writer", "connection_lost")


def test_a_modeled_read_s_replacement_stays_on_the_reader_it_began_on() -> None:
    broken, fresh = ScriptedConnection(lost=lost_session()), ScriptedConnection()
    reader_pool, writer_pool = pool_of(broken, fresh), pool_of()
    resource = preferred_context(routed(writer_pool, reader_pool))

    with resource as scoped:
        scoped.submit("select 1", replay_safe=True)

    assert fresh.submitted == ["select 1"]
    assert writer_pool.budgets == []
    assert resource.selection == RouteSelection("reader")


def test_a_reader_disposal_that_cannot_be_confirmed_refuses_the_fallback() -> None:
    reader_connection = ScriptedConnection(
        lost=lost_session(), close_failure=RuntimeError("no close")
    )
    writer_pool = pool_of()
    resource = preferred_context(routed(writer_pool, pool_of(reader_connection)), "tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert isinstance(resource.cleanup_result, ReleaseUnconfirmed)
    assert writer_pool.budgets == []


def test_an_interrupt_a_lost_reader_setup_displaced_propagates_and_falls_back_nowhere() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool = pool_of()
    resource = preferred_context(
        routed(writer_pool, pool_of(ScriptedConnection(lost=_lost_while_draining(interrupt)))),
        "tenant_reader",
    )

    with pytest.raises(KeyboardInterrupt) as raised:
        resource.__enter__()

    assert raised.value is interrupt
    assert writer_pool.budgets == []


# --------------------------------------------------------------------------- #
# A key reservation's lease: the writer's reservation pool, bounded by one    #
# deadline its setup carries into the session.                                #
# --------------------------------------------------------------------------- #


def test_a_reservation_lease_bounds_its_statements_by_what_remains_of_its_deadline() -> None:
    connection = ScriptedConnection()
    runtime = pooled_runtime(pool_of(), reservation=pool_of(connection))
    source = runtime.reservation_source()
    assert source.reservation_timeout == 15.0

    with source.new_context(monotonic() + 5.0) as leased:
        assert leased is not None

    assert connection.submitted == ["limit"]
    (seconds,) = connection.limits
    assert 0.0 < seconds <= 5.0


def test_a_reservation_whose_deadline_passed_takes_no_connection() -> None:
    connection = ScriptedConnection()
    pool = pool_of(connection)
    runtime = pooled_runtime(pool_of(), reservation=pool)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        runtime.reservation_source().new_context(monotonic() - 1.0).__enter__()

    assert refused.value.reason == "timeout"
    assert connection.submitted == []
    assert pool.returned == []


def test_a_reservation_whose_deadline_passes_bounding_its_statements_is_not_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    slow = ScriptedConnection(on_submit=lambda _text: setattr(clock, "now", 11.0))
    pool = pool_of(slow)
    resource = pooled_runtime(pool_of(), reservation=pool).reservation_source().new_context(10.0)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert slow.submitted == ["limit"]
    assert resource.cleanup_result == Returned()
    assert pool.returned == [slow]


def test_a_statement_bound_the_session_refuses_fails_preparation_and_disposes_it() -> None:
    refusal = RuntimeError("cannot set statement_timeout")
    refusing = ScriptedConnection(failure=refusal)
    runtime = pooled_runtime(pool_of(), reservation=pool_of(refusing))
    resource = runtime.reservation_source().new_context(monotonic() + 5.0)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is refusal
    assert issues_of(resource.cleanup_result) == [("inspect", "suspect")]


def test_an_interrupt_bounding_the_statements_propagates_once_disposed() -> None:
    interrupted = ScriptedConnection(failure=KeyboardInterrupt())
    pool = pool_of(interrupted)
    runtime = pooled_runtime(pool_of(), reservation=pool)
    resource = runtime.reservation_source().new_context(monotonic() + 5.0)

    with pytest.raises(KeyboardInterrupt):
        resource.__enter__()

    assert pool.returned == [interrupted]
    assert issues_of(resource.cleanup_result) == [("inspect", "suspect")]


def test_a_reservation_lease_over_a_session_ended_while_idle_bounds_a_replacement() -> None:
    broken = ScriptedConnection(lost=lost_session())
    fresh = ScriptedConnection()
    pool = pool_of(broken, fresh)
    resource = (
        pooled_runtime(pool_of(), reservation=pool)
        .reservation_source()
        .new_context(monotonic() + 5.0)
    )

    with resource:
        pass

    assert fresh.submitted == ["limit"]
    assert (broken.closes, fresh.closes) == (1, 0)
    assert pool.returned == [broken, fresh]
    assert resource.cleanup_result == Returned()


def test_a_reservation_statement_that_loses_its_session_is_never_sent_again() -> None:
    # The server may have reserved a block before the session went, so the
    # statement is not resent on a replacement: the failure is the caller's,
    # and the lease is disposed of rather than handed to the next reservation.
    def lose_after_setup(_text: str) -> None:
        if lost.submitted:
            lost.lost = lost_session()

    lost = ScriptedConnection(on_submit=lose_after_setup)
    pool = pool_of(lost, ScriptedConnection())
    resource = cast(
        "Any",
        pooled_runtime(pool_of(), reservation=pool)
        .reservation_source()
        .new_context(monotonic() + 5.0),
    )

    with resource as leased, pytest.raises(SessionLost):
        leased.submit("select pg_catalog.nextval(?)", "px.ids")

    assert len(pool.budgets) == 1
    assert len(lost.submitted) == 2
    assert lost.closes == 1
    assert isinstance(resource.cleanup_result, Invalidated)


def test_a_reservation_checkout_waits_only_what_remains_of_its_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The allocator's wait on another reservation already spent part of the
    # budget; the checkout gets the rest of it, not a fresh acquire timeout.
    Clock(monkeypatch, now=6.0)
    pool = pool_of(ScriptedConnection())
    resource = pooled_runtime(pool_of(), reservation=pool).reservation_source().new_context(10.0)

    with resource:
        pass

    assert pool.budgets == [pytest.approx(4.0)]
