"""Postgres adapter internal-seam unit tests (Docker-free).

The public exports are ``PostgresAdapter`` and ``isolation_spelling`` (§8
topology); psycopg bind mechanics stay internal. The bind-adaptation seam — the
neutral ``JsonDocument`` carrier becoming a psycopg ``Jsonb`` at the adapter
boundary — and the `m-db-error` port-boundary re-raise (every psycopg exception
translated to a neutral ``DatabaseError``) are both pure and proven here without
a container; the end-to-end deadlock witness lives in the provider lane.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import TupleRow
from psycopg.sql import Composable
from psycopg.types.json import Jsonb

import parallax.postgres
import parallax.postgres.adapter as adapter_module
from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    ISOLATION_LEVELS,
    BeginFailed,
    CallbackRaised,
    CommitFailed,
    Committed,
    JsonDocument,
    RollbackFailed,
    RolledBack,
    isolation_level,
)
from parallax.postgres import PostgresAdapter, isolation_spelling
from parallax.postgres.adapter import (
    adapt_binds,
    fold_document_reads,
    translate_driver_error,
    translating_driver_errors,
)

# Read off the class rather than named again here: these seams are the adapter's
# own internals, so grading them under any other dialect would grade something
# the adapter never runs.
_DIALECT = PostgresAdapter.dialect


def test_public_surface_is_the_adapter_and_this_engines_isolation_spelling() -> None:
    assert parallax.postgres.__all__ == ["PostgresAdapter", "isolation_spelling"]
    assert not hasattr(parallax.postgres, "Json")
    assert not hasattr(parallax.postgres, "Jsonb")


def test_every_portable_level_has_exactly_one_postgres_spelling() -> None:
    # The map is keyed by the port's own vocabulary, so a level added there with no
    # spelling here — or a spelling for a level the vocabulary does not name — is a
    # gap a caller meets as a KeyError on the level it asked for.
    spellings = {level: isolation_spelling(isolation_level(level)) for level in ISOLATION_LEVELS}
    assert spellings == {
        "read_committed": "read committed",
        "repeatable_read": "repeatable read",
        "serializable": "serializable",
    }


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
    error = translate_driver_error(_DIALECT, errors.UniqueViolation("dup key"))
    assert error.category == "uniqueViolation"
    assert error.native_code == "23505"
    assert error.violates_unique_index
    assert error.message == "dup key"


def test_translate_driver_error_is_uncategorized_without_sqlstate() -> None:
    # A driver failure with no SQLSTATE (a dropped connection) stays uncategorized.
    error = translate_driver_error(_DIALECT, psycopg.OperationalError("connection closed"))
    assert error.category is None
    assert error.native_code is None
    assert error.message == "connection closed"


def test_translating_driver_errors_reraises_as_a_database_error() -> None:
    with pytest.raises(DatabaseError) as exc_info, translating_driver_errors(_DIALECT):
        raise errors.DeadlockDetected("deadlock detected")
    assert exc_info.value.category == "deadlock"
    assert exc_info.value.is_retriable
    assert exc_info.value.native_code == "40P01"


def test_translating_driver_errors_passes_a_clean_block() -> None:
    with translating_driver_errors(_DIALECT):
        value = 1 + 1
    assert value == 2


def test_translating_driver_errors_passes_a_non_driver_exception() -> None:
    class _Boom(Exception):
        pass

    with pytest.raises(_Boom), translating_driver_errors(_DIALECT):
        raise _Boom


class _FakeCursor:
    """A psycopg-cursor stand-in whose ``execute`` raises a preset driver error.

    Every statement it is handed is appended to the list its connection gave it,
    so a test can ask what the adapter actually sent and in what order — which is
    the whole observable of a boundary opened at a requested isolation. A
    statement arrives either as the encoded text the port sends or as the
    composed statement a requested isolation is delimited into, so the list holds
    both and :func:`_sent` renders either one.
    """

    def __init__(self, error: psycopg.Error | None, executed: list[object]) -> None:
        self._error = error
        self._executed = executed
        self.description: object | None = None
        self.rowcount = 0

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(self, sql: bytes | Composable, _binds: object = None) -> None:
        self._executed.append(sql)
        if self._error is not None:
            raise self._error

    def fetchall(self) -> list[object]:
        return []


class _FakeTxn:
    """A ``connection.transaction()`` stand-in, faithful about what it hides.

    Begin and commit raise the driver failure asked of them. A ROLLBACK failure
    does NOT raise: psycopg's own transaction context catches it, logs a warning,
    and lets the exception that triggered the rollback carry on — which is why
    the adapter asks the connection to roll back a second time, and why this
    stand-in leaves that failure to :meth:`_FakeConnection.rollback` rather than
    raising it here. A stand-in that raised it would prove a boundary the real
    driver never presents.
    """

    def __init__(
        self, *, begin_error: psycopg.Error | None, commit_error: psycopg.Error | None
    ) -> None:
        self._begin_error = begin_error
        self._commit_error = commit_error

    def __enter__(self) -> _FakeTxn:
        if self._begin_error is not None:
            raise self._begin_error
        return self

    def __exit__(self, _exc_type: object, exc: BaseException | None, _tb: object) -> bool:
        if exc is None and self._commit_error is not None:
            raise self._commit_error
        return False


class _FakeAdapters:
    """A ``connection.adapters`` stand-in recording the loaders the adapter registers."""

    def __init__(self) -> None:
        self.registered: list[tuple[str, object]] = []

    def register_loader(self, name: str, loader: object) -> None:
        self.registered.append((name, loader))


class _FakeConnection:
    """A minimal psycopg-connection stand-in for the boundary tests.

    Each injected failure is a public attribute read at call time, so one
    connection — and therefore one adapter — can be driven through each failure
    site in turn. ``begin_error`` is set for the invocation that needs it: a
    boundary that fails to begin reaches neither commit nor rollback.
    ``rollback_error`` belongs to the connection rather than to the transaction
    context because that is where a real rollback failure becomes visible.
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
        self.rollbacks = 0
        self.closed = False
        self.executed: list[object] = []
        self.begins = 0

    def cursor(self, **_: object) -> _FakeCursor:
        return _FakeCursor(self.cursor_error, self.executed)

    def transaction(self) -> _FakeTxn:
        self.begins += 1
        return _FakeTxn(begin_error=self.begin_error, commit_error=self.commit_error)

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    def close(self) -> None:
        self.closed = True


def _adapter(connection: _FakeConnection) -> PostgresAdapter:
    return PostgresAdapter(cast("psycopg.Connection[TupleRow]", connection))


def _sent(connection: _FakeConnection) -> list[str]:
    """The statements the adapter handed the driver, as the driver would render them."""
    return [
        statement.as_string()
        if isinstance(statement, Composable)
        else cast("bytes", statement).decode()
        for statement in connection.executed
    ]


def test_adapter_registers_boundary_value_loaders() -> None:
    # The port normalizes native `timestamptz` infinity to the m-core sentinel by
    # registering a custom loader on the connection at construction.
    connection = _FakeConnection()
    _adapter(connection)
    assert [name for name, _loader in connection.adapters.registered] == [
        "timestamptz",
        "jsonb",
        "jsonb",
    ]


def test_fold_document_reads_distinguishes_sql_null_from_present_json_null() -> None:
    rows = fold_document_reads(
        _DIALECT,
        ("id", "doc_present", "doc"),
        (
            (1, False, None),
            (2, True, adapter_module._PRESENT_JSON_NULL),  # pyright: ignore[reportPrivateUsage]
        ),
        ((1, 2),),
    )
    assert rows == [
        {"id": 1, "doc": SQL_NULL},
        {"id": 2, "doc": PresentDocument(None)},
    ]


def test_json_loader_preserves_only_present_json_null() -> None:
    load = adapter_module._load_json_preserving_null  # pyright: ignore[reportPrivateUsage]
    assert load("null") is adapter_module._PRESENT_JSON_NULL  # pyright: ignore[reportPrivateUsage]
    assert load(b'{"answer": 42}') == {"answer": 42}


def test_fold_document_reads_rejects_invalid_projection_metadata_and_row_width() -> None:
    with pytest.raises(ValueError, match="adjacent, zero-based"):
        fold_document_reads(_DIALECT, ("presence", "gap", "document"), (), ((0, 2),))
    with pytest.raises(ValueError, match="must not overlap"):
        fold_document_reads(_DIALECT, ("first", "shared", "second"), (), ((0, 1), (1, 2)))
    with pytest.raises(ValueError, match="does not match"):
        fold_document_reads(_DIALECT, ("id", "presence", "document"), ((1, True),), ((1, 2),))


class _JsonNullCursor(_FakeCursor):
    def __init__(self) -> None:
        super().__init__(None, [])
        self.description = object()

    def fetchall(self) -> list[object]:
        return [{"id": 1, "doc": adapter_module._PRESENT_JSON_NULL}]  # pyright: ignore[reportPrivateUsage]


class _JsonNullConnection(_FakeConnection):
    def cursor(self, **_: object) -> _JsonNullCursor:
        return _JsonNullCursor()


def test_ordinary_execute_normalizes_present_json_null_to_none() -> None:
    assert _adapter(_JsonNullConnection()).execute("select 1", []) == [{"id": 1, "doc": None}]


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


def _translated(error: Exception) -> DatabaseError:
    """The neutral error a boundary outcome carries, which every failure the port
    itself makes must already be (`m-db-error` translation boundary)."""
    assert isinstance(error, DatabaseError)
    return error


def test_every_failed_port_invocation_reports_its_own_error_instance() -> None:
    # m-db-port failure identity, over every error the port itself makes: a
    # statement failure raised by `execute`, one raised by `execute_write`, and
    # each failure of the boundary `transaction` owns -- its begin, its commit,
    # and its rollback, all three of which the adapter classifies where they
    # occur. The driver here hands back ONE reused exception object for all of
    # them -- the input the rule exists to stop an adapter passing on -- so
    # distinctness can only come from classifying at the failing call. Driving
    # every site over one adapter also rules out reuse ACROSS paths, which a
    # per-path cache would produce while each path alone looked clean. This is
    # what lets a caller (an activity attributing its own failure) tell which
    # invocation the error it holds came from.
    driver_error = errors.UniqueViolation("dup")
    connection = _FakeConnection(cursor_error=driver_error, commit_error=driver_error)
    adapter = _adapter(connection)

    def raised(invoke: Callable[[], object]) -> DatabaseError:
        with pytest.raises(DatabaseError) as exc_info:
            invoke()
        return exc_info.value

    def failing_begin() -> DatabaseError:
        # Scoped to this invocation: a boundary that never begins reaches
        # neither the commit nor the rollback site below.
        connection.begin_error = driver_error
        try:
            outcome = adapter.transaction(lambda _port: None)
        finally:
            connection.begin_error = None
        assert isinstance(outcome, BeginFailed)
        return _translated(outcome.error)

    def failing_commit() -> DatabaseError:
        outcome = adapter.transaction(lambda _port: None)
        assert isinstance(outcome, RolledBack)
        trigger = outcome.trigger
        assert isinstance(trigger, CommitFailed)
        return _translated(trigger.error)

    def failing_rollback() -> DatabaseError:
        def body(_port: object) -> None:
            raise _BodyFailure

        connection.rollback_error = driver_error
        try:
            outcome = adapter.transaction(body)
        finally:
            connection.rollback_error = None
        assert isinstance(outcome, RollbackFailed)
        return _translated(outcome.rollback_error)

    invocations: tuple[Callable[[], DatabaseError], ...] = (
        lambda: raised(lambda: adapter.execute("select 1", [])),
        lambda: raised(lambda: adapter.execute_write("insert into gauge (v) values (%s)", [1])),
        failing_begin,
        failing_commit,
        failing_rollback,
    )
    reported = [invoke() for invoke in (*invocations, *invocations)]

    assert len({id(error) for error in reported}) == len(reported)
    assert {(error.category, error.native_code, error.message) for error in reported} == {
        ("uniqueViolation", "23505", "dup")
    }


def test_transaction_commits_and_reports_the_body_value() -> None:
    assert _adapter(_FakeConnection()).transaction(lambda _port: "kept") == Committed("kept")


def test_the_transaction_scoped_port_reports_the_boundarys_own_dialect() -> None:
    # The port a body holds spells the statements that boundary is about to run,
    # so it answers the dialect of the port that opened the boundary rather than
    # resolving one of its own.
    outcome = _adapter(_FakeConnection()).transaction(lambda port: port.dialect)
    assert outcome == Committed(PostgresAdapter.dialect)


def test_transaction_reports_a_boundary_that_never_began() -> None:
    # No attempt ran, so there is nothing to undo and nothing to re-execute; the
    # body is what proves it, by never running.
    connection = _FakeConnection(begin_error=errors.OperationalError("the connection is closed"))
    ran: list[str] = []
    outcome = _adapter(connection).transaction(lambda _port: ran.append("body"))
    assert isinstance(outcome, BeginFailed)
    assert _translated(outcome.error).category is None
    assert ran == []
    assert connection.rollbacks == 0


def test_a_boundary_asked_for_no_isolation_sends_no_level_statement() -> None:
    # The default path is the whole default path: absence asks for nothing, so
    # the connection keeps whatever it already defaults to and the boundary costs
    # exactly the statements the body ran.
    connection = _FakeConnection()
    assert _adapter(connection).transaction(lambda _port: "kept") == Committed("kept")
    assert connection.executed == []


@pytest.mark.parametrize("level", sorted(ISOLATION_LEVELS))
def test_each_portable_level_opens_the_boundary_at_its_postgres_spelling(level: str) -> None:
    # Postgres accepts a level only as the transaction's first statement, which
    # is what makes this part of opening the boundary rather than of the work
    # inside it. What it is asked for is Postgres' OWN name for the portable
    # level, delimited as the setting's value, so the whole statement is one
    # level and never a second transaction mode or a second statement.
    requested = isolation_level(level)
    connection = _FakeConnection()
    outcome = _adapter(connection).transaction(
        lambda port: port.execute("select 1", []), isolation=requested
    )
    assert isinstance(outcome, Committed)
    assert _sent(connection) == [
        f"set local transaction_isolation = '{isolation_spelling(requested)}'",
        "select 1",
    ]


def test_a_refused_isolation_reports_a_boundary_that_never_opened() -> None:
    # A boundary whose level statement the database refuses has begun and done
    # nothing. The body never runs, the empty transaction is undone here rather
    # than by the caller, and the outcome is the one for a boundary that never
    # opened — nothing to retry, nothing to undo.
    #
    # What separates this outcome from every other unhappy one is that the port
    # is still usable, so the proof runs to a NEXT boundary on the same adapter:
    # it begins, its body runs a statement through the port, and it commits. A
    # connection merely left unclosed would satisfy a weaker assertion while
    # carrying an abandoned transaction no later boundary could open through.
    connection = _FakeConnection(
        cursor_error=errors.InvalidParameterValue("invalid value for parameter")
    )
    adapter = _adapter(connection)
    ran: list[str] = []
    outcome = adapter.transaction(lambda _port: ran.append("body"), isolation="serializable")
    assert isinstance(outcome, BeginFailed)
    assert _translated(outcome.error).native_code == "22023"
    assert ran == []
    assert connection.rollbacks == 1
    assert not connection.closed

    connection.cursor_error = None
    assert adapter.transaction(lambda port: port.execute("select 1", [])) == Committed([])
    assert connection.begins == 2
    assert _sent(connection)[-1] == "select 1"


def test_a_connection_that_cannot_undo_a_refused_isolation_is_discarded() -> None:
    # The undo is the last thing this adapter can do about a boundary it could
    # not open as asked. When even that fails, what the connection would run next
    # is unknown, so it is dropped rather than handed back.
    connection = _FakeConnection(
        cursor_error=errors.InvalidParameterValue("invalid value for parameter"),
        rollback_error=errors.OperationalError("the connection is closed"),
    )
    outcome = _adapter(connection).transaction(lambda _port: None, isolation="serializable")
    assert isinstance(outcome, BeginFailed)
    assert _translated(outcome.error).native_code == "22023"
    assert connection.closed


def test_transaction_reports_a_commit_time_driver_error_as_rolled_back() -> None:
    outcome = _adapter(
        _FakeConnection(commit_error=errors.SerializationFailure("serialize"))
    ).transaction(lambda _port: None)
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CommitFailed)
    # A serialization failure at commit (40001) shares the retriable deadlock category.
    assert _translated(trigger.error).category == "deadlock"
    assert _translated(trigger.error).native_code == "40001"


def test_a_reported_boundary_failure_keeps_the_driver_exception_as_its_cause() -> None:
    # A statement failure is raised `from` the psycopg exception it classified,
    # so a caller reading the traceback sees the driver's own words. A boundary
    # failure is reported rather than raised, and chaining it here is what keeps
    # that reading the same for both.
    driver_error = errors.SerializationFailure("serialize")
    outcome = _adapter(_FakeConnection(commit_error=driver_error)).transaction(lambda _port: None)
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CommitFailed)
    assert trigger.error.__cause__ is driver_error


def test_transaction_reports_a_non_driver_body_error_unchanged() -> None:
    class _Boom(Exception):
        pass

    raised_by_the_body = _Boom()

    def body(_port: object) -> None:
        raise raised_by_the_body

    assert _adapter(_FakeConnection()).transaction(body) == RolledBack(
        CallbackRaised(raised_by_the_body)
    )


def test_transaction_reports_a_body_raised_driver_error_unchanged() -> None:
    # m-db-port scopes translation to the errors the PORT makes; an exception the
    # caller's own body raised is not one of them, however psycopg-shaped it is.
    # The identical object reaches the caller, so a body-authored deadlock-class
    # exception cannot read as a retriable DatabaseError to m-auto-retry and have
    # the body replayed over a failure the database never reported.
    raised_by_the_body = errors.DeadlockDetected("the caller's own deadlock")

    def body(_port: object) -> None:
        raise raised_by_the_body

    outcome = _adapter(_FakeConnection()).transaction(body)
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CallbackRaised)
    assert trigger.error is raised_by_the_body


def test_transaction_reports_a_rollback_failure_beside_the_body_error_that_triggered_it() -> None:
    # The other side of the same boundary: the rollback the body triggered is the
    # port's own work, so ITS driver failure classifies as one -- and neither
    # error replaces the other, because a caller needs the trigger to know what
    # went wrong and the rollback failure to know that undoing it did not happen.
    raised_by_the_body = errors.DeadlockDetected("the caller's own deadlock")

    def body(_port: object) -> None:
        raise raised_by_the_body

    connection = _FakeConnection(rollback_error=errors.UniqueViolation("dup"))
    outcome = _adapter(connection).transaction(body)
    assert isinstance(outcome, RollbackFailed)
    assert outcome.trigger == CallbackRaised(raised_by_the_body)
    assert _translated(outcome.rollback_error).violates_unique_index
    assert _translated(outcome.rollback_error).native_code == "23505"
    # The transaction's outcome is unknown, so the connection is not reused.
    assert connection.closed


def test_transaction_separates_a_rollback_failure_raised_as_the_bodys_own_object() -> None:
    # The same two failures over a driver that caches ONE exception object for
    # every failure -- the input m-db-port already requires an adapter to
    # withstand. Body and rollback then fail with the identical object, so
    # neither its type nor its identity says which occurrence is which: an
    # adapter reading identity alone reports the rollback's failure as the
    # body's, which m-auto-retry would read as a caller error the port never
    # made. Where each failure occurred is what separates them, so the body's
    # object stays the trigger and the boundary's own rollback classifies.
    reused = errors.UniqueViolation("dup")

    def body(_port: object) -> None:
        raise reused

    outcome = _adapter(_FakeConnection(rollback_error=reused)).transaction(body)
    assert isinstance(outcome, RollbackFailed)
    assert outcome.trigger == CallbackRaised(reused)
    assert outcome.rollback_error is not reused
    assert _translated(outcome.rollback_error).violates_unique_index


def test_transaction_reports_a_rollback_failure_after_a_failed_commit() -> None:
    # Both halves of the boundary failed: the commit that ended the work, and the
    # rollback that could not undo it. The commit failure stays the trigger --
    # replacing it with the rollback's would lose why the transaction ended.
    connection = _FakeConnection(
        commit_error=errors.SerializationFailure("serialize"),
        rollback_error=errors.OperationalError("the connection is lost"),
    )
    outcome = _adapter(connection).transaction(lambda _port: None)
    assert isinstance(outcome, RollbackFailed)
    trigger = outcome.trigger
    assert isinstance(trigger, CommitFailed)
    assert _translated(trigger.error).native_code == "40001"
    assert _translated(outcome.rollback_error).category is None
    assert connection.closed


def test_transaction_reports_a_body_raised_base_exception_unchanged() -> None:
    # Reporting the body's failure must not change what it IS: a base-level
    # exception stays base-level and stays the same object, so a cancellation or
    # interrupt is neither translated nor made catchable as an ordinary error on
    # the way out.
    raised_by_the_body = KeyboardInterrupt()

    def body(_port: object) -> None:
        raise raised_by_the_body

    outcome = _adapter(_FakeConnection()).transaction(body)
    assert isinstance(outcome, RolledBack)
    trigger = outcome.trigger
    assert isinstance(trigger, CallbackRaised)
    assert trigger.error is raised_by_the_body
