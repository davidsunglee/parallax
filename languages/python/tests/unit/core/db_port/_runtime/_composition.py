"""Runtimes and contexts composed over the scripted kit, for the shared runtime's suites.

Each builder composes the production runtime, routes, and contexts directly
over scripted pools and a scripted driver, standing in for startup where a
suite needs a runtime already started.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from parallax.core.internal.db_port import (
    RESOURCE_LOGGER_NAME,
    Invalidated,
    ReleaseUnconfirmed,
    Returned,
    Route,
    RouteCapabilities,
)
from parallax.core.internal.db_port._runtime._dial_record import DialLedger
from parallax.core.internal.db_port._runtime._pooled_route import PooledRoute
from parallax.core.internal.db_port._runtime._pooled_runtime import PooledRuntime
from parallax.core.internal.dialect import POSTGRES
from tests.unit.core.db_port._runtime._scripted_native import (
    ScriptedConnection,
    ScriptedDriver,
    ScriptedPool,
    SessionLost,
)

if TYPE_CHECKING:
    import pytest

__all__ = [
    "ROUTED",
    "WRITER_ONLY",
    "Pool",
    "available_samples",
    "issues_of",
    "login_context",
    "lost_session",
    "pool_of",
    "pooled_runtime",
    "preferred_context",
    "reader_context",
    "reader_route_of",
    "resource_records",
    "routed",
    "whatever_budget",
]

WRITER_ONLY: Mapping[Route, RouteCapabilities] = {"writer": RouteCapabilities.every_level()}


ROUTED: Mapping[Route, RouteCapabilities] = {
    "writer": RouteCapabilities.every_level(),
    "reader": RouteCapabilities(frozenset({"read_committed", "repeatable_read"})),
}


type Pool = ScriptedPool[ScriptedConnection]


def pool_of(*connections: ScriptedConnection, **kwargs: Any) -> Pool:
    """A scripted pool over ``connections``, or one fresh connection."""
    return ScriptedPool(*(connections or (ScriptedConnection(),)), **kwargs)


def whatever_budget(action: Callable[[], object]) -> Callable[[float], None]:
    """A checkout hook running ``action`` whatever budget the checkout was given."""

    def hook(_budget: float) -> None:
        action()

    return hook


def lost_session(message: str = "server closed the connection unexpectedly") -> SessionLost:
    return SessionLost(message)


def pooled_runtime(
    pool: Pool,
    *,
    acquire_timeout: float = 15.0,
    reservation: Pool | None = None,
    driver: ScriptedDriver | None = None,
    routes: Mapping[Route, RouteCapabilities] = WRITER_ONLY,
) -> PooledRuntime[ScriptedConnection, object]:
    return PooledRuntime(
        ScriptedDriver() if driver is None else driver,
        dialect=POSTGRES,
        routes=routes,
        writer=PooledRoute("writer", pool, DialLedger()),
        reservation=PooledRoute(
            "writer", pool_of() if reservation is None else reservation, DialLedger(), "reservation"
        ),
        acquire_timeout=acquire_timeout,
    )


def login_context(runtime: PooledRuntime[ScriptedConnection, object]) -> Any:
    return runtime.login_source().new_context("writer_only")


def routed(
    writer_pool: Pool,
    reader_pool: Pool,
    *,
    reader_readiness: str = "verified",
    acquire_timeout: float = 15.0,
) -> PooledRuntime[ScriptedConnection, object]:
    """A started runtime over two scripted pools, its reader verified or pending."""
    reader = PooledRoute("reader", reader_pool, DialLedger())
    runtime = PooledRuntime(
        ScriptedDriver(),
        dialect=POSTGRES,
        routes=ROUTED,
        writer=PooledRoute("writer", writer_pool, DialLedger()),
        reader=reader,
        reservation=PooledRoute("writer", pool_of(), DialLedger(), "reservation"),
        acquire_timeout=acquire_timeout,
    )
    runtime._complete_startup("runtime-login")  # pyright: ignore[reportPrivateUsage] - the startup transition this harness stands in for
    if reader_readiness == "verified":
        reader.start_verified()
    else:
        reader.start_pending()
    return runtime


def reader_route_of(
    runtime: PooledRuntime[ScriptedConnection, object],
) -> PooledRoute[ScriptedConnection]:
    reader = runtime._reader  # pyright: ignore[reportPrivateUsage] - the route whose readiness these proofs read
    assert reader is not None
    return reader


def reader_context(
    runtime: PooledRuntime[ScriptedConnection, object], authorization: object = None
) -> Any:
    source = (
        runtime.login_source() if authorization is None else runtime.principal_source(authorization)
    )
    return source.new_context("reader_only")


def preferred_context(
    runtime: PooledRuntime[ScriptedConnection, object], authorization: object = None
) -> Any:
    source = (
        runtime.login_source() if authorization is None else runtime.principal_source(authorization)
    )
    return source.new_context("reader_preferred")


def issues_of(result: object) -> list[tuple[str, str]]:
    assert isinstance(result, Returned | Invalidated | ReleaseUnconfirmed)
    return [(issue.phase, issue.code) for issue in result.issues]


def resource_records(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == RESOURCE_LOGGER_NAME]


def available_samples(runtime: PooledRuntime[ScriptedConnection, object]) -> list[Any]:
    samples = [
        source.sample() for source in runtime.pool_metrics if source.purpose == "application"
    ]
    assert all(type(sample).__name__ == "PoolAvailable" for sample in samples), samples
    return samples
