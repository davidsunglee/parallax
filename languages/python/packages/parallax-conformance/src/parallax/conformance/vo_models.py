"""Value-object-bearing Entity Classes, one sealed hub per corpus model.

``models/supplier.yaml`` (Transaction-Time-Only, the first production-reachable
temporal x value-object combination), ``models/branch.yaml`` (bitemporal, the
SAME recursive ``address`` composite over both axes), ``models/contact.yaml``
(non-temporal, REQUIRED nested members at every depth — the write-validation
exemplar), ``models/shipment.yaml`` (a non-nullable TOP-LEVEL value object), and
``models/customer.yaml`` (a non-temporal parent with two VO-bearing to-many
children).

Owned by ``parallax.conformance`` for the same package-boundary reason
``read_models``/``story_models``/``graph_models`` are (spec §7/§8): a dev-only
package module resolvable at ordinary import time, so ``read_stories.py`` and the
write-validation build-time proofs can run against real Postgres / the shared
model-aware validator without a ``tests/``-only mirror. This module deliberately
avoids ``from __future__ import annotations`` so the engine reads the live
``Attr[T]`` objects directly.

``Supplier``/``Branch`` share the identical ``Address``/``Geo``/``Phone``
composite (street/city, a nested ``geo{country}``, a nested many
``phones{type,number}``, every member nullable) — the SAME shape
``value_object_models.Customer`` uses for its own recursive composite, minus
Customer's ``elevation``/``point`` refinement. ``Contact``'s own composite is a
DIFFERENT, deliberately mostly-REQUIRED shape (the write-validation exemplar), so
it gets its own ``ContactAddress``/``ContactGeo``/``ContactPoint``/
``ContactPhone`` classes rather than reusing ``Address``/``Geo``/``Phone``.
A Value Object class is never a hub candidate and is reached only through the
occurrences that contain it, so the identical simple names (``Geo``, ``Phone``,
``Point``) recur freely across modules.

``Location`` reuses ``Customer``'s own recursive ``address`` composite verbatim,
while ``Depot`` declares a DIFFERENT, flat composite (``{line, postcode}``) in the
SAME ``address`` column — a deliberate descriptor divergence the corpus's own
cases pin, since decoding a Depot row with Customer's recursive descriptor would
yield observably wrong keys.
"""

import datetime as dt

from parallax.core import (
    ONE_TO_MANY,
    Attr,
    Bitemporal,
    Entity,
    MetamodelHub,
    Rel,
    TxTemporal,
    ValueObject,
    attr,
    index,
    rel,
)

_NS = "parallax.compatibility"

__all__ = [
    "BRANCH_MODEL",
    "CONTACT_MODEL",
    "CUSTOMER_MODEL",
    "SHIPMENT_MODEL",
    "SUPPLIER_MODEL",
    "Address",
    "Branch",
    "Contact",
    "ContactAddress",
    "ContactGeo",
    "ContactPhone",
    "ContactPoint",
    "Customer",
    "CustomerAddress",
    "CustomerGeo",
    "CustomerPhone",
    "CustomerPoint",
    "Depot",
    "DepotAddress",
    "Destination",
    "Geo",
    "Location",
    "Phone",
    "Shipment",
    "Supplier",
]


# --------------------------------------------------------------------------- #
# Supplier / Branch: the shared address composite (street/city, geo{country}, #
# phones{type,number} -- every member nullable).                              #
# --------------------------------------------------------------------------- #
class Geo(ValueObject):
    country: Attr[str | None]


class Phone(ValueObject):
    type: Attr[str | None]
    number: Attr[str | None]


class Address(ValueObject):
    street: Attr[str | None]
    city: Attr[str | None]
    geo: Attr[Geo | None]
    phones: Attr[tuple[Phone, ...]]


class Supplier(
    TxTemporal,
    table="supplier",
    namespace=_NS,
    indices=(
        index("supplier_pk", "id", "tx_start", unique=True),
        index("supplier_name", "name"),
    ),
):
    """Mirror of ``models/supplier.yaml`` (Transaction-Time-Only)."""

    id: Attr[int] = attr(primary_key=True, column="sup_id")
    name: Attr[str] = attr(max_length=64)
    address: Attr[Address | None]


SUPPLIER_MODEL = MetamodelHub(Supplier)


class Branch(
    Bitemporal,
    table="branch",
    namespace=_NS,
    indices=(
        index("branch_pk", "id", "valid_start", "tx_start", unique=True),
        index("branch_name", "name"),
    ),
):
    """Mirror of ``models/branch.yaml`` (bitemporal: the SAME address composite
    ``Supplier`` uses, over both axes)."""

    id: Attr[int] = attr(primary_key=True, column="br_id")
    name: Attr[str] = attr(max_length=64)
    address: Attr[Address | None]


BRANCH_MODEL = MetamodelHub(Branch)


# --------------------------------------------------------------------------- #
# Contact: REQUIRED nested members at every depth (models/contact.yaml) — the #
# write-validation exemplar (m-value-object-039..043).                        #
# --------------------------------------------------------------------------- #
class ContactPoint(ValueObject):
    lat: Attr[float]
    lon: Attr[float]


class ContactGeo(ValueObject):
    country: Attr[str]
    point: Attr[ContactPoint]


class ContactPhone(ValueObject):
    type: Attr[str | None]
    number: Attr[str | None]
    expires: Attr[dt.date | None]


class ContactAddress(ValueObject):
    street: Attr[str]
    city: Attr[str]
    geo: Attr[ContactGeo]
    phones: Attr[tuple[ContactPhone, ...]]


class Contact(
    Entity,
    table="contact",
    namespace=_NS,
    indices=(index("contact_pk", "id", unique=True),),
):
    """Mirror of ``models/contact.yaml``: the top-level ``address`` value object
    stays nullable, but every INNER member is required, deliberately — a document
    missing any of them is refused, and under this grammar the refusal lands at
    construction, because a non-nullable member is a required Python field."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    address: Attr[ContactAddress | None]


CONTACT_MODEL = MetamodelHub(Contact)


# --------------------------------------------------------------------------- #
# Shipment: a non-nullable TOP-LEVEL value object (models/shipment.yaml).     #
# --------------------------------------------------------------------------- #
class Destination(ValueObject):
    street: Attr[str]
    city: Attr[str]


class Shipment(
    Entity,
    table="shipment",
    namespace=_NS,
    indices=(index("shipment_pk", "id", unique=True),),
):
    """Mirror of ``models/shipment.yaml``: ``destination`` is declared
    non-nullable, so omitting it is refused at construction."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    destination: Attr[Destination]


SHIPMENT_MODEL = MetamodelHub(Shipment)


# --------------------------------------------------------------------------- #
# Customer / Location / Depot (models/customer.yaml).                         #
# --------------------------------------------------------------------------- #
class CustomerPoint(ValueObject):
    lat: Attr[float | None]
    lon: Attr[float | None]


class CustomerGeo(ValueObject):
    country: Attr[str]
    elevation: Attr[float | None]
    point: Attr[CustomerPoint | None]


class CustomerPhone(ValueObject):
    type: Attr[str | None]
    number: Attr[str | None]


class CustomerAddress(ValueObject):
    street: Attr[str]
    city: Attr[str]
    geo: Attr[CustomerGeo | None]
    phones: Attr[tuple[CustomerPhone, ...]]


class DepotAddress(ValueObject):
    line: Attr[str | None]
    postcode: Attr[str | None]


class Customer(
    Entity,
    table="customer",
    namespace=_NS,
    indices=(index("customer_pk", "id", unique=True),),
):
    """Mirror of ``models/customer.yaml``'s ``Customer``: the recursive
    ``address`` value object, plus TWO VO-bearing to-many children reached by a
    distinct relationship each (``locations`` / ``depots``)."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    address: Attr[CustomerAddress | None]
    locations: Rel[tuple["Location", ...]] = rel(
        cardinality=ONE_TO_MANY,
        join=("id", "customer_id"),
        dependent=True,
        order_by=("id",),
    )
    depots: Rel[tuple["Depot", ...]] = rel(
        cardinality=ONE_TO_MANY,
        join=("id", "customer_id"),
        dependent=True,
        order_by=("id",),
    )


class Location(
    Entity,
    table="location",
    namespace=_NS,
    indices=(
        index("location_pk", "id", unique=True),
        index("location_customer_id", "customer_id"),
    ),
):
    """Mirror of ``models/customer.yaml``'s ``Location``: Customer's OWN
    recursive ``address`` composite, reused VERBATIM (never redeclared) — the
    deep-fetch x value-object composition witness AT DEPTH."""

    id: Attr[int] = attr(primary_key=True)
    customer_id: Attr[int]
    label: Attr[str] = attr(max_length=64)
    address: Attr[CustomerAddress | None]
    customer: Rel[Customer | None] = rel(reverse_of="locations")


class Depot(
    Entity,
    table="depot",
    namespace=_NS,
    indices=(
        index("depot_pk", "id", unique=True),
        index("depot_customer_id", "customer_id"),
    ),
):
    """Mirror of ``models/customer.yaml``'s ``Depot``: a DIFFERENT, FLAT
    ``address`` composite (``{line, postcode}``) in the SAME column name
    Customer/Location use for their own recursive one — the wrong-descriptor
    decode hazard the corpus's own commentary explains."""

    id: Attr[int] = attr(primary_key=True)
    customer_id: Attr[int]
    label: Attr[str] = attr(max_length=64)
    address: Attr[DepotAddress | None]
    customer: Rel[Customer | None] = rel(reverse_of="depots")


CUSTOMER_MODEL = MetamodelHub(Customer, Location, Depot)
