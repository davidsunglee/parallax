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
    from collections.abc import Generator, Sequence
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


def initialized_session(
    connection: psycopg.Connection[TupleRow],
) -> psycopg.Connection[TupleRow]:
    """``connection`` after the setup every owned connection gets, or closed and re-raised.

    The same codecs and the same session-compatibility refusal the shipped
    adapter applies to every connection it creates, because a harness session
    that decoded differently from the adapter's would grade the adapter against
    a database nobody runs.

    A refusal closes what it opened: a connection nothing may execute on is not
    one to hand back to a caller that would then have to remember it. It takes a
    connection somebody else opened and so acquires nothing itself, which is what
    lets the refusal be proven without a server.
    """
    try:
        initialize_connection(connection)
    except BaseException:
        with contextlib.suppress(Exception):
            connection.close()
        raise
    return connection


def open_session(  # pragma: no cover - opens a real session; the Docker lanes exercise it
    conninfo: str, *, autocommit: bool = True, prepare_threshold: int | None = 5
) -> psycopg.Connection[TupleRow]:
    """Open one dedicated driver session, initialized exactly as an owned one is."""
    return initialized_session(
        psycopg.connect(
            conninfo,
            autocommit=autocommit,
            prepare_threshold=prepare_threshold,
            row_factory=tuple_row,
        )
    )


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
        if execution is None:
            return
        # Relinquished even if revocation does not complete: the runtime serves
        # one scope at a time, so a scope that failed to give the session back
        # would leave it refusing every later acquisition.
        try:
            execution.revoke()
        finally:
            self._execution = None
            self._runtime.relinquish(self)
            # The dedicated session is not returned anywhere: it is this
            # runtime's for its whole life, so what ended is the exclusive use
            # of it.
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
        self._state = threading.Lock()
        # Held for the whole of a control action, and taken BEFORE the state
        # lock by anything that admits a scope. Revalidating a captured scope
        # and acting on it have to be one step: between a check and an act, a
        # scope admitted on this session would be reached by an action nobody
        # validated against it. Ending a scope needs the state lock only, so a
        # worker that finishes while an action is in flight is never held up by
        # it — what is excluded is the NEXT scope, which is what the action
        # must not reach.
        self._admission = threading.Lock()
        # Held across every native end of this session and the completion it
        # publishes, and taken BEFORE the state lock. Retirement is reached from
        # paths that run on different threads — a close, the relinquishment a
        # deferred close waits for, and the termination ladder — and two of them
        # that each observed a live session would otherwise both close the same
        # driver connection, which is libpq finishing a connection another
        # thread is already finishing. Reentrant so that the observer retirement
        # notifies may reach this runtime again without deadlocking against the
        # claim its own retirement holds.
        self._retirement = threading.RLock()
        self._active: ControlledScope | None = None
        self._closed = False
        self._retired = False
        self._on_retired: Callable[[], None] | None = None

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
        with self._admission, self._state:
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
        with self._state:
            if self._active is scope:
                self._active = None
            deferred = self._closed and self._active is None
        if deferred:
            # A close arrived while this scope held the session, so retirement
            # waited for the borrower exactly as a pooled connection's close
            # waits for it to come back. Nothing here can be raised at — the
            # caller is leaving a scope, not closing a runtime — so a refusal is
            # dropped and stays readable as an unretired runtime.
            with contextlib.suppress(Exception):
                self._retire_session()

    @contextlib.contextmanager
    def holding(self, scope: ControlledScope | None) -> Generator[bool]:
        """Whether ``scope`` is the acquisition being served — answered for the whole block.

        What a delayed control action asks before it acts, and it asks for as
        long as it acts. Capturing a target is not permission to destroy it
        later: by then the scope that was stuck may have finished and another
        may hold the session, and acting on the captured native connection would
        reach that later scope's work. Answering and acting are therefore one
        step, with admission held shut across it, so there is no window for a
        next scope to arrive into.
        """
        with self._admission:
            with self._state:
                held = scope is not None and self._active is scope
            yield held

    def active_scope(self) -> ControlledScope | None:
        with self._state:
            return self._active

    def close(self) -> None:
        """Stop admitting scopes and retire the session this runtime owns.

        A pooled runtime hands its connections back to something that outlives
        it; this one has exactly one session and nothing to hand it to, so
        closing the runtime is what ends it. It does NOT end it under a
        borrower: a scope admitted before this close finishes everything it was
        going to do, and the session is retired when that scope relinquishes —
        which is what a pool does when a checked-out connection comes back.

        Never raises, because a runtime is closed by a caller that is unwinding.
        What a caller may ask afterwards is :attr:`retired`.

        Repeatable rather than once-only: a close the driver refused leaves the
        session alive and still this runtime's, so a later close tries again —
        which is the whole of what an opener's teardown backstop can do about
        one. A close after retirement reaches no driver call, so trying again
        costs nothing where there is nothing left to end.
        """
        with self._state:
            self._closed = True
            deferred = self._active is not None
        if deferred:
            return
        with contextlib.suppress(Exception):
            self._retire_session()

    @property
    def retired(self) -> bool:
        """Whether this runtime's session is known to be gone.

        False while a borrower still holds it, and false after a close the
        driver refused: a session nobody can show is dead is still this
        runtime's, which is what its opener needs in order to decide whether to
        forget it.
        """
        with self._state:
            return self._retired

    def condemn(self) -> None:
        """Record that the termination ladder destroyed this session.

        Termination is not a close and does not go through one, but what it
        leaves behind is a retired runtime: closing that session again would
        establish nothing new, and its opener may forget it.
        """
        with self._retirement:
            with self._state:
                self._closed = True
            self._complete_retirement()

    @contextlib.contextmanager
    def retiring(self) -> Generator[bool]:
        """The claim on ending this session — true while there is still a session to end.

        What every path that destroys this session enters: it holds the claim
        across the native teardown and the completion that publishes it, so
        exactly one path ends the session and every other one finds it already
        ended. Without that, two paths could each read an unretired runtime and
        both close the one driver connection.

        The claim is released whether or not retirement was reached, which is
        what keeps a refused close retryable: what a later attempt observes is
        the retirement flag, not a claim somebody once took.
        """
        with self._retirement:
            with self._state:
                pending = not self._retired
            yield pending

    def report_retirement_to(self, observer: Callable[[], None]) -> None:
        """Call *observer* once this session is gone, immediately if it already is.

        Retirement is not always finished by the caller that asked for it: a
        close under a borrower completes on the thread that relinquishes, which
        can be long afterwards and is never the closer's own. An opener deciding
        whether it may forget this runtime therefore cannot learn the answer by
        asking :attr:`retired` once, and this is how it is told instead.

        The observer runs once and is dropped; a runtime whose session never
        retires never runs it, which is what keeps a live session on its opener's
        books.
        """
        with self._state:
            retired = self._retired
            if not retired:
                self._on_retired = observer
        if retired:
            observer()

    def _retire_session(self) -> None:
        with self.retiring() as pending:
            if not pending:
                return
            self._connection.close()
            self._complete_retirement()

    def _complete_retirement(self) -> None:
        """Record the session as gone and tell whoever asked to be told.

        The one completion of retirement, whichever path reached it: a close,
        the relinquishment that a deferred close was waiting for, or the
        termination ladder. Retirement and the notification that ends the
        opener's bookkeeping are the same transition, so nothing can complete
        one without the other. Called under :meth:`retiring`, which is what
        makes it the transition the whole teardown it completes was claimed for.
        """
        with self._state:
            self._retired = True
            observer, self._on_retired = self._on_retired, None
        if observer is not None:
            observer()


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
        with contextlib.suppress(Exception), self._runtime.holding(scope) as still_serving:
            if still_serving:
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
        with self._runtime.holding(scope) as still_serving:
            if not still_serving:
                return TerminationReport(
                    terminated=False,
                    failures=("the scope this termination captured had already ended",),
                )
            return self._retire()

    def _retire(self) -> TerminationReport:
        """Destroy this execution's session, under the runtime's claim on ending it.

        The ladder's rungs are native teardowns of the one connection a close or
        a borrower's deferred retirement would also end, so it descends them
        holding the same claim those paths take. Against a session another path
        already retired there is nothing left to descend, and the report says
        exactly that: this attempt reached no rung, so it established nothing,
        and the miss is recorded rather than dressed up as a termination this
        escalation achieved.
        """
        with self._runtime.retiring() as pending:
            if not pending:
                return TerminationReport(
                    terminated=False,
                    failures=("this session had already been retired, so no rung was attempted",),
                )
            failures: list[str] = []
            connection = self._runtime.native
            try:
                connection.close()
            except Exception as exc:
                failures.append(f"the underlying driver connection's close() raised {exc!r}")
            else:
                self._runtime.condemn()
                return TerminationReport(terminated=True)

            socket_failures = _teardown_socket(connection)
            failures.extend(socket_failures)
            if not socket_failures:
                self._runtime.condemn()
            return TerminationReport(terminated=not socket_failures, failures=tuple(failures))

    def close(self) -> None:
        """Release this execution: its Database first, then its session.

        Quiet by design: the lane closes every execution it opened on its way
        out, including one the termination ladder already condemned, and a
        condemned session refusing to close again adds nothing to the report that
        ladder already returned.

        The release is reported to the opener once the session is gone — because
        the ladder condemned it, because this close retired it, or because the
        borrower that was holding it relinquished afterwards and the deferred
        retirement completed then. That last one arrives on the borrower's
        thread, which is why the report is asked for rather than tested here: a
        close that only looked once would leave a dead execution on its opener's
        books until teardown. A session that would not close at all is still this
        execution's as far as anyone can tell, and stays on those books for the
        teardown backstop rather than being forgotten while alive.
        """
        with contextlib.suppress(Exception):
            self._database.close()
        with contextlib.suppress(Exception):
            self._runtime.close()
        self._runtime.report_retirement_to(self._report_release)

    def _report_release(self) -> None:
        released, self._on_release = self._on_release, None
        if released is not None:
            released(self)


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
