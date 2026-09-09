"""The concrete Postgres database adapter (psycopg) — a leaf production artifact.

``PostgresAdapter`` is CONFIGURATION. Constructing one opens no connection, no
pool, and no thread; it parses the connection string, validates the retention
policy, and stores both. That is what makes it safe to build at import time, hold
as a module constant, share between threads, and — importantly for a forking web
server — build before a fork and open after one.

Opening is a separate act with a separate owner. ``Database.connect`` calls
:meth:`PostgresAdapter.open` and owns the runtime it gets back until it closes.
Each ``open`` produces an INDEPENDENT runtime, so reusing one configuration for
two handles gives two pools that know nothing about each other, and closing
either leaves the other working.

The implementation is split by responsibility behind this one public value:
``_options`` validates the retention policy, ``_runtime`` opens and closes the
native pool, ``_context`` owns one acquisition's lifetime, and ``_connection``
owns scoped execution, the codecs every physical connection gets, and the
authoritative transaction outcomes. None of those names is exported; an
application configures this value and executes through the handle it composes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg
import psycopg.conninfo

from parallax.core.dialect import POSTGRES
from parallax.postgres._options import OnDemandOptions, PoolOptions, RetentionOptions
from parallax.postgres._runtime import PostgresRuntime, open_runtime

__all__ = ["PostgresAdapter"]

_TYPE_REFUSAL = "connection_string must be a string."
_SYNTAX_REFUSAL = (
    "Invalid PostgreSQL connection string; expected libpq keyword/value syntax or a PostgreSQL URI."
)


def _parsed(connection_string: str) -> None:
    """Prove the string is one the driver will accept, and disclose nothing if not.

    Parsing here is a spelling check and nothing more: it opens no socket,
    resolves no host, reads no service file, and proves neither that the
    destination exists nor that the credentials work. Those resolve when each
    physical connection is created, which is deliberate — immutable
    configuration must not freeze an environment that the deployment expects to
    change underneath it.

    The refusal is fixed text. A parser's own message can quote the input it
    rejected, and the input is a connection string: it can carry a password. So
    neither the string nor the native message reaches the message, the logs, or
    the displayed cause chain, and the native exception is suppressed as a cause
    rather than chained. This disclosure rule is specific to construction-time
    configuration errors — a failure to CONNECT later chains its cause normally,
    because by then nothing is quoting the caller's input back.
    """
    if type(connection_string) is not str:
        raise TypeError(_TYPE_REFUSAL)
    try:
        psycopg.conninfo.conninfo_to_dict(connection_string)
    except psycopg.Error:
        raise ValueError(_SYNTAX_REFUSAL) from None


def _prepare_threshold(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"prepare_threshold takes an int or None (got {value!r})")
    if value < 0:
        raise ValueError(f"prepare_threshold takes a nonnegative int or None (got {value!r})")
    return value


def _retention(pool: object) -> RetentionOptions:
    if not isinstance(pool, PoolOptions | OnDemandOptions):
        raise TypeError(
            f"pool takes PoolOptions or OnDemandOptions (got {pool!r}); omit it for the "
            f"retaining defaults"
        )
    return pool


@dataclass(frozen=True, slots=True)
class PostgresAdapter:
    """How to reach one Postgres database, and how to hold connections to it.

    ``connection_string`` is libpq's own grammar — keyword/value pairs, a
    ``postgresql://`` URI, a ``service=`` reference, or the empty string, which
    asks libpq to take everything from the environment. It is stored exactly as
    given and kept out of this value's representation, because a connection
    string is a place a password lives and a repr is a place values get logged.

    ``pool`` selects retention. Omitting it takes :class:`PoolOptions`' defaults;
    :class:`OnDemandOptions` keeps no idle connections instead. Change either by
    constructing a new configuration — ``dataclasses.replace`` works and
    revalidates — never by mutating this one, so a runtime already open cannot
    be reconfigured underneath its handle.

    ``prepare_threshold`` is the driver's server-side auto-preparation after
    that many identical executions. The default suits an ordinary long-lived
    application connection against one stable schema. Pass ``None`` to disable
    it where the SAME connection may see a table's shape change underneath
    identical query text — a schema-reset-per-case harness, never a deployed
    application — because Postgres's own "cached plan must not change result
    type" is a server-side plan-cache invalidation rather than anything
    Parallax can reconcile.
    """

    dialect = POSTGRES
    """The one place this adapter's SQL spelling is stated.

    Unannotated, so it is a class attribute rather than one of this record's
    fields: a composition root selects an adapter and lowers SQL in the spelling
    it will execute in before any configuration, let alone any resource, exists,
    and no caller can construct one claiming a different spelling.
    """

    connection_string: str = field(repr=False)
    pool: RetentionOptions = field(default_factory=PoolOptions, kw_only=True)
    prepare_threshold: int | None = field(default=5, kw_only=True)

    def __post_init__(self) -> None:
        _parsed(self.connection_string)
        object.__setattr__(self, "pool", _retention(self.pool))
        object.__setattr__(self, "prepare_threshold", _prepare_threshold(self.prepare_threshold))

    def open(self) -> PostgresRuntime:
        """Open one independent ready runtime, or raise having released what it took.

        Ready means proved: the pool exists, a real connection was acquired,
        initialized, and made to decode an integer, an unbounded instant, and a
        structured document, and it was given back. A failure at any of those
        raises :class:`~parallax.core.db_port.DatabaseStartupError` naming the
        phase, and publishes no runtime: the pool is closed and a startup
        connection already acquired goes through the ordinary cleanup path,
        which reports what it established rather than promising reclamation.
        """
        return open_runtime(self.connection_string, self.pool, self.prepare_threshold)
