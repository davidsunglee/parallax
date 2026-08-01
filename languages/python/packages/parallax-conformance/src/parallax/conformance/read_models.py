"""Idiomatic Entity Classes mirroring the corpus read and inheritance families.

One class family per corpus model: ``models/balance.yaml`` (a plain
Transaction-Time-Only entity), ``models/payment.yaml`` (table-per-hierarchy),
``models/document.yaml`` (table-per-concrete-subtype with an intermediate
abstract subtype and a polymorphic owner), the non-owner portion of
``models/animal.yaml`` (table-per-hierarchy), ``models/rate.yaml``
(table-per-concrete-subtype bitemporal, the root alone selecting the
``Bitemporal`` base because temporal shape is family-wide and root-owned), and
``models/person.yaml`` (a one-to-one dependent relationship).

Each family is composed into its own sealed hub here, named for the corpus model
it mirrors, because an Entity Class belongs to exactly one hub for its lifetime:
the descriptor no-drift guard, the API-suite read stories, and the unit lane all
compose the same hub rather than a second one over the same classes. The animal
family is the one exception — ``models/animal.yaml`` also declares the
polymorphic owner ``Person``, whose canonical name collides with this module's
own ``Person`` (``models/person.yaml``), so the owner and the family's hub live
together in :mod:`parallax.conformance.animal_owner`.

Owned by ``parallax.conformance`` rather than by the test suite because
``read_stories.py`` is a real dev-only package module whose snippets render into
the Usage Guide via ``gen-usage-guide`` (which runs outside pytest entirely) and
whose statements execute through the shipped ``db.find`` against real Postgres,
so it needs classes resolvable at ordinary import time.

This module deliberately avoids ``from __future__ import annotations`` so the
engine reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

from decimal import Decimal

from parallax.core import (
    ONE_TO_MANY,
    ONE_TO_ONE,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Int32,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    attr,
    index,
    rel,
)

_NS = "parallax.compatibility"

__all__ = [
    "BALANCE_MODEL",
    "DOCUMENT_MODEL",
    "PAYMENT_MODEL",
    "PERSON_MODEL",
    "RATE_MODEL",
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
# Balance: Transaction-Time-Only (the TxTemporal base), models/balance.yaml.   #
# --------------------------------------------------------------------------- #
class Balance(
    TxTemporal,
    table="balance",
    namespace=_NS,
    indices=(
        index("balance_pk", "id", "tx_start", unique=True),
        index("balance_acct", "acct_num"),
    ),
):
    id: Attr[int] = attr(primary_key=True, column="bal_id")
    acct_num: Attr[str] = attr(max_length=32)
    value: Attr[Decimal] = attr(column="val", precision=18, scale=2)


BALANCE_MODEL = DomainModel(Balance)


# --------------------------------------------------------------------------- #
# Payment: table-per-hierarchy (models/payment.yaml).                          #
# --------------------------------------------------------------------------- #
class Payment(
    Entity,
    table="payment",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=18, scale=2)


class CardPayment(Payment, namespace=_NS, inheritance=ConcreteSubtype(tag_value="card")):
    card_network: Attr[str | None] = attr(max_length=16)


class CashPayment(Payment, namespace=_NS, inheritance=ConcreteSubtype(tag_value="cash")):
    tendered: Attr[Decimal | None] = attr(precision=18, scale=2)


PAYMENT_MODEL = DomainModel(Payment, CardPayment, CashPayment)


# --------------------------------------------------------------------------- #
# Document: table-per-concrete-subtype (models/document.yaml).                 #
# --------------------------------------------------------------------------- #
class Document(Entity, namespace=_NS, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str] = attr(max_length=64)
    folder_id: Attr[int | None]


class FinancialDocument(Document, namespace=_NS, inheritance=AbstractSubtype):
    currency: Attr[str] = attr(max_length=3)


class Invoice(FinancialDocument, table="invoice", namespace=_NS, inheritance=ConcreteSubtype):
    amount_due: Attr[Decimal] = attr(precision=18, scale=2)


class Receipt(FinancialDocument, table="receipt", namespace=_NS, inheritance=ConcreteSubtype):
    paid_amount: Attr[Decimal] = attr(precision=18, scale=2)


class Memo(Document, table="memo", namespace=_NS, inheritance=ConcreteSubtype):
    body: Attr[str] = attr(max_length=64)


class Folder(
    Entity,
    table="folder",
    namespace=_NS,
    indices=(index("folder_pk", "id", unique=True),),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    documents: Rel[tuple[Document, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "folder_id"))


DOCUMENT_MODEL = DomainModel(Document, FinancialDocument, Invoice, Receipt, Memo, Folder)


# --------------------------------------------------------------------------- #
# Animal: table-per-hierarchy (models/animal.yaml). The family's polymorphic   #
# owner and the hub composing them both live in `animal_owner` (this module's  #
# own docstring).                                                              #
# --------------------------------------------------------------------------- #
class Animal(
    Entity,
    table="animal",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    owner_id: Attr[int | None]
    # A relationship target is read as a SPELLING and resolved in the hub's own
    # candidate set, so this names `animal_owner.Person` — the owner
    # `models/animal.yaml` declares — never this module's unrelated `Person`
    # (`models/person.yaml`), which shares only the canonical name.
    owner: Rel["Person | None"] = rel(reverse_of="animals")


class Pet(Animal, namespace=_NS, inheritance=AbstractSubtype):
    license_id: Attr[str | None] = attr(max_length=16)


class Dog(Pet, namespace=_NS, inheritance=ConcreteSubtype(tag_value="dog")):
    bark_volume: Attr[int | None] = attr(type=Int32)


class Cat(Pet, namespace=_NS, inheritance=ConcreteSubtype(tag_value="cat")):
    indoor: Attr[bool | None]


class WildBoar(Animal, namespace=_NS, inheritance=ConcreteSubtype(tag_value="boar")):
    """A concrete SIBLING branch directly under ``Animal`` (not a ``Pet``):
    proves narrowing a read of ``Animal`` to ``Pet`` cannot broaden back out
    to ``WildBoar`` — its effective concrete set is ``[Dog, Cat]``, never
    ``WildBoar`` (``m-inheritance-064``/``-072``'s own rejected narrows)."""

    tusk_length: Attr[Decimal | None] = attr(precision=18, scale=2)


# --------------------------------------------------------------------------- #
# Rate: table-per-concrete-subtype BITEMPORAL family (models/rate.yaml). The   #
# root ALONE selects the Bitemporal base (m-inheritance "Inherited members",   #
# the binding root-ownership decision); DepositRate/LoanRate inherit the       #
# family's temporal shape and declare NONE of their own.                       #
# --------------------------------------------------------------------------- #
class Rate(
    Bitemporal,
    namespace=_NS,
    inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE),
    indices=(index("rate_pk", "id", "valid_start", "tx_start", unique=True),),
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=18, scale=2)


class DepositRate(Rate, table="deposit_rate", namespace=_NS, inheritance=ConcreteSubtype):
    grade: Attr[str | None] = attr(max_length=8)


class LoanRate(Rate, table="loan_rate", namespace=_NS, inheritance=ConcreteSubtype):
    spread: Attr[Decimal | None] = attr(precision=18, scale=2)


RATE_MODEL = DomainModel(Rate, DepositRate, LoanRate)


# --------------------------------------------------------------------------- #
# Person/Passport: a one-to-one dependent relationship (models/person.yaml).   #
# --------------------------------------------------------------------------- #
class Person(
    Entity,
    table="person",
    namespace=_NS,
    indices=(index("person_pk", "id", unique=True),),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    passport: Rel["Passport"] = rel(
        cardinality=ONE_TO_ONE, join=("id", "person_id"), dependent=True
    )


class Passport(
    Entity,
    table="passport",
    namespace=_NS,
    indices=(
        index("passport_pk", "id", unique=True),
        index("passport_person", "person_id", unique=True),
    ),
):
    id: Attr[int] = attr(primary_key=True)
    person_id: Attr[int]
    number: Attr[str] = attr(max_length=32)
    holder: Rel[Person | None] = rel(reverse_of="passport")


PERSON_MODEL = DomainModel(Person, Passport)
