from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from parallax.core.base import ParallaxError
from parallax.core.diagnostics import FailureDiagnostic

if TYPE_CHECKING:
    from collections.abc import Mapping

    from parallax.core.db_port import (
        DatabaseConnection,
        Route,
        RouteCapabilities,
        RoutePolicy,
        RouteSelection,
    )
    from parallax.core.db_port._pool_metrics import PoolMetricsSource
    from parallax.core.dialect import Dialect

__all__ = [
    "AcquisitionReason",
    "CleanupCode",
    "CleanupIssue",
    "CleanupPhase",
    "CleanupResult",
    "ConnectionAcquisitionError",
    "ConnectionContext",
    "ConnectionContextSource",
    "DatabaseAdapter",
    "DatabaseRuntime",
    "DatabaseStartupError",
    "InvalidAuthorizationError",
    "Invalidated",
    "ReleaseUnconfirmed",
    "Returned",
    "StartupPhase",
]

type CleanupPhase = Literal["inspect", "restore", "dispose", "return"]
"""Which step of the finite cleanup sequence met a problem.

The sequence is exactly these four and always in this order: ``inspect`` reads
the controlled native state and the suspect marker an execution may have left,
``restore`` removes scoped authorization from a reusable session, ``dispose``
establishes physical disposal of a connection that must not be reused, and
``return`` hands the connection back to whatever manages it. There is no fifth
step and no loop, which is what bounds the issues one cleanup can report without
retaining a history.
"""

type CleanupCode = Literal[
    "state-unreadable",
    "not-idle",
    "suspect",
    "authorization-restore-failed",
    "close-failed",
    "handoff-failed",
]
"""The stable identifier for one cleanup condition.

``state-unreadable`` means the controlled state could not be read at all, so
reuse cannot be established; ``not-idle`` means it was read and the connection
was not idle, which no cleanup repairs into reuse; ``suspect`` means the
execution itself declared the connection untrustworthy, whatever its state now
reads as. ``authorization-restore-failed`` means scoped authorization could not
be removed from an otherwise reusable session. ``close-failed`` and
``handoff-failed`` are the two steps that can fail after a disposal verdict.

A code describes the CONDITION met, not the disposition reached: a recovered
``not-idle`` accompanies a successful :class:`Invalidated`, and a
``handoff-failed`` is what makes an otherwise safe disposal
:class:`ReleaseUnconfirmed`.
"""


@dataclass(frozen=True, slots=True)
class CleanupIssue:
    """One condition met while releasing a connection.

    ``phase`` and ``code`` are the classification a restricted log may state;
    ``diagnostic`` is the detached projection of the underlying exception, for a
    caller that has a rich, application-controlled export path for it. An issue
    a step raised carries the exception it raised; an issue a step OBSERVED —
    a connection that is simply not idle — carries the projection of the
    refusal this module states about it, never a native message.
    """

    phase: CleanupPhase
    code: CleanupCode
    diagnostic: FailureDiagnostic


@dataclass(frozen=True, slots=True)
class Returned:
    """The connection was handed back and the handoff completed.

    It promises nothing beyond that: what manages the connection may retire it,
    replace it, or close it outright, and none of that changes what this reports.
    """

    issues: tuple[CleanupIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class Invalidated:
    """Physical disposal was established BEFORE the handoff, and the handoff
    then completed for accounting.

    Both halves are required. Disposal alone would leak the capacity the
    connection occupied; a handoff alone would offer a connection nothing may
    reuse. ``issues`` records why disposal was chosen and anything recovered on
    the way, so a deliberate invalidation is legible without being an error.
    """

    issues: tuple[CleanupIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class ReleaseUnconfirmed:
    """Required disposal or the accounting after it failed, or could not be confirmed.

    This is the honest report of a resource whose fate is unknown. It is never
    empty: something has to have gone wrong to reach it, and stating which step
    is the whole value of the outcome.
    """

    issues: tuple[CleanupIssue, ...]

    def __post_init__(self) -> None:
        if not self.issues:
            raise ValueError("a release-unconfirmed connection reports at least one cleanup issue")


type CleanupResult = Returned | Invalidated | ReleaseUnconfirmed
"""How one acquisition ended, as a closed union of exactly one member.

Absence of a result is not a member: a context that was never entered, or is
still in use, reports ``None`` instead.
"""

type AcquisitionReason = Literal[
    "timeout",
    "queue_rejected",
    "closed",
    "unavailable",
    "preparation_failed",
    "authorization_failed",
    "authentication_refused",
    "credentials_refused",
]
"""Why an acquisition did not produce a usable connection.

``timeout`` is the cooperative acquisition budget running out with no failure
on record that explains it — including a native success that arrived after it,
and a pool that was merely saturated. ``queue_rejected`` is a bounded waiting
queue refusing to hold another waiter. ``closed`` is the runtime no longer
admitting work. ``unavailable`` is a route that could not be reached: a dial
that met no server, a server not accepting connections yet, a connection lost
while the lease was being set up, or a budget spent while a dial failure
recorded during the wait was still the latest outcome. ``preparation_failed``
covers establishing or preparing execution access otherwise: a dial the server
refused for another reason, a session configuration the codecs cannot execute
under, a checkout that handed over a connection which was not idle, and a
route refused when its connection was verified. ``authorization_failed`` means
the provider could not establish the bound authorization before admitting
modeled work. ``authentication_refused`` means the server rejected the login
it was offered. ``credentials_refused`` means the configured Credential Source
produced no credential, so nothing was ever offered to the server — which is a
different thing to fix from a login the server itself rejected.

These are separate from `m-db-error`'s SQL categories on purpose. No modeled
statement ran, so nothing was classified, and no retry rule reads them.
"""


class ConnectionAcquisitionError(ParallaxError):
    """No connection was acquired, and ``reason`` says which way.

    A neutral outer message with the native cause chained where one exists, in
    the same shape as translated statement failures. Admission that was refused
    because the runtime is closed has no native cause to chain and fabricates
    none.

    It is terminal for a transaction attempt: no callback ran and no boundary
    opened, so there is nothing to undo and nothing to replay.

    ``selection`` is the route whose failure was terminal, with any fallback
    taken on the way there, and ``None`` where the acquisition was refused
    before any route was selected.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: AcquisitionReason,
        selection: RouteSelection | None = None,
    ) -> None:
        super().__init__("connection-acquisition-failed", message)
        self.reason: AcquisitionReason = reason
        self.selection: RouteSelection | None = selection


class InvalidAuthorizationError(ValueError):
    """An adapter refused the shape of a resource-free authorization value."""


type StartupPhase = Literal["open", "minimum_ready", "acquire", "probe", "release"]
"""Which readiness phase failed to complete.

``open`` creates the native resource, ``minimum_ready`` waits for a positive
retained minimum where one applies, ``acquire`` takes the startup connection,
``probe`` proves connectivity and decoding through it, and ``release`` gives it
back. All five share one budget, which is never restarted between them.
"""


class DatabaseStartupError(ParallaxError):
    """A runtime did not become ready, so no ``Database`` was published.

    ``route`` names whose readiness failed, so a reader that refused its login
    is never read as a writer outage. ``phase`` names where that route's
    readiness stopped and ``cleanup_result`` carries what
    is known about a startup connection that had already been acquired — which
    is how a successful probe followed by an unconfirmed release is
    reported without fabricating an exception that never existed.

    An earlier startup failure stays primary: cleanup that follows it reports
    through the restricted resource logger rather than replacing it.
    """

    def __init__(
        self,
        message: str,
        *,
        route: Route,
        phase: StartupPhase,
        cleanup_result: CleanupResult | None = None,
    ) -> None:
        super().__init__("database-startup-failed", message)
        self.route: Route = route
        self.phase: StartupPhase = phase
        self.cleanup_result: CleanupResult | None = cleanup_result


@runtime_checkable
class ConnectionContext(Protocol):
    """One acquisition, from checkout to release: a single-use context
    manager over a scoped :class:`~parallax.core.db_port.DatabaseConnection`.

    Creating one takes no connection. Entering it checks out, prepares, and
    admits — or raises :class:`ConnectionAcquisitionError` having already run
    cleanup over whatever partial ownership it took, so nothing is left for the
    caller to release and what that cleanup established is on
    :attr:`cleanup_result`. Leaving it revokes the execution access it yielded
    and releases the connection exactly once.

    Single-use is the whole lifetime rule: re-entering one, entering one that
    already exited, and entering one whose entry failed each raise
    ``RuntimeError`` without touching the resource. Each entry yields FRESH
    execution access even where the physical connection is reused, so a
    reference kept past the exit executes nothing and holds nothing.

    One context is one lease rather than one physical session: an adapter that
    replaces the connection beneath it does so inside this acquisition
    (``m-db-port``), and the cleanup it reports describes the ownership the
    context ended with, never an intermediate handoff.

    It is deliberately not a context manager over a transaction: entering opens
    no boundary and leaving neither commits nor rolls back. Transaction outcomes
    stay the execution Interface's, authoritative and unchanged.
    """

    @property
    def cleanup_result(self) -> CleanupResult | None:
        """What releasing this acquisition established, once it has happened.

        ``None`` before entry, during use, and after an acquisition failure that
        never reached Parallax ownership — absence, never success. Stable once
        set: an exited context does not revise its own report, and nothing
        inspects a connection already handed off in order to refine it. A
        handoff made while the context is in use is never published here.
        """
        ...

    @property
    def selection(self) -> RouteSelection | None:
        """The route this acquisition was served on, once entry selected one.

        ``None`` before entry and after a failed entry that selected no route;
        a failed entry that did select one reports it here as well as on its
        :class:`ConnectionAcquisitionError`. Stable once entry has returned or
        raised.
        """
        ...

    def __enter__(self) -> DatabaseConnection: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None: ...


@runtime_checkable
class ConnectionContextSource(Protocol):
    """A resource-free source of fresh single-use connection contexts."""

    def new_context(self, policy: RoutePolicy, /) -> ConnectionContext:
        """Construct a context requesting ``policy`` without acquiring a
        connection or performing I/O.

        ``policy`` names only routes the runtime declares: core resolves it
        against :attr:`DatabaseRuntime.routes` before asking.
        """
        ...


@runtime_checkable
class DatabaseRuntime[Authorization = object](Protocol):
    """The running database resource one connected ``Database`` owns.

    It hands out acquisitions and it stops. It is not a pool manager: there is
    no sizing, draining, statistics, or scheduling verb here, because those are
    the concrete implementation's own and an application tunes them by
    configuring the adapter it opened this from.

    ``close`` is idempotent and permanent. It stops admitting new acquisitions
    and releases what the runtime holds; it neither drains borrowers nor
    interrupts SQL already running. Work already admitted may finish, including
    later statements of an open transaction and later pages of a stream that
    already acquired. Anything needing a NEW acquisition — a retry, a stream
    that has not read its first page — is refused from then on.
    """

    @property
    def dialect(self) -> Dialect:
        """The SQL spelling every statement acquired here is written in."""
        ...

    @property
    def login_identity(self) -> str:
        """The actual authenticated login captured before runtime publication."""
        ...

    @property
    def routes(self) -> Mapping[Route, RouteCapabilities]:
        """The routes this runtime serves and what each can serve.

        Always declares ``writer``; ``reader`` only where one is configured.
        Immutable for the runtime's life, so a scope may validate a policy
        against it without I/O.
        """
        ...

    @property
    def pool_metrics(self) -> tuple[PoolMetricsSource, ...]:
        """This runtime's read-only pool measurements, one source per pool it keeps.

        Empty is an honest absence rather than a degraded source: a runtime
        that manages no pool has no bookkeeping to report, and a caller composes
        observation only over the sources that exist.
        """
        ...

    def login_source(self) -> ConnectionContextSource:
        """Bind execution under the authenticated login without I/O."""
        ...

    def principal_source(self, authorization: Authorization) -> ConnectionContextSource:
        """Validate and bind one provider authorization without I/O."""
        ...

    def close(self) -> None:
        """Stop admitting work and release what this runtime owns."""
        ...


@runtime_checkable
class DatabaseAdapter[Authorization = object](Protocol):
    """Immutable, resource-free configuration that knows how to open a runtime.

    Constructing one performs no I/O and allocates no resource, so it is safe to
    build at import time, share between threads, and reuse. Every ``open`` makes
    an INDEPENDENT runtime: two ``Database`` handles built from one
    configuration own two runtimes, and closing either leaves the other working.

    ``open`` returns only a READY runtime. Waiting for readiness, proving
    connectivity, and unwinding a partial startup are all inside it, which is
    what lets composition treat the returned value as usable without a second
    start step.
    """

    @property
    def dialect(self) -> Dialect:
        """The SQL spelling this configuration's runtimes execute in, readable
        without opening anything."""
        ...

    def open(self) -> DatabaseRuntime[Authorization]:
        """Open one independent ready runtime, or raise
        :class:`DatabaseStartupError` having published nothing and released what
        it had taken, so far as that release could be established."""
        ...
