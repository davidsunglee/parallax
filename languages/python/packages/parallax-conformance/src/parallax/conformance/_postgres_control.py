"""``parallax.conformance._postgres_control`` — the native side of the controls.

Every psycopg-shaped fact the harness's own sessions need lives here: opening a
dedicated connection, ending another session through the server, and the
escalation that destroys a session whose own thread is parked in driver I/O. The
protocols these implement carry none of it
(:mod:`parallax.conformance._database_control`), so the engine consumes declared
capabilities and this module is the only place a control knows it is Postgres.

Nothing else may import it eagerly: naming a control must not load the driver, so
the provisioner reaches this module inside the call that opens one, exactly as it
already reaches the adapter class itself.
"""

from __future__ import annotations

import contextlib
import os
import socket
from typing import TYPE_CHECKING, Final

from parallax.conformance._database_control import TerminationReport
from parallax.postgres import PostgresAdapter
from parallax.snapshot import handle

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import psycopg
    from psycopg.rows import TupleRow

    from parallax.core.db_port import (
        Bind,
        DbPort,
        DocumentReadOrdinals,
        IsolationLevel,
        Row,
        TransactionOutcome,
    )
    from parallax.core.dialect import Dialect
    from parallax.core.entity import DomainModel
    from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
    from parallax.core.unit_work import Clock
    from parallax.snapshot.handle import ServingModel

__all__ = ["PostgresControl", "PostgresInterleavedExecution"]

_BACKEND_PID: Final[str] = "select pg_backend_pid() as pid"
_TERMINATE_BACKEND: Final[str] = "select pg_terminate_backend(%s) as terminated"


class PostgresControl:
    """One separately owned psycopg session the harness executes through.

    Every verb forwards to the adapter over the connection this control opened,
    so a statement the harness runs directly is translated and classified exactly
    as one an application's own Database would be. What it adds is the lifetime:
    ``close`` releases this session and nothing else.
    """

    def __init__(
        self,
        adapter: PostgresAdapter,
        *,
        on_release: Callable[[PostgresControl], None] | None = None,
    ) -> None:
        self._adapter = adapter
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
            PostgresAdapter.connect(
                conninfo, autocommit=autocommit, prepare_threshold=prepare_threshold
            ),
            on_release=on_release,
        )

    @property
    def dialect(self) -> Dialect:
        return self._adapter.dialect

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return self._adapter.execute(sql, binds, document_reads)

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return self._adapter.execute_write(sql, binds)

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        return self._adapter.transaction(body, isolation=isolation)

    def rollback(self) -> None:
        self._adapter.connection.rollback()

    def terminate_session(self, target: DbPort) -> None:
        """End ``target``'s session by asking the server, not its transport."""
        (row,) = target.execute(_BACKEND_PID, [])
        self.execute(_TERMINATE_BACKEND, [row["pid"]])

    def close(self) -> None:
        """Release this session, and report the release to whoever tracks it.

        A close that raises reports nothing: the session is still this control's
        as far as anyone can tell, so it stays on its opener's books for the
        teardown backstop to try again rather than being forgotten while alive.
        """
        self._adapter.close()
        if self._on_release is not None:
            self._on_release(self)


class PostgresInterleavedExecution:
    """A dedicated psycopg session, the Database over it, and the ladder that ends it.

    The connection is this execution's own from the moment it is handed over: the
    handle is composed here rather than accepted, so no caller can pair a Database
    with a session it does not own, and a composition that refuses the model
    releases the session it had already opened rather than leaking it.

    Trust is declared by construction. The adapter's own ``close`` tears down the
    wrapped driver connection, whose ``close`` tears down the OS-level socket the
    blocked call is waiting on — an operating-system guarantee rather than a hope,
    which is what :meth:`terminate_active` escalates through.
    """

    def __init__(
        self,
        adapter: PostgresAdapter,
        model: DomainModel | ServingModel,
        *,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
        on_release: Callable[[PostgresInterleavedExecution], None] | None = None,
    ) -> None:
        self._adapter = adapter
        try:
            self._database = handle.Database(
                adapter, model, clock=clock, lifecycle_provider=lifecycle_provider
            )
        except BaseException:
            with contextlib.suppress(Exception):
                adapter.close()
            raise
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
            PostgresAdapter.connect(conninfo, autocommit=True),
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
        return self._adapter.dialect

    def cancel_active(self) -> None:
        """Ask the server to interrupt this session's in-flight statement.

        Thread-safe and non-destructive: it is callable from a thread other than
        the one blocked in the driver call, and a session it wakes stays usable.
        A cancellation request can itself fail or arrive too late, which is why
        the caller escalates to :meth:`terminate_active` rather than relying on it.
        """
        with contextlib.suppress(Exception):
            self._adapter.connection.cancel_safe()

    def terminate_active(self) -> TerminationReport:
        """Destroy this session, escalating one rung at a time.

        The adapter's own ``close`` first; then the driver connection underneath
        it; then genuine OS-level teardown of that connection's socket. Each rung
        is attempted only once the one above it has failed, and every failure is
        recorded rather than swallowed, so a caller can attach the whole trail to
        whatever it raises.
        """
        failures: list[str] = []
        try:
            self._adapter.close()
        except Exception as exc:
            failures.append(f"the session's own close() raised {exc!r}")
        else:
            return TerminationReport(terminated=True)

        connection = self._adapter.connection
        try:
            connection.close()
        except Exception as exc:
            failures.append(f"the underlying driver connection's close() raised {exc!r}")
        else:
            return TerminationReport(terminated=True, failures=tuple(failures))

        socket_failures = _teardown_socket(connection)
        failures.extend(socket_failures)
        return TerminationReport(terminated=not socket_failures, failures=tuple(failures))

    def close(self) -> None:
        """Release this execution's session.

        Quiet by design: the lane closes every execution it opened on its way
        out, including one the termination ladder already condemned, and a
        condemned session refusing to close again adds nothing to the report that
        ladder already returned.
        """
        with contextlib.suppress(Exception):
            self._adapter.close()
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
