"""Postgres adapter internal-seam unit tests (Docker-free).

The public export is ``PostgresAdapter`` alone (§8 topology); psycopg bind
mechanics stay internal. The bind-adaptation seam — the neutral ``JsonDocument``
carrier becoming a psycopg ``Jsonb`` at the adapter boundary — and the
`m-db-error` port-boundary re-raise (every psycopg exception translated to a
neutral ``DatabaseError``) are both pure and proven here without a container; the
end-to-end deadlock witness lives in the provider lane.
"""

from __future__ import annotations

from typing import cast

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import TupleRow
from psycopg.types.json import Jsonb

import parallax.postgres
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import JsonDocument
from parallax.postgres import PostgresAdapter
from parallax.postgres.adapter import (
    adapt_binds,
    translate_driver_error,
    translating_driver_errors,
)

pytestmark = pytest.mark.unit


def test_public_surface_is_the_adapter_alone() -> None:
    assert parallax.postgres.__all__ == ["PostgresAdapter"]
    assert not hasattr(parallax.postgres, "Json")
    assert not hasattr(parallax.postgres, "Jsonb")


def testadapt_binds_wraps_json_documents_and_passes_scalars_through() -> None:
    adapted = adapt_binds([1, "x", JsonDocument({"city": "Oslo"}), None])
    assert adapted[0] == 1
    assert adapted[1] == "x"
    assert isinstance(adapted[2], Jsonb)
    assert adapted[3] is None


def testadapt_binds_wraps_the_document_value() -> None:
    document = {"geo": {"lat": 1}}
    (adapted,) = adapt_binds([JsonDocument(document)])
    assert isinstance(adapted, Jsonb)
    assert adapted.obj == document


# -- port-boundary re-raise (m-db-error) ----------------------------------------


def test_translate_driver_error_maps_a_unique_violation() -> None:
    error = translate_driver_error(errors.UniqueViolation("dup key"))
    assert error.category == "uniqueViolation"
    assert error.native_code == "23505"
    assert error.violates_unique_index
    assert error.message == "dup key"


def test_translate_driver_error_is_uncategorized_without_sqlstate() -> None:
    # A driver failure with no SQLSTATE (a dropped connection) stays uncategorized.
    error = translate_driver_error(psycopg.OperationalError("connection closed"))
    assert error.category is None
    assert error.native_code is None
    assert error.message == "connection closed"


def test_translating_driver_errors_reraises_as_a_database_error() -> None:
    with pytest.raises(DatabaseError) as exc_info, translating_driver_errors():
        raise errors.DeadlockDetected("deadlock detected")
    assert exc_info.value.category == "deadlock"
    assert exc_info.value.is_retriable
    assert exc_info.value.native_code == "40P01"


def test_translating_driver_errors_passes_a_clean_block() -> None:
    with translating_driver_errors():
        value = 1 + 1
    assert value == 2


def test_translating_driver_errors_passes_a_non_driver_exception() -> None:
    class _Boom(Exception):
        pass

    with pytest.raises(_Boom), translating_driver_errors():
        raise _Boom


class _FakeCursor:
    """A psycopg-cursor stand-in whose ``execute`` raises a preset driver error."""

    def __init__(self, error: psycopg.Error | None) -> None:
        self._error = error
        self.description: object | None = None
        self.rowcount = 0

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(self, _sql: bytes, _binds: object) -> None:
        if self._error is not None:
            raise self._error

    def fetchall(self) -> list[object]:
        return []


class _FakeTxn:
    """A ``connection.transaction()`` stand-in that raises at commit if asked."""

    def __init__(self, commit_error: psycopg.Error | None) -> None:
        self._commit_error = commit_error

    def __enter__(self) -> _FakeTxn:
        return self

    def __exit__(self, _exc_type: object, exc: BaseException | None, _tb: object) -> bool:
        if exc is None and self._commit_error is not None:
            raise self._commit_error
        return False


class _FakeConnection:
    """A minimal psycopg-connection stand-in for the boundary-wrapping tests."""

    def __init__(
        self,
        *,
        cursor_error: psycopg.Error | None = None,
        commit_error: psycopg.Error | None = None,
    ) -> None:
        self._cursor_error = cursor_error
        self._commit_error = commit_error

    def cursor(self, **_: object) -> _FakeCursor:
        return _FakeCursor(self._cursor_error)

    def transaction(self) -> _FakeTxn:
        return _FakeTxn(self._commit_error)


def _adapter(connection: _FakeConnection) -> PostgresAdapter:
    return PostgresAdapter(cast("psycopg.Connection[TupleRow]", connection))


def test_execute_reraises_a_driver_error_at_the_boundary() -> None:
    adapter = _adapter(_FakeConnection(cursor_error=errors.UniqueViolation("dup")))
    with pytest.raises(DatabaseError) as exc_info:
        adapter.execute("select 1", [])
    assert exc_info.value.violates_unique_index
    assert exc_info.value.native_code == "23505"


def test_execute_write_reraises_a_driver_error_at_the_boundary() -> None:
    adapter = _adapter(_FakeConnection(cursor_error=errors.DeadlockDetected("deadlock")))
    with pytest.raises(DatabaseError) as exc_info:
        adapter.execute_write("update gauge set v = %s", [1])
    assert exc_info.value.category == "deadlock"
    assert exc_info.value.native_code == "40P01"


def test_transaction_reraises_a_commit_time_driver_error() -> None:
    adapter = _adapter(_FakeConnection(commit_error=errors.SerializationFailure("serialize")))
    with pytest.raises(DatabaseError) as exc_info:
        adapter.transaction(lambda _port: None)
    # A serialization failure at commit (40001) shares the retriable deadlock category.
    assert exc_info.value.category == "deadlock"
    assert exc_info.value.native_code == "40001"


def test_transaction_passes_a_non_driver_body_error_unchanged() -> None:
    class _Boom(Exception):
        pass

    def body(_port: object) -> None:
        raise _Boom

    adapter = _adapter(_FakeConnection())
    with pytest.raises(_Boom):
        adapter.transaction(body)
