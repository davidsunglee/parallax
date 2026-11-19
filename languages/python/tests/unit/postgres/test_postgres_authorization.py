"""PostgreSQL authority values."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from parallax.core.internal.base import UsageError
from parallax.postgres import PostgresRole
from tests._support.errors import raises_code


def test_postgres_role_is_an_immutable_opaque_nonempty_name() -> None:
    role = PostgresRole(" Tenant Role ")

    assert role.name == " Tenant Role "
    with pytest.raises(FrozenInstanceError):
        role.name = "other"  # pyright: ignore[reportAttributeAccessIssue] - immutability witness
    with raises_code(UsageError, "authorization-invalid"):
        PostgresRole("")
    with raises_code(UsageError, "authorization-invalid"):
        PostgresRole(cast("Any", 7))
