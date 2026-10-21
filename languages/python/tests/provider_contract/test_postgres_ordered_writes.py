"""The PostgreSQL ordered write operation against a real server
(`database-provider-test-contract`, `m-db-port` Ordered write transport).

The acquired facade does not advertise the operation yet, so each proof reaches
it on a facade it acquired through this run's own runtime. What a fake pipeline
cannot establish is here: that psycopg really pairs each result with the
statement that produced it, that a server error really aborts what follows it,
that an interruption reports no more than it established, and that what an
interrupted operation leaves behind never returns to the pool.
"""

from __future__ import annotations

import select
import signal
import threading
import time
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import psycopg
import pytest

import parallax.postgres._connection as connection_module
from parallax.conformance import engine, provision
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    CallbackRaised,
    CanonicalWriteStatement,
    Committed,
    ConnectionContext,
    Invalidated,
    OrderedWriteResult,
    OrderedWriteResultComplete,
    OrderedWriteResultInterrupted,
    PipelineStatement,
    RollbackFailed,
    RolledBack,
    StatementFailed,
    StatementNotExecuted,
)
from parallax.postgres import PoolOptions
from parallax.postgres._connection import PostgresConnection

_OPENED = datetime(2024, 1, 1, tzinfo=UTC)
_CORRECTED = datetime(2024, 4, 1, tzinfo=UTC)
_HEAD_END = datetime(2024, 6, 1, tzinfo=UTC)
_NOW = datetime(2024, 7, 1, tzinfo=UTC)
_WAITING = "select wait_event_type from pg_stat_activity where pid = %s"
_PID = "select pg_backend_pid() as pid"


@dataclass(frozen=True, slots=True)
class _Statement:
    sql: str
    binds: tuple[object, ...]


def _close(table: str, key: int, opened: datetime = _OPENED) -> _Statement:
    return _Statement(
        f"update {table} set out_z = ? where id = ? and thru_z = ? and out_z = ? and in_z = ?",
        (_NOW, key, INFINITY, INFINITY, opened),
    )


def _guard(table: str, key: int, opened: datetime = _OPENED) -> _Statement:
    return _Statement(
        f"update {table} set in_z = in_z where id = ? and thru_z = ? and out_z = ? and in_z = ?",
        (key, INFINITY, INFINITY, opened),
    )


def _revision(key: int, amount: Decimal) -> _Statement:
    return _Statement(
        "update coverage set amount = ? where id = ? and thru_z = ? and out_z = ?",
        (amount, key, INFINITY, INFINITY),
    )


def _removal(table: str, key: int) -> _Statement:
    return _Statement(
        f"delete from {table} where id = ? and thru_z = ? and out_z = ?", (key, INFINITY, INFINITY)
    )


# Coverage 10's head ends where its tail begins; extending it to the open bound
# collides with the tail's own key.
_COLLIDING = _Statement(
    "update coverage set thru_z = ? where id = ? and thru_z = ? and out_z = ?",
    (INFINITY, 10, _HEAD_END, INFINITY),
)


def _seeded(profile_run: Any) -> None:
    case = load_case(default_cases_dir() / "m-db-error-010-unique-violation-temporal-pk.yaml")
    profile_run.reset(
        engine.load_case_metamodel(case), provision.load_fixtures(str(case.document["model"]))
    )


def _ordered(
    facade: object,
) -> Callable[[Sequence[CanonicalWriteStatement]], OrderedWriteResult]:
    assert isinstance(facade, PostgresConnection)
    return facade._ordered_writes  # pyright: ignore[reportPrivateUsage] - the operation is qualified here before the facade advertises it


def _runtime(profile_run: Any, **options: Any) -> Any:
    return profile_run.configured(pool=PoolOptions(min_size=1, max_size=1), **options).open()


def _acquired(runtime: Any) -> ConnectionContext:
    return runtime.login_execution().new_context()


def _pid(connection: Any) -> int:
    (row,) = connection.execute(_PID, [])
    return int(row[0])


def _state(profile_run: Any) -> list[tuple[object, ...]]:
    return [
        *profile_run.port.execute(
            "select 'policy', id, out_z from policy order by id, thru_z, out_z", []
        ),
        *profile_run.port.execute(
            "select 'coverage', id, amount from coverage order by id, thru_z, out_z", []
        ),
        *profile_run.port.execute(
            "select 'claim', id, in_z from claim order by id, thru_z, out_z", []
        ),
    ]


def _raising(result: OrderedWriteResult) -> None:
    """Fail the body the way execution does with a result that did not succeed."""
    if isinstance(result, OrderedWriteResultInterrupted):
        raise result.error
    for outcome in result.outcomes:
        if isinstance(outcome, StatementFailed):
            raise outcome.error


@contextmanager
def _locked_claim(profile_run: Any) -> Generator[None]:
    """Hold claim 1000 under another session's row lock for the block's duration."""
    holder = profile_run.control(autocommit=False)
    try:
        holder.execute("select id from claim where id = %s for update", [1000])
        yield
    finally:
        holder.close()


def _when_waiting(profile_run: Any, pid: int, act: Callable[[Any, int], None]) -> threading.Thread:
    """Run ``act`` from another session once ``pid`` waits on a lock."""
    watcher = profile_run.control()

    def watch() -> None:
        try:
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                rows = watcher.execute(_WAITING, [pid])
                if rows and rows[0][0] == "Lock":
                    act(watcher, pid)
                    return
                time.sleep(0.01)
        finally:
            watcher.close()

    thread = threading.Thread(target=watch)
    thread.start()
    return thread


@pytest.mark.adapter_smoke
def test_each_statement_answers_its_own_count_across_kinds_and_tables(profile_run: Any) -> None:
    _seeded(profile_run)
    statements = (
        _close("policy", 1),
        _guard("claim", 1000),
        _revision(20, Decimal("350.00")),
        _removal("claim", 2000),
        _close("policy", 99),
        _guard("policy", 2, opened=_CORRECTED),
    )
    runtime = _runtime(profile_run)
    try:
        context = _acquired(runtime)
        with context as facade:

            def body(port: Any) -> OrderedWriteResult:
                result = _ordered(facade)(statements)
                native = cast("PostgresConnection", facade)._native()  # pyright: ignore[reportPrivateUsage] - the session's own pipeline state
                assert native.pgconn.pipeline_status == psycopg.pq.PipelineStatus.OFF
                assert port.execute("select count(*) from policy where out_z = %s", [_NOW]) == [
                    (1,)
                ]
                return result

            outcome = facade.transaction(body)
            saved = _ordered(facade)
        assert outcome == Committed(OrderedWriteResultComplete((1, 1, 1, 1, 0, 0)))
        assert context.cleanup_result is not None
        assert not isinstance(context.cleanup_result, Invalidated)
        with pytest.raises(RuntimeError, match="scope has ended"):
            saved(statements)
        state = _state(profile_run)
        assert ("policy", 1, _NOW) in state
        assert ("coverage", 20, Decimal("350.00")) in state
        assert [row for row in state if row[:2] == ("claim", 2000)] == []
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_server_error_fails_its_own_statement_and_confirms_what_it_kept_from_running(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    before = _state(profile_run)
    statements = (_close("policy", 1), _COLLIDING, _guard("claim", 1000), _removal("claim", 2000))
    runtime = _runtime(profile_run)
    try:
        results: list[OrderedWriteResult] = []
        with _acquired(runtime) as facade:
            first = _pid(facade)

            def body(_port: Any) -> None:
                results.append(_ordered(facade)(statements))
                results.append(_ordered(facade)(statements))
                _raising(results[0])

            outcome = facade.transaction(body)
        with _acquired(runtime) as reused:
            assert _pid(reused) == first

        assert isinstance(outcome, RolledBack)
        first_result, second_result = results
        assert isinstance(first_result, OrderedWriteResultComplete)
        count, failed, *rest = first_result.outcomes
        assert count == 1
        assert rest == [StatementNotExecuted(), StatementNotExecuted()]
        assert isinstance(failed, StatementFailed)
        error = failed.error
        assert isinstance(error, DatabaseError)
        assert error.violates_unique_index
        assert error.native_code == "23505"
        assert isinstance(error.__cause__, psycopg.errors.UniqueViolation)
        assert error.__cause__.__traceback__ is None
        assert cast("CallbackRaised", outcome.trigger).error is error
        # The whole transaction is aborted, so the repeat fails at its first
        # statement, with an error of its own.
        assert isinstance(second_result, OrderedWriteResultComplete)
        repeated = second_result.outcomes[0]
        assert isinstance(repeated, StatementFailed)
        assert repeated.error is not error
        assert cast("DatabaseError", repeated.error).native_code == "25P02"
        assert _state(profile_run) == before
    finally:
        runtime.close()


# The server sends its replies once its 8 KiB output buffer fills, which this
# many guards' replies do several times over. Holding the rest of the queue
# until they reach the socket makes them arrive while later statements queue,
# however the server's pace compares with the client's.
_ANSWERING_PREFIX = 1000


def _until_answered(pgconn: Any) -> None:
    """Block until the server has answered something on ``pgconn``."""
    deadline = time.monotonic() + 30.0
    while (remaining := deadline - time.monotonic()) > 0:
        sending = [pgconn.socket] if pgconn.flush() else []
        readable, _, _ = select.select([pgconn.socket], sending, [], remaining)
        if readable:
            return
    pytest.fail("the server answered none of the queued statements")


@pytest.mark.adapter_smoke
def test_counts_arriving_while_later_statements_queue_stay_with_their_own_statements(
    profile_run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seeded(profile_run)
    queued = [0]
    arrivals: list[int] = []
    cursor_type = connection_module._CountCursor  # pyright: ignore[reportPrivateUsage] - observing when psycopg hands each result over
    execute = cursor_type.execute
    check = cursor_type._check_results  # pyright: ignore[reportPrivateUsage] - the hook under observation

    def counting_execute(self: Any, *args: Any, **kwargs: Any) -> Any:
        executed = execute(self, *args, **kwargs)
        queued[0] += 1
        if queued[0] == _ANSWERING_PREFIX and not arrivals:
            _until_answered(self.connection.pgconn)
        return executed

    def observed_check(self: Any, results: Any) -> None:
        arrivals.append(queued[0])
        check(self, results)

    monkeypatch.setattr(cursor_type, "execute", counting_execute)
    monkeypatch.setattr(cursor_type, "_check_results", observed_check)
    statements = [_guard("claim", 1000)] * 1500 + [_close("policy", 99), _guard("claim", 1000)]
    runtime = _runtime(profile_run)
    try:
        with _acquired(runtime) as facade:
            outcome = facade.transaction(lambda _port: _ordered(facade)(statements))
    finally:
        runtime.close()

    assert outcome == Committed(OrderedWriteResultComplete((*([1] * 1500), 0, 1)))
    assert min(arrivals) < len(statements)


@pytest.mark.adapter_smoke
def test_an_unsent_suffix_is_only_what_never_reached_the_driver(profile_run: Any) -> None:
    _seeded(profile_run)
    before = _state(profile_run)
    unadaptable = _Statement(_close("policy", 2).sql, (object(), 2, INFINITY, INFINITY, _OPENED))
    statements = (_close("policy", 1), _guard("claim", 1000), unadaptable, _removal("claim", 2000))
    runtime = _runtime(profile_run)
    try:
        context = _acquired(runtime)
        seen: list[list[tuple[object, ...]]] = []
        with context as facade:

            def body(port: Any) -> None:
                result = _ordered(facade)(statements)
                assert isinstance(result, OrderedWriteResultInterrupted)
                assert (result.confirmed, result.unconfirmed_count, result.unsent_count) == (
                    (),
                    3,
                    1,
                )
                assert isinstance(result.error, DatabaseError)
                assert isinstance(result.error.__cause__, psycopg.ProgrammingError)
                # What was sent before the failure ran even though its outcome
                # was not established; what was never sent did not.
                seen.append(port.execute("select id, out_z from policy where id = 1", []))
                seen.append(port.execute("select id from claim where id = 2000", []))
                raise result.error

            outcome = facade.transaction(body)
            assert cast("PostgresConnection", facade).suspect
        assert isinstance(outcome, RolledBack)
        assert (1, _NOW) in seen[0]
        assert seen[1] == [(2000,)]
        assert isinstance(context.cleanup_result, Invalidated)
        assert [issue.code for issue in context.cleanup_result.issues] == ["suspect"]
        assert _state(profile_run) == before
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_terminated_session_interrupts_with_only_what_it_established(profile_run: Any) -> None:
    _seeded(profile_run)
    before = _state(profile_run)
    statements = (
        _close("policy", 1),
        _guard("claim", 1000),
        _close("policy", 2),
        _removal("claim", 2000),
    )
    runtime = _runtime(profile_run)
    try:
        context = _acquired(runtime)
        results: list[OrderedWriteResult] = []
        with _locked_claim(profile_run), context as facade:
            pid = _pid(facade)

            def body(port: Any) -> None:
                port.execute_write("set local lock_timeout = '10s'", [])
                watcher = _when_waiting(
                    profile_run,
                    pid,
                    lambda session, target: session.execute(
                        "select pg_terminate_backend(%s)", [target]
                    ),
                )
                try:
                    results.append(_ordered(facade)(statements))
                finally:
                    watcher.join()
                _raising(results[0])

            outcome = facade.transaction(body)
            assert cast("PostgresConnection", facade).suspect
        (result,) = results
        assert isinstance(result, OrderedWriteResultInterrupted)
        assert result.unsent_count == 0
        assert len(result.confirmed) + result.unconfirmed_count == len(statements)
        # Whether the close's count is confirmed depends on whether the session
        # ending reaches the driver as a result or as a failed read; neither may
        # be blamed on a statement.
        assert result.confirmed in ((), (1,))
        assert isinstance(result.error, DatabaseError)
        assert result.error.native_code in (None, "57P01")
        assert isinstance(outcome, RollbackFailed)
        assert isinstance(context.cleanup_result, Invalidated)
        assert _state(profile_run) == before
        with _acquired(runtime) as replacement:
            assert _pid(replacement) != pid
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_lock_timeout_fails_the_waiting_statement_as_its_own(profile_run: Any) -> None:
    _seeded(profile_run)
    statements = (_close("policy", 1), _guard("claim", 1000), _close("policy", 2))
    runtime = _runtime(profile_run)
    try:
        context = _acquired(runtime)
        with _locked_claim(profile_run), context as facade:

            def body(port: Any) -> OrderedWriteResult:
                port.execute_write("set local lock_timeout = '50ms'", [])
                return _ordered(facade)(statements)

            outcome = facade.transaction(body)
        assert isinstance(outcome, Committed)
        result = outcome.value
        assert isinstance(result, OrderedWriteResultComplete)
        count, failed, aborted = result.outcomes
        assert (count, aborted) == (1, StatementNotExecuted())
        assert isinstance(failed, StatementFailed)
        assert cast("DatabaseError", failed.error).native_code == "55P03"
        assert not isinstance(context.cleanup_result, Invalidated)
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_cancelled_statement_fails_as_its_own(profile_run: Any) -> None:
    _seeded(profile_run)
    statements = (_close("policy", 1), _guard("claim", 1000), _close("policy", 2))
    runtime = _runtime(profile_run)
    try:
        with _locked_claim(profile_run), _acquired(runtime) as facade:
            pid = _pid(facade)

            def body(port: Any) -> OrderedWriteResult:
                port.execute_write("set local lock_timeout = '10s'", [])
                watcher = _when_waiting(
                    profile_run,
                    pid,
                    lambda session, target: session.execute(
                        "select pg_cancel_backend(%s)", [target]
                    ),
                )
                try:
                    return _ordered(facade)(statements)
                finally:
                    watcher.join()

            outcome = facade.transaction(body)
        assert isinstance(outcome, Committed)
        result = outcome.value
        assert isinstance(result, OrderedWriteResultComplete)
        count, failed, aborted = result.outcomes
        assert (count, aborted) == (1, StatementNotExecuted())
        assert isinstance(failed, StatementFailed)
        assert cast("DatabaseError", failed.error).native_code == "57014"
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_an_interrupt_while_waiting_propagates_as_itself_and_disposes_the_scope(
    profile_run: Any,
) -> None:
    if threading.current_thread() is not threading.main_thread():
        pytest.skip("an interrupt is delivered to the main thread only")
    _seeded(profile_run)
    before = _state(profile_run)
    statements = (_close("policy", 1), _guard("claim", 1000), _close("policy", 2))

    def interrupt(_signal: int, _frame: object) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGALRM, interrupt)
    runtime = _runtime(profile_run)
    try:
        context = _acquired(runtime)
        with _locked_claim(profile_run), context as facade:
            pid = _pid(facade)

            def body(port: Any) -> OrderedWriteResult:
                port.execute_write("set local lock_timeout = '10s'", [])
                watcher = _when_waiting(
                    profile_run, pid, lambda _session, _target: signal.raise_signal(signal.SIGALRM)
                )
                try:
                    return _ordered(facade)(statements)
                finally:
                    watcher.join()

            outcome = facade.transaction(body)
            assert cast("PostgresConnection", facade).suspect
        assert isinstance(outcome, RolledBack | RollbackFailed)
        assert isinstance(cast("CallbackRaised", outcome.trigger).error, KeyboardInterrupt)
        assert isinstance(context.cleanup_result, Invalidated)
        assert _state(profile_run) == before
    finally:
        signal.signal(signal.SIGALRM, previous)
        runtime.close()


def _prepare_rotation(port: Any) -> int:
    """Leave psycopg owing the server one deallocation when the next statement
    runs, and answer how many statements the server held before it was owed.

    Under a threshold of zero every distinct statement is prepared when first
    run. A plain execution past the cache's capacity deallocates the evicted
    statement once it has run; a pipeline's results are validated only as it
    exits, after the point where psycopg sends what it owes, so the eviction
    its own statement causes is still owed afterwards.
    """
    for ordinal in range(100):
        port.execute(f"select {ordinal} as prepared", [])
    held = _prepared(port)
    port.execute_pipeline((PipelineStatement("select 'evicting' as prepared"),))
    return held


def _prepared(port: Any) -> int:
    """How many statements this session holds prepared."""
    (row,) = port.execute("select count(*) from pg_prepared_statements", [])
    return int(row[0])


@pytest.mark.adapter_smoke
def test_prepared_cache_maintenance_inside_an_ordered_write_answers_no_statement(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    statements = (_close("policy", 1), _guard("claim", 1000))
    runtime = _runtime(profile_run, prepare_threshold=0)
    try:
        with _acquired(runtime) as facade:

            def body(port: Any) -> tuple[int, OrderedWriteResult, int]:
                held = _prepare_rotation(port)
                result = _ordered(facade)(statements)
                return held, result, _prepared(port)

            outcome = facade.transaction(body)
        assert isinstance(outcome, Committed)
        held, result, settled = outcome.value
        assert result == OrderedWriteResultComplete((1, 1))
        # The pipeline's own eviction was paid inside the ordered write: without
        # it, the count would still include the evicted statement.
        assert settled == held - 1
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_failed_prepared_cache_maintenance_interrupts_without_blaming_a_statement(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    statements = (_COLLIDING, _close("policy", 1), _guard("claim", 1000))
    runtime = _runtime(profile_run, prepare_threshold=0)
    try:
        context = _acquired(runtime)
        results: list[OrderedWriteResult] = []
        with context as facade:

            def body(port: Any) -> None:
                _prepare_rotation(port)
                results.append(_ordered(facade)(statements))
                _raising(results[0])

            outcome = facade.transaction(body)
            assert cast("PostgresConnection", facade).suspect
        (result,) = results
        assert isinstance(result, OrderedWriteResultInterrupted)
        assert result.unsent_count == 0
        assert len(result.confirmed) + result.unconfirmed_count == len(statements)
        assert isinstance(result.error, DatabaseError)
        assert isinstance(result.error.__cause__, psycopg.errors.PipelineAborted)
        assert not any(
            isinstance(confirmed, StatementFailed) and confirmed.error is result.error
            for confirmed in result.confirmed
        )
        assert isinstance(outcome, RolledBack)
        assert isinstance(context.cleanup_result, Invalidated)
    finally:
        runtime.close()
