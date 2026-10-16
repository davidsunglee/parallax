from __future__ import annotations

import inspect
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import DomainModel
from parallax.core.execution import ReadOnlyTxnOptions, TransactionAccessModeError
from parallax.snapshot import ReadOnlyTxnContext, connect

__all__ = [
    "ReadOnlyReport",
    "read_only_snippet",
    "reads_run_in_one_read_only_transaction_at_a_chosen_isolation",
]

_TARGET_ID = 2


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


def read_only_snippet() -> str:
    """The story's own source — the Usage Guide snippet that cannot drift."""
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (ReadOnlyReport, reads_run_in_one_read_only_transaction_at_a_chosen_isolation)
    )
