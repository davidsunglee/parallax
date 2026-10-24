# Reading and querying

Reads return immutable values. The relationships a read requests are loaded before a value
is delivered, so following one never runs another query. Building a query performs no I/O.

Within each result root's graph, a row reached along two include paths, or through a
cycle, is one shared object. A `Snapshot` answers exactly one, at most one, or many
results, and a context-managed stream delivers a large result a page at a time. A
temporal read carries its instant through the whole requested graph, so related objects
are read from the same point in time. The Wire API takes canonical query documents and
returns immutable mappings; it shares the Typed API's execution, and a Typed result can
be published as Wire data without another read.

## Where a read runs

### Reads run in one read-only transaction at a chosen isolation

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

## Predicates, ordering and limits

### Equality on the primary key

<!-- example: m-predicate-002 -->
```python
query = Order.where(Order.id == 42)
```
<!-- /example -->

### Conjoined filters (big-AND)

<!-- example: m-predicate-020 -->
```python
query = Order.where(Order.active.is_(True), Order.qty > 10)
```
<!-- /example -->

### Ordering and limiting

<!-- example: m-object-query-003 -->
```python
query = Order.where(Order.all).order_by(Order.active.desc(), Order.qty.asc()).limit(2)
```
<!-- /example -->

### Relationship quantifier with a predicate

<!-- example: m-navigate-004 -->
```python
query = Order.where(Order.items.any(OrderItem.quantity >= 4))
```
<!-- /example -->

### A scoped to-many predicate requiring one element to satisfy both fields

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

### A result narrowed to one concrete subtype, filtered by its own attribute

<!-- example: m-inheritance-012 -->
```python
query = Animal.where(Animal.is_a(Dog, where=Dog.bark_volume > 3))
```
<!-- /example -->

## Loading a graph

### Read optional relationships

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

## Streaming

### Stream results

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

## Temporal reads

### As-of read at a past instant

<!-- example: m-temporal-read-003 -->
```python
query = Balance.where(Balance.all).as_of(tx_time=datetime(2024, 4, 1, tzinfo=UTC))
```
<!-- /example -->

## The Wire API

### Publish a Typed result as Wire data

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
