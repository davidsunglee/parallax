# Reading and querying

A read returns immutable values: frozen instances of your own entity classes, with the
relationships you asked for already loaded. Following one of those relationships never
runs another query. Building a query runs nothing either; the database is touched only
when you hand the query to `find` or `stream`.

This chapter starts with the question every read answers first, where it runs, and then
builds queries, loads graphs and chooses result shapes. After that it covers streaming
large results, reading history, and the Wire API, which delivers the same reads as plain
mappings. The examples use the shop model from [Modeling](02-modeling.md) unless they say
otherwise.

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
transaction and `db.transact(callback)` a read-write one; each hands its callback a
context whose `find` and `stream` read inside that transaction. Which of the three you
choose decides what a read sees, what it locks, and whether you can write what it
returned:

|  | Standalone: `db.find`, `db.stream` | Read-only: `db.read_only(...)` | Read-write: `db.transact(...)` |
| -- | -- | -- | -- |
| Transaction | None. Each read borrows its own connection, and a stream borrows one for each page | One read-only transaction, at the isolation level you choose | One read-write transaction |
| Do several reads agree? | No. Each read sees the database as it is when that read runs | Yes, at Repeatable Read or Serializable. On PostgreSQL, every read in the transaction sees one snapshot | It depends on the transaction's isolation level |
| Do a stream's pages agree? | No. Each page is consistent only within itself | At Repeatable Read, a row already delivered can't change value. The level still permits new matching rows to appear, but PostgreSQL's snapshot doesn't produce them | As for read-only, at the transaction's level |
| Row locks | None, even under a root that prefers locking | None, even for an entity without a version | A shared row lock wherever the entity's concurrency strategy is locking, which includes every unversioned Non-Temporal entity |
| Sees this transaction's pending writes | No. It reads outside every transaction | Nothing to see: a read-only transaction has no writes | Yes. The read flushes them first |
| Can the value license a later write? | No. Amending it raises `WriteEvidenceError`; state the revision it carries in a target write instead | No, as for a standalone read | Yes, while its evidence stays usable in the same attempt. History and range reads keep no write evidence, and a value read at a finite Transaction Time is read-only |
| Stream lifetime | Can stay open across pages, holding no connection between them | Ends with the transaction attempt | Ends with the transaction attempt |

Calling `db.find` inside a callback still makes a standalone read, on its own connection.
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
written; outside the callback it arrives as the `cause` of an `ExecutionFailure`. In the
second, the read inside the transaction licenses the amendment. `Customer` has no
version, so that read also takes a shared lock on the customer's row, which holds until
the transaction ends.

Sometimes you do need to write a value read earlier, such as one a user edited on a form.
Then state the revision the value carries with a
[target write](04-writing.md#target-writes). It applies only if the row still stands at
that revision.

### Several reads must agree

Two standalone reads can each see a different state of the database. Two reads in a
read-only transaction at Repeatable Read see the same one:

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
no flush, so it gets this agreement without making any writer wait. A `read_only` call
made inside it joins the same transaction, and a `transact` call is refused with
`TransactionAccessModeError`. This example, from Parallax's conformance suite, shows all
three:

<!-- example: m-execution-002 -->
```python
@dataclass(frozen=True, slots=True)
class ReadOnlyReport:
    """What the read-only callback observed, and how its joins were treated."""

    options: ReadOnlyTxnOptions
    balance: Decimal
    reread_balance: Decimal
    read_only_join_shared_the_context: bool
    writable_join_refused: bool


def reads_run_in_one_read_only_transaction_at_a_chosen_isolation(
    adapter: DatabaseAdapter, model: DomainModel
) -> ReadOnlyReport:
    """Two reads of one account inside one read-only transaction at Repeatable
    Read, so both observe the transaction's one snapshot.

    ``adapter`` is the shipped adapter's configuration for the story database,
    which holds the seeded account row. ``db.read_only`` opens a native
    read-only transaction at the isolation it names and hands the callback a
    context with reads and no writes; its reads take no shared row lock. A
    read-only call made inside it joins the same transaction, while a writable
    call is refused before its callback runs and, once caught, leaves the
    read-only transaction usable.
    """
    with connect(adapter, model) as database:
        db = database.using_database_login()

        def report(rtx: ReadOnlyTxnContext) -> ReadOnlyReport:
            query = Account.where(Account.id == _TARGET_ID)
            balance = rtx.find(query).result().balance
            joined = db.read_only(lambda joined_rtx: joined_rtx is rtx)
            refused = False
            try:
                db.transact(lambda tx: tx.find(query).result())
            except TransactionAccessModeError:
                refused = True
            return ReadOnlyReport(
                options=rtx.options,
                balance=balance,
                reread_balance=rtx.find(query).result().balance,
                read_only_join_shared_the_context=joined,
                writable_join_refused=refused,
            )

        return db.read_only(report, isolation="repeatable_read")
```
<!-- /example -->

[Transactions](05-transactions.md) explains the isolation levels and how a transaction's
options are chosen.

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
with `Entity.where(Entity.all)`. The examples in this section come from Parallax's
conformance suite, whose models differ from the shop's: its `Order` has `qty` and
`active` attributes and a to-many `items` relationship.

The simplest predicate compares an attribute with a value:

<!-- example: m-predicate-002 -->
```python
query = Order.where(Order.id == 42)
```
<!-- /example -->

Several predicates passed to `where` must all hold. To combine predicates yourself, use
`&`, `|` and `~`, with parentheses; Python's `and`, `or` and `not` can't build a
predicate. A boolean attribute is tested with `.is_(True)` or `.is_(False)`, and a
nullable one with `.is_null()` or `.is_not_null()`, never by comparing with `None`:

<!-- example: m-predicate-020 -->
```python
query = Order.where(Order.active.is_(True), Order.qty > 10)
```
<!-- /example -->

`order_by` takes sort keys in order of precedence, and `limit` caps the number of
results:

<!-- example: m-object-query-003 -->
```python
query = Order.where(Order.all).order_by(Order.active.desc(), Order.qty.asc()).limit(2)
```
<!-- /example -->

Rows sort exactly as you ask, with nulls last unless a key says otherwise; nothing is
added to break ties. Without `order_by`, `limit` returns some of the matching rows, but
which ones is unspecified, so a limit is a cap rather than a way to page through results.
To work through a large result, stream it.

A to-many relationship is filtered with a quantifier: `.any(p)` matches when at least one
related object satisfies `p`, `.all(p)` when every one does, and `.none(p)` when none
does. The README's `Customer.orders.any(Order.total > total)` is one; here is another:

<!-- example: m-navigate-004 -->
```python
query = Order.where(Order.items.any(OrderItem.quantity >= 4))
```
<!-- /example -->

The predicate inside a quantifier applies to one element at a time. That is how you ask
for one element that satisfies two conditions together, here a home phone with this
number, rather than any home phone and any phone with this number:

<!-- example: m-value-object-019 -->
```python
def customer_to_many_scoped_exists_requires_one_element_to_satisfy_both(
    db: ScopedDatabase,
) -> Snapshot[Any]:
    return db.find(
        Customer.where(
            Customer.address.phones.any(
                (CustomerPhone.type == "home") & (CustomerPhone.number == "555-9999")
            )
        )
    )
```
<!-- /example -->

A to-one relationship and a single value object use `.exists()` and `.not_exists()`
instead.

A query over an [inheritance family](02-modeling.md#inheritance-families) returns every
concrete subtype. When `is_a` is the whole filter, it narrows the result to the subtypes
it names, and its `where` can then filter on their own attributes:

<!-- example: m-inheritance-012 -->
```python
query = Animal.where(Animal.is_a(Dog, where=Dog.bark_volume > 3))
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

An include path can run two relationships deep:

<!-- example: load-orders-with-their-customer -->
```python
def orders_with_their_customer(db: ScopedDatabase, since: dt.date) -> list[Order]:
    """Each order arrives with its customer, and that customer with all of its orders."""
    query = Order.where(Order.placed_on >= since).include(Order.customer.orders)
    return db.find(query).results()
```
<!-- /example -->

Within one result, a row reached along two paths is one object. Each order here reaches
itself again through its customer, and `order.customer.orders` holds that same `order`
object, not a copy.

The sharing stops at the edge of each result. Two orders from the same customer each
come with their own `Customer` object: equal, but not the same object. So compare
results across roots by their keys, not with `is`.

Touching a relationship the read didn't include raises `UnloadedRelationshipError`. A
to-one relationship that was included but has no target is `None`. Use
`is_view_loaded` to tell the two apart without raising. This example comes from the
conformance suite, where an `OrderStatus` belongs to an order and optionally to one of
its items:

<!-- example: read-optional-relationships -->
```python
class OrderStatus(
    Entity,
    table="order_status",
    namespace=_NS,
    indices=(index("order_status_order_id", "order_id"),),
):
    """Mirror of the ``OrderStatus`` entity of ``models/orders.yaml``: each
    status belongs to an ``Order`` and OPTIONALLY to a specific ``OrderItem``
    (a nullable many-to-one — the to-one navigate/deep-fetch nullable shape)."""

    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    order_item_id: Attr[int | None]
    code: Attr[str] = attr(max_length=16)
    order: Rel[Order | None] = rel(reverse_of="statuses")
    order_item: Rel[OrderItem | None] = rel(reverse_of="statuses")


def read_to_one_relationship_states(db: ScopedDatabase) -> tuple[Snapshot[Any], Snapshot[Any]]:
    """Use is_view_loaded to distinguish an omitted relationship from a loaded null."""
    included = db.find(
        OrderStatus.where(OrderStatus.all).include(OrderStatus.order, OrderStatus.order_item)
    )
    return included, db.find(OrderStatus.where(OrderStatus.all))
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
the Columns layout, the database's own column types and constraints guard each value,
and Parallax trusts them. A JSON document column has no such guard, so Parallax checks
what it reads from one. By default, an accessor raises `InvalidDataError` when a result
it returns breaks the model. When you would rather handle such rows yourself, `checked()`
hands them back as `InvalidData` records, in their place among the results:

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

<!-- example: stream-results -->
```python
def stream_a_result_one_root_at_a_time(db: ScopedDatabase, page: int) -> tuple[int, list[str]]:
    """Summing keeps bounded application state; collecting names retains every name.

    Consume the stream inside its scope. Page size counts roots, not their included
    children.
    """
    quantity = 0
    with db.stream(Order.where(Order.all).include(Order.items), batch_size=page) as orders:
        for order in orders:
            quantity += sum(item.quantity for item in order.items)

    names: list[str] = []
    with db.wire.stream(Order.where(Order.all), batch_size=page) as rows:
        for row in rows:
            names.append(str(row["name"]))
    return quantity, names
```
<!-- /example -->

A stream is a context manager, and you consume it inside its `with` block, once, in
order. It has no `.results()`. Keeping every value it hands you rebuilds the whole result
in memory: the first loop avoids that by keeping a running sum, and the second, which
collects every name, doesn't. `batch_size` sets how many results each page reads, 1024 by
default. It counts results, not their included relationships, and it changes how many
statements a stream issues, never which results arrive or in what order.

While it runs, a stream holds the page it is working through and the result it last
handed you. A standalone stream borrows a connection only while it reads a page, so
between pages, and while your loop runs, it holds none, and other work can use the
connection. A stream inside a transaction uses the transaction's connection instead.

A stream ends when its results run out or when you leave the `with` block, whichever
comes first. Using it after that, entering it twice or iterating it twice raises
`StreamStateError`. If a page fails partway through, the results already delivered stay
delivered, and the failure is raised in place of the next one.

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

The current state is called `LATEST`, and it is what an omitted `tx_time` means. It is
not the same as the current clock time. An instant taken from the clock is an ordinary
finite instant, so a value read at it is read-only, like any value read at a finite
Transaction Time. To change a limit, read its latest state inside `transact`.

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
reached through an include is read at the same instant as the root.

## Bitemporal reads

A `Bitemporal` entity records two times: when a fact is true in the world, its Valid
Time, and when the database recorded it, its Transaction Time. The examples below read
`Price` after two transactions. In January, the database recorded a price of 10.00 from
January onwards. In May, it recorded the summer sale from
[Modeling](02-modeling.md#choosing-a-temporality-profile), 8.00 from June until
September:

```text
Valid Time →          Jan          Jun          Sep
recorded in January   |---------------- 10.00 ---------------->
recorded in May       |--- 10.00 ---|--- 8.00 ---|--- 10.00 -->
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
`price_on_as_recorded_at` answers 10.00, because the database hadn't heard of the sale
yet.

Valid Time has no default because "the latest Valid Time" is a claim about your business,
not about the database: it picks the fact whose window is still open, which may not be
the one in effect on the day you care about. You can still ask for that milestone
explicitly with `as_of(valid_time=LATEST)`.

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

From May to July, that is 10.00 from January and 8.00 from June. A range includes its
start and excludes its end, so one ending on 1 September leaves out the price that starts
then. `history(VALID_TIME)` returns every milestone on the Valid-Time axis, and a read can
scan both axes at once. As with Transaction-Time-Only history, each milestone arrives as
its own value, and none licenses a write.

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

It also accepts a query document: the canonical form of an Object Query, as a plain
mapping. Code that receives queries from outside Python, or builds them as data, uses
this form:

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
every result uses the same names, so a Python `customer_id` is `customerId` in both.
Values take their canonical form too: a `Decimal` total arrives as the string `"150.00"`
and a date as `"2024-04-01"`. A `WireEntity` is an immutable mapping that `json.dumps`
accepts as it is, with included relationships nested inside it. The
[Object Query](../../../../core/spec/m-object-query.md) contract defines the document's
clauses, and [predicates](../../../../core/spec/m-predicate.md) its filters.

When you already hold a Typed result and some caller needs Wire data, project it with
`wire()` instead of reading again:

<!-- example: publish-typed-result-as-wire -->
```python
class Account(
    Entity,
    table="account",
    namespace=_NS,
    indices=(index("account_owner", "owner"),),
):
    """Mirror of ``models/account.yaml``."""

    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str] = attr(max_length=64)
    balance: Attr[Decimal] = attr(precision=18, scale=2)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


def publish_typed_read_as_wire(db: ScopedDatabase) -> Snapshot[Any]:
    """Project an existing Typed result without another read.

    Use db.wire.find directly when no caller needs Typed values.
    """
    typed = db.find(Account.where(Account.id == 1))
    return typed.wire()
```
<!-- /example -->

Projection runs in memory and keeps the relationships the read loaded. A Typed stream
offers the same for the result it has just handed you, with `stream.wire(value)`.

A Wire read follows the same rules as a Typed one everywhere else in this chapter: where
it runs, what it locks, and which values can license a write. `edge_of(node)` tells you
where a temporal Wire node's milestone starts, and
[Writing](04-writing.md#wire-writes) shows how to write through Wire, including a write
conditioned on that milestone.

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
