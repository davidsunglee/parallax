# Modeling

Your model is a set of Python classes. Each entity class maps to a table, and a
`DomainModel` composes the classes your application uses and checks them as a whole.
There is no global registry: a class takes part only when you pass it to `DomainModel`.
A model that breaks a rule, such as a join that names an attribute its entity doesn't
have, makes `DomainModel(...)` raise a `ValueError` whose `issues` list every problem
found, before anything touches the database. [Errors](08-errors.md#mistakes-in-what-you-wrote)
describes those issues.

This chapter starts with a plain entity and adds one idea per section: relationships,
value objects, inheritance, history, optimistic locking and storage layout. Every
example belongs to one small shop domain. The chapter uses these imports:

<!-- example: modeling-imports -->
```python
import datetime as dt
from decimal import Decimal

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    ONE_TO_ONE,
    READ_ONLY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    EntityDefinitionError,
    Int32,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    ValueObject,
    attr,
    desc,
    index,
    rel,
)
from parallax.core.entity import UnloadedRelationshipError
from parallax.snapshot import ScopedDatabase, TxnContext
```
<!-- /example -->

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
`precision` and `scale`; a `str` with a `max_length` is a bounded string, and one
without it, such as `Product.description` below, is unbounded text. The other attribute
types are `bool`, `float`, `bytes`, `datetime.date`, `datetime.time`,
`datetime.datetime` and `uuid.UUID`, besides value objects and tuples of one of these
types. There is no enum type. A `datetime` must be timezone-aware, and Parallax stores
it as a UTC instant; a `date` or a `time` has no timezone. The
[declarations binding](../../spec/declarations.md#python-scalar-carriers) lists what each
type accepts. An attribute is nullable only when its annotation says `| None`; there is
no separate `nullable` option.

An entity is a frozen Pydantic model, and `model_dump` works as usual. Validators you
declare run when you construct an instance and when `edit(...)` changes one, though not
when Parallax builds one from a stored row: stored data is checked against the model
itself, as [Choosing a storage layout](#choosing-a-storage-layout) describes. An
attribute takes no default value: its slot holds `attr(...)` or nothing. The constructor
needs every attribute except a nullable one, which is then `None`, and one Parallax
sets, such as `version`. To change a value, `edit(...)` returns a modified copy;
`model_copy` is refused.

`primary_key=True` makes `id` the key, with values your application assigns. A primary
key is always one attribute, of type `int`, `str` or `uuid.UUID`.

`indices=` in the class header declares database indexes, each written
`index(name, *attributes)`, and `schema_delta` creates them with the tables. The index on
`orders.customer_id` serves the join to customers. `index(..., unique=True)` declares a
unique index instead, so the database refuses a second row with the same values.

Python names become canonical names by dropping each underscore and capitalizing the
next letter, so `customer_id` is `customerId` wherever names are serialized. Wire, the
API that reads and writes plain mappings instead of your classes, is one such place;
[Reading](03-reading.md#the-wire-api) covers it. The default column name comes back from
the canonical name, so `customer_id` is stored in a `customer_id` column. Use `column=`
to choose another, and a `persistence=READ_ONLY` header for an entity your application
only reads.

`table=` names the table and nothing more: the class header has no schema option. Neither
the generated statements nor Parallax's queries name a schema, so PostgreSQL finds the
tables through the connection's `search_path`; set it on the login or in the connection
string to keep the tables somewhere other than `public`. `namespace=`, which
[Reading](03-reading.md#the-wire-api) shows, has nothing to do with it: it qualifies an
entity's canonical name.

The strings in `index(...)`, `join=`, `reverse_of=` and `order_by=` name Python
attributes, never columns or canonical names.

A member can't take a name Parallax uses on the class itself, such as `all`, `where`,
`include` or `edit`, nor one starting with `model_`. Creating such a class raises
`EntityDefinitionError` with the code `entity-reserved-member-name`. To keep `all` as the
canonical name, give the attribute another Python name and rename it:
`all_items: Attr[int] = attr(name="all")`.

## Relationships

A relationship connects two entities through their attributes. `Customer.orders` is the
defining side: it states the cardinality and the join, from the customer's `id` to the
order's `customer_id`. `Order.customer` is the reverse side and only names the
relationship it mirrors.

The cardinality is `ONE_TO_MANY`, `MANY_TO_ONE` or `ONE_TO_ONE`, so a to-one
relationship can be the defining side too: declared on `Order`,
`rel(cardinality=MANY_TO_ONE, join=("customer_id", "id"))` would define the same link
from the order's end. There is no many-to-many relationship. Model one with an entity of
its own, such as an order line, related to each side.

The annotation states what a loaded relationship holds. `Rel[tuple[Order, ...]]` is a
to-many relationship and is never `None`; `Rel[Customer | None]` is a to-one
relationship that may load as `None`. `Order.customer` has to say `| None`: Parallax
creates no foreign key, so the customer an order points at may not exist, and
`DomainModel` refuses `Rel[Customer]` there.

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
also declare the order its targets load in, such as `order_by=(desc("placed_on"),)`; a
bare name sorts ascending. [Reading and querying](03-reading.md) covers loading graphs.

A relationship is not a database constraint. Parallax creates no foreign keys and
doesn't cascade a delete, so deleting a customer leaves its orders in place.

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
family. A family is a closed tree: one abstract root, the concrete subtypes you actually
store, and optionally abstract subtypes between them that group concrete subtypes and
are never stored themselves.

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
subtype supplies its `tag_value`. Because every subtype's rows share the table, the
columns of a subtype's own attributes, such as `card_last_four`, are nullable there:
the other subtypes' rows leave them empty.

`AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)` instead gives each concrete subtype a table of
its own, which each subtype names with `table=` while the root names none. This family
of deliveries also has an abstract subtype, `CarrierDelivery`, which groups the two
deliveries a carrier tracks. It declares `inheritance=AbstractSubtype`, is never stored
itself, and is subclassed in turn by concrete subtypes:

<!-- example: store-each-subtype-in-its-own-table -->
```python
class Delivery(Entity, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]


class CarrierDelivery(Delivery, inheritance=AbstractSubtype):
    tracking_number: Attr[str] = attr(max_length=40)


class CourierDelivery(CarrierDelivery, table="courier_delivery", inheritance=ConcreteSubtype):
    courier: Attr[str] = attr(max_length=40)


class PostalDelivery(CarrierDelivery, table="postal_delivery", inheritance=ConcreteSubtype):
    service: Attr[str] = attr(max_length=20)


class StorePickup(Delivery, table="store_pickup", inheritance=ConcreteSubtype):
    store: Attr[str] = attr(max_length=40)


def arrange_a_pickup(db: ScopedDatabase, delivery_id: int, order_id: int, store: str) -> None:
    """Insert a concrete subtype: the row goes to ``store_pickup``, its own table."""
    db.transact(lambda tx: tx.insert(StorePickup(id=delivery_id, order_id=order_id, store=store)))


def deliveries_for(db: ScopedDatabase, order_id: int) -> list[Delivery]:
    """Read the whole family, from every subtype's table, each as its own concrete class."""
    return db.find(Delivery.where(Delivery.order_id == order_id)).results()


def tracked_deliveries_for(db: ScopedDatabase, order_id: int) -> list[CarrierDelivery]:
    """Narrow to the abstract subtype: courier and postal deliveries, never a pickup."""
    query = Delivery.where(Delivery.order_id == order_id).narrow(CarrierDelivery)
    return db.find(query).results()
```
<!-- /example -->

The generated statements create three tables, `courier_delivery`, `postal_delivery` and
`store_pickup`, and none for `Delivery` or `CarrierDelivery`. Inserting a concrete
subtype, as `arrange_a_pickup` does, writes its own table. Reading the root reads every
subtype's table, and narrowing to the abstract subtype reads only its concrete
subtypes'.

The spellings follow one rule. A role or strategy with no required argument can be
written bare or called, so `AbstractSubtype` and `AbstractSubtype()` mean the same, as do
`ConcreteSubtype` and `ConcreteSubtype()`. One given an argument is called with it, as
`TablePerHierarchy(tag_column=...)` and `ConcreteSubtype(tag_value=...)` are.
`TABLE_PER_CONCRETE_SUBTYPE` is a constant, because that strategy has no settings at all.

Under either strategy, queries can narrow a family to particular subtypes and filter on their
attributes, as [Reading and querying](03-reading.md#predicates-ordering-and-limits)
shows. Decisions that apply to the whole family, such as its history and its locking,
are made once at the root. A `DomainModel` must include a family's root along with the
subtypes you use; a concrete subtype you leave out is simply not part of that model.

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
a summer window only. The `discount` callback receives the `TxnContext` that
[Getting started](01-getting-started.md#write-in-a-transaction) introduced:

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

The callback reads the price as of June, and the amendment starts where that read
looked: Valid Time June. `until=september` ends it there, so the price before June and
from September onwards keeps its old value. [Writing](04-writing.md#bitemporal-entities)
builds Bitemporal writes up step by step.

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

Parallax protects a write to a row a transaction read in one of two ways, its two
concurrency strategies. The optimistic strategy checks, when the write runs, that the
row still holds the state the read saw. The locking strategy takes a shared lock on the
row when it is read, so nobody else can change it until the transaction ends. Which
one applies depends on the entity and on what the transaction prefers.

`Order` declares `version` with `optimistic_locking=True`. Parallax sets the version to
1 on insert and advances it on every write; you never assign it. When a transaction
writes an order it read, the write checks that the version is still the one it read. If
another transaction changed the order in between, the write conflicts, and Parallax
re-runs your transaction against a fresh read. [Transactions](05-transactions.md#optimistic-and-locking-concurrency) shows
that replay, and how a transaction can prefer the locking strategy for every entity.

`Customer` has no version, so nothing in its row shows that it changed. Parallax always
uses the locking strategy for it: a read inside `db.transact`, a read-write transaction,
takes a shared lock on the customer's row, and the lock holds until the transaction ends.
Reads outside one take no lock, as [Reading](03-reading.md#where-a-read-runs) explains.

A temporal entity can't declare a `version`; `DomainModel` refuses one. The
Transaction-Time start of the state a transaction read already identifies that state,
and the optimistic strategy checks it instead.

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
temporal bounds, an optimistic-lock version, which only a Non-Temporal entity can have,
and a family's tag column.

For data that fits the model, nothing above the storage changes. The query, the values
it returns and the writes you make are the same under either layout, so you can choose
per entity without changing code that uses it. What differs is who guards the stored
data. Under Columns, each attribute's column type and constraints guard it inside the
database. A document can hold data that breaks the model, such as a missing `name`, so
Parallax checks each document as it reads it; [Reading](03-reading.md#result-shapes)
shows what a read does with a row that fails.

The Document layout can suit an entity with many optional or nested attributes that you
rarely filter on. Moving an existing entity from one layout to the other is a schema and
data migration that you run yourself.

## How it works →

- The [Python declarations binding](../../spec/declarations.md) records how classes,
  attributes, relationships and value objects are spelled.
- [Metamodel](../../../../core/spec/m-metamodel.md) and
  [model formation](../../../../core/spec/m-model-formation.md) define what a model
  declares and how it is checked.
- [Relationships](../../../../core/spec/m-relationship.md),
  [value objects](../../../../core/spec/m-value-object.md) and
  [inheritance](../../../../core/spec/m-inheritance.md) define each building block.
- [The temporal model](../../../../docs/concepts/temporal-model.md) explains the two time
  axes, milestones and how a write composes over existing history.
- [Temporal reads](../../../../core/spec/m-temporal-read.md) and
  [temporal writes](../../../../core/spec/m-temporal-write.md) define the two time axes.
- [Optimistic locking](../../../../core/spec/m-opt-lock.md) and
  [read locks](../../../../core/spec/m-read-lock.md) define the two concurrency
  strategies.
- [Storage layout](../../../../core/spec/m-storage-layout.md) defines both layouts and
  why callers can't tell them apart.
