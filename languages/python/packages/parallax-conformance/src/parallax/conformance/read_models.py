"""Idiomatic entity classes the API-suite read stories (`read_stories.py`)
build statements over: real-named mirrors of ``models/balance.yaml`` (a plain
Transaction-Time-Only temporal entity), ``models/payment.yaml`` (table-per-hierarchy:
``Payment`` / ``CardPayment`` / ``CashPayment``), ``models/document.yaml``
(table-per-concrete-subtype: ``Document`` / ``FinancialDocument`` / ``Invoice``
/ ``Receipt`` / ``Memo`` / ``Folder``), the NON-owner portion of
``models/animal.yaml`` (table-per-hierarchy: ``Animal`` / ``Pet`` / ``Dog`` /
``Cat``), ``models/rate.yaml`` (table-per-concrete-subtype BITEMPORAL:
``Rate`` / ``DepositRate`` / ``LoanRate`` — the root ALONE selects the
family's ``Bitemporal`` base; the concrete subtypes declare no temporal shape
of their own, per the binding root-ownership decision, m-inheritance
"Inherited members"), and
``models/person.yaml`` (``Person`` / ``Passport``, a one-to-one dependent
relationship).

Owned by ``parallax.conformance`` for the same reason ``story_models`` /
``graph_models`` are: ``read_stories.py`` is a real dev-only package module
whose snippets render into the Usage Guide via ``gen-usage-guide`` (which runs
outside pytest entirely) and whose statements execute through the shipped
``db.find`` against real Postgres, so it needs classes resolvable at ordinary
import time, not only under pytest's test-path magic — `tests/mirrored_models.py`
/ `tests/inheritance_models.py` / `tests/snapshot_models.py` (test-only, moved
there for exactly this package-boundary reason) cannot be imported from here.
`tests/mirrored_models.py` RE-EXPORTS ``Person``/``Passport`` from here (the
``Balance`` discipline), rather than redeclaring them.

``models/animal.yaml``'s own polymorphic owner is ALSO named ``Person`` — a
literal canonical-name collision with THIS module's ``Person``
(``models/person.yaml``). Ledger D-20 (COR-3 Phase 8 increment 7) resolves the
structural constraint that used to make this collision fatal: an explicit,
independently-collision-checked :class:`~parallax.core.entity.base.EntityRegistry`
scope now lets the SAME canonical name coexist across two registries. The
animal family's own owner accordingly lives in a SEPARATE installed module,
`parallax.conformance.animal_owner`, scoped to its own registry (whose parent
is this module's own DEFAULT registry, so it still resolves ``Animal`` /
``Pet`` / ``Dog`` / ``Cat`` below without redeclaring them) — never here,
where it would immediately collide with this module's OWN ``Person``.

This module deliberately avoids ``from __future__ import annotations`` so the
metaclass reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

from decimal import Decimal

from parallax.core import (
    Attr,
    Bitemporal,
    Entity,
    EntityConfig,
    Field,
    Rel,
    Relationship,
    RelationshipJoin,
    RelationshipTarget,
    ReverseRelationship,
    TxTemporal,
)
from parallax.core.entity.base import Concrete, FamilyRoot

_NS = "parallax.compatibility"

__all__ = [
    "Balance",
    "CardPayment",
    "CashPayment",
    "Cat",
    "DepositRate",
    "Document",
    "Dog",
    "FinancialDocument",
    "Folder",
    "Invoice",
    "LoanRate",
    "Memo",
    "Passport",
    "Payment",
    "Person",
    "Pet",
    "Rate",
    "Receipt",
    "WildBoar",
]


# --------------------------------------------------------------------------- #
# Balance: Transaction-Time-Only (the TxTemporal base), mirrors               #
# models/balance.yaml.                                                        #
# --------------------------------------------------------------------------- #
class Balance(TxTemporal, frozen=True):
    __parallax__ = EntityConfig(table="balance", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none", column="bal_id")
    acct_num: Attr[str] = Field(max_length=32)
    value: Attr[Decimal] = Field(type="decimal(18,2)", column="val")


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
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="Document", attribute="folderId")
        ),
    )


# --------------------------------------------------------------------------- #
# Animal: table-per-hierarchy (models/animal.yaml), owner side DELIBERATELY   #
# omitted (module docstring: the Person registry collision).                  #
# --------------------------------------------------------------------------- #
class Animal(Entity, frozen=True):
    __parallax__ = EntityConfig(
        namespace=_NS,
        mutability="transactional",
        inheritance=FamilyRoot(strategy="table-per-hierarchy", tag="kind"),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=32)
    owner_id: Attr[int | None] = Field(type="int64", column="owner_id", nullable=True)


class Pet(Animal, frozen=True):
    __parallax__ = EntityConfig(namespace=_NS)

    license_id: Attr[str | None] = Field(
        type="string", max_length=16, column="license_id", nullable=True
    )


class Dog(Pet, frozen=True):
    __parallax__ = EntityConfig(
        namespace=_NS, mutability="transactional", inheritance=Concrete(tag_value="dog")
    )

    bark_volume: Attr[int | None] = Field(type="int32", column="bark_volume", nullable=True)


class Cat(Pet, frozen=True):
    __parallax__ = EntityConfig(
        namespace=_NS, mutability="transactional", inheritance=Concrete(tag_value="cat")
    )

    indoor: Attr[bool | None] = Field(type="boolean", column="indoor", nullable=True)


class WildBoar(Animal, frozen=True):
    """A concrete SIBLING branch directly under ``Animal`` (not a ``Pet``):
    proves narrowing a read of ``Animal`` to ``Pet`` cannot broaden back out
    to ``WildBoar`` — its effective concrete set is ``[Dog, Cat]``, never
    ``WildBoar`` (``m-inheritance-064``/``-072``'s own rejected narrows)."""

    __parallax__ = EntityConfig(
        namespace=_NS, mutability="transactional", inheritance=Concrete(tag_value="boar")
    )

    tusk_length: Attr[Decimal | None] = Field(
        type="decimal(18,2)", column="tusk_length", nullable=True
    )


# --------------------------------------------------------------------------- #
# Rate: table-per-concrete-subtype BITEMPORAL family (models/rate.yaml). The   #
# root ALONE selects the Bitemporal base (m-inheritance "Inherited members",  #
# the binding root-ownership decision); DepositRate/LoanRate inherit the      #
# family's temporal shape and declare NONE of their own.                      #
# --------------------------------------------------------------------------- #
class Rate(Bitemporal, frozen=True):
    __parallax__ = EntityConfig(
        namespace=_NS,
        mutability="transactional",
        inheritance=FamilyRoot(strategy="table-per-concrete-subtype"),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    amount: Attr[Decimal] = Field(type="decimal(18,2)")


class DepositRate(Rate, frozen=True):
    __parallax__ = EntityConfig(namespace=_NS, mutability="transactional", inheritance=Concrete())

    grade: Attr[str | None] = Field(type="string", max_length=8, nullable=True)


class LoanRate(Rate, frozen=True):
    __parallax__ = EntityConfig(namespace=_NS, mutability="transactional", inheritance=Concrete())

    spread: Attr[Decimal | None] = Field(type="decimal(18,2)", nullable=True)


# --------------------------------------------------------------------------- #
# Person/Passport: a one-to-one dependent relationship (models/person.yaml).   #
# Installed here (ledger D-20/D-21, COR-3 Phase 8 increment 7): the FIRST      #
# production-reachable mirror of this model (`m-snapshot-read-007`).          #
# `mirrored_models.Person`/`.Passport` RE-EXPORT these (the `Balance`          #
# discipline) rather than redeclaring them.                                   #
# --------------------------------------------------------------------------- #
class Person(Entity, frozen=True):
    __parallax__ = EntityConfig(table="person", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none")
    name: Attr[str] = Field(max_length=64)
    passport: Rel["Passport"] = Relationship(
        cardinality="one-to-one",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="Passport", attribute="personId")
        ),
        dependent=True,
    )


class Passport(Entity, frozen=True):
    __parallax__ = EntityConfig(table="passport", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none")
    person_id: Attr[int]
    number: Attr[str] = Field(max_length=32)
    holder: Rel["Person"] = ReverseRelationship(reverse_of="Person.passport")
