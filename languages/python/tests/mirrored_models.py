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
from typing import Any

import inheritance_models as _im
from parallax.conformance.read_models import Balance
from parallax.conformance.story_models import Account
from parallax.core import Attr, Entity, EntityConfig, Field, Rel, Relationship

_NS = "parallax.compatibility"

# ``Account`` (mirror of ``models/account.yaml``) is **re-exported** from
# ``parallax.conformance.story_models`` -- the installed package's own mirror,
# which the API Conformance Suite's write/graph stories execute against
# `db.find`/`db.transact` -- following the SAME ``Balance`` discipline below:
# this module's own no-drift proof and the API-suite's execution resolve the
# exact SAME registered class, never a second, differently-scoped copy racing
# it in the same registry (ledger D-20 fixed the silent version of this bug;
# the fix here is to stop declaring a duplicate at all).


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


# ``Balance`` (mirror of ``models/balance.yaml``, audit-only / processing-
# temporal, the D-7 temporal class spelling) is **re-exported** from
# ``parallax.conformance.read_models`` — the installed package's own mirror,
# which the API Conformance Suite's real-database read stories execute
# against `db.find` — so this module's own no-drift proof and the API-suite's
# execution resolve the exact SAME registered class, never a second,
# differently-scoped copy silently racing it in the shared, global,
# process-wide entity registry.

# corpus model stem -> the idiomatic classes assembled into that descriptor.
#
# "animal" and "customer" are deliberately ABSENT: animal.yaml's own polymorphic
# owner entity is ALSO named "Person" — the same literal canonical name
# `person.yaml`'s own Person/Passport pair above already claims in this shared,
# single, process-wide class registry — so a full descriptor mirror of
# animal.yaml cannot coexist with this module's own Person; see
# `snapshot_models`'s module docstring. customer.yaml's own descriptor spans
# three entities (Customer, Location, Depot); `value_object_models.Customer`
# mirrors only the first (no example needs Location/Depot), so a full-model
# entry would fail this proof by omission, not drift.
MIRRORED: list[tuple[str, list[type]]] = [
    ("account", [Account]),
    ("pk-max", [Attendee]),
    ("person", [Person, Passport]),
    ("balance", [Balance]),
    ("payment", [_im.Payment, _im.CardPayment, _im.CashPayment]),
    (
        "document",
        [_im.Document, _im.FinancialDocument, _im.Invoice, _im.Receipt, _im.Memo, _im.Folder],
    ),
]


def drop_indices(document: dict[str, Any]) -> dict[str, Any]:
    """A descriptor document with the physical ``indices`` array removed."""
    clone = copy.deepcopy(document)
    entities = [clone["entity"]] if "entity" in clone else clone["entities"]
    for entity in entities:
        entity.pop("indices", None)
    return clone
