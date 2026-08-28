"""The Usage-Guide Snapshot read recipes, against real Postgres.

Each recipe (`parallax.conformance.snapshot_recipes`) mirrors a spec section
rather than one corpus case, so it is graded here as a standalone Docker-backed
proof rather than as a case-keyed `api_suite.EXAMPLES` entry, while the Usage
Guide renders the same body through the case-free `api_suite.RECIPES` section.

Each test seeds its own rows through the public write surface instead of
borrowing a case's fixtures, which is what makes the family recipes proofs of
the ACCEPTED DECLARATIONS end to end: the same `AbstractRoot` /
`AbstractSubtype` / `ConcreteSubtype` classes decide the tables written and the
concrete class each row materializes back as.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, cast

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
    stream_a_result_one_root_at_a_time,
    stream_and_write_inside_one_transaction,
)
from parallax.conformance.story_models import Account, Order, OrderItem, OrderStatus
from parallax.core.db_port import Bind, Committed, DbPort, Row, TransactionOutcome
from parallax.core.entity import UnloadedRelationshipError
from parallax.core.entity._model import model_of
from parallax.snapshot import SnapshotStreamStateError, connect, is_view_loaded
from parallax.snapshot.handle import Database

_ACCOUNT = MODELS["account"]
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
    # No lazy load behind the refusal: an unloaded view raises rather than
    # reaching the database, so the read that published it stays one statement.


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


def _seed_streamed_orders(db: Database, count: int) -> None:
    """``count`` active orders, each carrying two items, so a delivery pages over
    something with fan-out and every page's child level is non-empty."""

    def load(tx: Any) -> None:
        for order_id in range(1, count + 1):
            tx.insert(
                Order(
                    id=order_id,
                    name=f"order-{order_id}",
                    sku="A-100",
                    qty=order_id,
                    price=Decimal("10.50"),
                    active=True,
                    ordered_on=dt.date(2024, 1, 5),
                )
            )
            for offset in range(2):
                tx.insert(
                    OrderItem(
                        id=order_id * 10 + offset,
                        order_id=order_id,
                        sku="SKU",
                        quantity=order_id,
                        shipped_on=None,
                    )
                )

    db.transact(load)


def test_a_streamed_delivery_answers_the_same_result_at_every_page_size(
    provisioner: Any,
) -> None:
    # The recipe's own claim, against real Postgres: `batch_size` is a dial and
    # nothing else. Seven roots at three page sizes — one that divides the result,
    # one that does not, and one larger than the whole of it — must agree on the
    # summed child quantities and on the roots' order, which is the Continuation
    # Order the delivery derived from a query that declared none.
    provisioner.reset(model_of(_ORDERS), {})
    db = connect(provisioner.port, _ORDERS)
    _seed_streamed_orders(db, 7)

    readings = [stream_a_result_one_root_at_a_time(db, page) for page in (2, 3, 16)]

    # Two items per order, each of quantity `order_id`: 2 * (1 + ... + 7).
    assert readings[0] == (2 * sum(range(1, 8)), [f"order-{n}" for n in range(1, 8)])
    assert readings[1] == readings[0]
    assert readings[2] == readings[0]


def test_a_streamed_delivery_is_scope_bound_and_single_pass(provisioner: Any) -> None:
    # What the recipe's `with` block is for, stated as the two refusals a caller
    # earns by leaving it: there is no whole-result accessor to reach for, and a
    # delivery hands its roots to one view, once.
    provisioner.reset(model_of(_ORDERS), {})
    db = connect(provisioner.port, _ORDERS)
    _seed_streamed_orders(db, 3)

    with db.stream(Order.where(Order.all), batch_size=2) as orders:
        assert [order.id for order in orders] == [1, 2, 3]
        with pytest.raises(SnapshotStreamStateError, match="single-pass"):
            iter(orders)
    escaped = db.stream(Order.where(Order.all), batch_size=2)
    with pytest.raises(SnapshotStreamStateError, match="own scope"):
        escaped.pin  # noqa: B018 - the access itself is the assertion


def test_a_participating_delivery_writes_every_root_exactly_once(provisioner: Any) -> None:
    # The transactional recipe against real Postgres: a loop that reads and writes
    # through one unit of work credits each account once, whatever the page size,
    # because the Continuation Order over an unordered query is the primary key and
    # no write moves one. The committed rows are what says so, read back after the
    # boundary rather than from the values the loop held.
    provisioner.reset(model_of(_ACCOUNT), {})
    db = connect(provisioner.port, _ACCOUNT)
    db.transact(
        lambda tx: [
            tx.insert(Account(id=n, owner=f"owner-{n}", balance=Decimal("100.00")))
            for n in range(1, 6)
        ]
    )

    written = stream_and_write_inside_one_transaction(db, 2)

    assert written == [Decimal("110.00")] * 5
    committed = db.find(Account.where(Account.all)).results()
    assert sorted(account.balance for account in committed) == [Decimal("110.00")] * 5


# --------------------------------------------------------------------------- #
# Database-free run-through of every recipe body.                              #
# --------------------------------------------------------------------------- #
def _streamed_delivery_at_page_two(db: Database) -> tuple[int, list[str]]:
    """The streamed recipe with its page size bound, so the run-through drives
    every recipe through one signature."""
    return stream_a_result_one_root_at_a_time(db, 2)


def _streamed_write_at_page_two(db: Database) -> list[Decimal]:
    """The participating recipe, bound the same way."""
    return stream_and_write_inside_one_transaction(db, 2)


class _CannedPort:
    """A fake `m-db-port` answering every read with no rows, which is all a
    run-through proof needs: an empty root level short-circuits every child."""

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return []

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:  # pragma: no cover
        raise AssertionError("a read recipe issues no DML")

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        raise AssertionError("a read recipe opens no transaction")


class _CannedAccountPort:
    """A fake `m-db-port` answering ONE account row and then none, so a delivery
    over it runs its caller's loop body exactly once and then ends.

    The read-only port above cannot serve the participating recipe twice over: it
    refuses DML, and an empty first page would end the delivery before the loop
    body ran at all — which is the half of that recipe worth running through.
    A short first page is what proves exhaustion (`m-snapshot-read`), so one row
    is a whole delivery and no second read is issued.
    """

    def __init__(self) -> None:
        self.rows = [_ACCOUNT_ROW]

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        answered, self.rows = self.rows, []
        return answered

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        return Committed(body(cast("DbPort", self)))


_ACCOUNT_ROW: Row = {"id": 1, "owner": "owner-1", "balance": Decimal("100.00"), "version": 1}

_ORDER_ROW: Row = {
    "id": 1,
    "name": "Ada",
    "sku": "A-100",
    "qty": 5,
    "price": Decimal("10.50"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 5),
}

_ORDER_ITEM_ROW: Row = {
    "id": 11,
    "order_id": 1,
    "sku": "SKU-1",
    "quantity": 2,
    "shipped_on": None,
}


class _CannedOrderPort:
    """A fake `m-db-port` scripting the three reads the streamed read recipe makes.

    Its Typed delivery is one short page — one root for a requested two, which is
    what proves exhaustion — and that page's item level; its Wire delivery is one
    short page of its own. Answering an empty result instead would run neither
    loop body, and the loop body is what the recipe is about.
    """

    def __init__(self) -> None:
        self.scripted = [[_ORDER_ROW], [_ORDER_ITEM_ROW], [_ORDER_ROW]]

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        return self.scripted.pop(0) if self.scripted else []

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:  # pragma: no cover
        raise AssertionError("a read recipe issues no DML")

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        raise AssertionError("a read recipe opens no transaction")


@pytest.mark.parametrize(
    ("recipe", "model", "port"),
    [
        pytest.param(read_to_one_relationship_states, "orders", _CannedPort, id="to-one-states"),
        pytest.param(
            read_a_table_per_hierarchy_family, "payment", _CannedPort, id="table-per-hierarchy"
        ),
        pytest.param(
            read_a_table_per_concrete_subtype_family,
            "document",
            _CannedPort,
            id="table-per-concrete-subtype",
        ),
        pytest.param(
            _streamed_delivery_at_page_two, "orders", _CannedOrderPort, id="streamed-delivery"
        ),
        pytest.param(
            _streamed_write_at_page_two, "account", _CannedAccountPort, id="participating-delivery"
        ),
    ],
)
def test_every_recipe_runs_through_the_shipped_surface(
    recipe: Callable[[Database], Any], model: str, port: Callable[[], Any]
) -> None:
    recipe(Database.connect(port(), MODELS[model]))


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(snapshot_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            read_to_one_relationship_states,
            read_a_table_per_hierarchy_family,
            read_a_table_per_concrete_subtype_family,
            stream_a_result_one_root_at_a_time,
            stream_and_write_inside_one_transaction,
        )
    )
