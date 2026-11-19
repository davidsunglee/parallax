from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Literal

from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import (
    CleanupResult,
    ConnectionAcquisitionError,
    DatabaseStartupError,
    ReleaseUnconfirmed,
    StartupPhase,
    report_resource_issues,
)
from parallax.postgres._connection import session_lost
from parallax.postgres._route import (
    PROBE_SQL,
    PostgresRoute,
    ProbeMismatch,
    check_probe,
    open_reservation_route,
    open_route,
)
from parallax.postgres._runtime import PostgresRuntime

if TYPE_CHECKING:
    from parallax.postgres._endpoint import PostgresEndpoint

__all__ = ["ReaderStartup", "open_runtime"]

ReaderStartup = Literal["deferrable", "required"]
"""Whether an unavailable reader may leave startup to finish its proof later."""


class _ReadinessFailure(Exception):
    """A route's readiness failed, and whether that failure was only an outage.

    An outage is an unavailable route, or one whose share of the
    budget ran out with no other failure on record. Anything else — a refused
    credential or login, a session the codecs cannot run under, a probe that
    read back the wrong thing or another login, an unconfirmed release — is a
    route that would fail the same way again, which no deferral can wait out.
    """

    def __init__(self, error: DatabaseStartupError, *, outage: bool) -> None:
        super().__init__(str(error))
        self.error = error
        self.outage = outage


def open_runtime(
    writer: PostgresEndpoint,
    reader: PostgresEndpoint | None,
    *,
    acquire_timeout: float,
    startup_timeout: float,
    reader_startup: ReaderStartup,
    prepare_threshold: int | None,
) -> PostgresRuntime:
    """Open one ready runtime over ``writer`` and an optional ``reader``, or raise
    having released what it took.

    Both pools open before either is proved, so a retaining reader's workers
    dial while the writer is being proved and the two share the one budget's
    wall-clock time. The writer must prove itself; the reader then proves the
    same login within what remains. Where ``reader_startup`` permits, an
    unavailable reader stays pending until a connection proves it. The writer's
    reservation pool opens beside them holding no connection, and the writer's
    proof stands for it.

    Every failure below publishes no runtime: every pool opened so far is closed
    on the way out, and a startup connection that was already acquired is
    released through the same cleanup path an ordinary operation uses — which
    reports what it established, so a disposal or handoff that itself failed is
    stated rather than assumed away.
    """
    deadline = monotonic() + startup_timeout
    opened: list[PostgresRoute] = []
    try:
        writer_route = open_route(
            writer, "writer", acquire_timeout=acquire_timeout, prepare_threshold=prepare_threshold
        )
        opened.append(writer_route)
        reader_route = None
        if reader is not None:
            reader_route = open_route(
                reader,
                "reader",
                acquire_timeout=acquire_timeout,
                prepare_threshold=prepare_threshold,
            )
            opened.append(reader_route)
        reservation_route = open_reservation_route(
            writer, acquire_timeout=acquire_timeout, prepare_threshold=prepare_threshold
        )
        opened.append(reservation_route)
        runtime = PostgresRuntime(
            writer_route,
            reader_route,
            reservation=reservation_route,
            acquire_timeout=acquire_timeout,
        )
        try:
            login = _probe(runtime, writer_route, deadline, None)
        except _ReadinessFailure as failure:
            raise failure.error from failure.error.__cause__
        writer_route.proved_at_startup()
        # The writer's proof is the reservation pool's: it dials the same
        # endpoint with the same credentials.
        reservation_route.proved_at_startup()
        runtime._complete_startup(login)  # pyright: ignore[reportPrivateUsage] - module-owned startup transition
        if reader_route is not None:
            _start_reader(runtime, reader_route, deadline, login, reader_startup)
    except BaseException:
        _abandon(opened)
        raise
    return runtime


def _abandon(opened: list[PostgresRoute]) -> None:
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


def _start_reader(
    runtime: PostgresRuntime,
    route: PostgresRoute,
    deadline: float,
    login: str,
    reader_startup: ReaderStartup,
) -> None:
    try:
        _probe(runtime, route, deadline, login)
    except _ReadinessFailure as failure:
        if failure.outage and reader_startup == "deferrable":
            route.defer_verification()
            return
        raise failure.error from failure.error.__cause__
    route.proved_at_startup()


def _probe(
    runtime: PostgresRuntime, route: PostgresRoute, deadline: float, expected_login: str | None
) -> str:
    """Acquire one real connection, prove it decodes, capture its login, and give it back.

    Startup owns no model and adopts no edition, so this creates no execution
    and reports through no observer: it runs on an initialized connection
    exactly as later work will. It establishes that later work can run at all
    and records the authenticated login identity before the runtime is published.
    """
    _remaining(route, deadline, "acquire")
    resource = runtime.acquisition(route, deadline)
    try:
        connection = resource.__enter__()
    except ConnectionAcquisitionError as exc:
        report_resource_issues("startup", resource.cleanup_result)
        error = DatabaseStartupError(
            "no database connection could be acquired while starting up",
            route=route.route,
            phase="acquire",
            cleanup_result=resource.cleanup_result,
        )
        error.__cause__ = exc
        raise _ReadinessFailure(
            error,
            outage=exc.reason in {"unavailable", "timeout"} and _confirmed(resource.cleanup_result),
        ) from None
    try:
        login = check_probe(connection.execute(PROBE_SQL, [], read_only=True), expected_login)
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
        error = DatabaseStartupError(
            str(exc)
            if isinstance(exc, ProbeMismatch)
            else "the database runtime's startup probe did not return what it asked for",
            route=route.route,
            phase="probe",
            cleanup_result=resource.cleanup_result,
        )
        error.__cause__ = exc
        raise _ReadinessFailure(
            error, outage=_lost(exc) and _confirmed(resource.cleanup_result)
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
    _remaining(route, deadline, "release")
    return login


def _confirmed(cleanup: CleanupResult | None) -> bool:
    """Whether what a failed startup acquisition took was given back as far as
    its release could establish; an unconfirmed release is never an outage."""
    return not isinstance(cleanup, ReleaseUnconfirmed)


def _lost(failure: Exception) -> bool:
    """Whether a probe failed only because its connection could not be kept."""
    native = failure.__cause__ if isinstance(failure, DatabaseError) else failure
    return native is not None and session_lost(native)


def _remaining(route: PostgresRoute, deadline: float, phase: StartupPhase) -> float:
    """The startup budget left, refusing to begin ``phase`` without any.

    Checked between phases rather than inside them: the budget stops the next
    step from starting and makes no claim about interrupting one already
    running. Running out is an outage's symptom only where the route has no
    refusal on record: a route whose own background dials were refused would
    be refused again, however long it were given.
    """
    remaining = deadline - monotonic()
    if remaining <= 0.0:
        failure = route.establishment.last_failure
        error = DatabaseStartupError(
            "the database runtime did not become ready within its startup timeout",
            route=route.route,
            phase=phase,
        )
        error.__cause__ = None if failure is None else failure.cause
        raise _ReadinessFailure(error, outage=failure is None or failure.reason == "unavailable")
    return remaining
