"""Opening a runtime: every pool, then each route's proof, within one budget.

Only a runtime that has proved it can execute is published. A failure at any
phase publishes nothing, unwinds every pool opened so far, and says which route
and phase failed; a reader that is merely unreachable may instead be left
pending where startup allows it. The pool and driver are scripted at their
seams, and the live proofs are in the provider lane.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from parallax.core.internal.db_port import (
    RESOURCE_LOGGER_NAME,
    ConnectionAcquisitionError,
    CredentialResolutionError,
    DatabaseRuntime,
    DatabaseStartupError,
    PoolAvailable,
    ProbeMismatch,
    ReleaseUnconfirmed,
    Returned,
    Route,
    RouteCapabilities,
    open_runtime,
)
from parallax.core.internal.dialect import POSTGRES
from tests.unit.core.db_port._runtime._composition import (
    ROUTED,
    WRITER_ONLY,
    Pool,
    available_samples,
    issues_of,
    lost_session,
    pool_of,
    resource_records,
    whatever_budget,
)
from tests.unit.core.db_port._runtime._scripted_native import (
    PROVE,
    Clock,
    ScriptedConnection,
    ScriptedDriver,
    SessionLost,
    checkout_failed,
)


def _open_runtime(
    driver: ScriptedDriver,
    routes: Mapping[Route, RouteCapabilities] = WRITER_ONLY,
    *,
    reader_startup: Any = "deferrable",
) -> DatabaseRuntime:
    return open_runtime(
        driver,
        dialect=POSTGRES,
        routes=routes,
        acquire_timeout=15.0,
        startup_timeout=30.0,
        reader_startup=reader_startup,
    )


def _opened(pool: Pool) -> ScriptedDriver:
    """A driver whose writer pool is ``pool``."""
    return ScriptedDriver(pools={"writer": pool})


def _reader_readiness(runtime: DatabaseRuntime) -> str:
    (reader,) = (source for source in runtime.pool_metrics if source.route == "reader")
    sample = reader.sample()
    assert isinstance(sample, PoolAvailable), sample
    return sample.readiness


def _open_routed(driver: ScriptedDriver, *, reader_startup: Any = "deferrable") -> DatabaseRuntime:
    return _open_runtime(driver, ROUTED, reader_startup=reader_startup)


# --------------------------------------------------------------------------- #
# Readiness: only a runtime that has proved it can execute is returned.       #
# --------------------------------------------------------------------------- #


def test_startup_opens_every_pool_then_proves_and_returns_one_connection() -> None:
    connection = ScriptedConnection()
    pool = pool_of(connection)
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
    writer_pool = pool_of()
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
    pool = pool_of(checkout_failure=checkout_failed("timeout"))
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
    pool = pool_of(checkout_failure=checkout_failed("timeout"))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "acquire"
    assert isinstance(failed.value.__cause__, ConnectionAcquisitionError)
    assert pool.closes == 1


def test_a_probe_that_does_not_read_back_what_it_asked_for_fails_startup() -> None:
    mismatch = "the startup probe returned 2 rows rather than one"
    connection = ScriptedConnection(mismatch=mismatch)
    pool = pool_of(connection)

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
    pool = pool_of(hand_back_failure=RuntimeError("the return failed"))

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
    from parallax.core.internal.db_port._runtime import _startup as startup_module

    clock = iter([0.0, 99.0])
    monkeypatch.setattr(startup_module, "monotonic", lambda: next(clock))
    pool = pool_of()

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
    broken = ScriptedConnection(lost=lost_session(), when_lost=lambda: setattr(clock, "now", 10.0))
    fresh = ScriptedConnection()
    pool = pool_of(broken, fresh)

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
    original = lost_session()
    broken = ScriptedConnection(lost=original, when_lost=lambda: setattr(clock, "now", 31.0))
    pool = pool_of(broken, ScriptedConnection())

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "probe"
    assert failed.value.__cause__ is original
    assert pool.budgets == [30.0]
    assert issues_of(failed.value.cleanup_result) == [("inspect", "suspect")]
    assert pool.closes == 1


def test_a_probe_answering_after_the_startup_budget_fails_its_release_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The proof is not admitted again once it answers: the connection it ran
    # on is given back for reuse, and the spent budget is what the next phase
    # check reports.
    clock = Clock(monkeypatch)
    slow = ScriptedConnection(on_submit=lambda _text: setattr(clock, "now", 31.0))
    pool = pool_of(slow)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool))

    assert failed.value.phase == "release"
    assert failed.value.__cause__ is None
    assert failed.value.cleanup_result == Returned()
    assert pool.check_ins == [slow]


# --------------------------------------------------------------------------- #
# Readiness: what a failed phase propagates.                                  #
# --------------------------------------------------------------------------- #


def test_a_probe_that_cannot_run_fails_startup_with_the_failure_as_its_cause() -> None:
    failure = RuntimeError("the statement failed")

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool_of(ScriptedConnection(failure=failure))))

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
    pool = pool_of(connection)

    with pytest.raises(KeyboardInterrupt):
        _open_runtime(_opened(pool))

    assert pool.returned == [connection]
    assert pool.closes == 1


def test_a_budget_already_spent_refuses_to_begin_the_next_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.core.internal.db_port._runtime import _startup as startup_module

    monkeypatch.setattr(startup_module, "monotonic", lambda: 1e18)

    with pytest.raises(DatabaseStartupError) as failed:
        _open_runtime(_opened(pool_of()))

    assert failed.value.phase == "acquire"


# --------------------------------------------------------------------------- #
# Routed startup: every pool opens, then each route proves itself.            #
# --------------------------------------------------------------------------- #


def test_a_failed_startup_abandons_every_opened_pool_the_latest_first() -> None:
    closed: list[str] = []
    pools = {
        "writer": pool_of(checkout_failure=checkout_failed("timeout")),
        "reader": pool_of(),
        "reservation": pool_of(),
    }
    for name, pool in pools.items():
        pool.on_close = lambda name=name: closed.append(name)

    with pytest.raises(DatabaseStartupError):
        _open_routed(ScriptedDriver(pools=pools))

    assert closed == ["reservation", "reader", "writer"]


def test_an_interrupted_abandonment_still_abandons_every_other_opened_pool() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool, reservation_pool = pool_of(), pool_of()
    reader_pool = pool_of(ScriptedConnection(login="other"), close_failure=interrupt)
    driver = ScriptedDriver(
        pools={"writer": writer_pool, "reader": reader_pool, "reservation": reservation_pool}
    )

    with pytest.raises(KeyboardInterrupt) as raised:
        _open_routed(driver)

    assert raised.value is interrupt
    assert isinstance(raised.value.__context__, DatabaseStartupError)
    assert (writer_pool.closes, reader_pool.closes, reservation_pool.closes) == (1, 1, 1)


def test_a_pool_whose_open_is_interrupted_propagates_the_interrupt_and_closes_the_others() -> None:
    interrupt = KeyboardInterrupt()
    writer_pool = pool_of()

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

    writer_pool = pool_of(ScriptedConnection(on_submit=writer_probe))
    reader_pool = pool_of(ScriptedConnection(on_submit=lambda _text: order.append("reader")))
    driver = ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool})

    runtime = _open_routed(driver)

    assert order == ["writer", "reader"]
    assert writer_pool.returned[0].submitted == reader_pool.returned[0].submitted == [PROVE]
    assert runtime.login_identity == "runtime-login"
    assert [sample.readiness for sample in available_samples(runtime)] == [
        "verified",
        "verified",
    ]


def test_a_reader_is_opened_only_where_the_routes_declare_one() -> None:
    driver = ScriptedDriver()

    runtime = _open_runtime(driver)

    assert ("reader", "application") not in driver.opened
    assert dict(runtime.routes) == dict(WRITER_ONLY)
    with pytest.raises(ValueError, match="does not serve"):
        runtime.login_source().new_context("reader_only")


def test_routed_startup_proves_the_reader_within_what_remains_of_the_one_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    writer = ScriptedConnection(on_submit=lambda _text: setattr(clock, "now", 12.0))
    reader_pool = pool_of()

    _open_routed(ScriptedDriver(pools={"writer": pool_of(writer), "reader": reader_pool}))

    assert reader_pool.budgets == [18.0]


def test_a_reader_that_authenticates_another_login_fails_startup_and_closes_both() -> None:
    writer_pool = pool_of()
    reader_pool = pool_of(ScriptedConnection(login="other"))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("reader", "probe")
    assert isinstance(failed.value.__cause__, ProbeMismatch)
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_writer_that_fails_startup_names_the_writer_and_closes_both() -> None:
    writer_pool = pool_of(checkout_failure=checkout_failed("timeout"))
    reader_pool = pool_of()

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("writer", "acquire")
    assert reader_pool.budgets == []
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_pool_that_will_not_open_closes_the_writer_pool_already_open() -> None:
    writer_pool = pool_of()
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
    from parallax.core.internal.db_port._runtime import _startup as startup_module

    writer_pool, reader_pool = pool_of(), pool_of()

    def refuse(*_args: object, **_kwargs: object) -> Any:
        raise RuntimeError("the runtime could not be built")

    monkeypatch.setattr(startup_module, "PooledRuntime", refuse)

    with pytest.raises(RuntimeError, match="could not be built"):
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


@pytest.mark.parametrize(
    "unreachable",
    [
        pytest.param(lambda: checkout_failed("timeout"), id="spent-share"),
        pytest.param(
            lambda: checkout_failed("unavailable", lost_session("connection refused")),
            id="refused-dial",
        ),
    ],
)
def test_an_unreachable_reader_is_left_pending_under_deferrable_startup(
    caplog: pytest.LogCaptureFixture,
    unreachable: Callable[[], BaseException],
) -> None:
    reader_pool = pool_of(checkout_failure=unreachable())

    with caplog.at_level(logging.INFO, logger=RESOURCE_LOGGER_NAME):
        runtime = _open_routed(ScriptedDriver(pools={"writer": pool_of(), "reader": reader_pool}))

    assert [sample.readiness for sample in available_samples(runtime)] == [
        "verified",
        "pending",
    ]
    (notice,) = resource_records(caplog)
    assert notice.startswith("the database runtime's reader route started unverified")
    assert reader_pool.closes == 0
    runtime.close()


def test_an_unreachable_reader_fails_startup_when_it_is_required() -> None:
    writer_pool = pool_of()
    reader_pool = pool_of(
        checkout_failure=checkout_failed("unavailable", lost_session("connection refused"))
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


@pytest.mark.parametrize(
    "recorded",
    [
        pytest.param({}, id="nothing-recorded"),
        pytest.param(
            {"reader": ("unavailable", lost_session("sorry, too many clients already"))},
            id="connection-limit-recorded",
        ),
    ],
)
def test_a_reader_whose_budget_ran_out_between_phases_is_left_pending(
    monkeypatch: pytest.MonkeyPatch,
    recorded: Mapping[Route, tuple[Any, BaseException]],
) -> None:
    # Running out with at most an unavailable dial on record is an outage's
    # symptom. The startup clock reads the deadline, the writer's two phase
    # checks, and then the reader's first, by which time the one budget is gone.
    from parallax.core.internal.db_port._runtime import _startup as startup_module

    Clock(monkeypatch)
    readings = iter([0.0, 0.0, 0.0, 31.0])
    monkeypatch.setattr(startup_module, "monotonic", lambda: next(readings))
    reader_pool = pool_of()

    runtime = _open_routed(
        ScriptedDriver(pools={"writer": pool_of(), "reader": reader_pool}, recorded=recorded)
    )

    assert _reader_readiness(runtime) == "pending"
    assert reader_pool.budgets == []


def test_a_reader_whose_budget_ran_out_with_credentials_refused_fails_deferrable_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same spent budget as above, but the reader's own background dials
    # had their credentials refused meanwhile, so it is no outage.
    from parallax.core.internal.db_port._runtime import _startup as startup_module

    Clock(monkeypatch)
    readings = iter([0.0, 0.0, 0.0, 31.0])
    monkeypatch.setattr(startup_module, "monotonic", lambda: next(readings))
    refusal = CredentialResolutionError("RDS IAM token could not be generated")
    writer_pool, reader_pool = pool_of(), pool_of()
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
    writer_pool = pool_of()
    reader_pool = pool_of(checkout_failure=checkout_failed("timeout"))
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
    writer_pool = pool_of()
    reader_pool = pool_of(checkout_failure=checkout_failed(reason))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_probe_lost_with_no_replacement_is_left_pending() -> None:
    # The replacement's checkout times out, so the probe's own driver failure
    # stands — and a session the driver says was lost is an outage.
    reader_pool = pool_of(ScriptedConnection(lost=lost_session()))
    outcomes = iter([None, checkout_failed("timeout")])

    def fail_the_replacement(_budget: float) -> None:
        reader_pool.checkout_failure = next(outcomes)

    reader_pool.on_check_out = fail_the_replacement

    runtime = _open_routed(ScriptedDriver(pools={"writer": pool_of(), "reader": reader_pool}))

    assert _reader_readiness(runtime) == "pending"


def test_a_reader_probe_whose_replacement_arrives_past_the_budget_is_left_pending_unproved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The budget ran out with nothing refused on record, which is an outage,
    # and the late replacement is given back without being proved.
    clock = Clock(monkeypatch)
    late = ScriptedConnection()
    reader_pool = pool_of(ScriptedConnection(lost=lost_session()), late)

    def overrun(_budget: float) -> None:
        if len(reader_pool.budgets) == 2:
            clock.now = 31.0

    reader_pool.on_check_out = overrun

    runtime = _open_routed(ScriptedDriver(pools={"writer": pool_of(), "reader": reader_pool}))

    assert _reader_readiness(runtime) == "pending"
    assert late.submitted == []
    assert reader_pool.check_ins == [late]
    runtime.close()


def test_a_writer_probe_whose_replacement_arrives_past_the_budget_fails_startup_unproved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock(monkeypatch)
    late = ScriptedConnection()
    pool = pool_of(ScriptedConnection(lost=lost_session()), late)

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
    original = lost_session()
    refusal = RuntimeError("the replacement's dial was refused")
    reader_pool = pool_of(ScriptedConnection(lost=original))
    writer_pool = pool_of()
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
    reader_pool = pool_of(ScriptedConnection(failure=failure))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": pool_of(), "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("reader", "probe")
    assert failed.value.__cause__ is failure


def test_a_reader_probe_whose_raw_failure_the_driver_calls_a_lost_session_is_left_pending() -> None:
    # Nothing replaced it, because the driver still reports the session open;
    # the outage is judged on the raw failure itself.
    reader_pool = pool_of(ScriptedConnection(failure=SessionLost("terminating connection")))

    runtime = _open_routed(ScriptedDriver(pools={"writer": pool_of(), "reader": reader_pool}))

    assert _reader_readiness(runtime) == "pending"
    assert len(reader_pool.budgets) == 1


def test_a_reader_probe_whose_release_is_unconfirmed_fails_startup() -> None:
    reader_pool = pool_of(hand_back_failure=RuntimeError("the return failed"))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": pool_of(), "reader": reader_pool}))

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
        reader_pool = pool_of(ScriptedConnection(lost=lost_session()), hand_back_failure=handoff)
    else:
        reader_pool = pool_of(hand_back_failure=handoff)
        reader_pool.on_check_out = whatever_budget(lambda: setattr(clock, "now", 31.0))
    writer_pool = pool_of()

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert failed.value.route == "reader"
    assert failed.value.phase == ("probe" if failure == "lost-probe" else "acquire")
    assert isinstance(failed.value.cleanup_result, ReleaseUnconfirmed)
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)


def test_a_reader_the_server_refuses_once_its_password_is_sent_fails_deferrable_startup() -> None:
    # An on-demand reader dials on the startup thread, so the refusal its own
    # dial met is the checkout's reason, and a refusal is no outage.
    refused = RuntimeError("password authentication failed")
    writer_pool = pool_of()
    reader_pool = pool_of(checkout_failure=checkout_failed("authentication_refused", refused))

    with pytest.raises(DatabaseStartupError) as failed:
        _open_routed(ScriptedDriver(pools={"writer": writer_pool, "reader": reader_pool}))

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError)
    assert cause.reason == "authentication_refused"
    assert cause.__cause__ is refused
    assert (writer_pool.closes, reader_pool.closes) == (1, 1)
