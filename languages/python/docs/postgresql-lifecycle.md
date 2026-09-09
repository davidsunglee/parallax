# PostgreSQL connection lifecycle

How a Parallax application over PostgreSQL gets connections, holds them, and
gives them back — and what a deployment has to decide because of it.

This is operational guidance. The normative contracts are `core/spec/m-db-port.md`
(configuration, runtime, acquisition, relinquishment, and what a pool publishes),
`core/spec/m-execution-lifecycle.md` (observation, including pool observation),
and `languages/python/spec/python.md` (the Python realization). Nothing here
restates them normatively; where the two could disagree, they win.

Every Python block below marked as a story is the exact source of an executable
function in `parallax.conformance.database_pooling_stories`. They are checked for
drift by `tests/unit/test_postgresql_lifecycle_guide.py` and run against a real
PostgreSQL server by `tests/api/test_database_pooling.py`, so nothing here is a
snippet that has never executed. Every other block is import lines, whose names
the same guard resolves. The prose around them has no such guard: where it and a
specification disagree, the specification is right.

## What you build, and what owns it

```python
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresAdapter
from parallax.snapshot import ServingModel, connect, prepare_model
```

`PostgresAdapter` is **configuration**. Constructing one opens no connection, no
pool, and no thread: it parses the connection string, validates the retention
policy, and stores both. That is what makes it safe to build at import time, hold
as a module constant, and share between threads — in any of the four retention
forms.

<!-- story: construction_snippet -->

```python
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
```

`connect` is what opens a runtime, and the handle it returns is what owns that
runtime. **Close it**: `db.close()` and the context manager are equivalent, and
both are idempotent. The model it serves is either form — the static shorthand,
or a `ServingModel` the application prepared and holds.

<!-- story: closing_snippet -->

```python
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
```

Every `connect` over one configuration opens an independent runtime, so closing
one handle leaves another working.

<!-- story: retention_snippet -->

```python
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
```

## Retention

`pool=PoolOptions(...)` keeps connections between operations;
`pool=OnDemandOptions(...)` keeps none, closing each on release unless a caller
is already waiting for one. Omitting `pool` takes the retaining defaults.

| Setting | Retaining default | On demand |
|---|---|---|
| `min_size` | 1 | — (no inventory to keep) |
| `max_size` | 10 | 10 |
| `acquire_timeout` | 15.0 s | 15.0 s |
| `startup_timeout` | 30.0 s | 30.0 s |
| `max_waiting` | 0 (uncounted) | 0 (uncounted) |
| `validate_on_checkout` | `True` | `True` |
| `max_idle` | 600.0 s | — (no inventory to retire) |
| `max_lifetime` | 3600.0 s | 3600.0 s |
| `reconnect_timeout` | 300.0 s | 300.0 s |
| `num_workers` | 3 | 3 |

Both records are frozen and validated at construction; change one by building
another (`dataclasses.replace` works and revalidates). The defaults are a
starting point chosen to be safe rather than fast, and **no benchmark claims
them optimal** — tune from measured occupancy and queue latency, which the pool
observation section below is how you obtain.

Three of them are the driver's own maintenance and keep the driver's meanings.
`max_idle` drives periodic, incremental retirement of excess capacity rather
than an exact per-connection idle deadline. `max_lifetime` retains the driver's
jitter, so connections built together do not all retire together.
`reconnect_timeout` bounds the driver's own background attempts to restore
capacity, and `num_workers` sizes the driver's maintenance threads — not your
application's. Retirement never interrupts work in progress, and the driver
reconnecting is not a Parallax transaction retry.

An on-demand pool still runs those maintenance workers and still cares about
lifetime, because a return handed straight to a waiter is a connection being
reused. What it does not do is keep idle inventory, which is why its
`pool_available` reading is zero even while it is serving perfectly well.

## What each operation holds

Each operation acquires a connection and gives it back:

| Operation | Holds a connection |
|---|---|
| Eager read (`db.find`, `db.wire.find`, `db.read_rows`) | For the whole read, materialization included |
| Standalone delivery (`db.stream`, `db.wire.stream`) | From its first page to its exhaustion, failure, or early close |
| Transaction attempt (`db.transact`) | For the attempt, every participating read, write and delivery inside it included |

Work that INHERITS a connection takes none of its own: a read inside a
transaction runs on the attempt's connection, and a delivery's later pages run
on the one its first page took. A retry acquires afresh — and so is refused
outright once the handle is closed, rather than replaying.

**A delivery holds its slot for as long as it is being read.** That is the one
pooling consequence an application has to design around: an independent
`db.transact(...)` inside a streaming loop needs ANOTHER connection and will time
out where the delivery occupies them all. A delivery that has exhausted or failed
releases at that point rather than at the end of its `with` block, so the slot
comes back where the delivery ends.

A delivery's pages run on one backend session, which is what gives them a
consistent read of a stable table. That affinity is a fact about a direct
connection to a backend; a transaction-multiplexing proxy between you and the
server can move statements between backends and takes it away. Parallax adds no
snapshot guarantee of its own, no server cursor, and no resumption: a connection
lost mid-delivery fails the delivery rather than reconnecting and continuing.

If a connection string already points at a reader endpoint, that is where its
connections go; Parallax adds no replica routing and no second runtime to route
between.

## Timeouts

Five controls are often confused and are genuinely distinct:

| Control | Bounds |
|---|---|
| `acquire_timeout` | ONE caller's wait for a connection |
| `startup_timeout` | Becoming ready before `connect` returns — the whole of it, shared across opening, waiting, probing and releasing, never restarted between them |
| `reconnect_timeout` | The driver's own background retrying to restore capacity |
| `statement_timeout` (a session setting) | The server's execution of one statement |
| Your application's own limits | Transaction duration, request deadlines |

None of them is a retry budget for an operation, and none of them is a hard
wall-clock guarantee. Both Parallax deadlines are **cooperative**: they stop the
next step from starting, and they cannot interrupt a driver call already in
flight or the cleanup that must follow one. A connection that arrives after the
budget is spent is given back and reported as a timeout rather than used.

One driver behavior is worth knowing before tuning on-demand retention: for a
connection it establishes directly, the driver derives its own
`connect_timeout` from whatever remains of the acquisition budget, **overriding**
a `connect_timeout` the connection string carries for that creation. So
`connect_timeout=2` with `acquire_timeout=15` does not preserve a two-second
establishment limit, and the two do not compose as independent limits.
`acquire_timeout` is the control that matters there. Startup acquisition derives
its own the same way, from what remains of `startup_timeout`.

## Process and application lifetime

**Build the handle after the fork, not at module import.** A forking application
server imports your module once and then forks; a pool created before the fork
would hand the same sockets to every worker. Configuration is a value and is
safe to build at import time — the handle is not.

For an ASGI application, that means composing in the lifespan:

<!-- story: serving_snippet -->

```python
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
```

FastAPI takes exactly that object as its `lifespan=` argument, and no part of
this needs FastAPI to be installed: a lifespan is an async context manager and
FastAPI's own endpoint offloading is a worker thread. The server drains the
requests it has accepted before running the shutdown half — but that drain is
the server's own and is bounded by its own configuration. Uvicorn waits for
`--timeout-graceful-shutdown` and then cancels what has not finished, and
cancelling an `await asyncio.to_thread(...)` ends the await rather than the
worker thread running the operation, so a blocking operation can still be
running when the lifespan closes the handle. Size that timeout for the longest
operation you offload. What makes closing there survivable regardless is
Parallax's own part of the bargain: work already admitted finishes on the
connection it holds, including statements it has not issued yet, while anything
needing a new connection is refused from the close onward.

**Offload complete operations.** From an async endpoint, what crosses into the
worker thread must be the WHOLE operation — statements, materialization, and the
release. Handing a `Snapshot` back to be walked on the event loop, or a stream to
be iterated there, moves part of the operation onto the loop and keeps the
connection for as long as the loop takes to get around to it. Synchronous
endpoints need none of this: the server already runs them off the loop.

Parallax adds no async interface, so no Parallax call ever awaits while holding a
connection. Your own code still can: entering `db.stream(...)` on the event loop,
reading its first page, and then awaiting anything before the delivery ends holds
that connection for the whole of the await, and a slow client or a busy loop
decides how long that is. A delivery is the shape to watch, because it is the one
that outlives the call that started it — which is what offloading complete
operations prevents.

**Pool capacity is not HTTP concurrency.** An operation occupies a worker thread
and a connection for its whole duration, so the number that can run at once is
the smaller of the two, and raising `max_size` past the threadpool buys nothing.
Budget in the other direction as well: total connections is
`max_size` × runtimes-per-process × processes-per-host × hosts, and the server's
own `max_connections` (minus what it reserves for superusers, and minus what
your migrations, backups, and consoles take) is the ceiling all of them share.
An application that serves two models through two handles has two runtimes and
therefore two pools.

Waiting is synchronous and occupies the waiting thread. A `max_waiting` above
zero converts a queue that would have grown into an immediate refusal, which is
usually what a request-serving process wants: a caller that will time out anyway
is better told now.

## Observing the pool

The runtime publishes read-only measurements. A `lifecycle_provider` that also
implements `observe_pool` is offered them once at composition; what it answers
with is closed when the handle closes.

<!-- story: observation_snippet -->

```python
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
```

Registration happens **before** the handle is published, so a registration that
raises fails `connect` and closes the runtime rather than leaving a handle to
explain itself later. Where several Providers are composed through
`FanoutLifecycleProvider`, each is offered the source and one of them raising
closes the registrations already taken.

The handle closes the **registration**, never your exporter. The queue, the
metrics client, and the scrape endpoint behind it are yours and outlive the
handle.

Sampling is a question you ask on your own cadence — a scrape, a timer, a health
check. It runs no statement, takes no connection, and needs no credential, which
is why a reading succeeds even while every slot is held. It answers one of three:

| Sample | Meaning |
|---|---|
| `PoolAvailable(measurements)` | This is the reading |
| `PoolUnavailable(diagnostic)` | This reading did not happen; the runtime is still alive and the next one may |
| `PoolDetached()` | The handle has closed; there is nothing to read |

Unavailable is not a zero. Publishing a substituted zero for one is how a
monitoring dashboard comes to show an outage that did not happen; skip the
sample instead, and ask again on your next cadence.

`PoolMeasurements` carries five gauges and nine counters:

| Measurement | What it is, and what it is not |
|---|---|
| `pool_min`, `pool_max` | The retention bounds you configured |
| `pool_size` | Capacity the pool manages, INCLUDING connections reserved but not finished preparing |
| `pool_available` | Idle and immediately takeable. Zero for an on-demand pool by design |
| `requests_waiting` | Queue length. May include entries whose own wait has already expired and that have not been removed |
| `requests_num` | Checkout CALLS, startup's own included |
| `requests_queued`, `requests_wait_ms` | Queue entries, and the milliseconds those queued waits took — not whole acquisition time, and not health-check time |
| `requests_errors` | Checkout calls the pool reported an error for. Not every acquisition failure |
| `connections_num`, `connections_ms` | Connection attempts, and the time successful attempts took to ESTABLISH — excluding the initialization after |
| `connections_errors` | Failed attempts, excluding a configure-callback refusal |
| `connections_lost`, `returns_bad` | Connections found broken, and connections handed back unusable — a deliberate Parallax invalidation contributes to the latter |

Three caveats an exporter must not paper over. **There is no active-connection
gauge**: `pool_size - pool_available` is not one, and the hold duration a Release
event reports belongs to one operation rather than to the pool. **Counters
include the pool's own housekeeping and may reset**, so treat them as counters
rather than as absolute totals. **A reading is not atomic**, so two of its fields
may describe instants a moment apart and may look inconsistent; that is a pool
measured mid-change, not a broken one.

What is worth watching: `requests_waiting` and `requests_wait_ms` say whether
callers are queueing, which is the signal that `max_size` is too small for the
offered load; `pool_available` sitting at `pool_max` says the opposite.
`connections_num` climbing steadily against a stable `pool_size` says
connections keep being ATTEMPTED, which is not the same as being replaced: the
counter is incremented before each attempt, so establishment that keeps failing
climbs it exactly as replacement does, and a connection refused in preparation
for a wrong `client_encoding` or `DateStyle` counts as an attempt rather than as
an error. Read it against `connections_errors` and `connections_lost` — errors
climbing with it is failing establishment, `connections_lost` climbing with it
is churn, and neither climbing is a session-setting refusal.

## Session settings

The connection string is libpq's own grammar — keyword/value pairs, a
`postgresql://` URI, a `service=` reference, or the empty string, which asks
libpq to take everything from the environment. It is stored exactly as given,
kept out of the adapter's representation, and resolved against the environment,
service files and server defaults when each physical connection is created, so
immutable configuration does not freeze inputs a deployment expects to change.
Local parsing at construction proves neither connectivity nor that a referenced
service file, credential, or server setting exists.

Two effective settings are load-bearing and refused when they are wrong, before
any modeled statement runs: the client encoding must be UTF-8 and `DateStyle`
must be ISO (any field order within ISO). The check reads the established
connection's own parameters and runs no SQL, on every connection the pool
creates — initial capacity, growth, replacements, and on-demand connections
alike. Everything else a string, an environment, a service file or a server
default establishes is preserved: the time zone, a stronger default isolation, a
read-only session, a search path, statement and lock timeouts. Parallax owns
autocommit, physical-close semantics, row shape, and its own codecs, and does
not restore caller settings because it never changes them.

`prepare_threshold` is the driver's server-side auto-preparation after that many
identical executions, defaulting to 5. Pass `None` where the same connection may
see a table's shape change underneath identical query text — a
schema-reset-per-case harness, never a deployed application.

## What gets logged, and by whom

Three reporting paths with three different disclosure policies. They are not
interchangeable and only one of them is yours to redact.

| Path | Carries | Policy |
|---|---|---|
| Lifecycle events (a Handler you installed) | Rich detached diagnostics: bounded message and stack, error type and code, the cleanup a release established | **Yours.** You decide what is exported and what is redacted. Detaching and truncating a native message does not sanitize it |
| `parallax.resources` (standard `logging`) | One fixed sentence per occasion, and the cleanup phase and code where a cleanup is what failed — nothing else. No credential, SQL, bind, native message, stack, structured extra, or `exc_info`. A pool observation that would not close is the one record carrying no phase and no code, because nothing was relinquished | Parallax's, and deliberately thin: it must be safe to leave on in a deployment that has redacted nothing. It speaks only when something went wrong AND no Handler received it |
| `psycopg.pool` (the driver's own logger) | Whatever the driver logs, exception text included | **The driver's.** Parallax's restriction does not reach it. Configure it yourself |

`parallax.resources` is a fixed logger name so an operator silences or routes
resource reporting by naming one logger. It is a floor rather than a second
export path: a cleanup problem reaches exactly one of a Handler and this log,
never both and never neither.

## Migrating from the earlier surface

| Before | Now |
|---|---|
| `PostgresAdapter(open_psycopg_connection)` | `PostgresAdapter(connection_string)` — configuration, not a live connection |
| `PostgresAdapter.connect(conninfo, ...)` | `PostgresAdapter(conninfo, prepare_threshold=...)`, opened by `connect` |
| `adapter.connection` (raw psycopg connection) | removed; open your own connection for DDL, migrations, and fixtures |
| `adapter.close()` | `db.close()`, or leaving the handle's `with` block |
| `DbPort` | `DatabaseConnection` |
| `from parallax.core.execution_lifecycle import FailureDiagnostic` | `from parallax.core.diagnostics import FailureDiagnostic` |

A handle previously held one connection forever and released nothing; it now
owns a runtime and must be closed. Nothing else about a read, a stream, or a
transaction changes: the same verbs, the same results, and the same transaction
outcomes.

The two removals with the widest blast radius are the raw accessor and the
implicit lifetime. DDL, migrations, fixture loading, and any statement you author
verbatim now run on a connection you opened yourself — Parallax hands out no raw
pooled session and no escape hatch to one. And a handle built and forgotten used
to leak one connection; it now holds a pool and maintenance threads, so a process
that composes handles per request will exhaust the server rather than merely
waste one socket.
