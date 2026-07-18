"""Value-object-bearing entity classes, installed for real (ledger D-21, COR-3
Phase 8 increment 7): ``models/supplier.yaml`` (unitemporal-processing, the
first production-reachable temporal x value-object combination),
``models/branch.yaml`` (bitemporal, the SAME recursive ``address`` composite
over both axes), ``models/contact.yaml`` (non-temporal, REQUIRED nested
members at every depth — the write-validation exemplar), and
``models/shipment.yaml`` (a non-nullable TOP-LEVEL value object).

Owned by ``parallax.conformance`` for the same package-boundary reason
``read_models``/``story_models``/``graph_models`` are (spec §7/§8): a
dev-only package module resolvable at ordinary import time, so
``read_stories.py`` and the write-validation build-time proofs can run
against real Postgres / the shared model-aware validator without a
``tests/``-only mirror. This module deliberately avoids ``from __future__
import annotations`` so the metaclass reads the live ``Attr[T]`` objects
directly.

``Supplier``/``Branch`` share the identical ``Address``/``Geo``/``Phone``
composite (street/city, a nested ``geo{country}``, a nested many
``phones{type,number}``, every member nullable) — the SAME shape
``value_object_models.Customer`` uses for its own recursive composite, minus
Customer's ``elevation``/``point`` refinement. ``Contact``'s own composite is
a DIFFERENT, deliberately mostly-REQUIRED shape (the write-validation
exemplar, ``models/contact.yaml``'s own docstring), so it gets its own
``ContactAddress``/``ContactGeo``/``ContactPoint``/``ContactPhone`` classes
rather than reusing ``Address``/``Geo``/``Phone`` — ``ValueObject`` classes
carry no name-registry collision risk at all (unlike entity classes: a VO
class is looked up by Python object reference through its owning entity's
``WireNames.vo_classes``, never by canonical name in a shared namespace), so
the identical simple names (``Geo``, ``Phone``, ``Point``) recur freely
across ``value_object_models``/this module without any collision.
"""

import datetime as dt

from parallax.core import AsOfAttribute, Attr, Entity, EntityConfig, Field
from parallax.core.entity.value_object import ValueObject, VoField

_NS = "parallax.compatibility"

__all__ = [
    "Address",
    "Branch",
    "Contact",
    "ContactAddress",
    "ContactGeo",
    "ContactPhone",
    "ContactPoint",
    "Destination",
    "Geo",
    "Phone",
    "Shipment",
    "Supplier",
]


# --------------------------------------------------------------------------- #
# Supplier / Branch: the shared address composite (street/city, geo{country}, #
# phones{type,number} -- every member nullable).                              #
# --------------------------------------------------------------------------- #
class Geo(ValueObject, frozen=True):
    country: Attr[str | None] = VoField(type="string", nullable=True, default=None)


class Phone(ValueObject, frozen=True):
    type: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    number: Attr[str | None] = VoField(type="string", nullable=True, default=None)


class Address(ValueObject, frozen=True):
    street: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    city: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    geo: Attr[Geo | None] = VoField(nullable=True, default=None)
    phones: Attr[tuple[Phone, ...]] = VoField(nullable=True, default=())


class Supplier(Entity, frozen=True):
    """Mirror of ``models/supplier.yaml`` (unitemporal-processing, audit-only)."""

    __parallax__ = EntityConfig(
        table="supplier",
        namespace=_NS,
        mutability="transactional",
        as_of=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", column="sup_id", type="int64")
    name: Attr[str] = Field(max_length=64)
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")
    address: Attr[Address | None] = Field(nullable=True, default=None)


class Branch(Entity, frozen=True):
    """Mirror of ``models/branch.yaml`` (bitemporal: the SAME address
    composite ``Supplier`` uses, over both axes)."""

    __parallax__ = EntityConfig(
        table="branch",
        namespace=_NS,
        mutability="transactional",
        as_of=(
            AsOfAttribute(
                name="businessDate", from_column="from_z", to_column="thru_z", axis="business"
            ),
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", column="br_id", type="int64")
    name: Attr[str] = Field(max_length=64)
    business_from: Attr[dt.datetime] = Field(column="from_z")
    business_to: Attr[dt.datetime] = Field(column="thru_z")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")
    address: Attr[Address | None] = Field(nullable=True, default=None)


# --------------------------------------------------------------------------- #
# Contact: REQUIRED nested members at every depth (models/contact.yaml) — the #
# write-validation exemplar (m-value-object-039..043).                        #
# --------------------------------------------------------------------------- #
class ContactPoint(ValueObject, frozen=True):
    # Every field stays PYTHON-optional (accepts and defaults to None) even
    # though the DECLARED descriptor is non-nullable (VoField's own
    # `nullable` flag is independent metadata, never inferred from the
    # Python type union): a caller CAN construct a structurally-incomplete
    # instance, so the shared `validate_write` classifier — never Pydantic's
    # own required-field enforcement — is what refuses it
    # (`m-value-object-039..042`'s own build-time reproduction).
    lat: Attr[float | None] = VoField(type="float64", default=None)
    lon: Attr[float | None] = VoField(type="float64", default=None)


class ContactGeo(ValueObject, frozen=True):
    country: Attr[str | None] = VoField(type="string", default=None)
    point: Attr[ContactPoint | None] = VoField(default=None)


class ContactPhone(ValueObject, frozen=True):
    type: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    number: Attr[str | None] = VoField(type="string", nullable=True, default=None)


class ContactAddress(ValueObject, frozen=True):
    street: Attr[str | None] = VoField(type="string", default=None)
    city: Attr[str | None] = VoField(type="string", default=None)
    geo: Attr[ContactGeo | None] = VoField(default=None)
    phones: Attr[tuple[ContactPhone, ...]] = VoField(nullable=True, default=())


class Contact(Entity, frozen=True):
    """Mirror of ``models/contact.yaml``: the top-level ``address`` value
    object stays nullable, but every INNER member is DECLARED required
    (deliberately, the write-validation exemplar) — a write missing any of
    them is refused pre-SQL (``m-value-object-039..042``). Every inner
    Python field still ACCEPTS ``None`` (see ``ContactPoint``'s own
    docstring) so the incomplete document can be constructed at all; the
    shared `validate_write` classifier is what refuses it, matching the
    corpus's own raw-dict reproduction exactly."""

    __parallax__ = EntityConfig(table="contact", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    address: Attr[ContactAddress | None] = Field(nullable=True, default=None)


# --------------------------------------------------------------------------- #
# Shipment: a non-nullable TOP-LEVEL value object (models/shipment.yaml) —    #
# the write-validation exemplar for an OMITTED required VO (m-value-object-044).#
# --------------------------------------------------------------------------- #
class Destination(ValueObject, frozen=True):
    street: Attr[str | None] = VoField(type="string", default=None)
    city: Attr[str | None] = VoField(type="string", default=None)


class Shipment(Entity, frozen=True):
    """Mirror of ``models/shipment.yaml``: ``destination`` is DECLARED
    non-nullable, but the Python field still accepts an omitted/``None``
    value (same discipline as ``Contact``'s own inner members) so
    `validate_write` — not Pydantic's own construction — is what refuses a
    write omitting it entirely (``m-value-object-044``)."""

    __parallax__ = EntityConfig(table="shipment", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    destination: Attr[Destination | None] = Field(default=None)
