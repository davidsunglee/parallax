"""Class-backed models whose stored state a real read can reject.

A native Column is accepted exactly as its provider normalized it, so a Page
suite that needs a stored-data issue converts rows of these models instead.
Every Bytes Column is projected as canonical wire under its ``_hex`` result key,
which conversion decodes and admits: a malformed spelling is an undecodable
stored value, and SQL null in a required one is a null stored value. ``address``
is a document Column the document codec classifies.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from parallax.conformance.vo_models import Address
from parallax.core import ONE_TO_MANY, Attr, DomainModel, Entity, Int32, Rel, attr, rel

__all__ = [
    "ENCODED_ACCOUNT",
    "ENCODED_ORDERS",
    "EncodedAccount",
    "EncodedOrder",
    "EncodedOrderItem",
]

_NAMESPACE = "parallax.compatibility"


class EncodedOrder(Entity, table="encoded_order", namespace=_NAMESPACE):
    """An order with Bytes payloads and two sibling item relationships over
    one join so a single item row can be reached through two projections."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str]
    badge: Attr[bytes | None]
    address: Attr[Address | None]
    items: Rel[tuple[EncodedOrderItem, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "order_id"))
    items_by_code: Rel[tuple[EncodedOrderItem, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "order_id"), order_by=("code",)
    )


class EncodedOrderItem(Entity, table="encoded_order_item", namespace=_NAMESPACE):
    """An item whose required ``code`` is a Bytes Column."""

    id: Attr[int] = attr(primary_key=True)
    order_id: Attr[int]
    code: Attr[bytes]
    order: Rel[EncodedOrder | None] = rel(reverse_of="items")


ENCODED_ORDERS = DomainModel(EncodedOrder, EncodedOrderItem)


class EncodedAccount(Entity, table="encoded_account", namespace=_NAMESPACE):
    """A versioned Entity whose required ``token`` is a Bytes Column."""

    id: Attr[int] = attr(primary_key=True)
    token: Attr[bytes]
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


ENCODED_ACCOUNT = DomainModel(EncodedAccount)
