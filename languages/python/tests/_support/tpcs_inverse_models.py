from __future__ import annotations

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Rel,
    attr,
    rel,
)


class InverseParent(Entity, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]
    owner_id: Attr[int | None]
    links: Rel[tuple[InverseLink, ...]] = rel(reverse_of="parent")
    owner: Rel[InverseOwner | None] = rel(reverse_of="parents")


class InverseAlpha(InverseParent, table="inverse_alpha", inheritance=ConcreteSubtype):
    pass


class InverseBeta(InverseParent, table="inverse_beta", inheritance=ConcreteSubtype):
    pass


class InverseLink(Entity, table="inverse_link"):
    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int | None]
    parent: Rel[InverseParent | None] = rel(cardinality=MANY_TO_ONE, join=("parent_id", "id"))


class InverseOwner(Entity, table="inverse_owner"):
    id: Attr[int] = attr(primary_key=True)
    parents: Rel[tuple[InverseParent, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))


INVERSE_MODEL = DomainModel(InverseParent, InverseAlpha, InverseBeta, InverseLink, InverseOwner)
PARENT_ROWS: list[dict[str, object]] = [
    {"id": 1, "label": "alpha", "owner_id": 10, "family_variant": "InverseAlpha"},
    {"id": 1, "label": "beta", "owner_id": 10, "family_variant": "InverseBeta"},
]
LINK_ROW = {"id": 11, "parent_id": 1}
