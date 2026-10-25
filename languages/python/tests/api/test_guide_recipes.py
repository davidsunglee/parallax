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
import io
import json
import re
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance import case_format, guide_models, guide_recipes
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
    a_scope_for_reports,
    add_a_customer_from_json,
    add_a_surcharge_to_every_order,
    add_and_find_a_customer,
    add_to_an_order,
    add_to_an_order_once,
    add_to_an_order_under_a_lock,
    amend_a_value_read_earlier,
    amend_after_reading_it_again,
    cancel_an_order,
    cancel_reviewed_orders,
    cancel_unless_changed,
    card_payments_ending_in,
    card_payments_over,
    change_a_credit_limit,
    change_a_limit_shown_earlier,
    change_a_price_from,
    change_a_reviewed_limit,
    change_a_reviewed_total,
    change_a_reviewed_total_within_the_limit,
    change_an_email,
    configure_the_database,
    connect_with_transaction_defaults,
    correct_a_past_price,
    correct_a_price_as_recorded_then,
    credit_limit_history,
    credit_limit_on_record,
    current_credit_limit,
    customer_as_json,
    customer_for_page_and_api,
    customer_with_email,
    customer_with_their_orders,
    customers_and_orders_from_one_snapshot,
    customers_and_orders_one_read_at_a_time,
    customers_named,
    customers_with_a_large_recent_order,
    customers_with_a_recent_order_and_a_large_one,
    customers_with_an_order_over,
    customers_with_an_order_over_as_wire,
    delete_the_shipments_of,
    discontinue_a_tea,
    export_customers,
    forget_an_email_address,
    grant_a_credit_limit,
    largest_orders_since,
    list_a_seasonal_tea,
    list_a_tea,
    look_up_a_customer,
    open_an_account,
    open_an_account_even_if_the_order_fails,
    orders_of,
    orders_placed_on,
    orders_with_their_customer,
    payments_for,
    place_an_order,
    place_an_order_within_the_limit,
    place_two_orders,
    place_two_orders_together,
    place_two_orders_together_serializably,
    price_on,
    price_on_as_recorded_at,
    prices_during,
    products_and_unreadable_rows,
    products_named,
    record_an_order,
    register_a_customer,
    rename_a_customer_through_wire,
    replace_contact_details,
    reprice_a_tea_for,
    reprice_from_a_review,
    run_a_summer_sale,
    shipments_to,
    table_statements,
    total_of_every_order,
    who_placed,
    withdraw_a_credit_limit,
)
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.conformance.usage_guide import snippet_sources
from parallax.core import LATEST, TX_TIME, VALID_TIME, DomainModel
from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind, Committed, DatabaseConnection, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import model_of
from parallax.core.execution import (
    ExecutionFailure,
    TransactionAccessModeError,
    TransactionOptionConflictError,
    TransactionTimePinReadOnlyError,
    TxnOptions,
)
from parallax.core.execution_lifecycle import (
    AttemptCommitted,
    AttemptRolledBack,
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    ReadFinished,
    RootExecution,
    TransactionAttemptFinished,
    TransactionAttemptOutcome,
    TransactionAttemptStarted,
)
from parallax.core.read_delivery import InvalidDataError
from parallax.core.unit_work import (
    InstructionRejectedError,
    OptimisticLockConflictError,
    RollbackOnlyError,
    WriteEvidenceError,
    WriteInstructionError,
    WritePreconditionError,
)
from parallax.postgres import PostgresAdapter
from parallax.snapshot import (
    Database,
    NoResultFound,
    ReadOnlyTxnContext,
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


def _seed_the_first_three_price_transactions(profile_run: Any) -> ScopedDatabase:
    # The worked example's first three transactions: the listing, the April rise
    # and the summer sale, recorded on the dates Reading's timeline names.
    db = _shop(profile_run, clock=ScriptedClock([_T1, _T3, _T4]))
    list_a_tea(db, "TEA-1", Decimal("10.00"), _JAN)
    change_a_price_from(db, "TEA-1", Decimal("12.00"), _APR)
    run_a_summer_sale(db)
    return db


def test_a_bitemporal_read_answers_on_either_axis(profile_run: Any) -> None:
    db = _seed_the_first_three_price_transactions(profile_run)

    assert price_on(db, "TEA-1", _JUL) == Decimal("8.00")
    assert price_on(db, "TEA-1", _OCT) == Decimal("12.00")
    # In March the database knew of the rise but not yet of the sale.
    assert price_on_as_recorded_at(db, "TEA-1", _JUL, _MAR) == Decimal("12.00")
    assert price_on_as_recorded_at(db, "TEA-1", _JUL, _JAN) == Decimal("10.00")
    assert price_on_as_recorded_at(db, "TEA-1", _JUL, _JUN) == Decimal("8.00")


def test_a_valid_time_range_returns_each_price_in_effect(profile_run: Any) -> None:
    db = _seed_the_first_three_price_transactions(profile_run)

    assert prices_during(db, "TEA-1", _MAY, _JUL) == [
        (_APR, Decimal("12.00")),
        (_JUN, Decimal("8.00")),
    ]
    # The range is half-open: one ending where September starts leaves it out.
    assert prices_during(db, "TEA-1", _JUL, _SEP) == [(_JUN, Decimal("8.00"))]
    assert prices_during(db, "TEA-1", _MAY, _OCT) == [
        (_APR, Decimal("12.00")),
        (_JUN, Decimal("8.00")),
        (_SEP, Decimal("12.00")),
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


def test_a_read_in_the_inserting_transaction_sees_the_pending_insert(profile_run: Any) -> None:
    db = _shop(profile_run)

    registered = register_a_customer(db, 5, "Barbara")

    assert (registered.id, registered.name, registered.email) == (5, "Barbara", None)
    assert look_up_a_customer(db, 5) == registered


def test_an_amendment_writes_the_edited_member_and_a_replacement_writes_them_all(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    change_an_email(db, 1, "ada@example.org")

    assert (look_up_a_customer(db, 1).name, look_up_a_customer(db, 1).email) == (
        "Ada",
        "ada@example.org",
    )

    replace_contact_details(db, 1, "Ada King")

    assert (look_up_a_customer(db, 1).name, look_up_a_customer(db, 1).email) == (
        "Ada King",
        "ada@example.org",
    )


def test_an_assignment_amends_an_order_and_advances_its_version(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    add_to_an_order(db, 10, Decimal("7.50"))

    order = db.find(Order.where(Order.id == 10)).result()
    assert (order.total, order.version) == (Decimal("157.50"), 2)


def test_a_delete_removes_the_order_its_transaction_read(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    cancel_an_order(db, 11)

    assert sorted(order.id for order in db.find(Order.where(Order.all)).results()) == [10, 12]


_T1 = dt.datetime(2023, 12, 15, tzinfo=dt.UTC)
_T2 = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)
_T3 = dt.datetime(2024, 2, 15, tzinfo=dt.UTC)
_T4 = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
_T5 = dt.datetime(2024, 6, 20, tzinfo=dt.UTC)
_T6 = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)
_T7 = dt.datetime(2024, 11, 15, tzinfo=dt.UTC)
_APR = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
_DEC = dt.datetime(2024, 12, 1, tzinfo=dt.UTC)


def test_transaction_time_only_writes_append_milestones(profile_run: Any) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_T1, _T2, _T3, _T4]))

    grant_a_credit_limit(db, 1, Decimal("1000.00"))
    change_a_credit_limit(db, 1, Decimal("2500.00"))

    query = CreditLimit.where(CreditLimit.customer_id == 1)
    assert [
        (limit.amount, limit.tx_start, limit.tx_end)
        for limit in db.find(query.history(TX_TIME)).results()
    ] == [(Decimal("1000.00"), _T1, _T2), (Decimal("2500.00"), _T2, INFINITY)]

    def delete_the_limit(tx: TxnContext) -> None:
        tx.delete(tx.find(CreditLimit.where(CreditLimit.customer_id == 1)).result())

    with pytest.raises(ExecutionFailure) as refused:
        db.transact(delete_the_limit)
    assert isinstance(refused.value.cause, WriteInstructionError)
    assert "terminate" in str(refused.value.cause)

    withdraw_a_credit_limit(db, 1)

    assert db.find(query).result_or_none() is None
    assert credit_limit_on_record(db, 1, dt.datetime(2024, 2, 1, tzinfo=dt.UTC)) == Decimal(
        "2500.00"
    )
    assert [
        (limit.amount, limit.tx_start, limit.tx_end)
        for limit in db.find(query.history(TX_TIME)).results()
    ] == [(Decimal("1000.00"), _T1, _T2), (Decimal("2500.00"), _T2, _T3)]

    # The same customer can be granted a limit again; it opens after the old ones.
    grant_a_credit_limit(db, 1, Decimal("500.00"))
    assert [
        (limit.amount, limit.tx_start, limit.tx_end)
        for limit in db.find(query.history(TX_TIME)).results()
    ] == [
        (Decimal("1000.00"), _T1, _T2),
        (Decimal("2500.00"), _T2, _T3),
        (Decimal("500.00"), _T4, INFINITY),
    ]


type _Milestone = tuple[Decimal, dt.datetime, object, dt.datetime, object]


def _price_milestones(db: ScopedDatabase, sku: str) -> set[_Milestone]:
    """Every stored row of ``sku``: its amount, Valid-Time extent and Transaction-Time extent."""
    query = Price.where(Price.sku == sku).history(TX_TIME).history(VALID_TIME)
    return {
        (price.amount, price.valid_start, price.valid_end, price.tx_start, price.tx_end)
        for price in db.find(query).results()
    }


def test_the_bitemporal_worked_example_stores_the_rows_its_timelines_draw(
    profile_run: Any,
) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_T1, _T2, _T3, _T4, _T5, _T6, _T7]))
    ten, twelve = Decimal("10.00"), Decimal("12.00")

    list_a_tea(db, "TEA-1", ten, _JAN)
    assert _price_milestones(db, "TEA-1") == {(ten, _JAN, INFINITY, _T1, INFINITY)}

    list_a_seasonal_tea(db, "TEA-2", Decimal("6.00"), _JUN, _SEP)
    assert _price_milestones(db, "TEA-2") == {(Decimal("6.00"), _JUN, _SEP, _T2, INFINITY)}
    # No window of the summer blend stays open, so the latest Valid Time finds nothing.
    latest = Price.where(Price.sku == "TEA-2").as_of(valid_time=LATEST)
    assert db.find(latest).result_or_none() is None
    # A Bitemporal insert must say where it starts.
    with pytest.raises(ExecutionFailure) as refused:
        db.transact(lambda tx: tx.insert(Price(sku="TEA-3", amount=Decimal("5.00"))))
    assert isinstance(refused.value.cause, WriteInstructionError)

    change_a_price_from(db, "TEA-1", twelve, _APR)
    first_year = {
        (ten, _JAN, INFINITY, _T1, _T3),
        (ten, _JAN, _APR, _T3, INFINITY),
    }
    assert _price_milestones(db, "TEA-1") == first_year | {(twelve, _APR, INFINITY, _T3, INFINITY)}
    assert (
        price_on_as_recorded_at(db, "TEA-1", _MAY, dt.datetime(2024, 1, 20, tzinfo=dt.UTC)) == ten
    )

    run_a_summer_sale(db)
    summer = {
        (twelve, _APR, INFINITY, _T3, _T4),
        (twelve, _APR, _JUN, _T4, INFINITY),
        (Decimal("8.00"), _JUN, _SEP, _T4, INFINITY),
    }
    assert _price_milestones(db, "TEA-1") == first_year | summer | {
        (twelve, _SEP, INFINITY, _T4, INFINITY)
    }

    reprice_a_tea_for(db, "TEA-2", Decimal("7.00"), _JUL, _OCT)
    # The replacement's window reaches past September, where nothing was stored,
    # and its state there merges with the repriced piece into one row.
    assert _price_milestones(db, "TEA-2") == {
        (Decimal("6.00"), _JUN, _SEP, _T2, _T5),
        (Decimal("6.00"), _JUN, _JUL, _T5, INFINITY),
        (Decimal("7.00"), _JUL, _OCT, _T5, INFINITY),
    }

    discontinue_a_tea(db, "TEA-1", _DEC)
    autumn = {
        (twelve, _SEP, INFINITY, _T4, _T6),
        (twelve, _SEP, _DEC, _T6, INFINITY),
    }
    assert _price_milestones(db, "TEA-1") == first_year | summer | autumn
    assert (
        db.find(Price.where(Price.sku == "TEA-1").as_of(valid_time=_DEC)).result_or_none() is None
    )

    correct_a_past_price(db, "TEA-1", Decimal("9.50"), _JAN, _APR)
    assert (
        _price_milestones(db, "TEA-1")
        == {
            (ten, _JAN, INFINITY, _T1, _T3),
            (ten, _JAN, _APR, _T3, _T7),
            (Decimal("9.50"), _JAN, _APR, _T7, INFINITY),
        }
        | summer
        | autumn
    )

    february = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    assert price_on(db, "TEA-1", february) == Decimal("9.50")
    assert price_on_as_recorded_at(db, "TEA-1", february, _T6) == ten


def test_a_value_read_at_a_past_transaction_time_cannot_be_corrected(profile_run: Any) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_T1, _T3]))
    list_a_tea(db, "TEA-1", Decimal("10.00"), _JAN)
    change_a_price_from(db, "TEA-1", Decimal("12.00"), _APR)
    stored = _price_milestones(db, "TEA-1")

    with pytest.raises(ExecutionFailure) as refused:
        correct_a_price_as_recorded_then(db, "TEA-1", Decimal("9.50"), _JAN, _APR, _T2)

    assert isinstance(refused.value.cause, TransactionTimePinReadOnlyError)
    assert refused.value.cause.code == "transaction-time-pin-read-only"
    assert _price_milestones(db, "TEA-1") == stored


def test_an_amendment_over_a_window_leaves_uncovered_valid_time_uncovered(
    profile_run: Any,
) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_T2, _T5]))
    list_a_seasonal_tea(db, "TEA-2", Decimal("6.00"), _JUN, _SEP)

    correct_a_past_price(db, "TEA-2", Decimal("7.00"), _JUL, _OCT)

    assert _price_milestones(db, "TEA-2") == {
        (Decimal("6.00"), _JUN, _SEP, _T2, _T5),
        (Decimal("6.00"), _JUN, _JUL, _T5, INFINITY),
        (Decimal("7.00"), _JUL, _SEP, _T5, INFINITY),
    }


def test_a_target_write_applies_only_at_the_revision_its_caller_states(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)
    reviewed = db.find(Order.where(Order.id == 10)).result()

    change_a_reviewed_total(db, reviewed, Decimal("140.00"))

    order = db.find(Order.where(Order.id == 10)).result()
    assert (order.total, order.version) == (Decimal("140.00"), 2)
    # The same review, stated again, no longer matches the stored version.
    with pytest.raises(ExecutionFailure) as refused:
        change_a_reviewed_total(db, reviewed, Decimal("130.00"))
    assert isinstance(refused.value.cause, WritePreconditionError)
    assert refused.value.cause.expected == 1
    assert db.find(Order.where(Order.id == 10)).result().total == Decimal("140.00")


def test_a_temporal_target_write_states_the_milestone_start_it_saw(profile_run: Any) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_T1, _T2, _T3]))
    grant_a_credit_limit(db, 1, Decimal("1000.00"))
    reviewed = db.find(CreditLimit.where(CreditLimit.customer_id == 1)).result()

    change_a_reviewed_limit(db, reviewed, Decimal("1500.00"))

    assert current_credit_limit(db, 1) == Decimal("1500.00")
    with pytest.raises(ExecutionFailure) as refused:
        change_a_reviewed_limit(db, reviewed, Decimal("2000.00"))
    assert isinstance(refused.value.cause, WritePreconditionError)
    assert refused.value.cause.expected == _T1
    assert current_credit_limit(db, 1) == Decimal("1500.00")


def test_reviewed_orders_are_cancelled_unless_they_changed_since(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)
    reviewed = db.find(Order.where(Order.all).order_by(Order.id.asc())).results()
    add_to_an_order(db, 11, Decimal("1.00"))

    changed = cancel_reviewed_orders(db, reviewed)

    assert changed == [11]
    assert [order.id for order in db.find(Order.where(Order.all)).results()] == [11]


def test_a_target_write_to_an_unversioned_entity_is_refused(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    with pytest.raises(ExecutionFailure) as refused:
        db.transact(
            lambda tx: tx.amend_if(
                Customer, Customer.email.set("ada@example.org"), key=1, version=1
            )
        )

    assert isinstance(refused.value.cause, WriteInstructionError)


def test_predicate_writes_run_at_the_call_and_answer_their_row_count(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)
    db.transact(
        lambda tx: (
            tx.insert(Customer(id=3, name="Ada", email="ada@example.com")),
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
                    order_id=10,
                    ship_to=Address(street="1 Fjord Vei", city="Bergen", postcode="5003"),
                    tracking_number="TRK-2",
                )
            ),
        )
    )

    assert forget_an_email_address(db, "ada@example.com") == 2
    assert forget_an_email_address(db, "nobody@example.com") == 0
    assert [customer.email for customer in db.find(Customer.where(Customer.all)).results()] == [
        None,
        None,
        None,
    ]
    assert delete_the_shipments_of(db, 10) == 2
    assert db.find(Shipment.where(Shipment.all)).results() == []


def test_a_predicate_write_to_a_versioned_entity_is_refused(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    with pytest.raises(ExecutionFailure) as refused:
        db.transact(
            lambda tx: tx.amend_where(Order.where(Order.all), Order.total.set(Decimal("0.00")))
        )

    assert isinstance(refused.value.cause, InstructionRejectedError)
    assert refused.value.cause.rule == "set-based-write-target-unsupported"


def test_wire_writes_insert_from_json_and_amend_a_node_read_in_the_transaction(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)

    add_a_customer_from_json(db, '{"id": 4, "name": "Edsger", "email": null}')
    rename_a_customer_through_wire(db, 4, "Edsger Dijkstra")

    customer = look_up_a_customer(db, 4)
    assert (customer.name, customer.email) == ("Edsger Dijkstra", None)


def test_a_read_only_call_inside_a_read_only_callback_joins_its_snapshot(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)
    _seed_customers(db)
    peer = own_root(connect(profile_run.port, SHOP_MODEL)).using_database_login()
    observer = _PeerCommitsAfterTheFirstRead(
        lambda: peer.transact(
            lambda tx: tx.insert(
                Order(id=13, customer_id=1, placed_on=dt.date(2024, 4, 5), total=Decimal("9.00"))
            )
        )
    )
    db = own_root(
        connect(profile_run.port, SHOP_MODEL, lifecycle_provider=observer)
    ).using_database_login()

    customer, orders = customer_with_their_orders(db, 1)

    # The peer committed after the customer was read; the joined read still sees
    # the transaction's snapshot, while a later read of its own sees the new order.
    assert customer.id == 1
    assert sorted(order.id for order in orders) == [10, 11]
    assert sorted(order.id for order in orders_of(db, 1)) == [10, 11, 13]


def test_a_writable_call_inside_a_read_only_callback_is_refused_and_leaves_it_usable(
    profile_run: Any,
) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    def read(rtx: ReadOnlyTxnContext) -> str:
        with pytest.raises(TransactionAccessModeError):
            db.transact(lambda tx: None)
        return rtx.find(Customer.where(Customer.id == 1)).result().name

    assert db.read_only(read) == "Ada"


def test_filters_sort_keys_and_a_limit_shape_a_query(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)
    db.transact(
        lambda tx: (
            tx.insert(Customer(id=3, name="Alan", email=None)),
            tx.insert(
                Order(id=14, customer_id=3, placed_on=dt.date(2024, 4, 5), total=Decimal("40.00"))
            ),
        )
    )

    # Orders 12 and 14 tie on their total; the second sort key orders them.
    assert [order.id for order in largest_orders_since(db, dt.date(2024, 4, 2), 2)] == [12, 14]
    assert [order.id for order in largest_orders_since(db, dt.date(2024, 4, 2), 5)] == [
        12,
        14,
        11,
    ]
    assert [customer.name for customer in customers_named(db, "A")] == ["Ada"]


def test_one_quantifier_needs_one_order_to_satisfy_both_conditions(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)
    since, minimum = dt.date(2024, 4, 5), Decimal("100.00")

    # Ada's recent order is small and her large order is old.
    assert customers_with_a_large_recent_order(db, since, minimum) == []
    assert [
        customer.name
        for customer in customers_with_a_recent_order_and_a_large_one(db, since, minimum)
    ] == ["Ada"]
    assert [
        customer.name
        for customer in customers_with_a_large_recent_order(db, dt.date(2024, 4, 1), minimum)
    ] == ["Ada"]


def test_a_family_query_narrows_to_card_payments(profile_run: Any) -> None:
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

    (card,) = card_payments_ending_in(db, "4242")
    assert (type(card), card.id) == (CardPayment, 1)
    assert [payment.id for payment in card_payments_over(db, Decimal("30.00"))] == [1]
    over_ten = card_payments_over(db, Decimal("10.00"))
    assert sorted((payment.id, payment.card_last_four) for payment in over_ten) == [
        (1, "4242"),
        (3, "1111"),
    ]


def test_an_unloaded_customer_is_told_apart_from_a_missing_one(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)
    db.transact(
        lambda tx: tx.insert(
            Order(id=15, customer_id=99, placed_on=dt.date(2024, 4, 6), total=Decimal("5.00"))
        )
    )
    included = Order.where(Order.id.in_([10, 15])).include(Order.customer).order_by(Order.id.asc())

    assert [who_placed(order) for order in db.find(included).results()] == ["Ada", "no customer"]
    assert who_placed(db.find(Order.where(Order.id == 10)).result()) == "not loaded"


@pytest.mark.parametrize("page", [1, 2, 100])
def test_a_stream_adds_up_every_order(profile_run: Any, page: int) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    assert total_of_every_order(db, page) == Decimal("210.00")


def test_a_wire_stream_exports_one_json_line_per_customer(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)
    out = io.StringIO()

    assert export_customers(db, out, 1) == 2

    exported = {line["id"]: line for line in map(json.loads, out.getvalue().splitlines())}
    assert sorted(exported) == [1, 2]
    assert sorted(order["id"] for order in exported[1]["orders"]) == [10, 11]
    assert exported[2]["email"] is None


def test_a_typed_result_projects_to_the_same_graph_as_wire_data(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    customer, payload = customer_for_page_and_api(db, 1)

    assert (customer.id, payload["id"], payload["name"]) == (1, 1, "Ada")
    orders = cast("Sequence[WireEntity]", payload["orders"])
    assert sorted(cast("int", order["id"]) for order in orders) == sorted(
        order.id for order in customer.orders
    )


def test_a_bitemporal_target_write_states_the_milestone_its_review_read(
    profile_run: Any,
) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_T1, _T3, _T4]))
    list_a_tea(db, "TEA-1", Decimal("10.00"), _JAN)
    reviewed = db.find(Price.where(Price.sku == "TEA-1").as_of(valid_time=_APR)).result()

    reprice_from_a_review(db, reviewed, Decimal("12.00"), _APR)

    assert _price_milestones(db, "TEA-1") == {
        (Decimal("10.00"), _JAN, INFINITY, _T1, _T3),
        (Decimal("10.00"), _JAN, _APR, _T3, INFINITY),
        (Decimal("12.00"), _APR, INFINITY, _T3, INFINITY),
    }
    with pytest.raises(ExecutionFailure) as refused:
        reprice_from_a_review(db, reviewed, Decimal("13.00"), _APR)
    assert isinstance(refused.value.cause, WritePreconditionError)
    assert refused.value.cause.expected == _T1


def test_a_wire_target_write_states_the_milestone_an_earlier_wire_read_showed(
    profile_run: Any,
) -> None:
    db = _shop(profile_run, clock=ScriptedClock([_T1, _T2, _T3]))
    grant_a_credit_limit(db, 1, Decimal("1000.00"))
    shown = db.wire.find(CreditLimit.where(CreditLimit.customer_id == 1)).result()

    change_a_limit_shown_earlier(db, shown, "1500.00")

    assert current_credit_limit(db, 1) == Decimal("1500.00")
    with pytest.raises(ExecutionFailure) as refused:
        change_a_limit_shown_earlier(db, shown, "2000.00")
    assert isinstance(refused.value.cause, WritePreconditionError)
    assert current_credit_limit(db, 1) == Decimal("1500.00")


class _PeerCommitsDuringAttempts:
    """A lifecycle provider that lets another session commit ``work`` right after
    the first read of the first attempt, or of every attempt, and records how
    each attempt of the transactions it observes ended."""

    def __init__(self, work: Callable[[], object], *, every_attempt: bool = False) -> None:
        self._work = work
        self._every_attempt = every_attempt
        self._armed = False
        self._fired = False
        self.attempts: list[str] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler:
        return self

    def handle(self, event: ExecutionEvent, /) -> None:
        if isinstance(event, TransactionAttemptStarted):
            self._armed = self._every_attempt or not self._fired
        elif isinstance(event, ReadFinished) and self._armed:
            self._armed, self._fired = False, True
            commit_as_a_peer(self._work)
        elif isinstance(event, TransactionAttemptFinished):
            self.attempts.append(_how_the_attempt_ended(event.outcome))

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(error)


def _how_the_attempt_ended(outcome: TransactionAttemptOutcome) -> str:
    if isinstance(outcome, AttemptCommitted):
        return "committed"
    assert isinstance(outcome, AttemptRolledBack)
    failed = outcome.failure
    verdict = "retried" if failed.retry_eligible else "not retried"
    return f"{failed.failure.diagnostic.qualified_type.rsplit('.', 1)[-1]}, {verdict}"


def _observed(
    profile_run: Any, work: Callable[[ScopedDatabase], object], *, every_attempt: bool = False
) -> tuple[ScopedDatabase, _PeerCommitsDuringAttempts]:
    """A scope whose transaction attempts let ``work`` commit, through a peer root,
    right after their first read."""
    peer = own_root(connect(profile_run.port, SHOP_MODEL)).using_database_login()
    observer = _PeerCommitsDuringAttempts(lambda: work(peer), every_attempt=every_attempt)
    db = own_root(
        connect(profile_run.port, SHOP_MODEL, lifecycle_provider=observer)
    ).using_database_login()
    return db, observer


def _order(order_id: int, customer_id: int, total: str) -> Order:
    return Order(
        id=order_id, customer_id=customer_id, placed_on=dt.date(2024, 5, 1), total=Decimal(total)
    )


def _seed_customers_and_a_limit(profile_run: Any) -> ScopedDatabase:
    db = _shop(profile_run)
    _seed_customers(db)
    grant_a_credit_limit(db, 1, Decimal("250.00"))
    return db


def test_a_helper_joins_its_callers_transaction_and_commits_with_it(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    opened = open_an_account(db, Customer(id=3, name="Edsger", email=None), _order(13, 3, "9.00"))

    assert (opened.id, opened.name) == (3, "Edsger")
    assert [order.id for order in orders_of(db, 3)] == [13]

    # Order 10 exists already, so the joined insert fails, and the customer the
    # outer callback inserted is rolled back with it.
    with pytest.raises(ExecutionFailure):
        open_an_account(db, Customer(id=4, name="Barbara", email=None), _order(10, 4, "9.00"))
    assert db.find(Customer.where(Customer.id == 4)).result_or_none() is None


def test_a_caught_joined_failure_still_rolls_the_transaction_back(profile_run: Any) -> None:
    db = _shop(profile_run)
    _seed_customers(db)

    assert open_an_account_even_if_the_order_fails(
        db, Customer(id=3, name="Edsger", email=None), _order(13, 3, "9.00")
    )
    assert look_up_a_customer(db, 3).name == "Edsger"

    with pytest.raises(ExecutionFailure) as refused:
        open_an_account_even_if_the_order_fails(
            db, Customer(id=4, name="Barbara", email=None), _order(14, 4, "0.00")
        )

    assert isinstance(refused.value.cause, RollbackOnlyError)
    assert isinstance(refused.value.cause.__cause__, ValueError)
    assert db.find(Customer.where(Customer.id == 4)).result_or_none() is None


def test_serializable_keeps_two_concurrent_orders_within_the_limit(profile_run: Any) -> None:
    _seed_customers_and_a_limit(profile_run)
    peer_placed: list[bool] = []
    db, observer = _observed(
        profile_run,
        lambda peer: peer_placed.append(
            place_an_order_within_the_limit(peer, _order(20, 1, "50.00"))
        ),
    )

    # Orders 10 and 11 total 170.00 against a limit of 250.00, so either new
    # order fits alone but not both. The peer commits between this
    # transaction's reads and its insert, so its first attempt fails to
    # serialize; the retry sees the peer's order and declines.
    placed = place_an_order_within_the_limit(db, _order(21, 1, "60.00"))

    assert peer_placed == [True]
    assert placed is False
    assert observer.attempts == ["DatabaseError, retried", "committed"]
    assert sorted(order.id for order in orders_of(db, 1)) == [10, 11, 20]


def test_a_write_another_writer_overtook_is_replayed_from_a_fresh_read(profile_run: Any) -> None:
    _seed_customers(_shop(profile_run))
    db, observer = _observed(profile_run, lambda peer: add_to_an_order(peer, 10, Decimal("5.00")))

    add_to_an_order(db, 10, Decimal("20.00"))

    assert observer.attempts == ["OptimisticLockConflictError, retried", "committed"]
    order = db.find(Order.where(Order.id == 10)).result()
    assert (order.total, order.version) == (Decimal("175.00"), 3)


def test_a_conflict_on_every_attempt_exhausts_ten_retries(profile_run: Any) -> None:
    _seed_customers(_shop(profile_run))
    db, observer = _observed(
        profile_run, lambda peer: add_to_an_order(peer, 10, Decimal("1.00")), every_attempt=True
    )

    with pytest.raises(ExecutionFailure) as exhausted:
        add_to_an_order(db, 10, Decimal("20.00"))

    assert isinstance(exhausted.value.cause, OptimisticLockConflictError)
    assert exhausted.value.cause.__notes__ == [
        "bounded retry exhausted after 11 attempts (retries=10)"
    ]
    assert observer.attempts == ["OptimisticLockConflictError, retried"] * 11
    assert db.find(Order.where(Order.id == 10)).result().total == Decimal("161.00")


def test_a_locking_transaction_holds_its_read_lock_until_it_ends(profile_run: Any) -> None:
    _seed_customers(_shop(profile_run))
    refused: list[DatabaseError] = []

    def write_the_order_elsewhere(_: ScopedDatabase) -> None:
        with contextlib.closing(profile_run.control()) as control:
            control.execute_write("set lock_timeout = '200ms'", ())
            try:
                control.execute_write("update orders set total = total where id = 10", ())
            except DatabaseError as timed_out:
                refused.append(timed_out)

    db, observer = _observed(profile_run, write_the_order_elsewhere)

    add_to_an_order_under_a_lock(db, 10, Decimal("20.00"))

    assert [error.category for error in refused] == ["lockWaitTimeout"]
    assert observer.attempts == ["committed"]
    order = db.find(Order.where(Order.id == 10)).result()
    assert (order.total, order.version) == (Decimal("170.00"), 2)


def test_a_retried_target_write_fails_the_precondition_it_states_again(profile_run: Any) -> None:
    reviewed = _seed_customers_and_a_limit(profile_run).find(Order.where(Order.id == 10)).result()
    db, observer = _observed(profile_run, lambda peer: add_to_an_order(peer, 10, Decimal("5.00")))

    # The first attempt's write meets a row the peer changed after its
    # Serializable snapshot, which fails to serialize and is retried; the retry
    # states the same version, which no longer holds, and is not retried.
    with pytest.raises(ExecutionFailure) as refused:
        change_a_reviewed_total_within_the_limit(db, reviewed, Decimal("160.00"))

    assert isinstance(refused.value.cause, WritePreconditionError)
    assert observer.attempts == ["DatabaseError, retried", "WritePreconditionError, not retried"]
    assert db.find(Order.where(Order.id == 10)).result().total == Decimal("155.00")
    assert change_a_reviewed_total_within_the_limit(db, reviewed, Decimal("300.00")) is False


def test_a_single_attempt_surfaces_the_conflict_unretried(profile_run: Any) -> None:
    _seed_customers(_shop(profile_run))
    db, observer = _observed(profile_run, lambda peer: add_to_an_order(peer, 10, Decimal("5.00")))

    with pytest.raises(ExecutionFailure) as conflicted:
        add_to_an_order_once(db, 10, Decimal("20.00"))

    assert isinstance(conflicted.value.cause, OptimisticLockConflictError)
    assert conflicted.value.cause.__notes__ == [
        "bounded retry exhausted after 1 attempts (retries=0)"
    ]
    assert observer.attempts == ["OptimisticLockConflictError, retried"]
    assert db.find(Order.where(Order.id == 10)).result().total == Decimal("155.00")


def test_root_and_scope_defaults_resolve_each_transactions_options(profile_run: Any) -> None:
    profile_run.reset(model_of(SHOP_MODEL), {})
    database = own_root(
        connect_with_transaction_defaults(cast("PostgresAdapter", profile_run.port), SHOP_MODEL)
    )
    db = database.using_database_login()
    reports = a_scope_for_reports(db)

    assert db.transact(lambda tx: tx.options) == TxnOptions(
        max_retries=3, concurrency="locking", isolation="read_committed"
    )
    assert reports.transact(lambda tx: tx.options) == TxnOptions(
        max_retries=3, concurrency="locking", isolation="repeatable_read"
    )
    assert reports.transact(lambda tx: tx.options, max_retries=0) == TxnOptions(
        max_retries=0, concurrency="locking", isolation="repeatable_read"
    )
    assert reports.read_only(lambda rtx: rtx.options.isolation) == "repeatable_read"


def test_a_join_must_name_the_options_its_transaction_resolved(profile_run: Any) -> None:
    db = _seed_customers_and_a_limit(profile_run)

    with pytest.raises(ExecutionFailure) as refused:
        place_two_orders_together(db, _order(20, 1, "50.00"), _order(21, 1, "60.00"))

    assert isinstance(refused.value.cause, TransactionOptionConflictError)
    assert sorted(order.id for order in orders_of(db, 1)) == [10, 11]

    # The second check sees the first order, pending in the same transaction,
    # and declines.
    placed = place_two_orders_together_serializably(
        db, _order(20, 1, "50.00"), _order(21, 1, "60.00")
    )

    assert placed == (True, False)
    assert sorted(order.id for order in orders_of(db, 1)) == [10, 11, 20]

    # Outside a transaction, each check runs and commits in a transaction of its own.
    assert place_two_orders(db, _order(22, 1, "20.00"), _order(23, 1, "20.00")) == (True, False)
    assert sorted(order.id for order in orders_of(db, 1)) == [10, 11, 20, 22]


# --------------------------------------------------------------------------- #
# Database-free run-through of every recipe body.                              #
# --------------------------------------------------------------------------- #
class _ScriptedPort(ConnectsAsItself):
    """A fake `m-db-port` answering successive reads with scripted rows, then
    none, every write with ``affected`` rows, and every boundary by committing."""

    dialect: Dialect = POSTGRES

    def __init__(self, *reads: Sequence[Mapping[str, object]], affected: int = 1) -> None:
        self.reads = list(reads)
        self.affected = affected

    def execute(
        self, sql: str, binds: Sequence[Bind], document_reads: Sequence[tuple[int, int]] = ()
    ) -> list[Row]:
        answered = self.reads.pop(0) if self.reads else ()
        return [projected_row(sql, row, document_reads) for row in answered]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        return self.affected

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
_NO_ROWS: Sequence[Mapping[str, object]] = ()


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


def _register_customer_five(db: ScopedDatabase) -> Customer:
    return register_a_customer(db, 5, "Barbara")


def _change_customer_ones_email(db: ScopedDatabase) -> None:
    change_an_email(db, 1, "ada@example.org")


def _replace_customer_ones_details(db: ScopedDatabase) -> None:
    replace_contact_details(db, 1, "Ada King")


def _add_to_order_ten(db: ScopedDatabase) -> None:
    add_to_an_order(db, 10, Decimal("7.50"))


def _cancel_order_ten(db: ScopedDatabase) -> None:
    cancel_an_order(db, 10)


def _grant_customer_one_a_limit(db: ScopedDatabase) -> None:
    grant_a_credit_limit(db, 1, Decimal("1000.00"))


def _change_customer_ones_limit(db: ScopedDatabase) -> None:
    change_a_credit_limit(db, 1, Decimal("2500.00"))


def _withdraw_customer_ones_limit(db: ScopedDatabase) -> None:
    withdraw_a_credit_limit(db, 1)


def _list_tea_from_january(db: ScopedDatabase) -> None:
    list_a_tea(db, "TEA-1", Decimal("10.00"), _JAN)


def _list_a_summer_tea(db: ScopedDatabase) -> None:
    list_a_seasonal_tea(db, "TEA-2", Decimal("6.00"), _JUN, _SEP)


def _change_tea_from_april(db: ScopedDatabase) -> None:
    change_a_price_from(db, "TEA-1", Decimal("12.00"), _APR)


def _reprice_tea_from_july_to_october(db: ScopedDatabase) -> None:
    reprice_a_tea_for(db, "TEA-1", Decimal("7.00"), _JUL, _OCT)


def _discontinue_tea_in_december(db: ScopedDatabase) -> None:
    discontinue_a_tea(db, "TEA-1", _DEC)


def _correct_tea_from_january_to_april(db: ScopedDatabase) -> None:
    correct_a_past_price(db, "TEA-1", Decimal("9.50"), _JAN, _APR)


def _correct_tea_as_recorded_in_january(db: ScopedDatabase) -> None:
    with pytest.raises(ExecutionFailure):
        correct_a_price_as_recorded_then(db, "TEA-1", Decimal("9.50"), _JAN, _APR, _T2)


def _change_a_reviewed_order(db: ScopedDatabase) -> None:
    reviewed = db.find(Order.where(Order.id == 10)).result()
    change_a_reviewed_total(db, reviewed, Decimal("140.00"))


def _change_a_reviewed_credit_limit(db: ScopedDatabase) -> None:
    reviewed = db.find(CreditLimit.where(CreditLimit.customer_id == 1)).result()
    change_a_reviewed_limit(db, reviewed, Decimal("1500.00"))


def _forget_adas_email(db: ScopedDatabase) -> int:
    return forget_an_email_address(db, "ada@example.com")


def _delete_order_tens_shipments(db: ScopedDatabase) -> int:
    return delete_the_shipments_of(db, 10)


def _add_edsger_from_json(db: ScopedDatabase) -> None:
    add_a_customer_from_json(db, '{"id": 4, "name": "Edsger", "email": null}')


def _rename_customer_one_through_wire(db: ScopedDatabase) -> None:
    rename_a_customer_through_wire(db, 1, "Ada King")


def _customer_one_with_their_orders(db: ScopedDatabase) -> object:
    return customer_with_their_orders(db, 1)


def _largest_orders_since_april(db: ScopedDatabase) -> list[Order]:
    return largest_orders_since(db, dt.date(2024, 4, 1), 2)


def _customers_named_a(db: ScopedDatabase) -> list[Customer]:
    return customers_named(db, "A")


def _customers_with_a_large_recent_order(db: ScopedDatabase) -> list[Customer]:
    return customers_with_a_large_recent_order(db, dt.date(2024, 4, 1), Decimal("100.00"))


def _customers_with_a_recent_order_and_a_large_one(db: ScopedDatabase) -> list[Customer]:
    return customers_with_a_recent_order_and_a_large_one(db, dt.date(2024, 4, 1), Decimal("100.00"))


def _card_payments_ending_in_4242(db: ScopedDatabase) -> list[Payment]:
    return card_payments_ending_in(db, "4242")


def _card_payments_over_ten(db: ScopedDatabase) -> list[CardPayment]:
    return card_payments_over(db, Decimal("10.00"))


def _total_of_every_order(db: ScopedDatabase) -> Decimal:
    return total_of_every_order(db, 10)


def _export_customers(db: ScopedDatabase) -> int:
    return export_customers(db, io.StringIO(), 10)


def _customer_one_for_page_and_api(db: ScopedDatabase) -> object:
    return customer_for_page_and_api(db, 1)


def _reprice_a_reviewed_tea(db: ScopedDatabase) -> None:
    reviewed = db.find(Price.where(Price.sku == "TEA-1").as_of(valid_time=_APR)).result()
    reprice_from_a_review(db, reviewed, Decimal("12.00"), _APR)


def _change_a_limit_shown_earlier(db: ScopedDatabase) -> None:
    shown = db.wire.find(CreditLimit.where(CreditLimit.customer_id == 1)).result()
    change_a_limit_shown_earlier(db, shown, "1500.00")


_ANOTHER_ORDER_ROW: Mapping[str, object] = {**_ORDER_ROW, "id": 11, "total": Decimal("20.00")}


def _open_an_account_for_edsger(db: ScopedDatabase) -> Customer:
    return open_an_account(db, Customer(id=3, name="Edsger", email=None), _order(13, 3, "9.00"))


def _open_an_account_whatever_the_order(db: ScopedDatabase) -> bool:
    return open_an_account_even_if_the_order_fails(
        db, Customer(id=3, name="Edsger", email=None), _order(13, 3, "9.00")
    )


def _place_an_order_that_fits(db: ScopedDatabase) -> bool:
    return place_an_order_within_the_limit(db, _order(13, 1, "80.00"))


def _place_an_order_past_the_limit(db: ScopedDatabase) -> bool:
    return place_an_order_within_the_limit(db, _order(13, 1, "900.00"))


def _add_to_order_ten_under_a_lock(db: ScopedDatabase) -> None:
    add_to_an_order_under_a_lock(db, 10, Decimal("20.00"))


def _change_a_reviewed_total_within_the_limit(db: ScopedDatabase) -> bool:
    reviewed = db.find(Order.where(Order.id == 10)).result()
    return change_a_reviewed_total_within_the_limit(db, reviewed, Decimal("160.00"))


def _change_a_reviewed_total_past_the_limit(db: ScopedDatabase) -> bool:
    reviewed = db.find(Order.where(Order.id == 10)).result()
    return change_a_reviewed_total_within_the_limit(db, reviewed, Decimal("990.00"))


def _add_to_order_ten_once(db: ScopedDatabase) -> None:
    add_to_an_order_once(db, 10, Decimal("20.00"))


def _place_two_orders_together_serializably(db: ScopedDatabase) -> tuple[bool, bool]:
    return place_two_orders_together_serializably(
        db, _order(13, 1, "50.00"), _order(14, 1, "60.00")
    )


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
        pytest.param(_register_customer_five, ([_CUSTOMER_ROW],), id="insert-and-read"),
        pytest.param(_change_customer_ones_email, ([_CUSTOMER_ROW],), id="amend-an-edit"),
        pytest.param(_replace_customer_ones_details, ([_CUSTOMER_ROW],), id="replace-an-edit"),
        pytest.param(_add_to_order_ten, ([_ORDER_ROW],), id="amend-an-assignment"),
        pytest.param(_cancel_order_ten, ([_ORDER_ROW],), id="delete"),
        pytest.param(_grant_customer_one_a_limit, (), id="transaction-time-insert"),
        pytest.param(
            _change_customer_ones_limit, ([_CREDIT_LIMIT_ROW],), id="transaction-time-amend"
        ),
        pytest.param(
            _withdraw_customer_ones_limit, ([_CREDIT_LIMIT_ROW],), id="transaction-time-terminate"
        ),
        pytest.param(_list_tea_from_january, (), id="bitemporal-insert"),
        pytest.param(_list_a_summer_tea, (), id="bitemporal-bounded-insert"),
        pytest.param(_change_tea_from_april, ([_PRICE_ROW], [_PRICE_ROW]), id="bitemporal-amend"),
        pytest.param(
            _reprice_tea_from_july_to_october, ([_PRICE_ROW], [_PRICE_ROW]), id="bitemporal-replace"
        ),
        pytest.param(
            _discontinue_tea_in_december, ([_PRICE_ROW], [_PRICE_ROW]), id="bitemporal-terminate"
        ),
        pytest.param(
            _correct_tea_from_january_to_april,
            ([_PRICE_ROW], [_PRICE_ROW]),
            id="bitemporal-correction",
        ),
        pytest.param(
            _correct_tea_as_recorded_in_january, ([_PRICE_ROW],), id="pinned-correction-refused"
        ),
        pytest.param(_change_a_reviewed_order, ([_ORDER_ROW],), id="target-version"),
        pytest.param(
            _change_a_reviewed_credit_limit,
            ([_CREDIT_LIMIT_ROW], [_CREDIT_LIMIT_ROW]),
            id="target-tx-start",
        ),
        pytest.param(_forget_adas_email, (), id="predicate-amend"),
        pytest.param(_delete_order_tens_shipments, (), id="predicate-delete"),
        pytest.param(_add_edsger_from_json, (), id="wire-insert"),
        pytest.param(_rename_customer_one_through_wire, ([_CUSTOMER_ROW],), id="wire-amend"),
        pytest.param(
            _customer_one_with_their_orders, ([_CUSTOMER_ROW], [_ORDER_ROW]), id="read-only-join"
        ),
        pytest.param(_largest_orders_since_april, ([_ORDER_ROW],), id="sort-and-limit"),
        pytest.param(_customers_named_a, ([_CUSTOMER_ROW],), id="combined-predicates"),
        pytest.param(_customers_with_a_large_recent_order, ([_CUSTOMER_ROW],), id="one-quantifier"),
        pytest.param(
            _customers_with_a_recent_order_and_a_large_one, ([_CUSTOMER_ROW],), id="two-quantifiers"
        ),
        pytest.param(_card_payments_ending_in_4242, (), id="is-a-narrowing"),
        pytest.param(_card_payments_over_ten, (), id="narrow-clause"),
        pytest.param(_total_of_every_order, ([_ORDER_ROW],), id="typed-stream"),
        pytest.param(_export_customers, ([_CUSTOMER_ROW], [_ORDER_ROW]), id="wire-stream"),
        pytest.param(
            _customer_one_for_page_and_api, ([_CUSTOMER_ROW], [_ORDER_ROW]), id="wire-projection"
        ),
        pytest.param(
            _reprice_a_reviewed_tea, ([_PRICE_ROW], [_PRICE_ROW]), id="bitemporal-target-write"
        ),
        pytest.param(
            _change_a_limit_shown_earlier,
            ([_CREDIT_LIMIT_ROW], [_CREDIT_LIMIT_ROW]),
            id="wire-target-tx-start",
        ),
        pytest.param(_open_an_account_for_edsger, ([_CUSTOMER_ROW],), id="joined-insert"),
        pytest.param(_open_an_account_whatever_the_order, (), id="caught-join-unneeded"),
        pytest.param(
            _place_an_order_that_fits, ([_CREDIT_LIMIT_ROW], [_ORDER_ROW]), id="limit-fits"
        ),
        pytest.param(
            _place_an_order_past_the_limit, ([_CREDIT_LIMIT_ROW], [_ORDER_ROW]), id="limit-passed"
        ),
        pytest.param(_add_to_order_ten_under_a_lock, ([_ORDER_ROW],), id="locking-preference"),
        pytest.param(
            _change_a_reviewed_total_within_the_limit,
            ([_ORDER_ROW], [_CREDIT_LIMIT_ROW], [_ORDER_ROW, _ANOTHER_ORDER_ROW]),
            id="limited-target-write",
        ),
        pytest.param(
            _change_a_reviewed_total_past_the_limit,
            ([_ORDER_ROW], [_CREDIT_LIMIT_ROW], [_ORDER_ROW, _ANOTHER_ORDER_ROW]),
            id="limited-target-write-declined",
        ),
        pytest.param(_add_to_order_ten_once, ([_ORDER_ROW],), id="single-attempt"),
        pytest.param(
            _place_two_orders_together_serializably,
            ([_CREDIT_LIMIT_ROW], [_ORDER_ROW], [_CREDIT_LIMIT_ROW], [_ORDER_ROW]),
            id="matching-join",
        ),
    ],
)
def test_every_recipe_runs_through_the_shipped_surface(
    recipe: Callable[[ScopedDatabase], object], reads: tuple[Sequence[Mapping[str, object]], ...]
) -> None:
    recipe(own_root(Database.connect(_ScriptedPort(*reads), SHOP_MODEL)).using_database_login())


@pytest.mark.parametrize(
    ("include", "reads", "named"),
    [
        pytest.param(False, ([_ORDER_ROW],), "not loaded", id="not-included"),
        pytest.param(True, ([_ORDER_ROW], [_CUSTOMER_ROW]), "Ada", id="customer"),
        pytest.param(True, ([_ORDER_ROW], _NO_ROWS), "no customer", id="no-customer"),
    ],
)
def test_naming_who_placed_an_order_runs_through_the_shipped_surface(
    include: bool, reads: tuple[Sequence[Mapping[str, object]], ...], named: str
) -> None:
    db = own_root(Database.connect(_ScriptedPort(*reads), SHOP_MODEL)).using_database_login()
    query = Order.where(Order.id == 10)

    order = db.find(query.include(Order.customer) if include else query).result()

    assert who_placed(order) == named


class _WriteFailsPort(_ScriptedPort):
    """A scripted port whose every write fails as the database refusing it."""

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        raise RuntimeError("the database refused the write")


@pytest.mark.parametrize(
    ("port", "changed"),
    [
        pytest.param(_ScriptedPort([_ORDER_ROW]), [], id="unchanged"),
        pytest.param(_ScriptedPort([_ORDER_ROW], affected=0), [10], id="changed-since-review"),
    ],
)
def test_cancelling_reviewed_orders_runs_through_the_shipped_surface(
    port: _ScriptedPort, changed: list[int]
) -> None:
    db = own_root(Database.connect(port, SHOP_MODEL)).using_database_login()
    reviewed = db.find(Order.where(Order.id == 10)).results()

    assert cancel_reviewed_orders(db, reviewed) == changed


def test_cancelling_reviewed_orders_lets_any_other_failure_through() -> None:
    db = own_root(
        Database.connect(_WriteFailsPort([_ORDER_ROW]), SHOP_MODEL)
    ).using_database_login()
    reviewed = db.find(Order.where(Order.id == 10)).results()

    with pytest.raises(ExecutionFailure) as failed:
        cancel_reviewed_orders(db, reviewed)

    assert not isinstance(failed.value.cause, WritePreconditionError)


def test_a_caught_joined_failure_runs_through_the_shipped_surface() -> None:
    db = own_root(Database.connect(_ScriptedPort(), SHOP_MODEL)).using_database_login()

    with pytest.raises(ExecutionFailure) as refused:
        open_an_account_even_if_the_order_fails(
            db, Customer(id=3, name="Edsger", email=None), _order(13, 3, "0.00")
        )

    assert isinstance(refused.value.cause, RollbackOnlyError)


def test_a_join_naming_another_level_runs_through_the_shipped_surface() -> None:
    db = own_root(Database.connect(_ScriptedPort(), SHOP_MODEL)).using_database_login()

    with pytest.raises(ExecutionFailure) as refused:
        place_two_orders_together(db, _order(13, 1, "50.00"), _order(14, 1, "60.00"))

    assert isinstance(refused.value.cause, TransactionOptionConflictError)


def test_transaction_defaults_run_through_the_shipped_surface() -> None:
    database = own_root(
        connect_with_transaction_defaults(cast("PostgresAdapter", _ScriptedPort()), SHOP_MODEL)
    )

    reports = a_scope_for_reports(database.using_database_login())

    assert reports.transact(lambda tx: tx.options) == TxnOptions(
        max_retries=3, concurrency="locking", isolation="repeatable_read"
    )


def test_every_recipe_the_module_exports_has_a_driver() -> None:
    assert sorted(guide_recipes.__all__) == sorted(
        recipe.__name__
        for recipe in (
            a_scope_for_reports,
            add_a_customer_from_json,
            add_a_surcharge_to_every_order,
            add_and_find_a_customer,
            add_to_an_order,
            add_to_an_order_once,
            add_to_an_order_under_a_lock,
            amend_a_value_read_earlier,
            amend_after_reading_it_again,
            cancel_an_order,
            cancel_reviewed_orders,
            cancel_unless_changed,
            card_payments_ending_in,
            card_payments_over,
            change_a_credit_limit,
            change_a_limit_shown_earlier,
            change_a_price_from,
            change_a_reviewed_limit,
            change_a_reviewed_total,
            change_a_reviewed_total_within_the_limit,
            change_an_email,
            configure_the_database,
            connect_with_transaction_defaults,
            correct_a_past_price,
            correct_a_price_as_recorded_then,
            credit_limit_history,
            credit_limit_on_record,
            current_credit_limit,
            customer_as_json,
            customer_for_page_and_api,
            customer_with_email,
            customer_with_their_orders,
            customers_and_orders_from_one_snapshot,
            customers_and_orders_one_read_at_a_time,
            customers_named,
            customers_with_a_large_recent_order,
            customers_with_a_recent_order_and_a_large_one,
            customers_with_an_order_over,
            customers_with_an_order_over_as_wire,
            delete_the_shipments_of,
            discontinue_a_tea,
            export_customers,
            forget_an_email_address,
            grant_a_credit_limit,
            largest_orders_since,
            list_a_seasonal_tea,
            list_a_tea,
            look_up_a_customer,
            open_an_account,
            open_an_account_even_if_the_order_fails,
            orders_of,
            orders_placed_on,
            orders_with_their_customer,
            payments_for,
            place_an_order,
            place_an_order_within_the_limit,
            place_two_orders,
            place_two_orders_together,
            place_two_orders_together_serializably,
            price_on,
            price_on_as_recorded_at,
            prices_during,
            products_and_unreadable_rows,
            products_named,
            record_an_order,
            register_a_customer,
            rename_a_customer_through_wire,
            replace_contact_details,
            reprice_a_tea_for,
            reprice_from_a_review,
            run_a_summer_sale,
            shipments_to,
            table_statements,
            total_of_every_order,
            who_placed,
            withdraw_a_credit_limit,
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
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            bound.add(node.name)
        elif isinstance(node, ast.Name):
            (bound if isinstance(node.ctx, ast.Store) else loaded).add(node.id)
    return bound, loaded


_GUIDE = case_format.find_repo_root() / "languages" / "python" / "docs" / "guide"
_MARKER = re.compile(r"<!-- example: ([a-z0-9][a-z0-9-]*) -->")
_EXAMPLE_BLOCK = re.compile(r"<!-- example: .*?<!-- /example -->", re.DOTALL)
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_SHOP_MODEL_NAMES: frozenset[str] = frozenset(guide_models.__all__) - {"SHOP_MODEL"}
_NOTHING_ASSUMED: frozenset[str] = frozenset()


@pytest.mark.parametrize(
    ("chapter", "imports_id", "assumed"),
    [
        pytest.param("01-getting-started.md", "getting-started-imports", _NOTHING_ASSUMED, id="01"),
        pytest.param("02-modeling.md", "modeling-imports", _NOTHING_ASSUMED, id="02"),
        pytest.param("03-reading.md", "reading-imports", _SHOP_MODEL_NAMES, id="03"),
        pytest.param("04-writing.md", "writing-imports", _SHOP_MODEL_NAMES, id="04"),
        pytest.param("05-transactions.md", "transactions-imports", _SHOP_MODEL_NAMES, id="05"),
    ],
)
def test_each_chapters_imports_bind_what_its_snippets_read_and_only_what_it_names(
    chapter: str, imports_id: str, assumed: frozenset[str]
) -> None:
    # A reader finds every name a chapter uses in its imports block. The block
    # has to resolve, cover every name the chapter's snippets read beyond the
    # shop model the later chapters assume, and import nothing the chapter
    # neither reads in a snippet nor names in its prose.
    text = (_GUIDE / chapter).read_text(encoding="utf-8")
    sources = snippet_sources()
    marked = _MARKER.findall(text)
    assert imports_id in marked
    imports = sources[imports_id]
    exec(compile(imports, imports_id, "exec"), {})
    bound, loaded = _bound_and_loaded("\n\n".join(sources[source_id] for source_id in marked))
    imported, _ = _bound_and_loaded(imports)
    named = {
        name
        for span in _CODE_SPAN.findall(_EXAMPLE_BLOCK.sub("", text))
        for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", span)
    }

    assert loaded - bound - set(dir(builtins)) - assumed == set()
    assert imported - loaded - named == set()
