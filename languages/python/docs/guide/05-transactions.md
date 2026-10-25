# Transactions

Every write in Parallax runs inside a transaction, and a transaction is a callback.
`db.transact(callback)` runs it and commits when it returns. When something a second try
can fix ends the attempt, such as a deadlock or a row another transaction changed,
Parallax rolls back and runs the whole callback again.

This chapter starts with that callback: what it returns, and what happens when a
transaction calls code that opens another. It then covers the choices a transaction
makes: read-only or read-write, its isolation level, and how it protects the rows it
writes. After the rule that every keyed write needs a licence, it explains which
failures are retried and where a transaction's options come from. The examples use the
shop model from [Modeling](02-modeling.md) and these imports:

<!-- example: transactions-imports -->
```python
from decimal import Decimal

from parallax.core import DomainModel
from parallax.core.execution import (
    ExecutionFailure,
    ReadOnlyTxnOptions,
    TransactionAccessModeError,
    TransactionOptionConflictError,
    TxnOptions,
)
from parallax.core.unit_work import (
    OptimisticLockConflictError,
    RollbackOnlyError,
    WriteEvidenceError,
    WritePreconditionError,
)
from parallax.postgres import PostgresAdapter, PostgresRole
from parallax.snapshot import (
    Database,
    ReadOnlyTxnContext,
    ScopedDatabase,
    TxnContext,
    connect,
)
```
<!-- /example -->

## Running a transaction

`db.transact(callback)` opens a transaction, hands the callback a `TxnContext`, and
commits when the callback returns. Only then does it return what the callback returned.
If the callback raises, or the commit fails, nothing is committed: you get an
`ExecutionFailure` whose `cause` is what went wrong, and the callback's value is never
handed back as if it had been saved.

Each run of the callback is an attempt, and one call to `transact` can make several
attempts when it is [retried](#retries). That is why a transaction is a callback rather
than a `with` block: Parallax has to be able to run your code again. What the callback
does through `tx` is rolled back and redone, but anything else it does, such as sending
an email or appending to a list declared outside it, happens once per attempt. Keep such
effects safe to repeat, or move them after `transact` returns.

### A nested call joins

A `db.transact` call made inside a callback doesn't open a second transaction. It joins
the one already running: its callback runs in the same attempt, sees the same pending
writes, and commits or rolls back with it. So a helper can open a transaction of its own
when called alone, and take part in its caller's when called from one:

<!-- example: join-the-callers-transaction -->
```python
def record_an_order(db: ScopedDatabase, order: Order) -> None:
    """Insert ``order`` in a transaction of its own, or in the caller's when it has one."""

    def record(tx: TxnContext) -> None:
        if order.total <= 0:
            raise ValueError(f"order {order.id} has no total")
        tx.insert(order)

    db.transact(record)


def open_an_account(db: ScopedDatabase, customer: Customer, first_order: Order) -> Customer:
    """The customer and the first order commit together, because ``record_an_order`` joins."""

    def open_account(tx: TxnContext) -> Customer:
        tx.insert(customer)
        record_an_order(db, first_order)
        return tx.find(Customer.where(Customer.id == customer.id)).result()

    return db.transact(open_account)
```
<!-- /example -->

Called alone, `record_an_order` commits its order in a transaction of its own. Called
from `open_an_account`, it joins, so the customer and the order commit together or not at
all. If the order can't be inserted, say because another order already has its id, the
customer isn't saved either. A joined call returns its callback's value straight away,
because it has nothing to commit; `open_an_account` returns the customer it read back,
and only once the commit has succeeded.

Active transactions belong to the thread that runs them, so a call made on another
thread starts a transaction of its own. A join is refused before its callback runs when
it comes from another root, runs under another authority, asks for the other kind of
transaction ([below](#read-only-and-read-write-transactions)), or names options that
differ from the transaction's ([Options and root defaults](#options-and-root-defaults)).
Catching such a refusal leaves the transaction usable.

### A failed joined call dooms the transaction

A joined callback that raises is a different matter. Its failure marks the whole
transaction rollback-only on its way out, and catching it doesn't undo that:

<!-- example: a-caught-joined-failure-still-rolls-back -->
```python
def open_an_account_even_if_the_order_fails(
    db: ScopedDatabase, customer: Customer, first_order: Order
) -> bool:
    """Doesn't work: once the joined call has failed, the transaction can only roll back."""

    def open_account(tx: TxnContext) -> bool:
        tx.insert(customer)
        try:
            record_an_order(db, first_order)
        except ValueError:
            return False
        return True

    return db.transact(open_account)
```
<!-- /example -->

With a valid order this commits both rows and returns `True`. When `record_an_order`
refuses an order with no total, its `ValueError` reaches the outer callback, which
catches it and returns `False`. The transaction rolls back anyway: `transact` raises an
`ExecutionFailure` whose `cause` is a `RollbackOnlyError`, chained to the `ValueError`,
and the customer isn't saved. A read or write the callback tried after catching the
failure would raise `RollbackOnlyError` too.

This is deliberate. The joined callback may have buffered some of its writes before it
failed, and its caller can't tell which. Committing the rest could save half of what the
helper meant to do. When a step may fail and the rest should commit regardless, check
before calling it, or run it in a transaction of its own once the first has committed.

A failure while the transaction sends its writes, such as a database error or a
conflict, dooms it in the same way, even when the callback catches it. A refusal a write
verb raises before anything is sent, such as `WriteEvidenceError`, leaves the transaction
usable.

## Read-only and read-write transactions

`db.read_only(callback)` runs a read-only transaction. Its callback receives a
`ReadOnlyTxnContext`, which has the read verbs, such as `find`, `stream` and `wire`, and
no write verbs. [Where a read runs](03-reading.md#where-a-read-runs) explains when to
choose it over a standalone read or `transact`; this section covers how the two kinds of
transaction behave.

- **The kind is fixed by the call.** Every attempt of `read_only` asks the database for a
  read-only transaction, and every attempt of `transact` for a read-write one. No option,
  join or read changes that.
- **A read-only transaction takes no row locks and forces no flush.** Its reads lock
  nothing, even for an unversioned entity such as `Customer`, which a read inside
  `transact` locks, and it has no pending writes to send.
- **A call joins only a transaction of its own kind.** `transact` inside a `read_only`
  callback, or `read_only` inside a `transact` one, raises `TransactionAccessModeError`
  before its callback runs. Catching it leaves the transaction usable.
- **A standalone read stays standalone.** `db.find` and `db.stream` called inside either
  callback read on a connection of their own, outside the transaction. Inside `transact`,
  they don't see the transaction's pending writes.
- **What a read-only transaction returns licenses no later write.** Its values stay
  readable after it commits, while a stream inside it ends with the attempt. To write one
  of those values, state the revision it carries in a
  [target write](04-writing.md#target-writes).

A read-only transaction is retried like any other, and it takes `max_retries` and
`isolation`. It has no concurrency preference, because it takes no locks.

## Isolation levels

The isolation level decides what a transaction's reads see while other transactions
commit. Parallax names three levels and defines each by what it rules out, so the same
name means the same guarantee on every database:

| Level | Rules out | Still allows |
| -- | -- | -- |
| Read Committed | reading another transaction's uncommitted writes | a row changing between two reads; new rows appearing; anomalies such as write skew |
| Repeatable Read | the above, and a row changing between two reads | new rows appearing; anomalies such as write skew |
| Serializable | all of the above: committed transactions behave as if they ran one at a time | a transaction failing with a serialization failure instead |

What a level allows, it doesn't require: PostgreSQL rules out more than the table
promises, and nothing should depend on an anomaly occurring. On PostgreSQL:

- **Read Committed**: each statement sees what was committed when it started. A statement
  that waited for a row another transaction changed checks its conditions again against
  the row's new version.
- **Repeatable Read**: the transaction's first statement takes a snapshot, and every later
  read sees it, so new rows don't appear either. Writing or locking a row that changed
  after the snapshot fails with a serialization failure. Write skew is still possible.
- **Serializable**: PostgreSQL watches for transactions that couldn't have run one at a
  time, and fails one of them with a serialization failure. It protects only
  transactions that all run at Serializable.

Parallax [retries](#retries) a serialization failure, so a stronger level usually costs
re-runs rather than errors.

Both `transact` and `read_only` run at Read Committed unless you pass `isolation=`, as
`"read_committed"`, `"repeatable_read"` or `"serializable"`, or give the root or scope
another default. Parallax asks for the level on every attempt rather than relying on the
database's own default.

Serializable is the level to use when a transaction checks a condition across several
rows and then writes on the strength of it. This function keeps a customer's orders
within their credit limit:

<!-- example: place-an-order-within-a-credit-limit -->
```python
def place_an_order_within_the_limit(db: ScopedDatabase, order: Order) -> bool:
    """Insert ``order`` unless it takes its customer's orders past their credit limit."""

    def place(tx: TxnContext) -> bool:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == order.customer_id)).result()
        placed = tx.find(Order.where(Order.customer_id == order.customer_id)).results()
        if sum((each.total for each in placed), order.total) > limit.amount:
            return False
        tx.insert(order)
        return True

    return db.transact(place, isolation="serializable")
```
<!-- /example -->

Suppose a customer's orders total 170.00 against a limit of 250.00, and two calls run at
once, one placing an order of 50.00 and the other one of 60.00. Either fits alone; both
don't. At Read Committed or Repeatable Read, each call can read 170.00, pass the check
and insert, because neither changes a row the other read. That is write skew, and those
levels allow it. At Serializable, PostgreSQL finds that the two can't be put in order and
fails one of them with a serialization failure. Parallax retries it, the re-run reads the
other call's order, and the check returns `False` without inserting.
The callback contains no conflict handling; the retry does the work.

The isolation level and the concurrency strategy, below, are independent. The level
decides what reads see, uniformly for the whole transaction. The strategy decides, per
entity, what a read locks and what a write checks.

## Optimistic and locking concurrency

[Modeling](02-modeling.md#optimistic-lock-versions) introduced the two concurrency
strategies. Each transaction has a concurrency preference, `"optimistic"` by default or
`"locking"`, and Parallax combines it with each entity to decide which strategy that
entity uses:

| Entity | Preference `"optimistic"`, the default | Preference `"locking"` |
| -- | -- | -- |
| Versioned, such as `Order` | Optimistic: the read takes no lock, and the write checks the version it read | Locking |
| Temporal, such as `CreditLimit` or `Price` | Optimistic: the write checks the Transaction-Time start it read | Locking |
| Unversioned Non-Temporal, such as `Customer` | Locking: there is nothing to check, so the read takes a shared lock | Locking |

So `"optimistic"` means checking a revision wherever the model has one, and locking where
it doesn't. One transaction can read an order optimistically and its customer under a
lock. The preference applies only to reads inside `transact`: a standalone read and a
read-only transaction never lock.

Under the optimistic strategy, a concurrent change shows up when the write runs. This
function from [Writing](04-writing.md#amend-or-replace-an-edited-value) adds an amount to
an order:

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

Suppose order 10 holds 150.00 at version 1, this call adds 20.00, and another
transaction adds 5.00 between this one's read and its write. The write checks for
version 1, finds version 2, and changes no row: an optimistic lock conflict. Parallax
rolls back and runs the callback again. The re-run reads 155.00 at version 2 and writes
175.00, so both additions survive and the order ends at version 3. You wrote no retry
code.

The locking strategy prevents the conflict instead of detecting it. Pass
`concurrency="locking"` to prefer it for one transaction:

<!-- example: amend-an-order-under-a-lock -->
```python
def add_to_an_order_under_a_lock(db: ScopedDatabase, order_id: int, amount: Decimal) -> None:
    """Lock the order as it is read, so no other transaction changes it before this one ends."""

    def add(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == order_id)).result()
        tx.amend(order, Order.total.set(order.total + amount))

    db.transact(add, concurrency="locking")
```
<!-- /example -->

Here the read takes a shared lock on the order's row and holds it until the transaction
ends. Other transactions can still read the order, but a write to it waits until this
transaction commits or rolls back, so this write applies to exactly the row it read. The
write doesn't check the version, though it still advances it.

Choose locking for rows that many transactions write at once, where a re-run costs more
than a wait. Its cost is that writers wait for each other, and transactions waiting on
each other's locks can deadlock; the database then ends one of them, and Parallax
retries it. Optimistic is the default because most rows are rarely written at the same
moment, and a check costs nothing until they are.

## No blind writes

A keyed write to an object that already exists needs a licence: something that shows the
write knows what it is overwriting. There are four:

- a **State Observation**: the version or Transaction-Time start that a read in this
  attempt saw, which the write then checks is still there;
- the **shared lock** such a read holds, for an entity whose strategy is locking;
- this attempt's own **insertion** of the object;
- a **revision you state** yourself, in a target write.

[Writing](04-writing.md) shows the verbs that use each licence, and
[the write flow](../../../../docs/concepts/write-flow.md#admitted-write) explains how
Parallax checks them. A predicate write such as `amend_where` needs none, because it
reads nothing, which is why only entities with no version and no history accept one.

The licence must come from the attempt that writes. A value read by a standalone read, a
read-only transaction or an earlier attempt took part in nothing this attempt can stand
on, so amending it raises `WriteEvidenceError`. That rule is what makes retries safe: a
re-run reads again, so every observed licence is taken afresh, while a revision you
stated stays exactly what you stated. The next section turns on that difference.

## Retries

When an attempt fails, Parallax decides once, after rolling it back, whether a re-run
could succeed. If it could, Parallax waits a short random delay, so that transactions
that just collided don't collide again, and runs the whole callback again. The new
attempt has its own connection, its own transaction instant and its own reads. A value
captured outside the callback isn't refreshed, and a stream the callback reads starts
again from the beginning.

Which failures are retried is fixed:

| Failure | Retried? | Why |
| -- | -- | -- |
| A deadlock or a serialization failure | Yes | It is transient: a re-run can succeed |
| An optimistic lock conflict: a version or Transaction-Time start a read in this attempt observed has moved | Yes | The re-run reads the newer state and applies the change to it |
| Either of the above, caught by the callback, after which the transaction refused to continue with `RollbackOnlyError` | Yes, on the original failure's terms | The failure that doomed the attempt is what counts |
| A target write's failed precondition: the revision you stated no longer matches | No | A re-run would state the same revision again |
| A failure to get a connection | No | No attempt began, so there is nothing to re-run |
| Anything else | No | It reaches you after the attempt it ended |

Anything else includes your own exceptions, a lock that couldn't be had in time, and a
constraint violation such as a duplicate key. Each reaches you as the `cause` of an
`ExecutionFailure`. How long a statement waits for a lock is PostgreSQL's `lock_timeout`
setting, which you set on the login or in the connection string; the lifecycle guide's
[session settings](../postgresql-lifecycle.md#session-settings) explain which settings
Parallax leaves to you.

### Observed and stated revisions

The difference between the second row and the fourth is who supplied the revision.
Parallax took an observed revision itself, so a re-run can take it again. A stated
revision is your assertion that the row hasn't changed since you looked, and a retry must
not override it. A transaction can hold both kinds, and then it can be retried and still
fail. This function changes a total a user reviewed earlier, provided the customer's
orders stay within their limit:

<!-- example: change-a-reviewed-total-within-the-limit -->
```python
def change_a_reviewed_total_within_the_limit(
    db: ScopedDatabase, reviewed: Order, total: Decimal
) -> bool:
    """Change the total a review showed, unless the customer's orders would pass their limit."""

    def change(tx: TxnContext) -> bool:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == reviewed.customer_id)).result()
        placed = tx.find(Order.where(Order.customer_id == reviewed.customer_id)).results()
        others = sum(each.total for each in placed if each.id != reviewed.id)
        if others + total > limit.amount:
            return False
        tx.amend_if(Order, Order.total.set(total), key=reviewed.id, version=reviewed.version)
        return True

    return db.transact(change, isolation="serializable")
```
<!-- /example -->

The review showed order 10 at version 1. Suppose another transaction adds 5.00 to it
after this one has read the limit and the orders. When this attempt writes, PostgreSQL
finds that the row changed after the attempt's Serializable snapshot and fails the write
with a serialization failure. That is transient, so Parallax retries. The re-run reads
the limit and the orders afresh, passes the check, and states version 1 again, as the
caller asked. The order is now at version 2, so the write fails its precondition. That
`WritePreconditionError` reaches the caller as the `cause` of an `ExecutionFailure` after
two attempts, with no third: a re-run would only state version 1 again.

A deadlock that ends a transaction holding a target write plays out the same way. The
re-run states the same revision, and if the row moved in the meantime, the precondition
fails and isn't retried.

At the default Read Committed, the same race ends sooner. Nothing raises a serialization
failure, so the write is checked against the version you stated and fails its
precondition on the first attempt. The attempt's own read of the order doesn't license
the target write: only the stated version counts.

### How many times

`max_retries` counts re-runs, not attempts. The default is 10, so a transaction makes up
to 11 attempts. If every one of them fails with something retryable, the last attempt's
failure reaches you as the `cause` of an `ExecutionFailure`, with a note naming the
count, such as `bounded retry exhausted after 11 attempts (retries=10)`. For a deadlock
or a serialization failure, that cause is the database's error, whose `category` is
`"deadlock"`; [Errors](08-errors.md#failures-the-database-reports) describes it.
`max_retries=0` turns retries off, and the callback runs once:

<!-- example: make-a-single-attempt -->
```python
def add_to_an_order_once(db: ScopedDatabase, order_id: int, amount: Decimal) -> None:
    """Make a single attempt: the job queue that runs this redelivers a job that fails."""

    def add(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == order_id)).result()
        tx.amend(order, Order.total.set(order.total + amount))

    db.transact(add, max_retries=0)
```
<!-- /example -->

If another transaction changes the order between the read and the write, this raises an
`ExecutionFailure` whose `cause` is an `OptimisticLockConflictError`, and the job queue
runs the job again later. `max_retries` is the only control: which failures are retried,
and how long Parallax waits between attempts, aren't options.

## Options and root defaults

A transaction runs under three options: `max_retries`, `concurrency` and `isolation`.
`TxnOptions` holds all three, and its defaults are 10 retries, the optimistic preference
and Read Committed. Each option comes from the first of these that sets it:

1. a keyword on the call, such as `db.transact(callback, isolation="serializable")`;
2. the scope the call is made through, which `db.with_options(...)` derives with some
   options changed;
3. the root, whose `connect(adapter, model, options=TxnOptions(...))` sets the defaults
   for everything derived from it.

<!-- example: set-transaction-defaults -->
```python
def connect_with_transaction_defaults(
    adapter: PostgresAdapter, model: DomainModel
) -> Database[PostgresRole]:
    """Every transaction of this root makes at most four attempts and prefers locking."""
    return connect(adapter, model, options=TxnOptions(max_retries=3, concurrency="locking"))


def a_scope_for_reports(db: ScopedDatabase) -> ScopedDatabase:
    """Transactions through this scope run at Repeatable Read, with the root's other defaults."""
    return db.with_options(isolation="repeatable_read")
```
<!-- /example -->

`connect_with_transaction_defaults` returns a root, a `Database[PostgresRole]`: the
type parameter is what its subject scopes take as a database authorization, a
`PostgresRole` on PostgreSQL, as [Execution authority](06-execution-authority.md#subject-scope)
explains. Pass `a_scope_for_reports` a scope of that root, such as
`root.using_database_login()`. A transaction through the reports scope then runs with
`max_retries=3`, `concurrency="locking"` and `isolation="repeatable_read"`, and a call
through it that passes `max_retries=0` changes only that. Only leaving a keyword out
inherits; passing `None` raises `ValueError` before anything runs. `tx.options` holds the resolved `TxnOptions`, the same for every
attempt and every joined call. In a read-only transaction, `rtx.options` holds a
`ReadOnlyTxnOptions`, which has no concurrency preference.

A joined call never changes the options of the transaction it joins. Leaving an option
out inherits the transaction's value, and naming the same value is accepted. Naming a
different one raises `TransactionOptionConflictError` before the joined callback runs.
Levels are exact: a join that names Read Committed inside a Serializable transaction
conflicts, rather than being satisfied by the stronger level. The scope's and root's
defaults play no part in the comparison, so a join that names the default conflicts with
a transaction whose call overrode it:

<!-- example: join-with-matching-options -->
```python
def place_two_orders(db: ScopedDatabase, first: Order, second: Order) -> tuple[bool, bool]:
    """Check and place each order in turn; each check joins the caller's transaction."""
    return place_an_order_within_the_limit(db, first), place_an_order_within_the_limit(db, second)


def place_two_orders_together(db: ScopedDatabase, first: Order, second: Order) -> tuple[bool, bool]:
    """Refused with ``TransactionOptionConflictError``: each check names Serializable, and
    this transaction runs at the scope's default level."""
    return db.transact(lambda tx: place_two_orders(db, first, second))


def place_two_orders_together_serializably(
    db: ScopedDatabase, first: Order, second: Order
) -> tuple[bool, bool]:
    """Both checks join this Serializable transaction, so both orders commit or neither does."""
    return db.transact(lambda tx: place_two_orders(db, first, second), isolation="serializable")
```
<!-- /example -->

Called alone, `place_two_orders` runs each check in a transaction of its own, so the
first order can commit while the second is declined. `place_two_orders_together` runs at
the scope's default, Read Committed here, so the first check's `isolation="serializable"`
is refused, and the call raises an `ExecutionFailure` whose `cause` is that
`TransactionOptionConflictError`. In `place_two_orders_together_serializably`, both
checks join. Against the 170.00 of orders and the 250.00 limit from
[Isolation levels](#isolation-levels), orders of 50.00 and 60.00 return `(True, False)`:
the second check's read sees the first order, pending in the same transaction, and
declines it.

## How it works →

- [Transactions, concurrency and retry](../../../../docs/concepts/transactions.md)
  explains attempts, the unit of work, licences, concurrency, isolation and retry in
  domain terms, and [the write flow](../../../../docs/concepts/write-flow.md) follows a
  write from its verb to the statements that commit.
- [Execution](../../../../core/spec/m-execution.md) defines
  [attempts](../../../../core/spec/m-execution.md#attempts),
  [read-only transactions](../../../../core/spec/m-execution.md#read-only-transactions),
  [the options a root is configured with](../../../../core/spec/m-execution.md#options-a-root-is-configured-with)
  and [how a transaction and a join resolve them](../../../../core/spec/m-execution.md#option-resolution).
- The [unit of work](../../../../core/spec/m-unit-work.md) defines
  [abort](../../../../core/spec/m-unit-work.md#abort),
  [target writes](../../../../core/spec/m-unit-work.md#target-writes),
  [the transaction instant](../../../../core/spec/m-unit-work.md#the-transaction-instant),
  [the effective concurrency strategy](../../../../core/spec/m-unit-work.md#strategy-selection--one-preference-an-effective-strategy-per-entity)
  and [the isolation level beside it](../../../../core/spec/m-unit-work.md#the-isolation-level-beside-it--what-the-transaction-reads).
- [Automatic retry](../../../../core/spec/m-auto-retry.md) defines which failures are
  retried, the bound and the delay.
  [Optimistic locking](../../../../core/spec/m-opt-lock.md#retry-contract) and
  [read locks](../../../../core/spec/m-read-lock.md) define the two strategies.
- The [database port](../../../../core/spec/m-db-port.md#the-portable-isolation-vocabulary)
  defines the isolation levels and
  [what PostgreSQL does with each](../../../../core/spec/m-db-port.md#adapter-profile--nonportable-per-engine).
- The [Python execution binding](../../spec/execution.md#transactions-and-failure-boundaries)
  records the Python failure boundaries and join refusals, and
  [models, roots, and scopes](../../spec/execution.md#models-roots-and-scopes) records
  `TxnOptions`.
