# Getting started

This chapter takes you from an empty PostgreSQL database to a first write and a first
read. Along the way you meet the three objects every Parallax program uses: a model, a
`Database` root, and the scope you run work through.

## Install

Parallax needs the Python version its
[package metadata](../../packages/parallax-snapshot/pyproject.toml) requires,
[uv](https://docs.astral.sh/uv/) to build it, and a PostgreSQL server. It is not
published to a package index yet, so clone the repository and build its distributions:

```bash
git clone https://github.com/davidsunglee/parallax.git
cd parallax/languages/python
uv build --all-packages -o dist
pip install --find-links dist parallax-snapshot parallax-postgres parallax-evolution parallax-descriptor
```

Run the `pip install` in your application's environment. It installs the distributions
this guide imports from:

- `parallax-snapshot`, the API you program against. It takes its name from the snapshots
  its reads return, the immutable values that `find` hands you inside a `Snapshot`.
- `parallax-postgres`, the PostgreSQL adapter. It drives PostgreSQL through the psycopg
  driver, whose binary build it installs, so you need no system libpq; the lifecycle
  guide's [driver build](../postgresql-lifecycle.md#driver-build) section explains.
- `parallax-evolution`, which generates schema changes from your model.
- `parallax-descriptor`, which saves a model as a YAML descriptor and reads one back.
- `parallax-core`, which provides the `parallax.core` modules every chapter imports.
  `pip` takes it from the same `dist` directory, because the others depend on it.

Third-party dependencies, such as Pydantic and psycopg, come from PyPI as usual. Add
`parallax-aws` if you authenticate to Amazon RDS with IAM.

Each chapter of this guide opens with the imports for every name it uses. This
chapter's are:

<!-- example: getting-started-imports -->
```python
import datetime as dt
from decimal import Decimal

from parallax.core import ONE_TO_MANY, Attr, DomainModel, Entity, Int32, Rel, attr, index, rel
from parallax.core.db_port import Password
from parallax.core.dialect import POSTGRES
from parallax.core.entity import model_of
from parallax.core.execution import ExecutionFailure, TxnOptions
from parallax.evolution import ABSENT, evolve, schema_delta
from parallax.postgres import PostgresAdapter
from parallax.snapshot import (
    Database,
    NoResultFound,
    ScopedDatabase,
    TooManyResultsFound,
    TxnContext,
    connect,
)
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
def table_statements(model: DomainModel) -> tuple[str, ...]:
    """The SQL that creates the model's tables in an empty PostgreSQL schema.

    Parallax never changes a schema itself: run these with your migration tool.
    """
    return schema_delta(evolve(ABSENT, model_of(model)), POSTGRES).statements
```
<!-- /example -->

`model_of(model)` takes out of the `DomainModel` its language-neutral form: the same
entities, attributes and relationships as the core specification defines them, without
your Python classes. A YAML descriptor holds a model in that form too, so `evolve` can
compare a model rebuilt from a descriptor with one built from classes. `ABSENT` stands
for no model at all, as in an empty database, so `evolve(ABSENT, ...)` describes
creating everything this model needs. That change is always one `schema_delta` accepts,
and its type says so. `schema_delta` turns the change into PostgreSQL statements. For a
first try, run them in `psql` or any SQL client connected to an empty database. They
name no schema, so the tables land in the connection's current schema, usually `public`.

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
    return PostgresAdapter(conninfo, credentials=Password(password))


def add_and_find_a_customer(adapter: PostgresAdapter) -> Customer:
    model = DomainModel(Customer, Order)
    with connect(adapter, model) as database:
        db = database.using_database_login()
        db.transact(
            lambda tx: tx.insert(Customer(id=1, name="Ada Lovelace", email="ada@example.com"))
        )
        return db.find(Customer.where(Customer.id == 1)).result()
```
<!-- /example -->

To run it, create the tables first, as the previous section shows, then call
`add_and_find_a_customer(configure_the_database(conninfo, password))` with a connection
string such as `host=localhost dbname=shop user=shop`. It returns the customer it read
back. The rest of this chapter walks through it.

### Connect

`PostgresAdapter` is configuration. The connection string says where the database is,
in libpq's own syntax: `host=... dbname=...` keyword pairs, a `postgresql://` URI or a
`service=` name. `credentials` says how to log in. Keeping the password out of the
connection string is deliberate: building an adapter from a string that contains one
raises `ValueError`. Building an adapter opens nothing, so you can create it once at
startup and share it.

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

If the callback raises, nothing is committed, and you get an `ExecutionFailure`: the
error Parallax raises when work it ran fails. It carries the original exception as its
`cause` attribute, which is also its `__cause__`. A standalone read that fails while it
runs against the database reaches you the same way. A mistake Parallax refuses before
any work runs, such as a query naming an entity the model lacks, is raised as itself.
[Errors](08-errors.md#where-an-error-reaches-you) sets out both rules.

If the transaction fails for a reason a second attempt can fix, such as a deadlock,
Parallax rolls it back and runs the callback again. Each run is an attempt. By default
Parallax makes up to ten more attempts, and if the last one fails too, its failure
arrives inside an `ExecutionFailure`. That is why a transaction is a callback rather
than a block, and why anything the callback does outside the database must be safe to
repeat. A `db.transact` call made inside a callback joins the transaction that is
already running rather than starting another. [Transactions](05-transactions.md) covers
retries and nesting.

### Read

`Customer.where(...)` builds a query and runs nothing. `db.find(query)` runs it and
returns a `Snapshot`. `.result()` takes its single result and raises `NoResultFound` if
there is none or `TooManyResultsFound` if there are several. Use `.result_or_none()`
when the result may be missing, and `.results()` for a list. These accessors raise after
`find` has returned, so their errors reach you as themselves; inside a callback, one
you let escape becomes the `cause` of the `ExecutionFailure`.

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
