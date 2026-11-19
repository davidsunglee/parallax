from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from parallax.core.internal.db_port import ExecutionAccess, Route
    from parallax.core.internal.db_port._pool_metrics import PoolMetrics, PoolPurpose

__all__ = [
    "CheckoutFailed",
    "CheckoutReason",
    "ConnectionLease",
    "ConnectionPool",
    "DialReason",
    "DialRecord",
    "IdleReading",
    "NativeDriver",
    "NativeOperation",
    "NotIdle",
    "ProbeMismatch",
    "SubmissionProgress",
    "displaced_control_flow",
]

type DialReason = Literal[
    "unavailable", "authentication_refused", "credentials_refused", "preparation_failed"
]
"""The acquisition reasons establishing a connection can meet."""

type CheckoutReason = Literal["timeout", "queue_rejected", "closed"] | DialReason
"""The acquisition reasons one checkout can end with."""


class DialRecord(Protocol):
    """Where a pool reports what each physical connection attempt met.

    Every attempt reports exactly one outcome, from the thread that made it,
    before a checkout can hand over or refuse because of it: a classified
    failure, or usable once the connection has been initialized. Reporting does
    no I/O, calls nothing on the pool, and waits for nothing the pool holds.
    """

    def report_failure(self, reason: DialReason, cause: BaseException, /) -> None: ...

    def report_usable(self) -> None: ...


class CheckoutFailed(Exception):
    """A checkout that handed over no connection, and why.

    A dial reason describes a dial made and failed by this checkout call
    itself; what other attempts met reaches the runtime through the pool's
    :class:`DialRecord` instead. The native failure is chained as the cause
    where there is one.
    """

    def __init__(self, reason: CheckoutReason) -> None:
        super().__init__(reason)
        self.reason: CheckoutReason = reason


class ConnectionPool[C](Protocol):
    """The physical connections one route keeps for one purpose.

    :meth:`check_out` makes one fair wait within ``budget`` seconds, or raises
    :class:`CheckoutFailed`. A native dial MAY overrun the budget by its own
    timeout granularity; the runtime refuses such a late handover rather than
    running work on it.

    Every connection handed over comes back exactly once: through
    :meth:`check_in` while it remains reusable, or through :meth:`discard`
    once it has already been closed.

    :meth:`metrics` reads the pool's own bookkeeping without I/O and without
    taking a connection, and raises when no reading can be taken.
    :meth:`close` is idempotent.
    """

    def check_out(self, budget: float, /) -> C: ...

    def check_in(self, connection: C, /) -> None: ...

    def discard(self, connection: C, /) -> None: ...

    def metrics(self) -> PoolMetrics: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class SubmissionProgress:
    """How far one native operation got with the submission it may make.

    The operation sets :attr:`started` immediately before it hands its
    submission to the driver, and :attr:`answered` as soon as the driver has
    answered it — a pipeline once it has synchronized — before any result is
    fetched or decoded. Whoever runs the operation reads both once it returns
    or raises.
    """

    started: bool = False
    answered: bool = False


type NativeOperation[C, T, *P] = Callable[[C, SubmissionProgress, *P], T]
"""One native operation over the connection it is handed, marking its
submission's progress, with inputs prepared once by its caller.

Raw driver failures propagate as themselves, and the same prepared inputs may be
handed to the operation again over a replacement connection.
"""


class ConnectionLease[C](Protocol):
    """The holder of one physical connection that execution borrows per operation.

    :meth:`run` invokes each operation with fresh :class:`SubmissionProgress` on
    the connection currently held. ``replay_safe`` asserts that repeating the
    operation can have no effect, which permits a lease to repeat it once over a
    replacement where the first submission of the lease met a broken session;
    ``setup`` marks session setup rather than modeled work. A lease never
    replaces a connection for any other submission.
    """

    def run[T, *P](
        self,
        operation: NativeOperation[C, T, *P],
        /,
        *prepared: *P,
        replay_safe: bool,
        setup: bool = False,
    ) -> T: ...

    def current_connection(self) -> C: ...

    @property
    def suspect(self) -> bool: ...

    def mark_suspect(self) -> None: ...


@dataclass(frozen=True, slots=True)
class NotIdle:
    """A connection reporting a session state other than idle, in the driver's words."""

    state: str


type IdleReading = Literal["idle", "unreadable"] | NotIdle


class ProbeMismatch(Exception):
    """A readiness proof ran but read back something other than what it asked for.

    That is a positive incompatibility rather than an outage: the same route
    would read the same thing back next time.
    """


class NativeDriver[C, A](Protocol):
    """What a database adapter supplies so the shared runtime can serve it.

    ``C`` is the adapter's native connection and ``A`` its scoped authorization.
    :meth:`authorization` turns a caller's value into an ``A`` without I/O, or
    raises the adapter's ``UsageError`` with code ``AUTHORIZATION_INVALID``.

    :meth:`open_pool` returns an open pool reporting its dials to
    ``dial_record``, or raises the raw failure having released what it built.
    :meth:`open_execution` does no I/O and returns fresh execution access
    whose every statement runs through the lease.

    :meth:`read_idle` neither blocks nor raises. :meth:`is_session_broken`
    answers whether ``failure`` left ``connection`` unusable, and
    :meth:`is_session_lost` whether a failure on an established session says
    the session itself ended.

    :meth:`prove_readiness` returns the authenticated login, raises
    :class:`ProbeMismatch` for a positive mismatch, including a login other
    than ``expected_login``, and otherwise raises raw driver failures.
    :meth:`limit_statement_time` rounds ``seconds`` up to a native unit, never
    to an unbounded value.
    """

    def open_pool(
        self, route: Route, purpose: PoolPurpose, dial_record: DialRecord
    ) -> ConnectionPool[C]: ...

    def open_execution(self, lease: ConnectionLease[C]) -> ExecutionAccess: ...

    def authorization(self, value: object, /) -> A: ...

    def read_idle(self, connection: C) -> IdleReading: ...

    def close_connection(self, connection: C) -> None: ...

    def is_session_broken(self, connection: C, failure: BaseException) -> bool: ...

    def is_session_lost(self, failure: BaseException) -> bool: ...

    def prove_readiness(
        self, connection: C, submission: SubmissionProgress, expected_login: str | None
    ) -> str: ...

    def install_authorization(
        self, connection: C, submission: SubmissionProgress, authorization: A
    ) -> None: ...

    def restore_authorization(self, connection: C) -> None: ...

    def limit_statement_time(
        self, connection: C, submission: SubmissionProgress, seconds: float
    ) -> None: ...


def displaced_control_flow(
    escaped: Exception, ambient: BaseException | None
) -> BaseException | None:
    """The control-flow exception raised during an operation that ``escaped``
    took the place of, if any.

    A driver may answer an interrupt raised while it waits by finishing its
    own exchange with the server, so a failure in that exchange escapes in the
    interrupt's place and carries it only as context. ``ambient`` is the
    exception already being handled when the operation began; its context chain
    predates the operation.
    """
    context = escaped.__context__
    while context is not None and context is not ambient:
        if not isinstance(context, Exception):
            return context
        context = context.__context__
    return None
