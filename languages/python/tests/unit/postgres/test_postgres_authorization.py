"""PostgreSQL authority values and role command rendering."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from psycopg.sql import Composed

from parallax.core.base import UsageError
from parallax.postgres import PostgresRole
from parallax.postgres._authorization import install_role, restore_role
from tests._support.errors import raises_code


class _RecordingConnection:
    def __init__(self) -> None:
        self.commands: list[object] = []

    def execute(self, command: object) -> None:
        self.commands.append(command)

    def cursor(self) -> _RecordingConnection:
        return self

    def __enter__(self) -> _RecordingConnection:
        return self

    def __exit__(self, *_: object) -> None:
        return


def test_postgres_role_is_an_immutable_opaque_nonempty_name() -> None:
    role = PostgresRole(" Tenant Role ")

    assert role.name == " Tenant Role "
    with pytest.raises(FrozenInstanceError):
        role.name = "other"  # pyright: ignore[reportAttributeAccessIssue] - immutability witness
    with raises_code(UsageError, "authorization-invalid"):
        PostgresRole("")
    with raises_code(UsageError, "authorization-invalid"):
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
