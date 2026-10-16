from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import DomainModel
from parallax.snapshot import ScopedDatabase, TxnContext, connect

__all__ = [
    "CreditReport",
    "a_credit_overtaken_by_another_writer_is_replayed_from_a_fresh_read",
    "conflict_replay_snippet",
]

_TARGET_ID = 2


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


def conflict_replay_snippet() -> str:
    """The story's own source — the Usage Guide snippet that cannot drift."""
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (
            CreditReport,
            a_credit_overtaken_by_another_writer_is_replayed_from_a_fresh_read,
            another_writer_sets_the_balance,
        )
    )
