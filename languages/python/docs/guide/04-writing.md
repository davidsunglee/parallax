# Writing

Writes run inside a transaction, through the context `db.transact` hands its callback.
The values a read returns are immutable, so nothing is written by changing an object.
Instead you tell the transaction what to do: insert a new value, amend or replace an
edited copy of one you read, or delete it. The transaction's unit of work buffers those
writes, combines writes to the same object, batches them, and orders them around their
dependencies. It sends them when a read needs them, when a predicate write runs, or when
the transaction commits, and they all commit together or not at all.

Parallax refuses blind writes. A write to an object that already exists needs a licence,
something that shows what the write applies to:

- a read of that object in the same transaction attempt;
- the attempt's own insertion of it; or
- a revision you state yourself, in a [target write](#target-writes).

[Predicate writes](#predicate-writes) are the one exception. They change every row a
query selects without reading it first, and only entities with no version and no history
accept them.

This chapter starts with the simplest temporality profile and adds time one axis at a
time: Non-Temporal entities, then Transaction-Time-Only, then Bitemporal. After that it
covers target writes, predicate writes and writing through Wire. The examples use the
shop model from [Modeling](02-modeling.md) and these imports:

<!-- example: writing-imports -->
```python
import datetime as dt
import json
from decimal import Decimal

from parallax.core import LATEST, Attr, Bitemporal, Edge, TxTemporal, attr
from parallax.core.execution import ExecutionFailure, TransactionTimePinReadOnlyError
from parallax.core.unit_work import (
    InstructionRejectedError,
    WriteEvidenceError,
    WritePreconditionError,
)
from parallax.snapshot import ScopedDatabase, TxnContext, WireEntity, edge_of
```
<!-- /example -->

## Non-Temporal entities

### Insert, then read your own write

`tx.insert` takes a new instance:

<!-- example: insert-and-read-your-own-write -->
```python
def register_a_customer(db: ScopedDatabase, customer_id: int, name: str) -> Customer:
    """Insert a customer, then read it back before the transaction commits."""

    def register(tx: TxnContext) -> Customer:
        tx.insert(Customer(id=customer_id, name=name, email=None))
        return tx.find(Customer.where(Customer.id == customer_id)).result()

    return db.transact(register)
```
<!-- /example -->

The insert waits in the transaction's buffer. The `find` after it needs the new customer,
so the transaction flushes the insert first, and the read sees it. A flushed write is
still inside the transaction: if the callback raises, or the commit fails, the insert is
discarded like everything else the transaction did.

The instance you inserted carries a licence of its own for the rest of the attempt. You
can amend or delete it, or an edited copy of it, without reading it back.

### Amend or replace an edited value

To change an object, read it inside the transaction, edit a copy, and hand the copy to
`amend` or `replace`:

<!-- example: amend-or-replace-an-edited-value -->
```python
def change_an_email(db: ScopedDatabase, customer_id: int, email: str) -> None:
    """Write the members ``edit`` changed; every other member keeps its stored value."""

    def change(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.amend(customer.edit(email=email))

    db.transact(change)


def replace_contact_details(db: ScopedDatabase, customer_id: int, name: str) -> None:
    """Write every writable member the value holds, the unedited email included."""

    def rewrite(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.replace(customer.edit(name=name))

    db.transact(rewrite)
```
<!-- /example -->

`edit(...)` returns a copy with the members you name changed, and leaves the value you
read as it was. `amend` writes the members the copy's edits touched, and every other
member keeps its stored value. `replace` writes the copy's whole writable state, edited
or not, so the second function writes `email` too.

For a value read in the same transaction, the two end in the same stored state, because
the members you didn't edit already hold their stored values. `replace` matters when the
state comes from somewhere else. A Wire document or a target write's payload states a
whole state, and `replace` completes any member it leaves out: a nullable member is
written as null, a list as empty, and a required member left out is refused. Over a
window of Valid Time, `replace` also fills Valid Time that nothing covered, as
[Bitemporal entities](#bitemporal-entities) shows.

When the new value is computed from the old one, you can pass `Attr.set(...)`
assignments beside the value you read instead of editing it:

<!-- example: amend-with-an-assignment -->
```python
def add_to_an_order(db: ScopedDatabase, order_id: int, amount: Decimal) -> None:
    """Amend with an assignment computed from the value just read."""

    def add(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == order_id)).result()
        tx.amend(order, Order.total.set(order.total + amount))

    db.transact(add)
```
<!-- /example -->

The two forms don't mix: a value with edits takes no assignments.

### Delete a value you read

`delete` removes the row of a value read in the transaction:

<!-- example: delete-a-value-you-read -->
```python
def cancel_an_order(db: ScopedDatabase, order_id: int) -> None:
    """Delete an order this transaction read."""

    def cancel(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == order_id)).result()
        tx.delete(order)

    db.transact(cancel)
```
<!-- /example -->

`delete` physically removes the row, so only Non-Temporal entities accept it. A temporal
entity keeps its history instead, and you end its current state with `terminate`.

### Locks and versions

Every example above reads before it writes, and that read is the write's licence. What
else the read does depends on whether the entity has a version.

`Customer` has none, so nothing in a customer's row shows whether it changed. Its read
takes a shared lock on the row instead, and the lock holds until the transaction ends.
Until then, other transactions can still read the customer but can't change it, so the
row your write applies to is the row you read.

`Order` declares a `version`. Its read takes no lock; it records the version it saw, and
the write applies only if the order still has that version. Parallax sets the version
to 1 on insert and advances it on every write, so after `add_to_an_order` the order's
version is 2. If another transaction changed the order between your read and your write,
the write conflicts, and Parallax rolls the transaction back and runs your callback
again against fresh reads. A transaction can also prefer the locking strategy for
versioned entities, with `db.transact(callback, concurrency="locking")`.
[Transactions](05-transactions.md) explains that replay and that choice.

A value read outside the transaction licenses nothing, whichever kind of entity it
belongs to. [Reading](03-reading.md#youll-write-what-you-read) shows the refusal, and
[target writes](#target-writes) show how to write such a value when it has a revision.

## Transaction-Time-Only entities

A `TxTemporal` entity, such as `CreditLimit`, keeps every state it has held. An insert
opens its first milestone. After that, a write never changes a committed milestone's
values: it closes the current milestone at the transaction's instant and chains what
follows it.

The transaction's instant is one timestamp per attempt, taken from the clock of the
process running Parallax, not the database's, when the attempt first sends a write that
needs it. Every row the attempt closes or opens uses that instant, and a retry takes a
fresh one.

<!-- example: change-a-credit-limit -->
```python
class CreditLimit(TxTemporal, table="credit_limit"):
    customer_id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=12, scale=2)


def grant_a_credit_limit(db: ScopedDatabase, customer_id: int, amount: Decimal) -> None:
    """Open the first milestone of a customer's limit."""
    db.transact(lambda tx: tx.insert(CreditLimit(customer_id=customer_id, amount=amount)))


def change_a_credit_limit(db: ScopedDatabase, customer_id: int, amount: Decimal) -> None:
    """Close the current milestone and chain a new one; the old limit stays in history."""

    def change(tx: TxnContext) -> None:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == customer_id)).result()
        tx.amend(limit.edit(amount=amount))

    db.transact(change)
```
<!-- /example -->

Suppose the limit is granted by a transaction on 15 December 2023 and changed by one on
10 January 2024. The table then holds two rows, one for each milestone:

```text
amount      tx_start      tx_end
1000.00     15 Dec 2023   10 Jan 2024
2500.00     10 Jan 2024   ∞
```

The amendment closed the first milestone by setting its `tx_end`, and chained the
second, which is current: its `tx_end` is open, shown as ∞. The first milestone's
values are untouched. `replace` chains the same way, with a successor that states the
whole writable state. No write ever edits a closed milestone, which is what makes a read
of the past stable. Two amendments of one limit in the same transaction still add only
one milestone: the second revises the milestone the first opened, which no other
transaction has seen.

`terminate` closes the current milestone and chains nothing after it:

<!-- example: withdraw-a-credit-limit -->
```python
def withdraw_a_credit_limit(db: ScopedDatabase, customer_id: int) -> None:
    """Close the current milestone and chain nothing after it."""

    def withdraw(tx: TxnContext) -> None:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == customer_id)).result()
        tx.terminate(limit)

    db.transact(withdraw)
```
<!-- /example -->

After a withdrawal on 15 February 2024, no milestone is current:

```text
amount      tx_start      tx_end
1000.00     15 Dec 2023   10 Jan 2024
2500.00     10 Jan 2024   15 Feb 2024
```

A read of the latest state now finds no limit, while a read as of 1 February still
answers 2500.00, and history still lists both milestones. Inserting a limit for the same
customer later opens a new current milestone after them. `tx.delete` is refused for a
temporal entity, because it would remove rows; the error names `terminate` instead.

## Bitemporal entities

Every Bitemporal write applies to a stretch of Valid Time. Transaction Time is not yours
to choose: every row a write closes ends at the transaction's instant, and every row it
opens starts there. So every row a write reaches stays in place, closed in Transaction
Time, and the Valid Time the write didn't reach keeps its price.

This section follows one price list through a year, using `Price` from
[Modeling](02-modeling.md#choosing-a-temporality-profile). Suppose its transactions
commit on the dates the `tx_start` column shows. Each picture lists every stored row of
one product: its amount, the Valid Time it covers, from `|` up to the next `|` or onwards
for `--->`, and its `tx_start` and `tx_end`. A row whose `tx_end` is ∞ is current.

### Insert from a date

A Bitemporal insert requires `valid_from`, where the price starts to apply; an insert
without one is refused. With `until` as well, it applies up to that instant and not
after:

<!-- example: list-a-price -->
```python
class Price(Bitemporal, table="price"):
    sku: Attr[str] = attr(primary_key=True, max_length=20)
    amount: Attr[Decimal] = attr(precision=12, scale=2)


def list_a_tea(db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime) -> None:
    """Open a price from ``start``, with no end."""
    db.transact(lambda tx: tx.insert(Price(sku=sku, amount=amount), valid_from=start))


def list_a_seasonal_tea(
    db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime, end: dt.datetime
) -> None:
    """Open a price from ``start`` up to, but not including, ``end``."""
    db.transact(lambda tx: tx.insert(Price(sku=sku, amount=amount), valid_from=start, until=end))
```
<!-- /example -->

`TEA-1`, listed at 10.00 from January, has one row, open on both axes:

```text
            Jan         Apr     Jun         Sep         Dec         tx_start      tx_end
10.00       |--------------------------------------------------->   15 Dec 2023   ∞
```

`TEA-2`, a summer blend listed at 6.00 from June until September, covers only that
window. `until` is excluded, so the blend has no price from 1 September:

```text
                                Jun         Sep                     tx_start      tx_end
6.00                            |-----------|                       10 Jan 2024   ∞
```

### Amend from a date onwards

An amendment starts where its source was read, at the Valid Time the `find` asked for,
and applies from there onwards:

<!-- example: amend-a-price-from-a-date -->
```python
def change_a_price_from(db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime) -> None:
    """Change a price from ``start`` onwards; earlier Valid Time keeps the old price."""

    def change(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == sku).as_of(valid_time=start)).result()
        tx.amend(price.edit(amount=amount))

    db.transact(change)
```
<!-- /example -->

Raising `TEA-1` to 12.00 from April closes the January row in Transaction Time and opens
two in its place, the old price up to April and the new one after it. Without `until`,
an amendment reaches every row from its start onwards, including any later window
already stored, and each of them takes the new values while keeping the members the
write doesn't assign. Here there is only the one row:

```text
            Jan         Apr     Jun         Sep         Dec         tx_start      tx_end
10.00       |--------------------------------------------------->   15 Dec 2023   15 Feb 2024
10.00       |-----------|                                           15 Feb 2024   ∞
12.00                   |--------------------------------------->   15 Feb 2024   ∞
```

The closed row still answers a read at an earlier Transaction Time: asked as recorded
in January, the price for May is 10.00. Because the write starts where its source was
read, a Bitemporal source must be read at a finite Valid Time. A value read at
`valid_time=LATEST` names no instant, and amending it is refused.

### Amend a window

With `until`, an amendment changes a window of Valid Time and leaves the time after it
alone. This is the summer sale from Modeling:

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

The sale reaches only the row from April, which splits into three: 12.00 before the
window, 8.00 inside it, and 12.00 again after it. The January to April row is outside
the window and stays as it was:

```text
            Jan         Apr     Jun         Sep         Dec         tx_start      tx_end
10.00       |--------------------------------------------------->   15 Dec 2023   15 Feb 2024
10.00       |-----------|                                           15 Feb 2024   ∞
12.00                   |--------------------------------------->   15 Feb 2024   1 May 2024
12.00                   |-------|                                   1 May 2024    ∞
8.00                            |-----------|                       1 May 2024    ∞
12.00                                       |------------------->   1 May 2024    ∞
```

A window can reach several rows. Each row it reaches is closed and reopened in pieces,
and the pieces inside the window take the new values while keeping every member the
write doesn't assign.

### Replace over a window

`replace` makes its state the whole state over its window, including where nothing was
covered before:

<!-- example: replace-a-price-over-a-window -->
```python
def reprice_a_tea_for(
    db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime, end: dt.datetime
) -> None:
    """Make ``amount`` the whole state from ``start`` up to ``end``, gaps included."""

    def reprice(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == sku).as_of(valid_time=start)).result()
        tx.replace(price.edit(amount=amount), until=end)

    db.transact(reprice)
```
<!-- /example -->

In June, the summer blend is repriced to 7.00 from July and extended to October:

```text
                                Jun Jul     Sep Oct                 tx_start      tx_end
6.00                            |-----------|                       10 Jan 2024   20 Jun 2024
6.00                            |---|                               20 Jun 2024   ∞
7.00                                |-----------|                   20 Jun 2024   ∞
```

The replacement covers September, which had no price, and stores July to October as one
row, because its pieces hold the same state. An amendment over the same window changes
only what is already covered, so it would leave September without a price:

```text
                                Jun Jul     Sep Oct                 tx_start      tx_end
6.00                            |-----------|                       10 Jan 2024   20 Jun 2024
6.00                            |---|                               20 Jun 2024   ∞
7.00                                |-------|                       20 Jun 2024   ∞
```

A replacement still needs a licence, here the read at July. It can't create a product
that has no row where it starts, so it is never an insert in disguise.

### Terminate

`terminate` ends a price from the Valid Time its source was read at:

<!-- example: terminate-a-price -->
```python
def discontinue_a_tea(db: ScopedDatabase, sku: str, day: dt.datetime) -> None:
    """End a price from ``day`` onwards; earlier Valid Time keeps it."""

    def discontinue(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == sku).as_of(valid_time=day)).result()
        tx.terminate(price)

    db.transact(discontinue)
```
<!-- /example -->

`TEA-1` is discontinued from December. The row from September closes, and its piece
before December reopens:

```text
            Jan         Apr     Jun         Sep         Dec         tx_start      tx_end
10.00       |--------------------------------------------------->   15 Dec 2023   15 Feb 2024
10.00       |-----------|                                           15 Feb 2024   ∞
12.00                   |--------------------------------------->   15 Feb 2024   1 May 2024
12.00                   |-------|                                   1 May 2024    ∞
8.00                            |-----------|                       1 May 2024    ∞
12.00                                       |------------------->   1 May 2024    1 Nov 2024
12.00                                       |-----------|           1 Nov 2024    ∞
```

From December, a read finds no price for `TEA-1`. Every earlier month keeps its price,
and every earlier row stays on record. `terminate` takes `until` too, which ends the
price only inside that window.

### Correct the past

In November, you find that `TEA-1` should have cost 9.50 from January to April. A
correction is an ordinary write whose Valid Time has already passed:

<!-- example: correct-a-past-price -->
```python
def correct_a_past_price(
    db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime, end: dt.datetime
) -> None:
    """Correct a window of Valid Time that has already passed."""

    def correct(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == sku).as_of(valid_time=start)).result()
        tx.amend(price.edit(amount=amount), until=end)

    db.transact(correct)


def correct_a_price_as_recorded_then(
    db: ScopedDatabase,
    sku: str,
    amount: Decimal,
    start: dt.datetime,
    end: dt.datetime,
    recorded_at: dt.datetime,
) -> None:
    """Refused with ``TransactionTimePinReadOnlyError``: the value was read at a past
    Transaction Time."""

    def correct(tx: TxnContext) -> None:
        query = Price.where(Price.sku == sku).as_of(valid_time=start, tx_time=recorded_at)
        price = tx.find(query).result()
        tx.amend(price.edit(amount=amount), until=end)

    db.transact(correct)
```
<!-- /example -->

The first function closes the January to April row and opens the corrected one. Its
Transaction Time is still the moment the correction commits:

```text
            Jan         Apr     Jun         Sep         Dec         tx_start      tx_end
10.00       |--------------------------------------------------->   15 Dec 2023   15 Feb 2024
10.00       |-----------|                                           15 Feb 2024   15 Nov 2024
9.50        |-----------|                                           15 Nov 2024   ∞
12.00                   |--------------------------------------->   15 Feb 2024   1 May 2024
12.00                   |-------|                                   1 May 2024    ∞
8.00                            |-----------|                       1 May 2024    ∞
12.00                                       |------------------->   1 May 2024    1 Nov 2024
12.00                                       |-----------|           1 Nov 2024    ∞
```

Now the price for February is 9.50. Asked as recorded on 1 November, it is still 10.00,
because that is what the database held then.

The second function is refused. Its source was read at a finite Transaction Time, and a
value read there is read-only: amending it raises `TransactionTimePinReadOnlyError`,
which reaches the caller as the `cause` of an `ExecutionFailure`. A correction always
starts from what the database knows now and appends to it. What the database knew at an
earlier instant never changes.

## Target writes

A value from a standalone or read-only read can't license `amend`: amending it raises
`WriteEvidenceError`, as
[You'll write what you read](03-reading.md#youll-write-what-you-read) showed. One way to
write it is to read it again inside `transact`. The other is a target write: `amend_if`,
`replace_if`, `delete_if` or `terminate_if`. A target write names the object by its
entity and key, and states the revision the value showed: its `version` for a versioned
entity, or its `tx_start` for a temporal one. It applies only if the object still stands
at that revision.

Here a user reviewed an order or a credit limit on a page, which a standalone read
filled, and then confirmed a change:

<!-- example: amend-what-a-review-showed -->
```python
def change_a_reviewed_total(db: ScopedDatabase, reviewed: Order, total: Decimal) -> None:
    """``reviewed`` came from an earlier read: state the version it showed."""
    db.transact(
        lambda tx: tx.amend_if(
            Order, Order.total.set(total), key=reviewed.id, version=reviewed.version
        )
    )


def change_a_reviewed_limit(db: ScopedDatabase, reviewed: CreditLimit, amount: Decimal) -> None:
    """A temporal entity states where the milestone it showed starts in Transaction Time."""
    db.transact(
        lambda tx: tx.amend_if(
            CreditLimit,
            CreditLimit.amount.set(amount),
            key=reviewed.customer_id,
            tx_start=reviewed.tx_start,
        )
    )
```
<!-- /example -->

The stated revision is the write's condition. If the object has moved on since the
review, the write fails with `WritePreconditionError`. Under the default optimistic
strategy it is raised when the transaction flushes, typically at commit; when the
transaction prefers locking, it is raised at the call. That failure is never retried,
because running the callback again would state the same revision again. A revision the
transaction observed through its own read is different: when that one moves, Parallax
can read again and retry. [Transactions](05-transactions.md) explains which failures are
retried.

`key=` takes the object's primary-key value; an entity's primary key is always one
attribute. `Customer` has no version, so a target write can't name a revision for it,
and Parallax refuses one. Read a customer inside the transaction instead; its shared
lock protects the write. `replace_if` takes a whole instance, which can be an edited copy
of the reviewed value, and states that instance's writable state.

On a Bitemporal entity, a target write also states `valid_from`, where it starts, and
optionally `until`. Its `tx_start` describes the row at `valid_from`, so a reviewed value
read at that Valid Time carries the right one:

<!-- example: amend-a-reviewed-price -->
```python
def reprice_from_a_review(
    db: ScopedDatabase, reviewed: Price, amount: Decimal, start: dt.datetime
) -> None:
    """``reviewed`` was read at ``start``: state its milestone's start in Transaction Time."""
    db.transact(
        lambda tx: tx.amend_if(
            Price,
            Price.amount.set(amount),
            key=reviewed.sku,
            valid_from=start,
            tx_start=reviewed.tx_start,
        )
    )
```
<!-- /example -->

A failed precondition is the caller's to handle. This function cancels each order a user
reviewed, unless it has changed since:

<!-- example: cancel-reviewed-orders -->
```python
def cancel_reviewed_orders(db: ScopedDatabase, reviewed: list[Order]) -> list[int]:
    """Cancel each order in a transaction of its own; return the ones that changed."""
    return [order.id for order in reviewed if not cancel_unless_changed(db, order)]


def cancel_unless_changed(db: ScopedDatabase, order: Order) -> bool:
    """Cancel ``order`` unless it changed since it was read; answer whether it was cancelled."""
    try:
        db.transact(lambda tx: tx.delete_if(Order, key=order.id, version=order.version))
    except ExecutionFailure as failure:
        if not isinstance(failure.cause, WritePreconditionError):
            raise
        return False
    return True
```
<!-- /example -->

Each order is cancelled in a transaction of its own, so one that changed doesn't stop
the others, and the function reports it instead. Any other failure passes through.

## Predicate writes

`amend_where`, `replace_where` and `delete_where` write every row a query selects, in one
statement, without reading any of them:

<!-- example: amend-and-delete-where -->
```python
def forget_an_email_address(db: ScopedDatabase, email: str) -> int:
    """Clear an email address from every customer holding it; answers how many did."""
    return db.transact(
        lambda tx: tx.amend_where(Customer.where(Customer.email == email), Customer.email.set(None))
    )


def delete_the_shipments_of(db: ScopedDatabase, order_id: int) -> int:
    """Delete every shipment of an order; answers how many there were."""
    return db.transact(lambda tx: tx.delete_where(Shipment.where(Shipment.order_id == order_id)))
```
<!-- /example -->

A predicate write runs at the call, not at the next flush. The transaction first sends
the writes it buffered before the call, then runs the statement, and the verb returns
how many rows it matched or deleted, `0` when nothing matched. An amendment counts a row
it matched even when the row already held the assigned values. `replace_where` takes the
query and an instance of its entity, and writes that instance's whole writable state to
every selected row; the instance's key selects nothing and is never written.

Because nothing is read, there is no version to check and no milestone to close. So a
predicate write accepts only an entity with no version and no history, such as
`Customer` and `Shipment` here. Over `Order` or `CreditLimit` it is refused with
`InstructionRejectedError` before anything runs. Read those objects and write each one,
or state each revision in a target write.

Values this transaction read before a predicate write keep the values they were read
with: the predicate write doesn't refresh them, and doesn't take away their licence.
An `amend` of one still writes only the members you edit. Read again to see what the
predicate write left.

## Wire writes

The transaction's `wire` has the same verbs as the transaction, and takes plain mappings
in Wire spelling instead of instances:

<!-- example: write-through-wire -->
```python
def add_a_customer_from_json(db: ScopedDatabase, payload: str) -> None:
    """Insert a customer from a JSON document in Wire spelling."""
    db.transact(lambda tx: tx.wire.insert("Customer", json.loads(payload)))


def rename_a_customer_through_wire(db: ScopedDatabase, customer_id: int, name: str) -> None:
    """Amend the node a Wire read of this transaction returned."""

    def rename(tx: TxnContext) -> None:
        customer = tx.wire.find(Customer.where(Customer.id == customer_id)).result()
        tx.wire.amend(customer, {"name": name})

    db.transact(rename)
```
<!-- /example -->

`tx.wire.insert` names the entity and returns the node it opened, which carries the
insertion's licence just as an inserted instance does. `tx.wire.amend` takes a node a
Wire read of this transaction returned and a document naming the members to change;
`tx.wire.replace` takes a node and the whole new state. The target verbs take an entity
name and a document holding the key. The predicate verbs take a Typed query or a
selection document, which names the entity and a predicate in canonical form, such as
`{"entity": "Customer", "predicate": {"eq": {"path": "Customer.email", "value": email}}}`.
`tx.wire.editable_data(node)` copies a node's key and writable members into plain
mutable mappings, ready to edit and pass back.

A Wire read outside the transaction licenses no write either, but it tells you which
milestone a temporal node stands on. `edge_of(node)` returns that milestone's `Edge`,
which says where the milestone starts on each time axis its entity keeps: `tx_time`,
and for a Bitemporal entity `valid_time` as well. Its `tx_time` is the revision a target
write can state. Here a page showed a credit limit from an earlier Wire read, and the
user confirmed a new amount:

<!-- example: condition-a-wire-write-on-a-milestone -->
```python
def change_a_limit_shown_earlier(db: ScopedDatabase, shown: WireEntity, amount: str) -> None:
    """``shown`` came from an earlier Wire read: state where its milestone starts."""
    db.transact(
        lambda tx: tx.wire.amend_if(
            "CreditLimit",
            {"customerId": shown["customerId"], "amount": amount},
            tx_start=edge_of(shown).tx_time,
        )
    )
```
<!-- /example -->

The amendment applies only while the milestone the read returned is still current.
Otherwise it fails with `WritePreconditionError`, like any target write.

## How it works →

- [The write flow](../../../../docs/concepts/write-flow.md) follows a write from the
  verb you call to the statements that commit, in domain terms, and
  [the temporal model](../../../../docs/concepts/temporal-model.md) explains the two
  time axes and how a Bitemporal write reshapes coverage. The
  [Python write-flow architecture](../architecture/write-flow.md) maps the write path
  onto the implementation.
- The [unit of work](../../../../core/spec/m-unit-work.md) defines buffering, flushing
  and [abort](../../../../core/spec/m-unit-work.md#abort), which reads
  [license a write](../../../../core/spec/m-unit-work.md#current-attempt-source-admission),
  [insertion authority](../../../../core/spec/m-unit-work.md#insertion-authority),
  [replacement](../../../../core/spec/m-unit-work.md#source-authorized-replacement) and
  [target writes](../../../../core/spec/m-unit-work.md#target-writes).
- [Temporal writes](../../../../core/spec/m-temporal-write.md) define
  Transaction-Time-Only chaining, the Bitemporal rectangle split, and why
  [the Transaction-Time past is never rewritten](../../../../core/spec/m-temporal-write.md#the-transaction-time-past-is-never-rewritten).
- [Optimistic locking](../../../../core/spec/m-opt-lock.md) and
  [read locks](../../../../core/spec/m-read-lock.md) define the two concurrency
  strategies, and [batch writes](../../../../core/spec/m-batch-write.md) define
  predicate writes.
- The [Wire codec](../../../../core/spec/m-wire.md) defines the canonical values Wire
  writes accept.
- The [Python execution binding](../../spec/execution.md#transactions-and-failure-boundaries)
  records the Python write verbs, and the
  [queries and results binding](../../spec/queries-and-results.md#wire-results-and-projection)
  records `edge_of`.
