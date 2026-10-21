"""A versioned table-per-hierarchy family for target writes of a
subtype, which state the version their family's root declares."""

from __future__ import annotations

from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Int32,
    TablePerHierarchy,
    attr,
)

__all__ = ["VESSEL", "Ferry", "Tug", "Vessel"]

_NS = "parallax.targetwrites"


class Vessel(
    Entity,
    table="vessel",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


class Ferry(Vessel, namespace=_NS, inheritance=ConcreteSubtype(tag_value="ferry")):
    berths: Attr[int | None]


class Tug(Vessel, namespace=_NS, inheritance=ConcreteSubtype(tag_value="tug")):
    pull: Attr[int | None]


VESSEL = DomainModel(Vessel, Ferry, Tug)
