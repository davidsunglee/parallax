"""Idiomatic Entity Classes for the observation-keying suite: the two include
shapes no corpus mirror carries.

A read observes a row only when its entity is versioned or temporal, and a keyed
write is licensed only by an observation of the row it names. Proving that an
INCLUDED node is licensed therefore needs a relationship whose target is one of
those two, and the corpus has neither: ``mirrored_models`` puts the version
column on ``Ledger``, which no relationship reaches, and the only relationship
into an inheritance family (``Folder.documents``) reaches a family that is
neither temporal nor versioned. These two families supply exactly the missing
edges — one into a VERSIONED entity, one into a TEMPORAL table-per-hierarchy
family, so an included level's rows resolve to more than one concrete.

They are declared here rather than beside the corpus mirrors because
``read_models``, ``graph_models``, and ``mirrored_models`` mirror corpus YAML
and are pinned by the descriptor and graph-story no-drift guards: a family with
no corpus counterpart cannot live in any of them.

This module deliberately avoids ``from __future__ import annotations`` so the
metaclass reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

from decimal import Decimal

from parallax.core import (
    ONE_TO_MANY,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Int32,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    attr,
    rel,
)

__all__ = [
    "FLEET_MODEL",
    "VAULT_MODEL",
    "Barge",
    "Fleet",
    "Slip",
    "Tug",
    "Vault",
    "Vessel",
]

_NS = "parallax.observation"


class Vault(Entity, table="obs_vault", namespace=_NS):
    """The unversioned owner of the versioned include target — itself observed
    by nothing, so only the included level's own observation can license a
    write."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    slips: Rel[tuple["Slip", ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "vault_id"))


class Slip(Entity, table="obs_slip", namespace=_NS):
    """The VERSIONED include target: a ``tx.update`` of one derives both its
    version advance and its optimistic gate from the including read's own
    observation."""

    id: Attr[int] = attr(primary_key=True)
    vault_id: Attr[int]
    memo: Attr[str] = attr(max_length=32)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


VAULT_MODEL = DomainModel(Vault, Slip)


class Fleet(Entity, table="obs_fleet", namespace=_NS):
    """The non-temporal owner of the temporal family below."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    vessels: Rel[tuple["Vessel", ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "fleet_id"))


class Vessel(
    TxTemporal,
    table="obs_vessel",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    """The abstract, temporal position ``Fleet.vessels`` addresses. One child
    query returns rows of both concretes below, each resolved by the shared
    table's own tag column."""

    id: Attr[int] = attr(primary_key=True)
    fleet_id: Attr[int]
    name: Attr[str] = attr(max_length=32)


class Tug(Vessel, namespace=_NS, inheritance=ConcreteSubtype(tag_value="tug")):
    bollard_pull: Attr[int | None] = attr(type=Int32)


class Barge(Vessel, namespace=_NS, inheritance=ConcreteSubtype(tag_value="barge")):
    deck_area: Attr[Decimal | None] = attr(precision=18, scale=2)


FLEET_MODEL = DomainModel(Fleet, Vessel, Tug, Barge)
