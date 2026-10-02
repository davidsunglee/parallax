from __future__ import annotations

from uuid import UUID

from parallax.core import ONE_TO_MANY, Attr, DomainModel, Entity, Int32, Rel, attr, rel

_NAMESPACE = "parallax.compatibility"


class Int32Parent(Entity, table="int32_parent", namespace=_NAMESPACE):
    id: Attr[int] = attr(type=Int32, primary_key=True)
    label: Attr[str]
    children: Rel[tuple[Int32Child, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "parent_id"), order_by=("id",)
    )


class Int32Child(Entity, table="int32_child", namespace=_NAMESPACE):
    id: Attr[int] = attr(type=Int32, primary_key=True)
    parent_id: Attr[int] = attr(type=Int32)
    parent: Rel[Int32Parent | None] = rel(reverse_of="children")


class Int64Parent(Entity, table="int64_parent", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]
    children: Rel[tuple[Int64Child, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "parent_id"), order_by=("id",)
    )


class Int64Child(Entity, table="int64_child", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int]
    parent: Rel[Int64Parent | None] = rel(reverse_of="children")


class StringParent(Entity, table="string_parent", namespace=_NAMESPACE):
    id: Attr[str] = attr(primary_key=True)
    label: Attr[str]
    children: Rel[tuple[StringChild, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "parent_id"), order_by=("id",)
    )


class StringChild(Entity, table="string_child", namespace=_NAMESPACE):
    id: Attr[str] = attr(primary_key=True)
    parent_id: Attr[str]
    parent: Rel[StringParent | None] = rel(reverse_of="children")


class UuidParent(Entity, table="uuid_parent", namespace=_NAMESPACE):
    id: Attr[UUID] = attr(primary_key=True)
    label: Attr[str]
    children: Rel[tuple[UuidChild, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "parent_id"), order_by=("id",)
    )


class UuidChild(Entity, table="uuid_child", namespace=_NAMESPACE):
    id: Attr[UUID] = attr(primary_key=True)
    parent_id: Attr[UUID]
    parent: Rel[UuidParent | None] = rel(reverse_of="children")


IDENTIFIER_TYPES = DomainModel(
    Int32Parent,
    Int32Child,
    Int64Parent,
    Int64Child,
    StringParent,
    StringChild,
    UuidParent,
    UuidChild,
)
