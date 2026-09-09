"""``parallax.conformance._postgres_control`` — the native side of the controls.

Every psycopg-shaped fact the harness's own sessions need lives here: opening a
dedicated connection, ending another session through the server, and the
escalation that destroys a session whose own thread is parked in driver I/O. The
protocols these implement carry none of it
(:mod:`parallax.conformance._database_control`), so the engine consumes declared
capabilities and this module is the only place a control knows it is Postgres.

It reaches one private module of the shipped adapter,
``parallax.postgres._connection``, for exactly two names:
:func:`~parallax.postgres._connection.initialize_connection`, the setup every
physical connection gets, and :class:`~parallax.postgres._connection.PostgresConnection`,
the scoped execution over one. That reach is deliberate and recorded in the
Python specification's source grants. The alternative is a second
implementation of the codecs, the error translation, and the transaction
outcomes inside the harness — which is a harness that proves its own behavior
rather than the adapter's.

What this module does NOT reuse is the runtime: the shipped runtime owns a pool,
and a session the harness may have to cancel, close, or tear down at the socket
must be one connection nothing else can be handed. So the controlled adapter
below is its own, and it exists only for choreography that needs those actions.
Ordinary conformance work composes its Database from the shipped
:class:`~parallax.postgres.PostgresAdapter`.

Nothing else may import this module eagerly: naming a control must not load the
driver, so the provisioner reaches this module inside the call that opens one.
"""

from __future__ import annotations

import contextlib
import os
import socket
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

import psycopg
from psycopg.rows import TupleRow, tuple_row

from parallax.conformance._database_control import TerminationReport
from parallax.core.db_port import (
    CleanupResult,
    ConnectionAcquisitionError,
    DatabaseConnection,
    Returned,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres._connection import PostgresConnection, initialize_connection
from parallax.snapshot import handle

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType

    from parallax.core.db_port import (
        Bind,
        ConnectionContext,
        DocumentReadOrdinals,
        IsolationLevel,
        PoolMetricsSource,
        Row,
        TransactionOutcome,
    )
    from parallax.core.entity import DomainModel
    from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
    from parallax.core.unit_work import Clock
    from parallax.snapshot.handle import ServingModel

__all__ = ["PostgresControl", "PostgresInterleavedExecution"]

_BACKEND_PID: Final[str] = "select pg_backend_pid() as pid"
_TERMINATE_BACKEND: Final[str] = "select pg_terminate_backend(%s) as terminated"
_RELINQUISHED: Final[CleanupResult] = Returned()


def open_session(  # pragma: no cover - opens a real session; the Docker lanes exercise it
    conninfo: str, *, autocommit: bool = True, prepare_threshold: int | None = 5
) -> psycopg.Connection[TupleRow]:
    """Open one dedicated driver session, initialized exactly as an owned one is.

    The same codecs and the same session-compatibility refusal the shipped
    adapter applies to every connection it creates, because a harness session
    that decoded differently from the adapter's would grade the adapter against
    a database nobody runs.

    A refusal closes what it opened: a connection nothing may execute on is not
    one to hand back to a caller that would then have to remember it.
    """
    connection = psycopg.connect(
        conninfo,
        autocommit=autocommit,
        prepare_threshold=prepare_threshold,
        row_factory=tuple_row,
    )
    try:
        initialize_connection(connection)
    except BaseException:
        with contextlib.suppress(Exception):
            connection.close()
        raise
    return connection


class PostgresControl:
    """One separately owned psycopg session the harness executes through.

    Every verb forwards to the shipped scoped execution over the connection this
    control opened, so a statement the harness runs directly is translated and
    classified exactly as one an application's own Database would be. What it
    adds is the lifetime: ``close`` releases this session and nothing else.
    """

    def __init__(
        self,
        connection: psycopg.Connection[TupleRow],
        *,
        on_release: Callable[[PostgresControl], None] | None = None,
    ) -> None:
        self._connection = connection
        self._execution = PostgresConnection(connection)
        self._on_release = on_release

    @classmethod
    def open(  # pragma: no cover - opens a real session; the Docker lanes exercise it
        cls,
        conninfo: str,
        *,
        autocommit: bool = True,
        prepare_threshold: int | None = 5,
        on_release: Callable[[PostgresControl], None] | None = None,
    ) -> PostgresControl:
        """Open a dedicated session over ``conninfo``.

        ``autocommit=False`` is what a peer holding one transaction across several
        statements needs; ``prepare_threshold`` is the driver's own, exposed here
        because a connection that outlives a schema reset must disable it.
        """
        return cls(
            open_session(conninfo, autocommit=autocommit, prepare_threshold=prepare_threshold),
            on_release=on_release,
        )

    @property
    def dialect(self) -> Dialect:
        return self._execution.dialect

    @property
    def native(self) -> psycopg.Connection[TupleRow]:
        """This control's own driver session, for the harness's native proofs.

        A provider proof of the two JSONB loader slots has to ask a cursor for
        each result format, which is a driver fact with no neutral spelling. It
        is reachable here — on a session the harness opened and closes — and
        nowhere on a ``Database``: the point of removing the raw accessor is that
        no application can reach a connection it did not open, not that the
        harness cannot open one.
        """
        return self._connection

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return self._execution.execute(sql, binds, document_reads)

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return self._execution.execute_write(sql, binds)

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        return self._execution.transaction(body, isolation=isolation)

    def rollback(self) -> None:
        self._connection.rollback()

    def terminate_session(self, target: DatabaseConnection) -> None:
        """End ``target``'s session by asking the server, not its transport."""
        (row,) = target.execute(_BACKEND_PID, [])
        self.execute(_TERMINATE_BACKEND, [row["pid"]])

    def close(self) -> None:
        """Release this session, and report the release to whoever tracks it.

        A close that raises reports nothing: the session is still this control's
        as far as anyone can tell, so it stays on its opener's books for the
        teardown backstop to try again rather than being forgotten while alive.

        The execution over it is deliberately NOT revoked. A closed control is a
        closed driver session, and a statement run on one fails the way the
        driver fails it — which is what makes a genuinely closed connection the
        provider contract's reachable begin failure. Revocation is the
        acquisition contract's, where a scope ends while its connection lives on.
        """
        self._connection.close()
        if self._on_release is not None:
            self._on_release(self)


class ControlledScope:
    """One acquisition of the dedicated session, and the identity of that scope.

    It is an ordinary single-use :class:`~parallax.core.db_port.ConnectionContext`
    with one addition nothing production has: it is identifiable while it lasts,
    so a control action captured during THIS scope can tell that it is still
    THIS scope when it finally executes.
    """

    def __init__(self, runtime: ControlledRuntime) -> None:
        self._runtime = runtime
        self._execution: PostgresConnection | None = None
        self._spent = False
        self._cleanup_result: CleanupResult | None = None

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return self._cleanup_result

    def __enter__(self) -> DatabaseConnection:
        if self._spent:
            raise RuntimeError("a controlled connection context is entered exactly once")
        self._spent = True
        execution = self._runtime.admit(self)
        self._execution = execution
        return execution

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        del exc_type, exc, traceback
        execution = self._execution
        self._execution = None
        if execution is None:
            return
        execution.revoke()
        self._runtime.relinquish(self)
        # The dedicated session is not returned anywhere: it is this runtime's
        # for its whole life, so what ended is the exclusive use of it.
        self._cleanup_result = _RELINQUISHED


class ControlledRuntime:
    """A runtime over exactly ONE dedicated driver session.

    It is a real :class:`~parallax.core.db_port.DatabaseRuntime` — a Database
    composed over it acquires, executes, and relinquishes through the ordinary
    contract — and it manages no pool at all. That is the point: a session the
    harness may cancel, close, or tear down at the socket must be one nothing
    else can be handed, and a pool exists precisely to hand connections around.

    Exclusive use is enforced rather than assumed: a second overlapping
    acquisition is refused rather than quietly sharing the one session, because
    two overlapping scopes on one connection is the confusion the choreography
    this serves would otherwise be built on.
    """

    dialect: Dialect = POSTGRES

    def __init__(self, connection: psycopg.Connection[TupleRow]) -> None:
        self._connection = connection
        self._lock = threading.Lock()
        self._active: ControlledScope | None = None
        self._closed = False

    @property
    def pool_metrics(self) -> PoolMetricsSource | None:
        return None

    @property
    def native(self) -> psycopg.Connection[TupleRow]:
        """The dedicated session itself, for this module's control actions alone.

        Private to :mod:`parallax.conformance._postgres_control`: cancellation
        and the termination ladder are native facts, and nothing above this
        module names a driver connection.
        """
        return self._connection

    def connection(self) -> ConnectionContext:
        return ControlledScope(self)

    def admit(self, scope: ControlledScope) -> PostgresConnection:
        with self._lock:
            if self._closed:
                raise ConnectionAcquisitionError(
                    "this controlled runtime is closed, so it opens no new scope",
                    reason="closed",
                )
            if self._active is not None:
                raise ConnectionAcquisitionError(
                    "this controlled runtime serves one scope at a time and one is already open",
                    reason="queue_rejected",
                )
            self._active = scope
        return PostgresConnection(self._connection)

    def relinquish(self, scope: ControlledScope) -> None:
        with self._lock:
            if self._active is scope:
                self._active = None

    def holds(self, scope: ControlledScope | None) -> bool:
        """Whether ``scope`` is the acquisition this runtime is serving right now.

        What a delayed control action asks before it acts. Capturing a target is
        not permission to destroy it later: by then the scope that was stuck may
        have finished and another may hold the session, and acting on the
        captured native connection would reach that later scope's work.
        """
        with self._lock:
            return scope is not None and self._active is scope

    def active_scope(self) -> ControlledScope | None:
        with self._lock:
            return self._active

    def close(self) -> None:
        """Stop admitting scopes and retire the session this runtime owns.

        A pooled runtime hands its connections back to something that outlives
        it; this one has exactly one session and nothing to hand it to, so
        closing the runtime is what ends it. Quiet about a session the
        termination ladder already condemned: closing an already-closed
        connection establishes nothing new.
        """
        with self._lock:
            already, self._closed = self._closed, True
        if already:
            return
        with contextlib.suppress(Exception):
            self._connection.close()


class ControlledAdapter:
    """Configuration for one dedicated session: what a controlled Database connects from.

    It takes a connection string, never a live resource, so the runtime it opens
    owns the session it created and no caller can pair a Database with a session
    somebody else holds. Opening it twice would open two sessions; the execution
    below opens it exactly once.
    """

    dialect: Dialect = POSTGRES

    def __init__(
        self, conninfo: str, *, session: Callable[[], psycopg.Connection[TupleRow]] | None = None
    ) -> None:
        self._conninfo = conninfo
        # The internal seam the Docker-free control pins inject a session at.
        # Nothing production supplies it: a controlled runtime opens the session
        # it owns, and a caller that could hand one in could hand in one it also
        # holds.
        self._session = session
        self.opened: ControlledRuntime | None = None

    def open(self) -> ControlledRuntime:
        opener = self._session
        connection = opener() if opener is not None else open_session(self._conninfo)
        runtime = ControlledRuntime(connection)
        self.opened = runtime
        return runtime


class PostgresInterleavedExecution:
    """A dedicated psycopg session, the Database over it, and the ladder that ends it.

    The connection is this execution's own from the moment it exists: the handle
    is composed here from configuration rather than accepted, so no caller can
    pair a Database with a session it does not own, and a composition that
    refuses the model releases the session it had already opened rather than
    leaking it.

    Trust is declared by construction. Closing the driver connection tears down
    the OS-level socket a blocked call is waiting on — an operating-system
    guarantee rather than a hope, which is what :meth:`terminate_active`
    escalates through.
    """

    def __init__(
        self,
        adapter: ControlledAdapter,
        model: DomainModel | ServingModel,
        *,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
        on_release: Callable[[PostgresInterleavedExecution], None] | None = None,
    ) -> None:
        # A composition that refuses the model does so before the configuration
        # is opened, and one that fails after opening closes the runtime it was
        # handed — which is what retires this session, since the runtime owns it.
        self._database = handle.Database.connect(
            adapter, model, clock=clock, lifecycle_provider=lifecycle_provider
        )
        runtime = adapter.opened
        if runtime is None:  # pragma: no cover - a composed Database opened its runtime
            raise RuntimeError("a controlled Database composed no runtime")
        self._runtime = runtime
        self._on_release = on_release

    @classmethod
    def open(  # pragma: no cover - opens a real session; the Docker lanes exercise it
        cls,
        conninfo: str,
        model: DomainModel | ServingModel,
        *,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
        on_release: Callable[[PostgresInterleavedExecution], None] | None = None,
    ) -> PostgresInterleavedExecution:
        """Open a dedicated session for one choreography and compose its Database."""
        return cls(
            ControlledAdapter(conninfo),
            model,
            clock=clock,
            lifecycle_provider=lifecycle_provider,
            on_release=on_release,
        )

    @property
    def termination_ladder_trusted(self) -> bool:
        """Granted by construction: the ladder below ends in an OS-level teardown."""
        return True

    @property
    def database(self) -> handle.Database:
        return self._database

    @property
    def dialect(self) -> Dialect:
        return self._runtime.dialect

    def cancel_active(self) -> None:
        """Ask the server to interrupt the in-flight statement of the scope it captures.

        Thread-safe and non-destructive: it is callable from a thread other than
        the one blocked in the driver call, and a session it wakes stays usable.
        A cancellation request can itself fail or arrive too late, which is why
        the caller escalates to :meth:`terminate_active` rather than relying on it.

        The scope is captured first and revalidated immediately before the
        request goes out. A cancellation that started while one scope was stuck
        must not reach the work of a scope that opened after it: what would be
        interrupted then is a statement nobody asked to interrupt.
        """
        scope = self._runtime.active_scope()
        with contextlib.suppress(Exception):
            if self._runtime.holds(scope):
                self._runtime.native.cancel_safe()

    def terminate_active(self) -> TerminationReport:
        """Destroy the session serving the scope it captures, escalating a rung at a time.

        The driver connection's own ``close`` first; then genuine OS-level
        teardown of that connection's socket. Each rung is attempted only once
        the one above it has failed, and every failure is recorded rather than
        swallowed, so a caller can attach the whole trail to whatever it raises.

        Revalidated exactly as cancellation is, and for a stronger reason: a
        descriptor this would tear down can be recycled by a later connection,
        so acting on a captured target whose scope has ended risks destroying an
        unrelated session that now answers to the same number.
        """
        scope = self._runtime.active_scope()
        if not self._runtime.holds(scope):
            return TerminationReport(
                terminated=False,
                failures=("the scope this termination captured had already ended",),
            )
        return self._retire()

    def _retire(self) -> TerminationReport:
        failures: list[str] = []
        connection = self._runtime.native
        try:
            connection.close()
        except Exception as exc:
            failures.append(f"the underlying driver connection's close() raised {exc!r}")
        else:
            return TerminationReport(terminated=True)

        socket_failures = _teardown_socket(connection)
        failures.extend(socket_failures)
        return TerminationReport(terminated=not socket_failures, failures=tuple(failures))

    def close(self) -> None:
        """Release this execution: its Database first, then its session.

        Quiet by design: the lane closes every execution it opened on its way
        out, including one the termination ladder already condemned, and a
        condemned session refusing to close again adds nothing to the report that
        ladder already returned.
        """
        with contextlib.suppress(Exception):
            self._database.close()
        with contextlib.suppress(Exception):
            self._runtime.close()
        if self._on_release is not None:
            self._on_release(self)


def _teardown_socket(connection: psycopg.Connection[TupleRow]) -> tuple[str, ...]:
    """Force the driver connection's socket down from another thread.

    ``shutdown(SHUT_RDWR)`` is the thread-safe way to make a blocking syscall on
    that descriptor return with an OS-level error, unlike closing the descriptor
    underneath a call still in flight. The descriptor is closed afterwards either
    way: this connection is already condemned, so closing it too loses nothing,
    and a failed shutdown must not leave it open.
    """
    try:
        fd = connection.fileno()
    except Exception as exc:
        return (f"the underlying connection's fileno() raised {exc!r}",)
    try:
        sock = socket.socket(fileno=fd)
    except Exception as exc:
        with contextlib.suppress(Exception):
            os.close(fd)
        return (f"OS-level socket(fileno={fd}) raised {exc!r}",)
    failures: list[str] = []
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception as exc:
        failures.append(f"OS-level shutdown(fd={fd}) raised {exc!r}")
    finally:
        with contextlib.suppress(Exception):
            sock.close()
    return tuple(failures)
