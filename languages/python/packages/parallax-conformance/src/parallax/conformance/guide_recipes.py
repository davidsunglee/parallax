from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import TextIO

from parallax.conformance.guide_models import (
    CardPayment,
    CreditLimit,
    Customer,
    Order,
    Payment,
    Price,
    Product,
    Shipment,
)
from parallax.core import (
    TABLE_PER_CONCRETE_SUBTYPE,
    TX_TIME,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    attr,
)
from parallax.core.db_port import Password
from parallax.core.dialect import POSTGRES
from parallax.core.entity import model_of
from parallax.core.execution import ExecutionFailure, TxnOptions
from parallax.core.read_delivery import InvalidData
from parallax.core.unit_work import WritePreconditionError
from parallax.evolution import ABSENT, evolve, schema_delta
from parallax.postgres import PostgresAdapter, PostgresRole
from parallax.snapshot import (
    Database,
    ReadOnlyTxnContext,
    ScopedDatabase,
    TxnContext,
    WireEntity,
    connect,
    edge_of,
    is_view_loaded,
)

__all__ = [
    "CarrierDelivery",
    "CourierDelivery",
    "Delivery",
    "PostalDelivery",
    "StorePickup",
    "a_scope_for_reports",
    "add_a_customer_from_json",
    "add_a_surcharge_to_every_order",
    "add_and_find_a_customer",
    "add_to_an_order",
    "add_to_an_order_once",
    "add_to_an_order_under_a_lock",
    "amend_a_value_read_earlier",
    "amend_after_reading_it_again",
    "arrange_a_pickup",
    "cancel_an_order",
    "cancel_reviewed_orders",
    "cancel_unless_changed",
    "card_payments_ending_in",
    "card_payments_over",
    "change_a_credit_limit",
    "change_a_limit_shown_earlier",
    "change_a_price_from",
    "change_a_reviewed_limit",
    "change_a_reviewed_total",
    "change_a_reviewed_total_within_the_limit",
    "change_an_email",
    "configure_the_database",
    "connect_with_transaction_defaults",
    "correct_a_past_price",
    "correct_a_price_as_recorded_then",
    "credit_limit_history",
    "credit_limit_on_record",
    "current_credit_limit",
    "customer_as_json",
    "customer_for_page_and_api",
    "customer_with_email",
    "customer_with_their_orders",
    "customers_and_orders_from_one_snapshot",
    "customers_and_orders_one_read_at_a_time",
    "customers_named",
    "customers_with_a_large_recent_order",
    "customers_with_a_recent_order_and_a_large_one",
    "customers_with_an_order_over",
    "customers_with_an_order_over_as_wire",
    "delete_the_shipments_of",
    "deliveries_for",
    "discontinue_a_tea",
    "export_customers",
    "forget_an_email_address",
    "grant_a_credit_limit",
    "largest_orders_since",
    "list_a_seasonal_tea",
    "list_a_tea",
    "look_up_a_customer",
    "open_an_account",
    "open_an_account_even_if_the_order_fails",
    "orders_of",
    "orders_placed_on",
    "orders_with_their_customer",
    "payments_for",
    "place_an_order",
    "place_an_order_within_the_limit",
    "place_two_orders",
    "place_two_orders_together",
    "place_two_orders_together_serializably",
    "price_on",
    "price_on_as_recorded_at",
    "prices_during",
    "products_and_unreadable_rows",
    "products_named",
    "record_an_order",
    "register_a_customer",
    "rename_a_customer_through_wire",
    "replace_contact_details",
    "reprice_a_tea_for",
    "reprice_from_a_review",
    "run_a_summer_sale",
    "shipments_to",
    "table_statements",
    "total_of_every_order",
    "tracked_deliveries_for",
    "who_placed",
    "withdraw_a_credit_limit",
]


def table_statements(model: DomainModel) -> tuple[str, ...]:
    """The SQL that creates the model's tables in an empty PostgreSQL schema.

    Parallax never changes a schema itself: run these with your migration tool.
    """
    return schema_delta(evolve(ABSENT, model_of(model)), POSTGRES).statements


def configure_the_database(conninfo: str, password: str) -> PostgresAdapter:
    """Configuration only: building an adapter opens no connection."""
    return PostgresAdapter(conninfo, credentials=Password(password))


def add_and_find_a_customer(adapter: PostgresAdapter) -> Customer:
    model = DomainModel(Customer, Order)
    with connect(adapter, model) as database:
        db = database.using_database_login()
        db.transact(
            lambda tx: tx.insert(Customer(id=1, name="Ada Lovelace", email="ada@example.com"))
        )
        return db.find(Customer.where(Customer.id == 1)).result()


def customers_with_an_order_over(db: ScopedDatabase, total: Decimal) -> list[Customer]:
    """Each matching customer arrives with all of its orders already loaded."""
    query = Customer.where(Customer.orders.any(Order.total > total)).include(Customer.orders)
    return db.find(query).results()


def customers_with_an_order_over_as_wire(db: ScopedDatabase, total: Decimal) -> list[WireEntity]:
    """The same read, delivered as immutable mappings ready to serialize."""
    query = Customer.where(Customer.orders.any(Order.total > total)).include(Customer.orders)
    return db.wire.find(query).results()


def place_an_order(db: ScopedDatabase) -> None:
    """Insert an order and update its customer: both commit, or neither does."""

    def place(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == 1)).result()
        tx.insert(
            Order(
                id=7,
                customer_id=customer.id,
                placed_on=dt.date(2024, 5, 2),
                total=Decimal("80.00"),
            )
        )
        tx.amend(customer.edit(email="ada@example.org"))

    db.transact(place)


def credit_limit_on_record(db: ScopedDatabase, customer_id: int, when: dt.datetime) -> Decimal:
    """The limit the database held at ``when``, even if it has changed since."""
    query = CreditLimit.where(CreditLimit.customer_id == customer_id).as_of(tx_time=when)
    return db.find(query).result().amount


def run_a_summer_sale(db: ScopedDatabase) -> None:
    """Lower a price from June to September; the rest of the year keeps the old price."""
    june = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    september = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def discount(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == "TEA-1").as_of(valid_time=june)).result()
        tx.amend(price.edit(amount=Decimal("8.00")), until=september)

    db.transact(discount)


def shipments_to(db: ScopedDatabase, city: str) -> list[Shipment]:
    return db.find(Shipment.where(Shipment.ship_to.city == city)).results()


def payments_for(db: ScopedDatabase, order_id: int) -> list[Payment]:
    """Each payment arrives as its own concrete class."""
    return db.find(Payment.where(Payment.order_id == order_id)).results()


class Delivery(Entity, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]


class CarrierDelivery(Delivery, inheritance=AbstractSubtype):
    tracking_number: Attr[str] = attr(max_length=40)


class CourierDelivery(CarrierDelivery, table="courier_delivery", inheritance=ConcreteSubtype):
    courier: Attr[str] = attr(max_length=40)


class PostalDelivery(CarrierDelivery, table="postal_delivery", inheritance=ConcreteSubtype):
    service: Attr[str] = attr(max_length=20)


class StorePickup(Delivery, table="store_pickup", inheritance=ConcreteSubtype):
    store: Attr[str] = attr(max_length=40)


def arrange_a_pickup(db: ScopedDatabase, delivery_id: int, order_id: int, store: str) -> None:
    """Insert a concrete subtype: the row goes to ``store_pickup``, its own table."""
    db.transact(lambda tx: tx.insert(StorePickup(id=delivery_id, order_id=order_id, store=store)))


def deliveries_for(db: ScopedDatabase, order_id: int) -> list[Delivery]:
    """Read the whole family, from every subtype's table, each as its own concrete class."""
    return db.find(Delivery.where(Delivery.order_id == order_id)).results()


def tracked_deliveries_for(db: ScopedDatabase, order_id: int) -> list[CarrierDelivery]:
    """Narrow to the abstract subtype: courier and postal deliveries, never a pickup."""
    query = Delivery.where(Delivery.order_id == order_id).narrow(CarrierDelivery)
    return db.find(query).results()


def products_named(db: ScopedDatabase, name: str) -> list[Product]:
    """The same query a column-stored product would take."""
    return db.find(Product.where(Product.name == name)).results()


def look_up_a_customer(db: ScopedDatabase, customer_id: int) -> Customer:
    """A one-off lookup: there is no transaction to open or close."""
    return db.find(Customer.where(Customer.id == customer_id)).result()


def customers_and_orders_one_read_at_a_time(
    db: ScopedDatabase,
) -> tuple[list[Customer], list[Order]]:
    """Two standalone reads: each one sees the database as it is when it runs."""
    customers = db.find(Customer.where(Customer.all)).results()
    orders = db.find(Order.where(Order.all)).results()
    return customers, orders


def customers_and_orders_from_one_snapshot(
    db: ScopedDatabase,
) -> tuple[list[Customer], list[Order]]:
    """Two reads of one snapshot, so every order's customer is in the list."""

    def read_both(rtx: ReadOnlyTxnContext) -> tuple[list[Customer], list[Order]]:
        customers = rtx.find(Customer.where(Customer.all)).results()
        orders = rtx.find(Order.where(Order.all)).results()
        return customers, orders

    return db.read_only(read_both, isolation="repeatable_read")


def amend_a_value_read_earlier(db: ScopedDatabase, customer: Customer, email: str) -> None:
    """Refused with ``WriteEvidenceError``: ``customer`` was read outside this transaction."""
    db.transact(lambda tx: tx.amend(customer.edit(email=email)))


def amend_after_reading_it_again(db: ScopedDatabase, customer_id: int, email: str) -> None:
    """Accepted: the read inside the transaction is what licenses the amendment."""

    def change_email(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.amend(customer.edit(email=email))

    db.transact(change_email)


def orders_with_their_customer(db: ScopedDatabase, since: dt.date) -> list[Order]:
    """Each order arrives with its customer, and that customer with all of its orders."""
    query = Order.where(Order.placed_on >= since).include(Order.customer.orders)
    return db.find(query).results()


def customer_with_email(db: ScopedDatabase, email: str) -> Customer | None:
    """At most one customer has this email; ``None`` when nobody does."""
    return db.find(Customer.where(Customer.email == email)).result_or_none()


def orders_placed_on(db: ScopedDatabase, day: dt.date) -> list[Order]:
    """Every order placed on ``day``, possibly none."""
    return db.find(Order.where(Order.placed_on == day)).results()


def products_and_unreadable_rows(
    db: ScopedDatabase,
) -> tuple[list[Product], list[InvalidData[Product]]]:
    """Every product, with rows whose stored data breaks the model set aside."""
    readable: list[Product] = []
    unreadable: list[InvalidData[Product]] = []
    for item in db.find(Product.where(Product.all)).checked().results():
        if isinstance(item, InvalidData):
            unreadable.append(item)
        else:
            readable.append(item)
    return readable, unreadable


def add_a_surcharge_to_every_order(db: ScopedDatabase, surcharge: Decimal, page: int) -> int:
    """Stream every order and amend each one, all in one transaction.

    The stream keeps its default order, the primary key, which no write can change,
    so no order is skipped or delivered twice.
    """

    def apply(tx: TxnContext) -> int:
        amended = 0
        with tx.stream(Order.where(Order.all), batch_size=page) as orders:
            for order in orders:
                tx.amend(order.edit(total=order.total + surcharge))
                amended += 1
        return amended

    return db.transact(apply)


def current_credit_limit(db: ScopedDatabase, customer_id: int) -> Decimal:
    """Without ``as_of``, a read answers what the database holds now."""
    return db.find(CreditLimit.where(CreditLimit.customer_id == customer_id)).result().amount


def credit_limit_history(db: ScopedDatabase, customer_id: int) -> list[tuple[dt.datetime, Decimal]]:
    """Every limit the database has held for a customer, oldest first, with when it was set."""
    query = CreditLimit.where(CreditLimit.customer_id == customer_id).history(TX_TIME)
    return [(limit.tx_start, limit.amount) for limit in db.find(query).results()]


def price_on(db: ScopedDatabase, sku: str, day: dt.datetime) -> Decimal:
    """The price in effect on ``day``, as the database knows it now."""
    return db.find(Price.where(Price.sku == sku).as_of(valid_time=day)).result().amount


def price_on_as_recorded_at(
    db: ScopedDatabase, sku: str, day: dt.datetime, recorded_at: dt.datetime
) -> Decimal:
    """The price in effect on ``day``, as the database recorded it at ``recorded_at``."""
    query = Price.where(Price.sku == sku).as_of(valid_time=day, tx_time=recorded_at)
    return db.find(query).result().amount


def prices_during(
    db: ScopedDatabase, sku: str, start: dt.datetime, end: dt.datetime
) -> list[tuple[dt.datetime, Decimal]]:
    """Each price in effect at some point from ``start`` up to ``end``, with where it begins."""
    query = Price.where(Price.sku == sku).as_of_range(valid_time=(start, end))
    return [(price.valid_start, price.amount) for price in db.find(query).results()]


def customer_as_json(db: ScopedDatabase, customer_id: int) -> str:
    """Query with a Wire document and serialize what comes back."""
    document = {
        "target": "Customer",
        "predicate": {"eq": {"path": "Customer.id", "value": customer_id}},
        "includes": [{"segments": [{"rel": "Customer.orders"}]}],
    }
    return json.dumps(db.wire.find(document).result())


def register_a_customer(db: ScopedDatabase, customer_id: int, name: str) -> Customer:
    """Insert a customer, then read it back before the transaction commits."""

    def register(tx: TxnContext) -> Customer:
        tx.insert(Customer(id=customer_id, name=name, email=None))
        return tx.find(Customer.where(Customer.id == customer_id)).result()

    return db.transact(register)


def change_an_email(db: ScopedDatabase, customer_id: int, email: str) -> None:
    """Write the members ``edit`` changed; every other member keeps its stored value."""

    def change(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.amend(customer.edit(email=email))

    db.transact(change)


def replace_contact_details(db: ScopedDatabase, customer_id: int, name: str) -> None:
    """Write every writable member the value holds, the unedited email included."""

    def rewrite(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.replace(customer.edit(name=name))

    db.transact(rewrite)


def add_to_an_order(db: ScopedDatabase, order_id: int, amount: Decimal) -> None:
    """Amend with an assignment computed from the value just read."""

    def add(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == order_id)).result()
        tx.amend(order, Order.total.set(order.total + amount))

    db.transact(add)


def cancel_an_order(db: ScopedDatabase, order_id: int) -> None:
    """Delete an order this transaction read."""

    def cancel(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == order_id)).result()
        tx.delete(order)

    db.transact(cancel)


def grant_a_credit_limit(db: ScopedDatabase, customer_id: int, amount: Decimal) -> None:
    """Open the first milestone of a customer's limit."""
    db.transact(lambda tx: tx.insert(CreditLimit(customer_id=customer_id, amount=amount)))


def change_a_credit_limit(db: ScopedDatabase, customer_id: int, amount: Decimal) -> None:
    """Close the current milestone and chain a new one; the old limit stays in history."""

    def change(tx: TxnContext) -> None:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == customer_id)).result()
        tx.amend(limit.edit(amount=amount))

    db.transact(change)


def withdraw_a_credit_limit(db: ScopedDatabase, customer_id: int) -> None:
    """Close the current milestone and chain nothing after it."""

    def withdraw(tx: TxnContext) -> None:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == customer_id)).result()
        tx.terminate(limit)

    db.transact(withdraw)


def list_a_tea(db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime) -> None:
    """Open a price from ``start``, with no end."""
    db.transact(lambda tx: tx.insert(Price(sku=sku, amount=amount), valid_from=start))


def list_a_seasonal_tea(
    db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime, end: dt.datetime
) -> None:
    """Open a price from ``start`` up to, but not including, ``end``."""
    db.transact(lambda tx: tx.insert(Price(sku=sku, amount=amount), valid_from=start, until=end))


def change_a_price_from(db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime) -> None:
    """Change a price from ``start`` onwards; earlier Valid Time keeps the old price."""

    def change(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == sku).as_of(valid_time=start)).result()
        tx.amend(price.edit(amount=amount))

    db.transact(change)


def reprice_a_tea_for(
    db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime, end: dt.datetime
) -> None:
    """Make ``amount`` the whole state from ``start`` up to ``end``, gaps included."""

    def reprice(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == sku).as_of(valid_time=start)).result()
        tx.replace(price.edit(amount=amount), until=end)

    db.transact(reprice)


def discontinue_a_tea(db: ScopedDatabase, sku: str, day: dt.datetime) -> None:
    """End a price from ``day`` onwards; earlier Valid Time keeps it."""

    def discontinue(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == sku).as_of(valid_time=day)).result()
        tx.terminate(price)

    db.transact(discontinue)


def correct_a_past_price(
    db: ScopedDatabase, sku: str, amount: Decimal, start: dt.datetime, end: dt.datetime
) -> None:
    """Correct a window of Valid Time that has already passed."""

    def correct(tx: TxnContext) -> None:
        price = tx.find(Price.where(Price.sku == sku).as_of(valid_time=start)).result()
        tx.amend(price.edit(amount=amount), until=end)

    db.transact(correct)


def correct_a_price_as_recorded_then(
    db: ScopedDatabase,
    sku: str,
    amount: Decimal,
    start: dt.datetime,
    end: dt.datetime,
    recorded_at: dt.datetime,
) -> None:
    """Refused with ``TransactionTimePinReadOnlyError``: the value was read at a past
    Transaction Time."""

    def correct(tx: TxnContext) -> None:
        query = Price.where(Price.sku == sku).as_of(valid_time=start, tx_time=recorded_at)
        price = tx.find(query).result()
        tx.amend(price.edit(amount=amount), until=end)

    db.transact(correct)


def change_a_reviewed_total(db: ScopedDatabase, reviewed: Order, total: Decimal) -> None:
    """``reviewed`` came from an earlier read: state the version it showed."""
    db.transact(
        lambda tx: tx.amend_if(
            Order, Order.total.set(total), key=reviewed.id, version=reviewed.version
        )
    )


def change_a_reviewed_limit(db: ScopedDatabase, reviewed: CreditLimit, amount: Decimal) -> None:
    """A temporal entity states where the milestone it showed starts in Transaction Time."""
    db.transact(
        lambda tx: tx.amend_if(
            CreditLimit,
            CreditLimit.amount.set(amount),
            key=reviewed.customer_id,
            tx_start=reviewed.tx_start,
        )
    )


def reprice_from_a_review(
    db: ScopedDatabase, reviewed: Price, amount: Decimal, start: dt.datetime
) -> None:
    """``reviewed`` was read at ``start``: state its milestone's start in Transaction Time."""
    db.transact(
        lambda tx: tx.amend_if(
            Price,
            Price.amount.set(amount),
            key=reviewed.sku,
            valid_from=start,
            tx_start=reviewed.tx_start,
        )
    )


def cancel_reviewed_orders(db: ScopedDatabase, reviewed: list[Order]) -> list[int]:
    """Cancel each order in a transaction of its own; return the ones that changed."""
    return [order.id for order in reviewed if not cancel_unless_changed(db, order)]


def cancel_unless_changed(db: ScopedDatabase, order: Order) -> bool:
    """Cancel ``order`` unless it changed since it was read; answer whether it was cancelled."""
    try:
        db.transact(lambda tx: tx.delete_if(Order, key=order.id, version=order.version))
    except ExecutionFailure as failure:
        if not isinstance(failure.cause, WritePreconditionError):
            raise
        return False
    return True


def forget_an_email_address(db: ScopedDatabase, email: str) -> int:
    """Clear an email address from every customer holding it; answers how many did."""
    return db.transact(
        lambda tx: tx.amend_where(Customer.where(Customer.email == email), Customer.email.set(None))
    )


def delete_the_shipments_of(db: ScopedDatabase, order_id: int) -> int:
    """Delete every shipment of an order; answers how many there were."""
    return db.transact(lambda tx: tx.delete_where(Shipment.where(Shipment.order_id == order_id)))


def add_a_customer_from_json(db: ScopedDatabase, payload: str) -> None:
    """Insert a customer from a JSON document in Wire spelling."""
    db.transact(lambda tx: tx.wire.insert("Customer", json.loads(payload)))


def rename_a_customer_through_wire(db: ScopedDatabase, customer_id: int, name: str) -> None:
    """Amend the node a Wire read of this transaction returned."""

    def rename(tx: TxnContext) -> None:
        customer = tx.wire.find(Customer.where(Customer.id == customer_id)).result()
        tx.wire.amend(customer, {"name": name})

    db.transact(rename)


def change_a_limit_shown_earlier(db: ScopedDatabase, shown: WireEntity, amount: str) -> None:
    """``shown`` came from an earlier Wire read: state where its milestone starts."""
    db.transact(
        lambda tx: tx.wire.amend_if(
            "CreditLimit",
            {"customerId": shown["customerId"], "amount": amount},
            tx_start=edge_of(shown).tx_time,
        )
    )


def orders_of(db: ScopedDatabase, customer_id: int) -> list[Order]:
    """Read in a read-only transaction of its own, or in the caller's when it has one."""
    return db.read_only(
        lambda rtx: rtx.find(Order.where(Order.customer_id == customer_id)).results()
    )


def customer_with_their_orders(
    db: ScopedDatabase, customer_id: int
) -> tuple[Customer, list[Order]]:
    """Both reads see one snapshot, because ``orders_of`` joins this transaction."""

    def read(rtx: ReadOnlyTxnContext) -> tuple[Customer, list[Order]]:
        customer = rtx.find(Customer.where(Customer.id == customer_id)).result()
        return customer, orders_of(db, customer_id)

    return db.read_only(read, isolation="repeatable_read")


def largest_orders_since(db: ScopedDatabase, since: dt.date, count: int) -> list[Order]:
    """The ``count`` largest orders placed on or after ``since``, largest first."""
    query = (
        Order.where(Order.placed_on >= since)
        .order_by(Order.total.desc(), Order.id.asc())
        .limit(count)
    )
    return db.find(query).results()


def customers_named(db: ScopedDatabase, prefix: str) -> list[Customer]:
    """Customers whose name starts with ``prefix`` and who have an email address."""
    query = Customer.where(Customer.name.starts_with(prefix) & Customer.email.is_not_null())
    return db.find(query).results()


def customers_with_a_large_recent_order(
    db: ScopedDatabase, since: dt.date, minimum: Decimal
) -> list[Customer]:
    """One order must be both recent and large: the quantifier tests each order alone."""
    query = Customer.where(
        Customer.orders.any((Order.placed_on >= since) & (Order.total >= minimum))
    )
    return db.find(query).results()


def customers_with_a_recent_order_and_a_large_one(
    db: ScopedDatabase, since: dt.date, minimum: Decimal
) -> list[Customer]:
    """Two quantifiers: the recent order and the large one can be different orders."""
    query = Customer.where(
        Customer.orders.any(Order.placed_on >= since),
        Customer.orders.any(Order.total >= minimum),
    )
    return db.find(query).results()


def card_payments_ending_in(db: ScopedDatabase, last_four: str) -> list[Payment]:
    """Only card payments match, so the filter can use a card payment's own attribute."""
    query = Payment.where(Payment.is_a(CardPayment, where=CardPayment.card_last_four == last_four))
    return db.find(query).results()


def card_payments_over(db: ScopedDatabase, amount: Decimal) -> list[CardPayment]:
    """``narrow`` keeps card payments only and types the result as ``CardPayment``."""
    return db.find(Payment.where(Payment.amount > amount).narrow(CardPayment)).results()


def who_placed(order: Order) -> str:
    """Name an order's customer without risking ``UnloadedRelationshipError``."""
    if not is_view_loaded(order, Order.customer):
        return "not loaded"
    if order.customer is None:
        return "no customer"
    return order.customer.name


def total_of_every_order(db: ScopedDatabase, page: int) -> Decimal:
    """Add up every order while holding only one page of them at a time."""
    total = Decimal("0.00")
    with db.stream(Order.where(Order.all), batch_size=page) as orders:
        for order in orders:
            total += order.total
    return total


def export_customers(db: ScopedDatabase, out: TextIO, page: int) -> int:
    """Write each customer, with its orders, as one line of JSON; answer how many."""
    written = 0
    query = Customer.where(Customer.all).include(Customer.orders)
    with db.wire.stream(query, batch_size=page) as customers:
        for customer in customers:
            out.write(json.dumps(customer) + "\n")
            written += 1
    return written


def customer_for_page_and_api(db: ScopedDatabase, customer_id: int) -> tuple[Customer, WireEntity]:
    """One read: a Typed value to render, and the same graph as Wire data to send."""
    snapshot = db.find(Customer.where(Customer.id == customer_id).include(Customer.orders))
    return snapshot.result(), snapshot.wire().result()


def record_an_order(db: ScopedDatabase, order: Order) -> None:
    """Insert ``order`` in a transaction of its own, or in the caller's when it has one."""

    def record(tx: TxnContext) -> None:
        if order.total <= 0:
            raise ValueError(f"order {order.id} has no total")
        tx.insert(order)

    db.transact(record)


def open_an_account(db: ScopedDatabase, customer: Customer, first_order: Order) -> Customer:
    """The customer and the first order commit together, because ``record_an_order`` joins."""

    def open_account(tx: TxnContext) -> Customer:
        tx.insert(customer)
        record_an_order(db, first_order)
        return tx.find(Customer.where(Customer.id == customer.id)).result()

    return db.transact(open_account)


def open_an_account_even_if_the_order_fails(
    db: ScopedDatabase, customer: Customer, first_order: Order
) -> bool:
    """Doesn't work: once the joined call has failed, the transaction can only roll back."""

    def open_account(tx: TxnContext) -> bool:
        tx.insert(customer)
        try:
            record_an_order(db, first_order)
        except ValueError:
            return False
        return True

    return db.transact(open_account)


def place_an_order_within_the_limit(db: ScopedDatabase, order: Order) -> bool:
    """Insert ``order`` unless it takes its customer's orders past their credit limit."""

    def place(tx: TxnContext) -> bool:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == order.customer_id)).result()
        placed = tx.find(Order.where(Order.customer_id == order.customer_id)).results()
        if sum((each.total for each in placed), order.total) > limit.amount:
            return False
        tx.insert(order)
        return True

    return db.transact(place, isolation="serializable")


def add_to_an_order_under_a_lock(db: ScopedDatabase, order_id: int, amount: Decimal) -> None:
    """Lock the order as it is read, so no other transaction changes it before this one ends."""

    def add(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == order_id)).result()
        tx.amend(order, Order.total.set(order.total + amount))

    db.transact(add, concurrency="locking")


def change_a_reviewed_total_within_the_limit(
    db: ScopedDatabase, reviewed: Order, total: Decimal
) -> bool:
    """Change the total a review showed, unless the customer's orders would pass their limit."""

    def change(tx: TxnContext) -> bool:
        limit = tx.find(CreditLimit.where(CreditLimit.customer_id == reviewed.customer_id)).result()
        placed = tx.find(Order.where(Order.customer_id == reviewed.customer_id)).results()
        others = sum(each.total for each in placed if each.id != reviewed.id)
        if others + total > limit.amount:
            return False
        tx.amend_if(Order, Order.total.set(total), key=reviewed.id, version=reviewed.version)
        return True

    return db.transact(change, isolation="serializable")


def add_to_an_order_once(db: ScopedDatabase, order_id: int, amount: Decimal) -> None:
    """Make a single attempt: the job queue that runs this redelivers a job that fails."""

    def add(tx: TxnContext) -> None:
        order = tx.find(Order.where(Order.id == order_id)).result()
        tx.amend(order, Order.total.set(order.total + amount))

    db.transact(add, max_retries=0)


def connect_with_transaction_defaults(
    adapter: PostgresAdapter, model: DomainModel
) -> Database[PostgresRole]:
    """Every transaction of this root makes at most four attempts and prefers locking."""
    return connect(adapter, model, options=TxnOptions(max_retries=3, concurrency="locking"))


def a_scope_for_reports(db: ScopedDatabase) -> ScopedDatabase:
    """Transactions through this scope run at Repeatable Read, with the root's other defaults."""
    return db.with_options(isolation="repeatable_read")


def place_two_orders(db: ScopedDatabase, first: Order, second: Order) -> tuple[bool, bool]:
    """Check and place each order in turn; each check joins the caller's transaction."""
    return place_an_order_within_the_limit(db, first), place_an_order_within_the_limit(db, second)


def place_two_orders_together(db: ScopedDatabase, first: Order, second: Order) -> tuple[bool, bool]:
    """Refused with ``TransactionOptionConflictError``: each check names Serializable, and
    this transaction runs at the scope's default level."""
    return db.transact(lambda tx: place_two_orders(db, first, second))


def place_two_orders_together_serializably(
    db: ScopedDatabase, first: Order, second: Order
) -> tuple[bool, bool]:
    """Both checks join this Serializable transaction, so the orders they accept commit together."""
    return db.transact(lambda tx: place_two_orders(db, first, second), isolation="serializable")
