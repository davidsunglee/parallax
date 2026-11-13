# Getting started

This chapter takes you from an empty PostgreSQL database to a first write and a first
read. Along the way you meet the three objects every Parallax program uses: a model, a
`Database` root, and the scope you run work through.

## Install

Install the coordinated production distributions in your application's environment:

```bash
python -m pip install parallax-snapshot==0.2.0 parallax-postgres==0.2.0 parallax-evolution==0.2.0 parallax-descriptor==0.2.0
```

These are the distributions this guide imports: Snapshot supplies the application
API, PostgreSQL supplies the database adapter, Evolution generates schema changes,
and Descriptor reads and writes model descriptors. Their exact first-party
requirements install the matching `parallax-core`. Install only the distributions
your application needs; `parallax-conformance` is repository development tooling
and is not published.

The [package metadata](../../packages/parallax-snapshot/pyproject.toml) owns Python
support, the [wheel targets](../../tools/wheel_targets.json) own supported platforms,
and the [binding contract](../../spec/execution.md#supported-postgresql) owns
PostgreSQL support. Use wheels for normal installation. Third-party dependencies
come from PyPI alongside the selected Parallax packages.

Starting with `0.2.0`, Parallax no longer supports Intel macOS or musl Linux, including
Alpine, and publishes no wheels for them. Published `0.1.0` wheels remain available.
Move Intel macOS deployments to a supported host and Alpine deployments to a glibc-based
Linux environment. Building from source on a removed platform does not make it supported.

`parallax-postgres` installs psycopg's binary build, including libpq. For a build
against your own libpq, follow the lifecycle guide's
[C-driver installation](../postgresql-lifecycle.md#driver-build). Add
`"parallax-aws[postgres]==0.2.0"` for Amazon RDS IAM authentication; it is optional
and does not arrive with the other distributions.

The distributions share the `parallax` import namespace. Do not co-install the
unrelated PyPI distribution named `parallax`: its imports collide with this
namespace. The [release policy](../releasing.md#compatibility-and-maintenance)
explains coordinated upgrades and maintenance.

Each chapter of this guide opens with the imports for every name it uses. This
chapter's are:

<!-- example: getting-started-imports -->
```python
import datetime as dt
from decimal import Decimal

from parallax.core import (
    ONE_TO_MANY,
    Attr,
    DomainModel,
    Entity,
    Int32,
    NoResultFound,
    Password,
    Rel,
    TooManyResultsFound,
    TxnOptions,
    attr,
    index,
    rel,
)
from parallax.evolution import ABSENT, evolve, schema_delta
from parallax.postgres import PostgresAdapter, PostgresBinding, PostgresEndpoint
from parallax.snapshot import Database, ScopedDatabase, TxnContext, connect
```
<!-- /example -->

## Declare a model

An entity is a Pydantic class that maps to one table. Each attribute is annotated
`Attr[T]`, and `attr(...)` adds what the type alone can't say, such as the primary key
or a maximum length. An attribute is nullable only when its type says so, as `email`
does with `str | None`.

<!-- example: declare-customers-and-orders -->
```python
class Customer(Entity, table="customer"):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=100)
    email: Attr[str | None] = attr(max_length=200)
    orders: Rel[tuple["Order", ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "customer_id"))


class Order(Entity, table="orders", indices=(index("orders_customer", "customer_id"),)):
    id: Attr[int] = attr(primary_key=True)
    customer_id: Attr[int]
    placed_on: Attr[dt.date]
    total: Attr[Decimal] = attr(precision=12, scale=2)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    customer: Rel[Customer | None] = rel(reverse_of="orders")
```
<!-- /example -->

A customer has many orders, so `Customer.orders` is a relationship to `Order`, joined
from the customer's `id` to the order's `customer_id`. `Order.customer` is the same
relationship seen from the order: `reverse_of` names the side it mirrors. It is
`Customer | None` because Parallax creates no foreign key, so an order's `customer_id`
might match no customer. `index(...)` in the class header declares a database index on
`orders.customer_id`, which serves that join.

`version`, declared with `optimistic_locking=True` and stored as a 32-bit integer
(`Int32`), lets Parallax detect when two transactions change the same order. You never
pass it: Parallax sets it. You can also leave out a nullable attribute such as `email`
when you construct an instance, and it is then `None`.

`DomainModel(Customer, Order)` composes the classes into one checked model, which every
later step takes. [Modeling](02-modeling.md) explains all of these, along with the other
building blocks.

## Create the tables

Parallax never creates or alters tables by itself. It generates the statements, and you
apply them with whatever already runs your migrations:

<!-- example: create-tables-from-the-model -->
```python
def table_statements(model: DomainModel, binding: PostgresBinding) -> tuple[str, ...]:
    """The SQL that creates the model's tables where ``binding`` places them.

    Parallax never changes a schema itself, and never creates one: create the
    binding's schemas and run these with your migration tool.
    """
    return schema_delta(evolve(ABSENT, model, later_binding=binding)).statements
```
<!-- /example -->

`evolve` compares models by their entities, attributes and relationships, not by your
Python classes, so it can compare a `DomainModel` rebuilt from a YAML descriptor with one
built from classes. `ABSENT` stands
for no model at all, as in an empty database, so `evolve(ABSENT, ...)` describes
creating everything this model needs. That change is always one `schema_delta` accepts,
and its type says so. `schema_delta` turns the change into PostgreSQL statements. For a
first try, run them in `psql` or any SQL client connected to an empty database after
creating the schema the binding names. They name every table schema-qualified, as the
binding passed to `evolve` places it.

The binding says where this deployment keeps each table: the model names its tables but
not their schema. `PostgresBinding(default=PostgresLocation(schema="shop"))` keeps every
table in schema `shop`, so the first statement creates `shop.customer`.
[Database bindings](02-modeling.md#database-bindings) explains the rest of what a binding
can say.

When your model changes later, `evolve` compares the model you deployed before with the
new one, so keep a copy of each model you deploy. Exporting it as a descriptor with
`parallax.descriptor.export_yaml`, from the `parallax-descriptor` distribution, is one
way. [Model evolution](07-model-evolution.md#describing-a-change) explains how `evolve`
tells you whether `schema_delta` can carry a change.

## Write, then read

Here is a complete first program. It connects, inserts a customer, and reads it back:

<!-- example: connect-and-run-a-first-transaction -->
```python
def configure_the_database(conninfo: str, password: str) -> PostgresAdapter:
    """Configuration only: building an adapter opens no connection."""
    return PostgresAdapter(writer=PostgresEndpoint(conninfo, credentials=Password(password)))


def add_and_find_a_customer(adapter: PostgresAdapter, binding: PostgresBinding) -> Customer:
    model = DomainModel(Customer, Order)
    with connect(adapter, model, binding=binding) as database:
        db = database.using_database_login()
        db.transact(
            lambda tx: tx.insert(Customer(id=1, name="Ada Lovelace", email="ada@example.com"))
        )
        return db.find(Customer.where(Customer.id == 1)).result()
```
<!-- /example -->

To run it, create the tables first, as the previous section shows, then call
`add_and_find_a_customer(configure_the_database(conninfo, password), binding)` with a
connection string such as `host=localhost dbname=shop user=shop` and the binding you
created the tables under, such as `PostgresBinding(default=PostgresLocation(schema="shop"))`.
It returns the customer it read back. The rest of this chapter walks through it.

### Connect

`PostgresAdapter` is configuration, and its `writer` is the `PostgresEndpoint` your
transactions and reads use. The endpoint's connection string says where the database is,
in libpq's own syntax: `host=... dbname=...` keyword pairs, a `postgresql://` URI or a
`service=` name. `credentials` says how to log in. Keeping the password out of the
connection string is deliberate: building an endpoint from a string that contains one
raises `ValueError`. Building either opens nothing, so you can create them once at
startup and share them.

`connect` opens the runtime, including its connection pool, and returns a `Database`
root that owns it. Close the root when your application stops, either by calling
`close()` or, as here, by leaving its `with` block. `connect` also takes
`options=TxnOptions(...)`, the defaults every transaction of the root starts from: how
many times to retry, the isolation level and the concurrency preference.
[Transactions](05-transactions.md#options-and-root-defaults) covers them.

One root serves the whole process. Every thread can share it and the scopes derived from
it, while each transaction belongs to the thread that runs it. The API is synchronous;
an `asyncio` application runs each complete operation in a worker thread, as the
[PostgreSQL connection lifecycle](../postgresql-lifecycle.md#process-and-application-lifetime)
guide shows. That guide also covers what to decide for production: pooled or on-demand
connections, credentials that refresh (such as RDS IAM tokens), timeouts, observing the
pool, and reuse of read plans.

### Choose who the work runs as

A `Database` root doesn't read or write by itself. You first choose the authority your
work runs under, which gives you a `ScopedDatabase`: an Execution Scope.
`using_database_login()` runs everything as the login the adapter authenticated with.
That is the usual choice for a service with its own database account.

When each request should run as an application user instead, `using_principal(principal)`
derives a scope for that user. The principal names the user and the database role the
work runs under, which the PostgreSQL adapter switches to with `SET ROLE`. The
[lifecycle guide](../postgresql-lifecycle.md#execution-authority-and-session-affinity)
covers the PostgreSQL side, and [Execution authority](06-execution-authority.md) shows
both kinds of scope in use.

You can derive as many scopes from one root as you need. They share its connections.

### Write in a transaction

`db.transact(callback)` runs the callback inside a transaction and commits when it
returns. The callback receives a `TxnContext`, here `tx`, and every write happens
through it, here `tx.insert(...)`. Once the transaction has committed, `transact`
returns whatever the callback returned.

If the callback raises, nothing is committed, and the exception it raised reaches you
as itself, with a note naming the model edition the transaction ran under. A
standalone read that fails while it runs against the database reaches you the same
way. A mistake Parallax refuses before any work runs, such as a query naming an entity
the model lacks, is raised without a note.
[Errors](08-errors.md#where-an-error-reaches-you) sets out both rules.

If the transaction fails for a reason a second attempt can fix, such as a deadlock,
Parallax rolls it back and runs the callback again. Each run is an attempt. By default
Parallax makes up to ten more attempts, and if the last one fails too, its failure
reaches you. That is why a transaction is a callback rather
than a block, and why anything the callback does outside the database must be safe to
repeat. A `db.transact` call made inside a callback joins the transaction that is
already running rather than starting another. [Transactions](05-transactions.md) covers
retries and nesting.

### Read

`Customer.where(...)` builds a query and runs nothing. `db.find(query)` runs it and
returns a `Snapshot`. `.result()` takes its single result and raises `NoResultFound` if
there is none or `TooManyResultsFound` if there are several. Use `.result_or_none()`
when the result may be missing, and `.results()` for a list. These accessors raise after
`find` has returned, so their errors reach you without a note; inside a callback, one
you let escape gains the transaction's note.

What you get back is a `Customer`, an instance of your own class, and it is frozen. To
change a customer, you read it inside a transaction, call `edit(...)` for a modified
copy, and amend that copy. [Writing](04-writing.md) explains why the read belongs in the
same transaction.

## How it works →

- [Execution](../../../../core/spec/m-execution.md) defines the Database Root, Execution
  Scopes and transactions; the
  [Python execution binding](../../spec/execution.md) records the Python spellings.
- [Execution authority](../../../../core/spec/m-execution-authority.md) defines what a
  scope's authority is and how it reaches the database.
- [Schema delta](../../../../core/spec/m-schema-delta.md) defines the generated
  statements.
