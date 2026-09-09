"""The Postgres runtime's resource lifetimes, over a fake native pool (Docker-free).

Three things live here and nowhere else, so they are proven here rather than
against a container: what readiness establishes before a handle is published,
what one acquisition is allowed to do, and what relinquishing one establishes.
The failures that matter most are the ones a real server will not produce on
demand — a checkout that hands over a connection in a transaction, a physical
close that raises, a native return that raises after it may already have handed
the connection to somebody else — so the native pool and its connections are
fakes with those failures scripted, and the live proofs are in the provider lane.

The pins are deliberately pessimistic about cleanup. A cleanup result says what
was ESTABLISHED, so the interesting assertions are the ones that refuse to claim
more than that: a failed disposal does not fall back to returning a suspect
connection, a failed handoff is not retried, and a completed handoff is never
inspected afterwards.
"""

from __future__ import annotations

from collections.abc import Sequence
from time import monotonic
from typing import Any, cast

import psycopg
import psycopg_pool
import pytest
from psycopg.pq import TransactionStatus

from parallax.core.base import INFINITY, PresentDocument
from parallax.core.db_port import (
    ConnectionAcquisitionError,
    DatabaseStartupError,
    Invalidated,
    Returned,
    Unrelinquished,
)
from parallax.postgres import OnDemandOptions, PoolOptions
from parallax.postgres._connection import ConnectionPreparation, IncompatibleSessionError
from parallax.postgres._context import PostgresConnectionContext, relinquish
from parallax.postgres._runtime import PROBE_SQL, PostgresRuntime, open_runtime

_PROBE_ROW = {"ready": 1, "temporal_bound": INFINITY, "document": {"ready": True}}


class _Column:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeCursor:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection
        self.description: list[_Column] | None = None
        self.rowcount = 0

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return

    def execute(self, sql: object, binds: Sequence[object] | None = None) -> None:
        del binds
        text = sql.decode() if isinstance(sql, bytes) else str(sql)
        self._connection.statements.append(text)
        if self._connection.execute_error is not None:
            raise self._connection.execute_error
        rows = self._connection.rows
        self.description = [_Column(name) for name in rows[0]] if rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return [tuple(row.values()) for row in self._connection.rows]


class _FakePgConn:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    @property
    def transaction_status(self) -> int:
        if self._connection.status_error is not None:
            raise self._connection.status_error
        return int(self._connection.status)


class _FakeConnection:
    """One physical connection: the state cleanup inspects and the failures it meets."""

    def __init__(
        self,
        *,
        rows: list[dict[str, object]] | None = None,
        status: TransactionStatus = TransactionStatus.IDLE,
        status_error: Exception | None = None,
        close_error: Exception | None = None,
        execute_error: Exception | None = None,
    ) -> None:
        self.rows = rows if rows is not None else [dict(_PROBE_ROW)]
        self.status = status
        self.status_error = status_error
        self.close_error = close_error
        self.execute_error = execute_error
        self.statements: list[str] = []
        self.closes = 0
        self.pgconn = _FakePgConn(self)

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def close(self) -> None:
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error


class _FakePool:
    """The native pool, scripted at the four calls the runtime makes of it."""

    def __init__(
        self,
        *connections: _FakeConnection,
        checkout_error: Exception | None = None,
        putconn_error: Exception | None = None,
        wait_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self._connections = list(connections) or [_FakeConnection()]
        self.checkout_error = checkout_error
        self.putconn_error = putconn_error
        self.wait_error = wait_error
        self.close_error = close_error
        self.checkouts: list[float | None] = []
        self.returned: list[_FakeConnection] = []
        self.waits: list[float] = []
        self.closes = 0
        self.late_by: float = 0.0

    def wait(self, timeout: float = 30.0) -> None:
        self.waits.append(timeout)
        if self.wait_error is not None:
            raise self.wait_error

    def getconn(self, timeout: float | None = None) -> _FakeConnection:
        self.checkouts.append(timeout)
        if self.checkout_error is not None:
            raise self.checkout_error
        return self._connections[min(len(self.checkouts), len(self._connections)) - 1]

    def putconn(self, conn: _FakeConnection) -> None:
        if self.putconn_error is not None:
            raise self.putconn_error
        self.returned.append(conn)

    def close(self) -> None:
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error


def _pool(*connections: _FakeConnection, **kwargs: Any) -> Any:
    return cast("Any", _FakePool(*connections, **kwargs))


def _runtime(pool: Any, options: Any = None) -> PostgresRuntime:
    return PostgresRuntime(pool, options if options is not None else PoolOptions(), _preparation())


def _preparation() -> ConnectionPreparation:
    return ConnectionPreparation()


def _context(pool: Any, *, deadline: float | None = None, admit: Any = None) -> Any:
    runtime = _runtime(pool)
    return PostgresConnectionContext(
        pool,
        admit if admit is not None else runtime._admit,  # pyright: ignore[reportPrivateUsage]
        deadline if deadline is not None else monotonic() + 5.0,
        _preparation(),
    )


# --------------------------------------------------------------------------- #
# Readiness: only a runtime that has proved it can execute is returned.        #
# --------------------------------------------------------------------------- #


def _opened(monkeypatch: pytest.MonkeyPatch, pool: Any) -> Any:
    """Make ``open_runtime`` build ``pool`` rather than a native one."""
    from parallax.postgres import _runtime as runtime_module

    def build(*_args: object, **_kwargs: object) -> Any:
        return pool

    monkeypatch.setattr(runtime_module, "_build_pool", build)
    return pool


def test_startup_probes_a_real_connection_and_gives_it_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Waiting for a minimum is not readiness: it says a connection exists rather
    # than that a statement works. The probe reads an integer, a neutral
    # unbounded instant, and a structured document through the same initialized
    # execution an application gets.
    pool = _opened(monkeypatch, _pool())
    runtime = open_runtime("", PoolOptions(min_size=1), 5)

    assert pool.waits and pool.checkouts
    assert pool.returned and pool.returned[0].statements == [PROBE_SQL]
    assert runtime.pool_metrics is None


def test_a_zero_minimum_and_on_demand_wait_for_nothing_and_still_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Neither retains capacity, so a native wait would either return having
    # proved nothing or establish a connection of its own and throw it away.
    for options in (PoolOptions(min_size=0), OnDemandOptions()):
        pool = _opened(monkeypatch, _pool())
        open_runtime("", options, 5)
        assert pool.waits == []
        assert len(pool.checkouts) == 1
        assert pool.returned


def test_a_pool_that_will_not_open_fails_startup_at_the_open_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `open=False` then an explicit open, because the driver's implicit opening
    # is a deprecated default whose behavior is documented to change — so the
    # open is a phase of readiness with a failure of its own.
    class _Refusing(_FakePool):
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            super().__init__()

        check_connection = staticmethod(psycopg_pool.ConnectionPool.check_connection)

        def open(self) -> None:
            raise psycopg_pool.PoolTimeout("the pool would not open")

    monkeypatch.setattr(psycopg_pool, "ConnectionPool", _Refusing)

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(), 5)

    assert failed.value.phase == "open"
    assert isinstance(failed.value.__cause__, psycopg_pool.PoolTimeout)


def test_a_minimum_that_is_not_reached_fails_at_its_own_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _opened(monkeypatch, _pool(wait_error=psycopg_pool.PoolTimeout("not filled")))

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=2), 5)

    assert failed.value.phase == "minimum_ready"
    assert pool.closes == 1


def test_a_configuration_every_connection_is_refused_under_is_named_rather_than_timed_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Filling happens on the pool's own background path, where an initialization
    # refusal is retried and logged where the waiting caller never sees it. A
    # bare "timed out" names nothing an operator can fix.
    from parallax.postgres import _runtime as runtime_module

    preparation = _preparation()
    refusal = IncompatibleSessionError("this connection's client encoding is 'LATIN1'")
    preparation.last_refusal = refusal
    pool = _pool(wait_error=psycopg_pool.PoolTimeout("not filled"))

    def build(*_args: object, **_kwargs: object) -> Any:
        return pool

    monkeypatch.setattr(runtime_module, "_build_pool", build)
    monkeypatch.setattr(runtime_module, "ConnectionPreparation", lambda: preparation)

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=1), 5)

    assert failed.value.phase == "minimum_ready"
    assert failed.value.__cause__ is refusal
    assert "usable" in str(failed.value)


def test_a_startup_acquisition_that_fails_carries_its_phase_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _opened(
        monkeypatch, _pool(checkout_error=psycopg_pool.PoolTimeout("no connection available"))
    )

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=0), 5)

    assert failed.value.phase == "acquire"
    assert isinstance(failed.value.__cause__, ConnectionAcquisitionError)
    assert pool.closes == 1


@pytest.mark.parametrize(
    "row",
    [
        {"ready": 0, "temporal_bound": INFINITY, "document": {"ready": True}},
        {"ready": 1, "temporal_bound": "2026-01-01", "document": {"ready": True}},
        {"ready": 1, "temporal_bound": INFINITY, "document": "not a document"},
    ],
)
def test_a_probe_that_does_not_read_back_what_it_asked_for_fails_startup(
    monkeypatch: pytest.MonkeyPatch, row: dict[str, object]
) -> None:
    connection = _FakeConnection(rows=[row])
    pool = _opened(monkeypatch, _pool(connection))

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=0), 5)

    assert failed.value.phase == "probe"
    # The probe scope is relinquished on the way out rather than leaked.
    assert pool.returned == [connection]
    assert pool.closes == 1


def test_a_probe_scope_that_cannot_be_relinquished_fails_startup_at_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A successful probe followed by an unconfirmed relinquishment is not a
    # ready runtime: the connection's fate is unknown and nothing else will
    # revisit it.
    pool = _opened(monkeypatch, _pool(putconn_error=RuntimeError("the return failed")))

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=0), 5)

    assert failed.value.phase == "release"
    assert isinstance(failed.value.cleanup_result, Unrelinquished)
    assert failed.value.__cause__ is None
    assert pool.closes == 1


def test_readiness_shares_one_budget_that_is_never_restarted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A budget that stops the next phase from starting: it cannot interrupt a
    # native call in flight, and it does not begin a phase it cannot finish.
    from parallax.postgres import _runtime as runtime_module

    clock = iter([0.0, 0.0, 0.5, 99.0, 99.0, 99.0, 99.0])
    monkeypatch.setattr(runtime_module, "monotonic", lambda: next(clock))
    _opened(monkeypatch, _pool())

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=1), 5)

    assert failed.value.phase in {"acquire", "minimum_ready"}


# --------------------------------------------------------------------------- #
# Acquisition: what a checkout is allowed to become.                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("native", "reason"),
    [
        (psycopg_pool.PoolTimeout("waited"), "timeout"),
        (psycopg_pool.TooManyRequests("queued"), "queue_rejected"),
        (psycopg_pool.PoolClosed("closed"), "closed"),
        (psycopg.OperationalError("could not connect"), "preparation_failed"),
    ],
)
def test_every_native_checkout_failure_maps_to_its_own_reason(
    native: Exception, reason: str
) -> None:
    resource = _context(_pool(checkout_error=native))

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == reason
    assert refused.value.__cause__ is native
    # Nothing was taken, so there is nothing to have cleaned up.
    assert resource.cleanup_result is None


def test_an_expired_budget_refuses_before_asking_the_pool_for_anything() -> None:
    pool = _pool()
    resource = _context(pool, deadline=monotonic() - 1.0)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert pool.checkouts == []


def test_a_timeout_names_the_initialization_refusal_on_record() -> None:
    # The pool retries an initialization refusal in the background, so the
    # waiting caller would otherwise get a bare timeout naming nothing to fix.
    preparation = _preparation()
    refusal = IncompatibleSessionError("this connection's DateStyle is 'German'")
    preparation.last_refusal = refusal
    pool = _pool(checkout_error=psycopg_pool.PoolTimeout("waited"))
    runtime = _runtime(pool)
    resource = PostgresConnectionContext(
        pool,
        runtime._admit,  # pyright: ignore[reportPrivateUsage]
        monotonic() + 5.0,
        preparation,
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert refused.value.__cause__ is refusal


def test_a_successful_initialization_clears_the_refusal_on_record() -> None:
    preparation = _preparation()
    preparation.last_refusal = IncompatibleSessionError("earlier")
    preparation(cast("Any", _Initializable()))
    assert preparation.last_refusal is None


class _Initializable:
    """A connection whose initialization succeeds: the two settings and the loaders."""

    def __init__(self) -> None:
        self.info = _Info()
        self.adapters = _Adapters()


class _Info:
    encoding = "utf-8"

    def parameter_status(self, name: str) -> str | None:
        return "ISO, MDY" if name == "DateStyle" else None


class _Adapters:
    def __init__(self) -> None:
        self.registered: list[str] = []

    def register_loader(self, name: str, loader: object) -> None:
        del loader
        self.registered.append(name)


def test_the_remaining_budget_is_what_the_native_checkout_is_given() -> None:
    pool = _pool()
    _context(pool, deadline=monotonic() + 2.0).__enter__()
    (given,) = pool.checkouts
    assert given is not None and 0.0 < given <= 2.0


def test_a_checkout_that_hands_over_a_connection_in_a_transaction_is_refused() -> None:
    # No modeled SQL runs on it and no unknown transaction is rolled back to
    # make it usable: an adapter invariant this broken is reported.
    connection = _FakeConnection(status=TransactionStatus.INTRANS)
    pool = _pool(connection)
    resource = _context(pool)

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "preparation_failed"
    assert connection.statements == []
    # The partial ownership is cleaned up, and a connection in this state is
    # disposed of rather than offered to the next caller.
    assert isinstance(resource.cleanup_result, Invalidated)
    assert connection.closes == 1


def test_a_late_native_success_is_relinquished_rather_than_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The caller has already been waiting past what it asked for; its own
    # timeout handling is a better answer than work starting after the budget.
    # The budget is live when the checkout starts and spent when it returns,
    # which is the race a cooperative deadline can only lose.
    from parallax.postgres import _runtime as runtime_module

    connection = _FakeConnection()
    pool = _pool(connection)
    runtime = _runtime(pool)
    monkeypatch.setattr(runtime_module, "monotonic", lambda: 1e18)
    resource = PostgresConnectionContext(
        pool,
        runtime._admit,  # pyright: ignore[reportPrivateUsage]
        monotonic() + 5.0,
        _preparation(),
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        resource.__enter__()

    assert refused.value.reason == "timeout"
    assert connection.statements == []
    assert resource.cleanup_result == Returned()
    assert pool.returned == [connection]


def test_a_context_is_entered_exactly_once_and_a_failed_entry_spends_it() -> None:
    pool = _pool()
    resource = _context(pool)
    with resource, pytest.raises(RuntimeError):
        resource.__enter__()
    with pytest.raises(RuntimeError):
        resource.__enter__()

    failed = _context(_pool(checkout_error=psycopg_pool.PoolClosed("closed")))
    with pytest.raises(ConnectionAcquisitionError):
        failed.__enter__()
    with pytest.raises(RuntimeError):
        failed.__enter__()


def test_leaving_a_scope_revokes_the_execution_it_yielded() -> None:
    # Enforced by clearing the native reference, so a reference kept past the
    # exit executes nothing and — more importantly — RETAINS nothing.
    connection = _FakeConnection()
    resource = _context(_pool(connection))
    with resource as scoped:
        scoped.execute("select 1", [])
    with pytest.raises(RuntimeError, match="scope has ended"):
        scoped.execute("select 1", [])
    assert connection.statements == ["select 1"]


def test_each_acquisition_yields_fresh_execution_access() -> None:
    pool = _pool()
    first = _context(pool)
    second = _context(pool)
    with first as one, second as two:
        assert one is not two


# --------------------------------------------------------------------------- #
# Relinquishment: what a cleanup result is allowed to claim.                   #
# --------------------------------------------------------------------------- #


def test_an_idle_untrusted_free_connection_is_offered_for_reuse() -> None:
    connection = _FakeConnection()
    pool = _pool(connection)

    result = relinquish(pool, cast("Any", connection), suspect=False)

    assert result == Returned()
    assert connection.closes == 0
    assert pool.returned == [connection]


def test_an_execution_that_declared_the_connection_suspect_disposes_of_it_first() -> None:
    # Disposal BEFORE the handoff, and the handoff still happens: disposal alone
    # would leak the capacity, and a handoff alone would offer a connection
    # nothing may reuse.
    connection = _FakeConnection()
    pool = _pool(connection)

    result = relinquish(pool, cast("Any", connection), suspect=True)

    assert isinstance(result, Invalidated)
    assert [(issue.phase, issue.code) for issue in result.issues] == [("inspect", "suspect")]
    assert connection.closes == 1
    assert pool.returned == [connection]


def test_a_connection_whose_state_cannot_be_read_is_disposed_of() -> None:
    connection = _FakeConnection(status_error=RuntimeError("the state is gone"))
    pool = _pool(connection)

    result = relinquish(pool, cast("Any", connection), suspect=False)

    assert isinstance(result, Invalidated)
    assert [issue.code for issue in result.issues] == ["state-unreadable"]
    assert connection.closes == 1


def test_a_connection_that_is_not_idle_is_disposed_of_rather_than_repaired() -> None:
    connection = _FakeConnection(status=TransactionStatus.INERROR)
    pool = _pool(connection)

    result = relinquish(pool, cast("Any", connection), suspect=False)

    assert isinstance(result, Invalidated)
    assert [issue.code for issue in result.issues] == ["not-idle"]
    assert connection.statements == []


def test_a_failed_disposal_does_not_fall_back_to_returning_a_suspect_connection() -> None:
    # Balancing the accounting is not worth offering the next caller a session
    # nothing can vouch for, and a closed flag after a failed close establishes
    # no disposal.
    connection = _FakeConnection(close_error=RuntimeError("close failed"))
    pool = _pool(connection)

    result = relinquish(pool, cast("Any", connection), suspect=True)

    assert isinstance(result, Unrelinquished)
    assert [issue.code for issue in result.issues] == ["suspect", "close-failed"]
    assert pool.returned == []


def test_a_failed_handoff_is_neither_retried_nor_followed_by_a_close() -> None:
    # A native return that raised may still have handed the connection to
    # another caller, so retrying it or closing afterwards risks destroying
    # somebody else's session.
    connection = _FakeConnection()
    pool = _pool(connection, putconn_error=RuntimeError("the return failed"))

    result = relinquish(pool, cast("Any", connection), suspect=False)

    assert isinstance(result, Unrelinquished)
    assert [(issue.phase, issue.code) for issue in result.issues] == [("return", "handoff-failed")]
    assert connection.closes == 0


def test_a_cleanup_issue_carries_a_detached_diagnostic_and_no_live_object() -> None:
    connection = _FakeConnection(status=TransactionStatus.INTRANS)
    result = relinquish(_pool(connection), cast("Any", connection), suspect=False)

    (issue,) = result.issues
    assert isinstance(issue.diagnostic.message, str)
    assert issue.diagnostic.qualified_type.endswith("_Condition")
    assert not hasattr(issue.diagnostic, "__traceback__")


def test_an_unrelinquished_result_must_name_at_least_one_issue() -> None:
    with pytest.raises(ValueError, match="at least one cleanup issue"):
        Unrelinquished(())


# --------------------------------------------------------------------------- #
# Admission and shutdown.                                                      #
# --------------------------------------------------------------------------- #


def test_close_is_idempotent_and_permanent() -> None:
    pool = _pool()
    runtime = _runtime(pool)

    runtime.close()
    runtime.close()

    assert pool.closes == 1
    with pytest.raises(ConnectionAcquisitionError) as refused:
        runtime.connection().__enter__()
    assert refused.value.reason == "closed"


def test_a_scope_admitted_before_a_close_may_still_finish() -> None:
    # Admission is decided once, immediately before the connection is handed
    # over: later work in an admitted scope uses what it was given, including
    # statements it has not issued yet.
    connection = _FakeConnection()
    pool = _pool(connection)
    runtime = _runtime(pool)

    with runtime.connection() as scoped:
        runtime.close()
        scoped.execute("select 1", [])

    assert connection.statements == ["select 1"]
    assert pool.returned == [connection]


def test_a_native_close_problem_is_reported_rather_than_raised() -> None:
    # Close is what a caller runs while unwinding; a handle that refused to
    # close would leave them nothing better to do.
    runtime = _runtime(_pool(close_error=RuntimeError("the pool would not close")))
    runtime.close()


def test_the_ordinary_acquisition_budget_comes_from_the_configured_timeout() -> None:
    pool = _pool()
    runtime = _runtime(pool, PoolOptions(acquire_timeout=3.0))
    with runtime.connection():
        pass
    (given,) = pool.checkouts
    assert given is not None and 0.0 < given <= 3.0


def test_close_holds_no_lock_across_a_checkout() -> None:
    # Admission stops under the lock and the native close runs outside it, so an
    # acquisition that blocks cannot block a close.
    pool = _pool()
    runtime = _runtime(pool)
    resource = runtime.connection()
    with resource:
        runtime.close()
    assert pool.closes == 1


def test_a_runtime_answers_the_dialect_its_statements_are_spelled_in() -> None:
    assert _runtime(_pool()).dialect.name == "postgres"


def test_the_on_demand_policy_selects_the_native_null_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Which record is supplied selects which behavior the runtime has, so there
    # is no mode flag beside the settings to disagree with them.
    from parallax.postgres import _runtime as runtime_module

    built: list[str] = []

    class _Null(_FakePool):
        def __init__(self, *_args: object, **kwargs: object) -> None:
            super().__init__()
            built.append(type(self).__name__)
            assert "min_size" not in kwargs
            assert "max_idle" not in kwargs

        check_connection = staticmethod(psycopg_pool.ConnectionPool.check_connection)

        def open(self) -> None:
            return

    monkeypatch.setattr(psycopg_pool, "NullConnectionPool", _Null)
    runtime_module._build_pool(  # pyright: ignore[reportPrivateUsage]
        "", OnDemandOptions(), 5, _preparation()
    )
    assert built == ["_Null"]


def test_a_probe_that_answers_more_than_one_row_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(rows=[dict(_PROBE_ROW), dict(_PROBE_ROW)])
    _opened(monkeypatch, _pool(connection))

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=0), 5)

    assert failed.value.phase == "probe"


def test_a_budget_already_spent_refuses_to_begin_the_next_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from parallax.postgres import _runtime as runtime_module

    _opened(monkeypatch, _pool())
    monkeypatch.setattr(runtime_module, "monotonic", lambda: 1e18)

    with pytest.raises(DatabaseStartupError) as failed:
        open_runtime("", PoolOptions(min_size=0), 5)

    assert failed.value.phase == "acquire"


def test_configuration_opens_the_runtime_it_describes(monkeypatch: pytest.MonkeyPatch) -> None:
    from parallax.postgres import adapter as adapter_module

    opened: list[tuple[str, object, object]] = []

    def open_runtime_stub(conninfo: str, options: object, prepare_threshold: object) -> object:
        opened.append((conninfo, options, prepare_threshold))
        return "the runtime"

    monkeypatch.setattr(adapter_module, "open_runtime", open_runtime_stub)
    configured = adapter_module.PostgresAdapter("host=localhost", prepare_threshold=None)

    assert configured.open() == "the runtime"
    assert opened == [("host=localhost", configured.pool, None)]


def test_leaving_a_context_that_was_never_entered_does_nothing() -> None:
    # Total on every exit: a context a caller built and abandoned has taken
    # nothing, so leaving it relinquishes nothing and reports nothing.
    pool = _pool()
    resource = _context(pool)
    resource.__exit__(None, None, None)
    assert (pool.returned, resource.cleanup_result) == ([], None)


def test_a_document_read_folds_its_adjacent_cells_on_the_scoped_execution() -> None:
    # The document-read projection is the read path's, and it runs on the scoped
    # execution rather than anywhere a pool can see.
    connection = _FakeConnection(rows=[{"id": 1, "doc_present": True, "doc": {"a": 1}}])
    resource = _context(_pool(connection))
    with resource as scoped:
        rows = scoped.execute("select id, doc_present, doc from t", [], [(1, 2)])
    (row,) = rows
    assert row["id"] == 1
    assert row["doc"] == PresentDocument({"a": 1})
