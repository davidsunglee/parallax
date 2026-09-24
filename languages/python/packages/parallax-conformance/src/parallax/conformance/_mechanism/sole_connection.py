"""The ``m-db-port`` scaffolding a double needs when it IS its one connection.

A stand-in database that answers statements in memory still has to be an
adapter: something opened into a runtime, acquired into scoped connections, and
closed. :class:`ConnectsAsItself` supplies all of that, so a double states only
what its statements and transactions mean.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Protocol, cast

from parallax.core.db_port import (
    CallbackRaised,
    CleanupResult,
    Committed,
    ConnectionAcquisitionError,
    ConnectionContext,
    ConnectionContextSource,
    DatabaseConnection,
    PipelineStatement,
    PoolMetricsSource,
    Returned,
    RolledBack,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect

__all__ = [
    "STAND_IN_LOGIN",
    "BoundContextSource",
    "ConnectsAsItself",
    "SoleConnectionRuntime",
    "SoleConnectionScope",
    "body_outcome",
]

_RETURNED: Final[CleanupResult] = Returned()
"""What a completed release establishes where nothing had to be reclaimed."""

STAND_IN_LOGIN: Final = "test-login"
"""The login identity every stand-in runtime reports."""


class _BindsContexts(Protocol):
    def new_bound_context(self, authorization: object | None) -> ConnectionContext: ...


@dataclass(frozen=True, slots=True)
class BoundContextSource:
    """A stand-in runtime's execution source, bound to one authorization or none."""

    runtime: _BindsContexts
    authorization: object | None = None

    def new_context(self) -> ConnectionContext:
        return self.runtime.new_bound_context(self.authorization)


class SoleConnectionScope:
    """One acquisition of a double that IS its own connection.

    There is nothing to check out and nothing to give back, but "nothing to give
    back" is still a completed release rather than an absent one: the
    contract is that an acquisition which was entered reports what its exit
    ESTABLISHED, and ``None`` is reserved for a context nobody entered or one
    whose entry never reached ownership. So this reports :class:`Returned` from
    the moment it is left, and nothing before that.
    """

    __slots__ = ("_connection", "_left")

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection
        self._left = False

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return _RETURNED if self._left else None

    def __enter__(self) -> DatabaseConnection:
        return self._connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._left = True


class SoleConnectionRuntime:
    """The minimal runtime around one in-memory connection."""

    __slots__ = ("_connection", "closed")

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection
        self.closed = False

    @property
    def dialect(self) -> Dialect:
        return self._connection.dialect

    @property
    def pool_metrics(self) -> PoolMetricsSource | None:
        return None

    @property
    def login_identity(self) -> str:
        return STAND_IN_LOGIN

    def login_execution(self) -> ConnectionContextSource:
        return BoundContextSource(self)

    def principal_execution(self, authorization: object) -> ConnectionContextSource:
        return BoundContextSource(self, authorization)

    def new_bound_context(self, authorization: object | None) -> ConnectionContext:
        del authorization
        if self.closed:
            raise ConnectionAcquisitionError(
                "this runtime is closed, so it opens no new connection", reason="closed"
            )
        return SoleConnectionScope(self._connection)

    def close(self) -> None:
        self.closed = True


class ConnectsAsItself:
    """A double that is its own configuration as well as its own connection.

    A production adapter is configuration and a connection is what one
    acquisition of it yields; a double small enough to be both saves every
    caller that drives execution directly from composing a resource lifetime it
    does not care about. What it costs is that such a double proves nothing
    about acquisition — a double grading THAT has to yield a fresh revocable
    connection per acquisition instead.
    """

    def open(self) -> SoleConnectionRuntime:
        return SoleConnectionRuntime(cast("DatabaseConnection", self))

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        connection = cast("DatabaseConnection", self)
        return [
            connection.execute(statement.sql, statement.binds, statement.document_reads)
            for statement in statements
        ]


def body_outcome[T](
    port: DatabaseConnection, body: Callable[[DatabaseConnection], T]
) -> TransactionOutcome[T]:
    """Run ``body`` on ``port`` and report what the body alone decided.

    Committed with its value, or rolled back carrying the exception it raised —
    including a base-level one, which a fake boundary undoes as readily as any
    other and which the composition root re-raises from the outcome.

    A fake port that scripts no boundary failure has no boundary of its own:
    nothing can fail at its begin, its commit, or its rollback, so every
    transaction it runs ends exactly as the body did. Such a port routes
    through here rather than restating that reading.
    """
    try:
        return Committed(body(port))
    except BaseException as raised:
        return RolledBack(CallbackRaised(raised))
