"""``parallax.conformance._decoration`` — decorating what a Database executes on.

Two conformance lanes need every statement a ``Database`` runs to pass through a
decorator of theirs: the boundary lane arms a fault at a chosen seam, and a
scenario step marked ``rollback: true`` aborts the transaction after its body.
Both decorate EXECUTION — the four verbs — and neither has anything to say about
a connection's lifetime.

Since a ``Database`` is now connected from configuration, a decorator can no
longer be handed to it directly. So the decoration moves to where the connection
is acquired: this adapter opens the real runtime underneath, and wraps each
connection an acquisition yields as it is handed over. What the lane wrote stays
an execution decorator, and the resource lifetime underneath stays the shipped
one, including its single-use contexts and its cleanup results.

A decorator is applied per acquisition, so a retry decorates its own fresh
connection. State the lane wants to survive that — a fault that fires once
across a whole invocation — belongs to the lane's own value, which its factory
closes over, rather than to a connection that is deliberately not reused.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from parallax.core.db_port import (
    ConnectionContext,
    ConnectionContextSource,
    DatabaseAdapter,
    DatabaseConnection,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from parallax.core.db_port import (
        CleanupResult,
        DatabaseRuntime,
        PoolMetricsSource,
    )
    from parallax.core.dialect import Dialect

__all__ = ["Decorate", "DecoratingAdapter"]

type Decorate = Callable[[DatabaseConnection], DatabaseConnection]
"""How a lane wraps the connection one acquisition yields."""


class DecoratingAdapter[Authorization]:
    """Configuration that opens ``inner``'s runtime and decorates what it yields.

    The dialect is ``inner``'s own throughout: a decorator reports the dialect of
    the thing it stands in for and authors none of its own (`m-db-port`), and
    that rule reaches the lifetime half here for the same reason it reaches the
    execution half — what a caller lowers SQL in must be what executes it.
    """

    def __init__(self, inner: DatabaseAdapter[Authorization], decorate: Decorate) -> None:
        self._inner = inner
        self._decorate = decorate

    @property
    def dialect(self) -> Dialect:
        return self._inner.dialect

    def open(self) -> _DecoratingRuntime[Authorization]:
        return _DecoratingRuntime(self._inner.open(), self._decorate)


class _DecoratingRuntime[Authorization]:
    def __init__(self, inner: DatabaseRuntime[Authorization], decorate: Decorate) -> None:
        self._inner = inner
        self._decorate = decorate

    @property
    def dialect(self) -> Dialect:
        return self._inner.dialect

    @property
    def pool_metrics(self) -> PoolMetricsSource | None:
        return self._inner.pool_metrics

    @property
    def login_identity(self) -> str:
        return self._inner.login_identity

    def login_execution(self) -> ConnectionContextSource:
        return _DecoratingSource(self._inner.login_execution(), self._decorate)

    def principal_execution(self, authorization: Authorization) -> ConnectionContextSource:
        return _DecoratingSource(self._inner.principal_execution(authorization), self._decorate)

    def close(self) -> None:
        self._inner.close()


class _DecoratingContext:
    """One acquisition of ``inner``, decorated at the moment it is handed over.

    Everything about the lifetime is the inner context's, including what it
    reports afterwards: decoration adds a layer to what the caller executes
    through and takes no part in checking out, releasing, or classifying
    what that established.
    """

    def __init__(self, inner: ConnectionContext, decorate: Decorate) -> None:
        self._inner = inner
        self._decorate = decorate

    @property
    def cleanup_result(self) -> CleanupResult | None:
        return self._inner.cleanup_result

    def __enter__(self) -> DatabaseConnection:
        return self._decorate(self._inner.__enter__())

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._inner.__exit__(exc_type, exc, traceback)


@dataclass(frozen=True, slots=True)
class _DecoratingSource:
    inner: ConnectionContextSource
    decorate: Decorate

    def new_context(self) -> ConnectionContext:
        return _DecoratingContext(self.inner.new_context(), self.decorate)
