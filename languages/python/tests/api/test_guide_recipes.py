"""The README's and the Python Guide's teaching recipes against real Postgres.

Each recipe's source is a published snippet, so these tests grade the outcome a
reader is told to expect. The database-free run-through at the end drives every
recipe body through the shipped surface over a scripted port.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import datetime as dt
import json
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance import guide_recipes
from parallax.conformance.guide_models import (
    SHOP_MODEL,
    Address,
    BankTransfer,
    CardPayment,
    CreditLimit,
    Customer,
    Order,
    Payment,
    Price,
    Product,
    Shipment,
)
from parallax.conformance.guide_recipes import (
    add_a_surcharge_to_every_order,
    add_and_find_a_customer,
    amend_a_value_read_earlier,
    amend_after_reading_it_again,
    configure_the_database,
    credit_limit_history,
    credit_limit_on_record,
    current_credit_limit,
    customer_as_json,
    customer_with_email,
    customers_and_orders_from_one_snapshot,
    customers_and_orders_one_read_at_a_time,
    customers_with_an_order_over,
    customers_with_an_order_over_as_wire,
    look_up_a_customer,
    orders_placed_on,
    orders_with_their_customer,
    payments_for,
    place_an_order,
    price_on,
    price_on_as_recorded_at,
    prices_during,
    products_and_unreadable_rows,
    products_named,
    run_a_summer_sale,
    shipments_to,
    table_statements,
)
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.conformance.usage_guide import snippet_sources
from parallax.core import DomainModel
from parallax.core.base import INFINITY
from parallax.core.db_port import Bind, Committed, DatabaseConnection, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle import (
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ReadFinished,
    RootExecution,
)
from parallax.core.read_delivery import InvalidDataError
from parallax.core.unit_work import WriteEvidenceError
from parallax.postgres import PostgresAdapter
from parallax.snapshot import (
    Database,
    NoResultFound,
    ScopedDatabase,
    TooManyResultsFound,
    TxnContext,
    WireEntity,
    connect,
)
from tests._support.db_port import ConnectsAsItself, projected_row
from tests._support.root_ownership import own_root
from tests.api._peer_commit import commit_as_a_peer

_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_MAR = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_MAY = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
_JUN = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_JUL = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
_SEP = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)
_OCT = dt.datetime(2024, 10, 1, tzinfo=dt.UTC)


def _shop(profile_run: Any, **connect_options: Any) -> ScopedDatabase:
    profile_run.reset(model_of(SHOP_MODEL), {})
    return own_root(connect(profile_run.port, SHOP_MODEL, **connect_options)).using_database_login()


def _seed_customers(db: ScopedDatabase) -> None:
    db.transact(
        lambda tx: (
            tx.insert(Customer(id=1, name="Ada", email="ada@example.com")),
            tx.insert(Customer(id=2, name="Grace", email=None)),
            tx.insert(
                Order(id=10, customer_id=1, placed_on=dt.date(2024, 4, 1), total=Decimal("150.00"))
            ),
            tx.insert(
                Order(id=11, customer_id=1, placed_on=dt.date(2024, 4, 9), total=Decimal("20.00"))
            ),
            tx.insert(
                Order(id=12, customer_id=2, placed_on=dt.date(2024, 4, 3), total=Decimal("40.00"))
            ),
        )
    )


def test_the_generated_statements_create_tables_the_first_program_runs_against(
    profile_run: Any,
) -> None:
    # The provisioned schema grants the test login's role its table privileges;
    # replacing the tables with the recipe's own statements, as a migration
    # would, leaves that grant to restate.
    model = DomainModel(Customer, Order)
    profile_run.reset(model_of(model), {})
    with contextlib.closing(profile_run.control()) as control:
        control.execute_write("drop table customer, orders", ())
        for statement in table_statements(model):
            control.execute_write(statement, ())
        control.execute_write(
            "grant select, insert, update, delete on all tables in schema public "
            f'to "{profile_run.default_role.name}"',
            (),
        )

    adapter = configure_the_database(profile_run.connection_info, profile_run.credentials.secret)
    customer = add_and_find_a_customer(adapter)

    assert type(customer) is Customer
    assert (customer.id, customer.name, customer.email) == (1, "Ada Lovelace", "ada@example.com")


def test_a_relationship_filter_returns_matching_customers_with_every_order(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    customers = customers_with_an_order_over(db, Decimal("100.00"))

    assert [customer.name for customer in customers] == ["Ada"]
    # The filter selects customers; the include still loads each one's whole
    # relationship, the small order beside the qualifying one included.
    assert sorted(order.id for order in customers[0].orders) == [10, 11]


def test_the_wire_read_answers_the_typed_reads_values_as_mappings(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    (customer,) = customers_with_an_order_over_as_wire(db, Decimal("100.00"))

    assert {key: customer[key] for key in ("id", "name", "email")} == {
        "id": 1,
        "name": "Ada",
        "email": "ada@example.com",
    }
    orders = cast("Sequence[WireEntity]", customer["orders"])
    assert sorted((order["id"], order["total"]) for order in orders) == [
        (10, "150.00"),
        (11, "20.00"),
    ]


def test_an_order_and_its_customers_change_commit_together(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    place_an_order(db)

    customer = db.find(Customer.where(Customer.id == 1).include(Customer.orders)).result()
    assert customer.email == "ada@example.org"
    assert sorted(order.id for order in customer.orders) == [7, 10, 11]
    placed = next(order for order in customer.orders if order.id == 7)
    assert (placed.total, placed.version) == (Decimal("80.00"), 1)


def test_an_as_of_read_answers_the_limit_recorded_then(profile_run: Any) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_JAN, _MAR]))
    db.transact(lambda tx: tx.insert(CreditLimit(customer_id=1, amount=Decimal("1000.00"))))

    def raise_the_limit(tx: Any) -> None:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == 1)).result()
        tx.amend(limit.edit(amount=Decimal("2500.00")))

    db.transact(raise_the_limit)

    assert credit_limit_on_record(db, 1, dt.datetime(2024, 2, 1, tzinfo=dt.UTC)) == Decimal(
        "1000.00"
    )
    assert credit_limit_on_record(db, 1, dt.datetime(2024, 4, 1, tzinfo=dt.UTC)) == Decimal(
        "2500.00"
    )


def test_a_bounded_amendment_changes_only_its_window(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(lambda tx: tx.insert(Price(sku="TEA-1", amount=Decimal("10.00")), valid_from=_JAN))

    run_a_summer_sale(db)

    def price_on(day: dt.datetime) -> Decimal:
        query = Price.where(Price.sku == "TEA-1").as_of(valid_time=day)
        return db.find(query).result().amount

    assert price_on(_MAR) == Decimal("10.00")
    assert price_on(_JUN) == Decimal("8.00")
    assert price_on(_JUL) == Decimal("8.00")
    assert price_on(_SEP) == Decimal("10.00")
    assert price_on(_OCT) == Decimal("10.00")


def test_a_value_object_field_filters_like_a_column(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(
        lambda tx: (
            tx.insert(
                Shipment(
                    id=1,
                    order_id=10,
                    ship_to=Address(street="1 Fjord Vei", city="Bergen", postcode="5003"),
                    tracking_number=None,
                )
            ),
            tx.insert(
                Shipment(
                    id=2,
                    order_id=11,
                    ship_to=Address(street="2 Karl Johans gate", city="Oslo", postcode="0154"),
                    tracking_number="TRK-2",
                )
            ),
        )
    )

    (shipment,) = shipments_to(db, "Oslo")

    assert shipment.id == 2
    assert shipment.ship_to == Address(street="2 Karl Johans gate", city="Oslo", postcode="0154")


def test_a_family_read_materializes_each_concrete_class(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(
        lambda tx: (
            tx.insert(
                CardPayment(id=1, order_id=10, amount=Decimal("100.00"), card_last_four="4242")
            ),
            tx.insert(BankTransfer(id=2, order_id=10, amount=Decimal("50.00"), reference="INV-10")),
            tx.insert(
                CardPayment(id=3, order_id=11, amount=Decimal("20.00"), card_last_four="1111")
            ),
        )
    )

    by_id = {payment.id: payment for payment in payments_for(db, 10)}

    assert sorted(by_id) == [1, 2]
    assert type(by_id[1]) is CardPayment
    assert type(by_id[2]) is BankTransfer
    assert by_id[1].card_last_four == "4242"
    assert by_id[2].reference == "INV-10"


def test_a_document_layout_entity_reads_like_a_column_one(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(
        lambda tx: (
            tx.insert(Product(sku="TEA-1", name="Green tea", description="Sencha, 100 g")),
            tx.insert(Product(sku="TEA-2", name="Black tea", description=None)),
        )
    )

    (product,) = products_named(db, "Green tea")

    assert (product.sku, product.description) == ("TEA-1", "Sencha, 100 g")
    # Every declared member lives in one JSON document column beside the key.
    with contextlib.closing(profile_run.control()) as control:
        columns = control.execute(
            "select column_name from information_schema.columns "
            "where table_name = 'product' order by column_name",
            (),
        )
    assert [row[0] for row in columns] == ["payload", "sku"]


def test_a_one_off_lookup_answers_the_one_customer(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    customer = look_up_a_customer(db, 2)

    assert (customer.id, customer.name) == (2, "Grace")


class _PeerCommitsAfterTheFirstRead:
    """A lifecycle provider that lets another session commit ``work`` once, right
    after the first read any root it observes finishes."""

    def __init__(self, work: Callable[[], object]) -> None:
        self._work: Callable[[], object] | None = work

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler:
        return self

    def handle(self, event: ExecutionEvent, /) -> None:
        if isinstance(event, ReadFinished) and self._work is not None:
            work, self._work = self._work, None
            commit_as_a_peer(work)

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(error)


def _seed_customers_and_a_peer_order(profile_run: Any) -> _PeerCommitsAfterTheFirstRead:
    db = _shop(profile_run)
    _seed_customers(db)
    peer = own_root(connect(profile_run.port, SHOP_MODEL)).using_database_login()
    return _PeerCommitsAfterTheFirstRead(
        lambda: peer.transact(
            lambda tx: (
                tx.insert(Customer(id=3, name="Edsger", email=None)),
                tx.insert(
                    Order(
                        id=13, customer_id=3, placed_on=dt.date(2024, 4, 5), total=Decimal("9.00")
                    )
                ),
            )
        )
    )


def test_standalone_reads_each_see_the_database_as_it_is_when_they_run(
    profile_run: Any,
) -> None:
    peer = _seed_customers_and_a_peer_order(profile_run)
    db = own_root(
        connect(profile_run.port, SHOP_MODEL, lifecycle_provider=peer)
    ).using_database_login()

    customers, orders = customers_and_orders_one_read_at_a_time(db)

    # The peer committed between the two reads: the second sees its order, the
    # first never saw its customer.
    assert sorted(customer.id for customer in customers) == [1, 2]
    assert sorted(order.id for order in orders) == [10, 11, 12, 13]


def test_reads_in_one_read_only_transaction_agree(profile_run: Any) -> None:
    peer = _seed_customers_and_a_peer_order(profile_run)
    db = own_root(
        connect(profile_run.port, SHOP_MODEL, lifecycle_provider=peer)
    ).using_database_login()

    customers, orders = customers_and_orders_from_one_snapshot(db)

    assert sorted(customer.id for customer in customers) == [1, 2]
    assert sorted(order.id for order in orders) == [10, 11, 12]
    # The peer did commit; a later read sees both of its rows.
    later_customers, later_orders = customers_and_orders_from_one_snapshot(db)
    assert sorted(customer.id for customer in later_customers) == [1, 2, 3]
    assert sorted(order.id for order in later_orders) == [10, 11, 12, 13]


def test_only_a_read_in_the_writing_transaction_licenses_an_amendment(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)
    shown = db.find(Customer.where(Customer.id == 1)).result()

    with pytest.raises(ExecutionFailure) as refused:
        amend_a_value_read_earlier(db, shown, "ada@example.net")

    assert isinstance(refused.value.cause, WriteEvidenceError)
    assert refused.value.cause.code == "write-evidence-unavailable"
    assert look_up_a_customer(db, 1).email == "ada@example.com"

    amend_after_reading_it_again(db, 1, "ada@example.net")

    assert look_up_a_customer(db, 1).email == "ada@example.net"


def test_identity_is_shared_within_one_result_root_and_never_across_roots(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    orders = {order.id: order for order in orders_with_their_customer(db, dt.date(2024, 4, 2))}

    assert sorted(orders) == [11, 12]
    # Order 11 reaches itself again through its customer: one object, not a copy.
    eleven = orders[11]
    assert eleven.customer is not None
    assert sorted(order.id for order in eleven.customer.orders) == [10, 11]
    assert any(order is eleven for order in eleven.customer.orders)


def test_two_result_roots_reaching_one_customer_hold_distinct_objects(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    ten, eleven = (
        order
        for order in orders_with_their_customer(db, dt.date(2024, 4, 1))
        if order.customer_id == 1
    )

    assert ten.customer is not None and eleven.customer is not None
    assert ten.customer is not eleven.customer
    assert ten.customer == eleven.customer


def test_each_result_shape_answers_its_arity(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    found = customer_with_email(db, "ada@example.com")
    assert found is not None and found.id == 1
    assert customer_with_email(db, "nobody@example.com") is None
    assert [order.id for order in orders_placed_on(db, dt.date(2024, 4, 9))] == [11]
    assert orders_placed_on(db, dt.date(2024, 4, 2)) == []

    with pytest.raises(NoResultFound):
        look_up_a_customer(db, 99)

    db.transact(lambda tx: tx.insert(Customer(id=3, name="Ada", email="ada@example.com")))
    with pytest.raises(TooManyResultsFound):
        customer_with_email(db, "ada@example.com")


def test_a_checked_read_hands_back_rows_that_break_the_model(profile_run: Any) -> None:
    db = _shop(profile_run)
    db.transact(lambda tx: tx.insert(Product(sku="TEA-1", name="Green tea", description=None)))
    with contextlib.closing(profile_run.control()) as control:
        control.execute_write(
            "insert into product (sku, payload) values ('TEA-2', '{\"description\": \"Oolong\"}')",
            (),
        )

    readable, unreadable = products_and_unreadable_rows(db)

    assert [product.sku for product in readable] == ["TEA-1"]
    (damaged,) = unreadable
    assert (damaged.ordinal, damaged.data) == (1, None)
    assert {issue.code for issue in damaged.issues} == {"stored-data-attribute-null"}
    with pytest.raises(InvalidDataError):
        db.find(Product.where(Product.all)).results()


@pytest.mark.parametrize("page", [1, 2, 100])
def test_a_stream_inside_a_transaction_amends_every_order_exactly_once(
    profile_run: Any, page: int
) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    amended = add_a_surcharge_to_every_order(db, Decimal("5.00"), page)

    assert amended == 3
    orders = db.find(Order.where(Order.all)).results()
    assert sorted((order.id, order.total, order.version) for order in orders) == [
        (10, Decimal("155.00"), 2),
        (11, Decimal("25.00"), 2),
        (12, Decimal("45.00"), 2),
    ]


def test_a_stream_ordered_by_what_its_loop_writes_delivers_an_order_twice(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    def raise_totals_in_total_order(tx: TxnContext) -> list[int]:
        delivered: list[int] = []
        query = Order.where(Order.all).order_by(Order.total.asc())
        with tx.stream(query, batch_size=1) as orders:
            for order in orders:
                delivered.append(order.id)
                if delivered.count(order.id) > 1:
                    break
                tx.amend(order.edit(total=order.total + Decimal("200.00")))
        return delivered

    # 11 (20.00) moves to 220.00, ahead of the position, so it comes round again.
    assert db.transact(raise_totals_in_total_order) == [11, 12, 10, 11]


def test_a_transaction_time_history_lists_every_limit_held(profile_run: Any) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_JAN, _MAR]))
    db.transact(lambda tx: tx.insert(CreditLimit(customer_id=1, amount=Decimal("1000.00"))))

    def raise_the_limit(tx: TxnContext) -> None:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == 1)).result()
        tx.amend(limit.edit(amount=Decimal("2500.00")))

    db.transact(raise_the_limit)

    assert current_credit_limit(db, 1) == Decimal("2500.00")
    assert credit_limit_history(db, 1) == [(_JAN, Decimal("1000.00")), (_MAR, Decimal("2500.00"))]


def _seed_a_price_and_a_summer_sale(profile_run: Any) -> ScopedDatabase:
    # The price is recorded in January; the sale is recorded in May.
    db = _shop(profile_run, clock=ScriptedClock([_JAN, _MAY]))
    db.transact(lambda tx: tx.insert(Price(sku="TEA-1", amount=Decimal("10.00")), valid_from=_JAN))
    run_a_summer_sale(db)
    return db


def test_a_bitemporal_read_answers_on_either_axis(profile_run: Any) -> None:
    db = _seed_a_price_and_a_summer_sale(profile_run)

    assert price_on(db, "TEA-1", _JUL) == Decimal("8.00")
    assert price_on(db, "TEA-1", _OCT) == Decimal("10.00")
    # In March the database had not heard of the sale.
    assert price_on_as_recorded_at(db, "TEA-1", _JUL, _MAR) == Decimal("10.00")
    assert price_on_as_recorded_at(db, "TEA-1", _JUL, _JUN) == Decimal("8.00")


def test_a_valid_time_range_returns_each_price_in_effect(profile_run: Any) -> None:
    db = _seed_a_price_and_a_summer_sale(profile_run)

    assert prices_during(db, "TEA-1", _MAY, _JUL) == [
        (_JAN, Decimal("10.00")),
        (_JUN, Decimal("8.00")),
    ]
    # The range is half-open: one ending where September starts leaves it out.
    assert prices_during(db, "TEA-1", _JUL, _SEP) == [(_JUN, Decimal("8.00"))]
    assert prices_during(db, "TEA-1", _MAY, _OCT) == [
        (_JAN, Decimal("10.00")),
        (_JUN, Decimal("8.00")),
        (_SEP, Decimal("10.00")),
    ]


def test_a_wire_document_reads_a_customer_ready_to_serialize(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    customer = json.loads(customer_as_json(db, 1))

    orders = sorted(customer.pop("orders"), key=lambda order: order["id"])
    assert customer == {"id": 1, "name": "Ada", "email": "ada@example.com"}
    assert orders == [
        {"id": 10, "customerId": 1, "placedOn": "2024-04-01", "total": "150.00", "version": 1},
        {"id": 11, "customerId": 1, "placedOn": "2024-04-09", "total": "20.00", "version": 1},
    ]


# --------------------------------------------------------------------------- #
# Database-free run-through of every recipe body.                              #
# --------------------------------------------------------------------------- #
class _ScriptedPort(ConnectsAsItself):
    """A fake `m-db-port` answering successive reads with scripted rows, then
    none, every write with one affected row, and every boundary by committing."""

    dialect: Dialect = POSTGRES

    def __init__(self, *reads: Sequence[Mapping[str, object]]) -> None:
        self.reads = list(reads)

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        answered = self.reads.pop(0) if self.reads else ()
        return [projected_row(sql, row, document_reads) for row in answered]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return 1

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        return Committed(body(cast("DatabaseConnection", self)))


_CUSTOMER_ROW: Mapping[str, object] = {"id": 1, "name": "Ada", "email": "ada@example.com"}
_ORDER_ROW: Mapping[str, object] = {
    "id": 10,
    "customer_id": 1,
    "placed_on": dt.date(2024, 4, 1),
    "total": Decimal("150.00"),
    "version": 1,
}
_CREDIT_LIMIT_ROW: Mapping[str, object] = {
    "customer_id": 1,
    "amount": Decimal("1000.00"),
    "in_z": _JAN,
    "out_z": INFINITY,
}
_PRICE_ROW: Mapping[str, object] = {
    "sku": "TEA-1",
    "amount": Decimal("10.00"),
    "from_z": _JAN,
    "thru_z": INFINITY,
    "in_z": _JAN,
    "out_z": INFINITY,
}

_PRODUCT_ROW: Mapping[str, object] = {
    "sku": "TEA-1",
    "payload": {"name": "Green tea", "description": None},
}
_DAMAGED_PRODUCT_ROW: Mapping[str, object] = {"sku": "TEA-2", "payload": {"description": "Oolong"}}


def test_the_first_program_runs_through_the_shipped_surface() -> None:
    model = DomainModel(Customer, Order)
    statements = table_statements(model)
    assert [statement.split(" (")[0] for statement in statements] == [
        "create table customer",
        "create table orders",
        "create index pxi_orders_order_orders_custom_b818642dd60617fc200f3b8e1a175ccb on orders",
    ]

    adapter = configure_the_database("postgresql://shop@localhost/shop", "s3cret")
    assert type(adapter) is PostgresAdapter

    customer = add_and_find_a_customer(cast("PostgresAdapter", _ScriptedPort([_CUSTOMER_ROW])))
    assert customer.name == "Ada"


def _over_one_hundred(db: ScopedDatabase) -> Any:
    return customers_with_an_order_over(db, Decimal("100.00"))


def _over_one_hundred_as_wire(db: ScopedDatabase) -> Any:
    return customers_with_an_order_over_as_wire(db, Decimal("100.00"))


def _limit_on_the_first_of_february(db: ScopedDatabase) -> Decimal:
    return credit_limit_on_record(db, 1, dt.datetime(2024, 2, 1, tzinfo=dt.UTC))


def _shipments_to_oslo(db: ScopedDatabase) -> list[Shipment]:
    return shipments_to(db, "Oslo")


def _payments_for_order_ten(db: ScopedDatabase) -> list[Payment]:
    return payments_for(db, 10)


def _products_named_green_tea(db: ScopedDatabase) -> list[Product]:
    return products_named(db, "Green tea")


def _look_up_customer_one(db: ScopedDatabase) -> Customer:
    return look_up_a_customer(db, 1)


def _amend_a_customer_read_earlier(db: ScopedDatabase) -> None:
    shown = look_up_a_customer(db, 1)
    with pytest.raises(ExecutionFailure):
        amend_a_value_read_earlier(db, shown, "ada@example.net")


def _amend_customer_one_after_reading_it_again(db: ScopedDatabase) -> None:
    amend_after_reading_it_again(db, 1, "ada@example.net")


def _orders_since_april(db: ScopedDatabase) -> list[Order]:
    return orders_with_their_customer(db, dt.date(2024, 4, 1))


def _customer_with_adas_email(db: ScopedDatabase) -> Customer | None:
    return customer_with_email(db, "ada@example.com")


def _orders_placed_on_the_first_of_april(db: ScopedDatabase) -> list[Order]:
    return orders_placed_on(db, dt.date(2024, 4, 1))


def _surcharge_every_order(db: ScopedDatabase) -> int:
    return add_a_surcharge_to_every_order(db, Decimal("5.00"), 10)


def _current_limit_of_customer_one(db: ScopedDatabase) -> Decimal:
    return current_credit_limit(db, 1)


def _limit_history_of_customer_one(db: ScopedDatabase) -> object:
    return credit_limit_history(db, 1)


def _tea_price_in_july(db: ScopedDatabase) -> Decimal:
    return price_on(db, "TEA-1", _JUL)


def _tea_price_in_july_as_recorded_in_march(db: ScopedDatabase) -> Decimal:
    return price_on_as_recorded_at(db, "TEA-1", _JUL, _MAR)


def _tea_prices_from_may_to_july(db: ScopedDatabase) -> object:
    return prices_during(db, "TEA-1", _MAY, _JUL)


def _customer_one_as_json(db: ScopedDatabase) -> str:
    return customer_as_json(db, 1)


@pytest.mark.parametrize(
    ("recipe", "reads"),
    [
        pytest.param(_over_one_hundred, ([_CUSTOMER_ROW], [_ORDER_ROW]), id="relationship-filter"),
        pytest.param(_over_one_hundred_as_wire, ([_CUSTOMER_ROW], [_ORDER_ROW]), id="wire-read"),
        pytest.param(place_an_order, ([_CUSTOMER_ROW],), id="insert-and-amend"),
        pytest.param(_limit_on_the_first_of_february, ([_CREDIT_LIMIT_ROW],), id="as-of-read"),
        pytest.param(run_a_summer_sale, ([_PRICE_ROW], [_PRICE_ROW]), id="bounded-amendment"),
        pytest.param(_shipments_to_oslo, (), id="value-object-filter"),
        pytest.param(_payments_for_order_ten, (), id="family-read"),
        pytest.param(_products_named_green_tea, (), id="document-layout-read"),
        pytest.param(_look_up_customer_one, ([_CUSTOMER_ROW],), id="one-off-lookup"),
        pytest.param(
            customers_and_orders_one_read_at_a_time,
            ([_CUSTOMER_ROW], [_ORDER_ROW]),
            id="standalone-reads",
        ),
        pytest.param(
            customers_and_orders_from_one_snapshot,
            ([_CUSTOMER_ROW], [_ORDER_ROW]),
            id="read-only-reads",
        ),
        pytest.param(_amend_a_customer_read_earlier, ([_CUSTOMER_ROW],), id="amend-refused"),
        pytest.param(
            _amend_customer_one_after_reading_it_again, ([_CUSTOMER_ROW],), id="amend-re-read"
        ),
        pytest.param(
            _orders_since_april, ([_ORDER_ROW], [_CUSTOMER_ROW], [_ORDER_ROW]), id="graph"
        ),
        pytest.param(_customer_with_adas_email, ([_CUSTOMER_ROW],), id="optional-one"),
        pytest.param(_orders_placed_on_the_first_of_april, ([_ORDER_ROW],), id="many"),
        pytest.param(
            products_and_unreadable_rows, ([_PRODUCT_ROW, _DAMAGED_PRODUCT_ROW],), id="checked-read"
        ),
        pytest.param(_surcharge_every_order, ([_ORDER_ROW],), id="stream-and-amend"),
        pytest.param(_current_limit_of_customer_one, ([_CREDIT_LIMIT_ROW],), id="latest"),
        pytest.param(_limit_history_of_customer_one, ([_CREDIT_LIMIT_ROW],), id="history"),
        pytest.param(_tea_price_in_july, ([_PRICE_ROW],), id="valid-time"),
        pytest.param(_tea_price_in_july_as_recorded_in_march, ([_PRICE_ROW],), id="both-axes"),
        pytest.param(_tea_prices_from_may_to_july, ([_PRICE_ROW],), id="valid-time-range"),
        pytest.param(_customer_one_as_json, ([_CUSTOMER_ROW], [_ORDER_ROW]), id="wire-document"),
    ],
)
def test_every_recipe_runs_through_the_shipped_surface(
    recipe: Callable[[ScopedDatabase], object], reads: tuple[Sequence[Mapping[str, object]], ...]
) -> None:
    recipe(own_root(Database.connect(_ScriptedPort(*reads), SHOP_MODEL)).using_database_login())


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(guide_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            add_a_surcharge_to_every_order,
            add_and_find_a_customer,
            amend_a_value_read_earlier,
            amend_after_reading_it_again,
            configure_the_database,
            credit_limit_history,
            credit_limit_on_record,
            current_credit_limit,
            customer_as_json,
            customer_with_email,
            customers_and_orders_from_one_snapshot,
            customers_and_orders_one_read_at_a_time,
            customers_with_an_order_over,
            customers_with_an_order_over_as_wire,
            look_up_a_customer,
            orders_placed_on,
            orders_with_their_customer,
            payments_for,
            place_an_order,
            price_on,
            price_on_as_recorded_at,
            prices_during,
            products_and_unreadable_rows,
            products_named,
            run_a_summer_sale,
            shipments_to,
            table_statements,
        )
    )


def _bound_and_loaded(source: str) -> tuple[set[str], set[str]]:
    """Every name ``source`` binds and every name it reads, scope-blind."""
    bound: set[str] = set()
    loaded: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name):
            (bound if isinstance(node.ctx, ast.Store) else loaded).add(node.id)
    return bound, loaded


def test_the_getting_started_imports_bind_every_name_its_snippets_read() -> None:
    # Getting started is the one page a reader copies whole, so its import block
    # has to resolve and has to cover every name the snippets after it use.
    sources = snippet_sources()
    imports = sources["getting-started-imports"]
    exec(compile(imports, "getting-started-imports", "exec"), {})
    shown = "\n\n".join(
        sources[source_id]
        for source_id in (
            "getting-started-imports",
            "declare-customers-and-orders",
            "create-tables-from-the-model",
            "connect-and-run-a-first-transaction",
        )
    )
    bound, loaded = _bound_and_loaded(shown)

    assert loaded - bound - set(dir(builtins)) == set()
