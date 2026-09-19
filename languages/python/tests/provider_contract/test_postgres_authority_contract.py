"""PostgreSQL execution authority against a real reused session."""

from __future__ import annotations

from typing import Any

import pytest

from parallax.core.db_error import DatabaseError
from parallax.core.db_port import ConnectionAcquisitionError
from parallax.postgres import PoolOptions, PostgresRole


def _identity(connection: Any) -> tuple[int, str, str]:
    (row,) = connection.execute(
        "select pg_backend_pid(), session_user, current_user",
        [],
    )
    return int(row[0]), str(row[1]), str(row[2])


@pytest.mark.adapter_smoke
def test_reused_session_contains_roles_and_restores_the_configured_default(
    profile_run: Any,
) -> None:
    profile_run.reset(*_grade_model())
    role_a = profile_run.authorization("role-a")
    role_b = profile_run.authorization("role-b")
    dialect = profile_run.port.dialect
    control = profile_run.control()
    try:
        control.execute_write("create table authority_a (value integer not null)", [])
        control.execute_write("create table authority_b (value integer not null)", [])
        control.execute_write(
            f"grant select, insert on authority_a to {dialect.quote(role_a.name)}", []
        )
        control.execute_write(
            f"grant select, insert on authority_b to {dialect.quote(role_b.name)}", []
        )
    finally:
        control.close()

    runtime = profile_run.configured(pool=PoolOptions(min_size=1, max_size=1)).open()
    try:
        login_source = runtime.login_execution()
        role_a_source = runtime.principal_execution(role_a)
        role_b_source = runtime.principal_execution(role_b)

        with login_source.new_context() as login:
            login_pid, session_user, current_user = _identity(login)
            assert session_user == profile_run.login_identity == runtime.login_identity
            assert current_user == profile_run.default_role.name
            assert login.execute("select count(*) from grade", []) == [(3,)]
            with pytest.raises(DatabaseError):
                login.execute("select value from authority_a", [])

        with role_a_source.new_context() as authorized_a:
            pid_a, session_user_a, current_user_a = _identity(authorized_a)
            assert (pid_a, session_user_a, current_user_a) == (
                login_pid,
                profile_run.login_identity,
                role_a.name,
            )
            authorized_a.execute_write("insert into authority_a (value) values (%s)", [1])
            assert authorized_a.execute("select value from authority_a", []) == [(1,)]
            with pytest.raises(DatabaseError):
                authorized_a.execute("select value from authority_b", [])

        with role_b_source.new_context() as authorized_b:
            pid_b, session_user_b, current_user_b = _identity(authorized_b)
            assert (pid_b, session_user_b, current_user_b) == (
                login_pid,
                profile_run.login_identity,
                role_b.name,
            )
            authorized_b.execute_write("insert into authority_b (value) values (%s)", [2])
            assert authorized_b.execute("select value from authority_b", []) == [(2,)]
            with pytest.raises(DatabaseError):
                authorized_b.execute("select value from authority_a", [])

        with login_source.new_context() as restored_login:
            restored_pid, restored_session, restored_current = _identity(restored_login)
            assert (restored_pid, restored_session, restored_current) == (
                login_pid,
                profile_run.login_identity,
                profile_run.default_role.name,
            )
            with pytest.raises(DatabaseError):
                restored_login.execute("select value from authority_a", [])
            with pytest.raises(DatabaseError):
                restored_login.execute("select value from authority_b", [])
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_server_role_refusal_disposes_the_session_before_login_execution_resumes(
    profile_run: Any,
) -> None:
    runtime = profile_run.configured(pool=PoolOptions(min_size=1, max_size=1)).open()
    try:
        with runtime.login_execution().new_context() as first:
            first_pid, _, default_role = _identity(first)

        refused = runtime.principal_execution(PostgresRole("role_that_does_not_exist"))
        with pytest.raises(ConnectionAcquisitionError) as failure:
            refused.new_context().__enter__()

        assert failure.value.reason == "authorization_failed"
        with runtime.login_execution().new_context() as replacement:
            replacement_pid, session_user, current_user = _identity(replacement)
        assert replacement_pid != first_pid
        assert session_user == runtime.login_identity == profile_run.login_identity
        assert current_user == default_role == profile_run.default_role.name
    finally:
        runtime.close()


def _grade_model() -> tuple[Any, Any]:
    from parallax.conformance import engine, provision
    from parallax.conformance.case_format import default_cases_dir, load_case

    case = load_case(default_cases_dir() / "m-descriptor-001-quoted-reserved-identifier.yaml")
    return engine.load_case_metamodel(case), provision.load_fixtures(str(case.document["model"]))
