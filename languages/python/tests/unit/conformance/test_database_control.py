"""The harness's own scoped driver controls (Docker-free).

A control is the session the conformance harness drives DIRECTLY — the schema
reset, a case's verbatim golden SQL, a peer holding its own transaction, and the
dedicated session an interleaved choreography may destroy. What the Docker lanes
prove is that those sessions do the database work; what is proven here is
everything around it: that a control forwards to the shipped execution rather
than reimplementing it, that whoever opens one is told when it is released, that
a composition refusing the model does not leak the session it had already
opened, that the controlled runtime serves one scope at a time, that a delayed
control action cannot reach a later scope, and that the termination ladder
escalates rung by rung and RECORDS every rung it had to leave behind.

The ladder's last rung is a real OS-level socket teardown, so these pins hand it
real descriptors from ``socket.socketpair`` rather than a fake standing in for
one: what that rung promises is an operating-system guarantee, which a fake
could only assert.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from types import TracebackType
from typing import Any, cast

import psycopg
import pytest
from psycopg.rows import TupleRow

from parallax.conformance._database_control import TerminationReport
from parallax.conformance._postgres_control import (
    ControlledAdapter,
    PostgresControl,
    PostgresInterleavedExecution,
    initialized_session,
)
from parallax.core.db_port import ConnectionAcquisitionError, DatabaseConnection, Row
from parallax.core.dialect import POSTGRES
from parallax.snapshot.handle import SnapshotConnectionError
from tests._support.snapshot_models import SNAP_ORDERS_MODEL
from tests.unit._contention_support import observing


class _FakeCursor:
    """One statement's worth of a psycopg cursor: what the shipped execution asks of it."""

    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection
        self.description: list[Any] | None = None
        self.rowcount = 1

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return

    def execute(self, sql: object, binds: Sequence[object] | None = None) -> None:
        text = sql.decode() if isinstance(sql, bytes) else str(sql)
        self._connection.statements.append((text, tuple(binds or ())))
        rows = self._connection.rows
        self.description = [_Column(name) for name in rows[0]] if rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return [tuple(row.values()) for row in self._connection.rows]


class _Column:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeTransaction:
    """The driver's transaction context, driven a phase at a time as the port drives it."""

    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> _FakeTransaction:
        self._connection.begins += 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> bool:
        self._connection.commits += 1
        return False


class _FakeConnection:
    """A psycopg-connection stand-in: the seams a control, a ladder, and the
    shipped scoped execution reach for."""

    def __init__(
        self,
        *,
        rows: list[Row] | None = None,
        fd: int | None = None,
        cancel_raises: Exception | None = None,
        close_raises: Exception | None = None,
        parked: Callable[[], None] | None = None,
    ) -> None:
        self.rows: list[Row] = rows if rows is not None else []
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.rollbacks = 0
        self.cancels = 0
        self.closes = 0
        self.begins = 0
        self.commits = 0
        self._fd = fd
        self._cancel_raises = cancel_raises
        # Public and mutable: a session that refused one close and answers the
        # next is the state a retried teardown is proven against.
        self.close_raises = close_raises
        # What a control action does while it is in flight, for the pins that
        # need to observe the runtime WHILE one is running rather than after.
        self._parked = parked if parked is not None else lambda: None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def rollback(self) -> None:
        self.rollbacks += 1

    def cancel_safe(self) -> None:
        self.cancels += 1
        self._parked()
        if self._cancel_raises is not None:
            raise self._cancel_raises

    def close(self) -> None:
        self.closes += 1
        self._parked()
        if self.close_raises is not None:
            raise self.close_raises

    def fileno(self) -> int:
        if self._fd is None:
            raise AssertionError("this pin's ladder never reaches the descriptor")
        return self._fd


def _native(connection: _FakeConnection) -> psycopg.Connection[TupleRow]:
    return cast("psycopg.Connection[TupleRow]", connection)


def _control(connection: _FakeConnection, **kwargs: Any) -> PostgresControl:
    return PostgresControl(_native(connection), **kwargs)


def _adapter(connection: _FakeConnection) -> ControlledAdapter:
    return ControlledAdapter("", session=lambda: _native(connection))


def _execution(connection: _FakeConnection, **kwargs: Any) -> PostgresInterleavedExecution:
    return PostgresInterleavedExecution(_adapter(connection), SNAP_ORDERS_MODEL, **kwargs)


def _connected_descriptor(stack: ExitStack) -> int:
    """A real, still-connected socket descriptor the ladder's last rung destroys.

    Detached from its Python socket so the teardown owns it outright: that rung
    wraps the descriptor in a socket of its own and closes it, which would be a
    double close of a descriptor something else still held. Its far end stays
    open for the test's duration — shutting down a descriptor whose peer is
    already gone would take the FAILING path rather than the one being proven.
    """
    near, far = socket.socketpair()
    stack.enter_context(far)
    return near.detach()


# --------------------------------------------------------------------------- #
# The directly driven session.                                                 #
# --------------------------------------------------------------------------- #
def test_a_control_forwards_every_verb_to_the_shipped_execution_over_its_session() -> None:
    # A statement the harness runs directly is translated and classified exactly
    # as an application's own would be, because the SAME scoped execution runs
    # it. The control adds a lifetime, never a second execution path.
    connection = _FakeConnection(rows=[{"n": 1}])
    control = _control(connection)

    assert control.dialect is POSTGRES
    assert control.execute("select 1 as n", []) == [{"n": 1}]
    assert control.execute_write("update t set a = 1", [2]) == 1
    control.transaction(lambda port: port.execute("select 1 as n", []))

    assert connection.statements == [
        ("select 1 as n", ()),
        ("update t set a = 1", (2,)),
        ("select 1 as n", ()),
    ]
    assert (connection.begins, connection.commits) == (1, 1)


def test_a_control_undoes_its_own_held_transaction_through_the_driver() -> None:
    # `rollback` is the verb an application's Database has no use for: only a
    # session the harness itself holds open across statements can be told to
    # discard what it has done so far.
    connection = _FakeConnection()
    _control(connection).rollback()
    assert connection.rollbacks == 1


def test_a_control_ends_another_session_by_asking_the_server() -> None:
    # The one way to make a genuine ROLLBACK fail is to remove the session the
    # undo would run in — which is reached through the SERVER, by backend pid,
    # rather than through the target's own transport, so a transaction-scoped
    # connection is as reachable as any other.
    executioner = _FakeConnection()
    victim = _FakeConnection(rows=[{"pid": 4271}])

    _control(executioner).terminate_session(
        cast("DatabaseConnection", _control(victim)),
    )

    assert victim.statements == [("select pg_backend_pid() as pid", ())]
    assert executioner.statements == [("select pg_terminate_backend(%s) as terminated", (4271,))]


def test_closing_a_control_releases_the_session_and_reports_it_to_its_opener() -> None:
    # Scoped ownership: the caller closes, and the provisioner that handed the
    # session out is told, so its teardown backstop covers only what a caller
    # really left open.
    connection = _FakeConnection()
    released: list[object] = []
    control = _control(connection, on_release=released.append)

    control.close()

    assert connection.closes == 1
    assert released == [control]


def test_a_session_whose_initialization_is_refused_is_closed_before_the_refusal_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Setup failure, proven without a server: a connection nothing may execute
    # on is not one to hand back to a caller that would then have to remember
    # it, so the refusal leaves with the session already closed.
    from parallax.conformance import _postgres_control as control_module

    def refuse(_connection: object) -> None:
        raise RuntimeError("this session cannot be initialized")

    monkeypatch.setattr(control_module, "initialize_connection", refuse)
    connection = _FakeConnection()

    with pytest.raises(RuntimeError, match="cannot be initialized"):
        initialized_session(_native(connection))

    assert connection.closes == 1


def test_an_initialized_session_is_handed_over_open(monkeypatch: pytest.MonkeyPatch) -> None:
    # The other half of the same decision: what initialization accepted is
    # handed to the caller as it stands, and closing it is the caller's from
    # there on.
    from parallax.conformance import _postgres_control as control_module

    initialized: list[object] = []
    monkeypatch.setattr(control_module, "initialize_connection", initialized.append)
    connection = _FakeConnection()

    assert initialized_session(_native(connection)) is _native(connection)

    assert initialized == [_native(connection)]
    assert connection.closes == 0


def test_a_session_opened_without_a_tracker_releases_itself() -> None:
    # Not every session is handed out by a provisioner tracking it. One opened
    # directly has nobody to report its release to, and closing it is still the
    # whole release.
    connection = _FakeConnection()
    _control(connection).close()
    assert connection.closes == 1

    execution_connection = _FakeConnection()
    _execution(execution_connection).close()
    assert execution_connection.closes == 1


def test_a_control_whose_close_fails_stays_on_its_openers_books() -> None:
    # A session that would not close is still alive as far as anyone can tell,
    # so it must not be forgotten: the failure surfaces to the caller AND the
    # backstop still knows about it.
    connection = _FakeConnection(close_raises=RuntimeError("the session would not close"))
    released: list[object] = []
    control = _control(connection, on_release=released.append)

    with pytest.raises(RuntimeError, match="would not close"):
        control.close()

    assert released == []


# --------------------------------------------------------------------------- #
# The dedicated session one interleaved choreography may destroy.              #
# --------------------------------------------------------------------------- #
def test_an_execution_composes_its_own_handle_from_its_own_configuration() -> None:
    # The Database is composed HERE, from configuration, rather than accepted:
    # no caller can pair a handle with a session it does not own, and the
    # dialect it answers is the one the session under it spells.
    execution = _execution(_FakeConnection())

    assert execution.dialect is POSTGRES
    assert execution.termination_ladder_trusted is True
    # A real acquisition through the composed handle's runtime, released again.
    assert execution.database.transact(lambda tx: tx.edition) is not None


def test_a_composition_that_refuses_the_model_opens_no_session_at_all() -> None:
    # The model is judged before the configuration is opened, so a value that
    # could never be served costs no session — and the refusal itself is what
    # the caller sees.
    connection = _FakeConnection()

    with pytest.raises(SnapshotConnectionError):
        PostgresInterleavedExecution(_adapter(connection), cast("Any", object()))

    assert connection.statements == []
    assert connection.closes == 0


def test_closing_a_controlled_runtime_retires_the_session_it_owns() -> None:
    # A pooled runtime hands its connections back to something that outlives it;
    # this one has exactly one session and nothing to hand it to, so closing the
    # runtime is what ends it — which is also what makes a composition that
    # failed after opening release what it took, since Database closes the
    # runtime it was handed.
    connection = _FakeConnection()
    runtime = _adapter(connection).open()

    runtime.close()
    runtime.close()

    assert connection.closes == 1


def test_closing_the_composed_handle_retires_the_dedicated_session() -> None:
    connection = _FakeConnection()
    execution = _execution(connection)

    execution.database.close()

    assert connection.closes == 1


def test_a_controlled_runtime_serves_one_scope_at_a_time() -> None:
    # Exclusive use is enforced rather than assumed: there is ONE session under
    # this runtime, and two overlapping scopes on it would be the confusion the
    # choreography it serves is built to avoid.
    runtime = _adapter(_FakeConnection()).open()
    first = runtime.connection()
    with first, pytest.raises(ConnectionAcquisitionError) as refused:
        runtime.connection().__enter__()
    assert refused.value.reason == "queue_rejected"
    # Released again, the next scope is admitted.
    with runtime.connection():
        pass


def test_a_controlled_scope_is_entered_exactly_once() -> None:
    runtime = _adapter(_FakeConnection()).open()
    scope = runtime.connection()
    with scope:
        pass
    with pytest.raises(RuntimeError):
        scope.__enter__()


def test_a_closed_controlled_runtime_admits_no_further_scope() -> None:
    runtime = _adapter(_FakeConnection()).open()
    runtime.close()
    with pytest.raises(ConnectionAcquisitionError) as refused:
        runtime.connection().__enter__()
    assert refused.value.reason == "closed"


def test_leaving_a_controlled_scope_revokes_what_it_yielded() -> None:
    # The session outlives the scope, so what must not outlive it is ACCESS: a
    # reference kept past the release executes nothing.
    connection = _FakeConnection()
    runtime = _adapter(connection).open()
    with runtime.connection() as scoped:
        pass
    with pytest.raises(RuntimeError):
        scoped.execute("select 1", [])
    assert connection.statements == []


def test_cancelling_asks_the_driver_and_survives_a_refusal() -> None:
    # The non-destructive rung: a cancellation request is best effort by nature
    # — it can be refused, arrive late, or have nothing to interrupt — so a
    # failure here escalates rather than propagates.
    connection = _FakeConnection()
    execution = _execution(connection)
    with _scope_of(execution):
        execution.cancel_active()
    assert connection.cancels == 1

    refusing = _FakeConnection(cancel_raises=RuntimeError("the request was refused"))
    refused = _execution(refusing)
    with _scope_of(refused):
        refused.cancel_active()
    assert refusing.cancels == 1


def _scope_of(execution: PostgresInterleavedExecution) -> Any:
    """One open acquisition of ``execution``'s session, as a control action sees it."""
    runtime = cast("Any", execution)._runtime
    scope = runtime.connection()
    scope.__enter__()
    return _Releasing(scope)


class _Releasing:
    def __init__(self, scope: Any) -> None:
        self.scope = scope

    def __enter__(self) -> Any:
        return self.scope

    def __exit__(self, *exc: object) -> None:
        self.scope.__exit__(None, None, None)


class _PausedCapture:
    """A runtime's own capture, held open between capturing a target and revalidating it.

    The seam a delayed control action turns on is inside the action: it captures
    the scope being served, and the request goes out only once the runtime has
    been asked AGAIN whether that scope is still the one being served. A delay
    anywhere else proves something weaker — parking inside the native call is
    already past the revalidation — so the capture itself waits here, on the
    acting thread, while the test ends the captured scope and opens the next one.
    """

    def __init__(self, runtime: Any) -> None:
        self._capture = runtime.active_scope
        self.captured = threading.Event()
        self.resume = threading.Event()
        runtime.active_scope = self

    def __call__(self) -> Any:
        scope = self._capture()
        self.captured.set()
        assert self.resume.wait(timeout=5.0)
        return scope


@pytest.mark.parametrize("action", ["cancel", "terminate"])
def test_an_action_captured_in_one_scope_reaches_neither_the_next_nor_its_descriptor(
    action: str,
) -> None:
    # A delayed control action revalidates when it EXECUTES, not only when it
    # captured its target. This is that gap itself: the action captures the
    # scope it was asked about and is then held there while that scope ends and
    # another takes the session. What it must not do on resuming is act on the
    # target it captured — interrupting a statement nobody asked to interrupt,
    # or tearing down a descriptor a later connection can be answering to. So
    # the request never goes out, the descriptor is still open, and the scope
    # that arrived meanwhile runs its own work. The driver's own close is set to
    # fail, which is what puts that descriptor within reach: a termination that
    # acted on its stale target would find rung one refused and destroy the
    # descriptor at the operating system on rung two.
    with ExitStack() as stack:
        descriptor = _connected_descriptor(stack)
        connection = _FakeConnection(fd=descriptor, close_raises=RuntimeError("close failed"))
        execution = _execution(connection)
        runtime = cast("Any", execution)._runtime
        captured = runtime.connection()
        captured.__enter__()

        paused = _PausedCapture(runtime)
        reports: list[TerminationReport] = []

        def act() -> None:
            if action == "cancel":
                execution.cancel_active()
            else:
                reports.append(execution.terminate_active())

        acting = threading.Thread(target=act)
        acting.start()
        assert paused.captured.wait(timeout=5.0)

        captured.__exit__(None, None, None)
        with runtime.connection() as replacement:
            paused.resume.set()
            acting.join(timeout=5.0)
            assert not acting.is_alive()
            assert (connection.cancels, connection.closes) == (0, 0)
            replacement.execute("select 1", [])

        assert connection.statements == [("select 1", ())]
        with socket.socket(fileno=descriptor):
            pass

    if action == "terminate":
        assert reports == [
            TerminationReport(
                terminated=False,
                failures=("the scope this termination captured had already ended",),
            )
        ]


def test_a_cancellation_with_no_scope_open_asks_the_driver_for_nothing() -> None:
    # Nothing is being served, so there is no statement anyone asked to
    # interrupt and the request is not made at all.
    idle = _execution(_FakeConnection())
    idle.cancel_active()
    assert cast("Any", idle)._runtime.native.cancels == 0


@pytest.mark.parametrize("action", ["cancel", "terminate"])
def test_no_scope_is_admitted_while_a_validated_control_action_is_in_flight(action: str) -> None:
    # An action that HAS revalidated is still mid-flight, and the answer it
    # validated has to keep holding while it acts: a scope admitted between the
    # check and the native call would be reached by a request nobody validated
    # against it. So admission stays shut for the whole of the action, and the
    # cost of that is bounded to the next scope — the captured one still ends
    # without waiting for the action, which is what this parks to observe.
    running = threading.Event()
    finish = threading.Event()

    def park() -> None:
        running.set()
        assert finish.wait(timeout=5.0)

    connection = _FakeConnection(parked=park)
    execution = _execution(connection)
    runtime = cast("Any", execution)._runtime
    captured = runtime.connection()
    captured.__enter__()

    acting = threading.Thread(
        target=execution.cancel_active if action == "cancel" else execution.terminate_active
    )
    acting.start()
    assert running.wait(timeout=5.0)

    # The captured scope ends without waiting for the action, and the next scope
    # asks for the session while the action is still running.
    captured.__exit__(None, None, None)
    admission = observing(runtime, "_admission")
    settled = threading.Event()
    outcome: list[str] = []

    def take_the_session() -> None:
        try:
            with runtime.connection():
                outcome.append("admitted")
        except ConnectionAcquisitionError:
            outcome.append("refused")
        settled.set()

    waiting = threading.Thread(target=take_the_session)
    waiting.start()
    # The overlap itself: the next scope has reached admission and found the
    # in-flight action holding it shut. Only now is not finishing meaningful.
    assert admission.contended.wait(timeout=5.0)
    assert not settled.wait(timeout=0.25)

    finish.set()
    acting.join(timeout=5.0)
    waiting.join(timeout=5.0)
    # Only once the action is done is the question even answered — and a
    # termination answers it by refusing, because the session it destroyed is
    # the only one this runtime has.
    assert outcome == (["admitted"] if action == "cancel" else ["refused"])


def test_a_controlled_scope_gives_the_session_back_even_if_revocation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The runtime serves one scope at a time, so a scope that failed to hand the
    # session back would leave it refusing every later acquisition. Relinquishing
    # is therefore what the exit does last and unconditionally.
    from parallax.postgres._connection import PostgresConnection

    def refuse(_self: object) -> bool:
        raise RuntimeError("the scope could not be revoked")

    monkeypatch.setattr(PostgresConnection, "revoke", refuse)
    runtime = _adapter(_FakeConnection()).open()
    scope = runtime.connection()

    with pytest.raises(RuntimeError), scope:
        pass

    assert runtime.active_scope() is None
    monkeypatch.undo()
    with runtime.connection():
        pass


def test_a_termination_with_no_live_scope_reports_that_it_reached_nothing() -> None:
    # Nothing is being served, so there is no scope this termination could have
    # captured and no rung it may descend. What it owes its caller then is an
    # honest report of having reached nothing, not a session destroyed on the
    # strength of a target it never had.
    connection = _FakeConnection()
    execution = _execution(connection)

    report = execution.terminate_active()

    assert report.terminated is False
    assert report.failures == ("the scope this termination captured had already ended",)
    assert connection.closes == 0


def test_terminating_stops_at_the_driver_connections_own_close() -> None:
    # Rung one is the whole ladder when it works: nothing below it is attempted
    # and there is no failure to record.
    connection = _FakeConnection()
    execution = _execution(connection)

    with _scope_of(execution):
        assert execution.terminate_active() == TerminationReport(terminated=True)
    assert connection.closes == 1


def test_terminating_a_session_the_ladder_already_destroyed_attempts_no_rung() -> None:
    # A condemned session stays the scope's until that scope ends, so a second
    # escalation can still capture it — and descending the ladder again would
    # close a driver connection that has been closed. What the report says of
    # that second escalation is what it established, which is nothing: the
    # session was gone before it started, and a caller reading `terminated`
    # learns whether ITS attempt is what ended the session, not whether some
    # earlier one did.
    connection = _FakeConnection()
    execution = _execution(connection)

    with _scope_of(execution):
        assert execution.terminate_active() == TerminationReport(terminated=True)
        assert execution.terminate_active() == TerminationReport(
            terminated=False,
            failures=("this session had already been retired, so no rung was attempted",),
        )

    assert connection.closes == 1


def test_terminating_escalates_to_os_level_teardown_of_a_real_descriptor() -> None:
    # Rung two: the driver's own close failed, so the descriptor the blocked
    # call is waiting on is shut down at the operating system — the guarantee
    # the whole unbounded post-ladder join rests on. The descriptor is genuinely
    # gone afterwards, which is what makes it a guarantee rather than a claim.
    with ExitStack() as stack:
        fd = _connected_descriptor(stack)
        connection = _FakeConnection(fd=fd, close_raises=RuntimeError("driver close failed"))
        execution = _execution(connection)
        with _scope_of(execution):
            report = execution.terminate_active()

    assert report.terminated is True
    assert report.failures == (
        "the underlying driver connection's close() raised RuntimeError('driver close failed')",
    )
    with pytest.raises(OSError):
        socket.socket(fileno=fd).close()


def test_terminating_reports_a_descriptor_the_teardown_could_not_shut_down() -> None:
    # An unconnected descriptor cannot be shut down, and the rung says so rather
    # than reporting a termination it did not establish. The descriptor is still
    # closed: a failed shutdown must never leave one open.
    unconnected = socket.socket()
    fd = unconnected.detach()
    connection = _FakeConnection(fd=fd, close_raises=RuntimeError("driver close failed"))
    execution = _execution(connection)

    with _scope_of(execution):
        report = execution.terminate_active()

    assert report.terminated is False
    assert any("OS-level shutdown" in failure for failure in report.failures)
    with pytest.raises(OSError):
        socket.socket(fileno=fd).close()


def test_terminating_reports_a_descriptor_no_socket_can_be_made_from() -> None:
    # A connection whose descriptor is not one at all: the rung records it and
    # returns rather than crashing the caller that is already handling a hang.
    connection = _FakeConnection(fd=-1, close_raises=RuntimeError("driver close failed"))
    execution = _execution(connection)

    with _scope_of(execution):
        report = execution.terminate_active()

    assert report.terminated is False
    assert any("OS-level socket(fileno=-1)" in failure for failure in report.failures)


def test_terminating_reports_a_connection_that_will_not_answer_its_descriptor() -> None:
    # The last rung needs the descriptor to reach; a connection that will not
    # give one up ends the ladder with an honest, unterminated report.
    connection = _FakeConnection(close_raises=RuntimeError("driver close failed"))
    execution = _execution(connection)

    with _scope_of(execution):
        report = execution.terminate_active()

    assert report.terminated is False
    assert any("fileno() raised" in failure for failure in report.failures)


def test_closing_an_execution_is_quiet_about_a_session_the_ladder_condemned() -> None:
    # The lane closes every execution it opened on the way out, terminated ones
    # included. A condemned session is already gone, so it is not closed a second
    # time and nothing the ladder already reported is repeated — and its opener
    # IS told, because what it was tracking really has been released.
    connection = _FakeConnection()
    released: list[object] = []
    execution = _execution(connection, on_release=released.append)
    with _scope_of(execution):
        assert execution.terminate_active().terminated is True

    execution.close()

    assert connection.closes == 1
    assert released == [execution]


def test_an_execution_whose_session_would_not_close_stays_on_its_openers_books() -> None:
    # Symmetric with a directly driven control: a session nobody can show is
    # dead is still this execution's, so it stays on the provisioner's books for
    # the teardown backstop rather than being forgotten while alive. The close
    # itself is still quiet — it runs while a caller is unwinding.
    connection = _FakeConnection(close_raises=RuntimeError("the session would not close"))
    released: list[object] = []
    execution = _execution(connection, on_release=released.append)

    execution.close()

    assert released == []


def test_a_session_that_refused_one_close_is_retired_by_the_next() -> None:
    # What being kept on those books is FOR. The backstop closes what it still
    # tracks, so a refused close must leave a runtime that tries again rather
    # than one that has recorded itself closed and does nothing — and the opener
    # is told when the retry succeeds, which is what takes it off the books.
    connection = _FakeConnection(close_raises=RuntimeError("the session would not close"))
    released: list[object] = []
    execution = _execution(connection, on_release=released.append)
    execution.close()

    connection.close_raises = None
    execution.close()

    assert released == [execution]
    # And a retired session is not closed again: the retry costs a driver call
    # only while there is something left to end.
    retired_after = connection.closes
    execution.close()
    assert connection.closes == retired_after


def test_an_execution_closed_under_a_borrower_reports_its_release_when_the_scope_ends() -> None:
    # Retirement deferred to the borrower completes on the borrower's thread,
    # long after the close that asked for it returned. The opener has to be told
    # THEN: a session really gone that stayed on the books would be closed a
    # second time by a teardown that had nothing left to end.
    connection = _FakeConnection()
    released: list[object] = []
    execution = _execution(connection, on_release=released.append)

    with _scope_of(execution):
        execution.close()
        assert connection.closes == 0
        assert released == []

    assert connection.closes == 1
    assert released == [execution]


def test_closing_a_controlled_runtime_under_a_borrower_waits_for_the_scope_to_end() -> None:
    # `m-db-port`: a close stops admission and neither waits for borrowers nor
    # interrupts their statements. This runtime has one session and nothing to
    # hand it back to, so what would otherwise be "closed when it comes back" is
    # "retired when the scope that held it relinquishes".
    connection = _FakeConnection()
    runtime = _adapter(connection).open()
    scope = runtime.connection()
    scoped = scope.__enter__()

    runtime.close()

    assert connection.closes == 0
    assert runtime.retired is False
    # Admitted before the close, so it finishes what it was going to do.
    assert scoped.execute("select 1 as n", []) == []
    with pytest.raises(ConnectionAcquisitionError) as refused:
        runtime.connection().__enter__()
    assert refused.value.reason == "closed"

    scope.__exit__(None, None, None)

    assert connection.closes == 1
    assert runtime.retired is True


def test_a_deferred_retirement_and_a_second_close_end_the_session_exactly_once() -> None:
    # The shutdown race the interleaved lane really runs: a close arrives while
    # a borrower holds the session, so retirement waits for it and completes on
    # the borrower's thread — while the closer, seeing the borrower gone, comes
    # back for the session itself. Both would read a runtime nobody has retired
    # yet, and a driver connection closed by two threads at once is libpq
    # finishing a connection the other is already finishing. So the second path
    # waits for the first and then finds nothing left to end.
    guard = threading.Lock()
    entered = 0
    closing = threading.Event()
    proceed = threading.Event()

    def park_the_first_close() -> None:
        nonlocal entered
        with guard:
            entered += 1
            first = entered == 1
        if first:
            closing.set()
            assert proceed.wait(timeout=5.0)

    connection = _FakeConnection(parked=park_the_first_close)
    runtime = _adapter(connection).open()
    scope = runtime.connection()
    scope.__enter__()
    runtime.close()

    borrower = threading.Thread(target=scope.__exit__, args=(None, None, None))
    borrower.start()
    assert closing.wait(timeout=5.0)

    retirement = observing(runtime, "_retirement")
    closed_again = threading.Event()

    def close_again() -> None:
        runtime.close()
        closed_again.set()

    closer = threading.Thread(target=close_again)
    closer.start()
    # The race itself, and the only way to run it: the second closer has reached
    # the claim on ending this session while the deferred retirement is still
    # inside the native close. A closer that arrived afterwards would find the
    # session retired and do nothing — which the implementation this pin
    # condemns also does, so the pin waits for the overlap rather than for time.
    assert retirement.contended.wait(timeout=5.0)
    assert not closed_again.wait(timeout=0.25)

    proceed.set()
    borrower.join(timeout=5.0)
    closer.join(timeout=5.0)

    assert connection.closes == 1
    assert runtime.retired is True


def test_a_control_exposes_its_own_session_for_the_harnesss_native_proofs() -> None:
    # Reachable on a session the harness opened and closes, and nowhere on a
    # Database: the point of removing the raw accessor is that no application
    # reaches a connection it did not open, not that the harness cannot.
    connection = _FakeConnection()
    assert _control(connection).native is _native(connection)


def test_a_controlled_runtime_publishes_no_pool_measurements() -> None:
    # It manages no pool, so it keeps no bookkeeping — absence rather than a
    # source that would answer nothing.
    assert _adapter(_FakeConnection()).open().pool_metrics is None


def test_leaving_a_controlled_scope_that_was_never_entered_does_nothing() -> None:
    runtime = _adapter(_FakeConnection()).open()
    scope = runtime.connection()
    scope.__exit__(None, None, None)
    assert scope.cleanup_result is None
    # And the runtime never thought a scope was open.
    with runtime.connection():
        pass
