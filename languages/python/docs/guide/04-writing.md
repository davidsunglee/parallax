# Writing

Writes run inside a transaction. A keyed write to an existing object needs a licence: a
read of that object in the same transaction attempt, the attempt's own insertion of it, or
a revision the caller states.

Returned values are immutable, and writes are explicit rather than inferred from changes
to a live object: you insert a new value, amend an edited copy, or delete through the
transaction. The transaction's unit of work buffers your writes, combines or cancels
writes to the same object, batches them, and orders them around their dependencies. A
read inside the transaction first flushes the pending writes it needs, so it sees your
own changes. Predicate writes change every row a query selects without reading them first.

## Non-Temporal entities

### Insert, then read your own write

<!-- example: m-unit-work-001 -->
```python
def insert_then_read_your_own_write(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: TxnContext) -> list[Entity]:
        tx.insert(Account(id=7, owner="Newton", balance=Decimal("5.00")))
        return list(tx.find(Account.where(Account.id == 7)).results())

    return db.transact(fn)
```
<!-- /example -->

### Keyed amendment, observed in-transaction

<!-- example: m-unit-work-005 -->
```python
def keyed_amendment_observed_in_transaction(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: TxnContext) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 1)).result()
        tx.amend(current.edit(balance=Decimal("175.00")))
        return list(tx.find(Account.where(Account.id == 1)).results())

    return db.transact(fn)
```
<!-- /example -->

### Keyed delete, observed in-transaction

<!-- example: m-unit-work-006 -->
```python
def keyed_delete_observed_in_transaction(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: TxnContext) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 3)).result()
        tx.delete(current)
        return list(tx.find(Account.where(Account.id == 3)).results())

    return db.transact(fn)
```
<!-- /example -->

### A row with no revision is written through a read of the writing transaction

<!-- example: m-opt-lock-023 -->
```python
def an_unversioned_wallet_is_written_through_a_read_of_the_writing_transaction(
    adapter: DatabaseAdapter, model: DomainModel
) -> Decimal:
    """Top up a wallet, an Entity with no version and no temporal history.

    ``adapter`` holds the seeded wallets. No revision describes a wallet's
    state, so no caller-stated condition could detect a change since an
    earlier read; the write reads the wallet in the writing transaction
    instead, where the shared lock the read takes protects it until commit.
    """
    with connect(adapter, model) as database:
        db = database.using_database_login()
        query = Wallet.where(Wallet.id == 1)

        def top_up(tx: TxnContext) -> None:
            wallet = tx.find(query).result()
            tx.amend(wallet, Wallet.balance.set(wallet.balance + Decimal("75.00")))

        db.transact(top_up)
        return db.find(query).result().balance
```
<!-- /example -->

## Bitemporal entities

### Bitemporal amend-until splits head/middle/tail

<!-- example: m-temporal-write-017 -->
```python
def bitemporal_amend_until_splits_head_middle_tail(db: ScopedDatabase) -> None:
    def insert(tx: TxnContext) -> None:
        tx.insert(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    def split(tx: TxnContext) -> None:
        current = tx.find(
            Position.where(Position.id == 1).as_of(
                valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
            )
        ).result()
        tx.amend(
            current.edit(value=Decimal("200.00")),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )

    db.transact(insert)
    db.transact(split)
```
<!-- /example -->

## Target writes

### A value read before the transaction is written under the version it showed

<!-- example: m-unit-work-056 -->
```python
@dataclass(frozen=True, slots=True)
class ReviewedWriteReport:
    """Whether the reviewed value licensed a source write, and the balance the
    target write committed."""

    source_write_refused: bool
    balance: Decimal


def a_reviewed_value_is_written_under_the_version_its_review_saw(
    adapter: DatabaseAdapter, model: DomainModel
) -> ReviewedWriteReport:
    """Credit an account a caller reviewed in an earlier read-only transaction.

    ``adapter`` is the shipped adapter's configuration for the story database,
    which holds the seeded account row. Only a read of the writing transaction
    licenses ``tx.amend``, so the reviewed value — read before that transaction
    began — is refused, and catching the refusal leaves the transaction usable.
    The write states instead the version the review saw through ``amend_if``,
    which fails as a precondition if anyone changed the account since.
    """
    with connect(adapter, model) as database:
        db = database.using_database_login()
        query = Account.where(Account.id == _TARGET_ID)
        reviewed = db.read_only(lambda rtx: rtx.find(query).result())
        credited = reviewed.balance + Decimal("25.00")

        def credit(tx: TxnContext) -> bool:
            refused = False
            try:
                tx.amend(reviewed.edit(balance=credited))
            except WriteEvidenceError:
                refused = True
            tx.amend_if(
                Account, Account.balance.set(credited), key=reviewed.id, version=reviewed.version
            )
            return refused

        refused = db.transact(credit)
        return ReviewedWriteReport(refused, db.find(query).result().balance)
```
<!-- /example -->

### A target amendment states its key and the version its caller last observed

<!-- example: m-opt-lock-027 -->
```python
def target_amendment_gates_on_the_callers_version(db: ScopedDatabase) -> None:
    def fn(tx: TxnContext) -> None:
        tx.amend_if(Account, Account.balance.set(Decimal("250.00")), key=2, version=1)

    db.transact(fn)
```
<!-- /example -->

### A target replacement states the object's whole writable state

<!-- example: m-opt-lock-028 -->
```python
def target_replacement_states_every_writable_member(db: ScopedDatabase) -> None:
    def fn(tx: TxnContext) -> None:
        tx.replace_if(Account(id=3, owner="Hopper", balance=Decimal("12.00")), version=1)

    db.transact(fn)
```
<!-- /example -->

### Accounts reviewed earlier are deleted under the versions the review saw

<!-- example: m-opt-lock-041 -->
```python
@dataclass(frozen=True, slots=True)
class ClosingReport:
    """The reviewed accounts each target deletion removed or refused, and
    the accounts left standing."""

    closed: tuple[int, ...]
    refused: tuple[int, ...]
    remaining: tuple[int, ...]


def reviewed_accounts_are_deleted_under_the_versions_their_review_saw(
    adapter: DatabaseAdapter, model: DomainModel
) -> ClosingReport:
    """Close every account a caller reviewed in an earlier read-only transaction.

    ``adapter`` is the shipped adapter's configuration for the story database,
    which holds the seeded accounts. Each deletion states the version its
    review saw, so an account another writer changed after the review fails
    that precondition instead of being deleted, and one nobody changed is
    deleted. A failed precondition is never retried: the stated version stays
    what the review saw.
    """
    with connect(adapter, model) as database:
        db = database.using_database_login()
        reviewed = db.read_only(
            lambda rtx: list(
                rtx.find(Account.where(Account.id >= 2).order_by(Account.id.asc())).results()
            )
        )

        def credit(tx: TxnContext) -> None:
            current = tx.find(Account.where(Account.id == 2)).result()
            tx.amend(current, Account.balance.set(current.balance + Decimal("5.00")))

        db.transact(credit)
        closed: list[int] = []
        refused: list[int] = []
        for account in reviewed:

            def close(tx: TxnContext, account: Account = account) -> None:
                tx.delete_if(Account, key=account.id, version=account.version)

            try:
                db.transact(close)
            except ExecutionFailure as failure:
                if not isinstance(failure.cause, WritePreconditionError):
                    raise
                refused.append(account.id)
            else:
                closed.append(account.id)
        everyone = Account.where(Account.id >= 1).order_by(Account.id.asc())
        remaining = tuple(account.id for account in db.find(everyone).results())
        return ClosingReport(tuple(closed), tuple(refused), remaining)
```
<!-- /example -->

### A bitemporal target amendment states its window and its caller's milestone

<!-- example: m-temporal-write-042 -->
```python
def bitemporal_target_amendment_gates_on_the_callers_milestone(db: ScopedDatabase) -> None:
    def insert(tx: TxnContext) -> None:
        tx.insert(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    def patch(tx: TxnContext) -> None:
        tx.wire.amend_if(
            "Position",
            {"id": 1, "value": "200.00"},
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
            tx_start=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    db.transact(insert)
    db.transact(patch)
```
<!-- /example -->

## Predicate writes

### A predicate-selected delete over an unversioned entity is readless

<!-- example: m-batch-write-005 -->
```python
def wallet_predicate_delete_is_readless(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: TxnContext) -> list[Entity]:
        deleted = tx.delete_where(Wallet.where(Wallet.balance < Decimal("200.00")))
        assert deleted == 2
        return list(tx.find(Wallet.where(Wallet.balance < Decimal("200.00"))).results())

    return db.transact(fn)
```
<!-- /example -->

### A predicate-selected amendment over an unversioned entity is readless

<!-- example: m-batch-write-006 -->
```python
def wallet_predicate_amend_is_readless(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: TxnContext) -> list[Entity]:
        amended = tx.amend_where(
            Wallet.where(Wallet.balance < Decimal("200.00")),
            Wallet.balance.set(Decimal("150.00")),
            Wallet.owner.set("Updated"),
        )
        assert amended == 2
        return list(tx.find(Wallet.where(Wallet.owner == "Updated")).results())

    return db.transact(fn)
```
<!-- /example -->

## Wire writes

### Condition a Wire write on the milestone a read returned

<!-- example: condition-wire-write-on-read-milestone -->
```python
class Balance(
    TxTemporal,
    table="balance",
    namespace=_NS,
    indices=(index("balance_acct", "acct_num"),),
):
    id: Attr[int] = attr(primary_key=True, column="bal_id")
    acct_num: Attr[str] = attr(max_length=32)
    value: Attr[Decimal] = attr(column="val", precision=18, scale=2)


def condition_a_wire_write_on_the_milestone_it_read(
    db: ScopedDatabase, balance_id: int, value: str
) -> None:
    """State the milestone a Wire node stands on as a later write's condition.

    The read's pin is where it looked; edge_of answers where the node's own
    milestone starts. The read grants no write authority: the amendment applies
    only while that milestone is still current.
    """
    node = db.wire.find(Balance.where(Balance.id == balance_id)).result()
    milestone = edge_of(node)
    db.transact(
        lambda tx: tx.wire.amend_if(
            "parallax.compatibility.Balance",
            {"id": balance_id, "value": value},
            tx_start=milestone.tx_time,
        )
    )
```
<!-- /example -->
