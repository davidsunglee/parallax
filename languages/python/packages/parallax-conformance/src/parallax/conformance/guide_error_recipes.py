from __future__ import annotations

import logging
from collections.abc import Mapping

from parallax.conformance.guide_models import Customer
from parallax.core import DomainModel, EditError
from parallax.core.db_port import CredentialSource
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle import LoggingLifecycleProvider
from parallax.postgres import PoolOptions, PostgresAdapter, PostgresRole
from parallax.snapshot import Database, ScopedDatabase, TxnContext, connect

__all__ = [
    "add_a_customer_unless_the_id_is_taken",
    "change_a_customer_from_a_form",
    "open_the_shop_database",
]


def change_a_customer_from_a_form(
    db: ScopedDatabase, customer_id: int, form: Mapping[str, object]
) -> dict[str | None, str]:
    """Apply a form's changes, or answer every field the model refuses, by member name."""

    def change(tx: TxnContext) -> dict[str | None, str]:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        try:
            edited = customer.edit(**form)
        except EditError as refused:
            return {violation.member_name: violation.message for violation in refused.violations}
        tx.amend(edited)
        return {}

    return db.transact(change)


def add_a_customer_unless_the_id_is_taken(db: ScopedDatabase, customer: Customer) -> bool:
    """Insert ``customer``, or answer False when another customer already has its id."""
    try:
        db.transact(lambda tx: tx.insert(customer))
    except ExecutionFailure as failure:
        if getattr(failure.cause, "category", None) != "uniqueViolation":
            raise
        return False
    return True


def open_the_shop_database(
    conninfo: str, credentials: CredentialSource, model: DomainModel
) -> Database[PostgresRole]:
    """The process's one root: a bounded pool, room for more read plans, and logging."""
    adapter = PostgresAdapter(conninfo, credentials=credentials, pool=PoolOptions(max_size=20))
    return connect(
        adapter,
        model,
        read_plan_cache_capacity=64,
        lifecycle_provider=LoggingLifecycleProvider(logging.getLogger("shop.database")),
    )
