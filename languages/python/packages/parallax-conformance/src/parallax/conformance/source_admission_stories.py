from __future__ import annotations

import inspect
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import DomainModel
from parallax.core.unit_work import WriteEvidenceError
from parallax.snapshot import TxnContext, connect

__all__ = [
    "ReviewedWriteReport",
    "a_reviewed_value_is_written_under_the_version_its_review_saw",
    "source_admission_snippet",
]

_TARGET_ID = 2


@dataclass(frozen=True, slots=True)
class ReviewedWriteReport:
    """Whether the reviewed value licensed a source write, and the balance the
    conditional write committed."""

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


def source_admission_snippet() -> str:
    """The story's own source — the Usage Guide snippet that cannot drift."""
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (
            ReviewedWriteReport,
            a_reviewed_value_is_written_under_the_version_its_review_saw,
        )
    )
