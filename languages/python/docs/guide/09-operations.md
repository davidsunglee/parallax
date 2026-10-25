# Operations

Running Parallax in production comes down to one object per process: the `Database`
root that `connect` returns. It owns the connection pool, the cached read plans and the
observer that sees every operation, and closing it gives them all back. This chapter
shows where each of those is set, and points to the
[PostgreSQL lifecycle guide](../postgresql-lifecycle.md), which covers running Parallax
against PostgreSQL in depth. Its example uses these imports:

<!-- example: operations-imports -->
```python
import logging

from parallax.core import DomainModel
from parallax.core.db_port import CredentialSource
from parallax.core.execution_lifecycle import LoggingLifecycleProvider
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresAdapter, PostgresRole
from parallax.snapshot import Database, connect
```
<!-- /example -->

## Open one root per process

Configure the adapter once, open the root once the process is ready to serve, and close
it on shutdown. This function opens the shop's root:

<!-- example: open-one-root-per-process -->
```python
def open_the_shop_database(
    conninfo: str, credentials: CredentialSource, model: DomainModel
) -> Database[PostgresRole]:
    """The process's one root: a bounded pool, room for more read plans, and logging."""
    adapter = PostgresAdapter(conninfo, credentials=credentials, pool=PoolOptions(max_size=20))
    return connect(
        adapter,
        model,
        read_plan_cache_capacity=64,
        lifecycle_provider=LoggingLifecycleProvider(logging.getLogger("shop.database")),
    )
```
<!-- /example -->

`PostgresAdapter` is configuration: building one opens nothing, so it is safe at import
time. `connect` opens the runtime, and the root it returns is what you share across the
process and close at the end. Each setting here has a section of its own:

- **The pool.** `PoolOptions` bounds how many connections the root keeps and opens,
  and how long a caller waits for one. `OnDemandOptions` keeps none between operations.
  See the lifecycle guide on
  [what you build](../postgresql-lifecycle.md#what-you-build-and-what-owns-it),
  [retention](../postgresql-lifecycle.md#retention) and
  [what each operation holds](../postgresql-lifecycle.md#what-each-operation-holds).
- **Credentials.** The `credentials` the adapter takes are resolved each time a
  connection is made, so a rotated secret or a short-lived token reaches every new
  connection. See [Execution authority](06-execution-authority.md#credentials) and the
  lifecycle guide on [where the password lives](../postgresql-lifecycle.md#where-the-password-lives).
- **Read plans.** Planning a query, from its predicate and includes to the SQL for each
  level, is work a root keeps and reuses. `read_plan_cache_capacity` sets how many plans
  it keeps, 16 by default; raise it when a service runs more distinct queries than that,
  or pass 0 to plan every read afresh. The
  [Python execution binding](../../spec/execution.md#models-roots-and-scopes) defines
  what makes two reads share a plan.
- **Observation.** A `lifecycle_provider` sees every read, transaction, attempt and
  statement the root runs. `LoggingLifecycleProvider` writes them to a logger you
  configure: each root operation's summary at `INFO`, or `ERROR` when it fails, a
  rollback before a retry at `WARNING`, and the steps inside it at `DEBUG`. A provider of your own can export metrics or traces, and
  can also watch the pool. See the lifecycle guide on
  [observing the pool](../postgresql-lifecycle.md#observing-the-pool) and
  [what gets logged, and by whom](../postgresql-lifecycle.md#what-gets-logged-and-by-whom).

## Before you deploy

The lifecycle guide also covers the decisions a deployment makes once:

- [Timeouts](../postgresql-lifecycle.md#timeouts): which of the five controls bounds
  what, and why none of them is a retry budget.
- [Process and application lifetime](../postgresql-lifecycle.md#process-and-application-lifetime):
  building the root after a forking server forks, and closing it on shutdown.
- [Session settings](../postgresql-lifecycle.md#session-settings): the driver build, and
  how a subject scope's role is set on and cleared from each connection.

[Model evolution](07-model-evolution.md) covers rolling a new model out to running
processes, and [Errors](08-errors.md) covers what reaches your code when the database
or the pool fails.

## How it works →

- The [PostgreSQL lifecycle guide](../postgresql-lifecycle.md) is the operational
  reference for connections, pooling, credentials, timeouts and observation.
- The [database port](../../../../core/spec/m-db-port.md) defines configuration,
  acquisition, release and what a pool publishes, and
  [execution lifecycle](../../../../core/spec/m-execution-lifecycle.md) defines the
  events a lifecycle provider receives.
- [Execution](../../../../core/spec/m-execution.md#database-root) defines the Database
  Root and what it owns, and the
  [Python execution binding](../../spec/execution.md#models-roots-and-scopes) records
  `connect`, its options and read-plan reuse.
