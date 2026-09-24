from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from parallax.conformance.read_models import Document, Payment
from parallax.conformance.story_models import Account, Order, OrderStatus
from parallax.snapshot.handle import ScopedDatabase, Snapshot, Transaction, WireEntity

__all__ = [
    "publish_typed_read_as_wire",
    "publish_typed_stream_as_wire",
    "read_a_table_per_concrete_subtype_family",
    "read_a_table_per_hierarchy_family",
    "read_to_one_relationship_states",
    "stream_a_result_one_root_at_a_time",
    "stream_and_write_inside_one_transaction",
]


def read_to_one_relationship_states(db: ScopedDatabase) -> tuple[Snapshot[Any], Snapshot[Any]]:
    """Use is_view_loaded to distinguish an omitted relationship from a loaded null."""
    included = db.find(
        OrderStatus.where(OrderStatus.all).include(OrderStatus.order, OrderStatus.order_item)
    )
    return included, db.find(OrderStatus.where(OrderStatus.all))


def read_a_table_per_hierarchy_family(db: ScopedDatabase) -> Snapshot[Any]:
    """Read the abstract root and inspect each returned node's concrete Python type."""
    return db.find(Payment.where(Payment.all))


def read_a_table_per_concrete_subtype_family(db: ScopedDatabase) -> Snapshot[Any]:
    """Read an abstract root whose concrete classes own separate tables."""
    return db.find(Document.where(Document.all))


def publish_typed_read_as_wire(db: ScopedDatabase) -> Snapshot[Any]:
    """Project an existing Typed result without another read.

    Use db.wire.find directly when no caller needs Typed values.
    """
    typed = db.find(Account.where(Account.id == 1))
    return typed.wire()


def publish_typed_stream_as_wire(
    db: ScopedDatabase, page: int, publish: Callable[[WireEntity], None]
) -> None:
    """Consume each Wire projection while paused at its Typed root inside the scope."""
    with db.stream(Order.where(Order.all).include(Order.items), batch_size=page) as orders:
        for order in orders:
            publish(orders.wire(order))


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


def stream_and_write_inside_one_transaction(db: ScopedDatabase, page: int) -> list[Decimal]:
    """Order by the immutable primary key so writes cannot move the next page's cursor."""
    written: list[Decimal] = []

    def credit(tx: Transaction) -> None:
        with tx.stream(Account.where(Account.id >= 1), batch_size=page) as accounts:
            for account in accounts:
                balance = account.balance + Decimal("10.00")
                tx.update(account.edit(balance=balance))
                written.append(balance)

    db.transact(credit)
    return written
