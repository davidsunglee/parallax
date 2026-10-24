# Transactions

A transaction runs a callback. Parallax commits when the callback returns and retries the
whole callback when a transient failure or a conflict it can resolve ends an attempt.

Concurrency control combines optimistic conflict detection, locking reads and a
configurable isolation level. A nested call joins the active transaction when it is
eligible to, and a joined callback that fails marks the whole transaction rollback-only,
so its caller can't catch the failure and commit anyway.

## Retries

### A write another writer overtook is replayed from a fresh read

<!-- example: m-opt-lock-009 -->
```python
@dataclass(frozen=True, slots=True)
class CreditReport:
    """The balance each attempt of the credit read, and the balance it committed."""

    balances_read: tuple[Decimal, ...]
    balance: Decimal


def a_credit_overtaken_by_another_writer_is_replayed_from_a_fresh_read(
    adapter: DatabaseAdapter, model: DomainModel
) -> CreditReport:
    """Credit an account while another writer changes it mid-transaction.

    ``adapter`` is the shipped adapter's configuration for the story database,
    which holds the seeded account row. The credit reads the account inside its
    callback, so each attempt computes its write from what that attempt read.
    Another writer commits between the first attempt's read and its write, so
    that write's version check fails and the transaction replays the whole
    callback: the replay reads the other writer's balance and credits on top of
    it. Nothing asks for the replay; ``max_retries`` only bounds it.
    """
    with connect(adapter, model) as database:
        db = database.using_database_login()
        query = Account.where(Account.id == _TARGET_ID)
        balances_read: list[Decimal] = []

        def credit(tx: TxnContext) -> None:
            account = tx.find(query).result()
            balances_read.append(account.balance)
            if len(balances_read) == 1:
                another_writer_sets_the_balance(db, Decimal("999.00"))
            tx.amend(account.edit(balance=account.balance + Decimal("25.00")))

        db.transact(credit)
        return CreditReport(tuple(balances_read), db.find(query).result().balance)


def another_writer_sets_the_balance(db: ScopedDatabase, balance: Decimal) -> None:
    """Commit a new balance from another thread, as a concurrent writer would."""

    def write(tx: TxnContext) -> None:
        account = tx.find(Account.where(Account.id == _TARGET_ID)).result()
        tx.amend(account.edit(balance=balance))

    writer = threading.Thread(target=db.transact, args=(write,))
    writer.start()
    writer.join()
```
<!-- /example -->

## Per-call options and root defaults

### A root default is overridden per call, and a joining call inherits the override

<!-- example: m-unit-work-041 -->
```python
@dataclass(frozen=True, slots=True)
class ResolvedOptions:
    """What each transaction of the story ran under, read off ``tx.options``."""

    inherited: TxnOptions
    overridden: TxnOptions
    joined: TxnOptions
    repeated: TxnOptions
    root_level_refused_on_join: bool
    balance: Decimal


def a_root_default_is_overridden_per_call_and_a_join_inherits_the_override(
    adapter: DatabaseAdapter, model: DomainModel
) -> ResolvedOptions:
    """A root configured once, a call that overrides one field, and a joining
    call held to the override rather than to the root.

    ``adapter`` is the shipped adapter's configuration for the story database,
    which holds the seeded account row the transactions read. The record handed
    to ``connect`` is every transaction's default; a keyword on ``transact`` is
    an explicit request for that one call, resolved over the record; and a
    joining call inherits what the ACTIVE transaction resolved — omitting a
    field inherits it, repeating the resolved value is accepted, and naming any
    other value, the root's own included, is refused before the joined body
    runs. Nothing is passed as ``None``: only an omitted keyword inherits.
    """
    root = TxnOptions(isolation="repeatable_read", max_retries=2)
    with connect(adapter, model, options=root) as database:
        db = database.using_database_login()
        inherited = db.transact(lambda tx: tx.options)

        def outer(tx: TxnContext) -> ResolvedOptions:
            account = tx.find(Account.where(Account.id == _TARGET_ID)).result()

            def joined_body(joined_tx: TxnContext) -> TxnOptions:
                return joined_tx.options

            joined = db.transact(joined_body)
            repeated = db.transact(joined_body, isolation="serializable")
            refused = False
            try:
                db.transact(joined_body, isolation="repeatable_read")
            except TransactionOptionConflictError:
                refused = True
            return ResolvedOptions(
                inherited=inherited,
                overridden=tx.options,
                joined=joined,
                repeated=repeated,
                root_level_refused_on_join=refused,
                balance=account.balance,
            )

        return db.transact(outer, isolation="serializable")
```
<!-- /example -->
