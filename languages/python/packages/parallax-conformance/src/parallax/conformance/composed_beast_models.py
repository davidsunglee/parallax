"""``models/composed-beast-reader.yaml``: a table-per-hierarchy family composed
PARTIALLY. The shared ``beast`` table also holds rows of a concrete subtype this
model omits, which an unnarrowed ``Beast`` read returns and diagnoses."""

from parallax.core import (
    ONE_TO_MANY,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Rel,
    TablePerHierarchy,
    attr,
    rel,
)

_NS = "parallax.compatibility"

__all__ = ["COMPOSED_BEAST_READER", "Beast", "Keeper", "Wolf"]


class Beast(
    Entity,
    table="beast",
    namespace=_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    keeper_id: Attr[int | None]


class Wolf(Beast, namespace=_NS, inheritance=ConcreteSubtype(tag_value="wolf")):
    howl: Attr[str | None] = attr(max_length=16)


class Keeper(Entity, table="keeper", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=32)
    beasts: Rel[tuple[Beast, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "keeper_id"), order_by=("id",)
    )


COMPOSED_BEAST_READER = DomainModel(Beast, Wolf, Keeper)
