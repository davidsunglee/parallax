"""``parallax.conformance.database_pooling_stories`` — the executable stories the
PostgreSQL lifecycle guide is written out of.

The guide (`languages/python/docs/postgresql-lifecycle.md`) is operational
advice, and operational advice that has never run is how a deployment snippet
comes to name a keyword that no longer exists. So every Python block in it that
shows an application composing or serving through a handle is the exact source
of a function here, guarded by ``tests/unit/test_postgresql_lifecycle_guide.py``
and executed against real Postgres by ``tests/api/test_database_pooling.py``.

Three shapes, each answering a question the guide raises:

* **Retention.** One configuration, two independent handles, and what closing one
  does to the other.
* **Pool observation.** A Provider that observes the runtime rather than any
  operation, what it registers, and what it reads.
* **Application lifetime.** The lifespan an ASGI application composes the handle
  in, and the boundary a synchronous operation crosses to be served from an
  async endpoint. Neither imports a web framework: the lifespan is an async
  context manager and the offload is a worker thread, which is what FastAPI's
  ``lifespan=`` argument and its own threadpool are.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account
from parallax.core.db_port import (
    DatabaseAdapter,
    PoolAvailable,
    PoolDetached,
    PoolMetricsSource,
    PoolSample,
)
from parallax.core.entity import DomainModel
from parallax.core.execution_lifecycle import (
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ExecutionLifecycleProvider,
    RootExecution,
)
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresAdapter
from parallax.snapshot import ServingModel, connect
from parallax.snapshot.handle import Database

__all__ = [
    "ClosedBothWays",
    "PoolGauges",
    "PoolReading",
    "PoolWatch",
    "PoolWatchingProvider",
    "RetentionForms",
    "RetentionShape",
    "a_handle_is_closed_by_leaving_its_scope_or_by_closing_it",
    "account_balances",
    "closing_snippet",
    "construction_snippet",
    "every_retention_form_is_one_configuration_value",
    "observation_snippet",
    "one_configuration_opens_independent_runtimes",
    "pooled_database",
    "retention_snippet",
    "serve_account_balances",
    "serving_snippet",
    "the_pool_reports_its_own_capacity_and_stops_when_the_handle_closes",
]


# --------------------------------------------------------------------------- #
# Construction: the retention forms, both model forms, and both closes.        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RetentionForms:
    default: PostgresAdapter
    tuned: PostgresAdapter
    zero_minimum: PostgresAdapter
    on_demand: PostgresAdapter


def every_retention_form_is_one_configuration_value(conninfo: str) -> RetentionForms:
    """The four ways to configure retention, none of which opens anything.

    Each one parses the connection string, validates the policy, and stops
    there. ``default`` takes the retaining defaults; ``tuned`` sets them;
    ``zero_minimum`` retains connections but keeps none until one is asked for;
    ``on_demand`` retains none at all and closes each connection on release.
    """
    return RetentionForms(
        default=PostgresAdapter(conninfo),
        tuned=PostgresAdapter(conninfo, pool=PoolOptions(min_size=2, max_size=20)),
        zero_minimum=PostgresAdapter(conninfo, pool=PoolOptions(min_size=0, max_size=20)),
        on_demand=PostgresAdapter(conninfo, pool=OnDemandOptions(max_size=20)),
    )


@dataclass(frozen=True, slots=True)
class ClosedBothWays:
    scoped_rows: int
    explicit_rows: int


def a_handle_is_closed_by_leaving_its_scope_or_by_closing_it(
    adapter: DatabaseAdapter, model: DomainModel, serving: ServingModel
) -> ClosedBothWays:
    """Both model forms, and the two equivalent ways to give a runtime back.

    ``model`` is the static shorthand, which ``connect`` prepares once into a
    Serving Model of its own; ``serving`` is one the application prepared and
    holds, so that publishing a later edition stays its own decision. Either
    connects, and neither changes what the handle owns.

    Closing is the part that is not optional. The ``with`` block and the
    explicit ``close`` are the same call, and a handle that gets neither holds a
    pool and its maintenance threads for the life of the process.
    """
    with connect(adapter, model) as scoped:
        scoped_rows = len(account_balances(scoped))
    explicit = connect(adapter, serving)
    try:
        explicit_rows = len(account_balances(explicit))
    finally:
        explicit.close()
    return ClosedBothWays(scoped_rows, explicit_rows)


# --------------------------------------------------------------------------- #
# Retention: what a configuration is, and what a handle owns.                  #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RetentionShape:
    first_rows: int
    second_rows_after_first_closed: int


def one_configuration_opens_independent_runtimes(
    adapter: DatabaseAdapter, model: DomainModel
) -> RetentionShape:
    """Two handles from one configuration own two runtimes.

    ``adapter`` is a value, not a resource: constructing it opened no connection
    and no pool, so it is safe to build once at import time and hand to every
    ``connect`` in the process. Each ``connect`` opens a runtime of its own, and
    each handle owns the one it was given — which is why closing the first below
    leaves the second serving.
    """
    with connect(adapter, model) as first:
        first_rows = len(account_balances(first))
        second = connect(adapter, model)
    with second:
        return RetentionShape(first_rows, len(account_balances(second)))


def account_balances(db: Database) -> list[Decimal]:
    """One COMPLETE operation: read, materialize, and answer plain values.

    Completeness is the point wherever this is called from a worker thread. The
    connection is acquired when the read starts and given back when it has
    finished materializing, and what comes back holds nothing that would still
    need the database — so the caller receives values rather than a handle to
    work that has not happened yet.
    """
    return [account.balance for account in db.find(Account.where(Account.all)).results()]


# --------------------------------------------------------------------------- #
# Pool observation: watching the runtime rather than any operation.            #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PoolGauges:
    """The four numbers an operator actually watches, taken from one sample."""

    managed: int
    idle: int
    waiting: int
    checkouts: int


class PoolWatch:
    """The registration a handle closes, and the exporter's own sampling seam.

    Closing it gives up the interest. It closes no exporter, queue, or metrics
    client: those are the application's, they outlive the handle, and Parallax
    never touches them.
    """

    def __init__(self, source: PoolMetricsSource) -> None:
        self._source = source
        self.closed = False

    def read(self) -> PoolGauges | None:
        """One reading, or ``None`` where there is no reading to take.

        The cadence is the exporter's own — a scrape, a timer, a health check —
        because sampling is a question rather than a subscription. Unavailable
        and detached both answer ``None`` here, and they are different: the
        first is a live runtime that could not be read this time, the second is
        a handle that has closed.
        """
        sample: PoolSample = self._source.sample()
        if not isinstance(sample, PoolAvailable):
            return None
        measured = sample.measurements
        return PoolGauges(
            managed=measured.pool_size,
            idle=measured.pool_available,
            waiting=measured.requests_waiting,
            checkouts=measured.requests_num,
        )

    def detached(self) -> bool:
        return isinstance(self._source.sample(), PoolDetached)

    def close(self) -> None:
        self.closed = True


class PoolWatchingProvider:
    """A Provider interested in the pool and in no individual operation.

    The two interests are independent. ``open`` returns ``None`` for every root,
    which declines execution observation outright and costs the operations
    nothing; ``observe_pool`` is what makes this Provider worth installing. A
    Provider that wanted both would return a Handler here as well.
    """

    def __init__(self) -> None:
        self.watch: PoolWatch | None = None

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        del execution
        return None

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        """Nothing to do, because this Provider opens no Handler to fail.

        The seam is one Protocol with two methods, so a Provider implements
        both. An application that accepted roots would report or count the
        failure here.
        """
        del error

    def observe_pool(self, source: PoolMetricsSource, /) -> PoolWatch:
        """Take an interest in this runtime's pool, once, at composition.

        ``source`` is stable for the runtime's whole life, so it is retained
        rather than re-fetched. Returning ``None`` instead would decline.
        """
        self.watch = PoolWatch(source)
        return self.watch


@dataclass(frozen=True, slots=True)
class PoolReading:
    at_rest: PoolGauges
    while_working: PoolGauges
    detached_after_close: bool
    registration_closed: bool


def the_pool_reports_its_own_capacity_and_stops_when_the_handle_closes(
    adapter: DatabaseAdapter, model: DomainModel
) -> PoolReading:
    """Watch one runtime's pool from composition to close.

    The Provider is offered the source once, before ``connect`` returns, and the
    registration it answers with lives exactly as long as the handle. Sampling
    runs no statement and takes no connection, which is why the reading taken
    from inside a streaming loop below — while the delivery is holding the only
    slot — succeeds rather than queueing behind it.
    """
    provider = PoolWatchingProvider()
    with connect(adapter, model, lifecycle_provider=provider) as db:
        watch = provider.watch
        assert watch is not None
        at_rest = watch.read()
        with db.stream(Account.where(Account.all), batch_size=1) as roots:
            next(iter(roots))
            while_working = watch.read()
    assert at_rest is not None
    assert while_working is not None
    return PoolReading(at_rest, while_working, watch.detached(), watch.closed)


# --------------------------------------------------------------------------- #
# Application lifetime: the lifespan, and the offload boundary.                #
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def pooled_database(
    adapter: DatabaseAdapter,
    model: DomainModel,
    *,
    lifecycle_provider: ExecutionLifecycleProvider | None = None,
) -> AsyncGenerator[Database]:
    """The application lifespan: one handle for the process, opened and closed.

    This is what an ASGI application passes as ``lifespan=``. Everything before
    the ``yield`` runs at startup and everything after it at shutdown, once the
    server has drained the requests it accepted — a drain that is the SERVER's
    and is bounded by its own configuration, since a graceful-shutdown timeout
    cancels whatever has not finished and cancelling an ``asyncio.to_thread``
    await ends the await rather than the worker beneath it. Closing here is safe
    either way, which is Parallax's half of the bargain: work already admitted
    finishes on the connection it holds, and anything needing a new one is
    refused.

    Both halves are offloaded because both block. Composition opens the pool and
    proves it can execute; closing tears it down. Neither belongs on an event
    loop that is meanwhile meant to be serving.

    Build the handle HERE rather than at module import. A forking server imports
    the module once and then forks, and a pool created before the fork would
    hand the same sockets to every worker.
    """
    db = await asyncio.to_thread(connect, adapter, model, lifecycle_provider=lifecycle_provider)
    try:
        yield db
    finally:
        await asyncio.to_thread(db.close)


async def serve_account_balances(db: Database) -> list[Decimal]:
    """An async endpoint's body: offload the WHOLE operation, await the values.

    The boundary matters more than the offload. What crosses it is one complete
    operation — every statement, the materialization, and the release — so the
    connection is taken and given back inside the worker thread and the event
    loop is never holding one. Handing back a Snapshot to be walked on the loop,
    or a stream to be iterated there, would move part of the operation back onto
    it and keep the connection for as long as the loop took to get around to it.

    Pool capacity is not HTTP concurrency for the same reason: each of these
    occupies a worker thread AND a connection for its whole duration, so the
    number of them that can run at once is the smaller of the two.
    """
    return await asyncio.to_thread(account_balances, db)


def construction_snippet() -> str:
    return _sources(RetentionForms, every_retention_form_is_one_configuration_value)


def closing_snippet() -> str:
    return _sources(a_handle_is_closed_by_leaving_its_scope_or_by_closing_it)


def retention_snippet() -> str:
    return _sources(one_configuration_opens_independent_runtimes, account_balances)


def observation_snippet() -> str:
    return _sources(
        PoolGauges,
        PoolWatch,
        PoolWatchingProvider,
        the_pool_reports_its_own_capacity_and_stops_when_the_handle_closes,
    )


def serving_snippet() -> str:
    return _sources(pooled_database, serve_account_balances)


def _sources(*parts: Callable[..., object] | type) -> str:
    """The exact source of ``parts``, which is what the guide renders.

    Rendered from the objects rather than copied into Markdown, so a guide block
    cannot describe a spelling that no longer compiles.
    """
    return "\n\n\n".join(inspect.getsource(part).rstrip("\n") for part in parts)
