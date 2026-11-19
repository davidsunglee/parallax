"""A writer and a reader route to one real server (`database-provider-test-contract`).

Two endpoints over this run's one database are two routes to the same server,
which is all these proofs need: which pool a lease came from, which source was
asked, which login authenticated, and what readiness the open established. Each
endpoint names itself through ``application_name``, so the server, not the
adapter's own diagnostics, says where a lease landed. What a reader route
observes about the writer's changes needs a real standby and is proved apart
from this. Concurrent readiness proofs, the probe slot, and races during
connection setup are exercised with scripted faults in ``tests/unit/postgres``.
"""

from __future__ import annotations

import socket
from contextlib import closing, contextmanager
from dataclasses import replace
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any

import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import (
    Committed,
    ConnectionAcquisitionError,
    DatabaseConnection,
    DatabaseStartupError,
    Password,
    PoolAvailable,
    RouteSelection,
    Row,
)
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresEndpoint
from tests.provider_contract.tcp_forwarder import TcpForwarder

if TYPE_CHECKING:
    from collections.abc import Generator

    from parallax.core.internal.db_port import PoolMetricsSource

_WHERE = "select current_setting('application_name') as route, session_user as login"
_RECOVERING_READER = PoolOptions(reconnect_timeout=2.0)


class _Counting:
    """The run's own credential source, counting how often it is asked."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls = 0

    def resolve(self) -> Any:
        self.calls += 1
        return self._inner.resolve()


def _named(route: str) -> dict[str, str]:
    return {"application_name": f"parallax-test-{route}"}


def _reader(profile_run: Any, **options: Any) -> PostgresEndpoint:
    return profile_run.endpoint(settings=_named("reader"), **options)


def _routed(profile_run: Any, reader: PostgresEndpoint, **options: Any) -> Any:
    """This run's database as the writer, with ``reader`` as its reader route."""
    options.setdefault("pool", OnDemandOptions())
    return profile_run.configured(settings=_named("writer"), reader=reader, **options)


def _where(runtime: Any, policy: str, role: Any = None) -> tuple[object, ...]:
    source = runtime.login_source() if role is None else runtime.principal_source(role)
    with source.new_context(policy) as connection:
        (row,) = connection.execute(_WHERE, [])
    return row


def _where_inside(port: DatabaseConnection) -> list[Row]:
    return port.execute(_WHERE, [])


def _unreachable_endpoint(profile_run: Any) -> PostgresEndpoint:
    """An endpoint whose host accepts no connection: a port nothing listens on."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return PostgresEndpoint(
        f"host=127.0.0.1 port={port} dbname=postgres connect_timeout=1",
        credentials=profile_run.credentials,
        pool=OnDemandOptions(),
    )


@pytest.mark.adapter_smoke
def test_each_strict_policy_leases_from_its_own_route_under_the_same_login(
    profile_run: Any,
) -> None:
    runtime = _routed(
        profile_run,
        _reader(profile_run, pool=PoolOptions(min_size=0)),
        pool=PoolOptions(min_size=0),
    ).open()
    try:
        writer = _where(runtime, "writer_only")
        reader = _where(runtime, "reader_only")
        samples = [source.sample() for source in runtime.pool_metrics]
    finally:
        runtime.close()

    assert writer == ("parallax-test-writer", runtime.login_identity)
    assert reader == ("parallax-test-reader", runtime.login_identity)
    assert [(source.route, source.purpose) for source in runtime.pool_metrics] == [
        ("writer", "application"),
        ("reader", "application"),
        ("writer", "reservation"),
    ]
    assert all(isinstance(sample, PoolAvailable) for sample in samples)
    assert [sample.readiness for sample in samples if isinstance(sample, PoolAvailable)] == [
        "verified",
        "verified",
        "verified",
    ]


@pytest.mark.adapter_smoke
def test_each_route_asks_only_its_own_source_and_keeps_its_own_capacity(
    profile_run: Any,
) -> None:
    writer_source = _Counting(profile_run.credentials)
    reader_source = _Counting(profile_run.credentials)
    runtime = _routed(
        profile_run,
        _reader(profile_run, pool=PoolOptions(min_size=0, max_size=2), credentials=reader_source),
        pool=PoolOptions(min_size=1, max_size=1),
        credentials=writer_source,
        acquire_timeout=1.0,
    ).open()
    try:
        # One retained writer connection and one reader dialed for its proof.
        assert (writer_source.calls, reader_source.calls) == (1, 1)
        reader = runtime.login_source()
        with reader.new_context("reader_only"), reader.new_context("reader_only"):
            # A third reader lease waits on the reader's own capacity while
            # the writer still has its own connection to give.
            with pytest.raises(ConnectionAcquisitionError) as saturated:
                reader.new_context("reader_only").__enter__()
            assert _where(runtime, "writer_only")[0] == "parallax-test-writer"
        assert saturated.value.reason == "timeout"
        assert writer_source.calls == 1
        assert reader_source.calls == 2
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_reader_lease_installs_the_bound_principal(profile_run: Any) -> None:
    runtime = _routed(profile_run, _reader(profile_run, pool=OnDemandOptions())).open()
    role = profile_run.authorization("role-a")
    try:
        source = runtime.principal_source(role)
        with source.new_context("reader_only") as connection:
            (row,) = connection.execute(
                "select current_setting('application_name') as route, current_user as role", []
            )
    finally:
        runtime.close()

    assert row == ("parallax-test-reader", role.name)


@pytest.mark.adapter_smoke
def test_an_unreachable_reader_is_left_pending_and_refuses_reader_work(
    profile_run: Any,
) -> None:
    runtime = _routed(
        profile_run,
        _unreachable_endpoint(profile_run),
        acquire_timeout=2.0,
        startup_timeout=10.0,
    ).open()
    try:
        (_writer, reader, _reservation) = [source.sample() for source in runtime.pool_metrics]
        assert isinstance(reader, PoolAvailable) and reader.readiness == "pending"
        assert _where(runtime, "writer_only")[0] == "parallax-test-writer"
        with pytest.raises(ConnectionAcquisitionError) as refused:
            runtime.login_source().new_context("reader_only").__enter__()
    finally:
        runtime.close()

    assert refused.value.reason == "unavailable"


@pytest.mark.adapter_smoke
def test_an_unreachable_reader_fails_the_open_when_it_is_required(profile_run: Any) -> None:
    adapter = _routed(
        profile_run,
        _unreachable_endpoint(profile_run),
        startup_timeout=10.0,
        reader_startup="required",
    )

    with pytest.raises(DatabaseStartupError) as failed:
        adapter.open()

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")


@contextmanager
def _forwarded_reader(
    profile_run: Any, *, pool: PoolOptions = _RECOVERING_READER
) -> Generator[tuple[PostgresEndpoint, TcpForwarder]]:
    reader = _reader(profile_run, pool=pool)
    conninfo = conninfo_to_dict(reader.connection_string)
    host, port = conninfo["host"], conninfo["port"]
    assert isinstance(host, str) and isinstance(port, str | int)
    with TcpForwarder.open((host, int(port))) as forwarder:
        yield (
            replace(
                reader,
                connection_string=make_conninfo(
                    reader.connection_string, host="127.0.0.1", port=forwarder.port
                ),
            ),
            forwarder,
        )


@pytest.mark.adapter_smoke
def test_a_deferred_retaining_reader_serves_after_its_endpoint_recovers(profile_run: Any) -> None:
    with _forwarded_reader(profile_run) as (reader, forwarder):
        runtime = _routed(profile_run, reader, acquire_timeout=0.25, startup_timeout=1.0).open()
        try:
            _, source, _ = runtime.pool_metrics
            pending = source.sample()
            assert isinstance(pending, PoolAvailable) and pending.readiness == "pending"

            forwarder.restore()
            deadline = monotonic() + 5.0
            while True:
                try:
                    row = _where(runtime, "reader_only")
                except ConnectionAcquisitionError as error:
                    assert error.reason in {"timeout", "unavailable"}
                    if monotonic() >= deadline:
                        raise AssertionError("the retaining reader did not recover") from error
                else:
                    break

            assert row == ("parallax-test-reader", runtime.login_identity)
            verified = source.sample()
            assert isinstance(verified, PoolAvailable) and verified.readiness == "verified"
        finally:
            runtime.close()


@pytest.mark.adapter_smoke
def test_an_unreachable_required_retaining_reader_fails_at_acquire(profile_run: Any) -> None:
    with _forwarded_reader(profile_run) as (reader, _forwarder):
        adapter = _routed(profile_run, reader, startup_timeout=1.0, reader_startup="required")
        with pytest.raises(DatabaseStartupError) as failed:
            adapter.open()

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError)
    assert cause.reason == "unavailable"


def _wait_for_failed_dial(source: PoolMetricsSource, previous_errors: int) -> None:
    deadline = monotonic() + 5.0
    while True:
        sample = source.sample()
        assert isinstance(sample, PoolAvailable)
        if sample.measurements.connections_errors > previous_errors:
            return
        if monotonic() >= deadline:
            pytest.fail("the reader pool did not record a failed dial after severing")
        sleep(0.01)


def _preferred_where(runtime: Any) -> tuple[Row, RouteSelection]:
    resource = runtime.login_source().new_context("reader_preferred")
    with resource as connection:
        (row,) = connection.execute(_WHERE, [], read_only=True)
    assert resource.selection is not None
    return row, resource.selection


@pytest.mark.adapter_smoke
def test_a_retaining_reader_falls_back_during_an_outage_and_serves_again(
    profile_run: Any,
) -> None:
    with _forwarded_reader(profile_run, pool=replace(_RECOVERING_READER, max_size=1)) as (
        reader,
        forwarder,
    ):
        forwarder.restore()
        runtime = _routed(
            profile_run, reader, pool=PoolOptions(max_size=1), acquire_timeout=0.5
        ).open()
        try:
            reader_row = ("parallax-test-reader", runtime.login_identity)
            writer_row = ("parallax-test-writer", runtime.login_identity)
            fallback = (writer_row, RouteSelection("writer", "unavailable"))
            recovered = (reader_row, RouteSelection("reader"))
            assert _preferred_where(runtime) == recovered

            _, reader_metrics, _ = runtime.pool_metrics
            healthy = reader_metrics.sample()
            assert isinstance(healthy, PoolAvailable)

            # A designated read's replacement stays on the route that began serving it.
            lost = runtime.login_source().new_context("reader_preferred")
            with lost as connection:
                forwarder.sever()
                with pytest.raises(DatabaseError):
                    connection.execute(_WHERE, [], read_only=True)
            assert lost.selection == RouteSelection("reader")
            _wait_for_failed_dial(reader_metrics, healthy.measurements.connections_errors)

            for _ in range(4):
                assert _preferred_where(runtime) == fallback
            with pytest.raises(ConnectionAcquisitionError) as unavailable:
                _where(runtime, "reader_only")
            assert unavailable.value.reason == "unavailable"
            assert unavailable.value.selection == RouteSelection("reader")

            forwarder.restore()
            deadline = monotonic() + 5.0
            while (result := _preferred_where(runtime)) != recovered:
                assert result == fallback
                if monotonic() >= deadline:
                    pytest.fail("a preferred read never returned to the restored reader")
        finally:
            runtime.close()


@pytest.mark.adapter_smoke
def test_a_reader_with_a_rejected_password_fails_even_deferrable_startup(
    profile_run: Any,
) -> None:
    reader = _reader(profile_run, pool=OnDemandOptions(), credentials=Password("not-the-secret"))
    adapter = _routed(profile_run, reader, startup_timeout=10.0)

    with pytest.raises(DatabaseStartupError) as failed:
        adapter.open()

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError)
    assert cause.reason == "authentication_refused"


@pytest.mark.adapter_smoke
def test_a_preferred_read_is_served_by_a_healthy_reader(profile_run: Any) -> None:
    runtime = _routed(profile_run, _reader(profile_run, pool=OnDemandOptions())).open()
    try:
        resource = runtime.login_source().new_context("reader_preferred")
        with resource as connection:
            (row,) = connection.execute(_WHERE, [])
    finally:
        runtime.close()

    assert row == ("parallax-test-reader", runtime.login_identity)
    assert resource.selection == RouteSelection("reader")


@pytest.mark.adapter_smoke
def test_a_preferred_read_falls_back_to_the_writer_from_an_unreachable_reader(
    profile_run: Any,
) -> None:
    runtime = _routed(
        profile_run,
        _unreachable_endpoint(profile_run),
        acquire_timeout=4.0,
        startup_timeout=10.0,
    ).open()
    role = profile_run.authorization("role-a")
    try:
        resource = runtime.principal_source(role).new_context("reader_preferred")
        with resource as connection:
            (row,) = connection.execute(
                "select current_setting('application_name') as route, current_user as role", []
            )
        transaction = runtime.login_source().new_context("reader_preferred")
        with transaction as connection:
            outcome = connection.transaction(
                _where_inside,
                isolation="repeatable_read",
                access_mode="read_only",
            )
    finally:
        runtime.close()

    assert row == ("parallax-test-writer", role.name)
    assert resource.selection == RouteSelection("writer", "unavailable")
    assert outcome == Committed([("parallax-test-writer", runtime.login_identity)])
    assert transaction.selection == RouteSelection("writer", "unavailable")


@pytest.mark.adapter_smoke
def test_a_preferred_read_does_not_fall_back_from_a_busy_reader(profile_run: Any) -> None:
    runtime = _routed(
        profile_run,
        _reader(profile_run, pool=PoolOptions(min_size=0, max_size=1)),
        acquire_timeout=1.0,
    ).open()
    try:
        source = runtime.login_source()
        with (
            source.new_context("reader_only"),
            pytest.raises(ConnectionAcquisitionError) as busy,
        ):
            source.new_context("reader_preferred").__enter__()
    finally:
        runtime.close()

    assert busy.value.reason == "timeout"
    assert busy.value.selection == RouteSelection("reader")
