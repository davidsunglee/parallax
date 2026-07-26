"""The corpus models the class frontend mirrors, each as one sealed hub.

Every hub here composes exactly the classes of one corpus model, so the
descriptor no-drift guard can compare the accepted Metamodel a class family
forms against the one that model's YAML forms. All but ``pk-max`` are
**re-exported** from the installed ``parallax.conformance`` package: an Entity
Class belongs to exactly one hub for its lifetime, so the API-suite's own
execution and this proof compose the same hub rather than a second one over a
second copy of the same classes.

This module deliberately does **not** use ``from __future__ import annotations``:
the engine reads the live ``Attr[T]`` / ``Rel[T]`` annotation objects, so a
scalar attribute's neutral type is inferred from ``T``.
"""

from parallax.conformance.animal_owner import ANIMAL_MODEL
from parallax.conformance.read_models import (
    BALANCE_MODEL,
    DOCUMENT_MODEL,
    PAYMENT_MODEL,
    PERSON_MODEL,
    Balance,
    Passport,
    Payment,
    Person,
)
from parallax.conformance.story_models import ACCOUNT_MODEL, Account
from parallax.conformance.vo_models import (
    BRANCH_MODEL,
    CONTACT_MODEL,
    CUSTOMER_MODEL,
    SHIPMENT_MODEL,
    SUPPLIER_MODEL,
    Branch,
    Contact,
    Shipment,
    Supplier,
)
from parallax.core import MAX, Attr, Entity, MetamodelHub, attr, index

_NS = "parallax.compatibility"

__all__ = [
    "MIRRORED",
    "PK_MAX_MODEL",
    "Account",
    "Attendee",
    "Balance",
    "Branch",
    "Contact",
    "Passport",
    "Payment",
    "Person",
    "Shipment",
    "Supplier",
]


class Attendee(
    Entity,
    table="attendee",
    namespace=_NS,
    indices=(index("attendee_pk", "id", unique=True),),
):
    """Mirror of ``models/pk-max.yaml`` (the ``max`` primary-key generation)."""

    id: Attr[int] = attr(primary_key=MAX)
    name: Attr[str] = attr(max_length=64)


PK_MAX_MODEL = MetamodelHub(Attendee)

MIRRORED: list[tuple[str, MetamodelHub]] = [
    ("account", ACCOUNT_MODEL),
    ("pk-max", PK_MAX_MODEL),
    ("person", PERSON_MODEL),
    ("balance", BALANCE_MODEL),
    ("payment", PAYMENT_MODEL),
    ("document", DOCUMENT_MODEL),
    ("animal", ANIMAL_MODEL),
    ("supplier", SUPPLIER_MODEL),
    ("branch", BRANCH_MODEL),
    ("contact", CONTACT_MODEL),
    ("shipment", SHIPMENT_MODEL),
    ("customer", CUSTOMER_MODEL),
]
"""Corpus model stem -> the hub the idiomatic classes for it compose into."""
