# Modeling

Your model is a set of Python classes. Each entity class maps to a table, and a
`DomainModel` composes the classes your application uses and checks them as a whole.
There is no global registry: a class takes part only when you pass it to `DomainModel`.

This chapter starts with a plain entity and adds one idea per section: relationships,
value objects, inheritance, history, optimistic locking and storage layout. Every
example belongs to one small shop domain.

## Entities and keys

These two entities appeared in [Getting started](01-getting-started.md):

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

The class header names the table. Each attribute's Python type decides its column
type: `int` is a 64-bit integer, and `type=Int32` narrows it; a `Decimal` states its
`precision` and `scale`; a `str` usually states a `max_length`. An attribute is nullable
only when its annotation says `| None`; there is no separate `nullable` option.

`primary_key=True` makes `id` the key, with values your application assigns. To let
Parallax generate keys instead, use `primary_key=MAX` or `primary_key=Sequence(...)`.
The [primary key generation](../../../../core/spec/m-pk-gen.md) contract describes both.

Python names become canonical names by dropping each underscore and capitalizing the
next letter, so `customer_id` is `customerId` wherever names are serialized, as in
Wire. Use `column=` to store an attribute under a column name of your choosing, and a
`persistence=READ_ONLY` header for an entity your application only reads.

## Relationships

A relationship connects two entities through their attributes. `Customer.orders` is the
defining side: it states the cardinality and the join, from the customer's `id` to the
order's `customer_id`. `Order.customer` is the reverse side and only names the
relationship it mirrors.

The annotation states what a loaded relationship holds. `Rel[tuple[Order, ...]]` is a
to-many relationship and is never `None`; `Rel[Customer | None]` is a to-one
relationship that may load as `None`. The index on `orders.customer_id` serves the join.

Queries can filter on a relationship and load it in the same read:

<!-- example: filter-on-a-relationship -->
```python
def customers_with_an_order_over(db: ScopedDatabase, total: Decimal) -> list[Customer]:
    """Each matching customer arrives with all of its orders already loaded."""
    query = Customer.where(Customer.orders.any(Order.total > total)).include(Customer.orders)
    return db.find(query).results()
```
<!-- /example -->

A read loads only the relationships it asks for with `include`. Touching one it didn't
load raises `UnloadedRelationshipError` instead of quietly running another query, so an
unloaded relationship is never mistaken for an empty one. A to-many relationship can
also declare the order its targets load in, with `order_by=`.
[Reading and querying](03-reading.md) covers loading graphs.

## Value objects

Some structured values have no identity of their own: an address belongs to the
shipment it's on and is always read and written with it. Declare such a value as a
`ValueObject` and use it as an attribute type:

<!-- example: query-a-value-object -->
```python
class Address(ValueObject):
    street: Attr[str]
    city: Attr[str]
    postcode: Attr[str]


class Shipment(Entity, table="shipment"):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    ship_to: Attr[Address]
    tracking_number: Attr[str | None] = attr(max_length=40)


def shipments_to(db: ScopedDatabase, city: str) -> list[Shipment]:
    return db.find(Shipment.where(Shipment.ship_to.city == city)).results()
```
<!-- /example -->

A value object is frozen, like an entity, and is stored inside its entity's row; in
PostgreSQL, `ship_to` is one JSON column. Queries reach into it with ordinary attribute
paths such as `Shipment.ship_to.city`. Declare `Attr[Address | None]` for an optional
value and `Attr[tuple[Address, ...]]` for a list of them. Choose an entity instead when
the thing has its own identity, is shared between owners, or is read on its own.

## Inheritance families

When several kinds of a thing share attributes, declare them as one inheritance
family. A family is a closed tree: one abstract root, optional abstract subtypes, and
the concrete subtypes you actually store.

<!-- example: read-an-inheritance-family -->
```python
class Payment(
    Entity,
    table="payment",
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    amount: Attr[Decimal] = attr(precision=12, scale=2)


class CardPayment(Payment, inheritance=ConcreteSubtype(tag_value="card")):
    card_last_four: Attr[str] = attr(max_length=4)


class BankTransfer(Payment, inheritance=ConcreteSubtype(tag_value="transfer")):
    reference: Attr[str] = attr(max_length=40)


def payments_for(db: ScopedDatabase, order_id: int) -> list[Payment]:
    """Each payment arrives as its own concrete class."""
    return db.find(Payment.where(Payment.order_id == order_id)).results()
```
<!-- /example -->

`Payment` is abstract, so you never store one directly; you insert a `CardPayment` or a
`BankTransfer`. Reading the root returns each row as its own concrete class, carrying
its own attributes and none of its siblings'.

The root chooses how the family is stored. `TablePerHierarchy` keeps every concrete
subtype in one table, with a tag column naming each row's subtype; each concrete
subtype supplies its `tag_value`. `TABLE_PER_CONCRETE_SUBTYPE` gives each concrete
subtype a table of its own, which each subtype names with `table=`. Either way, queries
can narrow a family to particular subtypes and filter on their attributes, as
[Reading and querying](03-reading.md) shows. Decisions that apply to the whole family,
such as its history and its locking, are made once at the root.

## Choosing a temporality profile

Every entity has one of three temporality profiles, chosen by its base class:

| Base class | Profile | What the database keeps |
| -- | -- | -- |
| `Entity` | Non-Temporal | The current state only |
| `TxTemporal` | Transaction-Time-Only | Every state it held, and when it held it |
| `Bitemporal` | Bitemporal | Every state it held, and when each fact is true in the world |

Transaction Time records when the database learned something. A Transaction-Time-Only
entity answers "what did we have on record on 1 March?", which suits audit trails and
reproducing past reports:

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

Valid Time records when a fact is true in the domain, independently of when anyone
recorded it. A Bitemporal entity tracks both, so you can enter a change ahead of time or
correct the past while keeping what you previously believed. Here a price changes for
a summer window only:

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

The time-tracking attributes, `tx_start` and `tx_end` and, for a Bitemporal entity,
`valid_start` and `valid_end`, belong to Parallax. You don't declare or assign them;
you read them, and you choose the instants you read at.

To choose a profile, ask what your application will need to answer later:

- Only the current state? Use `Entity`.
- What the data looked like at a past moment, and when it changed? Use `TxTemporal`.
- What was true on a given date, including changes recorded late or in advance? Use
  `Bitemporal`.

Temporal entities change through the same verbs as other entities, with one exception:
you remove one with `terminate`, which ends its current state and keeps its history,
rather than with `delete`.
[Writing](04-writing.md) shows each profile's writes.

## Optimistic-lock versions

`Order` declares `version` with `optimistic_locking=True`. Parallax sets the version on
insert and advances it on every write; you never assign it. When a transaction writes an
order it read, the write checks that the version is still the one it read. If another
transaction changed the order in between, the write conflicts, and Parallax re-runs your
transaction against a fresh read. [Transactions](05-transactions.md) shows that replay.

`Customer` has no version. Parallax protects a write to it differently: a read inside a
writable transaction takes a shared lock on the customer's row, and the lock holds until
the transaction ends.

A temporal entity doesn't declare a `version`. The Transaction-Time start of the state a
transaction read already identifies that state, and Parallax checks it instead.

## Choosing a storage layout

By default an entity uses the Columns layout: each attribute gets its own column, and
each value object its own JSON column. The Relational Document Layout instead keeps an
entity's ordinary attributes together in one JSON document column, named `payload`
unless you choose another name with `Document(column=...)`:

<!-- example: query-a-document-layout-entity -->
```python
class Product(Entity, table="product", layout=Document()):
    sku: Attr[str] = attr(primary_key=True, max_length=20)
    name: Attr[str] = attr(max_length=100)
    description: Attr[str | None]


def products_named(db: ScopedDatabase, name: str) -> list[Product]:
    """The same query a column-stored product would take."""
    return db.find(Product.where(Product.name == name)).results()
```
<!-- /example -->

The `product` table has two columns, `sku` and `payload`. Columns that give a row its
structure stay real columns, such as the primary key, relationship join columns,
temporal bounds, the version of a Non-Temporal entity, and a family's tag column.

Nothing above the storage changes. The query, the values it returns and the writes you
make are the same under either layout, so you can choose per entity without changing
code that uses it. The Document layout can suit an entity with many optional or
nested attributes that you rarely filter on. Moving an existing entity from one layout
to the other is a schema and data migration that you run yourself.

## How it works →

- The [Python declarations binding](../../spec/declarations.md) records how classes,
  attributes, relationships and value objects are spelled.
- [Metamodel](../../../../core/spec/m-metamodel.md) and
  [model formation](../../../../core/spec/m-model-formation.md) define what a model
  declares and how it is checked.
- [Relationships](../../../../core/spec/m-relationship.md),
  [value objects](../../../../core/spec/m-value-object.md) and
  [inheritance](../../../../core/spec/m-inheritance.md) define each building block.
- [Temporal reads](../../../../core/spec/m-temporal-read.md) and
  [temporal writes](../../../../core/spec/m-temporal-write.md) define the two time axes.
- [Optimistic locking](../../../../core/spec/m-opt-lock.md) and
  [read locks](../../../../core/spec/m-read-lock.md) define the two concurrency
  strategies.
- [Storage layout](../../../../core/spec/m-storage-layout.md) defines both layouts and
  why callers can't tell them apart.
