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
from parallax.conformance.animal_owner import Person as AnimalOwnerPerson
from parallax.conformance.read_models import Animal as AnimalRoot
from parallax.conformance.read_models import Balance, Cat, Dog, Passport, Person, Pet
from parallax.conformance.read_models import WildBoar as AnimalWildBoar
from parallax.conformance.story_models import Account
from parallax.conformance.vo_models import (
    Branch,
    Contact,
    Customer,
    Depot,
    Location,
    Shipment,
    Supplier,
)
from parallax.core import Attr, Entity, EntityConfig, Field

_NS = "parallax.compatibility"

# ``Account`` / ``Person`` / ``Passport`` / ``Balance`` / the whole ``Animal``
# family are all **re-exported** from the installed ``parallax.conformance``
# package (the API Conformance Suite's own write/read/graph stories execute
# the SAME classes against `db.find`/`db.transact`) rather than redeclared
# here — the discipline every installed mirror follows so this module's own
# no-drift proof and the API-suite's execution resolve the exact SAME
# registered class, never a second, differently-scoped copy racing it in the
# same registry. `animal_owner.Person` (the animal family's REAL owner) lives
# in its OWN `EntityRegistry` (ledger D-20): a DIFFERENT class than THIS
# module's own `Person` (`models/person.yaml`) despite sharing the identical
# canonical name — the descriptor no-drift proof below is purely class-list-
# based (`descriptor_document`), so combining classes from two different
# registries into one "animal" entry is exactly as sound as any other.


class Attendee(Entity, frozen=True):
    """Mirror of ``models/pk-max.yaml`` (the ``max`` pk-generator strategy)."""

    __parallax__ = EntityConfig(table="attendee", namespace=_NS, mutability="transactional")

    id: Attr[int] = Field(primary_key=True, pk_generator="max")
    name: Attr[str] = Field(max_length=64)


# corpus model stem -> the idiomatic classes assembled into that descriptor.
#
# "customer" spans THREE entities (customer.yaml's own descriptor): the
# non-temporal `Customer` root plus its two VO-bearing to-many children,
# `Location` (reusing Customer's own recursive `address` composite verbatim)
# and `Depot` (a deliberately DIVERGENT flat `address` composite in the same
# column) — all installed together in `parallax.conformance.vo_models`
# (ledger D-20/D-21).
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
    ("animal", [AnimalRoot, Pet, Dog, Cat, AnimalWildBoar, AnimalOwnerPerson]),
    ("supplier", [Supplier]),
    ("branch", [Branch]),
    ("contact", [Contact]),
    ("shipment", [Shipment]),
    ("customer", [Customer, Location, Depot]),
]


def drop_indices(document: dict[str, Any]) -> dict[str, Any]:
    """A descriptor document with the physical ``indices`` array removed."""
    clone = copy.deepcopy(document)
    entities = [clone["entity"]] if "entity" in clone else clone["entities"]
    for entity in entities:
        entity.pop("indices", None)
    return clone
