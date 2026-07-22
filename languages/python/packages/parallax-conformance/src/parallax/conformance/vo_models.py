"""Value-object-bearing entity classes, installed for real (ledger D-21, COR-3
Phase 8 increment 7): ``models/supplier.yaml`` (Transaction-Time-only, the
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

``Customer``/``Location``/``Depot`` (D-20 residue, COR-3 Phase 8 increment 7
completion round) mirror ``models/customer.yaml``. ``value_object_models.py``
ALREADY declares its own test-only ``Customer`` (an ENTITY class, unlike the
bare VOs above) in the process :func:`~parallax.core.entity.base.default_registry`
under the SAME canonical name — a genuine
:class:`~parallax.core.entity.errors.RegistryCollisionError` the moment both
modules import in one process (empirically confirmed), the exact shape ledger
D-20 fixed for the animal family's owner (`parallax.conformance.animal_owner`).
The fix is identical: ``CUSTOMER_REGISTRY`` is a SEPARATE
:class:`~parallax.core.entity.base.EntityRegistry` (parent defaults to the
process default, needed for nothing here since ``Customer``/``Location``/
``Depot`` reference only each other) that SHADOWS the default registry's own
``Customer`` with THIS family's real, installed one, never colliding with it.
A ``Database`` exercising this family connects with
``CUSTOMER_REGISTRY.metamodel()`` (never the bare ingested corpus descriptor),
mirroring ``animal_owner.ANIMAL_OWNER_REGISTRY``'s own precedent exactly.
"""

import datetime as dt

from parallax.core import (
    AsOfAxisMetadata,
    Attr,
    Entity,
    EntityConfig,
    Field,
    OrderByTerm,
    Rel,
    Relationship,
    RelationshipJoin,
    RelationshipTarget,
    ReverseRelationship,
)
from parallax.core.entity.base import EntityRegistry
from parallax.core.entity.value_object import ValueObject, VoField

_NS = "parallax.compatibility"

__all__ = [
    "CUSTOMER_REGISTRY",
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
class Geo(ValueObject, frozen=True):
    country: Attr[str | None] = VoField(type="string", nullable=True, default=None)


class Phone(ValueObject, frozen=True):
    type: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    number: Attr[str | None] = VoField(type="string", nullable=True, default=None)


class Address(ValueObject, frozen=True):
    street: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    city: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    geo: Attr[Geo | None] = VoField(nullable=True, default=None)
    phones: Attr[tuple[Phone, ...]] = VoField(default=())


class Supplier(Entity, frozen=True):
    """Mirror of ``models/supplier.yaml`` (Transaction-Time-only)."""

    __parallax__ = EntityConfig(
        table="supplier",
        namespace=_NS,
        mutability="transactional",
        as_of=(
            AsOfAxisMetadata(
                dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", column="sup_id", type="int64")
    name: Attr[str] = Field(max_length=64)
    tx_start: Attr[dt.datetime] = Field(name="tx_start", column="in_z")
    tx_end: Attr[dt.datetime] = Field(name="tx_end", column="out_z")
    address: Attr[Address | None] = Field(nullable=True, default=None)


class Branch(Entity, frozen=True):
    """Mirror of ``models/branch.yaml`` (bitemporal: the SAME address
    composite ``Supplier`` uses, over both axes)."""

    __parallax__ = EntityConfig(
        table="branch",
        namespace=_NS,
        mutability="transactional",
        as_of=(
            AsOfAxisMetadata(
                dimension="validTime", start_attribute="valid_start", end_attribute="valid_end"
            ),
            AsOfAxisMetadata(
                dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", column="br_id", type="int64")
    name: Attr[str] = Field(max_length=64)
    valid_start: Attr[dt.datetime] = Field(name="valid_start", column="from_z")
    valid_end: Attr[dt.datetime] = Field(name="valid_end", column="thru_z")
    tx_start: Attr[dt.datetime] = Field(name="tx_start", column="in_z")
    tx_end: Attr[dt.datetime] = Field(name="tx_end", column="out_z")
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
    phones: Attr[tuple[ContactPhone, ...]] = VoField(default=())


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


# --------------------------------------------------------------------------- #
# Customer / Location / Depot (models/customer.yaml, D-20 residue, COR-3      #
# Phase 8 increment 7 completion round): a non-temporal parent (Customer)     #
# with TWO VO-bearing to-many children reached the same way — Location reuses #
# Customer's OWN recursive address composite (street/city, geo{country,       #
# elevation}, geo.point{lat,lon}, phones{type,number}) VERBATIM, while Depot  #
# declares a DIFFERENT, flat composite ({line, postcode}) in the SAME         #
# `address` column — a deliberate descriptor divergence the corpus's own      #
# cases pin (decoding a Depot row with Customer's recursive descriptor would  #
# yield observably wrong keys). ``CustomerAddress``/``CustomerGeo``/          #
# ``CustomerPoint``/``CustomerPhone`` get their own names (never reusing      #
# ``Address``/``Geo``/``Phone`` above): Customer's ``Geo`` carries            #
# ``elevation``/``point`` Supplier/Branch's simpler composite does not — a    #
# DIFFERENT shape, the same ``ContactAddress``-style naming discipline.       #
# --------------------------------------------------------------------------- #
class CustomerPoint(ValueObject, frozen=True):
    lat: Attr[float | None] = VoField(type="float64", nullable=True, default=None)
    lon: Attr[float | None] = VoField(type="float64", nullable=True, default=None)


class CustomerGeo(ValueObject, frozen=True):
    # `country` stays Python-optional (accepts and defaults to `None`) even
    # though the DECLARED descriptor is non-nullable — the SAME
    # `ContactGeo.country`/`ContactPoint` discipline (this module's own
    # docstring): the corpus's own fixture rows materialize a missing key
    # (id 5 Kavi) or an explicit JSON-null leaf (id 7 Nils) as a null
    # PROJECTED field on read (the declared-projection absence collapse,
    # `models/customer.yaml`'s own commentary), which the wrap construction
    # must be able to build; `validate_write` — never Pydantic's own
    # required-field enforcement — is what refuses an incomplete WRITE.
    country: Attr[str | None] = VoField(type="string", default=None)
    elevation: Attr[float | None] = VoField(type="float64", nullable=True, default=None)
    point: Attr[CustomerPoint | None] = VoField(nullable=True, default=None)


class CustomerPhone(ValueObject, frozen=True):
    type: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    number: Attr[str | None] = VoField(type="string", nullable=True, default=None)


class CustomerAddress(ValueObject, frozen=True):
    street: Attr[str] = VoField(type="string")
    # `city` stays Python-optional for the SAME reason `CustomerGeo.country`
    # does (see its own comment above): a missing key (ids 5/8/9/10) or an
    # explicit JSON-null leaf (id 7) materializes as a null projected field.
    city: Attr[str | None] = VoField(type="string", default=None)
    geo: Attr[CustomerGeo | None] = VoField(nullable=True, default=None)
    phones: Attr[tuple[CustomerPhone, ...]] = VoField(default=())


class DepotAddress(ValueObject, frozen=True):
    line: Attr[str | None] = VoField(type="string", nullable=True, default=None)
    postcode: Attr[str | None] = VoField(type="string", nullable=True, default=None)


# A SEPARATE registry (ledger D-20's fix, mirroring `animal_owner.
# ANIMAL_OWNER_REGISTRY`): `value_object_models.Customer` already claims the
# canonical name "Customer" in the process default registry, so this family's
# real, installed classes shadow it from their OWN scope rather than colliding
# with it. Parent defaults to the process default (needed for nothing here —
# Customer/Location/Depot reference only each other).
CUSTOMER_REGISTRY = EntityRegistry()


class Customer(Entity, frozen=True, registry=CUSTOMER_REGISTRY):
    """Mirror of ``models/customer.yaml``'s ``Customer``: the recursive
    ``address`` value object, plus TWO VO-bearing to-many children reached by
    a distinct relationship each (``locations`` / ``depots``)."""

    __parallax__ = EntityConfig(table="customer", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    address: Attr[CustomerAddress | None] = Field(nullable=True, default=None)
    locations: Rel[tuple["Location", ...]] = Relationship(
        cardinality="one-to-many",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="Location", attribute="customerId")
        ),
        dependent=True,
        order_by=[OrderByTerm(attr="id", direction="asc")],
    )
    depots: Rel[tuple["Depot", ...]] = Relationship(
        cardinality="one-to-many",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="Depot", attribute="customerId")
        ),
        dependent=True,
        order_by=[OrderByTerm(attr="id", direction="asc")],
    )


class Location(Entity, frozen=True, registry=CUSTOMER_REGISTRY):
    """Mirror of ``models/customer.yaml``'s ``Location``: Customer's OWN
    recursive ``address`` composite, reused VERBATIM (never redeclared) —
    the deep-fetch x value-object composition witness AT DEPTH."""

    __parallax__ = EntityConfig(table="location", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    customer_id: Attr[int] = Field(column="customer_id", type="int64")
    label: Attr[str] = Field(max_length=64)
    address: Attr[CustomerAddress | None] = Field(nullable=True, default=None)
    customer: Rel["Customer"] = ReverseRelationship(reverse_of="Customer.locations")


class Depot(Entity, frozen=True, registry=CUSTOMER_REGISTRY):
    """Mirror of ``models/customer.yaml``'s ``Depot``: a DIFFERENT, FLAT
    ``address`` composite (``{line, postcode}``) in the SAME column name
    Customer/Location use for their own recursive one — the wrong-descriptor
    decode hazard the corpus's own commentary explains (`customer.yaml`
    `:37-47,220-230`)."""

    __parallax__ = EntityConfig(table="depot", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    customer_id: Attr[int] = Field(column="customer_id", type="int64")
    label: Attr[str] = Field(max_length=64)
    address: Attr[DepotAddress | None] = Field(nullable=True, default=None)
    customer: Rel["Customer"] = ReverseRelationship(reverse_of="Customer.depots")
