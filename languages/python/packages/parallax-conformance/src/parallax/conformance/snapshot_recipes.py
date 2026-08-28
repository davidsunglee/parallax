"""Executable Usage-Guide recipes for the Snapshot read surface.

Each function here is one executable read over the **public** developer surface
(``parallax.snapshot.connect`` -> ``db.find``), and its own source is the
Usage-Guide snippet (``api_suite.RECIPES``). Unlike a story
(:mod:`parallax.conformance.graph_stories`), a recipe mirrors a SPEC section
rather than one corpus case: what each of these shows is a **declaration**
together with the runtime states that declaration produces, which spans more
than any single case's goldens — registering one under a borrowed case id would
misrepresent what that case grades.

A recipe seeds nothing: its caller supplies a ``Database`` already holding the
rows the recipe reads, so the same body serves as both the rendered snippet and
an executable proof.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from parallax.conformance.read_models import Document, Payment
from parallax.conformance.story_models import Account, Order, OrderStatus
from parallax.snapshot.handle import Database, Snapshot, Transaction

__all__ = [
    "read_a_table_per_concrete_subtype_family",
    "read_a_table_per_hierarchy_family",
    "read_to_one_relationship_states",
    "stream_a_result_one_root_at_a_time",
    "stream_and_write_inside_one_transaction",
]


def read_to_one_relationship_states(db: Database) -> tuple[Snapshot[Any], Snapshot[Any]]:
    """The three runtime states a to-one relationship takes, over one Entity that
    declares both multiplicities. A to-one's multiplicity is its foreign key's
    nullability: ``order_id`` is non-nullable, so ``order`` is 1..1 and every
    status resolves it to an instance, while ``order_item_id`` is nullable, so
    ``order_item`` is 0..1 and an order-level status resolves it to ``None`` — a
    LOADED null, not an absence of knowledge. Both are spelled ``Rel[T | None]``
    because both are REVERSE directions, where nothing in the model guarantees a
    counterpart row; a DEFINING to-one instead spells its key's nullability in
    the annotation itself (``Rel[Customer]`` versus ``Rel["Coupon | None"]``) and
    a mismatch is refused at model construction.

    The second read includes neither, leaving both UNLOADED: access raises
    ``UnloadedRelationshipError`` and issues no SQL, and
    ``is_view_loaded(node, OrderStatus.order_item)`` is what tells that state
    apart from the loaded null (``False`` versus ``True``)."""
    included = db.find(
        OrderStatus.where(OrderStatus.all).include(OrderStatus.order, OrderStatus.order_item)
    )
    return included, db.find(OrderStatus.where(OrderStatus.all))


def read_a_table_per_hierarchy_family(db: Database) -> Snapshot[Any]:
    """An abstract-root read of a table-per-hierarchy family: every row of the one
    shared table, each materialized as the concrete class its declared tag value
    names. ``type(node)`` is the observation (``python.md`` §4) — a ``CardPayment``
    node carries ``card_network`` and no ``tendered`` at all, and a ``CashPayment``
    node the reverse, never a sibling's null-padded column."""
    return db.find(Payment.where(Payment.all))


def read_a_table_per_concrete_subtype_family(db: Database) -> Snapshot[Any]:
    """The same read over a table-per-concrete-subtype family, whose concretes own
    separate tables and no tag at all: the read unions them, and each row still
    materializes as its own declared concrete class — including one reached
    through an intermediate abstract subtype (``Invoice``/``Receipt`` under
    ``FinancialDocument``) and one declared directly under the root (``Memo``)."""
    return db.find(Document.where(Document.all))


def stream_a_result_one_root_at_a_time(db: Database, page: int) -> tuple[int, list[str]]:
    """A read delivered one root at a time instead of all at once, in both
    namespaces over one query.

    ``db.stream`` is ``db.find``'s peer, not a different read: the same Object
    Query, the same includes, the same values. What differs is delivery. The
    result is scope-bound and single-pass — it has no whole-result accessor, and
    nothing outside the ``with`` block answers — so a loop over it holds one root
    and the page it came from, whatever the result's size. Summing as you go, as
    below, is the shape that stays bounded; appending each root to a list is not,
    and is outside the guarantee on purpose.

    ``batch_size`` counts ROOT positions and is a performance dial and nothing
    else. It changes neither which roots arrive, nor the order they arrive in, nor
    what any of them carries; what it changes is how many round trips the delivery
    costs and how much one page holds. Included children are not counted by it:
    every one of a delivered root's items is loaded, exactly as under ``db.find``.

    Roots arrive in the Continuation Order — the query's own ``order_by`` first,
    then the primary key — which is a total order the delivery derives, so it is
    deterministic even for a query that declared no ordering at all.
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


def stream_and_write_inside_one_transaction(db: Database, page: int) -> list[Decimal]:
    """A streamed delivery inside a unit of work, writing every root it hands over.

    ``tx.stream`` is ``tx.find``'s peer the same way, and what participation adds
    is a flush before every PAGE rather than one at entry: the writes the loop
    buffered reach the database before the statement that reads the next page, so
    read-your-own-writes holds at every page boundary and the buffer a consuming
    loop accumulates is bounded by the page size rather than by the result.

    A delivery is stable per PAGE and no further, so a loop that writes the member
    its own query ordered by can move a root across the position the next page
    seeks from — and see it twice, or not at all. This one orders by nothing,
    which makes the Continuation Order the primary key alone; no write moves a
    primary key, so the hazard cannot arise. That is the escape whenever a loop is
    both the reader and the writer.
    """
    written: list[Decimal] = []

    def credit(tx: Transaction) -> None:
        with tx.stream(Account.where(Account.id >= 1), batch_size=page) as accounts:
            for account in accounts:
                balance = account.balance + Decimal("10.00")
                tx.update(account.edit(balance=balance))
                written.append(balance)

    db.transact(credit)
    return written
