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

from typing import Any

from parallax.conformance.read_models import Document, Payment
from parallax.conformance.story_models import OrderStatus
from parallax.snapshot.handle import Database, Snapshot

__all__ = [
    "read_a_table_per_concrete_subtype_family",
    "read_a_table_per_hierarchy_family",
    "read_to_one_relationship_states",
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
