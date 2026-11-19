from __future__ import annotations

from contextlib import ExitStack, closing, contextmanager
from time import monotonic
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from testcontainers.community.postgres import PostgresContainer

from parallax.conformance import constants
from parallax.conformance._postgres_control import PostgresControl
from parallax.core.internal.db_port import (
    ConnectionAcquisitionError,
    DatabaseStartupError,
    Password,
    PoolAvailable,
    RouteSelection,
)
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresAdapter, PostgresEndpoint
from parallax.postgres._connection import (
    _SERVER_DIAL_MESSAGES,  # pyright: ignore[reportPrivateUsage] - require a canary for every entry
    _fatal_dial_message,  # pyright: ignore[reportPrivateUsage] - inspect native diagnostic text
    dial_reason,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from psycopg.rows import TupleRow

    from parallax.conformance._database_control import DriverControl
    from parallax.core.internal.db_port import Row
    from parallax.postgres._runtime import PostgresRuntime


def _endpoint(endpoint: PostgresEndpoint, **options: str) -> PostgresEndpoint:
    return PostgresEndpoint(
        make_conninfo(endpoint.connection_string, **options),
        credentials=endpoint.credentials,
        pool=endpoint.pool,
    )


def _dial(endpoint: PostgresEndpoint) -> psycopg.Connection[TupleRow]:
    assert isinstance(endpoint.credentials, Password)
    return psycopg.connect(  # database-access: native dial diagnostics on canary servers
        endpoint.connection_string,
        password=endpoint.credentials.secret,
        connect_timeout=3,
        autocommit=True,
    )


@contextmanager
def _login(
    admin: DriverControl,
    endpoint: PostgresEndpoint,
    *,
    limit: int = -1,
) -> Generator[PostgresEndpoint]:
    login = f"capacity_{uuid4().hex}"
    password = Password(uuid4().hex)
    admin.execute(
        f"create role {login} login password '{password.secret}' connection limit {limit}", []
    )
    try:
        yield PostgresEndpoint(
            make_conninfo(endpoint.connection_string, user=login), credentials=password
        )
    finally:
        admin.execute(f"drop role {login}", [])


@contextmanager
def _limited_database(
    admin: DriverControl, endpoint: PostgresEndpoint
) -> Generator[PostgresEndpoint]:
    database = f"capacity_{uuid4().hex}"
    admin.execute(f"create database {database} connection limit 1", [])
    try:
        yield _endpoint(endpoint, dbname=database)
    finally:
        admin.execute(f"drop database {database} with (force)", [])


def _refused(endpoint: PostgresEndpoint) -> psycopg.OperationalError:
    with pytest.raises(psycopg.OperationalError) as failed, _dial(endpoint):
        pass
    return failed.value


def _database_missing(endpoint: PostgresEndpoint) -> psycopg.OperationalError:
    missing = _endpoint(endpoint, dbname=f"absent_{uuid4().hex}")
    adapter = PostgresAdapter(writer=endpoint, reader=missing)
    with pytest.raises(DatabaseStartupError) as failed:
        adapter.open()  # database-access: routes over profile_run's shared server

    assert (failed.value.route, failed.value.phase) == ("reader", "acquire")
    acquisition = failed.value.__cause__
    assert isinstance(acquisition, ConnectionAcquisitionError)
    assert acquisition.reason == "preparation_failed"
    native = acquisition.__cause__
    assert isinstance(native, psycopg.OperationalError)
    return native


def _isolated_server_refusals() -> tuple[
    psycopg.OperationalError, psycopg.OperationalError, psycopg.OperationalError
]:
    server = PostgresContainer(  # database-access: isolated capacity canary
        constants.POSTGRES_IMAGE,
        driver=None,
        command=[
            "postgres",
            "-c",
            "max_connections=8",
            "-c",
            "superuser_reserved_connections=1",
            "-c",
            "reserved_connections=1",
        ],
    )
    with ExitStack() as container:
        container.callback(server.stop)
        server.start()
        admin_endpoint = PostgresEndpoint(
            make_conninfo(
                host=server.get_container_host_ip(),
                port=server.get_exposed_port(server.port),
                user=server.username,
                dbname=server.dbname,
            ),
            credentials=Password(server.password),
        )
        admin = PostgresControl.open(  # database-access: administrative session on the canary
            server.get_connection_url(), autocommit=True, prepare_threshold=None
        )
        with closing(admin), _login(admin, admin_endpoint) as ordinary, ExitStack() as held:
            # The admin and five ordinary sessions occupy the ordinary slots.
            for _ in range(5):
                held.enter_context(_dial(ordinary))
            reserved_role = _refused(ordinary)
            held.enter_context(_dial(admin_endpoint))
            superuser = _refused(ordinary)
            held.enter_context(_dial(admin_endpoint))
            full = _refused(admin_endpoint)
    return reserved_role, superuser, full


def test_each_server_dial_message_has_a_real_server_canary(profile_run: Any) -> None:
    shared: PostgresEndpoint = profile_run.endpoint(pool=OnDemandOptions())
    missing_database = _database_missing(shared)
    with closing(profile_run.control()) as admin:
        with _login(admin, shared, limit=1) as limited_role, _dial(limited_role):
            per_role = _refused(limited_role)
        with (
            _login(admin, shared) as ordinary,
            _limited_database(admin, ordinary) as limited_database,
            _dial(limited_database),
        ):
            per_database = _refused(limited_database)

    reserved_role, superuser, full = _isolated_server_refusals()
    assert "pg_use_reserved_connections" in _fatal_dial_message(reserved_role)
    assert "SUPERUSER" in _fatal_dial_message(superuser)
    assert _fatal_dial_message(per_role).startswith('too many connections for role "')
    assert _fatal_dial_message(per_database).startswith('too many connections for database "')

    canaries = {
        "missing-database": (missing_database,),
        "connection-limit": (per_role, per_database),
        "reserved-slots": (reserved_role, superuser),
        "server-full": (full,),
    }
    assert canaries.keys() == _SERVER_DIAL_MESSAGES.keys()
    for name, (_, reason) in _SERVER_DIAL_MESSAGES.items():
        for failure in canaries[name]:
            assert failure.sqlstate is None
            message = _fatal_dial_message(failure)
            matches = {
                key for key, (pattern, _) in _SERVER_DIAL_MESSAGES.items() if pattern.match(message)
            }
            assert matches == {name}, message
            assert dial_reason(failure) == reason


def _preferred_read(runtime: PostgresRuntime) -> tuple[Row, RouteSelection | None]:
    resource = runtime.login_source().new_context("reader_preferred")
    with resource as connection:
        (row,) = connection.execute(
            "select current_setting('application_name'), session_user", [], read_only=True
        )
    return row, resource.selection


def test_a_reader_at_its_login_limit_defers_falls_back_and_recovers(profile_run: Any) -> None:
    with (
        closing(profile_run.control()) as admin,
        _login(admin, profile_run.endpoint(), limit=2) as login,
    ):
        # A zero reader minimum lets the writer reserve its slot before the reader's first dial.
        writer = PostgresEndpoint(
            make_conninfo(login.connection_string, application_name="capacity-writer"),
            credentials=login.credentials,
            pool=PoolOptions(max_size=1),
        )
        reader = PostgresEndpoint(
            make_conninfo(login.connection_string, application_name="capacity-reader"),
            credentials=login.credentials,
            pool=PoolOptions(min_size=0, max_size=1, reconnect_timeout=2.0),
        )
        adapter = PostgresAdapter(
            writer=writer, reader=reader, acquire_timeout=0.5, startup_timeout=1.5
        )
        with _dial(login) as holder:
            runtime = adapter.open()  # database-access: two routes over profile_run's shared server
            try:
                _, reader_metrics, _ = runtime.pool_metrics
                pending = reader_metrics.sample()
                assert isinstance(pending, PoolAvailable) and pending.readiness == "pending"

                writer_row = ("capacity-writer", runtime.login_identity)
                fallback = (writer_row, RouteSelection("writer", "unavailable"))
                assert _preferred_read(runtime) == fallback

                strict = runtime.login_source().new_context("reader_only")
                with pytest.raises(ConnectionAcquisitionError) as unavailable, strict:
                    pass
                assert unavailable.value.reason == "unavailable"
                failure = unavailable.value.__cause__
                assert isinstance(failure, psycopg.OperationalError)
                assert _fatal_dial_message(failure).startswith('too many connections for role "')

                holder.close()
                recovered = (("capacity-reader", runtime.login_identity), RouteSelection("reader"))
                deadline = monotonic() + 5.0
                while (observed := _preferred_read(runtime)) != recovered:
                    assert observed == fallback
                    if monotonic() >= deadline:
                        pytest.fail(
                            "the retaining reader did not recover after a slot was released"
                        )

                verified = reader_metrics.sample()
                assert isinstance(verified, PoolAvailable) and verified.readiness == "verified"
            finally:
                runtime.close()
