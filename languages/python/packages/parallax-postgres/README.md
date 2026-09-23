# parallax-postgres

Parallax's Postgres database adapter: the sole declarer of `psycopg` and its
companion `psycopg-pool`. See `languages/python/spec/python.md`.

## Connecting

```python
from parallax.core.db_port import Password
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresAdapter
from parallax.snapshot import connect

adapter = PostgresAdapter("postgresql://app@localhost/app", credentials=Password("s3cret"))
with connect(adapter, model) as root:
    db = root.using_database_login()
    ...
```

`PostgresAdapter` is **configuration**. Constructing one opens no connection, no
pool, and no thread: it parses the connection string, validates the credential
declaration and the retention policy, and stores them. That is what makes it
safe to build at import time, hold as a module constant, share between threads,
and — for a forking server — build before the fork and open after it.

## Where the password lives

The connection string says **where**, and `credentials` says **how**. A string
carrying a password is refused at construction, whatever `credentials` is, and
the refusal never quotes the string back:

```text
PostgresAdapter("postgresql://app:<password>@db.internal/app", credentials=Password("<password>"))
ValueError: connection_string must not carry a password; supply it through credentials.
```

There are three spellings, all exported from `parallax.core.db_port`:

```python
from parallax.core.db_port import DRIVER_MANAGED, Password

# a constant secret; `Password` is its own source and keeps it out of every repr
PostgresAdapter("postgresql://app@db.internal:5432/app", credentials=Password("s3cret"))

# any object with `resolve() -> Password`, asked as connections are established
PostgresAdapter("postgresql://app@db.internal/app", credentials=my_source)

# Parallax supplies none: peer, trust, a client certificate, Kerberos, or
# libpq's own PGPASSWORD, .pgpass and service files
PostgresAdapter("host=/var/run/postgresql dbname=app", credentials=DRIVER_MANAGED)
```

A source is asked where the driver establishes a **physical** connection, and
never when an acquisition reuses a retained one, which is what lets a
short-lived cloud token authenticate a pool that outlives it. It may block on a
network and must bound its own I/O. Parallax cannot see a password reachable
through a `service` file or `PGPASSWORD`, so neither is refused above; under an
explicit source the resolved password wins over both, by libpq's own
precedence.

`connect` is what opens a runtime, and the Database Root it returns is what owns
that runtime. Modeled work requires an explicitly selected `ScopedDatabase`, as
shown above. **Close the root**: `root.close()` and the context manager above are
equivalent, and both are idempotent. Every `connect` over one configuration
opens an independent runtime, so closing one root leaves another working.

Each operation acquires a connection and gives it back — an eager read for its
whole execution, each standalone stream page through its materialization, and a
transaction attempt for the attempt. A standalone page gives the connection back
before publishing roots, so caller work between pages can use even a one-slot
pool. A participating stream instead inherits its transaction attempt's
connection for every page.

`pool=PoolOptions(...)` keeps connections between operations;
`pool=OnDemandOptions(...)` keeps none, closing each on release unless a caller
is already waiting for one. Omitting `pool` takes the retaining defaults.

## Everything else

[PostgreSQL connection lifecycle](https://github.com/davidsunglee/parallax/blob/main/languages/python/docs/postgresql-lifecycle.md)
is this adapter's operational guide, and the one place these facts are written
down:

- the full retention settings and their defaults, and what the driver's own
  maintenance settings mean;
- what each operation holds, standalone per-page leases, and participating
  connection affinity;
- the five distinct timeouts, and the one driver precedence that surprises
  people;
- process and application-server lifetime — post-fork construction, the ASGI
  lifespan, offloading complete operations, and why pool capacity is not HTTP
  concurrency;
- connection budgeting across workers, replicas and runtimes;
- observing the pool, and what its measurements do and do not mean;
- which session settings are required, which are preserved;
- how fixed login identity, scoped role replacement/restoration, and required
  session affinity behave, including unsupported transaction/statement pooling
  proxies and the absence of runtime proxy detection;
- the three logging paths and their different disclosure policies;
- migrating from the pre-pooling surface.

Every application-shaped Python block in it is the source of an executable story
that runs against a real PostgreSQL server, so nothing there is a snippet that
has never executed.
