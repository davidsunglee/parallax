# ruff: noqa: UP037 - Relationship targets remain strings until model formation.

import datetime as dt
from decimal import Decimal

from parallax.core import (
    ONE_TO_MANY,
    READ_ONLY,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    Int32,
    KeySequence,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    ValueObject,
    attr,
    index,
    rel,
)

__all__ = [
    "SHOP_MODEL",
    "Address",
    "BankTransfer",
    "CardPayment",
    "CreditLimit",
    "Customer",
    "Order",
    "Payment",
    "Price",
    "Product",
    "Shipment",
    "Subscription",
    "Supplier",
    "Ticket",
    "TicketNote",
]


class Customer(Entity, table="customer"):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=100)
    email: Attr[str | None] = attr(max_length=200)
    orders: Rel[tuple["Order", ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "customer_id"))


class Order(Entity, table="orders", indices=(index("orders_customer", "customer_id"),)):
    id: Attr[int] = attr(primary_key=True)
    customer_id: Attr[int]
    placed_on: Attr[dt.date]
    total: Attr[Decimal] = attr(precision=12, scale=2)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    customer: Rel[Customer | None] = rel(reverse_of="orders")


class Address(ValueObject):
    street: Attr[str]
    city: Attr[str]
    postcode: Attr[str]


class Shipment(
    Entity,
    table="shipment",
    indices=(index("shipment_tracking_number", "tracking_number", unique=True),),
):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    ship_to: Attr[Address]
    tracking_number: Attr[str | None] = attr(max_length=40)


class Payment(
    Entity,
    table="payment",
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    amount: Attr[Decimal] = attr(precision=12, scale=2)


class CardPayment(Payment, inheritance=ConcreteSubtype(tag_value="card")):
    card_last_four: Attr[str] = attr(max_length=4)


class BankTransfer(Payment, inheritance=ConcreteSubtype(tag_value="transfer")):
    reference: Attr[str] = attr(max_length=40)


class CreditLimit(TxTemporal, table="credit_limit"):
    customer_id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=12, scale=2)


class Price(Bitemporal, table="price"):
    sku: Attr[str] = attr(primary_key=True, max_length=20)
    amount: Attr[Decimal] = attr(precision=12, scale=2)


class Ticket(Entity, table="ticket"):
    id: Attr[int] = attr(primary_key=KeySequence("support_ids"))
    customer_id: Attr[int]
    subject: Attr[str] = attr(max_length=200)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class TicketNote(Entity, table="ticket_note"):
    id: Attr[int] = attr(primary_key=KeySequence("support_ids"))
    ticket_id: Attr[int]
    body: Attr[str]


class Subscription(Bitemporal, table="subscription"):
    id: Attr[int] = attr(primary_key=KeySequence("subscription_ids", batch_size=20))
    customer_id: Attr[int]
    plan: Attr[str] = attr(max_length=20)


class Supplier(Entity, table="supplier", persistence=READ_ONLY):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=100)


class Product(Entity, table="product", layout=Document()):
    sku: Attr[str] = attr(primary_key=True, max_length=20)
    name: Attr[str] = attr(max_length=100)
    description: Attr[str | None]


SHOP_MODEL = DomainModel(
    Customer,
    Order,
    Shipment,
    Payment,
    CardPayment,
    BankTransfer,
    CreditLimit,
    Price,
    Product,
    Supplier,
    Ticket,
    TicketNote,
    Subscription,
)
