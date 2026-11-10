"""A writer and a reader route to one real server (`database-provider-test-contract`).

Two endpoints over this run's one database are two routes to the same server,
which is all these proofs need: which pool a lease came from, which source was
asked, which login authenticated, and what readiness the open established. Each
endpoint names itself through ``application_name``, so the server, not the
adapter's own diagnostics, says where a lease landed. What a reader route
observes about the writer's changes needs a real standby and is proved apart
from this. Refusal and recovery of a pending reader, a reader authenticating
another login, concurrent proofs, the probe slot, and a connection lost while
it is being set up are ``tests/unit/postgres``'s, because a server will not
produce them on demand.
"""

from __future__ import annotations

import socket
from contextlib import closing
from typing import Any

import pytest
from psycopg.conninfo import make_conninfo

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

_WHERE = "select current_setting('application_name') as route, session_user as login"


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
    assert [source.route for source in runtime.pool_metrics] == ["writer", "reader"]
    assert all(isinstance(sample, PoolAvailable) for sample in samples)
    assert [sample.readiness for sample in samples if isinstance(sample, PoolAvailable)] == [
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
        (_writer, reader) = [source.sample() for source in runtime.pool_metrics]
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


def _missing_database(endpoint: PostgresEndpoint) -> PostgresEndpoint:
    """``endpoint`` naming a database the server does not have."""
    return PostgresEndpoint(
        make_conninfo(endpoint.connection_string, dbname="parallax_no_such_database"),
        credentials=endpoint.credentials,
        pool=OnDemandOptions(),
    )


@pytest.mark.adapter_smoke
@pytest.mark.parametrize(
    ("refusal", "reason"),
    [
        ("rejected-password", "authentication_refused"),
        ("missing-database", "preparation_failed"),
    ],
)
def test_a_reader_the_server_refuses_once_its_password_is_sent_fails_even_deferrable_startup(
    profile_run: Any, refusal: str, reason: str
) -> None:
    # The driver reports the refusal with no SQLSTATE, but the failed
    # connection says it sent the password, so the server was reached and
    # refused it rather than being an outage. Only this server's own message
    # tells a database that does not exist apart from a rejected login, so a
    # server or driver that rewords it fails here.
    reader = (
        _reader(profile_run, pool=OnDemandOptions(), credentials=Password("not-the-secret"))
        if refusal == "rejected-password"
        else _missing_database(_reader(profile_run))
    )
    adapter = _routed(profile_run, reader, startup_timeout=10.0)

    with pytest.raises(DatabaseStartupError) as failed:
        adapter.open()

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError)
    assert cause.reason == reason


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
