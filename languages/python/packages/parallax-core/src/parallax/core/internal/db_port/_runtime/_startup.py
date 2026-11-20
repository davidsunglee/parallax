from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Literal

from parallax.core.internal.db_port import (
    ConnectionAcquisitionError,
    DatabaseStartupError,
    ProbeMismatch,
    ReleaseUnconfirmed,
    report_resource_issues,
)
from parallax.core.internal.db_port._runtime._context import OUTAGE_REASONS
from parallax.core.internal.db_port._runtime._dial_record import DialLedger
from parallax.core.internal.db_port._runtime._pooled_route import PooledRoute
from parallax.core.internal.db_port._runtime._pooled_runtime import PooledRuntime

if TYPE_CHECKING:
    from collections.abc import Mapping

    from parallax.core.internal.db_port import (
        CleanupResult,
        DatabaseRuntime,
        NativeDriver,
        PoolPurpose,
        Route,
        RouteCapabilities,
        StartupPhase,
    )
    from parallax.core.internal.dialect import Dialect

__all__ = ["ReaderStartup", "open_runtime"]

ReaderStartup = Literal["deferrable", "required"]
"""Whether an unavailable reader may leave startup to finish its proof later."""


class _ReadinessFailure(Exception):
    """A route's readiness failed, and whether that failure was only an outage.

    An outage is a failure whose only finding is that no usable connection was
    obtained within the budget: the route was unreachable, its session was lost
    with no replacement refused as anything worse, a connection arrived only
    after the budget, or the budget ran out with nothing on record but an
    unavailable dial. Anything else — a refused credential or login, a session
    the codecs cannot run under, a probe that read back the wrong thing or
    another login, an unconfirmed release, a full queue — says more than that,
    and deferral waits out nothing more.
    """

    def __init__(self, error: DatabaseStartupError, *, outage: bool) -> None:
        super().__init__(str(error))
        self.error = error
        self.outage = outage


def open_runtime[C, A](
    driver: NativeDriver[C, A],
    /,
    *,
    dialect: Dialect,
    routes: Mapping[Route, RouteCapabilities],
    acquire_timeout: float,
    startup_timeout: float,
    reader_startup: ReaderStartup,
) -> DatabaseRuntime[A]:
    """Open one ready runtime serving ``routes`` through ``driver``, or raise
    :class:`DatabaseStartupError` having attempted to release what it took.

    ``routes`` is the declaration the runtime publishes: it always names the
    writer, and a reader pool opens only where it names a reader. Every pool
    opens before any is proved, so a reader pool that dials in the background
    does so while the writer is being proved, and the two share the one
    budget's wall-clock time.
    The writer must prove itself; the reader then proves the same login within
    what remains. Where ``reader_startup`` permits, an unavailable reader stays
    pending until a connection proves it. The writer's reservation pool opens
    beside them holding no connection, and the writer's proof stands for it.

    Every failure below publishes no runtime: every pool opened so far has its
    close attempted on the way out, and a startup connection that was already acquired is
    released through the same cleanup path an ordinary operation uses — which
    reports what it established, so a disposal or handoff that itself failed is
    stated rather than assumed away.
    """
    deadline = monotonic() + startup_timeout
    opened: list[PooledRoute[C]] = []
    try:
        writer_route = _open_route(driver, "writer", "application")
        opened.append(writer_route)
        reader_route = None
        if "reader" in routes:
            reader_route = _open_route(driver, "reader", "application")
            opened.append(reader_route)
        reservation_route = _open_route(driver, "writer", "reservation")
        opened.append(reservation_route)
        runtime = PooledRuntime(
            driver,
            dialect=dialect,
            routes=routes,
            writer=writer_route,
            reader=reader_route,
            reservation=reservation_route,
            acquire_timeout=acquire_timeout,
        )
        try:
            login = _prove_route(runtime, driver, writer_route, deadline, None)
        except _ReadinessFailure as failure:
            raise failure.error from failure.error.__cause__
        writer_route.start_verified()
        # The writer's proof is the reservation pool's: it dials the same
        # endpoint with the same credentials.
        reservation_route.start_verified()
        runtime._complete_startup(login)  # pyright: ignore[reportPrivateUsage] - module-owned startup transition
        if reader_route is not None:
            _start_reader(runtime, driver, reader_route, deadline, login, reader_startup)
    except BaseException:
        _unwind(opened)
        raise
    return runtime


def _open_route[C, A](
    driver: NativeDriver[C, A], route: Route, purpose: PoolPurpose
) -> PooledRoute[C]:
    """Open ``route``'s pool for ``purpose`` through ``driver``, unproven.

    The driver releases whatever it built before raising, so a pool that would
    not open has nothing left to close.
    """
    dial_ledger = DialLedger()
    try:
        pool = driver.open_pool(route, purpose, dial_ledger)
    except Exception as exc:
        name = route if purpose == "application" else f"{route}-{purpose}"
        raise DatabaseStartupError(
            f"the database runtime's {name} connection pool could not be opened",
            route=route,
            phase="open",
        ) from exc
    return PooledRoute(route, pool, dial_ledger, purpose)


def _unwind[C](opened: list[PooledRoute[C]]) -> None:
    """Abandon every route opened, the latest first; an interrupt propagates
    only once each has been attempted."""
    interrupted: BaseException | None = None
    for route in reversed(opened):
        try:
            route.abandon()
        except BaseException as exc:
            if interrupted is None:
                interrupted = exc
    if interrupted is not None:
        raise interrupted


def _start_reader[C, A](
    runtime: PooledRuntime[C, A],
    driver: NativeDriver[C, A],
    route: PooledRoute[C],
    deadline: float,
    login: str,
    reader_startup: ReaderStartup,
) -> None:
    try:
        _prove_route(runtime, driver, route, deadline, login)
    except _ReadinessFailure as failure:
        if failure.outage and reader_startup == "deferrable":
            route.start_pending()
            return
        raise failure.error from failure.error.__cause__
    route.start_verified()


def _prove_route[C, A](
    runtime: PooledRuntime[C, A],
    driver: NativeDriver[C, A],
    route: PooledRoute[C],
    deadline: float,
    expected_login: str | None,
) -> str:
    """Acquire one real connection, prove it, capture its login, and give it back.

    Startup owns no model and adopts no edition, so this runs no execution and
    reports through no observer: the driver's proof runs on the lease, on an
    initialized connection exactly as later work will. It establishes that
    later work can run at all and records the authenticated login identity
    before the runtime is published. The proof is the lease's first
    submission, so a broken session is replaced once within what remains of
    the budget. It is not the lease's setup: like any submission after entry,
    it is not admitted again once it answers, and the budget is checked
    between phases instead.
    """
    _remaining_budget(route, deadline, "acquire")
    resource = runtime.startup_context(route, deadline)
    try:
        resource.__enter__()
    except ConnectionAcquisitionError as exc:
        report_resource_issues("startup", resource.cleanup_result)
        raise _unacquired(route, "acquire", exc, resource.cleanup_result) from None
    try:
        login = resource.run(driver.prove_readiness, expected_login, replay_safe=True)
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
        if isinstance(exc, ConnectionAcquisitionError):
            # The replacement for a lost proof arrived after the budget.
            raise _unacquired(route, "probe", exc, resource.cleanup_result) from None
        error = DatabaseStartupError(
            str(exc)
            if isinstance(exc, ProbeMismatch)
            else "the database runtime's startup probe did not return what it asked for",
            route=route.route,
            phase="probe",
            cleanup_result=resource.cleanup_result,
        )
        error.__cause__ = exc
        # A lost session is an outage only where its replacement was not
        # refused as anything worse; the loss that asked for it stays primary.
        refusal = resource.replacement_refusal
        raise _ReadinessFailure(
            error,
            outage=driver.is_session_lost(exc)
            and (refusal is None or refusal.reason in OUTAGE_REASONS)
            and _confirmed(resource.cleanup_result),
        ) from None
    resource.__exit__(None, None, None)
    result = resource.cleanup_result
    report_resource_issues("startup", result)
    if isinstance(result, ReleaseUnconfirmed):
        raise _ReadinessFailure(
            DatabaseStartupError(
                "the database runtime's startup connection release could not be confirmed",
                route=route.route,
                phase="release",
                cleanup_result=result,
            ),
            outage=False,
        )
    _remaining_budget(route, deadline, "release", cleanup_result=result)
    return login


def _unacquired[C](
    route: PooledRoute[C],
    phase: StartupPhase,
    refused: ConnectionAcquisitionError,
    cleanup_result: CleanupResult | None,
) -> _ReadinessFailure:
    error = DatabaseStartupError(
        "no database connection could be acquired while starting up",
        route=route.route,
        phase=phase,
        cleanup_result=cleanup_result,
    )
    error.__cause__ = refused
    return _ReadinessFailure(
        error,
        outage=refused.reason in OUTAGE_REASONS and _confirmed(cleanup_result),
    )


def _confirmed(cleanup: CleanupResult | None) -> bool:
    """Whether what a failed startup acquisition took was given back as far as
    its release could establish; an unconfirmed release is never an outage."""
    return not isinstance(cleanup, ReleaseUnconfirmed)


def _remaining_budget[C](
    route: PooledRoute[C],
    deadline: float,
    phase: StartupPhase,
    *,
    cleanup_result: CleanupResult | None = None,
) -> float:
    """The startup budget left, refusing to begin ``phase`` without any.

    Checked between phases rather than inside them: the budget stops the next
    step from starting and makes no claim about interrupting one already
    running. Running out is an outage's symptom unless the route's latest
    recorded dial failure is something other than unavailable; such a refusal
    is the failure, and deferral does not wait it out.
    """
    remaining = deadline - monotonic()
    if remaining <= 0.0:
        failure = route.dial_ledger.latest_failure
        error = DatabaseStartupError(
            "the database runtime did not become ready within its startup timeout",
            route=route.route,
            phase=phase,
            cleanup_result=cleanup_result,
        )
        error.__cause__ = None if failure is None else failure.cause
        raise _ReadinessFailure(error, outage=failure is None or failure.reason == "unavailable")
    return remaining
