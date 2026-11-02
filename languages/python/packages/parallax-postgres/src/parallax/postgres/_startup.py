from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Literal

from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    ConnectionAcquisitionError,
    DatabaseStartupError,
    ReleaseUnconfirmed,
    StartupPhase,
    report_resource_issues,
)
from parallax.postgres._connection import DialFailure, session_lost
from parallax.postgres._options import PoolOptions
from parallax.postgres._route import (
    PROBE_SQL,
    PostgresRoute,
    ProbeMismatch,
    check_probe,
    open_route,
)
from parallax.postgres._runtime import PostgresRuntime

if TYPE_CHECKING:
    from parallax.postgres._endpoint import PostgresEndpoint

__all__ = ["ReaderStartup", "open_runtime"]

ReaderStartup = Literal["deferrable", "required"]
"""Whether an unreachable reader may leave startup to finish its proof later."""


class _ReadinessFailure(Exception):
    """A route's readiness failed, and whether that failure was only an outage.

    An outage is a route that could not be reached, or whose share of the
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
    same login within what remains, or — where ``reader_startup`` permits and
    the reader could only not be reached — is left pending, to be proved by
    the first connection it hands over.

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
        runtime = PostgresRuntime(writer_route, reader_route, acquire_timeout=acquire_timeout)
        try:
            login = _prove(runtime, writer_route, writer, deadline, None)
        except _ReadinessFailure as failure:
            raise failure.error from failure.error.__cause__
        writer_route.proved_at_startup()
        runtime._complete_startup(login)  # pyright: ignore[reportPrivateUsage] - module-owned startup transition
        if reader is not None and reader_route is not None:
            _start_reader(runtime, reader_route, reader, deadline, login, reader_startup)
    except BaseException:
        for route in reversed(opened):
            route.abandon()
        raise
    return runtime


def _start_reader(
    runtime: PostgresRuntime,
    route: PostgresRoute,
    endpoint: PostgresEndpoint,
    deadline: float,
    login: str,
    reader_startup: ReaderStartup,
) -> None:
    try:
        _prove(runtime, route, endpoint, deadline, login)
    except _ReadinessFailure as failure:
        if failure.outage and reader_startup == "deferrable":
            route.defer_verification()
            return
        raise failure.error from failure.error.__cause__
    route.proved_at_startup()


def _prove(
    runtime: PostgresRuntime,
    route: PostgresRoute,
    endpoint: PostgresEndpoint,
    deadline: float,
    expected_login: str | None,
) -> str:
    """Prove ``route`` ready within ``deadline``, answering the login it authenticated."""
    _await_minimum(route, endpoint, deadline)
    return _probe(runtime, route, deadline, expected_login)


def _await_minimum(route: PostgresRoute, endpoint: PostgresEndpoint, deadline: float) -> None:
    """Wait for the retained minimum, where there is one to wait for.

    Skipped for a zero minimum and for on-demand retention, because neither has
    retained capacity: the native wait would either return immediately having
    proved nothing, or establish a connection of its own that is then thrown
    away. The probe below is what proves readiness in every mode, so nothing is
    lost by skipping this one.

    Filling happens on the route's own background path, where an establishment
    failure is retried rather than reported, so all this wait can see is that
    time ran out. Where a failure is on record it is stated as the failure
    instead: a configuration every connection is refused under is what an
    operator has to fix, and "timed out" names none of it.
    """
    options = endpoint.pool
    if not isinstance(options, PoolOptions) or options.min_size <= 0:
        return
    remaining = _remaining(route, deadline, "minimum_ready")
    try:
        route.pool.wait(timeout=remaining)
    except Exception as exc:
        failure = route.establishment.last_failure
        error = DatabaseStartupError(
            _minimum_failure(failure), route=route.route, phase="minimum_ready"
        )
        error.__cause__ = exc if failure is None else failure.cause
        raise _ReadinessFailure(
            error, outage=failure is None or failure.reason == "unavailable"
        ) from None


def _minimum_failure(failure: DialFailure | None) -> str:
    if failure is None:
        return "the database runtime did not reach its minimum number of connections in time"
    if failure.reason == "credentials_refused":
        return "no database connection this runtime opened could be authenticated"
    if failure.reason == "unavailable":
        return "no database connection this runtime tried to open could reach its server"
    if failure.reason == "authentication_refused":
        return "no database connection this runtime opened was accepted once its login was offered"
    return "no database connection this runtime opened became usable"


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
        raise _ReadinessFailure(error, outage=exc.reason in {"unavailable", "timeout"}) from None
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
        raise _ReadinessFailure(error, outage=_lost(exc)) from None
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


def _lost(failure: Exception) -> bool:
    """Whether a probe failed only because its connection could not be kept."""
    native = failure.__cause__ if isinstance(failure, DatabaseError) else failure
    return native is not None and session_lost(native)


def _remaining(route: PostgresRoute, deadline: float, phase: StartupPhase) -> float:
    """The startup budget left, refusing to begin ``phase`` without any.

    Checked between phases rather than inside them: the budget stops the next
    step from starting and makes no claim about interrupting one already
    running. Running out names no failure, so it is an outage's symptom rather
    than a refusal.
    """
    remaining = deadline - monotonic()
    if remaining <= 0.0:
        raise _ReadinessFailure(
            DatabaseStartupError(
                "the database runtime did not become ready within its startup timeout",
                route=route.route,
                phase=phase,
            ),
            outage=True,
        )
    return remaining
