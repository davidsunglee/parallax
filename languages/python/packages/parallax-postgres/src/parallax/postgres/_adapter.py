from __future__ import annotations

from dataclasses import dataclass
from typing import Final, cast, get_args

from parallax.core.dialect import POSTGRES
from parallax.postgres._endpoint import PostgresEndpoint
from parallax.postgres._options import positive_seconds
from parallax.postgres._runtime import PostgresRuntime
from parallax.postgres._startup import ReaderStartup, open_runtime

__all__ = ["PostgresAdapter"]


class _Omitted:
    """The type of the one marker ``reader_startup`` defaults to when the caller
    says nothing.

    A marker rather than a default spelling, because omission and an explicit
    choice promise different things: omitted, a configured reader defers, and
    no reader is no contradiction; chosen, it is a decision about a reader, and
    making it without one is refused.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "OMITTED"


_OMITTED: Final = _Omitted()

_READER_STARTUPS: Final = cast("tuple[ReaderStartup, ...]", get_args(ReaderStartup))


def _endpoint(name: str, value: object) -> PostgresEndpoint:
    if not isinstance(value, PostgresEndpoint):
        raise TypeError(f"{name} takes a PostgresEndpoint")
    return value


def _reader_startup(value: object, reader: PostgresEndpoint | None) -> ReaderStartup | _Omitted:
    if value is _OMITTED:
        return _OMITTED
    if reader is None:
        raise ValueError("reader_startup describes a reader, and no reader is configured")
    for startup in _READER_STARTUPS:
        if value == startup:
            return startup
    raise ValueError(f"reader_startup must be one of {sorted(_READER_STARTUPS)}, got {value!r}")


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
    and every read that requests the writer, use. ``reader``, where configured,
    is the endpoint reads requesting the reader use; each endpoint carries its
    own credentials and retention, and both must authenticate the same login.
    Nothing about either is inferred from its connection string: a writer
    endpoint that reaches a replica stays valid here, and writes through it
    fail natively; a reader endpoint promises no physical replica.

    ``reader_startup`` says what opening does when the reader cannot be
    reached. Omitted with a reader configured, it is ``"deferrable"``: the
    runtime opens with the reader pending, reader-only work fails until one of
    the reader's connections has been proved, and a fixed warning says so — the
    choice that lets a reader resuming after the writer, as a paused Aurora
    Serverless reader does, not fail a cold start. ``"required"`` fails opening
    instead, which is the way to have a mistyped reader host fail a deployment
    rather than its first read. Any other reader failure — a refused credential
    or login, an unusable session, another login than the writer's — fails
    opening either way. Supplying it without a reader is refused.

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
    reader: PostgresEndpoint | None = None
    acquire_timeout: float = 15.0
    startup_timeout: float = 30.0
    reader_startup: ReaderStartup | _Omitted = _OMITTED
    prepare_threshold: int | None = 5

    def __post_init__(self) -> None:
        object.__setattr__(self, "writer", _endpoint("writer", self.writer))
        reader = None if self.reader is None else _endpoint("reader", self.reader)
        object.__setattr__(self, "reader", reader)
        object.__setattr__(self, "reader_startup", _reader_startup(self.reader_startup, reader))
        object.__setattr__(
            self, "acquire_timeout", positive_seconds("acquire_timeout", self.acquire_timeout)
        )
        object.__setattr__(
            self, "startup_timeout", positive_seconds("startup_timeout", self.startup_timeout)
        )
        object.__setattr__(self, "prepare_threshold", _prepare_threshold(self.prepare_threshold))

    def open(self) -> PostgresRuntime:
        """Open one independent ready runtime, or raise having released what it took.

        Ready means proved: each route's pool exists, a real connection was
        acquired from it, initialized, and made to decode an integer, an
        unbounded instant, a structured document, and a Float32 and a Float64
        exactly, and it was given back — the reader's having authenticated the
        writer's login — unless an unreachable reader was deferred. A failure at
        any of those raises :class:`~parallax.core.db_port.DatabaseStartupError`
        naming the route and the phase, and publishes no runtime: every pool is
        closed and a startup connection already acquired goes through the
        ordinary cleanup path, which reports what it established rather than
        promising reclamation.
        """
        startup = self.reader_startup
        return open_runtime(
            self.writer,
            self.reader,
            acquire_timeout=self.acquire_timeout,
            startup_timeout=self.startup_timeout,
            reader_startup="deferrable" if isinstance(startup, _Omitted) else startup,
            prepare_threshold=self.prepare_threshold,
        )
