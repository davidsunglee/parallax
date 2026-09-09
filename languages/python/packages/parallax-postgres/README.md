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
starting point chosen to be safe rather than fast, and no benchmark claims them
optimal — tune from measured occupancy and queue latency.

Five controls are often confused and are genuinely distinct: `acquire_timeout`
bounds ONE caller's wait for a connection; `startup_timeout` bounds becoming
ready before `connect` returns; `reconnect_timeout` is how long the runtime's own
background retrying keeps trying to restore capacity; statement execution and
transaction duration are the database's and the application's. None of them is a
retry budget for an operation.

One driver behavior is worth knowing before tuning on-demand retention: the
driver derives its own connection-establishment timeout from whatever remains of
the acquisition budget, overriding a `connect_timeout` the connection string
carries for that creation. `acquire_timeout` is the control that matters there,
and the two do not compose as independent limits.

## Session settings

The connection string is libpq's own grammar — keyword/value pairs, a
`postgresql://` URI, a `service=` reference, or the empty string, which asks
libpq to take everything from the environment. It is stored exactly as given,
kept out of this value's representation, and resolved against the environment,
service files and server defaults when each physical connection is created, so
immutable configuration does not freeze inputs a deployment expects to change.

Two effective settings are load-bearing and refused when they are wrong, before
any modeled statement runs: the client encoding must be UTF-8 and `DateStyle`
must be ISO (any field order within ISO). Everything else a string, an
environment, a service file or a server default establishes is preserved — the
time zone, a stronger default isolation, a read-only session, a search path,
statement and lock timeouts.

`prepare_threshold` is the driver's server-side auto-preparation after that many
identical executions, defaulting to 5. Pass `None` where the same connection may
see a table's shape change underneath identical query text — a
schema-reset-per-case harness, never a deployed application.

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
