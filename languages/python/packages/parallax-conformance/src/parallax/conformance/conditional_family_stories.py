from __future__ import annotations

import inspect
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account, Wallet
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import DomainModel
from parallax.core.execution import ExecutionFailure
from parallax.core.unit_work import WritePreconditionError
from parallax.snapshot import TxnContext, connect

__all__ = [
    "ClosingReport",
    "an_unversioned_wallet_is_written_through_a_read_of_the_writing_transaction",
    "reviewed_accounts_are_deleted_under_the_versions_their_review_saw",
    "reviewed_deletion_snippet",
    "unversioned_write_snippet",
]


@dataclass(frozen=True, slots=True)
class ClosingReport:
    """The reviewed accounts each conditional deletion removed or refused, and
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


def reviewed_deletion_snippet() -> str:
    """The reviewed-deletion story's own source — the Usage Guide snippet that
    cannot drift."""
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (
            ClosingReport,
            reviewed_accounts_are_deleted_under_the_versions_their_review_saw,
        )
    )


def unversioned_write_snippet() -> str:
    """The unversioned-write story's own source — the Usage Guide snippet that
    cannot drift."""
    return inspect.getsource(
        an_unversioned_wallet_is_written_through_a_read_of_the_writing_transaction
    ).rstrip("\n")
