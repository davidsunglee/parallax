"""Idiomatic entity classes mirroring corpus model families.

These are the API Conformance Suite's hand-authored classes; their exported
descriptors must be structurally equal to the corpus YAML (the descriptor
no-drift guard). The unit lane imports this module too, so the class frontend is
exercised under coverage. Physical ``indices`` are a storage concern the class
frontend does not express, so the guard compares the logical model (see
``drop_indices``).

This module deliberately does **not** use ``from __future__ import annotations``:
the metaclass reads the live ``Attr[T]`` / ``Rel[T]`` annotation objects, so the
neutral type of a scalar attribute can be inferred from ``T`` and relationship
targets use string forward references (``Rel["Passport"]``).
"""

import copy
import datetime as dt
from decimal import Decimal
from typing import Any

from parallax.core import AsOfAttribute, Attr, Entity, EntityConfig, Field, Rel, Relationship

_NS = "parallax.compatibility"


class Account(Entity, frozen=True):
    """Mirror of ``models/account.yaml`` (plain transactional entity)."""

    __parallax__ = EntityConfig(table="account", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none")
    owner: Attr[str] = Field(max_length=64)
    balance: Attr[Decimal] = Field(type="decimal(18,2)")
    version: Attr[int] = Field(type="int32", optimistic_locking=True)


class Attendee(Entity, frozen=True):
    """Mirror of ``models/pk-max.yaml`` (the ``max`` pk-generator strategy)."""

    __parallax__ = EntityConfig(table="attendee", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="max")
    name: Attr[str] = Field(max_length=64)


class Person(Entity, frozen=True):
    """Mirror of ``models/person.yaml`` Person (one-to-one dependent relationship)."""

    __parallax__ = EntityConfig(table="person", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none")
    name: Attr[str] = Field(max_length=64)
    passport: Rel["Passport"] = Relationship(
        cardinality="one-to-one",
        join="this.id = Passport.personId",
        related_entity="Passport",
        reverse_name="holder",
        dependent=True,
        foreign_key="person_id",
    )


class Passport(Entity, frozen=True):
    """Mirror of ``models/person.yaml`` Passport (the one-to-one peer)."""

    __parallax__ = EntityConfig(table="passport", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="none")
    person_id: Attr[int]
    number: Attr[str] = Field(max_length=32)
    holder: Rel["Person"] = Relationship(
        cardinality="one-to-one",
        join="this.personId = Person.id",
        related_entity="Person",
        reverse_name="passport",
        foreign_key="person_id",
    )


class Balance(Entity, frozen=True):
    """Mirror of ``models/balance.yaml`` (audit-only / processing-temporal).

    The D-7 temporal class spelling: the processing axis is declared in the
    descriptor's own vocabulary via ``EntityConfig.as_of``, and the interval
    bounds are ordinary scalar attributes beside it.
    """

    __parallax__ = EntityConfig(
        table="balance",
        namespace=_NS,
        mutability="transactional",
        as_of=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", column="bal_id")
    acct_num: Attr[str] = Field(max_length=32)
    value: Attr[Decimal] = Field(type="decimal(18,2)", column="val")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")


# corpus model stem -> the idiomatic classes assembled into that descriptor.
MIRRORED: list[tuple[str, list[type]]] = [
    ("account", [Account]),
    ("pk-max", [Attendee]),
    ("person", [Person, Passport]),
    ("balance", [Balance]),
]


def drop_indices(document: dict[str, Any]) -> dict[str, Any]:
    """A descriptor document with the physical ``indices`` array removed."""
    clone = copy.deepcopy(document)
    entities = [clone["entity"]] if "entity" in clone else clone["entities"]
    for entity in entities:
        entity.pop("indices", None)
    return clone
