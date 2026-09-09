# parallax-postgres

Parallax's Postgres database adapter: the sole declarer of `psycopg` and its
companion `psycopg-pool`. See `languages/python/spec/python.md`.

## Connecting

```python
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresAdapter
from parallax.snapshot import connect

with connect(PostgresAdapter("postgresql://localhost/app"), model) as db:
    ...
```

`PostgresAdapter` is **configuration**. Constructing one opens no connection, no
pool, and no thread: it parses the connection string, validates the retention
policy, and stores both. That is what makes it safe to build at import time,
hold as a module constant, share between threads, and — for a forking server —
build before the fork and open after it.

`connect` is what opens a runtime, and the handle it returns is what owns that
runtime. **Close it**: `db.close()` and the context manager above are
equivalent, and both are idempotent. Every `connect` over one configuration
opens an independent runtime, so closing one handle leaves another working.

Each operation acquires a connection and gives it back — an eager read for its
whole execution, a stream from its first page to its exhaustion or failure, a
transaction attempt for the attempt. Capacity a stream is holding is capacity
other work waits for: an independent `db.transact(...)` inside a streaming loop
needs another connection and will time out where the stream occupies them all.

`pool=PoolOptions(...)` keeps connections between operations;
`pool=OnDemandOptions(...)` keeps none, closing each on release unless a caller
is already waiting for one. Omitting `pool` takes the retaining defaults.

## Everything else

[PostgreSQL connection lifecycle](https://github.com/davidsunglee/parallax/blob/main/languages/python/docs/postgresql-lifecycle.md)
is this adapter's operational guide, and the one place these facts are written
down:

- the full retention settings and their defaults, and what the driver's own
  maintenance settings mean;
- what each operation holds, held stream slots, and connection affinity;
- the five distinct timeouts, and the one driver precedence that surprises
  people;
- process and application-server lifetime — post-fork construction, the ASGI
  lifespan, offloading complete operations, and why pool capacity is not HTTP
  concurrency;
- connection budgeting across workers, replicas and runtimes;
- observing the pool, and what its measurements do and do not mean;
- which session settings are required, which are preserved;
- the three logging paths and their different disclosure policies;
- migrating from the pre-pooling surface.

Every application-shaped Python block in it is the source of an executable story
that runs against a real PostgreSQL server, so nothing there is a snippet that
has never executed.
