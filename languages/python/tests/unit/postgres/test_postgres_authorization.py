"""PostgreSQL authority values and role command rendering."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from psycopg.sql import Composed

from parallax.core.db_port import InvalidAuthorizationError
from parallax.postgres import PoolOptions, PostgresRole
from parallax.postgres._authorization import install_role, restore_role
from parallax.postgres._connection import ConnectionPreparation
from parallax.postgres._runtime import PostgresRuntime


class _RecordingConnection:
    def __init__(self) -> None:
        self.commands: list[object] = []

    def execute(self, command: object) -> None:
        self.commands.append(command)


class _UnusedPool:
    def get_stats(self) -> dict[str, int]:
        return {}

    def close(self) -> None:
        return


def test_postgres_role_is_an_immutable_opaque_nonempty_name() -> None:
    role = PostgresRole(" Tenant Role ")

    assert role.name == " Tenant Role "
    with pytest.raises(FrozenInstanceError):
        role.name = "other"  # pyright: ignore[reportAttributeAccessIssue] - immutability witness
    with pytest.raises(InvalidAuthorizationError):
        PostgresRole("")
    with pytest.raises(InvalidAuthorizationError):
        PostgresRole(cast("Any", 7))


def test_role_commands_use_identifier_composition_and_fixed_restoration() -> None:
    connection = _RecordingConnection()
    role = PostgresRole('tenant"; reset role; --')

    install_role(connection, role)
    restore_role(connection)

    installed, restored = connection.commands
    assert isinstance(installed, Composed)
    assert installed.as_string() == 'SET ROLE "tenant""; reset role; --"'
    assert restored == "RESET ROLE"


def test_principal_binding_refuses_any_value_other_than_postgres_role() -> None:
    runtime = PostgresRuntime(cast("Any", _UnusedPool()), PoolOptions(), ConnectionPreparation())

    with pytest.raises(InvalidAuthorizationError):
        runtime.principal_execution(cast("Any", "tenant"))
