from __future__ import annotations

import datetime as dt
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
from parallax.core import DomainModel
from parallax.core.db_port import Password
from parallax.core.dialect import POSTGRES
from parallax.core.entity import model_of
from parallax.evolution import ABSENT, evolve, schema_delta
from parallax.postgres import PostgresAdapter
from parallax.snapshot import ScopedDatabase, TxnContext, WireEntity, connect

__all__ = [
    "add_and_find_a_customer",
    "configure_the_database",
    "credit_limit_on_record",
    "customers_with_an_order_over",
    "customers_with_an_order_over_as_wire",
    "payments_for",
    "place_an_order",
    "products_named",
    "run_a_summer_sale",
    "shipments_to",
    "table_statements",
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
