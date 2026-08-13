"""The `Columns` member of the classification layout twin.

One logical model authored twice — here and in ``_layout_twin_document`` —
differing only in the root-owned ``layout``, exactly as the corpus twin
descriptors do. The duplication is the point: omission is the only ``Columns``
spelling, so a single model parameterized by layout would be a twin only in a
harness's imagination, and a shared declaration would hide the very difference
the pair exists to prove irrelevant.

Both members declare the same Entity names in the same namespace over the same
tables, so a published classification's Entity, member, and Object Key values are
comparable between them without normalizing anything.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from parallax.core import ONE_TO_MANY, Attr, DomainModel, Entity, Rel, ValueObject, attr, rel

__all__ = ["COLUMNS_TWIN", "LayoutTwinChild", "LayoutTwinItem", "TwinProfile"]

_NAMESPACE = "parallax.compatibility"


class TwinProfile(ValueObject):
    street: Attr[str]
    city: Attr[str | None]


class LayoutTwinChild(Entity, table="layout_twin_child", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    item_id: Attr[int]
    profile: Attr[TwinProfile | None]


class LayoutTwinItem(Entity, table="layout_twin", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    profile: Attr[TwinProfile | None]
    children: Rel[tuple[LayoutTwinChild, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "item_id")
    )


COLUMNS_TWIN = DomainModel(LayoutTwinItem, LayoutTwinChild)
