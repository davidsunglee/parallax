"""Opening a ready Postgres runtime, admitting work to it, and closing it.

Three responsibilities, in the order they matter.

**Readiness.** :func:`open_runtime` returns only a runtime that has proved it
can execute. It builds the native pool, waits for a positive retained minimum
where one is configured, then acquires a real connection and runs one probe
through the same initialized execution an application gets — an integer, a
neutral infinite timestamp, and a decoded JSONB document — and requires that
connection to come back before publishing anything. Waiting for a minimum is not
that proof: with no minimum to wait for it proves nothing at all, and even with
one it says a connection exists rather than that a statement works.

All of readiness shares ONE deadline, checked between phases and never restarted.
It is a cooperative budget: it stops the next phase from starting, and it cannot
interrupt a native call already in flight or the cleanup that must follow one.

**Admission.** Starting an acquisition reserves no right to execute. The
deadline and the runtime's open state are checked together, once, immediately
before the acquired connection is handed over. A scope admitted before a close
may finish everything it was going to do, including statements it has not issued
yet; anything needing a NEW acquisition after that close is refused.

**Shutdown.** :meth:`PostgresRuntime.close` is idempotent and permanent. It stops
admission, detaches the metrics source, then closes the native pool, which fails
waiting and future acquisitions, closes idle connections, and closes checked-out
connections as they come back. It does not wait for borrowers and does not
interrupt their SQL.

The runtime also publishes that source — one stable object for its whole life,
created with it and detached before the pool is torn down — so an exporter reads
capacity, idleness and queue depth without taking a connection or running a
statement.
"""

from __future__ import annotations

import contextlib
import threading
from time import monotonic
from typing import Final

import psycopg_pool

from parallax.core.base import INFINITY
from parallax.core.db_port import (
    CleanupIssue,
    ConnectionAcquisitionError,
    ConnectionContext,
    DatabaseStartupError,
    PoolMetricsSource,
    Row,
    StartupPhase,
    Unrelinquished,
    report_resource_issues,
)
from parallax.core.diagnostics import diagnostic_for
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres._connection import CONNECT_KWARGS, ConnectionPreparation
from parallax.postgres._context import NativePool, PostgresConnectionContext
from parallax.postgres._options import PoolOptions, RetentionOptions
from parallax.postgres._pool_metrics import PostgresPoolMetrics

__all__ = ["PROBE_SQL", "PostgresRuntime", "open_runtime"]

PROBE_SQL: Final = """SELECT
    1 AS ready,
    'infinity'::timestamptz AS temporal_bound,
    '{"ready": true}'::jsonb AS document"""
"""The one statement a runtime runs before it is usable.

It proves the three decodings the read path cannot work without and that a bare
connectivity check does not exercise: an ordinary integer, the neutral sentinel a
temporal interval's open upper bound reads back as, and a structured document
decoded to a mapping. It reads no model, opens no explicit transaction, and
registers nothing — the connection it runs on was already initialized like every
other. It is a smoke probe, not a substitute for the codec suites.
"""

_CLOSED = "this Database is closed, so it opens no new database connection"


class PostgresRuntime:
    """One independent running Postgres resource, owned by one connected handle.

    Two runtimes built from one configuration share nothing: closing either
    leaves the other working, which is what makes reusing configuration safe.
    """

    dialect: Dialect = POSTGRES

    __slots__ = ("_admission", "_closed", "_metrics", "_options", "_pool", "_preparation")

    def __init__(
        self,
        pool: NativePool,
        options: RetentionOptions,
        preparation: ConnectionPreparation,
    ) -> None:
        self._pool = pool
        self._options = options
        self._preparation = preparation
        self._metrics = PostgresPoolMetrics(pool)
        self._closed = False
        # Held only across the two field reads that decide admission, never
        # across a checkout, a statement, or a callback: an acquisition that
        # blocks must not be able to block a close.
        self._admission = threading.Lock()

    @property
    def pool_metrics(self) -> PoolMetricsSource | None:
        """This runtime's one source, the same object for its whole life.

        A pool is what this runtime manages, so there is always something to
        measure and this is never absent. It stays the same object across the
        close as well: an exporter holding it keeps a handle that answers
        detached rather than a handle that has gone stale.
        """
        return self._metrics

    def connection(self) -> ConnectionContext:
        """A fresh single-use acquisition under this runtime's acquisition budget."""
        return self.acquisition(monotonic() + self._options.acquire_timeout)

    def acquisition(self, deadline: float) -> PostgresConnectionContext:
        """A fresh acquisition bounded by ``deadline`` rather than by the ordinary budget.

        Startup uses this: readiness has one budget of its own that the
        acquisition it makes has to fit inside, rather than an ordinary
        acquisition timeout added to it.
        """
        return PostgresConnectionContext(self._pool, self._admit, deadline, self._preparation)

    def close(self) -> None:
        """Stop admitting work and close the native pool. Idempotent and permanent.

        Admission stops first, so nothing is admitted while the pool is being
        torn down. The native close then refuses waiting and future checkouts,
        closes what is idle, and closes what comes back later; it neither drains
        borrowers nor interrupts their statements, so an operation already
        running finishes on the connection it holds and that connection is
        closed when it is returned.

        The metrics source detaches between the two, so every sample begun
        after that reaches nothing — and a native close that is slow or that
        fails delays nothing about that, because detachment has already happened
        by then. A sample already inside the native read may complete and report
        what it measured; that read copies bookkeeping and waits for nothing
        this close holds.

        Problems closing are reported through the restricted resource logger and
        never raised: close is what a caller runs while unwinding, and a handle
        that refused to close would leave them nothing better to do.
        """
        with self._admission:
            if self._closed:
                return
            self._closed = True
        self._metrics.detach()
        try:
            self._pool.close()
        except Exception as exc:
            report_resource_issues("shutdown", _shutdown_issue(exc))

    def _admit(self, deadline: float) -> None:
        """Decide, in one critical section, whether this acquisition may proceed.

        Expiry and closure together, because either alone can change while the
        other is being asked. A late native success is refused here rather than
        admitted: the caller has already been waiting past what it asked for,
        and its own timeout handling is a better answer than work starting after
        the budget it was given.
        """
        with self._admission:
            if self._closed:
                raise ConnectionAcquisitionError(_CLOSED, reason="closed")
            if monotonic() >= deadline:
                raise ConnectionAcquisitionError(
                    "a database connection arrived after the acquisition timeout, so no "
                    "statement was run on it",
                    reason="timeout",
                )


def open_runtime(
    conninfo: str, options: RetentionOptions, prepare_threshold: int | None
) -> PostgresRuntime:
    """Open one ready runtime over ``conninfo``, or raise having released what it took.

    Every failure below publishes no runtime: the native pool is closed on the
    way out, and a startup connection that was already acquired is relinquished
    through the same cleanup path an ordinary operation uses — which reports
    what it established, so a disposal or handoff that itself failed is stated
    rather than assumed away.
    """
    deadline = monotonic() + options.startup_timeout
    preparation = ConnectionPreparation()
    pool = _build_pool(conninfo, options, prepare_threshold, preparation)
    runtime = PostgresRuntime(pool, options, preparation)
    try:
        _await_minimum(pool, options, deadline, preparation)
        _probe(runtime, deadline)
    except BaseException:
        with contextlib.suppress(Exception):
            pool.close()
        raise
    return runtime


def _build_pool(
    conninfo: str,
    options: RetentionOptions,
    prepare_threshold: int | None,
    preparation: ConnectionPreparation,
) -> NativePool:
    """Create and open the native pool this runtime manages.

    ``open=False`` then an explicit open, because the driver's implicit opening
    is a deprecated default whose behavior is documented to change. The
    connection keyword arguments are the ones this adapter owns — autocommit,
    row shape, and prepared-statement policy — and ``configure`` is where every
    connection, however it came to exist, is initialized and checked.

    No ``reset`` callback is configured. Native return already brings a
    connection back to a usable state or discards it, and a reset callback runs
    after that decision rather than instead of it — so it could not prevent an
    unexpected transaction being rolled back for reuse, which is exactly the
    outcome this adapter refuses by disposing of such a connection itself.
    """
    kwargs: dict[str, object] = {**CONNECT_KWARGS, "prepare_threshold": prepare_threshold}
    check = psycopg_pool.ConnectionPool.check_connection if options.validate_on_checkout else None
    pool: NativePool
    if isinstance(options, PoolOptions):
        pool = psycopg_pool.ConnectionPool(
            conninfo,
            kwargs=kwargs,
            open=False,
            configure=preparation,
            check=check,
            min_size=options.min_size,
            max_size=options.max_size,
            timeout=options.acquire_timeout,
            max_waiting=options.max_waiting,
            max_idle=options.max_idle,
            max_lifetime=options.max_lifetime,
            reconnect_timeout=options.reconnect_timeout,
            num_workers=options.num_workers,
        )
    else:
        pool = psycopg_pool.NullConnectionPool(
            conninfo,
            kwargs=kwargs,
            open=False,
            configure=preparation,
            check=check,
            max_size=options.max_size,
            timeout=options.acquire_timeout,
            max_waiting=options.max_waiting,
            max_lifetime=options.max_lifetime,
            reconnect_timeout=options.reconnect_timeout,
            num_workers=options.num_workers,
        )
    try:
        pool.open()
    except Exception as exc:
        with contextlib.suppress(Exception):
            pool.close()
        raise DatabaseStartupError(
            "the database runtime's connection pool could not be opened", phase="open"
        ) from exc
    return pool


def _await_minimum(
    pool: NativePool,
    options: RetentionOptions,
    deadline: float,
    preparation: ConnectionPreparation,
) -> None:
    """Wait for the retained minimum, where there is one to wait for.

    Skipped for a zero minimum and for on-demand retention, because neither has
    retained capacity: the native wait would either return immediately having
    proved nothing, or establish a connection of its own that is then thrown
    away. The probe below is what proves readiness in every mode, so nothing is
    lost by skipping this one.

    Filling happens on the runtime's own background path, where an initialization
    refusal is retried rather than reported, so all this wait can see is that
    time ran out. Where such a refusal is on record it is stated as the failure
    instead: a configuration every connection is refused under is what an
    operator has to fix, and "timed out" names none of it.
    """
    if not isinstance(options, PoolOptions) or options.min_size <= 0:
        return
    remaining = _remaining(deadline, "minimum_ready")
    try:
        pool.wait(timeout=remaining)
    except Exception as exc:
        refusal = preparation.last_refusal
        raise DatabaseStartupError(
            "no database connection this runtime opened became usable"
            if refusal is not None
            else "the database runtime did not reach its minimum number of connections in time",
            phase="minimum_ready",
        ) from (refusal if refusal is not None else exc)


def _probe(runtime: PostgresRuntime, deadline: float) -> None:
    """Acquire one real connection, prove it decodes, and give it back.

    Startup owns no model and adopts no edition, so this creates no execution
    and reports through no observer: it runs on an initialized connection
    exactly as later work will, and what it establishes is that later work can
    run at all.
    """
    _remaining(deadline, "acquire")
    resource = runtime.acquisition(deadline)
    try:
        connection = resource.__enter__()
    except ConnectionAcquisitionError as exc:
        report_resource_issues("startup", resource.cleanup_result)
        raise DatabaseStartupError(
            "no database connection could be acquired while starting up",
            phase="acquire",
            cleanup_result=resource.cleanup_result,
        ) from exc
    try:
        _check_probe(connection.execute(PROBE_SQL, []))
    except BaseException as exc:
        resource.__exit__(type(exc), exc, exc.__traceback__)
        report_resource_issues("startup", resource.cleanup_result)
        if not isinstance(exc, Exception):
            # The connection is released either way, but a fatal or
            # control-flow exception keeps its own propagation: an interpreter
            # being torn down is not a runtime that failed to become ready, and
            # a caller unwinding must not have that turned into an ordinary
            # startup error it might handle.
            raise
        raise DatabaseStartupError(
            "the database runtime's startup probe did not return what it asked for",
            phase="probe",
            cleanup_result=resource.cleanup_result,
        ) from exc
    resource.__exit__(None, None, None)
    result = resource.cleanup_result
    report_resource_issues("startup", result)
    if isinstance(result, Unrelinquished):
        raise DatabaseStartupError(
            "the database runtime's startup connection could not be relinquished",
            phase="release",
            cleanup_result=result,
        )
    _remaining(deadline, "release")


def _check_probe(rows: list[Row]) -> None:
    if len(rows) != 1:
        raise ValueError(f"the startup probe returned {len(rows)} rows rather than one")
    (row,) = rows
    if row.get("ready") != 1:
        raise ValueError("the startup probe did not read its integer back")
    if row.get("temporal_bound") is not INFINITY:
        raise ValueError("the startup probe did not read an unbounded instant back")
    if row.get("document") != {"ready": True}:
        raise ValueError("the startup probe did not read its structured document back")


def _remaining(deadline: float, phase: StartupPhase) -> float:
    """The startup budget left, refusing to begin ``phase`` without any.

    Checked between phases rather than inside them: the budget stops the next
    step from starting and makes no claim about interrupting one already running.
    """
    remaining = deadline - monotonic()
    if remaining <= 0.0:
        raise DatabaseStartupError(
            "the database runtime did not become ready within its startup timeout",
            phase=phase,
        )
    return remaining


def _shutdown_issue(exc: Exception) -> Unrelinquished:
    return Unrelinquished(
        (CleanupIssue(phase="return", code="handoff-failed", diagnostic=diagnostic_for(exc)),)
    )
