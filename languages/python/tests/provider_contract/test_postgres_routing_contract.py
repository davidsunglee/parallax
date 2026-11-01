"""A writer and a reader route to one real server (`database-provider-test-contract`).

Two endpoints over this run's one database are two routes to the same server,
which is all these proofs need: which pool a lease came from, which source was
asked, which login authenticated, and what readiness the open established. Each
endpoint names itself through ``application_name``, so the server, not the
adapter's own diagnostics, says where a lease landed. What a reader route
observes about the writer's changes needs a real standby and is proved apart
from this. Refusal and recovery of a pending reader, a reader authenticating
another login, and concurrent proofs are ``tests/unit/postgres``'s, because a
server will not produce them on demand.
"""

from __future__ import annotations

import socket
from contextlib import closing
from typing import Any

import pytest

from parallax.core.db_port import (
    ConnectionAcquisitionError,
    DatabaseStartupError,
    Password,
    PoolAvailable,
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


@pytest.mark.adapter_smoke
def test_a_reader_whose_login_the_server_rejects_reads_as_unreachable(
    profile_run: Any,
) -> None:
    # The driver reports a refusal the server sent while connecting without its
    # SQLSTATE, so a rejected reader login is classified exactly as an outage:
    # required readiness fails the open on it, and deferrable readiness would
    # defer it.
    adapter = _routed(
        profile_run,
        _reader(profile_run, pool=OnDemandOptions(), credentials=Password("not-the-secret")),
        startup_timeout=10.0,
        reader_startup="required",
    )

    with pytest.raises(DatabaseStartupError) as failed:
        adapter.open()

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    cause = failed.value.__cause__
    assert isinstance(cause, ConnectionAcquisitionError) and cause.reason == "unavailable"
