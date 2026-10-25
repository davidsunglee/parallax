# Reading and querying

A read returns immutable values: frozen instances of your own entity classes, with the
relationships you asked for already loaded. Following one of those relationships never
runs another query. Building a query runs nothing either; the database is touched only
when you hand the query to `find` or `stream`.

This chapter starts with the question every read answers first, where it runs, and then
builds queries, loads graphs and chooses result shapes. After that it covers streaming
large results, reading history, and the Wire API, which delivers the same reads as plain
mappings. The examples use the shop model from [Modeling](02-modeling.md) and these
imports:

<!-- example: reading-imports -->
```python
import datetime as dt
import json
from decimal import Decimal
from typing import TextIO

from parallax.core import LATEST, TX_TIME, VALID_TIME, Attr, QueryDefinitionError, TxTemporal, attr
from parallax.core.entity import UnloadedRelationshipError
from parallax.core.execution import ExecutionFailure, TransactionAccessModeError
from parallax.core.read_delivery import InvalidData, InvalidDataError, StreamStateError
from parallax.core.unit_work import WriteEvidenceError
from parallax.snapshot import (
    NoResultFound,
    ReadOnlyTxnContext,
    ScopedDatabase,
    Snapshot,
    TooManyResultsFound,
    TxnContext,
    WireEntity,
    is_view_loaded,
)
```
<!-- /example -->

## Where a read runs

Most reads need nothing more than a scope. `db.find(query)` runs the query and returns
its result:

<!-- example: look-up-a-customer -->
```python
def look_up_a_customer(db: ScopedDatabase, customer_id: int) -> Customer:
    """A one-off lookup: there is no transaction to open or close."""
    return db.find(Customer.where(Customer.id == customer_id)).result()
```
<!-- /example -->

This is a standalone read. It borrows a connection for as long as the read takes and
returns it before you see the result. For a lookup, a page that displays data, or any
other read that you won't write back, that is all you need.

A read can also run inside a transaction. `db.read_only(callback)` opens a read-only
transaction and hands its callback a `ReadOnlyTxnContext`, usually called `rtx`, which
can read but has no write verbs. `db.transact(callback)` opens a read-write one and hands
its callback the `TxnContext`, `tx`, from
[Getting started](01-getting-started.md#write-in-a-transaction). Both contexts have
`find` and `stream`, which read inside the transaction. Which of the three you choose
decides what a read sees, what it locks, and whether you can write what it returned.

In short: a standalone read is the simplest and locks nothing. A read-only transaction
lets several reads see one consistent state. A read inside `transact` is the one whose
values you can write back. A read-write transaction also holds its pending writes, the
writes you have made through `tx` that it hasn't sent to the database yet, and it sends
them before each read, so the read sees them. The table spells out the details, some of
which later chapters explain: [Writing](04-writing.md) covers pending writes and target
writes, and [Transactions](05-transactions.md) covers isolation and locking.

|  | Standalone: `db.find`, `db.stream` | Read-only: `db.read_only(...)` | Read-write: `db.transact(...)` |
| -- | -- | -- | -- |
| Transaction | None. Each read borrows its own connection, and a stream borrows one for each page | One read-only transaction | One read-write transaction |
| Do several reads agree? | No. Each read sees the database as it is when that read runs | Only at Repeatable Read or Serializable: on PostgreSQL, every read in the transaction then sees one snapshot of the database. At the default, Read Committed, each read sees the latest commits | As for read-only. A read also sees the transaction's own writes |
| Do a stream's pages agree? | No. Each page is consistent only within itself | At Repeatable Read or Serializable, a row already delivered can't change value, and on PostgreSQL every page reads the transaction's one snapshot, so no new rows appear either. At Read Committed, each page is consistent only within itself | As for read-only |
| Row locks | None | None | A shared lock on each row read from an entity that uses the locking strategy: always a Non-Temporal entity without a version, such as `Customer`, and every entity when the transaction prefers locking |
| Sees this transaction's pending writes | No. It reads outside every transaction | Nothing to see: a read-only transaction writes nothing | Yes. The read first sends the pending writes |
| Can the value license a later write? | No. Amending it raises `WriteEvidenceError`; a [target write](04-writing.md#target-writes), which states the version the value showed, can write it instead | No, as for a standalone read | Yes, within the same attempt. History and range reads can't, and a value read at a past Transaction Time is read-only |
| Stream lifetime | Can stay open across pages, holding no connection between them | Ends with the attempt | Ends with the attempt |

Both kinds of transaction run at Read Committed unless you pass `isolation=`, as
`"read_committed"`, `"repeatable_read"` or `"serializable"`, or give the root another
default. [Modeling](02-modeling.md#optimistic-lock-versions) explains the two concurrency
strategies, and [Transactions](05-transactions.md#isolation-levels) explains the isolation levels.

A read through `db` never joins a transaction: `db.find` and `db.stream` make a
standalone read on their own connection wherever you call them, even inside a callback.
To read inside the transaction, use the context the callback receives: `rtx.find` in a
read-only transaction, `tx.find` in a read-write one.

The distinction matters in four situations.

### You'll write what you read

This is the main one. A value from a standalone or read-only read took part in nothing a
writing transaction can stand on: that transaction never locked the row or observed its
revision, and the row may have changed since. So the value can't license an amendment.
This is the rule that [Writing](04-writing.md) calls "no blind writes", seen from the
reader's side:

<!-- example: re-read-before-amending -->
```python
def amend_a_value_read_earlier(db: ScopedDatabase, customer: Customer, email: str) -> None:
    """Refused with ``WriteEvidenceError``: ``customer`` was read outside this transaction."""
    db.transact(lambda tx: tx.amend(customer.edit(email=email)))


def amend_after_reading_it_again(db: ScopedDatabase, customer_id: int, email: str) -> None:
    """Accepted: the read inside the transaction is what licenses the amendment."""

    def change_email(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.amend(customer.edit(email=email))

    db.transact(change_email)
```
<!-- /example -->

In the first function, `tx.amend` raises `WriteEvidenceError` before anything is
written; outside the callback it arrives as the `cause` of the `ExecutionFailure` that
[Getting started](01-getting-started.md#write-in-a-transaction) described. In the
second, the read inside the transaction licenses the amendment. `Customer` has no
version, so that read also takes a shared lock on the customer's row, which holds until
the transaction ends.

Sometimes you do need to write a value read earlier, such as one a user edited on a form.
If its entity carries a revision, a version or a Transaction-Time start, state the
revision the value carries with a [target write](04-writing.md#target-writes). It
applies only if the row still stands at that revision. An unversioned entity such as
`Customer` has no revision to state, so read it again inside the transaction.

### Several reads must agree

Two standalone reads can each see a different state of the database. Two reads in a
read-only transaction at Repeatable Read see the same one. `Customer.where(Customer.all)`
reads every customer; [Predicates, ordering and limits](#predicates-ordering-and-limits)
explains `all`.

<!-- example: reads-that-agree -->
```python
def customers_and_orders_one_read_at_a_time(
    db: ScopedDatabase,
) -> tuple[list[Customer], list[Order]]:
    """Two standalone reads: each one sees the database as it is when it runs."""
    customers = db.find(Customer.where(Customer.all)).results()
    orders = db.find(Order.where(Order.all)).results()
    return customers, orders


def customers_and_orders_from_one_snapshot(
    db: ScopedDatabase,
) -> tuple[list[Customer], list[Order]]:
    """Two reads of one snapshot, so every order's customer is in the list."""

    def read_both(rtx: ReadOnlyTxnContext) -> tuple[list[Customer], list[Order]]:
        customers = rtx.find(Customer.where(Customer.all)).results()
        orders = rtx.find(Order.where(Order.all)).results()
        return customers, orders

    return db.read_only(read_both, isolation="repeatable_read")
```
<!-- /example -->

If another transaction commits a new customer and their first order between the two
reads, the first function returns the order without its customer. The second returns
neither, because both of its reads see the database as it was when the transaction's
first read ran.

A read-only transaction offers reads and no writes. Its reads take no row locks and force
no flush, so it gets this agreement without making any writer wait. A `db.read_only` call
made inside its callback joins the same transaction instead of opening another, so a
helper that reads through `db.read_only` works on its own and inside a larger read-only
transaction:

<!-- example: join-a-read-only-transaction -->
```python
def orders_of(db: ScopedDatabase, customer_id: int) -> list[Order]:
    """Read in a read-only transaction of its own, or in the caller's when it has one."""
    return db.read_only(
        lambda rtx: rtx.find(Order.where(Order.customer_id == customer_id)).results()
    )


def customer_with_their_orders(
    db: ScopedDatabase, customer_id: int
) -> tuple[Customer, list[Order]]:
    """Both reads see one snapshot, because ``orders_of`` joins this transaction."""

    def read(rtx: ReadOnlyTxnContext) -> tuple[Customer, list[Order]]:
        customer = rtx.find(Customer.where(Customer.id == customer_id)).result()
        return customer, orders_of(db, customer_id)

    return db.read_only(read, isolation="repeatable_read")
```
<!-- /example -->

Called alone, `orders_of` opens its own read-only transaction. Called from
`customer_with_their_orders`, it joins that transaction and reads the same snapshot as
the customer. A `db.transact` call made inside a read-only callback is refused with
`TransactionAccessModeError` before its callback runs, and catching that refusal leaves
the read-only transaction usable. The reverse holds too: called from inside a
`db.transact` callback, `orders_of` raises `TransactionAccessModeError`, so a helper that both kinds of
caller use takes the context to read through as a parameter instead. [Transactions](05-transactions.md#running-a-transaction) covers
nesting in full, including what happens when a joined callback fails.

### Cost and contention

A read inside `transact` flushes the transaction's pending writes before it runs, and it
can take a shared lock on every row it reads. Those locks hold until the transaction
ends and make concurrent writers to those rows wait. So keep large reports out of
read-write transactions. A report that only reads belongs in standalone reads, or in
`read_only` when its reads must agree; neither takes row locks.

### Streams

A stream's lifetime depends on where it runs. A standalone stream can stay open as long
as you like, while one inside a transaction ends with the transaction attempt. And a
stream ordered by a column that a write can change can skip a row, or deliver it twice,
when that column changes underneath it, even when the write comes from your own loop.
[Eager and streaming delivery](#eager-and-streaming-delivery) explains both.

## Predicates, ordering and limits

A query starts from an entity class: `Entity.where(...)` takes one or more predicates
built from the class's attributes. It needs at least one, so a read of every row says so
with `Entity.where(Entity.all)`.

A predicate compares an attribute with a value. Several predicates passed to `where`
must all hold. To combine predicates yourself, use `&`, `|` and `~`, with parentheses;
Python's `and`, `or` and `not` can't build a predicate. `order_by` takes sort keys in
order of precedence, and `limit` caps the number of results:

<!-- example: filter-sort-and-limit -->
```python
def largest_orders_since(db: ScopedDatabase, since: dt.date, count: int) -> list[Order]:
    """The ``count`` largest orders placed on or after ``since``, largest first."""
    query = (
        Order.where(Order.placed_on >= since)
        .order_by(Order.total.desc(), Order.id.asc())
        .limit(count)
    )
    return db.find(query).results()


def customers_named(db: ScopedDatabase, prefix: str) -> list[Customer]:
    """Customers whose name starts with ``prefix`` and who have an email address."""
    query = Customer.where(Customer.name.starts_with(prefix) & Customer.email.is_not_null())
    return db.find(query).results()
```
<!-- /example -->

Besides `==`, `!=`, `<`, `<=`, `>` and `>=`, an attribute offers `between`, `in_` and
`not_in`, and a string attribute `starts_with`, `ends_with`, `contains`, `like` and
`not_like`, each of which takes `case_insensitive=True`. `like` and `not_like` take a
SQL pattern, in which `%` matches any run of characters and `_` any one character, with
no escaping; `starts_with`, `ends_with` and `contains` match their text literally, `%`
and `_` included. A boolean attribute is tested
with `.is_(True)` or `.is_(False)`. A nullable one is tested with `.is_null()` or
`.is_not_null()`; comparing with `None` raises `QueryDefinitionError` as you build the
query. The [Predicate](../../../../core/spec/m-predicate.md#predicate-set) contract
defines each operation.

Rows sort exactly as you ask, with nulls last unless a key says otherwise, as
`Customer.email.asc().nulls_first()` does; nothing is added to break ties. Without
`order_by`, `find` returns its results in no particular order, and `limit` returns some
of the matching rows, but which ones is unspecified. A stream and a history read are the
exceptions: they follow the primary key, as later sections show.
Parallax has no offset, so a limit is a cap rather than a way to page. To show results a
screen at a time, filter past the last key you showed, as in
`Order.where(Order.id > last_id).order_by(Order.id.asc()).limit(20)`. To work through a
large result in one go, stream it.

A to-many relationship is filtered with a quantifier: `.any(p)` matches when at least one
related object satisfies `p`, `.all(p)` when every one does, and `.none(p)` when none
does. A customer with no orders satisfies `.all(p)` and `.none(p)` but not `.any(p)`, and
bare `.any()` and `.none()` ask whether there are any orders at all. Don't confuse
`Customer.orders.all(p)`, a quantifier, with `Customer.all`, which matches every
customer.

The predicate inside a quantifier applies to one related object at a time. That is how
you ask for one order that is both recent and large, rather than a recent order and a
large one that may be different orders:

<!-- example: quantify-over-a-relationship -->
```python
def customers_with_a_large_recent_order(
    db: ScopedDatabase, since: dt.date, minimum: Decimal
) -> list[Customer]:
    """One order must be both recent and large: the quantifier tests each order alone."""
    query = Customer.where(
        Customer.orders.any((Order.placed_on >= since) & (Order.total >= minimum))
    )
    return db.find(query).results()


def customers_with_a_recent_order_and_a_large_one(
    db: ScopedDatabase, since: dt.date, minimum: Decimal
) -> list[Customer]:
    """Two quantifiers: the recent order and the large one can be different orders."""
    query = Customer.where(
        Customer.orders.any(Order.placed_on >= since),
        Customer.orders.any(Order.total >= minimum),
    )
    return db.find(query).results()
```
<!-- /example -->

Quantifiers work the same way over a list of value objects, such as an
`Attr[tuple[Address, ...]]`. A to-one relationship and a single value object use
`.exists()` and `.not_exists()` instead.

A query over an [inheritance family](02-modeling.md#inheritance-families) returns every
concrete subtype. `Payment.is_a(CardPayment)` matches only card payments, and its
`where=` can filter on a card payment's own attributes. It filters wherever it appears,
alone or beside other predicates, and the result keeps the family's type, `Payment`,
although each value arrives as its own concrete class. The `narrow` clause narrows the
result itself and types it as the subtype:

<!-- example: narrow-a-family-to-a-subtype -->
```python
def card_payments_ending_in(db: ScopedDatabase, last_four: str) -> list[Payment]:
    """Only card payments match, so the filter can use a card payment's own attribute."""
    query = Payment.where(Payment.is_a(CardPayment, where=CardPayment.card_last_four == last_four))
    return db.find(query).results()


def card_payments_over(db: ScopedDatabase, amount: Decimal) -> list[CardPayment]:
    """``narrow`` keeps card payments only and types the result as ``CardPayment``."""
    return db.find(Payment.where(Payment.amount > amount).narrow(CardPayment)).results()
```
<!-- /example -->

## Loading a graph

A read loads the relationships you name with `include`, and only those. Filtering on a
relationship and loading it are separate choices; this read does both:

<!-- example: filter-on-a-relationship -->
```python
def customers_with_an_order_over(db: ScopedDatabase, total: Decimal) -> list[Customer]:
    """Each matching customer arrives with all of its orders already loaded."""
    query = Customer.where(Customer.orders.any(Order.total > total)).include(Customer.orders)
    return db.find(query).results()
```
<!-- /example -->

The filter chooses the customers. The include then loads each one's orders, all of them,
not only those over the total. Parallax loads a graph with one statement per relationship
level, however many rows each level holds, so an include never turns into one query per
row.

`include` takes any number of paths, and calling it again adds more. An include path can run at most two relationships deep, and a
longer one raises `QueryDefinitionError` as you build the query. A path loads every
relationship along the way, so `include(Order.customer.orders)` loads each order's
customer as well as that customer's orders:

<!-- example: load-orders-with-their-customer -->
```python
def orders_with_their_customer(db: ScopedDatabase, since: dt.date) -> list[Order]:
    """Each order arrives with its customer, and that customer with all of its orders."""
    query = Order.where(Order.placed_on >= since).include(Order.customer.orders)
    return db.find(query).results()
```
<!-- /example -->

Each value `.results()` returns is a result root, the top of its own graph. Within one
root's graph, a row reached along two paths is one object. Each order here reaches
itself again through its customer, and `order.customer.orders` holds that same `order`
object, not a copy.

The sharing stops at the edge of each root. Two orders from the same customer each
come with their own `Customer` object: equal, but not the same object. So compare
values across roots by their keys, not with `is`.

Touching a relationship the read didn't include raises `UnloadedRelationshipError`. A
to-one relationship that was included but has no target is `None`, as for an order whose
`customer_id` matches no customer. `is_view_loaded(value, path)` tells the two apart
without raising:

<!-- example: tell-unloaded-from-empty -->
```python
def who_placed(order: Order) -> str:
    """Name an order's customer without risking ``UnloadedRelationshipError``."""
    if not is_view_loaded(order, Order.customer):
        return "not loaded"
    if order.customer is None:
        return "no customer"
    return order.customer.name
```
<!-- /example -->

## Result shapes

`find` returns a `Snapshot`, an envelope around the results. It isn't a list; you say
which shape you expect, and the envelope checks it. `.result()` takes exactly one result,
as in `look_up_a_customer` above, and raises `NoResultFound` or `TooManyResultsFound`
otherwise. The other two shapes allow for absence:

<!-- example: choose-a-result-shape -->
```python
def customer_with_email(db: ScopedDatabase, email: str) -> Customer | None:
    """At most one customer has this email; ``None`` when nobody does."""
    return db.find(Customer.where(Customer.email == email)).result_or_none()


def orders_placed_on(db: ScopedDatabase, day: dt.date) -> list[Order]:
    """Every order placed on ``day``, possibly none."""
    return db.find(Order.where(Order.placed_on == day)).results()
```
<!-- /example -->

`.result_or_none()` returns `None` for no result and still raises `TooManyResultsFound`
for several. `.results()` returns a new list each time you call it.

Stored data can contradict the model when something other than Parallax wrote it. Under
the Columns layout, the database's own column types and constraints guard each
attribute, and Parallax trusts them. A JSON column has no such guard, whether it holds a
value object or, under the Document layout, a whole entity, so Parallax checks what it
reads from one. `find` itself doesn't raise for a row that breaks the model. The
accessor you call does: `.result()`, `.result_or_none()` and `.results()` raise
`InvalidDataError` when a result they would return breaks it. When you would rather
handle such rows yourself, `checked()` hands them back as `InvalidData` records, in their
place among the results. A stream offers `checked()` too, and iterating what it returns
yields the same records in place:

<!-- example: read-rows-that-break-the-model -->
```python
def products_and_unreadable_rows(
    db: ScopedDatabase,
) -> tuple[list[Product], list[InvalidData[Product]]]:
    """Every product, with rows whose stored data breaks the model set aside."""
    readable: list[Product] = []
    unreadable: list[InvalidData[Product]] = []
    for item in db.find(Product.where(Product.all)).checked().results():
        if isinstance(item, InvalidData):
            unreadable.append(item)
        else:
            readable.append(item)
    return readable, unreadable
```
<!-- /example -->

A record's `issues` say what is wrong, and its `data` holds the value as far as Parallax
could build it without inventing anything, or `None` when it couldn't. Here, a product
document missing its `name` comes back with `data` set to `None`, because `name` isn't
optional. A value built from invalid data can't license a write; you author any
correction yourself.

## Eager and streaming delivery

`find` is eager: it reads the whole result before handing you any of it, and either
every result arrives or none does. That is the right default for anything that fits
comfortably in memory. `stream` delivers the same results one at a time, reading them a
page at a time, so the memory it holds doesn't grow with the number of results. Use it
for results too large to hold at once:

<!-- example: stream-a-large-result -->
```python
def total_of_every_order(db: ScopedDatabase, page: int) -> Decimal:
    """Add up every order while holding only one page of them at a time."""
    total = Decimal("0.00")
    with db.stream(Order.where(Order.all), batch_size=page) as orders:
        for order in orders:
            total += order.total
    return total
```
<!-- /example -->

A stream is a context manager, and you consume it inside its `with` block, once, in
order. It has no `.results()`. Keeping every value it hands you would rebuild the whole
result in memory; this loop keeps only a running total. It adds the totals up itself
because a query always returns whole entities: Parallax has no aggregates, grouping or
projections, and no way to run SQL you write. For a sum the database should compute, run
your own SQL on a connection of your own. `batch_size` sets how many
results each page reads, 1024 by default. It counts results, not their included
relationships, and it changes how many statements a stream issues, never which results
arrive or in what order.

While it runs, a stream holds the page it is working through and the result it last
handed you. A standalone stream borrows a connection only while it reads a page, so
between pages, and while your loop runs, it holds none, and other work can use the
connection. A stream inside a transaction uses the transaction's connection instead.

A stream ends when its results run out or when you leave the `with` block, whichever
comes first. Using it after that, entering it twice or iterating it twice raises
`StreamStateError`. If a page fails partway through, the results already delivered stay
delivered, and the failure is raised in place of the next one. A standalone stream
raises it as an `ExecutionFailure`, as a failing standalone read does. Inside a
transaction it is the page's own error, which `transact` wraps if you let it escape the
callback.

A stream inside a transaction can't outlive the transaction attempt. Each page of a
read-write stream flushes your pending writes before it reads, so a loop can stream rows
and amend them as it goes:

<!-- example: stream-and-amend-in-a-transaction -->
```python
def add_a_surcharge_to_every_order(db: ScopedDatabase, surcharge: Decimal, page: int) -> int:
    """Stream every order and amend each one, all in one transaction.

    The stream keeps its default order, the primary key, which no write can change,
    so no order is skipped or delivered twice.
    """

    def apply(tx: TxnContext) -> int:
        amended = 0
        with tx.stream(Order.where(Order.all), batch_size=page) as orders:
            for order in orders:
                tx.amend(order.edit(total=order.total + surcharge))
                amended += 1
        return amended

    return db.transact(apply)
```
<!-- /example -->

If the transaction is retried, Parallax runs the callback again, and the stream starts
again from the beginning. That is why `amended` is counted inside the callback. Anything
your loop does per result outside the database must be safe to repeat, like any other
effect inside a transaction.

A stream promises that each page is consistent within itself, and nothing more. Rows
change between pages, and what that does depends on where the change lands relative to
the stream's position, the last result it delivered:

| A concurrent change | Effect on the stream |
| -- | -- |
| A row inserted behind the position | Never delivered |
| A row inserted ahead of it | Delivered |
| A row deleted ahead of it | Never delivered |
| A row moved from ahead of the position to behind it | Skipped |
| A row moved from behind the position to ahead of it | Delivered twice |

A row can move only if the query orders by something a write can change. With no
`order_by`, a stream follows the primary key, which no write changes, so nothing can be
skipped or delivered twice. Order the surcharge stream by `Order.total` instead, and each
amended order moves ahead of the stream's position and comes round again. The writer that
moves a row can be your own loop.

Inside a transaction, the isolation level adds its own guarantees across pages, as the
[table above](#where-a-read-runs) shows. A shared row lock doesn't help here: it protects
rows already read, not rows the stream has yet to reach.

## Transaction-Time-Only reads

A `TxTemporal` entity keeps every state the database has held. `CreditLimit`, from
[Modeling](02-modeling.md#choosing-a-temporality-profile), is one. A read that doesn't
mention time answers what the database holds now:

<!-- example: read-the-latest-state -->
```python
def current_credit_limit(db: ScopedDatabase, customer_id: int) -> Decimal:
    """Without ``as_of``, a read answers what the database holds now."""
    return db.find(CreditLimit.where(CreditLimit.customer_id == customer_id)).result().amount
```
<!-- /example -->

`as_of(tx_time=...)` reads what the database held at an earlier instant:

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

Every instant you pass is a timezone-aware `datetime`; a naive one is refused as you
build the query. The current state is called `LATEST`, and it is what an omitted
`tx_time` means. It is not the same as the current clock time. An instant taken from the
clock is an ordinary finite instant, so a value read at it is read-only, like any value
read at a finite Transaction Time. To change a limit, read its latest state inside
`transact`.

`history(TX_TIME)` returns every state the database has held, each as its own value:

<!-- example: read-transaction-time-history -->
```python
def credit_limit_history(db: ScopedDatabase, customer_id: int) -> list[tuple[dt.datetime, Decimal]]:
    """Every limit the database has held for a customer, oldest first, with when it was set."""
    query = CreditLimit.where(CreditLimit.customer_id == customer_id).history(TX_TIME)
    return [(limit.tx_start, limit.amount) for limit in db.find(query).results()]
```
<!-- /example -->

Each of those states is a milestone. Its `tx_start` and `tx_end` say when the database
started and stopped holding it, and the current one has no end yet. History arrives in
primary-key order and, within one key, oldest first. `as_of_range(tx_time=(start, end))`
returns only the milestones the database held at some point in that range. Neither
history nor a range read can license a write.

A temporal read carries its instant through the whole graph it loads: a temporal entity
reached through an include is read at the same instant as the root. An entity reached
from one that doesn't keep a time axis is read at `LATEST` on that axis. So a Bitemporal
entity included from a Non-Temporal root is read at the latest Valid Time and the latest
Transaction Time, and needs no `as_of`.

## Bitemporal reads

A `Bitemporal` entity records two times: when a fact is true in the world, its Valid
Time, and when the database recorded it, its Transaction Time. The examples below read
`Price` for `TEA-1` after the first three transactions of the year that
[Writing](04-writing.md#bitemporal-entities) walks through. On 15 December 2023, the
database recorded a price of 10.00 from January onwards. On 15 February 2024, it recorded
a rise to 12.00 from April. On 1 May, it recorded the summer sale from
[Modeling](02-modeling.md#choosing-a-temporality-profile), 8.00 from June until
September:

```text
Valid Time →           Jan       Apr       Jun       Sep
recorded 15 Dec 2023   |------------------- 10.00 ------------------->
recorded 15 Feb 2024   |- 10.00 -|-------------- 12.00 -------------->
recorded 1 May 2024    |- 10.00 -|- 12.00 -|- 8.00 --|---- 12.00 ---->
```

A Bitemporal read must say which Valid Time it reads; there is no default. Transaction
Time still defaults to `LATEST`, what the database knows now. Pin both to ask what the
database believed at an earlier instant:

<!-- example: read-a-price-on-both-axes -->
```python
def price_on(db: ScopedDatabase, sku: str, day: dt.datetime) -> Decimal:
    """The price in effect on ``day``, as the database knows it now."""
    return db.find(Price.where(Price.sku == sku).as_of(valid_time=day)).result().amount


def price_on_as_recorded_at(
    db: ScopedDatabase, sku: str, day: dt.datetime, recorded_at: dt.datetime
) -> Decimal:
    """The price in effect on ``day``, as the database recorded it at ``recorded_at``."""
    query = Price.where(Price.sku == sku).as_of(valid_time=day, tx_time=recorded_at)
    return db.find(query).result().amount
```
<!-- /example -->

For a day in July, `price_on` answers 8.00. Asked as recorded in March,
`price_on_as_recorded_at` answers 12.00, because the database knew of the rise but not
yet of the sale; asked as recorded in January, it answers 10.00.

Valid Time has no default because "the latest Valid Time" is a claim about your business,
not about the database: it picks the fact whose window is still open, which may not be
the one in effect on the day you care about. You can still ask for that milestone
explicitly with `as_of(valid_time=LATEST)`. For `TEA-1` that answers 12.00, the price
whose window opens in September and has no end. When no window is open, as for a price
listed only until September, such as the summer blend that
[Writing](04-writing.md#insert-from-a-date) lists, nothing matches: `.result()` raises
`NoResultFound` and `.result_or_none()` returns `None`.

A range returns every milestone in effect at some point within it:

<!-- example: read-prices-over-a-valid-time-range -->
```python
def prices_during(
    db: ScopedDatabase, sku: str, start: dt.datetime, end: dt.datetime
) -> list[tuple[dt.datetime, Decimal]]:
    """Each price in effect at some point from ``start`` up to ``end``, with where it begins."""
    query = Price.where(Price.sku == sku).as_of_range(valid_time=(start, end))
    return [(price.valid_start, price.amount) for price in db.find(query).results()]
```
<!-- /example -->

From May to July, that is 12.00 from April and 8.00 from June. A range includes its
start and excludes its end, so one ending on 1 September leaves out the price that starts
then. `history(VALID_TIME)` returns every milestone on the Valid-Time axis, and
`history(TX_TIME).history(VALID_TIME)` scans both axes at once, returning every stored
row, which is what the timelines in Writing draw. As with Transaction-Time-Only history,
each milestone arrives as its own value, and none licenses a write.

A value read at a finite Valid Time and the latest Transaction Time stays writable:
[Writing](04-writing.md) uses one to correct a window of Valid Time.

## The Wire API

Wire is the second representation of a read. It returns immutable mappings in canonical
form instead of instances of your classes, ready to serialize or to hand to code that has
no entity classes. Every scope and transaction context has a `wire` with the same read
verbs, so `db.wire.find`, `db.wire.stream`, `rtx.wire.find` and `tx.wire.find` read
exactly where their Typed counterparts do.

A Wire read accepts the same Typed query:

<!-- example: read-through-wire -->
```python
def customers_with_an_order_over_as_wire(db: ScopedDatabase, total: Decimal) -> list[WireEntity]:
    """The same read, delivered as immutable mappings ready to serialize."""
    query = Customer.where(Customer.orders.any(Order.total > total)).include(Customer.orders)
    return db.wire.find(query).results()
```
<!-- /example -->

It also accepts a query document: the query a `where(...)` chain builds, an Object Query,
written as a plain mapping in Parallax's language-neutral form. Code that receives
queries from outside Python, or builds them as data, uses this form:

<!-- example: query-with-a-wire-document -->
```python
def customer_as_json(db: ScopedDatabase, customer_id: int) -> str:
    """Query with a Wire document and serialize what comes back."""
    document = {
        "target": "Customer",
        "predicate": {"eq": {"path": "Customer.id", "value": customer_id}},
        "includes": [{"segments": [{"rel": "Customer.orders"}]}],
    }
    return json.dumps(db.wire.find(document).result())
```
<!-- /example -->

A document names entities, attributes and relationships by their canonical names, and
every result uses the same names, so a Python `customer_id` is `customerId` in both. An
entity's canonical name is its class name, or the `name=` its class header gives, and a
class that declares `namespace=` adds it in front: `namespace="shop"` would make the
customer `shop.Customer`. Values take their canonical form too: a `Decimal` total
arrives as the string `"150.00"` and a date as `"2024-04-01"`. A `WireEntity` is an
immutable mapping that `json.dumps` accepts as it is, with included relationships nested
inside it. `target` names the entity, `predicate` the filter, and `includes` lists the
include paths: each path is a list of `segments`, one per relationship hop, and each
segment names its relationship under `rel`. So on a query whose target is `Order`, the
document form of `include(Order.customer.orders)` is
`{"segments": [{"rel": "Order.customer"}, {"rel": "Customer.orders"}]}`. The
[Object Query](../../../../core/spec/m-object-query.md) contract defines every clause,
and [predicates](../../../../core/spec/m-predicate.md) the filters.

`db.wire.stream` streams mappings, which suits an export that writes each value out as it
arrives:

<!-- example: export-customers-as-json-lines -->
```python
def export_customers(db: ScopedDatabase, out: TextIO, page: int) -> int:
    """Write each customer, with its orders, as one line of JSON; answer how many."""
    written = 0
    query = Customer.where(Customer.all).include(Customer.orders)
    with db.wire.stream(query, batch_size=page) as customers:
        for customer in customers:
            out.write(json.dumps(customer) + "\n")
            written += 1
    return written
```
<!-- /example -->

When you already hold a Typed result and some caller needs Wire data, project it with
`wire()` instead of reading again:

<!-- example: project-a-typed-result-as-wire -->
```python
def customer_for_page_and_api(db: ScopedDatabase, customer_id: int) -> tuple[Customer, WireEntity]:
    """One read: a Typed value to render, and the same graph as Wire data to send."""
    snapshot = db.find(Customer.where(Customer.id == customer_id).include(Customer.orders))
    return snapshot.result(), snapshot.wire().result()
```
<!-- /example -->

Projection runs in memory and keeps the relationships the read loaded. A Typed stream
offers the same for the result it has just handed you, with `stream.wire(value)`.

A Wire read follows the same rules as a Typed one everywhere else in this chapter: where
it runs, what it locks, and which values can license a write.
[Writing](04-writing.md#wire-writes) shows how to write through Wire, including a write
conditioned on the milestone a Wire read returned.

## How it works →

- [The read flow](../../../../docs/concepts/read-flow.md) follows a read from the query
  you author to the values you receive, in domain terms. The
  [Python read-flow architecture](../architecture/read-flow.md) maps the same path onto
  the implementation.
- [Execution](../../../../core/spec/m-execution.md#read-only-transactions) defines
  read-only transactions and the
  [conditions every read runs under](../../../../core/spec/m-execution.md#reads-under-an-attempt-or-a-scope).
  [Read locks](../../../../core/spec/m-read-lock.md) define when a read takes a shared
  lock, and the
  [unit of work](../../../../core/spec/m-unit-work.md#current-attempt-source-admission)
  defines which reads can license a write.
- The [database port](../../../../core/spec/m-db-port.md#the-portable-isolation-vocabulary)
  defines the isolation levels and
  [what PostgreSQL adds to them](../../../../core/spec/m-db-port.md#adapter-profile--nonportable-per-engine).
- [Object Query](../../../../core/spec/m-object-query.md) and
  [predicates](../../../../core/spec/m-predicate.md) define queries, and
  [snapshot reads](../../../../core/spec/m-snapshot-read.md) define the values a read
  returns, including identity within a result.
- [Read delivery](../../../../core/spec/m-read-delivery.md) defines eager and streamed
  delivery,
  [invalid stored data](../../../../core/spec/m-read-delivery.md#invalid-stored-data) and
  [what a stream promises under concurrent writes](../../../../core/spec/m-read-delivery.md#stability-under-concurrent-writing).
- [Temporal reads](../../../../core/spec/m-temporal-read.md) define the two time axes
  and their selections, and the [Wire codec](../../../../core/spec/m-wire.md) defines
  canonical values.
- The [Python queries and results binding](../../spec/queries-and-results.md) and the
  [Python execution binding](../../spec/execution.md) record the Python spellings.
