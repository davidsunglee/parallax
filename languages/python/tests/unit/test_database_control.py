"""The harness's own scoped driver controls (Docker-free).

A control is the session the conformance harness drives DIRECTLY — the schema
reset, a case's verbatim golden SQL, a peer holding its own transaction, and the
dedicated session an interleaved choreography may destroy. What the Docker lanes
prove is that those sessions do the database work; what is proven here is
everything around it: that a control forwards rather than reimplements, that
whoever opens one is told when it is released, that a composition refusing the
model does not leak the session it had already opened, and that the termination
ladder escalates rung by rung and RECORDS every rung it had to leave behind.

The ladder's last rung is a real OS-level socket teardown, so these pins hand it
real descriptors from ``socket.socketpair`` rather than a fake standing in for
one: what that rung promises is an operating-system guarantee, which a fake
could only assert.
"""

from __future__ import annotations

import socket
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from typing import Any, cast

import pytest

from _support.snapshot_models import SNAP_ORDERS_MODEL
from parallax.conformance._database_control import TerminationReport
from parallax.conformance._postgres_control import (
    PostgresControl,
    PostgresInterleavedExecution,
)
from parallax.core.db_port import Committed, DbPort, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres import PostgresAdapter
from parallax.snapshot import handle
from parallax.snapshot.handle import SnapshotConnectionError


class _FakeConnection:
    """The driver connection under a fake adapter: the three seams the ladder,
    the cancellation rung, and a held transaction's undo reach for."""

    def __init__(
        self,
        *,
        fd: int | None = None,
        cancel_raises: Exception | None = None,
        close_raises: Exception | None = None,
    ) -> None:
        self.rollbacks = 0
        self.cancels = 0
        self.closes = 0
        self._fd = fd
        self._cancel_raises = cancel_raises
        self._close_raises = close_raises

    def rollback(self) -> None:
        self.rollbacks += 1

    def cancel_safe(self) -> None:
        self.cancels += 1
        if self._cancel_raises is not None:
            raise self._cancel_raises

    def close(self) -> None:
        self.closes += 1
        if self._close_raises is not None:
            raise self._close_raises

    def fileno(self) -> int:
        if self._fd is None:
            raise AssertionError("this pin's ladder never reaches the descriptor")
        return self._fd


class _FakeAdapter:
    """A `PostgresAdapter`-shaped session recording what a control asked of it.

    Every verb answers a canned value rather than executing anything: what the
    control adds to an adapter is a lifetime and an escalation, so these pins
    grade the forwarding rather than the SQL.
    """

    dialect: Dialect = POSTGRES

    def __init__(
        self,
        *,
        rows: list[Row] | None = None,
        connection: _FakeConnection | None = None,
        close_raises: Exception | None = None,
    ) -> None:
        self.connection = connection if connection is not None else _FakeConnection()
        self.reads: list[tuple[str, tuple[object, ...]]] = []
        self.writes: list[tuple[str, tuple[object, ...]]] = []
        self.transactions = 0
        self.closes = 0
        self._rows = rows if rows is not None else []
        self._close_raises = close_raises

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[object] = ()
    ) -> list[Row]:
        self.reads.append((sql, tuple(binds)))
        return self._rows

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, tuple(binds)))
        return 1

    def transaction(
        self, body: Callable[[DbPort], object], *, isolation: str | None = None
    ) -> TransactionOutcome[object]:
        self.transactions += 1
        return Committed(value=body(cast("DbPort", self)))

    def close(self) -> None:
        self.closes += 1
        if self._close_raises is not None:
            raise self._close_raises


def _control(adapter: _FakeAdapter, **kwargs: Any) -> PostgresControl:
    return PostgresControl(cast("PostgresAdapter", adapter), **kwargs)


def _execution(adapter: _FakeAdapter, **kwargs: Any) -> PostgresInterleavedExecution:
    return PostgresInterleavedExecution(
        cast("PostgresAdapter", adapter), SNAP_ORDERS_MODEL, **kwargs
    )


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
def test_a_control_forwards_every_verb_to_the_session_it_opened() -> None:
    # A statement the harness runs directly is translated and classified exactly
    # as an application's own would be, because the same adapter runs it. The
    # control adds a lifetime, never a second execution path.
    row: Row = {"n": 1}
    adapter = _FakeAdapter(rows=[row])
    control = _control(adapter)

    assert control.dialect is POSTGRES
    assert control.execute("select 1 as n", []) == [row]
    assert control.execute_write("update t set a = 1", [2]) == 1
    outcome = control.transaction(lambda port: port.execute("select 1 as n", []))

    assert adapter.reads == [("select 1 as n", ()), ("select 1 as n", ())]
    assert adapter.writes == [("update t set a = 1", (2,))]
    assert isinstance(outcome, Committed)


def test_a_control_undoes_its_own_held_transaction_through_the_driver() -> None:
    # `rollback` is the verb an application's Database has no use for: only a
    # session the harness itself holds open across statements can be told to
    # discard what it has done so far.
    adapter = _FakeAdapter()
    _control(adapter).rollback()
    assert adapter.connection.rollbacks == 1


def test_a_control_ends_another_session_by_asking_the_server() -> None:
    # The one way to make a genuine ROLLBACK fail is to remove the session the
    # undo would run in — which is reached through the SERVER, by backend pid,
    # rather than through the target's own transport, so a transaction-scoped
    # port is as reachable as any other.
    executioner = _FakeAdapter()
    victim = _FakeAdapter(rows=[{"pid": 4271}])

    _control(executioner).terminate_session(cast("DbPort", victim))

    assert victim.reads == [("select pg_backend_pid() as pid", ())]
    assert executioner.reads == [("select pg_terminate_backend(%s) as terminated", (4271,))]


def test_closing_a_control_releases_the_session_and_reports_it_to_its_opener() -> None:
    # Scoped ownership: the caller closes, and the provisioner that handed the
    # session out is told, so its teardown backstop covers only what a caller
    # really left open.
    adapter = _FakeAdapter()
    released: list[object] = []
    control = _control(adapter, on_release=released.append)

    control.close()

    assert adapter.closes == 1
    assert released == [control]


def test_a_session_opened_without_a_tracker_releases_itself() -> None:
    # Not every session is handed out by a provisioner tracking it. One opened
    # directly has nobody to report its release to, and closing it is still the
    # whole release.
    control_adapter = _FakeAdapter()
    _control(control_adapter).close()
    assert control_adapter.closes == 1

    execution_adapter = _FakeAdapter()
    _execution(execution_adapter).close()
    assert execution_adapter.closes == 1


def test_a_control_whose_close_fails_stays_on_its_openers_books() -> None:
    # A session that would not close is still alive as far as anyone can tell,
    # so it must not be forgotten: the failure surfaces to the caller AND the
    # backstop still knows about it.
    adapter = _FakeAdapter(close_raises=RuntimeError("the session would not close"))
    released: list[object] = []
    control = _control(adapter, on_release=released.append)

    with pytest.raises(RuntimeError, match="would not close"):
        control.close()

    assert released == []


# --------------------------------------------------------------------------- #
# The dedicated session one interleaved choreography may destroy.              #
# --------------------------------------------------------------------------- #
def test_an_execution_composes_its_own_handle_over_the_session_it_owns() -> None:
    # The Database is composed HERE rather than accepted, so no caller can pair
    # a handle with a session it does not own — and the dialect it answers is
    # the one the session under it spells.
    adapter = _FakeAdapter()
    execution = _execution(adapter)

    assert isinstance(execution.database, handle.Database)
    assert execution.dialect is POSTGRES
    assert execution.termination_ladder_trusted is True


def test_a_composition_that_refuses_the_model_releases_the_session_it_opened() -> None:
    # Setup failure: the session opens before the handle is composed, so a
    # refusal after the open must release it rather than leak it — and the
    # refusal itself is what the caller sees.
    adapter = _FakeAdapter()

    with pytest.raises(SnapshotConnectionError):
        PostgresInterleavedExecution(cast("PostgresAdapter", adapter), cast("Any", object()))

    assert adapter.closes == 1


def test_cancelling_asks_the_driver_and_survives_a_refusal() -> None:
    # The non-destructive rung: a cancellation request is best effort by nature
    # — it can be refused, arrive late, or have nothing to interrupt — so a
    # failure here escalates rather than propagates.
    adapter = _FakeAdapter()
    _execution(adapter).cancel_active()
    assert adapter.connection.cancels == 1

    refusing = _FakeConnection(cancel_raises=RuntimeError("the request was refused"))
    _execution(_FakeAdapter(connection=refusing)).cancel_active()
    assert refusing.cancels == 1


def test_terminating_stops_at_the_sessions_own_close() -> None:
    # Rung one is the whole ladder when it works: nothing below it is attempted
    # and there is no failure to record.
    adapter = _FakeAdapter()

    assert _execution(adapter).terminate_active() == TerminationReport(terminated=True)
    assert adapter.closes == 1
    assert adapter.connection.closes == 0


def test_terminating_escalates_to_the_driver_connection_and_records_the_rung_it_left() -> None:
    # Rung two: the session's own close raised, so the connection underneath it
    # is closed directly — and the rung that failed on the way is REPORTED, not
    # erased by the rung that worked.
    adapter = _FakeAdapter(close_raises=RuntimeError("outer close failed"))

    report = _execution(adapter).terminate_active()

    assert report.terminated is True
    assert adapter.connection.closes == 1
    assert report.failures == (
        "the session's own close() raised RuntimeError('outer close failed')",
    )


def test_terminating_escalates_to_os_level_teardown_of_a_real_descriptor() -> None:
    # Rung three: both closes failed, so the descriptor the blocked call is
    # waiting on is shut down at the operating system — the guarantee the whole
    # unbounded post-ladder join rests on. The descriptor is genuinely gone
    # afterwards, which is what makes it a guarantee rather than a claim.
    with ExitStack() as stack:
        fd = _connected_descriptor(stack)
        connection = _FakeConnection(fd=fd, close_raises=RuntimeError("driver close failed"))
        adapter = _FakeAdapter(
            connection=connection, close_raises=RuntimeError("outer close failed")
        )

        report = _execution(adapter).terminate_active()

    assert report.terminated is True
    assert report.failures == (
        "the session's own close() raised RuntimeError('outer close failed')",
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
    adapter = _FakeAdapter(connection=connection, close_raises=RuntimeError("outer close failed"))

    report = _execution(adapter).terminate_active()

    assert report.terminated is False
    assert any("OS-level shutdown" in failure for failure in report.failures)
    with pytest.raises(OSError):
        socket.socket(fileno=fd).close()


def test_terminating_reports_a_descriptor_no_socket_can_be_made_from() -> None:
    # A connection whose descriptor is not one at all: the rung records it and
    # returns rather than crashing the caller that is already handling a hang.
    connection = _FakeConnection(fd=-1, close_raises=RuntimeError("driver close failed"))
    adapter = _FakeAdapter(connection=connection, close_raises=RuntimeError("outer close failed"))

    report = _execution(adapter).terminate_active()

    assert report.terminated is False
    assert any("OS-level socket(fileno=-1)" in failure for failure in report.failures)


def test_terminating_reports_a_connection_that_will_not_answer_its_descriptor() -> None:
    # The last rung needs the descriptor to reach; a connection that will not
    # give one up ends the ladder with an honest, unterminated report.
    connection = _FakeConnection(close_raises=RuntimeError("driver close failed"))
    adapter = _FakeAdapter(connection=connection, close_raises=RuntimeError("outer close failed"))

    report = _execution(adapter).terminate_active()

    assert report.terminated is False
    assert any("fileno() raised" in failure for failure in report.failures)


def test_closing_an_execution_is_quiet_about_a_session_the_ladder_condemned() -> None:
    # The lane closes every execution it opened on the way out, terminated ones
    # included. A condemned session refusing to close again adds nothing to the
    # report the ladder already returned, so it must not displace the timeout
    # error the caller is raising — and its opener is still told.
    adapter = _FakeAdapter(close_raises=RuntimeError("already condemned"))
    released: list[object] = []
    execution = _execution(adapter, on_release=released.append)

    execution.close()

    assert released == [execution]
