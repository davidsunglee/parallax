# Parallax

Parallax is an object-relational mapper for applications that need rich domain
models, explicit transactions, and a reliable history of how their data changes.
It combines typed queries and immutable object graphs with batched writes,
optimistic concurrency, and first-class temporal data.

The current implementation is **Python with PostgreSQL**. You declare
Pydantic-based entity classes, query through their attributes and relationships,
and receive frozen instances of your own types. Reads return complete snapshots
of the requested object graph; accessing a relationship never silently triggers
another database query.

Start with the [Python Usage Guide](languages/python/docs/usage-guide.md) for
executable examples, or the
[PostgreSQL lifecycle guide](languages/python/docs/postgresql-lifecycle.md) for
connection and application setup.

## Model Your Domain

Use entity classes to describe scalar attributes, primary keys, and to-one or
to-many relationships. Nested, immutable value objects let you model structured
data without turning every component into a separate entity. They can be stored
in JSON-backed columns and queried through their declared fields.

Parallax also supports generated primary keys, read-only entities, document
storage, and closed inheritance families. Inheritance can use a shared table or
a table per concrete subtype, while queries can narrow a family to particular
subtypes and their attributes.

## Query Objects and Relationships

Build typed expressions from your entity classes: compose filters, test whether
related objects exist, order and limit results, and explicitly include the
relationships you want to load. Query construction itself performs no I/O.

For example, with application entities already declared:

```python
# Orders with at least one qualifying item.
query = Order.where(Order.items.exists(OrderItem.quantity >= 4))

# A bounded, ordered result.
query = Order.where(Order.active.is_(True)).order_by(Order.qty.desc()).limit(20)
```

Included relationships are fetched eagerly. Shared objects and cycles preserve
identity within the returned graph, and unloaded relationships are explicit
rather than lazy database calls. The `Snapshot[T]` result envelope provides
accessors for exactly one, optional one, or multiple roots. Context-managed
streams support paged delivery when you do not want to materialize the entire
result at once.

Applications that need a data-oriented boundary can use the Wire API with
canonical query documents and immutable mapping results. Typed and Wire access
share the same execution semantics; an existing typed snapshot can also be
projected to Wire data without another database call.

## Treat History as Part of the Model

Parallax supports both transaction-time audit histories and full bitemporal
models:

- **Transaction time** records when a fact was stored in the database, letting
  you ask what the system knew at a past instant.
- **Valid time** records when a fact applies in the domain, letting you model
  effective dates independently of when a change was recorded.

Read the latest state, query as of a particular instant, or inspect histories
and time ranges. Temporal coordinates carry through the requested object graph
so related data is read at the same temporal perspective.

```python
from datetime import UTC, datetime

query = Balance.where(Balance.all).as_of(
    tx_time=datetime(2024, 4, 1, tzinfo=UTC)
)
```

Temporal writes preserve history rather than overwriting it. Bitemporal
operations support effective-dated changes and bounded corrections: change a
value for a particular interval while preserving the portions before and after
it. The [usage guide's temporal example](languages/python/docs/usage-guide.md#bitemporal-update-until-splits-headmiddletail)
shows an update restricted to a date range.

## Make Changes Through Explicit Transactions

Returned objects are immutable. Insert new values, use `edit(...)` and an
explicit update to persist changes, or delete an entity through the transaction.
Writes are explicit rather than inferred from mutation of a live object graph.

Transactions buffer changes in a unit of work, coalesce or cancel compatible
operations, batch database writes, and order them around dependencies. Reads
inside the transaction flush pending work when needed to observe your own
changes. Set-based operations support changes selected by a query as well as
changes to individually loaded entities.

Concurrency controls include optimistic conflict detection, locking reads, and
configurable isolation. Transactions run through callbacks so retryable failures
can replay the transaction body within a configured bound. Nested calls join an
eligible active transaction; a failed joined body cannot be caught and then
accidentally committed by its caller.

## Integrate with Your Application

The PostgreSQL adapter uses psycopg and supports pooled and on-demand connection
retention. A `Database` root owns its runtime; explicit scopes select execution
authority and transaction options. Credential sources can refresh credentials
when establishing connections, and the optional AWS integration supplies RDS IAM
authentication.

Lifecycle observation hooks expose execution activity without attaching a log
to every returned object. Read-plan reuse avoids rebuilding eligible plans,
while explicit connection and stream lifetimes make resource ownership visible
to the application.

See the [PostgreSQL lifecycle guide](languages/python/docs/postgresql-lifecycle.md)
for deployment choices, connection budgeting, timeouts, and pool observation.
The [Python binding](languages/python/spec/python.md) records the precise
Python-specific contracts behind the API.

## Developing Parallax

The implementation lives in [`languages/python/`](languages/python/).
[`TESTING.md`](TESTING.md) explains verification;
[`languages/python/TESTING.md`](languages/python/TESTING.md) covers Python test
placement and fixtures. Run the repository merge gate from the root:

```bash
just check
```

Database-backed checks require Docker. `just --list` lists the available
commands; use the testing map for focused iteration.

For a Docker runtime that exposes its socket through a CLI context rather than
the default socket, inspect the endpoint:

```bash
docker context inspect --format '{{ .Endpoints.docker.Host }}'
```

Set that endpoint as `docker.host` in your per-machine, untracked
`~/.testcontainers.properties`, for example
`docker.host=unix:///Users/you/.orbstack/run/docker.sock`.

## A Shared Specification, Tested Against Real Databases

Behind the ORM is a language-neutral behavioral specification and an executable
compatibility corpus. They make the difficult parts—temporal corrections,
transaction boundaries, SQL generation, and object materialization—explicit and
testable. Parallax is informed by the bitemporal ORM
[Reladomo](https://github.com/goldmansachs/reladomo); adopted semantics are
expressed independently of Java or any other host language.

The Python implementation proves the
[`slice-snapshot-1`](core/spec/slices.md#snapshot-conformance-slice) capability
set against PostgreSQL. Shared cases check emitted SQL, returned graphs, final
table state, errors, and concurrency observations. A separate API suite drives
the idiomatic Python interface and generates the usage guide from selected
executable examples. The reference harness validates the corpus against real
databases; it is not the ORM implementation.

This foundation also allows other language implementations to offer their own
idiomatic APIs while sharing behavioral contracts. It does not imply that every
language or database described by the core has a shipped ORM adapter.

For contributors exploring that foundation:

- [Core overview](core/spec/00-overview.md), [module catalog](core/spec/modules.md),
  and [slice catalog](core/spec/slices.md) describe the behavior and capability
  boundaries.
- [Schemas](core/schemas/) and [compatibility cases](core/compatibility/) hold
  serialized forms and concrete expected observations.
- [Implementing Parallax](IMPLEMENTING.md) explains contract ownership and how
  to build or extend a language implementation.

Inspect the Python capability set with:

```bash
just core-show-slice slice-snapshot-1
```

## License

Copyright 2026 David Lee.

Licensed under the [Apache License, Version 2.0](LICENSE).
