"""Postgres adapter internal-seam unit tests (Docker-free).

The public export is ``PostgresAdapter`` alone (§8 topology); psycopg bind
mechanics stay internal. The bind-adaptation seam — the neutral ``JsonDocument``
carrier becoming a psycopg ``Jsonb`` at the adapter boundary — and the
`m-db-error` port-boundary re-raise (every psycopg exception translated to a
neutral ``DatabaseError``) are both pure and proven here without a container; the
end-to-end deadlock witness lives in the provider lane.
"""

from __future__ import annotations

from collections.abc import Callable
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
    """A ``connection.transaction()`` stand-in that raises at any boundary asked.

    The adapter wraps the WHOLE boundary in its translating block, so begin,
    commit, and rollback are three raise sites of the port, not one: a driver
    failure at any of them reaches the caller as a port-raised error.
    """

    def __init__(
        self,
        *,
        begin_error: psycopg.Error | None,
        commit_error: psycopg.Error | None,
        rollback_error: psycopg.Error | None,
    ) -> None:
        self._begin_error = begin_error
        self._commit_error = commit_error
        self._rollback_error = rollback_error

    def __enter__(self) -> _FakeTxn:
        if self._begin_error is not None:
            raise self._begin_error
        return self

    def __exit__(self, _exc_type: object, exc: BaseException | None, _tb: object) -> bool:
        failure = self._rollback_error if exc is not None else self._commit_error
        if failure is not None:
            raise failure
        return False


class _FakeAdapters:
    """A ``connection.adapters`` stand-in recording the loaders the adapter registers."""

    def __init__(self) -> None:
        self.registered: list[tuple[str, object]] = []

    def register_loader(self, name: str, loader: object) -> None:
        self.registered.append((name, loader))


class _FakeConnection:
    """A minimal psycopg-connection stand-in for the boundary-wrapping tests.

    Each injected failure is a public attribute read at call time, so one
    connection — and therefore one adapter — can be driven through each raise
    site in turn. ``begin_error`` is set for the invocation that needs it: a
    boundary that fails to begin reaches neither commit nor rollback.
    """

    def __init__(
        self,
        *,
        cursor_error: psycopg.Error | None = None,
        begin_error: psycopg.Error | None = None,
        commit_error: psycopg.Error | None = None,
        rollback_error: psycopg.Error | None = None,
    ) -> None:
        self.cursor_error = cursor_error
        self.begin_error = begin_error
        self.commit_error = commit_error
        self.rollback_error = rollback_error
        self.adapters = _FakeAdapters()

    def cursor(self, **_: object) -> _FakeCursor:
        return _FakeCursor(self.cursor_error)

    def transaction(self) -> _FakeTxn:
        return _FakeTxn(
            begin_error=self.begin_error,
            commit_error=self.commit_error,
            rollback_error=self.rollback_error,
        )


def _adapter(connection: _FakeConnection) -> PostgresAdapter:
    return PostgresAdapter(cast("psycopg.Connection[TupleRow]", connection))


def test_adapter_registers_the_infinity_timestamptz_loader() -> None:
    # The port normalizes native `timestamptz` infinity to the m-core sentinel by
    # registering a custom loader on the connection at construction.
    connection = _FakeConnection()
    _adapter(connection)
    assert [name for name, _loader in connection.adapters.registered] == ["timestamptz"]


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


class _BodyFailure(Exception):
    """A transaction body's own error — what makes the boundary roll back."""


def test_every_failed_port_invocation_raises_its_own_error_instance() -> None:
    # m-db-port failure identity, over every error the port itself makes: a
    # statement failure from `execute`, one from `execute_write`, and each
    # failure of the boundary `transaction` wraps whole -- its begin, its commit,
    # and its rollback, all three of which the adapter's translating block
    # covers. The driver here hands back ONE reused exception object for all of
    # them -- the input the rule exists to stop an adapter passing on -- so
    # distinctness can only come from translating at the failing call. Driving
    # every site over one adapter also rules out reuse ACROSS paths, which a
    # per-path cache would produce while each path alone looked clean. This is
    # what lets a caller (the Execution Log) tell which invocation the error it
    # caught came from.
    driver_error = errors.UniqueViolation("dup")
    connection = _FakeConnection(
        cursor_error=driver_error, commit_error=driver_error, rollback_error=driver_error
    )
    adapter = _adapter(connection)

    def failing_begin() -> object:
        # Scoped to this invocation: a boundary that never begins reaches
        # neither the commit nor the rollback site below.
        connection.begin_error = driver_error
        try:
            return adapter.transaction(lambda _port: None)
        finally:
            connection.begin_error = None

    def failing_rollback() -> object:
        def body(_port: object) -> None:
            raise _BodyFailure

        return adapter.transaction(body)

    invocations: tuple[Callable[[], object], ...] = (
        lambda: adapter.execute("select 1", []),
        lambda: adapter.execute_write("insert into gauge (v) values (%s)", [1]),
        failing_begin,
        lambda: adapter.transaction(lambda _port: None),
        failing_rollback,
    )
    raised: list[DatabaseError] = []
    for invoke in (*invocations, *invocations):
        with pytest.raises(DatabaseError) as exc_info:
            invoke()
        raised.append(exc_info.value)

    assert len({id(error) for error in raised}) == len(raised)
    assert {(error.category, error.native_code, error.message) for error in raised} == {
        ("uniqueViolation", "23505", "dup")
    }


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


def test_transaction_passes_a_body_raised_driver_error_unchanged() -> None:
    # m-db-port scopes translation to the errors the PORT makes; an exception the
    # caller's own body raised is not one of them, however psycopg-shaped it is.
    # The identical object reaches the caller, so a body-authored deadlock-class
    # exception cannot read as a retriable DatabaseError to m-auto-retry and have
    # the body replayed over a failure the database never reported.
    raised_by_the_body = errors.DeadlockDetected("the caller's own deadlock")

    def body(_port: object) -> None:
        raise raised_by_the_body

    adapter = _adapter(_FakeConnection())
    with pytest.raises(psycopg.Error) as exc_info:
        adapter.transaction(body)
    assert exc_info.value is raised_by_the_body


def test_transaction_translates_a_rollback_failure_over_a_body_driver_error() -> None:
    # The other side of the same boundary: the rollback the body triggered is the
    # port's own work, so ITS driver failure translates and is what escapes, even
    # though the body's exception was also a psycopg error. Identity is what
    # separates the two; the classes cannot.
    def body(_port: object) -> None:
        raise errors.DeadlockDetected("the caller's own deadlock")

    adapter = _adapter(_FakeConnection(rollback_error=errors.UniqueViolation("dup")))
    with pytest.raises(DatabaseError) as exc_info:
        adapter.transaction(body)
    assert exc_info.value.violates_unique_index
    assert exc_info.value.native_code == "23505"
