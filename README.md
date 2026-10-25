# Parallax

Parallax is an object-relational mapper for applications whose data must stay correct
under concurrent writes and whose history matters. You declare your domain as typed
entity classes. Parallax reads complete, immutable object graphs, writes only inside
explicit transactions, and can keep a full record of how your data changed: when the
database learned each fact, and when each fact is true in the world. It ships today for
**Python with PostgreSQL**.

## Why Parallax

- **Reads return complete, immutable values.** A read gives you frozen instances of your
  own classes, with the relationships you asked for already loaded. Following a
  relationship never runs a hidden query, so there is no lazy loading and no N+1
  surprise. See [Reading and querying](languages/python/docs/guide/03-reading.md).
- **Transactions are explicit, and blind writes are refused.** Every write runs inside
  `db.transact(...)`, and Parallax refuses a blind write, one that changes a row by key
  without knowing what it holds. A write to an existing row shows that it knows in one of
  four ways. A read of the row in the same transaction shows it, either through the
  version the write then checks or, for a row with no version, through the lock the read
  took. So does the transaction's own insert of the row, or, for a value read earlier,
  the version it showed, stated with the write. Only an entity with no version and no
  history also accepts predicate writes, which change the rows a query selects without
  reading them.
  See [Writing](languages/python/docs/guide/04-writing.md).
- **Conflicts are retried for you, within a bound.** When a deadlock, or a change to a
  row the transaction read, ends an attempt, Parallax runs your whole callback again
  against fresh reads, up to ten more times by default. See
  [Transactions](languages/python/docs/guide/05-transactions.md).
- **History is part of the model.** Declare an entity `TxTemporal` to keep every state the
  database held, or `Bitemporal` to also record when each fact is true. The tour below
  reads the past and corrects a window of time.
- **Storage layout is invisible to callers.** Store an entity in ordinary columns or as
  one JSON document per row. For the same stored data, your queries, results and writes
  are the same. What changes is who guards that data: the database's column
  constraints, or Parallax checking each document as it reads it. See
  [Modeling](languages/python/docs/guide/02-modeling.md#choosing-a-storage-layout).
- **Typed and Wire are peers.** One query returns instances of your classes, through the
  Typed API, or immutable mappings of JSON-ready values, through the Wire API, and both
  work inside the same transaction. The tour ends with the same read both ways.
- **Models evolve without a restart.** Once your migration has run, a running process
  can switch to a changed model, and each transaction keeps the model it started with.
  The changed model's classes must already be loaded in the process; a model read from a
  YAML descriptor needs none and serves the Wire API. See
  [Model evolution](languages/python/docs/guide/07-model-evolution.md).
- **One specification, proven against real PostgreSQL.** A language-neutral
  specification and a compatibility corpus define the behaviour, and the Python
  implementation is tested against them on a real database. See
  [Implementing Parallax](IMPLEMENTING.md).

## A 60-second tour

The snippets below leave out imports and the setup that gives you `db`.
[Getting started](languages/python/docs/guide/01-getting-started.md) shows both, and each
chapter of the guide lists the imports its examples use.

Declare your entities as Pydantic classes. Annotations name each attribute and
relationship, `indices` declares database indexes, and an attribute declared with
`optimistic_locking=True`, here `version`, turns on optimistic locking.

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

Build queries from class attributes. This one filters customers by their orders and
loads those orders in the same read.

<!-- example: filter-on-a-relationship -->
```python
def customers_with_an_order_over(db: ScopedDatabase, total: Decimal) -> list[Customer]:
    """Each matching customer arrives with all of its orders already loaded."""
    query = Customer.where(Customer.orders.any(Order.total > total)).include(Customer.orders)
    return db.find(query).results()
```
<!-- /example -->

Values are frozen. To change one, edit a copy and hand it to a transaction. The read in
the same transaction is what allows the amendment.

<!-- example: insert-and-amend-in-one-transaction -->
```python
def place_an_order(db: ScopedDatabase) -> None:
    """Insert an order and update its customer: both commit, or neither does."""

    def place(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == 1)).result()
        tx.insert(
            Order(
                id=7,
                customer_id=customer.id,
                placed_on=dt.date(2024, 5, 2),
                total=Decimal("80.00"),
            )
        )
        tx.amend(customer.edit(email="ada@example.org"))

    db.transact(place)
```
<!-- /example -->

A `TxTemporal` entity keeps every state the database held. Ask what it held at any
past instant.

<!-- example: read-as-of-a-past-instant -->
```python
class CreditLimit(TxTemporal, table="credit_limit"):
    customer_id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=12, scale=2)


def credit_limit_on_record(db: ScopedDatabase, customer_id: int, when: dt.datetime) -> Decimal:
    """The limit the database held at ``when``, even if it has changed since."""
    query = CreditLimit.where(CreditLimit.customer_id == customer_id).as_of(tx_time=when)
    return db.find(query).result().amount
```
<!-- /example -->

A `Bitemporal` entity also records when each fact is true. An amendment starts at the
time its read asked for, June here, and `until` ends it, so it changes only that window.
The price before and after the window is untouched, and the previous prices stay
readable as history.

<!-- example: amend-a-valid-time-window -->
```python
class Price(Bitemporal, table="price"):
    sku: Attr[str] = attr(primary_key=True, max_length=20)
    amount: Attr[Decimal] = attr(precision=12, scale=2)


def run_a_summer_sale(db: ScopedDatabase) -> None:
    """Lower a price from June to September; the rest of the year keeps the old price."""
    june = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    september = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def discount(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == "TEA-1").as_of(valid_time=june)).result()
        tx.amend(price.edit(amount=Decimal("8.00")), until=september)

    db.transact(discount)
```
<!-- /example -->

The same query runs through Wire, which delivers immutable mappings ready to serialize.
Their names and values take Parallax's language-neutral canonical form, such as
`customerId` for `customer_id` and a decimal as a string.

<!-- example: read-through-wire -->
```python
def customers_with_an_order_over_as_wire(db: ScopedDatabase, total: Decimal) -> list[WireEntity]:
    """The same read, delivered as immutable mappings ready to serialize."""
    query = Customer.where(Customer.orders.any(Order.total > total)).include(Customer.orders)
    return db.wire.find(query).results()
```
<!-- /example -->

Every snippet on this page runs against a real PostgreSQL database in the test suite.

## Where to go next

- **Learn the API**: the [Python Guide](languages/python/docs/guide/README.md), starting
  with [Getting started](languages/python/docs/guide/01-getting-started.md).
- **Run it in production**: [Operations](languages/python/docs/guide/09-operations.md)
  shows how to configure a running application's connection pool, query-plan cache and
  logging, and the
  [PostgreSQL connection lifecycle](languages/python/docs/postgresql-lifecycle.md) covers
  pooling, credentials, timeouts and observability.
- **Understand how it works**: the [concepts](docs/concepts/README.md) explain each
  feature family in domain terms, and the
  [Python architecture](languages/python/docs/architecture/README.md) maps how the
  implementation is built.
- **Look up exact behaviour**: the [Python binding](languages/python/spec/python.md) and
  the [core specification](core/spec/00-overview.md).
- **Build or extend an implementation**: [Implementing Parallax](IMPLEMENTING.md).

## Developing Parallax

The implementation lives in [`languages/python/`](languages/python/).
[`TESTING.md`](TESTING.md) explains verification;
[`languages/python/TESTING.md`](languages/python/TESTING.md) covers Python test
placement and fixtures. The repository's commands run through
[just](https://github.com/casey/just), a command runner. Run the merge gate from the
root:

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

## License

Copyright 2026 David Lee.

Licensed under the [Apache License, Version 2.0](LICENSE).
