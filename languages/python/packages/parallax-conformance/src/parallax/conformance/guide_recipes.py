from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

from parallax.conformance.guide_models import (
    CreditLimit,
    Customer,
    Order,
    Payment,
    Price,
    Product,
    Shipment,
)
from parallax.core import TX_TIME, DomainModel
from parallax.core.db_port import Password
from parallax.core.dialect import POSTGRES
from parallax.core.entity import model_of
from parallax.core.execution import ExecutionFailure
from parallax.core.read_delivery import InvalidData
from parallax.core.unit_work import WritePreconditionError
from parallax.evolution import ABSENT, evolve, schema_delta
from parallax.postgres import PostgresAdapter
from parallax.snapshot import (
    ReadOnlyTxnContext,
    ScopedDatabase,
    TxnContext,
    WireEntity,
    connect,
)

__all__ = [
    "add_a_customer_from_json",
    "add_a_surcharge_to_every_order",
    "add_and_find_a_customer",
    "add_to_an_order",
    "amend_a_value_read_earlier",
    "amend_after_reading_it_again",
    "cancel_an_order",
    "cancel_reviewed_orders",
    "change_a_credit_limit",
    "change_a_price_from",
    "change_a_reviewed_limit",
    "change_a_reviewed_total",
    "change_an_email",
    "configure_the_database",
    "correct_a_past_price",
    "correct_a_price_as_recorded_then",
    "credit_limit_history",
    "credit_limit_on_record",
    "current_credit_limit",
    "customer_as_json",
    "customer_with_email",
    "customers_and_orders_from_one_snapshot",
    "customers_and_orders_one_read_at_a_time",
    "customers_with_an_order_over",
    "customers_with_an_order_over_as_wire",
    "delete_the_shipments_of",
    "discontinue_a_tea",
    "forget_an_email_address",
    "grant_a_credit_limit",
    "list_a_seasonal_tea",
    "list_a_tea",
    "look_up_a_customer",
    "orders_placed_on",
    "orders_with_their_customer",
    "payments_for",
    "place_an_order",
    "price_on",
    "price_on_as_recorded_at",
    "prices_during",
    "products_and_unreadable_rows",
    "products_named",
    "register_a_customer",
    "rename_a_customer_through_wire",
    "replace_contact_details",
    "reprice_a_tea_for",
    "run_a_summer_sale",
    "shipments_to",
    "table_statements",
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


def cancel_reviewed_orders(db: ScopedDatabase, reviewed: list[Order]) -> list[int]:
    """Cancel each order unless it changed since its review; return the ones that changed."""
    changed: list[int] = []
    for order in reviewed:

        def cancel(tx: TxnContext, order: Order = order) -> None:
            tx.delete_if(Order, key=order.id, version=order.version)

        try:
            db.transact(cancel)
        except ExecutionFailure as failure:
            if not isinstance(failure.cause, WritePreconditionError):
                raise
            changed.append(order.id)
    return changed


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
