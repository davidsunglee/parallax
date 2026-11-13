# PostgreSQL connection lifecycle

How a Parallax application over PostgreSQL gets connections, holds them, and
gives them back — and what a deployment has to decide because of it.

This is operational guidance. The normative contracts are `core/spec/m-db-port.md`
(configuration, runtime, acquisition, release, and what a pool publishes),
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

## Installation and supported servers

Install `parallax-postgres` with `parallax-snapshot` as shown in
[Getting started](guide/01-getting-started.md#install). The
[binding contract](../spec/execution.md#supported-postgresql) owns the supported
PostgreSQL range; the package metadata and wheel targets linked from that guide
own Python and platform support. Install `parallax-aws` with its `postgres` extra
when using RDS IAM credentials. Keep the selected first-party versions equal.

## What you build, and what owns it

```python
from parallax.core import (
    DRIVER_MANAGED,
    CredentialSource,
    DriverManaged,
    Password,
    ServingModel,
    prepare_model,
)
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresAdapter, PostgresEndpoint
from parallax.snapshot import connect
```

`PostgresAdapter` and the `PostgresEndpoint` it is given as its `writer` are
**configuration**. Constructing either opens no connection, no pool, and no
thread: the endpoint parses the connection string, validates the credential
declaration and the retention policy, and stores them, and the adapter
validates the budgets its runtime spends. That is what makes them safe to build
at import time, hold as module constants, and share between threads — in any of
the four retention forms.

<!-- story: construction_snippet -->

```python
@dataclass(frozen=True, slots=True)
class RetentionForms:
    default: PostgresAdapter
    tuned: PostgresAdapter
    zero_minimum: PostgresAdapter
    on_demand: PostgresAdapter


def every_retention_form_is_one_configuration_value(
    conninfo: str, credentials: CredentialSource | DriverManaged
) -> RetentionForms:
    """The four ways to configure retention, none of which opens anything.

    Each one parses the connection string, validates the credential declaration
    and the policy, and stops there. ``default`` takes the retaining defaults;
    ``tuned`` sets them; ``zero_minimum`` retains connections but keeps none
    until one is asked for; ``on_demand`` retains none at all and closes each
    connection on release.

    ``conninfo`` says where the database is and carries no password;
    ``credentials`` says how its login authenticates — a ``Password``, a
    provider's own source asked once per physical connection, or
    ``DRIVER_MANAGED`` where the driver and the server settle it themselves.
    """
    return RetentionForms(
        default=PostgresAdapter(writer=PostgresEndpoint(conninfo, credentials=credentials)),
        tuned=PostgresAdapter(
            writer=PostgresEndpoint(
                conninfo, credentials=credentials, pool=PoolOptions(min_size=2, max_size=20)
            )
        ),
        zero_minimum=PostgresAdapter(
            writer=PostgresEndpoint(
                conninfo, credentials=credentials, pool=PoolOptions(min_size=0, max_size=20)
            )
        ),
        on_demand=PostgresAdapter(
            writer=PostgresEndpoint(
                conninfo, credentials=credentials, pool=OnDemandOptions(max_size=20)
            )
        ),
    )
```

`connect` is what opens a runtime, and the handle it returns is what owns that
runtime. **Close it**: `db.close()` and the context manager are equivalent, and
both are idempotent. The model it serves is either form — the static shorthand,
or a `ServingModel` the application prepared and holds.

<!-- story: closing_snippet -->

```python
def a_handle_is_closed_by_leaving_its_scope_or_by_closing_it(
    adapter: DatabaseAdapter, model: DomainModel, binding: PostgresBinding, serving: ServingModel
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
    with connect(adapter, model, binding=binding) as scoped_root:
        scoped = scoped_root.using_database_login()
        scoped_rows = len(account_balances(scoped))
    explicit_root = connect(adapter, serving)
    explicit = explicit_root.using_database_login()
    try:
        explicit_rows = len(account_balances(explicit))
    finally:
        explicit_root.close()
    return ClosedBothWays(scoped_rows, explicit_rows)
```

Every `connect` over one configuration opens an independent runtime, so closing
one handle leaves another working.

<!-- story: retention_snippet -->

```python
def one_configuration_opens_independent_runtimes(
    adapter: DatabaseAdapter, model: DomainModel, binding: PostgresBinding
) -> RetentionShape:
    """Two handles from one configuration own two runtimes.

    ``adapter`` is a value, not a resource: constructing it opened no connection
    and no pool, so it is safe to build once at import time and hand to every
    ``connect`` in the process. Each ``connect`` opens a runtime of its own, and
    each handle owns the one it was given — which is why closing the first below
    leaves the second serving.
    """
    with connect(adapter, model, binding=binding) as first_root:
        first = first_root.using_database_login()
        first_rows = len(account_balances(first))
        second_root = connect(adapter, model, binding=binding)
    with second_root:
        second = second_root.using_database_login()
        return RetentionShape(first_rows, len(account_balances(second)))


def account_balances(db: ScopedDatabase) -> list[Decimal]:
    """One COMPLETE operation: read, materialize, and answer plain values.

    Completeness is the point wherever this is called from a worker thread. The
    connection is acquired when the read starts and given back when it has
    finished materializing, and what comes back holds nothing that would still
    need the database — so the caller receives values rather than a handle to
    work that has not happened yet.
    """
    return [account.balance for account in db.find(Account.where(Account.all)).results()]
```

## Where the password lives

The connection string says **where**, and `credentials` says **how**. They are
separate arguments because they have different lifetimes: the string is frozen
into configuration, while the credential is resolved afresh as the driver
establishes connections. That is what lets a fifteen-minute cloud token
authenticate a pool that outlives it.

A string carrying a password is refused at construction, whatever `credentials`
is, and the refusal never quotes the string back:

```text
PostgresEndpoint("postgresql://app:<password>@db.internal/app", credentials=Password("<password>"))
ValueError: connection_string must not carry a password; supply it through credentials.
```

There are three spellings and no fourth:

| `credentials=` | What authenticates the login |
|---|---|
| `Password("s3cret")` | A constant secret. It is its own source — there is no wrapper around it — and it is kept out of every repr |
| any `CredentialSource` | Anything with `resolve() -> Password`. It is asked once per **physical** connection — initial fill, growth, replacement, retirement by `max_lifetime`, on-demand establishment — and never when an acquisition reuses a retained connection. It may block on a network, on the pool's own worker threads or on an acquiring caller's thread, so it must bound its own I/O. A connection already open is never dropped because the credential that opened it expired |
| `DRIVER_MANAGED` | Parallax supplies none. Peer or trust authentication, a client certificate, Kerberos, or libpq's own `PGPASSWORD`, `.pgpass` and `service` files |

Two libpq facts follow from `DRIVER_MANAGED` being a declaration rather than an
absence. Parallax cannot see a password reachable through a `service` file or
through `PGPASSWORD`, so neither is refused by the check above; and under an
explicit source the resolved password wins over both, by libpq's own precedence
for an explicit connection keyword. Declaring `DRIVER_MANAGED` is therefore how
you ask for those mechanisms, rather than how you disable a check.

A source that produces no credential is named rather than timed out. Whatever it
raises is recorded and — unless it is already a `CredentialResolutionError` —
wrapped in one carrying fixed text, with the original chained beneath it. Where
that surfaces depends only on which retention policy was asked to establish the
connection:

| Where | What you get |
|---|---|
| A retained pool, at startup | `DatabaseStartupError` (`phase="minimum_ready"`), after `startup_timeout`: *no database connection this runtime opened could be authenticated* |
| A retained pool, once it is running | `ConnectionAcquisitionError` (`reason="credentials_refused"`), after `acquire_timeout`: *no database connection could be authenticated within the acquisition timeout* |
| An on-demand pool | `ConnectionAcquisitionError` (`reason="credentials_refused"`) on your own thread, with no wait: *a database connection could not be authenticated* |
| A startup probe over an on-demand pool, or over a zero minimum | `DatabaseStartupError` (`phase="acquire"`) wrapping the acquisition failure above |

The `CredentialResolutionError` is the `__cause__` in every row, and whatever
the source itself raised is the cause beneath that. Startup does not fail fast
on one: the pool retries with backoff exactly as it does for a session it cannot
execute under, so a transient token or metadata-service failure costs a retry
rather than a process. That backoff is also why the fixed text matters —
`psycopg.pool` logs the exception's own text on every failed attempt, under the
driver's disclosure policy rather than Parallax's.

### RDS and Aurora, authenticated by IAM

The shipped source for AWS lives in `parallax-aws`, installed beside this
adapter. Its `postgres` extra spells one endpoint in one call:

```python
from parallax.aws.postgres import rds_endpoint
```

```text
writer = rds_endpoint(
    host="orders.cluster-abc.us-east-1.rds.amazonaws.com",   # the endpoint you connect through
    user="orders_service",                                    # the login; IAM proves it
    database="orders",
    region="us-east-1",
    pool=PoolOptions(min_size=2, max_size=20),                # forwarded untouched
)
adapter = PostgresAdapter(writer=writer)
```

What comes back is an ordinary `PostgresEndpoint`: the factory resolves no token
and opens nothing, so it is configuration exactly as the forms above are, and
the application composes the adapter around it. What it states so a deployment
need not is that the connection is encrypted and that the token is signed for
the host, port and user that endpoint's connections then use — each endpoint
signs for its own host. `params` keeps the rest of libpq's grammar open and may
raise `sslmode` to `verify-ca` or `verify-full`, never lower it.

An application that composes its own connection string uses the source alone:

```python
from parallax.aws import RdsIamCredentials
```

```text
writer = PostgresEndpoint(
    "postgresql://orders_service@orders.cluster-abc.us-east-1.rds.amazonaws.com:5432/orders"
    "?sslmode=require",
    credentials=RdsIamCredentials(
        host="orders.cluster-abc.us-east-1.rds.amazonaws.com",
        port=5432,
        user="orders_service",
        region="us-east-1",
    ),
)
```

A token lasts fifteen minutes and a pool lasts longer, which is the case the
per-connection contract above exists for: a connection already open is never
disturbed by the token that opened it ageing out — `core/spec/m-db-port.md`,
"Configuration carries where, and a Credential Source carries how", is where
that rule lives. There is no token cache and no refresh thread.

## Retention

An endpoint's `pool=PoolOptions(...)` keeps connections between operations;
`pool=OnDemandOptions(...)` keeps none, closing each on release unless a caller
is already waiting for one. Omitting `pool` takes the retaining defaults.

| Setting | Retaining default | On demand |
|---|---|---|
| `min_size` | 1 | — (no inventory to keep) |
| `max_size` | 10 | 10 |
| `max_waiting` | 0 (uncounted) | 0 (uncounted) |
| `max_idle` | 600.0 s | — (no inventory to retire) |
| `max_lifetime` | 3600.0 s | 3600.0 s |
| `reconnect_timeout` | 300.0 s | 300.0 s |
| `num_workers` | 3 | 3 |

The runtime's two budgets are the adapter's rather than a pool's, because each
spans the whole runtime: `acquire_timeout` defaults to 15.0 s and
`startup_timeout` to 30.0 s, and `prepare_threshold` defaults to 5.

Every record is frozen and validated at construction; change one by building
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
| Eager read (`db.find`, `db.wire.find`) | For the whole read, materialization included |
| Standalone delivery (`db.stream`, `db.wire.stream`) | For one page at a time, through that page's materialization |
| Transaction attempt (`db.transact`) | For the attempt, every participating read, write and delivery inside it included |

Work that INHERITS a connection takes none of its own: a read inside a
transaction and every page of a participating delivery run on the attempt's
connection. A standalone delivery instead acquires afresh for each page. A retry
also acquires afresh — and so is refused outright once the handle is closed,
rather than replaying.

**A standalone delivery holds no slot while caller code processes published
roots.** Each page returns its slot before publishing any root, so independent
work inside the consuming loop can use even a one-slot pool before the next page
is requested. A page that fails still releases its own lease, while a delivery
closed before its first advance has acquired nothing.

The statements of one standalone page run on one backend session. A later page
may use another session and observe another committed database state; Parallax
adds no delivery-wide snapshot guarantee, server cursor, or connection affinity.
A caller needing one database snapshot across all pages uses a participating
delivery inside `db.transact`, whose pages inherit the attempt's connection. A
connection lost while a page is running fails that page rather than reconnecting
and continuing.

**Handing a connection over sends nothing.** There is no validation query at
checkout, so a connection the server or network ended while it sat idle is found
by the first request an operation sends on it. When that request can be sent
again without effect — a transaction's `BEGIN` before any of your code has run,
a principal's `SET ROLE`, a read or batch of reads, or the startup probe — the
broken connection is disposed of and the same request is sent once more on
another one, taken within what remains of the operation's own
`acquire_timeout` (or of `startup_timeout`, for the probe). That stays inside
the operation's one Acquisition and Release and adds no Database Call. Nothing
else is sent again: a write, any request after the first one answered, and a
second failure each fail exactly as they would have.

If a writer endpoint's connection string points at a replica, that is where its
connections go: nothing is inferred from the string, startup adds no
physical-writer check, and writes through it fail natively. Every operation of
such a root requests the writer route, which is the only one it declares.

## Writer and reader routes

Giving the adapter a `reader=PostgresEndpoint(...)` as well as its `writer`
declares a second route with its own pool, credentials and retention. The root
still opens one runtime and closes both pools with it, and both share one
`acquire_timeout` and one `startup_timeout`.

<!-- story: routing_snippet -->

```python
def routed_configuration(
    writer_conninfo: str, reader_conninfo: str, credentials: CredentialSource | DriverManaged
) -> PostgresAdapter:
    """A writer and a reader on one adapter, which opens nothing either.

    Each endpoint carries its own retention and credentials, and each route's
    pool its own capacity: this root can hold up to thirty connections, ten on
    the writer and twenty on the reader, in every process that opens it.
    ``acquire_timeout`` is one budget per acquisition across both routes, so a
    preferred read waits on the reader for at most half of it before the
    writer gets the rest. ``reader_startup="deferrable"`` is what omitting it
    means with a reader: a reader that cannot be reached when the root opens
    leaves it opening with the reader pending, while a writer that cannot be
    reached fails it.
    """
    return PostgresAdapter(
        writer=PostgresEndpoint(writer_conninfo, credentials=credentials),
        reader=PostgresEndpoint(
            reader_conninfo, credentials=credentials, pool=PoolOptions(max_size=20)
        ),
        acquire_timeout=15.0,
        reader_startup="deferrable",
    )


@dataclass(frozen=True, slots=True)
class RoutedBalances:
    from_reader: list[Decimal]
    from_writer: list[Decimal]
    reader_or_writer: list[Decimal]


def each_scope_reads_where_its_policy_says(
    adapter: DatabaseAdapter, model: DomainModel, binding: PostgresBinding
) -> RoutedBalances:
    """Three scopes over one root, each reading where its routing says.

    With a reader configured, new reads default to ``reader_only``: served by
    the reader or failed, and possibly behind the writer. ``writer_only`` is
    how a read avoids that lag. ``reader_preferred`` reads from the reader and
    moves to the writer only before anything runs — when the reader cannot be
    reached, or loses its connection while being set up — and an operation
    that moved stays on the writer for the rest of its pages and retries. None
    of the three derivations opens anything, and writable transactions use the
    writer whatever the scope says.
    """
    with connect(adapter, model, binding=binding) as root:
        db = root.using_database_login()
        return RoutedBalances(
            from_reader=account_balances(db),
            from_writer=account_balances(db.with_routing(read_policy="writer_only")),
            reader_or_writer=account_balances(db.with_routing(read_policy="reader_preferred")),
        )
```

With a reader declared, new reads default to it: an eager read, each standalone
delivery page, and every attempt of a `read_only` transaction request
`reader_only`, while `transact` always requests the writer. Work inside a
transaction runs on that attempt's connection whatever the scope's routing says.
`with_routing(read_policy="writer_only")` sends a scope's new reads to the
writer, which is how a caller avoids replica lag; nothing fences reads behind
writes automatically. A reader endpoint promises no physical replica: an Aurora
reader endpoint reaches the writer when the cluster has no replicas. A hot
standby cannot begin a Serializable read-only transaction, so the reader route
does not declare it: a `read_only(..., isolation="serializable")` under
`reader_only` is refused before anything is acquired, and under
`reader_preferred` it requests the writer, reporting no fallback.

### Preferred reads and fallback

`reader_preferred` gives the reader at most half of `acquire_timeout` and the
writer whatever remains of the whole. It moves to the writer for two reasons
only, both before any of your code or modeled SQL runs: the reader could not be
reached (`fallback="unavailable"`), or the connection it handed over was lost
while it was still being set up — its proof, a principal's `SET ROLE`, or a
transaction's first `BEGIN` (`fallback="connection_lost"`). That loss is the
same single resend a broken connection's first request always gets, spent on
the writer instead; a request that loses its connection after something else
was already sent on it, and a read's own resend, are not fallbacks. Nothing is
replayed that would not have been, and an active transaction never moves.

Everything else ends the acquisition instead: a reader that is merely busy until
its half runs out (`timeout`), a full queue, a closed root, a refused credential
or login, a role the reader denies, a reader whose verification refused it, and
a connection whose disposal could not be confirmed. A busy reader is never
mistaken for an unreachable one: a spent half reads as unreachable only where a
connection the reader tried to open during that same wait failed to reach its
server. A retaining reader opens connections on its own threads and cannot wake
a waiting caller when one fails, so that is noticed at the half; an on-demand
reader opens them on the caller's thread, so it is noticed at once.

Once the reader is known to be unreachable and holds no idle connection, one
preferred acquisition at a time tries it again within its half — which is what
re-dials it, since nothing probes it in the background — and every other one
goes straight to the writer. The first connection it hands over clears that
knowledge and every acquisition returns to the reader. Strict `reader_only`
reads always wait on the reader for their whole budget, so they recover as soon
as it does. After a fallback, the rest of that operation stays on the writer:
every later page of a standalone delivery and every permitted retry of a
`read_only` transaction requests `writer_only`. A transaction attempt reports
the route its boundary actually opened on, so its Acquisition finishes only once
`BEGIN` has opened; its acquisition duration runs through `BEGIN` while its hold
starts when the connection was handed over.

Preferred reads hide an unavailable reader by design. The `fallback` field on
each Acquisition's diagnostics, the reader pool's own metrics and readiness, and
the `parallax.resources` notices are how an operator sees one.

### Sizing two routes

Each pool keeps its own capacity, so a root with both routes at the default
`max_size=10` can hold twenty connections, multiplied by every process that
opens one; the sum across routes and processes has to fit the server's
connection limit with room for its reserved and administrative connections. Size
each route from what it serves: the connections a route needs is roughly its
operation rate times how long each operation holds a connection, which the
Release's `hold_duration_ns` measures, and a route whose `requests_waiting` and
`requests_wait_ms` grow is short of capacity rather than slow. A deployment
relying on `reader_preferred` to ride out a reader outage moves that reader's
load onto the writer for the duration, so the writer's `max_size` and the
server's limit decide whether it can absorb it.

Readiness proves the writer first and then the reader, within what remains of
the one `startup_timeout`, and the reader must authenticate the same login as
the writer however its credentials differ — an endpoint-specific IAM token
included. A reader that cannot be reached leaves the root opening anyway with
the reader's readiness pending, unless the adapter says `reader_startup="required"`;
a refused credential, an unusable session, or another login fails the open
either way. While the reader is pending, every connection it hands over is
proved before any of your work runs on it, and the first proof that succeeds
makes the reader serve. A reader read meanwhile waits up to its
`acquire_timeout` and then fails with `reason="unavailable"`. A deferral, the
reader becoming verified, and the reader being refused are each reported once
on `parallax.resources`, and each pool sample carries its route's readiness.

The driver reports a refusal the server sent while connecting with no
SQLSTATE. Where the endpoint's login sends a password — a configured credential
source, an IAM token included — the failed connection still says it sent one,
and that is read as the server refusing it (`reason="authentication_refused"`):
a rejected password or token, an unknown login, or anything else the server
refused once the login was offered. The one exception is a database that does
not exist: where the server's message is exactly PostgreSQL's
`database "<name>" does not exist`, the reason is `"preparation_failed"`, and a
reworded or translated message stays `"authentication_refused"`. Either way the
refusal fails the open even under deferrable startup and is never a
reason to fall back. A login that sends no password carries no such sign, so a
server refusing it before any credential is exchanged — a `pg_hba.conf`
rejection, say — reaches Parallax looking exactly like an unreachable server,
as does a mistyped host. Under the default deferrable startup either one leaves
the reader pending rather than failing the open, and `reader_preferred` falls
back from it; a deployment that wants them to fail its rollout says
`reader_startup="required"`.

## Timeouts

Five controls are often confused and are genuinely distinct:

| Control | Bounds |
|---|---|
| `acquire_timeout` (the adapter's) | ONE caller's wait for a connection |
| `startup_timeout` (the adapter's) | Becoming ready before `connect` returns — the whole of it, shared across opening, waiting, probing and releasing, never restarted between them |
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
    binding: PostgresBinding,
    *,
    lifecycle_provider: ExecutionLifecycleProvider | None = None,
) -> AsyncGenerator[ScopedDatabase]:
    """The application lifespan: one handle for the process, opened and closed.

    This is what an ASGI application passes as ``lifespan=``. Everything before
    the ``yield`` runs at startup and everything after it at shutdown, once the
    server has drained the requests it accepted — a drain that is the SERVER's
    and is bounded by its own configuration, since a graceful-shutdown timeout
    cancels whatever has not finished and cancelling an ``asyncio.to_thread``
    await ends the await rather than the worker beneath it. Closing here is safe
    either way, which is Parallax's half of the bargain: an acquisition already
    admitted finishes its bounded work, and anything needing a new one is
    refused.

    Both halves are offloaded because both block. Composition opens the pool and
    proves it can execute; closing tears it down. Neither belongs on an event
    loop that is meanwhile meant to be serving.

    Build the handle HERE rather than at module import. A forking server imports
    the module once and then forks, and a pool created before the fork would
    hand the same sockets to every worker.
    """
    root = await asyncio.to_thread(
        connect, adapter, model, binding=binding, lifecycle_provider=lifecycle_provider
    )
    try:
        yield root.using_database_login()
    finally:
        await asyncio.to_thread(root.close)


async def serve_account_balances(db: ScopedDatabase) -> list[Decimal]:
    """An async endpoint's body: offload the WHOLE operation, await the values.

    The boundary matters more than the offload. What crosses it is one complete
    operation — every statement, the materialization, and the release — so the
    connection is taken and given back inside the worker thread and the event
    loop is never holding one. Handing back a stream to be iterated there would
    instead run each blocking page acquisition and read on the loop, even though
    a standalone stream returns the lease before publishing that page's roots.

    Pool capacity is not HTTP concurrency for the same reason: each database
    phase occupies a worker thread and a connection together, so that phase's
    concurrency is the smaller capacity of the two.
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
Parallax's own part of the bargain: an acquisition already admitted finishes its
bounded work, while anything needing a new connection is refused from the close
onward.

**Offload complete operations.** From an async endpoint, what crosses into the
worker thread must be the WHOLE operation — statements, materialization, and the
release. Handing a stream back to be iterated on the event loop moves each
blocking page acquisition and read onto the loop, although a standalone stream
holds no connection between pages. Synchronous endpoints need none of this: the
server already runs them off the loop.

Parallax adds no async interface, so no Parallax call ever awaits while holding a
connection. A standalone stream takes and returns one lease inside each blocking
page read; awaiting between published roots holds no pool slot. The delivery is
still the shape to watch because asking for its next page on the event loop blocks
that loop, which is what offloading complete operations prevents.

**Pool capacity is not HTTP concurrency.** A database phase occupies a worker
thread and a connection together, so the number that can run at once is the
smaller of the two, and raising `max_size` past the threadpool buys nothing.
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

The runtime publishes read-only measurements, one source per pool, each naming
the route its pool serves. A `lifecycle_provider` that also implements
`observe_pool` is offered each source once at composition; what it answers with
is closed when the handle closes.

```python
from parallax.core import (
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    PoolAvailable,
    PoolDetached,
    PoolMetricsSource,
    PoolSample,
    PoolUnavailable,
    RootExecution,
)
```

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
    adapter: DatabaseAdapter, model: DomainModel, binding: PostgresBinding
) -> PoolReading:
    """Watch one runtime's pool from composition to close.

    The Provider is offered the source once, before ``connect`` returns, and the
    registration it answers with lives exactly as long as the handle. Sampling
    runs no statement and takes no connection. The reading below is taken after
    one root is published, when that page's lease has returned and before the
    next page asks for one.
    """
    provider = PoolWatchingProvider()
    with connect(adapter, model, binding=binding, lifecycle_provider=provider) as root:
        db = root.using_database_login()
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
| `PoolAvailable(measurements, readiness)` | This is the reading, and whether its route has proved it can serve: `verified`, `pending`, or `refused` |
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
| `requests_num` | Checkout CALLS, startup's own included. A connection replaced at its first use costs one more — it is not a count of operations |
| `requests_queued`, `requests_wait_ms` | Queue entries, and the milliseconds those queued waits took — not whole acquisition time |
| `requests_errors` | Checkout calls the pool reported an error for. Not every acquisition failure |
| `connections_num`, `connections_ms` | Connection attempts, and the time successful attempts took to ESTABLISH — excluding the initialization after |
| `connections_errors` | Failed attempts, excluding a configure-callback refusal |
| `connections_lost` | Connections the pool's own checks found broken. This runtime asks the pool for no checkout check, so a connection that broke while idle is not counted here |
| `returns_bad` | Connections handed back unusable: every one Parallax disposed of, a connection found broken at its first use included — not only network failures |

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
an error. Read it against `connections_errors` and `returns_bad`: errors
climbing with it is establishment failing, and `returns_bad` climbing with it is
connections handed back unusable — a connection found broken at its first use,
or any other Parallax invalidation. No counter, alone or summed with others, is
a total of network failures or of connections successfully replaced: a quiet
`connections_lost` says nothing about how many connections broke. Quiet
counters do not narrow the climb either. They rule those two causes out and
leave the ones no counter records and a reading cannot
tell apart — a connection refused in preparation, a healthy connection retired
at `max_lifetime`, and, on an on-demand pool, the connection every acquisition
creates and closes. A climb beside quiet counters is a question for the logs,
not a fault.

## Session settings

### Driver build

The adapter decodes `real` and `timestamptz` cells with compiled loaders that
psycopg's C row decoding calls directly. They run under psycopg's `binary`
build, which the adapter installs, or under its `c` build, compiled against a
system `libpq`. Under psycopg's pure-Python implementation — selected, for
example, with `PSYCOPG_IMPL=python` — importing `parallax.postgres` raises
`ImportError` naming that implementation, before any connection exists. There
is no slower fallback to run instead.

Install the supported C implementation against your system libpq with a C compiler,
Python development headers, and `pg_config` on `PATH`:

```bash
python -m pip install --no-binary psycopg-c "psycopg[c]" parallax-postgres==0.1.0 parallax-snapshot==0.1.0
```

Set `PSYCOPG_IMPL=c` in the application's environment before Python starts. The
adapter's binary dependency remains installed, but psycopg selects the C build
explicitly. Its version must satisfy the adapter's
[driver requirement](../packages/parallax-postgres/pyproject.toml). Without an
explicit selection, the presence of a C build can affect psycopg's implementation
selection; set `PSYCOPG_IMPL=binary` when that is the intended deployment.

For a Parallax source installation, select its sdist explicitly:

```bash
python -m pip install --no-binary parallax-postgres parallax-postgres==0.1.0 parallax-snapshot==0.1.0
```

The adapter sdist carries its Cython sources and requires a C compiler and the
Cython build dependency declared in its metadata. Normal build isolation installs
that dependency. Both compiled loader variants must be present at runtime;
startup refuses a missing or unloadable selected variant. Source publication does
not extend the supported platform set.

### Execution authority and session affinity

Each runtime authenticates every physical connection as the login named by its
connection string and captures that exact `session_user` during readiness. A
login-bound execution source adds no role command. A source bound to a
`PostgresRole` replaces the session's effective privileges with a safely quoted
session-level `SET ROLE` before modeled execution and, when the session remains
reusable, performs exactly one `RESET ROLE` before returning it. This is
replacement and containment, not additive privilege elevation: the login must
be allowed to assume the role, and work under that role receives only privileges
PostgreSQL resolves for that role.

`RESET ROLE` restores the connection's configured startup default. A failed role
installation, an unsafe session, or failed restoration disposes the physical
connection instead of repairing it into reuse. In the normal reusable case the
principal envelope therefore costs two provider commands, in addition to the
modeled work itself.

This contract requires end-to-end session affinity. Transaction-pooling and
statement-pooling proxies are unsupported because `SET ROLE`, modeled work, and
`RESET ROLE` could reach different server sessions. Parallax performs no runtime
proxy detection: deployment topology is an operator-owned prerequisite, and a
proxy that happens to accept the commands is not evidence that it preserves the
required affinity.

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
not restore caller settings it did not change. Scoped principal execution is the
one deliberate session mutation and is restored as described above.

A third setting is load-bearing: `extra_float_digits` must stay above zero, as
PostgreSQL's default of 1 is. At zero or below the server rounds every float it
sends, which no decoding can undo. A connection does not report the setting, so
it is checked once, by the startup probe, which reads a Float32 and a Float64
back and refuses startup with `DatabaseStartupError` (`phase="probe"`) naming
`extra_float_digits` when either comes back inexact. The probe sees what every
connection is configured with — the connection string, a service file, the
login's or the server's default — and not a later `SET` on some connections.

`prepare_threshold` is the driver's server-side auto-preparation after that many
identical executions, defaulting to 5. Pass `None` where the same connection may
see a table's shape change underneath identical query text — a
schema-reset-per-case harness, never a deployed application.

## Temporal constraints

A temporal table that `schema_delta` creates carries its constraints inline:

- its primary key, named `pxc_pk_<table>_<fingerprint>`, over the same columns as
  before: the key plus each axis's end column;
- one check per axis, `pxc_tx_<table>_<fingerprint>` requiring `in_z < out_z` on every
  temporal table, and `pxc_valid_<table>_<fingerprint>` requiring `from_z < thru_z` too
  on a Bitemporal one;
- an exclusion, `pxc_excl_<table>_<fingerprint>`, which refuses a row overlapping
  another row of the same key in Transaction Time and, on a Bitemporal table, in Valid
  Time as well. Intervals are half-open, so rows that only meet don't overlap. A shared
  table-per-hierarchy table compares keys whatever the row's subtype; a
  table-per-concrete-subtype table compares only its own rows.

PostgreSQL then refuses an empty or inverted interval, and overlapping history, from
any writer, Parallax or not, with a `DatabaseError` whose `category` is
`"constraintViolation"`: `native_code` `23514` and the check's name for an interval,
`23P01` and the exclusion's name for an overlap. The exclusion is checked as each
statement runs, not at commit, and a statement that conflicts with a row another
transaction hasn't committed yet waits for that transaction first. The fingerprint is
derived from the table and its columns, so the names change only when those do; take
them from the `create table` statement that provisioning the same model from `ABSENT`
returns.

### The `btree_gist` prerequisite

The exclusion compares the key with `=` inside a GiST index, which needs the
`btree_gist` extension that ships with PostgreSQL. A delta that creates a temporal table
begins with `create extension if not exists btree_gist`, the one statement a delta runs
only if needed. The extension is trusted, so a role with the `CREATE` privilege on the
database can install it without being a superuser; managed services such as Amazon RDS,
Google Cloud SQL and Azure Database for PostgreSQL offer it, though some require it to be
allow-listed first. A delta never upgrades or removes it. A schema reset that drops
`public` with `cascade` also drops an extension installed there, and the next delta that
creates a temporal table installs it again.

### Cost

Every row a temporal table stores is an entry in the exclusion's GiST index, which an
insert, a close, and a revision that moves a row's Valid-Time start all maintain. A
close already changed an indexed column, the key's `out_z`; a revision moving `from_z`
now does too, so neither is a HOT update. A write that changes only a payload column
keeps the update HOT where the page has room. Measure the write rate your tables need
before relying on these costs.

### Adopting the constraints on an existing table

A table that already existed gets none of the constraints from a later delta, because a
delta can't know whether the stored rows satisfy them. Migrate it yourself, in this
order; nothing in Parallax guesses the names your table carries now. For a Bitemporal
`position` table, first find the rows each check would refuse and every pair of rows
that overlaps:

```sql
select pos_id, in_z, out_z from position where not (in_z < out_z);
select pos_id, from_z, thru_z from position where not (from_z < thru_z);
select a.pos_id, a.ctid, b.ctid
from position a join position b
  on a.pos_id = b.pos_id and a.ctid < b.ctid
 and tstzrange(a.in_z, a.out_z) && tstzrange(b.in_z, b.out_z)
 and tstzrange(a.from_z, a.thru_z) && tstzrange(b.from_z, b.thru_z);
```

On a Transaction-Time-only table leave out the `from_z` and `thru_z` conditions.
Correct or remove each row they find; which is right is a decision about your history,
not one Parallax can make. Commit the corrections, note the time with
`select clock_timestamp()`, and wait until no transaction older than that is still open:

```sql
select pid, xact_start, state from pg_stat_activity
where datname = current_database() and pid <> pg_backend_pid()
  and backend_xmin is not null and xact_start < '...';  -- the time you noted
```

Until then, the exclusion's index build still reads the version of each row from
before your corrections, because an older transaction might see it, and fails with
`22000` on an inverted one although the queries above find nothing. Then rename the
primary key, which PostgreSQL named
`position_pkey` when an earlier development checkout created the table, add the
checks, install the prerequisite, and add the exclusion:

```sql
alter table position rename constraint position_pkey to pxc_pk_position_6033a9b256fa65fb6a06ae764dd7905d;
alter table position add constraint pxc_tx_position_05e7b5d0b3866810c782a91a8d1f7971 check (in_z < out_z);
alter table position add constraint pxc_valid_position_9c4697753a4cc41ed976ab6ee1f1f88b check (from_z < thru_z);
create extension if not exists btree_gist;
alter table position add constraint pxc_excl_position_e5c6616a7f7cfbf6c981cf0ad0f86610
  exclude using gist (pos_id with =, tstzrange(from_z, thru_z) with &&, tstzrange(in_z, out_z) with &&);
```

The checks come first: an exclusion can't even form the range of an inverted
interval, and fails with `22000` on one. Adding a check or the exclusion validates every
stored row while it holds an `ACCESS EXCLUSIVE` lock, which blocks reads and writes of
the table. A check can be added `NOT VALID` instead, which takes that lock only briefly
and checks new writes from then on, and its stored rows validated afterwards under a
`SHARE UPDATE EXCLUSIVE` lock, which lets reads and writes continue:

```sql
alter table position add constraint pxc_tx_position_05e7b5d0b3866810c782a91a8d1f7971 check (in_z < out_z) not valid;
alter table position validate constraint pxc_tx_position_05e7b5d0b3866810c782a91a8d1f7971;
```

`validate constraint` fails while any stored row breaks the check, and leaves it
`NOT VALID`; correct the row and validate again. An exclusion has no such option:
PostgreSQL refuses `NOT VALID` on one, so adding it scans and indexes every row under
`ACCESS EXCLUSIVE`. Plan that lock's duration on a large table, and add the exclusion
only after the queries above find nothing, or it fails with `23P01` and adds nothing.

## Authored indices on temporal tables

Every index you declare on a temporal Entity, unique or not, is created over its
declared columns followed by the table's axis ends: `out_z` on a
Transaction-Time-only table, `thru_z, out_z` on a Bitemporal one. A unique
`code` index on a Transaction-Time-only `handle` table is therefore
`unique (code, out_z)`, so an amend that keeps `code` can close the current row
and insert its successor. What each shape does and does not guarantee is
`core/spec/m-descriptor.md`'s, under *`index`*.

### Adopting the indices on an existing table

A development checkout before this rule created those indices over the declared
columns alone,
under names derived from those columns. A later delta changes neither: both model
editions it compares are compiled under the current rule, so equal editions give
an empty delta, and it never reads the catalog. Until you migrate, an amend that
keeps a unique index's value fails with `uniqueViolation` on that index, and a
non-unique index keeps working but a Latest lookup matches only its declared
columns. Migrate each such index yourself; nothing in Parallax guesses the names
your table carries now.

Take the target name from a fresh provisioning of the same model. The
`created_indices` of the delta from `ABSENT` lists every authored index it
creates, with its `physical_index_name`, `physical_table`,
`logical_index_identity`, and `unique` flag, and its statements give the columns:

```python
from parallax.core import POSTGRES
from parallax.evolution import ABSENT, evolve, schema_delta
```

```text
rollout = schema_delta(evolve(ABSENT, model), POSTGRES)
rollout.created_indices    # the target names
rollout.statements         # the target columns
```

Then find the index the table holds now, which carries the declared columns
without the axis ends:

```sql
select indexname, indexdef from pg_indexes
where tablename = 'handle' and left(indexname, 4) = 'pxi_' order by indexname;
```

Create the target first, then drop the held index:

```sql
create unique index <target_name> on handle (code, out_z);
drop index <held_name>;
```

On a Bitemporal table the columns are `(code, thru_z, out_z)`; for a non-unique
index leave out `unique`. A table-per-concrete-subtype family holds the index on
every concrete table carrying its columns, each under its own name, so repeat the
pair on each. Creating first keeps the old index enforcing until its replacement
exists. Every stored row that satisfies `unique (code)` also satisfies
`unique (code, out_z)`, so the replacement cannot fail on existing data and there
is nothing to check first.

`create index` builds the index while holding a `SHARE` lock, which lets reads
continue and blocks every write to the table until the build finishes; plan for
its duration on a large table. `drop index` takes an `ACCESS EXCLUSIVE` lock,
which blocks reads and writes as well, but only for as long as the drop takes;
it waits for queries already using the table, and queries arriving meanwhile
queue behind it.
Run as one transaction, the pair either completes or leaves the old index in
place, and holds both locks until it commits. `create index concurrently` and
`drop index concurrently` avoid blocking writes, but cannot run inside a
transaction block and take longer, and a concurrent build that fails leaves an
invalid index you must drop before trying again.

This adopts the indices of a table that is already temporal and stays so. Giving
an Entity a temporal profile or removing one is a coordinated model change with a
migration of its own, and no delta is generated for it.

## What gets logged, and by whom

Three reporting paths with three different disclosure policies. They are not
interchangeable and only one of them is yours to redact.

| Path | Carries | Policy |
|---|---|---|
| Lifecycle events (a Handler you installed) | Rich detached diagnostics: bounded message and stack, error type and code, the cleanup a release established | **Yours.** You decide what is exported and what is redacted. Detaching and truncating a native message does not sanitize it |
| `parallax.resources` (standard `logging`) | One fixed sentence per occasion, and — where a cleanup is what failed — the cleanup phase, the cleanup code, and the one fixed sentence that code stands for. Nothing else. No credential, SQL, bind, native message, stack, structured extra, or `exc_info`. A pool observation that would not close is the one record carrying no phase and no code, because no connection release occurred | Parallax's, and deliberately thin: it must be safe to leave on in a deployment that has redacted nothing. It speaks when something went wrong AND no Handler received it, and when a reader route's readiness is deferred, verified, or refused |
| `psycopg.pool` (the driver's own logger) | Whatever the driver logs, exception text included | **The driver's.** Parallax's restriction does not reach it. Configure it yourself |

`parallax.resources` is a fixed logger name so an operator silences or routes
resource reporting by naming one logger. It is a floor rather than a second
export path: a cleanup problem reaches exactly one of a Handler and this log,
never both and never neither.

## Migrating from a development checkout

| Before | Now |
|---|---|
| `PostgresAdapter(open_psycopg_connection)` | `PostgresAdapter(writer=PostgresEndpoint(connection_string, credentials=...))` — configuration, not a live connection |
| `PostgresAdapter.connect(conninfo, ...)` | `PostgresAdapter(writer=PostgresEndpoint(conninfo, credentials=...), prepare_threshold=...)`, opened by `connect` |
| `PostgresAdapter("postgresql://app:<password>@host/app")` | `PostgresEndpoint("postgresql://app@host/app", credentials=Password("<password>"))` — a password in the string is refused |
| `PostgresAdapter(conninfo, credentials=..., pool=PoolOptions(acquire_timeout=..., startup_timeout=...))` | `PostgresAdapter(writer=PostgresEndpoint(conninfo, credentials=..., pool=PoolOptions(...)), acquire_timeout=..., startup_timeout=...)` — the budgets are the runtime's, not a pool's |
| `rds_postgres(host=..., ..., pool=...)` | `PostgresAdapter(writer=rds_endpoint(host=..., ..., pool=...))` |
| `adapter.connection` (raw psycopg connection) | removed; open your own connection for DDL, migrations, and fixtures |
| `adapter.close()` | `db.close()`, or leaving the handle's `with` block |
| `DbPort` | `DatabaseConnection` |
| `from parallax.core.execution_lifecycle import FailureDiagnostic` | no import: the lifecycle events that carry a `FailureDiagnostic` hand it to your Handler |

Earlier development checkouts held one connection forever and released nothing.
The current handle owns a runtime and must be closed. Nothing else about a read, a stream, or a
transaction changes: the same verbs, the same results, and the same transaction
outcomes.

The two removals with the widest blast radius are the raw accessor and the
implicit lifetime. DDL, migrations, fixture loading, and any statement you author
verbatim now run on a connection you opened yourself — Parallax hands out no raw
pooled session and no escape hatch to one. And a handle built and forgotten used
to leak one connection; it now holds a pool and maintenance threads, so a process
that composes handles per request will exhaust the server rather than merely
waste one socket.
