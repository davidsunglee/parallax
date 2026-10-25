from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from parallax.conformance.guide_models import Customer, Order
from parallax.core.db_port import Password
from parallax.core.execution import TransactionAuthorityError
from parallax.postgres import PostgresAdapter, PostgresRole
from parallax.snapshot import Database, ScopedDatabase, TxnContext

__all__ = [
    "SecretFile",
    "ShopUser",
    "another_user_can_join",
    "change_an_email_for",
    "configure_with_a_secret_file",
    "orders_for_the_nightly_report",
    "rename_a_customer",
]


def orders_for_the_nightly_report(database: Database[PostgresRole], day: dt.date) -> list[Order]:
    """Scheduled work with no user behind it runs as the service's own login."""
    db = database.using_database_login()
    return db.find(Order.where(Order.placed_on == day)).results()


@dataclass(frozen=True, slots=True)
class ShopUser:
    """An application user as a Principal: who they are, and the role they work under."""

    subject: str
    database_authorization: PostgresRole


def change_an_email_for(
    database: Database[PostgresRole], user: ShopUser, customer_id: int, email: str
) -> None:
    """Run one request as the user who made it."""
    db = database.using_principal(user)

    def change(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.amend(customer.edit(email=email))

    db.transact(change)


@dataclass(frozen=True, slots=True)
class SecretFile:
    """A credential source that reads the password each time a connection is made."""

    path: Path

    def resolve(self) -> Password:
        return Password(self.path.read_text(encoding="utf-8").strip())


def configure_with_a_secret_file(conninfo: str, path: Path) -> PostgresAdapter:
    """A rotated secret reaches every connection opened after the rotation."""
    return PostgresAdapter(conninfo, credentials=SecretFile(path))


def rename_a_customer(db: ScopedDatabase, customer_id: int, name: str) -> None:
    """Joins the transaction already running on this thread, when there is one."""

    def rename(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.amend(customer.edit(name=name))

    db.transact(rename)


def another_user_can_join(
    database: Database[PostgresRole], user: ShopUser, other: ShopUser, customer_id: int
) -> bool:
    """Whether work for ``other`` can join a transaction that ``user`` began."""

    def request(_: TxnContext) -> bool:
        rename_a_customer(database.using_principal(user), customer_id, "Ada King")
        try:
            rename_a_customer(database.using_principal(other), customer_id, "Ada Lovelace")
        except TransactionAuthorityError:
            return False
        return True

    return database.using_principal(user).transact(request)
