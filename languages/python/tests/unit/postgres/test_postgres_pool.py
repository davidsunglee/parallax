"""The runtime's resource lifetimes, over a scripted pool and driver (Docker-free).

Three things live here and nowhere else, so they are proven here rather than
against a container: what readiness establishes before a handle is published,
what one acquisition is allowed to do, and what releasing one establishes.
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

import logging
from collections.abc import Callable, Mapping
from time import monotonic
from typing import Any, cast

import pytest

from parallax.core.internal.db_port import (
    RESOURCE_LOGGER_NAME,
    ConnectionAcquisitionError,
    CredentialResolutionError,
    DatabaseStartupError,
    Invalidated,
    NotIdle,
    PoolDetached,
    ProbeMismatch,
    ReleaseUnconfirmed,
    Returned,
    Route,
    RouteCapabilities,
    RouteSelection,
    SubmissionProgress,
)
from parallax.core.internal.db_port._runtime._dial_record import DialLedger
from parallax.core.internal.dialect import POSTGRES
from parallax.postgres._context import PostgresConnectionContext, checkout, release
from parallax.postgres._route import PostgresRoute
from parallax.postgres._route_plan import RoutePlan
from parallax.postgres._runtime import PostgresRuntime
from parallax.postgres._startup import open_runtime
from tests.unit._scripted_native import (
    PROVE,
    RESTORE,
    Clock,
    ScriptedConnection,
    ScriptedDriver,
    ScriptedPool,
    SessionLost,
    checkout_failed,
)

_WRITER: Mapping[Route, RouteCapabilities] = {"writer": RouteCapabilities.every_level()}
_ROUTED: Mapping[Route, RouteCapabilities] = {
    "writer": RouteCapabilities.every_level(),
    "reader": RouteCapabilities(frozenset({"read_committed", "repeatable_read"})),
}

type _Pool = ScriptedPool[ScriptedConnection]


def _pool(*connections: ScriptedConnection, **kwargs: Any) -> _Pool:
    """A scripted pool over ``connections``, or one fresh connection."""
    return ScriptedPool(*(connections or (ScriptedConnection(),)), **kwargs)


def _whatever_budget(action: Callable[[], object]) -> Callable[[float], None]:
    """A checkout hook running ``action`` whatever budget the checkout was given."""

    def hook(_budget: float) -> None:
        action()

    return hook


def _lost(message: str = "server closed the connection unexpectedly") -> SessionLost:
    return SessionLost(message)


def _runtime(
    pool: _Pool,
    *,
    acquire_timeout: float = 15.0,
    reservation: _Pool | None = None,
    driver: ScriptedDriver | None = None,
    routes: Mapping[Route, RouteCapabilities] = _WRITER,
) -> PostgresRuntime[ScriptedConnection, object]:
    return PostgresRuntime(
        ScriptedDriver() if driver is None else driver,
        dialect=POSTGRES,
        routes=routes,
        writer=PostgresRoute("writer", pool, DialLedger()),
        reservation=PostgresRoute(
            "writer", _pool() if reservation is None else reservation, DialLedger(), "reservation"
        ),
        acquire_timeout=acquire_timeout,
    )


def _context(
    pool: _Pool,
    *,
    deadline: float | None = None,
    admit: Any = None,
    authorization: object = None,
    ledger: DialLedger | None = None,
) -> Any:
    runtime = _runtime(pool)
    return PostgresConnectionContext(
        (
            (
                PostgresRoute("writer", pool, DialLedger() if ledger is None else ledger),
                monotonic() + 5.0 if deadline is None else deadline,
            ),
        ),
        runtime._admit if admit is None else admit,  # pyright: ignore[reportPrivateUsage] - the context is built with the runtime's own admission check, which is package-private
        ScriptedDriver(),
        authorization,
        expected_login=None,
    )


def _login_context(runtime: PostgresRuntime[ScriptedConnection, object]) -> Any:
    return runtime.login_source().new_context("writer_only")


def _open_runtime(
    driver: ScriptedDriver,
    routes: Mapping[Route, RouteCapabilities] = _WRITER,
    *,
    reader_startup: Any = "deferrable",
) -> PostgresRuntime[ScriptedConnection, object]:
    return open_runtime(
        driver,
        dialect=POSTGRES,
        routes=routes,
        acquire_timeout=15.0,
        startup_timeout=30.0,
        reader_startup=reader_startup,
    )


def _opened(pool: _Pool) -> ScriptedDriver:
    """A driver whose writer pool is ``pool``."""
    return ScriptedDriver(pools={"writer": pool})


def _admitted(_deadline: float) -> None:
    return


def _issues(result: object) -> list[tuple[str, str]]:
    assert isinstance(result, Returned | Invalidated | ReleaseUnconfirmed)
    return [(issue.phase, issue.code) for issue in result.issues]


def _unsent(_connection: ScriptedConnection, _submission: SubmissionProgress) -> None:
    return None


# --------------------------------------------------------------------------- #
# Readiness: only a runtime that has proved it can execute is returned.        #
# --------------------------------------------------------------------------- #


def test_startup_opens_every_pool_then_proves_and_returns_one_connection() -> None:
    connection = ScriptedConnection()
    pool = _pool(connection)
    driver = _opened(pool)

    runtime = _open_runtime(driver)
    try:
        assert driver.opened == [("writer", "application"), ("writer", "reservation")]
        assert len(pool.budgets) == 1
        assert connection.submitted == [PROVE]
        assert pool.returned == [connection]
        assert driver.pool("reservation").budgets == []
        assert runtime.login_identity == "runtime-login"
    finally:
        runtime.close()


def test_a_pool_that_will_not_open_fails_startup_at_the_open_phase() -> None:
    # Opening is a phase of readiness with a failure of its own, and the
    # failure that ended it stays the cause.
    refusal = RuntimeError("the pool would not open")

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(ScriptedDriver(pools={"writer": refusal}))

    assert (failed.value.route, failed.value.phase) == ("writer", "open")
    assert str(failed.value) == (
        "database-startup-failed: the database runtime's writer connection pool could not be opened"
    )
    assert failed.value.__cause__ is refusal


def test_a_reservation_pool_that_will_not_open_names_its_purpose_and_closes_the_writer() -> None:
    writer_pool = _pool()
    driver = ScriptedDriver(pools={"writer": writer_pool, "reservation": RuntimeError("no")})

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(driver)

    assert (failed.value.route, failed.value.phase) == ("writer", "open")
    assert "writer-reservation connection pool" in str(failed.value)
    assert writer_pool.budgets == []
    assert writer_pool.closes == 1


@pytest.mark.parametrize(
    ("refusal", "reason"),
    [
        (CredentialResolutionError("RDS IAM token could not be generated"), "credentials_refused"),
        (RuntimeError("password authentication failed"), "authentication_refused"),
        (RuntimeError("this connection's client encoding is 'LATIN1'"), "preparation_failed"),
    ],
)
def test_startup_reports_the_recorded_dial_refusal(refusal: Exception, reason: Any) -> None:
    pool = _pool(checkout_failure=checkout_failed("timeout"))
    driver = ScriptedDriver(pools={"writer": pool}, recorded={"writer": (reason, refusal)})

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(driver)

    assert (failed.value.route, failed.value.phase) == ("writer", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError)
    assert cause.reason == reason
    assert cause.__cause__ is refusal
    assert pool.closes == 1


def test_a_startup_acquisition_that_fails_carries_its_phase_and_cleanup() -> None:
    pool = _pool(checkout_failure=checkout_failed("timeout"))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "acquire"
    assert isinstance(failed.value.__cause__, ConnectionAcquisitionError)
    assert pool.closes == 1


def test_a_probe_that_does_not_read_back_what_it_asked_for_fails_startup() -> None:
    mismatch = "the startup probe returned 2 rows rather than one"
    connection = ScriptedConnection(mismatch=mismatch)
    pool = _pool(connection)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "probe"
    assert str(failed.value) == f"database-startup-failed: {mismatch}"
    assert isinstance(failed.value.__cause__, ProbeMismatch)
    # The probe scope is released on the way out rather than leaked.
    assert pool.returned == [connection]
    assert pool.closes == 1


def test_a_probe_scope_whose_release_cannot_be_confirmed_fails_startup() -> None:
    # A successful probe followed by an unconfirmed release is not a
    # ready runtime: the connection's fate is unknown and nothing else will
    # revisit it.
    pool = _pool(hand_back_failure=RuntimeError("the return failed"))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "release"
    assert isinstance(failed.value.cleanup_result, ReleaseUnconfirmed)
    assert failed.value.__cause__ is None
    assert pool.closes == 1


def test_readiness_shares_one_budget_that_is_never_restarted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A budget that stops the next phase from starting: it cannot interrupt a
    # native call in flight, and it does not begin a phase it cannot finish.
    from parallax.postgres import _startup as startup_module

    clock = iter([0.0, 99.0])
    monkeypatch.setattr(startup_module, "monotonic", lambda: next(clock))
    pool = _pool()

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "acquire"
    assert pool.budgets == []


def test_a_broken_startup_probe_is_replaced_within_the_one_startup_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The probe is replay-safe and its lease's first submission, so it gets the
    # same one replacement as any other — taken from what remains of the
    # startup budget, which nothing restarts.
    clock = Clock(monkeypatch)
    broken = ScriptedConnection(lost=_lost(), when_lost=lambda: setattr(clock, "now", 10.0))
    fresh = ScriptedConnection()
    pool = _pool(broken, fresh)

    runtime = _open_runtime(_opened(pool))

    assert runtime.login_identity == "runtime-login"
    assert pool.budgets == [30.0, 20.0]
    assert broken.submitted == fresh.submitted == [PROVE]
    assert pool.returned == [broken, fresh]


def test_a_broken_startup_probe_past_its_budget_takes_no_replacement_and_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The raw driver failure is the cause: nothing translates it first.
    clock = Clock(monkeypatch)
    original = _lost()
    broken = ScriptedConnection(lost=original, when_lost=lambda: setattr(clock, "now", 31.0))
    pool = _pool(broken, ScriptedConnection())

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "probe"
    assert failed.value.__cause__ is original
    assert pool.budgets == [30.0]
    assert _issues(failed.value.cleanup_result) == [("inspect", "suspect")]
    assert pool.closes == 1


def test_a_probe_answering_after_the_startup_budget_fails_its_release_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The proof is not admitted again once it answers: the connection it ran
    # on is given back for reuse, and the spent budget is what the next phase
    # check reports.
    clock = Clock(monkeypatch)
    slow = ScriptedConnection(on_submit=lambda _text: setattr(clock, "now", 31.0))
    pool = _pool(slow)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "release"
    assert failed.value.__cause__ is None
    assert failed.value.cleanup_result == Returned()
    assert pool.check_ins == [slow]


# --------------------------------------------------------------------------- #
# Acquisition: what a checkout is allowed to become.                           #
# --------------------------------------------------------------------------- #


def test_an_expired_budget_refuses_before_asking_the_pool_for_anything() -> None:
    pool = _pool()
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
    resource = _context(_pool(checkout_failure=checkout_failed(reason, native)))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == reason
    assert refused.value.__cause__ is native
    # Nothing was taken, so there is nothing to have cleaned up.
    assert resource.cleanup_result is None


def test_a_timeout_with_nothing_on_record_is_a_bare_timeout_caused_by_the_wait() -> None:
    native = RuntimeError("couldn't get a connection")
    ledger = DialLedger()
    resource = _context(_pool(checkout_failure=checkout_failed("timeout", native)), ledger=ledger)

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
    resource = _context(_pool(checkout_failure=checkout_failed("timeout")), ledger=ledger)

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
    resource = _context(_pool(checkout_failure=checkout_failed("timeout")), ledger=ledger)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "credentials_refused"
    assert refused.value.__cause__ is refusal
    assert "authenticated" in str(refused.value)


def test_the_remaining_budget_is_what_the_pool_s_one_wait_is_given() -> None:
    pool = _pool()
    _context(pool, deadline=monotonic() + 2.0).__enter__()
    (given,) = pool.budgets
    assert 0.0 < given <= 2.0


@pytest.mark.parametrize(
    ("reading", "state"), [(NotIdle("INTRANS"), "INTRANS"), ("unreadable", "unreadable")]
)
def test_a_checkout_that_hands_over_a_connection_that_is_not_idle_is_refused(
    reading: Any, state: str
) -> None:
    # No modeled SQL runs on it and no unknown transaction is rolled back to
    # make it usable: an adapter invariant this broken is reported.
    connection = ScriptedConnection(idle=reading)
    pool = _pool(connection)
    resource = _context(pool)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert f"whose state is {state} rather than idle" in str(refused.value)
    assert connection.submitted == []
    # The partial ownership is cleaned up, and a connection in this state is
    # disposed of rather than offered to the next caller.
    assert isinstance(resource.cleanup_result, Invalidated)
    assert connection.closes == 1


def test_a_late_native_success_is_released_rather_than_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The caller has already been waiting past what it asked for; its own
    # timeout handling is a better answer than work starting after the budget.
    # The budget is live when the checkout starts and spent when it returns,
    # which is the race a cooperative deadline can only lose.
    from parallax.postgres import _runtime as runtime_module

    connection = ScriptedConnection()
    pool = _pool(connection)
    monkeypatch.setattr(runtime_module, "monotonic", lambda: 1e18)
    ledger = DialLedger()
    ledger.report_failure("unavailable", _lost("connection refused"))
    resource = _context(pool, ledger=ledger)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert connection.submitted == []
    assert resource.cleanup_result == Returned()
    assert pool.check_ins == [connection]
    # The handover still cleared the record: the route did hand over a connection.
    assert ledger.latest_failure is None


def test_a_context_is_entered_exactly_once_and_a_failed_entry_spends_it() -> None:
    pool = _pool()
    resource = _context(pool)
    with resource, pytest.raises(RuntimeError):
        resource.__enter__()
    with pytest.raises(RuntimeError):
        resource.__enter__()

    failed = _context(_pool(checkout_failure=checkout_failed("closed")))
    with pytest.raises(ConnectionAcquisitionError):
        failed.__enter__()
    with pytest.raises(RuntimeError):
        failed.__enter__()


def test_entering_opens_fresh_execution_over_the_context_and_leaving_revokes_it() -> None:
    # The driver's execution borrows the context as its lease, and a reference
    # kept past the exit reaches nothing.
    connection = ScriptedConnection()
    driver = ScriptedDriver()
    runtime = _runtime(_pool(connection), driver=driver)
    resource = _login_context(runtime)

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
    pool = _pool(suspect, fresh)

    first = _context(pool)
    with first as scoped:
        scoped.lease.mark_suspect()
        assert scoped.lease.suspect
    second = _context(pool)
    with second as scoped:
        scoped.submit("select 1")

    assert _issues(first.cleanup_result) == [("inspect", "suspect")]
    assert suspect.closes == 1
    assert fresh.submitted == ["select 1"]
    assert second.cleanup_result == Returned()
    assert pool.returned == [suspect, fresh]


def test_a_runtime_publishes_an_immutable_copy_of_the_routes_it_was_declared() -> None:
    routes: dict[Route, RouteCapabilities] = {"writer": RouteCapabilities.every_level()}
    runtime = _runtime(_pool(), routes=routes)
    routes["reader"] = RouteCapabilities(frozenset())

    assert dict(runtime.routes) == {"writer": RouteCapabilities.every_level()}
    with pytest.raises(TypeError):
        cast("Any", runtime.routes)["reader"] = RouteCapabilities(frozenset())


def test_a_writer_only_acquisition_selects_the_writer_once_entered() -> None:
    pool = _pool()
    resource = _runtime(pool).login_source().new_context("writer_only")

    assert resource.selection is None
    with resource:
        assert resource.selection == RouteSelection("writer")
    assert resource.selection == RouteSelection("writer")


@pytest.mark.parametrize("policy", ["reader_only", "reader_preferred"])
def test_a_writer_only_runtime_refuses_to_build_a_reader_context(policy: str) -> None:
    # Core resolves every policy against the declared routes first, so being
    # asked for one this runtime cannot serve is a caller defect, refused before
    # anything is taken.
    pool = _pool()

    with pytest.raises(ValueError, match="does not serve"):
        _runtime(pool).login_source().new_context(cast("Any", policy))

    assert pool.budgets == []


def test_a_refused_entry_reports_the_writer_on_the_context_and_the_failure_alike() -> None:
    pool = _pool(checkout_failure=checkout_failed("timeout"))
    resource = _login_context(_runtime(pool))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert refused.value.selection == RouteSelection("writer")
    assert resource.selection == RouteSelection("writer")


def test_authority_binding_checks_its_authorization_once_and_acquires_nothing() -> None:
    pool = _pool()
    driver = ScriptedDriver()
    runtime = _runtime(pool, driver=driver)

    source = runtime.principal_source("tenant_reader")
    first = source.new_context("writer_only")
    second = source.new_context("writer_only")

    assert first is not second
    assert driver.authorizations == ["tenant_reader"]
    assert pool.budgets == []
    assert not hasattr(runtime, "connection")


def test_an_authorization_the_driver_refuses_binds_nothing_and_acquires_nothing() -> None:
    pool = _pool()
    driver = ScriptedDriver()
    refusal = ValueError("not this driver's authorization")
    driver.authorization_refusal = refusal

    with pytest.raises(ValueError) as refused:
        _runtime(pool, driver=driver).principal_source(7)

    assert refused.value is refusal
    assert pool.budgets == []


def test_an_installed_authorization_is_restored_before_its_connection_is_reused() -> None:
    connection = ScriptedConnection()
    pool = _pool(connection)
    resource = _context(pool, authorization="tenant_reader")

    with resource as scoped:
        scoped.submit("select current_user")

    assert connection.submitted == ["authorize tenant_reader", "select current_user", RESTORE]
    assert resource.cleanup_result == Returned()


def test_role_installation_preserves_a_control_flow_exception() -> None:
    connection = ScriptedConnection(failure=KeyboardInterrupt())
    resource = _context(_pool(connection), authorization="tenant_reader")

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

    pool = _pool(connection)
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
    pool = _pool(connection)
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
# First use: one replacement of a broken connection, inside the one lease.     #
# --------------------------------------------------------------------------- #


def test_a_broken_first_designated_read_is_submitted_once_more_on_a_replacement() -> None:
    # The same prepared inputs reach the replacement: the one object both
    # sessions were handed. The original is disposed of and handed back before
    # the replacement is asked for, and no cleanup is published while in use.
    binds = [[1, 2]]
    broken = ScriptedConnection(lost=_lost())
    fresh = ScriptedConnection(rows=[(1,)])
    pool = _pool(broken, fresh)
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
    pool = _pool(connection, ScriptedConnection())

    with _context(pool) as scoped, pytest.raises(type(refusal)) as failed:
        scoped.submit("select 1", replay_safe=True)

    assert failed.value is refusal
    assert len(pool.budgets) == 1


def test_a_failure_on_a_broken_session_the_driver_does_not_classify_is_not_replaced() -> None:
    connection = ScriptedConnection(failure=RuntimeError("not a driver failure"))
    connection.broken = True
    pool = _pool(connection, ScriptedConnection())

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
    pool = _pool(connection, ScriptedConnection())

    with _context(pool) as scoped:
        scoped.submit("first", replay_safe=replay_safe, setup=setup)
        connection.lost = _lost()
        with pytest.raises(SessionLost):
            scoped.submit("select 2", replay_safe=True)

    assert len(pool.budgets) == 1


def test_a_write_that_meets_a_broken_session_first_is_never_replaced() -> None:
    broken = ScriptedConnection(lost=_lost())
    pool = _pool(broken, ScriptedConnection())

    with _context(pool) as scoped, pytest.raises(SessionLost):
        scoped.submit("update t set v = 1")

    assert len(pool.budgets) == 1
    assert broken.submitted == ["update t set v = 1"]


def test_a_child_read_after_its_root_has_no_opportunity_to_claim() -> None:
    # A single child fetch is a designated read through the same seam as its
    # root, carrying the keys the root just gathered; the root already spent
    # the lease's one opportunity, and designation does not reopen it.
    connection = ScriptedConnection(rows=[(3,), (4,)])
    pool = _pool(connection, ScriptedConnection())

    with _context(pool) as scoped:
        keys = [row[0] for row in scoped.submit("select id from root", replay_safe=True)]
        connection.lost = _lost()
        with pytest.raises(SessionLost):
            scoped.submit("select * from child", keys, replay_safe=True)

    assert connection.prepared[-1] == ([3, 4],)
    assert len(pool.budgets) == 1
    assert pool.returned == [connection]


def test_a_fatal_first_submission_spends_the_opportunity_and_propagates_as_itself() -> None:
    connection = ScriptedConnection(failure=KeyboardInterrupt())
    pool = _pool(connection, ScriptedConnection())

    with _context(pool) as scoped:
        with pytest.raises(KeyboardInterrupt):
            scoped.submit("select 1", replay_safe=True)
        connection.failure = None
        connection.lost = _lost()
        with pytest.raises(SessionLost):
            scoped.submit("select 2", replay_safe=True)

    assert len(pool.budgets) == 1


def test_a_failure_after_the_answer_has_spent_the_opportunity() -> None:
    # Fetching and decoding come after the submission answered, so their
    # failure is never one a replacement could repair, even on a session the
    # driver then reports broken.
    connection = ScriptedConnection(after_answer=_lost("lost while fetching"))
    connection.broken = True
    pool = _pool(connection, ScriptedConnection())

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
    pool = _pool(broken, fresh)

    with _context(pool) as scoped:
        scoped.lease.run(_unsent, replay_safe=False)
        with pytest.raises(ValueError, match="before anything was sent"):
            scoped.lease.run(refuses_before_sending, replay_safe=True)
        broken.lost = _lost()
        assert scoped.submit("select 1", replay_safe=True) == [(1,)]

    assert len(pool.budgets) == 2
    assert broken.submitted == fresh.submitted == ["select 1"]


def _lost_while_draining(interrupt: BaseException) -> SessionLost:
    # A driver may answer an interrupt during a wait by finishing its exchange
    # with the server; a session that breaks then raises its driver failure in
    # the interrupt's place, carrying the interrupt as context.
    lost = _lost()
    lost.__context__ = interrupt
    return lost


@pytest.mark.parametrize("setup", [False, True], ids=["read", "begin"])
@pytest.mark.parametrize("interrupted", [KeyboardInterrupt, SystemExit])
def test_an_interrupt_a_broken_first_submission_displaced_propagates_and_is_not_replaced(
    setup: bool, interrupted: type[BaseException]
) -> None:
    interrupt = interrupted()
    broken = ScriptedConnection(lost=_lost_while_draining(interrupt))
    pool = _pool(broken, ScriptedConnection())
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
    pool = _pool(broken, ScriptedConnection())
    resource = _context(pool, authorization="tenant_reader")

    with pytest.raises(KeyboardInterrupt) as raised:
        resource.__enter__()

    assert raised.value is interrupt
    assert len(pool.budgets) == 1
    assert pool.returned == [broken]


def test_an_interrupt_already_being_handled_is_not_one_the_failure_displaced() -> None:
    # Work run while an earlier interrupt is handled inherits it as context
    # without the submission having been interrupted, so replacement proceeds.
    broken = ScriptedConnection(lost=_lost())
    fresh = ScriptedConnection(rows=[(1,)])
    pool = _pool(broken, fresh)

    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        with _context(pool) as scoped:
            rows = scoped.submit("select 1", replay_safe=True)

    assert rows == [(1,)]
    assert len(pool.budgets) == 2
    assert pool.returned == [broken, fresh]


def test_a_replacement_that_also_breaks_reports_its_own_failure_and_is_not_replaced() -> None:
    first, second = _lost("the first session is gone"), _lost("the second session is gone")
    broken = ScriptedConnection(lost=first)
    also_broken = ScriptedConnection(lost=second)
    pool = _pool(broken, also_broken, ScriptedConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(SessionLost) as failed:
        scoped.submit("select 1", replay_safe=True)

    assert failed.value is second
    assert second.__context__ is None
    assert len(pool.budgets) == 2
    assert pool.returned == [broken, also_broken]
    assert _issues(resource.cleanup_result) == [("inspect", "not-idle")]


def test_an_unavailable_replacement_preserves_the_original_failure_and_its_cleanup() -> None:
    # The original was disposed of and handed back, and that is what the
    # context reports once it exits — published then, and only then.
    original = _lost()
    broken = ScriptedConnection(lost=original)
    pool = _pool(broken, ScriptedConnection())
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
    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]


def test_a_replacement_that_is_not_idle_is_given_back_and_its_cleanup_is_what_is_reported() -> None:
    original = _lost()
    broken = ScriptedConnection(lost=original)
    busy = ScriptedConnection(idle=NotIdle("INTRANS"))
    pool = _pool(broken, busy)
    resource = _context(pool)

    with resource as scoped, pytest.raises(SessionLost) as failed:
        scoped.submit("select 1", replay_safe=True)

    assert failed.value is original
    assert busy.submitted == []
    assert pool.returned == [broken, busy]
    assert _issues(resource.cleanup_result) == [("inspect", "not-idle")]
    assert busy.closes == 1


def test_a_disposal_that_failed_ends_replacement_and_is_reported_without_repeating_it() -> None:
    broken = ScriptedConnection(lost=_lost(), close_failure=RuntimeError("close failed"))
    pool = _pool(broken, ScriptedConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(SessionLost):
        scoped.submit("select 1", replay_safe=True)

    result = resource.cleanup_result
    assert isinstance(result, ReleaseUnconfirmed)
    assert _issues(result) == [("inspect", "suspect"), ("dispose", "close-failed")]
    assert (len(pool.budgets), pool.hand_backs, broken.closes) == (1, 0, 1)
    resource.__exit__(None, None, None)
    assert resource.cleanup_result is result
    assert broken.closes == 1


def test_a_handoff_that_failed_is_neither_retried_nor_followed_by_a_close_or_a_checkout() -> None:
    broken = ScriptedConnection(lost=_lost())
    pool = _pool(broken, ScriptedConnection(), hand_back_failure=RuntimeError("the return failed"))
    resource = _context(pool)

    with resource as scoped, pytest.raises(SessionLost):
        scoped.submit("select 1", replay_safe=True)

    assert _issues(resource.cleanup_result) == [
        ("inspect", "suspect"),
        ("return", "handoff-failed"),
    ]
    assert (len(pool.budgets), pool.hand_backs, broken.closes) == (1, 1, 1)


def test_a_control_flow_exception_while_replacing_keeps_its_precedence() -> None:
    # Interrupted while taking the replacement: the interrupt propagates, and
    # the disposal already established is what the exit reports.
    broken = ScriptedConnection(lost=_lost())
    pool = _pool(broken, ScriptedConnection())
    broken.when_lost = lambda: setattr(pool, "checkout_failure", KeyboardInterrupt())
    resource = _context(pool)

    with resource as scoped, pytest.raises(KeyboardInterrupt):
        scoped.submit("select 1", replay_safe=True)

    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]
    assert pool.returned == [broken]


def test_a_disposal_interrupted_part_way_is_never_attempted_again() -> None:
    # A release that does not return established nothing to report, and the
    # slot it emptied leaves the exit nothing to release a second time.
    broken = ScriptedConnection(lost=_lost(), close_failure=KeyboardInterrupt())
    pool = _pool(broken, ScriptedConnection())
    resource = _context(pool)

    with resource as scoped, pytest.raises(KeyboardInterrupt):
        scoped.submit("select 1", replay_safe=True)

    assert resource.cleanup_result is None
    assert (broken.closes, pool.hand_backs, len(pool.budgets)) == (1, 0, 1)


def test_a_replacement_spends_only_what_remains_of_the_original_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    broken = ScriptedConnection(lost=_lost())
    pool = _pool(broken, ScriptedConnection())
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
    original = _lost()
    broken = ScriptedConnection(lost=original)
    pool = _pool(broken, ScriptedConnection())
    resource = _context(pool, deadline=10.0, admit=_admitted)

    with resource as scoped, pytest.raises(SessionLost) as failed:
        clock.now = 11.0
        scoped.submit("select 1", replay_safe=True)

    assert failed.value is original
    assert pool.budgets == [10.0]

    healthy = ScriptedConnection(rows=[(1,)])
    late = _context(_pool(healthy), deadline=12.0, admit=_admitted)
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
    broken, late = ScriptedConnection(lost=_lost()), ScriptedConnection()
    pool = _pool(broken, late)

    def overrun(_budget: float) -> None:
        if len(pool.budgets) == 2:
            clock.now = 11.0

    pool.on_check_out = overrun
    resource: Any
    if work == "proof":
        runtime = _routed(_pool(), pool, reader_readiness="pending", acquire_timeout=10.0)
        resource = _reader_context(runtime)
    elif work == "statement-bound":
        resource = _runtime(_pool(), reservation=pool).reservation_source().new_context(10.0)
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
    pool = _pool(ScriptedConnection(lost=_lost()), ScriptedConnection(rows=[(1,)]))
    runtime = _runtime(pool)

    def close_meanwhile(_budget: float) -> None:
        if len(pool.budgets) == 2:
            runtime.close()

    pool.on_check_out = close_meanwhile

    with _login_context(runtime) as scoped:
        assert scoped.submit("select 1", replay_safe=True) == [(1,)]
    with pytest.raises(ConnectionAcquisitionError) as refused:
        _login_context(runtime).__enter__()

    assert refused.value.reason == "closed"


def test_each_new_owner_has_a_budget_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock(monkeypatch)
    broken = ScriptedConnection(lost=_lost())
    pool = _pool(ScriptedConnection(), broken, ScriptedConnection())
    runtime = _runtime(pool, acquire_timeout=3.0)

    with _login_context(runtime):
        clock.now = 50.0
    with _login_context(runtime) as scoped:
        clock.now = 51.0
        scoped.submit("select 1", replay_safe=True)

    assert pool.budgets == [3.0, 3.0, 2.0]


def test_a_broken_role_installation_is_replaced_and_still_rechecks_admission() -> None:
    broken = ScriptedConnection(lost=_lost())
    fresh = ScriptedConnection()
    pool = _pool(broken, fresh)
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
    broken = ScriptedConnection(lost=_lost())
    fresh = ScriptedConnection()
    calls = 0

    def admit(_deadline: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionAcquisitionError("closed during authorization", reason="closed")

    pool = _pool(broken, fresh)
    resource = _context(pool, admit=admit, authorization="tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "closed"
    assert fresh.submitted[-1] == RESTORE
    assert pool.returned == [broken, fresh]
    assert resource.cleanup_result == Returned()


def test_a_role_installation_that_cannot_be_replaced_is_an_authorization_failure() -> None:
    original = _lost()
    broken = ScriptedConnection(lost=original)
    pool = _pool(broken, ScriptedConnection())
    broken.when_lost = lambda: setattr(pool, "checkout_failure", checkout_failed("timeout"))
    resource = _context(pool, authorization="tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.__cause__ is original
    assert pool.returned == [broken]
    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]


def test_a_replaced_role_installation_that_is_refused_reports_its_own_refusal() -> None:
    refusal = RuntimeError("permission denied to set role")
    broken = ScriptedConnection(lost=_lost())
    refusing = ScriptedConnection(failure=refusal)
    pool = _pool(broken, refusing)
    resource = _context(pool, authorization="tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.__cause__ is refusal
    assert pool.returned == [broken, refusing]
    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]
    assert RESTORE not in refusing.submitted


def _set_up_on(setup: str, pool: _Pool) -> Any:
    """Run the setup named ``setup`` as the first submission of a lease over ``pool``."""
    if setup == "proof":
        resource = _reader_context(_routed(_pool(), pool, reader_readiness="pending"))
        resource.__enter__()
    elif setup == "role":
        _context(pool, authorization="tenant_reader").__enter__()
    elif setup == "statement-bound":
        _runtime(_pool(), reservation=pool).reservation_source().new_context(
            monotonic() + 5.0
        ).__enter__()
    else:
        with _context(pool) as scoped:
            scoped.submit("BEGIN", replay_safe=True, setup=True)


@pytest.mark.parametrize("setup", ["proof", "role", "statement-bound", "outer-begin"])
@pytest.mark.parametrize(
    "refusal",
    ["credentials_refused", "authentication_refused", "preparation_failed", "not-idle"],
)
def test_setup_whose_replacement_was_refused_reports_that_refusal_rather_than_the_loss(
    setup: str, refusal: Any
) -> None:
    cause = RuntimeError("the replacement was refused")
    broken = ScriptedConnection(lost=_lost())
    if refusal == "not-idle":
        pool = _pool(broken, ScriptedConnection(idle=NotIdle("INTRANS")))
    else:
        pool = _pool(broken, ScriptedConnection())
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
    pool = _pool(connection, ScriptedConnection())

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _context(pool, authorization="tenant_reader").__enter__()

    assert refused.value.reason == "authorization_failed"
    assert len(pool.budgets) == 1


def test_an_installed_role_spends_the_opportunity_before_execution() -> None:
    connection = ScriptedConnection()
    pool = _pool(connection, ScriptedConnection())

    with _context(pool, authorization="tenant_reader") as scoped:
        connection.lost = _lost()
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
    pool = _pool(connection, ScriptedConnection())

    with _context(pool) as scoped:
        if ending is None:
            scoped.submit("update a set v = 1")
        else:
            with pytest.raises(type(ending)):
                scoped.submit("update a set v = 1")
        connection.failure = None
        connection.lost = _lost()
        with pytest.raises(SessionLost):
            scoped.submit("select 1", replay_safe=True)

    assert len(pool.budgets) == 1


# --------------------------------------------------------------------------- #
# Release: what a cleanup result is allowed to claim.                          #
# --------------------------------------------------------------------------- #


def _release(connection: ScriptedConnection, pool: _Pool | None = None, **kwargs: Any) -> Any:
    return release(
        ScriptedDriver(), _pool(connection) if pool is None else pool, connection, **kwargs
    )


def test_an_idle_untrusted_free_connection_is_offered_for_reuse() -> None:
    connection = ScriptedConnection()
    pool = _pool(connection)

    result = _release(connection, pool, suspect=False)

    assert result == Returned()
    assert connection.closes == 0
    assert (pool.check_ins, pool.discards) == ([connection], [])


def test_an_execution_that_declared_the_connection_suspect_disposes_of_it_first() -> None:
    # Disposal BEFORE the handoff, and the handoff still happens: disposal alone
    # would leak the capacity, and a handoff alone would offer a connection
    # nothing may reuse.
    connection = ScriptedConnection()
    pool = _pool(connection)
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
    pool = _pool(connection)

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
    pool = _pool(connection, hand_back_failure=RuntimeError("the return failed"))

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
# Admission and shutdown.                                                      #
# --------------------------------------------------------------------------- #


def test_close_is_idempotent_and_permanent() -> None:
    pool = _pool()
    runtime = _runtime(pool)

    runtime.close()
    runtime.close()

    assert pool.closes == 1
    with pytest.raises(ConnectionAcquisitionError) as refused:
        _login_context(runtime).__enter__()
    assert refused.value.reason == "closed"


def test_a_scope_admitted_before_a_close_may_still_finish() -> None:
    # Admission is decided once, immediately before the connection is handed
    # over: later work in an admitted scope uses what it was given, including
    # statements it has not issued yet.
    connection = ScriptedConnection()
    pool = _pool(connection)
    runtime = _runtime(pool)

    with _login_context(runtime) as scoped:
        runtime.close()
        scoped.submit("select 1")

    assert connection.submitted == ["select 1"]
    assert pool.returned == [connection]


def test_a_native_close_problem_is_reported_rather_than_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Close is what a caller runs while unwinding; a handle that refused to
    # close would leave them nothing better to do. So the problem leaves as a
    # report on the restricted resource logger — carrying the phase, the code
    # and fixed text, and nothing the native failure said — rather than as an
    # exception, and a close that reported nothing would be a silently lost
    # runtime.
    runtime = _runtime(_pool(close_failure=RuntimeError("connection to host=secret refused")))

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME):
        runtime.close()

    (record,) = caplog.records
    assert record.name == RESOURCE_LOGGER_NAME
    assert "return/handoff-failed" in record.getMessage()
    assert "secret" not in record.getMessage()
    assert record.exc_info is None


def test_the_ordinary_acquisition_budget_comes_from_the_configured_timeout() -> None:
    pool = _pool()
    runtime = _runtime(pool, acquire_timeout=3.0)
    with _login_context(runtime):
        pass
    (given,) = pool.budgets
    assert given is not None and 0.0 < given <= 3.0


def test_a_runtime_answers_the_dialect_it_was_composed_with() -> None:
    assert _runtime(_pool()).dialect is POSTGRES


def test_login_identity_is_unavailable_before_startup_completion() -> None:
    runtime = _runtime(_pool())

    with pytest.raises(RuntimeError, match="not completed startup"):
        _ = runtime.login_identity


def test_startup_completion_installs_the_login_exactly_once() -> None:
    runtime = _runtime(_pool())

    runtime._complete_startup(  # pyright: ignore[reportPrivateUsage] - direct startup state pin
        "first-login"
    )

    assert runtime.login_identity == "first-login"
    with pytest.raises(RuntimeError, match="already completed startup"):
        runtime._complete_startup(  # pyright: ignore[reportPrivateUsage] - direct startup state pin
            "second-login"
        )


def test_a_probe_that_cannot_run_fails_startup_with_the_failure_as_its_cause() -> None:
    failure = RuntimeError("the statement failed")

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(_pool(ScriptedConnection(failure=failure))))

    assert failed.value.phase == "probe"
    assert str(failed.value) == (
        "database-startup-failed: "
        "the database runtime's startup probe did not return what it asked for"
    )
    assert failed.value.__cause__ is failure


def test_a_control_flow_exception_in_the_probe_keeps_its_own_propagation() -> None:
    # An interpreter being torn down is not a runtime that failed to become
    # ready. Translating one would hand a caller who interrupted the process an
    # ordinary startup error it might catch and carry on from, so the fatal and
    # control-flow exceptions propagate as themselves — after the same release
    # every other probe failure reaches.
    connection = ScriptedConnection(failure=KeyboardInterrupt())
    pool = _pool(connection)

    with pytest.raises(KeyboardInterrupt):
        _open_runtime(_opened(pool))

    assert pool.returned == [connection]
    assert pool.closes == 1


def test_an_exit_whose_revocation_fails_still_gives_the_connection_back() -> None:
    # The exit is the only path back to the pool, so a revocation that does not
    # complete must not strand a connection outside it — and what does come back
    # is disposed of first, because a scope that may still reach it is not one
    # to offer the next caller.
    connection = ScriptedConnection()
    pool = _pool(connection)
    driver = ScriptedDriver()
    driver.revoke_failure = RuntimeError("the scope could not be revoked")
    resource = _login_context(_runtime(pool, driver=driver))

    with pytest.raises(RuntimeError), resource:
        pass

    assert connection.closes == 1
    assert pool.returned == [connection]
    assert isinstance(resource.cleanup_result, Invalidated)


def test_a_budget_already_spent_refuses_to_begin_the_next_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _startup as startup_module

    monkeypatch.setattr(startup_module, "monotonic", lambda: 1e18)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(_pool()))

    assert failed.value.phase == "acquire"


def test_leaving_a_context_that_was_never_entered_does_nothing() -> None:
    # Total on every exit: a context a caller built and abandoned has taken
    # nothing, so leaving it releases nothing and reports nothing.
    pool = _pool()
    resource = _context(pool)
    resource.__exit__(None, None, None)
    assert (pool.returned, resource.cleanup_result) == ([], None)


# --------------------------------------------------------------------------- #
# Routes: a writer and a reader, one admission, readiness proved or deferred.  #
# --------------------------------------------------------------------------- #


def _routed(
    writer_pool: _Pool,
    reader_pool: _Pool,
    *,
    reader_readiness: str = "verified",
    acquire_timeout: float = 15.0,
) -> PostgresRuntime[ScriptedConnection, object]:
    """A started runtime over two scripted pools, its reader verified or pending."""
    reader = PostgresRoute("reader", reader_pool, DialLedger())
    runtime = PostgresRuntime(
        ScriptedDriver(),
        dialect=POSTGRES,
        routes=_ROUTED,
        writer=PostgresRoute("writer", writer_pool, DialLedger()),
        reader=reader,
        reservation=PostgresRoute("writer", _pool(), DialLedger(), "reservation"),
        acquire_timeout=acquire_timeout,
    )
    runtime._complete_startup("runtime-login")  # pyright: ignore[reportPrivateUsage] - the startup transition this harness stands in for
    if reader_readiness == "verified":
        reader.proved_at_startup()
    else:
        reader.defer_verification()
    return runtime


def _reader_route(
    runtime: PostgresRuntime[ScriptedConnection, object],
) -> PostgresRoute[ScriptedConnection]:
    reader = runtime._reader  # pyright: ignore[reportPrivateUsage] - the route whose readiness these proofs read
    assert reader is not None
    return reader


def _reader_context(
    runtime: PostgresRuntime[ScriptedConnection, object], authorization: object = None
) -> Any:
    source = (
        runtime.login_source() if authorization is None else runtime.principal_source(authorization)
    )
    return source.new_context("reader_only")


def _open_routed(
    driver: ScriptedDriver, *, reader_startup: Any = "deferrable"
) -> PostgresRuntime[ScriptedConnection, object]:
    return _open_runtime(driver, _ROUTED, reader_startup=reader_startup)


def _resource_records(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == RESOURCE_LOGGER_NAME]


@pytest.mark.parametrize(
    ("policy", "has_reader", "steps"),
    [
        ("writer_only", False, [("writer", 1.0)]),
        ("writer_only", True, [("writer", 1.0)]),
        ("reader_only", True, [("reader", 1.0)]),
        ("reader_preferred", True, [("reader", 0.5), ("writer", 1.0)]),
    ],
)
def test_each_policy_plans_its_routes_and_their_shares_of_the_budget(
    policy: Any, has_reader: bool, steps: list[tuple[str, float]]
) -> None:
    plan = RoutePlan.for_policy(policy, has_reader=has_reader)
    assert [(step.route, step.share) for step in plan.steps] == steps


@pytest.mark.parametrize(
    ("policy", "has_reader"),
    [("reader_only", False), ("reader_preferred", False)],
)
def test_a_policy_with_no_route_to_serve_it_is_refused_by_the_plan(
    policy: Any, has_reader: bool
) -> None:
    with pytest.raises(ValueError, match="does not serve"):
        RoutePlan.for_policy(policy, has_reader=has_reader)


@pytest.mark.parametrize(
    ("failure", "fallback"),
    [
        ("unavailable", "unavailable"),
        ("connection_lost", "connection_lost"),
        ("timeout", None),
        ("queue_rejected", None),
        ("closed", None),
        ("preparation_failed", None),
        ("authorization_failed", None),
        ("authentication_refused", None),
        ("credentials_refused", None),
    ],
)
def test_only_an_unreachable_route_or_a_lost_setup_connection_falls_back(
    failure: Any, fallback: str | None
) -> None:
    assert RoutePlan.falls_back_on(failure) == fallback


def test_a_routed_runtime_measures_each_pool_in_route_order() -> None:
    runtime = _routed(_pool(), _pool())

    assert dict(runtime.routes) == dict(_ROUTED)
    assert [(source.route, source.purpose) for source in runtime.pool_metrics] == [
        ("writer", "application"),
        ("reader", "application"),
        ("writer", "reservation"),
    ]


def test_a_reader_lease_s_refusal_reports_the_reader() -> None:
    runtime = _routed(_pool(), _pool(checkout_failure=checkout_failed("timeout")))
    resource = _reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert (refused.value.reason, refused.value.selection) == (
        "timeout",
        RouteSelection("reader"),
    )


def test_closing_detaches_both_sources_then_closes_both_pools_whatever_one_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    writer_pool = _pool(close_failure=RuntimeError("the writer would not close"))
    reader_pool = _pool()
    runtime = _routed(writer_pool, reader_pool)
    sources = runtime.pool_metrics

    with caplog.at_level(logging.WARNING, logger=RESOURCE_LOGGER_NAME):
        runtime.close()
        runtime.close()

    assert (writer_pool.closes, reader_pool.closes) == (1, 1)
    assert all(isinstance(source.sample(), PoolDetached) for source in sources)
    assert len(_resource_records(caplog)) == 1
    # One admission decision serves both routes.
    with pytest.raises(ConnectionAcquisitionError) as refused:
        _reader_context(runtime).__enter__()
    assert refused.value.reason == "closed"


def test_an_interrupted_close_still_closes_every_later_pool() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool, reader_pool = _pool(close_failure=interrupt), _pool()
    runtime = _routed(writer_pool, reader_pool)

    with pytest.raises(KeyboardInterrupt) as raised:
        runtime.close()

    assert raised.value is interrupt
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_an_interrupted_abandonment_still_abandons_every_other_opened_pool() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool = _pool()
    reader_pool = _pool(ScriptedConnection(login="other"), close_failure=interrupt)

    with pytest.raises(KeyboardInterrupt) as raised:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert raised.value is interrupt
    assert isinstance(raised.value.__context__, DatabaseStartupError)
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_pool_whose_open_is_interrupted_propagates_the_interrupt_and_closes_the_others() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool = _pool()

    with pytest.raises(KeyboardInterrupt) as raised:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": interrupt}))

    assert raised.value is interrupt
    assert writer_pool.closes == 1


def test_routed_startup_opens_every_pool_before_proving_the_writer_then_the_reader() -> None:
    # Opening every pool first is what lets a retaining reader's workers dial
    # while the writer is being proved, so the two share the one budget's wall
    # time.
    order: list[str] = []

    def writer_probe(_text: str) -> None:
        assert driver.opened == [
            ("writer", "application"),
            ("reader", "application"),
            ("writer", "reservation"),
        ]
        order.append("writer")

    writer_pool = _pool(ScriptedConnection(on_submit=writer_probe))
    reader_pool = _pool(ScriptedConnection(on_submit=lambda _text: order.append("reader")))
    driver = ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool})

    runtime = _open_routed(driver)

    assert order == ["writer", "reader"]
    assert writer_pool.returned[0].submitted == reader_pool.returned[0].submitted == [PROVE]
    assert runtime.login_identity == "runtime-login"
    assert [sample.readiness for sample in _available_samples(runtime)] == [
        "verified",
        "verified",
    ]


def test_a_reader_is_opened_only_where_the_routes_declare_one() -> None:
    driver = ScriptedDriver()

    runtime = _open_runtime(driver)

    assert ("reader", "application") not in driver.opened
    assert dict(runtime.routes) == dict(_WRITER)
    with pytest.raises(ValueError, match="does not serve"):
        runtime.login_source().new_context("reader_only")


def _available_samples(runtime: PostgresRuntime[ScriptedConnection, object]) -> list[Any]:
    samples = [
        source.sample() for source in runtime.pool_metrics if source.purpose == "application"
    ]
    assert all(type(sample).__name__ == "PoolAvailable" for sample in samples), samples
    return samples


def test_routed_startup_proves_the_reader_within_what_remains_of_the_one_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    writer = ScriptedConnection(on_submit=lambda _text: setattr(clock, "now", 12.0))
    reader_pool = _pool()

    _open_routed(ScriptedDriver(pools={"writer": _pool(writer), "reader": reader_pool}))

    assert reader_pool.budgets == [18.0]


def test_a_reader_that_authenticates_another_login_fails_startup_and_closes_both() -> None:
    writer_pool = _pool()
    reader_pool = _pool(ScriptedConnection(login="other"))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("reader", "probe")
    assert isinstance(failed.value.__cause__, ProbeMismatch)
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_writer_that_fails_startup_names_the_writer_and_closes_both() -> None:
    writer_pool = _pool(checkout_failure=checkout_failed("timeout"))
    reader_pool = _pool()

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("writer", "acquire")
    assert reader_pool.budgets == []
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_pool_that_will_not_open_closes_the_writer_pool_already_open() -> None:
    writer_pool = _pool()
    refusal = RuntimeError("no reader pool")

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": refusal}))

    assert (failed.value.route, failed.value.phase) == ("reader", "open")
    assert "reader connection pool could not be opened" in str(failed.value)
    assert failed.value.__cause__ is refusal
    assert writer_pool.budgets == []
    assert writer_pool.closes == 1


def test_a_runtime_that_cannot_be_constructed_closes_both_pools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _startup as startup_module

    writer_pool, reader_pool = _pool(), _pool()

    def refuse(*_args: object, **_kwargs: object) -> Any:
        raise RuntimeError("the runtime could not be built")

    monkeypatch.setattr(startup_module, "PostgresRuntime", refuse)

    with pytest.raises(RuntimeError, match="could not be built"):
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


@pytest.mark.parametrize(
    "unreachable",
    [
        pytest.param(lambda: checkout_failed("timeout"), id="spent-share"),
        pytest.param(
            lambda: checkout_failed("unavailable", _lost("connection refused")), id="refused-dial"
        ),
    ],
)
def test_an_unreachable_reader_is_left_pending_under_deferrable_startup(
    caplog: pytest.LogCaptureFixture,
    unreachable: Callable[[], BaseException],
) -> None:
    reader_pool = _pool(checkout_failure=unreachable())

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME):
        runtime = _open_routed(ScriptedDriver(pools={"writer": _pool(), "reader": reader_pool}))

    assert _reader_route(runtime).readiness() == "pending"
    assert [sample.readiness for sample in _available_samples(runtime)] == [
        "verified",
        "pending",
    ]
    (notice,) = _resource_records(caplog)
    assert notice.startswith("the database runtime's reader route started unverified")
    assert reader_pool.closes == 0
    runtime.close()


def test_an_unreachable_reader_fails_startup_when_it_is_required() -> None:
    writer_pool = _pool()
    reader_pool = _pool(
        checkout_failure=checkout_failed("unavailable", _lost("connection refused"))
    )

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(
            ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}),
            reader_startup="required",
        )

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError) and cause.reason == "unavailable"
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_whose_budget_ran_out_between_phases_is_left_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Running out names no refusal, so it is an outage's symptom. The startup
    # clock reads the deadline, the writer's two phase checks, and then the
    # reader's first, by which time the one budget is gone.
    from parallax.postgres import _startup as startup_module

    Clock(monkeypatch)
    readings = iter([0.0, 0.0, 0.0, 31.0])
    monkeypatch.setattr(startup_module, "monotonic", lambda: next(readings))
    reader_pool = _pool()

    runtime = _open_routed(ScriptedDriver(pools={"writer": _pool(), "reader": reader_pool}))

    assert _reader_route(runtime).readiness() == "pending"
    assert reader_pool.budgets == []


def test_a_reader_whose_budget_ran_out_with_a_refusal_on_record_fails_deferrable_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same spent budget as above, but the reader's own background dials
    # were refused meanwhile, so it is no outage.
    from parallax.postgres import _startup as startup_module

    Clock(monkeypatch)
    readings = iter([0.0, 0.0, 0.0, 31.0])
    monkeypatch.setattr(startup_module, "monotonic", lambda: next(readings))
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    writer_pool, reader_pool = _pool(), _pool()
    driver = ScriptedDriver(
        pools={"writer": writer_pool, "reader": reader_pool},
        recorded={"reader": ("credentials_refused", refusal)},
    )

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(driver)

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    assert failed.value.__cause__ is refusal
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


@pytest.mark.parametrize(
    ("refusal", "reason"),
    [
        pytest.param(
            CredentialResolutionError("RDS IAM token could not be generated"),
            "credentials_refused",
            id="creds",
        ),
        pytest.param(
            RuntimeError("password authentication failed"), "authentication_refused", id="login"
        ),
        pytest.param(RuntimeError("DateStyle is 'German'"), "preparation_failed", id="codec"),
    ],
)
def test_a_reader_refused_rather_than_unreachable_fails_even_deferrable_startup(
    refusal: Exception, reason: Any
) -> None:
    writer_pool = _pool()
    reader_pool = _pool(checkout_failure=checkout_failed("timeout"))
    driver = ScriptedDriver(
        pools={"writer": writer_pool, "reader": reader_pool}, recorded={"reader": (reason, refusal)}
    )

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(driver)

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError)
    assert cause.reason == reason
    assert cause.__cause__ is refusal
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


@pytest.mark.parametrize("reason", ["queue_rejected", "closed", "preparation_failed"])
def test_a_reader_acquisition_that_is_no_outage_fails_even_deferrable_startup(reason: Any) -> None:
    writer_pool = _pool()
    reader_pool = _pool(checkout_failure=checkout_failed(reason))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_probe_lost_with_no_replacement_is_left_pending() -> None:
    # The replacement's checkout times out, so the probe's own driver failure
    # stands — and a session the driver says was lost is an outage.
    reader_pool = _pool(ScriptedConnection(lost=_lost()))
    outcomes = iter([None, checkout_failed("timeout")])

    def fail_the_replacement(_budget: float) -> None:
        reader_pool.checkout_failure = next(outcomes)

    reader_pool.on_check_out = fail_the_replacement

    runtime = _open_routed(ScriptedDriver(pools={"writer": _pool(), "reader": reader_pool}))

    assert _reader_route(runtime).readiness() == "pending"


def test_a_reader_probe_whose_replacement_arrives_past_the_budget_is_left_pending_unproved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The budget ran out with nothing refused on record, which is an outage,
    # and the late replacement is given back without being proved.
    clock = Clock(monkeypatch)
    late = ScriptedConnection()
    reader_pool = _pool(ScriptedConnection(lost=_lost()), late)

    def overrun(_budget: float) -> None:
        if len(reader_pool.budgets) == 2:
            clock.now = 31.0

    reader_pool.on_check_out = overrun

    runtime = _open_routed(ScriptedDriver(pools={"writer": _pool(), "reader": reader_pool}))

    assert _reader_route(runtime).readiness() == "pending"
    assert late.submitted == []
    assert reader_pool.check_ins == [late]
    runtime.close()


def test_a_writer_probe_whose_replacement_arrives_past_the_budget_fails_startup_unproved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    late = ScriptedConnection()
    pool = _pool(ScriptedConnection(lost=_lost()), late)

    def overrun(_budget: float) -> None:
        if len(pool.budgets) == 2:
            clock.now = 31.0

    pool.on_check_out = overrun

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "probe"
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError) and cause.reason == "timeout"
    assert failed.value.cleanup_result == Returned()
    assert late.submitted == []
    assert pool.check_ins == [late]


@pytest.mark.parametrize(
    ("recorded", "checkout_reason"),
    [
        pytest.param("credentials_refused", "credentials_refused", id="creds"),
        pytest.param("authentication_refused", "timeout", id="login-on-record"),
        pytest.param("preparation_failed", "preparation_failed", id="codec"),
    ],
)
@pytest.mark.parametrize("cleared", [False, True], ids=["held", "cleared-before-startup-reads"])
def test_a_reader_probe_whose_replacement_dial_was_refused_fails_even_deferrable_startup(
    monkeypatch: pytest.MonkeyPatch, recorded: Any, checkout_reason: Any, cleared: bool
) -> None:
    # The lost proof stays the primary failure, but its replacement was
    # refused, and a refusal is no outage — even once a later dial clears the
    # record before startup decides.
    original = _lost()
    refusal = RuntimeError("the replacement's dial was refused")
    reader_pool = _pool(ScriptedConnection(lost=original))
    writer_pool = _pool()
    driver = ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool})
    if cleared:
        judged = driver.is_session_lost

        def clear_then_judge(failure: BaseException) -> bool:
            assert reader_pool.dial_record is not None
            reader_pool.dial_record.report_usable()
            return judged(failure)

        monkeypatch.setattr(driver, "is_session_lost", clear_then_judge)

    def refuse_the_replacement(_budget: float) -> None:
        if len(reader_pool.budgets) == 2:
            assert reader_pool.dial_record is not None
            reader_pool.dial_record.report_failure(recorded, refusal)
            reader_pool.checkout_failure = checkout_failed(checkout_reason, refusal)

    reader_pool.on_check_out = refuse_the_replacement

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(driver)

    assert (failed.value.route, failed.value.phase) == ("reader", "probe")
    assert failed.value.__cause__ is original
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_probe_that_fails_for_another_reason_fails_startup_with_the_raw_cause() -> None:
    failure = RuntimeError("the statement failed")
    reader_pool = _pool(ScriptedConnection(failure=failure))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": _pool(), "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("reader", "probe")
    assert failed.value.__cause__ is failure


def test_a_reader_probe_whose_raw_failure_the_driver_calls_a_lost_session_is_left_pending() -> None:
    # Nothing replaced it, because the driver still reports the session open;
    # the outage is judged on the raw failure itself.
    reader_pool = _pool(ScriptedConnection(failure=SessionLost("terminating connection")))

    runtime = _open_routed(ScriptedDriver(pools={"writer": _pool(), "reader": reader_pool}))

    assert _reader_route(runtime).readiness() == "pending"
    assert len(reader_pool.budgets) == 1


def test_a_reader_probe_whose_release_is_unconfirmed_fails_startup() -> None:
    reader_pool = _pool(hand_back_failure=RuntimeError("the return failed"))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": _pool(), "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("reader", "release")


@pytest.mark.parametrize("failure", ["lost-probe", "late-checkout"])
def test_a_reader_outage_whose_cleanup_is_unconfirmed_fails_deferrable_startup(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    # Unreachable and timed out are outages, but what was taken could not be
    # shown to have been given back, which no deferral waits out.
    clock = Clock(monkeypatch)
    handoff = RuntimeError("the return failed")
    if failure == "lost-probe":
        reader_pool = _pool(ScriptedConnection(lost=_lost()), hand_back_failure=handoff)
    else:
        reader_pool = _pool(hand_back_failure=handoff)
        reader_pool.on_check_out = _whatever_budget(lambda: setattr(clock, "now", 31.0))
    writer_pool = _pool()

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert failed.value.route == "reader"
    assert failed.value.phase == ("probe" if failure == "lost-probe" else "acquire")
    assert isinstance(failed.value.cleanup_result, ReleaseUnconfirmed)
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_pending_reader_proves_each_connection_before_its_role_and_then_serves(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reader_pool = _pool(ScriptedConnection(), ScriptedConnection())
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    reader = _reader_route(runtime)

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME):
        with _reader_context(runtime, "tenant_reader") as scoped:
            scoped.submit("select 1")
        with _reader_context(runtime) as scoped:
            scoped.submit("select 2")

    first, second = reader_pool.returned
    assert first.submitted == [PROVE, "authorize tenant_reader", "select 1", RESTORE]
    # Verified now, so a later connection is not proved again.
    assert second.submitted == ["select 2"]
    assert reader.readiness() == "verified"
    notices = _resource_records(caplog)
    assert notices[-1] == "the database runtime's reader route was verified and now serves its work"
    assert sum("verified and now serves" in notice for notice in notices) == 1


def _lose_after_probe(connection: ScriptedConnection) -> Callable[[str], None]:
    def lose(text: str) -> None:
        if text != PROVE:
            connection.lost = _lost()

    return lose


def _losing_after_probe() -> ScriptedConnection:
    connection = ScriptedConnection()
    connection.on_submit = _lose_after_probe(connection)
    return connection


def test_a_pending_reader_s_proof_spends_the_first_send_before_its_role() -> None:
    # The proof was the lease's first submission, so a role installation that
    # then meets a broken session is not a second opportunity.
    reader_pool = _pool(_losing_after_probe(), ScriptedConnection())
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    resource = _reader_context(runtime, "tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert len(reader_pool.budgets) == 1
    assert _reader_route(runtime).readiness() == "verified"


@pytest.mark.parametrize("setup", [True, False], ids=["begin", "modeled-read"])
def test_a_pending_reader_s_proof_spends_the_first_send_before_later_work(setup: bool) -> None:
    reader_pool = _pool(_losing_after_probe(), ScriptedConnection())
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with _reader_context(runtime) as scoped, pytest.raises(SessionLost):
        scoped.submit("BEGIN" if setup else "select 1", replay_safe=True, setup=setup)

    assert len(reader_pool.budgets) == 1


def test_a_broken_proof_is_replaced_once_and_the_replacement_is_proved() -> None:
    broken = ScriptedConnection(lost=_lost())
    fresh = ScriptedConnection()
    reader_pool = _pool(broken, fresh)
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with _reader_context(runtime) as scoped:
        scoped.submit("select 1", replay_safe=True)

    assert broken.submitted == [PROVE]
    assert fresh.submitted == [PROVE, "select 1"]
    assert _reader_route(runtime).readiness() == "verified"


def test_a_proof_lost_beyond_replacement_fails_its_acquisition_as_unavailable() -> None:
    # An outage is not an incompatibility, so the route stays pending for the
    # next acquisition to prove.
    second = _lost("the replacement was lost too")
    reader_pool = _pool(
        ScriptedConnection(lost=_lost()), ScriptedConnection(lost=second), ScriptedConnection()
    )
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    resource = _reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "unavailable"
    assert refused.value.__cause__ is second
    assert refused.value.selection == RouteSelection("reader")
    assert _reader_route(runtime).readiness() == "pending"
    assert isinstance(resource.cleanup_result, Invalidated)
    with _reader_context(runtime):
        pass
    assert _reader_route(runtime).readiness() == "verified"


def test_a_proof_that_fails_for_an_unknown_reason_changes_no_readiness() -> None:
    failure = RuntimeError("the statement failed")
    reader_pool = _pool(ScriptedConnection(failure=failure))
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _reader_context(runtime).__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is failure
    assert _reader_route(runtime).readiness() == "pending"


def test_a_control_flow_exception_in_a_proof_keeps_its_own_propagation() -> None:
    # The connection is still disposed of, and an interrupt is no evidence
    # about the route, so its readiness is untouched.
    connection = ScriptedConnection(failure=KeyboardInterrupt())
    runtime = _routed(_pool(), _pool(connection), reader_readiness="pending")
    resource = _reader_context(runtime)

    with pytest.raises(KeyboardInterrupt):
        resource.__enter__()

    assert connection.closes == 1 and isinstance(resource.cleanup_result, Invalidated)
    assert _reader_route(runtime).readiness() == "pending"


def test_a_proof_that_reads_another_login_refuses_the_route_for_good(
    caplog: pytest.LogCaptureFixture,
) -> None:
    other = ScriptedConnection(login="other")
    reader_pool = _pool(other, ScriptedConnection())
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    resource = _reader_context(runtime)

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME):
        with pytest.raises(ConnectionAcquisitionError) as refused:
            resource.__enter__()
        with pytest.raises(ConnectionAcquisitionError) as later:
            _reader_context(runtime).__enter__()

    assert refused.value.reason == later.value.reason == "preparation_failed"
    mismatch = refused.value.__cause__
    assert isinstance(mismatch, ProbeMismatch) and later.value.__cause__ is mismatch
    # The mismatched connection is disposed of; the later acquisition takes nothing.
    assert other.closes == 1 and isinstance(resource.cleanup_result, Invalidated)
    assert len(reader_pool.budgets) == 1
    assert _reader_route(runtime).readiness() == "refused"
    assert [sample.readiness for sample in _available_samples(runtime)][1] == "refused"
    assert _resource_records(caplog)[-1].startswith(
        "the database runtime's reader route was refused"
    )


def test_a_proof_that_succeeds_after_a_concurrent_refusal_admits_nothing() -> None:
    def refuse_meanwhile(_text: str) -> None:
        _reader_route(runtime).refuse(ProbeMismatch("another lease read another login"))

    runtime = _routed(
        _pool(), _pool(ScriptedConnection(on_submit=refuse_meanwhile)), reader_readiness="pending"
    )
    resource = _reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert str(refused.value.__cause__) == "another lease read another login"
    # The connection itself proved compatible, so it is returned rather than disposed of.
    assert resource.cleanup_result == Returned()
    assert _reader_route(runtime).readiness() == "refused"


def test_a_route_refused_while_a_checkout_waited_admits_nothing_handed_over() -> None:
    connection = ScriptedConnection()
    reader_pool = _pool(connection)
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    mismatch = ProbeMismatch("another lease read another login")
    reader_pool.on_check_out = _whatever_budget(lambda: _reader_route(runtime).refuse(mismatch))
    resource = _reader_context(runtime, "tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is mismatch
    assert connection.submitted == []
    assert resource.cleanup_result == Returned()


def test_a_mismatch_whose_disposal_is_interrupted_still_refuses_the_route() -> None:
    other = ScriptedConnection(login="other", close_failure=KeyboardInterrupt())
    runtime = _routed(_pool(), _pool(other), reader_readiness="pending")

    with pytest.raises(KeyboardInterrupt):
        _reader_context(runtime).__enter__()

    assert _reader_route(runtime).readiness() == "refused"


def test_a_transient_proof_failure_never_downgrades_a_concurrently_verified_route() -> None:
    def verify_meanwhile_then_lose(_text: str) -> None:
        _reader_route(runtime).verified()
        connection.lost = _lost()

    connection = ScriptedConnection(on_submit=verify_meanwhile_then_lose)
    reader_pool = _pool(connection, ScriptedConnection(lost=_lost()))
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with pytest.raises(ConnectionAcquisitionError):
        _reader_context(runtime).__enter__()

    assert _reader_route(runtime).readiness() == "verified"


def test_a_mismatch_on_a_verified_route_fails_only_its_own_acquisition() -> None:
    def verify_meanwhile(_text: str) -> None:
        _reader_route(runtime).verified()

    connection = ScriptedConnection(on_submit=verify_meanwhile, login="other")
    runtime = _routed(_pool(), _pool(connection), reader_readiness="pending")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _reader_context(runtime).__enter__()

    assert refused.value.reason == "preparation_failed"
    assert _reader_route(runtime).readiness() == "verified"


def test_simultaneous_proofs_each_run_and_the_route_is_verified_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Both connections were handed over while the route was pending, so each
    # proves itself; the first success verifies and the second changes nothing.
    nested: list[Any] = []

    def acquire_meanwhile(text: str) -> None:
        if text == PROVE and not nested:
            inner = _reader_context(runtime)
            nested.append(inner)
            with inner:
                pass

    outer = ScriptedConnection(on_submit=acquire_meanwhile)
    inner_connection = ScriptedConnection()
    reader_pool = _pool(outer, inner_connection)
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME), _reader_context(runtime):
        pass

    assert outer.submitted == inner_connection.submitted == [PROVE]
    assert _reader_route(runtime).readiness() == "verified"
    assert sum("verified and now serves" in notice for notice in _resource_records(caplog)) == 1


def test_a_pending_proof_still_spends_the_acquisition_s_own_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    slow = ScriptedConnection(on_submit=lambda _text: setattr(clock, "now", 20.0))
    reader_pool = _pool(slow)
    runtime = _routed(_pool(), reader_pool, reader_readiness="pending")
    resource = _reader_context(runtime)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert resource.cleanup_result == Returned()
    assert _reader_route(runtime).readiness() == "verified"


# --------------------------------------------------------------------------- #
# The dial record: what a spent checkout reports, and what clears it.        #
# --------------------------------------------------------------------------- #


def test_a_spent_checkout_reports_the_latest_dial_failure() -> None:
    ledger = DialLedger()
    earlier = _lost("earlier connection refusal")
    ledger.report_failure("unavailable", earlier)
    pool = _pool(checkout_failure=checkout_failed("timeout"))
    route = PostgresRoute("reader", pool, ledger)

    with pytest.raises(ConnectionAcquisitionError) as before_wait:
        checkout(route, monotonic() + 5.0)

    fresh = CredentialResolutionError("later credential refusal")
    pool.on_check_out = _whatever_budget(
        lambda: ledger.report_failure("credentials_refused", fresh)
    )
    with pytest.raises(ConnectionAcquisitionError) as during_wait:
        checkout(route, monotonic() + 5.0)

    assert before_wait.value.reason == "unavailable"
    assert before_wait.value.__cause__ is earlier
    assert during_wait.value.reason == "credentials_refused"
    assert during_wait.value.__cause__ is fresh


def test_a_handed_over_connection_clears_whatever_failure_was_on_record() -> None:
    ledger = DialLedger()
    ledger.report_failure("credentials_refused", CredentialResolutionError("no token"))

    checkout(PostgresRoute("reader", _pool(), ledger), monotonic() + 5.0)

    assert ledger.latest_failure is None


# --------------------------------------------------------------------------- #
# Preferred fallback: the reader within half the budget, then the writer.     #
# --------------------------------------------------------------------------- #


def _preferred(
    runtime: PostgresRuntime[ScriptedConnection, object], authorization: object = None
) -> Any:
    source = (
        runtime.login_source() if authorization is None else runtime.principal_source(authorization)
    )
    return source.new_context("reader_preferred")


def _refusing(failure: BaseException, *, after: Callable[[], None] = lambda: None) -> _Pool:
    """A pool whose every checkout runs ``after`` and then raises ``failure``."""
    pool = _pool(checkout_failure=failure)
    pool.on_check_out = _whatever_budget(lambda: after())
    return pool


def test_a_healthy_reader_serves_a_preferred_acquisition_within_half_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    Clock(monkeypatch)
    writer_pool, reader_pool = _pool(), _pool()
    resource = _preferred(_routed(writer_pool, reader_pool))

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
    writer_pool = _pool()
    reader_pool = _refusing(
        checkout_failed("unavailable", _lost("connection refused")),
        after=lambda: setattr(clock, "now", 3.0),
    )
    resource = _preferred(_routed(writer_pool, reader_pool))

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
    writer_pool = _pool()
    reader_pool = _pool(checkout_failure=checkout_failed("timeout"))
    runtime = _routed(writer_pool, reader_pool)

    def dial_fails_meanwhile(_budget: float) -> None:
        _reader_route(runtime).dial_ledger.report_failure(
            "unavailable", _lost("connection refused")
        )
        clock.now = 7.5

    reader_pool.on_check_out = dial_fails_meanwhile
    resource = _preferred(runtime)

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
    writer_pool = _pool()
    resource = _preferred(_routed(writer_pool, _pool(checkout_failure=checkout_failed(reason))))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == reason
    assert refused.value.selection == RouteSelection("reader")
    assert writer_pool.budgets == []


def test_a_role_the_reader_denies_is_not_a_reason_to_fall_back() -> None:
    denied = RuntimeError("permission denied to set role")
    writer_pool = _pool()
    resource = _preferred(_routed(writer_pool, _pool(ScriptedConnection(failure=denied))), "tenant")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert refused.value.selection == RouteSelection("reader")
    assert writer_pool.budgets == []


def test_a_reader_success_after_its_share_is_refused_rather_than_used_or_fallen_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    writer_pool = _pool()
    connection = ScriptedConnection()
    reader_pool = _pool(connection)
    reader_pool.on_check_out = _whatever_budget(lambda: setattr(clock, "now", 8.0))
    resource = _preferred(_routed(writer_pool, reader_pool))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert writer_pool.budgets == []
    assert reader_pool.returned == [connection]


def test_a_refused_reader_ends_a_preferred_acquisition_as_a_configuration_failure() -> None:
    writer_pool = _pool()
    runtime = _routed(writer_pool, _pool(), reader_readiness="pending")
    mismatch = ProbeMismatch("another login")
    _reader_route(runtime).refuse(mismatch)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _preferred(runtime).__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is mismatch
    assert writer_pool.budgets == []


def test_a_writer_that_also_fails_after_a_fallback_reports_the_writer_and_the_fallback() -> None:
    resource = _preferred(
        _routed(
            _pool(checkout_failure=checkout_failed("timeout")),
            _pool(checkout_failure=checkout_failed("unavailable", _lost("connection refused"))),
        )
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert refused.value.selection == RouteSelection("writer", "unavailable")
    assert resource.selection == RouteSelection("writer", "unavailable")


# --------------------------------------------------------------------------- #
# The probe slot: one demand re-dial of a reader known to be unreachable.     #
# --------------------------------------------------------------------------- #


def _known_unreachable(
    runtime: PostgresRuntime[ScriptedConnection, object],
) -> PostgresRoute[ScriptedConnection]:
    reader = _reader_route(runtime)
    reader.dial_ledger.report_failure("unavailable", _lost("connection refused"))
    return reader


def test_one_acquisition_holds_the_probe_slot_and_concurrent_ones_fall_back_at_once() -> None:
    # Only the holder waits on the reader; whoever arrives meanwhile goes to
    # the writer without queueing on the route that just failed.
    writer_pool = _pool(ScriptedConnection(), ScriptedConnection())
    reader_pool = _pool(ScriptedConnection())
    runtime = _routed(writer_pool, reader_pool)
    reader = _known_unreachable(runtime)
    concurrent: list[Any] = []

    def recovering(_budget: float) -> None:
        meanwhile = _preferred(runtime)
        with meanwhile:
            concurrent.append(meanwhile.selection)

    reader_pool.on_check_out = recovering
    holder = _preferred(runtime)

    with holder:
        pass
    reader_pool.on_check_out = None

    assert concurrent == [RouteSelection("writer", "unavailable")]
    assert len(reader_pool.budgets) == 1
    assert holder.selection == RouteSelection("reader")
    # The holder's checkout cleared the record, and the slot was given back.
    assert reader.dial_ledger.latest_failure is None
    assert reader.claim_probe()
    reader.release_probe()
    with _preferred(runtime) as scoped:
        scoped.submit("select 1")
    assert len(reader_pool.budgets) == 2


def test_a_reader_with_an_idle_connection_is_tried_whatever_its_record_says() -> None:
    reader_pool = _pool()
    reader_pool.available = 1
    runtime = _routed(_pool(), reader_pool)
    reader = _known_unreachable(runtime)
    assert reader.claim_probe()

    try:
        resource = _preferred(runtime)
        with resource:
            pass
    finally:
        reader.release_probe()

    assert resource.selection == RouteSelection("reader")


def test_a_reader_whose_pool_cannot_be_measured_is_taken_to_hold_no_idle_connection() -> None:
    reader_pool = _pool(metrics_failure=RuntimeError("the pool's bookkeeping could not be read"))
    runtime = _routed(_pool(), reader_pool)
    reader = _known_unreachable(runtime)
    assert reader.claim_probe()

    try:
        resource = _preferred(runtime)
        with resource:
            pass
    finally:
        reader.release_probe()

    assert reader_pool.budgets == []
    assert resource.selection == RouteSelection("writer", "unavailable")


def test_a_probe_holder_falls_back_on_an_outage_recorded_before_its_wait() -> None:
    writer_pool = _pool()
    reader_pool = _pool(checkout_failure=checkout_failed("timeout"))
    runtime = _routed(writer_pool, reader_pool)
    reader = _known_unreachable(runtime)
    resource = _preferred(runtime)

    with resource as scoped:
        scoped.submit("select 1")

    assert len(reader_pool.budgets) == 1
    assert writer_pool.returned[0].submitted == ["select 1"]
    assert resource.selection == RouteSelection("writer", "unavailable")
    assert reader.claim_probe()
    reader.release_probe()


def test_a_strict_reader_always_demands_the_reader_whatever_its_record_says() -> None:
    reader_pool = _pool()
    runtime = _routed(_pool(), reader_pool)
    reader = _known_unreachable(runtime)
    assert reader.claim_probe()

    try:
        with _reader_context(runtime):
            pass
    finally:
        reader.release_probe()

    assert len(reader_pool.budgets) == 1


# --------------------------------------------------------------------------- #
# Setup that loses its connection moves to the writer; modeled reads do not.  #
# --------------------------------------------------------------------------- #


def test_a_reader_lost_installing_the_principal_falls_back_and_installs_it_on_the_writer() -> None:
    reader_connection = ScriptedConnection(lost=_lost())
    writer_connection = ScriptedConnection()
    reader_pool, writer_pool = _pool(reader_connection), _pool(writer_connection)
    resource = _preferred(_routed(writer_pool, reader_pool), "tenant_reader")

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
    writer_connection = ScriptedConnection(lost=_lost())
    writer_pool = _pool(writer_connection, ScriptedConnection())
    resource = _preferred(
        _routed(writer_pool, _pool(ScriptedConnection(lost=_lost()))), "tenant_reader"
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
        lost=_lost(), when_lost=lambda: setattr(clock, "now", 2.0)
    )
    writer_connection = ScriptedConnection()
    reader_pool, writer_pool = _pool(reader_connection), _pool(writer_connection)
    resource = _preferred(_routed(writer_pool, reader_pool))

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
    runtime = _routed(_pool(), _pool(reader_connection), acquire_timeout=10.0)
    resource = _preferred(runtime)

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
    writer_pool = _pool(writer_connection)
    writer_pool.on_check_out = _whatever_budget(lambda: setattr(clock, "now", 20.0))
    resource = _preferred(
        _routed(writer_pool, _pool(ScriptedConnection(lost=_lost())), acquire_timeout=10.0)
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
            reader_connection.lost = _lost()

    reader_connection = ScriptedConnection(on_submit=lose_at_begin)
    writer_pool = _pool()
    resource = _preferred(_routed(writer_pool, _pool(reader_connection)), "tenant")

    with resource as scoped, pytest.raises(SessionLost):
        scoped.submit("BEGIN", replay_safe=True, setup=True)

    assert writer_pool.budgets == []
    assert resource.selection == RouteSelection("reader")


def test_a_pending_reader_s_lost_proof_falls_back_and_leaves_the_reader_pending() -> None:
    writer_connection = ScriptedConnection()
    writer_pool = _pool(writer_connection)
    runtime = _routed(
        writer_pool, _pool(ScriptedConnection(lost=_lost())), reader_readiness="pending"
    )
    resource = _preferred(runtime, "tenant_reader")

    with resource:
        pass

    assert _reader_route(runtime).readiness() == "pending"
    # The writer is verified, so it runs no proof, and the role is installed there.
    assert writer_connection.submitted == ["authorize tenant_reader", RESTORE]
    assert resource.selection == RouteSelection("writer", "connection_lost")


def test_a_modeled_read_s_replacement_stays_on_the_reader_it_began_on() -> None:
    broken, fresh = ScriptedConnection(lost=_lost()), ScriptedConnection()
    reader_pool, writer_pool = _pool(broken, fresh), _pool()
    resource = _preferred(_routed(writer_pool, reader_pool))

    with resource as scoped:
        scoped.submit("select 1", replay_safe=True)

    assert fresh.submitted == ["select 1"]
    assert writer_pool.budgets == []
    assert resource.selection == RouteSelection("reader")


def test_a_reader_disposal_that_cannot_be_confirmed_refuses_the_fallback() -> None:
    reader_connection = ScriptedConnection(lost=_lost(), close_failure=RuntimeError("no close"))
    writer_pool = _pool()
    resource = _preferred(_routed(writer_pool, _pool(reader_connection)), "tenant_reader")

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "authorization_failed"
    assert isinstance(resource.cleanup_result, ReleaseUnconfirmed)
    assert writer_pool.budgets == []


def test_an_interrupt_a_lost_reader_setup_displaced_propagates_and_falls_back_nowhere() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool = _pool()
    resource = _preferred(
        _routed(writer_pool, _pool(ScriptedConnection(lost=_lost_while_draining(interrupt)))),
        "tenant_reader",
    )

    with pytest.raises(KeyboardInterrupt) as raised:
        resource.__enter__()

    assert raised.value is interrupt
    assert writer_pool.budgets == []


def test_a_reader_the_server_refuses_once_its_password_is_sent_fails_deferrable_startup() -> None:
    # An on-demand reader dials on the startup thread, so the refusal its own
    # dial met is the checkout's reason, and a refusal is no outage.
    refused = RuntimeError("password authentication failed")
    writer_pool = _pool()
    reader_pool = _pool(checkout_failure=checkout_failed("authentication_refused", refused))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError)
    assert cause.reason == "authentication_refused"
    assert cause.__cause__ is refused
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


# --------------------------------------------------------------------------- #
# A key reservation's lease: the writer's reservation pool, bounded by one     #
# deadline its setup carries into the session.                                 #
# --------------------------------------------------------------------------- #


def test_a_reservation_lease_bounds_its_statements_by_what_remains_of_its_deadline() -> None:
    connection = ScriptedConnection()
    runtime = _runtime(_pool(), reservation=_pool(connection))
    source = runtime.reservation_source()
    assert source.reservation_timeout == 15.0

    with source.new_context(monotonic() + 5.0) as leased:
        assert leased is not None

    assert connection.submitted == ["limit"]
    (seconds,) = connection.limits
    assert 0.0 < seconds <= 5.0


def test_a_reservation_whose_deadline_passed_takes_no_connection() -> None:
    connection = ScriptedConnection()
    pool = _pool(connection)
    runtime = _runtime(_pool(), reservation=pool)

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
    pool = _pool(slow)
    resource = _runtime(_pool(), reservation=pool).reservation_source().new_context(10.0)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert slow.submitted == ["limit"]
    assert resource.cleanup_result == Returned()
    assert pool.returned == [slow]


def test_a_statement_bound_the_session_refuses_fails_preparation_and_disposes_it() -> None:
    refusal = RuntimeError("cannot set statement_timeout")
    refusing = ScriptedConnection(failure=refusal)
    runtime = _runtime(_pool(), reservation=_pool(refusing))
    resource = runtime.reservation_source().new_context(monotonic() + 5.0)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is refusal
    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]


def test_an_interrupt_bounding_the_statements_propagates_once_disposed() -> None:
    interrupted = ScriptedConnection(failure=KeyboardInterrupt())
    pool = _pool(interrupted)
    runtime = _runtime(_pool(), reservation=pool)
    resource = runtime.reservation_source().new_context(monotonic() + 5.0)

    with pytest.raises(KeyboardInterrupt):
        resource.__enter__()

    assert pool.returned == [interrupted]
    assert _issues(resource.cleanup_result) == [("inspect", "suspect")]


def test_a_reservation_lease_over_a_session_ended_while_idle_bounds_a_replacement() -> None:
    broken = ScriptedConnection(lost=_lost())
    fresh = ScriptedConnection()
    pool = _pool(broken, fresh)
    resource = (
        _runtime(_pool(), reservation=pool).reservation_source().new_context(monotonic() + 5.0)
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
            lost.lost = _lost()

    lost = ScriptedConnection(on_submit=lose_after_setup)
    pool = _pool(lost, ScriptedConnection())
    resource = cast(
        "Any",
        _runtime(_pool(), reservation=pool).reservation_source().new_context(monotonic() + 5.0),
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
    pool = _pool(ScriptedConnection())
    resource = _runtime(_pool(), reservation=pool).reservation_source().new_context(10.0)

    with resource:
        pass

    assert pool.budgets == [pytest.approx(4.0)]
