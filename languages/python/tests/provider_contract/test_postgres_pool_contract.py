"""The owned Postgres runtime against a real server (`database-provider-test-contract`).

What a fake pool cannot establish is here: that a connection really is reused,
that capacity really is bounded, that a queue really refuses, that a runtime that
closed really admits nothing more, and that every connection a pool creates —
initial, grown, replacement, or on-demand — really decodes what the read path
depends on. The deterministic failure paths a server will not produce on demand
are ``tests/unit/test_postgres_pool.py``'s.

Every configuration here names the database this run opened, and every runtime
it opens is closed by the scope that opened it.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import pytest

from parallax.core.base import INFINITY
from parallax.core.db_port import (
    DRIVER_MANAGED,
    ConnectionAcquisitionError,
    CredentialResolutionError,
    DatabaseStartupError,
    PoolAvailable,
    PoolDetached,
    PoolUnavailable,
)
from parallax.postgres import OnDemandOptions, PoolOptions

_BACKEND = "select pg_backend_pid() as pid"
_SESSION_USER = "select session_user as login_identity"


def _pid(connection: Any) -> int:
    (row,) = connection.execute(_BACKEND, [])
    return int(row[0])


def _runtime(profile_run: Any, **options: Any) -> Any:
    return profile_run.configured(**options).open()


def _context(runtime: Any) -> Any:
    return runtime.login_execution().new_context()


# --------------------------------------------------------------------------- #
# Reuse, capacity, and the queue.                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.adapter_smoke
def test_runtime_login_identity_is_the_server_authenticated_session_user(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0))
    try:
        with _context(runtime) as connection:
            (row,) = connection.execute(_SESSION_USER, [])
        assert runtime.login_identity == row[0]
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_retaining_runtime_reuses_the_connection_it_kept(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=1))
    try:
        with _context(runtime) as first:
            first_pid = _pid(first)
        with _context(runtime) as second:
            assert _pid(second) == first_pid
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_capacity_bounds_how_many_scopes_are_open_at_once(profile_run: Any) -> None:
    # Two scopes at a capacity of two are two DIFFERENT sessions; the third
    # waits for one of them rather than opening a connection past the ceiling.
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0, max_size=2, acquire_timeout=1.0))
    try:
        with _context(runtime) as first, _context(runtime) as second:
            assert _pid(first) != _pid(second)
            with pytest.raises(ConnectionAcquisitionError) as refused:
                _context(runtime).__enter__()
        assert refused.value.reason == "timeout"
        # The ceiling is not a leak: capacity is available again afterwards.
        with _context(runtime) as third:
            assert _pid(third)
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_bounded_queue_refuses_a_further_waiter_rather_than_holding_it(
    profile_run: Any,
) -> None:
    runtime = _runtime(
        profile_run,
        pool=PoolOptions(min_size=0, max_size=1, max_waiting=1, acquire_timeout=2.0),
    )
    refusals: list[str] = []

    def wait_for_capacity() -> None:
        try:
            with _context(runtime):
                pass
        except ConnectionAcquisitionError as refused:  # pragma: no cover - timing
            refusals.append(refused.reason)

    try:
        with _context(runtime):
            queued = threading.Thread(target=wait_for_capacity)
            queued.start()
            # The waiter is really queued before the next acquisition asks —
            # read off the pool rather than inferred from a thread having
            # started — so what that acquisition meets is a full queue, and it
            # is refused outright rather than waiting for a slot already spoken
            # for.
            _wait_until_queued(runtime)
            with pytest.raises(ConnectionAcquisitionError) as rejected:
                _context(runtime).__enter__()
            assert rejected.value.reason == "queue_rejected"
        queued.join(timeout=10.0)
        assert refusals == []
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_closed_runtime_admits_nothing_further(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0))
    runtime.close()

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _context(runtime).__enter__()

    assert refused.value.reason == "closed"


@pytest.mark.adapter_smoke
def test_two_runtimes_from_one_configuration_are_independent(profile_run: Any) -> None:
    configured = profile_run.configured(pool=PoolOptions(min_size=1, max_size=1))
    first = configured.open()
    second = configured.open()
    try:
        with _context(first) as one, _context(second) as two:
            assert _pid(one) != _pid(two)
        first.close()
        # Closing one leaves the other working.
        with _context(second) as still_working:
            assert _pid(still_working)
    finally:
        first.close()
        second.close()


# --------------------------------------------------------------------------- #
# On-demand retention.                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.adapter_smoke
def test_an_on_demand_runtime_keeps_no_idle_connection(profile_run: Any) -> None:
    # Releasing closes the connection unless a caller is already waiting, so a
    # later acquisition establishes another — which is bounded concurrency
    # without inventory rather than a promise of a brand-new session each time.
    runtime = _runtime(profile_run, pool=OnDemandOptions(max_size=2))
    try:
        with _context(runtime) as first:
            first_pid = _pid(first)
        with _context(runtime) as second:
            assert _pid(second) != first_pid
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_an_on_demand_runtime_still_bounds_concurrency(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=OnDemandOptions(max_size=1, acquire_timeout=1.0))
    try:
        with _context(runtime), pytest.raises(ConnectionAcquisitionError) as refused:
            _context(runtime).__enter__()
        assert refused.value.reason == "timeout"
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_on_demand_establishment_takes_its_limit_from_the_acquisition_budget(
    profile_run: Any,
) -> None:
    # The driver derives its own `connect_timeout` from what remains of the
    # checkout budget, overriding one the connection string carries for that
    # creation. A connection string asking for a two-second establishment limit
    # therefore does not get one — the acquisition budget is the control that
    # matters here, and the two do not compose as independent limits. What the
    # override IS, exactly, is pinned against the installed pool release in
    # `tests/unit/test_postgres_pool.py`; here it is proven not to prevent an
    # establishment against a real server.
    from psycopg.conninfo import conninfo_to_dict

    configured = profile_run.configured(pool=OnDemandOptions(max_size=1, acquire_timeout=5.0))
    assert "connect_timeout" not in conninfo_to_dict(configured.connection_string)
    runtime = configured.open()
    try:
        with _context(runtime) as scoped:
            assert _pid(scoped)
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_an_on_demand_release_goes_straight_to_a_borrower_already_waiting(
    profile_run: Any,
) -> None:
    # Keeping no inventory is not the same as closing every connection: a
    # release with a caller already queued hands the connection straight on.
    # What makes it deterministic is the ordering: capacity is released only
    # once the borrower is queued, so the connection it gets can only be the one
    # released rather than one established for it afterwards.
    runtime = _runtime(profile_run, pool=OnDemandOptions(max_size=1, acquire_timeout=10.0))
    handed: list[int] = []

    def wait_for_the_handoff() -> None:
        with _context(runtime) as scoped:
            handed.append(_pid(scoped))

    try:
        waiter = threading.Thread(target=wait_for_the_handoff)
        with _context(runtime) as held:
            held_pid = _pid(held)
            waiter.start()
            _wait_until_queued(runtime)
        waiter.join(timeout=15.0)
        assert handed == [held_pid]
    finally:
        runtime.close()


def _wait_until_queued(runtime: Any) -> None:
    """Block until a borrower is queued on ``runtime``, or fail the test.

    Read from the pool's own bookkeeping rather than probed by taking a further
    acquisition. A probe is itself a caller: it can reach the queue before the
    borrower it is watching for and take the slot that borrower was about to
    take, which then rejects the borrower or parks the probe for a whole
    acquisition budget — so the proof would turn on which of two threads the
    pool admitted first. Reading takes no connection, occupies no slot, and
    changes nothing.

    It reads through the runtime's own ``pool_metrics`` source, which is the
    neutral publication of exactly this: queue depth, taken without a
    connection and without a statement.
    """
    source = runtime.pool_metrics
    assert source is not None
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        sample = source.sample()
        if isinstance(sample, PoolAvailable) and sample.measurements.requests_waiting > 0:
            return
        time.sleep(0.01)
    raise AssertionError("no borrower ever queued")


# --------------------------------------------------------------------------- #
# Every physical connection decodes what the read path depends on.             #
# --------------------------------------------------------------------------- #


_CODEC_PROBE = """SELECT
    'infinity'::timestamptz AS unbounded,
    '{"present": null}'::jsonb AS document,
    null::jsonb AS absent,
    'null'::jsonb AS stored_null,
    42::int AS number"""


@pytest.mark.adapter_smoke
def test_every_connection_a_runtime_creates_decodes_the_same_way(profile_run: Any) -> None:
    # Initial capacity, growth, and the connections an on-demand runtime creates
    # per acquisition: a codec installed on some connections and not others is a
    # decoding bug that appears under load and nowhere else.
    for options in (
        PoolOptions(min_size=1, max_size=3),
        PoolOptions(min_size=0, max_size=3),
        OnDemandOptions(max_size=3),
    ):
        runtime = _runtime(profile_run, pool=options)
        try:
            for _ in range(3):
                with _context(runtime) as scoped:
                    (row,) = scoped.execute(_CODEC_PROBE, [])
                assert row == (INFINITY, {"present": None}, None, None, 42)
        finally:
            runtime.close()


@pytest.mark.adapter_smoke
def test_a_grown_connection_decodes_exactly_as_the_first_one_does(profile_run: Any) -> None:
    # Growth, proven by HOLDING the scopes rather than taking them in turn: a
    # retaining runtime reuses one connection for sequential acquisitions, so
    # only overlapping ones make it create the second and third — and a codec
    # installed on the first connection and not on those is a decoding bug that
    # appears under load and nowhere else.
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=3))
    try:
        with (
            _context(runtime) as first,
            _context(runtime) as second,
            _context(runtime) as third,
        ):
            grown = [first, second, third]
            assert len({_pid(scoped) for scoped in grown}) == 3
            for scoped in grown:
                (row,) = scoped.execute(_CODEC_PROBE, [])
                assert row == (INFINITY, {"present": None}, None, None, 42)
    finally:
        runtime.close()


# --------------------------------------------------------------------------- #
# The credential: one resolution per physical connection, and none on reuse.   #
# --------------------------------------------------------------------------- #


class _Counting:
    """The run's own credential source, counting how often it is asked.

    It crosses the seam exactly as a provider's does — through
    ``credentials=`` on the shipped adapter — so what is counted is the
    adapter's real consumption rather than a stand-in for it.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls = 0

    def resolve(self) -> Any:
        self.calls += 1
        return self._inner.resolve()


def _counted(profile_run: Any, **options: Any) -> tuple[Any, _Counting]:
    source = _Counting(profile_run.credentials)
    return profile_run.configured(credentials=source, **options).open(), source


@pytest.mark.adapter_smoke
def test_the_retained_minimum_is_authenticated_once_and_reuse_asks_for_nothing(
    profile_run: Any,
) -> None:
    # Initial capacity is one physical connection, and the startup probe and
    # every sequential acquisition after it ride that same connection. A source
    # asked again there would be asked on a path that establishes nothing.
    runtime, source = _counted(profile_run, pool=PoolOptions(min_size=1, max_size=1))
    try:
        assert source.calls == 1
        with _context(runtime) as first:
            original = _pid(first)
        with _context(runtime) as second:
            assert _pid(second) == original
        assert source.calls == 1
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_growth_authenticates_each_connection_it_creates(profile_run: Any) -> None:
    # Overlapping scopes are what make a retaining runtime create the second and
    # third connections, and each is established in its own right.
    runtime, source = _counted(profile_run, pool=PoolOptions(min_size=1, max_size=3))
    try:
        with (
            _context(runtime) as first,
            _context(runtime) as second,
            _context(runtime) as third,
        ):
            assert len({_pid(scoped) for scoped in (first, second, third)}) == 3
        assert source.calls == 3
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_on_demand_establishment_authenticates_on_the_acquiring_thread_each_time(
    profile_run: Any,
) -> None:
    # An on-demand runtime keeps no inventory, so every acquisition is a
    # physical connection and every one is a resolution — on the caller's own
    # thread, ahead of the driver's connect timeout.
    runtime, source = _counted(profile_run, pool=OnDemandOptions(max_size=1))
    try:
        established = source.calls
        with _context(runtime) as first:
            first_pid = _pid(first)
        with _context(runtime) as second:
            assert _pid(second) != first_pid
        assert source.calls == established + 2
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_connection_retired_by_its_maximum_lifetime_is_authenticated_anew(
    profile_run: Any,
) -> None:
    # Age is judged when a connection comes back rather than when it is handed
    # out, so the aged connection serves one more scope and the replacement the
    # runtime creates for it is a fresh establishment with a fresh credential.
    runtime, source = _counted(
        profile_run, pool=PoolOptions(min_size=1, max_size=1, max_lifetime=1.0)
    )
    try:
        with _context(runtime) as first:
            original = _pid(first)
        time.sleep(1.5)
        with _context(runtime) as aged:
            assert _pid(aged) == original
        with _context(runtime) as replacement:
            assert _pid(replacement) != original
        assert source.calls == 2
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_connection_the_server_ended_is_authenticated_again_when_it_is_replaced(
    profile_run: Any,
) -> None:
    # The replacement is a physical connection the runtime created on its own,
    # so it crosses the credential seam exactly as the first one did.
    runtime, source = _counted(profile_run, pool=PoolOptions(min_size=1, max_size=1))
    executioner = profile_run.control()
    try:
        with _context(runtime) as first:
            retained = _pid(first)
        executioner.execute("select pg_terminate_backend(%s) as ended", [retained])

        with _context(runtime) as replacement:
            assert _pid(replacement) != retained
        assert source.calls == 2
    finally:
        executioner.close()
        runtime.close()


@pytest.mark.adapter_smoke
def test_the_driver_managed_declaration_asks_nothing_and_lets_libpq_authenticate(
    profile_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Declaring it means Parallax supplies no secret at all: the connection
    # string carries none, nothing is resolved, and libpq finds the password in
    # its own environment — the documented driver-managed case, against a real
    # server.
    from psycopg.conninfo import conninfo_to_dict

    monkeypatch.setenv("PGPASSWORD", profile_run.credentials.secret)
    configured = profile_run.configured(
        credentials=DRIVER_MANAGED, pool=OnDemandOptions(max_size=1)
    )
    assert "password" not in conninfo_to_dict(configured.connection_string)

    runtime = configured.open()
    try:
        with _context(runtime) as scoped:
            (row,) = scoped.execute(_SESSION_USER, [])
        assert row[0] == profile_run.login_identity
    finally:
        runtime.close()


# --------------------------------------------------------------------------- #
# The credential refused: named as the cause rather than reported as a wait.   #
# --------------------------------------------------------------------------- #

_SIGNING_SECRET = "hunter2-would-have-signed-this"
"""What a careless source puts in its own message, and what must not be logged."""


class _RefusingAfter:
    """The run's own source, refusing once it has produced ``successes`` of them.

    Zero refuses from the very first physical connection; a positive count lets
    retained capacity fill and refuses everything the runtime opens after that,
    which is how an operation-time refusal is reached without a startup that
    never completed.
    """

    def __init__(self, inner: Any, *, successes: int = 0, error: BaseException | None = None):
        self._inner = inner
        self._successes = successes
        self.error = (
            error
            if error is not None
            else CredentialResolutionError("RDS IAM token could not be generated")
        )
        self.calls = 0

    def resolve(self) -> Any:
        self.calls += 1
        if self.calls > self._successes:
            raise self.error
        return self._inner.resolve()


@pytest.mark.adapter_smoke
def test_a_retained_runtime_whose_source_refuses_fails_startup_naming_the_refusal(
    profile_run: Any, caplog: pytest.LogCaptureFixture
) -> None:
    # Filling happens on the pool's own worker threads, where a refusal is
    # retried with backoff and logged where nothing reaches the caller waiting
    # on it — so readiness spends its whole budget and then names the refusal
    # rather than the wait. What the source itself raised is wrapped in fixed
    # text, which is what keeps its message out of the driver's own log line.
    source = _RefusingAfter(
        profile_run.credentials, error=RuntimeError(f"could not sign for {_SIGNING_SECRET}")
    )
    configured = profile_run.configured(
        credentials=source, pool=PoolOptions(min_size=1, max_size=1, startup_timeout=2.0)
    )

    with (
        caplog.at_level(logging.WARNING, logger="psycopg.pool"),
        pytest.raises(DatabaseStartupError) as failed,
    ):
        configured.open()

    assert failed.value.phase == "minimum_ready"
    assert "authenticated" in str(failed.value)
    refusal = failed.value.__cause__
    assert isinstance(refusal, CredentialResolutionError)
    assert str(refusal) == "the credential source could not produce a password"
    assert refusal.__cause__ is source.error
    attempts = [record for record in caplog.records if record.name == "psycopg.pool"]
    assert attempts
    assert all(str(refusal) in record.getMessage() for record in attempts)
    assert all(_SIGNING_SECRET not in record.getMessage() for record in attempts)


@pytest.mark.adapter_smoke
def test_a_retained_runtime_that_cannot_replace_a_connection_reports_the_refusal(
    profile_run: Any,
) -> None:
    # The source authenticates initial capacity and refuses afterwards, so the
    # runtime is healthy until the server ends its one connection. The
    # replacement it then tries to open is what meets the refusal, and the
    # acquisition waiting on it says so instead of timing out.
    source = _RefusingAfter(profile_run.credentials, successes=1)
    runtime = profile_run.configured(
        credentials=source,
        pool=PoolOptions(min_size=1, max_size=1, acquire_timeout=2.0),
    ).open()
    executioner = profile_run.control()
    try:
        with _context(runtime) as first:
            retained = _pid(first)
        executioner.execute("select pg_terminate_backend(%s) as ended", [retained])

        with pytest.raises(ConnectionAcquisitionError) as refused:
            _context(runtime).__enter__()

        assert refused.value.reason == "credentials_refused"
        assert refused.value.__cause__ is source.error
    finally:
        executioner.close()
        runtime.close()


@pytest.mark.adapter_smoke
def test_an_on_demand_runtime_meets_the_refusal_on_its_own_thread_and_does_not_wait(
    profile_run: Any,
) -> None:
    # An on-demand runtime establishes on the acquiring thread, so the refusal
    # comes back as itself rather than as a record read after a wait. Startup's
    # own acquisition is the first one to meet it, and it is asked exactly once.
    source = _RefusingAfter(profile_run.credentials)
    configured = profile_run.configured(credentials=source, pool=OnDemandOptions(max_size=1))

    with pytest.raises(DatabaseStartupError) as failed:
        configured.open()

    assert failed.value.phase == "acquire"
    acquisition = failed.value.__cause__
    assert isinstance(acquisition, ConnectionAcquisitionError)
    assert acquisition.reason == "credentials_refused"
    assert acquisition.__cause__ is source.error
    assert source.calls == 1


@pytest.mark.adapter_smoke
def test_a_connection_the_server_ended_is_replaced_at_checkout(profile_run: Any) -> None:
    # The checkout health check spends a round trip proving a connection still
    # works, which is what turns one the server closed while it was idle into a
    # REPLACEMENT rather than a failed statement. The replacement is a physical
    # connection the runtime created on its own, so it also has to decode.
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=1))
    executioner = profile_run.control()
    try:
        with _context(runtime) as first:
            retained = _pid(first)
        executioner.execute("select pg_terminate_backend(%s) as ended", [retained])

        with _context(runtime) as replacement:
            assert _pid(replacement) != retained
            (row,) = replacement.execute(_CODEC_PROBE, [])
        assert row == (INFINITY, {"present": None}, None, None, 42)
    finally:
        executioner.close()
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_finite_timestamp_still_decodes_beside_the_unbounded_one(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0, max_size=1))
    try:
        with _context(runtime) as scoped:
            (row,) = scoped.execute(
                "select '2026-01-02 03:04:05+00'::timestamptz as at, "
                "'infinity'::timestamptz as forever",
                [],
            )
        assert row[1] is INFINITY
        assert row[0].year == 2026
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_checkout_validation_can_be_opted_out_of_without_changing_what_executes(
    profile_run: Any,
) -> None:
    # The health check spends a round trip proving a connection still works.
    # Turning it off changes what the runtime does before handing a connection
    # over and nothing about what the caller may then run on it.
    runtime = _runtime(
        profile_run, pool=PoolOptions(min_size=1, max_size=1, validate_on_checkout=False)
    )
    try:
        with _context(runtime) as scoped:
            assert scoped.execute("select 1 as n", []) == [(1,)]
    finally:
        runtime.close()


# --------------------------------------------------------------------------- #
# Transactions across scopes.                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.adapter_smoke
def test_two_scopes_hold_isolated_transactions(profile_run: Any) -> None:
    profile_run.reset(*_grade_model())
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0, max_size=2))
    try:
        with _context(runtime) as writer, _context(runtime) as reader:

            def insert(conn: Any) -> None:
                conn.execute_write(
                    'insert into grade (id, "order", label) values (%s, %s, %s)',
                    [99, 99, "z"],
                )
                # The other scope's transaction cannot see uncommitted work.
                assert reader.execute("select id from grade where id = 99", []) == []

            writer.transaction(insert)
            assert reader.execute("select id from grade where id = 99", []) == [(99,)]
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_scope_leaves_no_transaction_open_behind_it(profile_run: Any) -> None:
    # Autocommit and physical-close semantics: a standalone statement opens no
    # implicit whole-operation transaction, so the connection comes back idle
    # and the next scope over it starts clean.
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=1))
    try:
        with _context(runtime) as first:
            first.execute("select 1", [])
        with _context(runtime) as second:
            (row,) = second.execute("select txid_current_if_assigned() as tx", [])
        assert row[0] is None
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_indirect_connection_inputs_resolve_at_each_physical_connection(
    profile_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `m-db-port`: what a connection string REFERS to — environment, service
    # files, credentials, server defaults — resolves when each physical
    # connection is created, not when the configuration is constructed. One
    # configuration, two acquisitions, two different resolutions of the same
    # environment variable is the proof; on-demand retention is what makes each
    # acquisition a fresh physical connection.
    configured = profile_run.configured(pool=OnDemandOptions(max_size=1))

    def resolved_application_name(runtime: Any) -> str:
        with _context(runtime) as scoped:
            (row,) = scoped.execute("select current_setting('application_name') as name", [])
        return str(row[0])

    monkeypatch.setenv("PGAPPNAME", "parallax-before")
    runtime = configured.open()
    try:
        assert resolved_application_name(runtime) == "parallax-before"
        monkeypatch.setenv("PGAPPNAME", "parallax-after")
        assert resolved_application_name(runtime) == "parallax-after"
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_settings_a_deployment_configured_survive_initialization(profile_run: Any) -> None:
    # Initialization installs the loaders the read path depends on and checks
    # the two settings those loaders cannot work without. It configures nothing
    # else, so every other setting a deployment asked its connections for is
    # what its statements run under.
    runtime = _runtime(
        profile_run,
        pool=OnDemandOptions(max_size=1),
        settings={
            "timezone": "UTC",
            "default_transaction_read_only": "on",
            "search_path": "public",
            "statement_timeout": "7s",
        },
    )
    try:
        with _context(runtime) as scoped:
            (row,) = scoped.execute(
                "select current_setting('timezone') as timezone, "
                "current_setting('default_transaction_read_only') as read_only, "
                "current_setting('search_path') as search_path, "
                "current_setting('statement_timeout') as statement_timeout, "
                "current_setting('client_encoding') as encoding, "
                "current_setting('datestyle') as datestyle",
                [],
            )
    finally:
        runtime.close()
    assert row[:4] == ("UTC", "on", "public", "7s")
    # And the two it does own are the ones it checked for.
    assert row[4] == "UTF8"
    assert row[5].startswith("ISO")


@pytest.mark.adapter_smoke
def test_a_session_default_arrives_with_the_connection_rather_than_after_it(
    profile_run: Any,
) -> None:
    # `m-db-port` puts the isolation check at INTAKE, so the default has to be
    # there before initialization rather than set on a borrowed session. It
    # travels as a connection-establishment option, which is why every
    # connection this configuration opens carries it.
    runtime = profile_run.adapter_for_session_default("read-uncommitted").open()
    try:
        with _context(runtime) as scoped:
            (row,) = scoped.execute("show default_transaction_isolation", [])
        # Postgres HAS no level below Read Committed and runs a Read Uncommitted
        # request as Read Committed, so the floor is met and the connection is
        # kept — which is exactly what the corpus case grades.
        assert row[0] == "read uncommitted"
    finally:
        runtime.close()


def _grade_model() -> tuple[Any, Any]:
    from parallax.conformance import engine, provision
    from parallax.conformance.case_format import default_cases_dir, load_case

    case = load_case(default_cases_dir() / "m-descriptor-001-quoted-reserved-identifier.yaml")
    return engine.load_case_metamodel(case), provision.load_fixtures(str(case.document["model"]))


# --------------------------------------------------------------------------- #
# What the pool says about itself, against a real pool.                        #
# --------------------------------------------------------------------------- #


def _measurements(runtime: Any) -> Any:
    source = runtime.pool_metrics
    assert source is not None
    sample = source.sample()
    assert isinstance(sample, PoolAvailable), sample
    return sample.measurements


@pytest.mark.adapter_smoke
def test_a_ready_runtime_reports_the_capacity_it_was_configured_with(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=2, max_size=4))
    try:
        measurements = _measurements(runtime)
    finally:
        runtime.close()

    assert measurements.pool_min == 2
    assert measurements.pool_max == 4
    # Readiness waited for the minimum and gave its probe connection back, so
    # there is real managed capacity and it is idle.
    assert measurements.pool_size >= 2
    assert measurements.pool_available >= 1
    assert measurements.requests_waiting == 0
    # Startup itself is a caller, so the checkout counter is not zero on a
    # runtime no application has used yet.
    assert measurements.connections_num >= 2


@pytest.mark.adapter_smoke
def test_sampling_takes_no_connection_and_runs_no_statement(profile_run: Any) -> None:
    # Two proofs in one arrangement. A runtime with exactly one slot, with that
    # slot HELD, still answers — so the reading took no connection, since there
    # was none to take. And the checkout counter is unchanged across the
    # reading — so the reading was not itself a caller.
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=1, acquire_timeout=1.0))
    try:
        with _context(runtime) as held:
            assert _pid(held)
            before = _measurements(runtime)
            after = _measurements(runtime)
            assert before.pool_available == 0
            assert after.requests_num == before.requests_num
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_the_counters_follow_the_work_the_runtime_actually_did(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=2))
    try:
        before = _measurements(runtime)
        for _ in range(3):
            with _context(runtime) as scoped:
                assert _pid(scoped)
        after = _measurements(runtime)
    finally:
        runtime.close()

    assert after.requests_num == before.requests_num + 3
    # A counter is what the pool counted, not a Parallax gauge derived from it:
    # nothing here claims how many of those checkouts were concurrent.
    assert after.requests_errors == before.requests_errors


@pytest.mark.adapter_smoke
def test_an_on_demand_runtime_keeps_no_idle_inventory_to_report(profile_run: Any) -> None:
    # Zero available is the honest reading for a pool that retains nothing, even
    # while it is serving perfectly well — which is exactly the native fact an
    # exporter must not read as "exhausted".
    runtime = _runtime(profile_run, pool=OnDemandOptions(max_size=2))
    try:
        with _context(runtime) as scoped:
            assert _pid(scoped)
        measurements = _measurements(runtime)
    finally:
        runtime.close()

    assert measurements.pool_min == 0
    assert measurements.pool_max == 2
    assert measurements.pool_available == 0


@pytest.mark.adapter_smoke
def test_a_closed_runtime_answers_detached_through_the_same_source(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=1))
    source = runtime.pool_metrics
    assert source is not None
    assert isinstance(source.sample(), PoolAvailable)

    runtime.close()

    assert runtime.pool_metrics is source
    assert isinstance(source.sample(), PoolDetached)


@pytest.mark.adapter_smoke
def test_a_queued_borrower_is_visible_as_queue_depth(profile_run: Any) -> None:
    # The gauge an operator watches for saturation, read from a real queue: one
    # slot, one holder, and one contender that has actually reached the queue.
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=1, acquire_timeout=5.0))
    contended: list[str] = []
    try:
        with _context(runtime) as held:
            assert _pid(held)

            def contend() -> None:
                with _context(runtime) as second:
                    contended.append(str(_pid(second)))

            waiter = threading.Thread(target=contend)
            waiter.start()
            _wait_until_queued(runtime)
            assert _measurements(runtime).requests_waiting == 1
        waiter.join(timeout=10.0)
        assert contended
        assert _measurements(runtime).requests_waiting == 0
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_sample_is_unavailable_rather_than_raising_when_the_pool_will_not_answer(
    profile_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A real runtime, with only the native statistics call made to fail: an
    # exporter sampling on its own cadence gets an answer it can record rather
    # than an exception it has to defend against, and the source stays attached.
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0, max_size=1))
    try:
        source = runtime.pool_metrics
        assert source is not None

        def refuse() -> dict[str, int]:
            raise RuntimeError("the pool refuses to be measured")

        # The native pool is the runtime's own and its statistics call is the
        # one seam this failure can come from.
        monkeypatch.setattr(runtime._pool, "get_stats", refuse)
        unavailable = source.sample()
        monkeypatch.undo()

        assert isinstance(unavailable, PoolUnavailable)
        assert isinstance(source.sample(), PoolAvailable)
    finally:
        runtime.close()
