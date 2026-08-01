"""The corpus models the class frontend mirrors, each as one sealed hub.

Every hub here composes exactly the classes of one corpus model, so the
descriptor no-drift guard can compare the accepted Metamodel a class family
forms against the one that model's YAML forms. Most hubs are **re-exported** from
the installed ``parallax.conformance`` package: an Entity Class belongs to
exactly one hub for its lifetime, so the API-suite's own execution and this proof
compose the same hub rather than a second one over a second copy of the same
classes. The families declared below are the ones no story or example needs — a
declaration feature the guard must cover whose corpus carrier nothing else
exercises — so they live with the proof that is their only reader.

``UNMIRRORED`` names every corpus model this module does *not* mirror, with the
reason, so the pair partitions the corpus exactly and a new model cannot be
silently left out of the equivalence proof.

This module deliberately does **not** use ``from __future__ import annotations``:
the engine reads the live ``Attr[T]`` / ``Rel[T]`` annotation objects, so a
scalar attribute's neutral type is inferred from ``T``.
"""

import datetime as dt
import uuid
from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType

from parallax.conformance.animal_owner import ANIMAL_MODEL
from parallax.conformance.graph_models import POLICY_MODEL
from parallax.conformance.read_models import (
    BALANCE_MODEL,
    DOCUMENT_MODEL,
    PAYMENT_MODEL,
    PERSON_MODEL,
    RATE_MODEL,
    Balance,
    Passport,
    Payment,
    Person,
)
from parallax.conformance.story_models import (
    ACCOUNT_MODEL,
    ORDERS_MODEL,
    POSITION_MODEL,
    WALLET_MODEL,
    Account,
)
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
from parallax.core import (
    MAX,
    Attr,
    Entity,
    Float32,
    MetamodelHub,
    Sequence,
    attr,
    index,
)

_NS = "parallax.compatibility"

__all__ = [
    "MIRRORED",
    "PK_MAX_MODEL",
    "PK_SEQUENCE_MODEL",
    "TAXPAYER_MODEL",
    "UNMIRRORED",
    "WRITABLE_SCALARS_MODEL",
    "Account",
    "Attendee",
    "Badge",
    "Balance",
    "Branch",
    "Contact",
    "Pass",
    "Passport",
    "Payment",
    "Person",
    "PkSequence",
    "Shipment",
    "Supplier",
    "Taxpayer",
    "Ticket",
    "Voucher",
    "WritableScalar",
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


class PkSequence(
    Entity,
    table="pk_sequence",
    namespace=_NS,
    indices=(index("pk_sequence_pk", "name", unique=True),),
):
    """The sequence registry of ``models/pk-sequence.yaml``: one row per named
    sequence holding the next value to hand out. Its own key is a string, which
    is why ``primary_key=True`` carries no generation restriction."""

    name: Attr[str] = attr(primary_key=True, max_length=64)
    next_val: Attr[int]


class Badge(
    Entity,
    table="badge",
    namespace=_NS,
    indices=(index("badge_pk", "id", unique=True),),
):
    """``Sequence`` allocation on every parameter's semantic default."""

    id: Attr[int] = attr(primary_key=Sequence(name="badge_seq"))
    holder: Attr[str] = attr(max_length=64)


class Ticket(
    Entity,
    table="ticket",
    namespace=_NS,
    indices=(index("ticket_pk", "id", unique=True),),
):
    """``Sequence`` allocation with an offset start and a stride above one."""

    id: Attr[int] = attr(
        primary_key=Sequence(name="ticket_seq", initial_value=1000, increment_size=5)
    )
    tier: Attr[str] = attr(max_length=64)


class Pass(
    Entity,
    table="pass",
    namespace=_NS,
    indices=(index("pass_pk", "id", unique=True),),
):
    """``Sequence`` allocation that reserves a batch per registry round trip."""

    id: Attr[int] = attr(primary_key=Sequence(name="pass_seq", batch_size=3))
    zone: Attr[str] = attr(max_length=64)


class Voucher(
    Entity,
    table="voucher",
    namespace=_NS,
    indices=(index("voucher_pk", "id", unique=True),),
):
    """``Sequence`` allocation with every parameter set at once."""

    id: Attr[int] = attr(
        primary_key=Sequence(name="voucher_seq", initial_value=100, increment_size=10, batch_size=2)
    )
    label: Attr[str] = attr(max_length=64)


PK_SEQUENCE_MODEL = MetamodelHub(PkSequence, Badge, Ticket, Pass, Voucher)


class WritableScalar(
    Entity,
    table="writable_scalars",
    namespace=_NS,
    indices=(index("writable_scalars_pk", "id", unique=True),),
):
    """Mirror of ``models/writable-scalars.yaml``: the neutral scalars no other
    mirrored model reaches — ``Float32`` under the two-variant ``float`` family,
    ``bytes``, ``time``, ``uuid``, and a ``decimal`` precision/scale away from
    the corpus's ubiquitous money column."""

    id: Attr[int] = attr(primary_key=True)
    f32: Attr[float | None] = attr(type=Float32)
    f64: Attr[float | None]
    payload: Attr[bytes | None]
    local_time: Attr[dt.time | None]
    external_id: Attr[uuid.UUID | None]
    amount: Attr[Decimal | None] = attr(precision=18, scale=4)
    label: Attr[str | None] = attr(max_length=8)


WRITABLE_SCALARS_MODEL = MetamodelHub(WritableScalar)


class Taxpayer(
    Entity,
    table="taxpayer",
    namespace=_NS,
    indices=(
        index("taxpayer_pk", "id", unique=True),
        index("taxpayer_tax_id", "tax_id", unique=True),
    ),
):
    """Mirror of ``models/taxpayer.yaml``: the canonical name ``taxID`` is not
    reachable from any Python member name by the snake -> camel conversion, so
    ``name=`` authors it. ``column=`` is spelled out because ``taxID`` derives
    the mechanical default ``tax_i_d``, while the model stores the attribute as
    the acronym-friendly ``tax_id``."""

    id: Attr[int] = attr(primary_key=True)
    tax_id: Attr[str] = attr(name="taxID", column="tax_id", max_length=32)
    name: Attr[str] = attr(max_length=64)


TAXPAYER_MODEL = MetamodelHub(Taxpayer)

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
    ("orders", ORDERS_MODEL),
    ("policy", POLICY_MODEL),
    ("position", POSITION_MODEL),
    ("rate", RATE_MODEL),
    ("wallet", WALLET_MODEL),
    ("pk-sequence", PK_SEQUENCE_MODEL),
    ("writable-scalars", WRITABLE_SCALARS_MODEL),
    ("taxpayer", TAXPAYER_MODEL),
]
"""Corpus model stem -> the hub the idiomatic classes for it compose into."""

UNMIRRORED: Mapping[str, str] = MappingProxyType(
    {
        "appliance": (
            "no mirror authored; its declaration is the mirrored `rate` family's "
            "table-per-concrete-subtype shape plus the root-owned optimistic-lock version "
            "`account` already proves"
        ),
        "error-cases": (
            "behavioral-only model: it exists to provoke the m-db-error classes, and its only "
            "declaration beyond `account`'s is a non-primary-key unique index, which the "
            "mirrored `person` family already carries"
        ),
        "event": (
            "no mirror authored; the only construct it adds over the mirrored `account` is a "
            "plain `timestamp` member outside an as-of axis"
        ),
        "grade": (
            "no mirror authored; its subject is a reserved word appearing as a physical column "
            "name, which is SQL generation rather than declaration -- the `column=` override it "
            "needs is already proven by the mirrored `position`"
        ),
        "instrument": (
            "no mirror authored; it composes the mirrored `payment`'s table-per-hierarchy with "
            "the mirrored `rate`'s root-owned bitemporal axes, both already proven separately"
        ),
        "invoice": (
            "no mirror authored; it composes the mirrored `balance`'s transaction-time-only axis "
            "with the mirrored `orders`' dependent one-to-many, both already proven separately"
        ),
        "lease": (
            "no mirror authored; its subject is a mixed-temporality chain, and per-class base "
            "selection means the chain adds no construct the mirrored `balance` and `orders` "
            "do not already carry"
        ),
        "ledger": (
            "no mirror authored; it is the mirrored `balance`'s declaration shape -- a "
            "transaction-time-only entity with column overrides -- with different names"
        ),
        "member-column-defaults": (
            "no mirror authored; its ASCII default-column vectors are covered directly by "
            "the metamodel naming, declaration frontend, descriptor serde/export, and "
            "compile-sweep contract tests"
        ),
        "materialization-key-compatibility": (
            "portable compatibility-only model whose overlap and qualified-identity behavior "
            "is exercised directly by the compile sweep and generic descriptor adapter"
        ),
        "pk-audit": (
            "no mirror authored; it composes the `sequence` generation `pk-sequence` proves with "
            "the transaction-time-only axis `balance` proves"
        ),
        "quote": (
            "no mirror authored; it is the mirrored `rate`'s table-per-concrete-subtype family "
            "with a transaction-time-only root axis in place of the bitemporal pair"
        ),
        "reading": (
            "no mirror authored; it is the mirrored `payment`'s table-per-hierarchy family with "
            "a transaction-time-only root axis and a subtype that declares no local member"
        ),
        "scalars": (
            "no mirror authored; the mirrored `writable-scalars` carries the same scalar set, so "
            "the only construct this model adds is `persistence=READ_ONLY`"
        ),
        "shared-local-name": (
            "portable compatibility-only model: it exists to make one local Entity name "
            "ambiguous in a reference position, and its declarations are the mirrored "
            "`orders`' many-to-one join with different namespaces"
        ),
        "storage-layout": (
            "no mirror authored; it places the mirrored `payment`'s table-per-hierarchy family, "
            "the mirrored `document`'s table-per-concrete-subtype family, and the mirrored "
            "`customer`'s top-level Value Object in one descriptor so physical composition can "
            "be witnessed, adding no declaration construct of its own"
        ),
        "subscriber": (
            "no mirror authored; it composes the nested Value Object tree the mirrored `customer` "
            "and `supplier` prove with the optimistic-lock version `account` proves"
        ),
        "vehicle": (
            "no mirror authored; it composes the mirrored `payment`'s table-per-hierarchy with "
            "the root-owned optimistic-lock version `account` proves"
        ),
        "workshop": (
            "no mirror authored; a hub composes any number of classes and the mirrored `document` "
            "already relates an owner to an abstract root, so two independent families in one "
            "descriptor add no construct"
        ),
    }
)
"""Corpus model stem -> why the class frontend does not mirror it.

Every reason here is either a redundant declaration shape or an unwritten
mirror. **No corpus model is unmirrorable:** the class grammar can author all 39,
so this mapping records the guard's chosen breadth, not a grammar limit. A reason
that ever becomes a real limit belongs in the grammar's own specification instead.
"""
