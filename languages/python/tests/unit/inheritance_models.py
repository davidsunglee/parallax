"""Idiomatic entity classes mirroring the corpus's two inheritance families
(D-7 inheritance class spelling, DQ2, COR-3 Phase 7 increment 6a):
``models/payment.yaml`` (table-per-hierarchy: ``Payment`` / ``CardPayment`` /
``CashPayment``) and ``models/document.yaml`` (table-per-concrete-subtype, with
an intermediate abstract subtype and a polymorphic owner: ``Document`` /
``FinancialDocument`` / ``Invoice`` / ``Receipt`` / ``Memo`` / ``Folder``).
This module deliberately avoids ``from __future__ import annotations`` so the
metaclass reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

from decimal import Decimal

from parallax.core import Attr, Entity, EntityConfig, Field, Rel, Relationship
from parallax.core.entity.base import Concrete, FamilyRoot

_NS = "parallax.compatibility"


# --------------------------------------------------------------------------- #
# Payment: table-per-hierarchy (models/payment.yaml).                         #
# --------------------------------------------------------------------------- #
class Payment(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="payment",
        namespace=_NS,
        mutability="transactional",
        inheritance=FamilyRoot(strategy="table-per-hierarchy", tag="kind"),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    amount: Attr[Decimal] = Field(type="decimal(18,2)")


class CardPayment(Payment, frozen=True):
    __parallax__ = EntityConfig(
        namespace=_NS, mutability="transactional", inheritance=Concrete(tag_value="card")
    )

    card_network: Attr[str | None] = Field(
        type="string", column="card_network", max_length=16, nullable=True
    )


class CashPayment(Payment, frozen=True):
    __parallax__ = EntityConfig(
        namespace=_NS, mutability="transactional", inheritance=Concrete(tag_value="cash")
    )

    tendered: Attr[Decimal | None] = Field(type="decimal(18,2)", nullable=True)


class WirePayment(Payment, frozen=True):
    """A TPH concrete subtype with an EXPLICIT table override — D-7's escape
    hatch: ``EntityConfig(table=...)`` wins over the strategy's own shared-
    table default (not part of the payment.yaml no-drift proof; a standalone
    structural fixture)."""

    __parallax__ = EntityConfig(
        table="wire_payment",
        namespace=_NS,
        mutability="transactional",
        inheritance=Concrete(tag_value="wire"),
    )

    reference: Attr[str | None] = Field(type="string", max_length=32, nullable=True)


# --------------------------------------------------------------------------- #
# Document: table-per-concrete-subtype (models/document.yaml).                #
# --------------------------------------------------------------------------- #
class Document(Entity, frozen=True):
    __parallax__ = EntityConfig(
        namespace=_NS,
        mutability="transactional",
        inheritance=FamilyRoot(strategy="table-per-concrete-subtype"),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    title: Attr[str] = Field(max_length=64)
    folder_id: Attr[int | None] = Field(type="int64", column="folder_id", nullable=True)


class FinancialDocument(Document, frozen=True):
    __parallax__ = EntityConfig(namespace=_NS)

    currency: Attr[str] = Field(max_length=3)


class Invoice(FinancialDocument, frozen=True):
    __parallax__ = EntityConfig(namespace=_NS, mutability="transactional", inheritance=Concrete())

    amount_due: Attr[Decimal] = Field(type="decimal(18,2)", column="amount_due")


class Receipt(FinancialDocument, frozen=True):
    __parallax__ = EntityConfig(namespace=_NS, mutability="transactional", inheritance=Concrete())

    paid_amount: Attr[Decimal] = Field(type="decimal(18,2)", column="paid_amount")


class Memo(Document, frozen=True):
    __parallax__ = EntityConfig(namespace=_NS, mutability="transactional", inheritance=Concrete())

    body: Attr[str] = Field(max_length=64)


class Folder(Entity, frozen=True):
    __parallax__ = EntityConfig(table="folder", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=32)
    documents: Rel[tuple["Document", ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = Document.folderId",
        related_entity="Document",
        reverse_name="folder",
        foreign_key="folder_id",
    )
