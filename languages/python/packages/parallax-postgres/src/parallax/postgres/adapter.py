from __future__ import annotations

from dataclasses import dataclass

from parallax.core.dialect import POSTGRES
from parallax.postgres._endpoint import PostgresEndpoint
from parallax.postgres._options import positive_seconds
from parallax.postgres._runtime import PostgresRuntime, open_runtime

__all__ = ["PostgresAdapter"]


def _endpoint(name: str, value: object) -> PostgresEndpoint:
    if not isinstance(value, PostgresEndpoint):
        raise TypeError(f"{name} takes a PostgresEndpoint")
    return value


def _prepare_threshold(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"prepare_threshold takes an int or None (got {value!r})")
    if value < 0:
        raise ValueError(f"prepare_threshold takes a nonnegative int or None (got {value!r})")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class PostgresAdapter:
    """How to reach a Postgres deployment, and the budgets its runtime spends.

    ``writer`` is the :class:`PostgresEndpoint` that writable transactions,
    and every read that requests the writer, use. Nothing about it is inferred
    from its connection string: an endpoint that reaches a replica stays valid
    here, and writes through it fail natively.

    ``acquire_timeout`` is the one cooperative budget each acquisition spends,
    across checkout, admission, authorization setup, and safe replacement.
    ``startup_timeout`` is the one budget opening a runtime spends becoming
    ready, shared across every readiness phase and never restarted. Both are
    the runtime's rather than one pool's, which is why they live here and not
    on the endpoint's retention options.

    ``prepare_threshold`` is the driver's server-side auto-preparation after
    that many identical executions. The default suits an ordinary long-lived
    application connection against one stable schema. Pass ``None`` to disable
    it where the SAME connection may see a table's shape change underneath
    identical query text — a schema-reset-per-case harness, never a deployed
    application — because Postgres's own "cached plan must not change result
    type" is a server-side plan-cache invalidation rather than anything
    Parallax can reconcile.

    Change any of these by constructing a new configuration —
    ``dataclasses.replace`` works and revalidates — never by mutating this one.
    """

    dialect = POSTGRES
    """The one place this adapter's SQL spelling is stated.

    Unannotated, so it is a class attribute rather than one of this record's
    fields: a composition root selects an adapter and lowers SQL in the spelling
    it will execute in before any configuration, let alone any resource, exists,
    and no caller can construct one claiming a different spelling.
    """

    writer: PostgresEndpoint
    acquire_timeout: float = 15.0
    startup_timeout: float = 30.0
    prepare_threshold: int | None = 5

    def __post_init__(self) -> None:
        object.__setattr__(self, "writer", _endpoint("writer", self.writer))
        object.__setattr__(
            self, "acquire_timeout", positive_seconds("acquire_timeout", self.acquire_timeout)
        )
        object.__setattr__(
            self, "startup_timeout", positive_seconds("startup_timeout", self.startup_timeout)
        )
        object.__setattr__(self, "prepare_threshold", _prepare_threshold(self.prepare_threshold))

    def open(self) -> PostgresRuntime:
        """Open one independent ready runtime, or raise having released what it took.

        Ready means proved: the pool exists, a real connection was acquired,
        initialized, and made to decode an integer, an unbounded instant, a
        structured document, and a Float32 and a Float64 exactly, and it was
        given back. A failure at any of those
        raises :class:`~parallax.core.db_port.DatabaseStartupError` naming the
        phase, and publishes no runtime: the pool is closed and a startup
        connection already acquired goes through the ordinary cleanup path,
        which reports what it established rather than promising reclamation.
        """
        return open_runtime(
            self.writer,
            acquire_timeout=self.acquire_timeout,
            startup_timeout=self.startup_timeout,
            prepare_threshold=self.prepare_threshold,
        )
