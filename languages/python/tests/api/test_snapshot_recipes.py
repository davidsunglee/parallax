"""The Usage-Guide Snapshot read recipes, against real Postgres.

Each recipe (`parallax.conformance.snapshot_recipes`) mirrors a spec section
rather than one corpus case, so — like the stale-web-edit pair — it is graded
here as a standalone Docker-backed proof rather than as a case-keyed
`api_suite.EXAMPLES` entry, and the Usage Guide renders it through the case-free
`api_suite.RECIPES` section. One source, both consumers.

Each test seeds its own rows through the public write surface instead of
borrowing a case's fixtures, which is also what makes the family recipes proofs
of the ACCEPTED DECLARATIONS end to end: the same `AbstractRoot` /
`AbstractSubtype` / `ConcreteSubtype` classes decide the tables written and the
concrete class each row materializes back as.

The last section drives every recipe body against a canned fake `m-db-port`, so
those bodies contribute to the database-free coverage gate exactly as
`test_graph_story_no_drift.py` keeps the graph stories in it. The grading above
is the real proof; that driver only pins that each body RUNS through the public
surface with no database at all.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance import snapshot_recipes
from parallax.conformance.class_models import MODELS
from parallax.conformance.read_models import (
    CardPayment,
    CashPayment,
    Invoice,
    Memo,
    Receipt,
)
from parallax.conformance.snapshot_recipes import (
    read_a_table_per_concrete_subtype_family,
    read_a_table_per_hierarchy_family,
    read_to_one_relationship_states,
)
from parallax.conformance.story_models import Order, OrderItem, OrderStatus
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.entity import UnloadedRelationshipError
from parallax.core.entity._model import model_of
from parallax.snapshot import connect, is_view_loaded
from parallax.snapshot.handle import Database

_ORDERS = MODELS["orders"]
_PAYMENT = MODELS["payment"]
_DOCUMENT = MODELS["document"]


def _seed_orders(db: Database) -> None:
    db.transact(
        lambda tx: (
            tx.insert(
                Order(
                    id=1,
                    name="Ada",
                    sku="A-100",
                    qty=5,
                    price=Decimal("10.50"),
                    active=True,
                    ordered_on=dt.date(2024, 1, 5),
                )
            ),
            tx.insert(OrderItem(id=11, order_id=1, sku="SKU-1", quantity=2, shipped_on=None)),
            # One status attached to an item, one attached to the order alone.
            tx.insert(OrderStatus(id=101, order_id=1, order_item_id=None, code="NEW")),
            tx.insert(OrderStatus(id=201, order_id=1, order_item_id=11, code="PICKED")),
        )
    )


def test_a_to_one_relationship_takes_its_three_declared_runtime_states(
    provisioner: Any,
) -> None:
    provisioner.reset(model_of(_ORDERS), {})
    db = connect(provisioner.port, _ORDERS)
    _seed_orders(db)

    included, unincluded = read_to_one_relationship_states(db)

    by_id = {status.id: status for status in included.results()}
    # 1..1 over a non-nullable foreign key: an instance on every status.
    assert by_id[101].order is not None
    assert by_id[201].order is not None
    assert by_id[101].order is by_id[201].order  # one logical row, one node
    # 0..1 over a nullable foreign key: an instance where the key is set, and a
    # LOADED null where it is not — `is_view_loaded` is `True` for both.
    assert by_id[201].order_item is not None
    assert by_id[201].order_item.id == 11
    assert by_id[101].order_item is None
    assert is_view_loaded(by_id[101], OrderStatus.order_item) is True

    # The unloaded arm: neither multiplicity is knowable, and the two states are
    # told apart by `is_view_loaded` rather than by the value.
    unloaded = unincluded.results()[0]
    assert is_view_loaded(unloaded, OrderStatus.order) is False
    assert is_view_loaded(unloaded, OrderStatus.order_item) is False
    with pytest.raises(UnloadedRelationshipError, match="orderItem"):
        unloaded.order_item  # noqa: B018 - the access itself is the assertion
    assert unincluded.execution.round_trips == 1  # no lazy load behind the refusal


def test_a_table_per_hierarchy_family_materializes_its_declared_concretes(
    provisioner: Any,
) -> None:
    provisioner.reset(model_of(_PAYMENT), {})
    db = connect(provisioner.port, _PAYMENT)
    db.transact(
        lambda tx: (
            tx.insert(CardPayment(id=1, amount=Decimal("200.00"), card_network="visa")),
            tx.insert(CashPayment(id=2, amount=Decimal("50.00"), tendered=Decimal("60.00"))),
        )
    )

    by_id = {node.id: node for node in read_a_table_per_hierarchy_family(db).results()}

    assert type(by_id[1]) is CardPayment
    assert type(by_id[2]) is CashPayment
    assert by_id[1].card_network == "visa"
    assert by_id[2].tendered == Decimal("60.00")
    # Each node carries its own branch's members and no sibling's, so a sibling
    # attribute is not merely null — it is absent from the instance entirely.
    assert not hasattr(by_id[1], "tendered")
    assert not hasattr(by_id[2], "card_network")


def test_a_table_per_concrete_subtype_family_materializes_its_declared_concretes(
    provisioner: Any,
) -> None:
    provisioner.reset(model_of(_DOCUMENT), {})
    db = connect(provisioner.port, _DOCUMENT)
    db.transact(
        lambda tx: (
            tx.insert(
                Invoice(
                    id=1, title="Q1", folder_id=None, currency="EUR", amount_due=Decimal("10.00")
                )
            ),
            tx.insert(
                Receipt(
                    id=2, title="Q2", folder_id=None, currency="EUR", paid_amount=Decimal("5.00")
                )
            ),
            tx.insert(Memo(id=3, title="Note", folder_id=None, body="hello")),
        )
    )

    by_id = {node.id: node for node in read_a_table_per_concrete_subtype_family(db).results()}

    # Three separate tables, no tag column anywhere: the concrete each row
    # materializes as is the table it came from, including the branch reached
    # through the intermediate abstract subtype and the one declared directly
    # under the root.
    assert type(by_id[1]) is Invoice
    assert type(by_id[2]) is Receipt
    assert type(by_id[3]) is Memo
    assert by_id[1].currency == "EUR"
    assert not hasattr(by_id[3], "currency")  # Memo is not a FinancialDocument


# --------------------------------------------------------------------------- #
# Database-free run-through of every recipe body.                              #
# --------------------------------------------------------------------------- #
class _CannedPort:
    """A fake `m-db-port` answering every read with no rows, which is all a
    run-through proof needs: an empty root level short-circuits every child."""

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        return []

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:  # pragma: no cover
        raise AssertionError("a read recipe issues no DML")

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        raise AssertionError("a read recipe opens no transaction")


@pytest.mark.parametrize(
    ("recipe", "model"),
    [
        pytest.param(read_to_one_relationship_states, "orders", id="to-one-states"),
        pytest.param(read_a_table_per_hierarchy_family, "payment", id="table-per-hierarchy"),
        pytest.param(
            read_a_table_per_concrete_subtype_family, "document", id="table-per-concrete-subtype"
        ),
    ],
)
def test_every_recipe_runs_through_the_shipped_surface(
    recipe: Callable[[Database], Any], model: str
) -> None:
    recipe(Database.connect(_CannedPort(), MODELS[model]))


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(snapshot_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            read_to_one_relationship_states,
            read_a_table_per_hierarchy_family,
            read_a_table_per_concrete_subtype_family,
        )
    )
