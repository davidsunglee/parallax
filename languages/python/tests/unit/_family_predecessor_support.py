"""Bitemporal inheritance families whose concrete members hold Value Objects,
under each strategy and storage layout.

Each family's abstract root declares only its key. An abstract ``Account``
beneath it declares one Value Object its two concrete members inherit:
``Holding`` adds an Attribute and two Value Objects, and ``Vault`` adds one Value
Object. ``Bare``, directly under the root, adds nothing. Under ``Document``
layout a ``Vault`` row therefore keeps no document-resident Attribute and a
``Bare`` row no resident member at all, so only Value Object demand, or
raw-document observation alone, can require their Structured Column.

:func:`stored_row` lays a logical row out as the scripted port stores it under
the family's layout, its Structured Column carrying a key no member declares.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

# No `from __future__ import annotations`: the Entity classes are declared by a
# factory from annotation values, and a stringized annotation would name a local
# the declaration engine cannot resolve.

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

import pytest

from parallax.core import (
    AbstractRoot,
    AbstractSubtype,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Document,
    DomainModel,
    TablePerHierarchy,
    ValueObject,
    attr,
)
from parallax.core.base import INFINITY, DocumentValue, PresentDocument
from parallax.core.db_port import MappingRow
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityMetadata, TablePerConcreteSubtype, entity_by_name

__all__ = [
    "FAMILIES",
    "FAMILY_AXES",
    "MEMBERS",
    "MODEL",
    "UNKNOWN_KEY",
    "Family",
    "Layout",
    "Member",
    "Place",
    "Strategy",
    "member_metadata",
    "stored_row",
]

type Strategy = Literal["tph", "tpcs"]
type Layout = Literal["columns", "document"]
type Member = Literal["Holding", "Vault", "Bare"]

MEMBERS: Final[tuple[Member, ...]] = ("Holding", "Vault", "Bare")
UNKNOWN_KEY: Final = "future_key"
"""A stored Structured Column key no member of any family declares."""


class Place(ValueObject):
    city: Attr[str]
    zone: Attr[str | None]


@dataclass(frozen=True, slots=True)
class Family:
    strategy: Strategy
    layout: Layout
    namespace: str
    classes: Mapping[str, Any]
    """Every family class under its own name."""


def _family(strategy: Strategy, layout: Layout) -> Family:
    namespace = f"family.predecessor.{strategy}.{layout}"
    hierarchy = strategy == "tph"
    table = f"fp_{strategy}_{layout}"
    root: Any = type(
        "Asset",
        (Bitemporal,),
        {
            "__module__": __name__,
            "__annotations__": {"id": Attr[int]},
            "id": attr(primary_key=True),
        },
        namespace=namespace,
        inheritance=AbstractRoot(
            TablePerHierarchy("kind") if hierarchy else TablePerConcreteSubtype()
        ),
        **({"table": table} if hierarchy else {}),
        **({"layout": Document()} if layout == "document" else {}),
    )
    account: Any = type(
        "Account",
        (root,),
        {"__module__": __name__, "__annotations__": {"origin": Attr[Place | None]}},
        namespace=namespace,
        inheritance=AbstractSubtype,
    )
    declared: Mapping[Member, tuple[Any, Mapping[str, object]]] = {
        "Holding": (
            account,
            {"name": Attr[str], "home": Attr[Place], "extra": Attr[Place | None]},
        ),
        "Vault": (account, {"deposit": Attr[Place]}),
        "Bare": (root, {}),
    }
    classes: dict[str, Any] = {"Asset": root, "Account": account}
    for member, (parent, annotations) in declared.items():
        tag = member.lower()
        classes[member] = type(
            member,
            (parent,),
            {"__module__": __name__, "__annotations__": dict(annotations)},
            namespace=namespace,
            inheritance=ConcreteSubtype(tag_value=tag) if hierarchy else ConcreteSubtype(),
            **({} if hierarchy else {"table": f"{table}_{tag}"}),
        )
    return Family(strategy, layout, namespace, classes)


FAMILIES: Final[Mapping[tuple[Strategy, Layout], Family]] = {
    (strategy, layout): _family(strategy, layout)
    for strategy in ("tph", "tpcs")
    for layout in ("columns", "document")
}
MODEL: Final = DomainModel(
    *(cls for family in FAMILIES.values() for cls in family.classes.values())
)
FAMILY_AXES: Final = pytest.mark.parametrize(
    ("strategy", "layout"),
    list(FAMILIES),
    ids=[f"{strategy}-{layout}" for strategy, layout in FAMILIES],
)


def member_metadata(strategy: Strategy, layout: Layout, member: Member) -> EntityMetadata:
    """``member``'s accepted metadata in the ``strategy``/``layout`` family."""
    metadata = entity_by_name(model_of(MODEL), f"{FAMILIES[(strategy, layout)].namespace}.{member}")
    assert metadata is not None
    return metadata


def stored_row(
    strategy: Strategy,
    layout: Layout,
    member: Member,
    values: Mapping[str, DocumentValue],
    *,
    valid: tuple[dt.datetime, object],
    tx_start: dt.datetime,
    key: int = 1,
) -> MappingRow:
    """``values`` stored as ``member``'s row: domain members in the Structured
    Column beside :data:`UNKNOWN_KEY` under ``Document``, each in its own Column
    under ``Columns``."""
    start, end = valid
    row: dict[str, object] = {
        "id": key,
        "from_z": start,
        "thru_z": end,
        "in_z": tx_start,
        "out_z": INFINITY,
    }
    if strategy == "tph":
        row["kind"] = member.lower()
    if layout == "document":
        row["payload"] = PresentDocument({**values, UNKNOWN_KEY: "kept"})
        return row
    for name, value in values.items():
        row[name] = value if name == "name" else PresentDocument(value)
    return row
